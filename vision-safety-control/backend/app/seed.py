"""기본 데이터 넣기

    python -m app.seed --admin-password '비밀번호'            # 기본 데이터 + 첫 관리자
    python -m app.seed --admin-password '비밀번호' --demo     # + 화면 시연용 예시 데이터 (시연 회원도 같은 비밀번호)
    python -m app.seed --create-tables ...                    # schema.sql 대신 모델로 테이블 만들기 (개발용)
    python -m app.seed --demo-photos                          # 사진이 없는 작업자에게 예시 사진(그림) 넣기

이미 있는 데이터(같은 code · 이름)는 건너뛰므로 여러 번 실행해도 된다.
"""

import argparse
import random
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
    Education,
    EduType,
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
    REQUIRED_GENERAL_EDU,
    ReleaseCheckItem,
    SpecialReason,
    Roi,
    RoiRule,
    Role,
    Severity,
    User,
    UserStatus,
    Work,
    WorkAssignment,
    Worker,
    WorkerEducation,
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

# 구역 이름, 배치도 위 사각형 (왼쪽, 위, 너비, 높이 · 0~1 비율). 앞의 4곳에 CAM_0001~0004 가 달린다
ZONES = [
    ("101동 갱폼 인양구역", (0.06, 0.08, 0.36, 0.38)),
    ("102동 대형거푸집구역", (0.55, 0.08, 0.38, 0.38)),
    ("Sector A 토공", (0.63, 0.62, 0.18, 0.30)),
    ("외곽 야적장", (0.84, 0.62, 0.13, 0.30)),
    ("중앙 자재하역장", (0.38, 0.62, 0.21, 0.30)),
    ("103동 외벽 인양구역", (0.06, 0.66, 0.28, 0.28)),
]

# 안전교육 목록 (구분, 이름). 기초 4종은 모두 이수해야 화면에서 이수로 본다.
EDUCATIONS = [
    *[(EduType.GENERAL, name) for name in REQUIRED_GENERAL_EDU],
    (EduType.SPECIAL, "밀폐공간 작업"),
    (EduType.SPECIAL, "비계 조립·해체 작업"),
    (EduType.SPECIAL, "거푸집 동바리 조립·해체 작업"),
    (EduType.SPECIAL, "타워크레인 신호 작업"),
    (EduType.SPECIAL, "건설용 리프트 · 곤돌라 작업"),
]


def rect(x, y, w, h):
    return [[x, y], [round(x + w, 3), y], [round(x + w, 3), round(y + h, 3)], [x, round(y + h, 3)]]


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

    for kind, name in EDUCATIONS:
        get_or_create(db, Education, {"name": name}, edu_type=kind)

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
    db.flush()  # 이어서 넣는 시연 데이터가 이 관리자를 승인자 · 지정한 사람으로 찾을 수 있게
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

# 이름, 회사, 직종, 연락처, 생년월일, 현장 투입일(오늘부터 며칠 전), 특별관리 (사유, 메모, 지정 며칠 전, 지정한 사람), 이수 교육
G = "건설업 기초안전보건교육"
DEMO_WORKERS = [
    ("김영수", "대한골조", "형틀목공", "010-2231-0457", date(1962, 3, 5), 120,
     ([SpecialReason.ELDERLY], "고소작업 배치 금지", 53, "oh.sy"), [G, "거푸집 동바리 조립·해체 작업"]),
    ("이정호", "대한골조", "철근공", "010-8812-3390", date(1984, 7, 19), 90, None, [G]),
    ("박상철", "대한골조", "형틀목공", "010-4410-7721", date(1970, 11, 2), 200,
     ([SpecialReason.HYPERTENSION], "9월 건강검진 혈압 160/100", 75, None), [G]),
    ("서준기", "대한골조", "타설공", "010-6603-1184", date(1975, 1, 28), 60,
     ([SpecialReason.HYPERTENSION], "혈압약 복용 중", 18, None), [G]),
    ("최민재", "세진크레인", "신호수", "010-3345-9012", date(1991, 9, 14), 150, None, [G, "타워크레인 신호 작업"]),
    ("김창식", "세진크레인", "TC 운전원", "010-9020-4471", date(1977, 5, 30), 300, None, [G, "타워크레인 신호 작업"]),
    ("이상훈", "세진크레인", "TC 운전원", "010-2754-3318", date(1980, 12, 9), 280, None, [G]),
    ("박성민", "세진크레인", "TC 운전원", "010-6631-0925", date(1983, 4, 22), 260, None, [G]),
    ("응우옌 반 남", "한빛토건", "보통인부", "010-7781-2035", date(1996, 2, 11), 3,
     ([SpecialReason.NEW], "한국어 소통 서툼 · 통역 앱 사용", 3, "oh.sy"), [G]),
    ("정대호", "한빛토건", "굴착기 운전원", "010-5512-6630", date(1972, 8, 3), 180, None, [G]),
    ("오병철", "한빛토건", "보통인부", "010-2298-5543", date(1959, 6, 17), 400,
     ([SpecialReason.ELDERLY], None, 31, "oh.sy"), [G]),
    ("한상우", "우리설비", "배관공", "010-4067-8821", date(1998, 10, 25), 1,
     ([SpecialReason.NEW], None, 1, "oh.sy"), []),
    ("윤재석", "우리설비", "지게차 운전원", "010-3170-5582", date(1979, 3, 8), 210, None, [G]),
]

# 이름, 종류, 등록번호, 제원, 소속 회사, 구역, 운전원, 상태
DEMO_EQUIPMENT = [
    ("T-CRN-01 · 1호기", EquipType.TC, "TC-2024-0117", "T형 · 지브 55m", "세진크레인", "101동 갱폼 인양구역", "김창식", EquipStatus.RUNNING),
    ("T-CRN-02 · 2호기", EquipType.TC, "TC-2024-0118", "러핑 · 지브 50m", "세진크레인", "102동 대형거푸집구역", "이상훈", EquipStatus.IDLE),
    ("M-CRN-01 · 3호기", EquipType.TC, "TC-2023-0342", "T형 · 지브 48m", "세진크레인", "중앙 자재하역장", "박성민", EquipStatus.RUNNING),
    ("T-CRN-03 · 4호기", EquipType.TC, "TC-2024-0121", "러핑 · 지브 46m", "세진크레인", "103동 외벽 인양구역", None, EquipStatus.IDLE),
    ("PUMP-01", EquipType.PUMP_CAR, "경기 80가 4412", "콘크리트 펌프카 · 붐 42m", "OO펌프", "101동 갱폼 인양구역", "서준기", EquipStatus.RUNNING),
    ("MIX-07", EquipType.MIXER_TRUCK, "경기 91사 2207", "6㎥", "OO레미콘", "101동 갱폼 인양구역", None, EquipStatus.RUNNING),
    ("MIX-12", EquipType.MIXER_TRUCK, "경기 91사 2212", "6㎥", "OO레미콘", "101동 갱폼 인양구역", None, EquipStatus.IDLE),
    ("EXC_01", EquipType.EXCAVATOR, "EX-2021-0098", "0.8㎥", "한빛토건", "Sector A 토공", "정대호", EquipStatus.MAINTENANCE),
    ("DUMP-03", EquipType.DUMP_TRUCK, "경기 85바 7703", "15t", "OO운수", "외곽 야적장", None, EquipStatus.RUNNING),
    ("FORK-01", EquipType.FORKLIFT, "FL-2020-0031", "3t", "우리설비", None, "윤재석", EquipStatus.BROKEN),
]

# 구역, 작업 이름, 담당자 아이디, 시작(오늘부터 며칠), 종료(며칠 · None=하루), 상태, 작업 내용, 작업자
DEMO_WORKS = [
    ("101동 갱폼 인양구역", "101동 갱폼 인양", "park.jw", -11, 12, WorkStatus.IN_PROGRESS,
     "TC-1 양중. 인양 중 하부 출입 통제, 신호수 1명 상시 배치.", ["박상철", "최민재", "김창식"]),
    ("101동 갱폼 인양구역", "101동 3층 슬래브 타설", "kim.cs", 0, None, WorkStatus.IN_PROGRESS,
     "펌프카 PUMP-01 붐 하부 출입 금지.", ["서준기"]),
    ("102동 대형거푸집구역", "102동 대형거푸집 설치", "park.jw", -5, 7, WorkStatus.STOPPED,
     "TC-2 양중 연계. 신호수 1명 필수 배치. 하부 출입 통제.", ["김영수", "이정호"]),
    ("Sector A 토공", "Sector A 터파기", "jung.ms", -18, 28, WorkStatus.IN_PROGRESS,
     "굴착기 작업반경 5m 출입 통제. 흙막이 배면 균열 수시 확인.", ["응우옌 반 남", "정대호"]),
    ("중앙 자재하역장", "자재 하역", "park.jw", 0, None, WorkStatus.IN_PROGRESS, "TC-3 하역. 인양물 직하부 출입 금지.", []),
    ("103동 외벽 인양구역", "103동 외벽 배관", "kim.cs", 3, 17, WorkStatus.PLANNED, "외벽 배관 인양 예정.", []),
    ("외곽 야적장", "야적장 정리", "jung.ms", 0, None, WorkStatus.IN_PROGRESS, "덤프 운행로 정리.", ["오병철"]),
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
    ("11:40", 0, False, "WEATHER", Severity.MEDIUM, None, EventStatus.DONE, "순간풍속 15m/s. 인양 작업 20분 중지 후 재개"),
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

    # ---------------- 구역 · 작업자 · 교육 · 장비
    zones = {name: get_or_create(db, WorkZone, {"name": name}, plan_polygon=rect(*box)) for name, box in ZONES}
    edu = {e.name: e for e in db.scalars(select(Education))}
    workers = {}
    for name, comp, job, phone, birth, since_days, special, edus in DEMO_WORKERS:
        reasons, memo, marked_days, marked_by = special or (None, None, None, None)
        w = get_or_create(
            db, Worker, {"name": name}, company=comp, job_type=job, phone=phone, birth_date=birth,
            start_date=today - timedelta(days=since_days), is_special_care=special is not None,
            special_reasons=[r.value for r in reasons] if reasons else None, special_memo=memo,
            special_since=today - timedelta(days=marked_days) if special else None,
            special_by=(users[marked_by].id if marked_by else admin.id if admin else None) if special else None,
        )
        workers[name] = w
        if not w.educations:
            for k, edu_name in enumerate(edus):
                w.educations.append(WorkerEducation(edu_id=edu[edu_name].id,
                                                    completed_date=w.start_date - timedelta(days=1 + k * 30)))
    equipment = {
        name: get_or_create(db, Equipment, {"name": name}, equip_type=kind, reg_no=reg_no, spec=spec, company=comp,
                            work_zone_id=zones[zone].id if zone else None,
                            operator_id=workers[op].id if op else None, status=st)
        for name, kind, reg_no, spec, comp, zone, op, st in DEMO_EQUIPMENT
    }
    recorder = users["oh.sy"]
    for eq in equipment.values():
        for back in range(3):  # 최근 3일 일일 기록 (아침 7시 무렵 운전 전 점검)
            day = today - timedelta(days=back)
            broken_today = eq.status in (EquipStatus.MAINTENANCE, EquipStatus.BROKEN) and back == 0
            get_or_create(db, EquipmentDailyLog, {"equipment_id": eq.id, "log_date": day},
                          status=eq.status if back == 0 else EquipStatus.RUNNING, recorded_by=recorder.id,
                          inspected_at=None if broken_today else datetime.combine(day, datetime.min.time()) + timedelta(hours=7, minutes=10 + eq.id % 20),
                          note="유압 호스 교체 중" if broken_today else "운전 전 점검 이상 없음")

    # ---------------- 작업 · 배정
    for zone, name, manager, start, end, st, desc, names in DEMO_WORKS:
        work = get_or_create(db, Work, {"name": name}, work_zone_id=zones[zone].id, manager_id=users[manager].id,
                             start_date=today + timedelta(days=start),
                             end_date=today + timedelta(days=end) if end is not None else None,
                             status=st, description=desc)
        for wname in names:
            if not db.scalar(select(WorkAssignment).filter_by(work_id=work.id, worker_id=workers[wname].id)):
                db.add(WorkAssignment(work_id=work.id, worker_id=workers[wname].id, assigned_date=work.start_date))

    # ---------------- 카메라 (1페이지 현장 4대 · 2페이지 TC 4대)
    # 배치도 위치: 구역 아래쪽 가운데에서 구역(위쪽)을 바라본다. TC CAM 은 크레인에 달려 있어 위치를 두지 않는다
    cams = []
    for i, (zone, (x, y, w, h)) in enumerate(ZONES[:4], start=1):
        cams.append(get_or_create(db, Camera, {"name": f"CAM_000{i}"}, work_zone_id=zones[zone].id,
                                  camera_type=CameraType.FIXED, view_page=1, view_slot=i,
                                  stream_url=f"rtsp://192.168.0.{30 + i}:554/stream1", location_desc=f"{zone} 가설울타리 위",
                                  plan_x=Decimal(str(round(x + w / 2, 3))), plan_y=Decimal(str(round(min(y + h + 0.03, 0.97), 3))), plan_dir=0))
    tcs = [e for e in equipment.values() if e.equip_type == EquipType.TC]
    for i, tc in enumerate(tcs, start=1):
        get_or_create(db, Camera, {"name": f"TC{i}_CAM"}, equipment_id=tc.id, work_zone_id=tc.work_zone_id,
                      camera_type=CameraType.TC, view_page=2, view_slot=i, location_desc=f"{tc.name} 트롤리 하부")

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


# 지난 기록 만들 때 쓰는 값: 감지 유형별 하루 빈도 가중치, 시간대 가중치 (7~18시, 10시 · 14시 무렵 많음)
HISTORY_TYPE_WEIGHT = {
    "ZONE_INTRUSION": 9, "EQUIPMENT_PROXIMITY": 7, "NO_HELMET": 6, "NO_VEST": 4, "NO_SIGNALMAN": 4,
    "ZONE_DWELL": 3, "TC_HOOK_PROXIMITY": 3, "LOAD_OVERHEAD_WORKER": 2, "GROUND_SUBSIDENCE": 1, "WEATHER": 1,
}
HISTORY_HOUR_WEIGHT = {7: 2, 8: 4, 9: 6, 10: 8, 11: 6, 12: 2, 13: 6, 14: 9, 15: 7, 16: 5, 17: 3, 18: 1}
HISTORY_MEMOS = [
    "현장 확인 후 작업자 이격 조치", "작업 반장에게 전달, 재교육 예정", "통제선 보강", "유도원 배치 후 작업 재개",
    "인양 중지 후 신호수 배치", "보호구 착용 확인", "출입 통제 후 재개",
]


def seed_history(db: Session, days: int) -> int:
    """오늘 전 days 일 동안의 지난 이벤트 (통계 · 추이 화면 시연용). 이미 지난 기록이 있으면 건너뛴다.
    난수 시드를 고정해서 몇 번을 넣어도 같은 데이터가 나온다."""
    today = datetime.combine(date.today(), datetime.min.time())
    if days <= 0 or db.scalar(select(Event.id).where(Event.detected_at < today).limit(1)):
        return 0
    rnd = random.Random(20261005)
    types = {t.code: t for t in db.scalars(select(DetectionType))}
    rules = {r.detection_type_id: r for r in db.scalars(select(AlertRule))}
    cams = db.scalars(select(Camera).where(Camera.camera_type == CameraType.FIXED).order_by(Camera.id)).all()
    handlers = db.scalars(select(User).where(User.role.in_([Role.MANAGER, Role.ADMIN]), User.status == UserStatus.ACTIVE)).all()
    codes, code_w = zip(*[(c, w) for c, w in HISTORY_TYPE_WEIGHT.items() if c in types])
    hours, hour_w = zip(*HISTORY_HOUR_WEIGHT.items())
    made = 0
    for back in range(days, 0, -1):
        day = today - timedelta(days=back)
        # 주말은 적게, 시간이 지날수록 조금씩 줄어들게 (안전 조치 효과)
        base = 5 if day.weekday() >= 5 else 13
        n = max(1, round(base * (0.8 + 0.4 * back / days) + rnd.randint(-3, 3)))
        for _ in range(n):
            code = rnd.choices(codes, code_w)[0]
            t = types[code]
            at = day + timedelta(hours=rnd.choices(hours, hour_w)[0], minutes=rnd.randrange(60), seconds=rnd.randrange(60))
            rule = rules.get(t.id)
            event = Event(
                camera_id=None if code == "WEATHER" else rnd.choice(cams).id,
                detection_type_id=t.id,
                severity=rule.default_severity if rule else Severity.MEDIUM,
                confidence=None if code == "WEATHER" else Decimal(str(round(rnd.uniform(0.72, 0.98), 3))),
                status=EventStatus.FALSE if rnd.random() < 0.1 else EventStatus.DONE,
                detected_at=at,
            )
            who = rnd.choice(handlers).id
            minutes = rnd.randint(2, 6)
            event.actions.append(EventAction(user_id=who, action_type=ActionType.ACK, created_at=at + timedelta(minutes=minutes)))
            if event.status == EventStatus.FALSE:
                event.actions.append(EventAction(user_id=who, action_type=ActionType.FALSE_ALARM, memo="오탐 · 학습 데이터로 보냄",
                                                 created_at=at + timedelta(minutes=minutes + rnd.randint(1, 4))))
            else:
                for item in t.check_items:  # 해제 항목을 모두 허가해야 처리완료
                    minutes += rnd.randint(1, 3)
                    event.actions.append(EventAction(user_id=who, action_type=ActionType.PERMIT, check_item_id=item.id,
                                                     created_at=at + timedelta(minutes=minutes)))
                event.actions.append(EventAction(user_id=who, action_type=ActionType.RESOLVE, memo=rnd.choice(HISTORY_MEMOS),
                                                 created_at=at + timedelta(minutes=minutes + rnd.randint(2, 15))))
            db.add(event)
            made += 1
    db.flush()
    return made


def seed_worker_photos(db: Session) -> int:
    """사진이 없는 작업자에게 예시 프로필 사진(안전모 · 조끼를 입은 작업자 그림)을 넣는다. 신호수는 빨간 조끼"""
    from . import photos
    from .demo_photos import draw_worker

    made = 0
    for w in db.scalars(select(Worker).where(Worker.is_active, Worker.photo_path.is_(None)).order_by(Worker.id)):
        w.photo_path = photos.save("workers", w.id, draw_worker(w.id, signalman="신호" in (w.job_type or "")))
        made += 1
    db.flush()
    return made


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--create-tables", action="store_true", help="모델로 테이블 만들기 (없는 테이블만)")
    p.add_argument("--admin-id", default="choi.dh")
    p.add_argument("--admin-password", help="첫 관리자 비밀번호 (주면 관리자 계정을 만듦)")
    p.add_argument("--demo", action="store_true", help="시연용 구역 · 카메라 · 이벤트 넣기")
    p.add_argument("--history-days", type=int, default=30, help="--demo 때 넣을 지난 이벤트 일수 (통계 화면용, 0 이면 안 넣음)")
    p.add_argument("--demo-photos", action="store_true", help="사진이 없는 작업자에게 예시 프로필 사진 넣기 (--demo 때는 저절로)")
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
            made = seed_history(db, args.history_days)
            if made:
                print(f"지난 {args.history_days}일 이벤트 {made}건을 넣었습니다")
        if args.demo or args.demo_photos:
            made = seed_worker_photos(db)
            if made:
                print(f"작업자 {made}명에게 예시 프로필 사진을 넣었습니다")
        db.commit()
    print("완료")


if __name__ == "__main__":
    main()
