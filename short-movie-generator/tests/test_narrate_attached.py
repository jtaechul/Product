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
    # 비전 미가용(키 없음) → 소싱 출처 설명(source_topic)을 대본 근거로 사용
    res = N.narrate_video(str(vid), mode=mode, base_dir=str(tmp_path),
                          source_topic="潜水艦の残骸です。水深百m。")
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
    # 메타데이터(제목·설명·해시태그·훅, 일/한) 자동 생성 — 폴백이라도 채워짐
    meta = res["meta"]
    assert meta["title_jp"] and meta["desc_jp"] and meta["tags_jp"] and meta["hook_jp"]
    assert Path(res["meta_path"]).exists()
    # 오프닝 훅 + 썸네일: 폰트가 있으면 훅이 붙고 썸네일(jpg)이 나온다
    from src.core import hook_intro as hi
    if hi.fonts_available():
        assert res["hooked"] is True
        assert res["thumb"] and Path(res["thumb"]).exists()
        tw = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                             "stream=width,height", "-of", "csv=p=0:s=x", res["thumb"]],
                            capture_output=True, text=True).stdout.strip()
        assert tw == f"{w}x{h}"


def test_gen_metadata_fallback_and_llm(monkeypatch):
    """대본 → 훅·제목·설명·해시태그(일/한). LLM JSON 우선, 실패 시 결정론 폴백."""
    from src.core import llm
    chunks = ["深海に潜む生き物です。", "静かに漂います。", "神秘的な姿です。"]
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: None)     # 폴백
    fb = N._gen_metadata(chunks, "shorts")
    assert fb["title_jp"] and fb["desc_jp"] and fb["tags_jp"] and fb["tags_ko"] and fb["hook_jp"]
    good = ('{"hook_jp":"深海に潜むもの","title_jp":"深海の神秘","title_ko":"심해의 신비",'
            '"desc_jp":"静かな海の記録です。","desc_ko":"고요한 바다의 기록입니다.",'
            '"tags_jp":["#深海","#海"],"tags_ko":["#심해","#바다"]}')
    monkeypatch.setattr(llm, "generate_text", lambda *a, **k: good)
    d = N._gen_metadata(chunks, "shorts")
    assert d["title_ko"] == "심해의 신비" and d["tags_jp"][0] == "#深海"
    assert d["hook_jp"] == "深海に潜むもの"


def test_hook_and_thumb_render(tmp_path):
    """훅/썸네일 렌더 — 배경 프레임 위에 훅 문구를 얹어 카드+썸네일(jpg) 생성."""
    from src.core import hook_intro as hi
    if not hi.fonts_available():
        import pytest as _pt
        _pt.skip("CJK 폰트 없음")
    from PIL import Image
    bg = tmp_path / "bg.jpg"
    Image.new("RGB", (1280, 720), (20, 40, 60)).save(bg)
    card = tmp_path / "card.png"; thumb = tmp_path / "thumb.jpg"
    ok = N._render_hook_and_thumb(str(bg), "深海の未知の光景", "深海生物ドキュメント",
                                  1920, 1080, str(card), str(thumb))
    assert ok and card.exists() and thumb.exists()
    assert Image.open(str(thumb)).size == (1920, 1080)


def test_narrate_requires_content(tmp_path, monkeypatch):
    """비전 불가 + 출처 설명 없음 → 날조 대신 명확히 실패."""
    vid = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc=size=320x240:rate=15:duration=2", "-pix_fmt", "yuv420p", str(vid)], check=True)
    monkeypatch.setattr(N, "_describe_video", lambda *a, **k: "")       # 비전 미가용
    with pytest.raises(ValueError):
        N.narrate_video(str(vid), mode="shorts", base_dir=str(tmp_path), source_topic="")
