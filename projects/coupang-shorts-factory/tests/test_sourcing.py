"""소싱 데이터 모델·어댑터 단위 테스트 (SSOT §11·§6.2·§6.3).

네트워크·yt-dlp 없이 돈다(info_fn/download_fn 주입). pytest 없이 직접 실행:
    python tests/test_sourcing.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing.models import (Clip, Project, SourceVideo, load_project,      # noqa: E402
                                 load_source_video, save_project, save_source_video)
from src.sourcing.base import Seed, available, get_adapter                       # noqa: E402
from src.sourcing.manual_seed import ManualSeedAdapter                           # noqa: E402

_fails = []


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


def test_model_roundtrip():
    print("[T1] 모델 to_dict/from_dict 왕복")
    clip = Clip(source_video_id="sv_x", start_time=1.5, end_time=6.0,
                zoom_region={"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.5}, zoom_scale=1.4)
    check(abs(clip.duration() - 4.5) < 1e-9, "Clip.duration 계산")
    c2 = Clip.from_dict(clip.to_dict())
    check(c2.to_dict() == clip.to_dict(), "Clip 왕복 무손실")

    sv = SourceVideo(platform="tiktok", source_url="https://t/x", view_count=1234,
                     tags=["쇼핑", "가젯"], source_mode="manual", status="discovered",
                     title="테스트", duration=18.0, uploader="seller")
    sv2 = SourceVideo.from_dict(sv.to_dict())
    check(sv2.to_dict() == sv.to_dict(), "SourceVideo 왕복 무손실")

    prj = Project(title="P", source_video_ids=[sv.id], clips=[clip],
                  clip_order=[clip.clip_id])
    prj2 = Project.from_dict(prj.to_dict())
    check(prj2.to_dict() == prj.to_dict(), "Project 왕복 무손실(중첩 Clip 포함)")


def test_validation():
    print("[T2] 유효성 검사")
    for bad in [dict(platform="p", source_url="u", source_mode="weird"),
                dict(platform="p", source_url="u", status="weird")]:
        try:
            SourceVideo(**bad)
            check(False, f"잘못된 값 거부: {bad}")
        except ValueError:
            check(True, f"잘못된 값 거부: {list(bad)[-1]}")


def test_persist():
    print("[T3] 저장/로드(임시 폴더)")
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        sv = SourceVideo(platform="youtube", source_url="https://y/x")
        save_source_video(sv, base_dir=base)
        got = load_source_video(sv.id, base_dir=base)
        check(got is not None and got.id == sv.id, "SourceVideo 저장→로드")

        prj = Project(title="P", clips=[Clip(source_video_id=sv.id, start_time=0, end_time=3)])
        save_project(prj, base_dir=base)
        gp = load_project(prj.id, base_dir=base)
        check(gp is not None and len(gp.clips) == 1 and gp.title == "P", "Project 저장→로드")
        check(load_source_video("없음", base_dir=base) is None, "없는 id는 None")


def test_ordered_clips():
    print("[T4] clip_order 정렬")
    a = Clip(source_video_id="s", start_time=0, end_time=1, clip_id="clip_a")
    b = Clip(source_video_id="s", start_time=1, end_time=2, clip_id="clip_b")
    c = Clip(source_video_id="s", start_time=2, end_time=3, clip_id="clip_c")
    prj = Project(title="P", clips=[a, b, c], clip_order=["clip_c", "clip_a"])
    order = [x.clip_id for x in prj.ordered_clips()]
    # 지정된 c,a 먼저 → 미지정 b는 뒤에 원래 순서로
    check(order == ["clip_c", "clip_a", "clip_b"], f"정렬 결과 {order}")


def test_registry():
    print("[T5] 어댑터 레지스트리")
    check("manual_seed" in available(), f"manual_seed 등록됨 (available={available()})")
    ad = get_adapter("manual_seed")
    check(ad is not None and ad.mode == "manual", "get_adapter('manual_seed')")
    check(get_adapter("없는어댑터") is None, "없는 어댑터는 None")


def test_manual_seed_search():
    print("[T6] ManualSeedAdapter.search (yt-dlp 주입)")
    fake_info = {"extractor_key": "TikTok", "webpage_url": "https://www.tiktok.com/@x/video/1",
                 "view_count": 55000, "tags": ["가전", "꿀템"], "title": "신박한 물건",
                 "duration": 21.0, "uploader": "seller_kim"}
    ad = ManualSeedAdapter(info_fn=lambda url: fake_info)
    res = ad.search(Seed(kind="url", value="https://www.tiktok.com/@x/video/1"))
    check(len(res) == 1, "URL 시드 → 1건")
    sv = res[0]
    check(sv.platform == "tiktok" and sv.view_count == 55000
          and sv.tags == ["가전", "꿀템"] and sv.source_mode == "manual"
          and sv.status == "discovered", "메타 매핑 정확")

    # 검색 실패(예외) → 빈 리스트, 크래시 없음
    def boom(url):
        raise RuntimeError("차단됨")
    check(ManualSeedAdapter(info_fn=boom).search(Seed(kind="url", value="u")) == [],
          "메타 조회 예외 → [](크래시 없음)")

    # 해시태그 시드 → 미구현이라 [](크래시 없음)
    check(ad.search(Seed(kind="hashtag", value="#꿀템")) == [],
          "hashtag 시드 → [](미구현 안내)")


def test_manual_seed_download():
    print("[T7] ManualSeedAdapter.download (주입)")
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        sv = SourceVideo(platform="tiktok", source_url="https://t/x")

        def fake_dl(url, dd):
            p = Path(dd) / "out.mp4"
            p.write_bytes(b"\x00\x00")
            return p
        out = ManualSeedAdapter(download_fn=fake_dl).download(sv, dest)
        check(out is not None and out.exists() and sv.status == "downloaded"
              and sv.downloaded_path == str(out), "다운로드 성공 → status/path 갱신")

        sv2 = SourceVideo(platform="tiktok", source_url="https://t/y")
        out2 = ManualSeedAdapter(download_fn=lambda u, d: None).download(sv2, dest)
        check(out2 is None and sv2.status == "failed", "다운로드 실패 → status=failed, None")


if __name__ == "__main__":
    for fn in [test_model_roundtrip, test_validation, test_persist, test_ordered_clips,
               test_registry, test_manual_seed_search, test_manual_seed_download]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 전체 통과 — 소싱 데이터 모델·어댑터 골격 정상.")
