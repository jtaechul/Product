"""M5. 타임스탬프 폴백 — 타임스탬프 미제공 TTS(typecast/clova) 사용 시에만 활성화.

faster-whisper(오픈소스 Whisper 고속 구현)를 Actions 러너에서 직접 실행해
word_timestamps=True 로 단어 타임스탬프를 추출한다 (API 비용 0원, 스펙 §M5).

산출 계약: [{"word": "빨래를", "start": 0.00, "end": 0.42}, ...]
표시 단어는 항상 '원본 대본'의 단어를 쓴다 — Whisper 인식 결과는 타이밍 앵커로만 사용.
"""

from __future__ import annotations

from pathlib import Path


def align(audio_path: Path, script_text: str,
          model_size: str = "small", compute_type: str = "int8") -> list:
    """오디오를 Whisper로 정렬해 대본 단어별 타임스탬프를 만든다."""
    from faster_whisper import WhisperModel  # 무거운 임포트는 폴백 경로에서만

    model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    segments, info = model.transcribe(
        str(audio_path), language="ko", word_timestamps=True, beam_size=5,
    )
    anchor = []
    for seg in segments:
        for w in seg.words or []:
            token = (w.word or "").strip()
            if token:
                anchor.append({"word": token, "start": float(w.start), "end": float(w.end)})

    script_words = script_text.split()
    if not script_words:
        return []

    if not anchor:
        # 인식 실패(무음 등) → 오디오 길이에 균등 분배 (렌더가 죽지 않게 하는 최후 방어)
        duration = max(float(getattr(info, "duration", 0.0) or 0.0), 1.0)
        print(f"[align] Whisper가 단어를 인식하지 못함 → {duration:.1f}s 균등 분배 폴백")
        return _spread_evenly(script_words, 0.15, duration - 0.1)

    if len(anchor) == len(script_words):
        return [
            {"word": sw, "start": a["start"], "end": a["end"]}
            for sw, a in zip(script_words, anchor)
        ]

    print(f"[align] 단어 수 불일치(대본 {len(script_words)} vs 인식 {len(anchor)}) → "
          f"글자수 비례 재분배")
    return distribute_by_chars(script_words, anchor)


def distribute_by_chars(script_words: list, anchor_words: list) -> list:
    """대본 단어들을 앵커 타임라인 위에 글자 수 비례로 재분배한다.

    anchor_words 의 (누적 글자 비율 → 시각) 곡선을 만들어 선형 보간. 단어 수가
    달라도(인식 오차·조사 분리 등) 체감 싱크를 유지하는 근사 정렬.
    """
    if not anchor_words:
        return _spread_evenly(script_words, 0.15, max(1.0, 0.45 * len(script_words)))

    # 앵커: 누적 글자수 → (start, end) 지점들
    xs, ts = [0.0], [anchor_words[0]["start"]]
    total_anchor_chars = sum(len(a["word"]) for a in anchor_words) or 1
    acc = 0
    for a in anchor_words:
        acc += len(a["word"])
        xs.append(acc / total_anchor_chars)
        ts.append(a["end"])

    def at(ratio: float) -> float:
        for i in range(1, len(xs)):
            if ratio <= xs[i]:
                span = xs[i] - xs[i - 1] or 1e-9
                f = (ratio - xs[i - 1]) / span
                return ts[i - 1] + f * (ts[i] - ts[i - 1])
        return ts[-1]

    total_script_chars = sum(len(w) for w in script_words) or 1
    out, acc = [], 0
    for w in script_words:
        r0 = acc / total_script_chars
        acc += len(w)
        r1 = acc / total_script_chars
        s, e = at(r0), at(r1)
        if e - s < 0.05:
            e = s + 0.05
        out.append({"word": w, "start": round(s, 3), "end": round(e, 3)})
    return out


def _spread_evenly(script_words: list, start: float, end: float) -> list:
    n = len(script_words)
    span = max(end - start, 0.3 * n)
    weights = [max(len(w), 1) for w in script_words]
    total = sum(weights)
    out, t = [], start
    for w, wt in zip(script_words, weights):
        dur = span * wt / total
        out.append({"word": w, "start": round(t, 3), "end": round(t + dur * 0.85, 3)})
        t += dur
    return out
