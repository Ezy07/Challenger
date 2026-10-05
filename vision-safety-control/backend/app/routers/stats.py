"""통계 (요약 · 추이 · 리포트). DB 마다 날짜 함수가 달라서 기간 안 이벤트를 읽어 파이썬에서 센다."""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select

from ..deps import DB, CurrentUser
from ..models import ActionType, Camera, DetectionType, Event, EventAction, EventStatus, Roi, Severity, WorkZone

router = APIRouter(prefix="/api/stats", tags=["통계"])

ZONE_ID = func.coalesce(Roi.work_zone_id, Camera.work_zone_id)
CLOSING = (ActionType.RESOLVE, ActionType.FALSE_ALARM)  # 처리 끝 (처리 시간 계산 기준)
MAX_DAYS = 366


@dataclass
class Ev:
    id: int
    at: datetime
    code: str
    label: str
    zone_id: int | None
    zone: str | None
    camera: str | None
    severity: Severity
    status: EventStatus
    closed_at: datetime | None
    memo: str | None


class Count(BaseModel):
    key: str
    label: str
    count: int


class Totals(BaseModel):
    total: int
    high: int
    open: int                   # 미처리 + 확인중
    handled_rate: int | None    # (처리완료 + 오탐) / 전체, %
    avg_handle_min: float | None  # 감지 → 처리 끝까지 평균 (분)


class Summary(BaseModel):
    date_from: date
    date_to: date
    current: Totals
    previous: Totals            # 바로 앞 같은 길이 기간
    by_type: list[Count]
    by_zone: list[Count]
    by_hour: list[int]          # 0~23시
    daily: list[Count]          # key = 날짜


class HighEvent(BaseModel):
    id: int
    detected_at: datetime
    zone: str | None
    label: str
    status: EventStatus
    memo: str | None


class Report(Summary):
    high_events: list[HighEvent]


def day_range(start: date, end: date):
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def load(db: DB, start: date, end: date, *, codes: list[str] | None = None, zone_id: int | None = None,
         severity: list[Severity] | None = None) -> list[Ev]:
    lo, hi = day_range(start, end)
    closed = (
        select(EventAction.event_id, func.min(EventAction.created_at).label("at"))
        .where(EventAction.action_type.in_(CLOSING))
        .group_by(EventAction.event_id)
        .subquery()
    )
    q = (
        select(Event.id, Event.detected_at, DetectionType.code, DetectionType.label, ZONE_ID, WorkZone.name,
               Camera.name, Event.severity, Event.status, closed.c.at)
        .join(DetectionType, Event.detection_type_id == DetectionType.id)
        .outerjoin(Camera, Event.camera_id == Camera.id)
        .outerjoin(Roi, Event.roi_id == Roi.id)
        .outerjoin(WorkZone, WorkZone.id == ZONE_ID)
        .outerjoin(closed, closed.c.event_id == Event.id)
        .where(Event.detected_at >= lo, Event.detected_at < hi)
        .order_by(Event.detected_at)
    )
    if codes:
        q = q.where(DetectionType.code.in_(codes))
    if zone_id is not None:
        q = q.where(ZONE_ID == zone_id)
    if severity:
        q = q.where(Event.severity.in_(severity))
    return [Ev(*row, memo=None) for row in db.execute(q)]


def totals(evs: list[Ev]) -> Totals:
    closed = [e for e in evs if e.status in (EventStatus.DONE, EventStatus.FALSE)]
    minutes = [(e.closed_at - e.at).total_seconds() / 60 for e in closed if e.closed_at and e.closed_at >= e.at]
    return Totals(
        total=len(evs),
        high=sum(e.severity == Severity.HIGH for e in evs),
        open=sum(e.status in (EventStatus.NEW, EventStatus.ACK) for e in evs),
        handled_rate=round(len(closed) * 100 / len(evs)) if evs else None,
        avg_handle_min=round(sum(minutes) / len(minutes), 1) if minutes else None,
    )


def counts(keys, labels: dict) -> list[Count]:
    return [Count(key=str(k), label=labels[k], count=n) for k, n in Counter(keys).most_common()]


def daily(evs: list[Ev], start: date, end: date) -> list[Count]:
    c = Counter(e.at.date() for e in evs)
    days = (end - start).days + 1
    return [Count(key=str(d), label=f"{d:%m.%d}", count=c.get(d, 0)) for d in (start + timedelta(i) for i in range(days))]


def check_range(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "끝 날짜가 시작 날짜보다 빠릅니다.")
    if (end - start).days >= MAX_DAYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "기간은 1년까지만 볼 수 있습니다.")


def summarize(db: DB, start: date, end: date) -> tuple[Summary, list[Ev]]:
    check_range(start, end)
    evs = load(db, start, end)
    span = (end - start).days + 1
    prev = load(db, start - timedelta(days=span), start - timedelta(days=1))
    type_labels = {e.code: e.label for e in evs}
    zone_labels = {e.zone_id: e.zone or "구역 없음" for e in evs}
    hours = Counter(e.at.hour for e in evs)
    return Summary(
        date_from=start, date_to=end,
        current=totals(evs), previous=totals(prev),
        by_type=counts((e.code for e in evs), type_labels),
        by_zone=[Count(key=str(z) if z else "none", label=zone_labels[z], count=n)
                 for z, n in Counter(e.zone_id for e in evs).most_common()],
        by_hour=[hours.get(h, 0) for h in range(24)],
        daily=daily(evs, start, end),
    ), evs


@router.get("/summary", response_model=Summary)
def summary(db: DB, _: CurrentUser, date_from: date | None = None, date_to: date | None = None):
    """요약: 기간(기본 오늘)의 건수 · 높음 · 미처리 · 처리율 · 평균 처리 시간과 앞 기간 비교, 종류 · 구역 · 시간대별"""
    today = date.today()
    return summarize(db, date_from or today, date_to or date_from or today)[0]


@router.get("/trend")
def trend(
    db: DB,
    _: CurrentUser,
    days: Annotated[int, Query(ge=1, le=90, description="최근 며칠 (화면은 7 · 14 · 30)")] = 14,
    detection_type: Annotated[list[str] | None, Query()] = None,
    work_zone_id: int | None = None,
    severity: Annotated[list[Severity] | None, Query()] = None,
):
    """추이: 최근 N일 일별 건수와 그 기간의 시간대별 건수"""
    end = date.today()
    start = end - timedelta(days=days - 1)
    evs = load(db, start, end, codes=detection_type, zone_id=work_zone_id, severity=severity)
    per_day = daily(evs, start, end)
    last7 = [d.count for d in per_day[-7:]]
    hours = Counter(e.at.hour for e in evs)
    return {
        "date_from": start, "date_to": end, "total": len(evs),
        "avg_per_day": round(len(evs) / days, 1),
        "avg_last7": round(sum(last7) / len(last7), 1),
        "daily": per_day,
        "by_hour": [hours.get(h, 0) for h in range(24)],
    }


@router.get("/report", response_model=Report)
def report(db: DB, _: CurrentUser, date_from: date, date_to: date):
    """리포트: 요약 + 높음 이벤트 목록 (조치 메모 포함)"""
    s, evs = summarize(db, date_from, date_to)
    high = [e for e in evs if e.severity == Severity.HIGH]
    memos = {}
    if high:
        rows = db.execute(
            select(EventAction.event_id, EventAction.memo)
            .where(EventAction.event_id.in_([e.id for e in high]), EventAction.memo.is_not(None))
            .order_by(EventAction.id)
        )
        memos = {event_id: memo for event_id, memo in rows}  # 마지막 메모
    return Report(
        **s.model_dump(),
        high_events=[HighEvent(id=e.id, detected_at=e.at, zone=e.zone, label=e.label, status=e.status, memo=memos.get(e.id))
                     for e in sorted(high, key=lambda e: e.at, reverse=True)],
    )
