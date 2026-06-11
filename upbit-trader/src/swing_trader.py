"""스윙 실시간 매매 엔진 — '실시간 모니터링 → 빠른 진입 → 인내 청산'.

검증된 swing.py 로직(독립표본 3종에서 t>4)을 실거래/모의에 그대로 얹습니다.
1분봉 스캘핑 엔진(auto_trader)과 달리, 의사결정은 시간봉 스케일이지만
진입 '순간'은 실시간으로 빠르게 잡고, 하드 손절은 현재가로 초단위 감시합니다.

흐름:
  · 스캐너: 주기적으로 전체 마켓의 60분봉을 받아 swing.is_entry 로 후보 선별
  · 보유 감시(빠름): 현재가 일괄조회로 하드 손절/트레일링/보유시간 체크
  · 진입: 후보에 자리가 나면 매수 (동시 보유 상한 + 추세 게이트 + 쿨다운)

Broker 추상화로 모의(PaperBroker)·실거래(LiveBroker)를 같은 엔진으로 돌립니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd

from .swing import SwingConfig, _trail_for, compute_features, is_entry


class Broker(Protocol):
    def get_prices(self, markets: list[str]) -> dict[str, float]: ...
    def get_candles_60m(self, market: str, count: int = 200) -> pd.DataFrame: ...
    def buy(self, market: str, krw: float, price: float) -> float: ...
    def sell(self, market: str, price: float) -> float: ...


@dataclass
class SwingPosition:
    market: str
    entry_price: float
    entry_time: datetime
    peak_price: float = 0.0
    armed: bool = False

    def __post_init__(self):
        if self.peak_price <= 0:
            self.peak_price = self.entry_price

    def update(self, price: float, arm_profit: float):
        self.peak_price = max(self.peak_price, price)
        if not self.armed and price >= self.entry_price * (1 + arm_profit):
            self.armed = True


@dataclass
class SwingRecord:
    time: datetime
    market: str
    action: str
    price: float
    gain: float = 0.0
    reason: str = ""


def decide_swing_exit(pos: SwingPosition, price: float, cfg: SwingConfig,
                      now: datetime) -> tuple[bool, str]:
    """현재가/시간 기준 스윙 청산 판정 (백테스트 backtest_coin 과 동일 규칙)."""
    # 하드 손절 — 최우선
    if price <= pos.entry_price * (1 - cfg.stop_loss):
        return True, f"손절(-{cfg.stop_loss*100:.0f}%)"
    if cfg.take_profit is not None and price >= pos.entry_price * (1 + cfg.take_profit):
        return True, f"익절(+{cfg.take_profit*100:.0f}%)"
    if pos.armed:
        trail = _trail_for(cfg, pos.peak_price / pos.entry_price - 1.0)
        if price <= pos.peak_price * (1 - trail):
            return True, f"트레일링(고점-{trail*100:.0f}%)"
    held_h = (now - pos.entry_time).total_seconds() / 3600.0
    if held_h >= cfg.max_hold_bars:  # max_hold_bars 는 1h 기준 = 시간 수
        return True, f"보유초과({cfg.max_hold_bars}h)"
    return False, ""


@dataclass
class SwingTrader:
    broker: Broker
    cfg: SwingConfig = field(default_factory=SwingConfig)
    max_positions: int = 3
    invest_per_trade: float = 100_000
    cooldown_hours: int = 12
    daily_loss_limit: float | None = None

    positions: dict[str, SwingPosition] = field(default_factory=dict)
    cooldowns: dict[str, datetime] = field(default_factory=dict)
    trades: list[SwingRecord] = field(default_factory=list)
    realized_today: float = 0.0
    _day: object = None
    halted: bool = False

    def held(self) -> list[str]:
        return list(self.positions.keys())

    def has_room(self) -> bool:
        return len(self.positions) < self.max_positions

    def _roll_day(self, now):
        if self._day != now.date():
            self._day = now.date()
            self.realized_today = 0.0
            self.halted = False

    def check_exits(self, now: datetime) -> list[SwingRecord]:
        self._roll_day(now)
        if not self.positions:
            return []
        prices = self.broker.get_prices(self.held())
        done = []
        for m, pos in list(self.positions.items()):
            price = prices.get(m)
            if not price or price <= 0:
                continue
            pos.update(price, self.cfg.arm_profit)
            should, reason = decide_swing_exit(pos, price, self.cfg, now)
            if should:
                fill = self.broker.sell(m, price)
                gain = fill / pos.entry_price - 1.0
                self.realized_today += self.invest_per_trade * gain
                rec = SwingRecord(now, m, "SELL", fill, gain, reason)
                self.trades.append(rec)
                done.append(rec)
                del self.positions[m]
                self.cooldowns[m] = now + timedelta(hours=self.cooldown_hours)
                if (self.daily_loss_limit is not None
                        and self.realized_today <= -abs(self.daily_loss_limit)):
                    self.halted = True
        return done

    def try_entries(self, candidates: list[str], now: datetime) -> list[SwingRecord]:
        self._roll_day(now)
        if self.halted:
            return []
        done = []
        for m in candidates:
            if not self.has_room():
                break
            if m in self.positions:
                continue
            until = self.cooldowns.get(m)
            if until and now < until:
                continue
            price = self.broker.get_prices([m]).get(m)
            if not price or price <= 0:
                continue
            fill = self.broker.buy(m, self.invest_per_trade, price)
            self.positions[m] = SwingPosition(m, fill, now)
            self.trades.append(SwingRecord(now, m, "BUY", fill))
            done.append(self.trades[-1])
        return done


def scan_candidates(broker: Broker, markets: list[str], cfg: SwingConfig,
                    btc_ok: bool = True, top: int = 20) -> list[tuple[str, dict]]:
    """60분봉으로 진입 신호가 뜬 마켓을 점수(거래량 급증)순으로 반환.

    btc_ok: 시장 추세 게이트 결과(BTC가 자기 MA 위인지). False면 전부 보류.
    """
    if not btc_ok:
        return []
    need = cfg.base_bars + cfg.recent_bars + cfg.self_ma_bars + 2
    out = []
    for m in markets:
        try:
            df = broker.get_candles_60m(m, count=need)
        except Exception:
            continue
        if len(df) < need - 1:
            continue
        c = df["close"].to_numpy(float)
        h = df["high"].to_numpy(float)
        v = df["volume"].to_numpy(float)
        i = len(c) - 1
        feat = compute_features(c, h, v, i, cfg)
        if not is_entry(feat, cfg):
            continue
        # 코인 자체 추세 게이트
        if cfg.self_ma_bars > 0:
            ma = c[-cfg.self_ma_bars:].mean()
            if not c[i] > ma:
                continue
        out.append((m, feat))
    out.sort(key=lambda x: x[1]["surge"], reverse=True)
    return out[:top]
