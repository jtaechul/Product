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
