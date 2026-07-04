"""audio — 심해 앰비언트 사운드 레이어링 (CLAUDE.md 오디오 규칙: 무음 출력 금지).

MVP 앰비언트: FFmpeg 합성(브라운 노이즈 + 로우패스 + 페이드) = 자체 생성물이라 라이선스 무결.
카테고리가 ambient_audio_spec()으로 색·컷오프·볼륨을 지정한다.
로열티프리 외부 음원 도입 시 이 모듈의 소스만 교체하면 된다 (spec TBD #4).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.core.contracts import PipelineError

_DEFAULT_SPEC = {
    "noise_color": "brown",     # 저주파 웅웅거림 (심해 수압/해류 느낌)
    "lowpass_hz": 320,          # 고음 제거 → 깊은 물속 톤
    "volume": 0.9,
    "fade_s": 1.5,
}


def add_ambient(video_path: str, work_dir: str, duration_s: float, spec: dict | None = None) -> str:
    """무음 영상에 합성 앰비언트를 입혀 work/with_audio.mp4 반환."""
    s = {**_DEFAULT_SPEC, **(spec or {})}
    out_path = Path(work_dir) / "with_audio.mp4"

    fade_out_st = max(0.0, duration_s - s["fade_s"])
    af = (
        f"lowpass=f={s['lowpass_hz']},"
        f"afade=t=in:st=0:d={s['fade_s']},afade=t=out:st={fade_out_st}:d={s['fade_s']},"
        f"volume={s['volume']}"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-f", "lavfi", "-i",
        f"anoisesrc=color={s['noise_color']}:amplitude=0.55:duration={duration_s}:sample_rate=44100",
        "-af", af,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PipelineError("audio", f"앰비언트 합성 실패: {proc.stderr[-500:]}")
    return str(out_path)
