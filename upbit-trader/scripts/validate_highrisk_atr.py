#!/usr/bin/env python3
"""고위험봇 청산방식 비교 검증 — '현재(고정 트레일)' vs 'ATR+부분익절+본전보호'.

왜:
  사용자 지적 — 변동성 큰 알트에 고정 '고점 -20%' 트레일링은 애매하게 올랐다
  빠질 때 손해 보고 팔게 된다. 업계·학계 표준(ATR 변동성 트레일링 + 부분익절 +
  본전보호)이 더 나은지 '한 번도 본 적 없는' 2019~2026 검증구간으로 객관 비교.

방법(과최적화 차단):
  1) data/binance_1h_2019_2026/*.csv 코인별 로드(1시간봉)
  2) 진입조건은 동일(모멘텀 돌파). 청산만 두 방식으로 백테스트
  3) 학습60/검증40 분할 → '검증40 구간' Calmar·MaxDD 로만 우열 판정
  4) ATR 배수(2.0/2.5/3.0)도 같이 비교 — 단 검증구간 성적으로만

실행(서버):
    cd ~/Product/upbit-trader
    .venv/bin/python -m scripts.validate_highrisk_atr
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.validate_highrisk_2019 import equity_metrics, load_1h_dir  # noqa: E402
from src.highrisk import HighRiskConfig, backtest_coin, backtest_coin_atr  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "binance_1h_2019_2026"


def _cal(m):
    if not m:
        return "    (거래없음)"
    cal = "inf" if m["calmar"] == float("inf") else f"{m['calmar']:.2f}"
    return (f"{m['n']:>5}{m['total']*100:>10.1f}{m['cagr']*100:>8.1f}"
            f"{m['mdd']*100:>9.1f}{cal:>8}{m['win']*100:>7.0f}")


def main() -> None:
    p = argparse.ArgumentParser(description="고위험봇 청산방식 비교(현재 vs ATR+부분익절)")
    p.add_argument("--data-dir", default=str(DEFAULT_DIR))
    p.add_argument("--split", type=float, default=0.6)
    p.add_argument("--partial-tp", type=float, default=0.15, help="부분익절 목표(+비율)")
    p.add_argument("--partial-frac", type=float, default=0.5, help="부분익절 비중")
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[오류] 데이터 폴더 없음: {data_dir}")
        sys.exit(1)
    data = load_1h_dir(data_dir)
    if not data:
        print(f"[오류] {data_dir} 에 csv 없음")
        sys.exit(1)

    cfg = HighRiskConfig()
    variants = [
        ("현재(고정trail)", lambda d, s: backtest_coin(d, cfg, s)),
        ("ATR×2.0+부분", lambda d, s: backtest_coin_atr(
            d, cfg, s, atr_mult=2.0, partial_tp=args.partial_tp,
            partial_frac=args.partial_frac)),
        ("ATR×2.5+부분", lambda d, s: backtest_coin_atr(
            d, cfg, s, atr_mult=2.5, partial_tp=args.partial_tp,
            partial_frac=args.partial_frac)),
        ("ATR×3.0+부분", lambda d, s: backtest_coin_atr(
            d, cfg, s, atr_mult=3.0, partial_tp=args.partial_tp,
            partial_frac=args.partial_frac)),
    ]
    print("=== 고위험봇 청산방식 비교 (진입조건 동일, 청산만 다름) ===")
    print(f"  부분익절: +{args.partial_tp*100:.0f}% 에서 {args.partial_frac*100:.0f}% 실현, "
          f"나머지 ATR 트레일 + 본전보호")
    print(f"  대상 코인: {', '.join(sorted(data.keys()))}")

    # 변형별 검증40 합산 누적
    agg_val = {name: [] for name, _ in variants}
    hdr = f"{'방식':<16}{'거래':>5}{'누적%':>10}{'CAGR%':>8}{'MaxDD%':>9}{'Calmar':>8}{'승률%':>7}"

    for sym, df in sorted(data.items()):
        cut = int(len(df) * args.split)
        val = df.iloc[cut:].reset_index(drop=True)
        print(f"\n{'='*64}\n■ {sym}  검증40 구간 ({val['datetime'].iloc[0].date()}~"
              f"{val['datetime'].iloc[-1].date()})\n{'='*64}")
        print(hdr)
        print("-" * 64)
        for name, fn in variants:
            tr = fn(val, sym)
            agg_val[name] += tr
            print(f"{name:<16}{_cal(equity_metrics(tr))}")

    print(f"\n{'#'*64}\n# 통합 검증40 (전 코인 합산) — ★판정 기준★\n{'#'*64}")
    print(hdr)
    print("-" * 64)
    best = None
    for name, _ in variants:
        m = equity_metrics(agg_val[name])
        print(f"{name:<16}{_cal(m)}")
        if m and m["total"] > 0:
            score = m["calmar"] if m["calmar"] != float("inf") else 999
            if best is None or score > best[1]:
                best = (name, score, m)

    print("\n--- 판정 ---")
    base = equity_metrics(agg_val["현재(고정trail)"])
    if best is None:
        print("  ✗ 모든 방식이 검증구간 손실 — 채택할 개선안 없음(현행 유지/축소 권고)")
    else:
        name, _, m = best
        base_cal = (base["calmar"] if base and base["calmar"] != float("inf")
                    else 0) if base else 0
        print(f"  최고: <{name}> 검증 Calmar {m['calmar']:.2f}, "
              f"MaxDD {m['mdd']*100:.1f}%, 누적 {m['total']*100:.1f}%")
        if name != "현재(고정trail)" and m["calmar"] > base_cal:
            print(f"  ✅ 개선안 우위 — '{name}'가 현재(고정trail, Calmar "
                  f"{base_cal:.2f})보다 위험대비수익 높음 → 채택 검토")
        else:
            print(f"  ⚠️ 현재 방식이 더 낫거나 비슷 → 무리한 변경 불필요")
    print("  ※ 검증40(독립표본) 기준. 학습구간만 좋은 건 과최적화로 보고 채택 안 함.")


if __name__ == "__main__":
    main()
