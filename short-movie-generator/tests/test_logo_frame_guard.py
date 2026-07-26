"""오프닝 훅·썸네일 표지 프레임에서 '로고·큰 글씨 판'을 제외하는 규칙 회귀 테스트.

운영자 지적(실사고): NOAA 'Earth is Blue' 브랜딩 카드(로고·글씨 가득)가 오프닝 훅과 썸네일
배경으로 쓰였다. 본문 컷 선택은 예전부터 번인 텍스트 구간을 배제했는데, **표지 프레임만**
이 검사를 안 거쳐 시작 0.5초(브랜딩 슬레이트)를 그대로 썼다.

규칙: 표지(오프닝 배경·엔드카드 배경·썸네일·히어로 사진)는 `reframe.LOGO_FRAME_TH` 이상이면 제외.
"""
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from src.core import hook_intro_stage as his
from src.core import reframe

_F = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"


def _slate(path: Path) -> Path:
    """로고·큰 글씨가 가득한 브랜딩 판(문제의 프레임)."""
    im = Image.new("RGB", (640, 360), (4, 6, 10))
    dr = ImageDraw.Draw(im)
    dr.text((30, 60), "NOAA OCEAN EXPLORATION", font=ImageFont.truetype(_F, 42), fill=(255, 255, 255))
    dr.text((30, 150), "Earth is Blue", font=ImageFont.truetype(_F, 56), fill=(245, 245, 255))
    dr.ellipse([430, 210, 600, 350], outline=(255, 255, 255), width=8)
    im.save(path)
    return path


def _sea(path: Path, shift: int = 0) -> Path:
    """보통 수중 프레임(피사체 있음, 글씨 없음)."""
    im = Image.new("RGB", (640, 360), (8, 28, 44))
    dr = ImageDraw.Draw(im)
    x = 80 + shift
    dr.ellipse([x, 120, x + 150, 240], fill=(120, 150, 160))
    dr.ellipse([x + 50, 150, x + 90, 190], fill=(210, 215, 220))
    im.save(path)
    return path


def _sand(path: Path) -> Path:
    """밝은 모래 바닥 — 예전에 텍스트로 오검출되던 유형(오검출 방지 확인용)."""
    import random
    im = Image.new("RGB", (640, 360), (200, 195, 180))
    dr = ImageDraw.Draw(im)
    random.seed(1)
    for _ in range(4000):
        dr.point((random.randrange(640), random.randrange(360)), fill=(230, 225, 210))
    im.save(path)
    return path


@pytest.mark.skipif(not Path(_F).exists(), reason="CJK 폰트 없음")
def test_logo_slate_is_detected_and_normal_frames_are_not(tmp_path):
    """★판별 자체: 로고 판만 걸러지고, 수중 프레임·밝은 모래는 통과해야 한다."""
    assert reframe.is_logo_frame(str(_slate(tmp_path / "slate.jpg")))
    assert not reframe.is_logo_frame(str(_sea(tmp_path / "sea.jpg")))
    assert not reframe.is_logo_frame(str(_sand(tmp_path / "sand.jpg"))), "밝은 모래를 글씨로 오검출"


@pytest.mark.skipif(not Path(_F).exists(), reason="CJK 폰트 없음")
def test_pick_clean_frames_drops_logo_frames(tmp_path):
    cands = [str(_slate(tmp_path / "a.jpg")), str(_sea(tmp_path / "b.jpg")),
             str(_sea(tmp_path / "c.jpg", 60))]
    clean = reframe.pick_clean_frames(cands)
    assert str(tmp_path / "a.jpg") not in clean
    assert len(clean) == 2


@pytest.mark.skipif(not Path(_F).exists(), reason="CJK 폰트 없음")
def test_all_dirty_still_returns_something(tmp_path):
    """전부 로고 판인 소스라도 제작을 막지 않는다(가장 깨끗한 것만 남긴다)."""
    cands = [str(_slate(tmp_path / f"s{i}.jpg")) for i in range(3)]
    clean = reframe.pick_clean_frames(cands, keep_if_all_dirty=1)
    assert len(clean) == 1


@pytest.fixture(scope="module")
def slate_then_sea(tmp_path_factory):
    """앞 3초 = 브랜딩 슬레이트, 뒤 7초 = 수중 장면인 합성 영상(실제 사고 재현)."""
    d = tmp_path_factory.mktemp("logo_src")
    if not Path(_F).exists():
        pytest.skip("CJK 폰트 없음")
    _slate(d / "slate.png")
    for i in range(70):
        _sea(d / f"sea_{i:03d}.png", shift=i * 6)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", "3",
                    "-i", str(d / "slate.png"), "-vf", "fps=10,scale=640:360",
                    "-pix_fmt", "yuv420p", str(d / "a.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "10",
                    "-i", str(d / "sea_%03d.png"), "-pix_fmt", "yuv420p", str(d / "b.mp4")], check=True)
    (d / "l.txt").write_text(f"file '{d}/a.mp4'\nfile '{d}/b.mp4'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(d / "l.txt"), "-c", "copy", str(d / "src.mp4")], check=True)
    return d / "src.mp4"


def test_old_start_frame_would_have_been_a_logo_slate(slate_then_sea, tmp_path):
    """★사고 재현: 예전 폴백(시작 0.5초)은 브랜딩 슬레이트를 그대로 집었다."""
    old = str(tmp_path / "old.png")
    assert his._grab_frame(str(slate_then_sea), 0.5, old)
    assert reframe.is_logo_frame(old), "재현 실패 — 이 테스트의 전제(앞부분이 슬레이트)가 깨졌습니다"


def test_fallback_frame_now_avoids_logo(slate_then_sea, tmp_path):
    """폴백도 여러 시각을 떠서 글씨 없는 프레임을 고른다."""
    out = str(tmp_path / "new.png")
    assert his._grab_clean_frame(str(slate_then_sea), out, his._duration_of(str(slate_then_sea)))
    assert not reframe.is_logo_frame(out), "폴백이 아직 로고 판을 고릅니다"


def test_cover_frame_picker_avoids_logo(slate_then_sea, tmp_path):
    """표지 프레임 선택기(_score_best_frame)도 로고 판을 후보에서 제외한다."""
    best, _score = his._score_best_frame(str(slate_then_sea), tmp_path, n_samples=12)
    assert best and not reframe.is_logo_frame(best)


def test_cover_paths_use_the_guard():
    """소스 계약: 표지 경로들이 실제로 가드를 통과하도록 배선돼 있어야 한다(회귀 금지)."""
    src = Path(his.__file__).read_text(encoding="utf-8")
    assert "pick_clean_frames(grabbed)" in src, "후보 프레임 필터가 빠졌습니다"
    assert "_grab_clean_frame(src_open" in src, "오프닝 폴백이 옛 방식(시작 0.5초)으로 되돌아갔습니다"
    assert "_grab_clean_frame(src_subj" in src, "엔드카드 폴백이 가드를 안 씁니다"
    assert "is_logo_frame(hero)" in src, "히어로 사진 검사가 빠졌습니다"
