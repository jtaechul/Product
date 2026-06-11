"""스캐너 + 추적기 통합 자동매매 엔진 (4단계).

전체 흐름:
  · 백그라운드 스캐너(5분봉)가 급등 후보 목록을 계속 갱신
  · 엔진은 보유 코인을 '현재가 일괄 조회'로 빠르게(기본 2초) 감시 → 청산
  · 자리가 비면 후보 중 1분봉 진입 트리거가 뜬 코인을 매수 (최대 동시 보유 제한)

수익 극대화 / 손실 최소화 장치:
  · 트레일링 스탑 + 손절 하한 + 본전 스탑 + 단계별 트레일링 (tracker.ExitConfig)
  · 일일 손실 한도: 하루 누적 실현손익이 한도 이하로 떨어지면 신규 진입 중단
  · 재진입 쿨다운: 청산한 코인은 일정 시간 재진입 금지(끝난 펌프 추격 방지)

Broker 추상화로 모의(PaperBroker)·실거래(LiveBroker)를 동일 엔진으로 돌립니다.
보유 감시는 캔들이 아닌 '현재가 일괄 조회(get_prices)'라 종목이 늘어도 API 1회/틱.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

import pandas as pd

from .tracker import ExitConfig, Position, decide_entry, decide_exit


class Broker(Protocol):
    """매매/시세 인터페이스 (모의·실거래 공통)."""

    def get_prices(self, markets: list[str]) -> dict[str, float]:
        """여러 마켓의 현재가를 한 번에 반환."""
        ...

    def get_candles_1m(self, market: str, count: int = 60) -> pd.DataFrame:
        """1분봉 OHLCV DataFrame."""
        ...

    def buy(self, market: str, krw: float, price: float) -> float:
        """시장가 매수. 체결 추정가를 반환."""
        ...

    def sell(self, market: str, price: float) -> float:
        """보유 전량 시장가 매도. 체결 추정가를 반환."""
        ...


@dataclass
class TradeRecord:
    time: datetime
    market: str
    action: str       # "BUY" / "SELL"
    price: float
    gain_pct: float = 0.0   # 매도 시 수익률
    reason: str = ""


@dataclass
class AutoTrader:
    """다종목 자동매매 엔진."""

    broker: Broker
    exit_cfg: ExitConfig = field(default_factory=ExitConfig)
    max_positions: int = 3            # 동시 보유 종목 수 상한
    invest_per_trade: float = 10_000  # 1종목 매수 금액(원)
    cooldown_min: int = 30            # 청산 후 재진입 금지 시간(분)
    daily_loss_limit: float | None = None  # 일일 누적 손실 한도(원, None=무제한)
    # 연속 손실 쿨다운 점증: 같은 코인에서 연속으로 잃을수록 재진입 금지를
    # 배수로 연장. 백테스트에서는 득실이 엇갈려 기본 끔(1.0).
    loss_cooldown_mult: float = 1.0   # 1.0 이면 점증 없음
    max_cooldown_min: int = 480       # 쿨다운 상한(분)
    # 코인별 주간 브레이크: 최근 brake_window_days 일 누적 손익이
    # -brake_loss_pct 이하인 코인은 brake_block_days 일 진입 금지.
    # 고변동 장세의 느린 출혈 차단 (실데이터: ZEC -19.7% → -11.8%, 2024 무영향)
    brake_loss_pct: float | None = 0.04
    brake_window_days: int = 7
    brake_block_days: int = 3

    positions: dict[str, Position] = field(default_factory=dict)
    cooldowns: dict[str, datetime] = field(default_factory=dict)
    loss_streak: dict[str, int] = field(default_factory=dict)
    market_pnls: dict[str, list] = field(default_factory=dict)
    trades: list[TradeRecord] = field(default_factory=list)
    realized_today: float = 0.0
    _day: date | None = None
    halted: bool = False  # 일일 손실 한도 도달로 신규 진입 중단됨

    # --- 상태 조회 --------------------------------------------------------
    def held_markets(self) -> list[str]:
        return list(self.positions.keys())

    def has_room(self) -> bool:
        return len(self.positions) < self.max_positions

    def _in_cooldown(self, market: str, now: datetime) -> bool:
        until = self.cooldowns.get(market)
        return until is not None and now < until

    def _roll_day(self, now: datetime) -> None:
        """날짜가 바뀌면 일일 손익/중단 상태를 초기화."""
        if self._day != now.date():
            self._day = now.date()
            self.realized_today = 0.0
            self.halted = False

    # --- 청산 감시 (빠른 주기) -------------------------------------------
    def check_exits(self, now: datetime) -> list[TradeRecord]:
        """보유 코인 현재가를 일괄 조회해 청산 조건을 검사."""
        self._roll_day(now)
        if not self.positions:
            return []

        prices = self.broker.get_prices(self.held_markets())
        done: list[TradeRecord] = []
        for market, pos in list(self.positions.items()):
            price = prices.get(market)
            if price is None or price <= 0:
                continue
            pos.update(price, self.exit_cfg.arm_profit_pct)
            should_exit, reason = decide_exit(pos, price, self.exit_cfg, now)
            if should_exit:
                fill = self.broker.sell(market, price)
                gain = pos.gain_pct(fill)
                pnl = self.invest_per_trade * gain
                self.realized_today += pnl
                rec = TradeRecord(now, market, "SELL", fill, gain, reason)
                self.trades.append(rec)
                done.append(rec)
                del self.positions[market]
                # 연속 손실이면 쿨다운 점증
                self.loss_streak[market] = (
                    self.loss_streak.get(market, 0) + 1 if pnl < 0 else 0
                )
                cd = self.cooldown_min * self.loss_cooldown_mult ** max(
                    0, self.loss_streak[market] - 1)
                self.cooldowns[market] = now + timedelta(
                    minutes=min(cd, self.max_cooldown_min))
                # 코인별 주간 브레이크: 최근 누적 손실 한도 초과 시 장기 차단
                if self.brake_loss_pct is not None:
                    hist = self.market_pnls.setdefault(market, [])
                    hist.append((now, gain))
                    cutoff = now - timedelta(days=self.brake_window_days)
                    hist[:] = [(t, p) for t, p in hist if t >= cutoff]
                    if sum(p for _, p in hist) <= -abs(self.brake_loss_pct):
                        until = now + timedelta(days=self.brake_block_days)
                        if self.cooldowns.get(market, now) < until:
                            self.cooldowns[market] = until
                        hist.clear()
                # 일일 손실 한도 점검
                if (
                    self.daily_loss_limit is not None
                    and self.realized_today <= -abs(self.daily_loss_limit)
                ):
                    self.halted = True
        return done

    # --- 진입 (자리가 빌 때) ---------------------------------------------
    def try_entries(
        self, candidate_markets: list[str], now: datetime
    ) -> list[TradeRecord]:
        """후보 목록에서 진입 조건을 만족하는 코인을 매수."""
        self._roll_day(now)
        if self.halted:
            return []

        done: list[TradeRecord] = []
        for market in candidate_markets:
            if not self.has_room():
                break
            if market in self.positions or self._in_cooldown(market, now):
                continue
            try:
                df = self.broker.get_candles_1m(market)
            except Exception:
                continue
            if not decide_entry(df):
                continue
            price = float(df["close"].iloc[-1])
            fill = self.broker.buy(market, self.invest_per_trade, price)
            self.positions[market] = Position(market, fill, now)
            self.trades.append(TradeRecord(now, market, "BUY", fill))
            done.append(self.trades[-1])
        return done


# --- 모의 브로커 (dry-run / 테스트) --------------------------------------
class PaperBroker:
    """실주문 없이 동작하는 모의 브로커.

    실거래 시엔 LiveBroker(scripts/auto_trade.py)가 같은 인터페이스로 대체합니다.
    가격/캔들은 외부(실시간 시세 또는 테스트 픽스처)에서 주입합니다.
    """

    def __init__(self, quotation=None):
        self.quotation = quotation
        # 테스트용 주입 슬롯 (quotation 이 없을 때 사용)
        self.price_feed: dict[str, float] = {}
        self.candle_feed: dict[str, pd.DataFrame] = {}

    def get_prices(self, markets: list[str]) -> dict[str, float]:
        if self.quotation is not None:
            tickers = self.quotation.get_ticker(markets)
            return {t["market"]: float(t["trade_price"]) for t in tickers}
        return {m: self.price_feed.get(m, 0.0) for m in markets}

    def get_candles_1m(self, market: str, count: int = 60) -> pd.DataFrame:
        if self.quotation is not None:
            from .upbit_quotation import candles_to_dataframe
            candles = self.quotation.get_candles_minutes(market, unit=1, count=count)
            return candles_to_dataframe(candles)
        return self.candle_feed.get(market, pd.DataFrame())

    def buy(self, market: str, krw: float, price: float) -> float:
        return price  # 모의: 현재가에 체결됐다고 가정

    def sell(self, market: str, price: float) -> float:
        return price
