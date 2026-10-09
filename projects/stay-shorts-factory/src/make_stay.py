#!/usr/bin/env python3
"""숙소 이름 1개 → 세로 영상 1편.

    python3 src/make_stay.py            requests/produce/request.json 을 읽는다

request.json
    {"nonce": "...", "stay": "숙소 이름", "mode": "veo"}      ← 운영자가 원하는 방식 (사진 7장 → AI 이미지→영상 7컷)
    {"nonce": "...", "stay": "숙소 이름"}                     ← 예전 시험 방식 (사진 확대 + 자막, 유료 생성 없음)

흐름 (mode = veo)
  1) 쿠팡 파트너스 검색 API 로 숙소 이름을 검색한다 (객실 목록·사진·제휴 링크가 같이 온다)
  2) 사진 수집: requests/produce/photos/ 운영자 사진(우선) + 쿠팡 사진 → Gemini 가 보고 분류 → 물놀이 3·객실 2·특별 2 (src/photos.py)
  3) 사진마다 초점 기준 9:16 크롭 (지어낸 영역 없음)
  4) Gemini 가 장면 순서에 맞춘 대본을 쓰고, Gemini 음성으로 나레이션을 만든다 (싼 단계를 먼저 — 여기서 실패하면 돈을 안 쓴다)
  5) 사진마다 Veo 이미지→영상 4초 (src/veo.py — 한도·장부) → 7컷 이어 붙이기 → 숙소명·고지문·자막 → 나레이션 합성
  6) build/video.mp4 · meta.json · 원본 사진과 클립을 나란히 둔 비교 사진(data/runs/latest/compare_*.jpg)

기존 자산 재사용
  - Gemini 글·음성 호출 형식: projects/coupang-shorts-factory 의 generate.py · tts.py 에서 검증된 것
  - Veo 호출·비용 상한: jtaechul/verdict-theater 의 veo.py · cost.py (src/veo.py 로 이식)
  - 글꼴: projects/coupang-shorts-factory/assets/fonts/GmarketSansBold.ttf (상업적 사용 허용)
  - 쿠팡 서명·경로: scripts/coupang_probe.py 로 2026-10-09 실측한 것

규칙 (CLAUDE.md)
  - 스크래핑 없음. 사진은 쿠팡 API 가 준 것과 운영자가 직접 준 것만 쓴다. 제휴 링크를 따라가지 않는다.
  - 대본은 객실 이름과 사진에 보이는 것만 쓴다. 가격 숫자·'최고/유일' 같은 단정 표현 금지.
  - AI 영상은 실제 사진을 시작 프레임으로 쓴다. 지시문에 "사진에 없는 것을 넣지 말라"가 항상 붙는다.
  - 제휴 고지문은 화면과 캡션 첫 줄에 항상 들어간다.
  - 유료 생성은 src/veo.py 한 곳에서만, 한 번 실행·한 달 한도 안에서만.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photos  # noqa: E402
import veo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
REQUEST = ROOT / "requests" / "produce" / "request.json"
OPERATOR_PHOTOS = ROOT / "requests" / "produce" / "photos"
PREVIEW = ROOT / "data" / "runs" / "latest"
FONT_CANDIDATES = [
    ROOT.parent / "coupang-shorts-factory" / "assets" / "fonts" / "GmarketSansBold.ttf",
    ROOT / "assets" / "fonts" / "GmarketSansBold.ttf",
]

DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다"
W, H, FPS = 1080, 1920, 30
CLIP_SEC = 4                      # Veo 한 컷 길이 (실측 허용 범위 4~8초 중 가장 싼 것)
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

SYSTEM_VEO = """
이번 영상은 입력의 '장면 순서'대로 사진 여러 장을 움직이는 영상(장면당 4초)으로 이어 보여 준다.
- hook 은 장면 1 을 보면서 듣는 말이다. lines 는 장면 2 부터 마지막 장면까지의 흐름을 순서대로 따라간다 (앞 줄은 물놀이 공간, 가운데는 객실, 마지막 줄은 마지막 장면과 프로필 안내).
- 각 줄은 그때 화면에 보이는 것(장면 설명)과 객실 이름에 적힌 사실만 말한다. 장면 설명에도 객실 이름에도 없는 시설은 말하지 않는다.
- image_for_line 은 쓰지 않는다 — 고른 객실 번호 중 아무것이나 6개 채운다."""


def check_script(s: dict, n_items: int, need_images: bool = True) -> list:
    errs = []
    lines = [str(s.get("hook", ""))] + [str(x) for x in (s.get("lines") or [])]
    if len(lines) != 6 or not all(x.strip() for x in lines):
        errs.append("hook 1줄 + lines 5줄이 아니다")
    rooms = [i for i in (s.get("rooms") or []) if isinstance(i, int) and 0 <= i < n_items]
    if len(rooms) < 2:
        errs.append("이 숙소의 객실로 고른 것이 2개 미만이다")
    if need_images:
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


def write_script(model: str, stay: str, items: list, scenes: str = "") -> dict:
    listing = "\n".join(f"{i}. {str(it.get('productName', ''))[:70]} / {it.get('productPrice')}원"
                        for i, it in enumerate(items))
    content = f"숙소 이름: {stay}\n\n쿠팡 검색 결과:\n{listing}"
    system = SYSTEM
    if scenes:
        content += f"\n\n장면 순서:\n{scenes}"
        system += SYSTEM_VEO
    errs = []
    for attempt in range(3):
        extra = ("\n\n직전 답의 문제(고쳐서 다시): " + " / ".join(errs)) if errs else ""
        s = gemini_json(model, system, content + extra)
        errs = check_script(s, len(items), need_images=not scenes)
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


def make_overlay(path: Path, stay: str, caption: str, is_hook: bool, header: bool = True):
    """투명 PNG 한 장. header=True 면 위에 숙소 이름 + 고지문, caption 이 있으면 아래에 자막."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fp = font_path()
    if header:
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
    if caption:
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


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        raise RuntimeError(f"길이를 못 읽음: {path.name} {r.stderr[-200:]}")


def make_segment(img: Path, overlay: Path, dur: float, out: Path, idx: int):
    """(예전 방식) 사진 확대 + 자막 한 장면."""
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


def line_durations(lines: list, total: float) -> list:
    """줄별 길이 — 글자 수 비례 (정밀 맞춤은 다음 단계)."""
    weights = [len(re.sub(r"\s", "", x)) + 3 for x in lines]
    return [total * w / sum(weights) for w in weights]


# ── Veo 방식 합성 ───────────────────────────────────────────────────────
def normalize_clip(src: Path, dst: Path):
    """Veo 클립(720x1280 24fps, 소리 포함)을 1080x1920 30fps 무음으로 맞춘다. 길이는 CLIP_SEC 로 자른다."""
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-an",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},setsar=1",
         "-t", str(CLIP_SEC), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(dst)])


def compose_veo(stay: str, lines: list, clips: list, wav: Path, narr_total: float, build: Path) -> tuple[Path, float]:
    """클립들을 이어 붙이고, 숙소명·고지문(항상) + 줄별 자막(시간대별) 을 얹고 나레이션을 합친다."""
    norm = []
    for n, c in enumerate(clips):
        d = build / f"clip_{n}.mp4"
        normalize_clip(c, d)
        norm.append(d)
    (build / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in norm), encoding="utf-8")
    silent = build / "silent.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(build / "concat.txt"),
         "-c", "copy", str(silent)])
    video_len = probe_duration(silent)
    total = max(video_len, narr_total + 0.8)
    pad = max(0.0, total - video_len)          # 나레이션이 더 길면 마지막 장면을 멈춰 세워 채운다

    header = build / "ov_header.png"
    make_overlay(header, stay, "", False, header=True)
    durs = line_durations(lines, narr_total)
    caps, t = [], 0.0
    for n, (line, dur) in enumerate(zip(lines, durs)):
        p = build / f"ov_{n}.png"
        make_overlay(p, stay, line, n == 0, header=False)
        caps.append((p, t, t + dur))
        t += dur
    caps[-1] = (caps[-1][0], caps[-1][1], total)   # 마지막 자막은 끝까지

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(header)]
    for p, _, _ in caps:
        cmd += ["-i", str(p)]
    cmd += ["-i", str(wav)]
    fc = f"[0:v]tpad=stop_mode=clone:stop_duration={pad:.3f}[v0];[v0][1:v]overlay=0:0:format=auto[v1];"
    for n, (_, a, b) in enumerate(caps):
        fc += f"[v{n + 1}][{n + 2}:v]overlay=0:0:format=auto:enable='between(t,{a:.3f},{b:.3f})'[v{n + 2}];"
    fc += f"[v{len(caps) + 1}]format=yuv420p[v];[{len(caps) + 2}:a]apad[a]"
    video = build / "video.mp4"
    run(cmd + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}", "-r", str(FPS),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(video)])
    return video, total


def compare_images(shots: list, clips: dict, build: Path, outdir: Path) -> Path:
    """승인용: 원본(크롭) 사진과 Veo 클립 첫 프레임을 나란히. 컷마다 compare_N.jpg + 한 장짜리 compare_sheet.jpg."""
    from PIL import Image, ImageDraw, ImageFont
    fp = font_path()
    f = ImageFont.truetype(fp, 28)
    pairs = []
    for s in shots:
        n = s["n"]
        src = Image.open(build / f"shot_{n}.png").convert("RGB").resize((360, 640), Image.LANCZOS)
        clip = clips.get(n)
        if clip:
            fr = build / f"first_{n}.png"
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-frames:v", "1", str(fr)])
            right = Image.open(fr).convert("RGB").resize((360, 640), Image.LANCZOS)
        else:
            right = Image.new("RGB", (360, 640), (40, 40, 40))
        pair = Image.new("RGB", (720, 640), (0, 0, 0))
        pair.paste(src, (0, 0)); pair.paste(right, (360, 0))
        d = ImageDraw.Draw(pair)
        d.rectangle([0, 0, 720, 44], fill=(0, 0, 0))
        d.text((12, 8), f"{n}. 원본 사진 ({photos.KO[s['slot']]})", font=f, fill=(255, 255, 255))
        d.text((372, 8), "Veo 영상 첫 장면" if clip else "실패 — 제외", font=f, fill=(255, 232, 107) if clip else (255, 120, 120))
        pair.save(outdir / f"compare_{n}.jpg", "JPEG", quality=85)
        pairs.append(pair)
    cols, rows = 2, (len(pairs) + 1) // 2
    sheet = Image.new("RGB", (cols * 540, rows * 480), (20, 20, 20))
    for i, p in enumerate(pairs):
        sheet.paste(p.resize((540, 480), Image.LANCZOS), ((i % cols) * 540, (i // cols) * 480))
    out = outdir / "compare_sheet.jpg"
    sheet.save(out, "JPEG", quality=85)
    return out


def produce_veo(req: dict, stay: str, items: list, models: dict, report: dict) -> tuple[Path, float, dict]:
    """사진 7장 → Veo 7컷 → 이어 붙이기. 돌려주는 것: (영상, 길이, meta 에 넣을 것)."""
    # 1) 사진 수집·분류·선정 (0원에 가까움)
    cands = photos.gather(items, OPERATOR_PHOTOS, BUILD)
    if not cands:
        raise RuntimeError("쓸 사진이 한 장도 없습니다 (쿠팡 사진 없음 · requests/produce/photos/ 비어 있음)")
    classified = _try_models("vision", models["text"], lambda m: photos.classify(m, cands))
    shots, notes = photos.select(classified)
    for s in shots:
        photos.crop_9x16(s["path"], BUILD / f"shot_{s['n']}.png", s["focus_x"], s["focus_y"])
        s["prompt"] = photos.prompt_for(s)
    report["photos"] = {"candidates": len(cands), "notes": notes,
                        "classified": [{k: p[k] for k in ("k", "source", "name", "category", "quality", "description", "people")}
                                       for p in classified],
                        "shots": [{k: s[k] for k in ("n", "k", "slot", "category", "source", "description", "focus_x", "focus_y", "prompt")}
                                  for s in shots]}
    log(f"장면 {len(shots)}개: " + " · ".join(f"{s['n']}{photos.KO[s['slot']][:2]}" for s in shots))

    # 2) 대본·음성 (싼 단계 먼저 — 여기서 실패하면 영상값을 안 쓴다)
    script = _try_models("text", models["text"], lambda m: write_script(m, stay, items, photos.scene_list_ko(shots)))
    lines = [script["hook"]] + list(script["lines"])
    report["script"] = {k: script.get(k) for k in ("hook", "lines", "title", "caption", "hashtags", "rooms", "excluded")}
    report["room_names"] = {str(i): str(items[i].get("productName", ""))[:70] for i in script["rooms"]}
    wav, raw = BUILD / "narration.wav", BUILD / "narration_raw.wav"
    _try_models("tts", models["tts"], lambda m: gemini_tts(
        m, "\n".join(lines), str(req.get("voice") or "Erinome"),
        "다음 대사를 밝고 설레는 여행 추천 내레이션 톤으로, 또렷하고 리듬감 있게 읽어줘", raw))
    tempo = float(req.get("tempo") or 1.12)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"atempo={tempo:.3f}", str(wav)])
    with wave.open(str(wav), "rb") as wf:
        narr_total = wf.getnframes() / wf.getframerate()
    report["narration_sec"] = round(narr_total, 2)

    # 3) Veo 7컷 (돈이 나가는 자리 — 한도는 veo.py 가 본다)
    est = veo.estimate_krw(len(shots), CLIP_SEC)
    log(f"Veo {veo.MODEL} · {len(shots)}컷 x {CLIP_SEC}초 · 예상 약 {est:,.0f}원 · 이번 달 누적 {veo.month_total():,.0f}원 / {veo.MONTH_KRW:,.0f}원")
    clips, results, stopped = {}, [], None
    for s in shots:
        n, out = s["n"], BUILD / f"veo_{s['n']}.mp4"
        row = {"n": n, "slot": s["slot"], "ok": False, "krw": 0.0}
        seed = veo.seed_for(stay, n, s["k"])
        for attempt in range(2):
            try:
                row["krw"] += veo.make_clip(s["prompt"], BUILD / f"shot_{n}.png", CLIP_SEC, out, seed + attempt)
                row["ok"] = True
                clips[n] = out
                break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:160]}"
                log(f"컷 {n} 안전 필터 → 씨앗 바꿔 재시도" if attempt == 0 else f"컷 {n} 재시도도 안전 필터 — 제외")
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"
                stopped = str(e)
                break
            except veo.VeoError as e:
                row["error"] = str(e)[:200]
                log(f"컷 {n} 실패 — 제외: {str(e)[:160]}")
                break
        results.append(row)
        if stopped:
            log("한도에 걸려 여기서 멈춤 —", stopped)
            break
    report["veo"] = {"model": veo.MODEL, "clip_sec": CLIP_SEC, "estimated_krw": round(est),
                     "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total()),
                     "clips": results, "stopped": stopped}
    ok_shots = [s for s in shots if s["n"] in clips]
    if len(ok_shots) < photos.MIN_SHOTS:
        raise RuntimeError(f"만들어진 컷이 {len(ok_shots)}개뿐 (최소 {photos.MIN_SHOTS}개) — 영상을 만들지 않음. "
                           + (stopped or "실패 내용은 report.json 의 veo.clips"))

    # 4) 이어 붙이기 + 자막 + 나레이션
    video, total = compose_veo(stay, lines, [clips[s["n"]] for s in ok_shots], wav, narr_total, BUILD)
    sheet = compare_images(shots, clips, BUILD, PREVIEW)
    log("비교 사진:", sheet.relative_to(ROOT))
    rooms = [items[i] for i in script["rooms"]]
    cheapest = min(rooms, key=lambda it: float(it.get("productPrice") or 9e12))
    meta = {"mode": "veo", "title": script.get("title"),
            "caption": DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip() + "\n\n" + " ".join(script.get("hashtags") or []),
            "affiliate_url": cheapest.get("productUrl"), "lines": lines,
            "veo": {"model": veo.MODEL, "clips_ok": len(ok_shots), "clips_total": len(shots),
                    "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta


def produce_photo(req: dict, stay: str, items: list, models: dict, report: dict) -> tuple[Path, float, dict]:
    """(예전 시험 방식) 사진 확대 + 자막. 유료 생성 없음. 운영자 평가 '허접' — 비교용으로만 남긴다."""
    script = _try_models("text", models["text"], lambda m: write_script(m, stay, items))
    lines = [script["hook"]] + list(script["lines"])
    report["script"] = {k: script.get(k) for k in ("hook", "lines", "title", "caption", "hashtags", "rooms", "excluded", "image_for_line")}
    report["room_names"] = {str(i): str(items[i].get("productName", ""))[:70] for i in script["rooms"]}

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

    wav, raw = BUILD / "narration.wav", BUILD / "narration_raw.wav"
    _try_models("tts", models["tts"], lambda m: gemini_tts(
        m, "\n".join(lines), str(req.get("voice") or "Erinome"),
        "다음 대사를 밝고 설레는 여행 추천 내레이션 톤으로, 또렷하고 리듬감 있게 읽어줘", raw))
    tempo = float(req.get("tempo") or 1.12)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"atempo={tempo:.3f}", str(wav)])
    with wave.open(str(wav), "rb") as wf:
        total = wf.getnframes() / wf.getframerate()
    report["narration_sec"] = round(total, 2)

    durs = line_durations(lines, total)
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
    rooms = [items[i] for i in script["rooms"]]
    cheapest = min(rooms, key=lambda it: float(it.get("productPrice") or 9e12))
    meta = {"mode": "photo", "title": script.get("title"),
            "caption": DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip() + "\n\n" + " ".join(script.get("hashtags") or []),
            "affiliate_url": cheapest.get("productUrl"), "lines": lines}
    return video, sum(durs), meta


def main() -> int:
    req = json.loads(REQUEST.read_text(encoding="utf-8"))
    stay = str(req.get("stay") or "").strip()
    mode = str(req.get("mode") or "photo").strip().lower()
    if not stay:
        raise SystemExit("request.json 에 stay(숙소 이름)가 없습니다")
    BUILD.mkdir(parents=True, exist_ok=True)
    PREVIEW.mkdir(parents=True, exist_ok=True)
    for old in PREVIEW.glob("compare_*.jpg"):          # 지난 실행의 비교 사진은 지운다 (이번 것과 섞이지 않게)
        old.unlink()
    report = {"nonce": req.get("nonce"), "stay": stay, "mode": mode, "ok": False, "steps": {}}
    try:
        items = coupang_search(stay, 10)
        report["steps"]["search"] = {"count": len(items)}
        if len(items) < 2:
            raise RuntimeError("검색 결과가 2개 미만")
        models = pick_models()
        report["models"] = models
        if mode == "veo":
            video, dur_total, meta = produce_veo(req, stay, items, models, report)
        else:
            video, dur_total, meta = produce_photo(req, stay, items, models, report)

        # 미리보기 사진 3장 (저장소에 커밋되는 것은 이것뿐 — 영상은 Release 로)
        for k, t in enumerate([0.6, dur_total * 0.45, dur_total - 1.2]):
            run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(t, 0):.2f}", "-i", str(video), "-frames:v", "1",
                 "-vf", "scale=360:640", "-q:v", "5", str(PREVIEW / f"frame_{k}.jpg")])

        meta.update({"stay": stay, "duration_sec": round(dur_total, 2), "models": dict(USED)})
        (BUILD / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        assert DISCLOSURE in meta["caption"], "고지문 누락 — 중단"
        report["models_used"] = dict(USED)
        report.update({"ok": True, "duration_sec": round(dur_total, 2), "video_bytes": video.stat().st_size})
    except Exception as e:  # noqa: BLE001
        report["error"] = f"{type(e).__name__}: {str(e)[:500]}"
        if mode == "veo":
            report.setdefault("veo", {})["spent_krw"] = round(veo.spent_this_run())
        log("실패:", report["error"])
    out = PREVIEW / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
