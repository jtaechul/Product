"""첨부 영상 나레이션 — 오케스트레이션 E2E(실제 ffmpeg 체인, TTS만 모의)."""
import subprocess
from pathlib import Path
import pytest
from src.core import narrate_attached as N


def test_jp_chunks_fallback():
    """LLM 없이 제목·설명을 자막 청크로 분절(날조 없이 준 텍스트만)."""
    ch = N._jp_chunks_from_notes("深海の沈没船", "潜水艦の残骸です。水深およそ100メートル。", 18)
    assert ch and all(len(c) <= 24 for c in ch)
    assert N._jp_chunks_from_notes("", "") == []


def _fake_tts(work):
    Path(work).mkdir(parents=True, exist_ok=True)
    mp3 = str(Path(work) / "narration.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "anullsrc=r=44100:cl=mono", "-t", "5", "-q:a", "9", mp3], check=True)
    disp = [("深海の", 0.2, 1.4), ("沈没船です。", 1.6, 3.2), ("水深百m。", 3.4, 4.8)]
    return {"mp3": mp3, "words": [("x", 0.2, 4.6)], "disp": disp, "duration": 4.8}


@pytest.mark.parametrize("mode,w,h", [("shorts", 720, 1280), ("longform", 1920, 1080)])
def test_narrate_attached_e2e(tmp_path, monkeypatch, mode, w, h):
    # 합성 가로 소스 영상(8s)
    vid = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=1280x720:rate=30:duration=8", "-pix_fmt", "yuv420p", str(vid)], check=True)
    from src.core import narration_sync, llm
    monkeypatch.setattr(narration_sync, "synthesize", lambda chunks, work, **k: _fake_tts(work))
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)   # 결정론 폴백 강제
    res = N.narrate_video(str(vid), mode=mode, title="深海の沈没船",
                          notes="潜水艦の残骸です。水深百m。", base_dir=str(tmp_path))
    out = Path(res["path"])
    assert out.exists() and out.stat().st_size > 20_000
    ww = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                         "stream=width,height", "-of", "csv=p=0:s=x", str(out)],
                        capture_output=True, text=True).stdout.strip()
    assert ww == f"{w}x{h}"
    # 오디오 트랙 존재(나레이션 mux)
    a = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=codec_type", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout
    assert "audio" in a
