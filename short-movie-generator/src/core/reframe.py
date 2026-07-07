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
    """실제 길이 = duration − start_time. 일부 NOAA/Commons webm은 타임스탬프가 0에서
    시작하지 않아 duration이 '끝 타임스탬프'로 읽힌다(수 시간대 오판 → 구간 계산 파괴)."""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=start_time,duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        import json as _json
        fmt = _json.loads(r.stdout or "{}").get("format", {})
        dur = float(fmt.get("duration") or 0)
        start = float(fmt.get("start_time") or 0)
        return max(0.0, dur - max(0.0, start))
    except Exception:  # noqa: BLE001
        return 0.0


def _red_pixels(frame_path: str) -> tuple[list, int, int]:
    """프레임의 적색 신호 픽셀 [(가중치, x, y)]와 축소 해상도(w,h).
    붉은 심해 생물(r-g)이 강조되는 픽셀만 수집."""
    from PIL import Image
    im = Image.open(frame_path).convert("RGB")
    w, h = im.size
    im = im.resize((max(2, w // 4), max(2, h // 4)))
    w, h = im.size
    px = im.load()
    pts = []
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            wt = r - g
            if wt > 25:
                pts.append((wt, x, y))
    return pts, w, h


def _subject_centroid(frame_path: str) -> tuple[float, float]:
    """붉은 심해 생물의 무게중심(0~1). 실패 시 중앙.

    핵심(재발 방지): 프레임 '전체' 적색 픽셀 평균을 쓰면 해저 퇴적물의 옅은 붉은 기가
    센트로이드를 오염시켜 크롭이 피사체와 노이즈 '사이'를 겨냥한다(피사체가 화면 가장자리로
    밀리던 실제 결함). → **가장 강한 적색 상위 픽셀(상위 ~2%)만**으로 계산해
    가장 선명한 붉은 덩어리(=생물 본체)에 크롭을 고정한다.
    """
    try:
        pts, w, h = _red_pixels(frame_path)
        if not pts:
            return 0.5, 0.5
        pts.sort(key=lambda p: p[0], reverse=True)
        core = pts[:max(12, len(pts) // 50)]   # 상위 2%(최소 12픽셀) = 피사체 코어
        sw = sum(p[0] for p in core)
        sx = sum(p[1] * p[0] for p in core)
        sy = sum(p[2] * p[0] for p in core)
        return sx / sw / max(1, w - 1), sy / sw / max(1, h - 1)
    except Exception:  # noqa: BLE001
        return 0.5, 0.5


def subject_score(frame_path: str) -> float:
    """'피사체 전신이 온전히 보이는' 프레임 점수 — 엔드카드 배경 프레임 선택용.

    단순 적색량 최대는 ROV 초근접 컷(생물이 화면을 가득 채워 식별 불가)을 고르는
    실제 결함이 있었다. 규칙:
    ① 적색 신호가 있어야 하고(존재) ② 점유율이 과하면 감점(가득 채움=근접 과다)
    ③ 적색 덩어리가 프레임 경계에 닿으면 감점(전신이 잘림).
    """
    try:
        pts, w, h = _red_pixels(frame_path)
        if not pts:
            return 0.0
        pts.sort(key=lambda p: p[0], reverse=True)
        strength = float(sum(p[0] for p in pts[:max(12, len(pts) // 50)]))
        frac = len(pts) / max(1, w * h)          # 화면 점유율
        if frac <= 0.35:
            fit = 1.0
        elif frac >= 0.75:                        # 화면을 거의 가득 채움 → 식별 불가 근접컷
            fit = 0.05
        else:
            fit = 1.0 - (frac - 0.35) / 0.40 * 0.95
        xs = [p[1] for p in pts]; ys = [p[2] for p in pts]
        edges = sum([min(xs) <= 1, max(xs) >= w - 2, min(ys) <= 1, max(ys) >= h - 2])
        return strength * fit * (0.55 ** edges)   # 경계에 잘릴수록 감점
    except Exception:  # noqa: BLE001
        return 0.0


def _median(vals: list[float]) -> float:
    v = sorted(vals)
    return v[len(v) // 2] if v else 0.5


def _subject_frac(frame_path: str) -> float:
    """적색 피사체의 화면 점유율(0~1) — 줌 상한 계산용."""
    try:
        pts, w, h = _red_pixels(frame_path)
        return len(pts) / max(1, w * h)
    except Exception:  # noqa: BLE001
        return 0.0


def _pick_windows(scores: list[float], fps_trk: float, seg_len: float, n_seg: int) -> list[float]:
    """피사체 점수(subject_score) 기준 '가장 잘 보이는' 소스 구간 n_seg개 시작초 선택.

    왜(실제 결함): 소스의 앞부분을 무조건 쓰면 피사체가 없거나 ROV 초근접인 구간이
    그대로 들어가 생물을 식별할 수 없었다. 점수 상위·비중첩 구간을 골라 시간순 배치.
    """
    win = max(1, int(seg_len * fps_trk))
    n = len(scores)
    if n <= win:
        return [0.0] * n_seg
    pre = [0.0]
    for s in scores:
        pre.append(pre[-1] + s)
    step = max(1, int(0.5 * fps_trk))
    cand = sorted(((pre[st + win] - pre[st], st) for st in range(0, n - win, step)), reverse=True)
    chosen: list[int] = []
    for _sc, st in cand:
        if all(abs(st - o) >= win for o in chosen):
            chosen.append(st)
        if len(chosen) == n_seg:
            break
    while len(chosen) < n_seg:                      # 소스가 짧으면 겹침 허용해 채움
        chosen.append(chosen[len(chosen) % max(1, len(chosen))] if chosen else 0)
    chosen.sort()
    return [st / fps_trk for st in chosen]


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
    fracs = [_subject_frac(str(f)) for f in frames] or [0.0]
    scores = [subject_score(str(f)) for f in frames] or [0.0]
    fps_trk = 5.0

    # 세그먼트 분할(≈5초/컷)
    n_seg = max(2, min(8, round(target_dur / 5.0)))
    seg_len = target_dur / n_seg
    # 피사체가 가장 잘 보이는 소스 구간 선택(앞부분 무조건 사용 → 근접·부재 구간 유입 차단)
    starts = _pick_windows(scores, fps_trk, seg_len, n_seg) if not loop else None
    concat = wd / "reframe_concat.txt"
    lines = []
    import math as _m
    for i in range(n_seg):
        a = i * seg_len
        z = _ZOOM_CYCLE[i % len(_ZOOM_CYCLE)]
        sa = starts[i] if starts else (a % use if use > 0 else 0.0)
        fa, fb = int((sa) * fps_trk), int((sa + seg_len) * fps_trk)
        seg_c = cents[fa:fb] or cents
        fx = _median([c[0] for c in seg_c])
        fy = _median([c[1] for c in seg_c])
        # 줌 상한: 화면 점유율이 60%를 넘지 않게(이미 근접인 소스에 추가 줌 → 식별 불가 차단)
        med_frac = _median((fracs[fa:fb] or fracs))
        z_cap = _m.sqrt(0.6 * src_h * W / (max(med_frac, 1e-4) * src_w * H))
        z = max(1.0, min(z, z_cap))
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
