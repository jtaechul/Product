"""reframe 피사체 추적 회귀 테스트(실제 결함 기반).

결함: 해저 퇴적물의 옅은 붉은 기(확산 노이즈)가 센트로이드를 오염시켜
크롭이 피사체와 노이즈 '사이'를 겨냥 → 생물이 화면 가장자리로 밀렸다.
수정: 상위 적색 코어 픽셀만으로 센트로이드 계산 → 가장 선명한 붉은 덩어리(생물)에 고정.
"""
from PIL import Image, ImageDraw

from src.core import reframe


def _synthetic_frame(path: str):
    """왼쪽=넓고 옅은 붉은 퇴적물 노이즈, 오른쪽(0.75, 0.40)=작고 강한 붉은 생물."""
    im = Image.new("RGB", (480, 270), (60, 90, 80))          # 초록빛 해저
    d = ImageDraw.Draw(im)
    d.rectangle([20, 60, 200, 220], fill=(120, 88, 80))       # 옅은 붉은기(r-g=32) 넓게
    d.ellipse([340, 90, 380, 126], fill=(190, 60, 70))        # 강한 적색 생물(r-g=130)
    im.save(path)


def test_centroid_locks_on_strong_red_core(tmp_path):
    f = str(tmp_path / "frame.png")
    _synthetic_frame(f)
    fx, fy = reframe._subject_centroid(f)
    # 생물 중심 ≈ (360/479, 108/269) = (0.75, 0.40). 오염됐다면 왼쪽 노이즈로 크게 끌려감.
    assert abs(fx - 0.75) < 0.06, f"fx={fx:.3f} — 확산 노이즈에 오염됨"
    assert abs(fy - 0.40) < 0.06, f"fy={fy:.3f}"


def test_centroid_center_fallback_when_no_red(tmp_path):
    f = str(tmp_path / "green.png")
    Image.new("RGB", (480, 270), (40, 80, 70)).save(f)
    assert reframe._subject_centroid(f) == (0.5, 0.5)


def test_subject_score_prefers_frame_with_creature(tmp_path):
    with_c = str(tmp_path / "with.png"); _synthetic_frame(with_c)
    without = str(tmp_path / "without.png")
    Image.new("RGB", (480, 270), (60, 90, 80)).save(without)
    assert reframe.subject_score(with_c) > reframe.subject_score(without)


def test_subject_score_penalizes_screen_filling_closeup(tmp_path):
    """(실제 결함) ROV 초근접 컷: 생물이 화면을 가득 채우면 전신 프레임보다 점수가 낮아야 한다."""
    whole = str(tmp_path / "whole.png"); _synthetic_frame(whole)      # 전신이 온전히 보임
    closeup = str(tmp_path / "closeup.png")
    Image.new("RGB", (480, 270), (190, 60, 70)).save(closeup)          # 화면 전체가 생물 피부
    assert reframe.subject_score(whole) > reframe.subject_score(closeup)


def test_pick_wide_window_selects_full_body_span():
    """(전신 보장) 근접 구간(점유율 큼)이 아니라 전신이 보이는 구간이 선택돼야 한다."""
    # 0~9초: 초근접(frac 0.8), 10~19초: 전신 와이드(frac 0.08), 20~29초: 부재(frac 0)
    scores = [50.0] * 50 + [40.0] * 50 + [0.0] * 50
    fracs = [0.80] * 50 + [0.08] * 50 + [0.0] * 50
    sa = reframe._pick_wide_window(scores, fracs, 5.0, 5.0)
    assert 9.0 <= sa <= 15.0, f"전신 구간(10~19s)이 아닌 {sa}s 선택"


def test_pick_windows_prefers_high_score_spans():
    """소스 앞부분이 아니라 피사체 점수가 높은 구간이 선택돼야 한다."""
    # 0~9초 점수 0(피사체 없음), 10~19초 점수 높음, 20~29초 중간
    scores = [0.0] * 50 + [10.0] * 50 + [3.0] * 50   # 5fps × 30초
    starts = reframe._pick_windows(scores, 5.0, 5.0, 2)
    assert all(s >= 9.0 for s in starts), f"저점수(무피사체) 앞구간이 선택됨: {starts}"
    assert starts == sorted(starts)                   # 시간순 배치


def test_subject_score_penalizes_edge_cut_subject(tmp_path):
    """생물이 프레임 경계에 잘려 있으면 온전히 보이는 프레임보다 점수가 낮아야 한다."""
    whole = str(tmp_path / "whole.png"); _synthetic_frame(whole)
    cut = str(tmp_path / "cut.png")
    im = Image.new("RGB", (480, 270), (60, 90, 80))
    ImageDraw.Draw(im).ellipse([-30, 100, 30, 140], fill=(190, 60, 70))  # 왼쪽 경계에 걸침
    im.save(cut)
    assert reframe.subject_score(whole) > reframe.subject_score(cut)
