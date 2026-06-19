#!/usr/bin/env python3
"""대형코인봇(추세필터 레짐) 2019~2026 독립표본 검증 (Binance → 일봉).

왜:
  돌파추격·로테이션·잠수함이 모두 '옛날 좋음 → 최근 실패'를 보였다.
  대형코인봇은 실거래 중이며, 50일선 추세필터+기울기라는 '단순·견고' 부류라
  살아남을 가능성이 높지만 — 확인 전엔 믿지 않는다. 같은 규칙으로 검증한다.

전략(실거래와 동일, MajorsConfig 기본값):
  종가가 50일선 위 + 50일선 우상향이면 보유, 아니면 현금. 레짐 전환 시에만 매매.
  목표는 수익 극대화가 아니라 '낙폭을 줄이며 매수보유를 위험대비로 이기기'.

판정 기준: 검증40 구간에서 (a) 매수보유보다 낙폭(MaxDD)이 작고
           (b) Calmar 가 매수보유 이상이면 → 견고(실거래 지속 근거).

실행(서버):
    cd ~/Product/upbit-trader
    .venv/bin/python -m scripts.validate_majors_2019
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_highrisk_2019 import load_1h_dir  # noqa: E402
from src.majors import MajorsConfig, regime  # noqa: E402
from src.metrics import risk_metrics  # noqa: E402
from src.swing import resample  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "binance_1h_2019_2026"
COST = 0.002  # 레짐 전환 1회 비용(드물어서 영향 작음)


def backtest_majors_daily(df: pd.DataFrame, cfg: MajorsConfig) -> dict:
    """일봉 추세필터 재생. 보유일은 코인수익, 현금일은 0. 전환 시 비용."""
    close = df["close"].to_numpy(float)
    n = len(close)
    pos = np.zeros(n, dtype=int)
    held = False
    for i in range(n):
        if i < cfg.ma_bars + max(cfg.slope_bars, 1):
            held = False
        else:
            r = regime(df.iloc[: i + 1], cfg, held=held)
            held = bool(r["in_market"])
        pos[i] = 1 if held else 0

    eq = 1.0
    curve = [1.0]
    for i in range(1, n):
        if pos[i - 1] == 1 and close[i - 1] > 0:
            eq *= close[i] / close[i - 1]
        if pos[i] != pos[i - 1]:
            eq *= (1.0 - COST)
        curve.append(eq)
    return {"equity": pd.Series(curve), "exposure": float(pos.mean()),
            "switches": int((np.diff(pos) != 0).sum())}


def _line(name, total, cagr, mdd, calmar, expo, sw):
    cal = "inf" if calmar == float("inf") else f"{calmar:.2f}"
    ex = "-" if expo is None else f"{expo*100:.0f}"
    s = "-" if sw is None else f"{sw}"
    print(f"{name:<16}{total*100:>10.0f}{cagr*100:>8.0f}{mdd*100:>9.0f}"
          f"{cal:>8}{ex:>7}{s:>5}")


def report(coin: str, df: pd.DataFrame, cfg: MajorsConfig, label: str) -> None:
    bh = pd.Series(df["close"].to_numpy(float))
    bh = bh / bh.iloc[0]
    mbh = risk_metrics(bh, 365)
    r = backtest_majors_daily(df, cfg)
    mr = risk_metrics(r["equity"], 365)
    print(f"\n{'='*72}\n■ {coin}  [{label}]  "
          f"({df['datetime'].iloc[0].date()} ~ {df['datetime'].iloc[-1].date()}, "
          f"{len(df)}일)\n{'='*72}")
    print(f"{'전략':<16}{'누적%':>10}{'CAGR%':>8}{'MaxDD%':>9}{'Calmar':>8}{'노출%':>7}{'전환':>5}")
    print("-" * 72)
    _line("매수보유(벤치)", bh.iloc[-1] - 1, mbh["cagr"], mbh["mdd"], mbh["calmar"], 1.0, None)
    _line("추세필터(봇)", r["equity"].iloc[-1] - 1, mr["cagr"], mr["mdd"],
          mr["calmar"], r["exposure"], r["switches"])
    # 판정
    better_dd = mr["mdd"] > mbh["mdd"]            # 낙폭이 더 얕은가(덜 음수)
    better_cal = mr["calmar"] >= mbh["calmar"]
    verdict = ("✅ 견고(낙폭↓ & Calmar↑)" if (better_dd and better_cal)
               else "△ 부분(낙폭만↓)" if better_dd
               else "✗ 벤치 미달")
    print(f"  판정: {verdict}")


def main() -> None:
    p = argparse.ArgumentParser(description="대형코인봇 2019~2026 검증")
    p.add_argument("--data-dir", default=str(DEFAULT_DIR))
    p.add_argument("--split", type=float, default=0.6)
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[오류] 데이터 폴더 없음: {data_dir}")
        sys.exit(1)
    raw = load_1h_dir(data_dir)
    daily = {sym.replace("USDT", ""): resample(df, "1D") for sym, df in raw.items()}

    cfg = MajorsConfig()
    want = [c.replace("KRW-", "") for c in cfg.coins]  # BTC, ETH
    print("=== 대형코인봇 설정(실거래와 동일) ===")
    print(f"  대상={want}  ma_bars={cfg.ma_bars}  slope_bars={cfg.slope_bars}  "
          f"buffer={cfg.buffer}  전환비용={COST}")

    for coin in want:
        if coin not in daily:
            print(f"\n[건너뜀] {coin} 데이터 없음")
            continue
        df = daily[coin]
        cut = int(len(df) * args.split)
        report(coin, df, cfg, "전체")
        report(coin, df.iloc[:cut].reset_index(drop=True), cfg,
               f"학습{int(args.split*100)}%")
        report(coin, df.iloc[cut:].reset_index(drop=True), cfg,
               f"검증{int((1-args.split)*100)}% ←판정")

    print("\n--- 해석 ---")
    print("  · '추세필터(봇)'이 매수보유보다 MaxDD 작고 Calmar 같거나 높으면 → 견고.")
    print("  · 강세장 수익은 매수보유보다 낮을 수 있음(현금 구간 존재) — 대신 낙폭이 핵심.")
    print("  · 검증40 구간에서 BTC·ETH 모두 ✅ 면 실거래 지속 근거.")


if __name__ == "__main__":
    main()
