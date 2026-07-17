"""M7. 유튜브 업로드 — YouTube Data API v3 videos.insert (스펙 §M7).

- 미인증 API 프로젝트는 업로드 영상이 자동 private 잠금 → 기본 privacy=private (스펙 §M7-2)
- 제휴 고지문(§3.1)은 설명란 '최상단 첫 줄' + 댓글에 코드로 강제, 누락 시 assert로 업로드 중단
  (공정위 근접성 원칙상 최상단이 가장 안전 — 2026-07-17 사용자 재확정)
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

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # coupang-shorts-factory/


def _store_number(row_hash: str) -> str | None:
    """공개 스토어 카탈로그(admin/public/store-catalog.json)에서 이 상품(row_hash)의
    번호를 찾아 '001' 형태로 반환. 스토어에 없으면 None(번호 미표시)."""
    if not row_hash:
        return None
    try:
        cat = json.loads((PROJECT_ROOT / "admin" / "public" / "store-catalog.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    for it in (cat if isinstance(cat, list) else []):
        if str(it.get("row_hash", "")) == str(row_hash) and it.get("number") is not None:
            try:
                return f"{int(it['number']):03d}"
            except (TypeError, ValueError):
                return None
    return None


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


# 항상 붙는 브랜드+발견 해시태그(2026-07-17 사용자 확정). #미래마켓=클릭 시 우리 채널 영상만 모여
# '정주행' 유도(브랜드 그룹핑), #꿀템=검색량 크고 카테고리 불문 채널에 두루 맞는 발견 태그.
# 모델이 만든 상품별 태그 앞에 붙이고 중복(#·대소문자 무시)은 제거한다. #쇼츠는 유튜브가 포맷으로
# 자동 분류하므로 일부러 넣지 않는다(노이즈 방지).
FIXED_HASHTAGS = ["#미래마켓", "#꿀템"]

# 제품·구매처 안내는 설명란에 스펙·raw 링크를 늘어놓지 않고(신규 채널은 설명란 링크가 클릭 안 되고
# 궁금증→프로필 유도 전략과도 어긋남) '프로필 링크(미래마켓 스토어)로 오라'는 한 줄로만 둔다(2026-07-17).
# 실제 클릭되는 쿠팡 어필리에이트 링크는 링크가 살아있는 '고정 댓글'에 있다(youtube 업로드 시 등록).
PROFILE_CTA = "제품이 궁금하다면? 프로필 링크(미래마켓 스토어)에서 확인하세요"


def merge_hashtags(script: dict) -> list:
    """고정 브랜드 태그 + 모델 태그를 합쳐 중복 제거한 최종 해시태그 리스트(브랜드 먼저)."""
    out, seen = [], set()
    for h in FIXED_HASHTAGS + list(script.get("hashtags", []) or []):
        t = str(h).strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t
        key = t.lower().lstrip("#")
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def build_description(script: dict, product: dict) -> str:
    # 정식 제품명은 설명란에도 노출하지 않는다(2026-07-16 사용자 지시 — 궁금증→프로필 링크로 유도).
    #   ① 하드코딩 '[제품 정보] 상품명' 블록 제거 ② 모델이 쓴 description_body에서도 제품명 흔적 제거.
    from src.script.sanitize import hide_product_name, product_avoid_terms
    avoid = product_avoid_terms(product)
    body = hide_product_name(script.get("description_body", "").strip(), avoid)
    num = _store_number(product.get("_row_hash", ""))   # 스토어 카탈로그 번호(No.###과 동일)
    # 설명란은 '읽히게' 담백히: 고지문(맨 위 첫 줄) → 번호 → 훅 본문 → 프로필 안내 한 줄 → 해시태그.
    #   상세 스펙 나열·클릭 안 되는 raw 링크는 뺀다(2026-07-17 사용자 지시). 구매는 프로필/고정 댓글로.
    parts = [DISCLOSURE, ""]              # §3.1 고지문 — 설명란 최상단 첫 줄(2026-07-17 사용자 재확정, 공정위 근접성 원칙상 최안전)
    if num:
        parts += [f"미래마켓 #{num}", ""]   # 상품 번호 — 영상↔스토어(store#N) 매칭용
    parts += [
        body,
        "",
        PROFILE_CTA,          # 제품·구매처 안내는 프로필 링크 한 줄로만(별도 문단이라 안 겹침)
        "",
        " ".join(merge_hashtags(script)),
    ]
    desc = "\n".join(parts).strip()[:4900]
    assert desc.split("\n")[0] == DISCLOSURE, "고지문이 설명란 첫 줄이 아님 — 업로드 중단(§3.1)"
    return desc


def build_pinned_comment(product: dict, settings: dict) -> str:
    """고정 댓글(§3.1 ②) — 고지문(첫 줄) + 클릭되는 미래마켓 스토어 '딥링크'.
    스토어 URL 끝에 그 상품 번호(#001)를 붙이면 store.html 딥링크 핸들러가 해당 상품 카드로
    바로 스크롤·강조한다(2026-07-17 사용자 제안). 번호가 아직 없으면 스토어 홈으로 보낸다."""
    num = _store_number(product.get("_row_hash", ""))
    store_url = settings.get("channel", {}).get("store_url", "https://miraemarket.pages.dev")
    link = f"{store_url}#{num}" if num else store_url
    return f"{DISCLOSURE}\n\n미래마켓에서 이 제품 보기 → {link}"


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
            "tags": [h.lstrip("#") for h in merge_hashtags(script)],
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
    #   업로드 시점에 스토어 번호(_store_number)로 딥링크(#001)까지 붙여 그 상품으로 바로 이동.
    pinned = build_pinned_comment(product, settings)
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
