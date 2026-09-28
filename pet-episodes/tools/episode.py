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
# ★목소리 규칙(사용자 확정 2026-09) — 한 곳에서만 정한다: 성우 1명 고정 · 연기 톤 고정 · 속도 1.2배.
#   Gemini 음성(사람 같은 연기)을 쓰고, 속도는 숫자 설정이 없어 만든 뒤 편집에서 정확히 1.2배로 맞춘다.
VOICE_NAME = "Algenib"                     # 사용자 확정(2026-09): 거친 저음. 바꾸지 않는다
VOICE_SPEED = 1.2
VOICE_DIRECTION = ("한국어 내레이션. 40대 남자의 낮고 차분한 속마음 독백이다. 혼자 밥을 먹으며 한 입씩 음미하는 "
                   "'고독한 미식가' 같은 톤. 겉은 담담하지만 맛있는 순간엔 진심이 살짝 묻어난다. "
                   "문장 사이에 짧게 숨을 고른다. 아나운서·광고 톤, 과장된 연기 금지. 아래 대사만 그대로 읽어라.")
VOICE_SAMPLES = ["Gacrux", "Charon", "Algenib", "Orus"]   # 후보: 성숙함 · 차분한 정보형 · 거친 저음 · 단단함
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
              "table and the seat, the lighting and the prop, exactly as described below. On the table sits {vessel}, empty. "
              "{style}\nSET: {set}\nNo text, letters, signs with writing, logos or watermarks. Full-frame image with no borders.")
KF_HEAD = ("Create the FIRST FRAME of one shot of a vertical 9:16 film. "
           "Reference image 1 is the main character: draw exactly this {noun} (same face, fur colours, markings and "
           "proportions), a natural four-legged animal with no clothes, no collar and no accessories. "
           "Reference image 2 is THE restaurant set: this shot happens inside exactly this room — the same door, walls, "
           "floor, the same table (same wood, shape and size) and seat, the same lamp and prop. Only the camera position "
           "and framing change, as given in SHOT. ")
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


def step_keyframes(ep, epdir, work, log, redo, character, setimg):
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
        r = gen_image(text + "\n\nSHOT DESCRIPTION:\n" + c["imagePrompt"] + KF_TAIL, refs, out)
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


def _veo(key, start: Path, prompt: str, setimg: Path | None = None) -> bytes:
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


CLIP_TAIL = ("\nThe first attached image is the FIRST FRAME. The second attached image (if any) is the empty restaurant set "
             "for reference: the room, door, walls, floor, table, seat, lamp and props must stay exactly like these images "
             "for the whole clip — nothing is added, removed, moved or reshaped. Only the camera and the character move, "
             "slowly and smoothly. The bowl and the food never change.\nSOUND: none needed (it will be replaced). No dialogue. "
             "NEVER SHOW: text, letters, numbers, logos, packaging, humans, banknotes or cash, the character changing shape, "
             "morphing objects, changing furniture, cuts.")


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
                out.write_bytes(fn(key, work / f"kf_{name}.png", prompt, work / "set.png"))
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
def _pcm_to_wav(pcm: bytes, out: Path, speed: float):
    raw = out.with_suffix(".pcm")
    raw.write_bytes(pcm)
    # 앞뒤 무음은 잘라 낸다(문장을 이어 붙일 때 간격이 제멋대로 벌어지지 않게) → 정확히 speed배속
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
    _ff(["-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(raw), "-af", f"{trim},atempo={speed}", str(out)])
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


def step_voices(ep, epdir, work, log):
    """성우 고르기용 샘플 — 같은 대사를 후보 목소리마다 1.2배속으로 읽힌다(mp3로 저장해 바로 들을 수 있게)."""
    lines = [c["line"] for c in ep["clips"] if c.get("role") in ("order", "taste")][:2]
    text = " ".join(lines) or ep["clips"][0]["line"]
    res = log.setdefault("voices", {})
    for v in VOICE_SAMPLES:
        wav = work / f"voice_{v}.wav"
        r = tts_gemini(text, wav, v)
        if r["ok"]:
            _ff(["-i", str(wav), "-b:a", "128k", str(work / f"voice_{v}.mp3")])
            wav.unlink()
        res[v] = r
    log["voices_text"] = text


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


def step_tts(ep, epdir, work, log, redo):
    """문장마다 따로 읽혀 이어 붙인다 → 각 문장이 몇 초에 시작·끝나는지 정확히 안다(자막을 말에 딱 맞추기 위해)."""
    res = log.setdefault("tts", {})
    for c in ep["clips"]:
        name = f"c{c['no']:02d}"
        out, tj = work / f"v_{name}.wav", work / f"v_{name}.json"
        line = (c.get("line") or "").strip()
        if not line or (out.exists() and tj.exists() and name not in redo and f"v_{name}" not in redo):
            continue
        parts, timing, t, rec = [], [], 0.0, {"voice": VOICE_NAME, "sents": []}
        for k, sent in enumerate(split_sentences(line)):
            p = work / f"v_{name}_{k}.wav"
            r = tts_gemini(sent, p)
            if not r["ok"]:
                r = {"gemini": r, **tts_cloud(sent, p)}
            rec["sents"].append(r)
            if not p.exists():
                continue
            d = _dur(p)
            timing.append({"text": sent, "start": round(t, 3), "end": round(t + d, 3)})
            parts.append(p)
            t += d + SENT_GAP
        if not parts:
            res[name] = {**rec, "ok": False}
            continue
        ins, fc = [], []
        for i, p in enumerate(parts):
            ins += ["-i", str(p)]
            fc.append(f"[{i}:a]aresample=24000,aformat=channel_layouts=mono,apad=pad_dur={SENT_GAP if i < len(parts) - 1 else 0}[s{i}]")
        fc.append("".join(f"[s{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[a]")
        _ff([*ins, "-filter_complex", ";".join(fc), "-map", "[a]", str(out)])
        tj.write_text(json.dumps(timing, ensure_ascii=False, indent=1), encoding="utf-8")
        for p in parts:
            p.unlink()
        res[name] = {**rec, "ok": True, "sec": round(_dur(out), 2)}


# ---------- 5. 조립 ----------
FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
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


def _seal(dr, x, y, s, text="품격"):
    """붉은 낙관(도장) — 이모지 대신 직접 그린 도형."""
    dr.rounded_rectangle([x, y, x + s, y + s], radius=6, fill=SEAL + (235,))
    f = _f(SERIF_XB, int(s * 0.36))
    for i, ch in enumerate(text):
        dr.text((x + (s - f.getlength(ch)) / 2, y + s * 0.10 + i * s * 0.42), ch, font=f, fill=(255, 240, 230, 255))


def menu_png(name, out: Path):
    """오늘의 메뉴 — 한지 느낌 크림색 종이 + 이중 테두리 + 명조 + 붉은 낙관. 메뉴 이름만(상품명·사진 금지)."""
    bw, bh = 560, 300
    x0, y0 = (W - bw) // 2, 150
    ft, fn = _f(SERIF_B, 28), _f(SERIF_XB, 50)
    lines = _balanced(name, fn, bw - 120)[:2]

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
            dr.text(((W - fn.getlength(ln)) / 2, top + i * 66), ln, font=fn, fill=INK + (255,))
        _seal(dr, x0 + bw - 76, y0 + bh - 96, 56)
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
    for ln in _balanced(ep.get("menuName", ""), fx, pw - 80)[:2]:
        c(ln, fx, y)
        y += 50
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
    if ep.get("priceNote"):
        y += 8
        c(ep["priceNote"], fm, y)
        y += 44
    if ep.get("guestNote"):
        c(ep["guestNote"], fs, y + 4, (120, 104, 88))
        y += 40
    dots(ph - 190)
    c("이 메뉴는", fl, ph - 160)
    c("프로필 링크에서", fl, ph - 100)
    if seal_y:                                       # 붉은 '완식' 낙관 — 음식 사진 오른쪽 아래 모서리에 찍는다
        _seal(ImageDraw.Draw(paper), pw - 128, seal_y, 78, "완식")
    paper = paper.rotate(-1.5, resample=Image.BICUBIC, expand=True)
    sh = Image.new("RGBA", paper.size, (0, 0, 0, 0))
    sh.putalpha(paper.split()[3].point(lambda v: v * 150 // 255).filter(ImageFilter.GaussianBlur(16)))
    im.alpha_composite(sh, (x0 - 6, y0 + 14))
    im.alpha_composite(paper, (x0 - 10, y0))
    im.convert("RGB").save(out, quality=95)


# 컷 사이 전환(다음 컷의 역할별). 너무 요란하지 않게 드라마식으로.
TRANSITIONS = {"order": "fadeblack", "serve": "smoothleft", "taste": "dissolve", "bill": "smoothup",
               "exit": "fadeblack", "outro": "fade"}
XF = 0.4
LEAD = 0.45              # 컷 시작 후 대사가 시작되기까지(초)
TAIL = 0.75              # 대사가 끝난 뒤 다음 컷까지 여유(초)


def _zoom_expr(role, idx, L):
    """컷 안의 카메라 느낌(편집): 천천히 밀고 들어가거나 빠지는 줌을 번갈아. 입장은 끝에서 세 번 끊어 빠지는 줌."""
    if role == "enter":
        return (f"if(lt(it,{L - 1.2:.2f}),1+0.05*it/{L:.2f},if(lt(it,{L - 0.8:.2f}),1.45,"
                f"if(lt(it,{L - 0.4:.2f}),1.28,1.13)))")
    if idx % 2:
        return f"1.10-0.10*it/{L:.2f}"
    return f"1+0.09*it/{L:.2f}"


def _overlay_input(png: Path, L: float, a: float, b: float, fade=0.25):
    return (["-loop", "1", "-t", f"{L:.2f}", "-i", str(png)],
            f"format=rgba,fade=in:st={max(0, a):.2f}:d={fade}:alpha=1,fade=out:st={max(0, b - fade):.2f}:d={fade}:alpha=1")


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
    L = max(V, LEAD + N + TAIL)
    slow = min(1.3, L / V)
    a0 = max(0.3, L - N - 0.35) if role == "enter" else LEAD   # 입장: 오프닝이 끝의 줌과 겹치게
    ins, fcs, labels = [], [], []
    ins += ["-i", str(src)]
    z = _zoom_expr(role, idx, L)
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
    elif card.get("type") == "bill" and card.get("text"):
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
    return seg, L, {"clip": name, "len": round(L, 2), "voice": round(N, 2), "slow": round(slow, 3)}


def step_assemble(ep, epdir, work, log):
    tmp = work / "tmp"
    tmp.mkdir(exist_ok=True)
    food = next((p for p in (epdir / "refs" / "food.jpg", epdir / "refs" / "food.png") if p.exists()), None)
    segs, lens, roles, info = [], [], [], []
    for idx, c in enumerate(ep["clips"]):
        seg, L, meta = build_segment(ep, c, idx, work, tmp)
        segs.append(seg); lens.append(L); roles.append(c.get("role")); info.append(meta)
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
    total = _dur(final)
    _ff(["-i", str(final), "-vf", f"fps={len(segs)}/{total:.2f},scale=180:-2,tile={len(segs)}x1:margin=4:padding=4:color=white",
         "-frames:v", "1", str(work / "frames.jpg")])
    log["assemble"] = {"ok": True, "sec": round(total, 2), "clips": len(segs) - 1, "segments": info}
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
        if "voices" in steps:
            step_voices(ep, epdir, work, log)
        character = step_character(ep, epdir, work, log, redo)
        if "keyframes" in steps:
            setimg = step_set(ep, epdir, work, log, redo)
            step_keyframes(ep, epdir, work, log, redo, character, setimg)
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
