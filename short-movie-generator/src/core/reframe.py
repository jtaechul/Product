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


def text_score(frame_path: str) -> float:
    """프레임의 '번인 텍스트' 신호(0~1). **밝은 획-에지** 비율로 측정.

    왜(실제 결함 2건): NOAA 영상은 인트로 자막판·타이틀 카드(로고+종 정보)와
    아웃트로 URL에 텍스트가 통째로 박혀 있어, 구간 선택이 이를 컷으로 골라 최종물에 남았다.
    단순 '밝은 픽셀 비율'은 **밝은 모래 바닥**(대왕등각류 소스)에서 값이 치솟아
    텍스트와 구분이 안 됐다(그래서 임계 폭주 → 미검출). → 텍스트는 어두운 배경 위의
    가느다란 '밝은 획'이라 **국소 대비가 크다**. 밝으면서(순백 근처) 근처에 훨씬 어두운
    픽셀이 있는 '에지 픽셀'만 센다. 균일하게 밝은 모래는 대비가 낮아 걸러진다.
    """
    try:
        from PIL import Image
        im = Image.open(frame_path).convert("L")   # 밝기만
        w, h = im.size
        px = im.load()
        n = 0; S = 3
        for y in range(0, h - S, 1):
            for x in range(0, w - S, 1):
                v = px[x, y]
                if v < 200:                         # 순백 근처만(텍스트 획)
                    continue
                # 국소 대비: 오른/아래 S픽셀 이웃 중 하나라도 훨씬 어두우면 에지(획 경계)
                if v - px[x + S, y] > 70 or v - px[x, y + S] > 70 or \
                   v - px[x + S, y + S] > 70:
                    n += 1
        return n / max(1, w * h)
    except Exception:  # noqa: BLE001
        return 0.0


def _burned_text_threshold(tscores: list[float]) -> float:
    """번인 텍스트 판정 임계값 — 고정 하한 + 영상 기준선 반영.

    에지 기반 text_score는 깨끗한 심해 프레임에선 ~0.001 이하, 텍스트/타이틀 카드에선
    0.01~0.05로 확실히 갈린다(밝은 모래도 대비가 낮아 낮게 나옴). 절대 하한 0.006으로
    확실한 텍스트만 잡고, 소스가 전반적으로 노이지하면 중앙값 4배까지 올려 오검을 막는다."""
    return max(0.006, _median(tscores) * 4.0)


def _row_text_profile(frame_path: str, bands: int = 40) -> list[float]:
    """프레임을 세로로 bands개 띠로 나눠, 각 띠의 '밝은 획-에지' 밀도(0~1)를 반환.
    text_score와 동일한 획-에지 기준(밝고 국소대비 큰 픽셀)을 띠 단위로 집계."""
    try:
        from PIL import Image
        im = Image.open(frame_path).convert("L")
        w, h = im.size
        px = im.load()
        S = 3
        cnt = [0] * bands
        area = [0] * bands
        for y in range(0, h - S):
            b = min(bands - 1, y * bands // h)
            for x in range(0, w - S):
                area[b] += 1
                v = px[x, y]
                if v < 200:
                    continue
                if v - px[x + S, y] > 70 or v - px[x, y + S] > 70 or v - px[x + S, y + S] > 70:
                    cnt[b] += 1
        return [cnt[i] / max(1, area[i]) for i in range(bands)]
    except Exception:  # noqa: BLE001
        return [0.0] * bands


def detect_text_bands(frame_paths: list[str], bands: int = 40) -> tuple[float, float]:
    """주어진 프레임들에서 '가장자리(위/아래)에 박혀 있는 텍스트 띠'를 찾아 잘라낼
    상/하 비율(top_frac, bottom_frac)을 반환. **컷 단위로 호출**하는 것을 전제로 한다.

    핵심(오검 방지 + 간헐 자막 포착): 자막판·NOAA 로고·하단 정보카드(Site/Depth 등)는
    떠 있는 동안 **같은 행에 고정**돼 있다(피사체 반점은 프레임마다 위치가 바뀜).
    한 컷(≈5초)의 프레임들에 대해 '이 띠가 프레임 대부분에 텍스트로 떠 있나(지속률)'로 판정 →
    그 컷에 카드가 떠 있으면 대부분 프레임에서 검출돼 크롭되고, 없으면 0. **전체 영상 평균이
    아니라 컷 단위**라서, 영상 전체에선 10%만 나오는 하단 카드도 '그 카드가 뜬 컷'에서 확실히
    잡히고, 다른 깨끗한 컷은 과크롭되지 않는다. 가장자리(상·하 각 40%) 띠만 대상 → 중앙 안전.
    과크롭 상한 35%.
    """
    if not frame_paths:
        return (0.0, 0.0)
    profs = [_row_text_profile(p, bands) for p in frame_paths]
    n = len(profs)
    HIT = 0.010          # 띠 텍스트 판정(획-에지 밀도) — 확실한 텍스트만
    PERSIST = 0.55       # 이 프레임집합의 절반 이상에 떠 있어야 '박힌 텍스트'
    persist = [sum(1 for pr in profs if pr[b] >= HIT) / n for b in range(bands)]
    text_band = [p >= PERSIST for p in persist]
    # 가장자리 영역(상·하 각 40%) 안에서 '박힌 텍스트' 띠를 찾으면, 오버레이는 보통
    # 가장자리에서 살짝 안쪽에 여백을 두고 있으므로 **가장자리 ~ 텍스트 안쪽 끝**까지 통째로
    # 크롭한다(텍스트와 가장자리 사이 여백도 함께 제거). 중앙 피사체는 영역 밖이라 안전.
    region = int(bands * 0.40)
    top_hits = [b for b in range(0, region) if text_band[b]]
    bot_hits = [b for b in range(bands - region, bands) if text_band[b]]
    top = (max(top_hits) + 1) if top_hits else 0            # 위 텍스트의 '안쪽 끝'까지
    bot = (bands - min(bot_hits)) if bot_hits else 0        # 아래 텍스트의 '안쪽 끝'까지
    cap = int(bands * 0.35)
    top = min(top, cap); bot = min(bot, cap)
    return (top / bands, bot / bands)


def _subject_frac(frame_path: str) -> float:
    """적색 피사체의 화면 점유율(0~1) — 줌 상한 계산용."""
    try:
        pts, w, h = _red_pixels(frame_path)
        return len(pts) / max(1, w * h)
    except Exception:  # noqa: BLE001
        return 0.0


def _pick_windows(scores: list[float], fps_trk: float, seg_len: float, n_seg: int,
                  bad: list[bool] | None = None) -> list[float]:
    """피사체 점수(subject_score) 기준 '가장 잘 보이는' 소스 구간 n_seg개 시작초 선택.

    왜(실제 결함): 소스의 앞부분을 무조건 쓰면 피사체가 없거나 ROV 초근접인 구간이
    그대로 들어가 생물을 식별할 수 없었다. 점수 상위·비중첩 구간을 골라 시간순 배치.
    bad(번인 텍스트 프레임 마스크)가 오면 **텍스트가 1프레임이라도 포함된 구간을
    우선 배제**한다(전부 배제 불가 시 텍스트가 가장 적은 구간 순).
    """
    win = max(1, int(seg_len * fps_trk))
    n = len(scores)
    if n <= win:
        return [0.0] * n_seg
    pre = [0.0]
    for s in scores:
        pre.append(pre[-1] + s)
    preb = [0]
    for b in (bad or [False] * n):
        preb.append(preb[-1] + (1 if b else 0))
    step = max(1, int(0.5 * fps_trk))
    # (텍스트 프레임 수 오름차순 → 점수 내림차순): 깨끗한 구간이 항상 우선
    cand = sorted(((preb[st + win] - preb[st], -(pre[st + win] - pre[st]), st)
                   for st in range(0, n - win, step)))
    chosen: list[int] = []
    for _bc, _negs, st in cand:
        if all(abs(st - o) >= win for o in chosen):
            chosen.append(st)
        if len(chosen) == n_seg:
            break
    while len(chosen) < n_seg:                      # 소스가 짧으면 겹침 허용해 채움
        chosen.append(chosen[len(chosen) % max(1, len(chosen))] if chosen else 0)
    chosen.sort()
    return [st / fps_trk for st in chosen]


def _pick_wide_window(scores: list[float], fracs: list[float], fps_trk: float,
                      seg_len: float, bad: list[bool] | None = None) -> float:
    """'피사체 전신이 온전히 보이는' 와이드 구간 1개의 시작초.

    왜: 컷 전부가 근접이면 시청자가 생물의 전체 모습을 한 번도 못 본다(실제 불만).
    점유율이 적당한(0.4%~25%) 프레임만 유효 점수로 쳐서 최고 구간을 고른다.
    bad(번인 텍스트 마스크) 구간은 우선 배제. 유효 구간이 없으면 점유율 최소 구간.
    """
    win = max(1, int(seg_len * fps_trk))
    n = len(scores)
    if n <= win:
        return 0.0
    wide = [s if 0.004 <= f <= 0.25 else 0.0 for s, f in zip(scores, fracs)]
    pre_w = [0.0]; pre_f = [0.0]
    for w, f in zip(wide, fracs):
        pre_w.append(pre_w[-1] + w); pre_f.append(pre_f[-1] + f)
    preb = [0]
    for b in (bad or [False] * n):
        preb.append(preb[-1] + (1 if b else 0))
    step = max(1, int(0.5 * fps_trk))
    # 1순위: (텍스트 프레임 수 오름차순 → 와이드 점수 내림차순)
    best_st, best_key = 0, None
    for st in range(0, n - win, step):
        key = (preb[st + win] - preb[st], -(pre_w[st + win] - pre_w[st]))
        if best_key is None or key < best_key:
            best_key, best_st = key, st
    if best_key is not None and best_key[1] < 0:    # 와이드 점수 > 0 인 구간 존재
        return best_st / fps_trk
    # 유효 와이드 없음 → (텍스트 수, 점유율 합) 최소 구간(그나마 가장 넓은 그림)
    best_st, best_key = 0, None
    for st in range(0, n - win, step):
        key = (preb[st + win] - preb[st], pre_f[st + win] - pre_f[st])
        if best_key is None or key < best_key:
            best_key, best_st = key, st
    return best_st / fps_trk


def _logo_avoid(cx: int, cy: int, cw: int, ch: int, fx_abs: float, fy_abs: float,
                src_w: float, src_h: float, box: tuple) -> tuple:
    """좌상단 워터마크 회피(2안 기본 + 3안 보완 판단). 반환 (cx, cy, need_delogo).

    규칙: 크롭이 로고 영역과 겹치면 ① 오른쪽으로 밀기 ② 아래로 밀기 —
    단 **피사체가 크롭 안 8~92% 구간에 남을 때만**(화면 밖 이탈 금지, 정중앙은 양보 가능).
    둘 다 불가하면 need_delogo=True → 그 세그먼트만 delogo 필터로 로고를 메운다(3안).
    """
    lx1 = (box[0] + box[2]) * src_w
    ly1 = (box[1] + box[3]) * src_h
    if cx >= lx1 or cy >= ly1:                      # 이미 안 겹침
        return cx, cy, False
    ncx = int(lx1) + 2                              # ① 오른쪽으로 밀어 회피
    if ncx + cw <= src_w and 0.08 * cw <= fx_abs - ncx <= 0.92 * cw:
        return ncx, cy, False
    ncy = int(ly1) + 2                              # ② 아래로 밀어 회피(줌컷일 때 가능)
    if ncy + ch <= src_h and 0.08 * ch <= fy_abs - ncy <= 0.92 * ch:
        return cx, ncy, False
    return cx, cy, True                             # 회피 불가 → delogo 보완


def delogo_vf(src_w: float, src_h: float, box: tuple) -> str:
    """로고 영역을 주변 픽셀로 메우는 ffmpeg delogo 필터 문자열(3안)."""
    lw = min(int(box[2] * src_w) + 4, int(src_w) - 4)
    lh = min(int(box[3] * src_h) + 4, int(src_h) - 4)
    return f"delogo=x=1:y=1:w={lw}:h={lh}"


# 접사(fill) 컷의 줌 배율 — 과도한 줌인 방지를 위해 완만하게.
# 가로로 넓은 생물(문어·오징어 등)은 좁은 9:16 크롭에서 잘려 정체불명이 되므로 배율을 더 낮춘다
# (예전 1.2~1.24대 → 1.1대). 정체 식별을 최우선.
_ZOOM_CYCLE = [1.05, 1.12, 1.06, 1.14, 1.08, 1.10]
# 와이드 우선(난파선 등 큰 구조물): 접사 컷도 거의 줌 없이.
_WIDE_ZOOM_CYCLE = [1.00, 1.08, 1.00, 1.10, 1.04, 1.06]


def _detect_scene_cuts(path: str, src_dur: float, thr: float = 0.30) -> list[float]:
    """ffmpeg 씬 점수로 '컷이 전환되는 시각(초)' 리스트를 검출.

    왜: 사용자 규칙 — 해양생물 쇼츠는 원본에서 '씬이 전환되는 부분'을 개별 구간으로 나눠
    짧게 자주 전환한다. `select='gt(scene,thr)'`가 프레임 간 급변 지점을 잡아 showinfo로
    그 시각을 stderr에 찍는다. 양끝 0.3초는 잘라 자투리 컷을 배제한다.
    """
    import re
    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path,
                            "-filter:v", f"select='gt(scene,{thr})',showinfo",
                            "-an", "-f", "null", "-"],
                           capture_output=True, text=True)
        ts = []
        for m in re.finditer(r"pts_time:([0-9.]+)", r.stderr or ""):
            t = float(m.group(1))
            if 0.3 < t < src_dur - 0.3:
                ts.append(round(t, 2))
        return sorted(set(ts))
    except Exception:  # noqa: BLE001
        return []


def _build_regions(cuts: list[float], src_dur: float, min_len: float,
                   want_min: int = 3, want_max: int = 6) -> list[tuple[float, float]]:
    """씬 컷 시각 → '분절 구간' 리스트. 너무 짧은 씬은 이웃과 병합, 씬이 부족하면 등분 폴백.

    - 씬이 want_min(기본 3)개 미만이면(연속 촬영 원본 등) 소스를 4등분해 변화를 만든다.
    - 씬이 want_max(기본 6)개 초과면 '가장 긴 구간' 위주로 추려 로테이션 패스가 의미 있게 유지.
    """
    bounds = [0.0] + list(cuts) + [float(src_dur)]
    regions = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1) if bounds[i + 1] > bounds[i]]
    merged: list[list[float]] = []
    for s, e in regions:                            # 짧은 씬은 앞 구간에 흡수
        if merged and (e - s) < min_len:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    regions = [(s, e) for s, e in merged if e - s >= min_len] or [(s, e) for s, e in merged]
    if len(regions) < want_min:                     # 씬 부족 → 등분 폴백(연속 원본 대응)
        n = 4
        regions = [(i * src_dur / n, (i + 1) * src_dur / n) for i in range(n)]
    if len(regions) > want_max:                     # 씬 과다 → 긴 구간 우선 추림
        regions = sorted(regions, key=lambda r: r[1] - r[0], reverse=True)[:want_max]
        regions.sort()
    return regions


def _pick_windows_in_range(scores: list[float], bad: list[bool], fps: float,
                           seg_len: float, rs: float, re: float, count: int) -> list[float]:
    """구간 [rs,re] 안에서 '피사체가 잘 보이는' 비중첩 창 count개의 시작초(시간순).

    같은 씬에서 매 패스마다 다른 순간을 쓰도록(1-1,1-2,1-3이 서로 다른 장면) 점수 상위·비중첩
    창을 고르고, 번인 텍스트 프레임(bad)은 우선 배제한다. 구간이 짧으면 겹침을 허용해 채운다.
    """
    win = max(1, int(seg_len * fps))
    a = max(0, int(rs * fps + 0.5))          # 씬 시작 이후로 올림(경계 침범 방지)
    b = min(len(scores), int(re * fps))
    hi = b - win
    if count <= 0:
        return []
    if hi <= a:                                     # 구간이 한 창보다 짧음 → 시작 반복
        return [max(0.0, rs)] * count
    pre = [0.0]
    for s in scores:
        pre.append(pre[-1] + s)
    preb = [0]
    for bb in bad:
        preb.append(preb[-1] + (1 if bb else 0))
    step = max(1, int(0.4 * fps))
    cand = sorted(((preb[st + win] - preb[st], -(pre[st + win] - pre[st]), st)
                   for st in range(a, hi, step)))
    chosen: list[int] = []
    for _bc, _negs, st in cand:                     # 1순위: 비중첩 최고 창
        if all(abs(st - o) >= win for o in chosen):
            chosen.append(st)
        if len(chosen) == count:
            break
    if len(chosen) < count:                         # 부족하면 겹침 허용해 채움
        for _bc, _negs, st in cand:
            if st not in chosen:
                chosen.append(st)
            if len(chosen) == count:
                break
    chosen = sorted(chosen[:count]) or [a]
    while len(chosen) < count:
        chosen.append(chosen[-1])
    return [st / fps for st in chosen]


def _plan_scene_interleaved(path: str, src_dur: float, scores: list[float],
                            bad: list[bool], fps: float, target_dur: float) -> list[dict]:
    """해양생물 쇼츠용 컷 계획 — 씬 분절 + '라운드로빈 인터리브'로 짧게 자주 전환.

    순서 규칙(사용자 예시): 원본을 N개 씬으로 분절하면 1-1,2-1,3-1,…,N-1,1-2,2-2,… 처럼
    매 컷마다 다음 씬으로 넘기고, 같은 씬은 한 바퀴 뒤에 그 씬의 '다음 순간'을 쓴다.
    각 컷은 ≈2.2초로 짧게(지루함 방지). 컷의 1/3은 접사(줌인·얼굴 중앙), 2/3은 전신 핏.
    """
    cut_len = 2.2
    n_cuts = max(2, round(target_dur / cut_len))
    cut_len = target_dur / n_cuts                   # 합이 정확히 target_dur가 되게 재계산
    if cut_len < 1.8:
        n_cuts = max(2, int(target_dur // 1.8)); cut_len = target_dur / n_cuts
    elif cut_len > 2.8:
        n_cuts = max(2, -(-int(target_dur * 10) // 28)); cut_len = target_dur / n_cuts
    cuts = _detect_scene_cuts(path, src_dur)
    regions = _build_regions(cuts, src_dur, min_len=max(cut_len * 1.3, 2.0))
    N = len(regions)
    uses = [0] * N
    for k in range(n_cuts):
        uses[k % N] += 1
    region_starts = [_pick_windows_in_range(scores, bad, fps, cut_len, rs, re, uses[i])
                     for i, (rs, re) in enumerate(regions)]
    idx = [0] * N
    plan: list[dict] = []
    for k in range(n_cuts):
        ri = k % N
        starts = region_starts[ri] or [regions[ri][0]]
        sa = starts[min(idx[ri], len(starts) - 1)]
        idx[ri] += 1
        plan.append({"start": sa, "len": cut_len,
                     "mode": "closeup" if k % 3 == 2 else "fit"})
    log.info("[reframe] 씬 인터리브: 씬 %d개 → %d컷×%.2fs (컷당 씬 로테이션)", N, n_cuts, cut_len)
    return plan


def reframe_to_vertical(footage_path: str, out_path: str, target_dur: float,
                        work_dir: str, logo_box: tuple | None = None,
                        wide: bool = False) -> str:
    """가로 실사 영상 → 9:16 세로(피사체 추적 줌컷 + 틸 그레이딩), 길이 target_dur.
    logo_box(비율 x,y,w,h)가 오면 워터마크를 프레임 이동으로 회피(2안), 불가 시 delogo(3안).
    wide=True(난파선 등): 줌을 억제해 선체·구조물 전체가 넓게 보이는 원경 프레이밍."""
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

    # ★번인 텍스트 '띠' 제거(재발방지 핵심): NOAA/탐사 오버레이(종명·Site·Depth 등)는
    # 위/아래 가장자리에 '항상 같은 위치'로 박혀 있어, 시간 회피(_pick_windows)로는 못 없앤다
    # (전 구간에 존재 → 깨끗한 구간이 없음). 지속성 기반으로 텍스트 띠를 찾아 소스에서
    # 물리적으로 크롭한 '정제 소스'를 만들고, 이후 모든 컷(핏·접사)은 정제 소스로 렌더한다.
    top_f, bot_f = detect_text_bands([str(f) for f in frames])
    if top_f > 0 or bot_f > 0:
        cy0 = int(round(src_h * top_f)) & ~1
        ch0 = (int(round(src_h * (1 - top_f - bot_f))) & ~1)
        cleaned = wd / "cleaned_src.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", footage_path,
                        "-vf", f"crop={int(src_w) & ~1}:{ch0}:0:{cy0},setsar=1",
                        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                        str(cleaned)], check=True)
        log.info("[reframe] 번인 텍스트 띠 제거: 상 %.0f%% · 하 %.0f%% 크롭 → 정제 소스",
                 top_f * 100, bot_f * 100)
        footage_path = str(cleaned)
        # 워터마크 delogo 좌표(비율)를 크롭된 프레임 기준으로 재계산 —
        # 띠 안에 있던 로고는 이미 잘려 제거(None), 남아 있으면 새 y비율로 보정.
        if logo_box:
            lx, ly, lw, lh = logo_box
            span = 1 - top_f - bot_f
            ny = (ly - top_f) / span
            nh = lh / span
            if ny + nh <= 0.02 or ny >= 0.98:   # 로고가 잘린 띠 안 → 제거됨
                logo_box = None
            else:
                logo_box = (lx, max(0.0, ny), lw, min(nh, 1.0 - max(0.0, ny)))
        src_h = ch0
        # 정제 소스로 추적 프레임 재추출(텍스트가 빠져 피사체 중심이 정확해진다)
        for f in fr_dir.glob("f_*.jpg"):
            f.unlink()
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", footage_path,
                        "-vf", "fps=5,scale=480:-1", str(fr_dir / "f_%04d.jpg")], check=True)
        frames = sorted(fr_dir.glob("f_*.jpg"))
    cents = [_subject_centroid(str(f)) for f in frames] or [(0.5, 0.5)]
    fracs = [_subject_frac(str(f)) for f in frames] or [0.0]
    scores = [subject_score(str(f)) for f in frames] or [0.0]
    # ★번인 텍스트 구간(인트로 자막판·아웃트로 URL 등) 감지 → 컷 선택에서 원천 배제.
    # 감지 프레임 주변 ±1초를 함께 배제(팽창) — 텍스트 페이드 인/아웃 꼬리까지 커버.
    tscores = [text_score(str(f)) for f in frames] or [0.0]
    th = _burned_text_threshold(tscores)
    raw_bad = [t >= th for t in tscores]
    PAD = 5   # ±1초(5fps)
    bad = [any(raw_bad[max(0, i - PAD):i + PAD + 1]) for i in range(len(raw_bad))]
    if any(bad):
        log.info("[reframe] 번인 텍스트 프레임 감지: %d(팽창 %d)/%d (임계 %.4f) → 해당 구간 배제",
                 sum(raw_bad), sum(bad), len(bad), th)
    fps_trk = 5.0

    # ── 컷 계획(plan) 수립 ──
    #  · 해양생물(wide=False): 씬 분절 + 라운드로빈 인터리브로 짧게(≈2.2s) 자주 전환(지루함 방지).
    #  · 난파선(wide=True): 기존 방식 유지 — ≈5s 컷, 피사체 최고 창 선택 + 첫 컷 전신 와이드 보장.
    if wide:
        n_seg = max(2, min(8, round(target_dur / 5.0)))
        seg_len = target_dur / n_seg
        starts = _pick_windows(scores, fps_trk, seg_len, n_seg, bad=bad) if not loop else None
        if starts:
            wide_sa = _pick_wide_window(scores, fracs, fps_trk, seg_len, bad=bad)
            rest = [s for s in starts if abs(s - wide_sa) >= seg_len]
            starts = ([wide_sa] + rest)[:n_seg]
            while len(starts) < n_seg:
                starts.append(rest[len(starts) % len(rest)] if rest else wide_sa)
        plan = [{"start": (starts[i] if starts else (i * seg_len) % (use or target_dur)),
                 "len": seg_len, "mode": "closeup" if i % 3 == 2 else "fit"}
                for i in range(n_seg)]
    else:
        plan = _plan_scene_interleaved(footage_path, src_dur, scores, bad, fps_trk, target_dur)

    concat = wd / "reframe_concat.txt"
    lines = []
    import math as _m
    cycle = _WIDE_ZOOM_CYCLE if wide else _ZOOM_CYCLE
    GRADE = ("eq=contrast=1.12:saturation=1.16:brightness=-0.05,"
             "colorbalance=rm=-0.03:bm=0.05,vignette=PI/4.2,format=yuv420p")
    # ★전신 보장(과도한 줌인 방지): 컷의 2/3를 '핏(fit)'으로 — 원본 전체를 9:16 안에 담아
    #   피사체 전신 + 배경까지 다 보이게 하고, 남는 위/아래는 같은 화면의 블러로 채운다.
    #   나머지 1/3만 완만한 접사(줌인) — 심해생물은 얼굴을 화면 중앙에 두고 크롭.
    n_fit = 0
    for i, cut in enumerate(plan):
        sa = cut["start"]
        seg_len = cut["len"]
        seg_out = wd / f"rf_{i}.mp4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if loop:
            cmd += ["-stream_loop", "-1"]
        cmd += ["-ss", f"{sa:.2f}", "-t", f"{seg_len:.2f}", "-i", footage_path,
                "-an", "-r", "30", "-c:v", "libx264", "-preset", "medium", "-crf", "20"]
        if cut["mode"] != "closeup":
            # 핏 컷: 전신 + 배경 전체가 보이도록 원본 전체를 9:16 안에 맞춤(여백=블러 채움)
            n_fit += 1
            # ★핏 컷 번인 텍스트 방지(재발방지 2차 방어): 핏은 원본 프레임 '전체'를 보여줘
            #   이 컷 구간에 뜬 간헐 오버레이(하단 Site/Depth 카드 등)가 그대로 노출된다.
            #   → 이 컷 창(window)의 프레임만으로 텍스트 띠를 감지해 그 띠를 먼저 크롭한다.
            fa5, fb5 = int(sa * fps_trk), int((sa + seg_len) * fps_trk)
            win_fr = [str(frames[j]) for j in range(max(0, fa5), min(len(frames), fb5))]
            ct, cb = detect_text_bands(win_fr) if win_fr else (0.0, 0.0)
            precrop = ""
            if ct > 0 or cb > 0:
                pcy = int(round(src_h * ct)) & ~1
                pch = int(round(src_h * (1 - ct - cb))) & ~1
                precrop = f"crop={int(src_w) & ~1}:{pch}:0:{pcy},"
                log.info("[reframe] 컷%d 핏: 번인 텍스트 띠 크롭(상 %.0f%%·하 %.0f%%)",
                         i, ct * 100, cb * 100)
            # precrop 활성 시 delogo는 좌표가 어긋나므로 생략(띠 크롭이 로고 영역도 대개 포함)
            pre = "" if precrop else ((delogo_vf(src_w, src_h, logo_box) + ",") if logo_box else "")
            if wide:
                # ★난파선 등 가로 원경 소스: '블러 배경+축소 끼워넣기'(레터박스=얇은 띠)를 쓰지 않는다.
                #   가로 소스를 9:16에 contain하면 위아래 대부분이 블러가 되어 영상이 얇은 띠로 보인다.
                #   → 화면을 꽉 채우는 cover 크롭(가장자리 일부만 잘림)으로 선체가 크고 선명하게 보이게 한다.
                fc = (f"[0:v]{precrop}{pre}"
                      f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},{GRADE}")
            else:
                # 심해 생물 등: 피사체가 작아 전체 맥락이 중요 → 블러 배경 + 전체 프레임(contain).
                fc = (f"[0:v]{precrop}{pre}split=2[a][b];"
                      f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                      f"gblur=sigma=32,eq=brightness=-0.14:saturation=1.02[bg];"
                      f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                      f"[bg][fg]overlay=(W-w)/2:(H-h)/2,{GRADE}")
            cmd += ["-filter_complex", fc, str(seg_out)]
        else:
            # 접사 컷: 피사체 추적 + 완만한 줌. 크롭이라 좌우 일부만 보임.
            z = cycle[i % len(cycle)]
            fa, fb = int(sa * fps_trk), int((sa + seg_len) * fps_trk)
            # 크롭 중심 = 가장 강한 적색(상위 2%)의 무게중심 = ROV 조명 받는 '얼굴'.
            seg_c = cents[fa:fb] or cents
            fx = _median([c[0] for c in seg_c]); fy = _median([c[1] for c in seg_c])
            med_frac = _median((fracs[fa:fb] or fracs))
            # 점유율 상한 0.45: 접사에서도 피사체가 크롭의 45%를 넘지 않게 → 주변 맥락·전신이 더 남아
            # '이게 뭔지' 식별을 확보(과확대 방지).
            z_cap = _m.sqrt(0.45 * src_h * W / (max(med_frac, 1e-4) * src_w * H))
            z = max(1.0, min(z, z_cap))
            if not wide:
                # ★줌인 얼굴 중앙(사용자 규칙): 피사체가 프레임 가장자리에 있으면 넓은 크롭은
                #   가장자리에 '클램프'되어 얼굴이 화면 옆으로 밀린다. 얼굴을 정중앙에 두려면
                #   크롭이 [얼굴 중심±절반]이 소스 안에 들어갈 만큼 충분히 좁아야 한다
                #   (= 약간 더 줌인). 필요한 최소 줌을 계산해 적용하되 상한 1.9로 과확대는 막는다.
                mx = min(max(fx, 1e-3), 1 - 1e-3); my = min(max(fy, 1e-3), 1 - 1e-3)
                z_center_x = (src_h * W / H) / max(2 * src_w * min(mx, 1 - mx), 1e-3)
                z_center_y = 1.0 / (2 * min(my, 1 - my))
                z = max(z, min(max(z_center_x, z_center_y), 1.9))
                z = max(1.0, z)
            cw = int(round((src_h * W / H) / z)) & ~1
            ch = int(round(src_h / z)) & ~1
            cw = min(cw, int(src_w)) & ~1
            cx = int(min(max(fx * src_w - cw / 2, 0), src_w - cw))
            cy = int(min(max(fy * src_h - ch / 2, 0), src_h - ch))
            pre_vf = ""
            if logo_box:
                cx, cy, need_dl = _logo_avoid(cx, cy, cw, ch, fx * src_w, fy * src_h,
                                              src_w, src_h, logo_box)
                if need_dl:
                    pre_vf = delogo_vf(src_w, src_h, logo_box) + ","
            vf = f"{pre_vf}crop={cw}:{ch}:{cx}:{cy},scale={W}:{H},setsar=1,{GRADE}"
            cmd += ["-vf", vf, str(seg_out)]
        subprocess.run(cmd, check=True)
        lines.append(f"file '{seg_out.name}'")
    concat.write_text("\n".join(lines), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(concat), "-c", "copy", out_path], check=True)
    log.info("[reframe] 9:16 완성: %s (%d컷 중 전신핏 %d컷 %.0f%%, %.1fs)",
             out_path, len(plan), n_fit, 100.0 * n_fit / max(len(plan), 1), target_dur)
    return out_path
