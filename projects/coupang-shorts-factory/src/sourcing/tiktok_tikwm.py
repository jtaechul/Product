"""틱톡 소싱 어댑터 — tikwm 공개 API 경유 (SSOT §6 · 2026-07-26 사용자 확정 방향).

프로브(run2)에서 GitHub Actions 러너에서 tikwm 검색+무워터마크 다운로드가 됨(VIABLE) 확인.
GA가 틱톡에 직접 붙는 건 봇차단이라, tikwm가 대신 검색·무워터마크 URL을 주는 방식으로 우회한다.

- search: 키워드/해시태그/크리에이터/URL 시드 → SourceVideo 후보(조회수 내림차순, download_url 포함)
- download: download_url(무워터마크)에서 mp4 저장. 만료 시 source_url로 tikwm 재해석 폴백.

⚠️ 비공식 API라 불안정·레이트리밋 가능 → HTTP를 주입 가능하게 하고(단위 테스트), SourceAdapter로
   감싸 서비스 교체가 쉽게 한다. 저작권/약관(C 변형·재가공)은 §13.2 운영자 결정에 따른다.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from src.sourcing.base import Seed, SourceAdapter, register
from src.sourcing.models import SourceVideo

TIKWM_BASE = "https://www.tikwm.com"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_MIN_BYTES = 10_000   # 이보다 작으면 실패(에러 페이지 등)로 간주


def _default_http(url: str, data: dict | None = None, timeout: int = 60) -> bytes:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body,
                                 headers={"User-Agent": _UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


class TikwmClient:
    """tikwm 얇은 클라이언트. http는 주입 가능(테스트·서비스 교체)."""

    def __init__(self, http=None, base: str = TIKWM_BASE):
        self._http = http or _default_http
        self.base = base

    def _api(self, path: str, params: dict, post: bool = False) -> dict:
        if post:
            raw = self._http(self.base + path, params)
        else:
            raw = self._http(self.base + path + "?" + urllib.parse.urlencode(params))
        j = json.loads(raw)
        if j.get("code") != 0:
            raise RuntimeError(f"tikwm code={j.get('code')} msg={j.get('msg')}")
        return j.get("data") or {}

    def search_page(self, keywords: str, count: int = 20, cursor: int = 0) -> tuple:
        """검색 한 페이지 → (videos, next_cursor, has_more). cursor를 넘겨 '진짜 다음 영상'을 받는다."""
        data = self._api("/api/feed/search",
                         {"keywords": keywords, "count": count, "cursor": int(cursor or 0), "hd": 1},
                         post=True)
        try:
            nxt = int(data.get("cursor") or 0)
        except (TypeError, ValueError):
            nxt = 0
        return (data.get("videos") or [], nxt, bool(data.get("hasMore")))

    def search(self, keywords: str, count: int = 10, cursor: int = 0) -> list:
        return self.search_page(keywords, count, cursor)[0]

    def user_posts(self, unique_id: str, count: int = 10) -> list:
        return (self._api("/api/user/posts",
                          {"unique_id": unique_id, "count": count}).get("videos")) or []

    def resolve(self, url: str) -> dict:
        return self._api("/api/", {"url": url, "hd": 1})

    def download_bytes(self, url: str) -> bytes:
        return self._http(url, None)


def _abs_play(url, base: str) -> str | None:
    if not url:
        return None
    return url if str(url).startswith("http") else base + str(url)


def _sv_from_item(item: dict, base: str) -> SourceVideo:
    vid = str(item.get("video_id") or item.get("id") or "").strip()
    author = item.get("author") or {}
    uniq = author.get("unique_id") or ""
    src = (item.get("url")
           or (f"https://www.tiktok.com/@{uniq}/video/{vid}" if uniq and vid else ""))
    play = _abs_play(item.get("hdplay") or item.get("play"), base)
    cover = _abs_play(item.get("origin_cover") or item.get("cover"), base)
    return SourceVideo(
        platform="tiktok",
        source_url=src or (play or ""),
        view_count=item.get("play_count"),
        download_url=play,
        cover=cover,
        source_mode="auto",         # 검색 발굴 = 자동 discovery
        status="discovered",
        title=item.get("title"),
        duration=item.get("duration"),
        uploader=author.get("nickname") or (uniq or None),
    )


class TikwmAdapter(SourceAdapter):
    name = "tiktok_tikwm"
    mode = "auto"

    def __init__(self, client: TikwmClient | None = None):
        self.client = client or TikwmClient()

    def search(self, seed: Seed, limit: int = 10) -> list:
        return self.search_page(seed, limit)[0]

    def search_page(self, seed: Seed, limit: int = 20, cursor: int = 0) -> tuple:
        """(svs, next_cursor, has_more). keyword/hashtag만 커서 페이지네이션, 그 외는 커서 무시."""
        nxt, more = 0, False
        try:
            if seed.kind in ("keyword", "hashtag"):
                items, nxt, more = self.client.search_page(seed.value.lstrip("#"), count=limit, cursor=cursor)
            elif seed.kind == "creator":
                items = self.client.user_posts(seed.value.lstrip("@"), count=limit)
            elif seed.kind == "url":
                items = [self.client.resolve(seed.value)]
            else:
                return [], 0, False
        except Exception as e:
            print(f"[sourcing:tikwm] 검색 실패({seed.kind}:{seed.value}): {e}")
            return [], 0, False
        svs = [_sv_from_item(it, self.client.base) for it in items if it]
        svs = [s for s in svs if s.source_url or s.download_url]
        svs.sort(key=lambda s: (s.view_count or 0), reverse=True)   # 조회수 상위 추천
        return svs[:limit], nxt, more

    def download(self, sv: SourceVideo, dest_dir: Path) -> Path | None:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        url = sv.download_url
        if not url and sv.source_url:   # 만료·미보유 시 tikwm로 재해석
            try:
                r = self.client.resolve(sv.source_url)
                url = _abs_play(r.get("hdplay") or r.get("play"), self.client.base)
            except Exception as e:
                print(f"[sourcing:tikwm] resolve 실패({sv.source_url}): {e}")
                sv.status = "failed"
                return None
        if not url:
            sv.status = "failed"
            return None
        try:
            data = self.client.download_bytes(url)
        except Exception as e:
            print(f"[sourcing:tikwm] 다운로드 실패({url[:60]}): {e}")
            sv.status = "failed"
            return None
        if not data or len(data) < _MIN_BYTES:
            print(f"[sourcing:tikwm] 다운로드 바이트 부족({len(data or b'')}) — 실패 처리")
            sv.status = "failed"
            return None
        out = dest_dir / f"{sv.id}.mp4"
        out.write_bytes(data)
        sv.downloaded_path = str(out)
        sv.status = "downloaded"
        return out


register(TikwmAdapter)
