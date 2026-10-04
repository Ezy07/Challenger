import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import selectinload

from ..deps import DB, CurrentUser, Manager, ingest_key
from ..models import (
    ActionType,
    AlertRule,
    Camera,
    DetectionType,
    Event,
    EventAction,
    EventSnapshot,
    EventStatus,
    ReleaseCheckItem,
    Roi,
    RoiRule,
    Severity,
    WorkZone,
)
from ..schemas import (
    ActionIn,
    ActionOut,
    CheckItemState,
    EventDetail,
    EventIn,
    EventIngestOut,
    EventPage,
    EventRow,
)

router = APIRouter(prefix="/api/events", tags=["이벤트"])

DEFAULT_RULE = AlertRule(min_confidence=0.5, default_severity=Severity.MEDIUM, cooldown_sec=60, is_active=True)
CLOSED = {EventStatus.DONE, EventStatus.FALSE}
SEVERITY_RANK = case({Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}, value=Event.severity)
STATUS_KO = {EventStatus.NEW: "미처리", EventStatus.ACK: "확인중", EventStatus.DONE: "처리완료", EventStatus.FALSE: "오탐"}
SEVERITY_KO = {Severity.HIGH: "높음", Severity.MEDIUM: "중간", Severity.LOW: "낮음"}


# ---------------------------------------------------------------- AI 탐지 → 이벤트 생성
@router.post("", response_model=EventIngestOut, dependencies=[Depends(ingest_key)])
def ingest(body: EventIn, db: DB):
    """AI 탐지 결과를 받아 규칙(ROI별 덮어쓰기 → 기본값)을 적용하고, 통과하면 이벤트를 만든다.
    사람이 아니라 탐지 프로그램이 부르므로 X-Ingest-Key 헤더로 인증한다."""
    dtype = db.scalar(select(DetectionType).where(DetectionType.code == body.detection_type))
    if not dtype:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"없는 감지 유형입니다: {body.detection_type}")
    if body.camera_id is not None and not db.get(Camera, body.camera_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 카메라입니다.")
    if body.roi_id is not None:
        roi = db.get(Roi, body.roi_id)
        if not roi or roi.camera_id != body.camera_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "이 카메라의 ROI 가 아닙니다.")

    rule = dtype.rule or DEFAULT_RULE
    if not rule.is_active:
        return EventIngestOut(created=False, reason="사용 안 함 (판정 기준 화면에서 꺼진 감지 유형)")
    override = None
    if body.roi_id is not None:
        override = db.scalar(
            select(RoiRule).where(RoiRule.roi_id == body.roi_id, RoiRule.detection_type_id == dtype.id)
        )
    min_conf = override.min_confidence if override and override.min_confidence is not None else rule.min_confidence
    severity = override.severity if override and override.severity else rule.default_severity

    if body.confidence is not None and body.confidence < float(min_conf):
        return EventIngestOut(created=False, reason=f"판정 기준 미달 ({body.confidence:.2f} < {float(min_conf):.2f})")

    detected_at = body.detected_at or datetime.now()
    recent = db.scalar(
        select(Event.id).where(
            Event.detection_type_id == dtype.id,
            Event.camera_id.is_not_distinct_from(body.camera_id),
            Event.roi_id.is_not_distinct_from(body.roi_id),
            Event.detected_at > detected_at - timedelta(seconds=rule.cooldown_sec),
            Event.detected_at <= detected_at,
        ).limit(1)
    )
    if recent:
        return EventIngestOut(created=False, reason=f"쿨다운 중 ({rule.cooldown_sec}초 안에 같은 경보 EV-{recent})")

    event = Event(
        camera_id=body.camera_id,
        roi_id=body.roi_id,
        detection_type_id=dtype.id,
        severity=severity,
        confidence=body.confidence,
        bbox=body.bbox,
        detected_at=detected_at,
    )
    if body.snapshot_path:
        event.snapshots.append(EventSnapshot(image_path=body.snapshot_path))
    db.add(event)
    db.commit()
    return EventIngestOut(created=True, event_id=event.id)


# ---------------------------------------------------------------- 목록 · 내보내기
@dataclass
class EventFilter:
    date_from: date | None = None
    date_to: date | None = None
    status: Annotated[list[EventStatus] | None, Query()] = None
    severity: Annotated[list[Severity] | None, Query()] = None
    detection_type: Annotated[list[str] | None, Query(description="detection_type.code")] = None
    work_zone_id: int | None = None
    camera_id: int | None = None
    sort: Literal["latest", "severity", "confidence"] = "latest"


Filter = Annotated[EventFilter, Depends()]

# ROI 가 있으면 ROI 의 구역, 없으면 카메라가 놓인 구역
ZONE_ID = func.coalesce(Roi.work_zone_id, Camera.work_zone_id)


def filtered(f: EventFilter) -> Select:
    q = (
        select(Event, Camera.name, WorkZone.name, DetectionType.code, DetectionType.label)
        .join(DetectionType, Event.detection_type_id == DetectionType.id)
        .outerjoin(Camera, Event.camera_id == Camera.id)
        .outerjoin(Roi, Event.roi_id == Roi.id)
        .outerjoin(WorkZone, WorkZone.id == ZONE_ID)
    )
    if f.date_from:
        q = q.where(Event.detected_at >= datetime.combine(f.date_from, time.min))
    if f.date_to:
        q = q.where(Event.detected_at < datetime.combine(f.date_to + timedelta(days=1), time.min))
    if f.status:
        q = q.where(Event.status.in_(f.status))
    if f.severity:
        q = q.where(Event.severity.in_(f.severity))
    if f.detection_type:
        q = q.where(DetectionType.code.in_(f.detection_type))
    if f.work_zone_id is not None:
        q = q.where(ZONE_ID == f.work_zone_id)
    if f.camera_id is not None:
        q = q.where(Event.camera_id == f.camera_id)
    order = {
        "latest": [Event.detected_at.desc()],
        "severity": [SEVERITY_RANK, Event.detected_at.desc()],
        "confidence": [Event.confidence.desc(), Event.detected_at.desc()],
    }[f.sort]
    return q.order_by(*order, Event.id.desc())


def to_row(event: Event, camera_name, zone_name, code, label) -> EventRow:
    return EventRow(
        id=event.id,
        detected_at=event.detected_at,
        camera_name=camera_name,
        work_zone_name=zone_name,
        detection_code=code,
        detection_label=label,
        severity=event.severity,
        confidence=float(event.confidence) if event.confidence is not None else None,
        status=event.status,
    )


@router.get("", response_model=EventPage)
def list_events(
    db: DB,
    _: CurrentUser,
    f: Filter,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=200)] = 20,
):
    q = filtered(f)
    total = db.scalar(select(func.count()).select_from(q.order_by(None).subquery()))
    rows = db.execute(q.limit(size).offset((page - 1) * size)).all()
    return EventPage(total=total, page=page, size=size, items=[to_row(*r) for r in rows])


@router.get("/export.csv")
def export_csv(db: DB, _: CurrentUser, f: Filter):
    """이벤트 목록의 [CSV 내보내기]. 엑셀에서 한글이 깨지지 않게 BOM 을 붙인다."""
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf)
    w.writerow(["번호", "시각", "카메라", "구역", "종류", "심각도", "신뢰도", "처리 상태"])
    for r in db.execute(filtered(f)).all():
        row = to_row(*r)
        w.writerow([
            f"EV-{row.id}",
            row.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
            row.camera_name or "-",
            row.work_zone_name or "-",
            row.detection_label,
            SEVERITY_KO[row.severity],
            f"{row.confidence:.0%}" if row.confidence is not None else "-",
            STATUS_KO[row.status],
        ])
    filename = f"events_{datetime.now():%Y%m%d_%H%M}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------- 상세 · 처리
def load_event(db: DB, event_id: int) -> Event:
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id)
        .options(
            selectinload(Event.detection_type).selectinload(DetectionType.check_items),
            selectinload(Event.actions).selectinload(EventAction.user),
            selectinload(Event.snapshots),
            selectinload(Event.camera).selectinload(Camera.work_zone),
            selectinload(Event.roi).selectinload(Roi.work_zone),
        )
    )
    if not event:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 이벤트입니다.")
    return event


def permitted_items(event: Event) -> set[int]:
    """항목마다 마지막 PERMIT / REVOKE 를 보고 지금 허가된 항목을 구한다"""
    state: dict[int, bool] = {}
    for a in event.actions:
        if a.action_type in (ActionType.PERMIT, ActionType.REVOKE):
            state[a.check_item_id] = a.action_type == ActionType.PERMIT
    return {item_id for item_id, ok in state.items() if ok}


def to_detail(event: Event) -> EventDetail:
    zone = (event.roi and event.roi.work_zone) or (event.camera and event.camera.work_zone)
    row = to_row(
        event,
        event.camera.name if event.camera else None,
        zone.name if zone else None,
        event.detection_type.code,
        event.detection_type.label,
    )
    done = permitted_items(event)
    return EventDetail(
        **row.model_dump(),
        camera_id=event.camera_id,
        work_zone_id=zone.id if zone else None,
        roi_id=event.roi_id,
        roi_name=event.roi.name if event.roi else None,
        bbox=event.bbox,
        snapshots=[s.image_path for s in event.snapshots],
        check_items=[
            CheckItemState(id=i.id, title=i.title, permitted=i.id in done) for i in event.detection_type.check_items
        ],
        actions=[
            ActionOut(
                id=a.id,
                action_type=a.action_type,
                check_item_id=a.check_item_id,
                memo=a.memo,
                user_name=a.user.name,
                created_at=a.created_at,
            )
            for a in event.actions
        ],
    )


@router.get("/{event_id}", response_model=EventDetail)
def read_event(event_id: int, db: DB, _: CurrentUser):
    return to_detail(load_event(db, event_id))


@router.post("/{event_id}/actions", response_model=EventDetail, status_code=status.HTTP_201_CREATED)
def add_action(event_id: int, body: ActionIn, db: DB, user: Manager):
    """처리 기록 남기기. 흐름: 확인(ACK) → 해제 항목 하나씩 허가(PERMIT) → 모두 허가되면 처리완료(RESOLVE)"""
    event = load_event(db, event_id)
    kind = body.action_type

    if event.status in CLOSED and kind != ActionType.NOTE:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 끝난 이벤트에는 메모만 남길 수 있습니다.")

    item_ids = {i.id for i in event.detection_type.check_items}
    done = permitted_items(event)
    if kind in (ActionType.PERMIT, ActionType.REVOKE):
        if body.check_item_id not in item_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "이 이벤트 종류의 해제 항목이 아닙니다.")
        if kind == ActionType.PERMIT and body.check_item_id in done:
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 허가한 항목입니다.")
        if kind == ActionType.REVOKE and body.check_item_id not in done:
            raise HTTPException(status.HTTP_409_CONFLICT, "허가되지 않은 항목입니다.")
    elif body.check_item_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "해제 항목은 허가 · 허가 취소에만 씁니다.")

    if kind == ActionType.RESOLVE:
        missing = [i.title for i in event.detection_type.check_items if i.id not in done]
        if missing:
            raise HTTPException(status.HTTP_409_CONFLICT, f"아직 허가하지 않은 항목이 있습니다: {', '.join(missing)}")
        event.status = EventStatus.DONE
    elif kind == ActionType.FALSE_ALARM:
        event.status = EventStatus.FALSE
    elif kind != ActionType.NOTE and event.status == EventStatus.NEW:
        event.status = EventStatus.ACK  # 확인 · 재알림 · 허가는 모두 '확인중'으로 넘어감

    event.actions.append(
        EventAction(user_id=user.id, action_type=kind, check_item_id=body.check_item_id, memo=body.memo)
    )
    db.commit()
    db.expire_all()
    return to_detail(load_event(db, event_id))
