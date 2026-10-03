from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from ..deps import DB, Admin
from ..models import Organization, User, UserStatus
from ..schemas import UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["회원 관리 (관리자)"])


def get_user(db: DB, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 회원입니다.")
    return user


@router.get("", response_model=list[UserOut])
def list_users(db: DB, _: Admin, status_: Annotated[UserStatus | None, Query(alias="status")] = None):
    """회원 목록. ?status=PENDING 이면 회원가입 승인 대기 목록"""
    q = select(User).order_by(User.created_at.desc(), User.id.desc())
    if status_:
        q = q.where(User.status == status_)
    return db.scalars(q).all()


@router.get("/{user_id}", response_model=UserOut)
def read_user(user_id: int, db: DB, _: Admin):
    return get_user(db, user_id)


@router.post("/{user_id}/approve", response_model=UserOut)
def approve(user_id: int, db: DB, admin: Admin):
    user = get_user(db, user_id)
    if user.status != UserStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인 대기 중인 회원이 아닙니다.")
    user.status = UserStatus.ACTIVE
    user.approved_by = admin.id
    user.approved_at = datetime.now()
    db.commit()
    return user


@router.post("/{user_id}/reject", response_model=UserOut)
def reject(user_id: int, db: DB, _: Admin):
    user = get_user(db, user_id)
    if user.status != UserStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인 대기 중인 회원이 아닙니다.")
    user.status = UserStatus.REJECTED
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: DB, admin: Admin):
    """회원정보 수정 · 역할(권한) 변경 · 잠금/해제"""
    user = get_user(db, user_id)
    data = body.model_dump(exclude_unset=True)
    if user.id == admin.id and ("role" in data or "status" in data):
        raise HTTPException(status.HTTP_409_CONFLICT, "자기 자신의 역할 · 상태는 바꿀 수 없습니다.")
    if data.get("org_id") is not None and not db.get(Organization, data["org_id"]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 조직입니다.")
    for key, value in data.items():
        setattr(user, key, value)
    if data.get("status") == UserStatus.ACTIVE:
        user.failed_login_count = 0  # 잠금 해제
    db.commit()
    return user
