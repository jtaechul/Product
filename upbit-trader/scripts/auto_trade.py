#!/usr/bin/env python3
"""잠수함 알트코인 통합 자동매매 봇 (4단계) — ⚠️ --live 시 실제 주문.

전체 흐름:
  · 백그라운드 스캐너(5분봉)가 급등 후보를 계속 갱신 (보유 감시를 막지 않음)
  · 메인 루프는 보유 코인을 '현재가 일괄 조회'로 빠르게(기본 2초) 감시 → 청산
  · 자리가 비면 후보 중 1분봉 진입 트리거가 뜬 코인을 매수 (동시 보유 상한)

수익↑/손실↓ 장치: 트레일링 + 손절 하한 + 본전 스탑 + 단계별 트레일링
                + 일일 손실 한도 + 재진입 쿨다운

사용법:
    # 모의(dry-run) — 실제 시세로 돌리되 주문은 안 함
    python -m scripts.auto_trade

    # 동시 3종목, 1종목당 6천원, 일일손실 한도 2만원
    python -m scripts.auto_trade --max-positions 3 --invest 6000 --daily-loss 20000

    # 소액 실거래
    python -m scripts.auto_trade --invest 6000 --live

종료: Ctrl + C
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auto_trader import AutoTrader, PaperBroker  # noqa: E402
from src.scanner import scan  # noqa: E402
from src.tracker import ExitConfig  # noqa: E402
from src.upbit_quotation import UpbitQuotation  # noqa: E402

MIN_ORDER_KRW = 5000


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


class LiveBroker:
    """실거래 브로커 — 시세는 Quotation, 주문은 Exchange."""

    def __init__(self, quotation: UpbitQuotation, exchange):
        self.q = quotation
        self.ex = exchange

    def get_prices(self, markets):
        tickers = self.q.get_ticker(markets)
        return {t["market"]: float(t["trade_price"]) for t in tickers}

    def get_candles_1m(self, market, count: int = 60):
        from src.upbit_quotation import candles_to_dataframe
        return candles_to_dataframe(
            self.q.get_candles_minutes(market, unit=1, count=count)
        )

    def buy(self, market, krw, price):
        avail = min(krw, self.ex.get_krw_balance())
        if avail >= MIN_ORDER_KRW:
            self.ex.buy_market(market, avail)
        return price

    def sell(self, market, price):
        vol = self.ex.get_coin_balance(market)
        if vol > 0:
            self.ex.sell_market(market, vol)
        return price


class CandidateStore:
    """스캐너 스레드와 메인 루프가 공유하는 후보 목록(스레드 안전)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._markets: list[str] = []
        self.updated_at: datetime | None = None

    def set(self, markets: list[str]) -> None:
        with self._lock:
            self._markets = markets
            self.updated_at = datetime.now()

    def get(self) -> list[str]:
        with self._lock:
            return list(self._markets)


def scanner_loop(store: CandidateStore, args, stop: threading.Event) -> None:
    """백그라운드: 주기적으로 전체 스캔해 급등조짐 후보만 추려 저장."""
    while not stop.is_set():
        try:
            cands = scan(
                unit=5,
                top=args.top,
                min_trade_value_24h=args.min_value * 1e8,
                pause=0.1,
            )
            # 급등 조짐(is_signal) 우선, 점수순
            picks = [c.market for c in cands if c.is_signal] or [
                c.market for c in cands
            ]
            store.set(picks)
            log(f"🔍 스캔 갱신: 후보 {len(picks)}개 "
                + (", ".join(picks[:5]) + ("..." if len(picks) > 5 else "")))
        except Exception as exc:
            log(f"스캔 오류(계속): {exc}")
        stop.wait(args.scan_interval)


def main() -> None:
    p = argparse.ArgumentParser(description="잠수함 알트코인 통합 자동매매 봇")
    p.add_argument("--max-positions", type=int, default=3, help="동시 보유 종목 수")
    p.add_argument("--invest", type=float, default=10_000, help="1종목 매수액(원)")
    p.add_argument("--interval", type=float, default=2.0, help="보유 청산 감시 주기(초)")
    p.add_argument("--entry-interval", type=float, default=10.0,
                   help="진입 시도 주기(초)")
    p.add_argument("--scan-interval", type=int, default=60, help="전체 스캔 주기(초)")
    p.add_argument("--top", type=int, default=20, help="스캔 상위 N개를 후보로")
    p.add_argument("--min-value", type=float, default=1.0,
                   help="24h 거래대금 하한(억원)")
    p.add_argument("--trail", type=float, default=3.0, help="트레일링 스탑 %%")
    p.add_argument("--stop", type=float, default=5.0, help="손절 %%")
    p.add_argument("--arm", type=float, default=2.0, help="트레일링 활성화 수익 %%")
    p.add_argument("--cooldown", type=int, default=30, help="재진입 쿨다운(분)")
    p.add_argument("--daily-loss", type=float, default=0.0,
                   help="일일 손실 한도(원, 0=무제한)")
    p.add_argument("--live", action="store_true", help="실제 주문 (없으면 모의)")
    args = p.parse_args()

    cfg = ExitConfig(
        trail_pct=args.trail / 100,
        stop_loss_pct=args.stop / 100,
        arm_profit_pct=args.arm / 100,
    )
    quotation = UpbitQuotation()

    if args.live:
        if args.invest < MIN_ORDER_KRW:
            log(f"중단: 1종목 매수액이 최소 주문액({MIN_ORDER_KRW}원)보다 작습니다.")
            sys.exit(1)
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        try:
            broker = LiveBroker(quotation, UpbitExchange())
        except MissingApiKeyError as exc:
            log(f"중단: {exc}")
            sys.exit(1)
        print("=" * 60)
        print("🔴 실거래(LIVE) 모드 — 실제 주문이 나갑니다!")
        print(f"   동시 {args.max_positions}종목 / 1종목 {args.invest:,.0f}원")
        print("   중지: Ctrl+C. 5초 후 시작...")
        print("=" * 60)
        time.sleep(5)
    else:
        broker = PaperBroker(quotation)  # 실시간 시세 사용, 주문은 모의
        log(f"🟡 모의(dry-run) — 실주문 없음. 동시 {args.max_positions}종목 / "
            f"1종목 {args.invest:,.0f}원")

    engine = AutoTrader(
        broker=broker,
        exit_cfg=cfg,
        max_positions=args.max_positions,
        invest_per_trade=args.invest,
        cooldown_min=args.cooldown,
        daily_loss_limit=(args.daily_loss if args.daily_loss > 0 else None),
    )

    store = CandidateStore()
    stop = threading.Event()
    scanner = threading.Thread(
        target=scanner_loop, args=(store, args, stop), daemon=True
    )
    scanner.start()
    log("스캐너 스레드 시작. 첫 스캔 결과를 기다립니다...")

    last_entry = 0.0
    try:
        while True:
            now = datetime.now()
            # 1) 보유 청산 감시 (빠르게)
            for rec in engine.check_exits(now):
                log(f"✅ 매도 {rec.market} @ {rec.price:,.0f} "
                    f"({rec.gain_pct * 100:+.1f}%) — {rec.reason}")
            if engine.halted:
                log("⛔ 일일 손실 한도 도달 — 신규 진입 중단 (보유분만 관리)")

            # 2) 진입 시도 (덜 자주)
            if time.time() - last_entry >= args.entry_interval and engine.has_room():
                for rec in engine.try_entries(store.get(), now):
                    log(f"🟢 매수 {rec.market} @ {rec.price:,.0f} "
                        f"({args.invest:,.0f}원)")
                last_entry = time.time()

            # 상태 한 줄 요약
            if engine.positions:
                held = ", ".join(engine.held_markets())
                log(f"보유 {len(engine.positions)}/{args.max_positions}: {held} "
                    f"| 금일 실현 {engine.realized_today:+,.0f}원")

            time.sleep(args.interval)
    except KeyboardInterrupt:
        stop.set()
        log("사용자 중지(Ctrl+C).")
        wins = [t for t in engine.trades if t.action == "SELL" and t.gain_pct > 0]
        sells = [t for t in engine.trades if t.action == "SELL"]
        if sells:
            wr = len(wins) / len(sells) * 100
            log(f"요약: 매도 {len(sells)}회, 승률 {wr:.0f}%, "
                f"금일 실현손익 {engine.realized_today:+,.0f}원")


if __name__ == "__main__":
    main()
