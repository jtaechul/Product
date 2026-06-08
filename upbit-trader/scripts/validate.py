#!/usr/bin/env python3
"""검증 강화 — 학습/검증 분할(in-sample / out-of-sample)로 과최적화를 점검합니다.

방법:
  1) 데이터를 앞 70%(학습) / 뒤 30%(검증)로 나눔
  2) 학습 구간에서 각 전략의 '최고 파라미터'를 찾음
  3) 그 파라미터를 '처음 보는' 검증 구간에 그대로 적용
  4) 학습 성적 vs 검증 성적을 비교 → 차이가 크면 과최적화 의심

사용법:
    python scripts/validate.py
    python scripts/validate.py --csv data.csv --split 0.7
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


def main() -> None:
    parser = argparse.ArgumentParser(description="학습/검증 분할 과최적화 점검")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    parser.add_argument("--split", type=float, default=0.7, help="학습 비율(기본 0.7)")
    args = parser.parse_args()

    df = load_csv(args.csv) if args.csv else generate_synthetic_ohlcv()
    cut = int(len(df) * args.split)
    train = df.iloc[:cut].reset_index(drop=True)
    test = df.iloc[cut:].reset_index(drop=True)

    print(f"데이터: {'CSV ' + args.csv if args.csv else '합성(데모) 데이터'}")
    print(f"학습 {len(train)}일 / 검증 {len(test)}일\n")

    header = f"{'전략':<14}{'최적 파라미터':<28}{'학습수익':>10}{'검증수익':>10}  판정"
    print(header)
    print("-" * len(header))

    for name, fn, grid, valid in CONFIGS:
        # 1) 학습 구간에서 최적 파라미터 탐색
        train_results = optimize_strategy(train, fn, grid, valid=valid)
        best_params, train_r = train_results[0]
        # 2) 그 파라미터로 검증 구간 백테스트
        test_r = run_backtest(test, fn(test, **best_params))

        # 3) 판정: 학습은 좋은데 검증이 나쁘면 과최적화 의심
        if train_r.total_return > 0 and test_r.total_return > 0:
            verdict = "✅ 통과"
        elif train_r.total_return > 0 and test_r.total_return <= 0:
            verdict = "⚠️ 과최적화 의심"
        else:
            verdict = "➖ 학습부터 부진"

        pstr = ", ".join(f"{k}={v}" for k, v in best_params.items())
        print(f"{name:<14}{pstr:<28}"
              f"{train_r.total_return*100:>9.1f}%{test_r.total_return*100:>9.1f}%  {verdict}")

    print("\n해석:")
    print("  · ✅ 통과: 학습·검증 모두 수익 → 그나마 신뢰할 만함")
    print("  · ⚠️ 과최적화: 학습만 좋고 검증은 손실 → 그 파라미터는 믿으면 안 됨")
    print("  · 실전 투입 전 반드시 검증 구간(또는 실제 미래 데이터)에서 다시 확인하세요.")


if __name__ == "__main__":
    main()
