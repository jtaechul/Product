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
    # ★수심 날조 금지(하드룰): 미상('')은 옛 기본값(200,2000)을 폐기하고 (0,0)=미상 → 수심 줄 생략
    assert p("") == (0, 0)


def test_unknown_species_without_llm_uses_deterministic_fallback():
    # ★재발방지 #135(cranchiidae 'LLM 파싱 실패로 제작 중단'): LLM 키가 없어도 시드 외 종은
    #   이름·실제 수심만으로 유효한 일본어 훅을 결정론 생성한다(_fallback_hook). 하드 None 금지.
    info = SpeciesInfo(scientific_name="Xxx yyy", common_name_ko="가", common_name_en="z",
                       depth_range_m="100-200", distribution="", habitat="")
    import os
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GEMINI_API_KEY")):
        h = hook.build_hook(info)
        assert h and h.get("hook_line1") and h.get("hook_line2")   # 폴백이 유효 훅 생성
        # 날조 방지: 미상 아닌 실제 수심(100-200)이 반영, 국문 혼입 없음
        joined = h["hook_line1"] + h["hook_line2"]
        assert "가" not in joined


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
    # ★해시태그 정책(운영자 확정): 끝에 **정확히 2개 = [내용 1개] + [고정 공통 1개]**.
    #   #Shorts 미포함, 고정 공통은 카테고리 태그(심해=#심해생물). 전부 한국어.
    assert cd.hashtags_ko[-1] == "#심해생물"                       # 고정 공통(마지막)
    assert len(cd.hashtags_ko) == 2 and all(_no_japanese(t) for t in cd.hashtags_ko)
    assert not any(t.lower() == "#shorts" for t in (cd.hashtags or []) + (cd.hashtags_ko or []))
    # 일본어판도 동일 정책: [내용, #深海生物]
    assert cd.hashtags[-1] == "#深海生物" and len(cd.hashtags) == 2


def test_shorts_title_ends_with_two_hashtags(monkeypatch):
    """★쇼츠 제목 정책(운영자 확정): 모든 쇼츠 제목 끝에 해시태그 정확히 2개.
    두 태그는 영상 해시태그와 동일(제목·캡션 태그 일치)."""
    import re
    from src.core import llm
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)   # 폴백 강제
    cat = DeepSeaCategory()
    spec, _t, _b = cat.hook_intro_spec(INFO)
    cd = cat.build_reels_caption(INFO, spec)
    for title, tags in ((cd.yt_title, cd.hashtags), (cd.yt_title_ko, cd.hashtags_ko)):
        assert title, "쇼츠 제목이 비었음"
        assert len(re.findall(r"#\S+", title)) == 2, f"제목에 해시태그 2개가 아님: {title}"
        assert title.rstrip().endswith(" ".join(tags[:2])), f"제목 태그가 영상 태그와 불일치: {title}"
