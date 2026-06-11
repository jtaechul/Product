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

import pandas as pd

from .scanner import compute_pump_features, is_pump_signal
from .tracker import ExitConfig, Position, decide_entry, effective_trail_pct


def resample_5m(df1m: pd.DataFrame) -> pd.DataFrame:
    """1분봉 DataFrame을 5분봉으로 합성."""
    s = df1m.set_index("datetime")
    agg = s.resample("5min").agg(
        {"open": "first", "high": "max", "low": "min",
         "close": "last", "volume": "sum"}
    ).dropna()
    return agg.reset_index()


@dataclass
class BTConfig:
    exit_cfg: ExitConfig = field(default_factory=ExitConfig)
    max_positions: int = 3
    invest_per_trade: float = 10_000.0
    cooldown_min: int = 30
    fee_rate: float = 0.0005       # 편도 수수료(업비트 0.05%)
    slippage: float = 0.001        # 시장가 슬리피지 가정(편도 0.1%)
    min_score: float = 0.0         # 이 점수 미만 후보는 진입 대상 제외
    warmup: int = 180              # 초기 워밍업 1분봉 수


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

    pos.update(high, cfg.arm_profit_pct)  # 고점/활성화 갱신은 봉 고가 기준

    downside: list[tuple[float, str]] = []
    # 손절 하한
    sl = entry * (1 - cfg.stop_loss_pct)
    if low <= sl:
        downside.append((sl, f"손절(-{cfg.stop_loss_pct * 100:.0f}%)"))
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

    result = BTResult()
    positions: dict[str, Position] = {}
    cooldowns: dict[str, datetime] = {}
    equity = 0.0  # 누적 실현 순손익(원 환산: invest_per_trade 기준)

    for i in range(cfg.warmup, n):
        now = times[i]

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
                          price, gross, net, reason)
                )
                equity += cfg.invest_per_trade * net
                result.equity_curve.append(equity)
                cooldowns[market] = now + timedelta(minutes=cfg.cooldown_min)

        # --- 2) 스캔 (5분봉 경계에서만) → 후보 ---
        candidates: list[tuple[str, float]] = []
        if i % 5 == 0:
            for market in markets:
                if market in positions:
                    continue
                until = cooldowns.get(market)
                if until is not None and now < until:
                    continue
                window = data[market].iloc[max(0, i - 250):i + 1]
                df5 = resample_5m(window)
                feat = compute_pump_features(df5)
                if feat is None or not is_pump_signal(feat):
                    continue
                if feat["score"] < cfg.min_score:
                    continue
                candidates.append((market, feat["score"]))
            candidates.sort(key=lambda x: x[1], reverse=True)

        # --- 3) 진입 (자리가 있을 때, 1분봉 트리거 확인) ---
        for market, _score in candidates:
            if len(positions) >= cfg.max_positions:
                break
            window1m = data[market].iloc[max(0, i - 30):i + 1]
            if not decide_entry(window1m):
                continue
            entry_price = float(data[market].iloc[i]["close"])
            positions[market] = Position(market, entry_price, now)

    return result
