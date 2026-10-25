import io

import pytest
from PIL import Image

from app.config import settings


@pytest.fixture(autouse=True)
def photo_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "photo_dir", tmp_path / "photos")
    return tmp_path / "photos"


def jpeg(w=1600, h=1200, gps=True) -> bytes:
    img = Image.new("RGB", (w, h), (200, 80, 40))
    exif = Image.Exif()
    if gps:
        exif[0x8825] = {1: "N", 2: (37.0, 30.0, 0.0)}  # 촬영 위치 (GPS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def me(client, headers):
    return client.get("/api/auth/me", headers=headers).json()


def test_user_uploads_own_photo_resized_without_gps(client, manager, photo_dir):
    uid = me(client, manager)["id"]
    res = client.put(f"/api/users/{uid}/photo", content=jpeg(), headers={**manager, "Content-Type": "image/jpeg"})
    assert res.status_code == 200
    url = res.json()["photo_url"]
    assert url.startswith(f"/api/users/{uid}/photo?v=") and me(client, manager)["photo_url"] == url

    with Image.open(next(photo_dir.glob("users/*.jpg"))) as saved:
        assert max(saved.size) == 640              # 긴 변 640 으로 줄임
        assert 0x8825 not in saved.getexif()       # 촬영 위치는 지움

    token = manager["Authorization"].split()[1]
    assert client.get(url + "&token=" + token).headers["content-type"] == "image/jpeg"  # <img> 는 ?token= 으로
    assert client.get(url).status_code == 401      # 로그인 없이는 못 봄

    # 바꾸면 예전 파일은 지운다
    client.put(f"/api/users/{uid}/photo", content=jpeg(gps=False), headers={**manager, "Content-Type": "image/jpeg"})
    assert len(list(photo_dir.glob("users/*.jpg"))) == 1
    assert client.delete(f"/api/users/{uid}/photo", headers=manager).status_code == 204
    assert me(client, manager)["photo_url"] is None and not list(photo_dir.glob("users/*.jpg"))


def test_only_self_or_admin_changes_user_photo(client, admin, manager):
    admin_id = me(client, admin)["id"]
    manager_id = me(client, manager)["id"]
    body = {"content": jpeg(), "headers": {"Content-Type": "image/jpeg"}}
    assert client.put(f"/api/users/{admin_id}/photo", content=body["content"], headers={**manager, **body["headers"]}).status_code == 403
    assert client.put(f"/api/users/{manager_id}/photo", content=body["content"], headers={**admin, **body["headers"]}).status_code == 200
    listed = {u["id"]: u for u in client.get("/api/users", headers=admin).json()}
    assert listed[manager_id]["photo_url"]


def test_worker_photo_by_manager_and_bad_file(client, manager):
    w = client.get("/api/workers", headers=manager).json()[0]
    assert client.put(f"/api/workers/{w['id']}/photo", content=b"not an image", headers={**manager, "Content-Type": "image/jpeg"}).status_code == 415
    res = client.put(f"/api/workers/{w['id']}/photo", content=jpeg(300, 400), headers={**manager, "Content-Type": "image/jpeg"})
    assert res.status_code == 200
    again = client.get(f"/api/workers/{w['id']}", headers=manager).json()
    assert again["photo_url"] == res.json()["photo_url"]
    assert client.get(again["photo_url"], headers=manager).status_code == 200
    assert client.get("/api/workers/999999/photo", headers=manager).status_code == 404


def test_demo_worker_photos_fill_only_missing(client, manager, db_session, photo_dir):
    from app.seed import seed_worker_photos

    with db_session() as db:
        made = seed_worker_photos(db)
        db.commit()
        assert made > 0 and seed_worker_photos(db) == 0  # 이미 사진이 있으면 건너뜀
    workers = client.get("/api/workers", headers=manager).json()
    assert all(w["photo_url"] for w in workers)
    assert client.get(workers[0]["photo_url"], headers=manager).headers["content-type"] == "image/jpeg"
