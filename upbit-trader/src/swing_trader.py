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

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

import pandas as pd

from .swing import SwingConfig, _trail_for, compute_features, is_entry

MIN_ORDER_KRW = 5000  # 이 미만으로 남은 잔량은 '먼지'로 보고 보유에서 제외


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
    state_path: object = None      # 보유 영속화 파일 경로(None이면 저장 안 함)

    # ---- 보유 영속화(재시작해도 보유·진입가·고점을 기억) ----
    def save_state(self) -> None:
        if not self.state_path:
            return
        try:
            data = {m: {"entry_price": p.entry_price,
                        "entry_time": p.entry_time.isoformat(),
                        "peak_price": p.peak_price, "armed": p.armed}
                    for m, p in self.positions.items()}
            Path(self.state_path).write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def load_state(self) -> None:
        """저장된 보유를 복원(진입가·고점·armed 포함). 재시작 시 1회 호출."""
        if not self.state_path:
            return
        try:
            data = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
        except Exception:
            return
        for m, d in data.items():
            try:
                self.positions[m] = SwingPosition(
                    m, float(d["entry_price"]),
                    datetime.fromisoformat(d["entry_time"]),
                    float(d.get("peak_price", 0) or 0), bool(d.get("armed", False)))
            except Exception:
                pass

    def adopt_holdings(self, exclude=(), now: datetime | None = None) -> list[str]:
        """실제 계좌에 있으나 봇이 모르는 코인을 흡수(평단가를 진입가로 인식).

        과거에 봇이 사놓고 재시작으로 잊은 코인을 다시 관리(익절/손절)하기 위함.
        평단 0(거래불가 에어드랍)·먼지·제외목록·이미 보유 중인 건 건너뜀.
        반환: 새로 흡수한 마켓 목록.
        """
        get_holdings = getattr(self.broker, "get_holdings", None)
        if get_holdings is None:
            return []
        try:
            holdings = get_holdings()
        except Exception:
            return []
        if not holdings:
            return []
        now = now or datetime.now()
        added = []
        for m, h in holdings.items():
            vol, avg = (h[0], h[1]) if h else (0.0, 0.0)
            if m in self.positions or m in exclude:
                continue
            if avg <= 0 or vol * avg < MIN_ORDER_KRW:   # 거래불가/먼지 제외
                continue
            self.positions[m] = SwingPosition(m, avg, now)
            added.append(m)
        if added:
            self.save_state()
        return added

    def held(self) -> list[str]:
        return list(self.positions.keys())

    def has_room(self) -> bool:
        return len(self.positions) < self.max_positions

    def _roll_day(self, now):
        if self._day != now.date():
            self._day = now.date()
            self.realized_today = 0.0
            self.halted = False

    def reconcile_with_exchange(self) -> list[str]:
        """실제 업비트 잔고와 보유목록(positions)을 맞춘다(현행화).

        봇이 보유로 알지만 실제 계좌엔 없는(사용자가 직접 판/소진된) 코인을
        보유목록에서 제거한다. broker.get_holdings() 가 None(모의)이면 아무 일도
        안 함. 반환: 외부 매도로 간주해 정리한 마켓 목록.
        """
        get_holdings = getattr(self.broker, "get_holdings", None)
        if get_holdings is None:
            return []
        try:
            holdings = get_holdings()
        except Exception:
            return []
        if holdings is None:           # 모의 모드 → 메모리 상태 유지
            return []
        removed = []
        for m in list(self.positions.keys()):
            h = holdings.get(m)
            vol = h[0] if h else 0.0
            avg = h[1] if h else 0.0
            if vol <= 0 or vol * avg < MIN_ORDER_KRW:   # 계좌에 없음/먼지 → 정리
                del self.positions[m]
                self.cooldowns.pop(m, None)
                removed.append(m)
        if removed:
            self.save_state()
        return removed

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
        if done:
            self.save_state()
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
        if done:
            self.save_state()
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
