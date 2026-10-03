def test_list_cameras_by_page(client, manager):
    page1 = client.get("/api/cameras", params={"view_page": 1}, headers=manager).json()
    assert [c["name"] for c in page1] == ["CAM_0001", "CAM_0002", "CAM_0003", "CAM_0004"]
    assert page1[0]["work_zone_name"] == "101동 갱폼 인양구역"


def test_slot_conflict(client, admin):
    res = client.post("/api/cameras", json={"name": "CAM_0005", "view_page": 1, "view_slot": 1}, headers=admin)
    assert res.status_code == 409


def test_tc_camera_needs_tc_equipment(client, admin):
    res = client.post("/api/cameras", json={"name": "TC9_CAM", "camera_type": "TC", "view_page": 2}, headers=admin)
    assert res.status_code == 422


def test_create_update_delete(client, admin):
    cam = client.post("/api/cameras", json={"name": "CAM_0009", "view_page": 1}, headers=admin).json()
    res = client.patch(f"/api/cameras/{cam['id']}", json={"location_desc": "북측 가설울타리"}, headers=admin)
    assert res.json()["location_desc"] == "북측 가설울타리"
    assert client.delete(f"/api/cameras/{cam['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/cameras/{cam['id']}", headers=admin).status_code == 404


def test_camera_with_events_cannot_be_deleted(client, admin):
    cam1 = client.get("/api/cameras", headers=admin).json()[0]
    assert client.delete(f"/api/cameras/{cam1['id']}", headers=admin).status_code == 409


def test_screen_files_are_revalidated(client):
    """common.js 를 고치면 브라우저가 바로 새 파일을 받아야 한다 (예전 파일 캐시 금지)"""
    res = client.get("/common.js")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-cache"
    again = client.get("/common.js", headers={"If-None-Match": res.headers["etag"]})
    assert again.status_code == 304
