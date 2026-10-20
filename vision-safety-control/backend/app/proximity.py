"""추적(ByteTrack · BoT-SORT) 결과 → 장비 근접 이벤트 (EQUIPMENT_PROXIMITY).

- 작업자(person)와 장비(PROXIMITY_CLASSES, 기본 트럭 · 굴삭기)를 추적 번호로 짝지어 본다.
  추적 번호가 없는 박스(추적을 끈 경우, 막 잡힌 물체)는 판정하지 않는다.
- 거리는 카메라 보정 없이 화면에서 어림한다: 작업자 키(약 PERSON_HEIGHT_M)를 자로 삼아
  작업자 발밑(박스 아래 가운데)에서 장비 박스 아래쪽(GROUND_BAND, 땅에 닿는 부분)까지의 픽셀 거리를 미터로 바꾼다.
  카메라에서 멀어지는 방향(깊이)은 화면에서 줄어 보이므로 실제보다 가깝게 나올 수 있다.
- 작업자 박스가 장비 박스 안에 거의 들어 있고 발밑이 장비 아래쪽보다 위면 장비에 탄 사람(운전석)으로 보고 뺀다.
- 같은 작업자 · 장비 짝이 PROXIMITY_M 안에 PROXIMITY_HOLD_SEC 초 넘게 있으면 경보 한 번.
  잠깐 끊겨도 GAP_SEC 까지는 이어진 것으로 보고, 멀어졌다 다시 오면 다시 (같은 카메라 경보는 쿨다운 동안 막힘).
- 판정 기준(8-8)의 장비 근접 값을 쓴다: 작업자 · 장비 모두 추적하는 동안 한 번이라도 confidence 가 기준 이상이어야 센다.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from math import hypot

from . import vision
from .config import settings
from .schemas import EventIn

log = logging.getLogger("uvicorn.error")

PROXIMITY = "EQUIPMENT_PROXIMITY"
PERSON_HEIGHT_M = 1.7
GROUND_BAND = 0.5   # 장비 박스 아래쪽 이만큼(높이 비율)을 땅에 닿는 부분으로 본다
ONBOARD_INSIDE = 0.8  # 작업자 박스가 장비 박스 안에 이만큼 넘게 들어 있고
ONBOARD_ABOVE = 0.2   # 발밑이 장비 아래 끝에서 장비 높이의 이만큼보다 위면 장비에 탄 사람
GAP_SEC = 2.0
FORGET_SEC = 60.0   # 이만큼 안 보인 추적 번호는 잊는다


def equipment_classes() -> set[str]:
    return {c.strip() for c in settings.proximity_classes.split(",") if c.strip()}


def _inside_ratio(a: vision.Box, b: vision.Box) -> float:
    """a 박스 넓이 중 b 박스 안에 든 비율"""
    ix = max(0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0, min(a.y2, b.y2) - max(a.y1, b.y1))
    area = (a.x2 - a.x1) * (a.y2 - a.y1)
    return ix * iy / area if area > 0 else 0.0


def distance_m(person: vision.Box, equip: vision.Box) -> float | None:
    """작업자 발밑에서 장비까지 거리(m) 어림. 장비에 탄 사람이거나 박스가 이상하면 None"""
    ph, eh = person.y2 - person.y1, equip.y2 - equip.y1
    if ph <= 0 or eh <= 0:
        return None
    fx, fy = (person.x1 + person.x2) / 2, person.y2
    if _inside_ratio(person, equip) >= ONBOARD_INSIDE and fy < equip.y2 - ONBOARD_ABOVE * eh:
        return None
    dx = max(equip.x1 - fx, 0.0, fx - equip.x2)
    dy = max(equip.y2 - GROUND_BAND * eh - fy, 0.0, fy - equip.y2)
    return hypot(dx, dy) / ph * PERSON_HEIGHT_M


@dataclass
class Near:
    since: float
    last_seen: float
    fired: bool = False


@dataclass(frozen=True)
class Trigger:
    camera_id: int
    person: vision.Box
    equip: vision.Box
    meters: float
    conf: float  # 두 물체가 추적 동안 받은 가장 높은 confidence 중 낮은 쪽

    @property
    def bbox(self) -> list[int]:
        p, e = self.person, self.equip
        return [min(p.x1, e.x1), min(p.y1, e.y1), max(p.x2, e.x2), max(p.y2, e.y2)]


class Judge:
    """카메라마다 '어느 작업자가 어느 장비 곁에 언제부터 있는지'를 추적 번호로 기억한다. 탐지 스레드 하나에서만 부른다."""

    def __init__(self):
        self.pairs: dict[tuple[int, int, int], Near] = {}  # (카메라, 작업자 번호, 장비 번호)
        self.best: dict[tuple[int, int], float] = {}       # (카메라, 추적 번호) → 지금까지 가장 높은 confidence
        self.seen: dict[tuple[int, int], float] = {}

    def observe(self, camera_id: int, boxes: list[vision.Box], min_conf: float, now: float, *,
                classes: set[str] | None = None, limit_m: float | None = None,
                hold_sec: float | None = None) -> list[Trigger]:
        classes = equipment_classes() if classes is None else classes
        limit_m = settings.proximity_m if limit_m is None else limit_m
        hold_sec = settings.proximity_hold_sec if hold_sec is None else hold_sec

        tracked = [b for b in boxes if b.track_id is not None]
        for b in tracked:
            key = (camera_id, b.track_id)
            self.best[key] = max(self.best.get(key, 0.0), b.conf)
            self.seen[key] = now
        sure = [b for b in tracked if self.best[(camera_id, b.track_id)] >= min_conf]
        people = [b for b in sure if b.name == "person"]
        equips = [b for b in sure if b.name in classes]

        out = []
        for p in people:
            for e in equips:
                meters = distance_m(p, e)
                if meters is None or meters > limit_m:
                    continue
                key = (camera_id, p.track_id, e.track_id)
                near = self.pairs.get(key)
                if near is None or now - near.last_seen > GAP_SEC:
                    near = self.pairs[key] = Near(since=now, last_seen=now)
                near.last_seen = now
                if not near.fired and now - near.since >= hold_sec:
                    near.fired = True
                    conf = min(self.best[(camera_id, p.track_id)], self.best[(camera_id, e.track_id)])
                    out.append(Trigger(camera_id, p, e, meters, conf))
        for key in [k for k, n in self.pairs.items() if k[0] == camera_id and now - n.last_seen > GAP_SEC]:
            del self.pairs[key]
        for key in [k for k, t in self.seen.items() if k[0] == camera_id and now - t > FORGET_SEC]:
            del self.seen[key], self.best[key]
        return out


# ---------------------------------------------------------------- 이벤트 · 스냅샷 기록
@dataclass
class Job:
    trigger: Trigger
    camera_name: str
    snap: vision.Snapshot
    rois: list
    at: datetime = field(default_factory=datetime.now)


def save_snapshot(job: Job) -> str | None:
    """그 순간 화면에 작업자 ↔ 장비 선을 더 그려 저장한다"""
    from .zone_events import write_snapshot

    t = job.trigger
    jpeg = vision.render(job.snap, job.rois, True, links=[(t.person, t.equip, t.meters)])
    return write_snapshot(jpeg, job.camera_name, PROXIMITY, job.at)


def record(Session, job: Job):
    """판정 기준 · 쿨다운을 적용해 이벤트를 만든다 (ROI 와 상관없이 카메라 단위). 결과는 EventIngestOut"""
    from .routers.events import create_event

    t = job.trigger
    with Session() as db:
        body = EventIn(detection_type=PROXIMITY, camera_id=t.camera_id, confidence=round(t.conf, 3),
                       bbox=t.bbox, detected_at=job.at)
        result = create_event(db, body, lambda: save_snapshot(job))
    if result.created:
        log.info("이벤트 EV-%s: %s 장비 근접 %s#%s ↔ 사람#%s %.1fm", result.event_id, job.camera_name,
                 vision.NAMES_KO.get(t.equip.name, t.equip.name), t.equip.track_id, t.person.track_id, t.meters)
    return result


judge = Judge()
