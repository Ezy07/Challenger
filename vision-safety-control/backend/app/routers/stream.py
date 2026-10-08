"""YOLO 탐지 영상 (MJPEG). 관제화면(1-1) · 단일 카메라 확대(1-2)가 <img src="/api/stream/번호.mjpg"> 로 연다.
나머지 화면은 지금처럼 원본 영상 파일(/videos/...)을 그대로 튼다."""

import asyncio

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import vision
from ..config import settings
from ..deps import DB, CurrentUser, StreamUser
from .cameras import get_camera
from .videos import URL_PREFIX, video_path

router = APIRouter(prefix="/api/stream", tags=["탐지 영상"])


class StreamStatus(BaseModel):
    enabled: bool       # False 면 화면은 원본 영상을 튼다
    reason: str | None  # 못 쓰는 이유
    model: str | None


@router.get("/status", response_model=StreamStatus)
async def stream_status(_: CurrentUser):
    ok, reason = await asyncio.to_thread(vision.status)
    return StreamStatus(enabled=ok, reason=reason, model=settings.yolo_model if ok else None)


async def frames(feed: vision.Feed, camera_name: str, show_roi: bool):
    seq = -1
    try:
        while not feed.stopped:
            snap = feed.latest
            if snap is None or snap.seq == seq:
                await asyncio.sleep(0.02)
                continue
            seq = snap.seq
            rois = vision.rois_at(vision.roi_rows(), camera_name, snap.video_time)
            jpeg = await asyncio.to_thread(vision.render, snap, rois, show_roi)
            if jpeg:
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n%s\r\n" % (len(jpeg), jpeg)
    finally:
        feed.leave()


@router.get("/{camera_id}.mjpg")
async def stream(camera_id: int, db: DB, _: StreamUser, roi: bool = True):
    """카메라 영상에 YOLO 탐지 박스와 ROI(roi=false 면 박스만)를 그려 보낸다. 주소에 ?token=로그인토큰"""
    cam = get_camera(db, camera_id)
    name, url = cam.name, cam.stream_url
    db.close()  # 영상은 오래 이어지므로 DB 연결을 먼저 돌려준다
    if not url:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "이 카메라에는 영상 소스가 없습니다.")
    if url.startswith(URL_PREFIX):
        path = video_path(url)
        if not path or not path.is_file():
            raise HTTPException(status.HTTP_404_NOT_FOUND, "영상 폴더(storage/videos)에 없는 파일입니다.")
        source, is_file = str(path), True
    else:
        source, is_file = url, False  # RTSP 등 실시간 주소

    ok, reason = await asyncio.to_thread(vision.status)
    if not ok:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, reason)
    feed = vision.open_feed(camera_id, source, is_file)
    return StreamingResponse(frames(feed, name, roi), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})
