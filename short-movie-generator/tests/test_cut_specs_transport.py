"""컷 설정이 대시보드 → 워크플로 → 제작까지 **망가지지 않고** 도착하는지(전달 계약).

★실사고(운영자 확정 · 절대 회귀 금지): 표지는 반영됐는데 구간은 무시된 영상이 나왔다.
  원인은 워크플로가 컷 JSON을 **큰따옴표 안에 직접 치환**한 것 —
      --cut-specs "${{ inputs.cut_specs }}"      ← 셸이 JSON 안의 큰따옴표를 먹는다
      --cover     '${{ inputs.cover }}'          ← 작은따옴표라 표지만 멀쩡히 도착
  도착한 값은 `[{start:1.2,...}]`(따옴표 소실)이라 해석 실패 → 조용히 자동 컷으로 폴백.
→ 이제 지정값은 **환경변수**로 넘기고(셸 재해석 없음), 파서는 망가진 표기도 복원하며,
  그래도 안 되면 **제작을 멈춘다**(조용한 폴백 금지).
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from src.core import reframe

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT.parent / ".github" / "workflows" / "narrate-video.yml"


def _wf() -> str:
    return WF.read_text(encoding="utf-8")


def _wf_code() -> str:
    """주석(#)을 뺀 실행부만 — 주석에는 '나쁜 예'가 설명용으로 들어 있다."""
    return "\n".join(ln for ln in _wf().splitlines() if not ln.lstrip().startswith("#"))


def test_workflow_never_interpolates_settings_inside_quotes():
    """★핵심 회귀: 지정값을 셸 인용부호 안에 직접 치환하면 안 된다(따옴표 소실 사고)."""
    src = _wf_code()
    for key in ("cut_specs", "cover", "crop_x", "cuts", "zoom", "video_url", "transcript"):
        bad = re.search(r"""["']\$\{\{\s*inputs\.%s\s*\}\}["']""" % key, src)
        assert not bad, (
            f"inputs.{key} 를 셸 인용부호 안에 직접 치환하고 있습니다 — "
            "JSON 따옴표가 소실돼 지정이 무시됩니다. env: 로 넘기고 \"$IN_...\" 로 쓰세요.")


def test_reels_workflow_also_uses_env():
    """도감형(generate-short.yml)도 같은 규칙 — 값 안 따옴표가 소실되면 안 된다."""
    src = "\n".join(ln for ln in (ROOT.parent / ".github" / "workflows" / "generate-short.yml")
                    .read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
    for key in ("cut_specs", "video_url", "video_title", "video_credit"):
        assert not re.search(r"""["']\$\{\{\s*inputs\.%s\s*\}\}["']""" % key, src), \
            f"generate-short.yml이 inputs.{key} 를 셸 인용부호 안에 치환합니다"
    assert 'IN_CUT_SPECS:' in src and 'CUT_SPECS="$IN_CUT_SPECS"' in src


def test_workflow_passes_settings_through_env():
    src = _wf()
    for env_key in ("IN_CUT_SPECS:", "IN_COVER:"):
        assert env_key in src, f"워크플로가 지정값을 env로 넘기지 않습니다: {env_key}"
    assert '--cut-specs "$IN_CUT_SPECS"' in src
    assert '--cover "$IN_COVER"' in src


def test_shell_round_trip_keeps_json_intact():
    """실제 셸로 굴려 값이 그대로 도착하는지 확인한다(재현 테스트)."""
    payload = json.dumps([{"start": 1.2, "end": 8.4, "zoom": 1.67,
                           "crop_x": 0.5, "crop_y": 0.5}])
    # 지금 방식(env 경유)
    good = subprocess.run(["bash", "-c", 'printf %s "$IN_CUT_SPECS"'],
                          env={"IN_CUT_SPECS": payload, "PATH": "/usr/bin:/bin"},
                          capture_output=True, text=True, check=True).stdout
    assert json.loads(good) == json.loads(payload)
    # 옛 방식(큰따옴표 안 치환)이 실제로 값을 망가뜨린다 — 이 테스트가 사고를 설명한다
    broken = subprocess.run(["bash", "-c", f'printf %s "{payload}"'],
                            capture_output=True, text=True, check=True).stdout
    assert broken != payload and '"start"' not in broken


def test_parser_recovers_the_broken_form_anyway():
    """전달을 고쳤어도, 옛 회차·수동 입력으로 망가진 값이 오면 복원해 해석한다(2중 방어)."""
    broken = "[{start:1.2,end:8.4,zoom:1.67,crop_x:0.5,crop_y:0.5}]"
    plan = reframe._parse_cut_specs(broken, src_dur=60.0, target_dur=14.4)
    assert plan and plan[0]["start"] == pytest.approx(1.2)


def test_unparseable_stops_production():
    """복원도 실패하면 자동으로 넘어가지 않고 멈춘다(운영자가 원인을 알 수 있게)."""
    with pytest.raises(reframe.CutSpecError):
        reframe._parse_cut_specs("완전히 이상한 값", src_dur=60.0, target_dur=30.0)


def test_applied_settings_are_recorded_and_shown():
    """★운영자 확정: '내 설정이 정말 반영됐는지'를 상세 화면에서 눈으로 확인한다.

    지정값(edit)이 아니라 **실제 렌더에 쓰인 값(applied)** 을 남겨야 이번 같은 전달 사고를
    화면에서 구분할 수 있다."""
    rf = (ROOT / "src" / "core" / "reframe.py").read_text(encoding="utf-8")
    assert "applied_cuts.json" in rf, "실제 적용된 컷 목록을 남기지 않습니다"
    na = (ROOT / "src" / "core" / "narrate_attached.py").read_text(encoding="utf-8")
    assert 'meta["applied"] = applied' in na, "제작이 적용 내역을 메타에 남기지 않습니다"
    cs = (ROOT / "src" / "core" / "content_store.py").read_text(encoding="utf-8")
    assert 'rec["applied"] = meta["applied"]' in cs, "레코드에 적용 내역이 저장되지 않습니다"
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "function appliedSummaryHTML(" in w and "실제로 반영된 설정" in w, "화면에 적용 내역이 없습니다"


def test_edit_menus_are_one_card_in_order():
    """★운영자 지적: 표지·구간·실행 메뉴가 멀리 떨어져 불편했다 → 한 카드 1·2·3단계."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "function editStudioHTML(" in w, "통합 편집 카드가 없습니다"
    i = w.index("function editStudioHTML(")
    seg = w[i:i + 1400]
    for token, label in (("coverEditorHTML()", "1단계 표지"),
                         ('id="nvcutbox"', "2단계 구간"),
                         ("applyEditsHTML(", "3단계 실행")):
        assert token in seg, f"통합 카드에 {label}가 없습니다"
    assert seg.index("coverEditorHTML()") < seg.index('id="nvcutbox"') < seg.index("applyEditsHTML("), \
        "표지 → 구간 → 실행 순서가 아닙니다(실행 버튼이 설정보다 위에 오면 안 됩니다)"
    # 관리 버튼 그리드 안에 컷 카드를 다시 넣지 않는다(멀리 떨어지는 원인)
    assert w.count('id="nvcutbox"') == 1


def test_summary_refreshes_on_programmatic_fill():
    """★사진 띠 탭·복원처럼 **코드가 칸을 채울 때도** 요약이 갱신돼야 한다.
    (예전엔 입력칸 oninput에만 걸려 있어 '표지만 잡힌 것처럼' 보였다)"""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "function editChanged(" in w
    i = w.index("function ceRender(")
    assert "editChanged()" in w[i:i + 900], "컷 합계 갱신 시 요약이 따라가지 않습니다"
    j = w.index("function cvDraw(")
    assert "editChanged()" in w[j:j + 1200], "표지 갱신 시 요약이 따라가지 않습니다"
