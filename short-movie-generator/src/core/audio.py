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


def add_ambient(
    video_path: str,
    work_dir: str,
    duration_s: float,
    spec: dict | None = None,
    reveal_at_s: float | None = None,
) -> str:
    """무음 영상에 합성 앰비언트(+선택: 리빌 악센트)를 입혀 work/with_audio.mp4 반환.

    리빌 악센트(spec.reveal_accent=True && reveal_at_s 지정 시):
    - 스웰: 리빌 2.5초 전부터 차오르는 40Hz 서브베이스 (긴장 상승)
    - 스팅: 리빌 순간 55Hz 저음 타격 1회 (정체 공개 강조)
    전부 FFmpeg 합성 → 라이선스 무결.
    """
    s = {**_DEFAULT_SPEC, **(spec or {})}
    out_path = Path(work_dir) / "with_audio.mp4"

    fade_out_st = max(0.0, duration_s - s["fade_s"])
    ambient_chain = (
        f"lowpass=f={s['lowpass_hz']},"
        f"afade=t=in:st=0:d={s['fade_s']},afade=t=out:st={fade_out_st}:d={s['fade_s']},"
        f"volume={s['volume']}"
    )

    use_accent = bool(s.get("reveal_accent")) and reveal_at_s is not None and reveal_at_s > 3.0
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
           "-f", "lavfi", "-i",
           f"anoisesrc=color={s['noise_color']}:amplitude=0.55:duration={duration_s}:sample_rate=44100"]

    if use_accent:
        swell_start = reveal_at_s - 2.5
        # 스웰: 2.5초간 제곱 곡선으로 차오르는 40Hz / 스팅: 어택 후 지수 감쇠하는 55Hz
        # (lavfi 입력에서 콤마는 필터 구분자 → \, 로 이스케이프 필수)
        swell = r"sin(2*PI*40*t)*pow(min(t/2.5\,1)\,2)*0.55"
        sting = "sin(2*PI*55*t)*(1-exp(-10*t))*exp(-2.2*t)*0.85"
        cmd += [
            "-f", "lavfi", "-i", f"aevalsrc={swell}:d=2.5:s=44100",
            "-f", "lavfi", "-i", f"aevalsrc={sting}:d=1.4:s=44100",
        ]
        fc = (
            f"[1:a]{ambient_chain}[amb];"
            f"[2:a]adelay={int(swell_start*1000)}:all=1[swl];"
            f"[3:a]adelay={int(reveal_at_s*1000)}:all=1[stg];"
            f"[amb][swl][stg]amix=inputs=3:duration=first:normalize=0,"
            f"alimiter=limit=0.891[aout]"
        )
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += ["-af", ambient_chain, "-map", "0:v", "-map", "1:a"]

    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PipelineError("audio", f"앰비언트 합성 실패: {proc.stderr[-500:]}")
    return str(out_path)
