"""M2.5 — 상품 정보 보강 (쿠팡 API 승인 전 운영 플로우).

관리자 페이지에서 사용자는 제휴 링크(+상품 상세·리뷰 붙여넣기)만 등록한다.
상품명·가격·특징이 비어 있으면 붙여넣은 텍스트(data/notes/{row_hash}.md)에서
Claude가 핵심 정보를 추출해 채우고, 원문은 notes로 M3 대본 생성에 전달된다.

쿠팡 페이지 자동 수집(크롤링)은 봇 차단(403) + 스펙 §2(스크래핑 금지)·
§3.2(에셋 화이트리스트) 위반이라 구현하지 않는다 — 붙여넣기가 공식 대체 경로.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_EXTRACT_PROMPT = """아래는 사용자가 쿠팡 상품 페이지에서 복사해 붙여넣은 원문(설명·리뷰 혼합)이다.
쇼츠 제작에 필요한 핵심 정보만 JSON으로 추출하라. 다른 텍스트, 마크다운 백틱 금지.
스키마: {"name": "상품명(30자 내)", "price": 현재판매가_정수, "specs": ["숫자 위주 핵심 특징 2~4개"], "category": "카테고리 한 단어"}
가격이 여러 개 보이면 할인 적용된 현재 판매가를 고른다."""


def enrich_product(product: dict, settings: dict) -> dict:
    """이름·가격·특징이 비면 notes에서 추출해 채운다. notes는 항상 product에 첨부."""
    notes_path = PROJECT_ROOT / "data" / "notes" / f"{product['_row_hash']}.md"
    notes = notes_path.read_text(encoding="utf-8").strip() if notes_path.exists() else ""
    if notes:
        product["notes"] = notes[:4000]  # M3 대본 생성 컨텍스트로도 사용 (후기 통증포인트)

    if product.get("name") and product.get("price", 0) > 0 and product.get("specs"):
        return product
    if not notes:
        raise RuntimeError(
            "상품명·가격·특징이 비어 있고 붙여넣은 상세 텍스트도 없습니다. "
            "관리자 페이지에서 '상품 상세·리뷰 붙여넣기'를 채우거나 직접 입력으로 등록해 주세요.")

    from src.script.generate import anthropic_key
    key = anthropic_key()
    if not key:
        raise RuntimeError(
            "상품 정보 자동 추출에 Anthropic 키가 필요합니다 "
            "(SHORTS_ANTHROPIC_API_KEY 또는 ANTHROPIC_API_KEY 시크릿).")

    import anthropic
    client = anthropic.Anthropic(api_key=key)
    resp = client.messages.create(
        model=settings.get("script", {}).get("model", "claude-sonnet-4-6"),
        max_tokens=800,
        system=_EXTRACT_PROMPT,
        messages=[{"role": "user", "content": notes[:6000]}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("상세 텍스트에서 상품 정보를 추출하지 못했습니다(JSON 없음).")
    data = json.loads(text[start:end + 1])

    if not product.get("name"):
        product["name"] = str(data.get("name", "")).strip()[:60]
    if product.get("price", 0) <= 0:
        product["price"] = int(re.sub(r"[^\d]", "", str(data.get("price", 0))) or 0)
    if not product.get("specs"):
        product["specs"] = [str(s).strip() for s in (data.get("specs") or []) if str(s).strip()][:4]
    if not product.get("category"):
        product["category"] = str(data.get("category", "")).strip()[:20]

    if not product["name"] or product["price"] <= 0:
        raise RuntimeError(
            "붙여넣은 텍스트에서 상품명 또는 가격을 찾지 못했습니다. "
            "관리자 페이지의 '직접 입력'에 상품명과 가격을 채워 다시 등록해 주세요.")
    print(f"[enrich] M2.5 상세 텍스트로 보강: {product['name']} "
          f"({product['price']:,}원, 특징 {len(product['specs'])}개)")
    return product
