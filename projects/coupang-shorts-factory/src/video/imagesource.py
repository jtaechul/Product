"""라인별 비주얼 소싱 — 각 자막 라인에 '상황에 딱 맞는' 실사 이미지를 배정한다.

설계(2026-07-13 사용자 확정):
  ① 상품 사진은 '상품 자체/기능/스펙'을 설명하는 라인에서만. 나머지(훅·공감·문제·리액션·
     라이프스타일)는 그 장면에 맞는 다른 이미지로 대체 → 단조로움 제거.
  ② 다양한 소스: Pexels(키) + Openverse(CC/PD) + Wikimedia Commons — 라인마다 소스를 돌려
     화풍이 겹치지 않게.
  ③ 매 순간 정사각형이 꽉 차야 하므로, 못 받은 라인은 상품 사진으로 폴백(절대 빈 화면 없음).
  ④ 라인→(상품/이미지) 배정은 Gemini/Claude가 판단(구어체 맥락 이해), 실패 시 stage 휴리스틱.

주의: 무료 대형 라이브러리만 사용(문구 매칭 무제한 + 채널 리스크↓). 텍스트 LLM은 초저가.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

from src.script.generate import (
    GEMINI_BASE, anthropic_key, gemini_key, script_provider)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PEXELS = "https://api.pexels.com/v1/search"
PIXABAY = "https://pixabay.com/api/"
GIPHY = "https://api.giphy.com/v1/gifs/search"
OPENVERSE = "https://api.openverse.org/v1/images/"
WIKIMEDIA = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "miraemarket-shorts/1.0 (+https://youtube.com/@miraemarket)"}

_CATEGORY_QUERIES = {
    "가전": ["cozy living room", "home party friends", "modern apartment"],
    "주방": ["home cooking", "kitchen counter", "family dinner"],
    "생활": ["tidy home", "daily life routine", "minimal room"],
    "미용": ["skincare routine", "beauty mirror", "bathroom vanity"],
    "디지털": ["desk setup", "using smartphone", "modern workspace"],
    "가구": ["interior room", "home decor", "relaxing at home"],
}
_DEFAULT_QUERIES = ["young person at home", "cozy lifestyle", "everyday moment", "city night lights"]


def _pexels_key() -> str:
    return (os.environ.get("SHORTS_PEXELS_API_KEY") or "").strip()


def _pixabay_key() -> str:
    return (os.environ.get("SHORTS_PIXABAY_API_KEY") or "").strip()


def _giphy_key() -> str:
    return (os.environ.get("SHORTS_GIPHY_API_KEY") or "").strip()


# ───────────────────────── 라인별 배정(플랜) ─────────────────────────

def plan_line_visuals(product: dict, lines: list, settings: dict) -> list:
    """각 라인 → {"type":"product"} 또는 {"type":"image","query":"english"}. 길이는 lines와 동일.
    Gemini/Claude로 맥락 판단, 실패/불일치면 stage 휴리스틱으로 폴백."""
    n = len(lines)
    plan = None
    try:
        plan = _plan_via_llm(product, lines, settings)
    except Exception as e:
        print(f"[imgsrc] 라인 플랜 LLM 실패({type(e).__name__}: {e}) → 휴리스틱")
    if not plan or len(plan) != n:
        if plan is not None:
            print(f"[imgsrc] 라인 플랜 길이 불일치({len(plan) if plan else 0}≠{n}) → 휴리스틱")
        plan = _heuristic_plan(product, lines)
    # 정규화 + query 폴백 채움
    cat = str((product or {}).get("category", "")).strip()
    base = _CATEGORY_QUERIES.get(cat, list(_DEFAULT_QUERIES))
    out = []
    for i, item in enumerate(plan):
        typ = str((item or {}).get("type", "image")).lower()
        if typ == "product":
            out.append({"type": "product"})
        else:
            q = str((item or {}).get("query", "")).strip() or base[i % len(base)]
            out.append({"type": "image", "query": q})
    return out


def _heuristic_plan(product: dict, lines: list) -> list:
    """LLM 없이: 상품/스펙 신호가 있는 라인만 product, 나머지는 카테고리 기반 image."""
    cat = str((product or {}).get("category", "")).strip()
    base = _CATEGORY_QUERIES.get(cat, list(_DEFAULT_QUERIES))
    specs = str((product or {}).get("specs", "")) + " " + str((product or {}).get("name", ""))
    spec_tokens = [t for t in re.findall(r"[가-힣A-Za-z0-9]+", specs) if len(t) >= 2][:12]
    plan, img_i = [], 0
    for ln in lines:
        text = str(ln.get("text", ""))
        stage = int(ln.get("stage", 1) or 1)
        hit = any(tok in text for tok in spec_tokens)
        if stage >= 4 and hit:   # 해결/상품 단계 + 스펙 단어 포함 → 상품 기능 설명으로 간주
            plan.append({"type": "product"})
        else:
            plan.append({"type": "image", "query": base[img_i % len(base)]})
            img_i += 1
    return plan


def _plan_via_llm(product: dict, lines: list, settings: dict) -> list | None:
    """Gemini(우선, script.provider=gemini일 때) 또는 Claude로 라인 플랜 JSON 생성."""
    name = str((product or {}).get("name", "")).strip()
    cat = str((product or {}).get("category", "")).strip()
    numbered = "\n".join(f'{i}: {str(l.get("text", "")).strip()}' for i, l in enumerate(lines))
    # 학습: 운영자가 과거 확정한 (자막→검색어) 예시를 few-shot으로 먹여 추천 정확도를 올린다.
    ex = _learning_examples(12)
    shots = ("\n운영자가 과거에 좋다고 고른 예시(자막 → 검색어) — 이 감각을 따라라:\n"
             + "\n".join(f'  "{t}" → "{q}"' for t, q in ex)) if ex else ""
    prompt = (
        "너는 한국어 쇼츠의 각 자막 라인에 넣을 '정사각형 비주얼'을 정하는 편집자다.\n"
        f"상품: {name} (카테고리: {cat})\n"
        "규칙:\n"
        '- 그 라인이 "상품 자체·기능·스펙·사용법"을 설명하면 type="product".\n'
        '- 그 외(훅·공감·문제상황·감정·리액션·비교·라이프스타일)는 type="image"이고, 그 장면에\n'
        "  시각적으로 딱 맞는 영어 스톡 검색어 query(2~4단어, 사람·감정·상황 중심)를 준다.\n"
        "- 특정 브랜드/로고/유명인/워터마크 금지. 매 라인 최대한 '다르게'(같은 이미지 반복 금지)."
        + shots + "\n"
        f"라인:\n{numbered}\n\n"
        f'출력: JSON만. {{"plan":[{{"i":0,"type":"image","query":"..."}}, ...]}} — 라인마다 1개, 총 {len(lines)}개.'
    )
    prefer_gemini = script_provider(settings) == "gemini" and gemini_key()
    if prefer_gemini:
        raw = _gemini_json(prompt)
    elif anthropic_key():
        raw = _claude_json(prompt)
    elif gemini_key():
        raw = _gemini_json(prompt)
    else:
        return None
    data = _extract_json(raw)
    plan = data.get("plan") if isinstance(data, dict) else None
    if isinstance(plan, list):
        plan.sort(key=lambda x: int(x.get("i", 0)) if isinstance(x, dict) else 0)
    return plan


def _gemini_json(prompt: str) -> str:
    key = gemini_key()
    r = requests.post(
        f"{GEMINI_BASE}/models/gemini-2.5-flash:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={"contents": [{"role": "user", "parts": [{"text": prompt}]}],
              "generationConfig": {"maxOutputTokens": 1200, "temperature": 0.7,
                                   "responseMimeType": "application/json",
                                   "thinkingConfig": {"thinkingBudget": 0}}},  # 사고 OFF: JSON 잘림 방지
        timeout=60)
    r.raise_for_status()
    cands = r.json().get("candidates") or []
    parts = (cands[0].get("content") or {}).get("parts") or [] if cands else []
    return "".join(p.get("text", "") for p in parts)


def _claude_json(prompt: str) -> str:
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": anthropic_key(), "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 1200,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=60)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", []))


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    return json.loads(m.group(0)) if m else {}


# ───────────────────────── 소싱(다운로드) ─────────────────────────

def fetch_line_images(product: dict, lines: list, product_images: list,
                      job_dir: Path, settings: dict) -> tuple:
    """라인별 이미지 경로 목록(lines와 동일 길이) + 플랜 반환.
    product 라인 → 상품 사진 / image 라인 → 소스에서 문구 매칭 이미지(다양 소스 로테이션).
    못 받으면 상품 사진 폴백(빈 화면 없음). 상품 사진도 없으면 None(렌더가 브랜드 카드)."""
    out_dir = Path(job_dir) / "scene_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = plan_line_visuals(product, lines, settings)
    prod0 = Path(product_images[0]) if product_images else None
    line_images, seen, img_i = [], set(), 0
    n_img = sum(1 for p in plan if p["type"] == "image")
    got = 0
    for i, pl in enumerate(plan):
        if pl["type"] == "product" and prod0 is not None:
            line_images.append(prod0)
            continue
        url = _search_one(pl.get("query", ""), seen, order_seed=img_i) if pl["type"] == "image" else None
        img_i += 1
        ext = ".gif" if url and url.lower().split("?")[0].endswith(".gif") else ".jpg"
        dest = out_dir / f"line_{i:02d}{ext}"
        if url and _download_image(url, dest):
            line_images.append(dest)
            got += 1
        else:
            line_images.append(prod0)  # 폴백: 절대 빈 화면 없음
    print(f"[imgsrc] 라인 {len(plan)}개 · 이미지 라인 {n_img} → 문구 이미지 {got}장 확보"
          f"(부족분·상품라인은 상품 사진). 소스: Pexels/Openverse/Wikimedia")
    return line_images, plan


def _search_one(query: str, seen: set, order_seed: int = 0):
    """검색어 1개 → 미디어 URL 1개. 깨끗한 스톡(Pexels·Pixabay)을 우선, 그다음 재미있는 움짤(Giphy),
    끝으로 CC 아카이브(Openverse·Wikimedia) 폴백. Giphy/Pixabay는 키 없으면 자동 건너뜀."""
    if not query:
        return None
    for fn in (_pexels, _pixabay, _giphy, _openverse, _wikimedia):
        try:
            u = fn(query, seen)
            if u:
                return u
        except Exception as e:
            print(f"[imgsrc] {fn.__name__} 실패({query}: {type(e).__name__})")
    return None


def _search_many(query: str, n: int, seen: set) -> list:
    """후보 여러 장 — 소스별 최대 2장씩 모아 다양성 확보. [{url, source}] 반환.
    기존 단일 소스 함수는 seen에 추가하며 '안 쓴 것 중 첫 장'을 주므로 반복 호출 시 다른 장이 나온다."""
    if not query:
        return []
    out = []
    for fn in (_pexels, _pixabay, _giphy, _openverse, _wikimedia):
        src = fn.__name__.lstrip("_")
        for _ in range(2):
            if len(out) >= n:
                return out
            try:
                u = fn(query, seen)
            except Exception:
                u = None
            if not u:
                break
            out.append({"url": u, "source": src})
    return out


def fetch_candidates(product: dict, lines: list, job_dir: Path, settings: dict,
                     product_images: list | None = None, per_line: int = 6) -> list:
    """관리자 선택기용 — 라인마다 후보 이미지 여러 장 확보 + candidates.json manifest 작성.
    상품 사진은 항상 후보에 포함(사용자가 상품을 강제 선택 가능). 이미지 라인은 다양 소스에서 수집."""
    plan = plan_line_visuals(product, lines, settings)
    out_dir = Path(job_dir) / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    product_images = [str(p) for p in (product_images or []) if Path(p).exists()]
    manifest, seen = [], set()
    for i, (ln, pl) in enumerate(zip(lines, plan)):
        entry = {"line_i": i, "text": ln.get("text", ""), "stage": ln.get("stage"),
                 "punch": bool(ln.get("punch")), "type": pl["type"],
                 "query": pl.get("query", ""), "candidates": []}
        for p in product_images[:2]:   # 상품 사진 후보(강제 선택용)
            entry["candidates"].append({"file": p, "source": "product", "url": None, "is_product": True})
        if pl["type"] == "image":
            for j, c in enumerate(_search_many(pl.get("query", ""), per_line, seen)):
                ext = ".gif" if c["url"].lower().split("?")[0].endswith(".gif") else ".jpg"
                dest = out_dir / f"line{i:02d}_{j}{ext}"
                if _download_image(c["url"], dest):
                    entry["candidates"].append({"file": str(dest), "source": c["source"], "url": c["url"]})
        manifest.append(entry)
    (Path(job_dir) / "candidates.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(e["candidates"]) for e in manifest)
    print(f"[imgsrc] 후보 생성: {len(manifest)}라인 · 총 {total}장")
    return manifest


def load_selections(row_hash: str, lines: list, project_root: Path, job_dir: Path) -> list | None:
    """data/selections/{row_hash}.json 있으면 라인별 선택 이미지 경로 목록(lines 정렬) 반환, 없으면 None.
    선택 항목이 url이면 내려받고, 로컬/상품 파일이면 그대로. 학습 로그도 남긴다."""
    sel_path = Path(project_root) / "data" / "selections" / f"{row_hash}.json"
    if not sel_path.exists():
        return None
    try:
        data = json.loads(sel_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[imgsrc] selections 파싱 실패({e}) → 자동 소싱")
        return None
    picks = {int(x.get("line_i", -1)): x for x in (data.get("lines") or [])}
    dl_dir = Path(job_dir) / "selected"
    dl_dir.mkdir(parents=True, exist_ok=True)
    line_images, used = [], 0
    for i in range(len(lines)):
        pick = picks.get(i)
        if not pick:
            line_images.append(None)
            continue
        f = pick.get("file")
        if f and Path(f).exists():   # 저장소에 커밋된 파일(업로드본 등)
            line_images.append(Path(f))
            used += 1
            continue
        url = pick.get("url")
        if url:
            ext = ".gif" if url.lower().split("?")[0].endswith(".gif") else ".jpg"
            dest = dl_dir / f"sel_{i:02d}{ext}"
            if _download_image(url, dest):
                line_images.append(dest)
                used += 1
                continue
        line_images.append(None)
    print(f"[imgsrc] 운영자 선택 이미지 적용: {used}/{len(lines)}라인 (data/selections/{row_hash}.json)")
    _record_learning(project_root, lines, picks)
    return line_images


def _record_learning(project_root: Path, lines: list, picks: dict):
    """운영자가 확정한 (자막 문장 → 검색어/소스) 쌍을 학습 로그에 축적 → 다음 검색어 추천에 few-shot."""
    log = Path(project_root) / "data" / "vision_examples.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, ln in enumerate(lines):
        pk = picks.get(i)
        if not pk:
            continue
        q = str(pk.get("query", "")).strip()
        if q:
            rows.append(json.dumps({"text": str(ln.get("text", "")).strip(), "query": q,
                                    "source": pk.get("source", "")}, ensure_ascii=False))
    if rows:
        with log.open("a", encoding="utf-8") as f:
            f.write("\n".join(rows) + "\n")


def _learning_examples(limit: int = 12) -> list:
    """최근 학습 예시(자막→검색어) 몇 개 — 검색어 추천 프롬프트에 few-shot으로 먹인다."""
    log = PROJECT_ROOT / "data" / "vision_examples.jsonl"
    if not log.exists():
        return []
    out = []
    try:
        for line in log.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if line:
                d = json.loads(line)
                if d.get("text") and d.get("query"):
                    out.append((d["text"], d["query"]))
    except Exception:
        return []
    return out


def _pixabay(query: str, seen: set):
    pk = _pixabay_key()
    if not pk:
        return None
    r = requests.get(PIXABAY, params={"key": pk, "q": query, "per_page": 8,
                                      "image_type": "photo", "safesearch": "true",
                                      "orientation": "vertical"}, timeout=25)
    if not r.ok:
        return None
    for hit in r.json().get("hits", []):
        u = hit.get("largeImageURL") or hit.get("webformatURL")
        if u and u not in seen:
            seen.add(u)
            return u
    return None


def _giphy(query: str, seen: set):
    """재미있는 반응 움짤(GIF). 렌더가 정사각형에 애니메이션으로 깐다(더 코믹·자주 바뀜)."""
    gk = _giphy_key()
    if not gk:
        return None
    r = requests.get(GIPHY, params={"api_key": gk, "q": query, "limit": 8,
                                    "rating": "pg-13", "lang": "en"}, timeout=25)
    if not r.ok:
        return None
    for it in r.json().get("data", []):
        imgs = it.get("images") or {}
        u = ((imgs.get("downsized_medium") or {}).get("url")
             or (imgs.get("original") or {}).get("url"))
        if u and u not in seen:
            seen.add(u)
            return u
    return None


def _pexels(query: str, seen: set):
    pk = _pexels_key()
    if not pk:
        return None
    r = requests.get(PEXELS, headers={"Authorization": pk},
                     params={"query": query, "per_page": 8, "orientation": "square"}, timeout=25)
    if not r.ok:
        return None
    for ph in r.json().get("photos", []):
        u = (ph.get("src") or {}).get("large") or (ph.get("src") or {}).get("original")
        if u and u not in seen:
            seen.add(u)
            return u
    return None


def _openverse(query: str, seen: set):
    r = requests.get(OPENVERSE, headers=UA,
                     params={"q": query, "page_size": 8, "license_type": "all", "mature": "false"},
                     timeout=25)
    if not r.ok:
        return None
    for it in r.json().get("results", []):
        u = it.get("url") or it.get("thumbnail")
        if u and u not in seen:
            seen.add(u)
            return u
    return None


def _wikimedia(query: str, seen: set):
    r = requests.get(WIKIMEDIA, headers=UA, params={
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 8, "prop": "imageinfo", "iiprop": "url",
        "iiurlwidth": 1080, "format": "json"}, timeout=25)
    if not r.ok:
        return None
    pages = (r.json().get("query") or {}).get("pages") or {}
    for pg in pages.values():
        ii = (pg.get("imageinfo") or [{}])[0]
        u = ii.get("thumburl") or ii.get("url")
        if u and u not in seen and re.search(r"\.(jpe?g|png)$", u, re.I):
            seen.add(u)
            return u
    return None


def _download_image(url: str, dest: Path) -> bool:
    """이미지 다운로드 + 검증(PIL open + 최소 크기). 실패 시 False."""
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if not r.ok or not r.content:
            return False
        dest.write_bytes(r.content)
        from PIL import Image
        with Image.open(dest) as im:
            im.verify()
        with Image.open(dest) as im:
            if min(im.size) < 300:
                dest.unlink(missing_ok=True)
                return False
        return True
    except Exception:
        dest.unlink(missing_ok=True)
        return False
