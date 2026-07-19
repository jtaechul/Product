"""M3. 대본 생성 — Claude 또는 Gemini (config: script.provider).

product.json + §7 프롬프트 템플릿 → script.json (JSON only 강제).
금지어/형식 위반 시 위반 내용을 피드백으로 넣어 1회 재생성.

프로바이더(2026-07-13 사용자 확정 — 구어체 문구는 Gemini가 더 낫다는 판단):
  - claude : Anthropic Messages (SHORTS_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY)
  - gemini : Gemini generateContent (SHORTS_GEMINI_API_KEY / GEMINI_API_KEY) — 텍스트 전용.
             ⚠️ 유료 '영상' 생성(Veo)은 여전히 전면 금지. 여기서는 '텍스트'만 생성한다(초저가).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from src.script.sanitize import (
    RuleViolation,
    build_subs,
    check_forbidden,
    clean_text,
    hide_product_name,
    product_avoid_terms,
    sanitize_script,
    strip_target_words,
)

_STAGE_ROLE = {1: "훅(한줄썰 사건의 구체적 손해를 보여줌 — 주제는 드러내고 해결책만 감춤, 추상 선언·시대드립 금지)",
               2: "공감 확산(앞 줄을 지시어로 즉시 이어받아 같은 장면 심화)",
               3: "원흉 지목", 4: "제품 정체 공개(종류·킬러스펙만)", 5: "증거·반응(루프 이음새)"}
# 가격 표현(숫자+원 / N만원) — sanitize_script(line 204)와 동일 규칙을 라인 단위로도 강제한다.
_PRICE_RE = re.compile(r"\d[\d,]*\s*원|\d+\s*만\s*원")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def anthropic_key() -> str | None:
    return (os.environ.get("SHORTS_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None


def gemini_key() -> str | None:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("SHORTS_GEMINI_API_KEY") or "").strip() or None


def script_provider(settings: dict) -> str:
    return str(settings.get("script", {}).get("provider", "claude")).strip().lower()


def have_script_key(settings: dict) -> bool:
    """선택된 프로바이더의 키가 있는지 (파이프라인 사전 점검용)."""
    return bool(gemini_key()) if script_provider(settings) == "gemini" else bool(anthropic_key())


def missing_key_hint(settings: dict) -> str:
    if script_provider(settings) == "gemini":
        return "대본 프로바이더=gemini인데 GEMINI_API_KEY가 없습니다."
    return "대본 프로바이더=claude인데 SHORTS_ANTHROPIC_API_KEY(또는 ANTHROPIC_API_KEY)가 없습니다."


def generate_script(product: dict, settings: dict) -> dict:
    cfg = settings.get("script", {})
    provider = script_provider(settings)
    max_tokens = int(cfg.get("max_tokens", 4000))
    model = (cfg.get("gemini_model", "gemini-2.5-flash") if provider == "gemini"
             else cfg.get("model", "claude-sonnet-4-6"))

    template = (PROJECT_ROOT / "config" / "prompts" / "script_gen.md").read_text(encoding="utf-8")
    system = template.replace("{channel_name}", settings.get("channel", {}).get("name", "미래상점"))
    user_msg = "상품 데이터:\n" + json.dumps(product, ensure_ascii=False, indent=1)
    allow_price = bool(product.get("_price_ok"))
    if allow_price:   # ⭐ 예외(2026-07-18 사용자 확정): 운영자가 기획 방향(4안)에서 가격을 직접 언급
        user_msg += ("\n\n[운영자 가격 언급 예외] 운영자가 기획 방향에서 가격을 직접 언급했다 — "
                     "이번 대본에서는 '작성 규칙 2(가격 금지)'를 해제한다. 운영자가 준 가격 맥락 그대로만 "
                     "언급하고, 지어내거나 과장('반값' 등 비교 단정)하지 마라.")

    # 화면 금지어(브랜드·정식 제품명) — 상품명에서 자동 도출(+운영자 지정) → 대사·자막·헤드라인·제목에서 제거.
    #   (정식명칭은 링크의 쇼핑페이지에서만 공개. 일반 카테고리어는 최대한 보존.)
    avoid = product_avoid_terms(product)

    feedback = None
    ATTEMPTS = 4   # LLM이 가끔 깨진 JSON·짧은 분량을 낸다. 2회로는 자주 최종 실패 → 넉넉히 재시도(각 ≈5원).
    for attempt in range(1, ATTEMPTS + 1):
        extra = ""
        if feedback and "낭독 분량" in feedback:
            extra = ("\n분량 해결법: 본문(훅 제외) 공백 제외 110~170자 사이로 맞춰라 — 모자라면 웃긴 사용 "
                     "장면 라인을 더하고, 넘치면 설명 라인을 잘라라. subs 계약(이어 붙이면 text와 일치)도 유지하라.")
        if feedback and "구간 배분" in feedback:
            extra += ("\n배분 해결법: ②③(문제)은 합쳐 1~2줄로 압축하고, ④를 2~3줄(남들이 못한 것·"
                      "기능구조·작동방식), ⑤를 1줄(결과 체감)로 써 제품 구간이 절반 가까이 되게 하라.")
        if feedback and "토막" in feedback:
            extra += ("\n토막 해결법: 10자 미만 조각 라인을 앞뒤 줄과 합쳐, 라인당 공백 포함 16~32자의 "
                      "완결 문장으로 다시 써라(연결어로 앞 줄을 이어받기).")
        if feedback and ("delimiter" in feedback or "JSON" in feedback or "Expecting" in feedback):
            extra += "\nJSON 형식 엄수: 유효한 JSON만 출력(마크다운·주석·후행 콤마 금지, 모든 키/값 쉼표 확인)."
        content = user_msg if not feedback else (
            f"{user_msg}\n\n이전 시도가 규칙을 위반했다: {feedback}{extra}\n규칙을 지켜 다시 작성하라.")

        if provider == "gemini":
            text = _gemini_generate(model, system, content, max_tokens)
        else:
            text = _anthropic_generate(model, system, content, max_tokens)

        try:
            script = _parse_json(text)
            # 앞 2회는 분량 엄격, 이후엔 완화 — 유효한 대본이 '조금 짧다'는 이유로 최종 실패하지 않게.
            script = sanitize_script(script, strict_length=(attempt <= 2), avoid_terms=avoid,
                                     allow_price=allow_price)
            if attempt <= 2:   # 개연성 가드 — 스토리 스파인(한줄썰) 없으면 재생성 유도(마지막 시도엔 완화)
                issue = _story_issues(script)
                if issue:
                    raise RuleViolation(issue)
            break
        except (RuleViolation, ValueError) as e:
            feedback = str(e)[:400]
            last = attempt == ATTEMPTS
            print(f"[script] {attempt}/{ATTEMPTS}차 생성 규칙 위반 → {'중단' if last else '재생성'}: {feedback}")
            if last:
                raise RuleViolation(f"{ATTEMPTS}회 재생성 후에도 위반: {feedback}")

    # §3.1 고지문·링크는 모델 출력을 신뢰하지 않고 코드로 강제 재구성(2026-07-17 사용자 확정):
    #   고정 댓글은 링크가 '클릭 가능'하다는 점을 활용 → ① 고지문 먼저 ② 바로 밑에 미래마켓 스토어 링크.
    #   스토어 페이지(store.html)에 각 상품의 쿠팡 어필리에이트 링크 + 자체 고지문이 이미 있다(구매 경로 유지).
    store_url = settings.get("channel", {}).get("store_url", "https://miraemarket.pages.dev").rstrip("/")
    # 링크 형식(2026-07-17 사용자 확정): 도메인 뒤 "/" 필수 + URL은 줄 단독(유튜브 자동 링크 인식).
    # 실제 업로드 댓글은 youtube.build_pinned_comment(상품 번호 딥링크 포함)가 다시 만든다 — 여긴 미리보기용.
    script["pinned_comment"] = (
        f"{DISCLOSURE}\n미래마켓에서 이 제품 보기 →\n{store_url}/")
    print(f"[script] 생성 완료: '{script.get('title', '')[:40]}' "
          f"라인 {len(script['lines'])}개, 공백 제외 {script.get('_char_count', '?')}자 "
          f"(프로바이더 {provider}/{model})")
    return script


_FIELD_SPEC = {
    "title": "유튜브 제목 = thumb_hook과 완전히 동일한 문장(포맷 v2, 2026-07-18 사용자 확정 — 시스템이 훅으로 자동 통일). 공백 포함 12~25자 궁금증 문장, 길게 짓지 마라. 타깃·주거 서술어(자취·원룸 등)·브랜드·정식 제품명·가격 금지",
    "headline": "영상 상단 뉴스 헤드라인 — 폭로 기사 제목 톤(문어체), 제품명 감춤, 12~22자",
    "thumb_hook": "0:00 훅 카드 문구 — 이 문장이 곧 유튜브 제목이 되고, 나레이션 첫마디로 이 문장을 그대로 읽는다(포맷 v2). 공백 포함 12~25자, 1~2줄. concept.한줄썰의 '그 상황'이 한눈에 읽히면서 결말이 궁금해지는 한 방. 뜬구름·정체불명 문구 금지, 구체적으로. 브랜드·정식 제품명·가격·타깃 서술어(자취 등) 금지",
    "description": "유튜브 설명란 본문 — 간결·자연스럽게, 정식 제품명·브랜드·가격·금액 금지(제품은 종류로만 지칭)",
    "hashtags": "해시태그 정확히 3개(문자열 리스트)",
}


def regenerate_field(plan: dict, field: str, product: dict, settings: dict):
    """검수 단계 — 기획의 한 항목(title/headline/description/hashtags)만 '새 안 1개'로 재생성해 반환.
    텍스트 전용(Gemini/Claude). 나머지 대본·기획은 그대로 두고 이 필드만 바꾼다."""
    field = field.strip().lower()
    if field not in _FIELD_SPEC:
        raise ValueError(f"regen 대상 오류: {field} (가능: {list(_FIELD_SPEC)})")
    cfg = settings.get("script", {})
    provider = script_provider(settings)
    model = (cfg.get("gemini_model", "gemini-2.5-flash") if provider == "gemini"
             else cfg.get("model", "claude-sonnet-4-6"))
    ctx = {"concept": plan.get("concept"), "제품": product.get("name"),
           "대사": [l.get("text") for l in plan.get("lines", [])],
           "현재_title": plan.get("title"), "현재_headline": plan.get("headline"),
           "현재_hashtags": plan.get("hashtags"), "현재_description": plan.get("description_body")}
    want = "['태그1','태그2','태그3']" if field == "hashtags" else '"..."'
    system = "너는 한국어 쇼츠 편집자다. 요청한 항목만 새로 지어 JSON으로만 반환한다. 마크다운·설명 금지."
    prompt = (
        f"아래 영상 맥락을 보고 '{field}'를 새로운 안 1개로 다시 지어라: {_FIELD_SPEC[field]}.\n"
        "기존 것과 확실히 다르게, 더 낫게. 이모지·특수기호·최고/유일/100% 같은 단정 표현·금액 금지.\n"
        f"맥락 JSON: {json.dumps(ctx, ensure_ascii=False)}\n"
        f'출력(JSON만): {{"value": {want}}}')
    text = (_gemini_generate(model, system, prompt, 800) if provider == "gemini" and gemini_key()
            else _anthropic_generate(model, system, prompt, 800))
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0)) if m else {}
    if "value" not in data:
        raise ValueError(f"재생성 응답에 value 없음: {text[:120]}")
    val = data["value"]
    if field == "title":   # 제목=순수 특장점(2026-07-17) — 재생성 경로에도 타깃 서술어 하드 제거
        val = strip_target_words(str(val))
    return val


def regenerate_line(plan: dict, line_i: int, product: dict, settings: dict) -> dict:
    """검수 — 대본에서 '한 라인의 문구(text)'만 새로 지어 {text, subs}로 반환한다.
    나머지 라인·stage·punch·scene은 그대로 두고 이 줄의 문구만 바꾼다. 스토리 연결성을 지키려고
    한줄썰(스파인)·바로 앞뒤 라인을 문맥으로 주고, 앞줄을 이어받아 뒷줄로 넘어가게 요청한다.
    가드레일(제품명 감춤·가격/금지어·이모지 제거)과 subs 계약(join==text)은 코드가 강제한다."""
    lines = plan.get("lines") or []
    if not (0 <= line_i < len(lines)):
        raise ValueError(f"라인 번호 범위 밖: {line_i} (0~{len(lines) - 1})")
    cfg = settings.get("script", {})
    provider = script_provider(settings)
    model = (cfg.get("gemini_model", "gemini-2.5-flash") if provider == "gemini"
             else cfg.get("model", "claude-sonnet-4-6"))
    cur = lines[line_i]
    prev_t = lines[line_i - 1].get("text", "") if line_i > 0 else "(없음 — 이 줄이 첫 줄=폭로 훅)"
    next_t = lines[line_i + 1].get("text", "") if line_i + 1 < len(lines) else "(없음 — 이 줄이 마지막=루프 이음새)"
    spine = str((plan.get("concept") or {}).get("한줄썰") or "").strip() or "(미정)"
    role = _STAGE_ROLE.get(int(cur.get("stage", 0) or 0), "전개")
    avoid = product_avoid_terms(product)

    system = ("너는 한국어 쇼츠 대본 작가다. 요청한 '한 줄'만 새로 지어 JSON으로만 반환한다. "
              "마크다운·설명·백틱 금지. 만담 드립으로 웃기되 스토리 흐름을 지킨다.")
    prompt = (
        f"아래 쇼츠 대본에서 {line_i + 1}번째 줄의 '문구(text)'만 새로 지어라.\n"
        f"[이 영상의 한 줄 썰(모든 줄이 이 사건 하나로 이어짐)] {spine}\n"
        f"[이 줄의 역할] {cur.get('stage', '?')}단계 = {role}\n"
        f"[바로 앞 줄] {prev_t}\n"
        f"[바로 뒤 줄] {next_t}\n"
        "★ 조건: 앞 줄에서 자연스럽게 이어받아 뒤 줄로 매끄럽게 넘어가게(개연성) + 만담 드립으로 웃기게 "
        "+ 공백 포함 16~32자의 완결된 구어체 문장 한 줄(10자 미만 토막 금지). 앞뒤에 없던 새 소재·새 장소를 뜬금없이 꺼내지 마라.\n"
        "금지: 제품 브랜드·모델명·정식명칭(종류 일반명사로만), 금액·가격, 이모지·특수기호, 최고/유일/100% 단정.\n"
        f"현재 문구(참고 — 이것과 확실히 다르고 더 웃기게): {cur.get('text', '')}\n"
        '출력(JSON만): {"text": "새 문구 한 줄"}')

    for attempt in range(1, 4):   # 금지어·가격·형식 위반 방어(각 ≈2원)
        text = (_gemini_generate(model, system, prompt, 400) if provider == "gemini" and gemini_key()
                else _anthropic_generate(model, system, prompt, 400))
        m = re.search(r"\{.*\}", text, re.S)
        try:
            raw = str((json.loads(m.group(0)) if m else {}).get("text", "")).strip()
        except json.JSONDecodeError:
            raw = ""
        if not raw:
            continue
        # 생성 때와 동일한 라인 단위 가드레일을 적용한다: 제품명(브랜드·모델코드) 제거 → 이모지·특수기호
        #   정리 → 금지어(최고·유일 등)·가격(숫자+원) 차단. subs 계약(join==text)은 build_subs가 보장.
        #   (sanitize_script는 punch 1개·분량 등 '스크립트 전체' 규칙까지 봐서 한 줄만 태우면 오탐 → 라인 헬퍼로 정확히.)
        newt = clean_text(hide_product_name(raw, avoid))
        if newt and len(newt.replace(" ", "")) >= 4 and not check_forbidden(newt) \
                and (product.get("_price_ok") or not _PRICE_RE.search(newt)):
            print(f"[script] 라인 {line_i} 문구 재생성({provider}/{model}, {attempt}차): {newt}")
            return {"text": newt, "subs": build_subs(newt)}
        print(f"[script] 라인 {line_i} 문구 {attempt}차 규칙 위반/부적합 → 재시도")
    raise RuleViolation("라인 문구 재생성 실패 — 유효한 문구를 얻지 못했습니다(가격·금지어·형식). 다시 시도하세요.")


def _anthropic_generate(model: str, system: str, content: str, max_tokens: int) -> str:
    key = anthropic_key()
    if not key:
        raise RuntimeError("대본 생성용 Anthropic API 키가 없습니다.")
    import anthropic  # 무거운 임포트는 사용 시점에
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": content}])
    u = getattr(resp, "usage", None)
    if u:
        print(f"[script] 토큰 사용(claude): 입력 {u.input_tokens:,} / 출력 {u.output_tokens:,}")
    return "".join(b.text for b in resp.content if b.type == "text")


def _gemini_generate(model: str, system: str, content: str, max_tokens: int) -> str:
    """Gemini generateContent로 대본 텍스트 생성(JSON 강제). 텍스트 전용 — 영상 생성 아님."""
    key = gemini_key()
    if not key:
        raise RuntimeError("대본 생성용 Gemini API 키가 없습니다 (GEMINI_API_KEY).")
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": content}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens, "temperature": 1.0,
            "responseMimeType": "application/json",
            # ⚠️ 2.5 Flash는 '사고(thinking)'가 기본 ON이라 출력 예산을 잡아먹어 JSON이 잘린다.
            #    구조화 JSON 생성에는 사고를 끄고(0) 전체 예산을 답에 쓴다.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    r = requests.post(f"{GEMINI_BASE}/models/{model}:generateContent",
                      headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                      json=body, timeout=90)
    if not r.ok:
        raise RuntimeError(f"Gemini 대본 생성 실패 {r.status_code}: {r.text[:300]}")
    data = r.json()
    um = data.get("usageMetadata") or {}
    if um:
        print(f"[script] 토큰 사용(gemini): 입력 {um.get('promptTokenCount', '?')} / "
              f"출력 {um.get('candidatesTokenCount', '?')} / 사고 {um.get('thoughtsTokenCount', 0)}")
    cands = data.get("candidates") or []
    if not cands:
        raise ValueError(f"Gemini 응답에 candidates 없음: {str(data)[:200]}")
    fin = cands[0].get("finishReason")
    parts = (cands[0].get("content") or {}).get("parts") or []
    txt = "".join(p.get("text", "") for p in parts)
    if fin and fin not in ("STOP", "MAX_TOKENS") or not txt:
        raise ValueError(f"Gemini 비정상 종료(finishReason={fin}, len={len(txt)})")
    if fin == "MAX_TOKENS":
        print(f"[script] 경고: Gemini 출력이 max_tokens에 걸림 → 잘렸을 수 있음(파서가 판단)")
    return txt


def _story_issues(script: dict) -> str | None:
    """개연성 최소 가드 — 모든 라인이 '하나의 사건'으로 이어지도록 concept.한줄썰(스토리 스파인)이
    선언됐는지만 기계적으로 확인한다. 의미적 연결성은 프롬프트가 책임지고, 코드는 스파인 존재 여부만
    보므로 오검출(멀쩡한 대본을 잘못 막음)이 없다. 스파인이 있으면 모델이 그걸 축으로 라인을 잇는다."""
    concept = script.get("concept") or {}
    spine = str(concept.get("한줄썰") or concept.get("throughline") or "").strip()
    if len(spine) < 6:
        return ("concept.한줄썰(이 영상 전체를 관통하는 '하나의 사건'을 한 줄로)이 비었다 — "
                "사건을 정하고 8~11줄 모두가 그 사건을 시간순·인과로 이어가게 하라.")
    return None


def _parse_json(text: str) -> dict:
    t = re.sub(r"```(?:json)?", "", text).strip()   # 마크다운 코드펜스 제거(위치 무관)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("응답에 JSON 객체가 없음")
    blob = t[start:end + 1]
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        # 흔한 LLM JSON 오류 자동 보정: 후행 콤마 제거 후 1회 재시도(그래도 깨지면 상위 루프가 재생성)
        data = json.loads(re.sub(r",(\s*[}\]])", r"\1", blob))
    for k in ("concept", "title", "lines", "hashtags", "description_body"):
        if k not in data:
            raise ValueError(f"필수 키 누락: {k}")
    return data
