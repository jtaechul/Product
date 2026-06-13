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
    # optimize_majors 교차검증으로 선택한 기본값:
    #   · MA150  : 200일선보다 짧아 폭락 후 회복에 빨리 재진입(수익↑) — 일봉/시간봉 모두 우수
    #   · 완충2% : MA±2% 밴드(hysteresis)로 경계선 부근 헛매매(휩쏘) 차단 — 양쪽 데이터 개선
    ma_bars: int = 150        # 추세 이동평균 기간(일봉=일)
    buffer: float = 0.02      # MA 대비 ±완충 밴드. 위로 +buffer 넘어야 진입, 아래로 -buffer 깨야 청산
    slope_bars: int = 0       # >0 이면 MA가 slope_bars 전보다 높을(우상향) 때만 보유(옵션, 기본 끔)


def regime(df: pd.DataFrame, cfg: MajorsConfig, held: bool = False) -> dict:
    """최신 일봉 기준 '보유 vs 현금' 판정과 근거를 반환 (완충밴드 hysteresis 적용).

    held: 지금 그 코인을 보유 중인지. 보유 중이면 -buffer 밴드 아래로 깨질 때까지 유지하고,
          비보유면 +buffer 밴드 위로 올라설 때만 신규 진입 → 경계선 잔떨림에 안 휘둘림.
    df: OHLCV(datetime,open,high,low,close,volume), 오름차순. ma_bars+1 개 이상 필요.
    반환: {in_market, price, ma, dist(=현재가/MA-1), rising}
    """
    close = df["close"]
    ma_series = close.rolling(cfg.ma_bars).mean()
    price = float(close.iloc[-1])
    ma = float(ma_series.iloc[-1])
    dist = price / ma - 1.0 if ma > 0 else 0.0

    rising = True
    if cfg.slope_bars > 0 and len(ma_series) > cfg.slope_bars:
        prev = float(ma_series.iloc[-1 - cfg.slope_bars])
        rising = ma > prev

    if held:
        # 보유 유지: -buffer 밴드 위에 있고 (기울기 옵션 시) 우상향이면 계속 보유
        in_market = dist >= -cfg.buffer and rising
    else:
        # 신규 진입: +buffer 밴드 위 + (기울기 옵션 시) 우상향
        in_market = dist > cfg.buffer and rising
    return {"in_market": in_market, "price": price, "ma": ma,
            "dist": dist, "rising": rising}
