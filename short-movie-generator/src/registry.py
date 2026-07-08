"""카테고리 레지스트리 — 카테고리는 플러그인처럼 등록하고 category_id로 로드한다.

새 카테고리 추가 = CategoryModule 구현 1개 작성 + register() 1줄 (코어 재건축 불필요).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.contracts import CaptionData, RawAsset, Situation, SpeciesInfo


class CategoryModule(ABC):
    """카테고리 모듈 계약 (CLAUDE.md '새 카테고리 체크리스트'와 1:1 대응).

    코어 파이프라인은 이 인터페이스만 안다.
    """

    category_id: str = ""
    style_profile: str = ""

    @abstractmethod
    def parse_input(self, query: str) -> str:
        """사용자 입력 → 정규화된 대상 질의 (예: 종명)."""

    @abstractmethod
    def get_info(self, subject_query: str) -> SpeciesInfo:
        """대상 정보 조회 (사실 데이터 → 재작성용)."""

    @abstractmethod
    def source_assets(self, info: SpeciesInfo, raw_dir: str) -> list[RawAsset]:
        """소재 소싱 → assets/raw 에 저장 + 라이선스 메타 반환."""

    @abstractmethod
    def get_situation(self, info: SpeciesInfo) -> Situation:
        """상황/컷 뱅크 → 3컷 프롬프트 + 정확성 플래그."""

    @abstractmethod
    def validate_cuts(self, situation: Situation) -> list[str]:
        """카테고리 고유 정확성/윤리 규칙 위반 목록 반환 (빈 리스트 = 통과)."""

    @abstractmethod
    def build_caption(self, info: SpeciesInfo) -> CaptionData:
        """훅·캡션·해시태그 (카테고리 톤 규칙 적용)."""

    @abstractmethod
    def ambient_audio_spec(self) -> dict:
        """앰비언트 오디오 사양 (코어 audio 모듈에 전달)."""

    def grade_filter(self) -> str | None:
        """(선택) 합성 후 영상에 적용할 FFmpeg 그레이딩 필터 체인.

        텍스트 오버레이 '전'에 적용된다(텍스트는 선명 유지).
        None이면 그레이딩 생략. 카테고리가 룩 질감을 소유한다.
        """
        return None


_REGISTRY: dict[str, CategoryModule] = {}


def register(module: CategoryModule) -> None:
    if not module.category_id:
        raise ValueError("category_id가 비어 있음")
    _REGISTRY[module.category_id] = module


def get_category(category_id: str) -> CategoryModule:
    if category_id not in _REGISTRY:
        # 지연 로드: 알려진 카테고리는 임포트가 곧 등록
        if category_id == "deep_sea":
            import src.categories.deep_sea  # noqa: F401  (임포트 시 register 호출)
        elif category_id == "marine_algae":
            import src.categories.marine_algae  # noqa: F401
        elif category_id == "marine_life":
            import src.categories.marine_life  # noqa: F401
        elif category_id == "shipwreck":
            import src.categories.shipwreck  # noqa: F401
        if category_id not in _REGISTRY:
            raise KeyError(f"미등록 카테고리: {category_id} (등록됨: {list(_REGISTRY)})")
    return _REGISTRY[category_id]


def list_categories() -> list[str]:
    return sorted(_REGISTRY)
