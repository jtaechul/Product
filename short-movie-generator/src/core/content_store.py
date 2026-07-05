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
                 scope: str = "all") -> str:
    """제작 성공분을 content/<id>.json에 기록(병합). scope로 갱신 범위 표시(caption/images/video/all).

    반환: 기록된 파일 경로(str).
    """
    p = record_path(base_dir, content_id)
    rec = load_record(base_dir, content_id) or {}
    rec.setdefault("id", str(content_id))
    rec.setdefault("created_at", _now_iso())
    rec["updated_at"] = _now_iso()
    rec["status"] = "published"
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
            "caption": caption.caption_body,
            "hashtags": list(caption.hashtags or []),
            "reveal_name": caption.reveal_name,
            "reveal_fact": caption.reveal_fact,
        })
    if scope in ("video", "images", "all"):
        reels["visualizer"] = visualizer
        reels["video_file"] = Path(video_file).name if video_file else reels.get("video_file", "")
    rec["reels"] = reels
    rec["source"] = {
        "image_credit": asset.credit_string,
        "info_sources": list(info.sources or []),
        "license": getattr(asset, "license", "") or "",
    }
    rec.setdefault("media", {})   # CI가 Release 업로드 후 채움(video_url/cover_url/source_image_url)
    rec.setdefault("post", None)  # 게시물(캐러셀) 파트 — 1번 기능에서 채움
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[content] 레코드 기록: %s (scope=%s)", p.name, scope)
    return str(p)


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
