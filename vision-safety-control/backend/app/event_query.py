"""이벤트를 읽는 화면(이벤트 · 통계 · 구역 · 장비)이 같이 쓰는 기준"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func

from .models import Camera, Event, Roi
from .schemas import EventRow

# 이벤트의 구역: ROI 가 있으면 ROI 의 구역, 없으면 카메라가 놓인 구역
# (쿼리에 Camera · Roi 를 outerjoin 해야 쓸 수 있다)
ZONE_ID = func.coalesce(Roi.work_zone_id, Camera.work_zone_id)


def day_range(start: date, end: date | None = None) -> tuple[datetime, datetime]:
    """start 0시부터 end(없으면 start) 다음 날 0시 전까지 (detected_at >= lo, < hi 로 쓴다)"""
    return datetime.combine(start, time.min), datetime.combine((end or start) + timedelta(days=1), time.min)


def to_row(event: Event, camera_name, zone_name, code, label, snapshot=None) -> EventRow:
    """이벤트 목록 한 줄 (select(Event, Camera.name, WorkZone.name, DetectionType.code, DetectionType.label[, 스냅샷]))"""
    return EventRow(
        snapshot=snapshot,
        id=event.id,
        detected_at=event.detected_at,
        camera_id=event.camera_id,
        camera_name=camera_name,
        work_zone_name=zone_name,
        detection_code=code,
        detection_label=label,
        severity=event.severity,
        confidence=float(event.confidence) if event.confidence is not None else None,
        status=event.status,
    )
