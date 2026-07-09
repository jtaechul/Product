"""롱폼 전체 컴파일 — 콜드오픈 + 타이틀 + 글로벌 지도 + 세그먼트×N(5→1) + 아웃트로.

compile_longform(theme, segments, out_dir, cfg) → {video, chapters, total_s}
- 각 세그먼트는 segment.render_segment로 렌더(모션+SFX+실사+HUD+나레이션+스탬프).
- 전체에 연속 BGM 베드를 얹고, YouTube 설명용 챕터 타임스탬프 문자열을 생성.
- 표시 순서: 랭킹 내림차순(第N位 → 第1位). 콜드오픈은 1위(최대 충격) 소재 사용.
"""
from __future__ import annotations
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from src.core import hook_intro as hi
from src.core.longform import motion as M, segment as SEG

W, H = 1280, 720
CYAN = (120, 225, 245); MAG = (240, 95, 205); INK = (232, 240, 250); DIM = (150, 190, 210)
_serif, _sansb, _sansr, _sci, _mono = hi._serif, hi._sans_b, hi._sans_r, hi._sci, hi._mono
_BGM = Path(__file__).resolve().parents[3] / "assets" / "audio" / "bgm" / "longform_midnight_in_the_trench.mp3"


@dataclass
class CompileConfig:
    fps: int = 24
    cold_open_s: float = 9.0
    title_s: float = 5.0
    globalmap_s: float = 7.0
    outro_s: float = 18.0
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


def _globalmap_card(segments, out_png, cfg):
    im = _void(); d = ImageDraw.Draw(im)
    box = (150, 130, 1130, 610)
    d.rectangle(box, fill=(4, 12, 20, 150))
    mask, P = M._land_mask(M.MotionConfig(W=W, H=H, map_box=box), 1.0, 0.5, 0.45)
    px = mask.load()
    for y in range(0, H, 12):
        for x in range(0, W, 12):
            if px[x, y] > 128:
                d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=CYAN + (150,))
    for s in segments:
        cx, cy = P(s.region_nx, s.region_ny)
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), outline=MAG + (240,), width=3)
        d.ellipse((cx - 2, cy - 2, cx + 2, cy + 2), fill=MAG + (240,))
    d.text((W // 2, 90), f"本日のダイブ ・ {len(segments)}地点", font=_sansb(34), fill=INK + (240,), anchor="mm")
    im.convert("RGB").save(out_png); return out_png


def _outro_card(segments_desc, out_png):
    im = _void(); d = ImageDraw.Draw(im)
    t = _grad("あなたの1位は?", _serif(76)); im.alpha_composite(t, (W // 2 - t.width // 2, 90))
    y = 240
    for s in segments_desc:  # 5→1 순
        d.text((W // 2, y), f"第{s.rank}位  {s.jp_name}", font=_sansb(34), fill=INK + (235,), anchor="mm")
        y += 56
    d.text((W // 2, H - 130), "チャンネル登録で、次の深海へ。", font=_sansb(30), fill=CYAN + (235,), anchor="mm")
    d.text((W // 2, H - 70), "각 生き物のショートはプロフィールから", font=_sansr(24), fill=DIM + (220,), anchor="mm")
    im.convert("RGB").save(out_png); return out_png


def _cold_open(top_spec, out, cfg):
    """1위 소재 + 도발 훅 텍스트 오버레이."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    # 상단 훅
    d.rectangle((0, 0, W, 130), fill=(4, 10, 18, 150))
    d.text((W // 2, 66), top_spec.stamp_line, font=_sansb(48), fill=INK + (255,), anchor="mm")
    d.text((W // 2, H - 50), "深海の【衝撃】生き物ランキング", font=_sansr(26), fill=DIM + (220,), anchor="mm")
    hud = str(Path(out).with_suffix(".png")); ov.save(hud)
    _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{top_spec.footage_start}", "-t", f"{cfg.cold_open_s}",
          "-i", top_spec.footage_path, "-i", hud, "-filter_complex",
          f"[0:v]scale={W}:{H},setsar=1,{cfg.seg_cfg.grade}[g];[g][1:v]overlay=0:0,fade=t=in:st=0:d=0.3[v]",
          "-map", "[v]", "-r", str(cfg.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", out])


def _ts(sec):
    m, s = divmod(int(sec), 60)
    return f"{m}:{s:02d}"


def compile_longform(theme_word: str, segments: list[SEG.SegmentSpec], out_dir: str,
                     cfg: CompileConfig | None = None) -> dict:
    cfg = cfg or CompileConfig()
    wd = Path(out_dir); wd.mkdir(parents=True, exist_ok=True)
    segs = sorted(segments, key=lambda s: -s.rank)     # 5→1 표시 순
    top = min(segments, key=lambda s: s.rank)          # 1위(최대 충격)
    n = len(segments)

    parts = []          # (label, video_path, dur)
    # 콜드오픈
    co = str(wd / "cold.mp4"); _cold_open(top, co, cfg); parts.append(("オープニング", co, cfg.cold_open_s))
    # 타이틀
    tc = str(wd / "title.mp4"); _still_clip(_title_card(theme_word, n, str(wd / "title.png")), cfg.title_s, tc, cfg)
    parts.append((None, tc, cfg.title_s))
    # 글로벌 지도
    gm = str(wd / "gmap.mp4"); _still_clip(_globalmap_card(segs, str(wd / "gmap.png"), cfg), cfg.globalmap_s, gm, cfg)
    parts.append((None, gm, cfg.globalmap_s))
    # 세그먼트 ×N (5→1)
    for i, s in enumerate(segs):
        r = SEG.render_segment(s, str(wd / f"seg{i}"), cfg.seg_cfg)
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

    concat = wd / "concat.txt"
    concat.write_text("\n".join(f"file '{p}'" for p in norm), encoding="utf-8")
    body = str(wd / "body_all.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
          "-c", "copy", body])
    total_s = sum(d for _l, _v, d in parts)

    # 연속 BGM 베드 얹기(전체) — 세그먼트 자체 오디오와 amix
    final = str(wd / "longform.mp4")
    if _BGM.exists():
        _run(["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-stream_loop", "-1", "-i", str(_BGM),
              "-filter_complex",
              f"[1:a]volume=0.20,afade=t=in:st=0:d=2,afade=t=out:st={total_s - 3:.2f}:d=3[bed];"
              f"[0:a][bed]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.93[a]",
              "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", final])
    else:
        final = body

    # 챕터(YouTube 설명용)
    chapters = []
    acc = 0.0
    for lab, _v, dur in parts:
        if lab:
            chapters.append(f"{_ts(acc)} {lab}")
        acc += dur
    return {"video": final, "total_s": round(total_s, 2), "chapters": "\n".join(chapters), "n": n}


def _has_no_audio(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                        "stream=index", "-of", "csv=p=0", path], capture_output=True, text=True)
    return not r.stdout.strip()
