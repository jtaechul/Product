"""하이브리드 오프닝 1컷 — Gemini Veo 3.1로 '제품 사진 → 무음 9:16 클립' 생성.

설계(docs/semi-auto-workflow.md): 오프닝 히어로 컷 1개만 Veo로 만들고(비용 최소화),
나머지 구간은 무료 스틸 모션(켄번즈)으로 채운다. Veo 실패/미설정 시 None을 반환해
파이프라인이 스틸로 자동 폴백한다(제작이 멈추지 않음).

핵심 교훈 내장: 프롬프트 본문에 '형태 유지·글자 왜곡 금지'를 넣어 제품이 뭉개지지 않게 한다.

API (2026-07, Gemini Developer API):
  시작: POST {BASE}/models/{model}:predictLongRunning  (헤더 x-goog-api-key)
        body: {"instances":[{"prompt":..,"image":{"bytesBase64Encoded":..,"mimeType":..}}],
               "parameters":{"aspectRatio":"9:16","generateAudio":false,..}}
  폴링: GET {BASE}/{operation.name}  → done=true 되면 response에서 mp4 추출
비용: Veo 3.1 Fast 무음 ≈ $0.10/초. 시크릿: SHORTS_GEMINI_API_KEY.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "veo-3.1-fast-generate-preview"   # 저가 Fast(하이브리드). 표준은 veo-3.1-generate-preview
DEFAULT_NEGATIVE = ("distorted product, warped shape, extra objects, morphing text, fake ui, "
                    "garbled letters, changing logo, watermark, low quality, jitter, flicker")


def api_key() -> str:
    return (os.environ.get("SHORTS_GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()


def is_configured() -> bool:
    return bool(api_key())


def build_hero_prompt(product: dict) -> str:
    """제품 정보로 오프닝 히어로 컷 프롬프트 구성 (형태 유지·글자 왜곡 방지 내장)."""
    name = str((product or {}).get("title") or (product or {}).get("name") or "이 제품").strip()
    return (
        f"Cinematic vertical product commercial opening shot of this exact product ({name}). "
        "The camera slowly pushes in with smooth, premium motion in a clean, softly lit modern setting. "
        "Keep the product identical to the reference image — same shape, color, proportions and details, "
        "no distortion, no morphing, no added or changed text or logos, no invented UI or screen content. "
        "Shallow depth of field, gentle bokeh, high-end advertising look, 9:16 vertical."
    )


def generate_hero_clip(image_path, prompt: str, out_path,
                       settings: dict | None = None, negative: str | None = None):
    """제품 사진 → 오프닝 무음 클립 1개. 성공 시 out_path(Path), 실패/미설정 시 None(→스틸 폴백)."""
    key = api_key()
    if not key:
        print("[veo] SHORTS_GEMINI_API_KEY 없음 → Veo 건너뜀(스틸 폴백)")
        return None
    cfg = ((settings or {}).get("veo") or {})
    if not cfg.get("enabled", True):
        print("[veo] 설정에서 비활성(veo.enabled=false) → 스틸 폴백")
        return None

    model = cfg.get("model", DEFAULT_MODEL)
    seconds = int(cfg.get("seconds", 8))
    aspect = cfg.get("aspect_ratio", "9:16")
    timeout = int(cfg.get("poll_timeout", 300))
    interval = max(3, int(cfg.get("poll_interval", 10)))
    image_path = Path(image_path)

    try:
        if not image_path.exists():
            print(f"[veo] 씨앗 이미지 없음({image_path}) → 스틸 폴백")
            return None
        mime = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        params = {"aspectRatio": aspect, "generateAudio": False,
                  "negativePrompt": negative or DEFAULT_NEGATIVE}
        if seconds:
            params["durationSeconds"] = seconds
        body = {
            "instances": [{
                "prompt": prompt,
                "image": {"bytesBase64Encoded": base64.b64encode(image_path.read_bytes()).decode(),
                          "mimeType": mime},
            }],
            "parameters": params,
        }
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        r = requests.post(f"{BASE}/models/{model}:predictLongRunning",
                          json=body, headers=headers, timeout=60)
        if not r.ok:
            print(f"[veo] 시작 실패 {r.status_code}: {r.text[:200]} → 스틸 폴백")
            return None
        op = r.json().get("name")
        if not op:
            print(f"[veo] operation name 없음: {r.text[:200]} → 스틸 폴백")
            return None
        print(f"[veo] 생성 시작({model}, {seconds}s, 무음) op={op}")

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(interval)
            pr = requests.get(f"{BASE}/{op}", headers={"x-goog-api-key": key}, timeout=60)
            if not pr.ok:
                print(f"[veo] 폴링 실패 {pr.status_code}: {pr.text[:150]} → 스틸 폴백")
                return None
            j = pr.json()
            if j.get("error"):
                print(f"[veo] 생성 오류: {str(j['error'])[:200]} → 스틸 폴백")
                return None
            if j.get("done"):
                data = _extract_video_bytes(j.get("response") or {}, key)
                if not data:
                    print(f"[veo] 응답에서 영상 추출 실패: {str(j.get('response'))[:200]} → 스틸 폴백")
                    return None
                out_path = Path(out_path)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(data)
                print(f"[veo] 완료 → {out_path} ({len(data) // 1024}KB)")
                return out_path
        print(f"[veo] 폴링 타임아웃({timeout}s) → 스틸 폴백")
        return None
    except Exception as e:
        print(f"[veo] 예외({type(e).__name__}: {e}) → 스틸 폴백")
        return None


def _extract_video_bytes(response: dict, key: str):
    """여러 응답 스키마를 방어적으로 처리해 mp4 bytes 반환(없으면 None).
    base64(bytesBase64Encoded) 우선, 없으면 uri를 키로 다운로드."""
    samples = []
    for path in (("videos",),
                 ("generateVideoResponse", "generatedSamples"),
                 ("generatedSamples",),
                 ("generateVideoResponse", "videos")):
        node = response
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
        if isinstance(node, list) and node:
            samples = node
            break

    for s in samples:
        vid = s.get("video", s) if isinstance(s, dict) else {}
        b64 = (vid.get("bytesBase64Encoded") if isinstance(vid, dict) else None) \
            or (s.get("bytesBase64Encoded") if isinstance(s, dict) else None)
        if b64:
            try:
                return base64.b64decode(b64)
            except Exception:
                pass
        uri = (vid.get("uri") if isinstance(vid, dict) else None) \
            or (s.get("uri") if isinstance(s, dict) else None)
        if uri:
            try:
                dl = requests.get(uri, headers={"x-goog-api-key": key}, timeout=120)
                if dl.ok and dl.content:
                    return dl.content
            except Exception:
                pass
    return None
