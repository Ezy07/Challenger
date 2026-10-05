from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, or_, select, update

from ..deps import DB, CurrentUser, Manager
from ..models import Education, Equipment, Work, WorkAssignment, Worker, WorkerEducation, WorkStatus
from ..schemas import EducationOut, SpecialIn, WorkerEducationIn, WorkerIn, WorkerOut, WorkerUpdate
from ..today import today_works, worker_load, worker_out

router = APIRouter(prefix="/api", tags=["작업자 · 교육"])


def get_worker(db: DB, worker_id: int) -> Worker:
    w = db.scalar(select(Worker).where(Worker.id == worker_id, Worker.is_active).options(*worker_load()))
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 작업자입니다.")
    return w


def out(db: DB, w: Worker) -> WorkerOut:
    """저장 직후 응답: 세션에 남은 예전 값(교육 목록 등)을 버리고 다시 읽는다"""
    db.expire_all()
    w = get_worker(db, w.id)
    day = date.today()
    return worker_out(w, day, today_works(db, day, [w.id]))


@router.get("/workers", response_model=list[WorkerOut])
def list_workers(
    db: DB,
    _: CurrentUser,
    q: str | None = None,
    company: str | None = None,
    special: Annotated[bool | None, Query(description="true 면 지금 유효한 특별관리 대상만")] = None,
):
    query = select(Worker).where(Worker.is_active).options(*worker_load()).order_by(Worker.name)
    if q:
        query = query.where(or_(Worker.name.contains(q), Worker.job_type.contains(q)))
    if company:
        query = query.where(Worker.company == company)
    day = date.today()
    workers = db.scalars(query).all()
    works = today_works(db, day, [w.id for w in workers])
    rows = [worker_out(w, day, works) for w in workers]
    if special is not None:
        rows = [r for r in rows if bool(r.special_tags) == special]
    return rows


@router.get("/workers/{worker_id}", response_model=WorkerOut)
def read_worker(worker_id: int, db: DB, _: CurrentUser):
    w = get_worker(db, worker_id)
    day = date.today()
    return worker_out(w, day, today_works(db, day, [w.id]))


@router.post("/workers", response_model=WorkerOut, status_code=status.HTTP_201_CREATED)
def create_worker(body: WorkerIn, db: DB, _: Manager):
    w = Worker(**body.model_dump())
    db.add(w)
    db.commit()
    return out(db, w)


@router.patch("/workers/{worker_id}", response_model=WorkerOut)
def update_worker(worker_id: int, body: WorkerUpdate, db: DB, _: Manager):
    w = get_worker(db, worker_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(w, key, value)
    db.commit()
    return out(db, w)


@router.delete("/workers/{worker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_worker(worker_id: int, db: DB, _: Manager):
    """삭제: 끝나지 않은 작업 배정과 장비 운전원에서 빼고, 행은 이력 때문에 남긴다 (is_active = 0)"""
    w = get_worker(db, worker_id)
    open_works = select(Work.id).where(Work.status != WorkStatus.DONE)
    db.execute(delete(WorkAssignment).where(WorkAssignment.worker_id == w.id, WorkAssignment.work_id.in_(open_works)))
    db.execute(update(Equipment).where(Equipment.operator_id == w.id).values(operator_id=None))
    w.is_active = False
    db.commit()


# ---------------------------------------------------------------- 특별관리
@router.post("/workers/{worker_id}/special", response_model=WorkerOut)
def set_special(worker_id: int, body: SpecialIn, db: DB, user: Manager):
    """특별관리 지정 (이미 지정돼 있으면 사유 · 메모만 바꾼다)"""
    w = get_worker(db, worker_id)
    if not w.is_special_care:
        w.is_special_care = True
        w.special_since = date.today()
        w.special_by = user.id
    w.special_reasons = list(dict.fromkeys(body.reasons))  # 같은 사유 두 번 방지
    w.special_memo = body.memo
    db.commit()
    return out(db, w)


@router.delete("/workers/{worker_id}/special", response_model=WorkerOut)
def clear_special(worker_id: int, db: DB, _: Manager):
    w = get_worker(db, worker_id)
    w.is_special_care = False
    w.special_reasons = None
    w.special_memo = None
    w.special_since = None
    w.special_by = None
    db.commit()
    return out(db, w)


# ---------------------------------------------------------------- 안전교육
@router.get("/educations", response_model=list[EducationOut])
def list_educations(db: DB, _: CurrentUser):
    return db.scalars(select(Education).where(Education.is_active).order_by(Education.edu_type, Education.id)).all()


@router.post("/workers/{worker_id}/educations", response_model=WorkerOut, status_code=status.HTTP_201_CREATED)
def add_education(worker_id: int, body: WorkerEducationIn, db: DB, _: Manager):
    w = get_worker(db, worker_id)
    edu = db.get(Education, body.edu_id)
    if not edu or not edu.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 교육입니다.")
    if body.completed_date > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "이수일이 오늘보다 늦을 수 없습니다.")
    w.educations.append(WorkerEducation(edu_id=edu.id, completed_date=body.completed_date))
    db.commit()
    return out(db, w)


@router.delete("/workers/{worker_id}/educations/{history_id}", response_model=WorkerOut)
def delete_education(worker_id: int, history_id: int, db: DB, _: Manager):
    w = get_worker(db, worker_id)
    record = db.get(WorkerEducation, history_id)
    if not record or record.worker_id != w.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 이수 기록입니다.")
    db.delete(record)
    db.commit()
    return out(db, w)
