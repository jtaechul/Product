"""파이프라인 오케스트레이션 (spec 2장).

종 입력 → 정보 조회 → 소싱 → 라이선스 게이트 → 시각화(3컷) → 합성
→ 캡션 → 오버레이 → 오디오 → 출력·QC

원칙:
- 코어는 카테고리 내부를 모른다 (CategoryModule 계약만 의존)
- 시각화는 Visualizer 계약만 의존 (구현체 교체 가능)
- 단계 실패 시 명확 로그 + 안전 중단 (부분 산출물 미발행)
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.core import assembler, audio, license_gate, output, overlay
from src.core.contracts import OutputResult, PipelineError
from src.core.visualization import VisualizationError, get_visualizer
from src.registry import get_category

log = logging.getLogger(__name__)

WATERMARK = "DEEP DIVE LOG"  # 브랜드명 [TBD] — 확정 시 교체


def run(
    category_id: str,
    query: str,
    visualizer_name: str = "panzoom",
    base_dir: str = ".",
) -> OutputResult:
    base = Path(base_dir)
    raw_dir = base / "assets" / "raw"
    approved_dir = base / "assets" / "approved"
    clips_dir = base / "work" / "clips"
    work_dir = base / "work"
    out_dir = base / "output"
    for d in (raw_dir, approved_dir, clips_dir, work_dir, out_dir):
        d.mkdir(parents=True, exist_ok=True)

    category = get_category(category_id)
    viz = get_visualizer(visualizer_name)
    log.info("파이프라인 시작: category=%s, query=%r, visualizer=%s", category_id, query, viz.name)

    # 1. 입력 파싱
    subject = category.parse_input(query)
    log.info("[1/9] 입력: %s", subject)

    # 2. 정보 조회
    info = category.get_info(subject)
    log.info("[2/9] 정보: %s (%s)", info.common_name_ko, info.scientific_name)

    # 3. 소싱
    raw_assets = category.source_assets(info, str(raw_dir))
    if not raw_assets:
        raise PipelineError("sourcing", "수집된 에셋 없음")
    log.info("[3/9] 소싱: %d개", len(raw_assets))

    # 4. 라이선스 게이트 (하드 룰)
    approved = license_gate.filter_assets(raw_assets, str(approved_dir))
    if not approved:
        raise PipelineError("license_gate", "통과 에셋 없음 → 제작 중단 (차단 에셋은 절대 미사용)")
    asset = approved[0]
    log.info("[4/9] 게이트 통과: %s (%s)", asset.asset_path, asset.license)

    # 5. 상황 뱅크 + 정확성 게이트 (하드 룰)
    situation = category.get_situation(info)
    violations = category.validate_cuts(situation)
    if violations:
        raise PipelineError("situation_bank", f"정확성 규칙 위반: {violations}")
    log.info("[5/9] 상황: %s (%d컷, 정확성 통과)", situation.situation_id, len(situation.cuts))

    # 6. 시각화 (컷별 클립 생성) — 시각화 실패도 파이프라인 단계 실패로 통일
    clips = []
    for cut in situation.cuts:
        try:
            clip = viz.generate_clip(
                asset, cut, situation.situation_id, category.style_profile, str(clips_dir)
            )
        except VisualizationError as e:
            raise PipelineError("visualization", str(e)) from e
        log.info("[6/9] 클립: %s (%ss)", clip.clip_path, clip.duration_s)
        clips.append(clip)

    # 7. 합성
    base_video = assembler.concat_clips(clips, str(work_dir))
    total_duration = sum(c.duration_s for c in clips)
    log.info("[7/9] 합성: %s (%.0fs)", base_video, total_duration)

    # 8. 캡션 → 오버레이 → 오디오
    caption = category.build_caption(info)
    overlay_png = overlay.build_overlay_png(
        caption, info, asset.credit_string, WATERMARK, str(work_dir / "overlay.png")
    )
    overlaid = overlay.apply_overlay(base_video, overlay_png, str(work_dir))
    with_audio = audio.add_ambient(
        overlaid, str(work_dir), total_duration, category.ambient_audio_spec()
    )
    log.info("[8/9] 오버레이+오디오: %s", with_audio)

    # 9. 출력 + QC
    result = output.finalize(
        with_audio, info, caption, asset.credit_string, asset.license,
        str(out_dir), total_duration,
        extra_meta={"category": category_id, "visualizer": viz.name,
                    "style_profile": category.style_profile,
                    "situation_id": situation.situation_id},
    )
    log.info("[9/9] 출력: %s (QC %s)", result.video_path, "통과" if result.qc_passed else "실패")
    return result
