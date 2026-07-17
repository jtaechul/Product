"""Phase 3 — 텔레그램 알림 (실패 알림 + 성공 요약, 스펙 §8 Phase 3).

시크릿: SHORTS_TELEGRAM_BOT_TOKEN/SHORTS_TELEGRAM_CHAT_ID 우선,
없으면 저장소 공용 TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID 재사용.
미등록이면 조용히 no-op (파이프라인을 막지 않는다).
"""

from __future__ import annotations

import os


def _creds() -> tuple[str, str]:
    token = (os.environ.get("SHORTS_TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.environ.get("SHORTS_TELEGRAM_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    return token, chat


def send(text: str) -> bool:
    token, chat = _creds()
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


def send_audio(path, caption: str = "", title: str = "") -> bool:
    """오디오 파일을 텔레그램으로 전송(sendAudio) — 보이스 샘플 청취용. 미등록/실패 시 조용히 False."""
    from pathlib import Path
    token, chat = _creds()
    p = Path(path)
    if not token or not chat or not p.exists():
        return False
    try:
        import requests
        with open(p, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendAudio",
                data={"chat_id": chat, "caption": caption[:1024], "title": title or p.stem},
                files={"audio": (p.name, f, "audio/mpeg")},
                timeout=120,
            )
        if not r.ok:
            print(f"[notify] sendAudio 실패({r.status_code}): {r.text[:200]}")
        return r.ok
    except Exception as e:
        print(f"[notify] 오디오 발송 실패(무시): {e}")
        return False
