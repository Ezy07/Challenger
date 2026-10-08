import json
from datetime import datetime

import pytest

from app.clock import KST
from app.config import settings
from app.routers.roi_zones import Schedule, in_schedule

from .conftest import DEMO_PASSWORD, login

ROW = {"camera": "CAM_0001", "cameraName": "101동 갱폼 인양구역", "file": "Main_Cam_0001.mp4", "no": 1, "kind": "위험구역",
       "frame": 1, "time": 0.02, "points": [[100, 100], [300, 100], [300, 300]], "enabled": True}


@pytest.fixture(autouse=True)
def zones_file(tmp_path, monkeypatch):
    path = tmp_path / "roi-zones.json"
    monkeypatch.setattr(settings, "roi_zones_file", path)
    return path


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch):
    """2026-10-04 일요일 낮. 월·화·수 스케줄은 이 시각에 꺼져 있어서 저장한 사용 여부가 유지된다."""
    monkeypatch.setattr("app.routers.roi_zones.now_kst", lambda: (datetime(2026, 10, 4, 12, 0, tzinfo=KST), "local"))


def test_roi_zones_save_and_read(client, manager, zones_file):
    assert client.get("/api/roi-zones", headers=manager).json() == []
    later = {**ROW, "frame": 120, "points": [[110, 100], [310, 100], [310, 320], [110, 320]]}
    sched = {**ROW, "camera": "CAM_0002", "no": 2, "kind": "통제구역", "enabled": False,
             "schedule": {"on": True, "start": "07:00", "end": "18:30", "days": ["월", "화", "수"]}}
    res = client.put("/api/roi-zones", json=[sched, later, ROW], headers=manager)
    assert res.status_code == 200, res.text
    saved = client.get("/api/roi-zones", headers=manager).json()
    assert [(r["camera"], r["no"], r["frame"]) for r in saved] == [("CAM_0001", 1, 1), ("CAM_0001", 1, 120), ("CAM_0002", 2, 1)]
    assert saved[2]["schedule"]["days"] == ["월", "화", "수"] and saved[2]["enabled"] is False
    assert json.loads(zones_file.read_text(encoding="utf-8"))[0]["kind"] == "위험구역"  # AI 프로그램이 읽는 파일

    # 전체 바꾸기: 빈 목록이면 모두 지워진다
    assert client.put("/api/roi-zones", json=[], headers=manager).json() == []
    assert client.get("/api/roi-zones", headers=manager).json() == []


def test_roi_zones_validation(client, manager):
    bad = [
        {**ROW, "points": [[100, 100], [200, 200]]},           # 점 2개
        {**ROW, "points": [[100, 100], [1200, 100], [300, 300]]},  # 화면 밖
        {**ROW, "kind": "아무구역"},
        {**ROW, "no": 0},
        {**ROW, "schedule": {"on": True, "start": "25:00", "end": "18:00", "days": []}},
        {**ROW, "dwell": -1},
    ]
    for row in bad:
        assert client.put("/api/roi-zones", json=[row], headers=manager).status_code == 422, row


def test_dwell_seconds_round_trip(client, manager):
    saved = client.put("/api/roi-zones", json=[{**ROW, "dwell": 0}], headers=manager).json()
    assert saved[0]["dwell"] == 0
    again = client.put("/api/roi-zones", json=[{**ROW, "dwell": 12}], headers=manager).json()
    assert again[0]["dwell"] == 12
    assert client.get("/api/roi-zones", headers=manager).json()[0]["dwell"] == 12
    muted = client.put("/api/roi-zones", json=[{**ROW, "dwell": 0, "intrusion": False}], headers=manager).json()
    assert muted[0]["intrusion"] is False


def test_targets_round_trip(client, manager):
    saved = client.put("/api/roi-zones", json=[{**ROW, "targets": ["truck", "person", "person"]}], headers=manager).json()
    assert saved[0]["targets"] == ["truck", "person"]
    assert client.get("/api/roi-zones", headers=manager).json()[0]["targets"] == ["truck", "person"]
    empty = client.put("/api/roi-zones", json=[{**ROW, "targets": []}], headers=manager).json()
    assert empty[0]["targets"] == []
    assert client.put("/api/roi-zones", json=[{**ROW, "targets": ["bus"]}], headers=manager).status_code == 422


def test_schedule_toggles_enabled(client, manager, monkeypatch):
    def at(moment):
        monkeypatch.setattr("app.routers.roi_zones.now_kst", lambda: (moment, "local"))

    row = {**ROW, "enabled": False, "schedule": {"on": True, "start": "07:00", "end": "18:30", "days": ["수"]}}
    at(datetime(2026, 10, 7, 10, 0, tzinfo=KST))  # 수요일 오전, 적용 시간 안
    saved = client.put("/api/roi-zones", json=[row], headers=manager).json()
    assert saved[0]["enabled"] is True

    at(datetime(2026, 10, 7, 19, 0, tzinfo=KST))  # 같은 날 저녁, 적용 시간 밖
    assert client.get("/api/roi-zones", headers=manager).json()[0]["enabled"] is False

    at(datetime(2026, 10, 7, 10, 0, tzinfo=KST))
    manual = {**ROW, "enabled": False, "schedule": {"on": False, "start": "07:00", "end": "18:30", "days": ["수"]}}
    assert client.put("/api/roi-zones", json=[manual], headers=manager).json()[0]["enabled"] is False


def test_in_schedule_spans_midnight():
    plan = Schedule(on=True, start="22:00", end="06:00", days=["화", "수"])
    assert in_schedule(plan, datetime(2026, 10, 6, 23, 0, tzinfo=KST))
    assert in_schedule(plan, datetime(2026, 10, 7, 5, 30, tzinfo=KST))
    assert not in_schedule(plan, datetime(2026, 10, 7, 12, 0, tzinfo=KST))


def test_roi_zones_viewer_reads_only(client, admin, manager):
    client.put("/api/roi-zones", json=[ROW], headers=manager)
    uid = next(u["id"] for u in client.get("/api/users", headers=admin).json() if u["login_id"] == "yoon.gr")
    client.patch(f"/api/users/{uid}", json={"status": "ACTIVE"}, headers=admin)  # 시연 데이터에서 잠겨 있는 조회 전용
    viewer = login(client, "yoon.gr", DEMO_PASSWORD)
    assert len(client.get("/api/roi-zones", headers=viewer).json()) == 1
    assert client.put("/api/roi-zones", json=[], headers=viewer).status_code == 403
    assert client.get("/api/roi-zones").status_code == 401
