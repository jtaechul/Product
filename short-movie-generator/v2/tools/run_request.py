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


def _fit_9x16(src: Path, dst: Path) -> Path:
    """시작·끝 프레임을 정확한 9:16(720x1280)으로 가운데 맞춤 — 두 프레임에 같은 변환을 적용해
    구도가 어긋나지 않게 한다(격자에서 잘린 칸은 비율이 9:16에서 조금 벗어난다)."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf",
                    "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=720:1280,setsar=1",
                    "-q:v", "2", str(dst)], check=True)
    return dst


def gen_video(req: dict, pilot: Path, out: Path) -> dict:
    """Veo 영상 생성(시작 프레임 + 선택적 끝 프레임). 끝 프레임이 거절되면 그 사유를 기록하고
    시작 프레임만으로 한 번 더 시도한다 → '결제 연결'과 '끝 프레임 지원 여부'를 한 번에 확인."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return {"ok": False, "error": "GEMINI_API_KEY 없음"}
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=key)
    results = []
    for it in req["items"]:
        model = it.get("model", "veo-3.1-lite-generate-preview")
        if it.get("start_from"):
            # ★장면 안 이어붙이기(Lite는 끝 프레임 미지원): 앞 클립의 **마지막 프레임**을 시작으로 쓴다
            prev = next((r for r in results if r["name"] == it["start_from"]), None)
            if not prev or "file" not in prev:
                results.append({"name": it["name"], "model": model, "attempts": [],
                                "error": f"앞 클립({it['start_from']}) 실패 → 건너뜀"})
                continue
            start = out / f"{it['name']}_start.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.1", "-i",
                            str(out / prev["file"]), "-frames:v", "1", "-vf", "scale=720:1280,setsar=1",
                            "-q:v", "2", str(start)], check=True)
        else:
            start = _fit_9x16(pilot / it["start"], out / f"{it['name']}_start.jpg")
        end = _fit_9x16(pilot / it["end"], out / f"{it['name']}_end.jpg") if it.get("end") else None
        rec = {"name": it["name"], "model": model, "duration_s": it.get("duration", 4), "attempts": []}

        # ★Veo 3.1 Lite는 negativePrompt 설정을 400으로 거절한다(실측 2026-09-27) → 프롬프트 문장에 합친다
        neg = it.get("negative_prompt") or req.get("negative_prompt")
        prompt = it["prompt"] + (f" Avoid: {neg}." if neg else "")

        def run(with_end: bool):
            cfg = dict(aspect_ratio="9:16", resolution=it.get("resolution", "720p"),
                       duration_seconds=int(it.get("duration", 4)), number_of_videos=1)

            if with_end:
                cfg["last_frame"] = types.Image(image_bytes=end.read_bytes(), mime_type="image/jpeg")
            t0 = time.time()
            op = client.models.generate_videos(
                model=model, prompt=prompt,
                image=types.Image(image_bytes=start.read_bytes(), mime_type="image/jpeg"),
                config=types.GenerateVideosConfig(**cfg))
            while not op.done:
                if time.time() - t0 > 900:
                    raise TimeoutError("Veo 폴링 15분 초과")
                time.sleep(10)
                op = client.operations.get(op)
            resp = getattr(op, "response", None) or getattr(op, "result", None)
            if not resp or not getattr(resp, "generated_videos", None):
                err = getattr(op, "error", None)
                raise RuntimeError(f"영상 없음: {str(err)[:200] if err else '응답 비어 있음(안전 필터 가능)'}")
            v = resp.generated_videos[0].video
            client.files.download(file=v)
            fn = out / f"{it['name']}{'' if (with_end or not end) else '_start_only'}.mp4"
            v.save(str(fn))
            return fn, round(time.time() - t0, 1)

        for with_end in ([True, False] if end else [False]):
            try:
                fn, secs = run(with_end)
                dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                            "-of", "csv=p=0", str(fn)], capture_output=True, text=True).stdout or 0)
                sheet = out / f"{fn.stem}_frames.jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(fn), "-vf",
                                f"fps=4/{max(dur, 0.1):.2f},scale=240:-2,tile=4x1:margin=4:padding=4:color=white",
                                "-frames:v", "1", str(sheet)], check=False)
                rec["attempts"].append({"with_end_frame": with_end, "ok": True, "file": fn.name,
                                        "video_s": round(dur, 2), "wait_s": secs, "frames": sheet.name})
                rec["file"] = fn.name
                break
            except Exception as e:  # noqa: BLE001
                rec["attempts"].append({"with_end_frame": with_end, "ok": False, "error": str(e)[:300]})
        results.append(rec)
    return {"ok": all("file" in r for r in results), "items": results}


def _find_video(o):
    """Interactions 응답에서 영상(base64 data 또는 uri)을 찾는다 — 필드 위치가 SDK·REST 문서마다 달라 재귀 탐색."""
    if isinstance(o, dict):
        mt = str(o.get("mime_type") or o.get("mimeType") or "")
        if (o.get("type") == "video" or mt.startswith("video")) and (o.get("data") or o.get("uri")):
            return o
        for k in ("output_video", "outputVideo"):
            if isinstance(o.get(k), dict) and (o[k].get("data") or o[k].get("uri")):
                return o[k]
        for v in o.values():
            f = _find_video(v)
            if f:
                return f
    elif isinstance(o, list):
        for v in o:
            f = _find_video(v)
            if f:
                return f
    return None


def _strip_data(o):
    if isinstance(o, dict):
        return {k: (f"<{len(v)} chars>" if k == "data" and isinstance(v, str) else _strip_data(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [_strip_data(v) for v in o]
    return o


def gen_omni(req: dict, pilot: Path, out: Path) -> dict:
    """Gemini Omni Flash(Interactions API, REST) 영상 생성 — Veo Lite와 1:1 비교용.

    item: start(시작 이미지) 또는 extend_from(앞 클립을 '이어 늘리기' task=extend) + prompt.
    extend가 실패하면 앞 클립 마지막 프레임을 시작으로 image_to_video 재시도(기록 남김)."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        return {"ok": False, "error": "GEMINI_API_KEY 없음"}
    model = req.get("model", "gemini-omni-1.1-flash")
    hdr = {"x-goog-api-key": key, "Content-Type": "application/json"}
    results = []

    def call(inputs: list, task: str):
        body = {"model": model, "input": inputs,
                "response_format": {"type": "video", "aspect_ratio": "9:16",
                                    "resolution": req.get("resolution", "720p")},
                "generation_config": {"video_config": {"task": task}}}
        t0 = time.time()
        st, raw = _http(f"{API}/interactions", json.dumps(body).encode(), hdr, timeout=900)
        if st != 200:
            raise RuntimeError(f"HTTP {st}: {raw[:300].decode('utf-8', 'replace')}")
        j = json.loads(raw)
        while not _find_video(j) and j.get("id") and str(j.get("status", "")).lower() in (
                "in_progress", "pending", "running", "queued"):
            if time.time() - t0 > 900:
                raise TimeoutError("Omni 폴링 15분 초과")
            time.sleep(10)
            st, raw = _http(f"{API}/interactions/{j['id']}", None, hdr)
            j = json.loads(raw) if st == 200 else j
        v = _find_video(j)
        if not v:
            raise RuntimeError(f"영상 없음: {json.dumps(_strip_data(j), ensure_ascii=False)[:400]}")
        if v.get("data"):
            vid = base64.b64decode(v["data"])
        else:
            fid = str(v["uri"]).rstrip("/").split("/")[-1]
            for _ in range(90):
                st, raw = _http(f"{API}/files/{fid}", None, hdr)
                if st == 200 and json.loads(raw).get("state") == "ACTIVE":
                    break
                time.sleep(5)
            st, vid = _http(f"{API}/files/{fid}:download?alt=media", None, hdr)
            if st != 200:
                raise RuntimeError(f"다운로드 실패 HTTP {st}")
        return vid, round(time.time() - t0, 1), _strip_data(j)

    def img(p: Path) -> dict:
        return {"type": "image", "data": base64.b64encode(p.read_bytes()).decode(), "mime_type": "image/jpeg"}

    for it in req["items"]:
        rec = {"name": it["name"], "model": model, "attempts": []}
        prev = next((r for r in results if r["name"] == it.get("extend_from")), None) if it.get("extend_from") else None
        plans = []
        if it.get("extend_from"):
            if not prev or "file" not in prev:
                rec["error"] = f"앞 클립({it['extend_from']}) 실패 → 건너뜀"
                results.append(rec)
                continue
            pv = out / prev["file"]
            plans.append(("extend", [{"type": "video", "data": base64.b64encode(pv.read_bytes()).decode(),
                                      "mime_type": "video/mp4"}, {"type": "text", "text": it["prompt"]}]))
            last = out / f"{it['name']}_start.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.1", "-i", str(pv),
                            "-frames:v", "1", "-q:v", "2", str(last)], check=True)
            plans.append(("image_to_video", [img(last), {"type": "text", "text": it["prompt"]}]))
        else:
            start = _fit_9x16(pilot / it["start"], out / f"{it['name']}_start.jpg")
            plans.append(("image_to_video", [img(start), {"type": "text", "text": it["prompt"]}]))
        for task, inputs in plans:
            try:
                vid, secs, meta = call(inputs, task)
                fn = out / f"{it['name']}.mp4"
                fn.write_bytes(vid)
                dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                            "-of", "csv=p=0", str(fn)], capture_output=True, text=True).stdout or 0)
                sheet = out / f"{fn.stem}_frames.jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(fn), "-vf",
                                f"fps=4/{max(dur, 0.1):.2f},scale=240:-2,tile=4x1:margin=4:padding=4:color=white",
                                "-frames:v", "1", str(sheet)], check=False)
                rec["attempts"].append({"task": task, "ok": True, "file": fn.name, "video_s": round(dur, 2),
                                        "wait_s": secs, "frames": sheet.name,
                                        "usage": meta.get("usage") or meta.get("usageMetadata")})
                rec["file"] = fn.name
                break
            except Exception as e:  # noqa: BLE001
                rec["attempts"].append({"task": task, "ok": False, "error": str(e)[:400]})
        results.append(rec)
    return {"ok": all("file" in r for r in results), "items": results}


def main(path: str) -> int:
    rp = Path(path)
    req = json.loads(rp.read_text(encoding="utf-8"))
    pilot = rp.parent.parent
    out = pilot / "out" / req["id"]
    out.mkdir(parents=True, exist_ok=True)
    fn = {"fetch_refs": fetch_refs, "gen_images": gen_images, "gen_video": gen_video, "gen_omni": gen_omni}[req["kind"]]
    res = fn(req, pilot, out)
    res.update({"request": rp.name, "kind": req["kind"], "ran_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    (out / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "frames"}, ensure_ascii=False)[:1500])
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
