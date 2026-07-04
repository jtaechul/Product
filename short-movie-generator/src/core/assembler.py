"""assembler — 컷 클립들을 FFmpeg concat 으로 단일 영상으로 (spec 8장)."""
from __future__ import annotations

import subprocess
from pathlib import Path

from src.core.contracts import ClipResult, PipelineError

_CUT_ORDER = {"discovery": 0, "behavior": 1, "detail": 2}


def concat_clips(clips: list[ClipResult], work_dir: str) -> str:
    """3컷을 discovery→behavior→detail 순으로 이어붙여 work/base.mp4 반환."""
    if not clips:
        raise PipelineError("assembler", "이어붙일 클립이 없음")

    ordered = sorted(clips, key=lambda c: _CUT_ORDER.get(c.cut_type, 99))
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    # concat demuxer용 목록 파일 (동일 코덱/해상도 전제 → 시각화 계약이 보장)
    list_file = work / "concat_list.txt"
    lines = [f"file '{Path(c.clip_path).resolve()}'" for c in ordered]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    base_path = work / "base.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy",
        str(base_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not base_path.exists():
        raise PipelineError("assembler", f"concat 실패: {proc.stderr[-500:]}")
    return str(base_path)
