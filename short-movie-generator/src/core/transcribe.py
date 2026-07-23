"""음성 전사(faster-whisper) — 첨부 영상의 '원본 음성'을 문장별 타임스탬프와 함께 텍스트로 뽑는다.

용도(운영자 확정): 롱폼 '더빙형' 나레이션의 1단계. 원본 화자가 말하는 내용을 그 발화 시각에 맞춰
일본어로 옮기기 위해, 먼저 **무엇을 언제 말했는지**를 정확히 알아야 한다. silencedetect(소리 크기)로는
연속 발화·배경음이 있으면 실패하므로, ASR(강제정렬)로 문장 단위 [start,end]를 얻는다.

비용/원리: faster-whisper는 무료·오프라인·CPU. 제미나이 오디오는 저지연 최적화라 타임스탬프가 약해
전사·타이밍에는 부적합(번역만 제미나이). faster-whisper 미설치/무음/음악만/실패 시 None을 돌려주고,
호출부는 기존 비전 기반 나레이션으로 안전 폴백한다(발행 불정지)."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("shorts")

# CPU에서 5분 영상 ~1~2분. 정확도/속도 균형(더 정밀하면 'small'). 워크플로에서 환경변수로 덮어쓸 수 있음.
_DEFAULT_MODEL = "base"


def _extract_audio(video: str, wav: str) -> bool:
    """원본에서 16kHz 모노 WAV 추출(Whisper 입력 규격). 오디오 스트림 없으면 실패."""
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video,
                            "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", wav],
                           capture_output=True, text=True, timeout=600)
        return r.returncode == 0 and Path(wav).exists() and Path(wav).stat().st_size > 2000
    except Exception:  # noqa: BLE001
        return False


def has_speech_track(video: str) -> bool:
    """오디오 스트림 존재 여부(빠른 사전 판정 — 무음 영상은 전사 자체를 건너뛴다)."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                              "-show_entries", "stream=codec_type", "-of", "csv=p=0", video],
                             capture_output=True, text=True, timeout=30).stdout
        return "audio" in out
    except Exception:  # noqa: BLE001
        return False


def transcribe(video: str, work: str, model_size: str = "") -> dict | None:
    """원본 음성 → {"lang": 감지언어, "segments": [{"start","end","text"}]}. 실패 시 None.

    - faster-whisper 미설치 → None(호출부 폴백).
    - 오디오 없음/무음/음악만(발화 문장 0개) → None.
    - VAD 필터로 무음 구간을 제외해 타임스탬프 정확도를 높인다."""
    import os
    if not has_speech_track(video):
        log.info("[transcribe] 오디오 스트림 없음 → 전사 생략")
        return None
    try:
        from faster_whisper import WhisperModel
    except Exception:  # noqa: BLE001
        log.info("[transcribe] faster-whisper 미설치 → 전사 생략(비전 폴백)")
        return None
    wd = Path(work); wd.mkdir(parents=True, exist_ok=True)
    wav = str(wd / "audio16k.wav")
    if not _extract_audio(video, wav):
        log.info("[transcribe] 오디오 추출 실패 → 전사 생략")
        return None
    size = (model_size or os.environ.get("WHISPER_MODEL") or _DEFAULT_MODEL).strip()
    try:
        model = WhisperModel(size, device="cpu", compute_type="int8")
        segments, info = model.transcribe(wav, vad_filter=True, word_timestamps=False)
        out: list[dict] = []
        for s in segments:                       # generator — 순회 시 실제 추론 실행
            txt = (getattr(s, "text", "") or "").strip()
            if txt:
                out.append({"start": float(s.start), "end": float(s.end), "text": txt})
        if not out:
            log.info("[transcribe] 발화 문장 없음(무음/음악만) → None")
            return None
        lang = getattr(info, "language", "") or ""
        log.info("[transcribe] 전사 완료: %d문장 · 언어=%s · 모델=%s", len(out), lang, size)
        return {"lang": lang, "segments": out}
    except Exception as e:  # noqa: BLE001
        log.info("[transcribe] 전사 실패: %s", e)
        return None
