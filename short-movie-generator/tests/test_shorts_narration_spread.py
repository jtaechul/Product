"""쇼츠 나레이션 분배 — 문장 사이 쉼 + 영상 전체 배치 회귀 테스트.

운영자 지적(실사고): "나레이션이 문장과 문장 사이 간격 없이 빠르게만 나와서 어색하다.
영상 뒷부분에는 아무 나레이션이 없다." → 문장을 이어붙여 한 번에 읽히던 방식을 폐기하고,
문장별로 합성해 **영상 끝까지 고르게 배치**한다.

운영자 확정 규칙(절대 회귀 금지):
  ① 문장 사이는 **무조건 1초 이상** 쉰다.
  ② **영상 길이에 맞춰 나레이션(문장 수)을 조정**한다 — 억지로 밀어 넣지 않는다.
  ③ 영상이 끝나기 전에 **구독 유도(자막+나레이션)를 반드시** 넣고, 그 길이를 ②의 계산에 반영한다.
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


def _gaps(fake_tts, nar):
    """실제 배치에서 문장 사이 쉼(초) 목록. parts=[(mp3, anchor)] · 마지막은 구독 유도."""
    anchors = [a for _mp3, a in fake_tts["parts"]]
    spoken = list(nar["chunks"]) + [na._SHORTS_CTA_JP]
    lens = [0.18 * len(c) for c in spoken]
    return [anchors[i + 1] - (anchors[i] + lens[i]) for i in range(len(anchors) - 1)]


def test_gap_between_sentences_is_at_least_one_second(fake_tts, tmp_path):
    """★① 문장 사이는 무조건 1초 이상(운영자 확정) — 붙여 읽으면 안 된다."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0)
    assert nar and nar.get("spread")
    assert na._SHORTS_GAP_MIN >= 1.0, "최소 쉼이 1초 아래로 내려갔습니다"
    for i, gap in enumerate(_gaps(fake_tts, nar)):
        assert gap >= 1.0 - 1e-6, f"문장 {i+1}→{i+2} 사이 쉼이 1초 미만입니다: {gap:.2f}s"
        assert gap <= na._SHORTS_GAP_MAX + 1e-6, f"쉼이 과도합니다(끊긴 느낌): {gap:.2f}s"


def test_subscribe_cta_is_always_appended_at_the_end(fake_tts, tmp_path):
    """★③ 구독 유도(자막+나레이션)는 영상이 끝나기 전에 **무조건** 들어간다."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0)
    assert nar["disp"][-1][0] == na._SHORTS_CTA_JP, "마지막에 구독 유도 자막이 없습니다"
    assert fake_tts["parts"][-1][1] > 0, "구독 유도 나레이션이 배치되지 않았습니다"
    cta_start = fake_tts["parts"][-1][1]
    cta_end = cta_start + 0.18 * len(na._SHORTS_CTA_JP)
    assert cta_end <= nar["duration"] + 1e-6, "구독 유도가 영상 밖으로 밀렸습니다"
    assert cta_end >= nar["duration"] - na._SHORTS_TAIL_S - na._SHORTS_GAP_MAX, (
        "구독 유도가 영상 끝에서 너무 멀리 떨어져 있습니다")
    assert na._SHORTS_CTA_JP not in nar["chunks"], "구독 유도가 본문 대본에 섞였습니다"


def test_narration_reaches_the_end_of_video(fake_tts, tmp_path):
    """★핵심: 뒷부분이 통째로 무음이면 안 된다 — 마지막(구독 유도)이 영상 끝 근처에서 끝나야 한다."""
    target = 30.0
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, target)
    anchors = [a for _mp3, a in fake_tts["parts"]]
    end = anchors[-1] + 0.18 * len(na._SHORTS_CTA_JP)
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
    nar = na._spread_shorts_narration(chunks, tmp_path, 16.0)   # 쉼이 상한에 걸리지 않는 길이
    gaps = _gaps(fake_tts, nar)
    assert len(nar["chunks"]) == 3, "이 길이에선 문장을 줄일 필요가 없습니다"
    assert gaps[1] > gaps[0], "긴 문장 뒤의 쉼이 더 길어야 합니다"


def test_subtitles_do_not_overlap_and_follow_speech(fake_tts, tmp_path):
    """자막 창은 발화 시각을 따라가고 서로 겹치지 않아야 한다(쉼 동안 잠깐 머문 뒤 사라짐)."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0)
    disp = nar["disp"]
    assert len(disp) == len(nar["chunks"]) + 1        # 본문 + 구독 유도
    for i in range(len(disp) - 1):
        assert disp[i][2] <= disp[i + 1][1] + 1e-6, "자막이 겹칩니다"
        assert disp[i][2] > disp[i][1], "자막 표시 시간이 0 이하입니다"


def test_script_is_trimmed_to_fit_the_video_length(fake_tts, tmp_path):
    """★② 영상 길이에 맞춰 문장 수를 줄인다 — 1초 쉼과 구독 유도 자리를 지키면서."""
    long_chunks = _CHUNKS * 3                      # 15문장(짧은 영상에 다 들어갈 수 없다)
    nar = na._spread_shorts_narration(long_chunks, tmp_path, 30.0)
    assert len(nar["chunks"]) < len(long_chunks), "긴 대본이 그대로 밀어 넣어졌습니다"
    for gap in _gaps(fake_tts, nar):
        assert gap >= 1.0 - 1e-6, "문장을 줄였는데도 쉼이 1초 미만입니다"
    assert nar["disp"][-1][0] == na._SHORTS_CTA_JP, "줄이는 과정에서 구독 유도가 사라졌습니다"


def test_opening_and_closing_sentences_survive_trimming(fake_tts, tmp_path):
    """줄일 때도 이야기의 처음·끝은 남긴다(중간 문장을 덜어낸다)."""
    nar = na._spread_shorts_narration(_CHUNKS, tmp_path, 22.0)
    assert nar["chunks"][0] == _CHUNKS[0]
    assert nar["chunks"][-1] == _CHUNKS[-1]
    assert len(nar["chunks"]) >= na._SHORTS_MIN_BODY


def test_failure_returns_none_for_safe_fallback(monkeypatch, tmp_path):
    """합성이 깨지면 None → 호출부가 기존 방식으로 폴백(제작이 멈추면 안 된다)."""
    from src.core import narration_sync
    monkeypatch.setattr(narration_sync, "synthesize",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tts down")))
    assert na._spread_shorts_narration(_CHUNKS, tmp_path, 30.0) is None
    assert na._spread_shorts_narration([], tmp_path, 30.0) is None
