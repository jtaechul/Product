#!/usr/bin/env python3
"""Walk-forward 검증 — 가장 엄격한 과최적화 점검.

방법(구간을 굴려가며 반복):
  [학습 2년] → [검증 6개월] 으로 한 세트 검증하고, 6개월씩 앞으로 굴리며 반복.
  매 세트마다 '학습 구간에서 찾은 최적 파라미터'를 '처음 보는 다음 6개월'에 적용합니다.
  → 여러 시점에서 일관되게 통하는 전략만 살아남습니다.

사용법:
    python scripts/walkforward.py --csv data/btc.csv
    python scripts/walkforward.py --csv data/btc.csv --train 730 --test 180
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest import run_backtest  # noqa: E402
from src.optimize import optimize_strategy  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import (  # noqa: E402
    bollinger_bands,
    ma_crossover,
    macd,
    rsi_strategy,
    volatility_breakout,
)

CONFIGS = [
    ("이동평균 교차", ma_crossover,
     {"short": [3, 5, 10, 20], "long": [20, 30, 60, 120]},
     lambda p: p["short"] < p["long"]),
    ("RSI", rsi_strategy,
     {"period": [7, 14, 21], "low": [20, 25, 30], "high": [70, 75, 80]}, None),
    ("변동성 돌파", volatility_breakout, {"k": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]}, None),
    ("볼린저밴드", bollinger_bands,
     {"period": [10, 20, 30], "num_std": [1.5, 2.0, 2.5]}, None),
    ("MACD", macd, {"fast": [8, 12], "slow": [21, 26], "signal": [9]},
     lambda p: p["fast"] < p["slow"]),
]


def walk_forward(df, fn, grid, valid, train: int, test: int):
    """구간을 굴리며 검증. fold별 검증수익 리스트 반환."""
    returns = []
    i = 0
    while i + train + test <= len(df):
        tr = df.iloc[i:i + train].reset_index(drop=True)
        te = df.iloc[i + train:i + train + test].reset_index(drop=True)
        best_params, _ = optimize_strategy(tr, fn, grid, valid=valid)[0]
        r = run_backtest(te, fn(te, **best_params))
        returns.append(r.total_return)
        i += test
    return returns


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward 검증")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    parser.add_argument("--train", type=int, default=730, help="학습 구간 일수")
    parser.add_argument("--test", type=int, default=180, help="검증 구간 일수")
    args = parser.parse_args()

    df = load_csv(args.csv) if args.csv else generate_synthetic_ohlcv()
    print(f"데이터: {'CSV ' + args.csv if args.csv else '합성(데모)'} ({len(df)}일)")
    print(f"학습 {args.train}일 → 검증 {args.test}일, {args.test}일씩 전진\n")

    header = f"{'전략':<14}{'세트수':>6}{'수익세트':>8}{'누적(복리)':>12}{'평균/세트':>10}"
    print(header)
    print("-" * len(header))

    for name, fn, grid, valid in CONFIGS:
        rets = walk_forward(df, fn, grid, valid, args.train, args.test)
        if not rets:
            print(f"{name:<14} (데이터 부족)")
            continue
        wins = sum(1 for r in rets if r > 0)
        compound = 1.0
        for r in rets:
            compound *= (1 + r)
        compound -= 1
        avg = sum(rets) / len(rets)
        verdict = "✅" if wins / len(rets) >= 0.5 and compound > 0 else "⚠️"
        print(f"{name:<14}{len(rets):>6}{f'{wins}/{len(rets)}':>8}"
              f"{compound*100:>11.1f}%{avg*100:>9.1f}%  {verdict}")

    print("\n해석:")
    print("  · '수익세트': 검증 구간 중 플러스를 낸 비율 (높을수록 일관적)")
    print("  · '누적(복리)': 매 검증 구간을 이어붙였을 때의 실전 유사 수익")
    print("  · 여러 시점에서 꾸준히 ✅ 인 전략이 진짜 신뢰할 만한 전략입니다.")


if __name__ == "__main__":
    main()
