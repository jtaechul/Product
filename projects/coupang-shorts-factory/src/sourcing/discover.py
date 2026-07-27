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
from src.sourcing.translate import expand_zh_terms, identify_by_image, match_naver_by_image

DISCOVER_DIR = SOURCES_DIR / "discover"


def _candidate(sv: SourceVideo) -> dict:
    """관리자 추천 카드가 쓰는 표시용 dict."""
    return {"id": sv.id, "platform": sv.platform, "title": sv.title,
            "title_ko": sv.title_ko, "coupang_keywords": list(sv.coupang_keywords or []),
            "zh_terms": list(sv.zh_terms or []),
            "naver": dict(sv.naver or {}),
            "view_count": sv.view_count, "uploader": sv.uploader,
            "duration": sv.duration, "source_url": sv.source_url,
            "download_url": sv.download_url, "cover": sv.cover}


def _merge_naver(svs_info: list) -> dict:
    """여러 검색어 결과(find_coupang dict들)를 병합 — 후보를 대량 확보(진짜 상품이 들 확률↑, 2026-07-26).
    첫 결과 기준 real_title, 후보는 제목으로 dedup 병합, 쿠팡 판매는 어느 검색에서든 잡히면 채택."""
    infos = [i for i in svs_info if i]
    if not infos:
        return {}
    merged = dict(infos[0])
    cands, have = [], set()
    for info in infos:
        for c in (info.get("candidates") or []):
            key = (c.get("title") or "").strip()
            if key and key not in have:
                have.add(key)
                cands.append(c)
        if not merged.get("coupang") and info.get("coupang"):   # 쿠팡 판매 보강
            for k in ("coupang", "coupang_title", "coupang_lprice", "mall", "image"):
                merged[k] = info.get(k)
    cands.sort(key=lambda c: 0 if c.get("coupang") else 1)   # 쿠팡 항목 앞으로
    merged["candidates"] = cands[:10]
    return merged


def enrich_naver(svs: list, finder=find_coupang, matcher=match_naver_by_image) -> None:
    """후보마다 네이버 쇼핑으로 '진짜 상품명 + 쿠팡 판매 여부' 부착(키 없으면 조용히 스킵).
    ⭐ 여러 쿠팡 검색어로 검색·병합해 후보를 대량 확보(2026-07-26 사용자 확정 — 진짜 상품 일치도↑).
    finder(단일 검색어)/matcher 주입 가능(테스트).

    ⭐ 비전 자동 대조(사용자 아이디어): 네이버 후보 이미지들을 틱톡 썸네일과 비교해 '같은 상품'을
    자동 선택(best_match)하고 확신도(match_confidence)를 붙인다 — 운영자의 ② 기본선택 보조."""
    for s in svs:
        queries = [q for q in (s.coupang_keywords or [])[:3] if q] or [s.title_ko or s.title]
        queries = [q for q in queries if q]
        if not queries:
            continue
        results = []
        for q in queries:
            try:
                results.append(finder(q))
            except Exception as e:
                print(f"[discover] 네이버 확인 실패({q}): {e}")
        info = _merge_naver(results)
        if info:
            cands = info.get("candidates") or []
            if cands and s.cover:
                try:
                    m = matcher(s.cover, cands)
                    info["best_match"] = m.get("best", 0)
                    info["match_confidence"] = m.get("confidence", "unknown")
                    if m.get("reason"):
                        info["match_reason"] = m["reason"]
                except Exception as e:
                    print(f"[discover] 이미지 대조 실패: {e}")
            s.naver = info


def discover(keyword: str, limit: int = 10, adapter: TikwmAdapter | None = None,
             terms: list | None = None, cursor: int = 0, exclude: list | None = None) -> tuple:
    """한국어 키워드 → (중국어로 확장) → 여러 검색어로 틱톡 검색(커서 페이지네이션) → 병합·조회수 정렬.

    반환 (svs, next_cursor). ⭐ 새로고침이 '진짜 새 영상'을 받도록 tikwm 커서를 넘긴다(2026-07-26 개선:
    이전엔 cursor 고정이라 늘 같은 상위 풀 → 새로고침해도 그대로였음). exclude(이미 본 source_url)는
    제외. 한국어 설명·쿠팡 검색어·네이버 확인은 반환 슬라이스에만 적용. terms/adapter 주입 가능(테스트)."""
    ad = adapter or TikwmAdapter()
    terms = terms if terms is not None else expand_zh_terms(keyword)
    seen = set(exclude or [])
    fetch = limit * 3 + 10   # exclude 후에도 limit 확보하도록 넉넉히
    pool, next_cursor = {}, 0   # source_url|id → SourceVideo(최고 조회수 유지)
    for t in terms:
        try:
            svs_t, nxt, _more = ad.search_page(Seed(kind="keyword", value=t), limit=fetch, cursor=cursor)
        except Exception as e:
            print(f"[discover] 검색 실패({t}): {e}")
            svs_t, nxt = [], 0
        next_cursor = max(next_cursor, int(nxt or 0))
        for sv in svs_t:
            if sv.source_url and sv.source_url in seen:   # 이미 본 영상 제외
                continue
            k = sv.source_url or sv.id
            cur = pool.get(k)
            if cur is None or (sv.view_count or 0) > (cur.view_count or 0):
                pool[k] = sv
    ordered = sorted(pool.values(), key=lambda s: (s.view_count or 0), reverse=True)
    svs = ordered[:limit]
    # ⭐ 상품 식별을 '제목 텍스트 추측'이 아니라 '썸네일 이미지'로 한다(2026-07-26 오매칭 개선):
    #   비전이 실제 상품을 보고 정확한 쿠팡 검색어(ko) + 같은상품 중국어어(zh, ③용)를 준다.
    meta = identify_by_image([{"title": s.title or "", "cover": s.cover or ""} for s in svs])
    for s, m in zip(svs, meta):
        s.title_ko = m["ko"]
        s.coupang_keywords = m["keywords"]
        s.zh_terms = m.get("zh") or []
    enrich_naver(svs)   # 네이버 쇼핑으로 진짜 상품명 + 쿠팡 판매 여부(키 없으면 스킵)
    return svs, next_cursor


def discover_url(url: str, adapter: TikwmAdapter | None = None) -> list:
    """틱톡 URL 하나 → 그 영상만 소스 후보로(키워드 검색 대신 · 2026-07-27 사용자 요청).
    tikwm로 URL을 해석해 영상 1건을 받고, 키워드 발굴과 동일한 후처리(비전 식별→쿠팡 검색어→네이버 확인)를 적용."""
    ad = adapter or TikwmAdapter()
    try:
        svs, _n, _m = ad.search_page(Seed(kind="url", value=url), limit=1)
    except Exception as e:
        print(f"[discover] URL 해석 실패({url}): {e}")
        return []
    svs = [s for s in (svs or []) if s.source_url or s.download_url][:1]
    if svs:
        meta = identify_by_image([{"title": s.title or "", "cover": s.cover or ""} for s in svs])
        for s, m in zip(svs, meta):
            s.title_ko = m["ko"]
            s.coupang_keywords = m["keywords"]
            s.zh_terms = m.get("zh") or []
        enrich_naver(svs)
    return svs


def build_manifest(keyword: str, row_hash: str, svs: list, terms: list | None = None,
                   page: int = 0, nonce: str = "", next_cursor: int = 0) -> dict:
    return {"keyword": keyword, "hash": row_hash, "source": "tiktok_tikwm",
            "search_terms": terms or [], "page": int(page or 0), "nonce": str(nonce or ""),
            "next_cursor": int(next_cursor or 0),   # 새로고침이 이걸 넘겨 tikwm 다음 페이지를 받는다
            "count": len(svs), "candidates": [_candidate(s) for s in svs]}


def write_manifest(row_hash: str, manifest: dict, base_dir: Path | None = None) -> Path:
    d = base_dir or DISCOVER_DIR
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{row_hash}.json"
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="틱톡 발굴 — 키워드로 추천 후보 뽑기(또는 --url로 그 영상 하나)")
    ap.add_argument("--keyword", default="", help="틱톡 검색 키워드(--url을 주면 라벨로만 쓰임)")
    ap.add_argument("--url", default="", help="틱톡 URL(주면 키워드 검색 대신 이 영상 하나만 소스 후보로)")
    ap.add_argument("--hash", default="manual")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--page", type=int, default=0, help="새로고침 배치 라벨(0=상위, 1=다음…) — 실제 페이지는 --cursor")
    ap.add_argument("--cursor", type=int, default=0, help="tikwm 커서(새로고침 시 이전 next_cursor를 넘겨 진짜 다음 영상)")
    ap.add_argument("--exclude", default="", help="쉼표구분 source_url(이미 본 영상 제외)")
    ap.add_argument("--nonce", default="", help="폴링 신선도 매칭용(관리자가 넘김)")
    ap.add_argument("--terms", default="", help="쉼표구분 검색어(주면 한국어→중국어 확장 생략 — ③ 홍보영상: 확정 상품의 중국어어로 직접 검색)")
    a = ap.parse_args(argv)

    # ⭐ 틱톡 URL 붙여넣기(2026-07-27): 키워드 검색 대신 그 URL의 영상 하나만 소스 후보로 가져온다.
    if (a.url or "").strip():
        svs = discover_url(a.url.strip())
        manifest = build_manifest(a.url.strip(), a.hash, svs, terms=[], page=0, nonce=a.nonce, next_cursor=0)
        p = write_manifest(a.hash, manifest)
        print(f"[discover] URL 발굴='{a.url.strip()}' → 후보 {len(svs)}개: {p}")
        if not svs:
            print("[discover] 경고: URL에서 영상을 못 받음(잘못된 URL/차단) — 관리자에서 다시 시도 안내.")
        return 0

    if not (a.keyword or "").strip():
        print("[discover] 오류: --keyword 또는 --url 중 하나가 필요합니다.")
        return 2
    given = [t.strip() for t in (a.terms or "").split(",") if t.strip()]
    exclude = [u.strip() for u in (a.exclude or "").split(",") if u.strip()]
    # --terms 주면 그걸 그대로(왕복 번역 없이) — ③ 홍보영상은 ①에서 비전 식별한 '같은 상품' 중국어어로 검색.
    terms = given or expand_zh_terms(a.keyword)   # 한국어 → 중국어 검색어(매니페스트에도 기록)
    svs, next_cursor = discover(a.keyword, limit=a.limit, terms=terms, cursor=a.cursor, exclude=exclude)
    manifest = build_manifest(a.keyword, a.hash, svs, terms=terms, page=a.page, nonce=a.nonce, next_cursor=next_cursor)
    p = write_manifest(a.hash, manifest)
    print(f"[discover] 키워드='{a.keyword}' · 배치={a.page} · cursor={a.cursor}→{next_cursor} · 제외 {len(exclude)}건 → 검색어={terms} → 후보 {len(svs)}개: {p}")
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
