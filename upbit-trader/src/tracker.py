"""1분봉 정밀 추적기 + 청산 로직 (2·3단계).

스캐너(5분봉)가 포착한 코인을 1분봉으로 정밀 추적하며 진입/청산을 결정합니다.

청산 전략 = 트레일링 스탑 + 손절 하한 (추천 조합):
  · 손절 하한(stop-loss): 진입가 대비 -X% 하락 시 즉시 매도 (최후 방어선)
  · 트레일링 스탑: 고점 대비 -Y% 하락 시 매도 — 단, 일정 수익(arm_profit)에
    도달해 '활성화'된 뒤에만 작동. 진입 직후 노이즈로 바로 털리는 것을 방지.
  · 익절(take-profit, 선택): 진입가 대비 +Z% 도달 시 차익 실현
  · 보유시간 초과(선택): 지정 분(分) 넘게 진전 없으면 청산

핵심 판단(`decide_entry`, `decide_exit`)은 순수 함수 — 네트워크 없이 검증 가능합니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

# --- 진입 트리거 기본값 (1분봉) -------------------------------------------
ENTRY_LOOKBACK = 3       # 모멘텀/거래량 비교 구간(분)
ENTRY_MIN_MOMENTUM = 0.005   # 최근 N분 +0.5% 이상이면 상승 지속으로 간주
ENTRY_VOL_MULT = 1.5     # 최근 거래량이 평소의 1.5배 이상이어야 진입
ENTRY_VOL_BASE = 15      # 평소 거래량 기준 구간(분)


@dataclass
class ExitConfig:
    """청산 규칙 설정 (추천: 트레일링 + 손절 하한 + 본전 스탑)."""

    trail_pct: float = 0.03         # 고점 대비 -3% 하락 시 트레일링 청산
    stop_loss_pct: float = 0.05     # 진입가 대비 -5% 하락 시 손절(최후 방어선)
    arm_profit_pct: float = 0.02    # +2% 도달 후에만 트레일링 활성화
    take_profit_pct: float | None = None  # 진입가 대비 +X% 익절(선택, None=미사용)
    max_hold_min: int | None = None       # 최대 보유 분(선택, None=무제한)

    # 본전 스탑: 트레일링 활성화 후 가격이 본전 근처로 돌아오면 본전에서 탈출.
    # 한 번 수익권에 갔던 거래가 손실로 끝나는 것을 차단합니다.
    use_breakeven: bool = True
    breakeven_buffer_pct: float = 0.003  # 수수료 감안 +0.3% 위에서 탈출

    # 단계별 트레일링 조임: 고점 수익이 커질수록 트레일링 폭을 좁혀
    # 큰 수익을 더 단단히 보존합니다. (고점수익 기준, 트레일링 %)
    trail_tiers: tuple[tuple[float, float], ...] = ((0.06, 0.025), (0.10, 0.02))


def effective_trail_pct(cfg: ExitConfig, peak_gain: float) -> float:
    """고점 수익률에 따라 적용할 트레일링 폭(수익 클수록 좁게)."""
    trail = cfg.trail_pct
    for threshold, tier_trail in cfg.trail_tiers:
        if peak_gain >= threshold:
            trail = min(trail, tier_trail)
    return trail


@dataclass
class Position:
    """진입 후 추적 중인 포지션 상태."""

    market: str
    entry_price: float
    entry_time: datetime
    peak_price: float = 0.0
    armed: bool = False  # 트레일링 활성화 여부

    def __post_init__(self) -> None:
        if self.peak_price <= 0:
            self.peak_price = self.entry_price

    def update(self, price: float, arm_profit_pct: float) -> None:
        """매 틱마다 고점/활성화 상태 갱신."""
        if price > self.peak_price:
            self.peak_price = price
        if not self.armed and price >= self.entry_price * (1 + arm_profit_pct):
            self.armed = True

    def gain_pct(self, price: float) -> float:
        return price / self.entry_price - 1.0


def decide_entry(
    df: pd.DataFrame,
    *,
    lookback: int = ENTRY_LOOKBACK,
    min_momentum: float = ENTRY_MIN_MOMENTUM,
    vol_mult: float = ENTRY_VOL_MULT,
    vol_base: int = ENTRY_VOL_BASE,
) -> bool:
    """1분봉에서 '상승 지속' 진입 트리거 판정(순수 함수).

    스캐너가 이미 후보로 올린 코인에 대해, 1분봉에서 상승이 살아있는지
    (양의 단기 모멘텀 + 거래량 동반)를 확인합니다.
    """
    need = vol_base + lookback + 1
    if df is None or len(df) < need:
        return False

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)

    momentum = close.iloc[-1] / close.iloc[-1 - lookback] - 1.0
    recent_vol = volume.iloc[-lookback:].mean()
    base_vol = volume.iloc[-(vol_base + lookback):-lookback].median()
    vol_ok = base_vol > 0 and recent_vol >= vol_mult * base_vol

    return bool(momentum >= min_momentum and vol_ok)


def decide_exit(
    pos: Position,
    price: float,
    cfg: ExitConfig,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """현재가/시간 기준 청산 여부와 사유 판정(순수 함수).

    pos.update() 로 고점·활성화 상태를 먼저 갱신한 뒤 호출하세요.
    반환: (청산할지, 사유 문자열)
    """
    # 1) 손절 하한 — 최후 방어선
    if price <= pos.entry_price * (1 - cfg.stop_loss_pct):
        return True, f"손절(진입가 -{cfg.stop_loss_pct * 100:.0f}%)"

    # 2) 익절 (설정된 경우)
    if cfg.take_profit_pct is not None and price >= pos.entry_price * (
        1 + cfg.take_profit_pct
    ):
        return True, f"익절(진입가 +{cfg.take_profit_pct * 100:.0f}%)"

    # 3) 트레일링 스탑 — 활성화(arm)된 뒤에만 작동.
    #    고점 수익이 커질수록 트레일링 폭을 좁혀 큰 수익을 더 단단히 보존.
    if pos.armed:
        peak_gain = pos.peak_price / pos.entry_price - 1.0
        trail = effective_trail_pct(cfg, peak_gain)
        if price <= pos.peak_price * (1 - trail):
            return True, f"트레일링스탑(고점 -{trail * 100:.1f}%)"

        # 본전 스탑: 수익권에 갔던 거래가 본전 아래로 떨어지기 직전 탈출.
        # (이익→손실 전환 차단. 손실 최소화의 핵심)
        if cfg.use_breakeven:
            be_line = pos.entry_price * (1 + cfg.breakeven_buffer_pct)
            if price <= be_line:
                return True, "본전 스탑(수익권 반납 차단)"

    # 4) 보유시간 초과 (설정된 경우)
    if cfg.max_hold_min is not None and now is not None:
        held_min = (now - pos.entry_time).total_seconds() / 60.0
        if held_min >= cfg.max_hold_min:
            return True, f"보유시간 초과({cfg.max_hold_min}분)"

    return False, ""
