"""v2 관리자 페이지 규칙(운영자 확정 2026-09-27) 회귀 테스트.

- 단계 5개 · 승인 관문 4개(대본·스토리보드·완성본·업로드 전 확인). 앞 단계 승인 전에는 다음 단계가 잠긴다.
- 승인은 결과가 나온 뒤(승인 대기)에만. 수정 요청·다시 하기는 뒤 단계를 다시 잠근다.
- 새 편은 주제 후보(topics.json)에 있는 종만 시작할 수 있다.
- 화면: 메뉴 두 개('영상 목록'·'새 영상')만, 예전 화면은 /legacy 등으로 보존(worker/v2_admin_check.mjs).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v2" / "tools"))
import admin  # noqa: E402


@pytest.fixture()
def v2(tmp_path, monkeypatch):
    pilots = tmp_path / "pilots"
    pilots.mkdir()
    (tmp_path / "topics.json").write_text(json.dumps({"topics": [
        {"id": "test_fish", "name_ko": "시험어", "sci": "Testus fishus", "ready": True}]}), encoding="utf-8")
    monkeypatch.setattr(admin, "V2", tmp_path)
    monkeypatch.setattr(admin, "PILOTS", pilots)
    return tmp_path


def states(pid):
    st = admin.load_status(pid)
    return [st["stages"][s]["state"] for s in admin.STAGES]


def test_new_pilot_starts_at_script_with_later_stages_locked(v2):
    admin.new_pilot("test_fish")
    assert states("test_fish") == ["approved", "working", "locked", "locked", "locked"]
    idx = json.loads((v2 / "pilots" / "index.json").read_text(encoding="utf-8"))
    assert idx["items"][0]["id"] == "test_fish" and idx["items"][0]["stage"] == "script"


def test_unknown_topic_cannot_start(v2):
    with pytest.raises(SystemExit):
        admin.new_pilot("not_a_topic")


def test_approve_only_when_review_and_unlocks_next(v2):
    admin.new_pilot("test_fish")
    with pytest.raises(SystemExit):                       # 작업 중(결과 없음)엔 승인 불가
        admin.approve("test_fish", "script")
    with pytest.raises(SystemExit):                       # 잠긴 단계 승인 불가
        admin.approve("test_fish", "video")
    admin.main(["ready", "test_fish", "script", "대본 완료"])
    admin.approve("test_fish", "script")
    assert states("test_fish") == ["approved", "approved", "working", "locked", "locked"]


def test_revise_relocks_later_stages(v2):
    admin.new_pilot("test_fish")
    for s in ("script", "storyboard"):
        admin.main(["ready", "test_fish", s])
        admin.approve("test_fish", s)
    assert states("test_fish")[3] == "working"
    admin.revise("test_fish", "script", "2번 컷 대사를 더 쉽게")
    assert states("test_fish") == ["approved", "revise", "locked", "locked", "locked"]
    notes = admin.load_status("test_fish")["stages"]["script"]["notes"]
    assert notes[-1]["text"] == "2번 컷 대사를 더 쉽게"


def test_revise_needs_a_note(v2):
    admin.new_pilot("test_fish")
    with pytest.raises(SystemExit):
        admin.main(["revise", "test_fish", "script"])


def test_bad_pilot_id_is_rejected(v2):
    with pytest.raises(SystemExit):
        admin.status_path("../etc")


def test_real_pilot_status_is_consistent():
    """시범 편 status.json: 대본·스토리보드 승인 · 완성본 승인 대기 · 업로드 잠김 · 자동 검사 통과."""
    st = json.loads((ROOT / "v2" / "pilots" / "bathynomus_giganteus" / "status.json").read_text(encoding="utf-8"))
    assert [st["stages"][s]["state"] for s in admin.STAGES] == ["approved", "approved", "approved", "review", "locked"]
    assert st["checks"]["white_edge_px"]["ok"] and st["checks"]["loudness_lufs"]["ok"]
    for c in st["artifacts"]["video"]["clips"]:
        assert (ROOT / "v2" / "pilots" / "bathynomus_giganteus" / c["file"]).exists()


@pytest.mark.skipif(not shutil.which("node"), reason="node 없음")
def test_admin_pages_render_and_buttons_dispatch():
    out = subprocess.run(["node", str(ROOT / "worker" / "v2_admin_check.mjs")], capture_output=True, text=True,
                         timeout=120)
    r = json.loads(out.stdout)
    assert r["nav_two_menus"] and r["list_has_pilot"] and r["episode_five_stages"]
    assert r["locked_upload_has_no_buttons"] and r["video_approve_enabled"] and r["approved_script_approve_disabled"]
    assert r["clip_redo_buttons"] == 8 and r["new_lists_ready_topics"] > 0 and r["new_hides_in_progress"]
    assert r["legacy_home_renders"] and r["video_final_via_proxy"]
    acts = [(d["wf"], d["action"], d["pilot"], d["stage"]) for d in r["dispatches"]]
    assert ("v2-admin.yml", "approve", "bathynomus_giganteus", "video") in acts
    assert ("v2-admin.yml", "redo_cut", "bathynomus_giganteus", "1") in acts
