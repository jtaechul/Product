#!/usr/bin/env python3
"""모의매매 실행 — 가상 계좌로 전략을 돌리고 거래 일지를 출력합니다.

사용법:
    python scripts/paper_trade.py                       # 변동성 돌파 전략(기본)
    python scripts/paper_trade.py --strategy rsi        # RSI 전략
    python scripts/paper_trade.py --strategy ma         # 이동평균 교차
    python scripts/paper_trade.py --csv data.csv        # 내 데이터로
    python scripts/paper_trade.py --cash 5000000        # 시작 자금 변경
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.paper_trader import run_paper_trading  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import (  # noqa: E402
    ma_crossover,
    rsi_strategy,
    volatility_breakout,
)

STRATEGY_MAP = {
    "ma": ("이동평균 교차", ma_crossover),
    "rsi": ("RSI 과매도/과매수", rsi_strategy),
    "vb": ("변동성 돌파", volatility_breakout),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="모의매매 실행")
    parser.add_argument("--strategy", choices=STRATEGY_MAP, default="vb")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    parser.add_argument("--cash", type=float, default=1_000_000, help="시작 자금(원)")
    args = parser.parse_args()

    df = load_csv(args.csv) if args.csv else generate_synthetic_ohlcv()
    name, strategy_fn = STRATEGY_MAP[args.strategy]

    account = run_paper_trading(df, strategy_fn, initial_cash=args.cash)

    print(f"전략: {name}")
    print(f"시작 자금: {args.cash:,.0f}원")
    print(f"데이터: {'CSV ' + args.csv if args.csv else '합성(데모) 데이터'}\n")

    print("거래 일지:")
    if not account.trades:
        print("  (매매 신호가 발생하지 않았습니다)")
    for t in account.trades:
        print(
            f"  {t.datetime.date()}  {t.action:<4} "
            f"@ {t.price:>12,.0f}원   "
            f"총자산 {t.value_after:>14,.0f}원"
        )

    final_price = float(df["close"].iloc[-1])
    final_value = account.value(final_price)
    profit = final_value - args.cash
    ret = profit / args.cash * 100
    print("\n결과:")
    print(f"  최종 자산 : {final_value:,.0f}원")
    print(f"  손익      : {profit:+,.0f}원 ({ret:+.1f}%)")
    print(f"  매매 횟수 : {len(account.trades)}회")
    print("\n  ⚠️ 합성(데모) 데이터 기준입니다. 실제 수익을 보장하지 않습니다.")


if __name__ == "__main__":
    main()
