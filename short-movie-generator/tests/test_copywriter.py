"""copywriter 테스트 — 리빌 정책·스포일 가드·훅 루프·폴백."""
import pytest

from src.categories.deep_sea import copywriter
from src.core import llm
from src.registry import get_category


@pytest.fixture
def info():
    return get_category("deep_sea").get_info("dumbo octopus")


@pytest.fixture
def no_llm(monkeypatch):
    """LLM 전면 차단 → 결정적 템플릿 경로 강제."""
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)


def test_spoiler_guard_detects_names(info):
    assert copywriter.has_spoiler("덤보문어가 나타났다", info)
    assert copywriter.has_spoiler("the Dumbo Octopus appears", info)
    assert copywriter.has_spoiler("Grimpoteuthis 발견", info)
    assert copywriter.has_spoiler("덤보가 헤엄친다", info)      # 부분명
    assert not copywriter.has_spoiler("수심 4,000m의 미확인 생물", info)


def test_hook_never_spoils_species(info, no_llm):
    hook = copywriter.best_hook(info)
    assert hook
    assert not copywriter.has_spoiler(hook, info)


def test_cut_beats_follow_reveal_policy(info):
    beats = copywriter.cut_beats(info)
    assert len(beats) == 3
    # 컷1·2: 종명 금지 / 컷3: 종명 공개(리빌)
    assert not copywriter.has_spoiler(beats[0], info)
    assert not copywriter.has_spoiler(beats[1], info)
    assert "덤보문어" in beats[2]


def test_build_caption_data_complete(info, no_llm):
    cap = copywriter.build(info)
    assert cap.hook_text and cap.caption_body
    assert len(cap.cut_beats) == 3
    assert cap.reveal_name.startswith("덤보문어")
    assert cap.reveal_fact
    assert len(cap.hashtags) == 3


def test_hook_judge_loop_picks_candidate(info, monkeypatch):
    """LLM mock: 후보 5개 생성 → 채점기가 3번 선택 → 그 후보가 반환."""
    candidates = "어둠 속 미확인 생물\n수심 4천m의 그림자\n귀로 헤엄치는 정체\n빛 없는 곳의 생명체\n심해가 숨긴 존재"
    calls = {"n": 0}

    def fake_llm(prompt, max_tokens=500):
        calls["n"] += 1
        return candidates if calls["n"] == 1 else "3"

    monkeypatch.setattr(llm, "generate_text", fake_llm)
    monkeypatch.setattr(copywriter.llm, "generate_text", fake_llm)
    assert copywriter.best_hook(info) == "귀로 헤엄치는 정체"


def test_spoiled_candidates_filtered_before_judge(info, monkeypatch):
    """종명이 든 후보는 채점 전에 코드로 제거."""
    def fake_llm(prompt, max_tokens=500):
        if "후보" in prompt and "채점" not in prompt:
            return "덤보문어의 비밀\n수심 4천m의 그림자"
        return "1"

    monkeypatch.setattr(copywriter.llm, "generate_text", fake_llm)
    hook = copywriter.best_hook(info)
    assert not copywriter.has_spoiler(hook, info)
