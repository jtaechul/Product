"""deep_sea 카테고리 + 정확성 게이트 + 레지스트리 테스트."""
import pytest

from src.core.contracts import CutSpec, Situation
from src.registry import get_category, list_categories


@pytest.fixture
def cat():
    return get_category("deep_sea")


def test_registry_loads_deep_sea(cat):
    assert cat.category_id == "deep_sea"
    assert "deep_sea" in list_categories()


def test_parse_input_aliases(cat):
    assert cat.parse_input("dumbo octopus") == "dumbo octopus"
    assert cat.parse_input("덤보문어") == "dumbo octopus"
    assert cat.parse_input("Dumbo") == "dumbo octopus"


def test_parse_input_unknown_raises(cat):
    from src.core.contracts import PipelineError

    with pytest.raises(PipelineError):
        cat.parse_input("nonexistent creature xyz")


def test_info_and_situation(cat):
    info = cat.get_info("dumbo octopus")
    assert info.common_name_ko == "덤보문어"
    situation = cat.get_situation(info)
    assert len(situation.cuts) == 3
    assert [c.cut_type for c in situation.cuts] == ["discovery", "behavior", "detail"]


def test_seed_cuts_pass_accuracy(cat):
    info = cat.get_info("dumbo octopus")
    situation = cat.get_situation(info)
    assert cat.validate_cuts(situation) == []


def test_bioluminescent_violation_detected(cat):
    # bioluminescent=False 인데 발광 표현 → 위반 검출돼야 함
    bad = Situation(
        species="dumbo octopus", scientific_name="x",
        accuracy_flags={"bioluminescent": False},
        situation_id="s",
        cuts=[CutSpec("discovery", "a glowing bioluminescent octopus in the dark")],
    )
    violations = cat.validate_cuts(bad)
    assert any("발광" in v or "biolumin" in v for v in violations)


def test_banned_fiction_terms_detected(cat):
    bad = Situation(
        species="dumbo octopus", scientific_name="x",
        accuracy_flags={"bioluminescent": True},
        situation_id="s",
        cuts=[CutSpec("discovery", "a diver finds treasure near the octopus")],
    )
    violations = cat.validate_cuts(bad)
    assert len(violations) >= 2  # diver + treasure


@pytest.mark.parametrize("prompt", [
    "the octopus attacks its prey",
    "hunting a fish in the dark",
    "preying on small crustaceans",
    "devours a passing shrimp",
    "a colossal giant creature looms",
])
def test_predation_variants_blocked(cat, prompt):
    """어형 변화(attacks/hunting/preying/devours)·과장 크기도 차단돼야 함(우회 방지)."""
    bad = Situation(
        species="dumbo octopus", scientific_name="x",
        accuracy_flags={"bioluminescent": True}, situation_id="s",
        cuts=[CutSpec("behavior", prompt)],
    )
    assert cat.validate_cuts(bad), f"차단 실패: {prompt!r}"


@pytest.mark.parametrize("prompt", [
    "a luminescent creature", "glowing photophores line its body",
    "phosphorescent light organ", "발광하는 심해 생물",
])
def test_glow_synonyms_blocked_when_flag_false(cat, prompt):
    bad = Situation(
        species="x", scientific_name="x",
        accuracy_flags={"bioluminescent": False}, situation_id="s",
        cuts=[CutSpec("detail", prompt)],
    )
    assert cat.validate_cuts(bad), f"발광 동의어 차단 실패: {prompt!r}"


def test_floodlight_not_flagged_as_bioluminescence(cat):
    """외부 조명(floodlight/into the light)은 발광이 아니므로 오검출 금지."""
    ok = Situation(
        species="x", scientific_name="x",
        accuracy_flags={"bioluminescent": False}, situation_id="s",
        cuts=[CutSpec("discovery", "a hard floodlight sweeps as it emerges into the light")],
    )
    assert cat.validate_cuts(ok) == []


def test_caption_fallback_without_key(cat, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    info = cat.get_info("dumbo octopus")
    cap = cat.build_caption(info)
    assert cap.hook_text
    # 회귀 복구: 해시태그 풍부한 세트(종명 포함, 3개 고정 폐기)
    assert len(cap.hashtags) >= 5 and cap.hashtags[0] == "#덤보문어"
    assert cap.overlay_facts
