#!/usr/bin/env python3
"""1분봉 정밀 추적 매매 CLI (2·3단계) — ⚠️ --live 시 실제 주문.

스캐너가 포착한 코인 하나를 1분봉으로 추적하며,
진입 트리거가 뜨면 매수하고, 트레일링 스탑 + 손절 하한으로 청산합니다.

안전장치:
  · 기본은 모의(dry-run) — 실제 주문 없이 결정만 출력
  · 진짜 주문은 --live 명시 필요 + 1회 최대 투자금(--max-invest) 상한

사용법:
    # 모의로 KRW-XYZ 추적 (실주문 없음)
    python -m scripts.track_coin --market KRW-XYZ

    # 청산 파라미터 조정 (트레일링 4%, 손절 6%, +3% 도달 후 트레일링 활성화)
    python -m scripts.track_coin --market KRW-XYZ --trail 4 --stop 6 --arm 3

    # 소액 실거래
    python -m scripts.track_coin --market KRW-XYZ --max-invest 6000 --live

종료: Ctrl + C
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tracker import (  # noqa: E402
    ExitConfig,
    Position,
    decide_entry,
    decide_exit,
)
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

MIN_ORDER_KRW = 5000  # Upbit 최소 주문 금액


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="1분봉 정밀 추적 매매 봇")
    parser.add_argument("--market", required=True, help="추적할 마켓 (예: KRW-XYZ)")
    parser.add_argument("--interval", type=int, default=20, help="점검 주기(초)")
    parser.add_argument("--max-invest", type=float, default=10_000,
                        help="1회 매수 최대 금액(원)")
    parser.add_argument("--trail", type=float, default=3.0,
                        help="트레일링 스탑 %% (고점 대비 하락)")
    parser.add_argument("--stop", type=float, default=5.0,
                        help="손절 %% (진입가 대비 하락, 최후 방어선)")
    parser.add_argument("--arm", type=float, default=2.0,
                        help="트레일링 활성화 수익 %% (이 수익 도달 후 트레일링 작동)")
    parser.add_argument("--take-profit", type=float, default=0.0,
                        help="익절 %% (0이면 미사용)")
    parser.add_argument("--max-hold", type=int, default=0,
                        help="최대 보유 분(0이면 무제한)")
    parser.add_argument("--live", action="store_true",
                        help="실제 주문 실행 (없으면 모의 모드)")
    args = parser.parse_args()

    cfg = ExitConfig(
        trail_pct=args.trail / 100,
        stop_loss_pct=args.stop / 100,
        arm_profit_pct=args.arm / 100,
        take_profit_pct=(args.take_profit / 100) if args.take_profit > 0 else None,
        max_hold_min=args.max_hold if args.max_hold > 0 else None,
    )

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
        print(f"   마켓: {args.market} | 1회 최대: {args.max_invest:,.0f}원")
        print(f"   청산: 트레일링 -{args.trail:g}% / 손절 -{args.stop:g}% / "
              f"활성화 +{args.arm:g}%")
        print("   중지: Ctrl+C. 5초 후 시작...")
        print("=" * 60)
        time.sleep(5)
    else:
        log(f"🟡 모의(dry-run) 모드 — 실제 주문 없음. 마켓: {args.market}")
        log(f"   청산: 트레일링 -{args.trail:g}% / 손절 -{args.stop:g}% / "
            f"활성화 +{args.arm:g}%")

    position: Position | None = None

    try:
        while True:
            try:
                candles = quotation.get_candles_minutes(args.market, unit=1, count=60)
                df = candles_to_dataframe(candles)
                price = float(df["close"].iloc[-1])
                now = datetime.now()

                if position is None:
                    # --- 진입 판단 ---
                    if decide_entry(df):
                        if args.live and exchange is not None:
                            krw = min(args.max_invest, exchange.get_krw_balance())
                            if krw < MIN_ORDER_KRW:
                                log(f"매수 보류: 주문가능 원화 부족({krw:,.0f}원)")
                            else:
                                exchange.buy_market(args.market, krw)
                                position = Position(args.market, price, now)
                                log(f"✅ 매수: {krw:,.0f}원 @ ~{price:,.0f}")
                        else:
                            position = Position(args.market, price, now)
                            log(f"[모의] 매수 @ {price:,.0f} "
                                f"({args.max_invest:,.0f}원어치)")
                    else:
                        log(f"관망 — 진입 조건 미충족 (현재가 {price:,.0f})")
                else:
                    # --- 청산 판단 ---
                    position.update(price, cfg.arm_profit_pct)
                    should_exit, reason = decide_exit(position, price, cfg, now)
                    gain = position.gain_pct(price) * 100
                    if should_exit:
                        if args.live and exchange is not None:
                            vol = exchange.get_coin_balance(args.market)
                            if vol > 0:
                                exchange.sell_market(args.market, vol)
                                log(f"✅ 매도: {vol} @ ~{price:,.0f} "
                                    f"({gain:+.1f}%) — {reason}")
                        else:
                            log(f"[모의] 매도 @ {price:,.0f} ({gain:+.1f}%) — {reason}")
                        position = None
                    else:
                        armed = "활성" if position.armed else "대기"
                        log(f"보유 중 — {gain:+.1f}% / 고점대비 "
                            f"{(price / position.peak_price - 1) * 100:+.1f}% "
                            f"/ 트레일링:{armed} (현재가 {price:,.0f})")

            except Exception as exc:  # 일시적 오류는 건너뛰고 계속
                log(f"오류(계속 진행): {exc}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        log("사용자 중지(Ctrl+C). 추적을 종료합니다.")


if __name__ == "__main__":
    main()
