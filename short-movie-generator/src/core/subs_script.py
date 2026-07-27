"""subs_script — 화면에 나가는 자막을 '시각 + 일본어 + 한국어'로 정리(관리자 확인용).

운영자 요청: "모든 쇼츠 영상의 일본어/한국어 자막을 관리자 페이지에서 타임스탬프별로 보고 싶다."
나레이션형(narrate)과 도감형(reels)이 **같은 형식**을 쓰도록 이 모듈 하나로 모은다.

계약: rows_from_disp(disp, offset) → [{"s":시각, "e":끝, "jp":일본어, "ko":한국어}]
  · disp   : narration_sync.synthesize가 준 [(텍스트, 시작, 끝)]  (본문 기준 시각)
  · offset : 앞에 붙는 오프닝 훅 길이(초) — 완성본 기준 시각으로 맞춘다
  · 한국어는 **한 번의 LLM 호출**로 번역하고, 실패하면 빈 문자열(발행을 막지 않는다)
"""
from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)


def translate_ko(lines: list[str]) -> list[str]:
    """일본어 자막 목록 → 한국어(1회 호출). 실패하면 빈 리스트."""
    if not lines:
        return []
    try:
        from src.core import llm
        raw = llm.generate_text(
            "次の日本語字幕リストを自然な韓国語に訳し、**同じ個数**のJSON配列だけを出力してください。\n"
            + json.dumps(lines, ensure_ascii=False), max_tokens=1200)
        if raw:
            m = re.search(r"\[.*\]", raw, re.S)
            if m:
                arr = json.loads(m.group(0))
                if isinstance(arr, list) and len(arr) == len(lines):
                    return [str(x).strip() for x in arr]
    except Exception as e:  # noqa: BLE001
        log.info("[subs] 한국어 번역 생략(%s)", e)
    return []


def rows_from_disp(disp: list, offset: float = 0.0) -> list[dict]:
    """자막 표시창 → 레코드용 행 목록(완성본 기준 시각 + 한국어 번역)."""
    rows = [{"s": round(float(s) + offset, 2), "e": round(float(e) + offset, 2),
             "jp": str(t).strip()} for t, s, e in (disp or []) if str(t).strip()]
    if not rows:
        return []
    ko = translate_ko([r["jp"] for r in rows])
    for i, r in enumerate(rows):
        r["ko"] = ko[i] if i < len(ko) else ""
    return rows
