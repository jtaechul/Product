"""상대강도 로테이션 전략 (cross-sectional / dual momentum) — 고위험 슬롯 후보.

발상(돌파 추격과 정반대):
  · 돌파 추격: '한 코인'의 시계열 신고가를 보고 추격 → 알트에선 가짜 돌파가 많아 실패.
  · 로테이션: '여러 코인을 서로 비교'해 *가장 강한* 것만 보유하고 주기적으로 갈아탄다.
    + 절대모멘텀 필터: 최강 코인조차 하락 중이면 현금으로 빠진다(약세장 대낙폭 차단).

이것이 dual momentum(Antonacci): 상대강도(누가 제일 센가) + 절대모멘텀(시장이 오르는가).
시계열 돌파와 '다른 메커니즘'이라, 돌파 실패가 곧 이 전략 실패를 뜻하지 않는다.
검증은 동일 규칙: 2013~2019에서만 설계 → 2019~2026은 손대지 않고 시험.

모든 함수는 순수함수(가격 패널 입력) — 백테스트=실거래 동일 로직.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RotationConfig:
    lookback_days: int = 60      # 모멘텀(과거 수익률) 측정 기간
    hold_top: int = 1            # 상대강도 상위 몇 개를 보유할지
    rebalance_days: int = 7      # 며칠마다 재평가/교체할지
    abs_filter: bool = True      # 절대모멘텀: 최강 코인도 음수면 현금(약세장 회피)
    cost: float = 0.003          # 교체 시 왕복 수수료+슬리피지 가정


def build_daily_panel(daily: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """{코인: 일봉df(datetime,close,...)} → 공통 날짜축 종가 패널(컬럼=코인).

    빠진 날짜는 직전 종가로 채움(ffill). 상장 전 구간은 NaN으로 남겨 후보에서 제외.
    """
    cols = {}
    for coin, df in daily.items():
        s = df.set_index(pd.to_datetime(df["datetime"]).dt.normalize())["close"]
        s = s[~s.index.duplicated(keep="last")]
        cols[coin] = s
    panel = pd.DataFrame(cols).sort_index()
    panel = panel.ffill()  # 상장 후 빈 날만 메움(상장 전 선행 NaN은 유지)
    return panel


def backtest_rotation(panel: pd.DataFrame, cfg: RotationConfig) -> dict:
    """일봉 종가 패널로 로테이션 재생. 반환: equity(Series), holdings(list), turnover."""
    dates = panel.index
    n = len(dates)
    lb = cfg.lookback_days
    if n <= lb + cfg.rebalance_days:
        return {"equity": pd.Series([1.0]), "holdings": [], "turnover": 0,
                "exposure": 0.0, "n_days": n}

    equity = 1.0
    eq_curve = [1.0]
    cur_holdings: list[str] = []   # 현재 보유 코인들(동일가중)
    turnover = 0
    in_market_days = 0
    holdings_log = []

    prices = panel.to_numpy(float)
    coins = list(panel.columns)

    for i in range(lb, n):
        # 하루 수익 반영(보유 중인 코인 동일가중)
        if i > lb and cur_holdings:
            day_rets = []
            for c in cur_holdings:
                j = coins.index(c)
                p0, p1 = prices[i - 1, j], prices[i, j]
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    day_rets.append(p1 / p0 - 1.0)
            if day_rets:
                equity *= (1.0 + float(np.mean(day_rets)))
        if cur_holdings:
            in_market_days += 1
        eq_curve.append(equity)

        # 재평가일에만 교체
        if (i - lb) % cfg.rebalance_days != 0:
            continue

        # 각 코인 lookback 수익률(상대강도) 계산
        mom = {}
        for j, c in enumerate(coins):
            p_now, p_past = prices[i, j], prices[i - lb, j]
            if p_past > 0 and not np.isnan(p_past) and not np.isnan(p_now):
                mom[c] = p_now / p_past - 1.0
        if not mom:
            new_holdings: list[str] = []
        else:
            ranked = sorted(mom.items(), key=lambda x: x[1], reverse=True)
            top = ranked[: cfg.hold_top]
            if cfg.abs_filter:
                top = [(c, m) for c, m in top if m > 0]  # 절대모멘텀 양수만
            new_holdings = [c for c, _ in top]

        # 교체 비용: 빠지거나 새로 들어온 종목 수에 비례
        changed = set(new_holdings) ^ set(cur_holdings)
        if changed:
            frac = len(changed) / max(1, len(set(new_holdings) | set(cur_holdings)))
            equity *= (1.0 - cfg.cost * frac)
            turnover += 1
        cur_holdings = new_holdings
        holdings_log.append((dates[i], list(cur_holdings)))

    eq = pd.Series(eq_curve)
    exposure = in_market_days / max(1, (n - lb))
    return {"equity": eq, "holdings": holdings_log, "turnover": turnover,
            "exposure": exposure, "n_days": n - lb}


def buy_hold_basket(panel: pd.DataFrame) -> pd.Series:
    """동일가중 매수보유 벤치마크 자산곡선(첫 유효일=1.0)."""
    rets = panel.pct_change()
    basket = rets.mean(axis=1, skipna=True).fillna(0.0)
    return (1.0 + basket).cumprod()
