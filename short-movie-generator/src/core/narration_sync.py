"""narration_sync — 나레이션↔자막 정밀 싱크 체계 (모든 영상 공통).

핵심 원칙(왜 이 모듈이 존재하나):
- 과거 자막 타이밍을 '글자 수 비례'로 추정해, 나레이션의 쉼(문장부호)·단어 길이 차이를
  못 맞춰 뒤로 갈수록 어긋났다.
- 해결: TTS 엔진(edge-tts)이 제공하는 **실제 단어 타임스탬프(WordBoundary)** 를 그대로 써서
  각 자막 청크를 '진짜 발화 시각'에 붙인다. 언어 무관(일·영·한 공통) → 전 영상 자동 정합.

계약:
- synthesize(chunks, work_dir, voice, rate) → {mp3, words, disp}
    words: [(start_s, dur_s, text)]  (엔진이 준 단어 경계)
    disp : [(chunk_text, start_s, end_s)]  (각 청크의 화면 표시 창 = 발화 시각에 정합, 공백 없이 연속)
- build_synced_ass(disp, out_path, ...) → ass 경로 (청크당 1줄, 발화 시각에 켜짐)

주의(실행환경): 로컬(에지) 개발 환경은 아웃바운드 HTTPS가 MITM 프록시라 CA 신뢰가 필요.
CA 번들이 있으면 edge-tts의 SSL 컨텍스트에 주입한다. CI엔 프록시가 없어 기본 certifi로 동작.
"""
from __future__ import annotations

import asyncio
import re
import ssl
from pathlib import Path

_PROXY_CA = "/root/.ccr/ca-bundle.crt"
_PUNCT = re.compile(r"[、。，．・「」『』（）\s]")


def _install_ca() -> None:
    """프록시 CA가 있으면 edge-tts SSL 컨텍스트에 주입(로컬 개발). CI엔 무영향.

    주의: Path.exists()도 try 안에 둔다. CI 러너(비 root)에선 /root/.ccr 자체가
    접근 불가라 Python 3.11의 exists()가 PermissionError(EACCES)를 '되던진다'(ENOENT만 삼킴).
    이걸 밖에 두면 CI에서 나레이션 합성이 통째로 죽는다(실제 장애 원인). 전부 감싼다.
    """
    try:
        if Path(_PROXY_CA).exists():
            import edge_tts.communicate as ec
            ec._SSL_CTX = ssl.create_default_context(cafile=_PROXY_CA)
    except Exception:  # noqa: BLE001
        pass


def _core(s: str) -> str:
    """정합 비교용: 문장부호·공백 제거한 핵심 글자."""
    return _PUNCT.sub("", s)


_SPLIT = re.compile(r"(?<=[、。！？!?])")


def karaoke_split(chunks: list[str], max_len: int = 13) -> list[str]:
    """자막을 카라오케용 짧은 단위로 분할.

    긴 절이 통째로 자막에 뜨지 않도록 문장부호(、。！？)에서 끊고, 그래도 긴 조각은
    max_len 글자 단위로 추가 분할. 합쳐진 텍스트는 원본과 동일 → TTS 음성/정합 불변.
    """
    out: list[str] = []
    for c in chunks:
        c = str(c).strip()
        if not c:
            continue
        for part in _SPLIT.split(c):
            p = part.strip()
            if not p:
                continue
            while len(_core(p)) > max_len + 3:
                out.append(p[:max_len])
                p = p[max_len:].strip()
            if p:
                out.append(p)
    return out


async def _synth(text: str, voice: str, rate: str) -> tuple[bytes, list[tuple]]:
    import edge_tts
    c = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    audio = bytearray()
    words: list[tuple] = []
    async for ch in c.stream():
        if ch["type"] == "audio":
            audio += ch["data"]
        elif ch["type"] == "WordBoundary":
            words.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]))
    return bytes(audio), words


def align_chunks_to_words(chunks: list[str], words: list[tuple]) -> list[list]:
    """표시 청크를 단어 타임스탬프에 순서대로 정합 → [[text, start, end]].

    문장부호를 무시하고 글자를 소비해 각 청크가 차지하는 단어들을 찾는다.
    """
    res: list[list] = []
    wi, n = 0, len(words)
    for ch in chunks:
        need = len(_core(ch))
        acc = ""
        start = end = None
        while wi < n and len(acc) < need:
            w = words[wi]
            if start is None:
                start = w[0]
            acc += _core(w[2])
            end = w[0] + w[1]
            wi += 1
        if start is None:  # 경계가 부족하면 직전 끝에 이어 붙임(안전판)
            start = res[-1][2] if res else 0.0
            end = start + 0.3
        res.append([ch, start, end])
    return res


def _display_windows(aligned: list[list]) -> list[tuple]:
    """각 청크를 '자기 시작 → 다음 청크 시작'까지 연속 표시(쉼 구간에도 빈 화면 방지)."""
    n = len(aligned)
    disp = []
    for i, (ch, st, en) in enumerate(aligned):
        de = aligned[i + 1][1] if i + 1 < n else en + 0.3
        disp.append((ch, st, max(de, st + 0.4)))
    return disp


def synthesize(chunks: list[str], work_dir: str,
               voice: str = "ja-JP-KeitaNeural", rate: str = "+14%") -> dict:
    """청크 리스트 → 나레이션 mp3 + 단어 타이밍 + 표시 창(발화 시각 정합).

    반환: {"mp3": path, "words": [...], "disp": [(text,start,end)], "duration": s}
    """
    _install_ca()
    text = "".join(chunks)
    audio, words = asyncio.run(_synth(text, voice, rate))
    mp3 = str(Path(work_dir) / "narration.mp3")
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    Path(mp3).write_bytes(audio)
    disp = _display_windows(align_chunks_to_words(chunks, words))
    dur = (words[-1][0] + words[-1][1]) if words else 0.0
    return {"mp3": mp3, "words": words, "disp": disp, "duration": dur}


def _ts(t: float) -> str:
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


_ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,  {font}, {subsz}, &H00FFFFFF, &H00FFFFFF, &H00161616, &H00000000, -1, 0, 0, 0, 100, 100, 0.6, 0, 1, 3.4, 1.8, 2, 88, 88, {submv}, 1
Style: Hook, {font}, {hooksz}, &H00FFFFFF, &H00FFFFFF, {accent}, &H00000000, -1, 0, 0, 0, 100, 100, 2.0, 0, 1, 4, 0, 8, 88, 88, {hookmv}, 1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _char_px(c: str, subsz: int) -> float:
    """한 글자의 대략 렌더 폭(px). CJK·전각은 ≈폰트크기, 반각(영문·숫자·공백)은 ≈0.55×."""
    o = ord(c)
    full = (0x3000 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xFF00 <= o <= 0xFFEF
            or 0xAC00 <= o <= 0xD7A3)  # 히라·가타·한자·전각·한글
    return subsz * (1.0 if full else 0.55)


_PUNCT_JP = "、。，．！？」』）・…"
_HIRA = lambda o: 0x3040 <= o <= 0x309F                       # noqa: E731
_KANJI_OR_KATA = lambda o: (0x4E00 <= o <= 0x9FFF or 0x30A0 <= o <= 0x30FF)  # noqa: E731


def _break_points(text: str) -> set[int]:
    """단어(문절)를 쪼개지 않는 '끊어도 되는 위치' 집합 = 각 인덱스 i는 text[:i]|text[i:] 경계.

    일본어 문절 경계 근사(형태소 분석기 없이):
    1) 문장부호(、。！？…) 바로 뒤 — 가장 강한 경계.
    2) '히라가나 뒤에 오는 한자/가타카나' 앞 — 새 내용어(단어) 시작. okurigana(활용꼬리 します 등)는
       한자 뒤 히라가나라 여기서 안 걸림 → 단어 꼬리가 잘려 다음 페이지로 넘어가는 사고 방지.
    """
    bps = set()
    for i in range(1, len(text)):
        prev, cur = text[i - 1], text[i]
        if prev in _PUNCT_JP:
            bps.add(i)
        elif _KANJI_OR_KATA(ord(cur)) and _HIRA(ord(prev)):
            bps.add(i)
    return bps


# 숫자와 한 덩어리로 붙는 단위·구두점(날짜·수치를 통째로 유지) — 이 안에서는 절대 줄바꿈 금지.
_NUM_UNIT = set("0123456789０１２３４５６７８９年月日時分秒円ドル億万千百%％‰.,:mkgtcℓ")


def _num_spans(text: str) -> list[tuple]:
    """'숫자 그룹'(숫자+단위/구두점) 구간 [start,end) 목록. 예: '1914年5月29日'을 하나로 본다.
    자막을 폭으로 강제 분할할 때 이 구간 '내부'로 자르지 않게 하려는 용도(1914年5 | 月29日 방지)."""
    spans, i, n = [], 0, len(text)
    while i < n:
        if text[i].isdigit():
            j = i
            while j < n and text[j] in _NUM_UNIT:
                j += 1
            while j - 1 > i and text[j - 1] in ".,:":      # 끝에 붙은 구두점은 그룹에서 제외
                j -= 1
            spans.append((i, j)); i = j
        else:
            i += 1
    return spans


def _snap_out_of_num(cut: int, start: int, spans: list[tuple]) -> int:
    """자를 위치 cut이 숫자 그룹 내부면 그룹 경계로 옮긴다: 앞쪽 진행이 있으면 그룹 시작으로
    (그룹을 다음 조각으로 통째로), 없으면 그룹 끝으로(약간 넘쳐도 날짜를 쪼개지 않음)."""
    for a, b in spans:
        if a < cut < b:
            return a if a > start else b
    return cut


def _fit_pieces(text: str, st: float, en: float, max_px: float, subsz: int) -> list[tuple]:
    """한 자막 청크를 '한 줄에 들어가는 조각'들로 쪼갠다 — 단어(문절) 단위로만, 글자 중간 금지.

    - 통째로 한 줄에 들어가면 1개.
    - 넘치면 '끊어도 되는 위치(_break_points)'에서만 나눔 → 절대 단어를 글자 단위로 자르지 않음
      ("暮らします。"의 꼬리 'す。'만 넘어가는 사고 방지). 각 조각의 표시창은 글자수 비례로 분배.
    - 문절 경계가 하나도 없는(외자 긴 단어 등) 극단 케이스만 폭 기준 강제 분할(최후 수단).
    """
    text = text.strip()
    if not text:
        return []

    def width(s):
        return sum(_char_px(c, subsz) for c in s)

    if width(text) <= max_px:
        return [(text, st, en)]

    bps = sorted(_break_points(text))
    spans = _num_spans(text)                     # 숫자·날짜 그룹(내부 분할 금지)
    pieces, start, n = [], 0, len(text)
    while start < n:
        # start에서 폭이 허용되는 최대 end 계산
        end, cur = start, 0.0
        while end < n and cur + _char_px(text[end], subsz) <= max_px:
            cur += _char_px(text[end], subsz)
            end += 1
        if end >= n:
            cut = n
        else:
            cand = [b for b in bps if start < b <= end]
            if cand:
                cut = max(cand)
                # 남는 꼬리가 너무 짧으면(고아 방지) 더 앞 경계로 당겨 꼬리를 키움
                if 0 < n - cut < 2:
                    earlier = [b for b in cand if n - b >= 2]
                    cut = max(earlier) if earlier else cut
            else:
                cut = end  # 문절 경계 전무 → 최후수단 폭 분할
        cut = _snap_out_of_num(cut, start, spans)   # ★숫자·날짜 한가운데 자르지 않기(1914年5月29日 유지)
        if cut <= start:                            # 안전판(그룹이 통째로 max_px 초과 등) — 폭 분할로 진행
            cut = max(end, start + 1)
        pieces.append(text[start:cut])
        start = cut
    pieces = [p for p in (s.strip() for s in pieces) if p]
    # 마지막 조각이 1글자면 앞 조각에 붙여 '한 글자 페이지' 원천 차단(약간 넘쳐도 의미 우선)
    if len(pieces) >= 2 and len(pieces[-1]) <= 1:
        pieces[-2] += pieces[-1]
        pieces.pop()
    if len(pieces) <= 1:
        return [(text, st, en)]
    total = sum(len(p) for p in pieces) or 1
    out, t = [], st
    for k, p in enumerate(pieces):
        seg = (en - st) * (len(p) / total)
        pe = en if k == len(pieces) - 1 else t + seg
        out.append((p, t, pe)); t = pe
    return out


def build_synced_ass(disp: list[tuple], out_path: str, *, font: str = "Noto Sans CJK JP",
                     accent: str = "&H00EAE06F&", hook_first: bool = True,
                     w: int = 720, h: int = 1280, sub_scale: float = 1.0) -> str:
    """발화 시각에 정합된 disp로 ASS 생성. 청크당 1줄(고정 위치·크기). 첫 청크는 매력형 훅.

    accent: ASS 색(&HBBGGRR&). 테마 순환(cyan/gold/coral)을 상위에서 주입.
    sub_scale: 본문 자막 크기 배율(기본 1.0). 롱폼(16:9)은 h가 작아 자막이 작으므로 2.0 등으로 키운다.
    ★자막이 커져 프레임을 넘칠 땐 줄바꿈(WrapStyle) 대신 _fit_pieces로 '한 줄 조각'으로
      쪼개 순차 표시한다(세로 쇼츠 가독성·깔끔함 우선, 요청 반영).
    """
    subsz = int(h * 0.039 * sub_scale)
    margin = 88                                    # Sub 스타일 MarginL/R(인스타 릴스 좌우 안전여백 ↑)
    max_px = (w - 2 * margin) * 0.96               # 안전 여유 4%
    lines = [_ASS_HEAD.format(w=w, h=h, font=font,
                              subsz=subsz, submv=int(h * 0.16),
                              hooksz=int(h * 0.053), hookmv=int(h * 0.234),
                              accent=accent.strip("&") and accent)]
    for i, (ch, st, en) in enumerate(disp):
        if hook_first and i == 0:
            tag = (r"{\an8\pos(%d,%d)\fad(200,180)\fscx118\fscy118\t(0,260,\fscx100\fscy100)"
                   r"\bord4\blur7\3c%s\shad0}" % (w // 2, int(h * 0.28), accent))
            lines.append(f"Dialogue: 0,{_ts(st)},{_ts(en)},Hook,,0,0,0,,{tag}{ch}")
        else:
            for piece, ps, pe in _fit_pieces(ch, st, en, max_px, subsz):
                lines.append(f"Dialogue: 0,{_ts(ps)},{_ts(pe)},Sub,,0,0,0,,{{\\fad(70,70)}}{piece}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path
