#!/usr/bin/env python3
"""⭐ 메인 포맷 「데이터 호캉스 TOP3」 (2026-10-11 확정) — 테마 하나, 숙소 3곳, 25초 안팎.

request.json 예
    {"nonce": "...", "mode": "top3", "theme": "실내 온수풀·온천", "region": "강원", "month": "2026-11",
     "stays": ["소노펠리체 비발디파크", "롯데리조트 속초", "쏠비치 삼척"],   ← 생략하면 data/discover/latest 순위표 상위 3곳
     "fake": true,                                                            ← Veo 대신 가짜 클립(0원) — 포맷 검토용
     "max_veo_cuts": 6}

왜 이 포맷인가 (두 참고 영상 + 운영자 의견 + 우리 데이터를 종합한 결론)
    - 검증된 장치: 1초 안의 질문·감탄 훅 / 숫자 하나 / 혜택은 조건문 / 2초 컷 / 단점 고백 / 저장·링크 행동 지시 / 결론(1위)은 맨 끝
    - 우리만의 무기: "최근 30일 후기 ○○건"(네이버 블로그 집계) — 매주 자동 갱신되는 검증 가능한 숫자. 경쟁 채널엔 없다
    - 쇼핑 전환: 한 영상에 제휴 링크 3개. 숙소당 사진 2장이면 되어 쿠팡 사진 부족 문제도 풀린다
    - 사람·손은 AI 로 넣지 않는다. 질감은 실촬영 스톡 B롤(물결·김)로, 시점은 카메라 움직임으로

구조 (초)
    훅 2.5  →  3위 5 (컷 2 + 컷 2 + B롤 1)  →  2위 5  →  1위 6 (컷·컷 + 단점 한 줄)  →  CTA 3.5   ≈ 22~26초
    자막: 한 줄, 화면 위 1/3, 3~10자. 훅·CTA 는 손글씨체(나눔펜, OFL), 사실 자막은 고딕. 순위·숙소명 뱃지는 왼쪽 아래,
    데이터 뱃지("최근 30일 후기 931건 · 네이버 블로그 기준")는 오른쪽 위. 고지문은 아래 작게 항상.
    나레이션은 구간별로 따로 만들어(TTS 5번) 자막과 정확히 맞춘다.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover as dc  # noqa: E402
import make_stay as ms  # noqa: E402
import photos  # noqa: E402
import stock  # noqa: E402
import veo  # noqa: E402

ROOT = ms.ROOT
BUILD = ms.BUILD
FONT_HAND = ROOT / "assets" / "fonts" / "NanumPenScript-Regular.ttf"
W, H, FPS = ms.W, ms.H, ms.FPS
CUT = 2.0                                   # 컷 길이(초) — Veo 4초 클립의 앞 2초
PLAN = {"hook": 2.5, "rank": 5.0, "top": 6.0, "cta": 3.5}
BROLL = ["calm pool water surface ripples close up", "steam rising from hot spring water", "sunlight reflecting on blue pool water"]
BANNED = ms.BANNED + ["최장", "최대", "국내 유일"]


def log(*a):
    print("[top3]", *a, flush=True)


# ── 1) 숙소 3곳 고르기 ────────────────────────────────────────────────
def pick_candidates(req: dict) -> list[dict]:
    """순위표(data/discover/latest/candidates.json)에서 쿠팡 통과 숙소를 순서대로. stays 가 있으면 그 이름을 먼저."""
    f = ROOT / "data" / "discover" / "latest" / "candidates.json"
    rows = []
    if f.exists():
        rep = json.loads(f.read_text(encoding="utf-8"))
        rows = [c for c in rep.get("candidates") or [] if (c.get("coupang") or {}).get("ok")]
    want = [str(s).strip() for s in (req.get("stays") or []) if str(s).strip()]
    out = []
    for name in want:
        hit = next((c for c in rows if dc.same(name, c["name"])), None)
        out.append(hit or {"name": name, "demand": {}, "coupang": {}, "ai": {}, "facility_checks": []})
    for c in rows:
        if len(out) >= 6:
            break
        if not any(dc.same(c["name"], o["name"]) for o in out):
            out.append(c)
    if len(out) < 3:
        raise RuntimeError("후보가 3곳 미만입니다 — 먼저 stay-shorts-discover 를 돌리거나 request.json 에 stays 3곳을 적어 주세요")
    return out


def hotel_assets(c: dict, models: dict, idx: int) -> dict | None:
    """쿠팡 검색 → 규칙·동일성으로 '이 숙소 객실'만 → 사진 분류 → 물놀이 1 + 객실/특별 1 선택 → 9:16 크롭 + Veo 지시문."""
    name = c["name"]
    v = dc.coupang_verify(name)
    rooms = v.get("rooms") or []
    if len(rooms) >= dc.MIN_ROOMS:
        try:
            idn = ms._try_models("text", models["text"], lambda m: dc.identity(m, name, c.get("city", ""), rooms))
            if idn["confidence"] != "low":
                rooms = idn["rooms"]
        except Exception as e:  # noqa: BLE001
            log(f"{name}: 동일성 판정 실패 — 규칙 통과분 사용 ({str(e)[:60]})")
    if len(rooms) < 2:
        log(f"{name}: 쿠팡 객실 {len(rooms)}개 — 제외")
        return None
    build = BUILD / f"h{idx}"
    build.mkdir(parents=True, exist_ok=True)
    cands = photos.gather(rooms, ROOT / "requests" / "produce" / "photos_none", build)
    if not cands:
        return None
    cl = ms._try_models("vision", models["text"], lambda m: photos.classify(m, cands))
    usable = sorted([p for p in cl if p["category"] in photos.CATS and p["quality"] >= 4 and not p.get("people")],
                    key=lambda p: -p["quality"])
    water = [p for p in usable if p["category"] == "water"]
    other = [p for p in usable if p["category"] != "water"]
    chosen = []
    if water:
        chosen.append(water[0])
    if other:
        chosen.append(other[0])
    for p in usable:
        if len(chosen) >= 2:
            break
        if p not in chosen:
            chosen.append(p)
    if len(chosen) < 2:
        log(f"{name}: 쓸 수 있는 사진 {len(chosen)}장 — 제외")
        return None
    shots = []
    for k, p in enumerate(chosen):
        n = idx * 10 + k + 1
        photos.crop_9x16(p["path"], BUILD / f"shot_{n}.png", p["focus_x"], p["focus_y"])
        shots.append({**p, "n": n, "slot": p["category"], "prompt": photos.prompt_for(p)})
    prices = [float(it.get("productPrice") or 0) for it in rooms if float(it.get("productPrice") or 0) > 0]
    facts = [k["facility"] for k in (c.get("facility_checks") or []) if k.get("verified")][:3]
    return {"name": name, "shots": shots, "room_names": [str(it.get("productName", ""))[:40] for it in rooms[:5]],
            "theme_hits": dc.theme_hits(rooms, dc.DEFAULT_KEYWORDS), "verified_facilities": facts,
            "blog_30d": (c.get("demand") or {}).get("blog_30d"), "blog_total": (c.get("demand") or {}).get("blog_total"),
            "min_price": min(prices) if prices else None, "affiliate_url": str(rooms[0].get("productUrl", "")),
            "hook": (c.get("ai") or {}).get("hook", ""), "classified": cl}


HONEST_SYSTEM = """아래는 한 숙소에 대한 네이버 블로그 글 제목·요약 목록이다. 후기에서 반복되는 '아쉬운 점'이 있으면 한 줄(20자 내, 존댓말 없이 명사형)로 적는다.
없거나 불확실하면 빈 문자열. 지어내지 않는다. JSON 만: {"honest":"..."}"""


def honest_line(model: str, name: str) -> str:
    js = dc._naver_search("blog", f'"{name}" 아쉬운 점', 15)
    items = (js or {}).get("items") or []
    if len(items) < 3:
        return ""
    text = "\n".join(re.sub(r"<[^>]+>", "", f"{it.get('title', '')} — {it.get('description', '')}")[:160] for it in items)
    try:
        return str(ms.gemini_json(model, HONEST_SYSTEM, f"숙소: {name}\n\n{text}").get("honest", "")).strip()[:30]
    except Exception:  # noqa: BLE001
        return ""


# ── 2) 대본 ───────────────────────────────────────────────────────────
SCRIPT_SYSTEM = """너는 "데이터로 고른 호캉스" 쇼츠의 큐레이터다. 1인칭, 짧은 구어체(반말 아님, "~해요"체), 광고 말투 금지. 유행어는 영상 전체에 최대 1개.
입력: 테마·지역·시기, 숙소 3곳(3위→1위 순)의 확인된 사실(쿠팡 객실 이름, 블로그로 확인된 시설, 최근 30일 블로그 글 수, 후기 아쉬움).
절대 규칙
- 입력에 없는 시설·서비스·가격·할인을 말하지 않는다. 가격 숫자 금지. "최고·유일·최저가·1위(순위 외)·완벽·보장·최장·최대" 금지.
- 숫자는 입력의 블로그 글 수만 쓴다 ("최근 30일 후기 931건"). 시설은 '확인된 시설'과 객실 이름에 있는 것만.
- 혜택은 조건문으로 쓴다 (예: "조식 포함 객실을 고르면", "워터파크 이용권이 묶인 객실이 있어요").
- 자막(caption)은 3~10자, 한 줄, 느낌표·이모지 금지. 나레이션(narration)은 한 구간에 최대 2문장·합쳐 34자 이내.
출력 JSON 만:
{"hook":{"caption":"...","narration":"..."},            ← 질문형 훅. 예: 자막 "후기 제일 많은 온수풀은?" / 나레이션 "11월 강원 온수풀, 후기 데이터로 세 곳 골랐어요"
 "ranks":[{"rank":3,"captions":["...","..."],"narration":"...","benefit":"조건문 한 줄"},
          {"rank":2,"captions":["...","..."],"narration":"...","benefit":"..."},
          {"rank":1,"captions":["...","..."],"narration":"...","benefit":"...","honest":"입력의 아쉬움이 있으면 그대로, 없으면 빈 문자열"}],
 "cta":{"caption":"...","narration":"..."},             ← 저장 + 프로필 링크. 예: 자막 "저장해두고 비교하세요" / 나레이션 "세 곳 링크는 프로필에 있어요. 저장해 두고 비교해 보세요"
 "title":"유튜브 제목 12~25자","caption":"인스타 캡션 2문장(고지문·링크는 시스템이 붙임)","hashtags":["#..","#..","#..","#..","#.."]}"""


def check_script(s: dict, hotels: list[dict]) -> list[str]:
    errs = []
    ranks = s.get("ranks") or []
    if [r.get("rank") for r in ranks] != [3, 2, 1]:
        errs.append("ranks 는 3,2,1 순서 3개")
    segs = [s.get("hook") or {}, *ranks, s.get("cta") or {}]
    joined = ""
    for g in segs:
        caps = g.get("captions") or ([g.get("caption")] if g.get("caption") else [])
        for cp in caps:
            if not (2 <= len(str(cp).replace(" ", "")) <= 12):
                errs.append(f"자막 길이: '{cp}'")
        n = str(g.get("narration", ""))
        if not n or len(n.replace(" ", "")) > 40:
            errs.append(f"나레이션 길이: '{n[:20]}'")
        joined += " ".join(map(str, caps)) + n + str(g.get("benefit", "")) + str(g.get("honest", ""))
    joined += str(s.get("title", "")) + str(s.get("caption", ""))
    for b in BANNED:
        if b in joined:
            errs.append(f"금지 표현 '{b}'")
    if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", joined):
        errs.append("가격·할인 숫자")
    return errs


def write_script(model: str, req: dict, hotels: list[dict]) -> dict:
    lines = [f"테마: {req.get('theme')} · 지역: {req.get('region')} · 시기: {req.get('month')}", ""]
    for rank, h in zip((3, 2, 1), hotels):
        lines += [f"[{rank}위] {h['name']}",
                  f"  쿠팡 객실 이름: {', '.join(h['room_names'])}",
                  f"  확인된 시설: {', '.join(h['verified_facilities']) or '없음'} / 객실 이름의 테마 단어: {', '.join(h['theme_hits']) or '없음'}",
                  f"  최근 30일 블로그 글 수: {h['blog_30d'] if h['blog_30d'] is not None else '모름'}",
                  f"  후기 아쉬움: {h.get('honest') or '없음'}", ""]
    content = "\n".join(lines)
    errs = []
    for attempt in range(3):
        extra = ("\n\n직전 답의 문제(고쳐서 다시): " + " / ".join(errs)) if errs else ""
        s = ms.gemini_json(model, SCRIPT_SYSTEM, content + extra)
        errs = check_script(s, hotels)
        if not errs:
            return s
        log(f"대본 검사 실패({attempt + 1}):", errs)
    raise RuntimeError("대본이 규칙을 통과하지 못함: " + " / ".join(errs))


# ── 3) 화면 요소 ──────────────────────────────────────────────────────
def _fonts():
    from PIL import ImageFont
    g = ms.font_path()
    hand = str(FONT_HAND) if FONT_HAND.exists() else g
    return ImageFont, g, hand


def _fit(d, text, font_path, size, max_w, ImageFont):
    f = ImageFont.truetype(font_path, size)
    while d.textlength(text, font=f) > max_w and size > 24:
        size -= 2
        f = ImageFont.truetype(font_path, size)
    return f


def overlay(path: Path, caption: str = "", hand: bool = False, badge: str = "", data: str = "", sub: str = "", honest: str = ""):
    """투명 PNG: 위 1/3 자막 · 왼쪽 아래 순위 뱃지 · 오른쪽 위 데이터 뱃지 · 아래 고지문(항상)."""
    from PIL import Image, ImageDraw
    ImageFont, g, hand_font = _fonts()
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if caption:
        f = _fit(d, caption, hand_font if hand else g, 104 if hand else 68, W - 160, ImageFont)
        tw = d.textlength(caption, font=f)
        d.text(((W - tw) / 2, 560 if hand else 580), caption, font=f, fill=(255, 255, 255, 255),
               stroke_width=7 if hand else 6, stroke_fill=(0, 0, 0, 230))
    if honest:
        f = _fit(d, honest, g, 40, W - 200, ImageFont)
        tw = d.textlength(honest, font=f)
        d.rounded_rectangle([(W - tw) / 2 - 24, 700, (W + tw) / 2 + 24, 700 + f.size + 28], 18, fill=(0, 0, 0, 150))
        d.text(((W - tw) / 2, 714), honest, font=f, fill=(255, 220, 120, 255))
    if badge:
        f = _fit(d, badge, g, 46, W - 300, ImageFont)
        tw = d.textlength(badge, font=f)
        x, y = 48, 1520
        d.rounded_rectangle([x, y, x + tw + 52, y + f.size + 34], 26, fill=(0, 0, 0, 165))
        d.text((x + 26, y + 17), badge, font=f, fill=(255, 255, 255, 255))
    if data:
        f = _fit(d, data, g, 38, 620, ImageFont)
        tw = d.textlength(data, font=f)
        x2, y = W - 48, 130
        d.rounded_rectangle([x2 - tw - 44, y, x2, y + f.size + 28 + (26 if sub else 0)], 22, fill=(255, 232, 107, 235))
        d.text((x2 - tw - 22, y + 13), data, font=f, fill=(20, 20, 20, 255))
        if sub:
            f2 = ImageFont.truetype(g, 22)
            d.text((x2 - tw - 22, y + f.size + 20), sub, font=f2, fill=(60, 60, 60, 255))
    f = ImageFont.truetype(g, 22)
    y = 1790
    for ln in ms.wrap(d, ms.DISCLOSURE, f, W - 160):
        lw = d.textlength(ln, font=f)
        d.text(((W - lw) / 2, y), ln, font=f, fill=(255, 255, 255, 200), stroke_width=2, stroke_fill=(0, 0, 0, 180))
        y += 30
    im.save(path)


def counter_frames(n: int, out_dir: Path, sec: float = 1.0, label: str = "최근 30일 후기", sub: str = "네이버 블로그 기준") -> int:
    """오른쪽 위 데이터 뱃지의 숫자가 0 → n 으로 올라가는 PNG 프레임들 (훅 구간 전용)."""
    from PIL import Image, ImageDraw
    ImageFont, g, _ = _fonts()
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = max(2, int(sec * FPS))
    f = ImageFont.truetype(g, 38)
    f2 = ImageFont.truetype(g, 22)
    for i in range(frames):
        t = (i / (frames - 1)) ** 0.6
        val = int(round(n * t))
        text = f"{label} {val:,}건" + ("+" if n >= 1000 and val >= 1000 else "")
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        tw = d.textlength(text, font=f)
        x2, y = W - 48, 130
        d.rounded_rectangle([x2 - tw - 44, y, x2, y + f.size + 54], 22, fill=(255, 232, 107, 235))
        d.text((x2 - tw - 22, y + 13), text, font=f, fill=(20, 20, 20, 255))
        d.text((x2 - tw - 22, y + f.size + 20), sub, font=f2, fill=(60, 60, 60, 255))
        im.save(out_dir / f"c_{i:03d}.png")
    return frames


def cta_card(path: Path, hotels: list[dict], caption: str):
    """마지막 카드: 어두운 배경 + 1~3위 이름 + 손글씨 자막 + 직접 그린 아이콘(북마크·링크). 이모지 금지."""
    from PIL import Image, ImageDraw
    ImageFont, g, hand = _fonts()
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, 150))
    f = _fit(d, caption, hand, 112, W - 140, ImageFont)
    tw = d.textlength(caption, font=f)
    d.text(((W - tw) / 2, 430), caption, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 220))
    fy = ImageFont.truetype(g, 50)
    y = 700
    for rank, h in zip((1, 2, 3), hotels[::-1]):
        line = f"{rank}위  {h['name']}"
        fl = _fit(d, line, g, 50, W - 220, ImageFont)
        d.text((110, y), line, font=fl, fill=(255, 232, 107, 255) if rank == 1 else (255, 255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))
        y += fl.size + 34
    # 북마크 아이콘 + "저장" / 링크 아이콘 + "프로필 링크"
    bx, by = 300, 1180
    d.polygon([(bx, by), (bx + 70, by), (bx + 70, by + 96), (bx + 35, by + 70), (bx, by + 96)], fill=(255, 232, 107, 255))
    d.text((bx + 96, by + 22), "저장", font=fy, fill=(255, 255, 255, 255))
    lx, ly = 600, 1180
    d.rounded_rectangle([lx, ly + 22, lx + 60, ly + 62], 20, outline=(255, 232, 107, 255), width=9)
    d.rounded_rectangle([lx + 36, ly + 36, lx + 96, ly + 76], 20, outline=(255, 232, 107, 255), width=9)
    d.text((lx + 120, ly + 22), "프로필 링크", font=fy, fill=(255, 255, 255, 255))
    im.save(path)


# ── 4) 소리·합성 ──────────────────────────────────────────────────────
def tts(models: dict, text: str, out: Path, voice: str, tempo: float) -> float:
    raw = out.with_suffix(".raw.wav")
    ms._try_models("tts", models["tts"], lambda m: ms.gemini_tts(
        m, text, voice, "다음 대사를 친구에게 추천하듯 밝고 또렷하게, 너무 빠르지 않게 읽어줘", raw))
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-filter:a", f"atempo={tempo:.3f}", str(out)])
    with wave.open(str(out), "rb") as wf:
        return wf.getnframes() / wf.getframerate()


def segment(idx: int, clips: list[Path], wav: Path | None, narr: float, planned: float, overlays: list[tuple[Path, float, float]],
            counter: tuple[Path, int] | None = None) -> tuple[Path, float]:
    """클립들을 이어 붙이고(각 CUT 초) 자막·뱃지를 시간대별로 얹고 구간 나레이션을 합친다 → seg_N.mp4."""
    norm = []
    for k, c in enumerate(clips):
        d = BUILD / f"n{idx}_{k}.mp4"
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(c), "-an",
                "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},fps={FPS},setsar=1",
                "-t", f"{CUT if ms.probe_duration(c) >= CUT else ms.probe_duration(c):.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(d)])
        norm.append(d)
    vlen = sum(ms.probe_duration(d) for d in norm)
    seglen = max(planned, (narr or 0) + 0.35, vlen if not narr else 0)
    factor = min(1.5, seglen / vlen) if vlen < seglen else 1.0
    stretched = vlen * factor
    pad = max(0.0, seglen - stretched)
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for d in norm:
        cmd += ["-i", str(d)]
    n_in = len(norm)
    for p, _, _ in overlays:
        cmd += ["-i", str(p)]
    if counter:
        cmd += ["-framerate", str(FPS), "-i", str(counter[0] / "c_%03d.png")]
    if wav:
        cmd += ["-i", str(wav)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{seglen:.3f}", "-i", "anullsrc=r=24000:cl=mono"]
    fc = "".join(f"[{i}:v]" for i in range(n_in)) + f"concat=n={n_in}:v=1:a=0[v0];"
    fc += f"[v0]setpts={factor:.4f}*PTS,fps={FPS},tpad=stop_mode=clone:stop_duration={pad:.3f}[v1];"
    cur, k = "v1", n_in
    for j, (_, a, b) in enumerate(overlays):
        fc += f"[{cur}][{k}:v]overlay=0:0:format=auto:enable='between(t,{a:.3f},{b:.3f})'[v{j + 2}];"
        cur = f"v{j + 2}"; k += 1
    if counter:
        fc += f"[{cur}][{k}:v]overlay=0:0:format=auto:eof_action=repeat[vc];"
        cur = "vc"; k += 1
    fc += f"[{cur}]format=yuv420p[v];[{k}:a]apad[a]"
    out = BUILD / f"seg_{idx}.mp4"
    ms.run(cmd + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{seglen:.3f}", "-r", str(FPS),
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(out)])
    return out, seglen


# ── 5) 전체 ───────────────────────────────────────────────────────────
def produce_top3(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    theme, region, month = str(req.get("theme") or ""), str(req.get("region") or ""), str(req.get("month") or "")
    voice, tempo = str(req.get("voice") or "Erinome"), float(req.get("tempo") or 1.08)
    BUILD.mkdir(parents=True, exist_ok=True)

    # 1) 숙소 3곳 + 사진 2장씩 (싼 단계)
    hotels = []
    for i, c in enumerate(pick_candidates(req)):
        if len(hotels) >= 3:
            break
        h = hotel_assets(c, models, i + 1)
        if h:
            hotels.append(h)
    if len(hotels) < 3:
        raise RuntimeError(f"사진 2장 이상 확보된 숙소가 {len(hotels)}곳 — 3곳 필요")
    hotels = hotels[:3][::-1]                       # 입력 순서가 1위→3위 이므로 뒤집어 3위→1위
    hotels[2]["honest"] = ms._try_models("text", models["text"], lambda m: honest_line(m, hotels[2]["name"]))
    report["hotels"] = [{k: h[k] for k in ("name", "room_names", "verified_facilities", "theme_hits", "blog_30d", "min_price", "honest")
                         if k in h} for h in hotels]
    log("순서(3→1위):", " · ".join(h["name"] for h in hotels))

    # 2) 대본 + 구간별 나레이션 (싼 단계 — 여기서 실패하면 영상값을 안 쓴다)
    script = ms._try_models("text", models["text"], lambda m: write_script(m, req, hotels))
    report["script"] = script
    segs_text = [("hook", script["hook"]["narration"])] + [(f"r{r['rank']}", r["narration"] + (" " + r["benefit"] if r.get("benefit") else "")) for r in script["ranks"]] + [("cta", script["cta"]["narration"])]
    narr = {}
    for key, text in segs_text:
        narr[key] = tts(models, text, BUILD / f"narr_{key}.wav", voice, tempo)
    report["narration_sec"] = {k: round(v, 2) for k, v in narr.items()}

    # 3) Veo (돈) — 숙소당 2컷, 1위 컷을 훅에도 쓴다
    all_shots = [s for h in hotels for s in h["shots"]]
    max_cuts = int(req.get("max_veo_cuts") or 6)
    est = veo.estimate_krw(min(len(all_shots), max_cuts), 4)
    log(f"Veo {len(all_shots)}컷 중 {min(len(all_shots), max_cuts)}컷 · 예상 약 {est:,.0f}원 · 이번 달 누적 {veo.month_total():,.0f}원")
    clips, results = {}, []
    for k, s in enumerate(all_shots):
        n, out = s["n"], BUILD / f"veo_{s['n']}.mp4"
        row = {"n": n, "ok": False, "krw": 0.0}
        if k >= max_cuts:
            row["error"] = "max_veo_cuts 초과 — 가짜(확대) 클립으로 대체"
            veo._fake_clip(BUILD / f"shot_{n}.png", 4, out); clips[n] = out; row["ok"] = True; row["fake"] = True
            results.append(row); continue
        before = veo.spent_this_run()
        seed = veo.seed_for(theme, n)
        for attempt in range(2):
            try:
                veo.make_clip(s["prompt"], BUILD / f"shot_{n}.png", 4, out, seed + attempt)
                row["ok"] = True; clips[n] = out; break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:120]}"
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"; break
            except veo.VeoError as e:
                row["error"] = str(e)[:160]; break
        if not row["ok"]:                      # 실패한 컷은 가짜(확대) 클립으로 메워 영상은 완성한다 (표에 표시)
            veo._fake_clip(BUILD / f"shot_{n}.png", 4, out); clips[n] = out; row["fake"] = True
        row["krw"] = round(veo.spent_this_run() - before)
        results.append(row)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": results, "spent_krw": round(veo.spent_this_run()),
                     "month_total_krw": round(veo.month_total())}

    # 4) B롤 (0원) — 숙소 사이에 1초씩
    brolls = []
    for i, q in enumerate(BROLL[:2]):
        p = stock.cutaway(q, 1.0, BUILD / f"broll_{i}.mp4")
        brolls.append(p)
    report["broll"] = [str(p.name) if p else None for p in brolls]

    # 5) 구간 합성
    segs = []
    top = hotels[2]
    data_of = lambda h: (f"최근 30일 후기 {h['blog_30d']:,}건{'+' if (h['blog_30d'] or 0) >= 1000 else ''}" if h.get("blog_30d") else "")
    # 훅: 1위의 물놀이 컷 (이름 숨김) + 손글씨 자막 + 카운터
    ov = BUILD / "ov_hook.png"; overlay(ov, script["hook"]["caption"], hand=True)
    cdir = None
    if top.get("blog_30d"):
        cdir = BUILD / "counter"; counter_frames(int(top["blog_30d"]), cdir, 1.2)
    seg, L = segment(0, [clips[top["shots"][0]["n"]], clips[top["shots"][1]["n"]]], BUILD / "narr_hook.wav", narr["hook"], PLAN["hook"],
                     [(ov, 0, 99)], (cdir, 1) if cdir else None)
    segs.append(seg)
    # 3위 → 2위 → 1위
    for i, (h, r) in enumerate(zip(hotels, script["ranks"])):
        rank = r["rank"]
        planned = PLAN["top"] if rank == 1 else PLAN["rank"]
        cl = [clips[h["shots"][0]["n"]], clips[h["shots"][1]["n"]]]
        if rank != 1 and brolls[i % 2]:
            cl.append(brolls[i % 2])
        key = f"r{rank}"
        seglen_guess = max(planned, narr[key] + 0.35)
        half = seglen_guess / 2
        badge = f"{rank}위  {h['name']}"
        o1 = BUILD / f"ov_{key}_a.png"; overlay(o1, r["captions"][0], badge=badge, data=data_of(h), sub="네이버 블로그 기준" if data_of(h) else "")
        o2 = BUILD / f"ov_{key}_b.png"; overlay(o2, r["captions"][1], badge=badge, data=data_of(h), sub="네이버 블로그 기준" if data_of(h) else "",
                                                 honest=(f"후기 속 아쉬움: {r.get('honest')}" if rank == 1 and r.get("honest") else ""))
        seg, L = segment(rank, cl, BUILD / f"narr_{key}.wav", narr[key], planned, [(o1, 0, half), (o2, half, 99)])
        segs.append(seg)
    # CTA: 1위 컷 위에 어두운 카드
    card = BUILD / "ov_cta.png"; cta_card(card, hotels, script["cta"]["caption"])
    seg, L = segment(9, [clips[top["shots"][0]["n"]]], BUILD / "narr_cta.wav", narr["cta"], PLAN["cta"], [(card, 0, 99)])
    segs.append(seg)

    (BUILD / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    video = BUILD / "video.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(BUILD / "concat.txt"),
            "-c", "copy", "-movflags", "+faststart", str(video)])
    total = ms.probe_duration(video)

    # 6) 승인 자료 + meta
    for h in hotels:
        for s in h["shots"]:
            s["slot"] = s["category"]
    ms.compare_images([s for h in hotels for s in h["shots"]], clips, BUILD, ms.PREVIEW)
    names = [h["name"] for h in hotels[::-1]]
    caption = (ms.DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip() + "\n\n"
               + "\n".join(f"{i + 1}위 {n}" for i, n in enumerate(names)) + "\n세 곳 링크는 프로필에 있어요\n\n" + " ".join(script.get("hashtags") or []))
    meta = {"mode": "top3", "stay": " / ".join(names), "title": script.get("title"), "caption": caption,
            "affiliate_urls": {h["name"]: h["affiliate_url"] for h in hotels},
            "lines": [script["hook"]["narration"]] + [r["narration"] for r in script["ranks"]] + [script["cta"]["narration"]],
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": sum(1 for r in results if r["ok"] and not r.get("fake")),
                    "clips_total": len(results), "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
