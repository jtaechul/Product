"""panzoom 구현체 — FFmpeg zoompan(켄 번즈)으로 정지 이미지를 9:16 클립으로.

Veo 없이(API 키·비용 0) 파이프라인 전체를 완주·검증하기 위한 공식 fallback (spec 3장).
컷 타입별 카메라 무브를 스타일 스펙(slow push-in / lateral track / macro hold)에 맞춰 차등.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from src.core.contracts import ApprovedAsset, ClipResult, CutSpec

log = logging.getLogger(__name__)
from src.core.visualization.base import (
    CLIP_DURATION_S,
    CLIP_FPS,
    CLIP_H,
    CLIP_W,
    VisualizationError,
    Visualizer,
)

_FRAMES = CLIP_DURATION_S * CLIP_FPS

# 컷 타입 → zoompan 표현식 (스타일 스펙의 카메라 무브 매핑)
# zoompan 안 좌표계: 입력(업스케일된) 이미지 기준, zoom은 1.0=전체 뷰
# 벤치마크(What On Earth) 카메라 = 거의 정지·느린 관찰. 켄번즈 무브를 전반적으로 약하게 튜닝.
_CAMERA = {
    # discovery: 아주 느린 미세 푸시인 (어둠→등장 훅). 빠른 줌 금지.
    "discovery": {
        "z": f"min(1.0+0.08*on/{_FRAMES},1.08)",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
        "fade_in": True,
    },
    # behavior: 아주 완만한 횡이동 (고정 줌, 이동폭 절반으로 축소 → 부드럽게)
    "behavior": {
        "z": "1.10",
        "x": f"(iw-iw/zoom)*(0.35+0.30*on/{_FRAMES})",
        "y": "ih/2-(ih/zoom/2)",
        "fade_in": False,
    },
    # detail: 느린 매크로 홀드 (얕은 전진, 급줌 금지)
    "detail": {
        "z": f"min(1.12+0.16*on/{_FRAMES},1.28)",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
        "fade_in": False,
    },
}


def _subject_center(path: str) -> tuple[float, float]:
    """어두운 배경 위 밝은 심해 생물의 무게중심(가로·세로 비율 0~1)을 추정.

    실사 사진이 가로형이라 9:16 중앙 크롭 시 피사체가 한쪽으로 쏠려 잘리는 문제를 막기 위해,
    '배경보다 밝은 픽셀'의 무게중심으로 크롭 창을 옮긴다. 실패 시 (0.5, 0.5)=중앙.
    """
    try:
        from PIL import Image
        im = Image.open(path).convert("L").resize((64, 64))
        px = list(im.getdata())
        lo = sorted(px)[int(len(px) * 0.6)]  # 배경(하위 60%) 컷 → 밝은 피사체만 가중
        sx = sy = sw = 0.0
        for i, v in enumerate(px):
            w = v - lo
            if w <= 0:
                continue
            sx += (i % 64) * w
            sy += (i // 64) * w
            sw += w
        if sw <= 0:
            return 0.5, 0.5
        return sx / sw / 63.0, sy / sw / 63.0
    except Exception as e:  # noqa: BLE001
        log.warning("[panzoom] 피사체 중심 추정 실패 → 중앙 크롭: %s", e)
        return 0.5, 0.5


class PanzoomVisualizer(Visualizer):
    name = "panzoom"

    def generate_clip(
        self,
        asset: ApprovedAsset,
        cut: CutSpec,
        situation_id: str,
        style_profile: str,
        out_dir: str,
    ) -> ClipResult:
        cam = _CAMERA.get(cut.cut_type)
        if cam is None:
            raise VisualizationError(f"알 수 없는 cut_type: {cut.cut_type}")

        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        clip_path = out / f"{situation_id}_{cut.cut_type}.mp4"

        # 1) 이미지를 크게 업스케일(줌 계단현상 방지) 후 9:16 크롭 기준으로 zoompan
        #    크롭 창은 '피사체 무게중심'을 따라 이동(가로형 사진의 쏠림·잘림 방지).
        # 2) discovery만 1초 페이드인(어둠→등장)
        sh = CLIP_H * 4
        try:
            from PIL import Image
            w0, h0 = Image.open(asset.asset_path).size
        except Exception:  # noqa: BLE001
            w0, h0 = CLIP_W, CLIP_H
        sw = max(2, round(w0 * sh / max(1, h0)) & ~1)          # scale=-2:sh 후 가로(짝수)
        cw = min(sw, round(sh * CLIP_W / CLIP_H)) & ~1          # 9:16 크롭 폭
        ch = min(sh, round(sw * CLIP_H / CLIP_W)) & ~1          # 9:16 크롭 높이
        fx, fy = _subject_center(asset.asset_path)
        cx = int(min(max(fx * sw - cw / 2, 0), sw - cw))       # 피사체 중심 정렬(클램프)
        cy = int(min(max(fy * sh - ch / 2, 0), sh - ch))
        vf = (
            f"scale=-2:{sh},crop={cw}:{ch}:{cx}:{cy},"
            f"zoompan=z='{cam['z']}':x='{cam['x']}':y='{cam['y']}'"
            f":d={_FRAMES}:s={CLIP_W}x{CLIP_H}:fps={CLIP_FPS}"
        )
        if cam["fade_in"]:
            vf += ",fade=t=in:st=0:d=1.0"

        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-i", asset.asset_path,
            "-vf", vf,
            "-t", str(CLIP_DURATION_S),
            "-r", str(CLIP_FPS),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-an",  # raw 클립은 무음, 앰비언트는 후처리에서 (CLAUDE.md 오디오 규칙)
            str(clip_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not clip_path.exists():
            raise VisualizationError(f"ffmpeg 실패 ({cut.cut_type}): {proc.stderr[-500:]}")

        return ClipResult(clip_path=str(clip_path), cut_type=cut.cut_type, duration_s=CLIP_DURATION_S)
