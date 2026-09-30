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
  python admin.py job_start <id> <stage> [설명]  # 자동 작업 '진행 중' 기록(워크플로가 긴 작업 전에 먼저 커밋)
  python admin.py job_fail <id> <action>        # 워크플로가 중간에 죽으면 진행 중 기록을 '실패'로
  python admin.py ready <id> <stage> [메모]      # 작업 결과가 나왔음 → 승인 대기로
  python admin.py edit_line <id> <컷> '<json>'   # 컷 대사 수정(대본만 · 영상은 안 바뀜)
  python admin.py apply_lines <id>              # 수정한 대사를 영상에 반영(나레이션 다시 읽기 + 재조립만)
  python admin.py edit_hook <id> _ '<json>'     # 후킹 질문·정답·발췌 컷 수정(대본만 · 영상은 재조립 때 반영)
  python admin.py crosscheck <id>               # AI 교차 검사(대본 전체 × 사실 전체 — 모순·범위·근거 없음)
  python admin.py recut_plan <id> <컷> '<json>'  # 컷 수정 방향 → 샷 계획 + 콘티(영상은 안 만듦)
  python admin.py recut_approve <id> <컷>        # 콘티 승인 → 샷별 영상 → 한 컷 합성 → 재조립
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
    if stage == "video":                                    # 완성본 승인 → 유튜브 제목·설명·해시태그 자동 작성
        try:
            upload_meta(pid)
        except Exception as e:                               # noqa: BLE001 — 실패해도 승인은 유지, 버튼으로 다시
            st = load_status(pid)
            _note(st, "upload", "error", f"제목·설명 자동 작성 실패 — 「AI로 다시 쓰기」를 눌러 주세요: {str(e)[:120]}")
            _save(status_path(pid), st)
        st = load_status(pid)
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
    ending = "" if sc.get("hook") else str(pilot / asm["ending"])   # ★후킹 편은 공용 엔딩 대신 [후킹][본편][정답 카드]
    dst.parent.mkdir(parents=True, exist_ok=True)           # 빈 폴더는 git에 안 남아 로컬 재조립 때 없을 수 있다(실측 ffmpeg 254)
    A.main(str(pilot), asm["clips_id"], asm["tts_id"], ending, str(dst), overrides=over)
    st = load_status(pid)
    a = st["artifacts"]["video"]
    st["artifacts"].get("script", {}).pop("hook_pending", None)
    tmv = (sc.get("timing_v5") or [])
    body_s = sum(min(float(t["sec"]), float(t.get("lead", 0.15)) + float(t.get("speech_s") or t["sec"]) + A.TAIL_S) for t in tmv) \
        or sum(float(c.get("sec") or 0) for c in a.get("clips", []))
    st["checks"] = auto_checks(dst, body_s=body_s)
    st["checks"]["subtitle_font"] = {"ok": True, "value": font["font_file"],
                                     "rule": "자막 글꼴이 실제로 그려질 것(네모 □ 금지) — 조립 직전 이 서버에서 검사"}
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
    for k in ("question_jp", "question_ko", "answer_jp", "answer_ko"):
        if k in data and str(data[k]).strip():
            hk[k] = str(data[k]).strip()
    if data.get("cut"):
        hk["cut"] = int(data["cut"])
    if data.get("at") not in (None, ""):
        hk["at"] = round(float(data["at"]), 2)
    probs = validate_hook(hk, cuts, sc.get("facts", []))
    if probs:
        raise SystemExit("후킹 검사 불통과: " + " / ".join(probs))
    sec = float(cuts[int(hk["cut"]) - 1].get("sec") or 0)
    hk["at"] = round(max(0.0, min(float(hk.get("at") or 0.0), max(0.0, sec - HOOK_S))), 2)
    sc.setdefault("hook_history", []).append({"at": _now(), "hook": sc["hook"]})
    sc["hook"] = hk
    _save(_script_path(pid), sc)
    _sync_script_artifacts(st, sc)
    if (st["artifacts"].get("video") or {}).get("final"):
        st["artifacts"]["script"]["hook_pending"] = True         # 영상엔 아직 미반영 — 재조립 필요
        _note(st, "video", "hook", "후킹·정답 문구 수정됨 — 「완성본 다시 조립」을 누르면 반영(무료)")
    _note(st, "script", "hook", f"후킹 수정: {hk['cut']}번 컷 {hk['at']}초 「{hk['question_jp']}」 → 正解 {hk['answer_jp']}")
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
_OMNI_HEAD = ("Vertical 9:16 video, exactly {dur} seconds, one continuous shot, no cuts. Handcrafted miniature diorama "
              "photography, tilt-shift shallow depth of field, warm soft practical light. The attached image is the FIRST FRAME: "
              "keep every object's shape, size, colour and position consistent with it. The giant isopod (whenever visible) "
              "keeps its exact anatomy and size.\n")
_OMNI_TAIL = ("\nSOUND: none needed (it will be replaced). No music. No dialogue.\nNEVER SHOW: text, letters, numbers, symbols, "
              "labels, logos, watermarks; real human hands, fingers or people; extra or different creatures; the isopod growing, "
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
Rules: title_jp = hook-style Japanese title, max 28 characters, mystery/awe tone, no honorific needed, no hashtags,
no "#Shorts", no episode numbers, NO office-worker jokes (有給/残業/上司 etc.), never exaggerate beyond the facts.
desc_jp = 3-4 short sentences in polite Japanese (です・ます), summarising the story with the concrete facts.
title_ko / desc_ko = natural Korean versions (존댓말 for desc). Return JSON only:
{{"title_jp":"...","title_ko":"...","desc_jp":"...","desc_ko":"..."}}
# Species
{name_jp} / {name_ko} / {sci}
# Narration (by cut)
{cuts}
# Facts
{facts}
"""


def _compose_meta(sc: dict, gen: dict) -> dict:
    sub = sc.get("subject", {})
    tj, tk = "#" + sub.get("jp_name", "").replace(" ", ""), "#" + sub.get("ko_name", "").replace(" ", "")
    tags_jp, tags_ko = [tj, "#深海"], [tk, "#심해"]
    srcs = sorted({u for f in sc.get("facts", []) for u in f.get("sources", [])})
    def desc(body, cta, repro, tags, head):
        return (body.strip() + "\n\n" + cta + "\n\n" + repro + "\n" + head + "\n" + "\n".join(srcs)
                + "\n\n" + " ".join(tags)).strip()
    return {
        "title_jp": (gen["title_jp"].strip() + " " + " ".join(tags_jp))[:100],
        "title_ko": (gen["title_ko"].strip() + " " + " ".join(tags_ko))[:100],
        "desc_jp": desc(gen["desc_jp"], _CTA_JP, _REPRO_JP, tags_jp, "出典:"),
        "desc_ko": desc(gen["desc_ko"], _CTA_KO, _REPRO_KO, tags_ko, "출처:"),
        "tags_jp": tags_jp, "tags_ko": tags_ko, "pinned_comment": PINNED_COMMENT, "privacy": "private", "category": "15",
    }


YT_CATEGORIES = {"15": "반려동물/동물", "28": "과학기술", "27": "교육"}   # 유튜브 카테고리 번호(명시해서 보낸다)
_STALE = re.compile(r"有給|残業|定時|上司|出社|유급|야근|상사|출근|퇴근|직장인")


def upload_meta(pid: str, ask=None) -> dict:
    st = load_status(pid)
    sc = _load(_script_path(pid))
    sub = sc.get("subject", {})
    prompt = _META_PROMPT.format(
        name_jp=sub.get("jp_name", ""), name_ko=sub.get("ko_name", ""), sci=sub.get("scientific_name", ""),
        cuts="\n".join(f"{c['cut']}: {c['jp']}" for c in sc["cuts"] if "tts" in c),
        facts="\n".join(f"{f['id']}: {f['fact']}" for f in sc.get("facts", [])))
    gen = json.loads(re.search(r"\{.*\}", (ask or _gemini_text)(prompt), re.S).group(0))
    for k in ("title_jp", "title_ko", "desc_jp", "desc_ko"):
        if not str(gen.get(k, "")).strip():
            raise ValueError(f"{k} 비어 있음")
    if _STALE.search(gen["title_jp"] + gen["title_ko"]):
        raise ValueError("제목에 금지된 회사원 소재가 들어갔습니다 — 다시 쓰기")
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


def save_upload_meta(pid: str, data: dict) -> dict:
    st = load_status(pid)
    up = st.setdefault("artifacts", {}).setdefault("upload", {})
    if (up.get("result") or {}).get("url"):
        raise SystemExit("이미 업로드했습니다 — 제목·설명은 유튜브 스튜디오에서 고쳐 주세요")
    m = up.setdefault("meta", {})
    for k in ("title_jp", "title_ko", "desc_jp", "desc_ko", "pinned_comment", "privacy", "category"):
        if k in data:
            m[k] = str(data[k]).strip()
    if m.get("privacy") not in ("private", "unlisted", "public"):
        m["privacy"] = "private"
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


def youtube_upload(pid: str, uploader=None) -> dict:
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
    tags = [t.lstrip("#") for t in m.get("tags_jp", [])]
    try:
        r = uploader(str(video), m["title_jp"], m.get("desc_jp", ""), tags=tags, privacy=m.get("privacy", "private"),
                     category_id=m.get("category") or "15")
    except Exception as e:                                   # noqa: BLE001
        _note(st, "upload", "error", f"유튜브 업로드 실패: {str(e)[:160]}")
        _save(status_path(pid), st)
        raise SystemExit(f"유튜브 업로드 실패: {e}")
    up["result"] = {"url": r["url"], "video_id": r.get("video_id", ""), "privacy": r.get("privacy", ""),
                    "category": m.get("category") or "15", "at": _now()}
    _note(st, "upload", "uploaded", f"유튜브 업로드 완료({r.get('privacy', '')}): {r['url']} — 고정 댓글은 유튜브 앱에서 직접 달고 고정")
    _save(status_path(pid), st)
    return st


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
- 1カット目: 思わず手が止まる場面や問いから始める。発見の年・場所・人の出来事が事実リストにあれば、そこから物語として始める。
- 前提から親切に。専門用語はやさしく言い換える。
- 同じ単語・言い回しを何度も繰り返さない。文末も単調にしない。
- {n}カット目: 余韻のある締め(画面は暗闇に消えていく)。「チャンネル登録」「コメント」などの呼びかけは書かない(共通エンディングが別にある)。
- 呼び名: {name_rule}
- hook(冒頭2秒の引き): 台本の中で**いちばん驚く場面のカット番号**を選び、その場面を見せながら出す短い問い
  「〇〇する、この生き物は？」(8〜22文字・「？」で終わる・答えの名前は入れない・事実リストにある行動だけ)。
  answer_jp は最後の「正解：〇〇」に入れる呼び名(台本で使った呼び名と同じ)。
  ★正体当てなので、その呼び名(answer_jp)は**カット1・2には出さず**、3カット目以降で初めて明かす(冒頭で答えを言わない)。
{feedback}
# 出力(JSONのみ)
{{"cuts":[{{"cut":1,"jp":"日本語の台詞","ko":"자연스러운 한국어 번역","fact":"F1,F3",
"scene_ko":"이 컷의 화면 아이디어(미니어처 디오라마 · 한국어 한 줄)","annotation":"画面の赤い注釈(短く・数字は事実どおり・なければ空)"}}],
"hook":{{"cut":3,"question_jp":"皮を脱ぎ捨てる、この生き物は？","question_ko":"한국어 번역","answer_jp":"呼び名","answer_ko":"한국어 이름"}}}}

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
        if not re.search(r"[가-힣]", ko):
            probs.append(f"カット{i}: 韓国語訳(ko)がありません。")
        if not 12 <= len(jp) <= 50:
            probs.append(f"カット{i}: {len(jp)}文字です。18〜44文字にしてください。")
        if _CTA_WORDS.search(jp):
            probs.append(f"カット{i}: 呼びかけ(登録・コメント等)は書かないでください。")
        allowed = set().union(*[_nums(by[x]["fact"] + " " + by[x].get("fact_jp", "") + " " + by[x]["quote"]) for x in ids if x in by]) if ids else set()
        bad = sorted((_nums(jp) | _nums(str(c.get("annotation", "")))) - allowed)
        if bad:
            probs.append(f"カット{i}: 根拠の事実にない数字 {', '.join(bad)} があります。事実どおりにするか削ってください。")
        total += estimate_speech(auto_reading(jp)) if jp else 0
    if total > SPEECH_MAX_S:
        probs.append(f"全体が長すぎます(約{total:.0f}秒)。合計{SPEECH_MAX_S:.0f}秒以内(約300文字以内)に短くしてください。")
    return probs


def validate_hook(hook: dict | None, cuts: list[dict], facts: list[dict]) -> list[str]:
    """후킹(맨 앞 2초 질문 + 마지막 정답) 코드 검사 — 불통과 이유 목록."""
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
        probs.append(f"呼び名「{a}」がカット1〜2に出ています。正体当てなので3カット目以降で初めて明かしてください。")
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
        name_rule = (f"和名「{ja_name}」を使う。" if ja_name else
                     f"和名がないので、事実リストにある呼び名(英名「{topic.get('name_en', '')}」の直訳など)か「この生き物」と呼ぶ。和名を作らない。")
        ftxt = "\n".join(f"{f['id']}: {f.get('fact_jp') or f['fact']}(出典原文: {f.get('quote', '')})" for f in facts)
        fb, cuts, probs = "", [], []
        if feedback:
            prev = "\n".join(f"カット{c['cut']}: {c['jp']}" for c in old.get("cuts", []) if c.get("jp"))
            fb = f"# 運営者の修正依頼(必ず反映)\n{feedback}\n# 前の台本\n{prev}\n"
        hook = None
        for attempt in range(3):
            gen = _json_obj(ask_script(_SCRIPT_PROMPT.format(name=name, n=SCRIPT_CUTS, name_rule=name_rule, feedback=fb, facts=ftxt)))
            cuts, hook = gen.get("cuts") or [], gen.get("hook")
            probs = validate_script(cuts, facts) + validate_hook(hook, cuts, facts)
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
        sc = {"episode": pid, "subject": {"scientific_name": topic.get("sci", ""), "jp_name": ja_name or "",
                                          "ko_name": st.get("name_ko", "")},
              # ★후킹(운영자 확정 2026-09-30): 맨 앞 2초 = 본편 hk_cut 컷에서 그대로 발췌 + 빨간 질문 · 맨 뒤 = 정답 카드
              "hook": {"cut": hk_cut, "at": None, "question_jp": str(hook["question_jp"]).strip(),
                       "question_ko": str(hook.get("question_ko", "")).strip(), "answer_jp": str(hook["answer_jp"]).strip(),
                       "answer_ko": str(hook.get("answer_ko", "")).strip()},
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
        sc["hook"]["at"] = round(max(0.0, hsec / 2 - HOOK_S / 2), 2)      # 발췌 시작 = 컷 한가운데 2초(운영자가 고칠 수 있음)
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
_MINI_STYLE = ("handcrafted miniature / scale-model photography, strong tilt-shift shallow depth of field, warm soft practical "
               "lighting, muted grey-green and brown palette; everything except the creature is a deliberately rough, simple, "
               "hand-made model (chunky clay, wood, foam, paper textures)")
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

_SB_PROMPT = """You are the storyboard artist of a Japanese science YouTube Short made as a handcrafted MINIATURE DIORAMA
({style}). The creature is the ONLY precise object; its anatomy is fixed: {anatomy}
Plan ONE storyboard panel (the first frame of the video clip) for EACH of the {n} cuts below. HARD RULES:
- Each panel is a different stage or camera angle; never two consecutive cuts on the same set; cross-section "box" sets at most 2.
- Show exactly what that cut's narration says; do not invent facts. When the narration mentions a body part, frame that part close.
- Never place the creature next to boats, people, furniture or other props that would make it look giant; no size-misleading props.
- NEVER text, letters, numbers, labels, arrows, logos in the image. No real human hands or people. No other animals unless the
  narration says so. Keep the upper quarter of every panel calm and uncluttered (captions go there).
- The LAST cut's panel: the creature is already dim and receding into deep darkness (the video will fade to black).
- Cut {hook_cut} is used as the 2-second opening hook — make it the most striking, dynamic composition.
{feedback}
Return JSON only: {{"panels":{{"1":"English description of panel 1 (set, camera angle, creature pose, light, props)", "2":"..."}}}}
# Cuts (Japanese narration / Korean / scene idea / seconds)
{cuts}
# Facts
{facts}
"""

_VID_PROMPT = """You write per-second TIMELINE video prompts (English) for Gemini Omni Flash, one per cut, for a Japanese science
YouTube Short in a handcrafted MINIATURE DIORAMA style ({style}). The attached storyboard panel is each cut's FIRST FRAME.
The creature's anatomy is fixed and must never change: {anatomy}
HARD RULES for every cut:
- One continuous shot, exactly the cut's duration. Split it into 2-4 time ranges "0.0–2.0s ..." and for EACH range state
  camera position/move, what the creature does, what is and is not visible. Put visual changes at the narration boundaries given.
- Motion must be concrete (what moves from where to where). Slow, observational camera; no fast pans, no morphing.
- Never invent facts beyond the narration. No text, letters, numbers, symbols, logos. No real human hands or people.
- Cut {last}: the creature drifts away into deep darkness and the frame goes almost black by the end (episode ending).
{feedback}
Return JSON only: {{"prompts":{{"1":"TIMELINE text for cut 1","2":"..."}}}}
# Cuts (seconds / narration JP / KO / narration chunk timings / panel description)
{cuts}
"""

_CARD_PROMPT_HEAD = ("A single hand-crafted museum-grade miniature replica of {sci}, photographed as a macro studio shot. "
                     "The creature must be extremely detailed and anatomically faithful to the attached real reference photos: "
                     "{anatomy} Resin figure with subtle hand-painted texture, shallow depth of field (tilt-shift macro), warm soft "
                     "studio light, plain neutral mid-grey seamless backdrop. Exactly one animal, fully inside the frame. "
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
                  "checklist": checklist, "check": check, "refs": refs,
                  "use_as_reference": [{"file": c, "role": "생물 카드(자동)"} for c in cards] + [{"file": refs[0]["file"], "role": "실사 기준"}],
                  "compare": f"out/{rid}/compare.jpg" if compare else None}
            _save(pilot / "creature_card.json", cc)
            st = load_status(pid)
            st.setdefault("cost", {}).setdefault("spent", []).append({"at": _now(), "what": "생물 카드 2장", "usd": round(IMG_USD * 2, 3)})
            _save(status_path(pid), st)
        anatomy = cc["anatomy"]
        refs_for = [r["file"] for r in cc.get("use_as_reference", [])][:3]
        # 8컷 콘티 계획(AI) → 2×2 격자 2장
        hook_cut = int((sc.get("hook") or {}).get("cut") or 1)
        ctxt = "\n".join(f"Cut {c['cut']} ({c.get('sec', '')}s): JP「{c['jp']}」 / KO「{c.get('ko', '')}」 / scene: {c.get('scene_ko', '')}" for c in cuts)
        fb = f"# Operator's revision request (must apply)\n{feedback}\n" if feedback else ""
        plan = _json_obj((ask if ask else (lambda p: _gemini_text(p, temperature=0.5)))(
            _SB_PROMPT.format(style=_MINI_STYLE, anatomy=anatomy, n=len(cuts), hook_cut=hook_cut, feedback=fb, cuts=ctxt, facts=ftxt)))
        panels = {int(k): str(v) for k, v in (plan.get("panels") or {}).items() if str(k).isdigit()}
        missing = [c["cut"] for c in cuts if c["cut"] not in panels or len(panels[c["cut"]]) < 20]
        if missing:
            raise RuntimeError(f"콘티 설명이 빠진 컷: {missing}")
        rid = _rid("sb")
        head = _GRID_HEAD_GENERIC.format(style=_MINI_STYLE, anatomy=anatomy, forbidden=cc.get("forbidden", ""))
        items = []
        for g in range(0, len(cuts), 4):
            grp = cuts[g:g + 4]
            names = [f"p{c['cut']:02d}" for c in grp] + [""] * (4 - len(grp))
            body = "\n".join(f"Panel {i + 1} ({pos}): {panels[c['cut']]}" for i, (c, pos) in enumerate(zip(grp, ("top-left", "top-right", "bottom-left", "bottom-right"))))
            items.append({"name": f"grid{g // 4 + 1}", "aspect": "9:16", "size": "2K", "refs": refs_for, "prompt": head + body,
                          "split": {"rows": 2, "cols": 2, "names": names}})
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
            c["panel_desc"] = panels[c["cut"]]
        sheet = _tile(pfiles, pilot / "out" / rid / "storyboard.jpg", cols=4)
        sc.setdefault("storyboard_history", []).append({"at": _now(), "rid": rid, "feedback": feedback})
        _save(_script_path(pid), sc)
        st = load_status(pid)
        st["artifacts"]["storyboard"] = {"sheet": f"out/{rid}/storyboard.jpg" if sheet else None, "request": rid,
                                         "card": [r["file"] for r in cc.get("use_as_reference", [])],
                                         "compare": cc.get("compare"), "card_check": cc.get("check"), "checklist": cc.get("checklist"),
                                         "panels": [{"cut": c["cut"], "file": c["keyframe"], "desc": c["panel_desc"]} for c in cuts]}
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
                      "below. Shared look for all panels: {style}. The creature must match the attached replica and real reference images "
                      "exactly and be identical in every panel: {anatomy} {forbidden} Never place the creature next to boats, people or "
                      "furniture that would make it look giant. Keep the upper quarter of every panel calm and uncluttered. NEVER draw text, "
                      "letters, numbers, labels, arrows, logos, watermarks. No human hands or real people anywhere.\n")


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
        if targets:
            def chunks_txt(c):
                segs = _chunks(c["jp"])
                tps = tm[c["cut"]].get("local_tps") or []
                return "; ".join(f"{t['start']:.1f}-{t['end']:.1f}s「{s}」" for s, t in zip(segs, tps)) if tps else "(no timing)"
            ctxt = "\n".join(f"Cut {c['cut']} ({tm[c['cut']]['sec']}s): JP「{c['jp']}」 / KO「{c.get('ko', '')}」 / narration: {chunks_txt(c)} / panel: {c.get('panel_desc', '')}"
                             for c in targets)
            fb = f"# Operator's revision request (must apply)\n{feedback}\n" if feedback else ""
            plan = _json_obj((ask if ask else (lambda p: _gemini_text(p, temperature=0.4)))(
                _VID_PROMPT.format(style=_MINI_STYLE, anatomy=anatomy, last=cuts[-1]["cut"], feedback=fb, cuts=ctxt)))
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
                                        "clips": [{"cut": c["cut"], "file": prev_clips[c["cut"]], "sec": tm[c["cut"]]["sec"]} for c in cuts if c["cut"] in prev_clips]}
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
def build_index() -> dict:
    items = []
    for p in sorted(PILOTS.glob("*/status.json")):
        st = _load(p, {})
        if not st:
            continue
        cur = next((s for s in STAGES if st["stages"][s]["state"] != "approved"), "done")
        items.append({"id": st["id"], "name_ko": st.get("name_ko", ""), "sci": st.get("sci", ""),
                      "stage": cur, "state": st["stages"][cur]["state"] if cur != "done" else "approved",
                      "job": (st.get("jobs") or {}).get(cur), "created": st.get("created", "")})
    idx = {"updated": _now(), "items": items}
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


def build_topics(fetch=None) -> dict:
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
            "depth_m": depth, "facts_n": len(facts), "facts": facts[:3], "sources": sp.get("sources") or [],
            "checks": {"한 편 = 한 대상": ok_subject, "사실 3개 이상": len(facts) >= 3, "서식 수심": bool(depth)},
            "ready": ok_subject and len(facts) >= 3 and bool(depth),
            "in_progress": pid in have,
        })
    out.sort(key=lambda t: (not t["ready"], t["in_progress"], t["name_ko"]))
    media = _topic_media(out, fetch)
    for t in out:
        t["photo"] = (media.get(t["id"]) or {}).get("photo")
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
    elif cmd == "write_script":                              # 대본 자동 작성(메모가 있으면 '수정 요청'으로 반영)
        write_script(a[0], memo(1))
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
