"""텔레그램 알림 + 하트비트 (선택 기능).

클라우드(무료 VM)에서 봇을 24시간 돌릴 때, 매매/오류를 휴대폰으로 받고
'봇이 살아있는지'를 주기적으로 확인하기 위한 경량 알림 모듈입니다.

설정(.env):
    TELEGRAM_BOT_TOKEN=123456:ABC...      # @BotFather 로 봇 생성 후 토큰
    TELEGRAM_CHAT_ID=123456789            # @userinfobot 에게 받은 내 chat id

토큰이 없으면 모든 함수는 조용히 no-op — 봇 동작에 영향을 주지 않습니다.
외부 의존성 없이 표준 라이브러리(urllib)만 사용합니다.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def enabled() -> bool:
    return bool(_TOKEN and _CHAT)


def send(text: str) -> bool:
    """텔레그램 메시지 전송. 미설정/실패해도 예외를 던지지 않음(봇 보호)."""
    if not enabled():
        return False
    try:
        url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": _CHAT, "text": text, "parse_mode": "HTML"}
        ).encode()
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def start_heartbeat(get_status, interval_sec: int = 3600,
                    stop: threading.Event | None = None) -> threading.Thread | None:
    """interval_sec 마다 get_status() 문자열을 텔레그램으로 보내는 데몬 스레드.

    이 신호가 끊기면 = 봇/서버가 죽은 것. 미설정 시 None 반환(아무 일도 안 함).
    """
    if not enabled():
        return None

    def loop():
        while not (stop and stop.is_set()):
            try:
                send(f"💓 <b>하트비트</b> {datetime.now():%m-%d %H:%M}\n{get_status()}")
            except Exception:
                pass
            if stop:
                stop.wait(interval_sec)
            else:
                time.sleep(interval_sec)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    return th
