"""Phase 0 — 렌더 스파이크 (스펙 §8 Phase 0).

하드코딩 한국어 대본 1건 → 선택된 TTS(M4) → timestamps.json(M4/M5) →
MoviePy 렌더(M6) → data/jobs/{job_id}/video.mp4.

DoD: 한글 자막 정상 표시 / 자막-음성 싱크 체감 오차 없음 / 렌더 시간 측정 기록.
실행(프로젝트 루트에서): python -m src.phase0_spike --provider auto
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from src.audio import tts
from src.video.render import render_video

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 하드코딩 스파이크 대본 (썰피자식 훅·가격라인·질문 구조의 축약판, 약 12초)
SPIKE_SCRIPT = {
    "title": "Phase 0 렌더 스파이크 — 미니 세탁기",
    "lines": [
        {"text": "빨래를 3분 만에 끝내는 기계가 있다면 믿으시겠습니까", "price_shock": False},
        {"text": "이 미니 세탁기는 무게가 고작 1.2킬로그램입니다", "price_shock": False},
        {"text": "자취방에서도 캠핑장에서도 바로 돌릴 수 있습니다", "price_shock": False},
        {"text": "가격은 단돈 49,900원입니다", "price_shock": True},
        {"text": "이 가격이면 한번 써볼 만하지 않을까요", "price_shock": False},
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 렌더 스파이크")
    parser.add_argument("--provider", default=None,
                        help="auto|elevenlabs|typecast|clova|mock (기본: settings.yaml)")
    parser.add_argument("--job-id", default=None, help="data/jobs/ 하위 작업 폴더 이름")
    args = parser.parse_args()

    settings = yaml.safe_load((PROJECT_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    tts_settings = dict(settings.get("tts", {}))
    if args.provider:
        tts_settings["provider"] = args.provider

    job_id = args.job_id or time.strftime("job_%Y%m%d_%H%M%S")
    job_dir = PROJECT_ROOT / "data" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    lines = SPIKE_SCRIPT["lines"]
    text = "\n".join(line["text"] for line in lines)
    (job_dir / "script.json").write_text(
        json.dumps(SPIKE_SCRIPT, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"[phase0] job={job_id} 대본 {len(lines)}줄, 공백 제외 "
          f"{len(text.replace(' ', '').replace(chr(10), ''))}자")

    # M4 (+ 필요 시 M5 폴백) — 공통 계약: audio.mp3 + timestamps.json
    t0 = time.time()
    try:
        tts_result = tts.synthesize_to_files(
            text, job_dir, tts_settings, settings.get("whisper", {}))
    except tts.TTSError as e:
        print(f"::error::[phase0] TTS 중단: {e}")
        return 2
    tts_seconds = time.time() - t0
    words = tts_result["words"]
    print(f"[phase0] TTS 완료({tts_result['provider']}, "
          f"타임스탬프={tts_result['timestamps_source']}): 단어 {len(words)}개, "
          f"{tts_seconds:.1f}초 소요")

    # price_shock 라인 → 쉐이크 구간 (라인 시작 시점부터 shake_seconds)
    shake_windows = []
    shake_sec = float(settings.get("render", {}).get("shake_seconds", 0.3))
    idx = 0
    for line in lines:
        n = len(line["text"].split())
        if line["price_shock"] and idx < len(words):
            start = float(words[idx]["start"])
            shake_windows.append((start, start + shake_sec))
        idx += n

    # M6 렌더
    out_path = job_dir / "video.mp4"
    stats = render_video(
        audio_path=tts_result["audio_path"], words=words, out_path=out_path,
        settings=settings, shake_windows=shake_windows, project_root=PROJECT_ROOT)

    from importlib.metadata import version as pkg_version
    stats = {
        "job_id": job_id,
        "tts_provider": tts_result["provider"],
        "timestamps_source": tts_result["timestamps_source"],
        "tts_seconds": round(tts_seconds, 1),
        **stats,
        "total_seconds": round(time.time() - t0, 1),
        "moviepy_version": pkg_version("moviepy"),
        "shake_windows": [[round(a, 2), round(b, 2)] for a, b in shake_windows],
    }
    (job_dir / "render_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")

    print("[phase0] ===== 렌더 시간 측정 기록 (DoD) =====")
    for k in ("tts_provider", "timestamps_source", "tts_seconds", "render_seconds",
              "video_duration_seconds", "realtime_factor", "resolution",
              "font_used", "background_used", "total_seconds"):
        print(f"[phase0] {k}: {stats[k]}")
    print(f"[phase0] 산출물: {out_path} ({stats['output_bytes'] / 1e6:.1f}MB)")

    _write_step_summary(stats, out_path)
    return 0


def _write_step_summary(stats: dict, out_path: Path) -> None:
    """GitHub Actions 실행 요약 탭에 결과표 기록 (로컬에선 no-op)."""
    import os
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    rows = "\n".join(f"| {k} | {v} |" for k, v in stats.items())
    Path(summary).open("a", encoding="utf-8").write(
        f"## Phase 0 렌더 스파이크 결과\n\n| 항목 | 값 |\n|---|---|\n{rows}\n\n"
        f"영상은 이 실행 페이지 하단 **Artifacts** 에서 다운로드하세요.\n")


if __name__ == "__main__":
    sys.exit(main())
