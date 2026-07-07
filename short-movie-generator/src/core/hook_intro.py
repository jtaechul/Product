"""hook_intro — 오프닝 훅 · 엔드카드 · 임팩트 사운드 · 홀드/전환 통합 시스템(모든 영상 공통).

왜 이 모듈이 존재하나:
- 오프닝 훅/엔드카드의 디자인·타이밍·사운드가 매 영상 임의로 바뀌어 지저분했다.
  이 모듈이 **확정 디자인을 코드로 고정**해, 모든 영상이 동일한 방식으로 자동 적용받게 한다.

확정 사양(사용자 컨펌):
- 오프닝 타이틀: 명조체(Noto Serif CJK, 붓 뉘앙스) 초대형(화면 ~1/3),
  좌상 시안 → 우하 마젠타 대각 그라데이션 + 네온 글로우. 영문 병기·반짝이 없음.
- 어절 팝인(확대→축소) + 착지 순간 화면 셰이크 + 딥 붐('쿵/쾅') 효과음.
- 훅 나레이션은 제목답게 더 느리게·저음·큰 볼륨으로 강조.
- 타이틀 완성 후 충분히 홀드 → 플래시 전환으로 본문 진입.
- 엔드카드: 명조 대형 그라데이션 국명 + 이탤릭 학명 + 시안 수심 + 특징문구('光る' 주변 파티클).
  상단 구독 캡슐·게이지 아이콘·반짝이 없음, 중앙 정렬. NOAA 출처 표기.

계약(요약):
- render_opening_frames(bg_path, onsets, spec, cfg, out_dir) -> [png,...]
- render_endcard(bg_path, spec, cfg, out_path) -> out_path
- generate_boom(out_path) -> out_path
- build_flash_png(out_path) -> out_path
모든 수치는 HookIntroConfig 한 곳에 모아 플레이 테스트로 조정한다.
"""
from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ─────────────────────────── 폰트 경로(시스템/벤더) ───────────────────────────
_VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "fonts"
FONT_SERIF = "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"      # 명조(붓 뉘앙스)
FONT_SANS_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_SANS_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_MONO = str(_VENDOR / "ShareTechMono.ttf")
FONT_SCI = "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"  # 학명 이탤릭


@dataclass
class SpeciesSpec:
    """영상별 종 정보(오프닝/엔드카드 공통 주입값)."""
    jp_name: str                       # 국명(일본어) 예: ユメナマコ
    sci_name: str                      # 학명 예: Enypniastes eximia (첫 글자 대문자·이탤릭)
    depth_min: int                     # 실제 서식 최소 수심(m)
    depth_max: int                     # 실제 서식 최대 수심(m)
    hook_line1: str                    # 오프닝 1행 예: 頭も、目も、
    hook_line2: str                    # 오프닝 2행 예: 骨もない。
    hook_pop_words: list[str]          # 팝인 어절(순서) 예: [頭も、, 目も、, 骨もない。]
    feature_line: str                  # 엔드카드 특징문구 예: 泳ぐ・光る・透ける、深海のナマコ
    feature_glow_word: str = "光る"     # 파티클을 붙일 단어


@dataclass
class HookIntroConfig:
    """확정 디자인·타이밍·사운드 상수(단일 출처)."""
    W: int = 720
    H: int = 1280
    FPS: int = 30
    # ── 타이밍(시스템) ──
    opening_seg_s: float = 4.8         # 오프닝 페이지 총 길이(팝+홀드)
    narr_start_s: float = 0.30         # 세그먼트 내 훅 나레이션 시작
    transition_s: float = 0.5          # 오프닝→본문 플래시 전환
    pop_grow_s: float = 0.16           # 어절 확대→축소 시간
    pop_fade_s: float = 0.12           # 어절 알파 인
    # ── 오프닝 타이틀 ──
    title_size: int = 98
    title_y1: int = 548
    title_y2: int = 672
    # 넘침 방지(자동 맞춤): 안전여백·최소 크기·2줄 유지 하한.
    # 확정 디자인(頭も、目も、= 588px @98px)은 safe(608px) 안 → 그대로 유지되고,
    # 더 긴 훅만 자동 축소되거나(≥min_2line) 어절당 1줄(3줄)로 전환된다.
    title_safe_x: int = 40             # 좌우 안전여백(셰이크 margin과 별도)
    title_min_size: int = 56           # 축소 하한
    title_min_2line: int = 76          # 2줄 유지 최소 크기(미만이면 3줄 전환)
    grad_cyan: tuple = (120, 225, 245)
    grad_magenta: tuple = (240, 95, 205)
    glow: tuple = (80, 175, 240)
    glow_r: int = 26
    # ── 셰이크 ──
    shake_margin: int = 16
    shake_amp: float = 13.0
    shake_decay_s: float = 0.05
    shake_dur_s: float = 0.18
    # ── 사운드(무료·결정론) ──
    boom_dur_s: float = 0.46
    hook_tts_rate: str = "-14%"
    hook_tts_pitch: str = "-6Hz"
    hook_tts_volume: str = "+35%"
    body_tts_rate: str = "-2%"
    # ── 오디오 믹스 레벨 ──
    mix_hook: float = 1.30
    mix_body: float = 1.00
    mix_boom: float = 1.00
    mix_bgm: float = 0.10
    limiter: float = 0.95
    # ── 엔드카드 ──
    endcard_dur_s: float = 5.2
    end_title_size: int = 112
    end_sci_size: int = 38
    end_depth_size: int = 54
    end_feature_size: int = 40
    end_cyan: tuple = (120, 220, 255)
    # 타자기(타이핑) 연출 — 글자별 등장 + 타자 사운드 동기
    type_start_s: float = 0.35          # 첫 줄 타이핑 시작(전환 뒤 여유)
    type_cps_title: float = 11.0        # 초당 글자수(타이틀)
    type_cps_body: float = 16.0         # 초당 글자수(학명·수심·특징)
    type_line_gap_s: float = 0.18       # 줄 사이 간격
    type_click_dur_s: float = 0.030     # 타자 클릭 길이


# ─────────────────────────── 폰트 로더 ───────────────────────────
def _serif(s: int): return ImageFont.truetype(FONT_SERIF, s, index=0)
def _sans_b(s: int): return ImageFont.truetype(FONT_SANS_B, s, index=0)
def _sans_r(s: int): return ImageFont.truetype(FONT_SANS_R, s, index=0)
def _mono(s: int): return ImageFont.truetype(FONT_MONO, s)
def _sci(s: int): return ImageFont.truetype(FONT_SCI, s)


def fonts_available() -> bool:
    """필수 폰트가 모두 있으면 True(없으면 렌더 스킵/테스트 스킵)."""
    return all(Path(p).exists() for p in (FONT_SERIF, FONT_SANS_R, FONT_MONO, FONT_SCI))


# ─────────────────────────── 공통 그래픽 헬퍼 ───────────────────────────
def _grade_teal(img: Image.Image, cfg: HookIntroConfig) -> Image.Image:
    """다크틸 시네마틱 그레이딩 + 비네팅 + 마린스노우(결정론)."""
    W, H = cfg.W, cfg.H
    img = img.convert("RGB").resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(0.70)
    img = ImageEnhance.Contrast(img).enhance(1.14)
    img = Image.blend(img, Image.new("RGB", (W, H), (6, 30, 50)), 0.30)
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.25, -H * 0.12, W * 1.25, H * 1.12], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(160))
    img = Image.composite(img, ImageEnhance.Brightness(img).enhance(0.4), vig)
    dr = ImageDraw.Draw(img, "RGBA")
    s = 98765
    for _ in range(55):
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF; x = s % W
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF; y = s % H
        s = (s * 1103515245 + 12345) & 0x7FFFFFFF; a = 35 + s % 75
        r = 1 if a < 85 else 2
        dr.ellipse([x, y, x + r, y + r], fill=(200, 225, 235, a))
    return img.convert("RGB")


def _smooth(t: float) -> float:
    return t * t * (3 - 2 * t)


def _grad_sprite_diag(text: str, font, center: tuple, cfg: HookIntroConfig,
                      dmin: float, dmax: float, glow_r: int, pad: int = 48):
    """어절 스프라이트: 절대좌표 기준 대각 그라데이션(전 타이틀 연속) + 네온 글로우."""
    W, H = cfg.W, cfg.H
    ca, cb, gl = cfg.grad_cyan, cfg.grad_magenta, cfg.glow
    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(tmp).text(center, text, font=font, fill=(255, 255, 255, 255), anchor="mm")
    bbox = tmp.getbbox()
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad); y0 = max(0, y0 - pad); x1 = min(W, x1 + pad); y1 = min(H, y1 + pad)
    alpha = tmp.split()[3].crop((x0, y0, x1, y1))
    sw, sh = x1 - x0, y1 - y0
    grad = Image.new("RGB", (sw, sh)); px = grad.load()
    for yy in range(sh):
        for xx in range(sw):
            d = ((x0 + xx) + (y0 + yy) - dmin) / max(1, (dmax - dmin))
            d = min(1, max(0, d))
            px[xx, yy] = tuple(int(ca[i] + (cb[i] - ca[i]) * d) for i in range(3))
    colored = Image.merge("RGBA", (*grad.split(), alpha))
    ga = alpha.filter(ImageFilter.GaussianBlur(glow_r))
    gimg = Image.new("RGBA", (sw, sh), gl + (0,)); gimg.putalpha(ga.point(lambda v: int(v * 0.85)))
    return Image.alpha_composite(gimg, colored), center


# ─────────────────────────── 오프닝 타이틀 자동 배치 ───────────────────────────
def _fit_font(txt: str, base_size: int, max_w: float, loader, min_size: int = 24):
    """텍스트가 max_w를 넘으면 폰트를 비례 축소(넘침 원천 차단·모든 온스크린 텍스트 공통)."""
    meas = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
    w = meas.textlength(txt, font=loader(base_size))
    if w <= max_w:
        return loader(base_size)
    return loader(max(min_size, int(base_size * max_w / max(1, w))))


def opening_layout(spec: SpeciesSpec, cfg: HookIntroConfig | None = None) -> dict:
    """오프닝 타이틀 폰트·어절 중심 좌표 산출(단일 출처 — 화면 밖 넘침 원천 차단).

    왜 존재하나: 과거 고정 98px로 렌더해 긴 훅(ぺたんこの、体に、)이 좌우로 잘려 나갔다.
    규칙: ① 2줄(확정 디자인)로 safe 폭에 맞는 최대 크기 산출 ② 축소가 과하면
    (title_min_2line 미만) 어절당 1줄(3줄) 레이아웃으로 전환해 큰 글자를 유지.
    반환: {font, size, rows, centers[(x,y)], dmin, dmax}
    """
    cfg = cfg or HookIntroConfig()
    W = cfg.W
    meas = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
    safe = W - 2 * (cfg.shake_margin + cfg.title_safe_x)
    words = list(spec.hook_pop_words) or [spec.hook_line1]

    def max_width(texts: list[str], size: int) -> float:
        f = _serif(size)
        return max(meas.textlength(t, font=f) for t in texts)

    def fit(texts: list[str]) -> int:
        w = max_width(texts, cfg.title_size)
        if w <= safe:
            return cfg.title_size
        return max(cfg.title_min_size, int(cfg.title_size * safe / w))

    size = fit([spec.hook_line1, spec.hook_line2])
    if size >= cfg.title_min_2line or len(words) < 3:
        rows = 2
        f = _serif(size)
        w1 = meas.textlength(spec.hook_line1, font=f)
        centers: list[tuple] = []
        if len(words) >= 3:                      # line1 = 앞 어절들, line2 = 마지막 어절
            x = W / 2 - w1 / 2
            for wtxt in words[:-1]:
                ww = meas.textlength(wtxt, font=f)
                centers.append((int(x + ww / 2), cfg.title_y1)); x += ww
            centers.append((W // 2, cfg.title_y2))
        elif len(words) == 2:
            centers = [(W // 2, cfg.title_y1), (W // 2, cfg.title_y2)]
        else:
            centers = [(W // 2, (cfg.title_y1 + cfg.title_y2) // 2)]
    else:                                        # 3줄: 어절당 1줄 → 큰 글자 유지
        rows = len(words)
        size = fit(words)
        f = _serif(size)
        gap = int(size * 1.26)
        cy = (cfg.title_y1 + cfg.title_y2) // 2
        y0 = cy - gap * (rows - 1) // 2
        centers = [(W // 2, y0 + gap * i) for i in range(rows)]
    dmin, dmax = 1e9, -1e9                       # 전 어절 연속 대각 그라데이션 범위
    for wtxt, (cx, cy2) in zip(words, centers):
        ww = meas.textlength(wtxt, font=f)
        dmin = min(dmin, (cx - ww / 2) + (cy2 - 60))
        dmax = max(dmax, (cx + ww / 2) + (cy2 + 60))
    return {"font": f, "size": size, "rows": rows, "centers": centers,
            "dmin": dmin, "dmax": dmax, "safe": safe}


# ─────────────────────────── 오프닝 훅 렌더 ───────────────────────────
def render_opening_frames(bg_path: str, onsets: dict, spec: SpeciesSpec,
                          out_dir: str, cfg: HookIntroConfig | None = None) -> list[str]:
    """오프닝 훅 세그먼트 프레임(PNG) 렌더 → 파일 경로 리스트.

    onsets: {어절: 나레이션_로컬_시작초} — narration_sync WordBoundary에서 도출.
            팝인·셰이크·붐 SFX가 이 온셋에 정합된다.
    타이틀 배치는 opening_layout()이 단일 출처로 계산(넘침 원천 차단).
    """
    cfg = cfg or HookIntroConfig()
    W, H, M = cfg.W, cfg.H, cfg.shake_margin
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    lay = opening_layout(spec, cfg)
    f_title, centers, dmin, dmax = lay["font"], lay["centers"], lay["dmin"], lay["dmax"]

    # 팝인 어절 스프라이트(레이아웃이 준 중심·연속 그라데이션)
    words = spec.hook_pop_words
    ph = []
    for i, wtxt in enumerate(words):
        spr, c = _grad_sprite_diag(wtxt, f_title, centers[i % len(centers)], cfg, dmin, dmax, cfg.glow_r)
        onset = cfg.narr_start_s + list(onsets.values())[i % len(onsets)]
        ph.append((spr, c, onset))

    bg = _grade_teal(Image.open(bg_path), cfg)
    ov = _static_overlay(spec, cfg)
    CW, CH = W + 2 * M, H + 2 * M
    ovm = Image.new("RGBA", (CW, CH), (0, 0, 0, 0)); ovm.alpha_composite(ov, (M, M))

    def shake(t):
        dx = dy = 0.0
        for _, _, onset in ph:
            dt = t - onset
            if 0 <= dt < cfg.shake_dur_s:
                amp = cfg.shake_amp * math.exp(-dt / cfg.shake_decay_s)
                dx += amp * math.sin(2 * math.pi * 46 * dt)
                dy += amp * math.cos(2 * math.pi * 38 * dt) * 0.8
        return dx, dy

    def paste_scaled(base, spr, center, scale, alpha):
        if alpha <= 0:
            return
        w0, h0 = spr.size; w1s, h1s = max(1, int(w0 * scale)), max(1, int(h0 * scale))
        s = spr.resize((w1s, h1s), Image.LANCZOS)
        if alpha < 1:
            s.putalpha(s.split()[3].point(lambda v: int(v * alpha)))
        base.alpha_composite(s, (int(center[0] + M - w1s / 2), int(center[1] + M - h1s / 2)))

    paths = []
    N = int(cfg.opening_seg_s * cfg.FPS)
    for fi in range(N):
        t = fi / cfg.FPS
        z = 1.0 + 0.05 * _smooth(min(1, t / cfg.opening_seg_s))
        zw, zh = int(CW * z), int(CH * z)
        superf = bg.resize((zw, zh), Image.LANCZOS).crop(
            ((zw - CW) // 2, (zh - CH) // 2, (zw - CW) // 2 + CW, (zh - CH) // 2 + CH)).convert("RGBA")
        oa = _smooth(min(1, t / 0.5))
        if oa > 0:
            o = ovm.copy(); o.putalpha(o.split()[3].point(lambda v: int(v * oa))); superf.alpha_composite(o)
        for spr, center, onset in ph:
            dt = t - onset
            if dt < 0:
                continue
            sc = 1.34 - 0.34 * _smooth(min(1, dt / cfg.pop_grow_s))
            al = _smooth(min(1, dt / cfg.pop_fade_s))
            paste_scaled(superf, spr, center, sc, al)
        dx, dy = shake(t)
        ox = min(2 * M, max(0, int(round(M + dx))))
        oy = min(2 * M, max(0, int(round(M + dy))))
        p = str(Path(out_dir) / f"of_{fi:03d}.png")
        superf.crop((ox, oy, ox + W, oy + H)).convert("RGB").save(p)
        paths.append(p)
    return paths


def _static_overlay(spec: SpeciesSpec, cfg: HookIntroConfig) -> Image.Image:
    W, H = cfg.W, cfg.H
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, W, 70], fill=(0, 0, 0, 150)); d.rectangle([0, H - 70, W, H], fill=(0, 0, 0, 150))
    d.text((44, 455), "DEEP SEA · ROV CAM", font=_mono(19), fill=(150, 190, 205, 170), anchor="lm")
    # 실제 서식 수심 스케일(얕은 위 → 깊은 아래)
    x, y0, y1 = 648, 430, 910; col = (150, 200, 220)
    d.text((690, y0 - 42), "生息水深", font=_sans_r(20), fill=col + (200,), anchor="rm")
    d.line([x, y0, x, y1], fill=col + (140,), width=2)
    for i in range(4):
        t = i / 3; yy = int(y0 + (y1 - y0) * t)
        depth = int(round((spec.depth_min + (spec.depth_max - spec.depth_min) * t) / 100) * 100)
        d.line([x - 10, yy, x, yy], fill=col + (190,), width=2)
        d.text((x - 18, yy), f"{depth:,} m", font=_mono(23), fill=col + (215,), anchor="rm")
    # 하단 종 라벨(국명 + 이탤릭 학명)
    jp = f"{spec.jp_name}  /  "
    jw = d.textlength(jp, font=_sans_r(26))
    lxx = W // 2 - (jw + d.textlength(spec.sci_name, font=_sci(26))) / 2
    d.text((lxx + 1, H - 149), jp, font=_sans_r(26), fill=(0, 0, 0, 150), anchor="lm")
    d.text((lxx, H - 150), jp, font=_sans_r(26), fill=(180, 200, 215, 220), anchor="lm")
    d.text((lxx + jw, H - 150), spec.sci_name, font=_sci(26), fill=(180, 200, 215, 235), anchor="lm")
    return ov


# ─────────────────────────── 엔드카드 렌더 ───────────────────────────
def render_endcard(bg_path: str, spec: SpeciesSpec, out_path: str,
                   cfg: HookIntroConfig | None = None) -> str:
    cfg = cfg or HookIntroConfig()
    W, H = cfg.W, cfg.H
    CA, CB, GL = (120, 200, 250), cfg.grad_magenta, (90, 150, 240)
    CYAN = cfg.end_cyan
    img = Image.open(bg_path).convert("RGB").resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(0.82)
    img = ImageEnhance.Contrast(img).enhance(1.08)
    img = Image.blend(img, Image.new("RGB", (W, H), (8, 26, 44)), 0.20)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d0 = ImageDraw.Draw(ov)
    for y in range(560):
        d0.line([0, y, W, y], fill=(4, 12, 24, int(215 * (1 - y / 560))))
    for y in range(H - 360, H):
        t = (y - (H - 360)) / 360; d0.line([0, y, W, y], fill=(4, 10, 20, int(225 * t)))
    bg = img.convert("RGBA"); bg.alpha_composite(ov)

    def grad_text(center, text, font, glow_r=22, anchor="mm"):
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text(center, text, font=font, fill=(255, 255, 255, 255), anchor=anchor)
        bbox = tmp.getbbox()
        if not bbox:
            return
        x0, y0, x1, y1 = bbox; alpha = tmp.split()[3]
        grad = Image.new("RGB", (W, H)); px = grad.load(); dmin = x0 + y0; dmax = x1 + y1
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                dd = ((xx + yy) - dmin) / max(1, (dmax - dmin)); dd = min(1, max(0, dd))
                px[xx, yy] = tuple(int(CA[i] + (CB[i] - CA[i]) * dd) for i in range(3))
        colored = Image.merge("RGBA", (*grad.split(), alpha))
        ga = alpha.filter(ImageFilter.GaussianBlur(glow_r))
        gimg = Image.new("RGBA", (W, H), GL + (0,)); gimg.putalpha(ga.point(lambda v: int(v * 0.8)))
        bg.alpha_composite(gimg); bg.alpha_composite(colored)

    def text(center, t, font, fill, anchor="mm", shadow=True):
        dd = ImageDraw.Draw(bg)
        if shadow:
            dd.text((center[0] + 1, center[1] + 2), t, font=font, fill=(0, 0, 0, 150), anchor=anchor)
        dd.text(center, t, font=font, fill=fill, anchor=anchor)

    def particle(cx, cy, r, a=255):
        dd = ImageDraw.Draw(bg, "RGBA")
        for dx, dy, ln in [(0, -1, r), (0, 1, r), (-1, 0, r * 0.6), (1, 0, r * 0.6)]:
            dd.line([cx, cy, cx + dx * ln, cy + dy * ln], fill=(210, 240, 255, a), width=2)
        dd.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(255, 255, 255, a))

    # 중앙 정렬 텍스트 블록(캡슐·게이지 없음 — 사용자 확정) · 폰트는 화면폭 자동 맞춤
    max_w = W - 72
    f_title = _fit_font(spec.jp_name, cfg.end_title_size, max_w, _serif)
    f_feat = _fit_font(spec.feature_line, cfg.end_feature_size, max_w, _serif)
    grad_text((W // 2, 336), spec.jp_name, f_title, glow_r=26)
    text((W // 2, 430), spec.sci_name, _fit_font(spec.sci_name, cfg.end_sci_size, max_w, _sci),
         (210, 220, 235, 255))
    depth_str = f"水深 {spec.depth_min:,}〜{spec.depth_max:,} m"
    text((W // 2, 512), depth_str, _fit_font(depth_str, cfg.end_depth_size, max_w, _sans_b),
         CYAN + (255,))
    # 특징문구 + glow 단어 주변 파티클
    line = spec.feature_line
    text((W // 2, 1060), line, f_feat, (232, 240, 250, 255))
    dd = ImageDraw.Draw(bg)
    gw = spec.feature_glow_word
    idx = line.find(gw)
    if idx >= 0:
        full_w = dd.textlength(line, font=f_feat)
        lx = W // 2 - full_w / 2
        pre = line[:idx]
        hx = lx + dd.textlength(pre, font=f_feat) + dd.textlength(gw, font=f_feat) / 2
        for dx, dy, r, a in [(-46, -30, 7, 255), (30, -38, 5, 220), (52, 10, 6, 240),
                             (-30, 26, 4, 200), (8, -52, 4, 180)]:
            particle(int(hx + dx), 1060 + dy, r, a)
    text((W // 2, H - 40), "映像: NOAA Ocean Exploration ・ Public Domain",
         _sans_r(20), (160, 175, 200, 225), shadow=False)
    bg.convert("RGB").save(out_path)
    return out_path


# ─────────────────────────── 임팩트 사운드(딥 붐) ───────────────────────────
def generate_boom(out_path: str, cfg: HookIntroConfig | None = None) -> str:
    """'쿵/쾅' 시네마틱 딥 붐 합성(무료·결정론, stdlib).
    ①슬램 트랜지언트 ②서브베이스 스윕(110→38Hz) ③저역 바디+소프트 새추레이션."""
    cfg = cfg or HookIntroConfig()
    SR = 44100; N = int(SR * cfg.boom_dur_s)
    import random as _r
    rnd = _r.Random(11)
    buf = [0.0] * N
    for i in range(N):
        t = i / SR
        slam = rnd.uniform(-1, 1) * math.exp(-t / 0.006) * 0.9
        f_sub = 38 + (110 - 38) * math.exp(-t / 0.06)
        sub = math.sin(2 * math.pi * f_sub * t) * math.exp(-t / 0.16) * 1.15
        body = math.sin(2 * math.pi * 70 * t) * math.exp(-t / 0.10) * 0.55
        rumble = rnd.uniform(-1, 1) * math.exp(-t / 0.09) * 0.12
        buf[i] = math.tanh((slam + sub + body + rumble) * 1.5)
    for i in range(N):
        if i < 40:
            buf[i] *= i / 40
        if i > N - 400:
            buf[i] *= (N - i) / 400
    peak = max(1e-6, max(abs(x) for x in buf))
    buf = [x / peak * 0.98 for x in buf]
    with wave.open(out_path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(x * 32767)) for x in buf))
    return out_path


def build_flash_png(out_path: str, cfg: HookIntroConfig | None = None) -> str:
    """전환(오프닝→본문, 본문→엔드카드)용 밝은 플래시 프레임."""
    cfg = cfg or HookIntroConfig()
    Image.new("RGB", (cfg.W, cfg.H), (228, 240, 248)).save(out_path)
    return out_path


def build_specimen_bg(frame_path: str, out_path: str, cfg: HookIntroConfig | None = None) -> str:
    """엔드카드 배경: 메인 피사체 프레임을 과도 줌 없이 '중간 밴드'에 온전히 배치.
    상·하는 어둠(텍스트 영역) — 피사체가 텍스트에 가리지 않고 잘 보이게."""
    cfg = cfg or HookIntroConfig()
    W, H = cfg.W, cfg.H
    BAND_TOP, BAND_BOT = 545, 950
    src = Image.open(frame_path).convert("RGB")
    bw = W; bh = int(src.height * bw / src.width)
    # 소스가 세로로 과하면(9:16 리프레임 프레임 등) 중앙 크롭으로 밴드에 맞춤 —
    # 밴드가 텍스트 영역을 침범하거나 피사체가 확대·잘리는 것 방지.
    max_bh = (BAND_BOT - BAND_TOP) + 60
    if bh > max_bh:
        crop_h = int(src.width * max_bh / bw)
        top = max(0, (src.height - crop_h) // 2)
        src = src.crop((0, top, src.width, min(src.height, top + crop_h)))
        bh = max_bh
    band = src.resize((bw, bh), Image.LANCZOS)
    band = ImageEnhance.Brightness(band).enhance(0.82)
    band = ImageEnhance.Contrast(band).enhance(1.06)
    band = Image.blend(band, Image.new("RGB", (bw, bh), (10, 30, 48)), 0.28)
    canvas = Image.new("RGB", (W, H), (7, 20, 34))
    band_y = (BAND_TOP + BAND_BOT) // 2 - bh // 2
    mask = Image.new("L", (bw, bh), 255); md = ImageDraw.Draw(mask); fea = 70
    for i in range(fea):
        a = int(255 * i / fea)
        md.line([0, i, bw, i], fill=a); md.line([0, bh - 1 - i, bw, bh - 1 - i], fill=a)
    canvas.paste(band, (0, band_y), mask)
    vig = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vig).ellipse([-W * 0.15, band_y - 40, W * 1.15, band_y + bh + 40], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(90))
    canvas = Image.composite(canvas, ImageEnhance.Brightness(canvas).enhance(0.6), vig)
    canvas.save(out_path)
    return out_path


def generate_type_click(out_path: str, cfg: HookIntroConfig | None = None) -> str:
    """타자기 타이핑 클릭음(무료·결정론). 짧은 노이즈 어택 + 고역 클릭 → 'tk'."""
    cfg = cfg or HookIntroConfig()
    SR = 44100; N = int(SR * cfg.type_click_dur_s)
    import random as _r
    rnd = _r.Random(23)
    buf = []
    for i in range(N):
        t = i / SR
        click = rnd.uniform(-1, 1) * math.exp(-t / 0.0025) * 0.9
        tone = math.sin(2 * math.pi * 1850 * t) * math.exp(-t / 0.010) * 0.4
        buf.append(math.tanh((click + tone) * 1.2))
    peak = max(1e-6, max(abs(x) for x in buf))
    buf = [x / peak * 0.9 for x in buf]
    with wave.open(out_path, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(x * 32767)) for x in buf))
    return out_path


# ─────────────────────────── 엔드카드(타자기 애니메이션) ───────────────────────────
def _endcard_base(bg_path: str, cfg: HookIntroConfig) -> Image.Image:
    """엔드카드 배경(그레이딩 + 상·하 스크림). 피사체는 중간 밴드에 온전히 보이게 준비된 bg 사용."""
    W, H = cfg.W, cfg.H
    img = Image.open(bg_path).convert("RGB").resize((W, H))
    img = ImageEnhance.Brightness(img).enhance(0.9)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d0 = ImageDraw.Draw(ov)
    for y in range(540):
        d0.line([0, y, W, y], fill=(4, 12, 24, int(205 * (1 - y / 540))))
    for y in range(H - 320, H):
        t = (y - (H - 320)) / 320
        d0.line([0, y, W, y], fill=(4, 10, 20, int(215 * t)))
    base = img.convert("RGBA"); base.alpha_composite(ov)
    return base


def _styled_line(spec: SpeciesSpec, cfg: HookIntroConfig):
    """엔드카드 각 텍스트 줄 → (풀캔버스 RGBA 레이어, 글자별 누적 x경계, y, 시작초, cps)."""
    W, H = cfg.W, cfg.H
    CA, CB, GL, CYAN = (120, 200, 250), cfg.grad_magenta, (90, 150, 240), cfg.end_cyan
    meas = ImageDraw.Draw(Image.new("RGBA", (2, 2)))

    def char_bounds(txt, font):
        fw = meas.textlength(txt, font=font); lx = W // 2 - fw / 2
        return lx, [lx + meas.textlength(txt[: i + 1], font=font) for i in range(len(txt))]

    def solid_layer(txt, font, y, fill):
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
        d.text((W // 2 + 1, y + 2), txt, font=font, fill=(0, 0, 0, 150), anchor="mm")
        d.text((W // 2, y), txt, font=font, fill=fill, anchor="mm")
        return lay

    def grad_layer(txt, font, y, glow_r):
        tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(tmp).text((W // 2, y), txt, font=font, fill=(255, 255, 255, 255), anchor="mm")
        bbox = tmp.getbbox(); x0, y0, x1, y1 = bbox; alpha = tmp.split()[3]
        grad = Image.new("RGB", (W, H)); px = grad.load(); dmin = x0 + y0; dmax = x1 + y1
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                dd = ((xx + yy) - dmin) / max(1, (dmax - dmin)); dd = min(1, max(0, dd))
                px[xx, yy] = tuple(int(CA[i] + (CB[i] - CA[i]) * dd) for i in range(3))
        colored = Image.merge("RGBA", (*grad.split(), alpha))
        ga = alpha.filter(ImageFilter.GaussianBlur(glow_r))
        gimg = Image.new("RGBA", (W, H), GL + (0,)); gimg.putalpha(ga.point(lambda v: int(v * 0.8)))
        return Image.alpha_composite(gimg, colored)

    depth_str = f"水深 {spec.depth_min:,}〜{spec.depth_max:,} m"
    # 각 줄 폰트는 화면폭에 자동 맞춤(_fit_font) — 긴 국명·특징문구도 넘침 원천 차단
    max_w = W - 72
    ft = _fit_font(spec.jp_name, cfg.end_title_size, max_w, _serif)
    fs = _fit_font(spec.sci_name, cfg.end_sci_size, max_w, _sci)
    fd = _fit_font(depth_str, cfg.end_depth_size, max_w, _sans_b)
    ff = _fit_font(spec.feature_line, cfg.end_feature_size, max_w, _serif)
    specs = [
        ("title", spec.jp_name, ft, 336, cfg.type_cps_title, grad_layer(spec.jp_name, ft, 336, 26)),
        ("sci", spec.sci_name, fs, 430, cfg.type_cps_body, solid_layer(spec.sci_name, fs, 430, (210, 220, 235, 255))),
        ("depth", depth_str, fd, 512, cfg.type_cps_body, solid_layer(depth_str, fd, 512, CYAN + (255,))),
        ("feature", spec.feature_line, ff, 1060, cfg.type_cps_body, solid_layer(spec.feature_line, ff, 1060, (232, 240, 250, 255))),
    ]
    lines = []
    start = cfg.type_start_s
    for key, txt, font, y, cps, layer in specs:
        lx, bounds = char_bounds(txt, font)
        dur = len(txt) / cps
        lines.append({"key": key, "txt": txt, "font": font, "y": y, "lx": lx,
                      "bounds": bounds, "start": start, "cps": cps, "layer": layer})
        start += dur + cfg.type_line_gap_s
    return lines


def render_endcard_frames(bg_path: str, spec: SpeciesSpec, out_dir: str,
                          cfg: HookIntroConfig | None = None):
    """엔드카드를 '타자기'로 렌더 → (프레임 경로들, 타자 클릭 시각들).

    각 줄이 글자 단위로 왼→오 등장(타자기). 클릭음은 글자 등장 시각에 정확히 정합되어
    타이핑 시작·종료와 사운드 시작·종료가 맞는다. glow 단어 파티클은 특징줄 완성 후 페이드.
    """
    cfg = cfg or HookIntroConfig()
    W, H = cfg.W, cfg.H
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    base = _endcard_base(bg_path, cfg)
    lines = _styled_line(spec, cfg)

    # 타자 클릭 시각(공백 제외) 수집
    click_times = []
    for ln in lines:
        for i, ch in enumerate(ln["txt"]):
            if ch.strip():
                click_times.append(round(ln["start"] + i / ln["cps"], 3))
    feature = next(l for l in lines if l["key"] == "feature")
    feat_done = feature["start"] + len(feature["txt"]) / feature["cps"]

    def particles(canvas, alpha):
        line = feature["txt"]; gw = spec.feature_glow_word; idx = line.find(gw)
        if idx < 0 or alpha <= 0:
            return
        meas = ImageDraw.Draw(canvas)
        f = feature["font"]
        hx = feature["lx"] + meas.textlength(line[:idx], font=f) + meas.textlength(gw, font=f) / 2
        dd = ImageDraw.Draw(canvas, "RGBA")
        for dx, dy, r, a in [(-46, -30, 7, 255), (30, -38, 5, 220), (52, 10, 6, 240),
                             (-30, 26, 4, 200), (8, -52, 4, 180)]:
            aa = int(a * alpha)
            for ex, ey, ln2 in [(0, -1, r), (0, 1, r), (-1, 0, r * 0.6), (1, 0, r * 0.6)]:
                dd.line([hx + dx, 1060 + dy, hx + dx + ex * ln2, 1060 + dy + ey * ln2],
                        fill=(210, 240, 255, aa), width=2)

    credit_font = _sans_r(20)
    paths = []
    N = int(cfg.endcard_dur_s * cfg.FPS)
    for fi in range(N):
        t = fi / cfg.FPS
        frame = base.copy()
        for ln in lines:
            dt = t - ln["start"]
            if dt < 0:
                continue
            n = min(len(ln["txt"]), int(dt * ln["cps"]) + 1)
            reveal_x = ln["bounds"][n - 1] + 3
            mask = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mask).rectangle([0, 0, int(reveal_x), H], fill=255)
            lay = ln["layer"].copy()
            lay.putalpha(Image.composite(lay.split()[3], Image.new("L", (W, H), 0), mask))
            frame.alpha_composite(lay)
        # 특징줄 완성 후 파티클 페이드인
        particles(frame, _smooth(min(1, max(0, (t - feat_done) / 0.4))))
        # 크레딧(타이핑 없이 늦게 페이드인)
        ca = _smooth(min(1, max(0, (t - feat_done - 0.2) / 0.5)))
        if ca > 0:
            cl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(cl).text((W // 2, H - 40), "映像: NOAA Ocean Exploration ・ Public Domain",
                                    font=credit_font, fill=(160, 175, 200, int(225 * ca)), anchor="mm")
            frame.alpha_composite(cl)
        p = str(Path(out_dir) / f"ec_{fi:03d}.png")
        frame.convert("RGB").save(p)
        paths.append(p)
    return paths, click_times
