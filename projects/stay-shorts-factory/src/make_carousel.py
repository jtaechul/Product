#!/usr/bin/env python3
"""쓰레드(Threads) 캐러셀 — 2026-10-21 운영자 "이거 아무도 안 보고 넘겨버릴 것 같다. 쓰레드로 캐러셀 형태로 올려서 링크 클릭 유도하는 게 나으려나?"
→ 제안(완성 영상 3편은 그대로 발행 + 같은 숙소를 쓰레드 캐러셀로도 올려 2주 비교) → "진행해". **AI 호출 0 · 0원.**

영상 한 편의 계획(`build/story/plan.json` · 대본·컷 화면·특장점 라벨·체크리스트·캡션)에서 **4:5(1080×1350) 카드 3~5장 + 본문 글**을 만든다:
  1 표지  = 걱정형 큰 제목(줄마다 어두운 상자 · 핵심 낱말 하나 코랄) + 훅 문장 — 사진은 영상 첫 화면의 숙소 컷(인서트 제외)
  2~4     = 특장점 라벨(코랄 큰 글씨 · 영상과 같은 라벨) + 그 문장 — 사진은 **영상이 그 문장에서 보여 주는 화면 그대로**(cut_imgs · AI 패널이면 'AI 연출' 표시)
  5 마무리 = 체크리스트(조건) + "객실·예약 링크는 본문 링크에서" + 숙소 이름
  본문    = 고지문 → 캡션 첫 줄 → 요점 → 체크리스트 → 폴더 링크(프로필 N번과 같은 자리) → 숙소 이름 → 사진 출처·AI 표시 → 해시태그 (쓰레드 500자 안)
디자인은 영상과 같은 토큰(`design.py` · Pretendard · INK · ACCENT · MARGIN · 어두운 둥근 상자 · 아래 그라데이션 · 블러 없음 · 기호·이모지 없음 · 왼쪽 정렬).
카드에는 공식 홈페이지 사진이 들어 있다 → 저장소·Release 에 올리지 않는다(아티팩트·텔레그램으로만). 영상에만 쓰던 공식 사진을 정지 이미지로 한 번 더 쓰는 결정은 운영자 몫(규칙 문서에 기록)."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

import design
from design import ACCENT, INK, MARGIN, _box_lines, _draw_segs, _shadowed, _width, font, one_line, plain, segments, title_lines, wrap_marked

CW, CH = 1080, 1350                                    # 쓰레드·인스타 피드 4:5 — 세로 카드가 피드에서 가장 크게 보인다
LINK_BASE = "https://stay-folders.pages.dev"           # 프로필 링크 페이지(폴더) — 본문 링크는 영상 끝 카드의 '프로필 N번'과 같은 자리로 간다
THREADS_MAX = 500                                      # 쓰레드 본문 글자 한도
MAX_FEATURES = 3                                       # 특장점 카드 1~3장(영상 라벨 수와 같다)
CHECK_MAX = 4                                          # 마무리 카드 체크리스트 줄 수
AI_LINE = "AI 연출 · 실제 모습과 다를 수 있어요"
SOURCE_LINE = "사진: 숙소 공식 홈페이지 · 일부 장면은 AI 연출(실제와 다를 수 있어요)"
MID_LENSES = ("정체", "디테일", "상황", "사람", "행동", "연결", "희소성")

# 카드 글자 그리드 — 영상 GRID 와 같은 원칙: 유형마다 크기·x·줄 수를 한 번만 적고 모든 카드가 그 값만 쓴다(크기 자동 축소 없음)
G = {
    "disclosure": {"size": 24, "x": MARGIN, "y": 56, "lh": 32, "lines": 2},             # 고지문 — 모든 카드 왼쪽 위 같은 자리
    "ai": {"size": 24, "x": MARGIN, "y": 128},                                            # 'AI 연출' 줄 — 고지문 바로 아래(AI 패널·인서트 카드만)
    "title": {"size": 104, "lh": 128, "lines": 3, "w": CW - 2 * MARGIN},                  # 표지 큰 제목 — 줄마다 어두운 상자, [낱말] 하나 코랄
    "hook": {"size": 48, "lh": 66, "lines": 2, "w": CW - 2 * MARGIN},                     # 표지 훅 문장 — 제목 아래 흰 글자 상자
    "eyebrow": {"size": 40, "lh": 56},                                                     # '특장점 1' · '체크리스트' · 마무리 안내 줄
    "feature": {"size": 88, "lh": 104, "lines": 2, "w": CW - 2 * MARGIN},                  # 특장점 라벨 — 코랄 + 두꺼운 선·그림자(영상 라벨과 같은 처리)
    "line": {"size": 52, "lh": 72, "lines": 3, "w": CW - 2 * MARGIN},                      # 문장·체크리스트 줄 — 흰 글자 어두운 상자
    "bottom": CH - 96,                                                                     # 글 덩이의 아래 기준선(위로 쌓는다)
    "gap": 28,
}


def _gradient(im: Image.Image, y_from: int, y_to: int, a_from: float, a_to: float) -> Image.Image:
    """세로 그라데이션 어둡기(카드 크기용 · design.gradient 는 1080×1920 고정)."""
    y_from, y_to = max(0, y_from), min(CH, y_to)
    hgt = y_to - y_from
    if hgt <= 0:
        return im
    rows = []
    for y in range(hgt):
        t = y / max(1, hgt - 1)
        t = t * t * (3 - 2 * t)
        rows.append(int(255 * (a_from + (a_to - a_from) * t)))
    mask = Image.new("L", (1, hgt)); mask.putdata(rows); mask = mask.resize((CW, hgt))
    band = Image.new("RGBA", (CW, hgt), (*INK, 255)); band.putalpha(mask)
    im.alpha_composite(band, (0, y_from))
    if y_to < CH and a_to > 0:
        tail = Image.new("RGBA", (CW, CH - y_to), (*INK, int(255 * a_to)))
        im.alpha_composite(tail, (0, y_to))
    return im


def _base(photo: Path | None, dark_from: int) -> Image.Image:
    """선명한 사진(4:5 가운데 자르기) + 글자 자리부터 아래로 어둡기 — 블러 없음."""
    if photo and Path(photo).exists():
        im = design.cover(Image.open(photo).convert("RGB"), CW, CH).convert("RGBA")
    else:
        im = Image.new("RGBA", (CW, CH), (*INK, 255))
    _gradient(im, 0, 230, 0.34, 0.0)                                                      # 위쪽 살짝(고지문 자리)
    _gradient(im, dark_from, CH, 0.0, 0.78)
    return im


def _top_lines(im: Image.Image, disclosure: str, ai: bool) -> None:
    g = G["disclosure"]
    d = ImageDraw.Draw(im)
    f = font(g["size"], bold=False)
    words, lines, cur = disclosure.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= CW - 2 * MARGIN:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    for k, ln in enumerate(lines[:g["lines"]]):
        d.text((g["x"], g["y"] + k * g["lh"]), ln, font=f, fill=(255, 255, 255, 175), stroke_width=1, stroke_fill=(0, 0, 0, 110))
    if ai:
        d.text((G["ai"]["x"], G["ai"]["y"]), AI_LINE, font=f, fill=(255, 255, 255, 175), stroke_width=1, stroke_fill=(0, 0, 0, 110))


def _lines_for(d: ImageDraw.ImageDraw, text: str, f, max_w: int, max_lines: int) -> list:
    """제목·라벨은 띄어쓰기 자리에서만(title_lines), 안 되면 낱말 단위 wrap. 줄 수 상한을 넘으면 마지막 줄을 자른다(글자 축소 없음)."""
    lines = title_lines(d, text, f, max_w) or wrap_marked(d, text, f, max_w, max_lines=max_lines)
    return lines[:max_lines]


def _stack(im: Image.Image, blocks: list[dict], bottom: int) -> int:
    """글 덩이들을 아래 기준선에서 위로 쌓는다. 각 덩이 = {kind: box|shadow|plain, lines, f, lh, size, fill}. 돌려주는 값 = 가장 위 y."""
    total = sum(b["lh"] * len(b["lines"]) for b in blocks) + G["gap"] * (len(blocks) - 1)
    y = bottom - total
    top = y
    for i, b in enumerate(blocks):
        n = len(b["lines"])
        if b["kind"] == "box":
            _box_lines(im, b["lines"], b["f"], MARGIN, y, b["lh"], b["size"], fill=b.get("fill", (255, 255, 255, 255)))
        elif b["kind"] == "shadow":
            _shadowed(im, b["lines"], b["f"], [MARGIN] * n, y, b["lh"], b.get("fill", (*ACCENT, 255)), stroke=6)
        else:
            d = ImageDraw.Draw(im)
            for k, ln in enumerate(b["lines"]):
                _draw_segs(d, MARGIN, y + k * b["lh"], ln, b["f"], b.get("fill", (255, 255, 255, 225)), (*ACCENT, 255), stroke=2, stroke_fill=(0, 0, 0, 120))
        y += b["lh"] * n + (G["gap"] if i < len(blocks) - 1 else 0)
    return top


def card_cover(out: Path, photo: Path | None, title: str, hook_line: str, disclosure: str, ai: bool) -> Path:
    """표지: 걱정형 큰 제목(상자 · [낱말] 코랄) + 훅 문장. 제목이 없으면 훅 문장을 제목 자리에."""
    im = _base(photo, 560)
    d = ImageDraw.Draw(im)
    blocks = []
    ttl = one_line(title) or one_line(plain(hook_line))
    g = G["title"]
    ft = font(g["size"])
    blocks.append({"kind": "box", "lines": _lines_for(d, ttl, ft, g["w"], g["lines"]), "f": ft, "lh": g["lh"], "size": g["size"]})
    if title and one_line(plain(hook_line)) and plain(hook_line).replace(" ", "") != plain(title).replace(" ", ""):
        gh = G["hook"]
        fh = font(gh["size"])
        blocks.append({"kind": "box", "lines": wrap_marked(d, plain(hook_line), fh, gh["w"], max_lines=gh["lines"]), "f": fh, "lh": gh["lh"], "size": gh["size"]})
    _stack(im, blocks, G["bottom"])
    _top_lines(im, disclosure, ai)
    im.convert("RGB").save(out, "JPEG", quality=92)
    return out


def card_feature(out: Path, photo: Path | None, n: int, label: str, line: str, disclosure: str, ai: bool) -> Path:
    """특장점 카드: 눈썹 '특장점 n' → 라벨(코랄 큰 글씨) → 그 문장(흰 상자)."""
    im = _base(photo, 520)
    d = ImageDraw.Draw(im)
    blocks = []
    ge = G["eyebrow"]
    fe = font(ge["size"], bold=False)
    blocks.append({"kind": "plain", "lines": [[(f"특장점 {n}", False)]], "f": fe, "lh": ge["lh"], "size": ge["size"]})
    if label:
        gf = G["feature"]
        ff = font(gf["size"])
        blocks.append({"kind": "shadow", "lines": _lines_for(d, plain(label), ff, gf["w"], gf["lines"]), "f": ff, "lh": gf["lh"], "size": gf["size"]})
    gl = G["line"]
    fl = font(gl["size"])
    blocks.append({"kind": "box", "lines": wrap_marked(d, plain(line), fl, gl["w"], max_lines=gl["lines"]), "f": fl, "lh": gl["lh"], "size": gl["size"]})
    _stack(im, blocks, G["bottom"])
    _top_lines(im, disclosure, ai)
    im.convert("RGB").save(out, "JPEG", quality=92)
    return out


def card_check(out: Path, photo: Path | None, items: list[str], hotel: str, city: str, disclosure: str, ai: bool) -> Path:
    """마무리 카드: '체크리스트' 눈썹 → 줄들(각 2줄까지) → 안내 '객실 타입·예약 링크는 본문 링크에서' → 숙소 이름 · 지역."""
    im = _base(photo, 360)
    d = ImageDraw.Draw(im)
    ge, gl = G["eyebrow"], G["line"]
    fe, fl = font(ge["size"], bold=False), font(gl["size"])
    blocks = [{"kind": "plain", "lines": [[("체크리스트", True)]], "f": font(ge["size"]), "lh": ge["lh"], "size": ge["size"]}]
    for t in items[:CHECK_MAX]:
        blocks.append({"kind": "box", "lines": wrap_marked(d, plain(t), fl, gl["w"], max_lines=2), "f": fl, "lh": gl["lh"], "size": gl["size"]})
    tail = [[("객실 타입·예약 링크는 본문 링크에서", False)]]
    if hotel:
        tail.append([(one_line(hotel + (f" · {city}" if city else "")), False)])
    blocks.append({"kind": "plain", "lines": tail, "f": fe, "lh": ge["lh"], "size": ge["size"]})
    _stack(im, blocks, G["bottom"])
    _top_lines(im, disclosure, ai)
    im.convert("RGB").save(out, "JPEG", quality=92)
    return out


def contact_sheet(cards: list[Path], out: Path, labels: list[str] | None = None, tw: int = 300) -> Path:
    th = int(tw * CH / CW); gap = 20; top = 44
    sheet = Image.new("RGB", (gap + len(cards) * (tw + gap), top + th + gap), (18, 20, 26))
    d = ImageDraw.Draw(sheet); fl = font(22)
    for k, fp in enumerate(cards):
        sheet.paste(Image.open(fp).convert("RGB").resize((tw, th), Image.LANCZOS), (gap + k * (tw + gap), top))
        if labels and k < len(labels):
            d.text((gap + k * (tw + gap), 12), labels[k][:26], font=fl, fill=(255, 255, 255))
    sheet.save(out, "JPEG", quality=88)
    return out


# ── 재료 고르기 ─────────────────────────────────────────────────────────────────────────
def _is_ai(img: str) -> bool:
    return str(img or "").startswith(("sb_", "ins_"))


def _beat_imgs(b: dict, shots: dict, hotel_only: bool = True) -> list[str]:
    """문장의 컷 화면(영상과 같은 순서). hotel_only 면 인서트(집·차 안)는 뺀다."""
    ids = list(b.get("shots") or [])
    imgs = list(b.get("cut_imgs") or [])
    out = []
    for m, sid in enumerate(ids):
        s = shots.get(sid) or {}
        if hotel_only and (s.get("insert") or str(sid).startswith("INS")):
            continue
        img = imgs[m] if m < len(imgs) and imgs[m] else s.get("img")
        if img:
            out.append(str(img))
    return out


def pick_cards(text: dict, shots: dict, sig: dict) -> list[dict]:
    """카드 재료: 표지 1 + 특장점 1~3 + 마무리 1. 사진은 서로 다르게(같은 화면 두 번 금지), 영상이 그 문장에서 보여 주는 화면을 우선."""
    beats = list(text.get("beats") or [])
    used: set[str] = set()

    def take(cands: list[str], allow_repeat: bool = False) -> str | None:
        for c in cands:
            if c and c not in used:
                used.add(c); return c
        if allow_repeat and cands:
            return cands[0]
        return None

    hook = beats[0] if beats else {}
    cover_cands = _beat_imgs(hook, shots) + [i for b in beats[1:2] for i in _beat_imgs(b, shots)] \
        + [s["img"] for s in shots.values() if s.get("adv") and not s.get("insert") and s.get("grade", "full") != "insert"]
    cover_img = take(cover_cands)
    cards = [{"role": "cover", "img": cover_img, "title": str(text.get("hook_title") or ""), "line": str(hook.get("line") or "")}]

    feats = [f for f in (text.get("features") or []) if isinstance(f, dict) and f.get("text") and f.get("beats")]
    if feats:
        for f in feats[:MAX_FEATURES]:
            bi = [int(i) for i in f["beats"] if 1 <= int(i) <= len(beats)]
            if not bi:
                continue
            b = beats[bi[0] - 1]
            cands = [i for i_ in bi for i in _beat_imgs(beats[i_ - 1], shots)]
            img = take(cands) or take([shots[x]["img"] for i_ in bi for x in (beats[i_ - 1].get("shots") or []) if x in shots and not shots[x].get("insert")], allow_repeat=True)
            cards.append({"role": "feature", "img": img, "label": str(f["text"]), "line": str(b.get("line") or ""), "beat": bi[0]})
    else:                                                                                # v7 이전 계획(라벨 없음) — 가운데 문장 3개, 정체 문장엔 장점 이름
        for j, b in enumerate(beats[1:-1], 2):
            if str(b.get("lens") or "") not in MID_LENSES or len([c for c in cards if c["role"] == "feature"]) >= MAX_FEATURES:
                continue
            img = take(_beat_imgs(b, shots)) or take([shots[x]["img"] for x in (b.get("shots") or []) if x in shots and not shots[x].get("insert")], allow_repeat=True)
            cards.append({"role": "feature", "img": img, "label": str(sig.get("name") or "") if b.get("lens") == "정체" else "", "line": str(b.get("line") or ""), "beat": j})
    items = [str(x) for x in (text.get("checklist") or []) if str(x).strip()]
    cond = [str(b.get("line") or "") for b in beats if str(b.get("lens") or "") == "조건" and b.get("line")]
    for c in cond:                                                                        # 조건 문장은 체크리스트에 없을 때만 더한다
        if not any(_overlap(c, x) for x in items):
            items.append(c)
    if not items:
        items = [str(p) for p in ((text.get("caption") or {}).get("points") or []) if str(p).strip()][:3]
    if not items:
        items = [str(f.get("text")) for f in feats][:3]
    end_cands = [i for b in beats for i in _beat_imgs(b, shots) if b.get("lens") == "조건"] + [s["img"] for s in shots.values() if s.get("adv") and not s.get("insert")]
    end_img = take(end_cands) or (cover_img if cover_img else None)
    cards.append({"role": "check", "img": end_img, "items": items[:CHECK_MAX]})
    return cards


def _overlap(a: str, b: str) -> bool:
    ta = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", a)); tb = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", b))
    return bool(ta and tb) and len(ta & tb) / max(1, min(len(ta), len(tb))) >= 0.6


def folder_link(req: dict, pos: int) -> str:
    """프로필 링크 페이지의 그 숙소 자리 — 영상 끝 카드 '프로필 N번'과 같은 곳(#/f/<폴더>?no=N)."""
    try:
        import make_folder
        slug = make_folder.slug_of(str(req.get("month") or ""), str(req.get("theme") or ""), str(req.get("region") or ""))
    except Exception:  # noqa: BLE001
        slug = ""
    return f"{LINK_BASE}/#/f/{slug}?no={int(pos)}" if slug else f"{LINK_BASE}/?no={int(pos)}"


def post_text(text: dict, h: dict, req: dict, pos: int, disclosure: str, link: str, ai_any: bool, official: bool) -> tuple[str, dict]:
    """쓰레드 본문(500자 안): 고지문 → 캡션 첫 줄 → 요점 → 체크리스트 → 링크 → 숙소 → 출처·AI → 해시태그. 넘치면 해시태그 → 체크리스트 → 요점 순으로 줄인다."""
    cap = text.get("caption") or {}
    hook = one_line(str(cap.get("hook") or "")) or one_line(plain(str(text.get("hook_title") or "")))
    points = [one_line(str(p)) for p in (cap.get("points") or []) if str(p).strip()]
    checks = [one_line(str(x)) for x in (text.get("checklist") or []) if str(x).strip()]
    tags = [t for t in (text.get("hashtags") or []) if str(t).strip()][:5]
    name = one_line(str(h.get("name") or "")) + (f" · {h.get('city')}" if h.get("city") else "")
    src = ("사진: 숙소 공식 홈페이지" if official else "") + ((" · " if official else "") + "일부 장면은 AI 연출(실제와 다를 수 있어요)" if ai_any else "")
    n_pts, n_chk, n_tag = min(2, len(points)), min(3, len(checks)), len(tags)

    def build() -> str:
        parts = [disclosure, "", hook]
        parts += points[:n_pts]
        if n_chk:
            parts += [""] + [f"· {x}" for x in checks[:n_chk]]
        parts += ["", f"객실 타입·예약 링크 → {link}", name]
        if src:
            parts.append(src)
        if n_tag:
            parts += ["", " ".join(tags[:n_tag])]
        return "\n".join(parts).strip()

    body = build()
    trimmed = []
    while len(body) > THREADS_MAX and (n_tag > 3 or n_chk > 1 or n_pts > 1):
        if n_tag > 3:
            n_tag -= 1; trimmed.append("해시태그")
        elif n_chk > 1:
            n_chk -= 1; trimmed.append("체크리스트")
        else:
            n_pts -= 1; trimmed.append("요점")
        body = build()
    return body, {"chars": len(body), "limit": THREADS_MAX, "over": len(body) > THREADS_MAX, "trimmed": trimmed, "points": n_pts, "checks": n_chk, "tags": n_tag}


def build(text: dict, shots: dict, sig: dict, h: dict, req: dict, pos: int, story: Path, out_dir: Path, disclosure: str, report: dict | None = None) -> dict:
    """카드·본문·시트를 out_dir 에 만든다(0원). 돌려주는 값 = carousel.json 내용(report['carousel']·meta 에 그대로)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cards = pick_cards(text, shots, sig)
    files, labels, ai_any = [], [], False
    for n, c in enumerate(cards, 1):
        img = story / c["img"] if c.get("img") else None
        ai = _is_ai(c.get("img") or "")
        ai_any = ai_any or ai
        out = out_dir / f"card_{n}.jpg"
        if c["role"] == "cover":
            card_cover(out, img, c["title"], c["line"], disclosure, ai)
            labels.append("표지 · " + (plain(c["title"]) or c["line"]))
        elif c["role"] == "feature":
            card_feature(out, img, len(files), c.get("label") or "", c["line"], disclosure, ai)
            labels.append(f"특장점 {len(files)} · " + (c.get("label") or c["line"]))
        else:
            card_check(out, img, c["items"], str(h.get("name") or ""), str(h.get("city") or ""), disclosure, ai)
            labels.append("체크리스트 · 링크")
        c["file"], c["ai"] = out.name, ai
        files.append(out)
    link = folder_link(req, pos)
    official = bool((h.get("photo_counts") or {}).get("official")) or any(str(s.get("source") or "") == "official" for s in shots.values())
    body, info = post_text(text, h, req, pos, disclosure, link, ai_any, official)
    (out_dir / "carousel_post.txt").write_text(body + "\n", encoding="utf-8")
    contact_sheet(files, out_dir / "carousel_sheet.jpg", labels)
    manifest = {"stay": h.get("name"), "cards": [{k: v for k, v in c.items() if k != "items"} | ({"items": c["items"]} if c.get("items") else {}) for c in cards],
                "n": len(files), "link": link, "post": info, "ai_any": ai_any, "krw": 0, "dir": out_dir.name}
    (out_dir / "carousel.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if report is not None:
        report["carousel"] = manifest
    return manifest


def preview_md(manifest: dict, body: str, h: dict, src_label: str) -> str:
    rows = ["| 카드 | 역할 | 사진 | 글 |", "|---|---|---|---|"]
    for n, c in enumerate(manifest.get("cards") or [], 1):
        what = {"cover": "표지", "feature": "특장점", "check": "체크리스트·링크"}.get(c.get("role"), c.get("role"))
        txt = plain(str(c.get("title") or "")) + (" / " if c.get("title") else "") + str(c.get("line") or "") if c.get("role") == "cover" else \
            (str(c.get("label") or "") + (" / " if c.get("label") else "") + str(c.get("line") or "")) if c.get("role") == "feature" else " · ".join(c.get("items") or [])
        rows.append(f"| {n} | {what} | {c.get('img') or '-'}{' (AI 연출)' if c.get('ai') else ''} | {txt} |")
    p = manifest.get("post") or {}
    return "\n".join(["# 쓰레드 캐러셀 — " + str(h.get("name") or ""), "", f"- 재료: {src_label} · AI 호출 0 · 0원 · 카드 {manifest.get('n')}장(1080×1350)",
                      f"- 본문 {p.get('chars')}자 / {p.get('limit')}자" + (" · **넘침**" if p.get("over") else "") + (f" · 줄임: {', '.join(p.get('trimmed') or [])}" if p.get("trimmed") else ""),
                      f"- 링크: {manifest.get('link')}", "- 카드에는 공식 홈페이지 사진이 들어 있어 저장소·Release 에 올리지 않는다(텔레그램·아티팩트만)", "", "## 카드", "", *rows, "",
                      "## 본문(그대로 붙여넣기)", "", "```", body.strip(), "```", ""])
