"""deep_sea 도감 번호 원장 — 제작된 종을 순서대로 누적 기록(엔트리 No.가 안정적으로 증가).

문제: 기존 회차 번호는 output/*.json 개수로 셌는데, CI(깃허브 액션)는 매 실행마다 컨테이너가
새로 생겨 output/이 비어 있어 항상 1로 리셋됐다(번호가 누적 안 됨).

해결: 커밋되는 원장 파일(catalog.json)에 제작 성공분을 append → 다음 실행이 이어받아 증가.
번호(no)는 1부터 순차. 국문명·영문명·학명·날짜를 함께 저장해 제작 페이지 현황판이
"#000_국문명" 형태로 보여줄 수 있게 한다. CI가 catalog.json을 커밋해 영속화한다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CATALOG = Path(__file__).resolve().parent / "catalog.json"


def _load() -> list[dict]:
    if CATALOG.exists():
        try:
            data = json.loads(CATALOG.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:  # noqa: BLE001
            return []
    return []


def peek_next() -> int:
    """다음에 부여될 도감 번호(읽기 전용). 최대 no + 1, 비어 있으면 1."""
    items = _load()
    return (max((int(it.get("no", 0)) for it in items), default=0) + 1) if items else 1


def log_entry(no: int, common_name_ko: str, common_name_en: str,
              scientific_name: str = "", date: str = "") -> None:
    """제작 성공분을 원장에 append (같은 no가 이미 있으면 덮어쓰지 않고 무시)."""
    items = _load()
    if any(int(it.get("no", 0)) == int(no) for it in items):
        return
    items.append({
        "no": int(no),
        "common_name_ko": common_name_ko or "",
        "common_name_en": common_name_en or "",
        "scientific_name": scientific_name or "",
        "date": date or "",
    })
    items.sort(key=lambda it: int(it.get("no", 0)))
    CATALOG.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[catalog] No.%03d %s 기록", no, common_name_ko)
