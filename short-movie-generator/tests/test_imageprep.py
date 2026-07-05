"""imageprep 테스트 — 16:9 소스를 9:16 세로 캔버스로 사전 합성 (문제1 근본 해결)."""
from PIL import Image

from src.core import imageprep


def _probe(path):
    return Image.open(path).size


def test_landscape_to_9x16_fills_frame(tmp_path):
    """16:9 가로 → 720x1280 풀프레임 (하드 검은 바 없이 블러-다크 연장)."""
    src = tmp_path / "wide.jpg"
    Image.new("RGB", (1024, 576), (40, 90, 130)).save(src)
    out = imageprep.to_vertical_9x16(str(src), str(tmp_path / "v.png"))
    assert _probe(out) == (720, 1280)

    # 상단(확장 구역)이 순수 검정(하드 바)이 아니라 배경색이 있어야 함(블러-다크 연장)
    im = Image.open(out)
    top_px = im.getpixel((360, 20))
    assert sum(top_px) > 6, "상단이 완전한 검은 바 → 블러 연장 실패"
    # 배경은 전경보다 어둡게 처리됨(전경 중앙이 더 밝아야)
    center_px = im.getpixel((360, 640))
    assert sum(center_px) > sum(top_px)


def test_tall_image_cover_cropped(tmp_path):
    """이미 세로로 긴 이미지는 cover-크롭으로 풀프레임(배경 불필요)."""
    src = tmp_path / "tall.jpg"
    Image.new("RGB", (600, 1600), (30, 30, 30)).save(src)
    out = imageprep.to_vertical_9x16(str(src), str(tmp_path / "v.png"))
    assert _probe(out) == (720, 1280)


def test_square_image(tmp_path):
    src = tmp_path / "sq.jpg"
    Image.new("RGB", (800, 800), (50, 50, 50)).save(src)
    out = imageprep.to_vertical_9x16(str(src), str(tmp_path / "v.png"))
    assert _probe(out) == (720, 1280)
