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



# ★자막 '고아' 판정(운영자 확정 · 절대 회귀 금지): 한 글자나 문장부호만 홀로 한 페이지에 뜨면 안 된다.
#   실사고(운영자 지적, 재차): "마침표만 그다음 페이지 자막으로 넘어가는 문제가 발생한다."
#   원인은 두 층이었다 — ⓐ한 줄 조각 나누기(_fit_pieces)의 꼬리 ⓑ**청크 자체가 「。」 하나**인 경우
#   (조각이 1개뿐이라 기존 꼬리 병합 로직이 손대지 못했다).
_ORPHANISH = re.compile(r"^[、。，．・「」『』（）〜ー…!?！？\s\-]*$")


def _is_orphan(s: str) -> bool:
    """한 글자 이하이거나 문장부호만으로 이루어진 조각 → 홀로 띄우지 않는다."""
    t = (s or "").strip()
    return len(t) <= 1 or bool(_ORPHANISH.match(t))


def merge_orphan_chunks(disp: list) -> list:
    """표시 청크 목록에서 고아 청크를 **앞 청크에 흡수**한다(표시 시간도 이어붙인다).

    앞이 없으면(첫 청크가 고아) 뒤 청크의 앞에 붙인다. 합쳐서 줄이 길어지면 렌더 단계가
    **글자 크기를 조금 줄여** 한 줄을 유지한다(두 줄 금지 — 운영자 확정).
    """
    out: list = []
    for item in disp or []:
        ch, st, en = item[0], item[1], item[2]
        if _is_orphan(ch) and out:
            pch, pst, _pen = out[-1]
            out[-1] = (pch + str(ch).strip(), pst, en)      # 앞 청크에 흡수 + 끝시각 연장
            continue
        out.append((str(ch), st, en))
    if len(out) >= 2 and _is_orphan(out[0][0]):             # 첫 청크가 고아면 뒤에 붙인다
        ch, st, _en = out[0]
        nch, _nst, nen = out[1]
        out[1] = (str(ch).strip() + nch, st, nen)
        out.pop(0)
    return out

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
    # ★고아 조각(한 글자·문장부호만) 전면 차단 — 마지막뿐 아니라 **중간 조각도** 이웃에 흡수한다.
    #   조금 길어져도 의미 있는 덩어리가 낫다(넘치면 아래에서 글자를 살짝 줄여 한 줄 유지).
    i = 0
    while i < len(pieces):
        if len(pieces) >= 2 and _is_orphan(pieces[i]):
            if i > 0:
                pieces[i - 1] += pieces[i]
            else:
                pieces[i + 1] = pieces[i] + pieces[i + 1]
            pieces.pop(i)
            i = max(0, i - 1)
            continue
        i += 1
    if len(pieces) <= 1:
        return [(text, st, en)]
    total = sum(len(p) for p in pieces) or 1
    out, t = [], st
    for k, p in enumerate(pieces):
        seg = (en - st) * (len(p) / total)
        pe = en if k == len(pieces) - 1 else t + seg
        out.append((p, t, pe)); t = pe
    return out


# 고아 병합으로 줄이 길어졌을 때 허용하는 **최소 축소율**(이 아래로는 안 줄인다 — 가독성 바닥).
_MIN_FS_RATIO = 0.82


def fit_font_size(text: str, max_px: float, subsz: int) -> int:
    """한 줄을 유지하기 위한 글자 크기(px). 넘치지 않으면 기본 크기 그대로.

    ★두 줄로 만들지 않는다(운영자 확정) — 넘치면 **아주 조금 줄여서** 한 줄에 담는다.
    """
    w = sum(_char_px(c, subsz) for c in text)
    if w <= max_px or w <= 0:
        return subsz
    return max(int(subsz * _MIN_FS_RATIO), int(subsz * max_px / w))


# ★구독 유도(운영자 지시 "무조건 구독 늘려. 자막에도 넣어."). 실측: 조회 35,969에 구독 24명
#   (0.067%) · 시청시간의 98.9%가 미구독자. 자막에 구독 문구가 지나가도 **본문과 똑같은 스타일**이면
#   그냥 대사로 읽히고 만다 → CTA 절만 시안색·굵게·조금 크게 띄워 '눌러야 할 것'으로 보이게 한다.
_CTA_MARKERS = ("チャンネル登録", "채널 구독", "登録して", "구독")
# 중간 배지: 본문 도중 한 번, 화면 오른쪽 위에 작게. 상시 노출은 거슬려서 역효과 → 딱 한 번 3초.
_MID_BADGE_TEXT = "チャンネル登録"
_MID_BADGE_DUR_S = 3.0
# ★끝 배지: 나레이션형 쇼츠(nv-*)는 **엔드카드가 없어** 마지막에 구독 신호가 화면에 안 나온다
#   (도감형은 엔드카드가 담당). 자막 레이어로 큰 구독 배지를 마지막에 띄워 같은 역할을 하게 한다.
#   영상 길이·오디오를 건드리지 않아 안전하다(엔드카드를 붙이면 자막 오프셋 계산이 틀어진다).
_END_BADGE_DUR_S = 2.6


def is_cta_line(text: str) -> bool:
    """이 자막 줄이 구독 유도 문구인가(강조 대상)."""
    t = str(text or "")
    return any(k in t for k in _CTA_MARKERS)


def pick_mid_badge_at(disp: list[tuple], target_s: float = 10.0) -> float | None:
    """중간 구독 배지를 띄울 시각(초). 본문이 짧으면 None(띄우지 않는다).

    끝의 CTA와 너무 붙으면 같은 말을 두 번 보는 꼴이라, **마지막 CTA에서 6초 이상 떨어진**
    지점만 고른다. 본문 전체가 짧으면 배지를 포기한다(중복 노출 방지).
    """
    if not disp:
        return None
    try:
        end = float(disp[-1][2])
    except Exception:  # noqa: BLE001
        return None
    at = float(target_s)
    if at + _MID_BADGE_DUR_S > end - 6.0:
        return None
    return at


def build_synced_ass(disp: list[tuple], out_path: str, *, font: str = "Noto Sans CJK JP",
                     accent: str = "&H00EAE06F&", hook_first: bool = True,
                     w: int = 720, h: int = 1280, sub_scale: float = 1.0,
                     mid_badge: bool = True, end_badge: bool = False) -> str:
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
    # ★고아 청크(「。」 하나 등)를 앞 청크에 흡수한 뒤 렌더한다 — 한 글자/마침표만 뜨는 페이지 차단.
    disp = merge_orphan_chunks(disp)
    for i, (ch, st, en) in enumerate(disp):
        if hook_first and i == 0:
            tag = (r"{\an8\pos(%d,%d)\fad(200,180)\fscx118\fscy118\t(0,260,\fscx100\fscy100)"
                   r"\bord4\blur7\3c%s\shad0}" % (w // 2, int(h * 0.28), accent))
            lines.append(f"Dialogue: 0,{_ts(st)},{_ts(en)},Hook,,0,0,0,,{tag}{ch}")
        else:
            _cta = is_cta_line(ch)
            for piece, ps, pe in _fit_pieces(ch, st, en, max_px, subsz):
                # 고아 병합으로 줄이 길어졌으면 **글자만 살짝 줄여** 한 줄을 지킨다(두 줄 금지).
                fs = fit_font_size(piece, max_px, subsz)
                if _cta:
                    # ★구독 유도 절은 시안색·굵게·조금 크게 → 대사가 아니라 '행동 요청'으로 읽히게.
                    #   넘침 방지를 위해 확대분(1.12배)만큼 다시 맞춰 한 줄을 지킨다.
                    fs = fit_font_size(piece, max_px, int(subsz * 1.12))
                    tag = (r"{\fad(70,70)\fs%d\1c&H00FFE9A8&\3c&H00201000&\bord4}" % fs)
                else:
                    tag = "{\\fad(70,70)}" if fs >= subsz else ("{\\fad(70,70)\\fs%d}" % fs)
                lines.append(f"Dialogue: 0,{_ts(ps)},{_ts(pe)},Sub,,0,0,0,,{tag}{piece}")
    # ★본문 중간 구독 배지(딱 1회 · 오른쪽 위). 끝의 CTA만으로는 **끝까지 본 39%**에게만 닿는다.
    #   중간에 한 번 더 보여줘 도중 이탈자에게도 구독 신호를 남긴다. 짧게(3초) · 작게 → 거슬림 최소.
    if mid_badge:
        _at = pick_mid_badge_at(disp)
        if _at is not None:
            _bsz = int(subsz * 0.62)
            _tag = (r"{\an9\pos(%d,%d)\fad(220,260)\fs%d\1c&H00201000&\3c&H00FFE9A8&\bord6\shad0"
                    r"\t(0,400,\fscx108\fscy108)\t(400,800,\fscx100\fscy100)}"
                    % (w - 26, int(h * 0.115), _bsz))
            lines.append(f"Dialogue: 0,{_ts(_at)},{_ts(_at + _MID_BADGE_DUR_S)},"
                         f"Sub,,0,0,0,,{_tag}{_MID_BADGE_TEXT}")
    # ★끝 배지 — 엔드카드가 없는 경로(나레이션형 쇼츠)를 위한 마지막 구독 신호.
    if end_badge and disp:
        try:
            _end = float(disp[-1][2])
        except Exception:  # noqa: BLE001
            _end = 0.0
        if _end > _END_BADGE_DUR_S:
            _st = max(0.0, _end - _END_BADGE_DUR_S)
            _esz = int(subsz * 1.05)
            # ★자막 줄(하단 MarginV≈h*0.16)과 **충분히 떨어뜨린다** — 붙여 놨더니 구독 배지와
            #   구독 자막이 한 덩어리로 뭉쳐 읽혔다(실측 렌더로 확인 후 0.72 → 0.58로 올림).
            _etag = (r"{\an5\pos(%d,%d)\fad(220,180)\fs%d\1c&H00201000&\3c&H00FFE9A8&\bord8\shad0"
                     r"\t(0,300,\fscx112\fscy112)\t(300,700,\fscx100\fscy100)}"
                     % (w // 2, int(h * 0.58), _esz))
            lines.append(f"Dialogue: 0,{_ts(_st)},{_ts(_end)},Sub,,0,0,0,,{_etag}{_MID_BADGE_TEXT}")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    return out_path
