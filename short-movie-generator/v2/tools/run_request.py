"""제작 체계 v2 — 요청 파일 1개를 실행한다(GitHub Actions에서 호출).

왜 요청 파일 방식인가: GEMINI_API_KEY는 GitHub 시크릿에만 있고(로컬 .env 없음), 위키미디어는
작업 환경 IP를 429로 막는다 → 네트워크·유료 호출은 전부 Actions에서 돈다. 운영자·Claude는
`v2/pilots/<종>/requests/*.json`을 커밋하는 것만으로 단계를 실행하고, 결과는 `out/<요청id>/`에 커밋된다.

지원 kind
- fetch_refs : 라이선스 통과 실사 영상에서 참조 프레임을 균등 추출(비용 0)
- gen_images : Gemini 이미지 모델로 이미지 생성(유료). 항목마다 참조 이미지 첨부 가능

보안: 키는 환경변수로만 받고 절대 출력하지 않는다(헤더로만 전달).
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

API = "https://generativelanguage.googleapis.com/v1beta"
UA = "ShortMovieGeneratorBot/1.0 (https://github.com/jtaechul/Product; research use)"


def _http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 300):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    for i in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            body = e.read()
            if e.code in (429, 500, 503) and i < 3:
                time.sleep(8 * (i + 1))
                continue
            return e.code, body
    return 0, b""


def fetch_refs(req: dict, pilot: Path, out: Path) -> dict:
    """참조 프레임 추출. 첫·끝 5%는 제외(타이틀·검은 화면 회피)."""
    code, body = _http(req["video_url"])
    if code != 200:
        return {"ok": False, "error": f"download http {code}"}
    src = out / "source_video"
    src.write_bytes(body)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout or 0)
    n = int(req.get("count", 8))
    frames = []
    for k in range(n):
        t = dur * (0.05 + 0.90 * k / max(1, n - 1))
        p = out / f"ref_{k:02d}.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(src),
                        "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2", "-q:v", "2", str(p)], check=True)
        frames.append({"file": p.name, "t": round(t, 2)})
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-pattern_type", "glob", "-i", str(out / "ref_*.jpg"),
                    "-filter_complex", "scale=320:-2,tile=4x2:margin=4:padding=4:color=white",
                    "-frames:v", "1", str(out / "contact_sheet.jpg")], check=True)
    src.unlink()   # 원본 영상은 저장소에 넣지 않는다(용량) — 출처 URL로 언제든 재확보
    return {"ok": True, "duration_s": round(dur, 2), "frames": frames,
            "license": req.get("license"), "credit": req.get("credit"), "source": req["video_url"]}


def split_grid(img_path: Path, spec: dict, out: Path) -> list[str]:
    """격자 이미지를 칸별 파일로 자른다. 칸 사이 흰 경계선을 밝기로 찾아 자르고(없으면 등분),
    경계선이 남지 않게 안쪽으로 조금 더 잘라낸다.

    왜: 요금이 '이미지 1장당'이라 4칸을 한 장에 그리면 비용이 1/4이고, 한 번에 그려져 화풍도
    더 잘 맞는다. 단 Veo에 격자를 그대로 넣으면 분할 화면으로 오인하므로 반드시 잘라서 넘긴다."""
    from PIL import Image
    im = Image.open(img_path).convert("RGB")
    W, H = im.size
    rows, cols, names = int(spec["rows"]), int(spec["cols"]), list(spec["names"])
    g = im.convert("L")

    def line_mean(x: int, axis: str) -> float:
        if axis == "x":
            vals = [g.getpixel((x, y)) for y in range(0, H, max(1, H // 200))]
        else:
            vals = [g.getpixel((xx, x)) for xx in range(0, W, max(1, W // 200))]
        return sum(vals) / len(vals)

    def bands(n: int, length: int, axis: str) -> list[tuple[int, int]]:
        """칸 구간 [(시작, 끝), ...]. 경계는 '밝은 띠' 전체를 찾아 그 바깥에서 자른다."""
        edges = [0]
        for k in range(1, n):
            c = length * k // n
            lo, hi = max(1, int(c - length * 0.08)), min(length - 1, int(c + length * 0.08))
            means = {x: line_mean(x, axis) for x in range(lo, hi)}
            best = max(means, key=means.get)
            if means[best] > 200:                       # 흰 경계 띠: 양 끝까지 넓힌다
                a = best
                while a - 1 >= lo and means.get(a - 1, 0) > 200:
                    a -= 1
                b = best
                while b + 1 < hi and means.get(b + 1, 0) > 200:
                    b += 1
                edges += [a, b + 1]
            else:                                        # 경계가 안 보이면 등분
                edges += [c, c]
        edges.append(length)
        return [(edges[2 * i], edges[2 * i + 1]) for i in range(n)]

    xs, ys = bands(cols, W, "x"), bands(rows, H, "y")
    inset = max(4, int(min(W, H) * 0.006))
    saved = []
    for r in range(rows):
        for c in range(cols):
            i = r * cols + c
            if i >= len(names) or not names[i]:
                continue
            box = (xs[c][0] + inset, ys[r][0] + inset, xs[c][1] - inset, ys[r][1] - inset)
            fn = f"{names[i]}.jpg"
            im.crop(box).save(out / fn, quality=95)
            saved.append(fn)
    return saved


def _pick_model(key: str, prefs: list[str]) -> str | None:
    code, body = _http(f"{API}/models?pageSize=1000", headers={"x-goog-api-key": key})
    if code != 200:
        return None
    names = {m["name"].split("/")[-1] for m in json.loads(body).get("models", [])}
    return next((m for m in prefs if m in names), None)


def gen_images(req: dict, pilot: Path, out: Path) -> dict:
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return {"ok": False, "error": "GEMINI_API_KEY 없음"}
    model = _pick_model(key, req.get("model_preference", ["gemini-3-pro-image-preview",
                                                           "gemini-2.5-flash-image"]))
    if not model:
        return {"ok": False, "error": "사용 가능한 이미지 모델 없음"}
    results = []
    for it in req["items"]:
        parts = [{"text": it["prompt"]}]
        for r in it.get("refs", []):
            b = (pilot / r).read_bytes()
            parts.append({"inline_data": {"mime_type": "image/jpeg" if r.endswith((".jpg", ".jpeg"))
                                          else "image/png", "data": base64.b64encode(b).decode()}})
        img_cfg = {"aspectRatio": it.get("aspect", "1:1")}
        if it.get("size"):                       # "2K" 등 — 격자 생성 시 칸 해상도 확보
            img_cfg["imageSize"] = it["size"]
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": img_cfg}}
        code, raw = _http(f"{API}/models/{model}:generateContent",
                          data=json.dumps(body).encode(),
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        rec = {"name": it["name"], "http": code}
        if code == 200:
            d = json.loads(raw)
            imgs = [p["inlineData"] for c in d.get("candidates", [])
                    for p in c.get("content", {}).get("parts", []) if "inlineData" in p]
            if imgs:
                ext = ".png" if "png" in imgs[0].get("mimeType", "") else ".jpg"
                (out / f"{it['name']}{ext}").write_bytes(base64.b64decode(imgs[0]["data"]))
                rec["file"] = f"{it['name']}{ext}"
                if it.get("split"):              # ★격자 1장 → 칸별 단독 파일(Veo엔 칸만 넣는다)
                    rec["panels"] = split_grid(out / rec["file"], it["split"], out)
            else:
                rec["error"] = "이미지 없음(안전 필터 등)"
                rec["finish"] = [c.get("finishReason") for c in d.get("candidates", [])]
            rec["usage"] = d.get("usageMetadata", {})
        else:
            try:
                e = json.loads(raw).get("error", {})
                rec["error"] = f"{e.get('status')}: {(e.get('message') or '')[:200]}"
            except Exception:  # noqa: BLE001
                rec["error"] = f"http {code}"
        results.append(rec)
    return {"ok": all("file" in r for r in results), "model": model, "items": results}


def main(path: str) -> int:
    rp = Path(path)
    req = json.loads(rp.read_text(encoding="utf-8"))
    pilot = rp.parent.parent
    out = pilot / "out" / req["id"]
    out.mkdir(parents=True, exist_ok=True)
    fn = {"fetch_refs": fetch_refs, "gen_images": gen_images}[req["kind"]]
    res = fn(req, pilot, out)
    res.update({"request": rp.name, "kind": req["kind"], "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "frames"}, ensure_ascii=False)[:1500])
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
