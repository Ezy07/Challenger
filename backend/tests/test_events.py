from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.models import Camera, DetectionType, Roi, RoiRule, Severity


def cam_id(db_session, name="CAM_0001"):
    with db_session() as db:
        return db.scalar(select(Camera.id).where(Camera.name == name))


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
    assert len(tcs) == 3


def test_demo_history_is_consistent(client, manager):
    """시연 데이터의 처리완료 이벤트는 해제 항목이 모두 허가돼 있어야 한다"""
    done = client.get("/api/events", params={"status": "DONE", "size": 50}, headers=manager).json()["items"]
    for row in done:
        detail = client.get(f"/api/events/{row['id']}", headers=manager).json()
        assert all(c["permitted"] for c in detail["check_items"])
        assert detail["actions"][-1]["action_type"] == "RESOLVE"
