"""tts — 나레이션 합성 (narrated_wildlife 전환).

깊고 거친 ASMR풍 다큐 보이스, 문장별 톤 태그대로 변조. 배경음악 없음(앰비언트 SFX만).
엔진: Gemini TTS(gemini-2.5-flash-preview-tts, 같은 생태계·저비용). 스파이크 확인:
음질 양호하나 '단어 타임스탬프 미제공' → 자막은 subtitle 모듈이 음절 비례로 근사.

계약:
- synthesize(sentences, work_dir) → (wav_path, timings) / 키 없거나 실패 시 (None, []).
- timings: [{text, tone, start, end}] (문장 경계 초). 문장 사이 짧은 무음 gap 삽입(자연스러운 낭독).
"""
from __future__ import annotations

import logging
import os
import subprocess
import wave
from pathlib import Path

log = logging.getLogger(__name__)

TTS_MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Charon"           # 깊은 남성 보이스(다큐 내레이션)
SR = 24000                 # Gemini TTS 출력: PCM L16 24kHz mono
GAP_S = 0.22               # 문장 사이 무음(호흡) — 가속에 맞춰 단축
SPEED = 1.7                # 낭독 속도 배율(피치 보존, FFmpeg atempo). 1.5~2.0 튜닝 구간(사용자 요청)

# 톤 태그 → 낭독 스타일 지시(자연어). 기본은 깊고 거친 ASMR 다큐.
_BASE = "in a deep, gravelly, cinematic ASMR documentary voice"
_TONE_STYLE = {
    "gravelly": "in a deep, gravelly, cinematic voice",
    "slow": "in a deep, calm, deliberate voice",
    "whispered": "in a hushed, intimate whisper, very close and quiet",
    "whispering": "in a hushed, intimate whisper, very close and quiet",
    "hushed": "in a low, hushed, breathy tone",
    "reverent": "in a reverent, awe-struck tone, solemn",
    "tense": "in a tense, suspenseful low voice",
    "awe": "in an awe-inspiring, wondrous tone",
    # 아귀 릴스 벤치마크 톤(1.7억뷰) — 신비→침울→경외→사색→마무리
    "mysterious": "in a mysterious, secretive low voice",
    "somber": "in a somber, heavy, dark tone",
    "awestruck": "in an awe-struck, wondrous tone",
    "thoughtful": "in a thoughtful, reflective, quiet tone",
    "final": "in a slow, resonant, conclusive tone",
}


def _style(tone: str) -> str:
    return _TONE_STYLE.get((tone or "").lower(), _BASE)


def _synth_one(client, text: str, tone: str) -> bytes | None:
    from google.genai import types
    instr = f"Read this Korean nature-documentary line {_style(tone)}: {text}"
    resp = client.models.generate_content(
        model=TTS_MODEL, contents=instr,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE))),
        ),
    )
    return resp.candidates[0].content.parts[0].inline_data.data


def synthesize(sentences: list[dict], work_dir: str) -> tuple[str | None, list[dict]]:
    """문장별 톤으로 합성·연결한 wav와 문장 타이밍을 반환. 키 없거나 실패 시 (None, [])."""
    if not os.environ.get("GEMINI_API_KEY") or not sentences:
        log.info("[tts] GEMINI_API_KEY 없음/문장 없음 → 나레이션 생략(앰비언트만)")
        return None, []
    try:
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    except Exception as e:  # noqa: BLE001
        log.warning("[tts] 클라이언트 초기화 실패 → 나레이션 생략: %s", e)
        return None, []

    pcm = bytearray()
    gap = b"\x00\x00" * int(SR * GAP_S)
    timings: list[dict] = []
    for i, s in enumerate(sentences):
        try:
            data = _synth_one(client, s["text"], s.get("tone", "slow"))
        except Exception as e:  # noqa: BLE001
            log.warning("[tts] 문장 합성 실패(%d) → 나레이션 생략: %s", i, e)
            return None, []
        if not data:
            return None, []
        start = len(pcm) / 2 / SR
        pcm += data
        end = len(pcm) / 2 / SR
        timings.append({"text": s["text"], "tone": s.get("tone", "slow"),
                        "start": round(start, 3), "end": round(end, 3)})
        pcm += gap
    raw = str(Path(work_dir) / "narration_raw.wav")
    with wave.open(raw, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(bytes(pcm))
    # 낭독 속도 1.2배(피치 보존) — atempo. 실패 시 원본 유지. 타이밍도 동일 배율로 축소.
    out = raw
    if abs(SPEED - 1.0) > 0.01:
        sped = str(Path(work_dir) / "narration.wav")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
             "-filter:a", f"atempo={SPEED}", sped],
            capture_output=True, text=True,
        )
        if proc.returncode == 0 and Path(sped).exists():
            out = sped
            timings = [{**t, "start": round(t["start"] / SPEED, 3),
                        "end": round(t["end"] / SPEED, 3)} for t in timings]
        else:
            log.warning("[tts] atempo 가속 실패 → 원속도 유지: %s", proc.stderr[-200:])
    total = narration_duration(out)
    log.info("[tts] 나레이션 %d문장 · %.1fs(×%.1f) → %s", len(timings), total, SPEED, out)
    return out, timings


def narration_duration(wav_path: str) -> float:
    try:
        with wave.open(wav_path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:  # noqa: BLE001
        return 0.0
