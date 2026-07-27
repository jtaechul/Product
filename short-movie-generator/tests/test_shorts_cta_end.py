"""구독 유도(자막+나레이션)가 **완성 영상 끝까지 실제로 살아남는지** 검증.

운영자 요청: "마지막에 구독 유도 자막/스크립트가 계속 나오는 게 맞아? 누락되면 반영하고,
마지막에 나오는지 테스트까지 해서 검증해."

검증 범위(문서 확인이 아니라 실제 산출물):
  ① 배치: 구독 유도가 **마지막** 자막이고 영상 끝 근처에서 끝난다.
  ② 자막 파일(ASS): 실제로 번인되는 파일에 구독 유도 문장이 들어 있다.
     ※ ASS는 긴 문장을 조각으로 쪼개 넣으므로 **조각을 이어 붙여** 확인해야 한다.
  ③ 오디오: 영상 마지막 구간에 실제로 소리가 있다(무음이면 나레이션이 빠진 것).
  ④ 폴백 경로에서도 구독 유도가 빠지지 않는다(예전엔 이 경로로 새면 통째로 사라졌다).
"""
import re
import subprocess
from pathlib import Path

import pytest

from src.core import narrate_attached as na
from src.core import narration_sync

_CHUNKS = ["深い海の底に、静かな影が広がります。",
           "光の届かない世界で、その体はゆっくりと揺れています。",
           "静けさの奥に、確かな命が息づいています。"]


def _has_net_tts() -> bool:
    """실제 TTS(edge-tts) 사용 가능 여부 — 불가하면 배치 검증만 수행."""
    try:
        r = narration_sync.synthesize(["テスト。"], "/tmp/_ctacheck", rate="+0%")
        return bool(r.get("mp3") and Path(r["mp3"]).stat().st_size > 500)
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def spread(tmp_path_factory):
    if not _has_net_tts():
        pytest.skip("edge-tts 사용 불가(네트워크)")
    work = tmp_path_factory.mktemp("cta")
    nar = na._spread_shorts_narration(_CHUNKS, work, 30.0)
    if not nar:
        pytest.skip("나레이션 분배 실패")
    return nar


def test_cta_is_the_last_subtitle_near_the_end(spread):
    """① 구독 유도가 마지막 자막이고, 영상 끝 근처(꼬리 여운 안)에서 끝난다."""
    last_txt, last_s, last_e = spread["disp"][-1]
    assert last_txt == na._SHORTS_CTA_JP, f"마지막 자막이 구독 유도가 아닙니다: {last_txt}"
    total = spread["duration"]
    assert last_e <= total + 0.05, "구독 유도가 영상 밖으로 밀렸습니다"
    assert total - last_e <= na._SHORTS_TAIL_S + na._SHORTS_GAP_MAX, (
        f"구독 유도가 끝에서 {total - last_e:.1f}초나 떨어져 있습니다")


def test_cta_survives_into_the_burned_subtitle_file(spread, tmp_path):
    """② 실제로 화면에 굽는 자막 파일(ASS)에 구독 유도가 들어 있다.
    ASS는 긴 문장을 조각내므로 마지막 조각들을 이어 붙여 확인한다(조각만 보면 오판한다)."""
    ass = narration_sync.build_synced_ass(spread["disp"], str(tmp_path / "s.ass"),
                                          hook_first=False, w=720, h=1280, sub_scale=1.8)
    lines = [ln for ln in Path(ass).read_text(encoding="utf-8").splitlines()
             if ln.startswith("Dialogue:")]
    assert lines, "자막 파일이 비었습니다"
    tail = "".join(re.sub(r"\{[^}]*\}", "", ln.split(",", 9)[9]) for ln in lines[-6:])
    assert "チャンネル" in tail and "登録" in tail, f"자막 끝에 구독 유도가 없습니다: {tail}"


def test_audio_is_not_silent_at_the_end(spread):
    """③ 영상 마지막 구간에 실제 소리가 있다(구독 유도 나레이션)."""
    total = spread["duration"]
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", spread["mp3"],
                        "-ss", f"{max(0.0, total - 6):.2f}", "-t", "6",
                        "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+)", r.stderr)
    assert m, "음량 측정 실패"
    assert float(m.group(1)) > -50.0, f"마지막 6초가 무음입니다({m.group(1)}dB)"


def test_fallback_path_also_speaks_the_cta():
    """④ 분배가 실패해 옛 방식으로 폴백해도 구독 유도가 대본에 포함된다(소스 계약).
    예전엔 이 경로로 빠지면 구독 유도가 통째로 사라졌다."""
    src = Path(na.__file__).read_text(encoding="utf-8")
    i = src.index("if not nar:                       # 분배 실패")
    seg = src[i:i + 700]
    assert "chunks + [_SHORTS_CTA_JP]" in seg, "폴백 경로에 구독 유도가 빠졌습니다"


def test_subtitle_script_is_recorded_for_the_admin_page():
    """자막 스크립트(시각·일본어·한국어)를 레코드에 남겨 관리자 페이지가 보여줄 수 있어야 한다."""
    src = Path(na.__file__).read_text(encoding="utf-8")
    assert "def _subs_record(" in src
    assert 'meta["subs"] = _subs_record(' in src
    from src.core import content_store
    cs = Path(content_store.__file__).read_text(encoding="utf-8")
    assert 'rec["subs"] = meta["subs"]' in cs, "레코드에 자막이 저장되지 않습니다"
    worker = (Path(na.__file__).parents[2] / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "function subsPanel(" in worker and "subsPanel(rec)" in worker, "상세 페이지에 자막 표가 없습니다"
    assert "구독 유도" in worker, "구독 유도 줄 표시가 없습니다"


def test_subs_record_shifts_by_opening_offset(monkeypatch):
    """오프닝 훅이 앞에 붙는 만큼 자막 시각을 밀어 **완성본 기준**으로 기록한다."""
    monkeypatch.setattr(na, "llm", None, raising=False)
    rows = na._subs_record([("あ。", 1.0, 2.0), ("い。", 3.0, 4.0)], offset=4.6)
    assert [r["s"] for r in rows] == [5.6, 7.6]
    assert all("ko" in r for r in rows)
