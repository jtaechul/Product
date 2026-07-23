"""롱폼 저작권 음악 자동 제거(+자체 BGM 대체) 회귀 테스트.

실사고: NOAA 편집본의 상용 배경음악이 유튜브 Content ID 클레임을 유발(그 영상 광고수익이
음악 권리자에게). 대책: 전사(원본 오디오) → 보컬 분리로 음악 제거 → 보유 BGM 대체.
여기서는 (demucs 없이 검증 가능한) 폴백·선택·믹스 대체를 검증한다. 실제 분리는 CI 전용.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import music_strip
from src.core import narrate_attached as N


def _ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def test_strip_music_none_without_demucs(tmp_path):
    """demucs 미설치면 None → 호출부는 원본 오디오 그대로(발행 불정지)."""
    if music_strip.available():
        pytest.skip("demucs 설치 환경(CI) — 폴백 테스트는 미설치 환경 전용")
    fake = tmp_path / "v.mp4"; fake.write_bytes(b"x" * 100)
    assert music_strip.strip_music(str(fake), str(tmp_path / "ms")) is None


def test_pick_bgm_deterministic_longform():
    b1 = music_strip.pick_bgm("input.mp4")
    b2 = music_strip.pick_bgm("input.mp4")
    assert b1 == b2 and b1 and "longform_" in Path(b1).name
    assert Path(b1).exists()


def _rms(p: str) -> float:
    r = subprocess.run(["ffmpeg", "-i", p, "-af",
                        "astats=metadata=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
                        "-f", "null", "-"], capture_output=True, text=True)
    vals = [float(l.split("=")[1]) for l in r.stderr.splitlines()
            if "RMS_level=" in l and "-inf" not in l]
    return sum(vals) / len(vals) if vals else -99.0


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg 없음")
def test_mix_replaces_original_audio_and_adds_own_bgm(tmp_path):
    """bg_audio가 오면 영상의 원본(음악) 오디오가 결과에 섞이면 안 되고, bgm은 실제로 들려야 한다."""
    vid = str(tmp_path / "loud.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x180:rate=15:duration=6",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
                    "-map", "0:v", "-map", "1:a", "-pix_fmt", "yuv420p", "-c:a", "aac", vid],
                   check=True)
    quiet = str(tmp_path / "quiet.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo", "-t", "6", quiet], check=True)
    nar = str(tmp_path / "nar.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=stereo", "-t", "6", "-q:a", "9", nar], check=True)
    # 대체: 원본 사인파(시끄러움)가 결과에 없어야 한다
    out = N._mix_bg_narration(vid, nar, 6.0, tmp_path, bg_audio=quiet)
    assert _rms(out) < -50, "원본(음악) 오디오가 대체되지 않음"
    # 자체 BGM 삽입: 소리가 생기고 길이가 보존돼야 한다
    bgm = music_strip.pick_bgm("x")
    out2 = N._mix_bg_narration(vid, nar, 6.0, tmp_path, bg_audio=quiet, bgm=bgm)
    assert _rms(out2) > -60 + 10
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", out2], capture_output=True, text=True).stdout.strip())
    assert abs(d - 6.0) < 0.3
