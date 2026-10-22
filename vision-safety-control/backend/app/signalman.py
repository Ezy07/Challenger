"""조끼 색 + 추적 → 신호수 미배치 이벤트 (NO_SIGNALMAN).

- 현장 규칙: 빨간 계열 조끼 = 신호수, 노란 계열(형광 연두 포함) = 일반 작업자.
  PPE 모델(ppe.py)이 찾은 조끼 박스 중 작업자 몸통에 붙은 것의 가운데(VEST_INNER)만 HSV 로 보고,
  선명한 픽셀을 색상(H) SIGNAL_HUE_SPLIT 를 경계로 빨강 쪽 · 노랑 쪽으로 나눠 더 많은 쪽으로 정한다
  (조끼 밑 자주색 긴팔 · 반사띠 · 배경 기둥은 가장자리에 걸리므로 가운데만 본다).
  주황도 경계의 어느 쪽인지로 판정한다: 빨간 주황 = 신호수, 노란 주황 = 일반 작업자.
  선명한 빨강 · 노랑 픽셀이 COLOR_MIN 이하(회색 · 검정 · 흐린 조끼)면 색 없음.
- 한 프레임으로 정하지 않는다. 추적 번호마다 PPE_WINDOW_SEC 동안 색이 나온 표본의 과반이 빨강이면 신호수이고,
  한 번 신호수로 정한 추적 번호는 잊을 때까지 신호수 (돌아서거나 가려져도).
- 카메라에 장비(SIGNAL_CLASSES, 기본 트럭 · 굴삭기)가 보이는 동안 신호수가 SIGNAL_HOLD_SEC 초 넘게 안 보이면 경보.
  잠깐 끊겨도 GAP_SEC 까지는 계속 있는 것으로 본다. 경보 뒤에도 그대로면 REPEAT_SEC 마다 다시 내지만,
  해제 항목이 있는 유형이라 작업 허가 전에는 새 이벤트 대신 기존 경보가 이어진다 (events.create_event).
- 판정 기준(8-8)의 신호수 미배치 값은 장비에 쓴다: 장비가 추적 동안 한 번이라도 confidence 가 기준 이상이어야 센다.
  신호수를 놓치면 잘못된 경보가 나므로 작업자 쪽은 기준을 두지 않는다. 장비에 탄 사람(운전석)은 신호수로 보지 않는다.
- 카메라 한 대 화면만 본다. 신호수가 다른 카메라에만 보이는 자리에 서면 경보가 날 수 있다.
"""

import logging
from collections import deque
from dataclasses import dataclass, field

import cv2

from . import judging, ppe, proximity, vision
from .config import settings
from .judging import FORGET_SEC, Job

log = logging.getLogger("uvicorn.error")

NO_SIGNALMAN = "NO_SIGNALMAN"
LABEL = "신호수 미배치"
RED, YELLOW = "red", "yellow"
# OpenCV HSV (H 0~179, 360도의 절반). 빨강은 0 근처와 179 근처 양쪽, 노랑은 형광 연두(H 50)까지.
# 그 사이(주황)는 settings.signal_hue_split 이하면 빨강 쪽
PINK_HUE = 165   # 이 위(자홍 → 빨강)는 빨강 쪽
YELLOW_END = 50
MIN_SAT, MIN_VAL = 70, 60      # 이보다 흐리거나 어두운 픽셀은 색을 따지지 않는다
VEST_INNER = (0.2, 0.1)        # 조끼 박스 좌우 · 위아래에서 이 비율만큼 깎고 가운데만 본다
COLOR_MIN = 0.20               # 본 영역에서 그 색 픽셀이 이 비율 넘게
MIN_SAMPLES = 3
GAP_SEC = 2.0
REPEAT_SEC = 60.0


def signal_classes() -> set[str]:
    return judging.class_set(settings.signal_classes)


def vest_color(frame, vest: vision.Box) -> str | None:
    """조끼 박스 가운데 색: RED (빨강 · 빨간 주황) · YELLOW (노랑 · 노란 주황 · 형광 연두), 선명한 색이 없으면 None"""
    w, h = vest.x2 - vest.x1, vest.y2 - vest.y1
    mx, my = VEST_INNER
    x1, x2 = int(max(vest.x1 + mx * w, 0)), int(vest.x2 - mx * w)
    y1, y2 = int(max(vest.y1 + my * h, 0)), int(vest.y2 - my * h)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    hue, vivid = hsv[:, 0], (hsv[:, 1] >= MIN_SAT) & (hsv[:, 2] >= MIN_VAL)
    split = settings.signal_hue_split
    red = (vivid & ((hue <= split) | (hue >= PINK_HUE))).mean()
    yellow = (vivid & (hue > split) & (hue <= YELLOW_END)).mean()
    if max(red, yellow) <= COLOR_MIN:
        return None
    return RED if red > yellow else YELLOW


@dataclass
class Watch:
    last_seen: float
    samples: deque = field(default_factory=deque)  # (시각, RED | YELLOW)
    signal: bool = False


@dataclass
class Site:
    since: float           # 장비가 보이기 시작한 때
    last_seen: float       # 장비를 마지막으로 본 때
    signal_seen: float | None = None
    fired_at: float | None = None


@dataclass(frozen=True)
class Trigger:
    camera_id: int
    equip: vision.Box
    conf: float  # 장비가 추적 동안 받은 가장 높은 confidence


class Judge:
    """카메라 · 추적 번호마다 신호수인지, 카메라마다 장비가 언제부터 있는지 기억한다. 탐지 스레드 하나에서만 부른다."""

    def __init__(self):
        self.watches: dict[tuple[int, int], Watch] = {}  # (카메라, 작업자 번호)
        self.sites: dict[int, Site] = {}
        self.conf = judging.BestConf()                     # 장비 추적 번호마다 가장 높은 confidence

    def observe(self, camera_id: int, frame, boxes: list[vision.Box], min_conf: float, now: float, *,
                classes: set[str] | None = None, hold_sec: float | None = None, window: float | None = None,
                min_px: int | None = None) -> list[Trigger]:
        classes = signal_classes() if classes is None else classes
        hold_sec = settings.signal_hold_sec if hold_sec is None else hold_sec
        window = settings.ppe_window_sec if window is None else window
        min_px = settings.signal_min_person_px if min_px is None else min_px

        equips = [b for b in boxes if b.name in classes and b.track_id is not None
                  and self.conf.see(camera_id, b, now) >= min_conf]
        onboard = [b for b in boxes if b.name in proximity.equipment_classes() | classes]
        parts = [b for b in boxes if b.name == "vest"]

        signal_now = False
        for p in boxes:
            if p.name != "person" or p.track_id is None or p.y2 - p.y1 < min_px:
                continue
            if judging.onboard(p, onboard):
                continue
            key = (camera_id, p.track_id)
            watch = self.watches.setdefault(key, Watch(last_seen=now))
            watch.last_seen = now
            vest = ppe.part_on(p, parts, "vest")
            color = vest_color(frame, vest) if vest is not None and frame is not None else None
            if color:
                watch.samples.append((now, color))
            while watch.samples and now - watch.samples[0][0] > window:
                watch.samples.popleft()
            if not watch.signal and len(watch.samples) >= MIN_SAMPLES:
                watch.signal = sum(c == RED for _, c in watch.samples) * 2 > len(watch.samples)
            signal_now |= watch.signal

        out = []
        site = self.sites.get(camera_id)
        if equips:
            if site is None or now - site.last_seen > GAP_SEC:
                site = self.sites[camera_id] = Site(since=now, last_seen=now)
            site.last_seen = now
        if site is not None:
            if signal_now:
                site.signal_seen = now
            if now - site.last_seen > GAP_SEC:
                del self.sites[camera_id]  # 장비가 떠났다
            elif equips:
                missing_since = max(site.since, site.signal_seen or site.since)
                due = now - missing_since >= hold_sec
                if due and (site.fired_at is None or now - site.fired_at >= REPEAT_SEC
                            or (site.signal_seen or 0) > site.fired_at):
                    site.fired_at = now
                    e = max(equips, key=lambda b: self.conf.of(camera_id, b))
                    out.append(Trigger(camera_id, e, self.conf.of(camera_id, e)))

        judging.drop_stale(self.watches, camera_id, now, FORGET_SEC)
        self.conf.forget(camera_id, now)
        return out


def count(camera_id: int, now: float, fresh: float = vision.PEOPLE_FRESH_SEC) -> int:
    """화면 표시용: 지금(fresh 초 안) 보이는 신호수 수. 탐지 스레드가 고치는 중에 읽으므로 복사해서 본다"""
    return sum(1 for (cam, _), w in list(judge.watches.items())
               if cam == camera_id and w.signal and now - w.last_seen <= fresh)


# ---------------------------------------------------------------- 이벤트 · 스냅샷 기록
def record(Session, job: Job):
    """판정 기준 · 쿨다운 · 작업 허가 전 경보 유지를 적용해 이벤트를 만든다 (카메라 단위).
    스냅샷에 신호수가 있어야 할 장비를 붉은 박스로 두른다"""
    e = job.trigger.equip
    result = judging.create(Session, job, NO_SIGNALMAN, job.trigger.conf, judging.bbox(e),
                            lambda: judging.snapshot(job, NO_SIGNALMAN, marks=[(e, "신호수 없음")]))
    if result.created:
        log.info("이벤트 EV-%s: %s 신호수 미배치 (%s#%s)", result.event_id, job.camera_name,
                 vision.NAMES_KO.get(e.name, e.name), e.track_id)
    return result


judge = Judge()
