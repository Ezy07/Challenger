"""프로필 사진 (회원 · 작업자).

- 올린 그림은 정사각 크기 제한(MAX_SIDE) 안으로 줄여 JPEG 로 다시 저장한다. 휴대폰 사진의 촬영 위치(GPS) 같은
  EXIF 정보는 다시 저장하면서 지워진다. 회전 정보는 먼저 적용해 눕지 않게 한다.
- 파일은 storage/photos/{users|workers}/번호-시각.jpg. 얼굴 사진은 개인정보라 /plans 처럼 공개 폴더로 내려주지 않고,
  로그인한 사람만 GET /api/users/{번호}/photo 로 본다 (<img> 는 ?token= 으로).
"""

import io
import logging
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.responses import FileResponse

from .config import settings

log = logging.getLogger("uvicorn.error")

MAX_SIDE = 640  # 저장할 때 긴 변을 이만큼까지 줄인다 (목록 · 상세 · 크게 보기에 충분)
QUALITY = 85


async def read_upload(request: Request) -> bytes:
    """요청 본문 = 그림 파일 그대로 (도면 올리기와 같은 방식)"""
    limit = settings.max_photo_mb * 1024 * 1024
    too_big = HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"사진은 {settings.max_photo_mb}MB 까지 올릴 수 있습니다.")
    if int(request.headers.get("content-length") or 0) > limit:
        raise too_big
    data = await request.body()
    if len(data) > limit:
        raise too_big
    return data


def save(kind: str, owner_id: int, data: bytes) -> str:
    """그림을 줄여 저장하고 photo_path("users/3-....jpg")를 돌려준다. 그림이 아니면 415"""
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "JPG · PNG · WebP 사진만 올릴 수 있습니다.")
    folder = settings.photo_dir / kind
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{owner_id}-{datetime.now():%Y%m%d-%H%M%S-%f}.jpg"
    img.save(folder / name, "JPEG", quality=QUALITY, optimize=True)
    return f"{kind}/{name}"


def file_of(photo_path: str) -> Path:
    """DB 값 → 실제 파일 (폴더 밖을 가리키지 않게 이름만 쓴다)"""
    kind, _, name = photo_path.partition("/")
    return settings.photo_dir / Path(kind).name / Path(name).name


def remove(photo_path: str | None) -> None:
    if not photo_path:
        return
    try:
        file_of(photo_path).unlink(missing_ok=True)
    except OSError:  # Windows 에서 그 사진을 보내는 중이면 못 지운다. DB 는 이미 새 사진이라 파일만 남는다
        log.warning("예전 사진 파일을 지우지 못했습니다: %s", photo_path)


def respond(photo_path: str | None) -> FileResponse:
    if not photo_path or not file_of(photo_path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 사진이 없습니다.")
    # 주소에 ?v=파일이름 이 붙어 사진을 바꾸면 주소도 바뀌므로 하루 동안 브라우저에 둔다 (본인 브라우저에만)
    return FileResponse(file_of(photo_path), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


def url_of(kind: str, owner_id: int, photo_path: str | None) -> str | None:
    """화면이 쓰는 주소 (사진을 바꾸면 v 가 바뀌어 새로 받는다). <img> 에는 &token= 을 붙여 쓴다"""
    return f"/api/{kind}/{owner_id}/photo?v={Path(photo_path).stem}" if photo_path else None
