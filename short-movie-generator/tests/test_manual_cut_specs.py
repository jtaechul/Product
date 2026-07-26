"""컷별 운영자 지정(cut_specs) — 자동 컷 선택을 대체하는지 확인.

운영자 확정 방침: "자동으로 자르지 말고, 컷 구분만 해주고 컷별 구간은 내가 정한다."
따라서 cut_specs가 오면 자동 컷 선택(_plan_scene_interleaved)을 **쓰지 않는다**.

★길이 규칙(운영자 확정 · 회귀 금지): **나레이션 길이는 유지하되, 내가 자른 구간은 정확히 지킨다.**
  · 각 컷은 지정한 start~end 그대로의 길이로 렌더한다(끝점을 늘리지 않는다).
  · 합이 본문보다 짧으면 지정 컷들을 순서대로 **반복**해 채운다(지정 밖 장면은 절대 안 나옴).
  · 합이 본문보다 길면 마지막 컷을 잘라 총 길이를 정확히 맞춘다.
"""
import json

import pytest

from src.core import reframe


def _within(cut, s, e):
    """컷이 지정 구간 [s,e] 안에서만 렌더되는지."""
    return cut["start"] >= s - 1e-6 and cut["start"] + cut["len"] <= e + 1e-6


def test_simple_range_notation():
    """운영자 입력 편의: "0-6, 20-27, 41-48, 62-70" 같은 간단 표기도 받는다."""
    plan = reframe._parse_cut_specs("0-6, 20-27, 41-48, 62-70", src_dur=90.0, target_dur=30.0)
    assert plan is not None
    # 지정 순서대로 시작점이 나온다(합 28s < 본문 30s 라 첫 컷이 한 번 더 반복된다)
    assert [round(c["start"]) for c in plan[:4]] == [0, 20, 41, 62]
    assert sum(c["len"] for c in plan) == pytest.approx(30.0, abs=0.01)


def test_json_notation_with_crop_and_mode():
    raw = json.dumps([{"start": 3, "end": 9, "crop_x": 0.15, "mode": "closeup"},
                      {"start": 20, "end": 30, "mode": "fit"}])
    plan = reframe._parse_cut_specs(raw, src_dur=60.0, target_dur=32.0)
    assert plan[0]["crop_x"] == 0.15 and plan[0]["mode"] == "closeup"
    assert plan[1]["crop_x"] is None and plan[1]["mode"] == "fit"


def test_box_crop_x_y_zoom_kept_per_cut():
    """★손가락으로 그린 사각형: 컷마다 crop_x/crop_y/zoom이 따로 보존돼야 한다."""
    raw = json.dumps([{"start": 0, "end": 5, "crop_x": 0.2, "crop_y": 0.7, "zoom": 1.8},
                      {"start": 10, "end": 15, "crop_x": 0.8, "crop_y": 0.3, "zoom": 1.1}])
    plan = reframe._parse_cut_specs(raw, src_dur=60.0, target_dur=10.0)
    assert (plan[0]["crop_x"], plan[0]["crop_y"], plan[0]["zoom"]) == (0.2, 0.7, 1.8)
    assert (plan[1]["crop_x"], plan[1]["crop_y"], plan[1]["zoom"]) == (0.8, 0.3, 1.1)


def test_exact_windows_kept_not_stretched():
    """★실사고 회귀 방지: 2~8초를 골랐는데 나레이션이 30초면 2~17초가 나갔다.
    이제는 각 컷이 지정 끝점을 넘지 않고, 모자란 길이는 지정 컷 '반복'으로 채운다."""
    plan = reframe._parse_cut_specs("2-8, 12-18", src_dur=60.0, target_dur=30.0)
    assert sum(c["len"] for c in plan) == pytest.approx(30.0, abs=0.01)
    for c in plan:
        assert _within(c, 2.0, 8.0) or _within(c, 12.0, 18.0), c


def test_short_target_trims_last_cut_only():
    """본문이 지정 합보다 짧으면 마지막 컷만 잘라 정확히 맞춘다."""
    plan = reframe._parse_cut_specs("2-8, 12-18", src_dur=60.0, target_dur=9.0)
    assert sum(c["len"] for c in plan) == pytest.approx(9.0, abs=0.01)
    assert plan[0]["len"] == pytest.approx(6.0, abs=0.01)   # 첫 컷은 지정 그대로
    assert plan[-1]["len"] == pytest.approx(3.0, abs=0.01)  # 마지막만 잘림


def test_start_clamped_into_source():
    """소스 끝을 넘는 구간은 소스 안으로 당긴다(렌더가 짧게 잘리지 않게)."""
    plan = reframe._parse_cut_specs("50-60", src_dur=55.0, target_dur=20.0)
    assert all(c["start"] + c["len"] <= 55.0 + 1e-6 for c in plan)


def test_invalid_or_empty_falls_back_to_auto():
    """형식이 깨졌거나 비면 None → 자동 경로로 폴백(제작을 막지 않는다)."""
    for bad in ("", None, "  ", "그냥 아무 말", [], "10-5"):
        assert reframe._parse_cut_specs(bad, src_dur=60.0, target_dur=30.0) is None


def test_too_short_cut_dropped_but_rest_kept():
    plan = reframe._parse_cut_specs("0-0.1, 10-20", src_dur=60.0, target_dur=30.0)
    assert plan and all(_within(c, 10.0, 20.0) for c in plan)
    assert sum(c["len"] for c in plan) == pytest.approx(30.0, abs=0.01)


def test_first_cut_defaults_to_closeup_rest_fit():
    plan = reframe._parse_cut_specs("0-5, 10-15, 20-25", src_dur=60.0, target_dur=30.0)
    assert plan[0]["mode"] == "closeup"
    assert set(c["mode"] for c in plan[1:]) == {"fit"}


def test_roles_assigned_for_motion():
    """역할이 붙어야 컷 안 모션(푸시인 등)이 적용된다."""
    plan = reframe._parse_cut_specs("0-5, 10-15, 20-25, 30-35", src_dur=60.0, target_dur=30.0)
    assert all(c.get("role") for c in plan)
    assert all(c.get("push") for c in plan)


def test_start_preserved_when_source_shorter_than_body(caplog):
    """★실사고: 소스(13.6s)가 본문(28s)보다 짧을 때 시작점이 0으로 뭉개졌다.
    운영자가 2초를 골랐는데 0초부터 렌더된 것 — 지정 시작점은 그대로 존중해야 한다.
    (지금은 2~9초를 반복 배치해 본문을 채운다 — 지정 밖 장면은 나오지 않는다.)"""
    plan = reframe._parse_cut_specs("2-9", src_dur=13.6, target_dur=28.03)
    assert all(c["start"] == pytest.approx(2.0) for c in plan)   # 예전엔 0.0으로 뭉개졌다
    assert all(_within(c, 2.0, 9.0) for c in plan)
    assert sum(c["len"] for c in plan) == pytest.approx(28.03, abs=0.05)


def test_out_of_range_cuts_are_logged_not_silent(caplog):
    """소스 밖 구간을 조용히 버리면 운영자가 '반영됐다'고 오해한다 → 반드시 로그로 알린다."""
    import logging
    with caplog.at_level(logging.WARNING, logger="src.core.reframe"):
        plan = reframe._parse_cut_specs("2-9, 20-27, 40-50", src_dur=13.6, target_dur=28.03)
    assert all(_within(c, 2.0, 9.0) for c in plan)   # 살아남은 구간만 쓴다
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "소스 길이" in msg and "제외" in msg


def test_still_clamps_when_cut_fits_in_source():
    """컷이 소스 안에 들어가는 정상 경우에는 기존대로 끝 넘침을 막는다."""
    plan = reframe._parse_cut_specs("50-60", src_dur=55.0, target_dur=8.0)
    assert all(c["start"] + c["len"] <= 55.0 + 1e-6 for c in plan)
