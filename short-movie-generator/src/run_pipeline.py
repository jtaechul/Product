"""CLI 진입점.

사용:
  .venv/bin/python -m src.run_pipeline "dumbo octopus"
  .venv/bin/python -m src.run_pipeline "dumbo octopus" --visualizer veo_img2video
"""
from __future__ import annotations

import argparse
import logging
import sys

from dotenv import load_dotenv

from src.core.contracts import PipelineError
from src.core.pipeline import run


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="쇼츠/릴스 자동 생성 파이프라인")
    parser.add_argument("query", help="대상 질의 (예: 'dumbo octopus')")
    parser.add_argument("--category", default="deep_sea", help="카테고리 ID (기본: deep_sea)")
    parser.add_argument(
        "--visualizer", default="panzoom", choices=["panzoom", "veo_img2video"],
        help="시각화 구현체 (기본: panzoom, Veo는 GEMINI_API_KEY 필요)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        result = run(args.category, args.query, args.visualizer)
    except PipelineError as e:
        logging.error("파이프라인 중단: %s", e)
        return 1

    print(f"\n=== 완료 ===")
    print(f"영상: {result.video_path}")
    print(f"메타: {result.sidecar_meta}")
    print(f"QC: {'전 항목 통과' if result.qc_passed else '실패 항목 있음'}")
    for check, r in result.qc_report.items():
        print(f"  [{'O' if r['passed'] else 'X'}] {check}: {r['detail']}")
    return 0 if result.qc_passed else 2


if __name__ == "__main__":
    sys.exit(main())
