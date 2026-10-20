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

import argparse
import hashlib
import io
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "link" / "data" / "folders.json"
IMG_DIR = ROOT / "link" / "img"                 # 대표 이미지(쿠팡 객실 사진) 저장본 — 운영자 2026-10-11 "대표 이미지 하나 들어가야 한다"
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


def localize_image(url: str | None, slug: str, rank: int) -> str | None:
    """쿠팡 객실 사진(제휴 홍보용 API 사진)을 내려받아 link/img/<폴더>/<순위>.jpg 로 저장하고 상대 경로를 돌려준다.
    (쿠팡 CDN 주소를 그대로 쓰면 주소가 바뀌거나 막힐 때 그림이 사라진다 — 쿠팡 팩토리 스토어 페이지에서 겪은 문제. 저장본이 안전하다)"""
    if not url or not str(url).startswith("http"):
        return None
    try:
        from PIL import Image
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stay-shorts-factory)"})
        with urllib.request.urlopen(req, timeout=40) as r:
            data = r.read()
        with Image.open(io.BytesIO(data)) as im:
            im = im.convert("RGB")
            if max(im.size) > 1000:
                im.thumbnail((1000, 1000), Image.LANCZOS)
            d = IMG_DIR / slug
            d.mkdir(parents=True, exist_ok=True)
            dest = d / f"{rank}.jpg"
            im.save(dest, "JPEG", quality=86, optimize=True)
        return f"img/{slug}/{rank}.jpg"
    except Exception as e:  # noqa: BLE001
        log(f"대표 이미지 저장 실패 ({url[-50:]}): {str(e)[:60]}")
        return None


def pick_image(rooms: list[dict], theme: str = "") -> str | None:
    """대표 이미지 고르기 — 테마 낱말(온수풀·워터파크…)이 이름에 있는 객실 사진을 먼저, 없으면 첫 사진."""
    rooms = [r for r in rooms if r.get("image")]
    if not rooms:
        return None
    words = [w for w in re.split(r"[\s·/,]+", theme) if len(w) >= 2]
    for r in rooms:
        if any(w in str(r.get("name") or "") for w in words):
            return r["image"]
    return rooms[0]["image"]


def room_tags(name: str) -> list[str]:
    return [t for t, rx in ROOM_TAGS if re.search(rx, name or "", re.I)]


def hotel_entry(rank: int, h: dict, r: dict | None, slug: str = "", theme: str = "") -> dict:
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
    image = h.get("image_local") or localize_image(pick_image(uniq, theme), slug, rank) if slug else None
    return {"rank": rank, "name": h["name"], "city": h.get("city") or "", "hook": h.get("hook") or h.get("signature") or "",
            "blog_30d": h.get("blog_30d"), "facts": facts, "rooms": uniq[:5], "image": image,
            "links": {"coupang": h.get("affiliate_url") or None, "agoda": h.get("agoda_url") or None, "official": h.get("official_site") or None},
            "honest": (r or {}).get("honest") or h.get("honest") or "", "price_band": price_band(h["name"]),
            "caption": " · ".join((r or {}).get("captions") or [])[:80]}


def build(req: dict, hotels: list[dict], script: dict | None) -> dict:
    """hotels 는 3위→1위 순(make_top3 와 같음). script 가 있으면 순위별 자막·아쉬움을 붙인다."""
    ranks = {r.get("rank"): r for r in ((script or {}).get("ranks") or [])}
    slug = slug_of(str(req.get("month") or ""), str(req.get("theme") or ""), str(req.get("region") or ""))
    entries = [hotel_entry(rank, h, ranks.get(rank), slug, str(req.get("theme") or "")) for rank, h in zip((3, 2, 1), hotels)]
    entries.sort(key=lambda e: e["rank"])
    return {"slug": slug, "title": title_of(req), "month": str(req.get("month") or ""), "theme": str(req.get("theme") or ""), "region": str(req.get("region") or ""),
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
    old = next((f for f in (data.get("folders") or []) if f.get("slug") == folder["slug"]), None)
    if old:   # 새 데이터에 사진이 없으면 이전 저장본을 유지한다
        prev = {h.get("name"): h.get("image") for h in old.get("hotels") or []}
        for h in folder["hotels"]:
            h["image"] = h.get("image") or prev.get(h["name"])
    data["folders"] = [f for f in (data.get("folders") or []) if f.get("slug") != folder["slug"]] + [folder]
    data["folders"].sort(key=lambda f: (f.get("month") or ""), reverse=True)
    data["updated"] = date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"폴더 '{folder['title']}' 저장 — 숙소 {len(folder['hotels'])}곳 · 전체 폴더 {len(data['folders'])}개 → {OUT.relative_to(ROOT)}")
    return OUT


def update_hotel(req: dict, h: dict, rank: int, published: bool | None = None) -> Path:
    """숙소 하나만 테마 폴더에 넣거나 갱신한다 (단일 숙소 영상 모드). 같은 폴더의 다른 숙소는 그대로 둔다.
    published: True = 공개(정식 제작 성공) · False = 미리보기(새 숙소는 **숨김** 등록 — 번호만 받고 공개 페이지엔 안 보인다 · 이미 공개된 숙소는 숨기지 않는다) · None = 옛 호출(상태 유지).
    2026-10-20 점검: 규칙 '폴더 페이지 = 영상이 나간 숙소만'(2026-10-12)인데 미리보기가 숙소를 공개 페이지에 올리고 있었다."""
    slug = slug_of(str(req.get("month") or ""), str(req.get("theme") or ""), str(req.get("region") or ""))
    data = {"channel": CHANNEL, "folders": []}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    data["channel"] = CHANNEL
    folder = next((f for f in (data.get("folders") or []) if f.get("slug") == slug), None)
    if not folder:
        folder = {"slug": slug, "title": title_of(req), "month": str(req.get("month") or ""), "theme": str(req.get("theme") or ""),
                  "region": str(req.get("region") or ""), "updated": date.today().isoformat(), "intro": "", "hotels": []}
        data["folders"] = (data.get("folders") or []) + [folder]
    prev = next((x for x in folder["hotels"] if x.get("name") == h["name"]), None)
    rank = int(rank or (prev or {}).get("rank") or (len(folder["hotels"]) + 1))
    entry = hotel_entry(rank, h, None, slug, folder.get("theme") or "")
    # 숙소 고유 번호(no) — 2026-10-12 운영자 "'폴더'는 기계적 → 고유 번호 + 테마명": 전 폴더 통틀어 1부터, 한 번 준 번호는 바꾸지도 재사용하지도 않는다.
    # 영상·끝 카드·캡션의 "프로필 N번" 이 이 값이다. 같은 숙소가 다른 폴더에 또 들어가면 그 숙소의 기존 번호를 그대로 쓴다.
    existing = next((x.get("no") for f in (data.get("folders") or []) for x in (f.get("hotels") or []) if x.get("name") == h["name"] and x.get("no")), None)
    if existing:
        entry["no"] = int(existing)
    else:
        entry["no"] = max([int(x.get("no") or 0) for f in (data.get("folders") or []) for x in (f.get("hotels") or [])] + [0]) + 1
    if prev and not entry.get("image"):
        entry["image"] = prev.get("image")
    if published is True:
        hidden = False
    elif published is False:
        hidden = True if prev is None else bool(prev.get("hidden"))
    else:
        hidden = bool(prev.get("hidden")) if prev else False
    if hidden:
        entry["hidden"] = True
    folder["hotels"] = [x for x in folder["hotels"] if x.get("name") != h["name"]] + [entry]
    folder["hotels"].sort(key=lambda e: e.get("rank") or 99)
    folder["updated"] = date.today().isoformat()
    data["folders"].sort(key=lambda f: (f.get("month") or ""), reverse=True)
    data["updated"] = date.today().isoformat()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"폴더 '{folder['title']}' 에 {h['name']} 갱신 (순위 {rank} · 고유 번호 {entry['no']}{' · 숨김(미리보기)' if entry.get('hidden') else ''}) → 숙소 {len(folder['hotels'])}곳")
    return OUT


def mark_published(req: dict, name: str) -> bool:
    """정식 제작이 성공한 숙소를 공개 페이지에 보이게 한다(숨김 해제). 바뀐 것이 있으면 True."""
    if not OUT.exists():
        return False
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    slug = slug_of(str(req.get("month") or ""), str(req.get("theme") or ""), str(req.get("region") or ""))
    changed = False
    for f in data.get("folders") or []:
        if f.get("slug") != slug:
            continue
        for x in f.get("hotels") or []:
            if x.get("name") == name and x.get("hidden"):
                x.pop("hidden", None); changed = True
        if changed:
            f["updated"] = date.today().isoformat()
    if changed:
        data["updated"] = date.today().isoformat()
        OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        log(f"폴더 공개: {name} (정식 제작 성공)")
    return changed


def save_cover(path: str | Path, slug: str, rank: int) -> str | None:
    """영상에 쓴 사진(로컬 파일)을 폴더 대표 이미지로 저장한다 — 쿠팡 API 사진일 때만 부른다 (공식 홈페이지 사진은 페이지에 올리지 않는 규칙 유지)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            if max(im.size) > 1000:
                im.thumbnail((1000, 1000), Image.LANCZOS)
            d = IMG_DIR / slug
            d.mkdir(parents=True, exist_ok=True)
            im.save(d / f"{rank}.jpg", "JPEG", quality=86, optimize=True)
        return f"img/{slug}/{rank}.jpg"
    except Exception as e:  # noqa: BLE001
        log(f"대표 이미지 저장 실패: {str(e)[:60]}")
        return None


def place_hotel(req: dict, h: dict, rank: int, cover: str | Path | None = None, published: bool | None = None) -> int:
    """단일 숙소 영상용: 숙소를 테마 폴더에 넣고(update_hotel) **숙소 고유 번호(no)** 를 돌려준다.
    영상 끝 카드·나레이션의 "프로필 N번" 은 이 값이다 (2026-10-12 운영자 결정 — 폴더 안 순번이 아니라 전 폴더 통틀어 고유한 번호). 2026-10-11 이름 비공개 결정."""
    slug = slug_of(str(req.get("month") or ""), str(req.get("theme") or ""), str(req.get("region") or ""))
    data = {}
    if OUT.exists():
        try:
            data = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            data = {}
    folder = next((f for f in (data.get("folders") or []) if f.get("slug") == slug), None) or {"hotels": []}
    prev = next((x for x in folder["hotels"] if x.get("name") == h["name"]), None)
    rank = int(rank or (prev or {}).get("rank") or (len(folder["hotels"]) + 1))
    hh = dict(h)
    if cover:
        img = save_cover(cover, slug, rank)
        if img:
            hh["image_local"] = img
    update_hotel(req, hh, rank, published)
    data = json.loads(OUT.read_text(encoding="utf-8"))
    folder = next(f for f in data["folders"] if f.get("slug") == slug)
    return int(next(x for x in folder["hotels"] if x["name"] == h["name"])["no"])


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


def fill_images() -> int:
    """사진이 없는 숙소에 쿠팡 객실 사진을 채운다 (쿠팡 API 만, 0원 · Gemini 없음). 워크플로 stay-shorts-folder 가 부른다."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import discover as dc
    if not OUT.exists():
        log("folders.json 이 없다"); return 1
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cands = {}
    if CANDS.exists():
        cands = {c["name"]: c for c in (json.loads(CANDS.read_text(encoding="utf-8")).get("candidates") or [])}
    filled = 0
    for f in data.get("folders") or []:
        for h in f.get("hotels") or []:
            if h.get("image"):
                continue
            v = dc.coupang_verify(h["name"])
            rooms = [{"name": str(it.get("productName", "")), "image": it.get("productImage")} for it in (v.get("rooms") or [])]
            # 순위표(candidates.json)에 Gemini 가 '이 숙소 객실'로 확인한 이름이 있으면 그 객실만 쓴다 (다른 숙소 사진 혼입 방지)
            known = set((cands.get(h["name"]) or {}).get("coupang", {}).get("room_names") or [])
            if known:
                same = [r for r in rooms if r["name"][:40] in {k[:40] for k in known}]
                rooms = same or rooms
            img = localize_image(pick_image(rooms, f.get("theme") or ""), f["slug"], int(h["rank"]))
            if img:
                h["image"] = img; filled += 1
                if not h.get("rooms"):
                    h["rooms"] = [{"name": r["name"][:60], "tags": room_tags(r["name"]), "image": None} for r in rooms[:5]]
            log(f"{h['name']}: 쿠팡 객실 {len(rooms)}개 → 대표 이미지 {'저장' if img else '없음'}")
    data["updated"] = date.today().isoformat()
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"대표 이미지 {filled}장 채움")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fill-images", action="store_true", help="사진 없는 숙소에 쿠팡 객실 사진을 채운다 (COUPANG 키 필요)")
    a = ap.parse_args()
    sys.exit(fill_images() if a.fill_images else (print(from_report()) or 0))
