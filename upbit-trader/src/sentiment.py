"""시장 심리 지표 수집 — 공포탐욕지수 + 펀딩비 (외부 무료 API).

'시기 반응형' 국면 판단(regime6h)의 입력. 모든 함수는 실패 시 None 을 돌려
봇이 심리지표 없이도 정상 작동하도록 한다(fail-safe). 표준 라이브러리만 사용.

출처:
  · 공포탐욕지수: alternative.me (Crypto Fear & Greed, 0=극공포 ~ 100=극탐욕)
  · 펀딩비: OKX 무기한선물 (바이낸스/Bybit는 지역차단 451/403 → OKX 사용)
             양수 클수록 롱 과열(레버리지 쏠림), 음수는 숏 우위/공포.
"""

from __future__ import annotations

import json
import urllib.request

_FNG_URL = "https://api.alternative.me/fng/?limit=1"
_OKX_FUNDING = "https://www.okx.com/api/v5/public/funding-rate?instId=XRP-USDT-SWAP"


def _get(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fear_greed() -> int | None:
    """공포탐욕지수 0~100 (0=극공포, 100=극탐욕). 실패 시 None."""
    try:
        d = _get(_FNG_URL)
        return int(d["data"][0]["value"])
    except Exception:
        return None


def funding_rate() -> float | None:
    """XRP 무기한선물 펀딩비(예: 0.0001). 실패 시 None."""
    try:
        d = _get(_OKX_FUNDING)
        return float(d["data"][0]["fundingRate"])
    except Exception:
        return None


def snapshot() -> dict:
    """현재 심리 스냅샷 {fear_greed, funding}. 각 항목 실패 시 None."""
    return {"fear_greed": fear_greed(), "funding": funding_rate()}
