#!/usr/bin/env python3
"""손절/익절 조합 비교 — 같은 전략에 다양한 손절·익절을 적용해 효과를 봅니다.

목적: 최대낙폭(MDD)이 너무 클 때, 손절/익절로 얼마나 줄일 수 있는지(수익은 얼마나
      희생되는지) 트레이드오프를 한눈에 비교합니다.

사용법:
    python scripts/risk_compare.py --csv data/btc.csv
    python scripts/risk_compare.py --csv data/btc.csv --strategy macd
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest import run_backtest  # noqa: E402
from src.risk import apply_risk_management  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import (  # noqa: E402
    bollinger_bands,
    ma_crossover,
    macd,
    rsi_strategy,
    volatility_breakout,
)

STRATEGY_MAP = {
    "vb": ("변동성 돌파", volatility_breakout),
    "macd": ("MACD", macd),
    "ma": ("이동평균 교차", ma_crossover),
    "rsi": ("RSI", rsi_strategy),
    "bb": ("볼린저밴드", bollinger_bands),
}

# 검증 통과 전략을 기본 비교 대상으로
DEFAULT_STRATEGIES = ["vb", "macd"]

# 시험할 손절/익절 조합 (None = 미적용)
STOP_LOSSES = [None, 0.05, 0.10, 0.15, 0.20]
TAKE_PROFITS = [None, 0.30, 0.50]


def main() -> None:
    parser = argparse.ArgumentParser(description="손절/익절 조합 비교")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    parser.add_argument("--strategy", choices=STRATEGY_MAP,
                        help="특정 전략만 (생략 시 검증 통과 전략들)")
    args = parser.parse_args()

    df = load_csv(args.csv) if args.csv else generate_synthetic_ohlcv()
    targets = [args.strategy] if args.strategy else DEFAULT_STRATEGIES

    print(f"데이터: {'CSV ' + args.csv if args.csv else '합성(데모)'}  ({len(df)}일)\n")

    for key in targets:
        name, fn = STRATEGY_MAP[key]
        base_positions = fn(df)
        print(f"=== {name} — 손절/익절 조합별 결과 ===")
        print(f"{'손절':>6}{'익절':>6}{'누적수익':>12}{'최대낙폭':>12}{'매매':>6}")
        print("-" * 44)
        for sl in STOP_LOSSES:
            for tp in TAKE_PROFITS:
                pos = apply_risk_management(df, base_positions, sl, tp)
                r = run_backtest(df, pos)
                sl_s = f"{sl*100:.0f}%" if sl else "-"
                tp_s = f"{tp*100:.0f}%" if tp else "-"
                print(f"{sl_s:>6}{tp_s:>6}"
                      f"{r.total_return*100:>11.1f}%{r.max_drawdown*100:>11.1f}%"
                      f"{r.num_trades:>6}")
        print()

    print("읽는 법: 맨 윗줄(손절-/익절-)이 '리스크관리 없음' 기준선입니다.")
    print("  손절을 넣으면 보통 최대낙폭이 줄지만, 수익도 함께 깎일 수 있어요.")
    print("  '낙폭은 확 줄면서 수익은 덜 깎이는' 조합이 좋은 균형점입니다.")


if __name__ == "__main__":
    main()
