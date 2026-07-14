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
    p.add_argument("--plan", action="store_true",
                   help="기획+스토리보드+대본만 생성(승인 단계용) — data/plans/{row_hash}.json 작성, 이미지·제작 생략")
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
    (job_dir / "product.json").write_text(json.dumps(product, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] M2 상품: {product['name']} ({product['price']:,}원)")

    # ---- M3: 대본 (기획 승인 흐름)
    #   --plan          : 항상 새로 생성 → data/plans/{hash}.json 저장 후 종료(승인 대기)
    #   그 외(candidates/produce) : 승인된 기획(data/plans/{hash}.json)이 있으면 그걸 그대로 사용
    #                              (운영자가 확정한 대본을 재생성하지 않는다). 없으면 즉석 생성(하위호환).
    from src.script.sanitize import sanitize_script
    plan_path = PROJECT_ROOT / "data" / "plans" / f"{product['_row_hash']}.json"
    if args.script_file:
        script = json.loads(Path(args.script_file).read_text(encoding="utf-8"))
        script = sanitize_script(script, strict_length=False)
        print("[pipeline] M3 우회: script-file 사용")
    elif plan_path.exists() and not args.plan:
        script = sanitize_script(json.loads(plan_path.read_text(encoding="utf-8")), strict_length=False)
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
    # §3.1 고지문·링크는 항상 코드로 강제 (기획 로드 경로 포함)
    script["pinned_comment"] = f"제품 정보는 여기서 확인 → {product['affiliate_url']}\n{DISCLOSURE}"
    (job_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = script["lines"]
    text = "\n".join(l["text"] for l in lines)

    # ---- 기획 생성 모드(--plan): 기획+스토리보드+대본만 만들고 승인 대기 (이미지·제작 생략)
    if args.plan:
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[pipeline] 기획+대본 생성 완료 → data/plans/{product['_row_hash']}.json (승인 대기)")
        return 0

    # ---- 후보 이미지 생성 모드(#2 관리자 선택기용): TTS·렌더 없이 라인별 후보 이미지만 만든다.
    if args.candidates:
        _pimgs = list(product.get("hero_images") or [])
        _pimgs += _download_images(product.get("image_urls") or [], job_dir)
        manifest = imagesource.fetch_candidates(product, lines, job_dir, settings, product_images=_pimgs)
        _publish_candidates(manifest, product, job_dir)
        print(f"[pipeline] #2 후보 생성 완료 → {job_dir}/candidates/ + cand_{product['_row_hash']}.json "
              "(TTS·렌더 생략)")
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
    if str(settings.get("render", {}).get("layout", "framed")).lower() in ("framed", "expose"):
        try:
            # #2: 운영자가 관리자에서 고른 이미지(data/selections/{row}.json)가 있으면 그걸 최우선 사용.
            line_images = imagesource.load_selections(
                product["_row_hash"], lines, PROJECT_ROOT, job_dir)
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
                         headline=script.get("headline", ""))
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

    # ---- M7: 업로드 (자격 증명 없으면 건너뛰고 안내 — Artifacts로 검수)
    privacy = args.privacy or settings.get("upload", {}).get("privacy_default", "private")
    if youtube.is_configured():
        result = youtube.upload(out_path, script, product, settings, privacy=privacy)
        manual_queue.mark_done(product["_row_hash"])  # 성공 시에만 큐 소진(중복 제작 방지)
        for used in (PROJECT_ROOT / "data" / "notes").glob(f"{product['_row_hash']}*"):
            used.unlink(missing_ok=True)  # 소비한 캡처·메모 정리(저장소 비대화 방지)
        print("[pipeline] 큐 상태 갱신 + 사용한 상세 자료 정리 — 워크플로우가 커밋합니다")
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
            cands.append({"name": name, "url": c.get("url"), "source": c.get("source", ""),
                          "is_product": bool(c.get("is_product"))})
        web["lines"].append({"line_i": i, "text": e.get("text", ""), "stage": e.get("stage"),
                             "punch": bool(e.get("punch")), "query": e.get("query", ""),
                             "candidates": cands})
    man_path = job_dir / f"cand_{rh}.json"
    man_path.write_text(json.dumps(web, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] #2 웹 매니페스트: {man_path.name} "
          f"({sum(len(l['candidates']) for l in web['lines'])}장, {len(web['lines'])}라인)")
    return man_path


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
