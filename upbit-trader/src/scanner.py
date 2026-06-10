"""잠수함 알트코인 급등 스캐너 (1단계).

업비트 전체 KRW 마켓을 5분봉으로 훑어, "조용히 가라앉아(축적) 있다가
거래량이 터지며 급등 조짐을 보이는" 코인을 점수화해 순위를 매깁니다.

설계 의도 (2단계 구조):
  · 스캐너(여기)는 5분봉으로 '널널하게' 후보를 추립니다.
  · 포착된 코인은 이후 1분봉으로 정밀 추적/매매합니다(tracker, 다음 단계).

핵심은 `compute_pump_features` 순수 함수 — 네트워크 없이도 검증 가능합니다.
백테스트 엔진/전략과 동일하게 OHLCV DataFrame
(컬럼: datetime, open, high, low, close, volume)을 입력으로 받습니다.

⚠️ 급등 포착은 가장 위험한 영역입니다. 신호가 잡힐 땐 이미 오른 경우가 많고,
   잠수함 코인은 거래량이 적어 슬리피지(체결 미끄러짐)가 큽니다.
   반드시 모의로 충분히 검증한 뒤, 실거래는 소액으로만 사용하세요.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from .upbit_quotation import UpbitQuotation, candles_to_dataframe

# --- 스캔 파라미터 기본값 -------------------------------------------------
RECENT_N = 3       # '최근' 구간 캔들 수 (5분봉 × 3 ≈ 15분)
BASE_LEN = 30      # '축적(잠수함)' 기준 구간 캔들 수 (5분봉 × 30 ≈ 2.5시간)
MIN_CANDLES = RECENT_N + BASE_LEN + 2  # 점수 계산에 필요한 최소 캔들 수

# 정규화 기준 (이 값에 도달하면 해당 항목 만점 1.0)
VOL_SURGE_FULL = 5.0     # 평소 거래량의 5배면 만점
BREAKOUT_FULL = 0.03     # 직전 박스권 고점 대비 +3% 돌파면 만점
MOMENTUM_FULL = 0.05     # 최근 15분 +5%면 만점
DORMANT_VOL_REF = 0.008  # 5분봉 수익률 표준편차가 이보다 작으면 '잠수함'에 가까움

# 점수 가중치 (합 = 1.0)
W_VOLUME = 0.45
W_BREAKOUT = 0.30
W_MOMENTUM = 0.25

# '급등 조짐' 플래그 판정 기준
SIGNAL_VOL_SURGE = 3.0
SIGNAL_MOMENTUM = 0.02


@dataclass
class PumpCandidate:
    """스캔된 한 종목의 점수와 근거 지표."""

    market: str
    score: float
    vol_surge: float        # 최근 거래량 / 평소(기준구간) 거래량
    breakout: float         # 현재가 / 직전 박스권 고점 - 1
    momentum_15m: float     # 최근 ~15분 수익률
    dormancy: float         # 0~1, 1에 가까울수록 직전이 조용했음(잠수함)
    base_volatility: float  # 기준구간 5분봉 수익률 표준편차
    price: float
    trade_value_24h: float  # 24시간 누적 거래대금(원) — 유동성 참고
    is_signal: bool         # 급등 조짐 플래그
    features: dict[str, Any] = field(default_factory=dict)


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_pump_features(df: pd.DataFrame) -> dict[str, float] | None:
    """5분봉 OHLCV에서 급등 점수와 근거 지표를 계산(순수 함수).

    캔들이 부족하면 None 을 반환합니다.
    반환: score(0~100), vol_surge, breakout, momentum_15m, dormancy,
          base_volatility, price
    """
    if df is None or len(df) < MIN_CANDLES:
        return None

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    volume = df["volume"].astype(float)

    # 구간 분리: [.. 기준(축적) 구간 ..][.. 최근 구간 ..]
    base_slice = slice(-(BASE_LEN + RECENT_N), -RECENT_N)
    recent_vol = volume.iloc[-RECENT_N:].mean()
    base_vol = volume.iloc[base_slice].median()
    vol_surge = float(recent_vol / base_vol) if base_vol > 0 else 0.0

    # 가격 돌파: 현재가 vs 기준구간 고점
    base_high = high.iloc[base_slice].max()
    price = float(close.iloc[-1])
    breakout = float(price / base_high - 1.0) if base_high > 0 else 0.0

    # 최근 모멘텀 (~15분)
    ref_price = float(close.iloc[-RECENT_N - 1])
    momentum_15m = float(price / ref_price - 1.0) if ref_price > 0 else 0.0

    # 잠수함(축적) 정도: 기준구간 변동성이 낮을수록 1에 가까움
    returns = close.pct_change()
    base_volatility = float(returns.iloc[base_slice].std())
    dormancy = _clamp(1.0 - base_volatility / DORMANT_VOL_REF)

    # 항목별 점수 (0~1)
    s_volume = _clamp(vol_surge / VOL_SURGE_FULL)
    s_breakout = _clamp(breakout / BREAKOUT_FULL)
    s_momentum = _clamp(momentum_15m / MOMENTUM_FULL)

    base_score = W_VOLUME * s_volume + W_BREAKOUT * s_breakout + W_MOMENTUM * s_momentum
    # 잠수함 보너스: 조용하다가 터질수록 가산 (최대 +20%)
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


def is_pump_signal(feat: dict[str, float]) -> bool:
    """급등 '조짐' 플래그: 거래량 급증 + 양(+) 모멘텀 + 박스권 상단 돌파."""
    return (
        feat["vol_surge"] >= SIGNAL_VOL_SURGE
        and feat["momentum_15m"] >= SIGNAL_MOMENTUM
        and feat["breakout"] >= 0.0
    )


def scan(
    quotation: UpbitQuotation | None = None,
    *,
    unit: int = 5,
    count: int = 120,
    top: int = 20,
    min_trade_value_24h: float = 100_000_000.0,  # 1억원 미만은 유동성 부족으로 제외
    market_limit: int | None = None,
    pause: float = 0.1,
    on_progress=None,
) -> list[PumpCandidate]:
    """전체 KRW 마켓을 스캔해 급등 후보를 점수순으로 반환.

    min_trade_value_24h: 24h 거래대금이 이 값 미만이면 제외(슬리피지 위험).
    market_limit: 스캔할 마켓 수 상한(테스트용). None 이면 전체.
    on_progress(i, total, market): 진행 콜백(선택).
    """
    q = quotation or UpbitQuotation()

    markets = [m["market"] for m in q.get_markets(only_krw=True)]

    # 유동성 1차 필터: 24h 거래대금 (티커 일괄 조회 — 한 번에 받음)
    tickers = q.get_ticker(markets)
    value_map = {
        t["market"]: float(t.get("acc_trade_price_24h", 0.0)) for t in tickers
    }
    targets = [m for m in markets if value_map.get(m, 0.0) >= min_trade_value_24h]
    if market_limit:
        targets = targets[:market_limit]

    candidates: list[PumpCandidate] = []
    total = len(targets)
    for i, market in enumerate(targets):
        if on_progress:
            on_progress(i + 1, total, market)
        try:
            candles = q.get_candles_minutes(market, unit=unit, count=count)
            df = candles_to_dataframe(candles)
            feat = compute_pump_features(df)
            if feat is None:
                continue
            candidates.append(
                PumpCandidate(
                    market=market,
                    score=feat["score"],
                    vol_surge=feat["vol_surge"],
                    breakout=feat["breakout"],
                    momentum_15m=feat["momentum_15m"],
                    dormancy=feat["dormancy"],
                    base_volatility=feat["base_volatility"],
                    price=feat["price"],
                    trade_value_24h=value_map.get(market, 0.0),
                    is_signal=is_pump_signal(feat),
                    features=feat,
                )
            )
        except Exception:
            # 일시적 오류/응답 이상은 건너뛰고 계속 (rate limit 등)
            pass
        time.sleep(pause)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top]
