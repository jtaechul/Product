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
