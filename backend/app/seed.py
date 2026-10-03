"""기본 데이터 넣기

    python -m app.seed --admin-password '비밀번호'            # 기본 데이터 + 첫 관리자
    python -m app.seed --admin-password '비밀번호' --demo     # + 화면 시연용 예시 데이터 (시연 회원도 같은 비밀번호)
    python -m app.seed --create-tables ...                    # schema.sql 대신 모델로 테이블 만들기 (개발용)

이미 있는 데이터(같은 code · 이름)는 건너뛰므로 여러 번 실행해도 된다.
"""

import argparse
from pathlib import Path
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import Base, SessionLocal, engine
from .models import (
    ActionType,
    AlertRule,
    Camera,
    CameraType,
    DetectionType,
    Equipment,
    EquipStatus,
    EquipType,
    EquipmentDailyLog,
    Event,
    EventAction,
    EventSnapshot,
    EventStatus,
    Organization,
    OrgType,
    ReleaseCheckItem,
    Roi,
    RoiRule,
    Role,
    Severity,
    User,
    UserStatus,
    Work,
    WorkAssignment,
    Worker,
    WorkStatus,
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
    ("OO건설", True, ["현장소장실", "안전팀", "공사팀", "공무팀", "양중팀"]),
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


# 시연용 회원 (아이디, 이름, 직급, 회사, 부서, 역할, 상태) — frontend 목업과 같은 이름
DEMO_USERS = [
    ("han.jh", "한지훈", "소장", "OO건설", "현장소장실", Role.ADMIN, UserStatus.ACTIVE),
    ("oh.sy", "오세영", "주임", "OO건설", "안전팀", Role.MANAGER, UserStatus.ACTIVE),
    ("park.jw", "박진우", "차장", "OO건설", "양중팀", Role.MANAGER, UserStatus.ACTIVE),
    ("jung.ms", "정민수", "부장", "OO건설", "공사팀", Role.MANAGER, UserStatus.ACTIVE),
    ("kim.cs", "김철수", "과장", "OO건설", "공사팀", Role.MANAGER, UserStatus.ACTIVE),
    ("yoon.gr", "윤가람", "주임", "OO건설", "공무팀", Role.VIEWER, UserStatus.LOCKED),
    ("lee.sj", "이수진", "대리", "대한골조", None, Role.MANAGER, UserStatus.PENDING),
    ("jang.mh", "장민호", "주임", "한빛토건", None, Role.VIEWER, UserStatus.PENDING),
    ("baek.sh", "백승현", "기사", "세진크레인", None, Role.MANAGER, UserStatus.PENDING),
]

# 이름, 회사, 직종, 생년월일, 특별관리 사유(없으면 None)
DEMO_WORKERS = [
    ("김OO", "세진크레인", "TC 운전원", date(1975, 3, 12), None),
    ("이OO", "세진크레인", "TC 운전원", date(1979, 8, 1), None),
    ("박OO", "세진크레인", "TC 운전원", date(1982, 11, 20), None),
    ("정OO", "대한골조", "형틀목공", date(1958, 4, 2), "고령 · 고혈압"),
    ("최OO", "대한골조", "형틀목공", date(1986, 6, 9), None),
    ("강OO", "대한골조", "신호수", date(1990, 1, 15), None),
    ("조OO", "대한골조", "철근공", date(1999, 9, 30), "신규 투입 (7일 이내)"),
    ("윤OO", "한빛토건", "굴착기 운전원", date(1971, 2, 5), None),
    ("장OO", "한빛토건", "보통인부", date(1962, 12, 24), "고령"),
    ("임OO", "한빛토건", "신호수", date(1988, 7, 7), None),
    ("한OO", "우리설비", "펌프카 운전원", date(1980, 5, 18), None),
    ("오OO", "우리설비", "타설공", date(1994, 10, 3), None),
    ("서OO", "우리설비", "지게차 운전원", date(1977, 4, 27), None),
    ("신OO", "대한골조", "형틀목공", date(1966, 8, 14), "고혈압"),
]

# 이름, 종류, 구역, 운전원, 상태
DEMO_EQUIPMENT = [
    ("TC 1호기", EquipType.TC, "101동 갱폼 인양구역", "김OO", EquipStatus.RUNNING),
    ("TC 2호기", EquipType.TC, "102동 대형거푸집구역", "이OO", EquipStatus.RUNNING),
    ("TC 3호기", EquipType.TC, "Sector A 토공", "박OO", EquipStatus.RUNNING),
    ("굴착기 01", EquipType.EXCAVATOR, "Sector A 토공", "윤OO", EquipStatus.RUNNING),
    ("펌프카 01", EquipType.PUMP_CAR, "102동 대형거푸집구역", "한OO", EquipStatus.IDLE),
    ("지게차 01", EquipType.FORKLIFT, "외곽 야적장", "서OO", EquipStatus.MAINTENANCE),
]

# 구역, 작업 이름, 담당자 아이디, 상태, 작업자
DEMO_WORKS = [
    ("101동 갱폼 인양구역", "갱폼 인양 (12층)", "park.jw", WorkStatus.IN_PROGRESS, ["정OO", "최OO", "강OO"]),
    ("102동 대형거푸집구역", "거푸집 설치", "kim.cs", WorkStatus.IN_PROGRESS, ["신OO", "조OO"]),
    ("102동 대형거푸집구역", "슬래브 타설", "kim.cs", WorkStatus.PLANNED, ["오OO"]),
    ("Sector A 토공", "터파기 · 흙막이", "jung.ms", WorkStatus.IN_PROGRESS, ["장OO", "임OO"]),
    ("외곽 야적장", "자재 반입 정리", "oh.sy", WorkStatus.DONE, []),
]

# 카메라 번호, ROI 이름, 다각형(화면 비율 좌표), 덮어쓸 규칙 [(감지 code, 판정 기준, 심각도)]
DEMO_ROIS = [
    (1, "갱폼 인양 하부", [[0.52, 0.30], [0.86, 0.30], [0.90, 0.95], [0.48, 0.95]], [("NO_HELMET", "0.60", Severity.HIGH)]),
    (2, "TC 2호기 선회 반경", [[0.30, 0.20], [0.95, 0.20], [0.95, 0.90], [0.30, 0.90]], [("LOAD_OVERHEAD_WORKER", "0.60", None)]),
    (3, "흙막이 상부 접근금지", [[0.05, 0.55], [0.60, 0.50], [0.65, 0.80], [0.05, 0.85]], [("ZONE_INTRUSION", None, Severity.HIGH)]),
    (4, "자재 적치구역", [[0.10, 0.40], [0.70, 0.40], [0.70, 0.90], [0.10, 0.90]], []),
]

# (몇 시 몇 분, 카메라 번호(0=없음), ROI 쓰는지, 종류, 심각도, 신뢰도, 상태, 처리 메모)
DEMO_EVENTS = [
    ("09:05", 4, True, "ZONE_DWELL", Severity.MEDIUM, "0.74", EventStatus.DONE, "자재 정리 인원 5분 초과 체류. 작업 반장에게 교대 지시"),
    ("10:12", 2, False, "EQUIPMENT_PROXIMITY", Severity.HIGH, "0.87", EventStatus.DONE, "펌프카 붐 하부 출입 인원 이격, 유도원 배치"),
    ("11:40", 0, False, "WEATHER", Severity.MEDIUM, None, EventStatus.DONE, "순간풍속 10m/s. 인양 작업 20분 중지 후 재개"),
    ("13:22", 1, False, "NO_VEST", Severity.LOW, "0.88", EventStatus.DONE, "현장 지적 후 착용 확인"),
    ("13:41", 4, False, "NO_HELMET", Severity.LOW, "0.91", EventStatus.FALSE, "자재 위 둥근 물체를 사람 머리로 오인. 학습 데이터로 보냄"),
    ("13:58", 1, True, "ZONE_INTRUSION", Severity.MEDIUM, "0.78", EventStatus.DONE, "갱폼 하부 출입 인원 퇴거 조치"),
    ("14:28", 3, False, "GROUND_SUBSIDENCE", Severity.MEDIUM, "0.96", EventStatus.ACK, "흙막이 배면 균열 확인 중. 계측팀 호출"),
    ("14:32", 2, False, "NO_SIGNALMAN", Severity.HIGH, "0.85", EventStatus.NEW, None),
    ("14:35", 1, False, "LOAD_OVERHEAD_WORKER", Severity.HIGH, "0.82", EventStatus.NEW, None),
]


SNAPSHOT_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1920 1080">
<rect width="1920" height="1080" fill="#14202e"/><rect y="640" width="1920" height="440" fill="#1b2633"/>
<rect x="{x1}" y="{y1}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="8"/>
<rect x="{x1}" y="{ty}" width="{lw}" height="56" fill="{color}"/>
<text x="{tx}" y="{ty2}" font-family="Malgun Gothic, sans-serif" font-size="36" font-weight="700" fill="#0c1016">{label}</text>
<text x="40" y="70" font-family="Consolas, monospace" font-size="40" fill="#ffffff">{camera} · {time}</text>
<text x="40" y="1040" font-family="Malgun Gothic, sans-serif" font-size="30" fill="#8e9aab">시연용 예시 스냅샷 (실제 카메라 이미지 아님)</text>
</svg>"""
SEVERITY_COLOR = {Severity.HIGH: "#ff5d5d", Severity.MEDIUM: "#ffb020", Severity.LOW: "#3ddc84"}


def write_snapshot(snapshot_dir: Path, rel: str, bbox, label: str, camera: str, at: datetime, sev: Severity) -> None:
    """탐지 박스를 그린 예시 스냅샷 파일을 만든다 (진짜 스냅샷은 AI 탐지 프로그램이 저장)"""
    x1, y1, x2, y2 = bbox
    path = snapshot_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SNAPSHOT_SVG.format(
        x1=x1, y1=y1, w=x2 - x1, h=y2 - y1, ty=y1 - 56, ty2=y1 - 16, tx=x1 + 12, lw=len(label) * 38 + 24,
        color=SEVERITY_COLOR[sev], label=label, camera=camera, time=f"{at:%Y.%m.%d %H:%M:%S}",
    ), encoding="utf-8")


def seed_demo(db: Session, password: str, snapshot_dir: Path | None = None) -> None:
    """관제 · 이벤트 · 관리 화면을 시연할 만큼의 예시 (frontend 목업과 같은 이름).
    시연 회원은 모두 password 로 로그인할 수 있다. snapshot_dir 를 주면 예시 스냅샷 이미지도 만든다."""
    today = date.today()
    now = datetime.combine(today, datetime.min.time())
    orgs = {(o.name, o.parent_id): o for o in db.scalars(select(Organization))}
    company = {name: o for (name, parent), o in orgs.items() if parent is None}

    # ---------------- 회원
    pw_hash = hash_password(password)  # bcrypt 는 느려서 한 번만 계산해 같이 쓴다
    admin = db.scalar(select(User).where(User.role == Role.ADMIN).order_by(User.id))
    users = {}
    for i, (login_id, name, position, comp, dept, role, status) in enumerate(DEMO_USERS):
        org = orgs.get((dept, company[comp].id)) if dept else company[comp]
        active = status in (UserStatus.ACTIVE, UserStatus.LOCKED)
        users[login_id] = get_or_create(
            db, User, {"login_id": login_id}, name=name, position=position, org_id=org.id, role=role, status=status,
            password_hash=pw_hash, failed_login_count=5 if status == UserStatus.LOCKED else 0,
            approved_by=admin.id if admin and active else None, approved_at=now - timedelta(days=30 - i) if active else None,
            last_login_at=now - timedelta(days=i % 3, hours=-8 - i) if status == UserStatus.ACTIVE else None,
        )

    # ---------------- 구역 · 작업자 · 장비
    zones = {name: get_or_create(db, WorkZone, {"name": name}) for name in ZONES}
    workers = {
        name: get_or_create(db, Worker, {"name": name}, company=comp, job_type=job, birth_date=birth,
                            is_special_care=reason is not None, special_reason=reason)
        for name, comp, job, birth, reason in DEMO_WORKERS
    }
    equipment = {
        name: get_or_create(db, Equipment, {"name": name}, equip_type=kind, work_zone_id=zones[zone].id,
                            operator_id=workers[op].id, status=st)
        for name, kind, zone, op, st in DEMO_EQUIPMENT
    }
    recorder = users["oh.sy"]
    for eq in equipment.values():
        for back in range(3):  # 최근 3일 일일 기록
            get_or_create(db, EquipmentDailyLog, {"equipment_id": eq.id, "log_date": today - timedelta(days=back)},
                          status=eq.status if back == 0 else EquipStatus.RUNNING, recorded_by=recorder.id,
                          note="일일 점검 이상 없음" if eq.status != EquipStatus.MAINTENANCE or back else "유압 호스 교체 중")

    # ---------------- 오늘 작업 · 배정
    for zone, name, manager, st, names in DEMO_WORKS:
        work = get_or_create(db, Work, {"name": name, "work_date": today}, work_zone_id=zones[zone].id,
                             manager_id=users[manager].id, status=st)
        for wname in names:
            if not db.get(WorkAssignment, (work.id, workers[wname].id, today)):
                db.add(WorkAssignment(work_id=work.id, worker_id=workers[wname].id, assigned_date=today))

    # ---------------- 카메라 (1페이지 현장 4대 · 2페이지 TC 3대)
    cams = []
    for i, zone in enumerate(ZONES[:4], start=1):
        cams.append(get_or_create(db, Camera, {"name": f"CAM_000{i}"}, work_zone_id=zones[zone].id,
                                  camera_type=CameraType.FIXED, view_page=1, view_slot=i,
                                  stream_url=f"rtsp://192.168.0.{30 + i}:554/stream1", location_desc=f"{zone} 가설울타리 위"))
    for i in (1, 2, 3):
        tc = equipment[f"TC {i}호기"]
        get_or_create(db, Camera, {"name": f"TC{i}_CAM"}, equipment_id=tc.id, work_zone_id=tc.work_zone_id,
                      camera_type=CameraType.TC, view_page=2, view_slot=i, location_desc=f"TC {i}호기 트롤리 하부")

    # ---------------- ROI · ROI별 규칙
    types = {t.code: t for t in db.scalars(select(DetectionType))}
    rois = {}
    for cam_no, name, polygon, rules in DEMO_ROIS:
        cam = cams[cam_no - 1]
        roi = get_or_create(db, Roi, {"camera_id": cam.id, "name": name}, work_zone_id=cam.work_zone_id, polygon=polygon)
        rois[cam_no] = roi
        for code, conf, sev in rules:
            get_or_create(db, RoiRule, {"roi_id": roi.id, "detection_type_id": types[code].id},
                          min_confidence=Decimal(conf) if conf else None, severity=sev)

    # ---------------- 이벤트 · 스냅샷 · 처리 기록 (이미 있으면 건너뜀)
    if db.scalar(select(Event.id).limit(1)):
        return
    handler = users["oh.sy"]
    for hm, cam_no, use_roi, code, sev, conf, st, memo in DEMO_EVENTS:
        h, m = map(int, hm.split(":"))
        at = now + timedelta(hours=h, minutes=m)
        event = Event(
            camera_id=cams[cam_no - 1].id if cam_no else None, roi_id=rois[cam_no].id if use_roi else None,
            detection_type_id=types[code].id, severity=sev, confidence=Decimal(conf) if conf else None,
            bbox=[820, 310, 1040, 720] if cam_no else None, status=st, detected_at=at,
        )
        if cam_no:
            rel = f"{today:%Y%m%d}/{code.lower()}_{hm.replace(':', '')}.svg"
            event.snapshots.append(EventSnapshot(image_path="snapshots/" + rel, created_at=at))
            if snapshot_dir:
                cam = cams[cam_no - 1]
                write_snapshot(snapshot_dir, rel, event.bbox, f"{types[code].label} {float(conf):.0%}", cam.name, at, sev)

        def act(kind, minutes, **kw):
            event.actions.append(EventAction(user_id=handler.id, action_type=kind,
                                             created_at=at + timedelta(minutes=minutes), **kw))

        if st != EventStatus.NEW:
            act(ActionType.ACK, 1)
        if st == EventStatus.DONE:
            for n, item in enumerate(types[code].check_items, start=2):  # 해제 항목을 모두 허가해야 처리완료
                act(ActionType.PERMIT, n, check_item_id=item.id)
            act(ActionType.RESOLVE, 10, memo=memo)
        elif st == EventStatus.FALSE:
            act(ActionType.FALSE_ALARM, 3, memo=memo)
        elif st == EventStatus.ACK:
            act(ActionType.NOTE, 4, memo=memo)
        db.add(event)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--create-tables", action="store_true", help="모델로 테이블 만들기 (없는 테이블만)")
    p.add_argument("--admin-id", default="choi.dh")
    p.add_argument("--admin-password", help="첫 관리자 비밀번호 (주면 관리자 계정을 만듦)")
    p.add_argument("--demo", action="store_true", help="시연용 구역 · 카메라 · 이벤트 넣기")
    args = p.parse_args()
    if args.demo and not args.admin_password:
        p.error("--demo 는 --admin-password 와 같이 써야 합니다 (시연 회원 비밀번호로도 씀)")

    if args.create_tables:
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_base(db)
        if args.admin_password:
            seed_admin(db, args.admin_id, args.admin_password)
        if args.demo:
            seed_demo(db, args.admin_password, settings.snapshot_dir)
        db.commit()
    print("완료")


if __name__ == "__main__":
    main()
