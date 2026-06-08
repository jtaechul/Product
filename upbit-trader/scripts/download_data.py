#!/usr/bin/env python3
"""실제 과거 시세를 업비트에서 받아 CSV 로 저장합니다 (백테스트용).

⚠️ 이 스크립트는 인터넷 연결(api.upbit.com 접근)이 필요합니다. 본인 PC에서 실행하세요.
   인증은 필요 없습니다(시세 API).

사용법:
    python scripts/download_data.py                         # KRW-BTC 일봉 1000개 → data.csv
    python scripts/download_data.py --market KRW-ETH --count 2000
    python scripts/download_data.py --interval minute --unit 60 --count 500
    python scripts/download_data.py --out btc.csv

저장된 CSV 는 그대로 다른 스크립트에 사용:
    python scripts/run_backtest.py --csv data.csv
    python scripts/validate.py --csv data.csv
    python scripts/make_dashboard.py --csv data.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src.upbit_quotation import UpbitQuotation, candles_to_dataframe  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="업비트 과거 시세 CSV 다운로드")
    parser.add_argument("--market", default="KRW-BTC", help="마켓 코드 (기본 KRW-BTC)")
    parser.add_argument("--interval", choices=["day", "minute"], default="day")
    parser.add_argument("--unit", type=int, default=60,
                        help="분봉 단위(분). interval=minute 일 때 사용")
    parser.add_argument("--count", type=int, default=1000, help="받을 캔들 개수")
    parser.add_argument("--out", default="data.csv", help="저장 파일명")
    args = parser.parse_args()

    client = UpbitQuotation()
    label = f"{args.interval}" + (f"/{args.unit}분" if args.interval == "minute" else "")
    print(f"{args.market} {label} 캔들 {args.count}개 다운로드 중...")

    try:
        candles = client.collect_candles(
            args.market, total=args.count, interval=args.interval, unit=args.unit
        )
    except requests.exceptions.RequestException as exc:
        print(f"[오류] 다운로드 실패: {exc}")
        print("  → 인터넷 연결 / api.upbit.com 접근 가능 여부를 확인하세요.")
        sys.exit(1)

    df = candles_to_dataframe(candles)
    df = df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)

    out = Path(args.out)
    df.to_csv(out, index=False)
    print(f"저장 완료: {out.resolve()}  ({len(df)}개)")
    print(f"기간: {df['datetime'].iloc[0]} ~ {df['datetime'].iloc[-1]}")
    print(f"\n이제 검증해 보세요:\n  python scripts/validate.py --csv {args.out}")


if __name__ == "__main__":
    main()
