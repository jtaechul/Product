"""M8. 오케스트레이터 — M2(CSV큐/쿠팡API) → M3(대본) → M4(TTS) → (M5) → M6(렌더) → M7(업로드).

단계별 산출물을 data/jobs/{job_id}/에 저장하고, 실패 시 해당 단계에서 중단 +
Artifacts 업로드(디버깅용) + 텔레그램 알림(설정 시). (스펙 §M8)

실행: python -m src.pipeline --row auto --privacy private
- --soft: cron(스케줄) 모드 — 전제조건(큐/키) 미비 시 빨간 X 대신 안내 후 정상 종료
- --script-file: M3 우회(대본 JSON 직접 주입) — Anthropic 키 없이 E2E 테스트용
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from pathlib import Path

import requests
import yaml

from src import notify
from src.audio import tts
from src.product import manual_queue
from src.product.assets import fetch_product_videos
from src.product.enrich import enrich_product
from src.script.generate import (
    DISCLOSURE, generate_script, have_script_key, missing_key_hint, script_provider)
from src.upload import youtube
from src.video.qa import run_qa
from src.video import imagesource
from src.video.render import build_poster, render_video

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description="쿠팡 쇼츠 전체 파이프라인 (M2→M7)")
    p.add_argument("--row", default="auto", help="products_manual.csv 행 번호(1~) 또는 auto")
    p.add_argument("--privacy", default=None, help="private|unlisted|public (기본: settings)")
    p.add_argument("--provider", default=None, help="TTS 프로바이더 오버라이드")
    p.add_argument("--job-id", default=None)
    p.add_argument("--script-file", default=None, help="M3 우회용 대본 JSON 경로")
    p.add_argument("--soft", action="store_true", help="전제조건 미비 시 정상 종료(cron용)")
    p.add_argument("--no-narration", action="store_true",
                   help="나레이션(TTS) 없이 렌더 — 영상/이미지 튜닝용(대본 길이로 자막 타이밍 합성)")
    p.add_argument("--candidates", action="store_true",
                   help="렌더 대신 라인별 후보 이미지만 생성(관리자 선택기용) — candidates.json 작성")
    p.add_argument("--line", type=int, default=None,
                   help="--candidates와 함께: 그 라인(0-base) 후보만 재생성해 기존 매니페스트에 병합('다시 찾기' 라인별)")
    p.add_argument("--plan", action="store_true",
                   help="기획+스토리보드+대본만 생성(승인 단계용) — data/plans/{row_hash}.json 작성, 이미지·제작 생략")
    p.add_argument("--no-upload", action="store_true",
                   help="제작(렌더+릴리스)만 하고 유튜브 업로드는 하지 않음 — 검수 단계용(새 흐름 기본)")
    p.add_argument("--upload", action="store_true",
                   help="이미 제작된 영상(릴리스 shorts-run)을 유튜브에 업로드 — 검수 통과 후 '올리기'용")
    p.add_argument("--regen", default=None,
                   help="기획의 특정 항목만 재생성해 즉시 교체 (title|headline|description|hashtags)")
    p.add_argument("--regen-line", type=int, default=None,
                   help="대본 한 라인의 문구(text)만 재생성해 즉시 교체 (라인 번호 0~)")
    args = p.parse_args()

    settings = yaml.safe_load((PROJECT_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    job_id = args.job_id or time.strftime("job_%Y%m%d_%H%M%S")
    job_dir = PROJECT_ROOT / "data" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    _print_key_detection()

    try:
        return _run(args, settings, job_id, job_dir)
    except manual_queue.QueueEmpty as e:
        msg = f"[pipeline] 상품 큐 문제: {e}"
        if args.soft:
            print(msg + " → cron 모드라 정상 종료")
            return 0
        print(f"::error::{msg}")
        return 2
    except Exception as e:
        print(f"::error::[pipeline] 실패({type(e).__name__}): {e}")
        traceback.print_exc()
        notify.send(f"[쿠팡쇼츠] 파이프라인 실패 (job={job_id})\n{type(e).__name__}: {str(e)[:500]}")
        return 2


def _run(args, settings: dict, job_id: str, job_dir: Path) -> int:
    # cron(soft) 모드는 업로드까지 가능할 때만 제작한다. 업로드 미설정 상태로 매일 돌면
    # 같은 상품을 반복 제작해 TTS·대본 크레딧만 소모하므로(큐는 업로드 성공 시에만 소진)
    # 조용히 종료한다. 수동 실행(dispatch/request)은 영향 없음 — Artifacts 검수용으로 동작.
    if args.soft and not youtube.is_configured():
        print(f"[pipeline] cron 모드: 업로드 미설정({youtube.missing_hint()}) "
              "→ 크레딧 절약을 위해 제작 없이 정상 종료")
        return 0

    # ---- M2: 상품 확보 (기본: 수동 CSV 큐. 쿠팡 API는 키 승인 후 Phase 2에서 전환)
    product = manual_queue.pick(args.row)
    # ---- M2.5: 링크만 등록된 상품은 캡처(data/notes)로 이름·가격·특징·상품사진 자동 확보
    product = enrich_product(product, settings, job_dir)
    _persist_product_meta(product, settings)   # 이름 + 스토어 한줄소개를 관리자 표시용으로 기록
    (job_dir / "product.json").write_text(json.dumps(product, ensure_ascii=False, indent=1), encoding="utf-8")
    _p = int(product.get("price") or 0)
    print(f"[pipeline] M2 상품: {product['name']} ({f'{_p:,}원' if _p > 0 else '가격 미확인'})")

    # ---- 라인 문구 재생성 모드(--regen-line): 대본 한 줄의 text만 새로 만들어 즉시 교체
    if args.regen_line is not None:
        return _regen_line(product, args.regen_line, settings, PROJECT_ROOT)
    # ---- 검수 재생성 모드(--regen): 기획의 특정 항목만 새로 만들어 즉시 교체
    if args.regen:
        return _regen_field(product, args.regen, settings, PROJECT_ROOT)
    # ---- 업로드 모드(--upload): 이미 제작된 영상(릴리스)을 찾아 유튜브 업로드 ('올리기')
    if args.upload:
        return _upload_existing(product, settings, job_dir, PROJECT_ROOT, args.privacy)

    # ---- M3: 대본 (기획 승인 흐름)
    #   --plan          : 항상 새로 생성 → data/plans/{hash}.json 저장 후 종료(승인 대기)
    #   그 외(candidates/produce) : 승인된 기획(data/plans/{hash}.json)이 있으면 그걸 그대로 사용
    #                              (운영자가 확정한 대본을 재생성하지 않는다). 없으면 즉석 생성(하위호환).
    from src.script.sanitize import product_avoid_terms, sanitize_script
    avoid_terms = product_avoid_terms(product)   # 브랜드·정식명 → 대사·자막에서 제거(승인된 옛 기획 포함)
    plan_path = PROJECT_ROOT / "data" / "plans" / f"{product['_row_hash']}.json"
    # ---- 차별점·작동방식(2026-07-17): 상품 자료에서 3안 추출 → ⭐ 선택 게이트(사용자 확정) —
    #      기획(plan) 모드는 운영자가 3안 중 방향을 고르기 전에는 대본을 만들지 않고 여기서 멈춘다.
    #      (선택은 관리자 기획 탭 → '이 선택으로 기획·대본 만들기'가 plan을 다시 돌린다.)
    #      ⚠️ 게이트는 '새 대본이 만들어지는 모든 모드'에 적용한다(plan만 걸면 candidates/produce의
    #      즉석 생성이 우회함 — 2026-07-17 실사고: 등록→candidates가 3안 선택 없이 대본을 만들어버림).
    will_generate = bool((args.plan or not plan_path.exists()) and not args.script_file)
    try:
        from src.product import mechanism
        mech_txt, need_choice = mechanism.prepare(
            product, settings, PROJECT_ROOT, extract=will_generate, gate=will_generate)
    except Exception as e:
        print(f"[mech] 차별점 준비 실패({type(e).__name__}: {e}) — 기존 흐름으로 계속")
        mech_txt, need_choice = None, False
    if need_choice and will_generate:
        print("[mech] 차별점 3안 준비 완료 — 운영자 선택 대기(대본 생성 전 중단)")
        notify.send(
            f"[미래마켓] 기획 방향(차별점) 3안 준비 완료 — {product['name']}\n"
            f"관리자 기획 탭에서 하나를 고르거나 직접 적으면, 그 방향으로 대본을 씁니다.\n"
            f"https://shorts-admin.jtaechul.workers.dev")
        return 0
    if mech_txt:
        product["차별점_작동방식"] = mech_txt   # generate_script의 상품 JSON에 그대로 노출됨
    if args.script_file:
        script = json.loads(Path(args.script_file).read_text(encoding="utf-8"))
        script = sanitize_script(script, strict_length=False, avoid_terms=avoid_terms)
        print("[pipeline] M3 우회: script-file 사용")
    elif plan_path.exists() and not args.plan:
        script = sanitize_script(json.loads(plan_path.read_text(encoding="utf-8")),
                                 strict_length=False, avoid_terms=avoid_terms)
        print(f"[pipeline] M3: 승인된 기획+대본 사용 (data/plans/{product['_row_hash']}.json)")
    else:
        if not have_script_key(settings):
            msg = missing_key_hint(settings) + " (등록 전에는 --script-file로만 실행 가능)"
            if args.soft:
                print(f"[pipeline] {msg} → 정상 종료")
                return 0
            raise RuntimeError(msg)
        print(f"[pipeline] M3 대본 프로바이더: {script_provider(settings)}")
        script = generate_script(product, settings)
    # §3.1 고지문·링크는 항상 코드로 강제 (기획 로드 경로 포함) — 실제 등록도 upload가 같은 함수로 재생성
    from src.upload.youtube import build_pinned_comment
    script["pinned_comment"] = build_pinned_comment(product, settings)
    (job_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = script["lines"]
    text = "\n".join(l["text"] for l in lines)

    # ---- 기획 생성 모드(--plan): 기획+스토리보드+대본만 만들고 승인 대기 (이미지·제작 생략)
    if args.plan:
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[pipeline] 기획+대본 생성 완료 → data/plans/{product['_row_hash']}.json (승인 대기)")
        notify.send(
            f"[쿠팡쇼츠] 기획·대본 완성 — {product['name']}\n"
            f"제목: {script.get('title', '')}\n"
            f"다음: 관리자 '기획' 탭에서 검토 후 '이미지 찾기'로 승인하세요.\n"
            f"https://shorts-admin.jtaechul.workers.dev")
        return 0

    # ---- 후보 이미지 생성 모드(#2 관리자 선택기용): TTS·렌더 없이 라인별 후보 이미지만 만든다.
    if args.candidates:
        # 개편(2026-07-15): '상품 기획하기'가 곧바로 candidates를 돌린다. 이때 이 대본을 data/plans에
        # 저장해 제작(produce)이 같은 대본을 재사용하게 한다(대본 불일치·이미지 어긋남 방지).
        if not plan_path.exists():
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[pipeline] 후보용 대본 저장 → data/plans/{product['_row_hash']}.json (제작에서 재사용)")
        _pimgs = list(product.get("hero_images") or [])
        _pimgs += _download_images(product.get("image_urls") or [], job_dir)
        # 상세컷(2026-07-17): PDF 기능 설명 구간 크롭을 상품 라인 후보로 추가 — 선택폭 확대
        try:
            from src.product.enrich import harvest_detail_images
            detail_imgs = harvest_detail_images(product["_row_hash"], job_dir / "detail")
        except Exception as e:
            print(f"[pipeline] 상세컷 추출 실패({type(e).__name__}: {e}) — 대표컷만 사용")
            detail_imgs = []
        # 라인별 '다시 찾기'(--line): 그 라인만 재생성 → 기존 매니페스트에 병합(다른 라인 이미지는 그대로).
        only_line = args.line if (args.line is not None and args.line >= 0) else None
        prev = _download_prev_candidates(product["_row_hash"]) if only_line is not None else None
        if only_line is not None and prev is None:
            print(f"[pipeline] 이전 후보 매니페스트 없음 → 라인 {only_line} 대신 전체 재생성")
            only_line = None
        # '다시 찾기'가 확실히 다른 이미지를 주도록, 직전에 그 라인에 보여준 URL·밈을 제외 목록으로 넘긴다.
        excl_urls, excl_memes = [], []
        if only_line is not None and prev is not None:
            pl = next((l for l in prev.get("lines", []) if int(l.get("line_i", -1)) == only_line), None)
            for c in (pl.get("candidates", []) if pl else []):
                if c.get("url"):
                    excl_urls.append(c["url"])
                if c.get("is_meme") and c.get("file"):
                    excl_memes.append(c["file"])
            print(f"[pipeline] 라인 {only_line} 재생성 — 직전 이미지 {len(excl_urls)}개·밈 {len(excl_memes)}개 제외")
        manifest = imagesource.fetch_candidates(
            product, lines, job_dir, settings, product_images=_pimgs, only_line=only_line,
            exclude_urls=excl_urls, exclude_memes=excl_memes, detail_images=detail_imgs)
        # 제품 영상(링크 추출 + 업로드본)을 라인 후보('제품영상')로 추가 — 실패해도 이미지 후보만으로 계속
        try:
            from src.product.video_link import ensure_link_videos
            pvids = ensure_link_videos(product["_row_hash"], job_dir, PROJECT_ROOT)
            if len(pvids) < 2:   # 링크본 우선, 남는 슬롯만 업로드본으로(다운로드 시간 절약)
                seen_pv = {Path(p).name for p in pvids}
                pvids += [p for p in fetch_product_videos(product["_row_hash"], job_dir,
                                                          max_n=2 - len(pvids))
                          if Path(p).name not in seen_pv]
            if pvids:
                _append_video_candidates(manifest, pvids, job_dir)
        except Exception as e:
            print(f"[pipeline] 제품 영상 후보 추가 실패({type(e).__name__}: {e}) — 이미지 후보만 진행")
        web_path = _publish_candidates(manifest, product, job_dir)
        if only_line is not None and prev is not None:
            _merge_line_manifest(web_path, prev, only_line)
        print(f"[pipeline] #2 후보 생성 완료 → {job_dir}/candidates/ + cand_{product['_row_hash']}.json "
              f"{'(라인 '+str(only_line)+'만 병합)' if only_line is not None else ''}(TTS·렌더 생략)")
        if only_line is None:   # 전체 후보 생성만 알림(라인별 '다시 찾기'는 관리자에서 바로 보이므로 생략 — 노이즈 방지)
            notify.send(
                f"[쿠팡쇼츠] 이미지 후보 준비 완료 — {product['name']}\n"
                f"다음: 관리자 '이미지' 탭에서 라인별로 고르고 '선택 저장'하세요.\n"
                f"https://shorts-admin.jtaechul.workers.dev")
        return 0

    # ---- M4(+M5): TTS → audio.mp3 + timestamps.json (또는 --no-narration이면 무음+합성 타이밍)
    if args.no_narration:
        t0 = time.time()
        tts_result = _silent_track(lines, job_dir)
        words = tts_result["words"]
        print(f"[pipeline] M4 나레이션 생략(--no-narration): 무음 {tts_result['duration']:.1f}s, "
              f"단어 {len(words)}개(대본 길이로 타이밍 합성)")
    else:
        tts_settings = dict(settings.get("tts", {}))
        if args.provider:
            tts_settings["provider"] = args.provider
        t0 = time.time()
        tts_result = tts.synthesize_to_files(text, job_dir, tts_settings, settings.get("whisper", {}))
        words = tts_result["words"]
        print(f"[pipeline] M4 TTS 완료({tts_result['provider']}/{tts_result['timestamps_source']}) "
              f"{time.time() - t0:.1f}s, 단어 {len(words)}개")

    # ---- 라인 타이밍 → 쉐이크 윈도우 (punch 라인 = 가장 충격적인 훅)
    line_windows = _line_windows(lines, words)
    shake_sec = float(settings.get("render", {}).get("shake_seconds", 0.3))
    shake_windows = [(s, s + shake_sec) for (s, _e), l in zip(line_windows, lines) if l.get("punch")]

    # ---- 상품 히어로 사진: 캡처에서 확보한 것 + 붙여넣은 이미지 URL 다운로드 (화면 주인공)
    product_images = list(product.get("hero_images") or [])
    product_images += _download_images(product.get("image_urls") or [], job_dir)
    # ---- 제품 실사용 영상: 관리자 페이지에서 업로드한 것(릴리스 product-assets)을 상품 해시로
    #      내려받아 상품 단계 풀프레임 배경으로 사용. 없으면 사진 히어로 폴백.
    product_videos = [p for p in (product.get("hero_videos") or []) if Path(p).exists()]
    product_videos += fetch_product_videos(product["_row_hash"], job_dir)
    # ---- Gemini/Veo 영상 생성 폐지(2026-07-13 사용자 확정): 유료 AI 영상은 품질 대비 값어치 없음.
    #      상품 비주얼은 오직 (a) 운영자가 올린 제품 영상 + (b) 상품 사진 켄번즈 + (c) 밈 이미지로만 구성.
    #      → 어떤 경우에도 Gemini API를 호출하지 않는다(제작비=목소리 TTS + 대본 텍스트뿐).
    # ---- 스톡 b-roll 자동 검색 폐지(2026-07-12 개편): 검색어만으로는 무관한 장면(남의 집
    #      소파·주방)이 들어와 영상을 망친다. 운영자가 후보 그리드에서 직접 승인한 클립만
    #      product['stock_clips']로 들어온다(Task: Phase2 후보 그리드). 없으면 문제 구간은
    #      어두운 상품 배경 변주로 렌더 — 항상 상품과 관련된 화면만 나온다.
    stock_clips = [p for p in (product.get("stock_clips") or []) if Path(p).exists()]
    bg_path = None

    # ---- 라인별 비주얼 소싱: 라인마다 '상황에 맞는' 이미지 배정(상품 라인만 상품 사진).
    #      다양 소스(Pexels·Openverse·Wikimedia). 실패해도 렌더가 상품 사진으로 폴백(빈 화면 없음).
    line_images = []
    selections_applied = False   # 운영자 선택본이면 상품사진→제품영상 자동치환을 끈다(고른 사진 존중)
    if str(settings.get("render", {}).get("layout", "framed")).lower() in ("framed", "expose"):
        try:
            # #2: 운영자가 관리자에서 고른 이미지(data/selections/{row}.json)가 있으면 그걸 최우선 사용.
            line_images = imagesource.load_selections(
                product["_row_hash"], lines, PROJECT_ROOT, job_dir,
                product_images=product_images, product_videos=product_videos)
            selections_applied = line_images is not None
            if line_images is None:   # 선택본 없으면 자동 소싱(폴백)
                line_images, vis_plan = imagesource.fetch_line_images(
                    product, lines, product_images, job_dir, settings)
                (job_dir / "visual_plan.json").write_text(
                    json.dumps(vis_plan, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as e:
            print(f"[pipeline] 라인 이미지 소싱 실패({type(e).__name__}: {e}) → 상품 사진 폴백")

    # ---- M6: 렌더 (framed 레이아웃: 정사각형에 이미지/영상 항상 꽉 참 + 상/하단 바)
    out_path = job_dir / "video.mp4"
    stats = render_video(tts_result["audio_path"], words, out_path, settings,
                         shake_windows=shake_windows, project_root=PROJECT_ROOT,
                         product_images=product_images, bg_path=bg_path,
                         lines=lines, line_windows=line_windows, stock_clips=stock_clips,
                         product_videos=product_videos, line_images=line_images,
                         has_narration=not args.no_narration,
                         headline=script.get("headline", ""),
                         thumb_hook=script.get("thumb_hook", ""),
                         selections_applied=selections_applied)
    stats = {"job_id": job_id, "product": product["name"],
             "tts_provider": tts_result["provider"],
             "timestamps_source": tts_result["timestamps_source"], **stats}
    (job_dir / "render_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] M6 렌더 완료: {stats['render_seconds']}s, "
          f"{stats['video_duration_seconds']}s 영상, 이미지 {stats['image_clip_count']}개")

    # ---- M6.5: QA 게이트 — 자막=대본 일치·위치·길이·프레임 번인을 기계 검사.
    #      실패하면 여기서 중단(비정상 종료) → 워크플로우 실패 → 릴리스/업로드 차단.
    qa_report = run_qa(out_path, stats, lines, job_dir, settings)
    if not qa_report["passed"]:
        notify.send("[쿠팡쇼츠] QA 게이트 실패 — 발행 차단 (job={})\n{}".format(
            job_id, "\n".join(qa_report["problems"][:5])))
        raise RuntimeError("QA 게이트 실패: " + "; ".join(qa_report["problems"][:5]))

    # ---- 대표 썸네일(poster.jpg): 관리자 페이지 영상 목록에서 통일된 카드로 노출 (실패해도 제작은 계속)
    try:
        build_poster(job_dir / "poster.jpg", product, settings,
                     project_root=PROJECT_ROOT, product_images=product_images)
        print("[pipeline] 대표 썸네일 생성: poster.jpg")
    except Exception as e:
        print(f"[pipeline] 경고: 대표 썸네일 생성 실패({type(e).__name__}: {e}) — 건너뜀")

    # ---- M7: 업로드 (새 흐름: --no-upload면 제작만 하고 검수 후 '올리기'에서 업로드)
    privacy = args.privacy or settings.get("upload", {}).get("privacy_default", "private")
    if args.no_upload:
        result = {"status": "skipped_no_upload", "hint": "검수 단계 — 업로드는 '올리기' 버튼에서"}
        print("[pipeline] 제작만 수행(--no-upload) — 유튜브 업로드는 검수 통과 후 '올리기'로")
        notify.send(
            f"[쿠팡쇼츠] 영상 제작 완료 — 검수 대기\n"
            f"{product['name']} · {stats.get('video_duration_seconds')}초\n"
            f"다음: 관리자 '영상' 탭에서 확인 후 문제없으면 '올리기'를 누르세요.\n"
            f"https://shorts-admin.jtaechul.workers.dev")
    elif youtube.is_configured():
        result = youtube.upload(out_path, script, product, settings, privacy=privacy)
        manual_queue.mark_done(product["_row_hash"])  # 성공 시에만 큐 소진(중복 제작 방지)
        # ⭐ 캡처·메모(notes)는 삭제하지 않는다(2026-07-18 사용자 확정): 업로드 후 지우던 설계가
        #    '불러오기 재기획'에서 재료 없음 오류(run147~149)를 냈다 — 자료는 상품의 원천이라 보존.
        print("[pipeline] 큐 상태 갱신 — 워크플로우가 커밋합니다 (캡처 자료는 재기획용으로 보존)")
        notify.send(f"[쿠팡쇼츠] 영상 업로드 완료({privacy})\n{result['title']}\n{result['url']}\n"
                    f"→ 유튜브 앱에서 ①공개 전환 ②고지 댓글 고정을 확인하세요")
    else:
        result = {"status": "skipped_no_credentials", "hint": youtube.missing_hint()}
        print(f"[pipeline] M7 업로드 건너뜀 — {youtube.missing_hint()}")
        print("[pipeline] 영상은 Actions Artifacts에서 다운로드해 검수하세요")
        run_url = "{}/{}/actions/runs/{}".format(
            os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
            os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_RUN_ID", ""))
        if os.environ.get("GITHUB_RUN_ID"):
            notify.send(f"[쿠팡쇼츠] 영상 생성 완료 — 업로드 대기(유튜브 키 미등록)\n"
                        f"{script.get('title', '')}\n다운로드(하단 Artifacts): {run_url}\n"
                        f"업로드 자동화: docs/setup-guide.md의 SHORTS_YT_* 등록")
    (job_dir / "upload_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 릴리스 메타데이터(관리자 페이지 영상 카드용) — 워크플로우가 릴리스 본문으로 발행
    release_meta = {
        "name": product.get("name"),
        "price": product.get("price"),
        "title": script.get("title"),
        "row_hash": product.get("_row_hash"),   # '올리기'가 상품→영상 매칭에 사용
        "affiliate_url": product.get("affiliate_url"),
        "youtube_url": result.get("url"),
        "duration": stats.get("video_duration_seconds"),
    }
    (job_dir / "release_meta.json").write_text(
        json.dumps(release_meta, ensure_ascii=False, indent=1), encoding="utf-8")

    _step_summary(stats, result, script)
    print(f"[pipeline] 완료: {job_dir}")
    return 0


def _silent_track(lines: list, job_dir: Path) -> dict:
    """--no-narration: 나레이션 없이 렌더하기 위한 무음 오디오 + 대본 길이 기반 합성 타이밍.
    한국어 잰 템포(글자수×0.14s + 여유)로 라인 길이를 정하고 단어를 균등 배분한다.
    반환 형태는 tts.synthesize_to_files 결과와 호환(audio_path/words/provider)."""
    import wave
    CPS, PAUSE = 0.14, 0.35
    words, t = [], 0.0
    for ln in lines:
        toks = str(ln.get("text", "")).split()
        if not toks:
            continue
        chars = sum(len(x) for x in toks) or 1
        dur = max(1.0, chars * CPS + PAUSE)
        step = dur / len(toks)
        for w in toks:
            words.append({"word": w, "start": round(t, 3), "end": round(t + step - 0.02, 3)})
            t += step
    total = round(t + 0.3, 3)
    fr = 44100
    wavp = job_dir / "audio.wav"
    with wave.open(str(wavp), "w") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(fr)
        wv.writeframes(b"\x00\x00" * int(fr * total))
    return {"audio_path": wavp, "words": words, "duration": total,
            "provider": "none(silent)", "timestamps_source": "synth"}


def _line_windows(lines: list, words: list) -> list:
    """대본 라인별 (시작, 끝) 시각 — 단어 수 누적으로 timestamps와 매핑."""
    windows, idx = [], 0
    for line in lines:
        n = len(line["text"].split())
        chunk = words[idx:idx + n]
        if chunk:
            windows.append((float(chunk[0]["start"]), float(chunk[-1]["end"])))
        else:
            last = windows[-1][1] if windows else 0.0
            windows.append((last, last))
        idx += n
    return windows


def _download_images(urls: list, job_dir: Path) -> list:
    """붙여넣은 상품 이미지 URL(파트너스 공식 이미지)을 내려받아 히어로 후보로. 실패는 건너뜀."""
    if not urls:
        return []
    img_dir = job_dir / "images"
    img_dir.mkdir(exist_ok=True)
    paths = []
    for i, url in enumerate(urls):
        try:
            import requests
            r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (shorts-factory)"})
            r.raise_for_status()
            fp = img_dir / f"url_{i}.jpg"
            fp.write_bytes(r.content)
            paths.append(str(fp))
        except Exception as e:
            print(f"[pipeline] 경고: 이미지 URL {i} 다운로드 실패({e}) — 건너뜀")
    return paths


def _download_prev_candidates(row_hash: str) -> dict | None:
    """공개 릴리스 shorts-cand에서 현재 cand_{hash}.json을 받아온다(라인별 재생성 병합용).
    없으면 None(→ 전체 재생성 폴백). 저장소가 공개라 인증 없이 받는다."""
    slug = os.environ.get("GITHUB_REPOSITORY", "jtaechul/Product")
    url = f"https://github.com/{slug}/releases/download/shorts-cand/cand_{row_hash}.json"
    try:
        r = requests.get(url, headers={"User-Agent": "shorts-factory"}, timeout=30)
        if r.ok and r.text.strip():
            data = r.json()
            if isinstance(data, dict) and isinstance(data.get("lines"), list):
                return data
    except Exception as e:
        print(f"[pipeline] 이전 후보 매니페스트 다운로드 실패({type(e).__name__}: {e})")
    return None


def _persist_product_meta(product: dict, settings: dict) -> None:
    """M2.5가 추출한 상품명 + 스토어 카드용 '한 줄 소개'(무슨 불편을 없애는지)를
    data/product_names.json({row_hash: {name, pain}})에 기록 — 관리자 대기열·스토어 선택·
    공개 스토어 카드가 링크 조각 대신 실제 이름과 소개를 자동 표시한다(워크플로가 커밋).
    ⚠️ CSV의 이름칸은 절대 채우지 않는다: row_hash가 '이름|링크' 해시라 이름을 채우면 해시가
    바뀌어 기존 기획·이미지 선택·영상·노트 연결이 전부 끊긴다(별도 파일로만 매핑).
    한 줄 소개는 상품당 1회만 LLM(≈2원)으로 생성 — 이미 있으면 호출하지 않는다."""
    name = (product.get("name") or "").strip()
    rh = (product.get("_row_hash") or "").strip()
    if not name or not rh:
        return
    path = PROJECT_ROOT / "data" / "product_names.json"
    try:
        names = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if not isinstance(names, dict):
            names = {}
    except Exception:
        names = {}
    ent = names.get(rh)
    ent = {"name": ent} if isinstance(ent, str) else (ent if isinstance(ent, dict) else {})
    changed = False
    if ent.get("name") != name:
        ent["name"] = name
        changed = True
    if not (ent.get("pain") or "").strip():
        pain = _gen_store_pain(product, settings)
        if pain:
            ent["pain"] = pain
            changed = True
    if not changed:
        return
    names[rh] = ent
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(names, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] 상품 메타 기록(관리자·스토어 표시용): {rh} → {ent.get('name')} / {ent.get('pain', '(소개 없음)')}")


def _gen_store_pain(product: dict, settings: dict) -> str | None:
    """스토어 카드 한 줄 소개 생성 — '무슨 불편을 없애는지' 12~30자(레퍼런스: '집에서 간편하게
    즐기는 일본 온천욕' 톤). 키 없음·실패 시 None(관리자에서 직접 입력 가능 — 제작은 안 막음)."""
    from src.script.generate import (_anthropic_generate, _gemini_generate, anthropic_key,
                                     gemini_key, script_provider)
    from src.script.sanitize import check_forbidden, clean_text
    provider = script_provider(settings)
    if not (gemini_key() if provider == "gemini" else anthropic_key()):
        return None
    cfg = settings.get("script", {})
    model = (cfg.get("gemini_model", "gemini-2.5-flash") if provider == "gemini"
             else cfg.get("model", "claude-sonnet-4-6"))
    system = "너는 한국어 커머스 카피라이터다. JSON만 반환한다. 마크다운·설명 금지."
    prompt = (
        "쿠팡 상품의 스토어 카드용 '한 줄 소개'를 지어라 — 이 물건이 무슨 불편을 없애고 뭐가 좋은지, "
        "12~28자 한국어 한 줄.\n"
        "스타일 예시: '집에서 간편하게 즐기는 일본 온천욕' / '컵을 감지하면 자동으로 나오는 가글' / "
        "'점심을 정해주는 마법의 책'\n"
        "금지: 가격·금액, 이모지·특수기호, 최고/유일/100프로 같은 단정, 물음표 낚시.\n"
        f"상품명: {product.get('name', '')}\n"
        f"특징: {'; '.join(product.get('specs') or [])}\n"
        f"메모: {str(product.get('notes') or '')[:500]}\n"
        '출력(JSON만): {"line": "..."}')
    import re as _re
    for _ in range(2):
        try:
            text = (_gemini_generate(model, system, prompt, 300) if provider == "gemini"
                    else _anthropic_generate(model, system, prompt, 300))
            m = _re.search(r"\{.*\}", text, _re.S)
            line = clean_text(str((json.loads(m.group(0)) if m else {}).get("line", "")).strip())
            if (8 <= len(line) <= 40 and not check_forbidden(line)
                    and not _re.search(r"\d[\d,]*\s*원|\d+\s*만\s*원", line)):
                return line
        except Exception as e:
            print(f"[pipeline] 한 줄 소개 생성 실패({type(e).__name__}: {e}) — 재시도/생략")
    return None


def _pv_frame(vp: Path, t: float, out: Path) -> bool:
    """영상의 t초 프레임을 jpg로 저장(구간 대표 썸네일용)."""
    try:
        from PIL import Image
        from moviepy import VideoFileClip
        clip = VideoFileClip(str(vp))
        tt = min(max(0.1, float(t)), max(0.1, float(clip.duration or 1) - 0.1))
        Image.fromarray(clip.get_frame(tt)).save(str(out), quality=85)
        clip.close()
        return True
    except Exception as e:
        print(f"[pipeline] 포스터 실패({vp.name}@{t:.1f}s: {e})")
        return False


def _append_video_candidates(manifest: list, pvids: list, job_dir: Path) -> None:
    """제품 영상을 '특징 구간'별 후보로 추가(2026-07-17 사용자 확정 — 이전엔 영상 앞부분만 재생됨).
    장면 전환을 탐지해(vsegment) 구간마다 그 구간 한가운데 프레임을 썸네일로 만들고
    pv_start/pv_end(초)를 실어 보낸다 — 운영자가 고른 구간만 잘라 그 라인에서 재생된다."""
    from src.video.vsegment import detect_segments
    raw = Path(job_dir) / "cand_raw"
    raw.mkdir(parents=True, exist_ok=True)
    entries = []
    for v in pvids[:2]:
        vp = Path(v)
        try:
            segs = detect_segments(vp, max_n=4 if len(pvids) == 1 else 2)
        except Exception as e:
            print(f"[pipeline] 구간 탐지 실패({vp.name}: {e}) — 앞 8초 1구간")
            segs = [(0.0, 8.0)]
        for k, (s, e) in enumerate(segs):
            pj = raw / f"pv_{vp.stem}_s{k}.jpg"
            if _pv_frame(vp, (s + e) / 2, pj):
                entries.append({"file": str(pj), "pv_name": vp.name,
                                "pv_start": round(float(s), 2), "pv_end": round(float(e), 2)})
    if not entries:
        return
    for e0 in manifest:
        for c in entries:
            e0["candidates"].append({"file": c["file"], "source": "product_video", "url": None,
                                     "is_pvideo": True, "pv_name": c["pv_name"],
                                     "pv_start": c["pv_start"], "pv_end": c["pv_end"]})
    print(f"[pipeline] 제품 영상 특징구간 후보 {len(entries)}개를 {len(manifest)}개 라인에 추가")


def _merge_line_manifest(web_path: Path, prev_full: dict, line_i: int) -> None:
    """이번에 재생성한 라인(web_path의 그 한 라인)을 기존 전체 매니페스트(prev_full)에 끼워 넣어
    web_path를 '전체 매니페스트'로 다시 쓴다. 다른 라인은 prev_full 그대로 유지(이미지 안 바뀜)."""
    new = json.loads(web_path.read_text(encoding="utf-8"))
    new_line = next((l for l in new.get("lines", []) if int(l.get("line_i", -1)) == int(line_i)), None)
    lines = [dict(l) for l in prev_full.get("lines", [])]
    replaced = False
    for idx, l in enumerate(lines):
        if int(l.get("line_i", -1)) == int(line_i) and new_line is not None:
            lines[idx] = new_line
            replaced = True
            break
    if not replaced and new_line is not None:
        lines.append(new_line)
    merged = dict(prev_full)
    merged["lines"] = sorted(lines, key=lambda l: int(l.get("line_i", 0)))
    web_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] 라인 {line_i} 후보를 기존 매니페스트에 병합 → 총 {len(merged['lines'])}라인")


def _publish_candidates(manifest: list, product: dict, job_dir: Path) -> Path:
    """#2 관리자 선택기용 웹 매니페스트 — 후보 파일을 row_hash 기반 고유명으로 candidates/에 모으고,
    브라우저가 읽을 cand_{row_hash}.json 을 만든다(워크플로우가 이 폴더+매니페스트를 릴리스 shorts-cand에 올림).
    각 후보는 {name(자산 파일명), url(원본 소스 URL·이미지라인), source, is_product}. 관리자가 고른 뒤
    data/selections/{row_hash}.json 로 저장하면 load_selections가 url을 내려받아 그 라인에 쓴다."""
    import shutil
    rh = product["_row_hash"]
    cdir = job_dir / "candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    web = {"row_hash": rh, "product_name": product.get("name", ""), "lines": []}
    for e in manifest:
        i = int(e["line_i"])
        cands = []
        for j, c in enumerate(e.get("candidates", [])):
            src_file = c.get("file")
            if not src_file or not Path(src_file).exists():
                continue
            ext = Path(src_file).suffix.lower() or ".jpg"
            name = f"{rh}__L{i:02d}__{j}{ext}"
            dest = cdir / name
            try:
                if Path(src_file).resolve() != dest.resolve():
                    shutil.copyfile(src_file, dest)
            except Exception:
                continue
            cand = {"name": name, "url": c.get("url"), "source": c.get("source", ""),
                    "is_product": bool(c.get("is_product"))}
            if c.get("is_product"):   # 상품 사진: 어느 상품 이미지인지(prod_idx) 보존 → 선택 시 그 사진을 쓴다(#3)
                cand["prod_idx"] = int(c.get("prod_idx", 0))
            if c.get("is_meme"):   # 밈 후보: 선택 시 렌더가 저장소 파일을 그대로 쓰게 file(저장소 상대경로) 전달
                cand["is_meme"] = True
                cand["file"] = c.get("meme_rel")
            if c.get("is_pvideo"):   # 제품 영상 후보: 썸네일=포스터, 실제 영상=릴리스 자산명(pv_name)
                cand["is_pvideo"] = True
                cand["pv_name"] = c.get("pv_name")
                if c.get("pv_start") is not None:   # 특징 구간(초) — 선택 시 그 구간만 잘라 재생
                    cand["pv_start"] = float(c.get("pv_start"))
                    cand["pv_end"] = float(c.get("pv_end") or 0)
            if c.get("is_detail"):   # 상세컷(PDF 기능 설명 크롭): detail_idx로 제작 때 같은 컷 재현
                cand["is_detail"] = True
                cand["detail_idx"] = int(c.get("detail_idx", 0))
            cands.append(cand)
        web["lines"].append({"line_i": i, "text": e.get("text", ""), "stage": e.get("stage"),
                             "punch": bool(e.get("punch")), "is_hook": bool(e.get("is_hook")),
                             "query": e.get("query", ""), "candidates": cands})
    man_path = job_dir / f"cand_{rh}.json"
    man_path.write_text(json.dumps(web, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] #2 웹 매니페스트: {man_path.name} "
          f"({sum(len(l['candidates']) for l in web['lines'])}장, {len(web['lines'])}라인)")
    return man_path


def _regen_field(product: dict, field: str, settings: dict, root: Path) -> int:
    """검수 재생성(B4) — 기획의 한 항목만 새 안 1개로 만들어 data/plans/{hash}.json 갱신."""
    from src.script.generate import regenerate_field
    from src.script.sanitize import clean_text
    plan_path = root / "data" / "plans" / f"{product['_row_hash']}.json"
    if not plan_path.exists():
        print("::error::기획이 없습니다 — 먼저 '기획 만들기'로 기획을 만드세요")
        return 2
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    try:
        val = regenerate_field(plan, field, product, settings)
    except Exception as e:
        print(f"::error::재생성 실패({type(e).__name__}: {e})")
        return 2
    f = field.strip().lower()
    if f == "hashtags":
        tags = val if isinstance(val, list) else [val]
        norm = []
        for t in tags:
            tag = "#" + str(t).lstrip("#").replace(" ", "")
            if len(tag) > 1 and tag not in norm:
                norm.append(tag)
        plan["hashtags"] = norm[:3]
    elif f == "description":
        plan["description_body"] = clean_text(str(val))
    elif f in ("title", "thumb_hook"):
        # 포맷 v2(2026-07-18): 제목=훅 카드 문구=첫 낭독 삼위일체 — 하나를 재생성하면 셋 다 갱신.
        from src.script.sanitize import build_subs, strip_target_words
        hook = strip_target_words(clean_text(str(val))).strip()
        plan["title"] = plan["thumb_hook"] = hook
        lines = plan.get("lines") or []
        if lines and lines[0].get("is_hook"):   # 낭독 라인 0(훅 카드)도 같은 문장으로
            lines[0]["text"] = hook
            lines[0]["subs"] = build_subs(hook)
    else:
        plan[f] = clean_text(str(val))
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] '{field}' 재생성 완료 → data/plans/{product['_row_hash']}.json")
    notify.send(
        f"[쿠팡쇼츠] '{field}' 재생성 완료 — {product['name']}\n"
        f"다음: 관리자 '제작' 탭에서 새 내용을 확인하세요.\n"
        f"https://shorts-admin.jtaechul.workers.dev")
    return 0


def _regen_line(product: dict, line_i: int, settings: dict, root: Path) -> int:
    """검수 — 대본 한 라인의 문구(text)만 재생성해 기획 JSON에 즉시 교체(스토리 연결성 유지)."""
    from src.script.generate import regenerate_line
    plan_path = root / "data" / "plans" / f"{product['_row_hash']}.json"
    if not plan_path.exists():
        print("::error::기획이 없습니다 — 먼저 '기획 만들기'로 대본을 만드세요")
        return 2
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    lines = plan.get("lines") or []
    if not (0 <= line_i < len(lines)):
        print(f"::error::라인 번호 범위 밖: {line_i} (0~{len(lines) - 1})")
        return 2
    try:
        newline = regenerate_line(plan, line_i, product, settings)
    except Exception as e:
        print(f"::error::라인 문구 재생성 실패({type(e).__name__}: {e})")
        return 2
    old = lines[line_i].get("text", "")
    lines[line_i]["text"] = newline["text"]
    lines[line_i]["subs"] = newline["subs"]   # subs 계약(join==text) 유지 — 렌더 자막 그대로 사용
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] 라인 {line_i} 문구 재생성 완료: '{old}' → '{newline['text']}'")
    notify.send(
        f"[쿠팡쇼츠] 라인 {line_i + 1} 문구 재생성 완료 — {product['name']}\n"
        f"새 문구: {newline['text']}\n"
        f"다음: 관리자 '기획' 탭에서 확인하세요.\n"
        f"https://shorts-admin.jtaechul.workers.dev")
    return 0


def _find_and_download_video(row_hash: str, job_dir: Path) -> Path | None:
    """제작된 영상 찾기 — 릴리스 shorts-run* 중 release_meta.row_hash가 일치하는 최신본의 video.mp4 다운로드."""
    import requests
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "jtaechul/Product")
    if not token:
        print("[pipeline] GH_TOKEN 없음 — 릴리스에서 영상 조회 불가")
        return None
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        rels = requests.get(f"https://api.github.com/repos/{repo}/releases?per_page=100",
                            headers=h, timeout=30).json()
    except Exception as e:
        print(f"[pipeline] 릴리스 조회 실패({e})")
        return None
    for r in rels if isinstance(rels, list) else []:   # API가 최신순 반환
        if not str(r.get("tag_name", "")).startswith("shorts-run"):
            continue
        try:
            body = json.loads(r.get("body") or "{}")
        except Exception:
            body = {}
        if body.get("row_hash") != row_hash:
            continue
        va = next((a for a in r.get("assets", []) if str(a.get("name", "")).endswith("video.mp4")), None)
        if not va:
            continue
        dest = job_dir / "video.mp4"
        try:
            dl = requests.get(va["url"], headers={**h, "Accept": "application/octet-stream"}, timeout=180)
            dl.raise_for_status()
            dest.write_bytes(dl.content)
            print(f"[pipeline] 제작 영상 확보: {r['tag_name']} → {dest.name} ({len(dl.content)//1024}KB)")
            return dest
        except Exception as e:
            print(f"[pipeline] 영상 다운로드 실패({e})")
            return None
    return None


def _upload_existing(product: dict, settings: dict, job_dir: Path, root: Path, privacy_arg) -> int:
    """올리기(B5) — 이미 제작된 영상을 릴리스에서 받아 유튜브 업로드(기획의 제목·설명·해시태그 사용)."""
    if not youtube.is_configured():
        print(f"::error::유튜브 인증 미등록 — {youtube.missing_hint()}")
        return 2
    from src.script.sanitize import product_avoid_terms, sanitize_script
    plan_path = root / "data" / "plans" / f"{product['_row_hash']}.json"
    if not plan_path.exists():
        print("::error::기획이 없습니다 — 먼저 기획·제작을 완료하세요")
        return 2
    script = sanitize_script(json.loads(plan_path.read_text(encoding="utf-8")),
                             strict_length=False, avoid_terms=product_avoid_terms(product))
    script["pinned_comment"] = f"제품 정보는 여기서 확인 → {product['affiliate_url']}\n{DISCLOSURE}"
    video = _find_and_download_video(product["_row_hash"], job_dir)
    if not video or not video.exists():
        print("::error::제작된 영상을 못 찾음 — 먼저 '제작하기'로 영상을 만드세요")
        return 2
    privacy = privacy_arg or settings.get("upload", {}).get("privacy_default", "private")
    result = youtube.upload(video, script, product, settings, privacy=privacy)
    manual_queue.mark_done(product["_row_hash"])
    # 캡처·메모(notes) 보존 — 업로드 후에도 재기획(불러오기)에 쓴다(2026-07-18 사용자 확정, 위와 동일)
    (job_dir / "upload_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    notify.send(f"[쿠팡쇼츠] 유튜브 업로드 완료({privacy})\n{result.get('title', '')}\n{result.get('url', '')}")
    print(f"[pipeline] 업로드 완료: {result.get('url')}")
    return 0


def _print_key_detection() -> None:
    names = ["SHORTS_ELEVENLABS_API_KEY", "SHORTS_TYPECAST_API_KEY", "SHORTS_CLOVA_CLIENT_ID",
             "SHORTS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY",
             "SHORTS_YT_REFRESH_TOKEN", "SHORTS_YT_CLIENT_ID", "YOUTUBE_CLIENT_ID",
             "SHORTS_PEXELS_API_KEY", "SHORTS_YT_API_KEY",
             "SHORTS_COUPANG_ACCESS_KEY", "TELEGRAM_BOT_TOKEN"]
    present = [n for n in names if os.environ.get(n, "").strip()]
    print(f"[pipeline] 감지된 키(이름만): {present or '없음'}")


def _step_summary(stats: dict, upload_result: dict, script: dict) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    rows = "\n".join(f"| {k} | {v} |" for k, v in stats.items())
    up = upload_result.get("url") or upload_result.get("status")
    Path(summary).open("a", encoding="utf-8").write(
        f"## 쇼츠 제작 결과 — {script.get('title', '')}\n\n"
        f"| 항목 | 값 |\n|---|---|\n{rows}\n| 업로드 | {up} |\n\n"
        f"산출물은 하단 **Artifacts**에서 다운로드.\n")


if __name__ == "__main__":
    sys.exit(main())
