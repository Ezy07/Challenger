from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from .. import vision
from ..deps import DB, Admin, CurrentUser
from ..models import Camera, CameraType, Equipment, EquipType, WorkZone
from ..schemas import CameraIn, CameraOut, CameraUpdate
from .videos import URL_PREFIX, video_path

router = APIRouter(prefix="/api/cameras", tags=["카메라"])


def to_out(cam: Camera) -> CameraOut:
    out = CameraOut.model_validate(cam)
    out.work_zone_name = cam.work_zone.name if cam.work_zone else None
    return out


def get_camera(db: DB, camera_id: int) -> Camera:
    cam = db.get(Camera, camera_id)
    if not cam:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 카메라입니다.")
    return cam


def check_refs(db: DB, cam: Camera, check_video: bool = True) -> None:
    """저장 전에 구역 · 장비 연결이 맞는지 확인. 영상 파일은 영상 소스를 바꿀 때만 본다
    (나중에 파일이 지워진 카메라도 배치도 위치 · 색 같은 다른 값은 바꿀 수 있게)"""
    if check_video and cam.stream_url and cam.stream_url.startswith(URL_PREFIX):
        path = video_path(cam.stream_url)
        if not path or not path.is_file():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "영상 폴더(storage/videos)에 없는 파일입니다.")
    if cam.work_zone_id is not None and not db.get(WorkZone, cam.work_zone_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 작업구역입니다.")
    if cam.camera_type == CameraType.TC:
        equip = db.get(Equipment, cam.equipment_id) if cam.equipment_id else None
        if not equip or equip.equip_type != EquipType.TC:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "TC CAM 은 타워크레인 장비를 골라야 합니다.")
    elif cam.equipment_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "고정 카메라에는 장비를 연결하지 않습니다.")


def commit_or_409(db: DB) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "관제화면의 같은 칸에 이미 다른 카메라가 있습니다.")


@router.get("", response_model=list[CameraOut])
def list_cameras(db: DB, _: CurrentUser, view_page: int | None = None):
    """카메라 목록. ?view_page=1 이면 관제화면 1페이지(현장 CAM)에 놓인 카메라만"""
    q = select(Camera).options(selectinload(Camera.work_zone)).order_by(Camera.view_page, Camera.view_slot, Camera.id)
    if view_page is not None:
        q = q.where(Camera.view_page == view_page)
    return [to_out(c) for c in db.scalars(q)]


@router.get("/{camera_id}", response_model=CameraOut)
def read_camera(camera_id: int, db: DB, _: CurrentUser):
    return to_out(get_camera(db, camera_id))


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
def create_camera(body: CameraIn, db: DB, _: Admin):
    cam = Camera(**body.model_dump())
    check_refs(db, cam)
    db.add(cam)
    commit_or_409(db)
    return to_out(cam)


@router.patch("/{camera_id}", response_model=CameraOut)
def update_camera(camera_id: int, body: CameraUpdate, db: DB, _: Admin):
    cam = get_camera(db, camera_id)
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(cam, key, value)
    check_refs(db, cam, check_video="stream_url" in data)
    commit_or_409(db)
    db.refresh(cam)
    if "fine_detect" in data:
        vision.set_fine(cam.id, cam.fine_detect)  # 지금 탐지 중이면 바로 바꿔 탐지
    return to_out(cam)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_camera(camera_id: int, db: DB, _: Admin):
    cam = get_camera(db, camera_id)
    db.delete(cam)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이벤트 · ROI 기록이 있는 카메라는 지울 수 없습니다. 대신 사용 안 함으로 바꾸세요.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
