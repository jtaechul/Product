"""운영자가 관리자 페이지에서 업로드한 '제품 영상' 확보 (Task: 관리자 제품 비주얼).

경로: 관리자 페이지(브라우저, 사용자 PAT) → GitHub Release `product-assets` 자산
  {row_hash}_{업로드시각}.mp4|mov → 파이프라인이 상품 해시로 매칭해 내려받아
  렌더의 hero_videos(상품 구간 풀프레임 배경)로 사용한다.

- 목록 조회(api.github.com)는 CI 러너가 IP를 공유해 무인증 레이트리밋(60/h)에 걸릴 수
  있으므로 GH_TOKEN/GITHUB_TOKEN이 있으면 사용한다.
- 자산 다운로드는 공개 저장소 CDN(browser_download_url)이라 무인증으로도 된다.
- 어떤 실패도 제작을 막지 않는다 — 경고 후 빈 목록(사진 히어로 폴백).
"""

from __future__ import annotations

import os
from pathlib import Path

import requests

REPO = "jtaechul/Product"
TAG = "product-assets"
MAX_VIDEOS = 3          # 씬 변주에 충분 + 다운로드 시간 상한
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm")  # iPad 화면 녹화는 .mov일 수 있음


def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "shorts-factory"}
    tok = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    if tok:
        h["Authorization"] = "Bearer " + tok
    return h


def fetch_product_videos(row_hash: str, dest_dir: Path, repo: str = REPO, tag: str = TAG,
                         prefix: str | None = None, max_n: int = MAX_VIDEOS) -> list:
    """row_hash 상품의 업로드 영상 경로 목록을 반환(최신 max_n개). 실패 시 []."""
    prefix = f"{row_hash}_" if prefix is None else prefix
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
                         headers=_headers(), timeout=30)
        if r.status_code == 404:
            return []  # 아직 아무 영상도 업로드 안 됨 — 정상
        r.raise_for_status()
        assets = r.json().get("assets") or []
    except Exception as e:
        print(f"[assets] 경고: 제품 영상 목록 조회 실패({e}) — 사진으로 진행")
        return []

    picks = sorted(
        [a for a in assets
         if str(a.get("name", "")).startswith(prefix)
         and str(a.get("name", "")).lower().endswith(VIDEO_EXTS)],
        key=lambda a: str(a.get("created_at", "")), reverse=True,
    )[:max_n]
    if not picks:
        return []

    out_dir = Path(dest_dir) / "product_videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for a in picks:
        try:
            with requests.get(a["browser_download_url"], timeout=300, stream=True) as resp:
                resp.raise_for_status()
                fp = out_dir / str(a["name"])
                with fp.open("wb") as f:
                    for chunk in resp.iter_content(1 << 20):
                        f.write(chunk)
            out.append(str(fp))
        except Exception as e:
            print(f"[assets] 경고: 제품 영상 다운로드 실패({a.get('name')}: {e}) — 건너뜀")
    if out:
        print(f"[assets] 운영자 업로드 제품 영상 {len(out)}개 확보: {[Path(p).name for p in out]}")
    return out
