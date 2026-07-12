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

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}

# 씬마다 같은 사진의 흐린 배경·히어로 카드를 재계산하지 않도록 캐시(렌더 속도).
_BLUR_BG_CACHE: dict = {}
_HERO_RGBA_CACHE: dict = {}


def render_video(audio_path: Path, words: list, out_path: Path, settings: dict,
                 shake_windows: list | None = None, project_root: Path | None = None,
                 image_windows: list | None = None, bg_path: Path | None = None,
                 product_images: list | None = None, lines: list | None = None,
                 line_windows: list | None = None, stock_clips: list | None = None) -> dict:
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
    lines = list(lines or [])
    line_windows = list(line_windows or [])

    font_path = _resolve_font(project_root, s.get("font", "assets/fonts/GmarketSansBold.ttf"))

    audio = AudioFileClip(str(audio_path))
    duration = float(audio.duration) + 0.25

    over_w, over_h = width + 2 * shake_px, height + 2 * shake_px
    bg_dir = project_root / settings.get("assets", {}).get("backgrounds_dir", "assets/backgrounds")

    # 씬 시퀀스: 대본 단계(stage)별로 배경/상품카드를 갈아끼워 '사진 한 장 고정'을 없앤다.
    use_scenes = bool(line_windows) and bool(lines) and bool(product_images or stock_clips)
    bg_layers, card_layers = [], []
    if use_scenes:
        scenes = _plan_scenes(duration, lines, line_windows, len(product_images), len(stock_clips))
        for sc in scenes:
            bgc = _scene_bg_clip(sc, product_images, stock_clips, over_w, over_h)
            bgc = (bgc.with_start(sc["start"]).with_duration(sc["end"] - sc["start"] + 0.04)
                      .with_position(_seg_shake_pos(sc["start"], shake_windows, shake_px, fps)))
            bg_layers.append(bgc)
            if sc["kind"] == "product" and product_images:
                card = _product_card_clip(sc, product_images, width, height)
                if card is not None:
                    card_layers.append(card)
        bg_name = f"씬 {len(scenes)}컷 (상품 {len(product_images)}·스톡 {len(stock_clips)})"
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
    # 자막: 기본은 가라오케 단어 팝업(썰피자식, subtitle.mode=karaoke).
    # subtitle.mode=phrase 로 두면 구(라인) 단위로도 낼 수 있다.
    if s.get("mode", "karaoke") == "phrase" and lines and line_windows:
        sub_clips = _build_line_clips(lines, line_windows, duration, font_path, s, width)
    else:
        sub_clips = _build_word_clips(words, duration, font_path, s, width)

    t0 = time.time()
    layers = [*bg_layers, *card_layers]
    if scrim is not None:
        layers.append(scrim)
    layers += sub_clips
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
        "image_clip_count": len(card_layers),
        "scene_count": len(bg_layers),
        "hero_from_product": bool(product_images),
        "font_used": str(font_path),
        "background_used": bg_name,
        "output_bytes": out_path.stat().st_size,
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


def _blurred_product_bg(img_path: Path, over_w: int, over_h: int, duration: float) -> tuple:
    """상품 사진을 화면에 꽉 차게 흐리게+어둡게 깔아 배경으로 (항상 상품 관련).
    같은 사진·캔버스는 캐시해 씬마다 GaussianBlur 재계산을 피한다(렌더 속도 개선)."""
    key = (str(img_path), int(over_w), int(over_h))
    arr = _BLUR_BG_CACHE.get(key)
    if arr is None:
        from PIL import Image, ImageEnhance, ImageFilter
        im = Image.open(str(img_path)).convert("RGB")
        scale = max(over_w / im.width, over_h / im.height)
        im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))))
        left, top = (im.width - over_w) // 2, (im.height - over_h) // 2
        im = im.crop((left, top, left + over_w, top + over_h))
        im = im.filter(ImageFilter.GaussianBlur(32))
        im = ImageEnhance.Brightness(im).enhance(0.5)
        arr = np.array(im)
        _BLUR_BG_CACHE[key] = arr
    return ImageClip(arr).with_duration(duration), "(흐린 상품사진 배경)"


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
    """대본 라인 → 시각 씬 목록. 문제 단계(②③)는 스톡, 나머지는 상품 사진.
    연속 같은 종류는 병합하고, 긴 상품 씬은 여러 컷으로 쪼개 켄번즈를 변주한다(사진 한 장도 여러 컷처럼)."""
    problem = {2, 3}
    pairs = [((float(st), float(en)), ln) for (st, en), ln in zip(line_windows, lines)]
    if not pairs:
        return []
    segs = []
    for (st, en), ln in pairs:
        kind = "stock" if (int(ln.get("stage", 1) or 1) in problem and n_stock > 0) else "product"
        segs.append([st, en, kind])
    merged = [segs[0]]
    for st, en, k in segs[1:]:
        if k == merged[-1][2] and st <= merged[-1][1] + 0.6:
            merged[-1][1] = en
        else:
            merged.append([st, en, k])
    merged[0][0] = 0.0
    merged[-1][1] = duration
    for i in range(1, len(merged)):
        merged[i][0] = merged[i - 1][1]

    max_shot = 3.2
    scenes, prod_i, stock_i, shot = [], 0, 0, 0
    for st, en, k in merged:
        if en - st <= 0.05:
            continue
        if k == "stock":
            scenes.append({"start": st, "end": en, "kind": "stock", "asset": stock_i % max(n_stock, 1)})
            stock_i += 1
            continue
        dur = en - st
        n = max(1, int(-(-dur // max_shot)))
        step = dur / n
        for j in range(n):
            a = st + j * step
            b = en if j == n - 1 else a + step
            scenes.append({"start": a, "end": b, "kind": "product",
                           "asset": prod_i % max(n_product, 1), "shot": shot})
            prod_i += 1
            shot += 1
    return scenes


def _scene_bg_clip(scene: dict, product_images: list, stock_clips: list, over_w: int, over_h: int):
    """씬 배경: 문제 씬은 어둡게 깐 스톡 영상, 상품 씬은 흐린 상품 사진, 최후엔 그라데이션."""
    dur = scene["end"] - scene["start"]
    if scene["kind"] == "stock" and stock_clips:
        path = stock_clips[scene["asset"] % len(stock_clips)]
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
            return clip.with_effects([vfx.MultiplyColor(0.55)])  # 자막 가독성 위해 어둡게
        except Exception as e:
            print(f"[render] 경고: 스톡 클립 실패({Path(path).name}: {e}) — 대체 배경")
    if product_images:
        img = product_images[scene.get("asset", 0) % len(product_images)]
        clip, _ = _blurred_product_bg(Path(img), over_w, over_h, dur)
        return clip
    top, bottom = np.array([12, 14, 34]), np.array([44, 20, 60])
    rows = np.linspace(0, 1, over_h)[:, None]
    grad = (top[None, :] * (1 - rows) + bottom[None, :] * rows).astype(np.uint8)
    frame = np.repeat(grad[:, None, :], over_w, axis=1)
    if scene["kind"] == "stock":
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
    """가라오케 단위 재편성: 긴 어절은 쪼개고(≤max_chars) 짧은 조각(한두 글자)은 다음과 합쳐
    각 팝업이 3~8글자가 되게 한다 — 한 글자씩 튀거나 문장이 통째로 나오는 것을 둘 다 방지."""
    toks = _expand_long_words(words, max_chars)
    out, i, n = [], 0, len(toks)
    while i < n:
        text = str(toks[i]["word"])
        start, end = float(toks[i]["start"]), float(toks[i]["end"])
        j = i + 1
        while len(text) < min_chars and j < n and len(text) + len(str(toks[j]["word"])) <= max_chars:
            text += str(toks[j]["word"])
            end = float(toks[j]["end"])
            j += 1
        out.append({"word": text, "start": start, "end": end})
        i = j
    return out


def _build_word_clips(words: list, duration: float, font_path: Path,
                      s: dict, width: int) -> list:
    """가라오케식 단어 팝업 자막(3~8글자 단위, 문장 통째 X) — 중앙·노랑·굵은 검정테두리 +
    등장 시 통통 튀는 바운스(썰피자식). 각 팝업은 발화 시점에 등장해 다음 팝업 전까지 유지."""
    toks = _regroup_karaoke(words, int(s.get("karaoke_min_chars", 3)),
                            int(s.get("karaoke_max_chars", 8)))
    font_size = int(s.get("font_size", 80))
    color = s.get("color", "#FFE400")
    stroke_color = s.get("stroke_color", "#000000")
    stroke_width = int(s.get("stroke_width", 6))
    y = int(s.get("y", 1250))

    clips, n = [], len(toks)
    for i, w in enumerate(toks):
        start = max(0.0, float(w["start"]))
        end = float(toks[i + 1]["start"]) if i + 1 < n else min(float(w["end"]) + 0.35, duration)
        end = min(end, duration)
        if end - start < 0.06:
            end = min(start + 0.06, duration)
        if end <= start:
            continue

        clip = _make_text(w["word"], font_path, font_size, color, stroke_color, stroke_width)
        if clip.w > width - 60:  # 아주 긴 조각 방어: 화면 폭에 맞게 축소
            shrunk = max(30, int(font_size * (width - 100) / clip.w))
            clip = _make_text(w["word"], font_path, shrunk, color, stroke_color, stroke_width)
        clip = clip.resized(lambda t: _pop_scale(t, 0.16, 0.5))  # 등장 바운스
        clips.append(clip.with_start(start).with_end(end).with_position(("center", y)))
    return clips


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
    """PIL 폰트 폭 기준 글자 단위 줄바꿈 (한글은 공백이 없어 글자 기준). 넘치면 말줄임."""
    from PIL import Image, ImageDraw
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    lines, cur = [], ""
    for ch in text:
        if d.textbbox((0, 0), cur + ch, font=font)[2] <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                break
    if len(lines) < max_lines and cur:
        lines.append(cur)
    if len(lines) == max_lines:  # 남은 글자가 있으면 마지막 줄 끝에 말줄임
        used = sum(len(x) for x in lines)
        if used < len(text) and lines:
            while lines[-1] and d.textbbox((0, 0), lines[-1] + "…", font=font)[2] > max_w:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
    return lines[:max_lines]


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
