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

from src.core import assembler, audio, carousel, content_store, endcard, htmlhud, hud, license_gate, output, overlay, subtitle, tts  # noqa: F401
from src.core.visualization.base import CLIP_H, CLIP_W
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


def _pad_last_frame(video_path: str, target_s: float, work_dir: str) -> str:
    """영상을 target_s까지 마지막 프레임 복제로 연장(나레이션이 영상보다 길 때)."""
    out = Path(work_dir) / "padded.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
         "-vf", f"tpad=stop_mode=clone:stop_duration={target_s:.3f}",
         "-t", f"{target_s:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-an", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("pad", f"영상 연장 실패: {proc.stderr[-300:]}")
    return str(out)


def _maybe_apply_hook_intro(category, info, body_video: str, work_dir: str) -> str:
    """카테고리가 hook_intro_spec(info)→(SpeciesSpec, hook_text[, bgm])를 제공하면
    오프닝 훅/엔드카드/전환/임팩트 사운드 시스템을 적용. 미제공·실패 시 원본 그대로."""
    if not hasattr(category, "hook_intro_spec"):
        return body_video
    try:
        from src.core import hook_intro_stage
        provided = category.hook_intro_spec(info)
        if not provided:
            return body_video
        spec, hook_text = provided[0], provided[1]
        bgm = provided[2] if len(provided) > 2 else None
        return hook_intro_stage.apply(body_video, spec, hook_text,
                                      str(Path(work_dir) / "hook_intro"), bgm=bgm)
    except Exception as e:  # noqa: BLE001
        log.warning("[hook_intro] 연결 실패 → 본문 그대로: %s", e)
        return body_video


def run_narrated(
    category_id: str,
    query: str,
    visualizer_name: str = "panzoom",
    base_dir: str = ".",
    episode: int | None = None,
) -> OutputResult:
    """narrated_wildlife 파이프라인: 종→정보→소싱→게이트→대본→동적컷→합성→TTS→단어자막→
    앰비언트 SFX→출력·QC. HUD/엔드카드/캐러셀 없음(릴스 나레이션 다큐)."""
    base = Path(base_dir)
    for d in ("assets/raw", "assets/approved", "work/clips", "work", "output"):
        (base / d).mkdir(parents=True, exist_ok=True)
    raw_dir, approved_dir = base / "assets/raw", base / "assets/approved"
    clips_dir, work_dir, out_dir = base / "work/clips", base / "work", base / "output"

    category = get_category(category_id)
    viz = get_visualizer(visualizer_name)
    log.info("[narrated] 시작: category=%s query=%r viz=%s", category_id, query, viz.name)

    subject = category.parse_input(query)
    info = category.get_info(subject)
    raw_assets = category.source_assets(info, str(raw_dir))
    if not raw_assets:
        raise PipelineError("sourcing", "수집된 에셋 없음")
    approved = license_gate.filter_assets(raw_assets, str(approved_dir))
    if not approved:
        raise PipelineError("license_gate", "통과 에셋 없음 → 제작 중단")
    asset = approved[0]
    log.info("[narrated] 게이트 통과: %s (%s)", asset.asset_path, asset.license)

    # 동적 야생다큐 컷 + 정확성 게이트
    situation = category.get_situation_wildlife(info)
    violations = category.validate_cuts(situation)
    if violations:
        raise PipelineError("situation_bank", f"정확성 규칙 위반: {violations}")

    clips = []
    for cut in situation.cuts:
        try:
            clip = viz.generate_clip(asset, cut, situation.situation_id,
                                     category.style_profile, str(clips_dir))
        except VisualizationError as e:
            raise PipelineError("visualization", str(e)) from e
        clips.append(clip)
    base_video = assembler.concat_clips(clips, str(work_dir))
    video_total = sum(c.duration_s for c in clips)
    log.info("[narrated] 합성: %s (%.0fs)", base_video, video_total)

    # 대본 → 나레이션(TTS) → 단어 자막
    script_lines = category.build_script(info)
    narration_wav, sent_timings = tts.synthesize(script_lines, str(work_dir))
    total = video_total
    subbed = base_video
    if narration_wav and sent_timings:
        ndur = tts.narration_duration(narration_wav)
        total = max(video_total, ndur + 0.6)
        if total > video_total + 0.05:
            base_video = _pad_last_frame(base_video, total, str(work_dir))
        # 자막 번인은 폰트/libass 문제로 실패해도 발행 불정지(자막 없이 진행)
        try:
            # 문장 단위 카라오케(한 문장 표시 + 단어 하이라이트) — 사용자 요청
            ass = subtitle.build_karaoke_ass(sent_timings, str(work_dir / "subs.ass"), CLIP_W, CLIP_H)
            subbed = subtitle.burn(base_video, ass, str(work_dir))
            log.info("[narrated] 나레이션 %.1fs + 문장 카라오케 자막 %d문장", ndur, len(sent_timings))
        except Exception as e:  # noqa: BLE001
            log.warning("[narrated] 자막 번인 실패 → 자막 없이 진행: %s", e)
            subbed = base_video
    else:
        log.info("[narrated] 나레이션 없음(키 없음/실패) → 앰비언트만")

    with_audio = audio.add_narration(subbed, str(work_dir), total, narration_wav,
                                     category.ambient_audio_spec())

    # 오프닝 훅 + 엔드카드 + 전환 + 임팩트 사운드 시스템(카테고리가 hook_intro_spec 제공 시 적용).
    # 미제공/전제 미충족 시 원본 그대로(발행 불정지).
    with_audio = _maybe_apply_hook_intro(category, info, with_audio, str(work_dir))

    caption = (category.build_narrated_caption(info)
               if hasattr(category, "build_narrated_caption") else category.build_caption(info))
    if hasattr(category, "attach_attribution"):
        caption = category.attach_attribution(caption, info, asset.credit_string)

    if episode is None:
        episode = category.next_episode() if hasattr(category, "next_episode") else 1
    series_title = getattr(category, "series_title", "") or category_id
    result = output.finalize(
        with_audio, info, caption, asset.credit_string, asset.license, str(out_dir), total,
        extra_meta={"category": category_id, "visualizer": viz.name, "mode": "narrated_wildlife",
                    "style_profile": "narrated_wildlife", "situation_id": situation.situation_id,
                    "script": script_lines, "series": {"title": series_title, "episode": episode}},
    )
    log.info("[narrated] 출력: %s (QC %s)", result.video_path, "통과" if result.qc_passed else "실패")
    if hasattr(category, "log_catalog"):
        category.log_catalog(episode, info)
    try:
        content_store.write_record(
            base_dir, f"{int(episode):03d}", info=info, caption=caption, asset=asset,
            visualizer=viz.name, video_file=result.video_path, series_title=series_title, scope="all",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("[narrated] 레코드 기록 실패(무시): %s", e)
    return result


def _probe_duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def run_reels(
    category_id: str,
    query: str,
    base_dir: str = ".",
    episode: int | None = None,
) -> OutputResult:
    """reels 파이프라인(현행 확정 시스템): 실제 PD 심해 '영상' → 9:16 추적 리프레임 + 틸 그레이딩
    → 일본어 나레이션(edge-tts, 훅/본문) + 카라오케 자막 → 오프닝 훅/엔드카드/전환/임팩트 사운드.
    팬줌·Veo 미사용. 실사 영상·일본어 훅 확보 실패 시 명확 중단(날조 금지)."""
    from src.core import footage, hook_intro_stage, narration_sync, reframe
    from src.core.contracts import ALLOWED_LICENSES

    base = Path(base_dir)
    for d in ("assets/raw", "work", "output"):
        (base / d).mkdir(parents=True, exist_ok=True)
    raw_dir, work_dir, out_dir = base / "assets/raw", base / "work", base / "output"
    category = get_category(category_id)
    log.info("[reels] 시작: category=%s query=%r", category_id, query)

    info = category.get_info(category.parse_input(query))
    if not hasattr(category, "hook_intro_spec"):
        raise PipelineError("reels", "카테고리가 hook_intro_spec 미제공")
    spec_t = category.hook_intro_spec(info)
    if not spec_t:
        raise PipelineError("reels", "일본어 훅 생성 불가(대표종 시드 또는 LLM 키 필요)")
    spec, hook_text, bgm = spec_t

    # 1) 실사 심해 영상 소싱 + 라이선스 게이트
    fv = footage.fetch_footage(info.scientific_name, info.common_name_en, str(raw_dir))
    if not fv:
        raise PipelineError("footage", "실사 심해 영상 미확보 → 제작 중단(AI/정지 대체 금지)")
    if (fv["license"] or "").strip().lower() not in ALLOWED_LICENSES:
        raise PipelineError("license_gate", f"영상 라이선스 차단: {fv['license']}")

    # 2) 본문 일본어 나레이션 대본 → 합성(단어 타임스탬프)
    chunks = category.reels_body_script(info) if hasattr(category, "reels_body_script") else None
    if not chunks:
        raise PipelineError("script", "본문 일본어 대본 생성 불가(시드/LLM 필요)")
    nar = narration_sync.synthesize(chunks, str(work_dir))
    if not nar.get("mp3") or not nar.get("disp"):
        raise PipelineError("tts", "나레이션 합성 실패")
    body_dur = float(nar["duration"]) + 0.6

    # 3) 9:16 추적 리프레임 + 틸 그레이딩(본문 길이)
    body_v = reframe.reframe_to_vertical(fv["path"], str(work_dir / "body_reframed.mp4"),
                                         body_dur, str(work_dir / "rf"))

    # 4) 카라오케 자막 번인(본문 — 훅 없음)
    ass = narration_sync.build_synced_ass(nar["disp"], str(work_dir / "body.ass"),
                                          hook_first=False, w=CLIP_W, h=CLIP_H)
    subbed = str(work_dir / "body_subbed.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", body_v, "-vf", f"ass={ass}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", subbed], check=True)

    # 5) 본문 나레이션 오디오 mux
    body_av = str(work_dir / "body_av.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", subbed, "-i", nar["mp3"],
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", body_av], check=True)

    # 6) 오프닝 훅 + 엔드카드 + 전환 + 임팩트 사운드 래핑
    final = hook_intro_stage.apply(body_av, spec, hook_text, str(work_dir / "hook_intro"), bgm=bgm)
    if final == body_av:
        log.warning("[reels] hook_intro 미적용(폰트/edge-tts 전제 미충족) → 본문만 발행")

    # 7) 캡션(일본어 게시글 + 한국어 참고) + 출력 (캡션 생성 실패해도 발행 불정지)
    try:
        if hasattr(category, "build_reels_caption"):
            caption = category.build_reels_caption(info, spec)   # JP 본문 + KR 참고 번역
        else:
            caption = (category.build_narrated_caption(info)
                       if hasattr(category, "build_narrated_caption") else category.build_caption(info))
            if hasattr(category, "attach_attribution"):
                caption = category.attach_attribution(caption, info, fv["credit"])
    except Exception as e:  # noqa: BLE001
        log.warning("[reels] 캡션 생성 실패 → 최소 캡션으로 발행: %s", e)
        from src.core.contracts import CaptionData
        caption = CaptionData(
            hook_text=hook_text, caption_body=info.common_name_ko,
            overlay_facts=[f"수심 {info.depth_range_m}m"],
            hashtags=[f"#{info.common_name_ko}", "#심해생물", "#深海"],
            reveal_name=f"{info.common_name_ko} ({info.common_name_en})", reveal_fact="")
    if episode is None:
        episode = category.next_episode() if hasattr(category, "next_episode") else 1
    series_title = getattr(category, "series_title", "") or category_id
    total = _probe_duration(final) or body_dur
    result = output.finalize(
        final, info, caption, f'{fv["credit"]} · Public Domain', fv["license"], str(out_dir), total,
        extra_meta={"category": category_id, "mode": "reels", "visualizer": "reels",
                    "style_profile": "deepsea_reels_jp", "footage_source": fv.get("source", ""),
                    "series": {"title": series_title, "episode": episode}},
    )
    log.info("[reels] 출력: %s (QC %s)", result.video_path, "통과" if result.qc_passed else "실패")
    if hasattr(category, "log_catalog"):
        category.log_catalog(episode, info)
    try:
        content_store.write_record(base_dir, f"{int(episode):03d}", info=info, caption=caption,
                                   asset=None, visualizer="reels", video_file=result.video_path,
                                   series_title=series_title, scope="all")
    except Exception as e:  # noqa: BLE001
        log.warning("[reels] 레코드 기록 실패(무시): %s", e)
    return result


def run(
    category_id: str,
    query: str,
    visualizer_name: str = "panzoom",
    base_dir: str = ".",
    episode: int | None = None,
    scope: str = "all",
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

    # 게시물(캐러셀) 동시 제작 — 도감형 인포그래픽 5장(관리자·발행용). 실패해도 릴스 발행 불정지.
    # 카테고리가 generate_post=False면 일시 중단(현재: 나레이션 야생다큐 전환 집중 → 릴스만).
    post = None
    post_enabled = getattr(category, "generate_post", True)
    if post_enabled and scope in ("all", "images", "caption"):
        try:
            post_pngs = carousel.build_carousel(
                info, caption, asset.credit_string, asset.asset_path,
                str(out_dir), int(episode), eco_line=eco_line,
            )
            if post_pngs:
                post = {
                    "format": "carousel-5",
                    "images": [Path(p).name for p in post_pngs],  # CI가 Release URL로 보완
                    "caption": caption.caption_body,
                    "hashtags": list(caption.hashtags or []),
                }
                log.info("[+] 게시물 캐러셀 %d장 생성", len(post_pngs))
        except Exception as e:  # noqa: BLE001 — 게시물 실패해도 릴스는 유효
            log.warning("게시물(캐러셀) 생성 실패(무시): %s", e)

    # 콘텐츠 영구 레코드(관리자 페이지용): content/<id>.json. 미디어 URL은 CI가 Release 후 패치.
    try:
        content_store.write_record(
            base_dir, f"{int(episode):03d}", info=info, caption=caption, asset=asset,
            visualizer=viz.name, video_file=result.video_path, series_title=series_title,
            scope=scope, post=post,
        )
    except Exception as e:  # noqa: BLE001 — 레코드 실패해도 발행물은 유효
        log.warning("콘텐츠 레코드 기록 실패(무시): %s", e)
    return result
