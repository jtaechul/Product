"""제품 영상 '특징 구간' 자동 탐지 (2026-07-17 사용자 확정 — 영상 앞부분만 쓰이던 문제 해결).

장면 전환(프레임 급변)을 찾아 영상을 구간으로 나누고 대표 구간 최대 max_n개를 돌려준다.
제품 홍보 영상은 보통 기능마다 컷이 나뉘어 있어, 컷 경계가 곧 '특징 구간' 경계다.
결정론적(같은 영상 → 같은 구간) — 후보에서 고른 pv_start/pv_end가 제작 때 그대로 재현된다.
"""

from __future__ import annotations

from pathlib import Path


def detect_segments(path, max_n: int = 4, min_len: float = 2.5, probe_fps: float = 2.0) -> list:
    """반환 [(start_sec, end_sec)...] — 장면 경계 기준 구간(각 최대 8초, 최소 min_len)."""
    from moviepy import VideoFileClip
    try:
        clip = VideoFileClip(str(path))
        dur = float(clip.duration or 0)
        if dur <= 0:
            clip.close()
            return [(0.0, 8.0)]
        if dur <= min_len * 2:
            clip.close()
            return [(0.0, round(dur, 2))]
        prev, diffs, t = None, [], 0.0
        while t < dur - 0.2:
            fr = clip.get_frame(t)
            small = fr[::8, ::8].astype("float32")
            if prev is not None and small.shape == prev.shape:
                diffs.append((t, float(abs(small - prev).mean())))
            prev = small
            t += 1.0 / probe_fps
        clip.close()
    except Exception as e:
        print(f"[vseg] 구간 탐지 실패({Path(path).name}: {e}) — 앞 8초 1구간")
        return [(0.0, 8.0)]
    if not diffs:
        return [(0.0, round(dur, 2))]
    vals = sorted(d for _, d in diffs)
    mean = sum(vals) / len(vals)
    thr = max(vals[int(len(vals) * 0.9)], mean * 2.2)   # 상위 10% 급변 또는 평균의 2.2배 → 장면 전환
    bounds = [0.0]
    for tt, d in diffs:
        if d >= thr and tt - bounds[-1] >= min_len:
            bounds.append(round(tt, 2))
    if dur - bounds[-1] >= min_len:
        bounds.append(round(dur, 2))
    else:
        bounds[-1] = round(dur, 2)
    segs = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    if len(segs) > max_n:   # 앞·중·뒤 고르게 대표 구간 선발
        idxs = sorted({round(i * (len(segs) - 1) / (max_n - 1)) for i in range(max_n)})
        segs = [segs[i] for i in idxs]
    return [(round(s, 2), round(min(e, s + 8.0), 2)) for s, e in segs]   # 라인 배경용 — 구간 최대 8초
