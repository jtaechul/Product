"""표지(오프닝 훅 · 썸네일) 운영자 지정 — 구간·줌·구획 회귀 테스트.

운영자 확정: "쇼츠 표지도, 오프닝 훅/썸네일도 내가 이미지 구간·줌·구획을 정할 수 있게 해달라."
오프닝 훅 배경 = 썸네일 배경(오프닝 마지막 프레임)이므로 **지정 하나로 둘 다** 정해진다.

지정 형식: {"at": 초, "zoom": 배율(1.0=원본 높이 전체), "x": 가로중심, "y": 세로중심}
"""
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from src.core import hook_intro_stage as his


def test_spec_parsing_and_clamping():
    """형식 해석 + 안전 범위 클램프. 깨진 값은 None → 기존 자동 선택으로 폴백(제작 불정지)."""
    ok = his.parse_cover_spec('{"at":12.3,"zoom":1.6,"x":0.35,"y":0.4}')
    assert ok == {"at": 12.3, "zoom": 1.6, "x": 0.35, "y": 0.4}
    assert his.parse_cover_spec({"at": 5, "zoom": 99, "x": -3, "y": 8}) == {
        "at": 5.0, "zoom": 6.0, "x": 0.0, "y": 1.0}
    for bad in ("", None, "이상한 값", "{}", {"zoom": 2}, [1, 2]):
        assert his.parse_cover_spec(bad) is None, f"깨진 입력을 통과시켰습니다: {bad!r}"


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """왼쪽 위에 표식이 있는 6초 합성 영상(구획 지정이 실제로 반영되는지 확인용)."""
    d = tmp_path_factory.mktemp("cov")
    for i in range(36):
        im = Image.new("RGB", (640, 360), (10, 40, 60))
        dr = ImageDraw.Draw(im)
        dr.rectangle([20, 20, 180, 120], fill=(230, 60, 60))      # 좌상단 표식(빨강)
        dr.rectangle([460, 240, 620, 340], fill=(60, 230, 120))   # 우하단 표식(초록)
        im.save(d / f"f_{i:03d}.png")
    out = d / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "6",
                    "-i", str(d / "f_%03d.png"), "-pix_fmt", "yuv420p", str(out)], check=True)
    return str(out)


def _avg(png: str, box) -> tuple:
    im = Image.open(png).convert("RGB").crop(box)
    px = list(im.getdata())
    n = max(1, len(px))
    return tuple(sum(c[i] for c in px) // n for i in range(3))


def test_cover_uses_the_specified_region(clip, tmp_path):
    """★구획 지정이 실제 결과에 반영된다: 좌상단을 지정하면 빨강, 우하단을 지정하면 초록이 나온다."""
    left = str(tmp_path / "left.png")
    assert his.make_cover_frame(clip, his.parse_cover_spec({"at": 2.0, "zoom": 3.0, "x": 0.16, "y": 0.2}),
                                left, 720, 1280, tmp_path)
    r, g, _b = _avg(left, (200, 400, 520, 900))
    assert r > g + 40, f"좌상단(빨강) 구획이 반영되지 않았습니다: rgb={r},{g}"

    right = str(tmp_path / "right.png")
    assert his.make_cover_frame(clip, his.parse_cover_spec({"at": 2.0, "zoom": 3.0, "x": 0.84, "y": 0.8}),
                                right, 720, 1280, tmp_path)
    r2, g2, _ = _avg(right, (200, 400, 520, 900))
    assert g2 > r2 + 40, f"우하단(초록) 구획이 반영되지 않았습니다: rgb={r2},{g2}"


def test_cover_output_is_9_16(clip, tmp_path):
    out = str(tmp_path / "c.png")
    assert his.make_cover_frame(clip, {"at": 1.0, "zoom": 1.0, "x": 0.5, "y": 0.5}, out, 720, 1280, tmp_path)
    assert Image.open(out).size == (720, 1280)


def test_bad_time_falls_back_without_crashing(clip, tmp_path):
    """영상 밖 시각을 지정하면 실패를 반환해 상위가 자동 선택으로 폴백한다(예외로 죽지 않는다)."""
    out = str(tmp_path / "x.png")
    assert his.make_cover_frame(clip, {"at": 9999.0, "zoom": 1.0, "x": 0.5, "y": 0.5},
                                out, 720, 1280, tmp_path) is False


def test_operator_choice_is_not_overridden_by_the_logo_gate():
    """운영자가 눈으로 보고 고른 표지는 로고 게이트로 되돌리지 않는다(경고만)."""
    src = Path(his.__file__).read_text(encoding="utf-8")
    assert '_label == "운영자 지정 표지"' in src, "운영자 지정이 자동 게이트에 덮어써집니다"
    assert "지정대로 진행합니다" in src


def test_wired_end_to_end():
    """지정값이 대시보드 → 워크플로 → CLI → 제작까지 실제로 전달되는지(배선 계약)."""
    root = Path(his.__file__).parents[2]
    wf = (root.parent / ".github" / "workflows" / "narrate-video.yml").read_text(encoding="utf-8")
    yaml = pytest.importorskip("yaml")
    d = yaml.safe_load(wf)
    inputs = (d.get("on") or d.get(True))["workflow_dispatch"]["inputs"]
    assert "cover" in inputs, "워크플로에 cover 입력이 없습니다"
    assert "--cover" in wf, "워크플로가 --cover 인자를 넘기지 않습니다"
    cli = (root / "src" / "narrate_video.py").read_text(encoding="utf-8")
    assert '"--cover"' in cli and '("cover", a.cover)' in cli, "CLI가 표지 지정을 manual로 넘기지 않습니다"
    na = (root / "src" / "core" / "narrate_attached.py").read_text(encoding="utf-8")
    assert 'parse_cover_spec((manual or {}).get("cover"))' in na, "제작이 표지 지정을 읽지 않습니다"
    assert "cover_spec=cover_spec" in na, "오프닝 훅에 표지 지정이 전달되지 않습니다"
    partial = (root / "src" / "narrate_partial.py").read_text(encoding="utf-8")
    assert "cover" in partial and "make_cover_frame" in partial, "썸네일만 재생성에 표지 지정이 없습니다"
    worker = (root / "worker" / "index.mjs").read_text(encoding="utf-8")
    for token in ("function coverEditorHTML(", "function coverInputs(", "function bindCoverEditor(",
                  "coverEditorHTML()", 'id="cvat"', 'id="cvzoom"', 'id="cvbox"'):
        assert token in worker, f"대시보드 표지 편집기 누락: {token}"
    assert "zoom:Math.round((1/hf)*100)/100" in worker, (
        "줌을 높이 비율로 계산하지 않습니다 — 가로 폭 기준이면 16:9 화면에서 슬라이더가 먹지 않습니다")
