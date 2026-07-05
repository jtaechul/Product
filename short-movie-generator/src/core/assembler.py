"""assembler — 컷 클립들을 이어붙여 단일 영상으로 (spec 8장).

concat 필터(재인코딩)를 사용한다: `-c copy` 는 입력들의 코덱/타임베이스/GOP 가
byte-identical 이어야 하는데, Veo가 반환하는 클립은 인코딩이 균일하다는 보장이 없다.
concat 필터는 각 입력을 디코드→재인코딩하므로 panzoom·Veo 등 이질적 소스에도 안전.
(계약상 모든 클립은 9:16 720p 동일 해상도.)
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from src.core.contracts import ClipResult, PipelineError
from src.core.visualization.base import CLIP_FPS, CLIP_H, CLIP_W

_CUT_ORDER = {"discovery": 0, "behavior": 1, "detail": 2}

# cropdetect 결과 파싱: crop=W:H:X:Y
_CROP_RE = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


def detect_letterbox_crop(clip_path: str) -> str | None:
    """클립 앞 2초를 cropdetect로 분석해 검은 띠(레터박스) 크롭 문자열 반환.

    AI 생성 영상이 '시네마틱 검은 띠'를 넣는 문제(실측 v2·v3) 대응.
    유의미한 띠(높이/너비 3% 이상 손실)일 때만 크롭 반환, 아니면 None.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-i", clip_path, "-t", "2",
        "-vf", "cropdetect=limit=24:round=2:reset=0", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    matches = _CROP_RE.findall(proc.stderr)
    if not matches:
        return None
    w, h, x, y = map(int, matches[-1])  # 마지막(안정화된) 감지값
    if w <= 0 or h <= 0:
        return None
    # 원본 대비 3% 이상 잘려나갈 때만 적용 (미세 노이즈 크롭 방지)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", clip_path],
        capture_output=True, text=True,
    ).stdout.strip().split(",")
    try:
        ow, oh = int(probe[0]), int(probe[1])
    except (ValueError, IndexError):
        return None
    if w >= ow * 0.97 and h >= oh * 0.97:
        return None
    return f"crop={w}:{h}:{x}:{y}"


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
    # 입력별 정규화: (레터박스 감지 시) 띠 크롭 → '커버' 스케일 → 중앙 크롭(왜곡 방지)
    # → fps → SAR. 단순 scale은 크롭 후 화면을 늘려 왜곡시키므로 cover+crop 방식 사용.
    fit = (f"scale=w={CLIP_W}:h={CLIP_H}:force_original_aspect_ratio=increase,"
           f"crop={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1")
    norm_parts = []
    for i, c in enumerate(ordered):
        crop = detect_letterbox_crop(c.clip_path)
        chain = (crop + "," if crop else "") + fit
        norm_parts.append(f"[{i}:v]{chain}[v{i}];")
    norm = "".join(norm_parts)
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
