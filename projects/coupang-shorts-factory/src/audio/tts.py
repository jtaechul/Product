"""M4. TTS(문자→음성) — 멀티 프로바이더 추상화.

특정 업체 고정 금지: config/settings.yaml 의 tts.provider 값으로 선택한다.
  - elevenlabs : with-timestamps 엔드포인트로 오디오 + 문자 타임스탬프 동시 수신
  - typecast   : 오디오만 수신 (Typecast 공식 SDK 기준 POST /v1/text-to-speech,
                 응답 = 원시 오디오 바이트) → faster-whisper 폴백으로 단어 타임스탬프 생성
  - clova      : 네이버클라우드 CLOVA Voice Premium, 오디오만 수신 → 폴백
  - mock       : API 키 없이 렌더 검증용(단어별 비프음 + 합성 타임스탬프)
  - auto       : 등록된 키를 elevenlabs → typecast → clova 순으로 감지해 자동 선택

공통 계약: 어느 프로바이더든 최종 산출은 job 폴더의
  audio.mp3 + timestamps.json([{"word","start","end"}] 리스트, 스펙 §M5)
로 동일하다. 타임스탬프를 못 주는 프로바이더는 align_fallback(faster-whisper)이
자동 실행된다.

API 키는 GitHub Actions Secrets 환경변수로만 주입한다 (코드 하드코딩 금지):
  SHORTS_ELEVENLABS_API_KEY, SHORTS_TYPECAST_API_KEY,
  SHORTS_CLOVA_CLIENT_ID, SHORTS_CLOVA_CLIENT_SECRET
"""

from __future__ import annotations

import base64
import json
import math
import os
import struct
import subprocess
import wave
from dataclasses import dataclass, field
from pathlib import Path

import requests

from src.audio.align_fallback import distribute_by_chars

PROVIDER_ORDER = ["elevenlabs", "typecast", "clova"]

ENV_KEYS = {
    "elevenlabs": ["SHORTS_ELEVENLABS_API_KEY"],
    "typecast": ["SHORTS_TYPECAST_API_KEY"],
    "clova": ["SHORTS_CLOVA_CLIENT_ID", "SHORTS_CLOVA_CLIENT_SECRET"],
}


class TTSError(RuntimeError):
    pass


@dataclass
class TTSOutput:
    audio_bytes: bytes
    audio_ext: str                      # "mp3" | "wav"
    words: list | None                  # [{"word","start","end"}] 또는 None(폴백 필요)
    meta: dict = field(default_factory=dict)


def detect_available() -> dict:
    """등록된 시크릿(환경변수) 기준 사용 가능 프로바이더 감지. 값은 절대 로그에 남기지 않는다."""
    return {
        name: all(os.environ.get(k, "").strip() for k in keys)
        for name, keys in ENV_KEYS.items()
    }


def resolve_provider(requested: str) -> str:
    requested = (requested or "auto").strip().lower()
    if requested == "mock":
        return "mock"
    avail = detect_available()
    if requested in ENV_KEYS:
        if not avail[requested]:
            missing = ", ".join(ENV_KEYS[requested])
            raise TTSError(
                f"프로바이더 '{requested}'가 지정됐지만 시크릿({missing})이 비어 있습니다. "
                f"GitHub 저장소 Settings → Secrets and variables → Actions 에 등록하세요."
            )
        return requested
    if requested != "auto":
        raise TTSError(f"알 수 없는 tts.provider 값: {requested}")
    for name in PROVIDER_ORDER:
        if avail[name]:
            return name
    raise TTSError(
        "사용 가능한 TTS API 키가 하나도 없습니다. 다음 중 하나 이상을 GitHub 저장소 "
        "Settings → Secrets and variables → Actions 에 등록한 뒤 다시 실행하세요: "
        "SHORTS_ELEVENLABS_API_KEY / SHORTS_TYPECAST_API_KEY / "
        "SHORTS_CLOVA_CLIENT_ID + SHORTS_CLOVA_CLIENT_SECRET "
        "(키 없이 렌더만 검증하려면 provider를 mock 으로 실행)"
    )


# ---------------------------------------------------------------- providers

def _synth_elevenlabs(text: str, cfg: dict) -> TTSOutput:
    """ElevenLabs with-timestamps: 오디오와 문자 타임스탬프를 한 번의 호출로 수신.

    참고: https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps
    """
    api_key = os.environ["SHORTS_ELEVENLABS_API_KEY"].strip()
    voice_id = cfg.get("voice_id") or "21m00Tcm4TlvDq8ikWAM"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
    params = {"output_format": cfg.get("output_format", "mp3_44100_128")}
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    body = {"text": text, "model_id": cfg.get("model_id", "eleven_multilingual_v2")}
    voice_settings = cfg.get("voice_settings") or {}
    if voice_settings:
        body["voice_settings"] = voice_settings

    resp = requests.post(url, params=params, headers=headers, json=body, timeout=180)
    if resp.status_code >= 400 and "voice_settings" in body:
        # 일부 모델은 voice_settings(예: speed) 미지원 → 기본 설정으로 1회 재시도
        body.pop("voice_settings")
        resp = requests.post(url, params=params, headers=headers, json=body, timeout=180)
    if resp.status_code >= 400:
        raise TTSError(f"ElevenLabs 오류 HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    audio = base64.b64decode(data["audio_base64"])
    alignment = data.get("alignment") or data.get("normalized_alignment")
    words = _chars_to_words(alignment) if alignment else None
    return TTSOutput(audio, "mp3", words, {"voice_id": voice_id, "model_id": body["model_id"]})


def _chars_to_words(alignment: dict) -> list:
    """문자 단위 타임스탬프 → 공백 경계 기준 단어 단위로 병합."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words, buf, w_start, w_end = [], "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                words.append({"word": buf, "start": round(w_start, 3), "end": round(w_end, 3)})
                buf = ""
            continue
        if not buf:
            w_start = s
        buf += ch
        w_end = e
    if buf:
        words.append({"word": buf, "start": round(w_start, 3), "end": round(w_end, 3)})
    return words


def _synth_typecast(text: str, cfg: dict) -> TTSOutput:
    """Typecast: POST /v1/text-to-speech — 응답은 원시 오디오 바이트(오디오만 수신 가정).

    공식 SDK(neosapience/typecast-sdk, typecast-python) 기준 구현.
    TODO(Phase 1+): /v1/text-to-speech/with-timestamps 로 전환하면 whisper 폴백 없이
    base64 오디오 + 정렬 타임스탬프를 직접 받을 수 있음(비용·시간 절감).
    """
    api_key = os.environ["SHORTS_TYPECAST_API_KEY"].strip()
    headers = {"X-API-KEY": api_key}
    voice_id = (cfg.get("voice_id") or "").strip()
    model = cfg.get("model", "ssfm-v30")
    if not voice_id:
        voice_id = _typecast_pick_voice(headers, model, cfg.get("language", "kor"))
    body = {
        "voice_id": voice_id,
        "text": text,
        "model": model,
        "language": cfg.get("language", "kor"),
        "output": {
            "volume": 100,
            "audio_tempo": float(cfg.get("audio_tempo", 1.0)),
            "audio_format": "mp3",
        },
    }
    resp = requests.post(
        "https://api.typecast.ai/v1/text-to-speech", json=body, headers=headers, timeout=180
    )
    if resp.status_code >= 400:
        raise TTSError(f"Typecast 오류 HTTP {resp.status_code}: {resp.text[:300]}")
    ctype = resp.headers.get("Content-Type", "")
    if "json" in ctype:
        # 방어적 처리: 혹시 JSON(base64) 형식으로 응답하는 변형이 있으면 파싱 시도
        data = resp.json()
        audio = base64.b64decode(data["audio"])
        fmt = data.get("audio_format", "mp3")
    else:
        audio = resp.content
        fmt = "mp3" if "mpeg" in ctype or "mp3" in ctype else "wav"
    return TTSOutput(audio, fmt, None, {"voice_id": voice_id, "model": model})


def _typecast_pick_voice(headers: dict, model: str, language: str) -> str:
    """voice_id 미지정 시 /v1/voices 목록에서 자동 선택(한국어 우선)."""
    resp = requests.get(
        "https://api.typecast.ai/v1/voices", params={"model": model}, headers=headers, timeout=60
    )
    if resp.status_code >= 400:
        raise TTSError(
            f"Typecast 보이스 목록 조회 실패 HTTP {resp.status_code}: {resp.text[:300]} — "
            f"config/settings.yaml 의 tts.typecast.voice_id 를 직접 지정하세요 "
            f"(https://typecast.ai/developers/api/voices)"
        )
    voices = resp.json()
    if isinstance(voices, dict):
        voices = voices.get("voices") or voices.get("result") or []
    if not voices:
        raise TTSError("Typecast 보이스 목록이 비어 있습니다. voice_id를 직접 지정하세요.")
    lang = (language or "").lower()
    pick = next(
        (v for v in voices if lang and lang in json.dumps(v, ensure_ascii=False).lower()),
        voices[0],
    )
    vid = pick.get("voice_id") or pick.get("id")
    if not vid:
        raise TTSError(f"Typecast 보이스 응답에서 voice_id를 찾지 못했습니다: {str(pick)[:200]}")
    print(f"[tts] typecast voice 자동 선택: {vid} ({pick.get('voice_name') or pick.get('name') or '?'})")
    return vid


def _synth_clova(text: str, cfg: dict) -> TTSOutput:
    """네이버클라우드 CLOVA Voice Premium — 오디오만 수신.

    참고: https://api.ncloud-docs.com/docs/ai-naver-clovavoice-ttspremium
    (application/x-www-form-urlencoded, speed는 -5(빠름)~5(느림) 정수)
    """
    client_id = os.environ["SHORTS_CLOVA_CLIENT_ID"].strip()
    client_secret = os.environ["SHORTS_CLOVA_CLIENT_SECRET"].strip()
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    payload = {
        "speaker": cfg.get("speaker", "nara"),
        "text": text,
        "volume": str(int(cfg.get("volume", 0))),
        "speed": str(int(cfg.get("speed", 0))),
        "pitch": str(int(cfg.get("pitch", 0))),
        "format": cfg.get("format", "mp3"),
    }
    resp = requests.post(
        "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
        headers=headers, data=payload, timeout=180,
    )
    ctype = resp.headers.get("Content-Type", "")
    if resp.status_code >= 400 or "json" in ctype:
        raise TTSError(f"CLOVA 오류 HTTP {resp.status_code}: {resp.text[:300]}")
    return TTSOutput(resp.content, payload["format"], None, {"speaker": payload["speaker"]})


def _synth_mock(text: str, cfg: dict) -> TTSOutput:
    """API 키 없이 M6 렌더를 검증하기 위한 목업: 단어별 비프음 + 정확한 타임스탬프."""
    sr = 44100
    words = text.split()
    segments, timeline = [], []
    t = 0.2
    for i, w in enumerate(words):
        dur = min(0.6, 0.16 + 0.055 * len(w))
        gap = 0.09
        freq = 420 + (i % 7) * 40
        n = int(sr * dur)
        seg = bytearray()
        for j in range(n):
            envelope = min(1.0, j / (sr * 0.02), (n - j) / (sr * 0.05))
            val = int(9000 * envelope * math.sin(2 * math.pi * freq * j / sr))
            seg += struct.pack("<h", val)
        segments.append((int(sr * t) * 2, bytes(seg)))
        timeline.append({"word": w, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur + gap
    total_bytes = int(sr * (t + 0.3)) * 2
    pcm = bytearray(total_bytes)
    for offset, seg in segments:
        pcm[offset:offset + len(seg)] = seg

    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(pcm))
    return TTSOutput(buf.getvalue(), "wav", timeline, {"note": "mock beep audio"})


_SYNTH = {
    "elevenlabs": _synth_elevenlabs,
    "typecast": _synth_typecast,
    "clova": _synth_clova,
    "mock": _synth_mock,
}


# ---------------------------------------------------------------- orchestration

def synthesize_to_files(text: str, job_dir: Path, tts_settings: dict,
                        whisper_settings: dict | None = None) -> dict:
    """대본 텍스트 → job_dir/audio.mp3 + job_dir/timestamps.json (공통 계약).

    반환 meta: {provider, timestamps_source, audio_path, timestamps_path, words}
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    provider = resolve_provider(tts_settings.get("provider", "auto"))
    avail = detect_available()
    detected = [n for n, ok in avail.items() if ok]
    print(f"[tts] 감지된 API 키(이름만): {detected or '없음'} → 선택된 프로바이더: {provider}")

    out = _SYNTH[provider](text, tts_settings.get(provider, {}) or {})

    audio_path = job_dir / "audio.mp3"
    if out.audio_ext == "mp3":
        audio_path.write_bytes(out.audio_bytes)
    else:
        raw = job_dir / f"_tts_raw.{out.audio_ext}"
        raw.write_bytes(out.audio_bytes)
        _to_mp3(raw, audio_path)
        raw.unlink(missing_ok=True)

    words = out.words
    source = "tts"
    if words is None:
        from src.audio import align_fallback  # 무거운 의존성(faster-whisper)은 필요할 때만
        ws = whisper_settings or {}
        print(f"[tts] '{provider}'는 타임스탬프 미제공 → faster-whisper 폴백 실행 "
              f"(model={ws.get('model', 'small')})")
        words = align_fallback.align(audio_path, text,
                                     model_size=ws.get("model", "small"),
                                     compute_type=ws.get("compute_type", "int8"))
        source = "faster-whisper"

    # 공통 계약: timestamps.json 의 word 나열은 대본 text.split() 과 1:1 로 맞춘다
    script_words = text.split()
    if [w["word"] for w in words] != script_words:
        words = distribute_by_chars(script_words, words)

    timestamps_path = job_dir / "timestamps.json"
    timestamps_path.write_text(json.dumps(words, ensure_ascii=False, indent=1), encoding="utf-8")
    (job_dir / "tts_meta.json").write_text(json.dumps({
        "provider": provider, "timestamps_source": source, **out.meta,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"provider": provider, "timestamps_source": source,
            "audio_path": audio_path, "timestamps_path": timestamps_path, "words": words}


def _to_mp3(src: Path, dst: Path) -> None:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-codec:a", "libmp3lame", "-b:a", "128k", str(dst)],
        check=True, capture_output=True,
    )
