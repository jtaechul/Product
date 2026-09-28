"""반려동물 식당 에피소드(「한 그릇의 품격」) 자동 제작 — 심해 v2(short-movie-generator/v2) 절차를 옮겨 온 것.

절차: 캐릭터 참고 이미지 → 컷별 첫 장면(이미지 AI, 캐릭터·실제 음식·가게 참고) → 첫 장면에서 8초 영상(Omni Flash,
실패 시 Veo Lite) → 한국어 내레이션(Google TTS) → 조립(자막·메뉴판·계산서·오프닝 줌·영수증 아웃트로).

사용: python episode.py <에피소드 폴더>/requests/<요청>.json
요청: {"id": "...", "steps": ["character","keyframes","clips","tts","assemble"], "redo": ["c03"]}
  - 에피소드 폴더에는 episode.json(관리자 페이지 '프롬프트 만들기' 결과)과 refs/food.png(음식 참고 이미지)가 있다.
  - 결과는 work/에 쌓이고, 이미 있는 결과는 다시 만들지 않는다(비용 절약). 다시 뽑을 컷은 redo에 적는다.
보안: 키는 환경변수(GEMINI_API_KEY, GOOGLE_TTS_KEY)로만 받고 출력하지 않는다.
규칙(book-carousel CLAUDE.md): 상품명·포장은 영상에 넣지 않는다 · 가격은 100g당만 · 영상 AI 소리는 버린다.
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
TTS_VOICE = {"languageCode": "ko-KR", "name": "ko-KR-Neural2-C"}   # 낮은 남성 목소리 — 담담한 독백
TTS_RATE, TTS_PITCH = "105%", "-2st"
FONT_CANDIDATES = [("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),   # index 1 = KR
                   ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0)]

CHARACTER_PROMPTS = {
    "dog": "A photorealistic 3D animated style full-body portrait of an ultra-cute Shiba Inu puppy standing naturally on all "
           "four legs, three-quarter view, oversized round head with chubby cheeks, huge round sparkling dark brown eyes, "
           "a small playful smile, soft plush-like golden-cream and snow-white fur, absolutely no black hairs or mask, "
           "natural body with no clothes, no collar and no accessories, unbelievably fluffy soft texture, soft even studio "
           "lighting, plain light grey background, clean 3D rendering. No text.",
    "cat": "A photorealistic 3D animated style full-body portrait of an ultra-cute kitten standing naturally on all four legs, "
           "three-quarter view, oversized round head with chubby cheeks, huge round sparkling eyes, a tiny pink nose, soft "
           "plush-like cream and snow-white fur, natural body with no clothes, no collar and no accessories, unbelievably "
           "fluffy soft texture, soft even studio lighting, plain light grey background, clean 3D rendering. No text.",
}


# ---------- 공용 ----------
def _http(url, data=None, headers=None, timeout=300):
    req = urllib.request.Request(url, data=data, headers=headers or {})
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


def gen_image(prompt: str, refs: list[Path], out: Path, aspect="9:16") -> dict:
    key = _key("GEMINI_API_KEY")
    model = _pick_model(key, IMAGE_MODELS)
    parts = [{"inline_data": _b64img(r)} for r in refs] + [{"text": prompt}]
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
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
    if out.exists() and "character" not in redo:
        return out
    r = gen_image(CHARACTER_PROMPTS.get(ep.get("species", "dog"), CHARACTER_PROMPTS["dog"]), [], out, "1:1")
    log["character"] = r
    if not r["ok"]:
        raise RuntimeError(f"캐릭터 이미지 실패: {r.get('error')}")
    return out


# ---------- 2. 컷별 첫 장면 ----------
KF_HEAD = ("Create the FIRST FRAME of one shot of a vertical 9:16 animated short film. "
           "Reference image 1 is the main character: draw exactly this {noun} (same face, fur colours, proportions and cute "
           "style), a natural four-legged animal with no clothes, no collar and no accessories. ")
KF_FOOD = ("Reference image {n} is the real food: draw exactly these food pieces (same shape, size, colour and texture) in a "
           "plain white bowl or plate. Never show any packaging or bag. ")
KF_SET = ("Reference image {n} is the same restaurant from an earlier shot: keep the same room, the same single door, walls, "
          "floor, table, seat and lighting. ")
KF_TAIL = ("\nNo text, letters, numbers, signs with writing, logos or watermarks anywhere. No humans. "
           "Full-frame image with no borders.")


def step_keyframes(ep, epdir, work, log, redo, character):
    food = next((p for p in (epdir / "refs" / "food.png", epdir / "refs" / "food.jpg") if p.exists()), epdir / "refs" / "food.png")
    noun = "kitten" if ep.get("species") == "cat" else "puppy"
    first = None
    res = log.setdefault("keyframes", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out = work / f"kf_{name}.png"
        if out.exists() and f"kf_{name}" not in redo:
            first = first or out
            continue
        refs, text = [character], KF_HEAD.format(noun=noun)
        if "FOOD:" in c.get("prompt", "") and food.exists():
            refs.append(food)
            text += KF_FOOD.format(n=len(refs))
        if first is not None:
            refs.append(first)
            text += KF_SET.format(n=len(refs))
        r = gen_image(text + "\n\nSHOT DESCRIPTION:\n" + c["imagePrompt"] + KF_TAIL, refs, out)
        res[name] = r
        if r["ok"] and first is None:
            first = out
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


def _omni(key, start: Path, prompt: str) -> bytes:
    hdr = {"x-goog-api-key": key, "Content-Type": "application/json"}
    body = {"model": CLIP_MODEL,
            "input": [{"type": "image", **_b64img(start)}, {"type": "text", "text": prompt}],
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


def _veo(key, start: Path, prompt: str) -> bytes:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    op = client.models.generate_videos(
        model=VEO_FALLBACK, prompt=prompt,
        image=types.Image(image_bytes=start.read_bytes(), mime_type="image/png"),
        config=types.GenerateVideosConfig(aspect_ratio="9:16", resolution="720p", duration_seconds=8, number_of_videos=1))
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


CLIP_TAIL = ("\nThe attached image is the FIRST FRAME: keep every object's shape, size, colour and position consistent with it, "
             "and keep the character exactly as drawn.\nSOUND: none needed (it will be replaced). No dialogue. "
             "NEVER SHOW: text, letters, numbers, logos, packaging, humans, the character changing shape, morphing objects, cuts.")


def step_clips(ep, epdir, work, log, redo):
    key = _key("GEMINI_API_KEY")
    res = log.setdefault("clips", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out = work / f"{name}.mp4"
        if out.exists() and name not in redo:
            continue
        prompt = c["prompt"] + CLIP_TAIL
        rec = {"attempts": []}
        for label, fn in (("omni", _omni), ("veo-lite", _veo)):
            t0 = time.time()
            try:
                out.write_bytes(fn(key, work / f"kf_{name}.png", prompt))
                rec["attempts"].append({"model": label, "ok": True, "wait_s": round(time.time() - t0, 1)})
                rec["model"], rec["sec"] = label, round(_dur(out), 2)
                break
            except Exception as e:  # noqa: BLE001
                rec["attempts"].append({"model": label, "ok": False, "error": str(e)[:300]})
        res[name] = rec
    missing = [f"c{c['no']:02d}" for c in ep["clips"] if not (work / f"c{c['no']:02d}.mp4").exists()]
    if missing:
        raise RuntimeError(f"영상 실패: {missing}")


# ---------- 4. 내레이션 ----------
def step_tts(ep, epdir, work, log, redo):
    key = _key("GOOGLE_TTS_KEY")
    res = log.setdefault("tts", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out = work / f"v_{name}.wav"
        line = (c.get("line") or "").strip()
        if not line or (out.exists() and name not in redo and f"v_{name}" not in redo):
            continue
        ssml = f'<speak><prosody rate="{TTS_RATE}" pitch="{TTS_PITCH}">{line}</prosody></speak>'
        body = {"input": {"ssml": ssml}, "voice": TTS_VOICE,
                "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": 24000}}
        code, raw = _http("https://texttospeech.googleapis.com/v1/text:synthesize", json.dumps(body).encode(),
                          {"x-goog-api-key": key, "Content-Type": "application/json"})
        if code != 200:
            res[name] = {"ok": False, "error": raw[:300].decode("utf-8", "replace")}
            continue
        out.write_bytes(base64.b64decode(json.loads(raw)["audioContent"]))
        res[name] = {"ok": True, "sec": round(_dur(out), 2)}


# ---------- 5. 조립 ----------
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


def subtitle_png(text, out: Path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = _font(44)
    lines = _wrap(text, f, W - 120)
    lh = 60
    y = int(H * 0.80) - lh * len(lines) // 2
    dr = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        tw = f.getlength(ln)
        x = (W - tw) / 2
        dr.rounded_rectangle([x - 18, y + i * lh - 6, x + tw + 18, y + i * lh + lh - 4], radius=10, fill=(0, 0, 0, 150))
        dr.text((x, y + i * lh), ln, font=f, fill=(255, 255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    im.save(out)


def title_png(series, epno, out: Path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    f1, f2 = _font(30), _font(52)
    dr.text((40, 70), f"{series}", font=f1, fill=(255, 236, 200, 235), stroke_width=2, stroke_fill=(0, 0, 0, 160))
    if epno:
        dr.text((40, 108), f"#{epno}", font=f2, fill=(255, 255, 255, 245), stroke_width=3, stroke_fill=(0, 0, 0, 170))
    im.save(out)


def menu_png(name, out: Path):
    """나무 메뉴판 — 메뉴 이름만(상품명·사진 금지)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    bw, bh = 560, 250
    x0, y0 = (W - bw) // 2, 150
    dr.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=18, fill=(62, 40, 24, 238), outline=(150, 110, 70, 255), width=6)
    fh, fn = _font(30), _font(46)
    t = "오늘의 메뉴"
    dr.text(((W - fh.getlength(t)) / 2, y0 + 30), t, font=fh, fill=(235, 200, 140, 255))
    lines = _wrap(name, fn, bw - 70)[:2]
    for i, ln in enumerate(lines):
        dr.text(((W - fn.getlength(ln)) / 2, y0 + 92 + i * 62 - (31 if len(lines) == 1 else 0) + 30), ln, font=fn,
                fill=(255, 246, 225, 255))
    im.save(out)


def bill_png(text, out: Path):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    bw, bh = 520, 210
    x0, y0 = (W - bw) // 2, 160
    dr.rounded_rectangle([x0, y0, x0 + bw, y0 + bh], radius=10, fill=(252, 250, 244, 245), outline=(200, 195, 185, 255), width=3)
    fh, fb = _font(30), _font(44)
    dr.text(((W - fh.getlength("계산서")) / 2, y0 + 26), "계산서", font=fh, fill=(90, 80, 70, 255))
    dr.line([x0 + 40, y0 + 78, x0 + bw - 40, y0 + 78], fill=(190, 180, 170, 255), width=2)
    for i, ln in enumerate(_wrap(text, fb, bw - 60)[:2]):
        dr.text(((W - fb.getlength(ln)) / 2, y0 + 100 + i * 56), ln, font=fb, fill=(30, 28, 26, 255))
    im.save(out)


def receipt_png(ep, out: Path):
    im = Image.new("RGB", (W, H), (26, 22, 20))
    dr = ImageDraw.Draw(im)
    x0, y0, x1, y1 = 90, 170, W - 90, H - 190
    dr.rectangle([x0, y0, x1, y1], fill=(250, 248, 242))
    for x in range(x0, x1, 24):          # 톱니 가장자리
        dr.polygon([(x, y1), (x + 12, y1 + 14), (x + 24, y1)], fill=(250, 248, 242))
    c = lambda t, f, y, col=(40, 36, 32): dr.text(((W - f.getlength(t)) / 2, y), t, font=f, fill=col)
    fs, fm, fl = _font(28), _font(34), _font(46)
    c("영 수 증", fl, y0 + 50)
    c(f"{ep.get('series', '')}" + (f"  #{ep['episode']}" if ep.get("episode") else ""), fs, y0 + 120, (110, 100, 90))
    dr.line([x0 + 40, y0 + 180, x1 - 40, y0 + 180], fill=(180, 170, 160), width=2)
    y = y0 + 220
    for ln in _wrap(ep.get("menuName", ""), fm, x1 - x0 - 80)[:2]:
        c(ln, fm, y)
        y += 50
    if ep.get("priceNote"):
        c(ep["priceNote"], fm, y + 20)
        y += 70
    if ep.get("guestNote"):
        for ln in _wrap(ep["guestNote"], fs, x1 - x0 - 80)[:2]:
            c(ln, fs, y + 20, (90, 82, 74))
            y += 42
    dr.line([x0 + 40, y1 - 250, x1 - 40, y1 - 250], fill=(180, 170, 160), width=2)
    c("이 메뉴는", fl, y1 - 200)
    c("프로필 링크에서", fl, y1 - 130)
    im.save(out)


def step_assemble(ep, epdir, work, log):
    tmp = work / "tmp"
    tmp.mkdir(exist_ok=True)
    segs = []
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        src = work / f"{name}.mp4"
        D = min(8.0, _dur(src)) or 8.0
        voice = work / f"v_{name}.wav"
        vd = _dur(voice) if voice.exists() else 0.0
        role = c.get("role")
        # 입장 대사는 끝의 줌과 함께, 나머지는 조금 뒤에 시작. 대사가 컷 밖으로 넘지 않게 당긴다.
        at = (D - vd - 0.3) if role == "enter" else 0.7
        at = max(0.2, min(at, D - vd - 0.15))
        overlays = []                       # (png, from, to)
        if c.get("subtitle") or c.get("line"):
            p = tmp / f"sub_{name}.png"
            subtitle_png(c.get("subtitle") or c["line"], p)
            overlays.append((p, at, min(D, at + max(vd, 1.6) + 0.35)))
        card = c.get("card") or {}
        if card.get("type") == "menu" and card.get("name"):
            p = tmp / f"menu_{name}.png"
            menu_png(card["name"], p)
            overlays.append((p, 0.6, D))
        elif card.get("type") == "bill" and card.get("text"):
            p = tmp / f"bill_{name}.png"
            bill_png(card["text"], p)
            overlays.append((p, 0.6, D))
        if role == "enter":
            p = tmp / "title.png"
            title_png(ep.get("series", ""), ep.get("episode"), p)
            overlays.append((p, 0.3, min(D, 3.6)))
        # 영상: 9:16 맞춤 + (입장) 끝에서 세 번 끊어 뒤로 빠지는 줌
        base = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
        if role == "enter":
            z = (f"if(lt(t,{D - 1.2:.2f}),1,if(lt(t,{D - 0.8:.2f}),1.45,if(lt(t,{D - 0.4:.2f}),1.28,1.13)))")
            base += (f",scale=w='trunc({W}*{z}/2)*2':h='trunc({H}*{z}/2)*2':eval=frame,crop={W}:{H}")
        inputs = ["-i", str(src)]
        for p, _, _ in overlays:
            inputs += ["-i", str(p)]
        fc = [f"[0:v]trim=0:{D:.2f},setpts=PTS-STARTPTS,{base}[v0]"]
        last = "v0"
        for i, (_, a, b) in enumerate(overlays, start=1):
            fc.append(f"[{last}][{i}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[v{i}]")
            last = f"v{i}"
        n = len(overlays) + 1
        if voice.exists():
            inputs += ["-i", str(voice)]
            ms = int(at * 1000)
            fc.append(f"[{n}:a]aresample=44100,aformat=channel_layouts=stereo,adelay={ms}|{ms},apad,atrim=0:{D:.2f},"
                      f"volume=1.6[a]")
        else:
            inputs += ["-f", "lavfi", "-t", f"{D:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
            fc.append(f"[{n}:a]atrim=0:{D:.2f}[a]")
        seg = tmp / f"seg_{name}.mp4"
        _ff([*inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[a]", "-t", f"{D:.2f}",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-ar", "44100", str(seg)])
        segs.append(seg)
    # 영수증 아웃트로 2.6초
    rp = tmp / "receipt.png"
    receipt_png(ep, rp)
    outro = tmp / "seg_outro.mp4"
    _ff(["-loop", "1", "-t", "2.6", "-i", str(rp), "-f", "lavfi", "-t", "2.6", "-i", "anullsrc=r=44100:cl=stereo",
         "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-c:a", "aac", "-b:a", "160k", "-shortest", str(outro)])
    segs.append(outro)
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{s.resolve()}'\n" for s in segs), encoding="utf-8")
    final = work / "final.mp4"
    _ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(final)])
    # 점검용 장면 모음(컷마다 중간 1장 + 아웃트로)
    total = _dur(final)
    _ff(["-i", str(final), "-vf", f"fps={len(segs)}/{total:.2f},scale=180:-2,tile={len(segs)}x1:margin=4:padding=4:color=white",
         "-frames:v", "1", str(work / "frames.jpg")])
    log["assemble"] = {"ok": True, "sec": round(total, 2), "clips": len(segs) - 1}
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()


def main(path: str) -> int:
    rp = Path(path)
    req = json.loads(rp.read_text(encoding="utf-8"))
    epdir = rp.parent.parent
    ep = json.loads((epdir / "episode.json").read_text(encoding="utf-8"))
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
        character = step_character(ep, epdir, work, log, redo)
        if "keyframes" in steps:
            step_keyframes(ep, epdir, work, log, redo, character)
        if "clips" in steps:
            step_clips(ep, epdir, work, log, redo)
        if "tts" in steps:
            step_tts(ep, epdir, work, log, redo)
        if "assemble" in steps:
            step_assemble(ep, epdir, work, log)
    except Exception as e:  # noqa: BLE001
        log["error"] = str(e)[:500]
        ok = False
    log["last_request"] = {"file": rp.name, "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ok": ok}
    logp.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(log, ensure_ascii=False)[:3000])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
