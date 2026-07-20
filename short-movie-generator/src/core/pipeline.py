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
import os
import shutil
import subprocess
from pathlib import Path

from src.core import assembler, audio, carousel, content_store, endcard, htmlhud, hud, license_gate, output, overlay, subtitle, tts  # noqa: F401
from src.core.visualization.base import CLIP_H, CLIP_W
from src.core.contracts import OutputResult, PipelineError
from src.core.visualization import VisualizationError, get_visualizer
from src.registry import get_category

log = logging.getLogger(__name__)

WATERMARK = "DEEP DIVE LOG"  # 브랜드명 [TBD] — 확정 시 교체
# 쇼츠(9:16) 본문 자막 크기 배율 — 세로 영상 가독성 위해 크게. 1.8은 한 줄에 글자가 너무 적어
# 분절이 잦았음 → 1.5로 낮춰 한 문절이 한 줄에 잘 들어오게(요청 반영). 조정 시 이 값만 바꾼다.
REELS_SUB_SCALE = 1.5


def _verify_subject_or_raise(category, info) -> None:
    """★제작 직전 카테고리 적합성 최종 게이트(공용).
    카테고리가 verify_subject(info)를 제공하면 호출한다. 부적합이면 PipelineError를 던져
    영상이 렌더되기 전에 제작을 중단한다(표층 종·가짜 수심 발행 원천 차단). 미제공 카테고리는 무동작."""
    fn = getattr(category, "verify_subject", None)
    if callable(fn):
        fn(info)


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
    _verify_subject_or_raise(category, info)
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
        # 콘텐츠 id는 전 카테고리 공용 번호(카테고리별 회차 번호 충돌·덮어쓰기 방지)
        episode = content_store.next_global_id(base_dir)
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
            visualizer=viz.name, video_file=result.video_path, series_title=series_title,
            scope="all", category=category_id,
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


# ★쇼츠 길이 규칙(기획서: 40초 내외). 본문 나레이션이 길면 총 길이가 1분을 넘는다(소싱 종 LLM 본문이
#   길게 나오던 사고). 시드 종은 27~29초(총 30~39초)로 이미 규칙 내라 안 건드리고, 과길이 본문만
#   글자수 예산으로 컷한다. 실측 ja-JP edge-tts ≈ 5.4자/초 → 165자 ≈ 30초 본문 → 총 ≈ 40초.
_MAX_BODY_CHARS = 165
_MIN_BODY_CHUNKS = 12


def _cap_body_chunks(chunks: list[str], max_chars: int = _MAX_BODY_CHARS,
                     min_chunks: int = _MIN_BODY_CHUNKS) -> list[str]:
    """본문 절 리스트를 글자수 예산 내로 자른다(온전한 절 단위). 최소 절 수는 보장해 너무 짧아지지 않게.
    마지막 원본 절(마무리 비트)을 가능하면 포함해 끝맺음이 살아있게 한다."""
    total = sum(len(c) for c in chunks)
    if total <= max_chars or len(chunks) <= min_chunks:
        return chunks
    out, used = [], 0
    for c in chunks:
        if used + len(c) > max_chars and len(out) >= min_chunks:
            break
        out.append(c)
        used += len(c)
    # 끝맺음 절 보존: 마지막 원본 절이 빠졌으면 마지막 자리를 그것으로 교체
    if chunks[-1] not in out:
        out[-1] = chunks[-1]
    return out


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

    # auto* 는 '실사 영상 보유 종'에서만 선택(영상 없는 종으로 인한 실패 방지)
    # ★후보 순회 폴백(무한 실패 방지 핵심): 첫 후보의 소스가 정지 영상 등으로 게이트에 걸리면
    #   제작이 실패하고, 실패한 종은 '미제작'으로 남아 다음 실행도 같은 종을 고르는 교착이 실존
    #   (umbellula 정지 소스로 auto 제작이 전부 실패하던 사고). → 후보 목록을 순서대로 시도해
    #   실사 확보에 성공하는 첫 종으로 제작한다(게이트 기준은 그대로, 대상만 다음 후보로).
    q = (query or "").strip().lower()
    fv = None
    if q.startswith("auto") and hasattr(category, "pick_footage_species"):
        cands = (category.footage_candidates()
                 if hasattr(category, "footage_candidates")
                 else [category.pick_footage_species()])
        # ★풀 소진 자동 보충(운영자 확정 · auto 교착 해소): 미제작 시드가 0이면, 이미 소싱된 승인대기
        #   후보 중 '제작 가능·적합'한 첫 종을 자동 승격해 계속 돈다(중복은 여전히 금지 — 승격은 미제작만).
        #   승격 가능 후보도 없을 때만 명확히 중단(소싱하기 안내).
        if not cands and hasattr(category, "auto_replenish"):
            try:
                rk = category.auto_replenish()
                if rk:
                    cands = [rk]
                    log.info("[reels] auto 풀 소진 → 후보 자동 승격 사용: %s", rk)
            except Exception as e:  # noqa: BLE001
                log.warning("[reels] auto 자동 승격 실패: %s", e)
        if not cands:
            raise PipelineError("input",
                                "제작 가능한 미제작 대상이 없습니다 — 관리자 페이지에서 '소싱하기'로 새 대상을 확보하세요.")
        subject = info = None
        for cand in cands:
            ci = category.get_info(cand)
            cf = footage.fetch_footage(ci.scientific_name, ci.common_name_en, str(raw_dir))
            if cf:
                subject, info, fv = cand, ci, cf
                log.info("[reels] auto → 실사영상 보유 대상 선택: %s", subject)
                break
            log.warning("[reels] auto 후보 스킵(실사 미확보/정지 소스): %s", cand)
        if not fv:
            raise PipelineError("footage", "auto 후보 전원 실사 영상 미확보 → 제작 중단(날조 금지)")
    else:
        subject = category.parse_input(query)
        info = category.get_info(subject)
    _verify_subject_or_raise(category, info)   # ★제작 직전 카테고리 적합성 최종 게이트
    if not hasattr(category, "hook_intro_spec"):
        raise PipelineError("reels", "카테고리가 hook_intro_spec 미제공")
    spec_t = category.hook_intro_spec(info)
    if not spec_t:
        raise PipelineError("reels", "일본어 훅 생성 불가(대표종 시드 또는 LLM 키 필요)")
    spec, hook_text, bgm = spec_t

    # 1) 실사 심해 영상 소싱 + 라이선스 게이트 (auto는 위 후보 순회에서 이미 확보)
    if fv is None:
        fv = footage.fetch_footage(info.scientific_name, info.common_name_en, str(raw_dir))
    if not fv:
        raise PipelineError("footage", "실사 심해 영상 미확보 → 제작 중단(AI/정지 대체 금지)")
    if (fv["license"] or "").strip().lower() not in ALLOWED_LICENSES:
        raise PipelineError("license_gate", f"영상 라이선스 차단: {fv['license']}")

    # 2) 본문 일본어 나레이션 대본 → 합성(단어 타임스탬프)
    # ★침몰선 다큐(wreck_doc): 그 배 전용 대본(취항→사고→제원→잔해)을 dossier로 생성 → 제네릭 대체.
    if fv.get("doc"):
        from src.categories.shipwreck import dossier as _dsr
        chunks = _dsr.wreck_body_jp(fv["dossier"])
    else:
        chunks = category.reels_body_script(info) if hasattr(category, "reels_body_script") else None
    if not chunks:
        raise PipelineError("script", "본문 일본어 대본 생성 불가(시드/LLM 필요)")
    chunks = _cap_body_chunks(chunks)   # ★길이 상한(쇼츠 40초 규칙): 과길이 본문을 ~30초로 컷
    nar = narration_sync.synthesize(chunks, str(work_dir))
    if not nar.get("mp3") or not nar.get("disp"):
        raise PipelineError("tts", "나레이션 합성 실패")
    body_dur = float(nar["duration"]) + 0.6

    cutaway_credits: list[str] = []
    doc_map_start = None      # 난파선 지도 컷 시작 시각(있으면) — 지도 SFX 믹스 타이밍
    if fv.get("doc"):
        # ★침몰선 다큐 분기: 여러 이미지 시간순 시퀀스(취항→초상→사고→잔해)를 body_dur 길이로 합성.
        #   WQ/추적리프레임/컷어웨이를 우회한다(소스가 이미 9:16 순서보존 시퀀스 · 워터마크 없음 ·
        #   신문 스캔 등 정당한 텍스트를 delogo하면 안 됨 · 순서를 뒤섞으면 스토리가 깨짐).
        from src.categories.shipwreck import dossier as _dsr
        doss = fv["dossier"]
        seq = _dsr.ordered_beat_images(doss, max_per_beat=2)
        # ★침몰 위치 지도 컷(운영자 확정): 위키 문서 좌표가 있으면 우리 세계지도로 침몰 해역을 락온한
        #   9:16 컷을 만들어 '사고·침몰' 구간(첫 sinking 컷 앞, 없으면 첫 wreck 앞)에 시간순 삽입한다.
        #   좌표는 문서화된 사실 → '임의 좌표 금지' 대상 아님. 좌표 없으면 생략(날조 안 함).
        if doss.get("sink_lat") is not None and doss.get("sink_lon") is not None:
            try:
                from src.core import reels_stinger as _rs
                mc = _rs.build_map_cut(doss["sink_lat"], doss["sink_lon"],
                                       doss.get("sink_region_jp"), doss.get("sink_region_en"),
                                       str(work_dir / "wreck_map.mp4"), str(work_dir / "wmap"))
                if mc:
                    entry = {"video": mc["path"], "beat": "map",
                             "credit": "地図: Natural Earth", "license": "public-domain"}
                    ins = next((k for k, s in enumerate(seq) if s.get("beat") == "sinking"), None)
                    if ins is None:
                        ins = next((k for k, s in enumerate(seq) if s.get("beat") == "wreck"), len(seq))
                    seq.insert(ins, entry)
                    log.info("[reels] 침몰 위치 지도 컷 삽입(%s)", doss.get("sink_region_en"))
            except Exception as e:  # noqa: BLE001
                log.warning("[reels] 지도 컷 생략(오류): %s", e)
        card = _dsr.render_spec_card(doss, str(work_dir / "spec_card.png"))
        has_portrait = any(s.get("beat") == "portrait" for s in seq)
        overlays = {("portrait" if has_portrait else "afloat"): card} if card else {}
        docv = footage.build_wreck_documentary(
            seq, str(work_dir / "wdoc"), target_dur=body_dur + 1.0,
            key=info.scientific_name, overlays=overlays)
        if not docv:
            raise PipelineError("footage", "난파선 다큐 시퀀스 합성 실패")
        doc_map_start = docv.get("map_start")   # 지도 컷 시작 시각(SFX 믹스용)
        fv = {**fv, "path": docv["path"], "credit": docv.get("credit", fv.get("credit", "")),
              "license": docv.get("license", fv.get("license", "")), "logo_box": None}
        body_v = str(work_dir / "body_reframed.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", docv["path"],
                        "-t", f"{body_dur:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "19", "-an", body_v], check=True)
    elif fv.get("photo_doc"):
        # ★실사 사진 다큐(영상 미확보 생물 · 운영자 확정 "영상 우선·없으면 이미지"): 같은 종의 실사
        #   여러 장을 body_dur 길이의 켄번즈 9:16 시퀀스로 합성(난파선과 동일 엔진). 나레이션·자막·
        #   오프닝 훅·엔드카드·수심 스팅어는 생물 기본 경로 그대로(캡션·대본도 생물 기본). WQ/추적
        #   리프레임/컷어웨이는 우회한다(이미 9:16 시퀀스 · 워터마크 없음).
        docv = footage.build_wreck_documentary(
            fv["photos"], str(work_dir / "pdoc"), target_dur=body_dur + 1.0,
            key=info.scientific_name)
        if not docv:
            raise PipelineError("footage", "실사 사진 다큐 시퀀스 합성 실패")
        fv = {**fv, "path": docv["path"], "credit": docv.get("credit", fv.get("credit", "")),
              "license": docv.get("license", fv.get("license", "")), "logo_box": None}
        body_v = str(work_dir / "body_reframed.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", docv["path"],
                        "-t", f"{body_dur:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-crf", "19", "-an", body_v], check=True)
    else:
        # 2.5) ★워터마크 QC(하드룰 #9): 원본을 1초 간격 OCR 스캔 → 크레딧 슬레이트 초는 회피하고
        #      탐지된 로고/URL은 delogo한 '깨끗한 소스'를 먼저 만든다. 이후 모든 단계(리프레임·
        #      오프닝 배경·엔드카드 피사체)는 이 깨끗한 소스만 쓴다(좌표 하드코딩 logo_box 의존 폐기).
        from src.core import watermark_qc as WQ
        wm = WQ.plan(fv["path"], 0.0, body_dur + 10,
                     extra_boxes=[fv["logo_box"]] if fv.get("logo_box") else None)
        clean = str(work_dir / "footage_clean.mp4")
        chain = WQ.delogo_chain(wm["boxes"], 1280, 720)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{wm['start']:.2f}",
                        "-i", fv["path"], "-t", f"{body_dur + 10:.2f}",
                        "-vf", "scale=1280:720,setsar=1" + (("," + chain) if chain else ""),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-an", clean],
                       check=True)
        fv = {**fv, "path": clean, "logo_box": None}

        # 3) 9:16 추적 리프레임 + 틸 그레이딩(본문 길이)
        body_v = reframe.reframe_to_vertical(fv["path"], str(work_dir / "body_reframed.mp4"),
                                             body_dur, str(work_dir / "rf"),
                                             logo_box=None,
                                             wide=bool(getattr(category, "reframe_wide", False)))

        # 3.5) ★본문 사진 컷어웨이(반복 피로 완화): 소스 영상이 짧아 반복될 때, 같은 대상 고해상 사진
        #      1~2컷을 본문 중반에 짧게 오버레이(디졸브)한다. 자막 번인 '전'에 넣어 자막·오디오는 그대로
        #      위에 얹혀 타이밍·자막 연속성이 보존된다. 사진 없거나 본문이 길면 생략(발행 불정지).
        try:
            src_dur = _probe_duration(fv["path"]) or 0.0
            if src_dur and src_dur < body_dur * 0.9:   # 소스가 본문보다 짧아 반복되는 경우에만
                cuts = footage.fetch_cutaway_photos(
                    info.scientific_name, info.common_name_en, str(raw_dir), n=2)
                if cuts:
                    body_v2 = footage.insert_photo_cutaways(
                        body_v, cuts, str(work_dir / "body_cutaways.mp4"), body_dur,
                        key=info.scientific_name)
                    if body_v2 != body_v:
                        body_v = body_v2
                        cutaway_credits = [c["credit"] for c in cuts if c.get("credit")]
        except Exception as e:  # noqa: BLE001
            log.warning("[reels] 컷어웨이 생략(오류): %s", e)

    # 4) 카라오케 자막 번인(본문 — 훅 없음)
    ass = narration_sync.build_synced_ass(nar["disp"], str(work_dir / "body.ass"),
                                          hook_first=False, w=CLIP_W, h=CLIP_H,
                                          sub_scale=REELS_SUB_SCALE)
    subbed = str(work_dir / "body_subbed.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", body_v, "-vf", f"ass={ass}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", subbed], check=True)

    # 5) 본문 나레이션 오디오 mux
    body_av = str(work_dir / "body_av.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", subbed, "-i", nar["mp3"],
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", body_av], check=True)

    # 5.6) ★난파선 지도 컷 효과음(운영자 확정 · 무음 지적): 다큐 본문은 무음이라 지도 컷도 무음으로
    #      넣었더니 '지도 줌업' 순간에 소리가 하나도 안 났다 → 지도 컷 시작(스캔)·줌인(락온) 타이밍에
    #      scan/lockon SFX를 나레이션 위에 믹스한다(나레이션은 그대로 유지). 실패해도 발행 불정지.
    if fv.get("doc") and doc_map_start is not None:
        try:
            from src.core.longform import sfx as _sfx
            sd = _sfx.gen_all(str(work_dir / "mapsfx"))
            def _ms(t):  # noqa: E306
                return max(0, int(t * 1000))
            scan_at, lock_at = doc_map_start + 0.1, doc_map_start + 1.2   # 스캔 스윕 / 줌인 락온
            mixed = str(work_dir / "body_mapsfx.mp4")
            r = subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-i", body_av,
                 "-i", sd["scan"], "-i", sd["lockon"], "-filter_complex",
                 # ★볼륨 50%로 축소(운영자 확정): 지도 SFX가 나레이션·자막 낭독을 덮지 않도록
                 #   (scan 1.2→0.6, lockon 1.35→0.68). 나레이션이 항상 위로 들리게.
                 (f"[1:a]adelay={_ms(scan_at)}|{_ms(scan_at)},volume=0.6[sc];"
                  f"[2:a]adelay={_ms(lock_at)}|{_ms(lock_at)},volume=0.68[lk];"
                  f"[0:a][sc][lk]amix=inputs=3:duration=first:normalize=0,alimiter=limit=0.95[a]"),
                 "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", mixed],
                timeout=180)
            if r.returncode == 0 and Path(mixed).exists() and Path(mixed).stat().st_size > 10_000:
                body_av = mixed
                log.info("[reels] 지도 컷 SFX 믹스(scan@%.1fs·lockon@%.1fs)", scan_at, lock_at)
        except Exception as e:  # noqa: BLE001
            log.warning("[reels] 지도 SFX 믹스 생략(오류): %s", e)

    # 5.5) ★오프닝 지도·수심 하강 스팅어(운영자 확정): 훅 뒤에 '지도→해역 락온→실제 수심 하강'을
    #      ~2.3초 붙인다. 본문 앞에 결합하면 최종 순서가 [훅][스팅어][본문][엔드카드]가 된다.
    #      실패해도 발행 불정지(스팅어 없이 진행). 수심은 종 실제 서식수심(날조 아님).
    #      ★난파선 다큐(doc)는 제외: '생식해역·수심 하강'은 생물용 프레이밍이라 부적절하고,
    #        침몰 위치는 본문 안 '지도 컷'(위 doc 분기)이 사고 구간에 이미 정확히 보여준다.
    if not fv.get("doc"):
        try:
            from src.core import reels_stinger
            st = reels_stinger.build_stinger(info, str(work_dir / "stinger.mp4"),
                                             str(work_dir / "stinger"))
            if st:
                combined = str(work_dir / "body_with_stinger.mp4")
                # ★전환 효과음: 지도·수심 표시 → 본 영상 경계(=스팅어 길이)에 다이브 후시 SFX
                if reels_stinger.prepend_to_body(st["path"], body_av, combined,
                                                 boundary_s=st.get("duration"),
                                                 work_dir=str(work_dir / "trsfx")):
                    body_av = combined
                    log.info("[reels] 오프닝 하강 스팅어 결합(%.1fs) + 전환 SFX", st["duration"])
        except Exception as e:  # noqa: BLE001
            log.warning("[reels] 스팅어 결합 생략(오류): %s", e)

    # 6) 오프닝 훅 + 엔드카드 + 전환 + 임팩트 사운드 래핑
    # ★고화소 히어로 사진(있으면): 정지 화면인 오프닝·엔드카드 배경을 영상 프레임 대신 이 사진으로
    #   만든다(훨씬 선명). 미확보 시 기존 영상 프레임으로 자동 폴백(발행 불정지). 같은 대상의 사진만.
    hero = None
    try:
        if (fv.get("doc") or fv.get("photo_doc")) and fv.get("hero_url"):
            # 다큐/사진다큐: 첫 대표 사진을 오프닝·엔드카드 배경으로(선명한 원본)
            hp = raw_dir / "doc_hero.jpg"
            if footage._download(fv["hero_url"], hp):
                hero = {"path": str(hp)}
        else:
            hero = footage.fetch_hero_photo(info.scientific_name, info.common_name_en, str(raw_dir))
    except Exception as e:  # noqa: BLE001
        log.warning("[reels] 히어로 사진 확보 생략(오류): %s", e)
    # 배경 소스 분리(재발 방지): 오프닝 배경=자막 번인 '전' 클린 리프레임(body_v) →
    # 본문 자막 미리 노출 차단 / 엔드카드 피사체=크롭·줌 '전' 원본 광각(fv.path) → 과확대 차단
    yt_thumb = str(work_dir / "yt_thumb.jpg")   # ★유튜브 썸네일: 전체 타이틀 노출 오프닝 프레임
    final = hook_intro_stage.apply(body_av, spec, hook_text, str(work_dir / "hook_intro"), bgm=bgm,
                                   open_bg_video=body_v, subject_video=fv["path"],
                                   logo_box=fv.get("logo_box"),
                                   hero_image=(hero["path"] if hero else None),
                                   thumb_out=yt_thumb)
    # ★재발방지 하드 게이트(기획서 규칙: 모든 영상에 오프닝 훅+엔드카드 필수).
    # 폰트는 이제 항상 폴백 해석되므로 apply()가 본문을 그대로 돌려주는 건 '진짜 실패'뿐 →
    # 조용히 발행하지 않고 큰 오류로 멈춰 CI를 빨간불로 만든다(스펙 위반 영상 발행 원천 차단).
    # 로컬/특수상황은 SHORTS_ALLOW_BODY_ONLY=1 로만 우회 허용.
    if final == body_av:
        from src.core import hook_intro as _hi
        miss = _hi.missing_fonts()
        msg = ("[reels] 오프닝 훅+엔드카드 래핑 실패 → 스펙 위반. "
               + (f"필수 폰트 누락: {', '.join(miss)}" if miss else "렌더 파이프라인 오류(로그 확인)"))
        if os.environ.get("SHORTS_ALLOW_BODY_ONLY") == "1":
            log.warning(msg + " (SHORTS_ALLOW_BODY_ONLY=1 → 본문만 발행 허용)")
        else:
            raise PipelineError("hook_intro", msg)

    # 6.5) 최종 전체영상 재검증은 제거(속도). 소스는 이미 2.5)에서 세척(plan+delogo)됐고,
    #      완성본 수백 프레임 OCR이 CI에서 hang의 주원인이었다. 운영자 육안 확인으로 갈음.

    # 7) 캡션(일본어 게시글 + 한국어 참고) + 출력 (캡션 생성 실패해도 발행 불정지)
    try:
        if fv.get("doc"):
            # ★침몰선 다큐 전용 캡션(운영자 확정): 생물 관점(生息·서식 등) 배제 → 배의 역사·침몰
            #   경위·수심·해역·수중 잔해 중심의 스토리 캡션 + 침몰선 해시태그(생물 태그 아님).
            from src.categories.shipwreck import dossier as _dsr
            from src.core.contracts import CaptionData
            c = _dsr.wreck_caption(fv["dossier"], depth_m=info.depth_range_m or "")
            dep = _dsr._depth_num(info.depth_range_m or "")
            caption = CaptionData(
                hook_text=spec.hook_line1 + spec.hook_line2,
                overlay_facts=([f"水深 {dep} m"] if dep else []),
                caption_body=c["jp"], hashtags=c["tags"],
                reveal_name=fv["dossier"].get("display", info.scientific_name), reveal_fact="",
                caption_ko=c["ko"], hook_ko="", hashtags_ko=list(c["tags_ko"]),
                yt_title=c["yt_title"], yt_title_ko=c["yt_title_ko"])
        elif hasattr(category, "build_reels_caption"):
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
    # ★사진 크레딧(CC-BY 저작자 표기 의무): 오프닝·엔드카드(히어로)·본문 컷어웨이에 쓴 사진 출처를 캡션에.
    try:
        photo_credits = []
        if hero and hero.get("credit"):
            photo_credits.append(hero["credit"])
        photo_credits += cutaway_credits
        # 중복 제거(순서 유지)
        seen = set(); photo_credits = [c for c in photo_credits if not (c in seen or seen.add(c))]
        if photo_credits and getattr(caption, "caption_body", None):
            for cr in photo_credits:
                if cr not in caption.caption_body:
                    caption.caption_body = f"{caption.caption_body}\n写真: {cr}"
    except Exception:  # noqa: BLE001
        pass
    if episode is None:
        # 콘텐츠 id는 전 카테고리 공용 번호(카테고리별 회차 번호 충돌·덮어쓰기 방지)
        episode = content_store.next_global_id(base_dir)
    series_title = getattr(category, "series_title", "") or category_id
    total = _probe_duration(final) or body_dur
    result = output.finalize(
        final, info, caption, f'{fv["credit"]} · Public Domain', fv["license"], str(out_dir), total,
        extra_meta={"category": category_id, "mode": "reels", "visualizer": "reels",
                    "style_profile": "deepsea_reels_jp", "footage_source": fv.get("source", ""),
                    "series": {"title": series_title, "episode": episode}},
    )
    log.info("[reels] 출력: %s (QC %s)", result.video_path, "통과" if result.qc_passed else "실패")
    # ★유튜브 썸네일(전체 타이틀 노출 오프닝 프레임)을 최종 영상 옆에 둔다 → 워크플로가 Release 업로드.
    try:
        if Path(yt_thumb).exists():
            shutil.copy2(yt_thumb, str(Path(result.video_path).with_name("yt_thumb.jpg")))
    except Exception as e:  # noqa: BLE001
        log.warning("[reels] 유튜브 썸네일 배치 생략: %s", e)
    if hasattr(category, "log_catalog"):
        category.log_catalog(episode, info)
    try:
        content_store.write_record(base_dir, f"{int(episode):03d}", info=info, caption=caption,
                                   asset=None, visualizer="reels", video_file=result.video_path,
                                   series_title=series_title, scope="all", category=category_id)
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
    _verify_subject_or_raise(category, info)   # ★제작 직전 카테고리 적합성 최종 게이트
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
            scope=scope, post=post, category=category_id,
        )
    except Exception as e:  # noqa: BLE001 — 레코드 실패해도 발행물은 유효
        log.warning("콘텐츠 레코드 기록 실패(무시): %s", e)
    return result
