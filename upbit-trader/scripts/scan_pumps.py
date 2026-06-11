#!/usr/bin/env python3
"""잠수함 알트코인 급등 스캐너 CLI (1단계).

업비트 전체 KRW 마켓을 5분봉으로 훑어, 급등 조짐 코인을 점수순으로 출력합니다.
실제 주문은 전혀 하지 않습니다 — 조회/분석만 합니다.

사용법:
    python -m scripts.scan_pumps                 # 전체 스캔, 상위 20개
    python -m scripts.scan_pumps --top 10        # 상위 10개만
    python -m scripts.scan_pumps --min-value 5   # 24h 거래대금 5억원 이상만
    python -m scripts.scan_pumps --limit 30      # 마켓 30개만 (빠른 테스트)
    python -m scripts.scan_pumps --watch 60      # 60초마다 반복 스캔
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scanner import scan  # noqa: E402


def _fmt_won(value: float) -> str:
    """원 단위 거래대금을 읽기 쉽게(억/만) 축약."""
    if value >= 1e8:
        return f"{value / 1e8:.0f}억"
    if value >= 1e4:
        return f"{value / 1e4:.0f}만"
    return f"{value:.0f}"


def print_table(candidates) -> None:
    if not candidates:
        print("  (조건을 만족하는 후보가 없습니다)")
        return

    header = (
        f"  {'순위':<4}{'마켓':<12}{'점수':>6} {'거래량배수':>9}"
        f"{'돌파%':>8}{'15분%':>8}{'잠수함':>7}{'24h대금':>9}  신호"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for rank, c in enumerate(candidates, 1):
        signal = "🚀 급등조짐" if c.is_signal else ""
        print(
            f"  {rank:<4}{c.market:<12}{c.score:>6.1f} "
            f"{c.vol_surge:>8.1f}x{c.breakout * 100:>7.1f}{c.momentum_15m * 100:>8.1f}"
            f"{c.dormancy:>7.2f}{_fmt_won(c.trade_value_24h):>9}  {signal}"
        )


def run_once(args) -> None:
    started = datetime.now()
    print(f"\n[{started:%H:%M:%S}] 스캔 시작 — {args.unit}분봉, "
          f"24h 거래대금 {args.min_value:g}억원 이상"
          + (f", 마켓 {args.limit}개 제한" if args.limit else ""))

    scanned = {"n": 0, "total": 0}

    def on_progress(i, total, market):
        scanned["n"], scanned["total"] = i, total
        print(f"\r  스캔 중... {i}/{total}  {market:<12}", end="", flush=True)

    candidates = scan(
        unit=args.unit,
        count=args.count,
        top=args.top,
        min_trade_value_24h=args.min_value * 1e8,
        market_limit=args.limit,
        pause=args.pause,
        on_progress=on_progress,
    )
    elapsed = (datetime.now() - started).total_seconds()
    print(f"\r  {scanned['total']}개 마켓 스캔 완료 ({elapsed:.0f}초)"
          + " " * 20)
    print()
    print_table(candidates)
    print("\n  ※ 점수는 휴리스틱입니다. '급등조짐'도 이미 늦은 진입일 수 있으니"
          " 모의로 충분히 검증하세요.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="잠수함 알트코인 급등 스캐너")
    parser.add_argument("--unit", type=int, default=5,
                        help="스캔용 분봉 단위(기본 5분봉)")
    parser.add_argument("--count", type=int, default=120,
                        help="종목당 가져올 캔들 수(기본 120 ≈ 10시간)")
    parser.add_argument("--top", type=int, default=20, help="출력할 상위 N개")
    parser.add_argument("--min-value", type=float, default=1.0,
                        dest="min_value",
                        help="24h 거래대금 하한(억원, 기본 1억). 작을수록 잡코인 포함")
    parser.add_argument("--limit", type=int, default=None,
                        help="스캔할 마켓 수 상한(테스트용)")
    parser.add_argument("--pause", type=float, default=0.1,
                        help="API 호출 간 대기(초, rate limit 배려)")
    parser.add_argument("--watch", type=int, default=0,
                        help="N초마다 반복 스캔(0이면 1회만)")
    args = parser.parse_args()

    try:
        if args.watch > 0:
            print(f"🔁 {args.watch}초마다 반복 스캔합니다. 중지: Ctrl+C")
            while True:
                run_once(args)
                time.sleep(args.watch)
        else:
            run_once(args)
    except KeyboardInterrupt:
        print("\n사용자 중지(Ctrl+C).")


if __name__ == "__main__":
    main()
