import pytest
from sqlalchemy import select

from app import proximity, zone_events
from app.models import Camera, Event
from app.proximity import GAP_SEC, PROXIMITY, Judge, Job, Trigger, distance_m
from app.vision import Box, Snapshot

KW = {"classes": {"truck", "excavator"}, "limit_m": 3.0, "hold_sec": 1.0}


def person(x=200, tid=1, conf=0.9, top=300):
    return Box(x - 20, top, x + 20, top + 100, "person", conf, track_id=tid)  # 키 100px = 1.7m, 발밑 = (x, top+100)


def truck(tid=9, conf=0.9, name="truck"):
    return Box(400, 200, 700, 400, name, conf, track_id=tid)  # 땅에 닿는 부분: y 300~400


def observe(judge, boxes, now, min_conf=0.7, **kw):
    return judge.observe(7, boxes, min_conf, now, **{**KW, **kw})


def test_distance_uses_person_height_as_ruler():
    assert distance_m(person(x=400 - 100), truck()) == pytest.approx(1.7)  # 장비 왼쪽 끝에서 100px = 키 하나
    assert distance_m(person(x=500), truck()) == 0.0                       # 장비 바로 옆 (아래쪽 띠 안)
    assert distance_m(person(x=500, top=400), truck()) == pytest.approx(1.7)  # 장비보다 카메라 쪽으로 키 하나 앞
    # 운전석: 작업자 박스가 장비 안에 다 들어 있고 발밑이 장비 아래 끝보다 한참 위
    cab = Box(500, 210, 540, 300, "person", 0.9, track_id=1)
    assert distance_m(cab, truck()) is None


def test_fires_once_after_hold_per_pair():
    j = Judge()
    near = [person(x=380), truck()]
    assert observe(j, near, 0.0) == []                  # 막 다가옴
    trig = observe(j, near, 1.0)
    assert [(t.person.track_id, t.equip.track_id) for t in trig] == [(1, 9)]
    assert trig[0].meters == pytest.approx(0.34) and trig[0].bbox == [360, 200, 700, 400]
    assert observe(j, near, 2.0) == []                  # 계속 곁에 있는 동안은 한 번만
    assert observe(j, [truck()], 2.0 + GAP_SEC / 2) == []  # 잠깐 끊김 → 같은 근접
    assert observe(j, near, 2.0 + GAP_SEC) == []
    assert observe(j, [person(x=100), truck()], 10.0) == []  # 멀어짐 (약 5m)
    assert observe(j, near, 11.0) == [] and len(observe(j, near, 12.0)) == 1  # 다시 다가옴


def test_each_worker_counts_separately():
    j = Judge()
    boxes = [person(x=380, tid=1), person(x=720, tid=2), truck()]
    observe(j, boxes, 0.0)
    assert sorted(t.person.track_id for t in observe(j, boxes, 1.0)) == [1, 2]


def test_needs_tracked_confident_equipment():
    j = Judge()
    assert observe(j, [person(x=380, tid=None), truck()], 0.0) == []        # 추적 번호 없음
    assert observe(j, [person(x=380, tid=None), truck()], 1.0) == []
    assert observe(j, [person(x=380), truck(name="car")], 0.0) == []        # 장비 아님
    assert observe(j, [person(x=380), truck(name="car")], 1.0) == []

    j = Judge()
    low = [person(x=380, tid=3, conf=0.5), truck(tid=4)]
    observe(j, low, 0.0)
    assert observe(j, low, 1.0) == []                   # 판정 기준(0.7) 미달
    sure = [person(x=380, tid=3, conf=0.8), truck(tid=4)]
    observe(j, sure, 2.0 + GAP_SEC)
    # 한 번 기준을 넘은 추적은 confidence 가 잠깐 떨어져도 같은 작업자로 이어 본다
    trig = observe(j, low, 3.0 + GAP_SEC)
    assert len(trig) == 1 and trig[0].conf == pytest.approx(0.8)


def test_record_creates_camera_event(db_session, monkeypatch):
    saved = []
    monkeypatch.setattr(zone_events, "write_snapshot", lambda jpeg, *a: saved.append(a) or "snapshots/x/p.jpg")
    monkeypatch.setattr(proximity.vision, "render", lambda *a, **kw: b"jpeg")
    with db_session() as db:
        cam = db.scalars(select(Camera).order_by(Camera.id)).first()
        cam_id, cam_name = cam.id, cam.name
    trig = Trigger(cam_id, person(x=380), truck(), 0.34, 0.88)

    first = proximity.record(db_session, Job(trig, cam_name, Snapshot(0, None, 0.0, []), []))
    assert first.created
    again = proximity.record(db_session, Job(trig, cam_name, Snapshot(0, None, 0.0, []), []))
    # 장비 근접은 해제 항목이 있어 작업 허가 전이면 새 이벤트를 만들지 않는다 (경보는 그 이벤트로 계속)
    assert not again.created and again.event_id == first.event_id and "허가 전" in again.reason
    assert [a[1] for a in saved] == [PROXIMITY]  # 스냅샷도 처음 한 번만

    with db_session() as db:
        ev = db.get(Event, first.event_id)
        assert ev.detection_type.code == PROXIMITY and ev.roi_id is None and float(ev.confidence) == 0.88
        assert ev.bbox == [360, 200, 700, 400]
        assert [s.image_path for s in ev.snapshots] == ["snapshots/x/p.jpg"]


def test_proximity_is_live_on_threshold_page(client, admin):
    types = {t["code"]: t for t in client.get("/api/detection-types", headers=admin).json()}
    assert types[PROXIMITY]["live"]


@pytest.mark.parametrize("name", ["bytetrack", "botsort"])
def test_tracker_keeps_id_while_moving(name):
    pytest.importorskip("ultralytics")
    np = pytest.importorskip("numpy")
    from app.vision import Tracker

    frame = np.zeros((600, 1000, 3), np.uint8)
    a, b = Tracker(name), Tracker(name)
    ids = []
    for step in range(6):
        boxes = [Box(100 + step * 5, 300, 140 + step * 5, 400, "person", 0.9),
                 Box(500, 200, 800, 400, "truck", 0.9)]
        out = a.update(boxes, frame)
        ids.append(tuple(box.track_id for box in out))
    assert ids[-1][0] is not None and ids[-1][1] is not None and ids[-1][0] != ids[-1][1]
    assert len(set(ids[1:])) == 1  # 움직여도 번호가 그대로
    # 카메라마다 추적기가 따로 있어도 번호가 겹치지 않는다
    other = b.update([Box(100, 300, 140, 400, "person", 0.9)], frame)
    assert other[0].track_id not in ids[-1]
    # 낮은 confidence 박스로도 이어 붙인다 (ByteTrack 2단계 매칭)
    out = a.update([Box(130, 300, 170, 400, "person", 0.15)], frame)
    assert out[0].track_id == ids[-1][0]
