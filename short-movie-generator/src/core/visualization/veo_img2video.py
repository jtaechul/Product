"""veo_img2video 구현체 — Veo 3.1 Lite img2video (spec 채택 구현체).

GEMINI_API_KEY 필요(과금). 키가 없으면 명확한 에러로 안전 중단 → panzoom fallback 사용.
spikes/veo_cut1_test.py 실측 코드를 인터페이스 계약에 맞춰 모듈화한 것.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from src.core.contracts import ApprovedAsset, ClipResult, CutSpec
from src.core.visualization.base import (
    CLIP_DURATION_S,
    VisualizationError,
    Visualizer,
)

MODEL = "veo-3.1-lite-generate-preview"
# 주의: veo-3.1-lite는 negative_prompt 미지원(400 에러) → 왜곡 방지 지시는
# 상황뱅크 프롬프트 본문("Keep the octopus's exact shape ... do not distort")이 담당.
_POLL_INTERVAL_S = 10
_TIMEOUT_S = 15 * 60


class VeoImg2VideoVisualizer(Visualizer):
    name = "veo_img2video"

    def __init__(self, client=None):
        # client 주입 가능(테스트 mock). 실사용 시 지연 생성.
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not os.environ.get("GEMINI_API_KEY"):
            raise VisualizationError(
                "GEMINI_API_KEY 없음 → .env 에 키를 채우거나 --visualizer panzoom 사용"
            )
        from google import genai  # 지연 임포트 (키 없는 환경에서도 모듈 로드는 가능하게)

        self._client = genai.Client()
        return self._client

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

        mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
        operation = client.models.generate_videos(
            model=MODEL,
            prompt=cut.prompt,
            image=types.Image(image_bytes=img_path.read_bytes(), mime_type=mime),
            # generate_audio 파라미터는 Developer API 모드에서 미지원(전달 시 ValueError).
            # Veo가 오디오를 포함해 반환해도 assembler가 영상만 concat(a=0)하므로 제거되고,
            # 앰비언트는 후처리 audio 모듈에서 레이어링한다 (CLAUDE.md 오디오 규칙).
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
        client.files.download(file=video)  # 서버 보관 2일 → 즉시 로컬 저장
        video.save(str(clip_path))
        if not clip_path.exists():
            raise VisualizationError(f"클립 저장 실패: {clip_path}")

        return ClipResult(clip_path=str(clip_path), cut_type=cut.cut_type, duration_s=CLIP_DURATION_S)
