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


def test_video_files_list_and_camera_link(client, admin, tmp_path, monkeypatch):
    """storage/videos 의 영상을 카메라 영상 소스로 고를 수 있다"""
    from app.config import settings

    monkeypatch.setattr(settings, "video_dir", tmp_path)
    (tmp_path / "factory.mp4").write_bytes(b"\x00" * 64 + b"ftypisom....moov....avc1" + b"\x00" * 64)
    (tmp_path / "cctv.mp4").write_bytes(b"\x00" * 64 + b"ftypisom....moov....hvc1" + b"\x00" * 64)
    (tmp_path / "notes.txt").write_text("not a video")

    videos = {v["name"]: v for v in client.get("/api/videos", headers=admin).json()}
    assert set(videos) == {"cctv.mp4", "factory.mp4"}
    assert (videos["factory.mp4"]["codec"], videos["factory.mp4"]["browser_ok"]) == ("H.264", True)
    assert (videos["cctv.mp4"]["codec"], videos["cctv.mp4"]["browser_ok"]) == ("H.265", False)
    assert videos["factory.mp4"]["stream_url"] == "videos/factory.mp4"

    cam = client.get("/api/cameras", headers=admin).json()[0]
    res = client.patch(f"/api/cameras/{cam['id']}", json={"stream_url": "videos/factory.mp4"}, headers=admin)
    assert res.status_code == 200 and res.json()["stream_url"] == "videos/factory.mp4"
    # 없는 파일 · 폴더 밖으로 나가는 경로는 막음
    for bad in ("videos/none.mp4", "videos/../.env", "videos/sub/x.mp4"):
        assert client.patch(f"/api/cameras/{cam['id']}", json={"stream_url": bad}, headers=admin).status_code == 422
    # 연결한 뒤에 파일이 지워져도, 영상 소스가 아닌 값(배치도 위치 · 색)은 바꿀 수 있다
    (tmp_path / "factory.mp4").unlink()
    moved = client.patch(f"/api/cameras/{cam['id']}", json={"plan_x": 0.3, "plan_y": 0.3, "plan_color": "#3ddc84"}, headers=admin)
    assert moved.status_code == 200 and moved.json()["stream_url"] == "videos/factory.mp4"
    # RTSP 주소는 그대로 저장
    rtsp = client.patch(f"/api/cameras/{cam['id']}", json={"stream_url": "rtsp://10.0.0.5:554/s1"}, headers=admin)
    assert rtsp.status_code == 200
