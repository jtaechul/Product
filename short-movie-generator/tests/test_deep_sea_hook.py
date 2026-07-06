"""deep_sea 일본어 훅 + hook_intro_spec 검증."""
from src.categories.deep_sea import hook
from src.categories.deep_sea.module import DeepSeaCategory
from src.core.contracts import SpeciesInfo

INFO = SpeciesInfo(scientific_name="Enypniastes eximia", common_name_ko="유메나마코",
                   common_name_en="sea pig", depth_range_m="500-6000",
                   distribution="global", habitat="abyssal", fun_facts=["swims", "glows"])


def test_seed_hook_flagship():
    h = hook.build_hook(INFO)
    assert h and h["jp_name"] == "ユメナマコ"
    assert h["hook_line1"] and h["hook_line2"]
    assert len(h["pop_words"]) >= 2


def test_hook_intro_spec_builds_spec():
    spec, hook_text, bgm = DeepSeaCategory().hook_intro_spec(INFO)
    assert spec.jp_name == "ユメナマコ"
    assert spec.sci_name == "Enypniastes eximia"  # 속명 첫 글자 대문자
    assert (spec.depth_min, spec.depth_max) == (500, 6000)
    assert hook_text == spec.hook_line1 + spec.hook_line2


def test_depth_parsing():
    p = DeepSeaCategory._parse_depth
    assert p("1000-4000") == (1000, 4000)
    assert p("2000") == (1000, 2000)
    assert p("") == (200, 2000)


def test_unknown_species_without_llm_returns_none():
    # LLM 키 없으면 시드 외 종은 None(시스템 휴면·발행 불정지)
    info = SpeciesInfo(scientific_name="Xxx yyy", common_name_ko="가", common_name_en="z",
                       depth_range_m="100-200", distribution="", habitat="")
    import os
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        assert hook.build_hook(info) is None
