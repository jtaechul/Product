"""롱폼 세그먼트 조립 — 모션 인트로(+SFX) → 16:9 실사 + 도감 HUD + 순위카드 + 상세 나레이션/자막 → 데이터 스탬프.

한 종(랭킹 1개)당 하나의 세그먼트 mp4를 만든다. BGM은 넣지 않는다(전체 컴파일 단계에서
연속 베드로 얹음). 세그먼트 자체 오디오 = 모션 SFX + 도달 붐 + 나레이션 + 스탬프 붐.
"""
from __future__ import annotations
import math
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from src.core import hook_intro as hi, narration_sync
from src.core.longform import motion as M, sfx as SFX

W, H = 1280, 720
CYAN = (120, 225, 245)
MAG = (240, 95, 205)
INK = (232, 240, 250)
DIM = (150, 190, 210)
_serif, _sansb, _sansr, _sci, _mono = hi._serif, hi._sans_b, hi._sans_r, hi._sci, hi._mono


@dataclass
class SegmentSpec:
    rank: int
    jp_name: str
    sci_name: str
    depth_min: int
    depth_max: int
    size_label: str                    # 예: "約 40 cm"
    region_nx: float
    region_ny: float
    region_label_jp: str
    narration: list[str]               # 상세 나레이션 절(敬体·보통속도)
    stamp_line: str                    # 예: "4年半、絶食して卵を守る母。"
    stamp_big: str                     # 예: "最長の子育て"
    entry_no: int
    footage_path: str
    footage_start: float = 8.0
    target_depth_m: int = 5000
    creatures: list = field(default_factory=list)
    logo_box: tuple | None = None      # (x,y,w,h) 정규화 — 시드 힌트(자동 스캔에 합쳐짐)
    ko_name: str = ""                  # 국문명(대시보드 한국어 설명/챕터용, 화면엔 미노출)
    wm_boxes: list = field(default_factory=list)  # ★자동 스캔으로 확정된 delogo 박스(콜드오픈 재사용)


@dataclass
class SegmentConfig:
    fps: int = 24
    stamp_s: float = 4.0
    sub_scale: float = 2.0
    grade: str = "eq=contrast=1.10:saturation=1.15:brightness=-0.03,colorbalance=bm=0.05"


# ─────────────── 정적 도감 HUD 오버레이 ───────────────
def _sprite_solid(t, f, fill):
    im = Image.new("RGBA", (700, 240), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), t, font=f, fill=fill, anchor="la")
    return im.crop(im.getbbox())


def _sprite_grad(t, f):
    im = Image.new("RGBA", (900, 260), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), t, font=f, fill=(255, 255, 255, 255), anchor="la")
    bb = im.getbbox()
    cr = im.crop(bb)
    w, h = cr.size
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(w):
            tt = min(1, max(0, (x + y) / max(1, w + h - 2)))
            px[x, y] = tuple(int(CYAN[i] + (MAG[i] - CYAN[i]) * tt) for i in range(3))
    return Image.merge("RGBA", (*g.split(), cr.split()[3]))


def render_hud(spec: SegmentSpec, out_path: str) -> str:
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    def frame_lr(box, fill=(6, 18, 28, 200), col=CYAN, bw=3, tick=9):
        x0, y0, x1, y1 = box
        d.rectangle(box, fill=fill)
        c = col + (210,)
        d.line((x0, y0, x0, y1), fill=c, width=bw)
        d.line((x1, y0, x1, y1), fill=c, width=bw)
        for yy in (y0, y1):
            d.line((x0, yy, x0 + tick, yy), fill=c, width=bw)
            d.line((x1 - tick, yy, x1, yy), fill=c, width=bw)

    # 좌상단 도감 — 종명/학명은 패널 폭에 맞춰 자동 축소(프레임 밖 넘침 원천 차단)
    frame_lr((28, 28, 372, 246))
    d.text((48, 44), "DEEP-SEA DOSSIER", font=_mono(15), fill=CYAN + (220,))
    d.text((48, 78), spec.jp_name, font=hi._fit_font(spec.jp_name, 38, 312, _serif, 18),
           fill=INK + (255,))
    d.text((50, 128), spec.sci_name, font=hi._fit_font(spec.sci_name, 20, 310, _sci, 12),
           fill=DIM + (235,))
    d.text((48, 168), "水深", font=_sansr(17), fill=CYAN + (210,))
    d.text((150, 164), f"{spec.depth_min:,}–{spec.depth_max:,} m", font=_sansb(22), fill=INK + (255,))
    d.text((48, 202), "全長", font=_sansr(17), fill=CYAN + (210,))
    d.text((150, 198), spec.size_label, font=_sansb(22), fill=INK + (255,))
    # 우상단 순위(상하 중앙)
    rx0, ry0, rx1, ry1 = 1048, 30, 1252, 134
    frame_lr((rx0, ry0, rx1, ry1), tick=8)
    sr = _sprite_solid("RANK", _mono(14), CYAN + (210,))
    sn = _sprite_grad(f"第{spec.rank}位", _serif(48))
    gap = 6
    grp = sr.height + gap + sn.height
    top = ry0 + ((ry1 - ry0) - grp) // 2
    rc = (rx0 + rx1) // 2
    ov.alpha_composite(sr, (rc - sr.width // 2, top))
    ov.alpha_composite(sn, (rc - sn.width // 2, top + sr.height + gap))
    # 우측 수심 readout(플레이트로 가독성 보강)
    sx = 1232
    d.rectangle((sx - 96, 188, sx + 8, 622), fill=(4, 12, 20, 120))
    d.line((sx, 210, sx, 600), fill=CYAN + (140,), width=2)
    q = [spec.depth_min, int(spec.depth_min + (spec.depth_max - spec.depth_min) * 0.4),
         int(spec.depth_min + (spec.depth_max - spec.depth_min) * 0.72), spec.depth_max]
    for lb, yy in zip(q, (210, 340, 470, 600)):
        d.line((sx - 10, yy, sx, yy), fill=CYAN + (180,), width=2)
        d.text((sx - 16, yy), f"{lb:,} m", font=_mono(16), fill=INK + (230,), anchor="rm")
    d.text((32, H - 30), "ABYSS ・ 深淵アーカイブ", font=_sansr(20), fill=DIM + (200,), anchor="lm")
    ov.save(out_path)
    return out_path


def _stamp_base(spec: SegmentSpec) -> Image.Image:
    """엔드카드 정지 베이스(RGBA). 슬램 애니는 이 위에 스케일팝+셰이크로 만든다."""
    st = Image.new("RGB", (W, H), (4, 10, 16)).convert("RGBA")
    sd = ImageDraw.Draw(st)
    # 모든 텍스트는 화면 폭(≤W*0.86)에 맞춰 자동 축소 → 프레임/화면 밖 넘침 원천 차단
    title = _sprite_grad(spec.jp_name, hi._fit_font(spec.jp_name, 96, W * 0.86, _serif, 40))
    st.alpha_composite(title, (W // 2 - title.width // 2, 150))
    sd.text((W // 2, 300), spec.sci_name, font=hi._fit_font(spec.sci_name, 34, W * 0.86, _sci, 18),
            fill=DIM + (235,), anchor="mm")
    sd.text((W // 2, 405), spec.stamp_line, font=hi._fit_font(spec.stamp_line, 46, W * 0.88, _sansb, 24),
            fill=INK + (255,), anchor="mm")
    big = _sprite_grad(spec.stamp_big, hi._fit_font(spec.stamp_big, 64, W * 0.8, _serif, 34))
    st.alpha_composite(big, (W // 2 - big.width // 2, 470))
    sd.text((W // 2, H - 70), f"ENTRY LOGGED ・ No.{spec.entry_no:03d}", font=_mono(22),
            fill=CYAN + (220,), anchor="mm")
    return st


def render_stamp(spec: SegmentSpec, out_path: str) -> str:
    _stamp_base(spec).convert("RGB").save(out_path)
    return out_path


def render_stamp_frames(spec: SegmentSpec, out_dir: str, cfg: SegmentConfig) -> tuple[str, int]:
    """엔드카드를 '쾅' 슬램인 애니로 렌더 — 스케일팝 + 화면 흔들림 + 화이트 플래시.

    붐(효과음)은 세그먼트 오디오에서 스탬프 시작 시각에 배치되어 이 슬램과 동기된다.
    반환: (frames_glob, n).
    """
    base = _stamp_base(spec)
    fdir = Path(out_dir)
    fdir.mkdir(parents=True, exist_ok=True)
    n = int(cfg.stamp_s * cfg.fps)
    for i in range(n):
        t = i / cfg.fps
        appear = hi._smooth(min(1.0, t / 0.18))
        pop = 0.13 * (1.0 - appear)                 # 1.13 → 1.0
        Z = 1.06 + pop                              # 셰이크 여백 + 팝
        amp = 34.0 * math.exp(-t / 0.08)            # 빠르게 감쇠하는 흔들림
        dx, dy = amp * math.sin(t * 95), amp * math.cos(t * 72)
        bw, bh = int(W * Z), int(H * Z)
        big = base.resize((bw, bh), Image.LANCZOS)
        cx = max(0, min(bw - W, (bw - W) // 2 + int(dx)))
        cy = max(0, min(bh - H, (bh - H) // 2 + int(dy)))
        fr = big.crop((cx, cy, cx + W, cy + H)).convert("RGB")
        if t < 0.14:                                # 임팩트 화이트 플래시
            fa = 200 * (1.0 - hi._smooth(t / 0.14))
            if fa > 1:
                fr = Image.blend(fr, Image.new("RGB", (W, H), (255, 255, 255)), fa / 255.0)
        fr.save(str(fdir / f"s_{i:04d}.png"))
    return str(fdir / "s_%04d.png"), n


def _run(cmd):
    subprocess.run(cmd, check=True)


def render_segment(spec: SegmentSpec, out_dir: str, cfg: SegmentConfig | None = None) -> dict:
    """세그먼트 mp4 1개 생성. 반환: {video, total_s, motion_s, body_s, stamp_s}."""
    cfg = cfg or SegmentConfig()
    wd = Path(out_dir)
    wd.mkdir(parents=True, exist_ok=True)

    # 1) 나레이션(보통속도) + 자막(카라오케: 짧은 단위로 분할해 음성 정합)
    chunks = narration_sync.karaoke_split(spec.narration)
    nar = narration_sync.synthesize(chunks, str(wd), voice="ja-JP-KeitaNeural", rate="+0%")
    body_s = float(nar["duration"]) + 0.4
    ass = str(wd / "body.ass")
    narration_sync.build_synced_ass(nar["disp"], ass, hook_first=False, w=W, h=H, sub_scale=cfg.sub_scale)

    # 2) 모션 인트로(+SFX 이벤트) 프레임 → mp4
    mspec = M.MotionSpec(region_nx=spec.region_nx, region_ny=spec.region_ny,
                         region_label_jp=spec.region_label_jp, target_depth_m=spec.target_depth_m,
                         creatures=spec.creatures or _default_creatures())
    mcfg = M.MotionConfig(W=W, H=H, FPS=cfg.fps)
    meta = M.render_locate_descent(str(wd / "mframes"), mspec, mcfg)
    motion_s = meta["total_s"]
    intro = str(wd / "intro.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.fps),
          "-i", meta["frames_glob"], "-vf", f"scale={W}:{H},setsar=1", "-r", str(cfg.fps),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", intro])

    # 3) HUD 렌더(스탬프는 아래 5)에서 슬램 애니 프레임으로)
    hud = render_hud(spec, str(wd / "hud.png"))

    # 4) 본문: ★워터마크 QC(하드룰 #9) — 좌표 하드코딩 금지, 1초 간격 OCR로 자동 처리.
    #    ① 원본 클립 전체를 1초 간격 스캔 → 크레딧 슬레이트/대형 URL이 있는 초는 회피(시작점 이동)
    #    ② 남은 워터마크(로고 등)는 탐지 박스로 delogo → 그레이딩 → HUD → 자막 렌더
    #    ③ 렌더 결과를 다시 1초 간격 검증(NOAA 등 금지 문구) → 실패 시 박스 보강 1회 재렌더
    #    ④ 그래도 남으면 RuntimeError(WATERMARK_REMAINS) — 불량 영상 발행 차단.
    from src.core import watermark_qc as WQ
    wm = WQ.plan(spec.footage_path, spec.footage_start, body_s + 2.0,
                 extra_boxes=[spec.logo_box] if spec.logo_box else None)
    spec.footage_start = wm["start"]        # 콜드오픈(compile)도 같은 깨끗한 구간을 쓰게 반영
    boxes = list(wm["boxes"])
    body = str(wd / "body.mp4")
    bad: list = []
    for attempt in range(2):
        chain = WQ.delogo_chain(boxes, W, H)
        pre = ("," + chain) if chain else ""
        fc = (f"[0:v]scale={W}:{H},setsar=1{pre},{cfg.grade}[g];"
              f"[g][1:v]overlay=0:0[o];[o]ass={ass}[v]")
        _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{spec.footage_start}", "-t", f"{body_s:.2f}",
              "-i", spec.footage_path, "-i", hud, "-filter_complex", fc, "-map", "[v]",
              "-r", str(cfg.fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", body])
        bad = WQ.verify(body)
        if not bad:
            break
        # 검출된 문구 위치를 delogo 박스로 추가해 1회 재렌더(패딩 포함)
        boxes = WQ._merge_boxes(boxes + [tuple(b["box"]) for b in bad])
    if bad:
        raise RuntimeError(
            f"WATERMARK_REMAINS: rank{spec.rank} {spec.jp_name} — 금지 문구 잔존 "
            f"{[(round(b['t']), b['text']) for b in bad[:6]]} (발행 차단)")
    spec.wm_boxes = boxes                   # 콜드오픈(compile)이 같은 박스로 delogo

    # 5) 스탬프(엔드카드) — 쾅 슬램 애니(스케일팝+셰이크+플래시). 붐과 동기.
    sfg, _sn = render_stamp_frames(spec, str(wd / "sframes"), cfg)
    stampv = str(wd / "stamp.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(cfg.fps), "-i", sfg,
          "-vf", f"scale={W}:{H},setsar=1", "-r", str(cfg.fps),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", stampv])

    # 6) concat 영상 — ★concat 목록의 경로는 반드시 절대경로(ffmpeg는 상대경로를
    #    cat.txt 위치 기준으로 다시 해석해 경로가 중복됨. CI의 상대 --out에서 터졌던 버그).
    cat = wd / "cat.txt"
    _abs = lambda p: str(Path(p).resolve())  # noqa: E731
    cat.write_text(f"file '{_abs(intro)}'\nfile '{_abs(body)}'\nfile '{_abs(stampv)}'\n", encoding="utf-8")
    segv = str(wd / "seg_v.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(cat),
          "-c", "copy", segv])
    total_s = motion_s + body_s + cfg.stamp_s

    # 7) 오디오: 모션 SFX + 도달 붐 + 나레이션 + 스탬프 붐 (BGM 없음)
    s = SFX.gen_all(str(wd))
    boom = hi.generate_boom(str(wd / "boom.wav"), hi.HookIntroConfig())
    ms = lambda t: int(t * 1000)  # noqa: E731
    stamp_boom = motion_s + body_s
    # [0]=무음 베드(전체 길이 고정 → -shortest가 스탬프를 자르지 않게), 이후 나레이션/붐/SFX
    inputs = ["-f", "lavfi", "-t", f"{total_s:.3f}", "-i", "anullsrc=r=44100:cl=stereo",
              "-i", nar["mp3"], "-i", boom, "-i", s["scan"], "-i", s["lockon"], "-i", s["splash"]]
    af = (f"[0:a]volume=0[bed];"
          f"[1:a]adelay={ms(motion_s)}|{ms(motion_s)},volume=1.6[nar];"
          f"[2:a]adelay={ms(meta['boom_s'])}|{ms(meta['boom_s'])},volume=1.0[bm1];"
          f"[2:a]adelay={ms(stamp_boom)}|{ms(stamp_boom)},volume=1.0[bm2];"
          f"[3:a]adelay={ms(meta['scan_s'])}|{ms(meta['scan_s'])},volume=1.35[sc];"
          f"[4:a]adelay={ms(meta['lockon_s'])}|{ms(meta['lockon_s'])},volume=1.35[lk];"
          f"[5:a]adelay={ms(meta['splash_s'])}|{ms(meta['splash_s'])},volume=1.5[sp];"
          f"[bed][nar][bm1][bm2][sc][lk][sp]amix=inputs=7:duration=first:normalize=0,"
          f"alimiter=limit=0.92[a]")
    sega = str(wd / "seg_a.m4a")
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", af,
          "-map", "[a]", "-c:a", "aac", "-b:a", "192k", sega])

    out = str(wd / f"segment_rank{spec.rank}.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", segv, "-i", sega,
          "-c:v", "copy", "-c:a", "aac", "-shortest", out])
    return {"video": out, "total_s": round(total_s, 3), "motion_s": motion_s,
            "body_s": round(body_s, 3), "stamp_s": cfg.stamp_s}


def _default_creatures():
    C = M.Creature
    return [C(150, "fish", 300), C(600, "jelly", 950), C(1100, "squid", 320),
            C(2400, "angler", 950), C(3600, "grenadier", 320), C(4700, "angler", 950)]
