#!/usr/bin/env python3
"""사진 1장(인형 합성 첫 장면) → Gemini Omni Flash 영상 1컷. 미니어처 인물 컷 전용 (2026-10-12 운영자 결정 — 비오 라이트는 남녀가 뒤바뀜).

공식 문서 기준(ai.google.dev/gemini-api/docs/omni · 2026-10-12 확인)
    - POST /v1beta/interactions {"model", "input":[{"type":"image","data":b64,"mime_type"}, {"type":"text","text"}],
      "generation_config":{"video_config":{"task":"image_to_video"}}, "response_format":{"type":"video","aspect_ratio":"9:16","resolution":"720p"}}
    - 동기 호출(응답에 base64 mp4). 결과는 steps[type=model_output] 의 content[type=video].data
    - 길이 필드가 없다 → 지시문으로 정한다("exactly N seconds"). 실제 길이는 받은 뒤 ffprobe 로 재고, 비용도 실제 길이·토큰으로 적는다
    - 소리는 늘 만들어진다(지시문으로 대사·음악 금지). 우리는 나레이션·배경음악을 따로 깔고 이 소리는 버린다
가격(공식 가격표 · 2026-10-12): 비디오 출력 $17.50/1M 토큰, 720p 1초 = 5,792 토큰 → 약 $0.101/초(≈149원). 입력 $1.50/1M. 무료 구간 없음.
돈 잠금: 요청 전에 veo.py 와 같은 장부(state/spend.json)로 한 번 실행·한 달 한도를 본다 — 한 달 한도는 Veo·Omni·이미지·글·음성 **전부 합계**로 판단.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import veo  # noqa: E402  (장부·한도·키를 같이 쓴다)

API = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = (os.environ.get("OMNI_MODEL") or "").strip() or "gemini-omni-1.1-flash"
FALLBACK = ["gemini-omni-1.1-flash", "gemini-omni-flash-preview"]
OUT_USD_PER_M, IN_USD_PER_M, TOK_PER_SEC_720 = 17.50, 1.50, 5792
FAKE = (os.environ.get("OMNI_FAKE") or "") == "1"


def log(*a):
    print("[omni]", *a, flush=True)


def sec_krw(sec: float, resolution: str = "720p") -> float:
    scale = {"360p": 1 / 3, "720p": 1.0}.get(resolution, 1.5)          # 360p 는 제3자 자료(1/3, 확실하지 않음) · 1080p 이상은 보수적으로 1.5배
    return sec * TOK_PER_SEC_720 * OUT_USD_PER_M / 1e6 * veo.USD_KRW * scale


def guard(expect_sec: float, resolution: str) -> float:
    krw = sec_krw(expect_sec, resolution)
    if veo._state["spent"] + krw > veo.RUN_KRW:
        raise veo.CapReached(f"한 번 실행 한도({veo.RUN_KRW:,.0f}원) — 여기까지 {veo._state['spent']:,.0f}원, 이 컷 약 {krw:,.0f}원")
    used = veo.month_total("all")
    if used + krw > veo.MONTH_KRW:
        raise veo.CapReached(f"이번 달 한도({veo.MONTH_KRW:,.0f}원) — 지금까지 {used:,.0f}원(전부 합계), 이 컷 약 {krw:,.0f}원")
    return krw


def _find_video(obj):
    """응답 어디에 있든 video/mp4 base64 를 찾는다(문서의 steps/content 구조 + SDK 편의 필드 둘 다)."""
    if isinstance(obj, dict):
        mt = str(obj.get("mime_type") or obj.get("mimeType") or "")
        if (obj.get("type") == "video" or mt.startswith("video/")) and obj.get("data"):
            return obj["data"]
        for v in obj.values():
            r = _find_video(v)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_video(v)
            if r:
                return r
    return None


def _usage_tokens(obj) -> tuple[int, int]:
    """응답의 사용량(있으면) — 입력·출력 토큰. 필드 이름이 바뀔 수 있어 넓게 찾는다."""
    tin = tout = 0
    def walk(o):
        nonlocal tin, tout
        if isinstance(o, dict):
            for k, v in o.items():
                kl = k.lower()
                if isinstance(v, (int, float)):
                    if "input" in kl and "token" in kl:
                        tin = max(tin, int(v))
                    if "output" in kl and "token" in kl:
                        tout = max(tout, int(v))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj.get("usage") or obj.get("usage_metadata") or obj.get("usageMetadata") or {})
    return tin, tout


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def make_clip(prompt: str, image: Path, sec: float, out: Path, mime: str = "image/png", resolution: str = "720p") -> dict:
    """첫 장면 이미지 + 지시문 → mp4. 돌려주는 값: {"krw","sec","model","tokens_out"}. 실패는 veo.VeoError/CapReached."""
    if FAKE:
        log(f"OMNI_FAKE — 가짜 클립 ({sec}초, 0원): {out.name}")
        veo._fake_clip(image, int(round(sec)), out)
        return {"krw": 0.0, "sec": duration(out), "model": "FAKE", "tokens_out": 0}
    est = guard(sec + 1.0, resolution)                                    # 길이 필드가 없어 1초 여유를 두고 본다
    models = [MODEL] + [m for m in FALLBACK if m != MODEL]
    last = None
    for model in models:
        body = {"model": model,
                "input": [{"type": "image", "data": base64.b64encode(image.read_bytes()).decode(), "mime_type": mime},
                          {"type": "text", "text": prompt}],
                "generation_config": {"video_config": {"task": "image_to_video"}},
                "response_format": {"type": "video", "aspect_ratio": "9:16", "resolution": resolution}}
        req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST",
                                     headers={"x-goog-api-key": veo._key(), "Content-Type": "application/json"})
        log(f"영상 요청 {model} ({resolution} · 목표 {sec}초 · 약 {est:,.0f}원 이하 예상): {out.name}")
        try:
            with urllib.request.urlopen(req, timeout=900) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")[:300]
            last = veo.VeoError(f"Omni HTTP {e.code}: {msg}")
            if e.code in (404, 400) and ("not found" in msg.lower() or "model" in msg.lower()):
                log(f"모델 {model} 사용 불가 → 다음:", msg[:120])
                continue
            raise last
        b64 = _find_video(data)
        tin, tout = _usage_tokens(data)
        if not b64:
            # 응답을 받았으면 돈이 나갔을 수 있다 → 보수적으로 예상액을 적는다
            veo._state["spent"] += est
            veo.record_est("omni", est, f"{model} 영상 없음(보수적 기록) {out.name}")
            raise veo.VeoError(f"Omni 응답에 영상이 없음: {json.dumps(data, ensure_ascii=False)[:300]}")
        out.write_bytes(base64.b64decode(b64))
        real = duration(out)
        krw = (tout * OUT_USD_PER_M + tin * IN_USD_PER_M) / 1e6 * veo.USD_KRW if tout else sec_krw(real or sec, resolution)
        veo._state["spent"] += krw
        veo.record_est("omni", krw, f"{model} {resolution} {real:.1f}초 {out.name}" + (f" (토큰 {tout})" if tout else " (길이 기준 추정)"))
        log(f"완료 {out.name} · {real:.1f}초 · 약 {krw:,.0f}원")
        return {"krw": round(krw), "sec": round(real, 2), "model": model, "tokens_out": tout}
    raise last or veo.VeoError("쓸 수 있는 Omni 모델이 없음")
