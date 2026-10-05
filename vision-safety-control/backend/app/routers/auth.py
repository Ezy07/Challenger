from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import settings
from ..deps import DB, CurrentUser
from ..models import Organization, User, UserStatus
from ..schemas import LoginIn, SignupIn, TokenOut, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["로그인 · 회원가입"])

BLOCKED = {
    UserStatus.PENDING: "관리자 승인을 기다리는 중입니다.",
    UserStatus.REJECTED: "가입 신청이 반려되었습니다. 관리자에게 문의하세요.",
    UserStatus.LOCKED: "계정이 잠겼습니다. 관리자에게 잠금 해제를 요청하세요.",
    UserStatus.DELETED: "삭제된 계정입니다.",
}


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, db: DB):
    """가입 신청. 관리자가 승인하기 전(PENDING)에는 로그인할 수 없다."""
    if db.scalar(select(User.id).where(User.login_id == body.login_id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 사용 중인 아이디입니다.")
    if body.org_id is not None and not db.get(Organization, body.org_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 조직입니다.")
    user = User(**body.model_dump(exclude={"password"}), password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DB):
    user = db.scalar(select(User).where(User.login_id == body.login_id))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 맞지 않습니다.")
    if user.status in BLOCKED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, BLOCKED[user.status])
    if not verify_password(body.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.status = UserStatus.LOCKED
        db.commit()
        if user.status == UserStatus.LOCKED:
            raise HTTPException(status.HTTP_403_FORBIDDEN, BLOCKED[UserStatus.LOCKED])
        left = settings.max_failed_logins - user.failed_login_count
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"아이디 또는 비밀번호가 맞지 않습니다. ({left}번 더 틀리면 잠김)")
    user.failed_login_count = 0
    user.last_login_at = datetime.now()
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
