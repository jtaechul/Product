"""대형코인(BTC·ETH·XRP) 추세필터 '레짐' 전략 — 위험 대비 수익 중심.

analyze_majors 분석 결론을 코드화한 모듈입니다. 핵심 발견:
  · 대형코인은 buy&hold 수익이 매우 강하지만 최대낙폭(MaxDD)이 -85~95%로 가혹하다.
  · 종가가 장기 이동평균(기본 200일) '위'일 때만 보유하고, '아래'면 현금으로 빠지는
    추세필터는 강세장 수익을 대부분 따라가면서 약세장 폭락을 피해 MaxDD를 절반 수준으로
    줄였다(검증 뒤40% 구간에서도 BTC·ETH에서 buy&hold 대비 Calmar 우위).
  · 매매가 드물어(레짐 전환 시에만) 비용·휩쏘에 강하고 규칙이 단순해 견고하다.

따라서 이 전략은 '수익 극대화'가 아니라 '낙폭을 줄이며 꾸준히'(위험대비수익)를 노린다.

순수 함수 — 네트워크 없이 동일 로직으로 백테스트/모의/실거래가 작동한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class MajorsConfig:
    coins: tuple[str, ...] = ("KRW-BTC", "KRW-ETH", "KRW-XRP")
    ma_bars: int = 200       # 추세 이동평균 기간(일봉 200일 = 고전적 강/약세 분기선)
    buffer: float = 0.0      # MA 대비 ±완충(휩쏘 완화). 예 0.02 → MA보다 2% 위/아래에서 전환


def regime(df: pd.DataFrame, cfg: MajorsConfig) -> dict:
    """최신 일봉 기준 '보유 vs 현금' 판정과 근거를 반환.

    df: OHLCV(datetime,open,high,low,close,volume), 오름차순. ma_bars+1 개 이상 필요.
    반환: {in_market, price, ma, dist(=현재가/MA-1)}
    """
    close = df["close"]
    ma_series = close.rolling(cfg.ma_bars).mean()
    price = float(close.iloc[-1])
    ma = float(ma_series.iloc[-1])
    dist = price / ma - 1.0 if ma > 0 else 0.0
    # 완충: MA보다 buffer 만큼 위로 올라서야 진입, buffer 만큼 아래로 내려가야 청산
    in_market = dist > cfg.buffer
    return {"in_market": in_market, "price": price, "ma": ma, "dist": dist}
