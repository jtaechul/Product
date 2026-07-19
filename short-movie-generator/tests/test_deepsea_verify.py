"""심해 적합성 검증(deepsea_verify) — 결정론 단위 테스트(네트워크 불필요).

사고 재발 방지: 정어리(Sardinops sagax)가 '심해 도감'에 편입돼 가짜 '水深 200〜2,000 m'가
붙었다. 표층·연안 종은 배제하고, 심해 근거(수심≥200 m·심해대 키워드)가 있는 종만 통과시킨다."""
import pytest

from src.core import deepsea_verify as V


def test_sardine_rejected():
    # 정어리 = 표층 회유어(Clupeidae/Alosidae). 반드시 배제 + 수심 미표기.
    v = V.verdict("Sardinops sagax", "Pacific sardine",
                  "Sardinops is a genus of sardines of the family Alosidae. "
                  "Often considered monotypic. Its length is up to 40 cm.")
    assert v.ok is False
    assert v.depth_range_m == ""            # 가짜 수심 절대 부여 금지


def test_shallow_coastal_species_rejected():
    for sci, en, txt in [
        ("Sepia officinalis", "common cuttlefish", "a coastal cuttlefish of shallow waters"),
        ("Octopus vulgaris", "common octopus", "found in coastal waters and reefs"),
        ("Aplysia kurodai", "sea hare", "an intertidal sea hare grazing on algae"),
        ("Engraulis japonicus", "Japanese anchovy", "a small pelagic anchovy"),
        ("Scomber japonicus", "chub mackerel", "an epipelagic mackerel"),
    ]:
        v = V.verdict(sci, en, txt)
        assert v.ok is False, f"{sci} 는 표층·연안 → 배제돼야"


def test_deep_species_by_depth_number():
    # 문헌에 서식 수심 ≥200 m 수치가 있으면 통과 + 실제 값 추출.
    v = V.verdict("Rimicaris exoculata", "vent shrimp",
                  "found at hydrothermal vents at depths of 2,300 m along the Mid-Atlantic Ridge")
    assert v.ok is True
    assert "2300" in v.depth_range_m       # 콤마 흡수 + 실제 값


def test_deep_species_by_keyword_without_number():
    # 수심 수치가 없어도 심해대 키워드가 있으면 통과 — 단, 수심은 지어내지 않고 ''.
    v = V.verdict("Duobrachium sparksae", "ctenophore",
                  "a deep-sea benthic ctenophore observed by ROV in the abyssal zone")
    assert v.ok is True
    assert v.depth_range_m == ""


def test_no_evidence_rejected():
    # 표층 배제엔 안 걸리지만 심해 근거도 전혀 없으면 배제(수심 날조 방지).
    v = V.verdict("Lingulodinium polyedra", "dinoflagellate",
                  "a bioluminescent dinoflagellate forming red tides near the surface")
    assert v.ok is False
    assert v.depth_range_m == ""


def test_extract_depth_handles_commas_and_ranges():
    assert V.extract_depth("between 200 and 2,000 m") == "200-2000"
    assert V.extract_depth("at a depth of 4,000 m") == "4000"
    assert V.extract_depth("length up to 40 cm; weighs 3 kg") == ""   # 단위 m 아님 → 무시


# ── 제작 직전 게이트(verify_subject) — 표층 종은 렌더 전에 차단(네트워크 불필요) ──
def test_production_gate_blocks_surface_species():
    from src.categories.deep_sea.module import DeepSeaCategory
    from src.core.contracts import PipelineError, SpeciesInfo
    cat = DeepSeaCategory()
    for sci, ko, en in [("Octopus vulgaris", "참문어", "common octopus"),
                        ("Sepia officinalis", "갑오징어", "common cuttlefish"),
                        ("Sardinops sagax", "정어리", "Pacific sardine")]:
        info = SpeciesInfo(scientific_name=sci, common_name_ko=ko, common_name_en=en,
                           depth_range_m="", distribution="", habitat="", diet=[],
                           fun_facts=["a coastal species"], sources=[])
        with pytest.raises(PipelineError):
            cat.verify_subject(info)


def test_production_gate_allows_deep_species_with_local_evidence():
    from src.categories.deep_sea.module import DeepSeaCategory
    from src.core.contracts import SpeciesInfo
    cat = DeepSeaCategory()
    info = SpeciesInfo(scientific_name="Rimicaris exoculata", common_name_ko="열수분출공새우",
                       common_name_en="vent shrimp", depth_range_m="2300",
                       distribution="", habitat="hydrothermal vents", diet=[],
                       fun_facts=["lives at hydrothermal vents at 2,300 m depth"], sources=[])
    cat.verify_subject(info)   # 심해 근거 충분 → 예외 없이 통과


def test_habitat_region_verified_against_literature():
    """★서식해역 표기(北大西洋 등) + 문헌 일치 검증. 문헌이 뒷받침할 때만 라벨을 내고,
    데이터만 있고 문헌 근거 없으면 None(일반 라벨 폴백 · 날조 금지). 문헌이 데이터와 다르면 문헌 우선."""
    from src.core import deepsea_verify as dv
    # 데이터·문헌 일치 → 그 basin
    r = dv.habitat_region("북태평양 심해", "found in the North Pacific at bathyal depths")
    assert r and (r.label_jp, r.label_en) == ("北太平洋", "N. PACIFIC")
    assert r.lat is not None and r.lon is not None            # basin 중심 락온 좌표 존재
    # 범존(cosmopolitan) → 全世界の海(특정 락온 없음)
    r = dv.habitat_region("전 세계 심해", "cosmopolitan species found worldwide in all oceans")
    assert r and r.label_en == "WORLDWIDE" and r.lat is None
    # 데이터는 해역 주장, 문헌은 근거 없음 → None(폴백, 날조 금지)
    assert dv.habitat_region("북태평양 심해", "just some facts, no ocean named") is None
    # 문헌이 데이터와 다른 구체 basin → 문헌 우선
    r = dv.habitat_region("북태평양", "actually recorded only from the South Pacific")
    assert r and r.label_en == "S. PACIFIC"
    # 지중해 고유종
    r = dv.habitat_region("지중해", "endemic to the Mediterranean Sea, deep water")
    assert r and r.label_en == "MEDITERRANEAN"


def test_dive_transition_sfx_synthesizes_valid_wav(tmp_path):
    """★전환 효과음 합성 폴백(운영자 파일 없을 때 무음 방지): 유효한 WAV를 만든다."""
    import wave
    from src.core.longform import sfx
    p = sfx.gen_dive_transition(str(tmp_path / "tr.wav"))
    w = wave.open(p)
    try:
        assert w.getframerate() == 44100 and 0.5 < w.getnframes() / w.getframerate() < 1.5
    finally:
        w.close()
