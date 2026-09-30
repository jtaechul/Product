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
_GOOD = [("1977年、潜水艇アルビンが深海で見つけた魚がいます。", "F1"), ("すんでいるのは水深2000メートルより深い海。", "F2"),
         ("その名は、テストウオといいます。", "F1"), ("大きさは30センチほどになります。", "F3"),
         ("刺激を受けると、体が青く光ります。", "F4"), ("食べるのは、上から降ってくるマリンスノー。", "F5"),
         ("光の届かない世界で、静かに暮らしています。", "F2"), ("今日も暗い海の底で、青い光がまたたきます。", "F4")]


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
            hook = {"cut": 5, "question_jp": "青く光る、この生き物は？", "question_ko": "파랗게 빛나는 이 생물은?",
                    "answer_jp": "テストウオ", "answer_ko": "시험어"}
            return json.dumps({"cuts": cuts, "hook": hook})
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
    assert len(a["cuts"]) == 8 and a["cuts"][0]["facts"][0]["id"] == "F1" and a["crosscheck"]["issues"] == []
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
    admin.main(["edit_hook", "test_fish", "_", json.dumps({"cut": 4, "at": 99, "question_jp": "30センチの、この魚は？", "answer_jp": "テストウオ"})])
    sc = json.loads((v2 / "pilots" / "test_fish" / "script.json").read_text(encoding="utf-8"))
    assert sc["hook"]["cut"] == 4 and sc["hook"]["question_jp"] == "30センチの、この魚は？"
    assert sc["hook"]["at"] <= sc["cuts"][3]["sec"] - 2 and len(sc["hook_history"]) == 1     # 시작 초는 컷 안으로
    with pytest.raises(SystemExit):                                                     # 정답 이름이 질문에 들어가면 거절
        admin.edit_hook("test_fish", {"question_jp": "テストウオは何をする？"})


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
        return json.dumps({"panels": {str(i): f"Panel {i}: miniature deep-sea set, the creature drifts, camera three-quarter, warm practical light." for i in range(1, 9)}})
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
    for k in ("GEMINI_API_KEY", "GOOGLE_TTS_KEY", "YOUTUBE_REFRESH_TOKEN", "IN_ACTION", "IN_PILOT", "IN_STAGE", "IN_NOTE"):
        assert k in env, k
    assert "ffmpeg" in steps["준비"]["run"] and "janome" in steps["준비"]["run"]
    run1, run2 = steps["진행 중 먼저 기록"]["run"], steps["버튼 실행"]["run"]
    assert "job_start" in run1 and "ci_commit.sh" in run1
    for a in ("write_script", "write_storyboard", "make_video"):           # 키가 없는 첫 단계에서 유료 작업을 돌리면 안 된다
        assert f"admin.py {a}" not in run1, a
    for a in ("write_script", "write_storyboard", "make_video", "edit_hook", "recut_approve", "upload_meta", "save_meta"):
        assert a in run2, a
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
