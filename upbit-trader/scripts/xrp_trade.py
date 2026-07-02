#!/usr/bin/env python3
"""리플(XRP) 전용 자동매매 봇 — ⚠️ --live 시 실제 주문.

왜 XRP 전용인가 (scripts/analyze_xrp 검증 결론):
  · XRP는 추세필터(200MA)가 약했고(Calmar 0.21), MACD는 과최적화(전체 1.70→검증 0.13)였다.
  · 워크포워드 5개 시기 중 4개에서 '스윙펌프(거래량 급증 돌파 추격)'가 단순보유 대비
    위험대비수익(Calmar) 우위 — XRP의 '오래 잠잠하다 급등' 성격과 부합.
  · 따라서 이 봇은 검증된 '일봉 스윙펌프' 신호만으로 XRP 한 종목을 매매한다.

잠수함 봇과 차이:
  · 잠수함=전체 마켓 스캔(여러 코인). XRP봇=KRW-XRP 한 종목만, '일봉' 스케일로 판단.
  · 진입/청산 규칙(트레일링·손절)은 가격 기반이라 검증된 swing_trader 엔진을 그대로 재사용.

사용:
    python -m scripts.xrp_trade                 # 모의(실시세, 무주문) — 기본
    python -m scripts.xrp_trade --invest 50000 --live   # 소액 실거래

종료: Ctrl+C
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import allocation, news_filter, notifier  # noqa: E402
from src.swing import SwingConfig, compute_features, is_entry  # noqa: E402
from src.swing_trader import SwingTrader  # noqa: E402
from src.timeutil import now_kst as datetime_now  # noqa: E402
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

MARKET = "KRW-XRP"
MIN_ORDER_KRW = 5000

# tune_xrp 검증 승자 '공격형' 설정(일봉). 진입 신호는 '일봉', 청산은 가격기반 실시간.
#   공격조합 = 거래량 1.5배 + 박스 20일 + 추격상한 35% (self_ma=50·BTC게이트 끔 유지):
#     거래 24→53회(2.2배), Calmar 0.94→1.39, 워크포워드 5구간 4/5 · 8구간 6/8(기준 5/8).
#   ⚠️ 대가: 최대낙폭 -33%→-56%로 깊어짐(공격형의 비용) — 승률 49%, 손절 연발 구간 존재.
#   max_hold_bars 는 실시간 엔진에서 '시간(h)' 단위 → 30일 = 720h
XRP_CFG = dict(base_bars=20, recent_bars=3, self_ma_bars=50, btc_ma_bars=0,
               vol_surge=1.5, max_chase=0.35)


def log(msg: str, push: bool = False) -> None:
    print(f"[{datetime_now():%m-%d %H:%M:%S}] {msg}", flush=True)
    if push:
        notifier.send(msg)


class PaperBroker:
    def __init__(self, q: UpbitQuotation):
        self.q = q

    def get_prices(self, markets):
        return {t["market"]: float(t["trade_price"]) for t in self.q.get_ticker(markets)}

    def get_candles_60m(self, market, count=200):
        return candles_to_dataframe(
            self.q.get_candles_minutes(market, unit=60, count=min(200, count)))

    def buy(self, market, krw, price):
        return price

    def sell(self, market, price):
        return price

    def get_holdings(self):
        return None   # 모의: 실제 잔고 없음(메모리 상태만)


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
        return self.ex.get_holdings()


class Shared:
    """스캐너 스레드가 계산한 '오늘 일봉 신호'를 메인 루프와 공유."""
    def __init__(self):
        self.lock = threading.Lock()
        self.signal = False        # 지금 진입 신호가 떠 있는가
        self.feat: dict | None = None
        self.updated_at = None

    def set(self, signal, feat):
        with self.lock:
            self.signal = signal
            self.feat = feat
            self.updated_at = datetime_now()

    def get(self):
        with self.lock:
            return self.signal, self.feat, self.updated_at


def daily_signal(q: UpbitQuotation, cfg: SwingConfig) -> tuple[bool, dict | None]:
    """XRP 일봉으로 '오늘 진입 신호'를 계산 (백테스트 is_entry 와 동일 규칙)."""
    need = cfg.base_bars + cfg.recent_bars + cfg.self_ma_bars + 2
    df = candles_to_dataframe(q.get_candles_days(MARKET, count=min(200, need)))
    if len(df) < need - 1:
        return False, None
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    i = len(c) - 1
    feat = compute_features(c, h, v, i, cfg)
    if not is_entry(feat, cfg):
        return False, feat
    if cfg.self_ma_bars > 0:           # 코인 자체 추세 게이트(50일선 위)
        if not c[i] > c[-cfg.self_ma_bars:].mean():
            return False, feat
    return True, feat


def scanner_loop(shared, q, cfg, interval, stop):
    while not stop.is_set():
        try:
            sig, feat = daily_signal(q, cfg)
            shared.set(sig, feat)
            if sig:
                log(f"🔍 XRP 진입 신호 ON — 거래량 {feat['surge']:.1f}배, "
                    f"박스돌파 {feat['breakout']*100:+.1f}%, 최근상승 {feat['momentum']*100:+.1f}%")
            else:
                log("🔍 XRP 신호 없음 — 급등 조건 대기 중")
        except Exception as exc:
            log(f"신호 계산 오류(계속): {exc}")
        stop.wait(interval)


def main() -> None:
    p = argparse.ArgumentParser(description="리플(XRP) 전용 자동매매 봇")
    p.add_argument("--invest", type=float, default=100_000, help="1회 매수 금액")
    p.add_argument("--interval", type=float, default=10.0, help="보유 감시 주기(초)")
    p.add_argument("--scan-interval", type=int, default=1800,
                   help="일봉 신호 점검 주기(초). 일봉 전략이라 길게 둠(기본 30분)")
    p.add_argument("--trail", type=float, default=0.15, help="고점 대비 트레일링 폭")
    p.add_argument("--stop", type=float, default=0.10, help="하드 손절 폭")
    p.add_argument("--arm", type=float, default=0.06, help="트레일링 활성 수익선")
    p.add_argument("--max-hold-days", type=int, default=30, help="최대 보유(일)")
    p.add_argument("--cooldown", type=int, default=48, help="매도 후 재진입 쿨다운(시간)")
    p.add_argument("--take-profit", type=float, default=0.0,
                   help="고정 익절선(+비율, 0=끔). 도달 시 트레일링 안 기다리고 익절")
    p.add_argument("--news", choices=["auto", "off"], default="auto",
                   help="뉴스 브레이크(auto=API키 있으면 작동). 강한 악재면 매수 보류")
    p.add_argument("--news-threshold", type=int, default=50,
                   help="이 값 이상의 악재 점수(-N 이하)면 매수 보류")
    p.add_argument("--live", action="store_true")
    args = p.parse_args()

    cfg = SwingConfig(
        trail=args.trail, stop_loss=args.stop, arm_profit=args.arm,
        max_hold_bars=args.max_hold_days * 24,   # 실시간 엔진에서 '시간' 단위
        take_profit=(args.take_profit if args.take_profit > 0 else None),
        **XRP_CFG,
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
        print(f"   리플(XRP) 한 종목 / 매수 {args.invest:,.0f}원")
        print("=" * 60)
        time.sleep(5)
    else:
        broker = PaperBroker(q)
        log(f"🟡 모의(실시세, 무주문). 리플(XRP) 한 종목 / 매수 {args.invest:,.0f}원")

    state_file = (Path(__file__).resolve().parent.parent
                  / ".botstate" / "positions_xrp.json")
    engine = SwingTrader(
        broker=broker, cfg=cfg, max_positions=1, invest_per_trade=args.invest,
        cooldown_hours=args.cooldown, state_path=str(state_file),
    )
    engine.load_state()
    engine.adopt_holdings()   # 이미 보유 중인 XRP가 있으면 흡수해 관리(평단=진입가)
    # 이 봇은 XRP 전용 — 계좌의 '다른' 코인(직접 산 코인·에어드랍 등)은 절대 관리/매도
    # 하지 않는다. adopt_holdings 는 계좌 전체를 흡수하므로 XRP 외에는 즉시 제외한다.
    # (KRW 마켓 없는 에어드랍 토큰이 섞이면 시세조회가 깨져 봇이 죽는 문제도 함께 차단)
    for _m in [k for k in engine.positions if k != MARKET]:
        del engine.positions[_m]
    engine.save_state()

    shared = Shared()
    stop = threading.Event()
    th = threading.Thread(target=scanner_loop,
                          args=(shared, q, cfg, args.scan_interval, stop), daemon=True)
    th.start()

    mode_txt = ("🔴 실거래(진짜 돈)" if args.live
                else "🟡 모의(가짜 돈, 실제 주문 안 함)")
    log(f"리플 봇 시작 ({'🔴실거래' if args.live else '🟡모의'})")
    notifier.send(
        f"🤖 <b>리플(XRP) 봇이 시작됐어요</b>  ({mode_txt})\n"
        f"• 리플 한 종목만, 한 번에 {args.invest:,.0f}원으로 매매해요\n"
        f"• 거래량이 평소보다 크게 터지며 오를 때(검증된 신호) 사고, 규칙대로 팔아요\n"
        f"• 고점에서 {args.trail*100:.0f}% 내려오면 이익 보존 매도, -{args.stop*100:.0f}%면 손절\n"
        + (f"• +{args.take_profit*100:.0f}% 도달 시 바로 익절\n"
           if args.take_profit > 0 else "")
        + "• 사고팔 때마다 여기로 알려드릴게요")

    def reason_easy(r: str) -> str:
        if r.startswith("손절"):
            return f"손실이 한도(-{args.stop*100:.0f}%)에 닿아, 더 큰 손실을 막으려고 팔았어요"
        if r.startswith("트레일링"):
            return "고점에서 일정폭 내려와, 벌어둔 이익을 지키려고 팔았어요"
        if r.startswith("익절"):
            return "목표 수익에 도달해 이익을 확정했어요"
        if r.startswith("보유초과"):
            return f"정해둔 최대 보유기간({args.max_hold_days}일)이 지나 정리했어요"
        return r

    def status() -> str:
        sig, feat, upd = shared.get()
        n = len(engine.positions)
        sells = sum(1 for t in engine.trades if t.action == "SELL")
        out = ["🪙 <b>리플(XRP) 봇 현황</b>", "", "<b>[신호]</b>"]
        if sig and feat:
            out.append(f"• 진입 신호 ON — 거래량 평소 {feat.get('surge',0):.1f}배, "
                       f"박스돌파 {feat.get('breakout',0)*100:+.1f}%")
        else:
            out.append("• 진입 신호 없음 — 거래량 급등(돌파) 기다리는 중 👀")
        if upd:
            out.append(f"• 마지막 신호 점검: {upd:%H:%M}")
        out += ["", "<b>[내 거래]</b>"]
        if n == 0:
            out.append("• 보유: 없음 (현금)")
        else:
            try:
                price = engine.broker.get_prices([MARKET]).get(MARKET)
            except Exception:
                price = None
            pos = engine.positions.get(MARKET)
            if pos and price:
                g = price / pos.entry_price - 1.0
                # 손익 '원' 표시는 실제 보유 수량 기준(실거래). 조회 실패 시 매수액 근사.
                won = None
                try:
                    h = broker.get_holdings()
                    if h and MARKET in h:
                        won = (price - pos.entry_price) * h[MARKET][0]
                except Exception:
                    pass
                if won is None:
                    won = g * args.invest
                out.append(f"• 보유 중: 지금 {g*100:+.1f}% ({won:+,.0f}원)")
            else:
                out.append("• 보유 중")
        out.append(f"• 오늘 확정 손익: {engine.realized_today:+,.0f}원 (매도 {sells}회)")
        return "\n".join(out)

    notifier.run_shared("4_리플", status, stop=stop)

    # 뉴스 브레이크: 매수 직전에만 평가(비용↓). 1시간 캐시로 중복 호출 방지.
    _news_cache: dict = {"verdict": None, "at": 0.0}

    def news_gate() -> news_filter.NewsVerdict | None:
        if args.news == "off":
            return None
        if (_news_cache["verdict"] is not None
                and time.time() - _news_cache["at"] < 3600):
            return _news_cache["verdict"]
        v = news_filter.assess(neg_threshold=args.news_threshold)
        _news_cache.update(verdict=v, at=time.time())
        if v.enabled:
            log(f"📰 뉴스 평가: {v.label} ({v.score:+d}) — {v.reason}")
        else:
            log(f"📰 뉴스 브레이크 미작동: {v.reason}")
        return v

    # 반복 알림 방지용 타임스탬프(원화부족·뉴스보류는 상황이 지속돼도 1시간에 1번만 알림)
    _nocash = {"at": 0.0}
    _newsblock = {"at": 0.0}

    def tick(now) -> None:
        """한 번의 점검(청산 → 진입). 예외는 바깥 루프가 잡아 봇이 죽지 않고 계속 돈다."""
        for m in engine.reconcile_with_exchange():
            log(f"🔄 {m} 외부 매도 감지 — 보유목록서 정리")
        for rec in engine.check_exits(now):
            won = rec.gain * args.invest
            head = ("✅ <b>리플 매도 — 이익 실현 🎉</b>" if rec.gain > 0
                    else "🔻 <b>리플 매도 — 손실 정리</b>")
            log(f"매도 XRP ({rec.gain*100:+.1f}%) — {rec.reason}")
            notifier.send(
                f"{head}\n판 가격: {rec.price:,.0f}원\n"
                f"결과: <b>{rec.gain*100:+.1f}%  ({won:+,.0f}원)</b>\n"
                f"이유: {reason_easy(rec.reason)}\n"
                f"오늘 확정 손익: {engine.realized_today:+,.0f}원")
        # 다른 봇(잠수함 스캐너)이 XRP를 중복 매수하지 않도록 소유권 공표
        allocation.publish_owned("xrp", engine.held())
        sig, feat, _ = shared.get()
        if not (sig and engine.has_room()):
            return
        if args.live:
            # 원화가 최소주문액 미만이면 주문이 안 나가는데도 '샀다'고 기록되는
            # 유령 매수를 차단(실제 주문 없이 포지션만 생기는 버그 방지).
            avail = broker.ex.get_krw_balance()
            if avail < MIN_ORDER_KRW:
                if time.time() - _nocash["at"] > 3600:
                    log(f"⏸ 진입 신호 있지만 원화 {avail:,.0f}원(최소주문 미만) — 매수 보류")
                    _nocash["at"] = time.time()
                return
        v = news_gate()
        if v is not None and not v.allow:
            if time.time() - _newsblock["at"] > 3600:   # 신호 지속 시 반복 알림 방지
                log(f"⛔ 매수 보류 — 뉴스 악재({v.score:+d}): {v.reason}")
                notifier.send(
                    f"⛔ <b>리플 매수 보류</b>\n"
                    f"기술적 신호는 떴지만, 최근 뉴스가 강한 악재({v.score:+d})라 "
                    f"위험을 피해 이번 매수는 건너뛰었어요.\n사유: {v.reason}")
                _newsblock["at"] = time.time()
            return
        for rec in engine.try_entries([MARKET], now):
            log(f"매수 XRP @ {rec.price:,.0f}")
            notifier.send(
                f"🟢 <b>리플(XRP) 매수했어요!</b>\n"
                f"산 가격: {rec.price:,.0f}원\n투입: {args.invest:,.0f}원\n"
                f"이유: 거래량이 평소보다 크게 늘며 상승 신호(검증된 급등 패턴)가 떠서 샀어요\n"
                f"앞으로: 오르면 끝까지 따라가고, -{args.stop*100:.0f}%에 닿으면 손절해요")

    try:
        while True:
            try:
                tick(datetime_now())
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                # 일시적 네트워크/API 오류로 봇 전체가 죽어 재시작 알림이 반복되는 것 방지
                log(f"점검 루프 오류(계속 재시도): {exc}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        stop.set()
        log("리플 봇 중지")
        msg = "🛑 <b>리플 봇이 멈췄어요</b> (자동 매매 중단)"
        if engine.positions:
            msg += "\n⚠️ 아직 리플을 들고 있어요 — 봇이 멈춰서 자동 관리 안 돼요"
        notifier.send(msg)


if __name__ == "__main__":
    main()
