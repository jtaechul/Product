#!/usr/bin/env python3
"""쿠팡 파트너스 Open API 점검 (표준 라이브러리만 사용 — 설치 없음).

무엇을 확인하나
  1) 저장소 시크릿에 쿠팡 키가 어떤 이름으로 들어 있는가 (이름·형식만, 값은 절대 출력 안 함)
  2) 그 키로 상품 검색 / 카테고리 베스트(국내여행 1025·해외여행 1026) / 제휴링크 생성이 되는가
  3) 숙소(쿠팡 트래블)가 API 로 조회되고 제휴링크로 바뀌는가

안전 규칙
  - 키 값·서명·Authorization 헤더는 어디에도 쓰지 않는다 (로그·결과 파일 모두).
  - 제휴 링크의 회원 코드(lptag 등 쿼리 값)와 단축 링크 코드는 가려서 적는다 (저장소가 공개라서).
  - 받은 링크를 따라가지 않는다 (자기 링크 클릭은 부정 클릭으로 잡힐 수 있다).
  - 호출은 10회 안쪽, 호출 사이 1.5초 쉰다.

결과: data/probe/result.json (워크플로가 커밋) + Actions 요약.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULT = ROOT / "data" / "probe" / "result.json"
REQUEST = ROOT / "requests" / "probe" / "request.json"

DOMAIN = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi"

# 시크릿 이름 후보 (왼쪽이 우선). 2026-10-09 운영자 화면으로 COUPANG_* 등록을 확인했다.
PAIRS = [
    ("COUPANG_ACCESS_KEY", "COUPANG_SECRET_KEY"),
    ("SHORTS_COUPANG_ACCESS_KEY", "SHORTS_COUPANG_SECRET_KEY"),
]

SEARCH_KEYWORDS = ["여행용 캐리어", "가평 풀빌라", "제주 호텔"]
BEST_CATEGORIES = [("1025", "국내여행", 20), ("1026", "해외여행", 10)]
DEEPLINK_TESTS = [
    ("일반 상품", ["https://www.coupang.com/vp/products/184614775"]),
    ("트래블 홈", ["https://trip.coupang.com/"]),
    ("트래블 국내숙박 목록", ["https://trip.coupang.com/tp/domestic"]),
]

_SECRETS: list = []          # 결과에 섞여 들어가면 안 되는 값들
_CALLS = {"n": 0}
MAX_CALLS = 12


def _scrub(text: str) -> str:
    """혹시라도 응답에 키 값이 메아리쳐 오면 지운다."""
    for s in _SECRETS:
        if s and s in text:
            text = text.replace(s, "***")
    return text


def _mask_url(url: str) -> dict:
    """링크의 '모양'만 남긴다 — 호스트·경로 종류·쿼리 이름. 값은 버린다."""
    try:
        u = urllib.parse.urlsplit(url)
    except Exception:
        return {"host": "?", "path": "?", "params": []}
    path = u.path
    if u.netloc in ("link.coupang.com", "coupa.ng") and not path.startswith("/re/"):
        path = re.sub(r"[A-Za-z0-9]{4,}$", "***", path)      # 단축 코드 가림
    path = re.sub(r"\d{5,}", "{id}", path)
    return {"host": u.netloc, "path": path,
            "params": sorted(urllib.parse.parse_qs(u.query, keep_blank_values=True).keys())}


def _auth(method: str, path: str, query: str, access: str, secret: str) -> str:
    signed = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    msg = signed + method + path + query
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={signed}, signature={sig}"


def call(method: str, path: str, query: str, body, access: str, secret: str) -> dict:
    """한 번 부른다. 절대 예외를 밖으로 던지지 않는다."""
    if _CALLS["n"] >= MAX_CALLS:
        return {"http": None, "error": "호출 상한 도달 — 건너뜀"}
    _CALLS["n"] += 1
    if _CALLS["n"] > 1:
        time.sleep(1.5)
    url = DOMAIN + path + (("?" + query) if query else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": _auth(method, path, query, access, secret),
        "Content-Type": "application/json;charset=UTF-8",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:  # noqa: BLE001
        return {"http": None, "error": _scrub(f"{type(e).__name__}: {e}")[:200]}
    out = {"http": status}
    try:
        out["json"] = json.loads(raw)
    except Exception:
        out["text"] = _scrub(raw)[:300]
    return out


def _products(js) -> list:
    data = (js or {}).get("data")
    if isinstance(data, dict):
        return data.get("productData") or []
    if isinstance(data, list):
        return data
    return []


def summarize_products(resp: dict) -> dict:
    js = resp.get("json") or {}
    items = _products(js)
    out = {
        "http": resp.get("http"),
        "rCode": js.get("rCode"),
        "rMessage": _scrub(str(js.get("rMessage") or js.get("message") or ""))[:200],
        "count": len(items),
    }
    if resp.get("error"):
        out["error"] = resp["error"]
    if resp.get("text"):
        out["text"] = resp["text"]
    if items:
        fields = sorted({k for it in items if isinstance(it, dict) for k in it.keys()})
        out["fields"] = fields
        image_fields = [f for f in fields if "image" in f.lower()]
        out["image_fields"] = image_fields
        hosts, shapes, cats = {}, {}, {}
        samples = []
        out["distinct_images"] = len({str(it.get("productImage") or "") for it in items if isinstance(it, dict)})
        out["distinct_product_ids"] = len({str(it.get("productId") or "") for it in items if isinstance(it, dict)})
        for it in items:
            if not isinstance(it, dict):
                continue
            m = _mask_url(str(it.get("productUrl") or ""))
            shapes[m["host"] + m["path"]] = shapes.get(m["host"] + m["path"], 0) + 1
            ih = urllib.parse.urlsplit(str(it.get("productImage") or "")).netloc
            hosts[ih] = hosts.get(ih, 0) + 1
            c = str(it.get("categoryName") or "")
            cats[c] = cats.get(c, 0) + 1
            if len(samples) < 20:
                samples.append({
                    "name": _scrub(str(it.get("productName") or ""))[:60],
                    "price": it.get("productPrice"),
                    "category": c,
                    "isRocket": it.get("isRocket"),
                    "url_params": m["params"],
                })
        out.update({"url_shapes": shapes, "image_hosts": hosts, "categories": cats, "samples": samples})
    return out


def summarize_deeplink(resp: dict) -> dict:
    js = resp.get("json") or {}
    data = js.get("data") if isinstance(js.get("data"), list) else []
    out = {
        "http": resp.get("http"),
        "rCode": js.get("rCode"),
        "rMessage": _scrub(str(js.get("rMessage") or js.get("message") or ""))[:200],
        "converted": len(data),
    }
    if resp.get("error"):
        out["error"] = resp["error"]
    if resp.get("text"):
        out["text"] = resp["text"]
    if data:
        d0 = data[0] if isinstance(data[0], dict) else {}
        out["shorten"] = _mask_url(str(d0.get("shortenUrl") or ""))
        out["landing"] = _mask_url(str(d0.get("landingUrl") or ""))
    return out


def get_with_fallback(path_tail: str, query: str, access: str, secret: str) -> tuple:
    """v1 없는 경로 먼저, 404 면 v1 경로."""
    for variant, prefix in (("no_v1", BASE), ("v1", BASE + "/v1")):
        resp = call("GET", prefix + path_tail, query, None, access, secret)
        if resp.get("http") != 404:
            return variant, resp
    return variant, resp


def post_with_fallback(path_tail: str, body, access: str, secret: str) -> tuple:
    for variant, prefix in (("v1", BASE + "/v1"), ("no_v1", BASE)):
        resp = call("POST", prefix + path_tail, "", body, access, secret)
        if resp.get("http") != 404:
            return variant, resp
    return variant, resp


def check_secrets() -> dict:
    info = {"names": {}, "pairs": []}
    values = {}
    for a, s in PAIRS:
        for n in (a, s):
            raw = os.environ.get(n, "")
            v = raw.strip()
            values[n] = v
            info["names"][n] = {
                "registered": bool(v),
                "has_stray_whitespace": bool(raw) and raw != v,
            }
            if v:
                _SECRETS.append(v)
        if values[a] and values[s]:
            info["pairs"].append({
                "access": a, "secret": s,
                "access_looks_like_uuid": bool(re.fullmatch(r"[0-9a-fA-F-]{32,40}", values[a])),
                "secret_looks_like_hex": bool(re.fullmatch(r"[0-9a-fA-F]{32,64}", values[s])),
            })
    (a1, s1), (a2, s2) = PAIRS
    if values[a1] and values[a2]:
        info["duplicate_pair_same_value"] = (values[a1] == values[a2] and values[s1] == values[s2])
    info["_values"] = values
    return info


def main() -> int:
    req = {}
    try:
        req = json.loads(REQUEST.read_text(encoding="utf-8"))
    except Exception:
        pass
    keywords = [str(k) for k in (req.get("search_keywords") or SEARCH_KEYWORDS)][:6]
    limit = max(1, min(int(req.get("limit") or 10), 10))   # 검색 limit 는 10 이 상한 (20 → "limit is out of range" 실측)
    best = [] if req.get("skip_best") else BEST_CATEGORIES
    deeplinks = [] if req.get("skip_deeplink") else DEEPLINK_TESTS
    result = {"probe_version": 2,
              "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "nonce": None, "secrets": {}, "api": {}, "verdict": {}}
    result["nonce"] = req.get("nonce")

    sec = check_secrets()
    values = sec.pop("_values")
    result["secrets"] = sec

    if not sec["pairs"]:
        result["verdict"]["keys"] = "쿠팡 키 쌍을 찾지 못함"
        return _finish(result)

    api = result["api"]
    used = None
    # 어느 쌍이 통하는지 — 기준 검색 1회로 가린다
    for p in sec["pairs"]:
        access, secret = values[p["access"]], values[p["secret"]]
        q = urllib.parse.urlencode({"keyword": keywords[0], "limit": limit})
        variant, resp = get_with_fallback("/products/search", q, access, secret)
        s = summarize_products(resp)
        s.update({"keyword": keywords[0], "path_variant": variant, "pair": p["access"]})
        api.setdefault("search", []).append(s)
        if resp.get("http") == 200 and str(s.get("rCode")) == "0":
            used = (p, access, secret, variant)
            break

    if not used:
        result["verdict"]["keys"] = "키는 있으나 API 호출이 통과하지 못함 (search 결과 참조)"
        return _finish(result)

    p, access, secret, variant = used
    api["pair_used"] = {"access": p["access"], "secret": p["secret"]}
    prefix = BASE if variant == "no_v1" else BASE + "/v1"

    for kw in keywords[1:]:
        q = urllib.parse.urlencode({"keyword": kw, "limit": limit})
        s = summarize_products(call("GET", prefix + "/products/search", q, None, access, secret))
        s.update({"keyword": kw, "path_variant": variant})
        api["search"].append(s)

    for cid, cname, blimit in best:
        q = urllib.parse.urlencode({"limit": blimit})
        s = summarize_products(call("GET", prefix + f"/products/bestcategories/{cid}", q, None, access, secret))
        s.update({"category_id": cid, "category_name": cname})
        api.setdefault("bestcategories", []).append(s)

    dl_variant = None
    for label, urls in deeplinks:
        if dl_variant is None:
            dl_variant, resp = post_with_fallback("/deeplink", {"coupangUrls": urls}, access, secret)
        else:
            pre = BASE + "/v1" if dl_variant == "v1" else BASE
            resp = call("POST", pre + "/deeplink", "", {"coupangUrls": urls}, access, secret)
        s = summarize_deeplink(resp)
        s.update({"label": label, "input": urls[0], "path_variant": dl_variant})
        api.setdefault("deeplink", []).append(s)

    # 판정
    v = result["verdict"]
    v["keys"] = f"정상 — {p['access']} / {p['secret']} 로 호출 성공"
    best = {b["category_id"]: b for b in api.get("bestcategories", [])}
    v["domestic_travel_best_count"] = (best.get("1025") or {}).get("count")
    v["overseas_travel_best_count"] = (best.get("1026") or {}).get("count")
    dl = {d["label"]: d for d in api.get("deeplink", [])}
    v["deeplink_product_ok"] = bool((dl.get("일반 상품") or {}).get("converted"))
    v["deeplink_travel_ok"] = any((dl.get(k) or {}).get("converted") for k in ("트래블 홈", "트래블 국내숙박 목록"))
    v["calls_made"] = _CALLS["n"]
    return _finish(result)


def _finish(result: dict) -> int:
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    text = _scrub(json.dumps(result, ensure_ascii=False, indent=1))
    RESULT.write_text(text + "\n", encoding="utf-8")
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("## 쿠팡 API 점검\n\n```json\n" + _scrub(json.dumps(result.get("verdict"), ensure_ascii=False, indent=1)) + "\n```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
