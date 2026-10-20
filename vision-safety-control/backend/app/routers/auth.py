from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..config import settings
from ..deps import DB, CurrentUser
from ..models import Organization, User, UserStatus
from ..schemas import LoginIn, ProfileUpdate, SignupIn, TokenOut, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["로그인 · 회원가입"])

BLOCKED = {
    UserStatus.PENDING: "관리자 승인을 기다리는 중입니다.",
    UserStatus.REJECTED: "가입 신청이 반려되었습니다. 관리자에게 문의하세요.",
    UserStatus.LOCKED: "계정이 잠겼습니다. 관리자에게 잠금 해제를 요청하세요.",
    UserStatus.DELETED: "삭제된 계정입니다.",
}
# 아이디 · 비밀번호 · 계정 상태 중 무엇이 틀렸는지 알려 주지 않는다 (아이디가 있는지 짐작 못 하게)
WRONG = f"아이디 또는 비밀번호가 맞지 않습니다. ({settings.max_failed_logins}번 틀리면 {settings.login_lock_minutes}분 동안 잠깁니다)"
DUMMY_HASH = hash_password("no-such-user")  # 없는 아이디도 bcrypt 한 번 돌려 응답 시간을 맞춘다


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
    """계정 상태(승인 대기 · 잠금 등)는 비밀번호가 맞을 때만 알려 준다.
    비밀번호를 여러 번 틀리면 잠시 잠그고, 시간이 지나면 저절로 풀린다 (남이 일부러 틀려도 영구히 잠기지 않게)."""
    user = db.scalar(select(User).where(User.login_id == body.login_id))
    if not user:
        verify_password(body.password, DUMMY_HASH)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG)
    now = datetime.now()
    locked = user.locked_until is not None and user.locked_until > now
    if not verify_password(body.password, user.password_hash):
        if not locked:  # 잠긴 동안 틀린 건 세지 않는다 (풀리자마자 다시 잠기지 않게)
            if user.locked_until is not None:  # 지난 잠금이 풀린 뒤 처음 틀림: 새로 센다
                user.failed_login_count, user.locked_until = 0, None
            user.failed_login_count += 1
            if user.failed_login_count >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG)
    if user.status in BLOCKED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, BLOCKED[user.status])
    if locked:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"비밀번호를 여러 번 틀려 {user.locked_until:%H:%M} 까지 로그인할 수 없습니다. 급하면 관리자에게 잠금 해제를 요청하세요.")
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now()
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: ProfileUpdate, db: DB, user: CurrentUser):
    """자기 계정의 이름 · 전화번호 · 비밀번호만 바꾼다."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "이름을 입력하세요.")
    user.name = name
    user.phone = body.phone.strip() if body.phone and body.phone.strip() else None
    if body.password:
        user.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(user)
    return user
