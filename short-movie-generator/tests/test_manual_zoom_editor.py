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
def test_cut_specs_accepts_box():
    """컷별 JSON의 사각형(줌+가로+세로)이 plan까지 그대로 전달돼야 한다."""
    specs = json.dumps([{"start": 0, "end": 6, "zoom": 1.8, "crop_x": 0.5, "crop_y": 0.3},
                        {"start": 20, "end": 26}])
    plan = reframe._parse_cut_specs(specs, src_dur=60.0, target_dur=12.0)
    assert plan and len(plan) == 2
    assert plan[0]["zoom"] == 1.8 and plan[0]["crop_x"] == 0.5 and plan[0]["crop_y"] == 0.3
    assert plan[1]["zoom"] is None and plan[1]["crop_y"] is None   # 지정 안 한 컷은 자동


def test_cuts_keep_exact_windows():
    """★운영자가 자른 구간을 **정확히** 쓴다(운영자 확정 · 절대 회귀 금지).
    예전엔 지정 길이를 비율로만 쓰고 본문 길이에 맞춰 늘려, 2~8초를 골라도 2~17초가 나갔다."""
    specs = json.dumps([{"start": 2, "end": 8}, {"start": 12, "end": 18}])
    # ① 합(12초) = 본문(12초) → 지정 그대로 2컷
    p12 = reframe._parse_cut_specs(specs, src_dur=120.0, target_dur=12.0)
    assert [(round(c["start"], 1), round(c["len"], 1)) for c in p12] == [(2.0, 6.0), (12.0, 6.0)]
    # ② 본문이 더 길면 **지정 컷을 반복**해 채운다(지정 밖 장면은 절대 안 나온다)
    p30 = reframe._parse_cut_specs(specs, src_dur=120.0, target_dur=30.0)
    assert abs(sum(c["len"] for c in p30) - 30.0) < 0.05
    for c in p30:
        assert c["start"] in (2.0, 12.0), f"지정하지 않은 시작점이 나왔습니다: {c['start']}"
        assert c["len"] <= 6.01, f"컷이 지정 길이보다 늘어났습니다: {c['len']}"
    # ③ 본문이 더 짧으면 마지막 컷을 잘라 정확히 맞춘다
    p9 = reframe._parse_cut_specs(specs, src_dur=120.0, target_dur=9.0)
    assert abs(sum(c["len"] for c in p9) - 9.0) < 0.05


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


def test_editor_is_box_based_and_per_cut(worker):
    """★운영자 확정: 줌·크롭을 따로 고르지 않고 **9:16 사각형 하나**로 합치고, **컷마다 개별** 지정.
    구간은 ①원본 재생 중 '여기 시작/여기 끝' ②프레임 사진 탭 — 어느 쪽이든 **입력칸에 초가 보여야**
    한다(운영자 지적: 눌러도 칸이 안 채워졌다)."""
    start = worker.index("function cutEditorHTML(")
    body = worker[start:worker.index("// ★칸이 곧 값이다")]
    assert "data-mk=" in body, "'여기 시작/여기 끝' 버튼이 없습니다"
    assert "여기 시작" in body and "여기 끝" in body
    assert "placeholder=\"시작(초)\"" in body and "placeholder=\"끝(초)\"" in body, "시작·끝 입력칸이 없습니다"
    assert "data-cesel=" in body, "컷별 '잘라낼 곳' 선택이 없습니다(컷마다 개별 지정 불가)"
    assert "strip" in body and "사진" in body, "프레임 사진 스트립이 없습니다"
    assert "box" in body and "stage" in body, "크롭 사각형이 없습니다"


def test_marker_buttons_fill_the_visible_inputs(worker):
    """★실사고 회귀 금지: 버튼을 눌러도 칸이 비어 있던 문제.
    시작·끝 값은 **입력칸(ceVal/ceSet)** 에만 담고, 버튼 핸들러가 그 칸을 채워야 한다."""
    assert "function ceVal(" in worker and "function ceSet(" in worker
    start = worker.index("function bindCutEditor(")
    body = worker[start:worker.index("// extra = 편집 패널이 만든")]
    assert "[data-mk^='" in body, "버튼 핸들러 배선이 없습니다"
    assert "ceSet(pfx,i,f,t)" in body, "버튼이 입력칸을 채우지 않습니다"
    assert "v.currentTime" in body, "재생 위치를 읽지 않습니다"
    # 값은 상태가 아니라 칸에서 읽는다(칸이 비어 보이는데 값이 들어간 척하는 일 방지)
    inp = worker[worker.index("function cutEditorInputs("):worker.index("function bindCutEditor(")]
    assert 'ceVal(pfx,i,"a")' in inp and 'ceVal(pfx,i,"b")' in inp


def test_editor_shows_required_total_seconds(worker):
    """★운영자 확정: "구간을 반복해 채우지 말고 **총 몇 초가 필요한지** 알려주면 내가 그만큼 고른다."
    → 본문 길이(레코드 body_dur)와 지금 고른 합·부족분을 항상 보여준다."""
    assert "'need'" in worker or '"need"' in worker
    assert "필요한 총 길이" in worker, "필요한 총 길이 안내가 없습니다"
    assert "초 부족" in worker and "지금 고른 합" in worker
    assert "rec.body_dur" in worker, "레코드의 본문 길이를 읽지 않습니다"


def test_editor_card_is_full_width_on_mobile(worker):
    """★아이폰 최적화(운영자 지적 "너무 좁게 표현된다"): 편집 카드가 2열 그리드 안에서 절반 폭으로
    찌그러져 한글이 세로로 쪼개졌다 → 전체 폭(grid-column:1/-1) + 터치 44px 이상."""
    i = worker.index('id="nvcutbox"')
    assert "grid-column:1/-1" in worker[i - 120:i + 160], "나레이션형 편집 카드가 전체 폭이 아닙니다"
    assert "min-height:44px" in worker, "터치 타깃(44px 이상)이 없습니다"
    assert "white-space:nowrap" in worker, "버튼 글자가 세로로 쪼개지는 것을 막지 않았습니다"


def test_editor_inputs_are_per_cut_boxes(worker):
    """각 컷의 사각형이 zoom·crop_x·crop_y로 변환돼 cut_specs에 담겨야 한다."""
    start = worker.index("function cutEditorInputs(")
    body = worker[start:worker.index("function bindCutEditor(")]
    for token in ("zoom:", "crop_x:", "crop_y:", "cut_specs"):
        assert token in body, f"변환 누락: {token}"


def test_regen_forwards_extra_inputs(worker):
    """★도감형 재생성이 편집값을 실제로 워크플로에 넘겨야 한다(예전엔 아예 안 넘겨서 늘 자동)."""
    assert "async function regen(id,scope,extra)" in worker
    assert "Object.assign({content_id:id,scope:scope,visualizer:viz},extra||{})" in worker
    assert "async function regenNarrate(id,sourceUrl,mode,extra)" in worker


def test_editor_uses_frame_sheet_not_playback(worker):
    """★재생 대신 **프레임 사진 시트**를 쓴다(운영자 확정).
    원본 15/17종이 WebM이라 아이폰에서 재생이 안 돼, 재생 위치를 읽는 방식은 늘 0초였다."""
    assert "ref.sheet" in worker or "ref&&ref.sheet" in worker, "소싱이 만든 시트를 읽지 않습니다"
    assert "md.sheet" in worker, "나레이션형 레코드의 시트를 읽지 않습니다"
    assert "ceLoadSheet" in worker


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


# ── ★렌더 검증(운영자 지적 "메뉴가 아예 없다" 재발방지) ──────────────────────
def test_editor_is_not_collapsed(worker):
    """접힌 <details>로 두면 모바일에서 한 줄만 보여 '메뉴가 없다'고 느낀다(실제로 그랬다).
    → 편집 패널은 **항상 펼쳐진 카드**여야 하고, 버튼 그리드에도 진입 버튼이 있어야 한다."""
    assert '<details class="tok" id="cutbox"' not in worker, "도감형 편집 패널이 다시 접혔습니다"
    assert '<details class="tok" id="nvcutbox"' not in worker, "나레이션형 편집 패널이 다시 접혔습니다"
    assert 'id="bcut"' in worker, "버튼 그리드에 '구간·줌 직접 지정' 진입 버튼이 없습니다"
    assert 'id="cutbox"' in worker and 'id="nvcutbox"' in worker


def test_build_stamp_shown(worker):
    """화면 하단 빌드 표시 — '안 바뀌었다'가 배포 문제인지 화면 캐시인지 즉시 구분하기 위함."""
    assert "const BUILD=" in worker
    assert "insertAdjacentHTML(\"beforeend\"" in worker or "BUILD+" in worker


def test_detail_render_checker_exists():
    """소스에 코드가 있는 것과 **실제로 렌더되는 것**은 다르다 → 렌더 검사기를 유지한다.
    (실행: node worker/detail_render_check.mjs)"""
    chk = Path(__file__).resolve().parents[1] / "worker" / "detail_render_check.mjs"
    assert chk.exists(), "상세 렌더 검사기가 없습니다"
    body = chk.read_text(encoding="utf-8")
    assert "renderDetail" in body and "구간·줌 직접 지정" in body
    # ★렌더만 보면 '눌러도 안 채워지는' 사고를 못 잡는다 → 버튼 클릭까지 흉내 내는지 확인
    assert "onclick()" in body and "컷1 시작 칸" in body, "버튼 동작 검사가 빠졌습니다"
