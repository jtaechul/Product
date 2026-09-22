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

# 할당량이 바닥나 Edge 로 갈아탈 때, 성별이라도 맞춰 준다.
FALLBACK_VOICE = {
    "Sulafat": "ko-KR-SunHiNeural", "Kore": "ko-KR-SunHiNeural",
    "Aoede": "ko-KR-SunHiNeural", "Leda": "ko-KR-SunHiNeural",
    "Charon": "ko-KR-InJoonNeural", "Enceladus": "ko-KR-InJoonNeural",
}

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# 모든 낭독에 공통으로 거는 연기 지시. 씬별 지시(voice_direction)가 뒤에 덧붙는다.
# 표지에서 제목을 소개할 때의 연기 지시. 본문과 결이 같되 또렷하게 얹는다.
TITLE_DIRECTION = "이야기의 제목을 소개하듯 또박또박, 한 박자 느리게, 살짝 힘주어"

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


class QuotaError(TTSError):
    """할당량이 바닥났다. 기다려도 안 되므로 예비 엔진으로 갈아타야 한다."""


# ---------------------------------------------------------------- 감정 마커

# 대본에 쓸 수 있는 연기 마커. Gemini 는 SSML 을 안 받지만, 대괄호 인라인 지시는
# 알아듣는다. 마커는 **음성에만 보내고 자막에서는 지운다** — 안 그러면 화면에
# "[슬픔]" 이 그대로 뜬다.
MARKERS = [
    "[속삭이며]", "[슬픔]", "[기쁨]", "[놀라며]", "[다정하게]", "[단호하게]",
    "[빠르게]", "[천천히]", "[웃으며]", "[한숨]", "[떨리는 목소리로]", "[힘주어]",
]
_MARKER_RE = re.compile(r"\[[^\[\]]{1,16}\]")


def strip_markers(text: str) -> str:
    """자막·길이계산용 — 마커를 걷어낸 순수 대사."""
    return " ".join(_MARKER_RE.sub(" ", str(text)).split())


# ---------------------------------------------------------------- 페르소나

# ⭐ 조각이 나뉘어도 **글자 하나 다르지 않은** 이 문장이 모든 호출에 들어간다.
# 예전엔 조각마다 지시문을 조금씩 바꿨는데(첫 줄이냐, 문장 중간이냐…),
# Gemini 는 지시문이 바뀌면 톤도 같이 바뀌어서 씬마다 목소리가 흔들렸다.
PERSONA = (
    "[목소리] 한국 전래동화 전문 성우. 마흔 언저리의 따뜻하고 낮은 음색, "
    "또렷한 발음, 서두르지 않는 넉넉한 호흡. 늘 같은 사람입니다."
)
SCENE_SETTING = "[상황] 잠자리에서 아이에게 옛이야기를 도란도란 들려주는 자리."
MARKER_RULE = (
    "[규칙] 대괄호 안의 말은 소리 내어 읽지 말고, 바로 뒤 대사를 그렇게 연기하라는 "
    "지시로만 받아들이세요. 지시문·기호를 발음하지 마세요. 배경음 없이 목소리만."
)


def build_style(direction: str = "") -> str:
    """한 씬 안의 모든 조각이 공유할 지시문. 씬마다 [연기]만 달라진다."""
    return " ".join([
        PERSONA,
        SCENE_SETTING,
        f"[연기] {' '.join(str(direction or '담담하고 다정하게').split())}",
        MARKER_RULE,
    ])


# ---------------------------------------------------------------- 조각 나누기

_SENT_SPLIT = re.compile(r"(?<=[.!?…。])\s+")


def split_chunks(text: str, max_chars: int = 24) -> list[dict]:
    """대본 → **절(clause) 단위** 합성 조각. 조각 하나가 곧 자막 한 줄이 된다.

    왜 이렇게 하나 — 두 가지를 동시에 잡으려고.
    ① 운율: 20자마다 기계적으로 끊으면 말 중간이 잘려 조각마다 제 나름의 억양으로
       시작하고 끝맺는다. 그게 "평면적이고 기계적"의 진짜 원인이었다. 절 단위로 끊으면
       성우가 **완결된 구를 통째로** 읽으므로 억양 곡선이 산다.
    ② 자막 싱크: 조각 하나 = 자막 한 줄이면, 줄이 뜨고 사라지는 시각이 **측정값 그대로**다.
       보간으로 추정할 필요가 아예 없어진다. (어절 단위로 맞추려 했더니 말 빠르기가
       흔들릴 때 한 칸씩 밀려 1초 넘게 어긋난 적이 있다 — 그 위험을 구조로 없앤다.)

    끊는 자리: 문장 끝(. ! ?) 과 쉼표. 그래도 긴 절은 어절에서 쪼개는데, 그 자리는
    말 중간이라 쉼을 넣지 않고 크로스페이드로 잇는다.
    """
    out: list[dict] = []

    def add(piece: str, pause: float):
        piece = piece.strip()
        if piece:
            out.append({"tts": piece, "disp": strip_markers(piece), "pause": pause})

    buf = ""
    for tok in " ".join(str(text).split()).split():
        buf = f"{buf} {tok}".strip()
        plain = strip_markers(buf)
        tail = tok[-1:] if tok else ""
        if tail in _SENT_END:
            add(buf, 0.32)                     # 문장 끝 — 넉넉히 쉰다
            buf = ""
        elif tail in _COMMA and len(plain) >= 8:
            add(buf, 0.18)                     # 절 끝 — 짧게 쉰다
            buf = ""
        elif len(plain) >= max_chars:
            add(buf, 0.0)                      # 말 중간 — 쉼 없이 크로스페이드로 이음
            buf = ""
    if buf:
        add(buf, 0.32)
    if out:
        out[-1]["pause"] = 0.0                 # 씬 끝 여백은 렌더가 따로 붙인다
    return out


def split_display_lines(text: str, max_chars: int = 20) -> list[str]:
    """조각 하나를 화면 몇 줄로 보여줄지. 문장부호에서 먼저 끊는다."""
    lines, cur = [], ""
    for tok in str(text).split():
        cand = f"{cur} {tok}".strip()
        if cur and len(cand) > max_chars:
            lines.append(cur)
            cur = tok
        else:
            cur = cand
        # 문장 끝에서는 무조건, 쉼표에서는 줄이 어느 정도 찼을 때 끊는다.
        # 이 자리에는 성우가 실제로 쉬므로, 뒤에서 '무음 스냅'이 정확히 물린다.
        if cur and (cur[-1] in _SENT_END
                    or (cur[-1] in _COMMA and len(cur) >= max_chars * 0.55)):
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    # 한 어절만 남은 꼬리는 앞줄에 붙인다(화면에 덩그러니 뜨는 것 방지)
    merged: list[str] = []
    for ln in lines:
        toks = ln.split()
        if merged and len(toks) == 1 and len(toks[0]) <= 4:
            merged[-1] = f"{merged[-1]} {ln}"
        else:
            merged.append(ln)
    return merged or [str(text)]


def _syllables(s: str) -> int:
    n = sum(1 for c in s if "가" <= c <= "힣")
    return max(1, n or len(_PUNCT.sub("", s)))


# ---------------------------------------------------------------- 타이밍 보간

# 쉼표 하나가 먹는 시간을 음절 몇 개로 칠지. 한국어는 음절 길이가 비교적 고르기
# 때문에(초당 5음절 안팎) 음절 비례가 좋은 근사인데, 오차의 주범이 **쉼**이다.
_PAUSE_BETA = 1.6


def _token_weight(tok: str) -> float:
    w = float(_syllables(tok))
    tail = tok[-1] if tok else ""
    if tail in _SENT_END:
        w += _PAUSE_BETA * 2
    elif tail in _COMMA:
        w += _PAUSE_BETA
    return w


def find_silences(pcm: bytes, rate: int, min_ms: int = 15,
                  ratio: float = 0.10) -> list[tuple[float, float]]:
    """조각 안의 실제 공백 구간을 찾는다.

    문턱값을 고정하지 않고 **그 조각의 최대 음량 대비 비율**로 잡는다.
    목소리가 작은 성우에서 고정 문턱을 쓰면 말까지 공백으로 잡힌다.
    """
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    if not a:
        return []
    win = max(1, rate // 200)                       # 5ms
    peak = max(max(a), -min(a), 1)
    thresh = max(180, int(peak * ratio))
    quiet = []
    for i in range(0, len(a) - win + 1, win):
        seg = a[i:i + win]
        quiet.append(max(seg) < thresh and min(seg) > -thresh)
    need = max(1, min_ms * rate // 1000 // win)
    runs, start = [], None
    for i, q in enumerate(quiet + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if i - start >= need:
                runs.append((start * win / rate, i * win / rate))
            start = None
    return runs


def interpolate_lines(pcm: bytes, rate: int, t0: float, disp: str,
                      max_chars: int = 20) -> list[dict]:
    """측정된 조각 구간 안에서 줄·어절 타임스탬프를 역산한다.

    ① 줄 무게 = 그 줄 어절들의 (음절수 + β×쉼계수) 합
    ② 누적 비례로 줄 경계를 어림한 뒤, **조각 안의 실제 공백**에 박는다
       (가까움 + 쉼의 길이로 점수를 매겨 문장부호 자리를 고른다)
    ③ 줄 안에서는 어절 무게 비례로 나눈다
    ④ 마지막 줄의 끝을 조각 끝에 못 박아 오차가 누적되지 않게 한다
    조각의 시작·끝은 실측이므로 오차는 조각 하나 안에 갇힌다.
    """
    total = len(pcm) / 2 / rate
    # ⭐ 조각 하나 = 자막 한 줄. 쪼개지 않는다.
    # 쪼개는 순간 그 경계는 '추정'이 되고, 말 빠르기가 흔들리면 한 칸씩 밀려 1초 넘게
    # 어긋날 수 있다. 조각 경계는 측정값이므로 안 쪼개면 그 위험이 **구조적으로** 없다.
    # 화면에서는 두세 줄로 접혀 보일 뿐이다(ASS 가 알아서 접는다).
    toks = disp.split()
    if not toks:
        return []
    ws = [_token_weight(t) for t in toks]
    sw = sum(ws) or 1.0

    # 줄 안 어절은 무게 비례로 나누되, **아주 가까운 곳에 실제 공백이 있으면** 거기 붙인다.
    # 폭을 좁게(±0.12초) 잡는다 — 넓히면 옆 어절의 공백을 잘못 잡아 되레 밀린다.
    mids = [(a + b) / 2 for a, b in find_silences(pcm, rate, min_ms=30)
            if 0.05 < (a + b) / 2 < total - 0.05]
    # 공백 개수가 어절 사이 개수와 **정확히** 같으면 순서대로 그대로 쓴다.
    # 이럴 땐 헷갈릴 여지가 없어서(1:1) 어절 타이밍이 사실상 실측이 된다.
    if len(mids) == len(toks) - 1 and len(toks) > 1:
        bounds = [0.0] + list(mids) + [total]
        if all(bounds[i] < bounds[i + 1] for i in range(len(bounds) - 1)):
            words = [(round(t0 + bounds[j], 3),
                      round(max(0.06, bounds[j + 1] - bounds[j]), 3), tok)
                     for j, tok in enumerate(toks)]
            return [{"start": round(t0, 3), "end": round(t0 + total, 3), "words": words}]

    bounds, run, used = [0.0], 0.0, -1
    for w in ws[:-1]:
        run += w
        pr = total * run / sw
        pick = None
        for i in range(used + 1, len(mids)):
            if mids[i] > pr + 0.12:
                break
            if abs(mids[i] - pr) <= 0.12 and mids[i] > bounds[-1] + 0.05:
                if pick is None or abs(mids[i] - pr) < abs(mids[pick] - pr):
                    pick = i
        if pick is not None:
            bounds.append(mids[pick])
            used = pick
        else:
            bounds.append(max(bounds[-1] + 0.05, pr))
    bounds.append(total)

    words = []
    for j, tok in enumerate(toks):
        st, en = bounds[j], bounds[j + 1]
        words.append((round(t0 + st, 3), round(max(0.06, en - st), 3), tok))
    return [{"start": round(t0, 3), "end": round(t0 + total, 3), "words": words}]


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


def zero_cross_trim(pcm: bytes, rate: int, search_ms: int = 12) -> bytes:
    """조각의 앞뒤를 **파형이 0을 지나는 지점**으로 옮긴다.

    0이 아닌 값에서 뚝 끊고 다음 조각을 붙이면 파형이 수직으로 튀어 '툭' 소리가 난다.
    """
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    n = len(a)
    if n < 4:
        return pcm
    span = min(max(1, rate * search_ms // 1000), n // 4)
    s = min(range(span), key=lambda i: abs(a[i]))
    e = n - 1 - min(range(span), key=lambda i: abs(a[n - 1 - i]))
    return a[s:e + 1].tobytes() if e > s else pcm


def edge_fade(pcm: bytes, rate: int, ms: int = 10) -> bytes:
    """조각 앞뒤에 아주 짧은 페이드. 길이가 안 바뀌므로 자막이 밀리지 않는다."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    n = len(a)
    f = min(max(1, rate * ms // 1000), n // 2)
    if f < 2:
        return pcm
    for i in range(f):
        g = i / f
        a[i] = int(a[i] * g)
        a[n - 1 - i] = int(a[n - 1 - i] * g)
    return a.tobytes()


def crossfade_into(base: bytearray, add: bytes, rate: int, ms: int = 20) -> bytes:
    """말 **중간**을 끊은 자리를 겹쳐 섞는다(쉼이 0인 경계에서만 쓴다).

    겹친 만큼 전체가 짧아지므로, 줄어든 길이를 돌려주어 타임라인이 그만큼
    앞당겨지게 한다 — 이 값을 안 쓰면 뒤쪽 자막이 통째로 밀린다.
    """
    b = array.array("h")
    b.frombytes(add[: len(add) // 2 * 2])
    prev = array.array("h")
    prev.frombytes(bytes(base))
    f = min(max(1, rate * ms // 1000), len(b) // 2, len(prev) // 2)
    if f < 2:
        base += add
        return 0.0
    for i in range(f):
        g = i / f
        prev[len(prev) - f + i] = int(prev[len(prev) - f + i] * (1 - g) + b[i] * g)
    base[:] = bytearray(prev.tobytes())
    base += b[f:].tobytes()
    return f / rate


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
                model: str = GEMINI_TTS_MODEL, attempts: int = 3) -> tuple[bytes, int]:
    """한 덩어리를 Gemini TTS로 합성해 원시 PCM과 샘플레이트를 돌려준다."""
    body = json.dumps({
        "contents": [{"parts": [{"text": f"{style}\n\n{text}" if style else text}]}],
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
            detail = e.read().decode("utf-8", "replace")[:400]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (401, 403):      # 키 문제 — 다시 해도 같다
                raise TTSError(f"Gemini TTS 인증 실패({last}). GEMINI_API_KEY 를 확인하세요.") from e
            if e.code == 429:
                # 하루치가 바닥난 것이면 기다려도 오늘은 안 열린다. 바로 손을 턴다
                # (예전엔 씬마다 48초씩 버리고도 결국 실패했다).
                if re.search(r"per\s*day|PerDay|daily", detail, re.I):
                    raise QuotaError("Gemini 성우의 오늘 할당량을 다 썼습니다.") from e
                if i < attempts - 1:
                    wait = 20 * (i + 1)   # 분당 제한 — 한 번은 넉넉히 쉬고 다시
                    print(f"  분당 호출 제한에 걸려 {wait}초 쉽니다({i + 2}/{attempts})")
                    time.sleep(wait)
                    continue
                raise QuotaError(
                    "Gemini 성우 호출 제한을 계속 넘습니다(할당량 소진으로 보입니다).") from e
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


def _synth_gemini(index: int, text: str, work_dir: str, *, api_key: str,
                  voice: str, direction: str, max_chars: int,
                  gap: float = 0.0) -> SceneAudio:
    chunks = split_chunks(text)
    if not chunks:
        raise TTSError(f"{index + 1}번 씬 대본이 비어 있습니다.")

    # ⭐ 한 씬 안에서는 **똑같은** 지시문을 쓴다. 조각마다 바꾸면 톤이 흔들린다.
    style = build_style(direction)

    pcm_all = bytearray()
    rate = 24000
    timed: list[dict] = []
    for i, ch in enumerate(chunks):
        if gap > 0 and not (index == 0 and i == 0):
            time.sleep(gap)               # 분당 호출 제한을 덜 건드리게 띄엄띄엄
        pcm, rate = _gemini_say(api_key, ch["tts"], voice, style)
        pcm = zero_cross_trim(_trim_silence(pcm, rate), rate)
        pcm = edge_fade(pcm, rate, ms=10)
        if not pcm:
            raise TTSError(f"{index + 1}번 씬 {i + 1}번째 조각 음성이 비었습니다.")

        start = len(pcm_all) / 2 / rate
        prev_pause = chunks[i - 1]["pause"] if i else None
        if i and prev_pause == 0.0:
            # 말 중간을 끊은 자리 — 겹쳐 섞고, 줄어든 만큼 시작 시각을 당긴다
            start -= crossfade_into(pcm_all, pcm, rate, ms=20)
        else:
            pcm_all += pcm
        timed += interpolate_lines(pcm, rate, start, ch["disp"], max_chars=max_chars)
        if ch["pause"] > 0 and i < len(chunks) - 1:
            pcm_all += _silence(rate, ch["pause"])

    Path(work_dir).mkdir(parents=True, exist_ok=True)
    out = str(Path(work_dir) / f"scene_{index + 1:02d}.wav")
    _write_wav(out, bytes(pcm_all), rate)
    return SceneAudio(index=index, text=strip_markers(text), audio=out,
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
                      max_chars: int = 20) -> list[dict]:
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
                     max_chars: int = 20, gap: float = 0.0) -> SceneAudio:
    """씬 대본 한 편 → 음성 파일 + 줄 단위 자막 타이밍."""
    text = " ".join(str(text).split())
    if not text:
        raise TTSError(f"{index + 1}번 씬 대본이 비어 있습니다.")
    if engine == "edge":
        # ⚠️ Edge 는 연기 마커를 못 알아듣고 "대괄호 슬픔"처럼 **소리 내어 읽어버린다**.
        # 반드시 걷어내고 보낸다.
        v = voice if voice in EDGE_VOICES else "ko-KR-SunHiNeural"
        return _synth_edge(index, strip_markers(text), work_dir, voice=v, rate=rate,
                           pitch=pitch, max_chars=max_chars)
    if not api_key:
        raise TTSError("Gemini TTS 에는 GEMINI_API_KEY 가 필요합니다.")
    v = voice if voice in GEMINI_VOICES else "Sulafat"
    return _synth_gemini(index, text, work_dir, api_key=api_key, voice=v,
                         direction=direction, max_chars=max_chars, gap=gap)


# 한국어 낭독 속도(음절/초). 대본만 보고 "몇 초짜리 영상을 만들어야 하나"를 미리 알려주려고 쓴다.
# 실제 길이는 합성해 봐야 알지만, 영상을 만들기 전에 알아야 쓸모가 있다.
# 렌더가 끝나면 진짜 잰 값이 기록에 덮어써진다.
_SYLLABLES_PER_SEC = 4.8
_SENTENCE_PAUSE = 0.35


def estimate_seconds(text: str, tail_pad: float = 0.5) -> float:
    """대본 한 줄이 몇 초쯤 읽힐지 어림한다(한글 음절 수 + 문장 끝 쉼).

    연기 마커는 소리로 나가지 않으므로 빼고 센다.
    """
    text = strip_markers(text)
    syllables = sum(1 for c in str(text) if "가" <= c <= "힣")
    sentences = sum(1 for c in str(text) if c in ".!?…")
    return round(syllables / _SYLLABLES_PER_SEC + sentences * _SENTENCE_PAUSE + tail_pad, 1)
