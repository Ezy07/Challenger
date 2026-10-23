"""멀리 있는(작게 보이는) 물체 개선안 비교: 입력 크기 640 · 960 · 1280, 타일 탐지(SAHI 방식 2×2 + 전체).

robustness.py 와 같은 장면 · 같은 기준(원본 640 탐지)으로 원본 · 2배 멀리 · 3배 멀리 조건의 유지율,
키 100px 이상 작업자의 안전모 · 조끼 판정 비율, 프레임 한 장 탐지 시간을 잰다.

960 · 1280 모델은 미리 변환해 둔다 (OpenVINO 는 변환할 때 크기가 고정됨. 원래 폴더를 덮지 않게 이름을 바꿔서):
    copy site6c.pt site6c_960.pt  &&  yolo export model=site6c_960.pt format=openvino imgsz=960
    copy site6c.pt site6c_1280.pt &&  yolo export model=site6c_1280.pt format=openvino imgsz=1280

    cd backend
    .venv\\Scripts\\python ..\\tools\\eval\\small_objects.py --m960 site6c_960_openvino_model --m1280 site6c_1280_openvino_model

결과: docs/eval/small-objects.md
"""

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robustness as rb  # noqa: E402  (장면 뽑기 · 변형 · 매칭 · 착용 판정을 그대로 쓴다)
from app import vision  # noqa: E402
from app.config import settings  # noqa: E402

CONDS = [("원본", rb.same), ("2배 멀리 (1/2 크기)", rb.far(0.5)), ("3배 멀리 (1/3 크기)", rb.far(1 / 3))]
TILE_OVERLAP = 0.2


def predict(model, img, imgsz, ox=0, oy=0):
    device = settings.yolo_device or None
    r = model.predict(img, conf=rb.PART_CONF, imgsz=imgsz, device=device, verbose=False)[0]
    return [vision.Box(int(b[0]) + ox, int(b[1]) + oy, int(b[2]) + ox, int(b[3]) + oy, r.names[int(c)], float(p))
            for b, c, p in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist())]


def merge(boxes, thr=0.5):
    """타일 경계에 걸려 둘로 잡힌 박스 정리: 같은 클래스끼리 IoU 또는 작은 박스 기준 겹침이 크면 confidence 높은 것만"""
    out = []
    for b in sorted(boxes, key=lambda b: -b.conf):
        bb = rb.xyxy(b)
        dup = False
        for o in out:
            if o.name != b.name:
                continue
            ob = rb.xyxy(o)
            ix = max(0, min(bb[2], ob[2]) - max(bb[0], ob[0]))
            iy = max(0, min(bb[3], ob[3]) - max(bb[1], ob[1]))
            small = min((bb[2] - bb[0]) * (bb[3] - bb[1]), (ob[2] - ob[0]) * (ob[3] - ob[1])) or 1
            if rb.iou(bb, ob) >= thr or ix * iy / small >= 0.8:
                dup = True
                break
        if not dup:
            out.append(b)
    return out


def tiled(model, img, imgsz):
    """전체 1장 + 2×2 타일 (겹침 20%)"""
    h, w = img.shape[:2]
    tw, th = int(w / (2 - TILE_OVERLAP)), int(h / (2 - TILE_OVERLAP))
    boxes = predict(model, img, imgsz)
    for x in (0, w - tw):
        for y in (0, h - th):
            boxes += predict(model, img[y:y + th, x:x + tw], imgsz, x, y)
    return merge(boxes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="site6c_openvino_model")
    ap.add_argument("--m960", help="imgsz 960 으로 변환한 모델 (없으면 그 줄을 뺌)")
    ap.add_argument("--m1280", help="imgsz 1280 으로 변환한 모델")
    ap.add_argument("--frames", type=int, default=10)
    args = ap.parse_args()

    from ultralytics import YOLO
    base = YOLO(str(rb.BACKEND / args.model))
    methods = [("지금 (640)", lambda img: predict(base, img, 640), 1)]
    if args.m960:
        m960 = YOLO(str(rb.BACKEND / args.m960))
        methods.append(("입력 크기 960", lambda img: predict(m960, img, 960), 1))
    if args.m1280:
        m1280 = YOLO(str(rb.BACKEND / args.m1280))
        methods.append(("입력 크기 1280", lambda img: predict(m1280, img, 1280), 1))
    methods.append(("타일 2×2 + 전체 (640)", lambda img: tiled(base, img, 640), 5))

    vids = sorted((rb.ROOT / "storage" / "videos").glob("*.mp4"))
    # (방법, 조건) → 기준 · 유지 · 새 박스 · 장면 · PPE
    agg = defaultdict(lambda: dict(base=0, kept=0, new=0, n=0, p=0, h=0, v=0))
    times = defaultdict(list)
    for name, fn, _ in methods:  # 처음 몇 번은 느리므로 데우기
        for _ in range(3):
            fn(np.zeros((720, 1280, 3), np.uint8))
    for v in vids:
        print(v.name, flush=True)
        for _, img in rb.frames(v, args.frames):
            h, w = img.shape[:2]  # 실제 시스템처럼 STREAM_MAX_WIDTH(960)로 줄인 영상에서 탐지
            if w > settings.stream_max_width:
                img = cv2.resize(img, (settings.stream_max_width, round(h * settings.stream_max_width / w)), interpolation=cv2.INTER_AREA)
            gt0 = [b for b in predict(base, img, 640) if b.conf >= rb.GT_CONF and b.name not in vision.PPE_PARTS]
            for cname, tf in CONDS:
                out, mp = tf(img)
                gt = [(b.name, mp(rb.xyxy(b))) for b in gt0]
                for mname, fn, _ in methods:
                    t0 = time.perf_counter()
                    found = fn(out)
                    times[mname].append(time.perf_counter() - t0)
                    kept, new = rb.match(gt, [b for b in found if b.conf >= rb.CONF])
                    n, h, ve = rb.ppe_rate(found)
                    a = agg[(mname, cname)]
                    a["base"] += sum(t for t, _ in kept.values())
                    a["kept"] += sum(o for _, o in kept.values())
                    a["new"] += new
                    a["n"] += 1
                    a["p"] += n
                    a["h"] += h
                    a["v"] += ve

    pct = rb.pct
    lines = [
        "# 멀리 있는 물체 개선안 비교",
        "",
        f"- 모델 site6c · 현장 영상 {len(vids)}개 × {args.frames}장면 · 탐지 장치 `{settings.yolo_device}` (OpenVINO) · "
        f"실제 시스템처럼 영상을 가로 {settings.stream_max_width}px 로 줄여서 탐지",
        "- 유지율 · 새 박스 · 안전모 · 조끼는 robustness.md 와 같은 정의 (기준 = 원본 장면의 640 탐지). "
        "원본 조건의 **새 박스는 기준(640)이 놓친 진짜 물체일 수도** 있습니다",
        "- 시간 = 프레임 한 장 탐지에 걸린 평균 (그 조건들 전체, 박스 정리 포함). 관제화면은 카메라 4대가 이 시간을 나눠 씁니다",
        "",
        "| 방법 | 장당 탐지 | 장당 시간 | 4대일 때 카메라당 초당 | "
        + " | ".join(f"{c} 유지율" for c, _ in CONDS[1:])
        + " | 원본 새 박스 /100장면 | 3배 멀리 판정 작업자 · 안전모 · 조끼 |",
        "|---|---|---|---|" + "---|" * (len(CONDS) - 1) + "---|---|",
    ]
    for mname, _, runs in methods:
        ms = np.mean(times[mname]) * 1000
        far3 = agg[(mname, CONDS[-1][0])]
        lines.append(
            f"| {mname} | {runs}번 | {ms:.0f}ms | {1000 / (ms * 4):.1f} | "
            + " | ".join(f"**{pct(agg[(mname, c)]['kept'], agg[(mname, c)]['base'])}**" for c, _ in CONDS[1:])
            + f" | {agg[(mname, '원본')]['new'] / max(agg[(mname, '원본')]['n'], 1) * 100:.0f}"
            + f" | {far3['p']} · {pct(far3['h'], far3['p'])} · {pct(far3['v'], far3['p'])} |")
    out = rb.OUT / "small-objects.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
