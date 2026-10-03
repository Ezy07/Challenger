"""화면의 선택 칸 · 필터를 채우는 기준 정보"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..deps import DB, Admin, CurrentUser
from ..models import DetectionType, Organization, OrgType, WorkZone
from ..schemas import DetectionTypeOut, OrgIn, OrgOut, WorkZoneOut

router = APIRouter(prefix="/api", tags=["기준 정보"])


@router.get("/orgs", response_model=list[OrgOut])
def list_orgs(db: DB):
    """조직 · 부서 트리 (회원가입 화면에서 로그인 전에 쓰므로 공개)"""
    return db.scalars(select(Organization).order_by(Organization.is_prime.desc(), Organization.id)).all()


@router.post("/orgs", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
def create_org(body: OrgIn, db: DB, _: Admin):
    if body.type == OrgType.DEPT and body.parent_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "부서는 상위 조직이 필요합니다.")
    if body.parent_id is not None and not db.get(Organization, body.parent_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 상위 조직입니다.")
    org = Organization(**body.model_dump())
    db.add(org)
    db.commit()
    return org


@router.get("/work-zones", response_model=list[WorkZoneOut])
def list_work_zones(db: DB, _: CurrentUser):
    return db.scalars(select(WorkZone).order_by(WorkZone.id)).all()


@router.get("/detection-types", response_model=list[DetectionTypeOut])
def list_detection_types(db: DB, _: CurrentUser):
    """감지 유형과 기본 규칙(판정 기준 · 심각도 · 쿨다운)"""
    types = db.scalars(select(DetectionType).options(selectinload(DetectionType.rule)).order_by(DetectionType.id))
    return [
        DetectionTypeOut(
            id=t.id,
            code=t.code,
            label=t.label,
            min_confidence=float(t.rule.min_confidence) if t.rule else None,
            default_severity=t.rule.default_severity if t.rule else None,
            cooldown_sec=t.rule.cooldown_sec if t.rule else None,
        )
        for t in types
    ]
