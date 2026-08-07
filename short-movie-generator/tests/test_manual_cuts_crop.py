"""컷 전환 제한 + 운영자 수동 지정(구간·크롭·컷수) 회귀 테스트.

운영자 확정 2건:
① "카메라 구도 변경이 너무 어색하니 영상 전환은 쇼츠 회차당 3~4회로 제한" — 예전엔 컷당 2.2초
   고정이라 30초 본문에 14컷이 났다(구도가 쉴 새 없이 바뀜) → 기본 4컷(전환 3회)으로.
② "어느 구간을 쓸지·어디를 crop할지 운영자가 임의로 설정" — `manual` 딕트로 자동 판단을 덮어쓴다.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import reframe


def _ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _dur(p: str) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                 "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip())


def _src(path: Path, seconds: int = 40) -> str:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"testsrc=size=1280x720:rate=30:duration={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)
    return str(path)


def test_cut_count_defaults_to_three_or_four():
    """★핵심: 30초 본문이 예전처럼 10컷 이상으로 쪼개지지 않고 3~4컷으로 유지된다.

    ★기본값 4 → 3(운영자 확정 · 시청자층 실측): 시청자의 71%가 45세 이상(65+ 만 27%)이라
    빠른 구도 전환에서 이탈이 크다 → 컷을 하나 더 줄이고 한 컷을 길게 본다.
    """
    plan = reframe._plan_scene_interleaved.__wrapped__ if hasattr(
        reframe._plan_scene_interleaved, "__wrapped__") else None
    assert reframe._DEFAULT_MAX_CUTS == 3
    assert reframe._MIN_CUTS == 3
    # 역할 배정: 적은 컷에서도 리빌→설정→(디테일)→마무리 서사가 유지되고 접사/핏이 섞인다
    assert [reframe._role_for(k, 3) for k in range(3)] == ["reveal", "establish", "settle"]
    assert [reframe._role_for(k, 4) for k in range(4)] == ["reveal", "establish", "detail", "settle"]


def test_hard_max_cuts_caps_operator_input():
    """운영자가 큰 값을 넣어도 상한(_HARD_MAX_CUTS)을 넘지 않는다(어색함 재발 방지)."""
    assert reframe._HARD_MAX_CUTS <= 8


def test_manual_float_parser():
    """빈칸·공백·문자는 None(=자동), 숫자 문자열은 float."""
    assert reframe._f("") is None and reframe._f(None) is None and reframe._f("  ") is None
    assert reframe._f("auto") is None
    assert reframe._f("12.5") == 12.5 and reframe._f(7) == 7.0


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg 없음")
def test_default_render_is_few_cuts_and_keeps_duration(tmp_path, caplog):
    """실렌더: 기본 호출이 4컷으로 계획되고 목표 길이(30s)는 그대로 보존된다."""
    import logging
    caplog.set_level(logging.INFO, logger="src.core.reframe")
    src = _src(tmp_path / "src.mp4", 40)
    out = reframe.reframe_to_vertical(src, str(tmp_path / "out.mp4"), 30.0, str(tmp_path / "wd"))
    assert Path(out).exists()
    assert abs(_dur(out) - 30.0) < 0.5, "컷 제한 후에도 본문 길이가 보존돼야 함"
    arc = [r.getMessage() for r in caplog.records if "서사 아크" in str(r.msg)]
    assert arc and "4컷" in arc[0], f"기본 4컷이어야 함: {arc}"


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg 없음")
def test_manual_span_crop_and_cuts_applied(tmp_path, caplog):
    """실렌더: 운영자가 지정한 구간·크롭·컷수가 실제로 적용되고 길이는 보존된다."""
    import logging
    caplog.set_level(logging.INFO, logger="src.core.reframe")
    src = _src(tmp_path / "src.mp4", 40)
    out = reframe.reframe_to_vertical(
        src, str(tmp_path / "out.mp4"), 30.0, str(tmp_path / "wd"),
        manual={"start": 10, "end": 25, "crop_x": 0.8, "cuts": 3})
    assert Path(out).exists()
    assert abs(_dur(out) - 30.0) < 0.5
    msgs = [str(r.msg) % r.args if r.args else str(r.msg) for r in caplog.records]
    joined = "\n".join(msgs)
    assert "운영자 지정 구간 적용" in joined
    assert "운영자 지정 크롭 가로위치 고정" in joined
    assert "3컷" in joined, f"운영자 지정 컷수(3)가 반영돼야 함:\n{joined}"


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg 없음")
def test_manual_span_too_short_falls_back_to_auto(tmp_path, caplog):
    """지정 구간이 비정상적으로 짧으면 무시하고 자동으로 진행(발행 불정지)."""
    import logging
    caplog.set_level(logging.INFO, logger="src.core.reframe")
    src = _src(tmp_path / "src.mp4", 20)
    out = reframe.reframe_to_vertical(
        src, str(tmp_path / "out.mp4"), 15.0, str(tmp_path / "wd"),
        manual={"start": 5, "end": 5.2})
    assert Path(out).exists() and abs(_dur(out) - 15.0) < 0.5
    joined = "\n".join(str(r.msg) % r.args if r.args else str(r.msg) for r in caplog.records)
    assert "너무 짧아 무시" in joined
