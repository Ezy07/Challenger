import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .config import DEV_JWT_SECRET, settings
from .routers import auth, cameras, equipment, events, meta, stats, users, videos, workers, works, zones

app = FastAPI(title="비전AI 안전관제 API", version="0.1.0")

if settings.jwt_secret == DEV_JWT_SECRET:
    logging.getLogger("uvicorn.error").warning("JWT_SECRET 이 개발용 기본값입니다. 운영 전에 .env 에서 꼭 바꾸세요.")

for r in (auth, users, meta, zones, cameras, videos, workers, works, equipment, events, stats):
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
    return {"ok": True}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


# 화면(frontend/) · 날씨 데이터(tools/weather/) · 스냅샷 이미지 · 영상(storage/)은 같은 서버에서 그대로 내려준다.
# monitor.html 은 ../weather/weather.json 을 읽으므로 /weather 경로에 붙인다.
settings.snapshot_dir.mkdir(parents=True, exist_ok=True)
settings.video_dir.mkdir(parents=True, exist_ok=True)
app.mount("/weather", StaticFiles(directory=settings.weather_dir), name="weather")
app.mount("/snapshots", StaticFiles(directory=settings.snapshot_dir), name="snapshots")
app.mount("/videos", StaticFiles(directory=settings.video_dir), name="videos")  # 영상은 Range 요청으로 나눠 받음
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
