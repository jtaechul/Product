"""M2 1안 — 쿠팡 파트너스 Open API (HMAC 서명, 스펙 §M2).

⚠️ 미검증: API 키 발급에 파트너스 실적 요건이 있어(정확 기준 확실하지 않음) 아직 실키로
테스트하지 못했다. 서명 방식(CEA HMAC-SHA256)과 엔드포인트는 공개 문서 기준 구현이며,
키 발급 후 첫 호출에서 검증할 것. 그 전까지 파이프라인 기본 경로는 manual_queue(2안)다.

시크릿: SHORTS_COUPANG_ACCESS_KEY / SHORTS_COUPANG_SECRET_KEY
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
import urllib.parse

DOMAIN = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
DEEPLINK_PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"


def is_configured() -> bool:
    return bool(os.environ.get("SHORTS_COUPANG_ACCESS_KEY", "").strip()
                and os.environ.get("SHORTS_COUPANG_SECRET_KEY", "").strip())


def _auth_header(method: str, path: str, query: str) -> str:
    """CEA HMAC-SHA256 서명 (쿠팡 파트너스 공개 문서의 서명 규격)."""
    access = os.environ["SHORTS_COUPANG_ACCESS_KEY"].strip()
    secret = os.environ["SHORTS_COUPANG_SECRET_KEY"].strip()
    signed_date = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    message = signed_date + method + path + query
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    return (f"CEA algorithm=HmacSHA256, access-key={access}, "
            f"signed-date={signed_date}, signature={signature}")


def search_products(keyword: str, limit: int = 5) -> list:
    """상품 검색 → product dict 리스트 (스펙 §M2 산출 스키마)."""
    import requests
    query = urllib.parse.urlencode({"keyword": keyword, "limit": limit})
    url = f"{DOMAIN}{SEARCH_PATH}?{query}"
    r = requests.get(url, headers={"Authorization": _auth_header("GET", SEARCH_PATH, query)}, timeout=30)
    r.raise_for_status()
    items = (r.json().get("data") or {}).get("productData") or []
    return [{
        "name": it.get("productName", ""),
        "price": it.get("productPrice", 0),
        "image_urls": [it["productImage"]] if it.get("productImage") else [],
        "affiliate_url": it.get("productUrl", ""),
        "category": keyword,
        "specs": [],
    } for it in items]


def create_deeplink(urls: list) -> list:
    """일반 상품 URL → 제휴 추적 딥링크."""
    import requests
    r = requests.post(
        f"{DOMAIN}{DEEPLINK_PATH}",
        headers={"Authorization": _auth_header("POST", DEEPLINK_PATH, ""),
                 "Content-Type": "application/json"},
        json={"coupangUrls": urls}, timeout=30)
    r.raise_for_status()
    return [d.get("shortenUrl") for d in r.json().get("data", [])]
