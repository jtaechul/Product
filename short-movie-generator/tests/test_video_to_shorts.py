"""'찾은 영상으로 쇼츠 제작' 경로 — 종명·학명 확보와 라이선스 정규화 회귀 테스트.

운영자 확정: "찾은 영상으로 제작도 되게 해줘. 대신 그 경우엔 종명·학명이 추가로 검색·확보돼야 해."
→ 학명을 확보하지 못하면 **지어내지 않고 제작을 중단**한다(날조 금지 하드룰).
네트워크 호출은 전부 모킹한다(테스트가 외부 상태에 의존하지 않게).
"""
import pytest

from src.core import discovery, footage


# ── 라이선스 정규화(대시보드는 사람이 읽는 라벨을 넘긴다) ──────────────────────
@pytest.mark.parametrize("label,expect", [
    ("Public Domain / CC0", "cc0"),
    ("Public Domain (아카이브 컬렉션)", "public-domain"),
    ("CC BY", "cc-by"),
    ("CC BY-SA", "cc-by-sa"),
    ("cc-by-sa", "cc-by-sa"),
])
def test_license_label_normalized(label, expect):
    assert footage._norm_license(label) == expect


@pytest.mark.parametrize("label", [
    "CC BY-NC (사용 불가)",        # 비상업 — 하드룰 #1
    "CC BY-NC-SA",
    "라이선스 확인 필요",
    "",
])
def test_unusable_license_rejected(label):
    assert footage._norm_license(label) is None


# ── 종 정체성 확보 ────────────────────────────────────────────────────────────
def test_scientific_name_from_title_binomial(monkeypatch):
    """제목에 학명이 있으면 Wikidata 조회로 종을 확보한다."""
    monkeypatch.setattr(discovery, "_search_taxon_by_name",
                        lambda nm: {"qid": "Q1", "sci": "Octopus vulgaris",
                                    "ko": "참문어", "en": "common octopus",
                                    "ja": "マダコ", "sitelinks": {}, "parent_qid": None})
    monkeypatch.setattr(discovery, "_facts_with_fallback",
                        lambda ident: (["연안 암초에 산다."], "Wikipedia (ko)"))
    rec = discovery.resolve_from_video("https://example.invalid/x.mp4",
                                       "Octopus vulgaris hunting at night")
    assert rec is not None
    sp = rec["species"]
    assert sp["scientific_name"] == "Octopus vulgaris"
    assert sp["common_name_ko"] == "참문어"
    assert rec["key"] == "octopus vulgaris"
    assert rec["footage"]["url"] == "https://example.invalid/x.mp4"


def test_blocks_production_when_species_unknown(monkeypatch):
    """★핵심: 학명을 못 찾으면 None → 호출부가 제작을 중단한다(학명 날조 금지)."""
    monkeypatch.setattr(discovery, "_search_taxon_by_name", lambda nm: None)
    assert discovery.resolve_from_video("https://example.invalid/clip.mp4",
                                        "amazing underwater footage 2024") is None


def test_no_facts_still_returns_record(monkeypatch):
    """사실이 빈약해도 학명만 확보되면 제작은 잇는다(게이트를 늘리지 않는다는 방침)."""
    monkeypatch.setattr(discovery, "_search_taxon_by_name",
                        lambda nm: {"qid": "Q2", "sci": "Bathynomus giganteus", "ko": None,
                                    "en": None, "ja": None, "sitelinks": {}, "parent_qid": None})
    monkeypatch.setattr(discovery, "_facts_with_fallback", lambda ident: ([], ""))
    rec = discovery.resolve_from_video("https://example.invalid/x.mp4", "Bathynomus giganteus")
    assert rec and rec["species"]["scientific_name"] == "Bathynomus giganteus"
    # 이름이 없으면 학명으로 대체(빈 문자열 금지 — 화면에 공백이 뜨지 않게)
    assert rec["species"]["common_name_ko"] == "Bathynomus giganteus"


def test_depth_extracted_from_description_only(monkeypatch):
    """수심은 문헌 텍스트에서만 뽑는다(없으면 빈 문자열 — 지어내지 않는다)."""
    monkeypatch.setattr(discovery, "_search_taxon_by_name",
                        lambda nm: {"qid": "Q3", "sci": "Sepia mestus", "ko": None, "en": None,
                                    "ja": None, "sitelinks": {}, "parent_qid": None})
    monkeypatch.setattr(discovery, "_facts_with_fallback", lambda ident: (["얕은 암초에 산다."], "src"))
    rec = discovery.resolve_from_video("https://example.invalid/x.mp4", "Sepia mestus", "")
    assert rec["species"]["depth_range_m"] == ""


def test_footage_record_shape_matches_discovered_schema(monkeypatch):
    """반환 형태가 discovered.json 스키마와 같아야 카테고리 SUBJECTS에 편입된다."""
    monkeypatch.setattr(discovery, "_search_taxon_by_name",
                        lambda nm: {"qid": "Q4", "sci": "Sepia mestus", "ko": "무늬갑오징어",
                                    "en": "reaper cuttlefish", "ja": None, "sitelinks": {},
                                    "parent_qid": None})
    monkeypatch.setattr(discovery, "_facts_with_fallback", lambda ident: (["사실"], "src"))
    rec = discovery.resolve_from_video("https://example.invalid/x.mp4", "Sepia mestus")
    assert set(rec) >= {"key", "kind", "footage", "species"}
    assert rec["kind"] == "creature"
    assert set(rec["footage"]) >= {"url", "license", "credit", "source"}
    assert set(rec["species"]) >= {"scientific_name", "common_name_ko", "common_name_en",
                                   "depth_range_m", "fun_facts", "sources"}


# ── 나레이션형 저작권 표기(엔드카드 없음 → 캡션이 유일한 표기) ────────────────
import pytest as _pytest

from src.core import narrate_attached as _na


@_pytest.mark.parametrize("credit,lic,expect", [
    ("John Turnbull", "cc-by-sa", "John Turnbull · CC BY-SA"),
    ("NOAA Ocean Exploration", "public-domain", "NOAA Ocean Exploration · Public Domain"),
    ("Gary Williams · CC BY-SA", "cc-by-sa", "Gary Williams · CC BY-SA"),   # 중복 미부착
    ("", "cc-by", "CC BY"),
    ("작가만", "", "작가만"),
    ("", "", ""),                                                          # 빈 줄 안 넣음
])
def test_narrate_credit_line(credit, lic, expect):
    assert _na._credit_line(credit, lic) == expect
