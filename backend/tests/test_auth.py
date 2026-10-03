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
    assert pending[0]["login_id"] == "hong.gd"  # 최근 신청이 맨 위
    assert {u["status"] for u in pending} == {"PENDING"}
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


def test_approve_with_lower_role(client, admin):
    uid = client.post("/api/auth/signup", json=SIGNUP).json()["id"]
    res = client.post(f"/api/users/{uid}/approve", json={"role": "VIEWER"}, headers=admin).json()
    assert (res["role"], res["status"]) == ("VIEWER", "ACTIVE")
    assert client.post(f"/api/users/{uid}/approve", json={"role": "ADMIN"}, headers=admin).status_code == 422


def test_admin_creates_user_with_temp_password(client, admin):
    res = client.post("/api/users", json={"login_id": "new.user", "name": "신규", "role": "MANAGER"}, headers=admin)
    assert res.status_code == 201
    body = res.json()
    assert body["user"]["status"] == "ACTIVE"
    login(client, "new.user", body["temp_password"])


def test_reset_password_unlocks(client, admin):
    for _ in range(settings.max_failed_logins):
        client.post("/api/auth/login", json={"login_id": "manager.test", "password": "x"})
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["login_id"] == "manager.test")
    res = client.post(f"/api/users/{uid}/reset-password", headers=admin).json()
    assert res["user"]["status"] == "ACTIVE"
    login(client, "manager.test", res["temp_password"])
    # 예전 비밀번호는 더 이상 안 됨
    assert client.post("/api/auth/login", json={"login_id": "manager.test", "password": "manager-pass-1234"}).status_code == 401


def test_delete_user_keeps_row_but_blocks_login(client, admin):
    users = client.get("/api/users", headers=admin).json()
    uid = next(u["id"] for u in users if u["login_id"] == "manager.test")
    assert client.delete(f"/api/users/{uid}", headers=admin).status_code == 204
    assert "manager.test" not in [u["login_id"] for u in client.get("/api/users", headers=admin).json()]
    assert client.get(f"/api/users/{uid}", headers=admin).status_code == 404
    res = client.post("/api/auth/login", json={"login_id": "manager.test", "password": "manager-pass-1234"})
    assert res.status_code == 403

    me = client.get("/api/auth/me", headers=admin).json()
    assert client.delete(f"/api/users/{me['id']}", headers=admin).status_code == 409


def test_pending_status_not_changed_by_patch(client, admin):
    uid = client.post("/api/auth/signup", json=SIGNUP).json()["id"]
    assert client.patch(f"/api/users/{uid}", json={"status": "ACTIVE"}, headers=admin).status_code == 409


def test_demo_users_can_log_in(client):
    from .conftest import DEMO_PASSWORD
    headers = login(client, "oh.sy", DEMO_PASSWORD)
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "MANAGER"
    assert client.post("/api/auth/login", json={"login_id": "yoon.gr", "password": DEMO_PASSWORD}).status_code == 403
