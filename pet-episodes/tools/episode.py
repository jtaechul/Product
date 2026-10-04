"""반려동물 식당 에피소드(「한 그릇의 품격」) 자동 제작 — 심해 v2(short-movie-generator/v2) 절차를 옮겨 온 것.

절차: 캐릭터 참고 이미지 → 컷별 첫 장면(이미지 AI, 캐릭터·실제 음식·가게 참고) → 첫 장면에서 8초 영상(Omni Flash,
실패 시 Veo Lite) → 한국어 내레이션(Google TTS) → 조립(자막·메뉴판·계산서·오프닝 줌·영수증 아웃트로).

사용: python episode.py <에피소드 폴더>/requests/<요청>.json
요청: {"id": "...", "steps": ["character","keyframes","clips","tts","assemble"], "redo": ["c03"]}
  - 에피소드 폴더에는 episode.json(관리자 페이지 '프롬프트 만들기' 결과)과 refs/food.png(음식 참고 이미지)가 있다.
  - 결과는 work/에 쌓이고, 이미 있는 결과는 다시 만들지 않는다(비용 절약). 다시 뽑을 컷은 redo에 적는다.
보안: 키는 환경변수(GEMINI_API_KEY, GOOGLE_TTS_KEY)로만 받고 출력하지 않는다.
규칙(book-carousel CLAUDE.md): 상품명·포장·가격은 영상에 넣지 않는다(가격은 사용자 지시 2026-09로 전면 금지) · 영상 AI 소리는 버린다.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

API = "https://generativelanguage.googleapis.com/v1beta"
W, H, FPS = 720, 1280, 24
FFMPEG = os.environ.get("FFMPEG", "ffmpeg")
IMAGE_MODELS = ["gemini-3-pro-image-preview", "gemini-3.1-flash-image-preview", "gemini-2.5-flash-image"]
CLIP_MODEL = "gemini-omni-1.1-flash"
VEO_FALLBACK = "veo-3.1-lite-generate-preview"
# ★목소리 규칙(사용자 확정 2026-09) — 한 곳에서만 정한다: 성우 1명 고정 · 연기 톤 고정 · 속도 1.2배.
#   Gemini 음성(사람 같은 연기)을 쓰고, 속도는 숫자 설정이 없어 만든 뒤 편집에서 정확히 1.2배로 맞춘다.
VOICE_NAME = "Enceladus"                   # 사용자 확정(2026-09): 숨결 섞인 낮은 목소리. 바꾸지 않는다
VOICE_SPEED = 1.2
# 연기 지시(사용자 확정 2026-09: 더 '고독한 미식가'답게, 조곤조곤한 독백으로). 모든 컷에 글자 하나 안 바꾸고 똑같이 준다.
VOICE_DIRECTION = ("[연기 지시] 한국어. 드라마 '고독한 미식가'의 속마음 내레이션처럼 읽는다. 40대 남자가 혼자 밥을 먹으며 "
                   "마음속으로 중얼거리는 독백이다. 마이크에 가까이 대고 낮고 조용한 목소리로, 조곤조곤 속삭이듯 말한다. "
                   "소리를 크게 내지 않고, 문장 끝은 부드럽게 내려놓는다. 맛을 음미하는 대목에서는 아주 살짝 감탄이 묻어나되 "
                   "들뜨지 않는다. 문장 사이에는 짧게 숨을 고른다. 아나운서·광고·동화 구연 톤과 과장된 연기는 금지. "
                   "처음부터 끝까지 같은 사람, 같은 톤, 같은 거리감을 유지한다. 아래 대사만 그대로 읽어라.")
VOICE_PITCH_ST = -1.0      # 음높이(반음). 음수면 더 낮게 — 사용자 요청 '조금 더 낮은 톤'
# 후보 비교(사용자 요청 2026-09: Algenib보다 낮고 조곤조곤한 목소리 3개): 숨결 섞인 저음 · 부드러운 저음 · 차분하고 고른 톤
VOICE_SAMPLES = ["Enceladus", "Algieba", "Schedar"]
TTS_MODELS = ["gemini-2.5-pro-preview-tts", "gemini-2.5-flash-preview-tts"]
# 예비(Gemini 음성 실패 시): 구글 기본 음성
TTS_VOICE = {"languageCode": "ko-KR", "name": "ko-KR-Neural2-C"}
TTS_RATE, TTS_PITCH = "120%", "-2st"
FONT_CANDIDATES = [("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),   # index 1 = KR
                   ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0)]

CHARACTER_PROMPTS = {
    # 실사 시바견(사용자 확정 2026-09: 덜 귀엽게, 실제 시바견처럼)
    "dog": "A photorealistic photograph of a real young Shiba Inu dog about eight months old, full body, standing naturally "
           "on all four legs in a three-quarter view, true-to-life Shiba proportions and head size, almond-shaped dark brown "
           "eyes, small triangular upright ears, curled tail over the back, warm golden-red and cream coat with white urajiro "
           "markings on the cheeks, chest and legs, absolutely no black hairs or mask, no clothes, no collar and no "
           "accessories, realistic fur detail, soft even natural light, plain light grey background, sharp focus. No text.",
    "cat": "A photorealistic 3D animated style full-body portrait of an ultra-cute kitten standing naturally on all four legs, "
           "three-quarter view, oversized round head with chubby cheeks, huge round sparkling eyes, a tiny pink nose, soft "
           "plush-like cream and snow-white fur, natural body with no clothes, no collar and no accessories, unbelievably "
           "fluffy soft texture, soft even studio lighting, plain light grey background, clean 3D rendering. No text.",
}


# ---------- 공용 ----------
HTTP_UA = "pet-episodes/1.0 (+github-actions)"   # 파이썬 기본 이름표(Python-urllib)는 Cloudflare가 봇으로 막는다(오류 1010, 2026-10 리메이크 원본 403 사고)


def _http(url, data=None, headers=None, timeout=300):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": HTTP_UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _key(name):
    k = os.environ.get(name, "")
    if not k:
        raise RuntimeError(f"{name} 없음")
    return k


def _ff(args):
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


def _dur(p) -> float:
    r = subprocess.run([FFMPEG, "-i", str(p)], capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def _font(size):
    for path, idx in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=idx)
    raise RuntimeError("한글 글꼴 없음(fonts-noto-cjk 설치 필요)")


def _b64img(p: Path) -> dict:
    mt = "image/png" if p.suffix == ".png" else "image/jpeg"
    return {"mime_type": mt, "data": base64.b64encode(p.read_bytes()).decode()}


_model_cache: dict = {}


def _pick_model(key, prefs):
    if "names" not in _model_cache:
        code, body = _http(f"{API}/models?pageSize=1000", headers={"x-goog-api-key": key})
        _model_cache["names"] = {m["name"].split("/")[-1] for m in json.loads(body).get("models", [])} if code == 200 else set()
    return next((m for m in prefs if m in _model_cache["names"]), prefs[-1])


def gen_image(prompt: str, refs: list[Path], out: Path, aspect="9:16", size: str = "") -> dict:
    key = _key("GEMINI_API_KEY")
    model = _pick_model(key, IMAGE_MODELS)
    parts = [{"inline_data": _b64img(r)} for r in refs] + [{"text": prompt}]
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": aspect, **({"imageSize": size} if size else {})}}}
    for attempt in range(2):
        code, raw = _http(f"{API}/models/{model}:generateContent", json.dumps(body).encode(),
                          {"x-goog-api-key": key, "Content-Type": "application/json"})
        if code == 200:
            d = json.loads(raw)
            imgs = [p["inlineData"] for c in d.get("candidates", []) for p in c.get("content", {}).get("parts", [])
                    if "inlineData" in p]
            if imgs:
                out.write_bytes(base64.b64decode(imgs[0]["data"]))
                return {"ok": True, "model": model}
            err = f"이미지 없음 {[c.get('finishReason') for c in d.get('candidates', [])]}"
        else:
            err = f"HTTP {code}: {raw[:200].decode('utf-8', 'replace')}"
        time.sleep(3)
    return {"ok": False, "model": model, "error": err}


# ---------- 1. 캐릭터 ----------
def step_character(ep, epdir, work, log, redo):
    out = work / "character.png"
    given = epdir / "refs" / "character.png"
    if given.exists():
        log["character"] = {"ok": True, "source": "refs/character.png"}
        return given
    # 채널 고정 주인공(모든 회차 같은 개체) — pet-episodes/characters/<종>.png
    fixed = Path(__file__).resolve().parent.parent / "characters" / f"{ep.get('species', 'dog')}.png"
    if fixed.exists() and "character" not in redo:
        log["character"] = {"ok": True, "source": f"characters/{fixed.name}"}
        return fixed
    if out.exists() and "character" not in redo:
        return out
    r = gen_image(CHARACTER_PROMPTS.get(ep.get("species", "dog"), CHARACTER_PROMPTS["dog"]), [], out, "1:1")
    log["character"] = r
    if not r["ok"]:
        raise RuntimeError(f"캐릭터 이미지 실패: {r.get('error')}")
    return out


# ---------- 2. 가게 세트 원본 + 컷별 첫 장면 ----------
# 배경·테이블이 컷마다 바뀌던 문제(사용자 지적 2026-09) 대책:
#   ① 사람·동물 없는 '가게 세트 원본' 1장을 먼저 만들고 ② 모든 컷의 첫 장면이 이 원본을 참고한다
#   ③ 영상 AI에도 첫 장면과 함께 이 원본을 넣어 움직이는 동안 배경을 붙잡는다.
SET_PROMPT = ("Create an empty interior photo of one small quiet diner for a vertical 9:16 film. Nobody in it: no animals, no "
              "people. Eye-level wide shot showing the whole room: the single entrance door, the walls, the floor, the one "
              "table and the seat, the lighting and the prop, exactly as described below. The table is bare (nothing on it). "
              "{style}\nSET: {set}\nNo text, letters, signs with writing, logos or watermarks. Full-frame image with no borders.")
KF_HEAD = ("Create the FIRST FRAME of one shot of a vertical 9:16 film. "
           "Reference image 1 is the main character: draw exactly this {noun} (same face, fur colours, markings and "
           "proportions), a natural four-legged animal with no clothes, no collar and no accessories. "
           "Reference image 2 is THE restaurant set: this shot happens inside exactly this room — the same door, walls, "
           "floor, the same table (same wood, shape and size) and seat, the same lamp and prop. Only the camera position "
           "and framing change, as given in SHOT. Do NOT copy the camera angle of reference image 2 — it only shows what the "
           "room looks like; frame this shot exactly as SHOT says (close-up, overhead, low angle and so on). ")
KF_FOOD = ("Reference image {n} is the real food: draw exactly these food pieces (same shape, size, colour and texture) in "
           "the same shallow plain white ceramic bowl. Never show any packaging or bag. ")
KF_TAIL = ("\nNo text, letters, numbers, signs with writing, logos or watermarks anywhere. No humans. No banknotes, coins or cash. "
           "Full-frame image with no borders.")


def _line(prompt: str, head: str) -> str:
    m = re.search(rf"^{head}:\s*(.+)$", prompt or "", re.M)
    return m.group(1).strip() if m else ""


def step_set(ep, epdir, work, log, redo):
    out = work / "set.png"
    if out.exists() and "set" not in redo:
        return out
    p0 = ep["clips"][0].get("imagePrompt", "")
    r = gen_image(SET_PROMPT.format(vessel="a shallow plain white ceramic bowl", style=_line(p0, "STYLE"),
                                    set=ep.get("setBlock") or _line(p0, r"SET \(identical in every clip\)")), [], out)
    log["set"] = r
    if not r["ok"]:
        raise RuntimeError(f"가게 세트 원본 실패: {r.get('error')}")
    return out


# ---------- 2-b. 격자 스토리보드(심해 v2 방식 · 사용자 확정 2026-09) ----------
# 모든 컷의 첫 장면을 '한 장'에 같이 그린다 → 가게·조명·강아지·그릇이 전 컷에서 한 번에 통일된다(따로 그리면 조금씩 달라짐).
# 그린 뒤 칸 사이 흰 선을 찾아 칸별로 잘라 영상 AI에 넘긴다(격자를 통째로 넣으면 분할 화면으로 오인).
# 컷마다 '그릇 상태'를 정해 그림·영상 모두에 적는다 — 음식·그릇이 갑자기 생겼다 사라지던 오류(3차 실측) 대책.
def bowl_state(roles: list[str], i: int) -> str:
    r = roles[i]
    tastes = [k for k, x in enumerate(roles) if x == "taste"]
    if r in ("enter", "order"):
        return "The table is bare: no bowl, no food and no tray on it yet."
    if r == "serve":
        return "A human hand is setting the bowl down on the table; the bowl is completely full of the food."
    if r == "taste":
        k = tastes.index(i)
        left = ["almost full", "about half full", "about a quarter full", "nearly empty"][min(k, 3)]
        return f"The bowl stays on the table in the same place and is {left} of the food; no other dishes."
    if r == "bill":
        return ("The empty bowl stays on the table; beside it a small plain wooden tray holds one folded blank paper "
                "slip (no writing visible).")
    if r == "exit":
        return "The empty bowl and the small wooden tray stay on the table where they were."
    return ""


GRID_ASPECTS = {"1:1": 1.0, "4:5": 0.8, "5:4": 1.25, "3:4": 0.75, "4:3": 4 / 3, "2:3": 2 / 3, "3:2": 1.5, "9:16": 0.5625}


def grid_layout(n: int):
    """컷 수 → (행, 열, 전체 비율). 칸은 세로 9:16에 가깝게."""
    rows, cols = {5: (2, 3), 6: (2, 3), 7: (2, 4), 8: (2, 4), 9: (3, 3)}.get(n, (2, (n + 1) // 2))
    want = (cols * 9) / (rows * 16)
    aspect = min(GRID_ASPECTS, key=lambda k: abs(GRID_ASPECTS[k] - want))
    return rows, cols, aspect


def split_grid(img_path: Path, rows: int, cols: int, names: list[str], out_dir: Path) -> list[Path]:
    """격자 → 칸별 파일. 흰 경계 띠를 밝기로 찾아 그 바깥에서 자르고, 바깥 흰 테두리도 잘라낸다(심해 v2 split_grid)."""
    im = Image.open(img_path).convert("RGB")
    Wd, Hd = im.size
    g = im.convert("L")

    def line_mean(x, axis):
        if axis == "x":
            vals = [g.getpixel((x, y)) for y in range(0, Hd, max(1, Hd // 200))]
        else:
            vals = [g.getpixel((xx, x)) for xx in range(0, Wd, max(1, Wd // 200))]
        return sum(vals) / len(vals)

    def bands(n, length, axis):
        edges = [0]
        for k in range(1, n):
            c = length * k // n
            lo, hi = max(1, int(c - length * 0.08)), min(length - 1, int(c + length * 0.08))
            means = {x: line_mean(x, axis) for x in range(lo, hi)}
            best = max(means, key=means.get)
            if means[best] > 200:
                a = best
                while a - 1 >= lo and means.get(a - 1, 0) > 200:
                    a -= 1
                b = best
                while b + 1 < hi and means.get(b + 1, 0) > 200:
                    b += 1
                edges += [a, b + 1]
            else:
                edges += [c, c]
        edges.append(length)
        lim = int(length * 0.08)
        a = 0
        while a < lim and line_mean(a, axis) > 200:
            a += 1
        b = length
        while length - b < lim and line_mean(b - 1, axis) > 200:
            b -= 1
        edges[0], edges[-1] = a, b
        return [(edges[2 * i], edges[2 * i + 1]) for i in range(n)]

    xs, ys = bands(cols, Wd, "x"), bands(rows, Hd, "y")
    inset = max(4, int(min(Wd, Hd) * 0.006))
    saved = []
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if i >= len(names) or not names[i]:
                continue
            box = (xs[c][0] + inset, ys[r][0] + inset, xs[c][1] - inset, ys[r][1] - inset)
            p = out_dir / f"{names[i]}.png"
            panel = im.crop(box)
            # 9:16로 가운데 맞춤(칸 비율이 조금 달라도 영상 AI가 늘려 그리지 않게)
            pw, ph = panel.size
            tw = min(pw, int(ph * 9 / 16))
            th = min(ph, int(tw * 16 / 9))
            panel = panel.crop(((pw - tw) // 2, (ph - th) // 2, (pw - tw) // 2 + tw, (ph - th) // 2 + th))
            panel.resize((720, 1280), Image.LANCZOS).save(p)
            saved.append(p)
    return saved


GRID_HEAD = ("Create ONE image that is a clean grid of {n} separate, equal-sized vertical 9:16 photographs arranged in "
             "{rows} rows x {cols} columns, separated by thin plain white gutters, read left-to-right, top-to-bottom. "
             "{blank}Together they are the storyboard of ONE continuous short film, so every panel shows the SAME place, "
             "the SAME character and the SAME props, only from a different camera angle and at a later moment.\n"
             "Reference image 1 is the main character: in every panel draw exactly this {noun} (same face, fur colours, "
             "markings, proportions and size), a natural four-legged animal with no clothes, no collar and no accessories.\n"
             "Reference image 2 is the restaurant set: every panel happens inside exactly this room — the same single door, "
             "walls, floor, the same table (same wood, shape, size and position), the same seat cushion, the same lamp and "
             "prop, the same lighting. Do not copy its camera angle; frame each panel as its SHOT says.\n"
             "Neighbouring panels must never share the same framing: each panel changes BOTH the shot size (wide, medium, "
             "close-up, macro) and the camera direction (front, side, overhead, low, high, from behind) from the panel "
             "before it.\n"
             "{food}"
             "Shared look for all panels: {style}\n"
             "In every panel keep the upper quarter calm and uncluttered for captions. No text, letters, numbers, signs "
             "with writing, logos or watermarks in any panel. No humans except a hand and forearm where a panel says so. "
             "No banknotes, coins or cash.\n\n")


def step_storyboard(ep, epdir, work, log, redo, character, setimg):
    clips = ep["clips"]
    names = [f"kf_c{c['no']:02d}" for c in clips]
    grid = work / "storyboard.png"
    if grid.exists() and "storyboard" not in redo and all((work / f"{n}.png").exists() for n in names):
        return
    food = next((p for p in (epdir / "refs" / "food.png", epdir / "refs" / "food.jpg") if p.exists()), None)
    rows, cols, aspect = grid_layout(len(clips))
    roles = [c.get("role") for c in clips]
    noun = "kitten" if ep.get("species") == "cat" else "puppy"
    p0 = clips[0].get("imagePrompt", "")
    foodtxt = ""
    refs = [character, setimg]
    if food:
        refs.append(food)
        foodtxt = ("Reference image 3 is the real food: wherever the bowl has food, draw exactly these food pieces (same "
                   "shape, size, colour and texture) in the same shallow plain white ceramic bowl — the only dish in the "
                   "film. Never show any packaging or bag.\n")
    blank = (f"The last {rows * cols - len(clips)} panel(s) stay plain white. " if rows * cols > len(clips) else "")
    text = GRID_HEAD.format(n=rows * cols, rows=rows, cols=cols, blank=blank, noun=noun, food=foodtxt,
                            style=_line(p0, "STYLE"))
    for i, c in enumerate(clips):
        r, k = divmod(i, cols)
        moment = _line(c.get("imagePrompt", ""), "MOMENT")
        shot = c.get("shot") or _line(c.get("imagePrompt", ""), "SHOT")
        text += (f"PANEL {i + 1} (row {r + 1}, column {k + 1}) — {c.get('roleKo') or c.get('role')}: SHOT: {shot}. "
                 f"MOMENT: {moment}. PROPS: {bowl_state(roles, i)}\n")
    r = gen_image(text, refs, grid, aspect, size="4K")
    log["storyboard"] = {**r, "layout": f"{rows}x{cols}", "aspect": aspect}
    if not r["ok"]:
        raise RuntimeError(f"스토리보드 실패: {r.get('error')}")
    split_grid(grid, rows, cols, names, work)


def _look_sig(p: Path):
    from PIL import ImageFilter
    im = Image.open(p).convert("L").resize((36, 64)).filter(ImageFilter.GaussianBlur(1.5))
    px = list(im.getdata())
    m = sum(px) / len(px)
    return [x - m for x in px]


def look_diff(a: Path, b: Path) -> float:
    """두 화면이 얼마나 다른가(밝기 차이는 빼고 구도·형태 차이만). 실측: 같은 와이드 구도 3~5, 다른 구도 30~70."""
    x, y = _look_sig(a), _look_sig(b)
    return sum(abs(i - j) for i, j in zip(x, y)) / len(x)


SAME_LOOK = 20.0      # 이보다 작으면 '같은 구도'로 본다


def check_adjacent(ep, work, log, redo, character, setimg, epdir):
    """격자를 자른 뒤 이웃 컷끼리 비교해 너무 비슷한 칸은 그 칸만 다른 구도로 다시 그린다(사용자 지적 2026-09: 같은 구도가 이어지면 끊겨 보임).
    비용 상한: 한 편에 최대 2칸."""
    clips = ep["clips"]
    res = log.setdefault("adjacent", {})
    redrawn = 0
    for i in range(1, len(clips)):
        a, b = work / f"kf_c{clips[i - 1]['no']:02d}.png", work / f"kf_c{clips[i]['no']:02d}.png"
        if not (a.exists() and b.exists()):
            continue
        d = round(look_diff(a, b), 1)
        name = f"c{clips[i]['no']:02d}"
        res[name] = {"diff": d}
        if d < SAME_LOOK and redrawn < 2:
            res[name]["redrawn"] = True
            b.unlink()
            redo.add(f"kf_{name}")
            redrawn += 1
    if redrawn:
        step_keyframes(ep, epdir, work, log, redo, character, setimg, avoid_same=True)
        for i in range(1, len(clips)):
            name = f"c{clips[i]['no']:02d}"
            a, b = work / f"kf_c{clips[i - 1]['no']:02d}.png", work / f"{'kf_' + name}.png"
            if res.get(name, {}).get("redrawn") and a.exists() and b.exists():
                res[name]["after"] = round(look_diff(a, b), 1)


def step_keyframes(ep, epdir, work, log, redo, character, setimg, avoid_same=False):
    food = next((p for p in (epdir / "refs" / "food.png", epdir / "refs" / "food.jpg") if p.exists()), epdir / "refs" / "food.png")
    noun = "kitten" if ep.get("species") == "cat" else "puppy"
    res = log.setdefault("keyframes", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out = work / f"kf_{name}.png"
        if out.exists() and f"kf_{name}" not in redo:
            continue
        refs, text = [character, setimg], KF_HEAD.format(noun=noun)
        if "FOOD:" in c.get("prompt", "") and food.exists():
            refs.append(food)
            text += KF_FOOD.format(n=len(refs))
        roles = [x.get("role") for x in ep["clips"]]
        grid = work / "storyboard.png"
        if grid.exists():                                      # 격자가 있으면 화풍·소품 기준으로 함께 참고
            refs.append(grid)
            text += f"Reference image {len(refs)} is the storyboard of the other shots: match its look exactly. "
            if food in refs:                                   # 음식 모양은 격자보다 음식 참고 사진이 우선(격자 속 음식이 틀렸을 수 있다 — 2화 둥근 알갱이 사고)
                text += "For the food pieces in the bowl, follow the real food reference image, not the storyboard. "
        props = bowl_state(roles, ep["clips"].index(c))
        k = ep["clips"].index(c)
        if avoid_same and k > 0:                              # 앞 컷과 같은 구도로 나왔던 칸: 앞 컷을 보여 주고 '다르게'를 못 박는다
            prev = work / f"kf_c{ep['clips'][k - 1]['no']:02d}.png"
            if prev.exists():
                refs.append(prev)
                text += (f"Reference image {len(refs)} is the PREVIOUS shot. This shot must look clearly different from it: "
                         f"a different shot size and a different camera angle, exactly as SHOT says. ")
        r = gen_image(text + "\n\nSHOT DESCRIPTION:\n" + c["imagePrompt"] + f"\nPROPS: {props}" + KF_TAIL, refs, out)
        res[name] = r
    missing = [f"c{c['no']:02d}" for c in ep["clips"] if not (work / f"kf_c{c['no']:02d}.png").exists()]
    if missing:
        raise RuntimeError(f"첫 장면 실패: {missing}")


# ---------- 3. 영상 ----------
def _find_video(o):
    if isinstance(o, dict):
        mt = str(o.get("mime_type") or o.get("mimeType") or "")
        if (o.get("type") == "video" or mt.startswith("video")) and (o.get("data") or o.get("uri")):
            return o
        for v in o.values():
            f = _find_video(v)
            if f:
                return f
    elif isinstance(o, list):
        for v in o:
            f = _find_video(v)
            if f:
                return f
    return None


def _omni(key, start: Path, prompt: str, setimg: Path | None = None) -> bytes:
    hdr = {"x-goog-api-key": key, "Content-Type": "application/json"}
    extra = [{"type": "image", **_b64img(setimg)}] if setimg and setimg.exists() else []
    body = {"model": CLIP_MODEL,
            "input": [{"type": "image", **_b64img(start)}, *extra, {"type": "text", "text": prompt}],
            "response_format": {"type": "video", "resolution": "720p", "aspect_ratio": "9:16"},
            "generation_config": {"video_config": {"task": "image_to_video"}}}
    t0 = time.time()
    st, raw = _http(f"{API}/interactions", json.dumps(body).encode(), hdr, timeout=900)
    if st != 200:
        raise RuntimeError(f"Omni HTTP {st}: {raw[:300].decode('utf-8', 'replace')}")
    j = json.loads(raw)
    while not _find_video(j) and j.get("id") and str(j.get("status", "")).lower() in ("in_progress", "pending", "running", "queued"):
        if time.time() - t0 > 900:
            raise TimeoutError("Omni 15분 초과")
        time.sleep(10)
        st, raw = _http(f"{API}/interactions/{j['id']}", None, hdr)
        j = json.loads(raw) if st == 200 else j
    v = _find_video(j)
    if not v:
        raise RuntimeError("Omni 영상 없음(안전 필터 가능)")
    if v.get("data"):
        return base64.b64decode(v["data"])
    fid = str(v["uri"]).rstrip("/").split("/")[-1]
    for _ in range(90):
        st, raw = _http(f"{API}/files/{fid}", None, hdr)
        if st == 200 and json.loads(raw).get("state") == "ACTIVE":
            break
        time.sleep(5)
    st, vid = _http(f"{API}/files/{fid}:download?alt=media", None, hdr)
    if st != 200:
        raise RuntimeError(f"Omni 다운로드 실패 HTTP {st}")
    return vid


def _veo(key, start: Path, prompt: str, setimg: Path | None = None, secs: int = 8) -> bytes:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    op = client.models.generate_videos(
        model=VEO_FALLBACK, prompt=prompt,
        image=types.Image(image_bytes=start.read_bytes(), mime_type="image/png"),
        config=types.GenerateVideosConfig(aspect_ratio="9:16", resolution="720p", duration_seconds=int(secs), number_of_videos=1))
    t0 = time.time()
    while not op.done:
        if time.time() - t0 > 900:
            raise TimeoutError("Veo 15분 초과")
        time.sleep(10)
        op = client.operations.get(op)
    resp = getattr(op, "response", None) or getattr(op, "result", None)
    if not resp or not getattr(resp, "generated_videos", None):
        raise RuntimeError(f"Veo 영상 없음: {str(getattr(op, 'error', ''))[:200]}")
    v = resp.generated_videos[0].video
    client.files.download(file=v)
    tmp = Path("/tmp") / f"veo_{int(time.time())}.mp4"
    v.save(str(tmp))
    return tmp.read_bytes()


CLIP_TAIL = ("\nThe attached image is the FIRST FRAME: the room, door, walls, floor, table, seat, lamp and props must stay "
             "exactly like it for the whole clip — nothing is added, removed, moved or reshaped. Only the camera and the character move, "
             "slowly and smoothly. The bowl and the food never change. Keep the framing of the first frame: the camera does "
             "not pull back into a wide shot and does not cut to another angle at the end.\nSOUND: none needed (it will be replaced). No dialogue. "
             "NEVER SHOW: text, letters, numbers, logos, packaging, humans, banknotes or cash, the character changing shape, "
             "morphing objects, changing furniture, cuts.")


# 역할별 동작 고정 — 시식 중에 걸어 나가거나(3차 c04), 퇴장하다 되돌아오던(3차 c07) 오류 대책
ROLE_LOCK = {
    "order": "The {n} stays seated on the cushion in the same spot for the whole clip.",
    "serve": "The {n} stays at the table in the same spot for the whole clip.",
    "taste": "The {n} stays at the table in the same spot, eating from the bowl, for the whole clip. It never walks away "
             "and never leaves the frame. The bowl stays on the table.",
    "bill": "The {n} stays at the table in the same spot for the whole clip.",
    "exit": "The {n} walks away from the camera toward the door and goes out; it never turns around to walk back "
            "toward the camera.",
}


SET_CONVERGE = 8.0   # 컷 화면이 빈 가게 세트 사진과 이만큼 비슷해지면 '세트 사진으로 흘러간 것'(5차 실측: 1~6)


def clip_drift(clip: Path, first: Path, work: Path):
    """컷 뒤쪽(4~7.8초)이 빈 가게 세트 사진으로 흘러갔는지 — 가장 비슷한 순간의 차이값(작을수록 세트 사진과 같음)."""
    setimg = work / "set.png"
    if not setimg.exists():
        return None
    try:
        best = None
        D = _dur(clip)
        for t in (4.0, 5.0, 6.0, 7.0, D - 0.2):
            if t >= D:
                continue
            p = work / f"_drift_{clip.stem}.png"
            _ff(["-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", "-vf", "scale=720:1280", str(p)])
            d = look_diff(setimg, p)
            p.unlink()
            best = d if best is None else min(best, d)
        return None if best is None else round(best, 1)
    except Exception:  # noqa: BLE001
        return None


CLIP_CHOICES = (4, 6, 8)      # 영상 AI에 주문할 길이(초). 대사 길이에 맞춰 고른다(사용자 확정 2026-09: 8초 고정 폐기)
CLIP_STRETCH = 1.25           # 대사가 조금 길면 영상을 이만큼까지 늘려 맞춘다(build_segment의 1.3배 안쪽)


def clip_seconds(work, name):
    """녹음(v_cXX.wav)이 있으면 컷 길이(앞뒤 여유 포함)를 재서 4·6·8초 중 가장 짧은 걸 고른다. 녹음이 없으면 8초."""
    voice = work / f"v_{name}.wav"
    if not voice.exists():
        return 8
    L = max(MIN_SEG, LEAD + _dur(voice) + TAIL)
    return next((d for d in CLIP_CHOICES if d * CLIP_STRETCH >= L), CLIP_CHOICES[-1])


def fit_prompt(prompt, d):
    """클립 프롬프트의 '8-second'와 [0-4s]·[4-8s] 시간 표시를 d초에 맞게 바꾼다. Omni는 길이를 이 시간 표시로 알아듣는다."""
    k = d / 8.0
    fmt = lambda x: (f"{x:.1f}".rstrip("0").rstrip("."))
    prompt = re.sub(r"\b8-second\b", f"{d}-second", prompt)
    prompt = re.sub(r"\b8 seconds\b", f"{d} seconds", prompt)
    return re.sub(r"\[(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)s\]",
                  lambda m: f"[{fmt(float(m.group(1)) * k)}-{fmt(float(m.group(2)) * k)}s]", prompt)


def step_clips(ep, epdir, work, log, redo):
    key = _key("GEMINI_API_KEY")
    res = log.setdefault("clips", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out = work / f"{name}.mp4"
        if out.exists() and name not in redo:
            continue
        lock = ROLE_LOCK.get(c.get("role"), "").format(n="kitten" if ep.get("species") == "cat" else "puppy")
        props = bowl_state([x.get("role") for x in ep["clips"]], ep["clips"].index(c))
        secs = clip_seconds(work, name)
        prompt = (fit_prompt(c["prompt"], secs) + (f"\nACTION LOCK: {lock}" if lock else "")
                  + (f"\nPROPS (for the whole clip — nothing appears or disappears): {props}" if props else "") + CLIP_TAIL)
        rec = {"attempts": [], "target_s": secs}
        for label, fn in (("omni", _omni), ("veo-lite", lambda k, st, p, si: _veo(k, st, p, si, secs))):
            t0 = time.time()
            try:
                # ⚠️ 세트 원본(빈 가게 사진)은 영상 AI에 넣지 않는다 — 컷 끝에서 그 사진으로 되돌아가며
                #    강아지가 사라지고 와이드로 빠지는 끊김이 생겼다(5차 실측). 배경 통일은 격자 첫 장면이 맡는다.
                out.write_bytes(fn(key, work / f"kf_{name}.png", prompt, None))
                rec["attempts"].append({"model": label, "ok": True, "wait_s": round(time.time() - t0, 1)})
                rec["model"], rec["sec"] = label, round(_dur(out), 2)
                # 컷 뒤쪽이 첫 장면과 전혀 다른 화면(강아지가 사라진 빈 방·와이드로 빠짐)으로 흘렀는지 검사 → 1회만 다시 뽑기
                drift = clip_drift(out, work / f"kf_{name}.png", work)
                rec["drift"] = drift
                if drift is not None and drift < SET_CONVERGE and not rec.get("redrawn"):
                    rec["redrawn"] = True
                    rec["attempts"].append({"model": label, "note": f"뒤쪽이 빈 가게 사진으로 흘러감({drift}) → 다시 뽑기"})
                    out.write_bytes(fn(key, work / f"kf_{name}.png", prompt, None))
                    rec["drift_after"] = clip_drift(out, work / f"kf_{name}.png", work)
                break
            except Exception as e:  # noqa: BLE001
                rec["attempts"].append({"model": label, "ok": False, "error": str(e)[:300]})
        res[name] = rec
    missing = [f"c{c['no']:02d}" for c in ep["clips"] if not (work / f"c{c['no']:02d}.mp4").exists()]
    if missing:
        raise RuntimeError(f"영상 실패: {missing}")


# ---------- 4. 내레이션 ----------
def _pcm_to_wav(pcm: bytes, out: Path, speed: float, pitch_st: float = VOICE_PITCH_ST):
    raw = out.with_suffix(".pcm")
    raw.write_bytes(pcm)
    # 앞뒤 무음 제거 → 음높이만 pitch_st 반음 낮추고(길이 유지) → 정확히 speed배속
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
    r = 2 ** (pitch_st / 12)
    pitch = f"asetrate={24000 * r:.1f},aresample=24000," if abs(pitch_st) > 0.01 else ""
    _ff(["-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw), "-af", f"{trim},{pitch}atempo={speed / r:.4f}", str(out)])
    raw.unlink()


def tts_gemini(text: str, out: Path, voice: str = VOICE_NAME) -> dict:
    key = _key("GEMINI_API_KEY")
    model = _pick_model(key, TTS_MODELS)
    body = {"contents": [{"role": "user", "parts": [{"text": f"{VOICE_DIRECTION}\n\n대사: {text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for attempt in range(3):
        code, raw = _http(f"{API}/models/{model}:generateContent", json.dumps(body).encode(),
                          {"x-goog-api-key": key, "Content-Type": "application/json"})
        if code == 200:
            parts = [p for c in json.loads(raw).get("candidates", []) for p in c.get("content", {}).get("parts", [])
                     if "inlineData" in p]
            if parts:
                _pcm_to_wav(base64.b64decode(parts[0]["inlineData"]["data"]), out, VOICE_SPEED)
                return {"ok": True, "model": model, "voice": voice, "sec": round(_dur(out), 2)}
            err = "소리 없음"
        else:
            err = f"HTTP {code}: {raw[:200].decode('utf-8', 'replace')}"
        time.sleep(4 * (attempt + 1))
    return {"ok": False, "model": model, "voice": voice, "error": err}


def tts_cloud(text: str, out: Path) -> dict:
    key = _key("GOOGLE_TTS_KEY")
    ssml = f'<speak><prosody rate="{TTS_RATE}" pitch="{TTS_PITCH}">{text}</prosody></speak>'
    body = {"input": {"ssml": ssml}, "voice": TTS_VOICE,
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000}}
    code, raw = _http("https://texttospeech.googleapis.com/v1/text:synthesize", json.dumps(body).encode(),
                      {"x-goog-api-key": key, "Content-Type": "application/json"})
    if code != 200:
        return {"ok": False, "error": raw[:300].decode("utf-8", "replace")}
    out.write_bytes(base64.b64decode(json.loads(raw)["audioContent"]))
    return {"ok": True, "voice": "cloud-" + TTS_VOICE["name"], "sec": round(_dur(out), 2)}


def step_voices(ep, epdir, work, log, voices=None):
    """성우 고르기용 샘플 — 같은 대사(입장+첫 시식)를 후보 목소리마다 같은 연기 지시·음높이·1.2배속으로 읽힌다."""
    lines = [c["line"] for c in ep["clips"] if c.get("role") == "enter"][:1]
    lines += [c["line"] for c in ep["clips"] if c.get("role") == "taste"][:1]
    text = " ".join(lines) or ep["clips"][0]["line"]
    res = log.setdefault("voices", {})
    for v in (voices or VOICE_SAMPLES):
        wav = work / f"voice_{v}.wav"
        r = tts_gemini(text, wav, v)
        if r["ok"]:
            _ff(["-i", str(wav), "-b:a", "128k", str(work / f"voice_{v}.mp3")])
            wav.unlink()
        res[v] = r
    log["voices_text"] = text


# ---------- 시그니처 배경음악(사용자 요청 2026-09: 최소 1분) ----------
# 구글 음악 생성 AI(Lyria RealTime, Gemini 키)로 만든다 → 저작권 걱정 없는 우리 곡. 후보를 들어보고 하나를 signature.mp3로 고정.
BGM_SECONDS = 75
BGM_PROMPTS = {
    "jazz_trio": ("Mellow late-night jazz trio for a quiet solo dinner in a small neighborhood diner: brushed drums, warm "
                  "upright bass, soft clean electric jazz guitar melody, relaxed and cozy, gentle swing, instrumental", 84),
    "bossa_guitar": ("Laid-back acoustic nylon guitar and soft piano, gentle bossa nova groove, warm and tasteful, calm "
                     "restaurant background music, instrumental", 90),
    "lofi_rhodes": ("Slow lo-fi jazz with rhodes piano and muted trumpet, calm and contemplative, soft vinyl texture, "
                    "late afternoon mood, instrumental", 76),
}
MUSIC_DIR = Path(__file__).resolve().parent.parent / "music"
SIGNATURE_BGM = MUSIC_DIR / "signature.mp3"


def _lyria(prompt: str, bpm: int, seconds: int, out: Path) -> dict:
    import asyncio
    from google import genai
    from google.genai import types
    key = _key("GEMINI_API_KEY")

    async def run():
        client = genai.Client(api_key=key, http_options={"api_version": "v1alpha"})
        buf = bytearray()
        target = seconds * 48000 * 2 * 2           # 48kHz · 16bit · 스테레오
        async with client.aio.live.music.connect(model="models/lyria-realtime-exp") as session:
            await session.set_weighted_prompts(prompts=[types.WeightedPrompt(text=prompt, weight=1.0)])
            await session.set_music_generation_config(config=types.LiveMusicGenerationConfig(bpm=bpm, temperature=1.0))
            await session.play()
            async for message in session.receive():
                sc = getattr(message, "server_content", None)
                for ch in (getattr(sc, "audio_chunks", None) or []):
                    buf.extend(ch.data)
                if len(buf) >= target:
                    break
        return bytes(buf)

    pcm = asyncio.run(asyncio.wait_for(run(), timeout=seconds * 4 + 60))
    raw = out.with_suffix(".pcm")
    raw.write_bytes(pcm)
    _ff(["-f", "s16le", "-ar", "48000", "-ac", "2", "-i", str(raw), "-af",
         f"afade=t=in:d=2,afade=t=out:st={seconds - 4}:d=4,loudnorm=I=-18:TP=-2", "-b:a", "192k", str(out)])
    raw.unlink()
    return {"ok": True, "sec": round(_dur(out), 1)}


def step_bgm(work, log, names=None):
    res = log.setdefault("bgm", {})
    for name in (names or list(BGM_PROMPTS)):
        prompt, bpm = BGM_PROMPTS[name]
        out = work / f"bgm_{name}.mp3"
        try:
            res[name] = _lyria(prompt, bpm, BGM_SECONDS, out)
        except Exception as e:  # noqa: BLE001
            res[name] = {"ok": False, "error": str(e)[:300]}


ROOT = Path(__file__).resolve().parents[2]     # 저장소 맨 위
IG_RAW_BASE = "https://raw.githubusercontent.com/jtaechul/Product/claude/book-carousel-auto-upload-xpwihz"
COUPANG_NOTE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def _ig_token():
    """시크릿에 따옴표·줄바꿈·'Bearer '가 섞여 들어가도 읽히게 정리한다. 값은 기록하지 않는다."""
    t = os.environ.get("IG_ACCESS_TOKEN", "").strip().strip('"').strip("'").strip()
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return "".join(t.split())


def _ig_get(url, params):
    from urllib.parse import urlencode
    code, raw = _http(f"{url}?{urlencode(params)}", timeout=30)
    try:
        return code, json.loads(raw)
    except Exception:  # noqa: BLE001
        return code, {}


def _ig_account(tok):
    """(API 주소, IG 사용자 ID, 계정 이름, 진단). 신 인스타 로그인 → 페이스북 페이지 연결 순으로 찾는다."""
    diag = {"token_kind": ("instagram_login(IGAA)" if tok.startswith("IG") else
                           "facebook(EAA)" if tok.startswith("EAA") else "알 수 없음"), "token_len": len(tok)}
    code, j = _ig_get("https://graph.instagram.com/me", {"fields": "user_id,username", "access_token": tok})
    diag["instagram"] = {"http": code, "error": (j.get("error") or {}).get("message")}
    uid = str(j.get("user_id") or j.get("id") or "") if code == 200 else ""
    if uid:
        return "https://graph.instagram.com", uid, j.get("username", ""), diag
    code, j = _ig_get("https://graph.facebook.com/v21.0/me/accounts",
                      {"fields": "instagram_business_account{id,username}", "access_token": tok})
    diag["facebook_pages"] = {"http": code, "error": (j.get("error") or {}).get("message")}
    for pg in j.get("data", []) if code == 200 else []:
        iba = pg.get("instagram_business_account") or {}
        if iba.get("id"):
            return "https://graph.facebook.com/v21.0", str(iba["id"]), iba.get("username", ""), diag
    return None, None, None, diag


def step_ig_probe(log):
    """어느 인스타 계정에 올릴 수 있는 토큰인지 확인만 한다(발행 없음). 토큰 값은 기록하지 않는다."""
    tok = _ig_token()
    if not tok:
        log["ig_probe"] = {"ok": False, "error": "IG_ACCESS_TOKEN 없음"}
        return
    base, uid, name, diag = _ig_account(tok)
    log["ig_probe"] = {"ok": bool(uid), "username": name, "api": base, **diag,
                       "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


IG_HANDLE = "@lord.shiba.ydb"      # '프로필 링크' 문장 바로 아래 줄(사용자 지시 2026-10)


def _with_handle(cap: str) -> str:
    lines = [l for l in cap.split("\n") if l.strip() != IG_HANDLE]
    i = next((k for k, l in enumerate(lines) if "프로필 링크" in l), -1)
    if i >= 0:
        lines.insert(i + 1, IG_HANDLE)
    else:
        lines.append(IG_HANDLE)
    return "\n".join(lines).strip()


def ig_caption(ep):
    """인스타 캡션: 모델이 쓴 캡션 + 해시태그, 쿠팡 파트너스 고지는 없으면 반드시 붙인다(법적 요구)."""
    cap = _with_handle(str(ep.get("caption") or "").strip())
    tags = " ".join(t for t in (ep.get("hashtags") or []) if t and t not in cap)
    if tags:
        cap = f"{cap}\n\n{tags}"
    if "쿠팡 파트너스" not in cap:
        cap = f"{cap}\n\n{COUPANG_NOTE}"
    return cap[:2150]


def step_ig_publish(ep, epdir, work, log, force=False):
    """완성된 final.mp4(공개 저장소 raw 주소)를 인스타 릴스로 올린다. 같은 편은 한 번만(force로만 다시)."""
    if log.get("ig_publish", {}).get("media_id") and not force:
        return
    final = work / "final.mp4"
    if not final.exists():
        raise RuntimeError("final.mp4 없음 — 먼저 영상을 완성하세요")
    tok = _ig_token()
    if not tok:
        raise RuntimeError("IG_ACCESS_TOKEN 없음")
    base, uid, name, diag = _ig_account(tok)
    if not uid:
        log["ig_publish"] = {"ok": False, "error": "토큰으로 인스타 계정을 못 찾음(만료·권한)", **diag}
        raise RuntimeError("인스타 토큰이 유효하지 않음(만료 가능) — log.json의 ig_publish 참고")
    video_url = f"{IG_RAW_BASE}/{final.resolve().relative_to(ROOT).as_posix()}"
    from urllib.parse import urlencode
    params = {"media_type": "REELS", "video_url": video_url, "caption": ig_caption(ep),
              "share_to_feed": "true", "access_token": tok}
    cover = work / "cover.jpg"
    if cover.exists():                                    # 표지(후킹 이미지)를 릴스 커버로
        params["cover_url"] = f"{IG_RAW_BASE}/{cover.resolve().relative_to(ROOT).as_posix()}"
    body = urlencode(params).encode()
    code, raw = _http(f"{base}/{uid}/media", data=body, timeout=60)
    j = json.loads(raw or b"{}")
    cid = str(j.get("id") or "")
    if not cid:
        log["ig_publish"] = {"ok": False, "step": "container", "http": code,
                             "error": (j.get("error") or {}).get("message")}
        raise RuntimeError(f"릴스 컨테이너 생성 실패({code})")
    status = ""
    for _ in range(60):                                   # 인스타가 영상을 가져가 처리할 때까지(최대 10분)
        time.sleep(10)
        _, st = _ig_get(f"{base}/{cid}", {"fields": "status_code,status", "access_token": tok})
        status = st.get("status_code", "")
        if status in ("FINISHED", "ERROR", "EXPIRED"):
            break
    if status != "FINISHED":
        log["ig_publish"] = {"ok": False, "step": "processing", "status": status}
        raise RuntimeError(f"인스타 영상 처리 실패({status})")
    code, raw = _http(f"{base}/{uid}/media_publish", data=urlencode({"creation_id": cid, "access_token": tok}).encode(),
                      timeout=60)
    j = json.loads(raw or b"{}")
    mid = str(j.get("id") or "")
    if not mid:
        log["ig_publish"] = {"ok": False, "step": "publish", "http": code, "error": (j.get("error") or {}).get("message")}
        raise RuntimeError(f"릴스 발행 실패({code})")
    _, pl = _ig_get(f"{base}/{mid}", {"fields": "permalink", "access_token": tok})
    log["ig_publish"] = {"ok": True, "media_id": mid, "username": name, "permalink": pl.get("permalink"),
                         "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def split_sentences(text: str) -> list[str]:
    """대사를 자막·낭독 단위 문장으로. "음…" 같은 짧은 조각은 다음 문장과 붙인다."""
    out = []
    for x in [x.strip() for x in re.split(r"(?<=[.?…])\s+", (text or "").strip()) if x.strip()]:
        if out and len(out[-1]) <= 4:
            out[-1] = f"{out[-1]} {x}"
        else:
            out.append(x)
    return out


SENT_GAP = 0.28          # 문장 사이 숨 고르기(초)


def _sentence_times(wav: Path, sents: list[str]) -> list[dict]:
    """컷 전체를 한 번에 녹음한 뒤(톤이 문장마다 흔들리지 않게), 문장 사이 쉼(무음)을 찾아 문장별 시작·끝을 잰다.
    쉼이 모자라면 글자 수 비례로 나눈다."""
    D = _dur(wav)
    if len(sents) <= 1:
        return [{"text": sents[0] if sents else "", "start": 0.0, "end": round(D, 3)}]
    r = subprocess.run([FFMPEG, "-i", str(wav), "-af", "silencedetect=noise=-38dB:d=0.12", "-f", "null", "-"],
                       capture_output=True, text=True)
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    gaps = [(e - s_, s_, e) for s_, e in zip(st, en) if 0.15 < s_ and e < D - 0.1]
    need = len(sents) - 1
    tot = sum(len(x) for x in sents)
    guess, acc = [], 0                                 # 글자 수 비례로 예상한 경계 위치
    for x in sents[:-1]:
        acc += len(x)
        guess.append(D * acc / tot)
    cuts = []
    for g in guess:                                   # 예상 위치에 가장 가까운 쉼을 하나씩 짝짓는다
        cand = [c for c in gaps if c not in cuts]
        if not cand:
            break
        best = min(cand, key=lambda c: abs((c[1] + c[2]) / 2 - g) - c[0])
        if abs((best[1] + best[2]) / 2 - g) < D * 0.25:
            cuts.append(best)
    if len(cuts) == need:
        cuts.sort(key=lambda c: c[1])
        bounds = [0.0] + [c[1] for c in cuts]
        ends = [c[1] for c in cuts] + [D]
        starts = [0.0] + [c[2] for c in cuts]
        return [{"text": t, "start": round(a_, 3), "end": round(b_, 3)} for t, a_, b_ in zip(sents, starts, ends)]
    out, t0 = [], 0.0
    for t, g in zip(sents, guess + [D]):
        out.append({"text": t, "start": round(t0, 3), "end": round(g, 3)})
        t0 = g
    return out


def no_gun(t: str) -> str:
    """말끝 '~군'을 '~네'로(적시는군→적시네, 좋군→좋네, 뒷맛이로군→뒷맛이다)."""
    t = re.sub(r"이로군(?=[.…,?\s]|$)", "이다", t)
    t = re.sub(r"로군(?=[.…,?\s]|$)", "다", t)
    t = re.sub(r"는군(?=[.…,?\s]|$)", "네", t)
    return re.sub(r"([가-힣])군(?=[.…,?\s]|$)", lambda m: m.group(0) if m.group(1) in "장해공육국아" else m.group(1) + "네", t)


def step_tts(ep, epdir, work, log, redo):
    """컷 대사 전체를 한 번에 녹음한다(문장마다 따로 녹음하면 톤이 조금씩 달라짐 — 사용자 지적 2026-09)."""
    res = log.setdefault("tts", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out, tj = work / f"v_{name}.wav", work / f"v_{name}.json"
        line = no_gun((c.get("line") or "").strip())      # 말끝 '~군' 금지(사용자 확정 2026-09) — 새로 녹음할 때만 적용해 자막·목소리가 어긋나지 않게
        if not line or (out.exists() and tj.exists() and name not in redo and f"v_{name}" not in redo):
            continue
        r = tts_gemini(line, out)
        if not r["ok"]:
            r = {"gemini": r, **tts_cloud(line, out)}
        if out.exists():
            tj.write_text(json.dumps(_sentence_times(out, split_sentences(line)), ensure_ascii=False, indent=1),
                          encoding="utf-8")
        res[name] = r


# ---------- 5. 조립 ----------
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
SFX_DIR = Path(__file__).resolve().parent.parent / "sfx"           # 효과음(우리가 만든 것만)
SUB_FONT = FONT_DIR / "Pretendard-ExtraBold.otf"        # 자막: 굵고 깔끔한 고딕(배경 상자 없이 글자만)
SERIF_XB = FONT_DIR / "NanumMyeongjo-ExtraBold.ttf"     # 제목·메뉴판·영수증: 식당 간판 같은 명조
SERIF_B = FONT_DIR / "NanumMyeongjo-Bold.ttf"
INK, PAPER, SEAL = (42, 30, 22), (246, 240, 226), (178, 34, 34)


def _f(path: Path, size: int):
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return _font(size)


def _wrap(text, font, width):
    lines, cur = [], ""
    for word in text.split(" "):
        t = (cur + " " + word).strip()
        if font.getlength(t) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:                      # 한 단어가 너무 길면 글자 단위로 자른다
        while font.getlength(ln) > width:
            k = len(ln)
            while k > 1 and font.getlength(ln[:k]) > width:
                k -= 1
            out.append(ln[:k])
            ln = ln[k:]
        out.append(ln)
    return out


def _balanced(text, font, width):
    """두 줄이 되면 줄 길이를 비슷하게(윗줄만 길고 아랫줄에 한 단어 남는 모양 방지)."""
    lines = _wrap(text, font, width)
    if len(lines) == 2:
        words = text.split(" ")
        best = None
        for k in range(1, len(words)):
            a, b = " ".join(words[:k]), " ".join(words[k:])
            if font.getlength(a) <= width and font.getlength(b) <= width:
                d = abs(font.getlength(a) - font.getlength(b))
                if best is None or d < best[0]:
                    best = (d, [a, b])
        if best:
            return best[1]
    return lines


def _fit_lines(text, path, size, width, max_lines=2, min_size=26):
    """글이 max_lines 줄 안에 다 들어가도록 글자 크기를 줄인다(메뉴 이름 끝이 잘리던 문제 — 5차 실측)."""
    while True:
        f = _f(path, size)
        lines = _balanced(text, f, width)
        if len(lines) <= max_lines or size <= min_size:
            return f, lines[:max_lines], size
        size -= 2


def _fit_2or3(text, path, size, width, min2, min3):
    """두 줄에 들어가면 두 줄(한 단어만 남는 셋째 줄 방지), 안 되면 세 줄."""
    f, lines, fs = _fit_lines(text, path, size, width, max_lines=2, min_size=min2)
    if len(_balanced(text, f, width)) <= 2:
        return f, lines, fs
    return _fit_lines(text, path, size, width, max_lines=3, min_size=min3)


def _shadowed(size, draw_fn, blur=6, alpha=150, offset=(0, 4)):
    """글자·카드에 부드러운 그림자를 깐다(검은 상자 대신)."""
    from PIL import ImageFilter
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    mask = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(mask), shadow=True)
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    a = mask.split()[3].point(lambda v: min(255, v) * alpha // 255)
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(blur)))
    base.alpha_composite(sh, offset)
    draw_fn(ImageDraw.Draw(base), shadow=False)
    return base


def subtitle_png(text, out: Path):
    """자막 — 배경 상자 없이 흰 글자 + 얇은 외곽선 + 부드러운 그림자(사용자 지시 2026-09)."""
    f = _f(SUB_FONT, 50)
    lines = _balanced(text, f, W - 110)[:3]
    lh = 66
    y0 = int(H * 0.79) - lh * len(lines) // 2

    def draw(dr, shadow):
        for i, ln in enumerate(lines):
            x = (W - f.getlength(ln)) / 2
            if shadow:
                dr.text((x, y0 + i * lh), ln, font=f, fill=(0, 0, 0, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))
            else:
                dr.text((x, y0 + i * lh), ln, font=f, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(20, 16, 12, 235))
    _shadowed((W, H), draw, blur=7, alpha=120, offset=(0, 3)).save(out)


def title_png(series, epno, out: Path):
    """오프닝 제목 — 드라마 타이틀처럼 명조 + 가는 선 + 제N화."""
    f1, f2 = _f(SERIF_XB, 58), _f(SERIF_B, 30)

    def draw(dr, shadow):
        col = (0, 0, 0, 255) if shadow else (255, 250, 240, 255)
        x, y = 56, 118
        dr.text((x, y), series, font=f1, fill=col)
        w = f1.getlength(series)
        dr.line([x, y + 84, x + w, y + 84], fill=col if shadow else (226, 190, 120, 255), width=2)
        if epno:
            dr.text((x, y + 98), f"제{epno}화", font=f2, fill=col if shadow else (236, 214, 170, 255))
    _shadowed((W, H), draw, blur=8, alpha=170).save(out)


def _seal(dr, x_right, y, h, text="품격"):
    """붉은 낙관 — 가로로 긴 빨간 박스에 글자 한 줄(사용자 지시 2026-09). 이모지 대신 직접 그린 도형.
    x_right = 박스 오른쪽 끝, y = 위쪽, h = 높이. 너비는 글자 길이에 맞춘다."""
    f = _f(SERIF_XB, int(h * 0.56))
    tw = f.getlength(text)
    w = tw + h * 0.7
    x = x_right - w
    dr.rounded_rectangle([x, y, x_right, y + h], radius=int(h * 0.14), fill=SEAL + (238,))
    dr.rounded_rectangle([x + 4, y + 4, x_right - 4, y + h - 4], radius=int(h * 0.1), outline=(255, 226, 214, 150), width=1)
    a, d = f.getmetrics()
    dr.text((x + (w - tw) / 2, y + (h - a - d) / 2 + 1), text, font=f, fill=(255, 244, 236, 255))


def menu_png(name, out: Path):
    """오늘의 메뉴 — 한지 느낌 크림색 종이 + 이중 테두리 + 명조 + 붉은 낙관. 메뉴 이름만(상품명·사진 금지)."""
    bw, bh = 560, 300
    x0, y0 = (W - bw) // 2, 150
    ft = _f(SERIF_B, 28)
    fn, lines, fsz = _fit_lines(name, SERIF_XB, 50, bw - 120)

    def draw(dr, shadow):
        if shadow:
            dr.rectangle([x0, y0, x0 + bw, y0 + bh], fill=(0, 0, 0, 255))
            return
        dr.rectangle([x0, y0, x0 + bw, y0 + bh], fill=PAPER + (250,))
        dr.rectangle([x0 + 14, y0 + 14, x0 + bw - 14, y0 + bh - 14], outline=INK + (200,), width=2)
        dr.rectangle([x0 + 20, y0 + 20, x0 + bw - 20, y0 + bh - 20], outline=INK + (110,), width=1)
        t = "오 늘 의   메 뉴"
        dr.text(((W - ft.getlength(t)) / 2, y0 + 42), t, font=ft, fill=(120, 92, 64, 255))
        cx, cy = W // 2, y0 + 96
        dr.line([cx - 120, cy, cx - 12, cy], fill=(150, 120, 90, 255), width=1)
        dr.line([cx + 12, cy, cx + 120, cy], fill=(150, 120, 90, 255), width=1)
        dr.polygon([(cx, cy - 6), (cx + 6, cy), (cx, cy + 6), (cx - 6, cy)], fill=(150, 120, 90, 255))
        top = y0 + 128 + (32 if len(lines) == 1 else 0)
        for i, ln in enumerate(lines):
            dr.text(((W - fn.getlength(ln)) / 2, top + i * int(fsz * 1.32)), ln, font=fn, fill=INK + (255,))
        _seal(dr, x0 + bw - 30, y0 + 30, 40)          # 오른쪽 위 모서리(메뉴 이름과 겹치지 않게)
    _shadowed((W, H), draw, blur=14, alpha=140, offset=(0, 10)).save(out)


def bill_png(text, out: Path):
    bw, bh = 480, 200
    x0, y0 = (W - bw) // 2, 170
    fh, fb = _f(SERIF_B, 28), _f(SERIF_XB, 44)

    def draw(dr, shadow):
        if shadow:
            dr.rectangle([x0, y0, x0 + bw, y0 + bh], fill=(0, 0, 0, 255))
            return
        dr.rectangle([x0, y0, x0 + bw, y0 + bh], fill=PAPER + (250,))
        dr.rectangle([x0 + 12, y0 + 12, x0 + bw - 12, y0 + bh - 12], outline=INK + (170,), width=2)
        dr.text(((W - fh.getlength("계 산 서")) / 2, y0 + 32), "계 산 서", font=fh, fill=(120, 92, 64, 255))
        for i, ln in enumerate(_balanced(text, fb, bw - 70)[:2]):
            dr.text(((W - fb.getlength(ln)) / 2, y0 + 92 + i * 54), ln, font=fb, fill=INK + (255,))
    _shadowed((W, H), draw, blur=12, alpha=130, offset=(0, 8)).save(out)


COVER_HOOK = ("배가 고프다.", "심각하다.")


def _cover_bg(ep, work):
    """표지 배경: 첫 시식 컷(먹는 순간 클로즈업)이 가장 입맛을 당긴다. 없으면 서빙·주문 컷."""
    order = ["taste", "serve", "order", "enter"]
    for role in order:
        for c in ep.get("clips", []):
            if c.get("role") == role:
                kf = work / f"kf_c{c['no']:02d}.png"
                if kf.exists():
                    return kf
    return None


def step_cover(ep, work, log):
    """릴스 표지(후킹 이미지) — 조립할 때마다 같이 만든다. 비용 없음(이미 있는 장면 그림 + 글자)."""
    try:
        out = cover_png(ep, work, work / "cover.jpg")
        log["cover"] = out.name if out else ""
    except Exception as e:  # noqa: BLE001
        log["cover"] = ""
        log["cover_error"] = str(e)[:200]


def cover_png(ep, work, out: Path):
    """릴스 표지(후킹 이미지) 1080x1920. 인스타 격자는 가운데 3:4만 보여 주므로 글자는 위아래 12.5% 안쪽에만 둔다.
    상품명·포장은 넣지 않는다(메뉴 이름만)."""
    from PIL import ImageFilter
    CW, CH = 1080, 1920
    src = _cover_bg(ep, work)
    if not src:
        return None
    bg = Image.open(src).convert("RGB")
    s = max(CW / bg.width, CH / bg.height)
    bg = bg.resize((round(bg.width * s), round(bg.height * s)), Image.LANCZOS)
    bg = bg.crop(((bg.width - CW) // 2, (bg.height - CH) // 2, (bg.width - CW) // 2 + CW, (bg.height - CH) // 2 + CH))
    img = bg.convert("RGBA")
    # 위·아래 어둡게(글자가 읽히게), 가운데는 그대로
    grad = Image.new("L", (1, CH))
    for y in range(CH):
        t = y / CH
        a = 0
        if t < 0.46:
            a = int(215 * (1 - t / 0.46) ** 1.3)
        elif t > 0.66:
            a = int(225 * ((t - 0.66) / 0.34) ** 1.2)
        grad.putpixel((0, y), a)
    shade = Image.new("RGBA", (CW, CH), (12, 8, 6, 255))
    shade.putalpha(grad.resize((CW, CH)))
    img.alpha_composite(shade)
    epno = str(ep.get("episode") or "").strip()
    fser, fep = _f(SERIF_XB, 50), _f(SERIF_B, 38)
    # 표지 큰 글씨 = 대본의 후킹 문구(제품 특징을 비튼 한 줄, 사용자 확정 2026-09). 없으면 시리즈 오프닝.
    hook = str(ep.get("hookLine") or "").strip()
    if hook:
        fhook, hook_lines, hook_size = _fit_2or3(hook, SUB_FONT, 130, CW - 160, 74, 74)
    else:
        fhook, hook_lines, hook_size = _f(SUB_FONT, 150), list(COVER_HOOK), 150
    menu = str(ep.get("menuName") or "").strip()

    def draw(dr, shadow):
        col = (0, 0, 0, 255)
        x, y = 80, 270                                   # 3:4 안전 영역(위 240px) 바로 아래
        head = f"{ep.get('series') or '한 그릇의 품격'}"
        dr.text((x, y), head, font=fser, fill=col if shadow else (255, 248, 236, 255))
        w = fser.getlength(head)
        if epno:
            dr.text((x + w + 26, y + 10), f"제{epno}화", font=fep, fill=col if shadow else (236, 206, 150, 255))
        dr.line([x, y + 76, x + 250, y + 76], fill=col if shadow else (226, 190, 120, 255), width=3)
        for i, ln in enumerate(hook_lines):
            yy = y + 118 + i * int(hook_size * 1.15)
            if shadow:
                dr.text((x, yy), ln, font=fhook, fill=col, stroke_width=10, stroke_fill=col)
            else:
                dr.text((x, yy), ln, font=fhook, fill=(255, 255, 255, 255), stroke_width=3, stroke_fill=(20, 14, 10, 230))
        if menu and not shadow:
            fm, lines, fs = _fit_lines(f"「{menu}」", SERIF_XB, 64, CW - 160, max_lines=2, min_size=40)
            lh = int(fs * 1.34)
            yb = 1560 - len(lines) * lh                   # 3:4 안전 영역(아래 1680px) 안쪽
            lab = "오 늘 의   메 뉴"
            dr.text(((CW - fep.getlength(lab)) / 2, yb - 62), lab, font=fep, fill=(236, 206, 150, 255))
            for i, ln in enumerate(lines):
                dr.text(((CW - fm.getlength(ln)) / 2, yb + i * lh), ln, font=fm, fill=(255, 246, 232, 255),
                        stroke_width=2, stroke_fill=(20, 14, 10, 200))
            sf = _f(SERIF_XB, int(58 * 0.56))
            sw = sf.getlength("품격") + 58 * 0.7
            _seal(dr, (CW + sw) / 2, yb + len(lines) * lh + 18, 58, "품격")
    layer = _shadowed((CW, CH), draw, blur=10, alpha=160, offset=(0, 5))
    img.alpha_composite(layer)
    img.convert("RGB").save(out, "JPEG", quality=92)
    return out


def receipt_png(ep, food: Path | None, out: Path):
    """영수증 엔딩 — 음식 사진(그릇에 담긴 알맹이, 포장 없음) + 맛 평가 + 메뉴·가격·추천 손님 + 프로필 링크."""
    from PIL import ImageFilter, ImageOps
    bg = Image.new("RGB", (W, H), (30, 24, 20))
    if food and food.exists():                       # 배경: 음식 사진을 흐리게 깔아 따뜻한 분위기
        b = ImageOps.fit(Image.open(food).convert("RGB"), (W, H)).filter(ImageFilter.GaussianBlur(28))
        bg = Image.blend(bg, b, 0.45)
    im = bg.convert("RGBA")
    pw, x0, y0 = 560, (W - 560) // 2, 96
    notes = [n for n in (ep.get("tasteNotes") or []) if n.get("k") and n.get("v")][:4]
    ph = 1060
    paper = Image.new("RGBA", (pw, ph + 16), (0, 0, 0, 0))
    dr = ImageDraw.Draw(paper)
    dr.rectangle([0, 0, pw, ph], fill=(250, 247, 238, 255))
    for x in range(0, pw, 20):                       # 아래 톱니
        dr.polygon([(x, ph), (x + 10, ph + 14), (x + 20, ph)], fill=(250, 247, 238, 255))
    fs, fm, fl, fx = _f(SERIF_B, 26), _f(SERIF_B, 30), _f(SERIF_XB, 44), _f(SERIF_XB, 38)
    c = lambda t, f, y, col=INK: dr.text(((pw - f.getlength(t)) / 2, y), t, font=f, fill=col + (255,))
    dots = lambda y: [dr.ellipse([x, y, x + 3, y + 3], fill=(170, 160, 148, 255)) for x in range(36, pw - 36, 12)]
    c("영  수  증", fl, 34)
    c(f"{ep.get('series', '')}" + (f"  제{ep['episode']}화" if ep.get("episode") else ""), fs, 96, (130, 110, 90))
    dots(144)
    y, seal_y = 166, 0
    if food and food.exists():                       # 오늘 먹은 한 그릇(포장 없는 음식 사진)
        ph_img = ImageOps.fit(Image.open(food).convert("RGB"), (pw - 120, 250))
        m = Image.new("L", ph_img.size, 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, *ph_img.size], radius=14, fill=255)
        paper.paste(ph_img, (60, y), m)
        seal_y = y + 250 - 60
        y += 270
    fx, mlines, fxs = _fit_lines(ep.get("menuName", ""), SERIF_XB, 38, pw - 80)
    for ln in mlines:
        c(ln, fx, y)
        y += int(fxs * 1.3)
    y += 14
    dots(y)
    y += 22
    for n in notes:                                  # 식감 ········ 쫀득 부드러움
        k, v = n["k"], n["v"]
        if k == "한줄평":
            continue
        dr.text((48, y), k, font=fm, fill=(110, 90, 70, 255))
        vw = fm.getlength(v)
        dr.text((pw - 48 - vw, y), v, font=fm, fill=INK + (255,))
        kw = fm.getlength(k)
        for x in range(int(48 + kw + 14), int(pw - 48 - vw - 10), 10):
            dr.ellipse([x, y + 20, x + 2, y + 22], fill=(190, 180, 168, 255))
        y += 48
    one = next((n["v"] for n in notes if n["k"] == "한줄평"), "") or ep.get("verdict", "")
    if one:
        y += 6
        for ln in _balanced(f"“{one}”", fm, pw - 90)[:2]:
            c(ln, fm, y, (80, 60, 44))
            y += 42
    # 영수증에 가격은 넣지 않는다(사용자 지시 2026-09: 가격은 무조건 뺀다)
    if ep.get("guestNote"):
        c(ep["guestNote"], fs, y + 4, (120, 104, 88))
        y += 40
    dots(ph - 190)
    c("이 메뉴는", fl, ph - 160)
    c("프로필 링크에서", fl, ph - 100)
    if seal_y:                                       # 붉은 '완식' 낙관 — 음식 사진 오른쪽 아래 모서리에 찍는다
        _seal(ImageDraw.Draw(paper), pw - 66, seal_y + 14, 52, "완식")
    paper = paper.rotate(-1.5, resample=Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", paper.size, (0, 0, 0, 0))
    sh.putalpha(paper.split()[3].point(lambda v: v * 150 // 255).filter(ImageFilter.GaussianBlur(16)))
    im.alpha_composite(sh, (x0 - 6, y0 + 14))
    im.alpha_composite(paper, (x0 - 10, y0))
    im.convert("RGB").save(out, quality=95)


# 컷 사이 전환(다음 컷의 역할별). 너무 요란하지 않게 드라마식으로. dissolve는 모래알 노이즈가 생겨 쓰지 않는다.
TRANSITIONS = {"order": "fadeblack", "serve": "smoothleft", "taste": "fade", "bill": "smoothup",
               "exit": "fadeblack", "outro": "fade"}
XF = 0.4
LEAD = 0.45              # 컷 시작 후 대사가 시작되기까지(초)
TAIL = 0.75              # 대사가 끝난 뒤 다음 컷까지 여유(초)
MIN_SEG = 5.0            # 대사가 짧아도 컷은 이 길이 이상


ZOOM_OPEN, ZOOM_PULL = 1.22, 1.6   # 입장: 가까이(1.22배)에서 "심각하다"와 함께 1.6초 동안 부드럽게 빠진다


def _zoom_expr(role, idx, L, tz=None):
    """컷 안의 카메라 느낌(편집). ⛔ 화면 크기를 한 번에 툭 바꾸는 계단식 줌 금지(사용자 지적 2026-09: 뚝뚝 끊겨 보임) —
    모든 줌은 연속으로 부드럽게 변한다. 입장은 "심각하다"(tz초)에 맞춰 천천히 멈추듯 빠지는 줌(ease-out) 한 번."""
    if role == "enter":
        tz = max(0.4, tz if tz is not None else 1.2)
        p = f"min(1,max(0,(it-{tz:.2f})/{ZOOM_PULL}))"
        return f"{ZOOM_OPEN}-{ZOOM_OPEN - 1:.2f}*pow({p},2)*(3-2*{p})"
    if idx % 2:                                       # 편집 줌은 아주 약하게(구도 변화는 컷 설계가 맡는다)
        return f"1.04-0.04*it/{L:.2f}"
    return f"1+0.04*it/{L:.2f}"


def _check_smooth(expr: str, L: float, fps: int = FPS, max_step: float = 0.02):
    """⛔ 재발 방지: 줌이 한 프레임에 max_step(2%) 넘게 변하면(=계단식 점프) 조립을 멈춘다."""
    prev = None
    for k in range(int(L * fps) + 1):
        z = eval(expr, {"min": min, "max": max, "pow": pow, "it": k / fps})   # noqa: S307 — 우리가 만든 수식만 평가
        if prev is not None and abs(z - prev) > max_step:
            raise RuntimeError(f"줌이 {k / fps:.2f}초에 {prev:.3f}→{z:.3f}로 튐(계단식 줌 금지 규칙)")
        prev = z


def _overlay_input(png: Path, L: float, a: float, b: float, fade=0.25):
    return (["-loop", "1", "-t", f"{L:.2f}", "-i", str(png)],
            f"format=rgba,fade=in:st={max(0, a):.2f}:d={fade}:alpha=1,fade=out:st={max(0, b - fade):.2f}:d={fade}:alpha=1")


# ⭐ 맨 앞 후킹 구간(사용자 확정 2026-09, 핵심 규칙): 본편 중 가장 후킹이 될 장면(기본: 첫 시식 컷의 첫 느낌 문장)을
#   원본 그대로(목소리·자막 포함) 2~3.5초 떼어 맨 앞에 먼저 틀고, 화면 중간보다 조금 위에 후킹 문구(hookLine)를 크게 얹는다.
#   이어서 입장("배가 고프다. 심각하다.")부터 본편이 원래대로 흐른다. 본편 안에서는 멈춤·큰 문구 없음(일반 자막만).
#   정지 표지를 앞에 붙이거나 본편을 멈추는 방식은 폐기. 인스타 커버는 이 후킹 구간의 한 장면(문구 포함)을 쓴다.
HOOK_MIN, HOOK_MAX = 2.0, 4.5


def hook_png(text, out: Path):
    """첫 한입 멈춤 문구 — 화면 가운데 굵은 흰 글씨 두 줄까지(외곽선+그림자). 상품명·효능은 대본 단계에서 이미 걸렀다."""
    f, lines, fs = _fit_2or3(text, SUB_FONT, 86, W - 110, 58, 54)
    lh = int(fs * 1.28)
    y0 = int(H * 0.33) - lh * len(lines) // 2          # 화면 중간보다 조금 위(사용자 확정)

    def draw(dr, shadow):
        for i, ln in enumerate(lines):
            x = (W - f.getlength(ln)) / 2
            if shadow:
                dr.text((x, y0 + i * lh), ln, font=f, fill=(0, 0, 0, 255), stroke_width=10, stroke_fill=(0, 0, 0, 255))
            else:
                dr.text((x, y0 + i * lh), ln, font=f, fill=(255, 255, 255, 255), stroke_width=4, stroke_fill=(20, 14, 10, 240))
        if not shadow:                                   # 문구 위아래 가는 금색 선 두 줄(드라마 자막 느낌)
            dr.line([W * 0.3, y0 - 26, W * 0.7, y0 - 26], fill=(226, 190, 120, 230), width=2)
            dr.line([W * 0.3, y0 + len(lines) * lh + 18, W * 0.7, y0 + len(lines) * lh + 18], fill=(226, 190, 120, 230), width=2)
    _shadowed((W, H), draw, blur=10, alpha=170, offset=(0, 5)).save(out)


def hook_intro(ep, segs, roles, info, tmp, work):
    """후킹 구간 세그먼트를 만든다. (경로, 길이, 정보) 또는 None."""
    text = str(ep.get("hookLine") or "").strip()
    if not text:
        return None
    want = str(ep.get("hookRole") or "taste")
    k = next((i for i, r in enumerate(roles) if r == want), next((i for i, r in enumerate(roles) if r == "taste"), -1))
    if k < 0:
        return None
    src, sents = segs[k], info[k].get("sents") or []
    L = _dur(src)
    j = 1 if len(sents) > 1 and (ep["clips"][k].get("line") or "").startswith("잘 먹겠습니다") else 0
    if sents:
        ws = max(0.0, sents[j][0] - 0.25)
        we = min(L, max(sents[j][1] + 0.35, ws + HOOK_MIN))
    else:
        ws, we = 0.0, min(L, 3.0)
    we = min(we, ws + HOOK_MAX)
    hp, out = tmp / "hook_text.png", tmp / "seg_hook.mp4"
    hook_png(text, hp)
    HL = we - ws
    _ff(["-ss", f"{ws:.3f}", "-t", f"{HL:.3f}", "-i", str(src), "-loop", "1", "-t", f"{HL:.3f}", "-i", str(hp),
         "-filter_complex", f"[1:v]format=rgba,fade=t=in:st=0:d=0.15:alpha=1[t];[0:v][t]overlay=0:0:shortest=1,"
         f"fps={FPS},setsar=1,format=yuv420p[v];[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(out)])
    # 인스타 커버 = 후킹 구간의 한 장면(문구 포함) — 따로 만들지 않는다(사용자 확정 2026-09)
    _ff(["-ss", f"{min(HL * 0.6, HL - 0.1):.3f}", "-i", str(out), "-frames:v", "1", "-vf", "scale=1080:1920:flags=lanczos",
         "-q:v", "2", str(work / "cover.jpg")])
    return out, HL, {"from": ep["clips"][k].get("role"), "clip": info[k].get("clip"), "start": round(ws, 2),
                     "len": round(HL, 2), "text": text}


def build_segment(ep, c, idx, work, tmp):
    name = f"c{c['no']:02d}"
    src = work / f"{name}.mp4"
    role = c.get("role")
    V = min(8.0, _dur(src)) or 8.0
    voice = work / f"v_{name}.wav"
    tjp = work / f"v_{name}.json"
    timing = json.loads(tjp.read_text(encoding="utf-8")) if tjp.exists() else []
    N = _dur(voice) if voice.exists() else 0.0
    # 컷 길이는 대사에 맞춘다: 대사가 길면 목소리를 빠르게 하지 않고 영상을 조금 늘리거나 마지막 장면을 잠시 멈춘다.
    # 영상 AI는 컷 끝(7~8초)으로 갈수록 흐트러진다(시식 중 사라짐·퇴장 중 되돌아옴 — 3차 실측) → 8초를 다 쓰지 않고
    # 대사 길이만큼만 쓴다(최소 MIN_SEG초). 템포도 빨라진다.
    L = max(MIN_SEG, LEAD + N + TAIL)
    slow = min(1.3, max(1.0, L / V))                            # 짧으면 자르기만(빨리 감지 않음), 길면 최대 1.3배 늘림
    a0 = LEAD                                                    # 입장도 오프닝으로 바로 시작(사용자 확정 2026-09)
    ins, fcs, labels = [], [], []
    ins += ["-i", str(src)]
    tz = a0 + timing[1]["start"] if role == "enter" and len(timing) > 1 else None   # "심각하다" 시작 시각
    z = _zoom_expr(role, idx, L, tz)
    _check_smooth(z, L)
    fcs.append(f"[0:v]setpts={slow:.4f}*PTS,scale=1440:2560:force_original_aspect_ratio=increase,crop=1440:2560,"
               f"tpad=stop_mode=clone:stop_duration=3,trim=0:{L:.2f},setpts=PTS-STARTPTS,fps={FPS},"
               f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},setsar=1[v0]")
    ov = []                                                     # (png, from, to, fade)
    for k, t in enumerate(timing):                              # 자막: 실제로 말하는 시간에 딱 맞춰
        p = tmp / f"sub_{name}_{k}.png"
        subtitle_png(t["text"], p)
        ov.append((p, a0 + t["start"] - 0.05, a0 + t["end"] + 0.18, 0.12))
    card = c.get("card") or {}
    if card.get("type") == "menu" and card.get("name"):
        p = tmp / f"menu_{name}.png"
        menu_png(card["name"], p)
        ov.append((p, 0.5, L - 0.2, 0.35))
    elif False and card.get("type") == "bill":        # 가격 계산서 카드 폐지(사용자 지시 2026-09: 가격은 무조건 뺀다)
        p = tmp / f"bill_{name}.png"
        bill_png(card["text"], p)
        ov.append((p, 0.5, L - 0.2, 0.35))
    if role == "enter":
        p = tmp / "title.png"
        title_png(ep.get("series", ""), ep.get("episode"), p)
        ov.append((p, 0.3, min(L - 1.4, 3.8), 0.5))
    last = "v0"
    for i, (p, a, b, fd) in enumerate(ov, start=1):
        args, flt = _overlay_input(p, L, a, b, fd)
        ins += args
        fcs.append(f"[{i}:v]{flt}[o{i}]")
        fcs.append(f"[{last}][o{i}]overlay=0:0[v{i}]")
        last = f"v{i}"
    n = len(ov) + 1
    if voice.exists():
        ins += ["-i", str(voice)]
        ms = int(a0 * 1000)
        fcs.append(f"[{n}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={ms}|{ms},apad,atrim=0:{L:.2f},"
                   f"loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    else:
        ins += ["-f", "lavfi", "-t", f"{L:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
        fcs.append(f"[{n}:a]atrim=0:{L:.2f}[a]")
    seg = tmp / f"seg_{name}.mp4"
    _ff([*ins, "-filter_complex", ";".join(fcs), "-map", f"[{last}]", "-map", "[a]", "-t", f"{L:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(seg)])
    meta = {"clip": name, "len": round(L, 2), "voice": round(N, 2), "slow": round(slow, 3)}
    meta["sents"] = [[round(a0 + t["start"], 2), round(a0 + t["end"], 2)] for t in timing]   # 맨 앞 후킹 구간 고를 때 쓴다
    return seg, L, meta


def step_assemble(ep, epdir, work, log):
    tmp = work / "tmp"
    tmp.mkdir(exist_ok=True)
    food = next((p for p in (epdir / "refs" / "food.jpg", epdir / "refs" / "food.png") if p.exists()), None)
    segs, lens, roles, info = [], [], [], []
    for idx, c in enumerate(ep["clips"]):
        seg, L, meta = build_segment(ep, c, idx, work, tmp)
        segs.append(seg); lens.append(L); roles.append(c.get("role")); info.append(meta)
    hook = hook_intro(ep, segs, roles, info, tmp, work)       # 맨 앞 후킹 구간(본편 장면 + 큰 문구)
    if hook:
        segs.insert(0, hook[0]); lens.insert(0, hook[1]); roles.insert(0, "hook")
    else:
        step_cover(ep, work, log)                             # 후킹 문구가 없을 때만 예전 방식 표지
    # 영수증 엔딩 3초(천천히 다가가는 줌)
    rp = tmp / "receipt.jpg"
    receipt_png(ep, food, rp)
    outro, OL = tmp / "seg_outro.mp4", 3.2
    _ff(["-loop", "1", "-t", f"{OL}", "-i", str(rp), "-f", "lavfi", "-t", f"{OL}", "-i", "anullsrc=r=44100:cl=stereo",
         "-filter_complex", f"[0:v]scale=1440:2560,zoompan=z='1+0.04*it/{OL}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
         f"d=1:s={W}x{H}:fps={FPS},setsar=1,format=yuv420p[v]", "-map", "[v]", "-map", "1:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
         "-t", f"{OL}", str(outro)])
    segs.append(outro); lens.append(OL); roles.append("outro")
    # 컷 사이 전환(xfade)으로 한 편에 잇는다
    ins = []
    for s in segs:
        ins += ["-i", str(s)]
    fc, vlast, alast, t = [], "0:v", "0:a", lens[0]
    for i in range(1, len(segs)):
        tr = TRANSITIONS.get(roles[i], "fade")
        off = t - XF
        fc.append(f"[{vlast}][{i}:v]xfade=transition={tr}:duration={XF}:offset={off:.3f}[vx{i}]")
        fc.append(f"[{alast}][{i}:a]acrossfade=d={XF}[ax{i}]")
        vlast, alast = f"vx{i}", f"ax{i}"
        t = off + lens[i]
    final = work / "final.mp4"
    _ff([*ins, "-filter_complex", ";".join(fc), "-map", f"[{vlast}]", "-map", f"[{alast}]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)])
    # 배경음악은 영상에 넣지 않는다(사용자 지시 2026-09: 음악이 섞이면 인스타 '릴스 번역'이 막힘 → 음악은 인스타 앱에서 따로 얹는다).
    # 예전처럼 섞으려면 요청에 "bgm_mix": true (ep["_bgm_mix"]).
    if SIGNATURE_BGM.exists() and ep.get("_bgm_mix"):     # 시그니처 배경음악: 작게 깔고, 목소리가 나오면 자동으로 더 줄인다
        T = _dur(final)
        mixed = work / "final_bgm.mp4"
        _ff(["-i", str(final), "-stream_loop", "-1", "-i", str(SIGNATURE_BGM), "-filter_complex",
             f"[0:a]asplit=2[v1][v2];[1:a]aresample=44100,atrim=0:{T:.2f},volume=0.22,"
             f"afade=t=in:d=1.5,afade=t=out:st={max(0, T - 2.5):.2f}:d=2.5[m];"
             f"[m][v1]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500[md];"
             f"[v2][md]amix=inputs=2:duration=first:normalize=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", str(mixed)])
        mixed.replace(final)
        log.setdefault("assemble", {})["bgm"] = SIGNATURE_BGM.name
    total = _dur(final)
    _ff(["-i", str(final), "-vf", f"fps={len(segs)}/{total:.2f},scale=180:-2,tile={len(segs)}x1:margin=4:padding=4:color=white",
         "-frames:v", "1", str(work / "frames.jpg")])
    log["assemble"] = {**log.get("assemble", {}), "ok": True, "sec": round(total, 2), "clips": len(segs) - 1,
                       "segments": info, "hook": hook[2] if hook else None}
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()


# ---------- 춤 밈 시험(사용자 요청 2026-10): 참고 춤 영상의 동작을 시바견(두 발 서기 허용 — 이 형식만 예외)에 옮긴다 ----------
# 요청: {"id": "000-dance-test", "steps": ["dance"], "dance": {"video_url": "<비공개 임시 주소>", "out_h": 640}}
# 참고 영상은 남의 영상이라 저장소에 올리지 않는다(임시 주소에서 받아 쓰고 버린다). 결과는 360p로 줄여 비용·용량을 아낀다.
DANCE_START = ("Reference image 1 is our character: a real Shiba Inu (keep exactly this face, fur colour and body proportions). "
               "Reference image 2 is only a composition reference from a dance video. Create one photorealistic vertical 9:16 frame: "
               "the Shiba Inu stands upright on its two hind legs on a raised wooden platform above a cheering crowd at a night outdoor "
               "courtyard party, full body visible from ears to feet, centred, same camera distance and angle as reference image 2. "
               "The dog wears the dancer's outfit in a LONG-SLEEVE version: a horizontal-striped collared shirt (white, navy and beige "
               "stripes) whose sleeves reach all the way down to the wrists, loose wide-leg light trousers, chunky white sneakers on its hind paws, "
               "and small dark sunglasses. No arm or leg skin is visible at all - only big fluffy orange-and-cream Shiba front paws "
               "stick out of the sleeve cuffs. Exactly two front legs coming out of the sleeves, spread wide to the sides like the dancer's starting pose; tail "
               "curled out over the waistband. Strings of warm bulb lights overhead, a strong red stage light from the front, an old "
               "building facade behind, the whole audience is dogs of many breeds (corgis, poodles, retrievers, huskies) cheering with open mouths and wagging tails; only dogs, no people, no phones, no hands of any kind. The human dancer from "
               "reference image 2 must NOT appear. No text, no logos, no watermark.")
DANCE_PROMPT = ("DURATION: 5 seconds. Image 1 is the first frame. The video is the motion reference: the Shiba Inu in image 1 performs "
                "the same dance as the dancer in the video, beat for beat and just as big and sharp - Tecktonik / electro dance: fast "
                "full arm sweeps, front legs whipping around its head and chest, wide arm spreads, quick paw flicks, knee bounces and "
                "small steps - standing upright on its two hind legs on the platform the whole time, full body in frame. Keep the dog's "
                "face, fur, size and outfit (striped polo, wide trousers, sunglasses) identical to image 1, keep the same party "
                "background, red light and cheering crowd; camera locked-off with a slight handheld feel. Photorealistic. Exactly two "
                "front legs. No human dancer, no text, no extra dogs, no morphing.")

DANCE_EDIT = ("Edit this video: replace the human dancer with the Shiba Inu from image 1 (same face, fur, LONG-SLEEVE striped shirt "
              "with sleeves down to the wrists, wide light trousers covering the feet and dark sunglasses as in image 1 - the "
              "dancer's bare forearms are fully covered by the long sleeves; only fluffy dog paws stick out of the cuffs). The dog must copy the dancer's movement EXACTLY, frame by frame: "
              "the same arm (front leg) positions, angles, heights, speed and timing, the same leg steps, knee bounces and body turns. "
              "Motion fidelity is the top priority - stretch or distort the dog's limbs if needed to match every pose. Also replace EVERY person "
              "in the crowd with real dogs of many different breeds (corgis, poodles, retrievers, dachshunds, pugs, huskies...), "
              "cheering and bouncing to the beat, some standing on their hind legs with front paws raised, a few holding up phones "
              "to film - no humans anywhere in the video. Keep the camera, framing, string lights, building, red stage light and "
              "timing exactly as in the video. Remove any watermark or text. Photorealistic dog, "
              "exactly two front legs. CRITICAL ANATOMY: the dancer's arms become the Shiba's own FRONT LEGS - covered in "
              "orange-and-cream Shiba fur all the way down, ending in round dog paws with toe pads and short claws; the legs stay thick and fully furry like a real Shiba's legs at every "
              "angle, never smooth, skin-coloured or hairless. NEVER human "
              "arms, hands, fingers, thumbs, nails or bare skin on the Shiba or on any dog, in any frame - when the dancer points "
              "or spreads fingers, the dog just extends a furry paw. No human body parts anywhere in the video: the "
              "original crowd's raised human arms and hands must disappear completely - the crowd dogs cheer with dog ears, wagging "
              "tails and bouncing, any raised limb is clearly a short furry dog leg with a paw. The dark foreground at the bottom of the frame "
              "is the front row of the audience: furry dog heads and pointed dog ears seen from behind. Any phone in the crowd is "
              "held between a dog's two furry paws. The Shiba wears chunky white sneakers on its hind "
              "paws, under long trouser hems that reach the sneakers.")
DANCE_STRICT = ("DURATION: 5 seconds. Image 1 is the first frame. The video is the motion reference. MOTION FIDELITY IS THE TOP PRIORITY: "
                "the Shiba Inu must copy the dancer's movement EXACTLY, frame by frame and beat for beat - the same arm (front leg) "
                "positions, angles, heights (raise them fully above the head when the dancer does), speed and timing, the same leg "
                "steps, knee bounces and body turns. Stretch or distort the dog's limbs if needed to hit every pose; do not tone the "
                "moves down. Keep the dog's face, fur and outfit (long-sleeve striped shirt, wide trousers, white sneakers, sunglasses) "
                "identical to image 1, the same all-dog cheering audience and party background, strong red stage light; camera "
                "locked-off. Front legs stay fully furry with paws. Photorealistic. Exactly two front "
                "legs. No human dancer, no text, no extra dogs.")
DANCE_TEXT = ("DURATION: 5 seconds. Image 1 is the first frame. The Shiba Inu does a fast Tecktonik / electro dance to a 132 BPM "
              "club beat while standing upright on its two hind legs behind the DJ booth (the booth always hides everything below "
              "the waist): [0-1s] both front legs held wide open to the sides, bouncing to the beat; [1-2s] both front legs swing "
              "up over the head and clap twice; [2-3s] one front leg whips across in front of its face, then the other; [3-4s] quick "
              "paw flicks circling around the head and chest; [4-5s] a big diagonal sweep of one front leg out to the side with a "
              "proud head tilt. Sharp, snappy, on every beat. Same face, fur and size as image 1, same party background, red light "
              "and cheering crowd filming with phones; camera locked-off with a slight handheld feel. Photorealistic. Exactly two "
              "front legs. No human dancer, no text, no extra dogs, no morphing.")


def _omni_run(key, body) -> bytes:
    hdr = {"x-goog-api-key": key, "Content-Type": "application/json"}
    t0 = time.time()
    st, raw = _http(f"{API}/interactions", json.dumps(body).encode(), hdr, timeout=900)
    if st != 200:
        raise RuntimeError(f"Omni HTTP {st}: {raw[:400].decode('utf-8', 'replace')}")
    j = json.loads(raw)
    while not _find_video(j) and j.get("id") and str(j.get("status", "")).lower() in ("in_progress", "pending", "running", "queued"):
        if time.time() - t0 > 900:
            raise TimeoutError("Omni 15분 초과")
        time.sleep(10)
        st, raw = _http(f"{API}/interactions/{j['id']}", None, hdr)
        j = json.loads(raw) if st == 200 else j
    v = _find_video(j)
    if not v:
        raise RuntimeError(f"Omni 영상 없음: {json.dumps(j)[:300]}")
    if v.get("data"):
        return base64.b64decode(v["data"])
    fid = str(v["uri"]).rstrip("/").split("/")[-1]
    for _ in range(90):
        st, raw = _http(f"{API}/files/{fid}", None, hdr)
        if st == 200 and json.loads(raw).get("state") == "ACTIVE":
            break
        time.sleep(5)
    st, vid = _http(f"{API}/files/{fid}:download?alt=media", None, hdr)
    if st != 200:
        raise RuntimeError(f"Omni 다운로드 실패 HTTP {st}")
    return vid


HUMAN_CHECK = ("These are frames from an AI video where every character must be a dog. Look very carefully at every paw, leg "
               "and hand-like shape (especially the dancing Shiba's front legs and feet) and the whole background crowd. Is there ANY human body part - human hand, "
               "fingers, thumb, fingernails, bare human feet or toes, the back of a human head or human hair, bare human skin, human arm, or a smooth hairless skin-coloured arm that looks human rather than a furry dog leg - in ANY frame? "
               'JSON only: {"human": true, "where": "short English description of which frame/where, empty if none"}')


def _human_parts(video: Path, work: Path) -> dict:
    """완성 영상에 사람 손·손가락·맨발·뒤통수가 섞였는지 AI가 검사한다(사용자 지적 2026-10).
    전체 화면만 보면 가장자리·맨 앞줄을 놓친다(실측) → 전체 10장 + 아래쪽 절반 확대 + 가운데 인물 확대를 따로 본다."""
    d = max(1.0, _dur(video))
    views = {"full": f"fps={10 / d:.3f},scale=400:-2,tile=5x2",
             "bottom": f"fps={6 / d:.3f},crop=iw:ih*0.5:0:ih*0.5,scale=480:-2,tile=3x2",
             "center": f"fps={6 / d:.3f},crop=iw*0.6:ih*0.7:iw*0.2:ih*0.15,scale=360:-2,tile=3x2"}
    found = []
    for name, vf in views.items():
        sheet = work / f"_check_{name}.jpg"
        _ff(["-i", str(video), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(sheet)])
        r = _vision_json(sheet, HUMAN_CHECK)
        sheet.unlink(missing_ok=True)
        if not r:
            return {"human": None, "where": f"검사 실패({name})"}
        if r.get("human"):
            found.append(f"{name}: {r.get('where', '')}")
    return {"human": bool(found), "where": " / ".join(found)}


def step_dance(work, log, cfg):
    res = log.setdefault("dance", {})
    key = _key("GEMINI_API_KEY")
    ref = work / "_ref.mp4"
    st, raw = _http(cfg["video_url"], None, {}, timeout=120)
    if st != 200 or len(raw) < 10000:
        raise RuntimeError(f"참고 춤 영상을 못 받았습니다(HTTP {st})")
    ref.write_bytes(raw)
    if cfg.get("crop"):                                     # 춤추는 사람만 남기고 관객 얼굴을 줄인다(안전 필터 대책)
        cropped = work / "_ref_crop.mp4"
        mb = float(cfg.get("mask_bottom", 0))                # 맨 앞줄 관객(뒤통수·휴대폰 든 손)을 어둡게 지워 편집이 사람을 남기지 않게
        vf = f"crop={cfg['crop']},scale=360:640" + (f",drawbox=x=0:y=ih*{1 - mb:.2f}:w=iw:h=ih*{mb:.2f}:color=black@0.92:t=fill" if mb else "")
        _ff(["-i", str(ref), "-an", "-vf", vf + ",format=yuv420p", "-c:v", "libx264", "-crf", "24", str(cropped)])
        cropped.replace(ref)
        raw = ref.read_bytes()
    first = work / "_ref_first.jpg"
    _ff(["-i", str(ref), "-frames:v", "1", str(first)])
    start = work / "dance_start.png"
    if not start.exists() or "start" in cfg.get("redo", []):
        res["start_check"] = []
        for attempt in range(3):                             # 첫 장면 그림도 사람 흔적 검사(불합격이면 그림만 다시 — 영상 비용 전에)
            r = gen_image(DANCE_START, [ROOT / "pet-episodes" / "characters" / "dog.png", first], start, "9:16")
            res["start"] = r
            if not r.get("ok"):
                raise RuntimeError(f"첫 장면 실패: {r.get('error')}")
            c = _vision_json(start, HUMAN_CHECK)
            res["start_check"].append(c)
            if c and c.get("human") is False:
                break
        else:
            raise RuntimeError(f"첫 장면에 사람 흔적(3회): {c.get('where', '') if c else '검사 실패'}")
    if cfg.get("only_start"):                                # 첫 장면만 먼저 확인(영상 비용 전에)
        res["ok"] = "start_only"
        return
    vid = {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(raw).decode()}
    img = {"type": "image", **_b64img(start)}
    txt = {"type": "text", "text": DANCE_PROMPT}
    tries = []
    plans = [("reference_to_video", [img, vid, txt])]
    if cfg.get("mode") == "strict":                          # 우리 첫 장면에서 출발해 동작만 따라 함(원본 사람 흔적이 남지 않음)
        plans = [("reference_to_video", [img, vid, {"type": "text", "text": DANCE_STRICT}])]
    if cfg.get("mode") == "edit":                            # 원본 영상을 편집해 댄서만 바꾼다 → 동작·박자 그대로(1순위), 막히면 강한 지시로
        plans = [("edit", [vid, img, {"type": "text", "text": DANCE_EDIT}])]
        if not cfg.get("edit_only"):
            plans.append(("reference_to_video", [img, vid, {"type": "text", "text": DANCE_STRICT}]))
    for task, inputs in plans:                               # Omni가 받는 task: text_to_video·image_to_video·reference_to_video·edit·extend
        res_ = "720p"
        rf = {"type": "video", "resolution": res_} if task == "edit" else {"type": "video", "resolution": res_, "aspect_ratio": "9:16"}
        body = {"model": CLIP_MODEL, "input": inputs, "response_format": rf,      # edit은 화면비를 정할 수 없다(원본 비율 유지)
                "generation_config": {"video_config": {"task": task}}}
        try:
            data = _omni_run(key, body)
            tries.append({"task": task, "res": res_, "ok": True})
            res["mode_used"] = task
            break
        except Exception as e:  # noqa: BLE001
            tries.append({"task": task, "res": res_, "error": str(e)[:300]})
            if "safety" in str(e) and cfg.get("text_fallback"):   # 실제 사람 영상 참고가 막히면 → 동작을 글로 설명해 1회만
                body = {"model": CLIP_MODEL, "input": [img, {"type": "text", "text": DANCE_TEXT}],
                        "response_format": {"type": "video", "resolution": "720p", "aspect_ratio": "9:16"},
                        "generation_config": {"video_config": {"task": "image_to_video"}}}
                try:
                    data = _omni_run(key, body)
                    tries.append({"task": "image_to_video(text)", "ok": True})
                    break
                except Exception as e2:  # noqa: BLE001
                    tries.append({"task": "image_to_video(text)", "error": str(e2)[:300]})
                    res["tries"] = tries
                    raise
            if task == "edit":                               # 편집이 안 되면 다음 방법으로(1회)
                continue
            if "HTTP 4" not in str(e) or "safety" in str(e):   # 생성 실패·안전 차단이면 더 돌리지 않는다 — 비용 보호
                res["tries"] = tries
                raise
    else:
        res["tries"] = tries
        raise RuntimeError("Omni가 춤 영상 참고 입력을 받지 않았습니다")
    res["tries"] = tries
    raw_out = work / "_dance_raw.mp4"
    raw_out.write_bytes(data)
    chk = _human_parts(raw_out, work)
    res["human_check"] = [chk]
    if chk.get("human") is not False and cfg.get("mode") == "strict":    # 사람 흔적이면 1회만 다시
        body = {"model": CLIP_MODEL, "input": [img, vid, {"type": "text", "text": DANCE_STRICT + " Double-check every frame: furry front legs with paws, white sneakers, only dogs in the audience."}],
                "response_format": {"type": "video", "resolution": "720p", "aspect_ratio": "9:16"},
                "generation_config": {"video_config": {"task": "reference_to_video"}}}
        data = _omni_run(key, body)
        raw_out.write_bytes(data)
        chk = _human_parts(raw_out, work)
        res["human_check"].append(chk)
    if chk.get("human") is not False and cfg.get("mode") == "edit":      # 사람 손이 섞였으면 그 자리를 짚어 1회만 다시
        fix = {"type": "text", "text": DANCE_EDIT + " Double-check every frame: the Shiba's front legs are furry with paws, "
                                                   "its feet are in white sneakers, and every audience member is a dog."}   # 검사 문구(사람 신체 낱말)를 그대로 넣으면 입력 차단됨
        body = {"model": CLIP_MODEL, "input": [vid, img, fix], "response_format": {"type": "video", "resolution": "720p"},
                "generation_config": {"video_config": {"task": "edit"}}}
        data = _omni_run(key, body)
        raw_out.write_bytes(data)
        chk = _human_parts(raw_out, work)
        res["human_check"].append(chk)
    if chk.get("human") is not False:
        raise RuntimeError(f"사람 손·맨살이 섞여 나와 결과를 버렸습니다: {chk.get('where', '')}")
    h = int(cfg.get("out_h", 640))
    _ff(["-i", str(raw_out), "-an", "-vf", f"scale=-2:{h},format=yuv420p", "-c:v", "libx264", "-crf", "24",
         "-movflags", "+faststart", str(work / "dance.mp4")])
    # 원본과 나란히 놓은 비교본은 남의 영상이 들어가므로 저장소에서 만들지 않는다(필요하면 로컬에서 만든다)
    for f in (ref, first, raw_out):
        f.unlink(missing_ok=True)
    res["ok"] = True
    res["sec"] = _dur(work / "dance.mp4")




def step_dance_full(work, log, cfg):
    """원본 춤 전체(약 20초)를 줄이지 않고 4구간으로 나눠 만든다(사용자 확정 2026-10: 노래 박자·시간 준수).
    구간마다 원본의 같은 시간대를 동작 참고로 주고, 첫 장면은 앞 구간의 마지막 장면(첫 구간은 dance_start.png).
    결과는 구간마다 원본과 똑같은 길이로 맞춰 이어 붙인다 → 원본 노래와 박자가 맞는다. 주인공만 신경 쓰고 배경 변화는 허용."""
    res = log.setdefault("dance_full", {})
    key = _key("GEMINI_API_KEY")
    H = int(cfg.get("out_h", 1280))
    ref = work / "_ref_full.mp4"
    st, raw = _http(cfg["video_url"], None, {}, timeout=180)
    if st != 200 or len(raw) < 10000:
        raise RuntimeError(f"참고 춤 영상을 못 받았습니다(HTTP {st})")
    ref.write_bytes(raw)
    L = _dur(ref)
    n = int(cfg.get("segments", 4))
    seg = L / n
    res.update({"ref_sec": L, "segments": n, "seg_sec": round(seg, 3), "parts": res.get("parts", {})})
    start = work / "dance_start.png"
    mb = float(cfg.get("mask_bottom", 0.2))
    outs = []
    for i in range(n):
        out = work / f"dance_seg{i + 1}.mp4"
        outs.append(out)
        if out.exists() and f"seg{i + 1}" not in cfg.get("redo", []) and "all" not in cfg.get("redo", []):
            continue
        piece = work / f"_ref_seg{i + 1}.mp4"
        vf = f"crop={cfg.get('crop', '300:533:30:80')},scale=360:640" + (f",drawbox=x=0:y=ih*{1 - mb:.2f}:w=iw:h=ih*{mb:.2f}:color=black@0.92:t=fill" if mb else "")
        _ff(["-ss", f"{i * seg:.3f}", "-t", f"{seg:.3f}", "-i", str(ref), "-an", "-vf", vf + ",format=yuv420p",
             "-c:v", "libx264", "-crf", "22", str(piece)])
        first = start if i == 0 else work / f"_seg{i}_last.png"
        if i > 0:
            _ff(["-sseof", "-0.05", "-i", str(outs[i - 1]), "-frames:v", "1", str(first)])
        prompt = DANCE_STRICT.replace("DURATION: 5 seconds.", f"DURATION: {seg:.1f} seconds.")
        if i > 0:
            prompt += " Image 1 is where the previous part ended: continue from exactly this pose and look."
        vid = {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(piece.read_bytes()).decode()}
        part = {"checks": []}
        rawo = work / f"_seg{i + 1}_raw.mp4"
        for attempt in range(2):
            extra = "" if attempt == 0 else " Double-check every frame: furry front legs with paws, white sneakers, only dogs in the audience."
            body = {"model": CLIP_MODEL, "input": [{"type": "image", **_b64img(first)}, vid, {"type": "text", "text": prompt + extra}],
                    "response_format": {"type": "video", "resolution": "720p", "aspect_ratio": "9:16"},
                    "generation_config": {"video_config": {"task": "reference_to_video"}}}
            rawo.write_bytes(_omni_run(key, body))
            chk = _human_parts(rawo, work)
            part["checks"].append(chk)
            if chk.get("human") is False:
                break
        else:
            res["parts"][f"seg{i + 1}"] = part
            raise RuntimeError(f"{i + 1}구간에 사람 흔적(2회): {chk.get('where', '')}")
        got = _dur(rawo)
        part["gen_sec"] = got
        k = seg / got if got else 1.0                         # 원본과 똑같은 길이로(노래 박자 유지)
        _ff(["-i", str(rawo), "-an", "-vf", f"setpts=PTS*{k:.5f},scale=-2:{H},fps=24,setsar=1,format=yuv420p",
             "-t", f"{seg:.3f}", "-c:v", "libx264", "-crf", "20", str(out)])
        res["parts"][f"seg{i + 1}"] = part
        for f in (piece, rawo):
            f.unlink(missing_ok=True)
    ins = []
    for o in outs:
        ins += ["-i", str(o)]
    fc = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]"
    _ff([*ins, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(work / "dance.mp4")])
    res["ok"] = True
    res["sec"] = _dur(work / "dance.mp4")



# ---------- 춤 밈 광고 내레이션(사용자 요청 2026-10: 느끼하고 부담스럽게) ----------
VO_DIRECTION = ("[연기 지시] 한국어 광고 내레이션. 부담스러울 만큼 느끼하고 끈적한 목소리로 읽는다 — 심야 라디오 DJ가 "
                "마이크에 바짝 붙어 속삭이듯, 숨을 길게 섞고, 단어 끝을 늘이며, 자기 목소리에 취한 듯 느릿하고 달콤하게. "
                "'...'에서는 뜸을 들이고, '후우~'는 진짜 한숨처럼. 과장해도 좋다.")
# 리메이크 내레이션은 짧고 빠르게(사용자 지적 2026-10 헬기 편: 어설프고 너무 길다) — 뜸은 짧게, 1.45배
VO_PACE = "단, 뜸은 아주 짧게 하고 전체를 빠르고 리듬감 있게 읽는다. 마지막 '구매는 프로필 링크에서'는 또박또박 빠르게."
REMAKE_VO_SPEED = 1.3   # 1.45는 발음이 뭉개짐(사용자 지적 2026-10) → 1.3
VO_TEXT = ("당신의 강아지도오... 갈증을... 느낍니다. 후우~ 신나게 춤춘 뒤엔... 강아지 전용, 이온음료... 한 모금. "
           "구매는요... 프로필 링크에서.")


def step_vo(work, log, cfg):
    res = log.setdefault("vo", {})
    key = _key("GEMINI_API_KEY")
    model = _pick_model(key, TTS_MODELS)
    for voice in cfg.get("voices", ["Enceladus", "Algieba"]):
        out = work / f"vo_{voice}.wav"
        body = {"contents": [{"role": "user", "parts": [{"text": f"{VO_DIRECTION}\n\n대사: {cfg.get('text', VO_TEXT)}"}]}],
                "generationConfig": {"responseModalities": ["AUDIO"],
                                     "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
        code, raw = _http(f"{API}/models/{model}:generateContent", json.dumps(body).encode(),
                          {"x-goog-api-key": key, "Content-Type": "application/json"})
        parts = [p for c in json.loads(raw).get("candidates", []) for p in c.get("content", {}).get("parts", [])
                 if "inlineData" in p] if code == 200 else []
        if not parts:
            res[voice] = {"ok": False, "error": f"HTTP {code}: {raw[:200].decode('utf-8', 'replace')}"}
            continue
        _pcm_to_wav(base64.b64decode(parts[0]["inlineData"]["data"]), out, float(cfg.get("speed", 1.0)))
        res[voice] = {"ok": True, "sec": round(_dur(out), 2)}

# ---------- 원본 춤 영상에서 머리·손·발·관객만 바꾸기(사용자 지시 2026-10: 다른 건 아무것도 바꾸지 말 것, 360p, 1회) ----------
SWAP_PROMPT = ("Edit this video. Change ONLY these things and keep absolutely everything else exactly as it is (the dancer's body, "
               "clothes, every movement, timing, camera, background, lights): 1) replace the dancer's head with the head of the "
               "Shiba Inu from image 1 (keep the sunglasses); 2) replace the dancer's two hands with furry Shiba front paws; "
               "3) replace the dancer's two feet with furry Shiba hind paws; 4) replace every person in the audience with a real dog "
               "of various breeds. Remove the watermark text.")


def step_swap(work, log, cfg):
    """편집은 한 번에 10초까지(Omni 제한) → 원본을 같은 길이 구간으로 나눠 같은 지시로 바꾸고 그대로 이어 붙인다(시간·박자 원본 그대로)."""
    import math
    res = log.setdefault("swap", {})
    key = _key("GEMINI_API_KEY")
    ref = work / "_ref_full.mp4"
    st, raw = _http(cfg["video_url"], None, {}, timeout=180)
    if st != 200 or len(raw) < 10000:
        raise RuntimeError(f"원본 춤 영상을 못 받았습니다(HTTP {st})")
    ref.write_bytes(raw)
    L = _dur(ref)
    n = max(1, math.ceil(L / 9.5))
    seg = L / n
    img = {"type": "image", **_b64img(ROOT / "pet-episodes" / "characters" / "dog.png")}
    h = int(cfg.get("out_h", 640))
    outs = []
    for i in range(n):
        out = work / f"swap_seg{i + 1}.mp4"
        outs.append(out)
        if out.exists():                                     # 이미 만든 구간은 다시 만들지 않는다(비용)
            continue
        piece = work / f"_ref_seg{i + 1}.mp4"
        _ff(["-ss", f"{i * seg:.3f}", "-t", f"{seg:.3f}", "-i", str(ref), "-an", "-c:v", "libx264", "-crf", "20", str(piece)])
        vid = {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(piece.read_bytes()).decode()}
        body = {"model": CLIP_MODEL, "input": [vid, img, {"type": "text", "text": SWAP_PROMPT}],
                "response_format": {"type": "video", "resolution": "720p"},
                "generation_config": {"video_config": {"task": "edit"}}}
        rawo = work / f"_swap_raw{i + 1}.mp4"
        rawo.write_bytes(_omni_run(key, body))               # 구간마다 1회만(재시도 없음 — 사용자 지시)
        got = _dur(rawo)
        k = seg / got if got else 1.0                         # 원본 구간과 같은 길이로(박자 유지)
        _ff(["-i", str(rawo), "-an", "-vf", f"setpts=PTS*{k:.5f},scale=-2:{h},fps=24,setsar=1,format=yuv420p",
             "-t", f"{seg:.3f}", "-c:v", "libx264", "-crf", "23", str(out)])
        res[f"seg{i + 1}"] = {"gen_sec": got}
    ins = []
    for o in outs:
        ins += ["-i", str(o)]
    fc = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]"
    _ff([*ins, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-crf", "23", "-movflags", "+faststart", str(work / "swap.mp4")])
    res.update({"ok": True, "src_sec": L, "segments": n, "sec": _dur(work / "swap.mp4")})

# ---------- 춤 밈 끝 장면: 무대에서 내려와 펫 이온음료를 음미(사용자 확정 2026-10) ----------
# 병은 AI가 그리지 않는다(글자가 뭉개짐) → 쿠팡 실제 상품 사진에서 병 하나를 잘라 장면에 붙이고 병 전체를 흐림 처리한다.
BRIDGE_PROMPT = ("DURATION: 3 seconds. Image 1 is the first frame (the end of the dance) - continue seamlessly in the same night scene, same lighting, same dog crowd: the "
                 "Shiba Inu in the long-sleeve striped shirt, wide trousers and sunglasses finishes its last dance move, hops down from the "
                 "platform and walks on its hind legs to a small round wooden bar table at the side of the yard, then stops in front "
                 "of it. While walking it keeps its front legs relaxed close to its chest. The dog's front legs stay thick, fully "
                 "furry orange-and-cream Shiba legs with round paws coming out of the long sleeve cuffs - never human arms, hands, "
                 "fingers or bare skin. "
                 "It wears chunky white sneakers on its hind paws under the trouser hems. "
                 "The crowd is only dogs, no raised human arms or hands anywhere in the background. Camera follows smoothly. "
                 "Photorealistic. No text, no humans.")
DRINK_START = ("Image 1 is the last frame of the previous shot (keep exactly this Shiba Inu, its outfit - long-sleeve striped shirt, "
               "wide light trousers, dark sunglasses - and this night courtyard party lighting: warm string lights, red stage glow, "
               "dogs of other breeds in the background). Image 2 is the real product bottle. Create one photorealistic vertical 9:16 "
               "frame: the Shiba stands on its hind legs at a small round wooden bar table at the side of the party, both furry "
               "front paws resting on the table edge, lowering its head to lap from a shallow clear glass bowl of clear drink on the "
               "table. The bottle from image 2 stands on the same table just behind and beside the bowl, naturally placed with a "
               "soft reflection, clearly out of focus because the camera focuses on the dog (shallow depth of field, creamy "
               "bokeh). Camera at table height, medium close shot, the dog's face sharp. Front legs are furry Shiba legs with paws - "
               "no human hands, fingers or skin anywhere. No readable text anywhere.")
DRINK_PROMPT = ("DURATION: 4 seconds. Image 1 is the first frame. The Shiba Inu laps the clear drink from the bowl on the bar table "
                "with relish, little splashes, eyes half closed savouring it, then lifts its head, licks its lips with a deeply "
                "satisfied look and gives a tiny happy shimmy. The bottle stays where it is, out of focus, never moving or changing. "
                "Same night lighting and dogs in the background; camera fixed with shallow depth of field on the dog. Photorealistic. "
                "Furry dog legs and paws only - no human hands, fingers or skin. No text.")
BOTTLE_BOX = ('Find the drink bottle in this image. JSON only: {"found": true, "x0": 0.0, "y0": 0.0, "x1": 0.0, "y1": 0.0} '
              "as fractions of image width/height (x0,y0 = top-left, x1,y1 = bottom-right), covering the whole bottle including the cap.")


def _vision_json(img: Path, prompt: str) -> dict:
    key = _key("GEMINI_API_KEY")
    body = {"contents": [{"role": "user", "parts": [{"inline_data": _b64img(img)}, {"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    for model in ("gemini-flash-latest", "gemini-pro-latest"):
        st, raw = _http(f"{API}/models/{model}:generateContent", json.dumps(body).encode(),
                        {"x-goog-api-key": key, "Content-Type": "application/json"})
        if st == 200:
            try:
                t = "".join(p.get("text", "") for p in json.loads(raw)["candidates"][0]["content"]["parts"])
                return json.loads(t[t.find("{"):t.rfind("}") + 1])
            except Exception:  # noqa: BLE001
                pass
    return {}


def _wh(p: Path) -> tuple[int, int]:
    """영상 가로·세로 픽셀(ffmpeg 출력에서 읽는다)."""
    r = subprocess.run([FFMPEG, "-i", str(p)], capture_output=True, text=True)
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", r.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (9, 16)


def _norm(src: Path, out: Path, h: int):
    _ff(["-i", str(src), "-an", "-vf", f"scale=-2:{h},fps=24,setsar=1,format=yuv420p", "-c:v", "libx264", "-crf", "24", str(out)])


def step_drink(work, log, cfg):
    """춤 → 무대에서 내려와 바 테이블로(연장) → 테이블에서 펫 이온음료를 음미. 병은 장면 안 테이블 위에 두고 아웃포커스 + 병 영역 추가 흐림."""
    res = log.setdefault("drink", {})
    key = _key("GEMINI_API_KEY")
    H = int(cfg.get("out_h", 640))
    dance = work / "dance.mp4"
    # 1) 연결: 춤 영상을 이어 늘려 내려와 테이블까지 걸어가게(같은 밤 장면)
    bridge = work / "bridge.mp4"
    if not bridge.exists() or "bridge" in cfg.get("redo", []):
        # 연장(extend)은 원본의 사람 팔 느낌까지 끌고 와서(2026-10 실측 2회 불합격) → 춤 마지막 장면을 첫 장면으로 새로 만든다
        first = work / "_dance_last.png"
        _ff(["-sseof", "-0.1", "-i", str(dance), "-frames:v", "1", str(first)])
        tail = work / "_bridge_raw.mp4"
        res["bridge_check"] = []
        fix = ""
        for attempt in range(2):
            body = {"model": CLIP_MODEL,
                    "input": [{"type": "image", **_b64img(first)}, {"type": "text", "text": BRIDGE_PROMPT + fix}],
                    "response_format": {"type": "video", "resolution": "720p", "aspect_ratio": "9:16"},
                    "generation_config": {"video_config": {"task": "image_to_video"}}}
            tail.write_bytes(_omni_run(key, body))
            chk = _human_parts(tail, work)
            res["bridge_check"].append(chk)
            if chk.get("human") is False:
                break
            fix = " Double-check every frame: furry Shiba front legs with paws, white sneakers on the hind paws, and only dogs in the background."
        else:
            raise RuntimeError(f"연결 장면에 사람 손·맨살(2회): {chk.get('where', '')}")
        _norm(tail, bridge, H)
        for f in (first, tail):
            f.unlink(missing_ok=True)
    # 2) 테이블 첫 장면: 연결 장면 마지막 프레임 + 실제 병 사진
    last = work / "_bridge_last.png"
    _ff(["-sseof", "-0.1", "-i", str(bridge), "-frames:v", "1", str(last)])
    st, img = _http(cfg["bottle_url"], None, {}, timeout=60)
    if st != 200:
        raise RuntimeError(f"상품 사진을 못 받았습니다(HTTP {st})")
    bottle = work / "_bottle.jpg"
    bottle.write_bytes(img)
    start = work / "drink_start.png"
    if not start.exists() or "start" in cfg.get("redo", []):
        r = gen_image(DRINK_START, [last, bottle], start, "9:16")
        res["start"] = r
        if not r.get("ok"):
            raise RuntimeError(f"음료 첫 장면 실패: {r.get('error')}")
    # 3) 음미 영상
    plain = work / "drink_plain.mp4"
    if not plain.exists() or "video" in cfg.get("redo", []):
        body = {"model": CLIP_MODEL, "input": [{"type": "image", **_b64img(start)}, {"type": "text", "text": DRINK_PROMPT}],
                "response_format": {"type": "video", "resolution": "720p", "aspect_ratio": "9:16"},
                "generation_config": {"video_config": {"task": "image_to_video"}}}
        raw = work / "_drink_raw.mp4"
        raw.write_bytes(_omni_run(key, body))
        chk = _human_parts(raw, work)
        res["human_check"] = chk
        if chk.get("human") is not False:
            raise RuntimeError(f"음료 장면에 사람 손·맨살: {chk.get('where', '')}")
        _norm(raw, plain, H)
        raw.unlink(missing_ok=True)
    # 4) 병 글자가 읽히지 않게: 병 자리를 찾아 그 영역만 한 번 더 흐림(아웃포커스는 장면에서 이미)
    box = _vision_json(start, BOTTLE_BOX)
    res["bottle_box"] = box
    out = work / "drink.mp4"
    if box.get("found"):
        m = 0.04
        x0, y0 = max(0.0, float(box["x0"]) - m), max(0.0, float(box["y0"]) - m)
        x1, y1 = min(1.0, float(box["x1"]) + m), min(1.0, float(box["y1"]) + m)
        _ff(["-i", str(plain), "-filter_complex",
             f"[0:v]split[a][b];[b]crop=iw*{x1 - x0:.3f}:ih*{y1 - y0:.3f}:iw*{x0:.3f}:ih*{y0:.3f},gblur=sigma={int(cfg.get('blur', 8))}[c];"
             f"[a][c]overlay=W*{x0:.3f}:H*{y0:.3f},format=yuv420p[v]",
             "-map", "[v]", "-c:v", "libx264", "-crf", "24", str(out)])
    else:
        _ff(["-i", str(plain), "-c", "copy", str(out)])        # 병을 못 찾으면 아웃포커스만
    for f in (last, bottle):
        f.unlink(missing_ok=True)
    # 5) 미리보기: 춤 → 연결 → 음료(소리 없음, 노래는 인스타에서)
    parts = [dance, bridge, out]
    ins = []
    for p_ in parts:
        ins += ["-i", str(p_)]
    fc = ";".join(f"[{i}:v]scale=-2:{H},fps=24,setsar=1[v{i}]" for i in range(len(parts)))
    fc += ";" + "".join(f"[v{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0,format=yuv420p[v]"
    _ff([*ins, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-crf", "24", "-movflags", "+faststart",
         str(work / "preview.mp4")])
    res["ok"] = True
    res["preview_sec"] = _dur(work / "preview.mp4")

# ---------- 인기 영상 리메이크 + 상품 광고 (사용자 확정 2026-10) ----------
# 원본(사장님이 올린 남의 영상)은 워커 KV에서 서명 주소로 받아 쓰고 저장소에는 절대 남기지 않는다.
# 시험 = 첫 구간만 → 사장님 확인 → 본편 = 나머지 구간(시험 구간 재사용) + 상품 끝 장면 + 느끼한 내레이션 + 광고 문구. 노래는 넣지 않는다.
REMAKE_WORKER = "https://book-carousel.jtaechul.workers.dev"
REMAKE_MAX_SEC = 40.0          # 원본은 앞 40초까지만(한 편 5달러 한도 안)
REMAKE_SEG = 9.5               # Omni 편집은 한 번에 10초까지
REMAKE_COST = {"omni_sec": 0.10, "image": 0.15, "check": 0.01, "tts": 0.02}   # 구글 요금표 기준 어림값(720p 기준 — 360p는 더 쌈, 넉넉히 잡음)
REMAKE_RES = "360p"            # ⛔ 처음부터 360p로 만든다(사용자 확정 2026-10: 큰 화면으로 만들면 비용이 커짐). 720p·1080p로 바꾸지 않는다
# 동물 수 = 원본 등장인물 수(사용자 확정 2026-10: "한 마리만" 규칙 대신 대전제 하나 — 한 명이면 한 마리, 여럿이면 대략 그 수)
REMAKE_ONE_DOG = ("SAME HEADCOUNT: the number of animals in every frame matches the number of people in the original frame - "
                  "one person becomes exactly one animal, never two. Body parts of a person seen at the frame edges belong "
                  "to that same animal and stay attached to it.")
REMAKE_SWAP = ("Edit this video. Change ONLY these things and keep absolutely everything else exactly as it is (bodies, clothes, "
               "every movement and its timing, camera, background, lights): {swap}. Every replaced head is the Shiba Inu from "
               "image 1. Every visible arm, leg, hand and foot becomes a thick, fully furry orange-and-cream Shiba leg ending in a "
               "round Shiba paw (sleeves and trousers stay as they are). " + REMAKE_ONE_DOG + " Remove any watermark or "
               "on-screen text. COMPOSITING QUALITY: the dog parts must look filmed in the same shot - match the original lighting "
               "direction, colour, shadows, motion blur, focus and film grain; the head is a natural size for the body and turns, "
               "nods and moves its mouth exactly with the original head motion; the fur blends seamlessly into the neck and collar "
               "and into the sleeves and trouser hems with no visible seam, outline or halo; the same dog in every frame with no "
               "flicker, morphing or changing markings.")
# 구간 사이 같은 개로: 앞 구간 마지막 장면을 두 번째 참고 이미지로(사용자 지적 2026-10: 합성 품질을 더 높게)
REMAKE_PREV = (" Image 2 is how this Shiba looked at the end of the previous part of the same video: keep it identical (same face, "
               "fur colour and markings, eyes, accessories).")
# 합성 품질 채점: 사람 손 검사와 별도로 이음새·크기·조명·깜빡임을 본다. 기준 미달이면 한도 안에서 한 번 다시
REMAKE_QUALITY = ("These frames come from an AI edit where a person's head, hands and feet were replaced with a Shiba Inu's. Judge "
                  "ONLY the compositing quality: seam or halo where fur meets neck/collar/sleeves, head size and position natural for "
                  "the body, lighting and colour matching the scene, the dog looking identical across frames (no flicker/morphing), "
                  "smeared or melted body parts. JSON only: {\"score\": 0, \"issues\": \"short English, empty if fine\"} (0-100, 100 = "
                  "looks like real footage).")
REMAKE_QPASS = 70
# 스토리보드(사용자 제안 2026-10: 시험 영상 대신 그림으로 먼저 확인 — 한 장 약 0.15달러, 시험 영상 약 1달러).
# 원본에서 6장면(각 구간 첫 장면 + 중간)을 뽑아 3x2 격자 한 장으로 강아지 합성 → 확인받으면 영상 AI가 구간마다 그 첫 장면을 기준으로 삼는다.
BOARD_COLS, BOARD_ROWS, BOARD_CW, BOARD_CH = 3, 2, 360, 640
REMAKE_BOARD = ("Image 1 is a 3x2 grid of six frames taken from one video (each panel is a separate moment; dark bars are only "
                "padding). Edit ALL six panels the same way and keep the grid layout, panel sizes and everything else exactly as "
                "it is (bodies, clothes, poses, background, lights, camera framing): {swap}. Every replaced head is the Shiba Inu "
                "from image 2 (same face, fur colour and markings) - the same dog in every panel; "
                "every visible arm, leg, hand and foot is a thick, fully furry Shiba leg with a round paw. " + REMAKE_ONE_DOG + " Match each panel's lighting, shadows and focus so it looks like real "
                "footage, with no seams at the neck, sleeves or trouser hems. Remove any watermark or on-screen text; add no text.")
REMAKE_BOARD_REF = (" Image {n} is the approved storyboard for the FIRST FRAME of this clip: the first frame must look exactly like "
                    "it (same dog head, paws and background dogs), then follow the original motion.")


def _board_times(L: float, n: int, seg: float) -> list[float]:
    t = [round(i * seg + 0.05, 2) for i in range(n)]            # 칸 1~n = 구간 첫 장면(영상 AI 기준 그림)
    extra = [round(i * seg + seg / 2, 2) for i in range(n)]
    for x in extra:
        if len(t) >= BOARD_COLS * BOARD_ROWS:
            break
        t.append(x)
    while len(t) < BOARD_COLS * BOARD_ROWS:
        t.append(round(L * len(t) / (BOARD_COLS * BOARD_ROWS), 2))
    return t


def _remake_board(ref: Path, L: float, n: int, seg: float, swap: str, work: Path, res: dict, cap: float):
    W0, H0 = BOARD_CW * BOARD_COLS, BOARD_CH * BOARD_ROWS
    fit = f"scale={BOARD_CW}:{BOARD_CH}:force_original_aspect_ratio=decrease,pad={BOARD_CW}:{BOARD_CH}:(ow-iw)/2:(oh-ih)/2"
    cells = []
    for k, t in enumerate(_board_times(L, n, seg)):
        c = work / f"_bcell{k}.png"
        _ff(["-ss", f"{min(t, L - 0.1):.2f}", "-i", str(ref), "-frames:v", "1", "-vf", fit, str(c)])
        cells.append(c)
    tile = Image.new("RGB", (W0, int(W0 * 5 / 4)), (0, 0, 0))   # 4:5에 맞춰 아래만 검은 여백
    for k, c in enumerate(cells):
        tile.paste(Image.open(c).convert("RGB"), ((k % BOARD_COLS) * BOARD_CW, (k // BOARD_COLS) * BOARD_CH))
    src_tile = work / "_board_src.png"
    tile.save(src_tile)
    _remake_spend(res, REMAKE_COST["image"], "스토리보드 그림", cap)
    out = work / "_board_out.png"
    r = gen_image(REMAKE_BOARD.format(swap=swap), [src_tile, ROOT / "pet-episodes" / "characters" / "dog.png"], out, "4:5", "2K")
    if not r.get("ok"):
        raise RuntimeError(f"스토리보드 그림 실패: {r.get('error')}")
    im = Image.open(out).convert("RGB")
    k = im.size[0] / W0
    im.save(work / "board.jpg", quality=88)
    frames = []
    for i in range(BOARD_COLS * BOARD_ROWS):
        x, y = (i % BOARD_COLS) * BOARD_CW * k, (i // BOARD_COLS) * BOARD_CH * k
        f = work / f"board_{i + 1:02d}.jpg"
        im.crop((round(x), round(y), round(x + BOARD_CW * k), round(y + BOARD_CH * k))).save(f, quality=90)
        frames.append(f)
    return {"ok": True, "panels": len(frames)}
REMAKE_SWAP_DEFAULT = ("1) replace the main person's head with the head of the Shiba Inu from image 1; 2) turn their visible arms, "
                       "hands, legs and feet into thick furry Shiba legs with round paws; 3) replace every other person with a real "
                       "dog of various breeds")
REMAKE_END_START = ("Image 1 is the last frame of the previous shot: keep exactly this Shiba Inu (face, fur, outfit) and this place "
                    "and lighting. Image 2 is the real product. Create one photorealistic vertical 9:16 frame: {ending} The product "
                    "from image 2 is clearly visible and in focus right next to the dog, looking exactly like the real product "
                    "(same shape, colours and label layout). All four legs are thick, fully furry Shiba legs with round paws. "
                    "No other added text; only animals in the scene.")
REMAKE_END_PROMPT = ("DURATION: 4 seconds. Image 1 is the first frame. {ending} The product stays where it is and never changes "
                     "shape or label. Same place and lighting, camera almost fixed. Photorealistic. Thick, fully furry dog legs "
                     "and paws only. No added text.")


def _remake_spend(res: dict, usd: float, what: str, cap: float):
    """돈이 드는 호출 직전에 부른다. 한도를 넘으면 그 호출을 하지 않고 멈춘다(사용자 확정: 편당 5달러)."""
    spent = float(res.get("spent", 0))
    if spent + usd > cap + 1e-6:
        raise RuntimeError(f"비용 한도 ${cap:.0f}를 넘게 돼 멈췄습니다(지금까지 약 ${spent:.2f}, 다음 '{what}' 약 ${usd:.2f})")
    res["spent"] = round(spent + usd, 3)
    res.setdefault("ledger", []).append({"what": what, "usd": round(usd, 3)})


def _remake_src(ep_id: str, work: Path) -> Path:
    import hashlib
    import hmac
    sig = hmac.new(_key("GEMINI_API_KEY").strip().encode(), f"remake:{ep_id}".encode(), hashlib.sha256).hexdigest()
    st, raw = _http(f"{REMAKE_WORKER}/api/remake/src?id={ep_id}&sig={sig}", None, {}, timeout=300)
    if st != 200 or len(raw) < 10000:
        why = {403: "서버가 받기를 거절함(서명·접속 차단)", 404: "원본이 없음(7일이 지나 지워졌거나 덜 올라감 — 처음부터 다시 올려 주세요)"}.get(st, "")
        raise RuntimeError(f"원본 영상을 받지 못했습니다(HTTP {st} {why}): {raw[:120].decode('utf-8', 'replace')}")
    src = work / "_src_in.mp4"
    src.write_bytes(raw)
    ref = work / "_src.mp4"                               # 앞 40초, 소리 없이, 세로 720 이하로 정리
    # 원본 소리(발차기·부딪히는 소리 등)는 살려 둔다(사용자 요청 2026-10) — 앞부분 영상에 그대로 깐다
    _ff(["-i", str(src), "-t", f"{REMAKE_MAX_SEC}", "-c:a", "aac", "-b:a", "128k", "-vf", "scale=-2:'min(1280,ih)',fps=24,setsar=1,format=yuv420p",
         "-c:v", "libx264", "-crf", "20", str(ref)])
    src.unlink(missing_ok=True)
    return ref


CUT_ASK = ("Watch this video. Find the part described here and give its time range in seconds: \"{cut}\". "
           'JSON only: {{"found": true, "start": 0.0, "end": 0.0, "what": "short English description of what you found"}}. '
           "If the part continues to the end of the video, set end to the video length. If it is not in the video, found=false.")


def _video_json(video: Path, prompt: str) -> dict:
    key = _key("GEMINI_API_KEY")
    body = {"contents": [{"role": "user", "parts": [{"inline_data": {"mime_type": "video/mp4",
                                                                     "data": base64.b64encode(video.read_bytes()).decode()}},
                                                    {"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}
    for model in ("gemini-flash-latest", "gemini-pro-latest"):
        st, raw = _http(f"{API}/models/{model}:generateContent", json.dumps(body).encode(),
                        {"x-goog-api-key": key, "Content-Type": "application/json"})
        if st == 200:
            try:
                t = "".join(p.get("text", "") for p in json.loads(raw)["candidates"][0]["content"]["parts"])
                return json.loads(t[t.find("{"):t.rfind("}") + 1])
            except Exception:  # noqa: BLE001
                pass
    return {}


def _has_audio(p: Path) -> bool:
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", str(p)], capture_output=True, text=True)
    return "Audio:" in (r.stderr or "")


def _remake_cut(ref: Path, cut: str, work: Path, res: dict, cap: float) -> Path:
    """사장님이 적은 '잘라낼 장면'(예: 끝에 기괴하게 웃는 장면)을 AI가 원본에서 찾아 잘라 낸다(사용자 요청 2026-10).
    찾은 시각은 log에 남겨 다음 실행에도 같은 자리를 자른다(AI가 매번 다르게 답해 구간이 어긋나지 않게)."""
    L = _dur(ref)
    c = res.get("cut")
    if not (c and c.get("text") == cut):
        small = work / "_cut_small.mp4"
        _ff(["-i", str(ref), "-vf", "scale=-2:360,fps=8", "-an", "-c:v", "libx264", "-crf", "30", str(small)])
        _remake_spend(res, REMAKE_COST["check"], "잘라낼 장면 찾기", cap)
        r = _video_json(small, CUT_ASK.format(cut=cut))
        small.unlink(missing_ok=True)
        c = {"text": cut, "found": bool(r.get("found")), "start": float(r.get("start") or 0), "end": float(r.get("end") or 0),
             "what": str(r.get("what", ""))[:200]}
        res["cut"] = c
    if not c["found"] or c["end"] - c["start"] < 0.3:
        return ref
    a, b = max(0.0, c["start"]), min(L, c["end"])
    out = work / "_src_cut.mp4"
    if b >= L - 0.6:                                       # 끝부분이면 그 앞까지만
        _ff(["-i", str(ref), "-t", f"{a:.2f}", "-c:a", "aac", "-c:v", "libx264", "-crf", "18", str(out)])
    elif a <= 0.6:                                         # 앞부분이면 그 뒤부터
        _ff(["-ss", f"{b:.2f}", "-i", str(ref), "-c:a", "aac", "-c:v", "libx264", "-crf", "18", str(out)])
    else:                                                  # 가운데면 앞뒤를 이어 붙인다
        if _has_audio(ref):
            _ff(["-i", str(ref), "-filter_complex",
                 f"[0:v]trim=0:{a:.2f},setpts=PTS-STARTPTS[x];[0:a]atrim=0:{a:.2f},asetpts=PTS-STARTPTS[xa];"
                 f"[0:v]trim={b:.2f},setpts=PTS-STARTPTS[y];[0:a]atrim={b:.2f},asetpts=PTS-STARTPTS[ya];[x][xa][y][ya]concat=n=2:v=1:a=1[v][au]",
                 "-map", "[v]", "-map", "[au]", "-c:v", "libx264", "-crf", "18", "-c:a", "aac", str(out)])
        else:
            _ff(["-i", str(ref), "-filter_complex",
                 f"[0:v]trim=0:{a:.2f},setpts=PTS-STARTPTS[x];[0:v]trim={b:.2f},setpts=PTS-STARTPTS[y];[x][y]concat=n=2:v=1:a=0[v]",
                 "-map", "[v]", "-c:v", "libx264", "-crf", "18", str(out)])
    c["kept_sec"] = round(_dur(out), 2)
    return out


FACE_MODEL = Path(__file__).resolve().parents[1] / "models" / "face_detection_yunet_2023mar.onnx"   # OpenCV YuNet(MIT), 230KB
LIKENESS_RE = re.compile(r"real people|likeness|celebrit|public figure", re.I)


def _mask_faces(src: Path, out: Path, grow: float = 1.0) -> dict:
    """원본 속 실제 사람 얼굴을 머리카락까지 크게 모자이크한다(2026-10 사고: SNL 원본을 구글이 '실제 인물의 얼굴'이라며 거절).
    어차피 머리는 시바견으로 바뀌므로 얼굴을 가려도 결과는 같다. 얼굴을 놓친 몇 프레임은 앞 위치를 이어서 가린다."""
    import cv2
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    sc = min(1.0, 960.0 / max(w, h))
    det = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (int(w * sc), int(h * sc)), 0.35, 0.3, 50)
    tmp = out.with_suffix(".raw.mp4")
    vw = cv2.VideoWriter(str(tmp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    hold, frames, hit, most = [], 0, 0, 0
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        frames += 1
        _, faces = det.detect(cv2.resize(fr, (int(w * sc), int(h * sc))))
        now = []
        for f in (faces if faces is not None else []):
            x, y, bw, bh = (float(v) / sc for v in f[:4])
            gw, gh = bw * 2.2 * grow, bh * 2.1 * grow                    # 머리카락·귀까지(grow로 더 크게)
            now.append((x + bw / 2 - gw / 2, y + bh * 0.3 - gh * 0.5, gw, gh))
        hit += bool(now)
        most = max(most, len(now))

        def _far(b):                                      # 새로 찾은 얼굴과 겹치지 않는 옛 상자는 잠시 더 가린다(한 사람을 놓친 프레임 대비)
            return all(abs((b[0] + b[2] / 2) - (n[0] + n[2] / 2)) > n[2] * 0.5 for n in now)
        hold = [(b, 0) for b in now] + [(b, a + 1) for b, a in hold if a < 12 and _far(b)]
        for (x, y, bw, bh), _ in hold:
            x0, y0 = max(0, int(x)), max(0, int(y))
            x1, y1 = min(w, int(x + bw)), min(h, int(y + bh))
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            roi = fr[y0:y1, x0:x1]
            small = cv2.resize(roi, (max(1, (x1 - x0) // 14), max(1, (y1 - y0) // 14)), interpolation=cv2.INTER_LINEAR)
            fr[y0:y1, x0:x1] = cv2.GaussianBlur(cv2.resize(small, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST), (0, 0), 3)
        vw.write(fr)
    cap.release()
    vw.release()
    if not frames:
        raise RuntimeError(f"얼굴 가리기: 영상을 읽지 못했습니다({src.name})")
    _ff(["-i", str(tmp), "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)])
    tmp.unlink(missing_ok=True)
    return {"frames": frames, "with_face": hit, "max_faces": most}


def _remake_probe(key, ref: Path, prompt: str, work: Path, res: dict, cap: float, cases=None) -> list:
    """어떤 입력 때문에 '실제 인물' 거절이 나는지 1초 조각으로 차례로 시험한다(거절은 무료, 통과하면 거기서 멈춤). 결과만 log에 남긴다."""
    raw = work / "_probe.mp4"
    _ff(["-ss", "0", "-t", "1.0", "-i", str(ref), "-an", "-c:v", "libx264", "-crf", "18", str(raw)])
    vids = {"mask": work / "_probe_m.mp4", "mask_strong": work / "_probe_ms.mp4"}
    out = [{"mask": _mask_faces(raw, vids["mask"]), "mask_strong": _mask_faces(raw, vids["mask_strong"], 1.6)}]
    dog = {"type": "image", **_b64img(ROOT / "pet-episodes" / "characters" / "dog.png")}
    board = work / "board_01.jpg"
    neutral = "Edit this video: turn every person's head into a cartoon-free realistic Shiba Inu dog head and their hands into furry paws. Keep the motion."
    cases = cases or [["mask", "swap", 0], ["mask", "neutral", 0], ["mask_strong", "neutral", 0], ["board", "i2v", 0]]
    for vk, tk, _ in cases:
        name = f"{vk}+{tk}"
        if vk == "board":
            if not board.exists():
                continue
            body = {"model": CLIP_MODEL, "input": [{"type": "image", **_b64img(board)}, {"type": "text", "text":
                    "DURATION: 4 seconds. Image 1 is the first frame (a storyboard panel; use only the picture area, ignore black bars). "
                    "The characters keep dancing with the same energy, natural motion, photorealistic, camera almost fixed."}],
                    "response_format": {"type": "video", "resolution": REMAKE_RES, "aspect_ratio": "9:16"},
                    "generation_config": {"video_config": {"task": "image_to_video"}}}
            usd = REMAKE_COST["omni_sec"] * 4
        else:
            body = {"model": CLIP_MODEL, "input": [{"type": "video", "mime_type": "video/mp4",
                                                    "data": base64.b64encode(vids[vk].read_bytes()).decode()}, dog,
                                                   {"type": "text", "text": prompt if tk == "swap" else neutral}],
                    "response_format": {"type": "video", "resolution": REMAKE_RES},
                    "generation_config": {"video_config": {"task": "edit"}}}
            usd = REMAKE_COST["omni_sec"] * 1.0
        _remake_spend(res, usd, f"원인 찾기: {name}", cap)
        try:
            _omni_run(key, body)
            out.append({"case": name, "ok": True})
            break                                         # 통과하면 더 보내지 않는다(돈 절약)
        except RuntimeError as e:
            if "HTTP 400" in str(e):
                res["spent"] = round(float(res.get("spent", 0)) - usd, 3)
            out.append({"case": name, "ok": False, "err": str(e)[:120]})
    return out


def _remake_seg(key, ref: Path, i: int, seg: float, prompt: str, work: Path, res: dict, cap: float, h: int) -> Path:
    out = work / f"rm_seg{i + 1}.mp4"
    piece = work / f"_rm_piece{i + 1}.mp4"
    _ff(["-ss", f"{i * seg:.3f}", "-t", f"{seg:.3f}", "-i", str(ref), "-an", "-c:v", "libx264", "-crf", "16", str(piece)])
    inputs = [{"type": "image", **_b64img(ROOT / "pet-episodes" / "characters" / "dog.png")}]
    prev = work / f"rm_seg{i}.mp4"
    if i > 0 and prev.exists():                            # 앞 구간과 같은 개로 이어지게
        last = work / f"_rm_prev{i}.png"
        _ff(["-sseof", "-0.05", "-i", str(work / f"_rm_hi{i}.mp4" if (work / f"_rm_hi{i}.mp4").exists() else prev),
             "-frames:v", "1", str(last)])
        inputs.append({"type": "image", **_b64img(last)})
        prompt = prompt + REMAKE_PREV
    board = work / f"board_{i + 1:02d}.jpg"
    if board.exists():                                     # 확인받은 스토리보드 첫 장면에 맞춘다
        inputs.append({"type": "image", **_b64img(board)})
        prompt = prompt + REMAKE_BOARD_REF.format(n=len(inputs))
    tries = []
    res_name = REMAKE_RES
    # ⛔ 구간마다 딱 한 번만 만든다(사용자 지시 2026-10: "다시 만들지 마. 돈 아까워. 70점 아래여도 짠 대로") — 검사·다시 만들기 없음
    _remake_spend(res, REMAKE_COST["omni_sec"] * seg, f"구간{i + 1} 바꾸기", cap)
    vid = {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(piece.read_bytes()).decode()}
    rawo = work / f"_rm_raw{i + 1}.mp4"
    body = {"model": CLIP_MODEL, "input": [vid, *inputs, {"type": "text", "text": prompt}],
            "response_format": {"type": "video", "resolution": REMAKE_RES},
            "generation_config": {"video_config": {"task": "edit"}}}
    def _send(piece_path: Path):
        v = {"type": "video", "mime_type": "video/mp4", "data": base64.b64encode(piece_path.read_bytes()).decode()}
        body["input"][0] = v
        rawo.write_bytes(_omni_run(key, body))

    if res.get("mask_faces"):                             # 앞 구간에서 '실제 인물' 거절을 받았으면 처음부터 가린다
        masked = work / f"_rm_piece{i + 1}_m.mp4"
        res.setdefault("masked", {})[f"seg{i + 1}"] = _mask_faces(piece, masked)
        piece = masked
    try:
        try:
            _send(piece)
        except RuntimeError as e:
            # 실제 인물 얼굴이라 거절(요금 없음) → 얼굴을 모자이크해 한 번만 다시 보낸다(사용자 지시 2026-10: 실패 재발 방지)
            if "HTTP 400" in str(e) and LIKENESS_RE.search(str(e)) and not res.get("mask_faces"):
                res["mask_faces"] = True
                res.setdefault("ledger", []).append({"what": f"구간{i + 1} 실제 인물 거절 → 얼굴 가리고 다시(요금 없음)", "usd": 0})
                masked = work / f"_rm_piece{i + 1}_m.mp4"
                res.setdefault("masked", {})[f"seg{i + 1}"] = _mask_faces(piece, masked)
                _send(masked)
            else:
                raise
    except RuntimeError as e:
        if "HTTP 400" in str(e):                          # 막힌 요청은 요금 없음 → 장부에서 되돌린다
            res["spent"] = round(float(res.get("spent", 0)) - REMAKE_COST["omni_sec"] * seg, 3)
            res.setdefault("ledger", []).append({"what": f"구간{i + 1} 차단됨(요금 없음)", "usd": -round(REMAKE_COST["omni_sec"] * seg, 3)})
        raise
    best = (rawo, {}, None, "")
    tries = [best]
    got = _dur(best[0])
    k = seg / got if got else 1.0                         # 원본 구간과 같은 길이로(박자 유지)
    hi = work / f"_rm_hi{i + 1}.mp4"                      # 다음 구간 참고용(커밋 안 함)
    _ff(["-i", str(best[0]), "-an", "-vf", f"setpts=PTS*{k:.5f}", "-t", f"{seg:.3f}", "-c:v", "libx264", "-crf", "18", str(hi)])
    _ff(["-i", str(hi), "-an", "-vf", f"scale=-2:{h}:flags=lanczos,unsharp=3:3:0.4,fps=24,setsar=1,format=yuv420p",
         "-c:v", "libx264", "-crf", "19", "-preset", "slow", str(out)])
    res.setdefault("segs", {})[f"seg{i + 1}"] = {"human": best[1].get("human"), "where": best[1].get("where", ""),
                                                 "quality": best[2], "issues": best[3], "tries": len(tries), "res": res_name}
    return out


COPY_SPOT = ("This is the final shot of an ad. Big text (about 30% of the frame height) must be placed either at the TOP or at the "
             "BOTTOM so that it does not cover the dog's face, its legs/paws, anything it is holding or wearing (e.g. a cold pack) "
             "or the product. Which band is emptier? JSON only: {\"place\": \"top\" or \"bottom\", \"why\": \"short\"}")


def _copy_png(big: str, sub: str, out: Path, W=720, H=1280, place: str = "bottom"):
    """광고 문구: 끝 장면에서 강아지·들고 있는 것·상품을 가리지 않는 쪽(위/아래)에 둔다(사용자 지적 2026-10: 냉찜질이 글씨에 가림).
    배경은 딱딱한 반투명 상자 대신 가장자리에서 서서히 사라지는 그라데이션 + 글씨 그림자(사용자 지적 2026-10: 상자가 인위적)."""
    from PIL import ImageFilter
    band = int(H * 0.42)
    grad = Image.new("L", (1, band))
    for yy in range(band):                                 # 가장자리 쪽 진하고(최대 45%) 안쪽으로 부드럽게 0
        t = 1 - yy / band
        grad.putpixel((0, yy), int(115 * t * t))
    grad = grad.resize((W, band))
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shade = Image.new("RGBA", (W, band), (0, 0, 0, 255))
    if place == "top":
        shade.putalpha(grad)
        im.paste(shade, (0, 0))
        y = int(H * 0.095)
    else:
        shade.putalpha(grad.transpose(Image.FLIP_TOP_BOTTOM))
        im.paste(shade, (0, H - band))
        y = int(H * 0.60)
    # 글씨 크기는 이온음료 광고 편과 같게(사용자 지시 2026-10): 큰 글씨 85·작은 글씨 43(720 기준), 줄 간격 96·52
    def fit(text, size):                                   # 너무 긴 줄은 화면 폭에 맞게 줄인다
        f = _f(SUB_FONT, size)
        while size > 24 and f.getlength(text) > W - 40:
            size -= 2
            f = _f(SUB_FONT, size)
        return f
    lines = [(ln, fit(ln, 85), "white", 6, 96) for ln in [x for x in big.splitlines() if x.strip()][:2]]
    lines += [("", None, None, 0, 18)]
    lines += [(ln, fit(ln, 43), (255, 214, 10), 4, 52) for ln in [x for x in sub.splitlines() if x.strip()][:2]]
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))           # 글씨 그림자(흐림) — 상자 없이도 밝은 배경에서 읽히게
    ds, dt = ImageDraw.Draw(sh), ImageDraw.Draw(im)
    yy = y
    for ln, f, col, sw, step in lines:
        if f:
            x = (W - f.getlength(ln)) / 2
            ds.text((x, yy + 4), ln, font=f, fill=(0, 0, 0, 170), stroke_width=sw + 3, stroke_fill=(0, 0, 0, 170))
        yy += step
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(6)))
    dt = ImageDraw.Draw(im)
    yy = y
    for ln, f, col, sw, step in lines:
        if f:
            x = (W - f.getlength(ln)) / 2
            dt.text((x, yy), ln, font=f, fill=col, stroke_width=sw, stroke_fill="black")
        yy += step
    im.save(out)


def _cta_png(out: Path, W=720, H=1280):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    f = _f(SUB_FONT, 50)                                  # 이온음료 편과 같은 크기
    t = "구매는 프로필 링크에서"
    dr.text(((W - f.getlength(t)) / 2, int(H * 0.885)), t, font=f, fill="white", stroke_width=4, stroke_fill="black")
    im.save(out)


def step_remake(ep, epdir, work, log, req):
    import math
    res = log.setdefault("remake", {})
    rm = ep.get("remake") or {}
    cap = float(rm.get("cap", 5))
    mode = (req.get("remake") or {}).get("mode", "test")
    key = _key("GEMINI_API_KEY")
    W, H = 360, 640                                       # 360p(사용자 확정)
    prompt = REMAKE_SWAP.format(swap=(rm.get("swap") or REMAKE_SWAP_DEFAULT).rstrip(". "))
    try:
        ref = _remake_src(epdir.name, work)
        if (rm.get("cut") or "").strip():
            ref = _remake_cut(ref, rm["cut"].strip(), work, res, cap)
        L = _dur(ref)
        n = max(1, math.ceil(L / REMAKE_SEG))
        seg = L / n
        res.update({"src_sec": round(L, 2), "segments": n})
        est_all = round(REMAKE_COST["omni_sec"] * L + REMAKE_COST["image"] + REMAKE_COST["omni_sec"] * 4
                        + REMAKE_COST["tts"], 2)
        if mode == "probe":                               # 거절 원인 찾기: 1초짜리로 넣는 것을 바꿔 가며 보낸다(통과하면 1초에 0.1달러)
            res["probe"] = _remake_probe(key, ref, prompt, work, res, cap, (req.get("remake") or {}).get("cases"))
            return
        if mode == "board":                               # 그림으로 먼저 확인(영상은 만들지 않음)
            if (req.get("remake") or {}).get("redo") or not (work / "board.jpg").exists():
                res["board"] = _remake_board(ref, L, n, seg, (rm.get("swap") or REMAKE_SWAP_DEFAULT).rstrip(". "), work, res, cap)
            res["est_full"] = est_all
            if float(res.get("spent", 0)) + est_all > cap:
                res["board"]["over"] = True
            return
        # 수정 요청(사용자 요청 2026-10): 고를 부분의 결과만 지우고 다시 만든다 — 나머지는 그대로 재사용(돈 절약)
        redo = (req.get("remake") or {}).get("redo") if mode == "full" else None
        if isinstance(redo, list) and redo:
            gone = {"segs": ["rm_seg*.mp4", "remake.mp4", "board.jpg", "board_*.jpg"], "ending": ["rm_end_start.png", "rm_end.mp4"],
                    "vo": ["rm_vo.wav"], "copy": []}
            for part in redo:
                for pat in gone.get(part, []):
                    for f in work.glob(pat):
                        f.unlink(missing_ok=True)
            res.setdefault("fixes", []).append({"parts": redo, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        if mode == "full" and not (work / "board.jpg").exists():   # 스토리보드 없이 바로 영상을 누르면 먼저 그린다(약 0.16달러, 영상 품질 기준)
            res["board"] = _remake_board(ref, L, n, seg, (rm.get("swap") or REMAKE_SWAP_DEFAULT).rstrip(". "), work, res, cap)
            # 새로 그린 스토리보드는 확인받은 뒤에 영상으로(사용자 지적 2026-10 헬기 편: 확인 안 한 그림에 개가 두 마리 → 영상도 두 마리)
            res["est_full"] = est_all
            res["board"]["wait"] = True
            return
        if mode == "full" and isinstance(res.get("board"), dict):
            res["board"].pop("wait", None)                # 확인받은 스토리보드로 진행
        if mode == "full" and not (work / "rm_seg1.mp4").exists():
            if float(res.get("spent", 0)) + est_all > cap:
                raise RuntimeError(f"영상 예상 비용(약 ${est_all:.2f})이 한도 ${cap:.0f}를 넘어 시작하지 않았습니다. 더 짧은 원본으로 다시 해 주세요.")
        # 1) 시험(예전 방식): 첫 구간(본편에 그대로 쓴다)
        s1 = work / "rm_seg1.mp4"
        if not s1.exists():
            _remake_seg(key, ref, 0, seg, prompt, work, res, cap, H)
            if mode == "test":
                _ff(["-i", str(s1), "-c", "copy", "-movflags", "+faststart", str(work / "test.mp4")])
        first = res.get("segs", {}).get("seg1", {})
        if mode == "test":
            res["test"] = {"ok": True, "human": first.get("human"), "where": first.get("where", ""),
                           "quality": first.get("quality"), "issues": first.get("issues", "")}
        res["est_full"] = round(REMAKE_COST["omni_sec"] * seg * (n - 1) + REMAKE_COST["image"] + REMAKE_COST["omni_sec"] * 4
                                + REMAKE_COST["tts"], 2)
        if mode != "full":
            return
        # 본편 전체 예상이 한도를 넘으면 시작하지 않는다
        if float(res.get("spent", 0)) + res["est_full"] > cap:
            raise RuntimeError(f"본편 예상 비용(약 ${res['est_full']:.2f})이 한도 ${cap:.0f}를 넘어 시작하지 않았습니다. 더 짧은 원본으로 다시 해 주세요.")
        segs = []
        for i in range(n):
            o = work / f"rm_seg{i + 1}.mp4"
            if not o.exists():
                _remake_seg(key, ref, i, seg, prompt, work, res, cap, H)
            segs.append(o)
        body_v = work / "remake.mp4"
        ins = []
        for o in segs:
            ins += ["-i", str(o)]
        _ff([*ins, "-filter_complex", "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0,format=yuv420p[v]",
             "-map", "[v]", "-c:v", "libx264", "-crf", "23", str(body_v)])
        # 2) 끝 장면: 마지막 프레임 + 실제 상품 사진 → 첫 장면 → 4초
        last = work / "_rm_last.png"
        _ff(["-sseof", "-0.1", "-i", str(body_v), "-frames:v", "1", str(last)])
        prod = work / "_product.jpg"
        purl = (ep.get("product") or {}).get("image", "")
        st, img = _http(purl, None, {}, timeout=60) if purl else (0, b"")
        if st != 200 or len(img) < 1000:
            raise RuntimeError("상품 사진을 받지 못했습니다 — 상품을 다시 골라 주세요(사진 없이 만든 광고는 의미 없음)")
        prod.write_bytes(img)
        ending = (rm.get("ending") or "The Shiba Inu happily uses and enjoys the product.").rstrip(". ") + "."
        start = work / "rm_end_start.png"
        if not start.exists():
            _remake_spend(res, REMAKE_COST["image"], "끝 장면 그림", cap)
            r = gen_image(REMAKE_END_START.format(ending=ending), [last, prod], start, "9:16")
            if not r.get("ok"):
                raise RuntimeError(f"끝 장면 그림 실패: {r.get('error')}")
        end_v = work / "rm_end.mp4"
        if not end_v.exists():
            # 끝 장면도 한 번만(다시 만들기·검사 없음 — 사용자 지시 2026-10)
            _remake_spend(res, REMAKE_COST["omni_sec"] * 4, "끝 장면 영상", cap)
            body = {"model": CLIP_MODEL, "input": [{"type": "image", **_b64img(start)},
                                                   {"type": "text", "text": REMAKE_END_PROMPT.format(ending=ending)}],
                    "response_format": {"type": "video", "resolution": REMAKE_RES, "aspect_ratio": "9:16"},
                    "generation_config": {"video_config": {"task": "image_to_video"}}}
            raw = work / "_rm_end_raw.mp4"
            try:
                raw.write_bytes(_omni_run(key, body))
            except RuntimeError as e:
                if "HTTP 400" in str(e):
                    res["spent"] = round(float(res.get("spent", 0)) - REMAKE_COST["omni_sec"] * 4, 3)
                raise
            _norm(raw, end_v, H)
        # 3) 느끼한 내레이션(Enceladus, 1.3배 — 사용자 확정 2026-10)
        vo = work / "rm_vo.wav"
        if not vo.exists():
            _remake_spend(res, REMAKE_COST["tts"], "내레이션", cap)
            model = _pick_model(key, TTS_MODELS)
            body = {"contents": [{"role": "user", "parts": [{"text": f"{VO_DIRECTION} {VO_PACE}\n\n대사: {rm.get('vo', '')}"}]}],
                    "generationConfig": {"responseModalities": ["AUDIO"],
                                         "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE_NAME}}}}}
            code, raw = _http(f"{API}/models/{model}:generateContent", json.dumps(body).encode(),
                              {"x-goog-api-key": key, "Content-Type": "application/json"})
            parts = [p for c in json.loads(raw).get("candidates", []) for p in c.get("content", {}).get("parts", [])
                     if "inlineData" in p] if code == 200 else []
            if not parts:
                raise RuntimeError(f"내레이션 녹음 실패(HTTP {code})")
            _pcm_to_wav(base64.b64decode(parts[0]["inlineData"]["data"]), vo, float(rm.get("vo_speed", REMAKE_VO_SPEED)))
        # 4) 조립: 리메이크 → (흰 번쩍) 끝 장면(느리게 + 마지막 장면 멈춤) + 문구 + 내레이션. 노래 없음
        Lb, vl = _dur(body_v), _dur(vo)
        # 강아지 낑낑 소리는 실패 직후 광고 화면이 시작될 때(사용자 지시 2026-10) → 내레이션은 낑낑 소리가 끝난 뒤
        whimper = SFX_DIR / "whimper.mp3"
        use_wh = rm.get("whimper") is True and whimper.exists()   # 장면에 맞을 때만(사용자 지적 2026-10: 부딪힌 게 아니면 필요 없음)
        wh_at = Lb + 0.15
        t0 = (wh_at + _dur(whimper) + 0.1) if use_wh else max(0.0, Lb - 0.25)
        dd = round(max(4.0, t0 + vl + 0.6 - Lb), 2)        # 끝 장면 길이
        cta_at = max(0.5, t0 + vl - 1.3 - Lb)
        copy_png, cta_png = work / "_copy.png", work / "_cta.png"
        place = rm.get("copy_place") or (res.get("copy_place") or {}).get("place")
        if place not in ("top", "bottom"):                # 끝 장면을 보고 비어 있는 쪽(위/아래)을 고른다 — 한 번 정하면 기록해 둔다
            _remake_spend(res, REMAKE_COST["check"], "문구 위치 고르기", cap)
            r = _vision_json(start, COPY_SPOT) or {}
            place = r.get("place") if r.get("place") in ("top", "bottom") else "bottom"
            res["copy_place"] = {"place": place, "why": str(r.get("why", ""))[:120]}
        _copy_png(rm.get("big", ""), rm.get("sub", ""), copy_png, place=place)
        _cta_png(cta_png)
        tot = round(Lb + dd, 2)
        fit = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"   # 원본이 9:16이 아니어도 이어 붙게
        # 가로 원본(16:9 등)은 세로 화면에 검은 띠 대신 같은 영상을 흐리게 깔고 가운데에 원본 비율 그대로(사용자 지적 2026-10: 9:16으로 나와야 함)
        # — 가운데만 잘라 내면 옆 사람이 잘리므로 기본은 흐린 배경 채우기. 조금 키우려면 remake.frame_zoom(예 1.25, 양옆이 그만큼 잘림)
        bw, bh = _wh(body_v)
        if bw > bh * W / H * 1.05:
            z = max(1.0, float(rm.get("frame_zoom", 1.0)))
            fw = int(W * z) // 2 * 2
            body_f = (f"split[bg0][fg0];[bg0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=18,"
                      f"eq=brightness=-0.10:saturation=0.85[bgb];[fg0]scale={fw}:-2,crop={W}:ih[fgs];"
                      f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2")
            res["frame"] = {"mode": "blur_fill", "src": f"{bw}x{bh}", "zoom": z}
        else:
            body_f = fit
        V = (f"[0:v]{body_f},fps=24,setsar=1,format=yuv420p[a];"
             f"[1:v]{fit},setpts=1.6*PTS,fps=24,tpad=stop_mode=clone:stop_duration=20,trim=duration={dd},setpts=PTS-STARTPTS,"
             f"setsar=1,format=yuv420p,fade=t=in:st=0:d=0.25:color=white[b0];"
             f"[2:v]scale={W}:{H},format=rgba,trim=duration={dd},fade=t=in:st=0:d=0.3:alpha=1[t];[b0][t]overlay=(W-w)/2:0[b1];"
             f"[3:v]scale={W}:{H},format=rgba,trim=duration={dd},fade=t=in:st={cta_at:.2f}:d=0.25:alpha=1[c];[b1][c]overlay=(W-w)/2:0[b];"
             f"[a][b]concat=n=2:v=1:a=0,format=yuv420p[v];"
             f"[4:a]aresample=48000,adelay={int(t0 * 1000)}:all=1,apad,atrim=0:{tot}[vo0];")
        wh_in = ["-i", str(whimper)] if use_wh else []
        if use_wh:
            V += f"[5:a]volume=1.0,adelay={int(wh_at * 1000)}:all=1,apad,atrim=0:{tot}[wh0];[vo0][wh0]amix=inputs=2:normalize=0:duration=first[vo0w];"
            vo_lbl, nxt = "[vo0w]", 6
        else:
            vo_lbl, nxt = "[vo0]", 5
        src_in, mix = [], [vo_lbl]
        if rm.get("keep_audio", True) and _has_audio(ref):   # 원본 소리(발차기 소리 등)를 앞부분에 깔고, 내레이션이 나오면 끈다
            src_in = ["-i", str(ref)]
            V += (f"[{nxt}:a]atrim=0:{Lb:.2f},asetpts=PTS-STARTPTS,volume={float(rm.get('src_vol', 1.0)):.2f},"
                  f"afade=t=out:st={max(0.0, t0 - 0.3):.2f}:d=0.3,apad,atrim=0:{tot}[src0];")
            mix.append("[src0]")
            nxt += 1
        # 장면 효과음(사용자 요청 2026-10: 헬기 소리·용암에 팝콘 터지는 소리가 잘 들리게) — remake.sfx = [{file, at, vol, loop}]
        # 시각은 리메이크 본편 기준. loop는 at부터 내레이션 시작(t0)까지 반복하다 줄여 끈다. 파일은 pet-episodes/sfx(우리가 만든 효과음)
        sfx_in = []
        for s in rm.get("sfx") or []:
            f = SFX_DIR / str(s.get("file", ""))
            if not f.is_file():
                continue
            at, vol = max(0.0, float(s.get("at", 0))), float(s.get("vol", 1.0))
            if s.get("loop"):
                ln = max(0.5, float(s.get("until", t0)) - at)
                sfx_in += ["-stream_loop", "-1", "-i", str(f)]
                body_a = f"atrim=0:{ln:.2f},afade=t=out:st={max(0.0, ln - 0.6):.2f}:d=0.6,"
            else:
                sfx_in += ["-i", str(f)]
                body_a = ""
            lb = f"[fx{len(mix)}]"
            V += (f"[{nxt}:a]aresample=48000,{body_a}volume={vol:.2f},asetpts=PTS-STARTPTS,"
                  f"adelay={int(at * 1000)}:all=1,apad,atrim=0:{tot}{lb};")
            mix.append(lb)
            nxt += 1
        if len(mix) > 1:
            V += f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.97[aud]"
        else:
            V += f"{vo_lbl}alimiter=limit=0.97[aud]"
        # 말소리 또렷하게(사용자 지적 2026-10 헬기 편: 목소리·발음이 잘 안 들림) — 웅웅거리는 저음은 줄이고 발음 대역(3~5kHz)을 올린다, -9 LUFS
        # 내레이션은 고르게 눌러 준 뒤 영상에서 가장 큰 소리(원본 발차기 등, 실측 약 -12.7 LUFS)보다 크게(-10 LUFS, 최고점 -1) 맞춘 파일을 따로 만든다(사용자 지적 2026-10: 성우 목소리가 너무 작음).
        # ⚠️ 한 그래프 안에서 loudnorm 뒤에 adelay를 걸면 지연이 무시돼 내레이션이 통째로 빠진다(실측) → 파일로 먼저 만든다
        vo_loud = work / "_vo_loud.wav"
        _ff(["-i", str(vo), "-af", "highpass=f=90,equalizer=f=220:t=q:w=1:g=-3,equalizer=f=3000:t=q:w=1.2:g=5,equalizer=f=5500:t=q:w=1:g=2,"
             "acompressor=threshold=-24dB:ratio=3.5:attack=5:release=90:makeup=3,loudnorm=I=-9:TP=-1.0:LRA=6,aresample=48000",
             str(vo_loud)])
        final = work / "final.mp4"
        _ff(["-i", str(body_v), "-i", str(end_v), "-loop", "1", "-i", str(copy_png), "-loop", "1", "-i", str(cta_png), "-i", str(vo_loud), *wh_in, *src_in, *sfx_in,
             "-filter_complex", V, "-map", "[v]", "-map", "[aud]", "-c:v", "libx264", "-crf", "22", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(final)])
        _ff(["-ss", f"{Lb + min(dd - 0.3, 2.5):.2f}", "-i", str(final), "-frames:v", "1", "-vf", "scale=1080:1920:flags=lanczos",
             "-q:v", "3", str(work / "cover.jpg")])
        log["cover"] = "work/cover.jpg"
        log["assemble"] = {"ok": True, "sec": round(_dur(final), 2), "note": "리메이크(원본 소리 + 내레이션, 노래는 인스타 앱에서)"}
        res["full"] = {"ok": True}
    finally:                                              # 남의 원본·중간 파일은 성공·실패와 관계없이 저장소에 남기지 않는다
        for f in work.glob("_*"):
            f.unlink(missing_ok=True)
        for f in work.glob("rm_seg*_raw*"):
            f.unlink(missing_ok=True)


def main(path: str) -> int:
    rp = Path(path)
    req = json.loads(rp.read_text(encoding="utf-8"))
    epdir = rp.parent.parent
    epf = epdir / "episode.json"
    ep = json.loads(epf.read_text(encoding="utf-8")) if epf.exists() else {"clips": []}
    ep["_bgm_mix"] = bool(req.get("bgm_mix"))                # 기본: 배경음악 없이(릴스 번역용)
    work = epdir / "work"
    work.mkdir(exist_ok=True)
    logp = work / "log.json"
    log = json.loads(logp.read_text(encoding="utf-8")) if logp.exists() else {}
    # redo: "c03" = 그 컷 영상만 다시, "kf_c03" = 첫 장면부터 다시(영상도 자동으로 다시), "character" = 캐릭터 다시
    redo = set(req.get("redo", []))
    redo |= {n[3:] for n in redo if n.startswith("kf_")}
    steps = req.get("steps", ["character", "keyframes", "clips", "tts", "assemble"])
    ok = True
    try:
        if "bgm" in steps:
            step_bgm(work, log, req.get("bgm"))
        if "ig_probe" in steps:
            step_ig_probe(log)
        if "dance" in steps:
            try:
                step_dance(work, log, req.get("dance") or {})
            finally:                                         # 남의 영상(참고 춤)은 성공·실패와 관계없이 저장소에 남기지 않는다
                for f in work.glob("_ref*"):
                    f.unlink(missing_ok=True)
        if "vo" in steps:
            step_vo(work, log, req.get("vo") or {})
        if "remake" in steps:
            step_remake(ep, epdir, work, log, req)
        if "swap" in steps:
            try:
                step_swap(work, log, req.get("swap") or {})
            finally:
                for f in work.glob("_*"):
                    f.unlink(missing_ok=True)
        if "dance_full" in steps:
            try:
                step_dance_full(work, log, req.get("dance_full") or {})
            finally:
                for f in work.glob("_*"):
                    f.unlink(missing_ok=True)
        if "drink" in steps:
            try:
                step_drink(work, log, req.get("drink") or {})
            finally:                                         # 실패해도 중간 파일은 남기지 않는다
                for f in work.glob("_*"):
                    f.unlink(missing_ok=True)
        if not ep["clips"]:
            if "publish" in steps:                               # 직접 조립한 광고 편(컷 없음)도 인스타에 올릴 수 있게
                step_ig_publish(ep, epdir, work, log, bool(req.get("force_publish")))
            raise StopIteration
        if "voices" in steps:
            step_voices(ep, epdir, work, log, req.get("voices"))
        character = step_character(ep, epdir, work, log, redo)
        if "keyframes" in steps:
            # 음식 참고 이미지는 필수(사용자 확정 2026-09) — 없으면 비싼 그림·영상 단계를 시작하지 않는다
            if not any((epdir / "refs" / f).exists() for f in ("food.png", "food.jpg")):
                raise RuntimeError("음식 참고 이미지(refs/food.*)가 없어 제작을 멈췄습니다 — 관리자 영상 상세의 '음식 이미지 다시 만들기'를 먼저 누르세요")
            setimg = step_set(ep, epdir, work, log, redo)
            if req.get("storyboard", True):                     # 기본: 격자 한 장(사용자 확정 2026-09)
                step_storyboard(ep, epdir, work, log, redo, character, setimg)
            step_keyframes(ep, epdir, work, log, redo, character, setimg)   # 빠진 칸·redo 칸만 개별로
            check_adjacent(ep, work, log, redo, character, setimg, epdir)  # 이웃 컷 구도가 같으면 그 칸만 다시
        # 녹음을 먼저 한다 — 컷마다 대사 길이를 재서 영상 AI에 4·6·8초 중 맞는 길이로 주문하기 위해(비용·흐트러짐 감소)
        if "tts" in steps:
            step_tts(ep, epdir, work, log, redo)
        if "clips" in steps:
            step_clips(ep, epdir, work, log, redo)
        if "assemble" in steps:
            step_assemble(ep, epdir, work, log)
        elif "cover" in steps:
            step_cover(ep, work, log)
        if "publish" in steps:                                   # 인스타 릴스 발행(완성본이 커밋된 뒤 별도 요청으로)
            step_ig_publish(ep, epdir, work, log, bool(req.get("force_publish")))
    except StopIteration:
        pass
    except Exception as e:  # noqa: BLE001
        log["error"] = str(e)[:500]
        ok = False
    log["last_request"] = {"file": rp.name, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ok": ok}
    logp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False)[:3000])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
