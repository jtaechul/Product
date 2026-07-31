"""★검증 완료 NOAA 심해생물 클립 풀 — 라이선스·실측치·배선 계약(운영자 지시).

운영자 지시: "심해 생물 영상 소스를 추가로 확보해라."
확보 방식: NOAA 심해탐사(oceanexplorer.noaa.gov)의 mp4 **전량 1,563개**를 열거 →
  심해 생물 클립만 추림 → **실제로 내려받아** 재생·길이·움직임·크레딧 슬레이트를 실측 →
  통과분만 `src/data/noaa_clips.py`에 등록.

라이선스: 미 연방정부 저작물 = **퍼블릭도메인**(프로젝트 허용 목록).
  ⚠ 허용 목록 밖 라이선스가 섞이면 제작이 통째로 막히므로 여기서 못박는다.
★종(학명) 단정 금지: NOAA 파일명은 일반명 수준이라 학명을 임의로 붙이지 않는다.
"""
import pytest

from src.core.contracts import ALLOWED_LICENSES
from src.data import noaa_clips as NC


def test_pool_has_enough_verified_clips():
    """운영자 요구치(10개 이상)를 실제로 넘겼는지 — 목록 자체로 확인한다."""
    assert len(NC.CLIPS) >= 10, f"확보된 클립이 부족합니다: {len(NC.CLIPS)}건"


def test_license_is_allowed():
    assert NC.LICENSE in ALLOWED_LICENSES, f"허용되지 않는 라이선스: {NC.LICENSE}"
    assert NC.LICENSE == "public-domain", "NOAA(미 연방 저작물)는 퍼블릭도메인이어야 합니다"
    assert NC.CREDIT.strip(), "크레딧 표기가 비어 있으면 화면 표기가 허위가 됩니다"


@pytest.mark.parametrize("c", NC.CLIPS, ids=[c["tags"][0] for c in NC.CLIPS])
def test_each_clip_passed_the_real_measurements(c):
    """등록된 클립은 모두 **실측을 통과한 값**을 갖고 있어야 한다(주장만 있으면 안 된다)."""
    assert c["url"].startswith("https://oceanexplorer.noaa.gov/"), f"출처가 NOAA가 아님: {c['url']}"
    assert c["url"].lower().endswith(".mp4")
    assert c["dur"] >= 8.0, f"너무 짧음: {c['dur']}초"
    assert c["w"] >= 640 and c["h"] >= 360, f"저해상도: {c['w']}x{c['h']}"
    assert c["motion"] >= 3.0, f"정지 화면에 가까움(움직임 {c['motion']})"
    assert c["tags"], "어떤 생물인지 가리키는 낱말이 없습니다"


def test_no_duplicate_urls():
    urls = [c["url"] for c in NC.CLIPS]
    assert len(urls) == len(set(urls)), "같은 영상이 중복 등록되어 있습니다"


def test_find_matches_by_common_name():
    assert NC.find("dumbo octopus"), "일반명으로 클립을 찾지 못합니다"
    assert NC.find("comb jelly"), "빗해파리 클립을 찾지 못합니다"
    assert NC.find("hagfish") and NC.find("chimaera"), "구체적인 이름이 매칭돼야 합니다"
    assert NC.find("") == [], "빈 입력에 결과를 주면 안 됩니다"
    assert NC.find("giraffe") == [], "무관한 이름에 클립을 주면 안 됩니다"


def test_generic_words_never_match():
    """★품질 규칙: "fish"·"coral" 같은 흔한 낱말로는 매칭하지 않는다.

    거의 모든 종 이름에 들어 있어 그대로 두면 **무관한 종에 엉뚱한 영상**이 붙는다
    (실제로 가상의 'test fish'가 NOAA 일반 어류 클립을 물어 오던 것을 막았다)."""
    for q in ("fish", "test fish", "coral", "corals", "star"):
        assert NC.find(q) == [], f"너무 일반적인 낱말이 매칭됐습니다: {q!r}"


def test_sourcing_consults_the_pool_first():
    """배선 계약: 소싱이 라이브 검색보다 **먼저** 검증된 풀을 본다(간헐 실패·품질 편차 회피)."""
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "src" / "core" / "footage.py").read_text(
        encoding="utf-8")
    assert "def _noaa_curated(" in s, "검증 풀 조회 경로가 없습니다"
    i, j = s.index("cand = _noaa_curated("), s.index("ext = (_noaa_oer_videos(")
    assert i < j, "검증된 풀보다 라이브 검색을 먼저 보고 있습니다"


def test_curated_lookup_returns_allowed_license():
    from src.core import footage as F
    c = F._noaa_curated("Grimpoteuthis sp.", "dumbo octopus")
    assert c and c["license"] in ALLOWED_LICENSES
    assert c["credit"] == NC.CREDIT
    assert F._noaa_curated("Xxx yyy", "giraffe") is None, "무관한 종에 영상을 주면 안 됩니다"
