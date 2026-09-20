"""tts — Edge-TTS 나레이션 합성 + 단어 단위 실제 타임스탬프.

Whisper(STT)를 쓰지 않는 이유: Edge-TTS는 음성을 만들면서 "몇 초에 어떤 단어를
발음했는지"를 WordBoundary 이벤트로 직접 알려준다. 되받아 적는 추정이 아니라
엔진이 준 실제 값이므로 정확하고, 비용·대기시간·한국어 오인식이 모두 없다.

(로직 출처: short-movie-generator/src/core/narration_sync.py — 검증된 구현 이식)
"""
from __future__ import annotations

import asyncio
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path

VOICES = {
    "ko-KR-SunHiNeural": "선히 (여성 · 밝고 따뜻함 · 동화 낭독 추천)",
    "ko-KR-InJoonNeural": "인준 (남성 · 차분하고 묵직함)",
    "ko-KR-HyunsuMultilingualNeural": "현수 (남성 · 부드러운 젊은 톤)",
}

_PROXY_CA = "/root/.ccr/ca-bundle.crt"
_PUNCT = re.compile(r"[、。，．・「」『』（）!?.,…~\-\s]")


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


def _core(s: str) -> str:
    return _PUNCT.sub("", s)


@dataclass
class SceneAudio:
    index: int
    text: str
    mp3: str
    speech_duration: float
    words: list[tuple[float, float, str]] = field(default_factory=list)


async def _synth(text: str, voice: str, rate: str, pitch: str):
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
    """Streamlit 스크립트 스레드에서 안전하게 코루틴 실행."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def synthesize_scene(index: int, text: str, work_dir: str, *,
                     voice: str = "ko-KR-SunHiNeural",
                     rate: str = "+0%", pitch: str = "+0Hz") -> SceneAudio:
    """씬 대본 한 편 → mp3 + 단어 타임스탬프(씬 내부 기준 초)."""
    _install_ca()
    text = " ".join(str(text).split())
    if not text:
        raise ValueError(f"{index + 1}번 씬 대본이 비어 있습니다.")
    audio, words = _run(_synth(text, voice, rate, pitch))
    if not audio:
        raise RuntimeError(f"{index + 1}번 씬 음성 합성 결과가 비었습니다. 네트워크를 확인하세요.")
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    mp3 = str(Path(work_dir) / f"scene_{index + 1:02d}.mp3")
    Path(mp3).write_bytes(audio)
    dur = (words[-1][0] + words[-1][1]) if words else 0.0
    return SceneAudio(index=index, text=text, mp3=mp3, speech_duration=dur, words=words)


def group_words_into_lines(words: list[tuple[float, float, str]], text: str,
                           max_chars: int = 13) -> list[dict]:
    """단어 타임스탬프를 화면 한 줄 단위로 묶는다.

    한 줄 = {"start", "end", "words": [(dur, 표시어), ...]}
    문장부호에서 우선 끊고, 그래도 길면 max_chars 기준으로 끊는다.
    표시어는 원문(문장부호 포함)을 쓰기 위해 원문 토큰과 순서대로 정합한다.
    """
    tokens = text.split()
    ti, lines, cur = 0, [], []
    cur_chars = 0

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
        # 원문 토큰과 맞춰 문장부호를 살린다(엔진은 부호를 떼고 준다).
        if ti < len(tokens) and _core(tokens[ti]) == _core(wtext):
            disp = tokens[ti]
            ti += 1
        cur.append({"start": st, "dur": dur, "disp": disp})
        cur_chars += len(disp) + 1
        if disp and disp[-1] in "….!?。":
            flush()
        elif cur_chars >= max_chars:
            flush()
    flush()

    # "뭐예요." 처럼 한 단어만 남은 줄은 앞줄에 붙인다(화면에 덩그러니 뜨는 것 방지).
    merged: list[dict] = []
    for ln in lines:
        tail = ln["words"]
        if (merged and len(tail) == 1 and len(tail[0][2]) <= 4):
            prev = merged[-1]
            prev["words"] = prev["words"] + tail
            prev["end"] = ln["end"]
        else:
            merged.append(ln)
    return merged
