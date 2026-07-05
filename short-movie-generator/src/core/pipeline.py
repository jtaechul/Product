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
import subprocess
from pathlib import Path

from src.core import assembler, audio, endcard, htmlhud, hud, license_gate, output, overlay  # noqa: F401
from src.core.contracts import OutputResult, PipelineError
from src.core.visualization import VisualizationError, get_visualizer
from src.registry import get_category

log = logging.getLogger(__name__)

WATERMARK = "DEEP DIVE LOG"  # 브랜드명 [TBD] — 확정 시 교체


def _apply_grade(video_path: str, vf: str, work_dir: str) -> str:
    """카테고리 그레이딩 필터 적용 (오버레이 전 → 텍스트는 영향 없음)."""
    out = Path(work_dir) / "graded.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path, "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-an", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("grade", f"그레이딩 실패: {proc.stderr[-400:]}")
    return str(out)


def run(
    category_id: str,
    query: str,
    visualizer_name: str = "panzoom",
    base_dir: str = ".",
    episode: int | None = None,
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

    # 7. 합성 (+레터박스 자동 제거) → 카테고리 그레이딩 (텍스트 전이라 텍스트는 선명)
    base_video = assembler.concat_clips(clips, str(work_dir))
    total_duration = sum(c.duration_s for c in clips)
    grade = category.grade_filter()
    if grade:
        base_video = _apply_grade(base_video, grade, str(work_dir))
    log.info("[7/9] 합성+그레이딩: %s (%.0fs)", base_video, total_duration)

    # 8. 캡션 → 컷별 타이밍 오버레이(리빌 정책) → 오디오(리빌 악센트)
    caption = category.build_caption(info)
    # 저작권 표기(하드룰): 릴스 캡션에 이미지 출처(저작자·라이선스) + 종 정보 출처를 반드시 포함
    if hasattr(category, "attach_attribution"):
        caption = category.attach_attribution(caption, info, asset.credit_string)
    durations = [c.duration_s for c in clips]
    # 애니메이션 HTML HUD(우선) → 브라우저 불가/실패 시 PIL HUD 폴백 (파이프라인 불정지)
    hud_callouts = category.hud_callouts(info) if hasattr(category, "hud_callouts") else []
    hud_theme = getattr(category, "hud_theme", htmlhud.THEME_DEFAULT)
    try:
        overlaid = htmlhud.apply_hud(
            base_video, caption, info, WATERMARK, durations, str(work_dir),
            theme=hud_theme, callouts=hud_callouts,
        )
    except htmlhud.HudRenderError as e:
        log.warning("HTML HUD 실패 → PIL HUD 폴백: %s", e)
        overlaid = hud.apply_hud(
            base_video, caption, info, WATERMARK, durations, str(work_dir),
        )
    # 시리즈 엔드카드 (재방문·팔로우 유도) — 어둡게 끝나 콜드오픈 루프와 연결
    if episode is None:
        # 도감 번호는 카테고리의 커밋되는 원장에서 예약(안정적 누적). CI 컨테이너 리셋 무관.
        if hasattr(category, "next_episode"):
            episode = category.next_episode()
        else:
            episode = len(list(Path(out_dir).glob("*.json"))) + 1  # 폴백(자동 회차)
    series_title = getattr(category, "series_title", "") or category_id
    # 통합 마지막 페이지: 실제 NOAA 사진(충격 리빌·피사체 중앙 크롭) + 종 도감 도시에
    # (신뢰 앵커·출처·팔로우 + 생태 특성 한 줄)
    eco_bits = [f"수심 {info.depth_range_m}m" if info.depth_range_m else "", info.habitat or ""]
    if info.diet:
        eco_bits.append(" ".join(info.diet[:2]))
    eco_line = " · ".join(b for b in eco_bits if b)
    final_page = endcard.build_final_page(
        caption, series_title, episode, WATERMARK,
        asset.asset_path, asset.credit_string, info.scientific_name, str(work_dir),
        eco_line=eco_line,
    )
    with_endcard = endcard.concat_tail([overlaid, final_page], str(work_dir))
    final_duration = total_duration + endcard.FINAL_PAGE_DURATION_S

    reveal_at = sum(durations[:-1]) if len(durations) >= 2 else None  # 마지막 컷 시작 = 리빌
    # 타자 효과음을 화면 타이핑과 동기 (HUD 타임라인 재사용)
    sfx_tl = htmlhud.sfx_timeline(caption, info, durations)
    with_audio = audio.add_ambient(
        with_endcard, str(work_dir), final_duration, category.ambient_audio_spec(),
        reveal_at_s=reveal_at, sfx_timeline=sfx_tl,
        photo_at_s=total_duration,  # 실제 사진 카드 시작 = 본편 끝 → 셔터/확정 효과음
    )
    log.info("[8/9] 오버레이+엔드카드+오디오: %s (리빌 %.0fs, #%d)", with_audio, reveal_at or -1, episode)

    # 9. 출력 + QC
    result = output.finalize(
        with_audio, info, caption, asset.credit_string, asset.license,
        str(out_dir), final_duration,
        extra_meta={"category": category_id, "visualizer": viz.name,
                    "style_profile": category.style_profile,
                    "situation_id": situation.situation_id,
                    "series": {"title": series_title, "episode": episode}},
    )
    log.info("[9/9] 출력: %s (QC %s)", result.video_path, "통과" if result.qc_passed else "실패")

    # 제작 성공분을 도감 원장에 기록 → 번호 누적 + 제작 페이지 현황판("#000_국문명") 근거
    if hasattr(category, "log_catalog"):
        category.log_catalog(episode, info)
    return result
