"""릴스 4대 개선 회귀 테스트(네트워크 불필요, 결정론):
  ② 캡션 최소 분량 보장(폴백도 리치)
  문제점2 피사체 검출 일반화(색 무관 — 창백한 주인공도 잡힘) + 단일/다수 판별
"""
from PIL import Image

from src.core import reframe as R
from src.core import rich_caption as RC
from src.core.contracts import SpeciesInfo


# ── ② 캡션 최소 분량 ──────────────────────────────────────────
def test_fallback_caption_meets_floor_even_when_sparse():
    sparse = SpeciesInfo(scientific_name="Rimicaris exoculata", common_name_ko="열수분출공새우",
                         common_name_en="vent shrimp", depth_range_m="", distribution="",
                         habitat="", diet=[], fun_facts=["熱水噴出孔に群れる。"], sources=["Wikipedia"])
    d = RC._fallback(sparse, "ネッスイエビ", "Rimicaris exoculata", "変わった生き物",
                     "ふしぎ", "な深海エビ", "", "", "NOAA", ["#深海", "#ネッスイエビ", "#生き物"])
    assert len(d["jp"]) >= RC._CAPTION_FLOOR, "일본어 캡션이 바닥 분량 미만"
    assert len(d["ko"]) >= RC._CAPTION_FLOOR, "한국어 캡션이 바닥 분량 미만"


def test_evergreen_is_deterministic_and_varies_by_seed():
    a = RC._evergreen("Rimicaris exoculata", ko=False, n=2)
    assert a == RC._evergreen("Rimicaris exoculata", ko=False, n=2)   # 결정론
    b = RC._evergreen("Bathynomus giganteus", ko=False, n=2)
    assert a != b or len(RC._EVERGREEN_JP) <= 2                        # 종마다 다른 조합


# ── 문제점2: 피사체 검출 일반화 ───────────────────────────────
def _frame(path, draw_creature, pale=True):
    """어두운 배경 + (옵션) 밝은/창백한 피사체 덩어리 한 개."""
    im = Image.new("RGB", (480, 270), (18, 26, 34))    # 어두운 심해 배경
    if draw_creature:
        from PIL import ImageDraw
        d = ImageDraw.Draw(im)
        col = (225, 228, 220) if pale else (210, 40, 30)   # 창백(흰) 또는 붉은 생물
        # 미세구조(팔·촉수) 흉내: 방사형 밝은 선
        cx, cy = 300, 150
        for ang in range(0, 360, 20):
            import math
            x2 = cx + int(60 * math.cos(math.radians(ang)))
            y2 = cy + int(60 * math.sin(math.radians(ang)))
            d.line([cx, cy, x2, y2], fill=col, width=3)
        d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=col)
    im.save(path)


def test_pale_creature_is_detected(tmp_path):
    """창백한(흰) 피사체도 신호가 잡혀야 한다(예전 적색전용 검출은 0이었음)."""
    f = str(tmp_path / "pale.jpg")
    _frame(f, draw_creature=True, pale=True)
    assert R.subject_score(f) > 0, "창백한 피사체가 검출되지 않음(색 무관 일반화 실패)"
    cx, cy = R._subject_centroid(f)
    assert cx > 0.5, "무게중심이 피사체(우측) 쪽이어야"


def test_empty_background_scores_lower_than_creature(tmp_path):
    """피사체 없는 빈 배경은 피사체 프레임보다 점수가 낮아야(컷 선택이 빈 배경 회피)."""
    fc = str(tmp_path / "c.jpg"); fe = str(tmp_path / "e.jpg")
    _frame(fc, draw_creature=True, pale=True)
    _frame(fe, draw_creature=False)
    assert R.subject_score(fc) > R.subject_score(fe)


def test_focus_reports_spread(tmp_path):
    f = str(tmp_path / "one.jpg")
    _frame(f, draw_creature=True, pale=True)
    fx, fy, spread = R._subject_focus(f)
    assert 0.0 <= spread <= 1.0
    assert fx > 0.5   # 단일 피사체 → 그 덩어리(우측) 중심
