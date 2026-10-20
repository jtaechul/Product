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

# v8 (2026-10-19 운영자 "똑같은 사진을 여러 번 쓰는 건 말이 안 된다, 텀을 두고 반복되는 게 눈에 거슬린다" → A~E 전부):
#  A 패널은 같은 공간의 **다른 카메라 위치**(문가·침대 옆·바닥 가까이·창가…) — 사람·강아지 씬만 원본 각도(Veo 시작 장면의 충실도) · 환경 씬은 다른 각도
#  B 원본 사진은 영상에서 한 번만(패널이 떨어져 원본으로 돌아갈 때 이미 쓴 원본이면 여분 패널 → 없으면 그 컷을 뺀다) · 제안 = 훅 되돌아옴 폐기
#  C 숙소와 무관한 감정 인서트(집 창가의 강아지·현관의 목줄·해안도로 차창) 시트 1장(98원) → 훅 첫 컷·제안 컷
#  D 검수 등급: 시설·구조(풀·욕조·계단·창·침대…) 추가 = 탈락 / 작은 소품(조명·화분·쿠션) = 통과(기록) / 글자 = 그 시트 1회 재생성
FAKE = os.environ.get("SCENE_FAKE_IMAGE", "") == "1"                     # 로컬 시험: 시트 대신 원본에 색을 입힌 가짜 2×2(0원)
VIEW_ANGLES = ["from the same camera position as the photograph, framed a little tighter", "from the same spot, the camera turned a little to the left",
               "from the same spot, the camera turned a little to the right", "from the same spot, a little higher, looking slightly down"]   # 전망·바깥 사진은 자리를 옮기면 없는 난간·통창·건물을 지어낸다(#59 바다 사진 0/4) → 같은 자리에서 조금만
ANGLES = {                                                                 # 장소별 카메라 위치(환경 씬은 원본과 다른 각도로 — 같은 사진 느낌을 없앤다)
    "객실": ["from the doorway looking into the room", "from beside the bed looking toward the window", "low angle near the floor looking across the room",
             "from the window side looking back into the room"],
    "욕실": ["from the doorway", "close-up of the counter and mirror area", "low angle near the floor", "from the shower side looking back"],
    "수영장": ["from the pool edge at water level", "from the far end of the pool looking back", "from above the entry steps", "close-up of the water surface with the surroundings behind"],
    "온수탕·스파": ["from the edge of the bath at water level", "from the far side looking back", "from above the steps", "close-up of the water surface with the surroundings behind"],
    "물놀이": ["from the pool edge at water level", "from the far end looking back", "from above the entry steps", "close-up of the water with the surroundings behind"],
    "바다": VIEW_ANGLES, "외관": VIEW_ANGLES, "정원·산책로": VIEW_ANGLES, "테라스": VIEW_ANGLES,
    "_": ["from the same camera position as the photograph, framed a little tighter", "a few steps further back, wider", "low angle close to the ground",
          "from the side, along the length of the space"],
}
SAME_ANGLE = "the same camera position as the photograph"
FACILITY_RX = re.compile(r"풀|수영장|욕조|탕|계단|발코니|테라스|창|침대|소파|테이블|탁자|의자|가구|문|벽|천장|기둥|난간|데크|지붕|건물|방|복도|주방|싱크|세면대|거울|바다|산|pool|bath|tub|stair|balcony|window|bed|sofa|table|chair|door|wall|railing|deck|sea", re.I)
INSERTS = {                                                                # 숙소와 무관한 감정 장면(집·차 안) — 숙소처럼 보이면 안 된다
    "dog": [("worry", "a small cream-white dog waiting alone by a living-room window at home, seen from behind, grey rainy afternoon, no people"),
            ("depart", "a dog leash and car keys on a wooden console table by an apartment front door, soft morning light, no people"),
            ("road", "view through a car windshield on a coastal road with the sea on one side, a small cream-white dog's head seen from behind in the passenger seat"),
            ("window", "a small cream-white dog's paws on a car window glass, blurred sea outside, seen from inside the car")],
    "general": [("worry", "a half-packed suitcase open on a bed in an ordinary apartment bedroom, grey weekday morning, no people"),
                ("depart", "car keys and a thermos on a kitchen counter by the door, early morning light, no people"),
                ("road", "view through a car windshield on a coastal road, light rain, wipers mid-swipe, no people visible"),
                ("window", "a rain-streaked train or car window with blurred sea and sky outside, no people")],
}
INSERT_ACTION = {                                                          # 훅 AI 컷이 인서트 위에서 할 환경 움직임(사람·동물·차 낱말 없음 — make_story.ENV_BAN_RX 를 통과해야 한다)
    "worry": "light rain streaks down the window glass and the thin curtain sways very slightly",
    "depart": "soft morning light brightens slowly across the table and the wall",
    "road": "the coastal road and the sea glide past the windshield, the wipers sweep once",
    "window": "the blurred sea and sky slide past the glass as it moves along",
}
INSERT_PROMPT = """Create ONE image that is a 2x2 grid of four vertical 9:16 photographs separated by thin plain white gutters. These are ordinary everyday scenes at HOME or IN A CAR — they must NOT look like a hotel, resort or pool. Photorealistic, natural light, like phone travel-vlog footage. No text, numbers, captions, logos or watermarks. No faces: people, if any, are seen only from behind.
Panels (top-left, top-right, bottom-left, bottom-right):
{panels}"""
INSERT_CHECK = """너는 쇼츠 인서트 이미지 검수자다. 이미지 1장 = 2×2 패널(차례로 패널 1~4). 패널마다: hotel_like(호텔·리조트·수영장처럼 보이는가), text(글자·번호·로고), face_visible(얼굴이 보이는가),
dogs(강아지 수), looks_real(실사처럼 자연스러운가), what(한 줄 설명). JSON 만: {"panels":[{"n":1,"hotel_like":false,"text":false,"face_visible":false,"dogs":1,"looks_real":true,"what":"..."}]}"""
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
All four panels show the SAME real space as the photograph, like frames from one video shot inside it, but each panel is taken from the camera position written for it. Everything visible must stay consistent with the photograph: the same furniture pieces, materials, colors, floor, walls, window and the same view outside. Where the photograph does not show a part of the space, keep that part plain and simple. NEVER add a pool, bathtub, stairs, balcony, extra window, extra bed, extra door or any facility or furniture that the photograph does not show, and do not remove what it shows. Absolutely no text, numbers, captions, logos or watermarks anywhere in the image; bottles, packaging, signs, screens, books and labels must be blank with no lettering at all. Photorealistic.
Panels:
{panels}
Rules for people: only seen from behind, faces never visible, no eye contact with the camera, realistic adult size, no phones, cups or new objects in their hands. Nobody else appears. If a panel says "no people", it must contain no person and no animal."""
CHECK_SYSTEM = """너는 숙소 AI 스토리보드 검수자다. 이미지 1 = 실제 숙소 사진(원본). 이미지 2~5 = AI 가 같은 공간을 **다른 카메라 위치**에서 다른 순간으로 그린 패널(차례로 패널 1~4). 각도가 달라도 같은 공간이면 된다.
패널마다: same_place(같은 공간으로 보이는가 — 가구 종류·재질·색·창·바닥·전망이 원본과 일관), facilities_added(원본 사진에 없는 **시설·구조**가 생겼는가: 수영장·욕조·계단·발코니·창·침대·소파·문·난간·데크·건물 등 — 목록),
small_added(원본에 없는 **작은 소품**: 조명·화분·쿠션·수건·액자·그릇 등 — 목록), missing(원본에 보이는 **큰 사물·시설** 중 패널에서 사라진 것: 계단·침대·욕조·소파·창·문·난간 등 — 목록 · 각도가 달라 화면 밖으로 나간 것은 빼고, 그 자리인데 없어진 것만),
people(사람 수 · 손·팔만 보이면 "hand"), face_visible(눈·코·입이 보이는 얼굴이 있는가),
dogs(강아지 수), text(글자·번호·로고가 있는가), looks_real(실사처럼 자연스러운가 — 사람·강아지 몸·손가락이 이상하면 false).
JSON 만: {"panels":[{"n":1,"same_place":true,"facilities_added":[],"small_added":[],"missing":[],"people":0,"face_visible":false,"dogs":0,"text":false,"looks_real":true,"why":"한 줄"}]}"""


def log(*a):
    print("[scenes]", *a, flush=True)


def _sid_num(t: dict) -> int:
    """컷 id 의 숫자(S10 → 10). 글자 정렬이면 'S10' < 'S5' 라 S10 이 먼저 뽑힌다(#61 간판 사진이 그렇게 뽑혔다)."""
    return int(re.sub(r"\D", "", str(t.get("id") or "")) or 0)


# ── 1. 씬 계획(0원) ─────────────────────────────────────────────────────────────────
def plan_scenes(beats: list[dict], shots: dict, dog: bool, report: dict, end_scene: bool = True) -> list[dict]:
    """컷마다 씬 하나: 그 컷의 사진(장소) + 누가·동작(화면 계획의 actor) + 시간대(하루 흐름 — 앞은 낮, 뒤로 갈수록 저녁·밤).
    훅이 실제 강아지 사진이면(hook_keep) 원본 그대로. 옛 계획의 R(훅 재사용)은 씬 없음. end_scene=False 면 제안 컷 씬을 만들지 않는다(v8: 제안 = 인서트)."""
    n = len(beats)
    scenes: list[dict] = []
    order = ["day", "golden", "evening", "night"]
    for j, b in enumerate(beats):
        v = b.get("visual") or {}
        if v.get("type") == "R" or (j == 0 and b.get("hook_keep")):
            continue
        if not end_scene and j == n - 1 and str(b.get("lens") or "") in ("제안", "약속"):
            continue
        base_t = order[min(len(order) - 1, int(j * len(order) / max(1, n - 1)))] if n > 1 else "day"
        m = -1
        for sid in b.get("shots") or []:
            if sid not in shots or shots[sid].get("insert"):                             # v10.3: 재사용 계획(문제 시트만 다시)엔 인서트 컷이 이미 들어 있다 — 씬 아님
                continue
            m += 1
            s = shots[sid]
            who, act, with_dog = "env", "", False
            if m == 0 and v.get("actor") in ("couple", "back", "hand", "dog"):
                who, act, with_dog = v["actor"], str(v.get("action_en") or ""), bool(v.get("with_dog"))
            t = base_t if m == 0 else order[(order.index(base_t) + 1) % len(order)]
            if who == "dog" and not dog:
                who, act = "env", ""
            scenes.append({"n": len(scenes) + 1, "j": j, "m": m, "sid": sid, "k": s["k"], "place": s.get("place") or "", "who": who, "with_dog": with_dog,
                           "action_en": act[:200], "time": t, "src_img": s["img"], "img": None, "ok": None, "why": "", "panel_px": 0, "sheet": None, "angle": ""})
    assign_angles(scenes)
    report["scenes_planned"] = len(scenes)
    return scenes


def angles_for(place: str) -> list[str]:
    return ANGLES.get(place) or ANGLES["_"]


def assign_angles(scenes: list[dict]) -> None:
    """같은 참조 사진의 씬들에 카메라 위치를 나눠 준다(A): 사람·강아지 씬은 원본 각도(Veo 시작 장면 충실도), 환경 씬은 서로 다른 각도."""
    by_k: dict[int, list[dict]] = {}
    for sc in scenes:
        by_k.setdefault(sc["k"], []).append(sc)
    for k, group in by_k.items():
        angs = angles_for(group[0].get("place") or "")
        i = 0
        for sc in group:
            if sc.get("angle"):
                continue
            if sc["who"] in ("couple", "back", "hand", "dog"):
                sc["angle"] = SAME_ANGLE
            else:
                sc["angle"] = angs[i % len(angs)]; i += 1


def _panel_text(i: int, sc: dict) -> str:
    who = WHO_EN.get(sc["who"], "")
    if sc["who"] in ("env", "none") or not who:
        body = "no people, no animals"
    else:
        body = who + (f", who {sc['action_en']}" if sc.get("action_en") else "") + (DOG_EXTRA if sc.get("with_dog") else "")
    return f"{i}) camera: {sc.get('angle') or SAME_ANGLE}; {TIMES[sc['time']]}: {body}."


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
    fac, small = [], [str(x) for x in (r.get("small_added") or [])]
    for x in list(r.get("facilities_added") or r.get("structure_changes") or []) + list(r.get("added_objects") or []):
        (fac if FACILITY_RX.search(str(x)) else small).append(str(x))                  # 시설 목록에 소품(쿠션·액자)을 적었으면 소품으로 — 낱말 사전(FACILITY_RX)이 가른다
    if fac:
        probs.append("시설·구조 추가: " + ", ".join(fac)[:80])
    if small:
        sc["minor"] = ", ".join(small)[:80]                                            # 작은 소품은 통과(기록만)
    if sc.get("angle") == SAME_ANGLE:                                                  # 원본 각도 씬(사람·강아지 = Veo 시작 장면)은 원본의 시설·큰 사물이 빠져도 탈락 — #60 강아지 컷이 계단 없는 패널에서 시작해 Veo 가 계단을 지어냄(새 사물 탈락 · 294원)
        gone = [str(x) for x in (r.get("missing") or []) if FACILITY_RX.search(str(x))]
        if gone:
            probs.append("원본 시설 빠짐: " + ", ".join(gone)[:80])
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
    r, err = None, ""
    for attempt in range(2):                                                           # v10.3: 답이 잘리거나 비면 한 번 더(약 2원) — #61 시트 4가 '검수 호출 실패' 한 번에 패널 4개(98원)를 다 버렸다
        try:
            r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, CHECK_SYSTEM, want, [base] + panels, max_tokens=1500))
            if (r.get("panels") if isinstance(r, dict) else r):
                break
            err, r = "검수 답 비어 있음", None
        except Exception as e:  # noqa: BLE001
            err, r = str(e)[:60], None
        log(f"시트 검수 호출 실패({attempt + 1}/2): {err}")
    if r is None:
        return [{"ok": False, "why": f"검수 호출 실패: {err}", "raw": {}} for _ in group]
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
        out.append({"ok": ok, "why": why or str(p.get("why") or "")[:80], "raw": {k: p.get(k) for k in ("same_place", "facilities_added", "small_added", "missing", "structure_changes", "added_objects", "people", "face_visible", "dogs", "text", "looks_real")}})
    return out


# ── 2. 시트 생성·분할·검수 ──────────────────────────────────────────────────────────
SCENE_KEYS = ("n", "j", "m", "sid", "k", "place", "who", "with_dog", "action_en", "time", "img", "ok", "why", "panel_px", "sheet", "spare", "angle", "minor", "reused")


def scene_key(sc: dict) -> tuple:
    """같은 패널인가 — 같은 사진·누가·강아지·동작·시간대·카메라 위치(plan_scenes 는 결정적이라 같은 대본·컷이면 같은 키)."""
    return (int(sc["k"]), str(sc.get("who") or ""), bool(sc.get("with_dog")), str(sc.get("action_en") or "")[:200], str(sc.get("time") or ""), str(sc.get("angle") or ""))


def reuse_index(old_scenes: list[dict], story: Path) -> dict:
    """옛 미리보기의 씬 목록(plan.json text.scenes) → 키별 패널(파일이 있는 것만). v10.3 '문제 시트만 다시'의 재료."""
    out = {}
    for x in old_scenes or []:
        if x.get("img") and x.get("sheet") and (story / str(x["img"])).exists():
            out.setdefault(scene_key(x), x)
    return out


def make_sheets(models: dict, scenes: list[dict], shots: dict, story: Path, report: dict, reuse: dict | None = None, redo: dict | None = None) -> None:
    """참조 사진(k)별로 씬을 4개씩 묶어 시트 한 장씩(최대 MAX_SHEETS). 4개가 안 되면 빈 자리는 다른 시간대의 '사람 없음' 씬으로 채운다(여분 스틸).
    v10.3 reuse(옛 패널 키 → 씬) 가 있으면 **같은 패널이 다 있는 시트는 다시 만들지 않고 그 패널·검수 결과를 그대로**(0원) — redo 로 다시 만들 시트를 고른다:
    sheets "failed"(기본 · 컷 패널이 하나라도 탈락한 시트) / [번호…](옛 미리보기의 시트 번호) / "all". 새 시트 번호는 옛 번호 뒤부터(파일 이름 충돌 방지)."""
    rep = {"image_prefer": None}
    groups: dict[int, list[dict]] = {}
    for sc in scenes:
        groups.setdefault(sc["k"], []).append(sc)
    old = reuse or {}
    rd = redo or {}
    redo_list = {int(x) for x in rd.get("sheets")} if isinstance(rd.get("sheets"), list) else None
    redo_all = rd.get("sheets") == "all"
    sheets, n_sheet = [], max((int(x.get("sheet") or 0) for x in old.values()), default=0)
    spare_n = len(scenes)
    for k, group in groups.items():
        if not any(sc["m"] == 0 for sc in group):                                        # 꼬리 컷만 있는 사진은 시트를 안 만든다(돈) — 다른 사진이라 화면은 이미 바뀐다
            for sc in group:
                sc["ok"] = False; sc["why"] = "꼬리 컷은 원본(시트 생략)"
            continue
        chunks = [group[i:i + 4] for i in range(0, len(group), 4)]
        for chunk in chunks:
            redo_of = None
            matched = [old.get(scene_key(sc)) for sc in chunk] if old else []
            ns = {int(m_["sheet"]) for m_ in matched if m_}
            if old and all(matched) and len(ns) == 1:                                   # 옛 시트에 이 컷들의 패널이 다 있다 → 다시 만들지 말지
                n_old = ns.pop()
                failed = any(not m_.get("ok") for m_ in matched)
                want_redo = redo_all or (redo_list is not None and n_old in redo_list) or (redo_list is None and failed)
                if not want_redo:
                    for sc, m_ in zip(chunk, matched):
                        for key in ("img", "ok", "why", "panel_px", "minor", "check"):
                            if key in m_:
                                sc[key] = m_[key]
                        sc["sheet"], sc["reused"] = n_old, True
                    pad, taken = [], {sc.get("img") for sc in chunk}
                    for x in (x for x in old.values() if x.get("spare") and int(x.get("sheet") or 0) == n_old and x.get("img") not in taken):   # 그 시트의 여분 패널도 그대로(컷이 쓴 패널은 빼고)
                        spare_n += 1
                        pad.append({**x, "n": spare_n, "j": None, "m": None, "reused": True})
                    sheets.append({"n": n_old, "k": k, "ok": True, "reused": True, "panel_px": [sc["panel_px"] for sc in chunk + pad], "scenes": [sc["n"] for sc in chunk + pad],
                                   "passed": sum(1 for sc in chunk + pad if sc.get("ok")), "krw": 0, "angles": [str(sc.get("angle", ""))[:30] for sc in chunk + pad]})
                    scenes.extend(pad)
                    log(f"시트 {n_old} (사진 {k}) 재사용 · 통과 {sheets[-1]['passed']}/{len(chunk) + len(pad)} · 0원")
                    continue
                redo_of = n_old
                log(f"시트 {n_old} (사진 {k}) 다시 만든다" + (" — 컷 패널 탈락" if failed and redo_list is None else " — 운영자 지정" if redo_list is not None else ""))
            if len(sheets) >= MAX_SHEETS:
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
                            "action_en": "", "time": t, "src_img": shots[base_sid]["img"], "img": None, "ok": None, "why": "", "panel_px": 0, "sheet": None, "spare": True, "angle": ""})
            panel_scenes = chunk + pad
            used_ang = [sc.get("angle") for sc in panel_scenes if sc.get("angle")]
            for sc in pad:                                                              # 여분도 서로 다른 각도로
                sc["angle"] = next((a for a in angles_for(sc["place"]) if a not in used_ang), angles_for(sc["place"])[0]); used_ang.append(sc["angle"])
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
            if sum(1 for c in checks if "글자" in str(c.get("why") or "")) >= 2 and not FAKE:   # 글자가 들어간 시트 → 지시 강화해 1회 재생성(98원)
                try:
                    _, krw2 = _call_sheet(base, prompt + "\n\nIMPORTANT: the previous attempt contained text or numbers. Render ABSOLUTELY NO text, digits, labels, captions, logos or watermarks anywhere.", out, rep)
                    krw += krw2
                    with Image.open(out) as im:
                        W, H = im.size
                        boxes = photos.split_panels(str(out))
                        if len(boxes) != 4:
                            boxes = _grid_boxes(W, H)
                        for i, (sc, box) in enumerate(zip(panel_scenes, boxes)):
                            p = im.crop(box).convert("RGB")
                            design.cover(p, ms.W, ms.H).save(story / sc["img"], "PNG")
                            sc["panel_px"] = min(p.size)
                    checks = _check_sheet(models, base, panels, panel_scenes)
                    log(f"시트 {n_sheet} 글자 → 재생성 1회")
                except RuntimeError as e:
                    log(f"시트 {n_sheet} 재생성 실패: {str(e)[:80]}")
            for sc, c in zip(panel_scenes, checks):
                sc["ok"] = bool(c["ok"]) and sc["panel_px"] >= PANEL_MIN
                sc["why"] = c["why"] if not c["ok"] else ("" if sc["panel_px"] >= PANEL_MIN else f"패널이 작음 {sc['panel_px']}px")
                sc["check"] = c.get("raw")
            sheets.append({"n": n_sheet, "k": k, "ok": True, "redo_of": redo_of, "px": [W, H], "panel_px": [sc["panel_px"] for sc in panel_scenes], "scenes": [sc["n"] for sc in panel_scenes],
                           "passed": sum(1 for sc in panel_scenes if sc["ok"]), "krw": round(krw), "model": rep.get("image_model"),
                           "angles": [sc.get("angle", "")[:30] for sc in panel_scenes]})
            log(f"시트 {n_sheet} (사진 {k}) {W}×{H} · 패널 {[sc['panel_px'] for sc in panel_scenes]}px · 통과 {sheets[-1]['passed']}/4 · 약 {krw:,.0f}원")
            scenes.extend(pad)
    report["storyboard"] = {"sheets": sheets, "krw": sum(s.get("krw", 0) for s in sheets), "model": rep.get("image_model"), "fake": FAKE,
                            "reused": [s["n"] for s in sheets if s.get("reused")], "made": [s["n"] for s in sheets if not s.get("reused")],
                            "scenes": [{k_: sc.get(k_) for k_ in SCENE_KEYS if k_ != "action_en"} for sc in scenes]}


# ── 3. 컷에 적용 ─────────────────────────────────────────────────────────────────────
def apply_scenes(beats: list[dict], scenes: list[dict], shots: dict, report: dict | None = None) -> None:
    """통과한 패널을 그 컷의 화면으로(cut_imgs) · 탈락·없음은 원본 사진 — 단 **원본 사진은 영상에서 한 번만**(B · 같은 사진 k 의 다른 자르기도 같은 사진):
    이미 쓴 사진이면 같은 사진의 여분 패널(다른 각도·시간대), 그것도 없으면 그 컷을 뺀다(컷이 하나뿐인 문장은 어쩔 수 없이 원본 · '반복' 기록).
    인서트 컷(INS · 집·차 안)은 그 이미지 그대로. 사람·강아지 씬의 패널은 제작 때 Veo 시작 장면(start_img · in_frame = 사람이 이미 화면에 있어 '이미 있는 손·사람' 지시문)."""
    by = {(sc["j"], sc["sid"]): sc for sc in scenes if sc.get("j") is not None}
    spare_all = [sc for sc in scenes if sc.get("spare") and sc.get("ok")]
    scene_k = {sc["k"] for sc in scenes if sc.get("img")}                                 # 시트(패널)가 있는 사진 — 그 원본을 다른 컷에 쓰면 같은 사진 반복
    used_spare: set[str] = set()
    used_k: dict[int, int] = {}
    cuts_k: dict[int, int] = {}                                                            # 사진별 최종 컷 수(패널+원본) — 교체 패널도 사진당 2컷 안에서만(같은 방이 또 나오지 않게)
    dropped = []
    for j, b in enumerate(beats):
        imgs, kinds, keep, in_frame = [], [], [], False
        ids = list(b.get("shots") or [])
        for m, sid in enumerate(ids):
            s = shots.get(sid) or {}
            if s.get("insert"):
                imgs.append(s["img"]); kinds.append(f"인서트 {s.get('name') or ''}".strip()); keep.append(sid); continue
            sc = by.get((j, sid))
            if sc and sc.get("ok") and sc.get("img"):
                imgs.append(sc["img"]); kinds.append(f"AI 스토리보드 {WHO_KO.get(sc['who'], '')}·{TIME_KO[sc['time']]}"); keep.append(sid)
                cuts_k[sc["k"]] = cuts_k.get(sc["k"], 0) + 1
                if m == 0 and sc["who"] in ("couple", "back", "hand", "dog"):
                    in_frame = True
                continue
            k = sc["k"] if sc else s.get("k")
            alt = next((x for x in spare_all if x["k"] == k and x["img"] not in used_spare), None)
            need_orig = bool(sc and "원본 시설 빠짐" in str(sc.get("why") or "") and not used_k.get(k))   # 사람·강아지 패널에서 원본 시설이 빠졌으면 여분 패널(같은 시트)도 못 믿는다 → 원본(아직 안 썼을 때)에서 Veo 시작
            if alt and not need_orig and (sc is not None or used_k.get(k)):              # 탈락·시트 생략 컷, 또는 이미 쓴 사진 → 같은 사진의 여분 패널(다른 각도·시간대)
                used_spare.add(alt["img"]); imgs.append(alt["img"]); kinds.append(f"AI 스토리보드 여분·{TIME_KO[alt['time']]}"); keep.append(sid)
                cuts_k[k] = cuts_k.get(k, 0) + 1; continue
            orig = s.get("img") or ""
            swapped = ""
            if orig and used_k.get(k) and len(ids) > 1:                                 # 원본은 한 번만 — 아직 안 쓴 다른 사진(씬 없음)으로 바꾸고, 없으면 그 컷을 뺀다
                nb = {shots[y]["k"] for y in ids if y != sid and y in shots}
                if j > 0 and beats[j - 1].get("shots") and beats[j - 1]["shots"][-1] in shots:
                    nb.add(shots[beats[j - 1]["shots"][-1]]["k"])
                if j + 1 < len(beats) and beats[j + 1].get("shots") and beats[j + 1]["shots"][0] in shots:
                    nb.add(shots[beats[j + 1]["shots"][0]]["k"])
                first_place = shots[ids[0]].get("place") if ids[0] in shots else None
                lt = sg._tokens(b.get("line")) | sg._tokens(b.get("want"))

                def rel(t: dict) -> bool:                                               # v10.3: 첫 컷 교체는 문장과 관계있는 사진만(장점 사진 · 문장 낱말 겹침 · 같은 장소) — #61 조건 컷 밑에 간판 사진
                    return m > 0 or bool(t.get("adv")) or sg._overlap(lt, sg._tokens(t.get("desc"))) > 0 or (t.get("place") or "") == (s.get("place") or "")
                cand = sorted((t for t in shots.values() if not t.get("insert") and t["k"] >= 0 and t["k"] != k and not used_k.get(t["k"]) and t["k"] not in nb and t["k"] not in scene_k
                               and not (m == 0 and t.get("grade") == "insert") and rel(t)),   # 작은 패널(짧은 인서트)은 첫 컷·AI 시작 장면이 될 수 없다
                              key=lambda t: (t.get("place") == first_place, t.get("grade") == "insert", _sid_num(t)))
                if not cand:                                                            # 안 쓴 원본이 없으면 다른 사진의 여분 패널(이웃 컷과 다른 사진 · 그 사진도 2컷 안 · 첫 컷이면 관계있는 사진만)
                    alt2 = next((x for x in sorted(spare_all, key=lambda x: cuts_k.get(x["k"], 0)) if x["k"] != k and x["k"] not in nb and x["img"] not in used_spare
                                 and cuts_k.get(x["k"], 0) < 2 and rel(shots.get(x["sid"]) or {})), None)
                    if alt2:
                        used_spare.add(alt2["img"]); imgs.append(alt2["img"]); keep.append(alt2["sid"]); cuts_k[alt2["k"]] = cuts_k.get(alt2["k"], 0) + 1
                        kinds.append(f"AI 스토리보드 여분·{TIME_KO[alt2['time']]}(교체: {sid} 반복 방지)")
                        dropped.append(f"문장 {j + 1} 컷 {sid}(사진 {k} 원본 이미 씀) → 여분 패널 {alt2['img']}(사진 {alt2['k']})"); continue
                    dropped.append(f"문장 {j + 1} 컷 {sid}(사진 {k} 원본 이미 씀 · 대신 쓸 사진·패널 없음 → 뺌)"); continue
                t = cand[0]
                dropped.append(f"문장 {j + 1} 컷 {sid}(사진 {k} 원본 이미 씀) → {t['id']}(사진 {t['k']} · {t.get('place')})")
                swapped = f"(교체: {s.get('id')} → {t['id']} 반복 방지)"
                sid, s, k, orig, sc = t["id"], t, t["k"], t["img"], None
            skipped = bool(sc) and "시트 생략" in str(sc.get("why") or "")
            imgs.append(orig); keep.append(sid)
            used_k[k] = used_k.get(k, 0) + 1; cuts_k[k] = cuts_k.get(k, 0) + 1
            kinds.append(("원본 사진" if (not sc or sc.get("ok") or skipped) else f"원본 사진(패널 탈락: {sc.get('why', '')[:30]})") + swapped + (" · 반복" if used_k[k] > 1 else ""))
        if not keep and ids:                                                            # 전부 뺄 수는 없다 — 첫 컷을 원본(반복)으로 남긴다
            sid = ids[0]; keep, imgs, kinds = [sid], [shots.get(sid, {}).get("img") or ""], ["원본 사진 · 반복"]
            dropped[:] = [d for d in dropped if f"컷 {sid}(" not in d]
        if keep and keep != ids:
            b["shots"] = keep
        b["cut_imgs"], b["cut_kinds"] = imgs, kinds
        v = b.get("visual") or {}
        if v.get("type") in ("A", "B") and imgs:
            v["start_img"], v["in_frame"] = imgs[0], in_frame
            v["tail"] = keep[1] if len(keep) > 1 else None
    if report is not None:
        report["scene_drops"] = dropped
        if dropped:
            log(f"원본 반복 방지로 뺀 컷 {len(dropped)}: " + " / ".join(dropped[:4]))


# ── 4. 감정 인서트(C): 숙소와 무관한 집·차 안 장면 시트 1장 → 훅 첫 컷·제안 컷 ─────────
def plan_inserts(beats: list[dict], dog: bool) -> list[dict]:
    """훅 = '걱정' 장면을 숙소 장면 앞에, 제안 = '떠남' 장면(훅 되돌아옴 대신). 둘 다 숙소가 아닌 집·차 안."""
    if len(beats) < 2:
        return []
    sets = INSERTS["dog" if dog else "general"]
    want = [("hook", 0, sets[0]), ("end", len(beats) - 1, sets[1]), ("spare1", None, sets[2]), ("spare2", None, sets[3])]
    out = []
    for i, (role, j, (name, desc)) in enumerate(want):
        out.append({"n": i + 1, "role": role, "j": j, "name": name, "desc": desc, "img": None, "ok": None, "why": ""})
    return out


def _fake_insert_sheet(out: Path) -> Path:
    pw, ph, g = 760, 1350, 24
    sheet = Image.new("RGB", (pw * 2 + g * 3, ph * 2 + g * 3), "white")
    d = ImageDraw.Draw(sheet)
    for i, col in enumerate(((120, 140, 170), (170, 150, 120), (110, 160, 140), (150, 120, 160))):
        x, y = g + (i % 2) * (pw + g), g + (i // 2) * (ph + g)
        d.rectangle((x, y, x + pw, y + ph), fill=col)
        for yy in range(y, y + ph, 48):
            d.line([(x, yy), (x + pw, yy + 30)], fill=(col[0] + 80, col[1] + 80, col[2] + 80), width=12)
    sheet.save(out, "PNG")
    return out


def make_insert_sheet(models: dict, inserts: list[dict], story: Path, report: dict) -> None:
    """인서트 4장면을 시트 1장(약 98원)으로 — 참조 사진 없이 글만. 검수: 호텔처럼 보임·글자·얼굴·강아지 수(반려견 편은 1)."""
    if not inserts:
        return
    rep = {"image_prefer": None}
    out = story / "insert_sheet.png"
    prompt = INSERT_PROMPT.format(panels="\n".join(f"{i + 1}) {x['desc']}." for i, x in enumerate(inserts)))
    (story / "insert_prompt.txt").write_text(prompt, encoding="utf-8")
    krw = 0.0
    try:
        if FAKE:
            _fake_insert_sheet(out); rep["image_model"] = "FAKE"
        else:
            _, krw = _call_sheet_text(prompt, out, rep)
    except RuntimeError as e:
        log(f"인서트 시트 실패 → 인서트 없이: {str(e)[:100]}")
        for x in inserts:
            x["ok"] = False; x["why"] = f"시트 실패: {str(e)[:60]}"
        report["inserts"] = {"ok": False, "error": str(e)[:120], "krw": 0, "items": inserts}
        return
    with Image.open(out) as im:
        W, H = im.size
        boxes = photos.split_panels(str(out))
        if len(boxes) != 4:
            boxes = _grid_boxes(W, H)
        panels = []
        for i, (x, box) in enumerate(zip(inserts, boxes)):
            p = im.crop(box).convert("RGB")
            name = f"ins_{i + 1}.png"
            design.cover(p, ms.W, ms.H).save(story / name, "PNG")
            x["img"], x["panel_px"] = name, min(p.size)
            panels.append(story / name)
    if FAKE:
        for x in inserts:
            why = FAKE_CHECK.get(f"ins{x['n']}") or ""
            x["ok"], x["why"] = (not why) and x["panel_px"] >= PANEL_MIN, why
    else:
        try:
            r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, INSERT_CHECK, "패널 4개 · 숙소가 아닌 집·차 안 장면이어야 한다", [out]))
            by_n = {int(p["n"]): p for p in (r.get("panels") if isinstance(r, dict) else r) or [] if isinstance(p, dict) and str(p.get("n", "")).isdigit()}
        except Exception as e:  # noqa: BLE001
            by_n = {}
            log(f"인서트 검수 실패 → 전부 탈락: {str(e)[:60]}")
        for i, x in enumerate(inserts):
            pr = by_n.get(i + 1)
            probs = []
            if not pr:
                probs.append("검수 답 없음")
            else:
                if pr.get("hotel_like"):
                    probs.append("호텔처럼 보임")
                if pr.get("text"):
                    probs.append("글자")
                if pr.get("face_visible"):
                    probs.append("얼굴")
                if pr.get("looks_real") is False:
                    probs.append("실사 아님")
            x["ok"], x["why"] = (not probs) and x["panel_px"] >= PANEL_MIN, "; ".join(probs)
            x["what"] = str((pr or {}).get("what") or "")[:60]
    report["inserts"] = {"ok": True, "krw": round(krw), "model": rep.get("image_model"), "px": [W, H],
                         "items": [{k_: x.get(k_) for k_ in ("n", "role", "j", "name", "img", "ok", "why", "panel_px", "what")} for x in inserts]}
    log(f"인서트 시트 {W}×{H} · 통과 {sum(1 for x in inserts if x['ok'])}/4 · 약 {krw:,.0f}원")


def _call_sheet_text(prompt: str, out: Path, rep: dict) -> tuple[Path, float]:
    """참조 사진 없이 글만으로 시트 1장(돈 · 장부 kind image)."""
    models = rep.get("image_models") or mm.image_models(rep.get("image_prefer"))
    rep["image_models"] = models
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
            body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": cfg}}
            try:
                data = mm._post(f"models/{model}:generateContent", body)
            except RuntimeError as e:
                last = e
                if "HTTP 400" in str(e) and ("imageSize" in str(e) or "image_size" in str(e)) and size != "1K":
                    continue
                if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                    break
                raise
            veo.record_est("image", krw, f"{model} 감정 인서트 시트 {out.name} {size} (추정)")
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
            last = RuntimeError("이미지 없음")
            break
    raise RuntimeError(f"인서트 시트 생성 실패: {last}")


def apply_inserts(beats: list[dict], inserts: list[dict], shots: dict, report: dict | None = None, budget: int = 6) -> list[dict]:
    """통과한 인서트를 가짜 컷(shots 의 INS 항목 · k 음수 · insert=True)으로 넣는다: 훅 = [인서트, 숙소 컷] · 제안 = [인서트](훅 되돌아옴 대신).
    훅의 AI 컷은 인서트 위에서(창의 빗물·커튼 — 환경 동작, 예산 안일 때만). 컷 화면(cut_imgs)은 뒤이어 apply_scenes 가 채운다. 돌려주는 것: 추가된 shot 항목."""
    added = []
    ok = [x for x in inserts if x.get("ok") and x.get("img")]
    if not ok or len(beats) < 2:
        return added
    by_role = {x["role"]: x for x in ok}
    spares = [x for x in ok if x["role"].startswith("spare")]

    def take(role):
        x = by_role.pop(role, None)
        if x is None and spares:
            x = spares.pop(0)
        return x

    def add_shot(x):
        sid = f"INS{x['n']}"
        shots[sid] = {"id": sid, "k": -x["n"], "kind": "인서트", "name": x["name"], "desc": f"인서트(숙소 아님 · 집·차 안) {x['name']}: {x['desc'][:70]}", "img": x["img"],
                      "adv": False, "category": "insert", "veo_prompt": "", "source": "insert", "place": "인서트", "grade": "full", "insert": True}
        added.append(shots[sid])
        return sid
    hook = beats[0]
    x = take("hook")
    if x:
        sid = add_shot(x)
        hook["shots"] = [sid] + [s for s in (hook.get("shots") or []) if s != sid and not (shots.get(s) or {}).get("insert")][:1]
        hook["actor"], hook["action_en"], hook["insert"] = "env", INSERT_ACTION.get(x["name"], INSERT_ACTION["worry"]), x["name"]
        hook.pop("hook_keep", None)
        v = hook.get("visual") or {}
        n_ai = sum(1 for b in beats if (b.get("visual") or {}).get("type") in ("A", "B"))
        if v.get("type") in ("A", "B") or (v.get("type") == "C" and n_ai < max(0, int(budget))):   # 예산 안이면 훅 AI 컷 = 인서트 위의 환경 움직임(빗물·커튼)
            v = {"type": "B", "actor": "env", "action_en": hook["action_en"], "insert": True}
        hook["visual"] = v
    last = beats[-1]
    x = take("end")
    if x:
        sid = add_shot(x)
        last["shots"] = [sid]
        last["insert"] = x["name"]
        last["visual"] = {"type": "C", "insert": True}
    if report is not None:
        report["inserts_used"] = [s["id"] for s in added]
    return added


def cut_img(b: dict, m: int, shots: dict, story: Path) -> Path:
    imgs = b.get("cut_imgs") or []
    if m < len(imgs) and imgs[m]:
        return story / imgs[m]
    return story / shots[b["shots"][m]]["img"]
