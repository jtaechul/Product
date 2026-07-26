"""쇼츠 나레이션 분배 — 문장 사이 쉼 + 영상 전체 배치 회귀 테스트.

운영자 지적(실사고): "나레이션이 문장과 문장 사이 간격 없이 빠르게만 나와서 어색하다.
영상 뒷부분에는 아무 나레이션이 없다." → 문장을 이어붙여 한 번에 읽히던 방식을 폐기하고,
문장별로 합성해 **영상 끝까지 고르게 배치**한다(쉼은 문장 길이에 비례).
"""
from pathlib import Path

import pytest

from src.core import narrate_attached as na


@pytest.fixture
def fake_tts(monkeypatch, tmp_path):
    """edge-tts 없이 분배 로직만 검사(네트워크 불필요). 문장 길이는 글자 수에 비례."""
    from src.core import narration_sync

    def _synth(chunks, work_dir, voice="x", rate="+0%"):
        txt = chunks[0]
        dur = 0.18 * len(txt)                       # 글자당 0.18초로 가정
        p = Path(work_dir) / "narration.mp3"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"")
        return {"mp3": str(p), "words": [(0.0, dur, txt)],
                "disp": [(txt, 0.0, dur)], "duration": dur}

    monkeypatch.setattr(narration_sync, "synthesize", _synth)
    monkeypatch.setattr(na, "_probe_dur", lambda p: 0.0)        # 단어 기반 길이를 쓰게 한다
    mixed = {}

    def _mix(parts, total, work):
        mixed["parts"], mixed["total"] = parts, total
        out = Path(work) / "narration_full.mp3"
        out.write_bytes(b"")
        return str(out)

    monkeypatch.setattr(na, "_mix_delayed", _mix)
    return mixed


_CHUNKS = ["深い海の底に、静かな影が広がります。",
           "光の届かない世界で、体がゆっくり揺れています。",
           "色を変えているのかもしれません。",
           "深海は、まだ知られていないことばかりです。",
           "静けさの奥に、確かな命が息づいています。"]


def test_sentences_have_pauses_between(fake_tts, tmp_path):
    """★핵심: 문장과 문장 사이에 최소 쉼 이상 간격이 있어야 한다(랩처럼 붙여 읽지 않는다)."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0)
    assert nar and nar.get("spread")
    anchors = [a for _mp3, a in fake_tts["parts"]]
    lens = [0.18 * len(c) for c in _CHUNKS]
    for i in range(len(anchors) - 1):
        gap = anchors[i + 1] - (anchors[i] + lens[i])
        assert gap >= na._SHORTS_GAP_MIN - 1e-6, f"문장 {i+1}→{i+2} 사이 쉼이 없습니다: {gap:.2f}s"
        assert gap <= na._SHORTS_GAP_MAX + 1e-6, f"쉼이 과도합니다(끊긴 느낌): {gap:.2f}s"


def test_narration_reaches_the_end_of_video(fake_tts, tmp_path):
    """★핵심: 뒷부분이 통째로 무음이면 안 된다 — 마지막 문장이 영상 끝 근처에서 끝나야 한다."""
    target = 30.0
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, target)
    anchors = [a for _mp3, a in fake_tts["parts"]]
    end = anchors[-1] + 0.18 * len(_CHUNKS[-1])
    assert end >= target - na._SHORTS_TAIL_S - na._SHORTS_GAP_MAX, (
        f"나레이션이 {end:.1f}s에 끝나 뒤쪽 {target - end:.1f}s가 무음입니다")
    assert end <= target, "나레이션이 영상 끝을 넘었습니다"


def test_first_sentence_not_at_zero_and_tail_kept(fake_tts, tmp_path):
    """첫 문장 전 여유와 마지막 여운(엔딩 감성)이 있어야 한다."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0)
    anchors = [a for _mp3, a in fake_tts["parts"]]
    assert anchors[0] == pytest.approx(na._SHORTS_LEAD_S, abs=0.01)
    assert nar["duration"] >= 30.0


def test_longer_sentence_gets_longer_pause(fake_tts, tmp_path):
    """쉼은 문장 길이에 비례한다(긴 문장 뒤엔 더 긴 호흡) — 균등 분배보다 자연스럽다."""
    chunks = ["短い。", "とても長い文章がここに入りますのでたっぷりと余韻が必要です。", "短い。"]
    na._spread_shorts_narration(chunks, tmp_path, 11.0)   # 쉼이 상한에 걸리지 않는 길이
    anchors = [a for _mp3, a in fake_tts["parts"]]
    lens = [0.18 * len(c) for c in chunks]
    gap1 = anchors[1] - (anchors[0] + lens[0])
    gap2 = anchors[2] - (anchors[1] + lens[1])
    assert gap2 > gap1, "긴 문장 뒤의 쉼이 더 길어야 합니다"


def test_subtitles_do_not_overlap_and_follow_speech(fake_tts, tmp_path):
    """자막 창은 발화 시각을 따라가고 서로 겹치지 않아야 한다(쉼 동안 잠깐 머문 뒤 사라짐)."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0)
    disp = nar["disp"]
    assert len(disp) == len(_CHUNKS)
    for i in range(len(disp) - 1):
        assert disp[i][2] <= disp[i + 1][1] + 1e-6, "자막이 겹칩니다"
        assert disp[i][2] > disp[i][1], "자막 표시 시간이 0 이하입니다"


def test_dense_script_falls_back_to_min_gap(fake_tts, tmp_path):
    """대본이 길어 남는 시간이 없으면 최소 쉼만 두고, 필요한 만큼 길이를 늘려 알린다."""
    long_chunks = _CHUNKS * 3
    nar = na._spread_shorts_narration(long_chunks, tmp_path, 20.0)
    anchors = [a for _mp3, a in fake_tts["parts"]]
    lens = [0.18 * len(c) for c in long_chunks]
    gaps = [anchors[i + 1] - (anchors[i] + lens[i]) for i in range(len(anchors) - 1)]
    assert all(abs(g - na._SHORTS_GAP_MIN) < 1e-6 for g in gaps)
    assert nar["duration"] > 20.0, "필요 길이를 늘려 돌려주지 않았습니다"


def test_failure_returns_none_for_safe_fallback(monkeypatch, tmp_path):
    """합성이 깨지면 None → 호출부가 기존 방식으로 폴백(제작이 멈추면 안 된다)."""
    from src.core import narration_sync
    monkeypatch.setattr(narration_sync, "synthesize",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tts down")))
    assert na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0) is None
    assert na._spread_shorts_narration([], tmp_path, 30.0) is None
