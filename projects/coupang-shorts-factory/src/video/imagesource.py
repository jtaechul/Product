"""문구 매칭 이미지 소싱 — 문제/훅 씬을 '문구에 맞는 실사 이미지'로 채워 빈 화면을 없앤다.

설계(2026-07-13 사용자 확정): 화면이 비면 안 된다. 정사각형은 항상 이미지/영상으로 꽉 차야 한다.
  ① 대본 라인 → (있으면) Claude가 영어 검색어로 변환(정확한 매칭), 없으면 카테고리 키워드 폴백
  ② 대형 무료 라이브러리에서 이미지 확보: Pexels(키 있으면) → Openverse(키 불필요, CC/PD 대량)
  ③ job_dir/scene_images/ 로 내려받아 검증(PIL open) 후 경로 반환
  ④ 어떤 실패든 안전: 못 받으면 빈 목록 반환 → 렌더가 상품 사진으로 폴백(절대 빈 화면 없음)

주의: 대형 무료 라이브러리(Pexels 무료 이용 / Openverse=CC·퍼블릭도메인)만 사용한다 —
'문구에 맞는 이미지'를 사실상 무제한 커버하면서 채널 리스크도 낮춘다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import requests

PEXELS = "https://api.pexels.com/v1/search"
OPENVERSE = "https://api.openverse.org/v1/images/"
UA = {"User-Agent": "miraemarket-shorts/1.0 (+https://youtube.com/@miraemarket)"}

# 카테고리 → 영어 컨셉 검색어(Claude 미사용/실패 시 폴백). 무관 장면 최소화용 안전값.
_CATEGORY_QUERIES = {
    "가전": ["modern home appliance", "cozy living room", "home party"],
    "주방": ["modern kitchen", "cooking at home", "kitchen counter"],
    "생활": ["tidy home", "daily life home", "minimal room"],
    "미용": ["skincare routine", "beauty cosmetics", "bathroom vanity"],
    "디지털": ["desk gadget setup", "modern technology", "workspace"],
    "가구": ["modern furniture", "interior room", "home decor"],
}
_DEFAULT_QUERIES = ["modern lifestyle", "cozy home interior", "happy young person home"]


def _anthropic_key() -> str:
    return (os.environ.get("SHORTS_ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def _pexels_key() -> str:
    return (os.environ.get("SHORTS_PEXELS_API_KEY") or "").strip()


def build_queries(product: dict, lines: list, want: int) -> list:
    """씬을 채울 영어 이미지 검색어 목록(대략 want개). Claude로 라인→영어 검색어 변환,
    실패 시 카테고리 키워드 폴백. 항상 want개 이상 반환(부족하면 폴백으로 채움)."""
    queries: list = []
    key = _anthropic_key()
    problem_texts = [str(l.get("text", "")).strip()
                     for l in (lines or []) if str(l.get("text", "")).strip()]
    if key and problem_texts:
        try:
            queries = _claude_queries(key, product, problem_texts, want)
        except Exception as e:  # 폴백으로 계속 (제작 안 멈춤)
            print(f"[imgsrc] Claude 검색어 생성 실패({type(e).__name__}: {e}) → 카테고리 폴백")
    if not queries:
        cat = str((product or {}).get("category", "")).strip()
        base = _CATEGORY_QUERIES.get(cat, list(_DEFAULT_QUERIES))
        name = str((product or {}).get("name", "")).strip()
        # 상품명에서 한글 제거한 영문/숫자 토큰이 있으면 추가(브랜드·모델 매칭)
        tok = " ".join(re.findall(r"[A-Za-z0-9]+", name)[:2])
        queries = ([f"{tok} {base[0]}"] if tok else []) + base
    # want개로 맞춤(부족하면 순환)
    out = []
    i = 0
    while len(out) < max(1, want):
        out.append(queries[i % len(queries)])
        i += 1
    return out[:max(1, want)]


def _claude_queries(key: str, product: dict, texts: list, want: int) -> list:
    """Claude(sonnet)로 한국어 라인 → 영어 스톡 검색어(2~4단어) 변환. JSON 배열 반환."""
    name = str((product or {}).get("name", "")).strip()
    cat = str((product or {}).get("category", "")).strip()
    joined = "\n".join(f"- {t}" for t in texts[:12])
    prompt = (
        "너는 한국어 쇼츠 대본의 각 장면에 어울리는 '스톡 사진 검색어'를 정하는 편집자다.\n"
        f"상품: {name} (카테고리: {cat})\n"
        "아래 각 라인의 분위기·상황에 시각적으로 어울리는 **영어** 검색어를 2~4단어로 만들어라.\n"
        "사람·감정·상황을 담되 특정 브랜드/로고/유명인은 피한다. 세로 사진에 잘 맞는 일상 장면 위주.\n"
        f"라인:\n{joined}\n\n"
        f'출력: JSON만. {{"queries": ["...", "..."]}} 형태로 정확히 {want}개.'
    )
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json={"model": "claude-sonnet-4-6", "max_tokens": 500,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=40,
    )
    r.raise_for_status()
    txt = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", txt, re.S)
    data = json.loads(m.group(0) if m else txt)
    qs = [str(q).strip() for q in (data.get("queries") or []) if str(q).strip()]
    return qs


def fetch_scene_images(product: dict, lines: list, job_dir: Path, settings: dict,
                       want: int = 5) -> list:
    """문제/훅 씬용 이미지 want개를 확보해 job_dir/scene_images/에 저장, 경로 목록 반환.
    Pexels(키 있으면) 우선, 없으면 Openverse. 실패는 조용히 건너뜀(빈 목록이면 렌더가 상품 폴백)."""
    out_dir = Path(job_dir) / "scene_images"
    out_dir.mkdir(parents=True, exist_ok=True)
    queries = build_queries(product, lines, want)
    print(f"[imgsrc] 검색어 {len(queries)}개: {queries}")
    paths: list = []
    seen: set = set()
    for i, q in enumerate(queries):
        if len(paths) >= want:
            break
        url = _search_one(q, seen)
        if not url:
            continue
        dest = out_dir / f"scene_{i:02d}.jpg"
        if _download_image(url, dest):
            paths.append(dest)
    print(f"[imgsrc] 확보한 문구 이미지 {len(paths)}/{want}장"
          + (" (없음 → 렌더가 상품 사진으로 채움)" if not paths else ""))
    return paths


def _search_one(query: str, seen: set) -> str | None:
    """검색어 1개로 이미지 URL 1개 확보(중복 회피). Pexels→Openverse 순, 실패 시 None."""
    pk = _pexels_key()
    if pk:
        try:
            r = requests.get(PEXELS, headers={"Authorization": pk},
                             params={"query": query, "per_page": 5, "orientation": "portrait"},
                             timeout=25)
            if r.ok:
                for ph in r.json().get("photos", []):
                    u = (ph.get("src") or {}).get("large") or (ph.get("src") or {}).get("portrait")
                    if u and u not in seen:
                        seen.add(u)
                        return u
        except Exception as e:
            print(f"[imgsrc] Pexels 실패({query}: {type(e).__name__})")
    try:
        r = requests.get(OPENVERSE, headers=UA,
                         params={"q": query, "page_size": 5,
                                 "license_type": "all", "mature": "false"},
                         timeout=25)
        if r.ok:
            for it in r.json().get("results", []):
                u = it.get("url") or it.get("thumbnail")
                if u and u not in seen:
                    seen.add(u)
                    return u
    except Exception as e:
        print(f"[imgsrc] Openverse 실패({query}: {type(e).__name__})")
    return None


def _download_image(url: str, dest: Path) -> bool:
    """이미지 다운로드 + 검증(PIL로 실제 열림 + 최소 크기). 실패 시 False."""
    try:
        r = requests.get(url, headers=UA, timeout=30)
        if not r.ok or not r.content:
            return False
        dest.write_bytes(r.content)
        from PIL import Image
        with Image.open(dest) as im:
            im.verify()
        with Image.open(dest) as im:
            if min(im.size) < 320:  # 너무 작으면 정사각형에서 흐려짐 → 버림
                dest.unlink(missing_ok=True)
                return False
        return True
    except Exception:
        dest.unlink(missing_ok=True)
        return False
