"""discovery 소싱 수확 회귀 테스트(네트워크 불필요): 육상 포유류 배제 + 'sea pig' 보존 +
속(genus) 사실 폴백 존재 + 검색어 확장."""
from src.core import discovery as D


def test_land_mammals_excluded_but_sea_pig_kept():
    # 진짜 돼지(Sus scrofa)·소·개 등은 배제
    for t in ["Sus scrofa wild boar", "domestic pig Sus scrofa domesticus",
              "a herd of cattle", "豚の生態", "canine on the beach"]:
        assert D._EXCLUDE.search(t), f"차단돼야: {t}"
    # 'sea pig'(Scotoplanes=심해 해삼)와 해양어는 통과(오배제 금지)
    for t in ["sea pig Scotoplanes holothurian", "Scotoplanes globosa",
              "catfish on the reef", "spiny dogfish shark", "rattail grenadier fish",
              "seahorse", "cowfish boxfish"]:
        assert not D._EXCLUDE.search(t), f"통과돼야: {t}"


def test_genus_fact_fallback_exists():
    # 종 위키백과가 없을 때 상위 분류군으로 사실을 보충하는 폴백이 있어야 한다.
    assert hasattr(D, "_facts_with_fallback")


def test_deep_sea_terms_broadened():
    # 소싱 폭 확대(검색어 대량 추가) — 회귀로 축소되지 않게 하한 확인.
    assert len(D._TERMS_DEEP) >= 40
