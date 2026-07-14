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

    feedback = None
    for attempt in (1, 2):  # 위반 시 1회 재생성 (스펙 §M3)
        extra = ""
        if feedback and "낭독 분량" in feedback:
            extra = ("\n분량 해결법: 공백 제외 190~260자 사이로 맞춰라 — 모자라면 웃긴 사용 장면 라인을 "
                     "더하고, 넘치면 설명 라인을 잘라라. subs 계약(이어 붙이면 text와 일치)도 유지하라.")
        content = user_msg if not feedback else (
            f"{user_msg}\n\n이전 시도가 규칙을 위반했다: {feedback}{extra}\n규칙을 지켜 다시 작성하라.")

        if provider == "gemini":
            text = _gemini_generate(model, system, content, max_tokens)
        else:
            text = _anthropic_generate(model, system, content, max_tokens)

        try:
            script = _parse_json(text)
            script = sanitize_script(script, strict_length=(attempt == 1))
            break
        except (RuleViolation, ValueError) as e:
            feedback = str(e)[:400]
            print(f"[script] {attempt}차 생성 규칙 위반 → {'재생성' if attempt == 1 else '중단'}: {feedback}")
            if attempt == 2:
                raise RuleViolation(f"재생성 후에도 위반: {feedback}")

    # §3.1 고지문·링크는 모델 출력을 신뢰하지 않고 코드로 강제 재구성
    script["pinned_comment"] = (
        f"제품 정보는 여기서 확인 → {product.get('affiliate_url', '')}\n{DISCLOSURE}")
    print(f"[script] 생성 완료: '{script.get('title', '')[:40]}' "
          f"라인 {len(script['lines'])}개, 공백 제외 {script.get('_char_count', '?')}자 "
          f"(프로바이더 {provider}/{model})")
    return script


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
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 1.0,
                             "responseMimeType": "application/json"},
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
              f"출력 {um.get('candidatesTokenCount', '?')}")
    cands = data.get("candidates") or []
    if not cands:
        raise ValueError(f"Gemini 응답에 candidates 없음: {str(data)[:200]}")
    parts = (cands[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts)


def _parse_json(text: str) -> dict:
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("응답에 JSON 객체가 없음")
    data = json.loads(t[start:end + 1])
    for k in ("title", "lines", "hashtags", "description_body"):
        if k not in data:
            raise ValueError(f"필수 키 누락: {k}")
    return data
