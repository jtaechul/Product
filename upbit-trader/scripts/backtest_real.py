#!/usr/bin/env python3
"""실데이터(Binance 1분봉) 백테스트 CLI.

data/ 폴더의 월별 zip(예: NEOUSDT-1m-2024-11.zip)을 읽어 잠수함 급등
전략을 실제 시세에 재생합니다. 합성 데이터와 달리 진짜 시장의 노이즈,
가짜 펌프, 새벽 한산 구간이 모두 들어 있습니다.

  python -m scripts.backtest_real                          # data/ 전체
  python -m scripts.backtest_real --start 2024-10-01 --end 2024-12-31
  python -m scripts.backtest_real --trail 2.5 --stop 4 --min-score 40
  python -m scripts.backtest_real --show-trades            # 개별 거래 출력
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.binance_data import align_on_union, load_dir  # noqa: E402
from src.pump_backtest import BTConfig, run_pump_backtest  # noqa: E402
from src.tracker import ExitConfig  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def print_summary(title: str, s: dict) -> None:
    print(f"\n=== {title} ===")
    if s.get("trades", 0) == 0:
        print("  거래 없음")
        return
    print(f"  총 거래        : {s['trades']}회")
    print(f"  승률           : {s['win_rate']:.1f}%")
    print(f"  평균 손익/거래 : {s['avg_net_pct']:+.2f}%")
    print(f"  평균 수익(승)  : {s['avg_win_pct']:+.2f}%")
    print(f"  평균 손실(패)  : {s['avg_loss_pct']:+.2f}%")
    print(f"  누적 순손익    : {s['total_net_pct']:+.1f}% (1거래 투자금 대비 합)")
    print(f"  최대 낙폭(MDD) : {s['max_drawdown_krw']:+,.0f}원 (1거래 1만원 기준)")
    pf = s["profit_factor"]
    print(f"  손익비(PF)     : {pf:.2f}" if pf != float("inf") else "  손익비(PF)     : ∞")


def main() -> None:
    p = argparse.ArgumentParser(description="실데이터(Binance 1분봉) 백테스트")
    p.add_argument("--data-dir", default=str(DATA_DIR), help="zip/csv 폴더")
    p.add_argument("--start", default=None, help="구간 시작 (예: 2024-10-01)")
    p.add_argument("--end", default=None, help="구간 끝 (예: 2024-12-31)")
    p.add_argument("--max-positions", type=int, default=3)
    p.add_argument("--trail", type=float, default=3.0, help="트레일링 %%")
    p.add_argument("--stop", type=float, default=5.0, help="손절 %%")
    p.add_argument("--arm", type=float, default=2.0, help="트레일링 활성화 수익 %%")
    p.add_argument("--min-score", type=float, default=0.0)
    p.add_argument("--early-cut", type=int, default=5,
                   help="조기손절 시간(분). 0이면 비활성화")
    p.add_argument("--show-trades", action="store_true")
    args = p.parse_args()

    t0 = time.time()
    raw = load_dir(args.data_dir)
    if not raw:
        print(f"[오류] {args.data_dir} 에 *-1m-YYYY-MM.zip/csv 파일이 없습니다.")
        sys.exit(1)

    if args.start or args.end:
        for sym in list(raw.keys()):
            df = raw[sym]
            if args.start:
                df = df[df["datetime"] >= pd.Timestamp(args.start)]
            if args.end:
                df = df[df["datetime"] <= pd.Timestamp(args.end) + pd.Timedelta(days=1)]
            if len(df) < 300:
                del raw[sym]  # 구간에 데이터가 거의 없는 심볼 제외
            else:
                raw[sym] = df.reset_index(drop=True)
    if not raw:
        print("[오류] 지정한 구간에 데이터가 있는 심볼이 없습니다.")
        sys.exit(1)

    data = align_on_union(raw)
    first = next(iter(data.values()))
    print(f"실데이터 로드: {len(data)}개 심볼, "
          f"{first['datetime'].iloc[0]} ~ {first['datetime'].iloc[-1]} "
          f"({len(first):,} 분봉, {time.time() - t0:.1f}초)")
    for sym, df in raw.items():
        print(f"  {sym:10} {df['datetime'].iloc[0].date()} ~ "
              f"{df['datetime'].iloc[-1].date()}  ({len(df):,}봉)")

    cfg = BTConfig(
        exit_cfg=ExitConfig(
            trail_pct=args.trail / 100,
            stop_loss_pct=args.stop / 100,
            arm_profit_pct=args.arm / 100,
            early_cut_min=args.early_cut if args.early_cut > 0 else None,
        ),
        max_positions=args.max_positions,
        min_score=args.min_score,
    )
    print("\n백테스트 실행 중...")
    t0 = time.time()
    result = run_pump_backtest(data, cfg)
    print(f"완료 ({time.time() - t0:.1f}초)")

    print_summary("실데이터 백테스트 결과", result.summary())

    if result.trades:
        # 심볼별 성적
        by_sym: dict[str, list[float]] = defaultdict(list)
        for t in result.trades:
            by_sym[t.market].append(t.net_pct)
        print("\n  심볼별 성적:")
        for sym, nets in sorted(by_sym.items(), key=lambda x: -sum(x[1])):
            wins = sum(1 for x in nets if x > 0)
            print(f"    {sym:10} {len(nets):>3}회  승률 {wins / len(nets) * 100:>5.1f}%  "
                  f"누적 {sum(nets) * 100:+7.2f}%")

        # 청산 사유 분포
        reasons = Counter(t.reason.split("(")[0] for t in result.trades)
        print("\n  청산 사유 분포:")
        for r, c in reasons.most_common():
            nets = [t.net_pct for t in result.trades if t.reason.startswith(r)]
            print(f"    {r:<14} {c:>3}회  평균 {sum(nets) / len(nets) * 100:+.2f}%")

        # 월별 성적
        by_month: dict[str, list[float]] = defaultdict(list)
        for t in result.trades:
            by_month[str(t.entry_time)[:7]].append(t.net_pct)
        print("\n  월별 성적:")
        for m in sorted(by_month):
            nets = by_month[m]
            print(f"    {m}  {len(nets):>3}회  누적 {sum(nets) * 100:+7.2f}%")

        if args.show_trades:
            print("\n  개별 거래:")
            for t in result.trades:
                held = (t.exit_time - t.entry_time).total_seconds() / 60
                print(f"    {t.market:10} {t.entry_time} → {t.exit_time} "
                      f"({held:>4.0f}분) {t.net_pct * 100:+6.2f}%  {t.reason}")
    print()


if __name__ == "__main__":
    main()
