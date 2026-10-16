"""YOLO 탐지 영상. 관제화면(1-1) · 단일 카메라 확대(1-2)만 이 영상을 보여 주고, 나머지 화면은 원본 파일을 그대로 튼다.

- 카메라마다 읽기 스레드 하나가 영상을 실제 속도로 읽는다 (영상 파일은 끝나면 처음부터 반복).
- 탐지 스레드 하나가 지금 보고 있는 카메라들의 가장 최근 프레임을 돌아가며 YOLO 에 넣는다.
  CPU 하나를 여러 카메라가 나눠 쓰므로, 탐지 박스는 화면보다 조금 늦게 따라올 수 있다.
- 보는 사람마다 그 프레임에 ROI(storage/roi-zones.json) · 탐지 박스를 그려 JPEG 로 보낸다 (MJPEG).
- 아무도 안 보는 카메라는 IDLE_SECONDS 뒤 읽기를 멈춘다.

ultralytics · opencv 는 requirements-yolo.txt 로 따로 설치한다. 없으면 status() 가 이유를 돌려주고
화면은 원본 영상을 튼다.
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import settings

log = logging.getLogger("uvicorn.error")

IDLE_SECONDS = 15
ROI_W, ROI_H = 1000, 600  # ROI 그리기 화면 좌표 (영상 크기와 상관없이 가로 0~1000, 세로 0~600)
# frontend/roi-store.js 의 ROI_KINDS 와 같은 색 (RGB)
ROI_COLORS = {"위험구역": (255, 93, 93), "통제구역": (255, 154, 31), "관리구역": (108, 182, 255), "안전구역": (61, 220, 132)}
ZONE_ORDER = tuple(ROI_COLORS)  # 구역이 겹치면 앞쪽 종류로 본다 (위험 > 통제 > 관리 > 안전). 같은 종류끼리는 번호 순
BOX_COLOR = (255, 214, 10)  # ROI 밖에서 잡힌 물체
MASK_COLOR = (192, 132, 252)  # 세그 모델 윤곽 (굴삭기 등)
TEXT_DARK = (12, 16, 22)
NAMES_KO = {"person": "사람", "car": "차량", "truck": "트럭", "bus": "버스", "motorcycle": "오토바이", "bicycle": "자전거",
            "excavator": "굴삭기"}
FONTS = ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/malgun.ttf",
         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
         "/System/Library/Fonts/AppleSDGothicNeo.ttc")


# ---------------------------------------------------------------- ROI
_roi_lock = threading.Lock()
_roi_cache: dict = {"mtime": None, "rows": []}


def roi_rows() -> list:
    """storage/roi-zones.json 의 줄들. 파일이 바뀌었을 때만 다시 읽는다."""
    path = settings.roi_zones_file
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    with _roi_lock:
        if _roi_cache["mtime"] != mtime:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = []
            _roi_cache.update(mtime=mtime, rows=data if isinstance(data, list) else [])
        return _roi_cache["rows"]


def zones_at(rows: list, camera_name: str, t: float) -> list[dict]:
    """영상 t초에 보이는 그 카메라의 구역들. 단일 카메라 확대 화면(drawRois)과 같은 규칙:
    켜진 구역만, 모양이 여러 개면 시작 시각이 t 이하인 것 중 마지막 (없으면 첫 모양).
    한 구역 = {no, name, kind, points, dwell, intrusion, targets} (설정은 그 구역 첫 줄 기준)"""
    by_no: dict[int, list[dict]] = {}
    for r in rows:
        if not isinstance(r, dict) or r.get("kind") not in ROI_COLORS or not isinstance(r.get("no"), int):
            continue
        if r.get("camera") == camera_name:
            by_no.setdefault(r["no"], []).append(r)
    out = []
    for no in sorted(by_no):
        keys = sorted(by_no[no], key=lambda r: r.get("frame", 1))
        first = keys[0]
        if first.get("enabled", True) is False:
            continue
        key = first
        for k in keys:
            start = k["time"] if isinstance(k.get("time"), (int, float)) else (k.get("frame", 1) - 1) / 30
            if start <= t:
                key = k
        pts = key.get("points") or []
        if len(pts) >= 3:
            out.append({"no": no, "name": first.get("name"), "kind": key["kind"], "points": pts, "dwell": first.get("dwell"),
                        "intrusion": first.get("intrusion"), "targets": first.get("targets")})
    return out


def by_priority(items: list, kind_of) -> list:
    """구역 우선순위(ZONE_ORDER) 순으로. sorted 는 안정 정렬이라 같은 종류끼리는 원래(번호) 순서"""
    return sorted(items, key=lambda it: ZONE_ORDER.index(kind_of(it)))


def zone_title(zone: dict) -> str:
    """화면 · 이벤트에 보일 구역 이름. 이름을 안 정한 예전 구역은 등급으로 부른다"""
    return zone.get("name") or zone["kind"]


def rois_at(rows: list, camera_name: str, t: float) -> list[tuple[int, str, list, str]]:
    """영상 t초에 보이는 그 카메라의 구역 [(번호, 등급, 점들, 이름)] (그리기용)"""
    return [(z["no"], z["kind"], z["points"], zone_title(z)) for z in zones_at(rows, camera_name, t)]


# ---------------------------------------------------------------- YOLO
@dataclass(frozen=True)
class Box:
    x1: int
    y1: int
    x2: int
    y2: int
    name: str
    conf: float
    mask: list | None = field(default=None, compare=False)  # 세그 모델이면 윤곽 [[x, y], ...] (화면 좌표)


def _open_model(path: str):
    """모델 열기. "…_openvino_model" 폴더가 없으면 같은 이름의 .pt 를 (없으면 내려받아) 한 번 변환해 둔다."""
    from ultralytics import YOLO

    path = path.rstrip("/\\")
    if path.endswith("_openvino_model") and not Path(path).exists():
        pt = path[: -len("_openvino_model")] + ".pt"
        log.info("OpenVINO 모델이 없어 %s 를 변환합니다 (처음 한 번, 1분쯤)", pt)
        path = YOLO(pt).export(format="openvino", imgsz=settings.yolo_imgsz)
    model = YOLO(path)
    log.info("YOLO 모델을 열었습니다: %s (%s)", path, model.task)
    return model


class Detector:
    """YOLO 모델 하나를 모든 카메라가 같이 쓴다 (탐지 스레드 하나에서만 부름).
    YOLO_SEG_MODEL 을 주면 세그 모델을 하나 더 돌려 윤곽(mask)까지 받는다 (시험용. 그만큼 느려짐)."""

    def __init__(self):
        self._model = None
        self._seg = None
        self.error: str | None = None
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            if self._model is not None or self.error is not None:
                return
            if not settings.yolo_enabled:
                self.error = "YOLO 를 꺼 두었습니다 (YOLO_ENABLED=false)."
                return
            try:
                import cv2  # noqa: F401
                import ultralytics  # noqa: F401
            except ImportError:
                self.error = "YOLO 패키지가 설치되지 않았습니다 (backend 에서 pip install -r requirements-yolo.txt)."
                return
            try:
                self._model = _open_model(settings.yolo_model)
            except Exception as exc:  # 모델 파일이 없거나 내려받지 못함
                log.exception("YOLO 모델을 열지 못했습니다")
                self.error = f"YOLO 모델({settings.yolo_model})을 열지 못했습니다: {exc}"
                return
            if settings.yolo_seg_model:
                try:
                    self._seg = _open_model(settings.yolo_seg_model)
                except Exception:  # 세그 모델은 덤. 못 열어도 기본 탐지는 그대로
                    log.exception("세그 모델(%s)을 열지 못했습니다", settings.yolo_seg_model)

    @property
    def ready(self) -> bool:
        return self._model is not None

    @staticmethod
    def _run(model, frame, conf: float) -> list[Box]:
        device = settings.yolo_device or None
        if device and device.startswith("intel") and "openvino" not in str(model.model_name):
            device = None  # intel:gpu 는 OpenVINO 모델에서만 (.pt 로 바꿨으면 자동)
        result = model.predict(frame, conf=conf, imgsz=settings.yolo_imgsz, device=device, verbose=False)[0]
        names = result.names
        masks = result.masks.xy if result.masks is not None else [None] * len(result.boxes)
        return [Box(int(x1), int(y1), int(x2), int(y2), str(names[int(c)]), float(p),
                    m.astype(int).tolist() if m is not None and len(m) >= 3 else None)
                for (x1, y1, x2, y2), p, c, m in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(),
                                                      result.boxes.cls.tolist(), masks)]

    def detect(self, frame) -> list[Box]:
        # 판정 기준(8-8)을 화면용 기준보다 낮게 잡았으면 그만큼 낮은 박스도 받아야 이벤트 판정을 할 수 있다
        conf = min(settings.yolo_conf, min_conf) if min_conf is not None else settings.yolo_conf
        boxes = self._run(self._model, frame, conf)
        if self._seg is not None:
            segs = self._run(self._seg, frame, settings.yolo_conf)
            # 기본 모델이 같은 물체를 트럭 등으로 또 잡은 박스는 뺀다 (많이 겹치면 같은 물체로 봄)
            boxes = [b for b in boxes if b.name == "person" or not any(_iou(b, s) > 0.5 for s in segs)] + segs
        return boxes


def _iou(a: Box, b: Box) -> float:
    ix = max(0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0, min(a.y2, b.y2) - max(a.y1, b.y1))
    union = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - ix * iy
    return ix * iy / union if union else 0.0


detector = Detector()
min_conf: float | None = None  # 이벤트 판정에 쓰는 가장 낮은 판정 기준 (zone_events 가 채움)


def status() -> tuple[bool, str | None]:
    """(YOLO 영상을 쓸 수 있는지, 못 쓰면 그 이유). 처음 부를 때 모델을 연다 (내려받기 포함이라 느릴 수 있음)."""
    detector.load()
    return detector.ready, detector.error


# ---------------------------------------------------------------- 카메라 영상 읽기
@dataclass
class Snapshot:
    seq: int
    frame: object       # numpy 배열 (BGR). 읽기 스레드는 새 배열로 바꿔 끼우기만 하므로 읽는 쪽은 복사해서 그린다
    video_time: float   # 영상 파일 안의 시각(초). ROI 모양을 고를 때 씀
    boxes: list[Box] = field(default_factory=list)


_feeds_lock = threading.Lock()
_feeds: dict[tuple, "Feed"] = {}
_shutdown = threading.Event()
_detect_thread: threading.Thread | None = None
listeners: list = []  # 탐지가 끝날 때마다 fn(feed, snap) 을 부른다 (ROI 이벤트 판정 · zone_events)


class Feed:
    """카메라 하나의 영상 읽기. 보는 사람이 없으면 IDLE_SECONDS 뒤 스스로 멈춘다."""

    def __init__(self, key: tuple, source: str, is_file: bool, camera_name: str):
        self.key, self.source, self.is_file = key, source, is_file
        self.camera_id, self.camera_name = key[0], camera_name
        self._lock = threading.Lock()
        self.latest: Snapshot | None = None
        self.detected_seq = -1  # 탐지 스레드가 마지막으로 본 프레임
        self.viewers = 0
        self.idle_since = time.monotonic()
        self.stopped = False
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"feed-{key[0]}")

    def join(self) -> None:
        with self._lock:
            self.viewers += 1

    def leave(self) -> None:
        with self._lock:
            self.viewers -= 1
            if self.viewers <= 0:
                self.idle_since = time.monotonic()

    def _should_stop(self) -> bool:
        if _shutdown.is_set():
            self.stopped = True
            return True
        with _feeds_lock, self._lock:  # 새 사람이 이 Feed 에 붙는 중이 아닌지 같이 확인
            if self.viewers <= 0 and time.monotonic() - self.idle_since > IDLE_SECONDS:
                if _feeds.get(self.key) is self:
                    del _feeds[self.key]
                self.stopped = True
                return True
        return False

    def _publish(self, frame, video_time: float) -> None:
        import cv2

        h, w = frame.shape[:2]
        if w > settings.stream_max_width:
            s = settings.stream_max_width / w
            frame = cv2.resize(frame, (settings.stream_max_width, round(h * s)), interpolation=cv2.INTER_AREA)
        with self._lock:
            prev = self.latest
            self.latest = Snapshot((prev.seq + 1) if prev else 0, frame, video_time, prev.boxes if prev else [])

    def set_boxes(self, seq: int, boxes: list[Box]) -> None:
        with self._lock:
            self.detected_seq = seq
            if self.latest:  # 그 사이 새 프레임이 왔어도 박스는 최신 결과로
                self.latest.boxes = boxes

    def _run(self) -> None:
        import cv2

        cap = None
        gap = 1 / max(1, settings.stream_fps)
        try:
            while not self._should_stop():
                if cap is None:
                    cap = cv2.VideoCapture(self.source)
                    if not cap.isOpened():
                        log.warning("영상을 열 수 없습니다: %s", self.source)
                        cap = None
                        time.sleep(3)
                        continue
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    fps = fps if 1 <= fps <= 120 else 30
                    started, pos, sent = time.monotonic(), 0, 0.0

                if self.is_file:
                    # 영상 파일: 실제 시간에 맞춰 읽고, 늦었으면 디코딩만 하고 건너뛴다
                    target = int((time.monotonic() - started) * fps)
                    if pos > target:
                        time.sleep(min((pos - target) / fps, 0.05))
                        continue
                    ok = True
                    while ok and pos < target:
                        ok = cap.grab()
                        pos += 1
                    if ok:
                        ok, frame = cap.read()
                        pos += 1
                    if not ok:  # 끝까지 봤으면 처음부터 (관제화면의 반복 재생과 같게)
                        if not cap.set(cv2.CAP_PROP_POS_FRAMES, 0):
                            cap.release()
                            cap = None
                        started, pos, sent = time.monotonic(), 0, 0.0
                        continue
                    video_time = (pos - 1) / fps
                else:
                    # RTSP 등 실시간 카메라: 들어오는 대로 읽는다
                    ok, frame = cap.read()
                    if not ok:
                        cap.release()
                        cap = None
                        time.sleep(1)
                        continue
                    video_time = time.monotonic() - started

                now = time.monotonic()
                if now - sent >= gap:
                    sent = now
                    self._publish(frame, video_time)
        except Exception:
            log.exception("영상 읽기가 멈췄습니다: %s", self.source)
            with _feeds_lock:
                if _feeds.get(self.key) is self:
                    del _feeds[self.key]
            self.stopped = True
        finally:
            if cap is not None:
                cap.release()


def _detect_loop() -> None:
    """보고 있는 카메라들의 새 프레임을 돌아가며 탐지한다."""
    failed = False
    while not _shutdown.is_set():
        with _feeds_lock:
            feeds = list(_feeds.values())
        worked = False
        for feed in feeds:
            snap = feed.latest
            if snap is None or snap.seq == feed.detected_seq:
                continue
            try:
                boxes = detector.detect(snap.frame)
                failed = False
            except Exception:
                if not failed:  # 같은 오류로 로그가 넘치지 않게 한 번만
                    log.exception("YOLO 탐지에 실패했습니다")
                failed = True
                boxes = []
            feed.set_boxes(snap.seq, boxes)
            done = Snapshot(snap.seq, snap.frame, snap.video_time, boxes)
            for fn in listeners:
                try:
                    fn(feed, done)
                except Exception:
                    log.exception("탐지 결과를 처리하지 못했습니다")
            worked = True
        if not worked:
            time.sleep(0.01)


def open_feed(camera_id: int, source: str, is_file: bool, camera_name: str) -> Feed:
    """그 카메라 영상을 보는 사람을 하나 늘린다 (다 보면 Feed.leave). 이벤트 감시도 보는 사람 하나로 센다."""
    global _detect_thread
    key = (camera_id, source)
    with _feeds_lock:
        feed = _feeds.get(key)
        if feed is None:
            feed = _feeds[key] = Feed(key, source, is_file, camera_name)
            feed.thread.start()
        feed.join()
        if _detect_thread is None or not _detect_thread.is_alive():
            _detect_thread = threading.Thread(target=_detect_loop, daemon=True, name="yolo-detect")
            _detect_thread.start()
    return feed


def shutdown() -> None:
    _shutdown.set()


def stopping() -> bool:
    return _shutdown.is_set()


# ---------------------------------------------------------------- 그리기
def _bgr(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    return rgb[2], rgb[1], rgb[0]


@lru_cache(maxsize=16)
def _font(size: int):
    from PIL import ImageFont

    for path in FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)  # 한글 글꼴이 없으면 한글이 네모로 보임


@lru_cache(maxsize=512)
def _text_sprite(text: str, size: int, fg: tuple, bg: tuple | None):
    """글자 그림 (BGR 배열, 투명도 배열). OpenCV 는 한글을 못 써서 Pillow 로 한 번 그려 두고 붙인다."""
    import numpy as np
    from PIL import Image, ImageDraw

    font = _font(size)
    stroke = 0 if bg else max(2, size // 8)
    left, top, right, bottom = font.getbbox(text, stroke_width=stroke)
    pad = max(3, size // 5) if bg else 0
    w, h = right - left + pad * 2, bottom - top + pad * 2
    img = Image.new("RGBA", (w, h), (*bg, 255) if bg else (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad - left, pad - top), text, font=font, fill=(*fg, 255),
                             stroke_width=stroke, stroke_fill=(*TEXT_DARK, 255))
    arr = np.asarray(img)
    return arr[:, :, 2::-1].copy(), arr[:, :, 3:4].astype(np.float32) / 255


def _paste(img, sprite, x: int, y: int) -> None:
    rgb, alpha = sprite
    h, w = rgb.shape[:2]
    H, W = img.shape[:2]
    x, y = max(0, min(x, W - w)), max(0, min(y, H - h))
    if w > W or h > H:
        return
    area = img[y:y + h, x:x + w]
    area[:] = (rgb * alpha + area * (1 - alpha)).astype(area.dtype)


def render(snap: Snapshot, rois: list[tuple[int, str, list, str]], show_roi: bool, show_boxes: bool = True) -> bytes:
    """프레임 하나에 ROI · 탐지 박스를 그려 JPEG 로. 둘 다 끄면 원본 프레임 (탐지 · 판정은 그대로)"""
    import cv2
    import numpy as np

    img = snap.frame.copy()
    h, w = img.shape[:2]
    line = max(2, h // 360)
    # 우선순위 순 (박스 색은 앞쪽 구역). 그릴 때는 뒤집어서 위험구역이 맨 위에 오게 한다
    polys = by_priority([(no, kind, np.array([[x * w / ROI_W, y * h / ROI_H] for x, y in pts], np.int32), title)
                         for no, kind, pts, title in rois], lambda p: p[1])
    drawn = polys[::-1]

    if show_roi and polys:
        layer = img.copy()
        for _, kind, poly, _ in drawn:
            cv2.fillPoly(layer, [poly], _bgr(ROI_COLORS[kind]))
        cv2.addWeighted(layer, 0.18, img, 0.82, 0, img)
        for _, kind, poly, _ in drawn:
            cv2.polylines(img, [poly], True, _bgr(ROI_COLORS[kind]), line, cv2.LINE_AA)
        for no, _, poly, title in drawn:
            sprite = _text_sprite(f"{no} {title}", max(14, h // 28), (255, 255, 255), None)
            cx, cy = poly.mean(axis=0)
            _paste(img, sprite, int(cx) - sprite[0].shape[1] // 2, int(cy) - sprite[0].shape[0] // 2)

    # 세그 모델이 준 윤곽은 반투명하게 칠한다 (박스는 아래에서 평소처럼)
    boxes = snap.boxes if show_boxes else []
    masks = [np.array(b.mask, np.int32) for b in boxes if b.mask]
    if masks:
        layer = img.copy()
        cv2.fillPoly(layer, masks, _bgr(MASK_COLOR))
        cv2.addWeighted(layer, 0.4, img, 0.6, 0, img)
        cv2.polylines(img, masks, True, _bgr(MASK_COLOR), line, cv2.LINE_AA)

    for b in boxes:
        # 발밑(박스 아래 가운데)이 들어간 구역 중 우선순위가 가장 높은 구역의 색으로 그린다. ROI 표시를 꺼도 판정은 그대로
        foot = ((b.x1 + b.x2) / 2, float(b.y2))
        zone = next(((kind, title) for _, kind, poly, title in polys if cv2.pointPolygonTest(poly, foot, False) >= 0), None)
        color = ROI_COLORS[zone[0]] if zone else BOX_COLOR
        cv2.rectangle(img, (b.x1, b.y1), (b.x2, b.y2), _bgr(color), line, cv2.LINE_AA)
        label = f"{NAMES_KO.get(b.name, b.name)} {b.conf:.0%}" + (f" · {zone[1]}" if zone else "")
        sprite = _text_sprite(label, max(12, h // 40), TEXT_DARK, color)
        _paste(img, sprite, b.x1 - line // 2, b.y1 - sprite[0].shape[0])

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, settings.stream_jpeg_quality])
    return buf.tobytes() if ok else b""
