"""M3 후처리 — 금지어·특수기호 필터 + 길이 검증 (스펙 §3.3, §M3).

표시광고법 저촉 우려 표현(절대적·의학적 단정)을 차단하고,
이모지·특수기호를 제거한다. 규칙 위반은 RuleViolation으로 보고해
generate.py가 1회 재생성하도록 한다.
"""

from __future__ import annotations

import re

# 절대적 표현·의학적 단정 (스펙 §3.3) — 부분 문자열 매칭
FORBIDDEN = [
    "최고", "유일", "100%", "100프로", "백프로", "완벽한", "무조건",
    "질병", "치료", "완치", "부작용 없", "효과 보장", "다이어트 보장",
    "1등", "세계 최초", "국내 최초",
]

# 허용 문자: 한글, 영숫자, 공백, 기본 문장부호(쉼표·마침표·물음표·퍼센트·콤마 등)
_ALLOWED = re.compile(r"[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s.,?!%~\-()「」『』:/·']+")


class RuleViolation(Exception):
    pass


def clean_text(text: str) -> str:
    """이모지·특수기호 제거 + 공백 정리."""
    return re.sub(r"\s+", " ", _ALLOWED.sub("", text)).strip()


def check_forbidden(text: str) -> list:
    return [w for w in FORBIDDEN if w in text]


def sanitize_script(script: dict, strict_length: bool = True) -> dict:
    """대본 dict 정화 + 규칙 검증. 위반 시 RuleViolation(재생성 트리거)."""
    problems = []

    lines = script.get("lines") or []
    if not lines:
        raise RuleViolation("lines가 비어 있음")
    for line in lines:
        line["text"] = clean_text(str(line.get("text", "")))
        if not line["text"]:
            problems.append("빈 대사 라인 존재")

    full = " ".join(l["text"] for l in lines)
    bad = check_forbidden(full + " " + str(script.get("title", "")))
    if bad:
        problems.append(f"금지어 포함: {bad}")

    shocks = [l for l in lines if l.get("price_shock")]
    if len(shocks) != 1:
        problems.append(f"price_shock 라인이 {len(shocks)}개 (정확히 1개 필요)")
    elif not re.search(r"[\d,]+원", shocks[0]["text"]):
        problems.append("가격 라인에 숫자 금액(예: 49,900원)이 없음")

    hashtags = script.get("hashtags") or []
    if len(hashtags) != 3:
        problems.append(f"해시태그 {len(hashtags)}개 (3개 고정)")

    n_chars = len(full.replace(" ", ""))
    if strict_length and not (350 <= n_chars <= 450):
        problems.append(f"낭독 분량 공백 제외 {n_chars}자 (350~450자 필요)")

    if problems:
        raise RuleViolation("; ".join(problems))

    script["_char_count"] = n_chars
    return script
