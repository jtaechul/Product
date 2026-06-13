#!/usr/bin/env python3
"""대형코인(BTC·ETH) 추세필터 레짐 자동매매 봇 — ⚠️ --live 시 실제 주문.

전략(src/majors.py): 각 코인의 일봉 종가가 50일 이동평균 '위' + MA 우상향이면 보유,
아니면 현금. 약세장 폭락을 피해 최대낙폭을 줄이는 '위험 대비 수익' 중심 전략입니다.
(optimize_majors 교차검증: 일봉/시간봉 OOS에서 BTC·ETH 둘 다 흑자, 연승률 71%)

· 자금은 코인 수만큼 균등 배분(BTC·ETH 각 50%). 조건 충족 시 매수, 이탈 시 전량 매도.
· 실거래 시 '실제 업비트 잔고'와 동기화(현행화)하여 재시작/수동매수분도 인식·관리.
· 일봉 레짐이라 매매가 드뭅니다(전환 시에만). 가벼워 클라우드 24시간 가동에 적합.

사용:
    python -m scripts.majors_trade                       # 모의(실시세, 무주문)
    python -m scripts.majors_trade --invest 100000       # 총 10만 → 코인당 5만
    python -m scripts.majors_trade --invest 100000 --live  # 소액 실거래

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
from src.majors import MajorsConfig, regime  # noqa: E402
from src.timeutil import now_kst  # 한국시간(KST) 표시  # noqa: E402
from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402

MIN_ORDER_KRW = 5000


def log(msg: str, push: bool = False) -> None:
    print(f"[{now_kst():%m-%d %H:%M:%S}] {msg}", flush=True)
    if push:
        notifier.send(msg)


class PaperBroker:
    def __init__(self, q: UpbitQuotation):
        self.q = q

    def get_prices(self, markets):
        return {t["market"]: float(t["trade_price"]) for t in self.q.get_ticker(markets)}

    def get_daily(self, market, count=120):
        return candles_to_dataframe(self.q.get_candles_days(market, count=min(200, count)))

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


class Position:
    __slots__ = ("entry_price", "krw")

    def __init__(self, entry_price: float, krw: float):
        self.entry_price = entry_price
        self.krw = krw


def main() -> None:
    p = argparse.ArgumentParser(description="대형코인 추세필터 레짐 자동매매 봇")
    p.add_argument("--invest", type=float, default=300_000,
                   help="총 투자금(코인 수로 균등 분할)")
    p.add_argument("--ma", type=int, default=50,
                   help="추세 이동평균 기간(일). 교차검증 기본값 50")
    p.add_argument("--buffer", type=float, default=0.0,
                   help="MA 대비 ±완충 밴드(휩쏘 완화). 기본 0(기울기필터가 대체)")
    p.add_argument("--slope", type=int, default=10,
                   help="MA가 N일 전보다 높을 때만 보유(우상향 확인). 기본 10, 0=끔")
    p.add_argument("--coins", default="KRW-BTC,KRW-ETH",
                   help="대상 마켓 콤마구분 (기본 BTC,ETH — XRP 제외)")
    p.add_argument("--interval", type=int, default=1800,
                   help="레짐 점검 주기(초). 일봉 전략이라 기본 30분")
    p.add_argument("--live", action="store_true")
    args = p.parse_args()

    coins = tuple(c.strip() for c in args.coins.split(",") if c.strip())
    cfg = MajorsConfig(coins=coins, ma_bars=args.ma, buffer=args.buffer,
                       slope_bars=args.slope)
    per_coin = args.invest / len(coins)
    q = UpbitQuotation()

    if args.live:
        if per_coin < MIN_ORDER_KRW:
            log(f"중단: 코인당 매수액({per_coin:,.0f})이 최소주문({MIN_ORDER_KRW})보다 작음")
            sys.exit(1)
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        try:
            broker = LiveBroker(q, UpbitExchange())
        except MissingApiKeyError as exc:
            log(f"중단: {exc}")
            sys.exit(1)
        print("=" * 60)
        print("🔴 실거래(LIVE) — 실제 주문이 나갑니다! 5초 후 시작 (Ctrl+C 취소)")
        print(f"   대상 {len(coins)}종목 / 종목당 {per_coin:,.0f}원")
        print("=" * 60)
        time.sleep(5)
    else:
        broker = PaperBroker(q)
        log(f"🟡 모의(실시세, 무주문). 대상 {len(coins)}종목 / 종목당 {per_coin:,.0f}원")

    positions: dict[str, Position] = {}   # 보유 중인 코인 {market: Position}
    realized = 0.0                          # 누적 확정 손익
    pl_label = "확정 손익" if args.live else "확정 손익(모의)"
    last = {"info": {}, "at": None}         # 마지막 점검 결과(상태조회용)
    lock = threading.Lock()
    stop = threading.Event()

    def nm(market: str) -> str:
        return market.replace("KRW-", "")

    def reconcile_holdings(prices):
        """실거래: 실제 업비트 잔고와 봇의 positions 를 맞춘다(현행화).

        · 거래소엔 있는데 봇이 모르는 보유분 → 인식(평단가로 편입) — 재시작·수동매수 대응
        · 봇은 보유로 아는데 거래소엔 없음(외부 매도/소진) → 제거
        대상은 cfg.coins(BTC·ETH)로 한정 — 다른 코인/봇 자산은 건드리지 않음.
        """
        try:
            holdings = broker.get_holdings()
        except Exception as exc:
            log(f"잔고 동기화 오류(계속): {exc}")
            return
        if holdings is None:        # 모의 모드 → 메모리 상태 유지
            return
        for c in coins:
            real = holdings.get(c)
            cur = prices.get(c, 0.0)
            real_val = real[0] * (cur or real[1]) if real else 0.0
            if real and real_val >= MIN_ORDER_KRW:
                if c not in positions:
                    vol, avg = real
                    entry = avg if avg > 0 else (cur or avg)
                    positions[c] = Position(entry, vol * entry)
                    log(f"🔄 기존 보유 인식: {nm(c)} 수량 {vol:.6f} 평단 {entry:,.0f}")
                    notifier.send(
                        f"🔄 <b>기존 보유 코인을 봇이 인식했어요</b>\n"
                        f"종목: <b>{nm(c)}</b>\n평단가: {entry:,.0f}원\n"
                        f"이제부터 이 코인도 전략(50일선)에 따라 감시·관리합니다")
            elif c in positions:    # 거래소에 없음 → 봇 기록 정리
                positions.pop(c, None)
                log(f"🔄 보유 해제 인식: {nm(c)} (거래소 잔고 없음)")

    mode_txt = ("🔴 실거래(진짜 돈)" if args.live
                else "🟡 모의(가짜 돈, 실제 주문 안 함)")
    log(f"대형코인 레짐 봇 시작 ({'🔴실거래' if args.live else '🟡모의'})")
    notifier.send(
        f"🏔️ <b>대형코인 봇이 시작됐어요</b>  ({mode_txt})\n"
        f"• 대상: {', '.join(nm(c) for c in coins)} (총 {args.invest:,.0f}원, "
        f"종목당 {per_coin:,.0f}원)\n"
        f"• 규칙: 각 코인이 {args.ma}일 평균선 <b>위</b>면 보유, <b>아래</b>면 팔고 현금 보관\n"
        f"• 폭락장을 피해 손실 폭을 줄이는 '안전 위주' 전략이에요\n"
        f"• 사고팔 때마다 여기로 알려드릴게요. 궁금하면 아무 메시지나 보내세요")
    if notifier.enabled():
        log("텔레그램 알림 연결됨")

    def status() -> str:
        with lock:
            info = dict(last["info"])
            at = last["at"]
        out = ["🏔️ <b>대형코인 현황</b>", "", "<b>[코인별 추세]</b>"]
        if not info:
            out.append("• 아직 첫 점검 전이에요…")
        prices = {}
        try:
            prices = broker.get_prices(list(coins))
        except Exception:
            pass
        for c in coins:
            r = info.get(c)
            if not r:
                continue
            above = "위 ✅ 보유" if r["in_market"] else "아래 ⛔ 현금"
            held = c in positions
            tag = "보유중" if held else "현금"
            line = (f"• {nm(c)}: {args.ma}일선 대비 {r['dist']*100:+.1f}% "
                    f"({above}) — 지금 {tag}")
            if held:
                cur = prices.get(c, positions[c].entry_price)
                g = cur / positions[c].entry_price - 1.0
                line += f", 평가손익 {g*100:+.1f}%"
            out.append(line)
        if at:
            out.append(f"\n• 마지막 점검: {at:%m-%d %H:%M} (한국시간)")
        out.append(f"• 보유 종목: {len(positions)}/{len(coins)}개")
        out.append(f"• 누적 {pl_label}: {realized:+,.0f}원")
        return "\n".join(out)

    # 공유 상태 체제: 잠수함+대형코인 봇이 한 채팅을 공유 → '상태' 한 번에 두 봇 정보가
    # 합쳐서 나온다(이름 접두 2_ 로 잠수함 다음에 표시). 하트비트도 합쳐서 한 번만.
    notifier.run_shared("2_대형코인", status, stop=stop)
    if notifier.enabled():
        log("텔레그램에 아무 말이나 보내면 두 봇 상태를 한 번에 회신합니다")

    try:
        while True:
            info = {}
            try:
                prices = broker.get_prices(list(coins))
            except Exception as exc:
                log(f"시세 조회 오류(계속): {exc}")
                stop.wait(args.interval)
                continue

            # 실제 업비트 잔고와 동기화(현행화) — 재시작/수동매수분도 인식·관리
            reconcile_holdings(prices)

            # 배정 예산(대형코인 몫)을 종목 수로 나눠 1종목 매수액 산출(배분 변화 즉시 반영)
            per_coin = allocation.budget_for("majors", args.invest) / len(coins)
            allocation.publish_owned("majors", list(positions.keys()))

            for c in coins:
                try:
                    df = broker.get_daily(c, count=args.ma + args.slope + 15)
                    # 마지막 봉은 '오늘(아직 안 닫힌)' 캔들 → 제외하고 '어제 종가까지'로 판정
                    # (장중 잔떨림 방지 + 백테스트와 동일한 '닫힌 봉' 기준)
                    if df is not None and len(df) > 1:
                        df = df.iloc[:-1].reset_index(drop=True)
                    if df is None or len(df) < args.ma + args.slope + 1:
                        continue
                    held = c in positions
                    r = regime(df, cfg, held=held)
                    info[c] = r
                    price = prices.get(c, r["price"])

                    # 추세선 위(+우상향) + 미보유 → 매수
                    if r["in_market"] and not held:
                        broker.buy(c, per_coin, price)
                        positions[c] = Position(price, per_coin)
                        log(f"매수 {nm(c)} @ {price:,.0f}")
                        notifier.send(
                            f"🟢 <b>매수했어요!</b>\n"
                            f"종목: <b>{nm(c)}</b>\n"
                            f"산 가격: {price:,.0f}원\n"
                            f"투입: {per_coin:,.0f}원\n"
                            f"이유: {nm(c)}가 {args.ma}일 평균선 위로 올라서 "
                            f"상승추세에 올라탔어요(+{r['dist']*100:.1f}%)")
                    # 200일선 아래 + 보유 → 전량 매도(현금화)
                    elif (not r["in_market"]) and held:
                        broker.sell(c, price)
                        pos = positions.pop(c)
                        g = price / pos.entry_price - 1.0
                        won = g * pos.krw
                        realized += won
                        head = ("✅ <b>매도 — 이익 실현 🎉</b>" if g > 0
                                else "🔻 <b>매도 — 손실 정리</b>")
                        log(f"매도 {nm(c)} ({g*100:+.1f}%) — 200일선 이탈")
                        notifier.send(
                            f"{head}\n"
                            f"종목: <b>{nm(c)}</b>\n"
                            f"판 가격: {price:,.0f}원\n"
                            f"결과: <b>{g*100:+.1f}% ({won:+,.0f}원)</b>\n"
                            f"이유: {nm(c)}가 {args.ma}일 평균선 아래로 내려가 "
                            f"위험을 피해 팔고 현금으로 뒀어요\n"
                            f"누적 {pl_label}: {realized:+,.0f}원")
                except Exception as exc:
                    log(f"{nm(c)} 점검 오류(계속): {exc}")

            with lock:
                last["info"] = info
                last["at"] = now_kst()

            if positions:
                held = ", ".join(nm(c) for c in positions)
                log(f"보유 {len(positions)}/{len(coins)}: {held} | 확정 {realized:+,.0f}원")
            else:
                log(f"전량 현금(보유 없음) | 확정 {realized:+,.0f}원")
            stop.wait(args.interval)
    except KeyboardInterrupt:
        stop.set()
        log("대형코인 봇 중지")
        msg = "🛑 <b>대형코인 봇이 멈췄어요</b> (자동 매매 안 함)"
        if positions:
            msg += f"\n⚠️ 아직 보유: {', '.join(nm(c) for c in positions)} — 자동 관리 중단됨"
        msg += f"\n누적 {pl_label}: {realized:+,.0f}원"
        notifier.send(msg)


if __name__ == "__main__":
    main()
