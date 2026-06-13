"""고위험 모멘텀 돌파 전략 (시간봉/일봉) — '강한 상승에 올라타 시세차익'.

설계 철학(잠수함과 정반대):
  · 잠수함: '조용히 눌려 있던' 코인이 거래량 터지며 박스 상단을 깰 때 진입(저점 매집형).
  · 고위험: '이미 강하게 오르고 있는' 코인의 N봉 신고가 돌파에 추격 진입(모멘텀형).
    → 변동성 큰 알트의 큰 추세를 노려 고수익을 추구하되, 그만큼 낙폭도 큼(그래서 자산의 10%만).

핵심: 가격을 '예측'하지 않는다. 이미 발생한 강한 추세(신고가 돌파+모멘텀)에 올라타,
넓은 트레일링으로 끝까지 먹고, 추세가 꺾이면(하드손절/트레일링) 빠진다. 고전적 추세추종
(Donchian/터틀)을 알트에 적용한 형태로, 통계적으로 검증 가능한 엣지다.

모든 함수는 OHLCV(datetime,open,high,low,close,volume) 순수 함수 — 백테스트=실거래 동일 로직.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd


@dataclass
class HighRiskConfig:
    # --- 진입(모멘텀 돌파) ---
    breakout_bars: int = 20      # 직전 N봉 '신고가'를 종가가 돌파하면 진입(추세 시작 포착)
    trend_ma_bars: int = 50      # 종가가 이 MA 위(상승추세)일 때만 — 낙엽 잡기 방지
    mom_bars: int = 10           # 모멘텀 측정 구간
    min_momentum: float = 0.05   # 최근 mom_bars 상승률 하한(이미 오르는 중일 것)
    vol_surge: float = 1.5       # 거래량이 평소보다 이 배수↑(관심 유입 확인)
    base_bars: int = 60          # 거래량 기준선 구간
    # --- 청산(고위험이라 넓게: 큰 추세 끝까지, 대신 손절은 단호) ---
    arm_profit: float = 0.10     # +10% 도달 후 트레일링 활성화
    trail: float = 0.25          # 고점 대비 -25% 넓은 트레일링(변동성 흡수)
    stop_loss: float = 0.15      # 진입가 -15% 하드 손절
    max_hold_bars: int = 360     # 최대 보유
    cost: float = 0.003          # 왕복 수수료+슬리피지 가정


@dataclass
class HRTrade:
    coin: str
    entry_time: datetime
    exit_time: datetime
    entry: float
    exit: float
    net: float
    reason: str
    hold_bars: int
    feat: dict = field(default_factory=dict)


def backtest_coin(df: pd.DataFrame, cfg: HighRiskConfig, coin: str = "") -> list[HRTrade]:
    """한 코인에 모멘텀 돌파 전략 재생. intrabar 청산(고가/저가 기준)."""
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    t = df["datetime"].to_numpy()
    n = len(c)
    ma = pd.Series(c).rolling(cfg.trend_ma_bars).mean().to_numpy()
    # 직전 breakout_bars 봉의 최고가(현재봉 제외) — 이걸 넘으면 신고가 돌파
    prior_high = pd.Series(h).shift(1).rolling(cfg.breakout_bars).max().to_numpy()

    trades: list[HRTrade] = []
    need = max(cfg.breakout_bars, cfg.trend_ma_bars, cfg.base_bars, cfg.mom_bars) + 1
    i = need
    while i < n - 1:
        # 진입 조건: 신고가 돌파 + 상승추세(MA 위) + 모멘텀 + 거래량 유입
        breakout = c[i] > prior_high[i] if not np.isnan(prior_high[i]) else False
        uptrend = (not np.isnan(ma[i])) and c[i] > ma[i]
        mom = c[i] / c[i - cfg.mom_bars] - 1.0 if c[i - cfg.mom_bars] > 0 else 0.0
        base_v = float(np.median(v[i - cfg.base_bars:i])) if i >= cfg.base_bars else 0.0
        surge = (v[i] / base_v) if base_v > 0 else 0.0
        signal = (breakout and uptrend and mom >= cfg.min_momentum
                  and surge >= cfg.vol_surge)
        if not signal:
            i += 1
            continue

        entry = c[i]
        peak = entry
        armed = False
        exit_p, reason, j = entry, "보유초과", min(n - 1, i + cfg.max_hold_bars)
        for k in range(i + 1, min(n, i + 1 + cfg.max_hold_bars)):
            peak = max(peak, h[k])
            if not armed and h[k] >= entry * (1 + cfg.arm_profit):
                armed = True
            hard = entry * (1 - cfg.stop_loss)
            tline = peak * (1 - cfg.trail)
            downs = [(hard, "손절")]
            if armed:
                downs.append((tline, "트레일링"))
            hit = [(p, r) for p, r in downs if lo[k] <= p]
            if hit:
                exit_p, reason = max(hit, key=lambda x: x[0])
                j = k
                break
            exit_p, j = c[k], k
        net = exit_p / entry - 1.0 - cfg.cost
        trades.append(HRTrade(coin, t[i], t[j], entry, exit_p, net, reason,
                              j - i, {"mom": mom, "surge": surge}))
        i = j + 1
    return trades


def entry_signal(df: pd.DataFrame, cfg: HighRiskConfig) -> dict | None:
    """최신 '닫힌 봉' 기준 진입 신호 여부 + 근거(없으면 None). 실시간 스캐너용."""
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    n = len(c)
    need = max(cfg.breakout_bars, cfg.trend_ma_bars, cfg.base_bars, cfg.mom_bars) + 2
    if n < need:
        return None
    i = n - 1  # 최신(닫힌) 봉
    ma = float(pd.Series(c).rolling(cfg.trend_ma_bars).mean().iloc[-1])
    prior_high = float(h[i - cfg.breakout_bars:i].max())
    mom = c[i] / c[i - cfg.mom_bars] - 1.0 if c[i - cfg.mom_bars] > 0 else 0.0
    base_v = float(pd.Series(v[i - cfg.base_bars:i]).median())
    surge = (v[i] / base_v) if base_v > 0 else 0.0
    if (c[i] > prior_high and c[i] > ma and mom >= cfg.min_momentum
            and surge >= cfg.vol_surge):
        return {"breakout": c[i] / prior_high - 1.0, "momentum": mom, "surge": surge}
    return None


def scan_momentum(broker, markets, cfg: HighRiskConfig, top: int = 20
                  ) -> list[tuple[str, dict]]:
    """60분봉으로 모멘텀 돌파 신호가 뜬 마켓을 모멘텀 강도순으로 반환(실시간 스캐너).

    broker.get_candles_60m(market, count) 를 사용(스윙 봇 브로커와 호환).
    """
    need = max(cfg.breakout_bars, cfg.trend_ma_bars, cfg.base_bars, cfg.mom_bars) + 3
    out = []
    for m in markets:
        try:
            df = broker.get_candles_60m(m, count=need)
        except Exception:
            continue
        if df is None or len(df) < need - 1:
            continue
        feat = entry_signal(df, cfg)
        if feat:
            out.append((m, feat))
    out.sort(key=lambda x: x[1]["momentum"], reverse=True)
    return out[:top]
