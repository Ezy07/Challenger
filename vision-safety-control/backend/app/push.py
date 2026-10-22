"""웹 푸시 (Web Push): 이벤트가 새로 생기면 알림을 켠 기기(휴대폰 · PC 브라우저)로 보낸다.

- 기기에서 알림을 켜면 서비스 워커(frontend/sw.js)가 브라우저 푸시 서비스에 구독하고, 그 주소를
  PUT /api/push/subscriptions 로 저장한다 (push_subscription, 기기마다 한 줄).
- create_event 가 이벤트를 새로 만들면 notify_event → 기기마다 받을 심각도(min_severity) 이상이면 보낸다.
  쿨다운 · 작업 허가 대기로 이벤트를 만들지 않은 경우는 보내지 않으므로 같은 경보가 쌓이지 않는다.
- 보내기는 구글 · 애플 · 모질라 푸시 서비스로 나가는 HTTPS 요청이라 따로 스레드에서 한다 (탐지 · API 가 기다리지 않게).
  우리 서버가 바깥에서 접속될 필요는 없다. 기기가 알림을 켜고 알림을 눌러 화면을 열 때만 우리 서버에 닿으면 된다.
- 푸시 서비스가 404 · 410 을 주면 그 기기는 알림을 끈 것이라 지운다.
- 서명 키(VAPID)는 처음 쓸 때 PUSH_KEY_FILE 에 만든다.
"""

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .models import Event, PushSubscription, Role, Severity, User, UserStatus

log = logging.getLogger("uvicorn.error")

RANK = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}  # 작을수록 심각
SEVERITY_KO = {Severity.HIGH: "높음", Severity.MEDIUM: "중간", Severity.LOW: "낮음"}
TTL_SEC = 60 * 60  # 기기가 꺼져 있으면 푸시 서비스가 이만큼 들고 있다가 켜질 때 전한다 (그 뒤엔 버림)
GONE = (404, 410)  # 기기가 알림을 끄거나 앱을 지움 → 구독을 지운다

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="push")
_lock = threading.Lock()
_vapid = None


def vapid():
    """서명 키 (py_vapid.Vapid02). 파일이 없으면 만든다. pywebpush 가 설치되지 않았으면 None"""
    global _vapid
    with _lock:
        if _vapid is None:
            try:
                from py_vapid import Vapid02
            except ImportError:
                return None
            path = settings.push_key_file
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                key = Vapid02()
                key.generate_keys()
                key.save_key(str(path))
                log.info("웹 푸시 서명 키를 만들었습니다: %s", path)
            _vapid = Vapid02.from_file(str(path))
        return _vapid


def unavailable() -> str | None:
    """웹 푸시를 못 쓰는 이유 (쓸 수 있으면 None)"""
    if not settings.push_enabled:
        return "서버 설정에서 웹 푸시를 껐습니다 (PUSH_ENABLED=false)."
    if vapid() is None:
        return "서버에 pywebpush 가 설치되지 않았습니다 (pip install -r requirements.txt)."
    return None


def public_key() -> str:
    """브라우저가 구독할 때 쓰는 공개키 (applicationServerKey, base64url)"""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from py_vapid.utils import b64urlencode

    return b64urlencode(vapid().public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint))


def event_payload(event: Event, role: Role) -> dict:
    """알림 한 건 (서비스 워커 sw.js 가 그대로 띄운다). 누르면 그 카메라의 카메라 상세(지금 영상)로 간다.
    카메라가 없는 경보(TC 후크 겹침 · 기상 등)는 처리할 수 있는 사람은 처리 화면, 아니면 이벤트 상세"""
    where = " · ".join(x for x in (event.camera and event.camera.name, event.roi and event.roi.name) if x) or "카메라 없음"
    if event.camera_id is not None:
        url = f"/monitor-camera.html?camera={event.camera_id}"
    else:
        url = f"/{'event-handle' if role in (Role.ADMIN, Role.MANAGER) else 'event-detail'}.html?id={event.id}"
    snap = event.snapshots[0].image_path if event.snapshots else None
    return {
        "title": f"[{SEVERITY_KO[event.severity]}] {event.detection_type.label}",
        "body": f"{where} · {event.detected_at:%H:%M:%S} · EV-{event.id}",
        "url": url,
        "tag": f"event-{event.id}",
        "image": f"/{snap}" if snap else None,
        "severity": event.severity.value,
    }


def notify_event(db: Session, event_id: int) -> int:
    """새 이벤트를 받을 기기로 보낸다 (보내기는 다른 스레드). 보낼 기기 수"""
    if unavailable():
        return 0
    event = db.scalar(select(Event).where(Event.id == event_id).options(
        selectinload(Event.camera), selectinload(Event.roi), selectinload(Event.detection_type), selectinload(Event.snapshots)))
    if event is None:
        return 0
    rows = db.execute(select(PushSubscription, User.role).join(User).where(User.status == UserStatus.ACTIVE)).all()
    jobs = [(sub.id, _info(sub), event_payload(event, role)) for sub, role in rows
            if RANK[event.severity] <= RANK[sub.min_severity]]
    if jobs:
        _dispatch(db.get_bind(), jobs)
    return len(jobs)


def send_test(db: Session, user_id: int) -> int:
    """이 사람의 기기 모두에 시험 알림 (받을 심각도와 상관없이). 보낼 기기 수"""
    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all()
    payload = {"title": "🔔 테스트 알림", "body": f"이 기기로 안전관제 알림이 옵니다 · {datetime.now():%H:%M:%S}",
               "url": "/monitor.html", "tag": "push-test", "image": None, "severity": Severity.LOW.value}
    jobs = [(sub.id, _info(sub), payload) for sub in subs]
    if jobs:
        _dispatch(db.get_bind(), jobs)
    return len(jobs)


def _info(sub: PushSubscription) -> dict:
    return {"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}}


def _dispatch(bind, jobs: list[tuple[int, dict, dict]]) -> None:
    _pool.submit(_send_all, bind, jobs)


def _send_all(bind, jobs: list[tuple[int, dict, dict]]) -> None:
    sent, gone = [], []
    for sub_id, info, payload in jobs:
        code = _deliver(info, payload)
        if code in GONE:
            gone.append(sub_id)
        elif 200 <= code < 300:
            sent.append(sub_id)
        else:
            log.warning("웹 푸시를 보내지 못했습니다 (기기 %s, 응답 %s)", sub_id, code or "없음")
    if not (sent or gone):
        return
    try:
        with Session(bind) as db:
            if gone:
                db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
            if sent:
                db.execute(update(PushSubscription).where(PushSubscription.id.in_(sent)).values(last_sent_at=datetime.now()))
            db.commit()
    except Exception:
        log.exception("웹 푸시 기록을 저장하지 못했습니다")


def _deliver(info: dict, payload: dict) -> int:
    """푸시 서비스에 한 건 보내고 응답 코드를 돌려준다 (연결 실패면 0)"""
    from pywebpush import WebPushException, webpush

    try:
        res = webpush(info, json.dumps(payload, ensure_ascii=False), vapid_private_key=vapid(),
                      vapid_claims={"sub": settings.push_subject}, ttl=TTL_SEC, timeout=10,
                      headers={"Urgency": "high" if payload["severity"] == Severity.HIGH.value else "normal"})
        return res.status_code
    except WebPushException as e:
        return e.response.status_code if e.response is not None else 0
    except Exception:
        log.exception("웹 푸시 연결 오류")
        return 0
