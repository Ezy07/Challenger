from datetime import date, timedelta

TODAY = date.today()


def worker_by_name(client, headers, name):
    return next(w for w in client.get("/api/workers", headers=headers).json() if w["name"] == name)


# ---------------------------------------------------------------- 작업자
def test_worker_crud(client, manager):
    res = client.post("/api/workers", json={"name": "홍길동", "company": "대한골조", "job_type": "형틀목공",
                                            "birth_date": "1985-01-01"}, headers=manager)
    assert res.status_code == 201
    w = res.json()
    assert w["age"] == TODAY.year - 1985 - ((TODAY.month, TODAY.day) < (1, 1))
    assert w["general_edu"] is False and w["today_work"] is None

    w = client.patch(f"/api/workers/{w['id']}", json={"phone": "010-1111-2222"}, headers=manager).json()
    assert w["phone"] == "010-1111-2222"

    assert client.delete(f"/api/workers/{w['id']}", headers=manager).status_code == 204
    assert client.get(f"/api/workers/{w['id']}", headers=manager).status_code == 404
    assert "홍길동" not in [x["name"] for x in client.get("/api/workers", headers=manager).json()]


def test_viewer_cannot_write_workers(client, admin):
    client.post("/api/auth/signup", json={"login_id": "viewer.w", "password": "password123", "name": "조회", "role": "VIEWER"})
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["login_id"] == "viewer.w")
    client.post(f"/api/users/{uid}/approve", headers=admin)
    from .conftest import login
    viewer = login(client, "viewer.w", "password123")
    assert client.get("/api/workers", headers=viewer).status_code == 200
    assert client.post("/api/workers", json={"name": "x"}, headers=viewer).status_code == 403


def test_demo_special_tags_and_today_work(client, manager):
    kim = worker_by_name(client, manager, "김영수")
    assert kim["special_tags"] == [f"고령 {kim['age']}세"]
    assert kim["today_work"]["name"] == "102동 대형거푸집 설치"
    nam = worker_by_name(client, manager, "응우옌 반 남")
    assert nam["special_tags"] == ["신규 투입 · D+3"]
    han = worker_by_name(client, manager, "한상우")
    assert han["general_edu"] is False and han["today_work"] is None

    special = client.get("/api/workers", params={"special": "true"}, headers=manager).json()
    assert {w["name"] for w in special} == {"김영수", "박상철", "서준기", "응우옌 반 남", "오병철", "한상우"}


def test_new_worker_reason_expires_after_7_days(client, manager):
    w = client.post("/api/workers", json={"name": "신입", "start_date": str(TODAY - timedelta(days=8))}, headers=manager).json()
    w = client.post(f"/api/workers/{w['id']}/special", json={"reasons": ["NEW"]}, headers=manager).json()
    assert w["is_special_care"] is True
    assert w["special_tags"] == []  # 8일 지나서 자동으로 빠짐
    w = client.patch(f"/api/workers/{w['id']}", json={"start_date": str(TODAY - timedelta(days=2))}, headers=manager).json()
    assert w["special_tags"] == ["신규 투입 · D+2"]


def test_special_designate_and_clear(client, manager):
    lee = worker_by_name(client, manager, "이정호")
    res = client.post(f"/api/workers/{lee['id']}/special", json={"reasons": ["HYPERTENSION", "ETC"], "memo": "혈압 주의"},
                      headers=manager).json()
    assert res["special_tags"] == ["고혈압", "기타"]
    assert res["special_since"] == str(TODAY)
    assert res["special_by_name"] == "manager.test"
    assert client.post(f"/api/workers/{lee['id']}/special", json={"reasons": []}, headers=manager).status_code == 422

    res = client.delete(f"/api/workers/{lee['id']}/special", headers=manager).json()
    assert res["is_special_care"] is False and res["special_tags"] == [] and res["special_since"] is None


def test_worker_education(client, manager):
    from app.models import REQUIRED_GENERAL_EDU

    han = worker_by_name(client, manager, "한상우")
    edus = client.get("/api/educations", headers=manager).json()
    generals = [e for e in edus if e["name"] in REQUIRED_GENERAL_EDU]
    assert {e["name"] for e in generals} == set(REQUIRED_GENERAL_EDU)
    res = client.post(f"/api/workers/{han['id']}/educations", json={"edu_id": generals[0]["id"], "completed_date": str(TODAY)},
                      headers=manager)
    assert res.status_code == 201
    han = res.json()
    assert han["general_edu"] is False  # 4개 중 하나만으로는 이수되지 않는다
    record = han["educations"][0]
    future = {"edu_id": generals[0]["id"], "completed_date": str(TODAY + timedelta(days=1))}
    assert client.post(f"/api/workers/{han['id']}/educations", json=future, headers=manager).status_code == 422

    for edu in generals[1:]:
        han = client.post(f"/api/workers/{han['id']}/educations", json={"edu_id": edu["id"], "completed_date": str(TODAY)},
                          headers=manager).json()
    assert han["general_edu"] is True

    han = client.delete(f"/api/workers/{han['id']}/educations/{record['id']}", headers=manager).json()
    assert han["general_edu"] is False


def test_deleted_worker_leaves_open_work_and_equipment(client, manager):
    jung = worker_by_name(client, manager, "정대호")
    exc = next(e for e in client.get("/api/equipment", headers=manager).json() if e["name"] == "EXC_01")
    assert exc["operator_id"] == jung["id"]
    work_id = jung["today_work"]["id"]
    client.delete(f"/api/workers/{jung['id']}", headers=manager)
    detail = client.get(f"/api/works/{work_id}", headers=manager).json()
    assert "정대호" not in [w["name"] for w in detail["workers"]]
    assert client.get(f"/api/equipment/{exc['id']}", headers=manager).json()["operator_id"] is None


# ---------------------------------------------------------------- 작업 · 배정
def test_works_today_and_upcoming(client, manager):
    today = client.get("/api/works", params={"on": str(TODAY)}, headers=manager).json()
    assert len(today) == 6  # 103동 외벽 배관은 3일 뒤 시작
    upcoming = client.get("/api/works", params={"upcoming": "true"}, headers=manager).json()
    assert "103동 외벽 배관" in [w["name"] for w in upcoming]
    stopped = next(w for w in today if w["name"] == "102동 대형거푸집 설치")
    assert stopped["status"] == "STOPPED" and stopped["worker_count"] == 2 and stopped["special_count"] == 1


def test_work_crud_and_assign(client, manager):
    zones = client.get("/api/work-zones", headers=manager).json()
    body = {"name": "외벽 도장", "work_zone_id": zones[0]["id"], "start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=3)),
            "status": "PLANNED", "description": "곤돌라 사용"}
    res = client.post("/api/works", json=body, headers=manager)
    assert res.status_code == 201
    work = res.json()
    assert work["workers"] == [] and work["description"] == "곤돌라 사용"

    bad = {**body, "end_date": str(TODAY - timedelta(days=1))}
    assert client.post("/api/works", json=bad, headers=manager).status_code == 422

    han, lee = worker_by_name(client, manager, "한상우"), worker_by_name(client, manager, "이정호")
    work = client.put(f"/api/works/{work['id']}/workers", json={"worker_ids": [han["id"], lee["id"]]}, headers=manager).json()
    assert [w["name"] for w in work["workers"]] == ["이정호", "한상우"]
    assert work["special_count"] == 1  # 한상우 신규 투입
    assert work["workers"][0]["assigned_date"] == str(TODAY)

    # 배정이 남아 있으면 삭제 불가
    assert client.delete(f"/api/works/{work['id']}", headers=manager).status_code == 409
    work = client.put(f"/api/works/{work['id']}/workers", json={"worker_ids": [lee["id"]]}, headers=manager).json()
    assert [w["name"] for w in work["workers"]] == ["이정호"]

    work = client.patch(f"/api/works/{work['id']}", json={"status": "IN_PROGRESS", "name": "외벽 도장 1차"}, headers=manager).json()
    assert (work["status"], work["name"]) == ("IN_PROGRESS", "외벽 도장 1차")

    client.put(f"/api/works/{work['id']}/workers", json={"worker_ids": []}, headers=manager)
    assert client.delete(f"/api/works/{work['id']}", headers=manager).status_code == 204
    assert client.get(f"/api/works/{work['id']}", headers=manager).status_code == 404


def test_work_manager_must_be_active_staff(client, admin, manager):
    users = client.get("/api/users", headers=admin).json()
    viewer = next(u for u in users if u["role"] == "VIEWER")  # 윤가람 (조회 전용 · 잠금)
    zones = client.get("/api/work-zones", headers=manager).json()
    body = {"name": "x", "work_zone_id": zones[0]["id"], "start_date": str(TODAY), "manager_id": viewer["id"]}
    assert client.post("/api/works", json=body, headers=manager).status_code == 422


def test_staff_list_for_any_logged_in_user(client, manager):
    staff = client.get("/api/users/staff", headers=manager).json()
    names = {s["name"] for s in staff}
    assert {"오세영", "박진우", "한지훈"} <= names
    assert "윤가람" not in names  # 조회 전용 · 잠금
    assert "이수진" not in names  # 승인 대기
    assert set(staff[0]) == {"id", "name", "position", "role"}
