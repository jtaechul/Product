"""공용 엔딩 편집 — 확정 영상 위에 손글씨·나레이션을 입힌다 (운영자 확정 2026-09-27).

확정 영상(`_shared/approved/ending_omni_v2_trim.mp4`, Omni Flash): 말린 두루마리가 펼쳐짐 → 돋보기 →
렌즈 속 심해로 빨려 들어감 → 컴컴한 심해 정지. 이 영상은 모든 편 공용이고, 여기서 **그 편 생물 이름만 바꿔** 입힌다.
- 심해 정지 구간을 나레이션 길이만큼 천천히 늘린다(떠다니는 입자만 있는 장면이라 늘려도 티가 안 난다).
- 글씨는 화면 가운데, 줄마다 왼쪽→오른쪽으로 써진다(AI가 쓴 글씨 금지 — 뭉개짐).
  배경이 어두운 심해라 **밝은 종이색 글자 + 어두운 테두리**. 뒤 흐림 없음. 번호(No.) 없음.
- 소리: 영상의 효과음(두루마리·물소리)은 작게 깔고 심해 구간에서 줄인다 + 나레이션(-16 LUFS). **음악 없음.**

사용: python ending_overlay.py <확정엔딩.mp4> <생물 일본어 이름> <나레이션.wav> <출력.mp4>
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[2] / "vendor" / "fonts" / "YujiSyuku-Regular.ttf"
W, H, FPS = 720, 1280, 24
INK = (242, 230, 204)                   # 밝은 종이색 글자
STROKE_C = (8, 18, 30)                  # 어두운 남색 테두리
STROKE = 4
MAX_W = W - 120

SETTLE_S = 5.6                          # 이 시점부터 심해 정지 구간(글씨 시작)
NAR_T0 = 7.4                            # 나레이션 시작(질문 줄이 써지기 시작할 때)
MIN_TOTAL_S = 11.5

# (문구, 글자 크기, SETTLE_S 기준 시작 초, 끝 초) — {name} 자리에 그 편 생물 이름
LINES = [
    ("深海図鑑", 54, 0.0, 0.6),
    ("{name}", 64, 0.7, 1.6),
    ("あなたが見てみたい", 46, 1.9, 2.6),
    ("深海の生き物は？", 46, 2.6, 3.3),
    ("コメントで教えてください", 42, 3.5, 4.3),
]
GAP = [0, 6, 22, 2, 14]                 # 줄 앞 간격(px)


def _dur(p: Path | str) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(p)], capture_output=True, text=True, check=True).stdout.strip())


def _fit(text: str, size: int) -> ImageFont.FreeTypeFont:
    while size > 20:
        f = ImageFont.truetype(str(FONT), size)
        if f.getlength(text) + 2 * STROKE <= MAX_W:
            return f
        size -= 2
    return ImageFont.truetype(str(FONT), size)


def layout(name: str):
    rows, y = [], 0
    for (txt, size, t0, t1), gap in zip(LINES, GAP):
        txt = txt.format(name=name)
        f = _fit(txt, size)
        a, d = f.getmetrics()
        y += gap
        rows.append({"text": txt, "font": f, "y": y, "t0": SETTLE_S + t0, "t1": SETTLE_S + t1})
        y += a + d
    top = int(H * 0.5 - y / 2)                  # 화면 가운데 정렬
    for r in rows:
        r["y"] += top
    return rows


def render_frames(name: str, dur: float, out_dir: Path) -> None:
    rows = layout(name)
    ink = []
    for r in rows:
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        tw = r["font"].getlength(r["text"])
        x = int((W - tw) / 2)
        ImageDraw.Draw(im).text((x, r["y"]), r["text"], font=r["font"], fill=INK + (255,),
                                stroke_width=STROKE, stroke_fill=STROKE_C + (255,))
        ink.append((im, x, int(tw)))
    for i in range(int(round(dur * FPS))):
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


def main(src: str, name: str, narration: str, dst: str) -> None:
    src_d, nar_d = _dur(src), _dur(narration)
    total = max(MIN_TOTAL_S, NAR_T0 + nar_d + 1.0)
    k = (total - SETTLE_S) / (src_d - SETTLE_S)          # 심해 구간 늘림 배율
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        # ① 영상: 앞부분 그대로 + 심해 구간을 k배 천천히(프레임 보간)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", src, "-filter_complex",
            f"[0:v]scale={W}:{H},setsar=1,fps={FPS},split[a][b];"
            f"[a]trim=0:{SETTLE_S},setpts=PTS-STARTPTS[v1];"
            f"[b]trim={SETTLE_S},setpts=(PTS-STARTPTS)*{k:.4f},minterpolate=fps={FPS}:mi_mode=blend[v2];"
            f"[v1][v2]concat=n=2:v=1:a=0,trim=0:{total:.3f}[v]",
            "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(t / "base.mp4")],
            check=True)
        # ② 손글씨 프레임
        render_frames(name, total, t)
        # ③ 합성: 효과음(작게, 심해 구간에서 줄임) + 나레이션(-16 LUFS, NAR_T0부터)
        ms = int(NAR_T0 * 1000)
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(t / "base.mp4"), "-framerate", str(FPS),
            "-i", str(t / "o%04d.png"), "-i", src, "-i", narration, "-filter_complex",
            "[0:v][1:v]overlay=0:0:shortest=1[v];"
            f"[2:a]volume=0.5,afade=t=out:st={SETTLE_S}:d=1.5,apad,atrim=0:{total:.3f}[sfx];"
            f"[3:a]aresample=48000,adelay={ms}|{ms},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad,atrim=0:{total:.3f}[nar];"
            "[sfx]aresample=48000[sfx2];[sfx2][nar]amix=inputs=2:normalize=0[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", dst], check=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
