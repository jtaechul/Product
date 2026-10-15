"""시그니처 이야기 쇼츠 — mode "signature" v4 (2026-10-15 운영자 "진행해" · 구조안 A '장점 하나, 여러 관점').

왜 다시 만들었나 — v3(stay-run-50 · 소노펠리체 · 약 930원) 운영자 평가 "세 컷만 하는 게 말이 되냐 · 시그니처 하나로 스토리를 연결해서
흥미를 점점 증폭시켜야지". 벤치마크 4편(운영자 업로드)을 컷·음성 단위로 뜯어 본 결과 4편 모두 **나레이션이 처음부터 끝까지 이어지는 이야기**
(음성 98~100% · 12~21컷 · 컷 1~2초 · 자막 = 나레이션 한 문장의 조각)였고, 우리 v3 는 나레이션 0% · 3컷 · 시설 이름표였다.
운영자 아이디어 "장점 하나를 다른 시각으로 계속 부각하고, 연결되는 관점에서도 계속 부각" = 벤치마크 ②(비 오는 날 노천탕)의 구조.

흐름
  1. 사진·사실 수집(make_solo.assets) → 장점(시그니처) 하나 고르기(make_sig.choose_signature — 못 고르면 코드가 정함 · 사진 2장 이상이면 멈추지 않음)
  2. 장점에 대한 사실 더 모으기 — 공식 홈페이지 글에서 그 장점에 관한 문장만(`deep_facts` · 글 호출 1번)
  3. 컷 재료 — 장점 사진마다 넓은 컷 + 비전이 고른 디테일 컷 1~2개(원본 픽셀만 잘라 확대 · 최대 1.5배) + 연결용 다른 사진(넓게)
  4. 대본 — 관점 7종을 한 문장씩: 훅(걱정·상식과 부딪히는 질문) → 정체(장점 이름) → 디테일·상황·사람·행동·연결·희소성 중 3개 이상 → 약속(첫 걱정을 푸는 한 줄).
     **관점 검사**: 훅 3초·정체 6초 안 / 훅 말고 모든 문장에 장점 낱말 / 근거(사실 번호·사진 설명) / 1인칭·과거형·분위기 말·숙소 이름·가격 금지 /
     같은 원본 사진 반복 상한 / 연결 사진은 연결 관점에서만 / 마지막 컷은 첫 장면 사진으로 돌아옴. 3번 못 지키면 걸린 문장만 사실 문장으로 고치거나 빼고 끝까지.
  5. 나레이션 한 번 합성 → 문장별 분할(make_solo.narrate · Kore · 1.28배속) + 가라오케 자막 + 훅 제목 + 배경음악(덕킹) + 끝 카드(프로필 번호)
  6. 미리보기 = AI 영상 없이(사진 무빙) 완성 영상 + 스토리보드 + 나레이션 — 글·비전·음성만(약 90원). 제작 = 미리보기 계획·음성 재사용 + 훅·정체·약속 3컷만 Veo(약 882원).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

import design
import make_folder
import make_sig as sg
import make_solo as so
import make_stay as ms
import make_top3 as mt
import photos
import veo

STORY = ms.BUILD / "story"
REUSE_DIR = ms.BUILD / "reuse"
LENSES = ("훅", "정체", "디테일", "상황", "사람", "행동", "연결", "희소성", "약속")
MID_LENSES = ("디테일", "상황", "사람", "행동", "연결", "희소성")
VEO_LENSES = ("훅", "정체", "약속")                                   # 제작 때 AI 영상(Veo 4초)으로 움직일 문장 + 사람 컷 1 = 4컷 약 1,176원
PERSON_LENSES = ("행동", "사람", "상황")                              # 사람 컷(손·뒷모습)이 들어갈 수 있는 관점 — 운영자 2026-10-15 "손이나 뒷모습 한 컷 정도는 괜찮다"
PERSON_PROMPT = {
    "hand": ("Camera: steady and locked-off, no camera movement. A single adult hand and forearm, with nothing else of the person visible, "
             "enters from the bottom edge of the frame and {action}, then rests naturally. Realistic skin, natural size matching the objects it touches. "
             "Keep every object, structure, surface and the view exactly as in the first frame; do not add any new objects, other people or text."),
    "back": ("Camera: steady, a very slow push-in. One adult seen strictly from behind (back of the head and shoulders, the face is never shown) "
             "walks into the frame from the lower edge at a realistic human scale for the furniture and floor, and {action}. "
             "Keep every object, structure, surface and the view exactly as in the first frame; do not add any new objects, other people or text."),
}
PERSON_BAN_RX = re.compile(r"face|smil|look(s|ing)? at (the )?camera|selfie|phone|cup|glass|drink|bottle|book|bag|child|kid|baby|couple|two people|friends|"
                           r"jump|run|dive|swim|splash|naked|bikini", re.I)
PERSON_CHECK_SYSTEM = """너는 AI 영상 검수자다. 같은 4초 클립의 첫 장면·2초·끝 장면 3장을 받는다. 요청: 손(또는 뒷모습 사람) 하나가 들어와 사진에 이미 있는 사물에 동작한다.
판단: person = 보이는 사람 부분('hand' 손·팔만 / 'back' 뒷모습 / 'full' 얼굴까지 / 'none' 없음), face_visible = 얼굴(눈·코·입)이 보이는가,
extra_people = 두 사람 이상인가, new_objects = 첫 장면에 없던 사물(손에 든 물건 포함), structure_changed = 건물·가구·물가·전망이 바뀌었나, weird = 손가락 수·팔 길이·크기가 이상한가.
JSON 만: {"person":"hand","face_visible":false,"extra_people":false,"new_objects":[],"structure_changed":false,"weird":false,"verdict":"ok"|"fail","reason":"한 줄"}"""
LINE_LEN = (6, 30)                                                   # 문장 글자 수(공백 제외) — 1.28배속 약 6.6자/초
TOTAL_LEN = (80, 150)                                                # 전체 나레이션(공백 제외) — 약 12~23초
BEATS = (6, 9)
MIN_VIEWS = 3                                                        # 가운데 관점 종류 최소 개수(같은 말 반복이 아니라 '다른 시각')
ADV_PHOTOS = 4                                                       # 장점 사진 최대 장 수(디테일 비전 호출 상한)
LINK_PHOTOS = 5                                                      # 연결용 다른 사진 최대 장 수
ZOOM_MAX = 1.5                                                       # 디테일 컷 확대 상한(공식 사진 1024px → 1920 높이라 더 키우면 흐려진다)
SHOT_MIN = 0.9                                                       # 한 컷 최소 길이(초) — 한 문장에 컷 2~3개일 때
MIN_HOOK = 3.2
MOTION = 0.14                                                        # 짧은 컷 사진 무빙 폭(9컷 형식 0.24 의 절반 남짓 — 1초 컷에서 흔들려 보이지 않게)
PATTERNS = ("push", "pan", "diag", "tilt", "pull")
PRICE_RX = re.compile(r"\d[\d,]*\s*(원|만원|만 원|%)")


def log(*a):
    print("[story]", *a, flush=True)


# ── 1. 장점에 대한 사실 더 모으기 ────────────────────────────────────────────────────────
DEEP_SYSTEM = """너는 숙소 공식 홈페이지 글에서 사실을 뽑는 정리자다. 숙소의 장점(시설·공간) 이름과 홈페이지 글을 받는다.
그 장점 **하나에 대한** 사실만 최대 6개 뽑는다 — 크기·위치·구성·운영 시간·이용 대상·포함 여부·무엇을 할 수 있는지.
규칙: 글에 쓰인 내용만(추측·일반 상식 금지), 한 줄 8~40자, 가격·할인·프로모션 금지, 다른 시설 이야기 금지. 없으면 빈 목록.
JSON 만: {"facts":["..."]}"""


WEAK_RX = re.compile(r"(다|는|된|되어|되어있|하게|하고|있|이다|보이|놓인|놓여|깔린|깔려|있어|에서|으로|처럼|같은|함께)$")
WEAK = {"모습", "넓은", "작은", "큰", "모든", "다양", "가득", "위에", "아래", "옆에", "앞에", "뒤로", "주변", "사이", "배경", "전경", "내부", "외부", "한쪽", "가운데", "사진",
        "보이는", "있는", "설치", "배치", "이용", "곳", "부분", "느낌", "분위기", "감성", "깔끔", "조명", "햇살"}


def adv_tokens(sig: dict, extra: list[str] = ()) -> set[str]:
    """장점 낱말 — 장점 이름·설명·근거 사실 + 장점 사진 설명의 명사(동사·형용사·흔한 말 제외 — '있는'·'설치' 같은 말로 검사가 저절로 통과하지 않게)."""
    out = sg._tokens(sig.get("name")) | sg._tokens(sig.get("what")) | sg._tokens(sg._body(sig.get("fact")))
    for t in extra:
        out |= {w for w in sg._tokens(t) if not WEAK_RX.search(w)}
    return {t for t in out if len(t) >= 2 and t not in WEAK}


def deep_facts(models: dict, h: dict, sig: dict, report: dict) -> list[str]:
    pages = h.get("site_text") or {}
    if not pages:
        report["deep_facts"] = {"facts": [], "note": "공식 홈페이지 글 없음"}
        return []
    toks = adv_tokens(sig)
    hits = sorted(pages.items(), key=lambda kv: -sg._overlap(toks, sg._tokens(kv[1] or "")))
    body, total = [], 0
    for page, text in hits:
        t = str(text or "").strip()
        if not t or (body and not sg._overlap(toks, sg._tokens(t))):
            continue
        chunk = f"[페이지 {page}]\n{t[:2500]}\n"
        if total + len(chunk) > 7000:
            break
        body.append(chunk)
        total += len(chunk)
    if not body:
        report["deep_facts"] = {"facts": [], "note": "장점 낱말이 나오는 페이지 없음"}
        return []
    try:
        js = sg._ask(models, DEEP_SYSTEM, f"장점: {sig['name']} — {sig.get('what') or ''}\n\n" + "\n".join(body), 0.2)
    except RuntimeError as e:
        report["deep_facts"] = {"facts": [], "note": f"호출 실패: {str(e)[:60]}"}
        return []
    text_all = " ".join(str(v or "") for v in pages.values())
    out = []
    for f in js.get("facts") or []:
        f = design.one_line(str(f))[:40]
        if not f or PRICE_RX.search(f) or f in out:
            continue
        ft = sg._tokens(f)
        if not ft or sg._overlap(ft, sg._tokens(text_all)) < max(1, len(ft) // 2):     # 글에 낱말 절반 이상이 실제로 있어야(지어낸 문장 거름)
            continue
        out.append(f)
    out = out[:6]
    report["deep_facts"] = {"facts": out}
    log(f"장점 상세 사실 {len(out)}개: " + " / ".join(out[:4]))
    return [f"공식 홈페이지 상세: {f}" for f in out]


# ── 2. 컷 재료(넓게 · 디테일 · 연결) ───────────────────────────────────────────────────
DETAIL_SYSTEM = """너는 쇼츠 편집자다. 숙소 사진 1장과 이 숙소의 장점 이름을 받는다.
이 사진에서 그 장점을 **다른 각도로 다시 보여 줄 디테일 1~2곳**을 고른다(넓은 전체 컷은 따로 쓴다).
- 사진에 실제로 또렷이 보이는 사물·부분만(추측 금지). 시설 이름은 증거가 보일 때만, 아니면 일반어(예: '원형 온수탕').
- box = [x0, y0, x1, y1] (사진 폭·높이 대비 0~1). 너무 작으면 확대했을 때 흐려지므로 가로·세로 모두 0.25 이상.
- 서로 다른 곳(겹침 절반 이하), 사람 얼굴이 크게 걸리는 곳 금지.
JSON 만: {"details":[{"what":"보이는 것 짧게","box":[0.1,0.3,0.6,0.8]}]}"""


def crop_shot(src: str, dst: Path, cx: float, cy: float, frac: float = 1.0) -> Path:
    """사진에서 9:16 창을 잘라 1080x1920 으로. frac = 창 높이 / 가장 큰 9:16 창 높이(1.0 = 넓게, 0.67 = 1.5배 확대). 원본 픽셀만 쓴다."""
    with Image.open(src) as im0:
        im = im0.convert("RGB")
    W, H = im.size
    mw, mh = (H * 9 / 16, H) if W / H > 9 / 16 else (W, W * 16 / 9)
    frac = max(1 / ZOOM_MAX, min(1.0, frac))
    w, h = mw * frac, mh * frac
    x0 = min(max(cx * W - w / 2, 0), W - w)
    y0 = min(max(cy * H - h / 2, 0), H - h)
    im.crop((round(x0), round(y0), round(x0 + w), round(y0 + h))).resize((ms.W, ms.H), Image.LANCZOS).save(dst, "PNG")
    return dst


def _box(b) -> tuple[float, float, float, float] | None:
    try:
        x0, y0, x1, y1 = (float(v) for v in b)
    except (TypeError, ValueError):
        return None
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1) or (x1 - x0) < 0.2 or (y1 - y0) < 0.2:
        return None
    return x0, y0, x1, y1


def details(models: dict, sig: dict, p: dict) -> list[dict]:
    """장점 사진 1장에서 디테일 상자 1~2개(비전 · 약 1원). 실패하면 빈 목록(넓은 컷만 쓴다)."""
    try:
        r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, DETAIL_SYSTEM, f"장점: {sig['name']} — {sig.get('what') or ''}", [Path(p["path"])]))
    except Exception as e:  # noqa: BLE001
        log(f"디테일 고르기 실패(사진 {p['k']}): {str(e)[:80]}")
        return []
    out = []
    for d in r.get("details") or []:
        b = _box(d.get("box")) if isinstance(d, dict) else None
        what = design.one_line(str((d or {}).get("what") or ""))[:30] if isinstance(d, dict) else ""
        if not b or not what:
            continue
        if any(_iou(b, o["box"]) > 0.5 for o in out):
            continue
        out.append({"what": what, "box": b})
    return out[:2]


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def adv_ok(sig: dict) -> set[int]:
    """장점 사진으로 인정하는 원본 번호 — 주인공 확인을 통과한 사진(confirmed · 검사 ok/subject)만. 검사가 없으면(코드 대체 장점) 장점 사진 목록."""
    ok = {int(k) for k in sig.get("confirmed") or []}
    ok |= {int(c["k"]) for c in sig.get("checks") or [] if c.get("ok") or c.get("subject")}
    return ok or {int(k) for k in sig.get("photos") or []}


def build_shots(models: dict, sig: dict, h: dict, report: dict) -> list[dict]:
    """컷 재료 목록. 장점 사진(주인공 확인 → 시그니처 낱말 사진) 최대 4장 × (넓게 + 디테일 1~2) + 연결용 다른 사진 최대 5장(넓게만)."""
    by_k = {int(p["k"]): p for p in h.get("classified") or []}
    pool = {int(p["k"]): p for p in sg.usable_photos(h)} or {k: by_k[k] for k in sig.get("photos") or [] if k in by_k}
    toks = adv_tokens(sig)
    checked = [c for c in sig.get("checks") or [] if int(c["k"]) in by_k]
    adv = [int(k) for k in sig.get("confirmed") or [] if int(k) in by_k]
    # stay-run-53 실측(2026-10-16): 주인공 확인에서 '아님'(subject false)이 나온 키즈룸 사진이 '침대' 낱말 하나 겹친다고 장점 사진이 됐다
    # → '도그 파크' 문장 밑에 키즈룸이 깔림. 확인을 통과한 사진만 낱말 겹침으로 더한다
    good = adv_ok(sig)
    adv += [int(c["k"]) for c in checked if int(c["k"]) not in adv and int(c["k"]) in good and sg._overlap(toks, sg._tokens(by_k[int(c["k"])].get("description")))]
    adv += [int(k) for k in sig.get("photos") or [] if int(k) in by_k and int(k) not in adv]
    adv = adv[:ADV_PHOTOS]
    others = sorted((k for k in pool if k not in adv and not (mt.is_exterior(pool[k]) and k not in adv)),
                    key=lambda k: (-sg._overlap(toks, sg._tokens(pool[k].get("description"))), -int(pool[k].get("quality") or 0), k))[:LINK_PHOTOS]
    STORY.mkdir(parents=True, exist_ok=True)
    shots, n = [], 0
    for k in adv:
        p = by_k[k]
        n += 1
        sid = f"S{n}"
        crop_shot(p["path"], STORY / f"shot_{sid}.png", float(p.get("focus_x", 0.5)), float(p.get("focus_y", 0.5)))
        shots.append({"id": sid, "k": k, "kind": "장점·넓게", "desc": p.get("description") or "", "img": f"shot_{sid}.png", "adv": True,
                      "category": p.get("category"), "veo_prompt": p.get("veo_prompt") or "", "source": p.get("source")})
        with Image.open(p["path"]) as im:
            W, H = im.size
        mw, mh = (H * 9 / 16, H) if W / H > 9 / 16 else (W, W * 16 / 9)
        for d in details(models, sig, p):
            x0, y0, x1, y1 = d["box"]
            frac = max((y1 - y0) * H * 1.25 / mh, (x1 - x0) * W * 1.25 / mw)
            if frac >= 0.9:                                                # stay-run-53: 확대 1.0배 '디테일'이 넓은 컷과 같은 화면 → 같은 그림이 두 문장 연속. 1.1배 미만은 안 만든다
                continue
            n += 1
            sid = f"S{n}"
            crop_shot(p["path"], STORY / f"shot_{sid}.png", (x0 + x1) / 2, (y0 + y1) / 2, frac)
            shots.append({"id": sid, "k": k, "kind": "장점·디테일", "desc": f"{d['what']} (사진 {k} 확대: {p.get('description') or ''})"[:120],
                          "img": f"shot_{sid}.png", "adv": True, "category": p.get("category"), "veo_prompt": p.get("veo_prompt") or "", "source": p.get("source"),
                          "zoom": round(1 / max(1 / ZOOM_MAX, min(1.0, frac)), 2)})
    for k in others:
        p = by_k[k]
        n += 1
        sid = f"S{n}"
        crop_shot(p["path"], STORY / f"shot_{sid}.png", float(p.get("focus_x", 0.5)), float(p.get("focus_y", 0.5)))
        shots.append({"id": sid, "k": k, "kind": "연결", "desc": p.get("description") or "", "img": f"shot_{sid}.png", "adv": False,
                      "category": p.get("category"), "veo_prompt": p.get("veo_prompt") or "", "source": p.get("source")})
    report["story_shots"] = [{k: s.get(k) for k in ("id", "k", "kind", "desc", "zoom")} for s in shots]
    log(f"컷 재료 {len(shots)}개 — 장점 사진 {adv} · 연결 사진 {others}")
    return shots


# ── 3. 대본(관점별 한 문장) ─────────────────────────────────────────────────────────────
STORY_SYSTEM = """너는 숙소 쇼츠 작가다. 이 숙소의 **장점 하나**를 정해 두고, 나레이션 한 줄 한 줄이 그 장점을 **다른 관점으로 다시 부각**하는 20초 이야기를 쓴다.
(벤치마크: "여행 날 비 오면 다 망친 것 같잖아요. 근데 여긴 비가 와야 오히려 좋은 숙소예요. 방문만 열면 나만 쓰는 노천탕이 있어서 빗소리 들으며 산만 보면 돼요…"
 — 모든 문장이 노천탕이거나 노천탕에서 이어지는 행동, 마지막 문장이 첫 걱정을 푼다.)
관점(lens):
- 훅: 첫 문장. 시청자의 걱정·상식(계절·날씨·상황)과 부딪히는 질문. 장점 이름은 아직 말하지 않아도 된다. 6~18자.
- 정체: 둘째 문장. 장점이 무엇인지 분명히(장점 이름 낱말 필수) — 훅의 걱정을 뒤집는다.
- 디테일: 가까이서 보이는 것(사진 디테일 컷과 맞게).
- 상황: 언제·어떤 날 가장 좋은지(사실·시기에 근거).
- 사람: 누구의 어떤 고민을 푸는지(아이와·둘이서 등 — 사실에 없는 서비스 지어내기 금지).
- 행동: 거기서 무엇을 하면 되는지(2인칭 · '~하면 돼요').
- 연결: 다른 공간을 보여 줘도 문장은 그 장점으로 돌아와야 한다(예: '추우면 문 열고 방으로 들어오면 그만이에요' → 장점이 객실에 붙어 있다는 점).
- 희소성: 같은 테마 다른 숙소들이 내세우는 것과 비교한 차이(아래 '다른 후보' 목록에 근거 · 다른 숙소 이름은 말하지 않는다).
- 약속: 마지막 문장. 첫 걱정을 푸는 한 줄(장점 낱말 포함). 저장 권유는 캡션에서 하고 여기선 짧게.
규칙:
1) beats 6~9개: 첫째 훅, 둘째 정체, 마지막 약속, 가운데는 디테일·상황·사람·행동·연결·희소성 중 **서로 다른 3개 이상**.
2) 훅 말고 **모든 문장에 장점 낱말**(장점 이름·설명·장점 사진에 보이는 사물)이 들어간다. 장점과 상관없는 시설 이야기 금지.
3) 각 문장은 근거가 있어야 한다: fact = 아래 사실 번호, 사진에 보이는 것만 말하면 0. 사실·사진에 없는 내용·숫자 금지.
4) 말투: 2인칭 현재형 '~해요' 체. 금지: 1인칭·체험·과거형('다녀왔', '좋았', '-더라고요', '저는', '우리'), '~니다', 숙소 이름, 가격 숫자,
   '최고·유일·최저가·무조건', 분위기만 있는 말(노을빛·물들고·힐링·낭만·감성·설렘·아늑·포근·그림 같은·인생샷·완벽한·행복·추억).
5) 문장 길이: 공백 빼고 6~30자, 전체 합 80~150자(약 12~23초). 문장은 서로 이어지게(앞 문장을 받는 연결어 환영).
6) shots: 그 문장 동안 나올 컷 id(아래 목록). 훅·정체·약속은 1개, 나머지는 1~3개. **약속은 훅과 같은 사진**(같은 id 또는 같은 사진의 다른 컷).
   '연결' 컷은 연결·상황·사람·행동 관점에서만. 같은 원본 사진은 너무 자주 쓰지 않는다(목록의 '사진 번호' 기준).
7) hook_title: 첫 화면 위쪽 큰 제목 — 장점의 신박함을 묻는 질문(장점 낱말 · 핵심 낱말 하나만 [대괄호] · 공백 빼고 6~14자 · 물음표 끝 · 숙소·지역 이름 금지 · 나레이션을 그대로 옮기지 않는다).
8) caption: hook(첫 줄 — 장점이 무엇이고 왜 의외인지, 사실 그대로) · points(장점의 다른 관점 1~3줄, 사실 그대로) · save(저장 권유 한 줄, 시기와 연결).
   checklist: 사실 번호와 짧은 체크 항목 2~4개. title: 유튜브 제목 12~28자(숙소 이름 포함). hashtags 5개.
9) person: 사람 컷 **하나** — 행동·사람·상황 관점 문장 중 하나(장점 사진 컷)에, 사진 안에 **이미 있는 사물**을 손이 만지거나(kind "hand", 기본)
   뒷모습 한 사람이 그 자리를 쓰는(kind "back" — 바닥이 넓게 보이는 사진만) 장면. 얼굴·여러 사람·새 물건(컵·휴대폰 등)·뛰기·물에 뛰어들기 금지.
   action_en = 영어 동작 한 구절(사진에 있는 사물 이름으로, 예 "gently pushes the hammock so it sways"). 그 문장 내용과 맞게.
JSON 만: {"beats":[{"lens":"훅","line":"...","shots":["S1"],"fact":0}],"hook_title":"...","person":{"beat":6,"kind":"hand","action_en":"..."},
 "caption":{"hook":"...","points":["..."],"save":"..."},"checklist":[{"fact":1,"text":"..."}],"title":"...","hashtags":["#..."]}"""


def _nospace(t: str) -> int:
    return len(re.sub(r"\s", "", str(t or "")))


def story_errs(js: dict, sig: dict, h: dict, req: dict, facts: list[str], shots: list[dict], peers: list[str], toks: set[str]) -> list[str]:
    """관점 검사. 오류 문구는 '문장 N ' 으로 시작하면 그 문장 탓(대체·삭제 대상), 아니면 전체 구조 탓."""
    errs = []
    beats = [b for b in (js.get("beats") or []) if isinstance(b, dict)]
    if not (BEATS[0] <= len(beats) <= BEATS[1]):
        return [f"beats {len(beats)}개 — {BEATS[0]}~{BEATS[1]}개"]
    by_id = {s["id"]: s for s in shots}
    lenses = [str(b.get("lens") or "").strip() for b in beats]
    if lenses[0] != "훅" or lenses[1] != "정체" or lenses[-1] != "약속":
        errs.append(f"관점 순서 {lenses} — 첫째 훅 · 둘째 정체 · 마지막 약속")
    mids = [x for x in lenses[2:-1]]
    bad_mid = [x for x in mids if x not in MID_LENSES]
    if bad_mid:
        errs.append(f"가운데 관점 {bad_mid} — {'/'.join(MID_LENSES)} 중에서")
    if len(set(mids) - set(bad_mid)) < MIN_VIEWS:
        errs.append(f"가운데 관점 종류 {len(set(mids))}개 — 서로 다른 관점 {MIN_VIEWS}개 이상(같은 말 반복 금지)")
    if "희소성" in mids and not peers:
        errs.append("다른 후보 목록이 없어 희소성 관점은 근거가 없다 — 다른 관점으로")
    if _nospace(beats[0].get("line")) > 18:
        errs.append(f"문장 1 훅 {_nospace(beats[0].get('line'))}자 — 18자 안(약 3초)")
    if _nospace(beats[0].get("line")) + _nospace(beats[1].get("line")) > 40:
        errs.append("문장 2 정체가 6초 안에 안 나옴 — 훅·정체 합 40자 안")
    total = sum(_nospace(b.get("line")) for b in beats)
    if not (TOTAL_LEN[0] <= total <= TOTAL_LEN[1]):
        errs.append(f"전체 나레이션 {total}자 — {TOTAL_LEN[0]}~{TOTAL_LEN[1]}자")
    name_toks = so.name_tokens(h["name"], req, h)
    peer_names = [str(x).split(":")[0].strip() for x in peers]
    corpus = " ".join(facts)
    photo_count: dict[int, int] = {}
    n_photo = len({s["k"] for s in shots}) or 1
    n_used = sum(len(b.get("shots") or []) for b in beats)
    limit = max(3, -(-n_used // n_photo))                                               # 사진이 적으면 상한을 조금 올린다(올림 나눗셈)
    for i, b in enumerate(beats, 1):
        lens, line = lenses[i - 1], design.one_line(str(b.get("line") or ""))
        L = _nospace(line)
        if not (LINE_LEN[0] <= L <= LINE_LEN[1]):
            errs.append(f"문장 {i} '{line}' {L}자 — {LINE_LEN[0]}~{LINE_LEN[1]}자")
        elif not design.fits_chunks(line)[0]:
            errs.append(f"문장 {i} '{line}' 이 자막 조각 한 줄에 안 들어감 — 긴 낱말을 줄인다")
        ids = [str(x) for x in (b.get("shots") or [])]
        if not ids or any(x not in by_id for x in ids):
            errs.append(f"문장 {i} shots {ids} — 목록의 컷 id 로")
            continue
        if lens in ("훅", "정체", "약속") and len(ids) != 1:
            errs.append(f"문장 {i} {lens} 컷은 1개")
        if len(ids) > 3:
            errs.append(f"문장 {i} 컷 {len(ids)}개 — 3개까지")
        if lens in ("훅", "정체", "디테일", "약속") and any(not by_id[x]["adv"] for x in ids):
            errs.append(f"문장 {i} {lens} 관점에 연결 사진 — 장점 사진으로")
        for x in ids:
            photo_count[by_id[x]["k"]] = photo_count.get(by_id[x]["k"], 0) + 1
        desc = " ".join(by_id[x]["desc"] for x in ids)
        fi = sg._int(b.get("fact"))
        fact = facts[fi - 1] if fi and 1 <= fi <= len(facts) else ""
        lt = sg._tokens(line)
        if lens != "훅" and not sg._overlap(lt, toks):
            errs.append(f"문장 {i} '{line}' 에 장점 낱말이 없음 — 모든 문장이 장점({sig['name']})을 다른 관점으로 말한다")
        if lens not in ("훅", "약속") and not sg._overlap(lt, sg._tokens(sg._body(fact)) | sg._tokens(desc)):
            errs.append(f"문장 {i} '{line}' 근거가 없음 — 사실 {fi or '0'}·그 컷 사진 설명의 낱말로")
        mood = sg.MOOD_RX.search(line)
        if mood:
            errs.append(f"문장 {i} 분위기 말 '{mood.group(0)}'")
        if sg.PAST_RX.search(line) or sg.FIRST_RX.search(line):
            errs.append(f"문장 {i} 1인칭·체험·과거형 금지")
        if so.ENDING_RX.search(line):
            errs.append(f"문장 {i} '~니다' — '~해요'체로")
        if any(t in line for t in name_toks):
            errs.append(f"문장 {i} 숙소 이름 금지")
        if any(pn and pn in line for pn in peer_names):
            errs.append(f"문장 {i} 다른 숙소 이름 금지")
        if PRICE_RX.search(line):
            errs.append(f"문장 {i} 가격 숫자 금지")
        for d in sg.DIGIT_RX.findall(line):
            if d not in corpus and d != str(sg.month_num(req)):                            # 제작 시기의 달('11월 캠핑')은 허용
                errs.append(f"문장 {i} 숫자 '{d}' 는 사실 목록에 없음")
                break
        for w in list(ms.BANNED) + list(mt.WORDING_BAN):
            if w in line:
                errs.append(f"문장 {i} 금지 표현 '{w}'")
                break
        if so.cold_month(req) and so.SUMMER_TALK_RX.search(line):
            errs.append(f"문장 {i} 겨울 편에 여름 해변 시설")
        allow = f"{desc} {fact} {sig['fact']} {' '.join(facts)}"
        bad = [t for t in photos.facility_terms(line) if not photos.term_ok(t, allow)]
        if bad:
            errs.append(f"문장 {i} 시설 이름 '{'/'.join(bad)}' 는 사진·사실에서 확인 안 됨")
        if sg.ADJ_RX.search(sg._body(sig["fact"])) and lens == "정체" and not sg.ADJ_RX.search(line):
            errs.append(f"문장 {i} 장점이 숙소 밖 시설 — '바로 옆' 같은 위치를 말한다")
    over = {k: c for k, c in photo_count.items() if c > limit}
    if over:
        errs.append(f"같은 원본 사진을 너무 자주 씀 {over} — 사진당 {limit}컷까지")
    return errs


def _line_idx(e: str) -> int | None:
    m = re.match(r"문장 (\d+) ", e)
    return int(m.group(1)) if m else None


def recheck_shots(text: dict, shots: list[dict], sig: dict, report: dict) -> None:
    """재사용 계획 다시 검사(돈 0) — 위 build_shots 고치기 전에 만든 미리보기도 바로잡는다.
    주인공 확인을 못 통과한 사진의 '장점' 컷은 연결 컷으로 낮추고, 연결이 아닌 문장에 걸렸으면 확인된 장점 컷(덜 쓴 사진·옆 문장과 다른 컷)으로 바꾼다."""
    good = adv_ok(sig)
    bad = {s["id"] for s in shots if s.get("adv") and int(s["k"]) not in good}
    if not good or not bad:
        return
    for s in shots:
        if s["id"] in bad:
            s["adv"], s["kind"] = False, "연결"
    by_id = {s["id"]: s for s in shots}
    pool = [s["id"] for s in shots if s.get("adv")]
    beats = text.get("beats") or []
    use: dict[str, int] = {}
    for b in beats:
        for x in b.get("shots") or []:
            use[x] = use.get(x, 0) + 1
    changed = []
    for i, b in enumerate(beats):
        ids = list(b.get("shots") or [])
        if str(b.get("lens") or "") == "연결" or not any(x in bad for x in ids) or not pool:
            continue
        # 옆 문장과 같은 원본 사진은 피한다(stay-run-53: 디테일·행동·희소성 세 문장이 같은 사진이 될 뻔함) → 덜 쓴 컷
        near = [x for j in (i - 1, i + 1) if 0 <= j < len(beats) for x in beats[j].get("shots") or [] if x in by_id]
        near_k = {by_id[x]["k"] for x in near}
        new = []
        for x in ids:
            if x in bad:
                y = sorted((y for y in pool if y not in new and y not in ids),
                           key=lambda y: (by_id[y]["k"] in near_k, use.get(y, 0), pool.index(y)))[:1] or [pool[0]]
                y = y[0]
                use[y] = use.get(y, 0) + 1
                changed.append({"beat": i + 1, "from": x, "to": y})
                x = y
            new.append(x)
        b["shots"] = new
    report["shot_recheck"] = {"not_signature": sorted(bad), "changed": changed}
    log(f"컷 다시 검사: 주인공 확인 안 된 장점 컷 {sorted(bad)} → 연결로 낮춤 · 바꾼 문장 {changed}")


def fix_shots(js: dict, shots: list[dict]) -> None:
    """코드로 고칠 수 있는 것은 고친다(돈 0): ① 같은 컷을 두 번 쓰면 같은 사진의 안 쓴 컷(없으면 안 쓴 장점 컷)으로 바꾼다
    ② 약속 컷 = 훅 컷과 같은 사진(첫 장면으로 돌아오기 — 이것만 같은 컷 허용)."""
    beats = js.get("beats") or []
    if len(beats) < 2:
        return
    by_id = {s["id"]: s for s in shots}
    used = set()
    for b in beats[:-1]:
        ids = []
        for x in [x for x in b.get("shots") or [] if x in by_id]:
            if x in used:
                alt = [s["id"] for s in shots if s["k"] == by_id[x]["k"] and s["id"] not in used and s["id"] not in ids] \
                    or [s["id"] for s in shots if s["adv"] == by_id[x]["adv"] and s["id"] not in used and s["id"] not in ids]
                if alt:
                    x = alt[0]
            ids.append(x)
            used.add(x)
        if ids:
            b["shots"] = ids
    h_ids = [x for x in beats[0].get("shots") or [] if x in by_id]
    last = beats[-1]
    if not h_ids:
        return
    k0 = by_id[h_ids[0]]["k"]
    l_ids = [x for x in last.get("shots") or [] if x in by_id]
    if l_ids and by_id[l_ids[0]]["k"] == k0:
        return
    same = [s["id"] for s in shots if s["k"] == k0 and s["id"] != h_ids[0]]
    last["shots"] = [same[0] if same else h_ids[0]]


def repair(js: dict, errs: list[str], sig: dict, facts: list[str], report: dict) -> dict:
    """3번 다 관점 검사에 걸렸을 때 — 걸린 문장만 사실 문장으로 바꾸거나(훅·정체·약속) 뺀다(가운데, 6문장 아래로는 안 뺌). 멈추지 않는다."""
    beats = [dict(b) for b in js.get("beats") or [] if isinstance(b, dict)]
    bad = {_line_idx(e) for e in errs if _line_idx(e)}
    sig_line = sg._cut(sg._body(sig["fact"]), 28)
    toks = adv_tokens(sig)
    spare = [sg._cut(sg._body(f), 28) for f in sorted(facts, key=lambda f: ("상세" not in f, -sg._overlap(sg._tokens(f), toks))) if sg._overlap(sg._tokens(f), toks)]
    used = {str(b.get("line") or "") for i, b in enumerate(beats, 1) if i not in bad}

    def fresh(*cands) -> str | None:                                                    # 같은 문장이 두 번 나오지 않게
        for c in cands:
            if c and c not in used:
                used.add(c)
                return c
        return None
    keep = []
    for i, b in enumerate(beats, 1):
        if i not in bad:
            keep.append(b); continue
        lens = str(b.get("lens") or "")
        if lens == "훅":
            b["line"] = f"{sg._cut(sig['name'], 16)}, 들어보셨어요?"
        elif lens == "정체":
            b["line"] = fresh(sig_line, *spare) or sig_line
        elif lens == "약속":
            b["line"] = f"{sg._cut(sig['name'], 16)}, 기억해 두세요."
        elif len(keep) + (len(beats) - i) >= BEATS[0]:
            continue                                                                    # 이 문장을 빼도 6문장 이상 남으면 뺀다
        else:
            fi = sg._int(b.get("fact"))
            line = fresh(*([sg._cut(sg._body(facts[fi - 1]), 28)] if fi and 1 <= fi <= len(facts) else []), *spare)
            if not line:
                continue                                                                # 쓸 문장이 없으면 뺀다(6문장 아래로 내려갈 수 있다 — 기록에 남음)
            b["line"] = line
        keep.append(b)
    report["story_fallback"] = [str(e)[:120] for e in errs[:8]]
    log(f"관점 검사 3번 실패 → 걸린 문장만 고치거나 빼고 계속: {errs[:3]}")
    return {**js, "beats": keep}


def write_story(models: dict, sig: dict, h: dict, req: dict, facts: list[str], shots: list[dict], peers: list[str], toks: set[str], report: dict) -> dict:
    ttype = so.next_title_type()
    content = (f"장점: {sig['name']} — {sig.get('what') or ''}\n근거 사실: {sg._body(sig['fact'])}\n왜 의외: {sig.get('why') or '-'}\n"
               f"다른 후보와 다른 점: {sig.get('vs_peers') or '-'}\n시기: {req.get('month')} · 테마: {req.get('theme')} · 지역: {req.get('region')}\n"
               f"훅 제목 유형: {ttype} — {so.TITLE_TYPES[ttype]}\n최근 제목(다시 쓰지 말 것): {' / '.join(so.recent_titles()) or '없음'}\n"
               f"숙소 이름(제목·캡션용, 나레이션·훅 제목에는 금지): {h['name']}\n\n"
               "장점 낱말(훅 말고 모든 문장에 하나 이상): " + ", ".join(sorted(toks)[:30]) + "\n\n"
               "같은 테마 다른 후보(희소성 관점 근거 · 이름은 말하지 않는다):\n" + ("\n".join(f"- {x}" for x in peers) or "- (없음)")
               + "\n\n사실(번호):\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1))
               + "\n\n컷 목록(id · 종류 · 사진 번호 · 보이는 것):\n" + "\n".join(f"{s['id']} · {s['kind']} · 사진 {s['k']} · {s['desc']}" for s in shots))
    fb, best, tries = "", None, []
    for attempt in range(3):
        try:
            js = sg._ask(models, STORY_SYSTEM, content + fb, 0.6)
        except RuntimeError as e:
            tries.append({"errs": [f"호출 실패: {str(e)[:80]}"]})
            continue
        fix_shots(js, shots)
        errs = story_errs(js, sig, h, req, facts, shots, peers, toks)
        cerrs = sg.caption_errs(js.get("caption") if isinstance(js.get("caption"), dict) else {}, h, req, sig, facts)
        tries.append({"errs": (errs + cerrs)[:10], "beats": len(js.get("beats") or [])})
        if best is None or len(errs) < len(best[1]):
            best = (js, errs)
        if not errs and not cerrs:
            break
        errs = errs + cerrs
        log(f"관점 검사 실패({attempt + 1}): {errs[:4]}")
        fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs[:12])
    report["story_tries"] = tries
    report["text_title_type"] = ttype
    if best is None:                                                                   # 글 호출이 세 번 모두 실패 — 장점 사실로 최소 이야기
        adv = [s for s in shots if s["adv"]] or shots
        js = {"beats": [{"lens": "훅", "line": f"{sg._cut(sig['name'], 16)}, 들어보셨어요?", "shots": [adv[0]["id"]], "fact": 0},
                        {"lens": "정체", "line": sg._cut(sg._body(sig['fact']), 28), "shots": [adv[min(1, len(adv) - 1)]["id"]], "fact": sig.get("fact_i") or 0}]
              + [{"lens": "디테일", "line": sg._cut(s["desc"], 28), "shots": [s["id"]], "fact": 0} for s in adv[2:6]]
              + [{"lens": "약속", "line": f"{sg._cut(sig['name'], 16)}, 기억해 두세요.", "shots": [adv[0]["id"]], "fact": 0}], "caption": {}}
        best = (js, ["글 호출 실패"])
    js, errs = best
    mark_person(js, shots)
    report["lens_check"] = {"ok": not errs, "errs": [str(e)[:120] for e in errs[:10]]}
    if errs:
        js = repair(js, errs, sig, facts, report)
        fix_shots(js, shots)
        left = story_errs(js, sig, h, req, facts, shots, peers, toks)
        report["lens_check"]["after_fix"] = [str(e)[:120] for e in left[:8]]
    beats = []
    for b in js.get("beats") or []:
        ids = [x for x in b.get("shots") or [] if any(s["id"] == x for s in shots)][:3] or [shots[0]["id"]]
        fi = sg._int(b.get("fact")) or 0
        beats.append({"lens": str(b.get("lens") or "정보"), "line": design.one_line(str(b.get("line") or "")), "shots": ids,
                      "fact_i": fi if 1 <= fi <= len(facts) else 0, "fact": facts[fi - 1] if 1 <= fi <= len(facts) else "",
                      **({"person": b["person"]} if isinstance(b.get("person"), dict) else {})})
    ensure_person(beats, shots, report)
    shots_desc = [{"description": next(s["desc"] for s in shots if s["id"] == beats[0]["shots"][0])}]
    title = sg.ensure_sig_title(models, design.one_line(str(js.get("hook_title") or "")), [b["line"] for b in beats], shots_desc, sig, h, req, ttype, report)
    cap = js.get("caption") if isinstance(js.get("caption"), dict) else {}
    if sg.caption_errs(cap, h, req, sig, facts):
        pts = [b["line"] for b in beats[2:5] if b["fact_i"]] or [sg._cut(sg._body(sig["fact"]), 40)]
        cap = {"hook": sg._cut(sg._body(sig["fact"]), 80), "points": pts, "save": "갈 계획이 있다면 저장해두고 다시 꺼내 보세요."}
    name_title = str(js.get("title") or sig["name"])
    if h["name"] not in name_title:
        name_title = f"{h['name']} {name_title}".strip()
    text = {"beats": beats, "hook_title": title, "hook_title_type": ttype,
            "caption": {"hook": design.one_line(str(cap.get("hook") or "")), "points": [design.one_line(str(x)) for x in cap.get("points") or [] if str(x).strip()][:3],
                        "save": design.one_line(str(cap.get("save") or ""))},
            "checklist": sg.grounded_checklist(js.get("checklist") or [{"fact": b["fact_i"]} for b in beats if b["fact_i"]], facts, h),
            "title": name_title[:40], "hashtags": ([t if str(t).startswith("#") else f"#{t}" for t in (js.get("hashtags") or []) if str(t).strip()] or sg.default_tags(req))[:5]}
    log("대본: " + " / ".join(f"[{b['lens']}] {b['line']}" for b in beats) + f" · 훅 제목 {title or '(없음)'}")
    return text


# ── 4. 렌더 ─────────────────────────────────────────────────────────────────────────────
def beat_clip(beat: dict, shots: dict, L: float, out: Path, j: int) -> tuple[Path, str]:
    """문장 하나의 화면 — 컷이 여러 개면 길이를 나눠 사진 무빙을 이어 붙인다(원본 픽셀만)."""
    ids = beat["shots"]
    parts, n = [], len(ids)
    each = max(SHOT_MIN, L / n)
    for m, sid in enumerate(ids):
        sec = each if m < n - 1 else max(SHOT_MIN, L - each * (n - 1))
        pat = PATTERNS[(j + m) % len(PATTERNS)]
        parts.append(sg.photo_clip(STORY / shots[sid]["img"], sec, STORY / f"pan_{j}_{m}.mp4", pat, MOTION))
    if len(parts) == 1:
        return parts[0], f"사진 무빙·{PATTERNS[j % len(PATTERNS)]}"
    lst = STORY / f"beat_{j}.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out, f"사진 무빙 {n}컷"


def person_check(models: dict, first: Path, clip: Path, j: int) -> dict:
    frames = []
    for k, t in enumerate((0.1, 2.0, 3.8)):
        f = STORY / f"pchk_{j}_{k}.jpg"
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", "-vf", "scale=540:-2", str(f)])
        if f.exists():
            frames.append(f)
    if len(frames) < 2:
        return {"ok": False, "reason": "프레임을 못 뽑음"}
    try:
        r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, PERSON_CHECK_SYSTEM, "요청: 손 또는 뒷모습 하나", frames))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"검수 호출 실패: {str(e)[:60]}"}
    probs = []
    if str(r.get("person") or "") not in ("hand", "back"):
        probs.append(f"사람 부분 '{r.get('person')}'")
    if r.get("face_visible"):
        probs.append("얼굴이 보임")
    if r.get("extra_people"):
        probs.append("여러 사람")
    if r.get("new_objects"):
        probs.append("새 사물: " + ", ".join(map(str, r["new_objects"]))[:60])
    if r.get("structure_changed"):
        probs.append("구조 변경")
    if r.get("weird"):
        probs.append("손·크기가 이상함")
    if r.get("verdict") != "ok" and not probs:
        probs.append(str(r.get("reason") or "검수 탈락")[:60])
    return {"ok": not probs, "reason": "; ".join(probs)[:160], "raw": {k: r.get(k) for k in ("person", "face_visible", "extra_people", "new_objects", "structure_changed", "weird", "reason")}}


def mark_person(js: dict, shots: list[dict]) -> None:
    """모델이 고른 사람 컷을 그 문장에 붙여 둔다(빼기·고치기 뒤에도 따라가게). 규칙에 안 맞으면 붙이지 않는다(ensure_person 이 대신 고름)."""
    pr = js.get("person") if isinstance(js.get("person"), dict) else {}
    beats = js.get("beats") or []
    by_id = {s["id"]: s for s in shots}
    n = sg._int(pr.get("beat"))
    kind = str(pr.get("kind") or "hand").strip().lower()
    act = design.one_line(str(pr.get("action_en") or ""))
    if not (n and 2 <= n <= len(beats) - 1) or kind not in PERSON_PROMPT:
        return
    b = beats[n - 1]
    ids = [x for x in b.get("shots") or [] if x in by_id]
    if str(b.get("lens") or "") not in PERSON_LENSES or not ids or not by_id[ids[0]]["adv"]:
        return
    if not (8 <= len(act) <= 160) or not act.isascii() or PERSON_BAN_RX.search(act):
        return
    b["person"] = {"kind": kind, "action_en": act.rstrip(". ")}


def ensure_person(beats: list[dict], shots: list[dict], report: dict) -> None:
    """사람 컷은 영상당 하나. 모델이 안 골랐거나 규칙에 안 맞으면 코드가 행동 → 사람 → 상황 관점의 장점 사진 문장에 '손' 컷을 둔다."""
    by_id = {s["id"]: s for s in shots}
    marked = [j for j, b in enumerate(beats) if b.get("person")]
    for j in marked[1:]:
        beats[j].pop("person", None)
    if not marked:
        for lens in PERSON_LENSES:
            j = next((j for j, b in enumerate(beats[1:-1], 1) if b["lens"] == lens and by_id[b["shots"][0]]["adv"]), None)
            if j is not None:
                beats[j]["person"] = {"kind": "hand", "action_en": "reaches toward the main object in the scene and gently touches it", "auto": True}
                break
    j = next((j for j, b in enumerate(beats) if b.get("person")), None)
    report["person_cut"] = ({"i": j + 1, "lens": beats[j]["lens"], **beats[j]["person"]} if j is not None else None)


def veo_beats(beats: list[dict], shots: dict, report: dict, theme: str, models: dict | None = None) -> dict:
    """제작 때만: 훅·정체·약속 문장 + 사람 컷(손·뒷모습 1개)을 Veo 4초 AI 영상으로(9컷 형식과 같은 지시문). 실패한 컷은 사진 무빙. 재사용 클립(veo_b<j>.mp4)은 0원."""
    clips, rows, stopped = {}, [], None
    for j, b in enumerate(beats):
        if b["lens"] not in VEO_LENSES and not b.get("person"):
            continue
        s = shots[b["shots"][0]]
        out = STORY / f"veo_b{j}.mp4"
        row = {"i": j + 1, "lens": b["lens"], "shot": s["id"], "ok": False, "krw": 0, **({"person": b["person"]["kind"]} if b.get("person") else {})}
        if out.exists() and out.stat().st_size > 0:
            clips[j] = out; row.update({"ok": True, "reused": True}); rows.append(row); continue
        if stopped:
            row["error"] = f"한도: {stopped}"; rows.append(row); continue
        small = STORY / f"veo_in_{j}.png"
        Image.open(STORY / s["img"]).convert("RGB").resize((720, 1280), Image.LANCZOS).save(small, "PNG")
        cat = s.get("category") if s.get("category") in photos.CATS else "special"
        if b.get("person"):
            prompt = PERSON_PROMPT[b["person"]["kind"]].format(action=b["person"]["action_en"])
        else:
            prompt = photos.prompt_for({"veo_prompt": s.get("veo_prompt") or "", "category": cat})
        seed = veo.seed_for(theme, "story", s["k"], s["id"])
        before = veo.spent_this_run()
        for attempt in range(2):
            try:
                veo.make_clip(prompt, small, 4, out, seed + attempt)
                row["ok"] = True; clips[j] = out
                break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:120]}"
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"; stopped = str(e)
                break
            except veo.VeoError as e:
                row["error"] = str(e)[:160]
                break
        row["krw"] = round(veo.spent_this_run() - before)
        if row["ok"] and b.get("person"):                                              # 사람 컷은 영상 뒤 비전 검수(약 1원) — 얼굴·여러 사람·새 물건·구조 변경이면 버림
            chk = person_check(models, small, out, j)
            row["check"] = chk
            if not chk.get("ok"):
                row["ok"] = False
                row["error"] = f"사람 컷 검수 탈락: {chk.get('reason')}"
                clips.pop(j, None)
        if not row["ok"]:
            log(f"문장 {j + 1} AI 영상 실패 → 사진 무빙: {row.get('error')}")
        rows.append(row)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": rows, "stopped": stopped,
                     "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}
    return clips


def render(text: dict, shots: dict, narr: dict, req: dict, report: dict, folder: str, pos: int, preview: bool, models: dict | None = None) -> tuple[Path, float, list]:
    B = mt.BUILD
    style = str(req.get("caption_style") or design.DEFAULT_STYLE)
    frame = STORY / "ov_frame.png"
    design.frame_png(frame, ms.DISCLOSURE)
    beats = text["beats"]
    clips = {} if preview else veo_beats(beats, shots, report, str(req.get("theme") or ""), models)
    if preview:
        report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": [], "spent_krw": 0, "month_total_krw": round(veo.month_total())}
    segs, timeline = [], []
    for j, b in enumerate(beats):
        i = j + 1
        wav = B / f"narr_c{i}.wav"
        L = max(MIN_HOOK if j == 0 else 0.0, float(narr.get(i) or narr.get(str(i)) or 2.0) + 0.12, SHOT_MIN * len(b["shots"]))
        overlays = [{"path": frame, "a": 0, "b": 99, "anim": False}]
        if j == 0 and text.get("hook_title"):
            ttl = STORY / "ov_title.png"
            design.hook_title_png(ttl, text["hook_title"])
            overlays.append({"path": ttl, "a": 0.0, "b": 99, "anim": False})
        chunks = so.karaoke_times(b["line"], wav, L)
        for k, (txt, ta, tb) in enumerate(chunks):
            capk = STORY / f"ov_cap_{i:02d}_{k}.png"
            design.subtitle_png(capk, txt)
            overlays.append({"path": capk, "a": ta, "b": tb, "anim": True, "fade": 0.05, "slide": 8})
        slow = 1.0
        if j in clips:
            src, kind = clips[j], "AI 영상"
            avail = ms.probe_duration(src)
            slow = min(1.25, L / avail) if L > avail else 1.0
        else:
            src, kind = beat_clip(b, shots, L, STORY / f"beat_{j}.mp4", j)
        segs.append(so.cut_segment(100 + i, src, L, wav if wav.exists() else None, overlays, slow))
        timeline.append({"i": i, "lens": b["lens"], "kind": kind, "sec": round(L, 2), "shots": b["shots"], "narration": b["line"],
                         "title": text["hook_title"] if j == 0 else None, "chunks": [[t, a, c] for t, a, c in chunks]})
    hook_img = STORY / shots[beats[0]["shots"][0]]["img"]
    card = design.end_card(STORY / "end_card.jpg", hook_img, folder, pos, style, ms.DISCLOSURE)
    Lc = max(3.6, float(narr.get("cta") or 2.5) + 0.7)
    cta_wav = B / "narr_cta.wav"
    segs.append(so.cut_segment(199, card, Lc, cta_wav if cta_wav.exists() else None, [], image=True, fade_in=0.3))
    timeline.append({"i": "끝", "lens": "끝 카드", "kind": "카드", "sec": round(Lc, 2), "narration": so.cta_text(folder, pos)})
    (STORY / "concat.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in segs), encoding="utf-8")
    nob = STORY / "video_nobgm.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(STORY / "concat.txt"), "-c", "copy", "-movflags", "+faststart", str(nob)])
    total = ms.probe_duration(nob)
    video = ms.BUILD / "video.mp4"
    bgm_req = req.get("bgm", True)
    bgm_path = so.BGM if bgm_req is True else (mt.ROOT / "assets" / "music" / f"{bgm_req}.mp3" if isinstance(bgm_req, str) else None)
    if bgm_path and bgm_path.exists():
        so.mix_bgm(nob, bgm_path, video, total)
        report["bgm"] = bgm_path.name
    else:
        shutil.copy(nob, video)
        report["bgm"] = None
    return video, total, timeline


# ── 5. 검수 자료 ────────────────────────────────────────────────────────────────────────
def storyboard(text: dict, shots: dict, out: Path, report: dict) -> Path:
    """문장별 스토리보드 — 관점 · 문장 · 근거 · 컷 썸네일(최대 3). 공식 사진이 들어 있어 커밋·Release 금지(텔레그램·아티팩트만)."""
    beats = text["beats"]
    tw, th, pad, tx = 150, 267, 14, 640
    rowh = th + pad
    im = Image.new("RGB", (pad * 2 + tw * 3 + 8 * 2 + pad + tx, pad + len(beats) * rowh), (18, 20, 26))
    d = ImageDraw.Draw(im)
    f_lens, f_line, f_small = design.font(26), design.font(34), design.font(22, bold=False)
    veo_rows = {r["i"]: r for r in (report.get("veo") or {}).get("clips", [])}
    for r, b in enumerate(beats):
        y = pad + r * rowh
        for m, sid in enumerate(b["shots"][:3]):
            try:
                im.paste(Image.open(STORY / shots[sid]["img"]).convert("RGB").resize((tw, th), Image.LANCZOS), (pad + m * (tw + 8), y))
            except Exception:  # noqa: BLE001
                d.rectangle((pad + m * (tw + 8), y, pad + m * (tw + 8) + tw, y + th), fill=(40, 40, 48))
        x = pad * 2 + tw * 3 + 16
        vr = veo_rows.get(r + 1)
        who = {"hand": "손", "back": "뒷모습"}.get((b.get("person") or {}).get("kind"), "")
        tag = (" · AI 영상" + (f"(사람 컷 {who})" if who else "")) if vr and vr.get("ok") else \
              (f" · 사람 컷({who}) 자리" if who else (" · AI 영상 자리" if b["lens"] in VEO_LENSES else ""))
        d.text((x, y + 6), f"{r + 1} · {b['lens']}{tag}", font=f_lens, fill=(94, 234, 212))
        yy = y + 46
        line = b["line"]
        for ln in [line[k:k + 17] for k in range(0, len(line), 17)][:3]:
            d.text((x, yy), ln, font=f_line, fill=(255, 255, 255)); yy += 44
        basis = "근거: " + (sg._body(b["fact"]) if b["fact"] else "사진에 보이는 것")
        for ln in [basis[k:k + 26] for k in range(0, len(basis), 26)][:2]:
            d.text((x, yy + 6), ln, font=f_small, fill=(190, 190, 200)); yy += 30
        cuts = " / ".join(f"{sid} {shots[sid]['kind']}" for sid in b["shots"])
        d.text((x, yy + 10), cuts[:40], font=f_small, fill=(140, 140, 150))
    im.save(out, "JPEG", quality=86)
    return out


def preview_md(req: dict, sig: dict, text: dict, shots: dict, h: dict, pos: int, folder: str, report: dict, preview: bool) -> str:
    lc = report.get("lens_check") or {}
    md = [f"# 시그니처 이야기 {'미리보기' if preview else '제작'} — {h['name']} · {req.get('region')} · {req.get('theme')} · {req.get('month')}",
          f"구조: 장점 하나, 여러 관점 · 나레이션 + 가라오케 자막 + 음악 · 문장 {len(text['beats'])}개 · 프로필 {pos}번 ({folder}) · 영상에서는 숙소 이름 비공개", "",
          "## 장점", "", f"- **{sig['name']}** — {sig.get('what') or ''}", f"- 근거(사실 {sig.get('fact_i')}): {sg._body(sig['fact'])}",
          f"- 다른 후보와 다른 점: {sig.get('vs_peers') or '-'}" + (" · **코드가 정한 장점(모델이 3번 못 고름)**" if sig.get("fallback") else ""), ""]
    deep = (report.get("deep_facts") or {}).get("facts") or []
    if deep:
        md += ["## 장점 상세 사실(공식 홈페이지)", "", *[f"- {f}" for f in deep], ""]
    md += ["## 이야기 (관점별 한 문장)", "", "| # | 관점 | 문장 | 컷 | 근거 |", "|---|---|---|---|---|"]
    for j, b in enumerate(text["beats"], 1):
        cuts = ", ".join(x + "(" + shots[x]["kind"] + ")" for x in b["shots"])
        basis = sg._body(b["fact"])[:36] if b["fact"] else "사진에 보이는 것"
        md.append(f"| {j} | {b['lens']} | {b['line']} | {cuts} | {basis} |")
    pc_ = report.get("person_cut") or {}
    if pc_:
        who = {"hand": "손", "back": "뒷모습"}.get(pc_.get("kind"), "")
        md += ["", "## 사람 컷(1개)", "", f"- 문장 {pc_.get('i')} · {pc_.get('lens')} · {who}" + (" (코드가 고름)" if pc_.get("auto") else "")
               + f" · 동작: {pc_.get('action_en')}", "- 미리보기는 사진 무빙, 정식 제작 때 AI 영상으로 만들고 얼굴·여러 사람·새 물건·구조 변경을 비전으로 검수(탈락하면 사진 무빙)"]
    md += ["", "## 관점 검사", "", "- 결과: " + ("**통과**" if lc.get("ok") else "**미달 → 걸린 문장만 고치거나 뺌(아래 확인)**")]
    for e in (lc.get("after_fix") if not lc.get("ok") else []) or []:
        md.append(f"  - 고친 뒤 남은 것: {e}")
    for e in (report.get("story_fallback") or []):
        md.append(f"  - 처음 걸린 것: {e}")
    c = text["caption"]
    md += ["", "## 훅 제목", "", (f"**{text['hook_title']}** ({text['hook_title_type']})" if text.get("hook_title") else "(제목 없음 — 규칙에 맞는 후보가 없었다)"),
           "", "## 캡션", "", c.get("hook", ""), *(c.get("points") or []), "", *[f"· {x}" for x in text["checklist"]], "", c.get("save", ""),
           "", f"제목: {text['title']} · 해시태그: {' '.join(text['hashtags'])}", "",
           "## 비용", "", ("- 미리보기: AI 영상 없음(사진 무빙) · 글·비전·음성만 — 정식 제작 때 훅·정체·사람·약속 4컷만 AI 영상(약 1,176원)" if preview
                           else f"- AI 영상 {sum(1 for r in (report.get('veo') or {}).get('clips', []) if r.get('ok'))}/{len((report.get('veo') or {}).get('clips', []))}컷 · 이번 실행 약 {round(veo.spent_this_run()):,}원")]
    return "\n".join(md) + "\n"


# ── 6. 계획 저장·재사용 ─────────────────────────────────────────────────────────────────
NARR_FILES = ("narr_full.wav",)


def save_plan(req: dict, h: dict, pos0: int, pos: int, sig: dict, text: dict, shots: list[dict], narr: dict) -> Path:
    plan = {"version": 4, "stay": h["name"], "format": "story", "month": req.get("month"), "theme": req.get("theme"), "region": req.get("region"),
            "pos0": pos0, "pos": pos, "h": {k: h.get(k) for k in sg.H_KEYS}, "signature": sig, "text": text, "shots": shots,
            "narr": {str(k): v for k, v in narr.items()}}
    for f in list(mt.BUILD.glob("narr_c*.wav")) + [mt.BUILD / "narr_cta.wav", mt.BUILD / "narr_full.wav"]:
        if f.exists() and f.parent != STORY:
            shutil.copy(f, STORY / f.name)                                             # 아티팩트(build/story)에 음성까지 — 제작이 같은 목소리를 다시 쓴다
    out = STORY / "plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def find_reuse(req: dict) -> dict | None:
    if not req.get("reuse_runs") or not REUSE_DIR.exists():
        return None
    want = str(req.get("stay") or "").strip()
    for f in sorted(REUSE_DIR.glob("*/**/story/plan.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            plan = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if plan.get("version") != 4 or (want and plan.get("stay") != want):
            continue
        need = {s["img"] for s in plan["shots"]} | {f"narr_c{j}.wav" for j in range(1, len(plan["text"]["beats"]) + 1)} | {"narr_cta.wav"}
        if not all((f.parent / n).exists() for n in need):
            log(f"재사용 계획 {f} — 파일이 빠짐 → 건너뜀"); continue
        STORY.mkdir(parents=True, exist_ok=True)
        for g in f.parent.iterdir():
            if g.is_file():
                shutil.copy(g, STORY / g.name)
                if g.name.startswith("narr_"):
                    shutil.copy(g, mt.BUILD / g.name)
        log(f"미리보기 계획·음성 재사용(글·비전·음성 0원): {f.relative_to(REUSE_DIR)}")
        return plan
    return None


# ── 진입점 ──────────────────────────────────────────────────────────────────────────────
def produce_story(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    preview = str(req.get("stage") or "") == "preview"
    if STORY.exists():
        shutil.rmtree(STORY)
    STORY.mkdir(parents=True, exist_ok=True)
    mt.BUILD.mkdir(parents=True, exist_ok=True)
    report["stage"] = "preview" if preview else "produce"
    report["format"] = "story"
    voice, tempo = str(req.get("voice") or ms.VOICE_DEFAULT), float(req.get("tempo") or mt.TEMPO)
    plan = None if preview else find_reuse(req)
    folder = mt.folder_name(req)
    if plan:
        h, pos0, pos, sig, text, shot_list = plan["h"], plan.get("pos0") or 0, plan.get("pos") or 1, plan["signature"], plan["text"], plan["shots"]
        narr = {(int(k) if str(k).isdigit() else k): v for k, v in (plan.get("narr") or {}).items()}
        report["reused_plan"] = True
        report["hotels"] = [{k: h.get(k) for k in sg.H_KEYS if k in h}]
        report["lens_check"] = {"ok": True, "note": "미리보기 대본 재사용"}
        recheck_shots(text, shot_list, sig, report)
    else:
        h, pos0 = so.assets(req, models, report)
        sig = sg.choose_signature(models, h, req, report)
        facts = sg.facts_list(h) + deep_facts(models, h, sig, report)
        shot_list = build_shots(models, sig, h, report)
        if len(shot_list) < 2:
            raise RuntimeError(f"시그니처 이야기 불가 — 컷 재료 {len(shot_list)}개 (만들지 않음)")
        toks = adv_tokens(sig, [s["desc"] for s in shot_list if s["adv"]])
        peers = sg.peer_lines(req, h)
        text = write_story(models, sig, h, req, facts, shot_list, peers, toks, report)
        try:
            pos = make_folder.place_hotel(req, h, pos0, None)
        except Exception as e:  # noqa: BLE001
            log(f"폴더 데이터 갱신 실패 ({str(e)[:80]}) — 순위표 위치로 대체")
            pos = pos0 or 1
        script = {"cuts": [{"i": j, "narration": b["line"]} for j, b in enumerate(text["beats"], 1)], "cta": {"narration": so.cta_text(folder, pos)}}
        narr = so.narrate(models, script, voice, tempo)
        report["narration_sec"] = {str(k): round(v, 2) for k, v in narr.items()}
        report["narration_qa"] = mt.narration_qa(models, so.qa_items(script))
        nar = mt.BUILD / "narr_full.wav"
        if nar.exists():
            ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(nar), "-codec:a", "libmp3lame", "-q:a", "4", str(ms.PREVIEW / "narration_preview.mp3")])
        sg.unblock(h["name"])
        save_plan(req, h, pos0, pos, sig, text, shot_list, narr)
    shots = {s["id"]: s for s in shot_list}
    report["signature"] = {k: sig.get(k) for k in ("name", "what", "fact", "vs_peers", "peers", "photos", "confirmed", "why", "checks", "fallback")}
    video, total, timeline = render(text, shots, narr, req, report, folder, pos, preview, models)
    if not preview:
        so.save_hook_title(h["name"], {"hook_title": text["hook_title"], "hook_title_type": text["hook_title_type"]})
    storyboard(text, shots, ms.PREVIEW / "compare_sheet.jpg", report)
    (ms.PREVIEW / "preview.md").write_text(preview_md(req, sig, text, shots, h, pos, folder, report, preview), encoding="utf-8")
    report["hook_title"] = {"title": text["hook_title"], "type": text["hook_title_type"]}
    report["script"] = {"hook_title": text["hook_title"], "title": text["title"], "caption": text["caption"], "checklist": text["checklist"],
                        "cuts": [{"i": j, "narration": b["line"], "caption": b["lens"]} for j, b in enumerate(text["beats"], 1)]}
    report["screen_qa"] = []
    report["timeline"] = timeline
    c = text["caption"]
    pc = h.get("photo_counts") or {}
    v = report.get("veo") or {}
    ai = sum(1 for r in v.get("clips", []) if r.get("ok"))
    lens_ok = bool((report.get("lens_check") or {}).get("ok"))
    caption = (ms.DISCLOSURE + "\n\n" + str(c.get("hook") or "").strip()
               + ("\n" + "\n".join(c.get("points") or []) if c.get("points") else "")
               + ("\n\n" + "\n".join(f"· {x}" for x in text["checklist"]) if text["checklist"] else "")
               + "\n\n" + str(c.get("save") or "저장해두고 다시 꺼내 보세요.") + "\n같이 갈 사람에게도 보내 주세요."
               + f"\n\n{h['name']}" + (f" · {h['city']}" if h.get("city") else "")
               + f"\n객실 타입·예약 링크는 프로필 링크 → {pos}번 ({folder})"
               + ("\n사진: 숙소 공식 홈페이지" if pc.get("official") else "")
               + ("\n일부 장면의 움직임(물결·빛·카메라 이동)은 실제 사진을 바탕으로 AI로 만들었어요. 실제 모습과 다를 수 있어요." if ai else "")
               + ("\n손·뒷모습 장면은 AI로 만든 연출이에요(실제 사람 아님)." if any(r.get("ok") and r.get("person") for r in v.get("clips", [])) else "")
               + "\n\n" + " ".join(text["hashtags"]))
    meta = {"mode": "signature", "format": "story", "label": "시그니처 이야기 미리보기(AI 영상 없음)" if preview else f"시그니처 이야기 제작(AI 영상 {ai}/{len(v.get('clips', []))}컷)",
            "stage": report["stage"], "stay": h["name"], "signature": sig["name"], "title": text["title"], "caption": caption, "folder": folder, "folder_pos": pos,
            "bgm": report.get("bgm"), "pinned_comment": f"{h['name']} — 객실 타입·링크는 프로필 링크 → {pos}번 ({folder}) · 쿠팡 파트너스 링크 포함",
            "affiliate_urls": {h["name"]: h.get("affiliate_url")}, "lines": [b["line"] for b in text["beats"]], "cuts": timeline, "lens_ok": lens_ok,
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": ai, "clips_total": len(v.get("clips", [])),
                    "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
