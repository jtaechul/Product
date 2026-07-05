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
    "utterly still and motionless",  # 정적 물 (기포 대신 긍정 서술로 모션공백 채움)
    "settling gently downward",      # 마린스노우는 아래로 가라앉음
    "no letterbox",            # 세로 풀프레임(레터박스 금지)
    "no light shafts from above",  # 태양광/광선 금지
    "lamps on the vehicle right beside the camera",  # 조명=카메라 옆(핀조명 아님)
    "underexposed and very dark",  # 심해 저노출(어둡게)
    "nothing overhead is lit",  # 위에서 비추는 핀조명 금지
    "backscatter",             # 후방산란 (수중 실사 단서)
    "shadows fall away from the camera",  # 조명=카메라 동축 (방향 일치)
    "unmanned robotic vehicle",  # 무인 탐사정(호흡 없음) 시점
])
def test_every_cut_contains_hard_rule(cuts, needle):
    for c in cuts:
        assert needle in c["prompt"], f"{c['cut_type']} 프롬프트에 '{needle}' 누락"


@pytest.mark.parametrize("forbidden", ["beam", "laser", "bubble", "breath"])
def test_no_hallucination_trigger_substrings(cuts, forbidden):
    """핀조명(beam)·레이저·기포 유발어(bubble/breath)가 어떤 컷에도 없어야 함.

    핑크코끼리 역효과: 부정문이라도 유발 명사를 쓰면 확산모델이 그린다 → 단어 자체를 배제.
    """
    for c in cuts:
        assert forbidden not in c["prompt"].lower(), f"{c['cut_type']}에 '{forbidden}' 잔존"


def test_no_standalone_air_word(cuts):
    """'air' 단어(공기)도 배제 — 단, hair/pair 등 오탐 없이 단어 경계로만 검사."""
    import re
    for c in cuts:
        assert not re.search(r"\bair\b", c["prompt"], re.IGNORECASE), f"{c['cut_type']}에 'air' 잔존"


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


def test_stillness_rule_present_even_if_bioluminescent(monkeypatch):
    """발광 종이어도 '정적 물' 긍정 서술(기포 방지)은 유지돼야 함(스타일 블록 종 무관 고정)."""
    entry = dict(data.SPECIES["dumbo octopus"])
    entry["accuracy_flags"] = {**entry["accuracy_flags"], "bioluminescent": True}
    for c in prompts.build_cuts(entry):
        assert "utterly still and motionless" in c["prompt"]
        assert "bubble" not in c["prompt"].lower()
