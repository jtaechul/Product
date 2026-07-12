"""M3 후처리 — 금지어·특수기호 필터 + 길이 검증 + 자막 칸(subs) 계약 보장 (스펙 §3.3, §M3).

표시광고법 저촉 우려 표현(절대적·의학적 단정)을 차단하고, 이모지·특수기호를 제거한다.
'대본이 곧 자막' 원칙(2026-07-12 개편): 각 라인의 subs(자막 칸)는
  " ".join(subs) == text (띄어쓰기까지 완전 일치)
계약을 반드시 만족해야 렌더러가 재분할 없이 그대로 띄울 수 있다. 모델 출력이 계약을
어기면 어절 경계 기준으로 자동 복구한다(재생성 크레딧 낭비 방지).
규칙 위반은 RuleViolation으로 보고해 generate.py가 1회 재생성하도록 한다.
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

# 자막 칸 규격: 공백 포함 최대 글자수 / 칸당 최대 어절 수 (렌더 화면 폭·가독성 기준)
SUB_MAX_CHARS = 12
SUB_MAX_WORDS = 3
# 낭독 분량(공백 제외): 빠른 템포 30~40초 목표 (Typecast tempo 1.3 기준 약 6.5자/초)
CHAR_MIN, CHAR_MAX = 180, 280
REACT_MAX_COUNT = 6
REACT_MAX_CHARS = 6


class RuleViolation(Exception):
    pass


def clean_text(text: str) -> str:
    """이모지·특수기호 제거 + 공백 정리."""
    return re.sub(r"\s+", " ", _ALLOWED.sub("", text)).strip()


def check_forbidden(text: str) -> list:
    return [w for w in FORBIDDEN if w in text]


def build_subs(text: str) -> list:
    """어절 경계 기준 자막 칸 자동 생성(모델 subs가 없거나 계약 위반일 때의 복구 경로).
    1~3어절씩, 공백 포함 SUB_MAX_CHARS 이하로 묶는다. 띄어쓰기는 절대 훼손하지 않는다."""
    toks = text.split()
    subs, cur = [], ""
    for w in toks:
        cand = f"{cur} {w}".strip()
        if cur and (len(cand) > SUB_MAX_CHARS or len(cur.split()) >= SUB_MAX_WORDS):
            subs.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        subs.append(cur)
    # 꼬리가 한두 글자면 앞 칸에 합침(찰나 팝업 방지)
    if len(subs) >= 2 and len(subs[-1]) <= 2 and len(f"{subs[-2]} {subs[-1]}") <= SUB_MAX_CHARS + 2:
        subs[-2:] = [f"{subs[-2]} {subs[-1]}"]
    return subs


def _normalize_subs(line: dict) -> bool:
    """라인 subs를 계약(" ".join(subs)==text)에 맞게 정규화. 복구했으면 True 반환."""
    text = line["text"]
    raw = line.get("subs")
    if isinstance(raw, list) and raw:
        subs = [re.sub(r"\s+", " ", clean_text(str(s))).strip() for s in raw]
        subs = [s for s in subs if s]
        if subs and " ".join(subs) == text and all(len(s) <= SUB_MAX_CHARS + 2 for s in subs):
            line["subs"] = subs
            return False
    line["subs"] = build_subs(text)
    return True


def sanitize_script(script: dict, strict_length: bool = True) -> dict:
    """대본 dict 정화 + 규칙 검증. 위반 시 RuleViolation(재생성 트리거)."""
    problems = []

    lines = script.get("lines") or []
    if not lines:
        raise RuleViolation("lines가 비어 있음")
    repaired = 0
    react_seen = 0
    for line in lines:
        line["text"] = clean_text(str(line.get("text", "")))
        if not line["text"]:
            problems.append("빈 대사 라인 존재")
            continue
        if _normalize_subs(line):
            repaired += 1
        # react: 웃음 추임새 오버레이 — punch 라인 금지, 개수·길이 상한, 초과분은 조용히 제거
        react = clean_text(str(line.get("react", "") or ""))[:REACT_MAX_CHARS].strip()
        if react and not line.get("punch") and react_seen < REACT_MAX_COUNT:
            line["react"] = react
            react_seen += 1
        else:
            line.pop("react", None)
    if repaired:
        print(f"[sanitize] subs 계약 위반/누락 라인 {repaired}개 → 어절 경계 기준 자동 복구")

    full = " ".join(l["text"] for l in lines)
    bad = check_forbidden(full + " " + str(script.get("title", "")))
    if bad:
        problems.append(f"금지어 포함: {bad}")

    punches = [l for l in lines if l.get("punch")]
    if len(punches) != 1:
        problems.append(f"punch(쉐이크 강조) 라인이 {len(punches)}개 (정확히 1개 필요 — 훅)")

    # 가격 완전 제거(전략 확정): 대사에 금액 표현(숫자+원, N만원)이 있으면 재생성.
    # '원룸'·'지원' 등은 앞에 숫자가 없어 오탐 아님. 스펙(500ml·3분·1.2킬로그램)도 통과.
    if re.search(r"\d[\d,]*\s*원|\d+\s*만\s*원", full):
        problems.append("금액 표현 포함 — 가격은 영상에서 완전히 뺀다(링크로만 안내)")

    hashtags = script.get("hashtags") or []
    if len(hashtags) != 3:
        problems.append(f"해시태그 {len(hashtags)}개 (3개 고정)")

    n_chars = len(full.replace(" ", ""))
    if strict_length and not (CHAR_MIN <= n_chars <= CHAR_MAX):
        problems.append(f"낭독 분량 공백 제외 {n_chars}자 ({CHAR_MIN}~{CHAR_MAX}자 필요)")

    if problems:
        raise RuleViolation("; ".join(problems))

    script["_char_count"] = n_chars
    return script
