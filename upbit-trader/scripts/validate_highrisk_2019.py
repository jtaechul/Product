#!/usr/bin/env python3
"""고위험 봇 2019~2026 독립표본 교차검증 (Binance 1시간봉).

목적:
  2013~2019 Bitfinex 데이터로 튜닝한 고위험 봇 현재 기본값
  (breakout_bars=30, min_momentum=0.10, trail=0.20, stop_loss=0.12)이
  '한 번도 본 적 없는' 2019~2026 구간에서도 통하는지(과최적화가 아닌지) 확인.

방법:
  1) data/binance_1h_2019_2026/*.csv 코인별 로드(1시간봉)
  2) 현재 기본 설정 그대로 백테스트(파라미터 손대지 않음)
  3) 각 코인을 시간축 앞 60%(학습)/뒤 40%(검증)로 나눠
     검증구간 성적만으로 일반화 판정
  4) 누적·CAGR·최대낙폭(MaxDD)·Calmar(위험대비수익)·승률 출력

실행(서버에서):
    cd ~/Product/upbit-trader
    python3 -m scripts.validate_highrisk_2019
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.highrisk import HighRiskConfig, backtest_coin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "binance_1h_2019_2026"

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "trades",
              "taker_buy_base", "taker_buy_quote", "ignore"]


def load_1h_dir(data_dir: Path) -> dict[str, pd.DataFrame]:
    """폴더의 {SYM}-1h-YYYY-MM.csv 들을 심볼별로 묶어 시간순 연결."""
    by_sym: dict[str, list[Path]] = {}
    for f in sorted(data_dir.glob("*.csv")):
        sym = f.name.split("-", 1)[0]
        by_sym.setdefault(sym, []).append(f)
    out = {}
    for sym, files in sorted(by_sym.items()):
        frames = []
        for f in sorted(files):
            df = pd.read_csv(f, header=None, names=KLINE_COLS,
                             usecols=["open_time", "open", "high", "low",
                                      "close", "volume"])
            if df.empty:
                continue
            # 2025년 이후 아카이브는 마이크로초(us) 타임스탬프를 쓰기도 함
            unit = "us" if df["open_time"].iloc[0] > 10 ** 14 else "ms"
            df["datetime"] = pd.to_datetime(df["open_time"], unit=unit)
            frames.append(df[["datetime", "open", "high", "low", "close", "volume"]])
        if not frames:
            continue
        d = pd.concat(frames, ignore_index=True)
        d = d.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
        out[sym] = d
    return out


def equity_metrics(trades) -> dict | None:
    """거래 리스트 → 복리 자산곡선으로 위험대비수익 지표."""
    if not trades:
        return None
    ts = sorted(trades, key=lambda t: t.entry_time)
    eq = [1.0]
    for t in ts:
        eq.append(eq[-1] * (1 + t.net))
    eq = pd.Series(eq)
    dd = float((eq / eq.cummax() - 1).min())
    nets = np.array([t.net for t in ts])
    span = pd.Timestamp(ts[-1].exit_time) - pd.Timestamp(ts[0].entry_time)
    span_days = max(1, span.days)
    years = span_days / 365.25
    total = float(eq.iloc[-1] - 1)
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    calmar = (cagr / abs(dd)) if dd < 0 else float("inf")
    return {"n": len(ts), "total": total, "cagr": cagr, "mdd": dd,
            "calmar": calmar, "win": float((nets > 0).mean())}


def _row(label: str, m: dict | None) -> str:
    if not m:
        return f"{label:<8}{'(거래 없음)':>12}"
    cal = "inf" if m["calmar"] == float("inf") else f"{m['calmar']:.2f}"
    return (f"{label:<8}{m['n']:>5}{m['total']*100:>10.1f}{m['cagr']*100:>8.1f}"
            f"{m['mdd']*100:>9.1f}{cal:>8}{m['win']*100:>7.0f}")


def main() -> None:
    p = argparse.ArgumentParser(description="고위험 봇 2019~2026 교차검증")
    p.add_argument("--data-dir", default=str(DEFAULT_DIR))
    p.add_argument("--split", type=float, default=0.6, help="학습 비율(기본 0.6)")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[오류] 데이터 폴더 없음: {data_dir}")
        print("  먼저: python3 -m scripts.fetch_binance_1h 로 데이터를 받으세요.")
        sys.exit(1)

    data = load_1h_dir(data_dir)
    if not data:
        print(f"[오류] {data_dir} 에 csv 가 없습니다.")
        sys.exit(1)

    cfg = HighRiskConfig()
    print("=== 고위험 봇 현재 기본 설정(파라미터 변경 없음) ===")
    print(f"  breakout_bars={cfg.breakout_bars}  trend_ma={cfg.trend_ma_bars}  "
          f"mom_bars={cfg.mom_bars}  min_momentum={cfg.min_momentum}")
    print(f"  vol_surge={cfg.vol_surge}  arm={cfg.arm_profit}  "
          f"trail={cfg.trail}  stop={cfg.stop_loss}  cost={cfg.cost}")

    print("\n로드한 코인:")
    for sym, df in data.items():
        print(f"  {sym:<10}{len(df):>8,}봉  "
              f"{df['datetime'].iloc[0].date()} ~ {df['datetime'].iloc[-1].date()}")

    hdr = f"{'구간':<8}{'거래':>5}{'누적%':>10}{'CAGR%':>8}{'MaxDD%':>9}{'Calmar':>8}{'승률%':>7}"

    all_full, all_train, all_val = [], [], []
    for sym, df in sorted(data.items()):
        cut = int(len(df) * args.split)
        train = df.iloc[:cut].reset_index(drop=True)
        val = df.iloc[cut:].reset_index(drop=True)

        tr_full = backtest_coin(df, cfg, sym)
        tr_tr = backtest_coin(train, cfg, sym)
        tr_val = backtest_coin(val, cfg, sym)
        all_full += tr_full
        all_train += tr_tr
        all_val += tr_val

        print(f"\n{'='*64}\n■ {sym}\n{'='*64}")
        print(hdr)
        print("-" * 64)
        print(_row("전체", equity_metrics(tr_full)))
        print(_row("학습60", equity_metrics(tr_tr)))
        print(_row("검증40", equity_metrics(tr_val)))

    print(f"\n{'#'*64}\n# 통합 (전 코인 합산)\n{'#'*64}")
    print(hdr)
    print("-" * 64)
    print(_row("전체", equity_metrics(all_full)))
    print(_row("학습60", equity_metrics(all_train)))
    mval = equity_metrics(all_val)
    print(_row("검증40", mval))

    print("\n--- 판정(검증40 구간 기준) ---")
    if mval:
        cal = mval["calmar"]
        if cal != float("inf") and cal >= 1.5 and mval["mdd"] > -0.30:
            print(f"  ✅ 통과: 검증 Calmar {cal:.2f}, 최대낙폭 {mval['mdd']*100:.1f}% "
                  "→ 독립표본에서도 위험대비수익 유지")
        elif mval["total"] > 0:
            print(f"  ⚠️ 약함: 검증 Calmar {cal:.2f}, 낙폭 {mval['mdd']*100:.1f}% "
                  "→ 수익은 나지만 위험대비효율 낮음")
        else:
            print(f"  ✗ 부진: 검증 누적 {mval['total']*100:.1f}% "
                  "→ 독립표본에서 손실, 과최적화 의심")
    print("  ※ 학습60 대비 검증40 성적이 비슷하면 일반화 OK, 급락하면 과최적화.")


if __name__ == "__main__":
    main()
