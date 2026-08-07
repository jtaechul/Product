"""★엔드카드에 **시각적 구독 유도**가 있어야 한다(운영자 확정 · vidIQ 분석 결과).

@abyss_0cean 실측(2026-08-05): 조회수 35,969 / 구독자 24명 = **전환율 0.067%**.
  정상 쇼츠는 0.5~2% — 10~30배 낮다. 좋아요 0.5%, 댓글 총 4개.
진단: 엔드카드에 **구독 유도가 시각적으로 아예 없었다**. 종명·학명·수심·특징·크레딧만 있고,
  구독 문구는 나레이션 음성에만 존재했다. 쇼츠는 마지막 화면의 시각 신호가 전환을 만든다.
조치: 엔드카드 하단에 ①왜 구독하는지 한 줄 ②'チャンネル登録' 알약 배지를 넣는다.
  ★배지가 화면 밖으로 잘리거나 크레딧과 겹치면 없느니만 못하다 → 좌표를 픽셀로 검증한다.
"""
import shutil

import pytest

from src.core import hook_intro as HI


def _spec():
    return HI.SpeciesSpec(jp_name="クサウオ", sci_name="Liparidae",
                          feature_line="水圧に耐える、骨のない体",
                          depth_min=200, depth_max=3520,
                          hook_line1="a", hook_line2="b", hook_pop_words=["a"])


def test_config_has_subscribe_cta():
    cfg = HI.HookIntroConfig()
    assert cfg.end_cta_text.strip(), "구독 이유 문구가 비었습니다"
    assert "登録" in cfg.end_cta_sub, "구독 배지 문구가 없습니다"
    assert cfg.end_cta_size >= 36, "너무 작으면 모바일에서 안 보입니다"


def test_source_renders_the_cta():
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "src" / "core"
         / "hook_intro.py").read_text(encoding="utf-8")
    i = s.index("def render_endcard(")
    body = s[i:s.index("\ndef ", i + 10)]
    assert "end_cta_text" in body and "end_cta_sub" in body, \
        "엔드카드가 구독 유도를 그리지 않습니다(음성에만 있으면 전환이 안 됩니다)"
    assert "rounded_rectangle" in body, "구독 배지(알약)가 없습니다"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="렌더 환경 없음")
def test_cta_is_inside_the_frame_and_clear_of_credit(tmp_path):
    """★픽셀 검증: 배지가 화면 안에 있고, 크레딧 줄과 겹치지 않아야 한다."""
    from PIL import Image
    cfg = HI.HookIntroConfig()
    bg = tmp_path / "bg.png"
    Image.new("RGB", (cfg.W, cfg.H), (12, 34, 54)).save(bg)
    out = str(tmp_path / "endcard.png")
    HI.render_endcard(str(bg), _spec(), out)
    im = Image.open(out).convert("RGB")
    assert im.size == (cfg.W, cfg.H)

    def badge_rows(y0, y1):
        """그 구간에서 **배지 색(시안 120,220,255)** 픽셀이 있는 행 수.

        ⚠판정식을 느슨하게 잡으면 회색 크레딧 글자(150,166,192)까지 배지로 세어
        '잘렸다'는 거짓 실패가 난다(실제로 겪음) → 시안만 잡도록 좁게 잡는다."""
        n = 0
        for y in range(y0, y1):
            row = [im.getpixel((x, y)) for x in range(cfg.W // 4, cfg.W * 3 // 4, 6)]
            if any(p[2] > 230 and p[1] > 195 and p[0] < 160 for p in row):
                n += 1
        return n

    # 배지는 화면 하단 안쪽(마지막 40px 밖)에 온전히 있어야 한다
    assert badge_rows(1100, cfg.H - 40) > 20, "구독 배지가 보이지 않습니다"
    assert badge_rows(cfg.H - 12, cfg.H) == 0, "배지가 화면 아래로 잘렸습니다"


def test_narration_cta_still_exists():
    """음성 CTA도 그대로 유지 — 시각/청각 둘 다 있어야 한다(하나만으론 약하다)."""
    from src.core import pipeline as P
    assert any("登録" in c for c in P._CTA_BODY_JP), "나레이션 구독 유도가 사라졌습니다"
