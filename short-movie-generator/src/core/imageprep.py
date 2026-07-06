"""imageprep — 소스 이미지를 목표 9:16 캔버스로 '우리가' 사전 합성.

목적(문제1 근본 해결): 16:9 이미지를 그대로 Veo에 주면 Veo가 위·아래 세로 확장 구역을
스스로 상상해 검은 바·기포를 그린다. 그 확장을 Veo에 맡기지 않고 여기서 결정적으로 만든다.

방식(seam 없는 풀프레임):
- 전경(sharp): 원본을 화면 너비에 맞춰 중앙 배치 (생물 전체 보존, 잘림 없음)
- 배경(fill): 원본을 9:16로 cover-크롭 → 강한 블러 + 어둡게 → 심해 어둠이 자연스럽게 이어짐
  → 하드 검은 바가 아니라 '어두운 물이 계속된다'로 읽힘 = 이미지화 느낌 제거
- 이미 세로로 충분히 긴 이미지는 그냥 cover-크롭(배경 불필요)
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


def _cover_crop(im: Image.Image, w: int, h: int) -> Image.Image:
    scale = max(w / im.width, h / im.height)
    cw, ch = round(im.width * scale), round(im.height * scale)
    resized = im.resize((cw, ch), Image.LANCZOS)
    left, top = (cw - w) // 2, (ch - h) // 2
    return resized.crop((left, top, left + w, top + h))


def to_vertical_9x16(
    src_path: str, out_path: str, w: int = 720, h: int = 1280,
    bg_blur: int = 65, bg_darken: float = 0.28, feather: int = 56,
) -> str:
    """소스 이미지 → 9:16 세로 캔버스(블러-다크 연장). out_path 저장 후 경로 반환."""
    im = Image.open(src_path).convert("RGB")

    # 전경: 너비 맞춤
    fg_w = w
    fg_h = round(im.height * w / im.width)
    if fg_h >= h:  # 이미 세로가 충분 → cover-크롭으로 풀프레임(배경 불필요)
        _cover_crop(im, w, h).save(out_path, quality=92)
        return out_path

    fg = im.resize((fg_w, fg_h), Image.LANCZOS)

    # 배경: 9:16 cover-크롭 → 블러 + 어둡게 (심해 연장)
    bg = _cover_crop(im, w, h).filter(ImageFilter.GaussianBlur(bg_blur))
    bg = ImageEnhance.Brightness(bg).enhance(bg_darken)

    # 전경을 배경 위 중앙에 페더(부드러운 경계)로 합성
    canvas = bg.copy()
    y = (h - fg_h) // 2
    mask = Image.new("L", (fg_w, fg_h), 255)
    if feather > 0:  # 상·하단 feather 그라디언트 (seam 완화)
        px = mask.load()
        for row in range(min(feather, fg_h // 2)):
            a = int(255 * row / feather)
            for col in range(fg_w):
                px[col, row] = a
                px[col, fg_h - 1 - row] = a
    canvas.paste(fg, (0, y), mask)
    canvas.save(out_path, quality=92)
    return out_path
