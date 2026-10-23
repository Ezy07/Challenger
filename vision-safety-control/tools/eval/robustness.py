"""조명 · 거리 · 각도 · 화질 변수 테스트: 현장 영상 프레임을 바꿔 가며 모델이 얼마나 그대로 잡는지 잰다.

정답 라벨이 없으므로 **원본 프레임에서 확실히 잡힌 박스(confidence ≥ GT_CONF)를 기준**으로 삼는다.
변형한 프레임에서 같은 클래스 박스가 같은 자리(IoU ≥ IOU)에 다시 잡히면 "유지", 아니면 "놓침".
원본에 없던 박스는 "새 박스"(오탐 후보)로 센다. 안전모 · 조끼는 실제 판정(app.ppe.wearing)과 같은 식으로
키 PPE_MIN_PX 이상인 작업자 중 착용으로 잡힌 비율을 원본과 비교한다.

    cd backend
    .venv\\Scripts\\python ..\\tools\\eval\\robustness.py                 # 영상마다 12장면, site6c
    .venv\\Scripts\\python ..\\tools\\eval\\robustness.py --frames 30 --model yolov8n_openvino_model

결과: docs/eval/robustness.md (표) · robustness.csv (장면 단위) · robustness-samples.jpg (변형 예시)
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app import ppe, vision  # noqa: E402  (판정과 같은 착용 판정 · Box 를 쓴다)

ROOT = BACKEND.parent
OUT = ROOT / "docs" / "eval"
GT_CONF = 0.50      # 원본에서 이 이상이면 "있는 물체"로 본다
CONF = 0.35         # 변형 프레임에서 이 이상이면 잡은 것으로 본다 (화면 표시 기준)
PART_CONF = 0.30    # 안전모 · 조끼 박스 (PPE_PART_CONF)
IOU = 0.4
PPE_MIN_PX = 100    # PPE_MIN_PERSON_PX
SEED = 0


# ---------------------------------------------------------------- 변형 (이미지, 박스 좌표 바꾸는 함수)
def same(img):
    return img, lambda b: b


def gamma(g):
    lut = np.array([((i / 255) ** g) * 255 for i in range(256)], np.uint8)
    return lambda img: (cv2.LUT(img, lut), lambda b: b)


def bright(alpha, beta=0):
    return lambda img: (cv2.convertScaleAbs(img, alpha=alpha, beta=beta), lambda b: b)


def noise(sigma):
    def f(img):
        rng = np.random.default_rng(SEED)
        out = img.astype(np.int16) + rng.normal(0, sigma, img.shape).astype(np.int16)
        return np.clip(out, 0, 255).astype(np.uint8), lambda b: b
    return f


def night(img):
    """야간: 어둡게(감마 2.2 · 0.6배) + 센서 노이즈"""
    dark, _ = gamma(2.2)(img)
    dark = cv2.convertScaleAbs(dark, alpha=0.6)
    return noise(8)(dark)


def clahe(fn):
    """개선안: 어두운 프레임에 CLAHE(밝기 채널 대비 보정)를 걸고 탐지"""
    def f(img):
        out, mp = fn(img)
        lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
        lab[..., 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[..., 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), mp
    return f


def fog(k):
    def f(img):
        gray = np.full_like(img, 200)
        return cv2.addWeighted(img, 1 - k, gray, k, 0), lambda b: b
    return f


def backlight(img):
    """역광: 위쪽이 하얗게 날아가고 물체는 어둡게"""
    h, w = img.shape[:2]
    dark = cv2.convertScaleAbs(img, alpha=0.55)
    grad = np.linspace(1.0, 0.0, h, dtype=np.float32)[:, None, None] ** 1.5
    out = dark.astype(np.float32) * (1 - grad * 0.8) + 255 * grad * 0.8
    return np.clip(out, 0, 255).astype(np.uint8), lambda b: b


def motion_blur(k):
    kern = np.zeros((k, k), np.float32)
    kern[k // 2, :] = 1 / k
    return lambda img: (cv2.filter2D(img, -1, kern), lambda b: b)


def jpeg(q):
    def f(img):
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
        return cv2.imdecode(buf, cv2.IMREAD_COLOR), lambda b: b
    return f


def far(s):
    """거리: 화면 가운데에 s 배로 줄여 넣음 (물체가 s 배 멀리 있는 것처럼 작게)"""
    def f(img):
        h, w = img.shape[:2]
        small = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        canvas = cv2.resize(cv2.blur(img, (51, 51)), (w, h))  # 바깥은 흐린 배경 (빈 검은 칸이면 쉬워짐)
        ox, oy = (w - small.shape[1]) // 2, (h - small.shape[0]) // 2
        canvas[oy:oy + small.shape[0], ox:ox + small.shape[1]] = small
        return canvas, lambda b: (b[0] * s + ox, b[1] * s + oy, b[2] * s + ox, b[3] * s + oy)
    return f


def rotate(deg):
    """각도: 카메라가 deg 도 기울어짐 (TC 카메라 흔들림 · 설치 각도)"""
    def f(img):
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0)
        out = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)

        def mp(b):
            pts = np.array([[b[0], b[1], 1], [b[2], b[1], 1], [b[0], b[3], 1], [b[2], b[3], 1]], np.float32) @ m.T
            return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()
        return out, mp
    return f


def perspective(k):
    """각도: 위에서 내려다보는 쪽으로 기울어짐 (윗변을 k 비율만큼 좁힘)"""
    def f(img):
        h, w = img.shape[:2]
        src = np.float32([[0, 0], [w, 0], [0, h], [w, h]])
        dst = np.float32([[w * k, 0], [w * (1 - k), 0], [0, h], [w, h]])
        m = cv2.getPerspectiveTransform(src, dst)
        out = cv2.warpPerspective(img, m, (w, h), borderMode=cv2.BORDER_REFLECT)

        def mp(b):
            pts = np.float32([[b[0], b[1]], [b[2], b[1]], [b[0], b[3]], [b[2], b[3]]])[None]
            p = cv2.perspectiveTransform(pts, m)[0]
            return p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()
        return out, mp
    return f


# (분류, 이름, 변형)
CONDITIONS = [
    ("기준", "원본", same),
    ("조명", "어둡게 (감마 2.2)", gamma(2.2)),
    ("조명", "야간 (어둡게 + 노이즈)", night),
    ("조명", "야간 + CLAHE 보정 (개선안)", clahe(night)),
    ("조명", "과노출 (1.7배)", bright(1.7, 30)),
    ("조명", "역광", backlight),
    ("날씨", "안개 · 먼지 (40%)", fog(0.4)),
    ("거리", "2배 멀리 (1/2 크기)", far(0.5)),
    ("거리", "3배 멀리 (1/3 크기)", far(1 / 3)),
    ("각도", "카메라 기울어짐 10°", rotate(10)),
    ("각도", "내려다보는 각도 (원근 20%)", perspective(0.2)),
    ("화질", "흔들림 블러 (15px)", motion_blur(15)),
    ("화질", "센서 노이즈 (σ 20)", noise(20)),
    ("화질", "저품질 스트림 (JPEG 15)", jpeg(15)),
]


# ---------------------------------------------------------------- 측정
def detect(model, img, conf):
    r = model.predict(img, conf=conf, verbose=False)[0]
    names = r.names
    return [vision.Box(*map(int, xyxy), names[int(c)], float(p))
            for xyxy, c, p in zip(r.boxes.xyxy.tolist(), r.boxes.cls.tolist(), r.boxes.conf.tolist())]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def xyxy(b):
    return (b.x1, b.y1, b.x2, b.y2)


def match(gt, found):
    """클래스별 (기준 수, 유지 수), 새 박스 수"""
    kept, used = defaultdict(lambda: [0, 0]), set()
    for g_name, g_box in gt:
        kept[g_name][0] += 1
        best, bi = 0.0, None
        for i, b in enumerate(found):
            if i in used or b.name != g_name:
                continue
            v = iou(g_box, xyxy(b))
            if v > best:
                best, bi = v, i
        if best >= IOU:
            kept[g_name][1] += 1
            used.add(bi)
    new = sum(1 for i, b in enumerate(found) if i not in used and b.conf >= GT_CONF and b.name not in vision.PPE_PARTS
              and not any(n == b.name and iou(xyxy(b), g) >= IOU for n, g in gt))
    return kept, new


def ppe_rate(boxes):
    """키 PPE_MIN_PX 이상 작업자 수, 안전모 · 조끼 찾은 수 (실제 판정과 같은 위치 규칙)"""
    people = [b for b in boxes if b.name == "person" and b.conf >= CONF and b.y2 - b.y1 >= PPE_MIN_PX]
    parts = [b for b in boxes if b.name in vision.PPE_PARTS and b.conf >= PART_CONF]
    n, helmet, vest = len(people), 0, 0
    for p in people:
        w = ppe.wearing(p, parts)
        helmet += w["helmet"]
        vest += w["vest"]
    return n, helmet, vest


def frames(video, n):
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for i in np.linspace(0, total - 1, n + 2)[1:-1].astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, img = cap.read()
        if ok:
            yield int(i), img
    cap.release()


def pct(a, b):
    return f"{a / b * 100:.0f}%" if b else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="site6c_openvino_model", help="backend 기준 경로")
    ap.add_argument("--frames", type=int, default=12, help="영상마다 고르게 뽑을 장면 수")
    ap.add_argument("--videos", nargs="*", help="storage/videos 안의 파일 이름 (비우면 전부)")
    args = ap.parse_args()

    from ultralytics import YOLO
    model = YOLO(str(BACKEND / args.model))
    vids = sorted((ROOT / "storage" / "videos").glob("*.mp4"))
    if args.videos:
        vids = [v for v in vids if v.name in args.videos]
    OUT.mkdir(parents=True, exist_ok=True)

    # 조건마다: 클래스별 [기준, 유지], 새 박스, 장면 수, PPE [사람, 안전모, 조끼]
    agg = {name: dict(kept=defaultdict(lambda: [0, 0]), new=0, scenes=0, ppe=[0, 0, 0]) for _, name, _ in CONDITIONS}
    rows, sample = [], None
    for v in vids:
        print(v.name, flush=True)
        for fi, img in frames(v, args.frames):
            base = detect(model, img, PART_CONF)
            gt0 = [b for b in base if b.conf >= GT_CONF and b.name not in vision.PPE_PARTS]
            if sample is None and sum(b.name == "person" for b in gt0) >= 2:
                sample = img
            for group, name, fn in CONDITIONS:
                out, mp = fn(img)
                found = detect(model, out, PART_CONF)
                gt = [(b.name, mp(xyxy(b))) for b in gt0]
                kept, new = match(gt, [b for b in found if b.conf >= CONF])
                n, h, ve = ppe_rate(found)
                a = agg[name]
                a["scenes"] += 1
                a["new"] += new
                for k, (t, ok) in kept.items():
                    a["kept"][k][0] += t
                    a["kept"][k][1] += ok
                for i, x in enumerate((n, h, ve)):
                    a["ppe"][i] += x
                rows.append([v.name, fi, group, name, sum(t for t, _ in kept.values()),
                             sum(ok for _, ok in kept.values()), new, n, h, ve])

    with open(OUT / "robustness.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["영상", "프레임", "분류", "조건", "기준 물체", "유지", "새 박스", "작업자(100px+)", "안전모 찾음", "조끼 찾음"])
        w.writerows(rows)

    classes = ["person", "truck", "excavator", "forklift"]
    ko = {"person": "작업자", "truck": "트럭", "excavator": "굴삭기", "forklift": "지게차"}
    base = agg["원본"]
    bh = base["ppe"][1] / base["ppe"][0] if base["ppe"][0] else 0
    bv = base["ppe"][2] / base["ppe"][0] if base["ppe"][0] else 0
    lines = [
        "# 변수 테스트: 조명 · 거리 · 각도 · 화질",
        "",
        f"- 모델 `{args.model}` · 현장 영상 {len(vids)}개에서 영상마다 {args.frames}장면 (총 {base['scenes']}장면)",
        f"- 기준: 원본 장면에서 confidence {GT_CONF} 이상으로 잡힌 물체 "
        + ", ".join(f"{ko[c]} {base['kept'][c][0]}" for c in classes if base['kept'][c][0]),
        f"- **유지율** = 바꾼 장면에서도 같은 자리(IoU ≥ {IOU})에 confidence {CONF} 이상으로 다시 잡힌 비율 (미탐이 늘어난 정도)",
        f"- **새 박스** = 원본에 없던 자리에 confidence {GT_CONF} 이상으로 생긴 작업자 · 장비 박스, 장면 100개당 (오탐 후보)",
        f"- **안전모 · 조끼** = 키 {PPE_MIN_PX}px 이상 작업자 중 착용으로 잡힌 비율 (실제 판정 `ppe.wearing` 과 같은 규칙). "
        f"원본 대비 떨어진 만큼이 미착용 **오탐**으로 이어짐 (원본 안전모 {bh:.0%} · 조끼 {bv:.0%})",
        "- 정답 라벨이 아니라 원본 탐지를 기준으로 한 **상대 비교**입니다. 원본에서 놓친 물체는 셈에 들어가지 않습니다.",
        "",
        "| 분류 | 조건 | 전체 유지율 | " + " | ".join(ko[c] for c in classes) + " | 새 박스 /100장면 | 작업자(100px+) | 안전모 | 조끼 |",
        "|---|---|---|" + "---|" * len(classes) + "---|---|---|---|",
    ]
    for group, name, _ in CONDITIONS:
        a = agg[name]
        tot = sum(t for t, _ in a["kept"].values())
        ok = sum(o for _, o in a["kept"].values())
        n, h, ve = a["ppe"]
        lines.append(f"| {group} | {name} | **{pct(ok, tot)}** | "
                     + " | ".join(pct(a['kept'][c][1], a['kept'][c][0]) for c in classes)
                     + f" | {a['new'] / max(a['scenes'], 1) * 100:.0f} | {n} | {pct(h, n)} | {pct(ve, n)} |")
    (OUT / "robustness.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    if sample is not None:  # 변형 예시 한 장 (4열)
        tiles = []
        for _, name, fn in CONDITIONS:
            t = cv2.resize(fn(sample)[0], (480, 270))
            cv2.rectangle(t, (0, 0), (480, 26), (0, 0, 0), -1)
            tiles.append((t, name))
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(vision.FONTS[1], 18)
        imgs = []
        for t, name in tiles:
            im = Image.fromarray(cv2.cvtColor(t, cv2.COLOR_BGR2RGB))
            ImageDraw.Draw(im).text((8, 2), name, fill=(255, 255, 255), font=font)
            imgs.append(cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR))
        while len(imgs) % 4:
            imgs.append(np.zeros_like(imgs[0]))
        grid = np.vstack([np.hstack(imgs[i:i + 4]) for i in range(0, len(imgs), 4)])
        cv2.imencode(".jpg", grid, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(OUT / "robustness-samples.jpg"))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
