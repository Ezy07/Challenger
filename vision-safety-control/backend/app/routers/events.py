from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import Select, case, extract, func, select
from sqlalchemy.orm import selectinload

from ..config import settings
from ..deps import DB, Admin, CurrentUser, Manager, ingest_key
from ..event_query import ZONE_ID, day_range, to_row
from ..exporting import COLUMNS, DEFAULT_COLUMNS, to_csv, to_xlsx, to_zip
from ..models import (
    ActionType,
    AlertRule,
    Camera,
    DetectionType,
    Event,
    EventAction,
    EventSnapshot,
    EventStatus,
    Roi,
    RoiRule,
    Severity,
    User,
    WorkZone,
)
from ..schemas import (
    ActionIn,
    ActionOut,
    CheckItemState,
    EventDeleteIn,
    EventDeleteOut,
    EventDetail,
    EventIn,
    EventIngestOut,
    EventPage,
)

router = APIRouter(prefix="/api/events", tags=["이벤트"])

DEFAULT_RULE = AlertRule(min_confidence=0.5, default_severity=Severity.MEDIUM, cooldown_sec=60, is_active=True)
FUTURE_SLACK = timedelta(minutes=5)  # AI 프로그램 PC 와 서버 시계가 이만큼은 달라도 받는다
CLOSED = {EventStatus.DONE, EventStatus.FALSE}
SEVERITY_RANK = case({Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}, value=Event.severity)
STATUS_KO = {EventStatus.NEW: "미처리", EventStatus.ACK: "확인중", EventStatus.DONE: "처리완료", EventStatus.FALSE: "오탐"}
SEVERITY_KO = {Severity.HIGH: "높음", Severity.MEDIUM: "중간", Severity.LOW: "낮음"}


# ---------------------------------------------------------------- AI 탐지 → 이벤트 생성
def create_event(db: DB, body: EventIn, snapshot: Callable[[], str | None] | None = None, *, cooldown_sec: int | None = None) -> EventIngestOut:
    """규칙(ROI별 덮어쓰기 → 판정 기준 화면의 기본값)을 적용하고, 통과하면 이벤트를 만든다.
    외부 탐지 프로그램(POST /api/events)과 서버 안의 YOLO 판정(zone_events)이 같이 쓴다.
    snapshot 은 규칙을 통과했을 때만 불러서 스냅샷 파일을 만들고 그 경로("snapshots/...")를 받는다.
    cooldown_sec 를 주면 판정 기준의 쿨다운 대신 그 초만 같은 경보를 건너뛴다."""
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

    now = datetime.now()
    detected_at = body.detected_at or now
    if detected_at > now + FUTURE_SLACK:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "감지 시각이 서버 시각보다 미래입니다. AI 프로그램 PC 시계를 확인하세요.")
    cool = rule.cooldown_sec if cooldown_sec is None else cooldown_sec
    recent = None
    if cool > 0:
        recent = db.scalar(
            select(Event.id).where(
                Event.detection_type_id == dtype.id,
                Event.camera_id.is_not_distinct_from(body.camera_id),
                Event.roi_id.is_not_distinct_from(body.roi_id),
                Event.detected_at > detected_at - timedelta(seconds=cool),
                Event.detected_at <= detected_at,
            ).limit(1)
        )
    if recent:
        return EventIngestOut(created=False, reason=f"쿨다운 중 ({cool}초 안에 같은 경보 EV-{recent})")

    event = Event(
        camera_id=body.camera_id,
        roi_id=body.roi_id,
        detection_type_id=dtype.id,
        severity=severity,
        confidence=body.confidence,
        bbox=body.bbox,
        detected_at=detected_at,
    )
    image_path = body.snapshot_path or (snapshot() if snapshot else None)
    if image_path:
        event.snapshots.append(EventSnapshot(image_path=image_path))
    db.add(event)
    db.commit()
    return EventIngestOut(created=True, event_id=event.id)


@router.post("", response_model=EventIngestOut, dependencies=[Depends(ingest_key)])
def ingest(body: EventIn, db: DB):
    """AI 탐지 결과를 받아 규칙을 적용하고, 통과하면 이벤트를 만든다.
    사람이 아니라 탐지 프로그램이 부르므로 X-Ingest-Key 헤더로 인증한다."""
    return create_event(db, body)


@router.post("/tc-hook", response_model=EventIngestOut)
def tc_hook_overlap(db: DB, _: CurrentUser):
    """관제 화면 TC 패널을 연 뒤 1~4호기 후크가 약 5초 뒤 겹칠 때. 어느 화면에서든 로그인한 브라우저가 만든다.
    같은 겹침이 창 여러 개에서 동시에 올라오는 것만 건너뛰고, 다음 쌍의 경보는 따로 남긴다."""
    return create_event(db, EventIn(detection_type="TC_HOOK_PROXIMITY", confidence=0.95), cooldown_sec=2)


@router.post("/wind-gust", response_model=EventIngestOut)
def wind_gust(db: DB, _: CurrentUser):
    """순간풍속 10m/s 경고가 뜰 때마다 이벤트 로그에 남긴다.
    창이 여러 개여도 같은 강풍은 한 줄이고, 다음 강풍은 다시 남긴다. 기상 경보 기본 쿨다운(30분)은 쓰지 않는다."""
    return create_event(db, EventIn(detection_type="WEATHER", confidence=1), cooldown_sec=10)


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
    hour: Annotated[int | None, Query(ge=0, le=23, description="그 시간대(시)에 감지된 것만 (추이 차트 시간대 막대)")] = None
    sort: Literal["latest", "severity", "confidence"] = "latest"


Filter = Annotated[EventFilter, Depends()]

# 이벤트의 첫 스냅샷 (스냅샷 조회 화면 · 내보내기용)
FIRST_SNAPSHOT = (
    select(func.min(EventSnapshot.image_path)).where(EventSnapshot.event_id == Event.id).correlate(Event).scalar_subquery()
)


def filtered(f: EventFilter) -> Select:
    q = (
        select(Event, Camera.name, WorkZone.name, DetectionType.code, DetectionType.label, FIRST_SNAPSHOT)
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
    if f.hour is not None:
        q = q.where(extract("hour", Event.detected_at) == f.hour)
    order = {
        "latest": [Event.detected_at.desc()],
        "severity": [SEVERITY_RANK, Event.detected_at.desc()],
        "confidence": [Event.confidence.desc(), Event.detected_at.desc()],
    }[f.sort]
    return q.order_by(*order, Event.id.desc())


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


ExportFormat = Literal["csv", "xlsx", "zip"]
MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


def pick_columns(columns: list[str] | None) -> list[str]:
    cols = [c for c in (columns or DEFAULT_COLUMNS) if c in COLUMNS]
    if not cols:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "넣을 항목을 하나 이상 고르세요.")
    return list(dict.fromkeys(cols))


def export_rows(db: DB, f: EventFilter, limit: int | None = None) -> tuple[list[dict], dict[int, str]]:
    """내보내기 줄 (화면에 보이는 한글 값). 처리 담당자 · 조치 메모는 마지막 처리 기록에서 가져온다"""
    q = filtered(f)
    if limit:
        q = q.limit(limit)
    found = db.execute(q).all()
    ids = [r[0].id for r in found]
    handler, memo = {}, {}
    if ids:
        acts = db.execute(
            select(EventAction.event_id, User.name, EventAction.memo)
            .join(User, EventAction.user_id == User.id)
            .where(EventAction.event_id.in_(ids))
            .order_by(EventAction.id)
        )
        for event_id, user_name, text in acts:
            handler[event_id] = user_name
            if text:
                memo[event_id] = text
    rows, snapshots = [], {}
    for r in found:
        row = to_row(*r)
        if row.snapshot:
            snapshots[row.id] = row.snapshot
        rows.append({
            "_event_id": row.id,
            "id": f"EV-{row.id}",
            "time": row.detected_at.strftime("%Y-%m-%d %H:%M:%S"),
            "camera": row.camera_name or "-",
            "zone": row.work_zone_name or "-",
            "type": row.detection_label,
            "severity": SEVERITY_KO[row.severity],
            "confidence": f"{row.confidence:.0%}" if row.confidence is not None else "-",
            "status": STATUS_KO[row.status],
            "handler": handler.get(row.id, "-"),
            "memo": memo.get(row.id, "-"),
            "snapshot": row.snapshot or "-",
        })
    return rows, snapshots


def snapshot_file(image_path: str):
    """event_snapshot.image_path ("snapshots/...") → 실제 파일 (스냅샷 폴더 밖은 막음)"""
    if not image_path.startswith("snapshots/"):
        return None
    path = (settings.snapshot_dir / image_path[len("snapshots/"):]).resolve()
    root = settings.snapshot_dir.resolve()
    return path if root in path.parents else None


def file_response(content: bytes, fmt: str) -> Response:
    name = f"events_{datetime.now():%Y%m%d_%H%M}.{fmt}"
    return Response(content, media_type=MEDIA[fmt], headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/export/preview")
def export_preview(db: DB, _: CurrentUser, f: Filter, columns: Annotated[list[str] | None, Query()] = None):
    """내보내기 화면의 미리보기: 조건에 맞는 건수와 앞 5줄"""
    cols = pick_columns(columns)
    total = db.scalar(select(func.count()).select_from(filtered(f).order_by(None).subquery()))
    rows, _ = export_rows(db, f, limit=5)
    return {
        "total": total,
        "columns": [{"key": c, "label": COLUMNS[c]} for c in cols],
        "rows": [[r[c] for c in cols] for r in rows],
    }


@router.get("/export")
def export(db: DB, _: CurrentUser, f: Filter, format: ExportFormat = "csv",
           columns: Annotated[list[str] | None, Query()] = None):
    """이벤트 내보내기: csv (분석용) · xlsx (보고용 서식) · zip (CSV + 이벤트별 탐지 이미지)"""
    cols = pick_columns(columns)
    rows, snaps = export_rows(db, f)
    if format == "xlsx":
        return file_response(to_xlsx(cols, rows, "이벤트 내보내기"), "xlsx")
    if format == "zip":
        files = {eid: p for eid, path in snaps.items() if (p := snapshot_file(path))}
        return file_response(to_zip(cols, rows, files), "zip")
    return file_response(to_csv(cols, rows), "csv")


@router.get("/export.csv")
def export_csv(db: DB, _: CurrentUser, f: Filter):
    """예전 주소 (기본 항목 CSV). 새 화면은 /api/events/export 를 쓴다"""
    rows, _ = export_rows(db, f)
    return file_response(to_csv(DEFAULT_COLUMNS, rows), "csv")


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


# ---------------------------------------------------------------- 삭제 (관리자 전용 · 3-1)
def delete_events(db: DB, events: list[Event]) -> EventDeleteOut:
    """처리 기록 · 스냅샷 행은 cascade 로 함께 지우고, 스냅샷 그림 파일도 지운다"""
    files = [snapshot_file(s.image_path) for e in events for s in e.snapshots]
    for e in events:
        db.delete(e)
    db.commit()
    for path in files:
        if path:
            path.unlink(missing_ok=True)
    return EventDeleteOut(deleted=len(events))


@router.post("/delete", response_model=EventDeleteOut)
def delete_selected(body: EventDeleteIn, db: DB, _: Admin):
    q = select(Event).where(Event.id.in_(body.ids)).options(selectinload(Event.snapshots), selectinload(Event.actions))
    return delete_events(db, list(db.scalars(q)))


@router.delete("/range", response_model=EventDeleteOut)
def delete_range(date_from: date, date_to: date, db: DB, _: Admin):
    """date_from ~ date_to (끝일 포함) 에 감지된 이벤트 전부. 실수로 전체 기간을 지우지 않게 두 날짜 모두 받는다"""
    if date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "시작일이 끝일보다 늦습니다.")
    lo, hi = day_range(date_from, date_to)
    q = (
        select(Event)
        .where(Event.detected_at >= lo, Event.detected_at < hi)
        .options(selectinload(Event.snapshots), selectinload(Event.actions))
    )
    return delete_events(db, list(db.scalars(q)))
