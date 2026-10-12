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
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
FX = float(os.environ.get("USD_KRW") or 1470)
FAKE_IMG = os.environ.get("MINI_FAKE_IMAGE", "") == "1"          # 로컬 시험: 이미지 편집 대신 ref 를 붙인 가짜 합성(0원)
W, H = 720, 1280

KEEP_LINE = ("Keep both figures exactly identical to the attached reference figurines — same faces, hairstyles, "
             "body proportions, skin tone and swimwear.")
EDIT_HEAD = ("TASK: Edit the attached HOTEL PHOTOGRAPH (the photo of the real place). Keep the photograph exactly as it is — same framing, walls, "
             "water, furniture, decorations, colors, lighting and focus; do not blur, recolor, crop, extend, clean up or redraw anything, "
             "and do not add or remove any object. Only add the two miniature figurines shown in the attached REFERENCE IMAGE (two figurines sitting on a pool edge), "
             "placed into the scene as described below, with correct contact shadows, reflections and water interaction so they look "
             "physically present in the photograph.")
EDIT_SCALE = ("SCALE AND PLACEMENT: the figurines are 10 cm toys standing at the real spot described in SCENE, in true perspective — "
              "if that spot is close to the camera they appear large (up to about one third of the frame height), if it is farther they "
              "appear smaller. The real place keeps its true size and stays clearly recognizable. Never enlarge or shrink anything in the photograph.")
EDIT_PHOTO = ("PHOTOGRAPHY: realistic toy photography matched to the photograph's own light direction, color temperature and grain; "
              "figures tack-sharp; the background keeps the photograph's existing sharpness (at most a very gentle natural softness right "
              "behind the figures). Vertical 9:16, same size as the hotel photograph.")
EDIT_TAIL = ("PLACEMENT RULE: put the figurines only where that kind of place really exists in the photograph (real water, real pool rim, "
             "real floor). Never add, extend, enlarge, move or replace any pool, water area, floor, wall or structure to make room for them; "
             "if the described spot is farther from the camera, place them there and let them appear smaller. Do not zoom, reframe or shift "
             "the photograph. OUTPUT: exactly one photorealistic image. No text, no captions, no logos, no watermark, no borders.")
MAX_CHANGED = 0.30          # 배경 보존 검사(0원): 원본 대비 바뀐 화면 비율 상한. 실측 mini-1: 잘 된 파도풀 11% · 배경을 다시 그린 스파 67%

VEO_HEAD = ("The first frame is a real hotel photograph with two small hand-sculpted, hand-painted polymer-clay art-doll figurines of a "
            "Korean couple (elegant adult proportions, eight heads tall, satin clay finish). Keep the figurines exactly as they appear in "
            "the first frame for the whole clip: same faces with painted almond eyes and small sculpted lips (the mouth may open when laughing or surprised), same hairstyles "
            "(woman: dark-brown hair with a left side part in a neat low bun; man: black short dandy cut with a forward fringe), same "
            "cobalt-blue one-piece swimsuit and dark-navy swim shorts, same body proportions. They are alive and clearly enjoying the place: "
            "natural, visible, playful body movement (arms, heads, torsos and splashing water), smooth like an animated figurine film — "
            "not frozen, not stiff. They may move around within the same pool or spot.")
VEO_TAIL = ("Water reacts to every movement with splashes, droplets and ripples; steam and light behave naturally. Camera: a smooth, moderate push-in toward the figurines that ends at a medium shot — the figurines fill about half of the frame height and the place stays clearly visible behind them; never an extreme close-up of faces. The hotel place "
            "stays exactly the same as the first frame: no new objects, no new people, no text, no logos, no morphing; the figurines' "
            "faces, hair and swimwear never change; they never turn into real humans. Vertical 9:16, 4 seconds.")


def log(*a):
    print("[mini]", *a, flush=True)


def character_block() -> str:
    """miniature.md 의 첫 코드 블록(캐릭터 블록) — 사진 편집용으로 SCALE·PHOTOGRAPHY 문단만 바꾼다."""
    t = RULES.read_text(encoding="utf-8")
    m = re.search(r"## 1\. 캐릭터 블록.*?```\n(.*?)```", t, re.S)
    if not m:
        raise RuntimeError("miniature.md 에서 캐릭터 블록을 못 찾음")
    paras = [p for p in m.group(1).strip().split("\n\n") if not p.startswith(("SCALE:", "PHOTOGRAPHY:"))]
    return "\n\n".join(paras)


def edit_prompt(scene: str) -> str:
    return "\n\n".join([EDIT_HEAD, KEEP_LINE, character_block(), EDIT_SCALE, EDIT_PHOTO, "SCENE: " + scene.strip(), EDIT_TAIL])


def veo_prompt(motion: str) -> str:
    return " ".join([VEO_HEAD, "MOTION (4 seconds): " + motion.strip(), VEO_TAIL])


OMNI_HEAD = ("Use the attached image as the exact first frame of the video and animate from it. Total length: exactly 4 seconds. "
             "Audio: soft natural ambient sound of the place only — no dialogue, no voices, no music.")


def omni_prompt(motion: str) -> str:
    """옴니 플래시용 — 비오 지시문 + 첫 장면 고정·길이·소리 지시(옴니는 길이 필드가 없고 소리를 늘 만든다)."""
    return OMNI_HEAD + " " + veo_prompt(motion)


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
            try:
                data = _post(f"models/{model}:generateContent", body)
            except RuntimeError as e:
                last = e
                if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                    log(f"이미지 모델 {model} 사용 불가 → 다음:", str(e)[:140].replace("\n", " "))
                    break
                raise
            veo.record_est("image", krw, f"{model} 미니어처 합성 {out.name} (추정)")
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
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([x0 + feather, y0 + feather, x1 - feather, y1 - feather], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather / 2))
    Image.composite(b, a, mask).save(out, "PNG")
    # 경계 띠(안쪽 feather~2feather) 어긋남
    ga, gb = a.convert("L").filter(ImageFilter.GaussianBlur(1.5)), b.convert("L").filter(ImageFilter.GaussianBlur(1.5))
    pa, pb = ga.load(), gb.load()
    ring, bad = 0, 0
    for y in range(max(0, y0), min(H, y1), 3):
        for x in range(max(0, x0), min(W, x1), 3):
            d_edge = min(x - x0, x1 - x, y - y0, y1 - y)
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
    rep = {"nonce": req.get("nonce"), "started": datetime.now().isoformat(timespec="seconds"), "ok": False, "shots": [],
           "veo_model": veo.MODEL, "fake_veo": veo.FAKE, "fake_image": FAKE_IMG}
    if not (veo.FAKE and FAKE_IMG) and req.get("veo_approved") is not True:
        raise SystemExit('유료 시험은 운영자 허락이 필요합니다 — requests/mini/request.json 에 "veo_approved": true')
    models = [] if FAKE_IMG else image_models(req.get("image_model"))
    log("이미지 모델 후보:", models[:4])
    rows = []
    try:
        for s in req["shots"]:
            k = s["key"]
            row = {"key": k, "url": s["url"], "ok": False}
            rep["shots"].append(row)
            src = fetch(s["url"], BUILD / f"{k}_src.jpg")
            base = crop916(src, BUILD / f"{k}_base.jpg", float(s.get("focus_x", 0.5)), float(s.get("focus_y", 0.5)))
            ep = edit_prompt(s["scene"]); (BUILD / f"{k}_edit_prompt.txt").write_text(ep, encoding="utf-8")
            prev = ROOT / "build" / "mini_prev" / f"{k}_frame.png"                 # 이전 실행 아티팩트의 합성(돈 아끼기 · request "reuse_run_id")
            if req.get("reuse_run_id") and prev.exists():
                frame = BUILD / f"{k}_frame.png"; frame.write_bytes(prev.read_bytes()); row["reused_frame"] = int(req["reuse_run_id"])
                log(f"{k}: 이전 실행({req['reuse_run_id']})의 합성 장면 재사용 — 이미지 비용 0원")
            else:
                frame = composite(base, ep, BUILD / f"{k}_frame.png", models, rep)
            if s.get("box"):                                               # 인형 영역 밖은 원본으로 되돌림 → 배경 보존 보장
                frame, seam = paste_back(base, frame, s["box"], BUILD / f"{k}_frame_pb.png")
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
                vp = omni_prompt(motion); (BUILD / f"{k}_omni_prompt.txt").write_text(vp, encoding="utf-8")
                res = omni.make_clip(vp, frame, 4, clip, resolution=str(req.get("omni_resolution") or "720p"))
                row.update({"ok": True, "engine": "omni", "omni_krw": res["krw"], "clip_sec": res["sec"], "omni_model": res["model"], "tokens_out": res["tokens_out"]})
            else:
                vp = veo_prompt(motion); (BUILD / f"{k}_veo_prompt.txt").write_text(vp, encoding="utf-8")
                krw = veo.make_clip(vp, frame, 4, clip, veo.seed_for("mini", k), mime="image/png")
                row.update({"ok": True, "engine": "veo", "veo_krw": round(krw), "clip_sec": 4})
            row.update({"edit_prompt_chars": len(ep), "video_prompt_chars": len(vp)})
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
