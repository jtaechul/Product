"""백테스트 엔진 — 전략의 포지션 신호로 과거 수익을 시뮬레이션합니다.

핵심 원칙(미래참조 방지):
  오늘 신호로 '다음 봉'에 매매한 것으로 계산합니다 (positions.shift(1)).
거래마다 수수료(fee)를 차감합니다. (Upbit 기본 0.05% 가정)
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    total_return: float       # 전략 누적 수익률
    buy_hold_return: float    # 단순 보유(사서 가만히) 수익률
    num_trades: int           # 매매 횟수(진입 기준)
    win_rate: float           # 승률 (이익 낸 매매 비율)
    max_drawdown: float       # 최대 낙폭 (고점 대비 최대 하락)
    equity: pd.Series         # 자산 곡선 (1.0 시작)


def run_backtest(
    df: pd.DataFrame, positions: pd.Series, fee: float = 0.0005
) -> BacktestResult:
    close = df["close"].reset_index(drop=True)
    pos = positions.reset_index(drop=True)

    # 오늘 신호 → 다음 봉에 반영 (미래참조 방지)
    held = pos.shift(1).fillna(0)
    market_ret = close.pct_change().fillna(0)

    turnover = held.diff().abs().fillna(0)   # 포지션 변동 (진입/청산)
    cost = turnover * fee
    net_ret = held * market_ret - cost

    equity = (1 + net_ret).cumprod()
    total_return = float(equity.iloc[-1] - 1)
    buy_hold = float(close.iloc[-1] / close.iloc[0] - 1)

    # 최대 낙폭
    drawdown = equity / equity.cummax() - 1
    max_dd = float(drawdown.min())

    # 매매별 승패: 진입(0→1)부터 청산(1→0)까지 묶어서 손익 계산
    wins, trades = 0, 0
    entry_price = None
    for i in range(1, len(held)):
        if held.iloc[i] == 1 and held.iloc[i - 1] == 0:
            entry_price = close.iloc[i]
        elif held.iloc[i] == 0 and held.iloc[i - 1] == 1 and entry_price is not None:
            trades += 1
            if close.iloc[i] * (1 - 2 * fee) > entry_price:
                wins += 1
            entry_price = None
    win_rate = (wins / trades) if trades else 0.0

    return BacktestResult(
        total_return=total_return,
        buy_hold_return=buy_hold,
        num_trades=trades,
        win_rate=win_rate,
        max_drawdown=max_dd,
        equity=equity,
    )
