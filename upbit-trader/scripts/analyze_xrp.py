#!/usr/bin/env python3
"""리플(XRP) 전용 위험대비수익 분석 + 워크포워드 검증.

왜 별도 스크립트인가:
  · analyze_majors 1차 분석에서 XRP는 BTC·ETH와 성격이 달랐다.
    - 추세필터(200MA)는 XRP에서 Calmar 0.21로 약함(대형코인 봇이 XRP를 뺀 이유).
    - MACD는 전체기간 Calmar 1.70로 화려했으나 검증(뒤40%)에서 0.13으로 붕괴 = 과최적화.
    - 검증 구간에서 단순보유를 확실히 이긴 유일한 전략은 '스윙펌프(급등 추격 모멘텀)'
      (Calmar 1.16, MaxDD -25%). XRP의 '오래 잠잠하다 급등' 성격과 부합.
  · 따라서 XRP는 추세필터형이 아니라 '모멘텀/돌파' 계열이 맞다는 가설을, 한 번의 60/40
    분할이 아니라 '여러 시기로 잘라 보는 워크포워드'로 굳힌다(우연·특정 구간 의존 배제).

데이터(이미 보유): data/daily/xrp.csv (CoinMetrics 일봉, 2014~2026)

사용:
    python -m scripts.analyze_xrp                 # 일봉 전체+워크포워드
    python -m scripts.analyze_xrp --windows 5     # 워크포워드 구간 수
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
from src.metrics import PERIODS, risk_metrics  # noqa: E402
from src.swing import SwingConfig, backtest_coin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "data" / "daily" / "xrp.csv"

# analyze_majors 와 동일한 'XRP 일봉용' 스윙 설정(검증 승자). 파라미터는 손대지 않는다.
XRP_SWING = SwingConfig(base_bars=30, recent_bars=3, self_ma_bars=50,
                        btc_ma_bars=0, max_hold_bars=30)


def load_xrp() -> pd.DataFrame:
    df = pd.read_csv(DAILY, parse_dates=["date"]).dropna(subset=["price"])
    df = df.reset_index(drop=True)
    return pd.DataFrame({
        "datetime": df["date"], "open": df["price"], "high": df["price"],
        "low": df["price"], "close": df["price"], "volume": df.get("volume", 0.0),
    })


def swing_metrics(df: pd.DataFrame) -> dict | None:
    """스윙펌프를 거래단위 자산곡선으로 환산해 위험대비수익 지표 반환."""
    trades = backtest_coin(df, XRP_SWING)
    if not trades:
        return None
    trades = sorted(trades, key=lambda t: t.entry_time)
    eq = pd.Series(np.cumprod([1.0] + [1 + t.net for t in trades]))
    ppy = PERIODS["1D"]
    years = len(df) / ppy
    total = float(eq.iloc[-1] - 1)
    cagr = ((1 + total) ** (1 / years) - 1) if years > 0 else 0.0
    mdd = float((eq / eq.cummax() - 1).min())
    wins = sum(1 for t in trades if t.net > 0)
    return {"name": f"스윙펌프({len(trades)}거래)", "total_return": total,
            "cagr": cagr, "mdd": mdd,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("inf"),
            "n_trades": len(trades), "win_rate": wins / len(trades)}


def bh_metrics(df: pd.DataFrame) -> dict:
    pos = pd.Series(1, index=df.index)
    res = run_backtest(df, pos)
    m = risk_metrics(res.equity, PERIODS["1D"], positions=pos)
    return {"name": "단순보유", **m, "n_trades": 0, "win_rate": None}


def fmt_pct(x):
    return "   -  " if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:+7.1f}%"


def fmt_num(x):
    return "  -  " if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:5.2f}"


def main() -> None:
    ap = argparse.ArgumentParser(description="XRP 전용 위험대비수익 + 워크포워드")
    ap.add_argument("--windows", type=int, default=5, help="워크포워드 구간 수")
    args = ap.parse_args()

    if not DAILY.exists():
        print(f"[오류] XRP 데이터 없음: {DAILY}")
        sys.exit(1)

    df = load_xrp()
    out: list[str] = []

    def emit(s: str):
        print(s)
        out.append(s)

    d0 = pd.Timestamp(df["datetime"].iloc[0]).date()
    d1 = pd.Timestamp(df["datetime"].iloc[-1]).date()
    emit(f"\n{'#'*72}\n# 리플(XRP) 전용 분석 — 일봉 {d0} ~ {d1} ({len(df)}일)\n{'#'*72}")

    # ── 1) 전체 기간: 스윙펌프 vs 단순보유 ──
    emit("\n[전체 기간] 스윙펌프 vs 단순보유")
    emit(f"{'전략':<18}{'총수익':>10}{'CAGR':>8}{'MaxDD':>8}{'Calmar':>7}{'승률':>7}{'거래':>6}")
    emit("-" * 64)
    full = [swing_metrics(df), bh_metrics(df)]
    for r in [x for x in full if x]:
        emit(f"{r['name']:<18}{fmt_pct(r['total_return']):>10}{fmt_pct(r['cagr']):>8}"
             f"{fmt_pct(r['mdd']):>8}{fmt_num(r['calmar']):>7}"
             f"{fmt_pct(r['win_rate']):>7}{r['n_trades']:>6}")

    # ── 2) 워크포워드: 역사를 N구간으로 잘라 '어느 시기에나' 통하는지 ──
    emit(f"\n[워크포워드] 전 기간을 {args.windows}개 시기로 분할 — 구간별 스윙펌프 성적")
    emit("(우연·특정 강세장 의존이면 일부 구간에서 무너진다. 다수 구간 우위여야 신뢰)")
    emit(f"{'구간':<24}{'스윙 Calmar':>12}{'스윙 수익':>11}{'보유 수익':>11}{'승자':>8}")
    emit("-" * 70)
    n = len(df)
    edges = [int(n * k / args.windows) for k in range(args.windows + 1)]
    swing_wins = 0
    valid = 0
    for k in range(args.windows):
        seg = df.iloc[edges[k]:edges[k + 1]].reset_index(drop=True)
        if len(seg) < XRP_SWING.base_bars + XRP_SWING.recent_bars + 10:
            continue
        sm = swing_metrics(seg)
        bm = bh_metrics(seg)
        s0 = pd.Timestamp(seg["datetime"].iloc[0]).date()
        s1 = pd.Timestamp(seg["datetime"].iloc[-1]).date()
        valid += 1
        if sm is None:
            emit(f"{str(s0)+'~'+str(s1):<24}{'(거래없음)':>12}{'':>11}"
                 f"{fmt_pct(bm['total_return']):>11}{'보유':>8}")
            continue
        # 위험대비(Calmar) 우위로 승자 판정, 동률이면 수익으로
        swing_better = (sm["calmar"] > bm["calmar"]) if np.isfinite(bm["calmar"]) \
            else (sm["total_return"] > bm["total_return"])
        if swing_better:
            swing_wins += 1
        emit(f"{str(s0)+'~'+str(s1):<24}{fmt_num(sm['calmar']):>12}"
             f"{fmt_pct(sm['total_return']):>11}{fmt_pct(bm['total_return']):>11}"
             f"{('스윙' if swing_better else '보유'):>8}")

    # ── 3) 정직한 판정 ──
    emit("\n[판정]")
    if valid:
        emit(f"  · 스윙펌프가 위험대비수익으로 단순보유를 이긴 구간: {swing_wins}/{valid}")
        if swing_wins / valid >= 0.6:
            emit("  · ✅ 다수 시기에서 우위 — XRP는 '모멘텀/돌파' 계열이 맞다는 가설 강화."
                 " 실거래 후보로 모듈화할 근거.")
        elif swing_wins / valid >= 0.4:
            emit("  · ⚠️ 시기별 들쭉날쭉 — 엣지가 약하거나 특정 장세 의존. 모의로 신중 검증 필요.")
        else:
            emit("  · ✗ 다수 시기에서 단순보유에 못 미침 — 채택 보류. 추가 설계 필요.")
    emit("\n  ※ 일봉 합성가(O=H=L=C)라 봉내 손절/트레일링은 근사. 시간봉 실데이터로 재확인 권장.")
    emit("  ※ 어떤 결과든 '검증 안 된 전략은 실거래 금지' 원칙을 따른다(모의 우선).")

    report = ROOT / "data" / "xrp_report.txt"
    report.write_text("\n".join(out), encoding="utf-8")
    print(f"\n리포트 저장: {report}")


if __name__ == "__main__":
    main()
