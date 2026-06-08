"""Upbit 시세(Quotation) API 클라이언트.

인증이 필요 없는 공개 엔드포인트만 사용합니다. (마켓 목록, 현재가, 호가, 캔들)
공식 문서: https://docs.upbit.com/reference
"""

from __future__ import annotations

from typing import Any

import requests

from .config import UPBIT_API_BASE


class UpbitQuotation:
    """Upbit 시세 조회 클라이언트 (인증 불필요)."""

    def __init__(self, base_url: str = UPBIT_API_BASE, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        resp = self.session.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # --- 마켓 목록 ---------------------------------------------------------
    def get_markets(self, only_krw: bool = True) -> list[dict[str, Any]]:
        """거래 가능한 마켓 코드 목록.

        only_krw=True 면 원화 마켓(KRW-...)만 반환합니다.
        """
        markets = self._get("/market/all", {"isDetails": "false"})
        if only_krw:
            markets = [m for m in markets if m["market"].startswith("KRW-")]
        return markets

    # --- 현재가 -----------------------------------------------------------
    def get_ticker(self, markets: str | list[str]) -> list[dict[str, Any]]:
        """현재가 정보. markets 는 "KRW-BTC" 또는 ["KRW-BTC", "KRW-ETH"]."""
        if isinstance(markets, list):
            markets = ",".join(markets)
        return self._get("/ticker", {"markets": markets})

    def get_price(self, market: str) -> float:
        """단일 마켓의 현재 체결가만 빠르게 반환."""
        data = self.get_ticker(market)
        return float(data[0]["trade_price"])

    # --- 호가 -------------------------------------------------------------
    def get_orderbook(self, markets: str | list[str]) -> list[dict[str, Any]]:
        """호가(매수/매도 잔량) 정보."""
        if isinstance(markets, list):
            markets = ",".join(markets)
        return self._get("/orderbook", {"markets": markets})

    # --- 캔들 -------------------------------------------------------------
    def get_candles_minutes(
        self, market: str, unit: int = 1, count: int = 200
    ) -> list[dict[str, Any]]:
        """분봉 캔들. unit ∈ {1,3,5,10,15,30,60,240}, count ≤ 200."""
        return self._get(
            f"/candles/minutes/{unit}", {"market": market, "count": count}
        )

    def get_candles_days(self, market: str, count: int = 200) -> list[dict[str, Any]]:
        """일봉 캔들. count ≤ 200."""
        return self._get("/candles/days", {"market": market, "count": count})


def candles_to_dataframe(candles: list[dict[str, Any]]):
    """Upbit 캔들 응답을 pandas DataFrame 으로 변환 (시간 오름차순 정렬).

    pandas 가 설치되어 있을 때만 사용하세요.
    """
    import pandas as pd

    df = pd.DataFrame(candles)
    if df.empty:
        return df
    df = df.rename(
        columns={
            "candle_date_time_kst": "datetime",
            "opening_price": "open",
            "high_price": "high",
            "low_price": "low",
            "trade_price": "close",
            "candle_acc_trade_volume": "volume",
        }
    )
    df["datetime"] = pd.to_datetime(df["datetime"])
    cols = ["datetime", "open", "high", "low", "close", "volume"]
    df = df[cols].sort_values("datetime").reset_index(drop=True)
    return df
