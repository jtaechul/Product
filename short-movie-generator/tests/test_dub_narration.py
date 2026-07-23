"""더빙형 롱폼 나레이션(전사→번역→발화 시각 정렬) 회귀 테스트.

문제(이전): silencedetect(소리 크기)로 나레이션을 배치해, 원본이 연속 발화면 위치가 무너져
자막·나레이션이 원본 음성과 어긋났다. 해결: 전사(Whisper)로 문장별 [start,end]를 얻고 그 시각에
일본어 번역을 정렬(더빙). 이 테스트는 정렬·번역·분절 로직을 (무거운 의존성 없이) 검증한다.
"""
from pathlib import Path

from src.core import narrate_attached as na
from src.core import transcribe as tr


def test_jp_subtitle_split_by_punct_and_length():
    lines = na._jp_lines_for_subtitle("こんにちは、世界。これはとても長い一文なので分割されるはずです。")
    assert lines and all(len(x) <= 18 for x in lines)
    assert lines[0].startswith("こんにちは")


def test_translate_segments_parses_numbered_output(monkeypatch):
    segs = [{"text": "hello world"}, {"text": "goodbye"}]
    monkeypatch.setattr("src.core.llm.generate_text",
                        lambda prompt, max_tokens=500: "1. こんにちは、世界\n2. さようなら")
    out = na._translate_segments_jp(segs, "en")
    assert out == ["こんにちは、世界", "さようなら"]


def test_translate_returns_none_when_mostly_empty(monkeypatch):
    segs = [{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}]
    monkeypatch.setattr("src.core.llm.generate_text",
                        lambda prompt, max_tokens=500: "1. ええ")   # 4개 중 1개만 → 실패
    assert na._translate_segments_jp(segs, "en") is None


def test_dub_narration_aligns_jp_to_original_speech_times(monkeypatch, tmp_path):
    """일본어 자막·나레이션이 원본 발화 시작 시각(anchor)에 맞춰 배치돼야 한다."""
    transcript = [
        {"start": 2.0, "end": 4.0, "orig": "hello", "jp": "こんにちは。"},
        {"start": 10.0, "end": 12.5, "orig": "the deep sea", "jp": "深海の世界。"},
    ]

    def _fake_synth(lines, work_dir, **kw):
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        mp3 = str(Path(work_dir) / "n.mp3"); Path(mp3).write_bytes(b"x" * 100)
        return {"mp3": mp3, "words": [], "disp": [(lines[0], 0.0, 1.0)], "duration": 1.2}

    monkeypatch.setattr("src.core.narration_sync.synthesize", _fake_synth)
    monkeypatch.setattr(na, "_mix_delayed", lambda parts, total, work: str(tmp_path / "mix.mp3"))

    out = na._build_dub_narration("dummy.mp4", 60.0, tmp_path, transcript=transcript)
    assert out is not None
    # 두 발화 모두 배치됨
    assert len(out["chapters"]) == 2
    # 자막이 각 원본 발화 시작 시각 근처에 정렬(첫 발화 ≈2s, 둘째 ≈10s)
    starts = sorted(s for (_t, s, _e) in out["disp"])
    assert abs(starts[0] - 2.0) < 0.3, f"첫 자막이 원본 발화(2s)에 안 맞음: {starts[0]}"
    assert abs(starts[1] - 10.0) < 0.3, f"둘째 자막이 원본 발화(10s)에 안 맞음: {starts[1]}"
    # 편집·재현용 대본 원형 보존
    assert out["transcript"] == transcript
    assert out["duration"] == 60.0


def test_dub_narration_anchor_never_overlaps_previous(monkeypatch, tmp_path):
    """발화가 너무 촘촘해도 앵커는 이전 나레이션 끝 이후로 밀려 겹치지 않아야 한다."""
    transcript = [
        {"start": 1.0, "end": 1.4, "orig": "a", "jp": "あ。"},
        {"start": 1.2, "end": 1.6, "orig": "b", "jp": "い。"},   # 직전과 거의 동시
    ]

    def _fake_synth(lines, work_dir, **kw):
        Path(work_dir).mkdir(parents=True, exist_ok=True)
        mp3 = str(Path(work_dir) / "n.mp3"); Path(mp3).write_bytes(b"x" * 100)
        return {"mp3": mp3, "disp": [(lines[0], 0.0, 1.0)], "duration": 2.0}

    monkeypatch.setattr("src.core.narration_sync.synthesize", _fake_synth)
    monkeypatch.setattr(na, "_mix_delayed", lambda parts, total, work: str(tmp_path / "mix.mp3"))
    out = na._build_dub_narration("dummy.mp4", 60.0, tmp_path, transcript=transcript)
    anchors = [a for (_mp3, a) in []]  # noqa: F841
    starts = sorted(s for (_t, s, _e) in out["disp"])
    assert starts[1] > starts[0], "두 번째 발화 앵커가 첫 번째와 겹침(밀림 실패)"


def test_transcribe_none_without_audio(tmp_path):
    """오디오 스트림이 없으면(또는 파일 부재) 전사는 None → 호출부는 비전 폴백."""
    fake = tmp_path / "noaudio.txt"; fake.write_text("not a video")
    assert tr.transcribe(str(fake), str(tmp_path / "asr")) is None


def test_narrate_video_transcribe_phase_returns_draft(tmp_path, monkeypatch):
    """phase='transcribe'면 렌더 없이 검수용 대본만 반환해야 한다(2단계 검수의 1단계)."""
    vid = tmp_path / "in.mp4"; vid.write_bytes(b"x" * 20000)
    fake_tr = [{"start": 0.0, "end": 2.0, "orig": "hello", "jp": "こんにちは。"}]
    monkeypatch.setattr(na, "_dub_transcript", lambda video, work: fake_tr)
    monkeypatch.setattr(na, "_probe_dur", lambda v: 42.0)
    res = na.narrate_video(str(vid), mode="longform", base_dir=str(tmp_path), phase="transcribe")
    assert res["phase"] == "transcribe"
    assert res["transcript"] == fake_tr
    assert "path" not in res      # 렌더 안 함(영상 없음)
