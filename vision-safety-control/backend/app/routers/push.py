"""웹 푸시: 이 기기에서 알림 켜기 · 끄기 · 시험 보내기 (보내는 일은 app/push.py)"""

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, status
from sqlalchemy import delete, select

from .. import push
from ..deps import DB, CurrentUser
from ..models import PushSubscription
from ..schemas import PushKeyOut, PushSubIn, PushSubOut, PushTestOut

router = APIRouter(prefix="/api/push", tags=["웹 푸시"])


def _need_push() -> None:
    reason = push.unavailable()
    if reason:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, reason)


@router.get("/key", response_model=PushKeyOut)
def key(_: CurrentUser):
    """브라우저가 구독할 때 쓰는 공개키. 못 쓰면 enabled=false 와 이유"""
    reason = push.unavailable()
    return PushKeyOut(enabled=reason is None, public_key=None if reason else push.public_key(), reason=reason)


@router.get("/subscriptions", response_model=list[PushSubOut])
def my_devices(db: DB, user: CurrentUser):
    """내 계정으로 알림을 켠 기기"""
    return db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id).order_by(PushSubscription.id)).all()


@router.put("/subscriptions", response_model=PushSubOut)
def subscribe(body: PushSubIn, db: DB, user: CurrentUser, user_agent: Annotated[str | None, Header()] = None):
    """이 기기로 알림 받기 (같은 기기면 받을 심각도만 바꾼다). 다른 계정으로 켜 둔 기기면 지금 계정으로 옮긴다"""
    _need_push()
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        sub = PushSubscription(endpoint=body.endpoint)
        db.add(sub)
    sub.user_id = user.id
    sub.p256dh, sub.auth = body.keys.p256dh, body.keys.auth
    sub.min_severity = body.min_severity
    sub.device = (user_agent or "")[:255] or None
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(db: DB, user: CurrentUser, endpoint: Annotated[str, Query(max_length=700)]):
    """이 기기 알림 끄기 (내 계정의 기기만)"""
    db.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint, PushSubscription.user_id == user.id))
    db.commit()


@router.post("/test", response_model=PushTestOut)
def send_test(db: DB, user: CurrentUser):
    """내 기기 모두에 시험 알림 (받을 심각도와 상관없이)"""
    _need_push()
    devices = push.send_test(db, user.id)
    if not devices:
        raise HTTPException(status.HTTP_409_CONFLICT, "이 계정으로 알림을 켠 기기가 없습니다.")
    return PushTestOut(devices=devices)
