"""소싱 ⑥ 유튜브 업로드 — 완성 쇼츠(릴리스 shorts-src-{hash})를 유튜브에 올린다.

대본(plan: 제목/설명/해시태그) + 확정 상품(어필리에이트 링크) → 기존 검증된 `src.upload.youtube`
모듈을 그대로 재사용한다(설명란 최상단 제휴 고지 강제 · 고정 해시태그 병합 · 비공개면 고지 댓글
대기열). **기본 privacy=private(2026-07-19 사용자 재확정)**: 비공개로 먼저 올리고 유튜브 스튜디오에서
예약공개 → 공개되면 shorts-comments cron이 고지·링크 댓글을 자동 등록한다.

영상 파일은 워크플로가 릴리스에서 내려받아 --video 로 넘긴다(로컬엔 없음)."""
from __future__ import annotations

import json
from pathlib import Path

from src.sourcing.models import PROJECT_ROOT
from src.sourcing.plan import load_plan
from src.sourcing.product_info import build_product_info


def _load_settings(root: Path) -> dict:
    import yaml
    return yaml.safe_load((Path(root) / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}


def _upload_result_path(root: Path, product_hash: str) -> Path:
    return Path(root) / "data" / "sources" / "upload" / f"{product_hash}.json"


def upload_sourced(product_hash: str, video_path, settings: dict | None = None,
                   project_root=None, privacy: str = "private", nonce: str = "") -> dict:
    """완성 소싱 쇼츠 유튜브 업로드 → 결과 dict. data/sources/upload/{hash}.json에 결과 기록(관리자 폴링)."""
    root = Path(project_root or PROJECT_ROOT)
    settings = settings or _load_settings(root)
    plan = load_plan(product_hash, root)
    if not plan or not plan.get("lines"):
        raise RuntimeError("대본(plan)이 없습니다 — ⑤ 제작을 먼저 하세요")
    video_path = Path(video_path)
    if not video_path.exists():
        raise RuntimeError(f"완성 영상이 없습니다: {video_path}")

    product = build_product_info(product_hash, base_dir=root / "data" / "sources")
    product["_row_hash"] = product_hash   # 고정 댓글·스토어 번호 매칭용(소싱은 스토어에 없으면 번호 생략)

    from src.upload import youtube
    if not youtube.is_configured():
        raise RuntimeError("유튜브 인증(SHORTS_YT_CLIENT_ID/SECRET/REFRESH_TOKEN)이 없습니다: " + youtube.missing_hint())
    # youtube.upload가 내부에서: 설명란 고지문 강제 + 해시태그 병합 + (비공개면 고지 댓글 대기열, 공개면 즉시 등록)
    result = youtube.upload(video_path, plan, product, settings, privacy=privacy)

    p = _upload_result_path(root, product_hash)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"hash": product_hash, "videoId": result.get("videoId"),
                             "url": result.get("url"), "status": result.get("status"),
                             "title": plan.get("title", ""), "nonce": nonce}, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    print("SRC_UPLOAD_RESULT:", json.dumps(
        {"status": "ok", "videoId": result.get("videoId"), "url": result.get("url"),
         "privacy": result.get("status")}, ensure_ascii=False))
    return result


def _main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="소싱 ⑥ 유튜브 업로드")
    ap.add_argument("--hash", required=True, help="상품 해시(plan/{hash}.json)")
    ap.add_argument("--video", required=True, help="릴리스에서 내려받은 완성 영상 경로")
    ap.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    ap.add_argument("--nonce", default="", help="관리자 폴링 신선도 매칭용")
    a = ap.parse_args(argv)
    upload_sourced(a.hash, a.video, privacy=a.privacy, nonce=a.nonce)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
