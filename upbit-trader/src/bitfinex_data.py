"""Bitfinex 공개 1분봉 로더 (Zombie-3000/Bitfinex-historical-data 형식).

파일: data/bitfinex/{COIN}-{YEAR}.csv  (헤더 없음)
컬럼 순서(Bitfinex API 원형): [timestamp_ms, open, close, high, low, volume]
  ⚠️ OHLC 가 아니라 O,C,H,L 순서입니다. 매핑 시 주의.

거래소 API가 막힌 환경에서 git clone 으로 받은, Binance(2024~)와 완전히 독립인
검증 표본입니다: 다른 거래소·다른 코인·2013~2019·USD 표시.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Bitfinex merged.csv 컬럼 (O,C,H,L 순서!)
_COLS = ["ts", "open", "close", "high", "low", "volume"]


def load_file(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, header=None, names=_COLS)
    df["datetime"] = pd.to_datetime(df["ts"], unit="ms")
    df = df[["datetime", "open", "high", "low", "close", "volume"]]
    return df.dropna().reset_index(drop=True)


def load_dir(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """data/bitfinex 의 {COIN}-{YEAR}.csv 들을 코인별로 묶어 시간순 연결.

    반환: {"NEO": df, "XRP": df, ...} — 엔진 호환(datetime,open,high,low,close,volume).
    """
    data_dir = Path(data_dir)
    by_coin: dict[str, list[Path]] = {}
    for f in data_dir.glob("*.csv"):
        coin = f.stem.split("-")[0]
        by_coin.setdefault(coin, []).append(f)
    out = {}
    for coin, files in sorted(by_coin.items()):
        frames = [load_file(f) for f in sorted(files)]
        df = pd.concat(frames, ignore_index=True)
        df = df.drop_duplicates("datetime").sort_values("datetime")
        out[coin] = df.reset_index(drop=True)
    return out
