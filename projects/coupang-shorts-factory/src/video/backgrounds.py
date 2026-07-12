"""상품 연관 배경 영상 — Pexels Videos API 런타임 검색 (잡 단위).

스펙 §3.2 화이트리스트 준수: Pexels(무료 라이선스) 세로 영상만 사용하고,
출처(영상 페이지 URL·촬영자)를 잡 폴더의 bg_source.json에 기록한다.
검색어는 M3 대본 생성 시 Claude가 상품에 맞춰 함께 뽑은 영어 키워드(bg_keywords).
키가 없거나 검색·다운로드에 실패하면 None을 반환해 기존 배경
(커밋된 CC0 영상 → 자체 생성 그라데이션)으로 폴백한다 — 제작을 막지 않는다.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

SEARCH_URL = "https://api.pexels.com/videos/search"


def fetch_product_bg(keywords, dest_dir: Path, min_height: int = 1080) -> Path | None:
    key = os.environ.get("SHORTS_PEXELS_API_KEY", "").strip()
    query = _clean_query(keywords)
    if not key or not query:
        return None
    try:
        import requests
        r = requests.get(SEARCH_URL,
                         params={"query": query, "orientation": "portrait", "per_page": 5},
                         headers={"Authorization": key}, timeout=30)
        r.raise_for_status()
        picked = _pick_file(r.json().get("videos") or [], min_height)
        if not picked:
            print(f"[bg] Pexels 검색 결과 없음(query='{query}') → 기본 배경 사용")
            return None
        file_url, video = picked
        out = dest_dir / "bg_product.mp4"
        with requests.get(file_url, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            with out.open("wb") as f:
                for chunk in resp.iter_content(1 << 20):
                    f.write(chunk)
        (dest_dir / "bg_source.json").write_text(json.dumps({
            "provider": "pexels", "query": query,
            "video_url": video.get("url"),
            "photographer": (video.get("user") or {}).get("name"),
            "license": "Pexels License (free to use)",
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[bg] 상품 연관 배경 확보: '{query}' → {video.get('url')}")
        return out
    except Exception as e:
        print(f"[bg] 경고: 연관 배경 검색 실패({e}) → 기본 배경으로 폴백")
        return None


def _clean_query(keywords) -> str:
    """모델 출력 키워드를 영문/숫자/공백만 남겨 안전한 검색어로 정리."""
    if isinstance(keywords, str):
        keywords = [keywords]
    text = " ".join(str(k) for k in (keywords or []))
    text = re.sub(r"[^A-Za-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:60]
    return text if len(text) >= 3 else ""


def _pick_file(videos: list, min_height: int):
    """세로(w<h)·최소 해상도 충족 mp4 중 1920 높이에 가장 가까운 파일 선택."""
    best, best_score = None, None
    for v in videos:
        for f in v.get("video_files", []):
            w, h = f.get("width") or 0, f.get("height") or 0
            if h < min_height or w >= h or "mp4" not in (f.get("file_type") or ""):
                continue
            score = abs(h - 1920)
            if best_score is None or score < best_score:
                best, best_score = (f.get("link"), v), score
    return best
