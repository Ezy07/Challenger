"""PPE 모델(안전모 · 조끼 박스) + 추적 → 안전모 미착용(NO_HELMET) · 안전조끼 미착용(NO_VEST) 이벤트.

- 착용한 것만 학습한 모델(tools/train/ppe_finetune.ipynb, person · helmet · vest)을 쓴다. 미착용은 "없음"으로 판정한다:
  작업자(person) 박스 머리 영역(HEAD)에 안전모 박스가, 몸통 영역(TORSO)에 조끼 박스가 있으면 착용.
  PPE 모델이 없으면(YOLO_PPE_MODEL 비움) 판정하지 않는다 (모든 작업자가 미착용으로 나오므로).
- 한 프레임으로 정하지 않는다. 추적 번호마다 PPE_WINDOW_SEC 동안 본 결과에서 MISSING_RATIO 넘게 없었으면 미착용.
  고개를 숙이거나 잠깐 가려진 순간은 이걸로 걸러진다. 작업자 한 명(추적 번호)마다 유형별로 경보 한 번.
- 판정하지 않는 작업자: 추적 번호가 없음 · 화면에서 PPE_MIN_PERSON_PX 보다 작음(머리가 몇 픽셀) ·
  장비 박스 안에 거의 들어 있음(운전석).
- 판정 기준(8-8)의 안전모 · 조끼 값을 쓴다: 작업자가 추적하는 동안 한 번이라도 confidence 가 기준 이상이어야 센다.
  쿨다운 · 심각도는 이벤트를 만들 때(events.create_event) 적용한다. 이벤트는 ROI 와 상관없이 카메라 단위.
"""

import logging
from collections import deque
from dataclasses import dataclass, field

from . import judging, proximity, vision
from .config import settings
from .judging import FORGET_SEC, Job

log = logging.getLogger("uvicorn.error")

NO_HELMET, NO_VEST = "NO_HELMET", "NO_VEST"
CODES = (NO_HELMET, NO_VEST)
PART = {NO_HELMET: "helmet", NO_VEST: "vest"}
LABEL = {NO_HELMET: "안전모 미착용", NO_VEST: "안전조끼 미착용"}
# 작업자 박스 위쪽 끝에서 아래로 (박스 높이 비율). 안전모는 박스 위로 조금 삐져나올 수 있다
HEAD = (-0.15, 0.30)
TORSO = (0.15, 0.75)
SIDE = 0.15          # 좌우로 박스 너비의 이만큼까지는 그 작업자 것으로 본다
MISSING_RATIO = 0.7  # 지켜본 동안 이 비율 넘게 없었으면 미착용
MIN_SAMPLES = 3


def part_on(person: vision.Box, parts: list[vision.Box], name: str) -> vision.Box | None:
    """작업자 머리(안전모) · 몸통(조끼) 자리에 있는 그 부위 박스 (여럿이면 confidence 가 가장 높은 것)"""
    w, h = person.x2 - person.x1, person.y2 - person.y1
    top, bottom = HEAD if name == "helmet" else TORSO

    def on(b: vision.Box) -> bool:
        cx, cy = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
        return (person.x1 - SIDE * w <= cx <= person.x2 + SIDE * w
                and person.y1 + top * h <= cy <= person.y1 + bottom * h)

    return max((b for b in parts if b.name == name and on(b)), key=lambda b: b.conf, default=None)


def wearing(person: vision.Box, parts: list[vision.Box]) -> dict[str, bool]:
    """{"helmet": 머리에 안전모가 있는지, "vest": 몸통에 조끼가 있는지}"""
    return {name: part_on(person, parts, name) is not None for name in vision.PPE_PARTS}


@dataclass
class Watch:
    since: float
    last_seen: float
    best: float = 0.0
    samples: deque = field(default_factory=deque)  # (시각, {"helmet": bool, "vest": bool})
    fired: set = field(default_factory=set)


@dataclass(frozen=True)
class Trigger:
    camera_id: int
    code: str
    person: vision.Box
    conf: float  # 작업자가 추적 동안 받은 가장 높은 confidence


class Judge:
    """카메라 · 추적 번호마다 착용 여부를 모은다. 탐지 스레드 하나에서만 부른다."""

    def __init__(self):
        self.watches: dict[tuple[int, int], Watch] = {}

    def observe(self, camera_id: int, boxes: list[vision.Box], min_conf: dict[str, float], now: float, *,
                window: float | None = None, min_px: int | None = None) -> list[Trigger]:
        """min_conf: 판정할 유형 → 판정 기준 (사용을 끈 유형은 빼고 넘긴다)"""
        window = settings.ppe_window_sec if window is None else window
        min_px = settings.ppe_min_person_px if min_px is None else min_px
        parts = [b for b in boxes if b.name in vision.PPE_PARTS]
        equips = [b for b in boxes if b.name in proximity.equipment_classes()]

        out = []
        for p in boxes:
            if p.name != "person" or p.track_id is None or p.y2 - p.y1 < min_px:
                continue
            if judging.onboard(p, equips):
                continue  # 운전석 등 장비에 탄 사람
            key = (camera_id, p.track_id)
            watch = self.watches.get(key)
            if watch is None or now - watch.last_seen > window:  # 처음 보거나 오래 끊겼으면 새로
                watch = self.watches[key] = Watch(since=now, last_seen=now)
            watch.last_seen = now
            watch.best = max(watch.best, p.conf)
            watch.samples.append((now, wearing(p, parts)))
            while watch.samples and now - watch.samples[0][0] > window:
                watch.samples.popleft()
            if now - watch.since < window or len(watch.samples) < MIN_SAMPLES:
                continue
            for code, floor in min_conf.items():
                if code in watch.fired or watch.best < floor:
                    continue
                missing = sum(not seen[PART[code]] for _, seen in watch.samples) / len(watch.samples)
                if missing > MISSING_RATIO:
                    watch.fired.add(code)
                    out.append(Trigger(camera_id, code, p, watch.best))
        judging.drop_stale(self.watches, camera_id, now, FORGET_SEC)
        return out


def summary(camera_id: int, now: float, fresh: float = vision.PEOPLE_FRESH_SEC) -> dict[str, int]:
    """화면 표시용: 지금(fresh 초 안) 보이는 판정 대상 작업자 수와 안전모 · 조끼를 착용한 수.
    한 프레임이 아니라 작업자마다 지켜본 동안의 다수결이라 숫자가 덜 흔들리고 경보와 기준이 같다.
    탐지 스레드가 고치는 중에 읽으므로 복사해서 본다."""
    out = {"checked": 0, "helmet": 0, "vest": 0}
    for (cam, _), w in list(judge.watches.items()):
        samples = list(w.samples)
        if cam != camera_id or now - w.last_seen > fresh or not samples:
            continue
        out["checked"] += 1
        for part in vision.PPE_PARTS:
            out[part] += sum(seen[part] for _, seen in samples) * 2 >= len(samples)
    return out


# ---------------------------------------------------------------- 이벤트 · 스냅샷 기록
def record(Session, job: Job):
    """판정 기준 · 쿨다운을 적용해 이벤트를 만든다 (ROI 와 상관없이 카메라 단위). 스냅샷에 미착용 작업자를 붉은 박스로 두른다"""
    t, p = job.trigger, job.trigger.person
    result = judging.create(Session, job, t.code, t.conf, judging.bbox(p),
                            lambda: judging.snapshot(job, t.code, marks=[(p, LABEL[t.code])]))
    if result.created:
        log.info("이벤트 EV-%s: %s %s 사람#%s", result.event_id, job.camera_name, LABEL[t.code], p.track_id)
    return result


judge = Judge()
