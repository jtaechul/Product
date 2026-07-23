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
_OPEN_DUR = 2.8   # 오프닝 훅(타이틀 카드) 길이(초)


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


def _jp_script(title: str, notes: str, mode: str) -> list[str]:
    """일본어 나레이션 대본(청크 리스트) 생성. LLM 우선, 실패 시 결정론 폴백."""
    from src.core import llm
    n_hint = "12〜18" if mode == "shorts" else "24〜40"
    prompt = (
        "あなたは自然・海洋ドキュメンタリーの日本語ナレーターです。以下の素材情報だけを使い、"
        "落ち着いた敬体（です・ます）で短いナレーションを書いてください。事実の創作は禁止——"
        "与えられた情報にない固有名詞・数値・断定は書かないこと。装飾的な導入で始め、"
        f"1行に日本語で7〜14文字程度、全体で{n_hint}行。各行は字幕として画面に出ます。\n"
        f"【タイトル】{title}\n【内容メモ】{notes}\n"
        "出力は本文のみ。1行1チャンクで、記号や番号は付けないでください。"
    )
    txt = llm.generate_text(prompt, max_tokens=900)
    if txt:
        lines = [re.sub(r"^[\s0-9.\-・*]+", "", ln).strip() for ln in txt.splitlines()]
        lines = [ln for ln in lines if ln and not ln.startswith("【")]
        if len(lines) >= 3:
            cap = 18 if mode == "shorts" else 44
            return lines[:cap]
    return _jp_chunks_from_notes(title, notes, 18 if mode == "shorts" else 44)


def _dedup_tags(tags, core_jp) -> list[str]:
    out: list[str] = []
    for t in list(core_jp) + list(tags or []):
        t = str(t).strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + t.lstrip("#")
        t = t.replace(" ", "")
        if t not in out:
            out.append(t)
    return out[:6]


def _fallback_meta(chunks: list[str], mode: str) -> dict:
    """LLM 미가용 시 대본에서 결정론으로 제목·설명·해시태그(일/한) 도출(날조 없음)."""
    body = "。".join(c.strip("。.、,") for c in chunks[:4] if c.strip())
    first = (chunks[0] if chunks else "").strip() or "海の映像"
    title_jp = (first[:22] + ("…" if len(first) > 22 else ""))
    desc_jp = (body[:180] + "。") if body else "海の映像に日本語ナレーションと字幕を付けた作品です。"
    hook_jp = re.sub(r"[。.、,！!？?]+$", "", first)[:18] or "この光景を、ご存知ですか"
    return {
        "title_jp": title_jp, "title_ko": "",
        "desc_jp": desc_jp, "desc_ko": "",
        "hook_jp": hook_jp,
        "tags_jp": _dedup_tags(["#海", "#自然", "#癒し"], []),
        "tags_ko": ["#바다", "#자연", "#힐링"],
    }


def _gen_metadata(chunks: list[str], mode: str) -> dict:
    """완성된 일본어 나레이션(대본)으로부터 제목·설명·해시태그를 일본어+한국어로 생성.
    ★운영자 요청: 입력 없이 대본을 근거로 자동 생성(수치·사실은 대본 범위 내). LLM 실패 시 결정론 폴백."""
    from src.core import llm
    script = "\n".join(c for c in chunks if c and c.strip())
    kind = "YouTubeショート(縦型)" if mode == "shorts" else "YouTube長編(横型)"
    prompt = (
        "あなたは動画のメタデータ編集者です。以下は完成した日本語ナレーション(字幕本文)です。"
        f"この{kind}動画の公開用メタデータを作ってください。★本文にない事実・数値・固有名詞は創作しないこと。\n\n"
        f"【ナレーション】\n{script}\n\n"
        "次のJSONだけを出力(説明・記号なし):\n"
        '{\"hook_jp\":\"12〜18字の強いオープニングフック(冒頭2秒で指を止める一言・体言止め/問いかけ可)\",'
        '\"title_jp\":\"日本語タイトル(30字以内・クリックを誘う)\",'
        '\"title_ko\":\"上のタイトルの自然な韓国語訳\",'
        '\"desc_jp\":\"日本語の説明文(2〜4文・敬体)\",'
        '\"desc_ko\":\"上の説明の自然な韓国語訳\",'
        '\"tags_jp\":[\"#日本語タグ\",\"…3〜5個\"],'
        '\"tags_ko\":[\"#한국어태그\",\"…3〜5個\"]}')
    raw = llm.generate_text(prompt, max_tokens=700)
    if raw:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                tj = _dedup_tags(d.get("tags_jp") or [], [])
                tk = _dedup_tags(d.get("tags_ko") or [], [])
                hook = re.sub(r"[。.、,！!？?]*$", "", str(d.get("hook_jp", "")).strip())[:22]
                out = {
                    "hook_jp": hook,
                    "title_jp": str(d.get("title_jp", "")).strip(),
                    "title_ko": str(d.get("title_ko", "")).strip(),
                    "desc_jp": str(d.get("desc_jp", "")).strip(),
                    "desc_ko": str(d.get("desc_ko", "")).strip(),
                    "tags_jp": tj, "tags_ko": tk,
                }
                if out["title_jp"] and out["desc_jp"] and out["tags_jp"]:
                    if not out["hook_jp"]:
                        out["hook_jp"] = _fallback_meta(chunks, mode)["hook_jp"]
                    return out
            except Exception:  # noqa: BLE001
                pass
    return _fallback_meta(chunks, mode)


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


def _wrap_cjk(draw, text: str, font, max_w: float) -> list[str]:
    """공백 없는 일본어를 폭에 맞춰 글자 단위로 줄바꿈(온스크린 텍스트 넘침 방지 하드룰)."""
    lines, cur = [], ""
    for ch in str(text):
        if ch == "\n":
            lines.append(cur); cur = ""; continue
        if draw.textlength(cur + ch, font=font) <= max_w or not cur:
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
    """화이트 라운드 '필' 태그(레퍼런스의 「実在します」 칩). 반환: 필 높이."""
    from PIL import ImageDraw, ImageFont
    from src.core import hook_intro as hi
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(hi.FONT_SANS_B, fontsize, index=0)
    tw = d.textlength(text, font=f)
    asc = f.getbbox("あ")[3]
    padx, pady = int(fontsize * 0.6), int(fontsize * 0.42)
    rw, rh = int(tw + 2 * padx), int(asc + 2 * pady)
    d.rounded_rectangle([x, y, x + rw, y + rh], radius=int(rh * 0.26), fill=_CREAM)
    d.text((x + padx, y + pady - int(fontsize * 0.06)), text, font=f, fill=(22, 28, 36))
    return rh


def _render_hook_and_thumb(bg_path: str, hook: str, title: str, w: int, h: int,
                           card_png: str, thumb_png: str) -> bool:
    """훅 문구를 배경(피사체 프레임) 위에 얹어 ① 오프닝 카드 ② 유튜브 썸네일을 만든다.
    ★레퍼런스 양식(운영자 확정 · IMG_3526): 네 모서리 코너 브래킷 + 좌측 세로 어둠(피사체는 우측 노출) +
    좌측 정렬 대형 화이트 볼드 타이틀 + 골드 언더라인 + 화이트 라운드 필 킥커. 소프트 글로우·드롭섀도.
    ★이모지·시스템 아이콘 금지(하드룰) — 텍스트+벡터 도형만. 실패 시 False(훅 생략)."""
    try:
        from PIL import Image, ImageDraw, ImageEnhance
        base = Image.open(bg_path).convert("RGB")
        bg = _cover_crop(base, w, h)
        bg = ImageEnhance.Contrast(bg).enhance(1.10)
        bg = ImageEnhance.Color(bg).enhance(1.08)
        # 좌측 세로 어둠(텍스트 가독) — 왼쪽 짙게 → 오른쪽(피사체)로 투명해지는 수평 그라디언트
        grad = Image.new("L", (w, 1), 0)
        gp = grad.load()
        for xx in range(w):
            f = (1 - xx / (w * 0.62)) * 0.86 if xx < w * 0.62 else 0.0
            gp[xx, 0] = int(255 * max(0.0, f))
        dark = Image.composite(Image.new("RGB", (w, h), (3, 8, 15)), bg, grad.resize((w, h)))
        dark = Image.blend(dark, Image.new("RGB", (w, h), (2, 6, 12)), 0.10)   # 아주 옅은 전체 딤

        x0 = int(w * 0.058)                       # 좌측 텍스트 컬럼 시작
        col_w = int(w * 0.50)                     # 컬럼 폭(우측 피사체 침범 방지)

        def _compose(with_pill: bool):
            im = dark.copy()
            d = ImageDraw.Draw(im, "RGBA")
            _corner_brackets(d, w, h, _CREAM, 230)
            font, lines = _fit_block(d, hook, col_w, 3, int(h * 0.140), int(h * 0.062))
            asc = font.getbbox("あ")[3]
            line_h = int(asc * 1.30)
            y = int(h * 0.135)
            for ln in lines:
                _shadow_text(im, (x0, y), ln, font, blur=max(7, int(h * 0.012)), grow=max(3, int(h * 0.004)))
                dd = ImageDraw.Draw(im, "RGBA")
                dd.text((x0, y), ln, font=font, fill=(255, 255, 255),
                        stroke_width=max(4, int(h * 0.006)), stroke_fill=_INK)
                y += line_h
            d = ImageDraw.Draw(im, "RGBA")
            d.rectangle([x0, y + int(h * 0.012), x0 + int(w * 0.15), y + int(h * 0.012) + max(4, int(h * 0.008))],
                        fill=_ACCENT)                        # 골드 언더라인
            if with_pill and title:
                kick = re.split(r"[、。，,\n]", title.strip())[0][:14] or title.strip()[:14]
                if kick:
                    _pill(im, x0, y + int(h * 0.045), kick, int(h * 0.046))
            return im

        _compose(False).convert("RGB").save(card_png, quality=93)      # 오프닝 카드(영상): 훅만
        _compose(True).convert("RGB").save(thumb_png, quality=92)      # 썸네일: 훅 + 필 킥커
        return Path(card_png).exists() and Path(thumb_png).exists()
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 훅/썸네일 렌더 실패(생략): %s", e)
        return False


def _build_hook_clip(card_png: str, out: str, dur: float, w: int, h: int) -> str:
    """정지 훅 카드 → 무음(나레이션과 겹침 방지) 인트로 클립. 페이드인으로 부드럽게."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", card_png,
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{dur:.2f}",
                    "-vf", f"scale={w}:{h},setsar=1,fps=30,format=yuv420p,fade=t=in:st=0:d=0.5",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", out], check=True, timeout=300)
    return out


def _concat_av(a: str, b: str, out: str, w: int, h: int) -> str:
    """두 mp4를 [a][b] 순서로 이어붙인다(해상도·fps·오디오 포맷 통일 후 concat 필터)."""
    fc = (f"[0:v]scale={w}:{h},setsar=1,fps=30[v0];[1:v]scale={w}:{h},setsar=1,fps=30[v1];"
          "[0:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
          "[1:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
          "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", a, "-i", b,
                    "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", out], check=True, timeout=1200)
    return out


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


def _mix_bg_narration(video: str, narration_mp3: str, dur: float, work: Path) -> str:
    """★#1: 원본 오디오(효과음·배경 보존)를 나레이션 밑으로 '덕킹'하고 나레이션을 더 크게 얹은 최종 오디오.
    - 원본이 무음이면 나레이션만 그대로 반환(현행).
    - 원본 목소리는 배경으로 낮추고(volume 0.8), 나레이션은 키운다(volume 1.8).
    - 나레이션이 울리는 구간엔 사이드체인으로 원본을 더 눌러 나레이션이 확실히 크게 들리게 한다
      (그 사이엔 원본 효과음·배경음이 살아난다)."""
    if not _has_audio(video):
        return narration_mp3
    out = str(work / "mixed.m4a")
    fc = ("[0:a]aformat=sample_fmts=fltp:channel_layouts=stereo:sample_rates=44100,volume=0.8[bg];"
          "[1:a]aformat=sample_fmts=fltp:channel_layouts=stereo:sample_rates=44100,volume=1.8,"
          "asplit=2[vo][vok];"
          "[bg][vok]sidechaincompress=threshold=0.02:ratio=14:attack=15:release=350[bgd];"
          "[bgd][vo]amix=inputs=2:normalize=0:duration=longest,alimiter=limit=0.97[a]")
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", narration_mp3,
                        "-filter_complex", fc, "-map", "[a]", "-t", f"{dur:.2f}",
                        "-c:a", "aac", "-b:a", "192k", out], check=True, timeout=600)
        return out if Path(out).exists() and Path(out).stat().st_size > 2000 else narration_mp3
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 원본+나레이션 믹스 실패 → 나레이션만: %s", e)
        return narration_mp3


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
                  base_dir: str = ".", out_name: str | None = None) -> dict:
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

    # 0ب) 영상 내용 파악(비전) — 소싱 출처 설명이 있으면 근거로 합침.
    #   ★비용절감(운영자 확정): 쇼츠만 전체 영상을 1회 서술한다. 롱폼은 구간별로 각자 서술하므로
    #   전체 서술(_describe_video)을 생략한다(중복 Gemini 호출 제거). 롱폼은 _build_long_narration이 담당.
    import os
    desc = (source_topic or "").strip()
    if mode == "shorts":
        seen = _describe_video(src, work)
        if seen:
            desc = (desc + "\n" + seen).strip() if desc else seen
        if not desc:
            raise ValueError("영상 내용을 파악하지 못했습니다(GEMINI_API_KEY 또는 소싱 출처 설명 필요).")
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
        nar = _build_long_narration(src, orig_dur, seen, source_topic, work)
        chunks = nar["chunks"]
        chapters = nar.get("chapters") or []
        dur = orig_dur
    else:
        chunks = _jp_script("", desc, mode)
        if not chunks:
            raise ValueError("나레이션 대본을 만들 수 없습니다.")
        nar = narration_sync.synthesize(chunks, str(work))
        dur = float(nar.get("duration") or 0) + 0.6
    if not nar.get("mp3") or not nar.get("disp"):
        raise ValueError("나레이션 합성 실패(TTS)")

    # 3) 영상 정규화(쇼츠=9:16 추적 리프레임 · 롱폼=16:9 cover, 원본 전체 길이)
    body_v = str(work / "body.mp4")
    if mode == "shorts":
        from src.core import reframe
        body_v = reframe.reframe_to_vertical(src, body_v, dur, str(work / "rf"), wide=False)
    else:
        _normalize_landscape(src, body_v, dur, str(work))

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
    mixed_audio = _mix_bg_narration(src, nar["mp3"], dur, work)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", subbed, "-i", mixed_audio,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", body_final],
                   check=True, timeout=600)

    # 6) 대본 → 공개용 메타데이터(제목·설명·해시태그·훅, 일본어+한국어) 자동 생성
    meta = _gen_metadata(chunks, mode)

    # 7) 오프닝 훅(타이틀 카드) 생성 + 유튜브 썸네일 저장(운영자 확정 · 실패해도 발행 불정지)
    thumb_path = out_dir / f"{name}_thumb.jpg"
    hook_txt = (meta.get("hook_jp") or "").strip()
    hooked = False
    try:
        from src.core import hook_intro as hi
        if hook_txt and hi.fonts_available():
            hero = _pick_hero_frame(src, work / "hero", w,
                                    subject_hint=(source_topic or meta.get("title_jp", "") or "").strip())
            if hero:
                card = str(work / "hookcard.png")
                if _render_hook_and_thumb(hero, hook_txt, meta.get("title_jp", ""), w, h,
                                          card, str(thumb_path)):
                    hookclip = str(work / "hook.mp4")
                    _build_hook_clip(card, hookclip, _OPEN_DUR, w, h)
                    _concat_av(hookclip, body_final, final, w, h)
                    hooked = True
    except Exception as e:  # noqa: BLE001
        log.info("[narrate] 오프닝 훅 합성 실패(본문만 발행): %s", e)
    if not hooked:
        shutil.move(body_final, final)   # 훅 없이 본문만
    thumb_out = str(thumb_path) if thumb_path.exists() else ""

    # 8) ★설명란에 타임스탬프(구체 챕터) 삽입(롱폼) — 훅이 붙었으면 본문 시작이 밀리므로 오프셋 반영
    if mode == "longform" and chapters:
        offset = _OPEN_DUR if hooked else 0.0
        titles_jp = [t for _, t in chapters]
        titles_ko = _ko_titles(titles_jp)
        blk_jp = _chapter_block(chapters, offset, "▼ チャプター(目次)", titles_jp)
        blk_ko = _chapter_block(chapters, offset, "▼ 챕터(목차)", titles_ko)
        if blk_jp:
            meta["desc_jp"] = (meta.get("desc_jp", "").strip() + "\n\n" + blk_jp).strip()
        if blk_ko:
            meta["desc_ko"] = (meta.get("desc_ko", "").strip() + "\n\n" + blk_ko).strip()
        meta["chapters"] = [{"t": (0.0 if i == 0 else t + offset), "title_jp": titles_jp[i],
                             "title_ko": (titles_ko[i] if i < len(titles_ko) else titles_jp[i])}
                            for i, (t, _) in enumerate(chapters)]

    meta_path = out_dir / f"{name}.meta.json"
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    log.info("[narrate] 완성: %s (%s · %.1fs · %d청크 · %d챕터 · 훅=%s · 썸=%s) title=%s",
             final, mode, dur, len(chunks), len(chapters), hooked, bool(thumb_out), meta.get("title_jp", ""))
    return {"path": final, "duration": dur, "mode": mode, "chunks": chunks,
            "meta": meta, "meta_path": str(meta_path), "description": desc, "chapters": chapters,
            "hooked": hooked, "thumb": thumb_out, "width": w, "height": h}
