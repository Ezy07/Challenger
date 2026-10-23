"""입력 크기 960 모델이 640 에서 없던 박스를 새로 잡은 것들을 잘라 한 장으로 모은다 (진짜 물체인지 눈으로 확인용).

small_objects.py 와 같은 장면(가로 960 으로 줄인 원본)에서, 960 이 confidence 0.5 이상으로 잡은 작업자 · 장비 박스 중
640 의 같은 클래스 박스(confidence 0.35 이상, IoU 0.4 이상)와 겹치지 않는 것. 640 이 0.35 미만으로라도 잡았으면
그 confidence 를 같이 적는다 (낮게라도 잡았으면 진짜일 가능성이 높음).

    cd backend
    .venv\\Scripts\\python ..\\tools\\eval\\new_boxes.py --m960 site6c_960_openvino_model

결과: docs/eval/new-boxes-960.jpg · new-boxes-960.csv
"""

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import robustness as rb  # noqa: E402
import small_objects as so  # noqa: E402
from app import vision  # noqa: E402
from app.config import settings  # noqa: E402

TILE = 200
COLS = 8
KO = {"person": "작업자", "truck": "트럭", "excavator": "굴삭기", "forklift": "지게차"}


def crop(img, b, size=TILE):
    """박스 둘레를 조금 넓혀 정사각형으로 잘라 size 로 맞추고, 박스를 그린다"""
    h, w = img.shape[:2]
    cx, cy = (b.x1 + b.x2) / 2, (b.y1 + b.y2) / 2
    side = max(b.x2 - b.x1, b.y2 - b.y1) * 1.6 + 24
    x1, y1 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    x2, y2 = int(min(w, cx + side / 2)), int(min(h, cy + side / 2))
    c = img[y1:y2, x1:x2].copy()
    cv2.rectangle(c, (b.x1 - x1, b.y1 - y1), (b.x2 - x1, b.y2 - y1), (0, 220, 255), 2)
    s = size / max(c.shape[:2])
    c = cv2.resize(c, (max(1, int(c.shape[1] * s)), max(1, int(c.shape[0] * s))), interpolation=cv2.INTER_CUBIC)
    tile = np.full((size, size, 3), 30, np.uint8)
    tile[(size - c.shape[0]) // 2:(size - c.shape[0]) // 2 + c.shape[0], (size - c.shape[1]) // 2:(size - c.shape[1]) // 2 + c.shape[1]] = c
    return tile


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="site6c_openvino_model")
    ap.add_argument("--m960", required=True)
    ap.add_argument("--frames", type=int, default=10)
    args = ap.parse_args()

    from ultralytics import YOLO
    m640 = YOLO(str(rb.BACKEND / args.model))
    m960 = YOLO(str(rb.BACKEND / args.m960))
    found = []  # (영상, 프레임, Box, 640 최고 confidence, 타일)
    for v in sorted((rb.ROOT / "storage" / "videos").glob("*.mp4")):
        for fi, img in rb.frames(v, args.frames):
            h, w = img.shape[:2]
            if w > settings.stream_max_width:
                img = cv2.resize(img, (settings.stream_max_width, round(h * settings.stream_max_width / w)), interpolation=cv2.INTER_AREA)
            a = so.predict(m640, img, 640)
            b = so.predict(m960, img, 960)
            # 640 이 아주 낮은 confidence 로라도 잡았는지 보려고 한 번 더 (0.05 이상)
            a_low = [x for x in m640.predict(img, conf=0.05, imgsz=640, device=settings.yolo_device or None, verbose=False)[0].boxes]
            a_low = [(m640.names[int(x.cls)], tuple(map(int, x.xyxy[0].tolist())), float(x.conf)) for x in a_low]
            for nb in b:
                if nb.conf < rb.GT_CONF or nb.name in vision.PPE_PARTS:
                    continue
                if any(o.name == nb.name and o.conf >= rb.CONF and rb.iou(rb.xyxy(o), rb.xyxy(nb)) >= rb.IOU for o in a):
                    continue
                best = max((c for n, xy, c in a_low if n == nb.name and rb.iou(xy, rb.xyxy(nb)) >= rb.IOU), default=0.0)
                found.append((v.name, fi, nb, best, crop(img, nb)))
        print(v.name, len(found), flush=True)

    out = rb.OUT
    with open(out / "new-boxes-960.csv", "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.writer(f)
        wr.writerow(["번호", "영상", "프레임", "클래스", "960 confidence", "640 confidence (0.05 이상에서 최고)", "박스 높이(px)"])
        for i, (vn, fi, b, best, _) in enumerate(found, 1):
            wr.writerow([i, vn, fi, b.name, f"{b.conf:.2f}", f"{best:.2f}", b.y2 - b.y1])

    font = ImageFont.truetype(vision.FONTS[1], 15)
    rows = (len(found) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * TILE, max(1, rows) * (TILE + 40)), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (vn, fi, b, best, tile) in enumerate(found):
        x, y = (i % COLS) * TILE, (i // COLS) * (TILE + 40)
        sheet.paste(Image.fromarray(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB)), (x, y))
        d.text((x + 4, y + TILE + 2), f"{i + 1}. {KO.get(b.name, b.name)} {b.conf:.2f} · 640 {best:.2f}", font=font, fill=(20, 20, 20))
        d.text((x + 4, y + TILE + 20), f"{Path(vn).stem[:18]} · {b.y2 - b.y1}px", font=font, fill=(110, 110, 110))
    sheet.save(out / "new-boxes-960.jpg", quality=88)
    print("total", len(found))


if __name__ == "__main__":
    main()
