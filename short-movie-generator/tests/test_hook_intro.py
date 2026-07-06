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


@pytest.mark.skipif(not hi.fonts_available(), reason="시스템 폰트 없음")
def test_render_opening_frames(tmp_path):
    bg = str(tmp_path / "bg.png")
    Image.new("RGB", (720, 1280), (20, 40, 45)).save(bg)
    # 빠른 스모크: 짧은 세그먼트로 프레임 루프만 검증
    cfg = hi.HookIntroConfig(opening_seg_s=0.4)
    frames = hi.render_opening_frames(bg, ONSETS, SPEC, str(tmp_path / "of"), cfg)
    assert len(frames) == int(0.4 * 30)
    assert Image.open(frames[0]).size == (720, 1280)
