"""endcard — 시리즈 엔드카드 (재방문·팔로우 유도 + 리빌 재확인).

어두운 배경 카드: 시리즈명·회차 + 종명 리빌 + 킬러팩트 + 팔로우 문구 + 워터마크.
어둡게 끝나므로 콜드오픈(어둠 시작)과 루프 재생이 자연스럽게 이어진다.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from src.core.contracts import CaptionData, PipelineError
from src.core.overlay import _font, _text_with_stroke, _wrap
from src.core.visualization.base import CLIP_FPS, CLIP_H, CLIP_W

ENDCARD_DURATION_S = 2.0


def _render_png(caption: CaptionData, series_title: str, episode: int,
                watermark: str, out_path: str) -> str:
    img = Image.new("RGB", (CLIP_W, CLIP_H), (3, 8, 16))  # 심해 어둠 톤
    d = ImageDraw.Draw(img)

    # 미묘한 하단 청록 그라디언트 (완전 검정 화면 방지 — 송출 시 '끊김'으로 오해 방지)
    for y in range(CLIP_H // 2, CLIP_H):
        t = (y - CLIP_H // 2) / (CLIP_H // 2)
        d.line([(0, y), (CLIP_W, y)], fill=(3 + int(4 * t), 8 + int(10 * t), 16 + int(14 * t)))

    cx = CLIP_W // 2
    # 시리즈명 + 회차
    _text_with_stroke(d, (cx, 300), series_title, _font(44), fill=(160, 210, 230), anchor="ma")
    _text_with_stroke(d, (cx, 370), f"#{episode}", _font(76), fill=(255, 255, 255), anchor="ma")

    # 종명 리빌
    y = 560
    for line in _wrap(d, caption.reveal_name or "", _font(54), CLIP_W - 120):
        _text_with_stroke(d, (cx, y), line, _font(54), fill=(255, 230, 160), anchor="ma")
        y += 70

    # 킬러팩트
    y += 20
    for line in _wrap(d, caption.reveal_fact or "", _font(38), CLIP_W - 140):
        _text_with_stroke(d, (cx, y), line, _font(38), fill=(210, 240, 255), anchor="ma")
        y += 52

    # 팔로우 유도 (재방문 훅)
    _text_with_stroke(d, (cx, CLIP_H - 260), "팔로우하고 다음 심해 생물 만나기", _font(36),
                      fill=(255, 255, 255), anchor="ma")
    # 워터마크 (상시 규칙 유지)
    _text_with_stroke(d, (CLIP_W - 40, 36), watermark, _font(24),
                      fill=(255, 255, 255, 210), anchor="ra")

    img.save(out_path)
    return out_path


def build_endcard_video(caption: CaptionData, series_title: str, episode: int,
                        watermark: str, work_dir: str) -> str:
    """엔드카드 PNG → 페이드인 무음 비디오 (규격 동일: 720x1280@25)."""
    work = Path(work_dir)
    png = _render_png(caption, series_title, episode, watermark, str(work / "endcard.png"))
    out = work / "endcard.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-loop", "1", "-i", png,
         "-t", str(ENDCARD_DURATION_S), "-r", str(CLIP_FPS),
         "-vf", f"scale={CLIP_W}:{CLIP_H},setsar=1,fade=t=in:st=0:d=0.4",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-an", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"엔드카드 생성 실패: {proc.stderr[-400:]}")
    return str(out)


def append_endcard(main_video: str, endcard_video: str, work_dir: str) -> str:
    """본편(오버레이 완료) 뒤에 엔드카드를 이어붙임 (video-only concat 재인코딩)."""
    out = Path(work_dir) / "with_endcard.mp4"
    fc = (f"[0:v]scale={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1[v0];"
          f"[1:v]scale={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1[v1];"
          f"[v0][v1]concat=n=2:v=1:a=0[outv]")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", main_video, "-i", endcard_video,
         "-filter_complex", fc, "-map", "[outv]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"엔드카드 결합 실패: {proc.stderr[-400:]}")
    return str(out)
