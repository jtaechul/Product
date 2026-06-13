"""자산배분 + 봇 간 충돌방지 (여러 봇이 한 업비트 계좌를 안전하게 공유).

세 봇(대형코인/잠수함/고위험)이 같은 계좌의 KRW·코인을 쓰므로, 조정 장치가 없으면
현금을 중복 사용하거나 같은 코인을 서로 사고팔며 엉킨다. 이 모듈이 둘을 막는다:

1) 예산 상한(budget): 월/분기 리밸런싱(scripts/rebalance.py)이 전체 자산을 평가해
   .botstate/allocation.json 에 목표비중(기본 대형50/잠수30/고위험20)과 총자산을 기록.
   각 봇은 budget_for(name) 로 '자기 몫'만 받아 그 한도 안에서만 매수 → 충돌·초과 방지.
   (신호가 없으면 안 쓰므로, 나쁜 장에선 자연히 현금이 쌓임 = 유연한 현금 보유)

2) 코인 소유권(owned): 각 봇이 보유 코인을 .botstate/owned_<name>.txt 에 게시.
   스캐너는 '다른 봇이 가진 코인'을 제외 → 같은 코인 중복매수/교차매도 방지.

allocation.json 이 없으면 budget_for 는 fallback(각 봇의 기존 --invest)을 돌려줘
기존 동작을 그대로 유지한다(안전한 점진 도입).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

_STATE = Path(__file__).resolve().parent.parent / ".botstate"
_ALLOC = _STATE / "allocation.json"

# 목표 비중 (합 1.0 = 풀투자 지향. 신호 없으면 현금으로 남아 자연히 방어적). 조정 가능.
DEFAULT_WEIGHTS = {"majors": 0.5, "swing": 0.3, "highrisk": 0.2}


def _dir() -> Path:
    _STATE.mkdir(exist_ok=True)
    return _STATE


# ----------------------------- 예산(배분) -----------------------------
def load_allocation() -> dict | None:
    try:
        return json.loads(_ALLOC.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_allocation(total_krw: float, weights: dict | None = None) -> dict:
    weights = weights or DEFAULT_WEIGHTS
    data = {"total": float(total_krw), "weights": weights, "updated": time.time()}
    _dir()
    _ALLOC.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def budget_for(name: str, fallback: float) -> float:
    """이 봇에 배정된 투자 예산(KRW). allocation.json 있으면 총자산×비중, 없으면 fallback."""
    a = load_allocation()
    try:
        if a and a.get("total", 0) > 0 and name in a.get("weights", {}):
            return float(a["total"]) * float(a["weights"][name])
    except Exception:
        pass
    return float(fallback)


def current_weights() -> dict:
    """현재 적용 중인 목표 비중(없으면 기본값)."""
    a = load_allocation()
    if a and isinstance(a.get("weights"), dict):
        return dict(a["weights"])
    return dict(DEFAULT_WEIGHTS)


def set_weights(weights: dict) -> None:
    """목표 비중 갱신(총자산은 유지). 승인된 국면 조정을 반영할 때 사용."""
    a = load_allocation() or {"total": 0.0, "weights": dict(DEFAULT_WEIGHTS)}
    a["weights"] = {k: float(v) for k, v in weights.items()}
    a["updated"] = time.time()
    _dir()
    _ALLOC.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------- 비중조정 제안(승인 대기) -----------------------------
_PENDING = _STATE / "pending_weights.json"


def write_pending(proposal: dict) -> None:
    """국면 분석이 만든 '승인 대기' 비중 제안을 저장(텔레그램 버튼이 참조)."""
    _dir()
    _PENDING.write_text(json.dumps(proposal, ensure_ascii=False), encoding="utf-8")


def read_pending() -> dict | None:
    try:
        return json.loads(_PENDING.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_pending() -> None:
    try:
        _PENDING.unlink()
    except Exception:
        pass


# ----------------------------- 코인 소유권 -----------------------------
def publish_owned(name: str, markets) -> None:
    """이 봇이 현재 보유한 코인 목록을 게시(다른 봇이 피하도록)."""
    try:
        (_dir() / f"owned_{name}.txt").write_text(
            "\n".join(sorted(markets)), encoding="utf-8")
    except Exception:
        pass


def owned_by_others(name: str) -> set[str]:
    """나 이외의 봇들이 보유 중인 코인 집합(스캐너에서 제외용). 오래된(>1일) 파일은 무시."""
    out: set[str] = set()
    try:
        for f in _dir().glob("owned_*.txt"):
            if f.stem == f"owned_{name}":
                continue
            if time.time() - f.stat().st_mtime > 86400:
                continue
            for line in f.read_text(encoding="utf-8").splitlines():
                m = line.strip()
                if m:
                    out.add(m)
    except Exception:
        pass
    return out
