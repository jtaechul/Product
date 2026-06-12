#!/usr/bin/env python3
"""잠수함 코인 스윙 자동매매 봇 — ⚠️ --live 시 실제 주문.

검증된 스윙 전략(독립표본 3종 t>4)을 실시간으로 실행합니다.
  · 스캐너: 60분봉으로 거래량 급증 돌파 + 추세 게이트 통과 코인을 주기 선별
  · 보유 감시: 현재가 일괄조회로 하드 손절/트레일링/보유시간 초단위 체크
  · 진입은 빠르게, 청산은 인내(수시간~수일 트레일링)

사용:
    python -m scripts.swing_trade                      # 모의(실시세, 무주문)
    python -m scripts.swing_trade --max-positions 3 --invest 100000
    python -m scripts.swing_trade --invest 50000 --live   # 소액 실거래

종료: Ctrl+C
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import notifier  # noqa: E402
from src.swing import SwingConfig  # noqa: E402
from src.swing_trader import SwingTrader, scan_candidates  # noqa: E402
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

MIN_ORDER_KRW = 5000


def log(msg: str, push: bool = False) -> None:
    print(f"[{datetime.now():%m-%d %H:%M:%S}] {msg}", flush=True)
    if push:
        notifier.send(msg)


class PaperBroker:
    def __init__(self, q: UpbitQuotation):
        self.q = q

    def get_prices(self, markets):
        return {t["market"]: float(t["trade_price"]) for t in self.q.get_ticker(markets)}

    def get_candles_60m(self, market, count=200):
        return candles_to_dataframe(self.q.get_candles_minutes(market, unit=60, count=min(200, count)))

    def buy(self, market, krw, price):
        return price

    def sell(self, market, price):
        return price


class LiveBroker(PaperBroker):
    def __init__(self, q, exchange):
        super().__init__(q)
        self.ex = exchange

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


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.markets: list[str] = []
        self.btc_ok = True

    def set(self, markets, btc_ok):
        with self.lock:
            self.markets = markets
            self.btc_ok = btc_ok

    def get(self):
        with self.lock:
            return list(self.markets), self.btc_ok


def scanner_loop(shared, broker, q, cfg, args, stop):
    while not stop.is_set():
        try:
            # 시장 추세 게이트: BTC 60분봉이 자기 MA 위인지
            btc = broker.get_candles_60m("KRW-BTC", count=cfg.btc_ma_bars + 2)
            btc_ok = True
            if cfg.btc_ma_bars > 0 and len(btc) > cfg.btc_ma_bars:
                btc_ok = bool(btc["close"].iloc[-1] > btc["close"].tail(cfg.btc_ma_bars).mean())

            markets = [m["market"] for m in q.get_markets(only_krw=True)]
            tickers = q.get_ticker(markets)
            liquid = [t["market"] for t in tickers
                      if float(t.get("acc_trade_price_24h", 0)) >= args.min_value * 1e8]
            cands = scan_candidates(broker, liquid, cfg, btc_ok=btc_ok, top=args.top)
            picks = [m for m, _ in cands]
            shared.set(picks, btc_ok)
            gate = "강세" if btc_ok else "약세(진입중단)"
            log(f"🔍 스캔: BTC추세 {gate} | 후보 {len(picks)}개 "
                + (", ".join(p.replace('KRW-', '') for p in picks[:6])))
        except Exception as exc:
            log(f"스캔 오류(계속): {exc}")
        stop.wait(args.scan_interval)


def main() -> None:
    p = argparse.ArgumentParser(description="잠수함 코인 스윙 자동매매 봇")
    p.add_argument("--max-positions", type=int, default=3)
    p.add_argument("--invest", type=float, default=100_000)
    p.add_argument("--interval", type=float, default=5.0, help="보유 감시 주기(초)")
    p.add_argument("--scan-interval", type=int, default=300, help="스캔 주기(초)")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--min-value", type=float, default=5.0, help="24h 거래대금 하한(억)")
    p.add_argument("--trail", type=float, default=0.15)
    p.add_argument("--stop", type=float, default=0.10)
    p.add_argument("--arm", type=float, default=0.06)
    p.add_argument("--vol-surge", type=float, default=3.0)
    p.add_argument("--max-hold", type=int, default=240, help="최대 보유(시간)")
    p.add_argument("--cooldown", type=int, default=12, help="재진입 쿨다운(시간)")
    p.add_argument("--daily-loss", type=float, default=0.0)
    p.add_argument("--live", action="store_true")
    args = p.parse_args()

    cfg = SwingConfig(
        vol_surge=args.vol_surge, trail=args.trail, stop_loss=args.stop,
        arm_profit=args.arm, max_hold_bars=args.max_hold,
    )
    q = UpbitQuotation()

    if args.live:
        if args.invest < MIN_ORDER_KRW:
            log(f"중단: 매수액이 최소주문({MIN_ORDER_KRW})보다 작음")
            sys.exit(1)
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        try:
            broker = LiveBroker(q, UpbitExchange())
        except MissingApiKeyError as exc:
            log(f"중단: {exc}")
            sys.exit(1)
        print("=" * 60)
        print("🔴 실거래(LIVE) — 실제 주문이 나갑니다! 5초 후 시작 (Ctrl+C 취소)")
        print(f"   동시 {args.max_positions}종목 / 1종목 {args.invest:,.0f}원")
        print("=" * 60)
        time.sleep(5)
    else:
        broker = PaperBroker(q)
        log(f"🟡 모의(실시세, 무주문). 동시 {args.max_positions}종목 / "
            f"1종목 {args.invest:,.0f}원")

    engine = SwingTrader(
        broker=broker, cfg=cfg, max_positions=args.max_positions,
        invest_per_trade=args.invest, cooldown_hours=args.cooldown,
        daily_loss_limit=(args.daily_loss if args.daily_loss > 0 else None),
    )

    shared = Shared()
    stop = threading.Event()
    th = threading.Thread(target=scanner_loop,
                          args=(shared, broker, q, cfg, args, stop), daemon=True)
    th.start()

    mode_txt = ("🔴 실거래(진짜 돈)" if args.live
                else "🟡 모의(가짜 돈, 실제 주문 안 함)")
    log(f"스윙 봇 시작 ({'🔴실거래' if args.live else '🟡모의'})")
    notifier.send(
        f"🤖 <b>잠수함 봇이 시작됐어요</b>  ({mode_txt})\n"
        f"• 한 번에 최대 {args.max_positions}종목, 종목당 "
        f"{args.invest:,.0f}원으로 매매해요\n"
        f"• 거래량이 터지며 오르는 코인을 자동으로 사고, 규칙대로 팔아요\n"
        f"• 사고팔 때마다 여기로 자세히 알려드릴게요\n"
        f"• 궁금하면 아무 메시지나 보내세요 → 지금 상태를 바로 알려드려요")
    if notifier.enabled():
        log("텔레그램 알림 연결됨")

    def reason_easy(r: str) -> str:
        """청산 사유를 비전문가용 한 문장으로 풀어줌."""
        if r.startswith("손절"):
            return "손실이 한도(-10%)에 닿아, 더 큰 손실을 막으려고 팔았어요"
        if r.startswith("트레일링"):
            return "고점에서 일정폭 내려와, 벌어둔 이익을 지키려고 팔았어요"
        if r.startswith("익절"):
            return "목표 수익에 도달해 이익을 확정했어요"
        if r.startswith("보유초과"):
            return "정해둔 최대 보유기간(10일)이 지나 정리했어요"
        return r

    def status() -> str:
        """현재 보유 코인별 손익까지 쉬운 말로 풀어 보여줌."""
        n = len(engine.positions)
        sells = sum(1 for t in engine.trades if t.action == "SELL")
        if n == 0:
            body = "보유 중인 코인: 없음 (살 만한 코인을 기다리는 중이에요 👀)"
        else:
            try:
                prices = engine.broker.get_prices(engine.held())
            except Exception:
                prices = {}
            lines = [f"보유 코인: {n}/{args.max_positions}개"]
            for m, pos in engine.positions.items():
                cur = prices.get(m, pos.entry_price)
                g = cur / pos.entry_price - 1.0
                won = g * args.invest
                lines.append(f"  • {m.replace('KRW-','')}: "
                             f"지금 {g*100:+.1f}% ({won:+,.0f}원)")
            body = "\n".join(lines)
        return (f"{body}\n"
                f"오늘 확정 손익: {engine.realized_today:+,.0f}원 "
                f"(지금까지 매도 {sells}회)")

    notifier.start_heartbeat(status, interval_sec=3600, stop=stop)
    # 텔레그램에서 아무 메시지(예: /상태)를 보내면 즉시 현재 상태로 회신
    notifier.start_command_listener(status, stop=stop)
    if notifier.enabled():
        log("텔레그램에 아무 말이나 보내면 즉시 상태를 회신합니다 (강제 하트비트)")

    try:
        while True:
            now = datetime.now()
            for rec in engine.check_exits(now):
                won = rec.gain * args.invest
                head = ("✅ <b>매도 — 이익 실현 🎉</b>" if rec.gain > 0
                        else "🔻 <b>매도 — 손실 정리</b>")
                log(f"매도 {rec.market} ({rec.gain*100:+.1f}%) — {rec.reason}")
                notifier.send(
                    f"{head}\n"
                    f"종목: <b>{rec.market.replace('KRW-','')}</b>\n"
                    f"판 가격: {rec.price:,.0f}원\n"
                    f"결과: <b>{rec.gain*100:+.1f}%  ({won:+,.0f}원)</b>\n"
                    f"이유: {reason_easy(rec.reason)}\n"
                    f"오늘 확정 손익: {engine.realized_today:+,.0f}원")
            if engine.halted:
                log("⛔ 일일 손실 한도 — 신규 진입 중단")
            if engine.has_room():
                picks, btc_ok = shared.get()
                for rec in engine.try_entries(picks, now):
                    log(f"매수 {rec.market} @ {rec.price:,.0f}")
                    notifier.send(
                        f"🟢 <b>매수했어요!</b>\n"
                        f"종목: <b>{rec.market.replace('KRW-','')}</b>\n"
                        f"산 가격: {rec.price:,.0f}원\n"
                        f"투입 금액: {args.invest:,.0f}원\n"
                        f"이유: 거래량이 평소보다 크게 늘며 상승 신호가 떠서 샀어요\n"
                        f"현재 보유: {len(engine.positions)}/{args.max_positions}개\n"
                        f"앞으로: 오르면 끝까지 따라가고, -10%에 닿으면 손절해요")
            if engine.positions:
                held = ", ".join(m.replace("KRW-", "") for m in engine.held())
                log(f"보유 {len(engine.positions)}/{args.max_positions}: {held} "
                    f"| 금일 {engine.realized_today:+,.0f}원")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        stop.set()
        sells = [t for t in engine.trades if t.action == "SELL"]
        wins = [t for t in sells if t.gain > 0]
        log("스윙 봇 중지")
        msg = "🛑 <b>봇이 멈췄어요</b> (더 이상 자동 매매 안 함)"
        if sells:
            msg += (f"\n오늘 매도 {len(sells)}회 중 이익 {len(wins)}회 "
                    f"(승률 {len(wins)/len(sells)*100:.0f}%)\n"
                    f"오늘 확정 손익: {engine.realized_today:+,.0f}원")
        if engine.positions:
            held = ", ".join(m.replace("KRW-", "") for m in engine.held())
            msg += f"\n⚠️ 아직 들고 있는 코인: {held} — 봇이 멈춰서 자동 관리 안 돼요"
        notifier.send(msg)


if __name__ == "__main__":
    main()
