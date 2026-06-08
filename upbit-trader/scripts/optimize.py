#!/usr/bin/env python3
"""파라미터 최적화 실행 — 전략별로 좋은 설정값을 자동으로 탐색합니다.

사용법:
    python scripts/optimize.py            # 합성(데모) 데이터로 탐색
    python scripts/optimize.py --csv data.csv
    python scripts/optimize.py --top 10   # 상위 N개 표시 (기본 5)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.optimize import optimize_strategy  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import (  # noqa: E402
    ma_crossover,
    rsi_strategy,
    volatility_breakout,
)

# 전략별 탐색할 파라미터 격자(grid)
CONFIGS = [
    (
        "이동평균 교차",
        ma_crossover,
        {"short": [3, 5, 10, 20], "long": [20, 30, 60, 120]},
        lambda p: p["short"] < p["long"],  # 단기 < 장기 인 조합만
    ),
    (
        "RSI 과매도/과매수",
        rsi_strategy,
        {"period": [7, 14, 21], "low": [20, 25, 30], "high": [70, 75, 80]},
        None,
    ),
    (
        "변동성 돌파",
        volatility_breakout,
        {"k": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]},
        None,
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="전략 파라미터 최적화")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    parser.add_argument("--top", type=int, default=5, help="상위 N개 표시")
    args = parser.parse_args()

    df = load_csv(args.csv) if args.csv else generate_synthetic_ohlcv()
    print(f"데이터: {'CSV ' + args.csv if args.csv else '합성(데모) 데이터'}"
          f"  ({len(df)}일)\n")

    overall_best = None
    for name, fn, grid, valid in CONFIGS:
        results = optimize_strategy(df, fn, grid, valid=valid)
        print(f"=== {name} — 상위 {args.top}개 ===")
        print(f"{'파라미터':<34}{'누적수익':>10}{'승률':>8}{'최대낙폭':>10}")
        for params, r in results[: args.top]:
            pstr = ", ".join(f"{k}={v}" for k, v in params.items())
            print(f"{pstr:<34}{r.total_return*100:>9.1f}%"
                  f"{r.win_rate*100:>7.0f}%{r.max_drawdown*100:>9.1f}%")
        best_params, best_r = results[0]
        if overall_best is None or best_r.total_return > overall_best[2].total_return:
            overall_best = (name, best_params, best_r)
        print()

    name, params, r = overall_best
    pstr = ", ".join(f"{k}={v}" for k, v in params.items())
    print("★ 전체 1등:")
    print(f"  {name} ({pstr}) → 누적수익 {r.total_return*100:.1f}%, "
          f"최대낙폭 {r.max_drawdown*100:.1f}%")
    print("\n⚠️ 합성 데이터 기준 + 과최적화 위험. 실제 데이터로 재검증 필요.")


if __name__ == "__main__":
    main()
