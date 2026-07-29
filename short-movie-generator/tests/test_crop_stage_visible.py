"""★구획(잘라낼 부분) 설정 화면은 **어떤 경우에도 보여야 한다** (운영자 확정 · 절대 회귀 금지).

실사고(운영자 지적 · IMG_4080): 해양생물 회차 관리자 페이지에서 "영상 구획 설정하는 부분이 아예
보여지지 않는다". 화면엔 '잘라낼 부분' 안내문 바로 밑에 **크기 막대만** 있고 사각형을 그리는 칸이
통째로 없었다.

원인: 그 칸(스테이지)에 높이를 주는 곳이 `ceShowFrame` 하나뿐이었는데, 그 함수는
  `if(!img||!st.sheet) return;`
로 **프레임 사진(시트)이 없으면 즉시 빠져나갔다.** 시트는 '소싱하기'를 돌려야 생기므로,
시트가 없는 회차에서는 `aspect-ratio`가 설정되지 않고 안쪽 `<img>`도 src가 없어
칸 높이가 **0**이 되었다(overflow:hidden이라 사각형도 함께 사라짐).

조치:
  ① 스테이지 HTML이 **스스로 높이**를 갖는다(aspect-ratio + min-height) — 사진이 없어도 안 무너진다.
  ② 시트가 없으면 **재생 중인 원본의 현재 화면을 캔버스로 떠서** 배경으로 쓴다(그림을 보며 지정).
  ③ 그것도 안 되면 격자 배경으로 남되 **사각형은 항상 보이고 드래그된다**.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "worker" / "stage_visible_check.mjs"


def _probe():
    r = subprocess.run(["node", str(CHECK)], capture_output=True, text=True,
                       timeout=120, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    return {c["withSheet"]: c for c in json.loads(r.stdout.strip().splitlines()[-1])}


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_stage_is_visible_even_without_a_frame_sheet():
    """★핵심: 프레임 사진이 없어도 구획 설정 칸이 높이를 갖고 사각형이 그려져야 한다."""
    got = _probe()
    for has_sheet in (True, False):
        c = got[has_sheet]
        label = "프레임 사진 있음" if has_sheet else "프레임 사진 없음"
        assert c["stageHasOwnHeight"], (
            f"{label}: 구획 설정 칸이 스스로 높이를 갖지 않습니다 — 사진이 없으면 높이가 0이 되어 "
            "화면이 통째로 사라집니다(실사고)")
        assert c["boxW"] > 0 and c["boxH"] > 0, f"{label}: 잘라낼 사각형이 그려지지 않았습니다"
        assert c["coverStageTag"], f"{label}: 표지 편집기 칸도 같은 문제를 갖고 있습니다"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_falls_back_to_the_playing_video_frame():
    """프레임 사진이 없으면 **재생 중인 원본 화면**을 떠서 배경으로 쓰고, 비율도 영상에 맞춘다."""
    got = _probe()
    no_sheet = got[False]
    assert no_sheet["stageBgFromVideo"], "시트가 없을 때 재생 화면으로 대체하지 않습니다"
    assert no_sheet["stageAspect"] == "854/480", \
        f"영상 실제 비율로 칸을 맞추지 않았습니다: {no_sheet['stageAspect']}"
    # 시트가 있으면 시트 비율을 그대로 쓴다(기존 동작 유지)
    assert got[True]["stageAspect"] == "480/270"


def test_show_frame_does_not_bail_out_without_a_sheet():
    """소스 계약: `ceShowFrame`이 시트 없다고 그냥 return 하면 안 된다(사고의 직접 원인)."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    i = w.index("function ceShowFrame(")
    seg = w[i:i + 700]
    assert "if(!img||!st.sheet) return;" not in seg, \
        "시트가 없으면 즉시 빠져나가는 옛 코드가 되살아났습니다(구획 화면이 사라집니다)"
    assert "grabStageFrame(" in seg, "시트가 없을 때의 대체 경로가 없습니다"
    j = w.index("function cvShow(")
    seg2 = w[j:j + 700]
    assert "if(!stage||!st.sheet) return;" not in seg2, "표지 편집기도 같은 옛 코드가 남아 있습니다"


def test_stage_markup_carries_its_own_height():
    """HTML 자체가 높이를 갖는지(자바스크립트가 실패해도 칸은 보이게)."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    for anchor in ("'<div id=\"'+pfx+'stage\"", "'<div id=\"cvstage\""):
        i = w.index(anchor)
        seg = w[i:i + 400]
        assert "aspect-ratio:16/9" in seg and "min-height:170px" in seg, \
            f"{anchor} 칸에 기본 높이가 없습니다"
