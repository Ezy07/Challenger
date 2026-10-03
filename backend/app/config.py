from pathlib import Path

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

    frontend_dir: Path = ROOT_DIR / "frontend"
    weather_dir: Path = ROOT_DIR / "tools" / "weather"


settings = Settings()
