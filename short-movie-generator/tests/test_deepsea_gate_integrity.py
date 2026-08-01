"""★심해 인벤토리 무결성 — 부적합 종은 심해에 남아 있으면 안 된다(운영자 확정 · 실사고 run #183).

운영자 지적: "종이 부적합하면 해양 생물 소스로 옮기거나 삭제를 해야 될 거 아냐. 전부 다 확인해서
  수정 조치 완료해."

두 가지를 고정한다:
  ① `deep_sea/discovered.json`의 **모든** 종이 심해 게이트(`deepsea_verify`)를 통과할 것
     (통과 못 하는 종은 marine_life로 옮기거나 삭제한다 — 제작 시점에 터지면 늦다).
  ② 표층종 하드배제는 **대상의 이름에만** 적용할 것.
     실사고: 위키 본문의 계통 설명 "cusk-eels are part of the Percomorpha clade, along with
     **tuna**, perch, seahorses…" 한 줄 때문에 대표적 심해어 Ophidiidae(최대수심 8,370 m)가
     "표층·연안 분류군(tuna)"으로 제작 차단됐다. 본문은 다른 종을 자주 언급하므로 근거가 될 수 없다.
"""
import json
from pathlib import Path

import pytest

from src.core import deepsea_verify as DV

ROOT = Path(__file__).resolve().parents[1]
DS = ROOT / "src" / "categories" / "deep_sea" / "discovered.json"


def _verdict(sp, key):
    sci = sp.get("scientific_name") or key
    corpus = " ".join([" ".join(sp.get("fun_facts") or []), sp.get("habitat", ""),
                       sp.get("distribution", ""), sp.get("depth_range_m", "")])
    v = DV.verdict(sci, sp.get("common_name_en", ""), corpus)
    if not v.ok:                      # 로컬 사실이 빈약하면 위키 서식 문헌으로 재확인(제작 경로와 동일)
        try:
            from src.core import discovery
            ident = discovery._search_taxon_by_name(sci)
            if ident:
                v = DV.verdict(sci, sp.get("common_name_en", ""),
                               corpus + " " + discovery._habitat_corpus(ident))
        except Exception:  # noqa: BLE001
            pass
    return v


@pytest.mark.parametrize("row", json.loads(DS.read_text(encoding="utf-8")),
                         ids=lambda r: str(r.get("key", "?")))
def test_every_deep_sea_subject_passes_the_gate(row):
    """★인벤토리에 있는 종은 **제작 시점에 반드시 통과**해야 한다(부적합은 심해에 두지 않는다)."""
    v = _verdict(row.get("species") or {}, row.get("key", ""))
    assert v.ok, (f"{row.get('key')}: 심해 부적합인데 deep_sea 인벤토리에 있습니다 — {v.reason}. "
                  f"marine_life로 옮기거나 삭제하세요.")


def test_shallow_exclusion_uses_identity_only():
    """★설명 본문의 단순 언급으로 심해 종이 차단되면 안 된다(Ophidiidae/tuna 실사고)."""
    body = ("Cusk-eels are part of the Percomorpha clade, along with tuna, perch, seahorses. "
            "They live at depths of 8370 m.")
    v = DV.verdict("Ophidiidae", "cusk eel", body)
    assert v.ok, f"본문에 다른 물고기가 언급됐다고 심해어가 차단됩니다: {v.reason}"


@pytest.mark.parametrize("sci,en", [
    ("Sardinops sagax", "sardine"),
    ("Sepia officinalis", "common cuttlefish"),
    ("Octopus vulgaris", "common octopus"),
    ("Thunnus albacares", "yellowfin tuna"),
])
def test_real_shallow_species_are_still_blocked(sci, en):
    """게이트가 헐거워지면 안 된다 — 진짜 표층·연안 종은 계속 막혀야 한다."""
    v = DV.verdict(sci, en, "lives in coastal surface waters")
    assert not v.ok, f"{sci}: 표층종인데 통과했습니다"


def test_moved_species_live_in_marine_life():
    """심해에서 뺀 종은 **삭제가 아니라 이동** — 영상이 검증된 실제 해양생물이라 버리지 않는다."""
    ml = json.loads((ROOT / "src" / "categories" / "marine_life"
                     / "discovered.json").read_text(encoding="utf-8"))
    keys = {str(r.get("key", "")).lower() for r in ml}
    for k in ("chimaera", "scyliorhinidae", "myxine glutinosa", "octopus"):
        assert k in keys, f"심해에서 뺀 {k}가 marine_life에도 없습니다(유실)"


# ── 재발 방지: 등록 시점에 카테고리를 가른다 ─────────────────────────────
def test_registration_routes_unsuitable_species_to_marine_life():
    """★부적합은 **등록할 때** 갈라야 한다 — 제작을 눌러야 터지는 건 늦다(실사고 run #183).

    버리지 않고 marine_life로 보낸다: 실제 해양생물이고 영상도 검증됐기 때문이다."""
    from src.core import discovery as D
    deep = {"scientific_name": "Ophidiidae", "common_name_en": "cusk eel", "fun_facts": []}
    shallowish = {"scientific_name": "Chimaera", "common_name_en": "chimaera", "fun_facts": []}
    assert D._category_for_creature("deep_sea", deep) == "deep_sea"
    assert D._category_for_creature("deep_sea", shallowish) == "marine_life"
    # 다른 카테고리는 건드리지 않는다
    assert D._category_for_creature("marine_life", shallowish) == "marine_life"


def test_registration_gate_uses_the_same_judge_as_production():
    """소스 계약: 등록 게이트와 제작 게이트가 **같은 판정 함수**를 써야 어긋나지 않는다."""
    s = (ROOT / "src" / "core" / "discovery.py").read_text(encoding="utf-8")
    i = s.index("def _category_for_creature(")
    body = s[i:i + 1600]
    assert "deepsea_verify" in body and "verdict(" in body, \
        "등록 게이트가 제작과 다른 기준을 쓰고 있습니다"
    assert "_category_for_creature(category_id" in s, "승격 경로가 이 게이트를 호출하지 않습니다"
