"""소싱 어댑터 인터페이스 + 레지스트리 (SSOT §6.2).

플랫폼별(틱톡·유튜브·인스타)·모드별(자동/반자동) 수집을 어댑터로 분리한다 —
"틱톡 공식 검색 API 부재 → 차단·구조 변경 대비"(§6.2)라 소싱 로직을 한곳에 묶지 않고
어댑터를 갈아끼울 수 있게 한다. 한 어댑터가 막혀도 다른 어댑터/반자동으로 폴백.

계약:
- search(seed) → list[SourceVideo]  (메타만; status='discovered', 다운로드는 별도)
- download(sv, dest_dir) → Path|None (원본 확보; 성공 시 sv.downloaded_path·status 갱신)
네트워크·yt-dlp 실패는 예외를 삼키고 [] / None + 로그로 처리(파이프라인 중단 금지).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from src.sourcing.models import SourceVideo

# 운영자 시드(§6.3) — 반자동 수집의 입력. kind로 해석 방식이 갈린다.
SEED_KINDS = ("url", "hashtag", "creator", "keyword")


@dataclass
class Seed:
    kind: str          # url | hashtag | creator | keyword
    value: str
    platform: str = "" # 비면 어댑터가 판단(예: URL에서 도메인 추론)

    def __post_init__(self):
        if self.kind not in SEED_KINDS:
            raise ValueError(f"seed kind 오류: {self.kind} (가능: {SEED_KINDS})")


class SourceAdapter(ABC):
    name: str = "base"
    mode: str = "manual"   # auto | manual (§6)

    @abstractmethod
    def search(self, seed: Seed, limit: int = 10) -> list:
        """시드로 후보 영상 메타를 수집. 실패 시 [] (예외 삼킴)."""
        raise NotImplementedError

    @abstractmethod
    def download(self, sv: SourceVideo, dest_dir: Path) -> Path | None:
        """원본 영상을 dest_dir에 내려받아 경로 반환. 실패 시 None."""
        raise NotImplementedError


# ── 레지스트리 ──────────────────────────────────────────────────────────────
_ADAPTERS: dict = {}


def register(cls):
    """@register 데코레이터 — 어댑터 클래스를 이름으로 등록."""
    inst = cls() if isinstance(cls, type) else cls
    _ADAPTERS[inst.name] = inst
    return cls


def get_adapter(name: str) -> SourceAdapter | None:
    return _ADAPTERS.get(name)


def available() -> list:
    """등록된 어댑터 이름 목록."""
    return sorted(_ADAPTERS.keys())
