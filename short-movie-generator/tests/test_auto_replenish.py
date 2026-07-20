"""★deep_sea auto 풀 소진 자동 보충(실사고 run #134: '제작 가능한 미제작 대상이 없습니다').
시드 풀이 전부 제작돼 후보가 0이면, 소싱된 승인대기 후보 중 적합·제작가능한 첫 종을 자동 승격."""
from src.categories.deep_sea.module import DeepSeaCategory
from src.core.contracts import PipelineError


def test_auto_replenish_promotes_producible_candidate(monkeypatch):
    cat = DeepSeaCategory()
    from src.core import discovery, footage
    from src.categories.deep_sea import catalog, data
    cand_good = {"key": "riftia pachyptila", "kind": "creature",
                 "footage": {"url": "x", "license": "cc0", "credit": "c", "source": "s"},
                 "species": {"scientific_name": "Riftia pachyptila", "common_name_ko": "관벌레",
                             "common_name_en": "giant tube worm", "depth_range_m": "2500",
                             "distribution": "", "habitat": "hydrothermal vents", "diet": [],
                             "fun_facts": ["lives at hydrothermal vents at 2500 m depth"], "sources": []}}
    monkeypatch.setattr(discovery, "load_candidates", lambda cid: [cand_good])
    monkeypatch.setattr(catalog, "_load", lambda: [])                  # 아무것도 제작 안 됨
    promoted = {}
    monkeypatch.setattr(discovery, "promote_candidate",
                        lambda cid, k: promoted.setdefault("key", k) or True)
    monkeypatch.setattr(data, "_merge_discovered", lambda: data.SPECIES.__setitem__(
        "riftia pachyptila", cand_good["species"]))
    monkeypatch.setattr(footage, "_merge_discovered_seeds", lambda: None)
    monkeypatch.setattr(footage, "fetch_footage", lambda sci, en, tmp: {"path": "v.mp4"})
    try:
        key = cat.auto_replenish()
        assert key == "riftia pachyptila" and promoted.get("key") == "riftia pachyptila"
    finally:
        data.SPECIES.pop("riftia pachyptila", None)


def test_auto_replenish_skips_unproducible(monkeypatch):
    cat = DeepSeaCategory()
    from src.core import discovery, footage
    from src.categories.deep_sea import catalog
    cand = {"key": "x", "species": {"scientific_name": "Deep thing", "common_name_en": "x",
            "common_name_ko": "", "depth_range_m": "3000", "distribution": "", "habitat": "abyssal",
            "diet": [], "fun_facts": ["abyssal deep-sea species at 3000 m"], "sources": []}}
    monkeypatch.setattr(discovery, "load_candidates", lambda cid: [cand])
    monkeypatch.setattr(catalog, "_load", lambda: [])
    monkeypatch.setattr(footage, "fetch_footage", lambda *a, **k: None)   # 제작 불가
    called = {}
    monkeypatch.setattr(discovery, "promote_candidate", lambda cid, k: called.setdefault("p", True))
    assert cat.auto_replenish() is None and "p" not in called            # 승격 안 함
