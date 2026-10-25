"""프로필 사진 올리기 · 지우기 · 보기 (회원 · 작업자). 저장 · 줄이기는 app/photos.py

- 회원 사진: 본인 또는 관리자가 바꾼다. 작업자 사진: 관리자 · 안전관리자가 바꾼다.
- 보기는 로그인한 누구나 (<img src> 는 헤더를 못 붙여서 ?token= 으로도 받는다).
"""

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from .. import photos
from ..deps import DB, CurrentUser, Manager, StreamUser
from ..models import Role, User, UserStatus, Worker
from ..schemas import PhotoOut

router = APIRouter(prefix="/api", tags=["프로필 사진"])


def get_user(db: DB, user_id: int) -> User:
    u = db.scalar(select(User).where(User.id == user_id, User.status != UserStatus.DELETED))
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 회원입니다.")
    return u


def get_worker(db: DB, worker_id: int) -> Worker:
    w = db.scalar(select(Worker).where(Worker.id == worker_id, Worker.is_active))
    if not w:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 작업자입니다.")
    return w


def can_edit_user(me: User, user_id: int) -> None:
    if me.id != user_id and me.role != Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "본인이나 관리자만 사진을 바꿀 수 있습니다.")


async def replace(db: DB, row, kind: str, request: Request) -> PhotoOut:
    data = await photos.read_upload(request)
    new = photos.save(kind, row.id, data)
    old, row.photo_path = row.photo_path, new
    db.commit()
    photos.remove(old)
    return PhotoOut(photo_url=photos.url_of(kind, row.id, new))


def clear(db: DB, row) -> None:
    old, row.photo_path = row.photo_path, None
    db.commit()
    photos.remove(old)


# ---------------------------------------------------------------- 회원
@router.get("/users/{user_id}/photo")
def user_photo(user_id: int, db: DB, _: StreamUser):
    return photos.respond(get_user(db, user_id).photo_path)


@router.put("/users/{user_id}/photo", response_model=PhotoOut)
async def upload_user_photo(user_id: int, request: Request, db: DB, me: CurrentUser):
    """본문 = 사진 파일 그대로 (JPG · PNG · WebP). 긴 변 640px JPEG 로 줄여 저장한다"""
    can_edit_user(me, user_id)
    return await replace(db, get_user(db, user_id), "users", request)


@router.delete("/users/{user_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_photo(user_id: int, db: DB, me: CurrentUser):
    can_edit_user(me, user_id)
    clear(db, get_user(db, user_id))


# ---------------------------------------------------------------- 작업자
@router.get("/workers/{worker_id}/photo")
def worker_photo(worker_id: int, db: DB, _: StreamUser):
    return photos.respond(get_worker(db, worker_id).photo_path)


@router.put("/workers/{worker_id}/photo", response_model=PhotoOut)
async def upload_worker_photo(worker_id: int, request: Request, db: DB, _: Manager):
    return await replace(db, get_worker(db, worker_id), "workers", request)


@router.delete("/workers/{worker_id}/photo", status_code=status.HTTP_204_NO_CONTENT)
def delete_worker_photo(worker_id: int, db: DB, _: Manager):
    clear(db, get_worker(db, worker_id))
