"""원본 화면 정적 라벨 → 딥네이비 박스 + 일본어 오버레이(롱폼) 회귀 테스트."""
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import onscreen_translate as ost


def _ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


# ── 순수 로직 ──
def test_blocks_from_words_merges_nearby_and_filters_lowconf():
    words = [
        {"text": "DEPTH", "conf": 90, "x": 0.05, "y": 0.85, "w": 0.08, "h": 0.04},
        {"text": "1200", "conf": 88, "x": 0.14, "y": 0.85, "w": 0.05, "h": 0.04},   # 근접 → 병합
        {"text": "m", "conf": 80, "x": 0.20, "y": 0.85, "w": 0.02, "h": 0.04},
        {"text": ".", "conf": 95, "x": 0.5, "y": 0.5, "w": 0.01, "h": 0.01},         # 문장부호만 → 제외
        {"text": "xx", "conf": 20, "x": 0.7, "y": 0.2, "w": 0.05, "h": 0.04},        # 저신뢰 → 제외
    ]
    blocks = ost._blocks_from_words(words)
    assert len(blocks) == 1
    assert "DEPTH" in blocks[0]["text"] and "1200" in blocks[0]["text"]
    x, y, w, h = blocks[0]["box"]
    assert w > 0.13                     # 세 단어를 아우르는 폭


def test_ok_label_box_rejects_big_and_central():
    assert ost._ok_label_box((0.05, 0.86, 0.22, 0.06)) is True     # 하단 라벨 OK
    assert ost._ok_label_box((0.0, 0.0, 0.9, 0.5)) is False        # 너무 큼
    assert ost._ok_label_box((0.35, 0.35, 0.3, 0.3)) is False      # 중앙 큰 덩어리(피사체 위험)


def test_iou_basic():
    assert ost._iou((0, 0, 1, 1), (0, 0, 1, 1)) == pytest.approx(1.0)
    assert ost._iou((0, 0, 1, 1), (2, 2, 1, 1)) == 0.0


def test_translate_labels_parses_numbered(monkeypatch):
    monkeypatch.setattr("src.core.llm.generate_text",
                        lambda prompt, max_tokens=500: "1. 水深 1200 m\n2. ミズウオ科")
    out = ost._translate_labels_jp(["DEPTH 1200 m", "Alepisauridae"])
    assert out == ["水深 1200 m", "ミズウオ科"]


def test_apply_returns_original_without_tesseract(monkeypatch, tmp_path):
    monkeypatch.setattr(ost, "_has_tesseract", lambda: False)
    v = str(tmp_path / "in.mp4")
    Path(v).write_bytes(b"x" * 100)
    assert ost.apply(v, str(tmp_path / "out.mp4"), str(tmp_path / "w"), 30.0, 640, 360) == v


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg 없음")
def test_render_event_png_has_navy_box(tmp_path):
    from PIL import Image
    ev = {"box": [0.05, 0.85, 0.25, 0.07], "jp": "水深 1200 m"}
    p = str(tmp_path / "ov.png")
    assert ost._render_event_png(ev, 640, 360, p)
    im = Image.open(p).convert("RGBA")
    # 박스 좌측 안쪽(텍스트 중앙과 겹치지 않는 지점)에 불투명 딥네이비가 있어야 한다
    r, g, b, a = im.getpixel((int(0.07 * 640), int(0.885 * 360)))
    assert a > 200 and r < 45 and g < 55 and b < 75, f"딥네이비 박스 아님: {(r,g,b,a)}"
    # 박스 밖(상단)은 투명해야 한다
    assert im.getpixel((320, 20))[3] == 0


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg 없음")
def test_apply_overlays_box_only_during_event(tmp_path, monkeypatch):
    """오버레이가 이벤트 구간에만 나타나고(딥네이비), 구간 밖 프레임엔 없어야 한다. 길이 보존."""
    W, H = 640, 360
    vid = str(tmp_path / "plain.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"color=c=gray:s={W}x{H}:d=8:r=15", "-pix_fmt", "yuv420p", vid], check=True)
    ev = {"t0": 1.0, "t1": 6.0, "box": [0.05, 0.85, 0.25, 0.07], "text": "DEPTH 1200 m"}
    monkeypatch.setattr(ost, "_has_tesseract", lambda: True)
    monkeypatch.setattr(ost, "detect_static_text_events", lambda *a, **k: [dict(ev)])
    monkeypatch.setattr(ost, "_translate_labels_jp", lambda texts: ["水深 1200 m"])
    out = ost.apply(vid, str(tmp_path / "out.mp4"), str(tmp_path / "w"), 8.0, W, H)
    assert out != vid and Path(out).exists()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip())
    assert abs(dur - 8.0) < 0.6

    def _navy_count(t):
        fp = str(tmp_path / f"g_{t}.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", out,
                        "-frames:v", "1", fp], check=True)
        from PIL import Image
        im = Image.open(fp).convert("RGB")
        x0, y0 = int(0.05 * W), int(0.85 * H)
        x1, y1 = int(0.32 * W), int(0.94 * H)
        n = 0
        for yy in range(y0, y1, 2):
            for xx in range(x0, x1, 2):
                r, g, b = im.getpixel((xx, yy))
                if r < 45 and g < 55 and b < 75:
                    n += 1
        return n

    assert _navy_count(3.0) > 40, "이벤트 구간(3s)에 딥네이비 박스가 없음"
    assert _navy_count(7.2) < 5, "이벤트 구간 밖(7.2s)에 박스가 남아 있음"
