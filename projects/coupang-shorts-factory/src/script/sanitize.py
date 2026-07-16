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
# ⚠️ 슬래시(/)·파이프(|)는 자막에 '구분기호'로 새어 들어가므로(모델이 예시 구분자를 흉내) 불허 → 제거.
_ALLOWED = re.compile(r"[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s.,?!%~\-()「」『』:·']+")

# 자막 칸 규격: 공백 포함 최대 글자수 / 칸당 최대 어절 수 (렌더 화면 폭·가독성 기준)
SUB_MAX_CHARS = 12
SUB_MAX_WORDS = 3
# 낭독 분량(공백 제외): 25~32초 목표(쇼츠 최적 길이 — 늘어지면 이탈). 무나레이션은 ≈0.14초/자.
CHAR_MIN, CHAR_MAX = 150, 230

# ⭐ 정식 제품명 감추기(2026-07-15 사용자 지시): 영상 텍스트(대사·자막·headline·title)에는 제품의
#   '종류/통상 명사'만 쓰고 브랜드·모델명은 넣지 않는다(정식명칭은 프로필 링크의 쇼핑페이지에서만 공개).
#   1차 방어는 프롬프트(script_gen.md '제품명 규칙'), 2차 방어가 여기다 — 모델이 흘린 '모델코드'
#   (영문+숫자가 섞인 토큰: MJJSQ05DY·DR-3000·V12 등, 정식 제품명의 대표 신호)를 결정론적으로 제거한다.
#   ⚠️ 측정 단위(500ml·1.2kg·60hz 등 '숫자+단위')는 스펙이므로 보존한다(오탐 금지).
_UNIT_SUFFIX = ("ml", "l", "cc", "w", "kw", "kwh", "kg", "g", "mg", "t", "cm", "mm", "m",
                "km", "nm", "gb", "tb", "mb", "kb", "mah", "wh", "hz", "khz", "mhz", "ghz",
                "k", "p", "fps", "dpi", "inch", "ppm", "rpm", "psi", "db", "lux", "lm")
_MEASURE_RE = re.compile(r"\d[\d.,]*(?:" + "|".join(_UNIT_SUFFIX) + r")$")
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-]*")
# 제품명이 아니라 '일반 기술용어'인 영숫자 토큰 — 오탐 방지로 보존한다.
_ALNUM_ALLOW = {"mp3", "mp4", "2d", "3d", "usb2", "usb3", "hdmi2", "fhd", "uhd",
                "type-c", "usb-c", "a4", "b5"}


def _strip_model_codes(text: str) -> str:
    """영문+숫자 혼합 토큰(모델코드)만 제거. 숫자+단위(스펙)·일반 기술용어는 보존."""
    def repl(m):
        tok = m.group(0)
        low = tok.lower()
        if low in _ALNUM_ALLOW or _MEASURE_RE.fullmatch(low):
            return tok
        if re.search(r"[A-Za-z]", tok) and re.search(r"\d", tok):
            return ""
        return tok
    return re.sub(r"\s{2,}", " ", _TOKEN_RE.sub(repl, text)).strip()


def _strip_terms(text: str, terms) -> str:
    """운영자가 명시한 '화면 금지어'(브랜드·정식명칭)를 제거. 짧은(1자) 토큰은 오탐 위험이라 제외."""
    for t in (terms or []):
        t = str(t).strip()
        if len(t) >= 2:
            text = re.sub(re.escape(t), "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip()


def hide_product_name(text: str, avoid_terms=None) -> str:
    """대사·자막·헤드라인·제목에서 정식 제품명 흔적(모델코드 + 명시 금지어)을 제거한다."""
    return _strip_model_codes(_strip_terms(text, avoid_terms))


def product_avoid_terms(product) -> list:
    """상품에서 '화면·설명에 숨길 이름'(브랜드·정식명) 후보를 뽑는다(일반 카테고리어는 최대한 보존).
    - 전체 상품명(정확 일치 제거) + (3어절 이상이면) 첫 토큰=브랜드.
      (2어절 이하 짧은 이름은 통째로만 제거 — 일반명 오탐 방지.)
    - 운영자가 지정한 avoid_onscreen/avoid_terms도 합친다.
    이 목록을 hide_product_name/sanitize_script에 넘기면 대사·자막·헤드라인·제목·설명에서 함께 제거된다."""
    if not isinstance(product, dict):
        return []
    terms = []
    name = str(product.get("name") or "").strip()
    if name:
        terms.append(name)
        toks = [t for t in name.split() if len(t) >= 2]
        if len(toks) >= 3:
            terms.append(toks[0])   # 브랜드(첫 토큰)
    extra = product.get("avoid_onscreen") or product.get("avoid_terms") or []
    if isinstance(extra, str):
        extra = [extra]
    for e in extra:
        if str(e).strip():
            terms.append(str(e).strip())
    seen, out = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t); out.append(t)
    return out


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


def sanitize_script(script: dict, strict_length: bool = True, avoid_terms=None) -> dict:
    """대본 dict 정화 + 규칙 검증. 위반 시 RuleViolation(재생성 트리거).

    avoid_terms: 화면에 노출하면 안 되는 브랜드·정식 제품명 토큰(선택). 상품 데이터에서 넘어온다.
    """
    problems = []

    lines = script.get("lines") or []
    if not lines:
        raise RuleViolation("lines가 비어 있음")
    repaired = 0
    for line in lines:
        # ⭐ 핵심규칙(사용자 확정 2026-07-12): 화면 리액션 추임새(react — ㅋㅋㅋ·실화냐 등) 전면 금지.
        #    모델이 출력해도 여기서 무조건 제거한다. 렌더·QA도 각각 금지·차단한다.
        line.pop("react", None)
        # 정식 제품명(브랜드·모델코드) 흔적 제거 → 종류/통상 명사만 남긴다(2026-07-15).
        line["text"] = hide_product_name(clean_text(str(line.get("text", ""))), avoid_terms)
        if not line["text"]:
            problems.append("빈 대사 라인 존재")
            continue
        if _normalize_subs(line):
            repaired += 1
    if repaired:
        print(f"[sanitize] subs 계약 위반/누락 라인 {repaired}개 → 어절 경계 기준 자동 복구")

    # 제목 이모지 제거(핵심규칙: 이모지 금지) + 정식 제품명(브랜드·모델코드) 제거 — 종류 키워드만 남긴다
    if script.get("title"):
        script["title"] = hide_product_name(clean_text(str(script["title"])), avoid_terms)
    # headline(폭로 포맷 화면 상단 뉴스 헤더)도 같은 규칙으로 정화 — 이모지·슬래시·파이프 + 제품명 제거
    if script.get("headline"):
        script["headline"] = hide_product_name(clean_text(str(script["headline"])), avoid_terms)
    # description_body(유튜브 설명란 본문)에서도 정식 제품명 제거(2026-07-16) — 줄바꿈은 보존.
    if script.get("description_body"):
        body = str(script["description_body"])
        script["description_body"] = "\n".join(hide_product_name(ln, avoid_terms) for ln in body.split("\n"))
    # concept(기획서: 의도·타깃·후킹) — 운영자 검토용 표시 텍스트, 이모지·특수기호 정화
    concept = script.get("concept")
    if isinstance(concept, dict):
        script["concept"] = {k: clean_text(str(v)) for k, v in concept.items() if v}
    # 각 라인 scene(스토리보드 장면 묘사) 정화 (없으면 빈 문자열)
    for line in lines:
        if line.get("scene"):
            line["scene"] = clean_text(str(line["scene"]))

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

    # 해시태그: 모델(특히 Gemini)이 개수를 안 지켜도 3개로 자동 교정한다 —
    #   정규화(#+공백제거) + 중복 제거 + 상위 3개만. 3개 미만일 때만 진짜 문제로 본다.
    raw_tags = script.get("hashtags") or []
    norm_tags = []
    for t in raw_tags:
        tag = "#" + re.sub(r"\s+", "", str(t).lstrip("#"))
        if len(tag) > 1 and tag not in norm_tags:
            norm_tags.append(tag)
    if len(norm_tags) > 3:
        norm_tags = norm_tags[:3]
    script["hashtags"] = norm_tags
    if len(norm_tags) < 3:
        problems.append(f"해시태그 {len(norm_tags)}개 (3개 필요 — 자동교정 후에도 부족)")

    n_chars = len(full.replace(" ", ""))
    if strict_length and not (CHAR_MIN <= n_chars <= CHAR_MAX):
        problems.append(f"낭독 분량 공백 제외 {n_chars}자 ({CHAR_MIN}~{CHAR_MAX}자 필요)")

    if problems:
        raise RuleViolation("; ".join(problems))

    script["_char_count"] = n_chars
    return script
