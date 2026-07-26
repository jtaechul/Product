"""product_info(3b) 단위 테스트 — 소싱 저장물 → 대본/방향용 product dict 조립(LLM 없음).

관리자가 실제로 저장하는 구조를 그대로 흉내낸다:
  product/{hash}.json = {keyword, hash, product:<후보>, coupang:{affiliate_url}}
  promo/{hash}.json   = {product_hash, keyword, count, videos:[<후보>...]}
python tests/test_product_info.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.product_info import build_product_info   # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


def _write(base, hsh, prod, promo):
    (base / "product").mkdir(parents=True, exist_ok=True)
    (base / "promo").mkdir(parents=True, exist_ok=True)
    if prod is not None:
        (base / "product" / f"{hsh}.json").write_text(json.dumps(prod), encoding="utf-8")
    if promo is not None:
        (base / "promo" / f"{hsh}.json").write_text(json.dumps(promo), encoding="utf-8")


def test_full():
    print("[T1] 풀 데이터 — 쿠팡 등록명·재료·링크 조립")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cand = {"title": "amazing gadget", "title_ko": "손목 선풍기",
                "coupang_keywords": ["넥밴드 선풍기", "휴대용 선풍기"],
                "naver": {"coupang_title": "미니 넥밴드 선풍기 3단", "real_title": "넥밴드 선풍기"}}
        prod = {"keyword": "선풍기", "hash": "h1", "product": cand,
                "coupang": {"affiliate_url": "https://link.coupang.com/a/XYZ"}}
        promo = {"product_hash": "h1", "keyword": "미니 넥밴드 선풍기 3단", "count": 2,
                 "videos": [{"title_ko": "이거 목에 걸면 시원함", "title": "neck fan"},
                            {"title": "hands-free cooling demo"}]}
        _write(base, "h1", prod, promo)
        info = build_product_info("h1", base_dir=base)
        check(info["name"] == "미니 넥밴드 선풍기 3단", f"name=쿠팡등록명 ({info['name']})")
        check(info["affiliate_url"] == "https://link.coupang.com/a/XYZ", "affiliate_url 전달")
        check(info["promo_count"] == 2, f"promo_count=2 ({info['promo_count']})")
        check("손목 선풍기" in info["notes"], "notes에 상품 한줄설명 포함")
        check("넥밴드 선풍기" in info["notes"], "notes에 키워드 포함")
        check("이거 목에 걸면 시원함" in info["notes"], "notes에 홍보영상 설명 포함")
        check("hands-free cooling demo" in info["notes"], "notes에 영어 제목 폴백 포함")
        check(info["source"] == "tiktok_sourcing", "source 태그")
        check(info["keyword"] == "선풍기", "keyword 전달")


def test_name_fallback():
    print("[T2] 이름 폴백 — 네이버 없음 → 검색어")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cand = {"title": "cool thing", "coupang_keywords": ["각도 조절 독서대"], "naver": {}}
        prod = {"keyword": "독서대", "hash": "h2", "product": cand, "coupang": {}}
        _write(base, "h2", prod, {"product_hash": "h2", "videos": []})
        info = build_product_info("h2", base_dir=base)
        check(info["name"] == "각도 조절 독서대", f"name=검색어 폴백 ({info['name']})")
        check(info["affiliate_url"] == "", "링크 없으면 빈 문자열")
        check(info["promo_count"] == 0, "영상 0개")


def test_missing():
    print("[T3] 파일 없음 — 크래시 없이 최소 dict")
    with tempfile.TemporaryDirectory() as td:
        info = build_product_info("nope", base_dir=Path(td))
        check(info["name"] == "", "name 빈 문자열")
        check(info["promo_count"] == 0, "promo_count 0")
        check(info["notes"] == "", "notes 빈 문자열")
        check(info["source"] == "tiktok_sourcing", "source 태그 유지")


if __name__ == "__main__":
    for fn in [test_full, test_name_fallback, test_missing]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: product_info 조립 정상 (name·notes·링크·폴백).")
