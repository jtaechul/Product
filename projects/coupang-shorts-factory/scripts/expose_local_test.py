"""로컬 검증 전용 — 폭로(expose) 레이아웃 렌더 + QA 게이트를 API 키 없이 확인한다.
mock 대본(headline 포함) → 무음 트랙 → render_video(expose) → run_qa → 프레임 추출.
CI가 아니라 개발 검증용(수정 후 검증 원칙)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.script.sanitize import sanitize_script          # noqa: E402
from src.pipeline import _silent_track, _line_windows      # noqa: E402
from src.video.render import render_video                  # noqa: E402
from src.video.qa import run_qa                            # noqa: E402

JOB = ROOT / "data" / "jobs" / "_expose_test"
JOB.mkdir(parents=True, exist_ok=True)

# ── mock 대본 (폭로 아크 + headline). subs 계약은 sanitize가 검증/복구.
SCRIPT = {
    "title": "설거지 3분 만에 끝내는 그 물건 정체",
    "headline": "당신이 몰랐던 설거지의 진실",
    "lines": [
        {"text": "다들 속고 살았음", "stage": 1, "punch": True, "subs": ["다들", "속고 살았음"]},
        {"text": "설거지에 하루를 갈아넣음", "stage": 1, "punch": False, "subs": ["설거지에", "하루를 갈아넣음"]},
        {"text": "너도 그랬을걸", "stage": 2, "punch": False, "subs": ["너도", "그랬을걸"]},
        {"text": "손은 다 불어터짐", "stage": 3, "punch": False, "subs": ["손은 다", "불어터짐"]},
        {"text": "근데 이걸 끝낸 물건이 나타남", "stage": 4, "punch": False, "subs": ["근데 이걸", "끝낸 물건이", "나타남"]},
        {"text": "3초면 기름때가 사라짐", "stage": 4, "punch": False, "subs": ["3초면", "기름때가", "사라짐"]},
        {"text": "원리를 알면 소름 돋음", "stage": 5, "punch": False, "subs": ["원리를 알면", "소름 돋음"]},
        {"text": "그래서 다들 속고 살았던 거임", "stage": 5, "punch": False, "subs": ["그래서 다들", "속고 살았던", "거임"]},
    ],
    "hashtags": ["설거지", "주방템", "자취템"],
    "bg_keywords": ["kitchen sink", "dishwashing"],
    "description_body": "테스트",
    "pinned_comment": "테스트",
}


def _mk_img(path: Path, rgb: tuple, label: str):
    im = Image.new("RGB", (1200, 900), rgb)
    im.save(path)


def main() -> int:
    script = sanitize_script(dict(SCRIPT), strict_length=False)
    print(f"[test] headline='{script.get('headline')}' 라인 {len(script['lines'])}개")
    lines = script["lines"]

    # 무음 트랙 + 타이밍
    tts = _silent_track(lines, JOB)
    words = tts["words"]
    line_windows = _line_windows(lines, words)

    # 테스트용 라인 이미지: 컬러 PNG 몇 장 + 일부러 None(브랜드 패널 폴백 경로 확인)
    imgs = []
    palette = [(210, 90, 70), (70, 150, 200), (90, 190, 120), (200, 170, 60),
               (150, 100, 200), (60, 180, 190)]
    for i, ln in enumerate(lines):
        if i in (2, 6):        # 이 라인들은 이미지 없음 → 브랜드 패널로 채워져야 함
            imgs.append(None)
            continue
        p = JOB / f"img_{i}.png"
        _mk_img(p, palette[i % len(palette)], ln["text"])
        imgs.append(str(p))
    product_images = [imgs[4]]   # 상품 라인 사진 하나(④)

    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    print(f"[test] layout={settings['render']['layout']}")

    out = JOB / "video.mp4"
    stats = render_video(tts["audio_path"], words, out, settings,
                         project_root=ROOT, product_images=[p for p in product_images if p],
                         lines=lines, line_windows=line_windows, line_images=imgs,
                         has_narration=False, headline=script.get("headline", ""))
    print(f"[test] 렌더 완료: {stats['video_duration_seconds']}s, "
          f"{stats.get('render_seconds')}s 소요")

    stats2 = {"subtitle_plan": stats.get("subtitle_plan"),
              "video_duration_seconds": stats["video_duration_seconds"]}
    report = run_qa(out, stats2, lines, JOB, settings)
    print(f"[test] QA passed={report['passed']}")
    if not report["passed"]:
        for p in report["problems"]:
            print("   -", p)

    # 프레임 추출(눈으로 확인)
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    dur = stats["video_duration_seconds"]
    shots = JOB / "shots"
    shots.mkdir(exist_ok=True)
    for frac in (0.05, 0.35, 0.6, 0.85):
        t = dur * frac
        subprocess.run([ff, "-y", "-ss", f"{t:.2f}", "-i", str(out),
                        "-frames:v", "1", str(shots / f"f_{int(frac*100)}.png")],
                       capture_output=True, check=True)
    print(f"[test] 프레임 4장 → {shots}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
