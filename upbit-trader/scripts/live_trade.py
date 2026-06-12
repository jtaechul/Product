#!/usr/bin/env python3
"""실시간 자동매매 봇 (5단계) — ⚠️ 실제 주문 가능.

전략 신호에 따라 자동으로 매수/매도합니다. 안전을 위해:
  · 기본은 '모의(dry-run)' 모드 — 실제 주문 없이 결정만 출력합니다.
  · 진짜 주문은 --live 를 명시해야만 실행됩니다.
  · 1회 최대 투자금(--max-invest, 기본 10,000원) 상한을 둡니다.

사용법:
    # 1) 먼저 반드시 모의로 충분히 관찰 (실제 주문 안 함)
    python -m scripts.live_trade --strategy vb --interval 60

    # 2) 확신이 서면 소액으로 실거래 (API 키 + 허용 IP 필요)
    python -m scripts.live_trade --strategy vb --interval 60 --max-invest 6000 --live

종료: 터미널에서 Ctrl + C
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.timeutil import now_kst  # 한국시간(KST) 표시  # noqa: E402

from src.strategies import (  # noqa: E402
    bollinger_bands,
    ma_crossover,
    macd,
    rsi_strategy,
    volatility_breakout,
)
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

STRATEGY_MAP = {
    "vb": ("변동성 돌파", volatility_breakout),
    "macd": ("MACD", macd),
    "ma": ("이동평균 교차", ma_crossover),
    "rsi": ("RSI", rsi_strategy),
    "bb": ("볼린저밴드", bollinger_bands),
}

MIN_ORDER_KRW = 5000  # Upbit 최소 주문 금액


def log(msg: str) -> None:
    print(f"[{now_kst():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="실시간 자동매매 봇")
    parser.add_argument("--market", default="KRW-BTC")
    parser.add_argument("--strategy", choices=STRATEGY_MAP, default="vb")
    parser.add_argument("--interval", type=int, default=60, help="점검 주기(초)")
    parser.add_argument("--max-invest", type=float, default=10_000,
                        help="1회 매수 최대 금액(원)")
    parser.add_argument("--candle", choices=["day", "minute"], default="day",
                        help="신호 계산용 캔들 (기본 day=일봉, 백테스트 검증과 일치)")
    parser.add_argument("--unit", type=int, default=60,
                        help="--candle minute 일 때 분봉 단위(분)")
    parser.add_argument("--live", action="store_true",
                        help="실제 주문 실행 (없으면 모의 모드)")
    args = parser.parse_args()

    name, strategy_fn = STRATEGY_MAP[args.strategy]
    quotation = UpbitQuotation()

    exchange = None
    if args.live:
        if args.max_invest < MIN_ORDER_KRW:
            log(f"중단: 최대 투자금이 최소 주문액({MIN_ORDER_KRW}원)보다 작습니다.")
            sys.exit(1)
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        try:
            exchange = UpbitExchange()
        except MissingApiKeyError as exc:
            log(f"중단: {exc}")
            sys.exit(1)
        print("=" * 60)
        print("🔴 실거래(LIVE) 모드 — 실제 주문이 나갑니다!")
        candle_label = "일봉" if args.candle == "day" else f"{args.unit}분봉"
        print(f"   전략: {name}({candle_label}) | 마켓: {args.market} | "
              f"1회 최대: {args.max_invest:,.0f}원")
        print("   중지하려면 Ctrl+C. 5초 후 시작합니다...")
        print("=" * 60)
        time.sleep(5)
    else:
        candle_label = "일봉" if args.candle == "day" else f"{args.unit}분봉"
        log(f"🟡 모의(dry-run) 모드 — 실제 주문 없음. 전략: {name}({candle_label}), "
            f"마켓: {args.market}")

    holding = False  # 현재 보유 중인지 (세션 내 추적)
    if exchange is not None:
        holding = exchange.get_coin_balance(args.market) > 0
        log(f"시작 시 보유 상태: {'보유 중' if holding else '현금'}")

    try:
        while True:
            try:
                if args.candle == "day":
                    candles = quotation.get_candles_days(args.market, count=200)
                else:
                    candles = quotation.get_candles_minutes(
                        args.market, unit=args.unit, count=200
                    )
                df = candles_to_dataframe(candles)
                signal = int(strategy_fn(df).iloc[-1])
                price = float(df["close"].iloc[-1])

                if signal == 1 and not holding:
                    if args.live and exchange is not None:
                        krw = min(args.max_invest, exchange.get_krw_balance())
                        if krw < MIN_ORDER_KRW:
                            log(f"매수 보류: 주문가능 원화 부족({krw:,.0f}원)")
                        else:
                            exchange.buy_market(args.market, krw)
                            log(f"✅ 매수 주문 실행: {krw:,.0f}원 @ ~{price:,.0f}")
                            holding = True
                    else:
                        log(f"[모의] 매수 신호 — {args.max_invest:,.0f}원어치 매수했을 것 "
                            f"(현재가 {price:,.0f})")
                        holding = True

                elif signal == 0 and holding:
                    if args.live and exchange is not None:
                        vol = exchange.get_coin_balance(args.market)
                        if vol > 0:
                            exchange.sell_market(args.market, vol)
                            log(f"✅ 매도 주문 실행: {vol} 코인 @ ~{price:,.0f}")
                        holding = False
                    else:
                        log(f"[모의] 매도 신호 — 전량 매도했을 것 (현재가 {price:,.0f})")
                        holding = False
                else:
                    state = "보유 중" if holding else "현금"
                    log(f"대기 — 신호:{'보유' if signal else '관망'} / 상태:{state} "
                        f"(현재가 {price:,.0f})")

            except Exception as exc:  # 일시적 네트워크/응답 오류는 건너뛰고 계속
                log(f"오류(계속 진행): {exc}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        log("사용자 중지(Ctrl+C). 봇을 종료합니다.")


if __name__ == "__main__":
    main()
