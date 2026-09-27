"""v2 하단 나레이션 자막 — **v1과 같은 카라오케식**(운영자 확정 2026-09-27).

v1(`src/core/narration_sync`)의 방식을 그대로 쓴다: 짧게 끊은 조각을 **말하는 순서대로 하나씩** 하단에 띄운다
(`build_synced_ass` · 하단 Sub 스타일 · 한 줄 유지 · 고아 조각 흡수 · 숫자·날짜 통째 유지).
v2에서 바꾼 점 하나: 조각을 **문장부호(、。？！)에서만** 먼저 끊고(v1의 13글자 기계 분할은 「生き物|が」처럼
단어를 가른다), 한 줄에 안 들어가는 조각은 v1의 문절 경계 분할(`_fit_pieces`)이 나눈다.
조각 시각은 음성 합성 때 조각마다 넣은 <mark>의 timepoints를 쓴다(글자 수 추정이 아니라 실제 발화 시각).

★단어 덩어리(문절) 경계는 **형태소 분석(Janome, 사전 내장 순수 파이썬)** 으로 구한다. v1의 글자 종류 추정은
「生き|物は」「ダイオウグソクムシで|した」처럼 단어 중간을 잘랐다(실측). fugashi는 사전(unidic-lite) 빌드가
환경에 따라 실패해 Janome을 쓴다.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.core import narration_sync as NS  # noqa: E402

FONTS_DIR = ROOT / "vendor" / "fonts"
FONT = "Noto Sans JP"
_PUNCT_SPLIT = re.compile(r"(?<=[、。！？!?])")


_TOK = None
_INDEP = {"名詞", "動詞", "形容詞", "副詞", "連体詞", "接頭詞", "感動詞", "接続詞"}


def bunsetsu_breaks(text: str) -> set[int]:
    """문절이 새로 시작하는 글자 위치 집합(여기서만 줄을 나눌 수 있다)."""
    global _TOK
    if _TOK is None:
        from janome.tokenizer import Tokenizer
        _TOK = Tokenizer()
    toks = list(_TOK.tokenize(text))
    bps, pos, prev = set(), 0, None
    for t in toks:
        p = t.part_of_speech.split(",")
        head = p[0] in _INDEP and p[1] not in ("非自立", "接尾")
        if head and prev is not None:
            pp = prev.part_of_speech.split(",")
            compound = pp[0] == "名詞" and p[0] == "名詞" and pp[1] != "数"   # 복합명사는 붙인다
            after_prefix = pp[0] == "接頭詞"
            if t.surface == "ない" and pp[0] == "助詞":                     # 「見たことのない」 유지
                head = False
            if head and not compound and not after_prefix and pos > 0:
                bps.add(pos)
        if pos > 0 and prev is not None and prev.surface and prev.surface[-1] in "、。！？!?":
            bps.add(pos)
        pos += len(t.surface)
        prev = t
    return bps


def split_chunks(text: str) -> list[str]:
    """문장부호에서만 끊는다(단어 중간 분할 없음)."""
    return [p.strip() for p in _PUNCT_SPLIT.split(text) if p.strip()]


def disp_from_timepoints(jp: str, tps: list[dict], offset: float = 0.0, tail: float = 0.35) -> list[tuple]:
    """표시 문장(jp)을 조각내고, 같은 순서의 발화 조각 timepoints로 시각을 붙인다.
    각 조각은 '자기 시작 → 다음 조각 시작'까지 보인다(v1 `_display_windows`와 같음)."""
    chunks = split_chunks(jp)
    if len(chunks) != len(tps):
        raise ValueError(f"자막 조각({len(chunks)})과 발화 조각({len(tps)}) 수가 다릅니다: {chunks}")
    disp = []
    for i, (c, tp) in enumerate(zip(chunks, tps)):
        st = offset + float(tp["start"])
        en = offset + float(tps[i + 1]["start"]) if i + 1 < len(tps) else offset + float(tp["end"]) + tail
        disp.append((c, st, max(en, st + 0.4)))
    return disp


SUB_SCALE = 0.8   # v1 자막(h*0.039)의 0.8배 — '작은 하단 자막'(운영자 확정). 13글자 가타카나 이름도 한 줄에 든다


def _fit_pieces_no_forced(orig_fit):
    """v1 `_fit_pieces` 결과에서 **문절 경계가 아닌 곳의 강제 분할**을 되돌린다 → 그 줄은 글자만 줄여 한 줄 유지.
    (규칙: 단어 중간에서 자르지 않는다 · 넘치면 글자 크기만 조금 줄인다)"""
    def fit(text, st, en, max_px, subsz):
        pieces = orig_fit(text, st, en, max_px, subsz)
        if len(pieces) <= 1:
            return pieces
        ok = bunsetsu_breaks(text.strip())
        merged, pos = [list(pieces[0])], len(pieces[0][0])
        for p, ps, pe in pieces[1:]:
            if pos in ok:
                merged.append([p, ps, pe])
            else:                               # 강제 분할 → 앞 조각에 붙인다
                merged[-1][0] += p
                merged[-1][2] = pe
            pos += len(p)
        return [tuple(m) for m in merged]
    return fit


def build_ass(disp: list[tuple], out_path: str | Path) -> str:
    """v1 `build_synced_ass` 그대로(하단 Sub 스타일·한 줄·고아 흡수·숫자 통째) — 줄 나눔 경계만 형태소 문절로 바꿔 끼운다."""
    orig_bp, orig_fit = NS._break_points, NS._fit_pieces
    NS._break_points = bunsetsu_breaks
    NS._fit_pieces = _fit_pieces_no_forced(orig_fit)
    try:
        return NS.build_synced_ass(disp, str(out_path), font=FONT, hook_first=False, mid_badge=False,
                                   sub_scale=SUB_SCALE)
    finally:
        NS._break_points, NS._fit_pieces = orig_bp, orig_fit


def burn_filter(ass_path: str | Path) -> str:
    """ffmpeg 필터 문자열(우리 글꼴 폴더 사용 — 시스템에 일본어 글꼴이 없어도 된다)."""
    a = str(ass_path).replace("\\", "/").replace(":", r"\:")
    return f"subtitles='{a}':fontsdir='{FONTS_DIR}'"


def burn(video_in: str, ass_path: str | Path, video_out: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_in, "-vf", burn_filter(ass_path),
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", video_out], check=True)
