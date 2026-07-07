"""run_ig_publish — 콘텐츠 레코드 1건을 인스타그램 릴스로 발행(또는 안전 점검).

사용:
  python -m src.run_ig_publish --content-id 004            # 실제 발행
  python -m src.run_ig_publish --content-id 004 --probe    # 발행 없이 계정 확인만

토큰은 환경변수 IG_ACCESS_TOKEN 에서만 읽는다(하드코딩·커밋 금지).
발행 성공 시 레코드의 reels.instagram(post_id·발행시각)을 갱신하고 status를 published로.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.core import ig_publish

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_CONTENT = Path(__file__).resolve().parents[1] / "content"


def _load(cid: str) -> tuple[Path, dict]:
    p = _CONTENT / f"{cid}.json"
    if not p.exists():
        raise SystemExit(f"레코드 없음: {p}")
    return p, json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="인스타그램 릴스 발행")
    ap.add_argument("--content-id", required=True, help="콘텐츠 id(3자리, 예: 004)")
    ap.add_argument("--probe", action="store_true", help="발행 없이 계정 확인만")
    args = ap.parse_args()

    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        log.error("IG_ACCESS_TOKEN 환경변수가 없습니다.")
        return 2

    cid = "".join(ch for ch in args.content_id if ch.isdigit())[:3].zfill(3)

    # 안전 점검: 발행 없이 어느 계정에 올릴 수 있는지만 확인
    if args.probe:
        try:
            info = ig_publish.probe(token)
        except ig_publish.IGPublishError as e:
            log.error("점검 실패: %s", e)
            return 1
        log.info("점검 성공 ✅  계정=@%s (id=%s)  API=%s",
                 info["username"], info["ig_user_id"], info["base"])
        return 0

    path, rec = _load(cid)
    video_url = (rec.get("media") or {}).get("video_url", "")
    caption = ig_publish.build_caption(rec)
    if not video_url:
        log.error("레코드 #%s 에 media.video_url 이 없습니다(영상 미업로드).", cid)
        return 1

    try:
        result = ig_publish.publish_reel(token, video_url, caption)
    except ig_publish.IGPublishError as e:
        log.error("발행 실패: %s", e)
        return 1

    rec.setdefault("reels", {})["instagram"] = {
        "post_id": result["post_id"], "username": result["username"],
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    rec["status"] = "published"
    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("발행 완료 ✅  @%s  post_id=%s", result["username"], result["post_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
