"""M7. 유튜브 업로드 — YouTube Data API v3 videos.insert (스펙 §M7).

- 기본 privacy=unlisted(일부공개, 2026-07-17 확정): 비공개(private)는 유튜브가 댓글을 막아
  고지 댓글 자동 등록이 불가(run129 검증) → 일부공개로 올려 댓글까지 자동, 검수 후 공개 전환
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
BRAND = "미래에서 온 만물상"   # 채널 표시명(2026-07-19 사용자 확정, 핸들 @miraemarket·스토어 URL은 유지)

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # coupang-shorts-factory/
PENDING_PATH = PROJECT_ROOT / "data" / "pending_comments.json"   # 비공개→공개 대기 중인 고지 댓글 큐


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
# 고정 해시태그 — 모든 업로드의 설명란·유튜브 태그에 항상 포함(merge_hashtags가 병합).
# ⭐ 2026-07-19 사용자 확정: #인생꿀템 #인생꿀팁 #생활꿀팁 #생활꿀템 4종은 반드시 들어간다(빼지 말 것).
FIXED_HASHTAGS = ["#미래만물상", "#꿀템", "#인생꿀템", "#인생꿀팁", "#생활꿀팁", "#생활꿀템"]

# 제품·구매처 안내는 설명란에 스펙·raw 링크를 늘어놓지 않고(신규 채널은 설명란 링크가 클릭 안 되고
# 궁금증→프로필 유도 전략과도 어긋남) '프로필 링크(미래마켓 스토어)로 오라'는 한 줄로만 둔다(2026-07-17).
# 실제 클릭되는 쿠팡 어필리에이트 링크는 링크가 살아있는 '고정 댓글'에 있다(youtube 업로드 시 등록).
PROFILE_CTA = f"제품이 궁금하다면? 프로필 링크({BRAND} 스토어)에서 확인하세요"


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
    # 설명란은 '읽히게' 담백히: 고지문(맨 위 첫 줄) → 바로 밑 프로필 안내 → 번호 → 훅 본문 → 해시태그.
    #   상세 스펙 나열·클릭 안 되는 raw 링크는 뺀다(2026-07-17 사용자 지시). 구매는 프로필/고정 댓글로.
    #   §3.1 고지문 바로 다음 줄에 프로필 안내를 붙인다(2026-07-17 사용자 지시 — 고지 옆 유도).
    parts = [DISCLOSURE, "", PROFILE_CTA, ""]   # 고지문(최상단 첫 줄) + 바로 밑 프로필 안내
    if num:
        parts += [f"{BRAND} #{num}", ""]   # 상품 번호 — 영상↔스토어(store#N) 매칭용
    parts += [
        body,
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
    base = settings.get("channel", {}).get("store_url", "https://miraemarket.pages.dev").rstrip("/")
    # ⭐ 링크 형식(2026-07-17 사용자 확정): 도메인 뒤 반드시 "/" 다음 "#번호" — '.dev#005'처럼 /없이
    #   #이 붙으면 유튜브 댓글 자동 링크 인식이 깨져 클릭이 안 된다. URL은 줄 단독으로 둬야 확실히 인식.
    link = f"{base}/#{num}" if num else f"{base}/"
    return f"{DISCLOSURE}\n{BRAND}에서 이 제품 보기 →\n{link}"


def _yt_client():
    """YouTube Data API 클라이언트 — upload·댓글·상태조회 공용. 자격증명은 환경변수에서."""
    c = _creds_env()
    if not all(c.values()):
        raise RuntimeError(f"유튜브 자격 증명 부족 — {missing_hint()}")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials(
        token=None,
        refresh_token=c["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=c["client_id"],
        client_secret=c["client_secret"],
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def get_privacy_status(video_id: str) -> str | None:
    """영상의 현재 공개 상태(public|unlisted|private) 반환. 삭제·조회불가면 None."""
    yt = _yt_client()
    resp = yt.videos().list(part="status", id=video_id).execute()
    items = resp.get("items") or []
    if not items:
        return None
    return (items[0].get("status") or {}).get("privacyStatus")


def post_pinned_comment(video_id: str, pinned: str) -> str:
    """고지 댓글을 단다(공개·일부공개 영상에서만 가능). 반환: comment_id."""
    assert DISCLOSURE in pinned, "고지문이 댓글에 없음 — 등록 중단(§3.1)"
    yt = _yt_client()
    cresp = yt.commentThreads().insert(
        part="snippet",
        body={"snippet": {"videoId": video_id,
                          "topLevelComment": {"snippet": {"textOriginal": pinned}}}},
    ).execute()
    return cresp.get("id")


def upload(video_path: Path, script: dict, product: dict, settings: dict,
           privacy: str = "private") -> dict:
    """업로드 + (공개/일부공개면) 고지 댓글 등록. 비공개면 댓글은 미루고 대기열용 정보를 반환.
    반환: {videoId, url, status, comment_id, comment_pending, pinned, title}."""
    from googleapiclient.http import MediaFileUpload
    yt = _yt_client()

    # 제목=순수 특장점(2026-07-17 사용자 확정) — 예전에 저장된 기획이 올라와도 타깃 서술어(자취 등)는
    # 업로드 직전 최종 관문에서 한 번 더 제거한다(생성·재생성 단계와 동일 규칙).
    from src.script.sanitize import strip_target_words
    title = strip_target_words(script.get("title") or product.get("name", ""))[:95]
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
    # ⭐ 비공개 잠금 감지(2026-07-17 공개 업로드 전환): 유튜브는 API 심사(audit)를 안 받은 프로젝트가
    #   API로 올린 영상을 '비공개 잠금'으로 강제할 수 있다 — 요청(공개)과 실제 상태가 다르면 즉시 알린다.
    got_privacy = (resp.get("status") or {}).get("privacyStatus", "") or privacy

    # §3.1 ② 링크 옆 고지문 — 댓글. 업로드 시점에 스토어 번호(_store_number)로 딥링크(#001)까지 붙인다.
    pinned = build_pinned_comment(product, settings)
    assert DISCLOSURE in pinned, "고지문이 댓글에 없음 — 등록 중단(§3.1)"
    comment_id = None
    comment_pending = False
    # ⭐ 비공개(private) 영상은 유튜브가 댓글을 막는다(run129 검증) → 지금 달지 않고 '대기열'에 넣어
    #    공개된 뒤(예약공개 포함) 자동으로 단다(2026-07-19 사용자 확정: 비공개 예약 → 공개 후 자동 댓글).
    #    공개·일부공개면 지금 바로 단다(기존 동작 유지).
    if got_privacy in ("public", "unlisted"):
        try:
            comment_id = post_pinned_comment(video_id, pinned)
            print("[upload] 고지 댓글 등록 완료 (앱에서 '고정'만 눌러주세요)")
        except Exception as e:  # 댓글 실패는 업로드 자체를 무효화하지 않음 — 대기열로 넘겨 재시도
            emsg = str(e)
            print(f"[upload] 경고: 댓글 등록 실패({emsg}) — 대기열로 넘겨 공개 후 재시도")
            if "insufficient authentication scopes" in emsg or "ACCESS_TOKEN_SCOPE_INSUFFICIENT" in emsg:
                try:
                    from src import notify
                    notify.send(f"[{BRAND}] 고지 댓글 실패 — 유튜브 토큰에 '댓글 권한(youtube.force-ssl)'이 "
                                f"빠졌습니다. OAuth Playground에서 upload+force-ssl 두 권한을 승인해 토큰 "
                                f"재발급 후 SHORTS_YT_REFRESH_TOKEN 시크릿만 교체하세요.\n영상: {url}")
                except Exception:
                    pass
            comment_pending = True   # 다음 폴링에서 재시도
    else:
        comment_pending = True
        print(f"[upload] 비공개(privacy={got_privacy}) — 고지 댓글은 공개 후 자동 등록(대기열 추가)")

    return {"videoId": video_id, "url": url, "status": got_privacy,
            "comment_id": comment_id, "comment_pending": comment_pending,
            "pinned": pinned, "title": title}


# ── 비공개→공개 대기 고지 댓글 큐 (예약공개 후 자동 등록) ──────────────────────────
def _load_pending() -> list:
    if PENDING_PATH.exists():
        try:
            return json.loads(PENDING_PATH.read_text(encoding="utf-8")) or []
        except Exception:
            return []
    return []


def _save_pending(items: list) -> None:
    PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def queue_pending_comment(result: dict, product: dict) -> None:
    """업로드가 비공개여서 지금 못 단 고지 댓글을 대기열에 등록(공개되면 폴링이 자동으로 단다)."""
    import datetime
    vid = result.get("videoId")
    if not vid or not result.get("pinned"):
        return
    items = [e for e in _load_pending() if e.get("video_id") != vid]   # 같은 영상 중복 제거
    items.append({
        "video_id": vid, "row_hash": product.get("_row_hash", ""),
        "name": product.get("name", ""), "url": result.get("url", ""),
        "pinned": result["pinned"], "tries": 0,
        "queued_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    })
    _save_pending(items)
    print(f"[upload] 고지 댓글 대기열 등록 — 공개되면 자동 등록됩니다(대기 {len(items)}건)")


def process_pending_comments() -> dict:
    """대기열의 영상들을 확인해, 공개(예약공개 포함)된 것에 고지 댓글을 자동으로 단다.
    shorts-comments 워크플로가 주기적으로 호출. 반환: {posted, waiting, dropped}."""
    import datetime
    items = _load_pending()
    if not items:
        print("[comments] 대기 중인 고지 댓글 없음")
        return {"posted": 0, "waiting": 0, "dropped": 0}
    if not is_configured():
        print(f"[comments] 유튜브 인증 미설정 — {missing_hint()}")
        return {"posted": 0, "waiting": len(items), "dropped": 0}
    from src import notify
    now = datetime.datetime.now(datetime.timezone.utc)
    kept, posted, dropped = [], 0, 0
    for e in items:
        vid = e.get("video_id")
        # 14일 넘게 안 열린 건 만료 처리(예약을 안 잡았거나 취소) — 수동 확인 안내 후 드롭
        try:
            age_days = (now - datetime.datetime.fromisoformat(e.get("queued_at"))).days
        except Exception:
            age_days = 0
        if age_days >= 14:
            dropped += 1
            notify.send(f"[{BRAND}] '{e.get('name','')}' 고지 댓글 대기 14일 경과 — 공개 예약을 안 잡았거나 "
                        f"취소된 것 같습니다. 직접 확인해 주세요.\n{e.get('url','')}")
            continue
        try:
            status = get_privacy_status(vid)
        except Exception as ex:
            print(f"[comments] 상태조회 실패({vid}: {ex}) — 다음에 재시도")
            kept.append(e)
            continue
        if status is None:
            dropped += 1   # 삭제된 영상 — 조용히 제거
            continue
        if status in ("public", "unlisted"):
            try:
                post_pinned_comment(vid, e["pinned"])
                posted += 1
                notify.send(f"[{BRAND}] '{e.get('name','')}' 공개 확인 — 고지·링크 댓글을 자동으로 달았습니다. "
                            f"유튜브 앱에서 그 댓글 '고정'만 1탭 눌러주세요.\n{e.get('url','')}")
            except Exception as ex:
                e["tries"] = int(e.get("tries", 0)) + 1
                if e["tries"] >= 5:
                    dropped += 1
                    notify.send(f"[{BRAND}] '{e.get('name','')}' 고지 댓글 자동 등록 5회 실패 — 아래 내용을 "
                                f"직접 댓글로 달고 고정해 주세요.\n──댓글 내용──\n{e['pinned']}\n──────\n{e.get('url','')}")
                else:
                    print(f"[comments] 댓글 등록 실패({vid}: {ex}) — 재시도 예정({e['tries']}/5)")
                    kept.append(e)
        else:
            kept.append(e)   # 아직 비공개/예약 — 유지
    _save_pending(kept)
    print(f"[comments] 공개 영상 {posted}건 댓글 등록 / 대기 {len(kept)}건 / 정리 {dropped}건")
    return {"posted": posted, "waiting": len(kept), "dropped": dropped}
