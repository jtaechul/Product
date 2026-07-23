"""원본 화면에 박힌 '정적 라벨'(종명·수심·사이트·타이틀 카드 등)을 감지해, 그 위에 딥네이비 라운드
박스를 깔고 일본어 번역을 얹는다(롱폼 전용 · 운영자 확정).

설계(하이브리드): ① 값싼 OCR(tesseract, watermark_qc._ocr_words 재사용)로 '언제·어디에' 텍스트가
지속적으로 떠 있는지(=정적 라벨) 찾고, ② 그 텍스트를 제미나이로 보정·번역하고, ③ 각 라벨 자리에
반투명 아닌 '불투명 딥네이비 라운드 박스 + 일본어'를 그 지속 시간에만 오버레이한다.

안전(발행 불정지): tesseract 미설치·번역 실패·이벤트 없음이면 원본 영상을 그대로 반환한다.
정적 라벨만 대상(움직이는 크레딧은 프레임 간 위치가 안 맞아 자동 제외). 큰 중앙 영역은 피사체를
가릴 수 있어 제외. 롱폼에서만 호출한다(쇼츠는 짧아 원본 텍스트 노출이 적음)."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger("shorts")

# 딥네이비 라운드 박스(우리 디자인 톤). 불투명(원문 완전 가림) + 옅은 골드 테두리.
_BOX_FILL = (12, 20, 34, 255)
_BOX_EDGE = (245, 197, 66, 210)      # 골드 포인트(얇은 테두리)
_TXT = (245, 244, 240, 255)


def _has_tesseract() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def _grab(video: str, t: float, png: str) -> bool:
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
                            "-frames:v", "1", png], capture_output=True, text=True, timeout=60)
        return r.returncode == 0 and Path(png).exists()
    except Exception:  # noqa: BLE001
        return False


def _iou(a: tuple, b: tuple) -> float:
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    iw, ih = max(0.0, x1 - x0), max(0.0, y1 - y0)
    inter = iw * ih
    uni = aw * ah + bw * bh - inter
    return inter / uni if uni > 0 else 0.0


def _blocks_from_words(words: list[dict]) -> list[dict]:
    """OCR 단어들을 근접 병합해 '라벨 블록'([{box:(x,y,w,h) 정규화, text}])으로 묶는다.
    같은 라벨의 여러 단어/줄이 하나의 박스가 되도록 x·y 간격이 작으면 합친다."""
    ws = []
    for w in words:
        t = (w.get("text") or "").strip()
        try:
            conf = float(w.get("conf", -1))
        except (TypeError, ValueError):
            conf = -1
        if conf < 55 or len(t) < 2 or not any(c.isalnum() for c in t):
            continue
        ws.append({"box": [float(w["x"]), float(w["y"]), float(w["w"]), float(w["h"])], "text": t})
    if not ws:
        return []
    GAP = 0.03
    changed = True
    while changed:
        changed = False
        out: list[dict] = []
        while ws:
            a = ws.pop()
            ax, ay, aw, ah = a["box"]
            merged = True
            while merged:
                merged = False
                rest = []
                for b in ws:
                    bx, by, bw, bh = b["box"]
                    # 확장 박스(간격 GAP)로 겹치면 같은 블록
                    if (ax - GAP < bx + bw and bx - GAP < ax + aw and
                            ay - GAP < by + bh and by - GAP < ay + ah):
                        nx, ny = min(ax, bx), min(ay, by)
                        ax2, ay2 = max(ax + aw, bx + bw), max(ay + ah, by + bh)
                        ax, ay, aw, ah = nx, ny, ax2 - nx, ay2 - ny
                        a["text"] = (a["text"] + " " + b["text"]).strip()
                        merged = True; changed = True
                    else:
                        rest.append(b)
                ws = rest
            a["box"] = [ax, ay, aw, ah]
            out.append(a)
        ws = out
    return ws


def _frame_blocks(video: str, t: float, work: Path, idx: int) -> list[dict]:
    from src.core import watermark_qc as wq
    png = work / f"f_{idx}.png"
    if not _grab(video, t, str(png)):
        return []
    try:
        words = wq._ocr_words(png)
    except Exception:  # noqa: BLE001
        return []
    return _blocks_from_words(words)


def _ok_label_box(box: tuple) -> bool:
    """정적 라벨로 받아들일 박스인지(피사체 가림·전면 차지 방지)."""
    x, y, w, h = box
    if w <= 0 or h <= 0:
        return False
    area = w * h
    if area > 0.32 or h > 0.28:                 # 너무 큰 박스 = 화면 대부분 가림 → 제외
        return False
    cx, cy = x + w / 2, y + h / 2               # 중앙 큰 덩어리(피사체 가능성) 제외
    if 0.30 < cx < 0.70 and 0.30 < cy < 0.70 and area > 0.14:
        return False
    return True


def detect_static_text_events(video: str, work: Path, dur: float,
                              step: float = 2.0) -> list[dict]:
    """원본에서 '지속적으로 같은 자리에 떠 있는' 정적 텍스트 라벨을 이벤트로 추출.
    반환 [{t0,t1,box:(x,y,w,h) 정규화, text}]. 움직이는 텍스트는 프레임 간 위치가 안 맞아 자동 제외."""
    work.mkdir(parents=True, exist_ok=True)
    if dur <= 0:
        return []
    times = []
    t = 0.5
    while t < dur - 0.3:
        times.append(round(t, 2)); t += step
    open_ev: list[dict] = []
    done: list[dict] = []
    for i, tt in enumerate(times):
        blocks = [b for b in _frame_blocks(video, tt, work, i) if _ok_label_box(b["box"])]
        used = [False] * len(blocks)
        nxt: list[dict] = []
        for ev in open_ev:
            best, bi = 0.0, -1
            for k, b in enumerate(blocks):
                if used[k]:
                    continue
                s = _iou(tuple(ev["box"]), tuple(b["box"]))
                if s > best:
                    best, bi = s, k
            if best >= 0.35 and bi >= 0:                 # 같은 자리 지속 → 이벤트 연장
                used[bi] = True
                ev["t1"] = tt
                ev["seen"] += 1
                if len(blocks[bi]["text"]) > len(ev["text"]):
                    ev["text"] = blocks[bi]["text"]      # 더 온전히 읽힌 텍스트 채택
                nxt.append(ev)
            else:
                done.append(ev)
        for k, b in enumerate(blocks):
            if not used[k]:
                nxt.append({"t0": tt, "t1": tt, "box": b["box"], "text": b["text"], "seen": 1})
        open_ev = nxt
    done.extend(open_ev)
    # 정적 판정: 최소 지속(≥3초) + 최소 2회 이상 감지(깜빡임·오검 배제)
    out = []
    for ev in done:
        if ev["seen"] >= 2 and (ev["t1"] - ev["t0"]) >= 3.0:
            ev["t0"] = max(0.0, ev["t0"] - step * 0.5)   # 감지 경계 밖 여유(라벨 등장/퇴장 커버)
            ev["t1"] = min(dur, ev["t1"] + step * 0.5)
            out.append({"t0": ev["t0"], "t1": ev["t1"], "box": ev["box"], "text": ev["text"]})
    log.info("[ost] 정적 라벨 이벤트 %d개 감지", len(out))
    return out[:12]                                       # 과다 방지 상한


def _translate_labels_jp(texts: list[str]) -> list[str] | None:
    """OCR로 읽은 라벨들을 제미나이로 보정·번역(한 번 배치, 행수·순서 보존). 실패 시 None."""
    from src.core import llm
    if not texts:
        return None
    src = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(texts))
    prompt = (
        "次の各行は動画画面に焼き込まれたラベル文字を OCR で読み取ったものです（誤認識を含みうる）。"
        "各行を、意味の通る自然な日本語の短いラベルに翻訳してください。明らかな OCR 誤りは文脈で補正。"
        "固有名詞・数値・単位（m, °C など）は保持。★入力と同じ行数・順序で、各行頭に番号を付ける。"
        "説明や記号の装飾は書かない。\n" + src)
    txt = llm.generate_text(prompt, max_tokens=min(1500, 60 + 30 * len(texts)))
    if not txt:
        return None
    import re
    got: dict[int, str] = {}
    for ln in txt.splitlines():
        m = re.match(r"\s*(\d+)[.)、:：\-\s]+(.+)", ln.strip())
        if m:
            got[int(m.group(1))] = m.group(2).strip()
    out = [got.get(i + 1, "").strip() for i in range(len(texts))]
    if sum(1 for x in out if x) < max(1, len(texts) // 2):
        return None
    return out


def _render_event_png(event: dict, W: int, H: int, out_png: str) -> bool:
    """이벤트 1개 → 전체 프레임 크기 투명 PNG에 딥네이비 라운드 박스 + 일본어를 그린다."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        from src.core import hook_intro as hi
        jp = (event.get("jp") or "").strip()
        if not jp:
            return False
        x, y, w, h = event["box"]
        # 원문을 확실히 가리도록 약간 패딩(가로 6% · 세로 40% 여유), 화면 밖으로 안 나가게 클램프
        padx, pady = w * 0.06 + 0.006, h * 0.40 + 0.004
        bx = max(0.0, x - padx); by = max(0.0, y - pady)
        bw = min(1.0 - bx, w + padx * 2); bh = min(1.0 - by, h + pady * 2)
        px, py = int(bx * W), int(by * H)
        pw, ph = max(8, int(bw * W)), max(8, int(bh * H))
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        rad = max(6, int(ph * 0.28))
        d.rounded_rectangle([px, py, px + pw, py + ph], radius=rad, fill=_BOX_FILL,
                            outline=_BOX_EDGE, width=max(1, int(H * 0.0016)))
        # 일본어를 박스 안에 맞춰 크기 자동 조절(가로 폭·줄수 기준)
        pad = int(ph * 0.16)
        maxw = pw - pad * 2
        size = max(12, int(ph * 0.62))
        font = ImageFont.truetype(hi.FONT_SANS_B, size, index=0)
        while size > 12:
            font = ImageFont.truetype(hi.FONT_SANS_B, size, index=0)
            lines = _wrap(d, jp, font, maxw)
            th = len(lines) * int(font.getbbox("あ")[3] * 1.24)
            wmax = max((d.textlength(ln, font=font) for ln in lines), default=0)
            if th <= ph - pad * 2 and wmax <= maxw:
                break
            size -= 2
        lines = _wrap(d, jp, font, maxw)
        line_h = int(font.getbbox("あ")[3] * 1.24)
        ty = py + (ph - line_h * len(lines)) // 2
        for ln in lines:
            lw = d.textlength(ln, font=font)
            tx = px + (pw - lw) // 2
            d.text((tx, ty), ln, font=font, fill=_TXT,
                   stroke_width=max(1, int(size * 0.05)), stroke_fill=(4, 8, 14, 255))
            ty += line_h
        im.save(out_png)
        return Path(out_png).exists()
    except Exception as e:  # noqa: BLE001
        log.info("[ost] 오버레이 렌더 실패: %s", e)
        return False


def _wrap(draw, text: str, font, max_w: float) -> list[str]:
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


def apply(video: str, out: str, work: str, dur: float, W: int, H: int, step: float = 2.0) -> str:
    """정적 화면 라벨을 감지→일본어 번역→딥네이비 박스로 얹은 영상 경로. 없거나 실패면 원본 그대로."""
    wd = Path(work); wd.mkdir(parents=True, exist_ok=True)
    if not _has_tesseract():
        log.info("[ost] tesseract 없음 → 화면 라벨 번역 생략")
        return video
    events = detect_static_text_events(video, wd, dur, step)
    if not events:
        return video
    jps = _translate_labels_jp([e["text"] for e in events])
    if not jps:
        log.info("[ost] 라벨 번역 실패 → 오버레이 생략")
        return video
    for e, jp in zip(events, jps):
        e["jp"] = jp
    pngs: list[tuple] = []
    for i, e in enumerate(events):
        if not e.get("jp"):
            continue
        p = str(wd / f"ost_{i}.png")
        if _render_event_png(e, W, H, p):
            pngs.append((p, e))
    if not pngs:
        return video
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", video]
    for p, _ in pngs:
        cmd += ["-i", p]
    fc = []
    cur = "[0:v]"
    for idx, (_p, e) in enumerate(pngs):
        lab = "[vout]" if idx == len(pngs) - 1 else f"[v{idx}]"
        fc.append(f"{cur}[{idx + 1}:v]overlay=0:0:enable='between(t,{e['t0']:.2f},{e['t1']:.2f})'{lab}")
        cur = lab
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", out]
    try:
        subprocess.run(cmd, check=True, timeout=1800)
    except Exception as e:  # noqa: BLE001
        log.info("[ost] 오버레이 합성 실패 → 원본 사용: %s", e)
        return video
    if Path(out).exists() and Path(out).stat().st_size > 2000:
        log.info("[ost] 화면 라벨 %d개 일본어 오버레이 완료", len(pngs))
        return out
    return video
