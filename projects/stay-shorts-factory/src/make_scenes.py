"""v7 씬 스토리보드 — 한 이미지에 여러 씬 (2026-10-18).

운영자: "숙소 내외부 분석을 끝내고 그 이미지를 바탕으로 AI 로 대본에 맞는 씬별 스토리보드와 영상을 만들어야지, 기존 이미지로 줌인·줌아웃만 하는
영상을 누가 보겠나" → C안(스토리보드 → 확인 → 사람·강아지 씬만 Veo) + "스토리보드는 이미지 한 장에 여러 씬이 들어가게 만들어, 돈 좀 아껴".

흐름(미리보기 = 스토리보드 단계):
  대본 문장 → 컷(v6 동선) → 씬(컷마다: 장소의 실제 사진 + 누가(뒷모습 커플·강아지·손·없음) + 동작 + 시간대)
  → 참조 사진별로 **2×2 시트 한 장**(9:16 패널 4개 — 시트 전체도 9:16 · 이미지 1장 값 ≈ 98원, 2K 요청)
  → 패널 분할(흰 구분선 또는 고정 격자) → 패널 구조 검수(비전 1회/시트 · 같은 공간·새 사물·사람 수·얼굴·글자)
  → 통과한 패널이 그 컷의 화면(스틸 무빙) · 제작 때 사람·강아지 씬은 그 패널을 Veo 시작 장면으로.
규칙: 씬은 그 장소의 실제 사진 위에만(사진 없는 장소 금지) · 가구·창·전망은 그대로, 사람·강아지·빛·시간대만 바꾼다 · 사람은 끝까지 뒷모습 ·
     탈락한 패널은 원본 사진으로 되돌아간다(값은 이미 나감) · 화면에 'AI 연출' 표시(기존).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageDraw

import design
import make_mini as mm
import make_sig as sg
import make_stay as ms
import photos
import veo

FAKE = os.environ.get("SCENE_FAKE_IMAGE", "") == "1"                     # 로컬 시험: 시트 대신 원본에 색을 입힌 가짜 2×2(0원)
FAKE_CHECK: dict = {}                                                      # 시험용: {씬 번호: "fail 이유"} — 가짜 검수 탈락
GRID = (2, 2)                                                              # 시트 = 2열 × 2행 = 패널 4개(9:16) → 시트 전체 9:16
SHEET_SIZE = os.environ.get("SCENE_SHEET_SIZE", "2K")                     # 2K 면 패널 짧은 변 ≈ 768px(Veo 입력 720 이상) · 1K 로 떨어지면 ≈ 384px
SHEET_KRW_MULT = float(os.environ.get("SCENE_SHEET_MULT", "1.0"))          # 2K 단가가 1K 와 다르면 여기로(공식 가격표 미확인 · 장부는 토큰으로도 남는다)
PANEL_FULL, PANEL_MIN = 640, 400                                           # 패널 짧은 변: 이 이상이면 일반 컷·Veo 시작 장면 / 400~639 는 짧은 컷만 / 그 밑은 버림
MAX_SHEETS = 6
TIMES = {"day": "bright natural daylight", "golden": "warm late-afternoon golden light through the window",
         "evening": "dusk — the lamps are on and it is getting dark outside", "night": "night — lamps on, dark outside",
         "morning": "soft early-morning light"}
TIME_KO = {"day": "낮", "golden": "해 질 녘", "evening": "저녁", "night": "밤", "morning": "아침"}
WHO_EN = {"couple": "an adult couple in white hotel bathrobes seen strictly from behind (backs of their heads and shoulders; faces never visible), realistic adult size for the furniture",
          "back": "one adult in a white hotel bathrobe seen strictly from behind (face never visible), realistic size",
          "hand": "only one adult hand and forearm reaching in from the bottom edge of the panel, nothing else of the person",
          "dog": "a real small cream-white toy poodle with a coral-red collar, true small-dog size", "env": "", "none": ""}
WHO_KO = {"couple": "뒷모습 커플", "back": "뒷모습 한 사람", "hand": "손", "dog": "강아지", "env": "사람 없음", "none": "사람 없음"}
DOG_EXTRA = " The same small cream-white toy poodle with a coral-red collar is with them."
SHEET_PROMPT = """You are given one real hotel photograph (attached). Create ONE image that is a 2x2 storyboard grid: four vertical 9:16 panels of equal size, arranged top-left, top-right, bottom-left, bottom-right, separated by thin plain white gutters.
Every panel shows THIS EXACT space from the same camera position as the photograph: the same walls, windows, floor, furniture, objects, decorations and the same view outside. Do not add, remove, move or redesign any furniture, fixture, pool, railing or plant. No text, numbers, captions, logos or watermarks anywhere. Photorealistic, like frames taken from one video in this room. Only the light, the time of day and the requested people or dog differ between panels.
Panels:
{panels}
Rules for people: only seen from behind, faces never visible, no eye contact with the camera, realistic adult size, no phones, cups or new objects in their hands. Nobody else appears. If a panel says "no people", it must contain no person and no animal."""
CHECK_SYSTEM = """너는 숙소 AI 스토리보드 검수자다. 이미지 1 = 실제 숙소 사진(원본). 이미지 2~5 = AI 가 같은 공간의 다른 순간을 그린 패널(차례로 패널 1~4).
패널마다 엄격하게: same_place(원본과 같은 공간·같은 가구·창·바닥·전망인가), structure_changes(벽·창·가구·수영장·난간·전망 중 원본과 달라진 것 목록),
added_objects(원본에 없던 사물·시설·장식 — 사람·강아지·조명 변화·빛은 제외), people(사람 수 · 손·팔만 보이면 "hand"), face_visible(눈·코·입이 보이는 얼굴이 있는가),
dogs(강아지 수), text(글자·번호·로고가 있는가), looks_real(실사처럼 자연스러운가 — 사람·강아지 몸·손가락이 이상하면 false).
JSON 만: {"panels":[{"n":1,"same_place":true,"structure_changes":[],"added_objects":[],"people":0,"face_visible":false,"dogs":0,"text":false,"looks_real":true,"why":"한 줄"}]}"""


def log(*a):
    print("[scenes]", *a, flush=True)


# ── 1. 씬 계획(0원) ─────────────────────────────────────────────────────────────────
def plan_scenes(beats: list[dict], shots: dict, dog: bool, report: dict) -> list[dict]:
    """컷마다 씬 하나: 그 컷의 사진(장소) + 누가·동작(화면 계획의 actor) + 시간대(하루 흐름 — 앞은 낮, 뒤로 갈수록 저녁·밤).
    훅이 실제 강아지 사진이면(hook_keep) 원본 그대로, 제안(R)은 훅 재사용이라 씬 없음."""
    n = len(beats)
    scenes: list[dict] = []
    order = ["day", "golden", "evening", "night"]
    for j, b in enumerate(beats):
        v = b.get("visual") or {}
        if v.get("type") == "R" or (j == 0 and b.get("hook_keep")):
            continue
        base_t = order[min(len(order) - 1, int(j * len(order) / max(1, n - 1)))] if n > 1 else "day"
        for m, sid in enumerate(b.get("shots") or []):
            if sid not in shots:
                continue
            s = shots[sid]
            who, act, with_dog = "env", "", False
            if m == 0 and v.get("actor") in ("couple", "back", "hand", "dog"):
                who, act, with_dog = v["actor"], str(v.get("action_en") or ""), bool(v.get("with_dog"))
            t = base_t if m == 0 else order[(order.index(base_t) + 1) % len(order)]
            if who == "dog" and not dog:
                who, act = "env", ""
            scenes.append({"n": len(scenes) + 1, "j": j, "m": m, "sid": sid, "k": s["k"], "place": s.get("place") or "", "who": who, "with_dog": with_dog,
                           "action_en": act[:200], "time": t, "src_img": s["img"], "img": None, "ok": None, "why": "", "panel_px": 0, "sheet": None})
    report["scenes_planned"] = len(scenes)
    return scenes


def _panel_text(i: int, sc: dict) -> str:
    who = WHO_EN.get(sc["who"], "")
    if sc["who"] in ("env", "none") or not who:
        body = "no people, no animals"
    else:
        body = who + (f", who {sc['action_en']}" if sc.get("action_en") else "") + (DOG_EXTRA if sc.get("with_dog") else "")
    return f"{i}) {TIMES[sc['time']]}: {body}."


def _b64(path: Path, side: int = 1024) -> str:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


def _fake_sheet(base: Path, out: Path, n: int = 4) -> Path:
    """0원 가짜 시트: 원본 9:16 을 4칸에 색만 달리 넣고 흰 구분선(split_panels 가 나누게)."""
    im = Image.open(base).convert("RGB")
    pw, ph, g = 760, 1350, 24
    sheet = Image.new("RGB", (pw * 2 + g * 3, ph * 2 + g * 3), "white")
    tints = [(0, 0, 0), (60, 30, 0), (0, 20, 60), (30, 30, 30)]
    for i in range(n):
        p = im.resize((pw, ph), Image.LANCZOS)
        r, gg, b = tints[i % 4]
        p = Image.eval(p, lambda v, r=r: min(255, v + r)) if False else Image.merge("RGB", [ch.point(lambda v, d=d: max(0, min(255, v + d))) for ch, d in zip(p.split(), tints[i % 4])])
        x, y = g + (i % 2) * (pw + g), g + (i // 2) * (ph + g)
        sheet.paste(p, (x, y))
    sheet.save(out, "PNG")
    return out


def _grid_boxes(w: int, h: int, inset: float = 0.015) -> list[tuple[int, int, int, int]]:
    cols, rows = GRID
    out = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = int(w * c / cols), int(h * r / rows)
            x1, y1 = int(w * (c + 1) / cols), int(h * (r + 1) / rows)
            dx, dy = int((x1 - x0) * inset), int((y1 - y0) * inset)
            out.append((x0 + dx, y0 + dy, x1 - dx, y1 - dy))
    return out


def _call_sheet(base: Path, prompt: str, out: Path, rep: dict) -> tuple[Path, float]:
    """시트 1장 생성(돈 · 장부 kind image). 한도는 돈 쓰기 전에(make_mini.composite 와 같은 규칙). 2K 를 요청하고 안 되면 1K."""
    models = rep.get("image_models") or mm.image_models(rep.get("image_prefer"))
    rep["image_models"] = models
    parts = [{"text": prompt}, {"text": "Attached image: the real HOTEL PHOTOGRAPH (reference for every panel)."},
             {"inline_data": {"mime_type": "image/jpeg", "data": _b64(base, 1024)}}]
    last = None
    for model in models:
        krw = mm.image_krw(model) * (SHEET_KRW_MULT if SHEET_SIZE != "1K" else 1.0)
        used = veo.month_total("all")
        if used + krw > veo.MONTH_KRW:
            raise RuntimeError(f"이번 달 한도({veo.MONTH_KRW:,.0f}원) — 지금 {used:,.0f}원")
        if veo._state["spent"] + krw > veo.RUN_KRW:
            raise RuntimeError(f"한 번 실행 한도({veo.RUN_KRW:,.0f}원) — 여기까지 {veo._state['spent']:,.0f}원")
        for size in ([SHEET_SIZE, "1K"] if SHEET_SIZE != "1K" else ["1K"]):
            cfg = {"aspectRatio": "9:16"}
            if size != "1K":
                cfg["imageSize"] = size
            body = {"contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": cfg}}     # IMAGE 만 — TEXT 를 같이 주면 1K 로 떨어진다는 보고(2026 포럼)
            try:
                data = mm._post(f"models/{model}:generateContent", body)
            except RuntimeError as e:
                last = e
                if "HTTP 400" in str(e) and ("imageSize" in str(e) or "image_size" in str(e)) and size != "1K":
                    log(f"{model}: imageSize {size} 거부 → 1K 로 다시")
                    continue
                if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                    log(f"이미지 모델 {model} 사용 불가 → 다음: {str(e)[:120]}")
                    break
                raise
            veo.record_est("image", krw, f"{model} 씬 스토리보드 시트 {out.name} {size} (추정)")
            veo._state["spent"] += krw
            rep["image_krw"] = rep.get("image_krw", 0) + round(krw)
            rep["image_model"] = model
            img = None
            for c in data.get("candidates") or []:
                for p in (c.get("content") or {}).get("parts") or []:
                    d = p.get("inlineData") or p.get("inline_data")
                    if d and str(d.get("mimeType") or d.get("mime_type") or "").startswith("image/"):
                        img = base64.b64decode(d["data"])
            if img:
                out.write_bytes(img)
                Image.open(out).convert("RGB").save(out, "PNG")
                return out, krw
            last = RuntimeError(f"이미지 없음 (finish {[c.get('finishReason') for c in data.get('candidates') or []]})")
            log(f"시트 결과에 이미지가 없음: {str(last)[:120]}")
            break
    raise RuntimeError(f"시트 생성 실패: {last}")


def _expect(sc: dict) -> dict:
    who = sc["who"]
    if who == "couple":
        return {"people": 2, "dogs": 1 if sc.get("with_dog") else 0}
    if who == "back":
        return {"people": 1, "dogs": 0}
    if who == "hand":
        return {"people": "hand", "dogs": 0}
    if who == "dog":
        return {"people": 0, "dogs": 1}
    return {"people": 0, "dogs": 0}


def _judge(sc: dict, r: dict) -> tuple[bool, str]:
    exp = _expect(sc)
    probs = []
    if r.get("same_place") is not True:
        probs.append("다른 공간")
    if r.get("structure_changes"):
        probs.append("구조 변경: " + ", ".join(map(str, r["structure_changes"]))[:80])
    if r.get("added_objects"):
        probs.append("새 사물: " + ", ".join(map(str, r["added_objects"]))[:80])
    if r.get("face_visible"):
        probs.append("얼굴 보임")
    if r.get("text"):
        probs.append("글자")
    if r.get("looks_real") is False:
        probs.append("실사 아님")
    ppl = r.get("people")
    n_people = ("hand" if str(ppl).lower() == "hand" else int(ppl) if str(ppl).lstrip("-").isdigit() else 0)
    dogs = int(r.get("dogs") or 0) if str(r.get("dogs") or "0").isdigit() else 0
    if exp["people"] == "hand":
        if n_people not in ("hand", 0, 1) or (n_people == 1 and r.get("face_visible")):
            probs.append(f"사람 {n_people}(손만 기대)")
    elif n_people != exp["people"]:
        probs.append(f"사람 {n_people}(기대 {exp['people']})")
    if dogs != exp["dogs"]:
        probs.append(f"강아지 {dogs}(기대 {exp['dogs']})")
    return (not probs), "; ".join(probs)[:200]


def _check_sheet(models: dict, base: Path, panels: list[Path], group: list[dict]) -> list[dict]:
    """시트 1장 = 비전 1회(원본 + 패널 4장 · 약 2원). 실패하면 보수적으로 전부 탈락."""
    if FAKE:
        out = []
        for sc in group:
            why = FAKE_CHECK.get(sc["n"]) or ""
            out.append({"ok": not why, "why": why, "raw": {"fake": True}})
        return out
    want = "패널별 기대: " + " / ".join(f"패널 {i + 1}: {WHO_KO.get(sc['who'], '')}{'+강아지' if sc.get('with_dog') else ''} · {TIME_KO[sc['time']]}" for i, sc in enumerate(group))
    try:
        r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, CHECK_SYSTEM, want, [base] + panels))
    except Exception as e:  # noqa: BLE001
        return [{"ok": False, "why": f"검수 호출 실패: {str(e)[:60]}", "raw": {}} for _ in group]
    by_n = {}
    for p in (r.get("panels") if isinstance(r, dict) else r) or []:
        if isinstance(p, dict) and str(p.get("n", "")).isdigit():
            by_n[int(p["n"])] = p
    out = []
    for i, sc in enumerate(group):
        p = by_n.get(i + 1)
        if not p:
            out.append({"ok": False, "why": "검수 답 없음", "raw": {}}); continue
        ok, why = _judge(sc, p)
        out.append({"ok": ok, "why": why or str(p.get("why") or "")[:80], "raw": {k: p.get(k) for k in ("same_place", "structure_changes", "added_objects", "people", "face_visible", "dogs", "text", "looks_real")}})
    return out


# ── 2. 시트 생성·분할·검수 ──────────────────────────────────────────────────────────
def make_sheets(models: dict, scenes: list[dict], shots: dict, story: Path, report: dict) -> None:
    """참조 사진(k)별로 씬을 4개씩 묶어 시트 한 장씩(최대 MAX_SHEETS). 4개가 안 되면 빈 자리는 다른 시간대의 '사람 없음' 씬으로 채운다(여분 스틸)."""
    rep = {"image_prefer": None}
    groups: dict[int, list[dict]] = {}
    for sc in scenes:
        groups.setdefault(sc["k"], []).append(sc)
    sheets, n_sheet = [], 0
    spare_n = len(scenes)
    for k, group in groups.items():
        if not any(sc["m"] == 0 for sc in group):                                        # 꼬리 컷만 있는 사진은 시트를 안 만든다(돈) — 다른 사진이라 화면은 이미 바뀐다
            for sc in group:
                sc["ok"] = False; sc["why"] = "꼬리 컷은 원본(시트 생략)"
            continue
        chunks = [group[i:i + 4] for i in range(0, len(group), 4)]
        for chunk in chunks:
            if n_sheet >= MAX_SHEETS:
                for sc in chunk:
                    sc["why"] = "시트 상한"; sc["ok"] = False
                continue
            base_sid = chunk[0]["sid"]
            base = story / shots[base_sid]["img"]
            used_t = {sc["time"] for sc in chunk}
            pad = []
            while len(chunk) + len(pad) < 4:                                            # 여분 패널 = 같은 공간 다른 시간대(사람 없음) — 꼬리 컷 예비
                t = next((x for x in ("golden", "evening", "day", "night", "morning") if x not in used_t | {p["time"] for p in pad}), "day")
                spare_n += 1
                pad.append({"n": spare_n, "j": None, "m": None, "sid": base_sid, "k": k, "place": shots[base_sid].get("place") or "", "who": "env", "with_dog": False,
                            "action_en": "", "time": t, "src_img": shots[base_sid]["img"], "img": None, "ok": None, "why": "", "panel_px": 0, "sheet": None, "spare": True})
            panel_scenes = chunk + pad
            n_sheet += 1
            out = story / f"sheet_{n_sheet}.png"
            prompt = SHEET_PROMPT.format(panels="\n".join(_panel_text(i + 1, sc) for i, sc in enumerate(panel_scenes)))
            (story / f"sheet_{n_sheet}_prompt.txt").write_text(prompt, encoding="utf-8")
            krw = 0.0
            try:
                if FAKE:
                    _fake_sheet(base, out, 4); rep["image_model"] = "FAKE"
                else:
                    _, krw = _call_sheet(base, prompt, out, rep)
            except RuntimeError as e:
                log(f"시트 {n_sheet} 실패 → 이 씬들은 원본 사진: {str(e)[:120]}")
                for sc in panel_scenes:
                    sc["ok"] = False; sc["why"] = f"시트 실패: {str(e)[:60]}"
                sheets.append({"n": n_sheet, "k": k, "ok": False, "error": str(e)[:120], "scenes": [sc["n"] for sc in panel_scenes], "krw": 0})
                continue
            with Image.open(out) as im:
                W, H = im.size
                boxes = photos.split_panels(str(out))
                if len(boxes) != 4:
                    boxes = _grid_boxes(W, H)
                panels = []
                for i, (sc, box) in enumerate(zip(panel_scenes, boxes)):
                    p = im.crop(box).convert("RGB")
                    px = min(p.size)
                    name = f"sb_{n_sheet}_{i + 1}.png"
                    design.cover(p, ms.W, ms.H).save(story / name, "PNG")                   # 9:16 1080×1920 (가운데 기준 · 작으면 확대 — panel_px 로 등급)
                    sc["img"], sc["panel_px"], sc["sheet"] = name, px, n_sheet
                    panels.append(story / name)
            checks = _check_sheet(models, base, panels, panel_scenes)
            for sc, c in zip(panel_scenes, checks):
                sc["ok"] = bool(c["ok"]) and sc["panel_px"] >= PANEL_MIN
                sc["why"] = c["why"] if not c["ok"] else ("" if sc["panel_px"] >= PANEL_MIN else f"패널이 작음 {sc['panel_px']}px")
                sc["check"] = c.get("raw")
            sheets.append({"n": n_sheet, "k": k, "ok": True, "px": [W, H], "panel_px": [sc["panel_px"] for sc in panel_scenes], "scenes": [sc["n"] for sc in panel_scenes],
                           "passed": sum(1 for sc in panel_scenes if sc["ok"]), "krw": round(krw), "model": rep.get("image_model")})
            log(f"시트 {n_sheet} (사진 {k}) {W}×{H} · 패널 {[sc['panel_px'] for sc in panel_scenes]}px · 통과 {sheets[-1]['passed']}/4 · 약 {krw:,.0f}원")
            scenes.extend(pad)
    report["storyboard"] = {"sheets": sheets, "krw": sum(s.get("krw", 0) for s in sheets), "model": rep.get("image_model"), "fake": FAKE,
                            "scenes": [{k_: sc.get(k_) for k_ in ("n", "j", "m", "sid", "k", "place", "who", "with_dog", "time", "img", "ok", "why", "panel_px", "sheet", "spare")} for sc in scenes]}


# ── 3. 컷에 적용 ─────────────────────────────────────────────────────────────────────
def apply_scenes(beats: list[dict], scenes: list[dict], shots: dict) -> None:
    """통과한 패널을 그 컷의 화면으로(cut_imgs) · 탈락·없음은 원본 사진. 사람·강아지 씬의 패널은 제작 때 Veo 시작 장면(start_img)."""
    by = {(sc["j"], sc["m"]): sc for sc in scenes if sc.get("j") is not None}
    spare = [sc for sc in scenes if sc.get("spare") and sc.get("ok")]
    for j, b in enumerate(beats):
        imgs, kinds = [], []
        for m, sid in enumerate(b.get("shots") or []):
            sc = by.get((j, m))
            if sc and sc.get("ok") and sc.get("img"):
                imgs.append(sc["img"]); kinds.append(f"AI 스토리보드 {WHO_KO.get(sc['who'], '')}·{TIME_KO[sc['time']]}")
            elif sc and m > 0:                                                            # 꼬리 컷이 탈락하면 같은 사진의 여분 패널로
                alt = next((x for x in spare if x["k"] == sc["k"] and x["img"] not in imgs), None)
                if alt:
                    imgs.append(alt["img"]); kinds.append(f"AI 스토리보드 여분·{TIME_KO[alt['time']]}")
                else:
                    imgs.append(shots[sid]["img"]); kinds.append("원본 사진")
            else:
                skipped = bool(sc) and "시트 생략" in str(sc.get("why") or "")
                imgs.append(shots[sid]["img"] if sid in shots else "")
                kinds.append("원본 사진" if (not sc or sc.get("ok") or skipped) else f"원본 사진(패널 탈락: {sc.get('why', '')[:30]})")
        b["cut_imgs"], b["cut_kinds"] = imgs, kinds
        v = b.get("visual") or {}
        if v.get("type") in ("A", "B") and imgs:
            v["start_img"] = imgs[0]


def cut_img(b: dict, m: int, shots: dict, story: Path) -> Path:
    imgs = b.get("cut_imgs") or []
    if m < len(imgs) and imgs[m]:
        return story / imgs[m]
    return story / shots[b["shots"][m]]["img"]
