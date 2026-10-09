"""ig_publish — Instagram 릴스 자동 발행(콘텐츠 발행 API).

토큰(IG_ACCESS_TOKEN)으로 인스타그램 계정에 9:16 릴스를 올린다. 흐름:
  1) 토큰으로 IG 사용자 ID 자동 확인(resolve_ig_user_id) — 계정마다 API 경로가 달라
     graph.instagram.com(신 Instagram 로그인) → graph.facebook.com(연결된 페이지) 순으로 탐색.
  2) 컨테이너 생성(create_container): media_type=REELS + 공개 video_url + caption.
  3) 완료까지 폴링(wait_container) → 발행(publish_container).

probe(토큰) 는 발행 없이 '어느 API로, 어느 계정에 올릴 수 있는지'만 확인한다(안전 점검용).
비밀: 토큰은 인자로만 받는다(하드코딩·로그 노출 금지). 실패 시 명확한 예외.
"""
from __future__ import annotations

import json
import logging
import time

import requests

log = logging.getLogger(__name__)

# ★v24.0(2026-10-09): 시험 릴스 게시(trial_params)·「3초 안에 넘긴 비율」(reels_skip_rate)이 들어간 뒤의 버전으로 고정.
#   새 매개변수를 모르는 옛 버전은 그 값을 조용히 무시할 수 있다 → 시험 릴스가 일반 릴스(팔로워에게 보임)로 올라가는 사고 방지.
#   (옛 v21.0 은 2년 지원 기간이 끝나 가고, 버전 없는 graph.instagram.com 은 앱 기본 버전을 따른다)
_IG_BASE = "https://graph.instagram.com/v24.0"
_FB_BASE = "https://graph.facebook.com/v24.0"
_TIMEOUT = 30


class IGPublishError(RuntimeError):
    pass


def _mask(tok: str) -> str:
    return (tok[:6] + "…" + tok[-4:]) if tok and len(tok) > 12 else "(설정됨)"


def resolve_ig_user_id(token: str) -> tuple[str, str, str]:
    """(base_url, ig_user_id, username) 반환. 실패 시 IGPublishError.

    신 Instagram 로그인 계정은 graph.instagram.com/me 가 바로 IG 사용자 ID를 준다.
    구 방식(페이스북 페이지 연결)은 /me/accounts → instagram_business_account.
    """
    # ① 신 Instagram 로그인: graph.instagram.com/me
    try:
        r = requests.get(f"{_IG_BASE}/me",
                         params={"fields": "user_id,username", "access_token": token},
                         timeout=_TIMEOUT)
        if r.ok:
            d = r.json()
            uid = str(d.get("user_id") or d.get("id") or "")
            if uid:
                return _IG_BASE, uid, str(d.get("username", ""))
    except Exception as e:  # noqa: BLE001
        log.warning("[ig] graph.instagram.com/me 실패: %s", e)

    # ② 페이스북 페이지 연결 방식: /me/accounts → instagram_business_account
    try:
        r = requests.get(f"{_FB_BASE}/me/accounts",
                         params={"fields": "instagram_business_account{id,username}",
                                 "access_token": token}, timeout=_TIMEOUT)
        if r.ok:
            for page in r.json().get("data", []):
                iba = page.get("instagram_business_account")
                if iba and iba.get("id"):
                    return _FB_BASE, str(iba["id"]), str(iba.get("username", ""))
    except Exception as e:  # noqa: BLE001
        log.warning("[ig] /me/accounts 실패: %s", e)

    raise IGPublishError(
        "IG 사용자 ID를 확인하지 못했습니다. 토큰 권한(instagram_basic·instagram_content_publish) "
        "또는 계정 연결을 확인하세요. (토큰: %s)" % _mask(token))


def create_container(base: str, ig_id: str, video_url: str, caption: str,
                     token: str, trial: str | None = None) -> str:
    """릴스 컨테이너 생성 → creation_id(container id).
    trial: 시험 릴스(팔로워가 아닌 사람에게만 먼저 보임 · Meta 2025-12-03 추가 `trial_params`)의
    graduation_strategy — "MANUAL"(앱에서 직접 '모두에게 공유') 또는 "SS_PERFORMANCE"(성과가 좋으면 자동 공유)."""
    data = {"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": token}
    if trial:
        data["trial_params"] = json.dumps({"graduation_strategy": trial})
    r = requests.post(f"{base}/{ig_id}/media", data=data, timeout=_TIMEOUT)
    if not r.ok:
        raise IGPublishError(f"컨테이너 생성 실패({r.status_code}): {r.text[:300]}")
    cid = str(r.json().get("id", ""))
    if not cid:
        raise IGPublishError(f"컨테이너 ID 없음: {r.text[:300]}")
    return cid


def wait_container(base: str, container_id: str, token: str,
                   max_wait: int = 300, interval: int = 8) -> None:
    """컨테이너가 FINISHED 될 때까지 폴링. ERROR/EXPIRED면 예외."""
    waited = 0
    while waited < max_wait:
        r = requests.get(f"{base}/{container_id}",
                         params={"fields": "status_code,status", "access_token": token},
                         timeout=_TIMEOUT)
        if r.ok:
            code = r.json().get("status_code", "")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise IGPublishError(f"컨테이너 처리 실패: {r.text[:300]}")
        time.sleep(interval)
        waited += interval
    raise IGPublishError(f"컨테이너 처리 시간 초과({max_wait}s)")


def publish_container(base: str, ig_id: str, container_id: str, token: str) -> str:
    """컨테이너 발행 → 게시물 ID."""
    r = requests.post(f"{base}/{ig_id}/media_publish",
                      data={"creation_id": container_id, "access_token": token},
                      timeout=_TIMEOUT)
    if not r.ok:
        raise IGPublishError(f"발행 실패({r.status_code}): {r.text[:300]}")
    return str(r.json().get("id", ""))


def probe(token: str) -> dict:
    """발행 없이 '올릴 수 있는지'만 확인(안전 점검). {ok, base, ig_user_id, username}."""
    base, uid, username = resolve_ig_user_id(token)
    return {"ok": True, "base": base, "ig_user_id": uid, "username": username}


def diagnose(token: str) -> str:
    """토큰으로 각 엔드포인트를 실제 호출해 원인을 정밀 진단(발행 없음).

    어떤 경로가 왜 막히는지(토큰 종류·페이지 연결·권한)를 응답 본문 그대로 보여준다.
    """
    checks = [
        ("A graph.instagram.com/me (인스타로그인 토큰용)", f"{_IG_BASE}/me",
         {"fields": "user_id,username"}),
        ("B graph.facebook.com/me (페북 토큰 본인)", f"{_FB_BASE}/me",
         {"fields": "id,name"}),
        ("C /me/accounts→연결된 IG비즈계정(페이지연결 필요)", f"{_FB_BASE}/me/accounts",
         {"fields": "name,instagram_business_account{id,username}"}),
        ("D /me?accounts{instagram_business_account}", f"{_FB_BASE}/me",
         {"fields": "accounts{instagram_business_account{id,username}}"}),
        ("E /me/permissions (토큰 권한)", f"{_FB_BASE}/me/permissions", {}),
    ]
    out = []
    for label, url, params in checks:
        p = dict(params); p["access_token"] = token
        try:
            r = requests.get(url, params=p, timeout=_TIMEOUT)
            out.append(f"[{label}] HTTP {r.status_code}\n{r.text.replace(token, '***')[:350]}")
        except Exception as e:  # noqa: BLE001
            out.append(f"[{label}] 예외: {e}")
    return "\n\n".join(out)


def publish_reel(token: str, video_url: str, caption: str) -> dict:
    """릴스 1편 발행(전 과정). {post_id, ig_user_id, username}."""
    if not token:
        raise IGPublishError("IG_ACCESS_TOKEN 이 비어 있습니다.")
    if not video_url:
        raise IGPublishError("video_url 이 비어 있습니다(발행할 영상 없음).")
    base, ig_id, username = resolve_ig_user_id(token)
    log.info("[ig] 대상 계정 @%s (id=%s, base=%s)", username, ig_id, base)
    cid = create_container(base, ig_id, video_url, caption, token)
    log.info("[ig] 컨테이너 생성 %s — 처리 대기…", cid)
    wait_container(base, cid, token)
    post_id = publish_container(base, ig_id, cid, token)
    log.info("[ig] 발행 완료 post_id=%s", post_id)
    return {"post_id": post_id, "ig_user_id": ig_id, "username": username}


def media_info(base: str, media_id: str, token: str) -> dict:
    """게시물 주소(permalink)·시각 — 실패해도 빈 dict."""
    try:
        r = requests.get(f"{base}/{media_id}", params={"fields": "permalink,timestamp", "access_token": token},
                         timeout=_TIMEOUT)
        return r.json() if r.ok else {}
    except Exception:  # noqa: BLE001
        return {}


def publish_trial_reel(token: str, video_url: str, caption: str, strategy: str = "MANUAL") -> dict:
    """시험 릴스 1편 게시(팔로워가 아닌 사람에게만 먼저). {media_id, permalink, username, base}."""
    if not token:
        raise IGPublishError("IG_ACCESS_TOKEN 이 비어 있습니다.")
    base, ig_id, username = resolve_ig_user_id(token)
    cid = create_container(base, ig_id, video_url, caption, token, trial=strategy)
    wait_container(base, cid, token, max_wait=600)
    mid = publish_container(base, ig_id, cid, token)
    info = media_info(base, mid, token)
    log.info("[ig] 시험 릴스 게시 @%s media=%s", username, mid)
    return {"media_id": mid, "permalink": info.get("permalink", ""), "username": username, "base": base}


# 시험 릴스 비교 지표: 조회 · 도달 · 3초 안에 넘긴 비율(reels_skip_rate · Meta 2025-12-03 추가) · 평균 시청 시간
TRIAL_METRICS = ("views", "reach", "reels_skip_rate", "ig_reels_avg_watch_time")


def _metric_value(item: dict):
    vals = item.get("values")
    if vals:
        return (vals[0] or {}).get("value")
    return (item.get("total_value") or {}).get("value")


def media_insights(token: str, media_id: str, metrics=TRIAL_METRICS) -> dict:
    """게시물 지표 {metrics: {이름: 값}, errors: {이름: 이유}} — 한꺼번에 실패하면 지표마다 따로 물어 받을 수 있는 것만 모은다
    (새 지표는 계정·버전에 따라 아직 안 될 수 있음)."""
    base, _, _ = resolve_ig_user_id(token)

    def ask(ms):
        return requests.get(f"{base}/{media_id}/insights", params={"metric": ",".join(ms), "access_token": token},
                            timeout=_TIMEOUT)
    out, errors = {}, {}
    r = ask(metrics)
    if r.ok:
        for it in r.json().get("data", []):
            out[it.get("name")] = _metric_value(it)
    else:
        for m in metrics:
            r1 = ask([m])
            if r1.ok:
                for it in r1.json().get("data", []):
                    out[it.get("name")] = _metric_value(it)
            else:
                errors[m] = r1.text.replace(token, "***")[:200]
    return {"metrics": out, "errors": errors}


def build_caption(record: dict) -> str:
    """레코드 reels 에서 발행용 일본어 캡션(본문 + 해시태그) 조립."""
    re = record.get("reels", {})
    body = (re.get("caption") or "").strip()
    tags = " ".join(re.get("hashtags") or [])
    return (body + ("\n\n" + tags if tags else "")).strip()
