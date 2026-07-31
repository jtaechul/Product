"""★'확보 영상' 목록 화면 — 확보한 심해생물 소스를 운영자가 **눈으로 확인**할 수 있어야 한다.

운영자 지적: "쇼츠 생성 시작이나 소싱하기 중 뭘 눌러야 28건 확보된 걸 확인할 수 있나?"
  → 둘 다 아니었다(제작 로그에만 찍혔다). 그래서 목록 화면 `/clips`를 만들었다.

핵심 계약: 화면이 읽는 파일 = **제작(파이썬)이 읽는 바로 그 파일**(`src/data/noaa_clips.json`).
  두 곳에 데이터를 복사해 두면 화면과 실제 제작이 조용히 어긋난다 — 한 파일만 쓴다.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "worker" / "clips_page_check.mjs"


def _probe():
    r = subprocess.run(["node", str(CHECK)], capture_output=True, text=True,
                       timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_python_and_dashboard_read_the_same_file():
    """★가장 중요한 계약: 화면에 보이는 것 = 실제 제작이 쓰는 것."""
    from src.data import noaa_clips as NC
    data = json.loads((ROOT / "src" / "data" / "noaa_clips.json").read_text(encoding="utf-8"))
    assert data["clips"] == NC.CLIPS, "파이썬과 JSON이 서로 다른 목록을 들고 있습니다"
    assert data["license"] == NC.LICENSE and data["credit"] == NC.CREDIT


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_page_lists_every_clip():
    got = _probe()
    assert got["fetched"].startswith("/api/pub?path=short-movie-generator/src/data/noaa_clips.json"), \
        f"제작이 읽는 파일이 아닌 다른 곳을 읽습니다: {got['fetched']}"
    assert got["videos"] == got["expected"], \
        f"확보 {got['expected']}건 중 {got['videos']}건만 화면에 나옵니다"
    assert got["headerCount"] == str(got["expected"]), "제목의 건수가 실제와 다릅니다"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_page_shows_license_credit_and_measurements():
    """저작권 표기(허위 표기 금지)와 **실측치**가 함께 보여야 신뢰할 수 있는 목록이다."""
    got = _probe()
    assert got["hasCredit"], "크레딧(NOAA Ocean Exploration) 표기가 없습니다"
    assert got["saysPublicDomain"], "라이선스(퍼블릭도메인) 표기가 없습니다"
    assert got["showsMeasurements"], "실측치(움직임 등)가 보이지 않습니다"
    assert got["linksToSource"] == got["expected"], "출처 원본 페이지 링크가 빠졌습니다"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_previews_go_through_the_media_proxy():
    """미리보기는 워커 프록시 경유 — 브라우저에서 바로 재생되게(교차출처 차단 회피)."""
    got = _probe()
    assert got["proxied"] == got["expected"], "원본 URL을 그대로 써서 재생이 막힐 수 있습니다"


def test_route_and_nav_exist():
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert 'data-p="clips"' in w and 'href="/clips"' in w, "상단 메뉴에 '확보 영상'이 없습니다"
    assert 'renderClips()' in w and 'path.indexOf("/clips")===0' in w, "라우팅이 없습니다"
    assert "src\\/data\\/noaa_clips\\.json" in w, "서버가 이 파일 읽기를 허용하지 않습니다"
