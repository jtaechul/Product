"""반자동(운영자 시드) 소싱 어댑터 (SSOT §6.3).

운영자가 관리자 페이지에서 시드(URL·해시태그·크리에이터·키워드)를 주입하면 그 시드로만 수집한다.
자동 모드(트렌드 크롤)가 불안정할 때의 폴백 경로이자, 실현성이 가장 높은 기본 경로다
(틱톡·유튜브가 데이터센터 IP를 차단해 자동 크롤이 GitHub Actions에서 막힐 수 있으므로 — SSOT §6.2).

현재 구현:
- kind='url': 그 URL의 메타데이터를 yt-dlp로 조회(다운로드 안 함)해 SourceVideo 생성 — 실동작.
- kind in (hashtag·creator·keyword): 플랫폼 검색이 필요 → 아직 미구현(빈 리스트 + note 로그).
  (플랫폼 검색 어댑터는 실현성 검증 후 별도 추가 — 지금 반쪽으로 만들지 않는다.)

⚠️ 저작권/약관: 완성본에 원본 영상을 어떻게 쓰는지(A/B/C)는 §13.2 운영자 결정 사항.
   이 어댑터는 '수집(다운로드)'만 담당하고, 화면 사용 방식은 편집·합성 단계가 정한다.
   yt-dlp 호출은 injectable(info_fn/download_fn)이라 네트워크 없이 단위 테스트 가능.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from src.sourcing.base import Seed, SourceAdapter, register
from src.sourcing.models import SourceVideo


def _platform_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if "tiktok" in host:
        return "tiktok"
    if "youtu" in host:      # youtube.com · youtu.be
        return "youtube"
    if "instagram" in host:
        return "instagram"
    return host or "unknown"


def _ytdlp_info(url: str) -> dict:
    """yt-dlp로 메타데이터만 추출(다운로드 안 함). 기본 info_fn."""
    import yt_dlp  # 지연 임포트 — 미설치·미사용 환경에서 임포트 실패 회피
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True, "extract_flat": False}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


class ManualSeedAdapter(SourceAdapter):
    name = "manual_seed"
    mode = "manual"

    def __init__(self, info_fn=None, download_fn=None):
        # 테스트·대체 구현 주입점. 기본은 yt-dlp.
        self._info_fn = info_fn or _ytdlp_info
        self._download_fn = download_fn

    def search(self, seed: Seed, limit: int = 10) -> list:
        if seed.kind != "url":
            print(f"[sourcing:manual_seed] '{seed.kind}' 시드는 플랫폼 검색 어댑터 필요 — "
                  f"현재 미구현(빈 결과). URL 시드를 쓰세요.")
            return []
        try:
            info = self._info_fn(seed.value) or {}
        except Exception as e:
            print(f"[sourcing:manual_seed] 메타 조회 실패({seed.value}): {e}")
            return []
        if not info:
            return []
        sv = SourceVideo(
            platform=(info.get("extractor_key") or seed.platform
                      or _platform_from_url(seed.value)).lower(),
            source_url=info.get("webpage_url") or seed.value,
            view_count=info.get("view_count"),
            tags=list(info.get("tags") or []),
            source_mode="manual",
            status="discovered",
            title=info.get("title"),
            duration=info.get("duration"),
            uploader=info.get("uploader") or info.get("channel"),
        )
        return [sv]

    def download(self, sv: SourceVideo, dest_dir: Path) -> Path | None:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            if self._download_fn is not None:
                out = self._download_fn(sv.source_url, dest_dir)
            else:
                out = self._ytdlp_download(sv.source_url, dest_dir, sv.id)
        except Exception as e:
            print(f"[sourcing:manual_seed] 다운로드 실패({sv.source_url}): {e}")
            sv.status = "failed"
            return None
        if out is None or not Path(out).exists():
            sv.status = "failed"
            return None
        sv.downloaded_path = str(out)
        sv.status = "downloaded"
        return Path(out)

    @staticmethod
    def _ytdlp_download(url: str, dest_dir: Path, sv_id: str) -> Path | None:
        """워터마크 없는 원본을 dest_dir에 저장(§6.1). mp4 우선."""
        import yt_dlp
        outtmpl = str(dest_dir / f"{sv_id}.%(ext)s")
        opts = {"quiet": True, "no_warnings": True, "noplaylist": True,
                "outtmpl": outtmpl,
                "format": "mp4/bestvideo+bestaudio/best",
                "merge_output_format": "mp4"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        hits = sorted(dest_dir.glob(f"{sv_id}.*"))
        return hits[0] if hits else None


# 레지스트리 등록(임포트 시). 자동 어댑터는 실현성 검증 후 별도 등록.
register(ManualSeedAdapter)
