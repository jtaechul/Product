#!/usr/bin/env python3
"""특정 알트코인의 '잠수함→급등' 구간을 정밀 분석하고 차트를 생성.

find_submarine.py 가 저장한 data/real/*.csv 를 읽어, 지정한 자산의
축적(잠수함) 구간과 급등 구간을 수치로 분해하고 PNG 차트로 그립니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "real"
OUT = Path(__file__).resolve().parent.parent / "data" / "submarine_chart.png"

# (자산, 잠수함→급등 시작일, 표시 라벨)
CASES = [
    ("zrx", "2017-12-11", "ZRX (0x) · 2017"),
    ("neo", "2024-11-04", "NEO · 2024"),
    ("trx", "2024-11-04", "TRX · 2024"),
]
BASE_DAYS = 90
PUMP_DAYS = 30


def load(asset: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / f"{asset}.csv", parse_dates=["date"])
    return df


def analyze(df: pd.DataFrame, start: str):
    s = pd.Timestamp(start)
    idx = df.index[df["date"] >= s][0]
    base = df.iloc[idx - BASE_DAYS:idx]
    pump = df.iloc[idx:idx + PUMP_DAYS]
    p0 = df["price"].iloc[idx]
    peak_i = pump["price"].idxmax()
    stats = {
        "dormancy_days": BASE_DAYS,
        "base_low": base["price"].min(),
        "base_high": base["price"].max(),
        "base_range_pct": (base["price"].max() / base["price"].min() - 1) * 100,
        "base_vol": base["volume"].mean(),
        "p0": p0,
        "peak": pump["price"].max(),
        "peak_date": df["date"].loc[peak_i].date(),
        "days_to_peak": int(peak_i - idx),
        "pump_pct": (pump["price"].max() / p0 - 1) * 100,
        "pump_vol": pump["volume"].mean(),
    }
    stats["vol_mult"] = (stats["pump_vol"] / stats["base_vol"]
                         if stats["base_vol"] > 0 else 0)
    return idx, stats


def main() -> None:
    fig, axes = plt.subplots(len(CASES), 1, figsize=(11, 4 * len(CASES)))
    if len(CASES) == 1:
        axes = [axes]

    for ax, (asset, start, label) in zip(axes, CASES):
        try:
            df = load(asset)
        except FileNotFoundError:
            print(f"건너뜀: {asset} (먼저 find_submarine.py 실행 필요)")
            continue
        idx, st = analyze(df, start)
        s = pd.Timestamp(start)
        win = df[(df["date"] >= s - pd.Timedelta(days=BASE_DAYS + 20)) &
                 (df["date"] <= s + pd.Timedelta(days=PUMP_DAYS + 20))]

        ax.plot(win["date"], win["price"], color="#1f77b4", lw=1.5)
        ax.axvspan(s - pd.Timedelta(days=BASE_DAYS), s, color="#888", alpha=0.15)
        ax.axvspan(s, s + pd.Timedelta(days=PUMP_DAYS), color="#2ca02c", alpha=0.12)
        ax.axvline(s, color="#d62728", ls="--", lw=1)
        ax.set_title(
            f"{label}  —  accumulation {BASE_DAYS}d (range {st['base_range_pct']:.0f}%) "
            f"-> +{st['pump_pct']:.0f}% (volume x{st['vol_mult']:.1f}, "
            f"peak in {st['days_to_peak']}d)", fontsize=10)
        ax.set_ylabel("Price (USD)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(alpha=0.3)
        # 음영 설명
        ax.text(0.01, 0.92, "gray = submarine (dormant)   green = pump",
                transform=ax.transAxes, fontsize=8, color="#444")

        print(f"\n=== {label} ===")
        print(f"  잠수함(축적) 구간: {BASE_DAYS}일 | 박스권 폭 {st['base_range_pct']:.0f}% "
              f"(${st['base_low']:.4g}~${st['base_high']:.4g})")
        print(f"  급등 시작가 ${st['p0']:.4g} → 고점 ${st['peak']:.4g} "
              f"({st['peak_date']}, {st['days_to_peak']}일 소요)")
        print(f"  상승률 +{st['pump_pct']:.0f}%  |  거래량 {st['vol_mult']:.1f}배 증가")

    fig.suptitle("Submarine -> Pump altcoins (real daily data, Coin Metrics)",
                 fontsize=13, y=1.0)
    fig.tight_layout()
    fig.savefig(OUT, dpi=110, bbox_inches="tight")
    print(f"\n차트 저장: {OUT}")


if __name__ == "__main__":
    main()
