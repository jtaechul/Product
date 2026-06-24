"""공통 백테스트 유틸리티 — 여러 검증 스크립트에서 재사용."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume",
              "close_time", "quote_volume", "trades",
              "taker_buy_base", "taker_buy_quote", "ignore"]


def load_1h_dir(data_dir: Path) -> dict[str, pd.DataFrame]:
    """폴더의 {SYM}-1h-YYYY-MM.csv 들을 심볼별로 묶어 시간순 연결."""
    by_sym: dict[str, list[Path]] = {}
    for f in sorted(data_dir.glob("*.csv")):
        sym = f.name.split("-", 1)[0]
        by_sym.setdefault(sym, []).append(f)
    out = {}
    for sym, files in sorted(by_sym.items()):
        frames = []
        for f in sorted(files):
            df = pd.read_csv(f, header=None, names=KLINE_COLS,
                             usecols=["open_time", "open", "high", "low",
                                      "close", "volume"])
            if df.empty:
                continue
            # 2025년 이후 아카이브는 마이크로초(us) 타임스탬프를 쓰기도 함
            unit = "us" if df["open_time"].iloc[0] > 10 ** 14 else "ms"
            df["datetime"] = pd.to_datetime(df["open_time"], unit=unit)
            frames.append(df[["datetime", "open", "high", "low", "close", "volume"]])
        if not frames:
            continue
        out[sym] = pd.concat(frames, ignore_index=True)
    return out


def equity_metrics(trades) -> dict | None:
    """거래 리스트 → 복리 자산곡선으로 위험대비수익 지표."""
    if not trades:
        return None
    ts = sorted(trades, key=lambda t: t.entry_time)
    eq = [1.0]
    for t in ts:
        eq.append(eq[-1] * (1 + t.net))
    eq = pd.Series(eq)
    dd = float((eq / eq.cummax() - 1).min())
    nets = np.array([t.net for t in ts])
    span = pd.Timestamp(ts[-1].exit_time) - pd.Timestamp(ts[0].entry_time)
    span_days = max(1, span.days)
    years = span_days / 365.25
    total = float(eq.iloc[-1] - 1)
    cagr = float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    calmar = (cagr / abs(dd)) if dd < 0 else float("inf")
    return {"n": len(ts), "total": total, "cagr": cagr, "mdd": dd,
            "calmar": calmar, "win": float((nets > 0).mean())}
