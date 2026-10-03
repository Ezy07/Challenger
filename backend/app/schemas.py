"""API 요청 · 응답 형식"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import ActionType, CameraType, EventStatus, OrgType, Role, Severity, UserStatus


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- 조직
class OrgOut(Out):
    id: int
    parent_id: int | None
    type: OrgType
    name: str
    is_prime: bool


class OrgIn(BaseModel):
    parent_id: int | None = None
    type: OrgType
    name: str = Field(min_length=1, max_length=100)
    is_prime: bool = False


# ---------------------------------------------------------------- 회원
class SignupIn(BaseModel):
    login_id: str = Field(pattern=r"^[a-z0-9.]{4,20}$")
    password: str = Field(min_length=8, max_length=72)
    name: str = Field(min_length=1, max_length=50)
    position: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=20)
    org_id: int | None = None
    role: Literal[Role.MANAGER, Role.VIEWER] = Role.VIEWER  # 관리자 권한은 가입으로 받을 수 없음


class LoginIn(BaseModel):
    login_id: str
    password: str


class UserOut(Out):
    id: int
    login_id: str
    name: str
    position: str | None
    phone: str | None
    org_id: int | None
    role: Role
    status: UserStatus
    approved_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserUpdate(BaseModel):
    """회원정보 수정 (관리자). 보낸 값만 바꾼다."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    position: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=20)
    org_id: int | None = None
    role: Role | None = None
    status: UserStatus | None = None


# ---------------------------------------------------------------- 구역 · 카메라
class WorkZoneOut(Out):
    id: int
    name: str
    plan_polygon: list | None


class CameraIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    work_zone_id: int | None = None
    equipment_id: int | None = None
    camera_type: CameraType = CameraType.FIXED
    view_page: int = Field(default=1, ge=1, le=2)
    view_slot: int | None = Field(default=None, ge=1, le=4)
    stream_url: str | None = Field(default=None, max_length=500)
    location_desc: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    work_zone_id: int | None = None
    equipment_id: int | None = None
    camera_type: CameraType | None = None
    view_page: int | None = Field(default=None, ge=1, le=2)
    view_slot: int | None = Field(default=None, ge=1, le=4)
    stream_url: str | None = Field(default=None, max_length=500)
    location_desc: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class CameraOut(Out):
    id: int
    name: str
    work_zone_id: int | None
    work_zone_name: str | None = None
    equipment_id: int | None
    camera_type: CameraType
    view_page: int
    view_slot: int | None
    stream_url: str | None
    location_desc: str | None
    is_active: bool


# ---------------------------------------------------------------- 감지 유형
class CheckItemOut(Out):
    id: int
    title: str
    sort_order: int


class DetectionTypeOut(Out):
    id: int
    code: str
    label: str
    min_confidence: float | None = None
    default_severity: Severity | None = None
    cooldown_sec: int | None = None


# ---------------------------------------------------------------- 이벤트
class EventIn(BaseModel):
    """AI 탐지 프로그램이 올리는 감지 결과. 규칙을 통과해야 이벤트가 된다."""

    detection_type: str  # detection_type.code
    camera_id: int | None = None
    roi_id: int | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    detected_at: datetime | None = None  # 비우면 서버 시각
    snapshot_path: str | None = Field(default=None, max_length=500)


class EventIngestOut(BaseModel):
    created: bool
    event_id: int | None = None
    reason: str | None = None  # 만들지 않은 이유 (기준 미달 · 쿨다운)


class EventRow(BaseModel):
    id: int
    detected_at: datetime
    camera_name: str | None
    work_zone_name: str | None
    detection_code: str
    detection_label: str
    severity: Severity
    confidence: float | None
    status: EventStatus


class EventPage(BaseModel):
    total: int
    page: int
    size: int
    items: list[EventRow]


class ActionIn(BaseModel):
    action_type: ActionType
    check_item_id: int | None = None
    memo: str | None = Field(default=None, max_length=1000)


class ActionOut(Out):
    id: int
    action_type: ActionType
    check_item_id: int | None
    memo: str | None
    user_name: str
    created_at: datetime


class CheckItemState(BaseModel):
    id: int
    title: str
    permitted: bool


class EventDetail(EventRow):
    camera_id: int | None
    roi_id: int | None
    roi_name: str | None
    bbox: list | None
    snapshots: list[str]
    check_items: list[CheckItemState]
    actions: list[ActionOut]
