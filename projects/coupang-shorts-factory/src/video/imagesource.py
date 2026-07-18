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
    # 정규화 — image 라인은 keywords(라인 명사에서 뽑은 검색어들) 리스트로 통일. query=keywords[0](하위호환).
    cat = str((product or {}).get("category", "")).strip()
    base = _CATEGORY_QUERIES.get(cat, list(_DEFAULT_QUERIES))
    out = []
    for i, item in enumerate(plan):
        item = item or {}
        typ = str(item.get("type", "image")).lower()
        if typ == "product":
            out.append({"type": "product"})
            continue
        kws = item.get("keywords")
        if isinstance(kws, str):
            kws = [kws]
        kws = [str(k).strip() for k in (kws or []) if str(k).strip()]
        if not kws:
            q = str(item.get("query", "")).strip()
            kws = [q] if q else [base[i % len(base)], base[(i + 3) % len(base)]]
        out.append({"type": "image", "keywords": kws, "query": kws[0]})
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
        else:   # LLM 없을 때 폴백 — 카테고리 검색어 2개(라인마다 다르게)
            plan.append({"type": "image",
                         "keywords": [base[img_i % len(base)], base[(img_i + 2) % len(base)]]})
            img_i += 1
    return plan


def _plan_via_llm(product: dict, lines: list, settings: dict) -> list | None:
    """Gemini(우선, script.provider=gemini일 때) 또는 Claude로 라인 플랜 JSON 생성."""
    name = str((product or {}).get("name", "")).strip()
    cat = str((product or {}).get("category", "")).strip()
    numbered = "\n".join(f'{i}: {str(l.get("text", "")).strip()}' for i, l in enumerate(lines))
    # 학습: 운영자가 과거 확정한 (자막→검색어) 예시를 few-shot으로 먹여 추천 정확도를 올린다.
    ex = _learning_examples(20)
    shots = ("\n운영자가 과거에 좋다고 고른 예시(자막 → 검색어) — 이 감각을 참고:\n"
             + "\n".join(f'  "{t}" → "{q}"' for t, q in ex)) if ex else ""
    prompt = (
        "너는 한국어 쇼츠의 각 자막 라인에 넣을 '정사각형 비주얼'을 정하는 편집자다.\n"
        f"상품: {name} (카테고리: {cat})\n"
        "핵심: 그 라인 문장에 **실제로 등장하는 구체적인 명사·사물·행동**을 뽑아 영어 검색어로 준다.\n"
        "추상적 감정·분위기 말고 **눈에 보이는 것(사물·장소·동작)** 위주로. 그래야 관련 있는 이미지가 뜬다.\n"
        "규칙:\n"
        '- 그 라인이 "상품 자체·기능·스펙·사용법"을 설명하면 {"type":"product"}.\n'
        '- 그 외 라인은 {"type":"image","keywords":[...]}: 그 문장의 사물/장소/행동을 영어 검색어\n'
        "  2~4개(각 1~2단어)로. 문장에 사물이 없으면 그 상황을 그리는 사물·행동으로 바꿔라.\n"
        "예시(감 잡아라):\n"
        '  "밤새 에어컨 켜도 땀범벅" → ["air conditioner","sweating in bed","hot night"]\n'
        '  "분명 얼음골이었는데 찜질방" → ["ice","sauna steam","sweating"]\n'
        '  "침대에 누웠는데 배신감이" → ["bed","tossing in bed","frustrated"]\n'
        '  "냉장고 열었더니 미쳤다" → ["refrigerator","shocked face","opening fridge"]\n'
        "- 브랜드/로고/유명인/워터마크 금지."
        + shots + "\n"
        f"라인:\n{numbered}\n\n"
        f'출력: JSON만. {{"plan":[{{"i":0,"type":"image","keywords":["...","..."]}}, ...]}} — 라인마다 1개, 총 {len(lines)}개.'
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
    giphy_only = _giphy_only(settings)
    line_images, seen, got = [], set(), 0
    n_img = sum(1 for p in plan if p["type"] == "image")
    for i, pl in enumerate(plan):
        if pl["type"] == "product" and prod0 is not None:
            line_images.append(prod0)   # 상품 사진은 product(기능 설명) 라인에만
            continue
        # 이미지 라인: 라인 명사(keywords)로 검색(Giphy 우선/ giphy_only면 GIF만). 라인마다 다른 페이지.
        kws = pl.get("keywords") or ([pl.get("query")] if pl.get("query") else [])
        res = _keyword_urls(kws, seen, 1 + i * 2, 1, giphy_only)
        url = res[0]["url"] if res else None
        ext = ".gif" if url and url.lower().split("?")[0].endswith(".gif") else ".jpg"
        dest = out_dir / f"line_{i:02d}{ext}"
        if url and _download_image(url, dest):
            line_images.append(dest)
            got += 1
        else:
            # ⭐ 실패해도 상품 사진으로 때우지 않는다(상품 반복 방지 #3) → None(렌더가 브랜드 패널)
            line_images.append(None)
    src = "Giphy(GIF)만" if giphy_only else "Giphy 우선 + 스톡"
    print(f"[imgsrc] 라인 {len(plan)}개 · 이미지 라인 {n_img} → 문구 이미지 {got}장 확보"
          f"(상품 사진은 product 라인만, 실패는 브랜드 패널). 소스: {src}")
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
    """라인 텍스트에 어울리는 밈을 고른다. 이미 쓴 밈(used, basename)은 '무조건 뒤로' 밀어
    안 쓴 밈이 있으면 반드시 그걸 먼저 준다 → 라인마다·'다시 찾기'마다 다른 밈이 나온다.
    (안 쓴 밈이 부족할 때만 쓴 밈으로 폴백.) 반환: 경로 리스트(최대 k)."""
    from src.video import memes
    lib = memes.load_library(project_root)
    if not lib:
        return []
    text = text or ""
    def hits(m):
        return sum(1 for kw in (m.get("situations") or []) if kw and kw in text)
    fresh = sorted((m for m in lib if Path(m["_path"]).name not in used), key=lambda m: -hits(m))
    stale = sorted((m for m in lib if Path(m["_path"]).name in used), key=lambda m: -hits(m))
    ordered = fresh + stale   # 안 쓴 밈 먼저(매칭 순), 부족하면 쓴 밈
    return [m["_path"] for m in ordered[:max(0, k)]]


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


def _giphy_only(settings: dict) -> bool:
    return bool((settings or {}).get("images", {}).get("giphy_only", False))


def _keyword_urls(keywords: list, seen: set, base_page: int, n: int, giphy_only: bool,
                  stock_first: bool = True) -> list:
    """라인의 명사 keywords를 돌아가며 후보 URL n개 확보 — 그 라인 내용과 관련된 이미지가 나오게.
    2026-07-16 근접성 우선 개편: 슬롯을 번갈아 ① 실사 스톡(Pexels/Pixabay/Openverse/Wikimedia —
    자막 키워드와 가장 근접한 매칭) ② Giphy(재미)로 채워 '관련성 반 + 재미 반'을 보장한다.
    stock_first=False(운영자가 GIF를 더 골라온 학습 결과)면 GIF 슬롯이 먼저. giphy_only=true면 GIF만.
    반환 [{url, source, keyword}]. 키워드마다·페이지마다 달라 라인 간 중복도 준다."""
    keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()] or ["surprising gadget"]
    have_giphy = bool(_giphy_key())
    stock_chain = (_pexels, _pixabay, _openverse, _wikimedia)
    out, kwi, tries = [], 0, 0
    while len(out) < n and tries < n * 6 + 10:
        kw = keywords[kwi % len(keywords)]
        page = base_page + kwi
        kwi += 1
        tries += 1
        # 이번 슬롯의 소스 순서: 짝수/홀수 슬롯을 스톡↔GIF로 번갈아(선호 학습이 시작 순서를 정함)
        want_stock = (not giphy_only) and (((len(out) % 2 == 0) == stock_first) or not have_giphy)
        if giphy_only:
            order = [_giphy] if have_giphy else []
        elif want_stock:
            order = list(stock_chain) + ([_giphy] if have_giphy else [])
        else:
            order = ([_giphy] if have_giphy else []) + list(stock_chain)
        u, src = None, None
        for fn in order:
            try:
                u = fn(kw, seen, page)
            except Exception:
                u = None
            if u:
                src = fn.__name__.lstrip("_")
                break
        if u:
            out.append({"url": u, "source": src, "keyword": kw})
    return out


def _source_prefs(limit: int = 60) -> list:
    """운영자가 실제로 고른 픽의 소스 선호 순서(최근 limit개, 많이 고른 순) — 후보 구성에 반영.
    (2026-07-16 사용자 지시: 계속 고르면 알고리즘이 학습해 다음 후보가 더 나아져야 함.)"""
    log = PROJECT_ROOT / "data" / "vision_examples.jsonl"
    if not log.exists():
        return []
    from collections import Counter
    cnt = Counter()
    try:
        for line in log.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if line:
                s = str(json.loads(line).get("source", "")).strip().lower()
                if s:
                    # 스톡 계열은 하나로 묶어 학습(개별 스톡 API 이름 차이는 취향이 아님)
                    cnt["stock" if s in ("pexels", "pixabay", "openverse", "wikimedia") else s] += 1
    except Exception:
        return []
    return [s for s, _ in cnt.most_common()]


def _category_fallback_queries(product: dict) -> list:
    """키워드 검색이 말랐을 때 보충용 — 카테고리 일반 검색어(최소 6장 보장 top-up 라운드에서 사용)."""
    cat = str((product or {}).get("category", "")).strip()
    for key, qs in _CATEGORY_QUERIES.items():
        if key and key in cat:
            return list(qs)
    return list(_DEFAULT_QUERIES)


def fetch_candidates(product: dict, lines: list, job_dir: Path, settings: dict,
                     product_images: list | None = None, per_line: int = 6,
                     only_line: int | None = None, exclude_urls: list | None = None,
                     exclude_memes: list | None = None,
                     detail_images: list | None = None) -> list:
    """관리자 선택기용 — 라인마다 후보를 모은다. 설계(2026-07-15 사용자 개선):
    ① 라인마다 다른 검색 페이지 + 밈 로테이션으로 '라인별 차별화'(같은 이미지 반복 제거, #1)
    ② 후보의 절반 이상을 재미(밈·GIF·funny 스톡)로 구성(#2)
    ③ 상품 사진 후보는 'product 타입 라인'에만(그 외 라인엔 상품 후보 없음, #3)
    only_line 지정 시 그 라인 하나만 재생성('다시 찾기' 라인별 — 파이프라인이 병합).
    exclude_urls/exclude_memes: '다시 찾기'로 재생성할 때 직전에 보여준 이미지·밈을 제외해
    반드시 다른 후보가 나오게 한다(#다시찾기 안 바뀜 방지)."""
    plan = plan_line_visuals(product, lines, settings)
    # 원본 다운로드는 candidates/ 가 아니라 cand_raw/ 에 받는다. _publish_candidates가 정규 이름
    # ({hash}__L{i}__{j})으로 candidates/ 에 복사하고, 워크플로는 candidates/*만 릴리스에 올린다.
    # (예전엔 원본+정규가 둘 다 candidates/ 에 있어 릴리스 자산이 2배로 불어 180개 상한에서 다른 상품
    #  후보를 밀어내 썸네일이 깨지던 문제 → 원본을 분리해 업로드 자산을 절반으로 줄임.)
    out_dir = Path(job_dir) / "cand_raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    product_images = [str(p) for p in (product_images or []) if Path(p).exists()]
    base_page = random.randint(1, 6)
    giphy_only = _giphy_only(settings)
    # ⭐ 선택 학습 반영(2026-07-16): 운영자가 지금까지 실제로 고른 픽의 소스 분포로
    #    슬롯 우선순위(실사 스톡 vs GIF)와 밈 장수를 자동 조정 — 고를수록 다음 후보가 취향에 수렴.
    prefs = _source_prefs()
    stock_first = not (prefs and prefs[0] == "giphy")
    meme_n = 2
    if prefs:
        if prefs[0] == "meme":
            meme_n = 3
        elif "meme" not in prefs[:3]:
            meme_n = 1
        print(f"[imgsrc] 학습 반영: 소스 선호 {' > '.join(prefs[:4])} → "
              f"{'스톡(실사)' if stock_first else 'GIF'} 슬롯 우선 · 밈 {meme_n}장")
    # seen에 이전 URL을 미리 넣어두면 그 URL은 다시 안 뽑힌다 → '다시 찾기'가 확실히 새 이미지를 준다.
    seen = set(u for u in (exclude_urls or []) if u)
    used_memes = set(Path(m).name for m in (exclude_memes or []) if m)   # 직전 밈 basename 제외
    manifest = []
    for i, (ln, pl) in enumerate(zip(lines, plan)):
        if only_line is not None and i != int(only_line):
            continue
        text = ln.get("text", "")
        keywords = pl.get("keywords") or ([pl.get("query")] if pl.get("query") else [])
        line_page = base_page + i * 2      # 라인마다 다른 결과 창 → 라인 간 차별화(#1)
        entry = {"line_i": i, "text": text, "stage": ln.get("stage"),
                 "punch": bool(ln.get("punch")), "is_hook": bool(ln.get("is_hook")), "type": pl["type"],
                 "query": pl.get("query", ""), "keywords": keywords, "candidates": []}
        cands = entry["candidates"]
        k = 0
        # ① 상품 사진 — product 타입 라인에만(#3). prod_idx로 '어느 상품 사진'인지 보존(선택 시 그 사진 사용)
        if pl["type"] == "product":
            for pidx, p in enumerate(product_images[:3]):   # 2→3장(2026-07-17 선택폭 확대)
                cands.append({"file": p, "source": "product", "url": None,
                              "is_product": True, "prod_idx": pidx})
            # 상세컷(PDF 기능 설명 구간 크롭, 2026-07-17) — 라인마다 시작점을 돌려 다른 컷이 먼저 보이게.
            #   선택은 detail_idx로 저장 → 제작 때 harvest_detail_images가 같은 컷을 재현(load_selections).
            dpairs = list(enumerate(detail_images or []))
            if dpairs:
                start = (i * 2) % len(dpairs)
                for didx, dp in (dpairs[start:] + dpairs[:start])[:4]:
                    cands.append({"file": str(dp), "source": "detail", "url": None,
                                  "is_detail": True, "detail_idx": didx})
        # ② 재미(밈) — 로테이션(자체 제작물 = Content ID 안전, 장수는 학습이 조정). 라인 간·재생성 시 다른 밈.
        for mp in _pick_line_memes(PROJECT_ROOT, text, used_memes, meme_n):
            used_memes.add(Path(mp).name)
            cands.append({"file": str(mp), "source": "meme", "url": None,
                          "is_meme": True, "meme_rel": _meme_repo_rel(mp)})
        # ③ 라인 명사(keywords)로 검색 — 자막 단어와 '가장 근접한' 실사 스톡 + GIF(재미)를 슬롯 교대로.
        #    키워드·페이지 로테이션으로 라인마다 다르게(#1).
        for c in _keyword_urls(keywords, seen, line_page, per_line, giphy_only, stock_first):
            d = _dl_candidate(out_dir, i, k, c["url"]); k += 1
            if d:
                cands.append({"file": str(d), "source": c["source"], "url": c["url"], "keyword": c.get("keyword")})
        # ④ (mixed일 때) 재미가 절반 미만이면 밈으로 보충 — giphy_only면 이미 전부 GIF라 불필요.
        if not giphy_only:
            for _ in range(3):
                if sum(1 for c in cands if _is_funny(c)) * 2 >= len(cands) or not cands:
                    break
                more = _pick_line_memes(PROJECT_ROOT, text, used_memes, 1)
                if not more:
                    break
                for mp in more:
                    used_memes.add(Path(mp).name)
                    cands.append({"file": str(mp), "source": "meme", "url": None,
                                  "is_meme": True, "meme_rel": _meme_repo_rel(mp)})
        # ⑤ ⭐ 최소 보장(2026-07-16 사용자 지시: 라인당 무조건 6장 이상) — 부족하면 보충 라운드:
        #    1R 같은 키워드·다음 페이지 재검색 → 2R 카테고리 일반 검색어 추가 → 매 라운드 밈 1장씩.
        #    (상품 사진은 #3 규칙 유지 — product 라인 밖에는 채우지 않는다.)
        target = max(6, int(per_line))
        for r in range(1, 4):
            if len(cands) >= target:
                break
            kws = list(keywords or [])
            if r >= 2:
                kws += _category_fallback_queries(product)
            for c in _keyword_urls(kws, seen, line_page + 20 * r, target - len(cands), giphy_only, stock_first):
                d = _dl_candidate(out_dir, i, k, c["url"]); k += 1
                if d:
                    cands.append({"file": str(d), "source": c["source"], "url": c["url"], "keyword": c.get("keyword")})
        # 최후 보충: 목표에 닿을 때까지 밈으로 채운다(자체 제작물이라 항상 가용 — 같은 라인 중복만 방지,
        # 라인 간 재사용은 허용). 밈 풀 자체가 바닥나면 그때만 경고.
        line_memes = {Path(str(c.get("file", ""))).name for c in cands if c.get("is_meme")}
        while len(cands) < target:
            more = _pick_line_memes(PROJECT_ROOT, text, line_memes, 1)
            if not more:
                break
            for mp in more:
                line_memes.add(Path(mp).name)
                cands.append({"file": str(mp), "source": "meme", "url": None,
                              "is_meme": True, "meme_rel": _meme_repo_rel(mp)})
        if len(cands) < target:
            print(f"[imgsrc] ⚠️ 라인 {i} 후보 {len(cands)}장(<{target}) — 검색 키(SHORTS_GIPHY/PEXELS/"
                  f"PIXABAY_API_KEY) 등록·확인 필요")
        manifest.append(entry)
    (Path(job_dir) / "candidates.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(e["candidates"]) for e in manifest)
    funny_total = sum(1 for e in manifest for c in e["candidates"] if _is_funny(c))
    tag = f"(라인 {only_line}만)" if only_line is not None else ""
    mode = "Giphy-only(GIF만)" if giphy_only else "Giphy우선+스톡"
    warn = "" if _giphy_key() else " · ⚠️ Giphy 키 없음 → 후보 급감(SHORTS_GIPHY_API_KEY 등록 필요)"
    print(f"[imgsrc] 후보 생성{tag}: {len(manifest)}라인 · 총 {total}장 (재미 {funny_total}장, 소스={mode}){warn}")
    return manifest


def load_selections(row_hash: str, lines: list, project_root: Path, job_dir: Path,
                    product_images: list | None = None,
                    product_videos: list | None = None) -> list | None:
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
    prod_paths = [Path(p) for p in (product_images or []) if Path(p).exists()]
    prod0 = prod_paths[0] if prod_paths else None
    # 제품 영상 픽(pv_name=릴리스 자산명) 해석용 — 이미 내려받은 로컬본 매핑(없으면 픽 처리 때 개별 확보)
    pv_map = {Path(p).name: Path(p) for p in (product_videos or []) if Path(p).exists()}
    by_line = {int(x.get("line_i", -1)): x for x in (data.get("lines") or [])}
    dl_dir = Path(job_dir) / "selected"
    dl_dir.mkdir(parents=True, exist_ok=True)
    line_images, used, dropped = [], 0, 0
    detail_cache = None   # 상세컷 픽(detail_idx) 재추출 캐시 — 첫 픽에서 1회만 PDF에서 수확
    for i in range(len(lines)):
        entry = by_line.get(i)
        if not entry:
            line_images.append([])
            continue
        picks = entry.get("picks")
        if not isinstance(picks, list):    # 구형 단일 포맷(entry 자체가 픽) 하위호환
            picks = [entry]
        imgs = []
        prod_seen = 0   # 이 라인에서 지금까지 고른 상품사진 수(구형 선택 prod_idx 없을 때 등장순서로 매김)
        for j, pk in enumerate(picks):
            pv = pk.get("pv_name")
            if pv:                          # 제품 영상 픽 — 그 라인 구간에서 영상 재생(렌더가 mp4/mov 지원)
                loc = pv_map.get(pv)
                if loc is None:             # 이번 실행에 안 내려받은 자산이면 그 자산만 개별 확보
                    try:
                        from src.product.assets import fetch_product_videos
                        got = fetch_product_videos(row_hash, dl_dir, prefix=pv, max_n=1)
                        loc = Path(got[0]) if got else None
                        if loc:
                            pv_map[pv] = loc
                    except Exception as e:
                        print(f"[imgsrc] 제품영상 픽 확보 실패({pv}: {e}) — 건너뜀")
                if loc:
                    s0 = pk.get("pv_start")
                    if s0 is not None:   # ⭐ 특징 구간 픽(2026-07-17) — 고른 구간만 잘라 그 라인에서 재생
                        e0 = float(pk.get("pv_end") or 0) or (float(s0) + 8.0)
                        cut = dl_dir / f"pvseg_{i:02d}_{j}_{int(float(s0) * 10)}.mp4"
                        if not cut.exists():
                            try:
                                import subprocess
                                import imageio_ffmpeg
                                ff = imageio_ffmpeg.get_ffmpeg_exe()
                                subprocess.run([ff, "-y", "-ss", f"{float(s0):.2f}", "-i", str(loc),
                                                "-t", f"{max(0.8, e0 - float(s0)):.2f}", "-an",
                                                "-c:v", "libx264", "-preset", "veryfast", str(cut)],
                                               check=True, capture_output=True)
                            except Exception as ex:
                                print(f"[imgsrc] 구간 자르기 실패({type(ex).__name__}) — 전체 영상 사용")
                                cut = None
                        if cut is not None and Path(cut).exists():
                            print(f"[imgsrc] 라인{i + 1}: 제품영상 {float(s0):.1f}~{e0:.1f}초 구간 사용")
                            loc = Path(cut)
                    imgs.append(loc); used += 1
                continue
            if pk.get("detail_idx") is not None:   # 상세컷 픽(2026-07-17) — PDF에서 같은 컷을 재추출(결정론)
                if detail_cache is None:
                    try:
                        from src.product.enrich import harvest_detail_images
                        detail_cache = harvest_detail_images(row_hash, Path(job_dir) / "detail_sel")
                    except Exception as e:
                        print(f"[imgsrc] 상세컷 재추출 실패({type(e).__name__}: {e})")
                        detail_cache = []
                di = int(pk.get("detail_idx") or 0)
                if 0 <= di < len(detail_cache):
                    imgs.append(detail_cache[di]); used += 1
                else:
                    print(f"[imgsrc] 상세컷 {di}번 없음(추출 {len(detail_cache)}장) — 건너뜀")
                    dropped += 1
                continue
            f = pk.get("file")
            if f and Path(f).exists():      # 저장소에 커밋된 파일(업로드본·밈 등)
                imgs.append(Path(f)); used += 1; continue
            url = pk.get("url")
            if url:
                ext = ".gif" if url.lower().split("?")[0].endswith(".gif") else ".jpg"
                dest = dl_dir / f"sel_{i:02d}_{j}{ext}"
                # 운영자가 직접 고른 픽: 크기 필터 없음(작은 GIF도 존중) + 2회 재시도 + 실패 로그
                if _download_image(url, dest, min_side=0, tries=2, tag=f"라인{i + 1} 선택 픽"):
                    imgs.append(dest); used += 1; continue
                dropped += 1
                continue
            if pk.get("is_product") and prod_paths:   # 상품을 고른 라인에만 상품 사진
                # #3: '고른 그 상품 사진'을 쓴다(여러 장 골라도 반복되지 않게).
                #   prod_idx가 있으면 그걸, 없으면(구형 선택) 등장 순서(prod_seen)로 상품1·상품2…를 배정.
                pidx = pk.get("prod_idx")
                pidx = prod_seen if pidx is None else int(pidx or 0)
                prod_seen += 1
                imgs.append(prod_paths[pidx] if 0 <= pidx < len(prod_paths) else prod0)
                used += 1
        line_images.append(imgs)
    sel_lines = sum(1 for x in line_images if x)
    print(f"[imgsrc] 운영자 선택 적용: {sel_lines}/{len(lines)}라인 · 이미지 {used}장"
          + (f" · ⚠️ 실패 {dropped}장(위 로그 확인)" if dropped else "")
          + f" (data/selections/{row_hash}.json · 미선택 라인은 브랜드 패널)")
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


# Giphy 호출 절약(2026-07-16 — 베타 키 시간당 100회 한도 초과 사고 재발 방지):
#   예전엔 호출 1번(HTTP)당 8개를 받아 1개만 쓰고 버려서 후보 생성 1회에 수십 콜을 썼다.
#   이제 쿼리당 한 번에 25개를 받아 풀(pool)에 쌓아 재사용 → 같은 결과 기준 HTTP 호출 ~90% 감소.
#   429(한도 초과)를 만나면 이번 실행은 Giphy를 끄고 스톡·밈으로만 진행(경고 1회).
_GIPHY_POOL: dict = {}      # query → 남은 URL 목록
_GIPHY_FETCHES: dict = {}   # query → HTTP 페치 횟수(다음 offset)
_GIPHY_OFF = {"blocked": False}


def _giphy(query: str, seen: set, page: int = 1):
    """재미있는 반응 움짤(GIF). 렌더가 정사각형에 애니메이션으로 깐다(더 코믹·자주 바뀜).
    (page 인자는 소스 체인 시그니처 호환용 — 페이징은 내부 페치 횟수로 관리한다.)"""
    gk = _giphy_key()
    if not gk or _GIPHY_OFF["blocked"]:
        return None
    pool = _GIPHY_POOL.setdefault(query, [])
    for _ in range(4):   # (풀 소진 → 페치) 반복 상한
        while pool:
            u = pool.pop(0)
            if u not in seen:
                seen.add(u)
                return u
        n = _GIPHY_FETCHES.get(query, 0)
        if n >= 3:       # 쿼리당 최대 3페치(75개) — 그 이상은 결과 질이 떨어질 뿐
            return None
        _GIPHY_FETCHES[query] = n + 1
        r = requests.get(GIPHY, params={"api_key": gk, "q": query, "limit": 25,
                                        "offset": n * 25, "rating": "pg-13", "lang": "en"}, timeout=25)
        if r.status_code == 429:
            _GIPHY_OFF["blocked"] = True
            print("[imgsrc] ⚠️ Giphy 시간당 호출 한도 초과(429) — 이번 실행은 스톡·밈으로만 진행 "
                  "(해결: Giphy 개발자 대시보드에서 무료 Production 키 신청)")
            return None
        if not r.ok:
            return None
        data = r.json().get("data", [])
        if not data:
            _GIPHY_FETCHES[query] = 99   # 결과 없는 쿼리 — 재페치 금지
            return None
        for it in data:
            imgs = it.get("images") or {}
            u = ((imgs.get("downsized_medium") or {}).get("url")
                 or (imgs.get("original") or {}).get("url"))
            if u:
                pool.append(u)
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


def _download_image(url: str, dest: Path, min_side: int = 300, tries: int = 1, tag: str = "") -> bool:
    """이미지 다운로드 + 검증(PIL open). 실패 시 False.
    min_side: 자동 소싱 후보엔 300px 하한(저화질 걸러냄). ⚠️ 운영자가 직접 고른 픽에는 0을 줘라 —
      Giphy 원본 GIF는 300px 미만이 많아 이 필터가 '고른 이미지 소리 없이 탈락'의 주범이었다(2026-07-16).
    tries: 재시도 횟수(운영자 픽은 2회). tag가 있으면 실패를 로그로 남긴다(무음 탈락 금지)."""
    last = ""
    for attempt in range(max(1, tries)):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if not r.ok or not r.content:
                last = f"HTTP {r.status_code}"
                continue
            dest.write_bytes(r.content)
            from PIL import Image
            with Image.open(dest) as im:
                im.verify()
            if min_side:
                with Image.open(dest) as im:
                    if min(im.size) < min_side:
                        dest.unlink(missing_ok=True)
                        last = f"크기 미달({im.size})"
                        break   # 크기는 재시도해도 같다
            return True
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:60]}"
            dest.unlink(missing_ok=True)
    if tag:
        print(f"[imgsrc] ⚠️ 다운로드 실패({tag}): {last} — {url[:90]}")
    return False
