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
from src.sourcing.tiktok_tikwm import TikwmAdapter

DISCOVER_DIR = SOURCES_DIR / "discover"


def _candidate(sv: SourceVideo) -> dict:
    """관리자 추천 카드가 쓰는 표시용 dict."""
    return {"id": sv.id, "platform": sv.platform, "title": sv.title,
            "view_count": sv.view_count, "uploader": sv.uploader,
            "duration": sv.duration, "source_url": sv.source_url,
            "download_url": sv.download_url, "cover": sv.cover}


def discover(keyword: str, limit: int = 10, adapter: TikwmAdapter | None = None) -> list:
    """키워드 → 틱톡 후보 SourceVideo 리스트(조회수 상위). adapter 주입 가능(테스트)."""
    ad = adapter or TikwmAdapter()
    return ad.search(Seed(kind="keyword", value=keyword), limit=limit)


def build_manifest(keyword: str, row_hash: str, svs: list) -> dict:
    return {"keyword": keyword, "hash": row_hash, "source": "tiktok_tikwm",
            "count": len(svs), "candidates": [_candidate(s) for s in svs]}


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

    svs = discover(a.keyword, limit=a.limit)
    manifest = build_manifest(a.keyword, a.hash, svs)
    p = write_manifest(a.hash, manifest)
    print(f"[discover] 키워드='{a.keyword}' → 후보 {len(svs)}개 저장: {p}")
    for i, c in enumerate(manifest["candidates"], 1):
        print(f"  {i}. 조회 {(c['view_count'] or 0):>10,} · {str(c['title'])[:42]} · @{c['uploader']}")
    if not svs:
        print("[discover] 경고: 후보 0개 (tikwm 응답 없음/차단) — 관리자에서 재시도/다른 키워드 안내.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
