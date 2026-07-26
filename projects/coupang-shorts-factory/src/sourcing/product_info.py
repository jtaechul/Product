"""소싱 상품 → 대본/방향(3안) 생성용 product dict 조립 (3b).

② 확정 상품(data/sources/product/{hash}.json) + ③ 선택 홍보영상(data/sources/promo/{hash}.json)에서
기존 generate_script/mechanism이 받는 product dict를 만든다. 핵심:
  - name  : 네이버로 확인한 '쿠팡 등록 상품명'(없으면 한국어 설명/검색어)
  - notes : 홍보 틱톡 영상들의 한국어 설명 모음 = 차별점(3안) 추출·대본의 재료
  - affiliate_url : ② 파트너스 링크
LLM 없이 순수 조립(단위 테스트 가능). 대본/방향 생성은 기존 모듈이 이 dict를 받아 처리.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.sourcing.models import SOURCES_DIR


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build_product_info(product_hash: str, base_dir: Path | None = None) -> dict:
    """소싱 데이터 → generate_script/mechanism용 product dict. 없으면 최소 dict."""
    base = base_dir or SOURCES_DIR
    prod = _load(base / "product" / f"{product_hash}.json") or {}
    promo = _load(base / "promo" / f"{product_hash}.json") or {}

    p = prod.get("product") or {}
    nv = p.get("naver") or {}
    name = (nv.get("coupang_title") or nv.get("real_title") or p.get("title_ko")
            or (p.get("coupang_keywords") or [""])[0] or prod.get("keyword") or "")

    # 재료(notes): 홍보영상 설명 + 상품 한국어 설명 + 쿠팡 검색어 — 차별점 추출·대본의 원천.
    vids = promo.get("videos") or []
    lines = []
    if p.get("title_ko"):
        lines.append(f"상품 한줄설명: {p.get('title_ko')}")
    if nv.get("real_title") and nv.get("real_title") != name:
        lines.append(f"판매명(네이버): {nv.get('real_title')}")
    kws = p.get("coupang_keywords") or []
    if kws:
        lines.append("관련 키워드: " + ", ".join(kws[:5]))
    descs = [(v.get("title_ko") or v.get("title") or "").strip() for v in vids]
    descs = [d for d in descs if d]
    if descs:
        lines.append("이 상품을 홍보하는 틱톡 영상들의 내용:")
        lines += [f"- {d}" for d in descs[:10]]
    notes = "\n".join(lines)

    return {
        "name": name,
        "category": "",
        "notes": notes,
        "affiliate_url": (prod.get("coupang") or {}).get("affiliate_url") or "",
        "source": "tiktok_sourcing",
        "keyword": prod.get("keyword") or promo.get("keyword") or "",
        "promo_count": len(vids),
    }
