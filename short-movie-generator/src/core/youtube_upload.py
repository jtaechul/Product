"""YouTube 자동 업로드 (YouTube Data API v3 · videos.insert).

운영 게이트(확정): 생성물은 **비공개(private)** 로 업로드하고, 텔레그램으로 링크를 보내
운영자가 확인 후 유튜브에서 직접 '공개'로 전환한다(잘못된 영상 공개 방지).

인증: OAuth2 리프레시 토큰(일회성 발급). 시크릿 3개를 환경변수로 받는다.
  - YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET : Google Cloud OAuth 클라이언트(데스크톱)
  - YOUTUBE_REFRESH_TOKEN : scripts/youtube_oauth.py 로 1회 발급한 값
키가 하나라도 없으면 RuntimeError("no_credentials") → 상위(워크플로)는 업로드만 생략.

★채널 분리(운영자 확정): 난파선(shipwreck)은 해양생물 채널과 **다른 채널**에 올린다.
  같은 채널에 '심해 생물'과 '난파선 역사'가 섞이면 시청자·추천 알고리즘 양쪽에서 주제가 흐려진다
  (실측: 공개 29편 중 8편이 난파선). 그래서 업로드 대상 채널을 카테고리로 고른다.
  - main  : YOUTUBE_CLIENT_ID / _SECRET / _REFRESH_TOKEN            ← 해양생물(심해·일반·조류)
  - wreck : YOUTUBE_WRECK_CLIENT_ID / _SECRET / _REFRESH_TOKEN      ← 난파선 전용 채널
  난파선 채널 시크릿이 없으면 **본 채널로 흘려보내지 않고** RuntimeError("no_credentials:wreck")
  로 막는다(분리의 목적이 사라지므로). 예외로 올려야 하면 호출부에서 channel="main"을 명시한다.

의존성(요구): google-auth, google-auth-oauthlib, google-api-python-client.
없으면 ImportError → 워크플로에서 pip 설치.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_TOKEN_URI = "https://oauth2.googleapis.com/token"
_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 채널별 환경변수 접두어. 값이 ""이면 접두어 없음(기존 본 채널 시크릿 그대로).
_CHANNEL_PREFIX = {"main": "YOUTUBE_", "wreck": "YOUTUBE_WRECK_"}
# 유튜브 카테고리: 생물=15(Pets & Animals), 난파선=27(Education · 역사/기록물)
_CHANNEL_YT_CATEGORY = {"main": "15", "wreck": "27"}
# 난파선 카테고리 id(레코드 category 값). 이 목록만 별도 채널로 간다.
_WRECK_CATEGORIES = {"shipwreck"}


def channel_for_category(category_id: str | None) -> str:
    """레코드의 category → 업로드 채널 키. 난파선만 분리, 나머지는 본 채널."""
    return "wreck" if str(category_id or "").strip().lower() in _WRECK_CATEGORIES else "main"


def default_yt_category(channel: str = "main") -> str:
    """채널별 유튜브 카테고리 id(난파선은 생물이 아니라 교육/역사)."""
    return _CHANNEL_YT_CATEGORY.get(channel, "15")


def _env_keys(channel: str) -> tuple[str, str, str]:
    p = _CHANNEL_PREFIX.get(channel)
    if p is None:
        raise ValueError(f"unknown channel: {channel}")
    return (f"{p}CLIENT_ID", f"{p}CLIENT_SECRET", f"{p}REFRESH_TOKEN")


def has_credentials(channel: str = "main") -> bool:
    return all(os.environ.get(k) for k in _env_keys(channel))


def probe(channel: str = "main") -> dict:
    """토큰 건강검진 — 업로드 없이 리프레시만 수행. 반환 {"ok": bool, "error": str}.

    성공 = 토큰 살아있음. 이 호출 자체가 토큰을 '사용'하므로 **6개월 미사용 폐기도 예방**한다
    (주간 스케줄 워크플로가 이걸 돌려 토큰을 상시 워밍 + 만료 조짐 조기 감지).
    """
    if not has_credentials(channel):
        return {"ok": False, "error": f"no_credentials:{channel}"}
    try:
        import google.auth.transport.requests as gart
        cid, csec, ctok = _env_keys(channel)
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=None, refresh_token=os.environ[ctok],
            client_id=os.environ[cid], client_secret=os.environ[csec],
            token_uri=_TOKEN_URI, scopes=_SCOPES,
        )
        creds.refresh(gart.Request())
        return {"ok": bool(creds.token), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def _client(channel: str = "main"):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    cid, csec, ctok = _env_keys(channel)
    creds = Credentials(
        token=None,
        refresh_token=os.environ[ctok],
        client_id=os.environ[cid],
        client_secret=os.environ[csec],
        token_uri=_TOKEN_URI,
        scopes=_SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video_path: str, title: str, description: str, tags: list[str] | None = None,
           *, privacy: str = "private", category_id: str = "",
           made_for_kids: bool = False, channel: str = "main") -> dict:
    """영상 업로드(재개형). 반환: {"video_id", "url", "privacy", "channel"}.

    channel: "main"(해양생물) 또는 "wreck"(난파선 전용 채널). 카테고리로 고르려면
             channel_for_category(rec["category"]) 를 쓴다.
    category_id 미지정 시 채널 기본값(생물 15 · 난파선 27). privacy 기본 private(게이트).
    """
    if not has_credentials(channel):
        # ★난파선 시크릿이 없다고 본 채널로 흘려보내지 않는다(채널 분리 무력화 방지).
        raise RuntimeError(f"no_credentials:{channel}")
    category_id = category_id or default_yt_category(channel)
    from googleapiclient.http import MediaFileUpload

    yt = _client(channel)
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
    log.info("[youtube] 완료: %s (%s · 채널=%s)", vid, privacy, channel)
    return {"video_id": vid, "url": f"https://youtu.be/{vid}",
            "privacy": privacy, "channel": channel}
