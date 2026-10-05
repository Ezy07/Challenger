"""시연 · 개발용 영상 파일 (storage/videos). 실제 카메라 대신 카메라에 연결해서 쓴다."""

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings
from ..deps import CurrentUser

router = APIRouter(prefix="/api/videos", tags=["영상 파일"])

VIDEO_EXT = {".mp4", ".m4v", ".webm", ".mov", ".avi", ".mkv"}
URL_PREFIX = "videos/"  # camera.stream_url 에 "videos/파일이름" 으로 저장

# 파일 안의 표시로 영상 형식을 짐작한다 (mp4 는 형식 정보가 파일 앞이나 끝에 있음)
CODECS = [(b"avc1", "H.264"), (b"hvc1", "H.265"), (b"hev1", "H.265"), (b"av01", "AV1"), (b"vp09", "VP9"), (b"mp4v", "MPEG-4")]
BROWSER_OK = {"H.264", "VP9", "AV1"}  # Edge · Chrome 에서 어느 PC 나 재생되는 것


class VideoOut(BaseModel):
    name: str
    url: str          # 브라우저에서 여는 주소 (/videos/파일이름)
    stream_url: str   # 카메라에 저장하는 값 (videos/파일이름)
    size_mb: float
    codec: str | None
    browser_ok: bool  # False 면 관제화면에서 안 보일 수 있음 (H.265 등)


def sniff_codec(path: Path) -> str | None:
    if path.suffix.lower() == ".webm":
        return "VP9"
    size = path.stat().st_size
    with path.open("rb") as f:
        head = f.read(4_000_000)
        f.seek(max(0, size - 4_000_000))
        tail = f.read()
    for mark, name in CODECS:
        if mark in head or mark in tail:
            return name
    return None


def video_path(stream_url: str | None) -> Path | None:
    """카메라 stream_url 이 영상 파일을 가리키면 실제 파일 경로, 아니면 None (폴더 밖은 막음)"""
    if not stream_url or not stream_url.startswith(URL_PREFIX):
        return None
    name = stream_url[len(URL_PREFIX):]
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    return settings.video_dir / name


@router.get("", response_model=list[VideoOut])
def list_videos(_: CurrentUser):
    files = sorted(p for p in settings.video_dir.glob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    out = []
    for p in files:
        codec = sniff_codec(p)
        out.append(VideoOut(
            name=p.name, url=f"/videos/{p.name}", stream_url=URL_PREFIX + p.name,
            size_mb=round(p.stat().st_size / 1_000_000, 1), codec=codec,
            browser_ok=codec in BROWSER_OK and p.suffix.lower() in {".mp4", ".m4v", ".webm"},
        ))
    return out
