#!/usr/bin/env python3
"""테마·지역 → 숙소 후보 발굴 → 쿠팡 검증 → 점수표. 영상·Veo 없음 (Gemini 글·비전 호출만, 수십 원).

    python3 src/discover.py                    requests/discover/request.json 을 읽는다
    python3 src/discover.py --tour-scan 32     TourAPI 한 지역의 숙박·시설을 긁어 캐시만 만든다 (키 필요)

request.json
    {"nonce": "...", "theme": "실내 온수풀·온천", "region": "강원", "month": "2026-11", "count": 20,
     "keywords": ["온천", "온수풀", "실내수영장", "스파", "사우나"]}        ← keywords 는 선택 (없으면 theme 에서 뽑는다)

3겹 구조 (2026-10-09 운영자 선택)
  1겹 후보 생성 — Gemini(지역·테마에 맞는 실제 숙소 이름, 지어낼 수 있음) + 네이버 지역검색 API(질의당 5건)
                 + TourAPI(공공누리, 시설 항목: 사우나·대중탕·부대시설 글) → 이름 합치고 중복 제거
  2겹 쿠팡 검증 — 이름으로 쿠팡 검색 → 객실(패키지·입장권 제외) 2개 이상이어야 '판매 중'. 객실 이름의 테마 키워드,
                 사진을 Gemini 비전으로 분류(물놀이/객실/특별 — src/photos.py 재사용)
  3겹 점수·선정 — 테마 근거(객실 이름 + TourAPI 시설 + 사진) · 사진 충분(7장) · 출처 겹침 → 순위. 상위 3곳 강조
출력
  data/discover/latest/candidates.json · candidates.md(표) · summary.txt(텔레그램용) · sheet_N.jpg(상위 3곳 쿠팡 사진 모음)
  data/discover/prices/YYYY-MM-DD.json — 후보별 쿠팡 최저 객실가 기록 (자체 가격 기록의 시작. 영상엔 아직 안 쓴다)
  data/discover/tourapi/area_<code>.json — TourAPI 지역 시설 캐시 (공공 데이터, 키 없음)
규칙
  - 스크래핑 없음. 쿠팡 API·네이버 API·TourAPI·Gemini 만. 제휴 링크를 따라가지 않는다.
  - TourAPI 사진은 공공누리 3유형(변경 금지)이라 영상에 쓰지 않는다. 시설 사실만 쓴다.
  - 키가 없는 겹은 건너뛰고 그 사실을 결과에 적는다 (새 키 이름을 만들지 않는다: NAVER_CLIENT_ID/SECRET, TOUR_API_KEY).
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_stay as ms  # noqa: E402
import photos  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REQUEST = ROOT / "requests" / "discover" / "request.json"
OUT = ROOT / "data" / "discover"
LATEST = OUT / "latest"
BUILD = ROOT / "build" / "discover"

AREA = {"서울": 1, "인천": 2, "대전": 3, "대구": 4, "광주": 5, "부산": 6, "울산": 7, "세종": 8, "경기": 31, "강원": 32,
        "충북": 33, "충남": 34, "경북": 35, "경남": 36, "전북": 37, "전남": 38, "제주": 39}
SUBREGIONS = {"강원": ["강릉", "속초", "양양", "평창", "정선", "홍천", "춘천", "원주", "동해", "삼척", "고성"],
              "제주": ["제주시", "서귀포", "애월", "중문", "성산", "함덕"],
              "경기": ["가평", "양평", "파주", "용인", "포천", "안성"],
              "부산": ["해운대", "기장", "광안리", "송도"], "전남": ["여수", "순천", "담양", "완도"],
              "경남": ["거제", "통영", "남해", "창원"], "경북": ["경주", "포항", "안동", "울진"],
              "충남": ["태안", "보령", "아산", "부여"], "충북": ["충주", "제천", "단양", "청주"]}
PACKAGE_RE = re.compile(r"출발|항공|패키지|입장권|이용권|투어|자유여행|\d\s*박\s*\d\s*일|왕복|렌터카")
DEFAULT_KEYWORDS = ["온천", "온수풀", "온수 풀", "실내수영장", "실내 수영장", "수영장", "스파", "사우나", "자쿠지", "히노키", "노천탕", "찜질", "풀빌라", "인피니티", "워터파크"]

TOUR = "https://apis.data.go.kr/B551011/KorService2"
NAVER = "https://openapi.naver.com/v1/search/local.json"


def log(*a):
    print("[discover]", *a, flush=True)


def norm(name: str) -> str:
    s = re.sub(r"<[^>]+>", "", str(name)).lower()
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    return re.sub(r"[\s&·\-_,./'\"]+", "", s)


def same(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb or (len(na) >= 4 and (na in nb or nb in na)):
        return True
    return difflib.SequenceMatcher(None, na, nb).ratio() >= 0.86


# ── 1겹 후보 생성 ──────────────────────────────────────────────────────
GEN_SYSTEM = """너는 국내 숙소 큐레이터다. 지역과 테마에 맞는 **실제로 존재하는** 숙소(호텔·리조트·펜션·풀빌라)의 공식 이름을 고른다.
- 쿠팡 트래블 같은 예약 사이트에 올라올 만한, 검색하면 나오는 정확한 이름만 쓴다 (지점명 포함. 예: "롯데리조트 속초").
- 확실하지 않은 이름은 넣지 않는다. 지어내면 뒤 단계에서 걸러지지만 비용이 든다.
- 테마 근거(어떤 시설이 있다고 알려져 있는지)를 why 에 한 줄로 쓴다. 모르면 "근거 불확실"이라고 쓴다.
JSON 만 출력한다: {"stays":[{"name":"...","city":"시·군","why":"..."}]}"""


def gemini_candidates(model: str, theme: str, region: str, month: str, n: int) -> list[dict]:
    content = f"지역: {region}\n테마: {theme}\n시기: {month}\n숙소 {n}곳을 골라라."
    data = ms.gemini_json(model, GEN_SYSTEM, content)
    out = []
    for s in (data.get("stays") or [])[: n + 5]:
        name = str(s.get("name", "")).strip()
        if name:
            out.append({"name": name, "source": "gemini", "city": str(s.get("city", ""))[:20], "why": str(s.get("why", ""))[:100]})
    return out


def naver_candidates(region: str, keywords: list[str]) -> tuple[list[dict], str]:
    cid = (os.environ.get("NAVER_CLIENT_ID") or "").strip()
    sec = (os.environ.get("NAVER_CLIENT_SECRET") or "").strip()
    if not cid or not sec:
        return [], "네이버 키 없음 — 건너뜀"
    subs = SUBREGIONS.get(region, [region])
    kws = [k for k in keywords if " " not in k][:4] or ["온천"]
    out, errors, calls = [], 0, 0
    for sub in subs:
        for kw in kws:
            q = f"{sub} {kw} 호텔" if kw not in ("풀빌라", "펜션") else f"{sub} {kw}"
            url = f"{NAVER}?" + urllib.parse.urlencode({"query": q, "display": 5, "start": 1, "sort": "random"})
            req = urllib.request.Request(url, headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": sec})
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    js = json.loads(r.read().decode("utf-8"))
                calls += 1
            except urllib.error.HTTPError as e:
                errors += 1
                if e.code in (401, 403):
                    return out, f"네이버 지역검색 권한 없음 (HTTP {e.code}) — 건너뜀"
                continue
            except Exception:  # noqa: BLE001
                errors += 1
                continue
            for it in js.get("items") or []:
                if "숙박" not in str(it.get("category", "")):
                    continue
                name = re.sub(r"<[^>]+>", "", str(it.get("title", ""))).strip()
                if name:
                    out.append({"name": name, "source": "naver", "city": sub, "why": f"네이버 '{q}' · {it.get('category')}"})
            time.sleep(0.15)
    return out, f"네이버 {calls}회 호출 · 오류 {errors}"


# ── TourAPI (시설 사실) ────────────────────────────────────────────────
def _tour(op: str, **p) -> dict | None:
    key = (os.environ.get("TOUR_API_KEY") or "").strip()
    if not key:
        return None
    q = {"serviceKey": key, "MobileOS": "ETC", "MobileApp": "stayshorts", "_type": "json", **p}
    url = f"{TOUR}/{op}?" + urllib.parse.urlencode(q)
    for attempt in range(4):                              # 실측: 서버가 연결을 자주 끊는다 → 재시도·간격
        try:
            req = urllib.request.Request(url, headers={"Connection": "close", "User-Agent": "stay-shorts-discover"})
            with urllib.request.urlopen(req, timeout=40) as r:
                js = json.loads(r.read().decode("utf-8", "replace"))
            body = (js.get("response") or {}).get("body") or {}
            time.sleep(1.0)
            return body
        except Exception as e:  # noqa: BLE001
            if attempt == 3:
                log(f"TourAPI {op} 실패: {str(e)[:80]}")
            time.sleep(3 + 3 * attempt)
    return None


def _items(body) -> list:
    return ((body or {}).get("items") or {}).get("item") or []


def tour_scan(area_code: int) -> list[dict]:
    """지역의 숙박 전체 + 시설 항목. 캐시가 있으면 그대로 쓴다 (시설은 거의 안 바뀐다)."""
    cache = OUT / "tourapi" / f"area_{area_code}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    if not (os.environ.get("TOUR_API_KEY") or "").strip():
        return []
    stays, page = [], 1
    while True:
        body = _tour("searchStay2", areaCode=area_code, numOfRows=100, pageNo=page, arrange="Q")
        got = _items(body)
        stays += got
        if len(got) < 100 or page >= 10:
            break
        page += 1
    log(f"TourAPI 지역 {area_code} 숙박 {len(stays)}건 → 시설 조회 시작 (건당 1초)")
    out = []
    for i, s in enumerate(stays):
        intro = (_items(_tour("detailIntro2", contentId=s["contentid"], contentTypeId=32)) or [{}])[0]
        out.append({"contentid": s.get("contentid"), "title": s.get("title"), "addr": s.get("addr1"),
                    "sigungu": s.get("sigungucode"), "has_image": bool(s.get("firstimage")),
                    "sauna": str(intro.get("sauna", "")), "publicbath": str(intro.get("publicbath", "")),
                    "fitness": str(intro.get("fitness", "")), "sports": str(intro.get("sports", "")),
                    "subfacility": str(intro.get("subfacility", ""))[:200], "roomtype": str(intro.get("roomtype", ""))[:40],
                    "checkin": str(intro.get("checkintime", ""))[:20]})
        if i % 25 == 0:
            log(f"  시설 {i + 1}/{len(stays)}")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"area": area_code, "scanned": date.today().isoformat(), "stays": out},
                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def tour_facts(entry: dict, keywords: list[str]) -> tuple[list[str], bool]:
    """시설 항목에서 테마 근거를 뽑는다. (근거 목록, 테마 관련 여부)"""
    facts = []
    if entry.get("sauna") == "1":
        facts.append("사우나")
    if entry.get("publicbath") == "1":
        facts.append("대중탕")
    if entry.get("fitness") == "1":
        facts.append("피트니스")
    if entry.get("sports") == "1":
        facts.append("스포츠시설")
    sub = entry.get("subfacility") or ""
    hits = sorted({k.replace(" ", "") for k in keywords if k.replace(" ", "") in sub.replace(" ", "")})
    hits = [h for h in hits if not any(h != o and h in o for o in hits)]      # "수영장"과 "실내수영장"이 겹치면 긴 쪽만
    if hits:
        facts.append("부대시설: " + ", ".join(hits))
    themed = bool(hits) or entry.get("sauna") == "1" or entry.get("publicbath") == "1"
    return facts, themed


def tour_match(name: str, scan: dict) -> dict | None:
    for e in (scan or {}).get("stays", []):
        if same(name, e.get("title", "")):
            return e
    return None


# ── 2겹 쿠팡 검증 ──────────────────────────────────────────────────────
def coupang_verify(name: str, keywords: list[str]) -> dict:
    try:
        items = ms.coupang_search(name, 10)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120], "rooms": [], "items": []}
    rooms = [it for it in items if not PACKAGE_RE.search(str(it.get("productName", "")))]
    joined = " ".join(str(it.get("productName", "")) for it in rooms).replace(" ", "")
    hits = sorted({k for k in keywords if k.replace(" ", "") in joined})
    prices = [float(it.get("productPrice") or 0) for it in rooms if float(it.get("productPrice") or 0) > 0]
    return {"ok": len(rooms) >= 2, "items": items, "rooms": rooms, "rooms_n": len(rooms), "theme_hits": hits,
            "min_price": min(prices) if prices else None,
            "room_names": [str(it.get("productName", ""))[:40] for it in rooms[:6]]}


def photo_check(model: str, name: str, rooms: list, build: Path) -> dict:
    build.mkdir(parents=True, exist_ok=True)
    cands = photos.gather(rooms, ROOT / "requests" / "produce" / "photos_none", build)
    if not cands:
        return {"usable": 0, "water": 0, "room": 0, "special": 0, "skip": 0, "people": 0, "classified": []}
    cl = photos.classify(model, cands)
    cnt = {c: sum(1 for p in cl if p["category"] == c and p["quality"] >= 3) for c in ("water", "room", "special")}
    return {"usable": sum(cnt.values()), **cnt, "skip": sum(1 for p in cl if p["category"] == "skip"),
            "people": sum(1 for p in cl if p.get("people")), "classified": cl}


# ── 3겹 점수 ───────────────────────────────────────────────────────────
def score(c: dict) -> tuple[int, list[str]]:
    s, why = 0, []
    v, ph = c.get("coupang") or {}, c.get("photos") or {}
    if v.get("theme_hits"):
        s += min(3, len(v["theme_hits"])); why.append("객실 이름: " + ", ".join(v["theme_hits"]))
    if c.get("tour_themed"):
        s += 2; why.append("TourAPI 시설: " + ", ".join(c.get("tour_facts") or []))
    if ph.get("water", 0) >= 3:
        s += 3; why.append(f"물놀이 사진 {ph['water']}장")
    elif ph.get("water", 0) >= 1:
        s += 1; why.append(f"물놀이 사진 {ph['water']}장")
    if ph.get("usable", 0) >= 7:
        s += 2; why.append(f"쓸 수 있는 사진 {ph['usable']}장")
    elif ph.get("usable", 0) >= 5:
        s += 1; why.append(f"사진 {ph['usable']}장 (운영자 보완 필요)")
    if ph.get("room", 0) >= 1 and ph.get("special", 0) >= 1:
        s += 1; why.append("객실·특별 공간 사진 있음")
    n_src = len(c.get("sources") or [])
    if n_src >= 2:
        s += n_src - 1; why.append(f"출처 {n_src}곳 일치")
    return s, why


def sheet(cl: list[dict], out: Path, title: str):
    """후보 한 곳의 쿠팡 사진 모음 (분류 라벨 포함) — 운영자가 눈으로 고르게."""
    from PIL import Image, ImageDraw, ImageFont
    f = ImageFont.truetype(ms.font_path(), 26)
    cols, w, h = 5, 216, 216
    rows = (len(cl) + cols - 1) // cols
    im = Image.new("RGB", (cols * w, rows * (h + 34) + 44), (18, 18, 18))
    d = ImageDraw.Draw(im)
    d.text((10, 8), title, font=f, fill=(255, 232, 107))
    for i, p in enumerate(cl):
        try:
            t = Image.open(p["path"]).convert("RGB"); t.thumbnail((w, h))
        except Exception:  # noqa: BLE001
            continue
        x, y = (i % cols) * w, 44 + (i // cols) * (h + 34)
        im.paste(t, (x + (w - t.width) // 2, y))
        d.text((x + 6, y + h + 4), f"{photos.KO.get(p['category'], '제외')} q{p['quality']}", font=f, fill=(255, 255, 255))
    im.save(out, "JPEG", quality=82)


def run(req: dict) -> dict:
    theme = str(req.get("theme") or "").strip()
    region = str(req.get("region") or "").strip()
    month = str(req.get("month") or "").strip()
    count = int(req.get("count") or 20)
    keywords = [str(k) for k in (req.get("keywords") or [])] or [k for k in DEFAULT_KEYWORDS if any(w in theme for w in (k[:2],))] or DEFAULT_KEYWORDS
    if not theme or not region:
        raise SystemExit("request.json 에 theme 과 region 이 필요합니다")
    BUILD.mkdir(parents=True, exist_ok=True)
    LATEST.mkdir(parents=True, exist_ok=True)
    for old in LATEST.glob("sheet_*.jpg"):
        old.unlink()
    report = {"nonce": req.get("nonce"), "theme": theme, "region": region, "month": month, "keywords": keywords,
              "ran_at": date.today().isoformat(), "layers": {}, "candidates": []}
    models = ms.pick_models()

    # 1겹
    gem = ms._try_models("text", models["text"], lambda m: gemini_candidates(m, theme, region, month, count))
    report["layers"]["gemini"] = f"{len(gem)}곳"
    nav, nav_note = naver_candidates(region, keywords)
    report["layers"]["naver"] = f"{len(nav)}곳 · {nav_note}"
    scan = tour_scan(AREA.get(region, 0)) if region in AREA else []
    tour_list = []
    for e in (scan or {}).get("stays", []) if scan else []:
        facts, themed = tour_facts(e, keywords)
        if themed:
            tour_list.append({"name": e["title"], "source": "tourapi", "city": str(e.get("addr", ""))[:20], "why": " · ".join(facts)})
    report["layers"]["tourapi"] = (f"지역 숙박 {len((scan or {}).get('stays', []))}건 중 테마 시설 {len(tour_list)}곳"
                                  if scan else "TourAPI 캐시·키 없음 — 건너뜀")

    # 합치기 (같은 이름은 출처를 모은다)
    merged: list[dict] = []
    for c in gem + nav + tour_list:
        for m in merged:
            if same(c["name"], m["name"]):
                m["sources"].append(c["source"]); m["why"].append(c["why"]); break
        else:
            merged.append({"name": c["name"], "city": c.get("city", ""), "sources": [c["source"]], "why": [c["why"]]})
    # 출처가 겹치는 것 먼저, 그다음 Gemini·네이버·TourAPI 순. 검증 비용 때문에 상한을 둔다
    merged.sort(key=lambda m: (-len(set(m["sources"])), ["gemini", "naver", "tourapi"].index(m["sources"][0])))
    cap = int(req.get("verify_cap") or 40)
    merged = merged[:cap]
    log(f"후보 {len(merged)}곳 (Gemini {len(gem)} · 네이버 {len(nav)} · TourAPI {len(tour_list)}) → 쿠팡 검증")

    # 2겹
    prices = {}
    for i, c in enumerate(merged):
        c["sources"] = sorted(set(c["sources"]))
        v = coupang_verify(c["name"], keywords)
        c["coupang"] = {k: v.get(k) for k in ("ok", "error", "rooms_n", "theme_hits", "min_price", "room_names")}
        te = tour_match(c["name"], scan) if scan else None
        if te:
            c["tour_facts"], c["tour_themed"] = tour_facts(te, keywords)
            c["tour_addr"] = te.get("addr")
        if v.get("ok"):
            if v.get("min_price"):
                prices[c["name"]] = v["min_price"]
            try:
                ph = ms._try_models("vision", models["text"], lambda m: photo_check(m, c["name"], v["rooms"], BUILD / f"c{i}"))
            except Exception as e:  # noqa: BLE001
                ph = {"usable": 0, "water": 0, "room": 0, "special": 0, "error": str(e)[:100], "classified": []}
            c["photos"] = {k: ph.get(k) for k in ("usable", "water", "room", "special", "skip", "people", "error")}
            c["_classified"] = ph.get("classified") or []
            c["affiliate_url"] = str((v["rooms"][0] or {}).get("productUrl", ""))
        c["score"], c["reasons"] = score(c)
        log(f"  {c['name']}: 쿠팡 {'OK' if v.get('ok') else 'X'} 객실 {v.get('rooms_n', 0)} · 점수 {c['score']}")
        time.sleep(0.6)

    # 3겹
    passed = [c for c in merged if (c.get("coupang") or {}).get("ok")]
    passed.sort(key=lambda c: -c["score"])
    for rank, c in enumerate(passed[:3], 1):
        if c.get("_classified"):
            sheet(c["_classified"], LATEST / f"sheet_{rank}.jpg", f"{rank}. {c['name']} — 쿠팡 사진 {len(c['_classified'])}장")
    for c in merged:
        c.pop("_classified", None)
    report["candidates"] = passed + [c for c in merged if c not in passed]
    report["summary"] = {"generated": len(merged), "coupang_ok": len(passed), "models": dict(ms.USED)}

    # 기록
    (LATEST / "candidates.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if prices:
        pdir = OUT / "prices"; pdir.mkdir(parents=True, exist_ok=True)
        pf = pdir / f"{date.today().isoformat()}.json"
        old = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
        old.update({k: int(v) for k, v in prices.items()})
        pf.write_text(json.dumps(old, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    md = [f"# 숙소 후보 — {region} · {theme} · {month} ({report['ran_at']})", "",
          f"- 후보 {len(merged)}곳 (Gemini {report['layers']['gemini']} / 네이버 {report['layers']['naver']} / TourAPI {report['layers']['tourapi']})",
          f"- 쿠팡에서 판매 확인(객실 2개 이상) {len(passed)}곳", "",
          "| 순위 | 숙소 | 점수 | 출처 | 쿠팡 객실 | 근거 | 사진(물/객실/특별) | 최저 객실가(조회값) |", "|---|---|---|---|---|---|---|---|"]
    for i, c in enumerate(passed, 1):
        v, ph = c["coupang"], c.get("photos") or {}
        md.append(f"| {i} | {c['name']} | {c['score']} | {'+'.join(c['sources'])} | {v.get('rooms_n')} | {'; '.join(c['reasons'])[:120]} | "
                  f"{ph.get('water', 0)}/{ph.get('room', 0)}/{ph.get('special', 0)} | {int(v['min_price']):,}원 |" if v.get("min_price") else
                  f"| {i} | {c['name']} | {c['score']} | {'+'.join(c['sources'])} | {v.get('rooms_n')} | {'; '.join(c['reasons'])[:120]} | "
                  f"{ph.get('water', 0)}/{ph.get('room', 0)}/{ph.get('special', 0)} | - |")
    md += ["", "## 쿠팡에서 못 찾은 후보", ""]
    for c in merged:
        if c not in passed:
            md.append(f"- {c['name']} ({'+'.join(c['sources'])}) — 객실 {c['coupang'].get('rooms_n', 0)}개 {c['coupang'].get('error') or ''}")
    (LATEST / "candidates.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    top = passed[:5]
    lines = [f"숙소 후보 발굴 — {region} · {theme} · {month}", f"후보 {len(merged)}곳 중 쿠팡 판매 확인 {len(passed)}곳 (영상 제작 없음)"]
    for i, c in enumerate(top, 1):
        ph = c.get("photos") or {}
        lines.append(f"{i}. {c['name']} (점수 {c['score']}, 객실 {c['coupang'].get('rooms_n')}, 사진 물{ph.get('water', 0)}/객{ph.get('room', 0)}/특{ph.get('special', 0)}) — {'; '.join(c['reasons'])[:90]}")
    lines.append("표 전체: data/discover/latest/candidates.md")
    (LATEST / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tour-scan", type=int, default=0, help="TourAPI 지역 코드 하나를 긁어 캐시만 만든다")
    a = ap.parse_args()
    if a.tour_scan:
        cache = OUT / "tourapi" / f"area_{a.tour_scan}.json"
        if cache.exists():
            cache.unlink()
        scan = tour_scan(a.tour_scan)
        n = len(scan.get("stays", [])) if scan else 0
        themed = sum(1 for e in (scan or {}).get("stays", []) if tour_facts(e, DEFAULT_KEYWORDS)[1])
        print(f"지역 {a.tour_scan}: 숙박 {n}건 · 테마 시설 있음 {themed}곳 → {cache.relative_to(ROOT) if n else '실패'}")
        return 0 if n else 1
    req = json.loads(REQUEST.read_text(encoding="utf-8"))
    try:
        run(req)
        return 0
    except Exception as e:  # noqa: BLE001
        LATEST.mkdir(parents=True, exist_ok=True)
        (LATEST / "summary.txt").write_text(f"후보 발굴 실패 — {type(e).__name__}: {str(e)[:300]}\n", encoding="utf-8")
        log("실패:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
