from sqlalchemy import select

from app import push
from app.models import Camera, PushSubscription, Severity


def sub(n: int, severity: str = "MEDIUM") -> dict:
    return {"endpoint": f"https://push.example/send/{n}", "keys": {"p256dh": f"key{n}", "auth": f"auth{n}"}, "min_severity": severity}


def test_turn_device_on_and_off(client, manager):
    key = client.get("/api/push/key", headers=manager).json()
    assert key["enabled"] and len(key["public_key"]) == 87  # P-256 공개키 65바이트 → base64url

    res = client.put("/api/push/subscriptions", json=sub(1), headers={**manager, "User-Agent": "Galaxy S24"})
    assert res.status_code == 200 and res.json()["device"] == "Galaxy S24"
    # 같은 기기에서 다시 켜면 줄이 늘지 않고 받을 심각도만 바뀐다
    client.put("/api/push/subscriptions", json=sub(1, "HIGH"), headers=manager)
    mine = client.get("/api/push/subscriptions", headers=manager).json()
    assert [(d["endpoint"], d["min_severity"]) for d in mine] == [(sub(1)["endpoint"], "HIGH")]

    assert client.put("/api/push/subscriptions", json={**sub(2), "endpoint": "http://x"}, headers=manager).status_code == 422
    assert client.delete("/api/push/subscriptions", params={"endpoint": sub(1)["endpoint"]}, headers=manager).status_code == 204
    assert client.get("/api/push/subscriptions", headers=manager).json() == []


def test_device_moves_to_whoever_logged_in(client, admin, manager):
    """한 브라우저에서 계정을 바꿔 로그인하고 다시 켜면 그 계정의 기기가 된다 (다른 사람 기기는 못 끈다)"""
    client.put("/api/push/subscriptions", json=sub(1), headers=manager)
    client.put("/api/push/subscriptions", json=sub(1), headers=admin)
    assert client.get("/api/push/subscriptions", headers=manager).json() == []
    client.delete("/api/push/subscriptions", params={"endpoint": sub(1)["endpoint"]}, headers=manager)
    assert len(client.get("/api/push/subscriptions", headers=admin).json()) == 1


def test_new_event_pushed_by_severity(client, admin, manager, ingest, db_session, monkeypatch):
    sent = []

    def deliver(info, payload):
        sent.append((info["endpoint"], payload))
        return 410 if info["endpoint"].endswith("/3") else 201  # 3번 기기는 알림을 꺼 버림

    monkeypatch.setattr(push, "_dispatch", push._send_all)  # 테스트에선 바로 보낸다
    monkeypatch.setattr(push, "_deliver", deliver)
    client.put("/api/push/subscriptions", json=sub(1, "HIGH"), headers=admin)
    client.put("/api/push/subscriptions", json=sub(2, "LOW"), headers=manager)
    client.put("/api/push/subscriptions", json=sub(3, "LOW"), headers=manager)
    with db_session() as db:
        cam = db.scalars(select(Camera).order_by(Camera.id)).first()

    # 안전모 미착용은 기본 심각도 '중간' → 높음만 받는 1번 기기엔 안 간다
    res = client.post("/api/events", json={"detection_type": "NO_HELMET", "camera_id": cam.id, "confidence": 0.9}, headers=ingest).json()
    assert res["created"]
    assert sorted(e for e, _ in sent) == [sub(2)["endpoint"], sub(3)["endpoint"]]
    payload = sent[0][1]
    assert payload["title"] == "[중간] 안전모 미착용" and payload["tag"] == f"event-{res['event_id']}"
    assert payload["url"] == f"/monitor-camera.html?camera={cam.id}" and cam.name in payload["body"]  # 누르면 그 카메라 영상
    with db_session() as db:
        left = {s.endpoint: s.last_sent_at for s in db.scalars(select(PushSubscription))}
    assert sub(3)["endpoint"] not in left            # 410 → 지움
    assert left[sub(2)["endpoint"]] is not None      # 보낸 시각 기록

    # 쿨다운으로 이벤트를 안 만들면 알림도 없다
    sent.clear()
    again = client.post("/api/events", json={"detection_type": "NO_HELMET", "camera_id": cam.id, "confidence": 0.9}, headers=ingest).json()
    assert not again["created"] and sent == []


def test_send_test(client, manager, monkeypatch):
    sent = []
    monkeypatch.setattr(push, "_dispatch", push._send_all)
    monkeypatch.setattr(push, "_deliver", lambda info, payload: sent.append(payload["title"]) or 201)
    assert client.post("/api/push/test", headers=manager).status_code == 409  # 켠 기기가 없음
    client.put("/api/push/subscriptions", json=sub(1, Severity.HIGH.value), headers=manager)
    assert client.post("/api/push/test", headers=manager).json() == {"devices": 1}
    assert sent == ["🔔 테스트 알림"]


def test_push_only_to_chosen_zones(client, admin, manager, ingest, db_session, monkeypatch):
    sent = []
    monkeypatch.setattr(push, "_dispatch", push._send_all)
    monkeypatch.setattr(push, "_deliver", lambda info, payload: sent.append(info["endpoint"]) or 201)
    with db_session() as db:
        cam = db.scalars(select(Camera).where(Camera.work_zone_id.is_not(None)).order_by(Camera.id)).first()
        here = cam.work_zone_id
    other = next(z["id"] for z in client.get("/api/work-zones", headers=manager).json() if z["id"] != here)

    assert client.put("/api/push/subscriptions", json={**sub(9), "zone_ids": [99999]}, headers=manager).status_code == 422
    client.put("/api/push/subscriptions", json={**sub(1, "LOW"), "zone_ids": [here]}, headers=manager)   # 이 구역
    client.put("/api/push/subscriptions", json={**sub(2, "LOW"), "zone_ids": [other]}, headers=manager)  # 다른 구역
    client.put("/api/push/subscriptions", json=sub(3, "LOW"), headers=admin)                              # 전체 구역
    mine = {d["endpoint"]: d for d in client.get("/api/push/subscriptions", headers=manager).json()}
    assert mine[sub(1)["endpoint"]]["zone_ids"] == [here] and mine[sub(1)["endpoint"]]["high_any_zone"] is True

    client.post("/api/events", json={"detection_type": "NO_HELMET", "camera_id": cam.id, "confidence": 0.9}, headers=ingest)
    assert sorted(sent) == [sub(1)["endpoint"], sub(3)["endpoint"]]  # 다른 구역만 고른 2번은 못 받음

    sent.clear()  # 구역이 없는 경보(카메라 없음)는 모두 받는다
    client.post("/api/events", json={"detection_type": "NO_VEST", "confidence": 0.9}, headers=ingest)
    assert sorted(sent) == [sub(1)["endpoint"], sub(2)["endpoint"], sub(3)["endpoint"]]

    users = {u["login_id"]: u for u in client.get("/api/users", headers=admin).json()}
    devices = [d for u in users.values() for d in u["push_devices"]]
    assert len(devices) == 3 and any(d["zone_names"] == [] for d in devices)


def test_wants_high_any_zone():
    class Zone:
        def __init__(self, i):
            self.id = i

    s = PushSubscription(min_severity=Severity.LOW, high_any_zone=True)
    s.zones = []
    assert push.wants(s, Severity.LOW, 5)  # 구역을 안 고르면 전체
    s.zones = [Zone(1)]
    assert not push.wants(s, Severity.MEDIUM, 5) and push.wants(s, Severity.MEDIUM, 1)
    assert push.wants(s, Severity.HIGH, 5)  # 높음은 구역과 상관없이
    s.high_any_zone = False
    assert not push.wants(s, Severity.HIGH, 5) and push.wants(s, Severity.HIGH, None)
    s.min_severity = Severity.HIGH
    assert not push.wants(s, Severity.MEDIUM, 1)


def test_zone_summary_counts_high_alert_devices(client, manager):
    zones = client.get("/api/work-zones/summary", headers=manager).json()
    assert all(z["high_alert_devices"] == 0 for z in zones)
    client.put("/api/push/subscriptions", json={**sub(1, "HIGH"), "zone_ids": [zones[0]["id"]], "high_any_zone": False},
               headers=manager)
    got = {z["id"]: z["high_alert_devices"] for z in client.get("/api/work-zones/summary", headers=manager).json()}
    assert got[zones[0]["id"]] == 1 and got[zones[1]["id"]] == 0
