"""veo_text2video 구현체 — 확정 경로(CLAUDE.md): image2text 정밀묘사 → text2video.

img2video는 기포(공기방울) 유발로 폐기됨(검증 로그). text2video는 기포가 없다(사용자 실측 확인).
전략: 승인된 NOAA 사진을 '이미지→텍스트' 비전 모델로 정밀 묘사해 프롬프트에 주입(종 정확도↑),
그 텍스트만으로 Veo가 세로 영상을 생성(text2video). 이미지를 Veo에 직접 넣지 않으므로 기포 무발생.

GEMINI_API_KEY 필요(과금). 키 없으면 명확 에러로 안전 중단 → panzoom fallback.
Veo 3.1 Lite: 8초/컷, 9:16, 하루 10회 쿼터. negative_prompt·generate_audio 미지원.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from src.core.contracts import ApprovedAsset, ClipResult, CutSpec
from src.core.visualization.base import CLIP_DURATION_S, VisualizationError, Visualizer

log = logging.getLogger(__name__)

MODEL = "veo-3.1-lite-generate-preview"
VISION_MODEL = "gemini-2.5-flash"   # image2text (정밀 외형 묘사)
_POLL_INTERVAL_S = 10
_TIMEOUT_S = 15 * 60

_VISION_PROMPT = (
    "You are a marine biologist describing a deep-sea animal for an accurate video prompt. "
    "Look at this photograph and describe ONLY the animal's physical appearance in 2-3 concise "
    "English sentences: body shape, exact colour, texture, fins/arms and their count, eyes, and "
    "proportions. Describe only what is visibly true. Do NOT mention the background, lighting, "
    "camera, bubbles, or any action — appearance only."
)


class VeoText2VideoVisualizer(Visualizer):
    """image2text(비전) → text2video(Veo). 이미지 미입력 → 기포 무발생."""

    name = "veo_text2video"

    def __init__(self, client=None):
        self._client = client
        self._desc_cache: dict[str, str] = {}

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not os.environ.get("GEMINI_API_KEY"):
            raise VisualizationError(
                "GEMINI_API_KEY 없음 → .env 에 키를 채우거나 --visualizer panzoom 사용"
            )
        from google import genai  # 지연 임포트

        self._client = genai.Client()
        return self._client

    def _describe_image(self, client, img_path: Path) -> str:
        """image2text: 승인 사진 → 정밀 외형 묘사(캐시). 실패 시 '' (프롬프트만 사용)."""
        key = str(img_path)
        if key in self._desc_cache:
            return self._desc_cache[key]
        desc = ""
        try:
            from google.genai import types

            resp = client.models.generate_content(
                model=VISION_MODEL,
                contents=[
                    types.Part.from_bytes(data=img_path.read_bytes(), mime_type="image/jpeg"),
                    _VISION_PROMPT,
                ],
            )
            desc = (getattr(resp, "text", "") or "").strip().replace("\n", " ")
        except Exception as e:  # noqa: BLE001 — 비전 실패해도 파이프라인은 진행
            log.warning("image2text 실패(프롬프트만 사용): %s", e)
        self._desc_cache[key] = desc
        return desc

    def _final_prompt(self, cut: CutSpec, vision_desc: str) -> str:
        """컷 프롬프트 앞에 사진 기반 외형 묘사를 주입(종 정확도↑)."""
        if not vision_desc:
            return cut.prompt
        return (f"Reference appearance to match precisely (from a real photograph of this exact "
                f"species): {vision_desc}\n\n{cut.prompt}")

    def generate_clip(
        self,
        asset: ApprovedAsset,
        cut: CutSpec,
        situation_id: str,
        style_profile: str,
        out_dir: str,
    ) -> ClipResult:
        from google.genai import types

        client = self._get_client()
        img_path = Path(asset.asset_path)
        if not img_path.exists():
            raise VisualizationError(f"승인 이미지 없음: {img_path}")

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        clip_path = out / f"{situation_id}_{cut.cut_type}.mp4"

        vision_desc = self._describe_image(client, img_path)
        prompt = self._final_prompt(cut, vision_desc)

        # text2video: 이미지 인자 없음 → Veo가 사진을 세로로 '상상 확장'하지 않음(기포 무발생).
        operation = client.models.generate_videos(
            model=MODEL,
            prompt=prompt,
            config=types.GenerateVideosConfig(
                aspect_ratio="9:16",
                resolution="720p",
                duration_seconds=CLIP_DURATION_S,
                number_of_videos=1,
            ),
        )

        t0 = time.time()
        while not operation.done:
            if time.time() - t0 > _TIMEOUT_S:
                raise VisualizationError(f"Veo 폴링 타임아웃({_TIMEOUT_S}s): {cut.cut_type}")
            time.sleep(_POLL_INTERVAL_S)
            operation = client.operations.get(operation)

        resp = getattr(operation, "response", None) or getattr(operation, "result", None)
        if resp is None or not getattr(resp, "generated_videos", None):
            raise VisualizationError(f"Veo 응답에 영상 없음: {cut.cut_type}")

        video = resp.generated_videos[0].video
        client.files.download(file=video)
        video.save(str(clip_path))
        if not clip_path.exists():
            raise VisualizationError(f"클립 저장 실패: {clip_path}")

        log.info("[veo_text2video] %s 생성(비전묘사 %s)", cut.cut_type,
                 "적용" if vision_desc else "미적용")
        return ClipResult(clip_path=str(clip_path), cut_type=cut.cut_type, duration_s=CLIP_DURATION_S)
