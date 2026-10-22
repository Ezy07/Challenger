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
