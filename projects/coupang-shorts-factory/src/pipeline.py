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
from src.script.generate import DISCLOSURE, anthropic_key, generate_script
from src.upload import youtube
from src.video.render import render_video

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description="쿠팡 쇼츠 전체 파이프라인 (M2→M7)")
    p.add_argument("--row", default="auto", help="products_manual.csv 행 번호(1~) 또는 auto")
    p.add_argument("--privacy", default=None, help="private|unlisted|public (기본: settings)")
    p.add_argument("--provider", default=None, help="TTS 프로바이더 오버라이드")
    p.add_argument("--job-id", default=None)
    p.add_argument("--script-file", default=None, help="M3 우회용 대본 JSON 경로")
    p.add_argument("--soft", action="store_true", help="전제조건 미비 시 정상 종료(cron용)")
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
    # ---- M2: 상품 확보 (기본: 수동 CSV 큐. 쿠팡 API는 키 승인 후 Phase 2에서 전환)
    product = manual_queue.pick(args.row)
    (job_dir / "product.json").write_text(json.dumps(product, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] M2 상품: {product['name']} ({product['price']:,}원)")

    # ---- M3: 대본
    if args.script_file:
        script = json.loads(Path(args.script_file).read_text(encoding="utf-8"))
        from src.script.sanitize import sanitize_script
        script = sanitize_script(script, strict_length=False)
        script["pinned_comment"] = f"제품 정보는 여기서 확인 → {product['affiliate_url']}\n{DISCLOSURE}"
        print("[pipeline] M3 우회: script-file 사용")
    else:
        if not anthropic_key():
            msg = ("대본 생성용 Anthropic API 키 미등록 (SHORTS_ANTHROPIC_API_KEY 또는 ANTHROPIC_API_KEY). "
                   "등록 전에는 --script-file로만 실행 가능합니다.")
            if args.soft:
                print(f"[pipeline] {msg} → cron 모드라 정상 종료")
                return 0
            raise RuntimeError(msg)
        script = generate_script(product, settings)
    (job_dir / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = script["lines"]
    text = "\n".join(l["text"] for l in lines)

    # ---- M4(+M5): TTS → audio.mp3 + timestamps.json
    tts_settings = dict(settings.get("tts", {}))
    if args.provider:
        tts_settings["provider"] = args.provider
    t0 = time.time()
    tts_result = tts.synthesize_to_files(text, job_dir, tts_settings, settings.get("whisper", {}))
    words = tts_result["words"]
    print(f"[pipeline] M4 TTS 완료({tts_result['provider']}/{tts_result['timestamps_source']}) "
          f"{time.time() - t0:.1f}s, 단어 {len(words)}개")

    # ---- 라인 타이밍 → 쉐이크/이미지 윈도우
    line_windows = _line_windows(lines, words)
    shake_sec = float(settings.get("render", {}).get("shake_seconds", 0.3))
    shake_windows = [(s, s + shake_sec) for (s, _e), l in zip(line_windows, lines) if l.get("price_shock")]
    image_windows = _image_windows(lines, line_windows, product, job_dir)

    # ---- M6: 렌더
    out_path = job_dir / "video.mp4"
    stats = render_video(tts_result["audio_path"], words, out_path, settings,
                         shake_windows=shake_windows, project_root=PROJECT_ROOT,
                         image_windows=image_windows)
    stats = {"job_id": job_id, "product": product["name"],
             "tts_provider": tts_result["provider"],
             "timestamps_source": tts_result["timestamps_source"], **stats}
    (job_dir / "render_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[pipeline] M6 렌더 완료: {stats['render_seconds']}s, "
          f"{stats['video_duration_seconds']}s 영상, 이미지 {stats['image_clip_count']}개")

    # ---- M7: 업로드 (자격 증명 없으면 건너뛰고 안내 — Artifacts로 검수)
    privacy = args.privacy or settings.get("upload", {}).get("privacy_default", "private")
    if youtube.is_configured():
        result = youtube.upload(out_path, script, product, settings, privacy=privacy)
        manual_queue.mark_done(product["_row_hash"])  # 성공 시에만 큐 소진(중복 제작 방지)
        print("[pipeline] 큐 상태 갱신(data/processed.json) — 워크플로우가 커밋합니다")
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

    _step_summary(stats, result, script)
    print(f"[pipeline] 완료: {job_dir}")
    return 0


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


def _image_windows(lines: list, line_windows: list, product: dict, job_dir: Path) -> list:
    """image_cue 연속 구간별 상품 이미지 표시 윈도우. 다운로드 실패는 건너뜀."""
    urls = product.get("image_urls") or []
    if not urls:
        return []
    img_dir = job_dir / "images"
    img_dir.mkdir(exist_ok=True)
    cached = {}

    def fetch(i: int):
        if i in cached:
            return cached[i]
        path = None
        if 0 <= i < len(urls):
            try:
                import requests
                r = requests.get(urls[i], timeout=30,
                                 headers={"User-Agent": "Mozilla/5.0 (shorts-factory)"})
                r.raise_for_status()
                path = img_dir / f"img_{i}.jpg"
                path.write_bytes(r.content)
            except Exception as e:
                print(f"[pipeline] 경고: 이미지 {i} 다운로드 실패({e}) — 해당 구간 오버레이 생략")
                path = None
        cached[i] = path
        return path

    windows, cur_cue, cur_start = [], None, None
    for line, (s, e) in zip(lines, line_windows):
        cue = line.get("image_cue")
        if cue != cur_cue:
            if cur_cue is not None and fetch(cur_cue):
                windows.append((cur_start, s, str(fetch(cur_cue))))
            cur_cue, cur_start = cue, s
        last_end = e
    if cur_cue is not None and fetch(cur_cue):
        windows.append((cur_start, last_end + 0.4, str(fetch(cur_cue))))
    return windows


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
