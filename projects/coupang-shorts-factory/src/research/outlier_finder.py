"""M1. 소재 리서치 — 아웃라이어(돌연변이) 영상 탐지 (스펙 §M1).

YouTube Data API v3(공식 API만 — 스크래핑 금지 §2)로 벤치마크 채널의 최근 영상을 조회해
채널 중앙값 대비 3배 이상 터진 영상의 '제목·키워드만' 수집한다.
대본·오디오 추출은 절대 하지 않는다 (스펙 §M1 산출 규칙).

쿼터 절약: search.list(100유닛) 금지 → channels.list + playlistItems + videos.list (채널당 ~3유닛).
시크릿: SHORTS_YT_API_KEY (Data API v3 키 — OAuth 불필요, 읽기 전용)
산출: data/research/topics_{날짜}.json + report.md (소재 후보 풀 → M2 공급)
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
API = "https://www.googleapis.com/youtube/v3"


def main() -> int:
    key = os.environ.get("SHORTS_YT_API_KEY", "").strip()
    if not key:
        print("[research] SHORTS_YT_API_KEY 미등록 → 리서치 건너뜀 "
              "(Google Cloud Console에서 YouTube Data API v3 키를 만들어 등록하세요)")
        return 0

    import yaml
    conf = yaml.safe_load((PROJECT_ROOT / "config" / "competitors.yaml").read_text(encoding="utf-8")) or {}
    channels = conf.get("channels") or []
    if not channels:
        print("[research] config/competitors.yaml의 channels가 비어 있음 → 벤치마크 채널 ID를 추가하세요")
        return 0

    settings_conf = {}
    sp = PROJECT_ROOT / "config" / "settings.yaml"
    if sp.exists():
        settings_conf = (yaml.safe_load(sp.read_text(encoding="utf-8")) or {}).get("research", {})
    min_score = float(settings_conf.get("min_score", 3.0))
    recent_n = int(settings_conf.get("recent_videos", 30))

    import requests
    outliers, errors = [], []
    for ch in channels:
        cid = ch.get("id") if isinstance(ch, dict) else str(ch)
        try:
            outliers += _scan_channel(requests, key, cid, min_score, recent_n)
        except Exception as e:
            errors.append(f"{cid}: {e}")
            print(f"[research] 채널 {cid} 조회 실패(계속 진행): {e}")

    outliers.sort(key=lambda x: -x["score"])
    out_dir = PROJECT_ROOT / "data" / "research"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d")
    (out_dir / f"topics_{stamp}.json").write_text(
        json.dumps({"generated_at": stamp, "min_score": min_score,
                    "topics": outliers, "errors": errors}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    lines = [f"# 주간 소재 후보 리포트 ({stamp})", "",
             f"아웃라이어 기준: 채널 중앙값 조회수 대비 {min_score}배 이상", ""]
    for t in outliers[:10]:
        lines.append(f"- **{t['score']}x** [{t['title']}]({t['url']}) — {t['channel']} ({t['views']:,}회)")
    if not outliers:
        lines.append("(기준을 넘은 영상 없음)")
    report = "\n".join(lines)
    (out_dir / f"report_{stamp}.md").write_text(report, encoding="utf-8")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        Path(summary).open("a", encoding="utf-8").write(report + "\n")
    print(f"[research] 완료: 후보 {len(outliers)}건 → data/research/topics_{stamp}.json")

    from src import notify
    if outliers:
        notify.send("[쿠팡쇼츠 리서치] 이번 주 소재 후보 " + f"{len(outliers)}건\n" +
                    "\n".join(f"- {t['score']}x {t['title']}" for t in outliers[:5]))
    return 0


def _scan_channel(requests, key: str, channel_id: str, min_score: float, recent_n: int) -> list:
    # "@핸들"과 "UC..." 채널 ID 둘 다 지원 — 유튜브 앱에서 핸들을 그대로 복사해 붙여도 된다
    ident = {"forHandle": channel_id} if channel_id.startswith("@") else {"id": channel_id}
    r = requests.get(f"{API}/channels", params={
        "part": "contentDetails,snippet", "key": key, **ident}, timeout=30)
    r.raise_for_status()
    items = r.json().get("items") or []
    if not items:
        raise RuntimeError("채널 없음(ID/핸들 확인)")
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ch_name = items[0]["snippet"]["title"]

    video_ids = []
    page = None
    while len(video_ids) < recent_n:
        params = {"part": "contentDetails", "playlistId": uploads,
                  "maxResults": min(50, recent_n - len(video_ids)), "key": key}
        if page:
            params["pageToken"] = page
        pr = requests.get(f"{API}/playlistItems", params=params, timeout=30)
        pr.raise_for_status()
        data = pr.json()
        video_ids += [i["contentDetails"]["videoId"] for i in data.get("items", [])]
        page = data.get("nextPageToken")
        if not page:
            break

    if not video_ids:
        return []
    vr = requests.get(f"{API}/videos", params={
        "part": "statistics,snippet", "id": ",".join(video_ids[:50]), "key": key}, timeout=30)
    vr.raise_for_status()
    vids = vr.json().get("items", [])
    views = [int(v["statistics"].get("viewCount", 0)) for v in vids]
    med = statistics.median(views) if views else 0
    if med <= 0:
        return []

    out = []
    for v in vids:
        vc = int(v["statistics"].get("viewCount", 0))
        score = round(vc / med, 1)
        if score >= min_score:
            out.append({  # 제목·키워드만 기록 — 대본/오디오 추출 금지(§M1)
                "title": v["snippet"]["title"],
                "channel": ch_name,
                "videoId": v["id"],
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "views": vc,
                "channel_median": int(med),
                "score": score,
            })
    return out


if __name__ == "__main__":
    sys.exit(main())
