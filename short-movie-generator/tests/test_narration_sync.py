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


def test_install_ca_swallows_permission_error(monkeypatch):
    """회귀 테스트(실제 CI 장애): 비 root 러너에서 Path.exists()가 PermissionError를
    되던져도 _install_ca()가 죽으면 안 된다. 과거 이 예외가 나레이션 합성을 통째로
    죽여 영상 미제작·텔레그램 무전송을 일으켰다(#54)."""
    def boom(self):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(ns.Path, "exists", boom)
    ns._install_ca()  # 예외를 밖으로 던지지 않아야 통과


def test_hook_intro_install_ca_swallows_permission_error(monkeypatch):
    """hook_intro_stage 쪽 동일 패턴도 회귀 방지."""
    from src.core import hook_intro_stage as his

    def boom(self):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(his.Path, "exists", boom)
    his._install_ca()


def test_fit_pieces_keeps_date_number_whole():
    """★자막 줄바꿈 수정: 숫자·날짜(1914年5月29日)를 조각 경계에서 쪼개지 않는다
    (실사고: '1914年5' | '月29日'로 분리)."""
    subsz = int(1280 * 0.039 * 1.5)
    max_px = (720 - 2 * 88) * 0.96
    for text in ["しかし1914年5月29日、船は沈みました", "総トン数は14191トンでした", "約4億年前の生命"]:
        pieces = [p for p, _, _ in ns._fit_pieces(text, 0.0, 3.0, max_px, subsz)]
        joined = "".join(pieces)
        assert joined == text                      # 글자 손실 없음
        # 숫자 그룹이 두 조각에 걸쳐 쪼개지지 않았는지: 각 그룹이 어느 한 조각에 통째로 들어감
        for a, b in ns._num_spans(text):
            grp = text[a:b]
            assert any(grp in p for p in pieces), f"숫자그룹 '{grp}'가 쪼개짐: {pieces}"


def test_num_spans_detects_date_and_number():
    t = "しかし1914年5月29日、"
    assert ns._num_spans(t) == [(3, 13)] and t[3:13] == "1914年5月29日"   # 날짜 통째
    assert ns._num_spans("14191トン") and ns._num_spans("14191トン")[0][0] == 0
    assert ns._num_spans("あいうえお") == []                        # 숫자 없음
