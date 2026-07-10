"""YouTube 자동 업로드 (YouTube Data API v3 · videos.insert).

운영 게이트(확정): 생성물은 **비공개(private)** 로 업로드하고, 텔레그램으로 링크를 보내
운영자가 확인 후 유튜브에서 직접 '공개'로 전환한다(잘못된 영상 공개 방지).

인증: OAuth2 리프레시 토큰(일회성 발급). 시크릿 3개를 환경변수로 받는다.
  - YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET : Google Cloud OAuth 클라이언트(데스크톱)
  - YOUTUBE_REFRESH_TOKEN : scripts/youtube_oauth.py 로 1회 발급한 값
키가 하나라도 없으면 RuntimeError("no_credentials") → 상위(워크플로)는 업로드만 생략.

의존성(요구): google-auth, google-auth-oauthlib, google-api-python-client.
없으면 ImportError → 워크플로에서 pip 설치.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def has_credentials() -> bool:
    return all(os.environ.get(k) for k in
               ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"))


def probe() -> dict:
    """토큰 건강검진 — 업로드 없이 리프레시만 수행. 반환 {"ok": bool, "error": str}.

    성공 = 토큰 살아있음. 이 호출 자체가 토큰을 '사용'하므로 **6개월 미사용 폐기도 예방**한다
    (주간 스케줄 워크플로가 이걸 돌려 토큰을 상시 워밍 + 만료 조짐 조기 감지).
    """
    if not has_credentials():
        return {"ok": False, "error": "no_credentials"}
    try:
        import google.auth.transport.requests as gart
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
            client_id=os.environ["YOUTUBE_CLIENT_ID"],
            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
            token_uri=_TOKEN_URI, scopes=_SCOPES,
        )
        creds.refresh(gart.Request())
        return {"ok": bool(creds.token), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def _client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri=_TOKEN_URI,
        scopes=_SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video_path: str, title: str, description: str, tags: list[str] | None = None,
           *, privacy: str = "private", category_id: str = "15",
           made_for_kids: bool = False) -> dict:
    """영상 업로드(재개형). 반환: {"video_id", "url", "privacy"}.

    category_id 기본 15 = 'Pets & Animals'(해양생물에 적합). privacy 기본 private(게이트).
    """
    if not has_credentials():
        raise RuntimeError("no_credentials")
    from googleapiclient.http import MediaFileUpload

    yt = _client()
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": (tags or [])[:15],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": bool(made_for_kids),
        },
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log.info("[youtube] 업로드 %d%%", int(status.progress() * 100))
    vid = resp["id"]
    log.info("[youtube] 완료: %s (%s)", vid, privacy)
    return {"video_id": vid, "url": f"https://youtu.be/{vid}", "privacy": privacy}
