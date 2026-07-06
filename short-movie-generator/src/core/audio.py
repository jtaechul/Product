"""audio — 심해 앰비언트 + SF HUD 효과음 레이어링 (CLAUDE.md 오디오 규칙: 무음 출력 금지).

전부 FFmpeg 합성(브라운 노이즈 + 톤 이벤트)이라 자체 생성물 = 라이선스 무결.
카테고리가 ambient_audio_spec()으로 색·컷오프·볼륨·연출 플래그를 지정한다.

레이어:
  1) 앰비언트: 브라운 노이즈 + 로우패스 + 페이드 (심해 저주파)
  2) 리빌 악센트(reveal_accent): 리빌 직전 서브베이스 스웰 + 리빌 순간 스팅
  3) HUD 효과음(hud_sfx): 스캔 구간 소나 핑(주기) + 타이핑 클릭(훅·리빌) + 리빌 확정 차임
로열티프리 외부 음원 도입 시 이 모듈의 소스만 교체하면 된다 (spec TBD #4).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.core.contracts import PipelineError

_DEFAULT_SPEC = {
    "noise_color": "brown",     # 저주파 웅웅거림 (심해 수압/해류 느낌)
    "lowpass_hz": 320,          # 고음 제거 → 깊은 물속 톤
    "volume": 1.2,              # 수중 앰비언스 존재감 (↑ 사용자 요청)
    "fade_s": 1.5,
}


def add_narration(
    video_path: str,
    work_dir: str,
    duration_s: float,
    narration_path: str | None,
    spec: dict | None = None,
) -> str:
    """나레이션(주) + 낮은 심해 앰비언트(SFX)를 영상에 입힌다 (배경음악 없음).

    narrated_wildlife 전환용. narration_path 없으면 앰비언트만(add_ambient 위임).
    """
    if not narration_path or not Path(narration_path).exists():
        return add_ambient(video_path, work_dir, duration_s, spec)

    s = {**_DEFAULT_SPEC, **(spec or {})}
    out_path = Path(work_dir) / "with_audio.mp4"
    fade_out = max(0.0, duration_s - s["fade_s"])
    drone_on = bool(s.get("drone", True))     # 미세 저역 드론(음악 아님) — 긴장·몰입
    drone_vol = float(s.get("drone_volume", 0.16))
    # 앰비언트는 나레이션 밑에 낮게(0.45) 깔아 존재감만. BGM 없음.
    amb = (f"anoisesrc=color={s['noise_color']}:amplitude=0.4:duration={duration_s}:sample_rate=44100")
    # 저역 드론: 43Hz + 65Hz(5도) 지속음 + 느린 트레몰로 → 심해 긴장감(서브베이스)
    drone_src = (r"sin(2*PI*43*t)*0.6+sin(2*PI*64.5*t)*0.4")
    fc = (
        f"[1:a]lowpass=f={s['lowpass_hz']},volume=0.42,"
        f"afade=t=in:st=0:d={s['fade_s']},afade=t=out:st={fade_out:.2f}:d={s['fade_s']},"
        f"aformat=channel_layouts=mono[amb];"
        f"[2:a]adelay=300|300,volume=1.35,aformat=channel_layouts=mono[nar];"
    )
    inputs = ["-i", video_path, "-f", "lavfi", "-i", amb, "-i", narration_path]
    labels = "[amb][nar]"
    n = 2
    if drone_on:
        inputs += ["-f", "lavfi", "-i", f"aevalsrc={drone_src}:d={duration_s}:s=44100"]
        fc += (f"[3:a]tremolo=f=0.15:d=0.5,volume={drone_vol},"
               f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out:.2f}:d={s['fade_s']},"
               f"aformat=channel_layouts=mono[drn];")
        labels += "[drn]"
        n = 3
    fc += f"{labels}amix=inputs={n}:duration=first:normalize=0,alimiter=limit=0.9[aout]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs,
           "-filter_complex", fc, "-map", "0:v", "-map", "[aout]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", f"{duration_s:.3f}", str(out_path)]
    return _run(cmd, out_path)


def add_ambient(
    video_path: str,
    work_dir: str,
    duration_s: float,
    spec: dict | None = None,
    reveal_at_s: float | None = None,
    sfx_timeline: dict | None = None,
    photo_at_s: float | None = None,
) -> str:
    """무음 영상에 합성 앰비언트(+선택: 리빌 악센트·HUD 효과음)를 입혀 with_audio.mp4 반환.

    리빌 악센트(spec.reveal_accent=True && reveal_at_s>3):
    - 스웰: 리빌 2.5초 전부터 차오르는 40Hz 서브베이스 (긴장 상승)
    - 스팅: 리빌 순간 55Hz 저음 타격 1회 (정체 공개 강조)
    HUD 효과음(spec.hud_sfx=True && reveal_at_s>3):
    - 소나 핑: 스캔 구간(0~리빌) 1.15초 주기의 1180Hz 핑 (레이더 스윕 사운드)
    - 타이핑: 훅 등장 직후·리빌 순간 짧은 클릭 버스트 (터미널 타자감)
    - 확정 차임: 리빌 순간 상승 2음 (SPECIES IDENTIFIED 확정음)
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

    ready = reveal_at_s is not None and reveal_at_s > 3.0
    use_accent = bool(s.get("reveal_accent")) and ready
    use_sfx = bool(s.get("hud_sfx")) and ready
    bgm_path = s.get("bgm_path")
    use_bgm = bool(bgm_path and Path(bgm_path).exists())

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
           "-f", "lavfi", "-i",
           f"anoisesrc=color={s['noise_color']}:amplitude=0.55:duration={duration_s}:sample_rate=44100"]

    if not use_accent and not use_sfx and not use_bgm:
        cmd += ["-af", ambient_chain, "-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_path)]
        return _run(cmd, out_path)

    # 배경음악(BGM): 앰비언스 밑에 낮게 깔고 페이드. 무한 루프 후 duration까지 트림.
    # noise(1) 다음 입력으로 추가 → 항상 인덱스 2 (accent/sfx는 그 뒤).
    parts = [f"[1:a]{ambient_chain},aformat=channel_layouts=mono[amb]"]
    mix_labels = ["[amb]"]
    idx = 2  # 다음 입력 인덱스
    if use_bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm_path)]
        bgm_vol = float(s.get("bgm_volume", 0.5))
        bfo = max(0.0, duration_s - 2.0)
        parts.append(
            f"[{idx}:a]aformat=channel_layouts=mono,atrim=0:{duration_s},asetpts=PTS-STARTPTS,"
            f"volume={bgm_vol},afade=t=in:st=0:d=2,afade=t=out:st={bfo:.2f}:d=2[bgm]"
        )
        mix_labels.append("[bgm]")
        idx += 1

    if use_accent:
        swell = r"sin(2*PI*40*t)*pow(min(t/2.5\,1)\,2)*0.55"
        sting = "sin(2*PI*55*t)*(1-exp(-10*t))*exp(-2.2*t)*0.85"
        cmd += ["-f", "lavfi", "-i", f"aevalsrc={swell}:d=2.5:s=44100"]
        cmd += ["-f", "lavfi", "-i", f"aevalsrc={sting}:d=1.4:s=44100"]
        parts.append(f"[{idx}:a]adelay={int((reveal_at_s - 2.5) * 1000)}:all=1[swl]")
        parts.append(f"[{idx + 1}:a]adelay={int(reveal_at_s * 1000)}:all=1[stg]")
        mix_labels += ["[swl]", "[stg]"]
        idx += 2

    if use_sfx:
        scan_dur = max(0.5, sfx_timeline["scan_end"] if sfx_timeline else reveal_at_s)
        # 소나 핑: 1.15초 주기, 30% 구간만 발음, 지수 감쇠
        ping = r"sin(2*PI*1180*t)*exp(-24*mod(t\,1.15))*lt(mod(t\,1.15)\,0.30)*0.20"
        # 타이핑: ~17Hz 게이트된 고음 클릭(레트로 터미널) — 버스트 길이=화면 타이핑 길이
        typ = r"sin(2*PI*2300*t)*exp(-70*mod(t\,0.058))*lt(mod(t\,0.058)\,0.5)*0.11"
        # 확정 차임: 784Hz → 1175Hz 상승 2음
        chime = r"(sin(2*PI*784*t)*exp(-3.2*t)+sin(2*PI*1175*t)*exp(-3*max(t-0.13\,0))*gt(t\,0.13))*0.45"
        cmd += ["-f", "lavfi", "-i", f"aevalsrc={ping}:d={scan_dur:.2f}:s=44100"]
        parts.append(f"[{idx}:a]adelay=0:all=1[png]")
        mix_labels.append("[png]")
        idx += 1

        # 타이핑 버스트: 타임라인이 있으면 화면 타이핑과 정확히 동기(끝날 때까지 소리),
        # 없으면 기존 고정 2버스트로 폴백.
        bursts = sfx_timeline["typing"] if sfx_timeline else [
            (0.3, 1.4), (reveal_at_s + 0.2, 1.0),
        ]
        for k, (start, dur) in enumerate(bursts):
            cmd += ["-f", "lavfi", "-i", f"aevalsrc={typ}:d={max(0.2, dur):.2f}:s=44100"]
            parts.append(f"[{idx}:a]adelay={int(start * 1000)}:all=1[ty{k}]")
            mix_labels.append(f"[ty{k}]")
            idx += 1

        cmd += ["-f", "lavfi", "-i", f"aevalsrc={chime}:d=1.0:s=44100"]
        parts.append(f"[{idx}:a]adelay={int(reveal_at_s * 1000)}:all=1[chm]")
        mix_labels.append("[chm]")
        idx += 1

        # 근접 경보(실제 근접·인지 상황 한정): '쿵쿵' 저역 타격 2회 + 위급 경보음(비프)
        alert_at = sfx_timeline.get("alert") if sfx_timeline else None
        if alert_at is not None and alert_at > 0:
            thump = r"sin(2*PI*48*t)*(1-exp(-55*t))*exp(-4.8*t)*0.9"        # 단발 '쿵'
            alarm = r"sin(2*PI*720*t)*lt(mod(t\,0.5)\,0.22)*exp(-1.2*mod(t\,0.5))*0.15"  # 비프비프
            for k, off in enumerate((0.0, 0.42)):  # 쿵…쿵 (2회)
                cmd += ["-f", "lavfi", "-i", f"aevalsrc={thump}:d=0.9:s=44100"]
                parts.append(f"[{idx}:a]adelay={int((alert_at + off) * 1000)}:all=1[thm{k}]")
                mix_labels.append(f"[thm{k}]")
                idx += 1
            cmd += ["-f", "lavfi", "-i", f"aevalsrc={alarm}:d=1.5:s=44100"]
            parts.append(f"[{idx}:a]adelay={int(alert_at * 1000)}:all=1[alm]")
            mix_labels.append("[alm]")
            idx += 1

        # 실제 사진 '충격' 리빌 효과음: 저역 붐 + 서브 하모닉 + 트랜지언트 + 확정음
        if photo_at_s is not None and photo_at_s > 0:
            impact = (r"sin(2*PI*46*t)*(1-exp(-40*t))*exp(-3.2*t)*0.75"
                      r"+sin(2*PI*92*t)*exp(-6*t)*0.4"
                      r"+(sin(2*PI*2600*t)+sin(2*PI*1700*t))*exp(-60*t)*0.18"
                      r"+(sin(2*PI*880*t)*exp(-3.5*t)+sin(2*PI*1320*t)*exp(-3.5*max(t-0.12\,0))*gt(t\,0.12))*0.34")
            cmd += ["-f", "lavfi", "-i", f"aevalsrc={impact}:d=1.6:s=44100"]
            parts.append(f"[{idx}:a]adelay={int(photo_at_s * 1000)}:all=1[pho]")
            mix_labels.append("[pho]")
            idx += 1

    n = len(mix_labels)
    fc = ";".join(parts) + ";" + "".join(mix_labels) + \
        f"amix=inputs={n}:duration=first:normalize=0,alimiter=limit=0.891[aout]"
    cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(out_path)]
    return _run(cmd, out_path)


def _run(cmd: list[str], out_path: Path) -> str:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_path.exists():
        raise PipelineError("audio", f"앰비언트 합성 실패: {proc.stderr[-500:]}")
    return str(out_path)
