"""소싱 영상 합성(⑤) — 선택한 홍보 틱톡 클립을 다운로드하고 9:16 세로로 이어붙인다.

흐름: ③에서 저장한 data/sources/promo/{product_hash}.json → 각 영상 다운로드(tikwm 어댑터)
      → (④ 구간 지정이 있으면 그 구간만) 1080x1920로 cover-fit 크롭·리사이즈해 이어붙이고
      **원음 제거**('크게 재가공' 기본, SSOT §6·저작권 완화). 이후 파이프라인이 이 무음 영상 위에
      한국어 나레이션(TTS) + 카라오케 자막을 얹는다.

moviepy(v2) 렌더는 GitHub Actions에서 실행·프레임 검증한다(로컬에 moviepy/ffmpeg 없음).
선택 로드·다운로드 오케스트레이션은 어댑터 주입으로 네트워크 없이 단위 테스트한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.sourcing.base import get_adapter
from src.sourcing.models import SOURCES_DIR, SourceVideo

W, H, FPS = 1080, 1920, 30   # 9:16 세로 캔버스(기존 render.py와 동일)


def promo_path(product_hash: str, base_dir: Path | None = None) -> Path:
    return (base_dir or SOURCES_DIR) / "promo" / f"{product_hash}.json"


def load_promo_selection(product_hash: str, base_dir: Path | None = None) -> list:
    """③에서 저장한 홍보영상 선택 → SourceVideo 리스트(선택 순서 보존). 없으면 []."""
    p = promo_path(product_hash, base_dir)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return [SourceVideo.from_dict(v) for v in (data.get("videos") or [])]


def download_clips(videos: list, dest_dir, adapter=None) -> list:
    """선택 영상들을 다운로드 → [(SourceVideo, Path)] (실패 영상은 건너뜀). 어댑터 주입 가능(테스트)."""
    ad = adapter or get_adapter("tiktok_tikwm")
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for sv in videos:
        try:
            path = ad.download(sv, dest_dir)
        except Exception as e:
            print(f"[compose] 다운로드 예외({sv.source_url}): {type(e).__name__}: {str(e)[:120]}")
            path = None
        if path:
            out.append((sv, Path(path)))
        else:
            print(f"[compose] 다운로드 실패 건너뜀: {sv.source_url}")
    return out


# ── moviepy(v2) 합성 — GitHub Actions에서 실행·프레임 검증 ─────────────────────
def _fit_vertical(clip, width: int = W, height: int = H):
    """클립을 9:16 캔버스에 cover-fit(중앙 크롭). render.py와 동일 기법(resized→cropped)."""
    cw, ch = clip.size
    scale = max(width / cw, height / ch)
    clip = clip.resized(scale)
    return clip.cropped(width=width, height=height, x_center=clip.w / 2, y_center=clip.h / 2)


def _clip_parts(path, segments, width, height) -> list:
    """한 클립을 원음 제거 + (구간 있으면 그 구간만) 9:16로 변환. moviepy 필요(CI)."""
    from moviepy import VideoFileClip
    base = VideoFileClip(str(path)).without_audio()
    spans = (segments or {}).get(str(path)) or [(0.0, None)]
    parts = []
    for (s, e) in spans:
        sub = base.subclipped(s, e) if e is not None else base.subclipped(s)
        parts.append(_fit_vertical(sub, width, height))
    return parts


def stitch_vertical(clip_paths: list, out_path, segments: dict | None = None,
                    width: int = W, height: int = H, fps: int = FPS):
    """클립들을 원음 제거 + 9:16로 이어붙여 **무음 mp4** 생성. moviepy(CI에서 실행).

    segments: {clip_path: [(start,end), ...]} — ④에서 지정한 구간. 없으면 각 클립 전체.
    나레이션·카라오케 자막은 이후 단계에서 이 무음 영상 위에 얹는다(크게 재가공 원칙).
    """
    from moviepy import concatenate_videoclips
    parts = []
    for cp in clip_paths:
        parts.extend(_clip_parts(cp, segments, width, height))
    if not parts:
        raise RuntimeError("합성할 클립이 없습니다(다운로드 실패?)")
    final = concatenate_videoclips(parts, method="compose").with_fps(fps)
    out_path = Path(out_path)
    final.write_videofile(str(out_path), fps=fps, codec="libx264", audio=False,
                          ffmpeg_params=["-pix_fmt", "yuv420p"])
    return out_path
