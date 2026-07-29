"""★표지(오프닝 훅) 편집기에 **그림이 실제로 떠야** 한다 — 두 페이지 모두(운영자 확정·회귀 금지).

실사고(운영자 지적 · IMG_4081): "오프닝 훅 수정 기능이 추가되긴 했는데 보기에서 아무것도 안 보인다."
  사각형·안내문·표지 시각은 나오는데 **그림만 격자 배경**이었다.

원인: 표지 편집기가 화면을 떠올 **영상 요소 id를 "ncvid"로 고정**해 두었다.
  · 나레이션형(/nv)의 영상 id는 `ncvid`라 우연히 동작했고,
  · 도감형(/c)은 `cevid`라 캡처가 조용히 실패해 배경이 비어 있었다.
  (프레임 사진(시트)이 없는 회차는 이 캡처가 **유일한** 그림 공급원이라 곧바로 빈 화면이 된다.)

조치:
  ① 표지 편집기 상태에 **그 페이지의 영상 id**를 저장하고(`cvState().vid`) 그것으로 캡처한다.
  ② 고른 **표지 시각으로 원본을 옮긴 뒤**(seek) 화면을 떠서, 보이는 그림이 실제 표지와 같게 한다.
  ③ 컷 편집기도 같은 방식으로 그 컷의 시작 시각 장면을 보여준다.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "worker" / "cover_stage_check.mjs"


def _probe():
    r = subprocess.run(["node", str(CHECK)], capture_output=True, text=True,
                       timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    return {c["page"]: c for c in json.loads(r.stdout.strip().splitlines()[-1])}


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_cover_stage_shows_a_picture_on_both_pages():
    """★핵심: 프레임 사진이 없어도 표지 편집기에 원본 화면이 떠야 한다(두 페이지 모두)."""
    got = _probe()
    assert len(got) == 2, f"두 페이지를 모두 검사해야 합니다: {list(got)}"
    for name, c in got.items():
        assert c["stateVid"] == c["vidId"], (
            f"{name}: 표지 편집기가 이 페이지의 영상({c['vidId']})이 아니라 "
            f"'{c['stateVid']}'에서 화면을 뜨려 합니다 — 그림이 안 나옵니다")
        assert c["stageBg"], f"{name}: 표지 편집기에 그림이 뜨지 않습니다(격자 배경만 남음)"
        assert c["boxW"] > 0, f"{name}: 잘라낼 사각형이 그려지지 않았습니다"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_cover_stage_shows_the_chosen_moment():
    """고른 표지 시각의 장면을 보여준다(원본을 그 지점으로 옮긴 뒤 캡처) + 비율도 영상 기준."""
    for name, c in _probe().items():
        assert abs(c["seekedTo"] - 12.5) < 0.2, \
            f"{name}: 고른 시각(12.5초)으로 원본을 옮기지 않았습니다: {c['seekedTo']}"
        assert c["stageAspect"] == "854/480", f"{name}: 칸 비율이 영상 실제 비율이 아닙니다"


def test_video_id_is_not_hardcoded():
    """소스 계약: 표지 편집기가 영상 id를 고정값으로 쓰면 안 된다(사고의 직접 원인)."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    i = w.index("function cvShow(")
    seg = w[i:i + 800]
    assert 'grabStageFrame("ncvid"' not in seg, \
        "표지 편집기가 영상 id를 'ncvid'로 고정하고 있습니다(다른 페이지에서 그림이 안 나옵니다)"
    assert "st.vid" in seg, "페이지별 영상 id를 쓰지 않습니다"
    assert 'st.vid=srcVidId' in w, "표지 편집기 배선이 영상 id를 저장하지 않습니다"
    # 고른 시각으로 옮겨서 뜬다(보이는 그림 = 실제 표지)
    assert "function seekAndGrab(" in w, "고른 시각의 장면을 보여주는 경로가 없습니다"
    j = w.index("function ceShowFrame(")
    assert "seekAndGrab(pfx" in w[j:j + 700], "컷 편집기도 그 컷 시각의 장면을 보여야 합니다"
