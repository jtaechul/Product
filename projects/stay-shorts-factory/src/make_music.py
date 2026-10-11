#!/usr/bin/env python3
"""대표 배경음악 1곡 — Gemini API 의 Lyria 3.5 로 만든다 (2026-10-11 운영자 "제미나이로 대표 배경음악을 하나 만들어, 1분짜리").

- 호출: POST https://generativelanguage.googleapis.com/v1beta/interactions {"model":"lyria-3.5","input": 프롬프트}
  → 응답의 오디오(base64, 기본 MP3)를 저장. 공개 문서(ai.google.dev/gemini-api/docs/music-generation) 기준. 동기 호출.
- 비용: Lyria 3.5 **한 곡 $0.08 ≈ 118원** (공개 가격표 · 무료 구간 없음). 요청이 받아들여진 순간 장부(state/spend.json, kind "music")에 적는다.
  이 스크립트는 운영자가 requests/music/request.json 의 nonce 를 바꿔 푸시할 때만 돈다 (stay-shorts-music 워크플로).
- 출력: assets/music/<name>.mp3 (seconds 초 · 0.5초 페이드인 · 1.5초 페이드아웃 · 라우드니스 -18 LUFS · 44.1kHz 스테레오)
  + assets/music/bgm.mp3 (대표 복사본 — make_solo 가 제작 때 자동으로 깔고 나레이션 아래로 덕킹) + <name>.json (프롬프트·비용 기록).
요청: {"nonce":"m1","name":"bgm_01","seconds":60,"prompt":"(선택, 영어)","representative":true}
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import veo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = os.environ.get("STAY_MUSIC_MODEL", "lyria-3.5")
KRW_PER_SONG = float(os.environ.get("MUSIC_USD", "0.08")) * float(os.environ.get("USD_KRW", "1470"))
OUT_DIR = ROOT / "assets" / "music"
REQ = ROOT / "requests" / "music" / "request.json"
DEFAULT_PROMPT = ("Instrumental only, no vocals, no lyrics, no spoken words. Warm, cozy and hopeful background music for a short vertical travel video "
                  "about a hotel with a heated indoor pool on a cold late-autumn day in Korea. Soft felt piano, light acoustic guitar, gentle lo-fi drums, "
                  "subtle warm synth pads, 92 bpm, major key, steady loopable groove, no drops, no dramatic changes, no sound effects, "
                  "consistent energy from start to end, about 70 seconds long.")


def log(*a):
    print("[music]", *a, flush=True)


def _key() -> str:
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    return k


def _find_audio(o):
    """응답 어디에 있든 {"type":"audio","data":base64} 블록(또는 output_audio)을 찾는다."""
    if isinstance(o, dict):
        if (o.get("type") == "audio" or "mime_type" in o or "mimeType" in o) and isinstance(o.get("data"), str) and len(o["data"]) > 1000:
            return o
        for k in ("output_audio", "outputAudio"):
            v = o.get(k)
            if isinstance(v, dict) and isinstance(v.get("data"), str):
                return v
        for v in o.values():
            r = _find_audio(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_audio(v)
            if r:
                return r
    return None


def generate(prompt: str, out_raw: Path, name: str, nonce: str) -> dict:
    body = {"model": MODEL, "input": prompt}
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    log(f"{MODEL} 요청 (약 {KRW_PER_SONG:,.0f}원) …")
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"HTTP {e.code}: {msg}") from None
    veo.record_est("music", KRW_PER_SONG, f"{MODEL} 1곡 {name} ({nonce})")      # 요청이 받아들여진 순간 적는다 (보수적)
    hit = _find_audio(data)
    if not hit:
        raise RuntimeError("응답에 오디오가 없습니다: " + json.dumps(data, ensure_ascii=False)[:400])
    raw = base64.b64decode(hit["data"])
    out_raw.write_bytes(raw)
    text = ""
    for st in data.get("steps") or []:
        for c in st.get("content") or []:
            if isinstance(c, dict) and c.get("type") == "text":
                text += str(c.get("text", ""))
    return {"mime": hit.get("mime_type") or hit.get("mimeType") or "", "bytes": len(raw), "id": data.get("id"), "text": text[:300]}


def probe(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def finalize(raw: Path, out: Path, seconds: float) -> float:
    """seconds 초로 자르고(짧으면 반복) 페이드·라우드니스 정리 → mp3."""
    dur = probe(raw)
    loop = ["-stream_loop", "-1"] if 0 < dur < seconds else []
    af = f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0.0, seconds - 1.5):.2f}:d=1.5,loudnorm=I=-18:TP=-1.5:LRA=11"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *loop, "-i", str(raw), "-t", f"{seconds:.2f}", "-af", af,
                    "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "160k", str(out)], check=True)
    return probe(out)


def main() -> int:
    req = json.loads(REQ.read_text(encoding="utf-8")) if REQ.exists() else {}
    name = str(req.get("name") or "bgm_01").strip()
    seconds = float(req.get("seconds") or 60)
    prompt = str(req.get("prompt") or DEFAULT_PROMPT).strip()
    nonce = str(req.get("nonce") or "")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    build = ROOT / "build"
    build.mkdir(parents=True, exist_ok=True)
    raw = build / f"music_raw_{name}.bin"
    info = {"name": name, "model": MODEL, "date": date.today().isoformat(), "nonce": nonce, "seconds": seconds, "prompt": prompt,
            "krw_est": round(KRW_PER_SONG), "ok": False}
    try:
        g = generate(prompt, raw, name, nonce)
        info.update(g)
        info["raw_sec"] = round(probe(raw), 2)
        out = OUT_DIR / f"{name}.mp3"
        info["out_sec"] = round(finalize(raw, out, seconds), 2)
        info["ok"] = True
        if req.get("representative", True):
            shutil.copy(out, OUT_DIR / "bgm.mp3")
            info["representative"] = "bgm.mp3"
        log(f"완료: {out.name} {info['out_sec']}초 (원곡 {info['raw_sec']}초 · {info['bytes']:,}바이트)")
    except Exception as e:  # noqa: BLE001
        info["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        log("실패:", info["error"])
    (OUT_DIR / f"{name}.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: info[k] for k in info if k != "prompt"}, ensure_ascii=False))
    return 0 if info["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
