"""Upbit 거래(Exchange) API 클라이언트 — JWT 인증 필요.

잔고조회(/v1/accounts) 등 인증이 필요한 엔드포인트를 호출합니다.
Access Key / Secret Key 는 .env(또는 환경변수)에서 로딩하며 코드에 하드코딩하지 않습니다.

인증 방식 (Upbit 공식):
  - payload = {access_key, nonce}                 (파라미터 없는 요청)
  - 파라미터가 있으면 query_hash(SHA512) + query_hash_alg 추가
  - secret_key 로 HS256 서명한 JWT 를 "Authorization: Bearer <jwt>" 헤더로 전송
공식 문서: https://docs.upbit.com/kr/docs/create-authorization-request
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from urllib.parse import urlencode

import jwt
import requests

from .config import UPBIT_ACCESS_KEY, UPBIT_API_BASE, UPBIT_SECRET_KEY


class MissingApiKeyError(RuntimeError):
    """API 키가 설정되지 않았을 때 발생."""


class UpbitExchange:
    """Upbit 거래 API 클라이언트 (JWT 인증)."""

    def __init__(
        self,
        access_key: str = UPBIT_ACCESS_KEY,
        secret_key: str = UPBIT_SECRET_KEY,
        base_url: str = UPBIT_API_BASE,
        timeout: float = 10.0,
    ):
        if not access_key or not secret_key:
            raise MissingApiKeyError(
                "UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY 가 설정되지 않았습니다. "
                ".env 파일에 키를 넣어주세요 (.env.example 참고)."
            )
        self.access_key = access_key
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _auth_header(self, params: dict[str, Any] | None = None) -> dict[str, str]:
        """요청 파라미터에 맞는 Authorization 헤더 생성."""
        payload: dict[str, Any] = {
            "access_key": self.access_key,
            "nonce": str(uuid.uuid4()),
        }
        if params:
            query_string = urlencode(params)
            query_hash = hashlib.sha512(query_string.encode()).hexdigest()
            payload["query_hash"] = query_hash
            payload["query_hash_alg"] = "SHA512"

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        headers = self._auth_header(params)
        resp = self.session.get(
            f"{self.base_url}{path}",
            params=params,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    # --- 잔고조회 ---------------------------------------------------------
    def get_accounts(self) -> list[dict[str, Any]]:
        """보유 자산 목록.

        각 항목: currency, balance(주문가능), locked(주문중), avg_buy_price(평단가),
                 avg_buy_price_modified, unit_currency(기준 화폐, 보통 KRW)
        """
        return self._get("/accounts")

    def get_krw_balance(self) -> float:
        """보유 원화(KRW) 잔고."""
        for acc in self.get_accounts():
            if acc["currency"] == "KRW":
                return float(acc["balance"])
        return 0.0
