"""YouTube 자동 업로드 (YouTube Data API v3 · videos.insert).

운영 게이트(확정): 생성물은 **비공개(private)** 로 업로드하고, 텔레그램으로 링크를 보내
운영자가 확인 후 유튜브에서 직접 '공개'로 전환한다(잘못된 영상 공개 방지).

인증: OAuth2 리프레시 토큰(일회성 발급). 시크릿 3개를 환경변수로 받는다.
  - YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET : Google Cloud OAuth 클라이언트(데스크톱)
  - YOUTUBE_REFRESH_TOKEN : scripts/youtube_oauth.py 로 1회 발급한 값
키가 하나라도 없으면 RuntimeError("no_credentials") → 상위(워크플로)는 업로드만 생략.

★채널은 **하나만 쓴다**(운영자 확정 · 재확인). 한때 난파선을 별도 채널로 보내는 분기를 넣었으나
  운영자 지시로 전부 폐기했다 — "난파선 채널 따로 만들지 마. 내가 알아서 할 거야."
  업로드 대상은 언제나 YOUTUBE_* 시크릿의 그 채널이다. 카테고리로 채널을 가르지 않는다.

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
           made_for_kids: bool = False, publish_at: str | None = None) -> dict:
    """영상 업로드(재개형). 반환: {"video_id", "url", "privacy"}.

    category_id 기본 15 = 'Pets & Animals'(해양생물에 적합). privacy 기본 private(게이트).
    publish_at(UTC ISO 'YYYY-MM-DDTHH:MM:SSZ'): 예약 공개 — 지금은 비공개로 올리고 그 시각에 유튜브가 자동 공개
    (YouTube Data API 규칙: publishAt 은 privacyStatus=private 일 때만 유효).
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
    if publish_at:
        body["status"].update(privacyStatus="private", publishAt=publish_at)
        privacy = "scheduled"
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


# ── 재생목록·실적(운영자 선택 2026-10-05) ─────────────────────────────────────────
# 업로드 전용 토큰(youtube.upload)으로는 재생목록·실적을 못 읽는다 → scripts/youtube_oauth.py 로 토큰을 다시 받으면
# (youtube + yt-analytics.readonly 추가) 동작한다. 권한이 없으면 예외를 던지고, 호출부가 '토큰 재발급 필요'로 기록한다.
SCOPE_HELP = "유튜브 토큰에 재생목록·실적 권한이 없습니다 — scripts/youtube_oauth.py 로 토큰을 다시 발급해 YOUTUBE_REFRESH_TOKEN 을 바꿔 주세요"


def _creds_any():
    from google.oauth2.credentials import Credentials
    # scopes=None: 토큰이 받은 권한 그대로 갱신(없는 권한을 요구하면 갱신 자체가 실패하므로 지정하지 않는다)
    return Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                       client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
                       token_uri=_TOKEN_URI, scopes=None)


def add_to_playlist(video_id: str, title: str, description: str = "") -> dict:
    """제목이 같은 내 재생목록을 찾고(없으면 공개로 만들고) 영상을 넣는다. 반환 {"playlist_id"}."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=_creds_any(), cache_discovery=False)
    pid, tok = None, None
    while not pid:
        r = yt.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=tok).execute()
        pid = next((p["id"] for p in r.get("items", []) if p["snippet"]["title"] == title), None)
        tok = r.get("nextPageToken")
        if not tok:
            break
    if not pid:
        pid = yt.playlists().insert(part="snippet,status", body={"snippet": {"title": title, "description": description},
                                                                 "status": {"privacyStatus": "public"}}).execute()["id"]
    yt.playlistItems().insert(part="snippet", body={"snippet": {"playlistId": pid, "resourceId": {
        "kind": "youtube#video", "videoId": video_id}}}).execute()
    return {"playlist_id": pid}


STAT_METRICS = "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments"


def token_scopes() -> list[str]:
    """지금 YOUTUBE_REFRESH_TOKEN 이 실제로 받은 권한 목록(토큰 값은 기록하지 않는다 — 권한 이름만)."""
    import json
    import urllib.parse
    import urllib.request
    from google.auth.transport.requests import Request
    c = _creds_any()
    c.refresh(Request())
    q = urllib.parse.urlencode({"access_token": c.token})
    with urllib.request.urlopen(f"https://oauth2.googleapis.com/tokeninfo?{q}", timeout=20) as r:
        return sorted((json.loads(r.read().decode()).get("scope") or "").split())


def video_stats(video_id: str, start: str, end: str) -> dict:
    """한 영상의 실적. ① YouTube Analytics(조회·시청 분·평균 시청·구독 증가·좋아요·댓글 — yt-analytics 권한 필요)
    ② 안 되면 Data API videos.list 공개 통계(조회·좋아요·댓글 — 지금 토큰으로 되는지 실제 실행으로 확인).
    반환에 _source(analytics|data_api)와 _errors(실패한 경로 사유)를 붙인다."""
    from googleapiclient.discovery import build
    errors = {}
    creds = _creds_any()
    try:
        ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=STAT_METRICS,
                               filters=f"video=={video_id}").execute()
        row = (r.get("rows") or [[0] * len(STAT_METRICS.split(","))])[0]
        return {**dict(zip(STAT_METRICS.split(","), row)), "_source": "analytics"}
    except Exception as e:                                   # noqa: BLE001
        errors["analytics"] = str(e)[:200]
    try:
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        items = yt.videos().list(part="statistics", id=video_id).execute().get("items") or []
        if not items:
            raise RuntimeError("영상 없음")
        s = items[0]["statistics"]
        return {"views": int(s.get("viewCount") or 0), "likes": int(s.get("likeCount") or 0),
                "comments": int(s.get("commentCount") or 0), "_source": "data_api", "_errors": errors}
    except Exception as e:                                   # noqa: BLE001
        errors["data_api"] = str(e)[:200]
    raise RuntimeError(" / ".join(f"{k}: {v}" for k, v in errors.items()))
