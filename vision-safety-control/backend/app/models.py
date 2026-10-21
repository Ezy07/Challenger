"""ERD 3차 테이블 (db/schema.sql 과 같은 구조). 그림: docs/erd-v3.png"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# MySQL 에서는 BIGINT UNSIGNED, SQLite(테스트)에서는 자동 증가가 되는 INTEGER
Id = mysql.BIGINT(unsigned=True).with_variant(Integer, "sqlite")
DateTimeMs = DateTime().with_variant(mysql.DATETIME(fsp=3), "mysql")


# ---------------------------------------------------------------- 값 목록
class OrgType(StrEnum):
    COMPANY = "COMPANY"
    DEPT = "DEPT"


class Role(StrEnum):
    ADMIN = "ADMIN"      # 관리자
    MANAGER = "MANAGER"  # 안전관리자
    VIEWER = "VIEWER"    # 조회 전용


class UserStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    LOCKED = "LOCKED"
    DELETED = "DELETED"  # 삭제 (처리 기록에 이름이 남아야 해서 행은 지우지 않음)


class CameraType(StrEnum):
    FIXED = "FIXED"
    TC = "TC"


class Severity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EventStatus(StrEnum):
    NEW = "NEW"      # 미처리
    ACK = "ACK"      # 확인중
    DONE = "DONE"    # 처리완료
    FALSE = "FALSE"  # 오탐


class ActionType(StrEnum):
    ACK = "ACK"                  # 확인 시작
    NOTE = "NOTE"                # 메모만 남김
    ESCALATE = "ESCALATE"        # 조치 필요 · 담당자 재알림
    PERMIT = "PERMIT"            # 해제 항목 하나 허가
    REVOKE = "REVOKE"            # 허가 취소
    RESOLVE = "RESOLVE"          # 처리 완료 (모든 항목 허가 필요)
    FALSE_ALARM = "FALSE_ALARM"  # 오탐


class EquipType(StrEnum):
    TC = "TC"
    EXCAVATOR = "EXCAVATOR"
    PUMP_CAR = "PUMP_CAR"
    MIXER_TRUCK = "MIXER_TRUCK"
    DUMP_TRUCK = "DUMP_TRUCK"
    CRANE = "CRANE"
    FORKLIFT = "FORKLIFT"
    ETC = "ETC"


class EquipStatus(StrEnum):
    RUNNING = "RUNNING"          # 가동
    IDLE = "IDLE"                # 대기
    MAINTENANCE = "MAINTENANCE"  # 점검
    BROKEN = "BROKEN"            # 고장
    # 미투입은 상태가 아니라 투입 구역(work_zone_id)이 없는 것으로 나타낸다


class SpecialReason(StrEnum):
    ELDERLY = "ELDERLY"            # 고령 (만 60세 이상)
    HYPERTENSION = "HYPERTENSION"  # 고혈압 · 건강 주의
    NEW = "NEW"                    # 신규 투입 (투입 후 7일 이내, 지나면 자동으로 빠짐)
    ETC = "ETC"                    # 기타


class EduType(StrEnum):
    GENERAL = "GENERAL"  # 기초 이수 교육
    SPECIAL = "SPECIAL"  # 특별교육


# 이 4개가 이수 기록에 모두 있어야 기초교육 이수. 하나라도 없으면 미이수.
REQUIRED_GENERAL_EDU = (
    "근로자 정기안전보건교육",
    "건설업 기초안전보건교육",
    "채용 시 교육",
    "작업내용 변경 시 교육",
)


class WorkStatus(StrEnum):
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    STOPPED = "STOPPED"


def enum_col(e: type[StrEnum]) -> Enum:
    return Enum(e, native_enum=True, create_constraint=False, validate_strings=True)


# ---------------------------------------------------------------- 회원 · 조직
class Organization(Base):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(Id, ForeignKey("organization.id"))
    type: Mapped[OrgType] = mapped_column(enum_col(OrgType))
    name: Mapped[str] = mapped_column(String(100))
    is_prime: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    org_id: Mapped[int | None] = mapped_column(Id, ForeignKey("organization.id"))
    login_id: Mapped[str] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(50))
    position: Mapped[str | None] = mapped_column(String(30))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[Role] = mapped_column(enum_col(Role), default=Role.VIEWER)
    status: Mapped[UserStatus] = mapped_column(enum_col(UserStatus), default=UserStatus.PENDING)
    approved_by: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    failed_login_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now(), onupdate=datetime.now)

    org: Mapped[Organization | None] = relationship()


# ---------------------------------------------------------------- 구역 · 카메라 · ROI
class WorkZone(Base):
    __tablename__ = "work_zone"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    plan_polygon: Mapped[list | None] = mapped_column(JSON)


class SitePlan(Base):
    """현장 도면 (한 장). 전체 구역 표시 · 카메라 배치도가 같이 쓰고, 구역 · 카메라 위치는 이 그림 위의 비율(0~1)"""

    __tablename__ = "site_plan"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), default="현장 배치도")
    image_path: Mapped[str] = mapped_column(String(500))  # "plans/파일이름" (storage 기준)
    original_name: Mapped[str | None] = mapped_column(String(255))
    width: Mapped[int] = mapped_column(Integer)  # 그림 크기(px). 화면에서 가로세로 비율을 맞추는 데 씀
    height: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    uploader: Mapped[User | None] = relationship()


class Camera(Base):
    __tablename__ = "camera"
    __table_args__ = (
        UniqueConstraint("view_page", "view_slot", name="uk_camera_slot"),
        CheckConstraint("view_slot IS NULL OR view_slot BETWEEN 1 AND 4", name="chk_camera_slot"),
    )

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    work_zone_id: Mapped[int | None] = mapped_column(Id, ForeignKey("work_zone.id"))
    equipment_id: Mapped[int | None] = mapped_column(Id, ForeignKey("equipment.id"))
    camera_type: Mapped[CameraType] = mapped_column(enum_col(CameraType), default=CameraType.FIXED)
    view_page: Mapped[int] = mapped_column(SmallInteger, default=1)
    view_slot: Mapped[int | None] = mapped_column(SmallInteger)
    stream_url: Mapped[str | None] = mapped_column(String(500))
    location_desc: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    plan_x: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # 도면 위 위치 (왼쪽 0 ~ 오른쪽 1)
    plan_y: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))  # (위 0 ~ 아래 1)
    plan_dir: Mapped[int | None] = mapped_column(SmallInteger)     # 보는 방향 (0 = 위쪽, 시계 방향 도)
    plan_color: Mapped[str | None] = mapped_column(String(7))      # 배치도 화각 색 "#ff9a1f" (NULL = 기본색)
    plan_fov: Mapped[int | None] = mapped_column(SmallInteger)     # 화각 폭 도 (360 = 회전하며 전체, NULL = 기본 60)
    plan_range: Mapped[int | None] = mapped_column(SmallInteger)   # 화각 길이 (도면 너비 1000 기준, NULL = 기본 110)

    work_zone: Mapped[WorkZone | None] = relationship()
    equipment: Mapped["Equipment | None"] = relationship()


class Roi(Base):
    __tablename__ = "roi"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    camera_id: Mapped[int] = mapped_column(Id, ForeignKey("camera.id"))
    work_zone_id: Mapped[int | None] = mapped_column(Id, ForeignKey("work_zone.id"))
    name: Mapped[str] = mapped_column(String(100))
    polygon: Mapped[list] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    camera: Mapped[Camera] = relationship()
    work_zone: Mapped[WorkZone | None] = relationship()


# ---------------------------------------------------------------- 감지 규칙
class DetectionType(Base):
    __tablename__ = "detection_type"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    label: Mapped[str] = mapped_column(String(50))

    rule: Mapped["AlertRule | None"] = relationship(back_populates="detection_type", uselist=False)
    check_items: Mapped[list["ReleaseCheckItem"]] = relationship(order_by="ReleaseCheckItem.sort_order")


class AlertRule(Base):
    __tablename__ = "alert_rule"
    __table_args__ = (CheckConstraint("min_confidence BETWEEN 0 AND 1", name="chk_alert_rule_conf"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    detection_type_id: Mapped[int] = mapped_column(Id, ForeignKey("detection_type.id"), unique=True)
    min_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3), default=Decimal("0.5"))
    default_severity: Mapped[Severity] = mapped_column(enum_col(Severity), default=Severity.MEDIUM)
    cooldown_sec: Mapped[int] = mapped_column(Integer, default=60)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 끄면 이 유형은 이벤트를 만들지 않음

    detection_type: Mapped[DetectionType] = relationship(back_populates="rule")


class ReleaseCheckItem(Base):
    __tablename__ = "release_check_item"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    detection_type_id: Mapped[int] = mapped_column(Id, ForeignKey("detection_type.id"))
    title: Mapped[str] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class RoiRule(Base):
    __tablename__ = "roi_rule"
    __table_args__ = (UniqueConstraint("roi_id", "detection_type_id", name="uk_roi_rule"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    roi_id: Mapped[int] = mapped_column(Id, ForeignKey("roi.id", ondelete="CASCADE"))
    detection_type_id: Mapped[int] = mapped_column(Id, ForeignKey("detection_type.id"))
    min_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # NULL = 기본값
    severity: Mapped[Severity | None] = mapped_column(enum_col(Severity))  # NULL = 기본값


# ---------------------------------------------------------------- 이벤트
class Event(Base):
    __tablename__ = "event"
    __table_args__ = (CheckConstraint("confidence IS NULL OR confidence BETWEEN 0 AND 1", name="chk_event_conf"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(Id, ForeignKey("camera.id"))
    roi_id: Mapped[int | None] = mapped_column(Id, ForeignKey("roi.id"))
    detection_type_id: Mapped[int] = mapped_column(Id, ForeignKey("detection_type.id"))
    severity: Mapped[Severity] = mapped_column(enum_col(Severity))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    bbox: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[EventStatus] = mapped_column(enum_col(EventStatus), default=EventStatus.NEW, index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTimeMs, index=True)

    camera: Mapped[Camera | None] = relationship()
    roi: Mapped[Roi | None] = relationship()
    detection_type: Mapped[DetectionType] = relationship()
    actions: Mapped[list["EventAction"]] = relationship(order_by="EventAction.id", cascade="all, delete-orphan")
    snapshots: Mapped[list["EventSnapshot"]] = relationship(cascade="all, delete-orphan")


class EventAction(Base):
    __tablename__ = "event_action"
    __table_args__ = (
        CheckConstraint(
            "action_type NOT IN ('PERMIT', 'REVOKE') OR check_item_id IS NOT NULL", name="chk_action_item"
        ),
    )

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    event_id: Mapped[int] = mapped_column(Id, ForeignKey("event.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(Id, ForeignKey("users.id"))
    check_item_id: Mapped[int | None] = mapped_column(Id, ForeignKey("release_check_item.id"))
    action_type: Mapped[ActionType] = mapped_column(enum_col(ActionType))
    memo: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    user: Mapped[User] = relationship()


class EventSnapshot(Base):
    __tablename__ = "event_snapshot"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    event_id: Mapped[int] = mapped_column(Id, ForeignKey("event.id", ondelete="CASCADE"))
    image_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


# ---------------------------------------------------------------- 작업자 · 작업 · 장비
class Worker(Base):
    __tablename__ = "worker"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    company: Mapped[str | None] = mapped_column(String(100))
    job_type: Mapped[str | None] = mapped_column(String(50))
    phone: Mapped[str | None] = mapped_column(String(20))
    birth_date: Mapped[date | None] = mapped_column(Date)
    start_date: Mapped[date | None] = mapped_column(Date)  # 현장 투입일 (신규 투입 7일 판단)
    is_special_care: Mapped[bool] = mapped_column(Boolean, default=False)
    special_reasons: Mapped[list | None] = mapped_column(JSON)  # ["ELDERLY", "HYPERTENSION", ...]
    special_memo: Mapped[str | None] = mapped_column(String(200))  # 건강정보 = 민감정보
    special_since: Mapped[date | None] = mapped_column(Date)  # 지정일
    special_by: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))  # 지정한 사람
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # 삭제하면 0 (배정 이력은 남김)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    special_user: Mapped[User | None] = relationship()
    educations: Mapped[list["WorkerEducation"]] = relationship(
        order_by="WorkerEducation.completed_date", cascade="all, delete-orphan"
    )


class Education(Base):
    """안전교육 목록 (코드 테이블)"""

    __tablename__ = "education"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    edu_type: Mapped[EduType] = mapped_column(enum_col(EduType))
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class WorkerEducation(Base):
    """작업자별 교육 이수 이력 (같은 교육 재이수도 기록)"""

    __tablename__ = "worker_education"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    worker_id: Mapped[int] = mapped_column(Id, ForeignKey("worker.id", ondelete="CASCADE"), index=True)
    edu_id: Mapped[int] = mapped_column(Id, ForeignKey("education.id"))
    completed_date: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    education: Mapped[Education] = relationship()


class Work(Base):
    __tablename__ = "work"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    work_zone_id: Mapped[int] = mapped_column(Id, ForeignKey("work_zone.id"))
    manager_id: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date | None] = mapped_column(Date)  # 비우면 하루짜리 작업
    status: Mapped[WorkStatus] = mapped_column(enum_col(WorkStatus), default=WorkStatus.PLANNED)
    description: Mapped[str | None] = mapped_column(String(1000))  # 작업 내용 · 주의사항

    work_zone: Mapped[WorkZone] = relationship()
    manager: Mapped[User | None] = relationship()
    assignments: Mapped[list["WorkAssignment"]] = relationship(cascade="all, delete-orphan")


class WorkAssignment(Base):
    __tablename__ = "work_assignment"

    work_id: Mapped[int] = mapped_column(Id, ForeignKey("work.id", ondelete="CASCADE"), primary_key=True)
    worker_id: Mapped[int] = mapped_column(Id, ForeignKey("worker.id"), primary_key=True)
    assigned_date: Mapped[date] = mapped_column(Date, primary_key=True)

    worker: Mapped[Worker] = relationship()


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    equip_type: Mapped[EquipType] = mapped_column(enum_col(EquipType))
    reg_no: Mapped[str | None] = mapped_column(String(50), unique=True)  # 등록번호 · 차량번호
    spec: Mapped[str | None] = mapped_column(String(200))  # 제원 (T형 · 지브 55m, 15t ...)
    company: Mapped[str | None] = mapped_column(String(100))  # 소속 회사 (운전원 없이 오가는 트럭 등)
    work_zone_id: Mapped[int | None] = mapped_column(Id, ForeignKey("work_zone.id"))  # NULL = 미투입
    operator_id: Mapped[int | None] = mapped_column(Id, ForeignKey("worker.id"))
    status: Mapped[EquipStatus] = mapped_column(enum_col(EquipStatus), default=EquipStatus.IDLE)
    doc_checks: Mapped[list | None] = mapped_column(JSON)  # 구비 서류 체크 (license, registration ...)
    edu_checks: Mapped[list | None] = mapped_column(JSON)  # 안전교육 체크 (pre_entry, special)

    work_zone: Mapped[WorkZone | None] = relationship()
    operator: Mapped[Worker | None] = relationship()


class EquipmentDailyLog(Base):
    __tablename__ = "equipment_daily_log"
    __table_args__ = (UniqueConstraint("equipment_id", "log_date", name="uk_equipment_log_day"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(Id, ForeignKey("equipment.id", ondelete="CASCADE"))
    log_date: Mapped[date] = mapped_column(Date)
    status: Mapped[EquipStatus] = mapped_column(enum_col(EquipStatus))
    inspected_at: Mapped[datetime | None] = mapped_column(DateTime)  # 운전 전 점검 완료 시각
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())

    recorder: Mapped[User | None] = relationship()
