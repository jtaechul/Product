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
def _pick_hero_frame(video: str, work: Path, w: int) -> str:
    """영상에서 '피사체가 잘 보이는(구조 분산 큰)' 시각을 골라 그 프레임을 고해상으로 뽑는다.
    오프닝 훅·썸네일 배경용. 실패 시 ''(호출부가 훅 생략)."""
    dur = _probe_dur(video) or 0.0
    if dur <= 0:
        return ""
    work.mkdir(parents=True, exist_ok=True)
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


def _render_hook_and_thumb(bg_path: str, hook: str, title: str, w: int, h: int,
                           card_png: str, thumb_png: str) -> bool:
    """훅 문구를 배경(피사체 프레임) 위에 크게 얹어 ① 오프닝 카드(card_png) ② 유튜브 썸네일(thumb_png)을 만든다.
    ★이모지·시스템 아이콘 금지(하드룰) — 텍스트+벡터 도형만. 실패 시 False(훅 생략)."""
    try:
        from PIL import Image, ImageDraw
        base = Image.open(bg_path).convert("RGB")
        bg = _cover_crop(base, w, h)
        # 상·하단 어둡게(가독성) + 전체 살짝 딤
        dimmed = Image.blend(bg, Image.new("RGB", (w, h), (4, 10, 16)), 0.42)
        grad = Image.new("L", (1, h), 0)
        for yy in range(h):
            f = 0.0
            if yy < h * 0.30:
                f = (1 - yy / (h * 0.30)) * 0.55
            elif yy > h * 0.68:
                f = ((yy - h * 0.68) / (h * 0.32)) * 0.70
            grad.putpixel((0, yy), int(255 * f))
        grad = grad.resize((w, h))
        dark = Image.composite(Image.new("RGB", (w, h), (0, 0, 0)), dimmed, grad)

        accent = (242, 193, 78)   # 골드 포인트(팔레트)

        def _compose(hook_max_lines: int, with_title: bool):
            im = dark.copy()
            d = ImageDraw.Draw(im)
            safe = int(w * 0.86)
            font, lines = _fit_block(d, hook, safe, hook_max_lines, int(h * 0.13), int(h * 0.055))
            asc = font.getbbox("あ")[3]
            line_h = int(asc * 1.28)
            total = line_h * len(lines)
            y = int(h * 0.5 - total / 2) - (int(h * 0.06) if with_title else 0)
            # 골드 강조 바(훅 위)
            d.rectangle([(w - safe) // 2, y - int(h * 0.045), (w - safe) // 2 + int(w * 0.10), y - int(h * 0.028)],
                        fill=accent)
            for ln in lines:
                tw = d.textlength(ln, font=font)
                d.text(((w - tw) / 2, y), ln, font=font, fill=(255, 255, 255),
                       stroke_width=max(4, int(h * 0.006)), stroke_fill=(0, 0, 0))
                y += line_h
            if with_title and title:
                tf, tl = _fit_block(d, title, safe, 2, int(h * 0.05), int(h * 0.028))
                tasc = tf.getbbox("あ")[3]
                ty = int(h * 0.80)
                for ln in tl:
                    tw = d.textlength(ln, font=tf)
                    d.text(((w - tw) / 2, ty), ln, font=tf, fill=accent,
                           stroke_width=max(3, int(h * 0.004)), stroke_fill=(0, 0, 0))
                    ty += int(tasc * 1.3)
            return im

        _compose(3, False).save(card_png, quality=92)          # 오프닝 카드(영상): 훅만
        _compose(2, True).save(thumb_png, quality=90)           # 썸네일: 훅 + 제목
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

    # 0) 영상 내용 파악(비전) — 소싱 출처 설명이 있으면 근거로 합치고, 없으면 프레임을 보고 서술
    desc = (source_topic or "").strip()
    seen = _describe_video(str(vp), work)
    if seen:
        desc = (desc + "\n" + seen).strip() if desc else seen
    if not desc:
        raise ValueError("영상 내용을 파악하지 못했습니다(GEMINI_API_KEY 또는 소싱 출처 설명 필요).")

    # 1) 일본어 대본(청크) — 영상 내용을 근거로 LLM 생성(실패 시 결정론 폴백)
    chunks = _jp_script("", desc, mode)
    if not chunks:
        raise ValueError("나레이션 대본을 만들 수 없습니다.")

    # 2) 나레이션 합성(일본어 TTS + 표시 타이밍)
    from src.core import narration_sync
    nar = narration_sync.synthesize(chunks, str(work))
    if not nar.get("mp3") or not nar.get("disp"):
        raise ValueError("나레이션 합성 실패(TTS)")
    dur = float(nar["duration"]) + 0.6

    # 3) 영상 정규화(쇼츠=9:16 추적 리프레임 · 롱폼=16:9 cover)
    body_v = str(work / "body.mp4")
    if mode == "shorts":
        from src.core import reframe
        body_v = reframe.reframe_to_vertical(str(vp), body_v, dur, str(work / "rf"), wide=False)
    else:
        _normalize_landscape(str(vp), body_v, dur, str(work))

    # 4) 카라오케 자막 번인
    sub_scale = 1.5 if mode == "shorts" else 1.0
    ass = narration_sync.build_synced_ass(nar["disp"], str(work / "subs.ass"),
                                          hook_first=False, w=w, h=h, sub_scale=sub_scale)
    subbed = str(work / "subbed.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", body_v, "-vf", f"ass={ass}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-an", subbed],
                   check=True, timeout=900)

    # 5) 나레이션 오디오 mux → 본문 완성본(훅 앞에 붙이기 전 단계)
    name = out_name or f"narrated_{mode}"
    final = str(out_dir / f"{name}.mp4")
    body_final = str(work / "body_final.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", subbed, "-i", nar["mp3"],
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", body_final],
                   check=True, timeout=300)

    # 6) 대본 → 공개용 메타데이터(제목·설명·해시태그·훅, 일본어+한국어) 자동 생성
    meta = _gen_metadata(chunks, mode)
    meta_path = out_dir / f"{name}.meta.json"
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    # 7) 오프닝 훅(타이틀 카드) 생성 + 유튜브 썸네일 저장(운영자 확정 · 실패해도 발행 불정지)
    thumb_path = out_dir / f"{name}_thumb.jpg"
    hook_txt = (meta.get("hook_jp") or "").strip()
    hooked = False
    try:
        from src.core import hook_intro as hi
        if hook_txt and hi.fonts_available():
            hero = _pick_hero_frame(str(vp), work / "hero", w)
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
    else:
        thumb_out = str(thumb_path) if thumb_path.exists() else ""

    log.info("[narrate] 완성: %s (%s · %.1fs · %d청크 · 훅=%s · 썸=%s) title=%s",
             final, mode, dur, len(chunks), hooked, bool(thumb_out), meta.get("title_jp", ""))
    return {"path": final, "duration": dur, "mode": mode, "chunks": chunks,
            "meta": meta, "meta_path": str(meta_path), "description": desc,
            "hooked": hooked, "thumb": thumb_out, "width": w, "height": h}
