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


# ─────────────── 번인 텍스트(인트로 자막판·아웃트로 URL) 배제 ───────────────
def _text_banner_frame(path: str, bg=(60, 90, 80)):
    """NOAA 타이틀 카드식 '가는 흰 글자 획'이 여러 줄 있는 프레임(에지 밀도 높음)."""
    im = Image.new("RGB", (480, 270), bg)
    d = ImageDraw.Draw(im)
    # 얇은 흰 획을 격자로 촘촘히 → 실제 텍스트처럼 밝은 에지가 많게
    for yy in range(150, 250, 6):
        for xx in range(20, 460, 5):
            d.line([xx, yy, xx + 2, yy], fill=(245, 245, 245), width=1)
    im.save(path)


def _bright_sand_frame(path: str):
    """텍스트 없는 '밝은 모래 바닥'(대왕등각류 소스류) — 균일하게 밝지만 대비 낮음."""
    im = Image.new("RGB", (480, 270), (205, 210, 200))
    im.save(path)


def test_text_score_detects_thin_stroke_text(tmp_path):
    """(실제 결함) 가는 흰 글자 획이 많은 타이틀 카드는 텍스트 점수가 높아야 한다."""
    banner = str(tmp_path / "banner.png"); _text_banner_frame(banner)
    clean = str(tmp_path / "clean.png"); _synthetic_frame(clean)
    assert reframe.text_score(banner) > 0.006
    assert reframe.text_score(clean) < 0.004


def test_text_score_ignores_bright_sand(tmp_path):
    """(실제 결함) 균일하게 밝은 모래 바닥은 텍스트로 오인되면 안 된다(에지 대비 낮음)."""
    sand = str(tmp_path / "sand.png"); _bright_sand_frame(sand)
    banner = str(tmp_path / "banner.png"); _text_banner_frame(banner)
    assert reframe.text_score(sand) < 0.003, "밝은 모래가 텍스트로 오검됨"
    assert reframe.text_score(banner) > reframe.text_score(sand) * 5


def test_pick_windows_excludes_text_frames():
    """텍스트가 박힌 인트로/아웃트로 구간은 점수가 높아도 컷으로 선택되면 안 된다."""
    scores = [100.0] * 50 + [10.0] * 100
    bad = [True] * 50 + [False] * 100
    starts = reframe._pick_windows(scores, 5.0, 5.0, 2, bad=bad)
    assert all(s >= 9.0 for s in starts), f"텍스트 구간이 선택됨: {starts}"


def test_pick_wide_window_excludes_text_frames():
    scores = [100.0] * 50 + [50.0] * 100
    fracs = [0.10] * 150
    bad = [True] * 50 + [False] * 100
    sa = reframe._pick_wide_window(scores, fracs, 5.0, 5.0, bad=bad)
    assert sa >= 9.0, f"텍스트 구간이 와이드 컷으로 선택됨: {sa}"


def test_burned_text_threshold_adapts_to_baseline():
    """기준선(중앙값)이 낮으면 절대 하한 0.006, 높으면 중앙값의 4배."""
    assert reframe._burned_text_threshold([0.001] * 50) == 0.006
    assert abs(reframe._burned_text_threshold([0.005] * 50) - 0.020) < 1e-9


# ─────────────── NOAA 워터마크 대응(2안 회피 + 3안 delogo) ───────────────
BOX = (0.0, 0.0, 0.28, 0.15)   # 좌상단 로고(비율)


def test_logo_avoid_shifts_right_when_subject_allows():
    """(2안) 크롭이 로고와 겹치고 피사체가 오른쪽에 있으면 크롭을 밀어 회피한다."""
    cx, cy, dl = reframe._logo_avoid(200, 0, 404, 720, 700, 360, 1280, 720, BOX)
    assert not dl
    assert cx >= 0.28 * 1280                          # 로고 오른쪽으로 이동
    assert 0.08 * 404 <= 700 - cx <= 0.92 * 404       # 피사체는 화면 안 유지


def test_logo_avoid_falls_back_to_delogo_when_unavoidable():
    """(3안) 피사체가 로고 바로 옆이라 밀 수 없으면 delogo 보완으로 표시한다."""
    cx, cy, dl = reframe._logo_avoid(0, 0, 404, 720, 100, 60, 1280, 720, BOX)
    assert dl and (cx, cy) == (0, 0)


def test_logo_avoid_noop_when_not_overlapping():
    assert reframe._logo_avoid(500, 0, 404, 720, 700, 360, 1280, 720, BOX) == (500, 0, False)


def test_delogo_vf_within_bounds():
    vf = reframe.delogo_vf(1280, 720, BOX)
    assert vf.startswith("delogo=x=1:y=1:w=") and ":h=" in vf
