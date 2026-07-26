"""원본 미리보기 mp4 생성 — 운영자가 **아이폰에서** 컷 구간을 눈으로 정하기 위한 파일.

배경(실사고): 소싱 원본의 대다수가 **WebM(VP8/VP9)** 인데, iOS 사파리는 VP8 WebM을 재생하지
못한다(실측: 소싱 캐시 17건 중 14건이 webm, 문제의 클립은 VP8/Vorbis). 그래서 관리자 페이지의
'원본 영상 보기'가 폰에서 검은 화면이었고, **구간을 눈으로 정할 방법이 없었다.**

해결(운영자 확정): 제작할 때 원본을 **480p H.264 mp4**로 한 벌 만들어 릴리스에 함께 올리고,
관리자 페이지는 그 mp4를 재생한다. 어느 기기에서도 재생·스크럽되고 초 단위가 정확하다.

원칙:
- **원본 그대로의 타임라인**을 유지한다(자르거나 이어붙이지 않는다). 여기서 읽은 '초'가 곧
  컷 지정에 쓰는 초여야 하기 때문이다.
- 실패해도 제작을 막지 않는다(미리보기만 없는 상태로 발행).
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("shorts")

_MAX_H = 480          # 세로 480p — 폰에서 충분하고 용량이 작다
_CRF = 30             # 미리보기용(화질보다 용량)
_TIMEOUT = 900


def make_preview_mp4(src: str, out_path: str) -> str:
    """원본을 480p H.264 mp4(미리보기용)로 변환해 경로 반환. 실패 시 빈 문자열.

    이미 mp4(H.264)라도 용량을 줄이려 다시 인코딩한다 — 폰에서 로딩이 빨라야 실제로 쓰인다.
    """
    s, out = Path(src), Path(out_path)
    if not s.exists() or s.stat().st_size < 10_000:
        return ""
    out.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ffmpeg"):
        log.info("[preview] ffmpeg 없음 → 미리보기 생략")
        return ""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(s),
             # 세로가 480보다 작으면 확대하지 않는다(-2=짝수 보정, 코덱 요구)
             "-vf", f"scale=-2:'min({_MAX_H},ih)'",
             "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.1",
             "-preset", "veryfast", "-crf", str(_CRF), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "64k", "-ac", "1",
             "-movflags", "+faststart", str(out)],
            capture_output=True, text=True, timeout=_TIMEOUT)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 20_000:
            log.info("[preview] 원본 미리보기 mp4: %s (%.1fMB)", out, out.stat().st_size / 1e6)
            return str(out)
        log.warning("[preview] 변환 실패(rc=%s): %s", r.returncode, (r.stderr or "")[-200:])
    except Exception as e:  # noqa: BLE001
        log.warning("[preview] 변환 생략(오류): %s", e)
    return ""


# ── 프레임 사진 시트(contact sheet) — 손가락으로 구간·크롭을 고르기 위한 재료 ──────────
# 왜(운영자 확정): 원본 대부분이 WebM이라 아이폰에서 **재생 자체가 안 돼** '재생 위치 찍기' 방식이
# 무용지물이었다(현재 시각이 늘 0). → 재생 없이도 고를 수 있도록 **일정 간격 프레임을 한 장의
# 이미지로** 만들어 두고, 화면에서 타일로 잘라 보여준다(파일 1개라 가볍고 어디서나 뜬다).
_SHEET_STEP_S = 2.0        # 몇 초 간격으로 한 장
_SHEET_COLS = 8            # 가로 타일 수
_SHEET_TILE_W = 240        # 타일 가로 픽셀
_SHEET_MAX_TILES = 96      # 최대 타일(≈3분 12초 분량) — 파일이 너무 커지지 않게


def make_frame_sheet(src: str, out_path: str, step_s: float = _SHEET_STEP_S) -> dict | None:
    """원본을 step_s 간격으로 캡처해 한 장의 시트 이미지로 만든다.
    반환: {url 없이} {"cols","rows","n","step","tw","th"} — 호출부가 url을 붙여 저장한다. 실패 시 None."""
    s, out = Path(src), Path(out_path)
    if not s.exists() or not shutil.which("ffmpeg"):
        return None
    dur = _probe_dur(str(s))
    if dur <= 0:
        return None
    n = max(1, min(_SHEET_MAX_TILES, int(dur // step_s) + 1))
    cols = min(_SHEET_COLS, n)
    rows = (n + cols - 1) // cols
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(s),
             "-vf", (f"fps=1/{step_s},scale={_SHEET_TILE_W}:-2,"
                     f"tile={cols}x{rows}:padding=2:color=black"),
             "-frames:v", "1", "-q:v", "4", str(out)],
            capture_output=True, text=True, timeout=_TIMEOUT)
        if r.returncode != 0 or not out.exists() or out.stat().st_size < 5_000:
            log.warning("[preview] 프레임 시트 실패(rc=%s): %s", r.returncode, (r.stderr or "")[-200:])
            return None
        # 타일 높이는 원본 비율에서 계산(정확한 표시 비율 산출용)
        wh = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(s)],
                            capture_output=True, text=True, timeout=60).stdout.strip()
        sw, sh = (int(x) for x in wh.split(",")[:2]) if "," in wh else (16, 9)
        th = max(1, round(_SHEET_TILE_W * sh / max(sw, 1)))
        log.info("[preview] 프레임 시트: %s (%d장 · %dx%d 타일 · %.0fs 간격)", out, n, cols, rows, step_s)
        return {"cols": cols, "rows": rows, "n": n, "step": step_s,
                "tw": _SHEET_TILE_W, "th": th}
    except Exception as e:  # noqa: BLE001
        log.warning("[preview] 프레임 시트 생략(오류): %s", e)
        return None


def _probe_dur(video: str) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", video], capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip() or 0)
    except Exception:  # noqa: BLE001
        return 0.0
