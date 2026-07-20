"""★재발방지 회귀(실사고: 소싱 승격 생물이 '미등록 대상'으로 제작 실패 · run #131~133).
promote_candidate가 creature를 {key,kind,footage,species}로 쓰는데, collection_base._merge_discovered가
예전엔 subject+copy만 병합해 생물이 SUBJECTS에 안 들어갔다 → parse_input 전부 실패.
이제 species 엔트리도 병합되어 소싱 승격 생물이 제작 대상으로 등록되어야 한다(copy는 선택)."""
from src.categories.collection_base import CollectionCategory
from src.core import discovery as DC


def test_promoted_creature_registers_into_subjects(monkeypatch):
    species = {"scientific_name": "Carcharhinus perezi", "common_name_ko": "카리브암초상어",
               "common_name_en": "Caribbean reef shark", "depth_range_m": "", "distribution": "",
               "habitat": "", "diet": [], "fun_facts": ["a real shark"], "sources": ["Wikipedia"]}
    disc = [{"key": "carcharhinus perezi", "kind": "creature",
             "footage": {"url": "http://x/s.webm", "license": "cc-by-sa", "credit": "C", "source": "S"},
             "species": species}]                     # ★ subject/copy 없음(생물 소싱 스키마)
    monkeypatch.setattr(DC, "load_discovered", lambda cid: disc)

    class _Cat(CollectionCategory):
        category_id = "marine_life"
        SUBJECTS = {"_seed": {"scientific_name": "X", "common_name_ko": "씨앗", "common_name_en": "seed",
                              "depth_range_m": "", "distribution": "", "habitat": "", "diet": [],
                              "fun_facts": [], "sources": []}}
        COPY = {}

    cat = _Cat()
    # 승격 생물이 SUBJECTS에 등록되어 parse_input/get_info가 통과해야 한다(예전엔 '미등록 대상'으로 실패)
    key = cat.parse_input("carcharhinus perezi")
    assert key == "carcharhinus perezi"
    info = cat.get_info(key)
    assert info.scientific_name == "Carcharhinus perezi"
    # 별칭(학명·영문명)으로도 찾아진다
    assert cat.parse_input("Caribbean reef shark") == "carcharhinus perezi"
    # copy가 없어도 등록에는 지장 없음(LLM이 훅·본문 생성)
    assert cat.COPY.get("carcharhinus perezi", {}) == {}
