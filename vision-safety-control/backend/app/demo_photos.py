"""시연용 작업자 프로필 사진: 실제 사람 사진 대신 안전모 · 조끼를 입은 작업자 그림을 만든다.

작업자 번호로 색(안전모 · 조끼 · 피부 · 배경)을 정하므로 다시 만들어도 같은 그림이 나온다.
    python -m app.seed --demo-photos     # 사진이 없는 작업자에게 넣기
"""

import io
import random

from PIL import Image, ImageDraw

SIZE = 640
S = 2  # 크게 그린 뒤 줄여 가장자리를 부드럽게

BACKGROUNDS = [(214, 228, 240), (226, 236, 222), (240, 230, 214), (232, 224, 240), (222, 232, 236), (238, 226, 226)]
SKINS = [(241, 203, 170), (226, 180, 140), (198, 148, 108), (234, 192, 158), (214, 166, 126)]
HATS = [(250, 250, 248), (255, 206, 40), (255, 140, 30), (40, 110, 220), (250, 250, 248), (255, 206, 40)]
VESTS = [(205, 245, 40), (255, 150, 30), (205, 245, 40), (255, 210, 30)]
SIGNAL_VEST = (230, 40, 40)  # 신호수 (빨간 조끼)
SHIRTS = [(60, 72, 96), (90, 90, 96), (52, 84, 120), (110, 80, 60), (70, 100, 80)]
HAIR = [(40, 32, 28), (60, 48, 40), (90, 90, 90), (30, 30, 34)]


def draw_worker(seed: int, signalman: bool = False) -> bytes:
    """작업자 그림 한 장 (JPEG)"""
    rnd = random.Random(seed)
    W = SIZE * S
    bg, skin, hat = rnd.choice(BACKGROUNDS), rnd.choice(SKINS), rnd.choice(HATS)
    vest = SIGNAL_VEST if signalman else rnd.choice(VESTS)
    shirt, hair = rnd.choice(SHIRTS), rnd.choice(HAIR)
    img = Image.new("RGB", (W, W), bg)
    d = ImageDraw.Draw(img)
    u = W / 100  # 1% 단위

    # 몸 · 조끼 (어깨 아래)
    d.rounded_rectangle((14 * u, 70 * u, 86 * u, 120 * u), radius=22 * u, fill=shirt)
    d.polygon([(26 * u, 72 * u), (43 * u, 72 * u), (50 * u, 86 * u), (57 * u, 72 * u), (74 * u, 72 * u),
               (80 * u, 100 * u), (20 * u, 100 * u)], fill=vest)
    for y in (88, 94):  # 반사띠
        d.rectangle((22 * u, y * u, 78 * u, (y + 2.2) * u), fill=(220, 224, 228))
    d.rectangle((48.6 * u, 86 * u, 51.4 * u, 100 * u), fill=shirt)  # 앞 여밈

    # 목 · 얼굴
    d.rectangle((43 * u, 58 * u, 57 * u, 74 * u), fill=tuple(int(c * 0.92) for c in skin))
    d.ellipse((31 * u, 28 * u, 69 * u, 68 * u), fill=skin)
    d.ellipse((28.5 * u, 44 * u, 33.5 * u, 54 * u), fill=skin)  # 귀
    d.ellipse((66.5 * u, 44 * u, 71.5 * u, 54 * u), fill=skin)
    d.rectangle((32 * u, 38 * u, 68 * u, 42 * u), fill=hair)  # 안전모 아래 머리카락
    for x in (42.5, 57.5):  # 눈
        d.ellipse(((x - 1.6) * u, 47 * u, (x + 1.6) * u, 50.4 * u), fill=(40, 36, 34))
    d.arc((43 * u, 52 * u, 57 * u, 61 * u), start=20, end=160, fill=(150, 80, 70), width=int(1.1 * u))  # 웃는 입

    # 안전모: 둥근 윗부분 + 챙 + 가운데 줄
    d.pieslice((29 * u, 18 * u, 71 * u, 58 * u), start=180, end=360, fill=hat)
    d.rounded_rectangle((25 * u, 36 * u, 75 * u, 41.5 * u), radius=2.5 * u, fill=hat)
    shade = tuple(int(c * 0.82) for c in hat)
    d.rounded_rectangle((47.5 * u, 18.5 * u, 52.5 * u, 37 * u), radius=2 * u, fill=shade)
    d.line((25 * u, 41.5 * u, 75 * u, 41.5 * u), fill=shade, width=int(0.8 * u))

    out = io.BytesIO()
    img.resize((SIZE, SIZE), Image.LANCZOS).save(out, "JPEG", quality=88)
    return out.getvalue()
