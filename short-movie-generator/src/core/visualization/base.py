"""시각화 인터페이스 계약 (spec 3장) — 구현체 교체 가능, 상·하류는 이 계약만 의존.

계약: "승인 이미지 1장 + 상황/컷 지정 → 9:16 영상 클립 1개"
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.contracts import ApprovedAsset, ClipResult, CutSpec

# 영상 규격 (CLAUDE.md)
CLIP_W, CLIP_H = 720, 1280       # 9:16 720p
CLIP_DURATION_S = 8
CLIP_FPS = 25


class VisualizationError(RuntimeError):
    pass


class Visualizer(ABC):
    """구현체(plugin): veo_img2video(채택) / panzoom(fallback) / 향후 타 모델."""

    name: str = ""

    @abstractmethod
    def generate_clip(
        self,
        asset: ApprovedAsset,
        cut: CutSpec,
        situation_id: str,
        style_profile: str,
        out_dir: str,
    ) -> ClipResult:
        """승인 이미지 1장 + 컷 지정 → 9:16 클립 1개 (계약 고정)."""
