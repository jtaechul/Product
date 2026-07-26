"""운영자 수동 구간·줌 편집 — 백엔드(줌 배율)와 대시보드 편집 메뉴 회귀 테스트.

운영자 확정(강한 요구): "영상 구간이랑 줌 범위 정하는 건 내가 직접 하겠다.
자동으로만 만들어져 나오면 안 된다 — 관리자 페이지에 **내가 수정할 수 있는 메뉴**를 만들어라."

확정 설계:
  · 제작은 지금처럼 자동으로 하되, **결과 상세 페이지에 '구간·줌 다시 잡기' 메뉴**를 둔다.
  · 조절 항목 = 컷별 구간 + 크롭 가로위치 + **줌 배율** + 컷 수.
  · 고쳐서 다시 만들면 **같은 회차에 덮어쓴다**.
  · 원본 미리보기 mp4는 **소싱할 때 미리** 만들어 둔다(아이폰이 WebM을 재생 못 하므로).
"""
import json
import re
from pathlib import Path

import pytest

from src.core import reframe

_WORKER = Path(__file__).resolve().parents[1] / "worker" / "index.mjs"


# ── 백엔드: 줌 배율 ───────────────────────────────────────────────────────────
def test_cut_specs_accepts_zoom():
    """컷별 JSON에 zoom을 적으면 plan까지 그대로 전달돼야 한다."""
    specs = json.dumps([{"start": 0, "end": 6, "zoom": 1.8, "crop_x": 0.5},
                        {"start": 20, "end": 27}])
    plan = reframe._parse_cut_specs(specs, src_dur=60.0, target_dur=20.0)
    assert plan and len(plan) == 2
    assert plan[0]["zoom"] == 1.8
    assert plan[0]["crop_x"] == 0.5
    assert plan[1]["zoom"] is None      # 지정 안 한 컷은 자동


@pytest.mark.parametrize("raw", ["", "  ", None])
def test_cut_specs_empty_is_auto(raw):
    assert reframe._parse_cut_specs(raw, src_dur=60.0, target_dur=20.0) is None


def test_zoom_forces_crop_render_and_clamp():
    """★줌을 지정하면 그 컷은 '핏(전체 담기)'이 아니라 크롭 렌더로 가야 배율이 실제로 먹는다.
    또 과확대·축소를 막기 위해 1.0~2.5로 클램프한다(소스 코드 계약 검사)."""
    src = (Path(__file__).resolve().parents[1] / "src" / "core" / "reframe.py").read_text(encoding="utf-8")
    assert 'cut["mode"] = "closeup"' in src, "줌 지정 컷을 크롭 렌더로 강제하는 코드가 없습니다"
    assert "min(2.5, cz)" in src and "max(1.0, min(2.5, cz))" in src, "줌 클램프(1.0~2.5) 누락"
    # 지정 줌이면 자동 보정(점유율·얼굴중앙·여러마리)을 건너뛴다
    assert "줌 배율 운영자 지정" in src


def test_manual_zoom_is_optional():
    """줌을 안 넣으면 기존 자동 동작(하위호환) — manual 딕트가 비어도 예외 없이 통과."""
    assert reframe._f(None) is None
    assert reframe._f("") is None
    assert reframe._f("1.5") == 1.5


# ── 대시보드: 편집 메뉴가 두 상세 페이지에 모두 있는가 ────────────────────────
@pytest.fixture(scope="module")
def worker():
    return _WORKER.read_text(encoding="utf-8")


def test_cut_editor_helpers_exist(worker):
    for fn in ("function cutEditorHTML(", "function cutEditorInputs(", "function bindCutEditor("):
        assert fn in worker, f"공용 편집 패널 함수 누락: {fn}"


def test_editor_on_both_detail_pages(worker):
    """★도감형(/c)에 편집 메뉴가 없어서 '재생성해도 계속 자동'이던 것이 이번 사고의 핵심 원인."""
    assert 'id="cutbox"' in worker, "도감형 상세에 구간·줌 편집 메뉴가 없습니다"
    assert 'id="nvcutbox"' in worker, "나레이션형 상세에 구간·줌 편집 메뉴가 없습니다"
    assert worker.count('cutEditorHTML("') >= 2, "두 상세 페이지가 같은 편집 패널을 써야 합니다"


def test_editor_controls_cover_all_four(worker):
    """조절 항목 4종(구간·크롭·줌·컷수)이 모두 UI에 있어야 한다(운영자 선택)."""
    start = worker.index("function cutEditorHTML(")
    body = worker[start:start + 3000]
    for token in ("시작(초)", "끝(초)", "줌 배율", "크롭 가로 위치", "컷 수"):
        assert token in body, f"편집 항목 누락: {token}"


def test_editor_inputs_are_omitted_when_blank(worker):
    """비워둔 항목은 워크플로 inputs에 넣지 않는다(= 그 항목만 자동)."""
    start = worker.index("function cutEditorInputs(")
    body = worker[start:worker.index("function bindCutEditor(")]
    assert "if(specs.length) inp.cut_specs" in body
    assert "if(zoom) inp.zoom" in body and "if(crop) inp.crop_x" in body


def test_regen_forwards_extra_inputs(worker):
    """★도감형 재생성이 편집값을 실제로 워크플로에 넘겨야 한다(예전엔 아예 안 넘겨서 늘 자동)."""
    assert "async function regen(id,scope,extra)" in worker
    assert "Object.assign({content_id:id,scope:scope,visualizer:viz},extra||{})" in worker
    assert "async function regenNarrate(id,sourceUrl,mode,extra)" in worker


def test_preview_mp4_preferred_for_playback(worker):
    """아이폰에서 WebM이 안 되므로 미리보기 mp4를 첫 후보로 재생해야 한다."""
    assert "preview_url" in worker, "소싱이 만든 미리보기 URL을 쓰지 않습니다"
    assert "md.source_mp4_url" in worker


# ── 워크플로: 편집값이 CLI까지 도달하는가 ────────────────────────────────────
def test_workflows_expose_zoom():
    yaml = pytest.importorskip("yaml")
    root = Path(__file__).resolve().parents[2] / ".github" / "workflows"
    for name in ("generate-short.yml", "narrate-video.yml"):
        d = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        trig = d.get("on") or d.get(True)          # YAML은 'on'을 True로 파싱한다
        inputs = trig["workflow_dispatch"]["inputs"] or {}
        for k in ("zoom", "cut_specs", "crop_x", "cuts"):
            assert k in inputs, f"{name}에 {k} 입력이 없습니다"
        body = (root / name).read_text(encoding="utf-8")
        assert "--zoom" in body, f"{name}이 --zoom 인자를 넘기지 않습니다"


def test_sourcing_makes_preview():
    """미리보기는 '소싱할 때 미리' 만든다(운영자 선택) — 스텝과 캐시 기록이 있어야 한다."""
    wf = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "source-species.yml"
          ).read_text(encoding="utf-8")
    assert "source_preview" in wf and "preview_url" in wf
    assert re.search(r"gh release upload \"\$TAG\" work/preview/\*\.mp4", wf)
