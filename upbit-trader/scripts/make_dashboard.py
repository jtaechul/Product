#!/usr/bin/env python3
"""대시보드 생성 — 백테스트 결과를 dashboard.html 로 만듭니다.

사용법:
    python scripts/make_dashboard.py                 # 합성(데모) 데이터
    python scripts/make_dashboard.py --csv data.csv  # 내 데이터
    python scripts/make_dashboard.py --out my.html   # 출력 파일명 지정

생성된 HTML 을 브라우저로 열면 차트로 결과를 볼 수 있습니다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest import run_backtest  # noqa: E402
from src.dashboard import build_dashboard_html  # noqa: E402
from src.paper_trader import run_paper_trading  # noqa: E402
from src.sample_data import generate_synthetic_ohlcv, load_csv  # noqa: E402
from src.strategies import STRATEGIES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="대시보드 HTML 생성")
    parser.add_argument("--csv", help="OHLCV CSV 경로 (없으면 합성 데이터)")
    parser.add_argument("--out", default="dashboard.html", help="출력 파일명")
    args = parser.parse_args()

    df = load_csv(args.csv) if args.csv else generate_synthetic_ohlcv()
    dates = df["datetime"].dt.strftime("%Y-%m-%d").tolist()
    price = [round(p, 2) for p in df["close"].tolist()]

    comparison = []
    best = None  # (return, name, fn)
    for name, fn in STRATEGIES.items():
        r = run_backtest(df, fn(df))
        comparison.append({
            "name": name,
            "total_return": round(r.total_return, 4),
            "buy_hold": round(r.buy_hold_return, 4),
            "num_trades": r.num_trades,
            "win_rate": round(r.win_rate, 4),
            "max_drawdown": round(r.max_drawdown, 4),
            "equity": [round(e, 4) for e in r.equity.tolist()],
        })
        if best is None or r.total_return > best[0]:
            best = (r.total_return, name, fn)

    # 가장 성적 좋은 전략의 매매 시점 + 거래 일지
    _, best_name, best_fn = best
    account = run_paper_trading(df, best_fn)
    markers = [{
        "date": t.datetime.strftime("%Y-%m-%d"),
        "action": t.action,
        "price": round(t.price, 2),
        "value": round(t.value_after, 0),
    } for t in account.trades]

    source = f"CSV: {args.csv}" if args.csv else "합성(데모) 데이터 — 실제 시세 아님"
    meta = (f"데이터: {source} | 기간: {dates[0]} ~ {dates[-1]} ({len(df)}일) | "
            f"최고 전략: {best_name}")
    warning = ("이 대시보드는 합성(데모) 데이터 기준입니다. 실제 수익을 보장하지 않습니다. "
               "실데이터 CSV로 --csv 옵션을 쓰면 실제 검증이 가능합니다."
               if not args.csv else
               "백테스트 결과는 과거 데이터 기준이며 미래 수익을 보장하지 않습니다.")

    html = build_dashboard_html(dates, price, comparison, markers,
                                best_name, meta, warning)
    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"대시보드 생성 완료 → {out.resolve()}")
    print("브라우저로 열어보세요 (인터넷 연결 시 차트가 표시됩니다).")


if __name__ == "__main__":
    main()
