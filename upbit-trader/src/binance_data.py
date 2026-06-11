"""Binance 공개 아카이브 1분봉(kline) CSV/ZIP 로더.

data.binance.vision 에서 받은 월별 zip(예: NEOUSDT-1m-2024-11.zip)을
백테스트 엔진이 쓰는 OHLCV DataFrame(datetime, open, high, low, close, volume)
으로 변환합니다. 같은 심볼의 여러 달 파일은 자동으로 이어 붙입니다.

Binance kline 컬럼(헤더 없음):
  open_time(ms), open, high, low, close, volume, close_time(ms),
  quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

KLINE_COLS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]

# 파일명에서 심볼 추출: NEOUSDT-1m-2024-11.(zip|csv)
_NAME_RE = re.compile(r"^([A-Z0-9]+)-1m-\d{4}-\d{2}\.(zip|csv)$")


def _read_kline_csv(handle) -> pd.DataFrame:
    df = pd.read_csv(handle, header=None, names=KLINE_COLS,
                     usecols=["open_time", "open", "high", "low", "close", "volume"])
    # 2025년 이후 아카이브는 마이크로초(us) 타임스탬프를 쓰기도 함
    unit = "us" if df["open_time"].iloc[0] > 10 ** 14 else "ms"
    df["datetime"] = pd.to_datetime(df["open_time"], unit=unit)
    return df[["datetime", "open", "high", "low", "close", "volume"]]


def load_symbol_files(files: list[Path]) -> pd.DataFrame:
    """한 심볼의 월별 zip/csv 들을 읽어 시간순으로 이어 붙임."""
    frames = []
    for f in sorted(files):
        if f.suffix == ".zip":
            with zipfile.ZipFile(f) as z:
                inner = z.namelist()[0]
                with z.open(inner) as fh:
                    frames.append(_read_kline_csv(fh))
        else:
            frames.append(_read_kline_csv(f))
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates("datetime").sort_values("datetime").reset_index(drop=True)
    return df


def load_dir(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """폴더 안의 *-1m-YYYY-MM.zip/csv 를 심볼별로 묶어 전부 로드.

    반환: {"NEOUSDT": df, "TRXUSDT": df, ...}
    """
    data_dir = Path(data_dir)
    by_symbol: dict[str, list[Path]] = {}
    for f in data_dir.iterdir():
        m = _NAME_RE.match(f.name)
        if m:
            by_symbol.setdefault(m.group(1), []).append(f)
    return {sym: load_symbol_files(files) for sym, files in sorted(by_symbol.items())}


def align_on_union(data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """모든 심볼을 공통(합집합) 1분 시간축에 맞춤 — 엔진은 동일 인덱스를 가정.

    빠진 구간(데이터 공백, 늦은 상장 등)은 가격은 직전 종가로 고정하고
    거래량은 0으로 채웁니다. 거래량 0이면 스캐너/진입 트리거가 작동하지
    않으므로 가짜 신호가 생기지 않습니다.
    """
    start = min(df["datetime"].iloc[0] for df in data.values())
    end = max(df["datetime"].iloc[-1] for df in data.values())
    idx = pd.date_range(start, end, freq="1min")

    aligned = {}
    for sym, df in data.items():
        s = df.set_index("datetime").reindex(idx)
        s["volume"] = s["volume"].fillna(0.0)
        s["close"] = s["close"].ffill().bfill()
        for col in ("open", "high", "low"):
            s[col] = s[col].fillna(s["close"])
        aligned[sym] = s.rename_axis("datetime").reset_index()
    return aligned
