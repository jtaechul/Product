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
    """제작 성공분을 원장에 기록.

    ★같은 no가 이미 있고 **종이 다르면 실제 제작분으로 고쳐 쓴다**(운영자 확정 · 실사고 수정).
      예전에는 무조건 무시했다. 그래서 어떤 회차가 A로 기록된 뒤 실제로는 B가 제작되면
      (앞선 실행이 번호를 먼저 차지한 경우 등) 원장에 **A가 영원히 남고 B는 기록되지 않았다**.
      실측 어긋남: #27 원장 Rimicaris / 발행 Peltospira, #56 원장 Ctenophora / 발행 Aphyonidae,
      #59 원장 Vampire squid / 발행 Selachimorpha.
      결과는 두 가지 사고다 — ①실제로 만든 종이 '미제작'으로 남아 **또 만들어진다**(중복)
      ②만들지 않은 종이 '제작됨'으로 잠겨 후보에서 빠진다. 원장의 진실은 **발행 레코드**다.
      같은 종이면 그대로 둔다(중복 호출에 안전).
    """
    items = _load()
    for it in items:
        if int(it.get("no", 0)) != int(no):
            continue
        old = str(it.get("scientific_name", "")).strip().lower()
        new = str(scientific_name or "").strip().lower()
        if old == new:
            return
        log.warning("[catalog] No.%03d 기록 정정: %s → %s (실제 제작분 기준)",
                    no, it.get("scientific_name") or "?", scientific_name or "?")
        it.update({"common_name_ko": common_name_ko or "", "common_name_en": common_name_en or "",
                   "scientific_name": scientific_name or "", "date": date or it.get("date", "")})
        CATALOG.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
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
