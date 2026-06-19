"""시장 국면(레짐) 판별 + 국면별 권장 자산배분 제안.

목적: BTC 일봉으로 시장을 강세/중립/약세로 객관 분류하고, 국면에 맞는 3봇 비중을
'규칙 기반'으로 제안한다. (감이 아니라 미리 정해 둔 표 → 일관·설명가능)

판별:
  · BTC 종가가 200일선 위 = 큰 추세 강세 / 아래 = 약세
  · 50일선 위/아래 = 중기 모멘텀
  · 둘 다 위 → 강세(위험선호), 하나만 위 → 중립(조정), 둘 다 아래 → 약세(위험회피)

국면별 비중(2019~2026 교차검증 반영):
  검증 통과 전략은 '대형코인 추세필터(BTC·ETH)' 하나뿐 → 실거래는 대형 100% 고정.
  (방어는 대형봇 자체의 추세필터가 BTC·ETH를 약세 때 현금화하므로 충분. 별도 현금배분 불필요)
  잠수함·고위험은 엣지 미검증 → 비중 0(모의에서만 운용).

※ 휴리스틱 규칙입니다. 시장을 '예측'이 아니라 '추세에 반응'하는 보수적 설계.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# 검증 결과: 대형코인 추세필터만 채택 → 모든 국면에서 대형 100%(나머지 0).
# 라벨은 대시보드 정보용으로 유지(국면 자체는 계속 표시).
_ALL_MAJORS = {"majors": 1.0, "swing": 0.0, "highrisk": 0.0}
REGIMES = {
    "risk_on":  {"label": "강세 (위험선호) 🟢", "weights": dict(_ALL_MAJORS)},
    "neutral":  {"label": "중립 (약한 조정) 🟡", "weights": dict(_ALL_MAJORS)},
    "risk_off": {"label": "약세 (위험회피) 🔴", "weights": dict(_ALL_MAJORS)},
}


def detect_regime(df: pd.DataFrame) -> dict:
    """BTC 일봉 OHLCV(또는 close 포함) → 국면 + 권장비중 + 근거."""
    c = df["close"].astype(float)
    price = float(c.iloc[-1])
    ma50 = c.rolling(50).mean().iloc[-1]
    ma200 = c.rolling(200).mean().iloc[-1]
    rets = c.pct_change().dropna()
    vol = float(rets.tail(30).std() * np.sqrt(365)) if len(rets) >= 30 else 0.0

    above50 = bool(price > ma50) if not pd.isna(ma50) else True
    above200 = bool(price > ma200) if not pd.isna(ma200) else above50

    if above200 and above50:
        key = "risk_on"
    elif above200 or above50:
        key = "neutral"
    else:
        key = "risk_off"

    r = REGIMES[key]
    cash = round(1.0 - sum(r["weights"].values()), 4)
    return {
        "key": key, "label": r["label"], "weights": dict(r["weights"]), "cash": cash,
        "price": price,
        "ma50": float(ma50) if not pd.isna(ma50) else None,
        "ma200": float(ma200) if not pd.isna(ma200) else None,
        "vol": vol, "above50": above50, "above200": above200,
    }
