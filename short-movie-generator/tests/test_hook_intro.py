"""hook_intro 스모크 테스트 — 오프닝/엔드카드/붐/플래시가 헤드리스로 산출되는지 검증.

폰트가 없는 환경(일부 CI)에서는 렌더 테스트를 스킵한다(붐/플래시는 폰트 무관 → 항상 검증).
"""
import wave
from pathlib import Path

import pytest

from PIL import Image

from src.core import hook_intro as hi

SPEC = hi.SpeciesSpec(
    jp_name="ユメナマコ",
    sci_name="Enypniastes eximia",
    depth_min=500, depth_max=6000,
    hook_line1="頭も、目も、", hook_line2="骨もない。",
    hook_pop_words=["頭も、", "目も、", "骨もない。"],
    feature_line="泳ぐ・光る・透ける、深海のナマコ",
    feature_glow_word="光る",
)
ONSETS = {"頭": 0.10, "目": 1.10, "骨": 1.85}


def test_generate_boom_is_valid_wav(tmp_path):
    out = str(tmp_path / "boom.wav")
    hi.generate_boom(out)
    assert Path(out).stat().st_size > 1000
    with wave.open(out) as w:
        assert w.getframerate() == 44100
        assert w.getnframes() > 0
        # 딥 붐 길이(≈0.46s) 확인
        assert abs(w.getnframes() / 44100 - hi.HookIntroConfig().boom_dur_s) < 0.02


def test_build_flash_png(tmp_path):
    out = str(tmp_path / "flash.png")
    hi.build_flash_png(out)
    assert Image.open(out).size == (720, 1280)


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트(Noto Serif/Sans, mono, sci) 없음")
def test_render_endcard(tmp_path):
    bg = str(tmp_path / "bg.png")
    Image.new("RGB", (720, 1280), (40, 20, 30)).save(bg)
    out = str(tmp_path / "endcard.png")
    hi.render_endcard(bg, SPEC, out)
    assert Image.open(out).size == (720, 1280)


def test_generate_type_click(tmp_path):
    out = str(tmp_path / "tk.wav")
    hi.generate_type_click(out)
    with wave.open(out) as w:
        assert w.getframerate() == 44100
        assert w.getnframes() > 0


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_render_endcard_frames_typewriter(tmp_path):
    bg = str(tmp_path / "bg.png")
    Image.new("RGB", (720, 1280), (30, 20, 25)).save(bg)
    cfg = hi.HookIntroConfig(endcard_dur_s=0.5)  # 빠른 스모크
    frames, clicks = hi.render_endcard_frames(bg, SPEC, str(tmp_path / "ec"), cfg)
    assert len(frames) == int(0.5 * 30)
    assert Image.open(frames[0]).size == (720, 1280)
    # 타자 클릭 시각은 오름차순·공백 제외
    assert clicks == sorted(clicks)
    assert len(clicks) > 0


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_render_opening_frames(tmp_path):
    bg = str(tmp_path / "bg.png")
    Image.new("RGB", (720, 1280), (20, 40, 45)).save(bg)
    # 빠른 스모크: 짧은 세그먼트로 프레임 루프만 검증
    cfg = hi.HookIntroConfig(opening_seg_s=0.4)
    frames = hi.render_opening_frames(bg, ONSETS, SPEC, str(tmp_path / "of"), cfg)
    assert len(frames) == int(0.4 * 30)
    assert Image.open(frames[0]).size == (720, 1280)


# ─────────────── 회귀: 오프닝 타이틀 넘침(실제 결함) ───────────────
LONG_SPEC = hi.SpeciesSpec(          # メンダコ 훅 — 고정 98px에서 좌우로 잘려 나가던 케이스
    jp_name="メンダコ", sci_name="Opisthoteuthis californiana",
    depth_min=200, depth_max=1500,
    hook_line1="ぺたんこの、体に、", hook_line2="耳のひれ。",
    hook_pop_words=["ぺたんこの、", "体に、", "耳のひれ。"],
    feature_line="ひらひら舞う、深海のメンダコ", feature_glow_word="舞う",
)


def _word_extents(lay, words):
    """레이아웃 기준 각 어절의 (left, right) 픽셀 경계."""
    from PIL import ImageDraw
    meas = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
    out = []
    for w, (cx, _cy) in zip(words, lay["centers"]):
        ww = meas.textlength(w, font=lay["font"])
        out.append((cx - ww / 2, cx + ww / 2))
    return out


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_opening_layout_never_overflows_long_hook():
    """긴 훅도 모든 어절이 안전영역 안에 들어와야 한다(화면 밖 잘림 원천 차단)."""
    cfg = hi.HookIntroConfig()
    lay = hi.opening_layout(LONG_SPEC, cfg)
    lo = cfg.shake_margin + cfg.title_safe_x
    hi_x = cfg.W - lo
    for left, right in _word_extents(lay, LONG_SPEC.hook_pop_words):
        assert left >= lo - 2 and right <= hi_x + 2, f"어절 넘침: {left:.0f}~{right:.0f}"


# ★실제 결함(재발): hook_line1이 좁아도 실제 line1은 pop 어절들의 '가로 연결'이라 더 넓어
#   오른쪽 화면 밖으로 잘렸다(예: line1="まるで宇宙" 기준으로 맞췄으나 렌더는 "まるで宇宙深海の").
MISMATCH_SPEC = hi.SpeciesSpec(
    jp_name="X", sci_name="Duobrachium sparksae",
    depth_min=200, depth_max=2000,
    hook_line1="まるで宇宙", hook_line2="深海の幽霊。",           # line1이 join과 다름(좁음)
    hook_pop_words=["まるで宇宙", "深海の", "幽霊。"],             # 실제 line1 = "まるで宇宙深海の"
    feature_line="宇宙のような、深海のクラゲ", feature_glow_word="宇宙",
)


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_opening_layout_no_overflow_when_line1_differs_from_join():
    """hook_line1 ≠ 앞 어절 연결(join)이어도 실제 렌더 줄이 안전영역 안이어야 한다(오른쪽 잘림 재발 방지)."""
    cfg = hi.HookIntroConfig()
    lay = hi.opening_layout(MISMATCH_SPEC, cfg)
    lo = cfg.shake_margin + cfg.title_safe_x
    hi_x = cfg.W - lo
    for left, right in _word_extents(lay, MISMATCH_SPEC.hook_pop_words):
        assert left >= lo - 2 and right <= hi_x + 2, f"어절 넘침: {left:.0f}~{right:.0f}"


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_opening_layout_keeps_confirmed_flagship_design():
    """확정 디자인(ユメナマコ: 98px·2줄)은 자동 맞춤 도입 후에도 그대로여야 한다."""
    cfg = hi.HookIntroConfig()
    lay = hi.opening_layout(SPEC, cfg)
    assert lay["size"] == cfg.title_size          # 축소 없음
    assert lay["rows"] == 2                       # 2줄 유지
    ys = {cy for _cx, cy in lay["centers"]}
    assert ys == {cfg.title_y1, cfg.title_y2}


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_opening_layout_switches_to_3lines_when_2line_too_small():
    """2줄 유지가 과축소(<min_2line)면 어절당 1줄로 전환해 큰 글자를 유지한다."""
    cfg = hi.HookIntroConfig()
    lay = hi.opening_layout(LONG_SPEC, cfg)
    assert lay["rows"] == 3
    assert lay["size"] >= cfg.title_min_2line     # 3줄 전환으로 큰 크기 회복
    ys = [cy for _cx, cy in lay["centers"]]
    assert len(set(ys)) == 3 and ys == sorted(ys)


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_endcard_lines_fit_within_width(tmp_path):
    """엔드카드 국명·특징문구가 길어도 화면폭을 넘지 않게 자동 축소된다."""
    from PIL import ImageDraw
    cfg = hi.HookIntroConfig()
    wide = hi.SpeciesSpec(jp_name="オオグチボヤノナカマタチ", sci_name="Megalodicopia hians longname",
                          depth_min=200, depth_max=1000, hook_line1="a", hook_line2="b",
                          hook_pop_words=["a", "b"], feature_line="とてもとても長い特徴文がここに入ります、深海の生き物",
                          feature_glow_word="深海")
    meas = ImageDraw.Draw(Image.new("RGBA", (2, 2)))
    f = hi._fit_font(wide.jp_name, cfg.end_title_size, cfg.W - 72, hi._serif)
    assert meas.textlength(wide.jp_name, font=f) <= cfg.W - 72
    f2 = hi._fit_font(wide.feature_line, cfg.end_feature_size, cfg.W - 72, hi._serif)
    assert meas.textlength(wide.feature_line, font=f2) <= cfg.W - 72


def test_specimen_bg_caps_tall_source(tmp_path):
    """9:16 등 세로로 긴 소스도 밴드 높이를 넘지 않게 중앙 크롭된다(과확대 방지)."""
    src = str(tmp_path / "tall.png")
    Image.new("RGB", (720, 1280), (60, 30, 40)).save(src)
    out = str(tmp_path / "bg.png")
    hi.build_specimen_bg(src, out)
    assert Image.open(out).size == (720, 1280)
