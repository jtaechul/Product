#!/usr/bin/env python3
"""실행 결과 점검(0원): 운영 안내(운영시간·정비·요금·전화·몇 층 …)가 특장점 자리에 새지 않았는지 — 2026-10-20 운영자 "저런 게 다시는 특장점으로 들어가지 않도록".
쓰는 법: python3 scripts/check_facts.py [report.json]  (기본 data/runs/latest/report.json)
본다: 시그니처 근거 · 나레이션 문장의 근거 사실 · 특장점 라벨 · 요약 카드 답 · 캡션(첫 줄·포인트) · 체크리스트. 새면 줄마다 '새어 나감' 으로 적고 종료 코드 1."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import make_sig as sg  # noqa: E402

CAP_NIDA = sg.CAP_ENDING_RX


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "runs" / "latest" / "report.json"
    r = json.loads(path.read_text(encoding="utf-8"))
    leaks = []
    sig = r.get("signature") or {}
    if sig.get("fact") and sg.is_trivia(sig["fact"]):
        leaks.append(f"시그니처 근거: {sig['fact']}")
    for c in (r.get("script") or {}).get("cuts") or []:
        if c.get("fact") and sg.is_trivia(c["fact"]):
            leaks.append(f"문장 {c.get('i') or '?'} 근거: {c['fact']}")
        if c.get("narration") and sg.TRIVIA_RX.search(str(c["narration"])):
            leaks.append(f"문장 {c.get('i') or '?'} 나레이션: {c['narration']}")
    for f in ((r.get("features") or {}).get("items") or []):
        if sg.TRIVIA_RX.search(str(f.get("text") or "")):
            leaks.append(f"특장점 라벨: {f['text']}")
    for a in ((r.get("card") or {}).get("answers") or []):
        if sg.TRIVIA_RX.search(str(a.get("text") or "")):
            leaks.append(f"요약 카드 답: {a['text']}")
    cap = (r.get("script") or {}).get("caption") or {}
    for t in [cap.get("hook") or "", *(cap.get("points") or []), cap.get("save") or ""]:
        if t and sg.TRIVIA_RX.search(str(t)):
            leaks.append(f"캡션: {t}")
        if t and CAP_NIDA.search(str(t)):
            leaks.append(f"캡션 '~니다': {t}")
    for t in (r.get("script") or {}).get("checklist") or []:
        if sg.TRIVIA_RX.search(str(t)):
            leaks.append(f"체크리스트: {t}")
    trivia_pool = r.get("facts_trivia") or []
    print(f"점검: {path.name} · 숙소 {r.get('stay')} · 운영 안내 사실(인용 금지) {len(trivia_pool)}개")
    for t in trivia_pool[:8]:
        print("   -", t)
    if leaks:
        print(f"새어 나감 {len(leaks)}곳:")
        for x in leaks:
            print("   !", x)
        return 1
    print("통과 — 특장점·문장·캡션·체크리스트·카드·라벨 어디에도 운영 안내 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
