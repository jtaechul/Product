#!/usr/bin/env python3
"""대형코인 추세전략 '수익 개선' 탐색 + 과최적화 차단 검증.

목적: 단일 200일선 추세필터를 넘어서, 수익률(과 위험대비수익)을 높이는 변형을 찾되,
'안 본 구간(뒤 40%) + 두 독립 데이터(일봉/시간봉) 양쪽에서 좋아지는' 설정만 신뢰한다.
(과거 1분봉 전략이 in-sample 만 보고 골랐다가 독립표본에서 무너진 교훈 반영)

탐색 변형:
  · MA 길이              : 추세 기준선 기간
  · 완충 밴드(hysteresis): MA±buffer 로 진입/청산을 벌려 휩쏘(헛매매) 감소
  · MA 기울기 확인        : MA 가 우상향(상승추세)일 때만 보유 → 데드캣 진입 방지
대조군: 단순보유(buy&hold), 기존 200MA, 이동평균교차, MACD

평가: 각 코인 뒤 40%(검증)에서의 총수익·Calmar·MaxDD. 코인 평균 + 최악코인(min)까지
봐서 '평균만 좋고 한 코인은 망하는' 설정을 걸러낸다. 일봉/시간봉 결론이 같아야 신뢰.
"""

from __future__ import annotations

import argparse
import sys
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import strategies as S  # noqa: E402
from src.backtest import run_backtest  # noqa: E402
from src.metrics import PERIODS, risk_metrics  # noqa: E402

# analyze_majors 의 로더 재사용
from scripts.analyze_majors import COINS, load_daily, load_hourly  # noqa: E402


def trend_positions(df: pd.DataFrame, ma: int, buffer: float = 0.0,
                    slope_n: int = 0) -> pd.Series:
    """완충밴드 + (옵션)MA기울기 추세 포지션.

    진입: 종가 > MA*(1+buffer) / 청산: 종가 < MA*(1-buffer) / 그 외: 직전 유지(hysteresis).
    slope_n>0: MA 가 slope_n 봉 전보다 높을 때(우상향)만 보유 허용.
    """
    close = df["close"].to_numpy(float)
    m = pd.Series(close).rolling(ma).mean().to_numpy()
    up = (close > m * (1 + buffer))
    dn = (close < m * (1 - buffer))
    rising = (m > pd.Series(m).shift(slope_n).to_numpy()) if slope_n > 0 else np.ones_like(m, bool)
    pos = np.zeros(len(close), int)
    state = 0
    for i in range(len(close)):
        if np.isnan(m[i]):
            pos[i] = 0
            continue
        if state == 0 and up[i] and rising[i]:
            state = 1
        elif state == 1 and (dn[i] or (slope_n > 0 and not rising[i])):
            state = 0
        pos[i] = state
    return pd.Series(pos, index=df.index)


def metrics_for(df, positions, tf):
    res = run_backtest(df, positions)
    return risk_metrics(res.equity, PERIODS[tf], positions=positions)


def yearly_positive_frac(df, pos, tf):
    """연(또는 분기)별 수익이 +인 비율 — '거의 항상 수익'인지 가늠(높을수록 꾸준)."""
    res = run_backtest(df, pos)
    eq = res.equity.reset_index(drop=True)
    d = pd.to_datetime(df["datetime"]).reset_index(drop=True)
    g = pd.DataFrame({"eq": eq.values, "d": d.values})
    g["bucket"] = g["d"].dt.year if tf == "1D" else g["d"].dt.to_period("Q")
    wins = tot = 0
    for _, grp in g.groupby("bucket"):
        if len(grp) < 2:
            continue
        tot += 1
        if grp["eq"].iloc[-1] / grp["eq"].iloc[0] - 1 > 0:
            wins += 1
    return wins / tot if tot else 0.0


def evaluate_config(name, make_pos, tf, datasets):
    """각 코인 뒤40%(검증)에서 평가 → 코인 평균·최악 지표 + 매매빈도 + 연승률."""
    rets, calmars, mdds, trades, yrwin = [], [], [], [], []
    for df in datasets:
        cut = int(len(df) * 0.6)
        test = df.iloc[cut:].reset_index(drop=True)
        if len(test) < 260:
            continue
        pos = make_pos(test)
        m = metrics_for(test, pos, tf)
        rets.append(m["total_return"])
        calmars.append(m["calmar"] if np.isfinite(m["calmar"]) else 0.0)
        mdds.append(m["mdd"])
        trades.append(int((pos.diff() == 1).sum()))   # 0→1 진입 횟수(매매빈도)
        yrwin.append(yearly_positive_frac(test, pos, tf))
    if not rets:
        return None
    return {"name": name, "ret_avg": np.mean(rets), "ret_min": np.min(rets),
            "calmar_avg": np.mean(calmars), "calmar_min": np.min(calmars),
            "mdd_avg": np.mean(mdds), "mdd_worst": np.min(mdds),
            "trades": np.mean(trades), "yrwin": np.min(yrwin), "n": len(rets)}


def main():
    ap = argparse.ArgumentParser(description="대형코인 전략 수익 개선 탐색+검증")
    ap.add_argument("--tf", choices=["1D", "1h"], default="1D")
    ap.add_argument("--coins", default=",".join(COINS),
                    help="대상 코인 콤마구분(예: BTC,ETH). 기본 BTC,ETH,XRP")
    args = ap.parse_args()
    tf = args.tf
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    load = load_daily if tf == "1D" else load_hourly
    datasets = [d for d in (load(c) for c in coins) if d is not None and len(d) > 600]
    print(f"대상 코인: {', '.join(coins)}  ({len(datasets)}종 로드)")
    if not datasets:
        print("데이터 없음"); return

    # '매매를 더 자주' 위해 짧은 MA까지 포함해 스윕(20~150일). 같은 경제적 horizon(일)으로 비교.
    day_windows = (20, 30, 50, 75, 100, 150)
    ma_list = [w * (1 if tf == "1D" else 24) for w in day_windows]
    buffers = [0.0, 0.02, 0.05]
    slopes = [0, (10 if tf == "1D" else 240)]

    configs = []
    # 대조군
    configs.append(("단순보유(기준)", lambda d: pd.Series(1, index=d.index)))
    configs.append(("이동평균교차5/20", lambda d: S.ma_crossover(d)))
    configs.append(("MACD", lambda d: S.macd(d)))
    # 추세필터 변형 스윕
    for ma, buf, sl in product(ma_list, buffers, slopes):
        nm = f"추세 MA{ma} 완충{int(buf*100)}% 기울기{sl}"
        configs.append((nm, lambda d, ma=ma, buf=buf, sl=sl: trend_positions(d, ma, buf, sl)))

    rows = [r for r in (evaluate_config(n, f, tf, datasets) for n, f in configs) if r]
    base = next((r for r in rows if r["name"].startswith("단순보유")), None)

    # 정렬: 매매빈도 내림차순(자주 매매 우선) → '자주 하면서도 견고한' 설정 보기
    rows_by_freq = sorted(rows, key=lambda r: r["trades"], reverse=True)
    print(f"\n{'='*100}\n[{tf}] 검증구간(뒤40%) 성적 — 매매빈도 내림차순  "
          f"(코인 {len(datasets)}종 평균)\n{'-'*100}")
    print(f"{'설정':<28}{'매매수':>7}{'연승률':>7}{'평균수익':>9}{'최악코인':>9}"
          f"{'평균Calmar':>11}{'최악Calmar':>11}{'최악MDD':>9}")
    for r in rows_by_freq:
        mark = " ◀기준" if base and r is base else ""
        print(f"{r['name']:<28}{r['trades']:>6.0f}{r['yrwin']*100:>6.0f}%"
              f"{r['ret_avg']*100:>8.0f}%{r['ret_min']*100:>8.0f}%"
              f"{r['calmar_avg']:>11.2f}{r['calmar_min']:>11.2f}"
              f"{r['mdd_worst']*100:>8.0f}%{mark}")

    # 추천: '무조건 수익에 가장 가깝게' = 모든코인 흑자 + 연승률 높음 + 낙폭 얕음. 그중 매매 잦은 순.
    if base:
        cand = [r for r in rows if not r["name"].startswith("단순보유")
                and r["ret_min"] > 0 and r["calmar_min"] > 0
                and r["mdd_worst"] > base["mdd_worst"]]
        # 견고성(연승률·최악Calmar) 우선, 동급이면 매매 잦은 순
        cand = sorted(cand, key=lambda r: (round(r["yrwin"], 2), round(r["calmar_min"], 2),
                                           r["trades"]), reverse=True)
        print(f"\n[추천] 모든코인 흑자 & 모든코인 Calmar>0 & 낙폭 더 얕음 → 견고+자주 순:")
        if cand:
            for r in cand[:6]:
                print(f"  · {r['name']}: 매매 {r['trades']:.0f}회, 연승률 "
                      f"{r['yrwin']*100:.0f}%, 수익 {r['ret_avg']*100:.0f}% "
                      f"(최악 {r['ret_min']*100:.0f}%), 최악Calmar {r['calmar_min']:.2f}, "
                      f"최악MDD {r['mdd_worst']*100:.0f}%")
        else:
            print("  (조건 동시충족 없음 — 수익과 낙폭은 맞교환)")


if __name__ == "__main__":
    main()
