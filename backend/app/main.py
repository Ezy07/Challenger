import logging

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import DEV_JWT_SECRET, settings
from .routers import auth, cameras, events, meta, users

app = FastAPI(title="비전AI 안전관제 API", version="0.1.0")

if settings.jwt_secret == DEV_JWT_SECRET:
    logging.getLogger("uvicorn.error").warning("JWT_SECRET 이 개발용 기본값입니다. 운영 전에 .env 에서 꼭 바꾸세요.")

for r in (auth, users, meta, cameras, events):
    app.include_router(r.router)


@app.get("/api/health", tags=["상태"])
def health():
    return {"ok": True}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/login.html")


# 화면(frontend/)과 날씨 데이터(tools/weather/)는 같은 서버에서 그대로 내려준다.
# monitor.html 은 ../weather/weather.json 을 읽으므로 /weather 경로에 붙인다.
app.mount("/weather", StaticFiles(directory=settings.weather_dir), name="weather")
app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")
