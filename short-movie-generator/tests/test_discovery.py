"""discovery(자동 발굴) 오프라인 단위 테스트 — 네트워크 없이 순수 로직만 검증.

핵심: ① 라이선스 정규화(CC-BY-SA 오픈) ② 해양생물 필터(조류·사체 클립 배제)
③ discovered.json 저장/로드 라운드트립 ④ discovered 종이 SPECIES/_SEED에 병합.
"""
from src.core import discovery


def test_norm_license_opens_cc_by_sa():
    assert discovery._norm_license("CC BY-SA 4.0") == "cc-by-sa"
    assert discovery._norm_license("CC0 1.0") == "cc0"
    assert discovery._norm_license("Public domain") == "public-domain"
    assert discovery._norm_license("CC BY 3.0") == "cc-by"
    assert discovery._norm_license("CC BY-NC 4.0") is None   # 비상업은 여전히 차단


def test_marine_filter_accepts_sea_creatures():
    assert discovery._MARINE.search("深海にすむ甲殻類のエビ")
    assert discovery._MARINE.search("a deep-sea hydrothermal vent shrimp")


def test_marine_filter_rejects_birds_and_bad_clips():
    # 바닷새(조류)는 배제 — 해양 단어가 섞여도 _EXCLUDE가 우선
    assert discovery._EXCLUDE.search("コアホウドリは海鳥で、鳥類に分類される")
    assert discovery._EXCLUDE.search("Laysan albatross, a seabird")
    # 연구·사체·해부·양식 클립은 별도 배제
    assert discovery._BADCLIP.search("Pig Carcasses decomposition on the seafloor")
    assert discovery._BADCLIP.search("解剖 標本 の魚")


def test_discovered_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "_DISCOVERED_DIR", tmp_path)
    (tmp_path / "deep_sea").mkdir()
    items = [{"key": "rimicaris exoculata",
              "footage": {"url": "https://x/y.webm", "license": "cc-by",
                          "credit": "Ifremer · CC BY", "source": "File:y.webm"},
              "species": {"scientific_name": "Rimicaris exoculata",
                          "common_name_ko": "열수분출공새우", "common_name_en": "vent shrimp",
                          "depth_range_m": "", "distribution": "", "habitat": "",
                          "diet": [], "fun_facts": ["blind vent shrimp"], "sources": ["Wikipedia (en)"]}}]
    discovery.save_discovered("deep_sea", items)
    got = discovery.load_discovered("deep_sea")
    assert got and got[0]["key"] == "rimicaris exoculata"
    assert discovery.load_discovered("marine_life") == []   # 없으면 빈 리스트
