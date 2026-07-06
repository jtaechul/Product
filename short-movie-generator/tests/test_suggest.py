"""종 자동 추천 + 중복방지 (LLM 목킹 — 네트워크 없이)."""
import json
import pytest
from src.categories.deep_sea import suggest, data


_FAKE = {
    "scientific_name": "Testus deepus", "common_name_ko": "테스트어",
    "common_name_en": "Test fish", "depth_range_m": "1000-3000",
    "distribution": "전 세계 심해", "habitat": "심해 중층", "diet": ["x"],
    "fun_facts": ["사실1", "사실2", "사실3"], "accuracy_flags": {"bioluminescent": False},
    "appearance": "a small translucent deep-sea fish with a slender body",
    "anatomy_lock": "keep one dorsal fin and a slender tapering body unchanged",
    "forbidden_features": "extra fins, limbs",
    "cut_behaviors": {"discovery": "drifts in the open darkness",
        "behavior": "swims slowly with gentle undulations of its body",
        "detail": "turns toward the camera, then drifts back into the dark"},
    "hud_callouts": [{"slot": "left-mid", "title": "FIN", "sub": "DORSAL"}],
}


@pytest.fixture(autouse=True)
def _clean_ledger(tmp_path, monkeypatch):
    led = tmp_path / "used.json"
    led.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(suggest, "LEDGER", led)
    yield


def test_pick_registers_and_marks_used(monkeypatch):
    monkeypatch.setattr(suggest.llm, "generate_text", lambda *a, **k: json.dumps(_FAKE, ensure_ascii=False))
    key = suggest.pick("nekton")
    assert key == "test fish"
    assert data.SPECIES[key]["habitat_zone"] == "pelagic"  # nekton → pelagic
    assert data.SPECIES[key]["hud_callouts"][0]["slot"] == "left-mid"
    assert suggest.used_count() == 1


def test_banned_words_rejected(monkeypatch):
    bad = dict(_FAKE)
    bad["cut_behaviors"] = {**_FAKE["cut_behaviors"], "behavior": "hunts small prey in the dark"}
    monkeypatch.setattr(suggest.llm, "generate_text", lambda *a, **k: json.dumps(bad, ensure_ascii=False))
    # 금지어 → LLM 반환 무효 → 시드 폴백(dumbo)
    key = suggest.pick("nekton")
    assert key == "dumbo octopus"


def test_llm_unavailable_falls_back_to_seed(monkeypatch):
    monkeypatch.setattr(suggest.llm, "generate_text", lambda *a, **k: None)
    key = suggest.pick("benthos")
    assert key in data.SPECIES  # 시드 폴백


def test_category_rotation_deterministic():
    assert suggest._pick_category("") in suggest.BIOCATEGORIES
    assert suggest._pick_category("plankton") == "plankton"
