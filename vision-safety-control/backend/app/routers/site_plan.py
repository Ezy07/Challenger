"""현장 도면 (한 장). 전체 구역 표시 · 카메라 배치도의 배경으로 같이 쓴다.

그림은 storage/plans 에 저장하고 /plans/파일이름 으로 내려준다 (스냅샷과 같은 방식).
올릴 때는 multipart 대신 그림 파일 자체를 요청 본문으로 보낸다 (Content-Type: image/png 등).
"""

import struct
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from ..config import settings
from ..deps import DB, Admin, CurrentUser
from ..models import SitePlan
from ..schemas import SitePlanOut, SitePlanUpdate

router = APIRouter(prefix="/api/site-plan", tags=["현장 도면"])

EXT = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
MAX_SIDE = 20000  # 이보다 큰 숫자가 나오면 잘못 읽은 것으로 본다


def image_size(data: bytes) -> tuple[str, int, int] | None:
    """PNG · JPEG · WebP 의 (형식, 너비, 높이). 그림이 아니면 None (확장자 · Content-Type 은 믿지 않는다)"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return "png", w, h
    if data[:3] == b"\xff\xd8\xff":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # 길이 없는 표시
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # SOF: 그림 크기
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpeg", w, h
            i += 2 + length
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        kind = data[12:16]
        if kind == b"VP8 " and len(data) >= 30:
            w, h = struct.unpack("<HH", data[26:30])
            return "webp", w & 0x3FFF, h & 0x3FFF
        if kind == b"VP8L" and len(data) >= 25:
            b = data[21:25]
            w = 1 + (((b[1] & 0x3F) << 8) | b[0])
            h = 1 + (((b[3] & 0x0F) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
            return "webp", w, h
        if kind == b"VP8X" and len(data) >= 30:
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return "webp", w, h
    return None


def current(db: DB) -> SitePlan | None:
    return db.scalar(select(SitePlan).order_by(SitePlan.id).limit(1))


def file_of(plan: SitePlan) -> Path:
    return settings.plan_dir / Path(plan.image_path).name


def to_out(plan: SitePlan) -> SitePlanOut:
    return SitePlanOut(
        title=plan.title, url=f"/{plan.image_path}?v={int(plan.uploaded_at.timestamp())}", original_name=plan.original_name,
        width=plan.width, height=plan.height, size_bytes=plan.size_bytes,
        uploaded_by_name=plan.uploader.name if plan.uploader else None, uploaded_at=plan.uploaded_at,
    )


@router.get("", response_model=SitePlanOut | None)
def read_plan(db: DB, _: CurrentUser):
    """지금 도면. 아직 안 올렸으면 null (화면은 격자 배경을 보여 준다)"""
    plan = current(db)
    return to_out(plan) if plan else None


@router.put("", response_model=SitePlanOut)
async def upload_plan(request: Request, db: DB, user: Admin,
                      filename: str | None = Query(default=None, max_length=255),
                      title: str | None = Query(default=None, min_length=1, max_length=100)):
    """도면 올리기 · 바꾸기. 본문 = 그림 파일 그대로 (PNG · JPG · WebP, 15MB 까지)"""
    limit = settings.max_plan_mb * 1024 * 1024
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"도면 파일은 {settings.max_plan_mb}MB 까지 올릴 수 있습니다.")
    data = await request.body()
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"도면 파일은 {settings.max_plan_mb}MB 까지 올릴 수 있습니다.")
    info = image_size(data)
    if not info or not (0 < info[1] <= MAX_SIDE and 0 < info[2] <= MAX_SIDE):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "PNG · JPG · WebP 그림만 올릴 수 있습니다. (PDF · CAD 도면은 그림으로 저장해서 올려 주세요)")
    kind, width, height = info

    settings.plan_dir.mkdir(parents=True, exist_ok=True)
    name = f"site-plan-{datetime.now():%Y%m%d-%H%M%S-%f}{EXT[kind]}"
    (settings.plan_dir / name).write_bytes(data)

    plan = current(db)
    old_file = file_of(plan) if plan else None
    if not plan:
        plan = SitePlan(title=title or "현장 배치도")
        db.add(plan)
    elif title:
        plan.title = title
    plan.image_path = f"plans/{name}"
    plan.original_name = Path(filename).name if filename else None
    plan.width, plan.height, plan.size_bytes = width, height, len(data)
    plan.uploaded_by = user.id
    plan.uploaded_at = datetime.now()
    db.commit()
    db.refresh(plan)
    if old_file and old_file.name != name:
        old_file.unlink(missing_ok=True)
    return to_out(plan)


@router.patch("", response_model=SitePlanOut)
def update_plan(body: SitePlanUpdate, db: DB, _: Admin):
    """도면 이름 바꾸기 (그림은 그대로)"""
    plan = current(db)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 올린 도면이 없습니다.")
    plan.title = body.title
    db.commit()
    db.refresh(plan)
    return to_out(plan)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(db: DB, _: Admin):
    """도면 지우기. 구역 · 카메라 위치(비율)는 남겨 두어, 같은 도면을 다시 올리면 그대로 맞는다"""
    plan = current(db)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "아직 올린 도면이 없습니다.")
    path = file_of(plan)
    db.delete(plan)
    db.commit()
    path.unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
