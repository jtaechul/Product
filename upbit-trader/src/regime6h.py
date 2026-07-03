"""시기 반응형 국면 판단 — 6시간마다 '적극 / 소극 / 관망'을 결정.

철학: 고정 전략을 쓰지 않고, '지금 시국'에 맞춰 공격성을 바꾼다.
  · 적극(Aggressive): 상승·건강한 시장 → 진입조건 대폭 완화해 자주·크게 산다.
  · 소극(Passive)  : 방향 불분명(횡보) → 조심스럽게 검증된 조건으로만.
  · 관망(Observe)  : 하락·급락·악재 → 신규 매수 정지, 현금으로 지킨다.

입력은 전부 '현재 데이터'(감이 아니라 측정값):
  ① 추세: XRP·BTC가 50일선 위인지 + 50일선 기울기
  ② 모멘텀: 최근 7일 상승률
  ③ 심리: 공포탐욕지수 + 펀딩비 + Claude 뉴스 감성
규칙은 '해석 가능한 캐스케이드'(우선순위 판단)로 둬 과최적화 손잡이를 최소화한다.

⚠️ 이 판단층의 최대 효과는 '관망으로 하락을 피하는 것'이다. 적극이 돈을 더 버는지는
   시장이 준다. 검증 없이 실투자하므로 상위(봇)에서 손실 차단선을 반드시 함께 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Stance:
    stance: str                       # "적극" / "소극" / "관망"
    reason: str                       # 사람이 읽는 판단 근거(한국어)
    entry_key: str | None             # 진입설정 키("적극"/"소극") · 관망이면 None
    inputs: dict = field(default_factory=dict)


def _trend(df: pd.DataFrame, ma_bars: int = 50, slope_bars: int = 10):
    """(50일선 위인가, 50일선 상승중인가, 현재가, ma) 반환. 데이터 부족 시 (None...)."""
    close = df["close"]
    if len(close) < ma_bars + slope_bars + 1:
        return None, None, float(close.iloc[-1]), None
    ma = close.rolling(ma_bars).mean()
    price = float(close.iloc[-1])
    ma_now = float(ma.iloc[-1])
    ma_prev = float(ma.iloc[-1 - slope_bars])
    return price > ma_now, ma_now > ma_prev, price, ma_now


def _momentum(df: pd.DataFrame, bars: int = 7) -> float:
    close = df["close"]
    if len(close) < bars + 1:
        return 0.0
    ref = float(close.iloc[-1 - bars])
    return float(close.iloc[-1]) / ref - 1.0 if ref > 0 else 0.0


def decide(xrp: pd.DataFrame, btc: pd.DataFrame | None,
           fear_greed: int | None, funding: float | None,
           news_score: int | None) -> Stance:
    """현재 데이터로 스탠스 판정. 캐스케이드(관망 → 적극 → 소극) 순서로 평가."""
    x_above, x_rising, x_price, x_ma = _trend(xrp)
    b_above, _, _, _ = _trend(btc) if btc is not None else (None, None, None, None)
    mom = _momentum(xrp)
    inp = {"xrp_above_ma50": x_above, "xrp_rising": x_rising, "xrp_mom7": round(mom, 3),
           "btc_above_ma50": b_above, "fear_greed": fear_greed,
           "funding": funding, "news": news_score}

    fg_txt = (f"공포탐욕 {fear_greed}" if fear_greed is not None else "공포탐욕 N/A")
    fund_txt = (f"펀딩 {funding*100:+.3f}%" if funding is not None else "펀딩 N/A")

    # 데이터가 모자라면 안전하게 관망
    if x_above is None:
        return Stance("관망", "가격 데이터 부족 — 안전하게 관망", None, inp)

    # ── ① 관망: 지켜야 할 국면 ─────────────────────────────
    if news_score is not None and news_score <= -50:
        return Stance("관망", f"강한 악재 뉴스({news_score}) — 신규 매수 정지", None, inp)
    if (not x_above) and (not x_rising):
        return Stance("관망",
                      f"XRP 하락추세(50일선 아래·하향) — 지키기 우선 [{fg_txt}]", None, inp)
    if b_above is False and mom < 0.05:
        return Stance("관망",
                      f"비트코인 약세(50일선 아래)+XRP 약함 — 동반하락 회피 [{fg_txt}]",
                      None, inp)

    # ── ② 적극: 상승·건강한 국면(진입 대폭 완화) ─────────────
    aggressive = (
        x_above and x_rising
        and (b_above is not False or mom > 0.10)       # 시장 OK 또는 XRP 독자 강세
        and (fear_greed is None or fear_greed < 85)     # 극단적 탐욕(꼭지)엔 안 달림
        and (funding is None or funding < 0.0015)       # 롱 과열(레버리지 쏠림) 아님
        and (news_score is None or news_score > -20)
    )
    if aggressive:
        return Stance("적극",
                      f"XRP 상승추세+시장 우호 → 공격적 진입 [{fg_txt} · {fund_txt}]",
                      "적극", inp)

    # ── ③ 소극: 그 외(횡보·불확실) ─────────────────────────
    return Stance("소극",
                  f"방향 불분명/혼조 — 검증조건으로만 조심 진입 [{fg_txt} · {fund_txt}]",
                  "소극", inp)
