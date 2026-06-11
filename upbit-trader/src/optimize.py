"""파라미터 최적화 — 여러 설정값 조합을 모두 백테스트해 가장 좋은 걸 찾습니다.

예) 이동평균 전략에서 (단기5/장기20), (단기10/장기60) ... 수십 조합을 자동으로 돌려
    누적수익이 높은 순으로 정렬해 보여줍니다.

⚠️ 주의(과최적화): 특정 데이터에 가장 잘 맞는 값을 고르면, 그 데이터에만 맞고
   미래엔 안 맞을 수 있습니다(overfitting). 합성 데이터 결과는 더더욱 참고용입니다.
"""

from __future__ import annotations

import itertools
from typing import Callable

import pandas as pd

from .backtest import BacktestResult, run_backtest


def optimize_strategy(
    df: pd.DataFrame,
    strategy_fn: Callable[..., pd.Series],
    param_grid: dict[str, list],
    fee: float = 0.0005,
    valid: Callable[[dict], bool] | None = None,
) -> list[tuple[dict, BacktestResult]]:
    """param_grid 의 모든 조합을 백테스트하고 누적수익 내림차순으로 반환.

    param_grid 예: {"short": [5, 10], "long": [20, 60]}
    valid: 유효하지 않은 조합을 거르는 함수(예: short < long). None 이면 전부 허용.
    """
    keys = list(param_grid.keys())
    results: list[tuple[dict, BacktestResult]] = []

    for combo in itertools.product(*(param_grid[k] for k in keys)):
        params = dict(zip(keys, combo))
        if valid is not None and not valid(params):
            continue
        positions = strategy_fn(df, **params)
        result = run_backtest(df, positions, fee=fee)
        results.append((params, result))

    results.sort(key=lambda x: x[1].total_return, reverse=True)
    return results
