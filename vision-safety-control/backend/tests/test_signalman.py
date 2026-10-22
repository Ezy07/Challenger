import numpy as np
from sqlalchemy import select

from app import judging, signalman
from app.config import settings
from app.models import Camera, Event
from app.signalman import NO_SIGNALMAN, RED, YELLOW, Job, Judge, Trigger, vest_color
from app.vision import Box, Snapshot

BGR = {"red": (30, 30, 220), "yellow": (40, 230, 220), "lime": (40, 240, 190), "gray": (120, 128, 132),
       "red_orange": (0, 100, 255), "yellow_orange": (0, 160, 255)}  # 형광 주황 H 12 · 노란 주황 H 19


def person(tid=1, x=200):
    return Box(x - 20, 300, x + 20, 400, "person", 0.9, track_id=tid)  # 몸통 = y 315~375


def vest(x=200):
    return Box(x - 18, 320, x + 18, 360, "vest", 0.4)


def truck(tid=9, conf=0.9):
    return Box(500, 200, 800, 400, "truck", conf, track_id=tid)


def frame(colors: dict[int, str] = {}):
    """회색 화면에 x 위치마다 조끼 색을 칠한다"""
    img = np.full((480, 960, 3), 128, np.uint8)
    for x, color in colors.items():
        img[320:360, x - 18:x + 18] = BGR[color]
    return img


def run(judge, scene_at, seconds, start=0.0, step=0.5, min_conf=0.75):
    """step 초마다 scene_at(i) = (화면, 박스) 를 넣고 나온 경보를 모두 돌려준다"""
    out = []
    for i in range(int(seconds / step) + 1):
        img, boxes = scene_at(i)
        out += judge.observe(7, img, boxes, min_conf, start + i * step, hold_sec=10.0, window=3.0, min_px=60)
    return out


def test_vest_color():
    assert vest_color(frame({200: "red"}), vest()) == RED
    assert vest_color(frame({200: "yellow"}), vest()) == YELLOW
    assert vest_color(frame({200: "lime"}), vest()) == YELLOW         # 형광 연두
    assert vest_color(frame({200: "red_orange"}), vest()) == RED      # 주황도 경계로 판정
    assert vest_color(frame({200: "yellow_orange"}), vest()) == YELLOW
    assert vest_color(frame({200: "gray"}), vest()) is None           # 선명한 색 없음


def test_hue_split_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "signal_hue_split", 10)  # 주황 조끼를 일반 작업자로
    assert vest_color(frame({200: "red_orange"}), vest()) == YELLOW
    assert vest_color(frame({200: "red"}), vest()) == RED
    img = frame({200: "yellow"})
    img[320:360, 182:189] = BGR["red"]                          # 가장자리에 걸친 빨간 소매 · 기둥은 안 봄
    assert vest_color(img, vest()) == YELLOW


def test_fires_when_equipment_without_signalman():
    j = Judge()
    trig = run(j, lambda i: (frame({200: "yellow"}), [person(), vest(), truck()]), 15.0)
    assert [(t.equip.track_id, t.conf) for t in trig] == [(9, 0.9)]   # 10초 뒤 한 번
    assert run(j, lambda i: (frame({200: "yellow"}), [person(), vest(), truck()]), 30.0, start=15.5) == []
    # 그대로 두면 REPEAT_SEC 마다 다시 (작업 허가 전이면 create_event 가 기존 경보를 이어 간다)
    assert len(run(j, lambda i: (frame(), [truck()]), 30.0, start=46.0)) == 1  # 70초


def test_red_vest_worker_is_signalman():
    j = Judge()
    assert run(j, lambda i: (frame({200: "red"}), [person(), vest(), truck()]), 30.0) == []
    assert signalman.count(7, now=30.0) == 0  # 모듈의 judge 가 아님
    # 신호수가 떠나면 그때부터 10초 뒤 경보
    trig = run(j, lambda i: (frame(), [truck()]), 15.0, start=30.5)
    assert len(trig) == 1


def test_signalman_stays_signalman_when_vest_hidden():
    j = Judge()
    run(j, lambda i: (frame({200: "red"}), [person(), vest(), truck()]), 3.0)
    assert run(j, lambda i: (frame(), [person(), truck()]), 30.0, start=3.5) == []  # 돌아서서 조끼 색이 안 보여도


def test_no_alarm_without_sure_equipment_or_after_it_leaves():
    nothing = lambda boxes: run(Judge(), lambda i: (frame(), boxes), 20.0) == []
    assert nothing([])
    assert nothing([truck(conf=0.6)])                                   # 판정 기준 미달
    assert nothing([Box(500, 200, 800, 400, "truck", 0.9)])             # 추적 번호 없음
    assert nothing([Box(500, 200, 800, 400, "car", 0.9, track_id=3)])   # 장비가 아님
    j = Judge()
    run(j, lambda i: (frame(), [truck()]), 8.0)
    assert run(j, lambda i: (frame(), []), 5.0, start=8.5) == []        # 10초 전에 떠남
    assert run(j, lambda i: (frame(), [truck()]), 8.0, start=14.0) == []  # 다시 와서 처음부터 셈


def test_driver_in_red_is_not_signalman():
    j = Judge()
    driver = Box(600, 250, 640, 350, "person", 0.9, track_id=1)
    seat = Box(602, 270, 638, 310, "vest", 0.4)
    img = frame()
    img[270:310, 602:638] = BGR["red"]
    assert len(run(j, lambda i: (img, [driver, seat, truck()]), 15.0)) == 1


def test_record_creates_event_and_holds(db_session, monkeypatch):
    saved = []
    monkeypatch.setattr(judging, "write_snapshot", lambda jpeg, *a: saved.append(a) or "snapshots/x/s.jpg")
    monkeypatch.setattr(signalman.vision, "render", lambda *a, **kw: b"jpeg")
    with db_session() as db:
        cam = db.scalars(select(Camera).order_by(Camera.id)).first()
        cam_id, cam_name = cam.id, cam.name
    job = lambda: Job(Trigger(cam_id, truck(), 0.88), cam_name, Snapshot(0, None, 0.0, []), [])
    first = signalman.record(db_session, job())
    assert first.created
    again = signalman.record(db_session, job())
    assert not again.created and again.event_id == first.event_id and "허가" in again.reason  # 해제 항목: 경보 지속
    with db_session() as db:
        ev = db.get(Event, first.event_id)
        assert ev.detection_type.code == NO_SIGNALMAN and ev.bbox == [500, 200, 800, 400]
    assert [a[1] for a in saved] == [NO_SIGNALMAN]


def test_live_only_with_ppe_model(client, admin, monkeypatch):
    live = lambda: {t["code"]: t["live"] for t in client.get("/api/detection-types", headers=admin).json()}
    assert not live()[NO_SIGNALMAN]
    monkeypatch.setattr(settings, "yolo_ppe_model", "ppe_openvino_model")
    assert live()[NO_SIGNALMAN]
