"""잠수함 급등 전략 이벤트 기반 백테스트 (intrabar 청산).

실거래 시스템(scanner→tracker→auto_trader)과 동일한 판단 로직을 과거 데이터에
재생(replay)해 성적을 냅니다. 1분봉을 기준으로, 5분봉은 자동 합성해 스캐너에 씁니다.

청산은 봉 내부(intrabar)로 판정합니다:
  · 손절/트레일링/본전: 봉의 '저가'가 스탑 라인을 찔렀는지로 체결 (보수적)
  · 익절: 봉의 '고가'가 목표가에 닿았는지로 체결
  · 같은 봉에서 여러 하방 스탑이 동시 발동하면, 가격이 하락하며 가장 먼저
    닿는(가장 높은) 라인에서 체결된 것으로 처리

⚠️ 합성 데이터 백테스트는 '기계가 의도대로 작동하는지'와 '파라미터의 상대적
   효과'를 검증할 뿐, 실제 수익성을 보장하지 않습니다. 실데이터 CSV를 넣어야
   의미 있는 검증이 됩니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .scanner import (
    BREAKOUT_FULL,
    DORMANT_VOL_REF,
    MOMENTUM_FULL,
    VOL_SURGE_FULL,
    W_BREAKOUT,
    W_MOMENTUM,
    W_VOLUME,
    compute_pump_features,
    is_pump_signal,
)
from .tracker import ExitConfig, Position, decide_entry, effective_trail_pct

# 고속 스캔 윈도(1분봉 수): 5분봉 50개(완성) + 진행 중 1개
SCAN_WINDOW_1M = 250


def resample_5m(df1m: pd.DataFrame) -> pd.DataFrame:
    """1분봉 DataFrame을 5분봉으로 합성."""
    s = df1m.set_index("datetime")
    agg = s.resample("5min").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).dropna()
    return agg.reset_index()


def fast_pump_features(
    close: np.ndarray, high: np.ndarray, vol: np.ndarray, i: int
) -> dict[str, float] | None:
    """compute_pump_features 와 동치인 numpy 고속 경로.

    1분봉 배열에서 인덱스 i(5분 경계, i%5==0) 시점의 5분봉을 직접 합성합니다.
    pandas resample 대비 ~100배 빨라 멀티코인 장기 백테스트에 사용합니다.
    마지막 5분봉은 라이브와 동일하게 '진행 중'(1분치만 포함) 캔들입니다.
    """
    if i < SCAN_WINDOW_1M:
        return None
    c = close[i - SCAN_WINDOW_1M:i].reshape(-1, 5)
    h = high[i - SCAN_WINDOW_1M:i].reshape(-1, 5)
    v = vol[i - SCAN_WINDOW_1M:i].reshape(-1, 5)
    close5 = np.append(c[:, -1], close[i])
    high5 = np.append(h.max(axis=1), high[i])
    vol5 = np.append(v.sum(axis=1), vol[i])

    recent_vol = vol5[-3:].mean()
    base_vol = float(np.median(vol5[-33:-3]))
    vol_surge = float(recent_vol / base_vol) if base_vol > 0 else 0.0

    base_high = float(high5[-33:-3].max())
    price = float(close5[-1])
    breakout = float(price / base_high - 1.0) if base_high > 0 else 0.0

    ref_price = float(close5[-4])
    momentum_15m = float(price / ref_price - 1.0) if ref_price > 0 else 0.0

    r = np.diff(close5) / close5[:-1]
    base_volatility = float(r[-33:-3].std(ddof=1))
    dormancy = max(0.0, min(1.0, 1.0 - base_volatility / DORMANT_VOL_REF))

    s_volume = min(1.0, vol_surge / VOL_SURGE_FULL)
    s_breakout = max(0.0, min(1.0, breakout / BREAKOUT_FULL))
    s_momentum = max(0.0, min(1.0, momentum_15m / MOMENTUM_FULL))
    base_score = (W_VOLUME * s_volume + W_BREAKOUT * s_breakout
                  + W_MOMENTUM * s_momentum)
    score = 100.0 * base_score * (1.0 + 0.2 * dormancy)

    return {
        "score": round(score, 1),
        "vol_surge": round(vol_surge, 2),
        "breakout": round(breakout, 4),
        "momentum_15m": round(momentum_15m, 4),
        "dormancy": round(dormancy, 2),
        "base_volatility": round(base_volatility, 5),
        "price": price,
    }


@dataclass
class BTConfig:
    exit_cfg: ExitConfig = field(default_factory=ExitConfig)
    max_positions: int = 3
    invest_per_trade: float = 10_000.0
    cooldown_min: int = 30
    fee_rate: float = 0.0005       # 편도 수수료(업비트 0.05%)
    slippage: float = 0.001        # 시장가 슬리피지 가정(편도 0.1%)
    min_score: float = 0.0         # 이 점수 미만 후보는 진입 대상 제외
    min_dormancy: float = 0.0      # 잠수함 게이트(기본 끔 — 실데이터에서 역효과)
    max_momentum_15m: float | None = 0.04  # 추격 차단: 15분 상승률 상한(+4%)
    warmup: int = SCAN_WINDOW_1M   # 초기 워밍업 1분봉 수

    # --- 고변동 장세 방어 (ZEC 2025-09~10 같은 구간 대비) ---
    # 일일 손실 한도: 하루 실현손익이 이 금액(원) 이하로 떨어지면
    # 그날은 신규 진입 중단 (보유분 청산은 계속)
    daily_loss_limit: float | None = None
    # 연속 손실 쿨다운 점증: 같은 코인에서 연속으로 잃을 때마다
    # 재진입 금지 시간을 배수로 늘림 (30분 → 90분 → 270분 → ...)
    loss_cooldown_mult: float = 1.0   # 1.0 이면 점증 없음
    max_cooldown_min: int = 480       # 쿨다운 상한(분)
    # 코인별 주간 브레이크: 한 코인의 최근 window 일 누적 손익이
    # -brake_loss_pct 이하면 block 일 동안 그 코인 진입 금지.
    # 고변동 장세에서 '하루 -2%씩 천천히 새는' 출혈을 차단합니다.
    # (실데이터: ZEC 2025-09~10 손실 -19.7% → -11.8%, 2024 수익 무영향)
    brake_loss_pct: float | None = 0.04   # 누적 -4% (None=끔)
    brake_window_days: int = 7
    brake_block_days: int = 3


@dataclass
class Trade:
    market: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    gross_pct: float   # 수수료/슬리피지 전 수익률
    net_pct: float     # 비용 반영 후 수익률
    reason: str
    features: dict = field(default_factory=dict)  # 진입 시점 스캐너 특징


@dataclass
class BTResult:
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    def summary(self) -> dict[str, float]:
        n = len(self.trades)
        if n == 0:
            return {"trades": 0}
        nets = [t.net_pct for t in self.trades]
        wins = [x for x in nets if x > 0]
        losses = [x for x in nets if x <= 0]
        total = sum(nets)
        # 자산 곡선(누적 실현손익, 원) 기반 최대 낙폭 — 원 단위로 보고
        peak = 0.0
        mdd = 0.0
        for v in self.equity_curve:
            peak = max(peak, v)
            mdd = min(mdd, v - peak)
        return {
            "trades": n,
            "win_rate": len(wins) / n * 100,
            "avg_net_pct": total / n * 100,
            "avg_win_pct": (sum(wins) / len(wins) * 100) if wins else 0.0,
            "avg_loss_pct": (sum(losses) / len(losses) * 100) if losses else 0.0,
            "total_net_pct": total * 100,
            "max_drawdown_krw": mdd,
            "profit_factor": (sum(wins) / -sum(losses)) if losses else float("inf"),
        }


def _resolve_bar_exit(
    pos: Position, bar: pd.Series, cfg: ExitConfig, now: datetime
) -> tuple[float | None, str]:
    """한 봉 안에서 청산 여부/체결가/사유 판정 (intrabar)."""
    entry = pos.entry_price
    high = float(bar["high"])
    low = float(bar["low"])

    armed_before = pos.armed
    pos.update(high, cfg.arm_profit_pct)  # 고점/활성화 갱신은 봉 고가 기준

    downside: list[tuple[float, str]] = []
    # 손절 하한 — 활성화 전에는 더 타이트한 초기 손절(꼬리 손실 차단)
    stop = cfg.stop_loss_pct
    if not armed_before and cfg.initial_stop_pct is not None:
        stop = min(stop, cfg.initial_stop_pct)
    sl = entry * (1 - stop)
    if low <= sl:
        downside.append((sl, f"손절(-{stop * 100:.1f}%)"))
    if pos.armed:
        # 트레일링 (단계별 폭)
        peak_gain = pos.peak_price / entry - 1.0
        trail = effective_trail_pct(cfg, peak_gain)
        line = pos.peak_price * (1 - trail)
        if low <= line:
            downside.append((line, f"트레일링(-{trail * 100:.1f}%)"))
        # 본전 스탑
        if cfg.use_breakeven:
            be = entry * (1 + cfg.breakeven_buffer_pct)
            if low <= be:
                downside.append((be, "본전스탑"))

    if downside:
        # 하락하며 가장 먼저 닿는 = 가장 높은 라인
        price, reason = max(downside, key=lambda x: x[0])
        return price, reason

    # 익절 (상방)
    if cfg.take_profit_pct is not None:
        tp = entry * (1 + cfg.take_profit_pct)
        if high >= tp:
            return tp, f"익절(+{cfg.take_profit_pct * 100:.0f}%)"

    close_p = float(bar["close"])
    held_min = (now - pos.entry_time).total_seconds() / 60.0

    # 조기 손절 — 진입 후 일정 시간 안에 상승 못하면 종가 기준 탈출
    if (
        cfg.early_cut_min is not None
        and not pos.armed
        and held_min >= cfg.early_cut_min
        and close_p / entry - 1.0 <= cfg.early_cut_gain
    ):
        return close_p, f"조기손절({cfg.early_cut_min}분내 모멘텀 실패)"

    # 보유시간 초과
    if cfg.max_hold_min is not None and held_min >= cfg.max_hold_min:
        return close_p, f"보유시간초과({cfg.max_hold_min}분)"

    return None, ""


def run_pump_backtest(data: dict[str, pd.DataFrame], cfg: BTConfig) -> BTResult:
    """여러 코인의 1분봉을 재생하며 펌프 전략을 백테스트.

    data: {market: 1분봉 DataFrame}. 모든 코인이 동일한 datetime 인덱스를
          공유한다고 가정합니다(합성 데이터 생성기가 보장).
    """
    markets = list(data.keys())
    times = data[markets[0]]["datetime"].tolist()
    n = len(times)

    # 고속 스캔용 numpy 배열 (close, high, volume)
    arrs = {
        m: (df["close"].to_numpy(dtype=float),
            df["high"].to_numpy(dtype=float),
            df["volume"].to_numpy(dtype=float))
        for m, df in data.items()
    }

    result = BTResult()
    positions: dict[str, Position] = {}
    entry_feats: dict[str, dict] = {}
    cooldowns: dict[str, datetime] = {}
    loss_streak: dict[str, int] = {}   # 코인별 연속 손실 횟수
    market_pnls: dict[str, list] = {}  # 코인별 최근 거래 손익 (주간 브레이크용)
    equity = 0.0  # 누적 실현 순손익(원 환산: invest_per_trade 기준)
    day = None
    realized_today = 0.0
    halted = False  # 일일 손실 한도 도달 → 그날 신규 진입 중단

    for i in range(cfg.warmup, n):
        now = times[i]
        if day != now.date():  # 날짜가 바뀌면 일일 손익/중단 초기화
            day = now.date()
            realized_today = 0.0
            halted = False

        # --- 1) 보유 청산 (매 1분봉, intrabar) ---
        for market in list(positions.keys()):
            bar = data[market].iloc[i]
            price, reason = _resolve_bar_exit(positions[market], bar, cfg.exit_cfg, now)
            if price is not None:
                pos = positions.pop(market)
                gross = price / pos.entry_price - 1.0
                net = gross - 2 * (cfg.fee_rate + cfg.slippage)  # 매수+매도 비용
                result.trades.append(
                    Trade(market, pos.entry_time, now, pos.entry_price,
                          price, gross, net, reason,
                          features=entry_feats.pop(market, {}))
                )
                pnl = cfg.invest_per_trade * net
                equity += pnl
                realized_today += pnl
                result.equity_curve.append(equity)
                if (cfg.daily_loss_limit is not None
                        and realized_today <= -abs(cfg.daily_loss_limit)):
                    halted = True
                # 연속 손실이면 쿨다운 점증 (실패 반복 코인 장시간 차단)
                loss_streak[market] = loss_streak.get(market, 0) + 1 if net < 0 else 0
                cd = cfg.cooldown_min * cfg.loss_cooldown_mult ** max(
                    0, loss_streak[market] - 1)
                cooldowns[market] = now + timedelta(
                    minutes=min(cd, cfg.max_cooldown_min))
                # 코인별 주간 브레이크: 최근 window 일 누적이 한도 이하면 장기 차단
                if cfg.brake_loss_pct is not None:
                    hist = market_pnls.setdefault(market, [])
                    hist.append((now, net))
                    cutoff = now - timedelta(days=cfg.brake_window_days)
                    hist[:] = [(t, p) for t, p in hist if t >= cutoff]
                    if sum(p for _, p in hist) <= -abs(cfg.brake_loss_pct):
                        until = now + timedelta(days=cfg.brake_block_days)
                        if cooldowns.get(market, now) < until:
                            cooldowns[market] = until
                        hist.clear()  # 차단 후 새로 집계

        # --- 2) 스캔 (5분봉 경계에서만) → 후보 ---
        candidates: list[tuple[str, dict]] = []
        if i % 5 == 0 and not halted:
            for market in markets:
                if market in positions:
                    continue
                until = cooldowns.get(market)
                if until is not None and now < until:
                    continue
                close_a, high_a, vol_a = arrs[market]
                feat = fast_pump_features(close_a, high_a, vol_a, i)
                if feat is None or not is_pump_signal(
                    feat,
                    min_dormancy=cfg.min_dormancy,
                    max_momentum=cfg.max_momentum_15m,
                ):
                    continue
                if feat["score"] < cfg.min_score:
                    continue
                candidates.append((market, feat))
            candidates.sort(key=lambda x: x[1]["score"], reverse=True)

        # --- 3) 진입 (자리가 있을 때, 1분봉 트리거 확인) ---
        for market, feat in candidates:
            if len(positions) >= cfg.max_positions:
                break
            window1m = data[market].iloc[max(0, i - 30):i + 1]
            if not decide_entry(window1m):
                continue
            entry_price = float(arrs[market][0][i])
            positions[market] = Position(market, entry_price, now)
            entry_feats[market] = feat

    return result
