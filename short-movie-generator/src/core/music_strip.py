"""원본 영상 오디오에서 '상용 배경음악'을 제거하고 목소리(발화)만 남긴다 — 롱폼 저작권 대책.

배경(운영자 확정 · 실사고): NOAA 편집본의 배경음악은 NOAA가 라이선스한 상용 음원이라 퍼블릭도메인이
아니다 → 유튜브 Content ID '소유권 주장'이 걸려 그 영상의 광고 수익이 음악 권리자에게 간다.
→ 롱폼 제작 시 원본 오디오를 **보컬(목소리) / 반주(음악·효과음)** 로 분리(Demucs, 무료·오프라인)해
목소리만 남기고, 음악 자리는 우리가 보유한 자체 BGM(assets/audio/bgm)으로 채운다.

★순서 규칙(운영자 확정): 전사(음성→텍스트·자막)는 반드시 **음악 제거 전의 원본 오디오**로 먼저
수행한다(분리 과정에서 목소리가 열화될 수 있음). 이 모듈은 '믹스 직전'에만 호출된다.

안전(발행 불정지): demucs 미설치·오디오 없음·분리 실패 시 None → 호출부는 원본 오디오 그대로(현행).
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("shorts")

_TIMEOUT = 3600   # CPU 분리(htdemucs)는 5분 오디오에 수 분~십수 분


def available() -> bool:
    try:
        import demucs  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def _has_audio(video: str) -> bool:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                              "-show_entries", "stream=codec_type", "-of", "csv=p=0", video],
                             capture_output=True, text=True, timeout=30).stdout
        return "audio" in out
    except Exception:  # noqa: BLE001
        return False


def strip_music(video: str, work: str) -> str | None:
    """원본에서 목소리만 남긴 wav 경로를 반환(음악·반주 제거). 실패/불가 시 None(호출부 폴백).

    Demucs `--two-stems=vocals`: vocals(목소리) / no_vocals(음악+효과음) 분리 후 vocals 채택.
    주의: 반주 트랙에 섞인 현장 효과음도 함께 빠진다 — 그 공백은 호출부가 자체 BGM으로 채운다."""
    if not available():
        log.info("[music] demucs 미설치 → 음악 제거 생략(원본 오디오 사용)")
        return None
    if not _has_audio(video):
        return None
    wd = Path(work)
    wd.mkdir(parents=True, exist_ok=True)
    wav = wd / "orig.wav"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn",
                        "-ac", "2", "-ar", "44100", str(wav)], check=True, timeout=900)
    except Exception as e:  # noqa: BLE001
        log.info("[music] 오디오 추출 실패 → 생략: %s", e)
        return None
    try:
        r = subprocess.run(["python", "-m", "demucs.separate", "-n", "htdemucs",
                            "--two-stems", "vocals", "-o", str(wd / "sep"), str(wav)],
                           capture_output=True, text=True, timeout=_TIMEOUT)
        if r.returncode != 0:
            log.info("[music] demucs 분리 실패(%d): %s", r.returncode, (r.stderr or "")[-300:])
            return None
    except Exception as e:  # noqa: BLE001
        log.info("[music] demucs 실행 실패 → 생략: %s", e)
        return None
    voc = wd / "sep" / "htdemucs" / wav.stem / "vocals.wav"
    if voc.exists() and voc.stat().st_size > 10_000:
        log.info("[music] 원본 음악 제거 완료(목소리만 유지): %s", voc)
        return str(voc)
    log.info("[music] 분리 결과 없음 → 생략")
    return None


def pick_bgm(seed: str = "", base_dir: str = ".") -> str | None:
    """보유 자체 BGM(assets/audio/bgm) 중 롱폼용 한 곡을 결정론으로 선택(같은 소스=같은 곡).
    longform_* 우선, 없으면 아무 mp3. 없으면 None."""
    root = Path(base_dir) / "assets" / "audio" / "bgm"
    if not root.exists():
        root = Path(__file__).resolve().parents[2] / "assets" / "audio" / "bgm"
    cands = sorted(root.glob("longform_*.mp3")) or sorted(root.glob("*.mp3"))
    if not cands:
        return None
    idx = sum(ord(c) for c in (seed or "")) % len(cands)
    return str(cands[idx])
