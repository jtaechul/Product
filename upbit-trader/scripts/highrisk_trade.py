#!/usr/bin/env python3
"""고위험 모멘텀 돌파 자동매매 봇 — ⚠️ --live 시 실제 주문 (기본은 모의).

전략(src/highrisk.py): 이미 강하게 오르는 알트의 'N봉 신고가 돌파 + 상승추세 + 거래량'에
추격 진입, 넓은 트레일링으로 큰 추세를 먹고 손절은 단호. 잠수함(바닥 매집)과 반대 성격이라
분산 효과가 있고, 변동이 커 고수익·고위험(그래서 전체 자산의 일부만).

· 청산/포지션 관리는 검증된 SwingTrader 엔진을 재사용(트레일링/손절/보유상한).
· 예산은 allocation.budget_for('highrisk') 로 '배정된 몫'만 사용(다른 봇과 충돌 방지).
· 보유 코인은 owned 레지스트리에 게시하고, 다른 봇이 가진 코인은 매수 대상에서 제외.

사용:
    python -m scripts.highrisk_trade                      # 모의(실시세, 무주문) ← 기본
    python -m scripts.highrisk_trade --invest 40000 --live  # 소액 실거래
종료: Ctrl+C
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import allocation, notifier  # noqa: E402
from src.highrisk import HighRiskConfig, scan_momentum  # noqa: E402
from src.swing import SwingConfig  # noqa: E402
from src.swing_trader import SwingTrader  # noqa: E402
from src.timeutil import now_kst  # noqa: E402
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

MIN_ORDER_KRW = 5000
EXCLUDE = {"KRW-BTC", "KRW-ETH"}   # 대형코인 봇 영역 — 고위험은 알트만


def log(msg: str) -> None:
    print(f"[{now_kst():%m-%d %H:%M:%S}] {msg}", flush=True)


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

    def get_holdings(self):
        return None   # 모의: 실제 잔고 없음(메모리 상태만 사용)


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

    def get_holdings(self):
        return self.ex.get_holdings()   # 실제 업비트 보유 {market:(수량,평단가)}


class Shared:
    def __init__(self):
        self.lock = threading.Lock()
        self.cands: list = []
        self.scanned = 0
        self.updated_at = None

    def set(self, cands, scanned):
        with self.lock:
            self.cands, self.scanned, self.updated_at = cands, scanned, now_kst()

    def picks(self):
        with self.lock:
            return [m for m, _ in self.cands]

    def situation(self):
        with self.lock:
            return list(self.cands), self.scanned, self.updated_at


def scanner_loop(shared, broker, q, hr_cfg, args, stop):
    while not stop.is_set():
        try:
            markets = [m["market"] for m in q.get_markets(only_krw=True)]
            tickers = q.get_ticker(markets)
            others = allocation.owned_by_others("highrisk")
            liquid = [t["market"] for t in tickers
                      if float(t.get("acc_trade_price_24h", 0)) >= args.min_value * 1e8
                      and t["market"] not in EXCLUDE
                      and t["market"] not in others]
            cands = scan_momentum(broker, liquid, hr_cfg, top=args.top)
            shared.set(cands, len(liquid))
            log(f"🔍 스캔: 모멘텀 돌파 후보 {len(cands)}개 "
                + ", ".join(m.replace('KRW-', '') for m, _ in cands[:6]))
        except Exception as exc:
            log(f"스캔 오류(계속): {exc}")
        stop.wait(args.scan_interval)


def main() -> None:
    p = argparse.ArgumentParser(description="고위험 모멘텀 돌파 봇")
    p.add_argument("--invest", type=float, default=40_000,
                   help="배분 미설정 시 1종목 매수액(fallback)")
    p.add_argument("--max-positions", type=int, default=2)
    p.add_argument("--interval", type=float, default=10.0, help="보유 감시 주기(초)")
    p.add_argument("--scan-interval", type=int, default=300, help="스캔 주기(초)")
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--min-value", type=float, default=10.0, help="24h 거래대금 하한(억)")
    p.add_argument("--cooldown", type=int, default=12, help="재진입 쿨다운(시간)")
    p.add_argument("--live", action="store_true")
    args = p.parse_args()

    hr_cfg = HighRiskConfig()
    # 청산/관리는 SwingTrader 재사용 — 고위험용으로 넓은 트레일링/단호한 손절
    cfg = SwingConfig(trail=hr_cfg.trail, stop_loss=hr_cfg.stop_loss,
                      arm_profit=hr_cfg.arm_profit, max_hold_bars=hr_cfg.max_hold_bars,
                      trail_tiers=())
    q = UpbitQuotation()

    if args.live:
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        try:
            broker = LiveBroker(q, UpbitExchange())
        except MissingApiKeyError as exc:
            log(f"중단: {exc}")
            sys.exit(1)
        print("=" * 60)
        print("🔴 실거래(LIVE) — 실제 주문이 나갑니다! 5초 후 시작 (Ctrl+C 취소)")
        print("=" * 60)
        time.sleep(5)
    else:
        broker = PaperBroker(q)
        log("🟡 모의(실시세, 무주문) 고위험 봇")

    def per_trade() -> float:
        # 배정 예산(highrisk 몫)을 종목 수로 나눔. 배분 미설정 시 fallback(--invest).
        return allocation.budget_for("highrisk", args.invest * args.max_positions) / args.max_positions

    engine = SwingTrader(broker=broker, cfg=cfg, max_positions=args.max_positions,
                         invest_per_trade=per_trade(), cooldown_hours=args.cooldown)

    shared = Shared()
    stop = threading.Event()
    threading.Thread(target=scanner_loop,
                     args=(shared, broker, q, hr_cfg, args, stop), daemon=True).start()

    mode_txt = "🔴 실거래(진짜 돈)" if args.live else "🟡 모의(가짜 돈)"
    log(f"고위험 봇 시작 ({'🔴실거래' if args.live else '🟡모의'})")
    notifier.send(
        f"🚀 <b>고위험 봇이 시작됐어요</b>  ({mode_txt})\n"
        f"• 이미 강하게 오르는 알트의 '신고가 돌파'에 올라타 시세차익을 노려요\n"
        f"• 동시 최대 {args.max_positions}종목, 배정 예산의 {1/args.max_positions*100:.0f}%씩\n"
        f"• 변동이 커요(고위험). 그래서 전체의 일부만 맡깁니다\n"
        f"• 사고팔 때 알려드리고, '상태' 보내면 세 봇을 한 번에 보여드려요")

    def nm(m):
        return m.replace("KRW-", "")

    def reason_easy(r: str) -> str:
        if r.startswith("손절"):
            return "손실 한도(-15%)에 닿아 더 큰 손실을 막으려고 팔았어요"
        if r.startswith("트레일링"):
            return "고점에서 많이 내려와 벌어둔 이익을 지키려고 팔았어요"
        if r.startswith("보유초과"):
            return "정해둔 최대 보유기간이 지나 정리했어요"
        return r

    def status() -> str:
        cands, scanned, upd = shared.situation()
        n = len(engine.positions)
        out = ["🚀 <b>고위험 현황</b>", "", "<b>[모멘텀 후보]</b>",
               f"• 점검 {scanned}개 / 돌파 후보 {len(cands)}개"]
        if cands:
            out.append("  " + ", ".join(
                f"{nm(m)}(+{f['momentum']*100:.0f}%)" for m, f in cands[:4]))
        if upd:
            out.append(f"• 마지막 점검: {upd:%H:%M}")
        out += ["", "<b>[내 거래]</b>", f"• 보유 {n}/{args.max_positions}개 "
                f"(1종목 {per_trade():,.0f}원)"]
        if n:
            try:
                prices = engine.broker.get_prices(engine.held())
            except Exception:
                prices = {}
            for m, pos in engine.positions.items():
                cur = prices.get(m, pos.entry_price)
                g = cur / pos.entry_price - 1.0
                out.append(f"   · {nm(m)}: {g*100:+.1f}%")
        sells = [t for t in engine.trades if t.action == "SELL"]
        out.append(f"• 오늘 확정 손익: {engine.realized_today:+,.0f}원 (매도 {len(sells)}회)")
        return "\n".join(out)

    notifier.run_shared("3_고위험", status, stop=stop)
    if notifier.enabled():
        log("텔레그램에 아무 말이나 보내면 세 봇 상태를 한 번에 회신합니다")

    try:
        while True:
            now = now_kst()
            engine.invest_per_trade = per_trade()        # 배분 변화 즉시 반영
            # 실제 업비트 잔고와 현행화 — 사용자가 직접 판 코인은 보유목록서 제거
            for m in engine.reconcile_with_exchange():
                log(f"🔄 {m} 외부 매도 감지 — 보유목록서 정리")
                notifier.send(
                    f"🔄 <b>보유 정리</b> [고위험]\n종목: <b>{nm(m)}</b>\n"
                    f"계좌에 없어 보유 목록에서 뺐어요(직접 파셨거나 잔량 소진).")
            allocation.publish_owned("highrisk", engine.held())   # 내 보유 코인 게시
            for rec in engine.check_exits(now):
                head = ("✅ <b>매도 — 이익 실현 🎉</b>" if rec.gain > 0
                        else "🔻 <b>매도 — 손실 정리</b>")
                log(f"매도 {rec.market} ({rec.gain*100:+.1f}%) — {rec.reason}")
                notifier.send(
                    f"{head} [고위험]\n종목: <b>{nm(rec.market)}</b>\n"
                    f"판 가격: {rec.price:,.0f}원\n결과: <b>{rec.gain*100:+.1f}%</b>\n"
                    f"이유: {reason_easy(rec.reason)}")
            if engine.has_room():
                for rec in engine.try_entries(shared.picks(), now):
                    log(f"매수 {rec.market} @ {rec.price:,.0f}")
                    notifier.send(
                        f"🟢 <b>매수했어요!</b> [고위험]\n종목: <b>{nm(rec.market)}</b>\n"
                        f"산 가격: {rec.price:,.0f}원\n"
                        f"이유: 신고가를 강하게 돌파하는 상승 모멘텀이 떠서 올라탔어요\n"
                        f"앞으로: 오르면 끝까지 따라가고, -15%에 닿으면 손절해요")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        stop.set()
        allocation.publish_owned("highrisk", [])
        log("고위험 봇 중지")
        notifier.send("🛑 <b>고위험 봇이 멈췄어요</b>")


if __name__ == "__main__":
    main()
