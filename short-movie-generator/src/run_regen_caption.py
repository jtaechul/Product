"""run_regen_caption — 콘텐츠 레코드의 '캡션+해시태그 문구'만 새로 뽑는다(영상 재제작 없음).

대시보드 '캡션 재생성'용. 영상·오디오·자막은 그대로 두고, 발행용 캡션(reels.caption)과
한국어 참고 번역(caption_ko), 해시태그(hashtags/hashtags_ko)만 rich_caption으로 다시 생성한다.
레코드에 저장된 종 정보(학명·수심·분포·서식지·fun_facts)를 그대로 사용하므로 카테고리 불문·
AI추천 종도 안전(카테고리 재조회로 KeyError 나지 않음). LLM 있으면 풍부, 없으면 서술식 폴백.

사용: python -m src.run_regen_caption --content-id 004
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.core import rich_caption
from src.core.contracts import SpeciesInfo

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

_CONTENT = Path(__file__).resolve().parents[1] / "content"


def _info_from_record(sp: dict) -> SpeciesInfo:
    return SpeciesInfo(
        scientific_name=sp.get("scientific_name", ""),
        common_name_ko=sp.get("common_name_ko", ""),
        common_name_en=sp.get("common_name_en", ""),
        depth_range_m=sp.get("depth_range_m", ""),
        distribution=sp.get("distribution", ""),
        habitat=sp.get("habitat", ""),
        diet=sp.get("diet", []),
        fun_facts=sp.get("fun_facts", []),
        sources=sp.get("sources", []),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="캡션+해시태그만 재생성(영상 유지)")
    ap.add_argument("--content-id", required=True)
    args = ap.parse_args()
    cid = "".join(ch for ch in args.content_id if ch.isdigit())[:3].zfill(3)
    p = _CONTENT / f"{cid}.json"
    if not p.exists():
        log.error("레코드 없음: %s", p)
        return 1
    rec = json.loads(p.read_text(encoding="utf-8"))
    re = rec.get("reels", {})
    sp = rec.get("species", {})
    info = _info_from_record(sp)

    # 레코드에 저장된 요소로 rich_caption 입력 재구성(영상 재제작 없이 캡션만)
    reveal = re.get("reveal_name", "")            # "和名 / 学名" 형태
    jp_name = (reveal.split("/")[0].strip() if "/" in reveal else reveal.strip()) \
        or sp.get("common_name_en", "")
    sci_name = sp.get("scientific_name", "")
    feature_line = re.get("reveal_fact", "")      # 일본어 특징 한 줄
    hook = re.get("hook", "")
    credit = (rec.get("source", {}) or {}).get("image_credit", "") \
        or (info.sources or ["Wikimedia Commons"])[0]
    tags = re.get("hashtags") or None
    tags_ko = re.get("hashtags_ko") or None

    rc = rich_caption.generate(
        info, jp_name, sci_name, feature_line, hook, "",
        hook_ko=re.get("hook_ko", ""), feature_ko="", credit=credit,
        default_tags=list(tags) if tags else None,
        default_tags_ko=list(tags_ko) if tags_ko else None)

    re["caption"] = rc["jp"]
    re["caption_ko"] = rc["ko"]
    re["hashtags"] = rc["tags"]
    re["hashtags_ko"] = rc["tags_ko"]
    rec["reels"] = re
    rec["updated_at"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("캡션 재생성 완료 ✅  #%s\n--- JP ---\n%s\n--- KO ---\n%s",
             cid, rc["jp"], rc["ko"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
