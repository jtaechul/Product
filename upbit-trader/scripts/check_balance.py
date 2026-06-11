#!/usr/bin/env python3
"""잔고조회 CLI — 보유 자산을 표로 출력합니다.

사용법:
    python scripts/check_balance.py

사전 준비:
    1) cp .env.example .env
    2) .env 에 UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 입력
    3) Upbit Open API 관리에서 '자산 조회' 권한 + 현재 IP 허용 등록

이 스크립트는 읽기 전용(잔고조회)만 수행하며, 주문/출금은 하지 않습니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from src.upbit_exchange import MissingApiKeyError, UpbitExchange  # noqa: E402


def main() -> None:
    try:
        client = UpbitExchange()
        accounts = client.get_accounts()
    except MissingApiKeyError as exc:
        print(f"[설정 필요] {exc}")
        sys.exit(1)
    except requests.exceptions.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        print(f"[오류] Upbit API 가 {code} 를 반환했습니다.")
        if code in (401, 403):
            print("  → 인증 실패. 다음을 확인하세요:")
            print("     · Access/Secret key 가 올바른지")
            print("     · '자산 조회' 권한이 켜져 있는지")
            print("     · 현재 PC의 공인 IP 가 허용 IP 목록에 등록돼 있는지")
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        print(f"[오류] 네트워크 연결 실패: {exc}")
        sys.exit(1)

    if not accounts:
        print("보유 자산이 없습니다.")
        return

    print(f"{'자산':<8}{'보유수량':>20}{'주문중':>16}{'평단가':>16}")
    print("-" * 60)
    for acc in accounts:
        cur = acc["currency"]
        balance = float(acc["balance"])
        locked = float(acc["locked"])
        avg = float(acc["avg_buy_price"])
        avg_str = f"{avg:,.2f}" if cur != "KRW" else "-"
        print(f"{cur:<8}{balance:>20,.8f}{locked:>16,.8f}{avg_str:>16}")


if __name__ == "__main__":
    main()
