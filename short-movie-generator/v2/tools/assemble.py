"""v2 완성본 조립 — [후킹 2초] + 본편 컷(나레이션 + 카라오케 자막 + 빨간 주석 + 「再現映像」 + 특징 줌인 인서트) + [정답 카드].

규칙(CLAUDE.md v2): 영상은 정상 속도(컷 길이 = 나레이션 + 여유, 짝수 초) · 영상 AI 오디오는 전부 버림(음악 금지) ·
나레이션 -16 LUFS · 자막은 v1과 같은 카라오케식 하단(karaoke.py) · 주석은 강조색 빨강 하나 · 「再現映像」 표기.
★후킹·정답 카드(운영자 확정 2026-09-30): script.json 에 `hook`이 있으면 공용 엔딩 대신
  ① 맨 앞 — 본편의 가장 놀라운 2초를 그대로 발췌(새로 만들지 않음 · 비용 0) + 빨간 질문 글자만(자막·나레이션 없음)
  ② 맨 뒤 — 「正解：〇〇」 + 종명·학명 + 작은 구독 배지 카드 2초. 공용 댓글 유도 엔딩(약 10초)은 붙이지 않는다.

사용: python assemble.py <pilot 폴더> <클립 요청 id> <나레이션 요청 id> <엔딩 mp4 또는 ''> <출력 mp4>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import karaoke  # noqa: E402

W, H, FPS = 720, 1280, 24
ROOT = Path(__file__).resolve().parents[2]
FONT_BOLD = ROOT / "vendor" / "fonts" / "NotoSansJP-VF.ttf"
RED = (220, 38, 38)
EDGE = 12                      # 좌우 가장자리 여유 크롭(px)
HOOK_S = 2.0                   # 후킹 발췌 길이(초)
ANSWER_S = 2.0                 # 정답 카드 길이(초)
TAIL_S = 0.6                   # ★컷은 나레이션 끝 + 0.6초에서 자른다(운영자 확정 2026-09-30 · 핵심 규칙: 무음 구간 최소화)
FADE_S = 0.6                   # 마지막 컷 끝 어둠으로 페이드(자르면서 사라지는 퇴장 연출 보전)
NAVY = (8, 18, 30)

# 특징 줌인 인서트: 컷 번호 → (인서트 이미지, 시작 초, 빨간 원 중심 x,y(0~1), 반지름(0~1))
# ★시범편(대왕구족충) 전용 값 — 그 파일이 있는 편에만 적용한다(실사고 2026-09-30: 머리없는닭괴물 편 조립이 없는 파일로
#   ffmpeg 실패 → 영상 8컷($6.2)을 만들어 놓고 완성본이 안 나옴). 새 편은 script.json 컷의 "insert" 항목으로 지정한다.
INSERTS = {4: ("out/19_eye_macro/eye_macro.jpg", 5.0, (0.40, 0.50), 0.36)}


def insert_for(pilot: Path, n: int, cut: dict | None) -> tuple | None:
    """이 컷의 확대 인서트(없으면 None): script.json 컷의 insert{file,at,cx,cy,r} 우선, 없으면 시범편 상수(파일이 있을 때만)."""
    ins = (cut or {}).get("insert")
    if ins and (pilot / ins["file"]).exists():
        return (ins["file"], float(ins.get("at", 0)), (float(ins.get("cx", 0.5)), float(ins.get("cy", 0.5))), float(ins.get("r", 0.3)))
    if n in INSERTS and (pilot / INSERTS[n][0]).exists():
        return INSERTS[n]
    return None


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _dur(p) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(p)], capture_output=True, text=True, check=True).stdout.strip())


def _font(size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_BOLD), size)
    f.set_variation_by_name("Bold")
    return f


class GlyphError(RuntimeError):
    """화면 글자에 글꼴에 없는 문자가 있다(그대로 그리면 네모 □) — 영상을 만들지 않고 멈춘다."""


_CMAP: set | None = None


def missing_glyphs(text: str) -> list[str]:
    """FONT_BOLD 에 없는 글자 목록(공백 제외). 예: 한글은 NotoSansJP 에 없다 → 네모로 깨짐."""
    global _CMAP
    if _CMAP is None:
        try:
            from fontTools.ttLib import TTFont
            _CMAP = set(TTFont(str(FONT_BOLD)).getBestCmap())
        except ImportError:                                  # 실사고 2026-10-06: 서버에 fontTools 가 없어 조립 실패 → Pillow 로 대체 판정
            _CMAP = False
    if _CMAP is False:
        f = ImageFont.truetype(str(FONT_BOLD), 40)
        tofu = bytes(f.getmask("\U0010FFFF"))               # 글꼴에 없는 글자는 이 빈 상자(.notdef)와 똑같이 그려진다
        return sorted({ch for ch in text if not ch.isspace() and bytes(f.getmask(ch)) == tofu})
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in _CMAP})


def check_glyphs(text: str, where: str) -> None:
    """★화면에 그릴 글자 자가 검사(실사고 2026-10-05: 왕게 편 빨간 주석이 한국어로 들어가 네모 □로 깨짐)."""
    bad = missing_glyphs(text)
    if bad:
        raise GlyphError(f"{where}「{text}」에 글꼴에 없는 글자 {''.join(bad)} — 일본어로 고쳐야 합니다(한국어 금지)")


PAPER = (246, 236, 214)        # 미니어처 종이 꼬리표(크림 종이)
INK = (58, 40, 28)             # 갈색 잉크 글씨
TAG_RED = (178, 42, 36)        # 테두리·밑줄(빨간 주석 → 미니어처 소품 톤의 붉은 잉크)
TAPE = (232, 214, 160)         # 마스킹 테이프


def label_png(text: str, out: Path) -> Path:
    """화면 주석(위쪽 1/3 — 하단 자막과 겹치지 않게) — 미니어처 세트에 붙인 **종이 꼬리표** 모양
    (운영자 지시 2026-10-05: 빨간 칩이 디오라마와 안 어울림). 크림 종이 + 붉은 잉크 이중 테두리 + 갈색 글씨 +
    마스킹 테이프 + 살짝 기울임 + 그림자. 글꼴에 없는 글자(한국어 등)는 그리기 전에 멈춘다."""
    check_glyphs(text, "주석")
    f = _fit_font(text, 42, W - 200)
    tw = f.getlength(text)
    a, d = f.getmetrics()
    pw, ph = int(tw) + 72, a + d + 44
    tag = Image.new("RGBA", (pw + 40, ph + 60), (0, 0, 0, 0))
    ox, oy = 20, 30
    sh = Image.new("RGBA", tag.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([ox + 5, oy + 8, ox + pw + 5, oy + ph + 8], radius=6, fill=(0, 0, 0, 120))
    from PIL import ImageFilter
    tag.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))
    dr = ImageDraw.Draw(tag)
    dr.rounded_rectangle([ox, oy, ox + pw, oy + ph], radius=6, fill=PAPER + (255,))
    # 종이 결(아주 옅은 가로 줄) — 인쇄물이 아니라 손으로 만든 종이 느낌
    for yy in range(oy + 6, oy + ph - 4, 7):
        dr.line([(ox + 6, yy), (ox + pw - 6, yy)], fill=(222, 206, 174, 38), width=1)
    dr.rounded_rectangle([ox + 7, oy + 7, ox + pw - 7, oy + ph - 7], radius=4, outline=TAG_RED + (230,), width=3)
    dr.rounded_rectangle([ox + 12, oy + 12, ox + pw - 12, oy + ph - 12], radius=3, outline=TAG_RED + (120,), width=1)
    dr.text((ox + 36, oy + 22), text, font=f, fill=INK + (255,))
    # 마스킹 테이프(왼쪽 위 비스듬히)
    tp = Image.new("RGBA", (110, 34), TAPE + (225,))
    td = ImageDraw.Draw(tp)
    for x in range(0, 110, 9):
        td.line([(x, 0), (x, 2)], fill=(0, 0, 0, 0), width=4)
        td.line([(x + 4, 32), (x + 4, 34)], fill=(0, 0, 0, 0), width=4)
    tp = tp.rotate(28, expand=True, resample=Image.BICUBIC)
    tag.alpha_composite(tp, (ox - 26, oy - 22))
    tag = tag.rotate(2.5, expand=True, resample=Image.BICUBIC)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    im.alpha_composite(tag, (max(0, int((W - tag.width) / 2)), int(H * 0.27)))
    im.save(out)
    return out


def repro_png(out: Path) -> Path:
    """「再現映像」 — 왼쪽 위 작게(실사로 오인하지 않게 · 운영자 확정)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = _font(24)
    ImageDraw.Draw(im).text((26, 26), "再現映像", font=f, fill=(255, 255, 255, 190),
                            stroke_width=2, stroke_fill=(0, 0, 0, 150))
    im.save(out)
    return out


def circle_png(cx: float, cy: float, r: float, out: Path) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    R = int(r * W)
    ImageDraw.Draw(im).ellipse([int(cx * W) - R, int(cy * H) - R, int(cx * W) + R, int(cy * H) + R],
                               outline=RED + (255,), width=8)
    im.save(out)
    return out


def _fit_font(text: str, size: int, max_w: int) -> ImageFont.FreeTypeFont:
    while size > 24:
        f = _font(size)
        if f.getlength(text) <= max_w:
            return f
        size -= 2
    return _font(size)


def _wrap_lines(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """「、」에서 먼저 나누고(쉼표는 화면에 안 찍음), 그래도 넘치는 덩어리는 **글자 수를 고르게** 나눈다
    (앞줄만 꽉 채우고 뒷줄에 한두 글자가 남는 모양 방지)."""
    import math
    out = []
    for part in [x.strip() for x in text.split("、") if x.strip()]:
        n = len(part)
        k = 1
        while k < 4 and max(f.getlength(part[i * math.ceil(n / k):(i + 1) * math.ceil(n / k)]) for i in range(k)) > max_w:
            k += 1
        step = math.ceil(n / k)
        out += [part[i * step:(i + 1) * step] for i in range(k) if part[i * step:(i + 1) * step]]
    return out


HOOK_FONT = 128                # 후킹 글자 크기(운영자 지시 2026-09-30: 예전 64 → 2배 · 화면을 크게 덮게)


HOOK_TOP = 0.12                # 새 후킹 글자 위치(화면 위쪽 · 유튜브 위쪽 버튼 아래 · 생물을 가리지 않게)
KEY_RED = (232, 28, 28)


def hook_png(question: str, out: Path, key: str | None = None) -> Path:
    """후킹 글자. key=None 이면 옛 편 디자인(2026-09-30: 가운데 위쪽 빨간 글자 2~3줄).
    ★key 가 있으면(후킹 개편 2026-10-09 · 운영자 선택) **흰 글자 + 검은 테두리, 핵심 단어(key)만 빨강 + 흰 테두리** ·
    화면 위쪽(HOOK_TOP) · 「、」 자리에서만 줄바꿈(단어 중간 금지 · 최대 2줄) · 줄이 넘치면 글자 크기만 줄인다."""
    if key is not None:
        return _hook_png_line(question, out, key)
    check_glyphs(question, "후킹 질문")
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    size, max_w = HOOK_FONT, W - 60
    while True:
        f = _font(size)
        lines = _wrap_lines(question, f, max_w)
        if (len(lines) <= 3 and all(f.getlength(x) <= max_w for x in lines)) or size <= 72:
            break
        size -= 4
    a, d = f.getmetrics()
    lh = int((a + d) * 1.05)
    y = int(H * 0.38 - lh * len(lines) / 2)
    # 운영자 선택(2026-09-30 비교 시안 'NOW'): 빨간 글자 + 흰 테두리 + 부드러운 검은 그림자
    from PIL import ImageFilter
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    yy = y
    for ln in lines:
        sd.text((int((W - f.getlength(ln)) / 2) + 6, yy + 8), ln, font=f, fill=(0, 0, 0, 170), stroke_width=10, stroke_fill=(0, 0, 0, 170))
        yy += lh
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    dr = ImageDraw.Draw(im)
    for ln in lines:
        dr.text((int((W - f.getlength(ln)) / 2), y), ln, font=f, fill=(225, 32, 32, 255), stroke_width=7, stroke_fill=(255, 255, 255, 255))
        y += lh
    im.save(out)
    return out


def _hook_png_line(text: str, out: Path, key: str) -> Path:
    from PIL import ImageFilter
    check_glyphs(text, "후킹 문장")
    lines = [p.strip() for p in text.replace(",", "、").split("、") if p.strip()] or [text]
    size, max_w = HOOK_FONT, W - 70
    while size > 64 and max(_font(size).getlength(x) for x in lines) > max_w:
        size -= 4
    f = _font(size)
    lh = int(size * 1.22)                       # 줄 간격을 좁게(글꼴 기본 줄높이는 1.45배라 글자 덩어리가 화면 가운데까지 내려옴)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    y = int(H * HOOK_TOP)
    for ln in lines:
        sd.text((int((W - f.getlength(ln)) / 2) + 5, y + 7), ln, font=f, fill=(0, 0, 0, 170), stroke_width=12, stroke_fill=(0, 0, 0, 170))
        y += lh
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)))
    dr = ImageDraw.Draw(im)
    y = int(H * HOOK_TOP)
    for ln in lines:
        x = (W - f.getlength(ln)) / 2
        j = ln.find(key) if key else -1
        parts = [(ln, False)] if j < 0 else [(ln[:j], False), (key, True), (ln[j + len(key):], False)]
        for seg, red in parts:
            if not seg:
                continue
            dr.text((int(x), y), seg, font=f, fill=(KEY_RED if red else (255, 255, 255)) + (255,), stroke_width=8,
                    stroke_fill=(255, 255, 255, 255) if red else (0, 0, 0, 255))
            x += f.getlength(seg)
        y += lh
    im.save(out)
    return out


def _italic(im: Image.Image) -> Image.Image:
    """학명은 이탤릭(하드룰) — 이탤릭 글꼴이 없어 글자 그림을 살짝 기울인다."""
    w, h = im.size
    k = 0.2
    return im.transform((w + int(h * k), h), Image.AFFINE, (1, k, -int(h * k), 0, 1, 0), resample=Image.BICUBIC)


def answer_png(question: str, answer: str, sci: str, out: Path, bg: Path | None = None, portrait: Path | None = None,
               name: str = "", label: str = "正解") -> Path:
    """정답 카드(운영자 지시 2026-09-30 디자인 개선): 본편 마지막 화면을 어둡게·흐리게 깐 배경 위에
    작은 빨간 「正解」 라벨 → 큰 흰 이름 → 학명(이탤릭) → 가는 선 → 「チャンネル登録」 배지. 질문은 위쪽에 작게.
    name: 사실 질문 편(정답이 이름이 아님)일 때 정답 아래에 생물 이름을 한 줄 더(운영자 선택 2026-10-09 D)."""
    from PIL import ImageFilter
    check_glyphs(question + answer + sci + name + label, "정답 카드")
    if bg and Path(bg).exists():
        im = Image.open(bg).convert("RGB").resize((W, H)).filter(ImageFilter.GaussianBlur(10))
        im = Image.blend(im, Image.new("RGB", (W, H), NAVY), 0.62).convert("RGBA")
    else:
        im = Image.new("RGBA", (W, H), NAVY + (255,))
    # 가운데를 살짝 밝히는 비네트(위아래는 더 어둡게)
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.3, H * 0.15, W * 1.3, H * 0.85], fill=90)
    vig = vig.filter(ImageFilter.GaussianBlur(120))
    im.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (W, H), (40, 70, 95)).split(), vig)))
    dr = ImageDraw.Draw(im)
    # 생물 카드 초상(둥근 창 · 얇은 흰 테) — 있으면 위에 크게
    top = int(H * 0.20)
    if portrait and Path(portrait).exists():
        R_ = 150
        pim = Image.open(portrait).convert("RGB")
        side = min(pim.size)
        pim = pim.crop(((pim.width - side) // 2, (pim.height - side) // 2, (pim.width + side) // 2, (pim.height + side) // 2)).resize((2 * R_, 2 * R_))
        mask = Image.new("L", (2 * R_, 2 * R_), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 2 * R_ - 1, 2 * R_ - 1], fill=255)
        cx, cy = W // 2, top + R_
        dr.ellipse([cx - R_ - 5, cy - R_ - 5, cx + R_ + 5, cy + R_ + 5], fill=(255, 255, 255, 235))
        im.paste(pim, (cx - R_, cy - R_), mask)
        dr = ImageDraw.Draw(im)
        top = cy + R_ + 40
    else:
        top = int(H * 0.30)
    # 질문(작게)
    if question:
        f = _fit_font(question, 32, W - 120)
        dr.text((int((W - f.getlength(question)) / 2), top), question, font=f, fill=(170, 185, 200, 255))
        top += 60
    # 「正解」 빨간 라벨(후킹 개편 편은 이름 공개라 「この生き物は」)
    lab = label or "正解"
    f = _font(30)
    tw = f.getlength(lab)
    a, d = f.getmetrics()
    x0, y0 = int((W - tw) / 2) - 18, top
    dr.rounded_rectangle([x0, y0, x0 + tw + 36, y0 + a + d + 10], radius=8, fill=RED + (255,))
    dr.text((x0 + 18, y0 + 5), lab, font=f, fill=(255, 255, 255, 255))
    # 이름(크게 · 흰색 · 부드러운 그림자)
    y = y0 + a + d + 34
    f = _fit_font(answer, 84, W - 80)
    tw = f.getlength(answer)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((int((W - tw) / 2) + 4, y + 6), answer, font=f, fill=(0, 0, 0, 160))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    dr = ImageDraw.Draw(im)
    dr.text((int((W - tw) / 2), y), answer, font=f, fill=(255, 255, 255, 255))
    a2, d2 = f.getmetrics()
    y += a2 + d2 + 18
    if name and name != answer:
        f = _fit_font(name, 44, W - 120)
        dr.text((int((W - f.getlength(name)) / 2), y), name, font=f, fill=(235, 238, 245, 255))
        a3, d3 = f.getmetrics()
        y += a3 + d3 + 10
    if sci:
        sci = sci[:1].upper() + sci[1:]
        f = _fit_font(sci, 34, W - 160)
        tw = int(f.getlength(sci))
        a, d = f.getmetrics()
        lay = Image.new("RGBA", (tw + 20, a + d + 10), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text((10, 5), sci, font=f, fill=(205, 215, 230, 255))
        lay = _italic(lay)
        im.alpha_composite(lay, (int((W - lay.width) / 2), y))
        y += a + d + 40
    dr = ImageDraw.Draw(im)
    dr.line([(W // 2 - 60, y), (W // 2 + 60, y)], fill=(200, 60, 60, 220), width=3)
    # 연재감 한 줄(운영자 선택 2026-10-05 — 회차 번호는 금지라 '다음 수수께끼'를 약속하는 문장으로)
    series = "次の深海の謎も、このチャンネルで。"
    f = _fit_font(series, 30, W - 120)
    dr.text((int((W - f.getlength(series)) / 2), int(H * 0.78) - 64), series, font=f, fill=(225, 230, 240, 255))
    # 구독 배지(흰 알약 + 빨간 점)
    pill = "チャンネル登録"
    f = _font(30)
    tw = f.getlength(pill)
    a, d = f.getmetrics()
    x0, y0 = int((W - tw - 24) / 2) - 26, int(H * 0.78)
    dr.rounded_rectangle([x0, y0, x0 + tw + 76, y0 + a + d + 22], radius=30, fill=(255, 255, 255, 240))
    dr.ellipse([x0 + 22, y0 + (a + d + 22) // 2 - 8, x0 + 38, y0 + (a + d + 22) // 2 + 8], fill=RED + (255,))
    dr.text((x0 + 52, y0 + 11), pill, font=f, fill=NAVY + (255,))
    im.save(out)
    return out


def _portrait(pilot: Path) -> Path | None:
    """정답 카드 초상 = 생물 카드(creature_card.json use_as_reference 첫 장 · 없으면 None)."""
    try:
        cc = json.loads((pilot / "creature_card.json").read_text(encoding="utf-8"))
        for r in cc.get("use_as_reference", []):
            p = pilot / r["file"]
            if p.exists() and "ref_" not in p.name:
                return p
    except Exception:  # noqa: BLE001
        pass
    return None


def _silent_video(src_v: Path, out: Path, sec: float, fade_in: float = 0.0) -> Path:
    """무음(스테레오 48k) 트랙을 붙인 mp4 — 본편과 concat 할 수 있는 같은 규격."""
    vf = f"fps={FPS},setsar=1" + (f",fade=t=in:st=0:d={fade_in}" if fade_in else "")
    _run(["-i", str(src_v), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-shortest",
          "-t", f"{sec}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
          "-ar", "48000", str(out)])
    return out


# ★후킹 2초 자동 선택(운영자 선택 2026-10-09 · 실사고: 왕게 편 — 대본 단계에서 영상도 없이 「컷 한가운데 2초」를
#   정해 두었더니 거의 멈춘 장면이 맨 앞에 나가 81%가 바로 넘김). 이제 완성된 클립에서 실제로 가장 많이 움직이는 2초를 잰다.
#   움직임 = 회색 90×160 · 초당 8장 · 앞뒤 장면의 평균 밝기 차이(장면이 확 바뀌는 한 장은 뺌) — 실패 분석 때 쓴 것과 같은 계산.
MOTION_FPS = 8
HOOK_MIN_MOTION = 3.0          # 맨 앞 2초 움직임 하한(실측: 왕게 1.0 → 81% 즉시 이탈 · 대왕구족충 3.8 · 유령해삼 6.9)
FRONT_S = 15.0                 # 「앞 15초」 움직임 측정 구간(왕게 1.4 · 대왕구족충 7.4 · 유령해삼 2.5)
FRONT_MIN_MOTION = 2.0


def motion_series(mp4: Path, fps: int = MOTION_FPS, dur: float | None = None) -> list[float | None]:
    """프레임 사이 움직임 목록(i번 = i/fps초 → (i+1)/fps초). 컷 전환처럼 한 장만 확 튀는 값은 None(움직임에서 뺀다)."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), *(["-t", f"{dur}"] if dur else []),
                          "-vf", f"fps={fps},scale=90:160,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8)
    if fr.size < 2 * 90 * 160:
        return []
    fr = fr[:fr.size // (90 * 160) * 90 * 160].reshape(-1, 160, 90).astype(float)
    d = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    out: list[float | None] = []
    for i, v in enumerate(d):
        nb = [d[j] for j in (i - 1, i + 1) if 0 <= j < len(d)]
        out.append(None if v > 10 and nb and max(nb) < 0.45 * v else round(float(v), 3))
    return out


def window_motion(series: list[float | None], at: float, sec: float = HOOK_S, fps: int = MOTION_FPS) -> float:
    """at초부터 sec초 동안의 평균 움직임(뺀 값 제외)."""
    i0 = int(round(at * fps))
    vals = [v for v in series[i0:i0 + int(round(sec * fps))] if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def best_hook_window(series: list[float | None], usable_s: float, sec: float = HOOK_S, fps: int = MOTION_FPS) -> tuple[float, float]:
    """클립 앞 usable_s초 안에서 평균 움직임이 가장 큰 sec초 구간의 (시작 초, 움직임). 같으면 앞쪽."""
    best = (0.0, window_motion(series, 0.0, sec, fps))
    last = int(round(max(0.0, usable_s - sec) * fps))
    for i in range(1, last + 1):
        m = window_motion(series, i / fps, sec, fps)
        if m > best[1]:
            best = (round(i / fps, 2), m)
    return best


def pick_hook(clip: Path, hook: dict, clip_s: float, sec: float = HOOK_S) -> dict:
    """후킹 발췌 구간(길이 sec): 운영자가 시작 초를 직접 정했거나(at_by=operator) 시험 릴스 구간이면(at_by=trial) 그대로,
    아니면 가장 많이 움직이는 구간을 자동 선택."""
    hmax = max(0.0, clip_s - sec)
    series = motion_series(clip, dur=clip_s or None)
    if hook.get("at_by") in ("operator", "trial") and hook.get("at") is not None:   # trial = 시험 릴스에서 이긴(또는 겨루는) 구간 그대로
        at = round(max(0.0, min(float(hook["at"]), hmax)), 2)
        return {"at": at, "motion": window_motion(series, at, sec), "by": hook["at_by"]}
    at, m = best_hook_window(series, clip_s, sec)
    return {"at": round(min(at, hmax), 2), "motion": m, "by": "auto"}


# ★0초부터 목소리(후킹 개편 2026-10-09): 목소리가 길면 후킹을 최대 3초까지 늘린다(말이 잘리지 않게)
HOOK_MAX_S = 3.0
VOICE_LEAD_S = 0.1


def hook_seconds(voice: Path | None) -> float:
    if not voice:
        return HOOK_S
    return round(min(HOOK_MAX_S, max(HOOK_S, VOICE_LEAD_S + _dur(voice) + 0.3)), 2)


def _loudnorm_2pass(src: Path, dst: Path) -> Path:
    """짧은 목소리를 -16 LUFS 로 정확히 맞춘다(2번 재기 · 선형). 한 번에 하면 짧은 소리는 1~2LU 크게 나온다(실측 -14.9)."""
    er = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                         "-f", "null", "-"], capture_output=True, text=True).stderr
    try:
        m = json.loads(er[er.rindex("{"):er.rindex("}") + 1])
        af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
              f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    except (ValueError, KeyError):
        af = "loudnorm=I=-16:TP=-1.5:LRA=11"
    _run(["-i", str(src), "-af", af + ",aresample=48000", "-ac", "1", str(dst)])
    return dst


def _voiced_video(src_v: Path, voice: Path, out: Path, sec: float) -> Path:
    """후킹 목소리를 0.1초부터 깐 mp4(-16 LUFS · 스테레오 48k) — 본편과 concat 할 수 있는 같은 규격."""
    vn = _loudnorm_2pass(voice, out.with_name("hook_voice_norm.wav"))
    _run(["-i", str(src_v), "-i", str(vn), "-filter_complex",
          f"[0:v]fps={FPS},setsar=1[v];[1:a]aresample=48000,adelay={int(VOICE_LEAD_S * 1000)}:all=1,"
          f"apad=whole_dur={sec},atrim=0:{sec},asetpts=PTS-STARTPTS[a]",
          "-map", "[v]", "-map", "[a]", "-t", f"{sec}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(out)])
    return out


def build_hook(clip: Path, at: float, question: str, t: Path, key: str | None = None, voice: Path | None = None,
               sec: float = HOOK_S) -> Path:
    """후킹: 본편 컷(clip)의 at초부터 sec초를 그대로 발췌 + 글자.
    옛 편(key=None): 빨간 질문 0.2초부터 · 무음.  ★개편 편: 흰 글자+빨간 핵심 단어 0초부터 + 목소리(voice) 0.1초부터."""
    ex = t / "hook_ex.mp4"
    _run(["-ss", f"{at:.2f}", "-i", str(clip), "-vf",
          f"scale={W + 2 * EDGE}:{(H + 2 * EDGE * H // W) // 2 * 2}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={sec}", "-t", f"{sec}", "-an", "-c:v", "libx264", "-crf", "16",
          "-pix_fmt", "yuv420p", str(ex)])
    lab = hook_png(question, t / "hook_q.png", key=key)
    ov = t / "hook_v.mp4"
    start = "0" if key is not None else "0.2"
    _run(["-i", str(ex), "-i", str(lab), "-filter_complex", f"[0:v][1:v]overlay=0:0:enable='gte(t,{start})'[v]",
          "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(ov)])
    if voice:
        return _voiced_video(ov, voice, t / "hook.mp4", sec)
    return _silent_video(ov, t / "hook.mp4", sec)


def build_answer(question: str, answer: str, sci: str, t: Path, bg: Path | None = None, portrait: Path | None = None,
                 name: str = "", label: str = "正解") -> Path:
    png = answer_png(question, answer, sci, t / "answer.png", bg=bg, portrait=portrait, name=name, label=label)
    raw = t / "answer_raw.mp4"
    _run(["-loop", "1", "-i", str(png), "-t", f"{ANSWER_S}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(raw)])
    return _silent_video(raw, t / "answer.mp4", ANSWER_S, fade_in=0.4)


def _place_slices(src: Path, slices: list[tuple], total: float, out: Path) -> None:
    """src(모노 wav)에서 (from, to) 구간을 잘라 at 초에 놓은 total 초짜리 스테레오 wav."""
    import wave

    import numpy as np
    with wave.open(str(src), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, ch)[:, 0]
    outbuf = np.zeros(int(total * sr), dtype=np.int32)
    for a, b, at in slices:
        seg = data[int(a * sr):int(b * sr)].astype(np.int32)
        o = int(at * sr)
        seg = seg[:max(0, len(outbuf) - o)]
        outbuf[o:o + len(seg)] += seg
    outbuf = np.clip(outbuf, -32768, 32767).astype(np.int16)
    stereo = np.repeat(outbuf[:, None], 2, axis=1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def build_cut(pilot: Path, clip: Path, sec: float, n: int, ann: str | None, t: Path, cut: dict | None = None,
              fade_out: bool = False) -> Path:
    """한 컷: 9:16 맞춤 · 무음 · 길이 맞춤(sec = 실제로 쓰는 길이 · 짧으면 마지막 장면 유지) · 인서트·주석 · (마지막 컷) 페이드아웃."""
    base = t / f"cut{n}_base.mp4"
    # ★좌우 가장자리 12px씩 여유 크롭(약 3% 확대) — 시작 이미지의 흰 격자 테두리가 영상 첫머리에
    #   흰 선으로 남는 사고 방지(실측 최대 9px). 모든 컷에 같게 적용해 컷끼리 크기 차이가 없다.
    _run(["-i", str(clip), "-vf", f"scale={W + 2 * EDGE}:{(H + 2 * EDGE * H // W) // 2 * 2}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},setsar=1,fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={sec}" + (f",fade=t=out:st={max(0.0, sec - FADE_S):.2f}:d={FADE_S}" if fade_out else ""),
          "-t", f"{sec}", "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(base)])
    cur = base
    ins = insert_for(pilot, n, cut)
    if ins and sec > ins[1] + 0.5:                     # 특징 줌인 — 매크로 인서트(천천히 확대) + 빨간 원(잘린 길이 안에 들어갈 때만)
        img, at, (cx, cy), r = ins
        ins = t / f"cut{n}_ins.mp4"
        frames = int((sec - at) * FPS)
        _run(["-loop", "1", "-i", str(pilot / img), "-vf",
              f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='min(zoom+0.0012,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1",
              "-frames:v", str(frames), "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(ins)])
        circ = circle_png(cx, cy, r, t / f"cut{n}_circ.png")
        joined = t / f"cut{n}_join.mp4"
        _run(["-i", str(cur), "-i", str(ins), "-i", str(circ), "-filter_complex",
              f"[0:v]trim=0:{at},setpts=PTS-STARTPTS[a];[1:v][2:v]overlay=0:0:enable='gte(t,0.4)'[b];"
              "[a][b]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
              str(joined)])
        cur = joined
    if ann:
        lab = label_png(ann, t / f"cut{n}_lab.png")
        out = t / f"cut{n}_ann.mp4"
        _run(["-i", str(cur), "-i", str(lab), "-filter_complex", "[0:v][1:v]overlay=0:0:enable='gte(t,0.6)'[v]",
              "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)])
        cur = out
    return cur


def main(pilot: str, clips_id: str, tts_id: str, ending: str, dst: str, overrides: dict | None = None,
         hook_override: dict | None = None) -> dict:
    """overrides: {컷번호: 클립 경로} — 관리자 페이지에서 그 컷만 다시 만든 경우 새 클립을 쓴다.
    ending: 예전 공용 엔딩 mp4(script.json 에 hook 이 없는 옛 편에만 쓰임 · '' 이면 안 붙임).
    hook_override: script.json 의 hook 대신 쓸 후킹(시험 릴스 B 버전 — 대본은 그대로 두고 맨 앞만 다르게 조립).
    반환: {"hook": {"cut", "at", "motion", "by"}} — 실제로 쓴 후킹 구간(후킹이 없는 옛 편은 빈 dict)."""
    info: dict = {}
    karaoke.verify_font()        # ★자막 글꼴 자가 검사 — 네모(□)·빈칸이면 여기서 멈춘다(영상을 만들지 않음)
    P = Path(pilot)
    sc = json.loads((P / "script.json").read_text(encoding="utf-8"))
    cuts = {c["cut"]: c for c in sc["cuts"] if "tts" in c}
    timing = sc["timing_v5"]
    wav = P / "out" / tts_id / "body.wav"
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        # ① 컷별 영상
        parts, starts, acc = [], [], 0.0
        last_n = timing[-1]["cut"]
        for tm in timing:
            n, sec = tm["cut"], float(tm["sec"])
            # ★핵심 규칙(운영자 확정 2026-09-30): 컷은 나레이션 끝 + 0.6초에서 자른다 — 영상은 짝수 초로 만들어도
            #   남는 무음 구간을 화면에 남기지 않는다(실사고: 편당 14초 무음). 마지막 컷은 끝을 어둠으로 페이드.
            use = round(min(sec, float(tm.get("lead", 0.15)) + float(tm.get("speech_s") or sec) + TAIL_S), 2)
            tm["use_sec"] = use
            clip = Path((overrides or {}).get(n) or P / "out" / clips_id / f"c{n:02d}.mp4")
            parts.append(build_cut(P, clip, use, n, cuts[n].get("annotation"), t, cuts[n], fade_out=(n == last_n)))
            starts.append(acc)
            acc += use
        body_len = acc
        (t / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
        _run(["-f", "concat", "-safe", "0", "-i", str(t / "list.txt"), "-c", "copy", str(t / "body_v.mp4")])
        # ② 나레이션: 전체를 한 번에 음량 맞춤(-16 LUFS) → 컷별로 잘라 컷 시작 + 리드에 배치
        _run(["-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-ac", "1",
              "-sample_fmt", "s16", str(t / "nar_norm.wav")])
        # ★조각 배치는 파이썬으로 샘플 단위로 정확히 놓는다 — ffmpeg atrim+adelay 조합은 지연이 무시돼 조각이
        #   맨 앞에 겹쳐 깔렸다(실측: 두 조각이 0초에 겹쳐 -8 LUFS로 과대).
        _place_slices(t / "nar_norm.wav", [(tm["audio_from"], tm["audio_to"], st + tm["lead"])
                                           for tm, st in zip(timing, starts)], body_len, t / "body_a0.wav")
        _run(["-i", str(t / "body_a0.wav"), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",
              "-t", f"{body_len}", str(t / "body_a.wav")])          # 스테레오 기준 -16 LUFS(엔딩과 같게)
        # ③ 카라오케 자막(v1 방식) — 컷별 발화 조각 시각 + 컷 시작
        disp = []
        for tm, st in zip(timing, starts):
            disp += karaoke.disp_from_timepoints(cuts[tm["cut"]]["jp"], tm["local_tps"], offset=st)
        karaoke.build_ass(disp, t / "body.ass")
        rep = repro_png(t / "repro.png")
        _run(["-i", str(t / "body_v.mp4"), "-i", str(rep), "-i", str(t / "body_a.wav"), "-filter_complex",
              f"[0:v][1:v]overlay=0:0,{karaoke.burn_filter(t / 'body.ass')}[v]", "-map", "[v]", "-map", "2:a",
              "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
              "-t", f"{body_len}", str(t / "body.mp4")])
        # ④ 앞뒤 연결 — 후킹(hook)이 있으면 [후킹 2초][본편][정답 카드 2초], 없으면 예전 공용 엔딩(주어진 경우만)
        hook = hook_override or sc.get("hook") or None
        segs = [t / "body.mp4"]
        if hook:
            n = int(hook["cut"])
            clip = Path((overrides or {}).get(n) or P / "out" / clips_id / f"c{n:02d}.mp4")
            line = hook.get("type") == "line"                # 후킹 개편(2026-10-09) 편: 흰 글자 한 줄 + 0초 목소리
            vf = hook.get("voice_file") if line else None
            voice = P / vf if vf and (P / vf).exists() else None
            hsec = hook_seconds(voice)
            pick = pick_hook(clip, hook, float(cuts[n].get("sec") or 0), sec=hsec)
            at = pick["at"]
            info["hook"] = {"cut": n, **pick, "len": hsec, "voice": bool(voice)}
            lastf = t / "last_frame.jpg"
            _run(["-sseof", "-0.3", "-i", str(t / "body_v.mp4"), "-frames:v", "1", "-q:v", "2", str(lastf)])
            segs = [build_hook(clip, at, hook["question_jp"], t, key=(hook.get("key_jp") or "") if line else None,
                               voice=voice, sec=hsec), t / "body.mp4",
                    build_answer(hook.get("question_jp", ""), hook["answer_jp"], sc.get("subject", {}).get("scientific_name", ""), t,
                                 bg=lastf if lastf.exists() else None, portrait=_portrait(P),
                                 name=sc.get("subject", {}).get("jp_name", "") if hook.get("type") == "fact" else "",
                                 label="この生き物は" if line else "正解")]
        elif ending:
            _run(["-i", ending, "-vf", f"scale={W}:{H},setsar=1,fps={FPS}",
                  "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:v", "libx264", "-crf", "18",
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(t / "end.mp4")])
            segs.append(t / "end.mp4")
        if len(segs) == 1:
            _run(["-i", str(segs[0]), "-c", "copy", dst])
            return info
        ins = [x for p in segs for x in ("-i", str(p))]
        fc = "".join(f"[{i}:v][{i}:a]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[v][a]"
        _run([*ins, "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
              "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", dst])
    return info


if __name__ == "__main__":
    main(*sys.argv[1:6])
