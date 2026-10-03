from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database import Base, get_db, make_engine
from app.main import app
from app.models import Role, User, UserStatus
from app.seed import seed_base, seed_demo
from app.security import hash_password

ADMIN = ("admin.test", "admin-pass-1234")
MANAGER = ("manager.test", "manager-pass-1234")


@pytest.fixture
def db_session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        seed_base(db)
        seed_demo(db)
        for (login_id, pw), role in ((ADMIN, Role.ADMIN), (MANAGER, Role.MANAGER)):
            db.add(User(login_id=login_id, password_hash=hash_password(pw), name=login_id, role=role,
                        status=UserStatus.ACTIVE, approved_at=datetime.now()))
        db.commit()

    def override():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield Session
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture
def client(db_session):
    return TestClient(app)


def login(client, login_id, password) -> dict:
    res = client.post("/api/auth/login", json={"login_id": login_id, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client, *ADMIN)


@pytest.fixture
def manager(client):
    return login(client, *MANAGER)


@pytest.fixture
def ingest():
    return {"X-Ingest-Key": settings.ingest_api_key}
