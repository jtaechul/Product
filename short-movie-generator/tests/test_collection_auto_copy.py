"""COPY 시드가 없는 대상도 제작되는지 — 실사고 run #164 회귀 테스트.

실사고: 대시보드에서 marine_life / `sepia mestus`(소싱 승격 대상)를 제작 → 시작 0.0초 만에
`[reels] 일본어 훅 생성 불가(대표종 시드 또는 LLM 키 필요)`로 중단. 원인은 LLM 키가 아니라
collection_base.hook_intro_spec 이 COPY 시드가 없으면 무조건 None 을 돌려준 것 — 즉 손으로
COPY 를 써 넣은 대상만 제작 가능했고, 소싱으로 늘린 대상은 전부 제작 불가였다.

여기서는 **LLM 키가 없는 상태**(결정론 폴백만)로도 훅·본문이 나오는지 확인한다.
"""
import pytest

from src.categories.deep_sea import hook as dhook
from src.core.contracts import SpeciesInfo
from src.registry import get_category


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    """LLM 키를 지워 결정론 폴백 경로만 타게 한다(네트워크 호출 없음)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


_SHALLOW = SpeciesInfo(
    scientific_name="Sepia mestus", common_name_ko="Sepia mestus",
    common_name_en="Reaper cuttlefish", depth_range_m="0-22",
    distribution="호주 동부", habitat="얕은 암초", diet=[], fun_facts=[],
    sources=["Wikimedia Commons"],
)


def _marine_life_with_subject():
    cat = get_category("marine_life")
    cat.SUBJECTS = dict(cat.SUBJECTS)
    cat.SUBJECTS["sepia mestus"] = {
        "scientific_name": "Sepia mestus", "common_name_ko": "Sepia mestus",
        "common_name_en": "Reaper cuttlefish", "depth_range_m": "0-22",
        "distribution": "호주 동부", "habitat": "얕은 암초",
        "diet": [], "fun_facts": [], "sources": ["Wikimedia Commons"],
    }
    return cat


def test_hook_spec_generated_without_copy_seed():
    """★핵심: COPY가 없어도 hook_intro_spec이 None을 돌려주지 않는다(예전엔 여기서 제작 중단)."""
    cat = _marine_life_with_subject()
    assert not cat.COPY.get(cat._key_for(_SHALLOW))     # COPY 시드 없음(실사고와 동일 조건)
    spec_t = cat.hook_intro_spec(_SHALLOW)
    assert spec_t is not None
    spec, hook_text, _bgm = spec_t
    assert spec.jp_name and hook_text.strip()
    assert spec.hook_line1 and spec.hook_line2
    assert spec.hook_pop_words


def test_body_script_generated_without_copy_seed():
    cat = _marine_life_with_subject()
    body = cat.reels_body_script(_SHALLOW)
    assert body and len(body) >= 8
    assert all(isinstance(x, str) and x.strip() for x in body)


def test_shallow_species_never_called_deep_sea():
    """얕은 바다 종에 '深海/심해'를 붙이지 않는다(날조 금지 하드룰)."""
    cat = _marine_life_with_subject()
    spec, hook_text, _ = cat.hook_intro_spec(_SHALLOW)
    body = cat.reels_body_script(_SHALLOW)
    blob = hook_text + spec.feature_line + "".join(body)
    assert "深海" not in blob


def test_deep_sea_wording_preserved_for_deep_species():
    """반대로 심해 종은 기존 '深海' 문구를 그대로 유지한다(회귀 없음)."""
    deep = SpeciesInfo("Cranchiidae sp.", "유리오징어", "Glass squid", "200-1000",
                       "", "", [], [], [])
    h = dhook.build_hook(deep)                       # topic 미지정 = deep_sea(기본)
    body = dhook._fallback_body_jp(deep)
    assert "深海" in h["feature_line"]
    assert any("深海" in x for x in body)
    assert "高い水圧の中で、" in body                 # 심해 전용 서술 유지


def test_seeded_species_unchanged():
    """시드가 있는 대표종은 예전 카피 그대로(자동 생성으로 대체되지 않는다)."""
    hcm = SpeciesInfo("Enypniastes eximia", "머리없는닭괴물", "Headless chicken monster",
                      "500-6000", "", "", [], [], [])
    h = dhook.build_hook(hcm)
    assert h["jp_name"] == "ユメナマコ"
    assert h["hook_line1"] + h["hook_line2"] == "頭も、目も、骨もない。"


def test_shipwreck_opts_out_of_creature_copy():
    """침몰선은 생물이 아니므로 생물용 카피 자동 생성을 하지 않는다(오정보 방지)."""
    wreck = get_category("shipwreck")
    assert wreck.auto_copy is False
    wi = SpeciesInfo("Wreck Unknown", "무명 난파선", "Unknown wreck", "30",
                     "", "", [], [], [])
    assert wreck.hook_intro_spec(wi) is None
    assert wreck.reels_body_script(wi) is None


def test_topic_table_covers_collection_categories():
    """카테고리가 지정한 jp_topic이 실제 토픽 표에 있어야 한다(오타 시 조용히 심해로 폴백 방지)."""
    for cid in ("marine_life", "marine_algae"):
        cat = get_category(cid)
        assert cat.jp_topic in dhook._TOPICS, cid


# ── 크레딧/라이선스 표기(하드룰 #1) ────────────────────────────────────────────
def test_credit_label_follows_actual_license():
    """★실사고: 커먼스 CC BY-SA 영상인데 메타·화면에 'Public Domain'이라 적혔다(허위 표기).
    라벨은 실제 라이선스에서 나와야 한다."""
    from src.core import pipeline as P
    assert P._credit_with_license("John Turnbull", "cc-by-sa") == "John Turnbull · CC BY-SA"
    assert P._credit_with_license("NOAA Ocean Exploration", "public-domain") \
        == "NOAA Ocean Exploration · Public Domain"
    assert P._credit_with_license("", "cc-by") == "Wikimedia Commons · CC BY"
    # 이미 라이선스가 적힌 크레딧에 중복해 붙이지 않는다
    assert P._credit_with_license("Gary Williams · CC BY-SA", "cc-by-sa") == "Gary Williams · CC BY-SA"


def test_endcard_credit_uses_spec_not_hardcoded_noaa():
    """★실사고: 엔드카드에 'NOAA ・ Public Domain'이 하드코딩돼 커먼스 영상에도 굽혔다(오귀속)."""
    from src.core import hook_intro as hi
    spec = hi.SpeciesSpec(
        jp_name="X", sci_name="X sp.", depth_min=0, depth_max=22,
        hook_line1="a", hook_line2="b", hook_pop_words=["a", "b"], feature_line="f",
        credit_line="John Turnbull · CC BY-SA")
    assert hi._credit_text(spec) == "映像: John Turnbull · CC BY-SA"
    # 크레딧이 비면(주입 실패) 기존 기본 문구로 폴백
    spec.credit_line = ""
    assert hi._credit_text(spec) == hi._DEFAULT_CREDIT


def test_shallow_caption_has_no_deep_sea_wording():
    """얕은 바다 종 캡션에 '深海/深い海/심해'가 남지 않는다."""
    cat = _marine_life_with_subject()
    spec, _hook, _ = cat.hook_intro_spec(_SHALLOW)
    cap = cat.build_reels_caption(_SHALLOW, spec)
    jp, ko = cap.caption_body or "", cap.caption_ko or ""
    assert "深海" not in jp and "深い海" not in jp
    assert "심해" not in ko


def test_deep_sea_caption_keeps_deep_wording():
    """반대로 심해 종 캡션은 기존 심해 서술을 유지한다(회귀 없음)."""
    from src.core import rich_caption as rc
    i = SpeciesInfo("Bathynomus giganteus", "다이오우구소쿠무시", "Giant isopod",
                    "200-2000", "대서양", "심해저", [], [], ["NOAA"])
    out = rc._fallback(i, "ダイオウグソクムシ", "Bathynomus giganteus", "深海の掃除屋",
                       "深海の底に、", "うずくまる影。", "심해 바닥.", "심해의 청소부.",
                       "NOAA · Public Domain", ["#深海"], ["#심해"])
    assert "深い海の底で、たしかに命をつないでいる一種です。" in out["jp"]
