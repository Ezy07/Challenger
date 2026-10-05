"""API 요청 · 응답 형식"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    ActionType,
    CameraType,
    EduType,
    EquipStatus,
    EquipType,
    EventStatus,
    OrgType,
    Role,
    Severity,
    SpecialReason,
    UserStatus,
    WorkStatus,
)


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


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    parent_id: int | None = None


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
    approved_by: int | None
    approved_at: datetime | None
    failed_login_count: int
    last_login_at: datetime | None
    created_at: datetime


class StaffOut(Out):
    """담당자 고르기용 (로그인한 누구나 볼 수 있게 이름 · 직급만)"""

    id: int
    name: str
    position: str | None
    role: Role


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    """관리자가 직접 등록. 승인 없이 바로 활성이고, 첫 비밀번호는 서버가 만들어 한 번만 알려 준다."""

    login_id: str = Field(pattern=r"^[a-z0-9.]{4,20}$")
    name: str = Field(min_length=1, max_length=50)
    position: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=20)
    org_id: int | None = None
    role: Role = Role.VIEWER


class ApproveIn(BaseModel):
    role: Literal[Role.MANAGER, Role.VIEWER] | None = None  # 비우면 신청한 역할 그대로


class TempPasswordOut(BaseModel):
    user: UserOut
    temp_password: str


class UserUpdate(BaseModel):
    """회원정보 수정 (관리자). 보낸 값만 바꾼다."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    position: str | None = Field(default=None, max_length=30)
    phone: str | None = Field(default=None, max_length=20)
    org_id: int | None = None
    role: Role | None = None
    status: Literal[UserStatus.ACTIVE, UserStatus.LOCKED] | None = None  # 삭제는 DELETE 로


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
    is_active: bool | None = None


class RuleUpdate(BaseModel):
    """감지 유형별 기본 규칙 (판정 기준 · 심각도 기준 화면)"""

    min_confidence: float | None = Field(default=None, ge=0, le=1)
    default_severity: Severity | None = None
    cooldown_sec: int | None = Field(default=None, ge=0, le=24 * 3600)
    is_active: bool | None = None


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
    snapshot: str | None = None  # 첫 스냅샷 경로 ("snapshots/...")
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
    work_zone_id: int | None
    roi_id: int | None
    roi_name: str | None
    bbox: list | None
    snapshots: list[str]
    check_items: list[CheckItemState]
    actions: list[ActionOut]


# ---------------------------------------------------------------- 작업구역
class WorkZoneIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    plan_polygon: list[list[float]] | None = None  # 배치도 위 [[x, y], ...] (0~1 비율)


class WorkZoneUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    plan_polygon: list[list[float]] | None = None


class NamedRef(BaseModel):
    id: int
    name: str
    status: str | None = None
    kind: str | None = None


class ZoneSummary(WorkZoneOut):
    """전체 구역 표시 화면용 요약 (오늘 기준)"""

    works: list[NamedRef]      # 오늘 진행 · 예정 작업
    worker_count: int          # 오늘 배정 인원
    special_count: int         # 그중 특별관리
    equipment: list[NamedRef]  # 투입 장비
    cameras: list[str]
    open_events: int           # 미처리 · 확인중 이벤트
    open_high: int             # 그중 높음


# ---------------------------------------------------------------- 작업자 · 교육
class EducationOut(Out):
    id: int
    edu_type: EduType
    name: str


class WorkerEducationOut(BaseModel):
    id: int  # 이수 기록 번호
    edu_id: int
    edu_type: EduType
    name: str
    completed_date: date


class WorkerEducationIn(BaseModel):
    edu_id: int
    completed_date: date


class WorkerIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    company: str | None = Field(default=None, max_length=100)
    job_type: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None
    start_date: date | None = None


class WorkerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    company: str | None = Field(default=None, max_length=100)
    job_type: str | None = Field(default=None, max_length=50)
    phone: str | None = Field(default=None, max_length=20)
    birth_date: date | None = None
    start_date: date | None = None


class SpecialIn(BaseModel):
    reasons: list[SpecialReason] = Field(min_length=1)
    memo: str | None = Field(default=None, max_length=200)


class TodayWork(BaseModel):
    id: int
    name: str
    work_zone_id: int
    work_zone_name: str


class WorkerOut(BaseModel):
    id: int
    name: str
    company: str | None
    job_type: str | None
    phone: str | None
    birth_date: date | None
    start_date: date | None
    age: int | None
    is_special_care: bool
    special_reasons: list[SpecialReason]  # 지정할 때 고른 사유
    special_tags: list[str]               # 지금 유효한 사유를 화면용 글자로 (고령 64세, 신규 투입 · D+3)
    special_memo: str | None
    special_since: date | None
    special_by_name: str | None
    general_edu: bool                     # 기초안전보건교육 이수 여부
    educations: list[WorkerEducationOut]
    today_work: TodayWork | None          # 오늘 배정된 작업


# ---------------------------------------------------------------- 작업 · 배정
class WorkIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    work_zone_id: int
    manager_id: int | None = None
    start_date: date
    end_date: date | None = None
    status: WorkStatus = WorkStatus.PLANNED
    description: str | None = Field(default=None, max_length=1000)


class WorkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    work_zone_id: int | None = None
    manager_id: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: WorkStatus | None = None
    description: str | None = Field(default=None, max_length=1000)


class WorkOut(BaseModel):
    id: int
    name: str
    work_zone_id: int
    work_zone_name: str
    manager_id: int | None
    manager_name: str | None
    start_date: date
    end_date: date | None
    status: WorkStatus
    description: str | None
    worker_count: int
    special_count: int


class AssignedWorker(WorkerOut):
    assigned_date: date


class WorkDetail(WorkOut):
    workers: list[AssignedWorker]


class AssignIn(BaseModel):
    worker_ids: list[int]


# ---------------------------------------------------------------- 장비 · 일일 기록
class EquipmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    equip_type: EquipType
    reg_no: str | None = Field(default=None, max_length=50)
    spec: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=100)
    work_zone_id: int | None = None
    operator_id: int | None = None
    status: EquipStatus = EquipStatus.IDLE


class EquipmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    equip_type: EquipType | None = None
    reg_no: str | None = Field(default=None, max_length=50)
    spec: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=100)
    work_zone_id: int | None = None
    operator_id: int | None = None
    status: EquipStatus | None = None


class DailyLogOut(BaseModel):
    log_date: date
    status: EquipStatus
    inspected_at: datetime | None
    note: str | None
    recorded_by_name: str | None


class DailyLogIn(BaseModel):
    status: EquipStatus
    inspected_at: datetime | None = None
    note: str | None = Field(default=None, max_length=500)


class EquipmentOut(BaseModel):
    id: int
    name: str
    equip_type: EquipType
    reg_no: str | None
    spec: str | None
    company: str | None
    work_zone_id: int | None
    work_zone_name: str | None
    operator_id: int | None
    operator_name: str | None
    operator_company: str | None
    status: EquipStatus
    cameras: list[NamedRef]   # 이 장비에 달린 카메라 (TC CAM)
    today_log: DailyLogOut | None
    zone_events_today: int    # 투입 구역의 오늘 이벤트 수


class EquipmentDetail(EquipmentOut):
    logs: list[DailyLogOut]   # 최근 14일
    events: list[EventRow]    # 투입 구역 · 연결 카메라의 최근 이벤트


class DailyItem(BaseModel):
    equipment_id: int
    work_zone_id: int | None
    operator_id: int | None
    status: EquipStatus


class DailyIn(BaseModel):
    """장비 등록 및 배정 화면의 [오늘 기록 저장]: 장비 현재 값을 바꾸고 오늘 일일 기록을 남긴다"""

    items: list[DailyItem]
