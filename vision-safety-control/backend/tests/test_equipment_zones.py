from datetime import date, datetime, timedelta


TODAY = date.today()


def equip(client, headers, name):
    return next(e for e in client.get("/api/equipment", headers=headers).json() if e["name"] == name)


# ---------------------------------------------------------------- 장비
def test_equipment_list_values(client, manager):
    items = client.get("/api/equipment", headers=manager).json()
    assert len(items) == 10
    tc1 = next(e for e in items if e["name"] == "T-CRN-01 · 1호기")
    assert tc1["reg_no"] == "TC-2024-0117" and tc1["operator_name"] == "김창식"
    assert [c["name"] for c in tc1["cameras"]] == ["TC1_CAM"]
    assert tc1["today_log"]["inspected_at"] is not None
    assert tc1["zone_events_today"] == 3  # 101동 구역 (CAM_0001) 오늘 이벤트
    fork = next(e for e in items if e["name"] == "FORK-01")
    assert fork["work_zone_id"] is None and fork["status"] == "BROKEN"  # 미투입 · 고장
    trucks = client.get("/api/equipment", params={"equip_type": "MIXER_TRUCK"}, headers=manager).json()
    assert {t["company"] for t in trucks} == {"OO레미콘"}


def test_equipment_crud(client, manager):
    body = {"name": "EXC_02", "equip_type": "EXCAVATOR", "reg_no": "EX-2026-0001", "spec": "0.6㎥"}
    res = client.post("/api/equipment", json=body, headers=manager)
    assert res.status_code == 201
    e = res.json()
    assert e["status"] == "IDLE" and e["logs"] == []
    assert client.post("/api/equipment", json={**body, "name": "EXC_03"}, headers=manager).status_code == 409  # 등록번호 중복

    e = client.patch(f"/api/equipment/{e['id']}", json={"status": "RUNNING", "company": "한빛토건"}, headers=manager).json()
    assert (e["status"], e["company"]) == ("RUNNING", "한빛토건")
    assert client.delete(f"/api/equipment/{e['id']}", headers=manager).status_code == 204
    assert client.get(f"/api/equipment/{e['id']}", headers=manager).status_code == 404


def test_equipment_with_camera_cannot_be_deleted_or_retyped(client, manager):
    tc1 = equip(client, manager, "T-CRN-01 · 1호기")
    assert client.delete(f"/api/equipment/{tc1['id']}", headers=manager).status_code == 409
    assert client.patch(f"/api/equipment/{tc1['id']}", json={"equip_type": "CRANE"}, headers=manager).status_code == 409


def test_daily_save_updates_equipment_and_log(client, manager):
    tc2, fork = equip(client, manager, "T-CRN-02 · 2호기"), equip(client, manager, "FORK-01")
    zones = {z["name"]: z["id"] for z in client.get("/api/work-zones", headers=manager).json()}
    items = [
        {"equipment_id": tc2["id"], "work_zone_id": tc2["work_zone_id"], "operator_id": tc2["operator_id"], "status": "RUNNING"},
        {"equipment_id": fork["id"], "work_zone_id": zones["외곽 야적장"], "operator_id": fork["operator_id"], "status": "IDLE"},
    ]
    res = client.post("/api/equipment/daily", json={"items": items}, headers=manager)
    assert res.status_code == 200
    by_name = {e["name"]: e for e in res.json()}
    assert by_name["T-CRN-02 · 2호기"]["status"] == "RUNNING"
    assert by_name["T-CRN-02 · 2호기"]["today_log"]["inspected_at"] is not None  # 아침 점검 시각은 그대로
    assert by_name["FORK-01"]["work_zone_name"] == "외곽 야적장"
    assert by_name["FORK-01"]["today_log"]["status"] == "IDLE"
    assert by_name["FORK-01"]["today_log"]["recorded_by_name"] == "manager.test"


def test_equipment_checks_round_trip(client, manager):
    exc = equip(client, manager, "EXC_01")
    docs = client.put(f"/api/equipment/{exc['id']}/checks/docs",
                      json={"items": ["work_plan", "license", "license"]}, headers=manager)
    assert docs.status_code == 200, docs.text
    assert docs.json()["doc_checks"] == ["work_plan", "license"]
    edu = client.put(f"/api/equipment/{exc['id']}/checks/edu",
                     json={"items": ["special"]}, headers=manager).json()
    assert edu["edu_checks"] == ["special"] and edu["doc_checks"] == ["work_plan", "license"]
    again = client.get(f"/api/equipment/{exc['id']}", headers=manager).json()
    assert again["doc_checks"] == ["work_plan", "license"] and again["edu_checks"] == ["special"]
    bad = client.put(f"/api/equipment/{exc['id']}/checks/docs", json={"items": ["bus"]}, headers=manager)
    assert bad.status_code == 422
    assert client.put(f"/api/equipment/{exc['id']}/checks/edu", json={"items": []}).status_code == 401


def test_daily_log_write(client, manager):
    exc = equip(client, manager, "EXC_01")
    checked = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=7, minutes=5)
    detail = client.put(f"/api/equipment/{exc['id']}/logs/{TODAY}", json={"status": "RUNNING",
                        "inspected_at": checked.isoformat(), "note": "유압 호스 교체 완료"}, headers=manager).json()
    assert detail["status"] == "RUNNING"  # 오늘 기록은 현재 상태도 바꾼다
    assert detail["logs"][0]["note"] == "유압 호스 교체 완료"
    assert len(detail["logs"]) == 3
    assert any(ev["detection_code"] == "GROUND_SUBSIDENCE" for ev in detail["events"])  # Sector A 이벤트
    tomorrow = TODAY + timedelta(days=1)
    assert client.put(f"/api/equipment/{exc['id']}/logs/{tomorrow}", json={"status": "IDLE"}, headers=manager).status_code == 422


# ---------------------------------------------------------------- 작업구역
def test_zone_summary(client, manager):
    zones = {z["name"]: z for z in client.get("/api/work-zones/summary", headers=manager).json()}
    assert len(zones) == 6
    z101 = zones["101동 갱폼 인양구역"]
    assert [w["name"] for w in z101["works"]] == ["101동 갱폼 인양", "101동 3층 슬래브 타설"]
    assert z101["worker_count"] == 4 and z101["special_count"] == 2  # 박상철 · 서준기 고혈압
    assert z101["cameras"] == ["CAM_0001", "TC1_CAM"]
    assert z101["open_events"] == 1 and z101["open_high"] == 1  # 직하부 작업자 (미처리)
    assert len(z101["plan_polygon"]) == 4
    assert zones["103동 외벽 인양구역"]["works"] == []  # 예정 작업은 오늘 것이 아님


def test_zone_summary_counts_installed_cameras(client, admin, manager):
    """새 구역에 카메라를 달면 그 구역 요약에 잡힌다. 사용 안 함으로 꺼도 설치된 대수에는 남는다"""
    zid = client.post("/api/work-zones", json={"name": "104동 신규 구역"}, headers=manager).json()["id"]
    assert any(z["name"] == "104동 신규 구역" for z in client.get("/api/work-zones", headers=admin).json())  # 카메라 등록 화면의 구역 목록
    cam = client.post("/api/cameras", json={"name": "CAM_0104", "work_zone_id": zid, "view_page": 1, "location_desc": "3층 외벽"}, headers=admin).json()
    assert cam["work_zone_name"] == "104동 신규 구역"
    summary = lambda: next(z for z in client.get("/api/work-zones/summary", headers=manager).json() if z["id"] == zid)
    assert (summary()["cameras"], summary()["cameras_off"]) == (["CAM_0104"], [])
    client.patch(f"/api/cameras/{cam['id']}", json={"is_active": False}, headers=admin)
    assert (summary()["cameras"], summary()["cameras_off"]) == ([], ["CAM_0104"])


def test_zone_crud(client, manager):
    poly = [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]
    z = client.post("/api/work-zones", json={"name": "104동 구역", "plan_polygon": poly}, headers=manager)
    assert z.status_code == 201
    zid = z.json()["id"]
    bad = [[0.1, 0.1], [1.5, 0.1], [0.2, 0.2]]
    assert client.patch(f"/api/work-zones/{zid}", json={"plan_polygon": bad}, headers=manager).status_code == 422
    assert client.patch(f"/api/work-zones/{zid}", json={"name": "104동 골조"}, headers=manager).json()["name"] == "104동 골조"

    # 다각형 (ㄱ자 6각형) · 꼭짓점 상한 · 배치도에서 빼기(null)
    ell = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.2], [0.2, 0.2], [0.2, 0.5], [0.1, 0.5]]
    assert client.patch(f"/api/work-zones/{zid}", json={"plan_polygon": ell}, headers=manager).json()["plan_polygon"] == ell
    assert client.patch(f"/api/work-zones/{zid}", json={"plan_polygon": [[0.1, 0.1], [0.2, 0.2]]}, headers=manager).status_code == 422
    many = [[0.5 + 0.3 * (i % 2), i / 41] for i in range(41)]
    assert client.patch(f"/api/work-zones/{zid}", json={"plan_polygon": many}, headers=manager).status_code == 422
    assert client.patch(f"/api/work-zones/{zid}", json={"plan_polygon": None}, headers=manager).json()["plan_polygon"] is None
    assert client.delete(f"/api/work-zones/{zid}", headers=manager).status_code == 204
    used = client.get("/api/work-zones", headers=manager).json()[0]["id"]
    assert client.delete(f"/api/work-zones/{used}", headers=manager).status_code == 409


# ---------------------------------------------------------------- 조직
def test_org_update_and_delete_rules(client, admin):
    orgs = {o["name"]: o for o in client.get("/api/orgs").json()}
    prime, team = orgs["OO건설"], orgs["공사팀"]
    sub = client.post("/api/orgs", json={"type": "DEPT", "name": "양중", "parent_id": team["id"]}, headers=admin)
    assert sub.status_code == 201
    sub = sub.json()
    # 3단계는 안 됨
    assert client.post("/api/orgs", json={"type": "DEPT", "name": "x", "parent_id": sub["id"]}, headers=admin).status_code == 422
    # 하위 부서가 있는 부서를 2단계 아래로 옮기면 하위가 3단계가 되므로 안 됨
    other = orgs["공무팀"]
    assert client.patch(f"/api/orgs/{team['id']}", json={"parent_id": other["id"]}, headers=admin).status_code == 422
    # 자기 하위 부서를 상위로 둘 수 없음
    assert client.patch(f"/api/orgs/{team['id']}", json={"parent_id": sub["id"]}, headers=admin).status_code == 422
    assert client.patch(f"/api/orgs/{sub['id']}", json={"name": "양중파트"}, headers=admin).json()["name"] == "양중파트"

    assert client.delete(f"/api/orgs/{team['id']}", headers=admin).status_code == 409   # 하위 부서 있음
    assert client.delete(f"/api/orgs/{orgs['안전팀']['id']}", headers=admin).status_code == 409  # 소속 회원 있음
    assert client.delete(f"/api/orgs/{sub['id']}", headers=admin).status_code == 204
    assert client.patch(f"/api/orgs/{prime['id']}", json={"parent_id": team["id"]}, headers=admin).status_code == 422


def test_org_write_is_admin_only(client, manager):
    assert client.post("/api/orgs", json={"type": "COMPANY", "name": "x"}, headers=manager).status_code == 403


# ---------------------------------------------------------------- 판정 기준 · 심각도 기준
def test_rule_update_and_reset(client, admin, ingest):
    types = {t["code"]: t for t in client.get("/api/detection-types", headers=admin).json()}
    helmet = types["NO_HELMET"]
    res = client.patch(f"/api/detection-types/{helmet['id']}/rule",
                       json={"min_confidence": 0.65, "cooldown_sec": 300, "default_severity": "HIGH"}, headers=admin).json()
    assert (res["min_confidence"], res["cooldown_sec"], res["default_severity"]) == (0.65, 300, "HIGH")

    # 끄면 이벤트를 만들지 않음
    client.patch(f"/api/detection-types/{helmet['id']}/rule", json={"is_active": False}, headers=admin)
    res = client.post("/api/events", json={"detection_type": "NO_HELMET", "confidence": 0.99}, headers=ingest).json()
    assert res["created"] is False and "사용 안 함" in res["reason"]

    reset = {t["code"]: t for t in client.post("/api/detection-types/reset-rules", headers=admin).json()}
    assert (reset["NO_HELMET"]["min_confidence"], reset["NO_HELMET"]["is_active"]) == (0.8, True)
    assert reset["NO_HELMET"]["default_severity"] == "MEDIUM"


def test_rule_update_is_admin_only(client, manager):
    t = client.get("/api/detection-types", headers=manager).json()[0]
    assert client.patch(f"/api/detection-types/{t['id']}/rule", json={"is_active": False}, headers=manager).status_code == 403
