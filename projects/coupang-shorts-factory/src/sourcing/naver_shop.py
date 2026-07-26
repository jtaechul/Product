"""네이버 쇼핑 검색 — 소싱 상품의 '진짜 상품명' 확인 + 쿠팡 판매 여부 자동 판정 (§2 개선).

book-carousel가 쓰는 것과 동일한 네이버 OpenAPI 키(NAVER_CLIENT_ID/SECRET)로
쇼핑 검색(/v1/search/shop.json)을 호출한다. 쿠팡 직접 크롤링(봇차단·ToS 위반)과 달리
정식 API라 GitHub Actions에서도 동작한다. 키가 없거나 실패하면 폴백(빈 dict) — 발굴은 계속.

운영자 불편("쿠팡에서 찾기 힘들다") 해소가 목적:
  - real_title    : 한국에서 실제 팔리는 상품명 → 운영자가 쿠팡 검색창에 그대로 넣으면 잘 찾아짐.
  - coupang       : 판매처(mallName)에 '쿠팡'이 있으면 True (쿠팡 판매 확인 배지).
  - coupang_title : 쿠팡몰 항목의 제목(= 쿠팡에 등록된 상품명). 없으면 real_title 폴백.
어필리에이트 링크 자체는 네이버로 못 만든다(쿠팡 파트너스 몫) — 이 모듈은 '찾기'만 쉽게 한다.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

NAVER_SHOP = "https://openapi.naver.com/v1/search/shop.json"
_TAG = re.compile(r"<[^>]+>")


def naver_keys() -> tuple:
    """(client_id, client_secret) 또는 (None, None). SHORTS_NAVER_* 도 허용."""
    cid = (os.environ.get("NAVER_CLIENT_ID") or os.environ.get("SHORTS_NAVER_CLIENT_ID") or "").strip()
    sec = (os.environ.get("NAVER_CLIENT_SECRET") or os.environ.get("SHORTS_NAVER_CLIENT_SECRET") or "").strip()
    return (cid, sec) if (cid and sec) else (None, None)


def _clean(t: str) -> str:
    return _TAG.sub("", t or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def search_shop(query: str, display: int = 10, http=None) -> list:
    """네이버 쇼핑 검색 → 아이템 리스트. http 주입 가능(테스트). 키 없으면 []."""
    q = (query or "").strip()
    if not q:
        return []
    cid, sec = naver_keys()
    if http is None and not (cid and sec):
        return []
    url = f"{NAVER_SHOP}?query={urllib.parse.quote(q)}&display={max(1, min(display, 20))}&sort=sim"
    if http is not None:
        data = http(url)
    else:
        req = urllib.request.Request(
            url, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
    out = []
    for it in (data.get("items") or []):
        out.append({
            "title": _clean(it.get("title")), "link": it.get("link"),
            "image": it.get("image"), "lprice": it.get("lprice"),
            "mall": it.get("mallName"), "productId": it.get("productId"),
        })
    return out


def find_coupang(query: str, http=None) -> dict:
    """상품 키워드 → {real_title, lprice, coupang(bool), coupang_title, ...}. 실패/키없음 → {}."""
    try:
        items = search_shop(query, display=10, http=http)
    except Exception as e:
        print(f"[naver] 쇼핑 검색 실패({query!r}): {type(e).__name__}: {str(e)[:120]}")
        return {}
    if not items:
        return {}
    top = items[0]
    coup = next((it for it in items if "쿠팡" in (it.get("mall") or "")), None)
    # 상위 후보(이미지 포함)를 함께 반환 → 운영자가 틱톡 썸네일과 '나란히' 대조해 같은 상품을 고른다
    # ('맨 위 결과 맹신'으로 다른 상품이 잡히던 문제 완화). 쿠팡 판매 항목을 앞으로 정렬.
    cand = [{"title": it.get("title") or "", "image": it.get("image"), "mall": it.get("mall"),
             "lprice": it.get("lprice"), "link": it.get("link"),
             "coupang": "쿠팡" in (it.get("mall") or "")} for it in items[:6]]
    cand.sort(key=lambda c: 0 if c["coupang"] else 1)
    return {
        "query": query,
        "real_title": top.get("title") or "",
        "lprice": top.get("lprice"),
        "coupang": bool(coup),
        "coupang_title": (coup.get("title") if coup else top.get("title")) or "",
        "coupang_lprice": (coup.get("lprice") if coup else None),
        "mall": (coup.get("mall") if coup else top.get("mall")),
        "image": (coup.get("image") if coup else top.get("image")),
        "candidates": cand,
    }
