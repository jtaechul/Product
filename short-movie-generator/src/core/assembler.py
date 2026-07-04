"""assembler — 컷 클립들을 이어붙여 단일 영상으로 (spec 8장).

concat 필터(재인코딩)를 사용한다: `-c copy` 는 입력들의 코덱/타임베이스/GOP 가
byte-identical 이어야 하는데, Veo가 반환하는 클립은 인코딩이 균일하다는 보장이 없다.
concat 필터는 각 입력을 디코드→재인코딩하므로 panzoom·Veo 등 이질적 소스에도 안전.
(계약상 모든 클립은 9:16 720p 동일 해상도.)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.core.contracts import ClipResult, PipelineError
from src.core.visualization.base import CLIP_FPS, CLIP_H, CLIP_W

_CUT_ORDER = {"discovery": 0, "behavior": 1, "detail": 2}


def concat_clips(clips: list[ClipResult], work_dir: str) -> str:
    """3컷을 discovery→behavior→detail 순으로 이어붙여 work/base.mp4 반환."""
    if not clips:
        raise PipelineError("assembler", "이어붙일 클립이 없음")

    ordered = sorted(clips, key=lambda c: _CUT_ORDER.get(c.cut_type, 99))
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    base_path = work / "base.mp4"

    # 각 입력을 규격으로 정규화(scale+fps+sar) 후 concat 필터로 결합 (재인코딩)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for c in ordered:
        cmd += ["-i", c.clip_path]

    n = len(ordered)
    norm = "".join(
        f"[{i}:v]scale={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1[v{i}];"
        for i in range(n)
    )
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filtergraph = f"{norm}{concat_inputs}concat=n={n}:v=1:a=0[outv]"

    cmd += [
        "-filter_complex", filtergraph,
        "-map", "[outv]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        str(base_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not base_path.exists():
        raise PipelineError("assembler", f"concat 실패: {proc.stderr[-500:]}")
    return str(base_path)
