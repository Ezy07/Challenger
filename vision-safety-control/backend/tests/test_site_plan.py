import struct
import zlib

import pytest

from app.config import settings
from app.routers.site_plan import image_size

from .conftest import DEMO_PASSWORD, login


def png(width: int, height: int) -> bytes:
    """크기만 맞는 아주 작은 PNG (한 줄짜리 흰 그림)"""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def jpeg(width: int, height: int) -> bytes:
    """SOF0 까지만 있는 JPEG 머리 (크기 읽기 확인용)"""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


@pytest.fixture(autouse=True)
def plan_dir(tmp_path, monkeypatch):
    path = tmp_path / "plans"
    monkeypatch.setattr(settings, "plan_dir", path)
    return path


def upload(client, headers, data, **params):
    return client.put("/api/site-plan", content=data, params=params, headers={**headers, "Content-Type": "image/png"})


def test_image_size_reads_png_and_jpeg():
    assert image_size(png(40, 24)) == ("png", 40, 24)
    assert image_size(jpeg(1920, 1080)) == ("jpeg", 1920, 1080)
    assert image_size(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert image_size(b"%PDF-1.7") is None


def test_plan_crud(client, admin, plan_dir):
    assert client.get("/api/site-plan", headers=admin).json() is None

    first = upload(client, admin, png(40, 24), filename="C:\\도면\\현장.png", title="OO단지 배치도")
    assert first.status_code == 200, first.text
    body = first.json()
    assert (body["title"], body["width"], body["height"], body["original_name"]) == ("OO단지 배치도", 40, 24, "현장.png")
    assert body["url"].startswith("/plans/site-plan-") and body["uploaded_by_name"] == "admin.test"
    assert len(list(plan_dir.iterdir())) == 1

    # 바꾸기: 새 파일로 바뀌고 예전 파일은 지워진다. 이름은 그대로
    second = upload(client, admin, png(30, 30)).json()
    assert (second["title"], second["width"]) == ("OO단지 배치도", 30)
    files = list(plan_dir.iterdir())
    assert len(files) == 1 and second["url"].split("?")[0].endswith(files[0].name)

    assert client.patch("/api/site-plan", json={"title": "1공구 도면"}, headers=admin).json()["title"] == "1공구 도면"
    assert client.get("/api/site-plan", headers=admin).json()["title"] == "1공구 도면"

    assert client.delete("/api/site-plan", headers=admin).status_code == 204
    assert client.get("/api/site-plan", headers=admin).json() is None
    assert list(plan_dir.iterdir()) == []
    assert client.delete("/api/site-plan", headers=admin).status_code == 404
    assert client.patch("/api/site-plan", json={"title": "x"}, headers=admin).status_code == 404


def test_plan_rejects_non_images_and_big_files(client, admin, monkeypatch):
    assert upload(client, admin, b"<svg/>").status_code == 415
    assert upload(client, admin, b"%PDF-1.7 ...").status_code == 415
    monkeypatch.setattr(settings, "max_plan_mb", 0)
    assert upload(client, admin, png(4, 4)).status_code == 413


def test_only_admin_changes_plan(client, admin, manager):
    upload(client, admin, png(10, 10))
    demo_manager = login(client, "oh.sy", DEMO_PASSWORD)  # 시연 데이터의 안전관리자
    for headers in (manager, demo_manager):
        assert client.get("/api/site-plan", headers=headers).json()["width"] == 10  # 보기는 누구나
        assert upload(client, headers, png(10, 10)).status_code == 403
        assert client.patch("/api/site-plan", json={"title": "x"}, headers=headers).status_code == 403
        assert client.delete("/api/site-plan", headers=headers).status_code == 403
    assert client.get("/api/site-plan").status_code == 401


def test_camera_plan_position(client, admin, manager):
    cams = client.get("/api/cameras", headers=manager).json()
    cam = next(c for c in cams if c["name"] == "CAM_0001")
    assert cam["plan_x"] is not None and cam["plan_dir"] == 0  # 시연 데이터에 위치가 들어 있음

    res = client.patch(f"/api/cameras/{cam['id']}", json={"plan_x": 0.25, "plan_y": 0.5, "plan_dir": 270}, headers=admin).json()
    assert (res["plan_x"], res["plan_y"], res["plan_dir"]) == (0.25, 0.5, 270)
    assert client.patch(f"/api/cameras/{cam['id']}", json={"plan_x": 1.2}, headers=admin).status_code == 422
    assert client.patch(f"/api/cameras/{cam['id']}", json={"plan_dir": 360}, headers=admin).status_code == 422
    assert client.patch(f"/api/cameras/{cam['id']}", json={"plan_x": 0.1}, headers=manager).status_code == 403

    off = client.patch(f"/api/cameras/{cam['id']}", json={"plan_x": None, "plan_y": None, "plan_dir": None}, headers=admin).json()
    assert (off["plan_x"], off["plan_y"], off["plan_dir"]) == (None, None, None)


def test_camera_plan_color(client, admin):
    cam = next(c for c in client.get("/api/cameras", headers=admin).json() if c["name"] == "CAM_0001")
    assert cam["plan_color"] is None  # 기본색
    assert client.patch(f"/api/cameras/{cam['id']}", json={"plan_color": "#3DDC84"}, headers=admin).json()["plan_color"] == "#3DDC84"
    for bad in ("red", "#12345", "#gggggg", "3ddc84"):
        assert client.patch(f"/api/cameras/{cam['id']}", json={"plan_color": bad}, headers=admin).status_code == 422, bad
    assert client.patch(f"/api/cameras/{cam['id']}", json={"plan_color": None}, headers=admin).json()["plan_color"] is None


def test_camera_plan_fov_range(client, admin):
    cam = next(c for c in client.get("/api/cameras", headers=admin).json() if c["name"] == "CAM_0001")
    assert (cam["plan_fov"], cam["plan_range"]) == (None, None)  # 기본 부채꼴
    res = client.patch(f"/api/cameras/{cam['id']}", json={"plan_fov": 360, "plan_range": 250}, headers=admin).json()
    assert (res["plan_fov"], res["plan_range"]) == (360, 250)  # 회전 카메라는 원
    for bad in ({"plan_fov": 5}, {"plan_fov": 361}, {"plan_range": 10}, {"plan_range": 600}):
        assert client.patch(f"/api/cameras/{cam['id']}", json=bad, headers=admin).status_code == 422, bad
    res = client.patch(f"/api/cameras/{cam['id']}", json={"plan_fov": None, "plan_range": None}, headers=admin).json()
    assert (res["plan_fov"], res["plan_range"]) == (None, None)
