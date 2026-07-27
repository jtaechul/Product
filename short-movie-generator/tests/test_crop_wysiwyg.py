"""★"내가 그린 사각형" == "실제로 잘리는 사각형" (운영자 확정 · 절대 회귀 금지).

실사고(운영자 지적): "잘라낼 곳을 지정한 것과 실제 쇼츠에 제작된 것이 전혀 다르다."
  · 편집기는 사각형을 **가로 폭** 기준으로 그리고 줌을 `1/폭`으로 보냈다.
  · 제작(reframe)은 **높이** 기준으로 자른다 — `잘라낼 높이 = 원본 높이 ÷ 줌`, 너비 = 높이×9/16.
  → 실측(1280x720): 화면에 그린 상자 768x720@x256 vs 실제 크롭 242x430@x519 — 완전히 다른 영역.
     게다가 16:9 화면에선 상자 높이가 항상 화면 전체로 눌려(9:16이 아님) 위아래로 끌어도 보이는
     변화가 없었고, 줌 2.78처럼 상한(2.5)을 넘는 값이 조용히 깎였다.

이 테스트는 대시보드가 **실제로 그리는 상자**(서빙되는 스크립트를 Node로 실행해 얻은 px)와
제작이 계산할 크롭 사각형을 **원본 좌표에서 직접 비교**한다.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT_W, OUT_H = 720, 1280            # 완성본 9:16 (reframe 기본)


def _backend_crop(src_w: int, src_h: int, zoom: float, cx: float, cy: float, fit: str = "cover"):
    """제작이 실제로 쓰는 함수를 그대로 호출한다(같은 식임을 우회 없이 보장)."""
    from src.core import reframe
    return reframe.crop_rect(fit, src_w, src_h, zoom, cx, cy)


def test_fit_modes_have_the_expected_aspect():
    """화면 구성 3종의 사각형 비율: 꽉 채우기 9:16 · 정방형 1:1 · 좌우 전체=원본 비율."""
    from src.core import reframe
    assert abs(reframe.fit_aspect("cover", 1280, 720) - OUT_W / OUT_H) < 1e-6
    assert abs(reframe.fit_aspect("square", 1280, 720) - 1.0) < 1e-6
    assert abs(reframe.fit_aspect("full", 1280, 720) - 1280 / 720) < 1e-6
    assert abs(reframe.fit_aspect("이상한값", 1280, 720) - OUT_W / OUT_H) < 1e-6   # 안전 기본값
    # 좌우 전체 + 줌 1.0 = 원본 그대로(좌우가 하나도 안 잘림)
    x, y, w, h = reframe.crop_rect("full", 1280, 720, 1.0, 0.5, 0.5)
    assert (x, y, w, h) == (0, 0, 1280, 720)


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_drawn_box_equals_rendered_crop():
    """★핵심: 화면에 그려진 상자와 제작이 자를 사각형이 같은 곳이어야 한다(오차 ≤ 4px)."""
    r = subprocess.run(["node", str(ROOT / "worker" / "crop_wysiwyg_check.mjs")],
                       capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-800:]
    data = json.loads(r.stdout.strip().splitlines()[-1])
    src_w, src_h = data["src"]
    assert data["cases"], "검사 케이스가 비었습니다"
    for c in data["cases"]:
        d, s = c["drawn"], c["sent"]
        bx, by, bw, bh = _backend_crop(src_w, src_h, s["zoom"], s["crop_x"], s["crop_y"],
                                       s.get("fit", "cover"))
        for name, drew, cut in (("가로위치", d["x"], bx), ("세로위치", d["y"], by),
                                ("너비", d["w"], bw), ("높이", d["h"], bh)):
            assert abs(drew - cut) <= 4, (
                f"{name}가 다릅니다 — 화면에 그린 상자 {drew:.0f} vs 실제 잘리는 값 {cut} "
                f"(상태 {c['state']}, 보낸 값 {s})")


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_box_is_really_9_16_and_movable():
    """상자가 진짜 9:16이어야 한다(예전엔 화면 높이에 눌려 가로로 퍼진 상자였다)."""
    r = subprocess.run(["node", str(ROOT / "worker" / "crop_wysiwyg_check.mjs")],
                       capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    data = json.loads(r.stdout.strip().splitlines()[-1])
    from src.core import reframe
    for c in data["cases"]:
        d = c["drawn"]
        want = reframe.fit_aspect(c["sent"].get("fit", "cover"), *data["src"])
        assert abs(d["w"] / d["h"] - want) < 0.02, \
            f"{c['sent'].get('fit')} 모드의 사각형 비율이 다릅니다: {d}"
    # 높이를 줄인 케이스는 위아래로도 움직일 수 있어야 한다(y가 0에 붙어 있지 않음)
    moved = [c for c in data["cases"] if c["state"]["h"] < 0.99]
    assert any(c["drawn"]["y"] > 0 for c in moved), "상자가 위아래로 움직이지 않습니다"


def test_editor_never_sends_zoom_beyond_backend_limit():
    """제작은 줌을 1.0~2.5로 자른다 → 편집기가 그 밖의 값을 보내면 조용히 깎인다(실측 2.78→2.5).
    슬라이더 하한을 40%(=줌 2.5)로 두어 애초에 못 보내게 한다."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "const CE_HMIN=0.4;" in w, "줌 상한(2.5)에 맞는 높이 하한이 없습니다"
    i = w.index("function cutEditorHTML(")
    seg = w[i:w.index("async function ceLoadSheet(")]
    assert 'min="40"' in seg, "줌 슬라이더가 백엔드 상한을 넘는 값을 허용합니다"


def test_cut_editor_is_height_based_like_the_cover_editor():
    """표지 편집기는 이미 높이 기준으로 고쳤는데 컷 편집기만 폭 기준으로 남아 사고가 났다."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    i = w.index("function ceDrawBox(")
    seg = w[i:i + 1200]
    assert "bh=hf*H" in seg, "컷 사각형이 높이 기준이 아닙니다"
    assert "bh*ar" in seg, "화면 구성 비율(ar)로 너비를 잡지 않습니다"
    assert "box.w" not in seg, "폭 기준 계산이 남아 있습니다(사고 재발)"
    j = w.index("function cutEditorInputs(")
    seg2 = w[j:j + 800]
    assert "1/hf" in seg2, "줌을 높이 비율의 역수로 보내지 않습니다"


def test_frame_mode_tool_is_wired_everywhere():
    """★운영자 확정: 화면 구성 편집 기능은 **도감형·나레이션형 둘 다** 똑같이 노출·적용된다.

    편집기 HTML은 공용 함수(cutEditorHTML)라 양쪽 화면에 그대로 들어가고, 선택값(fit)이
    워크플로 → CLI → 제작까지 이어져야 실제로 반영된다."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    i = w.index("function cutEditorHTML(")
    seg = w[i:w.index("async function ceLoadSheet(")]
    for token in ("data-fit=", "꽉 채우기", "정방형", "좌우 전체"):
        assert token in seg, f"공용 편집기에 화면 구성 도구가 없습니다: {token}"
    assert 'cutEditorHTML("nc")' in w and 'cutEditorHTML("ce")' in w, \
        "나레이션형·도감형 양쪽에 편집기가 붙어 있지 않습니다"
    j = w.index("function cutEditorInputs(")
    assert "out.fit=st.fit" in w[j:j + 800], "선택한 화면 구성을 제작에 보내지 않습니다"

    root = ROOT.parent / ".github" / "workflows"
    for wf in ("narrate-video.yml", "generate-short.yml"):
        src = (root / wf).read_text(encoding="utf-8")
        assert "\n      fit:" in src, f"{wf}에 fit 입력이 없습니다"
        assert "IN_FIT:" in src, f"{wf}가 fit을 env로 넘기지 않습니다"
    for cli in ("narrate_video.py", "run_pipeline.py"):
        src = (ROOT / "src" / cli).read_text(encoding="utf-8")
        assert "--fit" in src and '"fit"' in src, f"{cli}가 화면 구성을 제작에 전달하지 않습니다"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_full_mode_keeps_both_edges_of_the_source(tmp_path):
    """★'좌우 전체'는 원본 양쪽 끝이 결과에 남아야 한다(꽉 채우기는 잘려야 정상)."""
    from PIL import Image, ImageDraw

    from src.core import reframe
    SW, SH = 1280, 720
    frames = tmp_path / "f"
    frames.mkdir()
    for i in range(36):
        im = Image.new("RGB", (SW, SH), (16, 44, 64))
        dr = ImageDraw.Draw(im)
        dr.rectangle([10, 300, 90, 420], fill=(240, 80, 60))        # 왼쪽 끝
        dr.rectangle([1190, 300, 1270, 420], fill=(80, 230, 140))   # 오른쪽 끝
        dr.ellipse([560 + i * 2, 120, 620 + i * 2, 180], fill=(255, 255, 255))
        im.save(frames / f"f_{i:03d}.png")
    src = str(tmp_path / "clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "6",
                    "-i", str(frames / "f_%03d.png"), "-pix_fmt", "yuv420p", src], check=True)

    def edges(fit):
        out = str(tmp_path / f"o_{fit}.mp4")
        reframe.reframe_to_vertical(src, out, 3.0, str(tmp_path / f"w_{fit}"), wide=True,
                                    manual={"fit": fit, "cut_specs": json.dumps(
                                        [{"start": 0.5, "end": 5.0, "zoom": 1.0,
                                          "crop_x": 0.5, "crop_y": 0.5}])})
        png = str(tmp_path / f"c_{fit}.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.05", "-i", out,
                        "-frames:v", "1", png], check=True)
        im = Image.open(png).convert("RGB")
        w2, h2 = im.size
        seen = {"left": False, "right": False}
        for y in range(0, h2, 6):
            for x in range(0, w2, 6):
                r, g, b = im.getpixel((x, y))
                if r > 170 and g < 140 and b < 120:
                    seen["left"] = True
                if g > 170 and r < 150 and b < 190:
                    seen["right"] = True
        return seen

    full = edges("full")
    assert full["left"] and full["right"], "좌우 전체 모드인데 원본 끝이 잘렸습니다"
    cover = edges("cover")
    assert not (cover["left"] and cover["right"]), "꽉 채우기인데 좌우가 안 잘렸습니다(모드가 안 먹음)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_real_render_crops_exactly_where_the_formula_says(tmp_path):
    """★계산식이 아니라 **실제 렌더 결과**로 확인: 원본에 찍은 점이 결과의 예상 위치에 있는가.

    (그레이딩·푸시인 모션이 색을 바꿔도 '점의 위치'는 기하학이라 흔들리지 않는다.)"""
    from PIL import Image, ImageDraw

    from src.core import reframe
    SW, SH = 1280, 720
    dot = (0.30, 0.35)
    frames = tmp_path / "f"
    frames.mkdir()
    for i in range(36):
        im = Image.new("RGB", (SW, SH), (18, 30, 42))
        dr = ImageDraw.Draw(im)
        dr.ellipse([int(dot[0] * SW) - 14, int(dot[1] * SH) - 14,
                    int(dot[0] * SW) + 14, int(dot[1] * SH) + 14], fill=(255, 255, 255))
        dr.rectangle([0, 700 + (i // 6) % 2, SW, SH], fill=(60, 60, 60))   # 미세 움직임
        im.save(frames / f"f_{i:03d}.png")
    src = str(tmp_path / "clip.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "6",
                    "-i", str(frames / "f_%03d.png"), "-pix_fmt", "yuv420p", src], check=True)

    zoom, cx, cy = 2.22, 0.30, 0.35
    out = str(tmp_path / "o.mp4")
    reframe.reframe_to_vertical(src, out, 3.0, str(tmp_path / "w"), wide=True,
                                manual={"cut_specs": json.dumps(
                                    [{"start": 0.5, "end": 5.0, "zoom": zoom,
                                      "crop_x": cx, "crop_y": cy}])})
    png = str(tmp_path / "c.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.03", "-i", out,
                    "-frames:v", "1", png], check=True)
    im = Image.open(png).convert("L")
    w2, h2 = im.size
    pts = [(x, y) for y in range(0, h2, 2) for x in range(0, w2, 2) if im.getpixel((x, y)) > 200]
    assert pts, "지정한 구획 안의 표식이 결과에 보이지 않습니다(엉뚱한 곳을 잘랐습니다)"
    x0, y0, cw, ch = _backend_crop(SW, SH, zoom, cx, cy)
    px = (sum(p[0] for p in pts) / len(pts)) / w2
    py = (sum(p[1] for p in pts) / len(pts)) / h2
    back = ((x0 + px * cw) / SW, (y0 + py * ch) / SH)      # 결과 좌표 → 원본 좌표 역산
    assert abs(back[0] - dot[0]) < 0.03 and abs(back[1] - dot[1]) < 0.03, \
        f"실제로 잘린 곳이 계산과 다릅니다: 역산 {back} vs 진짜 {dot}"


def test_operator_cuts_use_the_untrimmed_source():
    """★시간 기준도 하나로: 운영자가 고른 초는 **원본 기준**이다.

    제작은 인트로·아웃트로 카드를 잘라낸 사본으로 리프레임하는데, 운영자가 보는 미리보기·사진 띠는
    **자르지 않은 원본**이다. 카드가 잘리는 순간 지정한 초가 그만큼 밀려 다른 장면이 나온다.
    → 운영자가 구간을 지정한 경우엔 자동 카드 트림을 건너뛴다(지정 구간에 카드가 없도록 고른 것)."""
    na = (ROOT / "src" / "core" / "narrate_attached.py").read_text(encoding="utf-8")
    assert "_operator_cut_specs" in na or "cut_specs" in na
    i = na.index("clean = ")
    seg = na[max(0, i - 900):i + 400]
    assert "cut_specs" in seg, "운영자 구간 지정 시 카드 트림을 건너뛰지 않습니다(시간 기준 어긋남)"
