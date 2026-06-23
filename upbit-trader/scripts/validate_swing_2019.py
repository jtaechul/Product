#!/usr/bin/env python3
"""잠수함(스윙 펌프) 봇 2019~2026 독립표본 검증 (Binance 1시간봉).

왜 필요한가:
  잠수함봇은 실거래 중인데, 검증을 주로 2013~2019(Bitfinex)으로 했다.
  돌파추격·로테이션 두 전략이 '2013~2019 좋음 → 2019~2026 실패'를 보였으므로,
  실제 돈이 걸린 잠수함봇이 최근 시장(2019~2026)에서도 통하는지 반드시 확인한다.

설정은 실거래와 동일: SwingConfig 기본값 + BTC 게이트 OFF(라이브가 --btc-ma 0).
파라미터는 손대지 않는다(검증 전용).

실행(서버):
    cd ~/Product/upbit-trader
    .venv/bin/python -m scripts.validate_swing_2019
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest_utils import equity_metrics, load_1h_dir  # noqa: E402
from src.swing import SwingConfig, backtest_coin, resample  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "binance_1h_2019_2026"


def _row(label: str, m: dict | None) -> str:
    if not m:
        return f"{label:<8}{'(거래 없음)':>12}"
    cal = "inf" if m["calmar"] == float("inf") else f"{m['calmar']:.2f}"
    return (f"{label:<8}{m['n']:>5}{m['total']*100:>10.1f}{m['cagr']*100:>8.1f}"
            f"{m['mdd']*100:>9.1f}{cal:>8}{m['win']*100:>7.0f}")


def main() -> None:
    p = argparse.ArgumentParser(description="잠수함봇 2019~2026 검증")
    p.add_argument("--data-dir", default=str(DEFAULT_DIR))
    p.add_argument("--split", type=float, default=0.6)
    args = p.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"[오류] 데이터 폴더 없음: {data_dir}")
        sys.exit(1)
    data = load_1h_dir(data_dir)
    if not data:
        print(f"[오류] {data_dir} 에 csv 없음.")
        sys.exit(1)

    cfg = SwingConfig()  # 라이브 기본값(BTC 게이트는 btc_ma 전달 안 하면 미적용)
    print("=== 잠수함봇 현재 기본 설정(실거래와 동일, 파라미터 변경 없음) ===")
    print(f"  vol_surge={cfg.vol_surge}  min_momentum={cfg.min_momentum}  "
          f"max_chase={cfg.max_chase}  base_bars={cfg.base_bars}")
    print(f"  self_ma={cfg.self_ma_bars}  BTC게이트=OFF(라이브 --btc-ma 0)  "
          f"arm={cfg.arm_profit}  trail={cfg.trail}  stop={cfg.stop_loss}")

    hdr = (f"{'구간':<8}{'거래':>5}{'누적%':>10}{'CAGR%':>8}{'MaxDD%':>9}"
           f"{'Calmar':>8}{'승률%':>7}")
    all_full, all_tr, all_val = [], [], []
    for sym, df in sorted(data.items()):
        h = resample(df, "1h")  # 이미 1h지만 격자 정렬
        cut = int(len(h) * args.split)
        tr_full = backtest_coin(h, cfg, sym)
        tr_tr = backtest_coin(h.iloc[:cut].reset_index(drop=True), cfg, sym)
        tr_val = backtest_coin(h.iloc[cut:].reset_index(drop=True), cfg, sym)
        all_full += tr_full
        all_tr += tr_tr
        all_val += tr_val
        print(f"\n{'='*64}\n■ {sym}\n{'='*64}\n{hdr}\n{'-'*64}")
        print(_row("전체", equity_metrics(tr_full)))
        print(_row("학습60", equity_metrics(tr_tr)))
        print(_row("검증40", equity_metrics(tr_val)))

    print(f"\n{'#'*64}\n# 통합 (전 코인 합산)\n{'#'*64}\n{hdr}\n{'-'*64}")
    print(_row("전체", equity_metrics(all_full)))
    print(_row("학습60", equity_metrics(all_tr)))
    mval = equity_metrics(all_val)
    print(_row("검증40", mval))

    print("\n--- 판정(검증40 구간 기준) ---")
    if mval:
        cal = mval["calmar"]
        if cal != float("inf") and cal >= 1.0 and mval["total"] > 0:
            print(f"  ✅ 통과: 검증 Calmar {cal:.2f}, 누적 {mval['total']*100:+.1f}% "
                  "→ 최근 시장에서도 엣지 유지(실거래 지속 근거)")
        elif mval["total"] > 0:
            print(f"  ⚠️ 약함: 검증 Calmar {cal:.2f}, 누적 {mval['total']*100:+.1f}% "
                  "→ 수익은 나지만 위험대비효율 낮음")
        else:
            print(f"  ✗ 부진: 검증 누적 {mval['total']*100:+.1f}% "
                  "→ 최근 시장에서 손실, 실거래 설정 재검토 필요")
    print("  ※ 6개 코인(BTC/ETH/XRP/LTC/EOS/NEO)은 잠수함봇 실제 대상(중소형 알트)과")
    print("    다를 수 있음 — 표본 한계를 감안해 해석.")


if __name__ == "__main__":
    main()
