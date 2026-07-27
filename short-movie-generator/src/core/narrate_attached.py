"""첨부 영상 나레이션(운영자 요청): 운영자가 직접 받은 영상(예: NOAA 퍼블릭도메인)을 첨부하면
그 영상에 **일본어 나레이션 + 카라오케 자막**을 입혀 쇼츠(9:16) 또는 롱폼(16:9) 완성본을 만든다.

종·소싱과 무관한 독립 경로다(카테고리 파이프라인을 타지 않는다). 재사용:
- 대본: `llm.generate_text`(키 없으면 제목·설명으로 결정론 폴백 → 날조 없음)
- 나레이션: `narration_sync.synthesize`(edge-tts 일본어) + `build_synced_ass`(카라오케 자막)
- 리프레임: 쇼츠=`reframe.reframe_to_vertical`(9:16) · 롱폼=16:9 정규화(레터박스 없이 cover)

★저작권(운영자 확인 책임): 첨부 영상은 **퍼블릭도메인/CC 등 재가공 허용** 소스여야 한다. 이 모듈은
영상을 소싱하지 않고 '운영자가 첨부한 것'만 가공한다(출처·크레딧은 운영자가 캡션/설명에 표기)."""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("shorts")

SHORTS_W, SHORTS_H = 720, 1280
LONG_W, LONG_H = 1920, 1080


def _probe_dur(video: str) -> float:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", video], capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


def _probe_wh(video: str) -> tuple[int, int]:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream=width,height", "-of", "csv=p=0:s=x", video],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        w, h = out.split("x")[:2]
        return int(w), int(h)
    except Exception:  # noqa: BLE001
        return 0, 0


def _watermark_boxes(video: str, dur: float) -> list[tuple]:
    """전 구간 OCR 스캔 → '지속 번인 로고' 박스(정규화). NOAA 계열 토큰 무조건 + 같은 위치 다수 초 지속."""
    from src.core import watermark_qc as wq
    fps = max(0.4, min(1.0, 12.0 / max(1.0, dur)))
    secs = wq.scan(video, 0.0, dur, fps=fps)
    if not secs:
        return []
    cell = lambda w: (int((w["x"] + w["w"] / 2) * 8), int((w["y"] + w["h"] / 2) * 8))  # noqa: E731
    counts: dict = {}
    by_cell: dict = {}
    noaa: list = []
    for s in secs:
        seen = set()
        for w in s["words"]:
            c = cell(w)
            if c not in seen:
                counts[c] = counts.get(c, 0) + 1
                seen.add(c)
            by_cell.setdefault(c, []).append(w)
            if wq._NOAAISH.search(w["text"]):
                noaa.append(w)
    pad = 0.014
    need = max(2, int(len(secs) * 0.4))
    raw: list = []
    def add(w):
        raw.append((max(0.0, w["x"] - pad), max(0.0, w["y"] - pad),
                    min(1.0, w["w"] + 2 * pad), min(1.0, w["h"] + 2 * pad)))
    for w in noaa:
        add(w)
    for c, n in counts.items():
        if n >= need and by_cell.get(c):
            add(by_cell[c][0])
    boxes = wq._merge_boxes(raw)
    return sorted(boxes, key=lambda b: -(b[2] * b[3]))[:5]


def _clean_watermark(video: str, work: Path) -> str:
    """★NOAA 등 '지속되는 번인 로고/URL'을 delogo로 제거. 잠깐 문구는 안 건드림. OCR 없거나 박스 없으면 원본 반환."""
    try:
        from src.core import watermark_qc as wq
        dur = _probe_dur(video)
        sw, sh = _probe_wh(video)
        if dur <= 0 or sw <= 0 or sh <= 0:
            return video
        boxes = _watermark_boxes(video, dur)
        chain = wq.delogo_chain(boxes, sw, sh) if boxes else ""
        if not chain:
            return video
        work.mkdir(parents=True, exist_ok=True)
        out = str(work / "clean.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vf", chain,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-c:a", "copy", out], check=True, timeout=1200)
        # ★검증은 '길이'로(delogo는 길이 보존). 바이트 크기 문턱은 압축 잘되는 소스 오탈락(실사고: 단색 3KB) → 폐기.
        if Path(out).exists() and _probe_dur(out) >= dur * 0.8:
            log.info("[narrate] 워터마크 delogo 적용: %d박스 (%s)", len(boxes), video)
            return out
        return video
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 워터마크 정리 생략(tesseract 없음/실패): %s", e)
        return video


def _sample_frames(video: str, work: Path, n: int = 4) -> list[str]:
    """영상에서 고르게 n장 프레임 추출(비전 분석용). 실패 시 []."""
    dur = _probe_dur(video) or 0.0
    work.mkdir(parents=True, exist_ok=True)
    out: list[str] = []
    if dur <= 0:
        return out
    for i in range(n):
        t = dur * (i + 0.5) / n
        fp = work / f"vf_{i}.jpg"
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
                            "-frames:v", "1", "-vf", "scale=512:-1", str(fp)], check=True, timeout=60)
            if fp.exists() and fp.stat().st_size > 1000:
                out.append(str(fp))
        except Exception:  # noqa: BLE001
            continue
    return out


# 쇼츠 최소 길이(초). 나레이션이 짧아도 여기까지는 원본을 보여준다(원본이 더 짧으면 원본 길이).
_SHORTS_MIN_S = 30.0
# ★쇼츠 나레이션 속도(운영자 확정 · "자막이 너무 빠르다" 2차 수정): narration_sync 기본값은
#   +14%(빠름)라 자막이 1.4초마다 넘어갔다. 보통 속도로 낮춰 한 자막이 오래 머물게 한다.
#   ※도감형(reels)은 운영자 확정에 따라 기존 속도를 유지한다(나레이션형만 적용).
_SHORTS_TTS_RATE = "+0%"

_LICENSE_LABEL = {
    "public-domain": "Public Domain", "cc0": "CC0",
    "cc-by": "CC BY", "cc-by-sa": "CC BY-SA", "kogl-type1": "KOGL Type 1",
}


def _credit_line(credit: str, license_id: str) -> str:
    """'저작자 · 라이선스' 한 줄. 둘 다 없으면 ''(빈 줄을 넣지 않는다).
    ★나레이션형은 엔드카드가 없어 캡션이 유일한 표기 위치다(운영자 확정)."""
    c = (credit or "").strip()
    label = _LICENSE_LABEL.get((license_id or "").strip().lower(), "")
    if not c and not label:
        return ""
    if not c:
        return label
    if not label:
        return c
    flat = c.replace(" ", "").replace("-", "").upper()
    if label.replace(" ", "").replace("-", "").upper() in flat:
        return c            # 크레딧에 이미 라이선스가 적혀 있으면 중복 금지
    return f"{c} · {label}"


def _trim_intro_outro_cards(video: str, work: Path) -> str:
    """인트로·아웃트로 브랜딩 카드(로고 화면)를 잘라낸 '본편만' 소스를 만들어 경로를 반환.

    ★실사고: NOAA 'Earth Is Blue' 클립으로 만든 22초 쇼츠에서 **10초가 로고 화면**이었다.
    도감형(reels)은 footage._auto_trim_cards 로 이미 잘라내고 있었는데 나레이션형엔 없었다.
    실패하면 원본 경로를 그대로 돌려준다(제작을 막지 않는다)."""
    try:
        from src.core import footage as _ft
        dur = _probe_dur(video)
        head, tail = _ft._auto_trim_cards(video, dur) if dur else (0.0, 0.0)
        if head <= 0 and tail <= 0:
            return video
        keep = dur - head - tail
        if keep < 6.0:                     # 다 잘라내면 쓸 게 없다 → 원본 유지
            log.info("[narrate] 카드 트림 결과가 너무 짧아 원본 사용(%.1fs)", keep)
            return video
        out = str(work / "no_cards.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{head:.2f}",
                        "-t", f"{keep:.2f}", "-i", video, "-c:v", "libx264", "-preset", "medium",
                        "-crf", "18", "-c:a", "aac", out], check=True, timeout=1800)
        log.info("[narrate] 인트로·아웃트로 카드 제거: 앞 %.1fs · 뒤 %.1fs → 본편 %.1fs",
                 head, tail, keep)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("[narrate] 카드 트림 생략(오류): %s", e)
        return video


def _speech_notes(video: str, work: Path, limit: int = 2400) -> str:
    """원본 음성을 전사해 **대본 근거 텍스트**로 돌려준다(번역 안 함 — _jp_script가 일본어로 쓴다).

    ★운영자 확정 우선순위: ①원본 음성 ②출처 페이지 설명 ③(최후수단)화면 분석.
    해설·인터뷰가 있는 영상은 화면만 보는 것보다 훨씬 정확하고 내용이 풍부해 1순위다.
    무음·음악만·faster-whisper 미설치면 ''(호출부가 다음 근거로 넘어간다)."""
    try:
        from src.core import transcribe as _tr
        tr = _tr.transcribe(video, str(work / "asr"))
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 음성 전사 생략(오류): %s", e)
        return ""
    if not tr or not tr.get("segments"):
        return ""
    txt = " ".join((sg.get("text") or "").strip() for sg in tr["segments"]).strip()
    txt = re.sub(r"\s+", " ", txt)
    if len(txt) < 40:            # 인사말 한두 마디뿐이면 근거로 못 쓴다
        return ""
    log.info("[narrate] 음성 전사 확보: %d자(언어=%s · %d문장)",
             len(txt), tr.get("lang", "?"), len(tr["segments"]))
    return txt[:limit]


def _describe_video(video: str, work: Path) -> str:
    """영상 프레임을 비전 LLM으로 '눈으로 보고' 사실 설명(일본어)을 만든다 → 대본 근거.
    ★날조 금지: 화면에 실제로 보이는 것만 서술(없는 사실·수치·고유명 금지). 키 없으면 ''(폴백)."""
    frames = _sample_frames(video, work / "frames", 4)
    if not frames:
        return ""
    from src.core import llm
    prompt = (
        "あなたは映像内容の記述アシスタントです。渡された複数フレームは1本の動画から等間隔で抜いたものです。"
        "画面に実際に写っているものだけを、日本語で3〜5文の短い事実説明にしてください。"
        "被写体・場所・動き・雰囲気を客観的に。★推測や創作は禁止（映っていない固有名詞・数値・物語は書かない）。"
        "出力は説明文のみ。")
    txt = llm.describe_frames(frames, prompt, max_tokens=400)
    return (txt or "").strip()


def _jp_chunks_from_notes(title: str, notes: str, max_chunks: int = 18) -> list[str]:
    """LLM 없이도 도는 결정론 폴백: 제목·설명 텍스트를 자막 청크(문장/구두점 단위)로 나눈다.
    ★날조 금지: 운영자가 준 제목·설명 문장만 쓴다(없는 사실을 지어내지 않는다)."""
    text = (notes or "").strip() or (title or "").strip()
    if not text:
        return []
    # 문장부호(일본어·영문) 기준 분절 후, 너무 길면 다시 쪼갠다.
    parts = re.split(r"(?<=[。．\.!?！？、,])\s*", text)
    chunks: list[str] = []
    for p in parts:
        p = p.strip()
        while len(p) > 24:                         # 자막 한 줄 상한 근처에서 강제 분절
            cut = p[:24]
            chunks.append(cut); p = p[24:]
        if p:
            chunks.append(p)
    return [c for c in chunks if c][:max_chunks]


def _jp_script(title: str, notes: str, mode: str, conservative: bool = False) -> list[str]:
    """일본어 나레이션 대본(청크 리스트) 생성. LLM 우선, 실패 시 결정론 폴백.

    `conservative=True`(운영자 확정 "최대한 무난하게"): 근거가 **화면 분석뿐**일 때 쓴다.
    화면만 보고 쓴 대본은 종·행동을 단정하면 그대로 오정보가 되므로, 단정과 구체 주장을 금지하고
    '보이는 것 + 바다 일반의 정서'로만 무난하게 쓰게 한다."""
    from src.core import llm
    # ★쇼츠 문장 수(운영자 확정 · 실사고: 22초에 자막 11개 → 2초에 하나씩 넘어가 숨이 찼다).
    #   6~9문장이면 30~40초 영상에서 문장당 4~5초 → 읽히고 여운이 생긴다.
    # ★쇼츠 문장 수·길이(운영자 확정 2차 · 실사고: 나레이션 12.4초에 자막 9개 = 1.4초마다 교체).
    #   원인은 ①TTS 속도 +14% ②한 줄 7~14자로 너무 잘게 쪼갬. → 5~7문장 × 12~20자로 굵게 만들고
    #   속도도 보통(_SHORTS_TTS_RATE)으로 낮춰 자막 하나가 3~4초 머물게 한다.
    n_hint = "5〜7" if mode == "shorts" else "24〜40"
    len_hint = "12〜20文字" if mode == "shorts" else "7〜14文字"
    safe = ("\n★この素材は『画面から見えること』しか根拠がありません。"
            "種名・生態・行動の意図・数値・場所を**断定しないでください**。"
            "「〜のようです」「〜が広がります」のように見えるままを穏やかに述べ、"
            "海そのものの静けさ・スケール感で余韻を作ってください。"
            if conservative else "")
    prompt = (
        "あなたは自然・海洋ドキュメンタリーの日本語ナレーターです。以下の素材情報だけを使い、"
        "落ち着いた敬体（です・ます）で短いナレーションを書いてください。事実の創作は禁止——"
        "与えられた情報にない固有名詞・数値・断定は書かないこと。装飾的な導入で始め、"
        f"1行に日本語で{len_hint}程度、全体で{n_hint}行。各行は字幕として画面に出ます。{safe}\n"
        f"【タイトル】{title}\n【内容メモ】{notes}\n"
        "出力は本文のみ。1行1チャンクで、記号や番号は付けないでください。"
    )
    txt = llm.generate_text(prompt, max_tokens=900)
    if txt:
        lines = [re.sub(r"^[\s0-9.\-・*]+", "", ln).strip() for ln in txt.splitlines()]
        lines = [ln for ln in lines if ln and not ln.startswith("【")]
        if len(lines) >= 3:
            cap = 7 if mode == "shorts" else 44
            return lines[:cap]
    return _jp_chunks_from_notes(title, notes, 7 if mode == "shorts" else 44)


def _dedup_tags(tags, core_jp, limit: int = 12) -> list[str]:
    """해시태그 정규화·중복제거. ★유튜브 SEO상 태그가 3개뿐이면 검색 노출이 약하다(운영자 지적:
    '말도 안 되는 3개') → 상한을 12개로 올려 내용 기반 태그가 넉넉히 살아남게 한다."""
    out: list[str] = []
    for t in list(core_jp) + list(tags or []):
        t = str(t).strip()
        if not t:
            continue
        # 문장·설명이 태그로 새는 것 방지(너무 긴 것·공백 다수 배제)
        if not t.startswith("#"):
            t = "#" + t.lstrip("#")
        t = re.sub(r"\s+", "", t)
        t = re.sub(r"[、。,.!！?？…·・/|]+", "", t)
        core = t.lstrip("#")
        if not core or len(core) > 20:      # 태그다운 길이만(문장 배제)
            continue
        if t not in out:
            out.append(t)
    return out[:limit]


def _fallback_title_jp(chunks: list[str], source_topic: str = "") -> str:
    """LLM 미가용 시 결정론 제목(A안 폴백 · 날조 없음).

    ★실사고: 예전 폴백은 '첫 문장을 절 단위로 누적'이라 밋밋하고 내용 예측이 안 됐다
    (「私たちはちょうど、ある海域のマッピングを終え…」). → 대본/출처에 **문자 그대로 등장하는** 사실
    (수심 水深○m·주역 대상어)만으로 후킹형 사실 템플릿을 만든다. 없으면 가장 구체적인(수치·주역이 든)
    절을 골라 쓰고, 그것도 없으면 기존 절 누적으로 폴백. ★대본에 없는 사실·수치는 절대 만들지 않는다."""
    joined = "。".join(c.strip("。.、,") for c in chunks if c and c.strip())
    corpus = (joined + "。" + (source_topic or "")).strip()
    first = (chunks[0] if chunks else "").strip() or "海の映像"

    # ① 대본/출처에 실제로 있는 수심(水深○○m) → 【深海】+주역+水深○mの記録
    depth = ""
    m = re.search(r"水深[^\d]{0,4}([0-9,]{2,6})\s*(?:m|メートル|ｍ)", corpus)
    if m:
        depth = m.group(1).replace(",", "")
    # 주역(대상) 후보: 대본에 등장하는 생물명(문자 그대로). ★수심이 있으면 그 수심이 언급된 절 안에서
    #   먼저 찾는다(엉뚱한 공정어 'マッピング' 등이 주역으로 뽑히던 문제 방지). 없으면 전체에서.
    _SUBJ_RE = r"([ァ-ヴ]{2,}(?:イカ|タコ|クラゲ|エビ|カニ|ザメ|ウナギ|ナマコ|ヒトデ|ダラ|ウオ|フグ|アンコウ|ダコ)|[ァ-ヴー]{3,}|[一-龠]{2,4}(?:イカ|タコ|クラゲ|エビ|カニ|ザメ|ウナギ|ナマコ|ヒトデ|魚|貝))"
    subj = ""
    if depth:
        for sent in re.split(r"(?<=[。\n])", corpus):   # 문장(。) 단위 — 같은 문장 안의 생물명 우선
            if "水深" in sent:
                sm2 = re.search(_SUBJ_RE, re.sub(r"水深[^\d]{0,4}[0-9,]{2,6}\s*(?:m|メートル|ｍ)", "", sent))
                if sm2:
                    subj = sm2.group(1)
                    break
    if not subj:
        sm = re.search(_SUBJ_RE, corpus)
        if sm:
            subj = sm.group(1)
    if depth:
        head = f"【深海】{subj}" if subj else "【深海】"
        cand = f"{head} 水深{depth}mの記録"
        if len(cand) <= 30:
            return cand

    # ② 수치·주역이 든 '가장 구체적인 절'을 제목으로(문자 그대로, 30자 이내)
    parts = [p.strip("、。 ") for p in re.split(r"(?<=[、。])", joined) if p.strip()]
    scored = []
    for p in parts:
        if not p or len(p) > 30:
            continue
        score = len(re.findall(r"[0-9]", p)) * 3 + (2 if subj and subj in p else 0)
        # 一人称の状況説明(私たち…)より、対象・現象を述べる절を優先(감점)
        if re.search(r"^(私|僕|我々|私たち)", p):
            score -= 2
        if score > 0:
            scored.append((score, p))
    if scored:
        scored.sort(key=lambda x: (-x[0], len(x[1])))
        return scored[0][1]

    # ③ 최후: 첫 문장을 절 단위로 누적(기존 동작 · 말줄임/중간절단 없음)
    title = ""
    for p in [q for q in re.split(r"(?<=[、。])", first) if q.strip()]:
        if len(title + p) > 30:
            break
        title += p
    return re.sub(r"[、。]+$", "", title) or _trim_jp(first, 30)


# 대본에 이 단서가 있으면 붙이는 발견형 광범위 태그(내용 일치할 때만 · 날조 아님)
_TOPIC_TAGS_JP = [
    (r"深海|海底|水深|abyss|deep.?sea", ["#深海", "#深海生物", "#海洋生物"]),
    (r"クラゲ|水母", ["#クラゲ"]),
    (r"イカ|烏賊|タコ|蛸", ["#頭足類"]),
    (r"サメ|鮫", ["#サメ"]),
    (r"魚|ウオ|フィッシュ", ["#魚"]),
    (r"沈没|難破|沈船|shipwreck|wreck", ["#沈没船", "#難破船"]),
    (r"海|ocean|sea|マリン", ["#海", "#海洋生物"]),
    (r"珊瑚|サンゴ", ["#サンゴ"]),
]
_TOPIC_TAGS_KO = {
    "#深海": "#심해", "#深海生物": "#심해생물", "#海洋生物": "#해양생물", "#クラゲ": "#해파리",
    "#頭足類": "#두족류", "#サメ": "#상어", "#魚": "#물고기", "#沈没船": "#침몰선",
    "#難破船": "#난파선", "#海": "#바다", "#サンゴ": "#산호",
}


def _fallback_tags(chunks: list[str], source_topic: str) -> tuple[list[str], list[str]]:
    """LLM 미가용 시 대본·출처에서 내용 기반 해시태그(일/한) 도출(날조 없음).
    ★실사고: 폴백이 항상 '#海 #自然 #癒し' 3개뿐 → 검색 노출 약함. 대본에 실제로 있는 대상어·주제
    단서로 태그를 넓힌다(내용과 일치하는 단서만 채택)."""
    corpus = ("。".join(c for c in chunks if c) + " " + (source_topic or "")).lower()
    tags_jp: list[str] = []
    for pat, tags in _TOPIC_TAGS_JP:
        if re.search(pat, corpus, re.I):
            tags_jp.extend(tags)
    # 대본에 등장하는 생물명(카타카나 고유명)도 태그로(문자 그대로 · 짧은 이름 ソコダラ 등 포함)
    for m in re.findall(r"[ァ-ヴ]{2,}(?:イカ|タコ|クラゲ|エビ|カニ|ザメ|ダラ|ウオ|フグ|アンコウ|ダコ|ウニ|ナマコ)", corpus):
        tags_jp.append("#" + m)
    if not tags_jp:
        tags_jp = ["#海", "#海洋生物", "#自然"]
    tags_jp = _dedup_tags(tags_jp, [])
    tags_ko = _dedup_tags([_TOPIC_TAGS_KO.get(t, "") for t in tags_jp if _TOPIC_TAGS_KO.get(t)],
                          []) or ["#바다", "#해양생물", "#자연"]
    return tags_jp, tags_ko


def _fallback_meta(chunks: list[str], mode: str, source_topic: str = "") -> dict:
    """LLM 미가용 시 대본에서 결정론으로 제목·설명·해시태그(일/한) 도출(날조 없음)."""
    body = "。".join(c.strip("。.、,") for c in chunks[:4] if c.strip())
    first = (chunks[0] if chunks else "").strip() or "海の映像"
    title_jp = _fallback_title_jp(chunks, source_topic)
    desc_jp = (body[:180] + "。") if body else "海の映像に日本語ナレーションと字幕を付けた作品です。"
    hook_jp = _trim_jp(re.sub(r"[。.！!？?]+$", "", first), 18) or "この光景を、ご存知ですか"
    tags_jp, tags_ko = _fallback_tags(chunks, source_topic)
    return {
        "title_jp": title_jp, "title_ko": "",
        "desc_jp": desc_jp, "desc_ko": "",
        "hook_jp": hook_jp,
        "tags_jp": tags_jp,
        "tags_ko": tags_ko,
    }


def _gen_metadata(chunks: list[str], mode: str, source_topic: str = "") -> dict:
    """완성된 일본어 나레이션(대본)으로부터 제목·설명·해시태그를 일본어+한국어로 생성.
    ★운영자 요청: 입력 없이 대본을 근거로 자동 생성(수치·사실은 대본 범위 내). LLM 실패 시 결정론 폴백.

    ★제목 도출 고도화(A안 · 운영자 확정 · 실사고: 롱폼 제목이 후킹·내용예측 실패):
    예전 프롬프트는 '本文を要約' 수준이라 화자가 말한 대로 밋밋한 제목이 나왔다(예: 「私たちはちょうど、
    ある海域のマッピングを終え…」 — 무엇의 영상인지·볼거리·시청 이유가 전무). → **한 번의 LLM 호출 안에서**
    ① 대본 전체를 종합해 ② 시청자에게 가장 강한 '피사체 + 사실/미스터리' 하나를 먼저 뽑고 ③ 검증된 일본어
    유튜브 제목 공식으로 후보 5개를 만든 뒤 ④ 스스로 채점해 가장 내용예측·후킹이 강한 하나를 고르게 한다.
    ★날조 금지는 그대로: 대본(+소싱 출처)에 있는 사실·수치·고유명사만 사용."""
    from src.core import llm
    script = "\n".join(c for c in chunks if c and c.strip())
    topic = (source_topic or "").strip()
    kind = "YouTubeショート(縦型)" if mode == "shorts" else "YouTube長編(横型)"
    src_block = (f"【素材の出典説明(参考・事実根拠)】\n{topic[:600]}\n\n" if topic else "")
    prompt = (
        "あなたはチャンネル登録者を伸ばすプロの動画編集者兼サムネ・タイトル設計者です。"
        f"以下は完成した日本語ナレーション(字幕本文)です。この{kind}動画の公開用メタデータ、"
        "特に『クリックされるタイトル』を設計してください。\n\n"
        f"{src_block}"
        f"【ナレーション(台本全体)】\n{script}\n\n"
        "■ タイトル設計の手順(頭の中で実行し、最終結果だけをJSONで出す):\n"
        "1) 台本全体を通読し、要約ではなく『この動画で最も視聴者の興味を引く一点』"
        "(=主役の対象+意外な事実 or 謎 or 見どころ)を1つだけ特定する。\n"
        "2) その一点を核に、実証済みの日本語YouTubeタイトル公式で候補を5つ作る:"
        "(a)【対象名】+具体的な事実/数値、(b)好奇心ギャップの問いかけ(答えは動画内)、"
        "(c)意外性・衝撃(「実は〜」)、(d)断定+具体、(e)対象名を先頭に置く。\n"
        "3) 5候補を『内容が予測できるか/続きが気になるか/釣りすぎ(誇張)ないか/30字以内か/"
        "台本の事実に忠実か』で自己採点し、最も強い1つを選ぶ。\n"
        "4) ハッシュタグは台本の内容から視聴者を集められるSEOタグを日本語で8〜12個作る:"
        "(a)対象・主役の具体名(種名・生き物名など台本に出るもの)、"
        "(b)発見・検索されやすい広めのタグ(例:深海・海洋生物・生き物・自然・野生動物・水中映像・"
        "ドキュメンタリー・神秘 など、映像内容に合うものだけ)、(c)形式タグ。"
        "各タグは#付き・空白なし・短く(1タグ=1語句)。文章をタグにしない。無関係・意味不明・"
        "誇張(怪物/UMA等)タグは禁止。★台本(と出典)に無い固有名詞・事実は作らない。\n"
        "★制約: 本文(と出典)にない事実・数値・固有名詞は創作しない。UMA・怪物・宇宙人など事実歪曲は禁止"
        "(比喩や問いかけは可)。抽象的な釣り文句だけ・意味のない問いかけだけのタイトルは不可。\n\n"
        "次のJSONだけを出力(説明・記号・前置きなし):\n"
        '{\"subject\":\"台本の主役(対象)を短く\",'
        '\"key_point\":\"最も引きの強い一点を一文で(内部用)\",'
        '\"title_candidates\":[\"候補1\",\"候補2\",\"候補3\",\"候補4\",\"候補5\"],'
        '\"title_jp\":\"最終タイトル(30字以内・上記で選んだ最良の1つ。視聴者が何の映像で何が見られるかを予測でき、続きが気になるもの)\",'
        '\"title_ko\":\"上の最終タイトルの自然な韓国語訳\",'
        '\"hook_jp\":\"12〜18字の強いオープニングフック(冒頭2秒で指を止める一言・体言止め/問いかけ可)。★タイトルと同じ文言の使い回しは禁止(別表現)\",'
        '\"desc_jp\":\"日本語の説明文(2〜4文・敬体)\",'
        '\"desc_ko\":\"上の説明の自然な韓国語訳\",'
        '\"tags_jp\":[\"#具体タグ\",\"#広めのタグ\",\"…8〜12個\"],'
        '\"tags_ko\":[\"#한국어태그\",\"…8〜12個\"]}')
    # ★일시 오류로 폴백(잘린 제목·빈 한국어)이 발행되는 걸 줄이기 위해 실패 시 1회 재시도.
    #   후보 5개+자기채점을 담아 max_tokens 상향(900).
    raw = llm.generate_text(prompt, max_tokens=900) or llm.generate_text(prompt, max_tokens=900)
    if raw:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                tj = _dedup_tags(d.get("tags_jp") or [], [])
                tk = _dedup_tags(d.get("tags_ko") or [], [])
                hook = _trim_jp(re.sub(r"[。.！!？?]*$", "", str(d.get("hook_jp", "")).strip()), 22)
                # 최종 제목이 비었으면 후보 중 첫 유효안으로 보강(자기채점이 빠져도 후보는 활용)
                title = str(d.get("title_jp", "")).strip()
                if not title:
                    for c in (d.get("title_candidates") or []):
                        if str(c).strip():
                            title = str(c).strip()
                            break
                out = {
                    "hook_jp": hook,
                    "title_jp": title,
                    "title_ko": str(d.get("title_ko", "")).strip(),
                    "desc_jp": str(d.get("desc_jp", "")).strip(),
                    "desc_ko": str(d.get("desc_ko", "")).strip(),
                    "tags_jp": tj, "tags_ko": tk,
                }
                if out["title_jp"] and out["desc_jp"] and out["tags_jp"]:
                    if not out["hook_jp"]:
                        out["hook_jp"] = _fallback_meta(chunks, mode, source_topic)["hook_jp"]
                    return _fill_missing_ko(out)
            except Exception:  # noqa: BLE001
                pass
    return _fill_missing_ko(_fallback_meta(chunks, mode, source_topic))


def _fill_missing_ko(meta: dict) -> dict:
    """제목·설명 한국어 번역이 비어 있으면 소형 LLM 호출로 채운다(실사고: 제목·한국어 빈칸).
    본 생성 호출이 실패(폴백)했어도 번역만 따로 재시도 — 그래도 실패하면 빈 채 유지(발행 불정지)."""
    from src.core import llm
    need = [k for k, src in (("title_ko", "title_jp"), ("desc_ko", "desc_jp"))
            if not str(meta.get(k, "")).strip() and str(meta.get(src, "")).strip()]
    if not need:
        return meta
    try:
        src_txt = "\n---\n".join(str(meta.get({"title_ko": "title_jp", "desc_ko": "desc_jp"}[k], "")) for k in need)
        txt = llm.generate_text(
            "次の日本語を自然な韓国語に翻訳してください。項目は '---' で区切られています。"
            "訳文のみを同じ順序で '---' 区切りで出力(説明・記号なし)。\n" + src_txt, max_tokens=600)
        if txt:
            parts = [p.strip() for p in txt.split("---")]
            for k, v in zip(need, parts):
                if v:
                    meta[k] = v
    except Exception:  # noqa: BLE001
        pass
    return meta


def _normalize_landscape(video: str, out: str, dur: float, work_dir: str) -> str:
    """롱폼(16:9): 소스를 1920×1080에 **cover**(잘라 채움)로 맞추고 dur 길이로 만든다(레터박스 없음).
    소스가 짧으면 -stream_loop로 채운다. 무음(나레이션은 뒤에서 mux)."""
    src = _probe_dur(video) or dur
    loop = ["-stream_loop", "-1"] if src < dur - 0.1 else []
    vf = (f"scale={LONG_W}:{LONG_H}:force_original_aspect_ratio=increase,"
          f"crop={LONG_W}:{LONG_H},setsar=1,fps=30,format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *loop, "-i", video,
                    "-t", f"{dur:.2f}", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-an", out], check=True, timeout=900)
    return out


# ─────────────────────── 오프닝 훅(타이틀 카드) + 유튜브 썸네일 ───────────────────────
def _pick_hero_frame(video: str, work: Path, w: int, subject_hint: str = "") -> str:
    """영상에서 '피사체(생물)가 또렷하게 나온' 프레임을 골라 오프닝 훅·썸네일 배경용으로 돌려준다.
    실패 시 ''(호출부가 훅 생략).

    ★재발방지(실사고 · ソコダラ 등 오프닝훅에 빈 바다만 나옴): 예전엔 밝기 표준편차(stddev)만으로 5개
    프레임 중 골라, **질감 많은 빈 모래 바닥이 어두운 물고기보다 높은 점수**를 받아 빈 바다가 표지가 됐다.
    → 릴스 경로와 **동일한 Gemini 우선 선택기**(`hook_intro_stage._score_best_frame`: 촘촘한 20프레임을
    Gemini가 직접 보고 피사체 프레임 선택, 키 없으면 움직임 기반 폴백)로 통일한다. 이 함수는 비전을
    쓰지 않던 유일한 구멍이었다. 실패 시에만 옛 stddev 방식으로 마지막 폴백."""
    dur = _probe_dur(video) or 0.0
    if dur <= 0:
        return ""
    work.mkdir(parents=True, exist_ok=True)
    # ★릴스와 동일한 Gemini 우선 피사체 프레임 선택(빈 바다 회피). 반환은 원본 해상도 프레임(cover_crop이 리사이즈).
    try:
        from src.core import hook_intro_stage as his
        best, _score = his._score_best_frame(video, work, hint=subject_hint, n_samples=24)
        if best and Path(best).exists() and Path(best).stat().st_size > 1000:
            return best
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 히어로 프레임 비전 선택 실패 → stddev 폴백: %s", e)
    # 마지막 폴백(비전·릴스경로 모두 실패): 옛 밝기 표준편차 방식
    try:
        from PIL import Image, ImageStat
    except Exception:  # noqa: BLE001
        return ""
    n = 5
    best_t, best_s = dur * 0.5, -1.0
    for i in range(n):
        t = dur * (i + 0.5) / n
        p = work / f"s_{i}.jpg"
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
                            "-frames:v", "1", "-vf", "scale=160:-1", str(p)], check=True, timeout=60)
            s = ImageStat.Stat(Image.open(p).convert("L")).stddev[0]
        except Exception:  # noqa: BLE001
            s = 0.0
        if s > best_s:
            best_s, best_t = s, t
    hero = work / "hero.jpg"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{best_t:.2f}", "-i", video,
                        "-frames:v", "1", "-vf", f"scale={w}:-1", str(hero)], check=True, timeout=60)
        return str(hero) if hero.exists() and hero.stat().st_size > 1000 else ""
    except Exception:  # noqa: BLE001
        return ""


def _cover_crop(im, w: int, h: int):
    from PIL import Image
    iw, ih = im.size
    sc = max(w / iw, h / ih)
    nw, nh = max(1, int(iw * sc + 0.5)), max(1, int(ih * sc + 0.5))
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return im.crop((x, y, x + w, y + h))


# 일본어 '단어(문자종 런)' 토크나이저 — 가타카나/한자/히라가나/영숫자 런을 한 덩어리로 취급
_JP_TOK_RE = re.compile(r"[ァ-ヶヴー]+|[一-龯々〆]+|[ぁ-ゖ]+|[A-Za-z0-9]+|[０-９Ａ-Ｚａ-ｚ]+|\n|.")
# 행두 금칙(금속처리): 이 문자로 줄을 시작하지 않는다 → 앞 토큰에 붙임
_KINSOKU_HEAD = set("、。，,！!？?…・ー」』）)]｝}〟”’")


def _wrap_cjk(draw, text: str, font, max_w: float) -> list[str]:
    """일본어를 **단어(문자종 런) 단위**로 폭에 맞춰 줄바꿈 + 행두 금칙(넘침 방지 하드룰).

    ★실사고(운영자 지적): 글자 단위 줄바꿈이 'ちょうど'를 'ちょう/ど', 'マッピング'을 중간에서
    쪼갰다 → 가타카나·한자·히라가나·영숫자 '런'을 한 덩어리(단어)로 묶어 그 경계에서만 줄을 바꾼다.
    구두점(、。 등)은 앞 단어에 붙여 행두에 오지 않게 한다. 한 단어가 폭보다 길 때만 글자 분할."""
    toks: list[str] = []
    for m in _JP_TOK_RE.finditer(str(text)):
        t = m.group(0)
        if t != "\n" and toks and toks[-1] != "\n" and t and t[0] in _KINSOKU_HEAD:
            toks[-1] += t                      # 구두점류는 앞 단어에 부착(행두 금칙)
        else:
            toks.append(t)
    lines, cur = [], ""
    for t in toks:
        if t == "\n":
            lines.append(cur); cur = ""; continue
        if not cur or draw.textlength(cur + t, font=font) <= max_w:
            cur += t
            continue
        if draw.textlength(t, font=font) <= max_w:
            lines.append(cur); cur = t         # 단어째 다음 줄로
            continue
        # 단어 자체가 한 줄보다 긺 → 그 단어만 글자 분할(최후 수단)
        for ch in t:
            if not cur or draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                lines.append(cur); cur = ch
    if cur:
        lines.append(cur)
    return lines


def _fit_block(draw, text: str, max_w: float, max_lines: int, base: int, minsz: int):
    from PIL import ImageFont
    from src.core import hook_intro as hi
    size = base
    while size >= minsz:
        font = ImageFont.truetype(hi.FONT_SANS_B, size, index=0)
        lines = _wrap_cjk(draw, text, font, max_w)
        if len(lines) <= max_lines:
            return font, lines
        size -= 4
    font = ImageFont.truetype(hi.FONT_SANS_B, minsz, index=0)
    return font, _wrap_cjk(draw, text, font, max_w)


_ACCENT = (245, 197, 66)     # 골드 포인트
_INK = (10, 16, 24)          # 딥 네이비 잉크(패널·그림자)


def _vignette(im, strength: float = 0.62):
    """가장자리를 어둡게(라디얼 비네트) — 시선을 중앙 훅으로 모은다. 순수 PIL(넘파이 불필요)."""
    from PIL import Image
    w, h = im.size
    sw, sh = 96, int(96 * h / w) or 54
    mask = Image.new("L", (sw, sh), 0)
    px = mask.load()
    cx, cy = (sw - 1) / 2, (sh - 1) / 2
    maxd = (cx ** 2 + cy ** 2) ** 0.5
    for yy in range(sh):
        for xx in range(sw):
            d = ((xx - cx) ** 2 + (yy - cy) ** 2) ** 0.5 / maxd
            v = max(0.0, (d - 0.45) / 0.55) ** 1.4
            px[xx, yy] = int(255 * min(1.0, v) * strength)
    mask = mask.resize((w, h), Image.BILINEAR)
    return Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), im, mask)


def _shadow_text(im, xy, text, font, *, blur: int = 10, grow: int = 3):
    """부드러운 드롭섀도(블러) 레이어를 얹어 텍스트에 입체감·가독성을 준다."""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = im.size
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((xy[0], xy[1] + grow), text, font=font, fill=(0, 0, 0, 210),
                             stroke_width=grow, stroke_fill=(0, 0, 0, 210))
    lay = lay.filter(ImageFilter.GaussianBlur(blur))
    im.paste(lay, (0, 0), lay)


_CREAM = (244, 240, 232)     # 코너 브래킷·필 배경(따뜻한 화이트)


def _corner_brackets(d, w: int, h: int, color, alpha: int = 235):
    """네 모서리에 얇은 L자 코너 브래킷(레퍼런스 썸네일 양식). 정제된 프레임 악센트."""
    m = int(min(w, h) * 0.045)
    arm = int(min(w, h) * 0.075)
    t = max(3, int(min(w, h) * 0.006))
    col = color + (alpha,) if len(color) == 3 else color
    for cx, cy, sx, sy in [(m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)]:
        d.line([(cx, cy), (cx + sx * arm, cy)], fill=col, width=t)
        d.line([(cx, cy), (cx, cy + sy * arm)], fill=col, width=t)


def _pill(im, x: int, y: int, text: str, fontsize: int) -> int:
    """딥네이비 라운드 '필' 태그(ROV HUD 톤 · 골드 테두리 + 화이트 텍스트). 반환: 필 높이.
    ★프레임 이탈 금지(운영자 확정 · 실사고: 칩이 썸네일 하단 밖으로 삐져나감): 어떤 입력에서도
    칩 전체가 캔버스 안에 있도록 ① y를 하단 여백 안으로 클램프 ② 텍스트가 길면 말줄임(…)으로
    가로 폭을 맞춘다. 다시는 박스가 프레임 밖으로 나가지 않는다."""
    from PIL import ImageDraw, ImageFont
    from src.core import hook_intro as hi
    W_, H_ = im.size
    d = ImageDraw.Draw(im, "RGBA")
    f = ImageFont.truetype(hi.FONT_SANS_B, fontsize, index=0)
    asc = f.getbbox("あ")[3]
    padx, pady = int(fontsize * 0.6), int(fontsize * 0.42)
    margin = max(8, int(H_ * 0.030))
    # ② 가로: 캔버스 안에 들어갈 때까지 말줄임
    max_rw = W_ - x - margin
    t = str(text)
    while t and int(d.textlength(t + ("…" if t != text else ""), font=f) + 2 * padx) > max_rw:
        t = t[:-1]
    if not t:
        return 0
    if t != text:
        t += "…"
    tw = d.textlength(t, font=f)
    rw, rh = int(tw + 2 * padx), int(asc + 2 * pady)
    # ① 세로: 하단 여백 안으로 클램프(코너 브래킷 영역 침범 최소화)
    y = max(margin, min(y, H_ - margin - rh))
    d.rounded_rectangle([x, y, x + rw, y + rh], radius=int(rh * 0.26),
                        fill=(12, 20, 34, 235), outline=_ACCENT + (220,),
                        width=max(2, int(fontsize * 0.07)))
    d.text((x + padx, y + pady - int(fontsize * 0.06)), t, font=f, fill=(245, 244, 240))
    return rh


def _trim_jp(text: str, maxn: int) -> str:
    """일본어 문구를 maxn자 이내로 줄이되 **단어 중간이 아닌 구두점 경계**에서 자른다.
    ★실사고(운영자 지적): 훅이 'マッピング'의 중간('マッピン')에서 잘려 어색 → 한도 안의 마지막
    구두점(、。・)까지로 줄이고, 구두점이 없으면 그때만 글자수로 자른다. 끝 구두점은 제거."""
    t = (text or "").strip()
    if len(t) <= maxn:
        return re.sub(r"[、。，,]+$", "", t)
    cut = t[:maxn]
    m = max(cut.rfind("、"), cut.rfind("。"), cut.rfind("・"))
    if m >= max(6, maxn // 3):                 # 너무 앞이면(내용 소실) 구두점 컷 포기
        cut = cut[:m]
    return re.sub(r"[、。，,]+$", "", cut)


def _kicker_text(hook: str, title: str) -> str:
    """썸네일 필(작은 칩) 문구 — 제목에서 추출하되 **큰 글씨(훅)와 중복·유사면 배제**.

    ★실사고 2건(운영자 지적): ① 같은 문구가 큰 글씨와 칩에 그대로 ② 포함관계는 아니지만
    사실상 같은 문장(훅=제목 앞 22자 절단본)이 칩에 들어감 → 포함 검사에 더해
    **유사도(SequenceMatcher ≥0.5) 검사**로 '거의 같은' 조각도 배제. 전부 중복이면 ''(칩 생략)."""
    from difflib import SequenceMatcher
    hook_n = re.sub(r"\s+", "", (hook or ""))
    for seg in re.split(r"[、。，,・|/\n]", (title or "").strip()):
        seg = seg.strip()[:16]
        seg_n = re.sub(r"\s+", "", seg)
        if not seg_n:
            continue
        if hook_n and (seg_n in hook_n or hook_n in seg_n):
            continue
        if hook_n and SequenceMatcher(None, seg_n, hook_n).ratio() >= 0.5:
            continue
        return seg
    return ""


def _gradient_glow_lines(im, x0: int, y0: int, lines: list[str], font, line_h: int, h: int):
    """세로 그라디언트(시안→핑크) + 소프트 글로우 타이틀(쇼츠 오프닝 HUD와 동일 룩). 순수 PIL.
    글자 마스크를 만들어 ① 옅은 블루 글로우를 깔고 ② 블록 세로 그라디언트로 채운다."""
    from PIL import Image, ImageDraw, ImageFilter
    W, H = im.size
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    yy = y0
    for ln in lines:
        md.text((x0, yy), ln, font=font, fill=255,
                stroke_width=max(2, int(h * 0.0022)), stroke_fill=255)
        yy += line_h
    block_h = max(1, yy - y0)
    # ① 글로우(옅은 블루) — 넓게 블러한 마스크로 은은한 발광
    glow = mask.filter(ImageFilter.GaussianBlur(max(6, int(h * 0.014))))
    im.paste(Image.new("RGB", (W, H), (110, 170, 255)), (0, 0),
             glow.point(lambda v: int(v * 0.55)))
    # ② 본문: 시안(#9FD3FF) → 핑크(#F79ADF) 세로 그라디언트
    top, bot = (159, 211, 255), (247, 154, 223)
    grad = Image.new("RGB", (1, block_h))
    for i in range(block_h):
        t = i / (block_h - 1) if block_h > 1 else 0.0
        grad.putpixel((0, i), tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
    full = Image.new("RGB", (W, H), top)
    full.paste(grad.resize((W, block_h)), (0, y0))
    im.paste(full, (0, 0), mask)
    return yy


def _hook_lines(hook: str) -> tuple[str, str, list[str]]:
    """훅 한 문장 → 오프닝 애니메이션용 (1행, 2행, 팝인 어절 리스트).

    도감형은 카테고리 COPY에 어절이 손으로 적혀 있지만, 나레이션형은 훅을 LLM이 만들므로
    여기서 쪼갠다. 일본어 읽기 단위인 「、」·「。」 를 우선 경계로 삼고, 없으면 길이 기준으로
    자연스러운 두 덩어리로 나눈다(단어 중간 줄바꿈 금지 — 화면 조판 하드룰 #7).
    """
    h = re.sub(r"\s+", "", (hook or "").strip())
    if not h:
        return "", "", []
    # ① 구두점 경계로 분할(구두점은 앞 조각에 붙인다 — 읽기 흐름 유지)
    parts = [p for p in re.split(r"(?<=[、。！？])", h) if p]
    if len(parts) == 1 and len(h) > 9:
        # ② 구두점이 없으면 중간 지점의 조사/접속 뒤에서 끊는다(없으면 정중앙)
        mid = len(h) // 2
        cut = mid
        for off in range(0, 4):
            for c in (mid + off, mid - off):
                if 3 <= c < len(h) - 2 and h[c - 1] in "はがをにでとへもの":
                    cut = c
                    break
            else:
                continue
            break
        parts = [h[:cut], h[cut:]]
    parts = [p for p in parts if p][:3]
    line1 = parts[0]
    line2 = "".join(parts[1:])
    return line1, line2, list(parts)


def _apply_opening_hook(body_video: str, hook: str, work: Path, hero_image: str = "",
                        open_bg_video: str = "", subject_video: str = "",
                        cover_spec: dict | None = None) -> str:
    """★쇼츠 오프닝 훅(운영자 확정): 도감형과 **같은 애니메이션 훅**을 본문 앞에 붙인다.

    도감형(reels)의 `hook_intro_stage`를 그대로 재사용한다 — 어절이 순서대로 팝인 + 훅 나레이션
    (edge-tts) + 스캔/임팩트 사운드. 나레이션형은 종 정보(국명·학명·수심)가 없으므로
    **수심 스케일과 엔드카드는 끄고**(`show_scale=False` / `include_endcard=False`) 훅만 쓴다.
    실패하면 원본 본문을 그대로 돌려준다(발행 불정지).
    """
    line1, line2, pops = _hook_lines(hook)
    if not pops:
        return body_video
    try:
        from src.core import hook_intro as hi, hook_intro_stage
        spec = hi.SpeciesSpec(
            jp_name="", sci_name="", depth_min=0, depth_max=0,
            hook_line1=line1, hook_line2=line2, hook_pop_words=pops,
            feature_line="", feature_glow_word="",
            corner_label="DEEP SEA · ROV CAM", scale_label="", show_scale=False)
        out = hook_intro_stage.apply(body_video, spec, hook, str(work / "open"),
                                     open_bg_video=(open_bg_video or None),
                                     subject_video=(subject_video or None),
                                     hero_image=(hero_image or None),
                                     include_endcard=False, cover_spec=cover_spec)
        if out and out != body_video and Path(out).exists():
            log.info("[narrate] 오프닝 훅 적용: %r (%d어절)", hook, len(pops))
            return out
        log.warning("[narrate] 오프닝 훅 생성 실패 → 본문 그대로")
    except Exception as e:  # noqa: BLE001
        log.warning("[narrate] 오프닝 훅 생략(오류): %s", e)
    return body_video


def _render_hook_and_thumb(bg_path: str, hook: str, title: str, w: int, h: int,
                           card_png: str, thumb_png: str) -> bool:
    """훅 문구를 배경(피사체 프레임) 위에 얹어 ① 오프닝 카드 ② 유튜브 썸네일을 만든다.
    ★우주선/ROV HUD 양식(운영자 확정 · 쇼츠 오프닝과 브랜드 통일): 네 모서리 코너 브래킷 +
    상단 모노 HUD 라벨(DEEP SEA · ROV CAM / REC · DIVE LOG + 벡터 레드닷) + 전체 딤·비네트 +
    대형 그라디언트(시안→핑크) 글로우 타이틀. 썸네일에는 딥네이비 필 킥커(★훅과 중복 문구 배제 —
    `_kicker_text`가 제목의 '내용 예고' 조각을 고름).
    ★이모지·시스템 아이콘 금지(하드룰) — 텍스트+벡터 도형만. 실패 시 False(훅 생략)."""
    try:
        from PIL import Image, ImageDraw, ImageEnhance, ImageFont
        from src.core import hook_intro as hi
        base = Image.open(bg_path).convert("RGB")
        bg = _cover_crop(base, w, h)
        bg = ImageEnhance.Contrast(bg).enhance(1.08)
        bg = ImageEnhance.Color(bg).enhance(1.06)
        # 전체 딤(HUD 톤) + 비네트 — 어두운 심해 계기판 위에 발광 텍스트가 뜨는 룩
        dark = Image.blend(bg, Image.new("RGB", (w, h), (3, 8, 16)), 0.42)
        dark = _vignette(dark, strength=0.55)

        x0 = int(w * 0.058)                       # 좌측 텍스트 컬럼 시작
        col_w = int(w * 0.62)                     # 타이틀 컬럼 폭

        def _compose(with_pill: bool):
            im = dark.copy()
            d = ImageDraw.Draw(im, "RGBA")
            _corner_brackets(d, w, h, _CREAM, 220)
            # 상단 HUD 라벨(모노): 좌 = 채널 시그니처 · 우 = REC 레드닷(벡터) + DIVE LOG
            mono = ImageFont.truetype(hi.FONT_MONO, max(14, int(h * 0.030)))
            ly = int(h * 0.072)
            d.text((x0, ly), "DEEP SEA · ROV CAM", font=mono, fill=(198, 219, 240, 225))
            rtxt = "REC · DIVE LOG"
            rw_ = d.textlength(rtxt, font=mono)
            rx = w - x0 - int(rw_)
            rr = max(4, int(h * 0.009))
            d.ellipse([rx - rr * 3, ly + rr * 0.6, rx - rr, ly + rr * 2.6], fill=(232, 64, 64, 235))
            d.text((rx, ly), rtxt, font=mono, fill=(198, 219, 240, 225))
            # 대형 그라디언트 글로우 타이틀(쇼츠 오프닝 룩)
            font, lines = _fit_block(d, hook, col_w, 3, int(h * 0.150), int(h * 0.064))
            asc = font.getbbox("あ")[3]
            line_h = int(asc * 1.28)
            y = int(h * 0.175)
            y_end = _gradient_glow_lines(im, x0, y, lines, font, line_h, h)
            if with_pill and title:
                kick = _kicker_text(hook, title)   # ★훅(큰 글씨)과 중복이면 다른 조각/생략
                if kick:
                    _pill(im, x0, y_end + int(h * 0.050), kick, int(h * 0.048))
            return im

        _compose(False).convert("RGB").save(card_png, quality=93)      # 오프닝 카드(영상): 훅만
        _compose(True).convert("RGB").save(thumb_png, quality=92)      # 썸네일: 훅 + 필 킥커
        return Path(card_png).exists() and Path(thumb_png).exists()
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 훅/썸네일 렌더 실패(생략): %s", e)
        return False


# ─────────────────────── 롱폼: 원본 전체 길이 유지 + 나레이션 분산 + 타임스탬프 ───────────────────────
def _ts_mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


def _sample_range_frames(video: str, work: Path, t0: float, t1: float, n: int = 3) -> list[str]:
    """구간 [t0,t1)에서 고르게 n장 프레임 추출(비전 분석용). 실패 시 []."""
    work.mkdir(parents=True, exist_ok=True)
    span = max(0.2, t1 - t0)
    out: list[str] = []
    for i in range(n):
        t = t0 + span * (i + 0.5) / n
        fp = work / f"f{i}.jpg"
        try:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
                            "-frames:v", "1", "-vf", "scale=512:-1", str(fp)], check=True, timeout=60)
            if fp.exists() and fp.stat().st_size > 1000:
                out.append(str(fp))
        except Exception:  # noqa: BLE001
            continue
    return out


def _describe_segment(video: str, work: Path, t0: float, t1: float, idx: int) -> str:
    """구간 [t0,t1)의 프레임을 비전 LLM으로 보고 사실 설명(일본어 1~2문). 키 없으면 ''."""
    frames = _sample_range_frames(video, work / f"segf{idx}", t0, t1, 3)
    if not frames:
        return ""
    from src.core import llm
    prompt = ("この複数フレームは1本の動画のある区間から抜いたものです。画面に実際に写るものだけを"
              "日本語1〜2文で簡潔に述べてください。★推測・創作は禁止(写っていない固有名詞・数値は書かない)。説明文のみ。")
    return (llm.describe_frames(frames, prompt, max_tokens=200) or "").strip()


def _jp_segment_chunks(basis: str, idx: int, n_seg: int) -> list[str]:
    """구간 설명(basis)으로 그 구간의 짧은 일본어 나레이션(3~5행)을 만든다. LLM 실패 시 결정론 폴백."""
    from src.core import llm
    basis = (basis or "").strip()
    if not basis:
        return []
    prompt = (
        "あなたは自然・海洋ドキュメンタリーの日本語ナレーターです。次の映像区間の事実説明だけを使い、"
        "落ち着いた敬体(です・ます)で短いナレーションを3〜5行書いてください。事実の創作は禁止——"
        "説明にない固有名詞・数値・断定は書かないこと。1行に日本語で8〜16文字程度。各行は字幕として画面に出ます。\n"
        f"【区間{idx + 1}/{n_seg}の映像説明】{basis}\n"
        "出力は本文のみ。1行1チャンクで、記号や番号は付けないでください。")
    txt = llm.generate_text(prompt, max_tokens=400)
    if txt:
        lines = [re.sub(r"^[\s0-9.\-・*]+", "", ln).strip() for ln in txt.splitlines()]
        lines = [ln for ln in lines if ln and not ln.startswith("【")]
        if lines:
            return lines[:6]
    return _jp_chunks_from_notes("", basis, 6)


def _chapter_title(basis: str, chunks: list[str]) -> str:
    """구간 챕터 제목(짧게). 설명 첫 문장 또는 첫 청크에서 도출(날조 없음)."""
    src = (basis or (chunks[0] if chunks else "")).strip()
    src = re.split(r"[。.\n]", src)[0].strip()
    src = re.sub(r"[、,]+$", "", src)
    return (src[:20] + ("…" if len(src) > 20 else "")) if src else "映像"


def _mix_delayed(parts: list[tuple], total: float, work: Path) -> str:
    """여러 나레이션 mp3를 각자의 앵커 시각에 배치(adelay)해 total 길이 오디오로 합성.
    parts=[(mp3, anchor_s)]. 한 개면 amix 없이 처리. 결과 mp3 경로."""
    out = str(work / "narration_full.mp3")
    inputs: list[str] = []
    fc: list[str] = []
    for k, (mp3, anchor) in enumerate(parts):
        inputs += ["-i", mp3]
        d = max(0, int(anchor * 1000))
        fc.append(f"[{k}]adelay={d}|{d}[a{k}]")
    if len(parts) == 1:
        fc.append(f"[a0]apad,atrim=0:{total:.2f}[a]")
    else:
        labels = "".join(f"[a{k}]" for k in range(len(parts)))
        fc.append(f"{labels}amix=inputs={len(parts)}:normalize=0:dropout_transition=0,apad,atrim=0:{total:.2f}[a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc),
                    "-map", "[a]", "-c:a", "libmp3lame", "-q:a", "4", out], check=True, timeout=600)
    return out


# ★쇼츠 나레이션 분배 상수(운영자 확정 · "문장 사이 간격이 없어 어색하다 / 뒷부분은 무음이다").
_SHORTS_LEAD_S = 0.35      # 첫 문장 전 여유(영상이 먼저 눈에 들어오게)
_SHORTS_TAIL_S = 1.20      # 마지막(구독 유도) 뒤 여운 — 끊긴 느낌 방지
_SHORTS_GAP_MIN = 1.00     # ★문장 사이 최소 쉼(운영자 확정 "무조건 1초 이상") — 절대 회귀 금지
_SHORTS_GAP_MAX = 2.60     # 최대 쉼(더 벌리면 '끊긴 영상'처럼 들린다)
_SHORTS_SUB_HOLD_S = 0.90  # 말이 끝난 뒤 자막이 더 머무는 시간
_SHORTS_MIN_BODY = 2       # 길이 맞추려 문장을 줄일 때 남겨야 할 본문 최소 문장 수
# ★구독 유도(운영자 확정 · 필수): 영상이 끝나기 전에 **자막 + 나레이션으로 반드시** 넣는다.
#   길이 계산에도 이 문장을 먼저 반영한다(본문이 자리를 다 먹어 잘리는 일 방지).
_SHORTS_CTA_JP = "チャンネル登録して、次の深海も。"   # 약 3.5초 — 본문 자리를 덜 뺏는 길이


def _spread_shorts_narration(chunks: list[str], work: Path, target_dur: float,
                             rate: str = _SHORTS_TTS_RATE) -> dict | None:
    """쇼츠 나레이션을 **문장별로 따로 합성해 영상 전체에 고르게 배치**한다.

    왜(실사고): 예전엔 문장을 모두 이어붙여 한 번에 읽혀, ①문장 사이에 쉼이 없어 랩처럼 들리고
    ②영상 30초 중 앞 15초에서 나레이션이 끝나 **뒤는 완전 무음**이었다.
    지금은 문장마다 mp3를 만들고 `_mix_delayed`로 각자의 시각에 배치한다.

    운영자 확정 규칙(3):
      ① 문장 사이는 **무조건 1초 이상**(`_SHORTS_GAP_MIN`) 쉰다. 남는 시간은 문장 길이에 비례해
         더 나눠 갖되 `_SHORTS_GAP_MAX`까지만(더 벌리면 끊긴 영상처럼 들린다).
      ② **영상 길이에 맞춰 나레이션 길이를 조정**한다 — 1초 쉼을 지키며 다 들어가지 않으면 본문
         문장을 줄인다(여는 문장·닫는 문장은 지키고 그 사이를 덜어낸다).
      ③ 영상이 끝나기 전에 **구독 유도(자막+나레이션)를 반드시** 넣고, ②의 계산에 그 길이를
         먼저 반영한다(구독 유도가 잘려 나가는 일이 없도록).

    반환: {mp3, disp, words, duration, chunks(실제로 읽은 본문), spread:True}
          실패하면 None(호출부가 기존 방식으로 폴백).
    """
    from src.core import narration_sync
    if not chunks:
        return None

    def _say(text: str, tag: str) -> dict | None:
        d = work / f"nar_{tag}"
        d.mkdir(parents=True, exist_ok=True)
        try:
            r = narration_sync.synthesize([text], str(d), rate=rate)
        except Exception as e:  # noqa: BLE001
            log.warning("[narrate] 문장 합성 실패(%s) → 분배 취소: %s", tag, e)
            return None
        if not r.get("mp3") or not r.get("disp"):
            return None
        # 실제 mp3 길이(단어 경계는 끝의 여운을 빼먹는다) — 겹침 방지를 위해 더 큰 값을 쓴다.
        r["len"] = max(float(r.get("duration") or 0.0), _probe_dur(r["mp3"]))
        return r if r["len"] > 0 else None

    # ③ 구독 유도부터 합성해 '반드시 들어갈 자리'를 먼저 확보한다.
    cta = _say(_SHORTS_CTA_JP, "cta")
    if not cta:
        return None
    parts: list[dict] = []
    for i, c in enumerate(chunks):
        r = _say(c, f"{i:02d}")
        if not r:
            return None
        parts.append(r)

    # ② 영상 길이에 맞춰 본문 문장 수 조정 — 1초 쉼을 지키며 들어갈 만큼만 남긴다.
    #    (여는 문장과 닫는 문장은 이야기의 처음·끝이라 지키고, 그 사이 문장을 덜어낸다.)
    reserve = _SHORTS_LEAD_S + _SHORTS_TAIL_S + cta["len"] + _SHORTS_GAP_MIN
    kept = list(chunks)                 # parts와 1:1로 함께 줄인다(같은 문장이 겹쳐도 안전)
    dropped: list[str] = []
    while len(parts) > _SHORTS_MIN_BODY:
        need = sum(p["len"] for p in parts) + _SHORTS_GAP_MIN * (len(parts) - 1) + reserve
        if need <= target_dur:
            break
        cut = len(parts) - 2            # 여는 문장·닫는 문장은 지키고 그 앞 문장을 덜어낸다
        dropped.append(kept.pop(cut))
        parts.pop(cut)
    if dropped:
        log.info("[narrate] 영상 %.1fs에 맞춰 본문 %d문장 → %d문장으로 조정(제외: %s)",
                 target_dur, len(chunks), len(parts), " / ".join(dropped))

    # ★구독 유도를 '마지막 문장'으로 넣어 본문과 **같은 규칙**으로 배치한다.
    #   (끝에 못 박아 두면 본문이 짧을 때 그 앞이 4초씩 비어 끊긴 느낌이 났다.)
    parts.append(cta)
    n = len(parts)
    speech = sum(p["len"] for p in parts)
    # ① 쉼: 최소 1초 보장 + 남는 시간은 문장 길이에 비례해 배분(최대 _SHORTS_GAP_MAX)
    usable = max(0.0, target_dur - _SHORTS_LEAD_S - _SHORTS_TAIL_S)
    free = usable - speech
    if n <= 1:
        gaps = []
    elif free / (n - 1) <= _SHORTS_GAP_MIN:
        gaps = [_SHORTS_GAP_MIN] * (n - 1)
    elif free / (n - 1) > _SHORTS_GAP_MAX:
        # ★대본이 짧아 남는 시간이 많은 경우: 상한(_SHORTS_GAP_MAX)을 고집하면 **끝에 몇 초씩 무음**이
        #   남고 구독 유도도 끝에서 멀어진다(운영자가 지적한 그 문제의 재발). 이럴 땐 상한을 풀고
        #   **균등하게 벌려 영상 끝까지 채운다** — 마지막(구독 유도)이 영상 끝에 딱 맞게 놓인다.
        gaps = [free / (n - 1)] * (n - 1)
    else:
        mean = speech / n
        wts = [0.75 + 0.5 * (parts[i]["len"] / mean if mean else 1.0) for i in range(n - 1)]
        tot = sum(wts) or 1.0
        raw = [free * w / tot for w in wts]
        gaps = [max(_SHORTS_GAP_MIN, min(_SHORTS_GAP_MAX, g)) for g in raw]

    # 배치(앵커) 계산 — 본문 → (1초 이상 쉼) → … → 구독 유도 → 여운
    anchors: list[float] = []
    t = _SHORTS_LEAD_S
    for i, p in enumerate(parts):
        anchors.append(t)
        t += p["len"] + (gaps[i] if i < len(gaps) else 0.0)
    cta_at = anchors[-1]
    total = max(target_dur, cta_at + cta["len"] + _SHORTS_TAIL_S)
    try:
        mp3 = _mix_delayed([(p["mp3"], a) for p, a in zip(parts, anchors)], total, work)
    except Exception as e:  # noqa: BLE001
        log.warning("[narrate] 나레이션 배치 합성 실패 → 분배 취소: %s", e)
        return None
    # 자막 창: 각 문장을 자기 발화 시각으로 옮기고, 말이 끝난 뒤 잠깐 더 머문다(다음 문장 전엔 비운다).
    disp: list[tuple] = []
    words: list[tuple] = []
    for i, (p, a) in enumerate(zip(parts, anchors)):
        for txt, st, en in p["disp"]:
            hold = en + _SHORTS_SUB_HOLD_S
            if i + 1 < n:
                hold = min(hold, (anchors[i + 1] - a) - 0.15)
            disp.append((txt, a + st, a + max(en, hold)))
        # 단어 경계(쇼츠 본문에선 쓰지 않지만 진단용으로 함께 옮겨 둔다). 형식이 다르면 건너뛴다.
        for w in p.get("words", []):
            if len(w) >= 3 and isinstance(w[0], (int, float)):
                words.append((a + w[0], w[1], w[2]))
    log.info("[narrate] 쇼츠 나레이션 분배: 본문 %d문장 + 구독유도 · 말 %.1fs / 영상 %.1fs · "
             "쉼 %s초 · 구독유도 %.1f~%.1fs",
             n - 1, speech + cta["len"], total, ", ".join(f"{g:.1f}" for g in gaps),
             cta_at, cta_at + cta["len"])
    return {"mp3": mp3, "disp": disp, "words": words, "duration": total,
            "chunks": kept, "cta": _SHORTS_CTA_JP, "spread": True}


def _has_audio(video: str) -> bool:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                              "stream=codec_type", "-of", "csv=p=0", video],
                             capture_output=True, text=True, timeout=30).stdout
        return "audio" in out
    except Exception:  # noqa: BLE001
        return False


def _audio_active_regions(video: str, dur: float) -> list[tuple]:
    """원본에서 소리가 나는(대개 목소리·행동) 구간 [(start,end)] — silencedetect의 반대.
    ★#2: 나레이션·자막을 '원본이 말하는(소리 나는) 부분'에 맞춰 배치하려는 용도."""
    if not _has_audio(video):
        return []
    try:
        r = subprocess.run(["ffmpeg", "-i", video, "-af", "silencedetect=noise=-30dB:d=0.5",
                            "-f", "null", "-"], capture_output=True, text=True, timeout=240)
    except Exception:  # noqa: BLE001
        return []
    txt = r.stderr or ""
    sil: list[tuple] = []
    cur = None
    for ln in txt.splitlines():
        ms = re.search(r"silence_start:\s*([0-9.]+)", ln)
        me = re.search(r"silence_end:\s*([0-9.]+)", ln)
        if ms:
            cur = float(ms.group(1))
        elif me and cur is not None:
            sil.append((cur, float(me.group(1)))); cur = None
    if cur is not None:
        sil.append((cur, dur))
    active: list[tuple] = []
    t = 0.0
    for s, e in sil:
        if s > t:
            active.append((t, min(s, dur)))
        t = max(t, e)
    if t < dur:
        active.append((t, dur))
    return [(a, b) for a, b in active if b - a >= 0.6]


def _mix_bg_narration(video: str, narration_mp3: str, dur: float, work: Path,
                      bg_audio: str | None = None, bgm: str | None = None) -> str:
    """★#1: 원본 오디오(효과음·배경 보존)를 나레이션 밑으로 '덕킹'하고 나레이션을 더 크게 얹은 최종 오디오.
    - 원본이 무음이면 나레이션만 그대로 반환(현행).
    - 원본 목소리는 배경으로 낮추고(volume 0.8), 나레이션은 키운다(volume 1.8).
    - 나레이션이 울리는 구간엔 사이드체인으로 원본을 더 눌러 나레이션이 확실히 크게 들리게 한다.
    ★저작권 음악 제거(운영자 확정): bg_audio가 오면 원본 오디오 **대신** 그 파일(음악 제거된
    목소리 트랙)을 배경으로 쓰고, bgm이 오면 보유 자체 BGM을 낮게(0.20) 루프로 깔아
    빠진 음악 자리를 채운다(페이드 인/아웃)."""
    src_a = bg_audio if (bg_audio and Path(bg_audio).exists()) else None
    if src_a is None and not _has_audio(video):
        return narration_mp3
    out = str(work / "mixed.m4a")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", (src_a or video), "-i", narration_mp3]
    # ★★나레이션이 끝나면 소리가 통째로 사라지던 실사고(운영자 지적 · 절대 회귀 금지):
    #   `sidechaincompress`는 **사이드체인 신호(나레이션)가 끝나면 출력도 함께 멈춘다.**
    #   그래서 나레이션 15.4초짜리를 20초 영상에 얹으면 15.4초 뒤 배경음까지 사라졌다
    #   (실측: 완성본 오디오 15.95초 vs 영상 20초 — 정확히 나레이션 길이에서 끊김).
    #   → 나레이션을 **무음으로 dur까지 패딩(apad)** 해 사이드체인이 끝까지 살아 있게 한다.
    #   그러면 나레이션 구간엔 원본이 눌리고(덕킹), 나레이션이 없는 구간엔 원본 배경·효과음이
    #   그대로 들린다 — 운영자가 처음 정한 규칙("배경음은 살리고 목소리만 죽인 뒤 더빙")과 일치.
    #   검증(실파일): apad 전 15.4초·이후 무음 → apad 후 20.00초·16~20초 구간 −18.5dB로 배경 생존.
    fc = ("[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo:sample_rates=44100,volume=0.8[bg];"
          "[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo:sample_rates=44100,volume=1.8,"
          f"apad=whole_dur={dur:.2f},asplit=2[vo][vok];"
          "[bg][vok]sidechaincompress=threshold=0.02:ratio=14:attack=15:release=350[bgd];")
    if bgm and Path(bgm).exists():
        cmd += ["-stream_loop", "-1", "-i", bgm]
        fc += (f"[2:a]aformat=sample_fmts=fltp:channel_layouts=stereo:sample_rates=44100,"
               f"atrim=0:{dur:.2f},volume=0.20,afade=t=in:st=0:d=2,"
               f"afade=t=out:st={max(0.0, dur - 3):.2f}:d=3[mus];"
               f"[bgd][vo][mus]amix=inputs=3:normalize=0:duration=longest,alimiter=limit=0.97[a]")
    else:
        fc += "[bgd][vo]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.97[a]"
    try:
        subprocess.run(cmd + ["-filter_complex", fc, "-map", "[a]", "-t", f"{dur:.2f}",
                              "-c:a", "aac", "-b:a", "192k", out], check=True, timeout=600)
        return out if Path(out).exists() and Path(out).stat().st_size > 2000 else narration_mp3
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 원본+나레이션 믹스 실패 → 나레이션만: %s", e)
        return narration_mp3


def _jp_lines_for_subtitle(jp: str, max_len: int = 18) -> list[str]:
    """일본어 한 덩어리를 자막용 짧은 줄(≈18자)로 분절. 문장부호 우선, 길면 글자수로 자른다."""
    jp = (jp or "").strip()
    if not jp:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[。！？、])", jp) if p.strip()]
    lines: list[str] = []
    for p in parts:
        while len(p) > max_len:
            lines.append(p[:max_len]); p = p[max_len:]
        if p:
            lines.append(p)
    return lines or [jp[:max_len]]


def _translate_segments_jp(segments: list[dict], lang: str = "") -> list[str] | None:
    """전사 문장들을 **한 번의 제미나이 호출**로 일본어 나레이션으로 번역(행수·순서 보존).
    반환: 세그먼트 수만큼의 일본어 리스트(일부 빈 문자열 가능) 또는 None(절반도 못 얻으면 실패).
    ★번역만 제미나이(저렴)·전사는 Whisper — 역할 분담(운영자 확정)."""
    from src.core import llm
    if not segments:
        return None
    src_lines = "\n".join(f"{i + 1}. {s.get('text', '')}" for i, s in enumerate(segments))
    prompt = (
        f"次の各行は動画音声の書き起こし原文です（元言語: {lang or '不明'}）。各行を、自然で落ち着いた"
        "日本語のドキュメンタリー・ナレーション(敬体)に翻訳してください。"
        "★厳守: 入力と同じ行数・同じ順序で、各行の先頭に元の番号を付けて出力する（例: 1. 本文）。"
        "原文の意味を保ち、創作・要約・情報の追加はしない。前置きや説明・記号の装飾は書かない。\n" + src_lines)
    txt = llm.generate_text(prompt, max_tokens=min(3000, 80 + 40 * len(segments)))
    if not txt:
        return None
    got: dict[int, str] = {}
    for ln in txt.splitlines():
        m = re.match(r"\s*(\d+)[.)、:：\-\s]+(.+)", ln.strip())
        if m:
            got[int(m.group(1))] = m.group(2).strip()
    out = [got.get(i + 1, "").strip() for i in range(len(segments))]
    if sum(1 for x in out if x) < max(1, len(segments) // 2):   # 절반도 못 얻으면 번역 실패로 간주
        return None
    return out


def _dub_transcript(video: str, work: Path) -> list[dict] | None:
    """전사(Whisper) → 일본어 번역(제미나이) → 검수용 대본 [{start,end,orig,jp}]. 실패 시 None.
    ★2단계 검수의 1단계 산출물이자 더빙 렌더의 입력(같은 로직 공유)."""
    from src.core import transcribe as _tr
    tr = _tr.transcribe(video, str(work / "asr"))
    if not tr:
        return None
    segs = tr["segments"]
    jps = _translate_segments_jp(segs, tr.get("lang", ""))
    if not jps:
        return None
    return [{"start": float(s["start"]), "end": float(s["end"]),
             "orig": s.get("text", ""), "jp": jps[i]} for i, s in enumerate(segs)]


def _build_dub_narration(video: str, orig_dur: float, work: Path,
                         transcript: list[dict] | None = None) -> dict | None:
    """★더빙형 롱폼: 원본 발화를 **전사→일본어 번역→그 발화 시각에 정렬**해 나레이션·자막을 얹는다.
    (기존 비전 기반 `_build_long_narration`은 화면을 보고 지어내 원본 음성과 어긋났다 → 더빙으로 해결.)

    - transcript(대시보드 검수 편집본 [{start,end,orig,jp}])가 오면 전사·번역을 건너뛰고 그대로 사용.
    - 없으면: Whisper 전사 → 제미나이 번역 → transcript 구성.
    - 각 일본어 문장을 **원본 발화 시작 시각(anchor)** 에 배치(자막·TTS 모두). 원본 오디오는 상위에서 덕킹.
    반환 {mp3, disp, chunks, chapters, duration, transcript} 또는 None(전사·번역 실패 → 비전 폴백)."""
    from src.core import narration_sync
    if transcript is None:
        transcript = _dub_transcript(video, work)
        if not transcript:
            return None

    all_disp: list[tuple] = []
    audio_parts: list[tuple] = []
    chapters: list[tuple] = []
    all_chunks: list[str] = []
    prev_end = 0.0
    for i, seg in enumerate(transcript):
        jp = (seg.get("jp") or "").strip()
        if not jp:
            continue
        lines = _jp_lines_for_subtitle(jp)
        if not lines:
            continue
        try:
            nar = narration_sync.synthesize(lines, str(work / f"dub{i}"))
        except Exception as e:  # noqa: BLE001
            log.info("[narrate] 더빙 구간%d 합성 실패(건너뜀): %s", i, e)
            continue
        if not nar.get("mp3") or not nar.get("disp"):
            continue
        anchor = max(float(seg.get("start", 0.0)), prev_end + 0.05)   # 원본 발화 시작에 정렬(비겹침 보정)
        anchor = min(anchor, max(0.0, orig_dur - 0.4))
        for (txt, s, e) in nar["disp"]:
            all_disp.append((txt, s + anchor, e + anchor))
        audio_parts.append((nar["mp3"], anchor))
        all_chunks.extend(lines)
        chapters.append((anchor, _chapter_title(seg.get("orig", ""), lines)))
        prev_end = anchor + float(nar.get("duration") or 0)
    if not audio_parts:
        return None
    mp3 = _mix_delayed(audio_parts, orig_dur, work)
    all_disp.sort(key=lambda d: d[1])
    log.info("[narrate] 더빙형 나레이션: %d발화 정렬(원본 음성 시각 기준)", len(audio_parts))
    return {"mp3": mp3, "disp": all_disp, "chunks": all_chunks,
            "chapters": chapters, "duration": orig_dur, "transcript": transcript}


def _build_long_narration(video: str, orig_dur: float, seen_global: str, source_topic: str,
                          work: Path) -> dict:
    """★롱폼: 원본 전체 길이(orig_dur)를 유지하며 나레이션을 타임라인 전체에 분산 배치한다.
    - 구간(segment)마다 프레임을 비전으로 보고 그 구간의 나레이션을 만든다(있으면 · 구간별 다른 내용).
    - 비전이 없으면(키 없음) 전역 대본 하나를 구간 수만큼 나눠 분산 배치한다(같은 내용 반복 대신 분할).
    - 각 나레이션은 자기 구간 시작 시각에 배치 → 영상을 자르지 않고 소리가 전체에 걸쳐 흐른다.
    반환 {mp3, disp, chunks, chapters:[(t, title)], duration=orig_dur}."""
    from src.core import narration_sync
    n_seg = max(3, min(8, round(orig_dur / 40.0)))
    seg_len = orig_dur / n_seg
    seg_descs = [_describe_segment(video, work, i * seg_len, (i + 1) * seg_len, i) for i in range(n_seg)]
    have_vision = sum(1 for d in seg_descs if d) >= max(2, n_seg // 2)

    paras: list[tuple] = []      # (chunks, basis_for_title)
    if have_vision:
        for i in range(n_seg):
            basis = seg_descs[i] or source_topic or seen_global
            paras.append((_jp_segment_chunks(basis, i, n_seg), seg_descs[i] or basis))
    else:
        # 비전 없음 → 전역 대본(진짜 정보만)을 구간 수로 분할해 분산(내용 반복 대신 분할)
        glob = _jp_script("", (source_topic or seen_global), "longform")
        if not glob:
            glob = _jp_chunks_from_notes("", (source_topic or seen_global), 44)
        per = max(1, -(-len(glob) // n_seg))   # ceil
        for i in range(n_seg):
            grp = glob[i * per:(i + 1) * per]
            paras.append((grp, (grp[0] if grp else "")))

    # ★#2: 원본이 '말하는(소리 나는)' 구간을 찾아, 각 나레이션을 그 구간 시작에 맞춰 배치한다
    #   (원본 목소리 구간에 일본어 나레이션·자막이 겹쳐 나오게). 없으면 균등 분할 시각 사용.
    regions = _audio_active_regions(video, orig_dur)
    all_disp: list[tuple] = []
    audio_parts: list[tuple] = []
    chapters: list[tuple] = []
    all_chunks: list[str] = []
    prev_end = 0.0
    for i, (chunks, basis) in enumerate(paras):
        chunks = [c for c in (chunks or []) if c and c.strip()]
        if not chunks:
            continue
        all_chunks.extend(chunks)
        segw = work / f"tts{i}"
        try:
            nar = narration_sync.synthesize(chunks, str(segw))
        except Exception as e:  # noqa: BLE001
            log.info("[narrate] 구간%d 나레이션 합성 실패(건너뜀): %s", i, e)
            continue
        if not nar.get("mp3") or not nar.get("disp"):
            continue
        t0, t1 = i * seg_len, (i + 1) * seg_len
        anchor = next((s for s, e in regions if t0 - 0.1 <= s < t1), t0)   # 그 구간의 원본 발화 시작
        if i == 0 and anchor < 0.2:
            anchor = 0.2
        anchor = max(anchor, prev_end + 0.25)                             # 순서·비겹침
        anchor = min(anchor, max(0.0, orig_dur - 0.5))                    # 끝 넘침 방지
        for (txt, s, e) in nar["disp"]:
            all_disp.append((txt, s + anchor, e + anchor))
        audio_parts.append((nar["mp3"], anchor))
        chapters.append((anchor, _chapter_title(basis, chunks)))
        prev_end = anchor + float(nar.get("duration") or 0)
    if not audio_parts:
        raise ValueError("나레이션을 만들 수 없습니다(구간 대본 없음).")
    mp3 = _mix_delayed(audio_parts, orig_dur, work)
    all_disp.sort(key=lambda d: d[1])
    return {"mp3": mp3, "disp": all_disp, "chunks": all_chunks,
            "chapters": chapters, "duration": orig_dur}


def _ko_titles(titles: list[str]) -> list[str]:
    """챕터 제목(일본어) 목록을 한 번의 LLM 호출로 한국어 번역. 실패 시 원문 유지."""
    from src.core import llm
    titles = [t for t in titles if t]
    if not titles:
        return []
    raw = llm.generate_text("次の日本語の見出しリストを自然な韓国語に訳し、同じ個数のJSON配列だけを出力:\n"
                            + json.dumps(titles, ensure_ascii=False), max_tokens=400)
    if raw:
        m = re.search(r"\[.*\]", raw, re.S)
        if m:
            try:
                arr = json.loads(m.group(0))
                if isinstance(arr, list) and len(arr) == len(titles):
                    return [str(x).strip() or titles[i] for i, x in enumerate(arr)]
            except Exception:  # noqa: BLE001
                pass
    return list(titles)


def _subs_record(disp: list[tuple], offset: float = 0.0) -> list[dict]:
    """화면에 나가는 자막을 **시각과 함께** 레코드용으로 정리(일본어 + 한국어 번역).

    운영자 요청: "자막이 뭐라고 나오는지 관리자 페이지에서 타임스탬프별로 보고 싶다."
    offset: 오프닝 훅이 앞에 붙는 만큼 본문 자막이 뒤로 밀린다 → 완성 영상 기준 시각으로 맞춘다.
    ★도감형(reels)과 **같은 형식**을 쓰도록 공용 모듈(subs_script)에 위임한다.
    """
    from src.core import subs_script
    return subs_script.rows_from_disp(disp, offset)


def _condense_chapters_llm(chapters: list[tuple], target: int) -> list[tuple] | None:
    """전체 챕터 후보를 LLM에 보여주고 '진짜 국면 전환' 지점만 고르게 한다. 실패 시 None."""
    from src.core import llm
    listing = "\n".join(f"{i}. [{_ts_mmss(t)}] {title}" for i, (t, title) in enumerate(chapters))
    prompt = (
        "以下は動画のナレーション区間の一覧(時刻・見出し)です。この中から、内容が実際に大きく転換する"
        f"箇所だけを{max(3, target - 1)}〜{target}個選び、YouTubeのチャプター(目次)として使います。"
        "似た話題が続く区間はまとめて1つだけ選び、最初の区間(0番)は必ず含めてください。\n\n"
        f"{listing}\n\n"
        '選んだ番号だけをJSON配列で出力(説明・記号なし): 例 {"indices":[0,4,9,15]}')
    raw = llm.generate_text(prompt, max_tokens=200)
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        idxs = sorted({int(i) for i in d.get("indices", []) if 0 <= int(i) < len(chapters)})
    except Exception:  # noqa: BLE001
        return None
    if not idxs:
        return None
    if 0 not in idxs:
        idxs = [0] + idxs
    if len(idxs) > target + 1:      # 모델이 규칙을 안 지키고 과다 반환한 경우 방어
        idxs = idxs[: target + 1]
    return [chapters[i] for i in idxs]


def _condense_chapters(chapters: list[tuple], target: int = 4) -> list[tuple]:
    """★타임스탬프 과다 방지(운영자 확정 · '세네 개 정도가 적당'): 더빙형(`_build_dub_narration`)은
    원본 발화 문장(Whisper 세그먼트)마다 챕터를 하나씩 만들어, 몇 분짜리 영상에도 수십 개가 생겼다.
    유튜브 챕터는 '큰 국면 전환'만 표기하는 게 정상이므로 목표 개수(기본 4개)로 줄인다.
    ① LLM(있으면)에게 전체 후보(시각+제목)를 보여주고 화제가 실제로 바뀌는 지점만 고르게 한다.
    ② LLM 미가용/실패 시 시간축 균등 다운샘플(전체 구간에 고르게 퍼진 지점, 첫 챕터는 항상 포함)로 폴백."""
    if len(chapters) <= target:
        return chapters
    picked = _condense_chapters_llm(chapters, target)
    if picked:
        return picked
    n = max(3, min(target, len(chapters)))
    idxs = sorted({round(i * (len(chapters) - 1) / (n - 1)) for i in range(n)}) if n > 1 else [0]
    if 0 not in idxs:
        idxs = [0] + idxs
    return [chapters[i] for i in idxs]


def _chapter_block(chapters: list[tuple], offset: float, header: str, titles: list[str] | None = None) -> str:
    """[(t, title)] → '00:00 제목' 줄들(첫 줄은 항상 00:00 · 유튜브 챕터 규칙)."""
    if not chapters:
        return ""
    out = [header]
    for idx, (t, title) in enumerate(chapters):
        tt = titles[idx] if (titles and idx < len(titles)) else title
        disp_t = 0.0 if idx == 0 else (t + offset)
        out.append(f"{_ts_mmss(disp_t)} {tt}")
    return "\n".join(out)


def narrate_video(video_path: str, mode: str = "shorts", source_topic: str = "",
                  base_dir: str = ".", out_name: str | None = None,
                  phase: str = "render", transcript: list[dict] | None = None,
                  credit: str = "", license_id: str = "",
                  manual: dict | None = None) -> dict:
    """첨부 영상 → 일본어 나레이션·자막 완성본.

    ★운영자 확정: 제목·설명은 입력받지 않는다. 영상 내용을 비전으로 '보고' 대본을 만들고,
    그 대본으로부터 제목·설명·해시태그를 일본어+한국어로 자동 생성해 반환한다.
    `source_topic`: 소싱 출처(커먼스/아카이브)의 설명 — 있으면 근거로 활용(운영자 입력 아님).
    반환 {path, duration, mode, chunks, meta{title_jp/ko, desc_jp/ko, tags_jp/ko}, description}.

    mode: 'shorts'(9:16 720×1280) 또는 'longform'(16:9 1920×1080)."""
    mode = "longform" if str(mode).lower().startswith("long") else "shorts"
    vp = Path(video_path)
    if not vp.exists() or vp.stat().st_size < 10_000:
        raise ValueError(f"첨부 영상을 찾을 수 없습니다: {video_path}")
    base = Path(base_dir)
    work = base / "work" / "narrate"
    out_dir = base / "output"
    work.mkdir(parents=True, exist_ok=True); out_dir.mkdir(parents=True, exist_ok=True)
    w, h = (SHORTS_W, SHORTS_H) if mode == "shorts" else (LONG_W, LONG_H)

    # 0) 번인 로고 제거(NOAA 등 지속 로고 delogo) — ★롱폼은 안 함(운영자 확정: 쓸데없는 부분을 자꾸
    #    가려 거슬림). 쇼츠만 delogo(짧은 영상은 로고 노출이 더 거슬림). 롱폼은 운영자가 소스를 고르므로 원본 그대로.
    src = _clean_watermark(str(vp), work / "wm") if mode == "shorts" else str(vp)

    # ★2단계 더빙 검수(운영자 확정): phase="transcribe"면 렌더 없이 '전사→일본어 번역' 대본만 만들어
    #   돌려준다(대시보드에서 검수·수정 후 phase="render"로 확정 제작). 롱폼 전용(원본 화자 발화 더빙).
    if mode == "longform" and str(phase).lower() == "transcribe":
        tr = _dub_transcript(src, work)
        if not tr:
            raise ValueError("원본 음성 전사에 실패했습니다(무음이거나 faster-whisper 미설치).")
        log.info("[narrate] 전사 단계 완료: %d문장 대본(검수 대기)", len(tr))
        return {"phase": "transcribe", "mode": mode, "transcript": tr,
                "source_url": "", "duration": _probe_dur(src)}

    # 0ب) 영상 내용 파악(비전) — 소싱 출처 설명이 있으면 근거로 합침.
    #   ★비용절감(운영자 확정): 쇼츠만 전체 영상을 1회 서술한다. 롱폼은 구간별로 각자 서술하므로
    #   전체 서술(_describe_video)을 생략한다(중복 Gemini 호출 제거). 롱폼은 _build_long_narration이 담당.
    import os
    desc = (source_topic or "").strip()
    basis_kind = "topic" if desc else ""
    if mode == "shorts":
        # ★대본 근거 우선순위(운영자 확정): ①원본 음성 전사 ②출처 페이지 설명 ③최후수단 화면 분석.
        #   ①②가 실제 정보라 정확하고 풍부하다. ③은 "무엇이 보인다" 수준이라 마지막에만 쓴다.
        speech = _speech_notes(src, work)
        if speech:
            desc = (f"【原音声の書き起こし】{speech}" + ("\n【出典の説明】" + desc if desc else "")).strip()
            basis_kind = "audio"
        if len(desc) < 80:
            # ①②로 근거가 얇다 → 화면 분석을 최후 수단으로 덧댄다(운영자 확정: "최대한 무난하게").
            seen = _describe_video(src, work)
            if seen:
                desc = (desc + "\n【画面から見える様子】" + seen).strip() if desc else seen
                basis_kind = basis_kind or "vision"
        if not desc:
            raise ValueError("영상 내용을 파악하지 못했습니다"
                             "(원본 음성·출처 설명·화면 분석 모두 확보 실패).")
        log.info("[narrate] 쇼츠 대본 근거: %s (%d자)", basis_kind or "vision", len(desc))
    else:
        seen = ""   # 롱폼: 전체 서술 생략(구간별 비전이 담당)
        _vision_ok = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"))
        if not desc and not _vision_ok:      # 근거 전무(출처 없음+비전 키 없음)면 지어내지 않고 실패
            raise ValueError("영상 내용을 파악하지 못했습니다(GEMINI_API_KEY 또는 소싱 출처 설명 필요).")

    # 1~2) 나레이션 — 쇼츠=단일 대본(짧게) · 롱폼=원본 전체 길이에 분산 배치(구간별)
    from src.core import narration_sync
    chapters: list[tuple] = []
    if mode == "longform":
        # ★원본을 자르지 않는다: 출력 길이 = 원본 전체 길이. 나레이션은 타임라인 전체에 분산.
        orig_dur = _probe_dur(src)
        if orig_dur <= 0:
            raise ValueError("원본 영상 길이를 읽지 못했습니다.")
        # ★더빙형 우선(운영자 확정): 원본 화자가 말하면 그 발화를 전사→일본어 번역→발화 시각에 정렬해
        #   자막·나레이션이 정확히 맞물리게 한다. 검수 편집본(transcript)이 오면 그대로 사용. 전사 실패/
        #   무음이면 기존 비전 기반(_build_long_narration)으로 안전 폴백(발행 불정지).
        nar = None
        if transcript:
            nar = _build_dub_narration(src, orig_dur, work, transcript=transcript)
        elif _has_audio(src):
            nar = _build_dub_narration(src, orig_dur, work)
        if not nar:
            nar = _build_long_narration(src, orig_dur, seen, source_topic, work)
        chunks = nar["chunks"]
        # ★타임스탬프 과다 방지(운영자 확정): 더빙형은 문장마다 챕터가 생겨 폭증하므로 큰 국면 전환
        #   지점만 남도록 목표 개수(4개)로 줄인다(LLM 우선·실패 시 균등 다운샘플).
        chapters = _condense_chapters(nar.get("chapters") or [], target=4)
        dur = orig_dur
    else:
        # 근거가 화면 분석뿐이면 단정을 막는 '무난 모드'로 쓴다(운영자 확정).
        chunks = _jp_script("", desc, mode, conservative=(basis_kind in ("", "vision")))
        if not chunks:
            raise ValueError("나레이션 대본을 만들 수 없습니다.")
        # ★쇼츠 길이(운영자 확정): 예전엔 나레이션 길이 = 영상 길이라 22초짜리가 나왔다.
        #   원본이 충분하면 최소 _SHORTS_MIN_S 까지 늘려 영상을 더 보여준다.
        _src_dur = _probe_dur(src)
        target = min(_SHORTS_MIN_S, _src_dur) if _src_dur > 0 else _SHORTS_MIN_S
        # ★문장 사이 쉼 + 영상 전체 분배(운영자 확정 · 실사고): 문장을 한 덩어리로 붙여 읽어
        #   앞부분에서 숨도 안 쉬고 끝나고 **뒷부분은 완전 무음**이었다 → 문장별로 따로 합성해
        #   영상 끝까지 고르게 배치한다(쉼은 문장 길이에 비례).
        nar = _spread_shorts_narration(chunks, work, target)
        if not nar:                       # 분배 실패 시 기존 방식으로 안전 폴백(제작 불정지)
            # ★폴백에서도 **구독 유도는 반드시 들어간다**(운영자 확정): 예전엔 이 경로로 빠지면
            #   구독 유도가 통째로 사라졌다. 대본 끝에 붙여 읽히고 자막으로도 나가게 한다.
            nar = narration_sync.synthesize(chunks + [_SHORTS_CTA_JP], str(work),
                                            rate=_SHORTS_TTS_RATE)
            dur = max(float(nar.get("duration") or 0) + 0.6, target)
            log.warning("[narrate] 나레이션 분배 실패 → 이어읽기 폴백(구독 유도는 유지)")
        else:
            dur = max(target, float(nar.get("duration") or 0))
            # 길이에 맞춰 문장이 줄었으면 캡션·설명도 '실제로 읽은 문장'만 쓰게 맞춘다.
            chunks = list(nar.get("chunks") or chunks)
        log.info("[narrate] 쇼츠 길이: 영상 %.1fs (원본 %.1fs · 자막 %d개 · 분배=%s)",
                 dur, _src_dur, len(chunks), bool(nar.get("spread")))
    if not nar.get("mp3") or not nar.get("disp"):
        raise ValueError("나레이션 합성 실패(TTS)")

    # 3) 영상 정규화(쇼츠=9:16 리프레임 · 롱폼=16:9 cover, 원본 전체 길이)
    body_v = str(work / "body.mp4")
    if mode == "shorts":
        from src.core import reframe
        # ★①인트로·아웃트로 브랜딩 카드 제거(실사고: 22초 영상의 10초가 NOAA 'earth is blue'
        #   로고 화면이었다). 도감형(reels)엔 있던 자동 트림이 나레이션형엔 없어 그대로 들어갔다.
        # ★★시간 기준을 하나로(운영자 확정 · 절대 회귀 금지): 운영자가 고른 초는 **자르지 않은
        #   원본** 기준이다(미리보기 mp4·사진 띠가 원본에서 만들어진다). 그런데 아래 카드 트림은
        #   앞부분을 잘라낸 사본을 만들므로, 트림이 걸리는 순간 지정한 초가 그만큼 밀려 **엉뚱한
        #   장면**이 나간다. → 구간을 직접 지정한 회차는 트림을 건너뛴다(운영자가 카드 구간을
        #   피해서 고른 것이므로 안전). 지정이 없을 때만 기존대로 자동 트림.
        if str((manual or {}).get("cut_specs") or "").strip():
            clean = src
            log.info("[narrate] 운영자 구간 지정 → 인트로·아웃트로 자동 트림 건너뜀(시각 기준을 원본으로 고정)")
        else:
            clean = _trim_intro_outro_cards(src, work)
        # ★②cover 크롭(실사고: 화면 가운데 얇은 띠로만 보였다). 가로 소스를 9:16에 '전체 담기'로
        #   넣으면 위아래가 블러 여백이 되는데, 어두운 다큐 영상은 그 여백이 새까매서 띠처럼 보인다.
        #   → wide=True(=cover)로 화면을 꽉 채운다. 생물 도감형은 기존 '전체 담기'를 유지한다.
        body_v = reframe.reframe_to_vertical(clean, body_v, dur, str(work / "rf"),
                                             wide=True, manual=manual)
    else:
        _normalize_landscape(src, body_v, dur, str(work))
        # ★원본 화면의 정적 라벨(종명·수심·타이틀 등)을 딥네이비 박스+일본어로 번역해 얹기(롱폼 전용).
        #   자막 번인 '전'에 적용(좌표는 정규화된 본문 프레임 기준). 없거나 실패면 원본 그대로(발행 불정지).
        try:
            from src.core import onscreen_translate as ost
            body_v = ost.apply(body_v, str(work / "ost_body.mp4"), str(work / "ost"), dur, w, h)
        except Exception as e:  # noqa: BLE001
            log.info("[narrate] 화면 라벨 번역 오버레이 생략: %s", e)

    # 4) 카라오케 자막 번인 — ★자막 크게(쇼츠 1.8 · 롱폼 2.2로 2배 이상)
    sub_scale = 1.8 if mode == "shorts" else 2.2
    ass = narration_sync.build_synced_ass(nar["disp"], str(work / "subs.ass"),
                                          hook_first=False, w=w, h=h, sub_scale=sub_scale)
    subbed = str(work / "subbed.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", body_v, "-vf", f"ass={ass}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", subbed],
                   check=True, timeout=1800)

    # 5) 오디오 = 원본(효과음·배경 보존) 덕킹 + 나레이션(더 크게) 믹스 → 본문 완성본
    #    ★#1: 원본 배경/효과음을 살리고, 나레이션이 원본 목소리보다 크게 들리도록 사이드체인 덕킹.
    name = out_name or f"narrated_{mode}"
    final = str(out_dir / f"{name}.mp4")
    body_final = str(work / "body_final.mp4")
    # ★저작권 음악 자동 제거(운영자 확정 · 유튜브 Content ID 재발방지 · 롱폼만):
    #   순서 보장 — ①전사·번역(자막/나레이션)은 위에서 이미 '원본 오디오'로 끝났다(분리 열화 무관).
    #   ②이제 원본에서 상용 음악을 제거(보컬 분리 → 목소리만) ③빠진 음악 자리는 보유 자체 BGM
    #   (assets/audio/bgm/longform_*)으로 채운다. 분리 실패/미설치 시 원본 오디오 그대로(발행 불정지).
    bg_audio = bgm_path = None
    if mode == "longform":
        try:
            from src.core import music_strip
            bg_audio = music_strip.strip_music(src, str(work / "ms"))
            if bg_audio:
                bgm_path = music_strip.pick_bgm(seed=Path(str(vp)).name, base_dir=base_dir)
        except Exception as e:  # noqa: BLE001
            log.info("[narrate] 음악 제거 생략(오류): %s", e)
    mixed_audio = _mix_bg_narration(src, nar["mp3"], dur, work, bg_audio=bg_audio, bgm=bgm_path)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", subbed, "-i", mixed_audio,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", body_final],
                   check=True, timeout=600)

    # 6) 대본 → 공개용 메타데이터(제목·설명·해시태그·훅, 일본어+한국어) 자동 생성
    #    ★A안: 소싱 출처 설명(source_topic)도 사실 근거로 함께 넘겨 제목의 내용예측력↑(날조 없음).
    meta = _gen_metadata(chunks, mode, source_topic=source_topic)

    # 7) 유튜브 썸네일 저장 + ★쇼츠 오프닝 훅(운영자 확정 · 2차 수정).
    #    예전엔 "썸네일이 훅을 보여주니 영상 앞 카드는 중복"이라 판단해 오프닝을 아예 없앴는데,
    #    그건 **롱폼 기준**이었다. 운영자 확정: **쇼츠는 오프닝 훅이 반드시 있어야 한다**
    #    ("일반 나레이션 영상은 앞 표지를 잡고 없애도, 숏폼은 오프닝 훅을 없애면 안 돼").
    #    방식도 확정: 정지 카드가 아니라 **도감형과 같은 애니메이션 훅**(어절 팝인 + 훅 나레이션 +
    #    사운드) → 채널 톤 통일. 엔드카드는 나레이션형에 두지 않는다(운영자 기확정).
    #    실패해도 발행 불정지(오프닝 없이 본문 그대로).
    thumb_path = out_dir / f"{name}_thumb.jpg"
    hook_txt = (meta.get("hook_jp") or "").strip()
    thumb_rendered = False
    hero = ""
    # ★표지(오프닝 훅·썸네일) 운영자 지정(운영자 확정): {"at":초,"zoom":배율,"x":가로,"y":세로}
    #   지정이 있으면 자동 선택을 쓰지 않고 **그 시각·그 구획**으로 표지를 만든다.
    #   썸네일과 오프닝 훅은 같은 배경을 쓰므로 이 하나로 둘 다 정해진다.
    from src.core import hook_intro_stage as _his
    cover_spec = _his.parse_cover_spec((manual or {}).get("cover"))
    try:
        from src.core import hook_intro as hi
        if hook_txt and hi.fonts_available():
            if cover_spec:
                _cv = str(work / "cover.png")
                hero = _cv if _his.make_cover_frame(src, cover_spec, _cv, w, h, work / "cover") else ""
                if not hero:
                    log.warning("[narrate] 지정 표지 생성 실패 → 자동 선택으로 폴백")
            if not hero:
                hero = _pick_hero_frame(src, work / "hero", w,
                                        subject_hint=(source_topic or meta.get("title_jp", "") or "").strip())
            if hero:
                card = str(work / "hookcard.png")   # 썸네일 렌더의 부산물(영상에는 미사용)
                thumb_rendered = _render_hook_and_thumb(hero, hook_txt, meta.get("title_jp", ""), w, h,
                                                        card, str(thumb_path))
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 썸네일 렌더 실패(생략): %s", e)
    opened = body_final
    if mode == "shorts" and hook_txt:
        opened = _apply_opening_hook(body_final, hook_txt, work, hero_image=hero,
                                     open_bg_video=body_v, subject_video=src,
                                     cover_spec=cover_spec)
    shutil.move(opened, final)
    thumb_out = str(thumb_path) if thumb_path.exists() else ""

    # 8-00) ★저작권 표기(운영자 확정 "캡션에만"): 나레이션형은 엔드카드가 없어 **캡션이 유일한
    #       표기 위치**다. CC BY·CC BY-SA는 저작자 표시가 라이선스 의무이므로 반드시 넣는다.
    #       (하드룰 #1 · 표기 없으면 이용 조건 위반)
    _cred = _credit_line(credit, license_id)
    if _cred:
        for _k, _tag in (("desc_jp", "映像"), ("desc_ko", "영상")):
            _t = (meta.get(_k) or "").strip()
            _line = f"{_tag}: {_cred}"
            if _line not in _t:
                meta[_k] = (_t + ("\n\n" if _t else "") + _line).strip()
        log.info("[narrate] 캡션 저작권 표기: %s", _cred)

    # 8-0) ★설명란 CTA(구독+댓글) — 챕터 목차보다 **위**에 둔다(목차 아래는 접혀서 안 보임).
    #      나레이션에는 넣지 않는다(마무리 여운·시청완료율 보호). 문구는 릴스 캡션과 동일 출처.
    try:
        from src.core.rich_caption import _CTA_JP as _CJ, _CTA_KO as _CK
        for _k, _cta in (("desc_jp", _CJ), ("desc_ko", _CK)):
            _t = (meta.get(_k) or "").strip()
            _add = [c for c in _cta if c not in _t]
            if _add:
                meta[_k] = (_t + ("\n\n" if _t else "") + "\n".join(_add)).strip()
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 설명란 CTA 삽입 생략: %s", e)

    # 8) ★설명란에 타임스탬프(구체 챕터) 삽입(롱폼) — 오프닝 훅 영상 폐지로 본문은 항상 0초부터 시작
    if mode == "longform" and chapters:
        titles_jp = [t for _, t in chapters]
        titles_ko = _ko_titles(titles_jp)
        blk_jp = _chapter_block(chapters, 0.0, "▼ チャプター(目次)", titles_jp)
        blk_ko = _chapter_block(chapters, 0.0, "▼ 챕터(목차)", titles_ko)
        if blk_jp:
            meta["desc_jp"] = (meta.get("desc_jp", "").strip() + "\n\n" + blk_jp).strip()
        if blk_ko:
            meta["desc_ko"] = (meta.get("desc_ko", "").strip() + "\n\n" + blk_ko).strip()
        meta["chapters"] = [{"t": t, "title_jp": titles_jp[i],
                             "title_ko": (titles_ko[i] if i < len(titles_ko) else titles_jp[i])}
                            for i, (t, _) in enumerate(chapters)]

    # ★원본 미리보기 mp4 + 프레임 사진 시트(운영자 확정): 소싱 원본이 WebM(VP8)이면 아이폰에서
    #   재생이 안 돼 '구간 다시 잡기'를 쓸 수 없었다. mp4는 재생용, 시트는 **재생 없이** 손가락으로
    #   구간·크롭을 고르는 재료다. ★자르지 않은 **원본**(vp)을 쓴다 — 여기서 읽은 초가 곧 컷 지정 초.
    #   ⚠ 메타 파일 **쓰기 전에** 만들어야 시트 정보(sheet_meta)가 메타에 담겨 워크플로가 읽는다.
    from src.core import source_preview
    src_preview = source_preview.make_preview_mp4(str(vp), str(out_dir / f"{name}_source.mp4"))
    sheet_path = out_dir / f"{name}_sheet.jpg"
    src_sheet = source_preview.make_frame_sheet(str(vp), str(sheet_path))
    if src_sheet:
        meta["sheet_meta"] = src_sheet
    # ★필요한 총 길이(운영자 확정): "구간을 반복해 채우지 말고, 총 몇 초가 필요한지 알려주면
    #   내가 그만큼 고르겠다." → 본문 길이(=나레이션 길이)를 레코드에 남겨 대시보드가 보여준다.
    meta["body_dur"] = round(float(dur), 1)
    # ★자막 스크립트(운영자 요청): 화면에 나가는 자막을 시각과 함께 남겨 관리자 페이지에서 확인.
    #   오프닝 훅이 앞에 붙은 만큼(완성 길이 − 본문 길이) 본문 자막 시각을 밀어 완성본 기준으로 맞춘다.
    _open_off = max(0.0, _probe_dur(final) - float(dur)) if opened != body_final else 0.0
    meta["subs"] = _subs_record(nar.get("disp") or [], offset=_open_off)
    meta["cta_jp"] = _SHORTS_CTA_JP if mode == "shorts" else ""
    # ★운영자 지정값 보존(운영자 확정 · 실사고): 표지(cover)와 컷(cut_specs)을 레코드에 남긴다.
    #   예전엔 워크플로 입력으로 한 번 쓰고 버려서, 다음에 **컷만 고치면 표지 지정이 초기화**됐다.
    #   화면이 이 값을 다시 불러와 편집기에 채우고, 다시 만들 때 함께 보낸다.
    meta["edit"] = {k: str(v) for k, v in (manual or {}).items() if str(v or "").strip()}
    # ★적용 내역(운영자 확정): 지정값이 아니라 **실제로 렌더에 쓰인 값**을 남긴다.
    #   지정만 저장하면 이번 같은 전달 사고("보냈는데 안 먹었다")를 화면에서 구분할 수 없다.
    applied: dict = {}
    _fit = str((manual or {}).get("fit") or "").strip().lower()
    if _fit in ("square", "full"):
        applied["fit"] = _fit          # 화면 구성(꽉 채우기 외)을 실제 반영값으로 남긴다
    if cover_spec:
        applied["cover"] = {k: cover_spec[k] for k in ("at", "zoom", "x", "y")}
    try:
        _ac = json.loads((work / "rf" / "applied_cuts.json").read_text(encoding="utf-8"))
        if _ac.get("cuts"):
            applied["cuts"] = _ac["cuts"]
            applied["cuts_manual"] = bool(_ac.get("manual"))
    except Exception:  # noqa: BLE001
        pass
    if applied:
        meta["applied"] = applied

    meta_path = out_dir / f"{name}.meta.json"
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    log.info("[narrate] 완성: %s (%s · %.1fs · %d청크 · %d챕터 · 썸=%s · 미리보기=%s) title=%s",
             final, mode, dur, len(chunks), len(chapters), bool(thumb_out), bool(src_preview),
             meta.get("title_jp", ""))
    return {"path": final, "duration": dur, "mode": mode, "chunks": chunks,
            "source_preview": src_preview,
            "source_sheet": (str(sheet_path) if src_sheet else ""),
            "source_sheet_meta": src_sheet or None,
            # ★쇼츠 오프닝 훅이 실제로 붙었는지(회귀 테스트·운영 로그용). 붙지 않으면 '표지만 있고
            #   영상 시작에 훅이 없는' 상태가 되므로, 조용히 넘어가지 않게 결과에 남긴다.
            "opening_hook": bool(opened != body_final),
            "meta": meta, "meta_path": str(meta_path), "description": desc, "chapters": chapters,
            "hooked": thumb_rendered, "thumb": thumb_out, "width": w, "height": h,
            # ★더빙형 검수용: 원문·일본어 대본(전사 편집본). 대시보드에서 수정 후 재제작에 재사용.
            "transcript": (nar.get("transcript") if isinstance(nar, dict) else None)}
