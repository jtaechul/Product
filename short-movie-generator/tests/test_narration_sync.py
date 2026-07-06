"""narration_sync 정합 로직 검증(네트워크 불필요) — 단어 타임스탬프→자막 창."""
from src.core import narration_sync as ns


def test_align_chunks_to_words_uses_real_timestamps():
    # 가짜 단어 경계(start, dur, text): 문장부호는 경계에 없음(edge-tts와 동일)
    words = [(0.10, 0.37, "頭"), (0.47, 0.19, "も"), (0.99, 0.15, "目"), (1.15, 0.18, "も"),
             (1.64, 0.24, "骨"), (1.89, 0.12, "も"), (2.00, 0.29, "ない"),
             (3.13, 0.51, "深海"), (3.64, 0.12, "の"), (3.75, 0.23, "闇"), (3.98, 0.24, "を")]
    chunks = ["頭も、目も、骨もない。", "深海の闇を、"]
    al = ns.align_chunks_to_words(chunks, words)
    # 청크1 시작=첫 단어(0.10), 청크2 시작=深海(3.13) → 쉼(0.8s) 정확 반영
    assert abs(al[0][1] - 0.10) < 0.01
    assert abs(al[1][1] - 3.13) < 0.01
    # 글자수 비례였다면 청크2가 훨씬 이르게 떴을 것 → 실제 발화 시각과 어긋남(그걸 고친 것)


def test_display_windows_are_continuous_no_gaps():
    words = [(0.0, 0.5, "あ"), (1.5, 0.5, "い"), (3.0, 0.5, "う")]
    disp = ns._display_windows(ns.align_chunks_to_words(["あ", "い", "う"], words))
    # 각 청크 끝 == 다음 청크 시작(빈 화면 없음)
    assert abs(disp[0][2] - disp[1][1]) < 0.01
    assert abs(disp[1][2] - disp[2][1]) < 0.01


def test_build_synced_ass(tmp_path):
    disp = [("頭も、目も、骨もない。", 0.1, 3.1), ("深海の闇を、", 3.1, 4.5)]
    out = ns.build_synced_ass(disp, str(tmp_path / "s.ass"))
    txt = open(out, encoding="utf-8").read()
    assert txt.count("Dialogue:") == 2
    assert "Hook" in txt and "Sub" in txt          # 첫 줄=훅, 나머지=서브
    assert "0:00:00.10" in txt                      # 실제 발화 시각 반영
