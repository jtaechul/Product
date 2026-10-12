#!/usr/bin/env python3
"""미니어처 연출 시험 — 숙소 사진 + 기준 인형 → (Gemini 이미지 편집) 인물 든 첫 장면 → (Veo) 4초 영상.

2026-10-12 운영자 "진행해" (숙소 사진 합성 2장 + Veo 2컷, 약 710원 승인).
- 인물 규칙의 단일 출처: data/prompts/miniature.md 의 캐릭터 블록(코드 블록 그대로) + assets/characters/ref.jpg(기준 이미지).
- ① 합성: 숙소 사진(9:16 로 자른 것) + ref.jpg + [편집 지시 + 캐릭터 블록(사진 편집용으로 SCALE·PHOTOGRAPHY 교체) + 장면] → 첫 장면 1장.
     숙소 사진은 그대로 두고 인형만 넣는다(흐림·색 변경·덧그리기 금지). 인형은 앞쪽 가까이(강제 원근)라 화면 높이 약 1/3.
- ② 영상: 첫 장면 → Veo 3.1 Lite 4초(720p · 9:16). 인형 모습은 첫 장면 그대로 유지, 동작만 장면 블록의 4초 타임라인.
- AI 검수 호출 없음(운영자 "검수는 돈"). 결과는 운영자가 텔레그램으로 본다.
- 돈: 이미지 편집 장당 추정(flash 계열 $0.039 ≈ 57원, pro 계열 $0.134 ≈ 197원 — 확실하지 않음, 장부 kind "image"),
  Veo 4초 294원(veo.py 가 한도·장부 처리). 요청에 "veo_approved": true 가 있어야 돈을 쓴다.
- 사진 파일·합성 결과는 커밋하지 않는다(공식 홈페이지 사진 재배포 금지 규칙) — Actions 아티팩트·텔레그램으로만.
요청: requests/mini/request.json {"nonce","veo_approved":true,"shots":[{"key","url","focus_x","scene","motion"}], "image_model"(선택)}
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import veo  # noqa: E402
import crawl_photos  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requests" / "mini" / "request.json"
RULES = ROOT / "data" / "prompts" / "miniature.md"
REF = ROOT / "assets" / "characters" / "ref.jpg"
BUILD = ROOT / "build" / "mini"
REPORT = ROOT / "data" / "runs" / "mini" / "report.json"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
FX = float(os.environ.get("USD_KRW") or 1470)
FAKE_IMG = os.environ.get("MINI_FAKE_IMAGE", "") == "1"          # 로컬 시험: 이미지 편집 대신 ref 를 붙인 가짜 합성(0원)
W, H = 720, 1280

KEEP_LINE = ("Keep both figures exactly identical to the attached reference figurines — same faces, hairstyles, "
             "body proportions, skin tone and swimwear.")
EDIT_HEAD = ("TASK: Edit the FIRST attached image, a real hotel photograph. Keep the photograph exactly as it is — same framing, walls, "
             "water, furniture, decorations, colors, lighting and focus; do not blur, recolor, crop, extend, clean up or redraw anything, "
             "and do not add or remove any object. Only add the two miniature figurines shown in the SECOND attached image (the reference), "
             "placed into the scene as described below, with correct contact shadows, reflections and water interaction so they look "
             "physically present in the photograph.")
EDIT_SCALE = ("SCALE AND PLACEMENT (forced perspective): the figurines are 10 cm toys placed very close to the camera in the lower "
              "foreground, so each figure appears about one third of the frame height, while the real place behind them keeps its true "
              "size and stays clearly recognizable. Never enlarge or shrink anything in the photograph.")
EDIT_PHOTO = ("PHOTOGRAPHY: realistic toy photography matched to the photograph's own light direction, color temperature and grain; "
              "figures tack-sharp; the background keeps the photograph's existing sharpness (at most a very gentle natural softness right "
              "behind the figures). Vertical 9:16, same size as the first image.")
EDIT_TAIL = ("PLACEMENT RULE: put the figurines only where that kind of place really exists in the photograph (real water, real pool rim, "
             "real floor). Never add, extend, enlarge, move or replace any pool, water area, floor, wall or structure to make room for them; "
             "if the described spot is farther from the camera, place them there and let them appear smaller. Do not zoom, reframe or shift "
             "the photograph. OUTPUT: exactly one photorealistic image. No text, no captions, no logos, no watermark, no borders.")
MAX_CHANGED = 0.30          # 배경 보존 검사(0원): 원본 대비 바뀐 화면 비율 상한. 실측 mini-1: 잘 된 파도풀 11% · 배경을 다시 그린 스파 67%

VEO_HEAD = ("The first frame is a real hotel photograph with two small hand-sculpted, hand-painted polymer-clay art-doll figurines of a "
            "Korean couple (elegant adult proportions, eight heads tall, satin clay finish). Keep the figurines exactly as they appear in "
            "the first frame for the whole clip: same faces with painted almond eyes and small closed smiling lips, same hairstyles "
            "(woman: dark-brown hair with a left side part in a neat low bun; man: black short dandy cut with a forward fringe), same "
            "cobalt-blue one-piece swimsuit and dark-navy swim shorts, same size and position. They move gently and slowly, slightly "
            "stepwise like stop-motion figurines.")
VEO_TAIL = ("Water, steam and light behave naturally around them. Camera: locked-off with a very slow 5 percent push-in. The hotel place "
            "stays exactly the same as the first frame: no new objects, no new people, no text, no logos, no morphing; the figurines' "
            "faces, hair and swimwear never change; they never turn into real humans. Vertical 9:16, 4 seconds.")


def log(*a):
    print("[mini]", *a, flush=True)


def character_block() -> str:
    """miniature.md 의 첫 코드 블록(캐릭터 블록) — 사진 편집용으로 SCALE·PHOTOGRAPHY 문단만 바꾼다."""
    t = RULES.read_text(encoding="utf-8")
    m = re.search(r"## 1\. 캐릭터 블록.*?```\n(.*?)```", t, re.S)
    if not m:
        raise RuntimeError("miniature.md 에서 캐릭터 블록을 못 찾음")
    paras = [p for p in m.group(1).strip().split("\n\n") if not p.startswith(("SCALE:", "PHOTOGRAPHY:"))]
    return "\n\n".join(paras)


def edit_prompt(scene: str) -> str:
    return "\n\n".join([EDIT_HEAD, KEEP_LINE, character_block(), EDIT_SCALE, EDIT_PHOTO, "SCENE: " + scene.strip(), EDIT_TAIL])


def veo_prompt(motion: str) -> str:
    return " ".join([VEO_HEAD, "MOTION (4 seconds): " + motion.strip(), VEO_TAIL])


# ── 사진 ──────────────────────────────────────────────────────────────
def fetch(url: str, out: Path) -> Path:
    host = urllib.parse.urlparse(url).netloc
    if crawl_photos.DENY.search(host):
        raise RuntimeError(f"금지된 출처(공식 홈페이지만 허용): {host}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (stay-shorts-factory; official photo for a single test)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out.write_bytes(r.read())
    return out


def crop916(src: Path, out: Path, focus_x: float = 0.5, focus_y: float = 0.5) -> Path:
    im = Image.open(src).convert("RGB")
    iw, ih = im.size
    if iw / ih > 9 / 16:
        cw, ch = int(round(ih * 9 / 16)), ih
    else:
        cw, ch = iw, int(round(iw * 16 / 9))
    x = int(min(max(0, focus_x * iw - cw / 2), iw - cw))
    y = int(min(max(0, focus_y * ih - ch / 2), ih - ch))
    im.crop((x, y, x + cw, y + ch)).resize((W, H), Image.LANCZOS).save(out, "JPEG", quality=94)
    return out


# ── Gemini 이미지 편집 ─────────────────────────────────────────────────
def _key() -> str:
    k = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("GEMINI_API_KEY 가 실행 환경에 없습니다")
    return k


def _post(path: str, body: dict, timeout: int = 240) -> dict:
    req = urllib.request.Request(f"{GEMINI}/{path}", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-goog-api-key": _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gemini 오류 HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")


def image_models(prefer: str | None) -> list[str]:
    """이 키로 쓸 수 있는 이미지 편집 모델 — flash 계열(싸다) 먼저, 새 버전 먼저. 이름은 자주 바뀌어 목록을 물어 고른다."""
    names = []
    try:
        req = urllib.request.Request(f"{GEMINI}/models?pageSize=200", headers={"x-goog-api-key": _key()})
        with urllib.request.urlopen(req, timeout=30) as r:
            for m in json.loads(r.read().decode()).get("models", []):
                if "generateContent" in (m.get("supportedGenerationMethods") or []):
                    names.append(m.get("name", "").split("/", 1)[-1])
    except Exception as e:  # noqa: BLE001
        log("모델 목록 조회 실패 → 기본 이름:", str(e)[:100])
    cands = [n for n in names if n.startswith("gemini-") and "image" in n and "tts" not in n]

    def ver(n):
        m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(m.group(1)) if m else 0.0
    cands.sort(key=lambda n: ("pro" in n, -ver(n), "preview" in n, len(n)))
    if prefer:
        cands = [prefer] + [c for c in cands if c != prefer]
    return cands or ["gemini-2.5-flash-image"]


def image_krw(model: str) -> float:
    usd = float(os.environ.get("IMAGE_PRO_USD") or 0.134) if "pro" in model else float(os.environ.get("IMAGE_USD") or 0.039)
    return usd * FX


def composite(base: Path, prompt: str, out: Path, models: list[str], rep: dict) -> Path:
    if FAKE_IMG:
        im = Image.open(base).convert("RGB"); ref = Image.open(REF).convert("RGB")
        ref.thumbnail((W // 2, H // 2)); im.paste(ref, (W // 4, H - ref.height - 60)); im.save(out, "PNG")
        rep["image_model"] = "FAKE"; return out
    parts = [{"text": prompt},
             {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(base.read_bytes()).decode()}},
             {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(REF.read_bytes()).decode()}}]
    last = None
    for model in models:
        for attempt in range(2):
            body = {"contents": [{"role": "user", "parts": parts}],
                    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": "9:16"}}}
            krw = image_krw(model)
            used = veo.month_total("all")
            if used + krw > veo.MONTH_KRW:
                raise RuntimeError(f"이번 달 한도({veo.MONTH_KRW:,.0f}원) — 지금 {used:,.0f}원")
            try:
                data = _post(f"models/{model}:generateContent", body)
            except RuntimeError as e:
                last = e
                if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                    log(f"이미지 모델 {model} 사용 불가 → 다음:", str(e)[:140].replace("\n", " "))
                    break
                raise
            veo.record_est("image", krw, f"{model} 미니어처 합성 {out.name} (추정)")
            rep["image_krw"] = rep.get("image_krw", 0) + round(krw)
            img = None
            for c in data.get("candidates") or []:
                for p in (c.get("content") or {}).get("parts") or []:
                    d = p.get("inlineData") or p.get("inline_data")
                    if d and str(d.get("mimeType") or d.get("mime_type") or "").startswith("image/"):
                        img = base64.b64decode(d["data"])
            if img:
                out.write_bytes(img)
                im = Image.open(out).convert("RGB")
                if im.size != (W, H):
                    im = im.resize((W, int(round(im.height * W / im.width))), Image.LANCZOS)
                    if im.height != H:                                     # 9:16 이 아니면 가운데에서 맞춘다
                        top = max(0, (im.height - H) // 2)
                        im = im.crop((0, top, W, top + H)) if im.height >= H else im.resize((W, H), Image.LANCZOS)
                im.save(out, "PNG")
                rep["image_model"] = model
                log(f"합성 성공 {out.name} · {model} · 약 {krw:,.0f}원")
                return out
            why = json.dumps({k: data.get(k) for k in ("promptFeedback",)}, ensure_ascii=False)[:200]
            fin = [c.get("finishReason") for c in data.get("candidates") or []]
            last = RuntimeError(f"이미지 없음 (finish {fin}) {why}")
            log(f"합성 결과에 이미지가 없음 → 다시 ({attempt + 1}/2):", str(last)[:160])
    raise RuntimeError(f"합성 실패: {last}")


def changed_ratio(base: Path, frame: Path) -> float:
    """합성 결과가 숙소 사진을 얼마나 바꿨는지(0~1) — 작게 줄여 흐린 뒤 밝기 차 28 넘는 칸의 비율. 인형 자리만 바뀌면 0.1~0.25."""
    from PIL import ImageFilter
    a = Image.open(base).convert("L").resize((180, 320)).filter(ImageFilter.GaussianBlur(1.5))
    b = Image.open(frame).convert("L").resize((180, 320)).filter(ImageFilter.GaussianBlur(1.5))
    pa, pb = a.load(), b.load()
    n = sum(1 for y in range(320) for x in range(180) if abs(pa[x, y] - pb[x, y]) > 28)
    return n / (180 * 320)


# ── 확인 시트 ─────────────────────────────────────────────────────────
def frame_at(video: Path, t: float, out: Path) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(out)], check=True)
    return out


def sheet(rows: list[list[tuple[Path, str]]], out: Path) -> Path:
    tw, th, gap, top = 270, 480, 14, 34
    cols = max(len(r) for r in rows)
    im = Image.new("RGB", (gap + cols * (tw + gap), gap + len(rows) * (th + top + gap)), (18, 20, 26))
    d = ImageDraw.Draw(im)
    try:
        from design import font
        f = font(20, bold=False)
    except Exception:  # noqa: BLE001
        f = None
    for r, row in enumerate(rows):
        for c, (p, label) in enumerate(row):
            x, y = gap + c * (tw + gap), gap + r * (th + top + gap)
            d.text((x, y + 4), label, fill=(255, 255, 255), font=f)
            if p and Path(p).exists():
                im.paste(Image.open(p).convert("RGB").resize((tw, th), Image.LANCZOS), (x, y + top))
    im.save(out, "JPEG", quality=88)
    return out


def main():
    req = json.loads(REQ.read_text(encoding="utf-8"))
    BUILD.mkdir(parents=True, exist_ok=True)
    rep = {"nonce": req.get("nonce"), "started": datetime.now().isoformat(timespec="seconds"), "ok": False, "shots": [],
           "veo_model": veo.MODEL, "fake_veo": veo.FAKE, "fake_image": FAKE_IMG}
    if not (veo.FAKE and FAKE_IMG) and req.get("veo_approved") is not True:
        raise SystemExit('유료 시험은 운영자 허락이 필요합니다 — requests/mini/request.json 에 "veo_approved": true')
    models = [] if FAKE_IMG else image_models(req.get("image_model"))
    log("이미지 모델 후보:", models[:4])
    rows = []
    try:
        for s in req["shots"]:
            k = s["key"]
            row = {"key": k, "url": s["url"], "ok": False}
            rep["shots"].append(row)
            src = fetch(s["url"], BUILD / f"{k}_src.jpg")
            base = crop916(src, BUILD / f"{k}_base.jpg", float(s.get("focus_x", 0.5)), float(s.get("focus_y", 0.5)))
            ep = edit_prompt(s["scene"]); (BUILD / f"{k}_edit_prompt.txt").write_text(ep, encoding="utf-8")
            frame = composite(base, ep, BUILD / f"{k}_frame.png", models, rep)
            ch = changed_ratio(base, frame)
            row["changed"] = round(ch, 3)
            if ch > MAX_CHANGED:                                         # 배경을 다시 그렸다 → 한 번만 더, 그래도 넘으면 이 컷은 Veo 를 쓰지 않는다
                log(f"{k}: 숙소 사진이 {ch:.0%} 바뀜(상한 {MAX_CHANGED:.0%}) → 한 번 더 합성")
                frame = composite(base, ep + "\n\nPREVIOUS ATTEMPT FAILED: it redrew or reframed the photograph. Keep every pixel of the photograph except where the figurines are.",
                                  BUILD / f"{k}_frame.png", models, rep)
                ch = changed_ratio(base, frame); row["changed_retry"] = round(ch, 3)
                if ch > MAX_CHANGED:
                    row["skipped"] = f"배경 보존 실패 {ch:.0%} — Veo 생략(돈 아낌)"
                    log(f"{k}: {row['skipped']}")
                    rows.append([(base, f"{k} 숙소 사진"), (frame, f"합성 실패 {ch:.0%} 변경")])
                    continue
            vp = veo_prompt(s["motion"]); (BUILD / f"{k}_veo_prompt.txt").write_text(vp, encoding="utf-8")
            clip = BUILD / f"{k}.mp4"
            krw = veo.make_clip(vp, frame, 4, clip, veo.seed_for("mini", k), mime="image/png")
            row.update({"ok": True, "veo_krw": round(krw), "edit_prompt_chars": len(ep), "veo_prompt_chars": len(vp)})
            mids = [frame_at(clip, t, BUILD / f"{k}_t{t}.jpg") for t in (1.0, 2.5, 3.8)]
            rows.append([(base, f"{k} 숙소 사진"), (frame, "합성 첫 장면"), (mids[0], "영상 1.0초"), (mids[1], "영상 2.5초"), (mids[2], "영상 3.8초")])
        rep["ok"] = True
    except Exception as e:  # noqa: BLE001
        rep["error"] = f"{type(e).__name__}: {str(e)[:400]}"
        log("실패:", rep["error"])
    finally:
        if rows:
            sheet(rows, BUILD / "sheet.jpg")
        rep["veo_spent_krw"] = round(veo.spent_this_run())
        rep["month_veo_krw"] = round(veo.month_total())
        rep["finished"] = datetime.now().isoformat(timespec="seconds")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        log("기록:", json.dumps({k: rep.get(k) for k in ("ok", "image_model", "image_krw", "veo_spent_krw", "error")}, ensure_ascii=False))
    if not rep["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
