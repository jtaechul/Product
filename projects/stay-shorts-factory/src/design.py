#!/usr/bin/env python3
"""자막·카드 디자인 체계 — 2026-10-11 운영자 "자막이 촌스럽다, 영상 UI 를 깔끔하게, 글씨가 눈에 잘 들어오게".

v1 까지의 자막: 지마켓산스 68px 흰 글자 + 6px 검은 외곽선, 훅은 손글씨 104px + 7px 외곽선, 노란 스티커 뱃지, 한 화면에 요소 5종.
바꾼 원칙:
  - 글꼴 하나: Pretendard ExtraBold(자막) / SemiBold(작은 글). OFL 무료 → assets/fonts 에 둔다. 손글씨·노란색 폐기.
  - 두꺼운 외곽선 대신 부드러운 그림자(또는 반투명 바). 포인트 색은 [대괄호] 한 단어에만.
  - 최대 2줄, 줄당 10자 안, 글자 84px(훅 100px), 화면 높이 58% 자리(플랫폼 UI·엄지 영역 회피). 한 줄 강제로 글자를 줄이는 짓 금지.
  - 화면 요소는 자막 + 작은 폴더 표시(왼쪽 위) + 고지문(아래 작게) 만. 후기 숫자는 작은 칩으로 1~2초만.
  - 끝 카드: 대표 사진 블러 배경 + "프로필 링크 → 폴더 N번" 한 가지 메시지. 버튼 그림 폐기.
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


def segments(text: str) -> list[tuple[str, bool]]:
    """'실내 [파도풀]은' → [('실내 ', False), ('파도풀', True), ('은', False)]"""
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
    glass(im, [x, y, x + tw + 44 + 30, y + f.size + 24])
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
    glass(im, [x2 - tw - 40, y, x2, y + hgt])
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
    f = font(36, bold=False)
    text = text if text.startswith("+") else "+ " + text
    tw = d.textlength(text, font=f)
    x = (W - tw - 64) / 2
    y = int(H * cy) + 150
    glass(im, [x, y, x + tw + 64, y + f.size + 26], fill=(255, 255, 255, 34), border=(255, 255, 255, 70))
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


def end_card(out: Path, bg: Path | None, folder: str, pos: int, style: str = DEFAULT_STYLE, disclosure: str = "", label: str = "객실 타입 · 가격대 · 예약 링크"):
    """끝 카드 (2026-10-11 재설계 — 운영자 "이 카드처럼 촌스럽게 하지 마라"):
    흐린 배경·가운데 정렬·화살표 폐기 → **선명한 사진 + 아래쪽 어둡기 그라데이션**, 왼쪽 정렬 편집 타이포(작은 안내 → 큰 제목 2줄),
    그 아래 **프로필 폴더 페이지의 한 줄을 닮은 카드**(아이콘 · 폴더 이름 · N번 코랄 뱃지). 오른쪽 아이콘 영역(180px)은 비운다. 숙소 이름 없음."""
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
    for k, line in enumerate(("프로필 링크에서", "폴더를 열어 보세요")):
        d.text((x, 1056 + k * lh), line, font=f_h, fill=(255, 255, 255, 255))
    draw_folder_row(ov, x, 1056 + 2 * lh + 44, card_w, folder, pos)
    d = ImageDraw.Draw(ov)
    if disclosure:
        f_fine = font(TYPE["fine"], bold=False)
        y = 1700
        words, lines, cur = disclosure.split(" "), [], ""
        for wd in words:
            t = (cur + " " + wd).strip()
            if d.textlength(t, font=f_fine) <= card_w:
                cur = t
            else:
                lines.append(cur); cur = wd
        if cur:
            lines.append(cur)
        for ln in lines:
            d.text((x, y), ln, font=f_fine, fill=(255, 255, 255, 135)); y += TYPE["fine"] + 8
    im.alpha_composite(ov)
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
