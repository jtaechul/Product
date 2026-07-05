"""LLM 텍스트 생성 공용 체인 — Claude(품질 우선) → Gemini(폴백) → None.

CLAUDE.md AI 역할 분담: 훅·카피 등 고부가 텍스트는 Claude 우선, Gemini 폴백.
키가 하나도 없으면 None 반환 → 호출부는 반드시 결정적 템플릿 폴백을 갖춰야 한다.
비용: 짧은 텍스트라 회당 1원 미만 수준 (영상 생성과 달리 무시 가능).
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-5"      # 카피 품질/비용 균형
GEMINI_MODEL = "gemini-2.5-flash"


def generate_text(prompt: str, max_tokens: int = 500) -> str | None:
    """체인 순서대로 시도해 성공한 첫 결과를 반환. 전부 실패하면 None."""
    text = _try_claude(prompt, max_tokens)
    if text:
        return text
    text = _try_gemini(prompt)
    if text:
        return text
    log.info("LLM 체인 전부 불가 → 호출부 템플릿 폴백 사용")
    return None


def _try_claude(prompt: str, max_tokens: int) -> str | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # 선택 의존성 (미설치 환경 허용)

        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return (msg.content[0].text or "").strip() or None
    except Exception as e:  # noqa: BLE001
        log.info("Claude 호출 실패 → Gemini 폴백: %s", e)
        return None


def _try_gemini(prompt: str) -> str | None:
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    try:
        from google import genai

        client = genai.Client()
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        return (resp.text or "").strip() or None
    except Exception as e:  # noqa: BLE001
        log.info("Gemini 호출 실패: %s", e)
        return None
