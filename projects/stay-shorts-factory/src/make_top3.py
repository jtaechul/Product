#!/usr/bin/env python3
"""⭐ 메인 포맷 「데이터 호캉스 TOP3」 (2026-10-11 확정) — 테마 하나, 숙소 3곳, 25초 안팎.

request.json 예
    {"nonce": "...", "mode": "top3", "theme": "실내 온수풀·온천", "region": "강원", "month": "2026-11",
     "stays": ["소노펠리체 비발디파크", "롯데리조트 속초", "쏠비치 삼척"],   ← 생략하면 data/discover/latest 순위표 상위 3곳
     "fake": true,                                                            ← Veo 대신 가짜 클립(0원) — 포맷 검토용
     "max_veo_cuts": 6}

왜 이 포맷인가 (두 참고 영상 + 운영자 의견 + 우리 데이터를 종합한 결론)
    - 검증된 장치: 1초 안의 질문·감탄 훅 / 숫자 하나 / 혜택은 조건문 / 2초 컷 / 단점 고백 / 저장·링크 행동 지시 / 결론(1위)은 맨 끝
    - 우리만의 무기: "최근 30일 후기 ○○건"(네이버 블로그 집계) — 매주 자동 갱신되는 검증 가능한 숫자. 경쟁 채널엔 없다
    - 쇼핑 전환: 한 영상에 제휴 링크 3개. 숙소당 사진 2장이면 되어 쿠팡 사진 부족 문제도 풀린다
    - 사람·손은 AI 로 넣지 않는다. 질감은 실촬영 스톡 B롤(물결·김)로, 시점은 카메라 움직임으로

구조 (초)
    훅 2.5  →  3위 5 (컷 2 + 컷 2 + B롤 1)  →  2위 5  →  1위 6 (컷·컷 + 단점 한 줄)  →  CTA 3.5   ≈ 22~26초
    자막: 한 줄, 화면 위 1/3, 3~10자. 훅·CTA 는 손글씨체(나눔펜, OFL), 사실 자막은 고딕. 순위·숙소명 뱃지는 왼쪽 아래,
    데이터 뱃지("최근 30일 후기 931건 · 네이버 블로그 기준")는 오른쪽 위. 고지문은 아래 작게 항상.
    나레이션은 구간별로 따로 만들어(TTS 5번) 자막과 정확히 맞춘다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.parse
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import crawl_photos as crawl  # noqa: E402
import discover as dc  # noqa: E402
import make_folder  # noqa: E402
import make_stay as ms  # noqa: E402
import photos  # noqa: E402
import stock  # noqa: E402
import veo  # noqa: E402

ROOT = ms.ROOT
BUILD = ms.BUILD
FONT_HAND = ROOT / "assets" / "fonts" / "NanumPenScript-Regular.ttf"
W, H, FPS = ms.W, ms.H, ms.FPS
CUT = 2.0                                   # 컷 길이(초) — Veo 4초 클립을 앞 2초·뒤 2초로 나눠 쓴다 (템포 2초, 추가 비용 0)
PLAN = {"hook": 4.0, "rank": 11.0, "top": 14.0, "cta": 4.5}   # 구간 계획 길이 — 숙소당 장면 3개(각 2초 앞·뒤 반) + B롤 1초. 나레이션이 더 길면 그만큼 늘어난다
TEMPO = 1.28                                # TTS 배속 — 운영자 2026-10-11 "나레이션은 항상 1.28배속이 정석, 느리게 하지 마라(처진다)". 바꾸지 않는다
SHOTS_PER_HOTEL = 3                         # 운영자 2026-10-11 "설명이 너무 짧다" → 장면 3개(물놀이·객실·특별)와 2~3문장 나레이션
BROLL = ["swimming pool water surface ripples", "calm blue pool water close up", "gentle ocean waves water surface"]
BANNED = ms.BANNED + ["최장", "최대", "국내 유일"]


def log(*a):
    print("[top3]", *a, flush=True)


# ── 1) 숙소 3곳 고르기 ────────────────────────────────────────────────
def pick_candidates(req: dict) -> list[dict]:
    """순위표(data/discover/latest/candidates.json)에서 쿠팡 통과 숙소를 순서대로. stays 가 있으면 그 이름을 먼저."""
    f = ROOT / "data" / "discover" / "latest" / "candidates.json"
    rows = []
    if f.exists():
        rep = json.loads(f.read_text(encoding="utf-8"))
        rows = [c for c in rep.get("candidates") or [] if (c.get("coupang") or {}).get("ok")]
    want = [str(s).strip() for s in (req.get("stays") or []) if str(s).strip()]
    out = []
    for name in want:
        hit = next((c for c in rows if dc.same(name, c["name"])), None)
        out.append(hit or {"name": name, "demand": {}, "coupang": {}, "ai": {}, "facility_checks": []})
    for c in rows:
        if len(out) >= 6:
            break
        if not any(dc.same(c["name"], o["name"]) for o in out):
            out.append(c)
    if len(out) < 3:
        raise RuntimeError("후보가 3곳 미만입니다 — 먼저 stay-shorts-discover 를 돌리거나 request.json 에 stays 3곳을 적어 주세요")
    return out


SRC_KO = {"official": "공식 홈페이지", "coupang": "쿠팡", "operator": "운영자"}


def official_photos(name: str, city: str, out: Path, models: dict, req: dict) -> tuple[list[dict], dict, dict]:
    """공식 홈페이지 사진·글 수집 (2026-10-11 운영자 결정 · src/crawl_photos.py — 크롬 렌더 · robots 준수 · 차단이면 포기).
    실패해도 제작은 쿠팡 사진으로 이어간다. request.json "crawl": false 면 생략, "official_urls": {이름: 주소} 로 주소를 줄 수 있다.
    돌려주는 것: (사진 목록, 요약 정보, 페이지별 글)."""
    if not req.get("crawl", True):
        return [], {"skipped": "request.json crawl=false"}, {}
    try:
        cr = crawl.collect(name, city, out, official_url=(req.get("official_urls") or {}).get(name),
                           max_images=int(req.get("crawl_max") or crawl.MAX_IMAGES),      # 단일 숙소 포맷은 장면 5개가 필요해 더 모은다
                           gemini_json=lambda m, s, c: ms._try_models("text", models["text"], lambda mm: ms.gemini_json(mm, s, c)), model="auto")
    except Exception as e:  # noqa: BLE001
        log(f"{name}: 공식 홈페이지 수집 오류 — 쿠팡 사진만 사용 ({str(e)[:80]})")
        return [], {"reason": f"오류 {str(e)[:120]}"}, {}
    info = {k: cr.get(k) for k in ("url", "resolved_by", "reason", "pages", "tried")} | {"photos": len(cr["photos"])}
    log(f"{name}: 공식 홈페이지 사진 {len(cr['photos'])}장" + (f" — {cr['reason']}" if cr.get("reason") else f" ({cr.get('url')})"))
    try:   # 검수용 한 장 (build/ 에만 — 텔레그램으로만 보내고 저장소·Release 엔 올리지 않는다)
        crawl.contact_sheet(cr["photos"], out / "sheet.jpg")
    except Exception as e:  # noqa: BLE001
        log(f"{name}: 수집 사진 시트 실패 ({str(e)[:60]})")
    return cr["photos"], info, cr.get("text") or {}


FACTS_SYSTEM = """아래는 한 숙소의 공식 홈페이지에서 가져온 글(페이지별)이다. 쇼츠 나레이션에 쓸 '매력 포인트' 사실을 뽑는다.
규칙: 글에 있는 것만. 수온·길이·층·규모·운영시간·전망·구성(실내/야외, 온천수 여부, 객실 타입·뷰, 조식·사우나·키즈 시설)처럼 구체적이고 확인 가능한 것 우선.
가격·할인·프로모션·기간 한정·이벤트·예약 안내·전화번호는 제외. 과장 형용사("최고", "완벽") 제외. 다른 지점(같은 그룹의 다른 리조트) 이야기는 제외.
각 항목은 한국어 10~28자, 3~6개. JSON 만: {"facts":["..."], "signature":"이 숙소를 사실로 한 줄 요약(20자 내)"}"""


def official_facts(models: dict, name: str, text: dict) -> dict:
    """공식 홈페이지 글 → 매력 포인트 사실 3~6개 (운영자 2026-10-11 "숙소가 더 매력적으로 보이게 설명을 더 해 달라" → 사실 재료를 늘린다)."""
    if not text:
        return {"facts": [], "signature": ""}
    pri = sorted(text.items(), key=lambda kv: 0 if re.search(r"facilit|room|spa|sauna|pool|water|highlight|resort|hotel|stay", kv[0], re.I) else 1)
    body, total = [], 0
    for page, t in pri:
        t = (t or "").strip()
        if not t:
            continue
        chunk = f"[페이지 {urllib.parse.urlsplit(page).path or '/'}]\n{t[:2500]}\n"
        if total + len(chunk) > 9000:
            break
        body.append(chunk)
        total += len(chunk)
    try:
        js = ms._try_models("text", models["text"], lambda m: ms.gemini_json(m, FACTS_SYSTEM, f"숙소: {name}\n\n" + "\n".join(body)))
        facts = [str(f).strip()[:40] for f in (js.get("facts") or []) if str(f).strip() and not re.search(r"\d[\d,]*\s*(원|%)", str(f))][:6]
        out = {"facts": facts, "signature": str(js.get("signature") or "").strip()[:30]}
        log(f"{name}: 공식 홈페이지 사실 {len(facts)}개 — " + " / ".join(facts[:4]))
        return out
    except Exception as e:  # noqa: BLE001
        log(f"{name}: 사실 추출 실패 ({str(e)[:60]})")
        return {"facts": [], "signature": ""}


def record_sources(hotels: list[dict], report: dict) -> None:
    """어느 사진을 어디서 가져왔는지 장부 — report 와 data/runs/latest/photo_sources.json. 호텔이 삭제를 요청하면 여기서 찾는다."""
    rows = [{"hotel": h["name"], "official_site": (h.get("crawl") or {}).get("url"), "crawl": h.get("crawl"),
             "shots": [{"n": s["n"], "slot": s.get("slot"), "source": s.get("source"), "url": s.get("src_url"), "page": s.get("src_page"),
                        "description": s.get("description")} for s in h["shots"]]} for h in hotels]
    report["photo_sources"] = rows
    ms.PREVIEW.mkdir(parents=True, exist_ok=True)
    (ms.PREVIEW / "photo_sources.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def hotel_assets(c: dict, models: dict, idx: int, req: dict | None = None, quota: dict | None = None) -> dict | None:
    """쿠팡 검색 → 규칙·동일성으로 '이 숙소 객실'만 → 공식 홈페이지 사진 수집 → 사진 분류 → 장면 선택(quota: 분류별 장 수, 기본 물놀이1·객실1·특별1)
    → 9:16 크롭 + Veo 지시문. 사진 출처 우선순위: 공식 홈페이지(2026-10-11 운영자 결정) → 쿠팡."""
    name = c["name"]
    req = req or {}
    quota = quota or {"water": 1, "room": 1, "special": 1}
    want_total = sum(quota.values())
    v = dc.coupang_verify(name)
    rooms = v.get("rooms") or []
    if len(rooms) >= dc.MIN_ROOMS:
        try:
            idn = ms._try_models("text", models["text"], lambda m: dc.identity(m, name, c.get("city", ""), rooms))
            if idn["confidence"] != "low":
                rooms = idn["rooms"]
        except Exception as e:  # noqa: BLE001
            log(f"{name}: 동일성 판정 실패 — 규칙 통과분 사용 ({str(e)[:60]})")
    if len(rooms) < 2:
        log(f"{name}: 쿠팡 객실 {len(rooms)}개 — 제외")
        return None
    build = BUILD / f"h{idx}"
    build.mkdir(parents=True, exist_ok=True)
    official, crawl_info, site_text = official_photos(name, c.get("city", ""), build / "official", models, req)
    cands = photos.gather(rooms, ROOT / "requests" / "produce" / "photos_none", build, official=official)
    if not cands:
        return None
    facts = [k["facility"] for k in (c.get("facility_checks") or []) if k.get("verified")][:3]
    ctx = photos.context_for(name, c.get("city", ""), facts)
    cl = ms._try_models("vision", models["text"], lambda m: photos.classify(m, cands, ctx))
    theme = str(req.get("theme") or "")
    usable = sorted([p for p in cl if p["category"] in photos.CATS and p["quality"] >= 4 and not p.get("people")],
                    key=lambda p: (-theme_fit(p["description"], theme), -p["quality"]))   # 테마에 맞는 장면(실내·온수…)을 먼저
    # 장면 선택: 분류별 quota 만큼 (물놀이 → 객실 → 특별 순, 없으면 남은 것으로 채움). 2개 미만이면 제외
    chosen = []
    for cat in ("water", "room", "special"):
        for p in usable:
            if sum(1 for q in chosen if q["category"] == cat) >= quota.get(cat, 0):
                break
            if p["category"] == cat and p not in chosen:
                chosen.append(p)
    for p in usable:
        if len(chosen) >= want_total:
            break
        if p not in chosen:
            chosen.append(p)
    chosen = chosen[:want_total]
    if len(chosen) < 2:
        log(f"{name}: 쓸 수 있는 사진 {len(chosen)}장 — 제외")
        return None
    fd = official_facts(models, name, site_text)
    shots = []
    for k, p in enumerate(chosen):
        n = idx * 10 + k + 1
        photos.crop_9x16(p["path"], BUILD / f"shot_{n}.png", p["focus_x"], p["focus_y"])
        shots.append({**p, "n": n, "slot": p["category"], "prompt": photos.prompt_for(p)})
    prices = [float(it.get("productPrice") or 0) for it in rooms if float(it.get("productPrice") or 0) > 0]
    mism = [p for p in cl if p.get("mismatch")]
    if mism:
        log(f"{name}: 다른 지점 의심으로 제외 {len(mism)}장 — " + " / ".join(f"[{p['source']}] {p['mismatch'][:40]}" for p in mism[:4]))
    return {"name": name, "shots": shots, "room_names": [str(it.get("productName", ""))[:40] for it in rooms[:5]],
            "theme_hits": dc.theme_hits(rooms, dc.DEFAULT_KEYWORDS), "verified_facilities": facts,
            "blog_30d": (c.get("demand") or {}).get("blog_30d"), "blog_total": (c.get("demand") or {}).get("blog_total"),
            "min_price": min(prices) if prices else None, "affiliate_url": str(rooms[0].get("productUrl", "")),
            "hook": (c.get("ai") or {}).get("hook", ""), "classified": cl, "crawl": crawl_info,
            "official_facts": fd["facts"], "signature": fd["signature"], "city": c.get("city", ""), "official_site": crawl_info.get("url"),
            "rooms": [{"name": str(it.get("productName", ""))[:60], "price": float(it.get("productPrice") or 0) or None,
                       "image": it.get("productImage") or None, "url": str(it.get("productUrl", "")) or None} for it in rooms[:8]],
            "photo_counts": {k: sum(p["source"] == k for p in cands) for k in SRC_KO} | {"mismatch": len(mism)}}


THEME_RX = {"실내": r"실내|인도어|indoor|돔", "온수": r"온수|온천|스파|사우나|따뜻|온탕|노천", "온천": r"온천|온탕|노천|스파",
            "워터파크": r"워터파크|슬라이드|유수풀", "오션": r"바다|오션|해변", "자쿠지": r"자쿠지|욕조|노천|프라이빗", "키즈": r"키즈|아이|어린이"}


def theme_fit(desc: str, theme: str) -> int:
    """장면 설명이 이번 테마 낱말과 맞는 정도 (p3 실측: 테마가 '실내 온수풀'인데 야외 풀 사진이 뽑혔다 → 품질보다 먼저 본다)."""
    return sum(1 for key, rx in THEME_RX.items() if key in theme and re.search(rx, desc or ""))


HONEST_SYSTEM = """아래는 한 숙소에 대한 네이버 블로그 글 제목·요약 목록이다. 후기에서 반복되는 '아쉬운 점'이 있으면 한 줄(20자 내, 존댓말 없이 명사형)로 적는다.
없거나 불확실하면 빈 문자열. 지어내지 않는다. JSON 만: {"honest":"..."}"""


def honest_line(model: str, name: str) -> str:
    items = []
    for q in (f'"{name}" 아쉬운 점', f'"{name}" 단점', f'"{name}" 아쉬웠'):
        js = dc._naver_search("blog", q, 10)
        items += (js or {}).get("items") or []
        if len(items) >= 8:
            break
    if len(items) < 3:
        return ""
    text = "\n".join(re.sub(r"<[^>]+>", "", f"{it.get('title', '')} — {it.get('description', '')}")[:160] for it in items)
    try:
        return str(ms.gemini_json(model, HONEST_SYSTEM, f"숙소: {name}\n\n{text}").get("honest", "")).strip()[:30]
    except Exception:  # noqa: BLE001
        return ""


# ── 2) 대본 ───────────────────────────────────────────────────────────
SCRIPT_SYSTEM = """너는 "데이터로 고른 호캉스" 쇼츠의 큐레이터다. 1인칭, 짧은 구어체(반말 아님, "~해요"체), 광고 말투 금지. 유행어는 영상 전체에 최대 1개.
입력: 테마·지역·시기, 숙소 3곳(3위→1위 순)의 확인된 사실(쿠팡 객실 이름, 블로그로 확인된 시설, 공식 홈페이지 사실, 최근 30일 블로그 글 수, 후기 아쉬움)과 화면 장면 설명(A·B·C).
절대 규칙
- 입력에 없는 시설·서비스·가격·할인을 말하지 않는다. 가격 숫자 금지. "최고·유일·최저가·1위(순위 외)·완벽·보장·최장·최대" 금지.
- 숙소 나레이션은 **2~3문장**으로, 숙소가 매력적으로 보이게 (운영자 2026-10-11 "설명이 너무 짧다"):
  ① 첫 문장은 화면 A 장면을 감각적으로 — 수온·전망·창·동선·분위기 같은 **구체**(입력의 공식 홈페이지 사실·확인된 시설·장면 설명에 있는 것만)
  ② 둘째는 혜택·조건문(이용권 포함 객실, 조식, 사우나 포함, 체크아웃 전까지 이용 등 입력에 있는 것) 또는 둘째 장면의 매력
  ③ 셋째는 누구에게·언제 좋은지(아이와, 커플, 비 오는 날, 추운 날, 늦은 밤). 과장 형용사 대신 구체 명사. 세 숙소의 문장 구조가 똑같지 않게.
  예: "통유리 너머로 겨울 바다를 보면서 들어가는 실내 온수풀이에요. 투숙객은 사계절 이용이고, 사우나까지 이어져요. 추운 날 아이와 가기 딱 좋아요."
- 블로그 글 수는 화면 뱃지가 따로 보여 준다. **자막(caption)에는 숫자·'후기 N건'을 쓰지 않는다.** 나레이션에서는 1위 구간에서만 한 번 말해도 된다.
- 자막은 시설·혜택·느낌 키워드 3~10자 한 줄 (예: "사계절 온수 인피니티풀", "객실 전부 오션뷰", "조식 포함 객실"). 느낌표·이모지 금지. 세 숙소의 자막이 서로 다른 내용이어야 한다.
- captions 는 **장면 수만큼**(입력에 장면 A·B·C 가 있으면 3개, A·B 면 2개) — 각 장면 위에 하나씩 순서대로.
- 각 숙소에는 '화면 장면 설명'이 있다. 자막은 **시설·혜택 키워드가 우선**이고, 장면과 **모순될 때만** 바꾼다
  (식당 사진 위에 "수영장" 금지. 외관·항공 사진 위에 "실내 온수풀 보유"는 괜찮다). 장면을 묘사만 하는 자막("바다 앞 리조트 단지", "조명 켜진 야외 전경")은 금지 — 팔리는 말이 아니다.
- 시설은 '확인된 시설'과 객실 이름에 있는 것만. 혜택(benefit)은 테마와 관련된 것(워터파크·온수풀 이용권 포함, 조식 포함, 온천 객실)만 조건문 한 줄로. 관련 없는 사소한 것(취사 가능 등)이면 빈 문자열.
- 나레이션 길이(공백 제외): hook 24자 이내 · 3위/2위는 narration+benefit 합쳐 **55~85자** · 1위는 **75~115자** · cta 36자 이내. benefit 은 narration 에 녹였으면 빈 문자열.
- 말투(운영자 2026-10-11): "골랐어요·뽑았어요" 대신 **"추천드려요·추천해요"** 를 쓴다 (영상 어딘가에 한 번).
- **훅(첫 1초) 규칙 — 시청자 관점(2026-10-11 재설계)**: 훅은 **시청자의 상황이나 몸의 감각**으로 멈추게 한다. "데이터·후기·분석·추천·1위" 같은 말은 훅에 쓰지 않는다
  (그건 끝에서 신뢰를 주는 말이지 멈추게 하는 말이 아니다). 계절·테마 맥락을 반드시 담는다. 네 가지 중 테마와 1위 장면에 맞는 하나를 고른다:
  ① 상황 공감 — 자막 "11월에도 수영 되는 곳" / 나레이션 "밖은 패딩, 안은 수영복. 11월에 되는 온수풀이에요."
  ② 감각 대비 — 자막 "밖은 영하, 물은 온천수" / 나레이션 "찬바람 맞다가 따뜻한 물에 들어가는 그 순간, 강원에 있어요."
  ③ 문제 해결(가족) — 자막 "추운 날 애들 풀어놓을 곳" / 나레이션 "추운데 애들 어디 데려가지? 실내 온수풀 세 곳이면 돼요."
  ④ 반전·궁금증 — 자막 "온수풀 1위, 바다 아님" / 나레이션 "강원 온수풀 1위가 바다가 아니라 산속이에요." (입력 사실로 확인될 때만)
  훅 나레이션은 24자 이내, 숙소 이름 없음. 자막은 3~10자.
- 이름 공개 순서: 훅에는 숙소 이름이 없다. 3위·2위 나레이션은 이름을 먼저 말한다. **1위 나레이션은 숙소 이름을 문장 맨 끝에** 둔다
  (예: "최근 한 달 후기 칠백 건, 1위는 소노펠리체 비발디파크예요") — 끝까지 보게 만드는 장치.
- cta: 저장 유도 + 입력의 '프로필 폴더 이름' 을 말하고, 폴더에 있는 것(이용권 포함 객실·가격대·링크)으로 궁금하게 한다. 가격 숫자는 여기서도 금지.
출력 JSON 만:
{"hook":{"caption":"...","narration":"...","pattern":"상황|감각|가족|반전"},   ← 위 훅 규칙의 네 가지 중 하나. 데이터·후기·추천 금지
 "ranks":[{"rank":3,"captions":["장면 A 자막","장면 B 자막","장면 C 자막(장면이 3개일 때)"],"narration":"2~3문장","benefit":"조건문 한 줄 또는 빈 문자열"},
          {"rank":2,"captions":["...","...","..."],"narration":"...","benefit":"..."},
          {"rank":1,"captions":["...","...","..."],"narration":"...","benefit":"...","honest":"입력의 아쉬움이 있으면 그대로, 없으면 빈 문자열"}],
 "cta":{"caption":"...","narration":"..."},             ← 예: 자막 "저장해두고 비교하세요" / 나레이션 "이용권 포함 객실과 가격대는 프로필 폴더 '11월 실내 온수풀' 에 있어요"
 "title":"유튜브 제목 12~25자","caption":"인스타 캡션 2문장(고지문·링크는 시스템이 붙임)","hashtags":["#..","#..","#..","#..","#.."]}"""
NARR_MAX = {"hook": 24, "r3": 85, "r2": 85, "r1": 115, "cta": 36}   # p6 실측: 95/135자는 13.7/17.1초 → 영상 54초. 85/115자 + 배속 1.15 ≈ 11/15초
NARR_MIN = {"r3": 50, "r2": 50, "r1": 70}                     # 너무 짧으면(운영자 지적) 다시 쓰게 한다
WORDING_BAN = ("골랐", "골라", "뽑았", "뽑아")                    # 운영자 2026-10-11: '골랐어요' 대신 '추천'


def folder_name(req: dict) -> str:
    """프로필 링크 페이지의 테마 폴더 이름 — 영상·캡션·CTA 가 같은 이름을 가리킨다. request.json "folder" 로 바꿀 수 있다."""
    if req.get("folder"):
        return str(req["folder"]).strip()
    month = str(req.get("month") or "")
    m = re.search(r"-(\d{1,2})$", month)
    theme = re.sub(r"[·/,]+", " ", str(req.get("theme") or "")).strip()
    return (f"{int(m.group(1))}월 " if m else "") + theme


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s·\-()]+", name) if len(t) >= 2]


def check_script(s: dict, hotels: list[dict]) -> list[str]:
    errs = []
    ranks = s.get("ranks") or []
    if [r.get("rank") for r in ranks] != [3, 2, 1]:
        errs.append("ranks 는 3,2,1 순서 3개")
    segs = [("hook", s.get("hook") or {})] + [(f"r{r.get('rank')}", r) for r in ranks] + [("cta", s.get("cta") or {})]
    shots_n = {f"r{r}": len(h.get("shots") or []) or 2 for r, h in zip((3, 2, 1), hotels)}
    joined = ""
    for key, g in segs:
        caps = g.get("captions") or ([g.get("caption")] if g.get("caption") else [])
        if key.startswith("r") and len(caps) != shots_n.get(key, 2):
            errs.append(f"{key} 자막은 장면 수({shots_n.get(key, 2)})만큼")
        for cp in caps:
            if not (2 <= len(str(cp).replace(" ", "")) <= 12):
                errs.append(f"자막 길이: '{cp}'")
            if key.startswith("r") and re.search(r"\d|후기", str(cp)):      # 순위 자막엔 숫자·후기 금지 (뱃지가 보여 준다). 훅은 허용
                errs.append(f"순위 자막에 숫자·후기 금지: '{cp}'")
        n = str(g.get("narration", "")).strip()
        total = len((n + str(g.get("benefit", ""))).replace(" ", ""))
        if not n or total > NARR_MAX.get(key, 40):
            errs.append(f"{key} 나레이션 {total}자 (한도 {NARR_MAX.get(key, 40)})")
        if total < NARR_MIN.get(key, 0):
            errs.append(f"{key} 나레이션 {total}자 — 너무 짧다 (최소 {NARR_MIN[key]}자, 2~3문장으로 숙소를 매력적으로)")
        joined += " ".join(map(str, caps)) + n + str(g.get("benefit", "")) + str(g.get("honest", ""))
        if key == "hook":
            for h in hotels:
                if any(t in (n + " ".join(map(str, caps))) for t in _name_tokens(h["name"])):
                    errs.append(f"훅에 숙소 이름 금지 ({h['name']})")
            bad = [w for w in ("데이터", "후기", "분석", "추천", "AI", "인공지능", "빅데이터") if w in (n + " ".join(map(str, caps)))]
            if bad:
                errs.append(f"훅에 {'/'.join(bad)} 금지 — 상황·감각으로 시작 (2026-10-11 훅 규칙)")
        if key == "r1" and hotels:
            top = hotels[-1]                                   # hotels 는 3위→1위 순
            pos = [n.rfind(t) for t in _name_tokens(top["name"]) if n.rfind(t) >= 0]
            if not pos:
                errs.append(f"1위 나레이션에 숙소 이름({top['name']}) 넣기")
            elif max(pos) < len(n) * 0.45:
                errs.append("1위 나레이션은 숙소 이름을 문장 끝에")
        for w in WORDING_BAN:
            if w in n:
                errs.append(f"'{w}' 대신 '추천' 표현 ({key})")
    all_narr = " ".join(str((g or {}).get("narration", "")) for _, g in segs)
    if "추천" not in all_narr:
        errs.append("나레이션 어딘가에 '추천' 한 번 (운영자 말투 규칙)")
    joined += str(s.get("title", "")) + str(s.get("caption", ""))
    if re.search(r"(만족도|인기|평점|국내|업계|지역|강원|전국)\s*1위", joined):        # 순위 표기("1위는 ○○")는 허용, 과장 주장("국내 1위")만 금지
        errs.append("'○○ 1위' 과장 표현")
    plain = re.sub(r"[123]\s*위", "", joined)
    for b in BANNED:
        if b in plain:
            errs.append(f"금지 표현 '{b}'")
    if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", joined):
        errs.append("가격·할인 숫자")
    return errs


def write_script(model: str, req: dict, hotels: list[dict]) -> dict:
    lines = [f"테마: {req.get('theme')} · 지역: {req.get('region')} · 시기: {req.get('month')}", f"프로필 폴더 이름: {folder_name(req)}", ""]
    for rank, h in zip((3, 2, 1), hotels):
        scenes = " / ".join(f"장면 {'ABC'[k]}: {s.get('description') or s.get('category')}" for k, s in enumerate(h["shots"]))
        lines += [f"[{rank}위] {h['name']}" + (f" — {h['signature']}" if h.get("signature") else ""),
                  f"  화면 {scenes}",
                  f"  쿠팡 객실 이름: {', '.join(h['room_names'])}",
                  f"  확인된 시설: {', '.join(h['verified_facilities']) or '없음'} / 객실 이름의 테마 단어: {', '.join(h['theme_hits']) or '없음'}",
                  f"  공식 홈페이지 사실: {', '.join(h.get('official_facts') or []) or '없음'}",
                  f"  최근 30일 블로그 글 수: {h['blog_30d'] if h['blog_30d'] is not None else '모름'}",
                  f"  후기 아쉬움: {h.get('honest') or '없음'}", ""]
    content = "\n".join(lines)
    errs = []
    for attempt in range(3):
        extra = ("\n\n직전 답의 문제(고쳐서 다시): " + " / ".join(errs)) if errs else ""
        s = ms.gemini_json(model, SCRIPT_SYSTEM, content + extra)
        errs = check_script(s, hotels)
        if not errs:
            return s
        log(f"대본 검사 실패({attempt + 1}):", errs)
    raise RuntimeError("대본이 규칙을 통과하지 못함: " + " / ".join(errs))


# ── 3) 화면 요소 ──────────────────────────────────────────────────────
def _fonts():
    from PIL import ImageFont
    g = ms.font_path()
    hand = str(FONT_HAND) if FONT_HAND.exists() else g
    return ImageFont, g, hand


def _fit(d, text, font_path, size, max_w, ImageFont):
    f = ImageFont.truetype(font_path, size)
    while d.textlength(text, font=f) > max_w and size > 24:
        size -= 2
        f = ImageFont.truetype(font_path, size)
    return f


def overlay(path: Path, caption: str = "", hand: bool = False, badge: str = "", data: str = "", sub: str = "", honest: str = ""):
    """투명 PNG: 위 1/3 자막 · 왼쪽 아래 순위 뱃지 · 오른쪽 위 데이터 뱃지 · 아래 고지문(항상)."""
    from PIL import Image, ImageDraw
    ImageFont, g, hand_font = _fonts()
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if caption:
        f = _fit(d, caption, hand_font if hand else g, 104 if hand else 68, W - 160, ImageFont)
        tw = d.textlength(caption, font=f)
        d.text(((W - tw) / 2, 560 if hand else 580), caption, font=f, fill=(255, 255, 255, 255),
               stroke_width=7 if hand else 6, stroke_fill=(0, 0, 0, 230))
    if honest:
        f = _fit(d, honest, g, 40, W - 200, ImageFont)
        tw = d.textlength(honest, font=f)
        d.rounded_rectangle([(W - tw) / 2 - 24, 700, (W + tw) / 2 + 24, 700 + f.size + 28], 18, fill=(0, 0, 0, 150))
        d.text(((W - tw) / 2, 714), honest, font=f, fill=(255, 220, 120, 255))
    if badge:
        f = _fit(d, badge, g, 46, W - 300, ImageFont)
        tw = d.textlength(badge, font=f)
        x, y = 48, 1520
        d.rounded_rectangle([x, y, x + tw + 52, y + f.size + 34], 26, fill=(0, 0, 0, 165))
        d.text((x + 26, y + 17), badge, font=f, fill=(255, 255, 255, 255))
    if data:
        f = _fit(d, data, g, 38, 620, ImageFont)
        tw = d.textlength(data, font=f)
        x2, y = W - 48, 130
        d.rounded_rectangle([x2 - tw - 44, y, x2, y + f.size + 28 + (26 if sub else 0)], 22, fill=(255, 232, 107, 235))
        d.text((x2 - tw - 22, y + 13), data, font=f, fill=(20, 20, 20, 255))
        if sub:
            f2 = ImageFont.truetype(g, 22)
            d.text((x2 - tw - 22, y + f.size + 20), sub, font=f2, fill=(60, 60, 60, 255))
    f = ImageFont.truetype(g, 22)
    y = 1790
    for ln in ms.wrap(d, ms.DISCLOSURE, f, W - 160):
        lw = d.textlength(ln, font=f)
        d.text(((W - lw) / 2, y), ln, font=f, fill=(255, 255, 255, 200), stroke_width=2, stroke_fill=(0, 0, 0, 180))
        y += 30
    im.save(path)


def counter_frames(n: int, out_dir: Path, sec: float = 1.0, label: str = "최근 30일 후기", sub: str = "네이버 블로그 기준") -> int:
    """오른쪽 위 데이터 뱃지의 숫자가 0 → n 으로 올라가는 PNG 프레임들 (훅 구간 전용)."""
    from PIL import Image, ImageDraw
    ImageFont, g, _ = _fonts()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = max(2, int(sec * FPS))
    f = ImageFont.truetype(g, 38)
    f2 = ImageFont.truetype(g, 22)
    for i in range(frames):
        t = (i / (frames - 1)) ** 0.6
        val = int(round(n * t))
        text = f"{label} {val:,}건" + ("+" if n >= 1000 and val >= 1000 else "")
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        tw = d.textlength(text, font=f)
        x2, y = W - 48, 130
        d.rounded_rectangle([x2 - tw - 44, y, x2, y + f.size + 54], 22, fill=(255, 232, 107, 235))
        d.text((x2 - tw - 22, y + 13), text, font=f, fill=(20, 20, 20, 255))
        d.text((x2 - tw - 22, y + f.size + 20), sub, font=f2, fill=(60, 60, 60, 255))
        im.save(out_dir / f"c_{i:03d}.png")
    return frames


def cta_card(path: Path, hotels: list[dict], caption: str, folder: str = ""):
    """마지막 카드: 어두운 배경 + 1~3위 이름 + 손글씨 자막 + 직접 그린 아이콘(북마크·링크 → 프로필 폴더 이름). 이모지 금지."""
    from PIL import Image, ImageDraw
    ImageFont, g, hand = _fonts()
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, 150))
    f = _fit(d, caption, hand, 112, W - 140, ImageFont)
    tw = d.textlength(caption, font=f)
    d.text(((W - tw) / 2, 430), caption, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 220))
    fy = ImageFont.truetype(g, 50)
    y = 700
    for rank, h in zip((1, 2, 3), hotels[::-1]):
        line = f"{rank}위  {h['name']}"
        fl = _fit(d, line, g, 50, W - 220, ImageFont)
        d.text((110, y), line, font=fl, fill=(255, 232, 107, 255) if rank == 1 else (255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))
        y += fl.size + 34
    # 북마크 아이콘 + "저장" / 링크 아이콘 + "프로필 링크"
    bx, by = 300, 1180
    d.polygon([(bx, by), (bx + 70, by), (bx + 70, by + 96), (bx + 35, by + 70), (bx, by + 96)], fill=(255, 232, 107, 255))
    d.text((bx + 96, by + 22), "저장", font=fy, fill=(255, 255, 255, 255))
    lx, ly = 600, 1180
    d.rounded_rectangle([lx, ly + 22, lx + 60, ly + 62], 20, outline=(255, 232, 107, 255), width=9)
    d.rounded_rectangle([lx + 36, ly + 36, lx + 96, ly + 76], 20, outline=(255, 232, 107, 255), width=9)
    d.text((lx + 120, ly + 22), "프로필 링크", font=fy, fill=(255, 255, 255, 255))
    if folder:                                   # 어느 폴더로 가면 되는지 — 운영자 2026-10-11 "폴더를 만들어서 들어가서 볼 수 있게"
        line = f"폴더  {folder}"
        ff = _fit(d, line, g, 44, W - 240, ImageFont)
        tw = d.textlength(line, font=ff)
        d.text(((W - tw) / 2, ly + 120), line, font=ff, fill=(255, 232, 107, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))
    im.save(path)


# ── 4) 소리·합성 ──────────────────────────────────────────────────────
def tts(models: dict, text: str, out: Path, voice: str, tempo: float) -> float:
    """구간 나레이션 한 개. 지시문 없이 본문만 보내고(읽어 버리는 버그), 앞뒤 무음을 잘라 자막과 맞춘다."""
    raw = out.with_suffix(".raw.wav")
    ms._try_models("tts", models["tts"], lambda m: ms.gemini_tts(m, text, voice, "", raw))
    trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.12,areverse,"
            "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.25,areverse")
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"{trim},atempo={tempo:.3f}", str(out)])
    with wave.open(str(out), "rb") as wf:
        sec = wf.getnframes() / wf.getframerate()
    chars = len(text.replace(" ", ""))
    if sec > 0.32 * chars + 2.0:                 # 글자 수 대비 너무 길면 지시문을 읽었거나 긴 공백 — 기록에 남긴다
        log(f"⚠️ 나레이션이 글자 수 대비 깁니다: {chars}자 {sec:.1f}초 — '{text[:20]}'")
    return sec


def segment(idx: int, pieces: list, wav: Path | None, narr: float, planned: float, overlays: list[tuple[Path, float, float]],
            counter: tuple[Path, int] | None = None) -> tuple[Path, float]:
    """조각(path 또는 (path, 시작초, 길이초))들을 이어 붙이고 자막·뱃지를 시간대별로 얹고 구간 나레이션을 합친다 → seg_N.mp4."""
    norm = []
    for k, pc in enumerate(pieces):
        c, start, dur = (pc, 0.0, CUT) if not isinstance(pc, tuple) else pc
        avail = max(0.3, ms.probe_duration(c) - start)
        d = BUILD / f"n{idx}_{k}.mp4"
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(c), "-an",
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},setsar=1",
                "-t", f"{min(dur, avail):.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(d)])
        norm.append(d)
    vlen = sum(ms.probe_duration(d) for d in norm)
    seglen = max(planned, (narr or 0) + 0.35, vlen if not narr else 0)
    factor = min(1.5, seglen / vlen) if vlen < seglen else 1.0
    stretched = vlen * factor
    pad = max(0.0, seglen - stretched)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for d in norm:
        cmd += ["-i", str(d)]
    n_in = len(norm)
    for p, _, _ in overlays:
        cmd += ["-i", str(p)]
    if counter:
        cmd += ["-framerate", str(FPS), "-i", str(counter[0] / "c_%03d.png")]
    if wav:
        cmd += ["-i", str(wav)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{seglen:.3f}", "-i", "anullsrc=r=24000:cl=mono"]
    fc = "".join(f"[{i}:v]" for i in range(n_in)) + f"concat=n={n_in}:v=1:a=0[v0];"
    fc += f"[v0]setpts={factor:.4f}*PTS,fps={FPS},tpad=stop_mode=clone:stop_duration={pad:.3f}[v1];"
    cur, k = "v1", n_in
    for j, (_, a, b) in enumerate(overlays):
        # between() 은 양끝 포함이라 경계 프레임에 자막 두 장이 겹친다(실측) → [a, b) 반개구간
        fc += f"[{cur}][{k}:v]overlay=0:0:format=auto:enable='gte(t,{a:.3f})*lt(t,{b:.3f})'[v{j + 2}];"
        cur = f"v{j + 2}"; k += 1
    if counter:
        # counter = (프레임 폴더, 시작 초): 시작 초부터 숫자가 올라가고 마지막 프레임이 끝까지 남는다 (1위 이름 공개 순간에 쓴다)
        st = float(counter[1] or 0)
        fc += f"[{k}:v]setpts=PTS-STARTPTS+{st:.3f}/TB[cnt];[{cur}][cnt]overlay=0:0:format=auto:eof_action=repeat:enable='gte(t,{st:.3f})'[vc];"
        cur = "vc"; k += 1
    fc += f"[{cur}]format=yuv420p[v];[{k}:a]apad[a]"
    out = BUILD / f"seg_{idx}.mp4"
    ms.run(cmd + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{seglen:.3f}", "-r", str(FPS),
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(out)])
    return out, seglen


# ── 4-1) 나레이션 검증: 음성을 받아 적어 대본과 비교 (2026-10-11 운영자 지적 "이상한 워딩이 들린다") ──
def transcribe(model: str, wav: Path) -> str:
    import base64
    body = {"contents": [{"role": "user", "parts": [
        {"text": "이 음성을 들리는 그대로 한국어로 받아 적어라. 설명·따옴표 없이 받아 적은 문장만 출력한다."},
        {"inline_data": {"mime_type": "audio/wav", "data": base64.b64encode(wav.read_bytes()).decode()}}]}],
        # p6 실측: 14초 음성에서 받아쓰기가 중간에 잘렸다(0.54) — 생각 토큰이 출력 한도를 먹는다 → 생각 끄고 한도 확대
        "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.0, "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    return "".join(p.get("text", "") for p in parts).strip()


def narration_qa(models: dict, items: list[tuple[str, str, Path]]) -> list[dict]:
    """(구간, 대본, wav) → 받아쓰기·유사도. 유사도 0.75 미만이거나 '읽어줘·대사' 같은 지시문 낱말이 들리면 실패."""
    import difflib
    out = []
    for key, text, wav in items:
        try:
            heard = ms._try_models("text", models["text"], lambda m: transcribe(m, wav))
        except Exception as e:  # noqa: BLE001
            heard = f"(받아쓰기 실패: {str(e)[:60]})"
        a, b = re.sub(r"[\s.,!?~]", "", text), re.sub(r"[\s.,!?~]", "", heard)
        sim = difflib.SequenceMatcher(None, a, b).ratio() if b else 0.0
        bad = [w for w in ("읽어줘", "읽어 줘", "대사를", "톤으로", "추천하듯", "나레이션 톤") if w in heard]
        out.append({"segment": key, "script": text, "heard": heard, "similarity": round(sim, 2),
                    "ok": sim >= 0.75 and not bad, "instruction_words": bad})
    return out


def preview_sheet(hotels: list[dict], script: dict, out: Path):
    """사진 6장(3위→1위, 각 A·B) + 그 위에 들어갈 자막을 한 장으로 — 영상 전에 눈으로 판단."""
    from PIL import Image, ImageDraw, ImageFont
    g = ms.font_path()
    f = ImageFont.truetype(g, 30); f2 = ImageFont.truetype(g, 24)
    w, h = 300, 533
    cols = max(len(hh["shots"]) for hh in hotels)
    im = Image.new("RGB", (w * cols + 20 * (cols + 1), (h + 170) * 3 + 20), (18, 18, 18))
    d = ImageDraw.Draw(im)
    for row, (hh, r) in enumerate(zip(hotels, script["ranks"])):
        y0 = 20 + row * (h + 170)
        d.text((20, y0), f"{r['rank']}위  {hh['name']}", font=f, fill=(255, 232, 107))
        narr = r["narration"] + (f" / {r['benefit']}" if r.get("benefit") else "")
        maxc = max(30, (w * cols + 20 * (cols - 1)) // 13)
        d.text((20, y0 + 38), ("나레이션: " + narr)[:maxc], font=f2, fill=(220, 220, 220))
        if len("나레이션: " + narr) > maxc:
            d.text((20, y0 + 66), ("나레이션: " + narr)[maxc:maxc * 2], font=f2, fill=(220, 220, 220))
        y0 += 30
        for col, (s, cap) in enumerate(zip(hh["shots"], r["captions"])):
            try:
                t = Image.open(BUILD / f"shot_{s['n']}.png").convert("RGB").resize((w, h), Image.LANCZOS)
            except Exception:  # noqa: BLE001
                continue
            x = 20 + col * (w + 20)
            im.paste(t, (x, y0 + 74))
            d.rectangle([x, y0 + 74 + h - 40, x + w, y0 + 74 + h], fill=(0, 0, 0))
            d.text((x + 8, y0 + 74 + h - 34), f"자막: {cap}", font=f2, fill=(255, 255, 255))
            d.text((x + 8, y0 + 74 + 8), f"{photos.KO.get(s['category'], '')} · {SRC_KO.get(s.get('source'), '')}", font=f2,
                   fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    im.save(out, "JPEG", quality=85)


def preview_top3(req: dict, models: dict, report: dict) -> dict:
    """영상 없이 ① 사진 ② 대사·자막 ③ 나레이션 음성(받아쓰기 검증)만 만든다. 운영자가 보고 듣고 승인하면 그때 영상."""
    theme, region, month = str(req.get("theme") or ""), str(req.get("region") or ""), str(req.get("month") or "")
    voice, tempo = str(req.get("voice") or "Erinome"), float(req.get("tempo") or TEMPO)
    BUILD.mkdir(parents=True, exist_ok=True)
    hotels = []
    for i, c in enumerate(pick_candidates(req)):
        if len(hotels) >= 3:
            break
        h = hotel_assets(c, models, i + 1, req)
        if h:
            hotels.append(h)
    if len(hotels) < 3:
        raise RuntimeError(f"사진 2장 이상 확보된 숙소가 {len(hotels)}곳 — 3곳 필요")
    hotels = hotels[:3][::-1]
    hotels[2]["honest"] = ms._try_models("text", models["text"], lambda m: honest_line(m, hotels[2]["name"]))
    report["hotels"] = [{k: h[k] for k in ("name", "city", "room_names", "verified_facilities", "theme_hits", "blog_30d", "min_price", "honest", "photo_counts", "official_facts", "signature", "hook", "affiliate_url", "official_site", "rooms") if k in h} for h in hotels]
    record_sources(hotels, report)
    script = ms._try_models("text", models["text"], lambda m: write_script(m, req, hotels))
    report["script"] = script
    try:   # 프로필 링크 페이지의 테마 폴더(link/data/folders.json) — 영상 CTA 가 가리키는 그 폴더
        make_folder.update(req, hotels, script)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]})")
    segs_text = [("hook", script["hook"]["narration"])] + [(f"r{r['rank']}", r["narration"] + (" " + r["benefit"] if r.get("benefit") else "")) for r in script["ranks"]] + [("cta", script["cta"]["narration"])]
    wavs = []
    for key, text in segs_text:
        wav = BUILD / f"narr_{key}.wav"
        sec = tts(models, text, wav, voice, tempo)
        wavs.append((key, text, wav, sec))
    report["narration_sec"] = {k: round(s, 2) for k, _, _, s in wavs}
    qa = narration_qa(models, [(k, t, w) for k, t, w, _ in wavs])
    report["narration_qa"] = qa

    prev = ms.PREVIEW
    prev.mkdir(parents=True, exist_ok=True)
    # 들어볼 수 있게 한 파일로 (구간 사이 0.6초 쉼)
    (BUILD / "narr_list.txt").write_text("".join(f"file '{w.name}'\nfile 'gap.wav'\n" for _, _, w, _ in wavs), encoding="utf-8")
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", "0.6", "-i", "anullsrc=r=24000:cl=mono", str(BUILD / "gap.wav")])
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "narr_list.txt"), "-c:a", "libmp3lame", "-b:a", "96k", str(prev / "narration_preview.mp3")])
    preview_sheet(hotels, script, prev / "preview_shots.jpg")
    md = [f"# 미리보기 — {region} · {theme} · {month}", f"프로필 폴더 이름: **{folder_name(req)}** (영상 CTA·캡션이 이 이름을 가리킨다 — 프로필 링크 페이지에 같은 이름의 폴더가 있어야 한다)", "",
          "## 대사·자막", "", f"- 훅 자막: **{script['hook']['caption']}** / 나레이션: {script['hook']['narration']}"]
    for r in script["ranks"]:
        md.append(f"- {r['rank']}위 자막: " + " → ".join(f"**{c}**" for c in r["captions"]) + f" / 나레이션: {r['narration']}" + (f" / 혜택: {r['benefit']}" if r.get("benefit") else "") + (f" / 아쉬움: {r['honest']}" if r.get("honest") else ""))
    md += [f"- CTA 자막: **{script['cta']['caption']}** / 나레이션: {script['cta']['narration']}", "", "## 나레이션 받아쓰기 검증 (Gemini 가 음성을 듣고 적은 것)", "",
           "| 구간 | 대본 | 들린 것 | 일치 | 판정 |", "|---|---|---|---|---|"]
    for q in qa:
        md.append(f"| {q['segment']} | {q['script']} | {q['heard']} | {q['similarity']} | {'통과' if q['ok'] else '실패 ' + ','.join(q['instruction_words'])} |")
    md += ["", "## 숙소·사진", ""]
    for h, r in zip(hotels, script["ranks"]):
        cr = h.get("crawl") or {}
        pc = h.get("photo_counts") or {}
        src = " · ".join(f"장면 {'ABC'[k]}: {s.get('description')} [{SRC_KO.get(s.get('source'), '?')}]" for k, s in enumerate(h["shots"]))
        got = (f"공식 홈페이지 {pc.get('official', 0)}장 · 쿠팡 {pc.get('coupang', 0)}장" + (f" · 다른 지점 의심 제외 {pc['mismatch']}장" if pc.get("mismatch") else "")
               + (f" · 공식 홈페이지 수집 실패: {cr['reason']}" if cr.get("reason") else ""))
        md.append(f"- {r['rank']}위 {h['name']} — 확인된 시설: {', '.join(h['verified_facilities']) or '없음'} · 후기 30일 {h['blog_30d']} · 사진 후보 {got} · {src}")
        md.append(f"  - 공식 홈페이지 사실(나레이션 재료): {', '.join(h.get('official_facts') or []) or '없음'}" + (f" · 한 줄: {h['signature']}" if h.get("signature") else ""))
    md += ["", "사진 출처 장부: `data/runs/latest/photo_sources.json` (어느 페이지의 어느 사진인지 — 호텔 요청 시 삭제 근거)"]
    (prev / "preview.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    names = [h["name"] for h in hotels[::-1]]
    meta = {"mode": "top3", "stage": "preview", "stay": " / ".join(names), "title": script.get("title"),
            "narration_qa_ok": all(q["ok"] for q in qa), "files": ["preview.md", "preview_shots.jpg", "narration_preview.mp3"]}
    (BUILD / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


# ── 5) 전체 ───────────────────────────────────────────────────────────
def produce_top3(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    theme, region, month = str(req.get("theme") or ""), str(req.get("region") or ""), str(req.get("month") or "")
    voice, tempo = str(req.get("voice") or "Erinome"), float(req.get("tempo") or TEMPO)
    BUILD.mkdir(parents=True, exist_ok=True)

    # 1) 숙소 3곳 + 사진 2장씩 (싼 단계)
    hotels = []
    for i, c in enumerate(pick_candidates(req)):
        if len(hotels) >= 3:
            break
        h = hotel_assets(c, models, i + 1, req)
        if h:
            hotels.append(h)
    if len(hotels) < 3:
        raise RuntimeError(f"사진 2장 이상 확보된 숙소가 {len(hotels)}곳 — 3곳 필요")
    hotels = hotels[:3][::-1]                       # 입력 순서가 1위→3위 이므로 뒤집어 3위→1위
    hotels[2]["honest"] = ms._try_models("text", models["text"], lambda m: honest_line(m, hotels[2]["name"]))
    report["hotels"] = [{k: h[k] for k in ("name", "city", "room_names", "verified_facilities", "theme_hits", "blog_30d", "min_price", "honest", "photo_counts", "official_facts", "signature", "hook", "affiliate_url", "official_site", "rooms")
                         if k in h} for h in hotels]
    record_sources(hotels, report)
    log("순서(3→1위):", " · ".join(h["name"] for h in hotels))

    # 2) 대본 + 구간별 나레이션 (싼 단계 — 여기서 실패하면 영상값을 안 쓴다)
    script = ms._try_models("text", models["text"], lambda m: write_script(m, req, hotels))
    report["script"] = script
    try:   # 프로필 링크 페이지의 테마 폴더(link/data/folders.json) — 영상 CTA 가 가리키는 그 폴더
        make_folder.update(req, hotels, script)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]})")
    segs_text = [("hook", script["hook"]["narration"])] + [(f"r{r['rank']}", r["narration"] + (" " + r["benefit"] if r.get("benefit") else "")) for r in script["ranks"]] + [("cta", script["cta"]["narration"])]
    narr = {}
    for key, text in segs_text:
        narr[key] = tts(models, text, BUILD / f"narr_{key}.wav", voice, tempo)
    report["narration_sec"] = {k: round(v, 2) for k, v in narr.items()}

    # 3) Veo (돈) — 숙소당 2컷, 1위 컷을 훅에도 쓴다
    all_shots = [s for h in hotels for s in h["shots"]]
    max_cuts = int(req.get("max_veo_cuts") or 6)
    est = veo.estimate_krw(min(len(all_shots), max_cuts), 4)
    log(f"Veo {len(all_shots)}컷 중 {min(len(all_shots), max_cuts)}컷 · 예상 약 {est:,.0f}원 · 이번 달 누적 {veo.month_total():,.0f}원")
    clips, results = {}, []
    for k, s in enumerate(all_shots):
        n, out = s["n"], BUILD / f"veo_{s['n']}.mp4"
        row = {"n": n, "ok": False, "krw": 0.0}
        if k >= max_cuts:
            row["error"] = "max_veo_cuts 초과 — 가짜(확대) 클립으로 대체"
            veo._fake_clip(BUILD / f"shot_{n}.png", 4, out); clips[n] = out; row["ok"] = True; row["fake"] = True
            results.append(row); continue
        before = veo.spent_this_run()
        seed = veo.seed_for(theme, n)
        for attempt in range(2):
            try:
                veo.make_clip(s["prompt"], BUILD / f"shot_{n}.png", 4, out, seed + attempt)
                row["ok"] = True; clips[n] = out; break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:120]}"
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"; break
            except veo.VeoError as e:
                row["error"] = str(e)[:160]; break
        if not row["ok"]:                      # 실패한 컷은 가짜(확대) 클립으로 메워 영상은 완성한다 (표에 표시)
            veo._fake_clip(BUILD / f"shot_{n}.png", 4, out); clips[n] = out; row["fake"] = True
        row["krw"] = round(veo.spent_this_run() - before)
        results.append(row)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": results, "spent_krw": round(veo.spent_this_run()),
                     "month_total_krw": round(veo.month_total())}

    # 4) B롤 (0원) — 숙소 사이에 1초씩. 설명 낱말 + Gemini 비전으로 '물 장면'만 통과 (삼겹살 사고 재발 방지)
    def water_frame(frame: Path) -> bool:
        try:
            cl = ms._try_models("vision", models["text"], lambda m: photos.classify(m, [{"k": 0, "source": "stock", "name": "broll", "path": str(frame)}]))
            return bool(cl) and cl[0]["category"] == "water" and not cl[0].get("people")
        except Exception as e:  # noqa: BLE001
            log(f"B롤 비전 검사 실패 → 탈락 처리: {str(e)[:60]}")
            return False
    brolls = []
    for i, q in enumerate(BROLL[:2]):
        p = stock.cutaway(q, 1.0, BUILD / f"broll_{i}.mp4", verify=water_frame)
        brolls.append(p)
    report["broll"] = [str(p.name) if p else None for p in brolls]

    # 5) 구간 합성
    segs = []
    top = hotels[2]
    data_of = lambda h: (f"최근 30일 후기 {h['blog_30d']:,}건{'+' if (h['blog_30d'] or 0) >= 1000 else ''}" if h.get("blog_30d") else "")
    # 훅: 1위의 물놀이 컷 (이름 숨김) + 손글씨 자막. 2026-10-11 훅 재설계: 훅은 상황·감각 한 문장만 — 후기 카운터는 1위 이름 공개 순간으로 옮겼다
    ov = BUILD / "ov_hook.png"; overlay(ov, script["hook"]["caption"], hand=True)
    cdir = None
    if top.get("blog_30d"):
        cdir = BUILD / "counter"; counter_frames(int(top["blog_30d"]), cdir, 1.2)
    A, Bc = clips[top["shots"][0]["n"]], clips[top["shots"][1]["n"]]
    seg, L = segment(0, [(A, 0, CUT), (Bc, 0, CUT)], BUILD / "narr_hook.wav", narr["hook"], PLAN["hook"], [(ov, 0, 99)])
    segs.append(seg)
    # 3위 → 2위 → 1위: [A 앞 2초, B롤 1초, B 앞 2초, C 앞 2초, A 뒤 2초] (1위는 B·C 뒤 2초까지) — 2초 템포, 장면당 Veo 클립 1개(앞·뒤 반)
    for i, (h, r) in enumerate(zip(hotels, script["ranks"])):
        rank = r["rank"]
        planned = PLAN["top"] if rank == 1 else PLAN["rank"]
        sh = h["shots"]
        A = clips[sh[0]["n"]]
        # 장면 3개의 앞 2초 → 다시 앞에서부터 뒤 2초: 3위/2위 11초(A·B롤·B·C·A'·B'), 1위 14초(+C'·B롤). 나레이션 11~15초와 맞춰 느리게 늘리는 일을 줄인다
        cl = [(A, 0, CUT)]
        if brolls[i % 2]:
            cl.append((brolls[i % 2], 0, 1.0))
        cl += [(clips[s["n"]], 0, CUT) for s in sh[1:]] + [(A, CUT, CUT)] + [(clips[s["n"]], CUT, CUT) for s in sh[1:2]]
        if rank == 1:
            cl += [(clips[s["n"]], CUT, CUT) for s in sh[2:]]
            if brolls[(i + 1) % 2]:
                cl.append((brolls[(i + 1) % 2], 0, 1.0))
        key = f"r{rank}"
        seglen_guess = max(planned, narr[key] + 0.35)
        caps = list(r["captions"])[:len(sh)] or [""]
        badge = f"{rank}위  {h['name']}"
        ovs = []
        reveal_at = seglen_guess * (len(caps) - 1) / len(caps)          # 마지막 자막 = 1위 이름 공개 순간
        for k, cap in enumerate(caps):
            # 1위는 첫 자막 동안 이름을 숨기고("1위") 그 뒤에 공개 — 나레이션도 이름을 문장 끝에 둔다 (끝까지 보게 하는 장치, 운영자 2026-10-11 논의)
            o = BUILD / f"ov_{key}_{k}.png"
            last = k == len(caps) - 1
            use_counter = rank == 1 and last and cdir is not None       # 그 순간엔 정적 뱃지 대신 숫자가 올라가는 카운터(증거)
            overlay(o, cap, badge=(f"{rank}위" if rank == 1 and k == 0 else badge), data=("" if use_counter else data_of(h)),
                    sub=("" if use_counter or not data_of(h) else "네이버 블로그 기준"),
                    honest=(f"후기 속 아쉬움: {r.get('honest')}" if rank == 1 and last and r.get("honest") else ""))
            a, b = seglen_guess * k / len(caps), (seglen_guess * (k + 1) / len(caps) if k < len(caps) - 1 else 99)
            ovs.append((o, a, b))
        seg, L = segment(rank, cl, BUILD / f"narr_{key}.wav", narr[key], planned, ovs, (cdir, reveal_at) if rank == 1 and cdir else None)
        segs.append(seg)
    # CTA: 1위 컷 위에 어두운 카드
    A, Bc = clips[top["shots"][0]["n"]], clips[top["shots"][-1]["n"]]
    folder = folder_name(req)
    card = BUILD / "ov_cta.png"; cta_card(card, hotels, script["cta"]["caption"], folder)
    seg, L = segment(9, [(Bc, CUT, CUT), (A, CUT, CUT)], BUILD / "narr_cta.wav", narr["cta"], PLAN["cta"], [(card, 0, 99)])
    segs.append(seg)

    (BUILD / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    video = BUILD / "video.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "concat.txt"),
            "-c", "copy", "-movflags", "+faststart", str(video)])
    total = ms.probe_duration(video)

    # 6) 승인 자료 + meta
    for h in hotels:
        for s in h["shots"]:
            s["slot"] = s["category"]
    ms.compare_images([s for h in hotels for s in h["shots"]], clips, BUILD, ms.PREVIEW)
    names = [h["name"] for h in hotels[::-1]]
    caption = (ms.DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip() + "\n\n"
               + "\n".join(f"{i + 1}위 {n}" for i, n in enumerate(names)) + f"\n이용권 포함 객실·가격대·링크는 프로필 폴더 '{folder}' 에 있어요\n\n" + " ".join(script.get("hashtags") or []))
    meta = {"mode": "top3", "stay": " / ".join(names), "title": script.get("title"), "caption": caption, "folder": folder,
            "affiliate_urls": {h["name"]: h["affiliate_url"] for h in hotels},
            "lines": [script["hook"]["narration"]] + [r["narration"] for r in script["ranks"]] + [script["cta"]["narration"]],
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": sum(1 for r in results if r["ok"] and not r.get("fake")),
                    "clips_total": len(results), "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
