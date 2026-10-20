from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.config import settings
from app.models import Camera, DetectionType, Event, EventSnapshot, EventStatus, Roi, RoiRule, Severity


def cam_id(db_session, name="CAM_0001"):
    with db_session() as db:
        return db.scalar(select(Camera.id).where(Camera.name == name))


def test_tc_hook_overlap_creates_event(client, manager):
    made = client.post("/api/events/tc-hook", headers=manager)
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["created"] is True
    detail = client.get(f"/api/events/{body['event_id']}", headers=manager).json()
    assert detail["detection_code"] == "TC_HOOK_PROXIMITY"
    assert detail["detection_label"] == "TC 후크 근접"
    assert detail["severity"] == "HIGH"
    again = client.post("/api/events/tc-hook", headers=manager).json()
    assert again["created"] is False and again["reason"].startswith("쿨다운")
    assert client.post("/api/events/tc-hook").status_code == 401


def test_wind_gust_creates_event(client, manager, db_session):
    made = client.post("/api/events/wind-gust", headers=manager)
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["created"] is True
    detail = client.get(f"/api/events/{body['event_id']}", headers=manager).json()
    assert detail["detection_code"] == "WEATHER"
    assert detail["detection_label"] == "기상 경보"
    assert detail["severity"] == "MEDIUM"
    same = client.post("/api/events/wind-gust", headers=manager).json()
    assert same["created"] is False and same["reason"].startswith("쿨다운")
    with db_session() as db:
        ev = db.get(Event, body["event_id"])
        ev.detected_at = datetime.now() - timedelta(seconds=30)
        db.commit()
    nxt = client.post("/api/events/wind-gust", headers=manager).json()
    assert nxt["created"] is True and nxt["event_id"] != body["event_id"]
    assert client.post("/api/events/wind-gust").status_code == 401


def test_ingest_requires_key(client):
    assert client.post("/api/events", json={"detection_type": "NO_HELMET"}).status_code == 401


def test_ingest_threshold_and_cooldown(client, ingest, db_session):
    cam = cam_id(db_session)
    t0 = datetime(2026, 10, 3, 9, 0, 0)
    body = {"detection_type": "NO_HELMET", "camera_id": cam, "detected_at": t0.isoformat()}

    low = client.post("/api/events", json={**body, "confidence": 0.5}, headers=ingest).json()
    assert low == {"created": False, "event_id": None, "reason": "판정 기준 미달 (0.50 < 0.80)"}

    first = client.post("/api/events", json={**body, "confidence": 0.9}, headers=ingest).json()
    assert first["created"]

    soon = {**body, "confidence": 0.9, "detected_at": (t0 + timedelta(seconds=30)).isoformat()}
    assert client.post("/api/events", json=soon, headers=ingest).json()["reason"].startswith("쿨다운")

    later = {**body, "confidence": 0.9, "detected_at": (t0 + timedelta(seconds=61)).isoformat()}
    assert client.post("/api/events", json=later, headers=ingest).json()["created"]


def test_unpermitted_event_holds_alarm_instead_of_new(client, ingest, manager, db_session):
    """해제 항목이 있는 유형(장비 근접)은 작업 허가 전이면 새 이벤트를 만들지 않고, 그 이벤트가 허가 대기(holding)로 남는다"""
    cam, other = cam_id(db_session), cam_id(db_session, "CAM_0002")
    with db_session() as db:  # 시연 데이터의 처리 전 장비 근접은 치워 둔다
        for ev in db.scalars(select(Event).join(DetectionType).where(DetectionType.code == "EQUIPMENT_PROXIMITY")):
            ev.status = EventStatus.DONE
        db.commit()
    t0 = datetime.now().replace(microsecond=0) - timedelta(minutes=10)
    body = {"detection_type": "EQUIPMENT_PROXIMITY", "camera_id": cam, "confidence": 0.9}
    post = lambda sec, **kw: client.post("/api/events", headers=ingest, json={
        **body, **kw, "detected_at": (t0 + timedelta(seconds=sec)).isoformat()}).json()
    holding = lambda ev_id: client.get(f"/api/events/{ev_id}", headers=manager).json()["holding"]

    first = post(0)
    assert first["created"] and holding(first["event_id"])
    soon = post(5)  # 쿨다운(30초) 안
    assert (soon["created"], soon["event_id"]) == (False, first["event_id"]) and "경보 지속" in soon["reason"]
    later = post(100)  # 쿨다운이 지나도 허가 전이면 그대로
    assert (later["created"], later["event_id"]) == (False, first["event_id"])
    assert post(110, camera_id=other)["created"]  # 다른 카메라는 따로

    rows = client.get("/api/events", params={"status": "NEW", "size": 200}, headers=manager).json()["items"]
    assert next(r for r in rows if r["id"] == first["event_id"])["holding"]
    helmet = client.post("/api/events", headers=ingest, json={"detection_type": "NO_HELMET", "camera_id": cam,
                                                               "confidence": 0.9}).json()
    assert not holding(helmet["event_id"])  # 해제 항목이 없는 유형은 허가 대기가 아님

    # 항목을 모두 허가하면 (처리완료 전이라도) 경보가 풀리고 다음 탐지는 새 이벤트
    url = f"/api/events/{first['event_id']}/actions"
    checks = client.get(f"/api/events/{first['event_id']}", headers=manager).json()["check_items"]
    client.post(url, json={"action_type": "PERMIT", "check_item_id": checks[0]["id"]}, headers=manager)
    assert not post(200)["created"] and holding(first["event_id"])  # 하나만 허가 → 아직 허가 대기
    for c in checks[1:]:
        client.post(url, json={"action_type": "PERMIT", "check_item_id": c["id"]}, headers=manager)
    assert not holding(first["event_id"])
    again = post(300)
    assert again["created"] and again["event_id"] != first["event_id"]


def test_roi_rule_overrides_default(client, ingest, manager, db_session):
    cam = cam_id(db_session)
    with db_session() as db:
        roi = Roi(camera_id=cam, name="갱폼 하부", polygon=[[0, 0], [10, 0], [10, 10]])
        db.add(roi)
        db.flush()
        helmet = db.scalar(select(DetectionType.id).where(DetectionType.code == "NO_HELMET"))
        db.add(RoiRule(roi_id=roi.id, detection_type_id=helmet, min_confidence=Decimal("0.4"), severity=Severity.HIGH))
        db.commit()
        roi_id = roi.id

    res = client.post("/api/events", json={"detection_type": "NO_HELMET", "camera_id": cam, "roi_id": roi_id,
                                           "confidence": 0.5}, headers=ingest).json()
    assert res["created"]
    detail = client.get(f"/api/events/{res['event_id']}", headers=manager).json()
    assert detail["severity"] == "HIGH"
    assert detail["roi_name"] == "갱폼 하부"


def test_roi_must_belong_to_camera(client, ingest, db_session):
    with db_session() as db:
        roi = Roi(camera_id=cam_id(db_session, "CAM_0002"), name="x", polygon=[])
        db.add(roi)
        db.commit()
    res = client.post("/api/events", json={"detection_type": "NO_HELMET", "camera_id": cam_id(db_session),
                                           "roi_id": roi.id}, headers=ingest)
    assert res.status_code == 422


def test_list_filters(client, manager):
    today = date.today().isoformat()
    res = client.get("/api/events", params={"date_from": today, "date_to": today}, headers=manager).json()
    assert res["total"] == 9
    assert res["items"][0]["detection_code"] == "LOAD_OVERHEAD_WORKER"  # 최신순

    open_ = client.get("/api/events", params=[("status", "NEW"), ("status", "ACK")], headers=manager).json()
    assert {i["status"] for i in open_["items"]} == {"NEW", "ACK"}
    assert open_["total"] == 3
    assert all(i["camera_id"] for i in open_["items"] if i["camera_name"])  # 관제 화면이 카메라별로 묶는다

    by_sev = client.get("/api/events", params={"sort": "severity"}, headers=manager).json()["items"]
    assert [i["severity"] for i in by_sev[:3]] == ["HIGH", "HIGH", "HIGH"]
    assert by_sev[-1]["severity"] == "LOW"

    zones = client.get("/api/work-zones", headers=manager).json()
    zone1 = next(z["id"] for z in zones if z["name"] == "101동 갱폼 인양구역")
    in_zone = client.get("/api/events", params={"work_zone_id": zone1}, headers=manager).json()
    assert in_zone["total"] == 3
    assert {i["work_zone_name"] for i in in_zone["items"]} == {"101동 갱폼 인양구역"}

    paged = client.get("/api/events", params={"size": 4, "page": 3}, headers=manager).json()
    assert len(paged["items"]) == 1

    # 시간대: 추이 차트 막대를 누르면 그 시간에 감지된 이벤트만
    hour = datetime.fromisoformat(res["items"][0]["detected_at"]).hour
    at_hour = client.get("/api/events", params={"hour": hour}, headers=manager).json()
    assert at_hour["total"] >= 1
    assert all(datetime.fromisoformat(i["detected_at"]).hour == hour for i in at_hour["items"])
    assert client.get("/api/events", params={"hour": 24}, headers=manager).status_code == 422


def test_resolve_requires_all_permits(client, manager):
    items = client.get("/api/events", params={"detection_type": "LOAD_OVERHEAD_WORKER"}, headers=manager).json()["items"]
    eid = items[0]["id"]
    url = f"/api/events/{eid}/actions"

    detail = client.post(url, json={"action_type": "ACK"}, headers=manager).json()
    assert detail["status"] == "ACK"
    checks = detail["check_items"]
    assert [c["title"] for c in checks] == ["인양 중지", "직하부 대피", "반경 통제"]

    res = client.post(url, json={"action_type": "RESOLVE"}, headers=manager)
    assert res.status_code == 409

    for c in checks:
        client.post(url, json={"action_type": "PERMIT", "check_item_id": c["id"]}, headers=manager)
    assert client.post(url, json={"action_type": "PERMIT", "check_item_id": checks[0]["id"]}, headers=manager).status_code == 409

    # 하나 취소하면 다시 해제 불가
    client.post(url, json={"action_type": "REVOKE", "check_item_id": checks[1]["id"]}, headers=manager)
    assert client.post(url, json={"action_type": "RESOLVE"}, headers=manager).status_code == 409
    client.post(url, json={"action_type": "PERMIT", "check_item_id": checks[1]["id"]}, headers=manager)

    done = client.post(url, json={"action_type": "RESOLVE", "memo": "인양 재개"}, headers=manager).json()
    assert done["status"] == "DONE"
    assert all(c["permitted"] for c in done["check_items"])
    assert done["actions"][-1]["memo"] == "인양 재개"

    # 끝난 이벤트에는 메모만
    assert client.post(url, json={"action_type": "ACK"}, headers=manager).status_code == 409
    assert client.post(url, json={"action_type": "NOTE", "memo": "사후 교육"}, headers=manager).status_code == 201


def test_check_item_must_match_type(client, manager):
    helmet = client.get("/api/events", params={"detection_type": "NO_SIGNALMAN"}, headers=manager).json()["items"][0]
    overhead = client.get("/api/events", params={"detection_type": "LOAD_OVERHEAD_WORKER"}, headers=manager).json()["items"][0]
    item = client.get(f"/api/events/{overhead['id']}", headers=manager).json()["check_items"][0]
    res = client.post(f"/api/events/{helmet['id']}/actions", json={"action_type": "PERMIT", "check_item_id": item["id"]},
                      headers=manager)
    assert res.status_code == 422


def test_false_alarm(client, manager):
    eid = client.get("/api/events", params={"status": "NEW"}, headers=manager).json()["items"][0]["id"]
    res = client.post(f"/api/events/{eid}/actions", json={"action_type": "FALSE_ALARM"}, headers=manager).json()
    assert res["status"] == "FALSE"


def test_viewer_cannot_handle(client, admin, manager):
    client.post("/api/auth/signup", json={"login_id": "viewer.x", "password": "password123", "name": "조회", "role": "VIEWER"})
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["login_id"] == "viewer.x")
    client.post(f"/api/users/{uid}/approve", headers=admin)
    from .conftest import login
    viewer = login(client, "viewer.x", "password123")
    eid = client.get("/api/events", headers=viewer).json()["items"][0]["id"]
    assert client.post(f"/api/events/{eid}/actions", json={"action_type": "ACK"}, headers=viewer).status_code == 403


def test_csv_export(client, manager):
    res = client.get("/api/events/export.csv", params={"severity": "HIGH"}, headers=manager)
    assert res.status_code == 200
    text = res.content.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0] == "번호,시각,카메라,구역,종류,심각도,신뢰도,처리 상태"
    assert len(lines) == 1 + 3
    assert all(",높음," in line for line in lines[1:])


def test_detail_has_zone_and_equipment_list(client, manager):
    eid = client.get("/api/events", params={"detection_type": "NO_SIGNALMAN"}, headers=manager).json()["items"][0]["id"]
    detail = client.get(f"/api/events/{eid}", headers=manager).json()
    zones = {z["id"]: z["name"] for z in client.get("/api/work-zones", headers=manager).json()}
    assert zones[detail["work_zone_id"]] == detail["work_zone_name"]
    tcs = [e for e in client.get("/api/equipment", headers=manager).json() if e["equip_type"] == "TC"]
    assert len(tcs) == 4


def test_demo_history_is_consistent(client, manager):
    """시연 데이터의 처리완료 이벤트는 해제 항목이 모두 허가돼 있어야 한다"""
    done = client.get("/api/events", params={"status": "DONE", "size": 50}, headers=manager).json()["items"]
    for row in done:
        detail = client.get(f"/api/events/{row['id']}", headers=manager).json()
        assert all(c["permitted"] for c in detail["check_items"])
        assert detail["actions"][-1]["action_type"] == "RESOLVE"


def test_ingest_converts_timezone_and_rejects_future(client, ingest, db_session):
    cam = cam_id(db_session)
    local = datetime(2026, 10, 2, 9, 0, 0)
    utc = local.astimezone().astimezone(timezone.utc)  # 같은 순간을 UTC 로
    body = {"detection_type": "NO_HELMET", "camera_id": cam, "confidence": 0.9}

    first = client.post("/api/events", json={**body, "detected_at": utc.isoformat()}, headers=ingest).json()
    assert first["created"]
    with db_session() as db:
        assert db.get(Event, first["event_id"]).detected_at == local

    # 같은 순간 + 30초를 다른 시간대로 보내도 쿨다운으로 잡힌다
    kst = (local + timedelta(seconds=30)).astimezone().astimezone(timezone(timedelta(hours=9)))
    soon = client.post("/api/events", json={**body, "detected_at": kst.isoformat()}, headers=ingest).json()
    assert soon["reason"].startswith("쿨다운")

    future = (datetime.now() + timedelta(hours=1)).isoformat()
    assert client.post("/api/events", json={**body, "detected_at": future}, headers=ingest).status_code == 422


def test_admin_deletes_events(client, admin, manager, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "snapshot_dir", tmp_path / "snapshots")  # seed_demo 가 예시 스냅샷을 만든 곳
    with db_session() as db:
        ev = db.scalar(select(Event).join(EventSnapshot))
        ev_id, shot = ev.id, tmp_path / ev.snapshots[0].image_path
    assert shot.exists()

    assert client.post("/api/events/delete", json={"ids": [ev_id]}, headers=manager).status_code == 403
    assert client.delete("/api/events/range", params={"date_from": "2026-01-01", "date_to": "2026-01-01"}, headers=manager).status_code == 403

    assert client.post("/api/events/delete", json={"ids": [ev_id]}, headers=admin).json() == {"deleted": 1}
    assert client.get(f"/api/events/{ev_id}", headers=admin).status_code == 404
    assert not shot.exists()

    # 전체 삭제: 검색한 기간 (끝일 포함) 만 지우고, 그 앞날은 남긴다
    end = date.today()
    start = end - timedelta(days=2)
    rng = {"date_from": start.isoformat(), "date_to": end.isoformat()}
    count = lambda p: client.get("/api/events", params={**p, "size": 1}, headers=admin).json()["total"]
    before = count({"date_to": (start - timedelta(days=1)).isoformat()})
    in_range = count(rng)
    assert in_range > 0
    assert client.delete("/api/events/range", params=rng, headers=admin).json() == {"deleted": in_range}
    assert count(rng) == 0
    assert count({"date_to": (start - timedelta(days=1)).isoformat()}) == before

    assert client.delete("/api/events/range", params={"date_from": end.isoformat()}, headers=admin).status_code == 422
    bad = {"date_from": end.isoformat(), "date_to": start.isoformat()}
    assert client.delete("/api/events/range", params=bad, headers=admin).status_code == 422
