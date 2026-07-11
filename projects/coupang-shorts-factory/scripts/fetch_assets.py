"""배경 에셋 확보 (선택 단계) — CI 러너에서 실행.

우선순위:
  1) assets/backgrounds/ 에 이미 영상이 있으면 그대로 사용 (수동 배치분)
  2) SHORTS_PEXELS_API_KEY 가 있으면 Pexels 공식 API로 세로(portrait) CC0급 영상 다운로드
     (스크래핑 금지 원칙 §2 — 반드시 공식 API만 사용)
  3) 둘 다 없으면 통과 — 렌더러가 자체 생성 그라데이션 배경으로 폴백 (§3.2 자체 생성물)

이 스크립트는 실패해도 파이프라인을 막지 않는다 (항상 exit 0).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BG_DIR = PROJECT_ROOT / "assets" / "backgrounds"
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}


def main() -> int:
    BG_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p.name for p in sorted(BG_DIR.glob("*")) if p.suffix.lower() in VIDEO_EXTS]
    if existing:
        print(f"[assets] 배경 영상 {len(existing)}개 확보됨: {existing}")
        return 0

    api_key = os.environ.get("SHORTS_PEXELS_API_KEY", "").strip()
    if not api_key:
        print("[assets] 배경 영상 없음 + SHORTS_PEXELS_API_KEY 미등록 → "
              "자체 생성 그라데이션 배경으로 렌더합니다 (README의 배경 확보 안내 참고)")
        return 0

    try:
        import yaml
        settings = yaml.safe_load(
            (PROJECT_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
        query = settings.get("assets", {}).get("pexels_query", "night city lights")
        count = int(settings.get("assets", {}).get("pexels_count", 2))

        resp = requests.get(
            "https://api.pexels.com/videos/search",
            params={"query": query, "orientation": "portrait", "per_page": 10},
            headers={"Authorization": api_key}, timeout=60)
        resp.raise_for_status()
        videos = resp.json().get("videos", [])

        picked = 0
        for v in videos:
            if picked >= count:
                break
            files = [f for f in v.get("video_files", [])
                     if f.get("file_type") == "video/mp4"
                     and (f.get("height") or 0) >= 1080 and (f.get("width") or 0) >= 600
                     and (f.get("height") or 0) > (f.get("width") or 0)]
            if not files:
                continue
            best = min(files, key=lambda f: abs((f.get("height") or 0) - 1920))
            dest = BG_DIR / f"pexels_{v['id']}_{best['width']}x{best['height']}.mp4"
            print(f"[assets] 다운로드: {v.get('url')} → {dest.name}")
            with requests.get(best["link"], stream=True, timeout=300) as dl:
                dl.raise_for_status()
                with open(dest, "wb") as fh:
                    for chunk in dl.iter_content(1 << 20):
                        fh.write(chunk)
            print(f"[assets] 라이선스 기록용 → Pexels License, 출처: {v.get('url')}")
            picked += 1
        if picked == 0:
            print("[assets] 조건에 맞는 세로 영상을 찾지 못함 → 그라데이션 폴백")
    except Exception as e:  # 배경 확보 실패는 치명적이지 않음
        print(f"[assets] 경고: 배경 확보 실패({e}) → 그라데이션 폴백으로 진행")
    return 0


if __name__ == "__main__":
    sys.exit(main())
