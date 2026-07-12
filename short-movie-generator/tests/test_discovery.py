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
    # ★파충류(도마뱀붙이) 배제 — 일본어 분류군어까지(회귀: gekko japonicus가 후보로 새던 사고)
    assert discovery._EXCLUDE.search("ニホンヤモリ（Gekko japonicus）は、爬虫綱有鱗目ヤモリ科のトカゲ")
    assert discovery._EXCLUDE.search("a gecko / lizard")
    # 연구·사체·해부·양식 클립은 별도 배제
    assert discovery._BADCLIP.search("Pig Carcasses decomposition on the seafloor")
    assert discovery._BADCLIP.search("解剖 標本 の魚")


def test_marine_filter_keeps_real_sea_creatures():
    """실제 해양생물은 _EXCLUDE에 안 걸린다(아메프라시=바다토끼 오배제 회귀 방지)."""
    assert not discovery._EXCLUDE.search("Aplysia kurodai is a species of sea hare (gastropod)")
    assert not discovery._EXCLUDE.search("ウミグモ綱は鋏角類に属する節足動物")
    assert not discovery._EXCLUDE.search("ニセクロナマコはナマコの一種")


def test_land_spider_excluded_but_sea_spider_kept():
    """육상 거미(검은과부거미)는 배제, 바다거미(Pycnogonida)는 유지 — 실제 오소싱 회귀 방지."""
    land = "Latrodectus tredecimguttatus, the Mediterranean black widow, is one of the widow spiders."
    sea = "Sea spiders are marine arthropods of the class Pycnogonida, also called pycnogonids."
    assert discovery._EXCLUDE.search(land)          # 육상 거미 배제
    assert not discovery._EXCLUDE.search(sea)        # 바다거미는 남긴다


def test_category_catalog_has_distinct_terms():
    """카테고리마다 고유 검색어를 갖는다(과거엔 전부 심해 검색어를 공유 → 엉뚱한 종·중복)."""
    cat = discovery._CATALOG
    assert "marine_algae" in cat and "marine_life" in cat and "deep_sea" in cat
    algae, deep = set(cat["marine_algae"]["terms"]), set(cat["deep_sea"]["terms"])
    assert algae != deep and not (algae & deep)      # 미세조류 검색어는 심해와 완전 분리
    assert any("diatom" in t or "algae" in t or "plankton" in t for t in cat["marine_algae"]["terms"])


def test_algae_gate_positive_and_animal_exclude():
    """미세조류: 조류 양성 확인 + 동물 배제(거미·물고기가 미세조류로 새지 않게)."""
    assert discovery._ALGAE.search("a diatom is a single-celled microalgae (phytoplankton)")
    assert not discovery._ALGAE.search("a widow spider, a venomous arachnid")   # 거미는 조류 아님
    assert discovery._ANIMAL.search("this reef fish and octopus")               # 동물 배제 단서
    # marine_algae 설정은 동물 배제 + 조류 양성 요구
    assert discovery._CATALOG["marine_algae"]["require"] is discovery._ALGAE
    assert discovery._CATALOG["marine_algae"]["exclude"] is discovery._ANIMAL


def test_wreck_name_extraction_loose():
    """침몰선 이름 추출: 강한 접두사 없이도 실제 제목에서 이름을 뽑는다(0건 회귀 방지)."""
    f = discovery._wreck_name_from_title
    assert f("File:Best Wreck dive in Portugal - Madeirense Porto Santo.webm") == "Madeirense"
    assert f("File:Wreck Diving - Black sea Jacques Fraissinet 1-4.webm") == "Jacques Fraissinet"
    assert f("File:Wreck of the SS Thistlegorm.webm").startswith("SS")
    assert f("File:random underwater footage.webm") == ""   # 이름 단서 없으면 빈 문자열


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
