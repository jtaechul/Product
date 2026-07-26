"""소싱 ⑤ 제작 — 선택 홍보 클립을 9:16로 이어붙이고, 그 위에 한국어 나레이션 + 카라오케 자막 +
상단 브랜드바를 얹어 최종 쇼츠(mp4)를 만든다.

재료: ③ promo/{hash}.json(선택 홍보영상) + ③b plan/{hash}.json(대본 lines/subs).
합성: compose로 클립 9:16 cover-fit 이어붙이기(원음 제거) → 나레이션 길이에 맞춰 루프/트림 →
      render._build_subtitles(대본=자막 그대로 팝업) + _brand_bar_clip(브랜드) 오버레이 → 나레이션 오디오.
narrate=False면 무음+합성 타이밍으로 화면 조립만 검증(TTS 키 불필요 · CI 프로브).
moviepy(v2) 렌더는 GitHub Actions에서 프레임으로 검증(로컬엔 moviepy/ffmpeg 없음)."""
from __future__ import annotations

import json
import wave
from pathlib import Path

from src.sourcing.compose import FPS, H, W, _clip_parts, download_clips, load_promo_selection
from src.sourcing.models import PROJECT_ROOT
from src.sourcing.plan import load_plan


def _line_windows(lines: list, words: list) -> list:
    """대본 라인별 (시작,끝) 시각 — 단어 수 누적으로 timestamps와 매핑(pipeline과 동일 규칙)."""
    windows, idx = [], 0
    for ln in lines:
        n = len(str(ln.get("text", "")).split())
        chunk = words[idx:idx + n]
        if chunk:
            windows.append((float(chunk[0]["start"]), float(chunk[-1]["end"])))
        else:
            last = windows[-1][1] if windows else 0.0
            windows.append((last, last))
        idx += n
    return windows


def _silent_track(lines: list, job_dir: Path) -> dict:
    """나레이션 없이(키 없거나 프로브) 무음 오디오 + 대본 길이 기반 합성 타이밍."""
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
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(fr)
        wv.writeframes(b"\x00\x00" * int(fr * total))
    return {"audio_path": wavp, "words": words, "duration": total, "provider": "none(silent)"}


def _have_tts(settings: dict) -> bool:
    try:
        from src.audio.tts import detect_available
        return bool(detect_available())
    except Exception:
        return False


def _stitched_base(clip_paths: list, segments: dict | None, duration: float):
    """클립들을 9:16 무음으로 이어붙이고 duration에 맞춰 루프/트림한 moviepy 클립. moviepy(CI)."""
    from moviepy import concatenate_videoclips
    parts = []
    for cp in clip_paths:
        parts.extend(_clip_parts(cp, segments, W, H))
    parts = [p for p in parts if p and (p.duration or 0) > 0.05]
    if not parts:
        return None
    seq = list(parts)
    while sum((p.duration or 0) for p in seq) < duration + 0.1:   # 짧으면 반복해 채움
        seq.extend(parts)
    base = concatenate_videoclips(seq, method="compose").with_fps(FPS)
    return base.subclipped(0, min(duration, base.duration))


def _scrim(width: int, y0: int, height: int, duration: float, alpha: int = 150):
    """검은 띠(반투명) — 하단 자막 가독성/상단 브랜드바 배경용. 움직이는 배경 위 글자 대비 확보.
    y0~height 범위를 채운다(하단: y0=1440,height=1920 / 상단바: y0=0,height=110·불투명에 가깝게)."""
    import numpy as np
    from moviepy import ImageClip
    band_h = max(1, height - y0)
    arr = np.zeros((band_h, width, 4), dtype=np.uint8)
    arr[..., 3] = int(max(0, min(255, alpha)))
    return ImageClip(arr, transparent=True).with_duration(duration).with_position((0, y0))


def produce(product_hash: str, job_dir, settings: dict, project_root=None,
            adapter=None, narrate: bool = True) -> Path:
    """소싱 최종 쇼츠 제작 → job_dir/video.mp4 반환. narrate=False면 무음(조립 검증용)."""
    root = Path(project_root or PROJECT_ROOT)
    job_dir = Path(job_dir); job_dir.mkdir(parents=True, exist_ok=True)
    plan = load_plan(product_hash, root)
    if not plan or not plan.get("lines"):
        raise RuntimeError("대본(plan)이 없습니다 — ③b(기획 방향·대본)를 먼저 하세요")
    lines = plan["lines"]
    videos = load_promo_selection(product_hash, base_dir=root / "data" / "sources")
    if not videos:
        raise RuntimeError("선택한 홍보영상이 없습니다 — ③에서 영상을 고르세요")
    pairs = download_clips(videos, job_dir / "clips", adapter)
    clip_paths = [p for _, p in pairs]
    if not clip_paths:
        raise RuntimeError("홍보 클립 다운로드 실패(전부) — 다른 영상으로 재시도")

    if narrate and _have_tts(settings):
        from src.audio import tts
        text = "\n".join(l["text"] for l in lines)
        r = tts.synthesize_to_files(text, job_dir, dict(settings.get("tts", {})), settings.get("whisper", {}))
        audio_path, words, prov = r["audio_path"], r["words"], r["provider"]
    else:
        r = _silent_track(lines, job_dir)
        audio_path, words, prov = r["audio_path"], r["words"], r["provider"]

    from moviepy import AudioFileClip, CompositeVideoClip
    from src.video.render import _brand_bar_clip, _build_subtitles, _resolve_font
    audio = AudioFileClip(str(audio_path))
    duration = float(audio.duration) + 0.3
    line_windows = _line_windows(lines, words)

    base = _stitched_base(clip_paths, None, duration)   # ④ 구간 지정 전: 전체 클립 루프(자동)
    if base is None:
        raise RuntimeError("합성할 클립이 없습니다")

    font_path = _resolve_font(root, "assets/fonts/GmarketSansBold.ttf")
    sub_s = {"y": 1520, "font_size": 74, "color": "#FFE400",
             "stroke_color": "#000000", "stroke_width": 6, "mode": "karaoke"}
    sub_clips, _plan = _build_subtitles(words, lines, line_windows, duration, font_path, sub_s, W, H, framed=False)

    ch = settings.get("channel", {})
    bar_h = 110
    top_bar = _scrim(W, 0, bar_h, duration, alpha=235)   # 상단 브랜드바 배경(불투명 검정 — 브랜드 글자 대비)
    brand = _brand_bar_clip(W, bar_h, ch.get("name", "미래에서 온 만물상"), ch.get("handle", ""),
                            None, font_path, duration).with_position((0, 0))
    scrim = _scrim(W, 1440, H, duration)   # 하단 자막 스크림

    layers = [base, top_bar, scrim, brand] + list(sub_clips)
    final = CompositeVideoClip(layers, size=(W, H)).with_duration(duration)
    final = final.with_audio(audio)
    out = Path(job_dir) / "video.mp4"
    final.write_videofile(str(out), fps=FPS, codec="libx264", audio_codec="aac",
                          ffmpeg_params=["-pix_fmt", "yuv420p"], logger=None)
    print(f"[produce] 완료: {out} · {duration:.1f}s · 나레이션 {prov} · 클립 {len(clip_paths)}개")
    try:  # 대표 썸네일(poster.jpg) — 상품명(대본 제목)만 있는 브랜드 카드(상품 사진 없으면 그라데이션)
        from src.video.render import build_poster
        poster_product = {"name": plan.get("product") or plan.get("title") or "상품", "price": 0}
        build_poster(Path(job_dir) / "poster.jpg", poster_product, settings, project_root=root)
    except Exception as e:
        print(f"[produce] 포스터 생략({type(e).__name__}: {e})")
    return out


def _load_settings(root: Path) -> dict:
    import yaml
    return yaml.safe_load((Path(root) / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}


def _main(argv=None) -> int:
    """워크플로 CLI — 확정 홍보영상(promo)+대본(plan)으로 최종 쇼츠 제작 →
    data/jobs/{job-id}/video.mp4 + poster.jpg + release_meta.json(관리자 ⑥ 검수 목록이 읽음).
    'PRODUCE_RESULT:' 접두로 결과 JSON을 출력한다(잡 로그·관리자 폴링). 커밋·릴리스는 워크플로가."""
    import argparse
    ap = argparse.ArgumentParser(description="소싱 ⑤ 제작")
    ap.add_argument("--hash", required=True, help="상품 해시(promo/{hash}.json + plan/{hash}.json)")
    ap.add_argument("--job-id", default="srcprod", help="산출 폴더 이름(data/jobs/{job-id})")
    ap.add_argument("--no-narration", action="store_true", help="TTS 없이 무음 조립(튜닝용)")
    args = ap.parse_args(argv)
    root = PROJECT_ROOT
    settings = _load_settings(root)
    job_dir = Path(root) / "data" / "jobs" / args.job_id
    out = produce(args.hash, job_dir, settings, project_root=root, narrate=not args.no_narration)
    plan = load_plan(args.hash, root) or {}
    meta = {"name": (plan.get("product") or plan.get("title") or "쿠팡 쇼츠"),
            "hash": args.hash, "kind": "sourcing", "title": plan.get("title", ""),
            "description": plan.get("description", ""), "hashtags": plan.get("hashtags", []),
            "video": out.name}
    (job_dir / "release_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PRODUCE_RESULT:", json.dumps(
        {"status": "ok", "hash": args.hash, "video": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
