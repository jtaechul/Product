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


def load_segments(product_hash: str, project_root=None) -> dict:
    """④ 구간 지정 → {video_id: [(start,end), ...]}. 관리자가 영상별로 고른 '쓸 구간'.
    파일 없으면 {}(→ produce가 전체 클립 사용). end=null이면 끝까지(None)."""
    p = Path(project_root or PROJECT_ROOT) / "data" / "sources" / "segments" / f"{product_hash}.json"
    if not p.exists():
        return {}
    try:
        segs = (json.loads(p.read_text(encoding="utf-8")) or {}).get("segments") or {}
    except Exception as e:
        print(f"[produce] 구간 파싱 실패({e}) — 전체 클립 사용")
        return {}
    out = {}
    for vid, ranges in segs.items():
        spans = []
        for r in (ranges or []):
            try:
                s = float(r[0]); e = None if (len(r) < 2 or r[1] is None) else float(r[1])
            except (TypeError, ValueError, IndexError):
                continue
            if e is None or e > s:
                spans.append((s, e))
        if spans:
            out[str(vid)] = spans
    return out


def _download_insert_url(url: str, dest_dir: Path, i: int, j: int):
    """삽입 검색 픽(giphy 등 URL)을 로컬 파일로 내려받는다(제작 시점). 실패 시 None."""
    from urllib.parse import urlparse
    dest_dir.mkdir(parents=True, exist_ok=True)
    tail = urlparse(url).path.rsplit("/", 1)[-1]
    ext = tail.rsplit(".", 1)[-1].lower() if "." in tail else "gif"
    if ext not in ("gif", "mp4", "webm", "mov", "jpg", "jpeg", "png", "webp"):
        ext = "gif"
    out = dest_dir / f"ins_{i}_{j}.{ext}"
    try:
        import requests
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        out.write_bytes(r.content)
        return out if out.stat().st_size > 200 else None
    except Exception as e:
        print(f"[produce] 삽입 URL 다운로드 실패({str(url)[:60]}): {type(e).__name__}: {e}")
        return None


def load_inserts(product_hash: str, project_root=None, download_dir=None) -> dict:
    """⑤ 삽입물 → {line_index(int): [abs_path, ...]}. 운영자가 특정 대사(라인) 구간에 얹을
    이미지/영상(움짤). 그 라인 구간 동안 소스 영상 위에 '풀프레임 컷어웨이'로 덮인다.
    파일 없으면 {}(→ 삽입 없이 소스 클립만). 저장형식: {"inserts": {"0":[항목,...], "2":[...]}}(리스트도 허용).
    항목은 ① 문자열/{"file"} = 저장소 상대경로(업로드·커밋본) ② {"url"} = 검색 픽(giphy 등, download_dir에 내려받음)."""
    root = Path(project_root or PROJECT_ROOT)
    p = root / "data" / "sources" / "inserts" / f"{product_hash}.json"
    if not p.exists():
        return {}
    try:
        raw = (json.loads(p.read_text(encoding="utf-8")) or {}).get("inserts")
    except Exception as e:
        print(f"[produce] 삽입물 파싱 실패({e}) — 삽입 없이 진행")
        return {}
    if not raw:
        return {}
    items = raw.items() if isinstance(raw, dict) else enumerate(raw)
    out = {}
    for k, entries in items:
        try:
            i = int(k)
        except (TypeError, ValueError):
            continue
        resolved = []
        for entry in (entries or []):
            if not entry:
                continue
            rel = entry.get("file") if isinstance(entry, dict) else entry
            url = entry.get("url") if isinstance(entry, dict) else None
            if rel:   # 업로드/커밋된 로컬 경로
                fp = Path(rel) if Path(rel).is_absolute() else (root / str(rel))
                if fp.exists():
                    resolved.append(str(fp))
                else:
                    print(f"[produce] 삽입 파일 없음 건너뜀: {rel}")
            elif url and download_dir:   # 검색 픽(URL) → 제작 시점 다운로드
                dl = _download_insert_url(str(url), Path(download_dir), i, len(resolved))
                if dl:
                    resolved.append(str(dl))
            elif url:
                print(f"[produce] 삽입 URL 다운로드 경로 없음 건너뜀: {url}")
        if resolved:
            out[i] = resolved
    return out


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
    # ④ 구간 지정: 영상 id로 저장된 '쓸 구간'을 다운로드된 클립 경로에 매핑(없는 영상은 전체 사용).
    seg_map = load_segments(product_hash, root)
    seg_by_path = {str(path): seg_map[sv.id] for sv, path in pairs if sv.id in seg_map}

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

    base = _stitched_base(clip_paths, seg_by_path or None, duration)   # ④ 구간 있으면 그 구간만, 없으면 전체 클립 루프
    if base is None:
        raise RuntimeError("합성할 클립이 없습니다")

    font_path = _resolve_font(root, "assets/fonts/GmarketSansBold.ttf")
    sub_s = {"y": 1520, "font_size": 74, "color": "#FFE400",
             "stroke_color": "#000000", "stroke_width": 6, "mode": "karaoke"}
    # ④ 오프닝 훅 카드(썸네일용): 첫 라인(훅)은 어절별 가라오케 대신 '문구 전체를 한 번에' 보여주는 큰 카드로.
    #    쇼츠는 첫 프레임이 그리드 썸네일이 되므로 제목(훅)이 통째로 박힌다. 그동안 소스 영상은 배경으로 계속 재생.
    hook_clip = None
    n0 = len(str(lines[0].get("text", "")).split()) if lines else 0
    use_hook = bool(lines and lines[0].get("is_hook") and n0 and line_windows)
    if use_hook:
        hook_end = float(line_windows[1][0]) if len(line_windows) >= 2 else min(2.6, duration)
        hook_end = max(0.9, min(hook_end, duration))
        hook_text = (plan.get("thumb_hook") or plan.get("title") or lines[0].get("text") or "").strip()
        from src.video.render import _thumb_hook_overlay
        hook_clip = _thumb_hook_overlay(hook_text, W, H, hook_end, font_path, settings)
        # 훅 라인(0번) 어절 자막은 카드와 겹치므로 제외 — 1번 라인부터 하단 가라오케.
        sub_clips, _plan = _build_subtitles(words[n0:], lines[1:], line_windows[1:], duration, font_path, sub_s, W, H, framed=False)
        print(f"[produce] 훅 카드: '{hook_text[:20]}' 0~{hook_end:.1f}s (문구 전체 노출)")
    else:
        sub_clips, _plan = _build_subtitles(words, lines, line_windows, duration, font_path, sub_s, W, H, framed=False)

    ch = settings.get("channel", {})
    bar_h = 110
    top_bar = _scrim(W, 0, bar_h, duration, alpha=235)   # 상단 브랜드바 배경(불투명 검정 — 브랜드 글자 대비)
    brand = _brand_bar_clip(W, bar_h, ch.get("name", "미래에서 온 만물상"), ch.get("handle", ""),
                            None, font_path, duration).with_position((0, 0))
    scrim = _scrim(W, 1440, H, duration)   # 하단 자막 스크림

    # ⑤ 삽입물(컷어웨이): 특정 대사 구간 동안 소스 영상 위에 운영자가 고른 이미지/영상(움짤)을
    #    풀프레임으로 덮는다. 자막·브랜드바는 그 위에 유지(레이어 순서로 보장). 없으면 소스만.
    insert_map = load_inserts(product_hash, root, download_dir=job_dir / "inserts_dl")
    insert_clips = []
    if insert_map:
        from src.video.render import _expose_image_clip
        for i, srcs in insert_map.items():
            if i >= len(line_windows) or not srcs:
                continue
            ls, le = float(line_windows[i][0]), min(float(line_windows[i][1]), duration)
            if le - ls < 0.1:
                continue
            span = (le - ls) / len(srcs)
            for j, src in enumerate(srcs):
                s = ls + j * span
                e = min(ls + (j + 1) * span, duration)
                clip = _expose_image_clip(src, s, e, W, 0, H, [], [], kb_zoom=0.06)   # 풀프레임 컷어웨이
                if clip is not None:
                    insert_clips.append(clip)
        if insert_clips:
            print(f"[produce] 삽입물 {len(insert_clips)}컷 (라인 {len(insert_map)}개)")

    layers = [base] + insert_clips + [top_bar, scrim, brand] + list(sub_clips)
    if hook_clip is not None:
        layers.append(hook_clip)   # 훅 카드는 맨 위 — 첫 구간에 제목(훅) 문구 전체 노출

    # ⑤ 효과음(SFX): 대본 stage/punch에 맞춰 라인 효과음 + 제품 공개(reveal) 효과음을 나레이션 위에 얹는다.
    try:
        from src.video.render import _find_reveal_time, _mix_line_sfx, _mix_reveal_sfx
        reveal_t = _find_reveal_time(lines, line_windows)
        audio = _mix_reveal_sfx(audio, reveal_t, root, settings, duration)
        audio = _mix_line_sfx(audio, lines, line_windows, reveal_t, root, settings, duration)
        print(f"[produce] 효과음 반영 (라인 SFX + 공개 reveal @{reveal_t if reveal_t is None else round(reveal_t,1)})")
    except Exception as e:
        print(f"[produce] 효과음 생략({type(e).__name__}: {e})")

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
