"""매매 전략 — 가격 데이터로 '언제 사고 팔지' 신호를 생성합니다.

각 전략은 OHLCV DataFrame(컬럼: datetime, open, high, low, close, volume)을 받아
각 시점의 목표 포지션을 0/1 Series 로 반환합니다.
  - 1 = 보유(매수 상태), 0 = 비보유(현금)
백테스트 엔진이 이 포지션을 받아 수익을 계산합니다.
"""

from __future__ import annotations

import pandas as pd


def ma_crossover(df: pd.DataFrame, short: int = 5, long: int = 20) -> pd.Series:
    """이동평균 교차: 단기 이동평균이 장기 이동평균 위에 있으면 보유."""
    sma_short = df["close"].rolling(short).mean()
    sma_long = df["close"].rolling(long).mean()
    pos = (sma_short > sma_long).astype(int)
    return pos.fillna(0)


def rsi_strategy(
    df: pd.DataFrame, period: int = 14, low: float = 30, high: float = 70
) -> pd.Series:
    """RSI 과매도/과매수: RSI가 low 아래로 가면 매수, high 위로 가면 매도."""
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - 100 / (1 + rs)

    positions = []
    state = 0
    for value in rsi:
        if pd.isna(value):
            positions.append(0)
            continue
        if value < low:
            state = 1  # 과매도 → 매수
        elif value > high:
            state = 0  # 과매수 → 매도
        positions.append(state)  # 그 외엔 직전 상태 유지
    return pd.Series(positions, index=df.index)


def volatility_breakout(df: pd.DataFrame, k: float = 0.5) -> pd.Series:
    """변동성 돌파(래리 윌리엄스): 당일 시가 + k×(전일 고저폭)을 돌파하면 매수."""
    prev_range = (df["high"] - df["low"]).shift(1)
    target = df["open"] + k * prev_range
    pos = (df["high"] >= target).astype(int)
    return pos.fillna(0)


# 전략 이름 → 함수 매핑 (백테스트 비교에 사용)
STRATEGIES = {
    "이동평균 교차(5/20)": ma_crossover,
    "RSI(14, 30/70)": rsi_strategy,
    "변동성 돌파(k=0.5)": volatility_breakout,
}
