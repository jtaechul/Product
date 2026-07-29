"""★delogo는 '진짜 로고·번인 문구'에만 — 바다·생물이 뭉개지면 안 된다(운영자 확정 · 회귀 금지).

실사고(운영자 지적): "글씨가 글씨가 아닌데 자꾸 delogo가 적용돼서 일반 바다나 해양 생물들이
  자꾸 왜곡돼서 표현되고 있어."

원인(운영자 실제 원본 87.3초로 실측):
  ① OCR이 수중 질감을 글자로 **지어낸다** — 화면 정중앙을 'blue'(신뢰도 96) · 'eat'(59)로 읽었다.
  ② `_NOAAISH`의 느슨한 조각(OCEAN·RATION·OFFICE…)에 한 번만 걸려도 **지속성 검사 없이** 박스가 생겼고,
     박스의 **위치·크기 제한이 전혀 없어** 화면 한가운데 큰 영역도 그대로 delogo 됐다.

조치(이 테스트가 지키는 계약):
  ⓐ 지속성 면제는 **확실한 토큰**(NOAA·OKEANOS·.GOV)만 — 느슨한 조각은 반복될 때만
  ⓑ 그 외 단어는 스캔 프레임의 70% 이상 같은 자리에 반복될 때만
  ⓒ OCR 신뢰도 하한 70
  ⓓ 마지막 관문 `filter_logo_boxes` — 중앙·큰 박스 제거 + 총면적 10% 초과 시 **전부 취소**(원본 보존)
"""
from pathlib import Path

import pytest

from src.core import watermark_qc as WQ

ROOT = Path(__file__).resolve().parents[1]


# ──────────────────────────────────────────────────────────────
# 1) 박스 한 개 판정: 중앙·큰 것은 그림, 가장자리 작은 띠만 로고
# ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,box", [
    ("화면 정중앙 오인('blue')", (0.42, 0.46, 0.16, 0.07)),
    ("중앙 큰 영역", (0.20, 0.30, 0.60, 0.40)),
    ("가장자리지만 너무 큼(그림)", (0.00, 0.00, 0.30, 0.30)),
    ("티끌 잡음", (0.02, 0.90, 0.005, 0.01)),
])
def test_center_or_big_boxes_are_never_delogoed(name, box):
    assert WQ.plausible_logo_box(box) is False, f"{name}: 그림인데 delogo 대상이 되었습니다"


@pytest.mark.parametrize("name,box", [
    ("좌상단 로고", (0.03, 0.04, 0.14, 0.06)),
    ("좌하단 로고", (0.04, 0.88, 0.12, 0.05)),
    ("하단 중앙 번인 URL", (0.30, 0.90, 0.40, 0.045)),
    ("우상단 로고", (0.84, 0.03, 0.13, 0.05)),
])
def test_real_logo_places_are_kept(name, box):
    assert WQ.plausible_logo_box(box) is True, f"{name}: 진짜 로고 자리인데 제외되었습니다"


def test_total_area_blowup_cancels_everything():
    """오탐이 터졌을 땐(총면적 상한 초과) **원본을 그대로 둔다** — 뭉개진 영상보다 낫다."""
    many = [(0.01, 0.02 + i * 0.06, 0.25, 0.06) for i in range(9)]   # 각 1.5% × 9 ≈ 13.5%
    assert sum(b[2] * b[3] for b in many) > WQ._LOGO_TOTAL_MAX
    assert WQ.filter_logo_boxes(many, where="test") == []
    # 상한 안쪽이면 정상 통과
    ok = [(0.03, 0.90, 0.12, 0.05)]
    assert WQ.filter_logo_boxes(ok, where="test") == ok


# ──────────────────────────────────────────────────────────────
# 2) 실제 판정 경로: 지어낸 중앙 글자 vs 구석에 늘 붙어 있는 로고
# ──────────────────────────────────────────────────────────────
def _word(text, x, y, w, h, conf=95):
    return {"text": text, "x": x, "y": y, "w": w, "h": h, "conf": conf}


def _fake_scan(per_second_words):
    def scan(video, start, dur, fps=1.0, **kw):   # noqa: ARG001
        return [{"t": float(i), "words": list(ws)} for i, ws in enumerate(per_second_words)]
    return scan


def test_hallucinated_center_words_do_not_produce_delogo(monkeypatch):
    """글자 없는 바다 영상: OCR이 정중앙을 'blue'/'eat'로 지어내도 delogo 박스는 **0개**."""
    from src.core import narrate_attached as NA

    frames = []
    for i in range(12):
        ws = []
        if i % 3 == 0:                      # 산발적으로만 나타나는(=지속성 없는) 오인
            ws.append(_word("blue", 0.44, 0.47, 0.12, 0.06, conf=96))
        if i % 5 == 0:
            ws.append(_word("eat", 0.51, 0.52, 0.08, 0.05, conf=59))
        frames.append(ws)
    monkeypatch.setattr(WQ, "scan", _fake_scan(frames))

    assert NA._watermark_boxes("dummy.mp4", 12.0) == [], \
        "글씨가 아닌 곳(수중 질감 오인)에 delogo가 걸렸습니다 — 바다·생물이 왜곡됩니다"


def test_persistent_corner_logo_is_removed(monkeypatch):
    """구석에 **늘** 붙어 있는 로고는 정상적으로 delogo 대상이 된다(기능 자체는 살아 있어야 함)."""
    from src.core import narrate_attached as NA

    frames = [[_word("NOAA", 0.04, 0.90, 0.10, 0.04, conf=92)] for _ in range(12)]
    monkeypatch.setattr(WQ, "scan", _fake_scan(frames))

    boxes = NA._watermark_boxes("dummy.mp4", 12.0)
    assert len(boxes) == 1, f"구석 로고를 못 지웁니다: {boxes}"
    x, y, w, h = boxes[0]
    assert x + w / 2 < WQ._LOGO_EDGE_X and y + h / 2 > WQ._LOGO_EDGE_Y2, "로고 자리가 아닙니다"
    assert w * h < WQ._LOGO_MAX_AREA


def test_loose_fragment_alone_is_not_enough(monkeypatch):
    """느슨한 조각(OCEAN·RATION…)이 **한두 번** 보인 정도로는 delogo 하지 않는다(구멍 ②)."""
    from src.core import narrate_attached as NA

    frames = [[] for _ in range(12)]
    frames[2] = [_word("ocean", 0.40, 0.45, 0.14, 0.06, conf=88)]   # 중앙 · 1회
    monkeypatch.setattr(WQ, "scan", _fake_scan(frames))

    assert NA._watermark_boxes("dummy.mp4", 12.0) == [], \
        "느슨한 조각 한 번에 delogo가 걸립니다(예전 구멍이 되살아났습니다)"


# ──────────────────────────────────────────────────────────────
# 3) 소스 계약(회귀 방지)
# ──────────────────────────────────────────────────────────────
def test_source_contract():
    na = (ROOT / "src" / "core" / "narrate_attached.py").read_text(encoding="utf-8")
    wq = (ROOT / "src" / "core" / "watermark_qc.py").read_text(encoding="utf-8")

    from src.core import narrate_attached as NA
    assert NA._WM_MIN_CONF >= 70, "OCR 신뢰도 하한이 낮아지면 수중 질감 오인이 다시 들어옵니다"
    assert NA._WM_PERSIST >= 0.70, "지속성 요구가 낮아지면 오탐이 다시 늘어납니다"

    assert "wq._STRONG_LOGO_RE.search" in na, \
        "지속성 면제에 느슨한 조각(_NOAAISH)을 다시 쓰면 안 됩니다"
    assert "wq._NOAAISH" not in na, "느슨한 조각으로 지속성을 면제하던 경로가 되살아났습니다"
    assert 'filter_logo_boxes(wq._merge_boxes(raw), where="narrate")' in na, \
        "마지막 관문(중앙·큰 박스 제거)이 빠졌습니다"
    assert 'filter_logo_boxes(_merge_boxes(raw), where="plan")' in wq, \
        "plan() 경로에도 같은 관문이 있어야 합니다"
    assert "_STRONG_LOGO_RE.search(w0[\"text\"]) or counts.get" in wq, \
        "plan()의 지속성 면제도 확실한 토큰만이어야 합니다"
