"""소싱용 번역·검색어 확장 (Gemini 텍스트 — 저가·허용, 영상 생성 아님).

- expand_zh_terms: 한국어 키워드 → 중국어(간체) 검색어 3~5개로 확장(틱톡 중국 쇼핑 쇼츠 겨냥).
- translate_titles_ko: 영상 제목/설명(주로 중국어) → 한국어 한 줄 설명(선택 판단용).

의존성 없이 urllib로 Gemini generateContent 호출(소싱 워크플로는 stdlib만 설치).
키(GEMINI_API_KEY/SHORTS_GEMINI_API_KEY)가 없거나 실패하면 **원문 폴백**(발굴은 계속 동작).
call 인자로 Gemini 호출을 주입 가능(단위 테스트 — 네트워크 없이).
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL = "gemini-2.5-flash"


def gemini_key() -> str | None:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("SHORTS_GEMINI_API_KEY") or "").strip() or None


def _extract_json(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt or "", re.S)
    return json.loads(m.group(0)) if m else {}


def _gemini_json(prompt: str, system: str, max_tokens: int = 1024,
                 model: str = GEMINI_MODEL, call=None) -> dict:
    """Gemini에 JSON 응답을 요청해 파싱한 dict 반환. call 주입 시 그걸로 호출(테스트)."""
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens, "temperature": 0.4,
            "responseMimeType": "application/json",
            "thinkingConfig": {"thinkingBudget": 0},   # 2.5 Flash 사고 OFF(출력 예산 확보)
        },
    }
    if call is not None:
        data = call(body)
    else:
        key = gemini_key()
        if not key:
            raise RuntimeError("Gemini 키 없음")
        req = urllib.request.Request(
            f"{GEMINI_BASE}/models/{model}:generateContent",
            data=json.dumps(body).encode("utf-8"),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            data = json.loads(r.read())
    cands = data.get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") if cands else []) or []
    txt = "".join(p.get("text", "") for p in parts)
    return _extract_json(txt)


def expand_zh_terms(korean_keyword: str, call=None) -> list:
    """한국어 키워드 → 중국어 검색어 리스트(원문 폴백 포함, 항상 1개 이상)."""
    kw = (korean_keyword or "").strip()
    if not kw:
        return []
    if call is None and not gemini_key():
        return [kw]   # 키 없음 → 원문(틱톡은 원문으로도 검색됨)
    system = ("너는 쇼핑 쇼츠 소싱 도우미다. 한국어 키워드를 중국어(간체)로 번역하고, "
              "틱톡에서 조회수 높은 '중국 쇼핑/신박한 상품' 쇼츠를 찾기 좋은 관련 중국어 검색어로 확장한다. "
              "너무 일반적이지 않게 상품군을 특정하라. JSON만 출력.")
    prompt = (f'키워드: "{kw}"\n'
              '이 키워드와 관련된 중국어 검색어 3~5개를 JSON으로: {"terms": ["...", "..."]}')
    try:
        terms = [str(t).strip() for t in (_gemini_json(prompt, system, 512, call=call).get("terms") or []) if str(t).strip()]
        return terms[:5] or [kw]
    except Exception as e:
        print(f"[translate] 중국어 확장 실패: {e} → 원문 사용")
        return [kw]


def translate_titles_ko(titles: list, call=None) -> list:
    """영상 제목/설명 → 한국어 한 줄 설명(개수·순서 보존, 실패 시 원문 폴백)."""
    titles = [("" if t is None else str(t)) for t in (titles or [])]
    if not titles:
        return []
    if call is None and not gemini_key():
        return list(titles)
    system = ("너는 번역가다. 틱톡 쇼핑 영상의 제목/설명(주로 중국어)을 한국어 한 줄로 번역·요약한다. "
              "이모지·해시태그·'링크 클릭' 같은 판매유도 문구는 빼고 '무슨 상품/무슨 내용인지'만 담아라. "
              "JSON만 출력.")
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    prompt = (f"각 항목을 한국어 한 줄 설명으로 바꿔라(입력 순서·개수 그대로):\n{numbered}\n"
              '출력 JSON: {"ko": ["0번 한국어", "1번 한국어", ...]}')
    try:
        ko = _gemini_json(prompt, system, 2048, call=call).get("ko") or []
        return [(str(ko[i]).strip() if i < len(ko) and str(ko[i]).strip() else titles[i])
                for i in range(len(titles))]
    except Exception as e:
        print(f"[translate] 제목 번역 실패: {e} → 원문 사용")
        return list(titles)
