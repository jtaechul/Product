"""content_store — 제작된 콘텐츠의 영구 레코드(`content/<id>.json`).

관리자 페이지(라이브러리·상세·편집·재생성)가 과거 콘텐츠를 다룰 수 있으려면, 매 제작 성공 시
종·훅·캡션·해시태그·자산 참조·상태를 '종당 JSON 1개'로 남겨야 한다(저장소 커밋 → 무료·버전관리).
영상/이미지 같은 미디어는 CI가 GitHub Release로 업로드하고 그 URL을 이 레코드의 media에 채운다.

원칙:
- 같은 id로 재생성되면 기존 레코드를 '병합'(created_at·post 등 보존, updated_at·해당 파트만 갱신).
- 이 모듈은 파일 I/O만 담당(카테고리 무관). 미디어 업로드는 CI(워크플로)가 수행.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

CONTENT_DIRNAME = "content"


def content_dir(base_dir: str = ".") -> Path:
    d = Path(base_dir) / CONTENT_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def record_path(base_dir: str, content_id: str) -> Path:
    return content_dir(base_dir) / f"{content_id}.json"


def next_global_id(base_dir: str = ".") -> int:
    """전 카테고리 공용 다음 콘텐츠 번호 = 기존 content/NNN.json 최대값 + 1(없으면 1).

    카테고리별 회차 번호를 콘텐츠 id로 쓰면 서로 다른 카테고리가 같은 번호(#001 등)를 써서
    content/001.json을 덮어쓰는 충돌이 생긴다. 콘텐츠 id는 전 카테고리 공용으로 매긴다.
    """
    d = content_dir(base_dir)
    mx = 0
    for p in d.glob("*.json"):
        if p.stem.isdigit():
            mx = max(mx, int(p.stem))
    return mx + 1


MANIFEST_NAME = "manifest.json"


def _manifest_path(base_dir: str):
    return content_dir(base_dir) / MANIFEST_NAME


def upsert_manifest(base_dir: str, entry: dict) -> None:
    """content/manifest.json 에 항목 upsert(id 기준). 대시보드가 이 '공개 목록 1파일'만 읽어
    라이브러리·최근목록을 그린다 → GitHub 디렉토리 API(비인증 403) 없이 어느 기기서든 조회 가능.
    """
    p = _manifest_path(base_dir)
    items = []
    if p.exists():
        try:
            items = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                items = []
        except Exception:  # noqa: BLE001
            items = []
    eid = str(entry.get("id", ""))
    items = [x for x in items if isinstance(x, dict) and str(x.get("id")) != eid]
    items.append(entry)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def rebuild_manifest(base_dir: str) -> int:
    """content/*.json 레코드 원본에서 manifest.json을 결정적으로 재생성. 반환: 항목 수.

    CI '레코드 커밋'이 manifest.json 리베이스 충돌로 5회 재시도 모두 실패 → 런 전체가
    실패 처리되던 사고(run #41)의 복구 장치: 충돌 시 이 함수로 레코드에서 목록을 다시
    만들어 리베이스를 잇는다(manifest는 레코드의 파생물이라 언제든 재생성 가능)."""
    base = Path(base_dir) / "content"
    items: list[dict] = []
    for p in sorted(base.glob("*.json")):
        if p.name == "manifest.json":
            continue
        try:
            rec = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(rec, dict):
            continue
        rid = str(rec.get("id") or p.stem)
        media = rec.get("media") or {}
        if rec.get("kind") == "longform":
            e = {"id": rid, "kind": "longform",
                 "yt_title": rec.get("yt_title", ""), "yt_title_ko": rec.get("yt_title_ko", ""),
                 "n": rec.get("n", 0), "total_s": rec.get("total_s", 0),
                 "date": str(rec.get("created_at", ""))[:10],
                 "has_video": bool(media.get("video_url"))}
        else:
            sp = rec.get("species") or {}
            e = {"id": rid, "kind": "reels",
                 "common_name_ko": sp.get("common_name_ko") or sp.get("common_name_en") or "종",
                 "common_name_en": sp.get("common_name_en", ""),
                 "scientific_name": sp.get("scientific_name", ""),
                 "date": str(rec.get("updated_at") or rec.get("created_at") or "")[:10]}
        if media.get("youtube_url"):
            e["youtube_url"] = media["youtube_url"]
        items.append(e)
    _manifest_path(base_dir).write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[content] manifest 재생성: %d항목", len(items))
    return len(items)


def load_record(base_dir: str, content_id: str) -> dict | None:
    p = record_path(base_dir, content_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_record(base_dir: str, content_id: str, *, info, caption, asset,
                 visualizer: str, video_file: str, series_title: str = "",
                 scope: str = "all", post: dict | None = None, category: str = "") -> str:
    """제작 성공분을 content/<id>.json에 기록(병합). scope로 갱신 범위 표시(caption/images/video/all).

    반환: 기록된 파일 경로(str).
    """
    p = record_path(base_dir, content_id)
    rec = load_record(base_dir, content_id) or {}
    rec.setdefault("id", str(content_id))
    rec.setdefault("created_at", _now_iso())
    rec["updated_at"] = _now_iso()
    rec["status"] = "published"
    if category:   # 재생성 시 워크플로가 이 값으로 카테고리를 복원(침몰선을 deep_sea로 오복원하던 사고 방지)
        rec["category"] = category
    rec["series"] = series_title or rec.get("series", "")
    rec["species"] = {
        "common_name_ko": info.common_name_ko,
        "common_name_en": info.common_name_en,
        "scientific_name": info.scientific_name,
        "depth_range_m": info.depth_range_m,
        "habitat": info.habitat,
        "distribution": info.distribution,
        "diet": list(info.diet or []),
        "fun_facts": list(info.fun_facts or []),
    }
    # 릴스 파트(캡션/영상)는 scope에 따라 갱신. caption만 재생성 시 영상 참조는 보존.
    reels = rec.get("reels", {})
    if scope in ("caption", "all"):
        reels.update({
            "hook": caption.hook_text,
            "caption": caption.caption_body,                       # 일본어(발행문)
            "hashtags": list(caption.hashtags or []),
            "reveal_name": caption.reveal_name,
            "reveal_fact": caption.reveal_fact,
            # 한국어 참고 번역(분리 필드) — 대시보드 좌(일)/우(한) 2단 표시용
            "hook_ko": getattr(caption, "hook_ko", "") or "",
            "caption_ko": getattr(caption, "caption_ko", "") or "",
            "hashtags_ko": list(getattr(caption, "hashtags_ko", []) or []),
            # 유튜브 쇼츠 제목(일/한) — 시스템 생성(호기심 갭+종명+#Shorts), 대시보드 표시·편집용
            "yt_title": getattr(caption, "yt_title", "") or "",
            "yt_title_ko": getattr(caption, "yt_title_ko", "") or "",
        })
    if scope in ("video", "images", "all"):
        reels["visualizer"] = visualizer
        reels["video_file"] = Path(video_file).name if video_file else reels.get("video_file", "")
    rec["reels"] = reels
    rec["source"] = {
        "image_credit": getattr(asset, "credit_string", "") or "",  # reels는 영상(asset=None) → 빈값
        "info_sources": list(info.sources or []),
        "license": getattr(asset, "license", "") or "",
    }
    rec.setdefault("media", {})   # CI가 Release 업로드 후 채움(video_url/cover_url/source_image_url)
    # 게시물(캐러셀) 파트 — scope가 게시물에 영향줄 때만 갱신(video 재생성 시 보존)
    if post is not None and scope in ("all", "images", "caption"):
        rec["post"] = post
    else:
        rec.setdefault("post", None)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_manifest(base_dir, {
        "id": str(content_id), "kind": "reels",
        "common_name_ko": info.common_name_ko or info.common_name_en or "종",
        "common_name_en": info.common_name_en or "",
        "scientific_name": info.scientific_name or "",
        "date": rec.get("updated_at", "")[:10],
    })
    log.info("[content] 레코드 기록: %s (scope=%s)", p.name, scope)
    return str(p)


def write_longform_record(base_dir: str, content_id: str, meta: dict, *,
                          video_url: str = "", cover_url: str = "") -> str:
    """롱폼(랭킹형 TOP N) 결과 레코드 content/<id>.json 기록.

    쇼츠 레코드(단일 종 중심)와 스키마가 달라 kind="longform"으로 구분. 대시보드가
    이 필드로 제목·설명(일/한, 타임스탬프 포함)을 2단 프레임에 보여준다.
    """
    p = record_path(base_dir, content_id)
    rec = {
        "id": str(content_id), "kind": "longform", "created_at": _now_iso(),
        "status": "published", "theme": meta.get("theme", ""),
        "yt_title": meta.get("yt_title", ""), "yt_title_ko": meta.get("yt_title_ko", ""),
        "yt_description": meta.get("yt_description", ""),
        "yt_description_ko": meta.get("yt_description_ko", ""),
        "chapters": meta.get("chapters", ""), "chapters_ko": meta.get("chapters_ko", ""),
        "hashtags": meta.get("hashtags", []), "hashtags_ko": meta.get("hashtags_ko", []),
        "n": meta.get("n", 0), "total_s": meta.get("total_s", 0),
        "sources": meta.get("sources", []),
        "media": {"video_url": video_url, "cover_url": cover_url},
    }
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_manifest(base_dir, {
        "id": str(content_id), "kind": "longform",
        "yt_title": meta.get("yt_title", ""), "yt_title_ko": meta.get("yt_title_ko", ""),
        "n": meta.get("n", 0), "total_s": meta.get("total_s", 0),
        "date": rec.get("created_at", "")[:10], "has_video": bool(video_url),
    })
    log.info("[content] 롱폼 레코드 기록: %s", p.name)
    return str(p)


def write_narrate_record(base_dir: str, content_id: str, meta: dict, *,
                         mode: str = "shorts", video_url: str = "",
                         thumb_url: str = "", source_url: str = "") -> str:
    """첨부 영상 나레이션 결과 레코드 content/<id>.json (kind="narrate").

    대본에서 자동 생성한 훅·제목·설명·해시태그를 일본어/한국어 2단으로 보관 + 유튜브
    커스텀 썸네일 URL. 대시보드가 /nv/<id> 상세에서 영상·썸네일 미리보기와 함께 보여준다."""
    p = record_path(base_dir, content_id)
    rec = {
        "id": str(content_id), "kind": "narrate", "created_at": _now_iso(),
        "status": "published", "mode": mode, "source_url": source_url,
        "hook": meta.get("hook_jp", ""),
        "yt_title": meta.get("title_jp", ""), "yt_title_ko": meta.get("title_ko", ""),
        "yt_description": meta.get("desc_jp", ""), "yt_description_ko": meta.get("desc_ko", ""),
        "hashtags": meta.get("tags_jp", []), "hashtags_ko": meta.get("tags_ko", []),
        "media": {"video_url": video_url, "thumb_url": thumb_url},
    }
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_manifest(base_dir, {
        "id": str(content_id), "kind": "narrate",
        "yt_title": meta.get("title_jp", ""), "yt_title_ko": meta.get("title_ko", ""),
        "mode": mode, "date": rec.get("created_at", "")[:10], "has_video": bool(video_url),
    })
    log.info("[content] 나레이션 레코드 기록: %s", p.name)
    return str(p)


def regen_longform_text(base_dir: str, content_id: str, scope: str = "all") -> bool:
    """롱폼 레코드의 제목·설명·해시태그(일/한)를 다시 도출해 부분 갱신(영상 재렌더 없음).

    scope: all(전체) / title(제목만) / desc(설명만) / hashtags(해시태그만).
    과거에 만든 롱폼(해시태그 필드가 빈 레코드 등)을 영상 재제작 없이 텍스트만 새로 채운다.
    """
    from src.run_longform import rebuild_meta_from_record
    rec = load_record(base_dir, content_id)
    if not rec or rec.get("kind") != "longform":
        return False
    text = rebuild_meta_from_record(rec)
    if not text:
        return False
    sc = (scope or "all").lower()
    if sc in ("all", "title"):
        rec["yt_title"] = text["yt_title"]; rec["yt_title_ko"] = text["yt_title_ko"]
    if sc in ("all", "desc", "description"):
        rec["yt_description"] = text["yt_description"]
        rec["yt_description_ko"] = text["yt_description_ko"]
    if sc in ("all", "hashtags", "tags"):
        rec["hashtags"] = text["hashtags"]; rec["hashtags_ko"] = text["hashtags_ko"]
    rec["updated_at"] = _now_iso()
    record_path(base_dir, content_id).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_manifest(base_dir, {
        "id": str(content_id), "kind": "longform",
        "yt_title": rec.get("yt_title", ""), "yt_title_ko": rec.get("yt_title_ko", ""),
        "n": rec.get("n", 0), "total_s": rec.get("total_s", 0),
        "date": str(rec.get("created_at", ""))[:10],
        "has_video": bool((rec.get("media") or {}).get("video_url")),
    })
    log.info("[content] 롱폼 텍스트 재생성: %s (scope=%s)", content_id, sc)
    return True


def set_longform_youtube(base_dir: str, content_id: str, *, youtube_url: str,
                         privacy: str = "") -> bool:
    """롱폼 레코드에 유튜브 업로드 결과(URL·공개범위)를 기록 + 매니페스트 갱신.

    운영자가 대시보드에서 '유튜브에 올리기'를 눌러 upload-longform.yml 이 업로드에 성공한 뒤 호출.
    대시보드는 이 값을 보고 '이미 업로드됨(재업로드 방지)'을 표시한다.
    """
    rec = load_record(base_dir, content_id)
    if not rec or rec.get("kind") != "longform":
        return False
    media = rec.setdefault("media", {})
    media["youtube_url"] = youtube_url
    media["youtube_privacy"] = privacy
    rec["updated_at"] = _now_iso()
    record_path(base_dir, content_id).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    upsert_manifest(base_dir, {
        "id": str(content_id), "kind": "longform",
        "yt_title": rec.get("yt_title", ""), "yt_title_ko": rec.get("yt_title_ko", ""),
        "n": rec.get("n", 0), "total_s": rec.get("total_s", 0),
        "date": str(rec.get("created_at", ""))[:10],
        "has_video": bool((rec.get("media") or {}).get("video_url")),
        "youtube_url": youtube_url,
    })
    return True


def set_short_youtube(base_dir: str, content_id: str, *, youtube_url: str,
                      privacy: str = "") -> bool:
    """쇼츠(릴스) 레코드에 유튜브 업로드 결과(URL·공개범위) 기록 + 매니페스트 갱신.

    운영자가 라이브러리 상세(/c/<id>)에서 '유튜브 쇼츠로 올리기'를 눌러 upload-short.yml 이
    업로드에 성공한 뒤 호출. 대시보드는 이 값을 보고 '이미 업로드됨(재업로드 방지)'을 표시한다.
    """
    rec = load_record(base_dir, content_id)
    if not rec or rec.get("kind") == "longform":
        return False
    media = rec.setdefault("media", {})
    media["youtube_url"] = youtube_url
    media["youtube_privacy"] = privacy
    rec["updated_at"] = _now_iso()
    record_path(base_dir, content_id).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    sp = rec.get("species", {}) or {}
    upsert_manifest(base_dir, {
        "id": str(content_id), "kind": "reels",
        "common_name_ko": sp.get("common_name_ko") or sp.get("common_name_en") or "종",
        "common_name_en": sp.get("common_name_en", ""),
        "scientific_name": sp.get("scientific_name", ""),
        "date": str(rec.get("updated_at") or rec.get("created_at", ""))[:10],
        "youtube_url": youtube_url,
    })
    return True


def update_caption(base_dir: str, content_id: str, *, caption_body: str | None = None,
                   hashtags: list[str] | None = None, hook: str | None = None) -> bool:
    """캡션/해시태그/훅 텍스트 편집(경량, 재생성 없음). 로컬 편집·테스트용."""
    rec = load_record(base_dir, content_id)
    if not rec:
        return False
    reels = rec.setdefault("reels", {})
    if caption_body is not None:
        reels["caption"] = caption_body
    if hashtags is not None:
        reels["hashtags"] = hashtags
    if hook is not None:
        reels["hook"] = hook
    rec["updated_at"] = _now_iso()
    record_path(base_dir, content_id).write_text(
        json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
