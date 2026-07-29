"""★표지(오프닝 훅) 편집은 **도감형·나레이션형 둘 다** 있어야 한다(운영자 확정 · 절대 회귀 금지).

운영자 지적: "일반 해양생물·심해생물 쇼츠 수정 페이지에서도 오프닝 훅(표지)을 설정할 수 있어야
하는데 여긴 지금 안 들어가 있다."
  · 화면(/c)에 표지 편집기가 아예 없었고,
  · 제작(reels 파이프라인)도 표지 지정(cover)을 받지 않아 화면만 붙여도 반영되지 않는 상태였다.

이 테스트는 **화면 + 배선 + 제작**을 모두 확인한다:
  ① 도감형 상세가 나레이션형과 같은 편집 카드(1 표지 → 2 구간 → 3 실행)를 렌더하는지
  ② 표지와 구간이 한 번에 워크플로 입력으로 나가는지(실제 스크립트를 Node로 실행)
  ③ 워크플로·CLI가 cover를 제작까지 넘기는지
  ④ reels 파이프라인이 그 지정을 오프닝 훅에 실제로 적용하는지
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_reels_detail_renders_the_same_editor_as_narrate():
    """도감형 상세 화면에 표지 편집기·화면 구성·통합 실행 버튼이 모두 있어야 한다."""
    r = subprocess.run(["node", str(ROOT / "worker" / "detail_render_check.mjs")],
                       capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    out = r.stdout
    for line, label in (("1단계 표지 편집기", "표지(오프닝 훅) 편집기"),
                        ("화면 구성 선택", "화면 구성 선택"),
                        ("실행 버튼(통합)", "통합 실행 버튼"),
                        ("크롭 사각형", "구획 사각형")):
        m = re.search(re.escape(line) + r"\s*:\s*(\S+)", out)
        assert m and m.group(1) == "있음", f"도감형 화면에 {label}가 없습니다\n{out}"
    m = re.search(r"둘 다 전달\s*:\s*(\S+)", out)
    assert m and m.group(1) == "정상", f"표지와 구간이 함께 전달되지 않습니다\n{out}"


def test_reels_page_uses_the_shared_studio_card():
    """도감형·나레이션형이 **같은 함수**로 편집 카드를 그린다(기능이 갈라지지 않게)."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "function editStudioHTML(isShorts, rec, pfx)" in w, "편집 카드가 접두사별로 재사용되지 않습니다"
    assert 'editStudioHTML(true, rec, "ce")' in w, "도감형이 공용 편집 카드를 쓰지 않습니다"
    assert "editStudioHTML((rec.mode||\"\")===\"shorts\", rec)" in w, "나레이션형 배선이 깨졌습니다"
    # 도감형에도 표지 편집기 배선이 있어야 한다
    assert 'bindCoverEditor(sheet, "cevid"' in w, "도감형에 표지 편집기 배선이 없습니다"
    assert 'restoreEdits(rec,"ce")' in w, "도감형이 지난 설정을 복원하지 않습니다"
    assert 'allEditInputs("ce")' in w, "도감형이 표지+구간을 함께 보내지 않습니다"


def test_cover_is_wired_from_dashboard_to_production():
    """대시보드 → 워크플로(env) → CLI → 파이프라인까지 표지 지정이 이어져야 한다."""
    wf = (ROOT.parent / ".github" / "workflows" / "generate-short.yml").read_text(encoding="utf-8")
    assert "\n      cover:" in wf, "도감형 워크플로에 cover 입력이 없습니다"
    assert "IN_COVER:" in wf and '--cover "$COVER"' in wf, "cover를 env로 안전하게 넘기지 않습니다"
    cli = (ROOT / "src" / "run_pipeline.py").read_text(encoding="utf-8")
    assert '"--cover"' in cli and '("cover", args.cover)' in cli, "도감형 CLI가 표지를 manual로 넘기지 않습니다"
    pl = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert 'parse_cover_spec(_man.get("cover"))' in pl, "reels 제작이 표지 지정을 읽지 않습니다"
    assert "cover_spec=_cover" in pl, "오프닝 훅에 표지 지정이 전달되지 않습니다"


def test_operator_edit_skips_source_trimming():
    """★시각 기준 통일: 운영자가 구간·표지를 지정하면 소스를 자르지 않는다.

    관리자 화면의 미리보기·프레임 사진은 **자르지 않은 원본**으로 만들어지므로, 제작이 앞부분을
    잘라내면 지정한 초가 그만큼 밀려 엉뚱한 장면이 나간다(나레이션형에서 겪은 사고와 같은 원인)."""
    pl = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert "skip_trim=_op_edit" in pl, "운영자 지정 시 트림을 건너뛰지 않습니다"
    ft = (ROOT / "src" / "core" / "footage.py").read_text(encoding="utf-8")
    assert "skip_trim: bool = False" in ft and "if skip_trim:" in ft, \
        "footage가 트림 건너뛰기를 지원하지 않습니다"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_reels_opening_uses_the_operator_cover(tmp_path):
    """★실제 렌더: 지정한 시각·구획이 오프닝 훅 배경으로 쓰이는지 픽셀로 확인.

    (reels 전체 제작은 무겁고 키가 필요하므로, 실제로 쓰이는 함수인
     hook_intro_stage.make_cover_frame을 같은 인자로 호출해 결과를 본다.)"""
    from PIL import Image, ImageDraw, ImageStat

    from src.core import hook_intro_stage as his
    SW, SH = 1280, 720
    frames = tmp_path / "f"
    frames.mkdir()
    for i in range(48):
        im = Image.new("RGB", (SW, SH), (14, 30, 44))
        dr = ImageDraw.Draw(im)
        # 6초 뒤부터만 왼쪽에 빨간 표식 — '그 시각·그 구획'을 골라야 결과에 나온다
        if i / 6 >= 6.0:
            dr.rectangle([60, 200, 420, 560], fill=(235, 70, 50))
        im.save(frames / f"f_{i:03d}.png")
    src = str(tmp_path / "clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "6",
                    "-i", str(frames / "f_%03d.png"), "-pix_fmt", "yuv420p", src], check=True)

    spec = his.parse_cover_spec(json.dumps({"at": 7.0, "zoom": 1.6, "x": 0.19, "y": 0.5}))
    out = str(tmp_path / "cover.png")
    assert his.make_cover_frame(src, spec, out, 720, 1280, tmp_path / "w"), "표지 프레임 생성 실패"
    r, g, b = ImageStat.Stat(Image.open(out).convert("RGB")).mean
    assert r > g + 40 and r > b + 40, f"지정한 시각·구획이 표지에 반영되지 않았습니다: rgb={r:.0f},{g:.0f},{b:.0f}"
