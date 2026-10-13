#!/usr/bin/env python3
"""미니어처 연출 시험 — 숙소 사진 + 기준 인형 → (Gemini 이미지 편집) 인물 든 첫 장면 → (Veo) 4초 영상.

2026-10-12 운영자 "진행해" (숙소 사진 합성 2장 + Veo 2컷, 약 710원 승인).
- 인물 규칙의 단일 출처: data/prompts/miniature.md 의 캐릭터 블록(코드 블록 그대로) + assets/characters/ref.jpg(기준 이미지).
- ① 합성: 숙소 사진(9:16 로 자른 것) + ref.jpg + [편집 지시 + 캐릭터 블록(사진 편집용으로 SCALE·PHOTOGRAPHY 교체) + 장면] → 첫 장면 1장.
     숙소 사진은 그대로 두고 인형만 넣는다(흐림·색 변경·덧그리기 금지). 인형은 앞쪽 가까이(강제 원근)라 화면 높이 약 1/3.
- ② 영상: 첫 장면 → Veo 3.1 Lite 4초(720p · 9:16). 인형 모습은 첫 장면 그대로 유지, 동작만 장면 블록의 4초 타임라인.
- AI 검수 호출 없음(운영자 "검수는 돈"). 결과는 운영자가 텔레그램으로 본다.
- 돈: 이미지 편집 장당 추정(flash 계열 $0.039 ≈ 57원, pro 계열 $0.134 ≈ 197원 — 확실하지 않음, 장부 kind "image"),
  Veo 4초 294원(veo.py 가 한도·장부 처리). 요청에 "veo_approved": true 가 있어야 돈을 쓴다.
- 사진 파일·합성 결과는 커밋하지 않는다(공식 홈페이지 사진 재배포 금지 규칙) — Actions 아티팩트·텔레그램으로만.
요청: requests/mini/request.json {"nonce","veo_approved":true,"shots":[{"key","url","focus_x","scene","motion"}], "image_model"(선택)}
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import veo  # noqa: E402
import omni  # noqa: E402
import crawl_photos  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requests" / "mini" / "request.json"
RULES = ROOT / "data" / "prompts" / "miniature.md"
REF = ROOT / "assets" / "characters" / "ref.jpg"
BUILD = ROOT / "build" / "mini"
REPORT = ROOT / "data" / "runs" / "mini" / "report.json"
NONCE_DONE = ROOT / "state" / "mini_nonce.json"               # 잠금을 통과해 돈 요청의 nonce — 같은 nonce 재푸시(잠금 편집)는 건너뛴다
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
FX = float(os.environ.get("USD_KRW") or 1470)
FAKE_IMG = os.environ.get("MINI_FAKE_IMAGE", "") == "1"          # 로컬 시험: 이미지 편집 대신 ref 를 붙인 가짜 합성(0원)
W, H = 720, 1280

KEEP_LINE = ("Keep both figures exactly identical to the attached reference figurines — same faces, hairstyles, "
             "body proportions, skin tone and swimwear.")
KEEP_LINE_DRY = ("Keep both figures exactly identical to the attached reference figurines — same faces, hairstyles, "
                 "body proportions and skin tone.")   # 2026-10-12 검수: 마른 장소에 'swimwear' 가 남아 가운 지시와 충돌하고 물을 부르는 단서가 됐다
EDIT_HEAD = ("TASK: Edit the attached HOTEL PHOTOGRAPH (the photo of the real place). Keep the photograph exactly as it is — same framing, "
             "every surface, object and decoration, colors, lighting and focus; do not blur, recolor, crop, extend, clean up or redraw anything, "
             "and do not add or remove any object. Only add the two miniature figurines from the attached CHARACTER REFERENCE IMAGE — take only "
             "the figurines' design from it and ignore everything else in that image — placed into the scene as described below, with correct "
             "contact shadows so they look physically present in the photograph.")
EDIT_WATER = "They interact naturally with the water that is already in the photograph (correct reflections, a faint wet sheen)."
EDIT_SCALE = ("SCALE AND PLACEMENT: the figurines are toys placed on the real surface described in SCENE, close to the camera "
              "(forced perspective), so each figure appears about a quarter to two fifths of the frame height and is clearly readable. "
              "Their FACES must stay clearly visible: both faces sit higher than 58% of the frame height measured from the top, and not in "
              "the right-most 15% of the frame (captions and app buttons are drawn there later). Their bodies may extend lower. "
              "The real place keeps its true size and stays clearly recognizable behind them. "
              "Never enlarge or shrink anything in the photograph.")
# 인형 자리 (2026-10-12 운영자 "상체까지 가려져도 된다 — 얼굴만 안 가리면 된다"): 얼굴만 자막 띠(design.GRID 띠 위쪽 1150/1920 = 0.60)와
# 오른쪽 앱 버튼 기둥(1080-180 = 0.83)을 피한다. 몸은 아래로 내려가도 된다. (앞선 안 '전신 60% 위'·'상체 60% 위'는 폐기)
FACE_Y_MAX = 0.58           # 두 얼굴(턱)의 가장 낮은 점 상한 — 자막 띠 0.60 바로 위
FACE_X_MAX = 0.85           # 얼굴 오른쪽 끝 상한 — 앱 버튼 기둥(얼굴이 화면 위쪽 절반이면 버튼이 없어 면제)
BOX_TOP_MIN = 0.12          # 상자 위 끝 하한 — 위쪽 고지문(y 172/1920 = 0.09) 회피
POST_HEAD_TOP_MAX = 0.54    # 합성 뒤 다듬은 상자(여백 0.04 포함) 위 끝 상한 — 이보다 아래서 머리가 시작하면 얼굴이 자막 띠에 걸린다 → 옴니 생략
# 얼굴이 낮으면 화면 위쪽을 잘라 확대한다(2026-10-12 운영자 아이디어 "얼굴이 가려질 것 같으면 위쪽을 조금 크롭"). 아래쪽은 그대로 두고 위쪽만 c 만큼 잘라
# 9:16 을 유지하려 좌우도 같은 비율로 줄인다 → 얼굴 y 가 (y - c)/(1 - c) 로 올라가고 인형도 1/(1-c) 배 커진다. 실제 사진 픽셀만 쓴다(지어낸 영역 없음).
CROP_MAX = 0.25             # 잘라내기 상한(확대 1.33배) — 원본이 1024px 급이라 더 자르면 흐려진다
FACE_Y_LIMIT = round(FACE_Y_MAX + (CROP_MAX - 0.02) * (1 - FACE_Y_MAX), 3)   # 0.677 — 잘라내기로 구할 수 있는 얼굴 턱의 한계(여유 0.02 포함 · 비전 지시는 67%)


def plan_crop(box, faces=None):
    """(c, xs) 또는 None. c = 위쪽 잘라낼 비율, xs = 남길 창의 왼쪽 끝(인형 상자 가운데 맞춤). 얼굴이 이미 58% 위면 (0, 0)."""
    fy = faces[3] if faces else box[1] + 0.10
    if fy <= FACE_Y_MAX:
        return 0.0, 0.0
    c = (fy - FACE_Y_MAX) / (1 - FACE_Y_MAX) + 0.02
    if c > CROP_MAX:
        return None
    wdt = 1 - c
    xs = min(max(0.0, (box[0] + box[2]) / 2 - wdt / 2), c)
    return round(c, 3), round(xs, 3)


def map_crop(v, c: float, xs: float) -> list[float]:
    """원래 화면 비율 좌표 [x0,y0,x1,y1] → 잘라 확대한 화면의 좌표."""
    w = 1 - c
    f = lambda a, o: round(min(1.0, max(0.0, (a - o) / w)), 3)  # noqa: E731
    return [f(v[0], xs), f(v[1], c), f(v[2], xs), f(v[3], c)]


def crop_zoom(src: Path, out: Path, c: float, xs: float) -> Path:
    """9:16 사진(shotHD)에서 위쪽 c·좌우를 잘라 W×H 로 — 원본 픽셀만."""
    im = Image.open(src).convert("RGB")
    iw, ih = im.size
    x0, y0 = int(round(xs * iw)), int(round(c * ih))
    cw = int(round((1 - c) * iw))
    im.crop((x0, y0, min(iw, x0 + cw), ih)).resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=94)
    return out
EDIT_PHOTO = ("PHOTOGRAPHY: realistic toy photography matched to the photograph's own light direction, color temperature and grain; "
              "figures tack-sharp; the background keeps the photograph's existing sharpness (at most a very gentle natural softness right "
              "behind the figures). Vertical 9:16, same size as the hotel photograph.")
EDIT_TAIL = ("PLACEMENT RULE: put the figurines only on a surface that really exists in the photograph, exactly where SCENE says. Never add, "
             "extend, enlarge, move or replace any surface, structure or object to make room for them. Do not zoom, reframe or shift the "
             "photograph. OUTPUT: exactly one photorealistic image. No text, no captions, no logos, no watermark, no borders.")
MAX_CHANGED = 0.30          # 배경 보존 검사(0원): 원본 대비 바뀐 화면 비율 상한. 실측 mini-1: 잘 된 파도풀 11% · 배경을 다시 그린 스파 67%

# ── 실물 크기 모드 (2026-10-13 운영자 결정 "그냥 실제 사람 크기로 하고 8등신으로") · 기본값 ───────────────────────────
# run-31 컷 4 실측: 10cm 인형이 움직이기 시작하자 옴니가 '거실의 사람 = 사람 크기' 라는 기본값으로 되돌아가 인형이 가구 대비 2배로 커지고
# 미나는 바닥으로 내려왔다(끝 장면 변화율 0.40). 영상 모델의 기본값과 싸우지 않도록 인물을 처음부터 실제 사람 크기로 넣는다.
# 얼굴·머리·의상·점토 질감 규칙(캐릭터 블록·ref.jpg)은 그대로 쓰고 크기 문장만 바꾼다. 미니어처는 request "mini_scale": "mini" 로 되돌릴 수 있다.
LIFE_DEFAULT = True
EDIT_HEAD_LIFE = ("TASK: Edit the attached HOTEL PHOTOGRAPH (the photo of the real place). Keep the photograph exactly as it is — same framing, "
                  "every surface, object and decoration, colors, lighting and focus; do not blur, recolor, crop, extend, clean up or redraw anything, "
                  "and do not add or remove any object. Only add the two characters from the attached CHARACTER REFERENCE IMAGE — take only their "
                  "design (faces, hair, outfits) from it, ignore everything else in that image, and render them at real human size as "
                  "unmistakable collectible ball-jointed dolls (visible ball joints, semi-gloss vinyl skin, rigid molded hair) — never as real "
                  "people — placed into the scene as described below, with correct perspective and contact shadows so they look physically "
                  "present in the photograph.")
EDIT_SCALE_LIFE = ("SCALE AND PLACEMENT: the characters are real human size — Jun about 178 cm, Mina about 165 cm — standing, sitting or lying on "
                   "the real surface described in SCENE, at the true distance that surface is from the camera, so doors, furniture and railings "
                   "keep their real proportions next to them (a sofa seat reaches their knees, a door is a little taller than Jun). "
                   "Their FACES must stay clearly visible: both faces sit higher than 58% of the frame height measured from the top, and not in "
                   "the right-most 15% of the frame (captions and app buttons are drawn there later). Place them on the open floor or surface "
                   "NEAREST to the camera, in front of every piece of furniture: nothing — no table, chair, rail, plant or ledge — is between them "
                   "and the camera, and the place stays clearly visible behind and beside them. Never enlarge or shrink anything in the photograph.")
EDIT_PHOTO_LIFE = ("PHOTOGRAPHY: the dolls look photographed in the same shot — matched to the photograph's own light direction, color "
                   "temperature, depth of field and grain; their vinyl skin shows soft specular highlights like a doll, not like human skin; "
                   "the background keeps the photograph's existing sharpness. Vertical 9:16, same size as the hotel photograph.")
VEO_HEAD_LIFE = ("The first frame is a real hotel photograph with two human-size collectible ball-jointed dolls of a Korean couple — "
                 "semi-gloss vinyl skin, visible ball joints at the neck, shoulders, elbows, wrists, hips, knees and ankles, rigid molded hair "
                 "with carved grooves, painted eyes, elegant adult proportions, eight heads tall. They remain dolls for the whole clip: the skin "
                 "stays vinyl, the hair stays one rigid piece, the joints stay visible, and they wear exactly what they wear in the first frame "
                 "and nothing else, from head to feet, throughout. "
                 "Keep them exactly as they appear in the first frame: same faces with painted almond eyes and small sculpted lips (the mouth "
                 "may open when laughing or surprised), same hairstyles (woman: dark-brown hair with a left side part in a neat low bun; man: "
                 "black short dandy cut with a forward fringe), the same outfit they wear in the first frame, same body proportions, and the "
                 "same real human size relative to the furniture — they never grow, shrink or change their distance from the camera. They are "
                 "alive and clearly enjoying the place: natural, visible, playful movement of arms, heads and torsos, like a stop-motion doll "
                 "film — not frozen, not stiff. Their feet and hips stay planted exactly on the first-frame spot for the whole clip, at the "
                 "same distance from the camera; all movement happens above the waist.")

VEO_HEAD = ("The first frame is a real hotel photograph with two small hand-sculpted, hand-painted polymer-clay art-doll figurines of a "
            "Korean couple (elegant adult proportions, eight heads tall, satin clay finish). Keep the figurines exactly as they appear in "
            "the first frame for the whole clip: same faces with painted almond eyes and small sculpted lips (the mouth may open when laughing or surprised), same hairstyles "
            "(woman: dark-brown hair with a left side part in a neat low bun; man: black short dandy cut with a forward fringe), the same "
            "outfit they wear in the first frame, same body proportions. They are alive and clearly enjoying the place: "
            "natural, visible, playful body movement (arms, heads and torsos), smooth like an animated figurine film — "
            "not frozen, not stiff. They stay on the same spot where they are in the first frame, and their size relative to the "
            "furniture never changes.")
VEO_TAIL = ("Camera: keeps the first frame's framing — locked-off, at most a very slight push-in — so nothing outside the first frame ever appears; "
            "never invent anything that is not visible in the first frame. The hotel place "
            "stays exactly the same as the first frame: no new objects, no new people, no text, no logos, no morphing; the characters' "
            "faces, hair, outfits, size and position relative to the furniture never change; they never turn into real humans; "
            "their outfit stays exactly as in the first frame from head to feet. Vertical 9:16, 4 seconds.")


def log(*a):
    print("[mini]", *a, flush=True)


OUTFIT_WATER = "OUTFIT IN THIS SCENE: their swimwear exactly as described in CLOTHING."
OUTFIT_DRY = ("OUTFIT IN THIS SCENE: both wear plain cream waffle-texture bathrobes, tied at the waist, over their clothes; "
              "faces, hair and body proportions exactly as described.")


LIFE_SUBS = [   # 캐릭터 블록(v3 · 운영자 확정)에서 크기 문장만 실물 크기로 — 낱말이 바뀌어 못 찾으면 바로 멈춘다
    ("Two hand-sculpted, hand-painted miniature figurines of a Korean couple in their early 30s",
     "Two hand-sculpted, hand-painted art-doll style characters of a Korean couple in their early 30s"),
    ("collectible art-doll figurines with realistic adult fashion-figure proportions, photographed as tiny toys inside a real full-size place. "
     "Jun is 10 cm tall; Mina is 9.5 cm tall.",
     "collectible art-doll look with realistic adult proportions, standing at real human size inside the real place. Jun is 178 cm tall; "
     "Mina is 165 cm tall."),
    ("This is an elegant adult figurine", "This is an elegant adult figure"),
    ("FACE — small because of the eight-head proportions, but fully detailed", "FACE — in proportion to the eight-head body, fully detailed"),
    # v5 (2026-10-13 운영자 "1번 방향"): 사람 크기에서도 인형으로 읽히는 시각 단서 — 구체관절 인형
    ("MATERIAL: smooth sculpted polymer clay with a soft satin finish, subtle hand-painted shading, a faint warm blush on the cheeks, nose tip and "
     "shoulders; edges slightly softened like a sculpted doll. No fingerprints, no seams, no plastic gloss, no realistic pores or skin texture.",
     "MATERIAL — unmistakably a DOLL, never a real person: a human-size collectible ball-jointed doll. Skin is smooth cast vinyl with a soft "
     "semi-gloss sheen, with no pores, no fine body hair, no veins and no skin texture; soft specular highlights sit on the vinyl like on a doll. "
     "Visible spherical ball joints with a thin seam line at the neck, shoulders, elbows, wrists, hips, knees and ankles. Fingers are slightly "
     "simplified and stiff. A faint hand-painted blush on the cheeks and nose tip."),
    ("Eyes: almond-shaped sculpted eyes with painted dark-brown irises and black pupils",
     "Eyes: almond-shaped painted doll eyes under a glossy clear coat, with visibly hand-painted dark-brown irises and black pupils"),
    ("HAIR — exact and never changes, wet or dry, from any angle:",
     "HAIR — one rigid molded piece of sculpted doll hair (no separate strands, never moves or blows), exact and never changes, wet or dry, from any angle:"),
    ("extra fingers, text, logos, watermarks, melted or morphing shapes.",
     "extra fingers, text, logos, watermarks, melted or morphing shapes, hidden or missing ball joints, loose hair strands."),
]


def character_block(water: bool = True, life: bool | None = None) -> str:
    """miniature.md 의 첫 코드 블록(캐릭터 블록) — 사진 편집용으로 SCALE·PHOTOGRAPHY 문단만 바꾼다.
    2026-10-12 검수: 마른 장소(객실·로비·잔디)에도 'waterline·wet·swimsuit straps' 문장이 그대로 들어가 물을 부르는 단서가 됐다 →
    마른 장소용은 물·수영복 문장을 빼고 목욕 가운으로 고정한다(캐릭터 블록의 '객실·사우나 등은 가운' 규칙을 코드로 강제)."""
    t = RULES.read_text(encoding="utf-8")
    m = re.search(r"## 1\. 캐릭터 블록.*?```\n(.*?)```", t, re.S)
    if not m:
        raise RuntimeError("miniature.md 에서 캐릭터 블록을 못 찾음")
    paras = [p for p in m.group(1).strip().split("\n\n") if not p.startswith(("SCALE:", "PHOTOGRAPHY:"))]
    if LIFE_DEFAULT if life is None else life:
        text = "\n\n".join(paras)
        for old, new in LIFE_SUBS:
            if old not in text:
                raise RuntimeError(f"miniature.md 캐릭터 블록에서 실물 크기 치환 문장을 못 찾음: {old[:60]}")
            text = text.replace(old, new)
        paras = text.split("\n\n")
    if not water:
        out = []
        for p in paras:
            if p.startswith("CLOTHING"):
                continue                                              # 옷은 OUTFIT_DRY 가 정한다
            p = re.sub(r"\s*When wet,[^.]*\.", "", p)
            p = p.replace("nudity or missing swimsuit straps, patterned or colorful swimwear, ", "nudity, ")
            p = p.replace("never changes, wet or dry, from any angle", "never changes, from any angle").replace("no messy or wet-look texture", "no messy texture")
            out.append(p)
        paras = out
    return "\n\n".join(paras)


FIGURE_WORDS = re.compile(r"\b(two\s+)?((tiny|small|little|life-?sized?|human-?sized?|hand-?carved|carved|wooden|miniature|toy|clay|plastic|resin|sculpted)\s+)+(figures?|figurines?|dolls?|toys?|characters?)\b", re.I)
WATER_WORDS = re.compile(r"\b(water|pool|swim\w*|splash\w*|wave\w*|ripple\w*|wet|bath(?:e|ing)?|spa|jacuzzi|tub|steam)\b", re.I)


def clean_scene(scene: str) -> str:
    """비전이 인형 생김새를 제멋대로 적는 것을 막는다(run-27: 'hand-carved wooden figures' → 나무 인형이 나옴). 생김새는 캐릭터 블록만 정한다."""
    return re.sub(r"Mina and Jun,?\s*(?:named\s+)?Mina and Jun,?", "Mina and Jun", FIGURE_WORDS.sub("Mina and Jun", scene))


PROPS_SIGNATURE = ("PROPS IN THIS SHOT ONLY: both wear a cream terry-towel \"sheep-head\" wrap (a towel rolled into two small round ears) "
                   "on top of their usual hair — this towel wrap is allowed here even though hats are otherwise not.")


def edit_prompt(scene: str, water: bool = True, signature: bool = False, life: bool | None = None) -> str:
    """사진 편집 지시문. water=False(마른 장소)면 물·수영복 낱말이 하나도 없다(검사: WATER_WORDS). signature 면 양머리 수건 허용 줄을 붙인다
    (캐릭터 블록의 'no hats' 와 충돌해 모델이 수건을 빼먹을 수 있었다). life(기본 True)=실물 크기 — 크기 문장만 바뀐다."""
    life = LIFE_DEFAULT if life is None else life
    keep = KEEP_LINE if water else KEEP_LINE_DRY
    if life:
        keep = keep.replace("reference figurines", "reference characters") + (" The reference image does not show the ball joints and the "
                                                                              "semi-gloss vinyl finish — add them exactly as described below.")
    parts = [EDIT_HEAD_LIFE if life else EDIT_HEAD, keep, character_block(water, life), OUTFIT_WATER if water else OUTFIT_DRY,
             EDIT_SCALE_LIFE if life else EDIT_SCALE, EDIT_PHOTO_LIFE if life else EDIT_PHOTO, "SCENE: " + clean_scene(scene).strip()]
    if signature:
        parts.append(PROPS_SIGNATURE)
    elif water:                                                       # 시그니처는 물가여도 마른 데크에 선다 — 물과 닿는 문장 없음
        parts.append(EDIT_WATER)
    parts.append(EDIT_TAIL.replace("the figurines", "the characters") if life else EDIT_TAIL)
    out = "\n\n".join(parts)
    if not water and WATER_WORDS.search(out):
        raise RuntimeError(f"마른 장소 합성 지시문에 물 낱말 '{WATER_WORDS.search(out).group(0)}' — miniature.md 캐릭터 블록을 확인")
    return out


def veo_prompt(motion: str, life: bool | None = None) -> str:
    life = LIFE_DEFAULT if life is None else life
    return " ".join([VEO_HEAD_LIFE if life else VEO_HEAD, "MOTION (4 seconds): " + motion.strip(), VEO_TAIL])


OMNI_HEAD = ("Use the attached image as the exact first frame of the video and animate from it. Total length: exactly 4 seconds. "
             "Audio: soft natural ambient sound of the place only — no dialogue, no voices, no music.")


WATER_LINE = "Water reacts to every movement with splashes, droplets and ripples; steam and light behave naturally."
DRY_LINE = "The floor, furniture and surroundings stay exactly as they are in the first frame."   # 마른 장소엔 물 낱말을 아예 안 쓴다(부정문도 단서가 된다)


def omni_prompt(motion: str, water: bool = True, life: bool | None = None) -> str:
    """옴니 플래시용 — 비오 지시문 + 첫 장면 고정·길이·소리 지시(옴니는 길이 필드가 없고 소리를 늘 만든다).
    run-27 실측: 객실·외관 컷에서 '물 반응' 문장 + 크게 당기기 지시 때문에 옴니가 **없는 수영장을 지어냄** → 물 문장은 물 장소에서만, 마른 장소는 물 금지를 명시."""
    out = OMNI_HEAD + " " + veo_prompt(motion, life) + " " + (WATER_LINE if water else DRY_LINE)
    if not water and WATER_WORDS.search(out):                         # 2026-10-12 검수: 마른 장소 옴니 지시문은 물 낱말 0 — 어기면 돈 쓰기 전에 멈춘다
        raise RuntimeError(f"마른 장소 옴니 지시문에 물 낱말 '{WATER_WORDS.search(out).group(0)}'")
    return out


def refine_box(base: Path, frame: Path, box) -> list[float]:
    """비전이 준 상자가 인형 몸을 자르는 일(run-27: 다리만 남음)을 막는다 — 상자를 위로 넓힌 창 안에서 실제로 바뀐 픽셀의 범위와 합치고 여백을 더한다."""
    from PIL import ImageChops, ImageFilter
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    # 창: 위로 넉넉히(상자가 다리만 잡은 경우 머리까지) — 2026-10-12 검수: 상자 높이 12% 면 위로 14%만 봐서 머리가 잘렸다
    win = (max(0, x0 - max(w * 0.5, 0.10)), max(0, y0 - max(h * 1.2, 0.22)), min(1, x1 + max(w * 0.5, 0.10)), min(1, y1 + max(h * 0.4, 0.05)))
    a = Image.open(base).convert("RGB").resize((180, 320)).filter(ImageFilter.GaussianBlur(1.5))
    b = Image.open(frame).convert("RGB").resize((180, 320)).filter(ImageFilter.GaussianBlur(1.5))
    r, g, bl = ImageChops.difference(a, b).split()                     # 색 차이까지 본다(밝기만 보면 배경과 밝기가 비슷한 인형 부분을 놓친다)
    d = ImageChops.lighter(ImageChops.lighter(r, g), bl).point(lambda v: 255 if v > 28 else 0).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(5))
    wx0, wy0, wx1, wy1 = int(win[0] * 180), int(win[1] * 320), int(win[2] * 180), int(win[3] * 320)
    bb = d.crop((wx0, wy0, wx1, wy1)).getbbox()
    if bb:
        cx0, cy0, cx1, cy1 = (wx0 + bb[0]) / 180, (wy0 + bb[1]) / 320, (wx0 + bb[2]) / 180, (wy0 + bb[3]) / 320
        x0, y0, x1, y1 = min(x0, cx0), min(y0, cy0), max(x1, cx1), max(y1, cy1)
    m = 0.04
    out = [max(0.0, x0 - m), max(0.0, y0 - m), min(1.0, x1 + m), min(1.0, y1 + m)]
    # 2026-10-12 검수: 합성이 배경을 다시 그리면 '바뀐 픽셀' 이 창 전체로 번져 상자가 커지고 → 지어낸 배경까지 원본 복원에서 살아남는다.
    # 상자는 비전 상자의 2.5배(최소 화면 12%)·화면 40% 를 넘지 못한다. 넘으면 비전 상자를 30% 키운 것으로 되돌린다(그 뒤 이음매 검사가 판단).
    va = max(1e-6, w * h)
    oa = (out[2] - out[0]) * (out[3] - out[1])
    if oa > min(0.40, max(2.5 * va, 0.12)):
        # 인형은 바닿은 자리에서 위로 선다 — 비전 상자는 아래(접점)는 맞고 위(머리)를 자주 놓친다(run-27 훅 컷: 머리 없는 인형).
        # 그래서 제한할 때도 위로는 넉넉히(높이의 80%·최소 10%), 옆 15%씩, 아래 5%.
        out = [max(0.0, box[0] - w * 0.15), max(0.0, box[1] - max(h * 0.8, 0.10)), min(1.0, box[2] + w * 0.15), min(1.0, box[3] + h * 0.05)]
        log(f"상자 확장 상한 초과(바뀐 영역 {oa:.0%}) → 비전 상자 기준(위로 넉넉히)으로 제한")
    return out


def _md_code_after(heading: str) -> str:
    t = RULES.read_text(encoding="utf-8")
    m = re.search(re.escape(heading) + r".*?```\n(.*?)```", t, re.S)
    if not m:
        raise RuntimeError(f"miniature.md 에서 '{heading}' 블록을 못 찾음")
    return m.group(1).strip()


def signature_block() -> str:
    """채널 시그니처 포즈 — miniature.md 1-4 고정 블록(글자 그대로)."""
    return _md_code_after("## 1-4.")


def gag_table() -> list[tuple[str, str]]:
    """장소 개그 사전 — miniature.md 1-5 표의 (장소 유형, 개그)."""
    t = RULES.read_text(encoding="utf-8")
    sec = t.split("## 1-5.", 1)[1].split("\n## ", 1)[0]
    rows = []
    for ln in sec.splitlines():
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] and not cells[0].startswith(("장소 유형", "---")):
            rows.append((cells[0], cells[1]))
    return rows


# ── 사진 ──────────────────────────────────────────────────────────────
def fetch(url: str, out: Path) -> Path:
    host = urllib.parse.urlparse(url).netloc
    if crawl_photos.DENY.search(host):
        raise RuntimeError(f"금지된 출처(공식 홈페이지만 허용): {host}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stay-shorts-factory; official photo for a single test)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return out


def crop916(src: Path, out: Path, focus_x: float = 0.5, focus_y: float = 0.5) -> Path:
    im = Image.open(src).convert("RGB")
    iw, ih = im.size
    if iw / ih > 9 / 16:
        cw, ch = int(round(ih * 9 / 16)), ih
    else:
        cw, ch = iw, int(round(iw * 16 / 9))
    x = int(min(max(0, focus_x * iw - cw / 2), iw - cw))
    y = int(min(max(0, focus_y * ih - ch / 2), ih - ch))
    im.crop((x, y, x + cw, y + ch)).resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=94)
    return out


# ── Gemini 이미지 편집 ─────────────────────────────────────────────────
def _key() -> str:
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    return k


def _post(path: str, body: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(f"{GEMINI}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini 오류 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def image_models(prefer: str | None) -> list[str]:
    """이 키로 쓸 수 있는 이미지 편집 모델 — flash 계열(싸다) 먼저, 새 버전 먼저. 이름은 자주 바뀌어 목록을 물어 고른다."""
    names = []
    try:
        req = urllib.request.Request(f"{GEMINI}/models?pageSize=200", headers={"x-goog-api-key": _key()})
        with urllib.request.urlopen(req, timeout=30) as r:
            for m in json.loads(r.read().decode()).get("models", []):
                if "generateContent" in (m.get("supportedGenerationMethods") or []):
                    names.append(m.get("name", "").split("/", 1)[-1])
    except Exception as e:  # noqa: BLE001
        log("모델 목록 조회 실패 → 기본 이름:", str(e)[:100])
    cands = [n for n in names if n.startswith("gemini-") and "image" in n and "tts" not in n]

    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0
    cands.sort(key=lambda n: ("pro" in n, -ver(n), "preview" in n, len(n)))
    if prefer:
        cands = [prefer] + [c for c in cands if c != prefer]
    return cands or ["gemini-2.5-flash-image"]


def image_krw(model: str) -> float:
    """공식 가격표(2026-10-12): gemini-3.1-flash-image 1K 출력 $0.067 · 2.5-flash-image $0.039 · pro 계열 $0.134.
    mini-1 에서 3.1 을 $0.039 로 적어 장당 41원 적게 기록했다 → 장부에 정정 줄을 남겼다."""
    if "pro" in model:
        usd = float(os.environ.get("IMAGE_PRO_USD") or 0.134)
    elif re.search(r"gemini-2\.", model):
        usd = float(os.environ.get("IMAGE_USD") or 0.039)
    else:
        usd = float(os.environ.get("IMAGE3_USD") or 0.067)
    return usd * FX


def composite(base: Path, prompt: str, out: Path, models: list[str], rep: dict) -> Path:
    if FAKE_IMG:
        im = Image.open(base).convert("RGB"); ref = Image.open(REF).convert("RGB")
        ref.thumbnail((W // 2, H // 2)); im.paste(ref, (W // 4, H - ref.height - 60)); im.save(out, "PNG")
        rep["image_model"] = "FAKE"; return out
    parts = [{"text": prompt},
             {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(base.read_bytes()).decode()}},
             {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(REF.read_bytes()).decode()}}]
    last = None
    for model in models:
        for attempt in range(2):
            body = {"contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": "9:16"}}}
            krw = image_krw(model)
            used = veo.month_total("all")
            if used + krw > veo.MONTH_KRW:
                raise RuntimeError(f"이번 달 한도({veo.MONTH_KRW:,.0f}원) — 지금 {used:,.0f}원")
            if veo._state["spent"] + krw > veo.RUN_KRW:                       # 2026-10-12 검수: 이미지 비용이 한 번 실행 한도에서 빠져 있었다
                raise RuntimeError(f"한 번 실행 한도({veo.RUN_KRW:,.0f}원) — 여기까지 {veo._state['spent']:,.0f}원")
            try:
                data = _post(f"models/{model}:generateContent", body)
            except RuntimeError as e:
                last = e
                if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                    log(f"이미지 모델 {model} 사용 불가 → 다음:", str(e)[:140].replace("\n", " "))
                    break
                raise
            veo.record_est("image", krw, f"{model} 미니어처 합성 {out.name} (추정)")
            veo._state["spent"] += krw
            rep["image_krw"] = rep.get("image_krw", 0) + round(krw)
            img = None
            for c in data.get("candidates") or []:
                for p in (c.get("content") or {}).get("parts") or []:
                    d = p.get("inlineData") or p.get("inline_data")
                    if d and str(d.get("mimeType") or d.get("mime_type") or "").startswith("image/"):
                        img = base64.b64decode(d["data"])
            if img:
                out.write_bytes(img)
                im = Image.open(out).convert("RGB")
                if im.size != (W, H):
                    im = im.resize((W, int(round(im.height * W / im.width))), Image.LANCZOS)
                    if im.height != H:                                     # 9:16 이 아니면 가운데에서 맞춘다
                        top = max(0, (im.height - H) // 2)
                        im = im.crop((0, top, W, top + H)) if im.height >= H else im.resize((W, H), Image.LANCZOS)
                im.save(out, "PNG")
                rep["image_model"] = model
                log(f"합성 성공 {out.name} · {model} · 약 {krw:,.0f}원")
                return out
            why = json.dumps({k: data.get(k) for k in ("promptFeedback",)}, ensure_ascii=False)[:200]
            fin = [c.get("finishReason") for c in data.get("candidates") or []]
            last = RuntimeError(f"이미지 없음 (finish {fin}) {why}")
            log(f"합성 결과에 이미지가 없음 → 다시 ({attempt + 1}/2):", str(last)[:160])
    raise RuntimeError(f"합성 실패: {last}")


def _gray(path: Path, size=(180, 320)):
    from PIL import ImageFilter
    return Image.open(path).convert("L").resize(size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))


def _diff_ratio(a, b) -> float:
    pa, pb = a.load(), b.load()
    w, h = a.size
    n = sum(1 for y in range(h) for x in range(w) if abs(pa[x, y] - pb[x, y]) > 28)
    return n / (w * h)


def changed_ratio(base: Path, frame: Path) -> float:
    """합성 결과가 숙소 사진을 얼마나 바꿨는지(0~1). 인형 자리만 바뀌면 0.1~0.25.
    omni-1 실측: 합성 모델이 사진을 3~8% 확대·이동만 해도 그냥 비교하면 32%로 나와 좋은 합성이 탈락했다 →
    **확대 1.00~1.12배 · 이동 ±4% 안에서 가장 잘 맞는 정렬을 찾은 뒤** 비교한다(같은 장소를 살짝 당겨 찍은 것은 허용, 없는 수영장을 그린 것은 그대로 걸린다)."""
    W0, H0 = 180, 320
    big = Image.open(base).convert("L").resize((W0 * 2, H0 * 2), Image.BILINEAR)
    fb = _gray(frame, (W0, H0))
    best = 1.0
    for sc in (1.0, 1.02, 1.04, 1.06, 1.08, 1.10, 1.12):
        cw, ch = big.width / sc, big.height / sc
        for fx in (-0.04, -0.02, 0.0, 0.02, 0.04):
            for fy in (-0.04, -0.02, 0.0, 0.02, 0.04):
                x0 = (big.width - cw) / 2 + fx * big.width
                y0 = (big.height - ch) / 2 + fy * big.height
                if x0 < 0 or y0 < 0 or x0 + cw > big.width or y0 + ch > big.height:
                    continue
                from PIL import ImageFilter
                a = big.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W0, H0), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.5))
                best = min(best, _diff_ratio(a, fb))
    return best


def paste_back(base: Path, frame: Path, box, out: Path, feather: int = 18) -> tuple[Path, float]:
    """인형이 들어간 영역(box: 화면 비율 x0,y0,x1,y1)만 합성 결과를 쓰고 **나머지는 숙소 사진 원본 그대로** 되돌린다.
    omni-1 실측: 합성 모델이 인형을 잘 넣고도 위쪽 건물을 위로 당기고 야자수를 다시 그렸다(비교 32%) → 영역 밖은 원본 픽셀로 보장.
    돌려주는 값: (결과, 경계 어긋남 비율) — 경계 띠에서 합성과 원본이 크게 다르면(합성이 통째로 밀림) 이음매가 보이므로 거른다."""
    from PIL import ImageFilter
    a = Image.open(base).convert("RGB").resize((W, H), Image.LANCZOS)
    b = Image.open(frame).convert("RGB").resize((W, H), Image.LANCZOS)
    x0, y0, x1, y1 = [int(round(v * (W if i % 2 == 0 else H))) for i, v in enumerate(box)]
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    # 화면 가장자리에 붙은 변은 안쪽으로 들이지 않는다(2026-10-12 검수: box x1=1.0 이면 오른쪽 끝 인형이 원본으로 덮여 지워졌다)
    ex0, ey0 = (x0 if x0 <= 1 else x0 + feather), (y0 if y0 <= 1 else y0 + feather)
    ex1, ey1 = (x1 if x1 >= W - 1 else x1 - feather), (y1 if y1 >= H - 1 else y1 - feather)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([ex0, ey0, ex1, ey1], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather / 2))
    if x0 <= 1 or y0 <= 1 or x1 >= W - 1 or y1 >= H - 1:                     # 흐림이 가장자리에서 새지 않게 그 변은 다시 꽉 채운다
        dm = ImageDraw.Draw(mask)
        if x0 <= 1: dm.rectangle([0, ey0, feather, ey1], fill=255)          # noqa: E701
        if x1 >= W - 1: dm.rectangle([W - feather, ey0, W, ey1], fill=255)  # noqa: E701
        if y0 <= 1: dm.rectangle([ex0, 0, ex1, feather], fill=255)          # noqa: E701
        if y1 >= H - 1: dm.rectangle([ex0, H - feather, ex1, H], fill=255)  # noqa: E701
    Image.composite(b, a, mask).save(out, "PNG")
    # 경계 띠(안쪽 feather~2feather) 어긋남
    ga, gb = a.convert("L").filter(ImageFilter.GaussianBlur(1.5)), b.convert("L").filter(ImageFilter.GaussianBlur(1.5))
    pa, pb = ga.load(), gb.load()
    ring, bad = 0, 0
    for y in range(max(0, y0), min(H, y1), 3):
        for x in range(max(0, x0), min(W, x1), 3):
            d_edge = min([d for d, edge in ((x - x0, x0 <= 1), (x1 - x, x1 >= W - 1), (y - y0, y0 <= 1), (y1 - y, y1 >= H - 1)) if not edge] or [0])
            if feather <= d_edge <= 2 * feather:
                ring += 1
                bad += abs(pa[x, y] - pb[x, y]) > 28
    return out, (bad / ring if ring else 1.0)


MAX_SEAM = 0.35             # 경계 띠 어긋남 상한 — 넘으면 이음매가 보인다


# ── 확인 시트 ─────────────────────────────────────────────────────────
def frame_at(video: Path, t: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return out


def sheet(rows: list[list[tuple[Path, str]]], out: Path) -> Path:
    tw, th, gap, top = 270, 480, 14, 34
    cols = max(len(r) for r in rows)
    im = Image.new("RGB", (gap + cols * (tw + gap), gap + len(rows) * (th + top + gap)), (18, 20, 26))
    d = ImageDraw.Draw(im)
    try:
        from design import font
        f = font(20, bold=False)
    except Exception:  # noqa: BLE001
        f = None
    for r, row in enumerate(rows):
        for c, (p, label) in enumerate(row):
            x, y = gap + c * (tw + gap), gap + r * (th + top + gap)
            d.text((x, y + 4), label, fill=(255, 255, 255), font=f)
            if p and Path(p).exists():
                im.paste(Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS), (x, y + top))
    im.save(out, "JPEG", quality=88)
    return out


def probe_models() -> dict:
    """0원: 이 키로 보이는 모델 이름·지원 방식만 기록한다 (생성 호출 없음)."""
    req = urllib.request.Request(f"{GEMINI}/models?pageSize=1000", headers={"x-goog-api-key": _key()})
    with urllib.request.urlopen(req, timeout=30) as r:
        ms = json.loads(r.read().decode()).get("models", [])
    keep = [{"name": m.get("name", "").split("/", 1)[-1], "methods": m.get("supportedGenerationMethods") or []} for m in ms]
    pick = [k for k in keep if re.search(r"omni|veo|image|lyria|tts", k["name"])]
    return {"count": len(keep), "media_models": pick, "all_names": [k["name"] for k in keep]}


def main():
    req = json.loads(REQ.read_text(encoding="utf-8"))
    if req.get("probe_models"):                                   # 0원 점검 — 모델 목록만
        rep = {"nonce": req.get("nonce"), "ok": True, "probe": probe_models(), "finished": datetime.now().isoformat(timespec="seconds")}
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        log("모델 목록:", [m["name"] for m in rep["probe"]["media_models"]])
        return
    BUILD.mkdir(parents=True, exist_ok=True)
    try:
        done = json.loads(NONCE_DONE.read_text(encoding="utf-8")).get("nonce") if NONCE_DONE.exists() else None
    except Exception:  # noqa: BLE001
        done = None
    if req.get("nonce") and req.get("nonce") == done:                       # 2026-10-13: 시험 뒤 잠금(veo_approved false) 푸시가 또 실행되는 일 방지
        (BUILD / "SKIPPED").write_text(f"같은 nonce 재실행 건너뜀: {req.get('nonce')}\n", encoding="utf-8")
        log(f"같은 nonce '{req.get('nonce')}' 는 이미 처리됨 — 건너뜀(0원, 기록 유지)")
        return
    rep = {"nonce": req.get("nonce"), "started": datetime.now().isoformat(timespec="seconds"), "ok": False, "shots": [],
           "veo_model": veo.MODEL, "fake_veo": veo.FAKE, "fake_image": FAKE_IMG}
    if not (veo.FAKE and FAKE_IMG and omni.FAKE) and req.get("veo_approved") is not True:   # 2026-10-12 검수: 옴니 가짜 여부도 본다(빠져 있었다)
        raise SystemExit('유료 시험은 운영자 허락이 필요합니다 — requests/mini/request.json 에 "veo_approved": true')
    NONCE_DONE.parent.mkdir(parents=True, exist_ok=True)
    NONCE_DONE.write_text(json.dumps({"nonce": req.get("nonce"), "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n", encoding="utf-8")
    models = [] if FAKE_IMG else image_models(req.get("image_model"))
    life = str(req.get("mini_scale") or ("life" if LIFE_DEFAULT else "mini")) == "life"
    rep["scale"] = "life" if life else "mini"
    log("이미지 모델 후보:", models[:4], "· 인물 크기:", rep["scale"])
    rows = []
    try:
        for s in req["shots"]:
            k = s["key"]
            row = {"key": k, "url": s["url"], "ok": False}
            rep["shots"].append(row)
            src = fetch(s["url"], BUILD / f"{k}_src.jpg")
            base = crop916(src, BUILD / f"{k}_base.jpg", float(s.get("focus_x", 0.5)), float(s.get("focus_y", 0.5)))
            wet = bool(s.get("water", True))                                      # 물가면 수영복, 마른 실내면 가운
            ep = edit_prompt(s["scene"], water=wet, signature=bool(s.get("signature")), life=life); (BUILD / f"{k}_edit_prompt.txt").write_text(ep, encoding="utf-8")
            prev = ROOT / "build" / "mini_prev" / f"{k}_frame.png"                 # 이전 실행 아티팩트의 합성(돈 아끼기 · request "reuse_run_id")
            if req.get("reuse_run_id") and prev.exists():
                frame = BUILD / f"{k}_frame.png"; frame.write_bytes(prev.read_bytes()); row["reused_frame"] = int(req["reuse_run_id"])
                log(f"{k}: 이전 실행({req['reuse_run_id']})의 합성 장면 재사용 — 이미지 비용 0원")
            else:
                frame = composite(base, ep, BUILD / f"{k}_frame.png", models, rep)
            if s.get("box"):                                               # 인형 영역 밖은 원본으로 되돌림 → 배경 보존 보장
                frame, seam = paste_back(base, frame, refine_box(base, frame, s["box"]), BUILD / f"{k}_frame_pb.png")
                row["seam"] = round(seam, 3)
                ch = changed_ratio(base, frame); row["changed"] = round(ch, 3)
                if seam > MAX_SEAM:
                    row["skipped"] = f"이음매 어긋남 {seam:.0%} — 영상 생략(돈 아낌)"
                    log(f"{k}: {row['skipped']}")
                    rows.append([(base, f"{k} 숙소 사진"), (frame, f"이음매 실패 {seam:.0%}")])
                    continue
            else:
                ch = changed_ratio(base, frame)
                row["changed"] = round(ch, 3)
            if not s.get("box") and ch > MAX_CHANGED:                                         # 배경을 다시 그렸다 → 한 번만 더, 그래도 넘으면 이 컷은 Veo 를 쓰지 않는다
                log(f"{k}: 숙소 사진이 {ch:.0%} 바뀜(상한 {MAX_CHANGED:.0%}) → 한 번 더 합성")
                frame = composite(base, ep + "\n\nPREVIOUS ATTEMPT FAILED: it redrew or reframed the photograph. Keep every pixel of the photograph except where the figurines are.",
                                  BUILD / f"{k}_frame.png", models, rep)
                ch = changed_ratio(base, frame); row["changed_retry"] = round(ch, 3)
                if ch > MAX_CHANGED:
                    row["skipped"] = f"배경 보존 실패 {ch:.0%} — Veo 생략(돈 아낌)"
                    log(f"{k}: {row['skipped']}")
                    rows.append([(base, f"{k} 숙소 사진"), (frame, f"합성 실패 {ch:.0%} 변경")])
                    continue
            motion = signature_block() if s.get("signature") else s["motion"]
            engine = str(s.get("engine") or req.get("video_engine") or "omni")
            clip = BUILD / f"{k}.mp4"
            if engine == "omni":
                vp = omni_prompt(motion, water=wet and not s.get("signature"), life=life); (BUILD / f"{k}_omni_prompt.txt").write_text(vp, encoding="utf-8")
                res = omni.make_clip(vp, frame, 4, clip, resolution=str(req.get("omni_resolution") or "720p"))
                row.update({"ok": True, "engine": "omni", "omni_krw": res["krw"], "clip_sec": res["sec"], "omni_model": res["model"], "tokens_out": res["tokens_out"]})
            else:
                vp = veo_prompt(motion, life); (BUILD / f"{k}_veo_prompt.txt").write_text(vp, encoding="utf-8")
                krw = veo.make_clip(vp, frame, 4, clip, veo.seed_for("mini", k), mime="image/png")
                row.update({"ok": True, "engine": "veo", "veo_krw": round(krw), "clip_sec": 4})
            row.update({"edit_prompt_chars": len(ep), "video_prompt_chars": len(vp)})
            try:                                                           # 비전 검수(약 1원) — 시험 경로는 기록만
                import make_solo, make_stay as _ms
                row["vision"] = make_solo.clip_check(_ms.pick_models(), frame, clip, BUILD, k)
                log(f"{k} 비전 검수: {row['vision'].get('verdict')} — {row['vision'].get('why', '')[:80]}")
            except Exception as e:  # noqa: BLE001
                row["vision"] = {"verdict": "error", "why": str(e)[:120]}
            dur = omni.duration(clip) or 4.0
            ts = [round(dur * f, 1) for f in (0.25, 0.5, 0.75, 0.97)]
            mids = [frame_at(clip, t, BUILD / f"{k}_t{t}.jpg") for t in ts]
            rows.append([(base, f"{k} 숙소 사진"), (frame, "합성 첫 장면")] + [(m, f"영상 {t}초") for m, t in zip(mids, ts)])
        rep["ok"] = True
    except Exception as e:  # noqa: BLE001
        rep["error"] = f"{type(e).__name__}: {str(e)[:400]}"
        log("실패:", rep["error"])
    finally:
        if rows:
            sheet(rows, BUILD / "sheet.jpg")
        rep["veo_spent_krw"] = round(veo.spent_this_run())                # Veo + Omni 합계(같은 실행 카운터)
        rep["month_veo_krw"] = round(veo.month_total())
        rep["finished"] = datetime.now().isoformat(timespec="seconds")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        log("기록:", json.dumps({k: rep.get(k) for k in ("ok", "image_model", "image_krw", "veo_spent_krw", "error")}, ensure_ascii=False))
    if not rep["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
