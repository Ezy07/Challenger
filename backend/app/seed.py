"""기본 데이터 넣기

    python -m app.seed --admin-password '비밀번호'            # 기본 데이터 + 첫 관리자
    python -m app.seed --admin-password '비밀번호' --demo     # + 화면 시연용 예시 데이터
    python -m app.seed --create-tables ...                    # schema.sql 대신 모델로 테이블 만들기 (개발용)

이미 있는 데이터(같은 code · 이름)는 건너뛰므로 여러 번 실행해도 된다.
"""

import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import (
    AlertRule,
    Camera,
    CameraType,
    DetectionType,
    Equipment,
    EquipStatus,
    EquipType,
    Event,
    EventStatus,
    Organization,
    OrgType,
    ReleaseCheckItem,
    Role,
    Severity,
    User,
    UserStatus,
    Worker,
    WorkZone,
)
from .security import hash_password

# code, 이름, 기본 심각도, 판정 기준, 쿨다운(초), 해제 항목
DETECTION_TYPES = [
    ("ZONE_INTRUSION", "ROI 침범", Severity.MEDIUM, "0.70", 60, []),
    ("ZONE_DWELL", "ROI 체류 초과", Severity.MEDIUM, "0.70", 300, []),
    ("NO_SIGNALMAN", "신호수 미배치", Severity.HIGH, "0.75", 120, ["인양 중지", "신호수 배치"]),
    ("NO_HELMET", "안전모 미착용", Severity.MEDIUM, "0.80", 60, []),
    ("NO_VEST", "안전조끼 미착용", Severity.LOW, "0.80", 60, []),
    ("EQUIPMENT_PROXIMITY", "장비 근접", Severity.HIGH, "0.70", 30, ["장비 정지", "작업자 이격"]),
    ("TC_HOOK_PROXIMITY", "TC 후크 근접", Severity.HIGH, "0.70", 30, ["선회 정지", "작업자 대피"]),
    ("LOAD_OVERHEAD_WORKER", "직하부 작업자", Severity.HIGH, "0.70", 30, ["인양 중지", "직하부 대피", "반경 통제"]),
    ("GROUND_SUBSIDENCE", "지반침하 의심", Severity.MEDIUM, "0.85", 600, []),
    ("WEATHER", "기상 경보", Severity.MEDIUM, "0.00", 1800, []),
]

# 회사, 원청 여부, 부서
ORGS = [
    ("OO건설", True, ["안전팀", "공무팀", "양중팀"]),
    ("대한골조", False, []),
    ("한빛토건", False, []),
    ("세진크레인", False, []),
    ("우리설비", False, []),
]

ZONES = ["101동 갱폼 인양구역", "102동 대형거푸집구역", "Sector A 토공", "외곽 야적장", "중앙 자재하역장"]


def get_or_create(db: Session, model, where: dict, **values):
    obj = db.scalar(select(model).filter_by(**where))
    if obj:
        return obj
    obj = model(**where, **values)
    db.add(obj)
    db.flush()
    return obj


def seed_base(db: Session) -> None:
    for code, label, sev, conf, cooldown, items in DETECTION_TYPES:
        t = get_or_create(db, DetectionType, {"code": code}, label=label)
        get_or_create(
            db, AlertRule, {"detection_type_id": t.id},
            min_confidence=Decimal(conf), default_severity=sev, cooldown_sec=cooldown,
        )
        for i, title in enumerate(items, start=1):
            get_or_create(db, ReleaseCheckItem, {"detection_type_id": t.id, "title": title}, sort_order=i)

    for company, prime, depts in ORGS:
        c = get_or_create(db, Organization, {"type": OrgType.COMPANY, "name": company}, is_prime=prime)
        for d in depts:
            get_or_create(db, Organization, {"type": OrgType.DEPT, "name": d, "parent_id": c.id})


def seed_admin(db: Session, login_id: str, password: str) -> None:
    if db.scalar(select(User.id).where(User.login_id == login_id)):
        print(f"관리자 {login_id} 는 이미 있어서 건너뜀")
        return
    safety = db.scalar(select(Organization).where(Organization.name == "안전팀"))
    db.add(User(
        login_id=login_id, password_hash=hash_password(password), name="최동현", position="과장",
        org_id=safety.id if safety else None, role=Role.ADMIN, status=UserStatus.ACTIVE, approved_at=datetime.now(),
    ))
    print(f"관리자 {login_id} 를 만들었습니다")


def seed_demo(db: Session) -> None:
    """관제 · 이벤트 화면을 시연할 만큼의 예시 (frontend 목업과 같은 이름)"""
    zones = {name: get_or_create(db, WorkZone, {"name": name}) for name in ZONES}

    operators = [get_or_create(db, Worker, {"name": n}, company="세진크레인", job_type="TC 운전원") for n in ("김OO", "이OO", "박OO")]
    tcs = [
        get_or_create(
            db, Equipment, {"name": f"TC {i}호기"}, equip_type=EquipType.TC,
            work_zone_id=zones[ZONES[i - 1]].id, operator_id=operators[i - 1].id, status=EquipStatus.RUNNING,
        )
        for i in (1, 2, 3)
    ]
    get_or_create(db, Worker, {"name": "정OO"}, company="대한골조", job_type="형틀목공",
                  birth_date=date(1958, 4, 2), is_special_care=True, special_reason="고령 · 고혈압")

    cams = []
    for i, zone in enumerate(ZONES[:4], start=1):
        cams.append(get_or_create(db, Camera, {"name": f"CAM_000{i}"}, work_zone_id=zones[zone].id,
                                  camera_type=CameraType.FIXED, view_page=1, view_slot=i))
    for i, tc in enumerate(tcs, start=1):
        get_or_create(db, Camera, {"name": f"TC{i}_CAM"}, equipment_id=tc.id, work_zone_id=tc.work_zone_id,
                      camera_type=CameraType.TC, view_page=2, view_slot=i)

    if db.scalar(select(Event.id).limit(1)):
        return
    types = {t.code: t for t in db.scalars(select(DetectionType))}
    today = datetime.combine(date.today(), datetime.min.time())
    # (몇 시 몇 분, 카메라 번호(0=없음), 종류, 심각도, 신뢰도, 상태)
    samples = [
        ("09:05", 4, "ZONE_DWELL", Severity.MEDIUM, "0.74", EventStatus.DONE),
        ("10:12", 2, "EQUIPMENT_PROXIMITY", Severity.HIGH, "0.87", EventStatus.DONE),
        ("11:40", 0, "WEATHER", Severity.MEDIUM, None, EventStatus.DONE),
        ("13:22", 1, "NO_VEST", Severity.LOW, "0.88", EventStatus.DONE),
        ("13:41", 4, "NO_HELMET", Severity.LOW, "0.91", EventStatus.FALSE),
        ("13:58", 1, "ZONE_INTRUSION", Severity.MEDIUM, "0.78", EventStatus.DONE),
        ("14:28", 3, "GROUND_SUBSIDENCE", Severity.MEDIUM, "0.96", EventStatus.ACK),
        ("14:32", 2, "NO_SIGNALMAN", Severity.HIGH, "0.85", EventStatus.NEW),
        ("14:35", 1, "LOAD_OVERHEAD_WORKER", Severity.HIGH, "0.82", EventStatus.NEW),
    ]
    for hm, cam_no, code, sev, conf, st in samples:
        h, m = map(int, hm.split(":"))
        db.add(Event(
            camera_id=cams[cam_no - 1].id if cam_no else None, detection_type_id=types[code].id, severity=sev,
            confidence=Decimal(conf) if conf else None, status=st, detected_at=today + timedelta(hours=h, minutes=m),
        ))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--create-tables", action="store_true", help="모델로 테이블 만들기 (없는 테이블만)")
    p.add_argument("--admin-id", default="choi.dh")
    p.add_argument("--admin-password", help="첫 관리자 비밀번호 (주면 관리자 계정을 만듦)")
    p.add_argument("--demo", action="store_true", help="시연용 구역 · 카메라 · 이벤트 넣기")
    args = p.parse_args()

    if args.create_tables:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_base(db)
        if args.admin_password:
            seed_admin(db, args.admin_id, args.admin_password)
        if args.demo:
            seed_demo(db)
        db.commit()
    print("완료")


if __name__ == "__main__":
    main()
