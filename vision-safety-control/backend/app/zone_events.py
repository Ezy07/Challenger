"""YOLO 탐지 결과 → ROI 침범 · 체류 이벤트 (이벤트 로그 · 통계 화면에 쌓이는 데이터).

- ROI 목록 화면에서 구역마다 저장한 설정을 쓴다 (storage/roi-zones.json):
  · 침입 탐지 대상(targets): 고른 대상(사람 · 트럭)만 본다. 저장 전(없음)이거나 비어 있으면 이 구역은 판정하지 않음
  · 체류 시간(dwell): 0 이면 들어오자마자 ROI 침범(ZONE_INTRUSION), N초면 N초 넘게 머물 때 ROI 체류 초과(ZONE_DWELL)
  · 사용안함(intrusion=false) · 구역 사용 스위치 · 적용 시간이 꺼져 있으면 판정하지 않음
- 판정 기준 화면(8-8)의 값을 쓴다: confidence 가 기준 미만인 박스는 세지 않고, 사용을 끄면 판정하지 않고,
  쿨다운 · 심각도는 이벤트를 만들 때(events.create_event) 적용한다. 바꾸면 RULE_REFRESH_SEC 안에 반영된다.
- 발밑(박스 아래 가운데)이 구역 안이면 "들어와 있음". 구역이 겹치면 위험 > 통제 > 관리 > 안전 순으로 한 구역에만 센다.
  박스가 잠깐 끊겨도 GAP_SEC 까지는 계속 머문 것으로 본다.
  한 번 머무는 동안 이벤트는 한 번만 만든다 (나갔다 다시 들어오면 다시, 같은 경보는 쿨다운 동안 막힘).
- 이벤트가 생기면 그 순간 화면(ROI · 탐지 박스를 그린 JPEG)을 storage/snapshots/날짜/ 에 저장한다.
- 보는 사람이 없어도 판정할 구역이 있는 카메라는 계속 읽는다 (EVENT_WATCH=false 면 화면을 볼 때만 판정).
"""

import logging
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import vision
from .config import settings
from .database import SessionLocal
from .models import Camera, DetectionType, Roi
from .schemas import EventIn

log = logging.getLogger("uvicorn.error")

INTRUSION, DWELL = "ZONE_INTRUSION", "ZONE_DWELL"
LIVE_CODES = (INTRUSION, DWELL)  # 서버의 YOLO 판정이 실제로 만드는 감지 유형 (판정 기준 화면에 표시)
GAP_SEC = 2.0
RULE_REFRESH_SEC = 5


@dataclass(frozen=True)
class Rule:
    active: bool
    min_conf: float
    cooldown_sec: int


@dataclass
class Stay:
    since: float
    last_seen: float
    fired: bool = False


@dataclass(frozen=True)
class Trigger:
    camera_id: int
    zone: dict
    code: str
    box: vision.Box


def inside(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """점이 다각형 안인지 (반직선 교차 수)."""
    hit = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hit = not hit
        j = i
    return hit


def zone_code(zone: dict) -> str | None:
    """이 구역을 어떤 감지 유형으로 판정할지. 판정하지 않으면 None"""
    if not zone.get("targets") or zone.get("intrusion") is False:
        return None
    return DWELL if (zone.get("dwell") or 0) > 0 else INTRUSION


class Judge:
    """카메라 · 구역마다 '언제부터 들어와 있는지'를 기억한다. 탐지 스레드 하나에서만 부른다."""

    def __init__(self):
        self.stays: dict[tuple[int, int], Stay] = {}

    def observe(self, camera_id: int, zones: list[dict], boxes: list[vision.Box], width: int, height: int,
                rules: dict[str, Rule], now: float) -> list[Trigger]:
        out = []
        judged = []  # 판정하는 구역만, 우선순위(위험 > 통제 > 관리 > 안전) 순
        for zone in vision.by_priority(zones, lambda z: z["kind"]):
            code = zone_code(zone)
            rule = rules.get(code) if code else None
            if not rule or not rule.active:
                self.stays.pop((camera_id, zone["no"]), None)
                continue
            poly = [(x * width / vision.ROI_W, y * height / vision.ROI_H) for x, y in zone["points"]]
            judged.append((zone, code, rule, poly))
        # 발밑이 구역 여러 개에 겹치면 (통제구역 안의 위험구역 등) 우선순위가 가장 높은 구역 하나에만 센다
        hits_by_no: dict[int, list[vision.Box]] = {zone["no"]: [] for zone, *_ in judged}
        for b in boxes:
            for zone, _, rule, poly in judged:
                if b.name in zone["targets"] and b.conf >= rule.min_conf and inside((b.x1 + b.x2) / 2, b.y2, poly):
                    hits_by_no[zone["no"]].append(b)
                    break
        for zone, code, _, _ in judged:
            key = (camera_id, zone["no"])
            hits = hits_by_no[zone["no"]]
            stay = self.stays.get(key)
            if not hits:
                if stay and now - stay.last_seen > GAP_SEC:
                    del self.stays[key]
                continue
            if stay is None or now - stay.last_seen > GAP_SEC:
                stay = self.stays[key] = Stay(since=now, last_seen=now)
            stay.last_seen = now
            if not stay.fired and now - stay.since >= (zone.get("dwell") or 0):
                stay.fired = True
                out.append(Trigger(camera_id, zone, code, max(hits, key=lambda b: b.conf)))
        current = {z["no"] for z in zones}
        for key in [k for k in self.stays if k[0] == camera_id and k[1] not in current]:
            del self.stays[key]  # 꺼졌거나 지워진 구역
        return out


# ---------------------------------------------------------------- 판정 기준 (8-8)
def load_rules(db) -> dict[str, Rule]:
    from .routers.events import DEFAULT_RULE

    types = db.scalars(select(DetectionType).where(DetectionType.code.in_(LIVE_CODES))
                       .options(selectinload(DetectionType.rule)))
    out = {}
    for t in types:
        r = t.rule or DEFAULT_RULE
        out[t.code] = Rule(bool(r.is_active), float(r.min_confidence), int(r.cooldown_sec))
    return out


# ---------------------------------------------------------------- 이벤트 · 스냅샷 기록
def roi_id_for(db, camera_id: int, zone: dict) -> int:
    """그린 구역(JSON)을 DB roi 줄과 잇는다. 이름 "1번 타워크레인 하부 (위험구역)" 의 번호로 찾고, 없으면 만든다.
    이름을 안 정한 구역은 "1번 위험구역"."""
    prefix = f"{zone['no']}번 "
    name = f"{zone['no']}번 {zone['name']} ({zone['kind']})" if zone.get("name") else f"{zone['no']}번 {zone['kind']}"
    polygon = [[round(x / vision.ROI_W, 4), round(y / vision.ROI_H, 4)] for x, y in zone["points"]]
    roi = next((r for r in db.scalars(select(Roi).where(Roi.camera_id == camera_id)) if r.name.startswith(prefix)), None)
    if roi is None:
        cam = db.get(Camera, camera_id)
        roi = Roi(camera_id=camera_id, work_zone_id=cam.work_zone_id if cam else None, name=name, polygon=polygon)
        db.add(roi)
    else:
        roi.name, roi.polygon, roi.is_active = name, polygon, True
    db.commit()
    return roi.id


def save_snapshot(snap: vision.Snapshot, rois: list, camera_name: str, code: str, at: datetime) -> str | None:
    """그 순간 화면(ROI · 탐지 박스)을 JPEG 로 저장하고 "snapshots/..." 경로를 돌려준다."""
    jpeg = vision.render(snap, rois, True)
    if not jpeg:
        return None
    safe = re.sub(r"[^\w.-]", "_", camera_name)
    rel = f"{at:%Y%m%d}/{code.lower()}_{safe}_{at:%H%M%S}_{at.microsecond // 1000:03d}.jpg"
    path = settings.snapshot_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(jpeg)
    return "snapshots/" + rel


@dataclass
class Job:
    trigger: Trigger
    camera_name: str
    snap: vision.Snapshot
    rois: list
    at: datetime = field(default_factory=datetime.now)


def record(Session, job: Job):
    """규칙(판정 기준 · 쿨다운 · ROI별 규칙)을 적용해 이벤트를 만든다. 결과는 EventIngestOut"""
    from .routers.events import create_event

    t, box = job.trigger, job.trigger.box
    with Session() as db:
        body = EventIn(detection_type=t.code, camera_id=t.camera_id, roi_id=roi_id_for(db, t.camera_id, t.zone),
                       confidence=round(box.conf, 3), bbox=[box.x1, box.y1, box.x2, box.y2], detected_at=job.at)
        result = create_event(db, body, lambda: save_snapshot(job.snap, job.rois, job.camera_name, t.code, job.at))
    if result.created:
        log.info("이벤트 EV-%s: %s %s번 %s (%s %.0f%%)", result.event_id, job.camera_name, t.zone["no"],
                 vision.zone_title(t.zone), t.code, box.conf * 100)
    return result


# ---------------------------------------------------------------- 스레드
judge = Judge()
rules: dict[str, Rule] = {}
_jobs: queue.Queue[Job] = queue.Queue(maxsize=100)
_started = False


def on_detect(feed: vision.Feed, snap: vision.Snapshot) -> None:
    """탐지 스레드에서 프레임마다 불린다. DB · 파일 쓰기는 기록 스레드로 넘긴다."""
    if not rules:
        return
    zones = vision.zones_at(vision.roi_rows(), feed.camera_name, snap.video_time)
    height, width = snap.frame.shape[:2]
    for trig in judge.observe(feed.camera_id, zones, snap.boxes, width, height, rules, time.monotonic()):
        rois = [(z["no"], z["kind"], z["points"], vision.zone_title(z)) for z in zones]
        try:
            _jobs.put_nowait(Job(trig, feed.camera_name, snap, rois))
        except queue.Full:
            log.warning("이벤트 기록이 밀려 %s %s번 구역 이벤트를 버렸습니다", feed.camera_name, trig.zone["no"])


def _record_loop() -> None:
    while not vision.stopping():
        try:
            job = _jobs.get(timeout=1)
        except queue.Empty:
            continue
        try:
            record(SessionLocal, job)
        except HTTPException as exc:  # 그 사이 카메라가 지워진 경우 등
            log.warning("이벤트를 만들지 못했습니다: %s", exc.detail)
        except Exception:
            log.exception("이벤트를 기록하지 못했습니다")


def watched_cameras(db) -> dict[tuple[int, str], tuple[str, bool]]:
    """판정할 구역이 있는 카메라 → {(카메라 번호, 주소): (카메라 이름, 영상 파일인지)}"""
    from .routers.stream import source_of

    names = {r["camera"] for r in vision.roi_rows()
             if isinstance(r, dict) and r.get("enabled", True) is not False and zone_code(r)
             and (rule := rules.get(zone_code(r))) and rule.active}
    if not names:
        return {}
    out = {}
    cams = db.scalars(select(Camera).where(Camera.name.in_(names), Camera.is_active.is_(True),
                                           Camera.stream_url.is_not(None)))
    for cam in cams:
        found = source_of(cam.stream_url)
        if found:
            out[(cam.id, found[0])] = (cam.name, found[1])
    return out


def _watch_loop() -> None:
    global rules
    vision.detector.load()  # 처음이면 모델을 연다 (내려받기 포함)
    if not vision.detector.ready:
        log.info("ROI 이벤트 판정을 하지 않습니다: %s", vision.detector.error)
        return
    vision.listeners.append(on_detect)
    threading.Thread(target=_record_loop, daemon=True, name="zone-events").start()
    pinned: dict[tuple[int, str], vision.Feed] = {}
    while not vision.stopping():
        try:
            with SessionLocal() as db:
                rules = load_rules(db)
                floors = [r.min_conf for r in rules.values() if r.active]
                vision.min_conf = min(floors) if floors else None
                wanted = watched_cameras(db) if settings.event_watch else {}
            for key in [k for k, f in pinned.items() if k not in wanted or f.stopped]:
                pinned.pop(key).leave()
            for key, (name, is_file) in wanted.items():
                if key not in pinned:
                    pinned[key] = vision.open_feed(key[0], key[1], is_file, name)
                    log.info("ROI 이벤트 감시를 시작합니다: %s", name)
        except Exception:
            log.exception("ROI 이벤트 감시 설정을 읽지 못했습니다")
        for _ in range(RULE_REFRESH_SEC * 10):
            if vision.stopping():
                break
            time.sleep(0.1)
    for feed in pinned.values():
        feed.leave()


def start() -> None:
    """서버가 켜질 때 한 번. YOLO 를 못 쓰면 스레드가 이유를 남기고 그냥 끝난다."""
    global _started
    if _started or not settings.yolo_enabled:
        return
    _started = True
    threading.Thread(target=_watch_loop, daemon=True, name="zone-watch").start()
