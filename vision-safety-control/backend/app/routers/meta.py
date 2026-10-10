"""기준 정보: 조직 · 부서, 감지 유형과 기본 규칙"""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..deps import DB, Admin, CurrentUser
from ..models import AlertRule, DetectionType, Organization, OrgType, User, UserStatus
from ..schemas import DetectionTypeOut, OrgIn, OrgOut, OrgUpdate, RuleUpdate
from ..zone_events import LIVE_CODES

router = APIRouter(prefix="/api", tags=["기준 정보"])

MAX_DEPT_DEPTH = 2  # 회사 아래 부서는 최대 2단계 (예: OO건설 > 공사팀 > 양중)


# ---------------------------------------------------------------- 조직 · 부서
def get_org(db: DB, org_id: int) -> Organization:
    org = db.get(Organization, org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 조직입니다.")
    return org


def check_parent(db: DB, org_type: OrgType, parent_id: int | None, own_id: int | None = None) -> None:
    """회사는 최상위, 부서는 회사 아래 최대 2단계. 자기 자신이나 하위 부서를 상위로 둘 수 없다."""
    if org_type == OrgType.COMPANY:
        if parent_id is not None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "회사는 상위 조직을 둘 수 없습니다.")
        return
    if parent_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "부서는 상위 조직이 필요합니다.")
    depth, node = 1, db.get(Organization, parent_id)
    if not node:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "없는 상위 조직입니다.")
    while node.parent_id is not None:
        if node.id == own_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "자기 자신이나 하위 부서를 상위 조직으로 둘 수 없습니다.")
        depth += 1
        node = db.get(Organization, node.parent_id)
    if node.id == own_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "자기 자신을 상위 조직으로 둘 수 없습니다.")
    has_children = own_id is not None and db.scalar(select(Organization.id).where(Organization.parent_id == own_id))
    if depth > MAX_DEPT_DEPTH or (has_children and depth >= MAX_DEPT_DEPTH):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"부서는 회사 아래 {MAX_DEPT_DEPTH}단계까지만 만들 수 있습니다.")


@router.get("/orgs", response_model=list[OrgOut])
def list_orgs(db: DB):
    """조직 · 부서 트리 (회원가입 화면에서 로그인 전에 쓰므로 공개)"""
    return db.scalars(select(Organization).order_by(Organization.is_prime.desc(), Organization.id)).all()


@router.post("/orgs", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
def create_org(body: OrgIn, db: DB, _: Admin):
    check_parent(db, body.type, body.parent_id)
    org = Organization(**body.model_dump())
    db.add(org)
    db.commit()
    return org


@router.patch("/orgs/{org_id}", response_model=OrgOut)
def update_org(org_id: int, body: OrgUpdate, db: DB, _: Admin):
    org = get_org(db, org_id)
    data = body.model_dump(exclude_unset=True)
    if "parent_id" in data:
        check_parent(db, org.type, data["parent_id"], org.id)
    for key, value in data.items():
        setattr(org, key, value)
    db.commit()
    return org


@router.delete("/orgs/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_org(org_id: int, db: DB, _: Admin):
    org = get_org(db, org_id)
    if db.scalar(select(Organization.id).where(Organization.parent_id == org.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "하위 부서가 있으면 삭제할 수 없습니다. 하위 부서를 먼저 옮기거나 지우세요.")
    if db.scalar(select(User.id).where(User.org_id == org.id, User.status != UserStatus.DELETED)):
        raise HTTPException(status.HTTP_409_CONFLICT, "소속 회원이 있으면 삭제할 수 없습니다. 먼저 회원을 다른 부서로 옮기세요.")
    db.delete(org)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- 감지 유형 · 기본 규칙
def type_out(t: DetectionType) -> DetectionTypeOut:
    r = t.rule
    return DetectionTypeOut(
        id=t.id, code=t.code, label=t.label,
        min_confidence=float(r.min_confidence) if r else None,
        default_severity=r.default_severity if r else None,
        cooldown_sec=r.cooldown_sec if r else None,
        is_active=r.is_active if r else None,
        live=t.code in LIVE_CODES,
    )


@router.get("/detection-types", response_model=list[DetectionTypeOut])
def list_detection_types(db: DB, _: CurrentUser):
    """감지 유형과 기본 규칙(판정 기준 · 심각도 · 쿨다운 · 사용 여부)"""
    types = db.scalars(select(DetectionType).options(selectinload(DetectionType.rule)).order_by(DetectionType.id))
    return [type_out(t) for t in types]


@router.patch("/detection-types/{type_id}/rule", response_model=DetectionTypeOut)
def update_rule(type_id: int, body: RuleUpdate, db: DB, _: Admin):
    t = db.scalar(select(DetectionType).where(DetectionType.id == type_id).options(selectinload(DetectionType.rule)))
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "없는 감지 유형입니다.")
    if not t.rule:
        t.rule = AlertRule()
    data = body.model_dump(exclude_unset=True)
    if data.get("min_confidence") is not None:
        data["min_confidence"] = Decimal(str(round(data["min_confidence"], 3)))
    for key, value in data.items():
        if value is not None:
            setattr(t.rule, key, value)
    db.commit()
    return type_out(t)


@router.post("/detection-types/reset-rules", response_model=list[DetectionTypeOut])
def reset_rules(db: DB, _: Admin):
    """판정 기준 화면의 [기본값으로]: 처음 설치할 때 값으로 되돌린다"""
    from ..seed import DETECTION_TYPES  # 기본값은 seed 한 곳에서만 관리

    defaults = {code: (sev, conf, cooldown) for code, _, sev, conf, cooldown, _ in DETECTION_TYPES}
    types = db.scalars(select(DetectionType).options(selectinload(DetectionType.rule))).all()
    for t in types:
        if t.code not in defaults:
            continue
        sev, conf, cooldown = defaults[t.code]
        if not t.rule:
            t.rule = AlertRule()
        t.rule.default_severity, t.rule.min_confidence, t.rule.cooldown_sec, t.rule.is_active = sev, Decimal(conf), cooldown, True
    db.commit()
    return list_detection_types(db, _)
