import secrets
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..deps import DB, Admin, CurrentUser
from ..models import Organization, PushSubscription, Role, User, UserStatus
from ..schemas import ApproveIn, PushDeviceBrief, StaffOut, TempPasswordOut, UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["회원 관리 (관리자)"])


def get_user(db: DB, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user or user.status == UserStatus.DELETED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 회원입니다.")
    return user


def check_org(db: DB, org_id: int | None) -> None:
    if org_id is not None and not db.get(Organization, org_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 조직입니다.")


def not_self(user: User, admin: User, what: str) -> None:
    if user.id == admin.id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"자기 자신의 {what}")


def temp_password() -> str:
    return secrets.token_urlsafe(9)  # 12자, 첫 로그인 후 바꾸도록 안내


@router.get("", response_model=list[UserOut])
def list_users(db: DB, _: Admin, status_: Annotated[UserStatus | None, Query(alias="status")] = None):
    """회원 목록. ?status=PENDING 이면 회원가입 승인 대기 목록. 삭제한 회원은 빼고 보여 준다."""
    q = select(User).order_by(User.created_at.desc(), User.id.desc())
    q = q.where(User.status == status_) if status_ else q.where(User.status != UserStatus.DELETED)
    users = db.scalars(q).all()
    # 누가 어떤 기기로 알림을 받는지 (관리자가 알림 공백을 보도록. 설정은 각자 🔔 팝업에서)
    devices: dict[int, list[PushDeviceBrief]] = {}
    for sub in db.scalars(select(PushSubscription).options(selectinload(PushSubscription.zones)).order_by(PushSubscription.id)):
        devices.setdefault(sub.user_id, []).append(PushDeviceBrief(
            min_severity=sub.min_severity, zone_names=[z.name for z in sub.zones], high_any_zone=sub.high_any_zone))
    out = []
    for u in users:
        row = UserOut.model_validate(u)
        row.push_devices = devices.get(u.id, [])
        out.append(row)
    return out


@router.get("/staff", response_model=list[StaffOut])
def list_staff(db: DB, _: CurrentUser):
    """작업 담당자 고르기: 활성 상태의 관리자 · 안전관리자 (관리자 화면이 아니어도 필요해서 따로 둠)"""
    return db.scalars(
        select(User).where(User.status == UserStatus.ACTIVE, User.role.in_([Role.ADMIN, Role.MANAGER])).order_by(User.name)
    ).all()


@router.post("", response_model=TempPasswordOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DB, admin: Admin):
    if db.scalar(select(User.id).where(User.login_id == body.login_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다.")
    check_org(db, body.org_id)
    pw = temp_password()
    user = User(
        **body.model_dump(), password_hash=hash_password(pw),
        status=UserStatus.ACTIVE, approved_by=admin.id, approved_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TempPasswordOut(user=UserOut.model_validate(user), temp_password=pw)


@router.get("/{user_id}", response_model=UserOut)
def read_user(user_id: int, db: DB, _: Admin):
    return get_user(db, user_id)


@router.post("/{user_id}/approve", response_model=UserOut)
def approve(user_id: int, db: DB, admin: Admin, body: ApproveIn | None = None):
    """승인. 신청한 역할보다 낮게(조회 전용) 줄 수 있고, 관리자 역할은 승인으로 줄 수 없다."""
    user = get_user(db, user_id)
    if user.status != UserStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인 대기 중인 회원이 아닙니다.")
    if body and body.role:
        user.role = body.role
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
    if "role" in data or "status" in data:
        not_self(user, admin, "역할 · 상태는 바꿀 수 없습니다.")
    if user.status in (UserStatus.PENDING, UserStatus.REJECTED) and "status" in data:
        raise HTTPException(status.HTTP_409_CONFLICT, "가입 신청은 회원가입 승인 화면에서 처리하세요.")
    check_org(db, data.get("org_id"))
    for key, value in data.items():
        setattr(user, key, value)
    if data.get("status") == UserStatus.ACTIVE:
        user.failed_login_count = 0  # 잠금 해제
        user.locked_until = None
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=TempPasswordOut)
def reset_password(user_id: int, db: DB, _: Admin):
    """임시 비밀번호를 만들어 한 번만 보여 준다. 잠긴 계정이면 잠금도 풀린다."""
    user = get_user(db, user_id)
    pw = temp_password()
    user.password_hash = hash_password(pw)
    user.failed_login_count = 0
    user.locked_until = None
    if user.status == UserStatus.LOCKED:
        user.status = UserStatus.ACTIVE
    db.commit()
    return TempPasswordOut(user=UserOut.model_validate(user), temp_password=pw)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: DB, admin: Admin):
    """삭제. 처리 기록에 이름이 남아야 하므로 행은 지우지 않고 DELETED 로 바꾼다."""
    user = get_user(db, user_id)
    not_self(user, admin, "계정은 삭제할 수 없습니다.")
    user.status = UserStatus.DELETED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
