"""발굴 파이프라인(discover) 단위 테스트 — 네트워크 없이 어댑터 주입.

python tests/test_discover.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.discover import build_manifest, discover, write_manifest   # noqa: E402
from src.sourcing.tiktok_tikwm import TikwmAdapter, TikwmClient              # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


FAKE = {"code": 0, "data": {"videos": [
    {"video_id": "1", "title": "적게 본 꿀템", "play_count": 500, "cover": "/c/1.jpg",
     "play": "https://cdn/1.mp4", "author": {"unique_id": "a", "nickname": "A"}},
    {"video_id": "2", "title": "많이 본 꿀템", "play_count": 88000, "origin_cover": "https://cdn/2.jpg",
     "hdplay": "/hd/2.mp4", "author": {"unique_id": "b", "nickname": "B"}},
]}}


def fake_http(url, data=None, timeout=60):
    return json.dumps(FAKE).encode()


def test_discover_and_manifest():
    print("[T1] 발굴 → 후보(조회수 상위) + 매니페스트")
    ad = TikwmAdapter(client=TikwmClient(http=fake_http))
    svs = discover("꿀템", limit=10, adapter=ad)
    check(len(svs) == 2, f"후보 2개 ({len(svs)})")
    check(svs[0].view_count == 88000, "조회수 상위 먼저")
    m = build_manifest("꿀템", "hash123", svs)
    check(m["keyword"] == "꿀템" and m["count"] == 2 and m["source"] == "tiktok_tikwm",
          "매니페스트 헤더")
    c0 = m["candidates"][0]
    check(set(["id", "title", "view_count", "uploader", "source_url", "download_url", "cover"])
          <= set(c0), "후보 표시 필드 존재")
    check(c0["cover"] == "https://cdn/2.jpg" and c0["download_url"] == "https://www.tikwm.com/hd/2.mp4",
          "커버·다운로드 URL 절대화")


def test_write_manifest():
    print("[T2] 매니페스트 파일 저장/재로드")
    with tempfile.TemporaryDirectory() as td:
        ad = TikwmAdapter(client=TikwmClient(http=fake_http))
        svs = discover("꿀템", adapter=ad)
        m = build_manifest("꿀템", "h1", svs)
        p = write_manifest("h1", m, base_dir=Path(td))
        check(p.exists() and p.name == "h1.json", "파일 생성")
        got = json.loads(p.read_text(encoding="utf-8"))
        check(got["count"] == 2 and len(got["candidates"]) == 2, "내용 왕복")


def test_empty():
    print("[T3] 검색 실패/빈 결과 → 후보 0개(크래시 없음)")
    def boom(url, data=None, timeout=60):
        raise RuntimeError("blocked")
    ad = TikwmAdapter(client=TikwmClient(http=boom))
    svs = discover("x", adapter=ad)
    m = build_manifest("x", "h", svs)
    check(svs == [] and m["count"] == 0, "빈 후보 안전 처리")


if __name__ == "__main__":
    for fn in [test_discover_and_manifest, test_write_manifest, test_empty]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 전체 통과 — 발굴 파이프라인(discover) 정상.")
