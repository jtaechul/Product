"""위험 대비 수익(risk-adjusted return) 지표.

backtest.run_backtest 가 돌려주는 자산곡선(equity Series)으로,
'얼마나 벌었나'뿐 아니라 '얼마나 위험했나' 대비 효율을 계산합니다.

핵심 지표:
  · CAGR     : 연환산 복리수익률
  · MaxDD    : 최대 낙폭(고점 대비 최대 하락) — 대형코인 투자에서 가장 체감되는 위험
  · Calmar   : CAGR / |MaxDD| — '낙폭 1단위당 수익'. 위험대비수익의 핵심 순위 지표
  · Sharpe   : 변동성 대비 초과수익 (무위험수익 0 가정)
  · 변동성    : 수익률 표준편차(연환산)
  · 시장노출  : 전체 기간 중 실제로 코인을 들고 있던 비율(time-in-market)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 주기당 연환산 계수 (일봉=365, 시간봉=24*365)
PERIODS = {"1D": 365, "1h": 24 * 365}


def risk_metrics(equity: pd.Series, periods_per_year: float,
                 positions: pd.Series | None = None) -> dict:
    """자산곡선으로 위험대비수익 지표 dict 반환.

    equity: 1.0 에서 시작하는 누적 자산곡선.
    periods_per_year: 일봉이면 365, 시간봉이면 8760.
    positions: (선택) 보유여부 0/1 — 시장노출 비율 계산용.
    """
    eq = pd.Series(equity).reset_index(drop=True).astype(float)
    eq = eq[eq > 0]
    if len(eq) < 2:
        return {"total_return": 0.0, "cagr": 0.0, "mdd": 0.0, "calmar": 0.0,
                "sharpe": 0.0, "vol": 0.0, "exposure": None}

    rets = eq.pct_change().dropna()
    n = len(eq)
    years = n / periods_per_year if periods_per_year else 0.0

    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1)
    cagr = (float(eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1) if years > 0 else 0.0

    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())

    std = float(rets.std())
    vol = std * np.sqrt(periods_per_year)
    sharpe = (float(rets.mean()) / std * np.sqrt(periods_per_year)) if std > 0 else 0.0
    calmar = (cagr / abs(mdd)) if mdd < 0 else float("inf")

    exposure = None
    if positions is not None:
        p = pd.Series(positions).reset_index(drop=True)
        exposure = float((p > 0).mean())

    return {"total_return": total_return, "cagr": cagr, "mdd": mdd,
            "calmar": calmar, "sharpe": sharpe, "vol": vol, "exposure": exposure}
