"""발굴 파이프라인(discover) + 번역/중국어확장 단위 테스트 — 네트워크 없이 주입.

python tests/test_discover.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 단위 테스트 결정성: 키가 있으면 실네트워크를 타므로 제거(주입 call로만 성공 경로 검증)
for _k in ("GEMINI_API_KEY", "SHORTS_GEMINI_API_KEY"):
    os.environ.pop(_k, None)

from src.sourcing.discover import build_manifest, discover, enrich_naver, write_manifest  # noqa: E402
from src.sourcing.naver_shop import find_coupang, search_shop                   # noqa: E402
from src.sourcing.tiktok_tikwm import TikwmAdapter, TikwmClient                 # noqa: E402
from src.sourcing.translate import (                                            # noqa: E402
    describe_and_keywords_ko, expand_zh_terms, identify_by_image, match_naver_by_image,
    translate_titles_ko)

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


def test_identify_by_image():
    print("[T9] 비전 상품 식별(썸네일 이미지+제목 주입) → ko·keywords·zh")
    seen = {}

    def fake_fetch(url):
        return ("QUJD", "image/jpeg") if url else None   # 가짜 base64 이미지

    def call_vision(body):
        parts = body["contents"][0]["parts"]
        seen["has_img"] = any("inline_data" in p for p in parts)   # 이미지 파트 포함 확인
        payload = ('{"ko":"무선 고압 세척기","keywords":["무선 세척기","고압 물총"],'
                   '"zh":["无线洗车机","便携高压水枪"]}')
        return {"candidates": [{"content": {"parts": [{"text": payload}]}}]}

    out = identify_by_image([{"title": "神器洗车", "cover": "http://x/1.jpg"}],
                            call=call_vision, fetch=fake_fetch)
    check(seen.get("has_img") is True, "비전 요청에 이미지 파트 포함")
    check(out[0]["ko"] == "무선 고압 세척기", "비전 한국어 설명")
    check(out[0]["keywords"] == ["무선 세척기", "고압 물총"], "비전 쿠팡 검색어(이미지 기반)")
    check(out[0]["zh"] == ["无线洗车机", "便携高压水枪"], "비전 중국어어(③ 같은상품 검색용)")

    # 썸네일 없으면 제목 기반 폴백(zh 빈) — 크래시 없음
    out2 = identify_by_image([{"title": "挂钩", "cover": ""}], call=call_vision, fetch=lambda u: None)
    check(out2[0]["zh"] == [] and out2[0]["ko"] == "挂钩", "이미지 없음 → 제목 폴백(zh 빈)")


def test_match_by_image():
    print("[T10] 비전 이미지 대조 — 틱톡 썸네일 vs 네이버 후보 이미지 → 같은 상품 자동 선택")

    def fake_fetch(url):
        return ("IMG", "image/jpeg") if url else None

    def call_match(body):
        imgs = sum(1 for p in body["contents"][0]["parts"] if "inline_data" in p)
        assert imgs == 3, f"썸네일1+후보2=3 이미지 기대, 실제 {imgs}"   # 다중 이미지 전송 확인
        return {"candidates": [{"content": {"parts": [{"text": '{"best":1,"confidence":"high","reason":"같은 만두기"}'}]}}]}

    cands = [{"title": "A", "image": "http://a.jpg"}, {"title": "B", "image": "http://b.jpg"}]
    out = match_naver_by_image("http://cover.jpg", cands, call=call_match, fetch=fake_fetch)
    check(out["best"] == 1 and out["confidence"] == "high", "같은 상품 후보 인덱스+확신도(high)")

    out2 = match_naver_by_image("", cands, call=call_match, fetch=lambda u: None)
    check(out2 == {"best": 0, "confidence": "unknown"}, "썸네일 없음 → best0·unknown(최상위 유지)")

    def call_none(body):
        return {"candidates": [{"content": {"parts": [{"text": '{"best":-1,"confidence":"low"}'}]}}]}
    out3 = match_naver_by_image("http://c.jpg", cands, call=call_none, fetch=fake_fetch)
    check(out3["best"] == -1, "같은 상품 없음 → best -1")


def test_page_slicing():
    print("[T8] page 슬라이스 — 새로고침이 다른(다음) 영상 + 매니페스트 page/nonce")
    ad = _adapter()
    p0 = discover("꿀템", limit=1, adapter=ad, terms=["x"])            # 상위 1개
    p1 = discover("꿀템", limit=1, adapter=ad, terms=["x"], page=1)    # 다음 1개
    p2 = discover("꿀템", limit=1, adapter=ad, terms=["x"], page=2)    # 풀 소진
    check(len(p0) == 1 and p0[0].view_count == 88000, "page0 = 최고 조회수")
    check(len(p1) == 1 and p1[0].view_count == 500, "page1 = 다음 영상")
    check(p0[0].id != p1[0].id, "page0·page1 서로 다른 영상")
    check(p2 == [], "풀 소진 → 빈 배치")
    m = build_manifest("꿀템", "h", p1, terms=["x"], page=1, nonce="nX")
    check(m.get("page") == 1 and m.get("nonce") == "nX", "매니페스트 page·nonce 기록")


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
    # 나란히 확인용 후보(이미지 포함) — 쿠팡 항목이 앞으로 정렬
    cand = info.get("candidates") or []
    check(len(cand) == 2 and cand[0].get("coupang") is True, "candidates 반환 + 쿠팡 항목 우선정렬")
    check(cand[0].get("image") == "http://ic" and info.get("image") == "http://ic", "쿠팡 항목 이미지 노출")

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

    # 후보 이미지가 있으면 비전 대조로 best_match·confidence 부착(matcher 주입)
    svs2 = discover("꿀템", adapter=_adapter(), terms=["x"])
    def finder_cand(q):
        return {"coupang": True, "coupang_title": f"쿠팡 {q}",
                "candidates": [{"title": "c1", "image": "http://i1"}, {"title": "c2", "image": "http://i2"}]}
    def fake_matcher(cover, cands):
        return {"best": 1, "confidence": "high", "reason": "같음"}
    enrich_naver(svs2, finder=finder_cand, matcher=fake_matcher)
    check(all(s.naver.get("best_match") == 1 and s.naver.get("match_confidence") == "high" for s in svs2),
          "비전 대조 → best_match·confidence 부착")


if __name__ == "__main__":
    for fn in [test_discover_terms_and_ko, test_write_manifest, test_empty,
               test_translate_injected, test_describe_and_keywords, test_identify_by_image,
               test_match_by_image, test_page_slicing, test_naver_find_coupang, test_enrich_naver]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 전체 통과 — 발굴(중국어확장·병합·번역) 정상.")
