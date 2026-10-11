#!/usr/bin/env python3
"""실촬영 B롤(컷어웨이) — Pexels·Pixabay 무료 영상 (0원, 상업적 사용 허용, 출처 표기 불필요).

    from stock import cutaway
    cutaway("pool water ripple close up", 1.0, Path("build/cut_1.mp4"))   → 경로 또는 None

왜 쓰나 (2026-10-11 결정)
    "사진이 살짝 움직이는 영상"의 단조로움을 깨는 가장 싼 방법. 숙소 자체는 Veo 로, 물결·김·수면 같은 질감은
    실촬영으로. 사람·손은 AI 로 만들지 않는다 — 스톡에도 사람이 있는 것은 거른다(숙소 체험처럼 보이면 안 된다).

어디서 가져왔나
    jtaechul/verdict-theater 의 src/stock_video.py (검색 규격·사람 낱말 거르기·세로 맞춤) 를 줄였다.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

PEXELS_API = "https://api.pexels.com/videos/search"
PIXABAY_API = "https://pixabay.com/api/videos/"
W, H, FPS = 1080, 1920, 30
UA = "Mozilla/5.0 (stay-shorts-factory)"
PEOPLE = {"man", "men", "woman", "women", "people", "person", "boy", "girl", "child", "kids", "family", "couple",
          "crowd", "portrait", "model", "hand", "hands", "face", "feet", "legs", "swimmer", "swimming", "bikini", "body"}
# 참고 영상의 색감에 가깝게: 채도 살짝 낮추고 어둡지 않게
GRADE = "eq=saturation=0.9:contrast=1.02"


def log(*a):
    print("[stock]", *a, flush=True)


def _get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))


def _desc_pexels(v: dict) -> str:
    m = re.search(r"/video/([a-z0-9-]+?)-\d+/?$", str(v.get("url") or ""))
    return (m.group(1) if m else "").replace("-", " ")


def search(query: str, per: int = 12) -> list[dict]:
    out = []
    k = (os.environ.get("PEXELS_API_KEY") or "").strip()
    if k:
        try:
            q = urllib.parse.urlencode({"query": query, "per_page": per, "orientation": "portrait", "size": "medium"})
            for v in _get(f"{PEXELS_API}?{q}", {"Authorization": k}).get("videos") or []:
                out.append({"desc": _desc_pexels(v), "where": "pexels", "dur": v.get("duration") or 0,
                            "files": [{"link": f.get("link"), "width": f.get("width") or 0, "height": f.get("height") or 0}
                                      for f in (v.get("video_files") or []) if f.get("link")]})
        except Exception as e:  # noqa: BLE001
            log(f"pexels 검색 실패: {str(e)[:80]}")
    k2 = (os.environ.get("PIXABAY_API_KEY") or "").strip()
    if k2 and not out:
        try:
            q = urllib.parse.urlencode({"key": k2, "q": query, "per_page": per, "video_type": "film", "safesearch": "true"})
            for h in _get(f"{PIXABAY_API}?{q}").get("hits") or []:
                vs = h.get("videos") or {}
                out.append({"desc": str(h.get("tags") or "").replace(",", " "), "where": "pixabay", "dur": h.get("duration") or 0,
                            "files": [{"link": f.get("url"), "width": f.get("width") or 0, "height": f.get("height") or 0}
                                      for f in vs.values() if f.get("url")]})
        except Exception as e:  # noqa: BLE001
            log(f"pixabay 검색 실패: {str(e)[:80]}")
    return out


def _ok(v: dict) -> bool:
    return not (set(str(v.get("desc", "")).lower().split()) & PEOPLE)


def _best_file(v: dict) -> dict | None:
    got = [f for f in v.get("files") or [] if (f.get("height") or 0) >= 1080 and f.get("link")]
    if not got:
        return None
    got.sort(key=lambda f: ((f.get("height") or 0) >= (f.get("width") or 1), -(f.get("height") or 0)), reverse=True)
    # 세로 파일 먼저, 그다음 큰 것 — 너무 큰 파일(4K)은 받는 시간이 길어 2160 이하를 우선
    got.sort(key=lambda f: (not ((f.get("height") or 0) >= (f.get("width") or 1)), (f.get("height") or 0) > 2160, -(f.get("height") or 0)))
    return got[0]


def cutaway(query: str, sec: float, out: Path) -> Path | None:
    """질의에 맞는 세로 실촬영 클립 하나를 받아 sec 초로 잘라 1080x1920 30fps 무음으로 맞춘다. 키 없음·실패면 None."""
    for v in search(query):
        if not _ok(v) or (v.get("dur") or 0) < sec:
            continue
        f = _best_file(v)
        if not f:
            continue
        raw = out.with_suffix(".src.mp4")
        try:
            req = urllib.request.Request(f["link"], headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r, open(raw, "wb") as fh:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    fh.write(chunk)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "0.5", "-i", str(raw), "-t", f"{sec:.3f}", "-an",
                            "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{GRADE},fps={FPS},setsar=1",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)], check=True)
            raw.unlink(missing_ok=True)
            log(f"B롤 {out.name} ← {v['where']} '{v.get('desc', '')[:40]}'")
            return out
        except Exception as e:  # noqa: BLE001
            log(f"B롤 받기 실패 ({v['where']}): {str(e)[:80]}")
            raw.unlink(missing_ok=True)
            continue
    log(f"B롤 없음: '{query}' (키 없음이거나 후보 없음)")
    return None
