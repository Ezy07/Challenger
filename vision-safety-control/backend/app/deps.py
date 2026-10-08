from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import Role, User, UserStatus
from .security import decode_access_token

DB = Annotated[Session, Depends(get_db)]
bearer = HTTPBearer(auto_error=False)


def user_from_token(db: Session, token: str | None) -> User:
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if not user or user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")
    return user


def current_user(db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    return user_from_token(db, cred.credentials if cred else None)


def stream_user(db: DB, cred: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
                token: str | None = None) -> User:
    """<img> 로 여는 영상 주소는 헤더를 붙일 수 없어서 ?token= 으로 로그인 토큰을 받는다"""
    return user_from_token(db, cred.credentials if cred else token)


def require_roles(*roles: Role):
    def check(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "권한이 없습니다.")
        return user

    return check


CurrentUser = Annotated[User, Depends(current_user)]
StreamUser = Annotated[User, Depends(stream_user)]
Admin = Annotated[User, Depends(require_roles(Role.ADMIN))]
Manager = Annotated[User, Depends(require_roles(Role.ADMIN, Role.MANAGER))]  # 이벤트 처리 · 작업자 관리


def ingest_key(x_ingest_key: Annotated[str | None, Header()] = None) -> None:
    """AI 탐지 프로그램 전용 인증 (사람 로그인 대신 고정 키)"""
    if x_ingest_key != settings.ingest_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "잘못된 수집 키입니다.")
