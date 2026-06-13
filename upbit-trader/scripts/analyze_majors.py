#!/usr/bin/env python3
"""대형코인(BTC·ETH·XRP) 위험대비수익 전략 분석.

목표: '얼마나 버나'가 아니라 '위험(최대낙폭) 대비 얼마나 효율적으로 버나(Calmar)'로
여러 전략을 줄세워, 단순 보유(buy&hold)를 이기는 전략이 있는지 정직하게 검증한다.

데이터(이미 보유, 네트워크 불필요):
  · 일봉(1D)  : Coin Metrics — data/daily/{btc,eth,xrp}.csv  (장기, 2010s~)
  · 시간봉(1h): Bitfinex     — data/bitfinex/{BTC,ETH,XRP}-*.csv (독립표본, 2013~2019)

비교 전략:
  buy&hold(기준) / 추세필터(MA레짐) / 이동평균교차 / 볼린저 / MACD / RSI /
  변동성돌파(시간봉만) / 스윙펌프(swing.backtest_coin)

과최적화 점검: 각 코인을 앞 60%(학습)·뒤 40%(검증)로 나눠, 뒤 40%(검증구간)에서도
순위가 유지되는지 별도 표로 확인한다.

사용:
    python -m scripts.analyze_majors                 # 일봉(기본)
    python -m scripts.analyze_majors --tf 1h         # 시간봉(Bitfinex)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import strategies as S  # noqa: E402
from src.backtest import run_backtest  # noqa: E402
from src.bitfinex_data import load_dir  # noqa: E402
from src.metrics import PERIODS, risk_metrics  # noqa: E402
from src.swing import SwingConfig, backtest_coin, resample  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = ROOT / "data" / "daily"
BITFINEX_DIR = ROOT / "data" / "bitfinex"
COINS = ["BTC", "ETH", "XRP"]


# ----------------------------- 데이터 로딩 -----------------------------
def load_daily(coin: str) -> pd.DataFrame | None:
    """Coin Metrics 일봉 → OHLCV. (일봉은 종가만 있어 O=H=L=C 로 합성)"""
    path = DAILY_DIR / f"{coin.lower()}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path, parse_dates=["date"])
    df = df.dropna(subset=["price"]).reset_index(drop=True)
    return pd.DataFrame({
        "datetime": df["date"], "open": df["price"], "high": df["price"],
        "low": df["price"], "close": df["price"],
        "volume": df.get("volume", 0.0),
    })


_BITFINEX_CACHE: dict | None = None


def load_hourly(coin: str) -> pd.DataFrame | None:
    """Bitfinex 1분봉 → 1시간봉 (실제 OHLC 보존)."""
    global _BITFINEX_CACHE
    if _BITFINEX_CACHE is None:
        _BITFINEX_CACHE = load_dir(BITFINEX_DIR) if BITFINEX_DIR.exists() else {}
    df = _BITFINEX_CACHE.get(coin)
    return resample(df, "1h") if df is not None and len(df) else None


# ----------------------------- 전략 → 자산곡선 -----------------------------
def buy_hold_positions(df: pd.DataFrame) -> pd.Series:
    return pd.Series(1, index=df.index)


def strategy_rows(df: pd.DataFrame, tf: str, trend_ma: int) -> list[dict]:
    """run_backtest 기반 전략들(+buy&hold)의 위험대비수익 지표 행 목록."""
    ppy = PERIODS[tf]
    specs: list[tuple[str, pd.Series]] = [
        ("단순보유(buy&hold)", buy_hold_positions(df)),
        (f"추세필터({trend_ma}MA)", S.trend_filter(df, ma=trend_ma)),
        ("이동평균 교차(5/20)", S.ma_crossover(df)),
        ("볼린저밴드(20,2σ)", S.bollinger_bands(df)),
        ("MACD(12/26/9)", S.macd(df)),
        ("RSI(14,30/70)", S.rsi_strategy(df)),
    ]
    # 변동성 돌파는 봉내 고저폭이 필요 → 일봉(O=H=L=C 합성)에선 의미 없어 시간봉만
    if tf == "1h":
        specs.append(("변동성 돌파(k=0.5)", S.volatility_breakout(df)))

    rows = []
    for name, pos in specs:
        res = run_backtest(df, pos)
        m = risk_metrics(res.equity, ppy, positions=pos)
        rows.append({"name": name, **m, "is_bh": name.startswith("단순보유")})
    return rows


def swing_row(df: pd.DataFrame, tf: str) -> dict | None:
    """스윙펌프 전략을 거래단위 자산곡선으로 환산해 같은 지표로 비교."""
    cfg = SwingConfig() if tf == "1h" else SwingConfig(
        base_bars=30, recent_bars=3, self_ma_bars=50, btc_ma_bars=0,
        max_hold_bars=30)
    trades = backtest_coin(df, cfg)
    if not trades:
        return None
    trades = sorted(trades, key=lambda t: t.entry_time)
    eq = pd.Series(np.cumprod([1.0] + [1 + t.net for t in trades]))
    ppy = PERIODS[tf]
    n_bars = len(df)
    years = n_bars / ppy
    total_return = float(eq.iloc[-1] - 1)
    cagr = ((1 + total_return) ** (1 / years) - 1) if years > 0 else 0.0
    dd = eq / eq.cummax() - 1
    mdd = float(dd.min())
    exposure = float(sum(t.hold_bars for t in trades) / n_bars) if n_bars else None
    return {"name": f"스윙펌프({len(trades)}거래)", "total_return": total_return,
            "cagr": cagr, "mdd": mdd,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("inf"),
            "sharpe": float("nan"), "vol": float("nan"),
            "exposure": exposure, "is_bh": False}


# ----------------------------- 출력 -----------------------------
def fmt_pct(x):
    return "    -  " if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:+7.1f}%"


def fmt_num(x):
    return "  - " if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:5.2f}"


def print_table(coin: str, tf: str, rows: list[dict], out: list[str]) -> None:
    rows = sorted(rows, key=lambda r: (r["calmar"] if np.isfinite(r["calmar"]) else -9), reverse=True)
    bh = next((r for r in rows if r["is_bh"]), None)
    header = (f"\n{'='*78}\n[{coin} · {tf}]  위험대비수익 순위 (Calmar 내림차순)  "
              f"※ 기간 {('일' if tf=='1D' else '시간')} 단위\n{'-'*78}\n"
              f"{'전략':<20}{'총수익':>9}{'CAGR':>8}{'MaxDD':>8}"
              f"{'Calmar':>7}{'Sharpe':>7}{'노출':>7}")
    lines = [header]
    for r in rows:
        star = " ◀기준" if r["is_bh"] else ""
        lines.append(
            f"{r['name']:<20}{fmt_pct(r['total_return']):>9}{fmt_pct(r['cagr']):>8}"
            f"{fmt_pct(r['mdd']):>8}{fmt_num(r['calmar']):>7}{fmt_num(r['sharpe']):>7}"
            f"{fmt_pct(r['exposure']):>7}{star}")
    # 한 줄 결론: buy&hold 대비 Calmar 우위 전략
    if bh and np.isfinite(bh["calmar"]):
        better = [r for r in rows if not r["is_bh"] and np.isfinite(r["calmar"])
                  and r["calmar"] > bh["calmar"]]
        if better:
            top = better[0]
            lines.append(
                f"→ 결론: '{top['name']}' 가 단순보유보다 위험대비수익 우위 "
                f"(Calmar {top['calmar']:.2f} vs {bh['calmar']:.2f}, "
                f"MaxDD {top['mdd']*100:.0f}% vs {bh['mdd']*100:.0f}%)")
        else:
            lines.append("→ 결론: 위험대비수익에서 단순보유(buy&hold)를 이긴 전략 없음")
    block = "\n".join(lines)
    print(block)
    out.append(block)


def analyze(coin: str, tf: str, trend_ma: int, out: list[str]) -> None:
    df = load_daily(coin) if tf == "1D" else load_hourly(coin)
    if df is None or len(df) < trend_ma + 30:
        msg = f"\n[{coin} · {tf}] 데이터 부족 — 건너뜀"
        print(msg)
        out.append(msg)
        return

    # 전체 기간
    rows = strategy_rows(df, tf, trend_ma)
    sw = swing_row(df, tf)
    if sw:
        rows.append(sw)
    print_table(coin, tf, rows, out)

    # 검증: 뒤 40%(out-of-sample)에서도 순위가 유지되는지
    cut = int(len(df) * 0.6)
    test = df.iloc[cut:].reset_index(drop=True)
    if len(test) > trend_ma + 30:
        trows = strategy_rows(test, tf, trend_ma)
        tsw = swing_row(test, tf)
        if tsw:
            trows.append(tsw)
        print_table(f"{coin} (검증 뒤40%)", tf, trows, out)


def main() -> None:
    ap = argparse.ArgumentParser(description="대형코인 위험대비수익 분석")
    ap.add_argument("--tf", choices=["1D", "1h"], default="1D",
                    help="1D=일봉(CoinMetrics), 1h=시간봉(Bitfinex)")
    ap.add_argument("--trend-ma", type=int, default=0,
                    help="추세필터 이동평균 기간(0=자동: 일봉200, 시간봉480)")
    args = ap.parse_args()
    trend_ma = args.trend_ma or (200 if args.tf == "1D" else 480)

    out: list[str] = []
    title = (f"\n{'#'*78}\n# 대형코인 위험대비수익 분석 — {args.tf} "
             f"(추세필터 {trend_ma}MA)\n{'#'*78}")
    print(title)
    out.append(title)
    for coin in COINS:
        analyze(coin, args.tf, trend_ma, out)

    note = ("\n[해석] Calmar=CAGR/최대낙폭 (높을수록 위험대비 효율↑). "
            "추세필터는 강세장 수익은 다소 낮아도 약세장 현금화로 MaxDD를 줄여 "
            "Calmar를 높이는 게 목적. 검증(뒤40%) 표에서도 우위가 유지돼야 신뢰.")
    print(note)
    out.append(note)

    report = ROOT / "data" / f"majors_report_{args.tf}.txt"
    report.write_text("\n".join(out), encoding="utf-8")
    print(f"\n리포트 저장: {report}")


if __name__ == "__main__":
    main()
