"""CTA(구독·댓글 유도) 배치 규칙 회귀 테스트.

확정 규칙(운영자 결정):
  · 구독 유도 → 캡션 + 나레이션 **양쪽**
  · 댓글 유도 → 캡션(설명란) **에만** (나레이션 금지 — 마무리 여운·시청완료율 보호)
  · 나레이션 CTA는 길이 상한 컷 **이후**에 붙어 잘리지 않는다.
"""
from src.core import pipeline, rich_caption


def test_narration_cta_appended_after_close():
    body = ["深海の底に、", "うずくまる影。", "静かな大食漢です。"]
    out = pipeline._append_cta(body)
    assert out[:3] == body                      # 원본 마무리 보존
    # ★CTA 절 수는 문안을 바꾸면 달라진다 → 상수를 그대로 참조해 고정값을 박지 않는다.
    assert out[-len(pipeline._CTA_BODY_JP):] == pipeline._CTA_BODY_JP


def test_narration_cta_not_duplicated():
    once = pipeline._append_cta(["深海に、", "生きる姿。"])
    twice = pipeline._append_cta(once)
    assert once == twice


def test_narration_cta_has_no_comment_inducement():
    """나레이션에는 댓글 유도가 들어가면 안 된다."""
    joined = "".join(pipeline._CTA_BODY_JP + pipeline._CTA_BODY_JP_DOC)
    assert "コメント" not in joined
    assert "チャンネル登録" in joined


def test_wreck_doc_cta_variant():
    out = pipeline._append_cta(["静かに眠っています。"], doc=True)
    assert out[-len(pipeline._CTA_BODY_JP_DOC):] == pipeline._CTA_BODY_JP_DOC
    # 침몰선 편은 '1隻' — 생물용 문안('1種'·図鑑)이 섞이면 안 된다
    joined = "".join(out[-len(pipeline._CTA_BODY_JP_DOC):])
    assert "1種" not in joined and "図鑑" not in joined


def test_cta_budget_keeps_total_within_shorts_rule():
    """CTA 길이만큼 본문 예산을 미리 빼므로, 컷+CTA 총합이 상한을 넘지 않는다."""
    long_body = [f"深海の底に生きる姿です{i}。" for i in range(40)]
    cta_len = sum(len(c) for c in pipeline._CTA_BODY_JP)
    capped = pipeline._cap_body_chunks(long_body, max_chars=pipeline._MAX_BODY_CHARS - cta_len)
    final = pipeline._append_cta(capped)
    assert sum(len(c) for c in final) <= pipeline._MAX_BODY_CHARS + len(long_body[-1])


def test_caption_cta_contains_both_jp():
    txt = rich_caption._with_cta("深海の底に、静かな影。\n\n映像: NOAA", ko=False)
    for line in rich_caption._CTA_JP:
        assert line in txt
    # 크레딧 줄은 여전히 맨 끝
    assert txt.strip().split("\n")[-1].startswith("映像:")


def test_caption_cta_contains_both_ko():
    txt = rich_caption._with_cta("심해 바닥의 조용한 그림자.\n\n영상: NOAA", ko=True)
    for line in rich_caption._CTA_KO:
        assert line in txt
    assert txt.strip().split("\n")[-1].startswith("영상:")


def test_caption_cta_not_duplicated():
    once = rich_caption._with_cta("本文。\n\n映像: NOAA", ko=False)
    assert rich_caption._with_cta(once, ko=False) == once
