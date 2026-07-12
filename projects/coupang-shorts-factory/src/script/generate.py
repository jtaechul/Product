"""M3. 대본 생성 — Anthropic API (모델은 config, 스펙 §M3: claude-sonnet-4-6).

product.json + §7 프롬프트 템플릿 → script.json (JSON only 강제).
금지어/형식 위반 시 위반 내용을 피드백으로 넣어 1회 재생성.
API 키: SHORTS_ANTHROPIC_API_KEY(우선) 또는 ANTHROPIC_API_KEY(저장소 공용 폴백).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from src.script.sanitize import RuleViolation, sanitize_script

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다"


def anthropic_key() -> str | None:
    return (os.environ.get("SHORTS_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None


def generate_script(product: dict, settings: dict) -> dict:
    key = anthropic_key()
    if not key:
        raise RuntimeError(
            "대본 생성용 Anthropic API 키가 없습니다. SHORTS_ANTHROPIC_API_KEY 또는 "
            "ANTHROPIC_API_KEY 시크릿을 등록하세요.")

    import anthropic  # 무거운 임포트는 사용 시점에
    client = anthropic.Anthropic(api_key=key)
    cfg = settings.get("script", {})
    model = cfg.get("model", "claude-sonnet-4-6")

    template = (PROJECT_ROOT / "config" / "prompts" / "script_gen.md").read_text(encoding="utf-8")
    system = template.replace("{channel_name}", settings.get("channel", {}).get("name", "미래상점"))
    user_msg = "상품 데이터:\n" + json.dumps(product, ensure_ascii=False, indent=1)

    feedback = None
    for attempt in (1, 2):  # 위반 시 1회 재생성 (스펙 §M3)
        extra = ""
        if feedback and "낭독 분량" in feedback:
            extra = ("\n분량 해결법: 라인 수를 15~20개로 늘리고, 셀링포인트마다 구체적 사용 장면을 "
                     "한 라인씩 추가해 공백 제외 350자를 반드시 넘겨라.")
        content = user_msg if not feedback else (
            f"{user_msg}\n\n이전 시도가 규칙을 위반했다: {feedback}{extra}\n규칙을 지켜 다시 작성하라.")
        resp = client.messages.create(
            model=model,
            max_tokens=int(cfg.get("max_tokens", 4000)),
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        u = getattr(resp, "usage", None)
        if u:
            print(f"[script] 토큰 사용: 입력 {u.input_tokens:,} / 출력 {u.output_tokens:,}")
        text = "".join(b.text for b in resp.content if b.type == "text")
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
          f"라인 {len(script['lines'])}개, 공백 제외 {script.get('_char_count', '?')}자 (모델 {model})")
    return script


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
