"""판정 모듈(zone_events · proximity · ppe · signalman)이 함께 쓰는 것.

- 추적 번호마다 지금까지 가장 높은 confidence (한 번이라도 기준을 넘은 물체만 세고, 넘은 뒤로는 잠깐 낮게 잡혀도 이어 본다)
- 장비에 탄 사람(운전석) 판별 · 오래 안 보인 기억 지우기
- 이벤트 · 스냅샷 기록 (기록 스레드에서 부른다)
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from . import vision
from .config import settings
from .schemas import EventIn

FORGET_SEC = 60.0     # 이만큼 안 보인 추적 번호는 잊는다
ONBOARD_INSIDE = 0.8  # 작업자 박스가 장비 박스 안에 이만큼 넘게 들어 있으면 장비에 탄 사람(운전석)


def class_set(text: str) -> set[str]:
    """설정 값 "truck,excavator" → {"truck", "excavator"}"""
    return {c.strip() for c in text.split(",") if c.strip()}


def bbox(b: vision.Box) -> list[int]:
    return [b.x1, b.y1, b.x2, b.y2]


def inside_ratio(a: vision.Box, b: vision.Box) -> float:
    """a 박스 넓이 중 b 박스 안에 든 비율"""
    ix = max(0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0, min(a.y2, b.y2) - max(a.y1, b.y1))
    area = (a.x2 - a.x1) * (a.y2 - a.y1)
    return ix * iy / area if area > 0 else 0.0


def onboard(person: vision.Box, equips: list[vision.Box]) -> bool:
    """작업자 박스가 장비 박스 안에 거의 들어 있음 (운전석 등 장비에 탄 사람)"""
    return any(inside_ratio(person, e) >= ONBOARD_INSIDE for e in equips)


def drop_stale(items: dict, camera_id: int, now: float, after: float) -> None:
    """(카메라, …) → .last_seen 이 있는 기억 중 이 카메라에서 after 초 넘게 안 본 것을 지운다"""
    for key in [k for k, v in items.items() if k[0] == camera_id and now - v.last_seen > after]:
        del items[key]


class BestConf:
    """카메라 · 추적 번호마다 지금까지 가장 높은 confidence. 탐지 스레드 하나에서만 부른다."""

    def __init__(self):
        self.best: dict[tuple[int, int], float] = {}
        self.seen: dict[tuple[int, int], float] = {}

    def see(self, camera_id: int, b: vision.Box, now: float) -> float:
        key = (camera_id, b.track_id)
        self.best[key] = max(self.best.get(key, 0.0), b.conf)
        self.seen[key] = now
        return self.best[key]

    def of(self, camera_id: int, b: vision.Box) -> float:
        return self.best[(camera_id, b.track_id)]

    def forget(self, camera_id: int, now: float) -> None:
        for key in [k for k, t in self.seen.items() if k[0] == camera_id and now - t > FORGET_SEC]:
            del self.seen[key], self.best[key]


# ---------------------------------------------------------------- 이벤트 · 스냅샷 기록
@dataclass
class Job:
    trigger: Any  # 각 모듈의 Trigger (camera_id 가 있음)
    camera_name: str
    snap: vision.Snapshot
    rois: list
    at: datetime = field(default_factory=datetime.now)


def write_snapshot(jpeg: bytes, camera_name: str, code: str, at: datetime) -> str | None:
    """JPEG 를 storage/snapshots/날짜/ 에 저장하고 "snapshots/..." 경로를 돌려준다."""
    if not jpeg:
        return None
    safe = re.sub(r"[^\w.-]", "_", camera_name)
    rel = f"{at:%Y%m%d}/{code.lower()}_{safe}_{at:%H%M%S}_{at.microsecond // 1000:03d}.jpg"
    path = settings.snapshot_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    return "snapshots/" + rel


def snapshot(job: Job, code: str, **draw) -> str | None:
    """그 순간 화면(ROI · 탐지 박스, draw 로 vision.render 의 links · marks 를 더 그림)을 저장한다"""
    return write_snapshot(vision.render(job.snap, job.rois, True, **draw), job.camera_name, code, job.at)


def create(Session, job: Job, code: str, conf: float, box: list[int], save: Callable[[], str | None],
           roi_id: Callable[[Any], int] | None = None):
    """판정 기준 · 쿨다운 · 작업 허가 대기를 적용해 이벤트를 만든다 (events.create_event).
    roi_id: db → 이벤트에 이을 ROI 번호 (없으면 카메라 단위). 결과는 EventIngestOut"""
    from .routers.events import create_event

    with Session() as db:
        body = EventIn(detection_type=code, camera_id=job.trigger.camera_id, roi_id=roi_id(db) if roi_id else None,
                       confidence=round(conf, 3), bbox=box, detected_at=job.at)
        return create_event(db, body, save)
