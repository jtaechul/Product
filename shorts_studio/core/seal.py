"""seal — 관리자 페이지가 봉해 보낸 개인 API 키를 연다.

왜 봉해서 보내는가: 실제 작업은 GitHub Actions 에서 돌아가는데 이 저장소는 **공개**라,
워크플로 입력값이 실행 기록 화면에 그대로 보인다. 사용자의 API 키를 날것으로 넘기면
전 세계에 공개된다. 그래서 워커가 AES-GCM 으로 잠가 보내고, 같은 열쇠(KEY_SECRET)를
가진 이쪽에서만 연다. 기록에는 알아볼 수 없는 문자열만 남는다.

열쇠는 양쪽이 같은 문자열을 SHA-256 으로 눌러 만든다(워커 sealKey 와 짝).
봉투 = base64( 12바이트 IV + 암호문 ).
"""
from __future__ import annotations

import base64
import hashlib
import os


class SealError(RuntimeError):
    pass


def unseal(blob_b64: str, secret: str) -> str:
    """봉투를 열어 원래 키 문자열을 돌려준다. 빈 봉투는 빈 문자열."""
    blob_b64 = (blob_b64 or "").strip()
    if not blob_b64:
        return ""
    if not secret:
        raise SealError("열쇠(KEY_SECRET)가 없어 개인 API 키를 열 수 없습니다.")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:  # noqa: BLE001
        raise SealError("cryptography 패키지가 필요합니다 (pip install cryptography).") from e
    try:
        blob = base64.b64decode(blob_b64)
        key = hashlib.sha256(secret.encode("utf-8")).digest()
        return AESGCM(key).decrypt(blob[:12], blob[12:], None).decode("utf-8")
    except Exception as e:  # noqa: BLE001
        raise SealError(
            "개인 API 키를 열지 못했습니다. 관리자 페이지와 Actions 의 열쇠 값"
            "(MOVIEGEN_KEY_SECRET)이 다를 수 있습니다."
        ) from e


def gemini_key() -> str:
    """이번 작업에 쓸 Gemini 키를 고른다.

    ① 관리자 페이지가 봉해 보낸 사용자 개인 키가 있으면 그것,
    ② 없으면 저장소 시크릿 GEMINI_API_KEY(운영자 본인 키).
    로그에 새어 나가지 않게 Actions 에 가림(mask) 처리를 요청한다.
    """
    sealed = os.environ.get("GEMINI_KEY_ENC", "").strip()
    if sealed:
        key = unseal(sealed, os.environ.get("KEY_SECRET", "").strip())
        if key:
            # 혹시라도 다른 단계가 이 값을 출력해도 깃허브가 ***로 가려 준다.
            print(f"::add-mask::{key}")
            print("개인 API 키를 사용합니다.")
            return key
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        print("저장소 기본 API 키를 사용합니다.")
    return key
