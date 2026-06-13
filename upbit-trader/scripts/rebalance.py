#!/usr/bin/env python3
"""자산 리밸런싱 — 전체 자산을 평가해 세 봇의 '예산 비중'을 갱신(월/분기 실행).

통상적 방법론(전략적 자산배분 + 정기 리밸런싱)을 적용: 매 실행 시 전체 평가자산
(원화 + 보유코인 평가액)을 계산해, 목표비중(대형50/잠수30/고위험20)으로 각 봇의
'예산 상한'을 .botstate/allocation.json 에 기록한다. 봇들은 이 예산 안에서만 매수하므로
시간이 지나며 자연스럽게 목표비중으로 수렴한다(강제 청산 없이 안전하게).

신호가 없으면 봇이 예산을 안 쓰고 현금으로 두므로, 나쁜 장에선 자동으로 방어적이 된다.

systemd timer(rebalance.timer)로 매월 1일 실행. 수동: python -m scripts.rebalance
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import allocation, notifier  # noqa: E402
from src.upbit_quotation import UpbitQuotation  # noqa: E402


def total_equity() -> float | None:
    """원화 + 모든 보유코인 평가액 합계(KRW). 키 없으면 None."""
    try:
        from src.upbit_exchange import MissingApiKeyError, UpbitExchange
        ex = UpbitExchange()
    except Exception:
        return None
    q = UpbitQuotation()
    total = 0.0
    holdings = []
    for acc in ex.get_accounts():
        cur = acc.get("currency", "")
        if acc.get("unit_currency", "KRW") != "KRW":
            continue
        vol = float(acc.get("balance", 0) or 0) + float(acc.get("locked", 0) or 0)
        if cur == "KRW":
            total += vol
        elif vol > 0:
            holdings.append((f"KRW-{cur}", vol))
    if holdings:
        try:
            prices = {t["market"]: float(t["trade_price"])
                      for t in q.get_ticker([m for m, _ in holdings])}
        except Exception:
            prices = {}
        for m, vol in holdings:
            total += vol * prices.get(m, 0.0)
    return total


def main() -> None:
    total = total_equity()
    if total is None:
        print("API 키 없음 — 리밸런싱 건너뜀(모의 단계에서는 정상)")
        return
    # 비중은 '현재 적용 중'인 값을 유지(국면 제안 승인으로 바뀐 비중을 덮어쓰지 않음).
    # 총 평가자산만 갱신 → 각 봇 예산이 자산 변화에 맞춰 재계산됨.
    w = allocation.current_weights()
    allocation.write_allocation(total, w)
    lines = [f"⚖️ <b>자산 리밸런싱 완료</b>",
             f"총 평가자산: <b>{total:,.0f}원</b>",
             f"• 대형코인 {w['majors']*100:.0f}% → {total*w['majors']:,.0f}원",
             f"• 잠수함 {w['swing']*100:.0f}% → {total*w['swing']:,.0f}원",
             f"• 고위험 {w['highrisk']*100:.0f}% → {total*w['highrisk']:,.0f}원",
             "각 봇은 이 한도 안에서만 매수합니다(나쁜 장에선 현금 보유)."]
    msg = "\n".join(lines)
    print(msg.replace("<b>", "").replace("</b>", ""))
    notifier.send(msg)


if __name__ == "__main__":
    main()
