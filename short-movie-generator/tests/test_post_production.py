"""② 연출 보강 테스트 — 레터박스 자동 제거·그레이딩·리빌 사운드."""
import subprocess

import pytest

from src.core import assembler, audio
from src.core.contracts import ClipResult
from src.core.visualization.base import CLIP_H, CLIP_W


def _make_clip(path, w=720, h=1280, letterbox=0, secs=2):
    """테스트 클립 생성. letterbox>0이면 위아래 검은 띠 픽셀 수."""
    inner_h = h - 2 * letterbox
    vf = f"pad={w}:{h}:0:{letterbox}:black" if letterbox else "null"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", f"color=c=0x224466:size={w}x{inner_h}:duration={secs}:rate=25",
         "-vf", vf, "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )
    return str(path)


def test_letterbox_detected_on_barred_clip(tmp_path):
    clip = _make_clip(tmp_path / "barred.mp4", letterbox=180)
    crop = assembler.detect_letterbox_crop(clip)
    assert crop is not None and crop.startswith("crop=")
    # 감지된 높이는 내부 영상 높이(1280-360=920) 근처여야 함
    h = int(crop.split("=")[1].split(":")[1])
    assert abs(h - 920) <= 24


def test_no_crop_on_fullframe_clip(tmp_path):
    clip = _make_clip(tmp_path / "full.mp4", letterbox=0)
    assert assembler.detect_letterbox_crop(clip) is None


def test_concat_removes_letterbox_without_distortion(tmp_path):
    """레터박스 클립 concat → 출력은 풀프레임 720x1280 (검은 띠 제거)."""
    clip = _make_clip(tmp_path / "barred.mp4", letterbox=180, secs=1)
    out = assembler.concat_clips(
        [ClipResult(clip_path=clip, cut_type="discovery", duration_s=1)], str(tmp_path)
    )
    # 상단 5% 지점 픽셀이 검정이 아니어야 함 (띠 제거 확인)
    probe = subprocess.run(
        ["ffmpeg", "-i", out, "-frames:v", "1",
         "-vf", f"crop=10:10:{CLIP_W//2}:20,signalstats,metadata=print",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    yavg = [l for l in probe.stderr.splitlines() if "YAVG" in l]
    assert yavg and float(yavg[0].split("=")[-1]) > 20, "상단이 여전히 검은 띠"


def test_reveal_accent_produces_audio(tmp_path):
    """리빌 악센트 켜도 오디오 정상 생성 + 무음 아님."""
    clip = _make_clip(tmp_path / "v.mp4", secs=6)
    out = audio.add_ambient(
        clip, str(tmp_path), 6.0,
        {"reveal_accent": True}, reveal_at_s=4.0,
    )
    from src.core.output import _mean_volume_db
    assert _mean_volume_db(out) > -70


def test_accent_skipped_when_reveal_too_early(tmp_path):
    """리빌 시점이 너무 이르면(<3s) 악센트 생략하고 기본 앰비언트."""
    clip = _make_clip(tmp_path / "v.mp4", secs=4)
    out = audio.add_ambient(clip, str(tmp_path), 4.0, {"reveal_accent": True}, reveal_at_s=1.0)
    from src.core.output import _mean_volume_db
    assert _mean_volume_db(out) > -70
