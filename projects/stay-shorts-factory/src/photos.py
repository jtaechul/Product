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
import urllib.parse
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
- category: "water"(수영장·워터파크·온수풀·해변 등 물놀이 공간. 항공·외관 사진이라도 수영장이 또렷이 보이면 water) / "room"(침대·객실 내부·욕실) / "special"(산책로·정원·테라스·전망·라운지·바베큐장 등 객실 밖의 특별한 공간) / "skip"(사진이 아닌 안내문·지도·로고·항공권·음식 접시만 찍힌 것·심하게 작거나 흐린 것)
- description: 사진에 실제로 보이는 것만 한국어 한 문장 (없는 것을 지어내지 않는다. 예: "인피니티 풀 너머로 바다와 소나무가 보인다")
  **시설 이름 규칙(2026-10-14 · 같은 사진이 17번 실행에서 자쿠지·욕조·온수풀·탕으로 매번 달라졌다)**: 아래 이름은 **사진에 그 결정적 증거가 보일 때만** 쓴다.
  증거가 없으면 모양·재질·조명만 말하는 일반어("원형 실내 온수탕", "실내 풀", "스파 공간")를 쓴다. 분위기·주변 맥락(스파 페이지·조명)으로 이름을 추측하지 않는다.
  · 자쿠지·월풀: 물속 기포·거품이나 벽의 분사구(제트)가 보인다
  · 파도풀: 물결 띠·하얀 포말로 파도가 치는 것이 보인다
  · 유수풀: 길게 이어진 수로를 따라 물이 흐르거나 튜브가 떠간다
  · 인피니티풀: 수면 끝이 난간 없이 바깥 풍경과 이어진다
  · 노천: 하늘이나 바깥 풍경이 직접 보이는 야외의 탕·풀
  · 사우나·발한실: 나무 벤치·계단식 좌석이 있는 발한실 내부(문만 보이면 '사우나 입구')
  · 찜질: 찜질방 내부(황토·돌 벽, 눕는 바닥)
  · 히노키·편백: 나무로 된 욕조·탕
  · 워터슬라이드: 미끄럼 튜브 구조물
  · 키즈풀: 아이용 얕은 물과 놀이 구조물
  · 족욕: 발만 담그는 얕은 탕·자리
  숙소 이름·시설 고유 이름(클럽하우스·바스풀·오션월드 등)과 '온천'은 **간판이나 공식 사진 이름**에 있을 때만 쓴다(사진만으로는 알 수 없다).
- focus_x, focus_y: 세로(9:16)로 잘라낼 때 꼭 남겨야 할 중심점. 0.0~1.0 (왼쪽 위가 0,0). 수영장·침대·길 같은 핵심이 들어가게 고른다
- people: 사람이 보이면 true
- quality: 영상 소재로서의 품질 0~10 (해상도·구도·밝기)
- veo_prompt: 이 사진을 4초 영상으로 움직일 때의 영어 지시문 1~2문장. 카메라 움직임 한 가지(drone glide / slow push-in / slow tracking / gentle tilt 등)와 자연스러운 움직임 한 가지(water ripples / curtains sway / leaves sway / light shimmer)만 적는다. 사진에 없는 사물·사람·건물·풍경을 추가하라고 쓰지 않는다. 빠른 움직임·흔들림·줌 급변 금지.
- mismatch: 사용자 메시지에 숙소 이름·지역이 주어졌을 때, 사진이 **그 숙소의 것이 아닐 가능성이 높으면**(지역 지리와 맞지 않음 — 예: 내륙 산간 리조트인데 바다가 보임, 알려진 건물 양식·시설과 다름, 다른 지점 이름의 간판) 그 이유를 한국어 한 줄로. 확실하지 않으면 빈 문자열. mismatch 를 적은 사진은 category 를 "skip" 으로 한다
JSON 만 출력한다: {"photos":[{"k":번호,"category":"...","description":"...","focus_x":0.5,"focus_y":0.5,"people":false,"quality":7,"veo_prompt":"...","mismatch":""}]}"""


# ── 시설 이름 사전 (2026-10-14 운영자 "자쿠지가 아닌데 자쿠지라고 표기") ─────────────────────────────
# 사진에 결정적 증거가 있어야 쓸 수 있는 이름. 분류 설명(description)이 이 이름을 쓰면 컷으로 뽑힌 사진만 비전으로 한 번 더 확인(audit_terms)하고,
# 대본·라벨·훅 제목은 그 컷의 (확인된) 설명에 있는 이름만 쓸 수 있다(make_solo.unseen_terms). kind: "visual" = 사진으로 확인 / "fact" = 공식 표기로만.
FACILITY_TERMS = {
    # 대표 이름: (종류, 글에서 찾는 낱말, 설명에 있으면 인정하는 낱말, 결정적 증거 정의, 바꿀 일반어)
    # 종류 visual = 사진으로 확인(비전) · property = 숙소 전체 성질(공식 사실·확인 시설에 있으면 인정) · name = 특정 장소 이름(공식 사진 이름·페이지 주소에 있을 때만)
    "자쿠지": ("visual", ("자쿠지", "월풀"), ("자쿠지", "월풀"), "물속에서 올라오는 기포·거품이나 벽·바닥의 분사구(제트)가 보이는 월풀 욕조", "온수탕"),
    "파도풀": ("visual", ("파도풀",), ("파도풀",), "물결 띠·하얀 포말로 파도가 치는 것이 보이는 넓은 풀", "실내 풀"),
    "유수풀": ("visual", ("유수풀",), ("유수풀",), "길게 이어진 수로를 따라 물이 흐르거나 튜브가 떠가는 풀", "풀"),
    "인피니티풀": ("visual", ("인피니티",), ("인피니티",), "수면 끝이 난간 없이 바깥 풍경과 이어지는 풀", "야외 풀"),
    "노천탕": ("visual", ("노천",), ("노천", "야외"), "하늘이나 바깥 풍경이 직접 보이는 야외의 탕·풀", "탕"),
    "사우나": ("visual", ("사우나", "발한실"), ("사우나", "발한실"), "나무 벤치·계단식 좌석이 있는 발한실 내부(문만 보이면 아니다)", "스파 공간"),
    "찜질방": ("visual", ("찜질",), ("찜질",), "황토·돌 벽과 눕는 바닥이 있는 찜질방 내부", "휴게 공간"),
    "히노키": ("visual", ("히노키", "편백"), ("히노키", "편백"), "나무(편백)로 된 욕조·탕", "탕"),
    "워터슬라이드": ("visual", ("슬라이드",), ("슬라이드",), "워터 슬라이드(미끄럼 튜브) 구조물", "워터파크"),
    "키즈풀": ("visual", ("키즈풀",), ("키즈풀",), "아이용 얕은 물과 놀이 구조물", "풀"),
    "족욕": ("visual", ("족욕",), ("족욕",), "발만 담그는 얕은 탕·족욕 자리", "탕"),
    "온천": ("property", ("온천",), ("온천",), "", "온수"),
    "바스풀": ("name", ("바스풀",), ("바스풀",), "", "실내 풀"),
    "클럽하우스": ("name", ("클럽하우스",), ("클럽하우스",), "", "건물"),
}


EN_WORDS = {"자쿠지": r"jacuzzi|whirlpool|bubbl|jets?\b", "파도풀": r"\bwaves?\b", "유수풀": r"lazy river|current", "인피니티풀": r"infinity",
            "노천탕": r"open-air|outdoor", "사우나": r"sauna", "히노키": r"hinoki|cypress", "워터슬라이드": r"slide"}


def _josa(text: str, word: str) -> str:
    """바꿔 넣은 낱말 바로 뒤 조사를 받침에 맞춘다(와/과·를/을·는/은·가/이)."""
    code = ord(word[-1]) - 0xAC00 if word else -1
    batchim = 0 <= code < 11172 and code % 28 != 0
    pair = {"와": "과와", "과": "과와", "를": "을를", "을": "을를", "는": "은는", "은": "은는", "가": "이가", "이": "이가"}
    return re.sub(rf"({re.escape(word)})(와|과|를|을|는|은|가|이)(?=[\s.,!?]|$)",
                  lambda m: m.group(1) + pair[m.group(2)][0 if batchim else 1], text)


def facility_terms(text: str) -> list[str]:
    """글에 나온 시설 이름(사전 대표 이름)."""
    t = str(text or "")
    return [k for k, v in FACILITY_TERMS.items() if any(w in t for w in v[1])]


def term_ok(term: str, desc: str) -> bool:
    """설명(확인본)이 이 시설 이름을 인정하는지 — 대본·라벨·훅 제목 검사용."""
    return any(w in str(desc or "") for w in FACILITY_TERMS[term][2])


AUDIT_SYSTEM = """너는 숙소 사진 검수자다. 사진 1장과, 그 사진 설명에 쓰인 시설 이름들의 정의를 받는다.
이름마다 **이 사진에 그 정의의 결정적 증거가 실제로 보이는지**만 판단한다. 분위기·조명·주변 맥락·상식으로 추측하지 않는다(둥근 탕 = 자쿠지가 아니다).
보이면 seen=true 와 증거(무엇이 어디에 보이는지), 안 보이면 seen=false.
plain: 확인되지 않은 이름을 빼고, 사진에 보이는 모양·재질·조명만으로 쓴 한국어 설명 한 문장(확인된 이름은 써도 된다).
JSON 만: {"terms":[{"term":"이름","seen":true|false,"evidence":"..."}],"plain":"..."}"""


def audit_terms(model: str, shot: dict, facts: str = "", raise_errors: bool = False, offline: str = "") -> dict:
    """뽑힌 사진의 설명에 든 시설 이름을 확인한다(비전 1번 · 약 1원, 이름이 없으면 호출 0).
    visual = 비전 확인 · property(온천) = 공식 사실·확인 시설에 있으면 인정 · name(바스풀·클럽하우스) = 공식 사진 이름·페이지 주소에 있을 때만
    (숙소에 클럽하우스가 있다고 이 사진이 클럽하우스인 것은 아니다). 확인 안 된 이름은 설명에서 빼고 일반어 설명으로 바꾼다.
    shot 을 고친다: description(확인본) · description_raw(원래) · term_audit(기록)."""
    desc = str(shot.get("description") or "")
    found = facility_terms(desc)
    if not found:
        return {}
    alt = str(shot.get("src_alt") or (shot.get("name") if shot.get("source") == "coupang" else "") or "")   # 쿠팡은 상품 이름이 공식 표기
    page = urllib.parse.unquote(str(shot.get("src_page") or ""))
    rec = {"raw": desc, "terms": {}}
    visual = []
    for k in found:
        kind, words = FACILITY_TERMS[k][0], FACILITY_TERMS[k][1]
        if any(w in alt for w in words):                                   # 공식 사진 이름에 있으면 확인된 것
            rec["terms"][k] = {"seen": True, "evidence": f"공식 사진 이름 '{alt}'"}
        elif kind == "property":
            ok = any(w in facts for w in words)
            rec["terms"][k] = {"seen": ok, "evidence": "공식 사실·확인 시설" if ok else "공식 표기 없음"}
        elif kind == "name":
            ok = any(w in page for w in words)
            rec["terms"][k] = {"seen": ok, "evidence": f"페이지 주소 {page[-30:]}" if ok else "공식 사진 이름·페이지에 없음(숙소에 있다고 이 사진이 그곳은 아님)"}
        else:
            visual.append(k)
    plain = ""
    if visual and offline:                                                 # 비전 호출이 모두 실패 → 보수적으로 확인 안 된 것으로
        for k in visual:
            rec["terms"][k] = {"seen": False, "evidence": f"검수 실패: {offline}"}
        visual = []
    if visual:
        lines = "\n".join(f"- {k}: {FACILITY_TERMS[k][3]}" for k in visual)
        body = {"system_instruction": {"parts": [{"text": AUDIT_SYSTEM}]},
                "contents": [{"role": "user", "parts": [{"text": f"사진 설명: {desc}\n확인할 이름과 정의:\n{lines}"},
                                                        {"inline_data": {"mime_type": "image/jpeg", "data": _small_jpeg_b64(shot["path"], 1024)}}]}],
                "generationConfig": {"maxOutputTokens": 600, "temperature": 0.0, "responseMimeType": "application/json"}}
        try:
            data = _gpost(f"models/{model}:generateContent", body, 90)
            txt = "".join(p.get("text", "") for p in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []))
            js = json.loads(re.sub(r"^```(?:json)?|```$", "", txt.strip()).strip())
            got = {}
            for t in js.get("terms") or []:
                name = str(t.get("term", ""))
                key = next((k for k in visual if k in name or any(w in name for w in FACILITY_TERMS[k][1])), None)
                if key:
                    got[key] = {"seen": t.get("seen") is True, "evidence": str(t.get("evidence", ""))[:80]}
            for k in visual:
                rec["terms"][k] = got.get(k, {"seen": False, "evidence": "답 없음 — 확인 안 된 것으로"})
            plain = str(js.get("plain") or "").strip()[:120]
        except Exception as e:  # noqa: BLE001
            if raise_errors:
                raise
            for k in visual:                                              # 검수 실패면 보수적으로: 확인 안 된 것으로 본다
                rec["terms"][k] = {"seen": False, "evidence": f"검수 실패: {str(e)[:50]}"}
    bad = [k for k, v in rec["terms"].items() if not v["seen"]]
    if bad:
        new = plain if plain and not any(w in plain for k in bad for w in FACILITY_TERMS[k][1]) else desc
        for k in bad:                                                      # plain 이 없거나 이름을 다시 쓰면 낱말만 일반어로 바꾸고 조사를 맞춘다
            fb = FACILITY_TERMS[k][4]                                      # (preview-terms-1 실측: '클럽하우스와' → 빈칸 '곡선형 와' 사고)
            for w in FACILITY_TERMS[k][1]:
                new = _josa(re.sub(rf"(?:온수\s*)?{w}", fb, new), fb)
        new = re.sub(r"\s{2,}", " ", new).strip()
        shot["description_raw"] = desc
        shot["description"] = new
        rec["fixed"] = new
        en = "|".join(EN_WORDS[k] for k in bad if k in EN_WORDS)                # Veo 지시문에서도 그 시설을 부르는 문장을 뺀다(없는 거품·파도를 그리지 않게)
        if en and shot.get("prompt"):
            shot["prompt"] = " ".join(x for x in re.split(r"(?<=[.!?])\s+", shot["prompt"]) if not re.search(en, x, re.I))
        log(f"사진 {shot.get('k')} 시설 이름 확인 안 됨 {bad} → 설명 교체: {desc} → {new}")
    shot["term_audit"] = rec
    return rec


def context_for(name: str, city: str = "", facts: list[str] | None = None) -> str:
    """분류 호출에 붙이는 숙소 맥락 — 공식 홈페이지엔 같은 그룹 다른 지점 사진(프로모션)이 섞인다 (p3 실측: 홍천 비발디파크에 바다 인피니티풀)."""
    s = (f"이 사진들은 숙소 '{name}'" + (f"({city})" if city else "") + " 의 공식 홈페이지와 쿠팡 상품 사진에서 모았다. "
         "공식 홈페이지에는 같은 그룹의 다른 지점 사진(프로모션 배너)이 섞여 있을 수 있다. "
         + (f"'{city}' 의 지리(바다·산·도시)와 " if city else "") + "이 숙소의 알려진 모습에 맞지 않는 사진은 mismatch 에 이유를 적고 category 를 skip 으로 한다. ")
    if facts:
        s += f"블로그로 확인된 이 숙소의 시설: {', '.join(facts)}. "
    return s + "확실하지 않으면 mismatch 는 비워 둔다."


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


def gather(items: list, operator_dir: Path, build: Path, official: list[dict] | None = None) -> list[dict]:
    """후보 사진 목록. 운영자 폴더 → 공식 홈페이지 수집본(src/crawl_photos.py, 2026-10-11 운영자 결정) → 쿠팡 순.
    같은 사진(내용 해시)은 한 번만. 공식 홈페이지 사진은 출처(url·page)를 함께 들고 다닌다 (장부용)."""
    cands, seen = [], set()

    def add(data: bytes, source: str, name: str, index=None, extra: dict | None = None):
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
        cands.append({"k": k, "source": source, "name": name, "index": index, "path": str(dest), "size": list(size), **(extra or {})})

    if operator_dir.is_dir():
        for p in sorted(operator_dir.iterdir()):
            if p.suffix.lower() in EXTS and p.is_file():
                add(p.read_bytes(), "operator", p.name)
    for i, p in enumerate(official or []):
        try:
            add(Path(p["path"]).read_bytes(), "official", str(p.get("url", ""))[-60:], i,
                {"src_url": p.get("url"), "src_page": p.get("page"), "src_alt": p.get("alt") or ""})
        except Exception as e:  # noqa: BLE001
            log(f"공식 홈페이지 사진 읽기 실패 ({i}): {e}")
    for i, it in enumerate(items):
        url = str(it.get("productImage") or "")
        if not url.startswith("http"):
            continue
        try:
            add(_download(url), "coupang", str(it.get("productName", ""))[:60], i)
        except Exception as e:  # noqa: BLE001
            log(f"쿠팡 사진 내려받기 실패 ({i}): {e}")
    log(f"후보 사진 {len(cands)}장 (운영자 {sum(c['source'] == 'operator' for c in cands)} · "
        f"공식 홈페이지 {sum(c['source'] == 'official' for c in cands)} · 쿠팡 {sum(c['source'] == 'coupang' for c in cands)})")
    return cands


# ── Gemini 비전 ────────────────────────────────────────────────────────
USAGE_HOOK = None                            # make_stay.track_usage 가 꽂힌다 (비용 추정)


def _gpost(path: str, body: dict, timeout: int = 180) -> dict:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    req = urllib.request.Request(f"{GEMINI}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        if USAGE_HOOK:                       # make_stay 가 토큰 수를 모아 추정 비용을 낸다
            USAGE_HOOK(data)
        return data
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


def _src_label(c: dict) -> str:
    if c["source"] == "operator":
        return "운영자가 준 사진"
    if c["source"] == "official":
        return (f"공식 홈페이지 사진 (페이지 {str(c.get('src_page') or '')[-40:]}" + (f" · 공식 사진 이름 '{c['src_alt']}'" if c.get("src_alt") else "") + ")")
    return f"쿠팡 객실 상품 '{c['name']}'"


def classify(model: str, cands: list[dict], context: str = "") -> list[dict]:
    """사진마다 분류·설명·초점·지시문(+ 다른 지점 의심 mismatch). 돌려주는 목록은 cands 와 같은 순서(k 기준).
    context: 숙소 이름·지역·확인된 시설 (context_for) — 있으면 지리에 안 맞는 사진을 걸러낸다."""
    listing = "\n".join(f"사진 {c['k']}: {_src_label(c)}" for c in cands)
    parts = [{"text": (context + "\n\n" if context else "") + f"사진 {len(cands)}장. 각 사진 앞에 번호를 적어 둔다.\n{listing}"}]
    for c in cands:
        parts.append({"text": f"사진 {c['k']}:"})
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": _small_jpeg_b64(c["path"])}})
    body = {"system_instruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 8000, "temperature": 0.1,          # 0.4 → 0.1: 같은 사진의 설명이 실행마다 바뀌지 않게
                                 "responseMimeType": "application/json",
                                 "thinkingConfig": {"thinkingBudget": 0}}}
    got = {}
    for attempt in range(3):                      # 답이 JSON 이 아니면 다시 (0원에 가까운 단계). 2026-10-11 stay-run-8 에서 2회 연속 실패 → 3회 + 잘린 JSON 복구
        try:
            data = _gpost(f"models/{model}:generateContent", body)
        except RuntimeError as e:
            if "thinking" not in str(e).lower():
                raise
            body["generationConfig"].pop("thinkingConfig", None)
            data = _gpost(f"models/{model}:generateContent", body)
        cand = (data.get("candidates") or [{}])[0]
        txt = "".join(p.get("text", "") for p in ((cand.get("content") or {}).get("parts") or []))
        txt = re.sub(r"^```(?:json)?|```$", "", txt.strip()).strip()
        # 실측(stay-run-8): {"photos":[...]} 대신 맨 바깥이 리스트([{"k":0,...}])로 올 때가 있다 → 둘 다 받는다
        starts = [i for i in (txt.find("{"), txt.find("[")) if i >= 0]
        if starts:
            s0 = min(starts)
            e0 = max(txt.rfind("}"), txt.rfind("]"))
            if e0 > s0:
                txt = txt[s0:e0 + 1]
        try:
            js = json.loads(txt)
            items_js = js if isinstance(js, list) else (js.get("photos") or []) if isinstance(js, dict) else []
            got = {int(p.get("k", -1)): p for p in items_js if isinstance(p, dict)}
            if got:
                break
            raise ValueError("항목 없음")
        except (ValueError, AttributeError) as e:
            # 출력이 잘렸으면(MAX_TOKENS) 완성된 항목만 건진다
            items = re.findall(r"\{[^{}]*\"k\"\s*:\s*\d+[^{}]*\}", txt)
            salvaged = []
            for it in items:
                try:
                    salvaged.append(json.loads(it))
                except ValueError:
                    continue
            if len(salvaged) >= max(1, len(cands) // 2):
                got = {int(p.get("k", -1)): p for p in salvaged}
                log(f"분류 JSON 이 잘려 {len(salvaged)}/{len(cands)}개만 복구 (finish={cand.get('finishReason')})")
                break
            log(f"분류 답이 JSON 이 아님 (시도 {attempt + 1}, finish={cand.get('finishReason')}): {str(e)[:60]} / {txt[:80]!r}")
    if not got:
        raise RuntimeError("사진 분류 답을 읽지 못했습니다 (JSON 아님)")
    out = []
    for c in cands:
        p = got.get(c["k"]) or {}
        cat = str(p.get("category", "skip")).strip().lower()
        if cat not in CATS:
            cat = "skip"
        mismatch = str(p.get("mismatch") or "").strip()[:100]
        if mismatch:
            cat = "skip"

        def f01(v, d=0.5):
            try:
                return min(1.0, max(0.0, float(v)))
            except (TypeError, ValueError):
                return d
        out.append({**c, "category": cat, "description": str(p.get("description", ""))[:120],
                    "focus_x": f01(p.get("focus_x")), "focus_y": f01(p.get("focus_y")),
                    "people": bool(p.get("people", False)), "quality": _q(p.get("quality")),
                    "veo_prompt": str(p.get("veo_prompt", "")).strip()[:400], "mismatch": mismatch})
    for o in out:
        log(f"사진 {o['k']} [{o['source']}] → {o['category']} q{o['quality']} {o['description'][:50]}" + (f" ⚠ 다른 지점 의심: {o['mismatch']}" if o["mismatch"] else ""))
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
