"""★표지도 화면 구성 3종 + 재생 중 playhead가 끌려다니지 않기(운영자 확정 · 회귀 금지).

운영자 지적 2건:
  ① "왜 표지는 정방형·좌우 전체를 적용할 수 없게 되어 있나 — 표지(오프닝 훅)도 똑같이
     고를 수 있게 해줘." → 본문 컷과 **완전히 같은 3종**(꽉 채우기·정방형·좌우 전체)을 표지에도 준다.
  ② "영상 구간을 편집하다 원본을 재생하면, 다른 버튼을 누르거나 다른 구간으로 옮겨도
     한 구간(0.5초쯤)만 계속 반복 재생된다."
     원인: 영상의 loadeddata/seeked/pause 이벤트에서 **표지 편집기는 '표지 시각'으로,
     컷 편집기는 '컷 시작 시각'으로** 각각 원본을 되돌렸다(seek). 두 편집기가 같은 영상
     요소에 걸려 있어 한쪽의 seek이 seeked를 낳고 그게 다른 쪽 seek을 부르며 **두 시각
     사이를 무한 왕복**했다. → 이벤트에서는 화면만 떠온다(seek 금지).
     실측 A/B(같은 검사기): 예전 코드 30초→**12.5초로 끌려감** / 지금 30초 유지.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "worker" / "edit_playback_check.mjs"


def _probe():
    r = subprocess.run(["node", str(CHECK)], capture_output=True, text=True,
                       timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── ① 표지 화면 구성 ────────────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_cover_editor_offers_the_same_three_frame_modes():
    got = _probe()
    assert got["fitButtons"] == ["cover", "square", "full"], \
        f"표지에 화면 구성 3종이 없습니다: {got['fitButtons']}"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_cover_box_shape_follows_the_chosen_mode():
    """고른 모양이 곧 **잘라낼 사각형의 비율** — 그린 대로 잘린다(WYSIWYG)."""
    got = _probe()
    assert abs(got["cover"]["ar"] - 9 / 16) < 0.01, f"꽉 채우기는 9:16이어야 합니다: {got['cover']}"
    assert abs(got["square"]["ar"] - 1.0) < 0.01, f"정방형은 1:1이어야 합니다: {got['square']}"
    assert abs(got["full"]["ar"] - got["stageAr"]) < 0.01, \
        f"좌우 전체는 원본 비율이어야 합니다: {got['full']} vs {got['stageAr']}"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_cover_mode_is_sent_to_production():
    """고른 모양이 워크플로로 **실제 전달**되어야 한다(화면만 바뀌고 끝나면 의미 없다)."""
    got = _probe()
    assert got["coverInput"].get("fit") in ("cover", "square", "full"), \
        f"표지 값에 화면 구성이 없습니다: {got['coverInput']}"


# ── ② 재생 중 playhead 유지 ─────────────────────────────────────────
@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_playhead_is_not_yanked_back_while_watching():
    """운영자가 30초로 옮겼으면 30초에 있어야 한다 — 표지/컷 시각으로 끌고 오지 않는다."""
    got = _probe()
    assert got["afterSeek"] == 30, \
        f"구간을 옮겼는데 원본이 {got['afterSeek']}초로 끌려갔습니다(무한 반복의 원인)"
    assert got["afterMore"] == 30, \
        f"이벤트가 연달아 와도 유지되어야 합니다: {got['afterMore']}초"


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_marking_a_cut_end_does_not_rewind_playback():
    """'여기 끝'을 눌렀다고 컷 시작 지점으로 되감기면 안 된다(계속 보던 자리를 지킨다)."""
    got = _probe()
    assert got["afterMark"] == 42, f"'여기 끝' 후 재생 위치가 {got['afterMark']}초로 되감겼습니다"


def test_source_contract_no_seek_from_video_events():
    """소스 계약: 영상 이벤트 처리기에서 **되감기 함수를 부르지 않는다**(사고의 직접 원인)."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    for anchor in ('if(_sv&&!sheet)["loadeddata","seeked","pause"]',
                   '["loadeddata","seeked","pause"].forEach(ev=>v.addEventListener'):
        i = w.index(anchor)
        seg = w[i:i + 320]
        assert "cvShow()" not in seg and "ceShowFrame(pfx)" not in seg, \
            f"영상 이벤트에서 원본을 되감고 있습니다(무한 왕복 재발): {seg[:160]}"
        assert "grabStageFrame(" in seg, "이벤트에서는 화면만 떠와야 합니다"


# ── 백엔드: 표지도 컷과 같은 규칙으로 잘리고 배치된다 ───────────────
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_cover_render_keeps_both_edges_in_full_mode(tmp_path):
    """실제 렌더 검증: '좌우 전체'는 원본의 **양쪽 끝이 모두 살아 있어야** 한다."""
    from PIL import Image
    from src.core import hook_intro_stage as his

    src = tmp_path / "src.png"
    im = Image.new("RGB", (1280, 720), (20, 60, 90))
    for x in range(0, 40):
        for y in range(720):
            im.putpixel((x, y), (230, 20, 20))          # 좌 가장자리 = 빨강
    for x in range(1240, 1280):
        for y in range(720):
            im.putpixel((x, y), (20, 230, 20))          # 우 가장자리 = 초록
    im.save(src)

    W, H = 1080, 1920

    def edges(fit):
        out = tmp_path / f"cv_{fit}.png"
        spec = his.parse_cover_spec({"at": 0, "zoom": 1.0, "x": 0.5, "y": 0.5, "fit": fit})
        assert spec["fit"] == fit
        assert his._cover_crop_rect(str(src), str(out), W, H, spec), f"{fit} 표지 렌더 실패"
        o = Image.open(out).convert("RGB")
        assert o.size == (W, H), f"{fit}: 표지 크기가 화면과 다릅니다 {o.size}"
        px = o.load()
        near = lambda c, r: all(abs(a - b) <= 70 for a, b in zip(c, r))  # noqa: E731
        return (near(px[3, H // 2], (230, 20, 20)), near(px[W - 4, H // 2], (20, 230, 20)))

    assert edges("full") == (True, True), "좌우 전체인데 원본의 양쪽 끝이 잘렸습니다"
    assert edges("cover") == (False, False), "꽉 채우기는 좌우를 잘라 화면을 채워야 합니다"
    assert edges("square") == (False, False), "정방형은 가운데 정사각형만 써야 합니다"


def test_cover_spec_parses_and_defaults_the_mode():
    from src.core import hook_intro_stage as his
    assert his.parse_cover_spec({"at": 3, "fit": "square"})["fit"] == "square"
    assert his.parse_cover_spec({"at": 3})["fit"] == "cover", "미지정이면 기존 동작(꽉 채우기)"
    assert his.parse_cover_spec({"at": 3, "fit": "이상한값"})["fit"] == "cover"
