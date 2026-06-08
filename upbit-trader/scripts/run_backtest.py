#!/usr/bin/env python3
"""백테스트 실행 — 여러 전략을 같은 데이터로 비교합니다.

사용법:
    python scripts/run_backtest.py                 # 합성(데모) 데이터로 비교
    python scripts/run_backtest.py --csv data.csv  # 내 CSV 데이터로 비교

출력: 전략별 누적수익률 / 단순보유 대비 / 매매횟수 / 승률 / 최대낙폭
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest import run_backtest  # noqa: E402
from src.risk import apply_risk_management  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import STRATEGIES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="전략 백테스트 비교")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터 사용)")
    parser.add_argument("--stop-loss", type=float,
                        help="손절 비율 (예: 0.05 = -5%%에서 손절)")
    parser.add_argument("--take-profit", type=float,
                        help="익절 비율 (예: 0.10 = +10%%에서 익절)")
    args = parser.parse_args()

    if args.csv:
        df = load_csv(args.csv)
        source = f"CSV: {args.csv}"
    else:
        df = generate_synthetic_ohlcv()
        source = "합성(데모) 데이터 — 실제 시세 아님"

    print(f"데이터: {source}")
    print(f"기간: {df['datetime'].iloc[0].date()} ~ {df['datetime'].iloc[-1].date()}"
          f"  ({len(df)}일)")
    if args.stop_loss or args.take_profit:
        sl = f"{args.stop_loss*100:.0f}%" if args.stop_loss else "없음"
        tp = f"{args.take_profit*100:.0f}%" if args.take_profit else "없음"
        print(f"리스크 관리: 손절 {sl} / 익절 {tp}")
    print()

    header = f"{'전략':<22}{'누적수익':>10}{'단순보유':>10}{'매매':>6}{'승률':>8}{'최대낙폭':>10}"
    print(header)
    print("-" * len(header))

    for name, strategy_fn in STRATEGIES.items():
        positions = strategy_fn(df)
        if args.stop_loss or args.take_profit:
            positions = apply_risk_management(
                df, positions, args.stop_loss, args.take_profit
            )
        r = run_backtest(df, positions)
        print(
            f"{name:<22}"
            f"{r.total_return * 100:>9.1f}%"
            f"{r.buy_hold_return * 100:>9.1f}%"
            f"{r.num_trades:>6}"
            f"{r.win_rate * 100:>7.0f}%"
            f"{r.max_drawdown * 100:>9.1f}%"
        )

    print("\n해석:")
    print("  · '누적수익' > '단순보유' 이면 그냥 사서 들고 있는 것보다 나았다는 뜻")
    print("  · '최대낙폭'은 음수일수록 중간에 크게 물렸다는 의미 (작을수록 안정적)")
    if args.csv:
        print("  · ⚠️ 과거 데이터 기준이며 미래 수익을 보장하지 않습니다.")
    else:
        print("  · ⚠️ 합성 데이터 결과이므로 실제 수익을 보장하지 않습니다.")


if __name__ == "__main__":
    main()
