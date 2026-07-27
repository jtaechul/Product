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


def _backend_crop(src_w: int, src_h: int, zoom: float, cx: float, cy: float):
    """reframe의 운영자 지정 줌 경로와 **같은 식**(src/core/reframe.py 참조)."""
    cw = int(round((src_h * OUT_W / OUT_H) / zoom)) & ~1
    ch = int(round(src_h / zoom)) & ~1
    cw = min(cw, src_w) & ~1
    x = int(min(max(cx * src_w - cw / 2, 0), src_w - cw))
    y = int(min(max(cy * src_h - ch / 2, 0), src_h - ch))
    return x, y, cw, ch


def test_backend_formula_matches_reframe_source():
    """위 계산식이 실제 제작 코드와 같은지(코드가 바뀌면 이 테스트부터 깨지게)."""
    rf = (ROOT / "src" / "core" / "reframe.py").read_text(encoding="utf-8")
    assert "cw = int(round((src_h * W / H) / z)) & ~1" in rf
    assert "ch = int(round(src_h / z)) & ~1" in rf
    assert "cx = int(min(max(fx * src_w - cw / 2, 0), src_w - cw))" in rf
    assert "cy = int(min(max(fy * src_h - ch / 2, 0), src_h - ch))" in rf


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
        bx, by, bw, bh = _backend_crop(src_w, src_h, s["zoom"], s["crop_x"], s["crop_y"])
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
    for c in data["cases"]:
        d = c["drawn"]
        assert abs(d["w"] / d["h"] - 9 / 16) < 0.02, f"9:16이 아닙니다: {d}"
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
    seg = w[i:i + 900]
    assert "bh=hf*H" in seg and "bh*9/16" in seg, "컷 사각형이 높이 기준 9:16이 아닙니다"
    assert "box.w" not in seg, "폭 기준 계산이 남아 있습니다(사고 재발)"
    j = w.index("function cutEditorInputs(")
    seg2 = w[j:j + 700]
    assert "1/hf" in seg2, "줌을 높이 비율의 역수로 보내지 않습니다"


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
