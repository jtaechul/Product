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
from pathlib import Path

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


def send_buttons(text: str, buttons: list[list[tuple[str, str]]]) -> bool:
    """인라인 버튼이 달린 메시지 전송. buttons=[[(라벨, callback_data), ...], ...]."""
    token, chat = _creds()
    if not (token and chat):
        return False
    try:
        markup = {"inline_keyboard": [[{"text": l, "callback_data": d}
                                       for l, d in row] for row in buttons]}
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text, "parse_mode": "HTML",
             "reply_markup": json.dumps(markup)}
        ).encode()
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def send_document(path: str, caption: str = "") -> bool:
    """파일(예: HTML 대시보드)을 텔레그램 문서로 전송 (multipart/form-data)."""
    token, chat = _creds()
    if not (token and chat):
        return False
    try:
        with open(path, "rb") as f:
            content = f.read()
        fname = os.path.basename(path)
        boundary = "----botform" + str(int(time.time()))
        parts = []
        for key, val in (("chat_id", chat), ("caption", caption)):
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{key}"\r\n\r\n{val}\r\n')
        head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; "
                f'filename="{fname}"\r\nContent-Type: text/html\r\n\r\n')
        body = ("".join(parts) + head).encode() + content + f"\r\n--{boundary}--\r\n".encode()
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def _answer_callback(token: str, cq_id: str) -> None:
    """텔레그램 콜백(버튼 탭) 응답 — 버튼 로딩 표시 해제."""
    try:
        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        data = urllib.parse.urlencode({"callback_query_id": cq_id}).encode()
        urllib.request.urlopen(url, data=data, timeout=10)
    except Exception:
        pass


def _handle_weight_callback(data: str) -> None:
    """비중조정 승인/거절 버튼 처리 → 승인 시 목표비중 적용."""
    from . import allocation  # 지연 임포트(순환 방지)
    if data.startswith("approve_weights"):
        prop = allocation.read_pending()
        if prop and prop.get("weights"):
            allocation.set_weights(prop["weights"])
            allocation.clear_pending()
            w = prop["weights"]
            cash = max(0.0, 1.0 - sum(w.values()))
            send(f"✅ <b>비중 조정 승인됨</b>\n"
                 f"대형 {w.get('majors',0)*100:.0f}% / 잠수 {w.get('swing',0)*100:.0f}% / "
                 f"현금 {cash*100:.0f}%\n"
                 f"봇들이 다음 점검부터 이 비중으로 운용합니다.")
        else:
            send("⚠️ 적용할 제안이 없어요(이미 처리됨).")
    elif data.startswith("reject_weights"):
        allocation.clear_pending()
        send("❌ 비중 조정 제안을 거절했어요. 기존 비중을 유지합니다.")


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


# ─────────────────────────────────────────────────────────────────────────
# 여러 봇(잠수함 + 대형코인)을 '한 텔레그램 채팅'에서 함께 다루기.
#
# 문제: 봇 프로세스마다 따로 getUpdates 를 폴링하면, '상태' 메시지를 서로 가로채
#       번갈아 답한다. 또 하트비트도 봇마다 따로 온다.
# 해결: ① 각 봇은 자기 상태를 공유 파일(.botstate/status_<name>.txt)에 주기적으로 기록.
#       ② 오직 '한 프로세스'만(락으로 선출) 텔레그램을 폴링하고, 모든 상태파일을 합쳐서
#          한 번에 답한다. 하트비트도 그 한 프로세스가 합쳐서 보낸다.
# 이렇게 하면 '상태' 한 번에 두 봇 정보가 모두 나온다. (매매 알림은 각 봇이 따로 보냄)
# ─────────────────────────────────────────────────────────────────────────

_STATE_DIR = Path(__file__).resolve().parent.parent / ".botstate"

# 텔레그램 합산 상태/하트비트에 포함할 봇 이름 집합. 비어 있으면 전부 표시.
# 잠수함봇은 검증 실패로 운용 중단 → 현황 알림에서 영구 제외(대형코인만 표시).
_STATUS_WHITELIST: set[str] = {"2_대형코인"}


def _state_dir() -> Path:
    _STATE_DIR.mkdir(exist_ok=True)
    return _STATE_DIR


def publish_status(name: str, text: str) -> None:
    """이 봇의 현재 상태를 공유 파일에 기록(다른 봇/리스너가 합쳐 읽음)."""
    try:
        (_state_dir() / f"status_{name}.txt").write_text(text, encoding="utf-8")
    except Exception:
        pass


def status_allowed(bot_name: str) -> bool:
    """이 봇이 텔레그램 합산 현황에 표시돼도 되는지(화이트리스트 통과 여부).

    화이트리스트가 비어 있으면 전부 허용. 비어 있지 않으면 그 안에 든 봇만 허용.
    notifier 의 합산 현황과 portfolio_review 대시보드가 '같은 규칙'을 쓰도록 공용화.
    """
    return not (_STATUS_WHITELIST and bot_name not in _STATUS_WHITELIST)


def _read_all_statuses() -> str:
    """모든 봇의 상태파일을 합쳐 하나의 메시지로. 오래된(>10분) 건 경고 표시."""
    parts = []
    try:
        for f in sorted(_state_dir().glob("status_*.txt")):
            try:
                bot_name = f.stem[len("status_"):]
                if not status_allowed(bot_name):
                    continue
                txt = f.read_text(encoding="utf-8").strip()
                if not txt:
                    continue
                age = time.time() - f.stat().st_mtime
                if age > 600:
                    txt += (f"\n<i>(이 봇 상태가 {int(age // 60)}분째 갱신 안 됨 — "
                            f"점검 필요)</i>")
                parts.append(txt)
            except Exception:
                pass
    except Exception:
        pass
    return "\n\n──────────\n\n".join(parts) if parts else "상태 정보 없음"


def _own_listener(ttl: int = 90) -> bool:
    """단일 폴러 선출 락. 내가 소유(또는 갱신)하면 True. 소유자 죽으면 ttl 후 인계."""
    lock = _state_dir() / "listener.lock"
    try:
        if lock.exists() and (time.time() - lock.stat().st_mtime) < ttl:
            owner = ""
            try:
                owner = lock.read_text().strip()
            except Exception:
                pass
            if owner == str(os.getpid()):
                lock.touch()      # 내 소유 → 갱신
                return True
            return False          # 다른 프로세스가 살아있는 소유자
        lock.write_text(str(os.getpid()))   # 비었거나 만료 → 내가 차지
        return True
    except Exception:
        return True


def run_shared(name: str, get_status, stop: threading.Event | None = None,
               heartbeat_sec: int = 3600, publish_sec: int = 30) -> None:
    """이 봇을 '공유 상태' 체제로 운영(여러 봇이 한 채팅을 공유).

    · publish_sec 마다 get_status() 를 공유파일에 기록
    · 락을 가진 한 프로세스만 텔레그램을 폴링 → 어떤 메시지든 '모든 봇 상태'를 합쳐 회신
      + heartbeat_sec 마다 합친 하트비트 전송
    미설정(토큰 없음)이면 아무 것도 하지 않음.
    """
    if not enabled():
        return

    def publisher():
        while not (stop and stop.is_set()):
            try:
                publish_status(name, get_status())
            except Exception:
                pass
            stop.wait(publish_sec) if stop else time.sleep(publish_sec)

    def listener():
        global _offset
        last_hb = time.time()   # 시작 직후 하트비트 폭주 방지(다음 주기부터)
        while not (stop and stop.is_set()):
            if not _own_listener():
                time.sleep(10)
                continue
            token, chat = _creds()
            try:
                if time.time() - last_hb >= heartbeat_sec:
                    send(f"💓 <b>하트비트</b> {now_kst():%m-%d %H:%M}\n"
                         f"{_read_all_statuses()}")
                    last_hb = time.time()
                params: dict = {"timeout": 25}
                if _offset is not None:
                    params["offset"] = _offset
                url = (f"https://api.telegram.org/bot{token}/getUpdates?"
                       + urllib.parse.urlencode(params))
                with urllib.request.urlopen(url, timeout=30) as r:
                    updates = json.loads(r.read()).get("result", [])
                for upd in updates:
                    _offset = upd["update_id"] + 1
                    # 인라인 버튼 탭(비중조정 승인/거절) 처리
                    cq = upd.get("callback_query")
                    if cq:
                        if str(cq.get("from", {}).get("id", "")) == str(chat):
                            try:
                                _handle_weight_callback(cq.get("data", ""))
                            except Exception:
                                pass
                        _answer_callback(token, cq.get("id", ""))
                        continue
                    msg = upd.get("message", {})
                    text = (msg.get("text") or "").strip()
                    frm = str(msg.get("chat", {}).get("id", ""))
                    if not text or frm != str(chat):
                        continue
                    send(f"📟 <b>요청 응답</b> {now_kst():%m-%d %H:%M}\n"
                         f"{_read_all_statuses()}")
            except Exception:
                time.sleep(5)

    threading.Thread(target=publisher, daemon=True).start()
    threading.Thread(target=listener, daemon=True).start()
