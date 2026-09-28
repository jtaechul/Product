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
         "desc_jp": "メキシコ湾で見つかった大きな生き物です。", "desc_ko": "멕시코만에서 발견된 큰 생물입니다."}


def test_upload_meta_follows_channel_rules(real_copy):
    st = admin.upload_meta("bathynomus_giganteus", ask=lambda p: json.dumps(_META))
    m = st["artifacts"]["upload"]["meta"]
    assert m["title_jp"].endswith("#ダイオウグソクムシ #深海") and m["title_jp"].count("#") == 2
    assert "#shorts" not in (m["title_jp"] + m["desc_jp"]).lower()
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

    def fake(path, title, desc, tags=None, privacy="private"):
        calls.append((title, privacy, tags))
        return {"url": "https://youtu.be/TEST", "video_id": "TEST", "privacy": privacy}
    admin.youtube_upload("bathynomus_giganteus", uploader=fake)
    assert calls and calls[0][1] == "private" and calls[0][2] == ["ダイオウグソクムシ", "深海"]
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
