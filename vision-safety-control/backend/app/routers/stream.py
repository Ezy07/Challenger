"""YOLO 탐지 영상 (MJPEG). 관제화면(1-1) · 단일 카메라 확대(1-2)가 <img src="/api/stream/번호.mjpg"> 로 연다.
나머지 화면은 지금처럼 원본 영상 파일(/videos/...)을 그대로 튼다."""

import asyncio
import time

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import ppe, signalman, vision
from ..config import settings
from ..deps import DB, CurrentUser, StreamUser
from .cameras import get_camera
from .videos import URL_PREFIX, video_path

router = APIRouter(prefix="/api/stream", tags=["탐지 영상"])


class StreamStatus(BaseModel):
    enabled: bool       # False 면 화면은 원본 영상을 튼다
    reason: str | None  # 못 쓰는 이유
    model: str | None
    imgsz: int              # 보통 카메라의 탐지 입력 크기
    fine_imgsz: int         # 정밀 탐지 카메라의 입력 크기
    fine_error: str | None  # 정밀 탐지 모델을 못 열었으면 그 이유 (그 카메라도 보통 크기로 탐지)


@router.get("/status", response_model=StreamStatus)
async def stream_status(db: DB, _: CurrentUser):
    # 처음 부르면 모델을 여느라 수십 초 걸린다. 그동안 로그인 확인에 쓴 DB 연결을 붙잡고 있으면,
    # 화면 여러 개가 동시에 기다릴 때 연결 풀(15개)이 바닥나 다른 API 가 모두 멈춘다 → 먼저 돌려준다
    db.close()
    ok, reason = await asyncio.to_thread(vision.status)
    return StreamStatus(enabled=ok, reason=reason, model=settings.yolo_model if ok else None, imgsz=settings.yolo_imgsz,
                        fine_imgsz=settings.yolo_fine_imgsz, fine_error=vision.detector.fine_error)


class PpeCount(BaseModel):
    checked: int  # 착용을 판정하는 작업자 (화면에서 충분히 크게 보이고 추적 중)
    helmet: int   # 그중 안전모를 쓴 사람
    vest: int     # 그중 조끼를 입은 사람


class PeopleNow(BaseModel):
    camera_id: int
    workers: int              # 지금 화면의 작업자 수 (2초 안에 본 사람)
    ppe: PpeCount | None      # PPE 모델 · 미착용 판정을 안 쓰면 None
    signalmen: int | None     # 지금 보이는 신호수(빨간 계열 조끼) 수. 신호수 미배치 판정을 안 쓰면 None


@router.get("/people", response_model=list[PeopleNow])
def people_now(_: CurrentUser):
    """지금 탐지 중인 카메라마다 작업자 수 · 안전모 · 조끼 착용 수 · 신호수 수 (관제화면 섹터 감지경보).
    탐지 중이 아닌 카메라(아무도 안 보고 이벤트 감시도 안 함)는 빠진다."""
    from ..zone_events import rules

    worn = vision.detector.ppe_ready and any(r.active for c, r in rules.items() if c in ppe.CODES)
    signal = vision.detector.ppe_ready and (r := rules.get(signalman.NO_SIGNALMAN)) is not None and r.active
    now = time.monotonic()
    out = []
    for feed in vision.live_feeds():
        if feed.latest is None:
            continue
        out.append(PeopleNow(camera_id=feed.camera_id, workers=feed.workers(now),
                             ppe=PpeCount(**ppe.summary(feed.camera_id, now)) if worn else None,
                             signalmen=signalman.count(feed.camera_id, now) if signal else None))
    return out


async def frames(feed: vision.Feed, camera_name: str, show_roi: bool, show_boxes: bool):
    seq = -1
    try:
        while not feed.stopped:
            snap = feed.latest
            if snap is None or snap.seq == seq:
                await asyncio.sleep(0.02)
                continue
            seq = snap.seq
            rois = vision.rois_at(vision.roi_rows(), camera_name, snap.video_time)
            jpeg = await asyncio.to_thread(vision.render, snap, rois, show_roi, show_boxes)
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n%s\r\n" % (len(jpeg), jpeg)
    finally:
        feed.leave()


def source_of(url: str) -> tuple[str, bool] | None:
    """카메라 stream_url → (OpenCV 가 열 주소, 영상 파일인지). 영상 폴더에 없는 파일이면 None"""
    if url.startswith(URL_PREFIX):
        path = video_path(url)
        if not path or not path.is_file():
            return None
        return str(path), True
    return url, False  # RTSP 등 실시간 주소


@router.get("/{camera_id}.mjpg")
async def stream(camera_id: int, db: DB, _: StreamUser, roi: bool = True, boxes: bool = True):
    """카메라 영상에 YOLO 탐지 박스와 ROI 를 그려 보낸다 (roi=false · boxes=false 면 그것만 뺀다. 탐지 · 판정은 그대로).
    주소에 ?token=로그인토큰"""
    cam = get_camera(db, camera_id)
    name, url, fine = cam.name, cam.stream_url, cam.fine_detect
    db.close()  # 영상은 오래 이어지므로 DB 연결을 먼저 돌려준다
    if not url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 카메라에는 영상 소스가 없습니다.")
    found = source_of(url)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "영상 폴더(storage/videos)에 없는 파일입니다.")
    source, is_file = found

    ok, reason = await asyncio.to_thread(vision.status)
    if not ok:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, reason)
    feed = vision.open_feed(camera_id, source, is_file, name, fine)
    return StreamingResponse(frames(feed, name, roi, boxes), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})
