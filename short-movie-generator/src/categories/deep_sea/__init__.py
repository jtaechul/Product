"""deep_sea 카테고리 — 임포트 시 레지스트리에 자동 등록."""
from src.categories.deep_sea.module import DeepSeaCategory
from src.registry import register

register(DeepSeaCategory())
