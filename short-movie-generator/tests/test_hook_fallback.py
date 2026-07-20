"""★결정론 훅·본문 폴백(재발방지 실사고 #135 cranchiidae: LLM 파싱 실패로 제작 중단).
LLM 없이도 유효한 일본어 훅·본문을 만들어 제작이 죽지 않게 한다(날조 없음·敬体·언어혼입 없음)."""
import re
from src.core.contracts import SpeciesInfo
from src.categories.deep_sea import hook


def _info():
    return SpeciesInfo(scientific_name="Cranchiidae", common_name_ko="유리오징어",
                       common_name_en="glass squid", depth_range_m="200-3000",
                       distribution="", habitat="심해 중층", diet=[],
                       fun_facts=["transparent deep-sea squid"], sources=[])


def test_fallback_hook_valid_fields():
    h = hook._fallback_hook(_info())
    for k in ("jp_name", "hook_line1", "hook_line2", "pop_words", "feature_line", "feature_glow_word"):
        assert h.get(k), f"필드 없음: {k}"
    assert h["feature_glow_word"] in h["feature_line"]          # 글로우 단어는 feature_line 안에
    assert "3000" in (h["hook_line1"] + h["hook_line2"])         # 실제 수심 반영(날조 아님)


def test_fallback_body_japanese_only_and_polite():
    body = hook._fallback_body_jp(_info())
    assert body and len(body) >= 10
    assert not any(re.search(r"[가-힣]", l) for l in body)       # 국문 혼입 없음(일본어 본문)
    assert any(l.endswith("です。") or l.endswith("ます。") for l in body)   # 敬体
    # 이름 없으면 None(빈 후보 방어)
    empty = SpeciesInfo(scientific_name="", common_name_ko="", common_name_en="",
                        depth_range_m="", distribution="", habitat="", diet=[], fun_facts=[], sources=[])
    assert hook._fallback_body_jp(empty) is None


def test_build_hook_never_none_without_llm(monkeypatch):
    """LLM 미가용(키 없음)이어도 이름 있으면 결정론 폴백으로 dict 반환(절대 None 아님)."""
    from src.core import llm
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)
    h = hook.build_hook(_info())
    assert h and h["jp_name"]
