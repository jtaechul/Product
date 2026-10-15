"""시그니처 원테마 쇼츠 — mode "signature" (2026-10-14 운영자 "진행해").

벤치마크(stay__list · CLAUDE.md '벤치마크 stay__list'): 한 숙소 = **한 시그니처**(의외의 시설·장면·활동)만 극대화하고
일반 요소(일반 객실·로비·휴게실·관리실)는 전부 생략 → "여기 어디?" 궁금증. 영상은 음악 + 한 문장을 컷마다 한 구절씩.

흐름
  1. 사진·사실 수집(make_solo.assets — 공식 홈페이지 + 쿠팡, 분류·외관·다른 지점 검사 그대로)
  2. 시그니처 1개 선정 — 사실 목록의 한 줄이 그 시그니처를 직접 말하고(근거 번호 + 낱말 겹침 검사), 사진에 또렷이 보여야 한다(비전 확인).
     없으면 **만들지 않는다**(시그니처를 지어내지 않는다).
  3. 변주 계획 — 같은 시그니처를 시간(노을·해 질 녘·밤·아침 안개)·날씨(비·눈·김)·뒷모습 인물로. 변주 종류는 **코드의 목록에서만** 고른다(자유 지시문 금지).
  4. 이미지 편집 — 구조 유지 지시문 + 원본 대비 비전 검수(같은 장소·구조 변경·새 사물·얼굴·글자) + 윤곽선 유지율(0원, 기록용).
     두 번 실패하면 그 컷은 원본 사진으로.
  5. 문구 — **이미지가 확정된 뒤에** 쓴다(실패해 원본으로 바뀐 컷에 '비 오는 날' 같은 글이 붙지 않게). 2인칭 상상·현재형, 1인칭 체험·과거형 금지,
     시설 이름은 그 컷 사진 설명·근거 사실에 있을 때만, 겨울 편 여름 시설 금지. 훅 제목(반전 질문·의외 사실 번갈아). 캡션은 공감 → 장면 → 근거 있는 체크리스트.
  6. 렌더 — 사진 무빙(0원) + 제작 때만 첫 컷 Veo(294원), 위쪽 고지문·가운데 아래 구절 자막·첫 컷 훅 제목(design.GRID 자리 그대로), 끝 카드, 배경음악만.

요청: {"mode":"signature","stay":..,"stage":"preview"|없음,"format":"montage"|"single","people":"back"|"none","veo_approved":true(제작)}
미리보기 = 변주 이미지까지 만든 사진 무빙 영상(Veo 0원 · 편집 장당 약 98원). 제작 = 미리보기 결과 재사용(reuse_runs → build/reuse/*/…/sig/plan.json) + 첫 컷 Veo.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import design
import make_folder
import make_mini
import make_solo as so
import make_stay as ms
import make_top3 as mt
import photos
import veo

SIG = ms.BUILD / "sig"
REUSE_DIR = ms.BUILD / "reuse"
FAKE_IMG = os.environ.get("SIG_FAKE_IMAGE", "") == "1"          # 로컬 시험: 이미지 편집 대신 색만 바꾼 가짜 변주(0원)
MAX_EDITS = 5                                                     # 편당 편집 컷 상한(장당 약 98원)
EDIT_TRIES = 7                                                    # 한 번 실행의 편집 호출 상한(재시도 포함) — 최악 약 690원. 넘으면 남은 컷은 원본으로
N_SHOTS = {"montage": 6, "single": 2}
DUR = {"hook": 4.0, "mid": 1.9, "last": 2.4, "card": 2.8}        # stay__list 실측: 첫 컷 4.4초 뒤 약 1.6초씩
MOTION_SIG = 0.12                                                 # 짧은 컷이라 사진 무빙 폭을 9컷 형식(0.24)의 절반으로
MUSIC_LEVEL = 0.9                                                 # 나레이션이 없어 음악을 주 소리로
PATTERNS = ("push", "pan", "diag", "tilt", "pull")
WARM_WATER_RX = re.compile(r"온수|온천|노천|스파|탕|사우나|자쿠지|히노키|김이|증기")
WATER_RX = re.compile(r"물|풀|탕|스파|온천|수영|바다|파도|호수|계곡")
PAST_RX = re.compile(r"(었|았|였)(어요|다|고|는데|지만|던|죠)|더라|다녀|묵었|머물렀|즐기고 온|좋았|했던|갔던|봤는데")   # 1인칭 체험·과거형 (stay__list 캡션의 위험 요소)
FIRST_RX = re.compile(r"(^|\s)(저는|제가|저희|우리가|우리는|내가|나는)")
DIGIT_RX = re.compile(r"\d[\d,.]*")
GENERIC_SIG = {"객실", "숙소", "호텔", "리조트", "공간", "시설", "전망", "뷰", "실내", "야외", "있는", "갖춘", "운영", "보유"}

VARIANTS = {
    "original": "",
    "golden": ("the time of day becomes late-afternoon golden hour: warm, low sunlight, long soft shadows and a warm orange-pink sky wherever the sky is visible; "
               "lamps that already exist may glow softly."),
    "dusk": ("dusk (blue hour): a deep blue sky with a last warm glow at the horizon wherever the sky is visible; lights and lamps that already exist glow warmly "
             "and their reflections appear on existing water and glass."),
    "night": ("night: a dark sky wherever the sky is visible; only the lights and lamps that already exist in the photo glow warmly; "
              "no new light fixtures, no fireworks."),
    "rain": ("a gentle rainy day: soft overcast light, fine visible rain streaks, wet glossy surfaces and small rain ripples on water that already exists; "
             "low clouds or mist over distant mountains only if mountains are already visible."),
    "snow": ("light snowfall: soft falling snowflakes and a thin layer of fresh snow on outdoor horizontal surfaces that already exist (roofs, railings, ground, trees); "
             "indoor areas stay the same except snow seen through existing windows."),
    "mist": "an early morning: soft, cool morning light and a thin mist floating over water or distant landscape that already exists.",
    "steam": "cool air: soft white steam rising slowly from the surface of the warm water that already exists.",
}
VARIANT_KO = {"original": "원본", "golden": "노을빛", "dusk": "해 질 녘", "night": "밤", "rain": "비 오는 날", "snow": "눈", "mist": "아침 안개", "steam": "김"}
PEOPLE = {"one": "one adult", "couple": "a couple (two adults)", "family": "a parent and a young child"}
PEOPLE_KO = {"one": "한 명", "couple": "두 사람", "family": "부모와 아이"}
POSES = {"soak": "soaking up to the shoulders in the warm water that already exists, looking at the view",
         "sit": "sitting on a seat, bench or deck edge that already exists, looking at the view",
         "stand": "standing at a window, railing or edge that already exists, looking out at the view",
         "walk": "walking slowly away from the camera along a path that already exists"}
POSE_KO = {"soak": "몸 담그고 바라보기", "sit": "앉아서 바라보기", "stand": "서서 바라보기", "walk": "천천히 걷기"}

EDIT_KEEP = ("TASK: Edit the attached photograph of a real hotel into a mood variation of the SAME place at a different moment. "
             "KEEP EXACTLY: the camera position, framing and lens; every building, wall, roof, window, door, pool or bath shape, water edge, deck, railing, "
             "furniture, plant and object, with the same positions, sizes, colors and materials; the view outside (sea, mountains, skyline, city) and its direction. "
             "Do not add, remove, move, enlarge, shrink or redesign anything. Do not add new furniture, lamps, decorations, pools, water, plants, signs, text, logos or watermarks. ")
EDIT_PEOPLE = ("PEOPLE: add {who}, seen strictly from behind — the backs of their heads and shoulders toward the camera, no face visible — {pose}, at {place}. "
               "Realistic people at correct human scale for the perspective, relaxed and nearly still, partly hidden where natural (for example below the water line). "
               "Swimwear only when they are in water; otherwise simple casual clothes or bathrobes. They stay on surfaces that already exist in the photo. No other people. ")
EDIT_NO_PEOPLE = "Do not add any people or animals. "
EDIT_TAIL = ("The result must look like a real, unretouched photo taken by the same camera at a different moment — photorealistic, natural colors, "
             "no painterly, illustrated or cartoon look.")

VEO_SIG = ("Camera: locked-off with a very slow, steady push-in of about 5 percent, staying inside the photo the whole time; no other camera movement. "
           "Only natural ambient motion of what is already in the first frame: {motion} "
           "Keep every building, structure, object and the view exactly as in the first frame; no people, no new objects, no text.")
VEO_MOTION = {"rain": "rain falls steadily and small ripples spread on the existing water.", "snow": "snowflakes drift down slowly.",
              "steam": "soft white steam rises and drifts from the warm water.", "mist": "the thin mist drifts slowly.",
              "night": "lights glow and their reflections shimmer gently on water and glass.", "dusk": "lights glow and reflections shimmer gently.",
              "golden": "sunlight sparkles gently on surfaces.", "original": "water and leaves move gently and light sparkles softly."}


def log(*a):
    print("[sig]", *a, flush=True)


# ── 공통 호출 ──────────────────────────────────────────────────────────────────────────
def _json_text(model: str, system: str, content: str, temp: float = 0.4, max_tokens: int = 3000) -> dict:
    body = {"system_instruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": content}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temp, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    txt = "".join(p.get("text", "") for p in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])).strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError(f"JSON 아님: {txt[:120]}")
    return json.loads(m.group(0))


def _b64(path: Path, side: int = 1024) -> str:
    import io
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _json_vision(model: str, system: str, text: str, images: list[Path], side: int = 1024) -> dict:
    parts = [{"text": text}]
    for k, p in enumerate(images, 1):
        parts += [{"text": f"사진 {k}:"}, {"inline_data": {"mime_type": "image/jpeg", "data": _b64(p, side)}}]
    body = {"system_instruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 600, "temperature": 0.0, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    txt = "".join(p.get("text", "") for p in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])).strip()
    m = re.search(r"\{.*\}", re.sub(r"^```(?:json)?|```$", "", txt).strip(), re.S)
    return json.loads(m.group(0)) if m else {}


def month_num(req: dict) -> int:
    m = re.search(r"-(\d{1,2})\b", str(req.get("month") or ""))
    return int(m.group(1)) if m else 0


def _tokens(text: str) -> set[str]:
    """비교용 낱말: 2자 이상, 조사·일반 낱말 제거."""
    out = set()
    for w in re.findall(r"[가-힣A-Za-z0-9]+", str(text or "")):
        w = re.sub(r"(은|는|이|가|을|를|과|와|의|에|에서|으로|로|도|만|까지|부터|이에요|예요|이다|있는|하는)$", "", w)
        if len(w) >= 2 and w not in GENERIC_SIG:
            out.add(w)
    return out


def _overlap(ta: set[str], tb: set[str]) -> int:
    """ta 낱말 중 tb 의 어떤 낱말과 겹치는(한쪽이 다른 쪽을 포함) 수 — '산토리니풍'↔'산토리니' 같은 형태 차이를 인정한다."""
    return sum(1 for a in ta if any(a in b or b in a for b in tb))


def _int(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    return int(x) if isinstance(x, str) and x.strip().isdigit() else None


def _ask(models: dict, system: str, content: str, temp: float) -> dict:
    """글 호출 + JSON 해석. 답이 JSON 이 아니면 한 번 더 묻는다(모델 교체는 _try_models 가 맡는다)."""
    last = None
    for _ in range(2):
        try:
            return ms._try_models("text", models["text"], lambda m: _json_text(m, system, content, temp=temp))
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            log(f"JSON 답 해석 실패 → 다시: {str(e)[:80]}")
    raise RuntimeError(f"JSON 답을 받지 못함: {last}")


# ── 1. 사실·사진 목록 ─────────────────────────────────────────────────────────────────────
def facts_list(h: dict) -> list[str]:
    """시그니처·활동·체크리스트의 근거가 되는 사실(번호를 붙여 AI 에 준다). 이 목록 밖의 사실은 쓰지 않는다."""
    out = [str(f).strip() for f in (h.get("official_facts") or []) if str(f).strip()]
    out += [f"블로그 교차 확인 시설: {f}" for f in (h.get("verified_facilities") or []) if str(f).strip()]
    if h.get("signature"):
        out.append(f"공식 홈페이지 한 줄 요약: {h['signature']}")
    if h.get("hook"):
        out.append(f"후보표 훅: {h['hook']}")
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f); uniq.append(f)
    return uniq


def usable_photos(h: dict) -> list[dict]:
    """분류된 전체 사진 중 쓸 수 있는 것 — 사람 없음·다른 지점 아님·품질 5 이상. 외관도 허용(시그니처가 외관일 수 있다)."""
    out = [p for p in (h.get("classified") or []) if p.get("category") in photos.CATS and int(p.get("quality") or 0) >= 5
           and not p.get("people") and not p.get("mismatch") and Path(str(p.get("path") or "")).exists()]
    return out


def _photo_line(p: dict) -> str:
    alt = f" · 공식 사진 이름 '{p['src_alt']}'" if p.get("src_alt") else ""
    return f"사진 {p['k']} [{mt.SRC_KO.get(p.get('source'), '?')} · {p.get('category')} · {p.get('view') or '-'} · 품질 {p.get('quality')}{alt}] {p.get('description') or ''}"


# ── 2. 시그니처 선정 ─────────────────────────────────────────────────────────────────────
SIG_SYSTEM = """너는 숙소 쇼츠 기획자다. 한 숙소에서 시청자가 "여기 어디야?" 하고 멈출 **시그니처 하나**를 고른다.
시그니처 = 이 숙소에서 가장 의외이고 눈에 띄는 시설·장면 하나(예: 이집트 신전풍 야외 온수풀, 객실 전용 노천탕, 바다 바로 앞 테라스, 산토리니풍 파란 지붕과 바다).
일반 요소(평범한 객실·로비·휴게실·관리실·노래방·오락실·주차장·평범한 실내 수영장)는 시그니처가 아니다 — 그 자체가 독특할 때만 된다.
조건:
1) 근거: 아래 '사실' 목록 중 하나(번호)가 그 시그니처를 **직접** 말해야 한다. 사실에 없는 시그니처는 고르지 않는다.
2) 사진: 그 시그니처가 또렷이 보이는 사진 번호 1~3개(가장 좋은 것 먼저). 사진에 안 보이면 고르지 않는다.
3) 시기가 11~3월이면 바깥의 여름 물놀이(카바나·선베드·해수욕·야외 수영장)는 시그니처가 될 수 없다(온수·사계절이라고 사실에 있으면 된다).
4) 활동: 이 숙소에서 할 수 있다고 사실 목록에 있는 활동만(번호와 함께, 예: 불멍·바비큐·노천욕·산책). 없으면 빈 목록.
5) 마지막 장면용 객실 사진: 창밖으로 시그니처나 그 풍경(바다·산·숲)이 보이는 객실 사진 번호(없으면 null).
의외성(한국 숙소에서 드문 정도) · 사진 품질 · 테마 적합 순으로 고른다.
JSON 만: {"signature":"2~16자 이름","what":"무엇이 보이는지 한 줄","fact":번호,"photos":[번호],"room_view":번호 또는 null,
 "activities":[{"name":"2~10자","fact":번호}],"surprise":1~10,"why":"왜 의외인지 한 줄","alternatives":["다른 후보 이름"]}"""

CONFIRM_SYSTEM = """너는 숙소 사진 검수자다. 사진 1장과 시그니처 이름·설명을 받는다. 그 시그니처가 이 사진에 **또렷이** 보이는지만 판단한다(추측 금지).
JSON 만: {"visible": true 또는 false, "evidence": "사진에 보이는 근거 한 줄"}"""


def sig_errs(js: dict, facts: list[str], pool: dict, h: dict, req: dict) -> list[str]:
    errs = []
    name = str(js.get("signature") or "").strip()
    if not (2 <= len(name) <= 16):
        errs.append("signature 이름 2~16자")
    fi = _int(js.get("fact"))
    if fi is None or not (1 <= fi <= len(facts)):
        errs.append(f"fact 번호가 사실 목록(1~{len(facts)})에 없음")
        return errs
    fact = facts[fi - 1]
    if not _overlap(_tokens(name) | _tokens(js.get("what")), _tokens(fact)):
        errs.append(f"근거 사실 {fi}('{fact[:30]}')이 시그니처 '{name}'를 직접 말하지 않음 — 낱말이 겹치는 사실을 고른다")
    ks = [_int(k) for k in (js.get("photos") or [])]
    if not ks or any(k not in pool for k in ks):
        errs.append("photos 는 위 사진 번호 1~3개(목록에 있는 것만)")
        return errs
    hero = pool[ks[0]]
    desc = f"{hero.get('description') or ''} {hero.get('src_alt') or ''} {fact}"
    bad = [t for t in photos.facility_terms(name) if not photos.term_ok(t, desc)]
    if bad:
        errs.append(f"시그니처 이름의 시설 '{'/'.join(bad)}'이 사진 설명·근거 사실에서 확인되지 않음")
    if so.cold_month(req) and so.off_season(hero):
        errs.append("겨울 편에 바깥 여름 물놀이 사진을 시그니처로 고름")
    rv = _int(js.get("room_view")) if js.get("room_view") is not None else None
    if js.get("room_view") is not None and rv not in pool:
        errs.append("room_view 는 목록의 사진 번호 또는 null")
    for a in js.get("activities") or []:
        fa = _int(a.get("fact")) if isinstance(a, dict) else None
        if fa is None or not (1 <= fa <= len(facts)):
            errs.append("activities 의 fact 번호가 잘못됨"); break
    return errs


def choose_signature(models: dict, h: dict, req: dict, report: dict) -> dict:
    facts = facts_list(h)
    pool = {int(p["k"]): p for p in usable_photos(h)}
    if not facts or not pool:
        raise RuntimeError(f"시그니처 없음 — 사실 {len(facts)}개 · 쓸 수 있는 사진 {len(pool)}장 (만들지 않음)")
    content = (f"숙소: {h['name']} ({h.get('city') or ''}) · 테마: {req.get('theme')} · 시기: {req.get('month')}\n\n사실(번호):\n"
               + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1))
               + "\n\n사진:\n" + "\n".join(_photo_line(p) for p in pool.values()))
    fb, js, tries = "", {}, []
    for attempt in range(3):
        js = _ask(models, SIG_SYSTEM, content + fb, 0.3)
        errs = sig_errs(js, facts, pool, h, req)
        tries.append({"signature": js.get("signature"), "errs": errs})
        if not errs:
            break
        log(f"시그니처 검사 실패({attempt + 1}): {errs}")
        fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs)
    else:
        report["signature_tries"] = tries
        raise RuntimeError(f"시그니처 없음 — 근거·사진 조건을 만족하는 후보가 없음: {tries[-1]['errs']} (만들지 않음)")
    ks = [k for k in (_int(x) for x in js["photos"]) if k in pool][:3]
    confirmed, checks = [], []
    for k in ks:                                                           # 사진마다 그 시그니처가 또렷이 보이는지 비전으로 확인(약 1원)
        try:
            r = ms._try_models("vision", models["text"], lambda m: _json_vision(m, CONFIRM_SYSTEM, f"시그니처: {js['signature']} — {js.get('what') or ''}", [Path(pool[k]["path"])]))
        except Exception as e:  # noqa: BLE001
            r = {"visible": False, "evidence": f"확인 실패: {str(e)[:60]}"}
        checks.append({"k": k, **r})
        if r.get("visible") is True:
            confirmed.append(k)
    if not confirmed:
        report["signature_tries"] = tries
        report["signature_checks"] = checks
        raise RuntimeError(f"시그니처 없음 — '{js['signature']}'이(가) 고른 사진에서 또렷이 확인되지 않음 (만들지 않음)")
    fi = _int(js["fact"])
    rv = _int(js.get("room_view")) if js.get("room_view") is not None else None
    acts = [(str(a.get("name") or "")[:10], _int(a.get("fact"))) for a in (js.get("activities") or []) if isinstance(a, dict)]
    sig = {"name": js["signature"].strip(), "what": str(js.get("what") or "").strip(), "fact": facts[fi - 1], "fact_i": fi,
           "photos": confirmed, "room_view": rv if (rv in pool and rv not in confirmed) else None,
           "activities": [{"name": nm, "fact": facts[fa - 1]} for nm, fa in acts if nm and fa and 1 <= fa <= len(facts)],
           "surprise": js.get("surprise"), "why": str(js.get("why") or "")[:80], "alternatives": js.get("alternatives") or [], "checks": checks}
    log(f"시그니처: {sig['name']} — 근거 '{sig['fact'][:40]}' · 사진 {sig['photos']} · 의외성 {sig['surprise']}")
    return sig


# ── 3. 변주 계획 ────────────────────────────────────────────────────────────────────────
def allowed_variants(p: dict, month: int) -> list[str]:
    d = str(p.get("description") or "")
    out = ["original", "golden", "dusk", "night", "mist", "rain"]
    if month in (12, 1, 2) and (p.get("view") in ("exterior", "outdoor") or re.search(r"창|통창|테라스|발코니|바깥|야외|노천", d)):
        out.append("snow")
    if WARM_WATER_RX.search(d) and WATER_RX.search(d):
        out.append("steam")
    return out


def allowed_poses(p: dict) -> list[str]:
    d = str(p.get("description") or "")
    poses = ["sit", "stand"]
    if WARM_WATER_RX.search(d) and WATER_RX.search(d):
        poses.append("soak")
    if re.search(r"산책|길|정원|해변|데크|숲", d):
        poses.append("walk")
    return poses


PLAN_SYSTEM = """너는 숏폼 촬영 감독이다. 숙소의 **시그니처 하나**만으로 영상 컷 목록을 짠다. 일반 요소(평범한 객실·로비·휴게실)는 넣지 않는다.
같은 시그니처 사진을 시간·날씨·뒷모습 인물로 **변주**해 여러 컷을 만든다(실제 구조는 그대로, 바뀌는 것은 빛·날씨·사람뿐).
규칙:
- 컷 수는 입력의 '컷 수'. 첫 컷 = 시그니처가 가장 의외로 보이는 장면(사람 없이). 마지막 컷 = 객실 창 사진이 있으면 그것, 없으면 시그니처의 해 질 녘·밤.
- src 는 입력 사진 번호만. 시그니처 사진이 아닌 컷은 마지막 객실 창 컷 하나뿐.
- variant 는 그 사진의 '쓸 수 있는 변주'에서만. 같은 사진·같은 변주 반복 금지, 바로 이어지는 두 컷이 같은 사진이면 변주가 확연히 달라야 한다.
- people 는 "none" | "one" | "couple" | "family" (뒷모습만). 사람 컷은 최대 3개, 첫 컷은 none. pose 는 그 사진의 '쓸 수 있는 자세'에서만.
  place 는 사람이 있을 **사진 속 실제 자리**를 영어로 짧게(예: "in the round outdoor bath at the lower left", "on the wooden deck by the railing").
- 변주는 이야기 흐름이 되게: 예) 낮의 의외 장면 → 노을 → 사람이 몸 담금 → 해 질 녘 → 밤 → 객실 창.
JSON 만: {"shots":[{"src":번호,"variant":"...","people":"none","pose":"","place":""}]}"""


def plan_errs(js: dict, n: int, sig: dict, pool: dict, month: int, people_mode: str) -> list[str]:
    shots = js.get("shots") or []
    errs = []
    if not (max(2, n - 1) <= len(shots) <= n + 1):
        errs.append(f"컷 {len(shots)}개 — {n}개로")
    sig_set = set(sig["photos"])
    seen, prev, n_people, edits = set(), None, 0, 0
    for i, s in enumerate(shots, 1):
        k = _int(s.get("src"))
        s["src"] = k
        if k not in pool:
            errs.append(f"컷 {i} src {k} 는 목록에 없는 사진"); continue
        last = (i == len(shots))
        if k not in sig_set and not (last and k == sig.get("room_view")):
            errs.append(f"컷 {i} 는 시그니처 사진이 아님(마지막 객실 창 컷만 예외)")
        v = s.get("variant")
        if v not in allowed_variants(pool[k], month):
            errs.append(f"컷 {i} 변주 '{v}' 는 이 사진에 쓸 수 없음 — {allowed_variants(pool[k], month)}")
        pp = s.get("people") or "none"
        if pp not in ("none", *PEOPLE):
            errs.append(f"컷 {i} people '{pp}' 는 none/one/couple/family 만")
        if pp != "none":
            n_people += 1
            if people_mode == "none":
                errs.append(f"컷 {i} 사람 금지(people none)")
            if i == 1:
                errs.append("첫 컷은 사람 없이")
            if s.get("pose") not in allowed_poses(pool[k]):
                errs.append(f"컷 {i} 자세 '{s.get('pose')}' 는 이 사진에 쓸 수 없음 — {allowed_poses(pool[k])}")
            pl = str(s.get("place") or "")
            if not (3 <= len(pl) <= 90) or re.search(r"[가-힣]", pl):
                errs.append(f"컷 {i} place 는 사진 속 실제 자리를 영어로 짧게")
        key = (k, v, pp)
        if key in seen:
            errs.append(f"컷 {i} 같은 사진·같은 변주 반복")
        seen.add(key)
        if prev and prev == (k, v):
            errs.append(f"컷 {i} 바로 앞 컷과 같은 사진·같은 변주")
        prev = (k, v)
        if v != "original" or pp != "none":
            edits += 1
    if n_people > 3:
        errs.append("사람 컷은 최대 3개")
    if edits > MAX_EDITS:
        errs.append(f"편집 컷 {edits}개 — 최대 {MAX_EDITS}개(나머지는 original)")
    return errs


def plan_shots(models: dict, sig: dict, h: dict, req: dict, report: dict) -> list[dict]:
    pool = {int(p["k"]): p for p in usable_photos(h)}
    fmt = "single" if str(req.get("format") or "") == "single" else "montage"
    n = N_SHOTS[fmt]
    month = month_num(req)
    people_mode = "none" if str(req.get("people") or "back") == "none" else "back"
    ks = list(sig["photos"]) + ([sig["room_view"]] if sig.get("room_view") and fmt == "montage" else [])
    lines = [f"사진 {k} [{'객실 창(마지막 컷 전용)' if k == sig.get('room_view') and k not in sig['photos'] else '시그니처'}] {pool[k].get('description') or ''}\n"
             f"   쓸 수 있는 변주: {', '.join(allowed_variants(pool[k], month))} · 쓸 수 있는 자세: {', '.join(allowed_poses(pool[k]))}" for k in ks]
    content = (f"시그니처: {sig['name']} — {sig['what']}\n근거: {sig['fact']}\n활동(사실): {', '.join(a['name'] for a in sig['activities']) or '없음'}\n"
               f"시기: {req.get('month')} · 컷 수: {n} · 사람: {'뒷모습 허용' if people_mode == 'back' else '금지'}\n\n" + "\n".join(lines))
    fb = ""
    for attempt in range(3):
        try:
            js = _ask(models, PLAN_SYSTEM, content + fb, 0.5)
        except RuntimeError as e:
            js, errs = {}, [str(e)[:120]]
            continue
        errs = plan_errs(js, n, sig, pool, month, people_mode)
        if not errs:
            break
        log(f"컷 계획 검사 실패({attempt + 1}): {errs[:4]}")
        fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs[:8])
    else:
        log("컷 계획이 규칙을 못 지킴 → 안전한 기본 계획(시그니처 사진 원본·노을·해 질 녘·밤, 사람 없음)")
        js = {"shots": fallback_plan(sig, pool, n, month)}
    shots = []
    for i, s in enumerate(js["shots"], 1):
        p = pool[s["src"]]
        pp = s.get("people") or "none"
        shots.append({"i": i, "k": s["src"], "variant": s["variant"], "people": pp, "pose": s.get("pose") if pp != "none" else "", "place": s.get("place") if pp != "none" else "",
                      "source": p.get("source"), "src_url": p.get("src_url"), "category": p.get("category"), "view": p.get("view"),
                      "description": p.get("description") or "", "path": p["path"], "focus_x": p.get("focus_x", 0.5), "focus_y": p.get("focus_y", 0.5)})
    report["plan"] = [{k: s[k] for k in ("i", "k", "variant", "people", "pose", "place", "source", "description")} for s in shots]
    log("컷 계획: " + " · ".join(f"{s['i']}:{s['k']}/{VARIANT_KO[s['variant']]}{'/' + PEOPLE_KO[s['people']] if s['people'] != 'none' else ''}" for s in shots))
    return shots


def fallback_plan(sig: dict, pool: dict, n: int, month: int) -> list[dict]:
    order = ["original", "golden", "dusk", "night", "mist", "rain"]
    ks = list(sig["photos"])
    out, used = [], set()
    for i in range(n):
        k = ks[i % len(ks)]
        allowed = allowed_variants(pool[k], month)
        v = next((x for x in order if x in allowed and (k, x) not in used), "original")
        used.add((k, v))
        out.append({"src": k, "variant": v, "people": "none"})
    return out


# ── 4. 이미지 편집 + 검수 ────────────────────────────────────────────────────────────────
def edit_prompt(s: dict, retry_note: str = "") -> str:
    p = EDIT_KEEP + "CHANGE ONLY: " + (VARIANTS[s["variant"]] or "nothing about the light or weather.") + " "
    if s["people"] != "none":
        p += EDIT_PEOPLE.format(who=PEOPLE[s["people"]], pose=POSES.get(s["pose"], POSES["sit"]), place=s["place"] or "a natural spot")
    else:
        p += EDIT_NO_PEOPLE
    if retry_note:
        p += f"IMPORTANT: the previous attempt was rejected because: {retry_note}. Keep everything else identical. "
    return p + EDIT_TAIL


def _fake_edit(base: Path, s: dict, out: Path) -> Path:
    im = Image.open(base).convert("RGB")
    tint = {"golden": (255, 170, 90), "dusk": (70, 90, 170), "night": (20, 30, 70), "rain": (120, 130, 140), "snow": (235, 240, 250),
            "mist": (210, 215, 225), "steam": (240, 240, 240), "original": (255, 255, 255)}[s["variant"]]
    over = Image.new("RGB", im.size, tint)
    im = Image.blend(im, over, 0.35 if s["variant"] != "original" else 0.0)
    if s["people"] != "none":
        d = ImageDraw.Draw(im)
        w, hh = im.size
        d.ellipse((int(w * 0.42), int(hh * 0.62), int(w * 0.52), int(hh * 0.68)), fill=(40, 30, 25))
    im.save(out, "PNG")
    return out


def edit_image(base: Path, prompt: str, out: Path, s: dict, rep: dict) -> Path:
    """사진 1장 편집(돈). 한 번 실행·한 달 한도를 **돈 쓰기 전에** 본다(make_mini.composite 와 같은 규칙). 장부 kind image."""
    if FAKE_IMG:
        rep["image_model"] = "FAKE"
        return _fake_edit(base, s, out)
    models = rep.get("image_models") or make_mini.image_models(rep.get("image_prefer"))
    rep["image_models"] = models                                           # 모델 목록은 한 번만 묻는다
    parts = [{"text": prompt}, {"text": "Attached image: the HOTEL PHOTOGRAPH to edit."},
             {"inline_data": {"mime_type": "image/jpeg", "data": _b64(base, 1536)}}]
    last = None
    for model in models:
        krw = make_mini.image_krw(model)
        used = veo.month_total("all")
        if used + krw > veo.MONTH_KRW:
            raise RuntimeError(f"이번 달 한도({veo.MONTH_KRW:,.0f}원) — 지금 {used:,.0f}원")
        if veo._state["spent"] + krw > veo.RUN_KRW:
            raise RuntimeError(f"한 번 실행 한도({veo.RUN_KRW:,.0f}원) — 여기까지 {veo._state['spent']:,.0f}원")
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": "9:16"}}}
        try:
            data = make_mini._post(f"models/{model}:generateContent", body)
        except RuntimeError as e:
            last = e
            if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                log(f"이미지 모델 {model} 사용 불가 → 다음: {str(e)[:120]}")
                continue
            raise
        veo.record_est("image", krw, f"{model} 시그니처 변주 {out.name} (추정)")
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
            im = design.cover(Image.open(out).convert("RGB"), ms.W, ms.H)    # 9:16 1080×1920 로 맞춘다(가운데 기준)
            im.save(out, "PNG")
            return out
        last = RuntimeError(f"이미지 없음 (finish {[c.get('finishReason') for c in data.get('candidates') or []]})")
        log(f"편집 결과에 이미지가 없음: {str(last)[:120]}")
    raise RuntimeError(f"편집 실패: {last}")


def edge_keep(a: Path, b: Path) -> float:
    """원본의 윤곽선이 변주에서 얼마나 남았나(0~1) — 0원. 시간·날씨만 바뀌면 높고, 건물·물가를 다시 그리면 떨어진다. 기록용(문턱 미정 — 실측으로 정한다)."""
    def edges(p: Path):
        g = Image.open(p).convert("L").resize((270, 480), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))
        e = g.filter(ImageFilter.FIND_EDGES)
        px = sorted(e.getdata())
        thr = px[int(len(px) * 0.85)] if px else 0
        return e.point(lambda v: 255 if v > max(thr, 12) else 0)
    ea, eb = edges(a), edges(b).filter(ImageFilter.MaxFilter(5))
    pa, pb = ea.load(), eb.load()
    w, hh = ea.size
    tot = sum(1 for y in range(hh) for x in range(w) if pa[x, y])
    if not tot:
        return 1.0
    hit = sum(1 for y in range(hh) for x in range(w) if pa[x, y] and pb[x, y])
    return round(hit / tot, 3)


VERIFY_SYSTEM = """너는 숙소 사진 변주 검수자다. 사진 2장: 사진 1 = 실제 숙소 원본, 사진 2 = AI 가 빛·날씨·사람만 바꿨어야 하는 변주.
**같은 장소·같은 구조인지 엄격하게** 본다. 빛·하늘색·빗줄기·눈·김·안개·물에 비친 빛, 그리고 요청한 사람은 허용한다.
- structure_changes: 건물·벽·창·지붕·수영장/탕 모양·물가·데크·난간·가구·식물·전망(바다·산) 방향과 위치 중 원본과 달라진 것
- added_objects: 원본에 없던 사물·시설·가구·조명기구·물·수영장·장식·글자·로고(요청한 사람·빗줄기·눈·김 제외)
- people: 사람 수, face_visible: 얼굴(눈·코·입)이 또렷이 보이는 사람이 있는가
- variant_visible: 요청한 변주가 실제로 보이는가
JSON 만: {"same_place":true/false,"structure_changes":["..."],"added_objects":["..."],"people":0,"face_visible":false,"text_or_logo":false,"variant_visible":true/false,"verdict":"ok"|"fail","reason":"한 줄"}"""


def verify(models: dict, base: Path, var: Path, s: dict) -> dict:
    want = f"요청한 변주: {VARIANT_KO[s['variant']]}" + (f" · 뒷모습 사람 {PEOPLE_KO[s['people']]}({POSE_KO.get(s['pose'], '')})" if s["people"] != "none" else " · 사람 없음")
    try:
        r = ms._try_models("vision", models["text"], lambda m: _json_vision(m, VERIFY_SYSTEM, want, [base, var]))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"검수 호출 실패: {str(e)[:80]}"}
    n_people = int(r.get("people") or 0) if str(r.get("people") or "0").isdigit() else 0
    want_people = s["people"] != "none"
    probs = []
    if r.get("verdict") != "ok" or r.get("same_place") is not True:
        probs.append(str(r.get("reason") or "같은 장소가 아님"))
    if r.get("structure_changes"):
        probs.append("구조 변경: " + ", ".join(map(str, r["structure_changes"]))[:120])
    if r.get("added_objects"):
        probs.append("새 사물: " + ", ".join(map(str, r["added_objects"]))[:120])
    if r.get("text_or_logo"):
        probs.append("글자·로고")
    if s["variant"] != "original" and r.get("variant_visible") is not True:
        probs.append(f"'{VARIANT_KO[s['variant']]}'이(가) 안 보임")
    if want_people and not (1 <= n_people <= 3):
        probs.append(f"사람 수 {n_people}")
    if not want_people and n_people:
        probs.append(f"사람이 생김({n_people})")
    if r.get("face_visible"):
        probs.append("얼굴이 보임")
    return {"ok": not probs, "reason": "; ".join(probs)[:240], "raw": {k: r.get(k) for k in ("same_place", "structure_changes", "added_objects", "people", "face_visible", "variant_visible", "reason")}}


def make_images(models: dict, shots: list[dict], report: dict) -> None:
    """컷마다 9:16 원본 크롭(src_<k>.png) → 필요한 컷만 편집(var_<i>.png) + 검수. 두 번 실패하면 원본으로(variant original · people none)."""
    SIG.mkdir(parents=True, exist_ok=True)
    rep = {"image_prefer": None}
    rows, tries = [], 0
    for s in shots:
        src = SIG / f"src_{s['k']}.png"
        if not src.exists():
            photos.crop_9x16(s["path"], src, s["focus_x"], s["focus_y"], ms.W, ms.H)
        s["src_img"] = src.name
        if s["variant"] == "original" and s["people"] == "none":
            s["img"], s["verify"] = src.name, {"ok": True, "reason": "원본"}
            rows.append({"i": s["i"], "variant": "original", "ok": True}); continue
        out = SIG / f"var_{s['i']}.png"
        note, res = "", None
        for attempt in range(2):
            if tries >= EDIT_TRIES:
                res = {"ok": False, "reason": f"이번 실행 편집 호출 상한({EDIT_TRIES}번) — 원본으로"}
                break
            tries += 1
            try:
                edit_image(src, edit_prompt(s, note), out, s, rep)
            except RuntimeError as e:
                res = {"ok": False, "reason": f"편집 실패: {str(e)[:120]}"}
                if "한도" in str(e):
                    break
                continue
            res = verify(models, src, out, s)
            res["edge_keep"] = edge_keep(src, out)
            if res["ok"]:
                break
            note = res["reason"]
            log(f"컷 {s['i']} 변주 검수 탈락({attempt + 1}): {res['reason'][:120]}")
        if res and res.get("ok"):
            s["img"], s["verify"] = out.name, res
        else:
            s["fallback"] = f"{VARIANT_KO[s['variant']]}{'·' + PEOPLE_KO[s['people']] if s['people'] != 'none' else ''} → 원본 ({(res or {}).get('reason', '')[:80]})"
            log(f"컷 {s['i']} 변주 포기 → 원본 사진: {s['fallback']}")
            s.update({"variant": "original", "people": "none", "pose": "", "place": "", "img": src.name, "verify": res or {"ok": False}})
        rows.append({"i": s["i"], "variant": s["variant"], "people": s["people"], "ok": bool((s.get("verify") or {}).get("ok")),
                     "edge_keep": (s.get("verify") or {}).get("edge_keep"), "fallback": s.get("fallback")})
    report["images"] = {"rows": rows, "image_krw": rep.get("image_krw", 0), "image_model": rep.get("image_model"), "edit_calls": tries}


# ── 5. 문구 ─────────────────────────────────────────────────────────────────────────────
TEXT_SYSTEM = """너는 숙소 쇼츠 카피라이터다. 영상은 음악만 깔리고 **한 문장을 컷마다 한 구절씩** 자막으로 보여 준다(나레이션 없음).
시청자에게 "이런 데 가면 이렇다"를 **2인칭 상상·현재형**으로 말한다(예: "문만 열면", "바다가 펼쳐지고", "노을이 지면", "몸을 담그면").
절대 규칙:
- 1인칭·체험·과거형 금지("다녀왔어요", "좋았어요", "-더라고요", "묵었는데", "저는", "우리"). 실제로 가 본 척하지 않는다.
- 숙소 이름 금지(영상에서는 비공개). 가격 숫자 금지. "최고·유일·최저가·완벽·무조건" 금지.
- 시설 이름은 그 컷의 '보이는 것'이나 시그니처 근거 사실에 있는 것만. 활동은 입력 '활동' 목록에 있는 것만.
- 구절(phrases)은 컷 수만큼, 컷 순서대로. 각 구절은 **띄어쓰기 포함 4~11자**, 그 컷 화면과 맞아야 한다(노을 컷이면 노을). 구절을 이어 읽으면 1~2문장.
  첫 구절은 시그니처를 던지며 궁금하게, 마지막 구절은 "…숙소예요/…곳이에요" 처럼 닫는다. '~니다' 금지.
- hook_title: 첫 컷 위쪽에 크게 뜨는 제목. 입력의 '훅 제목 유형'으로, 공백 제외 6~14자(8~12 권장), 한 줄은 띄어쓰기 단위로 약 7자,
  핵심 낱말 하나만 [대괄호], 물음표로 끝, 숙소·지역 이름·가격·마침표·느낌표 금지. 구절을 그대로 옮기지 않는다.
- caption: empathy(공감 첫 줄, 시청자의 상황) · twist(반전 한 줄 — 시그니처) · scene(2인칭 감각 장면 1~2줄) · save(저장 권유, 시기와 연결 예: "추워지기 전에 저장해두세요").
- checklist: 사실 목록의 번호를 골라 짧게 옮긴 체크 항목 2~4개(가격·과장 금지, 사실에 없는 내용 추가 금지).
- title: 유튜브 제목 12~28자(숙소 이름 포함 — 제목·캡션은 텍스트라 이름을 쓴다). hashtags 5개.
JSON 만: {"phrases":["..."],"hook_title":"...","caption":{"empathy":"...","twist":"...","scene":["..."],"save":"..."},
 "checklist":[{"fact":번호,"text":"..."}],"title":"...","hashtags":["#..."]}"""


def _shot_seen(s: dict) -> str:
    seen = s["description"]
    if s["variant"] != "original":
        seen += f" — {VARIANT_KO[s['variant']]}"
    if s["people"] != "none":
        seen += f" — 뒷모습 사람 {PEOPLE_KO[s['people']]}({POSE_KO.get(s['pose'], '')})"
    return seen


def phrase_errs(ph: list, shots: list[dict], sig: dict, h: dict, req: dict, facts: list[str]) -> list[str]:
    errs = []
    if len(ph) != len(shots):
        return [f"phrases {len(ph)}개 — 컷 수 {len(shots)}개와 같게"]
    toks = so.name_tokens(h["name"], req, h)
    corpus = " ".join(facts)
    for i, (t, s) in enumerate(zip(ph, shots), 1):
        t = design.one_line(t)
        L = len(t)
        if not (3 <= L <= 12):
            errs.append(f"구절 {i} '{t}' {L}자 — 4~11자")
        elif not design.fits(t, "subtitle")[0]:
            errs.append(f"구절 {i} '{t}' 이 자막 한 줄에 안 들어감 — 줄인다")
        if PAST_RX.search(t) or FIRST_RX.search(t):
            errs.append(f"구절 {i} '{t}' 1인칭·체험·과거형 — 2인칭 상상·현재형으로")
        if so.ENDING_RX.search(t):
            errs.append(f"구절 {i} '~니다' — '~해요'체로")
        if any(k in t for k in toks):
            errs.append(f"구절 {i} 숙소 이름 금지")
        if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", t):
            errs.append(f"구절 {i} 가격 숫자 금지")
        for d in DIGIT_RX.findall(t):
            if d not in corpus:
                errs.append(f"구절 {i} 숫자 '{d}' 는 사실 목록에 없음"); break
        for b in list(ms.BANNED) + list(mt.WORDING_BAN):
            if b in t:
                errs.append(f"구절 {i} 금지 표현 '{b}'"); break
        if so.cold_month(req) and so.SUMMER_TALK_RX.search(t):
            errs.append(f"구절 {i} 겨울 편에 여름 해변 시설")
        allow = f"{s['description']} {sig['fact']} {' '.join(a['fact'] for a in sig['activities'])}"
        bad = [x for x in photos.facility_terms(t) if not photos.term_ok(x, allow)]
        if bad:
            errs.append(f"구절 {i} 시설 이름 '{'/'.join(bad)}' 는 이 컷 사진·근거 사실에서 확인 안 됨")
    return errs


def caption_errs(cap: dict, h: dict, req: dict, sig: dict, facts: list[str]) -> list[str]:
    errs = []
    lines = [cap.get("empathy"), cap.get("twist"), *(cap.get("scene") or []), cap.get("save")]
    allow = " ".join(facts) + " " + sig["fact"]
    for t in [str(x or "") for x in lines]:
        if not t.strip():
            errs.append("caption 빈 줄"); continue
        if PAST_RX.search(t) or FIRST_RX.search(t):
            errs.append(f"caption '{t[:20]}' 1인칭·체험·과거형")
        if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", t):
            errs.append(f"caption '{t[:20]}' 가격 숫자")
        bad = [x for x in photos.facility_terms(t) if not photos.term_ok(x, allow)]
        if bad:
            errs.append(f"caption 시설 이름 '{'/'.join(bad)}' 는 사실에 없음")
        for b in ms.BANNED:
            if b in t:
                errs.append(f"caption 금지 표현 '{b}'"); break
    return errs


def grounded_checklist(items: list, facts: list[str], h: dict) -> list[str]:
    """체크 항목은 사실 번호에 묶는다. 옮긴 글이 원문과 낱말이 절반도 안 겹치거나 원문에 없는 숫자가 있으면 원문 그대로 쓴다."""
    out = []
    for it in items or []:
        fi = _int(it.get("fact")) if isinstance(it, dict) else None
        if fi is None or not (1 <= fi <= len(facts)):
            continue
        src = facts[fi - 1]
        txt = design.one_line(str(it.get("text") or ""))[:40]
        ta, tb = _tokens(txt), _tokens(src)
        if not txt or not ta or _overlap(ta, tb) / len(ta) < 0.5 or any(d not in src for d in DIGIT_RX.findall(txt)) or PAST_RX.search(txt):
            txt = re.sub(r"^(블로그 교차 확인 시설|공식 홈페이지 한 줄 요약|후보표 훅): ", "", src)[:40]
        if txt not in out:
            out.append(txt)
    band = make_folder.price_band(h["name"])
    if band:
        out.append(f"1박 {band}")
    if h.get("honest"):
        out.append(f"후기 속 아쉬움: {h['honest']}")
    return out[:6]


def write_text(models: dict, shots: list[dict], sig: dict, h: dict, req: dict, report: dict) -> dict:
    facts = facts_list(h)
    ttype = so.next_title_type()
    content = (f"시그니처: {sig['name']} — {sig['what']} (왜 의외: {sig['why']})\n근거 사실: {sig['fact']}\n"
               f"활동(사실): {', '.join(a['name'] for a in sig['activities']) or '없음'}\n시기: {req.get('month')} · 테마: {req.get('theme')}\n"
               f"훅 제목 유형: {ttype} — {so.TITLE_TYPES[ttype]}\n최근 제목(다시 쓰지 말 것): {' / '.join(so.recent_titles()) or '없음'}\n"
               f"숙소 이름(제목·캡션용, 구절·훅 제목에는 금지): {h['name']}\n\n컷(순서대로, 화면에 보이는 것):\n"
               + "\n".join(f"컷 {s['i']}: {_shot_seen(s)}" for s in shots)
               + "\n\n사실(번호 — 체크리스트용):\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)))
    fb, js, errs = "", {}, []
    for attempt in range(3):
        try:
            js = _ask(models, TEXT_SYSTEM, content + fb, 0.7)
        except RuntimeError as e:
            errs = [str(e)[:120]]
            continue
        ph = [design.one_line(str(x)) for x in (js.get("phrases") or [])]
        cap = js.get("caption") if isinstance(js.get("caption"), dict) else {}
        title = design.one_line(str(js.get("hook_title") or ""))
        terrs = so.hook_title_errs(title, " ".join(ph), h, req, {"i": 1, "shot": {"description": f"{shots[0]['description']} {sig['fact']}"}})
        errs = phrase_errs(ph, shots, sig, h, req, facts) + caption_errs(cap, h, req, sig, facts)
        if not errs:                                                    # 구절·캡션은 통과 — 훅 제목만 틀리면 제목만 다시 받고(몇 원), 그래도 안 되면 제목 없이(make_solo 와 같은 처리)
            if terrs:
                hook_cut = {"i": 1, "section": "hook", "shot": {"description": f"{shots[0]['description']} {sig['fact']}"}}
                tmp = {"hook_title": title, "hook_title_type": ttype, "cuts": [{"i": 1, "narration": " ".join(ph)}]}
                tmp = ms._try_models("text", models["text"], lambda m: so.ensure_hook_title(m, tmp, [hook_cut], h, req))
                js["hook_title"] = tmp.get("hook_title") or ""
                if tmp.get("hook_title_missing"):
                    report["hook_title_missing"] = tmp["hook_title_missing"]
            break
        errs += [f"hook_title: {e}" for e in terrs]
        log(f"문구 검사 실패({attempt + 1}): {errs[:4]}")
        fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs[:10])
    else:
        report["text_errs"] = errs
        raise RuntimeError(f"문구가 규칙을 3번 못 지킴: {errs[:3]}")
    title = js.get("title") or ""
    if h["name"] not in title:
        title = f"{h['name']} {title}".strip()
    text = {"phrases": ph, "hook_title": design.one_line(js.get("hook_title") or ""), "hook_title_type": ttype, "caption": js["caption"],
            "checklist": grounded_checklist(js.get("checklist"), facts, h), "title": title[:40],
            "hashtags": [t if str(t).startswith("#") else f"#{t}" for t in (js.get("hashtags") or [])][:5]}
    log(f"훅 제목: {text['hook_title']} · 구절: {' / '.join(ph)}")
    return text


# ── 6. 렌더 ─────────────────────────────────────────────────────────────────────────────
def photo_clip(image: Path, sec: float, out: Path, pattern: str, M: float = MOTION_SIG) -> Path:
    """make_solo.photo_clip 과 같은 가속·감속 무빙, 폭만 짧은 컷에 맞게(기본 12%)."""
    F = max(2, int(round(sec * ms.FPS)))
    t = f"(on/{F})"
    eo = f"(1-pow(1-{t},2))"
    io = f"({t}*{t}*(3-2*{t}))"
    z = {"push": f"1.0+{M}*{eo}", "pull": f"1.0+{M}*(1-{eo})", "pan": f"1.0+{M}*0.8+{M}*0.2*{io}",
         "tilt": f"1.0+{M}*0.8+{M}*0.2*{io}", "diag": f"1.0+{M}*{eo}"}[pattern]
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    x = {"push": cx, "pull": cx, "pan": f"(iw-iw/zoom)*{io}", "tilt": cx, "diag": f"(iw-iw/zoom)*(0.5-0.4*{eo})"}[pattern]
    y = {"push": cy, "pull": cy, "pan": cy, "tilt": f"(ih-ih/zoom)*(1-{io})", "diag": f"(ih-ih/zoom)*(0.5+0.4*{eo})"}[pattern]
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(ms.FPS), "-i", str(image),
            "-vf", f"scale=2160:3840:flags=lanczos,zoompan=z='{z}':x='{x}':y='{y}':d={F}:s=1080x1920:fps={ms.FPS},setsar=1",
            "-frames:v", str(F), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)])
    return out


def veo_hero(shot: dict, report: dict, theme: str) -> Path | None:
    """제작 때만: 첫 컷(사람 없음)을 Veo 4초로 — 빛·물·김·비만 움직인다(294원). 실패하면 None(사진 무빙)."""
    img = SIG / shot["img"]
    small = SIG / "veo_in.png"
    Image.open(img).convert("RGB").resize((720, 1280), Image.LANCZOS).save(small, "PNG")
    out = SIG / "veo_hook.mp4"
    prompt = VEO_SIG.format(motion=VEO_MOTION.get(shot["variant"], VEO_MOTION["original"]))
    row = {"ok": False}
    before = veo.spent_this_run()
    try:
        veo.make_clip(prompt, small, 4, out, veo.seed_for(theme, "sig", shot["k"]))
        row["ok"] = True
    except veo.VeoError as e:
        row["error"] = str(e)[:160]
        log(f"첫 컷 Veo 실패 → 사진 무빙: {row['error']}")
    row["krw"] = round(veo.spent_this_run() - before)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": [row], "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}
    return out if row["ok"] else None


def compare_sheet(shots: list[dict], text: dict, out: Path) -> Path:
    """원본 | 변주를 컷마다 한 줄씩 — 운영자 검수용(공식 사진이 들어 있어 커밋·Release 금지, 텔레그램·아티팩트로만)."""
    tw, th, pad = 300, 533, 16
    rows = len(shots)
    im = Image.new("RGB", (tw * 2 + pad * 3 + 420, rows * (th + pad) + pad), (18, 20, 26))
    d = ImageDraw.Draw(im)
    f, fs = design.font(26), design.font(22, bold=False)
    for r, s in enumerate(shots):
        y = pad + r * (th + pad)
        for c, name in enumerate((s["src_img"], s["img"])):
            try:
                t = Image.open(SIG / name).convert("RGB").resize((tw, th), Image.LANCZOS)
                im.paste(t, (pad + c * (tw + pad), y))
            except Exception:  # noqa: BLE001
                d.rectangle((pad + c * (tw + pad), y, pad + c * (tw + pad) + tw, y + th), fill=(40, 40, 48))
        x = pad * 3 + tw * 2
        ok = (s.get("verify") or {}).get("ok")
        d.text((x, y + 6), f"컷 {s['i']} · {VARIANT_KO[s['variant']]}" + (f" · 사람 {PEOPLE_KO[s['people']]}" if s["people"] != "none" else ""), font=f, fill=(255, 255, 255))
        d.text((x, y + 46), "검수 통과" if ok else "원본 사용", font=fs, fill=(94, 234, 212) if ok else (255, 180, 120))
        ek = (s.get("verify") or {}).get("edge_keep")
        if ek is not None:
            d.text((x, y + 80), f"윤곽선 유지 {ek:.2f}", font=fs, fill=(200, 200, 200))
        d.text((x, y + 120), f"자막: {text['phrases'][r] if r < len(text['phrases']) else ''}", font=f, fill=(255, 255, 255))
        if s.get("fallback"):
            for j, ln in enumerate([s["fallback"][i:i + 18] for i in range(0, len(s["fallback"]), 18)][:5]):
                d.text((x, y + 170 + j * 30), ln, font=fs, fill=(255, 150, 150))
    im.save(out, "JPEG", quality=86)
    return out


def preview_md(req: dict, sig: dict, shots: list[dict], text: dict, h: dict, pos: int, folder: str, report: dict, preview: bool) -> str:
    md = [f"# 시그니처 {'미리보기' if preview else '제작'} — {h['name']} · {req.get('region')} · {req.get('theme')} · {req.get('month')}",
          f"형식: {'한 장면' if str(req.get('format')) == 'single' else '몽타주'} · 음악만(나레이션 없음) · 프로필 {pos}번 ({folder}) · 영상에서는 숙소 이름 비공개", "",
          "## 시그니처", "", f"- **{sig['name']}** — {sig['what']}", f"- 근거(사실 {sig['fact_i']}): {sig['fact']}",
          f"- 의외성 {sig.get('surprise')} · 왜: {sig.get('why')}", f"- 확인된 사진: {', '.join(map(str, sig['photos']))} · 객실 창 사진: {sig.get('room_view')}",
          f"- 활동(사실): {', '.join(a['name'] for a in sig['activities']) or '없음'} · 다른 후보: {', '.join(map(str, sig.get('alternatives') or [])) or '-'}", "",
          "## 컷", "", "| 컷 | 사진 | 변주 | 사람 | 검수 | 자막 구절 |", "|---|---|---|---|---|---|"]
    for r, s in enumerate(shots):
        v = s.get("verify") or {}
        md.append(f"| {s['i']} | {s['description'][:40]} [{mt.SRC_KO.get(s.get('source'), '?')}] | {VARIANT_KO[s['variant']]} | "
                  f"{PEOPLE_KO.get(s['people'], '-') if s['people'] != 'none' else '-'} | {'통과' if v.get('ok') else '원본'}{(' · ' + s['fallback']) if s.get('fallback') else ''} | {text['phrases'][r]} |")
    c = text["caption"]
    md += ["", "## 훅 제목", "", (f"**{text['hook_title']}** ({text['hook_title_type']})" if text.get("hook_title") else f"(제목 없음 — 규칙에 맞는 후보가 없었다: {report.get('hook_title_missing')})"), "", "## 캡션", "",
           c.get("empathy", ""), c.get("twist", ""), *(c.get("scene") or []), "", *[f"· {x}" for x in text["checklist"]], "", c.get("save", ""),
           "", f"제목: {text['title']} · 해시태그: {' '.join(text['hashtags'])}", "",
           "## 비용", "", f"- 이미지 편집 약 {report.get('images', {}).get('image_krw', 0):,}원 · Veo {round(veo.spent_this_run() - report.get('images', {}).get('image_krw', 0)):,}원(추정)"]
    return "\n".join(md) + "\n"


def render(shots: list[dict], text: dict, h: dict, req: dict, report: dict, preview: bool, folder: str, pos: int) -> tuple[Path, float, list]:
    theme = str(req.get("theme") or "")
    style = str(req.get("caption_style") or design.DEFAULT_STYLE)
    frame = SIG / "ov_frame.png"
    design.frame_png(frame, ms.DISCLOSURE)
    hero_clip = None if preview else veo_hero(shots[0], report, theme)
    if preview:
        report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": [], "spent_krw": 0, "month_total_krw": round(veo.month_total())}
    segs, timeline = [], []
    n = len(shots)
    for j, s in enumerate(shots):
        i = s["i"]
        L = DUR["hook"] if j == 0 else (DUR["last"] if j == n - 1 else DUR["mid"])
        overlays = [{"path": frame, "a": 0, "b": 99, "anim": False}]
        if j == 0 and text.get("hook_title"):
            ttl = SIG / "ov_title.png"
            design.hook_title_png(ttl, text["hook_title"])
            overlays.append({"path": ttl, "a": 0.0, "b": 99, "anim": False})          # 0초부터(첫 화면 = 썸네일)
        cap = SIG / f"ov_cap_{i:02d}.png"
        design.subtitle_png(cap, text["phrases"][j])
        overlays.append({"path": cap, "a": 0.0 if j == 0 else 0.08, "b": 99, "anim": j > 0, "fade": 0.12, "slide": 8})
        if j == 0 and hero_clip:
            src, kind, slow = hero_clip, "Veo", 1.0
            L = max(L, min(ms.probe_duration(hero_clip), 4.2))
        else:
            pattern = PATTERNS[j % len(PATTERNS)]
            src = photo_clip(SIG / s["img"], L, SIG / f"pan_{i}.mp4", pattern)
            kind, slow = f"사진·{pattern}", 1.0
        segs.append(so.cut_segment(100 + i, src, L, None, overlays, slow))
        timeline.append({"i": i, "kind": kind, "sec": round(L, 2), "variant": s["variant"], "people": s["people"], "phrase": text["phrases"][j],
                         "title": text["hook_title"] if j == 0 else None, "fallback": s.get("fallback")})
    card = design.end_card(SIG / "end_card.jpg", SIG / shots[0]["img"], folder, pos, style, ms.DISCLOSURE)
    segs.append(so.cut_segment(199, card, DUR["card"], None, [], image=True, fade_in=0.3))
    timeline.append({"i": "끝", "kind": "카드", "sec": DUR["card"]})
    (SIG / "concat.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in segs), encoding="utf-8")
    nob = SIG / "video_nomusic.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(SIG / "concat.txt"), "-c", "copy", "-movflags", "+faststart", str(nob)])
    total = ms.probe_duration(nob)
    video = ms.BUILD / "video.mp4"
    bgm_req = req.get("bgm", True)
    bgm_path = so.BGM if bgm_req is True else (mt.ROOT / "assets" / "music" / f"{bgm_req}.mp3" if isinstance(bgm_req, str) else None)
    if bgm_path and bgm_path.exists():
        so.mix_bgm(nob, bgm_path, video, total, level=MUSIC_LEVEL)
        report["bgm"] = bgm_path.name
    else:
        shutil.copy(nob, video)
        report["bgm"] = None
    return video, total, timeline


# ── 7. 계획 저장·재사용 ─────────────────────────────────────────────────────────────────
H_KEYS = ("name", "city", "room_names", "verified_facilities", "theme_hits", "blog_30d", "blog_total", "min_price", "honest", "photo_counts",
          "official_facts", "signature", "hook", "affiliate_url", "official_site", "rooms")


def save_plan(req: dict, h: dict, pos0: int, sig: dict, shots: list[dict], text: dict) -> Path:
    keep = ("i", "k", "variant", "people", "pose", "place", "source", "src_url", "category", "view", "description", "src_img", "img", "verify", "fallback")
    plan = {"version": 1, "stay": h["name"], "format": str(req.get("format") or "montage"), "month": req.get("month"), "theme": req.get("theme"), "region": req.get("region"),
            "pos0": pos0, "h": {k: h.get(k) for k in H_KEYS}, "signature": sig, "shots": [{k: s.get(k) for k in keep} for s in shots], "text": text}
    out = SIG / "plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def find_reuse(req: dict) -> dict | None:
    """미리보기 실행의 아티팩트(build/reuse/<이름>/…/sig/plan.json)에서 같은 숙소·형식의 계획을 찾아 이미지와 함께 build/sig 로 가져온다."""
    if not req.get("reuse_runs") or not REUSE_DIR.exists():
        return None
    want = str(req.get("stay") or "").strip()
    fmt = str(req.get("format") or "montage")
    for f in sorted(REUSE_DIR.glob("*/**/sig/plan.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            plan = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if (want and plan.get("stay") != want) or plan.get("format", "montage") != fmt:
            continue
        need = {s["img"] for s in plan["shots"]} | {s["src_img"] for s in plan["shots"]}
        if not all((f.parent / n).exists() for n in need):
            log(f"재사용 계획 {f} — 이미지 파일이 빠짐 → 건너뜀"); continue
        SIG.mkdir(parents=True, exist_ok=True)
        for n in need:
            shutil.copy(f.parent / n, SIG / n)
        log(f"미리보기 계획 재사용(이미지 0원): {f.relative_to(REUSE_DIR)}")
        return plan
    return None


# ── 진입점 ──────────────────────────────────────────────────────────────────────────────
def produce_sig(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    preview = str(req.get("stage") or "") == "preview"
    if SIG.exists():
        shutil.rmtree(SIG)
    SIG.mkdir(parents=True, exist_ok=True)
    report["stage"] = "preview" if preview else "produce"
    report["format"] = str(req.get("format") or "montage")
    plan = None if preview else find_reuse(req)
    if plan:
        h, pos0, sig, text = plan["h"], plan.get("pos0") or 0, plan["signature"], plan["text"]
        shots = plan["shots"]
        report["reused_plan"] = True
        report["hotels"] = [{k: h.get(k) for k in H_KEYS if k in h}]
    else:
        h, pos0 = so.assets(req, models, report)
        sig = choose_signature(models, h, req, report)
        shots = plan_shots(models, sig, h, req, report)
        make_images(models, shots, report)
        text = write_text(models, shots, sig, h, req, report)
    report["signature"] = {k: sig.get(k) for k in ("name", "what", "fact", "photos", "room_view", "activities", "surprise", "why", "alternatives")}
    folder = mt.folder_name(req)
    try:
        pos = make_folder.place_hotel(req, h, pos0, None)                          # 대표 이미지는 바꾸지 않는다(변주는 공식 사진 파생물 — 페이지에 안 올림)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]}) — 순위표 위치로 대체")
        pos = pos0 or 1
    save_plan(req, h, pos0, sig, shots, text)
    video, total, timeline = render(shots, text, h, req, report, preview, folder, pos)
    compare_sheet(shots, text, ms.PREVIEW / "compare_sheet.jpg")
    (ms.PREVIEW / "preview.md").write_text(preview_md(req, sig, shots, text, h, pos, folder, report, preview), encoding="utf-8")
    if not preview:
        so.save_hook_title(h["name"], text)                                         # 다음 편은 다른 유형(번갈아) — 제작 때만 기록
    report["hook_title"] = {"title": text["hook_title"], "type": text["hook_title_type"]}
    report["script"] = {"hook_title": text["hook_title"], "title": text["title"], "caption": text["caption"], "checklist": text["checklist"],
                        "cuts": [{"i": s["i"], "narration": text["phrases"][j], "caption": VARIANT_KO[s["variant"]]} for j, s in enumerate(shots)]}
    report["screen_qa"] = [{"i": s["i"], "threshold": 7, "score": 10 if (s.get("verify") or {}).get("ok") else 0, "seen": s.get("fallback") or ""}
                           for s in shots if (s.get("verify") or {}).get("reason") != "원본"]
    report["timeline"] = timeline
    c = text["caption"]
    pc = h.get("photo_counts") or {}
    edited = any(s["variant"] != "original" or s["people"] != "none" for s in shots)
    caption = (ms.DISCLOSURE + "\n\n" + "\n".join([c.get("empathy", ""), c.get("twist", "")]).strip()
               + ("\n\n" + "\n".join(c.get("scene") or []) if c.get("scene") else "")
               + ("\n\n" + "\n".join(f"· {x}" for x in text["checklist"]) if text["checklist"] else "")
               + "\n\n" + str(c.get("save") or "저장해두고 다시 꺼내 보세요.") + "\n같이 갈 사람에게도 보내 주세요."
               + f"\n\n{h['name']}" + (f" · {h['city']}" if h.get("city") else "")
               + f"\n객실 타입·예약 링크는 프로필 링크 → {pos}번 ({folder})"
               + ("\n사진: 숙소 공식 홈페이지" if pc.get("official") else "")
               + ("\n일부 장면(시간·날씨·뒷모습 인물)은 AI로 연출했어요. 실제 모습과 다를 수 있어요." if edited else "")
               + "\n\n" + " ".join(text["hashtags"]))
    v = report.get("veo") or {}
    img_krw = int((report.get("images") or {}).get("image_krw") or 0)              # 장부상 한 번 실행 돈(spent_this_run)에는 이미지 편집도 들어 있다 → 나눠 적는다
    meta = {"mode": "signature", "label": "시그니처 미리보기(Veo 0원)" if preview else "시그니처 제작", "stage": report["stage"], "stay": h["name"],
            "signature": sig["name"], "title": text["title"], "caption": caption, "folder": folder, "folder_pos": pos, "bgm": report.get("bgm"),
            "pinned_comment": f"{h['name']} — 객실 타입·링크는 프로필 링크 → {pos}번 ({folder}) · 쿠팡 파트너스 링크 포함",
            "affiliate_urls": {h["name"]: h.get("affiliate_url")}, "lines": text["phrases"], "cuts": timeline, "ai_edited": edited,
            "image_krw": img_krw,
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": sum(1 for r in v.get("clips", []) if r.get("ok")), "clips_total": len(v.get("clips", [])),
                    "spent_krw": max(0, round(veo.spent_this_run()) - img_krw), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
