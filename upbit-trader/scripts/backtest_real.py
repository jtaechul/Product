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
    p.add_argument("--initial-stop", type=float, default=2.5,
                   help="활성화 전 초기 손절 %% (0이면 비활성화)")
    p.add_argument("--min-dormancy", type=float, default=0.0,
                   help="잠수함 게이트: 직전 구간 dormancy 하한 (0~1)")
    p.add_argument("--max-chase", type=float, default=4.0,
                   help="추격 차단: 15분 상승률 상한 %% (0이면 비활성화)")
    p.add_argument("--daily-loss", type=float, default=0.0,
                   help="일일 손실 한도(원, 1거래 1만원 기준. 0=무제한)")
    p.add_argument("--loss-mult", type=float, default=1.0,
                   help="연속 손실 쿨다운 점증 배수 (1=점증 없음)")
    p.add_argument("--brake", type=float, default=4.0,
                   help="코인별 주간 브레이크: 최근 N일 누적 -X%% 손실 시 차단 (0=끔)")
    p.add_argument("--brake-window", type=int, default=7, help="브레이크 집계 기간(일)")
    p.add_argument("--brake-block", type=int, default=3, help="브레이크 차단 기간(일)")
    p.add_argument("--show-trades", action="store_true")
    p.add_argument("--dump-trades", default=None,
                   help="거래+진입특징을 CSV로 저장할 경로")
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
            initial_stop_pct=(args.initial_stop / 100
                              if args.initial_stop > 0 else None),
        ),
        max_positions=args.max_positions,
        min_score=args.min_score,
        min_dormancy=args.min_dormancy,
        max_momentum_15m=(args.max_chase / 100 if args.max_chase > 0 else None),
        daily_loss_limit=(args.daily_loss if args.daily_loss > 0 else None),
        loss_cooldown_mult=args.loss_mult,
        brake_loss_pct=(args.brake / 100 if args.brake > 0 else None),
        brake_window_days=args.brake_window,
        brake_block_days=args.brake_block,
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

        # 진입 특징 비교 (승 vs 패) — 필터 튜닝 근거
        wins_t = [t for t in result.trades if t.net_pct > 0 and t.features]
        loss_t = [t for t in result.trades if t.net_pct <= 0 and t.features]

        def favg(ts, key):
            vals = [t.features[key] for t in ts if key in t.features]
            return sum(vals) / len(vals) if vals else float("nan")

        if wins_t or loss_t:
            print(f"\n  진입 특징 평균 (승 {len(wins_t)}회 vs 패 {len(loss_t)}회):")
            for key in ("score", "vol_surge", "breakout", "momentum_15m", "dormancy"):
                print(f"    {key:<14} 승 {favg(wins_t, key):>8.4f} | "
                      f"패 {favg(loss_t, key):>8.4f}")

        if args.show_trades:
            print("\n  개별 거래:")
            for t in result.trades:
                held = (t.exit_time - t.entry_time).total_seconds() / 60
                print(f"    {t.market:10} {t.entry_time} → {t.exit_time} "
                      f"({held:>4.0f}분) {t.net_pct * 100:+6.2f}%  {t.reason}")

        if args.dump_trades:
            rows = []
            for t in result.trades:
                row = {"market": t.market, "entry_time": t.entry_time,
                       "exit_time": t.exit_time, "net_pct": t.net_pct,
                       "reason": t.reason}
                row.update(t.features)
                rows.append(row)
            pd.DataFrame(rows).to_csv(args.dump_trades, index=False)
            print(f"\n  거래 내역 저장: {args.dump_trades}")
    print()


if __name__ == "__main__":
    main()
