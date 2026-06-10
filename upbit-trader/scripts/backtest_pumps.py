#!/usr/bin/env python3
"""잠수함 급등 전략 백테스트 CLI.

합성 멀티코인 데이터(또는 실데이터 CSV 폴더)에 전략을 재생해 성적을 냅니다.

  python -m scripts.backtest_pumps                 # 합성 데이터로 빠른 검증
  python -m scripts.backtest_pumps --coins 40 --days 5
  python -m scripts.backtest_pumps --trail 2.5 --stop 4 --arm 1.5   # 파라미터 실험

⚠️ 합성 데이터는 '기계 검증/파라미터 비교'용입니다. 실수익을 보장하지 않습니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pump_backtest import BTConfig, run_pump_backtest  # noqa: E402
from src.tracker import ExitConfig  # noqa: E402


def _ohlc_from_close(times, close, vol):
    close = np.asarray(close, dtype=float)
    open_ = np.empty_like(close)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    hi = np.maximum(open_, close) * (1 + np.random.uniform(0, 0.002, len(close)))
    lo = np.minimum(open_, close) * (1 - np.random.uniform(0, 0.002, len(close)))
    return pd.DataFrame({"datetime": times, "open": open_, "high": hi,
                         "low": lo, "close": close, "volume": vol})


def gen_noise(times, seed):
    rng = np.random.default_rng(seed)
    n = len(times)
    close = 1000 * np.cumprod(1 + rng.normal(0, 0.0015, n))
    vol = np.abs(rng.normal(50, 15, n))
    return _ohlc_from_close(times, close, vol)


def gen_pump(times, seed):
    """잠수함(횡보) → 급등(중간중간 출렁임) → 덤프 패턴."""
    rng = np.random.default_rng(seed)
    n = len(times)
    start = rng.integers(int(n * 0.3), int(n * 0.7))
    ramp = rng.integers(15, 45)        # 급등 지속(분)
    peak_gain = rng.uniform(0.08, 0.30)  # 고점 상승률
    close = np.empty(n)
    vol = np.empty(n)
    price = 1000.0
    for i in range(n):
        if i < start:                  # 축적: 거의 횡보 + 낮은 거래량
            price *= 1 + rng.normal(0, 0.0008)
            vol[i] = abs(rng.normal(30, 8))
        elif i < start + ramp:         # 급등 + 거래량 폭증 (출렁임 큼 → 트레일링 시험)
            price *= 1 + (peak_gain / ramp) + rng.normal(0, 0.012)
            vol[i] = abs(rng.normal(300, 80))
        elif i < start + ramp + ramp:  # 덤프: 상승분 상당부 반납
            price *= 1 - (peak_gain * 0.7 / ramp) + rng.normal(0, 0.006)
            vol[i] = abs(rng.normal(200, 60))
        else:                          # 이후 다시 잠잠
            price *= 1 + rng.normal(0, 0.001)
            vol[i] = abs(rng.normal(40, 10))
        close[i] = price
    return _ohlc_from_close(times, close, vol)


def gen_fakeout(times, seed):
    """가짜 펌프(불 트랩): 거래량 터지며 잠깐 오르다 곧바로 덤프 → 손실 유발."""
    rng = np.random.default_rng(seed)
    n = len(times)
    start = rng.integers(int(n * 0.3), int(n * 0.7))
    spike = rng.integers(4, 10)
    bait_gain = rng.uniform(0.02, 0.05)  # 미끼 상승폭(작음)
    close = np.empty(n)
    vol = np.empty(n)
    price = 1000.0
    for i in range(n):
        if i < start:
            price *= 1 + rng.normal(0, 0.0008)
            vol[i] = abs(rng.normal(30, 8))
        elif i < start + spike:        # 미끼: 거래량 급증 + 약간 상승
            price *= 1 + (bait_gain / spike) + rng.normal(0, 0.004)
            vol[i] = abs(rng.normal(320, 80))
        elif i < start + spike + 20:   # 곧바로 급락 (진입한 봇은 손절)
            price *= 1 - 0.012 + rng.normal(0, 0.005)
            vol[i] = abs(rng.normal(150, 50))
        else:
            price *= 1 + rng.normal(0, 0.001)
            vol[i] = abs(rng.normal(40, 10))
        close[i] = price
    return _ohlc_from_close(times, close, vol)


def make_synthetic(coins: int, days: int, pump_ratio: float, seed: int):
    np.random.seed(seed)
    n = days * 24 * 60  # 1분봉 개수
    times = pd.date_range("2024-01-01", periods=n, freq="1min")
    data = {}
    n_pump = int(coins * pump_ratio)
    n_fake = int(coins * pump_ratio)  # 가짜 펌프도 동수로 섞어 난이도↑
    for k in range(coins):
        market = f"KRW-C{k:02d}"
        if k < n_pump:
            data[market] = gen_pump(times, seed + k)
        elif k < n_pump + n_fake:
            data[market] = gen_fakeout(times, seed + 500 + k)
        else:
            data[market] = gen_noise(times, seed + 1000 + k)
    return data, n_pump, n_fake


def print_summary(title: str, s: dict) -> None:
    print(f"\n=== {title} ===")
    if s.get("trades", 0) == 0:
        print("  거래 없음")
        return
    print(f"  총 거래        : {s['trades']}회")
    print(f"  승률           : {s['win_rate']:.1f}%")
    print(f"  평균 손익/거래 : {s['avg_net_pct']:+.2f}%")
    print(f"  평균 수익(승)  : {s['avg_win_pct']:+.2f}%")
    print(f"  평균 손실(패)  : {s['avg_loss_pct']:+.2f}%")
    print(f"  누적 순손익    : {s['total_net_pct']:+.1f}% (1거래=100% 기준 합)")
    print(f"  최대 낙폭(MDD) : {s['max_drawdown_krw']:+,.0f}원 (1종목 1만원 기준)")
    pf = s['profit_factor']
    print(f"  손익비(PF)     : {pf:.2f}" if pf != float('inf') else "  손익비(PF): ∞")


def main() -> None:
    p = argparse.ArgumentParser(description="잠수함 급등 전략 백테스트")
    p.add_argument("--coins", type=int, default=30)
    p.add_argument("--days", type=int, default=4)
    p.add_argument("--pump-ratio", type=float, default=0.3)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--max-positions", type=int, default=3)
    p.add_argument("--trail", type=float, default=3.0)
    p.add_argument("--stop", type=float, default=5.0)
    p.add_argument("--arm", type=float, default=2.0)
    p.add_argument("--min-score", type=float, default=0.0)
    args = p.parse_args()

    data, n_pump, n_fake = make_synthetic(
        args.coins, args.days, args.pump_ratio, args.seed
    )
    print(f"합성 데이터: 코인 {args.coins}개 (진짜펌프 {n_pump} / 가짜펌프 {n_fake} / "
          f"노이즈 {args.coins - n_pump - n_fake}), {args.days}일 1분봉...")

    cfg = BTConfig(
        exit_cfg=ExitConfig(
            trail_pct=args.trail / 100,
            stop_loss_pct=args.stop / 100,
            arm_profit_pct=args.arm / 100,
        ),
        max_positions=args.max_positions,
        min_score=args.min_score,
    )
    result = run_pump_backtest(data, cfg)
    print_summary("백테스트 결과", result.summary())

    # 청산 사유 분포
    if result.trades:
        from collections import Counter
        reasons = Counter(t.reason.split("(")[0] for t in result.trades)
        print("\n  청산 사유 분포:")
        for r, c in reasons.most_common():
            print(f"    {r:<12} {c}회")
    print()


if __name__ == "__main__":
    main()
