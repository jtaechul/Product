"""컷별 운영자 지정(cut_specs) — 자동 컷 선택을 대체하는지 확인.

운영자 확정 방침: "자동으로 자르지 말고, 컷 구분만 해주고 컷별 구간은 내가 정한다."
따라서 cut_specs가 오면 자동 컷 선택(_plan_scene_interleaved)을 **쓰지 않는다**.
"""
import json

import pytest

from src.core import reframe


def test_simple_range_notation():
    """운영자 입력 편의: "0-6, 20-27, 41-48, 62-70" 같은 간단 표기도 받는다."""
    plan = reframe._parse_cut_specs("0-6, 20-27, 41-48, 62-70", src_dur=90.0, target_dur=30.0)
    assert plan is not None and len(plan) == 4
    assert [round(c["start"]) for c in plan] == [0, 20, 41, 62]
    assert sum(c["len"] for c in plan) == pytest.approx(30.0, abs=0.01)


def test_json_notation_with_crop_and_mode():
    raw = json.dumps([{"start": 3, "end": 9, "crop_x": 0.15, "mode": "closeup"},
                      {"start": 20, "end": 30, "mode": "fit"}])
    plan = reframe._parse_cut_specs(raw, src_dur=60.0, target_dur=32.0)
    assert len(plan) == 2
    assert plan[0]["crop_x"] == 0.15 and plan[0]["mode"] == "closeup"
    assert plan[1]["crop_x"] is None and plan[1]["mode"] == "fit"


def test_lengths_normalized_to_target_by_ratio():
    """지정 구간의 '비율'대로 본문 길이를 배분한다(총 길이 규격 유지)."""
    plan = reframe._parse_cut_specs("0-10, 20-30, 40-60", src_dur=100.0, target_dur=30.0)
    lens = [c["len"] for c in plan]
    assert sum(lens) == pytest.approx(30.0, abs=0.01)
    assert lens[2] == pytest.approx(lens[0] * 2, rel=0.02)   # 20초 구간 = 10초 구간의 2배


def test_start_clamped_into_source():
    """소스 끝을 넘는 구간은 소스 안으로 당긴다(렌더가 짧게 잘리지 않게)."""
    plan = reframe._parse_cut_specs("50-60", src_dur=55.0, target_dur=20.0)
    assert plan[0]["start"] + plan[0]["len"] <= 55.0 + 1e-6


def test_invalid_or_empty_falls_back_to_auto():
    """형식이 깨졌거나 비면 None → 자동 경로로 폴백(제작을 막지 않는다)."""
    for bad in ("", None, "  ", "그냥 아무 말", [], "10-5"):
        assert reframe._parse_cut_specs(bad, src_dur=60.0, target_dur=30.0) is None


def test_too_short_cut_dropped_but_rest_kept():
    plan = reframe._parse_cut_specs("0-0.1, 10-20", src_dur=60.0, target_dur=30.0)
    assert len(plan) == 1 and round(plan[0]["start"]) == 10


def test_first_cut_defaults_to_closeup_rest_fit():
    plan = reframe._parse_cut_specs("0-5, 10-15, 20-25", src_dur=60.0, target_dur=30.0)
    assert plan[0]["mode"] == "closeup"
    assert [c["mode"] for c in plan[1:]] == ["fit", "fit"]


def test_roles_assigned_for_motion():
    """역할이 붙어야 컷 안 모션(푸시인 등)이 적용된다."""
    plan = reframe._parse_cut_specs("0-5, 10-15, 20-25, 30-35", src_dur=60.0, target_dur=30.0)
    assert all(c.get("role") for c in plan)
    assert all(c.get("push") for c in plan)
