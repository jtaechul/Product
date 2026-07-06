"""carousel — 게시물(인스타 캐러셀) 5장 생성 검증.

브라우저(Chromium) 있으면 실제 렌더까지, 없으면 HTML 구성만(마크업) 검증.
"""
import pytest

from src.core import carousel, htmlhud
from src.core.contracts import CaptionData, SpeciesInfo

_HAS_BROWSER = htmlhud._chromium_path() is not None
browser_only = pytest.mark.skipif(not _HAS_BROWSER, reason="Chromium 없음")


def _info():
    return SpeciesInfo(
        scientific_name="Grimpoteuthis spp.", common_name_ko="덤보문어",
        common_name_en="Dumbo octopus", depth_range_m="1000-4000",
        distribution="전 세계 심해", habitat="심해 저층", diet=["갑각류", "다모류"],
        fun_facts=["귀처럼 헤엄친다", "가장 깊은 곳의 문어", "먹물주머니가 없다"],
        sources=["NOAA", "WoRMS"],
    )


def _cap():
    return CaptionData(hook_text="수심 4,000m, 이것이 잡혔습니다", overlay_facts=[],
                       caption_body="본문", hashtags=["#덤보문어", "#심해생물", "#DeepSea"],
                       reveal_name="덤보문어 (Dumbo octopus)", reveal_fact="귀처럼 헤엄치는 문어")


def test_slide_html_has_brand_sources_and_keepall():
    """슬라이드 HTML에 브랜드·출처·팔로우·조판 규칙(keep-all) 마크업이 존재(브라우저 불필요)."""
    src = carousel._source(_info(), _cap(), "Jane / Wikimedia Commons (cc-by)")
    assert "SPECIES IDENTIFIED" in src and "덤보문어" in src
    assert "이미지 출처: Jane / Wikimedia Commons (cc-by)" in src
    assert "정보 출처: NOAA · WoRMS" in src
    assert "word-break:keep-all" in src            # 화면 조판 하드룰
    cov = carousel._cover(_info(), _cap(), "", 7)
    assert "UNIDENTIFIED SPECIMEN" in cov and "No.007" in cov


@browser_only
def test_build_carousel_renders_five_slides(tmp_path):
    pngs = carousel.build_carousel(_info(), _cap(), "NOAA (public-domain)", "",
                                   str(tmp_path), 7, eco_line="수심 1000-4000m · 심해 저층")
    assert len(pngs) == 5
    from PIL import Image
    for p in pngs:
        assert Image.open(p).size == (carousel.CW, carousel.CH)  # 1080x1080 (1:1 카드뉴스)
    assert carousel.CW == carousel.CH == 1080  # 무조건 1:1
