#!/usr/bin/env python3
"""상대강도 로테이션 백테스트/교차검증 (고위험 슬롯 후보 A).

설계 원칙(과최적화 차단):
  · 후보 파라미터는 2013~2019(Bitfinex)에서 미리 '고정'했다(아래 CANDIDATES).
  · 2019~2026(Binance 1h)은 손대지 않은 독립표본 — 여기서도 통해야 채택.
  · 단일 최고점을 좇지 않고, 경제적으로 합리적인 소수 후보만 비교한다.

소스:
  --source bitfinex   data/bitfinex/*.csv          (2013~2019, 설계표본)
  --source binance1h  data/binance_1h_2019_2026/   (2019~2026, 독립검증)

실행:
    python3 -m scripts.backtest_rotation --source bitfinex
    python3 -m scripts.backtest_rotation --source binance1h        # 서버
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.metrics import risk_metrics  # noqa: E402
from src.rotation import (RotationConfig, backtest_rotation,  # noqa: E402
                          build_daily_panel, buy_hold_basket)
from src.swing import resample  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# 2013~2019 설계표본에서 미리 고정한 후보들(모두 절대모멘텀 필터 ON).
# A1=공격(설계 최고), A2=분산(상위2), A3=느린·강건.
CANDIDATES = [
    ("A1 공격 30/1/7",  RotationConfig(lookback_days=30, hold_top=1, rebalance_days=7,  abs_filter=True)),
    ("A2 분산 30/2/7",  RotationConfig(lookback_days=30, hold_top=2, rebalance_days=7,  abs_filter=True)),
    ("A3 강건 60/2/14", RotationConfig(lookback_days=60, hold_top=2, rebalance_days=14, abs_filter=True)),
]

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "trades",
              "taker_buy_base", "taker_buy_quote", "ignore"]


def load_daily(source: str) -> dict[str, pd.DataFrame]:
    """소스별로 일봉 dict 반환."""
    if source == "bitfinex":
        from src.bitfinex_data import load_dir
        raw = load_dir(ROOT / "data" / "bitfinex")
        return {c: resample(df, "1D") for c, df in raw.items()}

    if source == "binance1h":
        data_dir = ROOT / "data" / "binance_1h_2019_2026"
        if not data_dir.exists():
            print(f"[오류] 데이터 폴더 없음: {data_dir}")
            sys.exit(1)
        by_sym: dict[str, list[Path]] = {}
        for f in sorted(data_dir.glob("*.csv")):
            by_sym.setdefault(f.name.split("-", 1)[0], []).append(f)
        out = {}
        for sym, files in sorted(by_sym.items()):
            frames = []
            for f in sorted(files):
                df = pd.read_csv(f, header=None, names=KLINE_COLS,
                                 usecols=["open_time", "open", "high", "low",
                                          "close", "volume"])
                if df.empty:
                    continue
                unit = "us" if df["open_time"].iloc[0] > 10 ** 14 else "ms"
                df["datetime"] = pd.to_datetime(df["open_time"], unit=unit)
                frames.append(df[["datetime", "open", "high", "low", "close", "volume"]])
            if frames:
                d = pd.concat(frames, ignore_index=True).drop_duplicates("datetime")
                out[sym.replace("USDT", "")] = resample(
                    d.sort_values("datetime").reset_index(drop=True), "1D")
        return out

    raise ValueError(source)


def report(panel: pd.DataFrame, label: str, ppy: float = 365) -> None:
    bh = buy_hold_basket(panel)
    mbh = risk_metrics(bh, ppy)
    print(f"\n{'='*72}\n{label}  ({panel.index[0].date()} ~ {panel.index[-1].date()}, "
          f"{len(panel)}일, 코인 {len(panel.columns)})\n{'='*72}")
    hdr = (f"{'전략':<16}{'누적%':>10}{'CAGR%':>8}{'MaxDD%':>9}"
           f"{'Calmar':>8}{'노출%':>7}{'교체':>5}")
    print(hdr)
    print("-" * 72)

    def line(name, total, cagr, mdd, calmar, expo, turn):
        cal = "inf" if calmar == float("inf") else f"{calmar:.2f}"
        ex = "-" if expo is None else f"{expo*100:.0f}"
        tn = "-" if turn is None else f"{turn}"
        print(f"{name:<16}{total*100:>10.0f}{cagr*100:>8.0f}{mdd*100:>9.0f}"
              f"{cal:>8}{ex:>7}{tn:>5}")

    line("매수보유(벤치)", bh.iloc[-1] - 1, mbh["cagr"], mbh["mdd"],
         mbh["calmar"], 1.0, None)
    for name, cfg in CANDIDATES:
        r = backtest_rotation(panel, cfg)
        m = risk_metrics(r["equity"], ppy)
        line(name, r["equity"].iloc[-1] - 1, m["cagr"], m["mdd"],
             m["calmar"], r["exposure"], r["turnover"])


def main() -> None:
    p = argparse.ArgumentParser(description="상대강도 로테이션 백테스트/검증")
    p.add_argument("--source", choices=["bitfinex", "binance1h"], default="bitfinex")
    p.add_argument("--split", type=float, default=0.6, help="학습 비율(기본 0.6)")
    args = p.parse_args()

    daily = load_daily(args.source)
    panel = build_daily_panel(daily)
    print(f"소스: {args.source}  미리 고정한 후보 {len(CANDIDATES)}개 (튜닝 없음)")

    report(panel, "전체 구간")

    cut = int(len(panel) * args.split)
    report(panel.iloc[:cut], f"학습 {int(args.split*100)}% (참고)")
    report(panel.iloc[cut:], f"검증 {int((1-args.split)*100)}% (← 일반화 판정)")

    print("\n--- 해석 ---")
    print("  · 검증 구간에서 후보 Calmar 가 '매수보유(벤치)'를 이기면 → 채택 후보.")
    print("  · 검증에서 무너지면(학습만 좋음) → 과최적화, 채택 안 함.")
    print("  · 절대모멘텀 필터 덕에 낙폭(MaxDD)이 매수보유보다 작은지 함께 확인.")


if __name__ == "__main__":
    main()
