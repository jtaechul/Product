#!/usr/bin/env python3
"""일봉 대규모 표본 검증 (Coin Metrics 공개 데이터).

거래소 API가 막힌 환경에서도 raw.githubusercontent 는 접근 가능하다는 점을 이용해,
24개 코인·수백 코인-년치 '일봉'으로 펌프 전략의 핵심 가설을 검증합니다.

⚠️ 이것은 1분봉 실거래 시스템 그 자체가 아니라, 동일한 '핵심 엣지'
   (거래량 급증 돌파를 사되, 이미 급등한 뒤엔 추격 안 함 + 승자는 트레일링)를
   일봉 스케일에서 대규모 독립표본으로 재검증하는 프록시입니다.
   1분봉 5개·3개월(43거래)의 과최적화 여부를 가늠하는 용도입니다.
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://raw.githubusercontent.com/coinmetrics-io/data/master/csv/{}.csv"
ASSETS = [
    "btc", "eth", "xrp", "ada", "doge", "trx", "link", "ltc", "bch", "eos",
    "neo", "xlm", "xmr", "dash", "zec", "etc", "vet", "mana", "sand", "algo",
    "atom", "fil", "aave", "uni", "sol", "avax", "near", "matic", "ape",
    "gala", "enj", "bat", "zrx", "knc", "icx", "theta", "chz", "hbar", "ftm",
    "dot",
]
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "daily"


def fetch(asset: str) -> pd.DataFrame | None:
    cache = DATA_DIR / f"{asset}.csv"
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        return df if len(df) > 200 else None
    try:
        r = requests.get(BASE.format(asset), timeout=30)
        if r.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(r.text), usecols=lambda c: c in (
            "time", "PriceUSD", "volume_reported_spot_usd_1d"))
        df = df.rename(columns={"time": "date", "PriceUSD": "price",
                                "volume_reported_spot_usd_1d": "volume"})
        df = df.dropna(subset=["price"])
        df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
        df["volume"] = df["volume"].fillna(0.0)
        if len(df) <= 200:
            return None
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)
        return df.reset_index(drop=True)
    except Exception:
        return None


def backtest_asset(
    df: pd.DataFrame, *, base=30, recent=3, vol_surge=3.0, mom_min=0.02,
    max_chase=0.15, trail=0.12, stop=0.10, arm=0.06, tp=None, max_hold=30,
    fee=0.002, self_ma=0, btc_ok=None,
) -> list[dict]:
    """일봉 펌프 전략. 1분봉 tracker 와 같은 구조(트레일링+손절+추격차단)를 일봉으로.

    self_ma: >0 이면 해당 코인 종가가 self_ma 일 이동평균 위일 때만 진입(추세 필터).
    btc_ok: {date: bool} 시장 추세 게이트. 그 날 BTC가 강세(200일선 위)인지.
    """
    p = df["price"].to_numpy(float)
    v = df["volume"].to_numpy(float)
    d = df["date"].to_numpy()
    n = len(p)
    ma = (pd.Series(p).rolling(self_ma).mean().to_numpy()
          if self_ma > 0 else None)
    trades = []
    i = base + recent
    while i < n - 1:
        base_v = np.median(v[i - base - recent:i - recent])
        recent_v = v[i - recent:i].mean()
        surge = recent_v / base_v if base_v > 0 else 0.0
        base_hi = p[i - base - recent:i - recent].max()
        breakout = p[i] / base_hi - 1.0 if base_hi > 0 else 0.0
        mom = p[i] / p[i - recent] - 1.0 if p[i - recent] > 0 else 0.0

        signal = (surge >= vol_surge and mom >= mom_min
                  and breakout >= 0.0 and mom <= max_chase)
        # 추세 필터: 코인 자체 MA 위 + BTC 강세
        if signal and ma is not None and not (p[i] > ma[i]):
            signal = False
        if signal and btc_ok is not None and not btc_ok.get(d[i], True):
            signal = False
        if not signal:
            i += 1
            continue

        # 진입: 다음 날 종가
        entry = p[i + 1]
        peak = entry
        armed = False
        exit_p, reason, hold = entry, "보유초과", 0
        for j in range(i + 1, min(n, i + 1 + max_hold)):
            hi = p[j]
            peak = max(peak, hi)
            if not armed and hi >= entry * (1 + arm):
                armed = True
            # 손절
            if p[j] <= entry * (1 - stop):
                exit_p, reason, hold = entry * (1 - stop), "손절", j - i
                break
            # 익절
            if tp is not None and hi >= entry * (1 + tp):
                exit_p, reason, hold = entry * (1 + tp), "익절", j - i
                break
            # 트레일링 (활성화 후)
            if armed and p[j] <= peak * (1 - trail):
                exit_p, reason, hold = peak * (1 - trail), "트레일링", j - i
                break
            exit_p, hold = p[j], j - i
        net = exit_p / entry - 1.0 - 2 * fee
        trades.append({"date": d[i + 1], "net": net, "reason": reason,
                       "hold": hold, "surge": surge, "mom": mom,
                       "breakout": breakout})
        i = j + 1  # 청산 다음 날부터 재탐색
    return trades


def summarize(trades: list[dict], title: str) -> dict:
    if not trades:
        print(f"\n=== {title} ===\n  거래 없음")
        return {}
    nets = np.array([t["net"] for t in trades])
    wins = nets[nets > 0]
    losses = nets[nets <= 0]
    pf = wins.sum() / -losses.sum() if losses.sum() < 0 else float("inf")
    # 부트스트랩: 평균수익 95% 신뢰구간
    rng = np.random.default_rng(0)
    boots = [rng.choice(nets, len(nets), replace=True).mean() for _ in range(2000)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    t_stat = nets.mean() / (nets.std(ddof=1) / np.sqrt(len(nets))) if len(nets) > 1 else 0
    print(f"\n=== {title} ===")
    print(f"  거래수      : {len(nets)}")
    print(f"  승률        : {len(wins) / len(nets) * 100:.1f}%")
    print(f"  평균손익/거래: {nets.mean() * 100:+.2f}%")
    print(f"  누적(단리)  : {nets.sum() * 100:+.1f}%")
    print(f"  손익비(PF)  : {pf:.2f}")
    print(f"  평균 95%CI  : [{lo * 100:+.2f}%, {hi * 100:+.2f}%]  "
          f"(t={t_stat:.2f}) {'✓유의' if lo > 0 else '✗0 포함(유의X)'}")
    return {"n": len(nets), "mean": nets.mean(), "pf": pf, "ci_lo": lo, "ci_hi": hi}


def main() -> None:
    ap = argparse.ArgumentParser(description="일봉 대규모 표본 검증")
    ap.add_argument("--vol-surge", type=float, default=3.0)
    ap.add_argument("--max-chase", type=float, default=0.15)
    ap.add_argument("--trail", type=float, default=0.12)
    ap.add_argument("--stop", type=float, default=0.10)
    ap.add_argument("--no-chase-filter", action="store_true",
                    help="추격 차단 끄고 비교(필터 효과 확인)")
    ap.add_argument("--self-ma", type=int, default=0,
                    help="코인 자체 N일선 위에서만 진입(추세 필터, 0=끔)")
    ap.add_argument("--btc-ma", type=int, default=0,
                    help="BTC가 N일선 위(시장 강세)일 때만 진입(0=끔)")
    args = ap.parse_args()

    print(f"Coin Metrics 일봉 다운로드/캐시... (후보 {len(ASSETS)}종)")
    data = {}
    for a in ASSETS:
        df = fetch(a)
        if df is not None:
            data[a] = df
    coin_years = sum(len(df) for df in data.values()) / 365
    print(f"로드: {len(data)}개 코인, {coin_years:.0f} 코인-년")

    chase = 99.0 if args.no_chase_filter else args.max_chase

    # BTC 시장 추세 게이트 준비
    btc_ok = None
    if args.btc_ma > 0 and "btc" in data:
        b = data["btc"]
        bma = b["price"].rolling(args.btc_ma).mean()
        btc_ok = {d: bool(pr > m) for d, pr, m in
                  zip(b["date"].to_numpy(), b["price"], bma)}

    all_trades = []
    by_asset = {}
    for a, df in data.items():
        tr = backtest_asset(df, vol_surge=args.vol_surge, max_chase=chase,
                            trail=args.trail, stop=args.stop,
                            self_ma=args.self_ma, btc_ok=btc_ok)
        for t in tr:
            t["asset"] = a
        by_asset[a] = tr
        all_trades.extend(tr)

    filt = []
    if args.no_chase_filter:
        filt.append("추격OFF")
    if args.self_ma:
        filt.append(f"자체{args.self_ma}MA")
    if args.btc_ma:
        filt.append(f"BTC{args.btc_ma}MA")
    summarize(all_trades, f"전체 통합 ({' '.join(filt) or '기본'})")

    # 연도별 워크포워드 (과최적화면 특정 해만 좋고 나머지 무너짐)
    print("\n  --- 연도별 워크포워드 ---")
    dft = pd.DataFrame(all_trades)
    dft["year"] = pd.to_datetime(dft["date"]).dt.year
    for y, g in dft.groupby("year"):
        net = g["net"]
        mark = "+" if net.sum() > 0 else "-"
        print(f"    {y}: {len(net):>4}거래  누적 {net.sum()*100:+7.1f}%  "
              f"승률 {(net>0).mean()*100:>4.0f}%  [{mark}]")

    # 코인별 (소수 코인 의존인지)
    print("\n  --- 코인별 누적 (상·하위) ---")
    rows = sorted(((a, sum(t["net"] for t in tr), len(tr))
                   for a, tr in by_asset.items() if tr), key=lambda x: -x[1])
    for a, s, c in rows[:5]:
        print(f"    {a:6} {c:>4}거래  {s*100:+7.1f}%")
    print("    ...")
    for a, s, c in rows[-5:]:
        print(f"    {a:6} {c:>4}거래  {s*100:+7.1f}%")
    pos = sum(1 for _, s, _ in rows if s > 0)
    print(f"\n  흑자 코인: {pos}/{len(rows)} ({pos/len(rows)*100:.0f}%)")


if __name__ == "__main__":
    main()
