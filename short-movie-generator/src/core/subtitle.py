"""subtitle — 단어별 카라오케 자막 (narrated_wildlife 전환).

나레이션에 동기해 단어가 하나씩 팝업, 굵게·중앙 정렬. Gemini TTS가 단어 타임스탬프를
주지 않으므로(스파이크 확인), 문장 오디오 구간 [start,end]을 어절 길이(음절≈글자 수) 비례로
분배해 단어 타이밍을 근사한다(강제 정렬). ASS 자막으로 만들어 FFmpeg로 번인.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from src.core.contracts import PipelineError

log = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).resolve().parents[1] / "vendor" / "fonts"
FONT_NAME = "Black Han Sans"   # 굵고 강한 한글(vendor/fonts/BlackHanSans.ttf)


def word_timings(sent_timings: list[dict]) -> list[dict]:
    """문장 타이밍 → 단어(어절) 타이밍. 각 문장 구간을 글자 수 비례로 분배(근사)."""
    out: list[dict] = []
    for s in sent_timings or []:
        words = str(s.get("text", "")).split()
        if not words:
            continue
        start, end = float(s.get("start", 0)), float(s.get("end", 0))
        dur = max(0.2, end - start)
        weights = [max(1, len(w)) for w in words]
        tot = sum(weights)
        cursor = start
        for w, wt in zip(words, weights):
            wd = dur * wt / tot
            out.append({"word": w, "start": round(cursor, 3), "end": round(cursor + wd, 3)})
            cursor += wd
    return out


def _ts(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600); m = int((t % 3600) // 60); s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(words: list[dict], out_path: str, video_w: int = 720, video_h: int = 1280) -> str:
    """단어별 팝업 ASS 자막 생성(굵게·하단중앙, 짧은 페이드 팝)."""
    fs = max(64, int(video_w * 0.13))          # 큰 굵은 단어
    style = (f"Style: Pop,{FONT_NAME},{fs},&H00FFFFFF,&H00FFFFFF,&H00101010,&H64000000,"
             f"-1,0,0,0,100,100,0,0,1,5,2,2,60,60,230,1")
    head = (
        "[Script Info]\nScriptType: v4.00+\nWrapStyle: 2\n"
        f"PlayResX: {video_w}\nPlayResY: {video_h}\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"{style}\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    ev = []
    for w in words:
        st, en = float(w["start"]), max(float(w["start"]) + 0.12, float(w["end"]))
        # 팝업: 살짝 커지며 등장(\fscx/\fscy + \t), 짧은 페이드
        txt = ("{\\fad(60,40)\\fscx70\\fscy70\\t(0,120,\\fscx100\\fscy100)}" + _esc(w["word"]))
        ev.append(f"Dialogue: 0,{_ts(st)},{_ts(en)},Pop,,0,0,0,,{txt}")
    Path(out_path).write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    return out_path


def burn(video_path: str, ass_path: str, work_dir: str, out_name: str = "subtitled.mp4") -> str:
    """ASS 자막을 영상에 번인. 한글 폰트는 vendor/fonts 우선, 실패 시 시스템 폰트."""
    out = str(Path(work_dir) / out_name)
    # 경로 이스케이프(콜론·콤마) — libass filter 문법
    ass_esc = ass_path.replace("\\", "/").replace(":", "\\:")
    fonts_esc = str(_FONTS_DIR).replace("\\", "/").replace(":", "\\:")
    vf = f"subtitles={ass_esc}:fontsdir={fonts_esc}"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path, "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "copy", out] if _has_audio(video_path) else
        ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path, "-vf", vf,
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-an", out],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not Path(out).exists():
        raise PipelineError("subtitle", f"자막 번인 실패: {proc.stderr[-400:]}")
    return out


def _has_audio(video_path: str) -> bool:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_name", "-of", "csv=p=0", video_path],
        capture_output=True, text=True,
    )
    return bool(r.stdout.strip())
