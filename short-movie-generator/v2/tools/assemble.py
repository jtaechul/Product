"""v2 완성본 조립 — 본편 컷 + 나레이션 + 카라오케 자막 + 빨간 주석 + 「再現映像」 + 특징 줌인 인서트 + 공용 엔딩.

규칙(CLAUDE.md v2): 영상은 정상 속도(컷 길이 = 나레이션 + 여유, 짝수 초) · 영상 AI 오디오는 전부 버림(음악 금지) ·
나레이션 -16 LUFS · 자막은 v1과 같은 카라오케식 하단(karaoke.py) · 주석은 강조색 빨강 하나 · 「再現映像」 표기.

사용: python assemble.py <pilot 폴더> <클립 요청 id> <나레이션 요청 id> <엔딩 mp4> <출력 mp4>
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import karaoke  # noqa: E402

W, H, FPS = 720, 1280, 24
ROOT = Path(__file__).resolve().parents[2]
FONT_BOLD = ROOT / "vendor" / "fonts" / "NotoSansJP-VF.ttf"
RED = (220, 38, 38)
EDGE = 12                      # 좌우 가장자리 여유 크롭(px)

# 특징 줌인 인서트: 컷 번호 → (인서트 이미지, 시작 초, 빨간 원 중심 x,y(0~1), 반지름(0~1))
INSERTS = {4: ("out/19_eye_macro/eye_macro.jpg", 5.0, (0.40, 0.50), 0.36)}


def _run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _dur(p) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 str(p)], capture_output=True, text=True, check=True).stdout.strip())


def _font(size: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_BOLD), size)
    f.set_variation_by_name("Bold")
    return f


def label_png(text: str, out: Path) -> Path:
    """빨간 주석(위쪽 1/3 — 하단 자막과 겹치지 않게): 흰 글씨 + 빨간 칩."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = _font(40)
    tw = f.getlength(text)
    a, d = f.getmetrics()
    x0, y0 = int((W - tw) / 2) - 20, int(H * 0.30)
    dr = ImageDraw.Draw(im)
    dr.rounded_rectangle([x0, y0, x0 + tw + 40, y0 + a + d + 20], radius=12, fill=RED + (235,))
    dr.text((x0 + 20, y0 + 10), text, font=f, fill=(255, 255, 255, 255))
    im.save(out)
    return out


def repro_png(out: Path) -> Path:
    """「再現映像」 — 왼쪽 위 작게(실사로 오인하지 않게 · 운영자 확정)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    f = _font(24)
    ImageDraw.Draw(im).text((26, 26), "再現映像", font=f, fill=(255, 255, 255, 190),
                            stroke_width=2, stroke_fill=(0, 0, 0, 150))
    im.save(out)
    return out


def circle_png(cx: float, cy: float, r: float, out: Path) -> Path:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    R = int(r * W)
    ImageDraw.Draw(im).ellipse([int(cx * W) - R, int(cy * H) - R, int(cx * W) + R, int(cy * H) + R],
                               outline=RED + (255,), width=8)
    im.save(out)
    return out


def _place_slices(src: Path, slices: list[tuple], total: float, out: Path) -> None:
    """src(모노 wav)에서 (from, to) 구간을 잘라 at 초에 놓은 total 초짜리 스테레오 wav."""
    import wave

    import numpy as np
    with wave.open(str(src), "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).reshape(-1, ch)[:, 0]
    outbuf = np.zeros(int(total * sr), dtype=np.int32)
    for a, b, at in slices:
        seg = data[int(a * sr):int(b * sr)].astype(np.int32)
        o = int(at * sr)
        seg = seg[:max(0, len(outbuf) - o)]
        outbuf[o:o + len(seg)] += seg
    outbuf = np.clip(outbuf, -32768, 32767).astype(np.int16)
    stereo = np.repeat(outbuf[:, None], 2, axis=1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def build_cut(pilot: Path, clip: Path, sec: float, n: int, ann: str | None, t: Path) -> Path:
    """한 컷: 9:16 맞춤 · 무음 · 길이 맞춤(짧으면 마지막 장면 유지) · 인서트·주석."""
    base = t / f"cut{n}_base.mp4"
    # ★좌우 가장자리 12px씩 여유 크롭(약 3% 확대) — 시작 이미지의 흰 격자 테두리가 영상 첫머리에
    #   흰 선으로 남는 사고 방지(실측 최대 9px). 모든 컷에 같게 적용해 컷끼리 크기 차이가 없다.
    _run(["-i", str(clip), "-vf", f"scale={W + 2 * EDGE}:{(H + 2 * EDGE * H // W) // 2 * 2}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},setsar=1,fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={sec}", "-t", f"{sec}", "-an", "-c:v", "libx264", "-crf", "16",
          "-pix_fmt", "yuv420p", str(base)])
    cur = base
    if n in INSERTS:                                   # 특징 줌인 — 매크로 인서트(천천히 확대) + 빨간 원
        img, at, (cx, cy), r = INSERTS[n]
        ins = t / f"cut{n}_ins.mp4"
        frames = int((sec - at) * FPS)
        _run(["-loop", "1", "-i", str(pilot / img), "-vf",
              f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
              f"zoompan=z='min(zoom+0.0012,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},setsar=1",
              "-frames:v", str(frames), "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(ins)])
        circ = circle_png(cx, cy, r, t / f"cut{n}_circ.png")
        joined = t / f"cut{n}_join.mp4"
        _run(["-i", str(cur), "-i", str(ins), "-i", str(circ), "-filter_complex",
              f"[0:v]trim=0:{at},setpts=PTS-STARTPTS[a];[1:v][2:v]overlay=0:0:enable='gte(t,0.4)'[b];"
              "[a][b]concat=n=2:v=1:a=0[v]", "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p",
              str(joined)])
        cur = joined
    if ann:
        lab = label_png(ann, t / f"cut{n}_lab.png")
        out = t / f"cut{n}_ann.mp4"
        _run(["-i", str(cur), "-i", str(lab), "-filter_complex", "[0:v][1:v]overlay=0:0:enable='gte(t,0.6)'[v]",
              "-map", "[v]", "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(out)])
        cur = out
    return cur


def main(pilot: str, clips_id: str, tts_id: str, ending: str, dst: str, overrides: dict | None = None) -> None:
    """overrides: {컷번호: 클립 경로} — 관리자 페이지에서 그 컷만 다시 만든 경우 새 클립을 쓴다."""
    P = Path(pilot)
    sc = json.loads((P / "script.json").read_text(encoding="utf-8"))
    cuts = {c["cut"]: c for c in sc["cuts"] if "tts" in c}
    timing = sc["timing_v5"]
    wav = P / "out" / tts_id / "body.wav"
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        # ① 컷별 영상
        parts, starts, acc = [], [], 0.0
        for tm in timing:
            n, sec = tm["cut"], float(tm["sec"])
            clip = Path((overrides or {}).get(n) or P / "out" / clips_id / f"c{n:02d}.mp4")
            parts.append(build_cut(P, clip, sec, n, cuts[n].get("annotation"), t))
            starts.append(acc)
            acc += sec
        body_len = acc
        (t / "list.txt").write_text("".join(f"file '{p}'\n" for p in parts))
        _run(["-f", "concat", "-safe", "0", "-i", str(t / "list.txt"), "-c", "copy", str(t / "body_v.mp4")])
        # ② 나레이션: 전체를 한 번에 음량 맞춤(-16 LUFS) → 컷별로 잘라 컷 시작 + 리드에 배치
        _run(["-i", str(wav), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-ac", "1",
              "-sample_fmt", "s16", str(t / "nar_norm.wav")])
        # ★조각 배치는 파이썬으로 샘플 단위로 정확히 놓는다 — ffmpeg atrim+adelay 조합은 지연이 무시돼 조각이
        #   맨 앞에 겹쳐 깔렸다(실측: 두 조각이 0초에 겹쳐 -8 LUFS로 과대).
        _place_slices(t / "nar_norm.wav", [(tm["audio_from"], tm["audio_to"], st + tm["lead"])
                                           for tm, st in zip(timing, starts)], body_len, t / "body_a0.wav")
        _run(["-i", str(t / "body_a0.wav"), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000",
              "-t", f"{body_len}", str(t / "body_a.wav")])          # 스테레오 기준 -16 LUFS(엔딩과 같게)
        # ③ 카라오케 자막(v1 방식) — 컷별 발화 조각 시각 + 컷 시작
        disp = []
        for tm, st in zip(timing, starts):
            disp += karaoke.disp_from_timepoints(cuts[tm["cut"]]["jp"], tm["local_tps"], offset=st)
        karaoke.build_ass(disp, t / "body.ass")
        rep = repro_png(t / "repro.png")
        _run(["-i", str(t / "body_v.mp4"), "-i", str(rep), "-i", str(t / "body_a.wav"), "-filter_complex",
              f"[0:v][1:v]overlay=0:0,{karaoke.burn_filter(t / 'body.ass')}[v]", "-map", "[v]", "-map", "2:a",
              "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
              "-t", f"{body_len}", str(t / "body.mp4")])
        # ④ 공용 엔딩 연결(같은 규격으로 맞춘 뒤 이어 붙임)
        _run(["-i", ending, "-vf", f"scale={W}:{H},setsar=1,fps={FPS}",
              "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000", "-c:v", "libx264", "-crf", "18",
              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", str(t / "end.mp4")])
        _run(["-i", str(t / "body.mp4"), "-i", str(t / "end.mp4"), "-filter_complex",
              "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
              "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", dst])


if __name__ == "__main__":
    main(*sys.argv[1:6])
