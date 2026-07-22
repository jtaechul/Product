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
    return {
        "title_jp": title_jp, "title_ko": "",
        "desc_jp": desc_jp, "desc_ko": "",
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
        '{\"title_jp\":\"日本語タイトル(30字以内・クリックを誘う)\",'
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
                out = {
                    "title_jp": str(d.get("title_jp", "")).strip(),
                    "title_ko": str(d.get("title_ko", "")).strip(),
                    "desc_jp": str(d.get("desc_jp", "")).strip(),
                    "desc_ko": str(d.get("desc_ko", "")).strip(),
                    "tags_jp": tj, "tags_ko": tk,
                }
                if out["title_jp"] and out["desc_jp"] and out["tags_jp"]:
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

    # 5) 나레이션 오디오 mux → 완성본
    name = out_name or f"narrated_{mode}"
    final = str(out_dir / f"{name}.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", subbed, "-i", nar["mp3"],
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", final],
                   check=True, timeout=300)
    # 6) 대본 → 공개용 메타데이터(제목·설명·해시태그, 일본어+한국어) 자동 생성
    meta = _gen_metadata(chunks, mode)
    meta_path = out_dir / f"{name}.meta.json"
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    log.info("[narrate] 완성: %s (%s · %.1fs · %d청크) title=%s",
             final, mode, dur, len(chunks), meta.get("title_jp", ""))
    return {"path": final, "duration": dur, "mode": mode, "chunks": chunks,
            "meta": meta, "meta_path": str(meta_path), "description": desc,
            "width": w, "height": h}
