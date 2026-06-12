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

from .timeutil import now_kst  # 모든 표시 시각을 한국시간(KST)으로 통일

# config 를 먼저 임포트해 .env 를 os.environ 으로 로딩(키를 읽기 전에 보장).
try:
    from . import config  # noqa: F401  (.env 자동 로딩 부수효과)
except Exception:
    pass


def _creds() -> tuple[str, str]:
    """토큰/챗ID 를 '호출 시점'에 읽음 — .env 가 나중에 로딩돼도 안전."""
    return (os.getenv("TELEGRAM_BOT_TOKEN", ""),
            os.getenv("TELEGRAM_CHAT_ID", ""))


def enabled() -> bool:
    token, chat = _creds()
    return bool(token and chat)


def send(text: str) -> bool:
    """텔레그램 메시지 전송. 미설정/실패해도 예외를 던지지 않음(봇 보호)."""
    token, chat = _creds()
    if not (token and chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text, "parse_mode": "HTML"}
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
                send(f"💓 <b>하트비트</b> {now_kst():%m-%d %H:%M}\n{get_status()}")
            except Exception:
                pass
            if stop:
                stop.wait(interval_sec)
            else:
                time.sleep(interval_sec)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    return th


_offset: int | None = None  # 이미 처리한 텔레그램 메시지 위치


def start_command_listener(get_status, stop: threading.Event | None = None
                           ) -> threading.Thread | None:
    """텔레그램에서 내가 보낸 명령(/상태,/status 등)에 즉시 답하는 데몬 스레드.

    내 chat id 가 보낸 메시지만 처리합니다(다른 사람 무시). 어떤 명령이든
    현재 상태(get_status())를 바로 회신 — 사실상 '강제 하트비트' 버튼.
    미설정 시 None.
    """
    if not enabled():
        return None

    def _get_updates(token: str):
        global _offset
        params: dict = {"timeout": 25}  # long-poll 25초
        if _offset is not None:
            params["offset"] = _offset
        url = (f"https://api.telegram.org/bot{token}/getUpdates?"
               + urllib.parse.urlencode(params))
        with urllib.request.urlopen(url, timeout=30) as r:
            return json.loads(r.read()).get("result", [])

    def loop():
        global _offset
        while not (stop and stop.is_set()):
            token, chat = _creds()
            try:
                for upd in _get_updates(token):
                    _offset = upd["update_id"] + 1
                    msg = upd.get("message", {})
                    text = (msg.get("text") or "").strip()
                    frm = str(msg.get("chat", {}).get("id", ""))
                    if not text or frm != str(chat):
                        continue  # 내 채팅이 아니거나 빈 메시지는 무시
                    send(f"📟 <b>요청 응답</b> {now_kst():%m-%d %H:%M}\n"
                         f"{get_status()}")
            except Exception:
                time.sleep(5)  # 오류 시 잠깐 쉬고 재시도

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    return th
