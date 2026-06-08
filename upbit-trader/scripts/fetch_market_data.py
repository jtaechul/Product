#!/usr/bin/env python3
"""시세 조회 데모 CLI.

사용법:
    python scripts/fetch_market_data.py             # 원화 마켓 목록 일부 출력
    python scripts/fetch_market_data.py KRW-BTC     # 특정 마켓 현재가/호가/일봉 요약

인증이 필요 없는 Upbit 시세 API만 사용합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가 (별도 설치 없이 실행 가능하도록)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402


def show_market_list(client: UpbitQuotation) -> None:
    markets = client.get_markets(only_krw=True)
    print(f"원화(KRW) 마켓 {len(markets)}개 중 상위 15개:\n")
    for m in markets[:15]:
        print(f"  {m['market']:<12} {m['korean_name']}")
    print("\n특정 마켓 조회:  python scripts/fetch_market_data.py KRW-BTC")


def show_market_detail(client: UpbitQuotation, market: str) -> None:
    # 현재가
    ticker = client.get_ticker(market)[0]
    price = ticker["trade_price"]
    change_rate = ticker["signed_change_rate"] * 100
    print(f"=== {market} ===")
    print(f"현재가      : {price:,.0f} KRW")
    print(f"전일대비    : {change_rate:+.2f}%")
    print(f"24h 거래대금: {ticker['acc_trade_price_24h']:,.0f} KRW\n")

    # 호가 (매수 1호가 / 매도 1호가)
    orderbook = client.get_orderbook(market)[0]
    best = orderbook["orderbook_units"][0]
    print("호가 (1호가):")
    print(f"  매도 {best['ask_price']:,.0f}  (잔량 {best['ask_size']:.4f})")
    print(f"  매수 {best['bid_price']:,.0f}  (잔량 {best['bid_size']:.4f})\n")

    # 일봉 캔들 요약
    candles = client.get_candles_days(market, count=10)
    df = candles_to_dataframe(candles)
    print("최근 10일 일봉:")
    print(df.to_string(index=False))


def main() -> None:
    client = UpbitQuotation()
    if len(sys.argv) >= 2:
        show_market_detail(client, sys.argv[1].upper())
    else:
        show_market_list(client)


if __name__ == "__main__":
    main()
