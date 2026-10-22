import numpy as np
from sqlalchemy import select

from app import judging, ppe, zone_events
from app.config import settings
from app.models import Camera, Event
from app.ppe import NO_HELMET, NO_VEST, Job, Judge, Trigger, wearing
from app.vision import Box, Snapshot

FLOORS = {NO_HELMET: 0.8, NO_VEST: 0.8}


def person(tid=1, conf=0.9, x=200, h=100):
    return Box(x - 20, 300, x + 20, 300 + h, "person", conf, track_id=tid)  # 머리 = y 285~330 · 몸통 = 315~375


def helmet(x=200, y=300):
    return Box(x - 8, y - 8, x + 8, y + 8, "helmet", 0.4)


def vest(x=200, y=340):
    return Box(x - 18, y - 20, x + 18, y + 20, "vest", 0.4)


def observe(judge, boxes, now, floors=FLOORS):
    return judge.observe(7, boxes, floors, now, window=3.0, min_px=60)


def run(judge, boxes_at, seconds, start=0.0, step=0.5, floors=FLOORS):
    """step 초마다 boxes_at(i) 장면을 넣고 나온 경보를 모두 돌려준다"""
    out = []
    for i in range(int(seconds / step) + 1):
        out += observe(judge, boxes_at(i), start + i * step, floors)
    return out


def test_wearing_regions():
    p = person()
    assert wearing(p, [helmet(), vest()]) == {"helmet": True, "vest": True}
    assert wearing(p, [helmet(y=350)]) == {"helmet": False, "vest": False}   # 허리춤에 든 안전모
    assert wearing(p, [helmet(x=300)])["helmet"] is False                     # 옆 사람 머리
    assert wearing(p, [vest(y=395)])["vest"] is False                         # 발밑


def test_fires_after_window_once_per_worker():
    j = Judge()
    trig = run(j, lambda i: [person(), vest()], 6.0)
    assert [(t.code, t.person.track_id) for t in trig] == [(NO_HELMET, 1)]   # 3초 지켜본 뒤 한 번, 조끼는 입음
    assert run(j, lambda i: [person(), vest()], 3.0, start=6.5) == []        # 같은 작업자는 다시 안 냄


def test_brief_misses_are_ignored():
    j = Judge()
    # 0.5초마다 보는데 네 번에 한 번만 안전모를 놓침 → 착용
    assert run(j, lambda i: [person(), vest()] + ([] if i % 4 == 0 else [helmet()]), 6.0) == []


def test_skips_untracked_small_onboard_or_low_conf_workers():
    nothing = lambda boxes: run(Judge(), lambda i: boxes, 6.0) == []
    assert nothing([person(tid=None)])
    assert nothing([person(h=40)])                                              # 너무 작게 보임
    assert nothing([person(), Box(150, 250, 300, 450, "excavator", 0.9, track_id=9)])  # 장비에 탄 사람
    assert nothing([person(conf=0.6)])                                          # 판정 기준 미달


def test_each_code_separately():
    assert [t.code for t in run(Judge(), lambda i: [person(), helmet()], 6.0)] == [NO_VEST]
    assert sorted(t.code for t in run(Judge(), lambda i: [person()], 6.0)) == [NO_HELMET, NO_VEST]
    # 판정 기준 화면에서 사용을 끈 유형은 floors 에서 빠진다
    assert [t.code for t in run(Judge(), lambda i: [person()], 6.0, floors={NO_HELMET: 0.8})] == [NO_HELMET]


def test_record_creates_event(db_session, monkeypatch):
    saved = []
    monkeypatch.setattr(judging, "write_snapshot", lambda jpeg, *a: saved.append(a) or "snapshots/x/h.jpg")
    monkeypatch.setattr(ppe.vision, "render", lambda *a, **kw: b"jpeg")
    with db_session() as db:
        cam = db.scalars(select(Camera).order_by(Camera.id)).first()
        cam_id, cam_name = cam.id, cam.name
    first = ppe.record(db_session, Job(Trigger(cam_id, NO_HELMET, person(), 0.91), cam_name, Snapshot(0, None, 0.0, []), []))
    assert first.created
    again = ppe.record(db_session, Job(Trigger(cam_id, NO_HELMET, person(tid=2), 0.91), cam_name, Snapshot(0, None, 0.0, []), []))
    assert not again.created and "쿨다운" in again.reason  # 해제 항목이 없는 유형이라 쿨다운만
    with db_session() as db:
        ev = db.get(Event, first.event_id)
        assert ev.detection_type.code == NO_HELMET and ev.roi_id is None and ev.bbox == [180, 300, 220, 400]
    assert [a[1] for a in saved] == [NO_HELMET]


def test_live_only_with_ppe_model(client, admin, monkeypatch):
    live = lambda: {t["code"]: t["live"] for t in client.get("/api/detection-types", headers=admin).json()}
    assert not live()[NO_HELMET]
    monkeypatch.setattr(settings, "yolo_ppe_model", "ppe_openvino_model")
    assert live()[NO_HELMET] and live()[NO_VEST]


def test_detector_adds_only_ppe_parts(monkeypatch):
    from app import vision

    def fake_run(model, frame, conf):
        if model == "ppe":  # PPE 모델의 사람은 버리고 안전모 · 조끼만 (낮은 confidence 도 받음)
            assert conf <= settings.ppe_part_conf
            return [person(conf=0.9), helmet(), vest()]
        return [person(conf=0.9)]

    d = vision.Detector()
    d._model, d._ppe = "base", "ppe"
    monkeypatch.setattr(vision.Detector, "_run", staticmethod(fake_run))
    assert d.ppe_ready and [b.name for b in d.detect(None)] == ["person", "helmet", "vest"]
    assert vision.keep_box(helmet()) and not vision.keep_box(Box(0, 0, 1, 1, "truck", 0.4))


def test_summary_is_majority_per_worker(monkeypatch):
    j = Judge()
    monkeypatch.setattr(ppe, "judge", j)
    # 1번: 안전모 · 조끼 모두 (한 번 놓침) · 2번: 조끼만 · 3번: 오래전에 사라짐
    for i in range(6):
        observe(j, [person(tid=1, x=200), vest(x=200)] + ([helmet(x=200)] if i else []), i * 0.5)
    observe(j, [person(tid=3, x=600)], 0.0)
    for i in range(6):
        observe(j, [person(tid=2, x=400), vest(x=400)], 2.5 + i * 0.1)
    assert ppe.summary(7, now=3.0) == {"checked": 2, "helmet": 1, "vest": 2}
    assert ppe.summary(8, now=3.0) == {"checked": 0, "helmet": 0, "vest": 0}  # 다른 카메라


def test_people_api(client, admin, monkeypatch):
    from types import SimpleNamespace

    from app import vision
    from app.zone_events import Rule

    snap = Snapshot(0, None, 0.0, [person(tid=1), helmet()])
    feed = SimpleNamespace(camera_id=5, latest=snap, workers=lambda now: 1)
    monkeypatch.setattr(vision, "live_feeds", lambda: [feed])
    monkeypatch.setattr(ppe, "summary", lambda cam, now: {"checked": 1, "helmet": 1, "vest": 0})
    # PPE 모델이 없으면 작업자 수만
    assert client.get("/api/stream/people", headers=admin).json() == [{"camera_id": 5, "workers": 1, "ppe": None, "signalmen": None}]
    monkeypatch.setattr(vision.detector, "_ppe", "ppe")
    monkeypatch.setattr(zone_events, "rules", {NO_HELMET: Rule(True, 0.8, 60)})
    assert client.get("/api/stream/people", headers=admin).json() == [
        {"camera_id": 5, "workers": 1, "ppe": {"checked": 1, "helmet": 1, "vest": 0}, "signalmen": None}]


def test_feed_counts_recent_workers(monkeypatch):
    from app import vision

    monkeypatch.setattr(vision, "make_tracker", lambda: None)
    feed = vision.Feed((1, "x"), "x", True, "CAM")
    feed.latest = Snapshot(0, None, 0.0, [])
    clock = [100.0]
    monkeypatch.setattr(vision.time, "monotonic", lambda: clock[0])
    feed.set_boxes(0, [person(tid=1), person(tid=2, x=400)])
    clock[0] = 101.0
    feed.set_boxes(1, [person(tid=1), person(tid=None, x=600)])  # 2번은 이번 프레임에 놓침 · 번호 없는 사람 하나
    assert feed.workers() == 3
    clock[0] = 103.5
    feed.set_boxes(2, [person(tid=1)])
    assert feed.workers() == 1  # 2번은 2초 넘게 안 보여 빠짐


def test_ppe_model_every_other_detection(monkeypatch):
    from app import vision

    calls = []

    def fake_run(model, frame, conf):
        calls.append(model)
        return [helmet(), vest()] if model == "ppe" else [person(conf=0.9)]

    d = vision.Detector()
    d._model, d._ppe = "base", "ppe"
    monkeypatch.setattr(vision.Detector, "_run", staticmethod(fake_run))
    assert [b.name for b in d.detect(None, with_ppe=False)] == ["person"] and calls == ["base"]

    monkeypatch.setattr(settings, "ppe_every", 2)
    monkeypatch.setattr(vision, "detector", d)  # PPE 모델을 따로 쓸 때만 번갈아 돌린다
    feed = vision.Feed((7, "x"), "x", True, "CAM_7")
    turns = [feed.ppe_turn() for _ in range(5)]
    assert turns == [True, False, True, False, True]

    # 건너뛴 프레임: 화면엔 직전 안전모 · 조끼를 그대로, 넘긴 박스 자체는 그대로
    first = feed.shown_boxes([person(), helmet(), vest()], True)
    assert [b.name for b in first] == ["person", "helmet", "vest"]
    assert [b.name for b in feed.shown_boxes([person()], False)] == ["person", "helmet", "vest"]
    assert [b.name for b in feed.shown_boxes([person()], True)] == ["person"]  # 새로 돌렸는데 없으면 지움

    monkeypatch.setattr(settings, "ppe_every", 1)
    assert all(feed.ppe_turn() for _ in range(3))


def test_frames_without_ppe_model_are_not_judged(monkeypatch):
    from app import vision

    monkeypatch.setattr(vision.detector, "_ppe", "ppe")
    monkeypatch.setattr(zone_events, "rules", {NO_HELMET: zone_events.Rule(True, 0.5, 0)})
    monkeypatch.setattr(ppe, "judge", Judge())
    feed = vision.Feed((7, "x"), "x", True, "CAM_7")
    frame = np.zeros((600, 1000, 3), np.uint8)
    zone_events.on_detect(feed, Snapshot(0, frame, 0.0, [person()], ppe=False))
    assert ppe.judge.watches == {}
    zone_events.on_detect(feed, Snapshot(1, frame, 0.0, [person()], ppe=True))
    assert list(ppe.judge.watches) == [(7, 1)]


def test_one_model_with_helmet_and_vest(monkeypatch):
    """기본 모델이 안전모 · 조끼까지 학습한 것이면(site6) PPE 모델 없이 그 모델로 판정한다"""
    from types import SimpleNamespace

    from app import vision

    seen = []

    def fake_run(model, frame, conf):
        seen.append(conf)
        return [person(conf=0.9), Box(0, 0, 9, 9, "truck", 0.35), helmet(), vest()]  # 안전모 · 조끼 · 트럭 모두 0.35~0.4

    d = vision.Detector()
    d._model = SimpleNamespace(names={0: "person", 1: "helmet", 2: "vest", 3: "truck"})
    monkeypatch.setattr(vision.Detector, "_run", staticmethod(fake_run))
    monkeypatch.setattr(vision, "min_conf", None)
    assert d.builtin_ppe and d.ppe_ready
    # 안전모 · 조끼만 PPE_PART_CONF 까지 낮춰 받고, 트럭은 원래 기준(YOLO_CONF) 미달이라 뺀다
    assert [b.name for b in d.detect(None)] == ["person", "helmet", "vest"]
    assert seen == [settings.ppe_part_conf]

    monkeypatch.setattr(vision, "detector", d)
    monkeypatch.setattr(settings, "ppe_every", 2)
    feed = vision.Feed((7, "x"), "x", True, "CAM_7")
    assert all(feed.ppe_turn() for _ in range(4))     # 모델을 따로 안 돌리니 매번 판정

    plain = vision.Detector()
    plain._model = SimpleNamespace(names={0: "person", 1: "truck"})
    assert not plain.ppe_ready                          # 안전모 · 조끼를 모르면 미착용 판정 안 함


def test_ppe_model_wins_over_base_helmets(monkeypatch):
    """PPE 모델도 주면 기본 모델의 안전모 · 조끼는 버린다 (같은 안전모가 두 번 잡히지 않게)"""
    from app import vision

    def fake_run(model, frame, conf):
        return [person(conf=0.9), helmet()] if model == "base" else [helmet(x=201), vest()]

    d = vision.Detector()
    d._model, d._ppe = "base", "ppe"
    monkeypatch.setattr(vision.Detector, "_run", staticmethod(fake_run))
    boxes = d.detect(None)
    assert [b.name for b in boxes] == ["person", "helmet", "vest"] and boxes[1].x1 == helmet(x=201).x1
