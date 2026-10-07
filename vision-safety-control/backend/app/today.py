"""작업자 · 작업 · 장비 화면이 같이 쓰는 '오늘 기준' 계산"""

from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, selectinload

from .models import EduType, SpecialReason, Work, WorkAssignment, Worker, WorkStatus, WorkerEducation
from .schemas import TodayWork, WorkerEducationOut, WorkerOut

NEW_WORKER_DAYS = 7  # 신규 투입은 투입 후 7일까지만 특별관리 사유로 본다
OPEN_WORK = (WorkStatus.PLANNED, WorkStatus.IN_PROGRESS, WorkStatus.STOPPED)


def work_active_on(day: date):
    """그날 걸쳐 있는 작업 (종료일이 비어 있으면 시작일 하루짜리)"""
    return and_(Work.start_date <= day, func.coalesce(Work.end_date, Work.start_date) >= day)


def age_on(birth: date | None, day: date) -> int | None:
    if not birth:
        return None
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def special_tags(w: Worker, day: date) -> list[str]:
    """지금 유효한 특별관리 사유를 화면용 글자로. 신규 투입은 7일이 지나면 자동으로 빠진다"""
    if not w.is_special_care:
        return []
    tags = []
    for reason in w.special_reasons or []:
        if reason == SpecialReason.ELDERLY:
            age = age_on(w.birth_date, day)
            tags.append(f"고령 {age}세" if age else "고령")
        elif reason == SpecialReason.HYPERTENSION:
            tags.append("고혈압")
        elif reason == SpecialReason.NEW:
            if not w.start_date:
                tags.append("신규 투입")
            elif 0 <= (day - w.start_date).days <= NEW_WORKER_DAYS:
                tags.append(f"신규 투입 · D+{(day - w.start_date).days}")
        elif reason == SpecialReason.ETC:
            tags.append("기타")
    return tags


def worker_load():
    """WorkerOut 을 만들 때 필요한 관계를 한 번에 불러오는 옵션"""
    return (
        selectinload(Worker.educations).selectinload(WorkerEducation.education),
        selectinload(Worker.special_user),
    )


def today_works(db: Session, day: date, worker_ids: list[int] | None = None) -> dict[int, TodayWork]:
    """작업자별 그날 배정된 작업 (여러 개면 먼저 시작한 것)"""
    q = (
        select(WorkAssignment.worker_id, Work)
        .join(Work, Work.id == WorkAssignment.work_id)
        .where(work_active_on(day), Work.status.in_(OPEN_WORK))
        .options(selectinload(Work.work_zone))
        .order_by(Work.start_date, Work.id)
    )
    if worker_ids is not None:
        q = q.where(WorkAssignment.worker_id.in_(worker_ids))
    found: dict[int, TodayWork] = {}
    for worker_id, work in db.execute(q):
        found.setdefault(worker_id, TodayWork(
            id=work.id, name=work.name, work_zone_id=work.work_zone_id, work_zone_name=work.work_zone.name,
        ))
    return found


def worker_out(w: Worker, day: date, works: dict[int, TodayWork]) -> WorkerOut:
    return WorkerOut(
        id=w.id,
        name=w.name,
        company=w.company,
        job_type=w.job_type,
        phone=w.phone,
        birth_date=w.birth_date,
        start_date=w.start_date,
        age=age_on(w.birth_date, day),
        is_special_care=w.is_special_care,
        special_reasons=w.special_reasons or [],
        special_tags=special_tags(w, day),
        special_memo=w.special_memo,
        special_since=w.special_since,
        special_by_name=w.special_user.name if w.special_user else None,
        general_edu=any(e.education.edu_type == EduType.GENERAL for e in w.educations),
        educations=[
            WorkerEducationOut(id=e.id, edu_id=e.edu_id, edu_type=e.education.edu_type,
                               name=e.education.name, completed_date=e.completed_date)
            for e in w.educations
        ],
        today_work=works.get(w.id),
    )
