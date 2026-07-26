"""틱톡 발굴 파이프라인 (SSOT §6 · 2026-07-26 사용자 확정 방향).

키워드로 틱톡 쇼핑 쇼츠를 검색해 **조회수 상위 5~10개**를 '추천 후보'로 뽑아
data/sources/discover/{hash}.json 매니페스트에 저장한다(관리자 추천 카드가 읽는다).

실행(주로 GitHub Actions — 러너에서 tikwm 검색이 됨):
    python -m src.sourcing.discover --keyword "꿀템" --hash <row_hash> --limit 10
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.sourcing.base import Seed
from src.sourcing.models import SOURCES_DIR, SourceVideo
from src.sourcing.naver_shop import find_coupang
from src.sourcing.tiktok_tikwm import TikwmAdapter
from src.sourcing.translate import describe_and_keywords_ko, expand_zh_terms

DISCOVER_DIR = SOURCES_DIR / "discover"


def _candidate(sv: SourceVideo) -> dict:
    """관리자 추천 카드가 쓰는 표시용 dict."""
    return {"id": sv.id, "platform": sv.platform, "title": sv.title,
            "title_ko": sv.title_ko, "coupang_keywords": list(sv.coupang_keywords or []),
            "naver": dict(sv.naver or {}),
            "view_count": sv.view_count, "uploader": sv.uploader,
            "duration": sv.duration, "source_url": sv.source_url,
            "download_url": sv.download_url, "cover": sv.cover}


def enrich_naver(svs: list, finder=find_coupang) -> None:
    """후보마다 네이버 쇼핑으로 '진짜 상품명 + 쿠팡 판매 여부' 부착(키 없으면 조용히 스킵).
    검색어는 후보의 첫 쿠팡 검색어(없으면 한국어 설명)를 쓴다. finder 주입 가능(테스트)."""
    for s in svs:
        q = (s.coupang_keywords[0] if s.coupang_keywords else None) or s.title_ko or s.title
        if not q:
            continue
        try:
            info = finder(q)
        except Exception as e:
            print(f"[discover] 네이버 확인 실패: {e}")
            info = {}
        if info:
            s.naver = info


def discover(keyword: str, limit: int = 10, adapter: TikwmAdapter | None = None,
             terms: list | None = None) -> list:
    """한국어 키워드 → (중국어로 확장) → 여러 검색어로 틱톡 검색 → 병합·조회수 상위 → 한국어 설명 번역.
    terms 주입 시 그 검색어들을 쓴다(없으면 keyword를 중국어로 확장). adapter/terms 주입 가능(테스트)."""
    ad = adapter or TikwmAdapter()
    terms = terms if terms is not None else expand_zh_terms(keyword)
    pool = {}   # source_url|id → SourceVideo(최고 조회수 유지)
    for t in terms:
        for sv in ad.search(Seed(kind="keyword", value=t), limit=max(limit, 15)):
            k = sv.source_url or sv.id
            cur = pool.get(k)
            if cur is None or (sv.view_count or 0) > (cur.view_count or 0):
                pool[k] = sv
    svs = sorted(pool.values(), key=lambda s: (s.view_count or 0), reverse=True)[:limit]
    meta = describe_and_keywords_ko([s.title or "" for s in svs])   # 카드용 한국어 설명 + 쿠팡 검색어
    for s, m in zip(svs, meta):
        s.title_ko = m["ko"]
        s.coupang_keywords = m["keywords"]
    enrich_naver(svs)   # 네이버 쇼핑으로 진짜 상품명 + 쿠팡 판매 여부(키 없으면 스킵)
    return svs


def build_manifest(keyword: str, row_hash: str, svs: list, terms: list | None = None) -> dict:
    return {"keyword": keyword, "hash": row_hash, "source": "tiktok_tikwm",
            "search_terms": terms or [], "count": len(svs),
            "candidates": [_candidate(s) for s in svs]}


def write_manifest(row_hash: str, manifest: dict, base_dir: Path | None = None) -> Path:
    d = base_dir or DISCOVER_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{row_hash}.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="틱톡 발굴 — 키워드로 추천 후보 뽑기")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--hash", default="manual")
    ap.add_argument("--limit", type=int, default=10)
    a = ap.parse_args(argv)

    terms = expand_zh_terms(a.keyword)   # 한국어 → 중국어 검색어(매니페스트에도 기록)
    svs = discover(a.keyword, limit=a.limit, terms=terms)
    manifest = build_manifest(a.keyword, a.hash, svs, terms=terms)
    p = write_manifest(a.hash, manifest)
    print(f"[discover] 키워드='{a.keyword}' → 검색어(중국어확장)={terms} → 후보 {len(svs)}개 저장: {p}")
    for i, c in enumerate(manifest["candidates"], 1):
        kws = " / ".join(c.get("coupang_keywords") or []) or "(검색어 없음)"
        nv = c.get("naver") or {}
        print(f"  {i}. 조회 {(c['view_count'] or 0):>10,} · {str(c.get('title_ko') or c['title'])[:40]} · @{c['uploader']}")
        print(f"      쿠팡 검색어: {kws}")
        if nv:
            mark = "쿠팡판매 O" if nv.get("coupang") else "쿠팡판매 미확인"
            print(f"      네이버: {str(nv.get('coupang_title') or nv.get('real_title'))[:44]} · {mark}")
    if not svs:
        print("[discover] 경고: 후보 0개 (tikwm 응답 없음/차단) — 관리자에서 재시도/다른 키워드 안내.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
