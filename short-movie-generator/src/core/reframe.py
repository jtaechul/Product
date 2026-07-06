"""reframe — 실사 심해 영상(가로)을 9:16 세로로 재편집.

핵심: 피사체(밝은/붉은 심해 생물)의 무게중심을 추적해 크롭 창을 옮기고, 세그먼트별로
와이드↔접사를 교차(줌컷)해 지루하지 않게. 다크틸 시네마틱 그레이딩 적용.
목표 길이(=본문 나레이션 길이)에 맞춰 필요하면 영상을 루프한다.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)
W, H = 720, 1280  # 9:16


def _probe(path: str, entry: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", f"stream={entry}", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip().split(",")[0])
    except Exception:  # noqa: BLE001
        return 0.0


def _duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def _subject_centroid(frame_path: str) -> tuple[float, float]:
    """붉은 심해 생물 강조(r-g 가중) 무게중심(0~1). 실패 시 중앙."""
    try:
        from PIL import Image
        im = Image.open(frame_path).convert("RGB")
        w, h = im.size
        im = im.resize((w // 4, h // 4))
        w, h = im.size
        px = im.load()
        sx = sy = sw = 0.0
        for y in range(h):
            for x in range(w):
                r, g, b = px[x, y]
                wt = r - g
                if wt > 25:
                    sx += x * wt; sy += y * wt; sw += wt
        if sw <= 0:
            return 0.5, 0.5
        return sx / sw / (w - 1), sy / sw / (h - 1)
    except Exception:  # noqa: BLE001
        return 0.5, 0.5


def _median(vals: list[float]) -> float:
    v = sorted(vals)
    return v[len(v) // 2] if v else 0.5


# 세그먼트 줌 패턴(와이드→접사→와이드… 교차)
_ZOOM_CYCLE = [1.00, 1.35, 1.10, 1.55, 1.15, 1.40]


def reframe_to_vertical(footage_path: str, out_path: str, target_dur: float,
                        work_dir: str) -> str:
    """가로 실사 영상 → 9:16 세로(피사체 추적 줌컷 + 틸 그레이딩), 길이 target_dur."""
    wd = Path(work_dir); wd.mkdir(parents=True, exist_ok=True)
    src_dur = _duration(footage_path) or target_dur
    src_w = _probe(footage_path, "width") or 1920
    src_h = _probe(footage_path, "height") or 1080

    # 목표 길이만큼 쓸 소스 창(부족하면 루프 입력 준비)
    use = min(src_dur, target_dur) if src_dur >= target_dur else src_dur
    loop = src_dur < target_dur - 0.1

    # 추적용 프레임 추출(5fps) — 루프 없이 원본에서
    fr_dir = wd / "trk"; fr_dir.mkdir(exist_ok=True)
    for f in fr_dir.glob("f_*.jpg"):
        f.unlink()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", footage_path,
                    "-vf", "fps=5,scale=480:-1", str(fr_dir / "f_%04d.jpg")], check=True)
    frames = sorted(fr_dir.glob("f_*.jpg"))
    cents = [_subject_centroid(str(f)) for f in frames] or [(0.5, 0.5)]
    fps_trk = 5.0

    # 세그먼트 분할(≈5초/컷)
    n_seg = max(2, min(8, round(target_dur / 5.0)))
    seg_len = target_dur / n_seg
    concat = wd / "reframe_concat.txt"
    lines = []
    for i in range(n_seg):
        a, b = i * seg_len, (i + 1) * seg_len
        z = _ZOOM_CYCLE[i % len(_ZOOM_CYCLE)]
        # 소스 시간(루프 고려): a를 소스 길이로 모듈로
        sa = a % use if use > 0 else 0.0
        fa, fb = int((sa) * fps_trk), int((sa + seg_len) * fps_trk)
        seg_c = cents[fa:fb] or cents
        fx = _median([c[0] for c in seg_c])
        fy = _median([c[1] for c in seg_c])
        cw = int(round((src_h * W / H) / z)) & ~1
        ch = int(round(src_h / z)) & ~1
        cw = min(cw, int(src_w)) & ~1
        cx = int(min(max(fx * src_w - cw / 2, 0), src_w - cw))
        cy = int(min(max(fy * src_h - ch / 2, 0), src_h - ch))
        seg_out = wd / f"rf_{i}.mp4"
        vf = (f"crop={cw}:{ch}:{cx}:{cy},scale={W}:{H},setsar=1,"
              f"eq=contrast=1.12:saturation=1.16:brightness=-0.05,"
              f"colorbalance=rm=-0.03:bm=0.05,vignette=PI/4.2,format=yuv420p")
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if loop:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-ss", f"{sa:.2f}", "-t", f"{seg_len:.2f}", "-i", footage_path,
                "-vf", vf, "-an", "-r", "30", "-c:v", "libx264", "-preset", "medium",
                "-crf", "20", str(seg_out)]
        subprocess.run(cmd, check=True)
        lines.append(f"file '{seg_out.name}'")
    concat.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-c", "copy", out_path], check=True)
    log.info("[reframe] 9:16 완성: %s (%d컷, %.1fs)", out_path, n_seg, target_dur)
    return out_path
