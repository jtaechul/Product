"""틱톡 tikwm 어댑터 단위 테스트 — 네트워크 없이 http 주입.

python tests/test_tiktok_tikwm.py
"""
import json
import sys
import tempfile
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.base import Seed, available, get_adapter          # noqa: E402
from src.sourcing.tiktok_tikwm import TikwmAdapter, TikwmClient      # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


# 가짜 tikwm: 검색은 videos 2건, 미디어 URL은 mp4 바이트 반환.
FAKE_VIDEOS = [
    {"video_id": "111", "title": "덜 본 영상", "play_count": 1000, "duration": 20,
     "hdplay": "/media/hd/111.mp4", "author": {"unique_id": "seller_a", "nickname": "판매자A"}},
    {"video_id": "222", "title": "많이 본 영상", "play_count": 99000, "duration": 25,
     "play": "https://cdn.tikwm.com/222.mp4", "author": {"unique_id": "seller_b", "nickname": "판매자B"}},
]


def fake_http(url, data=None, timeout=60):
    if "/api/feed/search" in url:
        return json.dumps({"code": 0, "data": {"videos": FAKE_VIDEOS}}).encode()
    if "/api/user/posts" in url:
        return json.dumps({"code": 0, "data": {"videos": FAKE_VIDEOS[:1]}}).encode()
    if "/api/" in url and "url=" in url:
        return json.dumps({"code": 0, "data": FAKE_VIDEOS[1]}).encode()
    if url.endswith(".mp4") or "/media/" in url or "cdn.tikwm" in url:
        return b"\x00\x00\x00\x18ftypisom" + b"\x00" * 200_000   # 200KB 가짜 mp4
    raise RuntimeError(f"unexpected url: {url}")


def adapter():
    return TikwmAdapter(client=TikwmClient(http=fake_http))


def test_search_sort_and_map():
    print("[T1] 검색 → 조회수 정렬·매핑")
    res = adapter().search(Seed(kind="keyword", value="꿀템"), limit=10)
    check(len(res) == 2, f"2건 반환 ({len(res)})")
    check(res[0].view_count == 99000, "조회수 내림차순(많이 본 게 먼저)")
    sv = res[0]
    check(sv.platform == "tiktok" and sv.source_mode == "auto" and sv.status == "discovered",
          "플랫폼/모드/상태")
    check(sv.source_url == "https://www.tiktok.com/@seller_b/video/222", "source_url 구성")
    check(sv.download_url == "https://cdn.tikwm.com/222.mp4", "download_url(절대 URL 그대로)")
    # 상대경로 hdplay는 base가 붙어야 한다
    rel = [s for s in res if s.source_url.endswith("/111")][0]
    check(rel.download_url == "https://www.tikwm.com/media/hd/111.mp4", "상대 hdplay → 절대화")


def test_seed_kinds():
    print("[T2] 시드 종류")
    ad = adapter()
    check(len(ad.search(Seed(kind="creator", value="@seller_a"))) == 1, "creator 시드")
    check(len(ad.search(Seed(kind="url", value="https://www.tiktok.com/@x/video/222"))) == 1, "url 시드")


def test_search_failure():
    print("[T3] 검색 실패 → [](크래시 없음)")
    def boom(url, data=None, timeout=60):
        raise RuntimeError("rate limited")
    ad = TikwmAdapter(client=TikwmClient(http=boom))
    check(ad.search(Seed(kind="keyword", value="x")) == [], "예외 → []")

    def code_err(url, data=None, timeout=60):
        return json.dumps({"code": -1, "msg": "blocked"}).encode()
    ad2 = TikwmAdapter(client=TikwmClient(http=code_err))
    check(ad2.search(Seed(kind="keyword", value="x")) == [], "code!=0 → []")


def test_download():
    print("[T4] 다운로드 → mp4 저장·상태 갱신")
    with tempfile.TemporaryDirectory() as td:
        res = adapter().search(Seed(kind="keyword", value="꿀템"))
        sv = res[0]
        out = adapter().download(sv, Path(td))
        check(out is not None and out.exists() and out.suffix == ".mp4", "mp4 파일 생성")
        check(sv.status == "downloaded" and sv.downloaded_path == str(out), "상태/경로 갱신")
        check(out.read_bytes()[:12].endswith(b"ftypisom"), "실제 mp4 바이트")

    print("[T5] download_url 만료 → source_url로 재해석 폴백")
    with tempfile.TemporaryDirectory() as td:
        res = adapter().search(Seed(kind="keyword", value="꿀템"))
        sv = res[0]
        sv.download_url = None   # 만료 상황 모사
        out = adapter().download(sv, Path(td))   # source_url → resolve → play → 다운로드
        check(out is not None and sv.status == "downloaded", "재해석 폴백 성공")


def test_registry():
    print("[T6] 레지스트리 등록")
    check("tiktok_tikwm" in available(), f"tiktok_tikwm 등록 (available={available()})")
    check(get_adapter("tiktok_tikwm") is not None, "get_adapter")


if __name__ == "__main__":
    for fn in [test_search_sort_and_map, test_seed_kinds, test_search_failure,
               test_download, test_registry]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 전체 통과 — tikwm 틱톡 어댑터(검색·정렬·다운로드·폴백) 정상.")
