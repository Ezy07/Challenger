"""ROI 그리기 · ROI 목록 화면이 그린 감지 구역 (storage/roi-zones.json).

구역은 카메라 영상의 프레임마다 모양이 바뀔 수 있어(키프레임) DB 의 roi 테이블과 모양이 달라서,
화면이 만든 줄 목록을 그대로 JSON 파일 하나에 저장한다. AI 탐지 프로그램도 이 파일을 읽으면 된다.
한 줄 = 카메라 하나 · 구역 번호 하나 · 그 모양이 시작되는 프레임 하나.
"""

import json
import os
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import settings
from ..deps import CurrentUser, Manager

router = APIRouter(prefix="/api/roi-zones", tags=["ROI 구역"])

Day = Literal["월", "화", "수", "목", "금", "토", "일"]
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
    kind: Literal["위험구역", "통제구역", "관리구역", "안전구역"]
    frame: int = Field(ge=1)                                 # 이 모양이 시작되는 프레임 (1부터)
    time: float | None = Field(default=None, ge=0)           # 그 프레임의 영상 시각(초)
    points: list[list[float]] = Field(min_length=3, max_length=100)  # 화면 좌표 (가로 0~1000, 세로 0~600)
    enabled: bool = True
    schedule: Schedule | None = None


def check_points(rows: list[RoiZoneRow]) -> None:
    for r in rows:
        if any(len(p) != 2 or not (0 <= p[0] <= 1000 and 0 <= p[1] <= 600) for p in r.points):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{r.camera} {r.no}번 구역의 점이 화면 밖에 있습니다.")


@router.get("", response_model=list[RoiZoneRow])
def read_zones(_: CurrentUser):
    path = settings.roi_zones_file
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


@router.put("", response_model=list[RoiZoneRow])
def save_zones(rows: list[RoiZoneRow], _: Manager):
    """구역 전체를 이 목록으로 바꾼다 (화면이 늘 전체를 보낸다)"""
    if len(rows) > 5000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "구역이 너무 많습니다 (5000줄까지).")
    check_points(rows)
    rows = sorted(rows, key=lambda r: (r.camera, r.no, r.frame))
    path = settings.roi_zones_file
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")  # 쓰다가 멈춰도 원래 파일이 깨지지 않게 바꿔치기
    tmp.write_text(json.dumps([r.model_dump(exclude_none=True) for r in rows], ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return rows
