"""모의매매(Paper Trading) — 실제 돈 없이 가상 계좌로 사고팔며 기록을 남깁니다.

백테스트가 '최종 성적표'라면, 모의매매는 '거래 일지'입니다.
전략이 언제·얼마에 사고팔았는지, 그때 잔고가 어떻게 변했는지 한 줄씩 기록합니다.
네트워크 없이 과거 데이터를 '재생(replay)'하는 방식으로 동작합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass
class Trade:
    datetime: pd.Timestamp
    action: str       # "BUY" 또는 "SELL"
    price: float
    amount: float     # 거래한 코인 수량
    value_after: float  # 거래 직후 총 자산(현금+코인평가) 가치


@dataclass
class PaperAccount:
    """가상 계좌. 전량 매수/전량 매도 방식(단순화)."""

    cash: float
    fee: float = 0.0005
    coin: float = 0.0
    trades: list[Trade] = field(default_factory=list)

    def buy(self, price: float, dt: pd.Timestamp) -> None:
        if self.cash <= 0:
            return
        bought = (self.cash * (1 - self.fee)) / price
        self.coin += bought
        self.cash = 0.0
        self.trades.append(Trade(dt, "BUY", price, bought, self.value(price)))

    def sell(self, price: float, dt: pd.Timestamp) -> None:
        if self.coin <= 0:
            return
        sold = self.coin
        self.cash += sold * price * (1 - self.fee)
        self.coin = 0.0
        self.trades.append(Trade(dt, "SELL", price, sold, self.value(price)))

    def value(self, price: float) -> float:
        """현재가 기준 총 자산 가치(현금 + 코인 평가액)."""
        return self.cash + self.coin * price


def run_paper_trading(
    df: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame], pd.Series],
    initial_cash: float = 1_000_000,
    fee: float = 0.0005,
) -> PaperAccount:
    """전략 신호에 따라 과거 데이터를 재생하며 가상 매매를 수행.

    미래참조 방지: 직전 봉의 신호로 현재 봉 시가에 체결한 것으로 처리합니다.
    """
    positions = strategy_fn(df).reset_index(drop=True)
    account = PaperAccount(cash=initial_cash, fee=fee)

    for i in range(1, len(df)):
        signal = positions.iloc[i - 1]   # 직전 봉의 신호
        price = float(df["open"].iloc[i])  # 현재 봉 시가에 체결
        dt = df["datetime"].iloc[i]
        if signal == 1 and account.coin == 0:
            account.buy(price, dt)
        elif signal == 0 and account.coin > 0:
            account.sell(price, dt)

    return account
