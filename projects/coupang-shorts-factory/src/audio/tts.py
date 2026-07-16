"""M4. TTS(문자→음성) — 멀티 프로바이더 추상화.

특정 업체 고정 금지: config/settings.yaml 의 tts.provider 값으로 선택한다.
  - elevenlabs : with-timestamps 엔드포인트로 오디오 + 문자 타임스탬프 동시 수신
  - gemini     : Gemini 2.5 TTS(generateContent, responseModalities=[AUDIO]) — 오디오만 수신
                 (→ faster-whisper 폴백). 대본 생성용 Gemini 키(GEMINI_API_KEY)를 재사용하고,
                 서버/클라우드 친화적이라 무료 소비자 TTS의 'UNUSUAL_ACTIVITY' 차단을 잘 안 겪는다.
                 화난 톤 등은 감정 프리셋이 아니라 style_prompt(자연어 지시)로 제어. (오디오 생성이지
                 유료 '영상' 생성이 아님 — 프로젝트 영상금지 규칙과 무관.)
  - typecast   : 오디오만 수신 (Typecast 공식 SDK 기준 POST /v1/text-to-speech,
                 응답 = 원시 오디오 바이트) → faster-whisper 폴백으로 단어 타임스탬프 생성
  - clova      : 네이버클라우드 CLOVA Voice Premium, 오디오만 수신 → 폴백
  - mock       : API 키 없이 렌더 검증용(단어별 비프음 + 합성 타임스탬프)
  - auto       : 등록된 키를 elevenlabs → gemini → typecast → clova 순으로 감지해 자동 선택

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

PROVIDER_ORDER = ["elevenlabs", "gemini", "typecast", "clova"]

ENV_KEYS = {
    "elevenlabs": ["SHORTS_ELEVENLABS_API_KEY"],
    "gemini": ["GEMINI_API_KEY"],   # 대본 생성용과 동일 시크릿(SHORTS_ 접두사 아님)
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
    # 감정 프리셋(ssfm 계열) — 화난 톤 등. normal/빈값이면 미적용(중립).
    preset = str(cfg.get("emotion_preset", "") or "").strip().lower()
    if preset and preset != "normal":
        body["prompt"] = {"emotion_preset": preset,
                          "emotion_intensity": float(cfg.get("emotion_intensity", 1.0))}
    resp = requests.post(
        "https://api.typecast.ai/v1/text-to-speech", json=body, headers=headers, timeout=180
    )
    if resp.status_code >= 400 and "prompt" in body:
        # 일부 모델·계정은 prompt(emotion) 미지원 → 감정 없이 1회 재시도(발화는 유지).
        print(f"[tts] Typecast prompt(emotion={preset}) 거부됨(HTTP {resp.status_code}) → 감정 없이 재시도")
        body.pop("prompt")
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


GEMINI_TTS_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _pcm_rate_from_mime(mime: str) -> int:
    """Gemini 오디오 mimeType(예: 'audio/L16;codec=pcm;rate=24000')에서 샘플레이트 추출."""
    import re
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else 24000


def _pcm_to_wav(pcm: bytes, rate: int, channels: int = 1, sampwidth: int = 2) -> bytes:
    """원시 16-bit PCM → WAV 컨테이너로 감싼다(파이프라인이 이후 mp3로 변환)."""
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _synth_gemini(text: str, cfg: dict) -> TTSOutput:
    """Gemini 2.5 TTS — POST generateContent(responseModalities=[AUDIO]) → 원시 PCM(base64).

    - 키: GEMINI_API_KEY(대본 생성용과 동일 시크릿 재사용).
    - 낭독 스타일(화난 톤 등)은 감정 프리셋이 아니라 style_prompt(자연어 지시)를 문장 앞에 붙여 제어.
    - 응답 PCM(16-bit mono, 보통 24kHz)을 WAV로 감싸 반환 → 타임스탬프는 whisper 폴백이 생성.
    ⚠️ 이는 오디오(음성) 생성이지 유료 '영상' 생성이 아니다(프로젝트 영상금지 규칙과 무관).
    """
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("SHORTS_GEMINI_API_KEY") or "").strip()
    if not key:
        raise TTSError("Gemini TTS 키가 없습니다 (GEMINI_API_KEY).")
    model = str(cfg.get("model", "gemini-2.5-flash-preview-tts")).strip()
    voice = str(cfg.get("voice") or "Kore").strip()
    style = str(cfg.get("style_prompt") or "").strip()
    # style_prompt를 앞에 붙여 '이 대사를 이런 톤으로 읽어라'로 지시한다(Gemini TTS 권장 패턴).
    prompt = f"{style}:\n{text}" if style else text
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}},
            },
        },
    }
    r = requests.post(
        f"{GEMINI_TTS_BASE}/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json=body, timeout=180,
    )
    if not r.ok:
        raise TTSError(f"Gemini TTS 오류 HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    cands = data.get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") or []) if cands else []
    inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
    if not inline or not inline.get("data"):
        raise TTSError(f"Gemini TTS 응답에 오디오가 없습니다: {str(data)[:200]}")
    pcm = base64.b64decode(inline["data"])
    rate = _pcm_rate_from_mime(inline.get("mimeType", ""))
    wav = _pcm_to_wav(pcm, rate)
    return TTSOutput(wav, "wav", None, {"voice": voice, "model": model})


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
    "gemini": _synth_gemini,
    "typecast": _synth_typecast,
    "clova": _synth_clova,
    "mock": _synth_mock,
}


# ---------------------------------------------------------------- orchestration

def _synth_with_retry(provider: str, text: str, cfg: dict, attempts: int = 3):
    """한 프로바이더로 합성 — 일시 오류(429/5xx/네트워크)는 백오프 재시도, 계정차단·인증오류
    (403/401/UNUSUAL_ACTIVITY)는 재시도해도 소용없고 오히려 차단을 악화시키므로 즉시 상위로 던져
    다음 프로바이더로 넘어가게 한다."""
    import time
    last = None
    for i in range(attempts):
        try:
            return _SYNTH[provider](text, cfg)
        except Exception as e:
            last = e
            m = str(e).upper()
            if any(t in m for t in ("403", "401", "UNUSUAL", "SUSPEND", "FORBIDDEN", "UNAUTHORIZED")):
                raise   # 계정/인증 문제 — 재시도 무의미, 다음 프로바이더로
            if i < attempts - 1:
                wait = 2 ** i
                print(f"[tts] '{provider}' 일시 오류 → {wait}s 후 재시도({i + 2}/{attempts}): {str(e)[:120]}")
                time.sleep(wait)
    raise last


def synthesize_to_files(text: str, job_dir: Path, tts_settings: dict,
                        whisper_settings: dict | None = None) -> dict:
    """대본 텍스트 → job_dir/audio.mp3 + job_dir/timestamps.json (공통 계약).

    반환 meta: {provider, timestamps_source, audio_path, timestamps_path, words}
    """
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    primary = resolve_provider(tts_settings.get("provider", "auto"))
    avail = detect_available()
    detected = [n for n, ok in avail.items() if ok]
    print(f"[tts] 감지된 API 키(이름만): {detected or '없음'} → 1순위 프로바이더: {primary}")

    # 폴백 체인: 1순위가 실패(예: Typecast 403 계정차단)해도 다른 등록 프로바이더로 자동 전환.
    # (한 프로바이더의 일시 장애/계정차단이 제작 전체를 죽이지 않게 한다.)
    order = [primary] + [p for p in PROVIDER_ORDER if avail.get(p) and p != primary]
    out, provider, errors = None, None, []
    for cand in order:
        try:
            out = _synth_with_retry(cand, text, tts_settings.get(cand, {}) or {})
            provider = cand
            if cand != primary:
                print(f"[tts] 1순위 실패 → '{cand}'로 폴백 성공")
            break
        except Exception as e:
            errors.append(f"{cand}: {str(e)[:180]}")
            print(f"[tts] 프로바이더 '{cand}' 실패 → 다음 후보 시도: {str(e)[:150]}")
    if out is None:
        raise TTSError(
            "모든 TTS 프로바이더 실패:\n  " + "\n  ".join(errors)
            + "\n조치: (1) Typecast 무료계정이 '비정상 활동(UNUSUAL_ACTIVITY)'으로 일시 차단됐을 수 있음 "
            "→ 잠시(수십 분~수 시간) 뒤 재시도, 또는 (2) SHORTS_ELEVENLABS_API_KEY 등 다른 TTS 키를 "
            "등록해 폴백을 확보하세요. (급하면 '나레이션 없이' 모드로 비주얼만 먼저 확인 가능)"
        )

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
