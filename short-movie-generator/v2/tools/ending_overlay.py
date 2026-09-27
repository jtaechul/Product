"""공용 엔딩 편집 — 확정 영상 위에 손글씨·나레이션을 입힌다 (운영자 확정 2026-09-27).

확정 영상(`_shared/approved/ending_omni_v2_trim.mp4`, Omni Flash): 말린 두루마리가 펼쳐짐 → 돋보기 →
렌즈 속 심해로 빨려 들어감 → 컴컴한 심해 정지. 이 영상은 모든 편 공용이고, 편마다 같은 글씨·나레이션을 입힌다(생물 이름 줄은 없음 — 운영자 확정).
- 심해 정지 구간을 나레이션 길이만큼 천천히 늘린다(떠다니는 입자만 있는 장면이라 늘려도 티가 안 난다).
- 글씨는 화면 가운데, 줄마다 왼쪽→오른쪽으로 써진다(AI가 쓴 글씨 금지 — 뭉개짐).
  배경이 어두운 심해라 **밝은 종이색 글자 + 어두운 테두리**. 뒤 흐림 없음. 번호(No.) 없음.
- 첫머리(약 0.4초~): 편별 마무리 멘트 나레이션 + **본편과 같은 하단 자막**(karaoke — v1과 같은 카라오케식).
- 소리: 영상의 효과음(두루마리·물소리)은 작게 깔고 심해 구간에서 줄인다 + 나레이션(-16 LUFS). **음악 없음.**

사용: python ending_overlay.py <확정엔딩.mp4> <출력.mp4> --cta-wav 질문.wav [--cta-tp 조각시각.json]
      [--recap-wav 마무리멘트.wav --recap-text 「今回探った深海の生き物は、〇〇でした。」]
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))   # karaoke

FONT = Path(__file__).resolve().parents[2] / "vendor" / "fonts" / "YujiSyuku-Regular.ttf"
W, H, FPS = 720, 1280, 24
INK = (242, 230, 204)                   # 밝은 종이색 글자
STROKE_C = (8, 18, 30)                  # 어두운 남색 테두리
STROKE = 4
MAX_W = W - 120

SETTLE_S = 5.6                          # 이 시점부터 심해 정지 구간(글씨 시작)
NAR_T0 = 6.0                            # 나레이션 시작(심해에 들어가 정지하자마자 — 엔딩 길이 단축)
MIN_TOTAL_S = 9.5

# (문구, 글자 크기, SETTLE_S 기준 시작 초, 끝 초, 나레이션 조각 번호) — {name} 자리에 그 편 생물 이름
# ★조각 번호가 있는 줄은 고정 초가 아니라 **그 조각을 실제로 읽기 시작하는 시각**에 써진다(운영자 확정:
#   자막과 말이 어긋나면 안 됨). 시각은 합성 때 받은 timepoints(<mark>)에서 온다. 없으면 고정 초로 폴백.
LINES = [
    ("あなたが見てみたい", 50, 0.5, 1.2, 0),
    ("深海の生き物は？", 50, 1.2, 1.9, 1),
    ("コメントで教えてください", 44, 2.2, 3.0, 2),
]
# ★'深海図鑑'·생물 이름 줄 삭제(운영자 확정 2026-09-27 — 이름은 본편에서 이미 말함 · 질문이 더 잘 보이게)
GAP = [0, 4, 18]                 # 줄 앞 간격(px)


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


def layout(name: str, tps: list | None = None):
    rows, y = [], 0
    for (txt, size, t0, t1, seg), gap in zip(LINES, GAP):
        txt = txt.format(name=name)
        f = _fit(txt, size)
        a, d = f.getmetrics()
        y += gap
        a0, a1 = SETTLE_S + t0, SETTLE_S + t1
        if seg is not None and tps and seg < len(tps) and tps[seg].get("start") is not None:
            st = NAR_T0 + tps[seg]["start"]
            en = NAR_T0 + (tps[seg].get("end") or tps[seg]["start"] + 1.0)
            a0, a1 = st, st + max(0.35, min(1.2, 0.8 * (en - st)))   # 말하는 동안 다 써지게
        rows.append({"text": txt, "font": f, "y": y, "t0": a0, "t1": a1})
        y += a + d
    top = int(H * 0.5 - y / 2)                  # 화면 가운데 정렬
    for r in rows:
        r["y"] += top
    return rows


def render_frames(name: str, dur: float, out_dir: Path, tps: list | None = None) -> None:
    rows = layout(name, tps)
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


RECAP_T0 = 0.4                          # 편별 마무리 멘트 시작(양피지가 펼쳐지기 시작할 때)


def main(src: str, dst: str, cta_wav: str, cta_tp: str | None = None,
         recap_wav: str | None = None, recap_text: str | None = None, recap_tp: str | None = None) -> None:
    import json
    import karaoke
    tps = json.loads(Path(cta_tp).read_text(encoding="utf-8")) if cta_tp else None
    src_d, nar_d = _dur(src), _dur(cta_wav)
    recap = None
    if recap_wav and recap_text:
        rd = _dur(recap_wav)
        if RECAP_T0 + rd > NAR_T0 - 0.3:
            raise SystemExit(f"마무리 멘트가 너무 깁니다({rd:.1f}초) — 질문 나레이션과 겹칩니다")
        rtps = json.loads(Path(recap_tp).read_text(encoding="utf-8"))
        recap = karaoke.disp_from_timepoints(recap_text, rtps, offset=RECAP_T0)   # ★v1과 같은 카라오케 조각
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
        # ② 손글씨 + 하단 멘트 자막 프레임
        render_frames("", total, t, tps)
        vf = "[0:v][1:v]overlay=0:0:shortest=1[v];"
        if recap:                                   # 하단 카라오케 자막(본편과 같은 v1 방식)
            karaoke.build_ass(recap, t / "recap.ass")
            vf = f"[0:v][1:v]overlay=0:0:shortest=1,{karaoke.burn_filter(t / 'recap.ass')}[v];"
        # ③ 합성: 효과음(작게) + 질문 나레이션 + (있으면) 마무리 멘트. ★지연(adelay)은 음량 맞춤(loudnorm) **앞**에
        #    (loudnorm 뒤에 두면 지연이 무시돼 영상 맨 앞에 깔린다 — 실측 사고)
        ms = int(NAR_T0 * 1000)
        inputs = ["-i", str(t / "base.mp4"), "-framerate", str(FPS), "-i", str(t / "o%04d.png"), "-i", src, "-i", cta_wav]
        fc = (vf +
              f"[2:a]volume=0.5,afade=t=out:st={SETTLE_S}:d=1.5,apad,atrim=0:{total:.3f},aresample=48000[sfx];"
              f"[3:a]aresample=48000,adelay={ms}|{ms},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,apad,atrim=0:{total:.3f}[nar];")
        mix = "[sfx][nar]"
        n = 2
        if recap:
            inputs += ["-i", recap_wav]
            rms = int(RECAP_T0 * 1000)
            fc += (f"[4:a]aresample=48000,adelay={rms}|{rms},loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,"
                   f"apad,atrim=0:{total:.3f}[rec];")
            mix += "[rec]"
            n = 3
        fc += f"{mix}amix=inputs={n}:normalize=0[a]"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "192k", "-t", f"{total:.3f}", dst], check=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--cta-wav", required=True); ap.add_argument("--cta-tp")
    ap.add_argument("--recap-wav"); ap.add_argument("--recap-text"); ap.add_argument("--recap-tp")
    a = ap.parse_args()
    main(a.src, a.dst, a.cta_wav, a.cta_tp, a.recap_wav, a.recap_text, a.recap_tp)
