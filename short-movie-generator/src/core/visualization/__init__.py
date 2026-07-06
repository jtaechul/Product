"""시각화 패키지 — 구현체 선택은 여기서만 (상·하류는 base 계약만 의존)."""
from __future__ import annotations

from src.core.visualization.base import VisualizationError, Visualizer


def get_visualizer(name: str) -> Visualizer:
    if name == "panzoom":
        from src.core.visualization.panzoom import PanzoomVisualizer

        return PanzoomVisualizer()
    if name == "veo_img2video":
        from src.core.visualization.veo_img2video import VeoImg2VideoVisualizer

        return VeoImg2VideoVisualizer()
    if name == "veo_text2video":  # 확정 경로(기포 무발생): image2text → text2video
        from src.core.visualization.veo_text2video import VeoText2VideoVisualizer

        return VeoText2VideoVisualizer()
    raise VisualizationError(
        f"알 수 없는 시각화 구현체: {name} (panzoom | veo_img2video | veo_text2video)"
    )
