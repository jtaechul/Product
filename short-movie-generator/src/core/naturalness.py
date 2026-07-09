"""naturalness — 발행 전 텍스트(나레이션·캡션) 자연스러움 검수·보완 (전 카테고리 공용).

LLM이 만든 문장이 번역투·기계어투로 어색하면 한 번 더 다듬는다. 원문의 **사실·의미·敬体
여부·분량은 절대 바꾸지 않는다**(문체 교정만). LLM 미가용/실패/이상 응답 시 원문을 그대로
반환한다(발행을 막지 않음 — 이미 생성 단계에서 품질 기준을 통과한 문장이므로 안전).

★적용 범위(의도적): 나레이션(자막)·캡션 본문에만 쓴다. 오프닝 훅·유튜브 제목은 적용하지
않는다 — 그 둘은 "임팩트 우선 마케팅 카피"(단문·체언종결 등 의도적 비표준 문체)라 이 모듈의
"자연스러운 대화체" 기준과 충돌한다(하드룰 #8 예외 취지 보존). 사람이 승인한 시드 문구도
재검수하지 않는다(불필요한 LLM 호출·드리프트 방지 — 호출부에서 시드 분기 이후에만 연결).
"""
from __future__ import annotations

import json
import logging
import re

from src.core import llm

log = logging.getLogger(__name__)

_POLISH_LINES_PROMPT = """次の日本語の文/節の配列を確認してください。機械翻訳のようにぎこちない、\
不自然な言い回しがあれば、**意味・事実・敬体/常体・行数・順序は絶対に変えず**に、自然な日本語に\
言い換えてください。すでに自然なら、そのまま返してください。JSON配列のみ出力(説明・コードブロック禁止)。

配列({n}行、必ず同じ行数で返す):
{lines}

JSON例: ["...","...","..."]
"""

_POLISH_TEXT_PROMPT = """次の日本語の文章を確認してください。機械翻訳のようにぎこちない表現が\
あれば、**意味・事実・敬体/常体・おおよその分量は絶対に変えず**に自然な日本語に言い換えて\
ください。すでに自然なら、そのまま返してください。本文のみ出力(説明・引用符・コードブロック禁止)。

本文:
{text}
"""


def polish_lines(lines: list[str]) -> list[str]:
    """나레이션 등 '문장 배열'을 검수·보완. 줄 수·순서 불변(자막/TTS 동기 보존). 실패 시 원문."""
    lines = [str(x) for x in (lines or [])]
    if not lines:
        return lines
    try:
        numbered = "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(lines))
        out = llm.generate_text(
            _POLISH_LINES_PROMPT.format(n=len(lines), lines=numbered), max_tokens=900)
        if not out:
            return lines
        m = re.search(r"\[.*\]", out, re.S)
        if not m:
            return lines
        arr = json.loads(m.group(0))
        if (isinstance(arr, list) and len(arr) == len(lines)
                and all(isinstance(x, str) and x.strip() for x in arr)):
            return [str(x).strip() for x in arr]
    except Exception as e:  # noqa: BLE001
        log.warning("[naturalness] 자막 검수 실패(원문 유지): %s", e)
    return lines


def polish_text(text: str) -> str:
    """캡션 등 '긴 본문'을 검수·보완. 실패·분량 급변 시 원문 유지."""
    text = str(text or "")
    if not text.strip():
        return text
    try:
        out = llm.generate_text(_POLISH_TEXT_PROMPT.format(text=text), max_tokens=1000)
        out = (out or "").strip()
        # 분량이 크게 다르면(요약/과편집 의심) 신뢰하지 않고 원문 유지
        if out and 0.6 <= len(out) / max(1, len(text)) <= 1.6:
            return out
    except Exception as e:  # noqa: BLE001
        log.warning("[naturalness] 캡션 검수 실패(원문 유지): %s", e)
    return text
