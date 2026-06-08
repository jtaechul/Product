"""리스크 관리 — 손절(stop-loss) / 익절(take-profit).

전략이 만든 포지션(0/1)에 손절·익절 규칙을 덧씌워 '조정된 포지션'을 만듭니다.
  - 손절: 매수가 대비 -stop_loss% 떨어지면 강제 매도
  - 익절: 매수가 대비 +take_profit% 오르면 강제 매도
손절/익절로 빠져나온 뒤에는, 전략 신호가 한 번 0으로 리셋되기 전까지 재진입을 막아
같은 신호로 곧바로 다시 사는 것을 방지합니다.
"""

from __future__ import annotations

import pandas as pd


def apply_risk_management(
    df: pd.DataFrame,
    positions: pd.Series,
    stop_loss: float | None = None,
    take_profit: float | None = None,
) -> pd.Series:
    """포지션에 손절/익절을 적용한 조정 포지션 Series 반환.

    stop_loss / take_profit 은 비율(예: 0.05 = 5%). None 이면 해당 규칙 미적용.
    """
    close = df["close"].reset_index(drop=True)
    sig = positions.reset_index(drop=True)
    adjusted = [0] * len(df)

    in_pos = False
    entry = 0.0
    blocked = False  # 손절/익절 후 재진입 차단 상태

    for i in range(len(df)):
        price = float(close.iloc[i])
        signal = int(sig.iloc[i])

        if not in_pos:
            if signal == 0:
                blocked = False  # 전략이 비보유로 리셋되면 차단 해제
            if signal == 1 and not blocked:
                in_pos = True
                entry = price
                adjusted[i] = 1
            else:
                adjusted[i] = 0
        else:
            hit_sl = stop_loss is not None and price <= entry * (1 - stop_loss)
            hit_tp = take_profit is not None and price >= entry * (1 + take_profit)
            if hit_sl or hit_tp:
                in_pos = False
                adjusted[i] = 0
                blocked = True  # 전략 신호가 0으로 돌아올 때까지 재진입 금지
            elif signal == 0:
                in_pos = False
                adjusted[i] = 0
            else:
                adjusted[i] = 1

    return pd.Series(adjusted, index=positions.index)
