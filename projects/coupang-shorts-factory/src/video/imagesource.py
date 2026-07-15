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
import random
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

# 카테고리별 폴백 검색어 — 라인 수가 풀보다 많아도 잘 반복되지 않게 넉넉히(라인별 차별화 #1).
_CATEGORY_QUERIES = {
    "가전": ["cozy living room", "home party friends", "modern apartment", "messy desk cables",
             "person relaxing sofa", "smart home gadget", "tired after chores", "surprised face closeup"],
    "주방": ["home cooking mess", "kitchen counter clutter", "family dinner table", "washing dishes tired",
             "quick meal alone", "spilled coffee morning", "person tasting food", "empty fridge"],
    "생활": ["messy room before", "daily life routine", "minimal tidy room", "laundry pile",
             "person cleaning home", "small apartment living", "organizing drawer", "frustrated at home"],
    "미용": ["skincare routine mirror", "beauty vanity table", "tired skin morning", "bathroom shelf",
             "person applying cream", "hair styling struggle", "makeup closeup", "self care evening"],
    "디지털": ["messy desk setup", "using smartphone night", "modern workspace", "tangled charger cables",
              "person working laptop", "gaming setup rgb", "confused looking phone", "coffee and laptop"],
    "가구": ["small interior room", "home decor cozy", "relaxing at home", "assembling furniture",
             "cramped apartment", "person on sofa", "moving boxes", "tidy bedroom"],
}
_DEFAULT_QUERIES = ["young person at home", "cozy lifestyle indoor", "everyday moment candid",
                    "city night lights", "person surprised reaction", "tired stressed person",
                    "messy before cleanup", "relaxing weekend home", "curious looking closeup",
                    "frustrated daily struggle"]
# 재미 소스에 붙이는 수식어(Giphy 키 없을 때 스톡을 더 웃기게)
_FUNNY_MODS = ["funny", "hilarious", "silly", "awkward", "goofy reaction", "shocked funny"]


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
            line_images.append(prod0)   # 상품 사진은 product(기능 설명) 라인에만
            continue
        # 이미지 라인: 라인마다 다른 order_seed로 다른 결과 → 라인 간 차별화(#1)
        url = _search_one(pl.get("query", ""), seen, order_seed=img_i) if pl["type"] == "image" else None
        img_i += 1
        ext = ".gif" if url and url.lower().split("?")[0].endswith(".gif") else ".jpg"
        dest = out_dir / f"line_{i:02d}{ext}"
        if url and _download_image(url, dest):
            line_images.append(dest)
            got += 1
        else:
            # ⭐ 실패해도 상품 사진으로 때우지 않는다(상품 반복 방지 #3) → None(렌더가 브랜드 패널)
            line_images.append(None)
    print(f"[imgsrc] 라인 {len(plan)}개 · 이미지 라인 {n_img} → 문구 이미지 {got}장 확보"
          f"(상품 사진은 product 라인만, 실패는 브랜드 패널). 소스: Pexels/Openverse/Wikimedia")
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


def _search_many(query: str, n: int, seen: set, page: int = 1) -> list:
    """후보 여러 장 — 소스별 최대 2장씩 모아 다양성 확보. [{url, source}] 반환.
    기존 단일 소스 함수는 seen에 추가하며 '안 쓴 것 중 첫 장'을 주므로 반복 호출 시 다른 장이 나온다.
    page: 결과 페이지(관리자 '다시 찾기'가 매 실행 다른 page를 주면 완전히 다른 후보가 나온다)."""
    if not query:
        return []
    out = []
    for fn in (_pexels, _pixabay, _giphy, _openverse, _wikimedia):
        src = fn.__name__.lstrip("_")
        for _ in range(2):
            if len(out) >= n:
                return out
            try:
                u = fn(query, seen, page)
            except Exception:
                u = None
            if not u:
                break
            out.append({"url": u, "source": src})
    return out


def _meme_repo_rel(mp) -> str:
    """밈 절대경로 → 저장소 상대경로(assets/memes/xxx.png). 렌더 시 load_selections가 그대로 연다."""
    try:
        return str(Path(mp).resolve().relative_to(PROJECT_ROOT))
    except Exception:
        return str(mp)


def _pick_line_memes(project_root: Path, text: str, used: set, k: int) -> list:
    """라인 텍스트에 어울리는 밈을 고르되, 이미 다른 라인이 쓴 밈은 후순위(로테이션)로 밀어
    라인마다 다른 밈이 오게 한다(반복 완화 #1). 반환: 경로 리스트(최대 k)."""
    from src.video import memes
    lib = memes.load_library(project_root)
    if not lib:
        return []
    text = text or ""
    scored = []
    for m in lib:
        hits = sum(1 for kw in (m.get("situations") or []) if kw and kw in text)
        fresh = 0 if str(m["_path"]) in used else 3   # 안 쓴 밈 가산 → 라인 간 중복 억제
        scored.append((hits * 10 + fresh, m["_path"]))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:max(0, k)]]


def _funny_urls(query: str, seen: set, page: int, n: int) -> list:
    """재미 소스 URL n개: Giphy GIF 우선(키 있으면), 부족분은 'funny 수식어' 스톡(#2).
    반환: [{url, source}] — source에 'giphy'/'funny' 포함(재미 집계용)."""
    out = []
    if _giphy_key():
        for _ in range(n):
            try:
                u = _giphy(query or "funny reaction", seen, page)
            except Exception:
                u = None
            if not u:
                break
            out.append({"url": u, "source": "giphy"})
    if len(out) < n:
        mod = _FUNNY_MODS[page % len(_FUNNY_MODS)]
        fq = (f"{mod} {query}".strip()) or f"{mod} person reaction"
        for fn in (_pexels, _openverse, _pixabay):
            for _ in range(2):
                if len(out) >= n:
                    break
                try:
                    u = fn(fq, seen, page)
                except Exception:
                    u = None
                if not u:
                    break
                out.append({"url": u, "source": fn.__name__.lstrip("_") + "-funny"})
            if len(out) >= n:
                break
    return out


def _is_funny(c: dict) -> bool:
    """후보가 '재미' 부류인지 — 밈 / Giphy GIF / funny 수식어 스톡."""
    s = str(c.get("source") or "")
    return bool(c.get("is_meme")) or "giphy" in s or "funny" in s


def _dl_candidate(out_dir: Path, i: int, k: int, url: str):
    """후보 이미지/움짤 다운로드 → 경로(실패 시 None). 파일명은 라인·순번으로 유일."""
    ext = ".gif" if url.lower().split("?")[0].endswith(".gif") else ".jpg"
    dest = out_dir / f"line{i:02d}_{k}{ext}"
    return dest if _download_image(url, dest) else None


def fetch_candidates(product: dict, lines: list, job_dir: Path, settings: dict,
                     product_images: list | None = None, per_line: int = 6,
                     only_line: int | None = None) -> list:
    """관리자 선택기용 — 라인마다 후보를 모은다. 설계(2026-07-15 사용자 개선):
    ① 라인마다 다른 검색 페이지 + 밈 로테이션으로 '라인별 차별화'(같은 이미지 반복 제거, #1)
    ② 후보의 절반 이상을 재미(밈·GIF·funny 스톡)로 구성(#2)
    ③ 상품 사진 후보는 'product 타입 라인'에만(그 외 라인엔 상품 후보 없음, #3)
    only_line 지정 시 그 라인 하나만 재생성('다시 찾기' 라인별 — 파이프라인이 병합)."""
    plan = plan_line_visuals(product, lines, settings)
    out_dir = Path(job_dir) / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    product_images = [str(p) for p in (product_images or []) if Path(p).exists()]
    base_page = random.randint(1, 6)
    regular_n = max(2, per_line - 4)
    manifest, seen, used_memes = [], set(), set()
    for i, (ln, pl) in enumerate(zip(lines, plan)):
        if only_line is not None and i != int(only_line):
            continue
        text = ln.get("text", "")
        query = pl.get("query", "")
        line_page = base_page + i          # 라인마다 다른 결과 창 → 라인 간 차별화(#1)
        entry = {"line_i": i, "text": text, "stage": ln.get("stage"),
                 "punch": bool(ln.get("punch")), "type": pl["type"], "query": query, "candidates": []}
        cands = entry["candidates"]
        k = 0
        # ① 상품 사진 — product 타입 라인에만(#3)
        if pl["type"] == "product":
            for p in product_images[:2]:
                cands.append({"file": p, "source": "product", "url": None, "is_product": True})
        # ② 재미(밈) — 로테이션 2장(#1·#2)
        for mp in _pick_line_memes(PROJECT_ROOT, text, used_memes, 2):
            used_memes.add(str(mp))
            cands.append({"file": str(mp), "source": "meme", "url": None,
                          "is_meme": True, "meme_rel": _meme_repo_rel(mp)})
        # ③ 재미(GIF/funny 스톡) — 2장(#2)
        for c in _funny_urls(query, seen, line_page, 2):
            d = _dl_candidate(out_dir, i, k, c["url"]); k += 1
            if d:
                cands.append({"file": str(d), "source": c["source"], "url": c["url"]})
        # ④ 일반 라인 이미지 — 고유 검색어 + 라인별 페이지(#1)
        for c in _search_many(query, regular_n, seen, line_page):
            d = _dl_candidate(out_dir, i, k, c["url"]); k += 1
            if d:
                cands.append({"file": str(d), "source": c["source"], "url": c["url"]})
        # ⑤ 재미 비중 보정 — 재미가 절반 미만이면 더 채운다(#2, 최대 4회)
        for _ in range(4):
            if sum(1 for c in cands if _is_funny(c)) * 2 >= len(cands) or not cands:
                break
            added = False
            for c in _funny_urls(query, seen, line_page + 1, 1):
                d = _dl_candidate(out_dir, i, k, c["url"]); k += 1
                if d:
                    cands.append({"file": str(d), "source": c["source"], "url": c["url"]}); added = True
            if not added:   # 소스가 막히면 밈 로테이션으로 보충
                more = _pick_line_memes(PROJECT_ROOT, text, used_memes, 1)
                if not more:
                    break
                for mp in more:
                    used_memes.add(str(mp))
                    cands.append({"file": str(mp), "source": "meme", "url": None,
                                  "is_meme": True, "meme_rel": _meme_repo_rel(mp)})
            line_page += 1
        manifest.append(entry)
    (Path(job_dir) / "candidates.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(e["candidates"]) for e in manifest)
    funny_total = sum(1 for e in manifest for c in e["candidates"] if _is_funny(c))
    tag = f"(라인 {only_line}만)" if only_line is not None else ""
    extra = "" if _giphy_key() else " · Giphy 키 없음(밈/funny 스톡 위주 — 더 많은 GIF는 SHORTS_GIPHY_API_KEY 등록)"
    print(f"[imgsrc] 후보 생성{tag}: {len(manifest)}라인 · 총 {total}장 (재미 {funny_total}장){extra}")
    return manifest


def load_selections(row_hash: str, lines: list, project_root: Path, job_dir: Path,
                    product_images: list | None = None) -> list | None:
    """data/selections/{row_hash}.json 있으면 라인별 '선택 이미지 목록'(lines 정렬) 반환, 없으면 None.
    각 라인은 여러 장 선택 가능(2026-07-14) → line_images[i] = [경로...] (렌더가 그 구간 슬라이드쇼).
    url이면 내려받고, 커밋 파일(업로드본)이면 그대로.
    ⭐ 상품 사진은 '운영자가 그 라인에 상품을 고른 경우에만' 나온다(2026-07-15 사용자 개선 #3):
      is_product 픽 → 실제 상품 사진 경로를 넣고, 안 고른 라인은 빈칸([])으로 둬 렌더가 브랜드
      패널로 채운다(상품 사진으로 때우지 않음). 포맷: {lines:[{line_i, picks:[...]}]} — 구형 단일도 허용."""
    sel_path = Path(project_root) / "data" / "selections" / f"{row_hash}.json"
    if not sel_path.exists():
        return None
    try:
        data = json.loads(sel_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[imgsrc] selections 파싱 실패({e}) → 자동 소싱")
        return None
    prod0 = next((Path(p) for p in (product_images or []) if Path(p).exists()), None)
    by_line = {int(x.get("line_i", -1)): x for x in (data.get("lines") or [])}
    dl_dir = Path(job_dir) / "selected"
    dl_dir.mkdir(parents=True, exist_ok=True)
    line_images, used = [], 0
    for i in range(len(lines)):
        entry = by_line.get(i)
        if not entry:
            line_images.append([])
            continue
        picks = entry.get("picks")
        if not isinstance(picks, list):    # 구형 단일 포맷(entry 자체가 픽) 하위호환
            picks = [entry]
        imgs = []
        for j, pk in enumerate(picks):
            f = pk.get("file")
            if f and Path(f).exists():      # 저장소에 커밋된 파일(업로드본·밈 등)
                imgs.append(Path(f)); used += 1; continue
            url = pk.get("url")
            if url:
                ext = ".gif" if url.lower().split("?")[0].endswith(".gif") else ".jpg"
                dest = dl_dir / f"sel_{i:02d}_{j}{ext}"
                if _download_image(url, dest):
                    imgs.append(dest); used += 1; continue
            if pk.get("is_product") and prod0 is not None:   # 상품을 고른 라인에만 상품 사진
                imgs.append(prod0); used += 1
        line_images.append(imgs)
    sel_lines = sum(1 for x in line_images if x)
    print(f"[imgsrc] 운영자 선택 적용: {sel_lines}/{len(lines)}라인 · 이미지 {used}장 "
          f"(data/selections/{row_hash}.json · 미선택 라인은 브랜드 패널)")
    _record_learning(project_root, lines, by_line)
    return line_images


def _record_learning(project_root: Path, lines: list, by_line: dict):
    """운영자가 확정한 (자막 → 검색어/소스) 쌍을 학습 로그에 축적 → 다음 검색어 추천 few-shot.
    라인당 여러 픽이면 각 픽을 기록(다중선택 지원)."""
    log = Path(project_root) / "data" / "vision_examples.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, ln in enumerate(lines):
        entry = by_line.get(i)
        if not entry:
            continue
        picks = entry.get("picks") if isinstance(entry.get("picks"), list) else [entry]
        for pk in picks:
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


def _pixabay(query: str, seen: set, page: int = 1):
    pk = _pixabay_key()
    if not pk:
        return None
    r = requests.get(PIXABAY, params={"key": pk, "q": query, "per_page": 8, "page": max(1, page),
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


def _giphy(query: str, seen: set, page: int = 1):
    """재미있는 반응 움짤(GIF). 렌더가 정사각형에 애니메이션으로 깐다(더 코믹·자주 바뀜)."""
    gk = _giphy_key()
    if not gk:
        return None
    r = requests.get(GIPHY, params={"api_key": gk, "q": query, "limit": 8,
                                    "offset": max(0, page - 1) * 8,
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


def _pexels(query: str, seen: set, page: int = 1):
    pk = _pexels_key()
    if not pk:
        return None
    r = requests.get(PEXELS, headers={"Authorization": pk},
                     params={"query": query, "per_page": 8, "page": max(1, page),
                             "orientation": "square"}, timeout=25)
    if not r.ok:
        return None
    for ph in r.json().get("photos", []):
        u = (ph.get("src") or {}).get("large") or (ph.get("src") or {}).get("original")
        if u and u not in seen:
            seen.add(u)
            return u
    return None


def _openverse(query: str, seen: set, page: int = 1):
    r = requests.get(OPENVERSE, headers=UA,
                     params={"q": query, "page_size": 8, "page": max(1, page),
                             "license_type": "all", "mature": "false"},
                     timeout=25)
    if not r.ok:
        return None
    for it in r.json().get("results", []):
        u = it.get("url") or it.get("thumbnail")
        if u and u not in seen:
            seen.add(u)
            return u
    return None


def _wikimedia(query: str, seen: set, page: int = 1):
    r = requests.get(WIKIMEDIA, headers=UA, params={
        "action": "query", "generator": "search", "gsrsearch": f"{query} filetype:bitmap",
        "gsrnamespace": 6, "gsrlimit": 8, "gsroffset": max(0, page - 1) * 8,
        "prop": "imageinfo", "iiprop": "url",
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
