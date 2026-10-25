import asyncio
import logging
import mimetypes
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .clock import now_kst
from .config import DEV_JWT_SECRET, settings
from .deps import CurrentUser
from . import vision, zone_events
from .routers import (auth, cameras, equipment, events, meta, photos, push, roi_zones, site_plan, stats, stream, users, videos,
                      workers, works, zones)
from .routers.roi_zones import sync_stored_zones


async def _watch_roi_schedule():
    """화면을 닫아 둬도 적용 시간이 되면 구역 사용 여부를 파일에 반영한다."""
    while True:
        await asyncio.sleep(20)
        try:
            await asyncio.to_thread(sync_stored_zones)
        except Exception:
            logging.getLogger("uvicorn.error").exception("ROI 사용 여부를 적용 시간에 맞추지 못했습니다")


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(_watch_roi_schedule())
    zone_events.start()  # YOLO 탐지 → ROI 침범 · 체류 이벤트 (YOLO 를 못 쓰면 그냥 끝남)
    yield
    vision.shutdown()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="비전AI 안전관제 API", version="0.1.0", lifespan=lifespan)
STARTED_AT = int(time.time() * 1000)

if settings.jwt_secret == DEV_JWT_SECRET:
    logging.getLogger("uvicorn.error").warning("JWT_SECRET 이 개발용 기본값입니다. 운영 전에 .env 에서 꼭 바꾸세요.")

for r in (auth, users, meta, zones, site_plan, cameras, roi_zones, videos, stream, workers, works, equipment, events, stats, push,
          photos):
    app.include_router(r.router)


@app.middleware("http")
async def revalidate_static(request, call_next):
    """화면 파일(html · js · css)은 브라우저가 매번 바뀌었는지 확인하게 한다.
    안 그러면 common.js 를 고쳐도 브라우저가 예전 파일을 계속 쓴다. 안 바뀌었으면 304 로 짧게 끝난다."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.get("/api/health", tags=["상태"])
def health():
    return {"ok": True, "started_at": STARTED_AT}


@app.get("/api/clock", tags=["상태"])
def clock(_: CurrentUser):
    """지금 시각. 인터넷에서 받은 한국 시각이고, 못 받으면 이 PC 의 한국 시각이다."""
    now, source = now_kst()
    return {"now": now.isoformat(timespec="seconds"), "source": source}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


# 화면(frontend/) · 날씨 데이터(tools/weather/) · 스냅샷 이미지 · 현장 도면 · 영상(storage/)은 같은 서버에서 그대로 내려준다.
# monitor.html 은 ../weather/weather.json 을 읽으므로 /weather 경로에 붙인다.
mimetypes.add_type("application/manifest+json", ".webmanifest")  # 홈 화면에 추가(PWA) 정보. 윈도우에는 이 형식이 없다
settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
settings.video_dir.mkdir(parents=True, exist_ok=True)
settings.plan_dir.mkdir(parents=True, exist_ok=True)
app.mount("/weather", StaticFiles(directory=settings.weather_dir), name="weather")
app.mount("/snapshots", StaticFiles(directory=settings.snapshot_dir), name="snapshots")
app.mount("/plans", StaticFiles(directory=settings.plan_dir), name="plans")
app.mount("/videos", StaticFiles(directory=settings.video_dir), name="videos")  # 영상은 Range 요청으로 나눠 받음
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
