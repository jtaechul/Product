"""subtitle — 가라오케(노래방식) ASS 자막 생성.

ASS의 \\kf 태그는 "이 단어를 몇 센티초(1/100초) 동안 쓸어 칠할지"를 뜻한다.
칠하기 전 색 = SecondaryColour(흰색), 칠한 뒤 색 = PrimaryColour(하이라이트).
Edge-TTS가 준 실제 단어 타임스탬프를 그대로 넣으므로 목소리와 정확히 맞는다.
"""
from __future__ import annotations

from pathlib import Path

# ASS 색은 &HAABBGGRR (RGB 역순)
HIGHLIGHTS = {
    "노란색": "&H0000FFFF",
    "연두색": "&H0080FF80",
    "하늘색": "&H00FFDF80",
    "분홍색": "&H00C0A0FF",
}

_HEAD = """[Script Info]
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {w}
PlayResY: {h}
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Kara,{font},{size},{hi},&H00FFFFFF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,{mx},{mx},{mv},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""


def _ts(t: float) -> str:
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def _esc(s: str) -> str:
    return (s or "").replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def build_karaoke_ass(lines: list[dict], out_path: str, *,
                      font: str = "NanumGothic",
                      highlight: str = "노란색",
                      video_w: int = 720, video_h: int = 1280) -> str:
    """전역 타임라인 기준 줄 목록 → 가라오케 ASS 파일.

    lines: [{"start": 초, "end": 초, "words": [(단어시작초, 단어길이초, 표시어), ...]}]
    """
    hi = HIGHLIGHTS.get(highlight, HIGHLIGHTS["노란색"])
    head = _HEAD.format(
        w=video_w, h=video_h, font=font,
        size=max(38, int(video_w * 0.072)),
        hi=hi,
        outline=max(3, round(video_w * 0.0055, 1)),
        shadow=max(1, round(video_w * 0.0028, 1)),
        mx=int(video_w * 0.09),
        mv=int(video_h * 0.135),   # 화면 중앙 하단
    )
    events = []
    for ln in lines:
        words = ln.get("words") or []
        if not words:
            continue
        start = float(ln["start"])
        end = max(float(ln["end"]), start + 0.4)
        parts, cursor = [], start
        for w_start, w_dur, disp in words:
            gap = max(0, round((w_start - cursor) * 100))
            if gap:
                parts.append("{\\k%d}" % gap)          # 쉼(침묵) 구간만큼 대기
            dur_cs = max(6, round(w_dur * 100))
            parts.append("{\\kf%d}%s" % (dur_cs, _esc(disp)))
            cursor = w_start + w_dur
        text = "{\\fad(90,90)}" + " ".join(parts)
        events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Kara,,0,0,0,,{text}")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(head + "\n".join(events) + "\n", encoding="utf-8")
    return out_path
