"""스윙 펌프 전략 (시간봉/일봉) — '빠른 진입, 인내하는 청산'.

1분봉 스캘핑 버전이 독립표본 검증에서 무너진(과최적화) 교훈을 반영한 재설계입니다.
검증으로 살아남은 엣지(거래량 급증 돌파를 사서 며칠 추세를 트레일링)만 취합니다.

설계:
  · 실시간 모니터링은 1분봉으로 '돌파 순간'을 빠르게 포착(신속 진입 유지)
  · 그러나 보유/청산은 시간봉 스케일 — 1분 노이즈·비용에 잘게 썰리지 않게
  · 진입 문턱을 크게 높여 빈도↓, 거래비용 비중↓
  · 추세 게이트(BTC·코인 자기 이동평균 위)로 약세장 진입 차단
  · 넓은 트레일링으로 큰 추세를 끝까지 먹고, 하드 손절로 꼬리 차단

모든 함수는 OHLCV DataFrame(datetime,open,high,low,close,volume)을 입력으로 받는
순수 함수 — 네트워크 없이 검증 가능합니다. 실거래/모의/백테스트가 같은 로직을 씁니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


def resample(df: pd.DataFrame, rule: str = "1h") -> pd.DataFrame:
    """1분봉 등 원본을 상위 시간봉으로 합성 (rule 예: '1h','4h','1D')."""
    s = df.set_index("datetime")
    agg = s.resample(rule).agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).dropna(subset=["close"])
    return agg.reset_index()


@dataclass
class SwingConfig:
    # --- 진입 신호 (상위 시간봉 종가 기준) ---
    base_bars: int = 96          # 축적/박스 기준 구간 (1h×96 = 4일)
    recent_bars: int = 6         # '최근' 구간 (1h×6 = 6시간)
    vol_surge: float = 3.0       # 최근 거래량 / 기준 중앙값 ≥ 이 배수
    min_breakout: float = 0.0    # 기준구간 고점 대비 돌파율 하한
    min_momentum: float = 0.02   # 최근 구간 상승률 하한
    max_chase: float = 0.20      # 최근 상승률 상한(과열 추격 차단)
    max_base_range: float = 0.50 # 기준구간 박스 폭 상한(잠수함=좁은 박스)

    # --- 추세 게이트 ---
    self_ma_bars: int = 100      # 코인 종가가 자기 MA 위일 때만
    btc_ma_bars: int = 200       # BTC가 자기 MA 위(시장 강세)일 때만(0=끔)

    # --- 청산 ---
    arm_profit: float = 0.06     # +6% 도달 후 트레일링 활성화
    trail: float = 0.15          # 고점 대비 -15% 트레일링
    stop_loss: float = 0.10      # 진입가 -10% 하드 손절
    take_profit: float | None = None
    max_hold_bars: int = 240     # 최대 보유 (1h×240 = 10일)
    # 단계별 트레일링: 고점수익 클수록 좁게(큰 추세 보존)
    trail_tiers: tuple[tuple[float, float], ...] = ((0.30, 0.12), (0.60, 0.10))

    # --- 비용 ---
    cost: float = 0.003          # 왕복 수수료+슬리피지 가정


def _trail_for(cfg: SwingConfig, peak_gain: float) -> float:
    t = cfg.trail
    for thr, tt in cfg.trail_tiers:
        if peak_gain >= thr:
            t = min(t, tt)
    return t


def compute_features(close, high, vol, i, cfg: SwingConfig):
    """i 시점(상위 시간봉)의 진입 특징. 부족하면 None."""
    need = cfg.base_bars + cfg.recent_bars + 1
    if i < need:
        return None
    b0 = i - cfg.base_bars - cfg.recent_bars
    b1 = i - cfg.recent_bars
    base_v = float(np.median(vol[b0:b1]))
    recent_v = float(vol[b1:i + 1].mean())
    surge = recent_v / base_v if base_v > 0 else 0.0
    base_hi = float(high[b0:b1].max())
    base_lo = float(close[b0:b1].min())
    price = float(close[i])
    breakout = price / base_hi - 1.0 if base_hi > 0 else 0.0
    base_range = base_hi / base_lo - 1.0 if base_lo > 0 else 9.9
    ref = float(close[i - cfg.recent_bars])
    mom = price / ref - 1.0 if ref > 0 else 0.0
    return {"surge": surge, "breakout": breakout, "momentum": mom,
            "base_range": base_range, "price": price}


def is_entry(feat, cfg: SwingConfig) -> bool:
    return (feat is not None
            and feat["surge"] >= cfg.vol_surge
            and feat["breakout"] >= cfg.min_breakout
            and feat["momentum"] >= cfg.min_momentum
            and feat["momentum"] <= cfg.max_chase
            and feat["base_range"] <= cfg.max_base_range)


@dataclass
class SwingTrade:
    coin: str
    entry_time: datetime
    exit_time: datetime
    entry: float
    exit: float
    net: float
    reason: str
    hold_bars: int
    feat: dict = field(default_factory=dict)


def backtest_coin(df: pd.DataFrame, cfg: SwingConfig, coin="", btc_ok=None):
    """한 코인(상위 시간봉)에 스윙 전략 재생. intrabar 청산(고가/저가 기준)."""
    c = df["close"].to_numpy(float)
    h = df["high"].to_numpy(float)
    lo = df["low"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    t = df["datetime"].to_numpy()
    n = len(c)
    sma = (pd.Series(c).rolling(cfg.self_ma_bars).mean().to_numpy()
           if cfg.self_ma_bars > 0 else None)
    trades = []
    i = cfg.base_bars + cfg.recent_bars
    while i < n - 1:
        feat = compute_features(c, h, v, i, cfg)
        ok = is_entry(feat, cfg)
        if ok and sma is not None and not (c[i] > sma[i]):
            ok = False
        if ok and btc_ok is not None and not btc_ok.get(t[i], True):
            ok = False
        if not ok:
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
            tline = peak * (1 - _trail_for(cfg, peak / entry - 1.0))
            # 하방: 같은 봉이면 더 높은(먼저 닿는) 라인에서 체결
            downs = [(hard, "손절")]
            if armed:
                downs.append((tline, "트레일링"))
            hit = [(p, r) for p, r in downs if lo[k] <= p]
            if hit:
                exit_p, reason = max(hit, key=lambda x: x[0])
                j = k
                break
            if cfg.take_profit is not None and h[k] >= entry * (1 + cfg.take_profit):
                exit_p, reason, j = entry * (1 + cfg.take_profit), "익절", k
                break
            exit_p, j = c[k], k
        net = exit_p / entry - 1.0 - cfg.cost
        trades.append(SwingTrade(coin, t[i], t[j], entry, exit_p, net, reason,
                                 j - i, feat))
        i = j + 1
    return trades


def btc_trend_gate(btc_df: pd.DataFrame, ma_bars: int) -> dict:
    """BTC 상위 시간봉이 자기 MA 위인지 {datetime: bool}."""
    c = btc_df["close"]
    ma = c.rolling(ma_bars).mean()
    return {d: bool(p > m) for d, p, m in
            zip(btc_df["datetime"].to_numpy(), c.to_numpy(), ma.to_numpy())}
