"""백테스트용 가격 데이터 공급.

네트워크가 없을 때도 동작하도록, 현실적인 합성(synthetic) OHLCV 데이터를 생성합니다.
나중에 실제 데이터로 바꾸려면:
  - load_csv() 로 CSV 를 불러오거나
  - upbit_quotation.UpbitQuotation 으로 실제 캔들을 받아 candles_to_dataframe() 사용
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_ohlcv(
    days: int = 500, start_price: float = 50_000_000, seed: int = 42
) -> pd.DataFrame:
    """추세 전환과 변동성이 섞인 현실적인 일봉 데이터를 생성.

    ⚠️ 이것은 데모용 가짜 데이터입니다. 실제 시세가 아니며, 전략 엔진이
       올바르게 동작하는지 보여주기 위한 용도입니다.
    """
    rng = np.random.default_rng(seed)

    # 며칠마다 추세(상승/하락)가 바뀌는 가격 흐름 생성
    drift = np.zeros(days)
    i = 0
    while i < days:
        block = rng.integers(20, 60)
        trend = rng.normal(0, 0.0015)  # 구간별 일일 평균 수익률
        drift[i : i + block] = trend
        i += block

    daily_vol = 0.02
    rets = drift + rng.normal(0, daily_vol, days)
    close = start_price * np.cumprod(1 + rets)

    # OHLC 구성
    open_ = np.empty(days)
    open_[0] = start_price
    open_[1:] = close[:-1] * (1 + rng.normal(0, 0.003, days - 1))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.01, days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.01, days)))
    volume = rng.uniform(50, 500, days)

    dates = pd.date_range("2025-01-01", periods=days, freq="D")
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def load_csv(path: str) -> pd.DataFrame:
    """OHLCV CSV 로딩 (컬럼: datetime, open, high, low, close, volume)."""
    df = pd.read_csv(path, parse_dates=["datetime"])
    return df.sort_values("datetime").reset_index(drop=True)
