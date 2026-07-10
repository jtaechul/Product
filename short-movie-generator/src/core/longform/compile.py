"""롱폼 전체 컴파일 — 콜드오픈 + 타이틀 + 글로벌 지도 + 세그먼트×N(5→1) + 아웃트로.

compile_longform(theme, segments, out_dir, cfg) → {video, chapters, chapter_items, total_s}
- 각 세그먼트는 segment.render_segment로 렌더(모션+SFX+실사+HUD+나레이션+스탬프).
- 전체에 연속 BGM 베드를 얹고, YouTube 설명용 챕터 타임스탬프 문자열(일본어, chapters)과
  구조화 항목(chapter_items: t·label_jp·rank·ko_name — 대시보드 한국어 설명 재구성용)을 생성.
- 표시 순서: 랭킹 내림차순(第N位 → 第1位). 콜드오픈은 1위(최대 충격) 소재 사용.
"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from src.core import hook_intro as hi, narration_sync
from src.core.longform import motion as M, segment as SEG, sfx as SFX


class _HkCfg:
    """_grad_sprite_diag용 최소 설정(16:9 콜드오픈 · 쇼츠 브랜드 그라데이션/글로우)."""
    W, H = 1280, 720
    grad_cyan = (120, 225, 245)
    grad_magenta = (240, 95, 205)
    glow = (80, 175, 240)

W, H = 1280, 720
CYAN = (120, 225, 245); MAG = (240, 95, 205); INK = (232, 240, 250); DIM = (150, 190, 210)
_serif, _sansb, _sansr, _sci, _mono = hi._serif, hi._sans_b, hi._sans_r, hi._sci, hi._mono
_BGM_DIR = Path(__file__).resolve().parents[3] / "assets" / "audio" / "bgm"


def _bgm_rotation(seed: str) -> list[str]:
    """롱폼 BGM 4곡(longform_*.mp3)을 시드로 회전 정렬해 반환. 8분을 여러 곡으로 채워 단조로움 방지."""
    cands = sorted(str(p) for p in _BGM_DIR.glob("longform_*.mp3"))
    if not cands:
        return []
    import hashlib
    h = int(hashlib.md5((seed or "deep").encode("utf-8")).hexdigest(), 16)
    k = h % len(cands)
    return cands[k:] + cands[:k]   # 회전 → 영상마다 시작 곡이 달라짐


@dataclass
class CompileConfig:
    fps: int = 24
    cold_open_s: float = 6.0            # 정지 화면 과다 → 페이스 타이트닝(9→6)
    title_s: float = 3.5               # (5→3.5)
    globalmap_s: float = 4.6           # 애니메이션 클립(도트 스윕 + 락온 브래킷)
    outro_s: float = 11.0              # (18→11)
    seg_cfg: SEG.SegmentConfig = field(default_factory=SEG.SegmentConfig)


def _run(cmd):
    subprocess.run(cmd, check=True)


def _grad(txt, font):
    im = Image.new("RGBA", (1200, 300), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), txt, font=font, fill=(255, 255, 255, 255), anchor="la")
    bb = im.getbbox(); cr = im.crop(bb); w, h = cr.size
    g = Image.new("RGB", (w, h)); px = g.load()
    for y in range(h):
        for x in range(w):
            tt = min(1, max(0, (x + y) / max(1, w + h - 2)))
            px[x, y] = tuple(int(CYAN[i] + (MAG[i] - CYAN[i]) * tt) for i in range(3))
    return Image.merge("RGBA", (*g.split(), cr.split()[3]))


def _void():
    im = Image.new("RGB", (W, H), (6, 14, 22)); d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H; d.line((0, y, W, y), fill=(int(6 + 6 * t), int(14 + 10 * t), int(22 + 16 * t)))
    return im.convert("RGBA")


def _still_clip(img_path, dur, out, cfg, fade=True):
    vf = f"scale={W}:{H},setsar=1" + (",fade=t=in:st=0:d=0.4" if fade else "")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", f"{dur}", "-i", img_path,
          "-vf", vf, "-r", str(cfg.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", out])


def _title_card(theme_word, n, out_png):
    im = _void(); d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 4), fill=CYAN + (120,))
    t1 = _grad(f"深海の【{theme_word}】", _serif(84)); im.alpha_composite(t1, (W // 2 - t1.width // 2, 220))
    t2 = _grad(f"生き物 TOP {n}", _serif(96)); im.alpha_composite(t2, (W // 2 - t2.width // 2, 340))
    d.text((W // 2, 500), f"第{n}位から", font=_sansb(40), fill=INK + (240,), anchor="mm")
    d.text((W // 2, H - 60), "ABYSS ・ 深淵アーカイブ", font=_sansr(22), fill=DIM + (200,), anchor="mm")
    im.convert("RGB").save(out_png); return out_png


_GMAP_BOX = (150, 150, 1130, 630)


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _bracket(d, cx, cy, rx, ry, col, alpha, bw=3, arm=26):
    a = int(alpha)
    for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
        ex, ey = cx + dx * rx, cy + dy * ry
        d.line((ex, ey, ex - dx * arm, ey), fill=col + (a,), width=bw)
        d.line((ex, ey, ex, ey - dy * arm), fill=col + (a,), width=bw)


def _gmap_dots():
    """지도 도트 좌표 1회 계산(전역 지도, 줌 없음)."""
    mask, P = M._land_mask(M.MotionConfig(W=W, H=H, map_box=_GMAP_BOX), 1.0, 0.5, 0.45)
    px = mask.load()
    pts = [(x, y) for y in range(0, H, 12) for x in range(0, W, 12) if px[x, y] > 128]
    return pts, P


def _gmap_frame(t01, segments, pts, P, reveals):
    """t01∈[0,1] 애니 프레임. 도트 좌우 스윕 등장 → 해역 브래킷 순차 락온."""
    im = _void(); d = ImageDraw.Draw(im)
    d.rectangle(_GMAP_BOX, fill=(4, 12, 20, 150))
    M._corner_box(d, _GMAP_BOX)
    d.rectangle((0, 0, W, 4), fill=CYAN + (120,))
    d.text((40, 26), "ABYSS ・ DIVE LOG", font=_sansr(18), fill=CYAN + (220,))
    d.text((W - 40, 26), "GLOBAL MAP", font=_mono(16), fill=MAG + (220,), anchor="ra")
    bx0, _by0, bx1, _by1 = _GMAP_BOX
    # 도트: 좌→우 와이프 등장(첫 40%)
    wipe = _smooth(t01 / 0.4) if t01 < 0.4 else 1.0
    wx = bx0 + (bx1 - bx0) * wipe
    for (x, y) in pts:
        if x <= wx:
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=CYAN + (160,))
    if t01 < 0.42:  # 스캔 라인
        d.line((wx, _GMAP_BOX[1], wx, _GMAP_BOX[3]), fill=CYAN + (230,), width=2)
    # 해역 브래킷 순차 락온
    for s, rt in zip(segments, reveals):
        if t01 < rt:
            continue
        a = _smooth((t01 - rt) / 0.14)
        cx, cy = P(s.region_nx, s.region_ny)
        _bracket(d, cx, cy, 34, 26, MAG, 235 * a)
        d.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=MAG + (int(235 * a),))
    tt = _smooth(t01 / 0.25)
    d.text((W // 2, 108), f"本日のダイブ ・ {len(segments)}地点", font=_sansb(34),
           fill=INK + (int(245 * tt),), anchor="mm")
    return im.convert("RGB")


def _globalmap_clip(segments, out_mp4, cfg):
    """애니메이션 글로벌맵 클립(오디오 포함: 스캔 스윕 + 해역별 락온 핑)."""
    wd = Path(out_mp4).parent
    fdir = wd / "gmframes"; fdir.mkdir(parents=True, exist_ok=True)
    dur = cfg.globalmap_s
    n = int(dur * cfg.fps)
    pts, P = _gmap_dots()
    # 해역 락온 시각(정규화 t01) — 스윕(0.4) 이후 순차
    m = len(segments)
    reveals = [0.46 + i * (0.42 / max(1, m)) for i in range(m)]
    for i in range(n):
        t01 = i / max(1, n - 1)
        _gmap_frame(t01, segments, pts, P, reveals).save(str(fdir / f"g_{i:04d}.png"))
    silent = str(wd / "gmap_silent.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.fps),
          "-i", str(fdir / "g_%04d.png"), "-vf", f"scale={W}:{H},setsar=1", "-r", str(cfg.fps),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", silent])
    # 오디오: 스캔 스윕(0.15s) + 해역별 락온 핑
    s = SFX.gen_all(str(wd))
    ms = lambda x: int(x * 1000)  # noqa: E731
    scan_at = 0.12
    lock_ts = [r * dur for r in reveals]
    inputs = ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
              "-i", s["scan"]]
    af = [f"[0:a]volume=0[bed]", f"[1:a]adelay={ms(scan_at)}|{ms(scan_at)},volume=1.2[sc]"]
    mixnames = ["[bed]", "[sc]"]
    for k, lt in enumerate(lock_ts):
        inputs += ["-i", s["lockon"]]
        af.append(f"[{k + 2}:a]adelay={ms(lt)}|{ms(lt)},volume=1.3[lk{k}]")
        mixnames.append(f"[lk{k}]")
    af.append("".join(mixnames) + f"amix=inputs={len(mixnames)}:duration=first:normalize=0,"
              f"alimiter=limit=0.92[a]")
    gma = str(wd / "gmap_a.m4a")
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(af),
          "-map", "[a]", "-c:a", "aac", "-b:a", "192k", gma])
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", gma,
          "-c:v", "copy", "-c:a", "aac", "-shortest", out_mp4])
    return out_mp4


def _outro_card(segments_desc, out_png):
    im = _void(); d = ImageDraw.Draw(im)
    t = _grad("あなたの1位は?", _serif(76)); im.alpha_composite(t, (W // 2 - t.width // 2, 90))
    y = 240
    for s in segments_desc:  # 5→1 순
        d.text((W // 2, y), f"第{s.rank}位  {s.jp_name}", font=_sansb(34), fill=INK + (235,), anchor="mm")
        y += 56
    d.text((W // 2, H - 130), "チャンネル登録で、次の深海へ。", font=_sansb(30), fill=CYAN + (235,), anchor="mm")
    d.text((W // 2, H - 70), "各生き物のショートはプロフィールから", font=_sansr(24), fill=DIM + (220,), anchor="mm")
    im.convert("RGB").save(out_png); return out_png


def _hook_sprites(text):
    """훅 텍스트(줄바꿈 가능)를 줄별 그라데이션+글로우 스프라이트로. 반환 [(sprite, cx, cy)]."""
    hc = _HkCfg()
    lines = [ln for ln in str(text).replace("／", "\n").split("\n") if ln.strip()] or [str(text)]
    # 화면폭에 맞춰 폰트 자동 축소
    base = 84 if len(lines) > 1 else 92
    font = hi._fit_font(max(lines, key=len), base, W * 0.86, _serif, min_size=44)
    lh = int(font.size * 1.28)
    top = int(H * 0.24) - (len(lines) - 1) * lh // 2
    out = []
    for i, ln in enumerate(lines):
        cy = top + i * lh
        spr, c = hi._grad_sprite_diag(ln.strip(), font, (W // 2, cy), hc, 0.0, float(W + H), 24)
        out.append((spr, W // 2, cy))
    return out


def _cold_open(top_spec, opening, out, cfg) -> float:
    """1위 소재(로고 제거+그레이딩) 위에 도발 훅이 쾅 떨어지는 애니 + 도발 나레이션.

    ★길이는 나레이션이 끝난 뒤 0.9초 여유를 두고 정해진다(말이 끊긴 채 넘어가지 않게).
    반환: 실제 콜드오픈 길이(초).
    """
    wd = Path(out).parent
    text = (opening or {}).get("text") or top_spec.stamp_line
    nar_lines = (opening or {}).get("narration") or [text]
    boom_at = 0.32
    nar_start = boom_at + 0.28

    # 1) 나레이션 먼저 합성 → 길이 측정 → 클립 길이 = 발화 종료 + 0.9초 홀드
    boom = hi.generate_boom(str(wd / "cold_boom.wav"), hi.HookIntroConfig())
    nar_mp3, nar_dur = None, 0.0
    try:
        nar = narration_sync.synthesize(nar_lines, str(wd / "conar"), rate="+6%")
        nar_mp3, nar_dur = nar.get("mp3"), float(nar.get("duration") or 0.0)
    except Exception:  # noqa: BLE001
        pass
    clip = max(cfg.cold_open_s, nar_start + nar_dur + 0.9) if nar_dur else cfg.cold_open_s

    # 2) 훅 오버레이 프레임(투명 PNG 시퀀스): 쾅 드롭 스케일팝 + 페이드 + 미세 셰이크
    sprites = _hook_sprites(text)
    fdir = wd / "coframes"; fdir.mkdir(parents=True, exist_ok=True)
    n = int(clip * cfg.fps)
    for i in range(n):
        t = i / cfg.fps
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dt = t - boom_at
        if dt >= 0:
            appear = _smooth(min(1.0, dt / 0.16))
            scale = 1.28 - 0.28 * _smooth(min(1.0, dt / 0.2))
            dy = int(-26 * (1 - appear))
            shx = int(round((6 * (1 - min(1.0, dt / 0.18))) * (1 if i % 2 else -1)))
            for spr, cx, cy in sprites:
                w1, h1 = max(1, int(spr.width * scale)), max(1, int(spr.height * scale))
                s2 = spr.resize((w1, h1), Image.LANCZOS)
                if appear < 1:
                    a = s2.split()[3].point(lambda v: int(v * appear))
                    s2.putalpha(a)
                fr.alpha_composite(s2, (cx - w1 // 2 + shx, cy - h1 // 2 + dy))
        fr.save(str(fdir / f"c_{i:04d}.png"))

    # 3) 실사(로고 제거 + 그레이딩) 위에 훅 프레임 오버레이
    #    ★워터마크 QC(하드룰 #9): 세그먼트 렌더가 1초 OCR 스캔으로 확정한 박스(wm_boxes)와
    #    깨끗한 시작점(footage_start)을 그대로 재사용해 콜드오픈에서도 문구 노출을 차단.
    silent = str(wd / "cold_silent.mp4")
    from src.core import watermark_qc as WQ
    boxes = list(getattr(top_spec, "wm_boxes", []) or [])
    if not boxes and top_spec.logo_box:
        lx, ly, lw, lh = top_spec.logo_box
        boxes = [(lx, ly, max(lw, 0.44), max(lh, 0.17))]   # 자동 스캔 전 레거시 폴백
    chain = WQ.delogo_chain(boxes, W, H)
    vf_pre = f"scale={W}:{H},setsar=1" + (("," + chain) if chain else "")
    _run(["ffmpeg", "-y", "-loglevel", "error",
          "-stream_loop", "-1", "-ss", f"{top_spec.footage_start}", "-i", top_spec.footage_path,
          "-framerate", str(cfg.fps), "-i", str(fdir / "c_%04d.png"),
          "-filter_complex",
          f"[0:v]{vf_pre},{cfg.seg_cfg.grade}[g];[g][1:v]overlay=0:0:shortest=1,fade=t=in:st=0:d=0.25[v]",
          "-map", "[v]", "-r", str(cfg.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19",
          "-an", "-t", f"{clip:.3f}", silent])

    # 4) 오디오: 무음 베드(clip 길이) + 쾅(훅 드롭) + 나레이션
    ms = lambda x: int(x * 1000)  # noqa: E731
    inputs = ["-f", "lavfi", "-t", f"{clip:.3f}", "-i", "anullsrc=r=44100:cl=stereo", "-i", boom]
    af = [f"[0:a]volume=0[bd]", f"[1:a]adelay={ms(boom_at)}|{ms(boom_at)},volume=1.0[bm]"]
    mix = ["[bd]", "[bm]"]
    if nar_mp3:
        inputs += ["-i", nar_mp3]
        af.append(f"[2:a]adelay={ms(nar_start)}|{ms(nar_start)},volume=1.6[nar]")
        mix.append("[nar]")
    af.append("".join(mix) + f"amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.93[a]")
    coa = str(wd / "cold_a.m4a")
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(af),
          "-map", "[a]", "-c:a", "aac", "-b:a", "192k", coa])
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", coa,
          "-c:v", "copy", "-c:a", "aac", "-shortest", out])
    return round(clip, 3)


def _ts(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def compile_longform(theme_word: str, segments: list[SEG.SegmentSpec], out_dir: str,
                     cfg: CompileConfig | None = None, opening: dict | None = None) -> dict:
    cfg = cfg or CompileConfig()
    wd = Path(out_dir); wd.mkdir(parents=True, exist_ok=True)
    segs = sorted(segments, key=lambda s: -s.rank)     # 5→1 표시 순
    top = min(segments, key=lambda s: s.rank)          # 1위(최대 충격)
    n = len(segments)

    parts = []          # (label, video_path, dur)
    seg_by_idx = {}     # part 인덱스 → SegmentSpec(챕터 한국어 라벨 구성용)
    # 콜드오픈
    co = str(wd / "cold.mp4"); co_dur = _cold_open(top, opening, co, cfg)
    parts.append(("オープニング", co, co_dur))
    # 타이틀
    tc = str(wd / "title.mp4"); _still_clip(_title_card(theme_word, n, str(wd / "title.png")), cfg.title_s, tc, cfg)
    parts.append((None, tc, cfg.title_s))
    # 글로벌 지도(애니메이션 + 락온 SFX)
    gm = str(wd / "gmap.mp4"); _globalmap_clip(segs, gm, cfg)
    parts.append((None, gm, cfg.globalmap_s))
    # 세그먼트 ×N (5→1)
    for i, s in enumerate(segs):
        r = SEG.render_segment(s, str(wd / f"seg{i}"), cfg.seg_cfg)
        seg_by_idx[len(parts)] = s
        parts.append((f"第{s.rank}位 {s.jp_name}", r["video"], r["total_s"]))
    # 아웃트로
    oc = str(wd / "outro.mp4"); _still_clip(_outro_card(segs, str(wd / "outro.png")), cfg.outro_s, oc, cfg)
    parts.append(("エンディング", oc, cfg.outro_s))

    # 오디오/영상 규격 표준화(모든 파트를 동일 v+a 파라미터로 재인코딩) → concat copy 안전.
    # (파트마다 aac 파라미터가 달라 concat 데먹서가 깨지던 문제 방지)
    vf = f"scale={W}:{H},setsar=1,fps={cfg.fps},format=yuv420p"
    norm = []
    for idx, (_lab, vpath, dur) in enumerate(parts):
        npath = str(wd / f"n{idx}.mp4")
        if _has_no_audio(vpath):   # 카드류: 무음 오디오 부여
            _run(["ffmpeg", "-y", "-loglevel", "error", "-i", vpath,
                  "-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
                  "-map", "0:v:0", "-map", "1:a:0", "-vf", vf,
                  "-c:v", "libx264", "-crf", "19", "-c:a", "aac", "-ar", "44100", "-ac", "2",
                  "-shortest", npath])
        else:                       # 세그먼트: 오디오 유지하되 규격 통일 재인코딩
            _run(["ffmpeg", "-y", "-loglevel", "error", "-i", vpath, "-vf", vf,
                  "-c:v", "libx264", "-crf", "19", "-c:a", "aac", "-ar", "44100", "-ac", "2", npath])
        norm.append(npath)

    # ★concat 목록은 절대경로로(ffmpeg가 상대경로를 concat.txt 위치 기준으로 재해석 → 경로 중복 버그)
    concat = wd / "concat.txt"
    concat.write_text("\n".join(f"file '{Path(p).resolve()}'" for p in norm), encoding="utf-8")
    body = str(wd / "body_all.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
          "-c", "copy", body])
    total_s = sum(d for _l, _v, d in parts)

    # 연속 BGM 베드(전체) — 4곡을 회전 순서로 이어붙여 8분을 다채롭게 채운 뒤 세그먼트 오디오와 amix.
    final = str(wd / "longform.mp4")
    bgms = _bgm_rotation(theme_word)
    if bgms:
        inputs = ["-i", body]
        for p in bgms:
            inputs += ["-i", p]
        # 각 곡 규격 통일 → 순차 concat → 볼륨/페이드 → 본문과 mix
        seq = "".join(f"[{i + 1}:a]aformat=sample_rates=44100:channel_layouts=stereo[b{i}];"
                      for i in range(len(bgms)))
        seq += "".join(f"[b{i}]" for i in range(len(bgms))) + f"concat=n={len(bgms)}:v=0:a=1[seq];"
        fc = (seq +
              f"[seq]volume=0.20,afade=t=in:st=0:d=2,afade=t=out:st={total_s - 3:.2f}:d=3[bed];"
              f"[0:a][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.93[a]")
        _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
              "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", final])
    else:
        final = body

    # 챕터(YouTube 설명용) + 구조화 타임스탬프(대시보드 한국어 설명 등 재구성용)
    chapters = []
    chapter_items = []
    acc = 0.0
    for idx, (lab, _v, dur) in enumerate(parts):
        if lab:
            chapters.append(f"{_ts(acc)} {lab}")
            s = seg_by_idx.get(idx)
            chapter_items.append({
                "t": round(acc, 2), "label_jp": lab,
                "rank": s.rank if s else None, "ko_name": (s.ko_name if s else "") or "",
            })
        acc += dur
    return {"video": final, "total_s": round(total_s, 2), "chapters": "\n".join(chapters),
            "chapter_items": chapter_items, "n": n}


def _has_no_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return not r.stdout.strip()
