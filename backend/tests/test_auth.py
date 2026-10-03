from app.config import settings

from .conftest import login

SIGNUP = {"login_id": "hong.gd", "password": "password123", "name": "홍길동", "role": "MANAGER"}


def test_signup_needs_approval_before_login(client, admin):
    res = client.post("/api/auth/signup", json=SIGNUP)
    assert res.status_code == 201
    user = res.json()
    assert user["status"] == "PENDING"
    assert "password_hash" not in user

    res = client.post("/api/auth/login", json={"login_id": "hong.gd", "password": "password123"})
    assert res.status_code == 403

    pending = client.get("/api/users", params={"status": "PENDING"}, headers=admin).json()
    assert [u["login_id"] for u in pending] == ["hong.gd"]
    assert client.post(f"/api/users/{user['id']}/approve", headers=admin).json()["status"] == "ACTIVE"

    headers = login(client, "hong.gd", "password123")
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "MANAGER"


def test_signup_cannot_request_admin(client):
    res = client.post("/api/auth/signup", json={**SIGNUP, "role": "ADMIN"})
    assert res.status_code == 422


def test_duplicate_login_id(client):
    client.post("/api/auth/signup", json=SIGNUP)
    assert client.post("/api/auth/signup", json=SIGNUP).status_code == 409


def test_lock_after_failed_logins(client, admin):
    for _ in range(settings.max_failed_logins - 1):
        assert client.post("/api/auth/login", json={"login_id": "manager.test", "password": "x"}).status_code == 401
    res = client.post("/api/auth/login", json={"login_id": "manager.test", "password": "x"})
    assert res.status_code == 403
    # 맞는 비밀번호여도 잠겨 있으면 못 들어옴
    assert client.post("/api/auth/login", json={"login_id": "manager.test", "password": "manager-pass-1234"}).status_code == 403

    users = client.get("/api/users", headers=admin).json()
    uid = next(u["id"] for u in users if u["login_id"] == "manager.test")
    assert client.patch(f"/api/users/{uid}", json={"status": "ACTIVE"}, headers=admin).status_code == 200
    login(client, "manager.test", "manager-pass-1234")


def test_admin_only_routes(client, manager):
    assert client.get("/api/users").status_code == 401
    assert client.get("/api/users", headers=manager).status_code == 403


def test_admin_cannot_demote_self(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    assert client.patch(f"/api/users/{me['id']}", json={"role": "VIEWER"}, headers=admin).status_code == 409
