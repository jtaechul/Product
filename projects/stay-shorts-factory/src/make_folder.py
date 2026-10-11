#!/usr/bin/env python3
"""프로필 링크 페이지의 **테마 폴더** 데이터 — `link/data/folders.json` 을 만든다 (운영자 2026-10-11 "폴더 페이지·프로필 링크 페이지 만들어").

영상 CTA·캡션이 "프로필 폴더 '11월 실내 온수풀 온천'" 을 가리키므로, 같은 이름의 폴더가 이 파일에 있어야 한다.
폴더 하나 = 테마(월·테마·지역) + 숙소 3곳(순위·확인된 시설·공식 홈페이지 사실·객실 예시·제휴 버튼·후기 속 아쉬움).

규칙
- 가격: 쿠팡 API 가격은 날짜·정가가 없어 **자체 기록(data/discover/prices/*.json)이 3회 이상 같은 10만 원대**일 때만 "20만 원대(조회 기준)" 로 적는다. 아니면 안 적는다
- 사진: 쿠팡 API 가 준 객실 사진(productImage, 제휴 홍보용)만 쓴다. 공식 홈페이지 사진은 페이지에 올리지 않는다(재배포 범위를 영상으로 한정)
- 고지문: 페이지가 항상 표시한다 (link/index.html)
- 호출: make_top3 의 미리보기·제작이 끝날 때 update() 로 폴더를 갱신(같은 slug 는 덮어씀). 손으로: `python3 src/make_folder.py` (최근 report 로 생성)
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "link" / "data" / "folders.json"
PRICES = ROOT / "data" / "discover" / "prices"
REPORT = ROOT / "data" / "runs" / "latest" / "report.json"
CANDS = ROOT / "data" / "discover" / "latest" / "candidates.json"

CHANNEL = {"name": "데이터 호캉스", "tagline": "후기 데이터로 고른 숙소, 테마별 폴더로 정리해 둡니다",
           "note": "네이버 블로그 글 수(최근 30일)로 수요를 재고, 블로그로 확인된 시설만 적습니다. 가격은 날짜가 있는 기록이 3회 이상 쌓인 곳만 범위로 적습니다."}
ROOM_TAGS = [("이용권 포함", r"이용권|입장권|워터파크 포함|오션월드 포함|스파 포함|패키지"), ("조식 포함", r"조식"),
             ("오션뷰", r"오션|바다|해안|항구|씨뷰"), ("취사 가능", r"취사"), ("스위트", r"스위트"), ("패밀리", r"패밀리|키즈|어린이"), ("반려견", r"펫|반려|패트")]


def log(*a):
    print("[folder]", *a, flush=True)


def slug_of(month: str, theme: str, region: str) -> str:
    s = re.sub(r"[^\w가-힣]+", "-", f"{month}-{region}-{theme}".lower()).strip("-")
    return re.sub(r"-+", "-", s)


def title_of(req: dict) -> str:
    """영상 CTA 와 같은 이름 — make_top3.folder_name 과 같은 규칙 (request.json "folder" 가 있으면 그것)."""
    if req.get("folder"):
        return str(req["folder"]).strip()
    m = re.search(r"-(\d{1,2})$", str(req.get("month") or ""))
    theme = re.sub(r"[·/,]+", " ", str(req.get("theme") or "")).strip()
    return (f"{int(m.group(1))}월 " if m else "") + theme


def price_band(name: str) -> str | None:
    """자체 기록 3회 이상 + 전부 같은 10만 원대일 때만 '20만 원대 (조회 기준 10-11)'."""
    recs = []
    for f in sorted(PRICES.glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        v = d.get(name) if isinstance(d, dict) else None
        if isinstance(v, (int, float)) and v > 0:
            recs.append((f.stem, float(v)))
    if len(recs) < 3:
        return None
    bands = {int(v // 100000) for _, v in recs[-3:]}
    if len(bands) != 1:
        return None
    b = bands.pop()
    return f"{b * 10}만 원대 (조회 기준 {recs[-1][0][5:]})" if b >= 1 else f"10만 원 미만 (조회 기준 {recs[-1][0][5:]})"


def room_tags(name: str) -> list[str]:
    return [t for t, rx in ROOM_TAGS if re.search(rx, name or "", re.I)]


def hotel_entry(rank: int, h: dict, r: dict | None) -> dict:
    rooms = []
    for it in (h.get("rooms") or [])[:6]:
        if isinstance(it, str):
            it = {"name": it}
        rooms.append({"name": str(it.get("name") or "")[:60], "tags": room_tags(str(it.get("name") or "")), "image": it.get("image") or None})
    if not rooms:
        rooms = [{"name": n, "tags": room_tags(n), "image": None} for n in (h.get("room_names") or [])[:6]]
    seen, uniq = set(), []
    for rm in rooms:
        if rm["name"] and rm["name"] not in seen:
            seen.add(rm["name"]); uniq.append(rm)
    facts = list(dict.fromkeys([*(h.get("official_facts") or []), *(h.get("verified_facilities") or [])]))[:6]
    image = next((rm["image"] for rm in uniq if rm.get("image")), None)
    return {"rank": rank, "name": h["name"], "city": h.get("city") or "", "hook": h.get("hook") or h.get("signature") or "",
            "blog_30d": h.get("blog_30d"), "facts": facts, "rooms": uniq[:5], "image": image,
            "links": {"coupang": h.get("affiliate_url") or None, "agoda": h.get("agoda_url") or None, "official": h.get("official_site") or None},
            "honest": (r or {}).get("honest") or h.get("honest") or "", "price_band": price_band(h["name"]),
            "caption": " · ".join((r or {}).get("captions") or [])[:80]}


def build(req: dict, hotels: list[dict], script: dict | None) -> dict:
    """hotels 는 3위→1위 순(make_top3 와 같음). script 가 있으면 순위별 자막·아쉬움을 붙인다."""
    ranks = {r.get("rank"): r for r in ((script or {}).get("ranks") or [])}
    entries = [hotel_entry(rank, h, ranks.get(rank)) for rank, h in zip((3, 2, 1), hotels)]
    entries.sort(key=lambda e: e["rank"])
    return {"slug": slug_of(str(req.get("month") or ""), str(req.get("theme") or ""), str(req.get("region") or "")),
            "title": title_of(req), "month": str(req.get("month") or ""), "theme": str(req.get("theme") or ""), "region": str(req.get("region") or ""),
            "updated": date.today().isoformat(), "intro": (script or {}).get("caption") or "", "hotels": entries}


def update(req: dict, hotels: list[dict], script: dict | None) -> Path:
    folder = build(req, hotels, script)
    data = {"channel": CHANNEL, "folders": []}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    data["channel"] = CHANNEL
    data["folders"] = [f for f in (data.get("folders") or []) if f.get("slug") != folder["slug"]] + [folder]
    data["folders"].sort(key=lambda f: (f.get("month") or ""), reverse=True)
    data["updated"] = date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"폴더 '{folder['title']}' 저장 — 숙소 {len(folder['hotels'])}곳 · 전체 폴더 {len(data['folders'])}개 → {OUT.relative_to(ROOT)}")
    return OUT


def from_report() -> Path:
    """최근 report.json(미리보기·제작 기록) + 순위표로 폴더를 만든다 (report 에 없는 지역·제휴 링크는 순위표에서 채운다)."""
    rep = json.loads(REPORT.read_text(encoding="utf-8"))
    cands = {}
    if CANDS.exists():
        cands = {c["name"]: c for c in (json.loads(CANDS.read_text(encoding="utf-8")).get("candidates") or [])}
    sites = {s.get("hotel"): (s.get("crawl") or {}).get("url") for s in (rep.get("photo_sources") or [])}
    hotels = []
    for h in rep.get("hotels") or []:
        c = cands.get(h["name"]) or {}
        hotels.append({**h, "city": h.get("city") or c.get("city") or "", "affiliate_url": h.get("affiliate_url") or c.get("affiliate_url"),
                       "hook": h.get("hook") or (c.get("ai") or {}).get("hook"), "official_site": h.get("official_site") or sites.get(h["name"])})
    req = {"theme": rep.get("theme") or "실내 온수풀·온천", "region": rep.get("region") or "강원", "month": rep.get("month") or "2026-11"}
    # report 에 테마가 없으면 request.json 을 본다
    rq = ROOT / "requests" / "produce" / "request.json"
    if rq.exists():
        try:
            j = json.loads(rq.read_text(encoding="utf-8"))
            req = {k: j.get(k) or req[k] for k in req} | ({"folder": j["folder"]} if j.get("folder") else {})
        except Exception:  # noqa: BLE001
            pass
    return update(req, hotels, rep.get("script"))


if __name__ == "__main__":
    print(from_report())
    sys.exit(0)
