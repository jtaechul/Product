#!/usr/bin/env python3
"""숙소 사진 7장 고르기 — 수집 → Gemini 가 보고 분류 → 물놀이 3·객실 2·특별 공간 2 → 9:16 크롭 → 컷별 Veo 지시문.

운영자가 준 수동 제작법(CLAUDE.md '운영자가 원하는 영상 방식')을 자동화한 것.
    1) 사진 수집: requests/produce/photos/ 에 운영자가 넣은 사진(있으면 우선) + 쿠팡 검색 결과 사진(객실당 1장)
    2) Gemini 비전(사진을 보는 AI 호출)이 사진마다: 분류(water/room/special/skip) · 한국어 설명 · 세로 크롭 초점 · 영문 Veo 지시문
    3) 3·2·2 선정. 모자라면 가까운 분류에서 채운다 (물놀이 없음 → 특별 공간 → 객실 순)
    4) 정사각형 사진을 초점 기준으로 9:16(720x1280) 잘라낸다 — 지어낸 영역 없이 실제 사진 부분만 남긴다
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

GEMINI = "https://generativelanguage.googleapis.com/v1beta"
CATS = ("water", "room", "special")
WANT = {"water": 3, "room": 2, "special": 2}
ORDER = ("water", "room", "special")                       # 영상에 나오는 순서 (운영자 제시 순서)
FILL = {"water": ("special", "room"), "room": ("special", "water"), "special": ("water", "room")}
KO = {"water": "물놀이 공간", "room": "객실", "special": "특별한 공간"}
MIN_SHOTS = 4
EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# 지시문 끝에 코드가 항상 붙이는 문장 — 모델이 빼먹어도 과장 광고 방지 규칙이 지켜지게 한다
SUFFIX = (" Keep every object, structure, layout and view exactly as in the photo; do not add people, buildings, "
          "furniture, water features or scenery that are not in the photo. No text, no captions, no logos, "
          "no watermark. Photorealistic, steady, high-end hotel promotional footage, vertical 9:16.")

# 모델이 지시문을 못 주면 분류별 기본 카메라 움직임
DEFAULT_MOTION = {
    "water": "Slow cinematic drone-style forward glide over the pool, gentle water ripples catching the sunlight.",
    "room": "Slow, smooth push-in dolly toward the bed, soft daylight, curtains barely moving.",
    "special": "Slow tracking shot moving gently through the space, leaves and grass swaying softly in a light breeze.",
}

SYSTEM = """너는 숙소 홍보 숏폼의 촬영 감독이다. 숙소 사진 여러 장을 보고 사진마다 JSON 한 항목을 쓴다.
각 사진에 대해:
- category: "water"(수영장·워터파크·온수풀·해변 등 물놀이 공간) / "room"(침대·객실 내부·욕실) / "special"(산책로·정원·테라스·전망·라운지·바베큐장 등 객실 밖의 특별한 공간) / "skip"(사진이 아닌 안내문·지도·로고·항공권·음식 접시만 찍힌 것·심하게 작거나 흐린 것)
- description: 사진에 실제로 보이는 것만 한국어 한 문장 (없는 것을 지어내지 않는다. 예: "인피니티 풀 너머로 바다와 소나무가 보인다")
- focus_x, focus_y: 세로(9:16)로 잘라낼 때 꼭 남겨야 할 중심점. 0.0~1.0 (왼쪽 위가 0,0). 수영장·침대·길 같은 핵심이 들어가게 고른다
- people: 사람이 보이면 true
- quality: 영상 소재로서의 품질 0~10 (해상도·구도·밝기)
- veo_prompt: 이 사진을 4초 영상으로 움직일 때의 영어 지시문 1~2문장. 카메라 움직임 한 가지(drone glide / slow push-in / slow tracking / gentle tilt 등)와 자연스러운 움직임 한 가지(water ripples / curtains sway / leaves sway / light shimmer)만 적는다. 사진에 없는 사물·사람·건물·풍경을 추가하라고 쓰지 않는다. 빠른 움직임·흔들림·줌 급변 금지.
JSON 만 출력한다: {"photos":[{"k":번호,"category":"...","description":"...","focus_x":0.5,"focus_y":0.5,"people":false,"quality":7,"veo_prompt":"..."}]}"""


def log(*a):
    print("[photos]", *a, flush=True)


# ── 수집 ───────────────────────────────────────────────────────────────
def _download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stay-shorts-factory)"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def _store(data: bytes, dest: Path) -> tuple[int, int]:
    """어떤 형식이든 RGB JPEG 로 저장. 아주 큰 사진은 긴 변 2000px 로 줄인다."""
    with Image.open(io.BytesIO(data)) as im:
        im = im.convert("RGB")
        if max(im.size) > 2000:
            im.thumbnail((2000, 2000), Image.LANCZOS)
        im.save(dest, "JPEG", quality=93)
        return im.size


def gather(items: list, operator_dir: Path, build: Path) -> list[dict]:
    """후보 사진 목록. 운영자 폴더 사진이 앞, 쿠팡 사진이 뒤. 같은 사진(내용 해시)은 한 번만."""
    cands, seen = [], set()

    def add(data: bytes, source: str, name: str, index=None):
        h = hashlib.sha1(data).hexdigest()
        if h in seen:
            return
        k = len(cands)
        dest = build / f"cand_{k}.jpg"
        try:
            size = _store(data, dest)
        except Exception as e:  # noqa: BLE001
            log(f"사진을 못 읽음 ({name}): {e}")
            return
        if min(size) < 300:
            log(f"너무 작은 사진 제외 ({name}): {size}")
            return
        seen.add(h)
        cands.append({"k": k, "source": source, "name": name, "index": index, "path": str(dest), "size": list(size)})

    if operator_dir.is_dir():
        for p in sorted(operator_dir.iterdir()):
            if p.suffix.lower() in EXTS and p.is_file():
                add(p.read_bytes(), "operator", p.name)
    for i, it in enumerate(items):
        url = str(it.get("productImage") or "")
        if not url.startswith("http"):
            continue
        try:
            add(_download(url), "coupang", str(it.get("productName", ""))[:60], i)
        except Exception as e:  # noqa: BLE001
            log(f"쿠팡 사진 내려받기 실패 ({i}): {e}")
    log(f"후보 사진 {len(cands)}장 (운영자 {sum(c['source'] == 'operator' for c in cands)} · "
        f"쿠팡 {sum(c['source'] == 'coupang' for c in cands)})")
    return cands


# ── Gemini 비전 ────────────────────────────────────────────────────────
def _gpost(path: str, body: dict, timeout: int = 180) -> dict:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    req = urllib.request.Request(f"{GEMINI}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini 오류 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def _small_jpeg_b64(path: str, side: int = 640) -> str:
    """분류용으로는 작은 그림이면 충분하다 (토큰 절약)."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def classify(model: str, cands: list[dict]) -> list[dict]:
    """사진마다 분류·설명·초점·지시문. 돌려주는 목록은 cands 와 같은 순서(k 기준)."""
    listing = "\n".join(f"사진 {c['k']}: " + ("운영자가 준 사진" if c["source"] == "operator" else f"쿠팡 객실 상품 '{c['name']}'")
                        for c in cands)
    parts = [{"text": f"사진 {len(cands)}장. 각 사진 앞에 번호를 적어 둔다.\n{listing}"}]
    for c in cands:
        parts.append({"text": f"사진 {c['k']}:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _small_jpeg_b64(c["path"])}})
    body = {"system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 4000, "temperature": 0.4,
                                 "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = _gpost(f"models/{model}:generateContent", body)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig")
        data = _gpost(f"models/{model}:generateContent", body)
    txt = "".join(p.get("text", "") for p in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []))
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip()).strip()
    got = {int(p.get("k", -1)): p for p in (json.loads(txt).get("photos") or []) if isinstance(p, dict)}
    out = []
    for c in cands:
        p = got.get(c["k"]) or {}
        cat = str(p.get("category", "skip")).strip().lower()
        if cat not in CATS:
            cat = "skip"

        def f01(v, d=0.5):
            try:
                return min(1.0, max(0.0, float(v)))
            except (TypeError, ValueError):
                return d
        out.append({**c, "category": cat, "description": str(p.get("description", ""))[:120],
                    "focus_x": f01(p.get("focus_x")), "focus_y": f01(p.get("focus_y")),
                    "people": bool(p.get("people", False)), "quality": _q(p.get("quality")),
                    "veo_prompt": str(p.get("veo_prompt", "")).strip()[:400]})
    for o in out:
        log(f"사진 {o['k']} [{o['source']}] → {o['category']} q{o['quality']} {o['description'][:50]}")
    return out


def _q(v) -> int:
    try:
        return int(min(10, max(0, float(v))))
    except (TypeError, ValueError):
        return 5


# ── 선정 ───────────────────────────────────────────────────────────────
def select(classified: list[dict]) -> tuple[list[dict], list[str]]:
    """물놀이 3·객실 2·특별 2 를 고른다. 운영자 사진 먼저, 그다음 품질 순. 모자라면 가까운 분류에서 채운다."""
    notes = []
    usable = [p for p in classified if p["category"] in CATS and p["quality"] >= 3]
    usable.sort(key=lambda p: (p["source"] != "operator", -p["quality"]))
    by = {c: [p for p in usable if p["category"] == c] for c in CATS}
    chosen = {c: by[c][:WANT[c]] for c in CATS}
    left = {c: by[c][WANT[c]:] for c in CATS}
    for c in CATS:
        for alt in FILL[c]:
            while len(chosen[c]) < WANT[c] and left[alt]:
                p = left[alt].pop(0)
                chosen[c].append(p)
                notes.append(f"{KO[c]} 사진이 모자라 {KO[alt]} 사진(k={p['k']})으로 채움")
    shots = []
    for c in ORDER:
        for p in chosen[c]:
            shots.append({**p, "slot": c, "n": len(shots) + 1})
    if len(shots) < MIN_SHOTS:
        raise RuntimeError(f"쓸 수 있는 사진이 {len(shots)}장뿐입니다 (최소 {MIN_SHOTS}장). "
                           f"requests/produce/photos/ 에 숙소 사진을 넣어 주세요.")
    if len(shots) < sum(WANT.values()):
        notes.append(f"사진이 {len(shots)}장뿐이라 {len(shots)}컷으로 만든다")
    return shots, notes


# ── 크롭·지시문 ─────────────────────────────────────────────────────────
def crop_9x16(src: str, dst: Path, fx: float, fy: float, w: int = 720, h: int = 1280) -> None:
    """초점(fx, fy)이 가운데 오도록 9:16 창을 잘라낸다. 실제 사진 바깥은 절대 만들지 않는다."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        iw, ih = im.size
        if iw / ih > w / h:                       # 원본이 더 넓다 → 가로를 자른다
            cw, ch = int(round(ih * w / h)), ih
            x = int(min(max(fx * iw - cw / 2, 0), iw - cw)); y = 0
        else:                                     # 원본이 더 좁거나 같다 → 세로를 자른다
            cw, ch = iw, int(round(iw * h / w))
            x = 0; y = int(min(max(fy * ih - ch / 2, 0), ih - ch))
        im.crop((x, y, x + cw, y + ch)).resize((w, h), Image.LANCZOS).save(dst, "PNG")


def prompt_for(shot: dict) -> str:
    base = shot.get("veo_prompt") or DEFAULT_MOTION[shot["category"]]
    if not re.search(r"(drone|push|track|dolly|tilt|glide|pan|orbit|camera)", base, re.I):
        base = DEFAULT_MOTION[shot["category"]] + " " + base
    return base.rstrip(". ") + "." + SUFFIX


def scene_list_ko(shots: list[dict]) -> str:
    return "\n".join(f"장면 {s['n']} ({KO[s['slot']]}): {s['description'] or KO[s['category']]}" for s in shots)
