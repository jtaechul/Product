"""공용 엔딩에 손글씨를 입힌다 (운영자 확정 2026-09-27).

영상(도면 + 파도·배 미세 일렁임)은 모든 편 공용 1개이고, 여기서 **그 편 생물 이름만 바꿔** 글씨를 입힌다.
- 글씨는 화면 가운데. 줄마다 왼쪽→오른쪽으로 먹이 번지듯 써진다(AI가 쓴 글씨 금지 — 뭉개짐).
- 파도 선과 겹쳐도 읽히게 글씨 뒤에만 종이색을 옅게 깐다.
- 번호(No.)는 쓰지 않는다. 음악 없음(소리는 나레이션만 — 여기서는 영상만 만든다).

사용: python ending_overlay.py <공용엔딩.mp4> <생물 일본어 이름> <출력.mp4>
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = Path(__file__).resolve().parents[2] / "vendor" / "fonts" / "YujiSyuku-Regular.ttf"
W, H, FPS = 720, 1280, 24
INK = (52, 36, 22)
PAPER = (232, 214, 184)

# (문구, 글자 크기, 쓰기 시작 초, 쓰기 끝 초) — {name} 자리에 그 편 생물 이름
LINES = [
    ("深海図鑑", 58, 0.3, 1.1),
    ("{name}", 66, 1.2, 2.4),
    ("次のページは…？", 46, 2.6, 3.5),
    ("あなたが見てみたい", 46, 3.7, 4.6),
    ("深海の生き物は？", 46, 4.6, 5.4),
    ("コメントで教えてください", 42, 5.6, 6.6),
]
GAP = [0, 26, 44, 20, 8, 26]           # 줄 앞 간격(px) — 제목·이름 뒤를 조금 띄운다
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


def _wash(top: int, bottom: int) -> Image.Image:
    """글씨 뒤 종이색 옅은 번짐(가장자리 부드럽게)."""
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle([40, top - 40, W - 40, bottom + 40], radius=60, fill=110)
    m = m.filter(ImageFilter.GaussianBlur(28))
    im = Image.new("RGBA", (W, H), PAPER + (0,))
    im.putalpha(m)
    return im


def render_frames(name: str, dur: float, out_dir: Path) -> int:
    rows, top, bottom = layout(name)
    wash = _wash(top, bottom)
    n = int(round(dur * FPS))
    # 줄별 완성 이미지(잉크) 미리 그리기
    ink = []
    for r in rows:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tw = r["font"].getlength(r["text"])
        x = int((W - tw) / 2)
        ImageDraw.Draw(im).text((x, r["y"]), r["text"], font=r["font"], fill=INK + (255,))
        ink.append((im, x, int(tw)))
    for i in range(n):
        t = i / FPS
        fr = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        wa = min(1.0, t / 0.4)                  # 종이 번짐은 0.4초에 걸쳐 나타남
        if wa > 0:
            w2 = wash.copy()
            w2.putalpha(wash.getchannel("A").point(lambda v, k=wa: int(v * k)))
            fr = Image.alpha_composite(fr, w2)
        for r, (im, x, tw) in zip(rows, ink):
            if t < r["t0"]:
                continue
            p = 1.0 if t >= r["t1"] else (t - r["t0"]) / (r["t1"] - r["t0"])
            reveal = int(x + tw * p) + 6
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


def main(src: str, name: str, dst: str) -> None:
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                src], capture_output=True, text=True, check=True).stdout.strip())
    with tempfile.TemporaryDirectory() as td:
        render_frames(name, dur, Path(td))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-framerate", str(FPS),
                        "-i", str(Path(td) / "o%04d.png"), "-filter_complex",
                        f"[0:v]scale={W}:{H},setsar=1,fps={FPS}[b];[b][1:v]overlay=0:0:shortest=1[v]",
                        "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", dst],
                       check=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
