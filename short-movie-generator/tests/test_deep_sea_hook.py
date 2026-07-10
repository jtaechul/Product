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


def test_seed_hooks_have_korean_translations():
    """모든 시드 종은 훅·특징의 한국어 번역을 갖는다(대시보드 우측 프레임용)."""
    for key, s in hook._SEED.items():
        assert s.get("hook_ko"), f"{key}: hook_ko 없음"
        assert s.get("feature_ko"), f"{key}: feature_ko 없음"


def _no_japanese(text: str) -> bool:
    import re
    return not re.search(r"[ぁ-んァ-ヶ一-龯]", text)


def test_fallback_ko_caption_fully_korean(monkeypatch):
    """(실제 결함 회귀) 폴백 한국어 캡션에 일본어 원문이 그대로 남으면 안 된다."""
    from src.core import llm
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)   # LLM 강제 실패 → 폴백
    c = hook.build_reels_caption(INFO, "ユメナマコ", "Enypniastes eximia",
                                 "泳ぐ・光る・透ける、深海のナマコ", "頭も、目も、", "骨もない。",
                                 hook_ko="머리도, 눈도, 뼈도 없다.",
                                 feature_ko="헤엄치고·빛나고·비치는, 심해의 해삼")
    assert c["ko"] and _no_japanese(c["ko"]), f"KO 캡션에 일본어 잔류: {c['ko'][:80]}"
    assert len(c["tags_ko"]) == 3 and all(_no_japanese(t) for t in c["tags_ko"])


def test_reels_captiondata_separates_jp_and_ko(monkeypatch):
    """CaptionData가 JP(발행)와 KO(참고)를 분리 필드로 담는다(합본 금지)."""
    from src.core import llm
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)
    cat = DeepSeaCategory()
    spec, _t, _b = cat.hook_intro_spec(INFO)
    cd = cat.build_reels_caption(INFO, spec)
    assert "한국어 참고 번역" not in cd.caption_body            # 합본 마커 없음
    assert _no_japanese(cd.caption_ko)
    assert cd.hook_ko and _no_japanese(cd.hook_ko)
    # 공통 태그(#심해·#해양생물)는 항상 앞에 포함(운영자 요청, _with_core_tags). 총 3~5개, 전부 한국어.
    assert "#심해" in cd.hashtags_ko and "#해양생물" in cd.hashtags_ko
    assert 3 <= len(cd.hashtags_ko) <= 5 and all(_no_japanese(t) for t in cd.hashtags_ko)
