"""M6. 영상 렌더링 — MoviePy 2.x (버전 고정: requirements.txt).

Phase 0 범위 (스펙 §8):
  - 캔버스 1080x1920(9:16), 30fps
  - 배경: assets/backgrounds/ 의 CC0 세로영상 랜덤 선택(오디오 길이에 맞춰 트림/루프),
    없으면 자체 생성 그라데이션(화이트리스트 §3.2: 자체 생성물) 폴백
  - 자막: 단어 단위 팝업 — GmarketSansBold, font_size 80, #FFE400, 검정 stroke 6,
    위치 (center, y=1250)
  - 쉐이크: punch 라인(가장 충격적인 훅) 시작 0.3초간 ±8px 랜덤 오프셋
  - 인코딩: H.264 CRF 20, AAC 128k
상품 이미지 오버레이(줌인)는 상품 데이터가 생기는 Phase 1에서 구현한다.

MoviePy 2.x 주의(스펙 §M6): TextClip은 PIL 기반 — font 인자에 ttf '파일 경로'를
직접 지정해야 한글이 깨지지 않는다.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    TextClip,
    VideoFileClip,
    vfx,
)

from src.video import memes as meme_lib

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}

# 씬마다 같은 사진의 흐린 배경·히어로 카드를 재계산하지 않도록 캐시(렌더 속도).
_BLUR_BG_CACHE: dict = {}
_HERO_RGBA_CACHE: dict = {}
_SQUARE_ARR_CACHE: dict = {}   # framed 정사각형 cover-fit 배열 캐시


def _mix_bgm(audio, project_root, settings, duration, has_narration):
    """assets/bgm/의 저작권 프리 곡을 골라 영상 아래에 깐다(루프·페이드). 나레이션 있으면 낮게(덕킹),
    무나레이션이면 조금 크게. 트랙이 없거나 실패하면 원래 오디오 그대로(BGM은 선택 — 렌더 안 멈춤)."""
    cfg = settings.get("bgm", {})
    if not cfg.get("enabled", True):
        return audio
    bgm_dir = Path(project_root) / cfg.get("dir", "assets/bgm")
    exts = {".mp3", ".m4a", ".wav", ".ogg", ".aac"}
    tracks = sorted(p for p in bgm_dir.glob("*") if p.suffix.lower() in exts) if bgm_dir.exists() else []
    if not tracks:
        print("[bgm] assets/bgm 트랙 없음 → BGM 생략(있으면 자동 적용)")
        return audio
    pick = random.choice(tracks)
    try:
        from moviepy import AudioFileClip, CompositeAudioClip, concatenate_audioclips
        bgm = AudioFileClip(str(pick))
        if bgm.duration and bgm.duration < duration:   # 짧으면 루프
            reps = int(duration // bgm.duration) + 1
            bgm = concatenate_audioclips([AudioFileClip(str(pick)) for _ in range(reps)])
        bgm = bgm.subclipped(0, duration)
        vol = float(cfg.get("volume_solo", 0.42) if not has_narration else cfg.get("volume_duck", 0.14))
        try:
            bgm = bgm.with_volume_scaled(vol)
        except Exception:
            from moviepy import afx
            bgm = bgm.with_effects([afx.MultiplyVolume(vol)])
        try:
            from moviepy import afx
            bgm = bgm.with_effects([afx.AudioFadeIn(float(cfg.get("fade_in", 0.8))),
                                    afx.AudioFadeOut(float(cfg.get("fade_out", 1.2)))])
        except Exception:
            pass
        mixed = CompositeAudioClip([audio, bgm]) if audio is not None else bgm
        print(f"[bgm] '{pick.name}' 적용 (vol {vol}, {'덕킹' if has_narration else '솔로'})")
        return mixed
    except Exception as e:
        print(f"[bgm] 믹싱 실패({type(e).__name__}: {e}) → BGM 생략")
        return audio


def _find_reveal_time(lines, line_windows):
    """제품이 '처음 등장'하는 순간 = 폭로 아크 ④단계(정체 공개=제품 등장) 첫 라인의 시작 시각.
    stage 정보가 없으면 None(효과음 생략) — 썰피자식 '제품 등장' 효과음 트리거용."""
    for (ls, _le), ln in zip(line_windows or [], lines or []):
        try:
            if int(ln.get("stage", 0) or 0) >= 4:
                return float(ls)
        except Exception:
            continue
    return None


def _mix_reveal_sfx(audio, reveal_time, project_root, settings, duration):
    """제품 등장 순간에 '리빌' 효과음(휘익→쨍)을 크게 얹는다 — 제품이 나온다는 걸 인식시키는 신호
    (2026-07-14 사용자 요청, 썰피자 벤치마크). 파일 없거나 시각 부적절하면 원래 오디오 그대로."""
    cfg = settings.get("sfx", {})
    if not cfg.get("enabled", True) or reveal_time is None:
        return audio
    sfx_path = Path(project_root) / cfg.get("reveal", "assets/sfx/reveal.wav")
    if not sfx_path.exists() or reveal_time < 0 or reveal_time >= duration:
        return audio
    try:
        from moviepy import AudioFileClip, CompositeAudioClip
        sfx = AudioFileClip(str(sfx_path))
        vol = float(cfg.get("reveal_volume", 0.9))   # 나레이션·BGM보다 크게(제품 등장 강조)
        try:
            sfx = sfx.with_volume_scaled(vol)
        except Exception:
            from moviepy import afx
            sfx = sfx.with_effects([afx.MultiplyVolume(vol)])
        if sfx.duration and reveal_time + sfx.duration > duration:
            sfx = sfx.subclipped(0, max(0.05, duration - reveal_time))
        sfx = sfx.with_start(float(reveal_time))
        print(f"[sfx] 제품 등장 효과음 삽입 @ {reveal_time:.1f}s (vol {vol})")
        return CompositeAudioClip([audio, sfx]) if audio is not None else sfx
    except Exception as e:
        print(f"[sfx] 효과음 실패({type(e).__name__}: {e}) → 생략")
        return audio


def _mix_sub_pop_sfx(audio, sub_plan: list, line_windows: list, project_root,
                     settings: dict, duration: float):
    """자막 리듬 효과음(2026-07-17 사용자 확정 · 썰피자 벤치마크 분석 반영) — 자막이 바뀌는
    순간마다 낮은 볼륨의 '뽁' 팝을 얹어 타닥타닥 리듬을 만든다(벤치마크는 0.35~0.5s 간격 팝).
    mode: pop=자막 팝(칸)마다(기본·벤치마크와 동일) | line=대사 라인 시작만 | off=끔.
    소리는 자체 물리 합성(assets/sfx/pop.wav) — 저작권 무관(§3.2 자체 생성물)."""
    cfg = settings.get("sfx", {})
    mode = str(cfg.get("sub_pop_mode", "off")).lower()   # 기본 off(2026-07-17 사용자 확정 — 라인 효과음만)
    if not cfg.get("enabled", True) or mode in ("off", "none", "false"):
        return audio
    path = Path(project_root) / cfg.get("sub_pop", "assets/sfx/pop.wav")
    if not path.exists():
        return audio
    if mode == "line":
        times = [float(a) for a, _b in (line_windows or [])]
    else:
        times = [float(p["start"]) for p in (sub_plan or []) if p.get("kind") == "sub"]
    times = sorted(t for t in times if 0 <= t < duration - 0.05)
    if not times:
        return audio
    try:
        import wave as _wave
        from moviepy import CompositeAudioClip
        from moviepy.audio.AudioClip import AudioArrayClip
        # wav를 직접 읽는다(AudioFileClip.to_soundarray는 짧은 클립에서 버퍼 오류) — 스테레오로 확장
        with _wave.open(str(path)) as wf:
            sr_ = wf.getframerate()
            raw = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float64) / 32768.0
            arr = raw.reshape(-1, 2) if wf.getnchannels() == 2 else np.column_stack([raw, raw])
        vol = float(cfg.get("sub_pop_volume", 0.25))   # 나레이션 아래 깔리는 낮은 리듬(기본 0.25)
        pops = [AudioArrayClip(arr * vol, fps=sr_).with_start(t) for t in times]
        print(f"[sfx] 자막 팝 {len(pops)}개 삽입 (mode={mode}, vol {vol})")
        return CompositeAudioClip([audio, *pops]) if audio is not None else CompositeAudioClip(pops)
    except Exception as e:
        print(f"[sfx] 자막 팝 실패({type(e).__name__}: {e}) → 생략")
        return audio


def _find_sfx_file(project_root, rel: str):
    """설정 경로 그대로 → 없으면 같은 이름의 다른 확장자(mp3/wav/m4a/ogg) 순회 — 관리자가
    어떤 포맷으로 업로드해도 슬롯이 잡히게."""
    p = Path(project_root) / rel
    if p.exists():
        return p
    for ext in (".mp3", ".wav", ".m4a", ".ogg"):
        q = p.with_suffix(ext)
        if q.exists():
            return q
    return None


def _mix_line_sfx(audio, lines: list, line_windows: list, reveal_time,
                  project_root, settings: dict, duration: float):
    """라인(문장) 시작마다 '문맥에 맞는' 효과음(2026-07-17 사용자 확정 · 1안 세트) —
    폭로 아크 stage별 매핑: ①훅=띠링(새 글 알림) ②공감=동동동(댓글 연타) ③지목=둥(서스펜스)
    ⑤증거=찰칵(셔터), punch 라인=띠용(스프링). ④제품 공개는 기존 '쾅'(reveal)이 담당하므로
    생략하고, reveal ±1.5s 안의 라인도 건너뛴다(소리 겹침 방지). 같은 소리가 반복되면
    0.8배씩 줄여 피로를 막는다. 파일은 관리자 설정 탭에서 업로드(없는 슬롯은 조용히 생략)."""
    cfg = settings.get("sfx", {})
    mapping = cfg.get("line_sfx") or {}
    if not cfg.get("enabled", True) or not mapping or not lines or not line_windows:
        return audio
    base_vol = float(cfg.get("line_sfx_volume", 0.35))
    guard = 1.5
    from moviepy import AudioFileClip, CompositeAudioClip
    clips, seen, missing = [], {}, set()
    for i, ln in enumerate(lines):
        if i >= len(line_windows):
            break
        t = float(line_windows[i][0])
        if t < 0 or t >= duration - 0.05:
            continue
        if reveal_time is not None and abs(t - float(reveal_time)) < guard:
            continue   # 쾅(제품 공개)과 겹침 방지
        key = "punch" if ln.get("punch") else f"stage{int(ln.get('stage', 1) or 1)}"
        rel = mapping.get(key)
        if not rel:
            continue   # stage4 등 매핑 없는 라인은 무음(쾅이 담당)
        path = _find_sfx_file(project_root, str(rel))
        if path is None:
            missing.add(key)
            continue
        try:
            sfx = AudioFileClip(str(path))
            k = seen.get(key, 0)
            seen[key] = k + 1
            vol = base_vol * (0.8 ** k)   # 같은 소리 반복 시 점감
            try:
                sfx = sfx.with_volume_scaled(vol)
            except Exception:
                from moviepy import afx
                sfx = sfx.with_effects([afx.MultiplyVolume(vol)])
            if sfx.duration and t + sfx.duration > duration:
                sfx = sfx.subclipped(0, max(0.05, duration - t))
            clips.append(sfx.with_start(t))
        except Exception as e:
            print(f"[sfx] 라인 효과음 실패({key}: {type(e).__name__}: {e}) → 생략")
    if missing:
        print(f"[sfx] 라인 효과음 파일 없음(슬롯 건너뜀): {sorted(missing)} — 관리자 설정 탭에서 업로드")
    if not clips:
        return audio
    print(f"[sfx] 라인 효과음 {len(clips)}개 삽입 (vol {base_vol}, 반복 점감)")
    return CompositeAudioClip([audio, *clips]) if audio is not None else CompositeAudioClip(clips)


def render_video(audio_path: Path, words: list, out_path: Path, settings: dict,
                 shake_windows: list | None = None, project_root: Path | None = None,
                 image_windows: list | None = None, bg_path: Path | None = None,
                 product_images: list | None = None, lines: list | None = None,
                 line_windows: list | None = None, stock_clips: list | None = None,
                 product_videos: list | None = None, scene_images: list | None = None,
                 line_images: list | None = None, has_narration: bool = True,
                 headline: str = "", thumb_hook: str = "") -> dict:
    """대본 단계(stage)별 씬 시퀀스 쇼츠 렌더. 반환: 렌더 통계 dict.

    lines(단계 포함)+line_windows가 있으면 '씬 시퀀스'로 렌더한다 — 상품 단계(①④⑤)는
    상품 사진을 켄번즈 변주로 크게 보여주고, 문제 단계(②③)는 어둡게 깐 스톡 b-roll로
    갈아끼워 '사진 한 장 고정'을 없앤다. 자막은 대본 라인(구) 단위로 또렷하게 표시한다.
    씬 정보가 없으면 기존 단일 히어로 + 단어 자막으로 폴백한다."""
    r = settings.get("render", {})
    s = settings.get("subtitle", {})
    width, height = int(r.get("width", 1080)), int(r.get("height", 1920))
    fps = int(r.get("fps", 30))
    shake_px = int(r.get("shake_px", 8))
    shake_windows = shake_windows or []
    project_root = project_root or Path.cwd()
    product_images = [Path(p) for p in (product_images or []) if Path(p).exists()]
    stock_clips = [Path(p) for p in (stock_clips or []) if Path(p).exists()]
    product_videos = [Path(p) for p in (product_videos or []) if Path(p).exists()]
    scene_images = [Path(p) for p in (scene_images or []) if Path(p).exists()]
    # line_images: lines와 정렬된 라인별 이미지(경로 또는 None). None 항목은 렌더가 폴백 처리.
    line_images = list(line_images) if line_images else []
    lines = list(lines or [])
    line_windows = list(line_windows or [])
    layout = str(r.get("layout", "framed")).lower()

    font_path = _resolve_font(project_root, s.get("font", "assets/fonts/GmarketSansBold.ttf"))

    audio = AudioFileClip(str(audio_path))
    # ── 썸네일 홀드(2026-07-17 사용자 확정): 0:00에 '헤더 제목 + 훅 이미지'만 있는(자막 없는)
    #    프레임을 잠깐 넣어 쇼츠 그리드 썸네일로 쓴다 — 쇼츠는 커스텀 썸네일 업로드가 안 되고
    #    영상 프레임에서 뽑히므로(벤치마크 채널들도 첫 프레임에 제목 카드를 굽는 방식).
    #    구현: 나레이션·자막·씬·SFX 타임라인을 통째로 +hold 시프트. 홀드 동안 화면은
    #    헤더(큰 제목)+첫 라인 이미지뿐(_plan_line_scenes가 첫 씬을 0초로 당겨 빈 화면 없음).
    thumb_hold = max(0.0, float(r.get("thumb_hold_sec", 0.5)))
    if thumb_hold > 0:
        from moviepy import CompositeAudioClip
        words = [{**w, "start": float(w.get("start", 0)) + thumb_hold,
                  "end": float(w.get("end", 0)) + thumb_hold} for w in (words or [])]
        line_windows = [(float(a) + thumb_hold, float(b) + thumb_hold) for a, b in line_windows]
        shake_windows = [(float(a) + thumb_hold, float(b) + thumb_hold) for a, b in shake_windows]
        audio = CompositeAudioClip([audio.with_start(thumb_hold)])
    duration = float(audio.duration) + 0.25

    over_w, over_h = width + 2 * shake_px, height + 2 * shake_px
    bg_dir = project_root / settings.get("assets", {}).get("backgrounds_dir", "assets/backgrounds")

    # framed 정사각형 기하 (상단바 sq_top / 정사각형 sq / 하단바 = 나머지)
    sq = int(r.get("square_size", width))
    sq_top = int(r.get("square_top", 380))
    if sq_top + sq > height:                      # 캔버스 밖으로 나가면 중앙 정렬로 안전 클램프
        sq = min(sq, width); sq_top = max(0, (height - sq) // 2)
    ch = settings.get("channel", {})
    logo_path = project_root / str(ch.get("logo", "")) if ch.get("logo") else None
    framed = (layout == "framed")
    expose = (layout == "expose")

    bg_layers, card_layers, expose_layers, sub_plan = [], [], [], []
    if expose:
        # ── expose(폭로/뉴스): 흰 배경 + 상단 뉴스헤더 + 큰 자막 + 하단 라인별 이미지 ──
        expose_layers, sub_plan = _build_expose(
            lines, line_windows, words, line_images, product_images, product_videos,
            duration, width, height, font_path, settings,
            headline or (ch.get("name", "미래마켓") + " 단독"),
            str(r.get("expose_author", "미래")).strip())
        scrim = None
        bg_name = f"expose {len(sub_plan)}라인 (뉴스헤더+큰자막+라인이미지 {sum(1 for x in (line_images or []) if x)}장)"
    elif framed:
        # ── framed: 검정 프레임 + 정사각형(항상 이미지/영상 꽉 참) + 상단 채널바 ──
        base = ImageClip(np.zeros((height, width, 3), dtype=np.uint8)).with_duration(duration)
        bg_layers = [base]
        name = ch.get("name", "미래마켓")
        if line_images and lines and line_windows:
            # ★ 라인별 배정(권장): 라인마다 다른 이미지(상품 라인만 상품 사진). 매 순간 꽉 참.
            scenes = _plan_line_scenes(duration, line_windows, line_images)
            for sc in scenes:
                card_layers.append(_square_line_clip(
                    sc, product_images, product_videos, sq, sq_top, name, font_path))
            n_img = sum(1 for x in line_images if x)
            bg_name = (f"framed 라인별 {len(scenes)}컷 (라인이미지 {n_img}/{len(line_images)}"
                       f"·상품사진 {len(product_images)}·상품영상 {len(product_videos)})")
        else:
            # 라인 이미지가 없으면 stage 기반 씬(문제=문구이미지풀, 상품=상품사진)으로 폴백
            if lines and line_windows and (product_images or product_videos or scene_images):
                scenes = _plan_scenes(duration, lines, line_windows,
                                      len(product_images), len(scene_images))
            else:  # 대본 정보가 없어도 정사각형은 항상 한 컷으로 꽉 채운다
                scenes = [{"start": 0.0, "end": duration, "kind": "product", "asset": 0, "shot": 0}]
            for sc in scenes:
                card_layers.append(_square_content_clip(
                    sc, product_images, product_videos, scene_images, sq, sq_top,
                    name, font_path))
            bg_name = (f"framed {len(scenes)}컷 (정사각형 {sq}px, 상단바 {sq_top}px / "
                       f"상품사진 {len(product_images)}·문구이미지 {len(scene_images)}·상품영상 {len(product_videos)})")
        card_layers.append(_brand_bar_clip(width, sq_top, name, ch.get("handle", ""),
                                            logo_path, font_path, duration))
        scrim = None
    else:
        # ── legacy: 흐린 상품 배경 + 히어로 카드 (과거 방식) ──
        use_scenes = (bool(line_windows) and bool(lines)
                      and bool(product_images or stock_clips or product_videos))
        if use_scenes:
            scenes = _plan_scenes(duration, lines, line_windows, len(product_images), len(stock_clips))
            for sc in scenes:
                bgc = _scene_bg_clip(sc, product_images, product_videos, stock_clips, over_w, over_h)
                bgc = (bgc.with_start(sc["start"]).with_duration(sc["end"] - sc["start"] + 0.04)
                          .with_position(_seg_shake_pos(sc["start"], shake_windows, shake_px, fps)))
                bg_layers.append(bgc)
                if sc["kind"] == "product" and product_images and not product_videos:
                    card = _product_card_clip(sc, product_images, width, height)
                    if card is not None:
                        card_layers.append(card)
            bg_name = (f"씬 {len(scenes)}컷 (상품사진 {len(product_images)}·상품영상 "
                       f"{len(product_videos)}·승인스톡 {len(stock_clips)})")
        else:
            if product_images:
                background, bg_name = _blurred_product_bg(product_images[0], over_w, over_h, duration)
            else:
                background, bg_name = _build_background(bg_dir, width, height, duration, shake_px,
                                                        override=bg_path)
            background = background.with_position(_seg_shake_pos(0.0, shake_windows, shake_px, fps))
            bg_layers = [background]
            if product_images:
                card_layers = _build_hero_clips(product_images, duration, width, height)
            else:
                card_layers = _build_image_clips(image_windows or [], duration, width)
        scrim = _subtitle_scrim(width, height, duration, s)

    # 자막(개편): 대본이 확정한 subs 칸을 그대로 팝업 + punch 라인 1회만 밈 카드.
    # ⭐ 핵심규칙: 화면 리액션 추임새(react 스티커) 전면 금지 — 자막·밈 카드 외 텍스트 오버레이 없음.
    # phrase 모드면 구(라인) 단위. 라인 정보 없으면 전체 가라오케 폴백(테스트 경로).
    if expose:
        sub_clips = []   # 자막은 _build_expose가 이미 레이어에 넣었다
    elif lines and line_windows and s.get("mode", "karaoke") == "phrase":
        sub_clips = _build_line_clips(lines, line_windows, duration, font_path, s, width)
    elif lines and line_windows:
        # 펀치라인 상황에 맞는 AI 밈 이미지(라이브러리)를 골라 밈 카드 배경으로 (글자는 렌더가 얹음)
        punch_line = next((ln for ln in lines if ln.get("punch")), None)
        meme_img = (meme_lib.select_meme(project_root, str(punch_line.get("text", "")),
                                         str(punch_line.get("meme_tag", "")))
                    if punch_line else None)
        sub_clips, sub_plan = _build_subtitles(words, lines, line_windows, duration,
                                               font_path, s, width, height, meme_img,
                                               framed=framed, sq=sq, sq_top=sq_top)
    else:
        sub_clips = _build_word_clips(words, duration, font_path, s, width)

    t0 = time.time()
    if expose:
        layers = list(expose_layers)
    else:
        layers = [*bg_layers, *card_layers]
        if scrim is not None:
            layers.append(scrim)
        layers += sub_clips
    # ── 오프닝 훅 '썸네일 페이지'(2026-07-17 사용자 확정): 0:00 홀드 동안에만 큰 훅 문구를 얹어
    #    쇼츠 그리드·공유 썸네일로 뽑히게 한다(쇼츠는 커스텀 썸네일 업로드가 안 됨). 홀드가 끝나면
    #    사라지므로 본편 화면 텍스트 규칙(하단 자막 + punch 밈 1개)엔 영향이 없다.
    if thumb_hold > 0:
        hook_clip = _thumb_hook_overlay(thumb_hook or headline, width, height,
                                        thumb_hold, font_path, settings)
        if hook_clip is not None:
            layers.append(hook_clip)
    audio = _mix_bgm(audio, project_root, settings, duration, has_narration)
    reveal_t = _find_reveal_time(lines, line_windows)
    audio = _mix_reveal_sfx(audio, reveal_t, project_root, settings, duration)
    audio = _mix_line_sfx(audio, lines, line_windows, reveal_t, project_root, settings, duration)
    audio = _mix_sub_pop_sfx(audio, sub_plan, line_windows, project_root, settings, duration)
    final = (
        CompositeVideoClip(layers, size=(width, height))
        .with_duration(duration)
        .with_audio(audio)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate=r.get("audio_bitrate", "128k"),
        preset="medium",
        ffmpeg_params=["-crf", str(r.get("crf", 20)), "-pix_fmt", "yuv420p"],
        threads=os.cpu_count() or 2,
        logger=None,
    )
    render_seconds = time.time() - t0
    final.close()
    audio.close()

    return {
        "render_seconds": round(render_seconds, 1),
        "video_duration_seconds": round(duration, 2),
        "realtime_factor": round(render_seconds / max(duration, 0.01), 2),
        "resolution": f"{width}x{height}@{fps}fps",
        "subtitle_clip_count": len(sub_clips),
        # expose는 라인 이미지가 expose_layers에 들어가므로 배정된 라인 이미지 수로 집계
        #   (예전엔 card_layers만 세서 expose 로그가 '이미지 0개'로 나오는 오해를 낳았다 — 2026-07-16)
        "image_clip_count": (sum(1 for x in (line_images or []) if x) if expose else len(card_layers)),
        "scene_count": len(bg_layers),
        "hero_from_product": bool(product_images),
        "font_used": str(font_path),
        "background_used": bg_name,
        "output_bytes": out_path.stat().st_size,
        "subtitle_plan": sub_plan,  # QA 게이트(자막=대본 일치·위치·길이) 검사 대상
    }


def _resolve_font(project_root: Path, font_rel: str) -> Path:
    """GmarketSansBold 우선, 없으면 폴더 내 아무 ttf, 최후엔 시스템 CJK 폰트(경고)."""
    font_path = (project_root / font_rel).resolve()
    if font_path.exists():
        return font_path
    fonts_dir = project_root / "assets" / "fonts"
    for cand in sorted(fonts_dir.glob("*.ttf")) + sorted(fonts_dir.glob("*.otf")):
        print(f"[render] 경고: {font_rel} 없음 → 대체 폰트 사용: {cand.name}")
        return cand
    for sys_cand in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    ):
        if Path(sys_cand).exists():
            print(f"[render] 경고: 프로젝트 폰트 없음 → 시스템 폰트 사용: {sys_cand}")
            return Path(sys_cand)
    raise FileNotFoundError(
        f"한글 폰트를 찾을 수 없습니다: {font_path} — README의 폰트 배치 안내를 따라주세요."
    )


def _build_background(bg_dir: Path, width: int, height: int, duration: float,
                      margin: int, override: Path | None = None) -> tuple:
    """배경 선택: 상품 연관 영상(override) → CC0 세로영상 랜덤 → 그라데이션 자체 생성."""
    over_w, over_h = width + 2 * margin, height + 2 * margin
    if override and Path(override).exists():
        candidates = [Path(override)]
    else:
        candidates = [p for p in sorted(bg_dir.glob("*")) if p.suffix.lower() in VIDEO_EXTS]
    if candidates:
        pick = random.choice(candidates)
        clip = VideoFileClip(str(pick)).without_audio()
        scale = max(over_w / clip.w, over_h / clip.h)
        clip = clip.resized(scale).cropped(
            x_center=clip.w * scale / 2, y_center=clip.h * scale / 2,
            width=over_w, height=over_h,
        )
        if clip.duration < duration:
            clip = clip.with_effects([vfx.Loop(duration=duration)])
        else:
            clip = clip.subclipped(0, duration)
        return clip, pick.name

    # 자체 생성 그라데이션 (딥네이비 → 퍼플, 스펙 §3.2 화이트리스트: 자체 생성물)
    top, bottom = np.array([12, 14, 34]), np.array([52, 22, 66])
    rows = np.linspace(0, 1, over_h)[:, None]
    grad = (top[None, :] * (1 - rows) + bottom[None, :] * rows).astype(np.uint8)
    frame = np.repeat(grad[:, None, :], over_w, axis=1)
    return ImageClip(frame).with_duration(duration), "(자체 생성 그라데이션)"


def _blurred_product_bg(img_path: Path, over_w: int, over_h: int, duration: float,
                        style: str = "hero") -> tuple:
    """상품 사진을 화면에 꽉 차게 흐리게+어둡게 깔아 배경으로 (항상 상품 관련).
    style='problem'은 더 어둡고 채도를 빼서 '문제 구간' 무드를 만든다(무관 스톡 대체).
    같은 사진·캔버스·스타일은 캐시해 씬마다 GaussianBlur 재계산을 피한다(렌더 속도)."""
    key = (str(img_path), int(over_w), int(over_h), style)
    arr = _BLUR_BG_CACHE.get(key)
    if arr is None:
        from PIL import Image, ImageEnhance, ImageFilter
        im = Image.open(str(img_path)).convert("RGB")
        scale = max(over_w / im.width, over_h / im.height)
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))))
        left, top = (im.width - over_w) // 2, (im.height - over_h) // 2
        im = im.crop((left, top, left + over_w, top + over_h))
        im = im.filter(ImageFilter.GaussianBlur(32))
        if style == "problem":
            im = ImageEnhance.Color(im).enhance(0.35)
            im = ImageEnhance.Brightness(im).enhance(0.32)
        else:
            im = ImageEnhance.Brightness(im).enhance(0.5)
        arr = np.array(im)
        _BLUR_BG_CACHE[key] = arr
    label = "(어두운 상품사진 배경)" if style == "problem" else "(흐린 상품사진 배경)"
    return ImageClip(arr).with_duration(duration), label


def _hero_rgba(img_path: Path, target_w: int) -> np.ndarray:
    """상품 사진을 둥근 카드 + 부드러운 그림자로 다듬은 RGBA 배열 (각진 흰 네모 방지). 캐시 적용."""
    key = (str(img_path), int(target_w))
    cached = _HERO_RGBA_CACHE.get(key)
    if cached is not None:
        return cached
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(str(img_path)).convert("RGB")
    h = max(1, round(im.height * target_w / im.width))
    im = im.resize((target_w, h))
    rad, pad = int(target_w * 0.045), 48
    mask = Image.new("L", (target_w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, target_w - 1, h - 1], radius=rad, fill=255)
    card = Image.new("RGBA", (target_w, h), (0, 0, 0, 0))
    card.paste(im, (0, 0), mask)
    canvas = Image.new("RGBA", (target_w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [pad, pad + 12, pad + target_w, pad + 12 + h], radius=rad, fill=(0, 0, 0, 130))
    canvas = Image.alpha_composite(canvas, shadow.filter(ImageFilter.GaussianBlur(20)))
    canvas.paste(card, (pad, pad), card)
    arr = np.array(canvas)
    _HERO_RGBA_CACHE[key] = arr
    return arr


def _build_hero_clips(images: list, duration: float, width: int, height: int) -> list:
    """상품 사진을 화면 주인공으로 — 둥근 카드로 크게(폭 78%) 상단 배치, 켄번즈 줌. 여러 장이면 순차."""
    clips, n = [], len(images)
    seg = duration / max(n, 1)
    target_w, top_y = int(width * 0.78), int(height * 0.13)
    for i, p in enumerate(images):
        start = i * seg
        dur = (duration - start) if i == n - 1 else seg
        if dur <= 0.1:
            continue
        try:
            base = ImageClip(_hero_rgba(Path(p), target_w), transparent=True)
            clips.append(
                base.resized(lambda t, d=dur: 1.0 + 0.06 * min(1.0, t / d))
                .with_start(start).with_duration(dur + 0.05)
                .with_position(("center", top_y))
            )
        except Exception as e:
            print(f"[render] 경고: 히어로 이미지 실패({Path(p).name}: {e}) — 건너뜀")
    return clips


# ─────────────────────────────────────────────────────────────────────────────
# framed 레이아웃(2026-07-13): 상단 검정바(채널명·로고) + 가운데 정사각형(항상 이미지/영상
# 꽉 참, 빈 화면·흐린 배경 절대 없음) + 하단 검정바(자막). 아래 함수들이 그 레이어를 만든다.
# ─────────────────────────────────────────────────────────────────────────────

def _square_cover_arr(img_path: Path, sq: int) -> np.ndarray:
    """이미지를 정사각형(sq×sq)에 꽉 차게 cover-fit(넘치는 부분 중앙 크롭)한 RGB 배열. 캐시."""
    key = (str(img_path), int(sq))
    arr = _SQUARE_ARR_CACHE.get(key)
    if arr is None:
        from PIL import Image
        im = Image.open(str(img_path)).convert("RGB")
        scale = max(sq / im.width, sq / im.height)
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))),
                       Image.LANCZOS)
        left, top = (im.width - sq) // 2, (im.height - sq) // 2
        im = im.crop((left, top, left + sq, top + sq))
        arr = np.array(im)
        _SQUARE_ARR_CACHE[key] = arr
    return arr


def _branded_fallback_arr(sq: int, name: str, font_path: Path) -> np.ndarray:
    """이미지가 하나도 없을 때조차 '빈 화면'이 없도록: 채널명이 박힌 브랜드 카드(정사각형).
    파스텔 그라데이션 + 중앙 채널명 → 흐린 배경이 아니라 의도된 브랜드 화면."""
    from PIL import Image, ImageDraw, ImageFont
    top, bottom = np.array([36, 30, 64]), np.array([88, 44, 92])
    rows = np.linspace(0, 1, sq)[:, None]
    grad = (top[None, :] * (1 - rows) + bottom[None, :] * rows).astype(np.uint8)
    im = Image.fromarray(np.repeat(grad[:, None, :], sq, axis=1)).convert("RGB")
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype(str(font_path), int(sq * 0.11))
    except Exception:
        f = ImageFont.load_default()
    tw = d.textbbox((0, 0), name, font=f)[2]
    d.text(((sq - tw) // 2, int(sq * 0.44)), name, font=f, fill="#FFFFFF",
           stroke_width=4, stroke_fill="#000000")
    return np.array(im)


def _branded_rect_arr(w: int, h: int, name: str, font_path: Path) -> np.ndarray:
    """expose 하단 영역용 브랜드 패널(가로 직사각형) — 라인 이미지·상품 사진이 하나도 없어도
    흰 여백(빈 화면)이 안 생기게 채널명 박힌 그라데이션으로 채운다(빈 화면 절대 금지 규칙)."""
    from PIL import Image, ImageDraw, ImageFont
    top, bottom = np.array([36, 30, 64]), np.array([88, 44, 92])
    rows = np.linspace(0, 1, max(1, h))[:, None]
    grad = (top[None, :] * (1 - rows) + bottom[None, :] * rows).astype(np.uint8)
    im = Image.fromarray(np.repeat(grad[:, None, :], w, axis=1)).convert("RGB")
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype(str(font_path), int(min(w, h) * 0.12))
    except Exception:
        f = ImageFont.load_default()
    tw = d.textbbox((0, 0), name, font=f)[2]
    d.text(((w - tw) // 2, int(h * 0.42)), name, font=f, fill="#FFFFFF",
           stroke_width=4, stroke_fill="#000000")
    return np.array(im)


def _square_content_clip(scene: dict, product_images: list, product_videos: list,
                         scene_images: list, sq: int, sq_top: int, name: str,
                         font_path: Path):
    """정사각형 콘텐츠 1컷 — 항상 실사 이미지/영상으로 꽉 채운다(흐린 배경·빈 화면 금지).
    우선순위: 제품 영상 → (문제 씬)문구 매칭 이미지 → 상품 사진 → 브랜드 카드.
    반환: (0, sq_top)에 배치된 sq×sq 클립. 어떤 경우에도 None이 아니다."""
    dur = scene["end"] - scene["start"]
    start = scene["start"]
    kind = scene.get("kind")

    # 1) 상품 씬 + 제품 실사용 영상 → 정사각형 cover-fit(모션 있음, 켄번즈 불필요)
    if kind == "product" and product_videos:
        v = _video_fullframe(product_videos[scene.get("asset", 0) % len(product_videos)],
                             sq, sq, dur)
        if v is not None:
            return v.with_start(start).with_position((0, sq_top))

    # 2) 이미지 소스 선택: 문제 씬은 문구 매칭 이미지 우선, 없으면 상품 사진(둘 다 없으면 브랜드 카드)
    src = None
    if kind == "problem" and scene_images:
        src = scene_images[scene.get("asset", 0) % len(scene_images)]
    elif product_images:
        src = product_images[scene.get("asset", 0) % len(product_images)]
    elif scene_images:
        src = scene_images[scene.get("asset", 0) % len(scene_images)]

    if src is not None:
        try:
            arr = _square_cover_arr(Path(src), sq)
        except Exception as e:
            print(f"[render] 경고: 정사각형 이미지 실패({Path(src).name}: {e}) → 브랜드 카드")
            arr = _branded_fallback_arr(sq, name, font_path)
    else:
        arr = _branded_fallback_arr(sq, name, font_path)

    # 켄번즈(줌인/줌아웃 교대) — 넘침은 sq×sq 내부 합성으로 클립(바 영역 침범 방지)
    zoom_in = int(scene.get("shot", 0)) % 2 == 0
    base = ImageClip(arr)
    if zoom_in:
        kb = base.resized(lambda t, d=dur: 1.0 + 0.08 * min(1.0, t / d))
    else:
        kb = base.resized(lambda t, d=dur: 1.08 - 0.08 * min(1.0, t / d))
    kb = kb.with_position(("center", "center"))
    inner = CompositeVideoClip([kb], size=(sq, sq)).with_duration(dur + 0.05)
    return inner.with_start(start).with_position((0, sq_top))


def _plan_line_scenes(duration: float, line_windows: list, line_images: list) -> list:
    """라인별 씬 — [0,duration] 연속 커버(빈 구간 없음). 각 라인의 이미지 1장 = 1컷.
    line_images[i]가 '여러 장(리스트)'이면 그 라인 구간을 균등 분할해 순서대로 슬라이드쇼로 보여준다
    (운영자가 한 구간에 여러 장 고른 경우 — 2026-07-14 사용자 확정)."""
    def as_list(v):
        if v is None:
            return []
        return list(v) if isinstance(v, (list, tuple)) else [v]

    scenes = []
    for i, (ls, le) in enumerate(line_windows):
        imgs = as_list(line_images[i]) if i < len(line_images) else []
        ls, le = float(ls), float(le)
        if not imgs:
            scenes.append({"start": ls, "end": le, "img": None, "shot": len(scenes)})
            continue
        span = (le - ls) / len(imgs)
        for j, im in enumerate(imgs):
            scenes.append({"start": ls + j * span, "end": ls + (j + 1) * span,
                           "img": im, "shot": len(scenes)})
    if not scenes:
        first = None
        if line_images:
            f0 = line_images[0]
            first = (f0[0] if isinstance(f0, (list, tuple)) and f0 else (None if isinstance(f0, (list, tuple)) else f0))
        return [{"start": 0.0, "end": duration, "img": first, "shot": 0}]
    scenes[0]["start"] = 0.0
    for i in range(1, len(scenes)):
        scenes[i]["start"] = scenes[i - 1]["end"]
    scenes[-1]["end"] = duration
    return [s for s in scenes if s["end"] - s["start"] > 0.05]


def _square_line_clip(sc: dict, product_images: list, product_videos: list,
                      sq: int, sq_top: int, name: str, font_path: Path):
    """라인 1컷의 정사각형 콘텐츠 — 그 라인에 배정된 이미지로 꽉 채운다(cover-fit + 켄번즈).
    상품 라인(이미지가 상품 사진)에서 제품 영상이 있으면 영상을 우선. 어떤 경우에도 빈 화면 없음."""
    dur = sc["end"] - sc["start"]
    start = sc["start"]
    src = sc.get("img")
    prod_set = {str(Path(p)) for p in product_images}
    is_product_line = src is not None and str(Path(src)) in prod_set

    if is_product_line and product_videos:
        v = _video_fullframe(product_videos[0], sq, sq, dur)
        if v is not None:
            return v.with_start(start).with_position((0, sq_top))

    # 움짤(GIF)·영상 라인 이미지 → 정사각형에 '움직이는' 배경으로(더 코믹·자주 바뀜)
    if src is not None and Path(src).suffix.lower() in VIDEO_EXTS | {".gif"}:
        v = _video_fullframe(src, sq, sq, dur)
        if v is not None:
            return v.with_start(start).with_position((0, sq_top))

    if src is None:
        src = product_images[0] if product_images else None
    if src is None:
        arr = _branded_fallback_arr(sq, name, font_path)
    else:
        try:
            arr = _square_cover_arr(Path(src), sq)
        except Exception as e:
            print(f"[render] 경고: 라인 이미지 실패({Path(src).name}: {e}) → 브랜드 카드")
            arr = _branded_fallback_arr(sq, name, font_path)

    zoom_in = int(sc.get("shot", 0)) % 2 == 0
    base = ImageClip(arr)
    if zoom_in:
        kb = base.resized(lambda t, d=dur: 1.0 + 0.08 * min(1.0, t / d))
    else:
        kb = base.resized(lambda t, d=dur: 1.08 - 0.08 * min(1.0, t / d))
    kb = kb.with_position(("center", "center"))
    inner = CompositeVideoClip([kb], size=(sq, sq)).with_duration(dur + 0.05)
    return inner.with_start(start).with_position((0, sq_top))


def _brand_bar_clip(width: int, bar_h: int, name: str, handle: str,
                    logo_path: Path | None, font_path: Path, duration: float):
    """상단 검정바에 얹을 채널 아이덴티티(로고 있으면 로고+채널명, 없으면 워드마크). 전체 길이 표시."""
    from PIL import Image, ImageDraw, ImageFont
    canvas = Image.new("RGBA", (width, bar_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    try:
        name_font = ImageFont.truetype(str(font_path), int(bar_h * 0.30))
        sub_font = ImageFont.truetype(str(font_path), int(bar_h * 0.13))
    except Exception:
        name_font = sub_font = ImageFont.load_default()

    logo_im = None
    if logo_path and Path(logo_path).exists():
        try:
            lg = Image.open(str(logo_path)).convert("RGBA")
            lh = int(bar_h * 0.5)
            logo_im = lg.resize((max(1, round(lg.width * lh / lg.height)), lh), Image.LANCZOS)
        except Exception as e:
            print(f"[render] 경고: 로고 로드 실패({e}) → 워드마크만")

    nb = d.textbbox((0, 0), name, font=name_font)
    nw, nh = nb[2] - nb[0], nb[3] - nb[1]
    gap = int(bar_h * 0.08)
    if logo_im is not None:
        total_w = logo_im.width + gap + nw
        x0 = (width - total_w) // 2
        cy = int(bar_h * 0.40)
        canvas.alpha_composite(logo_im, (x0, cy - logo_im.height // 2))
        tx = x0 + logo_im.width + gap
    else:
        tx = (width - nw) // 2
        cy = int(bar_h * 0.40)
    d.text((tx, cy - nh // 2 - nb[1]), name, font=name_font, fill="#FFFFFF",
           stroke_width=3, stroke_fill="#000000")
    if handle:
        hb = d.textbbox((0, 0), handle, font=sub_font)
        d.text(((width - (hb[2] - hb[0])) // 2, int(bar_h * 0.70)), handle,
               font=sub_font, fill="#C9B8FF")
    return (ImageClip(np.array(canvas), transparent=True)
            .with_duration(duration).with_position((0, 0)))


# ─────────────────────────────────────────────────────────────────────────────
# expose(폭로/뉴스) 레이아웃 — 흰 배경 + 상단 가짜 뉴스헤더(채널명·기사제목) + 큰 검정 자막(상단)
# + 라인별 full-width 이미지(하단). 참고 포맷(썰피자식)의 '구조'만 차용, 대본·콘텐츠는 오리지널.
# ─────────────────────────────────────────────────────────────────────────────

def _cover_rect_arr(img_path: Path, w: int, h: int) -> np.ndarray:
    """이미지를 w×h에 cover-fit(중앙 크롭)한 RGB 배열. 캐시."""
    key = ("rect", str(img_path), int(w), int(h))
    arr = _SQUARE_ARR_CACHE.get(key)
    if arr is None:
        from PIL import Image
        im = Image.open(str(img_path)).convert("RGB")
        scale = max(w / im.width, h / im.height)
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
        left, top = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((left, top, left + w, top + h))
        arr = np.array(im)
        _SQUARE_ARR_CACHE[key] = arr
    return arr


def _board_meta(author: str, headline: str) -> str:
    """게시판 글 메타줄 — 작성자 · 조회수 · 시간. 조회수는 headline에서 결정론적으로 파생
    (같은 영상=같은 수치, 다른 영상=다른 수치). '방금 전'으로 최신 글 느낌(바이럴 심리)."""
    seed = sum(ord(c) for c in (headline or "x"))
    views = 12000 + (seed * 733) % 388000
    v = f"{views / 10000:.1f}만".replace(".0만", "만")
    return f"{author} · 조회 {v} · 방금 전"


def _expose_header_arr(width: int, header_h: int, board: str, headline: str,
                       meta: str, font_path: Path, tag: str = "") -> np.ndarray:
    """상단 헤더 — 한국 커뮤니티 '게시판 글' 스타일(심플하게 재설계, 2026-07-14).
    구성: 슬림 보드바(로고+보드명) → 카테고리 칩 → 굵은 글 제목(좌측 정렬, ≤2줄)
    → 작성자·조회수·시간 메타줄 → 얇은 구분선. 흰 배경에 검정 텍스트로 담백하게.
    유튜브 쇼츠 UI 고려: 모든 텍스트 '좌측 정렬'(우측 좋아요·댓글·공유 버튼 영역 회피) +
    상단 안전존 배치(하단 캡션·채널 오버레이와 안 겹침)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (width, header_h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    mx = int(width * 0.05)                       # 좌우 여백(게시판 글 들여쓰기)

    # 1) 보드바(슬림): 연회색 배경 + 로고 사각형(보드 첫 글자) + 보드명 + 하단 헤어라인
    bar_h = int(header_h * 0.23)
    d.rectangle([0, 0, width, bar_h], fill=(244, 244, 246))
    logo = int(bar_h * 0.56)
    ly = (bar_h - logo) // 2
    d.rounded_rectangle([mx, ly, mx + logo, ly + logo], radius=int(logo * 0.28), fill=(212, 170, 76))
    lf = ImageFont.truetype(str(font_path), int(logo * 0.58))
    ch0 = (board or "미")[0]
    lb = d.textbbox((0, 0), ch0, font=lf)
    d.text((mx + (logo - (lb[2] - lb[0])) // 2 - lb[0], ly + (logo - (lb[3] - lb[1])) // 2 - lb[1]),
           ch0, font=lf, fill=(255, 255, 255))
    bnf = ImageFont.truetype(str(font_path), int(bar_h * 0.4))
    bnb = d.textbbox((0, 0), board, font=bnf)
    d.text((mx + logo + int(width * 0.022), (bar_h - (bnb[3] - bnb[1])) // 2 - bnb[1]),
           board, font=bnf, fill=(44, 44, 48))
    d.line([(0, bar_h), (width, bar_h)], fill=(228, 228, 232), width=2)

    y = bar_h + int(header_h * 0.05)
    # 2) 카테고리 칩(게시판 태그 느낌) — 브랜드 골드 배경
    if tag:
        tf = ImageFont.truetype(str(font_path), int(header_h * 0.072))
        tb = d.textbbox((0, 0), tag, font=tf)
        cw, chh = (tb[2] - tb[0]) + int(width * 0.045), (tb[3] - tb[1]) + int(header_h * 0.045)
        d.rounded_rectangle([mx, y, mx + cw, y + chh], radius=int(chh * 0.34), fill=(212, 170, 76))
        d.text((mx + (cw - (tb[2] - tb[0])) // 2 - tb[0], y + (chh - (tb[3] - tb[1])) // 2 - tb[1]),
               tag, font=tf, fill=(40, 30, 8))
        y += chh + int(header_h * 0.028)

    # 3) 글 제목(좌측 정렬, 굵은 검정, ≤2줄) — 후킹의 핵심이라 크게(2026-07-17, header 410 기준 ≈72px)
    hf = ImageFont.truetype(str(font_path), int(header_h * 0.175))
    for ln in _wrap_pil(headline, hf, width - 2 * mx, max_lines=2):
        d.text((mx, y), ln, font=hf, fill=(20, 20, 20))
        y += int(header_h * 0.185)

    # 4) 메타줄(작성자 · 조회수 · 시간) — 게시판 핵심 신호
    if meta:
        mf = ImageFont.truetype(str(font_path), int(header_h * 0.07))
        d.text((mx, y + 4), meta, font=mf, fill=(140, 140, 146))

    d.line([(0, header_h - 3), (width, header_h - 3)], fill=(226, 226, 230), width=3)
    return np.array(im)


def _thumb_hook_overlay(text: str, width: int, height: int, hold: float,
                        font_path: Path, settings: dict):
    """0:00 썸네일 홀드 동안에만 보이는 '오프닝 훅 카드'(2026-07-17).
    큰 훅 문구를 화면 중앙에 굵게(노랑 글자 + 검정 두꺼운 외곽선 + 반투명 검정 밴드) 얹어
    쇼츠 그리드·공유용 썸네일로 뽑히게 한다. 홀드가 끝나면(본편 시작) 사라진다."""
    from PIL import Image, ImageDraw, ImageFont
    text = " ".join(str(text or "").split()).strip()
    if not text or hold <= 0:
        return None
    s = settings.get("subtitle", {})
    max_fs = int(s.get("thumb_hook_font_size", 116))
    min_fs = int(s.get("thumb_hook_font_min", 60))
    mx = int(width * 0.07)
    avail = width - 2 * mx
    # 글씨 크기를 줄여가며 '단어 안 끊고 2줄 이내'에 딱 들어오는 최대 폰트를 찾는다(사용자 지시).
    fs, lines = max_fs, None
    while fs >= min_fs:
        f = ImageFont.truetype(str(font_path), fs)
        wrapped = _wrap_pil(text, f, avail, max_lines=99)   # 말줄임 없이 실제 줄 수만 확인
        if len(wrapped) <= 2:
            lines = wrapped
            break
        fs -= 4
    if lines is None:                                        # 최소 폰트로도 2줄 초과 → 최소 폰트 2줄(말줄임)
        fs = min_fs
        lines = _wrap_pil(text, ImageFont.truetype(str(font_path), fs), avail, max_lines=2)
    font = ImageFont.truetype(str(font_path), fs)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lh = int(fs * 1.22)
    block_h = lh * len(lines)
    top = int(height * 0.46) - block_h // 2          # 화면 중앙(헤더/하단 이미지와 안 겹치는 미들존)
    pad = int(fs * 0.42)
    d.rectangle([0, top - pad, width, top + block_h + pad], fill=(0, 0, 0, 150))
    y = top
    for ln in lines:
        b = d.textbbox((0, 0), ln, font=font, stroke_width=8)
        d.text(((width - (b[2] - b[0])) // 2 - b[0], y), ln, font=font,
               fill="#FFE86B", stroke_width=8, stroke_fill="#000000")
        y += lh
    return (ImageClip(np.array(img), transparent=True)
            .with_duration(hold).with_start(0).with_position((0, 0)))


def _expose_image_clip(src, start: float, end: float, width: int, img_top: int, img_h: int,
                       product_images: list, product_videos: list):
    """하단 full-width 이미지/영상 — cover-fit. 상품 라인+제품영상이면 영상, GIF/영상이면 재생."""
    dur = end - start
    if dur <= 0.05:
        return None
    prod_set = {str(Path(p)) for p in product_images}
    if src is not None and str(Path(src)) in prod_set and product_videos:
        v = _video_fullframe(product_videos[0], width, img_h, dur)
        if v is not None:
            return v.with_start(start).with_position((0, img_top))
    if src is not None and Path(src).suffix.lower() in VIDEO_EXTS | {".gif"}:
        v = _video_fullframe(src, width, img_h, dur)
        if v is not None:
            return v.with_start(start).with_position((0, img_top))
    if src is None:
        return None
    try:
        arr = _cover_rect_arr(Path(src), width, img_h)
    except Exception as e:
        print(f"[render] 경고: expose 이미지 실패({Path(src).name}: {e})")
        return None
    kb = ImageClip(arr).resized(lambda t, d=dur: 1.0 + 0.05 * min(1.0, t / d)).with_position(("center", "center"))
    inner = CompositeVideoClip([kb], size=(width, img_h)).with_duration(dur + 0.05)
    return inner.with_start(start).with_position((0, img_top))


def _sub_events(words: list, lines: list, line_windows: list, duration: float) -> list:
    """라인별 subs(대본이 확정한 자막 칸)를 단어 타임스탬프에 맞춰 (sub, start, end, show_end)
    가라오케 이벤트로 변환한다(_build_subtitles의 타이밍 규칙과 동일 — expose 가라오케 공용).
    ⭐ 렌더러는 자막을 재분할하지 않는다: subs가 곧 자막(1~3어절, 단어단위). 계약 위반 시 통문장 폴백."""
    events, cursor = [], 0
    for li, ((ls, le), ln) in enumerate(zip(line_windows, lines)):
        text = str(ln.get("text", "")).strip()
        n = len(text.split())
        lwords = words[cursor:cursor + n]
        cursor += n
        ls, le = max(0.0, float(ls)), min(float(le), duration)
        if not text or le - ls < 0.1:
            continue
        subs = [str(x).strip() for x in (ln.get("subs") or []) if str(x).strip()]
        if not subs or " ".join(subs) != text:
            subs = [text]
        wi = 0
        for sub in subs:
            k = len(sub.split())
            grp = lwords[wi:wi + k]
            wi += k
            if grp:
                a, b = float(grp[0]["start"]), float(grp[-1]["end"])
            else:   # 타임스탬프 부족 방어: 라인 구간을 글자수 비례 배분
                done = sum(len(x) for x in subs[:subs.index(sub)]) or 0
                total = sum(len(x) for x in subs) or 1
                a = ls + (le - ls) * done / total
                b = min(le, a + (le - ls) * len(sub) / total)
            events.append({"text": sub, "start": a, "end": b, "line_i": li})
    for i, ev in enumerate(events):   # 다음 팝업 시작까지 유지(빈 화면 방지), 발화 종료 +0.45s 이내
        nxt = events[i + 1]["start"] if i + 1 < len(events) else duration
        ev["show_end"] = min(max(nxt, ev["start"] + 0.12), ev["end"] + 0.45, duration)
    return events


def _caption_band_arr(w: int, h: int, alpha: int = 150, radius: int = 30):
    """가라오케 자막 뒤 반투명 어두운 캡션바(흰 게시판 배경에서 노랑 글자 가독성 확보)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=(0, 0, 0, alpha))
    return np.asarray(im)


def _build_expose(lines: list, line_windows: list, words: list, line_images: list, product_images: list,
                  product_videos: list, duration: float, width: int, height: int,
                  font_path: Path, settings: dict, headline: str, author: str) -> tuple:
    """expose 레이아웃 전체 레이어 + QA용 sub_plan 반환."""
    r = settings.get("render", {})
    s = settings.get("subtitle", {})
    ch = settings.get("channel", {})
    header_h = int(r.get("expose_header_h", 340))
    sub_top = header_h + int(r.get("expose_sub_gap", 26))
    sub_h = int(r.get("expose_sub_h", 300))
    img_top = sub_top + sub_h + int(r.get("expose_img_gap", 12))
    img_h = height - img_top
    box_w = int(width * 0.92)

    layers = [ImageClip(np.full((height, width, 3), 255, dtype=np.uint8)).with_duration(duration)]
    # 하단 라인별 이미지 (라인 이미지 → 상품 사진0 → 브랜드 패널 순으로 항상 꽉 채움)
    # ⭐ 상품 사진 폴백 제거(2026-07-15 사용자 개선 #3): 라인에 배정된 이미지(sc["img"])만 쓴다.
    #   비어 있으면 상품 사진으로 때우지 않고 브랜드 패널로 채운다 → 상품 사진이 많은 라인에 반복 노출되지 않음.
    #   (상품 사진은 운영자가 그 라인에 상품을 고른 경우에만 sc["img"]로 들어온다 — load_selections/plan)
    for sc in _plan_line_scenes(duration, line_windows, line_images or []):
        clip = _expose_image_clip(sc.get("img"), sc["start"], sc["end"],
                                  width, img_top, img_h, product_images, product_videos)
        if clip is None:   # 라인 이미지 없거나 로드 실패 → 빈 흰 여백 대신 브랜드 패널
            d = sc["end"] - sc["start"]
            if d > 0.05:
                arr = _branded_rect_arr(width, img_h, ch.get("name", "미래마켓"), font_path)
                clip = (ImageClip(arr).with_duration(d + 0.05)
                        .with_start(sc["start"]).with_position((0, img_top)))
        if clip is not None:
            layers.append(clip)
    # 상단 헤더(전체 길이) — 게시판 글 스타일(보드명·카테고리 칩·제목·메타줄)
    board = ch.get("name", "미래마켓")
    tag = str(r.get("expose_tag", "실화")).strip()
    meta = _board_meta(author, headline)
    layers.append(ImageClip(_expose_header_arr(width, header_h, board, headline, meta, font_path, tag))
                  .with_duration(duration).with_position((0, 0)))
    # 상단 자막 밴드 = 가라오케(대본 subs 단위로 어절별 팝업, 통문장 폐지 — 2026-07-15 사용자 지시).
    #   ⭐ 제목 vs 자막 구분(2026-07-17 사용자 지시): 제목(헤더)은 '큰 굵은 검정', 자막(대사)은
    #   제목보다 작게 + '노란 형광펜 하이라이트' 위 검정 글자 — 게시판 글에 형광펜 친 본문 느낌.
    #   같은 폰트·같은 검정·자막이 더 컸던 이전 상태가 위계 혼란의 원인이라 크기·배경으로 분리.
    kfs = int(s.get("expose_font_size", 62))      # 자막은 헤더 제목(≈72px)보다 확실히 작게
    kcolor = s.get("expose_color", "#141414")     # 흰 배경 게시판 본문 = 진한 검정(QA 검사색 유지)
    kstroke = s.get("expose_stroke_color", "#FFFFFF")
    ksw = int(s.get("expose_stroke_width", 0))    # 흰 배경이라 외곽선 불필요(0)
    hl_color = str(s.get("expose_hl_color", "#FFE86B"))   # 형광펜 노랑("" 또는 off면 하이라이트 없음)
    band_h = min(sub_h, int(kfs * 1.7))
    band_top = sub_top + max(0, (sub_h - band_h) // 2)
    ky = band_top + max(0, (band_h - kfs) // 2)   # 자막 팝업 top y — 전 자막 동일(QA: y 1곳)
    events = _sub_events(words, lines, line_windows, duration)
    plan = []
    for ev in events:
        clip = _fit_text(ev["text"], font_path, kfs, kcolor, kstroke, ksw, box_w)
        if hl_color and hl_color.lower() not in ("off", "none", "false"):
            clip = _highlight_unit(clip, kfs, hl_color)   # 노란 형광펜 배경과 한 덩어리로
        clip = clip.resized(lambda t: _pop_scale(t, 0.14, 0.6))   # 등장 바운스
        layers.append(clip.with_start(ev["start"]).with_end(ev["show_end"]).with_position(("center", ky)))
        plan.append({"kind": "sub", "text": ev["text"], "start": round(ev["start"], 3),
                     "end": round(ev["show_end"], 3), "y": ky, "line_i": ev["line_i"]})
    return layers, plan


def _highlight_unit(txt_clip, font_size: int, color: str):
    """자막 글자 뒤에 '형광펜' 라운드 사각형을 깔아 한 덩어리 클립으로 — 제목(순수 검정 굵은
    글씨)과 자막(형광펜 위 검정)을 한눈에 구분(2026-07-17). 팝 바운스는 덩어리째 적용된다."""
    from PIL import Image, ImageDraw
    pad_x, pad_y = int(font_size * 0.26), int(font_size * 0.14)
    w, h = int(txt_clip.w) + 2 * pad_x, int(txt_clip.h) + 2 * pad_y
    rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w - 1, h - 1], radius=int(h * 0.18),
                                         fill=(*rgb, 255))
    bg = ImageClip(np.array(im), transparent=True)
    return CompositeVideoClip([bg.with_position((0, 0)), txt_clip.with_position((pad_x, pad_y))],
                              size=(w, h))


def _subtitle_scrim(width: int, height: int, duration: float, s: dict):
    """자막 뒤 반투명 어둠(위→아래로 짙어짐) — 밝은 배경에서도 자막 가독성 확보."""
    y = int(s.get("y", 1250))
    band_top = max(0, y - 150)
    band_h = height - band_top
    if band_h < 10:
        return None
    ramp = np.linspace(0.0, 1.0, band_h)
    alpha = (np.clip(ramp / 0.45, 0.0, 1.0) * 165).astype(np.uint8)
    rgba = np.zeros((band_h, width, 4), dtype=np.uint8)
    rgba[..., 3] = alpha[:, None]
    return ImageClip(rgba, transparent=True).with_duration(duration).with_position((0, band_top))


def _build_image_clips(image_windows: list, duration: float, width: int) -> list:
    """상품 이미지 오버레이 — image_cue 라인 시작에 등장, 상단 중앙,
    줌인 1.00→1.08 선형 보간 (스펙 §M6-2). 실패한 이미지는 건너뛴다."""
    clips = []
    for start, end, img_path in image_windows:
        end = min(float(end), duration)
        start = max(0.0, float(start))
        dur = end - start
        if dur <= 0.1 or not Path(img_path).exists():
            continue
        try:
            base = ImageClip(str(img_path))
            target_w = int(width * 0.68)
            base = base.resized(width=target_w)
            clip = (
                base.resized(lambda t, d=dur: 1.0 + 0.08 * min(1.0, t / d))
                .with_start(start).with_duration(dur)
                .with_position(("center", 150))
            )
            clips.append(clip)
        except Exception as e:
            print(f"[render] 경고: 이미지 오버레이 실패({Path(img_path).name}: {e}) — 건너뜀")
    return clips


def _plan_scenes(duration: float, lines: list, line_windows: list,
                 n_product: int, n_stock: int) -> list:
    """대본을 단계(stage) 연속 구간으로 묶고 각 단계마다 1~2컷 배정 (총 5단계면 5~10컷).
    문제 단계(②③)는 'problem' 씬(승인 스톡 → 없으면 어두운 상품 배경 변주),
    나머지는 상품 사진(컷마다 켄번즈 변주) — 무관한 자동 스톡은 쓰지 않는다."""
    problem = {2, 3}
    pairs = [((float(st), float(en)), int(ln.get("stage", 1) or 1))
             for (st, en), ln in zip(line_windows, lines)]
    if not pairs:
        return []
    groups = [[pairs[0][0][0], pairs[0][0][1], pairs[0][1]]]  # [start, end, stage]
    for (st, en), stg in pairs[1:]:
        if stg == groups[-1][2]:
            groups[-1][1] = en
        else:
            groups.append([st, en, stg])
    groups[0][0] = 0.0
    groups[-1][1] = duration
    for i in range(1, len(groups)):
        groups[i][0] = groups[i - 1][1]

    scenes, prod_i, stock_i, shot = [], 0, 0, 0
    for st, en, stg in groups:
        dur = en - st
        if dur <= 0.05:
            continue
        kind = "problem" if stg in problem else "product"
        n = 2 if dur >= 4.0 else 1  # 4초 이상 단계는 2컷, 아니면 1컷 → 단계당 1~2개
        step = dur / n
        for j in range(n):
            a = st + j * step
            b = en if j == n - 1 else a + step
            if kind == "problem":
                scenes.append({"start": a, "end": b, "kind": "problem",
                               "asset": (stock_i % n_stock) if n_stock else (prod_i % max(n_product, 1))})
                stock_i += 1
                prod_i += 1
            else:
                scenes.append({"start": a, "end": b, "kind": "product",
                               "asset": prod_i % max(n_product, 1), "shot": shot})
                prod_i += 1
                shot += 1
    return scenes


def _video_fullframe(path, over_w: int, over_h: int, dur: float, darken: float = 1.0):
    """영상을 화면에 꽉 차게(cover) 잘라 오디오 길이에 맞춰 루프/트림, 필요 시 어둡게. 실패 시 None."""
    try:
        clip = VideoFileClip(str(path)).without_audio()
        scale = max(over_w / clip.w, over_h / clip.h)
        clip = clip.resized(scale).cropped(
            x_center=clip.w * scale / 2, y_center=clip.h * scale / 2,
            width=over_w, height=over_h)
        if clip.duration < dur:
            clip = clip.with_effects([vfx.Loop(duration=dur)])
        else:
            clip = clip.subclipped(0, dur)
        if darken < 1.0:
            clip = clip.with_effects([vfx.MultiplyColor(darken)])
        return clip
    except Exception as e:
        print(f"[render] 경고: 영상 로드 실패({Path(path).name}: {e}) — 대체 배경")
        return None


def _scene_bg_clip(scene: dict, product_images: list, product_videos: list,
                   stock_clips: list, over_w: int, over_h: int):
    """씬 배경: 문제 씬=운영자 승인 스톡(있으면)·없으면 어두운 상품 배경 변주(항상 상품 관련),
    상품 씬=제품 실사용 영상(있으면)·아니면 흐린 상품 사진, 최후엔 그라데이션."""
    dur = scene["end"] - scene["start"]
    if scene["kind"] == "problem":
        if stock_clips:  # 운영자가 후보 그리드에서 직접 고른 클립만 들어온다
            clip = _video_fullframe(stock_clips[scene["asset"] % len(stock_clips)],
                                    over_w, over_h, dur, darken=0.55)
            if clip is not None:
                return clip
        if product_images:  # 어둡고 색 빠진 상품 배경 — '문제 구간' 무드, 무관 장면 원천 차단
            clip, _ = _blurred_product_bg(
                Path(product_images[scene.get("asset", 0) % len(product_images)]),
                over_w, over_h, dur, style="problem")
            return clip
    if scene["kind"] == "product" and product_videos:
        clip = _video_fullframe(product_videos[scene.get("asset", 0) % len(product_videos)],
                                over_w, over_h, dur, darken=0.82)  # 제품이 주인공 → 살짝만
        if clip is not None:
            return clip
    if scene["kind"] == "product" and product_images:
        clip, _ = _blurred_product_bg(Path(product_images[scene.get("asset", 0) % len(product_images)]),
                                      over_w, over_h, dur)
        return clip
    top, bottom = np.array([12, 14, 34]), np.array([44, 20, 60])
    rows = np.linspace(0, 1, over_h)[:, None]
    grad = (top[None, :] * (1 - rows) + bottom[None, :] * rows).astype(np.uint8)
    frame = np.repeat(grad[:, None, :], over_w, axis=1)
    if scene["kind"] == "problem":
        frame = (frame * 0.75).astype(np.uint8)
    return ImageClip(frame).with_duration(dur)


def _product_card_clip(scene: dict, product_images: list, width: int, height: int):
    """상품 히어로 카드 — 컷마다 켄번즈(줌인/줌아웃 교대)로 변주. 실패 시 None."""
    img = product_images[scene.get("asset", 0) % len(product_images)]
    dur = scene["end"] - scene["start"]
    try:
        base = ImageClip(_hero_rgba(Path(img), int(width * 0.78)), transparent=True)
    except Exception as e:
        print(f"[render] 경고: 히어로 카드 실패({Path(img).name}: {e}) — 건너뜀")
        return None
    # 등장 바운스(0.88→1) × 켄번즈(줌인/줌아웃 교대) — 팝업되는 느낌 + 컷마다 변주
    if int(scene.get("shot", 0)) % 2 == 0:
        def zoom(t, d=dur):
            return _pop_scale(t, 0.2, 0.88) * (1.0 + 0.07 * min(1.0, t / d))
    else:
        def zoom(t, d=dur):
            return _pop_scale(t, 0.2, 0.88) * (1.07 - 0.07 * min(1.0, t / d))
    return (base.resized(zoom)
            .with_start(scene["start"]).with_duration(dur + 0.05)
            .with_position(("center", int(height * 0.12))))


def _seg_shake_pos(seg_start: float, shake_windows: list, shake_px: int, fps: int):
    """세그먼트 배경 위치 함수(절대 시각 기준 punch 쉐이크). 쉐이크 없으면 고정 오프셋."""
    base = (-shake_px, -shake_px)
    if not shake_windows:
        return base

    def pos(t):
        at = float(t) + seg_start
        for a, b in shake_windows:
            if a <= at <= b:
                rnd = random.Random(int(at * fps) * 9973 + 7)
                return (base[0] + rnd.randint(-shake_px, shake_px),
                        base[1] + rnd.randint(-shake_px, shake_px))
        return base

    return pos


def _build_line_clips(lines: list, line_windows: list, duration: float,
                      font_path: Path, s: dict, width: int) -> list:
    """대본 라인(구) 단위 자막 — 한 구절을 발화 구간 내내 표시(필요 시 2줄 자동 줄바꿈).
    단어 하나씩 튀던 방식보다 읽기 쉽다."""
    font_size = int(s.get("phrase_font_size", 64))
    color = s.get("phrase_color", "#FFFFFF")
    stroke_color = s.get("stroke_color", "#000000")
    stroke_width = int(s.get("stroke_width", 6))
    y = int(s.get("phrase_y", 1130))
    box_w = int(width * 0.86)
    pad = stroke_width * 3 + 14
    clips = []
    for (start, end), ln in zip(line_windows, lines):
        start = max(0.0, float(start))
        end = min(float(end), duration)
        if end - start < 0.15:
            continue
        txt = str(ln.get("text", "")).strip()
        if not txt:
            continue
        tc = None
        for extra in (dict(text_align="center"), {}):
            try:
                tc = TextClip(text=txt, font=str(font_path), font_size=font_size,
                              color=color, stroke_color=stroke_color, stroke_width=stroke_width,
                              method="caption", size=(box_w, None), margin=(pad, pad), **extra)
                break
            except TypeError:
                continue
        if tc is None:
            continue
        clips.append(tc.with_start(start).with_end(end).with_position(("center", y)))
    return clips


# 긴 어절을 쪼갤 때 다음 팝업으로 넘길 종결어미 (긴 것부터 매칭)
_SPLIT_ENDINGS = ("입니다", "합니다", "됩니다", "습니다", "습니까", "하세요", "되세요",
                  "이에요", "인데요", "거든요", "잖아요", "네요", "데요", "까요",
                  "예요", "세요", "이죠", "죠")


def _split_long_word(text: str, max_chars: int) -> list:
    """max_chars 초과 어절 분할: 종결어미("~입니다")를 다음 팝업으로 분리, 아니면 균등 분할.
    예) "49,900원입니다" → ["49,900원", "입니다"] — 한 화면에 긴 자막이 뜨는 것 방지."""
    if len(text) <= max_chars:
        return [text]
    core, trail = text, ""
    while core and core[-1] in ".,!?…":
        core, trail = core[:-1], core[-1] + trail
    for ending in _SPLIT_ENDINGS:
        if core.endswith(ending) and len(core) - len(ending) >= 2:
            head = core[: -len(ending)]
            return _split_long_word(head, max_chars) + [core[-len(ending):] + trail]
    n_parts = -(-len(core) // max_chars)
    size = -(-len(core) // n_parts)
    parts = [core[i:i + size] for i in range(0, len(core), size)]
    parts[-1] += trail
    return parts


def _expand_long_words(words: list, max_chars: int) -> list:
    """분할된 조각들에 원래 어절의 발화 구간을 글자 수 비례로 배분."""
    if max_chars < 3:
        return words
    out = []
    for w in words:
        parts = _split_long_word(str(w["word"]), max_chars)
        if len(parts) == 1:
            out.append(w)
            continue
        start, end = float(w["start"]), float(w["end"])
        total = sum(len(p) for p in parts) or 1
        t = start
        for p in parts:
            dur = (end - start) * len(p) / total
            out.append({"word": p, "start": t, "end": t + dur})
            t += dur
    return out


def _pop_scale(t: float, d: float = 0.16, lo: float = 0.5) -> float:
    """등장 바운스 스케일: lo에서 시작해 살짝 오버슈트 후 1.0으로 안착(ease-out-back)."""
    if t >= d:
        return 1.0
    p = t / d
    c1 = 1.70158
    eased = 1 + (c1 + 1) * (p - 1) ** 3 + c1 * (p - 1) ** 2
    return lo + (1.0 - lo) * eased


def _regroup_karaoke(words: list, min_chars: int = 3, max_chars: int = 8) -> list:
    """(폴백 전용 — 라인 subs가 없을 때만) 가라오케 단위 재편성: 긴 어절은 쪼개고 짧은 조각은
    다음과 합친다. 합칠 때 어절 사이 공백을 반드시 보존한다(띄어쓰기 실종 버그 수정)."""
    toks = _expand_long_words(words, max_chars)
    out, i, n = [], 0, len(toks)
    while i < n:
        text = str(toks[i]["word"])
        start, end = float(toks[i]["start"]), float(toks[i]["end"])
        j = i + 1
        while len(text) < min_chars and j < n and len(text) + 1 + len(str(toks[j]["word"])) <= max_chars:
            text += " " + str(toks[j]["word"])
            end = float(toks[j]["end"])
            j += 1
        out.append({"word": text, "start": start, "end": end})
        i = j
    return out


def _karaoke_clips(toks: list, end_bound: float, font_path: Path, s: dict, width: int) -> list:
    """토큰 목록을 가라오케 단어 팝업 클립으로 — 중앙·노랑·굵은 검정테두리 + 등장 바운스."""
    font_size = int(s.get("font_size", 80))
    color = s.get("color", "#FFE400")
    stroke_color = s.get("stroke_color", "#000000")
    stroke_width = int(s.get("stroke_width", 6))
    y = int(s.get("y", 1250))
    clips, n = [], len(toks)
    for i, w in enumerate(toks):
        start = max(0.0, float(w["start"]))
        end = float(toks[i + 1]["start"]) if i + 1 < n else min(float(w["end"]) + 0.35, end_bound)
        end = min(end, end_bound)
        if end - start < 0.06:
            end = min(start + 0.06, end_bound)
        if end <= start:
            continue
        clip = _make_text(w["word"], font_path, font_size, color, stroke_color, stroke_width)
        if clip.w > width - 60:  # 아주 긴 조각 방어: 화면 폭에 맞게 축소
            shrunk = max(30, int(font_size * (width - 100) / clip.w))
            clip = _make_text(w["word"], font_path, shrunk, color, stroke_color, stroke_width)
        clip = clip.resized(lambda t: _pop_scale(t, 0.16, 0.5))  # 등장 바운스
        clips.append(clip.with_start(start).with_end(end).with_position(("center", y)))
    return clips


def _build_word_clips(words: list, duration: float, font_path: Path,
                      s: dict, width: int) -> list:
    """(폴백) 전체 단어를 가라오케 팝업으로 — 라인 정보가 없을 때."""
    toks = _regroup_karaoke(words, int(s.get("karaoke_min_chars", 3)),
                            int(s.get("karaoke_max_chars", 8)))
    return _karaoke_clips(toks, duration, font_path, s, width)


def _meme_rgba(path: Path, target_w: int):
    """라이브러리 밈 이미지를 목표 폭으로 리사이즈해 RGBA 배열로(캐시). 글자 없는 원본만 온다."""
    from PIL import Image
    key = ("meme", str(path), int(target_w))
    if key in _HERO_RGBA_CACHE:
        return _HERO_RGBA_CACHE[key]
    im = Image.open(path).convert("RGBA")
    if im.width != int(target_w):
        h = max(1, int(im.height * int(target_w) / im.width))
        im = im.resize((int(target_w), h), Image.LANCZOS)
    arr = np.asarray(im)
    _HERO_RGBA_CACHE[key] = arr
    return arr


def _meme_image_clip(img_path: Path, start: float, end: float, width: int, height: int, s: dict):
    """펀치 밈 카드의 '배경 이미지'(글자 없는 라이브러리 짤). 상단 2/3에 크게 팝인 —
    글자는 _meme_card가 하단 클린존(meme_y)에 얹으므로 한글이 안 깨진다.
    핵심규칙: 이건 '화면 텍스트'가 아니라 punch 밈 카드 1회의 배경일 뿐(카드 개수 불변)."""
    if end - start < 0.12:
        return None
    try:
        base = ImageClip(_meme_rgba(Path(img_path), int(width * 0.86)), transparent=True)
    except Exception as e:
        print(f"[render] 경고: 밈 이미지 로드 실패({Path(img_path).name}: {e}) — 텍스트 카드만 사용")
        return None
    return (base.resized(lambda t: _pop_scale(t, 0.18, 0.45))
            .with_start(start).with_end(min(end, start + 30))
            .with_position(("center", int(height * 0.05))))


def _meme_card(text: str, start: float, end: float, font_path: Path, s: dict, width: int,
               y_override: int | None = None):
    """펀치라인/의문형 훅을 '큰 밈 텍스트 카드'로 — 화면 중앙, 흰색 굵게 + 두꺼운 검정테두리,
    큰 바운스로 팡 등장(드립·정곡 순간 강조). framed면 y_override로 정사각형 중앙에 얹는다."""
    if end - start < 0.12 or not text:
        return None
    font_size = int(s.get("meme_font_size", 92))
    stroke_width = int(s.get("meme_stroke_width", 8))
    box_w = int(width * 0.88)
    pad = stroke_width * 3 + 16
    tc = None
    for extra in (dict(text_align="center"), {}):
        try:
            tc = TextClip(text=text, font=str(font_path), font_size=font_size,
                          color=s.get("meme_color", "#FFFFFF"), stroke_color="#000000",
                          stroke_width=stroke_width, method="caption",
                          size=(box_w, None), margin=(pad, pad), **extra)
            break
        except TypeError:
            continue
    if tc is None:
        return None
    tc = tc.resized(lambda t: _pop_scale(t, 0.2, 0.4))  # 큰 바운스로 팡
    y = int(y_override) if y_override is not None else int(s.get("meme_y", 760))
    return tc.with_start(start).with_end(min(end, start + 30)).with_position(("center", y))


def _meme_square_clip(img_path: Path, start: float, end: float, sq: int, sq_top: int):
    """framed 펀치: 밈 이미지(글자 없는 원본)를 정사각형에 꽉 채워 얹는다(글자는 _meme_card가 위에).
    밈은 대개 정사각형이라 cover-fit이 정확히 맞고 바 영역을 침범하지 않는다."""
    if end - start < 0.12:
        return None
    try:
        arr = _square_cover_arr(Path(img_path), int(sq))
    except Exception as e:
        print(f"[render] 경고: 밈 정사각형 로드 실패({Path(img_path).name}: {e}) — 텍스트 카드만")
        return None
    return (ImageClip(arr).with_start(start).with_end(min(end, start + 30))
            .with_position((0, int(sq_top))))


def _fit_text(text: str, font_path: Path, font_size: int, color: str,
              stroke_color: str, stroke_width: int, max_w: int) -> TextClip:
    """자막 텍스트 클립 — 화면 폭을 넘으면 폰트를 줄여서 맞춤(줄바꿈·말줄임 금지)."""
    clip = _make_text(text, font_path, font_size, color, stroke_color, stroke_width)
    if clip.w > max_w:
        shrunk = max(40, int(font_size * max_w / clip.w))
        clip = _make_text(text, font_path, shrunk, color, stroke_color, stroke_width)
    return clip


def _build_subtitles(words: list, lines: list, line_windows: list, duration: float,
                     font_path: Path, s: dict, width: int, height: int = 1920,
                     meme_img: Path | None = None, framed: bool = False,
                     sq: int = 0, sq_top: int = 0) -> tuple:
    """'대본이 곧 자막' (2026-07-12 개편): 라인의 subs(대본이 확정한 자막 칸)를 렌더가
    재분할 없이 그대로 팝업한다 — 띄어쓰기·문맥·길이 일관성을 대본이 책임진다.
    위치는 하단 1곳 고정. 중앙 밈 카드는 punch 라인 딱 1회(의문형 자동 트리거 폐지).
    ⭐ 2026-07-13 개편: 오프닝 훅(punch)도 **다른 라인과 똑같이 하단 가라오케(어절별 팝)**로 띄운다
    (전체 문장 정적 표시 폐지). 밈 이미지는 punch 구간 정사각형 '배경'으로만 남는다(글자 카드 없음).
    반환: (클립 목록, QA용 자막 플랜)."""
    y = int(s.get("y", 1250))
    max_w = int(width * 0.94)
    font_size = int(s.get("font_size", 80))
    color = s.get("color", "#FFE400")
    stroke_color = s.get("stroke_color", "#000000")
    stroke_width = int(s.get("stroke_width", 6))

    events, meme_windows, cursor = [], [], 0
    for li, ((ls, le), ln) in enumerate(zip(line_windows, lines)):
        text = str(ln.get("text", "")).strip()
        n = len(text.split())
        lwords = words[cursor:cursor + n]
        cursor += n
        ls, le = max(0.0, float(ls)), min(float(le), duration)
        if not text or le - ls < 0.1:
            continue
        if bool(ln.get("punch")):
            # 훅은 밈 이미지를 정사각형 배경으로만 깔고, 글자는 아래 가라오케로 처리(계속 진행)
            meme_windows.append({"start": ls, "end": le, "line_i": li})
        subs = [str(x).strip() for x in (ln.get("subs") or []) if str(x).strip()]
        if not subs or " ".join(subs) != text:
            subs = [text]  # sanitize가 계약을 보장하지만 최종 방어
        wi = 0
        for sub in subs:
            k = len(sub.split())
            grp = lwords[wi:wi + k]
            wi += k
            if grp:
                a, b = float(grp[0]["start"]), float(grp[-1]["end"])
            else:  # 타임스탬프 부족 방어: 라인 구간을 글자수 비례 배분
                done = sum(len(x) for x in subs[:subs.index(sub)]) or 0
                total = sum(len(x) for x in subs) or 1
                a = ls + (le - ls) * done / total
                b = min(le, a + (le - ls) * len(sub) / total)
            events.append({"text": sub, "start": a, "end": b, "line_i": li})

    # 표시 유지: 다음 팝업 시작까지(빈 화면 방지), 단 발화 종료 +0.45s를 넘지 않음
    for i, ev in enumerate(events):
        nxt = events[i + 1]["start"] if i + 1 < len(events) else duration
        ev["show_end"] = min(max(nxt, ev["start"] + 0.12), ev["end"] + 0.45, duration)

    clips, plan = [], []
    # punch 밈 이미지(정사각형 배경) — 글자 없이 이미지만. 자막은 아래 가라오케가 담당.
    for m in meme_windows:
        if meme_img is not None:
            mi = (_meme_square_clip(meme_img, m["start"], m["end"], sq, sq_top) if framed
                  else _meme_image_clip(meme_img, m["start"], m["end"], width, height, s))
            if mi is not None:
                clips.append(mi)
        plan.append({"kind": "meme_img", "start": round(m["start"], 3),
                     "end": round(m["end"], 3), "line_i": m["line_i"],
                     "image": str(meme_img) if meme_img is not None else None})
    for ev in events:
        clip = _fit_text(ev["text"], font_path, font_size, color, stroke_color, stroke_width, max_w)
        clip = clip.resized(lambda t: _pop_scale(t, 0.14, 0.6))
        clips.append(clip.with_start(ev["start"]).with_end(ev["show_end"])
                         .with_position(("center", y)))
        plan.append({"kind": "sub", "text": ev["text"], "start": round(ev["start"], 3),
                     "end": round(ev["show_end"], 3), "y": y, "line_i": ev["line_i"]})
    return clips, plan


def _make_text(text: str, font_path: Path, font_size: int, color: str,
               stroke_color: str, stroke_width: int) -> TextClip:
    # margin: stroke가 글자 상자 밖으로 잘리지 않게 여유 확보 (MoviePy 2.x)
    pad = stroke_width * 3 + 12
    return TextClip(
        text=text,
        font=str(font_path),
        font_size=font_size,
        color=color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        margin=(pad, pad),
    )


def _wrap_pil(text: str, font, max_w: int, max_lines: int = 2) -> list:
    """어절(공백) 단위 줄바꿈 — 단어 중간에서 끊지 않는다(사용자 규칙). 한 어절이 한 줄보다 길 때만
    그 어절을 글자 단위로 쪼갠다(불가피). max_lines 초과분은 마지막 줄 끝에 말줄임(…)."""
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    def wpx(s):
        return d.textbbox((0, 0), s, font=font)[2]
    lines, cur = [], ""
    for word in str(text).split():
        trial = f"{cur} {word}".strip() if cur else word
        if wpx(trial) <= max_w:
            cur = trial
            continue
        if cur:                       # 현재 줄을 마무리하고 새 줄에서 이 어절을 시작
            lines.append(cur)
            cur = ""
        if wpx(word) > max_w:         # 어절 하나가 한 줄보다 긴 경우에만 글자 단위로 쪼갬
            for ch in word:
                if wpx(cur + ch) <= max_w:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
        else:
            cur = word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:        # 넘치면 마지막 줄에 말줄임
        lines = lines[:max_lines]
        while lines[-1] and d.textbbox((0, 0), lines[-1] + "…", font=font)[2] > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return lines


def build_poster(out_path: Path, product: dict, settings: dict,
                 project_root: Path | None = None, product_images: list | None = None) -> Path:
    """모든 영상에 통일된 느낌의 대표 썸네일(1080x1920) — 흐린 상품 배경 + 히어로 카드 +
    하단 상품명·가격. 영상 목록에서 poster로 사용. 상품 사진이 없으면 그라데이션 폴백."""
    from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
    project_root = project_root or Path.cwd()
    W, H = 1080, 1920
    imgs = [Path(p) for p in (product_images or []) if Path(p).exists()]

    if imgs:
        bg = Image.open(str(imgs[0])).convert("RGB")
        scale = max(W / bg.width, H / bg.height)
        bg = bg.resize((max(1, round(bg.width * scale)), max(1, round(bg.height * scale))))
        left, top = (bg.width - W) // 2, (bg.height - H) // 2
        bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(42))
        canvas = ImageEnhance.Brightness(bg).enhance(0.42).convert("RGBA")
    else:
        top_c, bot_c = np.array([12, 14, 34]), np.array([52, 22, 66])
        rows = np.linspace(0, 1, H)[:, None]
        grad = (top_c[None, :] * (1 - rows) + bot_c[None, :] * rows).astype(np.uint8)
        canvas = Image.fromarray(np.repeat(grad[:, None, :], W, axis=1)).convert("RGBA")

    if imgs:
        try:
            hero = Image.fromarray(_hero_rgba(imgs[0], int(W * 0.72)))
            canvas.alpha_composite(hero, ((W - hero.width) // 2, int(H * 0.13)))
        except Exception as e:
            print(f"[poster] 경고: 히어로 합성 실패({e})")

    band_top = int(H * 0.60)  # 하단 어둠(텍스트 가독성)
    band_h = H - band_top
    ramp = np.clip(np.linspace(0, 1, band_h) / 0.5, 0, 1)
    scrim = np.zeros((band_h, W, 4), dtype=np.uint8)
    scrim[..., 3] = (ramp * 210).astype(np.uint8)[:, None]
    canvas.alpha_composite(Image.fromarray(scrim), (0, band_top))

    canvas = canvas.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font_path = _resolve_font(project_root, settings.get("subtitle", {}).get(
        "font", "assets/fonts/GmarketSansBold.ttf"))
    name = (product.get("name") or "상품").strip()
    price = f"{int(product.get('price') or 0):,}원"
    name_font = ImageFont.truetype(str(font_path), 64)
    price_font = ImageFont.truetype(str(font_path), 98)

    y = int(H * 0.70)
    for ln in _wrap_pil(name, name_font, int(W * 0.86), max_lines=2):
        w = draw.textbbox((0, 0), ln, font=name_font)[2]
        draw.text(((W - w) // 2, y), ln, font=name_font, fill="#FFFFFF",
                  stroke_width=3, stroke_fill="#000000")
        y += 84
    y += 20
    pw = draw.textbbox((0, 0), price, font=price_font)[2]
    draw.text(((W - pw) // 2, y), price, font=price_font, fill="#FFE400",
              stroke_width=6, stroke_fill="#000000")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(out_path), "JPEG", quality=88)
    return out_path
