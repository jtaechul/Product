#!/usr/bin/env python3
"""1분봉 독립 표본 검증 (Bitfinex 2013~2019, 7개 코인).

git clone 으로 받은 Bitfinex 1분봉으로, Binance(2024~)에서 튜닝한 1분봉 전략을
'완전 독립 표본'에 그대로 재생합니다. 다른 거래소·코인·기간·통화 → 과최적화면
여기서 무너집니다. 파라미터는 건드리지 않고 현재 기본값 그대로 돌립니다.

  python -m scripts.backtest_bitfinex
  python -m scripts.backtest_bitfinex --coins NEO,EOS,XRP,IOT --show-trades
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.binance_data import align_on_union  # noqa: E402
from src.bitfinex_data import load_dir  # noqa: E402
from src.pump_backtest import BTConfig, run_pump_backtest  # noqa: E402
from src.tracker import ExitConfig  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "bitfinex"


def main() -> None:
    p = argparse.ArgumentParser(description="Bitfinex 1분봉 독립 표본 검증")
    p.add_argument("--data-dir", default=str(DATA_DIR))
    p.add_argument("--coins", default=None, help="쉼표구분 (기본 전체)")
    p.add_argument("--trail", type=float, default=3.0)
    p.add_argument("--stop", type=float, default=5.0)
    p.add_argument("--arm", type=float, default=2.0)
    p.add_argument("--max-chase", type=float, default=4.0)
    p.add_argument("--show-trades", action="store_true")
    args = p.parse_args()

    t0 = time.time()
    data = load_dir(args.data_dir)
    if args.coins:
        want = {c.strip().upper() for c in args.coins.split(",")}
        data = {k: v for k, v in data.items() if k in want}
    if not data:
        print(f"[오류] {args.data_dir} 에 데이터가 없습니다.")
        sys.exit(1)
    print(f"로드: {len(data)}개 코인 ({time.time()-t0:.1f}초)")
    for c, df in data.items():
        yrs = f"{df['datetime'].iloc[0].date()}~{df['datetime'].iloc[-1].date()}"
        print(f"  {c:5} {len(df):>9,}분봉  {yrs}")

    cfg = BTConfig(
        exit_cfg=ExitConfig(trail_pct=args.trail / 100, stop_loss_pct=args.stop / 100,
                            arm_profit_pct=args.arm / 100),
        max_positions=1,  # 코인별 독립 실행
        max_momentum_15m=(args.max_chase / 100 if args.max_chase > 0 else None),
    )

    all_trades = []
    print("\n코인별 백테스트 (각 코인 독립)...")
    for c, df in data.items():
        t1 = time.time()
        aligned = align_on_union({c: df})  # 연속 1분 격자로
        res = run_pump_backtest(aligned, cfg)
        for t in res.trades:
            all_trades.append(t)
        s = sum(t.net_pct for t in res.trades)
        print(f"  {c:5} {len(res.trades):>4}거래  누적 {s*100:+8.1f}%  ({time.time()-t1:.0f}초)")

    if not all_trades:
        print("\n거래 없음")
        return

    nets = np.array([t.net_pct for t in all_trades])
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
    rng = np.random.default_rng(0)
    boots = [rng.choice(nets, len(nets), replace=True).mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    t_stat = nets.mean() / (nets.std(ddof=1) / np.sqrt(len(nets)))

    print("\n=== 통합 (1분봉 독립표본, Bitfinex 2013~2019) ===")
    print(f"  거래수       : {len(nets)}")
    print(f"  승률         : {len(wins)/len(nets)*100:.1f}%")
    print(f"  평균손익/거래 : {nets.mean()*100:+.2f}%")
    print(f"  평균수익(승)  : {wins.mean()*100:+.2f}%" if len(wins) else "")
    print(f"  평균손실(패)  : {losses.mean()*100:+.2f}%" if len(losses) else "")
    print(f"  누적(단리)   : {nets.sum()*100:+.1f}%")
    print(f"  손익비(PF)   : {pf:.2f}")
    print(f"  평균 95%CI   : [{lo*100:+.2f}%, {hi*100:+.2f}%]  (t={t_stat:.2f}) "
          f"{'✓유의' if lo > 0 else '✗0 포함'}")

    # 연도별 워크포워드
    by_year = defaultdict(list)
    for t in all_trades:
        by_year[t.entry_time.year].append(t.net_pct)
    print("\n  --- 연도별 워크포워드 ---")
    for y in sorted(by_year):
        v = np.array(by_year[y])
        mark = "+" if v.sum() > 0 else "-"
        print(f"    {y}: {len(v):>4}거래  누적 {v.sum()*100:+8.1f}%  "
              f"승률 {(v>0).mean()*100:>4.0f}%  [{mark}]")

    # 청산 사유
    reasons = Counter(t.reason.split("(")[0] for t in all_trades)
    print("\n  --- 청산 사유 ---")
    for r, c in reasons.most_common():
        v = [t.net_pct for t in all_trades if t.reason.startswith(r)]
        print(f"    {r:<12} {c:>4}회  평균 {np.mean(v)*100:+.2f}%")

    if args.show_trades:
        print("\n  --- 상위/하위 거래 ---")
        st = sorted(all_trades, key=lambda t: t.net_pct)
        for t in st[:3] + st[-3:]:
            print(f"    {t.market:5} {t.entry_time} {t.net_pct*100:+7.2f}% {t.reason}")


if __name__ == "__main__":
    main()
