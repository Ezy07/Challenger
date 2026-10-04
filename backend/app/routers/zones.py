from datetime import date

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..deps import DB, CurrentUser, Manager
from ..models import Camera, Equipment, Event, EventStatus, Roi, Severity, Work, WorkAssignment, WorkZone
from ..schemas import NamedRef, WorkZoneIn, WorkZoneOut, WorkZoneUpdate, ZoneSummary
from ..today import OPEN_WORK, special_tags, work_active_on, worker_load

router = APIRouter(prefix="/api/work-zones", tags=["작업구역"])

ZONE_ID = func.coalesce(Roi.work_zone_id, Camera.work_zone_id)


def check_polygon(polygon: list[list[float]] | None) -> None:
    if polygon is None:
        return
    if len(polygon) < 3 or any(len(p) != 2 or not (0 <= p[0] <= 1 and 0 <= p[1] <= 1) for p in polygon):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "배치도 영역은 0~1 비율 좌표 3개 이상이어야 합니다.")


def get_zone(db: DB, zone_id: int) -> WorkZone:
    zone = db.get(WorkZone, zone_id)
    if not zone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 작업구역입니다.")
    return zone


@router.get("", response_model=list[WorkZoneOut])
def list_zones(db: DB, _: CurrentUser):
    return db.scalars(select(WorkZone).order_by(WorkZone.id)).all()


@router.get("/summary", response_model=list[ZoneSummary])
def zone_summary(db: DB, _: CurrentUser):
    """전체 구역 표시: 구역마다 오늘 작업 · 인원 · 장비 · 미처리 경보"""
    today = date.today()
    zones = db.scalars(select(WorkZone).order_by(WorkZone.id)).all()
    works = db.scalars(
        select(Work).where(work_active_on(today), Work.status.in_(OPEN_WORK))
        .options(selectinload(Work.assignments).selectinload(WorkAssignment.worker).options(*worker_load()))
        .order_by(Work.start_date, Work.id)
    ).all()
    equipment = db.scalars(select(Equipment).where(Equipment.work_zone_id.is_not(None)).order_by(Equipment.name)).all()
    cameras = db.scalars(select(Camera).where(Camera.work_zone_id.is_not(None), Camera.is_active).order_by(Camera.id)).all()
    open_q = (
        select(ZONE_ID, Event.severity, func.count(Event.id))
        .select_from(Event)
        .outerjoin(Camera, Event.camera_id == Camera.id)
        .outerjoin(Roi, Event.roi_id == Roi.id)
        .where(Event.status.in_([EventStatus.NEW, EventStatus.ACK]))
        .group_by(ZONE_ID, Event.severity)
    )
    open_events: dict[int, list[tuple[Severity, int]]] = {}
    for zone_id, sev, n in db.execute(open_q):
        open_events.setdefault(zone_id, []).append((sev, n))

    result = []
    for z in zones:
        z_works = [w for w in works if w.work_zone_id == z.id]
        people = {a.worker.id: a.worker for w in z_works for a in w.assignments if a.worker.is_active}
        counts = open_events.get(z.id, [])
        result.append(ZoneSummary(
            id=z.id,
            name=z.name,
            plan_polygon=z.plan_polygon,
            works=[NamedRef(id=w.id, name=w.name, status=w.status) for w in z_works],
            worker_count=len(people),
            special_count=sum(1 for w in people.values() if special_tags(w, today)),
            equipment=[NamedRef(id=e.id, name=e.name, status=e.status, kind=e.equip_type)
                       for e in equipment if e.work_zone_id == z.id],
            cameras=[c.name for c in cameras if c.work_zone_id == z.id],
            open_events=sum(n for _, n in counts),
            open_high=sum(n for sev, n in counts if sev == Severity.HIGH),
        ))
    return result


@router.post("", response_model=WorkZoneOut, status_code=status.HTTP_201_CREATED)
def create_zone(body: WorkZoneIn, db: DB, _: Manager):
    check_polygon(body.plan_polygon)
    zone = WorkZone(**body.model_dump())
    db.add(zone)
    db.commit()
    return zone


@router.patch("/{zone_id}", response_model=WorkZoneOut)
def update_zone(zone_id: int, body: WorkZoneUpdate, db: DB, _: Manager):
    zone = get_zone(db, zone_id)
    data = body.model_dump(exclude_unset=True)
    check_polygon(data.get("plan_polygon"))
    for key, value in data.items():
        setattr(zone, key, value)
    db.commit()
    return zone


@router.delete("/{zone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_zone(zone_id: int, db: DB, _: Manager):
    zone = get_zone(db, zone_id)
    db.delete(zone)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이 구역을 쓰는 작업 · 장비 · 카메라 · ROI 가 있어 지울 수 없습니다.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
