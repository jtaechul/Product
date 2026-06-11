#!/usr/bin/env python3
"""스윙 펌프 전략 백테스트 (시간봉/일봉) — 다중 데이터셋 교차검증.

데이터 소스:
  --source binance   data/*.zip            (2024~, USDT)
  --source bitfinex  data/bitfinex/*.csv    (2013~2019, USD) ← 독립 검증용
  --source daily     Coin Metrics 일봉      (24코인 2010~2026)

같은 전략·같은 파라미터를 서로 다른 거래소/기간에 재생해 일반화를 확인합니다.

  python -m scripts.backtest_swing --source bitfinex --tf 1h
  python -m scripts.backtest_swing --source binance  --tf 1h --show
  python -m scripts.backtest_swing --source daily    --tf 1D
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

from src.swing import (SwingConfig, backtest_coin, btc_trend_gate,  # noqa: E402
                       resample)

ROOT = Path(__file__).resolve().parent.parent


def load_source(source: str) -> dict[str, pd.DataFrame]:
    if source == "binance":
        from src.binance_data import load_dir
        return load_dir(ROOT / "data")
    if source == "bitfinex":
        from src.bitfinex_data import load_dir
        return load_dir(ROOT / "data" / "bitfinex")
    if source == "daily":
        import scripts.backtest_daily as D
        out = {}
        for a in D.ASSETS:
            df = D.fetch(a)
            if df is not None:
                out[a.upper()] = df.rename(columns={"price": "close"}).assign(
                    open=lambda x: x["close"], high=lambda x: x["close"],
                    low=lambda x: x["close"])[
                    ["date", "open", "high", "low", "close", "volume"]
                ].rename(columns={"date": "datetime"})
        return out
    raise ValueError(source)


def summarize(trades, title):
    if not trades:
        print(f"\n=== {title} ===\n  거래 없음")
        return
    nets = np.array([t.net for t in trades])
    wins, losses = nets[nets > 0], nets[nets <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
    rng = np.random.default_rng(0)
    boots = [rng.choice(nets, len(nets), replace=True).mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    tstat = nets.mean() / (nets.std(ddof=1) / np.sqrt(len(nets))) if len(nets) > 1 else 0
    print(f"\n=== {title} ===")
    print(f"  거래수       : {len(nets)}")
    print(f"  승률         : {len(wins)/len(nets)*100:.1f}%")
    print(f"  평균손익/거래 : {nets.mean()*100:+.2f}%")
    print(f"  평균수익(승)  : {wins.mean()*100:+.2f}%" if len(wins) else "")
    print(f"  평균손실(패)  : {losses.mean()*100:+.2f}%" if len(losses) else "")
    print(f"  누적(단리)   : {nets.sum()*100:+.1f}%")
    print(f"  손익비(PF)   : {pf:.2f}")
    print(f"  평균 95%CI   : [{lo*100:+.2f}%, {hi*100:+.2f}%]  (t={tstat:.2f}) "
          f"{'✓유의' if lo > 0 else '✗0포함'}")
    return {"n": len(nets), "mean": nets.mean(), "pf": pf, "tstat": tstat, "lo": lo}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["binance", "bitfinex", "daily"], default="bitfinex")
    p.add_argument("--tf", default="1h", help="시간봉 (1h,4h,1D)")
    p.add_argument("--coins", default=None)
    p.add_argument("--vol-surge", type=float, default=3.0)
    p.add_argument("--trail", type=float, default=0.15)
    p.add_argument("--stop", type=float, default=0.10)
    p.add_argument("--arm", type=float, default=0.06)
    p.add_argument("--max-chase", type=float, default=0.20)
    p.add_argument("--base-bars", type=int, default=96)
    p.add_argument("--self-ma", type=int, default=100)
    p.add_argument("--btc-ma", type=int, default=200)
    p.add_argument("--max-hold", type=int, default=240)
    p.add_argument("--show", action="store_true")
    args = p.parse_args()

    t0 = time.time()
    raw = load_source(args.source)
    if args.coins:
        want = {c.strip().upper() for c in args.coins.split(",")}
        raw = {k: v for k, v in raw.items() if k in want}
    # 시간봉 합성
    data = {c: (df if args.tf in ("1D", "1d") and args.source == "daily"
                else resample(df, args.tf)) for c, df in raw.items()}
    print(f"[{args.source}] {len(data)}개 코인, tf={args.tf} ({time.time()-t0:.1f}초)")

    cfg = SwingConfig(
        base_bars=args.base_bars, vol_surge=args.vol_surge, trail=args.trail,
        stop_loss=args.stop, arm_profit=args.arm, max_chase=args.max_chase,
        self_ma_bars=args.self_ma, btc_ma_bars=args.btc_ma, max_hold_bars=args.max_hold,
    )

    # BTC 추세 게이트 (BTC 데이터가 있을 때)
    btc_ok = None
    btc_key = next((k for k in data if k.startswith("BTC")), None)
    if args.btc_ma > 0 and btc_key:
        btc_ok = btc_trend_gate(data[btc_key], args.btc_ma)

    all_trades = []
    print("\n코인별:")
    for c, df in data.items():
        tr = backtest_coin(df, cfg, coin=c, btc_ok=btc_ok)
        all_trades += tr
        if tr:
            s = sum(x.net for x in tr)
            print(f"  {c:6} {len(tr):>4}거래  누적 {s*100:+8.1f}%")

    summarize(all_trades, f"통합 [{args.source} {args.tf}]")

    if all_trades:
        by_year = defaultdict(list)
        for t in all_trades:
            by_year[pd.Timestamp(t.entry_time).year].append(t.net)
        print("\n  --- 연도별 ---")
        for y in sorted(by_year):
            v = np.array(by_year[y])
            print(f"    {y}: {len(v):>3}거래 누적{v.sum()*100:+7.1f}% 승{(v>0).mean()*100:3.0f}% "
                  f"[{'+' if v.sum()>0 else '-'}]")
        reasons = Counter(t.reason for t in all_trades)
        print("  --- 청산사유 ---")
        for r, cnt in reasons.most_common():
            vv = [t.net for t in all_trades if t.reason == r]
            print(f"    {r:<8} {cnt:>4}회 평균{np.mean(vv)*100:+.2f}%")
        if args.show:
            st = sorted(all_trades, key=lambda t: t.net)
            print("  --- 최악/최고 ---")
            for t in st[:3] + st[-3:]:
                print(f"    {t.coin:6} {pd.Timestamp(t.entry_time).date()} "
                      f"{t.net*100:+7.1f}% {t.reason} ({t.hold_bars}봉)")


if __name__ == "__main__":
    main()
