"""Phase 3 — 텔레그램 알림 (실패 알림 + 성공 요약, 스펙 §8 Phase 3).

시크릿: SHORTS_TELEGRAM_BOT_TOKEN/SHORTS_TELEGRAM_CHAT_ID 우선,
없으면 저장소 공용 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 재사용.
미등록이면 조용히 no-op (파이프라인을 막지 않는다).
"""

from __future__ import annotations

import os


def send(text: str) -> bool:
    token = (os.environ.get("SHORTS_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("SHORTS_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    if not token or not chat:
        return False
    try:
        import requests
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4000], "disable_web_page_preview": True},
            timeout=20,
        )
        return r.ok
    except Exception as e:
        print(f"[notify] 텔레그램 발송 실패(무시): {e}")
        return False
