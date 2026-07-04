"""시각화 인터페이스 계약 테스트 — panzoom 실동작, veo mock/키없음."""
import pytest

from src.core.contracts import ApprovedAsset, CutSpec
from src.core.visualization import get_visualizer
from src.core.visualization.base import CLIP_DURATION_S, CLIP_H, CLIP_W


@pytest.fixture
def approved_img(tmp_path):
    from PIL import Image

    p = tmp_path / "img.jpg"
    Image.new("RGB", (800, 1200), (10, 30, 50)).save(p)
    return ApprovedAsset(asset_path=str(p), license_ok=True, credit_string="c", license="cc0")


def _probe_wh_dur(video):
    import json
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams",
         "-show_format", video],
        capture_output=True, text=True,
    ).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    return v["width"], v["height"], float(data["format"]["duration"])


@pytest.mark.parametrize("cut_type", ["discovery", "behavior", "detail"])
def test_panzoom_produces_9x16_clip(approved_img, tmp_path, cut_type):
    viz = get_visualizer("panzoom")
    clip = viz.generate_clip(
        approved_img, CutSpec(cut_type, "prompt"), "sit1", "deep_sea_realism", str(tmp_path)
    )
    w, h, dur = _probe_wh_dur(clip.clip_path)
    assert (w, h) == (CLIP_W, CLIP_H)
    assert abs(dur - CLIP_DURATION_S) <= 1.0
    assert clip.cut_type == cut_type


def test_veo_without_key_raises(monkeypatch, approved_img, tmp_path):
    from src.core.visualization.base import VisualizationError

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    viz = get_visualizer("veo_img2video")
    with pytest.raises(VisualizationError):
        viz.generate_clip(
            approved_img, CutSpec("discovery", "p"), "s", "deep_sea_realism", str(tmp_path)
        )


def test_unknown_visualizer_raises():
    from src.core.visualization.base import VisualizationError

    with pytest.raises(VisualizationError):
        get_visualizer("nope")
