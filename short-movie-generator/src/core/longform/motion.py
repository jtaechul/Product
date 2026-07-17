"""롱폼 세그먼트 시작 모션 — 세계지도 스캔 → 해역(면) 락온 → 스크롤 수심 하강 → 도달.

검증된 프로토타입(모션 v6)을 정식 모듈로 이식. 순수 PIL 렌더(무료·결정론).
공개 API: render_locate_descent(out_dir, spec, cfg) → 프레임 PNG 시퀀스 + 타이밍 메타.

디자인 규칙(하드룰 준수):
- 대륙 = 실제 세계지도(Natural Earth 110m land) 도트. 경도 unwrap으로 seam 방지.
- 위치는 GPS 좌표가 아니라 '해역(면) 하이라이트'만(가짜 좌표 금지). 수심만 실제 숫자.
- 각진 HUD(시안+마젠타), 오프닝/레이아웃 톤과 통일.
"""
from __future__ import annotations
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from src.core import hook_intro as hi

_GEO = Path(__file__).resolve().parents[3] / "assets" / "geo" / "ne_110m_land.geojson"

CYAN = (120, 225, 245)
MAG = (240, 95, 205)
INK = (232, 240, 250)
DIM = (140, 180, 205)

_serif = hi._serif
_sansb = hi._sans_b
_sansr = hi._sans_r
_mono = hi._mono


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _smoother(x: float) -> float:
    """느리게→빠르게→느리게(smootherstep)."""
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (x * 6 - 15) + 10)


def _load_land_rings():
    gj = json.load(open(_GEO, encoding="utf-8"))
    rings = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                rings.append(ring)

    def unwrap(ring):
        out = []
        prev = None
        for lon, lat in ring:
            L = float(lon)
            if prev is not None:
                while L - prev > 180:
                    L -= 360
                while L - prev < -180:
                    L += 360
            out.append((L, lat))
            prev = L
        return out

    # nx=lon/360 (연속), ny=(90-lat)/180 — Pacific-centered
    return [[(lon / 360.0, (90.0 - lat) / 180.0) for lon, lat in unwrap(r)] for r in rings]


_URINGS = None


def _uring():
    global _URINGS
    if _URINGS is None:
        _URINGS = _load_land_rings()
    return _URINGS


@dataclass
class Creature:
    depth_m: int
    kind: str          # fish|jelly|squid|angler|grenadier
    x: int             # 화면 x(좌/우 배치)


@dataclass
class MotionSpec:
    """세그먼트 시작 모션 입력."""
    region_nx: float = 0.63            # 해역 중심(지도 정규화 x, lon/360)
    region_ny: float = 0.25            # 해역 중심 y((90-lat)/180)
    region_label_jp: str = "北東太平洋"
    region_label_en: str = "生息海域"
    locate_label: str = "LOCATING SPECIMEN…"   # 지도 스캔 중 상단 상태문구(난파선은 'LOCATING WRECK…')
    target_depth_m: int = 5000
    creatures: list[Creature] = field(default_factory=list)
    zones: list[tuple] = field(default_factory=lambda: [
        (100, "有光層"), (600, "薄明層"), (2500, "漸深層"), (4600, "深海層")])


@dataclass
class MotionConfig:
    W: int = 1280
    H: int = 720
    FPS: int = 24
    t_map: float = 3.2                 # 지도 스캔+줌
    t_flash: float = 0.22              # 플래시 전환
    t_desc: float = 2.9                # 하강(≤3s)
    t_hold: float = 0.4                # 도달 홀드
    depth_px_per_m: float = 0.5        # 1000m=500px → 5000m=2500px 스크롤
    map_box: tuple = (150, 120, 1130, 620)
    dot_spacing: int = 12


def _header(d, cfg, step):
    d.rectangle((0, 0, cfg.W, 4), fill=CYAN + (120,))
    d.text((40, 26), "ABYSS ・ DIVE LOG", font=_sansr(18), fill=CYAN + (220,))
    d.text((cfg.W - 40, 26), step, font=_mono(16), fill=MAG + (220,), anchor="ra")


def _corner_box(d, box, t=14, col=CYAN, bw=2):
    x0, y0, x1, y1 = box
    for cx, cy, dx, dy in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        d.line((cx, cy, cx + dx * t, cy), fill=col + (230,), width=bw)
        d.line((cx, cy, cx, cy + dy * t), fill=col + (230,), width=bw)


def _void(cfg):
    im = Image.new("RGB", (cfg.W, cfg.H), (6, 14, 22))
    d = ImageDraw.Draw(im)
    for y in range(cfg.H):
        t = y / cfg.H
        d.line((0, y, cfg.W, y), fill=(int(6 + 6 * t), int(14 + 10 * t), int(22 + 16 * t)))
    return im.convert("RGBA")


# ── 도트 생물 실루엣 ──
def _fish(md, cx, cy, s):
    md.ellipse((cx - s, cy - s * 0.5, cx + s * 0.5, cy + s * 0.5), fill=255)
    md.polygon([(cx + s * 0.5, cy), (cx + s, cy - s * 0.4), (cx + s, cy + s * 0.4)], fill=255)


def _jelly(md, cx, cy, s):
    md.pieslice((cx - s, cy - s * 0.9, cx + s, cy + s * 0.5), 180, 360, fill=255)
    for i in range(-2, 3):
        tx = cx + i * s * 0.3
        md.line((tx, cy + s * 0.2, tx + i * 3, cy + s * 1.0), fill=255, width=int(s * 0.18))


def _squid(md, cx, cy, s):
    md.polygon([(cx, cy - s), (cx - s * 0.45, cy - s * 0.25), (cx + s * 0.45, cy - s * 0.25)], fill=255)
    md.line((cx, cy - s * 0.25, cx, cy + s * 0.15), fill=255, width=int(s * 0.35))
    for i in range(-2, 3):
        md.line((cx, cy + s * 0.15, cx + i * s * 0.28, cy + s), fill=255, width=int(s * 0.14))


def _angler(md, cx, cy, s):
    md.ellipse((cx - s * 0.7, cy - s * 0.6, cx + s * 0.7, cy + s * 0.6), fill=255)
    md.polygon([(cx + s * 0.6, cy), (cx + s, cy - s * 0.35), (cx + s, cy + s * 0.35)], fill=255)
    md.line((cx - s * 0.2, cy - s * 0.55, cx - s * 0.5, cy - s * 1.2), fill=255, width=int(s * 0.14))
    md.ellipse((cx - s * 0.62, cy - s * 1.35, cx - s * 0.38, cy - s * 1.1), fill=255)


def _grenadier(md, cx, cy, s):
    md.polygon([(cx - s, cy - s * 0.4), (cx + s * 0.2, cy - s * 0.28), (cx + s, cy),
                (cx + s * 0.2, cy + s * 0.28), (cx - s, cy + s * 0.4)], fill=255)


_SIL = {"fish": (_fish, 38), "jelly": (_jelly, 36), "squid": (_squid, 40),
        "angler": (_angler, 40), "grenadier": (_grenadier, 44)}


def _dot_sprite(kind, spacing=7, r=2, col=CYAN + (170,)):
    fn, s = _SIL[kind]
    S = int(s * 3)
    m = Image.new("L", (S, S), 0)
    fn(ImageDraw.Draw(m), S // 2, S // 2, s)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    od = ImageDraw.Draw(out)
    px = m.load()
    for y in range(0, S, spacing):
        for x in range(0, S, spacing):
            if px[x, y] > 128:
                od.ellipse((x - r, y - r, x + r, y + r), fill=col)
    bb = out.getbbox()
    return out.crop(bb) if bb else out


_SPRITES = None


def _sprites():
    global _SPRITES
    if _SPRITES is None:
        _SPRITES = {k: _dot_sprite(k) for k in _SIL}
    return _SPRITES


def _land_mask(cfg, scale, ccx, ccy):
    bx0, by0, bx1, by1 = cfg.map_box
    bw, bh = bx1 - bx0, by1 - by0

    def P(nx, ny):
        return (bx0 + ((nx - ccx) * scale + 0.5) * bw, by0 + ((ny - ccy) * scale + 0.5) * bh)

    mask = Image.new("L", (cfg.W, cfg.H), 0)
    md = ImageDraw.Draw(mask)
    for ring in _uring():
        for k in (-1, 0, 1, 2):
            pts = [P(nx + k, ny) for nx, ny in ring]
            xs = [p[0] for p in pts]
            if max(xs) < bx0 or min(xs) > bx1:
                continue
            md.polygon(pts, fill=255)
    boxm = Image.new("L", (cfg.W, cfg.H), 0)
    ImageDraw.Draw(boxm).rectangle(cfg.map_box, fill=255)
    return Image.composite(mask, Image.new("L", (cfg.W, cfg.H), 0), boxm), P


def _map_frame(t, spec, cfg):
    img = _void(cfg)
    ov = Image.new("RGBA", (cfg.W, cfg.H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    bx0, by0, bx1, by1 = cfg.map_box
    bw, bh = bx1 - bx0, by1 - by0
    zt = _smooth((t - 0.55) / 0.45) if t > 0.55 else 0.0
    scale = 1.0 + 1.3 * zt
    d.rectangle(cfg.map_box, fill=(4, 12, 20, 150))
    _corner_box(d, cfg.map_box)
    for i in range(13):
        x = bx0 + bw * i / 12
        d.line((x, by0, x, by1), fill=CYAN + (20,), width=1)
    for j in range(7):
        y = by0 + bh * j / 6
        d.line((bx0, y, bx1, y), fill=CYAN + (20,), width=1)
    mask, P = _land_mask(cfg, scale, spec.region_nx, spec.region_ny)
    px = mask.load()
    for y in range(0, cfg.H, cfg.dot_spacing):
        for x in range(0, cfg.W, cfg.dot_spacing):
            if px[x, y] > 128:
                d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=CYAN + (170,))
    if t < 0.55:
        sw = _smooth(t / 0.5)
        sy = by0 + bh * sw
        g = Image.new("RGBA", (cfg.W, cfg.H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for k in range(70):
            gd.line((bx0, sy - k, bx1, sy - k), fill=CYAN + (int(55 * (1 - k / 70)),))
        ov.alpha_composite(g)
        d.line((bx0, sy, bx1, sy), fill=CYAN + (230,), width=2)
        d.text((bx0 + 10, 95), getattr(spec, "locate_label", "LOCATING SPECIMEN…"),
               font=_mono(22), fill=INK + (240,))
    if t > 0.35:
        at = _smooth((t - 0.35) / 0.3)
        cx, cy = P(spec.region_nx, spec.region_ny)
        rx, ry = 0.14 * bw * scale, 0.11 * bh * scale
        for dx, dy in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            ex, ey = cx + dx * rx, cy + dy * ry
            d.line((ex, ey, ex - dx * 26, ey), fill=MAG + (int(235 * at),), width=3)
            d.line((ex, ey, ex, ey - dy * 26), fill=MAG + (int(235 * at),), width=3)
        if t > 0.45:
            lt = _smooth((t - 0.45) / 0.25)
            scr = Image.new("RGBA", (cfg.W, cfg.H), (0, 0, 0, 0))
            ImageDraw.Draw(scr).ellipse((cx - 150, cy - 46, cx + 150, cy + 40), fill=(4, 10, 18, int(150 * lt)))
            ov.alpha_composite(scr.filter(ImageFilter.GaussianBlur(10)))
            d.text((cx, cy - 13), spec.region_label_jp, font=_sansb(30), fill=INK + (int(255 * lt),), anchor="mm")
            d.text((cx, cy + 18), spec.region_label_en, font=_sansr(15), fill=DIM + (int(220 * lt),), anchor="mm")
    _header(d, cfg, "STEP 1 : LOCATE" if t < 0.55 else "STEP 2 : ZOOM-IN")
    img.alpha_composite(ov)
    return img


def _descent_frame(dt, boom, spec, cfg):
    depth = spec.target_depth_m * _smoother(dt)
    centerY = 360
    SCALE = cfg.depth_px_per_m
    img = Image.new("RGB", (cfg.W, cfg.H), (0, 0, 0))
    dd = ImageDraw.Draw(img)
    top, bot = (14, 46, 58), (1, 4, 7)
    dark = _smooth(dt)
    for y in range(cfg.H):
        f = y / cfg.H
        base = tuple(int(top[i] + (bot[i] - top[i]) * f) for i in range(3))
        base = tuple(int(c * (1 - 0.7 * dark)) for c in base)
        dd.line((0, y, cfg.W, y), fill=base)
    img = img.convert("RGBA")
    ov = Image.new("RGBA", (cfg.W, cfg.H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    cx = cfg.W // 2
    d.line((cx, 0, cx, cfg.H), fill=CYAN + (90,), width=2)
    scroll = (depth * SCALE) % 40
    yy = -40 + scroll
    while yy < cfg.H:
        d.line((cx - 9, yy, cx, yy + 10), fill=CYAN + (120,), width=2)
        d.line((cx + 9, yy, cx, yy + 10), fill=CYAN + (120,), width=2)
        yy += 40
    ax = cfg.W - 130
    d.line((ax, 0, ax, cfg.H), fill=CYAN + (120,), width=2)
    step = 500
    dep = 0
    while dep <= spec.target_depth_m + step:
        y = centerY + (dep - depth) * SCALE
        if -30 < y < cfg.H + 30:
            major = dep % 1000 == 0
            d.line((ax - (14 if major else 8), y, ax, y), fill=CYAN + (180,), width=2)
            if major and y > 50:   # 헤더(상단)와 겹침 방지
                d.text((ax - 20, y), f"{dep:,} m", font=_mono(16), fill=DIM + (230,), anchor="rm")
        dep += step
    for zdep, zname in spec.zones:
        y = centerY + (zdep - depth) * SCALE
        if -20 < y < cfg.H + 20:
            d.line((cx + 40, y, cx + 70, y), fill=CYAN + (90,), width=1)
            d.text((cx + 78, y), zname, font=_sansr(17), fill=CYAN + (150,), anchor="lm")
    spr = _sprites()
    for c in spec.creatures:
        y = centerY + (c.depth_m - depth) * SCALE
        if -90 < y < cfg.H + 90:
            sp = spr[c.kind]
            ov.alpha_composite(sp, (int(c.x - sp.width / 2), int(y - sp.height / 2)))
            d.text((c.x, y + sp.height // 2 + 8), f"~{c.depth_m}m", font=_mono(13), fill=DIM + (180,), anchor="ma")
    jx = int(6 * math.sin(dt * 70))
    jy = int(4 * math.sin(dt * 95))
    ay = centerY + jy
    d.polygon([(cx + jx, ay + 22), (cx + jx - 17, ay - 11), (cx + jx + 17, ay - 11)], fill=MAG + (245,))
    val = int(depth / 10) * 10
    s2 = Image.new("RGBA", (860, 180), (0, 0, 0, 0))
    ImageDraw.Draw(s2).text((10, 10), f"{val:,} m", font=_serif(72), fill=(255, 255, 255, 255), anchor="la")
    s2 = s2.crop(s2.getbbox())
    w, h = s2.size
    grad = Image.new("RGB", (w, h))
    gp = grad.load()
    for y2 in range(h):
        for x2 in range(w):
            tt = min(1, max(0, (x2 + y2) / max(1, w + h - 2)))
            gp[x2, y2] = tuple(int(CYAN[i] + (MAG[i] - CYAN[i]) * tt) for i in range(3))
    num = Image.merge("RGBA", (*grad.split(), s2.split()[3]))
    ov.alpha_composite(num, (70, centerY - num.height // 2))
    d.text((70, centerY - num.height // 2 - 30), "DEPTH", font=_mono(18), fill=CYAN + (220,))
    if boom > 0:
        ov.alpha_composite(Image.new("RGBA", (cfg.W, cfg.H), (190, 235, 255, int(235 * boom))))
    _header(d, cfg, "STEP 3 : DESCENT")
    img.alpha_composite(ov)
    return img


def render_locate_descent(out_dir: str, spec: MotionSpec | None = None,
                          cfg: MotionConfig | None = None) -> dict:
    """세그먼트 시작 모션 프레임(PNG) 시퀀스를 out_dir에 렌더.

    반환: {frames_glob, fps, total_s, boom_s, n_frames}
    """
    spec = spec or MotionSpec()
    cfg = cfg or MotionConfig()
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    total = cfg.t_map + cfg.t_flash + cfg.t_desc + cfg.t_hold
    n = int(total * cfg.FPS)
    boom_s = cfg.t_map + cfg.t_flash + cfg.t_desc * 0.93
    # SFX 이벤트 시각(초) — 시각 이벤트에 정합
    scan_s = round(cfg.t_map * 0.18, 3)                 # 스캔 스윕 시작
    lockon_s = round(cfg.t_map * 0.52, 3)               # 해역 락온
    splash_s = round(cfg.t_map + cfg.t_flash * 0.15, 3)  # 하강 직전(물속 진입)
    for i in range(n):
        t = i / cfg.FPS
        if t < cfg.t_map:
            f = _map_frame(t / cfg.t_map, spec, cfg)
        elif t < cfg.t_map + cfg.t_flash:
            f = _map_frame(1.0, spec, cfg)
            ff = (t - cfg.t_map) / cfg.t_flash
            f.alpha_composite(Image.new("RGBA", (cfg.W, cfg.H), (255, 255, 255, int(210 * (1 - abs(ff - 0.5) * 2)))))
        elif t < cfg.t_map + cfg.t_flash + cfg.t_desc:
            dt = (t - cfg.t_map - cfg.t_flash) / cfg.t_desc
            prog = min(1.0, dt / 0.93)
            boom = max(0.0, (dt - 0.93) / 0.07) if dt > 0.93 else 0.0
            f = _descent_frame(prog, min(1.0, boom), spec, cfg)
        else:
            ht = (t - (cfg.t_map + cfg.t_flash + cfg.t_desc)) / cfg.t_hold
            f = _descent_frame(1.0, max(0.0, 1 - ht * 2.5), spec, cfg)
        f.convert("RGB").save(str(Path(out_dir) / f"m_{i:04d}.png"))
    return {"frames_glob": str(Path(out_dir) / "m_%04d.png"), "fps": cfg.FPS,
            "total_s": round(total, 3), "boom_s": round(boom_s, 3), "n_frames": n,
            "scan_s": scan_s, "lockon_s": lockon_s, "splash_s": splash_s}
