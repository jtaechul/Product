"""tts — 나레이션 합성 + 자막 타이밍.

엔진 두 가지를 고를 수 있다.

**gemini (기본)** — Gemini 2.5 TTS. 감정·억양을 자연어로 지시할 수 있어 성우처럼 읽는다.
  다만 "몇 초에 어떤 말을 했는지"를 알려주지 않는다. 그래서 이 파일은 **자막 한 줄을
  하나의 합성 단위로 삼는다**: 줄마다 따로 합성하고, 앞뒤 묵음을 잘라내고, 실제 길이를
  샘플 수로 정확히 잰 뒤 정해진 쉼을 끼워 이어 붙인다. 그러면 각 줄이 화면에 뜨고
  사라지는 시각이 오디오와 **정확히** 일치한다(추정이 아니라 실측).
  한 줄(13자 안팎) 안에서 어절별 하이라이트만 음절 수 비례로 나눈다.

**edge (예비)** — Edge-TTS. 단어 타임스탬프(WordBoundary)를 엔진이 직접 준다.
  감정 지시는 못 하지만 무료이고 호출이 한 번이라 빠르다.
  (로직 출처: short-movie-generator/src/core/narration_sync.py)
"""
from __future__ import annotations

import array
import asyncio
import base64
import json
import re
import ssl
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path

# Edge-TTS 목소리 (예비 엔진)
EDGE_VOICES = {
    "ko-KR-SunHiNeural": "선히 (여성 · 밝고 따뜻함)",
    "ko-KR-InJoonNeural": "인준 (남성 · 차분하고 묵직함)",
    "ko-KR-HyunsuMultilingualNeural": "현수 (남성 · 부드러운 젊은 톤)",
}

# Gemini TTS 목소리 — 동화 낭독에 어울리는 것만 추렸다.
GEMINI_VOICES = {
    "Sulafat": "술라팟 (여성 · 따뜻하고 포근함 · 동화 낭독 추천)",
    "Kore": "코레 (여성 · 또렷하고 단단함)",
    "Aoede": "아오이데 (여성 · 가볍고 산뜻함)",
    "Leda": "레다 (여성 · 앳되고 발랄함)",
    "Charon": "카론 (남성 · 차분한 이야기꾼)",
    "Enceladus": "엔켈라두스 (남성 · 낮고 숨결 섞인 톤)",
}

VOICES = GEMINI_VOICES          # 관리자 화면이 보여 주는 기본 목록

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# 모든 낭독에 공통으로 거는 연기 지시. 씬별 지시(voice_direction)가 뒤에 덧붙는다.
BASE_DIRECTION = (
    "당신은 한국 전래동화를 들려주는 전문 성우입니다. 아이에게 이야기를 들려주듯 "
    "따뜻하고 다정하게, 또렷한 발음으로, 감정을 실어 읽어 주세요"
)

_PROXY_CA = "/root/.ccr/ca-bundle.crt"
_PUNCT = re.compile(r"[、。，．・「」『』（）!?.,…~\-\s]")
_SENT_END = "….!?。"
_COMMA = ",，、"


# ---------------------------------------------------------------- 공통 자료구조

@dataclass
class SceneAudio:
    index: int
    text: str
    audio: str                       # 합성된 음성 파일 경로 (wav 또는 mp3)
    speech_duration: float           # 말이 끝나는 시각(초)
    lines: list[dict] = field(default_factory=list)
    # lines[i] = {"start": 초, "end": 초, "words": [(시작초, 길이초, 표시어), ...]}


class TTSError(RuntimeError):
    pass


# ---------------------------------------------------------------- 줄 나누기

def split_lines(text: str, max_chars: int = 13) -> list[dict]:
    """대본 한 편을 화면 한 줄 단위로 나눈다(합성 단위이자 자막 단위).

    문장부호에서 먼저 끊고, 그래도 길면 어절 경계에서 max_chars 기준으로 끊는다.
    각 줄에 "뒤에 얼마나 쉴지"(pause)를 함께 정해 둔다 — 읽는 맛이 여기서 갈린다.
    """
    tokens = str(text).split()
    lines: list[dict] = []
    cur: list[str] = []
    cur_chars = 0

    def flush():
        nonlocal cur, cur_chars
        if not cur:
            return
        body = " ".join(cur)
        tail = body[-1] if body else ""
        if tail in _SENT_END:
            pause, ends = 0.32, True
        elif tail in _COMMA:
            pause, ends = 0.18, False
        else:
            pause, ends = 0.06, False
        lines.append({"text": body, "pause": pause, "sentence_end": ends})
        cur, cur_chars = [], 0

    for tok in tokens:
        cur.append(tok)
        cur_chars += len(tok) + 1
        if tok and tok[-1] in _SENT_END:
            flush()
        elif cur_chars >= max_chars:
            flush()
    flush()

    # "뭐예요." 처럼 한 어절만 남은 줄은 앞줄에 붙인다(화면에 덩그러니 뜨는 것 방지).
    merged: list[dict] = []
    for ln in lines:
        toks = ln["text"].split()
        if merged and len(toks) == 1 and len(toks[0]) <= 4:
            prev = merged[-1]
            prev["text"] = f"{prev['text']} {ln['text']}"
            prev["pause"] = ln["pause"]
            prev["sentence_end"] = ln["sentence_end"]
        else:
            merged.append(ln)
    return merged


def _syllables(s: str) -> int:
    n = sum(1 for c in s if "가" <= c <= "힣")
    return max(1, n or len(_PUNCT.sub("", s)))


def _spread_words(line_text: str, start: float, dur: float) -> list[tuple[float, float, str]]:
    """한 줄 안에서 어절별 하이라이트 구간을 음절 수 비례로 나눈다.

    줄 전체 구간은 실측이므로 정확하고, 줄이 13자 안팎이라 이 안에서의 오차는
    수십 밀리초 수준이다.
    """
    toks = line_text.split()
    if not toks:
        return []
    weights = [_syllables(t) for t in toks]
    total = sum(weights)
    out, t = [], start
    for i, (tok, w) in enumerate(zip(toks, weights)):
        d = dur * w / total
        if i == len(toks) - 1:            # 반올림 오차가 쌓이지 않게 마지막에서 맞춘다
            d = max(0.01, start + dur - t)
        out.append((round(t, 3), round(d, 3), tok))
        t += d
    return out


# ---------------------------------------------------------------- PCM 다루기

def _pcm_rate(mime: str) -> int:
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else 24000


def _trim_silence(pcm: bytes, rate: int, thresh: int = 500, keep: float = 0.035) -> bytes:
    """앞뒤 묵음을 잘라낸다. 이걸 해야 줄과 줄 사이 쉼을 우리가 정확히 통제한다."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    n = len(a)
    if n == 0:
        return pcm
    win = max(1, rate // 100)             # 10ms 단위로 본다
    s = 0
    while s + win <= n and max(a[s:s + win], default=0) < thresh and min(a[s:s + win], default=0) > -thresh:
        s += win
    e = n
    while e - win > s and max(a[e - win:e], default=0) < thresh and min(a[e - win:e], default=0) > -thresh:
        e -= win
    pad = int(rate * keep)
    s, e = max(0, s - pad), min(n, e + pad)
    if e <= s:
        return pcm
    return a[s:e].tobytes()


def _silence(rate: int, seconds: float) -> bytes:
    return b"\x00\x00" * max(0, int(rate * seconds))


def _write_wav(path: str, pcm: bytes, rate: int) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


# ---------------------------------------------------------------- Gemini TTS

def _gemini_say(api_key: str, text: str, voice: str, style: str,
                model: str = GEMINI_TTS_MODEL, attempts: int = 4) -> tuple[bytes, int]:
    """한 덩어리를 Gemini TTS로 합성해 원시 PCM과 샘플레이트를 돌려준다."""
    body = json.dumps({
        "contents": [{"parts": [{"text": f"{style}:\n{text}" if style else text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}},
            },
        },
    }).encode()
    url = f"{_GEMINI_BASE}/models/{model}:generateContent"

    last = ""
    for i in range(attempts):
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("x-goog-api-key", api_key)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
            inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
            if not inline or not inline.get("data"):
                raise TTSError(f"Gemini TTS 응답에 음성이 없습니다: {str(data)[:200]}")
            return base64.b64decode(inline["data"]), _pcm_rate(inline.get("mimeType", ""))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (401, 403):      # 키 문제 — 다시 해도 같다
                raise TTSError(f"Gemini TTS 인증 실패({last}). GEMINI_API_KEY 를 확인하세요.") from e
            if e.code == 429 and i < attempts - 1:
                wait = 8 * (i + 1)        # 분당 호출 제한 — 넉넉히 쉬고 다시
                print(f"  호출 제한에 걸려 {wait}초 쉬었다 다시 시도합니다({i + 2}/{attempts})")
                time.sleep(wait)
                continue
            if i < attempts - 1:
                time.sleep(2 ** i)
                continue
            raise TTSError(f"Gemini TTS 오류 {last}") from e
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            if i < attempts - 1:
                time.sleep(2 ** i)
                continue
            raise TTSError(f"Gemini TTS 실패: {last}") from e
    raise TTSError(f"Gemini TTS 실패: {last}")


def _style_for(direction: str, line: dict, is_first: bool, is_last: bool) -> str:
    """줄 하나를 어떤 어조로 읽을지 자연어 지시문을 만든다."""
    parts = [BASE_DIRECTION]
    d = " ".join(str(direction or "").split())
    if d:
        parts.append(d.rstrip("."))
    if not line["sentence_end"]:
        parts.append("문장이 아직 이어지는 중이니 끝을 내리지 말고 다음으로 이어지는 호흡으로")
    elif is_last:
        parts.append("이야기의 한 대목을 마무리하는 차분한 어조로")
    if is_first:
        parts.append("첫 마디이니 듣는 사람의 귀를 잡아끌도록")
    parts.append("배경음이나 효과음 없이 목소리만, 지시문은 읽지 말고 아래 문장만 그대로")
    return ", ".join(parts)


def _synth_gemini(index: int, text: str, work_dir: str, *, api_key: str,
                  voice: str, direction: str, max_chars: int) -> SceneAudio:
    lines = split_lines(text, max_chars=max_chars)
    if not lines:
        raise TTSError(f"{index + 1}번 씬 대본이 비어 있습니다.")

    pcm_all = bytearray()
    rate = 24000
    timed: list[dict] = []
    for i, ln in enumerate(lines):
        style = _style_for(direction, ln, is_first=(i == 0), is_last=(i == len(lines) - 1))
        pcm, rate = _gemini_say(api_key, ln["text"], voice, style)
        pcm = _trim_silence(pcm, rate)
        start = len(pcm_all) / 2 / rate
        pcm_all += pcm
        dur = len(pcm) / 2 / rate
        if dur <= 0:
            raise TTSError(f"{index + 1}번 씬 {i + 1}번째 줄 음성이 비었습니다.")
        timed.append({
            "start": round(start, 3),
            "end": round(start + dur, 3),
            "words": _spread_words(ln["text"], start, dur),
        })
        if i < len(lines) - 1:
            pcm_all += _silence(rate, ln["pause"])

    Path(work_dir).mkdir(parents=True, exist_ok=True)
    out = str(Path(work_dir) / f"scene_{index + 1:02d}.wav")
    _write_wav(out, bytes(pcm_all), rate)
    return SceneAudio(index=index, text=text, audio=out,
                      speech_duration=len(pcm_all) / 2 / rate, lines=timed)


# ---------------------------------------------------------------- Edge-TTS (예비)

def _install_ca() -> None:
    """개발 환경의 MITM 프록시 CA를 edge-tts SSL 컨텍스트에 주입. 배포 환경엔 무영향.

    Path.exists()까지 try 안에 둔다 — 비 root 실행 시 /root/.ccr 접근이
    PermissionError로 되던져져 합성이 통째로 죽는 사고가 실제 있었다.
    """
    try:
        if Path(_PROXY_CA).exists():
            import edge_tts.communicate as ec
            ec._SSL_CTX = ssl.create_default_context(cafile=_PROXY_CA)
    except Exception:  # noqa: BLE001
        pass


async def _edge_stream(text: str, voice: str, rate: str, pitch: str):
    import edge_tts
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    audio = bytearray()
    words: list[tuple[float, float, str]] = []
    async for ch in c.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return bytes(audio), words


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _core(s: str) -> str:
    return _PUNCT.sub("", s)


def _group_edge_lines(words: list[tuple[float, float, str]], text: str,
                      max_chars: int) -> list[dict]:
    """Edge-TTS 단어 타임스탬프를 화면 한 줄 단위로 묶는다."""
    tokens = text.split()
    ti, lines, cur, cur_chars = 0, [], [], 0

    def flush():
        nonlocal cur, cur_chars
        if cur:
            lines.append({
                "start": cur[0]["start"],
                "end": cur[-1]["start"] + cur[-1]["dur"],
                "words": [(w["start"], w["dur"], w["disp"]) for w in cur],
            })
        cur, cur_chars = [], 0

    for st, dur, wtext in words:
        disp = wtext
        if ti < len(tokens) and _core(tokens[ti]) == _core(wtext):
            disp = tokens[ti]
            ti += 1
        cur.append({"start": st, "dur": dur, "disp": disp})
        cur_chars += len(disp) + 1
        if disp and disp[-1] in _SENT_END:
            flush()
        elif cur_chars >= max_chars:
            flush()
    flush()

    merged: list[dict] = []
    for ln in lines:
        tail = ln["words"]
        if merged and len(tail) == 1 and len(tail[0][2]) <= 4:
            prev = merged[-1]
            prev["words"] = prev["words"] + tail
            prev["end"] = ln["end"]
        else:
            merged.append(ln)
    return merged


def _synth_edge(index: int, text: str, work_dir: str, *, voice: str,
                rate: str, pitch: str, max_chars: int) -> SceneAudio:
    _install_ca()
    audio, words = _run(_edge_stream(text, voice, rate, pitch))
    if not audio:
        raise TTSError(f"{index + 1}번 씬 음성 합성 결과가 비었습니다. 네트워크를 확인하세요.")
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    out = str(Path(work_dir) / f"scene_{index + 1:02d}.mp3")
    Path(out).write_bytes(audio)
    dur = (words[-1][0] + words[-1][1]) if words else 0.0
    return SceneAudio(index=index, text=text, audio=out, speech_duration=dur,
                      lines=_group_edge_lines(words, text, max_chars))


# ---------------------------------------------------------------- 진입점

def synthesize_scene(index: int, text: str, work_dir: str, *,
                     engine: str = "gemini",
                     api_key: str = "",
                     voice: str = "Sulafat",
                     direction: str = "",
                     rate: str = "+0%", pitch: str = "+0Hz",
                     max_chars: int = 13) -> SceneAudio:
    """씬 대본 한 편 → 음성 파일 + 줄 단위 자막 타이밍."""
    text = " ".join(str(text).split())
    if not text:
        raise TTSError(f"{index + 1}번 씬 대본이 비어 있습니다.")
    if engine == "edge":
        v = voice if voice in EDGE_VOICES else "ko-KR-SunHiNeural"
        return _synth_edge(index, text, work_dir, voice=v, rate=rate,
                           pitch=pitch, max_chars=max_chars)
    if not api_key:
        raise TTSError("Gemini TTS 에는 GEMINI_API_KEY 가 필요합니다.")
    v = voice if voice in GEMINI_VOICES else "Sulafat"
    return _synth_gemini(index, text, work_dir, api_key=api_key, voice=v,
                         direction=direction, max_chars=max_chars)


# 한국어 낭독 속도(음절/초). 대본만 보고 "몇 초짜리 영상을 만들어야 하나"를 미리 알려주려고 쓴다.
# 실제 길이는 합성해 봐야 알지만, 영상을 만들기 전에 알아야 쓸모가 있다.
# 렌더가 끝나면 진짜 잰 값이 기록에 덮어써진다.
_SYLLABLES_PER_SEC = 4.8
_SENTENCE_PAUSE = 0.35


def estimate_seconds(text: str, tail_pad: float = 0.5) -> float:
    """대본 한 줄이 몇 초쯤 읽힐지 어림한다(한글 음절 수 + 문장 끝 쉼)."""
    syllables = sum(1 for c in str(text) if "가" <= c <= "힣")
    sentences = sum(1 for c in str(text) if c in ".!?…")
    return round(syllables / _SYLLABLES_PER_SEC + sentences * _SENTENCE_PAUSE + tail_pad, 1)
