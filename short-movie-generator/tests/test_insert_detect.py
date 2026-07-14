"""watermark_qc 인위 삽입물(타이틀카드·로고) 검출 — OCR 비의존, 결정론 단위 테스트.

핵심 신호: 합성 그래픽은 밑 영상이 움직여도 '픽셀-정확 고정(frozen)' + '쨍한 색/엣지(graphic)'.
진짜 촬영은 큰 중앙 영역이 4초 내내 정확히 얼어있지 않는다(부유물·미세이동). 이 로직을 프레임을
직접 구성해 검증(네트워크 불필요)."""
import random

import pytest

from src.core import watermark_qc as WQ


def _frames_with_center_card(n=8, W=120, H=200):
    """중앙에 '픽셀-정확 고정 + 쨍한 빨강' 카드, 배경은 매 프레임 랜덤(움직이는 실사 모사)."""
    from PIL import Image, ImageDraw
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rectangle([int(W * .2), int(H * .35), int(W * .8), int(H * .6)], fill=(210, 25, 25, 255))
    d.rectangle([int(W * .2), int(H * .45), int(W * .8), int(H * .5)], fill=(245, 245, 245, 255))
    out = []
    rnd = random.Random(3)
    for _ in range(n):
        bg = Image.new("RGB", (W, H))
        bg.putdata([(rnd.randint(20, 70), rnd.randint(70, 120), rnd.randint(80, 130))
                    for _ in range(W * H)])
        out.append(Image.alpha_composite(bg.convert("RGBA"), card).convert("RGB"))
    return out


def _frames_all_moving(n=8, W=120, H=200):
    """전 화면이 매 프레임 바뀌는 실사(고정 영역 없음)."""
    from PIL import Image
    out = []
    rnd = random.Random(9)
    for _ in range(n):
        im = Image.new("RGB", (W, H))
        im.putdata([(rnd.randint(20, 90), rnd.randint(70, 130), rnd.randint(80, 140))
                    for _ in range(W * H)])
        out.append(im)
    return out


@pytest.mark.skipif(not hasattr(WQ, "_insert_masks"), reason="detector 없음")
def test_center_card_is_detected_as_insert():
    m = WQ._insert_masks(_frames_with_center_card())
    assert m is not None
    assert WQ._central_frac(m) >= WQ._INSERT_SKIP_CENTRAL   # 중앙 대형 삽입 → SKIP 임계 초과


def test_moving_footage_not_flagged():
    m = WQ._insert_masks(_frames_all_moving())
    # 고정 영역이 없으면 삽입물 비율이 임계 미만(오탐 없음 → 제작 실패 증가 방지)
    assert m is None or WQ._central_frac(m) < WQ._INSERT_SKIP_CENTRAL


def test_single_frame_returns_none():
    from PIL import Image
    assert WQ._insert_masks([Image.new("RGB", (10, 10))]) is None
