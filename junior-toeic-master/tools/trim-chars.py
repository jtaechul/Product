#!/usr/bin/env python3
"""캐릭터 PNG 다듬기 — 흰 배경 제거 + 크기 줄이기 (개발 단계 1회성)

만들어진 캐릭터 그림이 '흰 배경이 칠해진' 불투명 PNG라, 보라색 카드 위에 올리면
흰 네모가 그대로 보인다. 배경만 지우고 캐릭터는 그대로 둬야 한다.

⚠ 핵심: "흰색이면 다 지운다"로 하면 안 된다. 흰 토끼·펭귄 배까지 뚫려서
   몸에 구멍이 난다(이 저장소에서 실제로 겪은 사고). 그래서 바깥 가장자리에서
   시작해 번지는 방식(flood fill)으로 '바깥의 흰색'만 지운다.

크기도 줄인다: 원본 1024x1024인데 화면에서는 40~74px로 쓴다. 1MB짜리를
그대로 내려받게 하면 휴대폰 데이터만 잡아먹는다. 256px로 줄이면 충분하다.

필요: Python 3 + Pillow.  사용: python3 tools/trim-chars.py
"""
from pathlib import Path
from collections import deque
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
CHAR_DIR = ROOT / "public" / "img" / "char"
TARGET = 256          # 화면에서 최대 74px — 고해상도 화면(3배)까지 감당하고도 남는다
TOLERANCE = 26        # 이 정도까지는 '흰 배경'으로 본다 (그림자·계단현상 감안)


def white_ish(px):
    r, g, b = px[:3]
    return r >= 255 - TOLERANCE and g >= 255 - TOLERANCE and b >= 255 - TOLERANCE


def strip_outer_white(im):
    """바깥 가장자리와 이어진 흰색만 투명하게. 캐릭터 안쪽 흰색은 건드리지 않는다."""
    im = im.convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    q = deque()

    def push(x, y):
        i = y * w + x
        if not seen[i] and white_ish(px[x, y]):
            seen[i] = 1
            q.append((x, y))

    for x in range(w):
        push(x, 0)
        push(x, h - 1)
    for y in range(h):
        push(0, y)
        push(w - 1, y)

    while q:
        x, y = q.popleft()
        px[x, y] = (255, 255, 255, 0)
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                push(nx, ny)
    return im


def main():
    files = sorted(CHAR_DIR.glob("*.png"))
    if not files:
        print("캐릭터 PNG가 없습니다"); return
    for f in files:
        before = f.stat().st_size
        im = strip_outer_white(Image.open(f))

        # 잘린 자국이 도드라지지 않게 알파만 아주 살짝 부드럽게
        r, g, b, a = im.split()
        a = a.filter(ImageFilter.GaussianBlur(0.6))
        im = Image.merge("RGBA", (r, g, b, a))

        box = im.getbbox()                      # 투명 여백 잘라내기
        if box:
            im = im.crop(box)
        im.thumbnail((TARGET, TARGET), Image.LANCZOS)

        # 정사각형 가운데 정렬 — 화면마다 크기가 들쭉날쭉하지 않게
        canvas = Image.new("RGBA", (TARGET, TARGET), (0, 0, 0, 0))
        canvas.paste(im, ((TARGET - im.width) // 2, (TARGET - im.height) // 2), im)
        canvas.save(f, "PNG", optimize=True)

        after = f.stat().st_size
        print(f"{f.name}: {before // 1024}KB → {after // 1024}KB")


if __name__ == "__main__":
    main()
