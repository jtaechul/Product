"""발굴 파이프라인(discover) + 번역/중국어확장 단위 테스트 — 네트워크 없이 주입.

python tests/test_discover.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.discover import build_manifest, discover, write_manifest      # noqa: E402
from src.sourcing.tiktok_tikwm import TikwmAdapter, TikwmClient                 # noqa: E402
from src.sourcing.translate import expand_zh_terms, translate_titles_ko         # noqa: E402

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
    m = build_manifest("꿀템", "h", svs, terms=["厨房好物"])
    c0 = m["candidates"][0]
    check("title_ko" in c0 and m["search_terms"] == ["厨房好物"], "매니페스트에 title_ko·search_terms")


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


if __name__ == "__main__":
    for fn in [test_discover_terms_and_ko, test_write_manifest, test_empty, test_translate_injected]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 전체 통과 — 발굴(중국어확장·병합·번역) 정상.")
