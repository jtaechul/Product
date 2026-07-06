"""overlay — 훅·정보 텍스트·워터마크·출처 크레딧을 영상 위에 합성 (Pillow + FFmpeg).

PRD 6장: 워터마크는 1프레임부터 상시. 화면 정보 = 훅 + 팩트 + 종명 + 크레딧.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from src.core.contracts import CaptionData, PipelineError, SpeciesInfo
from src.core.visualization.base import CLIP_H, CLIP_W

_FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise PipelineError("overlay", "한국어 폰트 없음 (fonts-noto-cjk 설치 필요)")


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """단어 단위 줄바꿈 (한국어는 공백 기준으로 충분)."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _text_with_stroke(draw, xy, text, font, fill="white", anchor=None):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor,
              stroke_width=3, stroke_fill=(0, 0, 0, 220))


def build_overlay_png(
    caption: CaptionData,
    info: SpeciesInfo,
    credit_string: str,
    watermark: str,
    out_path: str,
) -> str:
    """투명 PNG 1장에 훅(상단)·팩트(하단)·종명·워터마크·크레딧을 그린다."""
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    f_hook = _font(52)
    f_fact = _font(38)
    f_name = _font(34)
    f_small = _font(24)

    margin = 40
    max_w = CLIP_W - margin * 2

    # 1) 워터마크 — 우상단 (1프레임부터 상시)
    _text_with_stroke(d, (CLIP_W - margin, 36), watermark, f_small, fill=(255, 255, 255, 210), anchor="ra")

    # 2) 훅 — 상단 중앙
    y = 120
    for line in _wrap(d, caption.hook_text, f_hook, max_w):
        _text_with_stroke(d, (CLIP_W // 2, y), line, f_hook, anchor="ma")
        y += 66

    # 하단 블록(팩트+종명)은 크레딧 위로 넘치지 않게 상한을 둔다.
    credit_y = CLIP_H - 60
    name_h, gap = 42, 8
    y = CLIP_H - 330
    # 종명이 크레딧과 겹치지 않는 팩트 하한
    fact_bottom_limit = credit_y - name_h - gap - 12

    # 3) 정보 팩트 — 하단 (최대 2줄, 하한 초과 시 절단)
    for fact in caption.overlay_facts[:2]:
        for line in _wrap(d, f"· {fact}", f_fact, max_w):
            if y > fact_bottom_limit:
                break
            _text_with_stroke(d, (margin, y), line, f_fact, fill=(210, 240, 255, 255))
            y += 50

    # 4) 종명 KR/EN — 팩트 아래(단, 크레딧 위로 클램프)
    name_y = min(y + gap, credit_y - name_h - gap)
    name_line = f"{info.common_name_ko} ({info.common_name_en})"
    _text_with_stroke(d, (margin, name_y), name_line, f_name, fill=(255, 230, 160, 255))

    # 5) 출처 크레딧 — 최하단 (하드 룰: 자동 삽입)
    _text_with_stroke(d, (margin, credit_y), credit_string, f_small, fill=(255, 255, 255, 190))

    img.save(out_path)
    return out_path


def apply_overlay(base_video: str, overlay_png: str, work_dir: str) -> str:
    """PNG 오버레이를 전 구간 합성 → work/overlaid.mp4"""
    out_path = Path(work_dir) / "overlaid.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", base_video, "-i", overlay_png,
        "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PipelineError("overlay", f"오버레이 합성 실패: {proc.stderr[-500:]}")
    return str(out_path)


# ---------- 컷별 타이밍 오버레이 (리빌 정책) ----------

def _base_png(watermark: str, credit_string: str, out_path: str) -> str:
    """전 구간 상시 레이어: 워터마크(1프레임부터) + 출처 크레딧 (하드 룰)."""
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _text_with_stroke(d, (CLIP_W - 40, 36), watermark, _font(24),
                      fill=(255, 255, 255, 210), anchor="ra")
    _text_with_stroke(d, (40, CLIP_H - 60), credit_string, _font(24),
                      fill=(255, 255, 255, 190))
    img.save(out_path)
    return out_path


def _cut_png(top_text: str, bottom_text: str, out_path: str) -> str:
    """컷 구간 레이어: 상단(훅) + 하단(비트) 텍스트."""
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin, max_w = 40, CLIP_W - 80
    if top_text:
        f_hook = _font(52)
        y = 120
        for line in _wrap(d, top_text, f_hook, max_w):
            _text_with_stroke(d, (CLIP_W // 2, y), line, f_hook, anchor="ma")
            y += 66
    if bottom_text:
        f_beat = _font(40)
        lines = _wrap(d, bottom_text, f_beat, max_w)
        y = CLIP_H - 150 - 52 * (len(lines) - 1)
        for line in lines:
            _text_with_stroke(d, (margin, y), line, f_beat, fill=(210, 240, 255, 255))
            y += 52
    img.save(out_path)
    return out_path


def apply_timed_overlays(
    base_video: str,
    caption: CaptionData,
    credit_string: str,
    watermark: str,
    cut_durations: list[float],
    work_dir: str,
) -> str:
    """컷별 타이밍 오버레이 합성 (리빌 정책 구현).

    컷1: 훅(상단) + 미스터리 비트(하단) — 종명 없음
    컷2: 행동 비트(하단)
    컷3: 리빌(종명+킬러팩트, 하단 강조)
    전 구간: 워터마크 + 크레딧
    """
    work = Path(work_dir)
    beats = caption.cut_beats or ["", "", ""]
    base_png = _base_png(watermark, credit_string, str(work / "ov_base.png"))
    cut_pngs = [
        _cut_png(caption.hook_text, beats[0], str(work / "ov_cut1.png")),
        _cut_png("", beats[1] if len(beats) > 1 else "", str(work / "ov_cut2.png")),
        _cut_png("", beats[2] if len(beats) > 2 else "", str(work / "ov_cut3.png")),
    ]

    # 컷 경계 시각 계산
    t0 = 0.0
    windows = []
    for dur in cut_durations:
        windows.append((t0, t0 + dur))
        t0 += dur
    while len(windows) < 3:  # 컷이 3개 미만이어도 안전
        windows.append(windows[-1] if windows else (0.0, 0.0))

    inputs = ["-i", base_video, "-i", base_png]
    for p in cut_pngs:
        inputs += ["-i", p]

    fc = "[0:v][1:v]overlay=0:0:format=auto[v0];"
    prev = "v0"
    for i, (start, end) in enumerate(windows[:3]):
        out = f"v{i+1}"
        fc += (f"[{prev}][{i+2}:v]overlay=0:0:format=auto:"
               f"enable='between(t,{start:.3f},{end:.3f})'[{out}];")
        prev = out
    fc = fc.rstrip(";")

    out_path = work / "overlaid.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex", fc, "-map", f"[{prev}]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PipelineError("overlay", f"타이밍 오버레이 실패: {proc.stderr[-500:]}")
    return str(out_path)
