"""ERD 2차 테이블 (db/schema.sql 과 같은 구조). 그림: docs/erd-v2.png"""

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
    CRANE = "CRANE"
    FORKLIFT = "FORKLIFT"
    ETC = "ETC"


class EquipStatus(StrEnum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    MAINTENANCE = "MAINTENANCE"
    OUT = "OUT"


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
    is_special_care: Mapped[bool] = mapped_column(Boolean, default=False)
    special_reason: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())


class Work(Base):
    __tablename__ = "work"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    work_zone_id: Mapped[int] = mapped_column(Id, ForeignKey("work_zone.id"))
    manager_id: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    work_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[WorkStatus] = mapped_column(enum_col(WorkStatus), default=WorkStatus.PLANNED)


class WorkAssignment(Base):
    __tablename__ = "work_assignment"

    work_id: Mapped[int] = mapped_column(Id, ForeignKey("work.id", ondelete="CASCADE"), primary_key=True)
    worker_id: Mapped[int] = mapped_column(Id, ForeignKey("worker.id"), primary_key=True)
    assigned_date: Mapped[date] = mapped_column(Date, primary_key=True)


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    equip_type: Mapped[EquipType] = mapped_column(enum_col(EquipType))
    work_zone_id: Mapped[int | None] = mapped_column(Id, ForeignKey("work_zone.id"))
    operator_id: Mapped[int | None] = mapped_column(Id, ForeignKey("worker.id"))
    status: Mapped[EquipStatus] = mapped_column(enum_col(EquipStatus), default=EquipStatus.IDLE)


class EquipmentDailyLog(Base):
    __tablename__ = "equipment_daily_log"
    __table_args__ = (UniqueConstraint("equipment_id", "log_date", name="uk_equipment_log_day"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    equipment_id: Mapped[int] = mapped_column(Id, ForeignKey("equipment.id", ondelete="CASCADE"))
    log_date: Mapped[date] = mapped_column(Date)
    status: Mapped[EquipStatus] = mapped_column(enum_col(EquipStatus))
    note: Mapped[str | None] = mapped_column(String(500))
    recorded_by: Mapped[int | None] = mapped_column(Id, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, server_default=func.now())
