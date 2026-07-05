"""hud — SF ROV 미스터리 HUD 오버레이 (전략: 현실 기반 극도로 드라마틱한 심해 미스터리).

컨셉: 무인 심해 탐사정(ROV) 계기판. 컷1~2는 정체를 숨기고 'SCANNING/UNKNOWN LIFEFORM',
컷3에서 'SPECIES IDENTIFIED'로 리빌. 네온 프레임 + 코너 텔레메트리 + 코너 소나 스윕.
원칙: 화면 중앙(생물)은 가리지 않는다. 스캔 연출은 코너로. 텍스트는 굵고 크게(모바일 1초 가독).
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from src.core.contracts import CaptionData, PipelineError, SpeciesInfo
from src.core.overlay import _font, _text_with_stroke, _wrap
from src.core.visualization.base import CLIP_H, CLIP_W

NEON = (40, 220, 240, 255)
ORG = (250, 150, 60, 255)
WHT = (240, 245, 248, 255)
GOLD = (255, 230, 160, 255)


def _max_depth(info: SpeciesInfo) -> str:
    import re
    d = re.sub(r"[^\d]", "", info.depth_range_m.split("-")[-1])
    return f"{int(d):,}" if d else "4,000"


def _neon_corners(d: ImageDraw.ImageDraw):
    for (x, y, dx, dy) in [(20, 20, 1, 1), (CLIP_W - 20, 20, -1, 1),
                           (20, CLIP_H - 20, 1, -1), (CLIP_W - 20, CLIP_H - 20, -1, -1)]:
        for o, a in ((5, 70), (2, 200)):
            d.line([(x, y), (x + dx * 58, y)], fill=(40, 220, 240, a), width=2 + o)
            d.line([(x, y), (x, y + dy * 58)], fill=(40, 220, 240, a), width=2 + o)
        d.line([(x + dx * 8, y + dy * 8), (x + dx * 22, y + dy * 8)], fill=ORG, width=4)


def _radar(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int, sweep_deg: int):
    for rr, a in ((r, 90), (int(r * 0.66), 140), (int(r * 0.33), 200)):
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=(40, 220, 240, a), width=2)
    d.line([(cx, cy), (cx + r * math.cos(math.radians(sweep_deg)),
                       cy + r * math.sin(math.radians(sweep_deg)))], fill=ORG, width=3)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=ORG)


def _base_layer(info: SpeciesInfo, watermark: str, timecode: str, sweep: int) -> Image.Image:
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _neon_corners(d)
    # 좌상단: 유닛 + REC
    _text_with_stroke(d, (34, 34), "ROV · DEEP DIVE UNIT", _font(20), fill=NEON)
    d.ellipse([34, 66, 48, 80], fill=(230, 70, 70, 255))
    _text_with_stroke(d, (56, 63), f"REC  {timecode}", _font(20), fill=WHT)
    # 우상단 텔레메트리 패널
    d.rectangle([CLIP_W - 250, 26, CLIP_W - 22, 120], fill=(6, 20, 30, 140),
                outline=(40, 220, 240, 170), width=2)
    _text_with_stroke(d, (CLIP_W - 238, 34), f"DEPTH  {_max_depth(info)} M", _font(22), fill=NEON)
    _text_with_stroke(d, (CLIP_W - 238, 64), "TEMP  2.1°C", _font(18), fill=WHT)
    _text_with_stroke(d, (CLIP_W - 238, 90), "34.21°N  127.88°E", _font(15), fill=(180, 190, 200, 255))
    # 좌하단 소나(코너) — 얼굴 안 가림
    _radar(d, 92, CLIP_H - 220, 60, sweep)
    _text_with_stroke(d, (34, CLIP_H - 148), "TACTICAL SONAR", _font(15), fill=(150, 225, 220, 255))
    # 워터마크
    _text_with_stroke(d, (CLIP_W - 30, CLIP_H - 46), watermark, _font(20), fill=(230, 235, 240, 200),
                      anchor="ra")
    return img


def _hook_layer(top_text: str, mid_tag: str, mid_sub: str) -> Image.Image:
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if top_text:
        y = 150
        for line in _wrap(d, top_text, _font(54), CLIP_W - 90):
            _text_with_stroke(d, (CLIP_W // 2, y), line, _font(54), anchor="ma")
            y += 66
    if mid_tag:
        _text_with_stroke(d, (CLIP_W // 2, CLIP_H - 300), mid_tag, _font(36), fill=NEON, anchor="ma")
    if mid_sub:
        _text_with_stroke(d, (CLIP_W // 2, CLIP_H - 254), mid_sub, _font(22), fill=ORG, anchor="ma")
    return img


def _reveal_layer(caption: CaptionData) -> Image.Image:
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([24, CLIP_H - 210, CLIP_W - 24, CLIP_H - 96], fill=(6, 20, 30, 175),
                outline=(40, 220, 240, 200), width=2)
    _text_with_stroke(d, (40, CLIP_H - 200), "▶ SPECIES IDENTIFIED", _font(20), fill=ORG)
    y = CLIP_H - 168
    for line in _wrap(d, caption.reveal_name, _font(34), CLIP_W - 90):
        _text_with_stroke(d, (40, y), line, _font(34), fill=GOLD)
        y += 42
    _text_with_stroke(d, (40, y + 2), caption.reveal_fact, _font(20), fill=(210, 235, 245, 255))
    return img


def apply_hud(base_video: str, caption: CaptionData, info: SpeciesInfo, watermark: str,
              cut_durations: list[float], work_dir: str) -> str:
    """컷별 SF HUD 오버레이 합성 (SCANNING → IDENTIFIED 리빌)."""
    work = Path(work_dir)
    beats = caption.cut_beats or ["", "", ""]

    t0 = 0.0
    windows = []
    for dur in cut_durations:
        windows.append((t0, t0 + dur, t0))
        t0 += dur
    while len(windows) < 3:
        windows.append(windows[-1] if windows else (0.0, 0.0, 0.0))

    # 컷별 레이어 PNG (base + 컷 콘텐츠 합쳐서 1장씩)
    layer_paths = []
    for i, (start, end, cum) in enumerate(windows[:3]):
        tc = f"00:{int(cum)//60:02d}:{int(cum):02d}"
        base = _base_layer(info, watermark, tc, sweep=(i * 120) % 360)
        if i == 0:
            top = caption.hook_text
            content = _hook_layer(top, ">> SCANNING . . .", "UNKNOWN LIFEFORM DETECTED")
        elif i == 1:
            content = _hook_layer("", ">> ANALYZING . . .", beats[1] if len(beats) > 1 else "")
        else:
            content = _reveal_layer(caption)
        base.alpha_composite(content)
        p = work / f"hud_{i}.png"
        base.convert("RGBA").save(p)
        layer_paths.append(str(p))

    inputs = ["-i", base_video]
    for p in layer_paths:
        inputs += ["-i", p]
    fc = ""
    prev = "0:v"
    for i, (start, end, _c) in enumerate(windows[:3]):
        out = f"v{i}"
        fc += (f"[{prev}][{i+1}:v]overlay=0:0:format=auto:"
               f"enable='between(t,{start:.3f},{end:.3f})'[{out}];")
        prev = out
    fc = fc.rstrip(";")

    out_path = work / "overlaid.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex", fc, "-map", f"[{prev}]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PipelineError("hud", f"HUD 오버레이 실패: {proc.stderr[-500:]}")
    return str(out_path)
