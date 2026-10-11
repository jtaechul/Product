#!/usr/bin/env python3
"""단일 숙소 포맷 「한 번에 한 숙소」 — 2026-10-11 운영자 결정: TOP3·예고 폐기, **영상 1편 = 숙소 1곳**, 충분히 소개한다.

구조 (약 35초 · 7~9문장 · 장면 5개: 물놀이 2 · 객실 1 · 특별 공간 2 · 컷 2초):
  훅 4초      시청자 상황·감각 한 문장 (숙소 이름·데이터 말 없음)          [물놀이 A 앞, 물놀이 B 앞]
  물놀이 7초   "여기는 ○○이에요" + 물놀이 공간 2문장 (수온·전망·실내/야외·운영 같은 구체)  [A 뒤, B롤 1초, B 앞, A 앞]  ← 이름 공개 + 후기 카운터
  객실 5초     객실 1~2문장 (뷰·구성·침대)                                   [객실 앞, 객실 뒤]
  특별 6초     특별 공간 1~2문장 (사우나·키즈·산책·조식)                        [특별 A 앞, 특별 B 앞, A 뒤]
  조건 8초     혜택 조건문 1 + 후기 속 아쉬움 1(있을 때) + 누구에게·언제 1       [특별 B 뒤, 물놀이 B 뒤, 객실 앞, B롤]
  CTA 4.5초   저장 + 프로필 폴더 이름                                       [카드]
요청: requests/produce/request.json = {"mode":"solo","stage":"preview"(미리보기)|없음(제작),"theme":..,"region":..,"month":..,
      "stay":"쏠비치 삼척"(선택 · 없으면 순위표에서 쿠팡 통과 1위),"max_veo_cuts":5,"crawl":true,"official_urls":{..}}
규칙은 make_top3 와 같다(사실만·가격 없음·추천 말투·1.28배속·잡음 제거·받아쓰기 검증·공식 홈페이지 사진). 유료 Veo 는 "veo_approved": true 일 때만.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover as dc  # noqa: E402
import make_folder  # noqa: E402
import make_stay as ms  # noqa: E402
import make_top3 as mt  # noqa: E402
import photos  # noqa: E402
import stock  # noqa: E402
import veo  # noqa: E402

CUT = mt.CUT
QUOTA = {"water": 2, "room": 1, "special": 2}
PLAN = {"hook": 4.0, "water": 7.0, "room": 5.0, "special": 6.0, "offer": 8.0, "cta": 4.5}
NARR = {"hook": (0, 24), "water": (45, 95), "room": (25, 65), "special": (30, 75), "offer": (55, 110), "cta": (0, 36)}
SECTIONS = ("hook", "water", "room", "special", "offer", "cta")
KO = {"hook": "훅", "water": "물놀이", "room": "객실", "special": "특별 공간", "offer": "조건·아쉬움·추천", "cta": "CTA"}


def log(*a):
    print("[solo]", *a, flush=True)


def B() -> Path:
    return mt.BUILD


SCRIPT_SYSTEM = """너는 숙소 소개 쇼츠의 큐레이터다. 영상 1편에 숙소 1곳만, 시청자가 "가고 싶다"고 느낄 만큼 **충분히** 소개한다 (7~9문장, 약 35초).
1인칭 "~해요"체, 광고 말투 금지, 유행어는 전체에 최대 1개. 입력에 없는 시설·서비스·가격·할인은 절대 말하지 않는다. 가격 숫자 금지.
"최고·유일·최저가·1위·완벽·보장·최장·최대" 금지. "골랐어요·뽑았어요" 대신 "추천해요"(영상 어딘가 한 번).
입력: 테마·지역·시기, 프로필 폴더 이름, 숙소 이름, 장면 설명(물놀이 A·B, 객실, 특별 A·B — 화면에 실제로 보이는 것), 쿠팡 객실 이름,
블로그로 확인된 시설, 공식 홈페이지 사실, 최근 30일 블로그 글 수, 후기 아쉬움.

구간별 규칙 (나레이션 길이는 공백 제외 글자 수)
- hook (24자 이내): 시청자의 **상황이나 몸의 감각**으로 멈추게 한다. 숙소 이름·"데이터·후기·분석·추천" 금지. 계절·테마 맥락 필수. 네 가지 중 하나:
  ① 상황 공감 "밖은 패딩, 안은 수영복. 11월에 되는 온수풀이에요." ② 감각 대비 "찬바람 맞다가 따뜻한 물에 들어가는 그 순간, 강원에 있어요."
  ③ 가족 문제 해결 "추운데 애들 어디 데려가지? 여기 실내 온수풀이면 돼요." ④ 반전·궁금증 (입력 사실로 확인될 때만)
- water (45~95자, 2문장): 첫 문장에 **숙소 이름**을 말한다("여기는 ○○이에요" 식). 물놀이 공간을 구체로 — 실내/야외, 온천수·온수, 전망(창·바다·산), 운영(사계절·투숙객), 파도풀·슬라이드 같은 구성.
- room (25~65자, 1~2문장): 객실 — 뷰·침대·구성·테라스. 쿠팡 객실 이름에 있는 사실만.
- special (30~75자, 1~2문장): **화면에 보이는 공간을 먼저** 말한다. 장면이 사우나·키즈·산책로·조식·라운지면 그 시설을, 장면이 외관·야경이면 "산속에 자리한", "밤이면 조명이 켜지는" 식으로
  보이는 것을 말하고, 보이지 않는 시설은 "…도 있어요" 로 한 문장만 덧붙인다. 자막도 보이는 공간의 시설 키워드로.
- offer (55~110자, 3문장): ① 혜택을 **조건문**으로 1문장(투숙객 무료·이용권 포함 객실·조식 포함 등 입력에 있는 것) ② 후기 아쉬움이 입력에 있으면 그대로 1문장(없으면 생략) ③ 누구에게·언제 좋은지 1문장(아이와, 커플, 부모님, 비 오는 날, 추운 날).
- cta (36자 이내): 저장 유도 + 프로필 폴더 이름. 폴더에 있는 것(객실 타입·가격대·링크)으로 궁금하게.
- 자막(captions): 구간마다 **장면 수만큼**(입력에 적힌 수) 3~10자 키워드 한 줄. 숫자·'후기' 금지, 느낌표·이모지 금지. 장면과 모순되지 않게(식당 사진 위에 "수영장" 금지). 묘사형("바다 앞 리조트") 금지, 시설·혜택 키워드.
- 문장마다 새 정보. 같은 시설을 두 번 말하지 않는다.
출력 JSON 만:
{"hook":{"caption":"...","narration":"...","pattern":"상황|감각|가족|반전"},
 "water":{"captions":["..","..”],"narration":"..."}, "room":{"captions":[".."],"narration":"..."}, "special":{"captions":["..",".."],"narration":"..."},
 "offer":{"caption":"혜택 키워드 3~10자","narration":"..."}, "cta":{"caption":"...","narration":"..."},
 "title":"유튜브 제목 12~25자(숙소 이름 포함)","caption":"인스타 캡션 2문장(고지문·링크는 시스템이 붙임)","hashtags":["#..","#..","#..","#..","#.."]}"""


def pick_hotel(req: dict) -> tuple[dict, int]:
    """요청의 stay(이름) 또는 순위표의 쿠팡 통과 1위. 돌려주는 것: (후보, 순위표 위치 1부터)."""
    rows = []
    f = mt.ROOT / "data" / "discover" / "latest" / "candidates.json"
    if f.exists():
        rep = json.loads(f.read_text(encoding="utf-8"))
        rows = [c for c in rep.get("candidates") or [] if (c.get("coupang") or {}).get("ok")]
    want = str(req.get("stay") or "").strip()
    if want:
        for i, c in enumerate(rows):
            if dc.same(want, c["name"]):
                return c, i + 1
        return {"name": want, "demand": {}, "coupang": {}, "ai": {}, "facility_checks": []}, 0
    if not rows:
        raise RuntimeError("순위표가 없습니다 — stay-shorts-discover 를 먼저 돌리거나 request.json 에 stay 를 적어 주세요")
    return rows[0], 1


FACILITY_RX = re.compile(r"사우나|찜질|키즈|놀이|산책|정원|테라스|라운지|조식|레스토랑|식당|스파|온천|노천|족욕|카페|바비큐|바베큐|수영장|풀")
EXTERIOR_RX = re.compile(r"외관|전경|건물|항공|야경|조명|단지|하늘|은하수|드론|멀리")


def scenes_of(hotel: dict) -> dict:
    """장면을 구간에 배정: water[A,B] · room[R] · special[A,B]. 모자라면 다른 분류로 채운다 (최소 2장).
    p9b 실측: '특별 공간'에 리조트 외관·야경(쿠팡)이 뽑혀 나레이션(사우나·수영장)과 화면이 어긋났다 → 특별 공간은 시설(사우나·키즈·산책로…)
    설명이 있는 사진을 먼저, 외관·야경은 맨 뒤로."""
    sh = list(hotel["shots"])
    by = {k: [s for s in sh if s["slot"] == k] for k in ("water", "room", "special")}

    def special_key(s):
        d = s.get("description") or ""
        return (0 if FACILITY_RX.search(d) else 1 if not EXTERIOR_RX.search(d) else 2, -int(s.get("quality") or 0))
    by["special"].sort(key=special_key)
    used = set()

    def take(cat, n):
        out = []
        for s in by[cat]:
            if len(out) >= n:
                break
            if id(s) not in used:
                used.add(id(s)); out.append(s)
        return out
    sc = {"water": take("water", 2), "room": take("room", 1), "special": take("special", 2)}
    rest = [s for s in sh if id(s) not in used]
    for k, n in (("water", 2), ("room", 1), ("special", 2)):
        while len(sc[k]) < n and rest:
            sc[k].append(rest.pop(0))
    if not sc["water"]:
        sc["water"] = [sh[0]]
    if not sc["room"]:
        sc["room"] = [sc["water"][-1]]
    if not sc["special"]:
        sc["special"] = [sc["water"][0]]
    return sc


def check_script(s: dict, hotel: dict, counts: dict) -> list[str]:
    errs = []
    toks = mt._name_tokens(hotel["name"])
    all_narr = ""
    for key in SECTIONS:
        g = s.get(key) or {}
        n = str(g.get("narration", "")).strip()
        all_narr += " " + n
        lo, hi = NARR[key]
        L = len(n.replace(" ", ""))
        if not n or L > hi:
            errs.append(f"{key} 나레이션 {L}자 (한도 {hi})")
        if L < lo:
            errs.append(f"{key} 나레이션 {L}자 — 너무 짧다 (최소 {lo}자)")
        caps = g.get("captions") or ([g.get("caption")] if g.get("caption") else [])
        want = counts.get(key)
        if want is not None and len(caps) != want:
            errs.append(f"{key} 자막은 장면 수({want})만큼")
        for cp in caps:
            c = str(cp)
            if not (2 <= len(c.replace(" ", "")) <= 12):
                errs.append(f"자막 길이: '{c}'")
            if key != "hook" and re.search(r"\d|후기", c):
                errs.append(f"자막에 숫자·후기 금지: '{c}'")
        text = n + " " + " ".join(map(str, caps))
        if key == "hook":
            if any(t in text for t in toks):
                errs.append("훅에 숙소 이름 금지")
            bad = [w for w in ("데이터", "후기", "분석", "추천", "AI", "인공지능", "빅데이터") if w in text]
            if bad:
                errs.append(f"훅에 {'/'.join(bad)} 금지 — 상황·감각으로 시작")
        if key == "water" and not any(t in n for t in toks):
            errs.append(f"물놀이 첫 문장에 숙소 이름({hotel['name']}) 넣기")
        for w in mt.WORDING_BAN:
            if w in n:
                errs.append(f"'{w}' 대신 '추천' ({key})")
    if "추천" not in all_narr:
        errs.append("나레이션 어딘가에 '추천' 한 번")
    joined = all_narr + str(s.get("title", "")) + str(s.get("caption", ""))
    if re.search(r"(만족도|인기|평점|국내|업계|지역|강원|전국)\s*1위", joined):
        errs.append("'○○ 1위' 과장 표현")
    plain = re.sub(r"[123]\s*위", "", joined)
    for b in mt.BANNED:
        if b in plain:
            errs.append(f"금지 표현 '{b}'")
    if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", joined):
        errs.append("가격·할인 숫자")
    if not any(t in str(s.get("title", "")) for t in toks):
        errs.append("제목에 숙소 이름")
    return errs


def write_script(model: str, req: dict, hotel: dict, sc: dict) -> dict:
    desc = lambda s: s.get("description") or s.get("category")
    lines = [f"테마: {req.get('theme')} · 지역: {req.get('region')} · 시기: {req.get('month')}", f"프로필 폴더 이름: {mt.folder_name(req)}",
             f"숙소: {hotel['name']}" + (f" ({hotel.get('city')})" if hotel.get("city") else "") + (f" — {hotel['signature']}" if hotel.get("signature") else ""),
             "장면 (화면에 실제로 보이는 것):",
             "  물놀이 " + " / ".join(f"{'AB'[i]}: {desc(s)}" for i, s in enumerate(sc["water"])) + f"  (자막 {len(sc['water'])}개)",
             "  객실: " + desc(sc["room"][0]) + "  (자막 1개)",
             "  특별 " + " / ".join(f"{'AB'[i]}: {desc(s)}" for i, s in enumerate(sc["special"])) + f"  (자막 {len(sc['special'])}개)",
             f"쿠팡 객실 이름: {', '.join(hotel['room_names'])}",
             f"확인된 시설: {', '.join(hotel['verified_facilities']) or '없음'} / 객실 이름의 테마 단어: {', '.join(hotel['theme_hits']) or '없음'}",
             f"공식 홈페이지 사실: {', '.join(hotel.get('official_facts') or []) or '없음'}",
             f"최근 30일 블로그 글 수: {hotel['blog_30d'] if hotel.get('blog_30d') is not None else '모름'}",
             f"후기 아쉬움: {hotel.get('honest') or '없음'}"]
    content = "\n".join(lines)
    counts = {"hook": 1, "water": len(sc["water"]), "room": 1, "special": len(sc["special"]), "offer": 1, "cta": 1}
    errs = []
    for attempt in range(3):
        extra = ("\n\n직전 답의 문제(고쳐서 다시): " + " / ".join(errs)) if errs else ""
        s = ms.gemini_json(model, SCRIPT_SYSTEM, content + extra)
        errs = check_script(s, hotel, counts)
        if not errs:
            return s
        log(f"대본 검사 실패({attempt + 1}):", errs)
    raise RuntimeError("대본이 규칙을 통과하지 못함: " + " / ".join(errs))


def segs_text(script: dict) -> list[tuple[str, str]]:
    return [(k, str((script.get(k) or {}).get("narration", "")).strip()) for k in SECTIONS]


def solo_card(path: Path, hotel: dict, caption: str, folder: str):
    """마지막 카드: 어두운 배경 + 손글씨 자막 + 숙소 이름 + 저장·프로필 링크 아이콘 + 폴더 이름. 이모지 금지."""
    from PIL import Image, ImageDraw
    ImageFont, g, hand = mt._fonts()
    W, H = mt.W, mt.H
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, 150))
    f = mt._fit(d, caption, hand, 112, W - 140, ImageFont)
    tw = d.textlength(caption, font=f)
    d.text(((W - tw) / 2, 430), caption, font=f, fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(0, 0, 0, 220))
    fl = mt._fit(d, hotel["name"], g, 64, W - 160, ImageFont)
    tw = d.textlength(hotel["name"], font=fl)
    d.text(((W - tw) / 2, 760), hotel["name"], font=fl, fill=(255, 232, 107, 255), stroke_width=4, stroke_fill=(0, 0, 0, 200))
    if hotel.get("city"):
        fc = ImageFont.truetype(g, 40)
        tw = d.textlength(hotel["city"], font=fc)
        d.text(((W - tw) / 2, 850), hotel["city"], font=fc, fill=(230, 230, 230, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))
    fy = ImageFont.truetype(g, 50)
    bx, by = 300, 1180
    d.polygon([(bx, by), (bx + 70, by), (bx + 70, by + 96), (bx + 35, by + 70), (bx, by + 96)], fill=(255, 232, 107, 255))
    d.text((bx + 96, by + 22), "저장", font=fy, fill=(255, 255, 255, 255))
    lx, ly = 600, 1180
    d.rounded_rectangle([lx, ly + 22, lx + 60, ly + 62], 20, outline=(255, 232, 107, 255), width=9)
    d.rounded_rectangle([lx + 36, ly + 36, lx + 96, ly + 76], 20, outline=(255, 232, 107, 255), width=9)
    d.text((lx + 120, ly + 22), "프로필 링크", font=fy, fill=(255, 255, 255, 255))
    if folder:
        line = f"폴더  {folder}"
        ff = mt._fit(d, line, g, 44, W - 240, ImageFont)
        tw = d.textlength(line, font=ff)
        d.text(((W - tw) / 2, ly + 120), line, font=ff, fill=(255, 232, 107, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))
    im.save(path)


def preview_sheet(hotel: dict, sc: dict, script: dict, out: Path):
    """장면 5장 + 자막 + 구간 나레이션을 한 장으로."""
    from PIL import Image, ImageDraw, ImageFont
    g = ms.font_path()
    f = ImageFont.truetype(g, 30); f2 = ImageFont.truetype(g, 24)
    w, h = 300, 533
    order = [("water", s) for s in sc["water"]] + [("room", s) for s in sc["room"]] + [("special", s) for s in sc["special"]]
    caps = list((script.get("water") or {}).get("captions") or []) + list((script.get("room") or {}).get("captions") or []) + list((script.get("special") or {}).get("captions") or [])
    cols = max(1, len(order))
    im = Image.new("RGB", (w * cols + 20 * (cols + 1), h + 420), (18, 18, 18))
    d = ImageDraw.Draw(im)
    d.text((20, 16), f"{hotel['name']}  ·  훅 자막: {(script.get('hook') or {}).get('caption', '')}", font=f, fill=(255, 232, 107))
    for col, ((cat, s), cap) in enumerate(zip(order, caps + [""] * len(order))):
        x = 20 + col * (w + 20)
        try:
            t = Image.open(B() / f"shot_{s['n']}.png").convert("RGB").resize((w, h), Image.LANCZOS)
            im.paste(t, (x, 60))
        except Exception:  # noqa: BLE001
            continue
        d.text((x + 8, 68), f"{photos.KO.get(cat, cat)} · {mt.SRC_KO.get(s.get('source'), '')}", font=f2, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
        d.rectangle([x, 60 + h - 40, x + w, 60 + h], fill=(0, 0, 0))
        d.text((x + 8, 60 + h - 34), f"자막: {cap}", font=f2, fill=(255, 255, 255))
    y = 60 + h + 16
    maxc = max(40, (w * cols) // 13)
    for key in SECTIONS:
        n = str((script.get(key) or {}).get("narration", ""))
        line = f"{KO[key]}: {n}"
        for i in range(0, len(line), maxc):
            d.text((20, y), line[i:i + maxc], font=f2, fill=(220, 220, 220)); y += 28
        y += 6
    im.save(out, "JPEG", quality=85)


def assets(req: dict, models: dict, report: dict) -> tuple[dict, dict, int]:
    c, pos = pick_hotel(req)
    req = {**req, "crawl_max": int(req.get("crawl_max") or 32)}        # 장면 5개(특별 공간 2)를 채우려면 사진 후보가 더 필요하다 (p9b: 24장 중 8장 제외)
    h = mt.hotel_assets(c, models, 1, req, quota=QUOTA)
    if not h:
        raise RuntimeError(f"{c['name']}: 쓸 수 있는 사진이 2장 미만이거나 쿠팡 객실이 없습니다")
    h["honest"] = ms._try_models("text", models["text"], lambda m: mt.honest_line(m, h["name"]))
    sc = scenes_of(h)
    report["hotels"] = [{k: h[k] for k in ("name", "city", "room_names", "verified_facilities", "theme_hits", "blog_30d", "min_price", "honest", "photo_counts",
                                            "official_facts", "signature", "hook", "affiliate_url", "official_site", "rooms") if k in h}]
    mt.record_sources([h], report)
    log(f"{h['name']}: 장면 물놀이 {len(sc['water'])} · 객실 {len(sc['room'])} · 특별 {len(sc['special'])} (순위표 {pos}위)")
    return h, sc, pos


def narrate(models: dict, script: dict, voice: str, tempo: float) -> dict:
    narr = {}
    for key, text in segs_text(script):
        narr[key] = mt.tts(models, text, B() / f"narr_{key}.wav", voice, tempo)
    return narr


def preview_solo(req: dict, models: dict, report: dict) -> dict:
    voice, tempo = str(req.get("voice") or "Erinome"), float(req.get("tempo") or mt.TEMPO)
    B().mkdir(parents=True, exist_ok=True)
    h, sc, pos = assets(req, models, report)
    script = ms._try_models("text", models["text"], lambda m: write_script(m, req, h, sc))
    report["script"] = script
    try:
        make_folder.update_hotel(req, h, pos)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]})")
    narr = narrate(models, script, voice, tempo)
    report["narration_sec"] = {k: round(v, 2) for k, v in narr.items()}
    qa = mt.narration_qa(models, [(k, t, B() / f"narr_{k}.wav") for k, t in segs_text(script)])
    report["narration_qa"] = qa
    prev = ms.PREVIEW
    prev.mkdir(parents=True, exist_ok=True)
    (B() / "narr_list.txt").write_text("".join(f"file 'narr_{k}.wav'\nfile 'gap.wav'\n" for k in SECTIONS), encoding="utf-8")
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", "0.6", "-i", "anullsrc=r=24000:cl=mono", str(B() / "gap.wav")])
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(B() / "narr_list.txt"), "-c:a", "libmp3lame", "-b:a", "96k", str(prev / "narration_preview.mp3")])
    preview_sheet(h, sc, script, prev / "preview_shots.jpg")
    md = [f"# 미리보기(단일 숙소) — {h['name']} · {req.get('region')} · {req.get('theme')} · {req.get('month')}",
          f"프로필 폴더 이름: **{mt.folder_name(req)}**", "", "## 대사·자막", ""]
    for key in SECTIONS:
        g = script.get(key) or {}
        caps = g.get("captions") or ([g.get("caption")] if g.get("caption") else [])
        md.append(f"- {KO[key]} 자막: " + " → ".join(f"**{c}**" for c in caps) + f" / 나레이션: {g.get('narration', '')}")
    md += ["", "## 나레이션 받아쓰기 검증", "", "| 구간 | 대본 | 들린 것 | 일치 | 판정 |", "|---|---|---|---|---|"]
    for q in qa:
        md.append(f"| {q['segment']} | {q['script']} | {q['heard']} | {q['similarity']} | {'통과' if q['ok'] else '실패 ' + ','.join(q['instruction_words'])} |")
    pc = h.get("photo_counts") or {}
    md += ["", "## 숙소·사진", "",
           f"- 확인된 시설: {', '.join(h['verified_facilities']) or '없음'} · 후기 30일 {h.get('blog_30d')} · 사진 후보 공식 홈페이지 {pc.get('official', 0)}장 · 쿠팡 {pc.get('coupang', 0)}장"
           + (f" · 다른 지점 의심 제외 {pc['mismatch']}장" if pc.get("mismatch") else ""),
           f"- 공식 홈페이지 사실: {', '.join(h.get('official_facts') or []) or '없음'}" + (f" · 한 줄: {h['signature']}" if h.get("signature") else ""),
           "- 장면: " + " · ".join(f"{photos.KO.get(cat, cat)} {('AB'[i] if cat != 'room' else '')}: {s.get('description')} [{mt.SRC_KO.get(s.get('source'), '?')}]"
                                  for cat in ("water", "room", "special") for i, s in enumerate(sc[cat])),
           "", "사진 출처 장부: `data/runs/latest/photo_sources.json`"]
    (prev / "preview.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    meta = {"mode": "solo", "stage": "preview", "stay": h["name"], "title": script.get("title"),
            "narration_qa_ok": all(q["ok"] for q in qa), "files": ["preview.md", "preview_shots.jpg", "narration_preview.mp3"]}
    (B() / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def produce_solo(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    theme = str(req.get("theme") or "")
    voice, tempo = str(req.get("voice") or "Erinome"), float(req.get("tempo") or mt.TEMPO)
    B().mkdir(parents=True, exist_ok=True)
    h, sc, pos = assets(req, models, report)
    script = ms._try_models("text", models["text"], lambda m: write_script(m, req, h, sc))
    report["script"] = script
    try:
        make_folder.update_hotel(req, h, pos)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]})")
    narr = narrate(models, script, voice, tempo)
    report["narration_sec"] = {k: round(v, 2) for k, v in narr.items()}

    # Veo (돈) — 장면 5개, 각 4초 클립을 앞·뒤 2초로 나눠 쓴다. max_veo_cuts 기본 5
    shots = sc["water"] + sc["room"] + sc["special"]
    seen, uniq = set(), []
    for s in shots:
        if s["n"] not in seen:
            seen.add(s["n"]); uniq.append(s)
    max_cuts = int(req.get("max_veo_cuts") or 5)
    est = veo.estimate_krw(min(len(uniq), max_cuts), 4)
    log(f"Veo {len(uniq)}컷 중 {min(len(uniq), max_cuts)}컷 · 예상 약 {est:,.0f}원 · 이번 달 누적 {veo.month_total():,.0f}원")
    clips, results = {}, []
    for k, s in enumerate(uniq):
        n, out = s["n"], B() / f"veo_{s['n']}.mp4"
        row = {"n": n, "ok": False, "krw": 0.0}
        if k >= max_cuts:
            row["error"] = "max_veo_cuts 초과 — 가짜(확대) 클립으로 대체"
            veo._fake_clip(B() / f"shot_{n}.png", 4, out); clips[n] = out; row["ok"] = True; row["fake"] = True
            results.append(row); continue
        before = veo.spent_this_run()
        seed = veo.seed_for(theme, n)
        for attempt in range(2):
            try:
                veo.make_clip(s["prompt"], B() / f"shot_{n}.png", 4, out, seed + attempt)
                row["ok"] = True; clips[n] = out; break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:120]}"
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"; break
            except veo.VeoError as e:
                row["error"] = str(e)[:160]; break
        if not row["ok"]:
            veo._fake_clip(B() / f"shot_{n}.png", 4, out); clips[n] = out; row["fake"] = True
        row["krw"] = round(veo.spent_this_run() - before)
        results.append(row)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": results, "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}

    # B롤 1개 (0원, 물 장면만)
    def water_frame(frame: Path) -> bool:
        try:
            cl = ms._try_models("vision", models["text"], lambda m: photos.classify(m, [{"k": 0, "source": "stock", "name": "broll", "path": str(frame)}]))
            return bool(cl) and cl[0]["category"] == "water" and not cl[0].get("people")
        except Exception as e:  # noqa: BLE001
            log(f"B롤 비전 검사 실패 → 탈락: {str(e)[:60]}")
            return False
    broll = stock.cutaway(mt.BROLL[0], 1.0, B() / "broll_0.mp4", verify=water_frame)
    report["broll"] = [str(broll.name) if broll else None]

    W = [clips[s["n"]] for s in sc["water"]]; R = clips[sc["room"][0]["n"]]; S = [clips[s["n"]] for s in sc["special"]]
    W2, S2 = (W[1] if len(W) > 1 else W[0]), (S[1] if len(S) > 1 else S[0])
    data = (f"최근 30일 후기 {h['blog_30d']:,}건{'+' if (h['blog_30d'] or 0) >= 1000 else ''}" if h.get("blog_30d") else "")
    name = h["name"]
    segs = []

    def part(idx, key, pieces, overlays, counter=None):
        seg, L = mt.segment(idx, pieces, B() / f"narr_{key}.wav", narr[key], PLAN[key], overlays, counter)
        segs.append(seg)
        return L

    def ovs_for(key, caps, badge, honest=""):
        guess = max(PLAN[key], narr[key] + 0.35)
        out = []
        for k, cap in enumerate(caps):
            o = B() / f"ov_{key}_{k}.png"
            mt.overlay(o, cap, badge=badge, data=(data if key == "offer" else ""), sub=("네이버 블로그 기준" if key == "offer" and data else ""),
                       honest=(honest if k == len(caps) - 1 else ""))
            a = guess * k / len(caps); b = guess * (k + 1) / len(caps) if k < len(caps) - 1 else 99
            out.append((o, a, b))
        return out
    # 훅: 물놀이 A 앞 + B 앞, 손글씨 자막, 이름 없음
    ov = B() / "ov_hook.png"; mt.overlay(ov, script["hook"]["caption"], hand=True)
    part(0, "hook", [(W[0], 0, CUT), (W2, 0, CUT)], [(ov, 0, 99)])
    # 물놀이: 이름 공개 + 후기 카운터(증거)
    cdir = None
    if h.get("blog_30d"):
        cdir = B() / "counter"; mt.counter_frames(int(h["blog_30d"]), cdir, 1.2)
    pieces = [(W[0], CUT, CUT)] + ([(broll, 0, 1.0)] if broll else []) + [(W2, 0, CUT), (W[0], 0, CUT)]
    part(1, "water", pieces, ovs_for("water", script["water"]["captions"], name), (cdir, 0.3) if cdir else None)
    part(2, "room", [(R, 0, CUT), (R, CUT, CUT)], ovs_for("room", script["room"]["captions"], name))
    part(3, "special", [(S[0], 0, CUT), (S2, 0, CUT), (S[0], CUT, CUT)], ovs_for("special", script["special"]["captions"], name))
    honest = f"후기 속 아쉬움: {h['honest']}" if h.get("honest") else ""
    pieces = [(S2, CUT, CUT), (W2, CUT, CUT), (R, 0, CUT)] + ([(broll, 0, 1.0)] if broll else [])
    part(4, "offer", pieces, ovs_for("offer", [script["offer"]["caption"]], name, honest))
    folder = mt.folder_name(req)
    card = B() / "ov_cta.png"; solo_card(card, h, script["cta"]["caption"], folder)
    part(9, "cta", [(W[0], CUT, CUT), (S[0], CUT, CUT)], [(card, 0, 99)])

    (B() / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    video = B() / "video.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(B() / "concat.txt"), "-c", "copy", "-movflags", "+faststart", str(video)])
    total = ms.probe_duration(video)
    ms.compare_images(list(uniq), clips, B(), ms.PREVIEW)
    caption = (ms.DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip() + "\n\n" + name
               + f"\n객실 타입·가격대·링크는 프로필 폴더 '{folder}' 에 있어요\n\n" + " ".join(script.get("hashtags") or []))
    meta = {"mode": "solo", "stay": name, "title": script.get("title"), "caption": caption, "folder": folder,
            "affiliate_urls": {name: h["affiliate_url"]}, "lines": [t for _, t in segs_text(script)],
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": sum(1 for r in results if r["ok"] and not r.get("fake")),
                    "clips_total": len(results), "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
