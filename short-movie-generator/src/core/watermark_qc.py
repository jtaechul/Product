"""watermark_qc — 실사 원본·최종 렌더의 박힌 문구(로고·URL·크레딧 슬레이트) 자동 검출/제거/검증.

★하드룰(CLAUDE.md #9): 소스 영상에 박힌 로고·글씨·워터마크는 최종 화면에 절대 노출 금지.
과거 '좌상단 고정 박스(logo_box) 하나만 delogo' 방식이라 ① 박스보다 넓은 로고 ② 하단 중앙
"OCEANEXPLORER.NOAA.GOV" URL ③ 전면 크레딧 슬레이트("NOAA OFFICE OF ...")가 그대로 노출되는
사고가 실제로 발생 → 좌표 하드코딩을 폐기하고 **1초 간격 OCR 스캔**으로 자동화한다.

3단계:
1) scan(): 클립을 1초 간격 프레임 OCR → 초별 텍스트 박스 목록.
2) plan(): 스캔 결과로 ①슬레이트 초(대면적 텍스트)는 사용 구간에서 회피(시작점 이동)
   ②나머지 워터마크 박스는 클러스터 → 시간 조건부 delogo 필터 체인 생성.
3) verify(): 최종 렌더를 다시 1초 간격 OCR → 금지 토큰(NOAA·OCEANEXPLORER 등) 검출 시
   해당 (초, 문구, 박스) 목록 반환. **비어 있지 않으면 제작 실패 처리**가 원칙(불량 발행 차단).

OCR: tesseract(eng). 반투명 로고 대비 대비강화·2배 확대 전처리 병행.
원본(raw) 스캔은 '영문 단어가 보이면 전부 이물질'로 취급(원본엔 우리 텍스트가 없으므로),
최종 렌더 검증은 우리 HUD의 정당한 영문(DOSSIER·RANK·학명·ABYSS)이 있으므로 금지 토큰만 본다.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# 금지 토큰(최종 렌더 검증용) — NOAA 계열 소스 문구. 학명·우리 HUD 문구와 겹치지 않게 구체적으로.
# 실측: 반투명 로고는 부분 인식(LORATION·PLORA·OCEA 등)이 흔함 → 파편 패턴 포함.
# (우리 화면의 정당한 영문은 DEEP-SEA DOSSIER·RANK·ABYSS·학명뿐 — 아래와 겹치지 않음 확인됨)
FORBIDDEN = re.compile(
    r"NOAA|OKEANOS|OKEA|OCEAN|OCEA\b|EXPLOR|PLORA|LORAT|LORATION|RATION\)?[®s]?$|\.GOV|"
    r"FISHERIES|MBARI|COURTESY|OFFICE\s+OF|EXPEDITION|SHAKEDOWN|"
    r"JANUARY|FEBRUARY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER",
    re.IGNORECASE)

# 원본 스캔에서 '텍스트'로 인정할 최소 신뢰도/길이(노이즈 억제)
_MIN_CONF = 55
_MIN_LEN = 3
_WORD_RE = re.compile(r"[A-Za-z0-9]{3,}")


# ★정지-이미지 소스 차단(핵심 규칙): 원본이 '움직이지 않는 정지 화면(사진을 영상으로 포장한 것 등)'
# 이면 영상으로 제작하지 않는다. 실측: 실제 수중 영상은 인접 프레임 median 밝기차 13~36,
# 정지 이미지는 0~1로 확연히 갈린다 → 문턱 3.0 아래면 정지로 판정(넉넉한 마진).
_STATIC_THRESHOLD = 3.0


def motion_score(video: str, sample: int = 20) -> float:
    """원본 클립의 움직임 점수 = 실시간 1fps로 뽑은 인접 프레임들의 median 절대밝기차(0~255).

    컨테이너 duration이 깨진 NOAA webm이 있어 duration에 의존하지 않고 `-frames:v`로 상한만 둔다.
    낮을수록 정지에 가깝다(사진→영상 포장물 걸러내기용).
    """
    from PIL import Image, ImageChops, ImageStat
    with tempfile.TemporaryDirectory(prefix="motion_") as td:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video,
                        "-vf", "fps=1,scale=320:-2", "-frames:v", str(sample),
                        str(Path(td) / "m_%03d.png")], capture_output=True)
        fs = sorted(Path(td).glob("m_*.png"))
        if len(fs) < 3:
            return 0.0                      # 프레임이 거의 없음 = 정지로 취급(안전측)
        diffs = []
        for a, b in zip(fs, fs[1:]):
            d = ImageChops.difference(Image.open(a).convert("L"), Image.open(b).convert("L"))
            diffs.append(ImageStat.Stat(d).mean[0])
        diffs.sort()
        return diffs[len(diffs) // 2]


def is_static_source(video: str, threshold: float = _STATIC_THRESHOLD) -> bool:
    """원본이 정지(이미지) 소스인가 → True면 제작 금지(상위에서 소스 폐기)."""
    score = motion_score(video)
    if score < threshold:
        log.warning("[wm] ★정지 소스 판정(움직임 %.2f < %.1f) → 영상 제작 금지: %s", score, threshold, video)
        return True
    log.info("[wm] 움직임 %.2f(≥%.1f) → 실사 영상 OK: %s", score, threshold, video)
    return False


def _extract_frames(video: str, out_dir: str, start: float = 0.0, dur: float | None = None,
                    fps: float = 1.0, width: int = 1280) -> list[Path]:
    """1초(기본) 간격 프레임 추출. 반환: PNG 경로 목록(시간순, t = start + i/fps)."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", video]
    if dur is not None:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vf", f"fps={fps},scale={width}:-2", str(out / "f_%05d.png")]
    subprocess.run(cmd, check=True, capture_output=True)
    return sorted(out.glob("f_*.png"))


# ★속도. OCR은 프레임당 tesseract 서브프로세스. 과거 '이진화(threshold)'로 잡음을 지우려 했으나
# 실측 결과 이진화한 해저 텍스처가 오히려 수천 개의 가짜 글자 후보(speckle)를 만들어 psm 레이아웃
# 분석이 폭주 → 롱폼 제작이 60분+로 hang. 그래서 이진화 폐기하고 '회색조 + 대비강화'로 되돌린다
# (회색조 해저는 완만한 그라데이션이라 psm이 빠르고, 반투명 로고도 잘 읽힘 — 검출·속도 모두 유리).
# 여기에 ①640폭 축소 ②스레드풀 병렬 ③넉넉한 timeout(안전망) 만 얹어 옛 방식보다 빠르게.
_OCR_MAXW = 480            # ★480축소(psm 부담↓). 워터마크·URL은 큰 글자라 480서도 읽힘
_OCR_TIMEOUT = 8           # 초/프레임(CI에서 psm11이 프레임당 12s+ → 대부분 타임아웃하던 문제.
                           #  8s로 낮춰 '느린 프레임은 빨리 포기'. 프레임 수도 대폭 줄여 총량 최소화)
_OCR_WORKERS = max(2, (os.cpu_count() or 4) - 1)


def _ocr_words(png: Path) -> list[dict]:
    """프레임 1장 OCR → [{text, conf, x, y, w, h}] (정규화 0~1). 회색조·480축소·대비강화 단일패스.

    (2패스→단일패스: 속도 2배. 로고는 모든 프레임에 지속되므로 여러 프레임 중 하나만 잡으면 충분.)
    """
    from PIL import Image, ImageOps
    import pytesseract
    im = Image.open(png).convert("L")
    fw, fh = im.size
    if fw > _OCR_MAXW:
        im = im.resize((_OCR_MAXW, max(1, round(fh * _OCR_MAXW / fw))))
    im = ImageOps.autocontrast(im, cutoff=1)               # 대비강화(반투명 로고까지 또렷하게)
    dw, dh = im.size
    words = []
    try:
        d = pytesseract.image_to_data(im, lang="eng", config="--psm 11 --oem 1",
                                      output_type=pytesseract.Output.DICT, timeout=_OCR_TIMEOUT)
    except (RuntimeError, Exception) as e:  # noqa: BLE001  (timeout 포함 — 그 프레임만 스킵)
        log.info("[wm] OCR 스킵(%s): %s", png.name, str(e)[:60])
        return words
    for i in range(len(d["text"])):
        t = (d["text"][i] or "").strip()
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < _MIN_CONF or len(t) < _MIN_LEN or not _WORD_RE.search(t):
            continue
        words.append({"text": t, "conf": conf,
                      "x": d["left"][i] / dw, "y": d["top"][i] / dh,
                      "w": d["width"][i] / dw, "h": d["height"][i] / dh})
    return words


def scan(video: str, start: float = 0.0, dur: float | None = None, fps: float = 1.0) -> list[dict]:
    """클립을 1초 간격 OCR 스캔 → [{"t": 초, "words": [...]}, ...]. 프레임 OCR은 병렬."""
    from concurrent.futures import ThreadPoolExecutor
    with tempfile.TemporaryDirectory(prefix="wmscan_") as td:
        frames = _extract_frames(video, td, start, dur, fps)
        if not frames:
            return []
        with ThreadPoolExecutor(max_workers=_OCR_WORKERS) as ex:
            results = list(ex.map(_ocr_words, frames))
        return [{"t": start + i / fps, "words": w} for i, w in enumerate(results)]


# NOAA 계열로 보이는 토큰(부분 인식 포함: LORATION·OCEA·plorer.noaa 등) — 지속성과 무관하게 처리
_NOAAISH = re.compile(r"NOAA|OCEAN|EXPLOR|OKEANOS|RATION|LORAT|PLORA|\.GOV|OKEA|"
                      r"RESEARCH|OFFICE|EXPRESS|SHAKEDOWN|EXPEDITION|FISHERIES", re.IGNORECASE)


def _is_slate_second(words: list[dict]) -> bool:
    """크레딧 슬레이트/대형 중앙 문구 판정 — delogo가 아니라 '그 초를 아예 쓰지 않기'로 처리.

    실측(NOAA 클립): 끝 크레딧은 y 0.2~0.8 중앙부에 큰 글자 여러 개, 하단 URL은 y≈0.7에
    대형 한 줄. 좌상단 로고(y<0.15)는 슬레이트가 아니라 지속 워터마크(delogo 대상).
    """
    center = [w for w in words if 0.15 < w["y"] < 0.88]
    if sum(1 for w in center if w["h"] > 0.045 and _NOAAISH.search(w["text"])) >= 1:
        return True                                     # 중앙 대형 NOAA 문구(URL·크레딧)
    strong = [w for w in center if w["conf"] >= 70 and len(w["text"]) >= 4]
    return len(strong) >= 3                             # 여러 단어짜리 크레딧 카드


def _merge_boxes(boxes: list[tuple], gap: float = 0.03) -> list[tuple]:
    """겹치거나 가까운 박스를 합쳐 delogo 박스 수를 최소화(체인 4개 이하 지향)."""
    boxes = [list(b) for b in boxes]
    changed = True
    while changed:
        changed = False
        out = []
        while boxes:
            a = boxes.pop()
            merged = False
            for b in out:
                if not (a[0] > b[0] + b[2] + gap or b[0] > a[0] + a[2] + gap or
                        a[1] > b[1] + b[3] + gap or b[1] > a[1] + a[3] + gap):
                    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
                    x1 = max(a[0] + a[2], b[0] + b[2]); y1 = max(a[1] + a[3], b[1] + b[3])
                    b[0], b[1], b[2], b[3] = x0, y0, x1 - x0, y1 - y0
                    merged = changed = True
                    break
            if not merged:
                out.append(a)
        boxes = out
    return [tuple(b) for b in boxes]


# ── 인위 삽입물(타이틀카드·로고·박힌 그래픽) 검출 — OCR 비의존(운영자 아이디어) ──────────
# 핵심: 합성된 그래픽은 밑 영상이 움직여도 **픽셀이 정확히 고정(frozen)**되고, **쨍한 색/날카로운
# 엣지(graphic)**를 갖는다. 진짜 촬영 영상엔 큰 영역이 몇 초씩 '정확히' 얼어있는 경우가 없다
# (가만히 있는 생물도 부유물·노이즈로 미세하게 변함). 그래서 frozen∧graphic 교집합이 인위 삽입물.
# 결정(운영자 규칙): 중앙에 크게 있으면 → 그 구간 사용 안 함(SKIP), 작고 가장자리면 → delogo.
# ★실클립 보정(배텔로 SUBMANIA 카드 vs NOAA enypniastes 깨끗) — 핵심은 '창 길이 4초':
#   생물은 가만히 있어도 4초면 부유물·조류로 미세 이동해 frozen이 풀리지만, 합성 카드는 4초 내내
#   픽셀-정확 고정 → 4초 창에서 중앙 5%↑면 카드로 확정. 실측: 4초창 배텔로 카드 10.6% vs 깨끗 0.0%
#   (2초창은 13~17% vs 4% 로 붙어 오탐 위험 → 반드시 4초창 유지. 되돌리지 말 것).
_INSERT_FROZEN_MAXDIFF = 2      # 인접프레임 '최대' 밝기차(0~255) 이 미만이면 '정확히 고정'(합성물)
_INSERT_SAT = 95               # 채도(HSV S) 이상이면 '쨍한 색'(그래픽 후보)
_INSERT_EDGE = 65              # FIND_EDGES 강도 이상이면 '날카로운 엣지'(렌더 글자/로고)
_INSERT_WIN_S = 4.0            # ★판정 창 길이(초) — 생물 미세이동으로 오탐을 없애는 핵심 파라미터
_INSERT_SKIP_CENTRAL = 0.05    # 4초 창 중앙밴드에서 삽입물 비율 이상이면 그 구간 SKIP(마진 큼)


def _insert_masks(frames: list["object"]):
    """연속 프레임(win) → frozen∧graphic 마스크(L, 255=삽입물). PIL만 사용(numpy 불필요)."""
    from PIL import ImageChops, ImageFilter
    n = len(frames)
    if n < 2:
        return None
    W, H = frames[0].size
    mx = None
    for a, b in zip(frames, frames[1:]):
        d = ImageChops.difference(a.convert("L"), b.convert("L"))
        mx = d if mx is None else ImageChops.lighter(mx, d)      # 픽셀별 '최대' 인접차
    frozen = mx.point(lambda p: 255 if p < _INSERT_FROZEN_MAXDIFF else 0)
    mid = frames[n // 2]
    sat = mid.convert("HSV").getchannel("S").point(lambda p: 255 if p > _INSERT_SAT else 0)
    edge = mid.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda p: 255 if p > _INSERT_EDGE else 0)
    graphic = ImageChops.logical_or(sat.convert("1"), edge.convert("1")).convert("L")
    return ImageChops.multiply(frozen, graphic).point(lambda p: 255 if p > 0 else 0)


def _central_frac(mask) -> float:
    """마스크의 중앙밴드(가로22~78%·세로15~80%) 커버리지 비율."""
    W, H = mask.size
    cx0, cx1, cy0, cy1 = int(W * .22), int(W * .78), int(H * .15), int(H * .80)
    px = mask.load()
    cen = sum(1 for y in range(cy0, cy1) for x in range(cx0, cx1) if px[x, y])
    return cen / max(1, (cx1 - cx0) * (cy1 - cy0))


def detect_insert_seconds(video: str, scan_cap: float, fps: float = 2.0) -> set:
    """영상에서 '중앙 대형 인위 삽입물(타이틀카드 등)'이 있는 초 집합을 반환(그 구간은 사용 회피).
    2fps로 프레임을 뽑아 2초 창마다 frozen∧graphic 중앙비율을 보고 임계 초과면 그 창을 dirty로.
    ★OCR로 못 읽는 스타일 로고(SUBMANIA 등)를 잡는 게 목적. 실패 시 빈 set(발행 불정지)."""
    try:
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix="ins_") as td:
            paths = _extract_frames(video, td, 0.0, scan_cap, fps=fps, width=240)
            if len(paths) < 4:
                return set()
            frames = [Image.open(p).convert("RGB") for p in paths]
            win = max(4, int(round(_INSERT_WIN_S * fps)))   # ★4초 창(생물 오탐 방지 핵심)
            dirty: set = set()
            for s in range(0, len(frames) - 1, win):
                w = frames[s:s + win]
                m = _insert_masks(w)
                if m is None:
                    continue
                if _central_frac(m) >= _INSERT_SKIP_CENTRAL:
                    t0 = s / fps
                    for k in range(int(t0), int(t0 + win / fps) + 1):
                        dirty.add(k)
            if dirty:
                log.info("[wm] 인위 삽입물(중앙 대형) 검출 → 회피 초: %s", sorted(dirty))
            return dirty
    except Exception as e:  # noqa: BLE001
        log.info("[wm] 삽입물 검출 스킵: %s", e)
        return set()


def plan(video: str, want_start: float, want_dur: float,
         extra_boxes: list[tuple] | None = None) -> dict:
    """사용 구간 계획: 슬레이트 초 회피(시작점 이동) + 워터마크 delogo 박스 산출.

    반환 {"start": 조정된 시작초, "boxes": [(x,y,w,h) 정규화], "dirty": [슬레이트 초...],
          "scanned_s": 스캔 길이}
    - 전체 클립을 1초 간격 스캔 → 슬레이트 초 집합.
    - want_dur 만큼 슬레이트 없는 연속 구간을 want_start 근처부터 탐색(없으면 슬레이트 최소 구간).
    - 선택 구간 안 텍스트 박스는 여유(패딩)를 두고 병합해 delogo 박스로.
    """
    # ★속도(핵심): CI에서 프레임당 OCR이 매우 느려 '프레임 수'가 곧 제작시간이다. 로고는 위치가
    # 고정·지속되므로 전 구간을 촘촘히 볼 필요 없이 **띄엄띄엄 ~14장**만 봐도 로고·슬레이트를 찾는다.
    # (기존 65장/세그먼트 → 14장. 세그먼트 검증까지 없애면 OCR 총량이 1/10로 줄어 hang 해소.)
    # 로고는 상위(extra_boxes=고정 좌상단 박스)에서 이미 항상 덮이므로, 여기 OCR은 '중앙/하단
    # 슬레이트(URL·크레딧 카드) 회피'용. 슬레이트는 크고 여러 초 지속 → 8장만 봐도 충분(속도 최우선).
    scan_cap = want_start + want_dur + 12.0
    n_samples = 8
    fps = max(0.1, n_samples / scan_cap)                  # ~8장 균등 샘플
    secs = scan(video, 0.0, scan_cap, fps=fps)
    dur_s = scan_cap
    slate = {round(s["t"]) for s in secs if _is_slate_second(s["words"])}
    # ★OCR 비의존 삽입물 검출(운영자 아이디어): OCR이 못 읽는 스타일 로고·타이틀카드(중앙 대형
    #   frozen∧graphic)를 잡아 그 초들도 회피 대상에 합친다 → 시작점이 카드 구간을 건너뛴다.
    slate |= detect_insert_seconds(video, scan_cap, fps=2.0)

    def dirty_in(st: float) -> int:
        # 샘플 간격(1/fps)보다 촘촘한 정수초 검사는 의미 없음 → 샘플된 슬레이트 초와 겹치는지만 본다.
        lo, hi = st - 1.0 / fps, st + want_dur + 1.0 / fps
        return sum(1 for k in slate if lo <= k <= hi)

    # want_start 근처부터 깨끗한 창 탐색(앞뒤로 번갈아 확장)
    best, best_d = max(0.0, want_start), dirty_in(want_start)
    if best_d > 0:
        limit = max(0.0, dur_s - want_dur - 1)
        for off in [x * 0.5 for x in range(1, int(limit * 2) + 2)]:
            for st in (want_start + off, want_start - off):
                if st < 0 or st > limit:
                    continue
                d = dirty_in(st)
                if d < best_d:
                    best, best_d = st, d
                    if d == 0:
                        break
            if best_d == 0:
                break
    start = round(best, 2)

    # 선택 구간 내 delogo 대상 선별 — 해저 무늬 오인(산발 소음) 얼룩 방지:
    #  (a) NOAA 계열 토큰은 무조건 포함  (b) 그 외에는 같은 위치(격자 셀)에 3초↑ 지속된 것만.
    win = [s for s in secs if start - 1 <= s["t"] <= start + want_dur + 1]
    cell = lambda w0: (int((w0["x"] + w0["w"] / 2) * 8), int((w0["y"] + w0["h"] / 2) * 8))  # noqa: E731
    counts: dict = {}
    for s in win:
        for c in {cell(w0) for w0 in s["words"]}:
            counts[c] = counts.get(c, 0) + 1
    need = max(3, int(len(win) * 0.2))
    pad = 0.012
    raw = []
    for s in win:
        for w0 in s["words"]:
            if _NOAAISH.search(w0["text"]) or counts.get(cell(w0), 0) >= need:
                raw.append((max(0.0, w0["x"] - pad), max(0.0, w0["y"] - pad),
                            min(1.0, w0["w"] + 2 * pad), min(1.0, w0["h"] + 2 * pad)))
    for b in (extra_boxes or []):
        raw.append(tuple(b))
    boxes = _merge_boxes(raw)
    # 병합 후에도 5개 초과면 큰 것부터 5개(체인 과다 방지)
    boxes = sorted(boxes, key=lambda b: -(b[2] * b[3]))[:5]
    if best_d > 0:
        log.warning("[wm] 슬레이트 완전 회피 실패(%d초 잔존) → delogo 폴백 포함: %s", best_d, video)
    log.info("[wm] plan: start %.1f→%.1f, delogo 박스 %d개, 슬레이트 초 %d개",
             want_start, start, len(boxes), len(slate))
    return {"start": start, "boxes": boxes, "dirty": sorted(slate), "scanned_s": dur_s}


def delogo_chain(boxes: list[tuple], out_w: int, out_h: int) -> str:
    """정규화 박스들 → ffmpeg delogo 필터 체인(콤마 연결). 빈 목록이면 ""."""
    parts = []
    for (x, y, w, h) in boxes:
        px = max(1, min(int(x * out_w), out_w - 8))
        py = max(1, min(int(y * out_h), out_h - 8))
        pw = min(int(w * out_w) + 4, out_w - px - 2)
        ph = min(int(h * out_h) + 4, out_h - py - 2)
        if pw > 8 and ph > 8:
            parts.append(f"delogo=x={px}:y={py}:w={pw}:h={ph}")
    return ",".join(parts)


def verify(video: str, fps: float = 1.0, skip_after: float | None = None) -> list[dict]:
    """최종 렌더 1초 간격 검증 → 금지 토큰 검출 목록 [{"t", "text", "box"}] (비면 통과).

    skip_after: 이 시각 이후는 검사 생략(아웃트로 카드 등 자체 제작 구간).
    """
    secs = scan(video, 0.0, skip_after, fps)
    bad = []
    for s in secs:
        for w0 in s["words"]:
            # 실제 NOAA 워터마크는 대개 conf 높음. 해저 텍스처 오검(가짜 문구)은 낮은 편이라
            # conf≥62 만 '진짜 잔존'으로 본다(가짜 문구로 렌더 전체가 실패하는 사고 방지).
            if w0.get("conf", 0) >= 62 and FORBIDDEN.search(w0["text"]):
                bad.append({"t": s["t"], "text": w0["text"],
                            "box": (w0["x"], w0["y"], w0["w"], w0["h"])})
    if bad:
        log.error("[wm] ★검증 실패 — 금지 문구 %d건: %s", len(bad),
                  [(round(b["t"]), b["text"]) for b in bad[:8]])
    else:
        log.info("[wm] 검증 통과(1초 간격, 금지 문구 0건): %s", video)
    return bad
