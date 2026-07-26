"""compose(⑤) 다운로드·선택로드 단위 테스트 — moviepy 없이(어댑터 주입).

합성(stitch_vertical)은 moviepy가 필요해 GitHub Actions에서 프레임으로 검증한다.
python tests/test_compose.py
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.compose import download_clips, load_promo_selection   # noqa: E402
from src.sourcing.models import SourceVideo                             # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


def test_load():
    print("[T1] 홍보영상 선택 로드(promo/{hash}.json → SourceVideo)")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "promo").mkdir(parents=True)
        vids = [
            {"platform": "tiktok", "source_url": "https://tt/1", "download_url": "https://cdn/1.mp4", "view_count": 100},
            {"platform": "tiktok", "source_url": "https://tt/2", "download_url": "https://cdn/2.mp4"},
        ]
        (base / "promo" / "h.json").write_text(json.dumps({"product_hash": "h", "videos": vids}), encoding="utf-8")
        svs = load_promo_selection("h", base_dir=base)
        check(len(svs) == 2 and svs[0].source_url == "https://tt/1", "2개 로드·선택순서 보존")
        check(load_promo_selection("none", base_dir=base) == [], "없는 해시 → []")


def test_download():
    print("[T2] 다운로드 오케스트레이션(어댑터 주입 · 실패 건너뜀)")

    class FakeAd:
        def __init__(self):
            self.n = 0

        def download(self, sv, dest):
            self.n += 1
            if "bad" in sv.source_url:
                sv.status = "failed"
                return None
            p = Path(dest) / f"{self.n}.mp4"
            p.write_bytes(b"x")
            sv.downloaded_path = str(p)
            return p

    svs = [SourceVideo(platform="tiktok", source_url="https://tt/ok1", download_url="u1"),
           SourceVideo(platform="tiktok", source_url="https://tt/bad", download_url="u2"),
           SourceVideo(platform="tiktok", source_url="https://tt/ok2", download_url="u3")]
    with tempfile.TemporaryDirectory() as td:
        out = download_clips(svs, td, adapter=FakeAd())
        check(len(out) == 2, f"성공 2개(실패 1건 건너뜀) ({len(out)})")
        check(all(p.exists() for _, p in out), "다운로드 파일 실제 생성")
        check(out[0][0].source_url == "https://tt/ok1", "성공 항목 순서 보존")

    # 어댑터가 예외를 던져도 크래시 없이 건너뜀
    class BoomAd:
        def download(self, sv, dest):
            raise RuntimeError("차단")
    with tempfile.TemporaryDirectory() as td:
        check(download_clips(svs, td, adapter=BoomAd()) == [], "다운로드 전부 예외 → [](크래시 없음)")


if __name__ == "__main__":
    for fn in [test_load, test_download]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: compose 선택로드·다운로드 정상 (합성 stitch_vertical은 moviepy로 CI 검증).")
