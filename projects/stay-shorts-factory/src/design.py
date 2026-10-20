#!/usr/bin/env python3
"""자막·카드 디자인 체계 — 2026-10-11 운영자 "자막이 촌스럽다, 영상 UI 를 깔끔하게, 글씨가 눈에 잘 들어오게".

v1 까지의 자막: 지마켓산스 68px 흰 글자 + 6px 검은 외곽선, 훅은 손글씨 104px + 7px 외곽선, 노란 스티커 뱃지, 한 화면에 요소 5종.
바꾼 원칙:
  - 글꼴 하나: Pretendard ExtraBold(자막) / SemiBold(작은 글). OFL 무료 → assets/fonts 에 둔다. 손글씨·노란색 폐기.
  - 두꺼운 외곽선 대신 부드러운 그림자(또는 반투명 바). 포인트 색은 [대괄호] 한 단어에만.
  - (v2) 최대 2줄, 글자 84px(훅 100px), 화면 높이 58% 자리 — **v3 에서 폐기**(아래 GRID). 한 줄 강제로 글자를 줄이는 짓 금지.
  - **v3 글자 그리드 (2026-10-12 운영자 "같은 유형 글씨는 항상 같은 위치 — 기본을 똑바로" · 절대 규칙)**: 글자 유형마다 (크기 · x · y · 줄 수) 를 `GRID` 에
    한 번만 적고 모든 컷·카드가 그 값만 쓴다. 자막은 첫 줄 y 고정(위 정렬 슬롯), 줄 수가 달라도 첫 줄·라벨 위치 불변. 크기 자동 축소 금지 —
    안 들어가면 대본을 줄인다(`fits` 로 대본 검사 단계에서 거른다). 고지문은 위쪽 한 자리(컷·끝 카드 동일). 알약·칩·태그 전부 폐기.
  - (v2) 화면 요소는 자막 + 작은 폴더 표시(왼쪽 위) + 고지문(아래 작게) 만 — **v3 에서 폐기**: 화면 요소는 고지문(위) + 장소 라벨(작게) + 문장 자막(아래) 뿐.
  - 끝 카드: 훅 사진 선명 + 세로 그라데이션(블러 금지) + 왼쪽 정렬 헤드라인 "프로필 링크에서 / 폴더를 열어 보세요" + 폴더 행 카드(이름 · N번). 버튼 그림 폐기.
네 가지 시안(STYLES)을 PNG 로 만들어 운영자가 고른다 → request.json "caption_style" (기본 shadow)."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920
FONT_X = ROOT / "assets" / "fonts" / "Pretendard-ExtraBold.otf"
FONT_S = ROOT / "assets" / "fonts" / "Pretendard-SemiBold.otf"
FALLBACK = [ROOT.parent / "coupang-shorts-factory" / "assets" / "fonts" / "GmarketSansBold.ttf", ROOT / "assets" / "fonts" / "GmarketSansBold.ttf"]

# 디자인 토큰 (2026-10-11 운영자 "UI·화면 구성을 촌스럽게 하지 마라, 제대로 세련되게" → 아래 값 외의 임의 색·크기·여백 금지)
INK = (11, 13, 18)                                    # 글자·배경 어두운색
ACCENT = (255, 138, 91)                               # 포인트 색 하나 — 웜 코랄 (청록 물 사진의 보색이라 민트보다 또렷하다). 화면당 1~2곳만
MARGIN = 72                                           # 좌우 여백 그리드
RADIUS = 28                                           # 카드·칩 모서리
SAFE_RIGHT = 180                                      # 릴스·쇼츠 오른쪽 아이콘 영역 — 카드는 이 안으로 들어가지 않는다
CHIP_FILL, CHIP_BORDER = (*INK, 130), (255, 255, 255, 75)   # 사진 위 칩(폴더 표시·후기·태그)은 어두운 유리 — 흰 유리는 밝은 물 사진에서 묻힌다(실측)
TYPE = {"eyebrow": 34, "body": 40, "label": 44, "caption": 84, "headline": 88, "hook": 100, "fine": 26}   # 화면당 3단계까지만 섞는다

STYLES = {
    "shadow": {"ko": "그림자형", "accent": ACCENT, "desc": "흰 글자 + 얇은 어두운 선 + 2겹 그림자 + 은은한 어둡기 띠 (확정 · 기본)"},
    "bar": {"ko": "바형", "accent": (255, 179, 107), "desc": "줄마다 반투명 어두운 바 위 흰 글자"},
    "highlight": {"ko": "형광펜형", "accent": (255, 107, 107), "desc": "흰 박스 위 어두운 글자 (잡지 느낌)"},
    "glass": {"ko": "패널형", "accent": (94, 234, 212), "desc": "한 장의 어두운 패널 + 얇은 테두리 안에 글자"},
}
DEFAULT_STYLE = "shadow"
GRADE = "eq=contrast=1.04:saturation=1.08"           # 공식·쿠팡 사진 색감 차이를 줄이는 공통 보정 (ffmpeg -vf 조각)
CY = 0.58                                             # 자막 세로 중심 (화면 높이 비율)
MAX_LINES, LINE_CHARS = 2, 11


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    p = FONT_X if bold else FONT_S
    if not p.exists():
        p = next((f for f in FALLBACK if f.exists()), None)
        if p is None:
            raise RuntimeError("글꼴이 없습니다 (assets/fonts/Pretendard-*.otf)")
    return ImageFont.truetype(str(p), size)


def one_line(text: str) -> str:
    """줄바꿈·탭·연속 공백을 공백 하나로. Pillow 는 줄바꿈 든 글의 폭을 못 잰다(ValueError) — stay-run-44 실측: 모델이 훅 제목 후보에 줄바꿈을 넣어 실행이 멈췄다."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def segments(text: str) -> list[tuple[str, bool]]:
    """'실내 [파도풀]은' → [('실내 ', False), ('파도풀', True), ('은', False)]"""
    text = one_line(text)
    out = []
    for part in re.split(r"(\[[^\]]+\])", text):
        if not part:
            continue
        if part.startswith("[") and part.endswith("]"):
            out.append((part[1:-1], True))
        else:
            out.append((part, False))
    return out


def plain(text: str) -> str:
    return text.replace("[", "").replace("]", "")


def _width(d: ImageDraw.ImageDraw, segs, f) -> float:
    return sum(d.textlength(t, font=f) for t, _ in segs)


def wrap_marked(d: ImageDraw.ImageDraw, text: str, f, max_w: float, max_lines: int = MAX_LINES) -> list[list[tuple[str, bool]]]:
    """대괄호 강조를 유지하면서 낱말 단위로 줄을 나눈다. 너무 긴 낱말은 글자 단위로 끊는다."""
    words = []
    for seg, acc in segments(text):
        for i, w in enumerate(seg.split(" ")):
            if w:
                words.append((w, acc))
            if i < len(seg.split(" ")) - 1:
                words.append((" ", False))
    lines, cur = [], []
    for w, acc in words:
        trial = cur + [(w, acc)]
        if _width(d, trial, f) <= max_w or not [x for x in cur if x[0].strip()]:
            cur = trial
        else:
            lines.append(cur); cur = [(w, acc)] if w != " " else []
    if cur:
        lines.append(cur)
    cleaned = []
    for ln in lines:
        while ln and ln[0][0] == " ":
            ln = ln[1:]
        while ln and ln[-1][0] == " ":
            ln = ln[:-1]
        if ln:
            cleaned.append(ln)
    return cleaned[:max_lines] if len(cleaned) <= max_lines else _force(d, text, f, max_w, max_lines)


def _force(d, text, f, max_w, max_lines):
    """낱말 나눔으로 안 되면 글자 수로 균등하게 나눈다 (강조는 글자 단위로 유지)."""
    chars = []
    for seg, acc in segments(text):
        chars += [(c, acc) for c in seg]
    n = max(1, min(max_lines, -(-len(chars) // LINE_CHARS)))
    per = -(-len(chars) // n)
    lines = [chars[i:i + per] for i in range(0, len(chars), per)][:max_lines]
    out = []
    for ln in lines:
        merged = []
        for c, acc in ln:
            if merged and merged[-1][1] == acc:
                merged[-1] = (merged[-1][0] + c, acc)
            else:
                merged.append((c, acc))
        out.append(merged)
    return out


def fit_font(d, text, size, max_w, min_size=56, max_lines=MAX_LINES):
    while size > min_size:
        f = font(size)
        lines = wrap_marked(d, text, f, max_w, max_lines)
        joined = "".join(t for ln in lines for t, _ in ln).replace(" ", "")
        if len(lines) <= max_lines and len(joined) >= len(plain(text).replace(" ", "")) and all(_width(d, ln, f) <= max_w for ln in lines):
            return f, lines
        size -= 4
    f = font(min_size)
    return f, wrap_marked(d, text, f, max_w, max_lines)


def _draw_segs(d, x, y, segs, f, fill, accent, stroke=0, stroke_fill=None):
    for t, acc in segs:
        d.text((x, y), t, font=f, fill=accent if acc else fill, stroke_width=stroke, stroke_fill=stroke_fill)
        x += d.textlength(t, font=f)


def _scrim(im: Image.Image, top: int, bottom: int, peak: float = 0.30):
    """자막 뒤 세로 띠: 가운데가 가장 어둡고(peak) 위아래로 부드럽게 사라진다. 박스처럼 보이지 않으면서 밝은 사진 위 대비를 보장한다."""
    top, bottom = max(0, top), min(H, bottom)
    hgt = bottom - top
    if hgt <= 0:
        return
    mid = hgt / 2
    rows = []
    for y in range(hgt):
        t = 1 - abs(y - mid) / mid                 # 0(가장자리) → 1(가운데)
        rows.append(int(255 * peak * (t * t * (3 - 2 * t))))   # smoothstep
    mask = Image.new("L", (1, hgt))
    mask.putdata(rows)
    mask = mask.resize((W, hgt))
    band = Image.new("RGBA", (W, hgt), (0, 0, 0, 255))
    band.putalpha(mask)
    im.alpha_composite(band, (0, top))


def glass(im: Image.Image, box, radius: int = 999, fill=(255, 255, 255, 30), border=(255, 255, 255, 60)):
    """유리 칩: 반투명 흰 면 + 1px 밝은 테두리. 검은 반투명 박스보다 사진 위에서 가볍고 고급스럽다."""
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius, fill=fill, outline=border, width=2)
    im.alpha_composite(layer)                           # 불투명 사진 위에서도 '섞이게' (ImageDraw 는 알파를 덮어쓴다)
    return im


def gradient(im: Image.Image, y_from: int, y_to: int, a_from: float, a_to: float, color=INK):
    """세로 그라데이션 어둡기(위→아래). 사진을 흐리게 뭉개지 않고도 글자 자리를 어둡게 만든다 (블러는 사진을 버리는 짓이다)."""
    y_from, y_to = max(0, y_from), min(H, y_to)
    hgt = y_to - y_from
    if hgt <= 0:
        return im
    rows = []
    for y in range(hgt):
        t = y / max(1, hgt - 1)
        t = t * t * (3 - 2 * t)
        rows.append(int(255 * (a_from + (a_to - a_from) * t)))
    mask = Image.new("L", (1, hgt)); mask.putdata(rows); mask = mask.resize((W, hgt))
    band = Image.new("RGBA", (W, hgt), (*color, 255)); band.putalpha(mask)
    im.alpha_composite(band, (0, y_from))
    if y_to < H and a_to > 0:
        tail = Image.new("RGBA", (W, H - y_to), (*color, int(255 * a_to)))
        im.alpha_composite(tail, (0, y_to))
    return im


def folder_icon(d: ImageDraw.ImageDraw, x: int, y: int, size: int = 56, color=(255, 255, 255, 235)):
    """벡터 폴더 아이콘 (이모지 금지)."""
    tab_w, tab_h = int(size * 0.42), int(size * 0.16)
    d.rounded_rectangle([x, y + tab_h, x + size, y + int(size * 0.8)], int(size * 0.14), fill=color)
    d.rounded_rectangle([x, y, x + tab_w, y + tab_h * 2], int(size * 0.1), fill=color)


def draw_folder_row(im: Image.Image, x: int, y: int, w: int, folder: str, pos: int):
    """프로필 폴더 페이지의 한 줄을 그대로 닮은 카드: [폴더 아이콘] 폴더 이름 / '테마 폴더' ... [N번] — 시청자가 페이지에서 바로 알아본다."""
    hgt = 160
    glass(im, [x, y, x + w, y + hgt], RADIUS, fill=(255, 255, 255, 26), border=(255, 255, 255, 56))
    d = ImageDraw.Draw(im)
    folder_icon(d, x + 36, y + 52, 56)
    f1 = font(TYPE["label"]); f2 = font(26, bold=False); fb = font(36)
    badge = f"{pos}번"
    bw = d.textlength(badge, font=fb) + 44
    bx = x + w - 36 - bw
    name_w = bx - (x + 120) - 24
    name = folder
    while d.textlength(name, font=f1) > name_w and len(name) > 3:
        name = name[:-1]
    if name != folder:
        name = name[:-1] + "…"
    d.text((x + 120, y + 38), name, font=f1, fill=(255, 255, 255, 255))
    d.text((x + 120, y + 38 + f1.size + 8), "테마 폴더", font=f2, fill=(255, 255, 255, 140))
    d.rounded_rectangle([bx, y + hgt / 2 - 30, bx + bw, y + hgt / 2 + 30], 999, fill=(*ACCENT, 255))
    d.text((bx + 22, y + hgt / 2 - 22), badge, font=fb, fill=(*INK, 255))
    return im


def draw_caption(im: Image.Image, text: str, style: str = DEFAULT_STYLE, size: int = 76, cy: float = CY, sub: str = "", max_w: int | None = None):
    """자막 본문(최대 2줄)과 보조 줄을 그린다. im 은 RGBA."""
    st = STYLES.get(style) or STYLES[DEFAULT_STYLE]
    accent = (*st["accent"], 255)
    d = ImageDraw.Draw(im)
    max_w = max_w or (W - 180)
    f, lines = fit_font(d, text, size, max_w)
    lh = int(f.size * 1.22)
    total = lh * len(lines) + (58 if sub else 0)
    y0 = int(H * cy - total / 2)
    widths = [_width(d, ln, f) for ln in lines]

    if style == "shadow":
        # 운영자 2026-10-11 "A 로 가되 자막 더 크게, 글자 잘 보이게(그림자·외곽선 활용, 더 좋은 방법은 네가 골라)":
        # 외곽선만 두껍게 하면 v1 처럼 싸 보이고, 그림자만으로는 밝은 물·하늘 위에서 흰 글자가 묻힌다(실측: 파도풀 사진).
        # → 넷플릭스·유튜브 자막처럼 **자막 뒤에 눈에 안 띄는 어둡기 띠(scrim, 최대 30%)** 로 대비를 보장하고,
        #   얇은 어두운 선(3px·65%) + 가까운 그림자(또렷함) + 넓은 그림자(후광) 2겹으로 가장자리를 세운다. 사진이 어두우면 띠는 거의 안 보인다.
        band_top, band_bot = y0 - int(lh * 1.1), y0 + lh * len(lines) + int(lh * 1.0) + (58 if sub else 0)
        _scrim(im, band_top, band_bot, 0.30)
        for blur, alpha, dy in ((5, 170, 4), (18, 120, 10)):
            sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
            ds = ImageDraw.Draw(sh)
            for k, ln in enumerate(lines):
                _draw_segs(ds, (W - widths[k]) / 2, y0 + k * lh + dy, ln, f, (0, 0, 0, alpha), (0, 0, 0, alpha), stroke=3, stroke_fill=(0, 0, 0, alpha))
            im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
        d = ImageDraw.Draw(im)
        for k, ln in enumerate(lines):
            _draw_segs(d, (W - widths[k]) / 2, y0 + k * lh, ln, f, (255, 255, 255, 255), accent, stroke=3, stroke_fill=(12, 14, 20, 165))
    elif style == "bar":
        padx, pady, r = 30, 14, 24
        for k, ln in enumerate(lines):
            x = (W - widths[k]) / 2
            d.rounded_rectangle([x - padx, y0 + k * lh - pady + 6, x + widths[k] + padx, y0 + k * lh + f.size + pady + 2], r, fill=(10, 12, 18, 165))
        for k, ln in enumerate(lines):
            _draw_segs(d, (W - widths[k]) / 2, y0 + k * lh, ln, f, (255, 255, 255, 255), accent)
    elif style == "highlight":
        padx, pady, r = 26, 10, 14
        for k, ln in enumerate(lines):
            x = (W - widths[k]) / 2
            d.rounded_rectangle([x - padx, y0 + k * lh - pady + 8, x + widths[k] + padx, y0 + k * lh + f.size + pady], r, fill=(255, 255, 255, 238))
        for k, ln in enumerate(lines):
            _draw_segs(d, (W - widths[k]) / 2, y0 + k * lh, ln, f, (22, 24, 30, 255), accent)
    else:  # glass
        pw = max(widths) + 96
        x0 = (W - pw) / 2
        y1 = y0 - 34
        y2 = y0 + lh * len(lines) + (58 if sub else 0) + 26
        d.rounded_rectangle([x0, y1, x0 + pw, y2], 30, fill=(12, 14, 22, 150), outline=(255, 255, 255, 70), width=2)
        for k, ln in enumerate(lines):
            _draw_segs(d, (W - widths[k]) / 2, y0 + k * lh, ln, f, (255, 255, 255, 255), accent)
    if sub:
        fs = font(40, bold=False)
        s = sub if d.textlength(sub, font=fs) <= max_w else sub[:max(4, int(len(sub) * max_w / d.textlength(sub, font=fs)) - 1)] + "…"
        sw = d.textlength(s, font=fs)
        ys = y0 + lh * len(lines) + 10
        if style in ("shadow", "glass"):
            d.text(((W - sw) / 2, ys), s, font=fs, fill=(255, 255, 255, 215), stroke_width=2, stroke_fill=(0, 0, 0, 110))
        else:
            d.rounded_rectangle([(W - sw) / 2 - 20, ys - 6, (W + sw) / 2 + 20, ys + fs.size + 10], 16, fill=(10, 12, 18, 150))
            d.text(((W - sw) / 2, ys), s, font=fs, fill=(255, 255, 255, 230))
    return im


def draw_pill(im: Image.Image, text: str, y: int = 118):
    """왼쪽 위 작은 폴더 표시 — '폴더 · 11월 실내 온수풀 · 1번'. 시청자가 어디서 찾을지 영상 내내 보인다."""
    d = ImageDraw.Draw(im)
    f = font(32, bold=False)
    tw = d.textlength(text, font=f)
    x = MARGIN - 16
    glass(im, [x, y, x + tw + 44 + 30, y + f.size + 24], fill=CHIP_FILL, border=CHIP_BORDER)
    d = ImageDraw.Draw(im)
    d.ellipse([x + 20, y + f.size / 2 + 5, x + 34, y + f.size / 2 + 19], fill=(*ACCENT, 255))     # 포인트 점 하나
    d.text((x + 48, y + 11), text, font=f, fill=(255, 255, 255, 235))
    return im


def draw_chip(im: Image.Image, text: str, sub: str = "", y: int = 118):
    """오른쪽 위 작은 칩 — '최근 30일 후기 719건' (1~2초만 보인다)."""
    d = ImageDraw.Draw(im)
    f = font(34, bold=False); f2 = font(22, bold=False)
    tw = max(d.textlength(text, font=f), d.textlength(sub, font=f2) if sub else 0)
    x2 = W - (MARGIN - 16)
    hgt = f.size + 22 + (f2.size + 6 if sub else 0)
    glass(im, [x2 - tw - 40, y, x2, y + hgt], 24, fill=CHIP_FILL, border=CHIP_BORDER)
    d = ImageDraw.Draw(im)
    d.text((x2 - tw - 20, y + 10), text, font=f, fill=(255, 255, 255, 255))
    if sub:
        d.text((x2 - tw - 20, y + f.size + 14), sub, font=f2, fill=(255, 255, 255, 175))
    return im


def draw_disclosure(im: Image.Image, text: str, y: int = 1772, size: int = 24):
    d = ImageDraw.Draw(im)
    f = font(size, bold=False)
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= W - 200:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    for ln in lines:
        lw = d.textlength(ln, font=f)
        d.text(((W - lw) / 2, y), ln, font=f, fill=(255, 255, 255, 185), stroke_width=1, stroke_fill=(0, 0, 0, 120))
        y += size + 8
    return im


def caption_png(out: Path, text: str, style: str = DEFAULT_STYLE, hook: bool = False, sub: str = "", pill: str = "", disclosure: str = ""):
    """컷 하나의 자막 겹침판(투명 PNG). hook 은 더 크고 가운데에 가깝게."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if text:
        draw_caption(im, text, style, size=100 if hook else 84, cy=0.52 if hook else CY, sub=sub)
    if pill:
        draw_pill(im, pill)
    if disclosure:
        draw_disclosure(im, disclosure)
    im.save(out)
    return out


def draw_tag(im: Image.Image, text: str, cy: float = CY):
    """자막 아래 작은 태그 칩 — '+ 히노키 사우나' (사진에 없는 시그니처를 "이것도 있다"로 표시). 유리 칩 + 코랄 점."""
    d = ImageDraw.Draw(im)
    f = font(40)
    text = text if text.startswith("+") else "+ " + text
    tw = d.textlength(text, font=f)
    x = (W - tw - 64) / 2
    y = int(H * cy) + 150
    glass(im, [x, y, x + tw + 64, y + f.size + 26], fill=CHIP_FILL, border=CHIP_BORDER)
    d = ImageDraw.Draw(im)
    d.ellipse([x + 20, y + f.size / 2 + 6, x + 34, y + f.size / 2 + 20], fill=(*ACCENT, 255))
    d.text((x + 46, y + 12), text.lstrip("+ "), font=f, fill=(255, 255, 255, 245))
    return im


def tag_png(out: Path, text: str):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_tag(im, text)
    im.save(out)
    return out


def chip_png(out: Path, text: str, sub: str = ""):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_chip(im, text, sub)
    im.save(out)
    return out


def cover(im: Image.Image, w: int = W, h: int = H) -> Image.Image:
    iw, ih = im.size
    if iw / ih > w / h:
        cw, ch = int(round(ih * w / h)), ih
        x, y = (iw - cw) // 2, 0
    else:
        cw, ch = iw, int(round(iw * h / w))
        x, y = 0, (ih - ch) // 2
    return im.crop((x, y, x + cw, y + ch)).resize((w, h), Image.LANCZOS)


def end_card(out: Path, bg: Path | None, folder: str, pos: int, style: str = DEFAULT_STYLE, disclosure: str = "", label: str = "객실 종류 · 예약 링크"):
    """끝 카드 (2026-10-11 재설계 → 2026-10-12 운영자 "디자인 좋다" 확정 · '폴더' 낱말만 교체):
    **선명한 사진 + 아래쪽 어둡기 그라데이션**, 왼쪽 정렬 편집 타이포 — 작은 안내 → 큰 제목 2줄 "프로필 링크 / [N번]에 있어요"(N = 숙소 고유 번호, 코랄)
    → 그 아래 테마명 한 줄(folder). 폴더 행 카드·아이콘 폐기. 오른쪽 아이콘 영역(180px)은 비운다. 숙소 이름 없음. 고지문은 컷과 같은 위쪽 자리."""
    if bg and Path(bg).exists():
        base = cover(Image.open(bg).convert("RGB"))
    else:
        base = Image.new("RGB", (W, H), INK)
    im = base.convert("RGBA")
    gradient(im, 0, 420, 0.28, 0.0)                     # 위쪽은 살짝만 (폴더 표시 자리)
    gradient(im, 640, 1150, 0.0, 0.80)                  # 글자 자리(제목 1056~)부터 아래는 고르게 어둡게, 사진은 위쪽에 선명하게 남긴다
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))        # 반투명 글자·칩은 투명 층에 그려 합성한다
    d = ImageDraw.Draw(ov)
    x = MARGIN
    card_w = W - MARGIN - SAFE_RIGHT - MARGIN // 2        # 오른쪽 아이콘 영역 회피
    f_eye = font(TYPE["eyebrow"], bold=False)
    d.text((x, 1004), label, font=f_eye, fill=(255, 255, 255, 180))
    f_h = font(TYPE["headline"])
    lh = int(f_h.size * 1.14)
    d.text((x, 1056), "프로필 링크", font=f_h, fill=(255, 255, 255, 255))
    _draw_segs(d, x, 1056 + lh, [(f"{int(pos)}번", True), ("에 있어요", False)], f_h, (255, 255, 255, 255), (*ACCENT, 255))
    if folder:
        d.text((x, 1056 + 2 * lh + 40), str(folder), font=font(TYPE["body"], bold=False), fill=(255, 255, 255, 170))
    im.alpha_composite(ov)
    if disclosure:
        draw_disclosure_top(im, disclosure)                 # v3: 고지문은 컷과 같은 자리(위쪽) — 같은 유형 글자는 항상 같은 위치
    im.convert("RGB").save(out, "JPEG", quality=92)
    return out


def mockups(photo: Path, out_dir: Path, caption: str = "실내 [파도풀]은 11월에도 따뜻해요", pill: str = "폴더 · 11월 실내 온수풀 · 1번",
            disclosure: str = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다", folder: str = "11월 실내 온수풀 온천") -> Path:
    """운영자 선택용 시안: 같은 사진·같은 자막으로 4가지 스타일 + 끝 카드 → 한 장(caption_mockups.jpg)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    base = cover(Image.open(photo).convert("RGB"))
    tiles = []
    for key, st in STYLES.items():
        im = base.convert("RGBA")
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_caption(ov, caption, key, size=84, sub="아쉬움: 주말엔 붐빈다는 후기" if key == "bar" else "")
        draw_pill(ov, pill)
        if key == "shadow":
            draw_chip(ov, "최근 30일 후기 719건", "네이버 블로그 기준")
        draw_disclosure(ov, disclosure)
        im.alpha_composite(ov)
        p = out_dir / f"mock_{key}.jpg"
        im.convert("RGB").save(p, "JPEG", quality=90)
        tiles.append((f"{'ABCD'[len(tiles)]}  {st['ko']} — {st['desc']}", p))
    hook = base.convert("RGBA")
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_caption(ov, "추운데 애들 [어디] 데려가지?", "shadow", size=100, cy=0.52)
    draw_disclosure(ov, disclosure)
    hook.alpha_composite(ov)
    ph = out_dir / "mock_hook.jpg"; hook.convert("RGB").save(ph, "JPEG", quality=90)
    pe = end_card(out_dir / "mock_end.jpg", photo, folder, 1, "shadow", disclosure)
    tiles += [("훅 자막 (A 스타일 · 92px)", ph), ("끝 카드 (프로필 → 폴더 N번)", pe)]
    tw, th = 360, 640
    cols = 3
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * (tw + 24) + 24, rows * (th + 96) + 24), (24, 26, 32))
    d = ImageDraw.Draw(sheet)
    fl = font(22, bold=False)
    for k, (label, p) in enumerate(tiles):
        x = 24 + (k % cols) * (tw + 24); y = 24 + (k // cols) * (th + 96)
        sheet.paste(Image.open(p).resize((tw, th), Image.LANCZOS), (x, y))
        for i, line in enumerate(_split(label, 17)):
            d.text((x, y + th + 10 + i * 26), line, font=fl, fill=(235, 235, 240))
    out = out_dir / "caption_mockups.jpg"
    sheet.save(out, "JPEG", quality=88)
    return out


def _split(s: str, n: int) -> list[str]:
    return [s[i:i + n] for i in range(0, len(s), n)] or [""]


if __name__ == "__main__":
    import sys
    print(mockups(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "build/design")))


# ═══════════════════════════ v3 글자 그리드 (2026-10-12) ═══════════════════════════
# 운영자: "같은 유형의 글씨라면 항상 같은 위치에 있어야지 왜 제각각이야 — 핵심 규칙에 반영해서 똑바로 해".
# v2 가 흔들린 이유: 자막을 세로 '중심'에 맞춰 줄 수에 따라 첫 줄이 오르내렸고, fit_font 가 문장 길이에 따라 글자 크기를 84→56 으로 줄였고,
# 훅만 100px·52% 자리였고, 보조 줄(아쉬움)·태그가 블록을 밀었다. → 유형별 (크기·x·y·줄 수) 를 여기 한 번만 적고, 그 값 밖으로는 아무것도 못 나간다.
SAFE_BOTTOM = 1520                                    # 쇼츠·릴스 아래 400px(제목·채널·음악 표시) 위
SAFE_X1 = W - SAFE_RIGHT                              # 900 — 오른쪽 아이콘 기둥 앞
SUB_W = 800                                           # 자막 한 줄 최대 너비(가운데·왼쪽 정렬 공통 — 검사도 이 값으로)
CX = (MARGIN + SAFE_X1) // 2 + 40                     # 가운데 정렬 중심 x (오른쪽 아이콘을 피해 살짝 왼쪽) = 526
GRID = {
    "disclosure": {"size": 24, "x": MARGIN, "y": 172, "lh": 32, "lines": 2},            # 고지문 — 컷·끝 카드 동일 자리
    "kicker":     {"size": 72, "x": MARGIN, "y": 1222},                                   # 장소 라벨 — **왼쪽** 한 줄, 72px (2026-10-12 운영자 "주황 장소 문구 2배로" · 36→72), 대사 줄 바로 위
    "subtitle":   {"size": 72, "y": 1330, "lh": 88, "lines": 1},                         # 대사 자막 — **가운데 한 줄, 2~3단어 가라오케식** (운영자 결정). 한 줄뿐이라 줄 수 변동 없음
    "hook":       {"size": 76, "bottom": 1418, "lh": 93, "lines": 3},                    # 훅(컷 1 전용) — 문장 전체, 마지막 줄 바닥을 대사 줄 바닥(1330+88)과 맞춘다
    "band":       {"top": 1150, "bottom": 1560, "peak": 0.34},                            # 어둡기 띠 — 대사 줄 중심(1374)에 고정, 글자 양과 무관
    # 훅 타이틀(컷 1 전용 · 2026-10-13 운영자 "훅 문구 중앙에 크게 — 나레이션 그대로 말고 요약해서 궁금증 유발").
    # 정중앙(0.50)은 실제 훅 컷 얼굴 자리(run-35 실측 0.45~0.55)라 얼굴을 가린다 → 위쪽 1/3 가운데(첫 줄 위 430 · 두 줄 바닥 718 = 0.37)에 고정.
    # 훅 컷 인물 얼굴은 이 바닥 아래(make_mini.HOOK_FACE_TOP_MIN)로 둔다.
    "hook_title": {"size": 120, "y": 430, "lh": 144, "lines": 2, "w": 840, "scrim": (330, 820, 0.38)},
}
CHUNK_WORDS = 3                                       # 가라오케 조각 = 최대 3단어 (운영자 "2~3단어 위주")


def fits(text: str, role: str = "subtitle") -> tuple[bool, int]:
    """문장이 고정 크기·고정 너비에서 허용 줄 수 안에 들어가는지. 대본 검사 단계에서 쓴다 — 렌더 단계에서는 절대 글자를 줄이지 않는다."""
    g = GRID[role]
    d = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    f = font(g["size"])
    mw = g.get("w", SUB_W)
    if role == "hook_title":                                                    # 훅 제목은 띄어쓰기 자리에서만 두 줄 — 낱말 안을 끊어야 들어가면 탈락(제목을 줄인다)
        lines = title_lines(d, text, f, mw, clean_only=True)
        if lines is None:
            return False, 3
    else:
        lines = wrap_marked(d, text, f, mw, max_lines=12)
    joined = "".join(t for ln in lines for t, _ in ln).replace(" ", "")
    ok = len(lines) <= g["lines"] and len(joined) >= len(plain(text).replace(" ", "")) and all(_width(d, ln, f) <= mw for ln in lines)
    return ok, len(lines)


_PUNCT_END = re.compile(r"[,.!?，。]$")


def chunk_words(text: str, max_words: int = CHUNK_WORDS) -> list[str]:
    """가라오케 조각 나누기: 띄어쓰기 단위로 2~3단어씩. 쉼표·마침표 뒤에서는 반드시 끊고, 한 조각은 GRID 대사 크기로 한 줄(SUB_W)에 들어가야 한다.
    마지막 조각이 1단어로 남으면 앞 조각에 붙인다(붙여도 한 줄이면). 렌더가 아니라 **대본 검사**가 이 함수로 거른다."""
    d = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    f = font(GRID["subtitle"]["size"])
    words = [w for w in one_line(plain(text)).split(" ") if w]
    chunks, cur = [], []
    def w_of(ws): return d.textlength(" ".join(ws), font=f)
    for w in words:
        trial = cur + [w]
        if cur and (len(trial) > max_words or w_of(trial) > SUB_W):
            chunks.append(cur); cur = [w]
        else:
            cur = trial
        if _PUNCT_END.search(w):
            chunks.append(cur); cur = []
    if cur:
        chunks.append(cur)
    if len(chunks) >= 2 and len(chunks[-1]) == 1 and len(chunks[-2]) < max_words and w_of(chunks[-2] + chunks[-1]) <= SUB_W \
            and not _PUNCT_END.search(chunks[-2][-1]):
        chunks[-2] = chunks[-2] + chunks[-1]; chunks.pop()
    return [" ".join(c) for c in chunks]


def fits_chunks(text: str) -> tuple[bool, list[str]]:
    """대사 문장을 가라오케 조각으로 나눴을 때 모든 조각이 한 줄에 들어가는지 (한 단어가 너무 길면 실패)."""
    d = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    f = font(GRID["subtitle"]["size"])
    ch = chunk_words(text)
    return all(d.textlength(c, font=f) <= SUB_W for c in ch) and len(ch) > 0, ch


def draw_disclosure_top(im: Image.Image, text: str):
    g = GRID["disclosure"]
    d = ImageDraw.Draw(im)
    f = font(g["size"], bold=False)
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= W - 2 * MARGIN:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    for k, ln in enumerate(lines[:g["lines"]]):
        d.text((g["x"], g["y"] + k * g["lh"]), ln, font=f, fill=(255, 255, 255, 170), stroke_width=1, stroke_fill=(0, 0, 0, 110))
    return im


def _shadow_lines(im: Image.Image, lines, f, xs, y0: int, lh: int, accent=(*ACCENT, 255)):
    """자막 A 확정안의 글자 처리: 가까운 그림자 + 넓은 후광 2겹 + 3px 어두운 선. 위치는 호출자가 고정해 준다."""
    for blur, alpha, dy in ((5, 170, 4), (18, 120, 10)):
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
        for k, ln in enumerate(lines):
            _draw_segs(ds, xs[k], y0 + k * lh + dy, ln, f, (0, 0, 0, alpha), (0, 0, 0, alpha), stroke=3, stroke_fill=(0, 0, 0, alpha))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(im)
    for k, ln in enumerate(lines):
        _draw_segs(d, xs[k], y0 + k * lh, ln, f, (255, 255, 255, 255), accent, stroke=3, stroke_fill=(12, 14, 20, 165))


def draw_band(im: Image.Image):
    """대사 줄 뒤 어둡기 띠 — 모든 컷에 같은 구간. 조각 겹침판이 아니라 **컷 고정 겹침판(frame)** 에 그려 깜빡이지 않게 한다."""
    b = GRID["band"]; _scrim(im, b["top"], b["bottom"], b["peak"])
    return im


def draw_label(im: Image.Image, text: str):
    """장소 라벨 — 왼쪽, 코랄 36px, 자리 고정 (운영자 2026-10-12 "장소 자막은 왼쪽")."""
    gk = GRID["kicker"]
    d = ImageDraw.Draw(im)
    d.text((gk["x"], gk["y"]), text, font=font(gk["size"]), fill=(*ACCENT, 255), stroke_width=2, stroke_fill=(0, 0, 0, 120))
    return im


def draw_subtitle(im: Image.Image, text: str, hook: bool = False):
    """대사 자막을 GRID 자리에 그린다. im 은 RGBA 1080×1920.
    - 대사(가라오케 조각 2~3단어): **가운데 한 줄**, y 고정, 72px. 한 줄에 안 들어가면 그리기 전에 fits_chunks() 로 걸렀어야 한다(여기서는 줄이지 않는다).
    - 훅(컷 1 전용): 문장 전체, 76px, 최대 3줄, 마지막 줄 바닥을 대사 줄 바닥에 맞춘다.
    띠(어둡기)는 frame 겹침판이 담당한다(draw_band)."""
    d = ImageDraw.Draw(im)
    g = GRID["hook" if hook else "subtitle"]
    f = font(g["size"])
    lines = wrap_marked(d, text, f, SUB_W, max_lines=g["lines"])
    lh = g["lh"]
    y0 = (g["bottom"] - lh * len(lines)) if hook else g["y"]
    widths = [_width(d, ln, f) for ln in lines]
    xs = [CX - w / 2 for w in widths]
    _shadow_lines(im, lines, f, xs, y0, lh)
    return im


def subtitle_png(out: Path, text: str, hook: bool = False) -> Path:
    """대사 조각(또는 훅 문장) 하나의 겹침판(투명 PNG)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_subtitle(im, text, hook)
    im.save(out, "PNG")
    return out


def title_lines(d: ImageDraw.ImageDraw, text: str, f, max_w: float, clean_only: bool = False):
    """훅 타이틀 줄 나누기: 한 줄에 들어가면 한 줄, 아니면 **띄어쓰기 자리에서만** 두 줄로 — 두 줄 너비가 가장 비슷한 자리.
    wrap_marked 는 '[정답]은' 처럼 강조와 조사 사이에서도 끊어 '은 여기'가 생겼다(2026-10-13 시안) → 낱말 안에서는 절대 안 끊는다.
    clean_only=True 면 띄어쓰기 자리로 못 나눌 때 None(검사용) — stay-run-38 '신전에서 물놀이 / 를 즐긴다고?' 가 예비 줄바꿈으로 통과했다."""
    text = one_line(text)
    one = segments(text)
    if _width(d, one, f) <= max_w:
        return [one]
    toks = [t for t in text.split(" ") if t]
    best = None
    for k in range(1, len(toks)):
        a, b = " ".join(toks[:k]), " ".join(toks[k:])
        if a.count("[") != a.count("]"):                                     # 강조 괄호 안에서는 안 끊는다
            continue
        wa, wb = _width(d, segments(a), f), _width(d, segments(b), f)
        if max(wa, wb) <= max_w and (best is None or max(wa, wb) < best[0]):
            best = (max(wa, wb), [segments(a), segments(b)])
    if best:
        return best[1]
    return None if clean_only else wrap_marked(d, text, f, max_w, max_lines=12)


def draw_hook_title(im: Image.Image, text: str, style: str = "shadow", y: int | None = None):
    """훅 타이틀 — 컷 1 의 큰 제목. 가운데 정렬, 120px, 최대 2줄, `[낱말]` 하나만 코랄.
    style "shadow": 부드러운 어둡기 띠 + 두꺼운 그림자(사진을 덜 가린다) · "box": 줄마다 어두운 둥근 상자(밝은 사진에서도 확실히 읽힌다).
    y 는 시안 비교용(정중앙 등) — 영상은 GRID 값만 쓴다."""
    g = GRID["hook_title"]
    d = ImageDraw.Draw(im)
    f = font(g["size"])
    lines = title_lines(d, text, f, g["w"])[:g["lines"]]
    lh = g["lh"]
    y0 = g["y"] if y is None else y
    widths = [_width(d, ln, f) for ln in lines]
    xs = [CX - w / 2 for w in widths]
    if style == "box":
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(layer)
        for k, w in enumerate(widths):
            top = y0 + k * lh - 6
            dl.rounded_rectangle((xs[k] - 30, top, xs[k] + w + 30, top + g["size"] + 30), 24, fill=(*INK, 214))
        im.alpha_composite(layer)
        d = ImageDraw.Draw(im)
        for k, ln in enumerate(lines):
            _draw_segs(d, xs[k], y0 + k * lh, ln, f, (255, 255, 255, 255), (*ACCENT, 255))
        return im
    st, sb, pk = g["scrim"]
    if y is not None:
        st, sb = st + (y - g["y"]), sb + (y - g["y"])
    _scrim(im, st, sb, pk)
    for blur, alpha, dy in ((6, 190, 5), (22, 140, 12)):
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
        for k, ln in enumerate(lines):
            _draw_segs(ds, xs[k], y0 + k * lh + dy, ln, f, (0, 0, 0, alpha), (0, 0, 0, alpha), stroke=5, stroke_fill=(0, 0, 0, alpha))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(im)
    for k, ln in enumerate(lines):
        _draw_segs(d, xs[k], y0 + k * lh, ln, f, (255, 255, 255, 255), (*ACCENT, 255), stroke=4, stroke_fill=(12, 14, 20, 190))
    return im


def hook_title_png(out: Path, text: str, style: str = "shadow") -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_hook_title(im, text, style)
    im.save(out, "PNG")
    return out


def label_png(out: Path, text: str) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_label(im, text)
    im.save(out, "PNG")
    return out


def frame_png(out: Path, disclosure: str, band: bool = True) -> Path:
    """모든 컷에 고정되는 겹침판 — 위쪽 고지문 + 대사 줄 어둡기 띠 (알약·칩 폐기). 띠를 여기 두면 조각이 바뀌어도 띠는 가만히 있다."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if band:
        draw_band(im)
    if disclosure:
        draw_disclosure_top(im, disclosure)
    im.save(out, "PNG")
    return out


def grid_sheet(frames: list[Path], out: Path, labels: list[str] | None = None, guides: bool = True, tw: int = 300) -> Path:
    """시안 여러 장을 가로로 놓고 GRID 기준선(라벨 y · 자막 첫 줄 y · 자막 바닥 · 안전 영역) 을 시트 전체에 그어 '같은 자리'를 눈으로 검증한다."""
    th = int(tw * H / W); gap = 20; top = 44
    sheet = Image.new("RGB", (gap + len(frames) * (tw + gap), top + th + gap), (18, 20, 26))
    d = ImageDraw.Draw(sheet); fl = font(22)
    for k, fp in enumerate(frames):
        sheet.paste(Image.open(fp).convert("RGB").resize((tw, th), Image.LANCZOS), (gap + k * (tw + gap), top))
        if labels and k < len(labels):
            d.text((gap + k * (tw + gap), 12), labels[k], font=fl, fill=(255, 255, 255))
    if guides:
        sc = th / H
        gt = GRID["hook_title"]
        for y, col, name in ((GRID["disclosure"]["y"], (120, 200, 255), "고지문"), (gt["y"], (200, 120, 255), "훅 제목"),
                             (gt["y"] + gt["lh"] * gt["lines"], (200, 120, 255), "훅 제목 바닥"), (GRID["kicker"]["y"], ACCENT, "라벨(왼쪽)"),
                             (GRID["subtitle"]["y"], (255, 255, 255), "대사 줄"), (GRID["hook"]["bottom"], (255, 255, 255), "대사·훅 바닥"),
                             (SAFE_BOTTOM, (255, 90, 90), "플랫폼 UI")):
            yy = top + int(y * sc)
            d.line([(0, yy), (sheet.width, yy)], fill=col, width=1)
            d.text((sheet.width - 150, yy - 24), name, font=font(18, bold=False), fill=col)
    sheet.save(out, "JPEG", quality=88)
    return out


# ═══════════════════════════ v9 요약 카드 (2026-10-19) ═══════════════════════════
# 운영자: "특장점 요약 — 배경 이미지만 흐리게, 세련된 텍스트 프레임 안에 글이 애니메이션과 함께 들어오고, 고객의 포인트와 숙소의 특장점을 집어 준다".
# 규칙 안에서 구현: 강한 블러(금지 ①) 대신 **약한 블러 + 어둡기 + 그라데이션**, 프레임은 토큰의 유리 칩, 왼쪽 정렬, 글자 3단계(눈썹 34 · 줄 44 · 고지문),
# 코랄 강조는 카드 전체에서 [대괄호] 한 곳, 안전영역(위 250 · 아래 420 · 오른쪽 180) 안. 자리는 GRID["card"] 에 고정(줄 수가 달라도 각 줄의 y 는 불변).
GRID["card"] = {"x": MARGIN, "top": 560, "w": W - MARGIN - SAFE_RIGHT - MARGIN // 2, "eyebrow": 44, "eyebrow_lh": 64, "point": 96, "point_lh": 140,
                "line": 72, "lh": 118, "gap": 36, "box_pad": 22}   # v10.1(2026-10-20 운영자 "카드 만들 거면 제대로 — 글씨도 안 보이고 AI스러워"): 유리 칩·블러 폐기 → 선명한 사진 + 아래 어둡기 + 줄마다 어두운 상자 위 큰 흰 글자(레퍼런스 표지 '서울인데 1박 5만 원' 방식)
GRID["card_point"] = {"size": GRID["card"]["point"], "w": GRID["card"]["w"], "lines": 2}      # fits 검사용 — 포인트 96px · 띄어쓰기 자리에서 두 줄까지
GRID["card_line"] = {"size": GRID["card"]["line"], "w": GRID["card"]["w"], "lines": 1}        # 답 72px · 한 줄(12자 이하)
# ── v10 특장점 라벨(2026-10-20 운영자 '2안 라벨만' → "특장점은 글씨 아주 크게") — 장소 라벨 자리(왼쪽 · 코랄)를 108px 로 키우고 두 줄까지 ──
GRID["feature"] = {"size": 108, "lh": 126, "x": MARGIN, "bottom": 1296, "w": SAFE_X1 - MARGIN - 24, "lines": 2}   # 아래 기준선 고정(자막 1330 위) · 1줄이면 자막 바로 위, 2줄이면 그 위로
CARD_EYEBROW, CARD_EYEBROW2 = "이런 고민이라면", "여기서는"


def fits_lines(text: str, role: str) -> bool:
    """띄어쓰기 자리에서만 줄을 나눠(낱말 안은 안 끊음) role 의 줄 수·폭 안에 들어가는지 — 라벨·제목·카드 줄 검사용."""
    g = GRID[role]
    d = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    lines = title_lines(d, text, font(g["size"]), g.get("w", SUB_W), clean_only=True)
    return lines is not None and len(lines) <= g["lines"]


def _shadowed(im: Image.Image, lines, f, xs, y0: int, lh: int, fill, stroke: int = 6):
    """큰 글자 처리: 넓은 그림자 2겹 + 두꺼운 어두운 선(밝은 사진에서도 읽힘). 라벨(코랄)·제목(흰색) 공통."""
    for blur, alpha, dy in ((6, 190, 5), (20, 130, 12)):
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ds = ImageDraw.Draw(sh)
        for k, ln in enumerate(lines):
            _draw_segs(ds, xs[k], y0 + k * lh + dy, ln, f, (0, 0, 0, alpha), (0, 0, 0, alpha), stroke=stroke, stroke_fill=(0, 0, 0, alpha))
        im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    d = ImageDraw.Draw(im)
    for k, ln in enumerate(lines):
        _draw_segs(d, xs[k], y0 + k * lh, ln, f, fill, fill, stroke=stroke, stroke_fill=(12, 14, 20, 210))
    return im


def draw_feature(im: Image.Image, text: str):
    """특장점 라벨 — 왼쪽 정렬 108px 코랄 + 두꺼운 어두운 선·그림자(레퍼런스의 검은 테두리 노란 글씨 역할). 띄어쓰기 자리에서만 2줄, 아래 기준선(bottom)에 맞춰 위로 쌓는다."""
    g = GRID["feature"]
    d = ImageDraw.Draw(im)
    f = font(g["size"])
    lines = (title_lines(d, text, f, g["w"]) or [segments(text)])[:g["lines"]]
    y0 = g["bottom"] - g["lh"] * len(lines)
    return _shadowed(im, lines, f, [g["x"]] * len(lines), y0, g["lh"], (*ACCENT, 255))


def feature_png(out: Path, text: str) -> Path:
    """특장점 라벨 겹침판 — 컷이 바뀌어도 같은 자리라 이어져 보인다(첫 컷만 페이드·올라오기는 render 가 정한다)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw_feature(im, text)
    im.save(out, "PNG")
    return out


def card_layout(point: str, answers: list[str]) -> dict:
    """카드 줄 배치(위에서 아래로 쌓음): 눈썹 → 포인트(96px · 띄어쓰기 자리에서 2줄까지) → 눈썹2 → 답(72px · 한 줄)들. 줄마다 어두운 상자."""
    g = GRID["card"]
    d = ImageDraw.Draw(Image.new("RGBA", (W, H)))
    fp, fl = font(g["point"]), font(g["line"])
    y = g["top"]
    rows = {"eyebrow": y}
    y += g["eyebrow_lh"]
    p_lines = (title_lines(d, point, fp, g["w"]) or [segments(point)])[:2]
    rows["point"] = (y, p_lines)
    y += g["point_lh"] * len(p_lines) + g["gap"]
    rows["eyebrow2"] = y
    y += g["eyebrow_lh"]
    rows["lines"] = []
    for t in answers:
        ls = (title_lines(d, t, fl, g["w"]) or [segments(t)])[:2]
        rows["lines"].append((y, ls))
        y += g["lh"] * len(ls)
    rows["bottom"] = y
    return rows


def card_fits(point: str, answers: list[str]) -> bool:
    """카드 전체가 플랫폼 UI 위(SAFE_BOTTOM) 안에 들어가는지."""
    return card_layout(point, answers)["bottom"] <= SAFE_BOTTOM - 24


def _box_lines(im: Image.Image, lines, f, x: int, y0: int, lh: int, size: int, fill=(255, 255, 255, 255), box=(*INK, 232)):
    """줄마다 어두운 둥근 상자 + 흰 글자([대괄호]는 코랄) — 레퍼런스 표지('서울인데 1박 5만 원')의 검은 띠 방식. 글자를 줄이지 않는다."""
    pad = GRID["card"]["box_pad"]
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(layer)
    d0 = ImageDraw.Draw(im)
    for k, ln in enumerate(lines):
        w = _width(d0, ln, f)
        top = y0 + k * lh - 6
        dl.rounded_rectangle((x - pad, top, x + w + pad, top + size + 30), 18, fill=box)
    im.alpha_composite(layer)
    d = ImageDraw.Draw(im)
    for k, ln in enumerate(lines):
        _draw_segs(d, x, y0 + k * lh, ln, f, fill, (*ACCENT, 255))
    return im


def card_bg(out: Path, photo: Path) -> Path:
    """요약 카드 배경: **선명한** 장점 사진 + 글자 자리부터 아래로 어둡기 그라데이션(블러·흐림 없음 — 사진이 진짜 숙소로 보여야 한다)."""
    im = cover(Image.open(photo).convert("RGB")).convert("RGBA")
    gradient(im, 380, 900, 0.0, 0.50)
    gradient(im, 900, H, 0.50, 0.72)
    im.convert("RGB").save(out, "JPEG", quality=92)
    return out


def card_frame_png(out: Path, point: str, answers: list[str], eyebrow: str = CARD_EYEBROW, eyebrow2: str = CARD_EYEBROW2) -> Path:
    """카드의 고정 요소 = 눈썹 글 2줄(코랄 44px · 그림자) — 애니메이션 첫 단계에 뜬다. 유리 칩·구분선 없음."""
    g, r = GRID["card"], card_layout(point, answers)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fe = font(g["eyebrow"])
    for y, t in ((r["eyebrow"], eyebrow), (r["eyebrow2"], eyebrow2)):                  # 눈썹 글도 작은 어두운 상자 위(밝은 하늘에서도 읽힘)
        w = d.textlength(t, font=fe)
        d.rounded_rectangle((g["x"] - 12, y - 4, g["x"] + w + 12, y + g["eyebrow"] + 12), 12, fill=(*INK, 200))
        d.text((g["x"], y), t, font=fe, fill=(*ACCENT, 255))
    im.save(out, "PNG")
    return out


def card_line_png(out: Path, lines, y: int, size: int, lh: int) -> Path:
    """카드 글 한 덩이(포인트 또는 답 하나 · 1~2줄) 겹침판 — 줄마다 어두운 상자 위 큰 흰 글자. 줄이기 없음."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _box_lines(im, lines, font(size), GRID["card"]["x"], y, lh, size)
    im.save(out, "PNG")
    return out


def card_layers(out_dir: Path, photo: Path, point: str, answers: list[str], eyebrow: str = CARD_EYEBROW, eyebrow2: str = CARD_EYEBROW2) -> dict:
    """렌더용 층: 배경(선명한 사진 + 어둡기) · 프레임(눈썹 2줄) · 글 덩이들(포인트 1 + 답 n). 렌더가 덩이마다 시차를 두고 띄운다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    g, r = GRID["card"], card_layout(point, answers)
    bg = card_bg(out_dir / "card_bg.jpg", photo)
    frame = card_frame_png(out_dir / "card_frame.png", point, answers, eyebrow, eyebrow2)
    y, pl = r["point"]
    lines = [card_line_png(out_dir / "card_l0.png", pl, y, g["point"], g["point_lh"])]
    for i, (y, ls) in enumerate(r["lines"], 1):
        lines.append(card_line_png(out_dir / f"card_l{i}.png", ls, y, g["line"], g["lh"]))
    return {"bg": bg, "frame": frame, "lines": lines, "rows": r}


def card_flat(out: Path, photo: Path, point: str, answers: list[str], eyebrow: str = CARD_EYEBROW, eyebrow2: str = CARD_EYEBROW2) -> Path:
    """층을 전부 합친 한 장(검수 시트·스토리보드 썸네일·시안용)."""
    tmp = out.parent / "_card_tmp"
    lay = card_layers(tmp, photo, point, answers, eyebrow, eyebrow2)
    im = Image.open(lay["bg"]).convert("RGBA")
    for p in [lay["frame"]] + lay["lines"]:
        im.alpha_composite(Image.open(p).convert("RGBA"))
    im.convert("RGB").save(out, "JPEG", quality=90)
    return out


def card_sheet(photos: list[Path], out: Path, point: str, answers: list[str], labels: list[str] | None = None, disclosure: str = "") -> Path:
    """운영자 승인용 시안 시트: 실제 사진 여러 장(밝음·중간·어두움)에 같은 카드를 얹고 안전영역·카드 자리 기준선을 긋는다."""
    frames = []
    for k, p in enumerate(photos):
        fp = out.parent / f"_card_{k}.jpg"
        card_flat(fp, p, point, answers)
        if disclosure:
            im = Image.open(fp).convert("RGBA"); draw_disclosure_top(im, disclosure); im.convert("RGB").save(fp, "JPEG", quality=90)
        frames.append(fp)
    tw = 360; th = int(tw * H / W); gap = 20; top = 44
    sheet = Image.new("RGB", (gap + len(frames) * (tw + gap), top + th + gap), (18, 20, 26))
    d = ImageDraw.Draw(sheet); fl = font(22)
    for k, fp in enumerate(frames):
        sheet.paste(Image.open(fp).convert("RGB").resize((tw, th), Image.LANCZOS), (gap + k * (tw + gap), top))
        if labels and k < len(labels):
            d.text((gap + k * (tw + gap), 12), labels[k], font=fl, fill=(255, 255, 255))
    sc = th / H
    g, r = GRID["card"], card_layout(point, answers)
    for y, col, name in ((250, (255, 90, 90), "위 안전영역"), (g["top"], (120, 200, 255), "카드 위"), (r["bottom"], (120, 200, 255), "카드 아래"), (SAFE_BOTTOM, (255, 90, 90), "플랫폼 UI")):
        yy = top + int(y * sc)
        d.line([(0, yy), (sheet.width, yy)], fill=col, width=1)
        d.text((sheet.width - 130, yy - 24), name, font=font(18, bold=False), fill=col)
    sheet.save(out, "JPEG", quality=88)
    return out
