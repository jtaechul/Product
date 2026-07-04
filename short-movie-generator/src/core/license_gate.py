"""라이선스 게이트 (spec 12장) — 절대 규칙: 통과 라이선스만 시각화 이후로 전달.

통과: public-domain / cc0 / cc-by / kogl-type1
차단: cc-by-nc / cc-by-sa / cc-by-nc-sa / unknown / null(None)
NOAA 예외: 캡션에 'copyright' 표기가 있으면 차단.
"""
from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path

from src.core.contracts import ALLOWED_LICENSES, ApprovedAsset, RawAsset

log = logging.getLogger(__name__)


def evaluate(asset: RawAsset) -> tuple[bool, str]:
    """단일 에셋 판정. (통과 여부, 사유) 반환."""
    lic = (asset.license or "").strip().lower()
    if not lic:
        return False, "라이선스 불명(null) → 차단"
    if lic not in ALLOWED_LICENSES:
        return False, f"차단 라이선스: {lic}"
    # NOAA 예외 규칙: 캡션에 copyright 표기 → 3자 저작권 포함 가능성 → 차단
    if "copyright" in (asset.caption_text or "").lower():
        return False, "NOAA 캡션에 copyright 표기 → 차단"
    return True, f"통과 라이선스: {lic}"


def filter_assets(assets: list[RawAsset], approved_dir: str) -> list[ApprovedAsset]:
    """통과분만 assets/approved/ 로 복사하고 메타를 남긴다. 차단분은 절대 전달하지 않는다."""
    out_dir = Path(approved_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    approved: list[ApprovedAsset] = []

    for asset in assets:
        ok, reason = evaluate(asset)
        if not ok:
            log.warning("차단: %s (%s)", asset.asset_path, reason)
            continue
        src = Path(asset.asset_path)
        dst = out_dir / src.name
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        # 에셋 메타 필수 필드 (spec 10장)
        meta = {
            "source": asset.source,
            "license": asset.license,
            "credit_string": asset.credit_string,
            "source_url": asset.source_url,
            "license_ok": True,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        dst.with_suffix(dst.suffix + ".json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("통과: %s (%s)", dst, reason)
        approved.append(
            ApprovedAsset(
                asset_path=str(dst),
                license_ok=True,
                credit_string=asset.credit_string,
                source=asset.source,
                license=asset.license or "",
            )
        )
    return approved
