"""v2 관리자 페이지의 '버튼'을 실제로 수행하는 도구 (운영자 확정 2026-09-27).

관리자 페이지(worker/index.mjs)는 파일을 직접 쓰지 않는다. 버튼을 누르면 `v2-admin.yml` 워크플로가
이 도구를 실행하고, 결과(status.json 등)를 커밋한다 → 페이지는 그 파일을 읽어 다시 그린다.

한 편 = 한 폴더(`v2/pilots/<id>/`) · 진행 상태 = `status.json` 하나. 단계는 5개, 승인 관문은 4개:
  topic(주제 선택) → script(대본 ✔관문1) → storyboard(이미지 ✔관문2) → video(완성본 ✔관문3) → upload(업로드 전 확인 ✔관문4)
앞 단계가 승인되기 전에는 다음 단계가 잠겨 있다(돈이 드는 단계 보호).

단계 상태: locked(잠김) · working(작업 중) · review(승인 대기) · revise(수정 요청됨) · approved(승인)

사용:
  python admin.py new <id>                      # 주제 후보(topics.json)에서 새 편 시작
  python admin.py approve <id> <stage> [메모]
  python admin.py revise  <id> <stage> <메모>   # 수정 요청(다음 작업이 반영)
  python admin.py redo    <id> <stage> [메모]   # 단계 전체 다시 하기 요청
  python admin.py redo_cut <id> <컷번호> [메모]  # 그 컷만 영상 재생성(유료) → 재조립까지
  python admin.py assemble <id>                 # 완성본 다시 조립 + 자동 검사
  python admin.py write_script <id> [수정 요청]  # 대본 자동 작성(출처 → 원문 확인된 사실 → 대본 → 검사 → 미리듣기 → 승인 대기)
  python admin.py write_storyboard <id> [수정 요청]  # 스토리보드 자동(참조 실사 → 생물 카드 → 실사 대조 → 콘티 격자 → 승인 대기)
  python admin.py make_video <id> [수정 요청]    # 영상 자동(컷별 지시문 → Omni → 조립 → 검사 → 승인 대기 · 'N번'이면 그 컷만)
  python admin.py stats [id]                    # 유튜브 실적(조회·시청 지속·구독 전환) 가져오기 — 재생목록·실적 권한 토큰 필요
  python admin.py job_start <id> <stage> [설명]  # 자동 작업 '진행 중' 기록(워크플로가 긴 작업 전에 먼저 커밋)
  python admin.py job_fail <id> <action>        # 워크플로가 중간에 죽으면 진행 중 기록을 '실패'로
  python admin.py ready <id> <stage> [메모]      # 작업 결과가 나왔음 → 승인 대기로
  python admin.py edit_line <id> <컷> '<json>'   # 컷 대사 수정(대본만 · 영상은 안 바뀜)
  python admin.py apply_lines <id>              # 수정한 대사를 영상에 반영(나레이션 다시 읽기 + 재조립만)
  python admin.py edit_hook <id> _ '<json>'     # 후킹 질문·정답·발췌 컷 수정(대본만 · 영상은 재조립 때 반영)
  python admin.py crosscheck <id>               # AI 교차 검사(대본 전체 × 사실 전체 — 모순·범위·근거 없음)
  python admin.py recut_plan <id> <컷> '<json>'  # 컷 수정 방향 → 샷 계획 + 콘티(영상은 안 만듦)
  python admin.py recut_approve <id> <컷>        # 콘티 승인 → 샷별 영상 → 한 컷 합성 → 재조립
  python admin.py after_video <id>              # 완성본 승인 뒤: 시험 릴스(후킹 A·B)로 겨루기 시작 — 못 하면 바로 제목·설명
  python admin.py trial_check [id]              # 시험 릴스 결과 가져오기·판정(24~48시간 · 이긴 후킹으로 제목·설명·예약 공개 준비)
  python admin.py trial_skip <id>               # 시험 건너뛰고 지금 후킹으로 진행
  python admin.py trial_cancel <id> [이유]       # 진행 중인 시험 무효(다른 계정에 올라감 등 — 그 결과로 판정 안 함)
  python admin.py trial_repost <id>             # 무효가 된 시험을 ABYSS(@abyss_0cean)에 다시 올리기(이미 만든 A·B 그대로)
  python admin.py ig_probe                      # 인스타 연결 점검(게시 없음)
  python admin.py topics                        # 주제 후보 목록(topics.json) 갱신
  python admin.py index                         # 편 목록(index.json) 갱신
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

V2 = Path(__file__).resolve().parents[1]
ROOT = V2.parent
PILOTS = V2 / "pilots"
STAGES = ["topic", "script", "storyboard", "video", "upload"]
STAGE_KO = {"topic": "주제 선택", "script": "대본", "storyboard": "스토리보드", "video": "영상 제작", "upload": "업로드"}
OMNI_USD_PER_SEC = 0.10                     # Omni Flash 720p 초당 약 $0.10(실측 가격표)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def status_path(pid: str) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", pid or ""):
        raise SystemExit(f"잘못된 편 id: {pid!r}")
    return PILOTS / pid / "status.json"


def load_status(pid: str) -> dict:
    st = _load(status_path(pid))
    if not st:
        raise SystemExit(f"status.json 없음: {pid}")
    return st


def _note(st: dict, stage: str, kind: str, text: str) -> None:
    st["stages"][stage].setdefault("notes", []).append({"at": _now(), "kind": kind, "text": text or ""})


# ── 버튼 동작 ─────────────────────────────────────────────────────────────
def approve(pid: str, stage: str, memo: str = "") -> dict:
    st = load_status(pid)
    s = st["stages"][stage]
    if s["state"] == "approved":                             # ★두 번 눌러도 실패로 만들지 않는다(실사고 2026-10-06: 반영이 늦어 다시 누름)
        print(f"{STAGE_KO[stage]}은(는) 이미 승인되어 있습니다 — 그대로 둡니다")
        return st
    if s["state"] != "review":
        raise SystemExit(f"{STAGE_KO[stage]}은(는) 지금 승인할 수 없습니다(상태: {s['state']}) — 결과가 나온 뒤(승인 대기)에만 승인")
    if stage == "upload":                                   # ★업로드 단계의 승인 = 실제 유튜브 업로드(실패하면 승인 안 됨)
        if memo.strip().startswith("{"):                     # ★화면에 보이는 값 그대로 올린다(저장 버튼을 안 눌렀어도)
            save_upload_meta(pid, json.loads(memo))           #   실사고: '공개'를 골랐는데 저장 전 값(비공개)으로 올라감
            memo = ""
        youtube_upload(pid)
        st = load_status(pid)
        s = st["stages"][stage]
    s.update(state="approved", approved_at=_now())
    _note(st, stage, "approve", memo)
    i = STAGES.index(stage)
    if i + 1 < len(STAGES):                                   # 다음 단계 잠금 해제
        nxt = st["stages"][STAGES[i + 1]]
        if nxt["state"] == "locked":
            nxt["state"] = "working"
    _save(status_path(pid), st)
    # ★완성본 승인 뒤의 일(시험 릴스로 후킹 겨루기 → 이긴 후킹으로 제목·설명)은 `after_video` 가 한다
    #   (워크플로 '버튼 실행' 단계 — 키가 있는 곳. 승인 자체는 키 없는 첫 단계에서 바로 반영 · 2026-10-06).
    #   실사고 2026-10-09: 승인을 첫 단계로 옮긴 뒤 여기서 부르던 제목 자동 작성이 키가 없어 조용히 실패하고 있었다.
    return st


def revise(pid: str, stage: str, memo: str, kind: str = "revise") -> dict:
    st = load_status(pid)
    s = st["stages"][stage]
    if s["state"] == "locked":
        raise SystemExit(f"{STAGE_KO[stage]}은(는) 아직 잠겨 있습니다 — 앞 단계를 먼저 승인하세요")
    s["state"] = "revise"
    _note(st, stage, kind, memo)
    # 승인했던 단계를 되돌리면 뒤 단계도 다시 잠근다(고친 대본으로 만든 적 없는 영상이 승인된 채 남지 않게)
    for later in STAGES[STAGES.index(stage) + 1:]:
        if st["stages"][later]["state"] != "locked":
            st["stages"][later]["state"] = "locked"
            _note(st, later, "auto", f"앞 단계({STAGE_KO[stage]}) 수정 요청으로 다시 잠김")
    _save(status_path(pid), st)
    return st


def new_pilot(pid: str) -> dict:
    p = status_path(pid)
    if p.exists():
        raise SystemExit(f"이미 있는 편입니다: {pid}")
    topic = next((t for t in (_load(V2 / "topics.json", {}) or {}).get("topics", []) if t["id"] == pid), None)
    if not topic:
        raise SystemExit(f"주제 후보에 없는 id: {pid}")
    st = {
        "id": pid, "name_ko": topic["name_ko"], "sci": topic["sci"], "created": _now(),
        "stages": {s: {"state": "locked", "notes": []} for s in STAGES},
        "topic": topic, "artifacts": {}, "checks": {},
    }
    st["stages"]["topic"].update(state="approved", approved_at=_now())
    st["stages"]["script"]["state"] = "working"
    _note(st, "topic", "approve", "운영자가 주제로 선택")
    _save(p, st)
    build_index()
    return st


def redo_cut(pid: str, cut: int, memo: str = "") -> dict:
    """그 컷만 Omni로 다시 만든다(원래 요청서의 시작 이미지·프롬프트 그대로) → 재조립 + 자동 검사."""
    st = load_status(pid)
    vid = st["stages"]["video"]
    if vid["state"] == "locked":
        raise SystemExit("영상 단계가 잠겨 있습니다 — 스토리보드를 먼저 승인하세요")
    art = st["artifacts"].get("video", {})
    clip = next((c for c in art.get("clips", []) if int(c["cut"]) == int(cut)), None)
    if not clip:
        raise SystemExit(f"{cut}번 컷이 없습니다")
    pilot = PILOTS / pid
    if clip.get("motion") == "still" or "_stills/" in clip["file"]:
        # 혼합 제작의 무료 줌인 컷 → 이 컷만 영상 AI(Omni)로 바꿔 만든다(같은 그림을 다시 확대해도 결과가 같으므로)
        sc = _load(_script_path(pid))
        for c in sc["cuts"]:
            if c.get("cut") == int(cut):
                c["motion"] = "omni"
        _save(_script_path(pid), sc)
        _note(st, "video", "redo_cut", f"{cut}번 컷: 무료 줌인 → 영상 AI로 바꿔 다시 만듦. {memo}".strip())
        _save(status_path(pid), st)
        return make_video(pid, f"{int(cut)}번 컷")
    # 그 컷을 만든 요청서(혼합 제작은 컷마다 요청서가 다를 수 있어 파일 경로에서 찾는다)
    m = re.match(r"out/([^/]+)/", clip["file"])
    src = _load(pilot / "requests" / f"{m.group(1) if m else art['clips_request']}.json") or _load(pilot / "requests" / f"{art['clips_request']}.json")
    item = next(i for i in src["items"] if i["name"] == f"c{int(cut):02d}")
    rid = f"r{time.strftime('%m%d%H%M', time.gmtime())}_c{int(cut):02d}"
    req = {k: v for k, v in src.items() if k != "items"}
    req.update(id=rid, purpose=f"관리자 페이지 '이 컷만 다시 만들기' — {cut}번 컷. 메모: {memo}", items=[item])
    rp = pilot / "requests" / f"{rid}.json"
    _save(rp, req)
    r = subprocess.run([sys.executable, str(V2 / "tools" / "run_request.py"), str(rp)], cwd=str(ROOT))
    newf = pilot / "out" / rid / f"c{int(cut):02d}.mp4"
    if r.returncode != 0 or not newf.exists():
        _note(st, "video", "error", f"{cut}번 컷 재생성 실패(요청 {rid})")
        _save(status_path(pid), st)
        raise SystemExit(f"{cut}번 컷 재생성 실패")
    clip.setdefault("history", []).append(clip["file"])
    clip["file"] = str(newf.relative_to(pilot))
    sec = float(clip.get("sec") or 0)
    st.setdefault("cost", {}).setdefault("spent", []).append(
        {"at": _now(), "what": f"{cut}번 컷 재생성", "usd": round(sec * OMNI_USD_PER_SEC, 2)})
    _note(st, "video", "redo_cut", f"{cut}번 컷 다시 만듦. {memo}".strip())
    _save(status_path(pid), st)
    return assemble(pid)


def assemble(pid: str) -> dict:
    """완성본 조립(assemble.py) + 자동 검사 → 영상 단계를 '승인 대기'로."""
    st = load_status(pid)
    pilot = PILOTS / pid
    a = st["artifacts"]["video"]
    asm = a["assemble"]
    sys.path.insert(0, str(V2 / "tools"))
    import assemble as A                                     # noqa: E402
    import karaoke                                           # noqa: E402
    over = {int(c["cut"]): str(pilot / c["file"]) for c in a.get("clips", [])}
    dst = pilot / a["final"]
    try:
        font = karaoke.verify_font()                         # ★자막 글꼴이 이 서버에서 실제로 그려지는지 먼저 확인
    except karaoke.SubtitleFontError as e:                   # 깨지면 영상을 만들지 않고, 승인 대기로도 올리지 않는다
        st["checks"] = {"at": _now(), "subtitle_font": {"ok": False, "value": str(e)[:200],
                                                        "rule": "자막 글꼴이 실제로 그려질 것(네모 □ 금지)"}}
        _note(st, "video", "error", "자막 글꼴 검사 불통과 — 영상을 만들지 않았습니다: " + str(e)[:160])
        _save(status_path(pid), st)
        raise SystemExit(str(e))
    sc = _load(_script_path(pid)) or {}
    try:                                                     # ★화면 글자(주석·후킹·정답) 글꼴 검사 — 없는 글자는 네모 □(실사고 2026-10-05)
        for c in sc.get("cuts", []):
            A.check_glyphs(str(c.get("annotation") or ""), f"{c.get('cut')}번 컷 주석")
        hk = sc.get("hook") or {}
        A.check_glyphs(str(hk.get("question_jp") or "") + str(hk.get("answer_jp") or "")
                       + str((sc.get("subject") or {}).get("jp_name") or ""), "후킹·정답")
    except A.GlyphError as e:
        st["checks"] = {"at": _now(), "screen_text": {"ok": False, "value": str(e)[:200],
                                                     "rule": "화면 글자가 글꼴에 모두 있을 것(한국어 주석 금지 · 네모 □ 금지)"}}
        _note(st, "video", "error", "화면 글자 검사 불통과 — 영상을 만들지 않았습니다: " + str(e)[:160])
        _save(status_path(pid), st)
        raise SystemExit(str(e))
    voice = ensure_hook_voice(pid, sc) if (sc.get("hook") or {}).get("voice_jp") else None   # ★0초부터 목소리(2026-10-09)
    ending = "" if sc.get("hook") else str(pilot / asm["ending"])   # ★후킹 편은 공용 엔딩 대신 [후킹][본편][정답 카드]
    dst.parent.mkdir(parents=True, exist_ok=True)           # 빈 폴더는 git에 안 남아 로컬 재조립 때 없을 수 있다(실측 ffmpeg 254)
    info = A.main(str(pilot), asm["clips_id"], asm["tts_id"], ending, str(dst), overrides=over) or {}
    used = info.get("hook")
    if used and sc.get("hook"):                              # 실제로 쓴 후킹 구간을 대본에 남긴다(페이지 「발췌: N번 컷 X초부터」가 사실이 되게)
        sc["hook"].update(at=used["at"], motion=used["motion"], at_by=used["by"])
        _save(_script_path(pid), sc)
    st = load_status(pid)
    if used and sc.get("hook"):
        _sync_script_artifacts(st, sc)
    a = st["artifacts"]["video"]
    st["artifacts"].get("script", {}).pop("hook_pending", None)
    tmv = (sc.get("timing_v5") or [])
    body_s = sum(min(float(t["sec"]), float(t.get("lead", 0.15)) + float(t.get("speech_s") or t["sec"]) + A.TAIL_S) for t in tmv) \
        or sum(float(c.get("sec") or 0) for c in a.get("clips", []))
    st["checks"] = auto_checks(dst, body_s=body_s)
    st["checks"]["subtitle_font"] = {"ok": True, "value": font["font_file"],
                                     "rule": "자막 글꼴이 실제로 그려질 것(네모 □ 금지) — 조립 직전 이 서버에서 검사"}
    st["checks"]["screen_text"] = {"ok": True, "value": "주석·후킹·정답 글자 모두 글꼴에 있음",
                                   "rule": "화면 글자가 글꼴에 모두 있을 것(한국어 주석 금지 · 네모 □ 금지)"}
    st["checks"].update(motion_checks(dst, used))
    if (sc.get("hook") or {}).get("voice_jp"):
        st["checks"]["hook_voice"] = {"ok": bool(voice and (used or {}).get("voice")), "value": sc["hook"]["voice_jp"],
                                      "rule": "후킹 한 줄을 0초부터 목소리로 읽기(실패하면 맨 앞이 무음 — 「완성본 다시 조립」으로 다시 시도)"}
    st["stages"]["video"]["state"] = "review"
    a["built_at"] = _now()
    _save(status_path(pid), st)
    return st


# ── 컷별 대사 수정(운영자 확정 2026-09-28) ────────────────────────────────
# ★대사를 고쳐도 영상은 자동으로 바뀌지 않는다: edit_line 은 대본(script.json)만 고치고 '미반영'으로 표시한다.
#   영상에 넣으려면 운영자가 따로 apply_lines(「수정한 대사 영상에 반영」)를 눌러야 하고, 그때도 **나레이션 다시 읽기 +
#   재조립만** 한다(약 $0.01). 영상 컷은 절대 다시 만들지 않는다 — 새 대사가 그 컷 길이에 안 들어가면 멈추고 알려 준다.
MARGIN_S = 0.6                                              # 컷 길이 = 나레이션 + 여유 0.6초 이상(운영자 확정 규칙)
_PUNCT = re.compile(r"(?<=[、。！？!?])")


def _chunks(text: str) -> list[str]:
    return [p.strip() for p in _PUNCT.split(text or "") if p.strip()]


def auto_reading(jp: str) -> str:
    """표시문(jp) → 낭독문(히라가나). 형태소 분석(Janome) 읽기를 히라가나로 바꾼다. 읽기가 없는 것(숫자·기호)은 그대로 둔다
    (TTS가 숫자는 제대로 읽는다). 운영자가 읽기를 직접 적으면 그걸 쓴다."""
    from janome.tokenizer import Tokenizer
    out = []
    for t in Tokenizer().tokenize(jp):
        r = t.reading if t.reading and t.reading != "*" else t.surface
        out.append("".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in r))
    return "".join(out)


def _script_path(pid: str) -> Path:
    return PILOTS / pid / "script.json"


def _sync_script_artifacts(st: dict, sc: dict) -> None:
    """관리자 페이지가 보는 컷 목록(status.artifacts.script.cuts)을 script.json 에서 다시 만든다."""
    tm = {t["cut"]: t for t in sc.get("timing_v5", [])}
    cuts = []
    for c in sc["cuts"]:
        if "tts" not in c:
            continue
        t = tm.get(c["cut"], {})
        cuts.append({"cut": c["cut"], "jp": c["jp"], "ko": c.get("ko", ""), "tts": c["tts"], "fact": c.get("fact", ""),
                     "sec": t.get("sec"), "speech_s": t.get("speech_s"), "pending": bool(c.get("pending_edit")),
                     "facts": facts_for(sc, c.get("fact", ""))})
    st.setdefault("artifacts", {}).setdefault("script", {})["cuts"] = cuts
    st["artifacts"]["script"]["pending_lines"] = [c["cut"] for c in cuts if c["pending"]]
    st["artifacts"]["script"]["hook"] = sc.get("hook")
    st["artifacts"]["script"]["core"] = (facts_for(sc, str(sc.get("core") or "")) or [None])[0]   # 핵심 사실 하나(D)


def facts_for(sc: dict, ids: str) -> list[dict]:
    """컷이 근거로 든 F번호(예: 'F3,F9')의 원문·출처 — 관리자 페이지에서 대사 바로 옆에 보여준다(검증 ②)."""
    by = {f["id"]: f for f in sc.get("facts", [])}
    return [{"id": i, "fact": by[i]["fact"], "sources": by[i].get("sources", []),
             **({"quote": by[i]["quote"]} if by[i].get("quote") else {}),
             **({"source_title": by[i]["source_title"]} if by[i].get("source_title") else {})}
            for i in re.findall(r"F\d+", ids or "") if i in by]


# ── 검증 ① AI 교차 검사(운영자 확정 2026-09-28) ─────────────────────────────
# 줄 하나를 자기 근거(F번호) 하나와만 대조하면, 대본 안의 **다른 줄·다른 사실과의 모순**을 놓친다
# (실사고: 2번 컷 "분류상 갯강구에 가깝다" ↔ 3번 컷 "공벌레 무리 중 세계 최대" — 출처는 "등각류 전체 중 최대").
# → 대본 전체 + 사실 전체를 한 번에 AI에게 주고 모순·근거 없음·범위 착오를 찾게 한다. 결과는 관리자 페이지에 빨간 표시.
_CC_PROMPT = """あなたは科学ドキュメンタリーの厳格なファクトチェッカーです。
下の「事実リスト」(出典つき)だけを根拠に、ナレーション台本の各カットを検査してください。
特に次の3種類の誤りを探します:
1. contradiction: 台本の中で、あるカットの主張が別のカットの主張や事実リストと矛盾している
   (例: 「分類上はフナムシに近い」と言った後で「ダンゴムシの仲間で世界最大」と言う)
2. scope: 比較・分類の範囲がずれている(出典は「等脚類全体で最大」なのに台本は「ダンゴムシの仲間で最大」など)
3. unsupported: 事実リストにない数字・断定・誇張
問題がなければ issues は空にしてください。推測で問題を作らないこと。
出力は JSON のみ:
{"issues":[{"cut":カット番号,"type":"contradiction|scope|unsupported","problem_ko":"무엇이 문제인지 한국어로 쉽게 1~2문장",
"facts":["F3"],"suggestion_jp":"直した台詞(日本語)","suggestion_ko":"고친 대사(한국어)"}]}

# 事実リスト
{facts}

# 台本
{cuts}
"""


def _cc_parse(txt: str) -> list[dict]:
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        raise ValueError("JSON 없음")
    out = []
    for it in json.loads(m.group(0)).get("issues", []):
        try:
            out.append({"cut": int(it["cut"]), "type": str(it.get("type", "")), "problem_ko": str(it.get("problem_ko", "")),
                        "facts": [str(x) for x in it.get("facts", [])],
                        "suggestion_jp": str(it.get("suggestion_jp", "")), "suggestion_ko": str(it.get("suggestion_ko", ""))})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def crosscheck(pid: str, ask=None) -> dict:
    """대본 전체 교차 검사 → status.artifacts.script.crosscheck 에 저장. 실패해도 멈추지 않는다(결과에 오류 표시).
    ask: 테스트용 대체 함수(prompt → 응답 텍스트)."""
    st = load_status(pid)
    sc = _load(_script_path(pid))
    if not sc or not sc.get("cuts"):                        # 대본이 아직 없으면 검사할 것이 없다
        return st
    facts = "\n".join(f"{f['id']}: {f['fact']}" for f in sc.get("facts", []))
    cuts = "\n".join(f"カット{c['cut']} [根拠 {c.get('fact', '')}] {c['jp']}" for c in sc["cuts"] if "tts" in c)
    prompt = _CC_PROMPT.replace("{facts}", facts).replace("{cuts}", cuts)
    res = {"at": _now()}
    try:
        txt = (ask or _gemini_text)(prompt)
        res["model"] = _TEXT_MODEL or "test"
        res["issues"] = _cc_parse(txt)
    except Exception as e:                                   # noqa: BLE001 — 검사 실패가 제작을 막지 않게
        res["error"] = f"AI 교차 검사 실패: {str(e)[:160]}"
    st.setdefault("artifacts", {}).setdefault("script", {})["crosscheck"] = res
    n = len(res.get("issues", []))
    _note(st, "script", "crosscheck", res.get("error") or (f"AI 교차 검사: 의심 {n}건" if n else "AI 교차 검사: 문제 없음"))
    _save(status_path(pid), st)
    return st


TEXT_MODEL_PREFS = ["gemini-3-pro-preview", "gemini-3-pro", "gemini-3.1-pro-preview", "gemini-2.5-pro",
                    "gemini-3-flash-preview", "gemini-2.5-flash"]
_TEXT_MODEL = None


def pick_text_model(names: list[dict], prefs: list[str] = TEXT_MODEL_PREFS) -> str | None:
    """서버가 실제로 제공하는 모델 목록에서 고른다(고정 이름은 퇴역하면 404 — 실사고 2026-09-28).
    ① 선호 목록 순서 ② 없으면 이름에 'pro'가 든 가장 최신 텍스트 모델 ③ 그다음 'flash'."""
    ok = []
    for m in names:
        n = m.get("name", "").split("/")[-1]
        if "generateContent" not in (m.get("supportedGenerationMethods") or []):
            continue
        if any(x in n for x in ("image", "tts", "embedding", "omni", "veo", "audio", "live", "vision", "aqa", "learnlm")):
            continue
        ok.append(n)
    for n in prefs:
        if n in ok:
            return n
    for tag in ("pro", "flash"):
        c = sorted((n for n in ok if tag in n), reverse=True)
        if c:
            return c[0]
    return None


def _gemini_text(prompt: str, temperature: float = 0, images: list | None = None) -> str:
    """images: 이미지 파일 경로 목록(비전 — 참조 실사·생물 카드 대조)."""
    import base64
    import os
    import urllib.request
    global _TEXT_MODEL
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 없음")
    if not _TEXT_MODEL:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                                     headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=60) as r:
            _TEXT_MODEL = pick_text_model(json.loads(r.read()).get("models", []))
        if not _TEXT_MODEL:
            raise RuntimeError("사용 가능한 텍스트 모델 없음")
    parts = [{"text": prompt}]
    for im in images or []:
        im = Path(im)
        parts.append({"inline_data": {"mime_type": "image/png" if im.suffix.lower() == ".png" else "image/jpeg",
                                      "data": base64.b64encode(im.read_bytes()).decode()}})
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"temperature": temperature, "responseMimeType": "application/json"}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{_TEXT_MODEL}:generateContent",
        data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        j = json.loads(r.read())
    return "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])


def edit_line(pid: str, cut: int, jp: str, ko: str = "", tts: str = "") -> dict:
    jp, ko, tts = (jp or "").strip(), (ko or "").strip(), (tts or "").strip()
    if not jp:
        raise SystemExit("대사(일본어)가 비어 있습니다")
    st = load_status(pid)
    sc = _load(_script_path(pid))
    c = next((x for x in sc["cuts"] if x.get("cut") == int(cut) and "tts" in x), None)
    if not c:
        raise SystemExit(f"{cut}번 컷이 없습니다")
    reading = tts or auto_reading(jp)
    if len(_chunks(reading)) != len(_chunks(jp)):          # 자막 조각 수 = 낭독 조각 수(카라오케 규칙)
        raise SystemExit(f"읽기 문장부호 수가 대사와 다릅니다(대사 {len(_chunks(jp))}조각 · 읽기 {len(_chunks(reading))}조각)")
    c.setdefault("line_history", []).append({"at": _now(), "jp": c["jp"], "ko": c.get("ko", ""), "tts": c["tts"]})
    c.update(jp=jp, tts=reading, pending_edit=True)
    if ko:
        c["ko"] = ko
    c.setdefault("verification_note", "")
    c["verification_note"] = "운영자 수정 대사 — 사실 대조 재검증 필요(대본 재검증 규칙)"
    _save(_script_path(pid), sc)
    _sync_script_artifacts(st, sc)
    _note(st, "script", "edit_line", f"{cut}번 컷 대사 수정 — 아직 영상에 반영 안 됨(「수정한 대사 영상에 반영」을 눌러야 반영)")
    _save(status_path(pid), st)
    return crosscheck(pid)                                  # 고친 대사도 곧바로 교차 검사


def edit_hook(pid: str, data: dict) -> dict:
    """후킹 질문·정답·발췌 컷/시작 초 수정 — script.json 만 고친다(영상은 「완성본 다시 조립」을 눌러야 바뀜 · 무료)."""
    st = load_status(pid)
    sc = _load(_script_path(pid))
    if not sc or not sc.get("hook"):
        raise SystemExit("후킹 정보가 없는 대본입니다")
    hk = dict(sc["hook"])
    cuts = [c for c in sc["cuts"] if "tts" in c]
    line = hk.get("type") == "line"                          # 2026-10-09 개편 뒤의 편(믿기 힘든 사실 한 줄 · 후보 3개)
    if line and data.get("pick") not in (None, ""):          # 후보 중 하나로 바꾸기(대본 승인 전에 운영자가 고름)
        i = int(data["pick"])
        if not 0 <= i < len(hk.get("candidates") or []):
            raise SystemExit(f"후보 {i + 1}번이 없습니다")
        hk = hook_from_candidate(hk, i)
    for k in ("question_jp", "question_ko", "answer_jp", "answer_ko") + (("key_jp", "voice_jp") if line else ()):
        if k in data and str(data[k]).strip():
            hk[k] = str(data[k]).strip()
    if data.get("cut"):
        hk["cut"] = int(data["cut"])
    # ★발췌 시작 초(운영자 선택 2026-10-09): 기본은 조립 때 「가장 많이 움직이는 2초」 자동 선택.
    #   운영자가 값을 **바꿨을 때만** 그 값으로 고정(at_by=operator) · 칸을 비우면 다시 자동 · 컷만 바꾸면 그 컷에서 자동.
    cut_changed = int(hk["cut"]) != int(sc["hook"].get("cut") or 0)
    raw_at = str(data.get("at") if data.get("at") is not None else "").strip()
    if "at" in data and not raw_at:
        hk.pop("at_by", None)                                # 칸을 비우면 자동 선택으로
    elif raw_at:
        new_at = round(float(raw_at), 2)
        if hk.get("at") is None or abs(new_at - float(hk["at"])) > 0.005:
            hk["at"], hk["at_by"] = new_at, "operator"       # 바꿨을 때만 고정
        elif cut_changed:
            hk.pop("at_by", None)                            # 컷만 바꾸면 새 컷에서 자동
    elif cut_changed:
        hk.pop("at_by", None)
    jp_name = (sc.get("subject") or {}).get("jp_name", "")
    if line:
        probs = validate_hook_line({"text_jp": hk.get("question_jp"), "key_jp": hk.get("key_jp"), "voice_jp": hk.get("voice_jp"),
                                    "pattern": hk.get("pattern")}, sc.get("facts", []), name_stems(hk.get("answer_jp", ""), jp_name))
        if not 1 <= int(hk["cut"]) <= len(cuts):
            probs.append(f"{hk['cut']}번 컷이 없습니다")
    else:
        probs = validate_hook(hk, cuts, sc.get("facts", []), name=jp_name)
    if probs:
        raise SystemExit("후킹 검사 불통과: " + " / ".join(probs))
    if not line:
        hk["type"] = hook_type(hk.get("question_jp", ""))
    if hk.get("voice_for") != hk.get("voice_jp"):            # 목소리 문장이 바뀌면 다음 조립 때 다시 읽힌다(약 $0.001)
        hk.pop("voice_file", None)
    sec = float(cuts[int(hk["cut"]) - 1].get("sec") or 0)
    hk["at"] = round(max(0.0, min(float(hk.get("at") or 0.0), max(0.0, sec - HOOK_S))), 2)
    if cut_changed or hk.get("at_by") != sc["hook"].get("at_by") or hk["at"] != sc["hook"].get("at"):
        hk.pop("motion", None)                               # 움직임 값은 다음 조립 때 다시 잰다
    sc.setdefault("hook_history", []).append({"at": _now(), "hook": sc["hook"]})
    sc["hook"] = hk
    _save(_script_path(pid), sc)
    _sync_script_artifacts(st, sc)
    if (st["artifacts"].get("video") or {}).get("final"):
        st["artifacts"]["script"]["hook_pending"] = True         # 영상엔 아직 미반영 — 재조립 필요
        _note(st, "video", "hook", "후킹·정답 문구 수정됨 — 「완성본 다시 조립」을 누르면 반영(무료)")
    where = {"operator": f"{hk['at']}초부터(운영자 지정)", "trial": f"{hk['at']}초부터(시험 릴스 구간)"}.get(
        hk.get("at_by"), "가장 많이 움직이는 2초(조립 때 자동 선택)")
    tail = f" · 목소리 「{hk.get('voice_jp', '')}」 · 끝 카드 {hk['answer_jp']}" if line else f" → 正解 {hk['answer_jp']}"
    _note(st, "script", "hook", f"후킹 수정: {hk['cut']}번 컷 {where} 「{hk['question_jp']}」{tail}")
    _save(status_path(pid), st)
    return st


def plan_timing(sc: dict, tps: list[dict], lead: float = 0.15) -> tuple[list[dict], list[str]]:
    """새 나레이션 조각 시각(tps)으로 컷별 구간을 다시 계산한다. 컷 길이(sec)는 **그대로**(영상은 안 바꾼다).
    반환: (새 timing, 안 들어가는 컷 설명 목록)."""
    old = {t["cut"]: t for t in sc["timing_v5"]}
    cuts = [c for c in sc["cuts"] if "tts" in c]
    timing, problems, i = [], [], 0
    for k, c in enumerate(cuts):
        n = len(_chunks(c["jp"]))
        seg = tps[i:i + n]
        nxt = tps[i + n]["start"] if i + n < len(tps) else seg[-1]["end"]
        a0, a1 = seg[0]["start"], nxt
        sec = float(old[c["cut"]]["sec"])
        ld = float(old[c["cut"]].get("lead", lead))
        speech = round(a1 - a0, 3)
        timing.append({"cut": c["cut"], "sec": old[c["cut"]]["sec"], "audio_from": a0, "audio_to": a1,
                       "speech_s": round(speech, 2), "lead": ld,
                       "local_tps": [{"jp_seg": None, "start": round(t["start"] - a0 + ld, 3),
                                      "end": round((t["end"] or a1) - a0 + ld, 3)} for t in seg]})
        # 고친 컷은 규칙대로 여유 0.6초, 안 고친 컷(이미 승인된 영상)은 말이 잘리지만 않으면 된다
        margin = MARGIN_S if c.get("pending_edit") else 0.0
        if ld + speech + margin > sec + 1e-6:
            need = ld + speech + MARGIN_S
            up = next((x for x in (4, 6, 8, 10) if x >= need), None)
            problems.append(f"{c['cut']}번 컷: 새 나레이션 {speech:.1f}초 — 지금 영상 {sec:g}초에 안 들어갑니다"
                            + (f"(필요 {up}초 · 이 컷만 다시 만들기 약 ${up * OMNI_USD_PER_SEC:.2f}) 또는 대사를 줄이세요"
                               if up else " — 대사를 줄이세요"))
        i += n
    return timing, problems


def apply_lines(pid: str) -> dict:
    """수정한 대사를 영상에 반영: 나레이션 전체 다시 읽기(TTS · 약 $0.01) → 컷별 구간 재계산 → 재조립 + 자동 검사.
    영상 컷은 다시 만들지 않는다. 새 대사가 컷 길이에 안 들어가면 아무것도 바꾸지 않고 멈춘다."""
    st = load_status(pid)
    pilot = PILOTS / pid
    sc = _load(_script_path(pid))
    cuts = [c for c in sc["cuts"] if "tts" in c]
    if not any(c.get("pending_edit") for c in cuts):
        raise SystemExit("반영할 대사 수정이 없습니다")
    rid = f"r{time.strftime('%m%d%H%M', time.gmtime())}_tts"
    req = {"id": rid, "kind": "gen_tts", "purpose": "관리자 페이지 대사 수정 반영 — 대본 전체를 한 번에 다시 읽기(억양·음량 일관)",
           "cut_map": [{"cut": c["cut"], "n": len(_chunks(c["jp"]))} for c in cuts],
           "items": [{"name": "body", "jp": "".join(c["jp"] for c in cuts),
                      "segments": [s for c in cuts for s in _chunks(c["tts"])]}]}
    rp = pilot / "requests" / f"{rid}.json"
    _save(rp, req)
    r = subprocess.run([sys.executable, str(V2 / "tools" / "run_request.py"), str(rp)], cwd=str(ROOT))
    tpf = pilot / "out" / rid / "body_timepoints.json"
    if r.returncode != 0 or not tpf.exists():
        _note(st, "video", "error", f"대사 반영 실패 — 나레이션 합성 오류(요청 {rid})")
        _save(status_path(pid), st)
        raise SystemExit("나레이션 합성 실패")
    timing, problems = plan_timing(sc, _load(tpf))
    if problems:                                            # ★영상은 건드리지 않고 멈춘다
        _note(st, "video", "blocked", "대사 반영 보류 — " + " / ".join(problems))
        st["artifacts"]["script"]["apply_blocked"] = problems
        _save(status_path(pid), st)
        return st
    sc.setdefault("superseded_timing", []).append({"at": _now(), "timing": sc["timing_v5"]})
    sc["timing_v5"] = timing
    for c in cuts:
        c.pop("pending_edit", None)
    _save(_script_path(pid), sc)
    st["artifacts"]["script"]["audio"] = f"out/{rid}/body.wav"
    st["artifacts"]["script"].pop("apply_blocked", None)
    st["artifacts"]["video"]["assemble"]["tts_id"] = rid
    _sync_script_artifacts(st, sc)
    st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": "대사 반영 나레이션 다시 읽기", "usd": 0.01})
    _note(st, "video", "apply_lines", "수정한 대사 반영 — 나레이션 다시 읽기 + 재조립(영상 컷은 그대로)")
    _save(status_path(pid), st)
    return assemble(pid)


# ── 컷 수정 방향 → 콘티 → 승인 → 영상(운영자 확정 2026-09-28) ──────────────────────
# 운영자가 관리자 페이지에 "이 컷을 이렇게 바꿔 달라"(예: 뱃속이 텅 빈 묘사 + 사인 불명 물음표, 화면 전환 2회 이상)를 적으면
#   ① AI가 규칙(미니어처 화풍·생물 카드 형태 고정·글자 금지·빨강 강조색·초 단위 타임라인)에 맞춰 **샷 계획**을 세우고
#   ② 2×2 **콘티 이미지 한 장**을 만든다(이미지 먼저 검토 규칙 · 약 $0.13)  → 운영자 승인 전에는 영상을 만들지 않는다
#   ③ 승인하면 샷별로 영상(움직이는 샷=Omni, 멈춘 샷=무료 천천히 확대)을 만들어 한 컷으로 이어 붙이고 재조립한다.
# 물음표 같은 기호는 AI 그림이 아니라 **편집에서 빨간 기호로** 얹는다(글자·기호를 AI가 그리면 뭉개짐 · 강조색 규칙).
IMG_USD = 0.134
_RECUT_PROMPT = """You plan a replacement for ONE cut of a Japanese science YouTube Short made in a handcrafted
MINIATURE DIORAMA style (tilt-shift, warm practical light, rough hand-made props; the ONLY precise object is the
giant isopod Bathynomus giganteus, whose anatomy is fixed by reference images). Follow these HARD RULES:
- Split the cut ({sec} s) into shots that exactly cover 0..{sec}s. At least {min_tr} scene transitions
  (= at least {min_shots} shots). Put transitions at narration boundaries when possible: {bounds}.
- Each shot uses one of 4 storyboard panels (1..4). motion "omni" = AI video of that panel (the creature or light moves);
  motion "still" = the panel with a slow push-in (use for diagrams / symbolic frames). Prefer at most 2 "omni" shots.
- NEVER draw text, letters, numbers or symbols in the images or videos. If a symbol such as a question mark is needed,
  set that shot's overlay to "question_mark" — it is added later in editing as a red mark.
- Never show real human hands or people, never change the creature's size or anatomy, no gore; an "empty stomach" must be
  shown respectfully and schematically (e.g. a cut-away/X-ray-like model view of the body showing an empty gut cavity).
- Stay faithful to the narration and facts below; do not invent facts.
- {ending_rule}
Return JSON only:
{{"summary_ko":"계획을 운영자가 이해하기 쉽게 한국어 2문장",
 "shots":[{{"t0":0,"t1":2,"panel":1,"motion":"omni","overlay":"none","desc_ko":"한국어 한 줄"}}],
 "panels":{{"1":"English description of storyboard panel 1","2":"...","3":"...","4":"..."}},
 "omni_prompts":{{"1":"English per-second TIMELINE video prompt for a shot that starts from panel 1 (only for panels used by omni shots)"}}}}

# Narration of this cut (Japanese / Korean)
{jp}
{ko}
# Facts (with ids)
{facts}
# Operator's revision direction (Korean)
{direction}
# Current version of this cut (for style reference)
{old_prompt}
"""
_GRID_HEAD = ("Create ONE image that is a clean 2x2 grid of FOUR separate, equal-sized vertical 9:16 photographs separated "
              "by thin plain white gutters. Shared look: handcrafted miniature / scale-model photography, strong tilt-shift "
              "shallow depth of field, warm soft practical lighting, muted grey-green and brown palette; everything except "
              "the giant isopod is a deliberately rough hand-made model. The giant isopod must match the attached replica and "
              "real reference images exactly: pale lavender-lilac glossy segmented armour, FLAT dark triangular compound eyes "
              "at the front corners of the head, seven pairs of thin legs, spiny fan-shaped tail plate. "
              "NEVER draw text, letters, numbers, question marks, labels or logos. No human hands or people.\n")
_OMNI_HEAD = ("Vertical 9:16 video, exactly {dur} seconds, one continuous shot, no cuts. Handcrafted tabletop miniature diorama "
              "photography, tilt-shift shallow depth of field, warm soft practical light. The attached image is the FIRST FRAME: "
              "keep every object's shape, size, colour and position consistent with it. The main creature (whenever visible) "
              "keeps its exact anatomy and size.\n")
_OMNI_TAIL = ("\nSOUND: none needed (it will be replaced). No music. No dialogue.\nNEVER SHOW: text, letters, numbers, symbols, "
              "labels, logos, watermarks; real human hands, fingers or people; extra or different creatures; the main creature growing, "
              "shrinking or changing shape; morphing or melting objects; cuts, jump cuts or flicker.")


def _even_up(x: float, lo: int = 4) -> int:
    return next(v for v in (4, 6, 8, 10) if v >= max(lo, x - 1e-6))


def _recut_state(st: dict, cut: int) -> dict:
    return st.setdefault("artifacts", {}).setdefault("recut", {}).setdefault(str(int(cut)), {})


def _validate_plan(plan: dict, sec: float, min_tr: int) -> list[dict]:
    shots = sorted(plan.get("shots") or [], key=lambda x: float(x["t0"]))
    if len(shots) < min_tr + 1:
        raise ValueError(f"화면 전환이 {len(shots) - 1}회뿐입니다(최소 {min_tr}회)")
    t = 0.0
    for sh in shots:
        sh["t0"], sh["t1"] = round(float(sh["t0"]), 2), round(float(sh["t1"]), 2)
        sh["panel"] = int(sh["panel"])
        if abs(sh["t0"] - t) > 0.05 or sh["t1"] <= sh["t0"] or not 1 <= sh["panel"] <= 4:
            raise ValueError(f"샷 구간이 이어지지 않습니다: {sh}")
        if sh.get("motion") not in ("omni", "still"):
            sh["motion"] = "still"
        if sh.get("overlay") not in ("none", "question_mark"):
            sh["overlay"] = "none"
        if sh["motion"] == "omni" and not (plan.get("omni_prompts") or {}).get(str(sh["panel"])):
            raise ValueError(f"{sh['panel']}번 칸 영상 지시문이 없습니다")
        t = sh["t1"]
    if abs(t - sec) > 0.05:
        raise ValueError(f"샷 합계 {t}초 ≠ 컷 길이 {sec}초")
    return shots


def recut_estimate(shots: list[dict]) -> float:
    omni = sum(_even_up(sh["t1"] - sh["t0"]) for sh in shots if sh["motion"] == "omni")
    return round(IMG_USD + omni * OMNI_USD_PER_SEC, 2)


def recut_plan(pid: str, cut: int, direction: str, min_tr: int = 0, ask=None, run_images: bool = True) -> dict:
    """수정 방향 → 샷 계획 + 2×2 콘티 이미지(승인 대기). 영상은 만들지 않는다."""
    direction = (direction or "").strip()
    if not direction:
        raise SystemExit("수정 방향을 적어 주세요")
    st = load_status(pid)
    if st["stages"]["video"]["state"] == "locked":
        raise SystemExit("영상 단계가 잠겨 있습니다")
    pilot = PILOTS / pid
    sc = _load(_script_path(pid))
    c = next(x for x in sc["cuts"] if x.get("cut") == int(cut) and "tts" in x)
    tm = next(x for x in sc["timing_v5"] if x["cut"] == int(cut))
    sec = float(tm["sec"])
    bounds = ", ".join(f"{x['start']:.1f}s" for x in tm.get("local_tps", [])[1:]) or "none"
    art = st["artifacts"]["video"]
    old = next((i["prompt"] for i in (_load(pilot / "requests" / f"{art['clips_request']}.json") or {}).get("items", [])
                if i["name"] == f"c{int(cut):02d}"), "")
    last = int(cut) == max(x["cut"] for x in sc["cuts"] if "tts" in x)
    ending_rule = ("This is the LAST cut: the final shot must end with the light dimming to complete black "
                   "(it connects to the shared ending)." if last or c.get("transition_out") else "No special ending rule.")
    prompt = _RECUT_PROMPT.format(sec=f"{sec:g}", min_tr=int(min_tr), min_shots=int(min_tr) + 1, bounds=bounds,
                                  ending_rule=ending_rule, jp=c["jp"], ko=c.get("ko", ""),
                                  facts="\n".join(f"{f['id']}: {f['fact']}" for f in facts_for(sc, c.get("fact", ""))),
                                  direction=direction, old_prompt=old[:1500])
    rc = _recut_state(st, cut)
    rc.update(direction=direction, min_transitions=int(min_tr), at=_now(), state="planning")
    rc.pop("error", None)
    try:
        plan = json.loads(re.search(r"\{.*\}", (ask or _recut_ask)(prompt), re.S).group(0))
        shots = _validate_plan(plan, sec, int(min_tr))
    except Exception as e:                                   # noqa: BLE001
        rc.update(state="error", error=f"계획 실패: {str(e)[:200]}")
        _note(st, "video", "error", f"{cut}번 컷 수정 계획 실패 — {str(e)[:120]}")
        _save(status_path(pid), st)
        raise SystemExit(rc["error"])
    rc["model"] = _TEXT_MODEL or "test"
    rc.update(plan={"summary_ko": plan.get("summary_ko", ""), "shots": shots, "panels": plan.get("panels", {}),
                    "omni_prompts": plan.get("omni_prompts", {})},
              estimate_usd=recut_estimate(shots))
    refs = [r["file"] for r in (_load(pilot / "creature_card.json") or {}).get("use_as_reference", [])][:3]
    if c.get("keyframe"):
        refs.append(c["keyframe"])
    pn = plan.get("panels", {})
    grid = _GRID_HEAD + "\n".join(f"Panel {k} ({pos}): {pn.get(str(k), '')}" for k, pos in
                                  zip((1, 2, 3, 4), ("top-left", "top-right", "bottom-left", "bottom-right")))
    rid = f"r{time.strftime('%m%d%H%M', time.gmtime())}_c{int(cut):02d}_conti"
    req = {"id": rid, "kind": "gen_images", "purpose": f"{cut}번 컷 수정 콘티 — {direction[:80]}",
           "model_preference": ["gemini-3-pro-image-preview"],
           "items": [{"name": "conti", "aspect": "9:16", "size": "2K", "refs": refs, "prompt": grid,
                      "split": {"rows": 2, "cols": 2, "names": ["p1", "p2", "p3", "p4"]}}]}
    rp = pilot / "requests" / f"{rid}.json"
    _save(rp, req)
    rc["conti"] = {"request": rid}
    _save(status_path(pid), st)
    if run_images:
        r = subprocess.run([sys.executable, str(V2 / "tools" / "run_request.py"), str(rp)], cwd=str(ROOT))
        res = _load(pilot / "out" / rid / "result.json") or {}
        it = (res.get("items") or [{}])[0]
        st = load_status(pid)
        rc = _recut_state(st, cut)
        if r.returncode != 0 or not it.get("panels"):
            rc.update(state="error", error="콘티 이미지 생성 실패")
            _note(st, "video", "error", f"{cut}번 컷 콘티 이미지 생성 실패(요청 {rid})")
            _save(status_path(pid), st)
            raise SystemExit("콘티 이미지 생성 실패")
        rc["conti"].update(sheet=f"out/{rid}/{it['file']}", panels=[f"out/{rid}/{x}" for x in it["panels"]])
        st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": f"{cut}번 컷 콘티", "usd": IMG_USD})
    rc["state"] = "conti_review"
    _note(st, "video", "recut_plan", f"{cut}번 컷 수정 콘티 준비 — 승인하면 영상 생성(약 ${rc['estimate_usd']})")
    _save(status_path(pid), st)
    return st


def _recut_ask(prompt: str) -> str:
    return _gemini_text(prompt)


def _qmark_png(path: Path) -> Path:
    """빨간 물음표(강조색 규칙) — AI가 아니라 편집에서 얹는다."""
    from PIL import Image, ImageDraw, ImageFont
    import assemble as A
    im = Image.new("RGBA", (720, 1280), (0, 0, 0, 0))
    f = ImageFont.truetype(str(A.FONT_BOLD), 360)
    f.set_variation_by_name("Bold")
    d = ImageDraw.Draw(im)
    w = d.textlength("?", font=f)
    d.text(((720 - w) / 2, 330), "?", font=f, fill=(220, 38, 38, 245), stroke_width=10, stroke_fill=(20, 10, 10, 200))
    im.save(path)
    return path


def compose_shots(pilot: Path, shots: list[dict], panels: list[str], omni: dict, dst: Path, fade_out: bool) -> Path:
    """샷들을 한 컷(720×1280·24fps)으로 잇는다: omni=그 영상 앞부분, still=칸 이미지 천천히 확대, 물음표는 빨간 기호."""
    import tempfile
    W, H, FPS = 720, 1280, 24
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        parts = []
        for i, sh in enumerate(shots):
            dur = sh["t1"] - sh["t0"]
            out = t / f"s{i}.mp4"
            if sh["motion"] == "omni":
                src = ["-i", str(pilot / omni[i])]
                vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},tpad=stop_mode=clone:stop_duration={dur}"
            else:
                n = int(round(dur * FPS))
                src = ["-loop", "1", "-i", str(pilot / panels[sh["panel"] - 1])]
                vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                      f"zoompan=z='min(zoom+0.0010,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},setsar=1")
            if sh.get("overlay") == "question_mark":
                q = _qmark_png(t / f"q{i}.png")
                cmd = [*src, "-loop", "1", "-i", str(q), "-filter_complex",
                       f"[0:v]{vf}[b];[1:v]format=rgba,fade=t=in:st=0.3:d=0.4:alpha=1[q];[b][q]overlay=0:0:shortest=1[v]",
                       "-map", "[v]"]
            else:
                cmd = [*src, "-vf", vf]
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cmd, "-t", f"{dur}", "-an", "-c:v", "libx264",
                            "-crf", "16", "-pix_fmt", "yuv420p", str(out)], check=True)
            parts.append(out)
        (t / "l.txt").write_text("".join(f"file '{x}'\n" for x in parts))
        tot = sum(sh["t1"] - sh["t0"] for sh in shots)
        vf = f",fade=t=out:st={tot - 1.0}:d=1.0" if fade_out else ""
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(t / "l.txt"),
                        "-vf", f"setsar=1{vf}", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(dst)],
                       check=True)
    return dst


def recut_approve(pid: str, cut: int) -> dict:
    """콘티 승인 → 샷별 영상 생성 → 한 컷으로 합성 → 재조립 + 자동 검사."""
    st = load_status(pid)
    rc = _recut_state(st, cut)
    if rc.get("state") != "conti_review":
        raise SystemExit("승인할 콘티가 없습니다(콘티가 나온 뒤 승인)")
    pilot = PILOTS / pid
    plan, panels = rc["plan"], rc["conti"]["panels"]
    shots = plan["shots"]
    rid = f"r{time.strftime('%m%d%H%M', time.gmtime())}_c{int(cut):02d}_recut"
    items, omni = [], {}
    for i, sh in enumerate(shots):
        if sh["motion"] != "omni":
            continue
        dur = _even_up(sh["t1"] - sh["t0"])
        name = f"s{i}"
        items.append({"name": name, "start": panels[sh["panel"] - 1],
                      "prompt": _OMNI_HEAD.format(dur=dur) + "\nTIMELINE\n" + plan["omni_prompts"][str(sh["panel"])] + _OMNI_TAIL})
        omni[i] = f"out/{rid}/{name}.mp4"
    if items:
        src = _load(pilot / "requests" / f"{st['artifacts']['video']['clips_request']}.json") or {}
        req = {"id": rid, "kind": "gen_omni", "model": src.get("model", "gemini-omni-1.1-flash"), "resolution": "720p",
               "purpose": f"{cut}번 컷 수정 — {rc['direction'][:80]}", "items": items}
        rp = pilot / "requests" / f"{rid}.json"
        _save(rp, req)
        subprocess.run([sys.executable, str(V2 / "tools" / "run_request.py"), str(rp)], cwd=str(ROOT))
        missing = [v for v in omni.values() if not (pilot / v).exists()]
        if missing:
            st = load_status(pid)
            _recut_state(st, cut).update(state="error", error="영상 생성 실패: " + ", ".join(missing))
            _note(st, "video", "error", f"{cut}번 컷 수정 영상 생성 실패(요청 {rid}) — 콘티는 그대로 남아 있습니다")
            _save(status_path(pid), st)
            raise SystemExit("영상 생성 실패")
    sc = _load(_script_path(pid))
    c = next(x for x in sc["cuts"] if x.get("cut") == int(cut))
    last = int(cut) == max(x["cut"] for x in sc["cuts"] if "tts" in x)
    newf = compose_shots(pilot, shots, panels, omni, pilot / "out" / rid / f"c{int(cut):02d}.mp4",
                         fade_out=bool(last or c.get("transition_out")))
    st = load_status(pid)
    rc = _recut_state(st, cut)
    clip = next(x for x in st["artifacts"]["video"]["clips"] if int(x["cut"]) == int(cut))
    clip.setdefault("history", []).append(clip["file"])
    clip["file"] = str(newf.relative_to(pilot))
    clip["review"] = "수정 반영: " + rc["direction"][:60]
    spent = round(sum(_even_up(sh["t1"] - sh["t0"]) for sh in shots if sh["motion"] == "omni") * OMNI_USD_PER_SEC, 2)
    st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": f"{cut}번 컷 수정 영상", "usd": spent})
    rc.update(state="done", done_at=_now(), result=clip["file"])
    _note(st, "video", "recut_done", f"{cut}번 컷을 수정 방향대로 다시 만들었습니다(샷 {len(shots)}개 · 전환 {len(shots) - 1}회)")
    _save(status_path(pid), st)
    return assemble(pid)


# ── 업로드(운영자 확정 2026-09-28) ─────────────────────────────────────────
# 완성본을 승인하면 유튜브 제목·설명·해시태그를 일본어/한국어로 자동 작성해 업로드 카드에 보여 주고(운영자가 고칠 수 있음),
# 업로드 단계 「승인 → 유튜브 업로드」를 눌러야만 올라간다. 같은 편은 두 번 올리지 않는다(중복 업로드 방지).
# 채널 규칙: 제목 끝 해시태그 정확히 2개(내용 1 + 고정 #深海) · #Shorts 금지 · 설명에 구독+댓글 유도(다음 편 소재 요청형) ·
#            AI 재현 영상임을 밝힘 · 출처 · 회차 번호 비노출 · 회사원 소재 금지 · 사실 왜곡 금지.
_CTA_JP = "チャンネル登録で、次の深海もいっしょに。\n次はどの生き物が気になりますか。コメントで教えてください。"
_CTA_KO = "다음 심해도 함께 보고 싶다면 구독해 주세요.\n다음엔 어떤 생물이 궁금하신가요? 댓글로 알려주세요."
_REPRO_JP = "※映像はAIによる再現映像です（生き物の形は実際の写真を参考にしています）。"
_REPRO_KO = "※ 영상은 AI 재현 영상입니다(생물의 형태는 실제 사진을 참고했습니다)."
PINNED_COMMENT = "次に見たい深海の生き物は？"
_META_PROMPT = """You write YouTube Shorts metadata for a Japanese deep-sea science channel. Use ONLY the facts and narration below.
Rules: title_jp = hook-style Japanese title, max 32 characters, mystery/awe tone, no honorific needed, no hashtags.
ONE CORE FACT: the title is about the episode's CORE FACT below — the same fact the opening question asks about and the ending
pays off. Put its most surprising concrete detail (a number, a missing body part, a strange behaviour) at the very start and end
with 深海の謎 or a question, e.g. 「5年以上も絶食する、深海の巨大生物の謎」「頭も骨もない、深海の謎」.
{name_rule}
no "#Shorts", no episode numbers, NO office-worker jokes (有給/残業/上司 etc.), never exaggerate beyond the facts.
desc_jp = 3-4 short sentences in polite Japanese (です・ます), summarising the story with the concrete facts.
title_ko / desc_ko = natural Korean versions (존댓말 for desc).
tags_jp / tags_ko = 8-12 SEO hashtags each, analysed from THIS story: the animal's group (e.g. #ナマコ), its notable behaviours
and traits actually in the narration (e.g. #発光 #脱皮), habitat words (#深海生物 #海の生き物), genre words (#雑学 #生き物 #自然
#ドキュメンタリー), curiosity words (#深海の謎). Korean list = same idea in Korean (#해삼 #발광 #심해생물 #잡학 ...).
Each tag starts with #, no spaces inside, no #Shorts, no episode numbers, nothing the facts do not support.
Return JSON only:
{{"title_jp":"...","title_ko":"...","desc_jp":"...","desc_ko":"...","tags_jp":["#..."],"tags_ko":["#..."]}}
# Species
{name_jp} / {name_ko} / {sci}
# CORE FACT (the one fact this episode is about)
{core}
# Opening question (first 2 seconds) → its answer (revealed only at the end)
{question} → {answer}
# Narration (by cut)
{cuts}
# Facts
{facts}
"""


CORE_TAGS_JP = ["#深海", "#海洋生物", "#深海生物"]        # 채널 공통 태그(하드룰: #深海·#海洋生物 항상)
CORE_TAGS_KO = ["#심해", "#해양생물", "#심해생물"]
MAX_TAGS = 15


def _tag_ok(t: str) -> bool:
    t = t.strip()
    return t.startswith("#") and 2 <= len(t) <= 24 and " " not in t and "shorts" not in t.lower() and not re.search(r"#\d+$", t)


def _merge_tags(head: list[str], core: list[str], ai: list) -> list[str]:
    out = []
    for t in list(head) + list(core) + [str(x) for x in (ai or [])]:
        t = t.strip()
        if _tag_ok(t) and t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out[:MAX_TAGS]


def species_tags(sc: dict) -> tuple[str, str]:
    """종명 태그(일본어·한국어). 실사고 2026-09-30: 和名이 없는 종은 '#'만 붙어 제목이 「… # #深海」가 됐다
    → 和名 → 후킹 정답 이름 → 학명 순으로 반드시 채운다."""
    sub = sc.get("subject", {})
    hk = sc.get("hook") or {}
    if hk.get("type") == "fact":                             # 사실 질문 편의 정답은 이름이 아니다(D) — 종명 태그로 쓰지 않음
        hk = {}
    jp = (sub.get("jp_name") or hk.get("answer_jp") or sub.get("scientific_name") or "").replace(" ", "")
    ko = (sub.get("ko_name") or hk.get("answer_ko") or sub.get("scientific_name") or "").replace(" ", "")
    return "#" + jp, "#" + ko


def _compose_meta(sc: dict, gen: dict) -> dict:
    tj, tk = species_tags(sc)
    title_jp_tags, title_ko_tags = [tj, "#深海"], [tk, "#심해"]                       # 제목 끝 2개(채널 규칙)
    tags_jp = _merge_tags([tj], CORE_TAGS_JP, gen.get("tags_jp"))                   # 설명·유튜브 키워드용 8~15개
    tags_ko = _merge_tags([tk], CORE_TAGS_KO, gen.get("tags_ko"))
    srcs = sorted({u for f in sc.get("facts", []) for u in f.get("sources", [])})
    def desc(body, cta, repro, tags, head):
        return (body.strip() + "\n\n" + cta + "\n\n" + repro + "\n" + head + "\n" + "\n".join(srcs)
                + "\n\n" + " ".join(tags)).strip()
    return {
        "title_jp": (gen["title_jp"].strip() + " " + " ".join(title_jp_tags))[:100],
        "title_ko": (gen["title_ko"].strip() + " " + " ".join(title_ko_tags))[:100],
        "desc_jp": desc(gen["desc_jp"], _CTA_JP, _REPRO_JP, tags_jp, "出典:"),
        "desc_ko": desc(gen["desc_ko"], _CTA_KO, _REPRO_KO, tags_ko, "출처:"),
        "tags_jp": tags_jp, "tags_ko": tags_ko, "pinned_comment": PINNED_COMMENT, "privacy": "private", "category": "15",
    }


YT_CATEGORIES = {"15": "반려동물/동물", "28": "과학기술", "27": "교육"}   # 유튜브 카테고리 번호(명시해서 보낸다)
_STALE = re.compile(r"有給|残業|定時|上司|出社|유급|야근|상사|출근|퇴근|직장인")


def title_spoilers(sc: dict) -> tuple[list[str], list[str]]:
    """제목 본문에 넣으면 안 되는 말(운영자 선택 2026-10-09 D: 제목에 정답 이름을 넣지 않는다) — (일본어, 한국어).
    후킹 정답은 늘 금지 · 정체 맞히기(identity) 편은 和名도 금지(종명은 제목 끝 해시태그로만 — 채널 규칙 그대로)."""
    hk, sub = sc.get("hook") or {}, sc.get("subject") or {}
    ident = (hk.get("type") or hook_type(hk.get("question_jp", ""))) in ("identity", "line")   # line = 끝 카드가 이름 공개
    jp = [hk.get("answer_jp", "")] + ([sub.get("jp_name", "")] if ident else [])
    ko = [hk.get("answer_ko", "")] + ([sub.get("ko_name", "")] if ident else [])
    return sorted(set(name_stems(*jp))), sorted(set(name_stems(*ko)))


def _title_key(s: str) -> str:
    return re.sub(r"[、。，,．.！!？?\s「」『』]", "", str(s or ""))


def upload_meta(pid: str, ask=None) -> dict:
    st = load_status(pid)
    sc = _load(_script_path(pid))
    sub = sc.get("subject", {})
    hk = sc.get("hook") or {}
    by = {f["id"]: f for f in sc.get("facts", [])}
    core = by.get(str(sc.get("core") or ""))
    ban_jp, ban_ko = title_spoilers(sc)
    name_rule = ("NEVER put these words in title_jp / title_ko (they give away the answer, which the video reveals only at the end; "
                 "the species name is added automatically as a hashtag): " + ", ".join(ban_jp + ban_ko) + ".") if ban_jp + ban_ko else ""
    if hk.get("type") == "line":                             # ★제목도 후킹과 같은 문장으로 시작(운영자 선택 2026-10-09)
        name_rule += (f"\nSAME LINE: title_jp must START with the opening line 「{hk.get('question_jp', '')}」 exactly as written "
                      "(you may drop the 「、」), then add a short continuation such as 深海の謎 (max 32 characters in total). "
                      "title_ko starts with its Korean meaning.")
    prompt = _META_PROMPT.format(
        name_jp=sub.get("jp_name", ""), name_ko=sub.get("ko_name", ""), sci=sub.get("scientific_name", ""),
        core=(f"{core['id']}: {core.get('fact_jp') or core['fact']} / {core['fact']}" if core else "(not set — use the most surprising fact)"),
        question=hk.get("question_jp", ""), answer=hk.get("answer_jp", ""), name_rule=name_rule,
        cuts="\n".join(f"{c['cut']}: {c['jp']}" for c in sc["cuts"] if "tts" in c),
        facts="\n".join(f"{f['id']}: {f['fact']}" for f in sc.get("facts", [])))
    probs: list[str] = []
    for _ in range(3):
        gen = json.loads(re.search(r"\{.*\}", (ask or _gemini_text)(prompt + (
            "\n# Problems in your previous answer (fix all)\n" + "\n".join("- " + x for x in probs) if probs else "")), re.S).group(0))
        for k in ("title_jp", "title_ko", "desc_jp", "desc_ko"):
            if not str(gen.get(k, "")).strip():
                raise ValueError(f"{k} 비어 있음")
        if _STALE.search(gen["title_jp"] + gen["title_ko"]):
            raise ValueError("제목에 금지된 회사원 소재가 들어갔습니다 — 다시 쓰기")
        probs = [f"title_jp contains 「{w}」 — remove it" for w in ban_jp if w in gen["title_jp"]] + \
                [f"title_ko contains 「{w}」 — remove it" for w in ban_ko if w in gen["title_ko"]]
        if hk.get("type") == "line" and not _title_key(gen["title_jp"]).startswith(_title_key(hk.get("question_jp", ""))):
            probs.append(f"title_jp must START with the opening line 「{hk.get('question_jp', '')}」 (same words) and then continue")
        if not probs:
            break
    if probs:
        raise ValueError("제목에 정답(이름)이 들어갔습니다 — 3번 다시 써도 빠지지 않음: " + " / ".join(probs[:2]))
    up = st.setdefault("artifacts", {}).setdefault("upload", {})
    old = up.get("meta") or {}
    up["meta"] = _compose_meta(sc, gen)
    up["meta"]["privacy"] = old.get("privacy", "private")
    up["meta"]["category"] = old.get("category", "15")
    up["meta_at"] = _now()
    if st["stages"]["upload"]["state"] in ("working", "revise"):
        st["stages"]["upload"]["state"] = "review"
    _note(st, "upload", "meta", "유튜브 제목·설명·해시태그 작성 — 확인 후 「승인 → 유튜브 업로드」")
    _save(status_path(pid), st)
    return st


# ── 예약 공개(운영자 요청 2026-10-06) ─────────────────────────────────────
# 화면에서 한국 시간(KST = 일본 시간과 같음)으로 고른 시각 → 유튜브 publishAt(UTC). 업로드는 바로 하고(비공개),
# 그 시각에 유튜브가 자동으로 공개한다(우리 서버가 그때 깨어 있을 필요 없음).
SCHEDULE_MIN_LEAD_S = 15 * 60                               # 너무 가까운 시각은 업로드가 끝나기 전에 지나 버린다
SCHEDULE_MAX_DAYS = 180


def parse_publish_at(text: str, now: float | None = None) -> str:
    """'2026-10-07T19:00'(KST) 또는 오프셋 있는 ISO → 'YYYY-MM-DDTHH:MM:00Z'(UTC). 지난 시각·너무 먼 시각은 거절."""
    import datetime as dt
    t = str(text or "").strip()
    if not t:
        raise SystemExit("예약 공개 시각이 비어 있습니다")
    try:
        d = dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(f"예약 공개 시각 형식이 이상합니다: {t}")
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone(dt.timedelta(hours=9)))   # 화면 입력 = 한국 시간
    u = d.astimezone(dt.timezone.utc).replace(second=0, microsecond=0)
    lead = u.timestamp() - (time.time() if now is None else now)
    if lead < SCHEDULE_MIN_LEAD_S:
        raise SystemExit("예약 공개 시각은 지금부터 15분 이후여야 합니다 — 시각을 다시 골라 주세요")
    if lead > SCHEDULE_MAX_DAYS * 86400:
        raise SystemExit(f"예약 공개는 {SCHEDULE_MAX_DAYS}일 안쪽으로만 잡을 수 있습니다")
    return u.strftime("%Y-%m-%dT%H:%M:00Z")


def save_upload_meta(pid: str, data: dict) -> dict:
    st = load_status(pid)
    up = st.setdefault("artifacts", {}).setdefault("upload", {})
    if (up.get("result") or {}).get("url"):
        raise SystemExit("이미 업로드했습니다 — 제목·설명은 유튜브 스튜디오에서 고쳐 주세요")
    m = up.setdefault("meta", {})
    for k in ("title_jp", "title_ko", "desc_jp", "desc_ko", "pinned_comment", "privacy", "category", "publish_at"):
        if k in data:
            m[k] = str(data[k]).strip()
    if m.get("privacy") not in ("private", "unlisted", "public", "scheduled"):
        m["privacy"] = "private"
    if m["privacy"] == "scheduled":
        m["publish_at"] = parse_publish_at(m.get("publish_at", ""))
    else:
        m.pop("publish_at", None)
    if m.get("category") not in YT_CATEGORIES:
        m["category"] = "15"
    if not m.get("title_jp") or len(m["title_jp"]) > 100:
        raise SystemExit("제목(일본어)은 1~100자여야 합니다")
    if "#shorts" in (m["title_jp"] + m.get("desc_jp", "")).lower():
        raise SystemExit("#Shorts는 넣지 않습니다(채널 규칙)")
    _note(st, "upload", "meta_edit", "운영자가 제목·설명 수정")
    if st["stages"]["upload"]["state"] in ("working", "revise"):
        st["stages"]["upload"]["state"] = "review"
    _save(status_path(pid), st)
    return st


PLAYLIST_TITLE = "深海の謎"                                     # 쇼츠를 모으는 재생목록(운영자 선택 2026-10-05)
PLAYLIST_DESC = "1話にひとつ、深海の生き物の謎を手作りのミニチュアで再現します。"


def youtube_upload(pid: str, uploader=None, playlister=None) -> dict:
    """완성본을 유튜브에 올린다(같은 편 두 번 금지). uploader: 테스트용 대체 함수."""
    st = load_status(pid)
    up = st.setdefault("artifacts", {}).setdefault("upload", {})
    if (up.get("result") or {}).get("url"):
        raise SystemExit(f"이미 업로드했습니다: {up['result']['url']}")
    m = up.get("meta") or {}
    if not m.get("title_jp"):
        raise SystemExit("제목·설명이 없습니다 — 먼저 작성하세요")
    video = PILOTS / pid / st["artifacts"]["video"]["final"]
    if uploader is None:
        sys.path.insert(0, str(ROOT))
        from src.core import youtube_upload as yt           # noqa: E402
        if not yt.has_credentials():
            raise SystemExit("유튜브 연결 키(YOUTUBE_*)가 없습니다")
        uploader = yt.upload
        playlister = playlister or yt.add_to_playlist
    tags = [t.lstrip("#") for t in m.get("tags_jp", [])]
    pub = parse_publish_at(m.get("publish_at", "")) if m.get("privacy") == "scheduled" else None   # 지났으면 여기서 멈춤
    try:
        r = uploader(str(video), m["title_jp"], m.get("desc_jp", ""), tags=tags,
                     privacy="private" if pub else m.get("privacy", "private"),
                     category_id=m.get("category") or "15", **({"publish_at": pub} if pub else {}))
    except Exception as e:                                   # noqa: BLE001
        _note(st, "upload", "error", f"유튜브 업로드 실패: {str(e)[:160]}")
        _save(status_path(pid), st)
        raise SystemExit(f"유튜브 업로드 실패: {e}")
    up["result"] = {"url": r["url"], "video_id": r.get("video_id", ""), "privacy": "scheduled" if pub else r.get("privacy", ""),
                    "category": m.get("category") or "15", "at": _now()}
    if pub:
        up["result"]["publish_at"] = pub
    _note(st, "upload", "uploaded", f"유튜브 업로드 완료({'예약 공개 ' + pub if pub else r.get('privacy', '')}): {r['url']}"
          " — 고정 댓글은 유튜브 앱에서 직접 달고 고정")
    if playlister and r.get("video_id"):                     # 재생목록 추가 — 실패해도 업로드는 성공으로 둔다
        try:
            pl = playlister(r["video_id"], PLAYLIST_TITLE, PLAYLIST_DESC)
            up["result"]["playlist"] = pl.get("playlist_id", "")
            _note(st, "upload", "playlist", f"재생목록 「{PLAYLIST_TITLE}」에 추가")
        except Exception as e:                               # noqa: BLE001
            up["result"]["playlist_error"] = str(e)[:160]
            _note(st, "upload", "error", f"재생목록 추가 실패(토큰 권한 부족이면 재발급 필요): {str(e)[:120]}")
    _save(status_path(pid), st)
    return st


def fetch_stats(pid: str | None = None, stats_fn=None) -> dict:
    """업로드한 편의 유튜브 실적을 가져와 status.artifacts.upload.stats 에 저장(운영자 선택 2026-10-05 · 실적 자동 수집).
    pid 가 없으면 업로드된 모든 편. 권한이 없으면 편마다 error 로 기록(재발급 안내)."""
    scopes = None
    if stats_fn is None:
        sys.path.insert(0, str(ROOT))
        from src.core import youtube_upload as yt           # noqa: E402
        stats_fn = yt.video_stats
        try:                                                 # 지금 토큰이 실제로 받은 권한(추측 대신 실측 기록)
            scopes = yt.token_scopes()
        except Exception as e:                               # noqa: BLE001
            scopes = [f"확인 실패: {str(e)[:80]}"]
    done = {}
    for p in sorted(PILOTS.glob("*/status.json")):
        st = _load(p, {})
        if not st or (pid and st.get("id") != pid):
            continue
        res = ((st.get("artifacts") or {}).get("upload") or {}).get("result") or {}
        if not res.get("video_id"):
            continue
        start = (res.get("at") or _now())[:10]
        end = time.strftime("%Y-%m-%d", time.gmtime())
        try:
            m = stats_fn(res["video_id"], start, end)
            sv = {"at": _now(), "views": int(m.get("views") or 0), "minutes": float(m.get("estimatedMinutesWatched") or 0),
                  "avg_view_s": float(m.get("averageViewDuration") or 0), "avg_view_pct": float(m.get("averageViewPercentage") or 0),
                  "subs": int(m.get("subscribersGained") or 0), "likes": int(m.get("likes") or 0), "comments": int(m.get("comments") or 0)}
            sv["subs_per_1k"] = round(sv["subs"] * 1000 / sv["views"], 2) if sv["views"] else 0
            sv["like_rate"] = round(sv["likes"] * 100 / sv["views"], 2) if sv["views"] else 0
            sv["source"] = m.get("_source", "analytics")
            if sv["source"] == "data_api":                   # 공개 통계만 — 시청 시간·구독 증가는 yt-analytics 권한이 있어야 나온다
                sv["partial"] = True
                sv["missing_reason"] = (m.get("_errors") or {}).get("analytics", "")[:160]
        except Exception as e:                               # noqa: BLE001
            msg = str(e)
            sv = {"at": _now(), "error": ("권한 없음 — 토큰 재발급 필요(scripts/youtube_oauth.py) · " + msg[:200]
                                          if "insufficient" in msg.lower() or "403" in msg or "scope" in msg.lower() else msg[:200])}
        if scopes is not None:
            sv["token_scopes"] = scopes
        st["artifacts"]["upload"]["stats"] = sv
        _save(p, st)
        done[st["id"]] = sv
    return done


# ── 자동 검사(완성본) ─────────────────────────────────────────────────────
def _frame_gray(mp4: Path, t: float):
    import numpy as np
    from PIL import Image
    b = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    if not b:
        return None
    return np.asarray(Image.open(io.BytesIO(b)).convert("L")).astype(float)


def _white_run(v) -> int:
    n = 0
    while n < len(v) and v[n] > 225:
        n += 1
    return n


def auto_checks(mp4: Path, body_s: float = 0.0, step: float = 0.25) -> dict:
    """흰 가장자리 줄 · 음량 · 길이. 결과는 화면에 그대로 보여준다(통과/불통과 + 실측값)."""
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(mp4)], capture_output=True, text=True).stdout or 0)
    worst, t = 0, 0.0
    end = body_s or dur
    while t < end:
        g = _frame_gray(mp4, t)
        if g is not None:
            c = g.mean(0)
            worst = max(worst, _white_run(c), _white_run(c[::-1]))
        t += step
    er = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp4), "-af", "ebur128", "-f", "null", "-"],
                        capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", er)
    lufs = float(m[-1]) if m else None
    return {
        "at": _now(),
        "duration_s": round(dur, 2),
        "white_edge_px": {"value": int(worst), "ok": worst == 0, "rule": "좌우 가장자리 흰 줄 0px"},
        "loudness_lufs": {"value": lufs, "ok": lufs is not None and abs(lufs + 16) <= 1.0, "rule": "-16 LUFS ±1"},
        "music": {"ok": True, "rule": "음악 없음(영상 AI 오디오는 조립 때 전부 버림)"},
    }


def motion_checks(mp4: Path, hook: dict | None) -> dict:
    """★맨 앞 움직임 검사(운영자 선택 2026-10-09 · 실사고: 왕게 편 — 앞 15초가 거의 멈춘 화면이라 81%가 바로 넘김).
    승인을 막지는 않고 「주의」로 알린다(warn). 기준은 지금까지 올린 3편 실측으로 정한 잠정값."""
    sys.path.insert(0, str(V2 / "tools"))
    import assemble as A                                     # noqa: E402
    out = {}
    if hook:
        m = float(hook.get("motion") or 0)
        how = {"auto": "자동 선택", "trial": "시험 릴스 구간"}.get(hook.get("by"), "운영자 지정")
        out["hook_motion"] = {"value": m, "ok": m >= A.HOOK_MIN_MOTION, "warn": True,
                              "rule": f"맨 앞 2초 움직임 {A.HOOK_MIN_MOTION:g} 이상 · {hook['cut']}번 컷 {hook['at']}초부터({how}) · "
                                      "실측: 왕게 1.0(81% 바로 넘김) · 대왕구족충 3.8 · 유령해삼 6.9"}
    f = A.window_motion(A.motion_series(mp4, dur=A.FRONT_S), 0.0, A.FRONT_S)
    out["front_motion"] = {"value": f, "ok": f >= A.FRONT_MIN_MOTION, "warn": True,
                           "rule": f"앞 15초 평균 움직임 {A.FRONT_MIN_MOTION:g} 이상(잠정) · 실측: 왕게 1.4 · 유령해삼 2.5 · 대왕구족충 7.4"}
    return out


# ── ② 대본 자동 작성(운영자 지적 2026-09-30 · 실사고) ──────────────────────────────
# 실사고: 새 편을 시작하면 대본 단계가 '작업 중'으로 바뀌고 화면엔 "대본을 작성하고 있습니다"가 떴지만, **실제로 대본을
#   쓰는 자동 작업이 없었다**(대본은 Claude 세션이 손으로 쓰던 시절의 상태값만 남음) → 아무 일도 안 일어나는데 '작업 중'.
# 고침: 「이 종으로 시작」·대본 「수정 요청」·「다시 하기」가 실제로 아래 작업을 돌린다(v2-admin.yml → write_script).
#   ① 출처 수집: 위키백과(영어·일본어) 본문 + v1 종 자료 — 주소가 남는 출처만
#   ② 사실 추출(AI) → **출처 원문 인용이 실제 본문에 그대로 있는 사실만** 채택(F번호) — 날조 차단
#   ③ 대본(AI, 처음부터 일본어) → 코드 검사(8컷 · 근거 F번호 · 사실에 없는 숫자 금지 · 길이 · 호소 문구 금지) → 불통과면 고쳐 쓰게 재시도
#   ④ 읽기(히라가나) 자동 → 나레이션 미리듣기(TTS · 약 $0.01) → 컷 길이(짝수 초) 계산
#   ⑤ AI 교차 검사 → '승인 대기'.  실패하면 '작업 중'으로 두지 않고 **실패 이유 + 다시 시도 버튼**을 남긴다(job 기록).
WIKI_UA = "shorts-admin/1.0 (v2 script writer; github.com/jtaechul/Product)"
SCRIPT_CUTS = 8
HOOK_S, ANSWER_S = 2.0, 2.0                                 # 후킹 발췌 2초 · 정답 카드 2초(assemble.py 와 같은 값)
SPEECH_CPS = 8.5                                            # 낭독문(히라가나) 글자/초 — 120% 속도 실측(시범편 8.0~9.6)
SPEECH_MAX_S = 47.0                                         # 나레이션 합계 상한(컷 여유 포함 약 54초가 되게)
JOB_STALE_MIN = 25                                          # 이보다 오래 '진행 중'이면 멈춘 것으로 본다(페이지 표시)
_CTA_WORDS = re.compile(r"チャンネル登録|高評価|コメント|フォロー|登録して|구독|댓글|좋아요")
# 1번 컷을 역사·발견 이야기로 여는 것 금지(운영자 선택 2026-10-09 B: 「1번 컷은 역사 설명 대신 생물의 이상한 행동부터」)
_HISTORY_OPEN = re.compile(r"(?:1[5-9]\d\d|20\d\d)年|学者|研究者|博士|探検|調査船|発見され")   # 「200年生きる」 같은 특징은 허용


def set_job(pid: str, stage: str, status: str, text: str = "", action: str = "") -> dict:
    """자동 작업 기록 — 페이지는 이 기록이 있을 때만 '진행 중'을 보여 준다(없거나 실패면 사실대로)."""
    st = load_status(pid)
    job = {"stage": stage, "status": status, "at": _now(), "action": action}
    if text:
        job["text"] = text
    st.setdefault("jobs", {})[stage] = job
    if status == "failed":
        _note(st, stage, "error", text)
    _save(status_path(pid), st)
    return st


def job_fail(pid: str, action: str, text: str = "") -> None:
    """워크플로가 도중에 죽었을 때(if: failure()) — 진행 중으로 남은 작업을 '실패'로 바꾼다."""
    try:
        st = load_status(pid)
    except SystemExit:
        return
    for stage, job in (st.get("jobs") or {}).items():
        if job.get("status") == "running":
            set_job(pid, stage, "failed", text or f"자동 작업이 중간에 멈췄습니다({action}) — 「다시 시도」를 눌러 주세요", action)


def _wiki_get(url: str, get=None):
    import urllib.request
    if get:
        return get(url)
    req = urllib.request.Request(url, headers={"User-Agent": WIKI_UA})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                               # noqa: BLE001 — 429 등은 잠시 쉬고 재시도
            if i == 3:
                raise
            print(f"[wiki] 재시도 {i + 1}: {e}")
            time.sleep(3 * (i + 1))


def _wiki_article(lang: str, titles: list[str], get=None) -> dict | None:
    import urllib.parse
    for t in [x for x in titles if x]:
        q = urllib.parse.urlencode({"action": "query", "prop": "extracts|langlinks|info", "explaintext": 1,
                                    "redirects": 1, "lllang": "ja", "inprop": "url", "titles": t, "format": "json"})
        d = _wiki_get(f"https://{lang}.wikipedia.org/w/api.php?{q}", get)
        for p in ((d or {}).get("query") or {}).get("pages", {}).values():
            txt = (p.get("extract") or "").strip()
            if "missing" in p or len(txt) < 200:
                continue
            ja = next((ll.get("*") for ll in p.get("langlinks") or [] if ll.get("lang") == "ja"), None)
            return {"title": p.get("title", t), "url": p.get("fullurl") or f"https://{lang}.wikipedia.org/wiki/{t}",
                    "text": txt[:14000], "ja_title": ja}
    return None


def gather_sources(topic: dict, sp: dict | None = None, get=None) -> tuple[list[dict], str | None]:
    """출처 문서 목록([{id,url,title,text}])과 일본어 이름(일본어 위키 제목 · 없으면 None)."""
    sci = topic.get("sci", "")
    genus = sci.split()[0] if " " in sci else ""
    docs, ja_name = [], None
    def safe(lang, titles):                                  # 한쪽 위키가 막혀도(429 등) 다른 출처로 계속
        try:
            return _wiki_article(lang, titles, get)
        except Exception as e:                               # noqa: BLE001
            print(f"[wiki] {lang} 실패: {e}")
            return None
    en = safe("en", [sci, topic.get("name_en", ""), genus])
    if en:
        docs.append({"url": en["url"], "title": "Wikipedia(en) " + en["title"], "text": en["text"]})
    ja = safe("ja", [en.get("ja_title") if en else None, sci])
    if ja:
        docs.append({"url": ja["url"], "title": "Wikipedia(ja) " + ja["title"], "text": ja["text"]})
        ja_name = re.sub(r"\s*[(（].*$", "", ja["title"]).strip() or None
    sp = sp or {}
    base = [f for f in sp.get("fun_facts") or [] if f]
    for k, lab in (("depth_range_m", "서식 수심(m)"), ("distribution", "분포"), ("habitat", "서식지")):
        if sp.get(k):
            base.append(f"{lab}: {sp[k]}")
    if sp.get("diet"):
        base.append("먹이: " + ", ".join(sp["diet"]))
    if base:                                                 # v1 에서 모아 둔 종 자료(출처 이름만 있음 — 주소 없음)
        docs.append({"url": "", "title": "v1 종 자료(" + " · ".join(sp.get("sources") or ["출처 이름 없음"]) + ")",
                     "text": "\n".join(base)})
    for i, d in enumerate(docs, 1):
        d["id"] = f"S{i}"
    return docs, ja_name


_FACT_PROMPT = """You are a strict science fact extractor. From the SOURCE DOCUMENTS below ONLY, extract up to 14 facts about
the deep-sea animal {sci} ({name_en}) that would make a gripping 50-second story. Prefer: discovery events (year, place,
people, expedition), records, size with units, depth, how it moves/eats/defends, surprising traits, famous incidents.
Rules: every fact MUST be supported by a verbatim quote copied EXACTLY from one document (same characters, max 220 chars,
no ellipsis, no paraphrase). If a document talks about a whole genus/family, say so in the fact (scope!). Never add knowledge
that is not in the documents.
Return JSON only: {{"facts":[{{"fact_ko":"한국어 한 문장","fact_jp":"日本語で一文","quote":"exact quote","src":"S1"}}]}}

# SOURCE DOCUMENTS
{docs}
"""

_SCRIPT_PROMPT = """あなたはNHKの科学ドキュメンタリーの構成作家です。深海生物「{name}」のYouTubeショート(縦型・約54秒)の
ナレーション台本を、最初から日本語で書いてください(翻訳調は禁止)。映像は手作りのミニチュア・ジオラマで再現します。
# 厳守ルール
- ちょうど{n}カット。1カット=1〜2文、日本語で18〜44文字。全体で300文字以内。
- 下の「事実リスト」にあることだけを書く。リストにない数字・年・地名・人名・断定・誇張は書かない。
  各カットに根拠の事実番号を付ける(例 "F2,F5")。出典どうしで数値が違えば広い方を断定しない。
- 数字は何の数字か分かるように書く(「水深5000メートル」「体長25センチ」)。数字は算用数字で。
- 1カット目: この生き物そのものの、思わず目を疑う行動・姿から始める(画面で生き物が動いている場面)。
  発見の年・学者・探検の話から始めない(歴史は3カット目以降で短く)。2カット目もその生き物が動く場面を続ける。
- 前提から親切に。専門用語はやさしく言い換える。
- 生き物を「あだ名」(海の豚・頭のないニワトリなど)で呼ぶときは、実際に何の生き物か(ナマコの仲間など)も分かるように書く。scene_ko も同じ(例: 바다돼지(해삼))。
- 同じ単語・言い回しを何度も繰り返さない。文末も単調にしない。
- {n}カット目: 余韻のある締め(画面は暗闇に消えていく)。「チャンネル登録」「コメント」などの呼びかけは書かない(共通エンディングが別にある)。
- 呼び名: {name_rule}
- core(この回の核・一つだけ): 事実リストから、この回でいちばん驚く事実を**一つだけ**選び、その番号を core に書く
  (候補: {core}・事実リストで裏付けること)。冒頭の問い(hook)・動画タイトル・最後の3カットのどれかが、すべてこの同じ事実を扱う。
  ほかの事実は、その理由や背景として使う(話をあちこちに広げない)。
- hook(冒頭2秒・0秒からナレーションの声つき): core の事実を描くカットの番号を cut にする(そのカットの fact に core を入れる)。
  「この生き物は？」のような名前当てクイズは禁止。core の事実を、スクロールの指が止まる「信じられない一行」にして、
  型の違う候補をちょうど3つ出す。型 = 正体の反転 / 常識破り / 異常な行動 / 欠けた体 / 極端な数字(事実リストにある数字だけ)。
  ・text_jp: 画面に大きく出す一行。「、」を除いて12文字以内・2行まで。改行したい所にだけ「、」を入れる(1行8文字以内・単語の途中で切らない)。
    いちばん驚く言葉を先頭近くに。生き物の名前・呼び名は入れない。事実を誇張しない(「〜と疑われている」程度の事実は「？」をつける)。
  ・key_jp: text_jp の中でいちばん強い言葉(赤で強調する・6文字以内・text_jp にそのまま含まれる)。
  ・voice_jp: 0秒からナレーションが読む一言(text_jp と同じ意味・少し補ってよい・2.5秒以内・key_jp を含む・名前は入れない)。
  ・answer_jp は最後のカードに出す生き物の呼び名(台本で使った呼び名と同じ)。カット1・2には出さず、3カット目以降で明かす。
{pattern_hint}{feedback}
# 出力(JSONのみ)
{{"core":"F4","cuts":[{{"cut":1,"jp":"日本語の台詞","ko":"자연스러운 한국어 번역","fact":"F1,F3",
"scene_ko":"이 컷의 화면 아이디어(미니어처 디오라마 · 한국어 한 줄 · 별명은 실제 생물을 괄호로: 바다돼지(해삼))","annotation":"画面の注釈(日本語のみ・韓国語禁止・14文字以内・数字は事実どおり・なければ空)"}}],
"hook":{{"cut":6,"answer_jp":"呼び名","answer_ko":"한국어 이름","candidates":[
{{"pattern":"常識破り","text_jp":"ナマコなのに、泳ぐ","key_jp":"泳ぐ","voice_jp":"ナマコなのに、海の中を泳ぐ","text_ko":"해삼인데 헤엄친다"}},
{{"pattern":"欠けた体","text_jp":"頭も骨もない","key_jp":"頭も骨も","voice_jp":"頭も、骨も、目もない","text_ko":"머리도 뼈도 없다"}},
{{"pattern":"異常な行動","text_jp":"光る皮を、おとりに捨てる","key_jp":"光る皮","voice_jp":"襲われると、光る皮をおとりに捨てる","text_ko":"빛나는 피부를 미끼로 버린다"}}]}}}}
(上の candidates の例は書き方の見本。今回の生き物の事実だけで書くこと)

# 事実リスト
{facts}
"""


def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s​\"'“”‘’「」『』]", "", s)


def ground_facts(raw: list[dict], docs: list[dict]) -> tuple[list[dict], int]:
    """AI가 뽑은 사실 중 **인용문이 실제 출처 본문에 그대로 있는 것만** F번호를 붙여 채택. (채택 목록, 버린 수)"""
    by = {d["id"]: d for d in docs}
    out, dropped, seen = [], 0, set()
    for f in raw or []:
        d = by.get(str(f.get("src", "")).strip())
        q = str(f.get("quote", "")).strip()
        if not d or len(_norm(q)) < 8 or "..." in q or "…" in q or _norm(q) not in _norm(d["text"]) or q in seen:
            dropped += 1
            continue
        seen.add(q)
        out.append({"id": f"F{len(out) + 1}", "fact": str(f.get("fact_ko", "")).strip(), "fact_jp": str(f.get("fact_jp", "")).strip(),
                    "quote": q, "sources": [d["url"]] if d["url"] else [], "source_title": d["title"]})
    return out, dropped


def estimate_speech(tts: str) -> float:
    return round(len(re.sub(r"\s", "", tts or "")) / SPEECH_CPS, 2)


def _nums(s: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", (s or "").replace(",", "").replace("，", "")))


def validate_script(cuts: list[dict], facts: list[dict]) -> list[str]:
    """대본 코드 검사 — 불통과 이유 목록(비면 통과). AI에게 그대로 돌려줘 고쳐 쓰게 한다."""
    by = {f["id"]: f for f in facts}
    probs = []
    if len(cuts) != SCRIPT_CUTS:
        probs.append(f"カット数が{len(cuts)}です。ちょうど{SCRIPT_CUTS}カットにしてください。")
    total = 0
    for i, c in enumerate(cuts, 1):
        jp, ko = str(c.get("jp", "")), str(c.get("ko", ""))
        ids = re.findall(r"F\d+", str(c.get("fact", "")))
        if not ids or any(x not in by for x in ids):
            probs.append(f"カット{i}: 根拠の事実番号がない/存在しない番号です({c.get('fact')})。")
        if re.search(r"[가-힣]", jp) or not re.search(r"[ぁ-んァ-ン一-龥]", jp):
            probs.append(f"カット{i}: 日本語の台詞になっていません。")
        m = _KO_NICK.search(str(c.get("scene_ko", "")))
        if m:                                                # ★별명만 쓰면 콘티가 진짜 동물을 그린다(실사고 2026-10-06 바다돼지)
            probs.append(f"カット{i}: scene_ko の「{m.group(1)}」は呼び名(あだ名)だけです。実際の生き物を括弧で添えてください(例: 바다돼지(해삼))。")
        ann = str(c.get("annotation", ""))
        if re.search(r"[가-힣ㄱ-ㆎ]", ann):                   # ★실사고 2026-10-05: 한국어 주석 → 영상 글꼴(일본어)에 없어 네모 □로 깨짐
            probs.append(f"カット{i}: 注釈「{ann}」に韓国語があります。注釈は日本語だけで書いてください。")
        if len(ann) > 14:
            probs.append(f"カット{i}: 注釈「{ann}」が長すぎます({len(ann)}文字)。14文字以内にしてください。")
        if not re.search(r"[가-힣]", ko):
            probs.append(f"カット{i}: 韓国語訳(ko)がありません。")
        if not 12 <= len(jp) <= 50:
            probs.append(f"カット{i}: {len(jp)}文字です。18〜44文字にしてください。")
        if _CTA_WORDS.search(jp):
            probs.append(f"カット{i}: 呼びかけ(登録・コメント等)は書かないでください。")
        if i == 1 and _HISTORY_OPEN.search(jp):             # ★왕게 편 실사고 2026-10-09: 「1800年代…学者は」로 시작 → 정지 화면 · 즉시 이탈
            probs.append(f"カット1: 「{_HISTORY_OPEN.search(jp).group(0)}」— 発見の年・学者・探検の話から始めないでください。"
                         "この生き物そのものの、目を疑う行動・姿から始めてください(歴史は3カット目以降)。")
        allowed = set().union(*[_nums(by[x]["fact"] + " " + by[x].get("fact_jp", "") + " " + by[x]["quote"]) for x in ids if x in by]) if ids else set()
        bad = sorted((_nums(jp) | _nums(str(c.get("annotation", "")))) - allowed)
        if bad:
            probs.append(f"カット{i}: 根拠の事実にない数字 {', '.join(bad)} があります。事実どおりにするか削ってください。")
        total += estimate_speech(auto_reading(jp)) if jp else 0
    if total > SPEECH_MAX_S:
        probs.append(f"全体が長すぎます(約{total:.0f}秒)。合計{SPEECH_MAX_S:.0f}秒以内(約300文字以内)に短くしてください。")
    return probs


# ★핵심 사실 하나로(운영자 선택 2026-10-09 D · 실사고: 왕게 편 — 후킹은 「물고기가 알을 낳는」 이야기, 제목은 다른 사실,
#   1번 컷은 학자 이야기라 한 편이 여러 사실로 흩어짐 + 생김새만 봐도 게인데 「이 생물은?」 정체 질문).
#   후킹 질문·제목·마지막 3컷 중 하나가 같은 핵심 사실(core F번호)을 다루고, 생김새로 정답이 보이는 생물은 정체 질문 금지.
_IDENTITY_Q = re.compile(r"(この(生き物|生物|動物|魚|子|仲間)(は|って)?|正体(は)?|何者(でしょう)?|だれ|誰)[？?]$")
_FAMILIAR = re.compile(r"カニ|ガニ|ヤドカリ|エビ|イカ|タコ|ダコ|サメ|ザメ|クラゲ|ヒトデ|ウニ")


def hook_type(question: str) -> str:
    """후킹 질문 종류: 'identity'(정체 맞히기 「…この生き物は？」) | 'fact'(사실 질문 「…何を隠している？」).
    ★2026-10-09 후킹 개편 뒤 새 편은 'line'(믿기 힘든 사실 한 줄) — 그건 hook["type"]에 저장돼 있다."""
    return "identity" if _IDENTITY_Q.search(str(question or "").strip()) else "fact"


# ★★후킹 개편(운영자 선택 2026-10-09 · 실사고: 첫 2초가 무음 + 22자짜리 이름 퀴즈가 1.8초만 떠서 다 못 읽음 +
#   빨간 글자 3줄이 생물을 가림 + 「投 / げ捨てる」처럼 단어 중간 줄바꿈 → 왕게 편 81% 넘김).
#   ① 0초부터 목소리: voice_jp 를 나레이션 목소리로 읽어 후킹에 깐다(TTS 약 $0.001)
#   ② 한눈에 읽히는 글자: 화면 문장 12자 이내(「、」 제외) · 2줄까지 · 「、」 자리에서만 줄바꿈(1줄 8자 이내)
#   ③ 이름 맞히기 금지 → 핵심 사실의 「믿기 힘든 한 줄」을 5가지 틀로 후보 3개 → 운영자가 대본 승인 때 고름 · 제목도 같은 문장
#   ④ 흰 글자 + 검은 테두리, 핵심 단어(key_jp)만 빨강 · 화면 위쪽(유튜브 버튼에 가리지 않는 높이) · 0초부터 표시
HOOK_LINE_MAX = 12
HOOK_SEG_MAX = 8
HOOK_KEY_MAX = 6
HOOK_VOICE_MAX_S = 2.6
HOOK_PATTERNS = ("正体の反転", "常識破り", "異常な行動", "欠けた体", "極端な数字")


def hook_segments(text: str) -> list[str]:
    """화면 문장의 줄(「、」에서만 나눔 · 쉼표는 화면에 안 찍음)."""
    return [p.strip() for p in re.split(r"[、,]", str(text or "")) if p.strip()]


def _visible_len(text: str) -> int:
    return len(re.sub(r"[、,\s]", "", str(text or "")))


def name_stems(*names: str) -> list[str]:
    """이름과 그 줄기(「タラバガニ科」→「タラバガニ」) — 후킹 문장·제목에 넣으면 안 되는 말."""
    out = []
    for x in names:
        x = str(x or "").strip()
        for y in (x, re.sub(r"(科|属|類|の仲間|과|속|류)$", "", x)):
            if len(y) >= 2 and y not in out:
                out.append(y)
    return out


def validate_hook_line(c: dict, facts: list[dict], banned: list[str], where: str = "hook") -> list[str]:
    """후킹 한 줄(화면 문장 text_jp · 빨간 단어 key_jp · 0초 목소리 voice_jp · 틀 pattern) 코드 검사."""
    t, k, v = (str(c.get(x, "") or "").strip() for x in ("text_jp", "key_jp", "voice_jp"))
    probs = []
    segs = hook_segments(t)
    if not t or _visible_len(t) > HOOK_LINE_MAX:
        probs.append(f"{where}: text_jp「{t}」は{_visible_len(t)}文字です。「、」を除いて{HOOK_LINE_MAX}文字以内にしてください。")
    if len(segs) > 2 or any(len(x) > HOOK_SEG_MAX for x in segs):
        probs.append(f"{where}: text_jp は2行まで・1行{HOOK_SEG_MAX}文字以内です。改行したい所にだけ「、」を入れてください(単語の途中で切らない)。")
    if _IDENTITY_Q.search(t) or _IDENTITY_Q.search(v):
        probs.append(f"{where}: 「この生き物は？」のような名前当ては使わないでください。核の事実を、信じられない一行にしてください。")
    if not k or k not in t or len(k) > HOOK_KEY_MAX:
        probs.append(f"{where}: key_jp「{k}」は text_jp にそのまま含まれる{HOOK_KEY_MAX}文字以内の、いちばん強い言葉にしてください。")
    if not v:
        probs.append(f"{where}: voice_jp(0秒からナレーションが読む一言)がありません。")
    else:
        if k and k not in v:
            probs.append(f"{where}: voice_jp に key_jp「{k}」を入れてください(画面と同じ言葉を声でも言う)。")
        s = estimate_speech(auto_reading(v))
        if s > HOOK_VOICE_MAX_S:
            probs.append(f"{where}: voice_jp「{v}」は長すぎます(約{s:.1f}秒)。{HOOK_VOICE_MAX_S}秒以内にしてください。")
    for w in banned:
        if w in t or w in v:
            probs.append(f"{where}: 名前「{w}」を入れないでください(名前は最後のカードで見せる)。")
    if _CTA_WORDS.search(t + v):
        probs.append(f"{where}: 呼びかけ(登録・コメント等)を入れないでください。")
    allowed = set().union(*[_nums(f["fact"] + " " + f.get("fact_jp", "") + " " + f.get("quote", "")) for f in facts]) if facts else set()
    bad = sorted((_nums(t) | _nums(v)) - allowed)
    if bad:
        probs.append(f"{where}: 根拠の事実にない数字 {', '.join(bad)} があります。")
    if c.get("pattern") not in HOOK_PATTERNS:
        probs.append(f"{where}: pattern は {' / '.join(HOOK_PATTERNS)} のどれかにしてください。")
    return probs


def validate_hook_candidates(hook: dict, cuts: list[dict], facts: list[dict], name: str = "") -> list[str]:
    """새 후킹(후보 3개) 검사: 컷 번호 · 마지막 카드 이름 · 후보마다 validate_hook_line · 서로 다른 문장."""
    probs = []
    try:
        cut = int(hook.get("cut", 0))
    except (TypeError, ValueError):
        cut = 0
    if not 1 <= cut <= max(1, len(cuts)):
        probs.append(f"hook.cut={hook.get('cut')} は存在しないカット番号です。")
    a = str(hook.get("answer_jp", "")).strip()
    if not a or len(a) > 24:
        probs.append("hook.answer_jp(最後のカードに出す呼び名)が空か長すぎます。")
    if a and any(a in str(c.get("jp", "")) for c in cuts[:2]):
        probs.append(f"呼び名「{a}」がカット1〜2に出ています。3カット目以降で初めて明かしてください。")
    cands = hook.get("candidates")
    if not isinstance(cands, list) or len(cands) != 3 or not all(isinstance(c, dict) for c in cands):
        return probs + ["hook.candidates は型の違う候補をちょうど3つにしてください。"]
    banned = name_stems(a, name)
    for i, c in enumerate(cands, 1):
        probs += validate_hook_line(c, facts, banned, where=f"候補{i}")
    if len({_norm(c.get("text_jp", "")) for c in cands}) < 3:
        probs.append("3つの候補の text_jp が同じです。言い方や型を変えてください。")
    return probs


def hook_from_candidate(hk: dict, i: int) -> dict:
    """후보 i 를 지금 후킹(화면 문장·빨간 단어·목소리·틀)으로 — 목소리 파일은 다음 조립 때 다시 만든다."""
    c = hk["candidates"][i]
    out = dict(hk)
    out.update(question_jp=str(c["text_jp"]).strip(), question_ko=str(c.get("text_ko", "")).strip(),
               key_jp=str(c["key_jp"]).strip(), voice_jp=str(c["voice_jp"]).strip(), pattern=c.get("pattern", ""),
               chosen=i, type="line")
    return out


def validate_core(core: str | None, hook: dict | None, cuts: list[dict], facts: list[dict]) -> list[str]:
    """핵심 사실 하나(core) 검사: 사실 번호인지 · 후킹 컷이 그 사실을 다루는지 · 마지막 3컷에서 다시 다루는지."""
    c = str(core or "").strip()
    if c not in {f["id"] for f in facts}:
        return [f"core「{core}」が事実リストの番号ではありません。この回の核になる事実を一つだけ選び、その番号(例 F3)を書いてください。"]
    has = lambda x: c in re.findall(r"F\d+", str(x.get("fact", "")))      # noqa: E731
    probs = []
    try:
        hc = int((hook or {}).get("cut", 0))
    except (TypeError, ValueError):
        hc = 0
    if 1 <= hc <= len(cuts) and not has(cuts[hc - 1]):
        probs.append(f"hook.cut={hc} のカットが核の事実 {c} を扱っていません。冒頭の問いは核の事実を描くカットから出してください"
                     f"(そのカットの fact に {c} を入れる)。")
    if cuts and not any(has(x) for x in cuts[-3:]):
        probs.append(f"核の事実 {c} が最後の3カットに出てきません。終盤で核の事実に戻り、冒頭の問いの答えを回収してください。")
    return probs


def validate_hook(hook: dict | None, cuts: list[dict], facts: list[dict], name: str = "") -> list[str]:
    """후킹(맨 앞 2초 질문 + 마지막 정답) 코드 검사 — 불통과 이유 목록. name: 和名(생김새로 정답이 보이는지 판단용)."""
    if not isinstance(hook, dict):
        return ["hook(冒頭の問い)がありません。cuts と一緒に hook を出してください。"]
    probs = []
    q, a = str(hook.get("question_jp", "")).strip(), str(hook.get("answer_jp", "")).strip()
    try:
        cut = int(hook.get("cut", 0))
    except (TypeError, ValueError):
        cut = 0
    if not 1 <= cut <= max(1, len(cuts)):
        probs.append(f"hook.cut={hook.get('cut')} は存在しないカット番号です。")
    if not 8 <= len(q) <= 24 or not q.endswith(("？", "?")):
        probs.append(f"hook.question_jp「{q}」は8〜22文字で「？」で終わる問いにしてください。")
    if _CTA_WORDS.search(q):
        probs.append("hook.question_jp に呼びかけ(登録・コメント等)を入れないでください。")
    if not a or len(a) > 24:
        probs.append("hook.answer_jp(正解の呼び名)が空か長すぎます。")
    if a and a in q:
        probs.append("hook.question_jp に答えの名前が入っています(答えは最後に見せる)。")
    if a and any(a in str(c.get("jp", "")) for c in cuts[:2]):
        probs.append(f"答え「{a}」がカット1〜2に出ています。3カット目以降で初めて明かしてください。")
    fam = _FAMILIAR.search(a + " " + str(name or ""))
    if hook_type(q) == "identity" and fam:
        probs.append(f"「{q}」は正体当てですが、答え「{a}」は見た目で{fam.group(0)}の仲間だと分かってしまいます。"
                     "正体当てにせず、核の事実についての問い(例「エラの中に、何を隠している？」)にして、answer_jp はその短い答えにしてください。")
    if hook_type(q) == "fact" and len(a) > 14:
        probs.append(f"事実の問いの答え「{a}」が長すぎます({len(a)}文字)。14文字以内にしてください。")
    allowed = set().union(*[_nums(f["fact"] + " " + f.get("fact_jp", "") + " " + f.get("quote", "")) for f in facts]) if facts else set()
    bad = sorted(_nums(q) - allowed)
    if bad:
        probs.append(f"hook.question_jp に根拠の事実にない数字 {', '.join(bad)} があります。")
    return probs


def _json_obj(txt: str) -> dict:
    m = re.search(r"\{.*\}", txt or "", re.S)
    if not m:
        raise ValueError("AI 응답에 JSON 없음")
    return json.loads(m.group(0))


def _species_data(topic: dict) -> dict:
    try:
        sys.path.insert(0, str(ROOT))
        from src.categories.deep_sea import data             # noqa: E402
        return data.SPECIES.get(topic.get("key", ""), {}) or {}
    except Exception:                                        # noqa: BLE001
        return {}


def first_timing(cuts: list[dict], tps: list[dict] | None, lead: float = 0.15) -> tuple[list[dict], list[str]]:
    """새 대본의 컷 길이 = (앞 여백 + 나레이션 + 여유 0.6초)를 짝수 초(4/6/8/10)로 올림. tps 가 없으면 글자 수로 추정."""
    timing, probs, i = [], [], 0
    for c in cuts:
        n = len(_chunks(c["jp"]))
        if tps:
            seg = tps[i:i + n]
            nxt = tps[i + n]["start"] if i + n < len(tps) else (seg[-1]["end"] or seg[-1]["start"])
            a0, a1 = seg[0]["start"], nxt
            speech = round(a1 - a0, 2)
            loc = [{"jp_seg": None, "start": round(t["start"] - a0 + lead, 3), "end": round((t["end"] or a1) - a0 + lead, 3)} for t in seg]
        else:
            a0 = a1 = None
            speech, loc = estimate_speech(c["tts"]), []
        need = lead + speech + MARGIN_S
        if need > 10:
            probs.append(f"{c['cut']}번 컷: 나레이션 {speech:.1f}초 — 한 컷(최대 10초)에 너무 깁니다. 대사를 줄이세요")
        sec = _even_up(min(need, 10))
        timing.append({"cut": c["cut"], "sec": sec, "audio_from": a0, "audio_to": a1, "speech_s": speech, "lead": lead,
                       "local_tps": loc})
        i += n
    return timing, probs


def write_script(pid: str, feedback: str = "", ask=None, get=None, tts: bool = True) -> dict:
    """대본 자동 작성(①~⑤). ask/get: 테스트용 대체(AI 응답·웹 요청). tts=False 면 미리듣기 없이 글자 수로 길이 추정."""
    st = load_status(pid)
    topic = st.get("topic") or {}
    ask_facts = ask or _gemini_text                          # 사실 추출은 온도 0(그대로 옮기기)
    ask_script = ask or (lambda p: _gemini_text(p, temperature=0.7))   # 대본은 약간의 문장력
    set_job(pid, "script", "running", "대본 자동 작성 중 — 출처 수집 → 사실 추출 → 대본 → 검증 → 미리듣기", "write_script")
    try:
        old = _load(_script_path(pid)) or {}
        keep_facts = bool(feedback) and old.get("facts") and old.get("generated")
        if keep_facts:                                       # 수정 요청: 이미 검증한 사실은 그대로, 대본만 고쳐 쓴다
            facts, docs, ja_name = old["facts"], old.get("source_docs", []), (old.get("subject") or {}).get("jp_name")
            dropped = 0
        else:
            docs, ja_name = gather_sources(topic, _species_data(topic), get)
            if not docs:
                raise RuntimeError("출처 문서를 하나도 찾지 못했습니다(위키백과·종 자료 없음)")
            dtxt = "\n\n".join(f"[{d['id']}] {d['title']} {d['url']}\n{d['text']}" for d in docs)
            raw = _json_obj(ask_facts(_FACT_PROMPT.format(sci=topic.get("sci", ""), name_en=topic.get("name_en", ""), docs=dtxt)))
            facts, dropped = ground_facts(raw.get("facts") or [], docs)
            if len(facts) < 4:
                raise RuntimeError(f"출처 원문으로 확인된 사실이 {len(facts)}개뿐입니다(버린 것 {dropped}개) — 대본을 쓸 수 없습니다")
        name = ja_name or topic.get("name_en") or topic.get("sci", "")
        core = (_load(TOPIC_SCORES, {}) or {}).get(pid, {}).get("hook_jp", "")
        name_rule = (f"和名「{ja_name}」を使う。" if ja_name else
                     f"和名がないので、事実リストにある呼び名(英名「{topic.get('name_en', '')}」の直訳など)か「この生き物」と呼ぶ。和名を作らない。")
        ftxt = "\n".join(f"{f['id']}: {f.get('fact_jp') or f['fact']}(出典原文: {f.get('quote', '')})" for f in facts)
        fb, cuts, probs = "", [], []
        if feedback:
            prev = "\n".join(f"カット{c['cut']}: {c['jp']}" for c in old.get("cuts", []) if c.get("jp"))
            fb = f"# 運営者の修正依頼(必ず反映)\n{feedback}\n# 前の台本\n{prev}\n"
        hook = None
        hint = _pattern_hint()                               # 시험 릴스에서 이긴 후킹 틀(쌓였을 때만 · 참고)
        for attempt in range(3):
            gen = _json_obj(ask_script(_SCRIPT_PROMPT.format(name=name, n=SCRIPT_CUTS, name_rule=name_rule, feedback=fb, facts=ftxt, pattern_hint=hint,
                                                             core=core or "(なし — 事実リストから最も驚く一つを選ぶ)")))
            cuts, hook, core_id = gen.get("cuts") or [], gen.get("hook"), str(gen.get("core") or "").strip()
            probs = validate_script(cuts, facts) + (validate_hook_candidates(hook, cuts, facts, name=ja_name or "")
                                                    if isinstance(hook, dict) else ["hook がありません。"]) + \
                validate_core(core_id, hook, cuts, facts)
            if not probs:
                break
            fb = (fb + "\n" if feedback else "") + "# 前回の台本の問題点(必ず直す)\n" + "\n".join("- " + p for p in probs) + "\n"
        if probs:
            raise RuntimeError("대본 검사를 3번 모두 통과하지 못했습니다: " + " / ".join(probs[:4]))
        out = []
        for i, c in enumerate(cuts, 1):
            jp = str(c["jp"]).strip()
            out.append({"cut": i, "jp": jp, "ko": str(c.get("ko", "")).strip(), "tts": auto_reading(jp),
                        "fact": ",".join(re.findall(r"F\d+", str(c.get("fact", "")))),
                        "scene_ko": str(c.get("scene_ko", "")).strip(), "annotation": str(c.get("annotation", "")).strip()})
        hk_cut = int(hook["cut"])
        cands = [{k: str(c.get(k, "") or "").strip() for k in ("pattern", "text_jp", "key_jp", "voice_jp", "text_ko")}
                 for c in hook["candidates"]]
        sc = {"episode": pid, "subject": {"scientific_name": topic.get("sci", ""), "jp_name": ja_name or "",
                                          "ko_name": st.get("name_ko", "")},
              # ★후킹(운영자 확정 2026-09-30 · 개편 2026-10-09): 맨 앞 = 본편 hk_cut 컷에서 발췌 + 0초부터 목소리 + 흰 글자 한 줄
              #   (핵심 단어만 빨강) · 후보 3개 중 운영자가 고른다(기본 1번) · 맨 뒤 = 생물 이름 카드
              "hook": hook_from_candidate({"cut": hk_cut, "at": None, "answer_jp": str(hook["answer_jp"]).strip(),
                                           "answer_ko": str(hook.get("answer_ko", "")).strip(), "candidates": cands}, 0),
              "core": core_id,                               # ★핵심 사실 하나(후킹·제목·마지막 3컷이 함께 다룸)
              "facts": facts, "source_docs": [{k: d[k] for k in ("id", "url", "title")} for d in docs],
              "cuts": out, "timing_rule": "컷 길이 = (앞 여백 0.15초 + 나레이션 + 여유 0.6초)를 짝수 초로 올림",
              "generated": {"at": _now(), "model": _TEXT_MODEL or "test", "feedback": feedback, "facts_dropped": dropped}}
        if old.get("cuts"):                                 # 이전 대본은 지우지 않고 보관
            sc["previous_scripts"] = (old.get("previous_scripts") or []) + [
                {"at": _now(), "script": {k: v for k, v in old.items() if k != "previous_scripts"}}]
        # ④ 나레이션 미리듣기 + 컷 길이
        tps, audio, tts_err = None, None, ""
        if tts:
            rid = f"r{time.strftime('%m%d%H%M', time.gmtime())}_script_tts"
            req = {"id": rid, "kind": "gen_tts", "purpose": "대본 자동 작성 — 나레이션 미리듣기 + 컷 길이 계산",
                   "items": [{"name": "body", "jp": "".join(c["jp"] for c in out), "segments": [s for c in out for s in _chunks(c["tts"])]}]}
            rp = PILOTS / pid / "requests" / f"{rid}.json"
            _save(rp, req)
            r = subprocess.run([sys.executable, str(V2 / "tools" / "run_request.py"), str(rp)], cwd=str(ROOT))
            tpf = PILOTS / pid / "out" / rid / "body_timepoints.json"
            if r.returncode == 0 and tpf.exists():
                tps, audio = _load(tpf), f"out/{rid}/body.wav"
            else:
                tts_err = "나레이션 미리듣기 실패(TTS) — 컷 길이는 글자 수로 추정"
        timing, tprobs = first_timing(out, tps)
        sc["timing_v5"] = timing
        sc["total_sec"] = sum(t["sec"] for t in timing)
        for c, t in zip(out, timing):
            c["sec"], c["speech_s"] = t["sec"], t["speech_s"]
        hsec = float(out[hk_cut - 1]["sec"])
        # 임시값(컷 한가운데 2초) — 조립 때 완성된 클립에서 「가장 많이 움직이는 2초」로 바뀐다(운영자가 직접 정하면 그 값)
        sc["hook"]["at"] = round(max(0.0, hsec / 2 - HOOK_S / 2), 2)
        sc["total_sec"] = sc["total_sec"] + HOOK_S + ANSWER_S
        _save(_script_path(pid), sc)
        st = load_status(pid)
        _sync_script_artifacts(st, sc)
        a = st["artifacts"]["script"]
        a.pop("crosscheck", None)
        if audio:
            a["audio"], a["tts_id"] = audio, rid
        st.setdefault("cost", {})["estimate"] = {"script": 0.05, "storyboard": round(IMG_USD * 4, 2),
                                                  "video": round(sum(t["sec"] for t in timing) * OMNI_USD_PER_SEC, 2)}
        a["verification"] = (f"자동 작성 · 출처 {len(docs)}곳 · 원문 인용이 확인된 사실 {len(facts)}개(확인 안 된 {dropped}개 버림) · "
                             f"코드 검사 통과 · 예상 길이 {sc['total_sec']}초" + (f" · {tts_err}" if tts_err else "")
                             + (" · " + " / ".join(tprobs) if tprobs else ""))
        st.setdefault("artifacts", {})["topic"] = {"facts": facts}
        st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": "대본 자동 작성(AI+나레이션)", "usd": 0.05})
        _note(st, "script", "auto", "대본 자동 작성 완료" + (" (수정 요청 반영)" if feedback else ""))
        _save(status_path(pid), st)
        crosscheck(pid, ask=ask)                            # ⑤ 교차 검사(실패해도 멈추지 않음)
        st = load_status(pid)
        st["stages"]["script"]["state"] = "review"
        _save(status_path(pid), st)
        return set_job(pid, "script", "done", "대본 자동 작성 완료 — 승인 대기", "write_script")
    except Exception as e:                                   # noqa: BLE001 — '작업 중'으로 남기지 않는다
        set_job(pid, "script", "failed", f"대본 자동 작성 실패: {str(e)[:220]} — 「다시 시도」를 눌러 주세요", "write_script")
        raise SystemExit(f"대본 자동 작성 실패: {e}")


# ── ③ 스토리보드 자동 · ④ 영상 자동(운영자 지시 2026-09-30 "다음으로 안 넘어간다" · 실사고) ────────────────
# 실사고: 대본을 승인해도 스토리보드·영상은 Claude 대화에서 손으로 만들어야 해서, 관리자 페이지에서는 아무 일도
#   일어나지 않았다. → 승인 관문마다 다음 단계가 **실제로 자동 실행**된다:
#   대본 승인 → write_storyboard(참조 실사 → 생물 카드 → 실사 대조(비전) → 8컷 콘티 격자 2장 → 승인 대기 · 약 $0.6)
#   콘티 승인 → make_video(컷별 초 단위 Omni 지시문(AI) → Omni Flash 8컷 → 조립(후킹·정답 카드) → 자동 검사 → 승인 대기 · 초당 $0.10)
#   수정 요청·다시 하기도 같은 함수를 메모와 함께 다시 돌린다(영상은 메모에 'N번' 컷이 있으면 그 컷만 다시 만든다 — 비용 절약).
STAGE_ACTION = {"script": "write_script", "storyboard": "write_storyboard", "video": "make_video"}
# ★미니어처 세계관(운영자 승인 2026-10-01 · 실사고: 자동 콘티가 '빈 배경 + 생물 접사'만 그려 아기자기한 맛이 사라짐)
_MINI_STYLE = ("a handcrafted TABLETOP miniature diorama shot like toy / scale-model photography: the whole world is a small "
               "hand-made set built on a wooden worktable or inside an open cardboard or wooden display box, lit by a warm desk "
               "lamp; strong tilt-shift with shallow depth of field and a slightly high camera looking down onto the set; every "
               "prop and the seabed are cute, chunky and visibly hand-made (felt, cotton-wool marine snow hanging on fine threads, "
               "crumpled blue cellophane water, painted cardboard backdrops with visible seams, paper-cut rocks and kelp, clay "
               "with fingerprints, bent wire, tiny LED fairy-light bulbs for any glow); muted warm palette")
_MINI_CREATURE = ("the creature is the ONLY precise object: an accurately sculpted, hand-painted collectible figurine with satin "
                  "paint and faint brush texture, with exactly the real anatomy, proportions and colours")
STYLE_REFS = ["../_shared/style/style_desk_chart.jpg", "../_shared/style/style_ocean_block.jpg"]   # 시범편 승인 콘티(생물 안 보이는 부분)
SB_WIDE_RATIO, SB_CLOSE_RATIO = 5 / 8, 2 / 8                 # 8컷 중 넓은 세트 샷 5컷 이상 · 접사 2컷 이하
# ★혼합 제작(운영자 선택 2026-10-05 · 편당 $7 → 약 $3): 움직임이 꼭 필요한 컷만 Omni 영상, 나머지는 콘티 이미지를
#   천천히 확대하는 무료 컷. 8컷 중 Omni 최대 4컷(후킹 컷은 반드시 Omni — 맨 앞 2초가 움직여야 한다).
SB_OMNI_RATIO = 4 / 8
_RUN_REQUEST = None                                          # 테스트용 대체(요청 파일 경로 → 반환코드)


def _run_request(rp: Path) -> int:
    if _RUN_REQUEST:
        return _RUN_REQUEST(rp)
    return subprocess.run([sys.executable, str(V2 / "tools" / "run_request.py"), str(rp)], cwd=str(ROOT)).returncode


_RID_LAST = [""]


def _rid(tag: str) -> str:
    """요청 id — 같은 초에 두 번 만들어도 겹치지 않게(실측: 연속 요청이 같은 id로 덮어씀)."""
    base = f"r{time.strftime('%m%d%H%M%S', time.gmtime())}"
    if base <= _RID_LAST[0]:
        base = _RID_LAST[0] + "x"
    _RID_LAST[0] = base
    return f"{base}_{tag}"


def _tile(files: list[Path], out: Path, cols: int, w: int = 360) -> Path | None:
    """여러 이미지를 한 장으로(운영자 검토용). 실패해도 제작을 막지 않는다."""
    try:
        from PIL import Image
        ims = [Image.open(f).convert("RGB") for f in files]
        ims = [im.resize((w, int(im.height * w / im.width))) for im in ims]
        h = max(im.height for im in ims)
        rows = (len(ims) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (w + 8) + 8, rows * (h + 8) + 8), "white")
        for i, im in enumerate(ims):
            sheet.paste(im, (8 + (i % cols) * (w + 8), 8 + (i // cols) * (h + 8)))
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out, quality=88)
        return out
    except Exception as e:                                   # noqa: BLE001
        print(f"[sheet] 실패: {e}")
        return None


def download_refs(pid: str, topic: dict, get=None, fetch=None) -> list[dict]:
    """참조 실사(자유 라이선스만): 주제 카드 사진 + iNaturalist 분류군 대표 사진 최대 4장 → out/<rid>/ref_NN.jpg."""
    import urllib.request
    rid = _rid("refs")
    out = PILOTS / pid / "out" / rid
    out.mkdir(parents=True, exist_ok=True)
    cands = []
    ph = topic.get("photo") or {}
    if ph.get("url"):
        cands.append(ph)
    try:
        import urllib.parse
        get = get or _get_json
        name = re.sub(r"\s+(sp|spp)\.?$", "", topic.get("sci", "").strip(), flags=re.I)
        d = get("https://api.inaturalist.org/v1/taxa?per_page=5&q=" + urllib.parse.quote(name))
        hit = next((t for t in d.get("results") or [] if (t.get("name") or "").lower() == name.lower()), None)
        if hit:
            full = (get("https://api.inaturalist.org/v1/taxa/%d" % hit["id"]).get("results") or [hit])[0]
            for tp in full.get("taxon_photos") or []:
                p = tp.get("photo") or {}
                if (p.get("license_code") or "").lower() in _FREE_LIC and p.get("medium_url"):
                    cands.append({"url": p["medium_url"], "credit": p.get("attribution") or "", "license": p["license_code"]})
    except Exception as e:                                   # noqa: BLE001
        print(f"[refs] iNaturalist 실패: {e}")
    refs, seen = [], set()
    for c in cands:
        if c["url"] in seen or len(refs) >= 4:
            continue
        seen.add(c["url"])
        try:
            fn = out / f"ref_{len(refs):02d}.jpg"
            if fetch:
                fetch(c["url"], fn)
            else:
                req = urllib.request.Request(c["url"], headers={"User-Agent": WIKI_UA})
                with urllib.request.urlopen(req, timeout=60) as r:
                    fn.write_bytes(r.read())
            refs.append({"file": f"out/{rid}/{fn.name}", "credit": c.get("credit", ""), "license": c.get("license", "")})
        except Exception as e:                               # noqa: BLE001
            print(f"[refs] 내려받기 실패 {c['url']}: {e}")
    _save(out / "refs.json", refs)
    return refs


_DESC_PROMPT = """You are a museum model maker's consultant. Look at the attached real photographs of the deep-sea animal
{sci} ({name_en}) and the verified facts below. Describe ONLY what the photographs and facts show (never invent features).
Return JSON only:
{{"anatomy":"precise English description, 60-110 words, for building an anatomically faithful miniature replica: overall body
shape and proportions, colour and surface texture, segments/armour, appendages (legs, arms, fins, tentacles — count if visible),
head, eyes (shape, position; say 'no eyes' if none), tail/rear, notable structures",
 "forbidden":"English, one line: features this animal must NOT have (e.g. 'no fish head, no bulging eyes, no extra legs')",
 "size_note":"English, one short line about real size from the facts, or empty",
 "checklist_ko":["해부학 확인 항목 5~8개 (한국어, 각 한 줄: 몸 비율·마디 수·다리 수·눈 모양/위치·꼬리 형태·색 등)"]}}
# Facts
{facts}
{extra}
"""

_SB_PROMPT = """You are the storyboard artist of a Japanese science YouTube Short made as {style}.
{creature}. Its anatomy is fixed: {anatomy}
Real size of the creature: {size_note}
Plan ONE storyboard panel (the first frame of the video clip) for EACH of the {n} cuts below. HARD RULES:
- WORLD: every panel is part of that hand-made tabletop world. In at least half of the panels the EDGE of the set is visible
  (table edge, box wall, backdrop seam, desk lamp, cutting mat, pencil or notebook next to the set).
- STORY PROPS: act out each cut's narration with tiny hand-made props and painted clay figurines (research ship on paper waves,
  toy submarine/ROV, clay scientists at a little desk, specimen jar, sketchbook, aquarium, sea chart, calendar ...). Each panel
  uses at least 2 hand-made props or set materials. Props are welcome — this is what makes the miniature charming.
- SCALE: clay figurines, boats and vehicles either appear in a panel WITHOUT the creature, or the creature is shown at its true
  size relative to them (never giant).
- SHOTS: at least {min_wide} WIDE set shots (the creature at most one third of the frame, the surrounding set clearly visible),
  at most {max_close} CLOSE shots (only when the narration names a body part); the rest MEDIUM. No two consecutive cuts on the same
  set; cross-section "box" sets at most 2.
- Show exactly what that cut's narration says; do not invent facts.
- NICKNAMES ARE NOT ANIMALS: many deep-sea creatures have figurative names ("sea pig" = a deep-sea SEA CUCUMBER, "headless
  chicken monster" = a swimming sea cucumber, "sea butterfly" = a tiny swimming sea snail, "sea toad" = an anglerfish). Always
  describe what the organism REALLY is with its true body (e.g. "a translucent pink deep-sea sea cucumber (Scotoplanes) with
  stubby tube-feet legs and two pairs of feeler-like papillae on its back"). NEVER write the nickname's land-animal word
  (pig, chicken, cow, dog ...) in a description and never draw a land animal.
- NEVER text, letters, numbers, labels, arrows, logos in the image. Painted clay figurines are fine; never real human hands or
  people. No other animals unless the narration says so. Keep the upper quarter of every panel calm and uncluttered (captions).
- The LAST cut's panel: the creature is already dim and receding into deep darkness (the video will fade to black).
- Cut {hook_cut} is used as the 2-second opening hook — make it the most striking, dynamic composition.
- OPENING (viewers decide in the first seconds whether to keep watching): cuts 1 and 2 show the creature ITSELF, large enough to
  read on a phone, caught in the middle of the strange action the narration describes — no clay scientists, ships, desks,
  calendars or empty sets in cut 1.
- MOTION (budget): cuts {required} MUST be "omni". Mark another cut "omni" ONLY if the narration needs real movement (swimming,
  eating, escaping, a fast reaction); mark it "still" when a calm, slowly pushed-in tableau tells it just as well (explanations,
  records, endings). "still" only from cut 3 on, and never 3 "still" cuts in a row. At most {max_omni} cuts may be "omni".
  Compose "still" panels so they read well without motion.
{feedback}
Return JSON only: {{"panels":{{"1":{{"shot":"wide|medium|close","motion":"omni|still","set_edge":true,"props":["prop 1","prop 2"],
"desc":"English description of panel 1: set, camera angle, creature pose and size in frame, props, light"}}, "2":{{...}}}}}}
# Cuts (Japanese narration / Korean / scene idea / seconds)
{cuts}
# Facts
{facts}
"""


# ★별명을 글자 그대로 그리는 사고 방지(실사고 2026-10-06: 왕게 편 5번 컷 — 사실은 「바다돼지라 불리는 해삼」인데
#   콘티 설명이 "clay sea pig"로 적혀 진짜 돼지 인형이 그려짐). 콘티 설명에 육상 동물 단어가 나오면 불통과 → 실제 생물로 다시 쓰게 한다.
_LAND_ANIMAL = re.compile(r"\b(pig|piglet|hog|boar|swine|chicken|hen|rooster|cow|bull|dog|puppy|cat|kitten|horse|elephant|mouse|"
                          r"rat|rabbit|sheep|goat|monkey|bear|lion|tiger|duck|frog)s?\b(?!-like|-ear|\s+like)", re.I)
# 한국어 장면 아이디어(scene_ko)에서 별명만 쓰는 것 — 「바다돼지(해삼)」처럼 실제 생물을 괄호로 함께 적어야 통과
_KO_NICK = re.compile(r"(돼지|닭|병아리|강아지|고양이|코끼리|토끼|생쥐|두꺼비)(?!\s*\()")


def literal_animal_problems(text: str, where: str) -> list[str]:
    """콘티 설명에 육상 동물 단어(별명을 글자 그대로 그릴 위험)가 있으면 이유 목록(영어 · AI에게 그대로 돌려줌)."""
    words = sorted({m.group(1).lower() for m in _LAND_ANIMAL.finditer(text or "")})
    if not words:
        return []
    return [f"{where}: the word(s) {', '.join(words)} name a land animal. If this comes from a nickname (e.g. 'sea pig' is a "
            f"deep-sea SEA CUCUMBER), describe the REAL organism by its true anatomy and never use that word — no land animals."]


# ★앞 15초는 움직이는 영상(운영자 선택 2026-10-09 · 실사고: 왕게 편 — 1·2번 컷이 무료 확대 컷(정지 그림)이고 1번 컷은
#   학자 인형이 나오는 역사 설명이라 앞 15초 움직임 1.4(대왕구족충 7.4) → 남은 사람도 앞 15초 동안 크게 빠짐).
#   1·2번 컷과 후킹 컷은 영상 AI 필수 · 무료 확대 컷은 3번부터 · 3컷 연속 금지 · 영상 AI 최대 4컷(비용 그대로).
#   (2컷 연속까지는 허용: 4컷 예산으로 「연속 0」은 8컷에서 불가능 — 5컷이 필요해 편당 약 $0.7 증가.)
OPENING_OMNI_CUTS = (1, 2)
_OPENING_PEOPLE = re.compile(r"\b(scientists?|researchers?|scholars?|professors?|explorers?|ships?|boats?|calendars?)\b", re.I)


def omni_required(n: int, hook_cut: int | None) -> list[int]:
    return sorted({c for c in OPENING_OMNI_CUTS if c <= n} | ({int(hook_cut)} if hook_cut else set()))


def omni_budget(n: int, hook_cut: int | None) -> int:
    return max(len(omni_required(n, hook_cut)), int(n * SB_OMNI_RATIO))


def validate_storyboard_plan(panels: dict, cuts: list[dict], hook_cut: int | None = None) -> list[str]:
    """콘티 계획 코드 검사(운영자 승인 2026-10-01 미니어처 규칙) — 불통과 이유(영어 · AI에게 그대로 돌려줌)."""
    import math
    n = len(cuts)
    probs = []
    for c in cuts:
        p = panels.get(c["cut"])
        if not isinstance(p, dict) or len(str(p.get("desc", ""))) < 40:
            probs.append(f"Cut {c['cut']}: missing or too short panel description.")
            continue
        if p.get("shot") not in ("wide", "medium", "close"):
            probs.append(f"Cut {c['cut']}: shot must be wide, medium or close.")
        if len([x for x in p.get("props") or [] if str(x).strip()]) < 2:
            probs.append(f"Cut {c['cut']}: list at least 2 hand-made props or set materials.")
        probs += literal_animal_problems(str(p.get("desc", "")) + " " + " ".join(map(str, p.get("props") or [])), f"Cut {c['cut']}")
    shots = [(panels.get(c["cut"]) or {}).get("shot") for c in cuts]
    min_wide, max_close = math.ceil(n * SB_WIDE_RATIO), max(1, round(n * SB_CLOSE_RATIO))
    if shots.count("wide") < min_wide:
        probs.append(f"Only {shots.count('wide')} WIDE set shots — make at least {min_wide} of the {n} panels wide tabletop shots.")
    if shots.count("close") > max_close:
        probs.append(f"{shots.count('close')} CLOSE shots — at most {max_close}; turn the others into wide or medium set shots.")
    motions = [(panels.get(c["cut"]) or {}).get("motion") for c in cuts]
    if any(m not in ("omni", "still") for m in motions):
        probs.append("Every panel needs motion = omni or still.")
    max_omni = omni_budget(n, hook_cut)
    if motions.count("omni") > max_omni:
        probs.append(f"{motions.count('omni')} cuts are omni — at most {max_omni}; make calmer cuts still.")
    if hook_cut and (panels.get(hook_cut) or {}).get("motion") != "omni":
        probs.append(f"Cut {hook_cut} is the opening hook and must be omni.")
    for c in OPENING_OMNI_CUTS:
        if c <= n and c != hook_cut and (panels.get(c) or {}).get("motion") != "omni":
            probs.append(f"Cut {c} plays in the first 15 seconds and must be omni (the creature moving).")
    run = 0
    for c, m in zip(cuts, motions):
        run = run + 1 if m == "still" else 0
        if run == 3:
            probs.append(f"Cuts {c['cut'] - 2}-{c['cut']} are 3 still cuts in a row — make one of them omni (and another cut still).")
    p1 = panels.get(1) or {}
    m1 = _OPENING_PEOPLE.findall(str(p1.get("desc", "")) + " " + " ".join(map(str, p1.get("props") or [])))
    if m1:
        probs.append(f"Cut 1 opens the video: show the creature itself in action, not {', '.join(sorted({w.lower() for w in m1}))}.")
    edges = sum(1 for c in cuts if (panels.get(c["cut"]) or {}).get("set_edge") is True)
    if edges < math.ceil(n / 2):
        probs.append(f"The set edge is visible in only {edges} panels — show it in at least {math.ceil(n / 2)}.")
    return probs


def plan_storyboard(sc: dict, cc: dict, feedback: str = "", ask=None) -> dict:
    """AI 콘티 계획 → 코드 검사 → 불통과면 이유를 돌려주고 최대 3번 다시. 반환 {컷: {shot,set_edge,props,desc}}."""
    import math
    cuts = [c for c in sc["cuts"] if "tts" in c]
    ftxt = "\n".join(f"{f['id']}: {f['fact']}" for f in sc.get("facts", []))
    hook_cut = int((sc.get("hook") or {}).get("cut") or 1)
    ctxt = "\n".join(f"Cut {c['cut']} ({c.get('sec', '')}s): JP「{c['jp']}」 / KO「{c.get('ko', '')}」 / scene: {c.get('scene_ko', '')}" for c in cuts)
    base_fb = f"# Operator's revision request (must apply)\n{feedback}\n" if feedback else ""
    fb, panels, probs = base_fb, {}, []
    ask = ask or (lambda p: _gemini_text(p, temperature=0.5))
    for _ in range(3):
        plan = _json_obj(ask(_SB_PROMPT.format(style=_MINI_STYLE, creature=_MINI_CREATURE, anatomy=cc.get("anatomy", ""),
                                               size_note=cc.get("size_note") or "see the facts", n=len(cuts),
                                               min_wide=math.ceil(len(cuts) * SB_WIDE_RATIO), max_close=max(1, round(len(cuts) * SB_CLOSE_RATIO)),
                                               max_omni=omni_budget(len(cuts), hook_cut),
                                               required=", ".join(map(str, omni_required(len(cuts), hook_cut))),
                                               hook_cut=hook_cut, feedback=fb, cuts=ctxt, facts=ftxt)))
        panels = {}
        for k, v in (plan.get("panels") or {}).items():
            if str(k).isdigit():
                panels[int(k)] = v if isinstance(v, dict) else {"desc": str(v)}
        probs = validate_storyboard_plan(panels, cuts, hook_cut)
        if not probs:
            return panels
        fb = base_fb + "# Problems in your previous plan (fix all)\n" + "\n".join("- " + p for p in probs) + "\n"
    raise RuntimeError("콘티 계획이 미니어처 규칙 검사를 3번 모두 통과하지 못했습니다: " + " / ".join(probs[:3]))


def _grid_items(cuts: list[dict], panels: dict, cc: dict) -> list[dict]:
    """2×2 격자 요청 항목(4컷씩). 참고 이미지 = 생물 카드·실사(앞) + 시범편 화풍 참고(뒤 · 있는 것만)."""
    refs = [r["file"] for r in cc.get("use_as_reference", [])][:3]
    style = [r for r in STYLE_REFS if (PILOTS / "_shared" / "style" / Path(r).name).exists()]
    head = _GRID_HEAD_GENERIC.format(style=_MINI_STYLE, creature=_MINI_CREATURE, anatomy=cc.get("anatomy", ""),
                                     forbidden=cc.get("forbidden", ""), ns=len(style))
    items = []
    for g in range(0, len(cuts), 4):
        grp = cuts[g:g + 4]
        names = [f"p{c['cut']:02d}" for c in grp] + [""] * (4 - len(grp))
        body = "\n".join(f"Panel {i + 1} ({pos}, {panels[c['cut']].get('shot', 'wide')} shot): {panels[c['cut']]['desc']} "
                         f"Hand-made props: {', '.join(map(str, panels[c['cut']].get('props') or []))}."
                         for i, (c, pos) in enumerate(zip(grp, ("top-left", "top-right", "bottom-left", "bottom-right"))))
        items.append({"name": f"grid{g // 4 + 1}", "aspect": "9:16", "size": "2K", "refs": refs + style, "prompt": head + body,
                      "split": {"rows": 2, "cols": 2, "names": names}})
    return items


def storyboard_trial(pid: str, cut_ids=(1, 2, 3, 4), out: Path | None = None, ask=None, gen=None) -> dict:
    """미니어처 규칙 시험(운영자 승인 2026-10-01): 상태는 바꾸지 않고, 새 규칙으로 콘티를 계획해 격자 1장(4칸)만 그린 뒤
    지금 콘티와 나란히 비교 이미지를 만든다. gen: 테스트용 이미지 생성 대체(req, pilot, out) → 결과 dict."""
    pilot = PILOTS / pid
    sc, cc = _load(_script_path(pid)), _load(pilot / "creature_card.json") or {}
    st = load_status(pid)
    out = Path(out or pilot / "out" / _rid("sb_trial"))
    out.mkdir(parents=True, exist_ok=True)
    panels = plan_storyboard(sc, cc, ask=ask)
    _save(out / "plan.json", {str(k): v for k, v in panels.items()})
    cuts = [c for c in sc["cuts"] if "tts" in c and c["cut"] in cut_ids][:4]
    item = _grid_items(cuts, panels, cc)[0]
    if gen is None:
        sys.path.insert(0, str(V2 / "tools"))
        import run_request as RR                                 # noqa: E402
        gen = RR.gen_images
    res = gen({"items": [item], "model_preference": ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"]}, pilot, out)
    new = [out / f"p{c['cut']:02d}.jpg" for c in cuts]
    old = {p["cut"]: pilot / p["file"] for p in (st.get("artifacts", {}).get("storyboard") or {}).get("panels", [])}
    if all(f.exists() for f in new):
        _tile([old[c["cut"]] for c in cuts if c["cut"] in old] + new, out / "compare_old_new.jpg", cols=len(cuts))
    return {"ok": bool(res.get("ok")) and all(f.exists() for f in new), "panels": {str(k): v for k, v in panels.items()},
            "image": res, "compare": "compare_old_new.jpg"}


_VID_PROMPT = """You write per-second TIMELINE video prompts (English) for Gemini Omni Flash, one per cut, for a Japanese science
YouTube Short in a handcrafted MINIATURE DIORAMA style ({style}). The attached storyboard panel is each cut's FIRST FRAME.
The creature's anatomy is fixed and must never change: {anatomy}
HARD RULES for every cut:
- One continuous shot, exactly the cut's duration. Split it into 2-4 time ranges "0.0–2.0s ..." and for EACH range state
  camera position/move, what the creature does, what is and is not visible. Put visual changes at the narration boundaries given.
- Motion must be concrete (what moves from where to where). Slow, observational camera; no fast pans, no morphing.
- Keep the hand-made tabletop set visible and the camera at miniature scale (slightly high angle, tilt-shift); never push into a
  realistic macro of the creature. Set pieces may move gently (paper waves rock, cotton marine snow drifts, fairy lights twinkle).
- Never invent facts beyond the narration. No text, letters, numbers, symbols, logos. No real human hands or people.
- OPENING (viewers swipe away in the first seconds): in cuts 1 and 2 the creature itself moves clearly from the very first
  second (swims, crawls, turns, reaches, feeds) — no static establishing shot, no slow look at an empty set first.
- Cut {hook_cut} also supplies the 2-second opening hook: it must contain ONE clear, quick, visible creature action that lasts at
  least 2 seconds (a burst of swimming, a lunge, a grab, a flip, a sudden turn — only actions the narration and facts support).
- Cut {last}: the creature drifts away into deep darkness and the frame goes almost black by the end (episode ending).
{feedback}
Return JSON only: {{"prompts":{{"1":"TIMELINE text for cut 1","2":"..."}}}}
# Cuts (seconds / narration JP / KO / narration chunk timings / panel description)
{cuts}
"""

_CARD_PROMPT_HEAD = ("A single accurately sculpted, hand-painted collectible miniature figurine of {sci}, photographed as a macro "
                     "studio shot. Shape, proportions and colour pattern must be anatomically faithful to the attached real reference "
                     "photos: {anatomy} Satin hand-painted finish with faint brush texture — clearly a crafted figure, not a slick "
                     "living animal (운영자 승인 2026-10-01). Shallow depth of field (tilt-shift macro), warm desk-lamp light, plain "
                     "neutral mid-grey seamless backdrop. Exactly one animal, fully inside the frame. "
                     "No text, no letters, no labels, no watermark, no logo, no scale bar, no collage, no multiple panels, "
                     "no split screen, no extra animals, no humans. {forbidden} View: {view}.")

_CHECK_PROMPT = """Compare the attached images: the FIRST {nc} are handcrafted replica renders of {sci}; the rest are REAL photographs.
For each checklist item decide whether the replica matches the real animal. Be strict but judge only what is visible;
if the real photos do not show that part, mark "unknown". Return JSON only:
{{"items":[{{"item":"checklist text","verdict":"pass|fail|unknown","note_ko":"한국어 한 줄"}}]}}
# Checklist
{checklist}
"""


def _ask_vision(prompt: str, images: list[Path], ask=None) -> str:
    if ask:
        return ask(prompt, images) if _accepts_images(ask) else ask(prompt)
    return _gemini_text(prompt, images=images)


def _accepts_images(fn) -> bool:
    import inspect
    try:
        return len(inspect.signature(fn).parameters) >= 2
    except (TypeError, ValueError):
        return False


def write_storyboard(pid: str, feedback: str = "", ask=None, get=None, fetch=None) -> dict:
    """③ 스토리보드 자동: 참조 실사 → 생물 카드(2장) → 실사 대조(비전 체크리스트) → 8컷 콘티(2×2 격자 2장) → 승인 대기."""
    st = load_status(pid)
    topic = st.get("topic") or {}
    sc = _load(_script_path(pid))
    if not sc or not sc.get("cuts"):
        raise SystemExit("대본이 없습니다 — 대본 단계를 먼저 끝내세요")
    pilot = PILOTS / pid
    set_job(pid, "storyboard", "running", "스토리보드 자동 작성 중 — 참조 실사 → 생물 카드 → 실사 대조 → 8컷 콘티", "write_storyboard")
    try:
        cuts = [c for c in sc["cuts"] if "tts" in c]
        ftxt = "\n".join(f"{f['id']}: {f['fact']}" for f in sc.get("facts", []))
        cc = _load(pilot / "creature_card.json") or {}
        redo_card = not cc.get("anatomy") or not feedback or "카드" in feedback
        if redo_card:
            refs = download_refs(pid, topic, get=get, fetch=fetch)
            if not refs:
                raise RuntimeError("참조 실사를 한 장도 받지 못했습니다(자유 라이선스 사진 없음) — 이 종은 생물 카드를 만들 수 없습니다")
            sp = _species_data(topic)
            extra = ""
            if sp.get("appearance"):
                extra = "# Curated notes (trusted)\n" + sp["appearance"] + "\n" + (sp.get("anatomy_lock") or "") + "\nForbidden: " + (sp.get("forbidden_features") or "")
            desc = _json_obj(_ask_vision(_DESC_PROMPT.format(sci=topic.get("sci", ""), name_en=topic.get("name_en", ""), facts=ftxt, extra=extra),
                                         [pilot / r["file"] for r in refs], ask))
            anatomy, forbidden = str(desc.get("anatomy", "")).strip(), str(desc.get("forbidden", "")).strip()
            checklist = [str(x) for x in desc.get("checklist_ko") or []][:8]
            if len(anatomy) < 40:
                raise RuntimeError("생물 형태 설명을 만들지 못했습니다")
            rid = _rid("card")
            items = [{"name": n, "aspect": "1:1", "refs": [r["file"] for r in refs][:3],
                      "prompt": _CARD_PROMPT_HEAD.format(sci=topic.get("sci", ""), anatomy=anatomy, forbidden=forbidden, view=v)}
                     for n, v in (("card_side", "three-quarter side view of the whole body"), ("card_top", "straight top-down view of the whole body"))]
            rp = pilot / "requests" / f"{rid}.json"
            _save(rp, {"id": rid, "kind": "gen_images", "purpose": "생물 카드(자동) — 이후 콘티·영상의 형태 기준",
                       "model_preference": ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"], "items": items})
            if _run_request(rp) != 0:
                raise RuntimeError(f"생물 카드 이미지 생성 실패(요청 {rid})")
            res = _load(pilot / "out" / rid / "result.json") or {}
            cards = [f"out/{rid}/{it['file']}" for it in res.get("items", []) if it.get("file")]
            if not cards:
                raise RuntimeError("생물 카드 이미지가 비어 있습니다")
            # 실사 대조(비전 체크리스트) — 판정은 기록만(운영자가 승인/수정 요청으로 결정)
            check = {"items": [], "error": ""}
            try:
                chk = _json_obj(_ask_vision(_CHECK_PROMPT.format(nc=len(cards), sci=topic.get("sci", ""), checklist="\n".join("- " + x for x in checklist)),
                                            [pilot / c for c in cards] + [pilot / r["file"] for r in refs], ask))
                check["items"] = [{"item": str(i.get("item", "")), "verdict": str(i.get("verdict", "unknown")), "note_ko": str(i.get("note_ko", ""))}
                                  for i in chk.get("items") or []]
            except Exception as e:                           # noqa: BLE001
                check["error"] = f"실사 대조 검사 실패: {str(e)[:120]}"
            compare = _tile([pilot / c for c in cards] + [pilot / r["file"] for r in refs][:2], pilot / "out" / rid / "compare.jpg", cols=2)
            cc = {"status": "자동 생성(운영자 승인 대기)", "at": _now(), "anatomy": anatomy, "forbidden": forbidden,
                  "size_note": str(desc.get("size_note", "")).strip(),
                  "checklist": checklist, "check": check, "refs": refs,
                  "use_as_reference": [{"file": c, "role": "생물 카드(자동)"} for c in cards] + [{"file": refs[0]["file"], "role": "실사 기준"}],
                  "compare": f"out/{rid}/compare.jpg" if compare else None}
            _save(pilot / "creature_card.json", cc)
            st = load_status(pid)
            st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": "생물 카드 2장", "usd": round(IMG_USD * 2, 3)})
            _save(status_path(pid), st)
        # 8컷 콘티 계획(AI · 미니어처 규칙 코드 검사) → 2×2 격자 2장(시범편 화풍 참고 포함)
        panels = plan_storyboard(sc, cc, feedback, ask=ask)
        rid = _rid("sb")
        items = _grid_items(cuts, panels, cc)
        rp = pilot / "requests" / f"{rid}.json"
        _save(rp, {"id": rid, "kind": "gen_images", "purpose": "8컷 콘티(자동) — 컷별 시작 이미지 · 2×2 격자",
                   "model_preference": ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"], "items": items})
        if _run_request(rp) != 0:
            raise RuntimeError(f"콘티 이미지 생성 실패(요청 {rid})")
        pfiles = []
        for c in cuts:
            f = pilot / "out" / rid / f"p{c['cut']:02d}.jpg"
            if not f.exists():
                raise RuntimeError(f"{c['cut']}번 컷 콘티 칸이 없습니다(격자 분할 실패)")
            pfiles.append(f)
            c["keyframe"] = f"out/{rid}/{f.name}"
            c["panel_desc"] = panels[c["cut"]]["desc"]
            c["panel_shot"] = panels[c["cut"]].get("shot", "")
            c["motion"] = panels[c["cut"]].get("motion", "omni")
        sheet = _tile(pfiles, pilot / "out" / rid / "storyboard.jpg", cols=4)
        sc.setdefault("storyboard_history", []).append({"at": _now(), "rid": rid, "feedback": feedback})
        _save(_script_path(pid), sc)
        st = load_status(pid)
        st["artifacts"]["storyboard"] = {"sheet": f"out/{rid}/storyboard.jpg" if sheet else None, "request": rid,
                                         "card": [r["file"] for r in cc.get("use_as_reference", [])],
                                         "compare": cc.get("compare"), "card_check": cc.get("check"), "checklist": cc.get("checklist"),
                                         "panels": [{"cut": c["cut"], "file": c["keyframe"], "desc": c["panel_desc"],
                                                     "shot": c.get("panel_shot", ""), "motion": c.get("motion", "omni")} for c in cuts]}
        tmv = {t["cut"]: t for t in sc.get("timing_v5") or []}
        st.setdefault("cost", {}).setdefault("estimate", {})["video"] = round(sum(
            float((tmv.get(c["cut"]) or {}).get("sec") or c.get("sec") or 6) for c in cuts if c.get("motion", "omni") == "omni") * OMNI_USD_PER_SEC, 2)
        st["cost"].setdefault("spent", []).append({"at": _now(), "what": "콘티 격자 2장", "usd": round(IMG_USD * len(items), 3)})
        st["stages"]["storyboard"]["state"] = "review"
        _note(st, "storyboard", "auto", "스토리보드 자동 작성 완료 — 승인 대기" + (" (수정 요청 반영)" if feedback else ""))
        _save(status_path(pid), st)
        return set_job(pid, "storyboard", "done", "스토리보드 자동 작성 완료 — 승인 대기", "write_storyboard")
    except Exception as e:                                   # noqa: BLE001
        set_job(pid, "storyboard", "failed", f"스토리보드 자동 작성 실패: {str(e)[:220]} — 「다시 시도」를 눌러 주세요", "write_storyboard")
        raise SystemExit(f"스토리보드 자동 작성 실패: {e}")


_GRID_HEAD_GENERIC = ("Create ONE image that is a clean 2x2 grid of FOUR separate, equal-sized vertical 9:16 photographs separated by thin "
                      "plain white gutters, read left-to-right, top-to-bottom. Each panel is a DIFFERENT scene and camera angle as described "
                      "below. Shared look for all panels: {style}. {creature}. It must match the attached replica (creature card) and "
                      "real reference photo exactly and be identical in every panel: {anatomy} {forbidden} "
                      "STYLE REFERENCES: the LAST {ns} attached images come from another episode of the same series — copy ONLY their "
                      "hand-made tabletop-diorama look (set building, materials, desk-lamp light, tilt-shift, camera height); never copy "
                      "their animal, map or objects literally. Clay figurines, boats and vehicles never make the creature look giant. "
                      "Keep the upper quarter of every panel calm and uncluttered. NEVER draw text, letters, numbers, labels, arrows, "
                      "logos, watermarks. Painted clay figurines are allowed; never real human hands or people. Every animal is drawn as "
                      "what it REALLY is — a nickname like 'sea pig' (a sea cucumber) never means a pig; never draw land animals.\n")


_PANEL_FIX_PROMPT = """You are the storyboard artist of a Japanese science YouTube Short made as {style}.
{creature}. Its anatomy is fixed: {anatomy}
Redraw the plan of ONE panel (cut {cut}) only. The operator found this problem and it MUST be fixed: {memo}
Narration (JP): {jp}
Korean: {ko}
Facts: {facts}
Previous panel description (wrong): {old}
Keep the same rules: hand-made tabletop miniature world, at least 2 hand-made props or set materials, no text/letters/numbers,
no real human hands or people, keep the upper quarter calm. NICKNAMES ARE NOT ANIMALS: describe every organism as what it
REALLY is with its true body ("sea pig" = a deep-sea SEA CUCUMBER) and never use a land-animal word or draw a land animal.
Cut 1 opens the video: there, show the creature itself in action — never clay scientists, ships or calendars.
{feedback}
Return JSON only: {{"shot":"wide|medium|close","props":["prop 1","prop 2"],"desc":"English description: set, camera angle, organisms with their true anatomy, props, light"}}
"""


def redo_panel(pid: str, cut: int, memo: str = "", ask=None, run=None) -> dict:
    """콘티 한 칸만 다시 그린다(운영자 지시 2026-10-06: 별명 '바다돼지'를 진짜 돼지로 그린 사고).
    AI가 그 칸 설명만 고쳐 쓰고(별명·육상 동물 코드 검사) → 9:16 이미지 1장(약 $0.134) → 무료 줌인 컷이면 바로 다시
    확대 영상을 만들어 재조립(추가 비용 0). 영상 AI 컷이면 그림만 바꾸고 「이 컷만 다시 만들기」를 눌러야 영상에 반영된다."""
    st = load_status(pid)
    sc = _load(_script_path(pid))
    pilot = PILOTS / pid
    c = next((x for x in sc.get("cuts", []) if int(x.get("cut", 0)) == int(cut)), None)
    if not c:
        raise SystemExit(f"{cut}번 컷이 없습니다")
    cc = _load(pilot / "creature_card.json") or {}
    ftxt = "\n".join(f"{f['id']}: {f['fact']}" for f in sc.get("facts", []))
    ask = ask or (lambda p: _gemini_text(p, temperature=0.4))
    set_job(pid, "storyboard", "running", f"{cut}번 콘티 칸 다시 그리는 중", "redo_panel")
    try:
        fb, plan, probs = "", {}, []
        for _ in range(3):
            plan = _json_obj(ask(_PANEL_FIX_PROMPT.format(style=_MINI_STYLE, creature=_MINI_CREATURE, anatomy=cc.get("anatomy", ""),
                                                          cut=cut, memo=memo or "the panel does not show what the narration says",
                                                          jp=c.get("jp", ""), ko=c.get("ko", ""), facts=ftxt,
                                                          old=c.get("panel_desc", ""), feedback=fb)))
            probs = validate_storyboard_plan({int(cut): plan}, [c])
            # 한 칸만 보므로 비율(넓은 샷 수 등)·영상 AI/무료 컷 배분 검사는 제외(그림만 다시 그리고 움직임 방식은 그대로)
            probs = [x for x in probs if x.startswith(f"Cut {cut}") and "must be omni" not in x]
            if not probs:
                break
            fb = "# Problems in your previous answer (fix all)\n" + "\n".join("- " + x for x in probs)
        if probs:
            raise RuntimeError("콘티 칸 설명이 검사를 3번 모두 통과하지 못했습니다: " + " / ".join(probs[:2]))
        refs = [r["file"] for r in cc.get("use_as_reference", [])][:3]
        style = [r for r in STYLE_REFS if (PILOTS / "_shared" / "style" / Path(r).name).exists()]
        head = _GRID_HEAD_GENERIC.format(style=_MINI_STYLE, creature=_MINI_CREATURE, anatomy=cc.get("anatomy", ""),
                                         forbidden=cc.get("forbidden", ""), ns=len(style))
        head = ("Create ONE single vertical 9:16 photograph — one scene, NOT a grid or collage. "
                + head[head.index("Shared look"):].replace("all panels", "the photo").replace("every panel", "the photo"))
        name = f"p{int(cut):02d}"
        rid = _rid("panel")
        rp = pilot / "requests" / f"{rid}.json"
        _save(rp, {"id": rid, "kind": "gen_images", "purpose": f"콘티 {cut}번 칸만 다시 그리기 — {memo}",
                   "model_preference": ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"],
                   "items": [{"name": name, "aspect": "9:16", "refs": refs + style,
                              "prompt": head + f"Scene ({plan.get('shot', 'wide')} shot): {plan['desc']} "
                                               f"Hand-made props: {', '.join(map(str, plan.get('props') or []))}."}]})
        if (run or _run_request)(rp) != 0:
            raise RuntimeError(f"콘티 칸 이미지 생성 실패(요청 {rid})")
        img = next((f for f in (pilot / "out" / rid).glob(f"{name}.*")), None)
        if not img:
            raise RuntimeError(f"콘티 칸 이미지가 없습니다(요청 {rid})")
        c.setdefault("keyframe_history", []).append(c.get("keyframe"))
        c["keyframe"], c["panel_desc"], c["panel_shot"] = str(img.relative_to(pilot)), plan["desc"], plan.get("shot", "")
        _save(_script_path(pid), sc)
        st = load_status(pid)
        for pnl in (st["artifacts"].get("storyboard") or {}).get("panels", []):
            if int(pnl["cut"]) == int(cut):
                pnl.update(file=c["keyframe"], desc=plan["desc"], shot=plan.get("shot", ""))
        st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": f"콘티 {cut}번 칸 다시 그리기", "usd": IMG_USD})
        _note(st, "storyboard", "redo_panel", f"{cut}번 칸만 다시 그림. {memo}".strip())
        clip = next((x for x in (st["artifacts"].get("video") or {}).get("clips", []) if int(x["cut"]) == int(cut)), None)
        msg = f"{cut}번 콘티 칸 다시 그림"
        if clip and (clip.get("motion") == "still" or "_stills/" in clip["file"]):
            tmv = {t["cut"]: t for t in sc.get("timing_v5") or []}
            sec = float((tmv.get(int(cut)) or {}).get("sec") or clip.get("sec") or 6)
            dst = pilot / "out" / f"{rid}_stills" / f"c{int(cut):02d}.mp4"
            still_clip(img, sec, dst)
            clip.setdefault("history", []).append(clip["file"])
            clip["file"] = str(dst.relative_to(pilot))
            _save(status_path(pid), st)
            set_job(pid, "storyboard", "done", msg + " — 무료 줌인 컷이라 바로 재조립", "redo_panel")
            return assemble(pid)
        if clip:
            msg += " — 영상 AI 컷이라 「이 컷만 다시 만들기」를 눌러야 영상에 반영됩니다"
            _note(st, "video", "auto", msg)
        _save(status_path(pid), st)
        return set_job(pid, "storyboard", "done", msg, "redo_panel")
    except Exception as e:                                   # noqa: BLE001
        set_job(pid, "storyboard", "failed", f"{cut}번 콘티 칸 다시 그리기 실패: {str(e)[:200]}", "redo_panel")
        raise SystemExit(f"콘티 칸 다시 그리기 실패: {e}")


def _ensure_tts(pid: str, sc: dict) -> str:
    """영상 조립에 쓸 나레이션(전체 한 번에 합성) — 대본 단계에서 만든 것이 있으면 그대로, 없으면 지금 합성."""
    st = load_status(pid)
    tid = (st.get("artifacts", {}).get("script") or {}).get("tts_id")
    pilot = PILOTS / pid
    if tid and (pilot / "out" / tid / "body_timepoints.json").exists():
        return tid
    cuts = [c for c in sc["cuts"] if "tts" in c]
    rid = _rid("tts")
    rp = pilot / "requests" / f"{rid}.json"
    _save(rp, {"id": rid, "kind": "gen_tts", "purpose": "본편 나레이션 — 대본 전체 한 번에 합성(자동)",
               "cut_map": [{"cut": c["cut"], "n": len(_chunks(c["jp"]))} for c in cuts],
               "items": [{"name": "body", "jp": "".join(c["jp"] for c in cuts), "segments": [s for c in cuts for s in _chunks(c["tts"])]}]})
    tpf = pilot / "out" / rid / "body_timepoints.json"
    if _run_request(rp) != 0 or not tpf.exists():
        raise RuntimeError(f"나레이션 합성 실패(요청 {rid})")
    timing, probs = first_timing(cuts, _load(tpf))
    if probs:
        raise RuntimeError("나레이션이 컷에 안 들어갑니다: " + " / ".join(probs))
    sc["timing_v5"] = timing
    for c, t in zip(cuts, timing):
        c["sec"], c["speech_s"] = t["sec"], t["speech_s"]
    sc["total_sec"] = sum(t["sec"] for t in timing) + HOOK_S + ANSWER_S
    _save(_script_path(pid), sc)
    st = load_status(pid)
    st["artifacts"].setdefault("script", {}).update(tts_id=rid, audio=f"out/{rid}/body.wav")
    _sync_script_artifacts(st, sc)
    _save(status_path(pid), st)
    return rid


def ensure_hook_voice(pid: str, sc: dict | None = None) -> str | None:
    """후킹 한 줄 목소리(0초부터 읽기 · 운영자 선택 2026-10-09). 지금 문장으로 만든 파일이 있으면 그대로, 없으면 나레이션과
    같은 목소리로 합성(약 $0.001). 반환: 편 폴더 기준 wav 경로 · 실패하면 None(조립은 계속하고 자동 검사에 「불통과」로 남긴다)."""
    sc = sc or _load(_script_path(pid)) or {}
    hk = sc.get("hook") or {}
    voice = str(hk.get("voice_jp") or "").strip()
    if not voice:
        return None
    pilot = PILOTS / pid
    if hk.get("voice_file") and hk.get("voice_for") == voice and (pilot / hk["voice_file"]).exists():
        return hk["voice_file"]
    rel = _tts_line(pid, voice, "hook_tts")
    if not rel:
        return None
    hk["voice_file"], hk["voice_for"] = rel, voice
    sc["hook"] = hk
    _save(_script_path(pid), sc)
    return rel


def _tts_line(pid: str, text: str, tag: str) -> str | None:
    """한 줄을 나레이션 목소리로 합성 → 편 폴더 기준 wav 경로(실패하면 None · 예외 없음)."""
    pilot = PILOTS / pid
    rid = _rid(tag)
    rp = pilot / "requests" / f"{rid}.json"
    _save(rp, {"id": rid, "kind": "gen_tts", "purpose": "후킹 한 줄 목소리(0초부터 읽기)",
               "items": [{"name": "hook", "jp": text, "tts": auto_reading(text)}]})
    try:
        code = _run_request(rp)
    except Exception:                                        # noqa: BLE001 — 목소리가 없어도 조립은 계속
        code = 1
    res = _load(pilot / "out" / rid / "result.json") or {}
    f = next((it.get("file") for it in res.get("items", []) if it.get("file")), None)
    if code != 0 or not f or not (pilot / "out" / rid / f).exists():
        return None
    return f"out/{rid}/{f}"


def still_clip(img: Path, sec: float, dst: Path, fade_out: bool = False) -> Path:
    """무료 컷(혼합 제작): 콘티 이미지를 sec초 동안 천천히 확대(1.00→1.08) — 720×1280·24fps·무음."""
    W, H, FPS = 720, 1280, 24
    n = int(round(sec * FPS))
    dst.parent.mkdir(parents=True, exist_ok=True)
    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
          f"zoompan=z='min(zoom+{0.08 / max(n, 1):.6f},1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS},setsar=1"
          + (f",fade=t=out:st={max(0.0, sec - 1.0):.2f}:d=1.0" if fade_out else ""))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(img), "-vf", vf, "-frames:v", str(n),
                    "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(dst)], check=True)
    return dst


def make_video(pid: str, feedback: str = "", ask=None) -> dict:
    """④ 영상 자동: 컷별 초 단위 Omni 지시문(AI) → Omni Flash 생성(메모에 'N번' 컷이 있으면 그 컷만) → 조립 → 자동 검사 → 승인 대기."""
    st = load_status(pid)
    sc = _load(_script_path(pid))
    pilot = PILOTS / pid
    cuts = [c for c in (sc or {}).get("cuts", []) if "tts" in c]
    if not cuts or any(not c.get("keyframe") for c in cuts):
        raise SystemExit("콘티(컷별 시작 이미지)가 없습니다 — 스토리보드 단계를 먼저 끝내세요")
    only = sorted({int(x) for x in re.findall(r"(\d+)\s*번", feedback or "")} & {c["cut"] for c in cuts}) if feedback else []
    set_job(pid, "video", "running", ("수정 컷 다시 만드는 중: " + ",".join(map(str, only)) + "번" if only else "영상 자동 제작 중 — 컷별 지시문 → Omni Flash 8컷 → 조립 → 자동 검사"), "make_video")
    try:
        tts_id = _ensure_tts(pid, sc)
        sc = _load(_script_path(pid))
        cuts = [c for c in sc["cuts"] if "tts" in c]
        tm = {t["cut"]: t for t in sc["timing_v5"]}
        cc = _load(pilot / "creature_card.json") or {}
        anatomy = cc.get("anatomy") or ""
        old = (st["artifacts"].get("video") or {})
        prev_clips = {int(c["cut"]): c["file"] for c in old.get("clips", []) if (pilot / c["file"]).exists()}
        targets = [c for c in cuts if (not only and c["cut"] not in prev_clips) or (only and c["cut"] in only)] if (only or prev_clips) else cuts
        if not targets and not prev_clips:
            targets = cuts
        # ★혼합 제작: 'still' 컷은 콘티 이미지를 천천히 확대하는 무료 컷으로 여기서 바로 만든다(유료 생성 대상에서 제외)
        stills = [c for c in targets if c.get("motion") == "still"]
        if stills:
            sid = _rid("stills")
            for c in stills:
                dst = pilot / "out" / sid / f"c{c['cut']:02d}.mp4"
                still_clip(pilot / c["keyframe"], float(tm[c["cut"]]["sec"]), dst, fade_out=(c["cut"] == cuts[-1]["cut"]))
                prev_clips[c["cut"]] = f"out/{sid}/{dst.name}"
            targets = [c for c in targets if c.get("motion") != "still"]
            st = load_status(pid)
            st["artifacts"]["video"] = {**old, "clips_request": old.get("clips_request") or sid,
                                        "clips": [{"cut": c["cut"], "file": prev_clips[c["cut"]], "sec": tm[c["cut"]]["sec"],
                                                   "motion": c.get("motion", "omni")} for c in cuts if c["cut"] in prev_clips]}
            _save(status_path(pid), st)
            old = st["artifacts"]["video"]
        if targets:
            def chunks_txt(c):
                segs = _chunks(c["jp"])
                tps = tm[c["cut"]].get("local_tps") or []
                return "; ".join(f"{t['start']:.1f}-{t['end']:.1f}s「{s}」" for s, t in zip(segs, tps)) if tps else "(no timing)"
            ctxt = "\n".join(f"Cut {c['cut']} ({tm[c['cut']]['sec']}s): JP「{c['jp']}」 / KO「{c.get('ko', '')}」 / narration: {chunks_txt(c)} / panel: {c.get('panel_desc', '')}"
                             for c in targets)
            fb = f"# Operator's revision request (must apply)\n{feedback}\n" if feedback else ""
            plan = _json_obj((ask if ask else (lambda p: _gemini_text(p, temperature=0.4)))(
                _VID_PROMPT.format(style=_MINI_STYLE, anatomy=anatomy, last=cuts[-1]["cut"], feedback=fb, cuts=ctxt,
                                   hook_cut=int((sc.get("hook") or {}).get("cut") or 1))))
            prompts = {int(k): str(v) for k, v in (plan.get("prompts") or {}).items() if str(k).isdigit()}
            miss = [c["cut"] for c in targets if len(prompts.get(c["cut"], "")) < 40]
            if miss:
                raise RuntimeError(f"영상 지시문이 빠진 컷: {miss}")
            rid = _rid("clips")
            items = [{"name": f"c{c['cut']:02d}", "start": c["keyframe"], "sec": tm[c["cut"]]["sec"],
                      "prompt": _OMNI_HEAD.format(dur=tm[c["cut"]]["sec"]) + anatomy + "\n\nTIMELINE\n" + prompts[c["cut"]] + _OMNI_TAIL}
                     for c in targets]
            rp = pilot / "requests" / f"{rid}.json"
            _save(rp, {"id": rid, "kind": "gen_omni", "model": "gemini-omni-1.1-flash", "resolution": "720p",
                       "purpose": "본편 컷 자동 생성(Omni Flash · 초 단위 지시문)" + (f" — {','.join(map(str, only))}번만" if only else ""), "items": items})
            _run_request(rp)
            res = _load(pilot / "out" / rid / "result.json") or {}
            got = {it["name"]: it["file"] for it in res.get("items", []) if it.get("file")}
            failed = [c["cut"] for c in targets if f"c{c['cut']:02d}" not in got]
            for c in targets:
                key = f"c{c['cut']:02d}"
                if key in got:
                    prev_clips[c["cut"]] = f"out/{rid}/{got[key]}"
            spent = sum(float(tm[c["cut"]]["sec"]) * OMNI_USD_PER_SEC for c in targets if c["cut"] not in failed)
            st = load_status(pid)
            st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": f"영상 컷 {len(targets) - len(failed)}개 생성", "usd": round(spent, 2)})
            st["artifacts"]["video"] = {**old, "clips_request": rid,
                                        "clips": [{"cut": c["cut"], "file": prev_clips[c["cut"]], "sec": tm[c["cut"]]["sec"],
                                                   "motion": c.get("motion", "omni")} for c in cuts if c["cut"] in prev_clips]}
            _save(status_path(pid), st)
            if failed:
                raise RuntimeError(f"영상 생성 실패 컷: {failed} (성공한 컷은 보관 — 「다시 시도」는 실패 컷만 다시 만듭니다)")
        st = load_status(pid)
        fin = _rid("final")
        (pilot / "out" / fin).mkdir(parents=True, exist_ok=True)
        st["artifacts"]["video"].update(final=f"out/{fin}/final.mp4",
                                        assemble={"clips_id": st["artifacts"]["video"]["clips_request"], "tts_id": tts_id, "ending": ""})
        _note(st, "video", "auto", "영상 컷 준비 완료 — 조립 + 자동 검사")
        _save(status_path(pid), st)
        assemble(pid)
        return set_job(pid, "video", "done", "영상 자동 제작 완료 — 승인 대기", "make_video")
    except SystemExit as e:
        set_job(pid, "video", "failed", f"영상 자동 제작 실패: {str(e)[:220]} — 「다시 시도」를 눌러 주세요", "make_video")
        raise
    except Exception as e:                                   # noqa: BLE001
        set_job(pid, "video", "failed", f"영상 자동 제작 실패: {str(e)[:220]} — 「다시 시도」를 눌러 주세요", "make_video")
        raise SystemExit(f"영상 자동 제작 실패: {e}")


# ── 목록 파일 ─────────────────────────────────────────────────────────────
# ── 시청함 % 기록(운영자 선택 2026-10-09) ────────────────────────────────────
# 유튜브 스튜디오 → 콘텐츠 → 그 쇼츠 → 분석 → 「시청함 vs 넘김」의 '시청함' 비율을 편마다 적어 두고, 후킹 틀별로 비교한다
# (지금은 유튜브 API로 이 숫자를 받지 않는다 · 왕게 편 18.6%). 3편뿐이라 결론이 아니라 가설 검증용.
_OLD_HOOK_PATTERN = {"identity": "名前当て(옛)", "fact": "事実の問い(옛)"}


def hook_pattern_label(sc: dict) -> str:
    hk = sc.get("hook") or {}
    if not hk:
        return "후킹 없음(옛)"
    return hk.get("pattern") or _OLD_HOOK_PATTERN.get(hk.get("type") or hook_type(hk.get("question_jp", "")), "")


def save_viewed(pid: str, data: dict) -> dict:
    st = load_status(pid)
    raw = str(data.get("pct", "")).replace("%", "").strip()
    try:
        pct = round(float(raw), 1)
    except ValueError:
        raise SystemExit("시청함 %는 숫자로 적어 주세요(예: 18.6)")
    if not 0 <= pct <= 100:
        raise SystemExit("시청함 %는 0~100 사이여야 합니다")
    sc = _load(_script_path(pid)) or {}
    hk = sc.get("hook") or {}
    up = st.setdefault("artifacts", {}).setdefault("upload", {})
    up["viewed"] = {"pct": pct, "at": _now(), "note": str(data.get("note", "") or "").strip()[:120],
                    "hook": {"line": hk.get("question_jp", ""), "pattern": hook_pattern_label(sc), "voice": bool(hk.get("voice_jp"))}}
    _note(st, "upload", "viewed", f"시청함 {pct}% 기록 · 후킹 틀 {up['viewed']['hook']['pattern']}")
    _save(status_path(pid), st)
    return st


# ── 시험 릴스로 후킹 겨루기(운영자 선택 2026-10-09: 자동 · 결과 보고 올리기 · 2개) ────────────────────────
# 완성본 승인 → 맨 앞만 다른 B 버전(다른 후보 문장·목소리·첫 장면)을 만들어 A·B 를 인스타 「시험 릴스」(팔로워가 아닌 사람에게
# 먼저 보임 · Meta API 2025-12-03 trial_params)로 함께 올리고, 24~48시간 뒤 「3초 안에 넘긴 비율」(reels_skip_rate)로
# 이긴 후킹을 고른다 → 이긴 후킹으로 유튜브 제목·설명을 쓰고 예약 공개(일본 시간 19시)를 준비한다.
# · 유튜브 업로드 승인(관문 4)은 그대로 운영자. 인스타 「모두에게 공유」(졸업)는 API로 안 돼 앱에서 직접 누른다.
# · 인스타 시청자 ≠ 유튜브 시청자 → 절대 숫자가 아니라 A·B 중 어느 쪽이 나은지만 본다(최종 확인은 유튜브 「시청함 %」).
# · 시험을 못 하면(키 없음·옛 형식 후킹·게시 실패) 이유를 남기고 예전처럼 바로 제목·설명을 쓴다(업로드 준비는 멈추지 않음).
TRIAL_DUE_H = 24                       # 인스타가 24시간 뒤부터 성과를 보여 준다 — 그 전엔 판정하지 않는다
TRIAL_LATE_H = 48                      # 이때까지 조회가 모자라면 낮은 기준으로 판정, 그래도 모자라면 판정 보류
TRIAL_MIN_VIEWS = 300                  # 24시간 판정: 버전마다 조회 이만큼
TRIAL_MIN_VIEWS_LATE = 100             # 48시간 판정: 버전마다 조회 이만큼(이보다 적으면 보류 → A 그대로)
TRIAL_TIE_PP = 3.0                     # 3초 넘김 비율 차이가 이보다 작으면 무승부 → A(처음 고른 후킹) 그대로
TRIAL_WATCH_TIE = 0.10                 # 넘김 비율을 48시간까지 못 받으면 평균 시청 시간으로 — 10% 미만 차이는 무승부
TRIAL_B_GAP_S = 1.0                    # B 첫 장면은 A 구간에서 1초 이상 떨어진 곳(거의 같은 영상 두 개 → 인스타 중복 판정 방지)
TRIAL_B_MOTION = 0.7                   # …단 A 움직임의 70% 이상일 때만, 아니면 A와 같은 장면(B를 덜 움직이는 장면으로 불리하게 안 함)
TRIAL_RULE = (f"게시 {TRIAL_DUE_H}시간 뒤 두 버전 모두 조회 {TRIAL_MIN_VIEWS}회 이상이면 「3초 안에 넘긴 비율」이 "
              f"{TRIAL_TIE_PP:g}%p 이상 낮은 쪽이 이김 · 차이가 그보다 작으면 A 그대로 · {TRIAL_LATE_H}시간까지 조회가 모자라면 "
              f"버전마다 {TRIAL_MIN_VIEWS_LATE}회 이상으로 판정, 그래도 모자라면 판정 보류(A 그대로)")
DASH_URL = "https://shorts-dashboard.jtaechul.workers.dev"   # 인스타가 영상을 가져가는 공개 주소(워커 /v2file/커밋/편/파일)
# ★시험 릴스를 올릴 계정 = ABYSS 인스타 @abyss_0cean 만(운영자 확정 2026-10-10) — 연결된 키가 다른 계정이면 절대 올리지 않는다.
#   실사고 2026-10-10: GitHub 비밀값의 키가 개인 계정(@lord.shiba.ybd) 것이라 파리지옥말미잘 편 시험 릴스 2개가 그 계정에 올라갔다.
IG_ACCOUNT = "abyss_0cean"
TRIAL_WAIT_JOB = {"stage": "upload", "status": "trial_wait", "action": "trial_cancel",   # 무효 → 다시 올리기·건너뛰기 대기(페이지 「시험 대기」)
                  "text": "시험 무효 — 「ABYSS 계정에 다시 올리기」 또는 「시험 건너뛰기」를 기다리는 중"}
_IG_API: dict = {}                     # 테스트용 대체 {"post": f(url, 캡션), "insights": f(media_id), "probe": f(), "check": f(url)}
_COMMIT_PUSH = None                    # 테스트용 대체(커밋·푸시 → 커밋 번호)


def _safe_err(e) -> str:
    """오류 문구에서 토큰을 지운다 — status.json 은 공개 저장소에 커밋된다(요청 주소에 access_token 이 섞여 나올 수 있음)."""
    s = str(e)
    tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if tok:
        s = s.replace(tok, "***")
    return re.sub(r"(access_token=)[^&\s'\"]+", r"\1***", s)[:240]


def _ig() -> dict | None:
    """인스타 API(토큰은 GitHub 비밀값 IG_ACCESS_TOKEN 에서만 · 화면·기록에 남기지 않음) — 키가 없으면 None."""
    if _IG_API:
        return _IG_API
    tok = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not tok:
        return None
    sys.path.insert(0, str(ROOT))
    from src.core import ig_publish as IG                    # noqa: E402
    return {"post": lambda url, cap: IG.publish_trial_reel(tok, url, cap, "MANUAL", expect=IG_ACCOUNT),
            "insights": lambda mid: IG.media_insights(tok, mid),
            "probe": lambda: IG.probe(tok),
            "check": _url_ready}


def _url_ready(url: str, tries: int = 6, wait: float = 10.0) -> bool:
    """인스타가 가져갈 영상 주소가 실제로 mp4 로 열리는지 — 방금 푸시한 파일·새 배포는 잠깐 늦을 수 있어 몇 번 더 본다."""
    import urllib.request
    for i in range(tries):
        if i:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=0-1023", "User-Agent": "shorts-admin/1.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.status in (200, 206) and "video/mp4" in (r.headers.get("Content-Type") or ""):
                    return True
        except Exception:                                    # noqa: BLE001
            pass
    return False


def _commit_push(msg: str) -> str:
    """B 영상을 먼저 커밋·푸시(인스타가 공개 주소로 가져가야 함) → 그 커밋 번호. 워크플로 밖(로컬)에서는 올리지 않는다."""
    if _COMMIT_PUSH:
        return _COMMIT_PUSH(msg)
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("시험 릴스는 워크플로에서만 올립니다(B 영상을 먼저 커밋·푸시해야 인스타가 가져갈 수 있음)")
    r = subprocess.run(["bash", str(V2 / "tools" / "ci_commit.sh"), msg], cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError("B 영상 커밋·푸시 실패: " + (r.stderr or r.stdout or "")[-200:])
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise RuntimeError("커밋 번호를 읽지 못했습니다")
    return sha


def trial_media_url(sha: str, pid: str, rel: str) -> str:
    """커밋 번호로 고정한 공개 주소 — 브랜치 이름 주소는 새 파일이 몇 분 늦게 보일 수 있다(raw 캐시)."""
    return f"{DASH_URL}/v2file/{sha}/{pid}/{rel}"


def trial_caption(sc: dict) -> str:
    """A·B 에 똑같이 붙는 캡션(후킹만 달라야 공정) — 후킹 문장·생물 이름 없이 채널 소개 + AI 재현 표기 + 공통 해시태그."""
    return PLAYLIST_DESC + "\n" + _REPRO_JP + "\n\n" + " ".join(CORE_TAGS_JP)


def _pick_b(hk: dict) -> int | None:
    """B 후보: 지금 후킹과 문장이 다른 후보 중 **틀(pattern)이 다른** 것을 먼저(같은 말 바꾸기보다 다른 각도를 겨룰 가치가 큼)."""
    cands = hk.get("candidates") or []
    others = [i for i, c in enumerate(cands) if isinstance(c, dict) and str(c.get("text_jp") or "").strip()
              and str(c.get("voice_jp") or "").strip() and _norm(c["text_jp"]) != _norm(hk.get("question_jp", ""))]
    diff = [i for i in others if cands[i].get("pattern") != hk.get("pattern")]
    return (diff or others or [None])[0]


def _other_window(series: list, a_at: float, usable_s: float, sec: float) -> tuple[float, float]:
    """B 첫 장면(같은 컷): A 구간에서 TRIAL_B_GAP_S 이상 떨어진 곳 중 가장 많이 움직이는 sec초 — 그 움직임이 A 의
    TRIAL_B_MOTION 배 이상일 때만, 아니면 A 와 같은 곳. 반환 (시작 초, 움직임)."""
    sys.path.insert(0, str(V2 / "tools"))
    import assemble as A                                     # noqa: E402
    a_m = A.window_motion(series, a_at, sec)
    best = None
    for i in range(int(round(max(0.0, usable_s - sec) * A.MOTION_FPS)) + 1):
        t = round(i / A.MOTION_FPS, 2)
        if abs(t - a_at) < TRIAL_B_GAP_S:
            continue
        m = A.window_motion(series, t, sec)
        if best is None or m > best[1]:
            best = (t, m)
    if best and best[1] > 0 and best[1] >= TRIAL_B_MOTION * a_m:
        return best
    return round(a_at, 2), a_m


def _assemble_with_hook(pid: str, hk: dict, dst: Path) -> dict:
    """대본은 그대로 두고 맨 앞 후킹만 hk 로 바꿔 조립(시험 B 버전 · 이긴 B 를 새 본편으로 다시 조립)."""
    st = load_status(pid)
    pilot = PILOTS / pid
    a = st["artifacts"]["video"]
    sys.path.insert(0, str(V2 / "tools"))
    import assemble as A                                     # noqa: E402
    over = {int(c["cut"]): str(pilot / c["file"]) for c in a.get("clips", [])}
    dst.parent.mkdir(parents=True, exist_ok=True)
    return A.main(str(pilot), a["assemble"]["clips_id"], a["assemble"]["tts_id"], "", str(dst), overrides=over,
                  hook_override=hk) or {}


def _hook_checks(pid: str, dst: Path, used: dict, voice_jp: str) -> dict:
    """맨 앞이 바뀐 완성본 검사(움직임 · 목소리 · 음량 · 맨 앞 가장자리 흰 줄)."""
    ck = auto_checks(dst, body_s=float(used.get("len") or 3.0))
    out = {k: ck[k] for k in ("duration_s", "loudness_lufs")}
    if not ck["white_edge_px"]["ok"]:
        out["white_edge_px"] = ck["white_edge_px"]
    out.update(motion_checks(dst, used))
    out["hook_voice"] = {"ok": bool(used.get("voice")), "value": voice_jp,
                         "rule": "후킹 한 줄을 0초부터 목소리로 읽기(실패하면 맨 앞이 무음 — 「완성본 다시 조립」으로 다시 시도)"}
    return out


def build_trial_variant(pid: str, ib: int) -> dict:
    """B 버전 완성본: 후보 ib 의 문장·빨간 단어·목소리 + (되면) 다른 첫 장면. 대본(script.json)은 바꾸지 않는다.
    반환 {"hook": B 후킹(전체), "file": 편 폴더 기준 mp4, "checks": 검사}."""
    st = load_status(pid)
    sc = _load(_script_path(pid)) or {}
    pilot = PILOTS / pid
    a = st["artifacts"]["video"]
    sys.path.insert(0, str(V2 / "tools"))
    import assemble as A                                     # noqa: E402
    hb = hook_from_candidate(sc["hook"], ib)
    for k in ("voice_file", "voice_for", "motion"):
        hb.pop(k, None)
    A.check_glyphs(hb["question_jp"], "시험 B 후킹")
    vrel = _tts_line(pid, hb["voice_jp"], "trial_tts")
    if not vrel:
        raise RuntimeError("B 후킹 목소리 합성 실패")
    hb["voice_file"], hb["voice_for"] = vrel, hb["voice_jp"]
    n = int(hb["cut"])
    clip = next((pilot / c["file"] for c in a.get("clips", []) if int(c["cut"]) == n), None) \
        or pilot / "out" / a["assemble"]["clips_id"] / f"c{n:02d}.mp4"
    cut_s = float(next((c.get("sec") for c in sc.get("cuts", []) if c.get("cut") == n and "tts" in c), 0) or 0)
    at_b, m_b = _other_window(A.motion_series(clip, dur=cut_s or None), float(sc["hook"].get("at") or 0), cut_s,
                              A.hook_seconds(pilot / vrel))
    hb.update(at=at_b, at_by="trial")                        # 조립 때 이 구간 그대로(자동 선택이 A 와 같은 곳으로 돌리지 않게)
    dst = pilot / "out" / _rid("trial") / "final_b.mp4"
    used = _assemble_with_hook(pid, hb, dst).get("hook") or {}
    hb.update(at=used.get("at", at_b), motion=used.get("motion", m_b))
    return {"hook": hb, "file": str(dst.relative_to(pilot)), "checks": _hook_checks(pid, dst, used, hb["voice_jp"])}


def _hook_brief(h: dict) -> dict:
    return {k: h.get(k) for k in ("question_jp", "question_ko", "key_jp", "voice_jp", "pattern", "chosen", "cut", "at", "motion")}


def _ig_account_ok(api: dict) -> tuple[bool, str]:
    """연결된 인스타 계정이 ABYSS(@abyss_0cean)인지 — 게시 전 필수. (맞는지, 계정 이름). 결과는 목록 화면 「인스타 연결」 칸에도 남긴다."""
    res: dict = {"at": _now(), "expected": IG_ACCOUNT}
    user, ok = "", False
    try:
        user = str((api["probe"]() or {}).get("username") or "")
        ok = user.lower() == IG_ACCOUNT.lower()
        res.update(ok=ok, username=user)
        if not ok:
            res["error"] = f"연결된 계정이 @{user or '?'} — ABYSS(@{IG_ACCOUNT})가 아니라 시험 릴스를 올리지 않습니다(키를 @{IG_ACCOUNT} 것으로 바꿔 주세요)"
    except Exception as e:                                   # noqa: BLE001
        res.update(ok=False, error=_safe_err(e))
    _save(_ig_status_path(), res)
    return ok, user


def start_trial(pid: str, api: dict, ib: int, reuse_b: dict | None = None) -> dict:
    """계정 확인(@abyss_0cean) → B 버전 조립(reuse_b 가 있으면 이미 만든 B 그대로) → 커밋·푸시 → A·B 를 시험 릴스로 게시(수동 졸업)
    → artifacts.trial = 진행 중. 예전 무효 기록(voided)은 그대로 둔다."""
    ok, user = _ig_account_ok(api)
    if not ok:
        raise RuntimeError(f"연결된 인스타 계정이 @{user or '?'} — ABYSS(@{IG_ACCOUNT})가 아니라 올리지 않았습니다"
                           f"(GitHub 비밀값 IG_ACCESS_TOKEN 을 @{IG_ACCOUNT} 계정 키로 바꿔 주세요)")
    set_job(pid, "upload", "running", "시험 릴스 준비 중 — B 버전 조립 → 인스타에 A·B 게시(5~15분)", "after_video")
    b = reuse_b or build_trial_variant(pid, ib)
    sha = _commit_push(f"chore(v2): 시험 릴스 B 영상 {pid} [skip ci]")
    st = load_status(pid)
    sc = _load(_script_path(pid)) or {}
    a = st["artifacts"]["video"]
    files = {"a": a["final"], "b": b["file"]}
    cap = trial_caption(sc)
    order = ["a", "b"] if sum(map(ord, pid)) % 2 == 0 else ["b", "a"]   # 먼저 올린 쪽이 늘 유리하지 않게 편마다 번갈아
    posted: dict = {}
    try:
        for k in order:
            url = trial_media_url(sha, pid, files[k])
            if not api["check"](url):
                raise RuntimeError(f"{k.upper()} 영상 주소가 열리지 않습니다(관리자 페이지 배포를 확인): {url}")
            posted[k] = api["post"](url, cap)
    except Exception as e:                                   # noqa: BLE001
        done = ", ".join(f"{k.upper()} {posted[k].get('permalink') or posted[k].get('media_id')}" for k in posted)
        raise RuntimeError(_safe_err(e) + (f" — 이미 올라간 시험 릴스: {done}(인스타 앱에서 지우거나 그대로 두세요)" if done else ""))
    hk = sc["hook"]
    side = lambda k, h: {"hook": h, "file": files[k], "media_id": posted[k].get("media_id", ""),   # noqa: E731
                         "permalink": posted[k].get("permalink", ""), "metrics": {}}
    tr = {"state": "running", "posted_at": _now(), "video_built_at": a.get("built_at"), "order": order, "rule": TRIAL_RULE,
          "caption": cap, "strategy": "MANUAL", "username": next((p.get("username") for p in posted.values() if p.get("username")), ""),
          "a": side("a", _hook_brief(hk)), "b": {**side("b", b["hook"]), "checks": b.get("checks") or {}}}
    old = (st.get("artifacts") or {}).get("trial") or {}
    if old.get("voided"):
        tr["voided"] = old["voided"]
    st["artifacts"]["trial"] = tr
    st.setdefault("jobs", {})["upload"] = {"stage": "upload", "status": "trial", "at": _now(), "action": "after_video",
                                           "text": "인스타 시험 릴스로 후킹 A·B 를 겨루는 중 — 게시 24시간 뒤부터 결과"}
    _note(st, "upload", "trial", f"시험 릴스 2개 게시 — A 「{hk.get('question_jp', '')}」 · B 「{b['hook']['question_jp']}」. "
                                 f"{TRIAL_DUE_H}~{TRIAL_LATE_H}시간 뒤 판정하고, 이긴 후킹으로 제목·설명을 씁니다")
    _save(status_path(pid), st)
    return st


def next_publish_slot(now: float | None = None, hour: int = 19) -> str:
    """다음 일본(=한국) 시간 19:00 — 지금부터 1시간 이상 뒤 → UTC 'YYYY-MM-DDTHH:MM:00Z'(유튜브 예약 공개 시각)."""
    import datetime as dt
    jst = dt.timezone(dt.timedelta(hours=9))
    n = dt.datetime.fromtimestamp(time.time() if now is None else now, jst)
    s = n.replace(hour=hour, minute=0, second=0, microsecond=0)
    if s.timestamp() - n.timestamp() < 3600:
        s += dt.timedelta(days=1)
    return s.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:00Z")


def _write_meta_safely(pid: str, schedule: bool = False) -> bool:
    """유튜브 제목·설명 자동 작성 — 실패해도 멈추지 않고 기록만(화면의 「제목·설명 AI로 쓰기」로 다시).
    schedule: 시험 판정 뒤 → 운영자가 고른 공개 범위가 없으면 「예약 공개 · 다음 19시」로 준비(업로드는 운영자 승인 때)."""
    try:
        upload_meta(pid)
    except Exception as e:                                   # noqa: BLE001
        st = load_status(pid)
        _note(st, "upload", "error", f"제목·설명 자동 작성 실패 — 「제목·설명 AI로 쓰기」를 눌러 주세요: {str(e)[:120]}")
        _save(status_path(pid), st)
        return False
    if schedule:
        st = load_status(pid)
        m = st["artifacts"]["upload"]["meta"]
        if m.get("privacy", "private") == "private":
            m["privacy"], m["publish_at"] = "scheduled", next_publish_slot()
            _note(st, "upload", "meta", f"예약 공개 준비: {m['publish_at']}(UTC = 일본·한국 19시) — 업로드는 「승인」을 눌러야 합니다")
            _save(status_path(pid), st)
    return True


def after_video(pid: str) -> dict:
    """완성본 승인 뒤(워크플로 '버튼 실행' 단계 · 키 있음): 시험 릴스로 후킹 겨루기 시작.
    못 하면(옛 형식 후킹 · 다른 후보 없음 · 인스타 키 없음 · 게시 실패) 이유를 남기고 예전처럼 바로 제목·설명을 쓴다."""
    st = load_status(pid)
    if st["stages"]["video"]["state"] != "approved":
        raise SystemExit("완성본이 아직 승인되지 않았습니다")
    if (((st.get("artifacts") or {}).get("upload") or {}).get("result") or {}).get("url"):
        print("이미 유튜브에 올린 편 — 그대로 둡니다")
        return st
    tr = (st.get("artifacts") or {}).get("trial") or {}
    if tr.get("state") == "running":                         # 다시 승인(수정 뒤)해도 진행 중인 시험은 그대로 — 후킹 문장 비교라 본편 수정과 무관
        _note(st, "upload", "trial", "시험 릴스 진행 중 — 결과가 나오면 이긴 후킹으로 제목·설명을 씁니다")
        _save(status_path(pid), st)
        return st
    if tr.get("state") == "cancelled":                       # 무효가 된 시험 — 운영자가 「ABYSS 계정에 다시 올리기」나 「건너뛰기」를 고른다
        _note(st, "upload", "trial", "시험이 무효 상태입니다 — 「ABYSS 계정에 다시 올리기」 또는 「시험 건너뛰기」를 눌러 주세요")
        _save(status_path(pid), st)
        return st
    if tr.get("state") == "decided":                         # 이미 판정 — 대본 후킹이 이긴 쪽이라 다시 조립해도 이긴 후킹
        _write_meta_safely(pid, schedule=True)
        return load_status(pid)
    sc = _load(_script_path(pid)) or {}
    hk = sc.get("hook") or {}
    api = _ig()
    ib = _pick_b(hk) if hk.get("type") == "line" else None
    voice_ok = ((st.get("checks") or {}).get("hook_voice") or {}).get("ok", True)
    why = ("옛 형식 후킹(후보 문장 없음)" if hk.get("type") != "line" else
           "겨룰 다른 후보 문장이 없음" if ib is None else
           "A 버전 맨 앞 목소리가 없어 공정하게 비교할 수 없음(「완성본 다시 조립」 뒤 다시 승인하면 시험)" if not voice_ok else
           "인스타 연결 키(IG_ACCESS_TOKEN)가 없음 — 영상 목록의 「인스타 시험 릴스」 칸 안내를 보세요" if not api else "")
    if not why:
        ok, user = _ig_account_ok(api)
        if not ok:                                           # ★키는 있는데 ABYSS 계정이 아님(또는 연결 오류) — 올리지 않고 기다린다(2026-10-10)
            err = (_load(_ig_status_path()) or {}).get("error", "")
            st = load_status(pid)
            st.setdefault("artifacts", {})["trial"] = {
                "state": "cancelled", "at": _now(), "rule": TRIAL_RULE,
                "reason": (f"연결된 인스타 계정이 @{user} — ABYSS(@{IG_ACCOUNT})가 아니라 올리지 않았습니다" if user
                           else f"인스타 연결 확인 실패 — {err}")}
            st.setdefault("jobs", {})["upload"] = {**TRIAL_WAIT_JOB, "at": _now()}
            _note(st, "upload", "trial", st["artifacts"]["trial"]["reason"] + f". 키를 @{IG_ACCOUNT} 것으로 고친 뒤 「ABYSS 계정에 다시 올리기」, "
                                         "또는 「시험 건너뛰고 지금 후킹(A)으로 진행」을 눌러 주세요")
            _save(status_path(pid), st)
            return st
        try:
            return start_trial(pid, api, ib)
        except Exception as e:                               # noqa: BLE001 — 시험이 안 돼도 업로드 준비는 계속
            why = "시험 릴스 게시 실패: " + _safe_err(e)
    st = load_status(pid)
    st.setdefault("artifacts", {})["trial"] = {"state": "skipped", "reason": why, "at": _now()}
    st.setdefault("jobs", {})["upload"] = {"stage": "upload", "status": "done", "at": _now(), "action": "after_video",
                                           "text": "시험 릴스 없이 진행"}
    _note(st, "upload", "trial", f"시험 릴스 건너뜀 — {why}. 지금 후킹으로 제목·설명을 씁니다")
    _save(status_path(pid), st)
    _write_meta_safely(pid)
    return load_status(pid)


def _iso_ts(iso: str) -> float:
    import datetime as dt
    return dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()


def _skip_pct(v) -> float | None:
    """3초 넘김 비율 → % (API 가 0~1 비율로 주면 100 을 곱한다 · 실제 넘김 비율이 1% 미만일 일은 없다)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v * 100 if 0 < v < 1 else v, 1)


def trial_decide(tr: dict, now: float | None = None) -> dict:
    """판정(TRIAL_RULE) — kind: wait(아직) · win(승부 남) · tie(차이 작음 → A) · hold(조회 부족 → A)."""
    hours = round(((time.time() if now is None else now) - _iso_ts(tr["posted_at"])) / 3600, 1)
    res = {"hours": hours, "winner": None}
    if hours < TRIAL_DUE_H:
        return {**res, "kind": "wait", "why": f"게시 {hours:g}시간 — {TRIAL_DUE_H}시간 뒤부터 판정"}
    ma, mb = ((tr.get(k) or {}).get("metrics") or {} for k in ("a", "b"))
    if "views" not in ma or "views" not in mb:
        return {**res, "kind": "wait", "why": "지표를 아직 못 가져왔습니다(인스타 연결 확인)"}
    va, vb = int(ma.get("views") or 0), int(mb.get("views") or 0)
    late = hours >= TRIAL_LATE_H
    need = TRIAL_MIN_VIEWS_LATE if late else TRIAL_MIN_VIEWS
    if min(va, vb) < need:
        if not late:
            return {**res, "kind": "wait", "why": f"조회 A {va} · B {vb} — 버전마다 {TRIAL_MIN_VIEWS}회가 모일 때까지(최대 {TRIAL_LATE_H}시간)"}
        return {**res, "kind": "hold", "why": f"{TRIAL_LATE_H}시간 동안 조회가 모자람(A {va} · B {vb}, 버전마다 {TRIAL_MIN_VIEWS_LATE}회 필요) — A 그대로"}
    sa, sb = _skip_pct(ma.get("reels_skip_rate")), _skip_pct(mb.get("reels_skip_rate"))
    if sa is not None and sb is not None:
        d = round(sa - sb, 1)                                # + 이면 B 가 덜 넘김
        if abs(d) < TRIAL_TIE_PP:
            return {**res, "kind": "tie", "by": "skip", "why": f"3초 안에 넘김 A {sa}% · B {sb}% — 차이 {abs(d):g}%p(기준 {TRIAL_TIE_PP:g}%p 미만) → A 그대로"}
        w = "b" if d > 0 else "a"
        return {**res, "kind": "win", "winner": w, "by": "skip", "why": f"3초 안에 넘김 A {sa}% · B {sb}% → {w.upper()} 가 {abs(d):g}%p 덜 넘김"}
    if not late:
        return {**res, "kind": "wait", "why": f"「3초 안에 넘긴 비율」을 아직 못 받음(조회 A {va} · B {vb}) — {TRIAL_LATE_H}시간까지 기다림"}
    wa, wb = float(ma.get("ig_reels_avg_watch_time") or 0), float(mb.get("ig_reels_avg_watch_time") or 0)
    if wa > 0 and wb > 0:
        rel = (wb - wa) / max(wa, wb)
        txt = f"넘김 비율을 끝내 못 받아 평균 시청 시간으로: A {wa / 1000:.1f}초 · B {wb / 1000:.1f}초"
        if abs(rel) < TRIAL_WATCH_TIE:
            return {**res, "kind": "tie", "by": "watch", "why": txt + f" — 차이 {TRIAL_WATCH_TIE:.0%} 미만 → A 그대로"}
        w = "b" if rel > 0 else "a"
        return {**res, "kind": "win", "winner": w, "by": "watch", "why": txt + f" → {w.upper()} 승"}
    return {**res, "kind": "hold", "why": "비교할 지표(넘김 비율·평균 시청 시간)를 끝내 못 받음 — A 그대로"}


def trial_check(pid: str | None = None, now: float | None = None) -> list[dict]:
    """진행 중인 시험 릴스 지표를 가져와 판정(편 id 가 없으면 진행 중인 모든 편) — 승부가 나면 apply_trial_result."""
    api = _ig()
    pids = [pid] if pid else [p.parent.name for p in sorted(PILOTS.glob("*/status.json"))]
    out = []
    for p in pids:
        st = load_status(p)
        tr = (st.get("artifacts") or {}).get("trial") or {}
        if tr.get("state") != "running":
            continue
        if not api:
            tr["error"] = "인스타 연결 키(IG_ACCESS_TOKEN)가 없어 결과를 못 가져왔습니다"
        else:
            tr.pop("error", None)
            for k in ("a", "b"):
                try:
                    got = api["insights"](tr[k]["media_id"])
                    tr[k]["metrics"] = {**(tr[k].get("metrics") or {}), **{m: v for m, v in (got.get("metrics") or {}).items() if v is not None}}
                    tr[k]["metric_errors"] = {m: _safe_err(v) for m, v in (got.get("errors") or {}).items()}
                except Exception as e:                       # noqa: BLE001 — 한쪽이 실패해도 다른 쪽은 기록
                    tr[k]["metric_errors"] = {"all": _safe_err(e)}
        tr["checked_at"] = _now()
        dec = trial_decide(tr, now)
        tr["last"] = dec
        st["artifacts"]["trial"] = tr
        _save(status_path(p), st)
        if dec["kind"] != "wait":
            apply_trial_result(p, dec)
        out.append({"pid": p, **dec})
    return out


def apply_trial_result(pid: str, dec: dict) -> dict:
    """판정 반영: B 가 이기면 대본 후킹을 B 로 바꾸고(구간 고정 at_by=trial) 완성본도 B 로 — 아니면 A 그대로.
    그다음 이긴 후킹으로 유튜브 제목·설명 + 예약 공개 준비. 업로드 자체는 운영자 승인(관문 4)."""
    st = load_status(pid)
    tr = st["artifacts"]["trial"]
    tr.update(state="decided", result=dec, decided_at=_now())
    win = dec.get("winner") if dec.get("kind") == "win" else None
    tr["winner"] = win or "a"
    a = st["artifacts"]["video"]
    if win == "b":
        sc = _load(_script_path(pid))
        hb = {**tr["b"]["hook"], "at_by": "trial"}
        sc.setdefault("hook_history", []).append({"at": _now(), "hook": sc["hook"], "why": "시험 릴스에서 B 승"})
        sc["hook"] = hb
        _save(_script_path(pid), sc)
        _sync_script_artifacts(st, sc)
        same = tr.get("video_built_at") == a.get("built_at") and (PILOTS / pid / tr["b"]["file"]).exists()
        if same:                                             # 시험에 쓴 바로 그 B 영상
            fb, ck = tr["b"]["file"], tr["b"].get("checks") or {}
        else:                                                # 시험 중 본편을 고쳐 다시 조립했으면 새 본편 + B 후킹으로 다시 조립
            dst = PILOTS / pid / "out" / _rid("final_b") / "final.mp4"
            used = _assemble_with_hook(pid, hb, dst).get("hook") or {}
            fb, ck = str(dst.relative_to(PILOTS / pid)), _hook_checks(pid, dst, used, hb.get("voice_jp", ""))
        a["final_a"], a["final"] = a["final"], fb
        st.setdefault("checks", {}).update(ck)
        _note(st, "video", "trial", f"시험 릴스 결과 B 승 — 완성본을 B 버전(「{hb.get('question_jp', '')}」)으로 바꿨습니다")
    st.setdefault("jobs", {})["upload"] = {"stage": "upload", "status": "done", "at": _now(), "action": "trial_check",
                                           "text": "시험 릴스 판정 끝"}
    kind_ko = {"win": f"{(win or 'a').upper()} 승", "tie": "무승부(A 그대로)", "hold": "판정 보류(A 그대로)"}.get(dec.get("kind"), "")
    _note(st, "upload", "trial", f"시험 릴스 판정: {kind_ko} — {dec.get('why', '')}. 이긴 후킹으로 제목·설명을 씁니다 · "
                                 f"인스타 앱에서 이긴 릴스의 「모두에게 공유」를 누르면 팔로워에게도 보입니다")
    _save(status_path(pid), st)
    _write_meta_safely(pid, schedule=True)
    return load_status(pid)


def trial_cancel(pid: str, reason: str = "") -> dict:
    """진행 중인 시험을 무효로(예: 다른 계정에 올라감) — 그 결과로는 판정하지 않는다. 올라간 릴스 주소는 「지워 주세요」로
    남기고(voided), 운영자의 「ABYSS 계정에 다시 올리기」(trial_repost) 또는 「시험 건너뛰기」(trial_skip)를 기다린다."""
    st = load_status(pid)
    tr = (st.get("artifacts") or {}).get("trial") or {}
    if tr.get("state") != "running":
        raise SystemExit("진행 중인 시험이 없습니다")
    reason = reason.strip() or "운영자가 시험을 무효로 함"
    tr.setdefault("voided", []).append({"at": _now(), "reason": reason, "username": tr.get("username", ""), "posted_at": tr.get("posted_at"),
                                        "posts": [{"side": k, "media_id": tr[k].get("media_id", ""), "permalink": tr[k].get("permalink", "")}
                                                  for k in ("a", "b")]})
    for k in ("a", "b"):
        for f in ("media_id", "permalink", "metric_errors"):
            tr[k].pop(f, None)
        tr[k]["metrics"] = {}
    for f in ("posted_at", "checked_at", "last", "username", "error"):
        tr.pop(f, None)
    tr.update(state="cancelled", reason=reason)
    st.setdefault("jobs", {})["upload"] = {**TRIAL_WAIT_JOB, "at": _now()}
    _note(st, "upload", "trial", f"시험 무효: {reason} — 올라간 릴스는 인스타 앱에서 지워 주세요. 「ABYSS 계정에 다시 올리기」로 다시 시험합니다")
    _save(status_path(pid), st)
    return st


def trial_repost(pid: str) -> dict:
    """무효가 된 시험을 ABYSS(@abyss_0cean)에 다시 올린다 — 이미 만든 A·B 영상 그대로(추가 비용 없음).
    본편이 그 뒤 다시 조립됐으면 B 를 새로 만든다. 연결된 계정이 다르면 올리지 않고 멈춘다."""
    st = load_status(pid)
    tr = (st.get("artifacts") or {}).get("trial") or {}
    if tr.get("state") != "cancelled":
        raise SystemExit("다시 올릴 시험이 없습니다(무효가 된 시험만 다시 올립니다)")
    if st["stages"]["video"]["state"] != "approved":
        raise SystemExit("완성본을 먼저 승인해 주세요")
    api = _ig()
    if not api:
        raise SystemExit("인스타 연결 키(IG_ACCESS_TOKEN)가 없습니다")
    sc = _load(_script_path(pid)) or {}
    b = tr.get("b") or {}
    ib = b.get("hook", {}).get("chosen")
    ib = ib if isinstance(ib, int) else _pick_b(sc.get("hook") or {})
    same = tr.get("video_built_at") == st["artifacts"]["video"].get("built_at") and b.get("file") and (PILOTS / pid / b["file"]).exists()
    try:
        return start_trial(pid, api, ib, reuse_b={k: b[k] for k in ("hook", "file", "checks") if k in b} if same else None)
    except Exception as e:                                   # noqa: BLE001 — 실패해도 무효 상태로 되돌려 다시 누를 수 있게
        st = load_status(pid)
        st["artifacts"]["trial"]["error"] = _safe_err(e)
        st.setdefault("jobs", {})["upload"] = {**TRIAL_WAIT_JOB, "at": _now()}
        _note(st, "upload", "error", "다시 올리기 실패: " + _safe_err(e))
        _save(status_path(pid), st)
        raise SystemExit("다시 올리기 실패: " + _safe_err(e))


def trial_skip(pid: str) -> dict:
    """운영자가 시험을 건너뜀 — 지금 후킹(A)으로 바로 제목·설명(인스타에 올라간 시험 릴스는 그대로 둔다 · 팔로워에겐 안 보임)."""
    st = load_status(pid)
    tr = (st.get("artifacts") or {}).get("trial") or {}
    if tr.get("state") == "decided":
        raise SystemExit("시험 판정이 이미 끝났습니다")
    if st["stages"]["video"]["state"] != "approved":
        raise SystemExit("완성본을 먼저 승인해 주세요")
    tr.update(state="skipped", reason="운영자가 건너뜀", at=_now())
    st.setdefault("artifacts", {})["trial"] = tr
    st.setdefault("jobs", {})["upload"] = {"stage": "upload", "status": "done", "at": _now(), "action": "trial_skip",
                                           "text": "시험 릴스 건너뜀"}
    _note(st, "upload", "trial", "운영자가 시험 릴스를 건너뜀 — 지금 후킹으로 제목·설명을 씁니다")
    _save(status_path(pid), st)
    _write_meta_safely(pid)
    return load_status(pid)


def _ig_status_path() -> Path:
    return PILOTS / "_shared" / "ig_status.json"


def ig_probe() -> dict:
    """인스타 연결 점검(게시 없음) — 키가 있는지 · 어느 계정에 올라가는지. 결과는 목록 화면에 보인다(index.json)."""
    api = _ig()
    if not api:
        res = {"at": _now(), "expected": IG_ACCOUNT, "ok": False, "error": "GitHub 비밀값 IG_ACCESS_TOKEN 이 없습니다"}
        _save(_ig_status_path(), res)
        return res
    _ig_account_ok(api)                                      # 계정이 @abyss_0cean 이 아니면 ok=False + 경고
    return _load(_ig_status_path())


def hook_pattern_stats() -> dict:
    """후킹 틀별 시험 릴스 성적 {틀: {tests, wins, losses, ties, skip_avg}} — 판정 보류는 세지 않는다."""
    out: dict = {}
    for p in sorted(PILOTS.glob("*/status.json")):
        tr = ((_load(p, {}) or {}).get("artifacts") or {}).get("trial") or {}
        res = tr.get("result") or {}
        if tr.get("state") != "decided" or res.get("kind") not in ("win", "tie"):
            continue
        for k in ("a", "b"):
            s = out.setdefault(((tr.get(k) or {}).get("hook") or {}).get("pattern") or "?",
                               {"tests": 0, "wins": 0, "losses": 0, "ties": 0, "skips": []})
            s["tests"] += 1
            s["ties" if res["kind"] == "tie" else ("wins" if res.get("winner") == k else "losses")] += 1
            sk = _skip_pct(((tr.get(k) or {}).get("metrics") or {}).get("reels_skip_rate"))
            if sk is not None:
                s["skips"].append(sk)
    for s in out.values():
        sk = s.pop("skips")
        s["skip_avg"] = round(sum(sk) / len(sk), 1) if sk else None
    return out


TRIAL_HINT_MIN = 3                     # 판정 난 시험이 이만큼 쌓여야 다음 대본 후보 쓰기에 참고로 알려 준다(적으면 우연)


def _pattern_hint() -> str:
    """지금까지 시험 릴스에서 어느 틀이 이겼는지 — 다음 대본 후보 3개를 쓸 때 참고(3개·서로 다른 틀 규칙은 그대로)."""
    stats = hook_pattern_stats()
    if sum(s["tests"] for s in stats.values()) < 2 * TRIAL_HINT_MIN:
        return ""
    rows = sorted(stats.items(), key=lambda kv: (-(kv[1]["wins"] - kv[1]["losses"]), kv[0]))
    return ("- 参考(これまでのInstagram試験リールで、最初の3秒で飛ばされにくかった型。少数なので傾向として): "
            + " / ".join(f"{k} {s['wins']}勝{s['losses']}敗{s['ties']}分" for k, s in rows)
            + "。成績の良い型を候補1にしてよいが、型の違う3つを出す規則は同じ。\n")


def _trial_brief(tr: dict | None) -> dict | None:
    if not tr:
        return None
    side = lambda k: {"line": (((tr.get(k) or {}).get("hook")) or {}).get("question_jp", ""),   # noqa: E731
                      "pattern": (((tr.get(k) or {}).get("hook")) or {}).get("pattern", "")}
    return {"state": tr.get("state"), "posted_at": tr.get("posted_at"), "checked_at": tr.get("checked_at"),
            "winner": tr.get("winner"), "kind": (tr.get("result") or {}).get("kind"), "reason": tr.get("reason"),
            "a": side("a"), "b": side("b")}


def build_index() -> dict:
    items = []
    for p in sorted(PILOTS.glob("*/status.json")):
        st = _load(p, {})
        if not st:
            continue
        cur = next((s for s in STAGES if st["stages"][s]["state"] != "approved"), "done")
        items.append({"id": st["id"], "name_ko": st.get("name_ko", ""), "sci": st.get("sci", ""),
                      "stage": cur, "state": st["stages"][cur]["state"] if cur != "done" else "approved",
                      "job": (st.get("jobs") or {}).get(cur), "created": st.get("created", ""),
                      "uploaded_at": (lambda r: r.get("publish_at") or r.get("at"))(                 # 예약이면 공개 시각 기준(주 2편 집계)
                          (((st.get("artifacts") or {}).get("upload") or {}).get("result") or {})),
                      "stats": (((st.get("artifacts") or {}).get("upload") or {}).get("stats")),
                      "viewed": (((st.get("artifacts") or {}).get("upload") or {}).get("viewed")),   # 시청함 %·후킹 틀
                      "trial": _trial_brief((st.get("artifacts") or {}).get("trial"))})            # 시험 릴스(목록 화면 · 자동 결과 확인)
    idx = {"updated": _now(), "items": items, "hook_patterns": hook_pattern_stats(), "ig": _load(_ig_status_path())}
    _save(PILOTS / "index.json", idx)
    return idx


# ── 주제 카드 사진·한글명(운영자 확정 2026-09-30: '시작할 수 있는 종' 이름 옆에 이미지와 한글명) ──────
# 사진은 iNaturalist 종 대표 사진 중 **자유 라이선스(퍼블릭 도메인·CC)** 만 쓴다(저작권 표시 그대로 보관).
# 한 번 찾은 결과는 topic_media.json 에 캐시해, 매번 외부에 묻지 않는다(찾지 못해도 주제 목록은 그대로 만든다).
TOPIC_MEDIA = V2 / "topic_media.json"
_FREE_LIC = {"cc0", "pd", "cc-by", "cc-by-sa", "cc-by-nc", "cc-by-nc-sa", "cc-by-nd", "cc-by-nc-nd"}
# 정식 한글 종명이 없는 종 = 지어내지 않고, 확실한 상위 무리 이름으로만 적는다(화면에 '정식 한글명 없음' 표기).
KO_GROUP = {
    "chaunax_stigmaeus": "아귀목 심해어",
    "grimpoteuthis_discoveryi": "덤보문어의 한 종",
    "pannychia_moseleyi": "심해 해삼의 한 종",
}


def _get_json(url: str, timeout: int = 20):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "shorts-admin/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_topic_photo(sci: str, get=None) -> dict | None:
    """학명으로 iNaturalist 분류군을 찾아, 자유 라이선스 대표 사진 1장을 돌려준다. 없으면 None."""
    import urllib.parse
    get = get or _get_json
    name = re.sub(r"\s+(sp|spp)\.?$", "", sci.strip(), flags=re.I)
    q = urllib.parse.quote(name)
    res = (get("https://api.inaturalist.org/v1/taxa?per_page=10&q=" + q).get("results") or []) + \
        (get("https://api.inaturalist.org/v1/taxa/autocomplete?per_page=10&q=" + q).get("results") or [])
    # 학명이 바뀐 종(예: 넓적문어)은 옛 이름이 matched_term 으로 걸린 '현재 이름' 분류군을 쓴다(같은 생물).
    hit = next((t for t in res if (t.get("name") or "").lower() == name.lower()), None) or \
        next((t for t in res if t.get("is_active", True) and (t.get("matched_term") or "").lower() == name.lower()), None)
    if not hit:
        return None
    full = (get("https://api.inaturalist.org/v1/taxa/%d" % hit["id"]).get("results") or [hit])[0]
    photos = [tp.get("photo") or {} for tp in full.get("taxon_photos") or []] or [full.get("default_photo") or {}]
    for ph in photos:
        if (ph.get("license_code") or "").lower() in _FREE_LIC and ph.get("medium_url"):
            return {"url": ph["medium_url"], "credit": ph.get("attribution") or "", "license": ph["license_code"],
                    "page": "https://www.inaturalist.org/taxa/%d" % hit["id"]}
    return None


def _topic_media(items: list[dict], fetch=None) -> dict:
    cache = _load(TOPIC_MEDIA, {}) or {}
    changed = False
    for t in items:
        if t["id"] in cache:
            continue
        try:
            cache[t["id"]] = {"photo": (fetch or fetch_topic_photo)(t["sci"]), "at": _now()}
            changed = True
            time.sleep(1)                                   # 외부 사이트 예의(요청 간격)
        except Exception as e:                              # 네트워크가 없어도 목록은 만든다(다음에 다시 시도)
            print(f"[topics] 사진 찾기 실패 {t['id']}: {e}")
    if changed:
        _save(TOPIC_MEDIA, cache)
    return cache


# ── 주제 '놀라움 점수'(운영자 선택 2026-10-05) ─────────────────────────────────────
# 이긴 두 편(5년 절식 · 머리가 없음)은 "한 줄로 말할 수 있는 믿기 힘든 사실"이 제목·후킹을 이끌었다 → 주제 후보마다
# AI가 출처 있는 사실 안에서 그 한 줄과 1~10점을 매기고, 새 영상 페이지는 점수 높은 종부터 보여 준다. 결과는 캐시.
TOPIC_SCORES = V2 / "topic_scores.json"
_SCORE_PROMPT = """You pick topics for a Japanese YouTube Shorts channel about deep-sea creatures. The two best-performing videos
were driven by ONE unbelievable, concrete fact told in a single line (「5年以上も絶食した」, 「頭も骨もない」).
For EACH species below, using ONLY its listed facts (never invent), write the single most surprising fact as a short hook and
score how strongly it would stop a scrolling viewer (1 = ordinary, 10 = unbelievable). Concrete numbers, missing/strange body
parts and extreme behaviours score high; generic "lives in the deep sea" scores low.
Return JSON only: {{"scores":{{"<id>":{{"score":7,"hook_jp":"日本語で一行(20字以内)","hook_ko":"한국어 한 줄"}}}}}}
# Species
{items}
"""


def _topic_scores(items: list[dict], ask=None) -> dict:
    cache = _load(TOPIC_SCORES, {}) or {}
    todo = [t for t in items if t["ready"] and t["id"] not in cache]
    if todo:
        try:
            txt = "\n".join(f"{t['id']} ({t['sci']} / {t['name_en']}): " + " | ".join(t.get("all_facts") or t["facts"]) for t in todo)
            got = _json_obj((ask or _gemini_text)(_SCORE_PROMPT.format(items=txt))).get("scores") or {}
            for t in todo:
                g = got.get(t["id"]) or {}
                try:
                    sc = max(1, min(10, int(g.get("score"))))
                except (TypeError, ValueError):
                    continue
                cache[t["id"]] = {"score": sc, "hook_jp": str(g.get("hook_jp", ""))[:40], "hook_ko": str(g.get("hook_ko", ""))[:60], "at": _now()}
            _save(TOPIC_SCORES, cache)
        except Exception as e:                               # noqa: BLE001 — 점수가 없어도 주제 목록은 만든다
            print(f"[topics] 놀라움 점수 실패: {e}")
    return cache


def build_topics(fetch=None, ask=None) -> dict:
    """주제 후보 = v1에서 이미 사실(출처 포함)을 모아 둔 심해 종 중 **한 편 = 한 대상** 기준을 통과한 종.
    사진 장수·이야기거리(발견 사건·연도)는 자동으로 판정하지 못한다 → 화면에 '시작 후 확인'으로 정직하게 표시."""
    sys.path.insert(0, str(ROOT))
    from src.categories.deep_sea import data                 # noqa: E402
    from src.core import subject_quality as SQ               # noqa: E402
    have = {p.parent.name for p in PILOTS.glob("*/status.json")}
    out = []
    for key, sp in data.SPECIES.items():
        sci = (sp.get("scientific_name") or "").strip()
        if not sci:
            continue
        pid = re.sub(r"[^a-z0-9]+", "_", sci.lower().replace(" spp.", "")).strip("_")
        facts = [f for f in sp.get("fun_facts") or [] if f]
        ok_subject = SQ.is_specific_enough(sci, sp.get("common_name_en", ""))
        depth = str(sp.get("depth_range_m") or "")
        ko = sp.get("common_name_ko") or ""
        ko_official = bool(ko) and not re.fullmatch(r"[A-Za-z .\-]+", ko)
        if not ko_official:                                 # 정식 한글명이 없으면 지어내지 않고 상위 무리 이름 또는 학명
            ko = KO_GROUP.get(pid) or sci
        out.append({
            "id": pid, "key": key, "name_ko": ko, "ko_official": ko_official, "name_en": sp.get("common_name_en", ""), "sci": sci,
            "depth_m": depth, "facts_n": len(facts), "facts": facts[:3], "all_facts": facts, "sources": sp.get("sources") or [],
            "checks": {"한 편 = 한 대상": ok_subject, "사실 3개 이상": len(facts) >= 3, "서식 수심": bool(depth)},
            "ready": ok_subject and len(facts) >= 3 and bool(depth),
            "in_progress": pid in have,
        })
    media = _topic_media(out, fetch)
    scores = _topic_scores(out, ask)
    for t in out:
        t["photo"] = (media.get(t["id"]) or {}).get("photo")
        sc = scores.get(t["id"]) or {}
        t["score"], t["hook_jp"], t["hook_ko"] = sc.get("score"), sc.get("hook_jp", ""), sc.get("hook_ko", "")
        t.pop("all_facts", None)
    out.sort(key=lambda t: (not t["ready"], t["in_progress"], -(t.get("score") or 0), t["name_ko"]))   # 점수 높은 종부터
    res = {"updated": _now(), "topics": out}
    _save(V2 / "topics.json", res)
    return res


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd, a = argv[0], argv[1:]
    memo = lambda i: " ".join(a[i:]).strip()                 # noqa: E731
    if cmd == "new":
        new_pilot(a[0])
    elif cmd == "approve":
        approve(a[0], a[1], memo(2))
    elif cmd in ("revise", "redo"):
        if cmd == "revise" and not memo(2):
            raise SystemExit("수정 요청에는 무엇을 고칠지 메모가 필요합니다")
        revise(a[0], a[1], memo(2) or "다시 하기 요청", kind=cmd)
    elif cmd == "redo_cut":
        redo_cut(a[0], int(a[1]), memo(2))
    elif cmd == "redo_panel":                                # 콘티 한 칸만 다시 그리기(메모 = 무엇이 틀렸는지)
        redo_panel(a[0], int(a[1]), memo(2))
    elif cmd == "write_script":                              # 대본 자동 작성(메모가 있으면 '수정 요청'으로 반영)
        write_script(a[0], memo(1))
    elif cmd == "stats":                                     # 유튜브 실적 가져오기(편 id 없으면 업로드된 모든 편)
        fetch_stats(a[0] if a and a[0] else None)
    elif cmd == "write_storyboard":                          # 스토리보드 자동(메모 = 수정 요청)
        write_storyboard(a[0], memo(1))
    elif cmd == "make_video":                                # 영상 자동(메모에 'N번'이 있으면 그 컷만)
        make_video(a[0], memo(1))
    elif cmd == "job_start":                                 # 워크플로가 긴 작업 전에 '진행 중'을 먼저 커밋
        set_job(a[0], a[1], "running", memo(2) or "자동 작업 시작", "job_start")
    elif cmd == "job_fail":                                  # 워크플로가 도중에 죽었을 때
        job_fail(a[0], a[1] if len(a) > 1 else "")
    elif cmd == "ready":                                     # 작업(대본·이미지 등)이 끝나 결과가 나왔을 때
        st = load_status(a[0])
        if st["stages"][a[1]]["state"] == "locked":
            raise SystemExit("잠긴 단계는 승인 대기로 바꿀 수 없습니다")
        st["stages"][a[1]]["state"] = "review"
        _note(st, a[1], "ready", memo(2) or "결과 준비됨 — 승인 대기")
        _save(status_path(a[0]), st)
        if a[1] == "script":                                 # 대본이 나오면 승인 전에 자동 교차 검사
            crosscheck(a[0])
    elif cmd == "edit_line":                                 # note = {"jp":..,"ko":..,"tts":..} (JSON)
        d = json.loads(memo(2) or "{}")
        edit_line(a[0], int(a[1]), d.get("jp", ""), d.get("ko", ""), d.get("tts", ""))
    elif cmd == "edit_hook":                                 # note = {"cut":..,"at":..,"question_jp":..,"answer_jp":..} (JSON)
        edit_hook(a[0], json.loads(memo(2)))
    elif cmd == "recut_plan":                                # note = {"direction":..,"min_transitions":..}
        d = json.loads(memo(2) or "{}")
        recut_plan(a[0], int(a[1]), d.get("direction", ""), int(d.get("min_transitions") or 0))
    elif cmd == "recut_approve":
        recut_approve(a[0], int(a[1]))
    elif cmd == "recut_cancel":
        st = load_status(a[0]); _recut_state(st, int(a[1])).update(state="cancelled", at=_now())
        _note(st, "video", "recut_cancel", f"{a[1]}번 컷 수정 취소"); _save(status_path(a[0]), st)
    elif cmd == "upload_meta":
        upload_meta(a[0])
    elif cmd == "save_meta":                                 # note = {"title_jp":..,"desc_jp":..,..}
        save_upload_meta(a[0], json.loads(memo(2) or "{}"))
    elif cmd == "save_viewed":                               # note = {"pct": 18.6, "note": ".."} — 유튜브 스튜디오 '시청함 %'
        save_viewed(a[0], json.loads(memo(2) or "{}"))
    elif cmd == "after_video":                               # 완성본 승인 뒤(버튼 실행 단계 · 키 있음): 시험 릴스 → 판정 뒤 제목·설명
        after_video(a[0])
    elif cmd == "trial_check":                               # 시험 릴스 결과·판정(편 id 가 없으면 진행 중인 모든 편)
        trial_check(a[0] if a and a[0] else None)
    elif cmd == "trial_skip":
        trial_skip(a[0])
    elif cmd == "trial_cancel":                              # 시험 무효(예: 다른 계정에 올라감) — 메모 = 이유
        trial_cancel(a[0], memo(1))
    elif cmd == "trial_repost":                              # 무효가 된 시험을 ABYSS 계정에 다시 올리기
        trial_repost(a[0])
    elif cmd == "ig_probe":
        ig_probe()
    elif cmd == "crosscheck":
        crosscheck(a[0])
    elif cmd == "apply_lines":
        apply_lines(a[0])
    elif cmd == "sync":                                      # 컷 목록 새로 만들기(script.json → status)
        st = load_status(a[0]); _sync_script_artifacts(st, _load(_script_path(a[0]))); _save(status_path(a[0]), st)
    elif cmd == "assemble":
        assemble(a[0])
    elif cmd == "topics":
        build_topics()
        return 0
    elif cmd == "index":
        pass
    else:
        raise SystemExit(f"모르는 명령: {cmd}")
    build_index()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
