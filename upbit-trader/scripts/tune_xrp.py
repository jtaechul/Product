#!/usr/bin/env python3
"""리플(XRP) 봇 '더 활발하게' 튜닝 실험 — 진입조건을 완화한 변형들을 검증.

문제의식: 현재 XRP 봇은 진입 문턱(거래량 3배 급등 + 박스돌파 + 50일선 위)이 높아
거래가 드물다(12년간 ~24회). "불장인데 안 산다"는 불만의 원인일 수 있다.

그래서 진입조건을 단계적으로 완화한 변형들을 만들어, 각각을
  ① 전체기간 성적(거래수·승률·수익·MDD·Calmar)
  ② 워크포워드(5개 시기로 잘라 단순보유를 몇 번 이기나)
로 평가해 '더 자주 사면서도 위험대비수익이 유지/개선되는' 설정이 있는지 정직하게 본다.

⚠️ 핵심 원칙: '거래가 많아짐'은 개선이 아니다. 검증(워크포워드)에서 baseline·단순보유를
   이겨야만 채택 후보다. 못 이기면 "완화는 손해"라고 정직히 결론낸다.

사용: python -m scripts.tune_xrp
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest import run_backtest  # noqa: E402
from src.metrics import PERIODS, risk_metrics  # noqa: E402
from src.swing import SwingConfig, backtest_coin  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / "data" / "daily" / "xrp.csv"

# 현재 라이브 봇과 동일한 기준 설정(baseline). 일봉 백테스트라 max_hold_bars=30(일).
BASE = dict(base_bars=30, recent_bars=3, self_ma_bars=50, btc_ma_bars=0,
            max_hold_bars=30, vol_surge=3.0, min_momentum=0.02, max_chase=0.20)

# 진입을 점점 더 활발하게 만든 변형들(무엇을 완화했는지 이름에 표기).
VARIANTS = {
    "기준(현재봇)":            {},
    "거래량 3→2배":            {"vol_surge": 2.0},
    "거래량 3→1.5배":          {"vol_surge": 1.5},
    "50일선 게이트 끔":         {"self_ma_bars": 0},
    "박스 30→20일":            {"base_bars": 20},
    "모멘텀 하한 0%":           {"min_momentum": 0.0},
    "추격상한 20→35%":         {"max_chase": 0.35},
    "완화조합(2배+20일+게이트끔)": {"vol_surge": 2.0, "base_bars": 20, "self_ma_bars": 0},
    "완화조합(2배+박스20)":     {"vol_surge": 2.0, "base_bars": 20},
    # 2차: 1차 상위(1.5배·박스20)의 조합 — '더 공격적' 후보 확정용
    "공격조합(1.5배+박스20)":   {"vol_surge": 1.5, "base_bars": 20},
    "공격조합(1.5배+게이트끔)":  {"vol_surge": 1.5, "self_ma_bars": 0},
    "공격조합(1.5+20+추격35)":  {"vol_surge": 1.5, "base_bars": 20, "max_chase": 0.35},
    "극공격(1.2배+박스20)":     {"vol_surge": 1.2, "base_bars": 20},
}


def load_xrp() -> pd.DataFrame:
    df = pd.read_csv(DAILY, parse_dates=["date"]).dropna(subset=["price"]).reset_index(drop=True)
    return pd.DataFrame({
        "datetime": df["date"], "open": df["price"], "high": df["price"],
        "low": df["price"], "close": df["price"], "volume": df.get("volume", 0.0)})


def swing_metrics(df: pd.DataFrame, cfg: SwingConfig) -> dict | None:
    trades = backtest_coin(df, cfg)
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
    return {"total": total, "cagr": cagr, "mdd": mdd,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("inf"),
            "n": len(trades), "win": wins / len(trades)}


def bh_total(df: pd.DataFrame) -> float:
    res = run_backtest(df, pd.Series(1, index=df.index))
    m = risk_metrics(res.equity, PERIODS["1D"])
    return m["total_return"]


def bh_calmar(df: pd.DataFrame) -> float:
    res = run_backtest(df, pd.Series(1, index=df.index))
    return risk_metrics(res.equity, PERIODS["1D"])["calmar"]


def walkforward_wins(df: pd.DataFrame, cfg: SwingConfig, windows: int = 5) -> tuple[int, int]:
    """N개 시기로 잘라, 각 구간에서 스윙이 단순보유를 Calmar로 이긴 횟수/유효구간."""
    n = len(df)
    edges = [int(n * k / windows) for k in range(windows + 1)]
    wins = valid = 0
    for k in range(windows):
        seg = df.iloc[edges[k]:edges[k + 1]].reset_index(drop=True)
        if len(seg) < cfg.base_bars + cfg.recent_bars + 10:
            continue
        valid += 1
        sm = swing_metrics(seg, cfg)
        if sm is None:
            continue
        bhc = bh_calmar(seg)
        better = (sm["calmar"] > bhc) if np.isfinite(bhc) else (sm["total"] > 0)
        if better:
            wins += 1
    return wins, valid


def main() -> None:
    if not DAILY.exists():
        print(f"[오류] 데이터 없음: {DAILY}")
        sys.exit(1)
    df = load_xrp()
    print(f"\n{'#'*84}\n# 리플(XRP) 진입조건 완화 튜닝 — 일봉 "
          f"{pd.Timestamp(df['datetime'].iloc[0]).date()} ~ "
          f"{pd.Timestamp(df['datetime'].iloc[-1]).date()}\n{'#'*84}")
    print(f"단순보유(기준선): 전체수익 {bh_total(df)*100:+.0f}%, "
          f"Calmar {bh_calmar(df):.2f}\n")

    hdr = (f"{'변형':<26}{'거래':>5}{'승률':>6}{'전체수익':>11}"
           f"{'MDD':>8}{'Calmar':>7}{'워크포워드':>10}")
    print(hdr + "\n" + "-" * 84)

    rows = []
    for name, override in VARIANTS.items():
        cfg = SwingConfig(**{**BASE, **override})
        m = swing_metrics(df, cfg)
        if m is None:
            print(f"{name:<26}{'(거래 없음)':>30}")
            continue
        wins, valid = walkforward_wins(df, cfg)
        rows.append((name, m, wins, valid))
        print(f"{name:<26}{m['n']:>5}{m['win']*100:>5.0f}%{m['total']*100:>10.0f}%"
              f"{m['mdd']*100:>7.0f}%{m['calmar']:>7.2f}{f'{wins}/{valid}':>10}")

    # 정직한 판정: baseline 대비, '더 자주 거래하면서 워크포워드도 유지/개선'된 변형만 후보
    base_row = next((r for r in rows if r[0] == "기준(현재봇)"), None)
    print("\n" + "=" * 84)
    if base_row:
        b_name, b_m, b_wins, b_valid = base_row
        print(f"[기준] {b_name}: 거래 {b_m['n']}회, Calmar {b_m['calmar']:.2f}, "
              f"워크포워드 {b_wins}/{b_valid}")
        cands = [r for r in rows if r[0] != "기준(현재봇)"
                 and r[1]["n"] > b_m["n"]                      # 더 자주 거래
                 and r[2] / max(1, r[3]) >= b_wins / max(1, b_valid)  # 워크포워드 유지↑
                 and r[1]["calmar"] >= b_m["calmar"] * 0.9]    # 위험대비수익 크게 안 나빠짐
        if cands:
            cands.sort(key=lambda r: (r[2] / max(1, r[3]), r[1]["calmar"]), reverse=True)
            print("\n[결과] 더 활발하면서도 검증이 유지/개선된 후보(강한 것부터):")
            for name, m, wins, valid in cands:
                print(f"  ✅ {name}: 거래 {m['n']}회(기준 {b_m['n']}), "
                      f"Calmar {m['calmar']:.2f}, 워크포워드 {wins}/{valid}, "
                      f"전체수익 {m['total']*100:+.0f}%")
            print("\n→ 위 후보 중 하나로 봇을 바꾸면 '더 자주 거래'가 검증상 타당함.")
        else:
            print("\n[결과] 완화 변형 중 '더 자주 거래하면서 검증도 유지'한 건 없음.")
            print("→ 정직한 결론: 지금 거래가 드문 건 결함이 아니라, XRP에선 아무 때나 "
                  "사면 오히려 위험대비수익이 나빠지기 때문. 조건 완화는 손해일 가능성이 큼.")
    print("\n※ 일봉 합성가 기준 근사. 채택 전 실제 시간봉/모의로 재확인 권장.")


if __name__ == "__main__":
    main()
