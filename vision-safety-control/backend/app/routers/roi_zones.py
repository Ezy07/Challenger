"""ROI 그리기 · ROI 목록 화면이 그린 감지 구역 (storage/roi-zones.json).

구역은 카메라 영상의 프레임마다 모양이 바뀔 수 있어(키프레임) DB 의 roi 테이블과 모양이 달라서,
화면이 만든 줄 목록을 그대로 JSON 파일 하나에 저장한다. AI 탐지 프로그램도 이 파일을 읽으면 된다.
한 줄 = 카메라 하나 · 구역 번호 하나 · 그 모양이 시작되는 프레임 하나.
"""

import json
import os
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from ..clock import now_kst
from ..config import settings
from ..deps import Admin, CurrentUser

router = APIRouter(prefix="/api/roi-zones", tags=["ROI 구역"])

Day = Literal["월", "화", "수", "목", "금", "토", "일"]
TargetClass = Literal["person", "truck", "excavator", "forklift"]  # 침입 탐지 대상 (frontend/roi-store.js 의 ROI_TARGETS 와 같게)
HHMM = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class Schedule(BaseModel):
    on: bool = True
    start: str = HHMM
    end: str = HHMM
    days: list[Day] = Field(default_factory=list, max_length=7)


class RoiZoneRow(BaseModel):
    camera: str = Field(min_length=1, max_length=100)        # 카메라 이름 (CAM_0001)
    cameraName: str | None = Field(default=None, max_length=200)  # 구역 · 위치 설명 (보기용)
    file: str | None = Field(default=None, max_length=255)   # 그린 영상 파일 (storage/videos)
    no: int = Field(ge=1, le=999)                            # 카메라 안에서의 구역 번호
    name: str | None = Field(default=None, max_length=40)    # 구역 이름 (타워크레인 하부 등). 없으면 등급으로 부름
    kind: Literal["위험구역", "통제구역", "관리구역", "안전구역"]  # 등급 (겹치면 위험 > 통제 > 관리 > 안전)
    frame: int = Field(ge=1)                                 # 이 모양이 시작되는 프레임 (1부터)
    time: float | None = Field(default=None, ge=0)           # 그 프레임의 영상 시각(초)
    points: list[list[float]] = Field(min_length=3, max_length=100)  # 화면 좌표 (가로 0~1000, 세로 0~600)
    enabled: bool = True
    dwell: int | None = Field(default=None, ge=0, le=24 * 60 * 60)  # 작업자가 이 초 이상 머무르면 경고. 저장 전이면 없음
    intrusion: bool | None = None  # false 면 침입 알림을 띄우지 않음 (체류 시간의 사용안함)
    targets: list[TargetClass] | None = Field(default=None, max_length=8)  # 이 구역에서 침입으로 볼 대상. 여러 개 가능
    schedule: Schedule | None = None
    # 목록의 붉은 점은 세 저장 버튼을 모두 눌렀을 때만 지운다. 값만 있고 저장을 안 누른 경우는 남긴다
    savedSchedule: bool | None = None
    savedDwell: bool | None = None
    savedTargets: bool | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str | None) -> str | None:
        value = " ".join(value.split()) if value else ""
        return value or None

    @field_validator("targets")
    @classmethod
    def unique_targets(cls, value: list[TargetClass] | None) -> list[TargetClass] | None:
        if value is None:
            return None
        seen: list[TargetClass] = []
        for item in value:
            if item not in seen:
                seen.append(item)
        return seen


def check_points(rows: list[RoiZoneRow]) -> None:
    for r in rows:
        if any(len(p) != 2 or not (0 <= p[0] <= 1000 and 0 <= p[1] <= 600) for p in r.points):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{r.camera} {r.no}번 구역의 점이 화면 밖에 있습니다.")


_WEEK = ("월", "화", "수", "목", "금", "토", "일")  # datetime.weekday(): 월요일 = 0


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def in_schedule(plan: Schedule, now: datetime) -> bool:
    """적용 시간이 켜져 있을 때, now(한국 시각)가 그 요일 · 시간 안인지."""
    if _WEEK[now.weekday()] not in plan.days:
        return False
    start, end = _minutes(plan.start), _minutes(plan.end)
    cur = now.hour * 60 + now.minute
    if start <= end:
        return start <= cur <= end
    return cur >= start or cur <= end  # 밤을 넘기는 구간 (22:00~06:00)


def sync_models(rows: list[RoiZoneRow], now: datetime) -> bool:
    """적용 시간이 켜진 구역의 사용 여부를 시각에 맞춘다. 항상(on 이 꺼짐)은 그대로 둔다."""
    changed = False
    for row in rows:
        if row.schedule is None or not row.schedule.on:
            continue
        active = in_schedule(row.schedule, now)
        if row.enabled != active:
            row.enabled = active
            changed = True
    return changed


def sync_raw(rows: list, now: datetime) -> bool:
    """파일에 있는 줄(dict)을 같은 규칙으로 고친다. 형식이 이상한 줄은 건너뛴다."""
    changed = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        sched = row.get("schedule")
        if not isinstance(sched, dict) or not sched.get("on", True):
            continue
        try:
            plan = Schedule.model_validate(sched)
        except Exception:
            continue
        active = in_schedule(plan, now)
        if bool(row.get("enabled", True)) != active:
            row["enabled"] = active
            changed = True
    return changed


def _write_raw(rows: list) -> None:
    path = settings.roi_zones_file
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")  # 쓰다가 멈춰도 원래 파일이 깨지지 않게 바꿔치기
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def sync_stored_zones() -> bool:
    """저장 파일을 인터넷(또는 PC) 한국 시각에 맞춘다. 바꿀 게 없으면 파일을 건드리지 않는다."""
    path = settings.roi_zones_file
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return False
    now, _source = now_kst()
    if not sync_raw(data, now):
        return False
    _write_raw(data)
    return True


@router.get("", response_model=list[RoiZoneRow])
def read_zones(_: CurrentUser):
    path = settings.roi_zones_file
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        now, _source = now_kst()
        if sync_raw(data, now):
            _write_raw(data)
    return data


@router.put("", response_model=list[RoiZoneRow])
def save_zones(rows: list[RoiZoneRow], _: Admin):  # ROI 는 관리자 전용 (5-1 · 5-2)
    """구역 전체를 이 목록으로 바꾼다 (화면이 늘 전체를 보낸다)"""
    if len(rows) > 5000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "구역이 너무 많습니다 (5000줄까지).")
    check_points(rows)
    rows = sorted(rows, key=lambda r: (r.camera, r.no, r.frame))
    now, _source = now_kst()
    sync_models(rows, now)
    _write_raw([r.model_dump(exclude_none=True) for r in rows])
    return rows
