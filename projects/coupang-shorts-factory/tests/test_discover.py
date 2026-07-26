"""발굴 파이프라인(discover) + 번역/중국어확장 단위 테스트 — 네트워크 없이 주입.

python tests/test_discover.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.discover import build_manifest, discover, enrich_naver, write_manifest  # noqa: E402
from src.sourcing.naver_shop import find_coupang, search_shop                   # noqa: E402
from src.sourcing.tiktok_tikwm import TikwmAdapter, TikwmClient                 # noqa: E402
from src.sourcing.translate import (                                            # noqa: E402
    describe_and_keywords_ko, expand_zh_terms, translate_titles_ko)

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


FAKE = {"code": 0, "data": {"videos": [
    {"video_id": "1", "title": "适量 적게 본 꿀템", "play_count": 500, "cover": "/c/1.jpg",
     "play": "https://cdn/1.mp4", "author": {"unique_id": "a", "nickname": "A"}},
    {"video_id": "2", "title": "많이 본 꿀템", "play_count": 88000, "origin_cover": "https://cdn/2.jpg",
     "hdplay": "/hd/2.mp4", "author": {"unique_id": "b", "nickname": "B"}},
]}}


def fake_http(url, data=None, timeout=60):
    return json.dumps(FAKE).encode()


def _adapter():
    return TikwmAdapter(client=TikwmClient(http=fake_http))


def test_discover_terms_and_ko():
    print("[T1] 발굴(주입 검색어) → 조회수상위 + title_ko(키없음=원문 폴백)")
    # terms 주입으로 Gemini 확장 우회, 번역은 키 없으면 원문 폴백
    svs = discover("꿀템", limit=10, adapter=_adapter(), terms=["厨房好物"])
    check(len(svs) == 2, f"후보 2개 ({len(svs)})")
    check(svs[0].view_count == 88000, "조회수 상위 먼저")
    check(all(s.title_ko for s in svs), "title_ko 채워짐(폴백이라도)")
    check(all(isinstance(s.coupang_keywords, list) for s in svs), "coupang_keywords 리스트(폴백 빈배열)")
    m = build_manifest("꿀템", "h", svs, terms=["厨房好物"])
    c0 = m["candidates"][0]
    check("title_ko" in c0 and "coupang_keywords" in c0 and m["search_terms"] == ["厨房好物"],
          "매니페스트에 title_ko·coupang_keywords·search_terms")


def test_write_manifest():
    print("[T2] 매니페스트 저장/재로드(검색어 포함)")
    with tempfile.TemporaryDirectory() as td:
        svs = discover("꿀템", adapter=_adapter(), terms=["x"])
        m = build_manifest("꿀템", "h1", svs, terms=["x", "y"])
        p = write_manifest("h1", m, base_dir=Path(td))
        got = json.loads(p.read_text(encoding="utf-8"))
        check(got["count"] == 2 and got["search_terms"] == ["x", "y"], "내용 왕복(검색어 포함)")


def test_empty():
    print("[T3] 검색 실패 → 후보 0개(크래시 없음)")
    def boom(url, data=None, timeout=60):
        raise RuntimeError("blocked")
    ad = TikwmAdapter(client=TikwmClient(http=boom))
    svs = discover("x", adapter=ad, terms=["x"])
    check(svs == [] and build_manifest("x", "h", svs)["count"] == 0, "빈 후보 안전")


def test_translate_injected():
    print("[T4] 번역/확장 성공 경로(Gemini 주입)")
    def call_terms(body):
        return {"candidates": [{"content": {"parts": [{"text": '{"terms":["厨房好物","家居神器"]}'}]}}]}
    check(expand_zh_terms("주방 꿀템", call=call_terms) == ["厨房好物", "家居神器"], "한국어→중국어 확장")

    def call_ko(body):
        return {"candidates": [{"content": {"parts": [{"text": '{"ko":["주방 정리 신박템","다용도 걸이"]}'}]}}]}
    check(translate_titles_ko(["厨房神器", "挂钩"], call=call_ko) == ["주방 정리 신박템", "다용도 걸이"],
          "중국어→한국어 번역")

    # 실패/개수불일치 → 원문 폴백
    def call_bad(body):
        return {"candidates": [{"content": {"parts": [{"text": '{"ko":["하나만"]}'}]}}]}
    out = translate_titles_ko(["A", "B"], call=call_bad)
    check(out == ["하나만", "B"], "개수 불일치 → 부족분 원문 폴백")


def test_describe_and_keywords():
    print("[T5] 설명+쿠팡검색어 동시 추출(Gemini 주입)")
    def call_items(body):
        payload = ('{"items":[{"ko":"휴대용 미니 다지기","keywords":["미니 다지기","휴대용 채칼"]},'
                   '{"ko":"회전 고기 슬라이서","keywords":["고기 슬라이서"]}]}')
        return {"candidates": [{"content": {"parts": [{"text": payload}]}}]}
    out = describe_and_keywords_ko(["便携绞菜器", "旋转切肉机"], call=call_items)
    check(out[0]["ko"] == "휴대용 미니 다지기" and out[0]["keywords"] == ["미니 다지기", "휴대용 채칼"],
          "0번 설명·검색어")
    check(out[1]["keywords"] == ["고기 슬라이서"], "1번 검색어")

    # 키 없음/개수불일치 → 폴백(ko=원문, keywords=[])
    def call_short(body):
        return {"candidates": [{"content": {"parts": [{"text": '{"items":[{"ko":"하나"}]}'}]}}]}
    out2 = describe_and_keywords_ko(["A", "B"], call=call_short)
    check(out2[0] == {"ko": "하나", "keywords": []} and out2[1] == {"ko": "B", "keywords": []},
          "개수 부족 → 뒤 항목 원문 폴백")


def test_naver_find_coupang():
    print("[T6] 네이버 쇼핑 → 진짜 상품명 + 쿠팡 판매여부(주입)")
    def http_ok(url):
        return {"items": [
            {"title": "다용도 <b>미니</b> 채칼 세트", "mallName": "스마트스토어",
             "lprice": "9900", "link": "http://a", "image": "http://i", "productId": "1"},
            {"title": "휴대용 미니 채칼 쿠팡배송", "mallName": "쿠팡", "lprice": "8500",
             "link": "http://c", "image": "http://ic", "productId": "2"},
        ]}
    info = find_coupang("미니 채칼", http=http_ok)
    check(info.get("real_title") == "다용도 미니 채칼 세트", "top 제목 태그 제거")
    check(info.get("coupang") is True, "쿠팡몰 항목 감지")
    check(info.get("coupang_title") == "휴대용 미니 채칼 쿠팡배송", "쿠팡 등록 상품명 추출")

    # 쿠팡 항목 없음 → coupang False, coupang_title=top 폴백
    def http_nocoup(url):
        return {"items": [{"title": "일반 채칼", "mallName": "옥션", "lprice": "5000"}]}
    info2 = find_coupang("채칼", http=http_nocoup)
    check(info2.get("coupang") is False and info2.get("coupang_title") == "일반 채칼",
          "쿠팡 없으면 top 폴백")

    # 검색 실패/빈결과 → {}
    def http_boom(url):
        raise RuntimeError("네이버 차단")
    check(find_coupang("x", http=http_boom) == {}, "실패 → 빈 dict")
    check(search_shop("", http=http_ok) == [], "빈 쿼리 → []")


def test_enrich_naver():
    print("[T7] enrich_naver — 후보에 네이버 정보 부착(finder 주입)")
    svs = discover("꿀템", adapter=_adapter(), terms=["x"])
    def fake_finder(q):
        return {"real_title": f"진짜 {q}", "coupang": True, "coupang_title": f"쿠팡 {q}"}
    enrich_naver(svs, finder=fake_finder)
    check(all(s.naver.get("coupang") for s in svs), "모든 후보에 쿠팡 판매여부")
    c0 = build_manifest("꿀템", "h", svs)["candidates"][0]
    check("naver" in c0 and c0["naver"].get("coupang_title", "").startswith("쿠팡 "),
          "매니페스트 후보에 naver.coupang_title")


if __name__ == "__main__":
    for fn in [test_discover_terms_and_ko, test_write_manifest, test_empty,
               test_translate_injected, test_describe_and_keywords,
               test_naver_find_coupang, test_enrich_naver]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 전체 통과 — 발굴(중국어확장·병합·번역) 정상.")
