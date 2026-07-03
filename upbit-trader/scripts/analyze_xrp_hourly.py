#!/usr/bin/env python3
"""리플(XRP) '시간봉' 스윙 전략 검증 — 더 잦은 매매(월 단위)가 가능/타당한지.

배경: 사용자는 연 4회(일봉)는 너무 뜸하다며, '오르면 팔고 조정에 다시 담는' 월 단위
      스윙을 원한다. 그건 일봉을 푸는 게 아니라 '시간봉' 전략이라야 가능하다.
      단, 과거 1분봉 스캘핑이 과최적화로 무너진 전력이 있어 반드시 검증부터 한다.

데이터: Bitfinex XRP 1분봉 → 1시간봉 (2017-05 ~ 2019-12, 약 2.6년).
  ⚠️ 한계: 2017 폭등+2018~19 폭락이 섞인 특수구간이며 '최근 시장'은 없다. 해석에 감안.

비교 전략(거래빈도 포함):
  · 단순보유(기준)
  · 급등추격 스윙펌프(모멘텀) — 시간봉용 파라미터 여러 개
  · 눌림목/평균회귀(볼린저·RSI) — 사용자가 말한 '조정에 사고 오르면 판다'에 해당
  · 추세(이동평균 교차·MACD)

평가: 전체 + 학습60/검증40 + 워크포워드(6구간). 핵심은
  '거래가 잦으면서(월 단위) 검증40에서도 단순보유를 위험대비수익으로 이기는가'.

사용: python -m scripts.analyze_xrp_hourly
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import strategies as S  # noqa: E402
from src.backtest import run_backtest  # noqa: E402
from src.bitfinex_data import load_dir  # noqa: E402
from src.metrics import risk_metrics  # noqa: E402
from src.swing import SwingConfig, backtest_coin, resample  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PPY = 24 * 365   # 시간봉 연환산 계수


def load_hourly() -> pd.DataFrame:
    d = load_dir(ROOT / "data" / "bitfinex")
    return resample(d["XRP"], "1h")


def n_entries(pos: pd.Series) -> int:
    """0/1 포지션에서 '신규 진입(0→1)' 횟수 = 거래 수."""
    p = pos.fillna(0).to_numpy()
    return int(((p[1:] == 1) & (p[:-1] == 0)).sum())


def metr_from_positions(df: pd.DataFrame, pos: pd.Series) -> dict:
    res = run_backtest(df, pos)
    m = risk_metrics(res.equity, PPY, positions=pos)
    m["trades"] = n_entries(pos)
    return m


def metr_from_swing(df: pd.DataFrame, cfg: SwingConfig) -> dict | None:
    trades = backtest_coin(df, cfg)
    if not trades:
        return None
    trades = sorted(trades, key=lambda t: t.entry_time)
    eq = pd.Series(np.cumprod([1.0] + [1 + t.net for t in trades]))
    years = len(df) / PPY
    total = float(eq.iloc[-1] - 1)
    cagr = ((1 + total) ** (1 / years) - 1) if years > 0 else 0.0
    mdd = float((eq / eq.cummax() - 1).min())
    wins = sum(1 for t in trades if t.net > 0)
    return {"total_return": total, "cagr": cagr, "mdd": mdd,
            "calmar": (cagr / abs(mdd)) if mdd < 0 else float("inf"),
            "trades": len(trades), "win": wins / len(trades)}


# 시간봉용 스윙 변형 (파라미터는 '시간' 단위: base 48h=2일 등)
SWING_VARIANTS = {
    "급등추격 기본(4일박스)":  SwingConfig(),
    "급등추격 짧게(2일박스)":  SwingConfig(base_bars=48, recent_bars=4, self_ma_bars=60,
                                     max_hold_bars=120, vol_surge=2.5),
    "급등추격 민감(1일박스)":  SwingConfig(base_bars=24, recent_bars=3, self_ma_bars=48,
                                     max_hold_bars=72, vol_surge=2.0, min_momentum=0.01),
}


def evaluate(df: pd.DataFrame, label: str, out: list[str]) -> list[dict]:
    years = len(df) / PPY
    rows: list[dict] = []

    bh = metr_from_positions(df, pd.Series(1, index=df.index))
    bh["name"] = "단순보유"; bh["is_bh"] = True
    rows.append(bh)

    for name, cfg in SWING_VARIANTS.items():
        m = metr_from_swing(df, cfg)
        if m:
            m["name"] = name; m["is_bh"] = False; m["win_known"] = True
            rows.append(m)

    # 눌림목/평균회귀 + 추세 (0/1 시그널 전략)
    sig = {
        "눌림목 볼린저(20,2σ)": S.bollinger_bands(df),
        "눌림목 RSI(14,30/70)": S.rsi_strategy(df),
        "추세 MA교차(5/20)": S.ma_crossover(df),
        "추세 MACD": S.macd(df),
    }
    for name, pos in sig.items():
        m = metr_from_positions(df, pos)
        m["name"] = name; m["is_bh"] = False
        rows.append(m)

    rows.sort(key=lambda r: (r["calmar"] if np.isfinite(r["calmar"]) else -9), reverse=True)
    line = (f"\n{'='*86}\n[{label}]  (기간 {years:.1f}년, 시간봉)  "
            f"Calmar 내림차순\n{'-'*86}\n"
            f"{'전략':<22}{'거래':>6}{'거래/년':>8}{'승률':>6}"
            f"{'전체수익':>11}{'MDD':>8}{'Calmar':>8}")
    buf = [line]
    for r in rows:
        star = " ◀기준" if r.get("is_bh") else ""
        win = f"{r['win']*100:>5.0f}%" if r.get("win") is not None else "   - "
        buf.append(
            f"{r['name']:<22}{r['trades']:>6}{r['trades']/years:>8.1f}{win:>6}"
            f"{r['total_return']*100:>10.0f}%{r['mdd']*100:>7.0f}%{r['calmar']:>8.2f}{star}")
    block = "\n".join(buf)
    print(block); out.append(block)
    return rows


def main() -> None:
    df = load_hourly()
    out: list[str] = []
    d0, d1 = df["datetime"].iloc[0], df["datetime"].iloc[-1]
    head = (f"\n{'#'*86}\n# 리플(XRP) 시간봉 스윙 검증 — {pd.Timestamp(d0).date()} ~ "
            f"{pd.Timestamp(d1).date()} ({len(df):,}시간봉)\n{'#'*86}")
    print(head); out.append(head)

    # 전체
    evaluate(df, "전체기간", out)
    # 학습60 / 검증40 (검증40이 진짜 신뢰 구간)
    cut = int(len(df) * 0.6)
    evaluate(df.iloc[:cut].reset_index(drop=True), "학습 앞60%", out)
    test_rows = evaluate(df.iloc[cut:].reset_index(drop=True), "검증 뒤40%(신뢰)", out)

    # 판정: 검증40에서 '월 1회 이상(연≥12) 거래 + 단순보유를 Calmar로 이긴' 전략
    years_test = (len(df) - cut) / PPY
    bh = next((r for r in test_rows if r.get("is_bh")), None)
    verdict = ["\n" + "=" * 86, "[판정 — 검증 뒤40% 기준]"]
    if bh:
        actives = [r for r in test_rows if not r.get("is_bh")
                   and r["trades"] / years_test >= 12          # 월 1회 이상
                   and np.isfinite(r["calmar"]) and np.isfinite(bh["calmar"])
                   and r["calmar"] > bh["calmar"] and r["total_return"] > 0]
        if actives:
            verdict.append("  ✅ '월 1회 이상 거래하면서 검증구간에서 단순보유를 이긴' 전략:")
            for r in actives:
                verdict.append(f"     · {r['name']}: 연 {r['trades']/years_test:.0f}회, "
                               f"검증수익 {r['total_return']*100:+.0f}%, Calmar {r['calmar']:.2f}")
            verdict.append("  → 이 중 하나를 시간봉 봇으로 도입할 근거 있음(모의 재확인 권장).")
        else:
            verdict.append("  ✗ 월 1회 이상 자주 거래하면서 '검증구간에서도' 단순보유를 위험대비수익으로")
            verdict.append("    이긴 전략은 없음. → 시간봉으로 자주 매매하면 이 데이터에선 오히려 손해.")
            verdict.append("    (정직한 결론: 잦은 매매가 곧 수익은 아니다. 도입 보류가 타당.)")
    verdict += ["\n※ 데이터가 2017~2019(폭등+폭락) 한정이라 '최근 시장' 대표성은 약함.",
                "※ 시간봉 합성 후 봉내 청산은 근사 — 채택 시 반드시 모의로 재확인."]
    vblock = "\n".join(verdict)
    print(vblock); out.append(vblock)

    (ROOT / "data" / "xrp_hourly_report.txt").write_text("\n".join(out), encoding="utf-8")


if __name__ == "__main__":
    main()
