"""쇼츠 나레이션 대본의 '근거' 우선순위 — 운영자 확정 규칙 회귀 테스트.

운영자 확정: ①원본 음성 전사 → ②출처 페이지 설명 → ③(최후수단)화면 분석.
그리고 근거가 화면 분석뿐이면 "최대한 무난하게" 쓴다(종·행동·수치 단정 금지).

※모킹 주의: `from src.core import transcribe as _tr` 는 **패키지 속성**을 읽으므로
  sys.modules 를 갈아끼워도 소용없다(다른 테스트가 먼저 import 하면 실패). 함수 자체를
  monkeypatch.setattr 로 바꾼다 — 실행 순서와 무관하게 동작한다.
"""
import pytest

from src.core import llm, narrate_attached as na, transcribe as tr_mod


# ── 음성 전사 근거 ────────────────────────────────────────────────────────────
def _fake_transcribe(monkeypatch, result):
    monkeypatch.setattr(tr_mod, "transcribe", lambda video, work: result)


def test_speech_notes_joins_segments(monkeypatch, tmp_path):
    _fake_transcribe(monkeypatch, {"lang": "en", "segments": [
        {"start": 0, "end": 3, "text": "These waters hide something remarkable."},
        {"start": 3, "end": 7, "text": "Scientists have watched them for years."}]})
    out = na._speech_notes("x.mp4", tmp_path)
    assert "remarkable" in out and "Scientists" in out
    assert "\n" not in out          # 한 줄로 정규화


def test_speech_notes_empty_when_no_transcript(monkeypatch, tmp_path):
    _fake_transcribe(monkeypatch, None)
    assert na._speech_notes("x.mp4", tmp_path) == ""


def test_speech_notes_rejects_too_short(monkeypatch, tmp_path):
    """인사말 한두 마디만 잡히면 근거로 쓰지 않는다(다음 근거로 넘어가게)."""
    _fake_transcribe(monkeypatch, {"lang": "en",
                                   "segments": [{"start": 0, "end": 1, "text": "Hi there."}]})
    assert na._speech_notes("x.mp4", tmp_path) == ""


def test_speech_notes_survives_transcriber_crash(monkeypatch, tmp_path):
    """전사기가 죽어도 제작을 막지 않는다(다음 근거로 폴백)."""
    def _boom(video, work):
        raise RuntimeError("faster-whisper 폭발")
    monkeypatch.setattr(tr_mod, "transcribe", _boom)
    assert na._speech_notes("x.mp4", tmp_path) == ""


def test_speech_notes_truncates_long_transcript(monkeypatch, tmp_path):
    """긴 해설은 잘라서 넘긴다(프롬프트 폭주 방지)."""
    _fake_transcribe(monkeypatch, {"lang": "en", "segments": [
        {"start": 0, "end": 1, "text": "word " * 2000}]})
    assert len(na._speech_notes("x.mp4", tmp_path)) <= 2400


# ── '무난 모드' 프롬프트 ──────────────────────────────────────────────────────
def _captured_prompt(monkeypatch, **kw):
    seen = {}

    def _gen(prompt, max_tokens=0):
        seen["p"] = prompt
        return "海の底に、\nしずかな時間が流れます。\nその奥へ、進みます。"
    monkeypatch.setattr(llm, "generate_text", _gen)
    na._jp_script("", "메모", "shorts", **kw)
    return seen["p"]


def test_conservative_mode_forbids_assertions(monkeypatch):
    """★화면 분석만으로 쓸 때는 종·생태·수치 단정을 금지하는 지시가 들어가야 한다."""
    p = _captured_prompt(monkeypatch, conservative=True)
    assert "断定しないでください" in p
    assert "種名" in p


def test_normal_mode_has_no_conservative_clause(monkeypatch):
    """음성·출처 근거가 있으면 불필요한 제약을 걸지 않는다(내용이 얕아지지 않게)."""
    p = _captured_prompt(monkeypatch, conservative=False)
    assert "断定しないでください" not in p


def test_fabrication_ban_always_present(monkeypatch):
    """어느 모드든 '사실 창작 금지'는 항상 걸려 있어야 한다(하드룰)."""
    for c in (True, False):
        assert "事実の創作は禁止" in _captured_prompt(monkeypatch, conservative=c)
