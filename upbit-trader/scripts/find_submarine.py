#!/usr/bin/env python3
"""실데이터로 '잠수함 → 급등' 알트코인 구간을 탐지/분석.

Coin Metrics 커뮤니티 데이터(raw.githubusercontent.com, 일별 시세)를 받아,
오래 횡보(축적)하다가 거래량과 함께 폭등한 구간을 찾습니다.

거래소 API가 막힌 환경에서도 GitHub raw 는 접근 가능하다는 점을 활용합니다.
일별 데이터라 '잠수함'의 거시적 패턴(수개월 횡보 → 수일~수주 폭등)을 봅니다.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pandas as pd
import requests

BASE = "https://raw.githubusercontent.com/coinmetrics-io/data/master/csv/{}.csv"

# 받아볼 알트코인 후보 (Coin Metrics 심볼, 소문자)
ASSETS = [
    "eth", "xrp", "ltc", "ada", "doge", "trx", "xlm", "link", "etc", "bch",
    "eos", "neo", "xmr", "dash", "zec", "vet", "theta", "chz", "mana", "sand",
    "ftm", "algo", "hbar", "fil", "aave", "uni", "atom", "dot", "sol", "avax",
    "near", "matic", "ape", "gala", "enj", "bat", "zrx", "knc", "ankr", "icx",
]

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "real"


def fetch(asset: str) -> pd.DataFrame | None:
    """자산의 일별 날짜/가격/거래량을 받아 정리."""
    try:
        r = requests.get(BASE.format(asset), timeout=30)
        if r.status_code != 200:
            return None
        df = pd.read_csv(io.StringIO(r.text),
                         usecols=lambda c: c in (
                             "time", "PriceUSD", "volume_reported_spot_usd_1d"))
        df = df.rename(columns={"time": "date", "PriceUSD": "price",
                                "volume_reported_spot_usd_1d": "volume"})
        df = df.dropna(subset=["price"])
        df["date"] = pd.to_datetime(df["date"])
        df["volume"] = df["volume"].fillna(0.0)
        return df.reset_index(drop=True) if len(df) > 200 else None
    except Exception:
        return None


def find_submarine(df: pd.DataFrame, base_days=90, pump_days=30,
                   max_base_range=0.6, min_pump=1.0):
    """가장 큰 '잠수함→급등' 에피소드 1건을 반환.

    base_days 동안 좁은 박스권(횡보) → 이후 pump_days 안에 min_pump(+100%) 이상 폭등.
    """
    price = df["price"].values
    vol = df["volume"].values
    n = len(df)
    best = None
    i = base_days
    while i < n - 5:
        base = price[i - base_days:i]
        lo, hi = base.min(), base.max()
        base_range = hi / lo - 1.0 if lo > 0 else 9.9
        if base_range <= max_base_range:  # 횡보(축적) 확인
            fwd_end = min(n, i + pump_days)
            fwd_peak = price[i:fwd_end].max()
            pump = fwd_peak / price[i] - 1.0
            if pump >= min_pump:
                base_vol = vol[i - base_days:i].mean()
                pump_vol = vol[i:fwd_end].mean()
                vmult = pump_vol / base_vol if base_vol > 0 else 0.0
                cand = {
                    "start": df["date"].iloc[i].date(),
                    "base_range_pct": base_range * 100,
                    "pump_pct": pump * 100,
                    "vol_mult": vmult,
                    "price_before": price[i],
                    "price_peak": fwd_peak,
                }
                if best is None or pump > best["pump_pct"] / 100:
                    best = cand
                i += pump_days  # 같은 급등 중복 방지
                continue
        i += 1
    return best


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Coin Metrics 일별 데이터 다운로드 중... (후보 {len(ASSETS)}종)\n")
    results = []
    for a in ASSETS:
        df = fetch(a)
        if df is None:
            continue
        df.to_csv(DATA_DIR / f"{a}.csv", index=False)  # 로컬 저장
        ep = find_submarine(df)
        if ep:
            results.append((a, ep, len(df)))
            print(f"  {a.upper():6} ✓ {len(df):>5}일  "
                  f"잠수함→급등: {ep['start']} | 횡보폭 {ep['base_range_pct']:.0f}% "
                  f"→ +{ep['pump_pct']:.0f}% (거래량 {ep['vol_mult']:.1f}배)")
        else:
            print(f"  {a.upper():6} ✓ {len(df):>5}일  (뚜렷한 잠수함 구간 없음)")

    results.sort(key=lambda x: x[1]["pump_pct"], reverse=True)
    print("\n" + "=" * 64)
    print("🏆 잠수함→급등 TOP (실데이터, 일별)")
    print("=" * 64)
    for a, ep, _ in results[:8]:
        print(f"  {a.upper():6} {ep['start']}  횡보 {ep['base_range_pct']:>3.0f}% "
              f"→ +{ep['pump_pct']:>5.0f}%  거래량 {ep['vol_mult']:>4.1f}배  "
              f"(${ep['price_before']:.4g}→${ep['price_peak']:.4g})")
    print(f"\n  데이터 저장 위치: {DATA_DIR}")


if __name__ == "__main__":
    main()
