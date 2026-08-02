"""★① 자막 고아(마침표·한 글자) 금지 ② 쇼츠 총 길이 40초 초과 금지(운영자 확정).

운영자 지적:
  1. "자막에서 **마침표만** 그다음 페이지 자막으로 넘어가는 문제가 발생해. 저번에 얘기했던 것처럼
     한 글자나 한 점만 다음 자막으로 홀로 넘어가지 않게 해줘. 그래야 되는 상황이면 자막 사이즈를
     아주 조금 줄인다든가 해(**단, 두 줄은 안 돼**)."
  2. "오프닝 훅·엔드카드·수심 보여주는 부분을 제외한 나머지 길이를 줄여서 전체가 **절대 40초를
     넘지 않게**, 가급적 **35초 이내**로 끝내자."
"""
import pytest

from src.core import narration_sync as NS
from src.core import pipeline as P

MAX_PX = (720 - 176) * 0.96
SUBSZ = int(1280 * 0.039)


# ── ① 자막 고아 ────────────────────────────────────────────────
@pytest.mark.parametrize("orphan", ["。", "、", "…", "！", "す", " 。 "])
def test_orphan_chunk_is_absorbed_into_previous(orphan):
    """★핵심: 마침표/한 글자만 있는 청크가 **혼자 한 페이지**로 뜨면 안 된다."""
    disp = [("深海の底で、ひっそりと暮らす魚がいます", 0.0, 2.0),
            (orphan, 2.0, 2.3),
            ("その名はクサウオ", 2.3, 4.0)]
    got = NS.merge_orphan_chunks(disp)
    assert len(got) == 2, f"고아 청크가 남았습니다: {[g[0] for g in got]}"
    assert got[0][0].endswith(orphan.strip()), "앞 청크에 흡수되지 않았습니다"
    assert got[0][2] == 2.3, "흡수한 만큼 표시 시간이 이어지지 않았습니다"


def test_leading_orphan_goes_to_the_next_chunk():
    """첫 청크가 고아면 앞이 없으니 **뒤에** 붙인다(그래도 혼자 두지 않는다)."""
    got = NS.merge_orphan_chunks([("。", 0.0, 0.3), ("深海の底で", 0.3, 2.0)])
    assert len(got) == 1 and got[0][0].startswith("。")


def test_no_orphan_pieces_after_line_splitting():
    """줄 조각내기에서도 한 글자/문장부호 조각이 남으면 안 된다(중간 조각 포함)."""
    for text in ["水深3520メートル、光の届かない世界で、彼らは静かに漂っています。",
                 "とても長い一続きの文章がここにあってはみ出してしまいます。",
                 "深海の底で、ひっそりと暮らす一匹の魚がいます。その名はクサウオ。"]:
        for piece, _s, _e in NS._fit_pieces(text, 0.0, 3.0, MAX_PX, SUBSZ):
            assert not NS._is_orphan(piece), f"고아 조각이 생겼습니다: {piece!r} ← {text}"


def test_long_line_shrinks_font_instead_of_wrapping():
    """★두 줄 금지 — 넘치면 **글자를 조금 줄여** 한 줄을 유지한다(축소 한계도 지킨다)."""
    long_one = "水深三千五百二十メートルの闇の中で静かに漂い続けています"
    fs = NS.fit_font_size(long_one, MAX_PX, SUBSZ)
    assert fs < SUBSZ, "넘치는 줄인데 글자 크기가 그대로입니다"
    assert fs >= int(SUBSZ * NS._MIN_FS_RATIO), f"너무 작아졌습니다({fs}) — 가독성 바닥 침범"
    assert NS.fit_font_size("短い一行", MAX_PX, SUBSZ) == SUBSZ, "짧은 줄까지 줄이면 안 됩니다"


def test_ass_never_wraps_to_two_lines():
    """ASS 자체가 자동 줄바꿈을 하지 않아야 한다(WrapStyle 2 = 줄바꿈 없음)."""
    assert "WrapStyle: 2" in NS._ASS_HEAD, "자동 줄바꿈이 켜져 있으면 두 줄이 됩니다"


# ── ② 총 길이 ──────────────────────────────────────────────────
def test_budget_targets_35_and_caps_40():
    assert P._TARGET_TOTAL_S == 35.0 and P._HARD_MAX_TOTAL_S == 40.0
    # 고정 구간(훅·스팅어·엔드카드)은 줄이지 않는다 — 본문만 줄인다
    assert 8.0 <= P._FIXED_OVERHEAD_S <= 10.0, f"고정 구간 추정이 어긋납니다: {P._FIXED_OVERHEAD_S}"
    assert P.body_budget_s() + P._FIXED_OVERHEAD_S <= P._TARGET_TOTAL_S + 0.01


def test_char_budget_matches_the_target():
    """글자수 상한이 목표(35초)와 어긋나면 예산이 무의미해진다."""
    est_body_s = P._MAX_BODY_CHARS / P._JP_CPS
    assert est_body_s + P._FIXED_OVERHEAD_S <= P._TARGET_TOTAL_S + 0.5


def test_overlong_body_is_trimmed_under_the_hard_cap():
    """★합성 후 실측이 넘치면 뒤 절을 덜어내 40초 안으로 들어와야 한다."""
    chunks = [f"深海の底に静かに暮らす生き物がいます{i}。" for i in range(20)]
    chunks.append("チャンネル登録で、次の海もいっしょに。")
    dur = 45.0
    out = P._fit_body_to_budget(chunks, dur)
    assert len(out) < len(chunks), "예산을 넘겼는데 줄이지 않았습니다"
    cps = sum(len(c) for c in chunks) / dur
    est = sum(len(c) for c in out) / cps
    assert est + P._FIXED_OVERHEAD_S <= P._HARD_MAX_TOTAL_S, \
        f"줄였는데도 40초를 넘습니다: {est + P._FIXED_OVERHEAD_S:.1f}초"
    assert out[-1].startswith("チャンネル"), "구독 유도 절이 잘려나갔습니다"


def test_short_body_is_left_alone():
    """예산 안쪽이면 손대지 않는다(멀쩡한 본문을 깎으면 안 된다)."""
    chunks = ["深海の底に、"] * 14
    assert P._fit_body_to_budget(chunks, 20.0) == chunks


def test_pipeline_rechecks_length_after_synthesis():
    """소스 계약: 글자수 추정만 믿지 말고 **합성 후 실측**으로 다시 맞춰야 한다."""
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "src" / "core" / "pipeline.py").read_text(
        encoding="utf-8")
    i = s.index("nar = narration_sync.synthesize(chunks")
    assert "_fit_body_to_budget(chunks, float(nar[\"duration\"]))" in s[i:i + 900], \
        "합성 후 실제 길이로 재검사하지 않습니다"
