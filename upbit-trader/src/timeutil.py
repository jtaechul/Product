"""시간대(타임존) 유틸 — 모든 표시/로그 시각을 한국시간(KST)으로 통일.

클라우드 VM(미국 리전 등)에서 봇을 돌리면 서버 로컬시각이 UTC라서, 텔레그램
상태 메시지·하트비트·로그의 시간이 한국 사용자에게 9시간 어긋나 보입니다.
이 모듈의 now() 는 서버 위치와 무관하게 항상 한국시간(UTC+9)을 돌려줍니다.

핵심: tz 정보가 없는(naive) datetime 으로 반환합니다. 그래서 기존 datetime.now()
를 그대로 대체할 수 있고(aware/naive 혼용 오류 없음), 표시하면 한국시각이 됩니다.
표준 라이브러리만 사용 — 추가 의존성 없음.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))  # 한국 표준시 (UTC+9, 서머타임 없음)


def now_kst() -> datetime:
    """현재 한국시각을 naive datetime 으로 반환 (datetime.now() 드롭인 대체)."""
    return datetime.now(KST).replace(tzinfo=None)
