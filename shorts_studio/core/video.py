"""video — FFmpeg 미디어 합성.

흐름: 씬 영상 정규화(9:16 크롭 + 길이 맞춤) → 이어붙이기 → 나레이션 입히기
      → 가라오케 자막 하드코딩(번인) → 최종 MP4.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

PRESETS = {
    "720x1280 (권장 · 빠름)": (720, 1280),
    "1080x1920 (고화질 · 느림)": (1080, 1920),
}

# 한국어 자막용 폰트 후보 — 모두 상업적 이용 무료(SIL OFL)
_FONT_CANDIDATES = [
    ("NanumGothic", "/usr/share/fonts/truetype/nanum"),
    ("NanumBarunGothic", "/usr/share/fonts/truetype/nanum"),
    ("Noto Sans CJK KR", "/usr/share/fonts/opentype/noto"),
    ("NanumGothic", str(Path(__file__).resolve().parent.parent / "assets" / "fonts")),
]


class RenderError(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    for exe in ("ffmpeg", "ffprobe"):
        if not shutil.which(exe):
            raise RenderError(
                f"{exe}를 찾을 수 없습니다. Streamlit Cloud라면 packages.txt에 ffmpeg가 있는지, "
                "로컬이라면 ffmpeg가 설치됐는지 확인하세요."
            )


def pick_font() -> tuple[str, str]:
    """설치된 한국어 폰트 이름과 폰트 폴더를 고른다."""
    for name, d in _FONT_CANDIDATES:
        p = Path(d)
        if p.is_dir() and any(p.glob("*.tt[fc]")):
            return name, str(p)
    return "NanumGothic", "/usr/share/fonts/truetype/nanum"


def _run(cmd: list[str], what: str) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-12:])
        raise RenderError(f"{what} 실패\n{tail}")


def probe_duration(path: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RenderError(f"영상 정보를 읽지 못했습니다: {Path(path).name}")
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception as e:  # noqa: BLE001
        raise RenderError(f"영상 길이를 확인하지 못했습니다: {Path(path).name}") from e


def normalize_scene(src: str, target_dur: float, out: str, *,
                    width: int, height: int, fps: int = 30) -> str:
    """씬 영상을 9:16으로 크롭·스케일하고 길이를 target_dur에 정확히 맞춘다.

    짧으면 마지막 프레임을 정지(freeze)시켜 늘리고, 길면 잘라낸다.
    """
    src_dur = probe_duration(src)
    pad = max(0.0, target_dur - src_dur) + 1.0   # 여유분 — 뒤에서 -t로 정확히 자름
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps},"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f}"
    )
    _run([
        "ffmpeg", "-y", "-i", src,
        "-vf", vf, "-an", "-t", f"{target_dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out,
    ], f"{Path(src).name} 규격 변환")
    return out


def build_narration_track(scene_mp3s: list[str], scene_durs: list[float],
                          work_dir: str) -> str:
    """씬별 mp3를 각 씬 길이에 맞춰 무음 패딩 후 하나로 이어붙인다."""
    work = Path(work_dir)
    parts = []
    for i, (mp3, dur) in enumerate(zip(scene_mp3s, scene_durs)):
        wav = str(work / f"narr_{i + 1:02d}.wav")
        _run([
            "ffmpeg", "-y", "-i", mp3,
            "-af", "apad", "-t", f"{dur:.3f}",
            "-ar", "48000", "-ac", "2", wav,
        ], f"{i + 1}번 씬 오디오 정렬")
        parts.append(wav)

    listing = work / "audio_list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts), encoding="utf-8")
    out = str(work / "narration_full.wav")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
          "-c", "copy", out], "나레이션 이어붙이기")
    return out


def concat_videos(scene_mp4s: list[str], work_dir: str) -> str:
    """정규화된 씬 영상들을 순서대로 이어붙인다(동일 규격이므로 무손실 복사)."""
    listing = Path(work_dir) / "video_list.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in scene_mp4s), encoding="utf-8")
    out = str(Path(work_dir) / "joined.mp4")
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
          "-c", "copy", out], "영상 이어붙이기")
    return out


def finalize(video: str, audio: str, ass: str, out: str, *,
             width: int, fonts_dir: str) -> str:
    """나레이션을 입히고 가라오케 자막을 태워 최종 MP4를 만든다."""
    ass_esc = ass.replace("\\", "/").replace(":", r"\:")
    fonts_esc = fonts_dir.replace("\\", "/").replace(":", r"\:")
    _run([
        "ffmpeg", "-y", "-i", video, "-i", audio,
        "-vf", f"ass='{ass_esc}':fontsdir='{fonts_esc}'",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "20" if width <= 720 else "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-shortest",
        "-movflags", "+faststart", out,
    ], "최종 렌더링(자막 번인)")
    return out
