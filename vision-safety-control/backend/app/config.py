from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]  # 저장소 최상위 폴더
DEV_JWT_SECRET = "dev-only-secret-do-not-use-in-production"


class Settings(BaseSettings):
    """환경 변수 또는 backend/.env 에서 읽는 설정. 예시는 backend/.env.example 참고."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://safety:safety@localhost:3306/safety_control?charset=utf8mb4"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 8 * 60  # 관제 근무 한 교대 시간
    ingest_api_key: str = "change-me-too"  # AI 탐지 프로그램이 이벤트를 올릴 때 쓰는 키
    max_failed_logins: int = 5
    login_lock_minutes: int = 15  # 비밀번호를 max_failed_logins 번 틀리면 이만큼 로그인 금지 (지나면 자동 해제)

    @field_validator("ingest_api_key")
    @classmethod
    def ascii_only(cls, v: str) -> str:
        if not v.isascii():
            raise ValueError("INGEST_API_KEY 는 HTTP 헤더로 보내므로 영문 · 숫자 · 기호만 쓸 수 있습니다 (한글 X)")
        return v

    frontend_dir: Path = ROOT_DIR / "frontend"
    weather_dir: Path = ROOT_DIR / "tools" / "weather"
    snapshot_dir: Path = ROOT_DIR / "storage" / "snapshots"
    plan_dir: Path = ROOT_DIR / "storage" / "plans"  # 현장 도면 그림 (site_plan.image_path 는 "plans/...")
    max_plan_mb: int = 15
    roi_zones_file: Path = ROOT_DIR / "storage" / "roi-zones.json"  # ROI 그리기 화면이 그린 구역 (AI 탐지 프로그램이 읽음)
    video_dir: Path = ROOT_DIR / "storage" / "videos"  # 시연 · 개발용 영상 (카메라 대신)  # event_snapshot.image_path 는 이 폴더 기준 "snapshots/..." 경로

    # YOLO 탐지 영상 (관제화면 1-1 · 단일 카메라 확대 1-2). 패키지는 requirements-yolo.txt
    yolo_enabled: bool = True
    yolo_model: str = "yolo11n.pt"  # 이름만 쓰면 처음 실행할 때 내려받는다. 직접 학습한 모델은 파일 경로
    yolo_conf: float = 0.35         # 이 confidence 미만인 탐지 박스는 그리지 않음
    yolo_imgsz: int = 640
    yolo_device: str = ""           # 비우면 자동 (그래픽카드가 있으면 cuda:0, 없으면 cpu)
    stream_fps: int = 8             # 화면으로 보내는 초당 장수 (탐지는 CPU 가 되는 만큼만). 노트북 기준으로 낮춤
    stream_max_width: int = 960     # 이보다 큰 영상은 줄여서 보냄 (탐지도 줄인 영상으로 함)
    stream_jpeg_quality: int = 80
    event_watch: bool = True        # 보는 사람이 없어도 ROI 를 판정할 카메라는 계속 탐지해 이벤트를 남김 (false 면 화면을 볼 때만)


settings = Settings()
