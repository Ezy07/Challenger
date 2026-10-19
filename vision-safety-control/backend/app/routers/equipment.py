from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm import selectinload

from ..deps import DB, CurrentUser, Manager
from ..event_query import ZONE_ID, day_range, to_row
from ..models import (
    Camera,
    DetectionType,
    EquipType,
    Equipment,
    EquipmentDailyLog,
    Event,
    Roi,
    User,
    Worker,
    WorkZone,
)
from ..schemas import (
    ChecksIn,
    DailyIn,
    DailyLogIn,
    DailyLogOut,
    EquipmentDetail,
    EquipmentIn,
    EquipmentOut,
    EquipmentUpdate,
    NamedRef,
)

router = APIRouter(prefix="/api/equipment", tags=["장비 · 일일 기록"])

DOC_KEYS = ("license", "registration", "spec_sheet", "business", "work_plan")
EDU_KEYS = ("pre_entry", "special")
_checks_ready = False


def ensure_check_columns(db: DB) -> None:
    """이미 만들어진 장비 테이블에도 체크리스트 칸을 붙인다 (없는 칸만)."""
    global _checks_ready
    if _checks_ready:
        return
    bind = db.get_bind()
    names = {col["name"] for col in inspect(bind).get_columns("equipment")}
    missing = [col for col in ("doc_checks", "edu_checks") if col not in names]
    if missing:
        conn = bind.connect()
        try:
            for col in missing:
                conn.exec_driver_sql(f"ALTER TABLE equipment ADD COLUMN {col} JSON NULL")
            conn.commit()
        finally:
            conn.close()
    _checks_ready = True


def save_checks(db: DB, equipment_id: int, field: str, allowed: tuple[str, ...], items: list[str]) -> EquipmentDetail:
    ensure_check_columns(db)
    unknown = [key for key in items if key not in allowed]
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "목록에 없는 항목입니다.")
    e = get_equipment(db, equipment_id)
    setattr(e, field, list(dict.fromkeys(items)))
    db.commit()
    return detail(db, e.id)

def log_out(log: EquipmentDailyLog) -> DailyLogOut:
    return DailyLogOut(
        log_date=log.log_date, status=log.status, inspected_at=log.inspected_at, note=log.note,
        recorded_by_name=log.recorder.name if log.recorder else None,
    )


def zone_event_counts(db: DB, day: date) -> dict[int, int]:
    start, end = day_range(day)
    q = (
        select(ZONE_ID, func.count(Event.id))
        .select_from(Event)
        .outerjoin(Camera, Event.camera_id == Camera.id)
        .outerjoin(Roi, Event.roi_id == Roi.id)
        .where(Event.detected_at >= start, Event.detected_at < end)
        .group_by(ZONE_ID)
    )
    return {zone_id: n for zone_id, n in db.execute(q) if zone_id is not None}


def load_all(db: DB):
    """장비마다 필요한 값(구역 · 운전원 · 카메라 · 오늘 기록)을 한 번에 모은다"""
    today = date.today()
    cams: dict[int, list[NamedRef]] = {}
    for cam in db.scalars(select(Camera).where(Camera.equipment_id.is_not(None)).order_by(Camera.id)):
        cams.setdefault(cam.equipment_id, []).append(NamedRef(id=cam.id, name=cam.name))
    logs = {
        log.equipment_id: log
        for log in db.scalars(
            select(EquipmentDailyLog).where(EquipmentDailyLog.log_date == today)
            .options(selectinload(EquipmentDailyLog.recorder))
        )
    }
    return cams, logs, zone_event_counts(db, today)


def to_out(e: Equipment, cams, logs, zone_events) -> EquipmentOut:
    return EquipmentOut(
        id=e.id,
        name=e.name,
        equip_type=e.equip_type,
        reg_no=e.reg_no,
        spec=e.spec,
        company=e.company,
        work_zone_id=e.work_zone_id,
        work_zone_name=e.work_zone.name if e.work_zone else None,
        operator_id=e.operator_id,
        operator_name=e.operator.name if e.operator else None,
        operator_company=e.operator.company if e.operator else None,
        status=e.status,
        cameras=cams.get(e.id, []),
        today_log=log_out(logs[e.id]) if e.id in logs else None,
        zone_events_today=zone_events.get(e.work_zone_id, 0) if e.work_zone_id else 0,
    )


def load_options():
    return selectinload(Equipment.work_zone), selectinload(Equipment.operator)


def get_equipment(db: DB, equipment_id: int) -> Equipment:
    e = db.scalar(select(Equipment).where(Equipment.id == equipment_id).options(*load_options()))
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 장비입니다.")
    return e


def detail(db: DB, equipment_id: int) -> EquipmentDetail:
    db.expire_all()
    e = get_equipment(db, equipment_id)
    cams, logs, zone_events = load_all(db)
    history = db.scalars(
        select(EquipmentDailyLog)
        .where(EquipmentDailyLog.equipment_id == e.id, EquipmentDailyLog.log_date >= date.today() - timedelta(days=13))
        .options(selectinload(EquipmentDailyLog.recorder))
        .order_by(EquipmentDailyLog.log_date.desc())
    ).all()
    # 관련 이벤트: 이 장비에 달린 카메라에서 났거나, 장비가 투입된 구역에서 난 것
    cam_ids = [c.id for c in cams.get(e.id, [])]
    conds = [Event.camera_id.in_(cam_ids)] if cam_ids else []
    if e.work_zone_id:
        conds.append(ZONE_ID == e.work_zone_id)
    rows = []
    if conds:
        q = (
            select(Event, Camera.name, WorkZone.name, DetectionType.code, DetectionType.label)
            .join(DetectionType, Event.detection_type_id == DetectionType.id)
            .outerjoin(Camera, Event.camera_id == Camera.id)
            .outerjoin(Roi, Event.roi_id == Roi.id)
            .outerjoin(WorkZone, WorkZone.id == ZONE_ID)
            .where(or_(*conds))
            .order_by(Event.detected_at.desc())
            .limit(10)
        )
        rows = [to_row(*r) for r in db.execute(q)]
    return EquipmentDetail(
        **to_out(e, cams, logs, zone_events).model_dump(),
        logs=[log_out(log) for log in history],
        events=rows,
        doc_checks=list(e.doc_checks or []),
        edu_checks=list(e.edu_checks or []),
    )


def check_refs(db: DB, work_zone_id: int | None, operator_id: int | None) -> None:
    if work_zone_id is not None and not db.get(WorkZone, work_zone_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 작업구역입니다.")
    if operator_id is not None:
        op = db.get(Worker, operator_id)
        if not op or not op.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 작업자입니다.")


def check_reg_no(db: DB, reg_no: str | None, own_id: int | None = None) -> None:
    if reg_no and db.scalar(select(Equipment.id).where(Equipment.reg_no == reg_no, Equipment.id != (own_id or 0))):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 등록번호입니다.")


def upsert_log(db: DB, e: Equipment, day: date, user: User, **values) -> EquipmentDailyLog:
    log = db.scalar(select(EquipmentDailyLog).where(EquipmentDailyLog.equipment_id == e.id,
                                                    EquipmentDailyLog.log_date == day))
    if not log:
        log = EquipmentDailyLog(equipment_id=e.id, log_date=day, status=e.status)
        db.add(log)
    for key, value in values.items():
        setattr(log, key, value)
    log.recorded_by = user.id
    return log


@router.get("", response_model=list[EquipmentOut])
def list_equipment(db: DB, _: CurrentUser, equip_type: EquipType | None = None,
                   work_zone_id: int | None = None, q: str | None = None):
    ensure_check_columns(db)
    query = select(Equipment).options(*load_options()).order_by(Equipment.equip_type, Equipment.name)
    if equip_type:
        query = query.where(Equipment.equip_type == equip_type)
    if work_zone_id is not None:
        query = query.where(Equipment.work_zone_id == work_zone_id)
    if q:
        query = query.where(or_(Equipment.name.contains(q), Equipment.reg_no.contains(q)))
    cams, logs, zone_events = load_all(db)
    return [to_out(e, cams, logs, zone_events) for e in db.scalars(query)]


@router.get("/{equipment_id}", response_model=EquipmentDetail)
def read_equipment(equipment_id: int, db: DB, _: CurrentUser):
    ensure_check_columns(db)
    return detail(db, equipment_id)


@router.post("", response_model=EquipmentDetail, status_code=status.HTTP_201_CREATED)
def create_equipment(body: EquipmentIn, db: DB, _: Manager):
    ensure_check_columns(db)
    check_refs(db, body.work_zone_id, body.operator_id)
    check_reg_no(db, body.reg_no)
    e = Equipment(**body.model_dump())
    db.add(e)
    db.commit()
    return detail(db, e.id)


@router.patch("/{equipment_id}", response_model=EquipmentDetail)
def update_equipment(equipment_id: int, body: EquipmentUpdate, db: DB, _: Manager):
    ensure_check_columns(db)
    e = get_equipment(db, equipment_id)
    data = body.model_dump(exclude_unset=True)
    check_refs(db, data.get("work_zone_id"), data.get("operator_id"))
    check_reg_no(db, data.get("reg_no"), e.id)
    if e.equip_type == EquipType.TC and data.get("equip_type", EquipType.TC) != EquipType.TC and \
            db.scalar(select(Camera.id).where(Camera.equipment_id == e.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "TC CAM 이 연결된 타워크레인은 종류를 바꿀 수 없습니다.")
    for key, value in data.items():
        setattr(e, key, value)
    db.commit()
    return detail(db, e.id)


@router.delete("/{equipment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_equipment(equipment_id: int, db: DB, _: Manager):
    ensure_check_columns(db)
    e = get_equipment(db, equipment_id)
    if db.scalar(select(Camera.id).where(Camera.equipment_id == e.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이 장비에 연결된 카메라가 있습니다. 카메라 연결을 먼저 바꾸세요.")
    db.delete(e)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/{equipment_id}/logs/{log_date}", response_model=EquipmentDetail)
def save_log(equipment_id: int, log_date: date, body: DailyLogIn, db: DB, user: Manager):
    """하루 기록 쓰기 (운전 전 점검 시각 · 메모). 오늘 기록이면 장비의 현재 상태도 같이 바꾼다."""
    ensure_check_columns(db)
    e = get_equipment(db, equipment_id)
    if log_date > date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "앞으로의 날짜에는 기록할 수 없습니다.")
    upsert_log(db, e, log_date, user, **body.model_dump())
    if log_date == date.today():
        e.status = body.status
    db.commit()
    return detail(db, e.id)


@router.post("/daily", response_model=list[EquipmentOut])
def save_daily(body: DailyIn, db: DB, user: Manager):
    """[오늘 기록 저장]: 장비마다 투입 구역 · 운전원 · 상태를 바꾸고 오늘 일일 기록에 상태를 남긴다"""
    ensure_check_columns(db)
    today = date.today()
    for item in body.items:
        e = get_equipment(db, item.equipment_id)
        check_refs(db, item.work_zone_id, item.operator_id)
        e.work_zone_id, e.operator_id, e.status = item.work_zone_id, item.operator_id, item.status
        upsert_log(db, e, today, user, status=item.status)
    db.commit()
    db.expire_all()
    return list_equipment(db, user)


@router.put("/{equipment_id}/checks/docs", response_model=EquipmentDetail)
def save_doc_checks(equipment_id: int, body: ChecksIn, db: DB, _: Manager):
    """구비 서류 체크리스트. 체크된 항목 키만 남긴다."""
    return save_checks(db, equipment_id, "doc_checks", DOC_KEYS, body.items)


@router.put("/{equipment_id}/checks/edu", response_model=EquipmentDetail)
def save_edu_checks(equipment_id: int, body: ChecksIn, db: DB, _: Manager):
    """안전교육 체크리스트. 체크된 항목 키만 남긴다."""
    return save_checks(db, equipment_id, "edu_checks", EDU_KEYS, body.items)
