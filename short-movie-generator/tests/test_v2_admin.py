"""v2 관리자 페이지 규칙(운영자 확정 2026-09-27) 회귀 테스트.

- 단계 5개 · 승인 관문 4개(대본·스토리보드·완성본·업로드 전 확인). 앞 단계 승인 전에는 다음 단계가 잠긴다.
- 승인은 결과가 나온 뒤(승인 대기)에만. 수정 요청·다시 하기는 뒤 단계를 다시 잠근다.
- 새 편은 주제 후보(topics.json)에 있는 종만 시작할 수 있다.
- 화면: 메뉴 두 개('영상 목록'·'새 영상')만, 예전 화면은 /legacy 등으로 보존(worker/v2_admin_check.mjs).
"""
import json
import re
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
    n = len(admin.load_status("test_fish")["stages"]["script"]["notes"])
    admin.approve("test_fish", "script")                  # ★두 번 눌러도 실패 아님 · 아무것도 안 바뀜(실사고 2026-10-06)
    assert states("test_fish") == ["approved", "approved", "working", "locked", "locked"]
    assert len(admin.load_status("test_fish")["stages"]["script"]["notes"]) == n


def test_video_approve_lands_before_installs():
    """영상 승인은 키가 필요 없으니 설치 전 첫 단계에서 바로 반영·커밋한다(반영 1.5분 → 약 20초)."""
    wf = (Path(admin.__file__).resolve().parents[3] / ".github/workflows/v2-admin.yml").read_text(encoding="utf-8")
    first = wf[wf.index("진행 중 먼저 기록"):wf.index("- name: 준비")]
    assert 'approve "$IN_PILOT" video' in first and "ci_commit.sh" in first.split('approve "$IN_PILOT" video')[1][:200]


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
    """시범 편 status.json의 불변 규칙: 앞 단계가 승인 전이면 뒤 단계는 잠김 · 자동 검사 통과 · 클립 파일 존재.
    (특정 순간의 단계 상태를 고정으로 적지 않는다 — 운영자가 버튼을 누를 때마다 바뀐다)"""
    st = json.loads((ROOT / "v2" / "pilots" / "bathynomus_giganteus" / "status.json").read_text(encoding="utf-8"))
    states = [st["stages"][s]["state"] for s in admin.STAGES]
    for a, b in zip(states, states[1:]):
        if a != "approved":
            assert b == "locked", states
    assert st["checks"]["white_edge_px"]["ok"] and st["checks"]["loudness_lufs"]["ok"]
    assert st["checks"].get("subtitle_font", {}).get("ok")
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


# ── 컷별 대사 수정(운영자 확정 2026-09-28): 저장은 대본만, 영상은 자동으로 안 바뀐다 ──
REAL = ROOT / "v2" / "pilots" / "bathynomus_giganteus"


def cur_tts() -> str:
    return json.loads((REAL / "status.json").read_text(encoding="utf-8"))["artifacts"]["video"]["assemble"]["tts_id"]


@pytest.fixture()
def real_copy(tmp_path, monkeypatch):
    pilots = tmp_path / "pilots"
    dst = pilots / "bathynomus_giganteus"
    tts = cur_tts()                                         # 지금 완성본이 쓰는 나레이션(반영할 때마다 바뀐다)
    (dst / "out" / tts).mkdir(parents=True)
    (dst / "requests").mkdir()
    for f in ("script.json", "status.json"):
        shutil.copy(REAL / f, dst / f)
    shutil.copy(REAL / "out" / tts / "body_timepoints.json", dst / "out" / tts / "body_timepoints.json")
    st = json.loads((dst / "status.json").read_text(encoding="utf-8"))
    st.get("artifacts", {}).pop("upload", None)             # 실제 편은 이미 업로드됨 — 테스트는 올리기 전 상태에서 시작
    (dst / "status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(admin, "V2", tmp_path)
    monkeypatch.setattr(admin, "PILOTS", pilots)
    return dst


def test_edit_line_changes_script_only(real_copy):
    before = (real_copy / "status.json").read_text(encoding="utf-8")
    st0 = json.loads(before)
    admin.edit_line("bathynomus_giganteus", 3, "大きさは最大50センチ近く。世界最大の仲間です。", "크기는 최대 50cm. 세계 최대입니다.")
    st = admin.load_status("bathynomus_giganteus")
    sc = json.loads((real_copy / "script.json").read_text(encoding="utf-8"))
    c3 = next(c for c in sc["cuts"] if c.get("cut") == 3)
    assert c3["jp"].startswith("大きさは") and c3["pending_edit"] and c3["line_history"][-1]["jp"] != c3["jp"]
    assert "せかいさいだい" in c3["tts"]                             # 읽기 자동 생성(히라가나)
    assert st["artifacts"]["video"] == st0["artifacts"]["video"]      # ★영상 쪽은 그대로
    assert [st["stages"][s]["state"] for s in admin.STAGES] == [st0["stages"][s]["state"] for s in admin.STAGES]
    assert st["artifacts"]["script"]["pending_lines"] == [3]
    assert sc["timing_v5"] == json.loads((REAL / "script.json").read_text(encoding="utf-8"))["timing_v5"]


def test_edit_line_rejects_reading_with_different_chunks(real_copy):
    with pytest.raises(SystemExit):
        admin.edit_line("bathynomus_giganteus", 3, "大きさは最大。世界最大です。", "", "おおきさは さいだい せかいさいだいです。")


def test_timing_unchanged_audio_reproduces_current_cut_times(real_copy):
    sc = json.loads((real_copy / "script.json").read_text(encoding="utf-8"))
    tps = json.loads((real_copy / "out" / cur_tts() / "body_timepoints.json").read_text(encoding="utf-8"))
    timing, problems = admin.plan_timing(sc, tps)
    assert problems == []
    for a, b in zip(timing, sc["timing_v5"]):
        assert abs(a["audio_from"] - b["audio_from"]) < 1e-6 and abs(a["audio_to"] - b["audio_to"]) < 1e-6
        assert a["sec"] == b["sec"]                                      # 컷 길이(영상)는 그대로


def test_apply_stops_without_touching_video_when_line_too_long(real_copy, monkeypatch):
    admin.edit_line("bathynomus_giganteus", 3, "大きさは最大50センチ近く。ダンゴムシの仲間では、世界最大です。")
    tps = json.loads((real_copy / "out" / cur_tts() / "body_timepoints.json").read_text(encoding="utf-8"))
    for t in tps[8:]:                          # 3번 컷(조각 7~9)의 두 번째 조각부터 밀어 3번 컷이 3초 길어졌다고 가정
        t["start"] += 3.0
        t["end"] = (t["end"] or 0) + 3.0

    def fake_run(args, cwd=None):
        req = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        out = real_copy / "out" / req["id"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "body_timepoints.json").write_text(json.dumps(tps), encoding="utf-8")
        (out / "body.wav").write_bytes(b"")
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(admin.subprocess, "run", fake_run)
    called = []
    monkeypatch.setattr(admin, "assemble", lambda pid: called.append(pid))
    st = admin.apply_lines("bathynomus_giganteus")
    sc = json.loads((real_copy / "script.json").read_text(encoding="utf-8"))
    assert called == []                                                  # 재조립 안 함
    assert st["artifacts"]["video"]["assemble"]["tts_id"] == cur_tts()   # 나레이션 교체 안 함
    assert sc["timing_v5"] == json.loads((REAL / "script.json").read_text(encoding="utf-8"))["timing_v5"]
    assert any("3번 컷" in x for x in st["artifacts"]["script"]["apply_blocked"])
    assert not any(n.get("kind") == "redo_cut" for n in st["stages"]["video"]["notes"])   # 컷 재생성 안 함


def test_line_edit_page_buttons():
    out = subprocess.run(["node", str(ROOT / "worker" / "v2_admin_check.mjs")], capture_output=True, text=True,
                         timeout=120)
    r = json.loads(out.stdout)
    assert r["line_edit_buttons"] == 8 and r["line_save_says_video_unchanged"]
    assert r["no_apply_button_without_edits"] and r["pending_shows_apply_and_asm"]
    assert r["edit_does_not_touch_video"] and r["edit_dispatch"][0]["action"] == "edit_line"
    assert r["fact_text_per_cut"] >= 8 and r["crosscheck_button"]
    assert r["flag_shown"] and r["suggestion_fills_editor"]
    assert r["recut_open_buttons"] == 8 and r["recut_review_shown"]
    assert r["recut_plan_dispatch"][0]["action"] == "recut_plan" and r["recut_plan_dispatch"][0]["note"]["min_transitions"] == 2
    assert r["recut_approve_dispatch"] == ["recut_approve:8"]
    assert r["upload_fields"] and r["upload_no_revise_box"]
    assert r["download_buttons"] == 2 and r["download_fetches_final"]         # 완성본 저장(영상·업로드 카드)
    assert r["after_upload_copy_boxes"] and r["copy_button_copies_description"]   # 업로드 뒤에도 복사 가능
    assert r["upload_sends_screen_values"]                                        # 저장 안 눌러도 화면 값 그대로


# ── 검증 ①② (운영자 확정 2026-09-28): AI 교차 검사 + 근거 원문 ──
def test_cut_rows_carry_fact_source_text(real_copy):
    admin.main(["sync", "bathynomus_giganteus"])
    c3 = admin.load_status("bathynomus_giganteus")["artifacts"]["script"]["cuts"][2]
    assert [f["id"] for f in c3["facts"]] == ["F3", "F9"] and "等脚類" in c3["facts"][1]["fact"]
    assert c3["facts"][0]["sources"]


def test_crosscheck_sees_whole_script_and_stores_issues(real_copy):
    # 사고 당시 대사로 되돌려, 검사기가 '다른 컷(2번)의 주장'과 '출처(F9)'를 함께 받는지 확인
    sc = json.loads((real_copy / "script.json").read_text(encoding="utf-8"))
    for c in sc["cuts"]:
        if c.get("cut") == 3:
            c["jp"] = "大きさは最大50センチ近く。ダンゴムシの仲間では、世界最大です。"
    (real_copy / "script.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    seen = {}

    def fake_ask(prompt):
        seen["p"] = prompt
        return json.dumps({"issues": [{"cut": 3, "type": "scope", "problem_ko": "출처는 등각류 전체 중 최대",
                                        "facts": ["F9"], "suggestion_jp": "等脚類の中では、世界最大です。",
                                        "suggestion_ko": "등각류 중 세계 최대"}]})
    st = admin.crosscheck("bathynomus_giganteus", ask=fake_ask)
    p = seen["p"]
    assert "フナムシ" in p and "ダンゴムシの仲間では、世界最大" in p and "等脚類" in p   # 다른 컷 + 출처 전체
    assert "カット2" in p and "カット8" in p
    iss = st["artifacts"]["script"]["crosscheck"]["issues"]
    assert iss[0]["cut"] == 3 and iss[0]["type"] == "scope"


def test_crosscheck_failure_does_not_block(real_copy):
    def boom(prompt):
        raise RuntimeError("GEMINI_API_KEY 없음")
    before = {s: v["state"] for s, v in admin.load_status("bathynomus_giganteus")["stages"].items()}
    st = admin.crosscheck("bathynomus_giganteus", ask=boom)
    assert "실패" in st["artifacts"]["script"]["crosscheck"]["error"]
    assert {s: v["state"] for s, v in st["stages"].items()} == before      # 다른 단계는 그대로


# ── 컷 수정 방향 → 콘티 → 승인 → 영상 (운영자 확정 2026-09-28) ──
_PLAN = {"summary_ko": "텅 빈 뱃속을 단면 모형으로 보여 준 뒤 물음표로 끝냅니다.",
         "shots": [{"t0": 0, "t1": 2.2, "panel": 1, "motion": "omni", "overlay": "none", "desc_ko": "표본"},
                   {"t0": 2.2, "t1": 4.0, "panel": 2, "motion": "still", "overlay": "none", "desc_ko": "텅 빈 위 단면"},
                   {"t0": 4.0, "t1": 6.0, "panel": 3, "motion": "still", "overlay": "question_mark", "desc_ko": "물음표"}],
         "panels": {"1": "specimen", "2": "cut-away empty gut", "3": "dark specimen", "4": "spare"},
         "omni_prompts": {"1": "0.0-2.2s slow push-in on the still specimen."}}


def test_recut_plan_makes_conti_request_only(real_copy):
    seen = {}

    def ask(prompt):
        seen["p"] = prompt
        return json.dumps(_PLAN)
    st = admin.recut_plan("bathynomus_giganteus", 8, "뱃속이 텅 빈 묘사 + 사인 불명 물음표", min_tr=2, ask=ask,
                          run_images=False)
    rc = st["artifacts"]["recut"]["8"]
    assert rc["state"] == "conti_review" and len(rc["plan"]["shots"]) == 3
    assert "뱃속이 텅 빈" in seen["p"] and "at least 2 scene transitions" in seen["p"].lower() and "LAST cut" in seen["p"]
    req = json.loads((real_copy / "requests" / f"{rc['conti']['request']}.json").read_text(encoding="utf-8"))
    it = req["items"][0]
    assert req["kind"] == "gen_images" and it["split"]["rows"] == 2 and "NEVER draw text" in it["prompt"]
    assert it["refs"] and it["refs"][-1] == "out/14_storyboard_12/p11.jpg"
    assert not list((real_copy / "requests").glob("*_recut.json"))              # ★영상 요청은 아직 없다
    assert rc["estimate_usd"] == round(0.134 + 4 * 0.10, 2)                     # 콘티 + 움직이는 샷 1개(4초)


def test_recut_plan_rejects_too_few_transitions(real_copy):
    one = dict(_PLAN, shots=[{"t0": 0, "t1": 6, "panel": 1, "motion": "omni", "overlay": "none"}])
    with pytest.raises(SystemExit):
        admin.recut_plan("bathynomus_giganteus", 8, "전환 2회", min_tr=2, ask=lambda p: json.dumps(one),
                         run_images=False)
    rc = admin.load_status("bathynomus_giganteus")["artifacts"]["recut"]["8"]
    assert rc["state"] == "error" and "전환" in rc["error"]
    assert not list((real_copy / "requests").glob("*_conti.json"))


def test_recut_approve_builds_new_cut_and_reassembles(real_copy, monkeypatch):
    admin.recut_plan("bathynomus_giganteus", 8, "뱃속·물음표", min_tr=2, ask=lambda p: json.dumps(_PLAN),
                     run_images=False)
    st = admin.load_status("bathynomus_giganteus")
    prev = next(c for c in st["artifacts"]["video"]["clips"] if c["cut"] == 8)["file"]
    for rel in ("out/14_storyboard_12/p11.jpg", "out/14_storyboard_12/p10.jpg", "out/14_storyboard_12/p08.jpg",
                "out/14_storyboard_12/p05.jpg", "out/23_clips_v5/c08.mp4"):
        (real_copy / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REAL / rel, real_copy / rel)
    st["artifacts"]["recut"]["8"]["conti"]["panels"] = ["out/14_storyboard_12/p11.jpg", "out/14_storyboard_12/p10.jpg",
                                                         "out/14_storyboard_12/p08.jpg", "out/14_storyboard_12/p05.jpg"]
    admin._save(admin.status_path("bathynomus_giganteus"), st)
    real_run = subprocess.run

    def fake_run(args, cwd=None, **k):
        if args and str(args[-1]).endswith("_recut.json"):                     # Omni 대신 기존 클립 복사
            req = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
            out = real_copy / "out" / req["id"]
            out.mkdir(parents=True, exist_ok=True)
            for it in req["items"]:
                assert "NEVER SHOW: text" in it["prompt"] and "TIMELINE" in it["prompt"]
                shutil.copy(real_copy / "out/23_clips_v5/c08.mp4", out / f"{it['name']}.mp4")
            return subprocess.CompletedProcess(args, 0)
        return real_run(args, cwd=cwd, **k)
    monkeypatch.setattr(admin.subprocess, "run", fake_run)
    called = []
    monkeypatch.setattr(admin, "assemble", lambda pid: called.append(pid))
    admin.recut_approve("bathynomus_giganteus", 8)
    st = admin.load_status("bathynomus_giganteus")
    clip = next(c for c in st["artifacts"]["video"]["clips"] if c["cut"] == 8)
    assert clip["file"].endswith("_recut/c08.mp4") and (real_copy / clip["file"]).exists()
    assert clip["history"][-1] == prev
    assert st["artifacts"]["recut"]["8"]["state"] == "done" and called == ["bathynomus_giganteus"]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(real_copy / clip["file"])], capture_output=True, text=True).stdout)
    assert abs(dur - 6.0) < 0.1                                                  # 컷 길이 그대로


def test_recut_approve_needs_conti(real_copy):
    with pytest.raises(SystemExit):
        admin.recut_approve("bathynomus_giganteus", 8)


def test_text_model_is_picked_from_what_the_server_offers():
    """고정 모델 이름(gemini-2.5-pro)이 서버에서 404로 사라진 실사고 — 목록에서 고른다."""
    L = [{"name": "models/gemini-3-pro-image-preview", "supportedGenerationMethods": ["generateContent"]},
         {"name": "models/gemini-9-pro", "supportedGenerationMethods": ["generateContent"]},
         {"name": "models/gemini-9-flash", "supportedGenerationMethods": ["generateContent"]},
         {"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]}]
    assert admin.pick_text_model(L) == "gemini-9-pro"                     # 선호 목록에 없어도 pro 계열로
    assert admin.pick_text_model(L[:1]) is None                          # 이미지 전용 모델은 고르지 않음
    assert admin.pick_text_model(L + [{"name": "models/gemini-2.5-pro",
                                       "supportedGenerationMethods": ["generateContent"]}]) == "gemini-2.5-pro"


# ── 업로드(운영자 확정 2026-09-28) ──
_META = {"title_jp": "深海の掃除屋、5年絶食の謎", "title_ko": "심해의 청소부, 5년 단식의 수수께끼",
         "desc_jp": "メキシコ湾で見つかった大きな生き物です。", "desc_ko": "멕시코만에서 발견된 큰 생물입니다.",
         "tags_jp": ["#ダンゴムシ", "#絶食", "#深海の謎", "#雑学", "#生き物", "#Shorts", "#深海", "#海の生き物", "#水族館", "#ドキュメンタリー"],
         "tags_ko": ["#등각류", "#단식", "#심해의비밀", "#잡학", "#생물", "#바다생물", "#수족관", "#다큐멘터리"]}


def test_upload_meta_follows_channel_rules(real_copy):
    st = admin.upload_meta("bathynomus_giganteus", ask=lambda p: json.dumps(_META))
    m = st["artifacts"]["upload"]["meta"]
    assert m["title_jp"].endswith("#ダイオウグソクムシ #深海") and m["title_jp"].count("#") == 2
    assert "#shorts" not in (m["title_jp"] + m["desc_jp"]).lower()
    # 설명·키워드 해시태그(운영자 지시 2026-09-30): 종명 + 공통 3개 + AI 분석 태그, 중복·#Shorts 제거, 15개 이내
    assert m["tags_jp"][:4] == ["#ダイオウグソクムシ", "#深海", "#海洋生物", "#深海生物"] and 10 <= len(m["tags_jp"]) <= 15
    assert "#絶食" in m["tags_jp"] and "#Shorts" not in m["tags_jp"] and m["tags_jp"].count("#深海") == 1
    assert m["tags_ko"][:4] == ["#대왕구족충", "#심해", "#해양생물", "#심해생물"] and "#단식" in m["tags_ko"]
    assert m["desc_jp"].rstrip().endswith(" ".join(m["tags_jp"]))
    assert "コメントで教えてください" in m["desc_jp"] and "チャンネル登録" in m["desc_jp"]
    assert "AIによる再現映像" in m["desc_jp"] and "wikipedia.org" in m["desc_jp"]
    assert m["privacy"] == "private" and m["pinned_comment"] == "次に見たい深海の生き物は？"


def test_upload_meta_rejects_office_worker_title(real_copy):
    bad = dict(_META, title_jp="有給ゼロの深海生活")
    with pytest.raises(ValueError):
        admin.upload_meta("bathynomus_giganteus", ask=lambda p: json.dumps(bad))


def test_upload_once_and_only_on_approve(real_copy):
    st = admin.upload_meta("bathynomus_giganteus", ask=lambda p: json.dumps(_META))
    st["stages"]["upload"]["state"] = "review"
    admin._save(admin.status_path("bathynomus_giganteus"), st)
    calls = []

    def fake(path, title, desc, tags=None, privacy="private", category_id="15"):
        calls.append((title, privacy, tags))
        return {"url": "https://youtu.be/TEST", "video_id": "TEST", "privacy": privacy}
    admin.youtube_upload("bathynomus_giganteus", uploader=fake)
    assert calls and calls[0][1] == "private" and calls[0][2][:2] == ["ダイオウグソクムシ", "深海"] and len(calls[0][2]) >= 10
    with pytest.raises(SystemExit):                                          # 같은 편 두 번 금지
        admin.youtube_upload("bathynomus_giganteus", uploader=fake)
    assert len(calls) == 1
    with pytest.raises(SystemExit):                                          # 업로드 뒤에는 메타 수정도 막음
        admin.save_upload_meta("bathynomus_giganteus", {"title_jp": "x"})


def test_save_meta_validation(real_copy):
    admin.upload_meta("bathynomus_giganteus", ask=lambda p: json.dumps(_META))
    with pytest.raises(SystemExit):
        admin.save_upload_meta("bathynomus_giganteus", {"title_jp": "テスト #Shorts"})
    st = admin.save_upload_meta("bathynomus_giganteus", {"title_jp": "新しい題名 #ダイオウグソクムシ #深海", "privacy": "public"})
    assert st["artifacts"]["upload"]["meta"]["privacy"] == "public"


def test_upload_uses_values_on_screen_even_without_save(real_copy):
    """실사고: 화면에서 '공개'를 골랐는데 저장 전 값(비공개)으로 올라감 → 승인 버튼이 화면 값을 함께 보낸다."""
    st = admin.upload_meta("bathynomus_giganteus", ask=lambda p: json.dumps(_META))
    for s_ in ("video", "upload"):
        st["stages"][s_]["state"] = "approved" if s_ == "video" else "review"
    admin._save(admin.status_path("bathynomus_giganteus"), st)
    got = {}

    def fake(path, title, desc, tags=None, privacy="private", category_id="15"):
        got.update(title=title, privacy=privacy, category=category_id)
        return {"url": "https://youtu.be/T", "video_id": "T", "privacy": privacy}
    import importlib
    orig = admin.youtube_upload
    admin.youtube_upload = lambda pid: orig(pid, uploader=fake)
    try:
        admin.approve("bathynomus_giganteus", "upload",
                      json.dumps({"title_jp": "画面の題名 #ダイオウグソクムシ #深海", "privacy": "public", "category": "28"}))
    finally:
        admin.youtube_upload = orig
    assert got == {"title": "画面の題名 #ダイオウグソクムシ #深海", "privacy": "public", "category": "28"}
    st = admin.load_status("bathynomus_giganteus")
    assert st["stages"]["upload"]["state"] == "approved" and st["artifacts"]["upload"]["result"]["category"] == "28"


def test_topic_photo_free_license_and_renamed_species():
    """주제 카드 사진: 학명이 바뀐 종도 찾고(옛 이름=matched_term), 자유 라이선스 사진만 고른다."""
    def fake(url):
        if "/taxa/autocomplete" in url:
            return {"results": []}
        if "/taxa?" in url:
            return {"results": [{"id": 7, "name": "Insigniteuthis albatrossi", "is_active": True,
                                 "matched_term": "Opisthoteuthis californiana"}]}
        return {"results": [{"id": 7, "taxon_photos": [
            {"photo": {"license_code": None, "medium_url": "https://x/nolicense.jpg"}},
            {"photo": {"license_code": "pd", "medium_url": "https://x/free.jpg", "attribution": "NOAA"}}]}]}
    ph = admin.fetch_topic_photo("Opisthoteuthis californiana", get=fake)
    assert ph["url"] == "https://x/free.jpg" and ph["license"] == "pd" and ph["page"].endswith("/taxa/7")
    none = admin.fetch_topic_photo("Nope nope", get=lambda u: {"results": []})
    assert none is None


def test_topics_have_photo_and_korean_name():
    """시작할 수 있는 종은 사진과 한글명(정식이 없으면 상위 무리 이름 + 표시)을 가진다(지어내지 않음)."""
    tp = json.loads((admin.V2 / "topics.json").read_text(encoding="utf-8"))["topics"]
    ready = [t for t in tp if t["ready"]]
    assert ready and all(t.get("photo") and t["photo"]["url"].startswith("https://") for t in ready)
    assert all(re.search(r"[가-힣]", t["name_ko"]) for t in ready)
    assert all(t["ko_official"] or t["id"] in admin.KO_GROUP for t in ready)


# ── 대본 자동 작성(실사고 2026-09-30: '작업 중'인데 실제로 아무것도 안 돌던 문제) ──────────
_EN_TXT = ("The testfish (Testus fishus) is a deep-sea fish. It was discovered in 1977 by the submersible Alvin "
           "near the Galapagos Rift. It lives at depths of 2000 to 3000 metres. Adults reach 30 cm in length. "
           "It glows blue when disturbed. It feeds on marine snow drifting down from above. " * 2)


def _fake_wiki(url):
    if "en.wikipedia" in url and "Testus" in url:
        return {"query": {"pages": {"1": {"title": "Testfish", "fullurl": "https://en.wikipedia.org/wiki/Testfish",
                                         "extract": _EN_TXT, "langlinks": [{"lang": "ja", "*": "テストウオ"}]}}}}
    if "ja.wikipedia" in url and "%E3%83%86" in url:          # テストウオ
        return {"query": {"pages": {"2": {"title": "テストウオ", "fullurl": "https://ja.wikipedia.org/wiki/テストウオ",
                                         "extract": "テストウオは深海魚である。1977年に潜水艇アルビンが発見した。" * 10}}}}
    return {"query": {"pages": {"-1": {"missing": ""}}}}


_FACTS = {"facts": [
    {"fact_ko": "1977년 잠수정 앨빈이 갈라파고스 열곡 근처에서 발견", "fact_jp": "1977年、潜水艇アルビンがガラパゴス地溝の近くで発見",
     "quote": "It was discovered in 1977 by the submersible Alvin near the Galapagos Rift.", "src": "S1"},
    {"fact_ko": "수심 2000~3000m에 산다", "fact_jp": "水深2000〜3000メートルにすむ", "quote": "It lives at depths of 2000 to 3000 metres.", "src": "S1"},
    {"fact_ko": "다 자라면 30cm", "fact_jp": "成体は30センチ", "quote": "Adults reach 30 cm in length.", "src": "S1"},
    {"fact_ko": "건드리면 파랗게 빛난다", "fact_jp": "刺激を受けると青く光る", "quote": "It glows blue when disturbed.", "src": "S1"},
    {"fact_ko": "마린 스노를 먹는다", "fact_jp": "マリンスノーを食べる", "quote": "It feeds on marine snow drifting down from above.", "src": "S1"},
    {"fact_ko": "지어낸 사실", "fact_jp": "作り話", "quote": "It can live for 500 years.", "src": "S1"},   # 원문에 없음 → 버림
]}
_GOOD = [("暗い海の底で、体を青く光らせる魚がいます。", "F4"), ("すんでいるのは水深2000メートルより深い海。", "F2"),
         ("その名は、テストウオといいます。", "F1"), ("大きさは30センチほどになります。", "F3"),
         ("刺激を受けると、体が青く光ります。", "F4"), ("食べるのは、上から降ってくるマリンスノー。", "F5"),
         ("光の届かない世界で、静かに暮らしています。", "F2"), ("今日も暗い海の底で、青い光がまたたきます。", "F4")]


_CANDS = [{"pattern": "異常な行動", "text_jp": "触ると、青く光る", "key_jp": "青く光る", "voice_jp": "触れると、体が青く光る", "text_ko": "건드리면 파랗게 빛난다"},
          {"pattern": "常識破り", "text_jp": "魚なのに、青く光る", "key_jp": "光る", "voice_jp": "魚なのに、体が青く光る", "text_ko": "물고기인데 파랗게 빛난다"},
          {"pattern": "正体の反転", "text_jp": "光の正体は、魚", "key_jp": "魚", "voice_jp": "暗い海の光、その正体は魚", "text_ko": "빛의 정체는 물고기"}]


def _fake_ai(bad_first=False):
    calls = {"script": 0}
    def ask(p):
        if "science fact extractor" in p:
            return json.dumps(_FACTS)
        if "構成作家" in p:
            calls["script"] += 1
            cuts = [{"cut": i + 1, "jp": jp, "ko": "한국어 번역 " + str(i + 1), "fact": f, "scene_ko": "장면", "annotation": ""}
                    for i, (jp, f) in enumerate(_GOOD)]
            if bad_first and calls["script"] == 1:
                cuts[3]["jp"] = "大きさは50センチにもなります。"      # 사실에 없는 숫자 → 코드 검사에서 걸려 다시 쓰게
            hook = {"cut": 5, "answer_jp": "テストウオ", "answer_ko": "시험어", "candidates": _CANDS}   # 후킹 개편: 사실 한 줄 후보 3개
            return json.dumps({"core": "F4", "cuts": cuts, "hook": hook})      # 핵심 사실 F4: 후킹 컷 5 · 마지막 3컷의 8번
        return json.dumps({"issues": []})                    # 교차 검사
    return ask, calls


def test_write_script_real_job_moves_script_to_review(v2):
    admin.new_pilot("test_fish")
    ask, calls = _fake_ai(bad_first=True)
    st = admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    assert states("test_fish")[1] == "review"                 # 실제로 대본이 생겨 '승인 대기'
    assert st["jobs"]["script"]["status"] == "done"
    sc = json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))
    assert len(sc["cuts"]) == 8 and all(c["tts"] and c["sec"] in (4, 6, 8, 10) for c in sc["cuts"])
    assert sc["subject"]["jp_name"] == "テストウオ"
    assert len(sc["facts"]) == 5 and sc["generated"]["facts_dropped"] == 1      # 원문에 없는 '500년'은 버림
    assert all(f["sources"] == ["https://en.wikipedia.org/wiki/Testfish"] for f in sc["facts"])
    assert calls["script"] == 2                              # 사실에 없는 숫자(50) → 한 번 더 쓰게 함
    assert "50" not in sc["cuts"][3]["jp"]
    a = st["artifacts"]["script"]
    assert len(a["cuts"]) == 8 and a["cuts"][0]["facts"][0]["id"] == "F4" and a["crosscheck"]["issues"] == []
    assert sc["core"] == "F4" and sc["hook"]["type"] == "line" and a["core"]["id"] == "F4"          # 핵심 사실 하나(D)
    hk = sc["hook"]                                                       # 후킹 개편: 후보 3개 · 기본 1번이 지금 후킹
    assert len(hk["candidates"]) == 3 and hk["chosen"] == 0 and hk["question_jp"] == "触ると、青く光る"
    assert hk["key_jp"] == "青く光る" and hk["voice_jp"] == "触れると、体が青く光る" and hk["pattern"] == "異常な行動"
    assert sc["hook"]["cut"] == 5 and sc["hook"]["at"] is not None and a["hook"]["answer_jp"] == "テストウオ"
    assert sc["total_sec"] == sum(c["sec"] for c in sc["cuts"]) + 4      # 후킹 2초 + 정답 카드 2초


def test_write_script_failure_is_not_left_as_working(v2):
    admin.new_pilot("test_fish")
    with pytest.raises(SystemExit):
        admin.write_script("test_fish", ask=lambda p: "{}", get=lambda u: {"query": {"pages": {}}}, tts=False)
    st = admin.load_status("test_fish")
    assert st["jobs"]["script"]["status"] == "failed" and "실패" in st["jobs"]["script"]["text"]


def test_job_fail_marks_running_job(v2):
    admin.new_pilot("test_fish")
    admin.main(["job_start", "test_fish", "script"])
    assert admin.load_status("test_fish")["jobs"]["script"]["status"] == "running"
    idx = json.loads((v2 / "pilots" / "index.json").read_text(encoding="utf-8"))
    assert idx["items"][0]["job"]["status"] == "running"      # 목록 화면도 실제 작업 여부를 안다
    admin.main(["job_fail", "test_fish", "write_script"])
    assert admin.load_status("test_fish")["jobs"]["script"]["status"] == "failed"


def test_validate_script_rules():
    facts = [{"id": "F1", "fact": "수심 2000m", "fact_jp": "", "quote": "2000 m"}]
    ok = [{"cut": i, "jp": "水深2000メートルの海にすんでいます。", "ko": "한국어", "fact": "F1"} for i in range(1, 9)]
    assert admin.validate_script(ok, facts) == []
    bad = [dict(c) for c in ok]
    bad[0]["jp"] = "チャンネル登録してね、水深2000メートル。"
    bad[1]["fact"] = "F9"
    bad[2]["jp"] = "水深9000メートルの海にすんでいます。"
    p = " ".join(admin.validate_script(bad[:7], facts))
    assert "カット数" in p and "呼びかけ" in p and "F9" in p and "9000" in p


def test_script_revise_rewrites_with_same_verified_facts(v2):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    admin.revise("test_fish", "script", "1번 컷을 더 짧게")
    seen = {}
    def ask2(p):
        if "science fact extractor" in p:
            raise AssertionError("수정 요청은 사실을 다시 뽑지 않는다")
        if "構成作家" in p:
            seen["fb"] = "1번 컷을 더 짧게" in p
        return ask(p)
    admin.write_script("test_fish", "1번 컷을 더 짧게", ask=ask2, get=lambda u: 1 / 0, tts=False)
    sc = json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))
    assert seen["fb"] and len(sc["facts"]) == 5 and len(sc["previous_scripts"]) == 1
    assert states("test_fish")[1] == "review"


# ── 후킹 2초 + 정답 카드(운영자 확정 2026-09-30 · 공용 엔딩 대체) ─────────────────────
def test_validate_hook_rules():
    cuts = [{"cut": i, "jp": "x"} for i in range(1, 9)]
    facts = [{"id": "F1", "fact": "수심 500m", "fact_jp": "", "quote": "500 m"}]
    assert admin.validate_hook({"cut": 3, "question_jp": "皮を脱ぎ捨てる、この生き物は？", "answer_jp": "ユメナマコ"}, cuts, facts) == []
    p = " ".join(admin.validate_hook({"cut": 9, "question_jp": "ユメナマコは9000メートルにいる？", "answer_jp": "ユメナマコ"}, cuts, facts))
    assert "存在しない" in p and "答えの名前" in p and "9000" in p
    assert admin.validate_hook(None, cuts, facts)


def test_edit_hook_changes_script_only(v2):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    admin.main(["edit_hook", "test_fish", "_", json.dumps({"cut": 4, "at": 99, "question_jp": "30センチの、光る魚", "key_jp": "光る魚",
                                                           "voice_jp": "30センチの、光る魚", "answer_jp": "テストウオ"})])
    sc = json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))
    assert sc["hook"]["cut"] == 4 and sc["hook"]["question_jp"] == "30センチの、光る魚" and sc["hook"]["type"] == "line"
    assert sc["hook"]["at"] <= sc["cuts"][3]["sec"] - 2 and len(sc["hook_history"]) == 1     # 시작 초는 컷 안으로
    with pytest.raises(SystemExit):                                                     # 정답 이름이 문장에 들어가면 거절
        admin.edit_hook("test_fish", {"question_jp": "テストウオ、光る魚"})
    with pytest.raises(SystemExit):                                                     # 이름 맞히기 퀴즈는 거절(개편)
        admin.edit_hook("test_fish", {"question_jp": "光る、この魚は？", "key_jp": "光る", "voice_jp": "光る魚"})


def _tiny_clip(path, sec, color):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=720x1280:r=24:d={sec}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def _silent_wav(path, sec):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={sec}",
                    "-ac", "1", "-ar", "24000", str(path)], check=True)


def test_assemble_hook_and_answer_replace_shared_ending(tmp_path):
    """실제 ffmpeg 조립: [후킹 2초][본편: 컷은 나레이션 끝+0.6초에서 잘라 3.25+3.25초][정답 2초] = 10.5초 · 공용 엔딩 없음 · 맨 앞은 그 컷 화면(빨강).
    (운영자 확정 2026-09-30 핵심 규칙: 영상 컷이 4초여도 나레이션 2.5초면 0.15+2.5+0.6=3.25초만 쓴다 — 무음 구간 최소화)"""
    import assemble as A
    P = tmp_path / "p"; (P / "out" / "clips").mkdir(parents=True); (P / "out" / "tts").mkdir(parents=True)
    _tiny_clip(P / "out" / "clips" / "c01.mp4", 4, "blue"); _tiny_clip(P / "out" / "clips" / "c02.mp4", 4, "red")
    _silent_wav(P / "out" / "tts" / "body.wav", 6)
    tps = lambda: [{"jp_seg": None, "start": 0.15, "end": 2.5}]
    sc = {"subject": {"scientific_name": "Testus fishus"}, "hook": {"cut": 2, "at": 1.0, "question_jp": "赤くなる、この生き物は？", "answer_jp": "テストウオ"},
          "cuts": [{"cut": 1, "jp": "こんにちは。", "tts": "こんにちは。", "sec": 4}, {"cut": 2, "jp": "さようなら。", "tts": "さようなら。", "sec": 4}],
          "timing_v5": [{"cut": 1, "sec": 4, "audio_from": 0.0, "audio_to": 2.5, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()},
                        {"cut": 2, "sec": 4, "audio_from": 2.5, "audio_to": 5.0, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()}]}
    (P / "script.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    dst = tmp_path / "final.mp4"
    A.main(str(P), "clips", "tts", "", str(dst))
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst)],
                               capture_output=True, text=True).stdout)
    assert abs(dur - 10.5) < 0.3
    from PIL import Image
    def frame(t):
        f = tmp_path / f"f{t}.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(dst), "-frames:v", "1", str(f)], check=True)
        return Image.open(f).convert("RGB")
    r, g, b = frame(0.1).resize((1, 1)).getpixel((0, 0))
    assert r > 150 and g < 80 and b < 80                     # 후킹 = 2번 컷(빨강) 화면을 그대로 발췌
    r, g, b = frame(10.2).resize((1, 1)).getpixel((0, 0))
    assert r < 90 and g < 90 and b < 110                     # 정답 카드 = 어두운 배경(마지막 화면 흐림 + 남색)
    r, g, b = frame(6.0).resize((1, 1)).getpixel((0, 0))
    assert r > 150 and g < 80                                # 8.5초가 아니라 5.25초부터 이미 2번 컷(빨강) — 1번 컷이 잘렸다
    assert not (tmp_path / "end.mp4").exists()


# ── ③ 스토리보드 자동 · ④ 영상 자동(운영자 지시 2026-09-30: 승인하면 다음 단계가 실제로 만들어진다) ──────────
def _fake_runner(tmp_root):
    """run_request.py 대신: 요청 kind 별로 가짜 결과 파일을 만든다(이미지·격자 칸·영상·나레이션)."""
    from PIL import Image
    def run(rp):
        req = json.loads(Path(rp).read_text(encoding="utf-8"))
        out = Path(rp).parent.parent / "out" / req["id"]; out.mkdir(parents=True, exist_ok=True)
        items = []
        for it in req.get("items", []):
            if req["kind"] == "gen_images":
                Image.new("RGB", (400, 700), (90, 90, 120)).save(out / f"{it['name']}.jpg")
                rec = {"name": it["name"], "file": f"{it['name']}.jpg"}
                if it.get("split"):
                    rec["panels"] = []
                    for n in it["split"]["names"]:
                        if n:
                            Image.new("RGB", (360, 640), (40, 60, 90)).save(out / f"{n}.jpg"); rec["panels"].append(f"{n}.jpg")
                items.append(rec)
            elif req["kind"] == "gen_omni":
                _tiny_clip(out / f"{it['name']}.mp4", it.get("sec", 4), "gray")
                items.append({"name": it["name"], "file": f"{it['name']}.mp4"})
            elif req["kind"] == "gen_tts" and it.get("name") == "hook":             # 후킹 한 줄 목소리(1.6초)
                _silent_wav(out / "hook.wav", 1.6)
                items.append({"name": "hook", "file": "hook.wav"})
            elif req["kind"] == "gen_tts":
                _silent_wav(out / "body.wav", 30)
                segs = it["segments"]
                (out / "body_timepoints.json").write_text(json.dumps([{"seg": s, "start": round(i * 3.0, 2), "end": round(i * 3.0 + 2.5, 2)} for i, s in enumerate(segs)]))
                items.append({"name": "body", "file": "body.wav"})
        (out / "result.json").write_text(json.dumps({"ok": True, "items": items}, ensure_ascii=False))
        return 0
    return run


def _fake_vision(p, images=None):
    if "model maker" in p:
        return json.dumps({"anatomy": "A translucent reddish swimming sea cucumber with a veil-like webbed fin, no head, no eyes, no bones, soft gelatinous body about 25 cm long.",
                           "forbidden": "no fish head, no eyes, no legs", "size_note": "", "checklist_ko": ["머리 없음", "눈 없음", "베일 같은 막", "반투명 붉은색"]})
    if "Compare the attached" in p:
        return json.dumps({"items": [{"item": "머리 없음", "verdict": "pass", "note_ko": "좋음"}, {"item": "눈 없음", "verdict": "unknown", "note_ko": ""}]})
    if "storyboard artist" in p:
        shots = ["wide", "wide", "close", "wide", "medium", "wide", "wide", "close"]
        motion = ["omni", "omni", "still", "still", "omni", "still", "still", "omni"]     # 1·2번·후킹 컷(5) omni · 4컷 이하 · still 3연속 없음
        return json.dumps({"panels": {str(i): {"shot": shots[i - 1], "motion": motion[i - 1], "set_edge": i % 2 == 1, "props": ["paper waves", "cotton marine snow"],
                                               "desc": f"Panel {i}: tabletop diorama box on a wooden desk, the creature small in the frame, desk lamp."}
                                      for i in range(1, 9)}})
    if "per-second TIMELINE" in p:
        return json.dumps({"prompts": {str(i): f"0.0-2.0s slow dolly toward the creature; 2.0-4.0s it undulates its veil and drifts left, camera holds. cut {i}" for i in range(1, 9)}})
    return json.dumps({"issues": []})


def _fake_fetch(url, fn):
    from PIL import Image
    Image.new("RGB", (300, 300), (200, 80, 80)).save(fn)


def _prep_pilot(v2, monkeypatch):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    admin.main(["ready", "test_fish", "script"]); admin.approve("test_fish", "script")
    st = admin.load_status("test_fish"); st["topic"]["photo"] = {"url": "https://x/p.jpg", "credit": "c", "license": "pd"}
    admin._save(admin.status_path("test_fish"), st)
    monkeypatch.setattr(admin, "_RUN_REQUEST", _fake_runner(v2))


def test_write_storyboard_reaches_review_with_card_check_and_8_panels(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    assert states("test_fish")[2] == "working"
    st = admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    assert states("test_fish")[2] == "review" and st["jobs"]["storyboard"]["status"] == "done"
    a = st["artifacts"]["storyboard"]
    assert len(a["panels"]) == 8 and a["sheet"] and (v2 / "pilots" / "test_fish" / a["sheet"]).exists()
    assert a["card_check"]["items"][0]["verdict"] == "pass" and len(a["card"]) == 3
    sc = json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))
    assert all(c["keyframe"].endswith(f"p{c['cut']:02d}.jpg") for c in sc["cuts"])
    cc = json.loads((v2 / "pilots" / "test_fish" / "creature_card.json").read_text(encoding="utf-8"))
    assert "no head" in cc["anatomy"] and len(cc["use_as_reference"]) == 3
    reqs = sorted(p.name for p in (v2 / "pilots" / "test_fish" / "requests").iterdir())
    assert any("_card" in r for r in reqs) and any("_sb" in r for r in reqs)


def test_storyboard_revise_keeps_card_unless_asked(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    n0 = len(list((v2 / "pilots" / "test_fish" / "requests").iterdir()))
    admin.revise("test_fish", "storyboard", "3번 컷을 더 어둡게")
    seen = {}
    def ask2(p, images=None):
        if "storyboard artist" in p:
            seen["fb"] = "3번 컷을 더 어둡게" in p
        return _fake_vision(p, images)
    admin.write_storyboard("test_fish", "3번 컷을 더 어둡게", ask=ask2, get=lambda u: {"results": []}, fetch=_fake_fetch)
    assert seen["fb"] and len(list((v2 / "pilots" / "test_fish" / "requests").iterdir())) == n0 + 1     # 카드 요청 없이 콘티만
    assert states("test_fish")[2] == "review"


def test_make_video_generates_clips_then_assembles(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    admin.approve("test_fish", "storyboard")
    called = []
    def fake_assemble(pid):
        st = admin.load_status(pid); st["stages"]["video"]["state"] = "review"; admin._save(admin.status_path(pid), st); called.append(pid)
    monkeypatch.setattr(admin, "assemble", fake_assemble)
    st = admin.make_video("test_fish", ask=_fake_vision)
    assert called == ["test_fish"] and st["jobs"]["video"]["status"] == "done" and states("test_fish")[3] == "review"
    v = st["artifacts"]["video"]
    assert len(v["clips"]) == 8 and v["assemble"]["ending"] == "" and v["assemble"]["tts_id"] == st["artifacts"]["script"]["tts_id"]
    assert all((v2 / "pilots" / "test_fish" / c["file"]).exists() for c in v["clips"])
    spent = [x for x in st["cost"]["spent"] if "영상 컷" in x["what"]]
    assert spent and spent[0]["usd"] > 0
    # 수정 요청 '3번 컷' → 그 컷만 다시 만든다(다른 컷 파일은 그대로)
    admin.revise("test_fish", "video", "3번 컷 배경을 더 어둡게")
    before = {c["cut"]: c["file"] for c in v["clips"]}
    st = admin.make_video("test_fish", "3번 컷 배경을 더 어둡게", ask=_fake_vision)
    after = {c["cut"]: c["file"] for c in st["artifacts"]["video"]["clips"]}
    assert after[3] != before[3] and all(after[k] == before[k] for k in before if k != 3)


def test_make_video_failed_cut_is_recorded_and_retry_only_redoes_missing(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    admin.approve("test_fish", "storyboard")
    base = _fake_runner(v2)
    def flaky(rp):
        rc = base(rp)
        req = json.loads(Path(rp).read_text(encoding="utf-8"))
        if req["kind"] == "gen_omni" and any(it["name"] == "c05" for it in req["items"]) and not flaky.done:
            flaky.done = True
            out = Path(rp).parent.parent / "out" / req["id"]
            res = json.loads((out / "result.json").read_text()); res["items"] = [i for i in res["items"] if i["name"] != "c05"]
            (out / "result.json").write_text(json.dumps(res)); return 1
        return rc
    flaky.done = False
    monkeypatch.setattr(admin, "_RUN_REQUEST", flaky)
    monkeypatch.setattr(admin, "assemble", lambda pid: None)
    with pytest.raises(SystemExit):
        admin.make_video("test_fish", ask=_fake_vision)
    st = admin.load_status("test_fish")
    assert st["jobs"]["video"]["status"] == "failed" and "[5]" in st["jobs"]["video"]["text"] and len(st["artifacts"]["video"]["clips"]) == 7
    seen = []
    def counting(rp):
        req = json.loads(Path(rp).read_text(encoding="utf-8"))
        if req["kind"] == "gen_omni":
            seen.append([it["name"] for it in req["items"]])
        return base(rp)
    monkeypatch.setattr(admin, "_RUN_REQUEST", counting)
    admin.make_video("test_fish", ask=_fake_vision)
    assert seen == [["c05"]]                                   # 성공한 7컷은 다시 만들지 않는다(과금 방지)


def test_workflow_has_secrets_and_setup():
    """v2-admin.yml 구조 검사(실사고 run #14: 편집 실수로 '버튼 실행' 단계의 env(키)와 '준비' 단계가 지워져 GEMINI_API_KEY 없음으로 실패)."""
    import yaml
    d = yaml.safe_load((ROOT.parent / ".github" / "workflows" / "v2-admin.yml").read_text(encoding="utf-8"))
    steps = {s.get("name"): s for s in d["jobs"]["run"]["steps"] if s.get("name")}
    assert list(steps) == ["진행 중 먼저 기록", "준비", "버튼 실행", "실패 기록", "결과 커밋"]
    env = steps["버튼 실행"]["env"]
    for k in ("GEMINI_API_KEY", "GOOGLE_TTS_KEY", "YOUTUBE_REFRESH_TOKEN", "IG_ACCESS_TOKEN", "IN_ACTION", "IN_PILOT", "IN_STAGE", "IN_NOTE"):
        assert k in env, k
    assert "ffmpeg" in steps["준비"]["run"] and "janome" in steps["준비"]["run"] and "requests" in steps["준비"]["run"]
    run1, run2 = steps["진행 중 먼저 기록"]["run"], steps["버튼 실행"]["run"]
    assert "job_start" in run1 and "ci_commit.sh" in run1
    for a in ("write_script", "write_storyboard", "make_video"):           # 키가 없는 첫 단계에서 유료 작업을 돌리면 안 된다
        assert f"admin.py {a}" not in run1, a
    for a in ("write_script", "write_storyboard", "make_video", "edit_hook", "recut_approve", "upload_meta", "save_meta", "save_viewed",
              "after_video", "trial_check", "trial_skip", "ig_probe"):                  # 시험 릴스(2026-10-09)
        assert a in run2, a
    assert "after_video" not in run1                                              # 인스타 키는 '버튼 실행' 단계에만 있다
    assert steps["실패 기록"].get("if") == "failure()" and steps["결과 커밋"].get("if") == "always()"


def test_build_cut_without_pilot_macro_insert(tmp_path):
    """실사고 2026-09-30: 시범편 전용 매크로 인서트(컷 4)를 파일이 없는 새 편에도 적용해 ffmpeg가 죽었다 → 파일 없으면 건너뛴다."""
    import assemble as A
    clip = tmp_path / "c04.mp4"; _tiny_clip(clip, 4, "green")
    out = A.build_cut(tmp_path, clip, 4, 4, None, tmp_path, {"cut": 4, "jp": "x"})
    assert out.exists() and A.insert_for(tmp_path, 4, {}) is None


def test_species_tag_never_empty_without_japanese_name():
    """실사고 2026-09-30: 和名이 없는 머리없는닭괴물 편 제목이 「… # #深海」로 올라감 → 후킹 정답 이름으로 채운다."""
    sc = {"subject": {"scientific_name": "Enypniastes eximia", "jp_name": "", "ko_name": "머리없는닭괴물"},
          "hook": {"answer_jp": "首なしチキンモンスター", "answer_ko": "머리없는닭괴물"}}
    assert admin.species_tags(sc) == ("#首なしチキンモンスター", "#머리없는닭괴물")
    assert admin.species_tags({"subject": {"scientific_name": "Testus fishus"}}) == ("#Testusfishus", "#Testusfishus")
    m = admin._compose_meta(sc, {"title_jp": "題", "title_ko": "제", "desc_jp": "説明", "desc_ko": "설명", "tags_jp": ["#ナマコ"], "tags_ko": ["#해삼"]})
    assert m["title_jp"] == "題 #首なしチキンモンスター #深海" and "#ナマコ" in m["tags_jp"] and "#" not in m["tags_jp"][0][1:]


# ── 미니어처 세계관 규칙(운영자 승인 2026-10-01 · 실사고: 자동 콘티가 빈 배경 + 생물 접사만 그림) ──────────────
def _plan(shots, edges=4, props=2, omni=(1, 2, 3, 6)):
    return {i + 1: {"shot": sh, "motion": "omni" if (i + 1) in omni else "still", "set_edge": i < edges,
                    "props": ["felt", "paper"][:props], "desc": "x" * 50} for i, sh in enumerate(shots)}


def test_validate_storyboard_plan_miniature_rules():
    cuts = [{"cut": i} for i in range(1, 9)]
    ok = _plan(["wide"] * 5 + ["medium", "close", "close"])
    assert admin.validate_storyboard_plan(ok, cuts) == []
    p = " ".join(admin.validate_storyboard_plan(_plan(["close"] * 6 + ["wide"] * 2, edges=2, props=1), cuts))   # 이번 편 같은 접사 위주
    assert "WIDE" in p and "CLOSE" in p and "edge" in p and "2 hand-made props" in p


def test_plan_storyboard_retries_until_miniature_rules_pass():
    sc = {"cuts": [{"cut": i, "jp": "x", "tts": "x", "sec": 6} for i in range(1, 9)], "facts": [], "hook": {"cut": 3}}
    seen = []
    def ask(p):
        seen.append(p)
        if len(seen) == 1:                                    # 첫 계획: 접사만 → 거절
            return json.dumps({"panels": {str(k): v for k, v in _plan(["close"] * 8).items()}})
        return json.dumps({"panels": {str(k): v for k, v in _plan(["wide"] * 6 + ["close", "medium"]).items()}})
    panels = admin.plan_storyboard(sc, {"anatomy": "a soft pink sea cucumber"}, ask=ask)
    assert len(seen) == 2 and "Problems in your previous plan" in seen[1] and panels[1]["shot"] == "wide"
    assert "TABLETOP" in seen[0] and "STORY PROPS" in seen[0] and "at least 5 WIDE" in seen[0]


def test_grid_items_add_style_refs_and_generic_creature(v2):
    style = v2 / "pilots" / "_shared" / "style"; style.mkdir(parents=True)
    for f in admin.STYLE_REFS:
        (style / Path(f).name).write_bytes(b"x")
    cuts = [{"cut": i} for i in range(1, 9)]
    items = admin._grid_items(cuts, _plan(["wide"] * 8), {"anatomy": "a soft pink sea cucumber", "use_as_reference": [{"file": "out/c/card.jpg"}]})
    assert len(items) == 2 and items[0]["refs"] == ["out/c/card.jpg"] + admin.STYLE_REFS
    assert "STYLE REFERENCES: the LAST 2" in items[0]["prompt"] and "isopod" not in items[0]["prompt"].lower()
    assert "isopod" not in admin._OMNI_HEAD.lower() and "isopod" not in admin._OMNI_TAIL.lower()   # 다른 종 지시문에 대왕구족충 금지


def test_storyboard_trial_does_not_touch_status(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    before = (v2 / "pilots" / "test_fish" / "status.json").read_text(encoding="utf-8")
    from PIL import Image
    def gen(req, pilot, out):
        for n in req["items"][0]["split"]["names"]:
            Image.new("RGB", (360, 640), (200, 150, 90)).save(out / f"{n}.jpg")
        return {"ok": True}
    out = v2 / "pilots" / "test_fish" / "out" / "trial"
    res = admin.storyboard_trial("test_fish", out=out, ask=_fake_vision, gen=gen)
    assert res["ok"] and (out / "compare_old_new.jpg").exists() and (out / "plan.json").exists()
    assert (v2 / "pilots" / "test_fish" / "status.json").read_text(encoding="utf-8") == before


# ── 개편(운영자 선택 2026-10-05): 혼합 제작 · 놀라움 점수 · 재생목록 · 실적 · 연재감 ──────────────
def test_plan_requires_hook_omni_and_omni_budget():
    cuts = [{"cut": i} for i in range(1, 9)]
    ok = _plan(["wide"] * 5 + ["medium", "close", "close"], omni=(1, 2, 3, 6))
    assert admin.validate_storyboard_plan(ok, cuts, hook_cut=3) == []
    p = " ".join(admin.validate_storyboard_plan(_plan(["wide"] * 8, omni=(1, 2, 3, 4, 5, 6)), cuts, hook_cut=7))
    assert "at most 4" in p and "Cut 7 is the opening hook" in p


def test_make_video_hybrid_generates_only_omni_cuts(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    st = admin.load_status("test_fish")
    assert [p["motion"] for p in st["artifacts"]["storyboard"]["panels"]].count("omni") == 4
    assert st["cost"]["estimate"]["video"] < sum(c["sec"] for c in st["artifacts"]["script"]["cuts"]) * admin.OMNI_USD_PER_SEC
    admin.approve("test_fish", "storyboard")
    seen = []
    base = _fake_runner(v2)
    def counting(rp):
        req = json.loads(Path(rp).read_text(encoding="utf-8"))
        if req["kind"] == "gen_omni":
            seen.append(sorted(it["name"] for it in req["items"]))
        return base(rp)
    monkeypatch.setattr(admin, "_RUN_REQUEST", counting)
    monkeypatch.setattr(admin, "assemble", lambda pid: None)
    st = admin.make_video("test_fish", ask=_fake_vision)
    assert seen == [["c01", "c02", "c05", "c08"]]                       # 유료 생성은 영상 AI 컷 4개만(1·2번 필수 · 후킹 5번)
    clips = {c["cut"]: c for c in st["artifacts"]["video"]["clips"]}
    assert len(clips) == 8 and clips[3]["motion"] == "still" and "_stills/" in clips[3]["file"]
    assert (v2 / "pilots" / "test_fish" / clips[3]["file"]).exists()
    spent = [x for x in st["cost"]["spent"] if "영상 컷" in x["what"]][0]["usd"]
    assert spent == round(sum(clips[k]["sec"] for k in (1, 2, 5, 8)) * admin.OMNI_USD_PER_SEC, 2)


def test_redo_still_cut_upgrades_to_omni(v2, monkeypatch):
    _prep_pilot(v2, monkeypatch)
    admin.write_storyboard("test_fish", ask=_fake_vision, get=lambda u: {"results": []}, fetch=_fake_fetch)
    admin.approve("test_fish", "storyboard")
    monkeypatch.setattr(admin, "assemble", lambda pid: None)
    admin.make_video("test_fish", ask=_fake_vision)
    called = []
    monkeypatch.setattr(admin, "make_video", lambda pid, fb="", ask=None: called.append(fb))
    admin.redo_cut("test_fish", 3)
    sc = json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))
    assert called == ["3번 컷"] and sc["cuts"][2]["motion"] == "omni"


def test_topic_scores_sort_and_cache(v2, monkeypatch):
    monkeypatch.setattr(admin, "TOPIC_SCORES", v2 / "topic_scores.json")
    items = [{"id": "a", "sci": "A a", "name_en": "a", "facts": ["x"], "ready": True},
             {"id": "b", "sci": "B b", "name_en": "b", "facts": ["y"], "ready": True}]
    calls = []
    def ask(p):
        calls.append(p)
        return json.dumps({"scores": {"a": {"score": 4, "hook_jp": "ふつう", "hook_ko": "보통"}, "b": {"score": 9, "hook_jp": "5年絶食", "hook_ko": "5년 단식"}}})
    sc = admin._topic_scores(items, ask=ask)
    assert sc["b"]["score"] == 9 and sc["a"]["hook_ko"] == "보통"
    admin._topic_scores(items, ask=ask)
    assert len(calls) == 1                                    # 캐시 — 두 번째는 묻지 않음


def test_upload_adds_playlist_and_stats(real_copy):
    st = admin.load_status("bathynomus_giganteus")
    st["artifacts"].setdefault("upload", {})["meta"] = admin._compose_meta(
        json.loads((admin._script_path("bathynomus_giganteus")).read_text(encoding="utf-8")), dict(_META))
    admin._save(admin.status_path("bathynomus_giganteus"), st)
    pl = []
    st = admin.youtube_upload("bathynomus_giganteus", uploader=lambda *a, **k: {"url": "https://youtu.be/X", "video_id": "X", "privacy": "private"},
                              playlister=lambda vid, title, desc: pl.append((vid, title)) or {"playlist_id": "PL1"})
    assert pl == [("X", "深海の謎")] and st["artifacts"]["upload"]["result"]["playlist"] == "PL1"
    got = admin.fetch_stats(stats_fn=lambda vid, a, b: {"views": 1383, "estimatedMinutesWatched": 432, "averageViewDuration": 42,
                                                         "averageViewPercentage": 71.5, "subscribersGained": 3, "likes": 20, "comments": 2})
    sv = got["bathynomus_giganteus"]
    assert sv["views"] == 1383 and sv["subs_per_1k"] == 2.17 and sv["like_rate"] == 1.45
    bad = admin.fetch_stats(stats_fn=lambda *a: (_ for _ in ()).throw(RuntimeError("HttpError 403 insufficientPermissions")))
    assert "재발급" in bad["bathynomus_giganteus"]["error"]
    idx = admin.build_index()
    assert next(i for i in idx["items"] if i["id"] == "bathynomus_giganteus")["stats"]["error"]
    # 분석 권한이 없어도 공개 통계(Data API)로 조회·좋아요·댓글은 기록된다(운영자 지적 2026-10-05)
    part = admin.fetch_stats(stats_fn=lambda *a: {"views": 1383, "likes": 20, "comments": 2, "_source": "data_api",
                                                  "_errors": {"analytics": "403 insufficient"}})
    sv = part["bathynomus_giganteus"]
    assert sv["views"] == 1383 and sv["partial"] and sv["source"] == "data_api" and "error" not in sv


def test_answer_card_has_series_line(tmp_path):
    import assemble as A
    src = Path(A.__file__).read_text(encoding="utf-8")
    assert "次の深海の謎も、このチャンネルで。" in src
    out = A.answer_png("この生き物は？", "テスト", "Testus fishus", tmp_path / "a.png")
    assert out.exists()


def test_screen_text_blocks_korean_annotation(tmp_path):
    """실사고 2026-10-05: 왕게 편 주석이 한국어 → 영상 글꼴(일본어)에 없어 네모 □. 대본 검사·조립 직전 검사 둘 다 막는다."""
    import assemble as A
    assert A.missing_glyphs("1800年代後半から 水深4152m 第5歩脚") == []
    assert A.label_png("宿主はセンジュナマコ", tmp_path / "ok.png").exists()
    with pytest.raises(A.GlyphError):
        A.label_png("1800년대 후반 이후", tmp_path / "bad.png")
    with pytest.raises(A.GlyphError):
        A.hook_png("수심에 사는, この生き物は？", tmp_path / "h.png")
    facts = [{"id": "F1", "fact": "1800", "fact_jp": "", "quote": "1800"}]
    cut = {"jp": "1800年代後半以降、学者は疑ってきました。", "ko": "학자들은 의심했습니다.", "fact": "F1", "annotation": "1800년대 후반"}
    probs = admin.validate_script([cut] * admin.SCRIPT_CUTS, facts)
    assert any("韓国語" in p for p in probs)
    cut["annotation"] = "1800年代後半から"
    assert not any("注釈" in p for p in admin.validate_script([cut] * admin.SCRIPT_CUTS, facts))


def test_nickname_is_not_drawn_as_land_animal():
    """실사고 2026-10-06: 「바다돼지라 불리는 해삼」을 콘티가 "clay sea pig"로 적어 진짜 돼지 인형이 그려짐."""
    assert admin.literal_animal_problems("a chunky translucent clay sea pig (Scotoplanes) stands still", "Cut 5")
    assert admin.literal_animal_problems("a headless chicken monster swims", "Cut 1")
    assert not admin.literal_animal_problems("a translucent pink deep-sea sea cucumber with stubby tube-feet legs", "Cut 5")
    assert not admin.literal_animal_problems("a dumbo octopus with elephant-ear fins", "Cut 2")
    cuts = [{"cut": i, "jp": "x", "ko": "x"} for i in range(1, 9)]
    panels = {i: {"shot": "wide", "motion": "omni" if i in (1, 2, 5, 8) else "still", "set_edge": True, "props": ["lamp", "chart"],
                  "desc": "A wide shot of the cardboard set: the creature crawls over paper-cut rocks beside a desk lamp."} for i in range(1, 9)}
    assert not admin.validate_storyboard_plan(panels, cuts, 1)
    panels[5]["desc"] = "Wide shot: a chunky translucent clay sea pig stands on the clay seabed with tiny king crabs on its back."
    assert any(p.startswith("Cut 5") and "sea cucumber" in p.lower() for p in admin.validate_storyboard_plan(panels, cuts, 1))
    assert "NICKNAMES ARE NOT ANIMALS" in admin._SB_PROMPT and "never draw land animals" in admin._GRID_HEAD_GENERIC
    # 대본의 장면 아이디어(scene_ko)도 별명만 쓰면 불통과 — 실제 생물을 괄호로
    facts = [{"id": "F1", "fact": "", "fact_jp": "", "quote": ""}]
    cut = {"jp": "幼い頃はセンジュナマコを宿主とします。", "ko": "어릴 때는 해삼을 숙주로 삼습니다.", "fact": "F1",
           "scene_ko": "바다돼지 위아래에 작은 왕게들", "annotation": ""}
    assert any("scene_ko" in p for p in admin.validate_script([cut] * admin.SCRIPT_CUTS, facts))
    cut["scene_ko"] = "바다돼지(해삼) 위아래에 작은 왕게들"
    assert not any("scene_ko" in p for p in admin.validate_script([cut] * admin.SCRIPT_CUTS, facts))


def test_redo_panel_redraws_one_still_cut_and_reassembles(real_copy, monkeypatch):
    from PIL import Image
    sc = json.loads((real_copy / "script.json").read_text(encoding="utf-8"))
    st = admin.load_status("bathynomus_giganteus")
    st["artifacts"].setdefault("video", {})["clips"] = [{"cut": 2, "file": "out/old_stills/c02.mp4", "sec": 4, "motion": "still"}]
    admin._save(admin.status_path("bathynomus_giganteus"), st)
    answers = iter(['{"shot":"wide","props":["lamp","chart"],"desc":"A clay sea pig stands on a painted seabed beside a desk lamp."}',
                    '{"shot":"wide","props":["lamp","chart"],"desc":"A translucent pink deep-sea sea cucumber with stubby tube-feet on a painted clay seabed beside a desk lamp."}'])
    prompts = []

    def ask(p):
        prompts.append(p)
        return next(answers)

    def run(rp):
        req = json.loads(rp.read_text(encoding="utf-8"))
        assert "NOT a grid" in req["items"][0]["prompt"] and "sea cucumber" in req["items"][0]["prompt"]
        out = rp.parent.parent / "out" / req["id"]
        out.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (360, 640), (40, 60, 80)).save(out / "p02.jpg")
        return 0
    called = {}
    monkeypatch.setattr(admin, "assemble", lambda pid: called.setdefault("asm", pid))
    admin.redo_panel("bathynomus_giganteus", 2, "바다돼지는 해삼인데 돼지가 그려짐", ask=ask, run=run)
    assert len(prompts) == 2 and "pig" in prompts[1]                     # 1차 답의 'pig' 를 이유와 함께 돌려보냄
    sc = json.loads((real_copy / "script.json").read_text(encoding="utf-8"))
    c2 = next(c for c in sc["cuts"] if c.get("cut") == 2)
    assert "sea cucumber" in c2["panel_desc"] and c2["keyframe"].endswith("p02.jpg")
    st = admin.load_status("bathynomus_giganteus")
    clip = st["artifacts"]["video"]["clips"][0]
    assert "_stills/" in clip["file"] and (real_copy / clip["file"]).exists() and clip["history"] == ["out/old_stills/c02.mp4"]
    assert called["asm"] == "bathynomus_giganteus"


def test_scheduled_upload_publishes_at_given_kst_time(real_copy):
    """예약 공개(운영자 요청 2026-10-06): 화면의 한국 시간 → 유튜브 publishAt(UTC) · 지금은 비공개로 업로드."""
    import time as _t
    now = _t.time()
    assert admin.parse_publish_at("2026-10-07T19:00", now=_t.mktime((2026, 10, 6, 0, 0, 0, 0, 0, 0))) == "2026-10-07T10:00:00Z"
    with pytest.raises(SystemExit):
        admin.parse_publish_at("2020-01-01T19:00")                     # 지난 시각
    with pytest.raises(SystemExit):
        admin.parse_publish_at(_t.strftime("%Y-%m-%dT%H:%M", _t.gmtime(now + 9 * 3600 + 300)))   # 5분 뒤(KST) — 너무 가까움
    with pytest.raises(SystemExit):
        admin.parse_publish_at("2099-01-01T19:00")                     # 180일 넘음
    st = admin.load_status("bathynomus_giganteus")
    st["artifacts"].setdefault("upload", {})["meta"] = admin._compose_meta(
        json.loads((admin._script_path("bathynomus_giganteus")).read_text(encoding="utf-8")), dict(_META))
    admin._save(admin.status_path("bathynomus_giganteus"), st)
    kst = _t.strftime("%Y-%m-%dT%H:%M", _t.gmtime(now + 9 * 3600 + 2 * 86400))   # 이틀 뒤(KST)
    admin.save_upload_meta("bathynomus_giganteus", {"privacy": "scheduled", "publish_at": kst})
    m = admin.load_status("bathynomus_giganteus")["artifacts"]["upload"]["meta"]
    assert m["privacy"] == "scheduled" and m["publish_at"].endswith("Z")
    got = {}

    def up(path, title, desc, tags=None, privacy=None, category_id=None, publish_at=None):
        got.update(privacy=privacy, publish_at=publish_at)
        return {"url": "https://youtu.be/x", "video_id": "x", "privacy": privacy}
    admin.youtube_upload("bathynomus_giganteus", uploader=up, playlister=lambda *a: {"playlist_id": "p"})
    assert got == {"privacy": "private", "publish_at": m["publish_at"]}
    res = admin.load_status("bathynomus_giganteus")["artifacts"]["upload"]["result"]
    assert res["privacy"] == "scheduled" and res["publish_at"] == m["publish_at"]
    # 공개로 바꾸면 예약 시각은 지워진다
    st = admin.load_status("bathynomus_giganteus"); st["artifacts"]["upload"].pop("result"); admin._save(admin.status_path("bathynomus_giganteus"), st)
    admin.save_upload_meta("bathynomus_giganteus", {"privacy": "public", "publish_at": kst})
    assert "publish_at" not in admin.load_status("bathynomus_giganteus")["artifacts"]["upload"]["meta"]


def test_youtube_body_has_publish_at_only_when_scheduled(monkeypatch):
    sys.path.insert(0, str(Path(admin.__file__).resolve().parents[2]))
    from src.core import youtube_upload as yt
    bodies = []

    class Req:
        def next_chunk(self):
            return None, {"id": "vid"}

    class Vids:
        def insert(self, part, body, media_body):
            bodies.append(body)
            return Req()

    class C:
        def videos(self):
            return Vids()
    monkeypatch.setattr(yt, "has_credentials", lambda: True)
    monkeypatch.setattr(yt, "_client", lambda: C())
    import types
    fake = types.ModuleType("googleapiclient.http")
    fake.MediaFileUpload = lambda *a, **k: None                            # 실제 라이브러리 없이 요청 본문만 확인
    monkeypatch.setitem(sys.modules, "googleapiclient", types.ModuleType("googleapiclient"))
    monkeypatch.setitem(sys.modules, "googleapiclient.http", fake)
    r = yt.upload("v.mp4", "t", "d", privacy="private", publish_at="2026-10-07T10:00:00Z")
    assert bodies[-1]["status"]["publishAt"] == "2026-10-07T10:00:00Z" and bodies[-1]["status"]["privacyStatus"] == "private"
    assert r["privacy"] == "scheduled"
    yt.upload("v.mp4", "t", "d", privacy="public")
    assert "publishAt" not in bodies[-1]["status"] and bodies[-1]["status"]["privacyStatus"] == "public"


def test_glyph_check_works_without_fonttools(monkeypatch):
    """실사고 2026-10-06: 서버에 fontTools 가 없어 조립이 실패 → Pillow 대체 판정으로도 같은 결과."""
    import builtins
    import assemble as A
    real = builtins.__import__

    def imp(name, *a, **k):
        if name.startswith("fontTools"):
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(A, "_CMAP", None)
    monkeypatch.setattr(builtins, "__import__", imp)
    assert A.missing_glyphs("1800年代後半から 水深4152m 第5歩脚") == []
    assert A.missing_glyphs("1800년대") == ["년", "대"]
    monkeypatch.setattr(A, "_CMAP", None)


# ── 왕게 편 실패 대책(운영자 선택 2026-10-09 · 81% 즉시 이탈): A 첫 2초 자동 선택 · B 앞 15초 움직임 · D 핵심 사실 하나 ──
def _still_then_moving(path, still_s, move_s):
    """앞 still_s초는 멈춘 회색 화면, 그 뒤 move_s초는 움직이는 시험 화면(testsrc2)."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=gray:s=720x1280:r=24:d={still_s}",
                    "-f", "lavfi", "-i", f"testsrc2=s=720x1280:r=24:d={move_s}", "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_best_hook_window_picks_the_most_moving_two_seconds():
    import assemble as A
    series = [0.2] * 16 + [6.0] * 16 + [1.0] * 16                  # 0~2초 거의 정지 · 2~4초 크게 움직임 · 4~6초 조금
    assert A.best_hook_window(series, 6.0) == (2.0, 6.0)
    assert A.window_motion([None, 4.0, 2.0] + [None] * 13, 0.0) == 3.0   # 컷 전환으로 뺀 값(None)은 평균에서 제외
    assert A.best_hook_window([], 4.0) == (0.0, 0.0)


def test_pick_hook_measures_real_clip_and_respects_operator(tmp_path):
    """실제 영상: 앞 4초가 멈춘 클립이면 자동 선택은 움직이는 뒷부분 · 운영자가 정한 초는 그대로(움직임만 기록)."""
    import assemble as A
    clip = tmp_path / "c.mp4"; _still_then_moving(clip, 4, 4)
    s = A.motion_series(clip)
    assert 60 <= len(s) <= 66 and all(v is None or v >= 0 for v in s)
    auto = A.pick_hook(clip, {"at": 1.0}, 8)                          # 대본 단계의 「한가운데 2초」 임시값은 무시
    op = A.pick_hook(clip, {"at": 1.0, "at_by": "operator"}, 8)
    assert op == {"at": 1.0, "motion": op["motion"], "by": "operator"} and op["motion"] < 0.5
    assert auto["by"] == "auto" and auto["at"] >= 3.9 and auto["motion"] > op["motion"] + 1.0
    assert None in s                                                   # 정지→움직임 전환 한 장(컷 전환)은 움직임에서 뺐다
    assert A.pick_hook(clip, {"at": 99, "at_by": "operator"}, 8)["at"] == 6.0      # 컷 밖이면 컷 안으로


def test_assemble_returns_used_hook_window(tmp_path):
    import assemble as A
    P = tmp_path / "p"; (P / "out" / "clips").mkdir(parents=True); (P / "out" / "tts").mkdir(parents=True)
    _tiny_clip(P / "out" / "clips" / "c01.mp4", 4, "blue"); _still_then_moving(P / "out" / "clips" / "c02.mp4", 2, 2)
    _silent_wav(P / "out" / "tts" / "body.wav", 6)
    tps = lambda: [{"jp_seg": None, "start": 0.15, "end": 2.5}]
    sc = {"subject": {"scientific_name": "Testus fishus", "jp_name": "テストウオ"},
          "hook": {"cut": 2, "at": 0.0, "question_jp": "青く光る、この生き物は？", "answer_jp": "テストウオ", "type": "identity"},
          "cuts": [{"cut": 1, "jp": "こんにちは。", "tts": "こんにちは。", "sec": 4}, {"cut": 2, "jp": "さようなら。", "tts": "さようなら。", "sec": 4}],
          "timing_v5": [{"cut": 1, "sec": 4, "audio_from": 0.0, "audio_to": 2.5, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()},
                        {"cut": 2, "sec": 4, "audio_from": 2.5, "audio_to": 5.0, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()}]}
    (P / "script.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    info = A.main(str(P), "clips", "tts", "", str(tmp_path / "final.mp4"))
    assert info["hook"]["cut"] == 2 and info["hook"]["by"] == "auto" and info["hook"]["at"] >= 1.8   # 움직이는 뒤 2초
    assert info["hook"]["motion"] > 1.0
    checks = admin.motion_checks(tmp_path / "final.mp4", info["hook"])
    assert checks["hook_motion"]["warn"] and "2번 컷" in checks["hook_motion"]["rule"] and "자동 선택" in checks["hook_motion"]["rule"]
    assert "front_motion" in checks and checks["front_motion"]["warn"]


def test_motion_checks_warn_on_static_opening(tmp_path):
    clip = tmp_path / "s.mp4"; _tiny_clip(clip, 6, "gray")
    ck = admin.motion_checks(clip, {"cut": 1, "at": 0.0, "motion": 1.0, "by": "auto"})
    assert ck["hook_motion"]["ok"] is False and ck["hook_motion"]["value"] == 1.0
    assert ck["front_motion"]["ok"] is False and ck["front_motion"]["value"] < 0.5


def test_edit_hook_fixes_start_only_when_operator_changes_it(v2):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    sc = lambda: json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))   # noqa: E731
    at0 = sc()["hook"]["at"]
    admin.edit_hook("test_fish", {"at": str(at0), "question_ko": "건드리면 빛난다"})          # 페이지는 지금 값을 그대로 다시 보낸다
    assert "at_by" not in sc()["hook"]
    admin.edit_hook("test_fish", {"at": "0.5"})
    assert sc()["hook"]["at"] == 0.5 and sc()["hook"]["at_by"] == "operator"
    admin.edit_hook("test_fish", {"at": ""})
    assert "at_by" not in sc()["hook"]                                                 # 칸을 비우면 다시 자동
    admin.edit_hook("test_fish", {"at": "1", "cut": 8})
    assert sc()["hook"]["at_by"] == "operator"
    admin.edit_hook("test_fish", {"at": str(sc()["hook"]["at"]), "cut": 5})          # 컷만 바꾸면 새 컷에서 자동
    assert "at_by" not in sc()["hook"] and sc()["hook"]["type"] == "line"


def test_storyboard_opening_cuts_must_move():
    cuts = [{"cut": i} for i in range(1, 9)]
    p = " ".join(admin.validate_storyboard_plan(_plan(["wide"] * 8, omni=(3, 5, 6, 8)), cuts, hook_cut=5))
    assert "Cut 1 plays in the first 15 seconds" in p and "Cut 2 plays in the first 15 seconds" in p
    p = " ".join(admin.validate_storyboard_plan(_plan(["wide"] * 8, omni=(1, 2, 3, 4)), cuts, hook_cut=3))
    assert "3 still cuts in a row" in p
    plan = _plan(["wide"] * 8, omni=(1, 2, 5, 8))
    plan[1]["desc"] = "A wide shot of a desk: a clay scientist holds a magnifying glass over a crab figurine."
    assert any("Cut 1 opens the video" in x for x in admin.validate_storyboard_plan(plan, cuts, hook_cut=5))
    plan[1]["desc"] = "Wide shot: the crab figurine strides over paper-cut rocks, legs spread, beside a desk lamp."
    assert admin.validate_storyboard_plan(plan, cuts, hook_cut=5) == []
    assert admin.omni_required(8, 5) == [1, 2, 5] and admin.omni_budget(8, 5) == 4 and admin.omni_budget(2, 2) == 2
    assert "cuts 1, 2, 5 MUST be" in admin._SB_PROMPT.format(style="", creature="", anatomy="", size_note="", n=8, min_wide=5,
                                                             max_close=2, max_omni=4, required="1, 2, 5", hook_cut=5, feedback="",
                                                             cuts="", facts="")
    assert "OPENING" in admin._VID_PROMPT and "{hook_cut}" in admin._VID_PROMPT


def test_script_cut1_must_not_open_with_history():
    facts = [{"id": "F1", "fact": "1880년대 발견 · 200년 산다", "fact_jp": "", "quote": "1880s 200 years"}]
    cut = {"jp": "1880年代、学者はこの生物を調べました。", "ko": "학자가 조사했습니다.", "fact": "F1", "scene_ko": "장면", "annotation": ""}
    later = dict(cut, jp="この生き物は、200年以上生きるといわれます。")
    assert any("カット1" in p and "学者" in p or "1880年" in p for p in admin.validate_script([cut] + [later] * 7, facts))
    assert not any("発見の年" in p for p in admin.validate_script([later] * 8, facts))     # 「200年 산다」 같은 특징은 허용
    assert not any("発見の年" in p for p in admin.validate_script([later] + [cut] * 7, facts))  # 역사는 3번째 컷 이후면 괜찮다(1번 컷만 검사)


def test_core_fact_ties_hook_and_ending():
    facts = [{"id": f"F{i}", "fact": "x", "fact_jp": "", "quote": ""} for i in range(1, 5)]
    cuts = [{"cut": i, "jp": "x", "fact": f} for i, f in enumerate(["F1", "F2", "F2", "F3", "F3", "F2", "F1", "F3"], 1)]
    assert admin.validate_core("F3", {"cut": 5}, cuts, facts) == []
    assert "hook.cut=2" in " ".join(admin.validate_core("F3", {"cut": 2}, cuts, facts))
    assert "最後の3カット" in " ".join(admin.validate_core("F4", {"cut": 1}, [dict(c, fact="F4" if c["cut"] == 1 else c["fact"]) for c in cuts], facts))
    assert "事実リストの番号ではありません" in " ".join(admin.validate_core("", {"cut": 5}, cuts, facts))


def test_identity_question_banned_when_looks_give_it_away():
    cuts = [{"cut": i, "jp": "x"} for i in range(1, 9)]
    facts = [{"id": "F1", "fact": "", "fact_jp": "", "quote": ""}]
    king = {"cut": 4, "question_jp": "エラの中に魚が卵を産む、この生き物は？", "answer_jp": "タラバガニ科"}     # 실제로 올린 왕게 편
    assert admin.hook_type(king["question_jp"]) == "identity"
    assert any("見た目で" in p for p in admin.validate_hook(king, cuts, facts, name="タラバガニ科"))
    fact_q = {"cut": 4, "question_jp": "エラの中に、何を隠している？", "answer_jp": "魚の卵"}
    assert admin.hook_type(fact_q["question_jp"]) == "fact" and admin.validate_hook(fact_q, cuts, facts, name="タラバガニ科") == []
    odd = {"cut": 4, "question_jp": "光る皮を投げ捨てる、この生き物は？", "answer_jp": "首なしチキンモンスター"}
    assert admin.validate_hook(odd, cuts, facts) == []                                   # 생김새로 정체를 모르는 생물은 정체 질문 OK


def test_title_never_contains_the_answer(v2):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    seen = []
    def meta(p):
        seen.append(p)
        title = "青く光る魚テストウオの謎" if len(seen) == 1 else "触ると青く光る、深海の謎"
        return json.dumps(dict(_META, title_jp=title, title_ko="자극을 받으면 파랗게 빛나는 심해의 수수께끼"))
    st = admin.upload_meta("test_fish", ask=meta)
    m = st["artifacts"]["upload"]["meta"]
    assert len(seen) == 2 and "テストウオ" in seen[1] and "Problems in your previous answer" in seen[1]
    assert m["title_jp"].startswith("触ると青く光る、深海の謎") and m["title_jp"].endswith("#テストウオ #深海")   # 종명은 끝 해시태그로만
    assert "SAME LINE" in seen[0] and "触ると、青く光る" in seen[0]                               # 제목도 후킹과 같은 문장으로 시작
    assert "CORE FACT" in seen[0] and "F4: 刺激を受けると青く光る" in seen[0]
    with pytest.raises(ValueError):
        admin.upload_meta("test_fish", ask=lambda p: json.dumps(dict(_META, title_jp="テストウオの秘密")))
    sc = {"subject": {"jp_name": "タラバガニ科", "ko_name": "왕게"}, "hook": {"type": "fact", "answer_jp": "魚の卵", "answer_ko": "물고기 알"}}
    assert admin.title_spoilers(sc) == (["魚の卵"], ["물고기 알"])                       # 사실 질문 편: 정답만 금지(이름은 괜찮음)
    assert admin.species_tags(sc) == ("#タラバガニ科", "#왕게")


def test_answer_card_shows_name_for_fact_question(tmp_path):
    import assemble as A
    out = A.answer_png("エラの中に、何を隠している？", "魚の卵", "Lithodidae", tmp_path / "a.png", name="タラバガニ科")
    assert out.exists()


# ── 후킹 개편(운영자 선택 2026-10-09): 0초 목소리 · 12자 한 줄 · 사실 한 줄 후보 3개 · 흰 글자+빨강 핵심어 · 시청함 % ──
_F = [{"id": "F1", "fact": "수심 2000m", "fact_jp": "水深2000メートル", "quote": "2000 m"}]


def test_hook_line_rules():
    ok = {"pattern": "常識破り", "text_jp": "ナマコなのに、泳ぐ", "key_jp": "泳ぐ", "voice_jp": "ナマコなのに、海の中を泳ぐ"}
    assert admin.validate_hook_line(ok, _F, ["センジュナマコ"]) == []
    bad = lambda **kw: " ".join(admin.validate_hook_line(dict(ok, **kw), _F, ["センジュナマコ"]))   # noqa: E731
    assert "12文字以内" in bad(text_jp="エラの中に魚が卵を産みつける")                           # 22자(왕게 편)
    assert "2行まで" in bad(text_jp="光る、皮を、捨てる", key_jp="光る", voice_jp="光る")
    assert "名前当て" in bad(text_jp="泳ぐ、この生き物は？")
    assert "key_jp" in bad(key_jp="走る")
    assert "voice_jp に key_jp" in bad(voice_jp="ナマコなのに、海の中を進む")
    assert "長すぎます" in bad(voice_jp="ナマコなのに泳ぐという、とても珍しい性質を持っていることで知られている")
    assert "センジュナマコ" in bad(text_jp="センジュナマコ、泳ぐ")
    assert "5000" in bad(text_jp="5000mで、泳ぐ", voice_jp="5000mで泳ぐ")                   # 사실에 없는 숫자
    assert "2000" not in bad(text_jp="2000mで、泳ぐ", voice_jp="2000mで泳ぐ")
    assert "pattern" in bad(pattern="なぞなぞ")
    assert admin.hook_segments("触ると、青く光る") == ["触ると", "青く光る"]


def test_write_script_candidates_and_pick(v2):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    sc = lambda: json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))   # noqa: E731
    hk = sc()["hook"]
    hk["voice_file"], hk["voice_for"] = "out/x/hook.wav", hk["voice_jp"]
    admin._save(admin._script_path("test_fish"), dict(sc(), hook=hk))
    st = admin.edit_hook("test_fish", {"pick": 2})
    h = sc()["hook"]
    assert h["chosen"] == 2 and h["question_jp"] == "光の正体は、魚" and h["key_jp"] == "魚" and h["pattern"] == "正体の反転"
    assert "voice_file" not in h                                          # 문장이 바뀌면 다음 조립 때 목소리를 다시 만든다
    assert st["artifacts"]["script"]["hook"]["chosen"] == 2
    with pytest.raises(SystemExit):
        admin.edit_hook("test_fish", {"pick": 5})


def test_hook_line_png_white_text_red_key_top(tmp_path):
    """흰 글자+검은 테두리, 핵심 단어만 빨강 · 화면 위쪽(생물을 가리지 않게) · 「、」에서만 줄바꿈."""
    import assemble as A
    from PIL import Image
    im = Image.open(A.hook_png("触ると、青く光る", tmp_path / "h.png", key="青く光る")).convert("RGBA")
    px = im.load()
    red = [(x, y) for y in range(0, A.H, 4) for x in range(0, A.W, 4) if px[x, y][3] > 200 and px[x, y][0] > 200 and px[x, y][1] < 70]
    white = [(x, y) for y in range(0, A.H, 4) for x in range(0, A.W, 4) if px[x, y][3] > 200 and min(px[x, y][:3]) > 235]
    assert len(red) > 150 and len(white) > 150
    ink = [y for y in range(0, A.H, 4) if any(px[x, y][3] > 120 for x in range(0, A.W, 8))]
    assert min(ink) > A.H * 0.08 and max(ink) < A.H * 0.40                # 위쪽 띠 안에만(가운데 생물 자리 비움)
    assert min(y for _, y in red) > min(y for _, y in white)              # 빨간 핵심어는 둘째 줄(青く光る)
    old = Image.open(A.hook_png("光る皮を投げ捨てる、この生き物は？", tmp_path / "o.png")).convert("RGBA")   # 옛 편 디자인 유지
    assert old.getbbox()[1] > A.H * 0.15


def test_assemble_line_hook_speaks_from_zero(tmp_path):
    """후킹 개편 편: 맨 앞 0초부터 글자 + 목소리(무음 아님) · 끝 카드 「この生き物は」."""
    import assemble as A
    P = tmp_path / "p"; (P / "out" / "clips").mkdir(parents=True); (P / "out" / "tts").mkdir(parents=True); (P / "out" / "hv").mkdir(parents=True)
    _tiny_clip(P / "out" / "clips" / "c01.mp4", 4, "blue"); _tiny_clip(P / "out" / "clips" / "c02.mp4", 4, "red")
    _silent_wav(P / "out" / "tts" / "body.wav", 6)
    _silent_wav(P / "out" / "hv" / "hook.wav", 2.2)                      # 목소리 대신 소리(2.2초)
    tps = lambda: [{"jp_seg": None, "start": 0.15, "end": 2.5}]
    sc = {"subject": {"scientific_name": "Testus fishus", "jp_name": "テストウオ"},
          "hook": {"cut": 2, "at": 0.0, "type": "line", "question_jp": "触ると、青く光る", "key_jp": "青く光る", "voice_jp": "触れると青く光る",
                   "voice_file": "out/hv/hook.wav", "answer_jp": "テストウオ"},
          "cuts": [{"cut": 1, "jp": "こんにちは。", "tts": "こんにちは。", "sec": 4}, {"cut": 2, "jp": "さようなら。", "tts": "さようなら。", "sec": 4}],
          "timing_v5": [{"cut": 1, "sec": 4, "audio_from": 0.0, "audio_to": 2.5, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()},
                        {"cut": 2, "sec": 4, "audio_from": 2.5, "audio_to": 5.0, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()}]}
    (P / "script.json").write_text(json.dumps(sc, ensure_ascii=False), encoding="utf-8")
    dst = tmp_path / "final.mp4"
    info = A.main(str(P), "clips", "tts", "", str(dst))
    hsec = info["hook"]["len"]
    assert info["hook"]["voice"] and 2.5 <= hsec <= A.HOOK_MAX_S              # 목소리 길이만큼 후킹이 늘어남(최대 3초)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dst)],
                               capture_output=True, text=True).stdout)
    assert abs(dur - (hsec + 6.5 + A.ANSWER_S)) < 0.3
    vol = subprocess.run(["ffmpeg", "-hide_banner", "-t", "2", "-i", str(dst), "-af", "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    mean = float(re.search(r"mean_volume: (-?[\d.]+) dB", vol).group(1))
    assert mean > -40                                                      # 예전 후킹은 -91dB(완전 무음)
    from PIL import Image
    f = tmp_path / "f0.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.04", "-i", str(dst), "-frames:v", "1", str(f)], check=True)
    im = Image.open(f).convert("RGB")
    band = [im.getpixel((x, y)) for y in range(int(A.H * 0.12), int(A.H * 0.35), 6) for x in range(0, A.W, 6)]
    assert sum(1 for r, g, b in band if min(r, g, b) > 225) > 40               # 0초 첫 장면부터 흰 글자


def test_answer_card_label_for_line_hook(tmp_path):
    import assemble as A
    from PIL import ImageChops, Image
    a = Image.open(A.answer_png("触ると、青く光る", "テストウオ", "Testus fishus", tmp_path / "a.png", label="この生き物は"))
    b = Image.open(A.answer_png("触ると、青く光る", "テストウオ", "Testus fishus", tmp_path / "b.png"))
    assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox()      # 라벨이 실제로 다르게 그려짐


def test_ensure_hook_voice_once_per_sentence(v2, monkeypatch):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    calls = []
    base = _fake_runner(v2)

    def run(rp):
        calls.append(json.loads(Path(rp).read_text(encoding="utf-8")))
        return base(rp)
    monkeypatch.setattr(admin, "_RUN_REQUEST", run)
    f1 = admin.ensure_hook_voice("test_fish")
    assert f1 and (v2 / "pilots" / "test_fish" / f1).exists() and calls[0]["items"][0]["tts"]   # 히라가나 낭독문
    assert admin.ensure_hook_voice("test_fish") == f1 and len(calls) == 1                      # 같은 문장이면 다시 안 만듦
    admin.edit_hook("test_fish", {"pick": 1})
    assert admin.ensure_hook_voice("test_fish") != f1 and len(calls) == 2                      # 문장이 바뀌면 새로
    monkeypatch.setattr(admin, "_RUN_REQUEST", lambda rp: 1)
    admin.edit_hook("test_fish", {"pick": 0})
    assert admin.ensure_hook_voice("test_fish") is None                                       # 실패해도 예외 없이 None


def test_save_viewed_records_pattern_and_index(v2):
    admin.new_pilot("test_fish")
    ask, _ = _fake_ai()
    admin.write_script("test_fish", ask=ask, get=_fake_wiki, tts=False)
    admin.main(["save_viewed", "test_fish", "_", json.dumps({"pct": "18.6%"})])
    v = admin.load_status("test_fish")["artifacts"]["upload"]["viewed"]
    assert v["pct"] == 18.6 and v["hook"]["pattern"] == "異常な行動" and v["hook"]["line"] == "触ると、青く光る" and v["hook"]["voice"]
    idx = json.loads((v2 / "pilots" / "index.json").read_text(encoding="utf-8"))
    assert idx["items"][0]["viewed"]["pct"] == 18.6
    for bad in ("abc", "120"):
        with pytest.raises(SystemExit):
            admin.save_viewed("test_fish", {"pct": bad})
    assert admin.hook_pattern_label({}) == "후킹 없음(옛)"
    assert admin.hook_pattern_label({"hook": {"question_jp": "光る皮を投げ捨てる、この生き物は？"}}) == "名前当て(옛)"


# ── 인스타 시험 릴스로 후킹 A·B 겨루기(운영자 선택 2026-10-09: 자동 · 결과 보고 올리기 · 2개) ──────────────────
_SHA = "a" * 40


def _scrolling_clip(path, sec):
    """처음부터 끝까지 고르게 움직이는 화면(시험 무늬가 옆으로 흐름) — 어느 2초를 잘라도 움직임이 비슷하다."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc2=s=1440x1280:r=24:d={sec}",
                    "-vf", "crop=720:1280:x='mod(t*240,720)':y=0", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def _trial_pilot(v2, monkeypatch, cands=None, line=True):
    """작은 실제 편: 컷 2개(2번 컷 = 6초 내내 움직임) · 후킹 후보 3개 · A 완성본을 실제로 조립 · 영상 승인까지."""
    import assemble as A
    pid = "test_fish"
    P = v2 / "pilots" / pid
    for d in ("out/clips", "out/tts", "out/hv", "out/final", "requests"):
        (P / d).mkdir(parents=True, exist_ok=True)
    _tiny_clip(P / "out/clips/c01.mp4", 4, "blue")
    _scrolling_clip(P / "out/clips/c02.mp4", 6)
    _silent_wav(P / "out/tts/body.wav", 8)
    _silent_wav(P / "out/hv/hook.wav", 1.6)
    tps = lambda: [{"jp_seg": None, "start": 0.15, "end": 2.5}]       # noqa: E731
    c = cands or _CANDS
    hook = {"cut": 2, "at": None, "answer_jp": "テストウオ", "answer_ko": "시험어", "candidates": c}
    hook = admin.hook_from_candidate(hook, 0) if line else {"cut": 2, "at": 0.0, "question_jp": "青く光る、この生き物は？",
                                                             "answer_jp": "テストウオ", "type": "identity"}
    if line:
        hook.update(voice_file="out/hv/hook.wav", voice_for=hook["voice_jp"])
    sc = {"subject": {"scientific_name": "Testus fishus", "jp_name": "テストウオ", "ko_name": "시험어"}, "hook": hook, "core": "F4",
          "facts": [{"id": "F4", "fact": "자극을 받으면 파랗게 빛난다", "fact_jp": "刺激を受けると青く光る", "sources": ["https://example.org/a"]}],
          "cuts": [{"cut": 1, "jp": "こんにちは。", "tts": "こんにちは。", "sec": 4, "fact": "F4"},
                   {"cut": 2, "jp": "さようなら。", "tts": "さようなら。", "sec": 6, "fact": "F4"}],
          "timing_v5": [{"cut": 1, "sec": 4, "audio_from": 0.0, "audio_to": 2.5, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()},
                        {"cut": 2, "sec": 6, "audio_from": 2.5, "audio_to": 5.0, "speech_s": 2.5, "lead": 0.15, "local_tps": tps()}]}
    admin._save(P / "script.json", sc)
    info = A.main(str(P), "clips", "tts", "", str(P / "out/final/final.mp4"))
    if line:
        sc["hook"].update(at=info["hook"]["at"], motion=info["hook"]["motion"], at_by=info["hook"]["by"])
        admin._save(P / "script.json", sc)
    st = {"id": pid, "name_ko": "시험어", "sci": "Testus fishus", "created": admin._now(),
          "stages": {s: {"state": "approved", "notes": []} for s in admin.STAGES[:4]} | {"upload": {"state": "working", "notes": []}},
          "artifacts": {"video": {"final": "out/final/final.mp4", "built_at": "2026-10-09T00:00:00Z",
                                  "assemble": {"clips_id": "clips", "tts_id": "tts", "ending": ""},
                                  "clips": [{"cut": 1, "file": "out/clips/c01.mp4", "sec": 4}, {"cut": 2, "file": "out/clips/c02.mp4", "sec": 6}]},
                        "script": {}}}
    admin._save(admin.status_path(pid), st)
    monkeypatch.setattr(admin, "_RUN_REQUEST", _fake_runner(v2))
    monkeypatch.setattr(admin, "_COMMIT_PUSH", lambda msg: _SHA)
    monkeypatch.delenv("IG_ACCESS_TOKEN", raising=False)
    return pid, P


class _FakeIG(dict):
    """가짜 인스타 API — 올린 주소·캡션을 기억하고, 지표는 media_id 별로 돌려준다."""
    def __init__(self, metrics=None, fail_on=None):
        self.posts, self.metrics, self.n = [], metrics or {}, 0
        def post(url, cap):
            self.n += 1
            if fail_on and self.n == fail_on:
                raise RuntimeError("HTTPSConnectionPool: /me?fields=user_id&access_token=SECRET123TOKEN failed")
            self.posts.append({"url": url, "caption": cap})
            return {"media_id": f"m{self.n}", "permalink": f"https://www.instagram.com/reel/R{self.n}/", "username": "deep.sea.test"}
        super().__init__(post=post, insights=lambda mid: {"metrics": dict(self.metrics.get(mid, {})), "errors": {}},
                         probe=lambda: {"ok": True, "username": "deep.sea.test"}, check=lambda url: True)


def _meta_ai(line):
    def ask(p):
        return json.dumps(dict(_META, title_jp=line.replace("、", "") + "深海の謎", title_ko="한국어 제목"))
    return ask


def test_after_video_posts_two_trial_reels_and_waits(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch)
    ig = _FakeIG(); monkeypatch.setattr(admin, "_IG_API", ig)
    a_hook = json.loads((P / "script.json").read_text(encoding="utf-8"))["hook"]
    admin.main(["after_video", pid])
    st = admin.load_status(pid)
    tr = st["artifacts"]["trial"]
    assert tr["state"] == "running" and len(ig.posts) == 2 and tr["username"] == "deep.sea.test"
    urls = {p["url"] for p in ig.posts}
    assert urls == {f"{admin.DASH_URL}/v2file/{_SHA}/{pid}/out/final/final.mp4", f"{admin.DASH_URL}/v2file/{_SHA}/{pid}/{tr['b']['file']}"}
    assert ig.posts[0]["caption"] == ig.posts[1]["caption"]                      # 후킹만 다르게(캡션은 똑같이)
    assert "触ると" not in ig.posts[0]["caption"] and "テストウオ" not in ig.posts[0]["caption"] and "AIによる再現映像" in ig.posts[0]["caption"]
    hb = tr["b"]["hook"]
    assert hb["pattern"] == "常識破り" and hb["question_jp"] == "魚なのに、青く光る" and hb["at_by"] == "trial"   # 틀이 다른 후보
    assert hb["voice_file"] != a_hook["voice_file"] and (P / hb["voice_file"]).exists()
    assert abs(hb["at"] - a_hook["at"]) >= admin.TRIAL_B_GAP_S and hb["motion"] >= admin.TRIAL_B_MOTION * a_hook["motion"]   # 다른 첫 장면
    assert (P / tr["b"]["file"]).exists() and tr["b"]["checks"]["hook_voice"]["ok"] and "hook_motion" in tr["b"]["checks"]
    assert tr["a"]["hook"]["question_jp"] == "触ると、青く光る" and tr["a"]["media_id"] and tr["b"]["permalink"].startswith("https://www.instagram.com/")
    sc = json.loads((P / "script.json").read_text(encoding="utf-8"))
    assert sc["hook"]["question_jp"] == a_hook["question_jp"] and sc["hook"]["at"] == a_hook["at"]     # 대본은 판정 전까지 A 그대로
    assert st["jobs"]["upload"]["status"] == "trial" and "meta" not in st["artifacts"].get("upload", {})  # 제목은 결과 뒤에
    assert st["stages"]["upload"]["state"] == "working" and tr["order"] in (["a", "b"], ["b", "a"])
    idx = json.loads((v2 / "pilots" / "index.json").read_text(encoding="utf-8"))
    assert idx["items"][0]["trial"]["state"] == "running" and idx["items"][0]["trial"]["b"]["line"] == "魚なのに、青く光る"
    dur = lambda f: float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(f)],  # noqa: E731
                                         capture_output=True, text=True).stdout)
    assert abs(dur(P / tr["b"]["file"]) - dur(P / "out/final/final.mp4")) < 0.4      # 본편은 같고 맨 앞만 다름
    n = len(ig.posts)
    admin.after_video(pid)                                                          # 다시 승인돼도 진행 중인 시험은 그대로(또 올리지 않음)
    assert len(ig.posts) == n


def test_trial_decide_rules():
    import datetime as dt
    t0 = dt.datetime(2026, 10, 9, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    tr = lambda a, b: {"posted_at": "2026-10-09T00:00:00Z", "a": {"metrics": a}, "b": {"metrics": b}}   # noqa: E731
    at = lambda h: t0 + h * 3600                                                                         # noqa: E731
    d = admin.trial_decide
    v = lambda n, s=None, w=None: {k: x for k, x in (("views", n), ("reels_skip_rate", s), ("ig_reels_avg_watch_time", w)) if x is not None}  # noqa: E731
    assert d(tr(v(900, 60), v(900, 50)), at(10))["kind"] == "wait"                                    # 24시간 전엔 판정 안 함
    r = d(tr(v(900, 60), v(800, 50)), at(25))
    assert r["kind"] == "win" and r["winner"] == "b" and "10%p" in r["why"]                           # 덜 넘긴 쪽이 이김
    assert d(tr(v(900, 50), v(800, 61)), at(25))["winner"] == "a"
    assert d(tr(v(900, 55), v(800, 53)), at(25))["kind"] == "tie"                                     # 3%p 미만 → A 그대로
    assert d(tr(v(900, 0.62), v(800, 0.48)), at(25))["winner"] == "b"                                 # 0~1 비율로 와도 % 로
    assert d(tr(v(900, 60), v(120, 40)), at(25))["kind"] == "wait"                                    # 조회 300 미만 → 기다림
    assert d(tr(v(900, 60), v(120, 40)), at(49))["winner"] == "b"                                     # 48시간 뒤엔 100회면 판정
    assert d(tr(v(900, 60), v(80, 40)), at(49))["kind"] == "hold"                                     # 그래도 모자라면 보류
    assert d(tr(v(900), v(900)), at(25))["kind"] == "wait"                                            # 넘김 비율 아직 없음
    assert d(tr(v(900, None, 4000), v(900, None, 5000)), at(49))["winner"] == "b"                     # 끝내 없으면 평균 시청 시간
    assert d(tr(v(900, None, 4000), v(900, None, 4200)), at(49))["kind"] == "tie"
    assert d(tr({}, v(900, 50)), at(30))["kind"] == "wait"                                            # 지표를 못 받으면 판정하지 않음


def test_trial_check_b_wins_swaps_hook_video_and_prepares_upload(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch)
    ig = _FakeIG(); monkeypatch.setattr(admin, "_IG_API", ig)
    admin.after_video(pid)
    st = admin.load_status(pid); tr = st["artifacts"]["trial"]
    a_final, b = st["artifacts"]["video"]["final"], tr["b"]
    ig.metrics = {tr["a"]["media_id"]: {"views": 820, "reach": 700, "reels_skip_rate": 61.0, "ig_reels_avg_watch_time": 4100},
                  tr["b"]["media_id"]: {"views": 760, "reach": 650, "reels_skip_rate": 47.5, "ig_reels_avg_watch_time": 5200}}
    admin.trial_check(pid, now=time_after(tr["posted_at"], 10))                     # 10시간: 지표만 갱신, 판정 안 함
    st = admin.load_status(pid)
    assert st["artifacts"]["trial"]["state"] == "running" and st["artifacts"]["trial"]["a"]["metrics"]["views"] == 820
    monkeypatch.setattr(admin, "_gemini_text", _meta_ai(b["hook"]["question_jp"]))
    res = admin.trial_check(None, now=time_after(tr["posted_at"], 26))               # 편 id 없이 = 진행 중인 모든 편
    assert res[0]["kind"] == "win" and res[0]["winner"] == "b"
    st = admin.load_status(pid); tr = st["artifacts"]["trial"]
    sc = json.loads((P / "script.json").read_text(encoding="utf-8"))
    assert tr["state"] == "decided" and tr["winner"] == "b"
    assert sc["hook"]["question_jp"] == "魚なのに、青く光る" and sc["hook"]["at_by"] == "trial" and sc["hook"]["voice_file"] == b["hook"]["voice_file"]
    assert sc["hook_history"][-1]["hook"]["question_jp"] == "触ると、青く光る"
    v = st["artifacts"]["video"]
    assert v["final"] == b["file"] and v["final_a"] == a_final and st["checks"]["hook_voice"]["ok"]
    m = st["artifacts"]["upload"]["meta"]
    assert m["title_jp"].startswith("魚なのに青く光る") and m["privacy"] == "scheduled" and m["publish_at"].endswith("T10:00:00Z")   # 일본 19시
    assert st["stages"]["upload"]["state"] == "review" and st["jobs"]["upload"]["status"] == "done"
    assert st["artifacts"]["script"]["hook"]["question_jp"] == "魚なのに、青く光る"
    stats = admin.hook_pattern_stats()
    assert stats["常識破り"]["wins"] == 1 and stats["異常な行動"]["losses"] == 1 and stats["常識破り"]["skip_avg"] == 47.5
    idx = admin.build_index()                                                       # (명령으로 부르면 끝에 자동으로 만든다)
    assert idx["hook_patterns"]["常識破り"]["wins"] == 1 and idx["items"][0]["trial"]["winner"] == "b"
    import assemble as A                                                            # 다시 조립해도 시험에서 이긴 구간 그대로
    pk = A.pick_hook(P / "out/clips/c02.mp4", sc["hook"], 6.0, sec=2.0)
    assert pk["by"] == "trial" and pk["at"] == round(min(sc["hook"]["at"], 4.0), 2)


def time_after(iso, hours):
    return admin._iso_ts(iso) + hours * 3600


def test_trial_tie_or_hold_keeps_a(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch)
    ig = _FakeIG(); monkeypatch.setattr(admin, "_IG_API", ig)
    admin.after_video(pid)
    tr = admin.load_status(pid)["artifacts"]["trial"]
    ig.metrics = {tr["a"]["media_id"]: {"views": 500, "reels_skip_rate": 55.0}, tr["b"]["media_id"]: {"views": 480, "reels_skip_rate": 53.5}}
    monkeypatch.setattr(admin, "_gemini_text", _meta_ai("触ると、青く光る"))
    admin.trial_check(pid, now=time_after(tr["posted_at"], 25))
    st = admin.load_status(pid)
    sc = json.loads((P / "script.json").read_text(encoding="utf-8"))
    assert st["artifacts"]["trial"]["result"]["kind"] == "tie" and st["artifacts"]["trial"]["winner"] == "a"
    assert sc["hook"]["question_jp"] == "触ると、青く光る" and st["artifacts"]["video"]["final"] == "out/final/final.mp4"
    assert "final_a" not in st["artifacts"]["video"] and st["artifacts"]["upload"]["meta"]["title_jp"].startswith("触ると青く光る")


def test_after_video_without_instagram_key_goes_straight_to_title(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch)
    monkeypatch.setattr(admin, "_IG_API", {})
    monkeypatch.setattr(admin, "_gemini_text", _meta_ai("触ると、青く光る"))
    admin.after_video(pid)
    st = admin.load_status(pid)
    assert st["artifacts"]["trial"]["state"] == "skipped" and "IG_ACCESS_TOKEN" in st["artifacts"]["trial"]["reason"]
    m = st["artifacts"]["upload"]["meta"]
    assert m["title_jp"].startswith("触ると青く光る") and m["privacy"] == "private"         # 시험 없으면 예전처럼(비공개 기본)
    assert st["stages"]["upload"]["state"] == "review" and not list((P / "out").glob("*_trial"))


def test_after_video_old_hook_skips_trial(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch, line=False)
    ig = _FakeIG(); monkeypatch.setattr(admin, "_IG_API", ig)
    monkeypatch.setattr(admin, "_gemini_text", lambda p: json.dumps(_META))
    admin.after_video(pid)
    st = admin.load_status(pid)
    assert st["artifacts"]["trial"]["state"] == "skipped" and "옛 형식" in st["artifacts"]["trial"]["reason"] and not ig.posts


def test_trial_post_failure_falls_back_and_hides_token(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch)
    monkeypatch.setenv("IG_ACCESS_TOKEN", "SECRET123TOKEN")
    ig = _FakeIG(fail_on=2); monkeypatch.setattr(admin, "_IG_API", ig)            # 첫 번째는 올라가고 두 번째에서 실패
    monkeypatch.setattr(admin, "_gemini_text", _meta_ai("触ると、青く光る"))
    admin.after_video(pid)
    raw = (P / "status.json").read_text(encoding="utf-8")
    st = admin.load_status(pid)
    why = st["artifacts"]["trial"]["reason"]
    assert st["artifacts"]["trial"]["state"] == "skipped" and "SECRET123TOKEN" not in raw and "access_token=***" in why
    assert "reel/R1/" in why                                                        # 이미 올라간 1개는 알려 준다
    assert st["artifacts"]["upload"]["meta"]["title_jp"] and st["jobs"]["upload"]["status"] == "done"


def test_trial_skip_by_operator(v2, monkeypatch):
    pid, P = _trial_pilot(v2, monkeypatch)
    ig = _FakeIG(); monkeypatch.setattr(admin, "_IG_API", ig)
    admin.after_video(pid)
    monkeypatch.setattr(admin, "_gemini_text", _meta_ai("触ると、青く光る"))
    admin.main(["trial_skip", pid])
    st = admin.load_status(pid)
    assert st["artifacts"]["trial"]["state"] == "skipped" and st["artifacts"]["trial"]["a"]["media_id"]
    assert st["artifacts"]["upload"]["meta"]["title_jp"].startswith("触ると青く光る") and st["stages"]["upload"]["state"] == "review"
    with pytest.raises(SystemExit):
        st["artifacts"]["trial"]["state"] = "decided"; admin._save(admin.status_path(pid), st); admin.trial_skip(pid)


def test_ig_probe_and_pattern_hint(v2, monkeypatch):
    monkeypatch.setattr(admin, "_IG_API", _FakeIG())
    admin.main(["ig_probe"])
    idx = json.loads((v2 / "pilots" / "index.json").read_text(encoding="utf-8"))
    assert idx["ig"]["ok"] and idx["ig"]["username"] == "deep.sea.test"
    monkeypatch.setenv("IG_ACCESS_TOKEN", "TOKX9")
    bad = _FakeIG(); bad["probe"] = lambda: (_ for _ in ()).throw(RuntimeError("Invalid token TOKX9 access_token=TOKX9"))
    monkeypatch.setattr(admin, "_IG_API", bad)
    r = admin.ig_probe()
    assert not r["ok"] and "TOKX9" not in json.dumps(r, ensure_ascii=False)
    assert admin._pattern_hint() == ""                                             # 시험이 없으면 대본 AI 에 아무것도 안 알림
    for i, (pa, pb, w) in enumerate([("異常な行動", "常識破り", "b"), ("欠けた体", "常識破り", "b"), ("異常な行動", "極端な数字", "a")]):
        admin._save(v2 / "pilots" / f"p{i}" / "status.json", {"id": f"p{i}", "stages": {s: {"state": "approved"} for s in admin.STAGES},
            "artifacts": {"trial": {"state": "decided", "winner": w, "result": {"kind": "win", "winner": w},
                                    "a": {"hook": {"pattern": pa}, "metrics": {}}, "b": {"hook": {"pattern": pb}, "metrics": {}}}}})
    h = admin._pattern_hint()
    assert "常識破り 2勝0敗0分" in h and h.index("常識破り") < h.index("欠けた体") and "型の違う3つ" in h
    seen = []
    ask, _ = _fake_ai()
    admin.new_pilot("test_fish")
    admin.write_script("test_fish", ask=lambda p: (seen.append(p), ask(p))[1], get=_fake_wiki, tts=False)
    assert any("常識破り 2勝0敗0分" in p for p in seen if "構成作家" in p)                # 다음 대본 후보 쓰기에 참고로 들어감


def test_next_publish_slot_is_next_19_jst():
    import datetime as dt
    ts = lambda s: dt.datetime.fromisoformat(s).timestamp()                         # noqa: E731
    assert admin.next_publish_slot(ts("2026-10-09T08:00:00+00:00")) == "2026-10-09T10:00:00Z"    # 17시 → 오늘 19시
    assert admin.next_publish_slot(ts("2026-10-09T09:30:00+00:00")) == "2026-10-10T10:00:00Z"    # 18시 30분 → 내일 19시
    assert admin.next_publish_slot(ts("2026-10-09T12:00:00+00:00")) == "2026-10-10T10:00:00Z"


def test_other_window_for_trial_b():
    s = [3.0] * 16 + [0.2] * 8 + [2.8] * 16                                         # 0~2초 · 3~5초 둘 다 움직임
    at, m = admin._other_window(s, 0.0, 5.0, 2.0)
    assert at >= admin.TRIAL_B_GAP_S and m >= admin.TRIAL_B_MOTION * 3.0
    s2 = [3.0] * 16 + [0.2] * 24                                                    # 다른 곳은 거의 정지 → A 와 같은 곳
    assert admin._other_window(s2, 0.0, 5.0, 2.0) == (0.0, 3.0)


def test_after_video_skips_trial_when_a_has_no_voice(v2, monkeypatch):
    """A 의 맨 앞 목소리 합성이 실패한 채 승인됐으면(무음) B 만 목소리가 있어 불공정 → 시험하지 않고 예전처럼."""
    pid, P = _trial_pilot(v2, monkeypatch)
    st = admin.load_status(pid); st["checks"] = {"hook_voice": {"ok": False}}; admin._save(admin.status_path(pid), st)
    ig = _FakeIG(); monkeypatch.setattr(admin, "_IG_API", ig)
    monkeypatch.setattr(admin, "_gemini_text", _meta_ai("触ると、青く光る"))
    admin.after_video(pid)
    tr = admin.load_status(pid)["artifacts"]["trial"]
    assert tr["state"] == "skipped" and "목소리" in tr["reason"] and not ig.posts
