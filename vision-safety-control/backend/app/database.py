from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        # SQLite 는 기본으로 외래키 검사를 하지 않으므로 켠다 (테스트에서 MySQL 과 같게 동작하도록)
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
