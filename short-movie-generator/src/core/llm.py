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
        # content에는 thinking 블록이 섞일 수 있음 → text 블록만 추출
        parts = [getattr(b, "text", "") for b in msg.content
                 if getattr(b, "type", "") == "text"]
        return "\n".join(p for p in parts if p).strip() or None
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001  # pyo3 PanicException 등 BaseException까지 방어
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
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001  # google.genai 임포트가 rust 패닉을 낼 수 있음 → 방어
        log.info("Gemini 호출 실패: %s", e)
        return None


# ─────────────────────── 비전(멀티모달): 프레임에 주제 피사체가 보이는가 ───────────────────────
def score_frames_subject(image_paths: list[str], subject: str, max_tokens: int = 300) -> list[float] | None:
    """각 프레임에 `subject`가 보이는지 0~1 점수 리스트. 비전 LLM(Claude→Gemini). 키 없으면 None.
    ★주제 피사체 의미검증(Step2): '잠수사 vs 배', '오종', '빈 물'을 정확히 구분한다.
    반환 None = 검증 불가(키 없음/실패) → 상위는 게이트를 건너뛴다(발행 불정지)."""
    imgs = [p for p in (image_paths or []) if p]
    if not imgs:
        return None
    prompt = (
        f"あなたは映像内容の確認アシスタントです。これから{len(imgs)}枚の画像を渡します。"
        f"各画像に「{subject}」がはっきり写っていれば1.0、部分的/遠い/不明瞭なら0.5、"
        f"写っていない(空の水中だけ・ダイバーや準備の様子だけ・別の被写体)なら0.0で評価してください。"
        f"出力はJSONの数値配列だけ(説明禁止)。例: [0.0, 1.0, 0.5]。要素数は必ず{len(imgs)}個。")
    out = _vision_claude(imgs, prompt, max_tokens) or _vision_gemini(imgs, prompt)
    if not out:
        return None
    import json
    import re
    m = re.search(r"\[[^\]]*\]", out)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        vals = [max(0.0, min(1.0, float(x))) for x in arr]
        return vals[:len(imgs)] if vals else None
    except Exception:  # noqa: BLE001
        return None


def describe_frames(image_paths: list[str], prompt: str, max_tokens: int = 400) -> str | None:
    """프레임 여러 장 + 프롬프트 → 자유형 텍스트(비전 LLM: Claude→Gemini). 키 없으면 None.
    첨부 영상 나레이션에서 '영상 내용을 눈으로 보고' 사실 설명을 뽑는 데 쓴다(대본 근거)."""
    imgs = [p for p in (image_paths or []) if p]
    if not imgs:
        return None
    return _vision_claude(imgs, prompt, max_tokens) or _vision_gemini(imgs, prompt)


def _vision_claude(image_paths: list[str], prompt: str, max_tokens: int) -> str | None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import base64

        import anthropic
        client = anthropic.Anthropic()
        content: list = []
        for p in image_paths:
            b = base64.b64encode(open(p, "rb").read()).decode()
            content.append({"type": "image", "source": {"type": "base64",
                            "media_type": "image/jpeg", "data": b}})
        content.append({"type": "text", "text": prompt})
        msg = client.messages.create(model=CLAUDE_MODEL, max_tokens=max_tokens,
                                     messages=[{"role": "user", "content": content}])
        parts = [getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text"]
        return "\n".join(p for p in parts if p).strip() or None
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        log.info("Claude vision 실패 → Gemini 폴백: %s", e)
        return None


def _vision_gemini(image_paths: list[str], prompt: str) -> str | None:
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    try:
        from google import genai
        from google.genai import types
        client = genai.Client()
        parts = [types.Part.from_bytes(data=open(p, "rb").read(), mime_type="image/jpeg")
                 for p in image_paths]
        resp = client.models.generate_content(model=GEMINI_MODEL, contents=parts + [prompt])
        return (resp.text or "").strip() or None
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        log.info("Gemini vision 실패: %s", e)
        return None
