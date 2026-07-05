"""deep_sea 프롬프트 템플릿 회귀 테스트 — 물리/실사 규칙이 모든 컷에 반드시 포함."""
import pytest

from src.categories.deep_sea import data, prompts
from src.categories.deep_sea.module import DeepSeaCategory
from src.core.contracts import CutSpec, Situation


@pytest.fixture
def cuts():
    return prompts.build_cuts(data.SPECIES["dumbo octopus"])


def test_three_cuts_in_order(cuts):
    assert [c["cut_type"] for c in cuts] == ["discovery", "behavior", "detail"]


@pytest.mark.parametrize("needle", [
    "NO air bubbles",          # 공기 기포 금지 (심해=잠수사 없음)
    "no rising bubbles",
    "never rise",              # 마린스노우는 가라앉음(상승 아님)
    "no letterbox",            # 세로 풀프레임(레터박스 금지)
    "no light shafts from above",  # 태양광/광선 금지
    "lamps on the vehicle right beside the camera",  # 조명=카메라 옆(핀조명 아님)
    "underexposed and very dark",  # 심해 저노출(어둡게)
    "nothing overhead is lit",  # 위에서 비추는 핀조명 금지
    "backscatter",             # 후방산란 (수중 실사 단서)
    "shadows fall away from the camera",  # 조명=카메라 동축 (방향 일치)
])
def test_every_cut_contains_hard_rule(cuts, needle):
    for c in cuts:
        assert needle in c["prompt"], f"{c['cut_type']} 프롬프트에 '{needle}' 누락"


@pytest.mark.parametrize("forbidden", ["beam", "laser"])
def test_no_pinlight_or_laser_vocabulary(cuts, forbidden):
    """핀조명 유발 어휘(beam)·삭제한 레이저 표현이 어떤 컷에도 없어야 함."""
    for c in cuts:
        assert forbidden not in c["prompt"].lower(), f"{c['cut_type']}에 '{forbidden}' 잔존"


def test_species_anatomy_injected(cuts):
    # 종별 형태 잠금이 프롬프트에 주입됐는지 (덤보 = 귀 지느러미)
    assert all("ear-like fins" in c["prompt"] for c in cuts)


def test_habitat_zone_drives_environment(cuts):
    """서식대 데이터가 배경을 결정: 덤보(benthic)=해저 퇴적층, pelagic=흑수 개방수역."""
    # 덤보문어는 benthic → 해저 문구 포함
    assert all("seafloor" in c["prompt"] for c in cuts)
    # 같은 종을 pelagic으로 바꾸면 해저 문구가 빠지고 개방수역 문구로 대체
    entry = dict(data.SPECIES["dumbo octopus"])
    entry["habitat_zone"] = "pelagic"
    for c in prompts.build_cuts(entry):
        assert "open black midwater" in c["prompt"]
        assert "silt" not in c["prompt"]


def test_generated_prompts_pass_accuracy_gate(cuts):
    """템플릿이 스스로 정확성 게이트를 위반하지 않아야 함(diver/human/발광 등 오탐 포함)."""
    sp = data.SPECIES["dumbo octopus"]
    sit = Situation(
        species="dumbo octopus", scientific_name=sp["scientific_name"],
        accuracy_flags=sp["accuracy_flags"], situation_id=sp["situation_id"],
        cuts=[CutSpec(**c) for c in cuts],
    )
    assert DeepSeaCategory().validate_cuts(sit) == []


def test_bubble_rule_present_even_if_bioluminescent(monkeypatch):
    """발광 종이어도 무기포 규칙은 유지돼야 함(스타일 블록은 종 무관 고정)."""
    entry = dict(data.SPECIES["dumbo octopus"])
    entry["accuracy_flags"] = {**entry["accuracy_flags"], "bioluminescent": True}
    for c in prompts.build_cuts(entry):
        assert "NO air bubbles" in c["prompt"]
