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

from src.script.sanitize import RuleViolation, sanitize_script

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def anthropic_key() -> str | None:
    return (os.environ.get("SHORTS_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None


def gemini_key() -> str | None:
    return (os.environ.get("SHORTS_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip() or None


def script_provider(settings: dict) -> str:
    return str(settings.get("script", {}).get("provider", "claude")).strip().lower()


def have_script_key(settings: dict) -> bool:
    """선택된 프로바이더의 키가 있는지 (파이프라인 사전 점검용)."""
    return bool(gemini_key()) if script_provider(settings) == "gemini" else bool(anthropic_key())


def missing_key_hint(settings: dict) -> str:
    if script_provider(settings) == "gemini":
        return "대본 프로바이더=gemini인데 SHORTS_GEMINI_API_KEY(또는 GEMINI_API_KEY)가 없습니다."
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

    # 화면 금지어(브랜드·정식 제품명) — 운영자가 상품에 avoid_onscreen을 지정하면 대사·자막에서 제거한다.
    #   (미지정이면 프롬프트 + 모델코드 자동제거만으로 방어. 정식명칭은 링크의 쇼핑페이지에서만 공개.)
    avoid = product.get("avoid_onscreen") or product.get("avoid_terms") or []
    if isinstance(avoid, str):
        avoid = [avoid]

    feedback = None
    ATTEMPTS = 4   # LLM이 가끔 깨진 JSON·짧은 분량을 낸다. 2회로는 자주 최종 실패 → 넉넉히 재시도(각 ≈5원).
    for attempt in range(1, ATTEMPTS + 1):
        extra = ""
        if feedback and "낭독 분량" in feedback:
            extra = ("\n분량 해결법: 공백 제외 190~260자 사이로 맞춰라 — 모자라면 웃긴 사용 장면 라인을 "
                     "더하고, 넘치면 설명 라인을 잘라라. subs 계약(이어 붙이면 text와 일치)도 유지하라.")
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
            script = sanitize_script(script, strict_length=(attempt <= 2), avoid_terms=avoid)
            break
        except (RuleViolation, ValueError) as e:
            feedback = str(e)[:400]
            last = attempt == ATTEMPTS
            print(f"[script] {attempt}/{ATTEMPTS}차 생성 규칙 위반 → {'중단' if last else '재생성'}: {feedback}")
            if last:
                raise RuleViolation(f"{ATTEMPTS}회 재생성 후에도 위반: {feedback}")

    # §3.1 고지문·링크는 모델 출력을 신뢰하지 않고 코드로 강제 재구성
    script["pinned_comment"] = (
        f"제품 정보는 여기서 확인 → {product.get('affiliate_url', '')}\n{DISCLOSURE}")
    print(f"[script] 생성 완료: '{script.get('title', '')[:40]}' "
          f"라인 {len(script['lines'])}개, 공백 제외 {script.get('_char_count', '?')}자 "
          f"(프로바이더 {provider}/{model})")
    return script


_FIELD_SPEC = {
    "title": "유튜브 제목 — ①훅의 궁금증 + 검색될 일반 카테고리 키워드(제습기·고데기 등), 브랜드·모델명·정식 제품명 금지, 40자 이내, 낚시·가격 표기 금지",
    "headline": "영상 상단 뉴스 헤드라인 — 폭로 기사 제목 톤(문어체), 제품명 감춤, 12~22자",
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
    return data["value"]


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
        raise RuntimeError("대본 생성용 Gemini API 키가 없습니다 (SHORTS_GEMINI_API_KEY / GEMINI_API_KEY).")
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
    for k in ("title", "lines", "hashtags", "description_body"):
        if k not in data:
            raise ValueError(f"필수 키 누락: {k}")
    return data
