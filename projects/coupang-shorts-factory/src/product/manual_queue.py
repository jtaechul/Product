"""M2 폴백 — 수동 상품 큐 (data/products_manual.csv, 스펙 §M2 2안).

컬럼: product_name, price, key_specs(;구분), image_urls(;구분), affiliate_url, category
처리 완료 행은 data/processed.json에 해시로 기록(성공 업로드 시 CI가 커밋)해
cron 무개입 운영에서 같은 상품이 반복 제작되지 않게 한다.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "products_manual.csv"
STATE_PATH = PROJECT_ROOT / "data" / "processed.json"


class QueueEmpty(Exception):
    pass


def row_hash(row: dict) -> str:
    key = f"{row.get('product_name', '')}|{row.get('affiliate_url', '')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def load_rows() -> list:
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        # 링크만 등록한 행(상품명은 M2.5 비전 추출이 채움)도 유효 — 판단 기준은 제휴 링크 유무
        return [r for r in csv.DictReader(f) if (r.get("affiliate_url") or "").strip()]


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"done": []}


def pick(row_arg: str = "auto") -> dict:
    """row_arg: 'auto'(미처리 첫 행) 또는 1부터 시작하는 행 번호."""
    rows = load_rows()
    if not rows:
        raise QueueEmpty("products_manual.csv에 상품이 없습니다. 1행을 추가해 주세요.")

    if row_arg and row_arg != "auto":
        idx = int(row_arg) - 1
        if not (0 <= idx < len(rows)):
            raise QueueEmpty(f"행 {row_arg} 없음 (총 {len(rows)}행)")
        row = rows[idx]
    else:
        done = set(load_state().get("done", []))
        row = next((r for r in rows if row_hash(r) not in done), None)
        if row is None:
            raise QueueEmpty(f"큐의 {len(rows)}행이 모두 처리 완료 상태입니다. 새 상품을 추가하세요.")

    product = {
        "product_id": time.strftime("job_%Y%m%d") + "_" + row_hash(row)[:6],
        "name": (row.get("product_name") or "").strip(),
        "price": int(re.sub(r"[^\d]", "", row.get("price", "0")) or 0),
        "specs": [s.strip() for s in (row.get("key_specs") or "").split(";") if s.strip()],
        "image_urls": [u.strip() for u in (row.get("image_urls") or "").split(";") if u.strip()],
        "affiliate_url": (row.get("affiliate_url") or "").strip(),
        "category": (row.get("category") or "").strip(),
        "_row_hash": row_hash(row),
    }
    if not product["affiliate_url"]:
        raise QueueEmpty(f"'{product['name']}' 행에 affiliate_url이 없습니다.")
    return product


def mark_done(rhash: str) -> None:
    state = load_state()
    if rhash not in state["done"]:
        state["done"].append(rhash)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
