from sqlalchemy import select

from app import zone_events
from app.models import AlertRule, Camera, DetectionType, Event, Roi
from app.vision import Box, Snapshot
from app.zone_events import DWELL, GAP_SEC, INTRUSION, Judge, Job, Rule, Trigger

# 화면 좌표 (가로 0~1000, 세로 0~600) 의 왼쪽 절반. 영상은 1000×600 으로 두어 좌표가 그대로 맞게 한다
LEFT = [[0, 0], [500, 0], [500, 600], [0, 600]]
RULES = {INTRUSION: Rule(True, 0.5, 60), DWELL: Rule(True, 0.5, 300)}


def zone(**kw):
    return {"no": 1, "kind": "위험구역", "points": LEFT, "dwell": 0, "intrusion": True, "targets": ["person"], **kw}


def person(x=200, conf=0.9, name="person"):
    return Box(x - 20, 300, x + 20, 400, name, conf)  # 발밑 = (x, 400)


def observe(judge, zones, boxes, now, rules=RULES):
    return judge.observe(7, zones, boxes, 1000, 600, rules, now)


def test_intrusion_fires_once_per_stay():
    j = Judge()
    first = observe(j, [zone()], [person()], 0.0)
    assert [t.code for t in first] == [INTRUSION]
    assert observe(j, [zone()], [person()], 1.0) == []          # 계속 머무는 중
    assert observe(j, [zone()], [], 1.0 + GAP_SEC / 2) == []    # 잠깐 끊김 → 같은 체류
    assert observe(j, [zone()], [person()], 1.0 + GAP_SEC) == []
    assert observe(j, [zone()], [], 10.0) == []                 # 나감
    assert len(observe(j, [zone()], [person()], 11.0)) == 1     # 다시 들어옴


def test_dwell_waits_for_seconds():
    j = Judge()
    z = zone(dwell=5)
    for sec in range(5):  # 1초마다 탐지
        assert observe(j, [z], [person()], float(sec)) == []
    trig = observe(j, [z], [person()], 5.5)
    assert [t.code for t in trig] == [DWELL]


def test_only_targets_inside_above_threshold_count():
    j = Judge()
    assert observe(j, [zone()], [person(x=700)], 0.0) == []              # 구역 밖
    assert observe(j, [zone()], [person(name="truck")], 0.0) == []       # 탐지 대상 아님
    assert observe(j, [zone()], [person(conf=0.4)], 0.0) == []           # 판정 기준 미달
    assert len(observe(j, [zone(targets=["person", "truck"])], [person(name="truck")], 0.0)) == 1


def test_zone_settings_and_rule_switch():
    j = Judge()
    assert observe(j, [zone(targets=None)], [person()], 0.0) == []       # 저장 전
    assert observe(j, [zone(targets=[])], [person()], 0.0) == []
    assert observe(j, [zone(intrusion=False)], [person()], 0.0) == []    # 사용안함
    off = {**RULES, INTRUSION: Rule(False, 0.5, 60)}
    assert observe(j, [zone()], [person()], 0.0, off) == []              # 8-8 에서 사용 끔


def test_rules_come_from_threshold_page(client, admin, db_session):
    types = client.get("/api/detection-types", headers=admin).json()
    by_code = {t["code"]: t for t in types}
    assert by_code[INTRUSION]["live"] and by_code[DWELL]["live"] and not by_code["NO_HELMET"]["live"]
    client.patch(f"/api/detection-types/{by_code[INTRUSION]['id']}/rule", headers=admin,
                 json={"min_confidence": 0.42, "is_active": False})
    with db_session() as db:
        rules = zone_events.load_rules(db)
    assert rules[INTRUSION] == Rule(False, 0.42, by_code[INTRUSION]["cooldown_sec"])


def test_record_creates_event_roi_and_snapshot(db_session, monkeypatch):
    saved = []
    monkeypatch.setattr(zone_events, "save_snapshot", lambda *a: saved.append(a) or "snapshots/x/a.jpg")
    with db_session() as db:
        cam = db.scalars(select(Camera).order_by(Camera.id)).first()
        cam_id, cam_name, cam_zone = cam.id, cam.name, cam.work_zone_id
    trig = Trigger(cam_id, zone(), INTRUSION, person(conf=0.8))
    job = Job(trig, cam_name, Snapshot(0, None, 0.0, []), [])

    first = zone_events.record(db_session, job)
    assert first.created
    again = zone_events.record(db_session, Job(trig, cam_name, Snapshot(0, None, 0.0, []), []))
    assert not again.created and "쿨다운" in again.reason
    assert len(saved) == 1  # 규칙을 통과한 이벤트만 스냅샷을 남긴다

    with db_session() as db:
        ev = db.get(Event, first.event_id)
        roi = db.get(Roi, ev.roi_id)
        assert (roi.camera_id, roi.name, roi.work_zone_id) == (cam_id, "1번 위험구역", cam_zone)
        assert ev.detection_type.code == INTRUSION and float(ev.confidence) == 0.8
        assert [s.image_path for s in ev.snapshots] == ["snapshots/x/a.jpg"]


def test_record_respects_inactive_rule(db_session, monkeypatch):
    monkeypatch.setattr(zone_events, "save_snapshot", lambda *a: "snapshots/x/b.jpg")
    with db_session() as db:
        rule = db.scalar(select(AlertRule).join(DetectionType).where(DetectionType.code == DWELL))
        rule.is_active = False
        db.commit()
        cam_id = db.scalars(select(Camera.id).order_by(Camera.id)).first()
    res = zone_events.record(db_session, Job(Trigger(cam_id, zone(dwell=10), DWELL, person()), "CAM", None, []))
    assert not res.created and "사용 안 함" in res.reason
