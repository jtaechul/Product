"""M7. 유튜브 업로드 — YouTube Data API v3 videos.insert (스펙 §M7).

- 미인증 API 프로젝트는 업로드 영상이 자동 private 잠금 → 기본 privacy=private (스펙 §M7-2)
- 제휴 고지문(§3.1)은 설명란 '최상단 첫 줄' + 댓글에 코드로 강제, 누락 시 assert로 업로드 중단
- 고정(핀) 지정은 API 미지원 → 댓글 자동 등록까지 수행, 핀 고정은 유튜브 앱에서 1탭(문서화)

시크릿: SHORTS_YT_REFRESH_TOKEN(필수 — 쿠팡 쇼츠 '새 채널' 계정으로 발급),
SHORTS_YT_CLIENT_ID/SECRET(없으면 저장소 공용 YOUTUBE_CLIENT_ID/SECRET 재사용 가능).
⚠️ 기존 YOUTUBE_REFRESH_TOKEN(다른 채널 계정)은 절대 폴백하지 않는다 — 엉뚱한 채널 업로드 방지.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다"


def _creds_env() -> dict:
    return {
        "client_id": (os.environ.get("SHORTS_YT_CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID") or "").strip(),
        "client_secret": (os.environ.get("SHORTS_YT_CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET") or "").strip(),
        "refresh_token": (os.environ.get("SHORTS_YT_REFRESH_TOKEN") or "").strip(),  # SHORTS_ 전용(의도적)
    }


def is_configured() -> bool:
    c = _creds_env()
    return all(c.values())


def missing_hint() -> str:
    c = _creds_env()
    need = [k for k, v in {
        "SHORTS_YT_REFRESH_TOKEN": c["refresh_token"],
        "SHORTS_YT_CLIENT_ID(또는 공용 YOUTUBE_CLIENT_ID)": c["client_id"],
        "SHORTS_YT_CLIENT_SECRET(또는 공용 YOUTUBE_CLIENT_SECRET)": c["client_secret"],
    }.items() if not v]
    return "미등록 시크릿: " + ", ".join(need)


def build_description(script: dict, product: dict) -> str:
    specs = "\n".join(f"- {s}" for s in product.get("specs", []))
    parts = [
        DISCLOSURE,  # §3.1 ① 최상단 첫 줄 (절대 위치 변경 금지)
        "",
        script.get("description_body", "").strip(),
        "",
        f"[제품 정보]\n{product.get('name', '')}\n{specs}".strip(),
        "",
        f"제품 보러가기: {product.get('affiliate_url', '')}",
        "",
        " ".join(script.get("hashtags", [])),
    ]
    desc = "\n".join(parts).strip()
    assert desc.split("\n")[0] == DISCLOSURE, "고지문이 설명란 첫 줄이 아님 — 업로드 중단(§3.1)"
    return desc[:4900]


def upload(video_path: Path, script: dict, product: dict, settings: dict,
           privacy: str = "private") -> dict:
    """업로드 + 고지 댓글 등록. 반환: upload_result dict (videoId, url, status)."""
    c = _creds_env()
    if not all(c.values()):
        raise RuntimeError(f"유튜브 업로드 자격 증명 부족 — {missing_hint()}")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = Credentials(
        token=None,
        refresh_token=c["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=c["client_id"],
        client_secret=c["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    title = (script.get("title") or product.get("name", ""))[:95]
    description = build_description(script, product)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": [h.lstrip("#") for h in script.get("hashtags", [])],
            "categoryId": str(settings.get("upload", {}).get("category_id", "28")),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"[upload] 업로드 진행 {int(status.progress() * 100)}%")
    video_id = resp["id"]
    url = f"https://youtu.be/{video_id}"
    print(f"[upload] 업로드 완료: {url} (privacy={privacy})")

    # §3.1 ② 링크 옆 고지문 — 댓글 자동 등록 (핀 고정은 UI에서 1탭)
    pinned = script.get("pinned_comment") or ""
    assert DISCLOSURE in pinned, "고지문이 댓글에 없음 — 등록 중단(§3.1)"
    comment_id = None
    try:
        cresp = yt.commentThreads().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id,
                              "topLevelComment": {"snippet": {"textOriginal": pinned}}}},
        ).execute()
        comment_id = cresp.get("id")
        print("[upload] 고지 댓글 등록 완료 (앱에서 '고정'만 눌러주세요)")
    except Exception as e:  # 댓글 실패는 업로드 자체를 무효화하지 않음 — 보고만
        print(f"[upload] 경고: 댓글 등록 실패({e}) — 수동 등록 필요")

    return {"videoId": video_id, "url": url, "status": privacy,
            "comment_id": comment_id, "title": title}
