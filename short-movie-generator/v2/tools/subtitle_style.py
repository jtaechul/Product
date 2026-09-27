"""v2 하단 나레이션 자막 — 본편 컷과 엔딩 멘트가 **같은 모양**을 쓰도록 한 곳에 모은다(운영자 확정 2026-09-27).

화면 하단 반투명 검은 칩 + 흰 굵은 고딕(Noto Sans JP Bold). 한 줄 유지(두 줄 금지) — 넘치면 글자만 줄인다.
쇼츠 하단 UI(제목·버튼)를 피해 칩 아래 끝을 화면 높이의 80% 지점에 둔다.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[2] / "vendor" / "fonts" / "NotoSansJP-VF.ttf"
W, H = 720, 1280
SIZE = 34                 # 기본 글자 크기(작게 — 운영자 확정)
MIN_SIZE = 26             # 이보다 작게는 줄이지 않는다(가독성 하한)
MAX_W = W - 96            # 좌우 여백
BOTTOM = int(H * 0.80)    # 칩 아래 끝
PAD_X, PAD_Y = 22, 12


def _font(size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_name("Bold")
    return f


def fit_font(text: str) -> ImageFont.FreeTypeFont:
    size = SIZE
    while size > MIN_SIZE:
        f = _font(size)
        if f.getlength(text) <= MAX_W - 2 * PAD_X:
            return f
        size -= 1
    return _font(MIN_SIZE)


def render(text: str) -> Image.Image:
    """자막 한 장(RGBA, 720x1280)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = fit_font(text)
    tw = f.getlength(text)
    a, d = f.getmetrics()
    bw, bh = int(tw + 2 * PAD_X), a + d + 2 * PAD_Y
    x0, y0 = (W - bw) // 2, BOTTOM - bh
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=14, fill=(0, 0, 0, 150))
    dr.text((x0 + PAD_X, y0 + PAD_Y), text, font=f, fill=(255, 255, 255, 255))
    return im
