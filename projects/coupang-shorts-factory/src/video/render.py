"""M6. 영상 렌더링 — MoviePy 2.x (버전 고정: requirements.txt).

Phase 0 범위 (스펙 §8):
  - 캔버스 1080x1920(9:16), 30fps
  - 배경: assets/backgrounds/ 의 CC0 세로영상 랜덤 선택(오디오 길이에 맞춰 트림/루프),
    없으면 자체 생성 그라데이션(화이트리스트 §3.2: 자체 생성물) 폴백
  - 자막: 단어 단위 팝업 — GmarketSansBold, font_size 80, #FFE400, 검정 stroke 6,
    위치 (center, y=1250)
  - 쉐이크: price_shock 라인 시작 0.3초간 ±8px 랜덤 오프셋
  - 인코딩: H.264 CRF 20, AAC 128k
상품 이미지 오버레이(줌인)는 상품 데이터가 생기는 Phase 1에서 구현한다.

MoviePy 2.x 주의(스펙 §M6): TextClip은 PIL 기반 — font 인자에 ttf '파일 경로'를
직접 지정해야 한글이 깨지지 않는다.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    vfx,
)

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}


def render_video(audio_path: Path, words: list, out_path: Path, settings: dict,
                 shake_windows: list | None = None, project_root: Path | None = None,
                 image_windows: list | None = None) -> dict:
    """단어 타임스탬프 기반 쇼츠 렌더. 반환: 렌더 통계 dict (DoD: 렌더 시간 기록)."""
    r = settings.get("render", {})
    s = settings.get("subtitle", {})
    width, height = int(r.get("width", 1080)), int(r.get("height", 1920))
    fps = int(r.get("fps", 30))
    shake_px = int(r.get("shake_px", 8))
    shake_windows = shake_windows or []
    project_root = project_root or Path.cwd()

    font_path = _resolve_font(project_root, s.get("font", "assets/fonts/GmarketSansBold.ttf"))

    audio = AudioFileClip(str(audio_path))
    duration = float(audio.duration) + 0.25

    bg_dir = project_root / settings.get("assets", {}).get("backgrounds_dir", "assets/backgrounds")
    background, bg_name = _build_background(bg_dir, width, height, duration, shake_px)

    if shake_windows:
        margin = shake_px
        base = (-margin, -margin)

        def bg_pos(t):
            for a, b in shake_windows:
                if a <= t <= b:
                    rnd = random.Random(int(t * fps) * 9973 + 7)  # 프레임별 결정적 랜덤
                    return (base[0] + rnd.randint(-shake_px, shake_px),
                            base[1] + rnd.randint(-shake_px, shake_px))
            return base

        background = background.with_position(bg_pos)
    else:
        background = background.with_position((-shake_px, -shake_px))

    word_clips = _build_word_clips(words, duration, font_path, s, width)
    image_clips = _build_image_clips(image_windows or [], duration, width)

    t0 = time.time()
    final = (
        CompositeVideoClip([background, *image_clips, *word_clips], size=(width, height))
        .with_duration(duration)
        .with_audio(audio)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate=r.get("audio_bitrate", "128k"),
        preset="medium",
        ffmpeg_params=["-crf", str(r.get("crf", 20)), "-pix_fmt", "yuv420p"],
        threads=os.cpu_count() or 2,
        logger=None,
    )
    render_seconds = time.time() - t0
    final.close()
    audio.close()

    return {
        "render_seconds": round(render_seconds, 1),
        "video_duration_seconds": round(duration, 2),
        "realtime_factor": round(render_seconds / max(duration, 0.01), 2),
        "resolution": f"{width}x{height}@{fps}fps",
        "word_clip_count": len(word_clips),
        "image_clip_count": len(image_clips),
        "font_used": str(font_path),
        "background_used": bg_name,
        "output_bytes": out_path.stat().st_size,
    }


def _resolve_font(project_root: Path, font_rel: str) -> Path:
    """GmarketSansBold 우선, 없으면 폴더 내 아무 ttf, 최후엔 시스템 CJK 폰트(경고)."""
    font_path = (project_root / font_rel).resolve()
    if font_path.exists():
        return font_path
    fonts_dir = project_root / "assets" / "fonts"
    for cand in sorted(fonts_dir.glob("*.ttf")) + sorted(fonts_dir.glob("*.otf")):
        print(f"[render] 경고: {font_rel} 없음 → 대체 폰트 사용: {cand.name}")
        return cand
    for sys_cand in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ):
        if Path(sys_cand).exists():
            print(f"[render] 경고: 프로젝트 폰트 없음 → 시스템 폰트 사용: {sys_cand}")
            return Path(sys_cand)
    raise FileNotFoundError(
        f"한글 폰트를 찾을 수 없습니다: {font_path} — README의 폰트 배치 안내를 따라주세요."
    )


def _build_background(bg_dir: Path, width: int, height: int, duration: float,
                      margin: int) -> tuple:
    """CC0 세로영상 랜덤 선택(cover-fit + 루프/트림). 없으면 그라데이션 자체 생성."""
    over_w, over_h = width + 2 * margin, height + 2 * margin
    candidates = [p for p in sorted(bg_dir.glob("*")) if p.suffix.lower() in VIDEO_EXTS]
    if candidates:
        pick = random.choice(candidates)
        clip = VideoFileClip(str(pick)).without_audio()
        scale = max(over_w / clip.w, over_h / clip.h)
        clip = clip.resized(scale).cropped(
            x_center=clip.w * scale / 2, y_center=clip.h * scale / 2,
            width=over_w, height=over_h,
        )
        if clip.duration < duration:
            clip = clip.with_effects([vfx.Loop(duration=duration)])
        else:
            clip = clip.subclipped(0, duration)
        return clip, pick.name

    # 자체 생성 그라데이션 (딥네이비 → 퍼플, 스펙 §3.2 화이트리스트: 자체 생성물)
    top, bottom = np.array([12, 14, 34]), np.array([52, 22, 66])
    rows = np.linspace(0, 1, over_h)[:, None]
    grad = (top[None, :] * (1 - rows) + bottom[None, :] * rows).astype(np.uint8)
    frame = np.repeat(grad[:, None, :], over_w, axis=1)
    return ImageClip(frame).with_duration(duration), "(자체 생성 그라데이션)"


def _build_image_clips(image_windows: list, duration: float, width: int) -> list:
    """상품 이미지 오버레이 — image_cue 라인 시작에 등장, 상단 중앙,
    줌인 1.00→1.08 선형 보간 (스펙 §M6-2). 실패한 이미지는 건너뛴다."""
    clips = []
    for start, end, img_path in image_windows:
        end = min(float(end), duration)
        start = max(0.0, float(start))
        dur = end - start
        if dur <= 0.1 or not Path(img_path).exists():
            continue
        try:
            base = ImageClip(str(img_path))
            target_w = int(width * 0.68)
            base = base.resized(width=target_w)
            clip = (
                base.resized(lambda t, d=dur: 1.0 + 0.08 * min(1.0, t / d))
                .with_start(start).with_duration(dur)
                .with_position(("center", 150))
            )
            clips.append(clip)
        except Exception as e:
            print(f"[render] 경고: 이미지 오버레이 실패({Path(img_path).name}: {e}) — 건너뜀")
    return clips


def _build_word_clips(words: list, duration: float, font_path: Path,
                      s: dict, width: int) -> list:
    """단어 단위 팝업 자막: 각 단어를 발화 시점에 표시, 다음 단어 시작까지 유지."""
    font_size = int(s.get("font_size", 80))
    color = s.get("color", "#FFE400")
    stroke_color = s.get("stroke_color", "#000000")
    stroke_width = int(s.get("stroke_width", 6))
    y = int(s.get("y", 1250))

    clips = []
    for i, w in enumerate(words):
        start = max(0.0, float(w["start"]))
        if i + 1 < len(words):
            end = float(words[i + 1]["start"])
        else:
            end = min(float(w["end"]) + 0.4, duration)
        end = min(end, duration)
        if end - start < 0.05:
            end = min(start + 0.05, duration)
        if end <= start:
            continue

        clip = _make_text(w["word"], font_path, font_size, color, stroke_color, stroke_width)
        if clip.w > width - 40:  # 아주 긴 단어 방어: 화면 폭에 맞게 축소
            shrunk = max(30, int(font_size * (width - 80) / clip.w))
            clip = _make_text(w["word"], font_path, shrunk, color, stroke_color, stroke_width)
        clips.append(
            clip.with_start(start).with_end(end).with_position(("center", y))
        )
    return clips


def _make_text(text: str, font_path: Path, font_size: int, color: str,
               stroke_color: str, stroke_width: int) -> TextClip:
    # margin: stroke가 글자 상자 밖으로 잘리지 않게 여유 확보 (MoviePy 2.x)
    pad = stroke_width * 3 + 12
    return TextClip(
        text=text,
        font=str(font_path),
        font_size=font_size,
        color=color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        margin=(pad, pad),
    )
