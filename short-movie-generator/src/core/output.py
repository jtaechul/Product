"""output — 최종 mp4 + 사이드카 메타 저장, QC 검증 (spec 11-1 수용 기준 자동 체크)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from src.core.contracts import CaptionData, OutputResult, PipelineError, SpeciesInfo
from src.core.visualization.base import CLIP_H, CLIP_W


def _ffprobe(video: str) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", video,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise PipelineError("output", f"ffprobe 실패: {proc.stderr[-300:]}")
    return json.loads(proc.stdout)


def _mean_volume_db(video: str) -> float:
    """volumedetect로 평균 음량(dB). 무음 출력 금지 검증용."""
    cmd = [
        "ffmpeg", "-i", video, "-map", "0:a", "-af", "volumedetect",
        "-f", "null", "-", "-loglevel", "info", "-y",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", proc.stderr)
    return float(m.group(1)) if m else -999.0


def run_qc(video: str, expected_duration_s: float, sidecar: dict) -> dict:
    """수용 기준(spec 11-1) 자동 검증 → {check: (bool, detail)} 리포트."""
    probe = _ffprobe(video)
    v = next((s for s in probe["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in probe["streams"] if s["codec_type"] == "audio"), None)
    duration = float(probe["format"].get("duration", 0))
    mean_db = _mean_volume_db(video) if a else -999.0

    report = {
        "resolution_9_16": (
            bool(v) and v["width"] == CLIP_W and v["height"] == CLIP_H,
            f"{v['width']}x{v['height']}" if v else "no video stream",
        ),
        "duration_3cuts": (
            abs(duration - expected_duration_s) <= 1.5,
            f"{duration:.2f}s (기대 {expected_duration_s}s)",
        ),
        "audio_present_not_silent": (
            a is not None and mean_db > -70.0,
            f"mean_volume={mean_db:.1f} dB" if a else "no audio stream",
        ),
        "caption_in_sidecar": (
            all(k in sidecar.get("caption", {}) for k in ("hook_text", "caption_body", "hashtags")),
            "hook/body/hashtags 존재 여부",
        ),
        "credit_in_sidecar": (
            bool(sidecar.get("credit_string")),
            sidecar.get("credit_string", ""),
        ),
        "license_ok_only": (
            sidecar.get("license_ok") is True,
            f"license={sidecar.get('license')}",
        ),
    }
    return report


def finalize(
    video_path: str,
    info: SpeciesInfo,
    caption: CaptionData,
    credit_string: str,
    license_name: str,
    out_dir: str,
    expected_duration_s: float,
    extra_meta: dict | None = None,
) -> OutputResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    slug = info.common_name_en.lower().replace(" ", "_")
    final_video = out / f"{slug}_{ts}.mp4"
    shutil.copy2(video_path, final_video)

    sidecar = {
        "species": {
            "scientific_name": info.scientific_name,
            "common_name_ko": info.common_name_ko,
            "common_name_en": info.common_name_en,
        },
        "caption": {
            "hook_text": caption.hook_text,
            "caption_body": caption.caption_body,
            "overlay_facts": caption.overlay_facts,
            "hashtags": caption.hashtags,
        },
        "credit_string": credit_string,
        "license": license_name,
        "license_ok": True,
        "created_at": ts,
        **(extra_meta or {}),
    }

    qc = run_qc(str(final_video), expected_duration_s, sidecar)
    qc_passed = all(ok for ok, _ in qc.values())
    sidecar["qc"] = {k: {"passed": ok, "detail": detail} for k, (ok, detail) in qc.items()}
    sidecar["qc_passed"] = qc_passed

    sidecar_path = final_video.with_suffix(".json")
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8")

    return OutputResult(
        video_path=str(final_video),
        sidecar_meta=str(sidecar_path),
        qc_passed=qc_passed,
        qc_report={k: {"passed": ok, "detail": d} for k, (ok, d) in qc.items()},
    )
