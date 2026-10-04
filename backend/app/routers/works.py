from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..deps import DB, CurrentUser, Manager
from ..models import Role, User, UserStatus, Work, WorkAssignment, Worker, WorkStatus, WorkZone
from ..schemas import AssignedWorker, AssignIn, WorkDetail, WorkIn, WorkOut, WorkUpdate
from ..today import special_tags, today_works, work_active_on, worker_load, worker_out

router = APIRouter(prefix="/api/works", tags=["작업 · 배정"])


def load_options():
    return (
        selectinload(Work.work_zone),
        selectinload(Work.manager),
        selectinload(Work.assignments).selectinload(WorkAssignment.worker).options(*worker_load()),
    )


def get_work(db: DB, work_id: int) -> Work:
    work = db.scalar(select(Work).where(Work.id == work_id).options(*load_options()))
    if not work:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 작업입니다.")
    return work


def active_assignments(work: Work) -> list[WorkAssignment]:
    return [a for a in work.assignments if a.worker.is_active]


def to_out(work: Work, day: date) -> WorkOut:
    people = active_assignments(work)
    return WorkOut(
        id=work.id,
        name=work.name,
        work_zone_id=work.work_zone_id,
        work_zone_name=work.work_zone.name,
        manager_id=work.manager_id,
        manager_name=f"{work.manager.name} {work.manager.position or ''}".strip() if work.manager else None,
        start_date=work.start_date,
        end_date=work.end_date,
        status=work.status,
        description=work.description,
        worker_count=len(people),
        special_count=sum(1 for a in people if special_tags(a.worker, day)),
    )


def to_detail(db: DB, work: Work) -> WorkDetail:
    day = date.today()
    people = active_assignments(work)
    works = today_works(db, day, [a.worker_id for a in people])
    return WorkDetail(
        **to_out(work, day).model_dump(),
        workers=[
            AssignedWorker(**worker_out(a.worker, day, works).model_dump(), assigned_date=a.assigned_date)
            for a in sorted(people, key=lambda a: a.worker.name)
        ],
    )


def check(db: DB, work: Work) -> None:
    if not db.get(WorkZone, work.work_zone_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 작업구역입니다.")
    if work.manager_id is not None:
        manager = db.get(User, work.manager_id)
        if not manager or manager.status != UserStatus.ACTIVE or manager.role == Role.VIEWER:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "담당자는 활성 상태의 안전관리자 · 관리자여야 합니다.")
    if work.end_date and work.end_date < work.start_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "종료 예정일이 시작일보다 빠릅니다.")


@router.get("", response_model=list[WorkOut])
def list_works(
    db: DB,
    _: CurrentUser,
    on: Annotated[date | None, Query(description="그날 걸쳐 있는 작업만 (예: 오늘)")] = None,
    upcoming: Annotated[bool, Query(description="끝나지 않은 작업만 (진행 · 예정)")] = False,
    work_zone_id: int | None = None,
    status_: Annotated[list[WorkStatus] | None, Query(alias="status")] = None,
):
    q = select(Work).options(*load_options()).order_by(Work.start_date, Work.id)
    if on:
        q = q.where(work_active_on(on))
    if upcoming:
        q = q.where(func.coalesce(Work.end_date, Work.start_date) >= date.today(), Work.status != WorkStatus.DONE)
    if work_zone_id is not None:
        q = q.where(Work.work_zone_id == work_zone_id)
    if status_:
        q = q.where(Work.status.in_(status_))
    day = date.today()
    return [to_out(w, day) for w in db.scalars(q)]


@router.get("/{work_id}", response_model=WorkDetail)
def read_work(work_id: int, db: DB, _: CurrentUser):
    return to_detail(db, get_work(db, work_id))


@router.post("", response_model=WorkDetail, status_code=status.HTTP_201_CREATED)
def create_work(body: WorkIn, db: DB, _: Manager):
    work = Work(**body.model_dump())
    check(db, work)
    db.add(work)
    db.commit()
    db.expire_all()
    return to_detail(db, get_work(db, work.id))


@router.patch("/{work_id}", response_model=WorkDetail)
def update_work(work_id: int, body: WorkUpdate, db: DB, _: Manager):
    work = get_work(db, work_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(work, key, value)
    check(db, work)
    db.commit()
    db.expire_all()
    return to_detail(db, get_work(db, work_id))


@router.delete("/{work_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work(work_id: int, db: DB, _: Manager):
    work = get_work(db, work_id)
    if active_assignments(work):
        raise HTTPException(status.HTTP_409_CONFLICT, "작업을 삭제하려면 배정된 작업자를 먼저 빼야 합니다.")
    db.delete(work)
    db.commit()


@router.put("/{work_id}/workers", response_model=WorkDetail)
def assign_workers(work_id: int, body: AssignIn, db: DB, _: Manager):
    """배정 작업자를 보낸 목록으로 맞춘다. 새로 들어온 사람은 오늘 날짜로 배정한다."""
    work = get_work(db, work_id)
    wanted = list(dict.fromkeys(body.worker_ids))
    found = set(db.scalars(select(Worker.id).where(Worker.id.in_(wanted), Worker.is_active)))
    missing = [i for i in wanted if i not in found]
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"없는 작업자입니다: {missing}")
    current = {a.worker_id for a in work.assignments}
    work.assignments = [a for a in work.assignments if a.worker_id in wanted]
    today = date.today()
    for worker_id in wanted:
        if worker_id not in current:
            work.assignments.append(WorkAssignment(worker_id=worker_id, assigned_date=today))
    db.commit()
    db.expire_all()
    return to_detail(db, get_work(db, work_id))
