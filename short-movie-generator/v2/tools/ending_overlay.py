"""공용 엔딩에 손글씨를 입힌다 (운영자 확정 2026-09-27).

영상(도면 + 파도·배 미세 일렁임)은 모든 편 공용 1개이고, 여기서 **그 편 생물 이름만 바꿔** 글씨를 입힌다.
- 글씨는 화면 가운데. 줄마다 왼쪽→오른쪽으로 먹이 번지듯 써진다(AI가 쓴 글씨 금지 — 뭉개짐).
- 글씨 뒤 흐림 없음 — 얇은 종이색 테두리로 잉크 선 위에서도 읽히게 한다(운영자 확정).
- 앞 1초는 양피지가 좌우로 펼쳐지는 편집 효과.
- 번호(No.)는 쓰지 않는다. 음악 없음(소리는 나레이션만 — 여기서는 영상만 만든다).

사용: python ending_overlay.py <공용엔딩.mp4> <생물 일본어 이름> <출력.mp4>
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[2] / "vendor" / "fonts" / "YujiSyuku-Regular.ttf"
W, H, FPS = 720, 1280, 24
INK = (52, 36, 22)
PAPER = (232, 214, 184)

# (문구, 글자 크기, 쓰기 시작 초, 쓰기 끝 초) — {name} 자리에 그 편 생물 이름. 시간은 양피지 펼침(INTRO_S) 포함 전체 기준.
# ★'次のページは…？' 줄 삭제 · 줄 간격 좁힘 · 글씨 뒤 흐림 없음(운영자 확정 2026-09-27)
LINES = [
    ("深海図鑑", 56, 1.2, 1.8),
    ("{name}", 64, 1.9, 2.8),
    ("あなたが見てみたい", 46, 3.0, 3.7),
    ("深海の生き物は？", 46, 3.7, 4.4),
    ("コメントで教えてください", 42, 4.6, 5.4),
]
GAP = [0, 6, 18, 2, 12]                 # 줄 앞 간격(px)
INTRO_S = 1.0                           # 앞 1초: 양피지가 가운데에서 좌우로 빠르게 펼쳐짐(편집 효과 — AI에 맡기면 종이가 녹아내림)
STROKE = 3                              # 글씨 테두리(종이색) — 잉크 선 위에서도 또렷하게
MAX_W = W - 120


def _fit(font_path: Path, text: str, size: int) -> ImageFont.FreeTypeFont:
    while size > 20:
        f = ImageFont.truetype(str(font_path), size)
        if f.getlength(text) <= MAX_W:
            return f
        size -= 2
    return ImageFont.truetype(str(font_path), size)


def layout(name: str):
    rows, y = [], 0
    for (txt, size, t0, t1), gap in zip(LINES, GAP):
        txt = txt.format(name=name)
        f = _fit(FONT, txt, size)
        a, d = f.getmetrics()
        y += gap
        rows.append({"text": txt, "font": f, "y": y, "h": a + d, "t0": t0, "t1": t1})
        y += a + d
    top = int(H * 0.5 - y / 2)                  # 화면 가운데 정렬
    for r in rows:
        r["y"] += top
    return rows, top, top + y


def render_frames(name: str, dur: float, out_dir: Path) -> int:
    rows, _top, _bottom = layout(name)
    n = int(round(dur * FPS))
    # 줄별 완성 이미지(잉크) 미리 그리기
    ink = []
    for r in rows:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tw = r["font"].getlength(r["text"])
        x = int((W - tw) / 2)
        ImageDraw.Draw(im).text((x, r["y"]), r["text"], font=r["font"], fill=INK + (255,),
                                stroke_width=STROKE, stroke_fill=PAPER + (255,))
        ink.append((im, x, int(tw)))
    for i in range(n):
        t = i / FPS
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for r, (im, x, tw) in zip(rows, ink):
            if t < r["t0"]:
                continue
            p = 1.0 if t >= r["t1"] else (t - r["t0"]) / (r["t1"] - r["t0"])
            reveal = int(x - STROKE + (tw + 2 * STROKE) * p) + 6
            mask = Image.new("L", (W, H), 0)
            md = ImageDraw.Draw(mask)
            md.rectangle([0, 0, reveal, H], fill=255)
            if p < 1.0:                         # 붓끝: 쓰는 지점만 살짝 옅게
                md.rectangle([reveal - 10, 0, reveal, H], fill=150)
            layer = im.copy()
            layer.putalpha(Image.composite(im.getchannel("A"), Image.new("L", (W, H), 0), mask))
            fr = Image.alpha_composite(fr, layer)
        fr.save(out_dir / f"o{i:04d}.png")
    return n


def _ease(x: float) -> float:
    return 1 - (1 - x) ** 3


def render_intro(first_frame: Path, out_dir: Path) -> int:
    """양피지 펼침: 첫 프레임을 가운데에서 좌우로 열고, 열리는 양 끝에 말린 두루마리 봉을 그린다."""
    base = Image.open(first_frame).convert("RGB").resize((W, H))
    n = int(round(INTRO_S * FPS))
    for i in range(n):
        p = _ease((i + 1) / n)
        half = max(6, int(W / 2 * p))
        fr = Image.new("RGB", (W, H), (8, 6, 5))
        l, r = W // 2 - half, W // 2 + half
        fr.paste(base.crop((l, 0, r, H)), (l, 0))
        d = ImageDraw.Draw(fr)
        if p < 0.999:
            for cx in (l, r):                  # 말린 종이 봉(음영 원기둥)
                for k in range(-14, 15):
                    shade = int(200 - abs(k) * 7)
                    d.line([(cx + k, int(H * 0.04)), (cx + k, int(H * 0.96))],
                           fill=(shade, int(shade * 0.86), int(shade * 0.66)))
        fr.save(out_dir / f"i{i:04d}.png")
    return n


def main(src: str, name: str, dst: str) -> None:
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", f"scale={W}:{H},setsar=1,fps={FPS}",
                        "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(t / "body.mp4")], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(t / "body.mp4"), "-frames:v", "1",
                        str(t / "first.png")], check=True)
        render_intro(t / "first.png", t)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(t / "i%04d.png"),
                        "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(t / "intro.mp4")], check=True)
        (t / "list.txt").write_text(f"file '{t / 'intro.mp4'}'\nfile '{t / 'body.mp4'}'\n")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(t / "list.txt"),
                        "-c", "copy", str(t / "full.mp4")], check=True)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                    str(t / "full.mp4")], capture_output=True, text=True, check=True).stdout.strip())
        render_frames(name, dur, t)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(t / "full.mp4"), "-framerate", str(FPS),
                        "-i", str(t / "o%04d.png"), "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1[v]",
                        "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst],
                       check=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
