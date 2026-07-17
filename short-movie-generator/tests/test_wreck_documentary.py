"""침몰선 다큐 시퀀스 빌더(footage.build_wreck_documentary) — 오프라인(네트워크 없이) 테스트.

네트워크를 타지 않도록, 다운로드 대상 경로(wdoc_{i}.png)에 로컬 이미지를 미리 깔아 둔다
(빌더는 파일이 이미 있으면 다운로드를 건너뛴다)."""
import os
import shutil
import subprocess

import pytest

from src.core import footage as F


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _noise_png(path: str, color: int) -> None:
    from PIL import Image
    import random
    rnd = random.Random(color)
    im = Image.new("RGB", (1200, 800))
    im.putdata([(rnd.randint(0, 255), (color * 7) % 255, rnd.randint(0, 255))
                for _ in range(1200 * 800)])
    im.save(path, quality=92)


def test_rep_license_picks_strongest_attribution():
    assert F._rep_license(["cc-by-sa", "public-domain"]) == "cc-by-sa"
    assert F._rep_license(["public-domain", "cc-by"]) == "cc-by"
    assert F._rep_license(["cc0", "public-domain"]) == "cc0"
    assert F._rep_license(["public-domain"]) == "public-domain"


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 없음")
def test_build_documentary_sequences_distinct_images(tmp_path):
    dest = tmp_path / "d"; dest.mkdir()
    # 3개 서로 다른 이미지를 다운로드 경로에 미리 배치(네트워크 우회)
    for i in range(3):
        _noise_png(str(dest / f"wdoc_{i}.png"), color=40 + i * 60)
    images = [
        {"url": "http://x/a.png", "beat": "afloat", "license": "cc-by", "credit": "A · CC BY"},
        {"url": "http://x/b.png", "beat": "sinking", "license": "public-domain", "credit": "B"},
        {"url": "http://x/c.png", "beat": "wreck", "license": "cc-by-sa", "credit": "C · CC BY-SA"},
    ]
    res = F.build_wreck_documentary(images, str(dest), target_dur=12.0, key="wreck test")
    assert res and res.get("sequenced") is True
    assert res["beats"] == ["afloat", "sinking", "wreck"]
    assert res["license"] == "cc-by-sa"                      # 혼합 → 가장 강한 표시의무
    assert os.path.exists(res["path"])
    dur = F._probe_dur(res["path"]) or 0
    assert dur >= 12.0 - 0.5                                 # 합 ≥ target(다운스트림 무반복 보장)


def test_build_documentary_empty_returns_none(tmp_path):
    assert F.build_wreck_documentary([], str(tmp_path), target_dur=10) is None


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 없음")
def test_build_map_cut_silent_vertical(tmp_path):
    """★침몰 위치 지도 컷: 9:16 무음 mp4가 만들어지고 좌표 락온 프레임이 나온다."""
    from src.core import reels_stinger as RS
    out = tmp_path / "map.mp4"
    r = RS.build_map_cut(41.73, -49.95, "北大西洋", "N. ATLANTIC",
                         str(out), str(tmp_path / "wmap"), dur=2.6)
    assert r and os.path.exists(r["path"])
    assert (F._probe_dur(r["path"]) or 0) >= 2.0
    # 무음(오디오 스트림 없음) 확인
    pr = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                         "-show_entries", "stream=index", "-of", "csv=p=0", r["path"]],
                        capture_output=True, text=True)
    assert pr.stdout.strip() == "", "지도 컷은 무음이어야(나레이션이 위에 얹힘)"


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 없음")
def test_build_documentary_inserts_video_map_cut(tmp_path):
    """★사전 렌더 영상(지도 컷) 항목이 시퀀스에 그대로 들어가고, 총 길이가 target에 근접한다
    (뒤쪽 잔해 컷이 과오버슛 트림으로 잘리지 않도록)."""
    dest = tmp_path / "d"; dest.mkdir()
    for i in (0, 2, 3):                       # afloat·sinking·wreck 이미지(다운로드 우회)
        _noise_png(str(dest / f"wdoc_{i}.png"), color=40 + i * 40)
    mapv = tmp_path / "mapcut.mp4"            # 지도 컷(무음 영상 항목)
    from src.core import reels_stinger as RS
    RS.build_map_cut(41.73, -49.95, "北大西洋", "N. ATLANTIC", str(mapv), str(tmp_path / "wm"), dur=2.6)
    images = [
        {"url": "http://x/a.png", "beat": "afloat", "license": "public-domain", "credit": "A"},
        {"video": str(mapv), "beat": "map", "license": "public-domain", "credit": "地図"},
        {"url": "http://x/c.png", "beat": "sinking", "license": "cc-by", "credit": "C"},
        {"url": "http://x/d.png", "beat": "wreck", "license": "cc-by-sa", "credit": "D"},
    ]
    res = F.build_wreck_documentary(images, str(dest), target_dur=18.0, key="map test")
    assert res and res["sequenced"] is True
    assert "map" in res["beats"] and res["beats"].index("map") < res["beats"].index("wreck")
    # ★지도 컷 시작 시각을 반환해야(파이프라인이 이 시각에 스캔/락온 SFX를 믹스)
    assert res["map_start"] is not None and res["map_start"] > 0
    dur = F._probe_dur(res["path"]) or 0
    assert 18.0 - 0.5 <= dur <= 18.0 + 2.5, f"총 길이가 target 근접이어야(과오버슛 금지): {dur}"


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 없음")
def test_build_documentary_with_relative_workdir(tmp_path, monkeypatch):
    """★재발방지(실사고: 난파선 5건 전부 실패): work_dir가 **상대경로**(CI 조건)일 때도
    concat이 성공해야 한다. 예전엔 cwd=dest로 실행하면서 -i·출력에 cwd-상대경로를 넘겨
    'work/wdoc/work/wdoc/wdoc_list.txt'로 이중 중첩 → No such file로 전부 죽었다."""
    monkeypatch.chdir(tmp_path)                 # 파이프라인처럼 임의 작업 디렉토리에서 실행
    rel = os.path.join("work", "wdoc")          # ★상대 work_dir(핵심 조건)
    os.makedirs(rel, exist_ok=True)
    for i in range(3):
        _noise_png(os.path.join(rel, f"wdoc_{i}.png"), color=30 + i * 50)
    images = [
        {"url": "http://x/a.png", "beat": "afloat", "license": "cc-by", "credit": "A · CC BY"},
        {"url": "http://x/b.png", "beat": "sinking", "license": "public-domain", "credit": "B"},
        {"url": "http://x/c.png", "beat": "wreck", "license": "cc-by-sa", "credit": "C · CC BY-SA"},
    ]
    res = F.build_wreck_documentary(images, rel, target_dur=12.0, key="wreck relative")
    assert res and res.get("sequenced") is True, "상대 work_dir에서 다큐 합성 실패(경로 이중중첩 회귀)"
    assert os.path.exists(res["path"])
    assert (F._probe_dur(res["path"]) or 0) >= 12.0 - 0.5
