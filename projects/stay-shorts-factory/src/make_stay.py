#!/usr/bin/env python3
"""숙소 이름 1개 → 세로 영상 1편 (시험 제작판).

    python3 src/make_stay.py            requests/produce/request.json 을 읽는다

흐름
  1) 쿠팡 파트너스 검색 API 로 숙소 이름을 검색한다 (객실 목록·사진·제휴 링크가 같이 온다)
  2) Gemini 가 '이 숙소의 객실'만 골라내고(패키지 여행·입장권 제외) 대본을 쓴다
  3) Gemini 음성으로 나레이션을 만든다
  4) 객실 사진에 움직임(확대)을 주고 자막을 얹어 ffmpeg 로 합친다
  5) build/video.mp4 · meta.json · 미리보기 사진을 남긴다

기존 자산 재사용
  - Gemini 글·음성 호출 형식: projects/coupang-shorts-factory 의 generate.py · tts.py 에서 검증된 것
  - 글꼴: projects/coupang-shorts-factory/assets/fonts/GmarketSansBold.ttf (상업적 사용 허용)
  - 쿠팡 서명·경로: scripts/coupang_probe.py 로 2026-10-09 실측한 것

규칙 (CLAUDE.md)
  - 스크래핑 없음. 사진은 쿠팡 API 가 준 것만 쓴다. 제휴 링크를 따라가지 않는다.
  - 대본은 객실 이름에 적힌 사실만 쓴다. 가격 숫자·'최고/유일' 같은 단정 표현 금지.
  - 제휴 고지문은 화면과 캡션 첫 줄에 항상 들어간다.
  - 유료 영상 생성(Veo)은 이 파일에 없다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
REQUEST = ROOT / "requests" / "produce" / "request.json"
FONT_CANDIDATES = [
    ROOT.parent / "coupang-shorts-factory" / "assets" / "fonts" / "GmarketSansBold.ttf",
    ROOT / "assets" / "fonts" / "GmarketSansBold.ttf",
]

DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다"
W, H, FPS = 1080, 1920, 30
BANNED = ["최고", "유일", "100%", "무조건", "보장", "최저가", "1위", "완벽"]

COUPANG = "https://api-gateway.coupang.com"
SEARCH_PATH = "/v2/providers/affiliate_open_api/apis/openapi/products/search"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"


def log(*a):
    print("[stay]", *a, flush=True)


# ── 쿠팡 ───────────────────────────────────────────────────────────────
def coupang_search(keyword: str, limit: int = 10) -> list:
    access = os.environ.get("COUPANG_ACCESS_KEY", "").strip()
    secret = os.environ.get("COUPANG_SECRET_KEY", "").strip()
    if not access or not secret:
        raise RuntimeError("쿠팡 키가 실행 환경에 없습니다 (COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY)")
    query = urllib.parse.urlencode({"keyword": keyword, "limit": min(limit, 10)})
    signed = time.strftime("%y%m%dT%H%M%SZ", time.gmtime())
    sig = hmac.new(secret.encode(), (signed + "GET" + SEARCH_PATH + query).encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(f"{COUPANG}{SEARCH_PATH}?{query}", headers={
        "Authorization": f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={signed}, signature={sig}",
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        js = json.loads(r.read().decode("utf-8"))
    if str(js.get("rCode")) != "0":
        raise RuntimeError(f"쿠팡 검색 실패 rCode={js.get('rCode')} {str(js.get('rMessage'))[:120]}")
    return (js.get("data") or {}).get("productData") or []


# ── Gemini ─────────────────────────────────────────────────────────────
def _gkey() -> str:
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    return k


def _gpost(path: str, body: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(f"{GEMINI}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": _gkey(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini 오류 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def pick_models() -> dict:
    """모델 이름은 자주 바뀐다 — 지금 이 키로 쓸 수 있는 것을 물어서 고른다 (판결극장과 같은 원칙)."""
    names = []
    try:
        req = urllib.request.Request(f"{GEMINI}/models?pageSize=200", headers={"x-goog-api-key": _gkey()})
        with urllib.request.urlopen(req, timeout=30) as r:
            names = [m.get("name", "").split("/", 1)[-1] for m in json.loads(r.read().decode()).get("models", [])]
    except Exception as e:  # noqa: BLE001
        log("모델 목록 조회 실패 → 기본 이름 사용:", str(e)[:100])

    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0

    bad = ("tts", "image", "live", "audio", "embed", "veo", "omni", "lyria", "robotics", "computer")
    text = [n for n in names if n.startswith("gemini-") and "flash" in n and not any(x in n for x in bad)]
    # 새 버전 먼저, 같은 버전이면 이름이 짧은(정식판) 것 먼저. 'lite' 는 뒤로.
    text.sort(key=lambda n: (-ver(n), "lite" in n, "preview" in n or "exp" in n, len(n)))
    tts = [n for n in names if "tts" in n]
    tts.sort(key=lambda n: (-ver(n), "flash" not in n, len(n)))
    return {"text": (text or ["gemini-2.5-flash"])[:6],
            "tts": (tts or ["gemini-2.5-flash-preview-tts"])[:5]}


USED = {}


def _try_models(kind: str, models: list, fn):
    """목록에 있어도 이 키로는 못 쓰는 모델이 있다(실측: 2.5-flash 404). 되는 것이 나올 때까지 넘긴다."""
    last = None
    for m in models:
        try:
            out = fn(m)
            USED[kind] = m
            return out
        except RuntimeError as e:
            last = e
            if any(c in str(e) for c in ("HTTP 404", "HTTP 400", "HTTP 403")):
                log(f"{kind} 모델 {m} 사용 불가 → 다음:", str(e)[:110].replace("\n", " "))
                continue
            raise
    raise RuntimeError(f"쓸 수 있는 {kind} 모델이 없음: {last}")


def gemini_json(model: str, system: str, content: str) -> dict:
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": content}]}],
            "generationConfig": {"maxOutputTokens": 3000, "temperature": 0.9,
                                 "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = _gpost(f"models/{model}:generateContent", body, 90)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig")      # 사고 끄기를 안 받는 모델
        data = _gpost(f"models/{model}:generateContent", body, 90)
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    txt = "".join(p.get("text", "") for p in parts).strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip()).strip()
    return json.loads(txt)


def gemini_tts(model: str, text: str, voice: str, style: str, out_wav: Path) -> float:
    body = {"contents": [{"parts": [{"text": f"{style}:\n{text}"}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    last = None
    for attempt in range(3):
        try:
            data = _gpost(f"models/{model}:generateContent", body, 180)
            parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
            inline = next((p.get("inlineData") for p in parts if p.get("inlineData")), None)
            if not inline or not inline.get("data"):
                raise RuntimeError(f"음성 응답에 오디오 없음: {str(data)[:160]}")
            pcm = base64.b64decode(inline["data"])
            m = re.search(r"rate=(\d+)", inline.get("mimeType", "") or "")
            rate = int(m.group(1)) if m else 24000
            with wave.open(str(out_wav), "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(rate); wf.writeframes(pcm)
            return len(pcm) / 2 / rate
        except Exception as e:  # noqa: BLE001
            last = e
            if any(c in str(e) for c in ("HTTP 404", "HTTP 400", "HTTP 403")):
                raise RuntimeError(str(e))
            log(f"음성 시도 {attempt + 1} 실패:", str(e)[:160])
            time.sleep(4)
    raise RuntimeError(f"음성 생성 실패: {last}")


# ── 대본 ───────────────────────────────────────────────────────────────
SYSTEM = """너는 숙소 소개 숏폼(세로 30초) 대본 작가다. 한국어 존댓말 구어체로 쓴다.
입력: 숙소 이름과, 쿠팡 검색 결과 목록(번호·상품명·가격).
할 일
1) 목록에서 '이 숙소의 객실 상품'만 고른다. 항공 포함 패키지 여행, 입장권·이용권·투어, 다른 숙소로 보이는 것은 제외한다.
2) 고른 객실 이름에 실제로 적힌 사실(전망, 자쿠지, 조식 포함, 평수, 인원, 반려동물 등)과 숙소 이름만 근거로 대본을 쓴다.
절대 규칙
- 목록에 없는 시설·서비스·위치 정보를 지어내지 않는다. 모르면 말하지 않는다.
- 가격 숫자, 할인율, '최고' '유일' '최저가' '1위' '완벽' '보장' 같은 단정 표현을 쓰지 않는다.
- 이모지·특수기호·영어 남용 금지.
- hook: 12~20자, 보는 사람이 자기 상황을 떠올리게 하는 한 문장(명령형 금지).
- lines: 정확히 5줄. 한 줄 18~32자. 5줄이 하나의 흐름으로 이어진다. 마지막 줄은 "예약 링크는 프로필에 있어요"처럼 프로필로 안내한다.
- hook + lines 전체는 공백 제외 120~165자.
- image_for_line: 길이 6 (hook, 5줄 순서). 각 값은 고른 객실의 번호. 그 줄 내용과 가장 맞는 객실을 고르고 가능하면 서로 다른 번호를 쓴다.
- title: 유튜브 제목 12~25자. caption: 인스타 캡션 본문 2~3문장(고지문은 넣지 않는다 — 시스템이 붙인다). hashtags: '#'으로 시작하는 태그 5개.
JSON 만 출력한다:
{"rooms":[번호...],"excluded":[{"i":번호,"reason":"..."}],"hook":"...","lines":["...","...","...","...","..."],"image_for_line":[n,n,n,n,n,n],"title":"...","caption":"...","hashtags":["#..."]}"""


def check_script(s: dict, n_items: int) -> list:
    errs = []
    lines = [str(s.get("hook", ""))] + [str(x) for x in (s.get("lines") or [])]
    if len(lines) != 6 or not all(x.strip() for x in lines):
        errs.append("hook 1줄 + lines 5줄이 아니다")
    rooms = [i for i in (s.get("rooms") or []) if isinstance(i, int) and 0 <= i < n_items]
    if len(rooms) < 2:
        errs.append("이 숙소의 객실로 고른 것이 2개 미만이다")
    ifl = s.get("image_for_line") or []
    if len(ifl) != 6 or any(i not in rooms for i in ifl):
        errs.append("image_for_line 은 길이 6이고 모두 rooms 안의 번호여야 한다")
    joined = "".join(lines) + str(s.get("title", "")) + str(s.get("caption", ""))
    for b in BANNED:
        if b in joined:
            errs.append(f"금지 표현 '{b}'")
    if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", joined):
        errs.append("가격·할인율 숫자가 들어 있다")
    n = len(re.sub(r"\s", "", "".join(lines)))
    if not 95 <= n <= 190:
        errs.append(f"분량 {n}자 (공백 제외 120~165자여야 한다)")
    return errs


def write_script(model: str, stay: str, items: list) -> dict:
    listing = "\n".join(f"{i}. {str(it.get('productName', ''))[:70]} / {it.get('productPrice')}원"
                        for i, it in enumerate(items))
    content = f"숙소 이름: {stay}\n\n쿠팡 검색 결과:\n{listing}"
    errs = []
    for attempt in range(3):
        extra = ("\n\n직전 답의 문제(고쳐서 다시): " + " / ".join(errs)) if errs else ""
        s = gemini_json(model, SYSTEM, content + extra)
        errs = check_script(s, len(items))
        if not errs:
            return s
        log(f"대본 검사 실패({attempt + 1}):", errs)
    raise RuntimeError("대본이 규칙을 통과하지 못함: " + " / ".join(errs))


# ── 그림·영상 ──────────────────────────────────────────────────────────
def font_path() -> str:
    for p in FONT_CANDIDATES:
        if p.exists():
            return str(p)
    raise RuntimeError("글꼴 파일을 찾지 못함 (GmarketSansBold.ttf)")


def wrap(draw, text, font, max_w):
    out, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            out.append(cur); cur = word
    if cur:
        out.append(cur)
    return out


def make_overlay(path: Path, stay: str, caption: str, is_hook: bool):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fp = font_path()
    # 위: 숙소 이름
    f_t = ImageFont.truetype(fp, 50)
    while d.textlength(stay, font=f_t) > W - 200 and f_t.size > 30:
        f_t = ImageFont.truetype(fp, f_t.size - 2)
    tw = d.textlength(stay, font=f_t)
    d.rounded_rectangle([(W - tw) / 2 - 36, 150, (W + tw) / 2 + 36, 150 + f_t.size + 40], 28, fill=(0, 0, 0, 150))
    d.text(((W - tw) / 2, 168), stay, font=f_t, fill=(255, 255, 255, 255))
    # 고지문 (항상 보인다)
    f_d = ImageFont.truetype(fp, 24)
    y = 150 + f_t.size + 62
    for ln in wrap(d, DISCLOSURE, f_d, W - 160):
        lw = d.textlength(ln, font=f_d)
        d.text(((W - lw) / 2, y), ln, font=f_d, fill=(255, 255, 255, 215), stroke_width=2, stroke_fill=(0, 0, 0, 200))
        y += 34
    # 자막
    f_c = ImageFont.truetype(fp, 84 if is_hook else 66)
    lines = wrap(d, caption, f_c, W - 180)
    lh = f_c.size + 22
    y = 1330 - (len(lines) * lh) // 2
    for ln in lines:
        lw = d.textlength(ln, font=f_c)
        d.text(((W - lw) / 2, y), ln, font=f_c, fill=(255, 232, 107, 255) if is_hook else (255, 255, 255, 255),
               stroke_width=7, stroke_fill=(0, 0, 0, 255))
        y += lh
    img.save(path)


def run(cmd: list):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 실패: " + r.stderr[-600:])


def make_segment(img: Path, overlay: Path, dur: float, out: Path, idx: int):
    from PIL import Image
    with Image.open(img) as im:
        iw, ih = im.size
    fg_h = int(min(1300, round(1080 * ih / iw)) // 2 * 2)
    frames = max(2, int(round(dur * FPS)))
    zin = idx % 2 == 0
    z = f"min(1+0.10*on/{frames},1.10)" if zin else f"max(1.10-0.10*on/{frames},1)"
    fc = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:4,"
        f"eq=brightness=-0.22:saturation=0.9,fps={FPS}[bg];"
        f"[1:v]scale=2160:-2,zoompan=z='{z}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={W}x{fg_h}:fps={FPS}[fg];"
        f"[bg][fg]overlay=0:{(H - fg_h) // 2 - 110}:shortest=1[v1];"
        f"[v1][2:v]overlay=0:0[v]"
    )
    run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{dur:.3f}", "-i", str(img),
         "-i", str(img), "-loop", "1", "-t", f"{dur:.3f}", "-i", str(overlay),
         "-filter_complex", fc, "-map", "[v]", "-t", f"{dur:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)])


def download(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stay-shorts-factory)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        dest.write_bytes(r.read())


def main() -> int:
    req = json.loads(REQUEST.read_text(encoding="utf-8"))
    stay = str(req.get("stay") or "").strip()
    if not stay:
        raise SystemExit("request.json 에 stay(숙소 이름)가 없습니다")
    BUILD.mkdir(parents=True, exist_ok=True)
    report = {"nonce": req.get("nonce"), "stay": stay, "ok": False, "steps": {}}
    try:
        items = coupang_search(stay, 10)
        report["steps"]["search"] = {"count": len(items)}
        if len(items) < 2:
            raise RuntimeError("검색 결과가 2개 미만")
        models = pick_models()
        report["models"] = models
        script = _try_models("text", models["text"], lambda m: write_script(m, stay, items))
        lines = [script["hook"]] + list(script["lines"])
        report["script"] = {k: script.get(k) for k in ("hook", "lines", "title", "caption", "hashtags", "rooms", "excluded", "image_for_line")}
        report["room_names"] = {str(i): str(items[i].get("productName", ""))[:70] for i in script["rooms"]}

        # 사진
        from PIL import Image
        imgs, dims = {}, {}
        for i in sorted(set(script["image_for_line"])):
            p = BUILD / f"img_{i}.jpg"
            download(str(items[i].get("productImage")), p)
            with Image.open(p) as im:
                dims[str(i)] = list(im.size)
                im.convert("RGB").save(p, "JPEG", quality=92)
            imgs[i] = p
        report["image_sizes"] = dims

        # 음성
        wav = BUILD / "narration.wav"
        raw = BUILD / "narration_raw.wav"
        _try_models("tts", models["tts"], lambda m: gemini_tts(
            m, "\n".join(lines), str(req.get("voice") or "Erinome"),
            "다음 대사를 밝고 설레는 여행 추천 내레이션 톤으로, 또렷하고 리듬감 있게 읽어줘", raw))
        tempo = float(req.get("tempo") or 1.12)
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"atempo={tempo:.3f}", str(wav)])
        with wave.open(str(wav), "rb") as wf:
            total = wf.getnframes() / wf.getframerate()
        report["narration_sec"] = round(total, 2)

        # 줄별 길이 — 글자 수 비례 (정밀 맞춤은 다음 단계)
        weights = [len(re.sub(r"\s", "", x)) + 3 for x in lines]
        durs = [total * w / sum(weights) for w in weights]
        durs[-1] += 0.8
        segs = []
        for n, (line, dur) in enumerate(zip(lines, durs)):
            ov = BUILD / f"ov_{n}.png"
            make_overlay(ov, stay, line, n == 0)
            seg = BUILD / f"seg_{n}.mp4"
            make_segment(imgs[script["image_for_line"][n]], ov, dur, seg, n)
            segs.append(seg)
        (BUILD / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
        silent = BUILD / "silent.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "concat.txt"),
             "-c", "copy", str(silent)])
        video = BUILD / "video.mp4"
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(wav), "-c:v", "copy",
             "-c:a", "aac", "-b:a", "128k", "-af", "apad=pad_dur=0.8", "-shortest", "-movflags", "+faststart", str(video)])

        # 미리보기 사진 3장 (저장소에 커밋되는 것은 이것뿐 — 영상은 Release 로)
        prev = ROOT / "data" / "runs" / "latest"
        prev.mkdir(parents=True, exist_ok=True)
        dur_total = sum(durs)
        for k, t in enumerate([0.6, dur_total * 0.45, dur_total - 1.2]):
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(t, 0):.2f}", "-i", str(video), "-frames:v", "1",
                 "-vf", "scale=360:640", "-q:v", "5", str(prev / f"frame_{k}.jpg")])

        rooms = [items[i] for i in script["rooms"]]
        cheapest = min(rooms, key=lambda it: float(it.get("productPrice") or 9e12))
        caption = DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip() + "\n\n" + " ".join(script.get("hashtags") or [])
        meta = {"stay": stay, "title": script.get("title"), "caption": caption,
                "affiliate_url": cheapest.get("productUrl"), "duration_sec": round(dur_total, 2),
                "lines": lines, "models": dict(USED)}
        (BUILD / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        assert DISCLOSURE in meta["caption"], "고지문 누락 — 중단"
        report["models_used"] = dict(USED)
        report.update({"ok": True, "duration_sec": round(dur_total, 2),
                       "video_bytes": video.stat().st_size})
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        log("실패:", report["error"])
    out = ROOT / "data" / "runs" / "latest" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
