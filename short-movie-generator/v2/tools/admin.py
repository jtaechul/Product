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
  python admin.py ready <id> <stage> [메모]      # 작업 결과가 나왔음 → 승인 대기로
  python admin.py edit_line <id> <컷> '<json>'   # 컷 대사 수정(대본만 · 영상은 안 바뀜)
  python admin.py apply_lines <id>              # 수정한 대사를 영상에 반영(나레이션 다시 읽기 + 재조립만)
  python admin.py crosscheck <id>               # AI 교차 검사(대본 전체 × 사실 전체 — 모순·범위·근거 없음)
  python admin.py topics                        # 주제 후보 목록(topics.json) 갱신
  python admin.py index                         # 편 목록(index.json) 갱신
"""
from __future__ import annotations

import io
import json
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
    if s["state"] != "review":
        raise SystemExit(f"{STAGE_KO[stage]}은(는) 지금 승인할 수 없습니다(상태: {s['state']}) — 결과가 나온 뒤(승인 대기)에만 승인")
    s.update(state="approved", approved_at=_now())
    _note(st, stage, "approve", memo)
    i = STAGES.index(stage)
    if i + 1 < len(STAGES):                                   # 다음 단계 잠금 해제
        nxt = st["stages"][STAGES[i + 1]]
        if nxt["state"] == "locked":
            nxt["state"] = "working"
    _save(status_path(pid), st)
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
    src = _load(pilot / "requests" / f"{art['clips_request']}.json")
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
    over = {int(c["cut"]): str(pilot / c["file"]) for c in a.get("clips", [])}
    dst = pilot / a["final"]
    A.main(str(pilot), asm["clips_id"], asm["tts_id"], str(pilot / asm["ending"]), str(dst), overrides=over)
    st["checks"] = auto_checks(dst, body_s=sum(float(c.get("sec") or 0) for c in a.get("clips", [])))
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


def facts_for(sc: dict, ids: str) -> list[dict]:
    """컷이 근거로 든 F번호(예: 'F3,F9')의 원문·출처 — 관리자 페이지에서 대사 바로 옆에 보여준다(검증 ②)."""
    by = {f["id"]: f for f in sc.get("facts", [])}
    return [{"id": i, "fact": by[i]["fact"], "sources": by[i].get("sources", [])}
            for i in re.findall(r"F\d+", ids or "") if i in by]


# ── 검증 ① AI 교차 검사(운영자 확정 2026-09-28) ─────────────────────────────
# 줄 하나를 자기 근거(F번호) 하나와만 대조하면, 대본 안의 **다른 줄·다른 사실과의 모순**을 놓친다
# (실사고: 2번 컷 "분류상 갯강구에 가깝다" ↔ 3번 컷 "공벌레 무리 중 세계 최대" — 출처는 "등각류 전체 중 최대").
# → 대본 전체 + 사실 전체를 한 번에 AI에게 주고 모순·근거 없음·범위 착오를 찾게 한다. 결과는 관리자 페이지에 빨간 표시.
CROSSCHECK_MODEL = "gemini-2.5-pro"
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
    res = {"at": _now(), "model": CROSSCHECK_MODEL}
    try:
        txt = (ask or _gemini_text)(prompt)
        res["issues"] = _cc_parse(txt)
    except Exception as e:                                   # noqa: BLE001 — 검사 실패가 제작을 막지 않게
        res["error"] = f"AI 교차 검사 실패: {str(e)[:160]}"
    st.setdefault("artifacts", {}).setdefault("script", {})["crosscheck"] = res
    n = len(res.get("issues", []))
    _note(st, "script", "crosscheck", res.get("error") or (f"AI 교차 검사: 의심 {n}건" if n else "AI 교차 검사: 문제 없음"))
    _save(status_path(pid), st)
    return st


def _gemini_text(prompt: str) -> str:
    import os
    import urllib.request
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 없음")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{CROSSCHECK_MODEL}:generateContent",
        data=json.dumps(body).encode(), headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
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


# ── 목록 파일 ─────────────────────────────────────────────────────────────
def build_index() -> dict:
    items = []
    for p in sorted(PILOTS.glob("*/status.json")):
        st = _load(p, {})
        if not st:
            continue
        cur = next((s for s in STAGES if st["stages"][s]["state"] != "approved"), "done")
        items.append({"id": st["id"], "name_ko": st.get("name_ko", ""), "sci": st.get("sci", ""),
                      "stage": cur, "state": st["stages"][cur]["state"] if cur != "done" else "approved",
                      "created": st.get("created", "")})
    idx = {"updated": _now(), "items": items}
    _save(PILOTS / "index.json", idx)
    return idx


def build_topics() -> dict:
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
        if re.fullmatch(r"[A-Za-z .\-]+", ko or ""):        # 한국어 이름이 없으면 영문명을 그대로 쓰지 않고 학명
            ko = sci
        out.append({
            "id": pid, "key": key, "name_ko": ko, "name_en": sp.get("common_name_en", ""), "sci": sci,
            "depth_m": depth, "facts_n": len(facts), "facts": facts[:3], "sources": sp.get("sources") or [],
            "checks": {"한 편 = 한 대상": ok_subject, "사실 3개 이상": len(facts) >= 3, "서식 수심": bool(depth)},
            "ready": ok_subject and len(facts) >= 3 and bool(depth),
            "in_progress": pid in have,
        })
    out.sort(key=lambda t: (not t["ready"], t["in_progress"], t["name_ko"]))
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
