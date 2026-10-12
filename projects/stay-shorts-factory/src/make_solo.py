#!/usr/bin/env python3
"""단일 숙소 포맷 「한 번에 한 숙소」 — 컷 단위 조립 (2026-10-11 v1 검수 반영 · 운영자 "진행해").

v1(stay-run-18) 의 문제와 원인
  - 같은 장면 반복: 사진 5장을 4초 클립으로 만들고 앞 2초·뒤 2초로 쪼개 15자리에 돌려 썼다(노천탕 4회). 나레이션이 길면 1.5배 슬로우 + 정지.
  - 화면·대사 불일치: 구간 대본을 먼저 쓰고 자막을 시간으로 균등 분할 → 노천탕 화면 위 "실내 파도풀" 자막, 외관 위 사우나 나레이션.
바꾼 설계 (0원)
  - **사진을 먼저 고른다 → 컷마다 "보이는 것"을 적는다 → 컷마다 문장 1개** ("한 컷에 한 문장"). 사진에 없는 시설은 말하지 않는다.
  - **한 컷은 한 번만**: 사진 9장 = 컷 9개 + 끝 카드. 재사용·슬로우·정지 프레임·스톡 물결 금지. 컷 길이 = 그 문장 길이(1.6~4.6초).
  - 자막은 컷에 고정(컷이 바뀔 때 바뀐다). 화면 검수(screen_qa): 컷 사진과 문장의 일치도를 AI 비전이 채점, 미달이면 문장만 다시 쓴다.
  - **숙소 이름 비공개(영상)·공개(캡션·고정 댓글)**: 나레이션·자막엔 이름 없음, 지역+유형으로 부른다. 끝 카드 = "프로필 링크 → 폴더 N번".
  - Veo 는 움직임이 중요한 컷(훅·물)에만 max_veo_cuts(기본 4) 개, 4초 클립을 쪼개지 않고 한 문장에 통째로. 나머지는 사진 무빙(푸시·팬·틸트·풀백) 0원.
  - 디자인은 design.py (Pretendard · 그림자형 자막 · 폴더 표시 · 끝 카드). request.json "caption_style": shadow|bar|highlight|glass
요청: {"mode":"solo","stage":"preview"|없음,"theme","region","month","stay"(선택),"max_veo_cuts":4,"veo_approved":true(제작),"crawl":true,"official_urls":{..}}
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design  # noqa: E402
import discover as dc  # noqa: E402
import make_folder  # noqa: E402
import make_stay as ms  # noqa: E402
import make_top3 as mt  # noqa: E402
import photos  # noqa: E402
import veo  # noqa: E402

QUOTA = {"water": 3, "room": 3, "special": 4}                 # 사진 10장 후보 → 훅1 · 물2 · 객실2 · 특별2~3(시설 사진 우선) · 조건1~2 = 컷 9~10
LIM = {"hook": (10, 22), "veo": (12, 24), "photo": (14, 30)}  # 컷 문장 길이(공백 제외). 1.28배속 실측 약 6.6자/초 → Veo 4초 컷은 24자까지
MIN_CUT, GAP, VEO_SEC, MAX_SLOW = 1.6, 0.30, 4, 1.25
PATTERNS = ("push", "pan", "tilt", "pull")                     # 사진 컷 카메라 무빙 4종 순환
KO = {"hook": "훅", "water": "물놀이", "room": "객실", "special": "특별 공간", "offer": "조건·추천", "cta": "끝 카드"}
GENERIC = {"호텔", "리조트", "앤", "스파", "풀빌라", "펜션", "콘도", "레지던스", "하우스", "파크", "비치", "해변", "온천", "관광호텔"}
FACILITY_RX = re.compile(r"사우나|찜질|키즈|놀이|산책|정원|테라스|라운지|조식|레스토랑|식당|스파|온천|노천|족욕|카페|바비큐|바베큐|수영장|풀")
EXTERIOR_RX = re.compile(r"외관|전경|건물|항공|야경|조명|단지|하늘|은하수|드론|멀리")
WATER_RX = re.compile(r"물|풀|탕|스파|사우나|온천|폭포|분수|파도|슬라이드|바다|강|호수")
QA_THR = {"offer": 5}                                          # 조건 컷은 느슨하게(5), 나머지 7
EXTRA_BONUS = 12                                               # 시그니처 덧붙임이 들어간 컷의 글자 한도 추가(공백 제외)
BGM = mt.ROOT / "assets" / "music" / "bgm.mp3"           # 대표 배경음악 (make_music.py 가 만든다) — 있으면 자동으로 깐다, request.json "bgm": false 면 생략
BGM_LEVEL = 0.22                                               # 나레이션 대비 배경음악 크기(선형). 말할 땐 사이드체인으로 더 내려간다


def log(*a):
    print("[solo]", *a, flush=True)


def B() -> Path:
    return mt.BUILD


SCRIPT_SYSTEM = """너는 숙소 소개 쇼츠의 큐레이터이자 편집자다. 영상 1편에 숙소 1곳만, 시청자가 "가고 싶다"고 느낄 만큼 충분히 소개한다.
영상은 **컷 단위**다. 입력에 컷 목록(번호 · 구간 · 화면에 보이는 것 · Veo/사진 · 글자 한도)이 있고, 컷마다 **그 화면을 설명하는 문장 1개**와 자막 1개를 쓴다.

절대 규칙
- 컷의 문장은 **그 컷 사진에 보이는 것**만 말한다. 보이지 않는 시설·전망·서비스는 그 컷에서 말하지 않는다 (사우나 사진이 없으면 사우나를 말하지 않는다).
  보이는 것에 입력 사실(수온·사계절 운영·투숙객 전용·조식 포함 등)을 덧붙이는 것은 좋다. 입력에 없는 사실·가격·할인 금지, 가격 숫자 금지.
- **숙소 이름을 절대 쓰지 않는다** (나레이션·자막 모두). 대신 "강원 홍천의 대형 워터파크 리조트"처럼 **지역 + 유형**으로 부른다 — 컷 2 문장에서 한 번.
- 1인칭 "~해요"체, 광고 말투 금지, 유행어 전체 1개 이하. "최고·유일·최저가·1위·완벽·보장·최장·최대" 금지. "골랐어요·뽑았어요" 금지. 마지막 컷에 "추천해요".
- 문장마다 새 정보. 같은 시설·같은 표현을 두 컷에서 반복하지 않는다. 글자 한도(공백 제외)를 지킨다 — Veo 컷은 4초라 짧다.
- **이어지는 한 편의 이야기**로 쓴다 (2026-10-11 운영자 "특징을 단순 나열만 해서 앞뒤 연결이 어색하다"): 한 사람이 숙소를 안내하며 걸어가듯,
  컷 2부터는 문장이 **앞 컷을 받는 연결어·장면 전환어**로 시작한다 — 예: "안으로 들어가면", "그 옆엔", "객실로 올라오면", "창밖엔", "밤이 되면", "여기에", "그래서",
  "덕분에", "다만", "특히", "이렇게", "저녁엔", "아침엔", "한 층 내려가면". "A가 있어요. B가 있어요." 식 나열 금지. 같은 연결어를 두 번 쓰지 않고,
  문장 끝(~있어요 / ~이에요 / ~좋아요 / ~돼요 / ~해요)도 연속으로 같은 것을 쓰지 않는다. 마지막 컷은 앞 내용을 받아 "그래서 …에게 추천해요"로 닫는다.
- 입력에 "사진 없는 시그니처"가 있으면(없으면 이 규칙 무시): 그 시설은 사진이 없지만 이 숙소의 대표 포인트라 **딱 한 번** 말해도 된다.
  입력이 지정한 컷(사진 컷)의 문장 **끝에** "…도 있어요", "…까지 이용돼요" 식의 짧은 절로 덧붙인다. 그 컷의 자막은 화면에 보이는 것 그대로 둔다. 다른 컷에서는 말하지 않는다.
  출력에 "extra": {"i": 그 컷 번호, "tag": "+ 시설 이름(2~10자)"} 를 적는다 — 화면에 '+ 히노키 사우나' 같은 작은 태그로 표시된다.

컷별 규칙
- 컷 1 (훅): 시청자의 상황·몸의 감각으로 멈추게 하는 한 문장. 숙소 이름·지역·"데이터·후기·분석·추천·AI" 금지. 계절·테마 맥락 필수. 네 가지 중 하나:
  ① 상황 공감 "밖은 패딩, 안은 수영복. 11월에 되는 온수풀이에요." ② 감각 대비 "찬바람 맞다가 따뜻한 물에 들어가는 그 순간." ③ 가족 문제 해결 "추운데 애들 어디 데려가지? 여기면 돼요." ④ 반전·궁금증(입력 사실로 확인될 때만)
- 물놀이 컷: 실내/야외, 온천수·온수, 전망, 운영(사계절·투숙객), 파도풀·슬라이드 같은 구성 중 **화면에 보이는 것**.
- 객실 컷: 뷰·침대·구성·테라스 — 쿠팡 객실 이름과 화면에 있는 것만.
- 특별 공간 컷: 화면의 시설(사우나·키즈·산책로·조식·라운지…)을 말한다. 화면이 외관·야경이면 "산속에 자리한", "밤이면 조명이 켜지는"처럼 보이는 것을 말한다.
- 조건 컷 ①: 혜택을 조건문으로 (투숙객 무료·이용권 포함 객실·조식 포함 등 입력에 있는 것). 후기 아쉬움이 입력에 있으면 짧게 덧붙여도 된다. 화면과 모순 금지.
- 조건 컷 ② (마지막 컷): 누구에게·언제 좋은지 + "추천해요".
- 자막: 컷마다 2~10자 키워드(명사형). 강조할 한 단어를 [대괄호]로 감싼다(선택, 컷당 1개). 숫자·'후기'·느낌표·이모지 금지(훅 자막의 월 숫자는 허용). 화면과 모순 금지. 묘사형 문장 금지.
출력 JSON 만:
{"cuts":[{"i":1,"narration":"...","caption":"..."}, ... 컷 수만큼 순서대로],
 "extra": {"i": 컷 번호, "tag": "+ 시설 이름"} 또는 null,
 "title":"유튜브 제목 12~25자 (숙소 이름 포함 — 제목·캡션은 텍스트라 이름을 쓴다)",
 "caption":"인스타 캡션 2문장 (숙소 이름 포함 가능. 고지문·링크·폴더 안내는 시스템이 붙임)","hashtags":["#..","#..","#..","#..","#.."]}"""

SCREEN_SYSTEM = """너는 쇼츠 편집 검수자다. 사진 1장과 그 위에 나올 나레이션 문장·자막을 받는다.
문장·자막이 **이 사진에 보이는 것**을 말하는지 0~10점으로 매긴다. 10 = 보이는 것을 정확히 말함 · 7 = 보이는 것과 어울리고 모순 없음 · 4 = 사진에 없는 것을 주로 말함 · 0 = 모순(사진은 외관인데 사우나 내부를 말함).
사진에 없는 사실을 덧붙여도 그 공간에 관한 설명(수온·운영·포함 여부·누구에게 좋은지)이면 감점하지 않는다. 가격·사람 이름은 다루지 않는다.
7점 미만이면 **공백 제외 {lo}~{hi}자**로, 사진에 보이는 것만 말하는 수정 문장을 fix 에 쓴다 (숙소 이름 금지, "~해요"체, 원래 문장의 사실·말투는 최대한 유지). 7점 이상이면 fix 는 빈 문자열.
JSON 만: {{"score": 0~10 정수, "seen": "사진에 보이는 것 한 줄", "problem": "문제 한 줄(없으면 빈 문자열)", "fix": "..."}}"""


# ── 숙소·사진 ───────────────────────────────────────────────────────────────────────────
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


def assets(req: dict, models: dict, report: dict) -> tuple[dict, int]:
    c, pos = pick_hotel(req)
    req = {**req, "crawl_max": int(req.get("crawl_max") or 32)}
    h = mt.hotel_assets(c, models, 1, req, quota=QUOTA)
    if not h:
        raise RuntimeError(f"{c['name']}: 쓸 수 있는 사진이 2장 미만이거나 쿠팡 객실이 없습니다")
    h["honest"] = ms._try_models("text", models["text"], lambda m: mt.honest_line(m, h["name"]))
    for s in h["shots"]:                                       # 사진 컷용 고해상 크롭 (Veo 입력은 720x1280 shot_N.png 그대로)
        photos.crop_9x16(s["path"], B() / f"shotHD_{s['n']}.png", s["focus_x"], s["focus_y"], 1080, 1920)
    report["hotels"] = [{k: h[k] for k in ("name", "city", "room_names", "verified_facilities", "theme_hits", "blog_30d", "min_price", "honest", "photo_counts",
                                            "official_facts", "signature", "hook", "affiliate_url", "official_site", "rooms", "classified_summary") if k in h}]
    mt.record_sources([h], report)
    log(f"{h['name']}: 사진 {len(h['shots'])}장 (순위표 {pos}위)")
    return h, pos


def _special_key(s, facts=()):
    d = s.get("description") or ""
    exterior = bool(EXTERIOR_RX.search(d))
    named = (not exterior) and any(len(t) >= 2 and t in d for f in facts for t in re.split(r"[\s·/,()]+", str(f)))
    return (0 if named else 1 if (FACILITY_RX.search(d) and not exterior) else 2 if not exterior else 3, -int(s.get("quality") or 0))


def plan_cuts(h: dict, max_veo: int) -> list[dict]:
    """사진을 컷에 배정한다 — 훅1(물) · 물2 · 객실2 · 특별2 · 조건2(남은 사진, 외관은 맨 뒤). **사진 하나는 컷 하나에만.**
    Veo 는 움직임이 중요한 순서(훅 → 물 → 물이 있는 특별 공간 → 나머지)로 max_veo 개."""
    shots = list(h["shots"])
    by = {k: [s for s in shots if s["slot"] == k] for k in photos.CATS}
    facts = list(h.get("verified_facilities") or [])
    by["special"].sort(key=lambda s: _special_key(s, facts))
    used = set()

    def take(cat, n):
        out = []
        for s in by.get(cat, []):
            if len(out) >= n:
                break
            if id(s) not in used:
                used.add(id(s)); out.append(s)
        return out
    hook = take("water", 1) or take("special", 1) or take("room", 1)
    water, room, special = take("water", 2), take("room", 2), take("special", 2)
    # 운영자 2026-10-11 "사우나 같은 필요한 사진을 다 반영": 시설이 보이는 특별 공간 사진이 더 있으면 3컷째까지 넣는다 (외관·야경은 제외)
    extra_fac = [s for s in by["special"] if id(s) not in used and _special_key(s, facts)[0] <= 1][:1]
    for s in extra_fac:
        used.add(id(s)); special.append(s)
    rest = [s for s in shots if id(s) not in used]
    rest.sort(key=lambda s: (1 if EXTERIOR_RX.search(s.get("description") or "") else 0))
    offer = rest[:2]
    cuts, i = [], 1
    for sec, lst in (("hook", hook), ("water", water), ("room", room), ("special", special), ("offer", offer)):
        for s in lst:
            cuts.append({"i": i, "section": sec, "n": s["n"], "shot": s, "veo": False}); i += 1
    if len(cuts) < 5:
        raise RuntimeError(f"사진 {len(cuts)}장 — 컷 5개 미만이라 제작하지 않습니다 (훅·물·객실·특별·조건 각 1장 필요)")
    if not any(c["section"] == "offer" for c in cuts):        # 조건·추천 컷은 반드시 하나
        cuts[-1]["section"] = "offer"

    def motion_rank(c):
        # Veo 는 훅 → 물놀이 → 물이 보이는 실내·시설 컷 → 객실 → 외관(맨 뒤) 순. p10 실측: '분수 연못 외관'이 물 낱말로 Veo 를 받아 아까웠다
        d = c["shot"].get("description") or ""
        if c["section"] == "hook":
            return 0
        if c["section"] == "water":
            return 1
        if EXTERIOR_RX.search(d):
            return 4
        return 2 if WATER_RX.search(d) else 3
    for c in sorted(cuts, key=lambda c: (motion_rank(c), c["i"]))[:max(0, int(max_veo))]:
        c["veo"] = True
    for c in cuts:
        c["lo"], c["hi"] = LIM["hook"] if c["section"] == "hook" else LIM["veo"] if c["veo"] else LIM["photo"]
    return cuts


def cut_label(c: dict) -> str:
    return f"컷 {c['i']} ({KO[c['section']]} · {'Veo 4초' if c['veo'] else '사진'} · {c['lo']}~{c['hi']}자)"


# ── 대본 ───────────────────────────────────────────────────────────────────────────────
def name_tokens(name: str, req: dict | None = None, h: dict | None = None) -> list[str]:
    """숙소 이름의 낱말 중 '이름'인 것만 — 일반 낱말(호텔·리조트)과 지역 낱말('쏠비치 삼척'의 삼척)은 뺀다 (지역은 컷 2 에서 말해야 하므로)."""
    skip = set(GENERIC) | (set(region_words(req, h)) if req is not None and h is not None else set())
    return [t for t in mt._name_tokens(name) if t not in skip]


def region_words(req: dict, h: dict) -> list[str]:
    out = [str(req.get("region") or "").strip()]
    city = re.sub(r"(특별자치)?(시|군|구|도)$", "", str(h.get("city") or "").split()[-1]) if h.get("city") else ""
    if city:
        out.append(city)
    return [w for w in out if len(w) >= 2]


def _len(s: str) -> int:
    return len(re.sub(r"\s", "", s))


def sentence_errs(text: str, c: dict, h: dict, req: dict) -> list[str]:
    errs = []
    L = _len(text)
    if not text:
        return [f"컷 {c['i']} 문장 없음"]
    if L > c["hi"]:
        errs.append(f"컷 {c['i']} {L}자 (한도 {c['hi']})")
    if L < c["lo"]:
        errs.append(f"컷 {c['i']} {L}자 — 너무 짧다 (최소 {c['lo']})")
    if any(t in text for t in name_tokens(h["name"], req, h)):
        errs.append(f"컷 {c['i']} 에 숙소 이름 — 영상에서는 이름을 쓰지 않는다")
    for w in mt.WORDING_BAN:
        if w in text:
            errs.append(f"컷 {c['i']} '{w}' 대신 '추천'")
    for b in mt.BANNED:
        if b in text:
            errs.append(f"컷 {c['i']} 금지 표현 '{b}'")
    if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", text):
        errs.append(f"컷 {c['i']} 가격·할인 숫자")
    if c["section"] == "hook":
        bad = [w for w in ("데이터", "후기", "분석", "추천", "AI", "인공지능", "빅데이터") if w in text]
        if bad:
            errs.append(f"훅에 {'/'.join(bad)} 금지 — 상황·감각으로 시작")
        if any(w in text for w in region_words(req, h)):
            errs.append("훅에 지역 이름 금지 (컷 2에서)")
    return errs


def check_script(s: dict, h: dict, cuts: list[dict], req: dict, sig: dict | None = None) -> list[str]:
    errs = []
    got = {int(x.get("i", 0)): x for x in (s.get("cuts") or []) if isinstance(x, dict)}
    if len(got) != len(cuts) or any(c["i"] not in got for c in cuts):
        errs.append(f"컷 {len(cuts)}개 전부 순서대로 (받은 것 {sorted(got)})")
        return errs
    toks = name_tokens(h["name"], req, h)
    all_text = ""
    ex = s.get("extra") if isinstance(s.get("extra"), dict) else None
    ex_i = int(ex.get("i", 0)) if ex else 0
    if sig and not ex:
        errs.append(f"사진 없는 시그니처를 컷 {sig['i']} 끝에 덧붙이고 extra 를 적는다")
    if ex and not sig:
        errs.append("extra 는 null (사진 없는 시그니처가 없다)")
    if ex and sig and ex_i != sig["i"]:
        errs.append(f"extra 는 컷 {sig['i']} 에만")
    if ex and not (2 <= _len(design.plain(str(ex.get("tag", "")).lstrip("+ "))) <= 10):
        errs.append("extra.tag 는 '+ 시설 이름' 2~10자")
    for c in cuts:
        x = got[c["i"]]
        n, cap = str(x.get("narration", "")).strip(), str(x.get("caption", "")).strip()
        all_text += " " + n
        cc = {**c, "hi": c["hi"] + EXTRA_BONUS} if (sig and c["i"] == sig["i"]) else c
        errs += sentence_errs(n, cc, h, req)
        if sig and c["i"] == sig["i"]:
            ws = [w for w in _words(sig["fact"]) if FACILITY_RX.search(w) or len(w) >= 3]
            if ws and not any(w in n for w in ws):
                errs.append(f"컷 {c['i']} 문장 끝에 시그니처({sig['fact']})를 한 절로 덧붙인다")
        pc = design.plain(cap)
        if not (2 <= _len(pc) <= 10):
            errs.append(f"컷 {c['i']} 자막 길이: '{cap}' (2~10자)")
        if cap.count("[") > 1 or cap.count("[") != cap.count("]"):
            errs.append(f"컷 {c['i']} 자막 대괄호는 한 단어만: '{cap}'")
        if c["section"] != "hook" and re.search(r"\d|후기", pc):
            errs.append(f"컷 {c['i']} 자막에 숫자·후기 금지: '{cap}'")
        if re.search(r"[!！]|[\U0001F300-\U0001FAFF]", cap):
            errs.append(f"컷 {c['i']} 자막에 느낌표·이모지 금지")
        if any(t in pc for t in toks):
            errs.append(f"컷 {c['i']} 자막에 숙소 이름")
    second = [c for c in cuts if c["i"] == 2]
    if second and not any(w in got[2].get("narration", "") for w in region_words(req, h)):
        errs.append(f"컷 2 문장에 지역({' 또는 '.join(region_words(req, h))}) + 유형으로 숙소를 부른다")
    last = got[cuts[-1]["i"]].get("narration", "")
    if "추천" not in last:
        errs.append("마지막 컷에 '추천해요'")
    joined = all_text + str(s.get("title", "")) + str(s.get("caption", ""))
    if re.search(r"(만족도|인기|평점|국내|업계|지역|강원|전국)\s*1위", joined):
        errs.append("'○○ 1위' 과장 표현")
    if not any(t in str(s.get("title", "")) for t in toks):
        errs.append("제목에 숙소 이름 (제목·캡션은 텍스트라 이름을 쓴다)")
    tags = s.get("hashtags") or []
    if not (3 <= len(tags) <= 5):
        errs.append("해시태그 3~5개")
    return errs


def _words(t: str) -> list[str]:
    return [w for w in re.split(r"[\s·/,()]+", str(t)) if len(w) >= 2]


def pick_signature(h: dict, cuts: list[dict]) -> dict | None:
    """사진이 없는 시그니처 1개 (운영자 2026-10-11 "사진이 없어도 시그니처는 한두 문장 넣자" → 조건부 반영: 영상당 1개 · 확인된 사실만 · 사진 컷 끝에 한 절 · 태그 칩).
    후보 = 블로그 교차확인 시설 + 공식 홈페이지 사실 중 **어느 컷 설명에도 안 보이는 시설 낱말**이 있는 것. 들어갈 컷 = 조건 컷 ①(아쉬움 줄 자리)을 뺀 사진 컷 중 물·특별 공간 쪽."""
    seen = " ".join(c["shot"].get("description") or "" for c in cuts)
    # p10b 실측: '오션월드'(워터파크 브랜드 이름)가 시설 낱말 없이 뽑혀 "오션월드도 가까워요"가 됐다 → 시설 낱말(사우나·키즈·조식…)이 든 사실만 후보
    cands = [f for f in list(h.get("verified_facilities") or []) + list(h.get("official_facts") or []) if FACILITY_RX.search(f)]
    pick = None
    for f in cands:
        ws = [w for w in _words(f) if FACILITY_RX.search(w)]
        if ws and not any(w in seen for w in ws):
            pick = f; break
    if not pick:
        return None
    photo_cuts = [c for c in cuts if not c["veo"] and c["section"] != "hook"]
    first_offer = next((c["i"] for c in cuts if c["section"] == "offer"), None)
    photo_cuts = [c for c in photo_cuts if c["i"] != first_offer] or photo_cuts
    if not photo_cuts:
        return None
    order = {"special": 0, "water": 1, "offer": 2, "room": 3}
    host = sorted(photo_cuts, key=lambda c: (order.get(c["section"], 9), c["i"]))[0]
    return {"fact": pick, "i": host["i"]}


CONNECTORS = ("그리고", "그 옆", "옆엔", "옆에는", "안으로", "들어가면", "들어서면", "올라오면", "올라가면", "내려가면", "나가면", "나오면", "창밖", "밤이", "밤엔", "저녁",
              "아침", "낮엔", "여기에", "여기서", "여긴", "그래서", "덕분에", "다만", "특히", "이렇게", "게다가", "그러면", "그럼", "그러니", "거기에", "한편", "바로",
              "그 뒤", "그다음", "다음은", "이제", "마지막", "참고로", "대신", "무엇보다", "특별히", "실내", "밖으로", "위로", "아래")


def flow_errs(s: dict, cuts: list[dict]) -> list[str]:
    """나열 방지 검사: 컷 2 이후 문장의 60% 이상이 연결어로 시작하고, 같은 문장 끝이 3번 연속 나오지 않는다."""
    got = {int(x.get("i", 0)): str(x.get("narration", "")).strip() for x in (s.get("cuts") or []) if isinstance(x, dict)}
    rest = [got.get(c["i"], "") for c in cuts[1:]]
    if not rest:
        return []
    errs = []
    linked = sum(1 for n in rest if any(w in n[:10] for w in CONNECTORS))     # 연결어가 문장 첫 10자 안에
    if linked < max(1, int(round(len(rest) * 0.6))):
        errs.append(f"컷 2부터는 앞 컷을 받는 연결어로 시작 (지금 {linked}/{len(rest)}) — 나열 금지")
    ends = [re.sub(r"[.!?~\s]+$", "", n)[-3:] for n in [got.get(c["i"], "") for c in cuts]]
    for k in range(2, len(ends)):
        if ends[k] and ends[k] == ends[k - 1] == ends[k - 2]:
            errs.append(f"문장 끝 '{ends[k]}' 3번 연속 — 끝맺음을 바꾼다")
            break
    return errs


POLISH_SYSTEM = """너는 쇼츠 나레이션 편집자다. 아래 JSON 대본을 **소리 내어 읽었을 때 한 사람이 한 호흡으로 안내하듯 이어지게** 다듬는다.
지켜야 할 것: 컷 수·순서·각 컷의 사실(시설·전망·조건)·자막(caption)·extra·title·caption·hashtags 는 그대로. 숙소 이름 금지. 가격·과장 금지. 각 컷의 글자 한도(공백 제외, 입력에 적힘)를 지킨다.
바꿀 것: 컷 2부터 앞 컷을 받는 연결어·장면 전환어로 시작하게 하고("안으로 들어가면", "그 옆엔", "객실로 올라오면", "밤이 되면", "그래서", "다만" …), 같은 연결어·같은 문장 끝을 연속해서 쓰지 않는다.
마지막 컷은 "…에게 추천해요"로 닫는다. 출력은 입력과 같은 구조의 JSON 만."""


def polish_script(model: str, s: dict, cuts: list[dict], h: dict, req: dict, sig: dict | None) -> dict:
    """연결성 다듬기 한 번 — 통과하면 다듬은 것을, 아니면 원본을 쓴다 (사실·길이 규칙은 check_script 가 다시 본다)."""
    limits = "\n".join(f"컷 {c['i']}: {c['lo']}~{c['hi'] + (EXTRA_BONUS if sig and sig['i'] == c['i'] else 0)}자" for c in cuts)
    try:
        t = ms.gemini_json(model, POLISH_SYSTEM, "글자 한도:\n" + limits + "\n\n대본 JSON:\n" + json.dumps(s, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        log(f"다듬기 실패(원본 유지): {str(e)[:80]}")
        return s
    for k in ("title", "caption", "hashtags", "extra"):
        t.setdefault(k, s.get(k))
    errs = check_script(t, h, cuts, req, sig) + flow_errs(t, cuts)
    if errs:
        log("다듬은 대본이 규칙에 걸려 원본 유지:", errs[:3])
        return s
    t["cuts"] = sorted(t["cuts"], key=lambda x: int(x["i"]))
    return t


def write_script(model: str, req: dict, h: dict, cuts: list[dict]) -> dict:
    lines = [f"테마: {req.get('theme')} · 지역: {req.get('region')} · 시기: {req.get('month')}", f"프로필 폴더 이름: {mt.folder_name(req)}",
             f"숙소(영상에서는 말하지 말 것 · 제목·캡션에만): {h['name']}" + (f" ({h.get('city')})" if h.get("city") else "") + (f" — {h['signature']}" if h.get("signature") else ""),
             f"지역 호칭 후보: {' / '.join(region_words(req, h))} (컷 2 에서 '지역 + 유형'으로 한 번)",
             "컷 목록 (화면에 실제로 보이는 것 — 이 순서대로 문장 1개씩):"]
    for c in cuts:
        lines.append(f"  {cut_label(c)}: {c['shot'].get('description') or photos.KO[c['shot']['category']]}  [{mt.SRC_KO.get(c['shot'].get('source'), '')}]")
    sig = pick_signature(h, cuts)
    lines += [f"쿠팡 객실 이름: {', '.join(h['room_names'])}",
              f"확인된 시설: {', '.join(h['verified_facilities']) or '없음'} / 객실 이름의 테마 단어: {', '.join(h['theme_hits']) or '없음'}",
              f"공식 홈페이지 사실: {', '.join(h.get('official_facts') or []) or '없음'}",
              f"후기 아쉬움: {h.get('honest') or '없음'}",
              (f"사진 없는 시그니처(컷 {sig['i']} 문장 끝에 한 절로 덧붙이기 · 한도 +{EXTRA_BONUS}자): {sig['fact']}" if sig else "사진 없는 시그니처: 없음 (extra 는 null)")]
    content = "\n".join(lines)
    errs = []
    for attempt in range(3):
        extra = ("\n\n직전 답의 문제(고쳐서 다시): " + " / ".join(errs)) if errs else ""
        s = ms.gemini_json(model, SCRIPT_SYSTEM, content + extra)
        errs = check_script(s, h, cuts, req, sig)
        if not errs:
            errs = flow_errs(s, cuts)
        if not errs:
            s["cuts"] = sorted(s["cuts"], key=lambda x: int(x["i"]))
            if not sig:
                s["extra"] = None
            return polish_script(model, s, cuts, h, req, sig)
        log(f"대본 검사 실패({attempt + 1}):", errs)
    raise RuntimeError("대본이 규칙을 통과하지 못함: " + " / ".join(errs))


def cta_text(folder: str, pos: int) -> str:
    return f"객실 타입이랑 링크는 프로필 '{folder}' 폴더 {pos}번에 정리해 뒀어요."


# ── 화면 검수 (컷 사진 ↔ 문장) ───────────────────────────────────────────────────────────
def _vision_json(model: str, system: str, text: str, image: Path) -> dict:
    body = {"system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": text}, {"inline_data": {"mime_type": "image/jpeg", "data": photos._small_jpeg_b64(str(image))}}]}],
            "generationConfig": {"maxOutputTokens": 500, "temperature": 0.2, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = ms._gpost(f"models/{model}:generateContent", body, 90)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        data = ms._gpost(f"models/{model}:generateContent", body, 90)
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    txt = "".join(p.get("text", "") for p in parts).strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    return json.loads(m.group(0)) if m else {}


def screen_qa(models: dict, cuts: list[dict], script: dict, h: dict, req: dict) -> list[dict]:
    """컷마다: 사진 + 문장·자막 → 일치도 0~10. 기준 미달이면 사진은 두고 **문장만** 다시 쓴다(한 번). 기록은 report['screen_qa']."""
    out = []
    by_i = {int(x["i"]): x for x in script["cuts"]}
    for c in cuts:
        x = by_i[c["i"]]
        thr = QA_THR.get(c["section"], 7)
        row = {"i": c["i"], "section": c["section"], "threshold": thr, "narration": x["narration"], "caption": x["caption"]}
        img = B() / f"shot_{c['n']}.png"
        ex = script.get("extra") if isinstance(script.get("extra"), dict) else None
        note = (f"\n덧붙임(허용 · 감점 금지): 이 문장 끝의 '{ex.get('tag', '')}' 시설은 사진에 없지만 화면에 태그로 표시된다" if ex and int(ex.get("i", 0)) == c["i"] else "")
        if c["i"] == cuts[-1]["i"]:
            note += "\n이 컷은 마지막 컷이라 수정 문장에도 '추천해요'가 들어가야 한다"
        try:
            r = ms._try_models("vision", models["text"], lambda m: _vision_json(m, SCREEN_SYSTEM.format(lo=c["lo"], hi=c["hi"] + (EXTRA_BONUS if note else 0)),
                                                                                f"구간: {KO[c['section']]}\n나레이션: {x['narration']}\n자막: {design.plain(x['caption'])}{note}", img))
            row.update({"score": int(r.get("score", -1)), "seen": str(r.get("seen", ""))[:80], "problem": str(r.get("problem", ""))[:120]})
        except Exception as e:  # noqa: BLE001
            row.update({"score": None, "error": str(e)[:100]})
            out.append(row); continue
        fix = str(r.get("fix", "")).strip()
        last = (c["i"] == cuts[-1]["i"])
        if last and fix and "추천" not in fix:                           # p10 실측: 마지막 컷 교체문에서 '추천해요'가 빠졌다 → 교체 거부
            row["fix_rejected"] = fix; fix = ""
        if row["score"] is not None and 0 <= row["score"] < thr and fix and not note and not sentence_errs(fix, c, h, req):
            x["narration"] = fix
            row["fixed"] = fix
            try:
                r2 = ms._try_models("vision", models["text"], lambda m: _vision_json(m, SCREEN_SYSTEM.format(lo=c["lo"], hi=c["hi"]),
                                                                                     f"구간: {KO[c['section']]}\n나레이션: {fix}\n자막: {design.plain(x['caption'])}", img))
                row["score2"] = int(r2.get("score", -1))
            except Exception as e:  # noqa: BLE001
                row["score2"] = None; row["error2"] = str(e)[:80]
            log(f"컷 {c['i']} 화면 검수 {row['score']} → 문장 교체 ({row.get('score2')}): {fix}")
        out.append(row)
    return out


# ── 음성 ───────────────────────────────────────────────────────────────────────────────
def silences(wav: Path, noise_db: int, min_sec: float) -> list[tuple[float, float]]:
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", f"silencedetect=noise={noise_db}dB:d={min_sec}", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(m) for m in re.findall(r"silence_start: ([0-9.]+)", out)]
    ends = [float(m) for m in re.findall(r"silence_end: ([0-9.]+)", out)]
    return list(zip(starts, ends))


def split_narration(full: Path, keys: list, texts: list[str] | None = None) -> dict | None:
    """전체 나레이션 wav 를 문장 사이 무음에서 n 조각으로 자른다.
    p10b 실측: "무음이 정확히 n-1 개" 조건은 쉼표 쉼(짧은 무음)이 섞이면 거의 안 맞는다 → **가장 긴 무음 n-1 개**를 경계로 잡고,
    조각 길이가 문장 글자 수 비율(±45%)과 맞는지로 검증한다. 안 맞으면 None(컷마다 합성으로 복귀). 진단은 기록에 남긴다."""
    n = len(keys)
    total = ms.probe_duration(full)
    if texts and len(texts) == n:
        w = [len(re.sub(r"\s", "", t)) + 3 for t in texts]          # +3 = 문장 끝 쉼 몫
    else:
        w = [1] * n
    frac = [x / sum(w) for x in w]
    why = []
    for noise, d in ((-35, 0.12), (-38, 0.12), (-32, 0.14), (-40, 0.10), (-30, 0.16)):
        sil = [(a, b) for a, b in silences(full, noise, d) if a > 0.3 and b < total - 0.3]
        if len(sil) < n - 1:
            why.append(f"{noise}dB/{d}s: 무음 {len(sil)}개(<{n - 1})"); continue
        top = sorted(sorted(sil, key=lambda ab: ab[1] - ab[0], reverse=True)[:n - 1])
        bounds = [0.0] + [(a + b) / 2 for a, b in top] + [total]
        durs = [bounds[k + 1] - bounds[k] for k in range(n)]
        ratio = [dd / (total * f) for dd, f in zip(durs, frac)]
        bad = [k + 1 for k, r in enumerate(ratio) if not (0.55 <= r <= 1.45) or durs[k] < 0.8]
        if bad:
            why.append(f"{noise}dB/{d}s: 길이 비율 어긋난 조각 {bad} " + " ".join(f"{r:.2f}" for r in ratio)); continue
        narr = {}
        for k, key in enumerate(keys):
            a, b = bounds[k], bounds[k + 1]
            out = B() / (f"narr_c{key}.wav" if isinstance(key, int) else f"narr_{key}.wav")
            ms.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(full),
                    "-af", "afade=t=in:d=0.02,afade=t=out:st=" + f"{max(0.0, b - a - 0.04):.3f}" + ":d=0.04", str(out)])
            narr[key] = round(b - a, 3)
        log(f"나레이션 한 번 합성 → {n}조각 분할 (무음 {noise}dB·{d}s 중 긴 것 {n - 1}개 · 전체 {total:.1f}초 · 비율 " + " ".join(f"{r:.2f}" for r in ratio) + ")")
        return narr
    log("무음 분할 실패 진단: " + " | ".join(why[:5]))
    return None


def narrate(models: dict, script: dict, voice: str, tempo: float) -> dict:
    """나레이션 전체를 **한 번에** 합성해 문장 사이 무음에서 자른다 → 한 목소리·한 호흡(운영자 "중간에 목소리가 바뀐다, 나열처럼 들린다").
    분할이 안 맞으면(무음 수 ≠ 문장 수-1) 예전처럼 컷마다 따로 합성한다."""
    keys = [int(x["i"]) for x in script["cuts"]] + ["cta"]
    texts = [x["narration"].strip() for x in script["cuts"]] + [script["cta"]["narration"].strip()]
    if len(keys) >= 3:
        try:
            full = B() / "narr_full.wav"
            mt.tts(models, "\n\n".join(texts), full, voice, tempo)
            got = split_narration(full, keys, texts)
            if got:
                return got
            log("⚠️ 무음 분할이 문장 수와 안 맞아 컷마다 따로 합성한다")
        except Exception as e:  # noqa: BLE001
            log(f"⚠️ 전체 합성 실패 → 컷마다 따로: {str(e)[:100]}")
    narr = {}
    for x in script["cuts"]:
        narr[int(x["i"])] = mt.tts(models, x["narration"], B() / f"narr_c{int(x['i'])}.wav", voice, tempo)
    narr["cta"] = mt.tts(models, script["cta"]["narration"], B() / "narr_cta.wav", voice, tempo)
    return narr


def qa_items(script: dict) -> list[tuple[str, str, Path]]:
    return [(f"컷{int(x['i'])}", x["narration"], B() / f"narr_c{int(x['i'])}.wav") for x in script["cuts"]] + [("끝", script["cta"]["narration"], B() / "narr_cta.wav")]


# ── 공통 준비 (미리보기·제작) ────────────────────────────────────────────────────────────
def prepare(req: dict, models: dict, report: dict) -> dict:
    voice, tempo = str(req.get("voice") or ms.VOICE_DEFAULT), float(req.get("tempo") or mt.TEMPO)
    B().mkdir(parents=True, exist_ok=True)
    h, pos0 = assets(req, models, report)
    cuts = plan_cuts(h, int(req.get("max_veo_cuts") or 4))
    report["cuts"] = [{"i": c["i"], "section": c["section"], "n": c["n"], "veo": c["veo"], "source": c["shot"].get("source"), "seen": c["shot"].get("description")} for c in cuts]
    log("컷: " + " · ".join(f"{c['i']}{KO[c['section']][0]}{'V' if c['veo'] else ''}" for c in cuts))
    script = ms._try_models("text", models["text"], lambda m: write_script(m, req, h, cuts))
    qa = screen_qa(models, cuts, script, h, req)
    report["screen_qa"] = qa
    folder = mt.folder_name(req)
    hook_shot = cuts[0]["shot"]
    cover = (B() / f"shotHD_{hook_shot['n']}.png") if hook_shot.get("source") == "coupang" else None
    try:
        pos = make_folder.place_hotel(req, h, pos0, cover)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]}) — 순위표 위치로 대체")
        pos = pos0 or 1
    script["cta"] = {"narration": cta_text(folder, pos), "caption": f"프로필 링크 → {folder} {pos}번"}
    report["script"] = script
    for x in script["cuts"]:
        report["cuts"][int(x["i"]) - 1].update({"narration": x["narration"], "caption": x["caption"]})
    narr = narrate(models, script, voice, tempo)
    report["narration_sec"] = {str(k): round(v, 2) for k, v in narr.items()}
    nqa = mt.narration_qa(models, qa_items(script))
    report["narration_qa"] = nqa
    return {"h": h, "cuts": cuts, "script": script, "qa": qa, "nqa": nqa, "narr": narr, "folder": folder, "pos": pos, "voice": voice, "tempo": tempo}


def preview_sheet(h: dict, cuts: list[dict], script: dict, qa: list[dict], out: Path):
    """컷 9장을 3열로 — 사진 · 구간/출처 · 자막 · 문장 · 화면 검수 점수. 영상 전에 눈으로 판단."""
    from PIL import Image, ImageDraw
    f = design.font(26, bold=False); f2 = design.font(22, bold=False); fb = design.font(26)
    w, hh = 330, 587
    cols = 3
    rows = -(-len(cuts) // cols)
    im = Image.new("RGB", (cols * (w + 20) + 20, 70 + rows * (hh + 150)), (20, 22, 28))
    d = ImageDraw.Draw(im)
    d.text((20, 18), f"{h['name']}  ·  컷 {len(cuts)}개 + 끝 카드  ·  영상에서는 이름 비공개", font=fb, fill=(94, 234, 212))
    by_i = {int(x["i"]): x for x in script["cuts"]}
    qa_i = {q["i"]: q for q in qa}
    for k, c in enumerate(cuts):
        x = 20 + (k % cols) * (w + 20); y = 70 + (k // cols) * (hh + 150)
        try:
            t = Image.open(B() / f"shot_{c['n']}.png").convert("RGB").resize((w, hh), Image.LANCZOS)
            im.paste(t, (x, y))
        except Exception:  # noqa: BLE001
            d.rectangle([x, y, x + w, y + hh], fill=(40, 40, 48))
        d.rectangle([x, y, x + w, y + 34], fill=(0, 0, 0))
        d.text((x + 8, y + 6), f"{cut_label(c)}  [{mt.SRC_KO.get(c['shot'].get('source'), '?')}]", font=f2, fill=(255, 255, 255))
        sx = by_i.get(c["i"], {})
        q = qa_i.get(c["i"], {})
        sc = q.get("score")
        col = (94, 234, 212) if (sc or 0) >= q.get("threshold", 7) else (255, 120, 120) if sc is not None else (200, 200, 200)
        d.text((x, y + hh + 8), f"자막: {sx.get('caption', '')}", font=f, fill=(255, 255, 255))
        d.text((x, y + hh + 40), f"화면 검수 {sc if sc is not None else '-'}/10" + (f" → 교체 후 {q.get('score2')}" if q.get("fixed") else ""), font=f2, fill=col)
        narr = str(sx.get("narration", ""))
        for j, line in enumerate([narr[i:i + 24] for i in range(0, len(narr), 24)][:3]):
            d.text((x, y + hh + 70 + j * 26), line, font=f2, fill=(225, 225, 230))
    im.save(out, "JPEG", quality=86)


def preview_md(req: dict, p: dict) -> str:
    h, cuts, script, qa, nqa = p["h"], p["cuts"], p["script"], p["qa"], p["nqa"]
    by_i = {int(x["i"]): x for x in script["cuts"]}
    qa_i = {q["i"]: q for q in qa}
    md = [f"# 미리보기(단일 숙소 · 컷 단위) — {h['name']} · {req.get('region')} · {req.get('theme')} · {req.get('month')}",
          f"프로필 폴더: **{p['folder']}** · 폴더에서 **{p['pos']}번** · 영상에서는 숙소 이름 비공개(캡션·고정 댓글에 공개)", "",
          "## 컷 (한 컷 = 사진 1장 = 문장 1개 · 재사용 없음)", "",
          "| 컷 | 구간 | 화면에 보이는 것 | 자막 | 나레이션 | 화면 검수 | 초 |", "|---|---|---|---|---|---|---|"]
    for c in cuts:
        x = by_i[c["i"]]; q = qa_i.get(c["i"], {})
        sc = q.get("score"); mark = "" if sc is None else ("통과" if sc >= q.get("threshold", 7) else "미달")
        fx = f" → 교체 {q.get('score2')}" if q.get("fixed") else ""
        ex = script.get("extra") if isinstance(script.get("extra"), dict) else None
        tag = f" 〔태그 {ex.get('tag')}〕" if ex and int(ex.get("i", 0)) == c["i"] else ""
        md.append(f"| {c['i']}{' (Veo)' if c['veo'] else ''} | {KO[c['section']]} | {c['shot'].get('description', '')} [{mt.SRC_KO.get(c['shot'].get('source'), '?')}] | {x['caption']}{tag} | {x['narration']} | {sc if sc is not None else '-'} {mark}{fx} | {p['narr'][c['i']]:.1f} |")
    md.append(f"| 끝 | 끝 카드 | 대표 사진 블러 | {script['cta']['caption']} | {script['cta']['narration']} | - | {p['narr']['cta']:.1f} |")
    md += ["", "## 나레이션 받아쓰기 검증", "", "| 컷 | 대본 | 들린 것 | 일치 | 판정 |", "|---|---|---|---|---|"]
    for q in nqa:
        md.append(f"| {q['segment']} | {q['script']} | {q['heard']} | {q['similarity']} | {'통과' if q['ok'] else '실패 ' + ','.join(q['instruction_words'])} |")
    pc = h.get("photo_counts") or {}
    md += ["", "## 숙소·사진", "",
           f"- 확인된 시설: {', '.join(h['verified_facilities']) or '없음'} · 후기 30일 {h.get('blog_30d')} · 사진 후보 공식 홈페이지 {pc.get('official', 0)}장 · 쿠팡 {pc.get('coupang', 0)}장"
           + (f" · 다른 지점 의심 제외 {pc['mismatch']}장" if pc.get("mismatch") else ""),
           f"- 공식 홈페이지 사실: {', '.join(h.get('official_facts') or []) or '없음'}" + (f" · 한 줄: {h['signature']}" if h.get("signature") else ""),
           f"- 후기 아쉬움: {h.get('honest') or '없음'}", f"- 제목: {script.get('title')} · 해시태그: {' '.join(script.get('hashtags') or [])}",
           "", "사진 출처 장부: `data/runs/latest/photo_sources.json`"]
    return "\n".join(md) + "\n"


def preview_solo(req: dict, models: dict, report: dict) -> dict:
    p = prepare(req, models, report)
    prev = ms.PREVIEW
    prev.mkdir(parents=True, exist_ok=True)
    if (B() / "narr_full.wav").exists():                        # 한 번에 합성한 원본 그대로 들려준다 (한 호흡)
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(B() / "narr_full.wav"), "-c:a", "libmp3lame", "-b:a", "96k", str(prev / "narration_preview.mp3")])
    else:
        names = [f"narr_c{int(x['i'])}.wav" for x in p["script"]["cuts"]] + ["narr_cta.wav"]
        (B() / "narr_list.txt").write_text("".join(f"file '{n}'\nfile 'gap.wav'\n" for n in names), encoding="utf-8")
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", "0.4", "-i", "anullsrc=r=24000:cl=mono", str(B() / "gap.wav")])
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(B() / "narr_list.txt"), "-c:a", "libmp3lame", "-b:a", "96k", str(prev / "narration_preview.mp3")])
    preview_sheet(p["h"], p["cuts"], p["script"], p["qa"], prev / "preview_shots.jpg")
    (prev / "preview.md").write_text(preview_md(req, p), encoding="utf-8")
    meta = {"mode": "solo", "stage": "preview", "stay": p["h"]["name"], "title": p["script"].get("title"), "folder": p["folder"], "folder_pos": p["pos"],
            "voice": p["voice"], "narration_mode": ("single_pass" if (B() / "narr_full.wav").exists() else "per_cut"),
            "narration_qa_ok": all(q["ok"] for q in p["nqa"]), "screen_qa_ok": all((q.get("score") or 0) >= q.get("threshold", 7) for q in p["qa"] if q.get("score") is not None),
            "cuts": len(p["cuts"]), "veo_cuts": sum(1 for c in p["cuts"] if c["veo"]), "files": ["preview.md", "preview_shots.jpg", "narration_preview.mp3"]}
    (B() / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


# ── 영상 조립 ───────────────────────────────────────────────────────────────────────────
def photo_clip(image: Path, sec: float, out: Path, pattern: str) -> Path:
    """사진 1장 → 정확히 sec 초의 무빙 클립 (0원). 2160x3840 으로 키운 뒤 zoompan → 1080x1920 (서브픽셀 떨림 완화).
    push: 천천히 밀고 들어감 · pull: 물러남 · pan: 왼쪽→오른쪽 · tilt: 아래→위."""
    F = max(2, int(round(sec * ms.FPS)))
    z = {"push": f"1.0+0.10*on/{F}", "pull": f"1.10-0.10*on/{F}", "pan": "1.12", "tilt": "1.12"}[pattern]
    x = {"push": "iw/2-(iw/zoom/2)", "pull": "iw/2-(iw/zoom/2)", "pan": f"(iw-iw/zoom)*on/{F}", "tilt": "iw/2-(iw/zoom/2)"}[pattern]
    y = {"push": "ih/2-(ih/zoom/2)", "pull": "ih/2-(ih/zoom/2)", "pan": "ih/2-(ih/zoom/2)", "tilt": f"(ih-ih/zoom)*(1-on/{F})"}[pattern]
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(ms.FPS), "-i", str(image),
            "-vf", f"scale=2160:3840:flags=lanczos,zoompan=z='{z}':x='{x}':y='{y}':d={F}:s=1080x1920:fps={ms.FPS},setsar=1",
            "-frames:v", str(F), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)])
    return out


def cut_segment(idx: int, src: Path, L: float, wav: Path | None, overlays: list[dict], slow: float = 1.0, image: bool = False, fade_in: float = 0.0) -> Path:
    """컷 하나 = 영상 1개(또는 카드 이미지) + 겹침판들 + 그 컷의 나레이션. overlays: {"path","a","b","anim"} — anim 은 0.12초 페이드 + 14px 올라오기.
    L 초로 정확히 맞춘다. 영상이 짧으면 최대 slow 배까지만 느리게, 그래도 모자라면 마지막 프레임 유지(기록에 남김 — 글자 한도로 거의 안 생긴다)."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    cmd += (["-loop", "1", "-t", f"{L:.3f}", "-i", str(src)] if image else ["-i", str(src)])
    for ov in overlays:
        cmd += ["-loop", "1", "-t", f"{L:.3f}", "-i", str(ov["path"])]
    if wav:
        cmd += ["-i", str(wav)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{L:.3f}", "-i", "anullsrc=r=24000:cl=mono"]
    avail = L if image else ms.probe_duration(src)
    stretched = avail * slow
    pad = max(0.0, L - stretched - 0.02)
    if pad > 0.05 and not image:
        log(f"⚠️ 컷 {idx}: 영상 {avail:.2f}초 × {slow:.2f} < 필요 {L:.2f}초 → 마지막 프레임 {pad:.2f}초 유지")
    vf = f"[0:v]scale={ms.W}:{ms.H}:force_original_aspect_ratio=increase:flags=lanczos,crop={ms.W}:{ms.H},setsar=1"
    if slow > 1.001:
        vf += f",setpts={slow:.4f}*PTS"
    vf += f",fps={ms.FPS},{design.GRADE}"
    if pad > 0:
        vf += f",tpad=stop_mode=clone:stop_duration={pad:.3f}"
    if fade_in > 0:
        vf += f",fade=t=in:st=0:d={fade_in:.2f}"
    fc = vf + "[v0];"
    cur, k = "v0", 1
    for j, ov in enumerate(overlays):
        a, b = float(ov.get("a", 0.0)), float(ov.get("b", 99.0))
        if ov.get("anim"):
            fc += f"[{k}:v]format=rgba,fade=t=in:st={a:.3f}:d=0.12:alpha=1[o{j}];"
            fc += f"[{cur}][o{j}]overlay=0:y='14*max(0,1-(t-{a:.3f})/0.15)':format=auto:enable='between(t,{a:.3f},{b:.3f})'[v{j + 1}];"
        else:
            fc += f"[{k}:v]format=rgba[o{j}];[{cur}][o{j}]overlay=0:0:format=auto:enable='between(t,{a:.3f},{b:.3f})'[v{j + 1}];"
        cur = f"v{j + 1}"; k += 1
    fc += f"[{cur}]format=yuv420p[v];[{k}:a]apad[a]"
    out = B() / f"seg_{idx:02d}.mp4"
    ms.run(cmd + ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{L:.3f}", "-r", str(ms.FPS),
                  "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", str(out)])
    return out


def mix_bgm(video: Path, bgm: Path, out: Path, total: float, level: float = BGM_LEVEL) -> Path:
    """배경음악을 영상 길이만큼 반복해 깔고, 나레이션이 나올 때는 사이드체인 압축으로 자동으로 낮춘다(덕킹). 끝 1.5초 페이드아웃."""
    T = max(1.0, total)
    fc = (f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume={level:.3f},atrim=0:{T:.3f},asetpts=PTS-STARTPTS,"
          f"afade=t=in:st=0:d=0.8,afade=t=out:st={max(0.0, T - 1.5):.3f}:d=1.5[bg];"
          f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[v1][v2];"
          f"[bg][v2]sidechaincompress=threshold=0.015:ratio=6:attack=30:release=500[bgd];"
          f"[v1][bgd]amix=inputs=2:duration=first:normalize=0[a]")
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-stream_loop", "-1", "-i", str(bgm), "-filter_complex", fc,
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(out)])
    return out


def make_veo(cuts: list[dict], theme: str, report: dict) -> dict:
    """Veo 컷 생성 (돈). 실패하면 그 컷은 사진 무빙으로 내려간다. 돌려주는 것: n → 클립 경로."""
    clips, results = {}, []
    todo = [c for c in cuts if c["veo"]]
    log(f"Veo {len(todo)}컷 · 예상 약 {veo.estimate_krw(len(todo), VEO_SEC):,.0f}원 · 이번 달 누적 {veo.month_total():,.0f}원")
    for c in todo:
        n, out = c["n"], B() / f"veo_{c['n']}.mp4"
        row = {"i": c["i"], "n": n, "ok": False, "krw": 0.0}
        before = veo.spent_this_run()
        seed = veo.seed_for(theme, n)
        for attempt in range(2):
            try:
                veo.make_clip(c["shot"]["prompt"], B() / f"shot_{n}.png", VEO_SEC, out, seed + attempt)
                row["ok"] = True; clips[n] = out; break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:120]}"
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"; break
            except veo.VeoError as e:
                row["error"] = str(e)[:160]; break
        if not row["ok"]:
            c["veo"] = False                                   # 사진 무빙으로 대체 (글자 한도는 이미 Veo 기준으로 짧게 써졌다 — 문제 없음)
            log(f"컷 {c['i']} Veo 실패 → 사진 무빙: {row.get('error')}")
        row["krw"] = round(veo.spent_this_run() - before)
        results.append(row)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": results, "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}
    return clips


def produce_solo(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    theme = str(req.get("theme") or "")
    style = str(req.get("caption_style") or design.DEFAULT_STYLE)
    p = prepare(req, models, report)
    h, cuts, script, narr, folder, pos = p["h"], p["cuts"], p["script"], p["narr"], p["folder"], p["pos"]
    name = h["name"]
    clips = make_veo(cuts, theme, report)

    pill = f"폴더 · {folder} · {pos}번"
    frame = B() / "ov_frame.png"
    design.caption_png(frame, "", style, pill=pill, disclosure=ms.DISCLOSURE)     # 모든 컷에 고정: 폴더 표시 + 고지문
    chip = None
    if h.get("blog_30d"):
        chip = design.chip_png(B() / "ov_chip.png", f"최근 30일 후기 {int(h['blog_30d']):,}건{'+' if int(h['blog_30d']) >= 1000 else ''}", "네이버 블로그 기준")
    honest = f"아쉬움: {h['honest']}" if h.get("honest") else ""
    first_offer = next((c["i"] for c in cuts if c["section"] == "offer"), None)
    by_i = {int(x["i"]): x for x in script["cuts"]}
    segs, timeline, k_pattern = [], [], 0
    for c in cuts:
        x = by_i[c["i"]]
        L = max(MIN_CUT, narr[c["i"]] + (0.12 if (B() / "narr_full.wav").exists() else GAP))
        cap = B() / f"ov_cap_{c['i']:02d}.png"
        design.caption_png(cap, x["caption"], style, hook=(c["section"] == "hook"), sub=(honest if c["i"] == first_offer else ""))
        overlays = [{"path": frame, "a": 0, "b": 99, "anim": False}, {"path": cap, "a": 0.0, "b": 99, "anim": True}]
        ex = script.get("extra") if isinstance(script.get("extra"), dict) else None
        if ex and int(ex.get("i", 0)) == c["i"]:                      # 사진 없는 시그니처: 문장 후반에 '+ 시설' 태그 칩 — "이것도 있다"로 읽히게
            tag = B() / f"ov_tag_{c['i']:02d}.png"
            design.tag_png(tag, str(ex.get("tag", "")))
            overlays.append({"path": tag, "a": round(L * 0.45, 2), "b": 99, "anim": True})
        if chip and c["i"] == 2:
            overlays.append({"path": chip, "a": 0.3, "b": min(L, 2.1), "anim": True})
        slow = 1.0
        if c["veo"] and c["n"] in clips:
            src = clips[c["n"]]
            avail = ms.probe_duration(src)
            slow = min(MAX_SLOW, L / avail) if L > avail else 1.0
            kind = "Veo"
        else:
            pattern = PATTERNS[k_pattern % len(PATTERNS)]; k_pattern += 1
            src = photo_clip(B() / f"shotHD_{c['n']}.png", L, B() / f"pan_{c['n']}.mp4", pattern)
            kind = f"사진·{pattern}"
        segs.append(cut_segment(c["i"], src, L, B() / f"narr_c{c['i']}.wav", overlays, slow))
        timeline.append({"i": c["i"], "section": c["section"], "kind": kind, "sec": round(L, 2), "slow": round(slow, 2), "narration": x["narration"], "caption": x["caption"],
                         "extra": (ex.get("tag") if ex and int(ex.get("i", 0)) == c["i"] else None)})
    # 끝 카드 — 훅 사진 블러 배경, "프로필 링크 → 폴더 N번"
    card = design.end_card(B() / "end_card.jpg", B() / f"shotHD_{cuts[0]['n']}.png", folder, pos, style, ms.DISCLOSURE)
    Lc = max(3.6, narr["cta"] + 0.7)
    segs.append(cut_segment(99, card, Lc, B() / "narr_cta.wav", [], image=True, fade_in=0.3))
    timeline.append({"i": "끝", "section": "cta", "kind": "카드", "sec": round(Lc, 2), "narration": script["cta"]["narration"], "caption": script["cta"]["caption"]})

    (B() / "concat.txt").write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    video = B() / "video.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(B() / "concat.txt"), "-c", "copy", "-movflags", "+faststart", str(video)])
    total = ms.probe_duration(video)
    # 배경음악 (2026-10-11 운영자 "대표 배경음악 하나"): assets/music/bgm.mp3 가 있으면 깔고 나레이션 아래로 덕킹. request.json "bgm": false 로 끌 수 있다
    bgm_req = req.get("bgm", True)
    bgm_path = BGM if bgm_req is True else (mt.ROOT / "assets" / "music" / f"{bgm_req}.mp3" if isinstance(bgm_req, str) else None)
    if bgm_path and bgm_path.exists():
        nob = B() / "video_nobgm.mp4"
        nob.unlink(missing_ok=True); video.rename(nob)
        mix_bgm(nob, bgm_path, video, total)
        report["bgm"] = bgm_path.name
        log(f"배경음악 {bgm_path.name} 적용 (레벨 {BGM_LEVEL} · 덕킹)")
    else:
        report["bgm"] = None
    veo_shots = [c["shot"] for c in cuts if c["n"] in clips]
    if veo_shots:
        ms.compare_images(veo_shots, clips, B(), ms.PREVIEW)
    preview_sheet(h, cuts, script, p["qa"], ms.PREVIEW / "preview_shots.jpg")
    (ms.PREVIEW / "preview.md").write_text(preview_md(req, p), encoding="utf-8")
    report["timeline"] = timeline

    pc = h.get("photo_counts") or {}
    caption = (ms.DISCLOSURE + "\n\n" + str(script.get("caption", "")).strip()
               + f"\n\n{name}" + (f" · {h['city']}" if h.get("city") else "")
               + f"\n객실 타입·가격대·링크는 프로필 링크 → '{folder}' 폴더 {pos}번"
               + ("\n사진: 숙소 공식 홈페이지" if pc.get("official") else "")
               + "\n\n" + " ".join(script.get("hashtags") or []))
    meta = {"mode": "solo", "stay": name, "title": script.get("title"), "caption": caption, "folder": folder, "folder_pos": pos, "caption_style": style, "bgm": report.get("bgm"),
            "pinned_comment": f"{name} — 객실 타입·링크는 프로필 링크 → '{folder}' 폴더 {pos}번 (쿠팡 파트너스 링크 포함)",
            "affiliate_urls": {name: h["affiliate_url"]}, "lines": [x["narration"] for x in script["cuts"]] + [script["cta"]["narration"]],
            "cuts": timeline, "screen_qa_ok": all((q.get("score") or 0) >= q.get("threshold", 7) for q in p["qa"] if q.get("score") is not None),
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": sum(1 for r in report["veo"]["clips"] if r["ok"]), "clips_total": len(report["veo"]["clips"]),
                    "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
