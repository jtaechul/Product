#!/usr/bin/env python3
"""리플(XRP) '시기 반응형' 자동매매 봇 — ⚠️ --live 시 실제 주문.

구조(3층):
  [6시간마다] 국면 판단(regime6h) → 스탠스(적극/소극/관망) → 실행층(매매)
    · 적극: 진입조건 '대폭 완화'(자주·크게)   · 소극: 검증조건으로 조심
    · 관망: 신규 매수 정지(현금으로 지키기)
  입력 = 현재 데이터: XRP·BTC 추세 + 공포탐욕지수 + 펀딩비 + Claude 뉴스 감성.

안전장치(검증 없이 실투자하므로 필수):
  · 손실 차단선(kill-switch): 누적 실현손실이 한도를 넘으면 자동 '관망'+신규매수 정지.
    (기존 보유의 청산은 계속 작동 — 지킬 건 지킨다). 재시작해도 유지(파일 영속).
  · 외부 지표 실패해도 봇은 안 죽음(심리 None → 가격·추세만으로 판단).
  · 청산 규칙(손절 -10%/트레일링 -15%)은 스탠스와 무관하게 '고정' — 보유 중 규칙이 안 바뀜.

사용:
    python -m scripts.xrp_trade                 # 모의(무주문)
    python -m scripts.xrp_trade --invest 100000 --live   # 실거래

종료: Ctrl+C
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import allocation, news_filter, notifier, regime6h, sentiment  # noqa: E402
from src.swing import SwingConfig, compute_features, is_entry  # noqa: E402
from src.swing_trader import SwingTrader  # noqa: E402
from src.timeutil import now_kst as datetime_now  # noqa: E402
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

MARKET = "KRW-XRP"
MIN_ORDER_KRW = 5000
STATE_DIR = Path(__file__).resolve().parent.parent / ".botstate"

# 스탠스별 '진입' 설정(청산 규칙과 분리). 적극 = 사용자 요청대로 대폭 완화.
STANCE_ENTRY = {
    "적극": dict(base_bars=15, recent_bars=3, self_ma_bars=0, btc_ma_bars=0,
               vol_surge=1.3, min_momentum=0.0, max_chase=0.40),   # 자주·크게
    "소극": dict(base_bars=30, recent_bars=3, self_ma_bars=50, btc_ma_bars=0,
               vol_surge=2.5, min_momentum=0.02, max_chase=0.20),  # 검증 조건
}


def log(msg: str, push: bool = False) -> None:
    print(f"[{datetime_now():%m-%d %H:%M:%S}] {msg}", flush=True)
    if push:
        notifier.send(msg)


# ───────────────────────── 브로커 ─────────────────────────
class PaperBroker:
    def __init__(self, q):
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
        return None


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


# ───────────────────────── 공유 상태 ─────────────────────────
class Shared:
    def __init__(self, exit_params: dict):
        self.lock = threading.Lock()
        self.signal = False
        self.feat = None
        self.updated_at = None
        # 국면(스탠스) — 시작은 안전하게 '소극'
        self.stance = "소극"
        self.stance_reason = "시작 — 국면 판단 대기"
        self.stance_inputs = {}
        self.entry_cfg = SwingConfig(**exit_params, **STANCE_ENTRY["소극"])
        self._exit_params = exit_params

    def set_signal(self, signal, feat):
        with self.lock:
            self.signal = signal
            self.feat = feat
            self.updated_at = datetime_now()

    def set_stance(self, st: "regime6h.Stance"):
        with self.lock:
            self.stance = st.stance
            self.stance_reason = st.reason
            self.stance_inputs = st.inputs
            if st.entry_key:                       # 적극/소극 → 해당 진입설정
                self.entry_cfg = SwingConfig(**self._exit_params,
                                             **STANCE_ENTRY[st.entry_key])
            # 관망이면 entry_cfg 는 그대로 두되(참고용), 매수는 상위에서 막음

    def get_signal(self):
        with self.lock:
            return self.signal, self.feat, self.updated_at

    def get_stance(self):
        with self.lock:
            return self.stance, self.stance_reason, self.entry_cfg, dict(self.stance_inputs)


# ───────────────────────── 신호/국면 계산 ─────────────────────────
def daily_signal(q, cfg: SwingConfig) -> tuple[bool, dict | None]:
    """현재 스탠스의 진입설정으로 XRP 일봉 '진입 신호' 계산."""
    need = cfg.base_bars + cfg.recent_bars + cfg.self_ma_bars + 2
    df = candles_to_dataframe(q.get_candles_days(MARKET, count=min(200, need)))
    if len(df) < cfg.base_bars + cfg.recent_bars + 2:
        return False, None
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    i = len(c) - 1
    feat = compute_features(c, h, v, i, cfg)
    if not is_entry(feat, cfg):
        return False, feat
    if cfg.self_ma_bars > 0 and not c[i] > c[-cfg.self_ma_bars:].mean():
        return False, feat
    return True, feat


def regime_loop(shared, q, interval, use_news, stop):
    """6시간마다 국면(스탠스)을 판단해 공유상태 갱신 + 변경 시 알림."""
    last_stance = None
    while not stop.is_set():
        try:
            xrp = candles_to_dataframe(q.get_candles_days(MARKET, count=210))
            btc = candles_to_dataframe(q.get_candles_days("KRW-BTC", count=210))
            snap = sentiment.snapshot()
            news_score = None
            if use_news:
                v = news_filter.assess()
                news_score = v.score if v.enabled else None
            st = regime6h.decide(xrp, btc, snap["fear_greed"], snap["funding"], news_score)
            shared.set_stance(st)
            log(f"🧭 국면 판단: [{st.stance}] {st.reason}")
            if last_stance is not None and st.stance != last_stance:
                notifier.send(
                    f"🧭 <b>리플 국면 전환: {last_stance} → {st.stance}</b>\n"
                    f"{st.reason}\n"
                    + ("→ 이제 진입조건을 대폭 완화해 적극적으로 노려요"
                       if st.stance == "적극" else
                       "→ 조심스럽게 검증 조건으로만 봐요" if st.stance == "소극" else
                       "→ 신규 매수를 멈추고 현금으로 지켜요"))
            last_stance = st.stance
        except Exception as exc:
            log(f"국면 판단 오류(계속): {exc}")
        stop.wait(interval)


def scanner_loop(shared, q, interval, stop):
    """현재 스탠스의 진입설정으로 신호를 주기 갱신. 관망이면 신호 없음."""
    while not stop.is_set():
        try:
            stance, _, entry_cfg, _ = shared.get_stance()
            if stance == "관망":
                shared.set_signal(False, None)
                log("🔍 관망 국면 — 신규 매수 안 함")
            else:
                sig, feat = daily_signal(q, entry_cfg)
                shared.set_signal(sig, feat)
                if sig:
                    log(f"🔍 [{stance}] 진입 신호 ON — 거래량 {feat['surge']:.1f}배, "
                        f"박스돌파 {feat['breakout']*100:+.1f}%")
                else:
                    log(f"🔍 [{stance}] 신호 없음 — 대기")
        except Exception as exc:
            log(f"신호 계산 오류(계속): {exc}")
        stop.wait(interval)


# ───────────────────────── 손실 차단선 ─────────────────────────
class KillSwitch:
    """누적 실현손익을 영속 추적. 한도 초과 시 killed=True(신규매수 정지)."""
    def __init__(self, limit: float, path: Path):
        self.limit = abs(limit)
        self.path = path
        self.cum = 0.0
        try:
            self.cum = float(json.loads(path.read_text()).get("cum", 0.0))
        except Exception:
            pass
        self.killed = self.cum <= -self.limit

    def add(self, pnl: float) -> bool:
        """실현손익 반영. 이번에 '새로' 발동됐으면 True."""
        self.cum += pnl
        try:
            self.path.write_text(json.dumps({"cum": self.cum}), encoding="utf-8")
        except Exception:
            pass
        if not self.killed and self.cum <= -self.limit:
            self.killed = True
            return True
        return False


# ───────────────────────── 메인 ─────────────────────────
def main() -> None:
    p = argparse.ArgumentParser(description="리플(XRP) 시기 반응형 자동매매 봇")
    p.add_argument("--invest", type=float, default=100_000)
    p.add_argument("--interval", type=float, default=10.0, help="보유 감시(초)")
    p.add_argument("--scan-interval", type=int, default=1800, help="신호 점검(초)")
    p.add_argument("--regime-interval", type=int, default=21600, help="국면 판단(초, 기본 6h)")
    p.add_argument("--trail", type=float, default=0.15)
    p.add_argument("--stop", type=float, default=0.10)
    p.add_argument("--arm", type=float, default=0.06)
    p.add_argument("--max-hold-days", type=int, default=30)
    p.add_argument("--cooldown", type=int, default=24, help="매도 후 재진입 쿨다운(시간)")
    p.add_argument("--take-profit", type=float, default=0.0)
    p.add_argument("--loss-limit", type=float, default=30000,
                   help="누적 실현손실 이 값 도달 시 자동 관망·신규매수 정지(0=끔)")
    p.add_argument("--news", choices=["auto", "off"], default="auto")
    p.add_argument("--live", action="store_true")
    args = p.parse_args()

    exit_params = dict(trail=args.trail, stop_loss=args.stop, arm_profit=args.arm,
                       max_hold_bars=args.max_hold_days * 24,
                       take_profit=(args.take_profit if args.take_profit > 0 else None))
    exit_cfg = SwingConfig(btc_ma_bars=0, **exit_params)   # 엔진 청산용(고정)
    q = UpbitQuotation()

    if args.live:
        if args.invest < MIN_ORDER_KRW:
            log(f"중단: 매수액이 최소주문({MIN_ORDER_KRW})보다 작음"); sys.exit(1)
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        try:
            broker = LiveBroker(q, UpbitExchange())
        except MissingApiKeyError as exc:
            log(f"중단: {exc}"); sys.exit(1)
        print("=" * 60)
        print("🔴 실거래(LIVE) — 실제 주문! 5초 후 시작 (Ctrl+C 취소)")
        print(f"   리플(XRP) / 매수 {args.invest:,.0f}원 / 손실차단 -{args.loss_limit:,.0f}원")
        print("=" * 60)
        time.sleep(5)
    else:
        broker = PaperBroker(q)
        log(f"🟡 모의(무주문). 리플(XRP) / 매수 {args.invest:,.0f}원")

    engine = SwingTrader(
        broker=broker, cfg=exit_cfg, max_positions=1, invest_per_trade=args.invest,
        cooldown_hours=args.cooldown, state_path=str(STATE_DIR / "positions_xrp.json"))
    engine.load_state()
    engine.adopt_holdings()
    # XRP 전용 — 계좌의 다른 코인은 절대 관리/매도하지 않음(흡수된 것 즉시 제외)
    for _m in [k for k in engine.positions if k != MARKET]:
        del engine.positions[_m]
    engine.save_state()

    kill = KillSwitch(args.loss_limit, STATE_DIR / "xrp_pnl.json") if args.loss_limit > 0 \
        else None

    shared = Shared(exit_params)
    stop = threading.Event()
    threading.Thread(target=regime_loop,
                     args=(shared, q, args.regime_interval, args.news != "off", stop),
                     daemon=True).start()
    threading.Thread(target=scanner_loop,
                     args=(shared, q, args.scan_interval, stop), daemon=True).start()

    mode_txt = "🔴 실거래(진짜 돈)" if args.live else "🟡 모의(가짜 돈)"
    log(f"리플 봇 시작 ({'🔴실거래' if args.live else '🟡모의'})")
    kill_txt = (f"• 누적 손실이 -{args.loss_limit:,.0f}원에 닿으면 자동으로 멈춰요(안전장치)\n"
                if kill else "")
    notifier.send(
        f"🤖 <b>리플(XRP) 봇 시작</b> ({mode_txt})\n"
        f"• 6시간마다 시국을 보고 <b>적극/소극/관망</b>을 스스로 정해요\n"
        f"• 적극이면 자주·크게, 관망이면 현금으로 지켜요\n"
        f"• 판단 근거: XRP·비트코인 추세 + 공포탐욕지수 + 펀딩비 + 뉴스\n"
        + kill_txt
        + f"• 고점 -{args.trail*100:.0f}% 이익보존 매도 / -{args.stop*100:.0f}% 손절")

    def reason_easy(r: str) -> str:
        if r.startswith("손절"):
            return f"손실이 한도(-{args.stop*100:.0f}%)에 닿아 더 큰 손실을 막으려고 팔았어요"
        if r.startswith("트레일링"):
            return "고점에서 내려와 벌어둔 이익을 지키려고 팔았어요"
        if r.startswith("익절"):
            return "목표 수익에 도달해 이익을 확정했어요"
        if r.startswith("보유초과"):
            return f"최대 보유기간({args.max_hold_days}일)이 지나 정리했어요"
        return r

    def status() -> str:
        sig, feat, upd = shared.get_signal()
        stance, sreason, _, inp = shared.get_stance()
        n = len(engine.positions)
        sells = sum(1 for t in engine.trades if t.action == "SELL")
        icon = {"적극": "🔥", "소극": "🐢", "관망": "🛡️"}.get(stance, "")
        out = ["🪙 <b>리플(XRP) 봇 현황</b>", "",
               f"<b>[국면] {icon} {stance}</b>", f"• {sreason}"]
        fg = inp.get("fear_greed"); fd = inp.get("funding")
        out.append(f"• 공포탐욕 {fg if fg is not None else 'N/A'} · "
                   f"펀딩 {f'{fd*100:+.3f}%' if fd is not None else 'N/A'}")
        if kill:
            out.append(f"• 누적 확정손익 {kill.cum:+,.0f}원 "
                       f"(차단선 -{kill.limit:,.0f}원){' ⛔정지' if kill.killed else ''}")
        out += ["", "<b>[신호]</b>"]
        if stance == "관망":
            out.append("• 관망 국면 — 신규 매수 안 함")
        elif sig and feat:
            out.append(f"• 진입 신호 ON — 거래량 {feat.get('surge',0):.1f}배")
        else:
            out.append("• 신호 없음 — 대기 중")
        out += ["", "<b>[내 거래]</b>"]
        if n == 0:
            out.append("• 보유: 없음 (현금)")
        else:
            try:
                price = broker.get_prices([MARKET]).get(MARKET)
            except Exception:
                price = None
            pos = engine.positions.get(MARKET)
            if pos and price:
                g = price / pos.entry_price - 1.0
                won = None
                try:
                    h = broker.get_holdings()
                    if h and MARKET in h:
                        won = (price - pos.entry_price) * h[MARKET][0]
                except Exception:
                    pass
                out.append(f"• 보유 중: 지금 {g*100:+.1f}% ({(won if won is not None else g*args.invest):+,.0f}원)")
            else:
                out.append("• 보유 중")
        out.append(f"• 오늘 확정 손익: {engine.realized_today:+,.0f}원 (매도 {sells}회)")
        return "\n".join(out)

    notifier.run_shared("4_리플", status, stop=stop)

    _nocash = {"at": 0.0}

    def tick(now) -> None:
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
            if kill and kill.add(won):     # 손실 차단선 발동
                log("⛔ 손실 차단선 도달 — 신규 매수 정지(관망)")
                notifier.send(
                    f"⛔ <b>리플 봇 안전정지</b>\n"
                    f"누적 확정손실이 한도(-{kill.limit:,.0f}원)에 닿아 "
                    f"<b>신규 매수를 멈췄어요</b>. 지금 보유분 관리는 계속합니다.\n"
                    f"다시 켜려면 알려주세요(손실차단 해제).")
        allocation.publish_owned("xrp", engine.held())

        stance, _, _, _ = shared.get_stance()
        if kill and kill.killed:      # 안전정지: 신규 매수 금지
            return
        if stance == "관망":
            return
        sig, feat, _ = shared.get_signal()
        if not (sig and engine.has_room()):
            return
        if args.live:
            avail = broker.ex.get_krw_balance()
            if avail < MIN_ORDER_KRW:
                if time.time() - _nocash["at"] > 3600:
                    log(f"⏸ 신호 있으나 원화 {avail:,.0f}원(최소주문 미만) — 매수 보류")
                    _nocash["at"] = time.time()
                return
        for rec in engine.try_entries([MARKET], now):
            log(f"매수 XRP @ {rec.price:,.0f} [{stance}]")
            notifier.send(
                f"🟢 <b>리플(XRP) 매수!</b> (국면: {stance})\n"
                f"산 가격: {rec.price:,.0f}원\n투입: {args.invest:,.0f}원\n"
                f"이유: {stance} 국면 + 거래량 급등 신호가 떠서 샀어요\n"
                f"앞으로: 오르면 따라가고, -{args.stop*100:.0f}%에 손절해요")

    try:
        while True:
            try:
                tick(datetime_now())
            except KeyboardInterrupt:
                raise
            except Exception as exc:
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
