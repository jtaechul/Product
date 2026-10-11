#!/usr/bin/env python3
"""자막·카드 디자인 체계 — 2026-10-11 운영자 "자막이 촌스럽다, 영상 UI 를 깔끔하게, 글씨가 눈에 잘 들어오게".

v1 까지의 자막: 지마켓산스 68px 흰 글자 + 6px 검은 외곽선, 훅은 손글씨 104px + 7px 외곽선, 노란 스티커 뱃지, 한 화면에 요소 5종.
바꾼 원칙:
  - 글꼴 하나: Pretendard ExtraBold(자막) / SemiBold(작은 글). OFL 무료 → assets/fonts 에 둔다. 손글씨·노란색 폐기.
  - 두꺼운 외곽선 대신 부드러운 그림자(또는 반투명 바). 포인트 색은 [대괄호] 한 단어에만.
  - 최대 2줄, 줄당 11자 안, 글자 72~80px, 화면 높이 58% 자리(플랫폼 UI·엄지 영역 회피). 한 줄 강제로 글자를 줄이는 짓 금지.
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

STYLES = {
    "shadow": {"ko": "그림자형", "accent": (94, 234, 212), "desc": "흰 글자 + 부드러운 그림자, 외곽선 없음 (기본)"},
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
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        for k, ln in enumerate(lines):
            _draw_segs(ds, (W - widths[k]) / 2, y0 + k * lh + 8, ln, f, (0, 0, 0, 190), (0, 0, 0, 190))
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        im.alpha_composite(sh)
        d = ImageDraw.Draw(im)
        for k, ln in enumerate(lines):
            _draw_segs(d, (W - widths[k]) / 2, y0 + k * lh, ln, f, (255, 255, 255, 255), accent, stroke=2, stroke_fill=(0, 0, 0, 90))
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
    x = 44
    d.rounded_rectangle([x, y, x + tw + 44, y + f.size + 24], 999, fill=(0, 0, 0, 135))
    d.text((x + 22, y + 11), text, font=f, fill=(255, 255, 255, 235))
    return im


def draw_chip(im: Image.Image, text: str, sub: str = "", y: int = 118):
    """오른쪽 위 작은 칩 — '최근 30일 후기 719건' (1~2초만 보인다)."""
    d = ImageDraw.Draw(im)
    f = font(34, bold=False); f2 = font(22, bold=False)
    tw = max(d.textlength(text, font=f), d.textlength(sub, font=f2) if sub else 0)
    x2 = W - 44
    hgt = f.size + 22 + (f2.size + 6 if sub else 0)
    d.rounded_rectangle([x2 - tw - 40, y, x2, y + hgt], 20, fill=(255, 255, 255, 232))
    d.text((x2 - tw - 20, y + 10), text, font=f, fill=(20, 22, 30, 255))
    if sub:
        d.text((x2 - tw - 20, y + f.size + 14), sub, font=f2, fill=(90, 94, 104, 255))
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
        draw_caption(im, text, style, size=92 if hook else 76, cy=0.52 if hook else CY, sub=sub)
    if pill:
        draw_pill(im, pill)
    if disclosure:
        draw_disclosure(im, disclosure)
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


def end_card(out: Path, bg: Path | None, folder: str, pos: int, style: str = DEFAULT_STYLE, disclosure: str = "", label: str = "객실 타입 · 가격대 · 링크는"):
    """끝 카드: 대표 사진 블러 배경 + '프로필 링크 → 폴더 N번'. 숙소 이름은 쓰지 않는다 (영상 비공개·텍스트 공개 결정)."""
    st = STYLES.get(style) or STYLES[DEFAULT_STYLE]
    accent = (*st["accent"], 255)
    if bg and Path(bg).exists():
        base = cover(Image.open(bg).convert("RGB")).filter(ImageFilter.GaussianBlur(26))
        base = Image.blend(base, Image.new("RGB", (W, H), (8, 10, 16)), 0.55)
    else:
        base = Image.new("RGB", (W, H), (14, 16, 24))
    im = base.convert("RGBA")
    d = ImageDraw.Draw(im)
    f1 = font(46, bold=False)
    tw = d.textlength(label, font=f1)
    d.text(((W - tw) / 2, 640), label, font=f1, fill=(255, 255, 255, 220))
    f2 = font(68)
    t2 = "프로필 링크"
    tw = d.textlength(t2, font=f2)
    d.text(((W - tw) / 2, 720), t2, font=f2, fill=(255, 255, 255, 255))
    # 화살표(아래) — 벡터로 그린다 (이모지 금지)
    cx, ay = W / 2, 830
    d.line([(cx, ay), (cx, ay + 70)], fill=(255, 255, 255, 230), width=8)
    d.polygon([(cx - 26, ay + 56), (cx + 26, ay + 56), (cx, ay + 92)], fill=(255, 255, 255, 230))
    f3, lines = fit_font(d, folder, 84, W - 200, min_size=60)
    y = 960
    for ln in lines:
        lw = _width(d, ln, f3)
        _draw_segs(d, (W - lw) / 2, y, ln, f3, accent, accent)
        y += int(f3.size * 1.2)
    t4 = f"{pos}번째 숙소"
    f4 = font(60)
    tw = d.textlength(t4, font=f4)
    pad = 26
    d.rounded_rectangle([(W - tw) / 2 - pad, y + 18, (W + tw) / 2 + pad, y + 18 + f4.size + 28], 999, fill=(255, 255, 255, 235))
    d.text(((W - tw) / 2, y + 32), t4, font=f4, fill=(20, 22, 30, 255))
    if disclosure:
        draw_disclosure(im, disclosure, y=1560, size=30)
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
        draw_caption(ov, caption, key, sub="아쉬움: 주말엔 붐빈다는 후기" if key == "bar" else "")
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
    draw_caption(ov, "추운데 애들 [어디] 데려가지?", "shadow", size=92, cy=0.52)
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
