import pytest

from app import vision
from app.config import settings


@pytest.fixture
def yolo_off(monkeypatch):
    """테스트는 모델을 내려받지 않도록 YOLO 를 끈 상태로 돈다"""
    monkeypatch.setattr(settings, "yolo_enabled", False)
    monkeypatch.setattr(vision, "detector", vision.Detector())


def test_status_says_why_when_off(client, admin, yolo_off):
    res = client.get("/api/stream/status", headers=admin)
    assert res.status_code == 200
    body = res.json()
    assert body["enabled"] is False and "YOLO_ENABLED" in body["reason"]


def test_stream_needs_login(client, admin, yolo_off):
    cam = client.get("/api/cameras", headers=admin).json()[0]
    assert client.get(f"/api/stream/{cam['id']}.mjpg").status_code == 401
    assert client.get(f"/api/stream/{cam['id']}.mjpg?token=wrong").status_code == 401


def test_stream_off_returns_503_with_token_in_query(client, admin, yolo_off, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "video_dir", tmp_path)
    (tmp_path / "a.mp4").write_bytes(b"0")
    cam = client.post("/api/cameras", headers=admin, json={"name": "CAM_T", "stream_url": "videos/a.mp4"}).json()
    token = admin["Authorization"].split()[1]
    res = client.get(f"/api/stream/{cam['id']}.mjpg?token={token}")
    assert res.status_code == 503
    assert "YOLO_ENABLED" in res.json()["detail"]


def test_stream_without_source_is_404(client, admin, yolo_off):
    cam = client.post("/api/cameras", headers=admin, json={"name": "CAM_NONE"}).json()
    res = client.get(f"/api/stream/{cam['id']}.mjpg", headers=admin)
    assert res.status_code == 404


def test_rois_at_follows_keyframes_and_enabled():
    sq = [[0, 0], [10, 0], [10, 10]]
    moved = [[100, 100], [110, 100], [110, 110]]
    rows = [
        {"camera": "CAM_A", "no": 1, "name": "크레인 하부", "kind": "위험구역", "frame": 1, "time": 0.0, "points": sq},
        {"camera": "CAM_A", "no": 1, "name": "크레인 하부", "kind": "위험구역", "frame": 61, "time": 2.0, "points": moved},
        {"camera": "CAM_A", "no": 2, "kind": "안전구역", "frame": 1, "points": sq, "enabled": False},  # 꺼진 구역
        {"camera": "CAM_A", "no": 3, "kind": "관리구역", "frame": 31, "points": moved},  # time 없으면 30fps 로 계산
        {"camera": "CAM_B", "no": 1, "kind": "관리구역", "frame": 1, "points": sq},  # 다른 카메라
    ]
    # 이름이 없는 예전 구역은 등급으로 부른다
    assert vision.rois_at(rows, "CAM_A", 0.5) == [(1, "위험구역", sq, "크레인 하부"), (3, "관리구역", moved, "관리구역")]
    assert vision.rois_at(rows, "CAM_A", 2.5) == [(1, "위험구역", moved, "크레인 하부"), (3, "관리구역", moved, "관리구역")]
    assert vision.rois_at(rows, "CAM_B", 0) == [(1, "관리구역", sq, "관리구역")]
