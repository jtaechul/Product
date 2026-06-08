"""환경변수/설정 로딩.

API 키는 코드에 하드코딩하지 않고 .env 파일 또는 환경변수에서 읽습니다.
python-dotenv 가 설치되어 있으면 .env 를 자동 로딩하고, 없으면 OS 환경변수만 사용합니다.
"""

from __future__ import annotations

import os
from pathlib import Path

# .env 자동 로딩 (python-dotenv 가 있을 때만). 시세 조회 단계에서는 없어도 됩니다.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# Upbit REST API 기본 주소
UPBIT_API_BASE = "https://api.upbit.com/v1"

# 거래(주문) 단계에서 사용할 키. 시세 조회만 한다면 비어 있어도 무방합니다.
UPBIT_ACCESS_KEY = os.getenv("UPBIT_ACCESS_KEY", "")
UPBIT_SECRET_KEY = os.getenv("UPBIT_SECRET_KEY", "")


def has_api_keys() -> bool:
    """실거래 API 호출에 필요한 키가 모두 설정되어 있는지 여부."""
    return bool(UPBIT_ACCESS_KEY and UPBIT_SECRET_KEY)
