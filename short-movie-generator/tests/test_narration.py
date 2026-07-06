"""narrated_wildlife 전환 — script/tts/subtitle 모듈 검증 (키 없이 결정적 경로)."""
import subprocess

from src.categories.deep_sea import script
from src.core import subtitle, tts
from src.core.contracts import SpeciesInfo


def _info():
    return SpeciesInfo(
        scientific_name="Grimpoteuthis spp.", common_name_ko="덤보문어",
        common_name_en="Dumbo octopus", depth_range_m="1000-4000",
        distribution="전 세계 심해", habitat="심해 저층", diet=["갑각류"],
        fun_facts=["귀처럼 생긴 지느러미로 헤엄친다", "수심 4000m 이상에서도 산다", "먹물주머니가 없다"],
        sources=["NOAA"],
    )


def test_script_fallback_structure(monkeypatch):
    """LLM 불가 시에도 5~6문장·유효 톤·실제 사실 기반 대본."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    lines = script.build_script(_info(), behavior="귀 같은 지느러미를 펄럭인다")
    assert 4 <= len(lines) <= 7
    assert all(l["text"] for l in lines)
    assert all(l["tone"] in script.TONES for l in lines)
    # 첫 문장=역설/결핍 훅(신비 계열), 마지막=철학적 마무리(마무리 계열)
    assert lines[0]["tone"] in ("mysterious", "gravelly", "tense", "whispered", "whispering")
    assert lines[-1]["tone"] in ("final", "reverent", "awe", "thoughtful")


def test_script_parse_numbered_tone_lines():
    raw = "1. [gravelly] 어둠 속에서.\n2. [whispered] 귀를 펄럭인다.\n3. [reverent] 생명은 버틴다."
    lines = script._parse(raw)
    assert [l["tone"] for l in lines] == ["gravelly", "whispered", "reverent"]
    assert lines[1]["text"] == "귀를 펄럭인다."


def test_tts_no_key_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    audio, timings = tts.synthesize([{"text": "안녕", "tone": "slow"}], str(tmp_path))
    assert audio is None and timings == []


def test_word_timings_partition():
    """문장 구간이 어절 글자수 비례로 분배되고 경계가 이어진다."""
    st = [{"text": "가나 다라마 바", "tone": "slow", "start": 0.0, "end": 6.0}]
    ws = subtitle.word_timings(st)
    assert [w["word"] for w in ws] == ["가나", "다라마", "바"]
    assert ws[0]["start"] == 0.0
    assert abs(ws[-1]["end"] - 6.0) < 0.01
    # 이어짐(겹침·공백 없음)
    for a, b in zip(ws, ws[1:]):
        assert abs(a["end"] - b["start"]) < 0.01


def test_karaoke_ass_sentence_level(tmp_path):
    """문장 단위 카라오케: 문장당 Dialogue 1개 + 단어별 \\kf 하이라이트."""
    st = [{"text": "이 심연엔 상식이 무너진다", "tone": "gravelly", "start": 0.0, "end": 3.0},
          {"text": "그런데 버틴다", "tone": "awe", "start": 3.3, "end": 5.0}]
    ass = subtitle.build_karaoke_ass(st, str(tmp_path / "k.ass"))
    txt = open(ass, encoding="utf-8").read()
    assert txt.count("Dialogue:") == 2          # 문장당 1개(단어별 아님)
    assert "\\kf" in txt and "Kara" in txt      # 카라오케 하이라이트
    base = tmp_path / "b.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=720x1280:d=5:r=25", "-pix_fmt", "yuv420p", str(base)],
                   check=True)
    out = subtitle.burn(str(base), ass, str(tmp_path))
    from pathlib import Path
    assert Path(out).exists()


def test_build_ass_and_burn(tmp_path):
    """ASS 마크업 생성 + 더미 영상에 번인(ffmpeg만 필요)."""
    ws = subtitle.word_timings([{"text": "어둠 속 심해", "tone": "slow", "start": 0.0, "end": 3.0}])
    ass = subtitle.build_ass(ws, str(tmp_path / "s.ass"))
    txt = open(ass, encoding="utf-8").read()
    assert "[Events]" in txt and "Dialogue:" in txt and "Pop" in txt
    base = tmp_path / "b.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=720x1280:d=3:r=25", "-pix_fmt", "yuv420p", str(base)],
                   check=True)
    out = subtitle.burn(str(base), ass, str(tmp_path))
    from pathlib import Path
    assert Path(out).exists()
