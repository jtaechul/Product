"""시그니처 원테마 쇼츠 — mode "signature".

v1(2026-10-14) 실패 — stay-run-47 롯데리조트 속초(약 714원): 쿠팡 외관 항공 사진 2~3장을 빛만 바꿔 6컷 반복 + 분위기 자막
("푸른 바다 앞 / 노을빛 물들고 / 따뜻한 곳이에요") → 운영자 "차별성이 전혀 안 보인다 · 관련 없는 이미지만 주구장창 · 쓸데없는 감성팔이".
원인(내 설계): ① 변주 계획이 '같은 사진을 빛·날씨·사람만 바꿔 여러 컷'을 강제 ② 자막 지시가 분위기 예시 + '화면(노을)에 맞춰라', 정보 없는 문장을 막지 않음
③ 시그니처를 다른 후보와 비교하지 않음(후보 8곳 공통인 테마 그 자체를 고름) ④ 9컷 형식의 '외관 1장'·근접 중복 거르기를 안 옮기고, 사진 확인이
'귀퉁이에 보이면 통과' ⑤ 2컷도 못 만들 재료인데 멈추지 않음.

v2(2026-10-15 운영자 "진행해") — 한 숙소 = 한 시그니처는 그대로, **컷마다 다른 사진 + 사실 하나**:
  1. 사진·사실 수집(make_solo.assets 그대로) → 쓸 사진 = 사람 없음·다른 지점 아님·품질 5↑ + 거의 같은 사진 제거 + **외관·전경은 1장까지**
  2. 시그니처 선정 — 같은 테마 다른 후보들이 내세우는 것과 나란히 보고 **이 숙소에만 있는 구체적인 것**(형태·위치·방식)을 고른다.
     전할 정보(points) = 신박함 → 차별성 → 유인 요소, 각 줄이 사실 번호에 묶이고 그 사실의 낱말을 써야 한다(분위기·체험 표현 금지).
  3. 사진 확인 — 시그니처가 사진의 **주인공**인가(화면 비율 추정 0.25 이상 · 멀리서 찍은 전경 귀퉁이는 탈락).
  4. 컷 = 확인된 사진(서로 다름) × 전할 정보(순서대로), 둘 중 적은 수(몽타주 최대 5 · 한 장면 최대 2). **2컷이 안 되면 만들지 않는다**(돈 쓰기 전).
     빛·날씨·인물 편집은 하지 않는다(정보 없는 장식 — 미리보기 이미지 0원).
  5. 자막 — 컷마다 그 컷의 정보 하나(근거 사실 낱말 필수 · 분위기 낱말·1인칭·과거형·숙소 이름·가격 금지 · 앞 컷과 같은 말 금지).
     훅 제목 = 시그니처의 신박함을 묻는 질문(시그니처 낱말 필수). 캡션 첫 줄 = 신박함, 다음 = 차별성·유인, 체크리스트(사실 번호).
     **정보 전달 시험**: 화면 글자만 보고 '특별한 점'을 말하게 해 사실과 2개 이상 맞아야 통과(두 번까지 다시 쓰고, 마지막은 경고로 남김).
  6. 렌더 — 사진 무빙(0원) + 제작 때만 첫 컷 Veo(294원), 정보 자막 컷 2.4초(읽을 시간), 끝 카드, 배경음악만.

v3(2026-10-15 운영자 "원인부터 똑바로 파악해 · 니가 있는 사진으로 ai 영상을 만들라고 했잖아") — v2 실행 두 번(stay-run-48·49) 연속 실패의 원인:
  ① 영상보다 '완벽한 시그니처 찾기' 관문을 앞에 세웠다(다른 후보와 다름 · 주인공 사진 2장 · 전할 정보 2개를 다 넘어야 영상)
     → 모델이 사진 1장짜리 답(run-48)·빈 답(run-49)을 내자 영상 0개로 끝났다
  ② 가짜 모델 답으로만 시험했다 — 실제 모델이 관문을 못 넘는 경우를 시험하지 않았다
  ③ 2026-10-09 확정 방식(사진마다 이미지→AI 영상)에서 벗어나 정지 사진 확대(사진 무빙)만 썼다
  고침 — **쓸 사진 2장 이상 + 사실 1개 이상이면 반드시 영상을 만든다**:
  - 시그니처: 모델 최대 3번(빈 답·규칙 위반은 이유를 붙여 다시) → 그래도 못 고르면 코드가 정한다(사진이 가장 많이 이어진 사실). 관문은 '우선순위'로만.
  - 컷 사진: 주인공 확인 사진 → 설명에 시그니처 낱말이 있는 사진 → 사실과 이어진 사진(→ 2컷이 안 될 때만 품질 순·외관). 컷 자막 = 그 사진 설명과 맞는 사실.
  - 렌더: **컷마다 그 실제 사진을 Veo 4초 AI 영상으로**(9컷 형식과 같은 지시문 — 사진별 카메라·자연 움직임 + 구조 유지). 실패한 컷만 사진 무빙.
  - 자막이 규칙에 3번 걸리면 걸린 줄만 사실 문장으로 바꿔 끝까지 만든다(멈추지 않음 · 기록에 남김).

요청: {"mode":"signature","stay":..,"stage":"preview"|없음,"format":"montage"|"single","veo_approved":true}
미리보기 = 컷마다 AI 영상(몽타주 최대 5컷 약 1,470원 · 한 장면 2컷 약 590원 + 글·비전 수십 원) → **미리보기도 돈이 든다 → veo_approved 필수**
(관리실 버튼이 금액을 보여 주고 한 번 더 확인 = 허락). 제작 = 미리보기 계획·AI 클립 재사용(reuse_runs → build/reuse/*/…/sig/plan.json · 0원).
쓸 사진이 2장 미만·사실 0개로 멈추면 state/sig_blocked.json 에 남긴다 — 관리실이 그 숙소의 시그니처 버튼을 잠근다(14일 뒤 풀림 · 성공하면 지움).
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

import design
import make_folder
import make_mini
import make_solo as so
import make_stay as ms
import make_top3 as mt
import photos
import veo

SIG = ms.BUILD / "sig"
REUSE_DIR = ms.BUILD / "reuse"
FAKE_IMG = os.environ.get("SIG_FAKE_IMAGE", "") == "1"          # 로컬 시험: 이미지 편집 대신 색만 바꾼 가짜 변주(0원)
MAX_EDITS = 5                                                     # (빛·날씨·인물 편집 — v2 는 쓰지 않는다. make_images 는 편집 컷이 있을 때만 돈을 쓴다)
EDIT_TRIES = 7                                                    # 한 번 실행의 편집 호출 상한(재시도 포함)
N_SHOTS = {"montage": 5, "single": 2}                             # 컷 수 상한 — 시그니처·사실과 이어진 사진 수만큼(이어진 사진이 모자라면 2컷까지만 채운다)
MIN_CUTS = 2                                                      # 쓸 사진이 이보다 적으면 만들지 않는다 — 같은 사진을 돌려 쓰지 않는다(run-47)
DUR = {"hook": 4.0, "mid": 3.0, "last": 3.0, "card": 2.8}        # 컷마다 AI 영상 4초 중 앞부분 — 자막 읽을 시간(14자 약 2.3초) + 움직임이 보일 시간
VEO_SEC = 4                                                       # 컷마다 Veo 4초(약 294원 · veo.py 의 한 번 실행 3,000원·한 달 50,000원 상한 그대로)
SUBJECT_MIN = 0.25                                                # 사진 확인: 시그니처가 화면에서 차지하는 비율(비전 추정) 하한 — 전경 귀퉁이는 탈락
MOTION_SIG = 0.12                                                 # 짧은 컷이라 사진 무빙 폭을 9컷 형식(0.24)의 절반으로
MUSIC_LEVEL = 0.9                                                 # 나레이션이 없어 음악을 주 소리로
PATTERNS = ("push", "pan", "diag", "tilt", "pull")
MOOD_RX = re.compile(r"노을빛|물들|푸른|힐링|낭만|감성|설레|설렘|여유로|아늑|포근|로맨틱|그림\s?같|꿈\s?같|인생샷|완벽한|행복|분위기|추억|따뜻한 곳|쉬는 곳|머물고 싶")   # run-47 '감성팔이' — 사실 없는 분위기 말
FACT_PREFIX_RX = re.compile(r"^(블로그 교차 확인 시설|공식 홈페이지 한 줄 요약|공식 홈페이지 상세|공식 안내문|후보표 훅): ")
ROLES = ("신박함", "차별성", "유인")
ADJ_RX = re.compile(r"인접|근처|주변|바로\s?옆|옆에|도보|셔틀|차로|분 거리|가까운")      # 숙소 밖 시설(stay-run-48: '오션월드와 루지월드 인접'을 숙소 시설처럼 고를 뻔)
PEERS_PATH = mt.ROOT / "data" / "discover" / "latest" / "candidates.json"     # 같은 테마 다른 후보(시그니처를 비교로 고르려고)
BLOCKED = mt.ROOT / "state" / "sig_blocked.json"                              # 사진·사실이 모자라 멈춘 숙소 — 관리실이 시그니처 버튼을 잠근다
PAST_RX = re.compile(r"(었|았|였)(어요|다|고|는데|지만|던|죠)|더라|다녀|묵었|머물렀|즐기고 온|좋았|했던|갔던|봤는데")   # 1인칭 체험·과거형 (stay__list 캡션의 위험 요소)
FIRST_RX = re.compile(r"(^|\s)(저는|제가|저희|우리가|우리는|내가|나는)")
DIGIT_RX = re.compile(r"\d[\d,.]*")
GENERIC_SIG = {"객실", "숙소", "호텔", "리조트", "공간", "시설", "전망", "뷰", "실내", "야외", "있는", "갖춘", "운영", "보유"}

VARIANTS = {
    "original": "",
    "golden": ("the time of day becomes late-afternoon golden hour: warm, low sunlight, long soft shadows and a warm orange-pink sky wherever the sky is visible; "
               "lamps that already exist may glow softly."),
    "dusk": ("dusk (blue hour): a deep blue sky with a last warm glow at the horizon wherever the sky is visible; lights and lamps that already exist glow warmly "
             "and their reflections appear on existing water and glass."),
    "night": ("night: a dark sky wherever the sky is visible; only the lights and lamps that already exist in the photo glow warmly; "
              "no new light fixtures, no fireworks."),
    "rain": ("a gentle rainy day: soft overcast light, fine visible rain streaks, wet glossy surfaces and small rain ripples on water that already exists; "
             "low clouds or mist over distant mountains only if mountains are already visible."),
    "snow": ("light snowfall: soft falling snowflakes and a thin layer of fresh snow on outdoor horizontal surfaces that already exist (roofs, railings, ground, trees); "
             "indoor areas stay the same except snow seen through existing windows."),
    "mist": "an early morning: soft, cool morning light and a thin mist floating over water or distant landscape that already exists.",
    "steam": "cool air: soft white steam rising slowly from the surface of the warm water that already exists.",
}
VARIANT_KO = {"original": "원본", "golden": "노을빛", "dusk": "해 질 녘", "night": "밤", "rain": "비 오는 날", "snow": "눈", "mist": "아침 안개", "steam": "김"}
PEOPLE = {"one": "one adult", "couple": "a couple (two adults)", "family": "a parent and a young child"}
PEOPLE_KO = {"one": "한 명", "couple": "두 사람", "family": "부모와 아이"}
POSES = {"soak": "soaking up to the shoulders in the warm water that already exists, looking at the view",
         "sit": "sitting on a seat, bench or deck edge that already exists, looking at the view",
         "stand": "standing at a window, railing or edge that already exists, looking out at the view",
         "walk": "walking slowly away from the camera along a path that already exists"}
POSE_KO = {"soak": "몸 담그고 바라보기", "sit": "앉아서 바라보기", "stand": "서서 바라보기", "walk": "천천히 걷기"}

EDIT_KEEP = ("TASK: Edit the attached photograph of a real hotel into a mood variation of the SAME place at a different moment. "
             "KEEP EXACTLY: the camera position, framing and lens; every building, wall, roof, window, door, pool or bath shape, water edge, deck, railing, "
             "furniture, plant and object, with the same positions, sizes, colors and materials; the view outside (sea, mountains, skyline, city) and its direction. "
             "Do not add, remove, move, enlarge, shrink or redesign anything. Do not add new furniture, lamps, decorations, pools, water, plants, signs, text, logos or watermarks. ")
EDIT_PEOPLE = ("PEOPLE: add {who}, seen strictly from behind — the backs of their heads and shoulders toward the camera, no face visible — {pose}, at {place}. "
               "Realistic people at correct human scale for the perspective, relaxed and nearly still, partly hidden where natural (for example below the water line). "
               "Swimwear only when they are in water; otherwise simple casual clothes or bathrobes. They stay on surfaces that already exist in the photo. No other people. ")
EDIT_NO_PEOPLE = "Do not add any people or animals. "
EDIT_TAIL = ("The result must look like a real, unretouched photo taken by the same camera at a different moment — photorealistic, natural colors, "
             "no painterly, illustrated or cartoon look.")

def log(*a):
    print("[sig]", *a, flush=True)


# ── 공통 호출 ──────────────────────────────────────────────────────────────────────────
def _json_text(model: str, system: str, content: str, temp: float = 0.4, max_tokens: int = 3000) -> dict:
    body = {"system_instruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": [{"text": content}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temp, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    txt = "".join(p.get("text", "") for p in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])).strip()
    txt = re.sub(r"^```(?:json)?|```$", "", txt).strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError(f"JSON 아님: {txt[:120]}")
    return json.loads(m.group(0))


def _b64(path: Path, side: int = 1024) -> str:
    import io
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _json_vision(model: str, system: str, text: str, images: list[Path], side: int = 1024) -> dict:
    parts = [{"text": text}]
    for k, p in enumerate(images, 1):
        parts += [{"text": f"사진 {k}:"}, {"inline_data": {"mime_type": "image/jpeg", "data": _b64(p, side)}}]
    body = {"system_instruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 600, "temperature": 0.0, "responseMimeType": "application/json", "thinkingConfig": {"thinkingBudget": 0}}}
    try:
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    except RuntimeError as e:
        if "thinking" not in str(e).lower():
            raise
        body["generationConfig"].pop("thinkingConfig", None)
        data = ms._gpost(f"models/{model}:generateContent", body, 120)
    txt = "".join(p.get("text", "") for p in (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])).strip()
    m = re.search(r"\{.*\}", re.sub(r"^```(?:json)?|```$", "", txt).strip(), re.S)
    return json.loads(m.group(0)) if m else {}


def month_num(req: dict) -> int:
    m = re.search(r"-(\d{1,2})\b", str(req.get("month") or ""))
    return int(m.group(1)) if m else 0


def _tokens(text: str) -> set[str]:
    """비교용 낱말: 2자 이상, 조사·일반 낱말 제거."""
    out = set()
    for w in re.findall(r"[가-힣A-Za-z0-9]+", str(text or "")):
        w = re.sub(r"(은|는|이|가|을|를|과|와|의|에|에서|으로|로|도|만|까지|부터|이에요|예요|이다|있는|하는)$", "", w)
        if len(w) >= 2 and w not in GENERIC_SIG:
            out.add(w)
    return out


def _overlap(ta: set[str], tb: set[str]) -> int:
    """ta 낱말 중 tb 의 어떤 낱말과 겹치는(한쪽이 다른 쪽을 포함) 수 — '산토리니풍'↔'산토리니' 같은 형태 차이를 인정한다."""
    return sum(1 for a in ta if any(a in b or b in a for b in tb))


def _int(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    return int(x) if isinstance(x, str) and x.strip().isdigit() else None


def _ask(models: dict, system: str, content: str, temp: float) -> dict:
    """글 호출 + JSON 해석. 답이 JSON 이 아니면 한 번 더 묻는다(모델 교체는 _try_models 가 맡는다)."""
    last = None
    for _ in range(2):
        try:
            return ms._try_models("text", models["text"], lambda m: _json_text(m, system, content, temp=temp))
        except (ValueError, json.JSONDecodeError) as e:
            last = e
            log(f"JSON 답 해석 실패 → 다시: {str(e)[:80]}")
    raise RuntimeError(f"JSON 답을 받지 못함: {last}")


# ── 1. 사실·사진 목록 ─────────────────────────────────────────────────────────────────────
def _body(f) -> str:
    """사실 줄에서 출처 머리말('블로그 교차 확인 시설: ' 등)을 뗀 본문 — 낱말 겹침 검사는 본문으로만 한다."""
    return FACT_PREFIX_RX.sub("", str(f or ""))


def _cut(text, n: int) -> str:
    """띄어쓰기 단위로 n자 안에서 자른다(낱말 중간을 자르지 않는다 · 첫 낱말이 n자를 넘으면 그 낱말만 n자로)."""
    t = design.one_line(str(text or "")).strip()
    if len(t) <= n:
        return t
    out = ""
    for w in t.split():
        c = f"{out} {w}".strip()
        if len(c) > n:
            break
        out = c
    return out or t[:n]


def _fmt(req: dict) -> str:
    return "single" if str(req.get("format") or "") == "single" else "montage"


def facts_list(h: dict) -> list[str]:
    """시그니처·전할 정보·체크리스트의 근거가 되는 사실(번호를 붙여 AI 에 준다). 이 목록 밖의 사실은 쓰지 않는다.
    후보표 훅(후보 찾기 때 AI 가 쓴 한 줄)은 사실이 아니라서 넣지 않는다 — run-47 시그니처 근거가 이것이었다."""
    out = [str(f).strip() for f in (h.get("official_facts") or []) if str(f).strip()]
    out += [f"블로그 교차 확인 시설: {f}" for f in (h.get("verified_facilities") or []) if str(f).strip()]
    if h.get("signature"):
        out.append(f"공식 홈페이지 한 줄 요약: {h['signature']}")
    out += [f"공식 안내문: {f}" for f in (h.get("notice_facts") or []) if str(f).strip()]      # v6: 글 안내문 이미지에서 읽은 사실(반려견 입장·무료·운영시간)
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f); uniq.append(f)
    return uniq


def usable_photos(h: dict, min_q: int = 5) -> list[dict]:
    """쓸 수 있는 사진 — 사람 없음·다른 지점 아님·품질 min_q 이상 + 거의 같은 사진(dHash) 제거 + **외관·전경은 1장까지**(품질 높은 것).
    run-47: 쿠팡 외관 항공 사진 5장(같은 단지 다른 각도)이 모두 '시그니처 사진'으로 들어가 6컷을 채웠다 → 9컷 형식의 MAX_EXTERIOR 를 그대로 쓴다.
    v3: 품질 5 이상이 2장이 안 되면 choose_signature 가 품질 3 이상(9컷 형식 기준)으로 한 번 더 본다 — 사진이 있는데 멈추지 않게."""
    base = [p for p in (h.get("classified") or []) if p.get("category") in photos.CATS and int(p.get("quality") or 0) >= min_q
            and not p.get("people") and not p.get("mismatch") and not p.get("closed") and photos.panel_grade(p) != "none"
            and Path(str(p.get("path") or "")).exists()]
    base.sort(key=lambda p: (-int(p.get("quality") or 0), int(p.get("k") or 0)))
    out, hashes, ext = [], [], 0
    for p in base:
        try:
            hv = mt.dhash(p["path"])
        except Exception:  # noqa: BLE001
            hv = None
        if hv is not None and any(mt.near_dup(hv, x) for x in hashes):
            continue
        if mt.is_exterior(p):
            if ext >= mt.MAX_EXTERIOR:
                continue
            ext += 1
        out.append(p)
        if hv is not None:
            hashes.append(hv)
    return sorted(out, key=lambda p: int(p["k"]))


def _photo_line(p: dict) -> str:
    alt = f" · 공식 사진 이름 '{p['src_alt']}'" if p.get("src_alt") else ""
    return f"사진 {p['k']} [{mt.SRC_KO.get(p.get('source'), '?')} · {p.get('category')} · {p.get('view') or '-'} · 품질 {p.get('quality')}{alt}] {p.get('description') or ''}"


def peer_lines(req: dict, h: dict) -> list[str]:
    """같은 후보표(같은 테마·지역·월)의 다른 숙소가 내세우는 것 — 시그니처를 '비교'로 고르게 한다(run-47: 후보 8곳 공통점을 고름)."""
    try:
        c = json.loads(PEERS_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out = []
    for x in c.get("candidates") or []:
        if not isinstance(x, dict) or x.get("name") == h.get("name"):
            continue
        ai = x.get("ai") or {}
        fac = [str(f.get("facility")) for f in (x.get("facility_checks") or []) if isinstance(f, dict) and f.get("verified")] \
            or [str(f) for f in (ai.get("known_facilities") or [])]
        why = x.get("why")
        hook = str(ai.get("hook") or (" ".join(map(str, why)) if isinstance(why, list) else (why or "")))
        line = " · ".join(t for t in (hook.strip(), ", ".join(fac)) if t)
        if line:
            out.append(f"{x.get('name')}: {line}"[:140])
    return out[:12]


def common_tokens(name: str, peers: list[str], req: dict) -> tuple[list[str], int]:
    """시그니처 이름 낱말 중 테마 낱말이거나 다른 후보 절반 이상(최소 2곳)이 함께 내세우는 낱말. 전부 그렇다면 차별점이 아니다."""
    toks = _tokens(name)
    if not toks:
        return [], 0
    theme = _tokens(req.get("theme"))
    need = max(2, (len(peers) + 1) // 2)
    common = [t for t in toks if _overlap({t}, theme) or (peers and sum(1 for pl in peers if t in pl) >= need)]
    return common, len(toks)


def _blocked() -> dict:
    try:
        d = json.loads(BLOCKED.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def block(h: dict, req: dict, reason: str) -> None:
    """사진·사실이 모자라 멈춘 숙소를 남긴다 — 관리실이 그 숙소의 시그니처 버튼을 잠근다(14일 뒤 풀림 · 성공하면 지운다)."""
    from datetime import date
    d = _blocked()
    d[h["name"]] = {"at": date.today().isoformat(), "reason": reason[:200], "theme": req.get("theme"), "month": req.get("month")}
    BLOCKED.parent.mkdir(parents=True, exist_ok=True)
    BLOCKED.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def unblock(name: str) -> None:
    d = _blocked()
    if name in d:
        d.pop(name)
        BLOCKED.write_text(json.dumps(d, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ── 2. 시그니처 선정 ─────────────────────────────────────────────────────────────────────
SIG_SYSTEM = """너는 숙소 쇼츠 기획자다. 시청자가 "이런 데가 있다고?" 하고 멈출 이 숙소의 **시그니처 하나**와, 그것에 대해 **영상에서 전할 정보**를 정한다.
시그니처 = 이 숙소에만 있는 구체적인 시설·장면 하나. 형태·위치·방식이 드러나야 한다
  (좋은 예: "이집트 신전풍 노천 스파", "돔 지붕이 열리는 인피니티풀", "객실 전용 노천탕", "바다 쪽으로 끝이 열린 온수풀").
  나쁜 예: 테마 그대로이거나 다른 후보 여럿이 함께 가진 것("실내 온수풀", "사계절 워터파크", "스파 시설"), 리조트 전경, 평범한 객실·로비.
아래 '같은 테마 다른 후보'가 다 가진 것은 피한다. 낱말이 겹치면 이 숙소만의 형태·위치·방식을 이름에 넣어 다른 점이 보이게 한다.
테마와 이어지는 시그니처를 먼저 찾고, 없으면 이 숙소만의 다른 것(테마 객실·이색 시설 등)을 고른다.
조건:
1) 근거: '사실' 목록 중 하나(번호)가 그 시그니처를 직접 말해야 한다. 사실에 없는 시그니처는 고르지 않는다.
2) points(영상에서 전할 정보) 2~5개, 순서: 신박함(그게 무엇이고 왜 의외인지) → 차별성(다른 후보와 다른 구체적인 점) → 유인(그래서 거기서 할 수 있는 것·언제).
   각 point 는 **그 시그니처에 대한** 사실 한 줄(번호)을 짧게 옮긴 것(4~24자) — 다른 시설 이야기·분위기·감성 묘사 금지, 사실에 없는 내용·숫자 추가 금지.
3) photos: 그 시그니처가 **사진의 주인공**(화면의 큰 부분·초점)인 서로 다른 사진 번호 2~5개, 좋은 것부터.
   멀리서 찍은 단지 전경·항공 사진에서 작게 보이는 것은 안 된다. **주인공 사진이 2장 안 되는 시그니처는 고르지 않는다** —
   사진 목록을 보고 사진이 넉넉한 다른 시그니처를 찾는다(영상은 컷마다 다른 사진이 필요하다).
4) 시기가 11~3월이면 바깥의 여름 물놀이(카바나·선베드·해수욕·야외 수영장)는 시그니처가 될 수 없다(온수·사계절이라고 사실에 있으면 된다).
5) 숙소 밖 시설(사실에 '인접·근처·바로 옆·셔틀·도보' 등, 또는 숙소와 이름이 다른 이웃 시설 — 예: 오션월드·루지월드·스키장)이 시그니처면
   이름이나 what 에 '바로 옆' 같은 위치를 넣고 첫 point 에도 위치를 말한다 — 숙소 안 시설처럼 보이게 하지 않는다. 숙소 안에 좋은 시그니처가 있으면 그것을 먼저.
6) 시그니처는 **반드시 하나** 고른다(빈 답 금지). 완벽한 것이 없으면 아래 '사실별 사진'에서 사진이 2장 이상인 사실 중 가장 의외인 것을 고른다.
   사실·사진에 없는 것을 지어내지는 않는다.
JSON 만: {"signature":"2~16자","what":"사진에 보이는 모습 한 줄","fact":번호,"vs_peers":"다른 후보와 다른 점 한 줄",
 "points":[{"role":"신박함|차별성|유인","text":"4~24자","fact":번호}],"photos":[번호],"surprise":1~10,"why":"왜 의외인지 한 줄","alternatives":["다른 후보 이름"]}"""

CONFIRM_SYSTEM = """너는 숙소 사진 검수자다. 사진 1장과 시그니처 이름·설명을 받는다.
그 시그니처가 이 사진의 **주인공**인지 판단한다 — 화면의 큰 부분을 차지하고 초점이 맞아 무엇인지 바로 알아볼 수 있어야 한다.
멀리서 찍은 단지 전경·항공 사진에서 작게 보이거나 귀퉁이에 걸린 것, 다른 것이 주인공이고 일부만 보이는 것은 주인공이 아니다(추측 금지).
share = 그 시그니처가 화면에서 차지하는 비율(0~1) 추정.
JSON 만: {"subject": true 또는 false, "share": 0.0~1.0, "evidence": "사진에 보이는 근거 한 줄"}"""


def check_points(js: dict, facts: list[str]) -> tuple[list[dict], list[str]]:
    """전할 정보(points) — 각 줄이 근거 사실의 낱말을 쓰고, 분위기·체험 표현·사실에 없는 숫자가 없어야 쓴다. 쓸 수 있는 것만 돌려준다."""
    good, notes = [], []
    for j, p in enumerate([x for x in (js.get("points") or []) if isinstance(x, dict)], 1):
        t = design.one_line(str(p.get("text") or ""))
        role, pf = str(p.get("role") or "").strip(), _int(p.get("fact"))
        if role not in ROLES:
            notes.append(f"point {j} role '{role}' — 신박함/차별성/유인 중 하나"); continue
        if pf is None or not (1 <= pf <= len(facts)):
            notes.append(f"point {j} fact 번호가 사실 목록에 없음"); continue
        src = facts[pf - 1]
        if not (4 <= len(t) <= 30):
            notes.append(f"point {j} '{t}' — 4~24자"); continue
        if not _overlap(_tokens(t), _tokens(_body(src))):
            notes.append(f"point {j} '{t}' 이 사실 {pf}('{_body(src)[:24]}')의 낱말을 쓰지 않음 — 사실을 그대로 짧게"); continue
        if MOOD_RX.search(t) or PAST_RX.search(t) or FIRST_RX.search(t):
            notes.append(f"point {j} '{t}' 분위기·체험 표현 — 사실만"); continue
        if any(d not in src for d in DIGIT_RX.findall(t)):
            notes.append(f"point {j} '{t}' 숫자는 사실에 있는 것만"); continue
        good.append({"role": role, "text": t, "fact": src, "fact_i": pf})
    return good, notes


def sig_errs(js: dict, facts: list[str], pool: dict, h: dict, req: dict, peers: list[str] | None = None) -> list[str]:
    errs = []
    name = str(js.get("signature") or "").strip()
    if not (2 <= len(name) <= 16):
        errs.append("signature 이름 2~16자")
    fi = _int(js.get("fact"))
    if fi is None or not (1 <= fi <= len(facts)):
        errs.append(f"fact 번호가 사실 목록(1~{len(facts)})에 없음")
        return errs
    fact = facts[fi - 1]
    if not _overlap(_tokens(name) | _tokens(js.get("what")), _tokens(_body(fact))):
        errs.append(f"근거 사실 {fi}('{_body(fact)[:30]}')이 시그니처 '{name}'를 직접 말하지 않음 — 낱말이 겹치는 사실을 고른다")
    common, n = common_tokens(name, peers or [], req)
    if n and len(common) == n:
        errs.append(f"'{name}' 은 테마·다른 후보 여럿이 함께 가진 공통점({', '.join(common)}) — 이 숙소에만 있는 형태·위치·방식이 드러나는 것으로")
    if not str(js.get("vs_peers") or "").strip():
        errs.append("vs_peers(다른 후보와 다른 점 한 줄) 없음")
    good, notes = check_points(js, facts)
    if len(good) < 2 or good[0]["role"] != "신박함":
        errs.append(f"쓸 수 있는 전할 정보 {len(good)}개{' — 첫 줄이 신박함이 아님' if good and good[0]['role'] != '신박함' else ''}: "
                    "그 시그니처에 대한 사실로 2개 이상, 첫 줄은 신박함")
        errs += notes[:4]
    if ADJ_RX.search(_body(fact)):
        if not ADJ_RX.search(f"{name} {js.get('what') or ''}"):
            errs.append(f"근거 사실이 숙소 밖 시설('{ADJ_RX.search(_body(fact)).group(0)}') — 이름이나 what 에 '바로 옆' 같은 위치를 넣는다")
        if good and not ADJ_RX.search(good[0]["text"]):
            errs.append("숙소 밖 시설 — 첫 point(신박함)에 '바로 옆' 같은 위치를 말한다")
    ks = [_int(k) for k in (js.get("photos") or [])]
    if not ks or any(k not in pool for k in ks) or len(set(ks)) != len(ks):
        errs.append(f"photos 는 위 목록의 서로 다른 사진 번호 {MIN_CUTS}~5개")
        return errs
    if len(ks) < MIN_CUTS:
        errs.append(f"photos {len(ks)}장 — 시그니처가 주인공인 사진 {MIN_CUTS}장 이상(안 되면 사진이 넉넉한 다른 시그니처)")
    hero = pool[ks[0]]
    desc = f"{hero.get('description') or ''} {hero.get('src_alt') or ''} {fact}"
    bad = [t for t in photos.facility_terms(name) if not photos.term_ok(t, desc)]
    if bad:
        errs.append(f"시그니처 이름의 시설 '{'/'.join(bad)}'이 사진 설명·근거 사실에서 확인되지 않음")
    if so.cold_month(req) and so.off_season(hero):
        errs.append("겨울 편에 바깥 여름 물놀이 사진을 시그니처로 고름")
    return errs


def fact_groups(facts: list[str], pool: dict) -> list[tuple[int, list[int]]]:
    """사실마다 그 내용 낱말이 설명에 있는 사진 — 시그니처를 '사진이 넉넉한 사실'에서 고르게 돕는 힌트(0원 · 확정은 비전 확인)."""
    out = []
    for i, f in enumerate(facts, 1):
        ft = _tokens(_body(f))
        ks = [k for k, p in pool.items() if ft and _overlap(ft, _tokens(f"{p.get('description') or ''} {p.get('src_alt') or ''}"))]
        if ks:
            out.append((i, ks[:8]))
    return sorted(out, key=lambda x: -len(x[1]))


def subject_candidates(js: dict, pool: dict, cap: int = 6) -> list[int]:
    """사진 확인 후보 = 모델이 고른 사진 + 설명에 시그니처 낱말이 있는 다른 사진(겹침 많은 순). 모델이 1장만 적어도 더 찾아본다(stay-run-48)."""
    ks = [k for k in (_int(x) for x in js.get("photos") or []) if k in pool]
    st = {t for t in _tokens(js.get("signature")) | _tokens(js.get("what")) if len(t) >= 2}
    more = sorted((k for k, p in pool.items() if k not in ks and _overlap(st, _tokens(f"{p.get('description') or ''} {p.get('src_alt') or ''}"))),
                  key=lambda k: (-_overlap(st, _tokens(pool[k].get("description"))), -int(pool[k].get("quality") or 0), k))
    return (ks + more)[:cap]


def confirm_subjects(models: dict, js: dict, pool: dict, ks: list[int], cache: dict) -> tuple[list[int], list[dict]]:
    """시그니처가 그 사진의 **주인공**인가(비전 · 사진당 약 1원). 같은 시그니처·사진은 다시 묻지 않는다."""
    confirmed, checks = [], []
    for k in ks:
        key = (str(js.get("signature") or ""), k)
        if key not in cache:
            try:
                r = ms._try_models("vision", models["text"], lambda m: _json_vision(m, CONFIRM_SYSTEM, f"시그니처: {js['signature']} — {js.get('what') or ''}", [Path(pool[k]["path"])]))
            except Exception as e:  # noqa: BLE001
                r = {"subject": False, "share": 0, "evidence": f"확인 실패: {str(e)[:60]}"}
            try:
                share = float(r.get("share") or 0)
            except (TypeError, ValueError):
                share = 0.0
            cache[key] = {"k": k, "subject": r.get("subject"), "share": round(share, 2), "ok": r.get("subject") is True and share >= SUBJECT_MIN,
                          "evidence": str(r.get("evidence") or "")[:80]}
        checks.append(cache[key])
        if cache[key]["ok"]:
            confirmed.append(k)
    return confirmed, checks


def fallback_signature(facts: list[str], groups: list[tuple[int, list[int]]], pool: dict, cold: bool = False) -> dict:
    """모델이 3번 모두 쓸 만한 시그니처를 못 내면 **코드가 정한다** — 멈추지 않는다(stay-run-48·49).
    고르는 순서: 숙소 안 시설(인접·셔틀 아님) → 설명이 이어지는 사진(외관 제외 · 겨울엔 바깥 여름 물놀이 제외)이 2장 이상 → 분위기 말 없음 → 사진 많은 것 → 앞 번호."""
    def ok(k):
        return not mt.is_exterior(pool[k]) and not (cold and so.off_season(pool[k]))
    best, key = None, None
    for i, ks in groups:
        ks2 = [k for k in ks if ok(k)]
        if not ks2:
            continue
        f = _body(facts[i - 1])
        kk = (not ADJ_RX.search(f), len(ks2) >= MIN_CUTS, not (MOOD_RX.search(f) or PAST_RX.search(f)), len(ks2), -i)
        if key is None or kk > key:
            best, key = (i, ks2), kk
    if best is None:                                                                # 어느 사실도 사진 설명과 안 이어지면: 첫 사실 + 품질 순 사진
        by_q = sorted(pool, key=lambda k: (-int(pool[k].get("quality") or 0), k))
        best = (1, [k for k in by_q if ok(k)] or by_q)
    i, ks = best
    body = _body(facts[i - 1])
    return {"signature": _cut(body, 24), "what": _cut(body, 40), "fact": i, "vs_peers": "", "why": "",
            "points": [{"role": "신박함", "text": _cut(body, 24), "fact": i}], "photos": ks[:5], "fallback": True}


def pick_photos(pool: dict, groups: list[tuple[int, list[int]]], confirmed: list[int], cands: list[int], n: int, cold: bool = False) -> tuple[list[int], set[int]]:
    """컷 사진(서로 다름) = 시그니처가 주인공으로 확인된 사진(최대 n). 2장이 안 되면 그때만 ② 설명에 시그니처 낱말이 있는 사진
    ③ 어느 사실과든 설명이 이어지는 사진 ④ 품질 높은 사진 ⑤ 외관·전경(1장)으로 2컷을 채운다 —
    사진이 있는데 영상을 못 만드는 일(run-48·49)도, 시그니처와 상관없는 사진을 늘어놓는 일(run-47)도 없게.
    돌려주는 것: (컷 사진 번호, 시그니처와 이어진 사진 번호 = 확인 + 후보)."""
    out: list[int] = []

    def add(ks, upto: int, allow_ext: bool = False, any_season: bool = False):
        for k in ks:
            if len(out) >= upto:
                return
            if k in pool and k not in out and (allow_ext or not mt.is_exterior(pool[k])) and (any_season or not (cold and so.off_season(pool[k]))):
                out.append(k)

    add(confirmed, n, allow_ext=True)                                               # 비전이 주인공으로 확인한 사진은 외관이어도 쓴다(시그니처가 건물 자체일 때)
    add(cands, MIN_CUTS)
    for _, ks in groups:
        add(ks, MIN_CUTS)
    by_q = sorted(pool, key=lambda k: (-int(pool[k].get("quality") or 0), k))
    add(by_q, MIN_CUTS)
    add(by_q, MIN_CUTS, allow_ext=True)
    add(by_q, MIN_CUTS, allow_ext=True, any_season=True)                             # 마지막 수단 — 자막은 그 사진에 보이는 것으로(assign_points)
    return out, set(confirmed) | set(cands)


ROLE_RANK = {"신박함": 0, "차별성": 1, "유인": 2, "정보": 3}


def assign_points(photos_: list[int], points: list[dict], facts: list[str], pool: dict, sig_rel: set[int]) -> list[tuple[int, dict]]:
    """컷마다 전할 정보 하나 — 첫 컷은 신박함(시그니처). 나머지 사진은 **사진 설명과 겹치는 낱말 합이 가장 큰 짝**으로(전부 따져 본다 · 시그니처 정보 먼저).
    겹치는 것이 없으면: 시그니처 사진이면 남은 시그니처 정보, 아니면 그 사진에 실제로 보이는 것(분류 설명) — 사진과 자막이 따로 놀지 않게(run-47).
    짝지은 뒤 둘째 컷부터는 신박함 → 차별성 → 유인 → 정보 순으로 놓는다(이야기 순서)."""
    used_fi = {p["fact_i"] for p in points}
    others = [{"role": "정보", "text": _cut(_body(f), 24), "fact": f, "fact_i": i} for i, f in enumerate(facts, 1) if i not in used_fi]
    cand = list(points) + [c for c in others if not (MOOD_RX.search(c["text"]) or PAST_RX.search(c["text"]) or ADJ_RX.search(c["text"]))]
    dtok = {k: _tokens(f"{pool[k].get('description') or ''} {pool[k].get('src_alt') or ''}") for k in photos_}

    def ov(c, k):
        return _overlap(_tokens(_body(c["fact"])) | _tokens(c["text"]), dtok[k])

    def seen(k):                                                                    # 이 사진과 이어지는 사실이 없다 → 사진에 보이는 것을 그대로(사실 번호 0)
        desc = str(pool[k].get("description") or "").strip() or photos.KO.get(pool[k].get("category"), "")
        return {"role": "정보", "text": _cut(desc, 24), "fact": desc, "fact_i": 0, "photo": True}

    if not photos_:
        return []
    out = {photos_[0]: cand[0] if cand else seen(photos_[0])}                      # 첫 컷 = points[0](신박함)
    rest = list(photos_[1:])
    left = [c for c in cand[1:] if any(ov(c, k) or (k in sig_rel and c in points) for k in rest)]

    def val0(k, j, c):
        o = ov(c, k)
        if o or (k in sig_rel and c in points):
            return o * 10 + (3 if c in points else 0) - j * 0.001                   # 같은 점수면 앞 정보(시그니처 정보) 먼저
        return None
    vals = {(k, id(c)): val0(k, cand.index(c), c) for k in rest for c in left}       # 미리 한 번만 계산(낱말 쪼개기는 느리다)

    def val(k, c):
        return vals[(k, id(c))]
    best = [float("-inf"), []]

    def search(i, taken, acc, picks):                                               # 사진 4장 × 이어진 정보 몇 개 — 전부 따져도 수천 가지
        if i == len(rest):
            if acc > best[0]:
                best[0], best[1] = acc, list(picks)
            return
        for c in left + [None]:
            if c is not None and id(c) in taken:
                continue
            v = 0.0 if c is None else val(rest[i], c)
            if v is None:
                continue
            if c is not None:
                taken.add(id(c))
            picks.append(c)
            search(i + 1, taken, acc + v, picks)
            picks.pop()
            if c is not None:
                taken.discard(id(c))
    search(0, set(), 0.0, [])
    for k, c in zip(rest, best[1]):
        out[k] = c if c is not None else seen(k)
    tail = sorted(photos_[1:], key=lambda k: (ROLE_RANK.get(out[k]["role"], 3), photos_.index(k)))
    return [(k, out[k]) for k in [photos_[0]] + tail]


def choose_signature(models: dict, h: dict, req: dict, report: dict) -> dict:
    """시그니처 고르기(모델 최대 3번 · 빈 답·규칙 위반은 이유를 붙여 다시) → 못 고르면 코드가 정한다 → 주인공 사진 확인 → 컷 사진·정보 짝짓기.
    **쓸 사진이 2장 이상이고 사실이 1개 이상이면 반드시 영상을 만든다** — 멈추는 것은 재료 자체가 없을 때뿐.
    stay-run-48·49: '완벽한 시그니처' 관문(다른 후보와 다름·주인공 사진 2장·사실 2개…)을 못 넘으면 영상을 안 만들게 짜서 두 번 연속 실패했다
    → 관문은 '우선순위'로만 쓴다(통과한 답이 있으면 그것, 없으면 코드가 정한 것)."""
    fmt = _fmt(req)
    cold = so.cold_month(req)
    facts = facts_list(h)
    pool = {int(p["k"]): p for p in usable_photos(h)}
    if len(pool) < MIN_CUTS:                                                        # 품질 5 이상이 모자라면 9컷 형식 기준(품질 3 이상)으로 한 번 더
        loose = {int(p["k"]): p for p in usable_photos(h, 3)}
        if len(loose) > len(pool):
            log(f"품질 5 이상 사진 {len(pool)}장 → 품질 3 이상으로 다시 봄: {len(loose)}장")
            report["sig_pool_relaxed"] = True
            pool = loose
    pc = h.get("photo_counts") or {}
    report["sig_pool"] = {"usable": len(pool), "exterior": sum(1 for p in pool.values() if mt.is_exterior(p)), "facts": len(facts),
                          "official": pc.get("official", 0), "coupang": pc.get("coupang", 0)}
    if len(pool) < MIN_CUTS or not facts:                                           # 재료 자체가 없을 때만 멈춘다(run-47 롯데: 외관 5장 → 1장만 셈)
        why = (f"사진 부족 — 쓸 수 있는 사진 {len(pool)}장(외관·전경은 1장만 셈 · 공식 홈페이지 {pc.get('official', 0)}장 · 쿠팡 {pc.get('coupang', 0)}장)"
               if len(pool) < MIN_CUTS else "사실 부족 — 근거 사실 0개")
        block(h, req, why)
        raise RuntimeError(f"시그니처 영상 불가 — {why} (만들지 않음)")
    peers = peer_lines(req, h)
    groups = fact_groups(facts, pool)
    content = (f"숙소: {h['name']} ({h.get('city') or ''}) · 테마: {req.get('theme')} · 시기: {req.get('month')}\n\n"
               "같은 테마 다른 후보(이들과 겹치는 것은 피한다):\n" + ("\n".join(f"- {x}" for x in peers) or "- (목록 없음)")
               + "\n\n사실(번호):\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1))
               + "\n\n사진:\n" + "\n".join(_photo_line(p) for p in pool.values()))
    if groups:
        content += "\n\n사실별로 그 내용이 보이는 사진(설명 낱말 기준 · 참고):\n" + "\n".join(f"- 사실 {i} → 사진 {', '.join(map(str, ks))}" for i, ks in groups)
    report["sig_groups"] = [{"fact": i, "photos": ks} for i, ks in groups]
    fb, js, tries = "", None, []
    for attempt in range(3):
        try:
            cand = _ask(models, SIG_SYSTEM, content + fb, 0.3)
        except RuntimeError as e:
            tries.append({"signature": "", "errs": [f"호출 실패: {str(e)[:80]}"]})
            continue
        name = str(cand.get("signature") or "").strip()
        if not name:
            many = [f"사실 {i}(사진 {', '.join(map(str, ks))})" for i, ks in groups if len(ks) >= MIN_CUTS] or ["위 사진 목록에서 같은 시설이 2장 이상 보이는 것"]
            errs = [f"빈 답은 받지 않는다 — 사진이 {MIN_CUTS}장 이상인 것 중 이 숙소에서 가장 의외인 것을 시그니처로: {', '.join(many[:6])}"]
        else:
            errs = sig_errs(cand, facts, pool, h, req, peers if attempt < 2 else None)  # 마지막 시도는 '다른 후보 공통점'을 따지지 않는다(영상을 못 만드는 것보다 낫다)
        tries.append({"signature": name, "errs": errs})
        if not errs:
            js = cand
            break
        log(f"시그니처 다시({attempt + 1}): {errs[:3]}")
        fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs[:8])
    report["signature_tries"] = tries
    if js is None:
        js = fallback_signature(facts, groups, pool, cold)
        report["signature_fallback"] = True
        log(f"시그니처를 모델이 못 골라 코드가 정함: {js['signature']} (사실 {js['fact']} · 사진 {js['photos']})")
    points, dropped = check_points(js, facts)
    if not points or points[0]["role"] != "신박함":
        fi0 = _int(js.get("fact")) or 1
        points = [{"role": "신박함", "text": _cut(_body(facts[fi0 - 1]), 24), "fact": facts[fi0 - 1], "fact_i": fi0}] + [p for p in points if p["fact_i"] != fi0]
    cands = subject_candidates(js, pool)
    confirmed, checks = confirm_subjects(models, js, pool, cands, {})
    report["signature_checks"] = checks
    photos_, sig_rel = pick_photos(pool, groups, confirmed, cands, N_SHOTS[fmt], cold)
    pairs = assign_points(photos_, points, facts, pool, sig_rel)
    if len(pairs) < MIN_CUTS:                                                       # pick_photos 가 쓸 사진 2장 이상이면 늘 2장을 채운다 — 여기 오면 코드 잘못
        raise RuntimeError(f"시그니처 영상 불가 — 컷 {len(pairs)}개(쓸 사진 {len(pool)}장인데 채우지 못함 · 코드 확인 필요)")
    fi = _int(js["fact"]) or points[0]["fact_i"]
    in_video = [p for _, p in pairs]
    sig = {"name": str(js["signature"]).strip(), "what": str(js.get("what") or "").strip(), "fact": facts[fi - 1], "fact_i": fi,
           "vs_peers": str(js.get("vs_peers") or "").strip()[:80], "peers": len(peers), "points": in_video + [p for p in points if p not in in_video],
           "dropped_points": dropped, "photos": [k for k, _ in pairs], "confirmed": confirmed, "surprise": js.get("surprise"),
           "why": str(js.get("why") or "")[:80], "alternatives": js.get("alternatives") or [], "checks": checks, "fallback": bool(js.get("fallback")),
           "pairs": [{"k": k, "fact_i": p["fact_i"], "fact": p["fact"], "role": p["role"], "text": p["text"], "photo": bool(p.get("photo"))} for k, p in pairs]}
    log(f"시그니처: {sig['name']} — 근거 '{_body(sig['fact'])[:40]}' · 컷 사진 {sig['photos']}(주인공 확인 {confirmed}) · 비교 후보 {len(peers)}곳"
        + (" · 코드가 정함" if sig["fallback"] else ""))
    return sig


# ── 3. 컷 계획 ──────────────────────────────────────────────────────────────────────────
def plan_cuts(sig: dict, h: dict, req: dict, report: dict) -> list[dict]:
    """컷 = 사진(서로 다름) × 그 사진 설명과 맞는 정보 하나(choose_signature 의 pairs). 원본 사진 그대로 → 렌더에서 컷마다 AI 영상(Veo)으로 움직인다."""
    by_k = {int(p["k"]): p for p in h.get("classified") or []}                    # 품질 3 이상으로 넓혀 고른 사진도 찾게(usable_photos 가 아니라 전체에서)
    facts = facts_list(h)
    shots = []
    for j, pr in enumerate(sig["pairs"]):
        k = int(pr["k"])
        p = by_k[k]
        fi = int(pr.get("fact_i") or 0)
        role = "신박함" if j == 0 else (pr["role"] if pr["role"] in ROLES else "정보")
        shots.append({"i": j + 1, "k": k, "role": role, "point": pr["text"], "fact": pr.get("fact") or (facts[fi - 1] if fi else ""), "fact_i": fi,
                      "photo_text": bool(pr.get("photo")), "variant": "original", "people": "none", "pose": "", "place": "",
                      "source": p.get("source"), "src_url": p.get("src_url"), "category": p.get("category"), "view": p.get("view"),
                      "description": p.get("description") or "", "veo_prompt": p.get("veo_prompt") or "", "path": p["path"],
                      "focus_x": p.get("focus_x", 0.5), "focus_y": p.get("focus_y", 0.5)})
    report["plan"] = [{k: s[k] for k in ("i", "k", "role", "point", "fact_i", "photo_text", "source", "description")} for s in shots]
    log("컷 계획: " + " · ".join(f"{s['i']}:사진{s['k']}/{s['role']}{'(사진 설명)' if s['photo_text'] else ''}" for s in shots))
    return shots


# ── 4. 이미지 편집 + 검수 ────────────────────────────────────────────────────────────────
def edit_prompt(s: dict, retry_note: str = "") -> str:
    p = EDIT_KEEP + "CHANGE ONLY: " + (VARIANTS[s["variant"]] or "nothing about the light or weather.") + " "
    if s["people"] != "none":
        p += EDIT_PEOPLE.format(who=PEOPLE[s["people"]], pose=POSES.get(s["pose"], POSES["sit"]), place=s["place"] or "a natural spot")
    else:
        p += EDIT_NO_PEOPLE
    if retry_note:
        p += f"IMPORTANT: the previous attempt was rejected because: {retry_note}. Keep everything else identical. "
    return p + EDIT_TAIL


def _fake_edit(base: Path, s: dict, out: Path) -> Path:
    im = Image.open(base).convert("RGB")
    tint = {"golden": (255, 170, 90), "dusk": (70, 90, 170), "night": (20, 30, 70), "rain": (120, 130, 140), "snow": (235, 240, 250),
            "mist": (210, 215, 225), "steam": (240, 240, 240), "original": (255, 255, 255)}[s["variant"]]
    over = Image.new("RGB", im.size, tint)
    im = Image.blend(im, over, 0.35 if s["variant"] != "original" else 0.0)
    if s["people"] != "none":
        d = ImageDraw.Draw(im)
        w, hh = im.size
        d.ellipse((int(w * 0.42), int(hh * 0.62), int(w * 0.52), int(hh * 0.68)), fill=(40, 30, 25))
    im.save(out, "PNG")
    return out


def edit_image(base: Path, prompt: str, out: Path, s: dict, rep: dict) -> Path:
    """사진 1장 편집(돈). 한 번 실행·한 달 한도를 **돈 쓰기 전에** 본다(make_mini.composite 와 같은 규칙). 장부 kind image."""
    if FAKE_IMG:
        rep["image_model"] = "FAKE"
        return _fake_edit(base, s, out)
    models = rep.get("image_models") or make_mini.image_models(rep.get("image_prefer"))
    rep["image_models"] = models                                           # 모델 목록은 한 번만 묻는다
    parts = [{"text": prompt}, {"text": "Attached image: the HOTEL PHOTOGRAPH to edit."},
             {"inline_data": {"mime_type": "image/jpeg", "data": _b64(base, 1536)}}]
    last = None
    for model in models:
        krw = make_mini.image_krw(model)
        used = veo.month_total("all")
        if used + krw > veo.MONTH_KRW:
            raise RuntimeError(f"이번 달 한도({veo.MONTH_KRW:,.0f}원) — 지금 {used:,.0f}원")
        if veo._state["spent"] + krw > veo.RUN_KRW:
            raise RuntimeError(f"한 번 실행 한도({veo.RUN_KRW:,.0f}원) — 여기까지 {veo._state['spent']:,.0f}원")
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"], "imageConfig": {"aspectRatio": "9:16"}}}
        try:
            data = make_mini._post(f"models/{model}:generateContent", body)
        except RuntimeError as e:
            last = e
            if any(c in str(e) for c in ("HTTP 404", "HTTP 403")) or ("HTTP 400" in str(e) and "imageConfig" in str(e)):
                log(f"이미지 모델 {model} 사용 불가 → 다음: {str(e)[:120]}")
                continue
            raise
        veo.record_est("image", krw, f"{model} 시그니처 변주 {out.name} (추정)")
        veo._state["spent"] += krw
        rep["image_krw"] = rep.get("image_krw", 0) + round(krw)
        rep["image_model"] = model
        img = None
        for c in data.get("candidates") or []:
            for p in (c.get("content") or {}).get("parts") or []:
                d = p.get("inlineData") or p.get("inline_data")
                if d and str(d.get("mimeType") or d.get("mime_type") or "").startswith("image/"):
                    img = base64.b64decode(d["data"])
        if img:
            out.write_bytes(img)
            im = design.cover(Image.open(out).convert("RGB"), ms.W, ms.H)    # 9:16 1080×1920 로 맞춘다(가운데 기준)
            im.save(out, "PNG")
            return out
        last = RuntimeError(f"이미지 없음 (finish {[c.get('finishReason') for c in data.get('candidates') or []]})")
        log(f"편집 결과에 이미지가 없음: {str(last)[:120]}")
    raise RuntimeError(f"편집 실패: {last}")


def edge_keep(a: Path, b: Path) -> float:
    """원본의 윤곽선이 변주에서 얼마나 남았나(0~1) — 0원. 시간·날씨만 바뀌면 높고, 건물·물가를 다시 그리면 떨어진다. 기록용(문턱 미정 — 실측으로 정한다)."""
    def edges(p: Path):
        g = Image.open(p).convert("L").resize((270, 480), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.2))
        e = g.filter(ImageFilter.FIND_EDGES)
        px = sorted(e.getdata())
        thr = px[int(len(px) * 0.85)] if px else 0
        return e.point(lambda v: 255 if v > max(thr, 12) else 0)
    ea, eb = edges(a), edges(b).filter(ImageFilter.MaxFilter(5))
    pa, pb = ea.load(), eb.load()
    w, hh = ea.size
    tot = sum(1 for y in range(hh) for x in range(w) if pa[x, y])
    if not tot:
        return 1.0
    hit = sum(1 for y in range(hh) for x in range(w) if pa[x, y] and pb[x, y])
    return round(hit / tot, 3)


VERIFY_SYSTEM = """너는 숙소 사진 변주 검수자다. 사진 2장: 사진 1 = 실제 숙소 원본, 사진 2 = AI 가 빛·날씨·사람만 바꿨어야 하는 변주.
**같은 장소·같은 구조인지 엄격하게** 본다. 빛·하늘색·빗줄기·눈·김·안개·물에 비친 빛, 그리고 요청한 사람은 허용한다.
- structure_changes: 건물·벽·창·지붕·수영장/탕 모양·물가·데크·난간·가구·식물·전망(바다·산) 방향과 위치 중 원본과 달라진 것
- added_objects: 원본에 없던 사물·시설·가구·조명기구·물·수영장·장식·글자·로고(요청한 사람·빗줄기·눈·김 제외)
- people: 사람 수, face_visible: 얼굴(눈·코·입)이 또렷이 보이는 사람이 있는가
- variant_visible: 요청한 변주가 실제로 보이는가
JSON 만: {"same_place":true/false,"structure_changes":["..."],"added_objects":["..."],"people":0,"face_visible":false,"text_or_logo":false,"variant_visible":true/false,"verdict":"ok"|"fail","reason":"한 줄"}"""


def verify(models: dict, base: Path, var: Path, s: dict) -> dict:
    want = f"요청한 변주: {VARIANT_KO[s['variant']]}" + (f" · 뒷모습 사람 {PEOPLE_KO[s['people']]}({POSE_KO.get(s['pose'], '')})" if s["people"] != "none" else " · 사람 없음")
    try:
        r = ms._try_models("vision", models["text"], lambda m: _json_vision(m, VERIFY_SYSTEM, want, [base, var]))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"검수 호출 실패: {str(e)[:80]}"}
    n_people = int(r.get("people") or 0) if str(r.get("people") or "0").isdigit() else 0
    want_people = s["people"] != "none"
    probs = []
    if r.get("verdict") != "ok" or r.get("same_place") is not True:
        probs.append(str(r.get("reason") or "같은 장소가 아님"))
    if r.get("structure_changes"):
        probs.append("구조 변경: " + ", ".join(map(str, r["structure_changes"]))[:120])
    if r.get("added_objects"):
        probs.append("새 사물: " + ", ".join(map(str, r["added_objects"]))[:120])
    if r.get("text_or_logo"):
        probs.append("글자·로고")
    if s["variant"] != "original" and r.get("variant_visible") is not True:
        probs.append(f"'{VARIANT_KO[s['variant']]}'이(가) 안 보임")
    if want_people and not (1 <= n_people <= 3):
        probs.append(f"사람 수 {n_people}")
    if not want_people and n_people:
        probs.append(f"사람이 생김({n_people})")
    if r.get("face_visible"):
        probs.append("얼굴이 보임")
    return {"ok": not probs, "reason": "; ".join(probs)[:240], "raw": {k: r.get(k) for k in ("same_place", "structure_changes", "added_objects", "people", "face_visible", "variant_visible", "reason")}}


def make_images(models: dict, shots: list[dict], report: dict) -> None:
    """컷마다 9:16 원본 크롭(src_<k>.png) → 필요한 컷만 편집(var_<i>.png) + 검수. 두 번 실패하면 원본으로(variant original · people none)."""
    SIG.mkdir(parents=True, exist_ok=True)
    rep = {"image_prefer": None}
    rows, tries = [], 0
    for s in shots:
        src = SIG / f"src_{s['k']}.png"
        if not src.exists():
            photos.crop_9x16(s["path"], src, s["focus_x"], s["focus_y"], ms.W, ms.H)
        s["src_img"] = src.name
        if s["variant"] == "original" and s["people"] == "none":
            s["img"], s["verify"] = src.name, {"ok": True, "reason": "원본"}
            rows.append({"i": s["i"], "variant": "original", "ok": True}); continue
        out = SIG / f"var_{s['i']}.png"
        note, res = "", None
        for attempt in range(2):
            if tries >= EDIT_TRIES:
                res = {"ok": False, "reason": f"이번 실행 편집 호출 상한({EDIT_TRIES}번) — 원본으로"}
                break
            tries += 1
            try:
                edit_image(src, edit_prompt(s, note), out, s, rep)
            except RuntimeError as e:
                res = {"ok": False, "reason": f"편집 실패: {str(e)[:120]}"}
                if "한도" in str(e):
                    break
                continue
            res = verify(models, src, out, s)
            res["edge_keep"] = edge_keep(src, out)
            if res["ok"]:
                break
            note = res["reason"]
            log(f"컷 {s['i']} 변주 검수 탈락({attempt + 1}): {res['reason'][:120]}")
        if res and res.get("ok"):
            s["img"], s["verify"] = out.name, res
        else:
            s["fallback"] = f"{VARIANT_KO[s['variant']]}{'·' + PEOPLE_KO[s['people']] if s['people'] != 'none' else ''} → 원본 ({(res or {}).get('reason', '')[:80]})"
            log(f"컷 {s['i']} 변주 포기 → 원본 사진: {s['fallback']}")
            s.update({"variant": "original", "people": "none", "pose": "", "place": "", "img": src.name, "verify": res or {"ok": False}})
        rows.append({"i": s["i"], "variant": s["variant"], "people": s["people"], "ok": bool((s.get("verify") or {}).get("ok")),
                     "edge_keep": (s.get("verify") or {}).get("edge_keep"), "fallback": s.get("fallback")})
    report["images"] = {"rows": rows, "image_krw": rep.get("image_krw", 0), "image_model": rep.get("image_model"), "edit_calls": tries}


# ── 5. 문구 ─────────────────────────────────────────────────────────────────────────────
TEXT_SYSTEM = """너는 숙소 쇼츠 카피라이터다. 영상은 음악만 깔리고 컷마다 자막 한 줄이 뜬다(나레이션 없음).
목표: 시청자가 화면 글자만 보고 "여기엔 ○○이 있고, ○○라서 다른 데와 다르고, 가면 ○○를 할 수 있다"를 알게 한다.
컷마다 '전할 정보'(역할 · 근거 사실)가 정해져 있다. 그 정보를 짧은 자막으로 옮긴다. 분위기·감성 묘사는 쓰지 않는다.
절대 규칙:
- 자막 하나 = 정보 하나. 그 컷 근거 사실의 구체적인 낱말(시설 이름·형태·위치·방식·숫자)을 반드시 넣는다. 앞 컷과 같은 말 반복 금지.
- 금지: 사실 없는 분위기 말(노을빛·물들고·푸른·힐링·낭만·감성·설렘·여유로운·아늑·포근·그림 같은·꿈 같은·인생샷·완벽한·행복·추억),
  1인칭·체험·과거형("다녀왔어요", "좋았어요", "-더라고요", "저는", "우리"), 숙소 이름, 가격 숫자, "최고·유일·최저가·무조건".
- 자막은 띄어쓰기 포함 4~14자 한 줄. 끝은 명사나 '~해요'('~니다' 금지).
- hook_title: 첫 컷 위쪽에 크게 뜨는 제목 = 시그니처의 신박함을 묻는 질문(입력 '훅 제목 유형'으로). 시그니처를 가리키는 낱말을 넣고 핵심 낱말 하나만 [대괄호].
  공백 제외 6~14자(8~12 권장), 한 줄은 띄어쓰기 단위로 약 7자, 물음표로 끝, 숙소·지역 이름·가격·마침표·느낌표 금지, 자막을 그대로 옮기지 않는다.
- caption: hook(첫 줄 — 시그니처가 무엇이고 왜 의외인지 한 문장, 사실 그대로) · points(차별성·유인 정보 1~3줄, 사실 그대로) · save(저장 권유 한 줄, 시기와 연결).
  공감·감성 문장 금지.
- checklist: 사실 목록의 번호를 골라 짧게 옮긴 체크 항목 2~4개(가격·과장 금지, 사실에 없는 내용 추가 금지).
- title: 유튜브 제목 12~28자(숙소 이름 포함 — 제목·캡션은 텍스트라 이름을 쓴다). hashtags 5개.
JSON 만: {"phrases":["..."],"hook_title":"...","caption":{"hook":"...","points":["..."],"save":"..."},
 "checklist":[{"fact":번호,"text":"..."}],"title":"...","hashtags":["#..."]}"""

SIG_TITLE_SYSTEM = """너는 숙소 쇼츠 훅 제목 작가다. 이 숙소 시그니처의 신박함을 묻는 질문 제목 후보 5개를 쓴다.
규칙: 공백 제외 6~14자(8~12 권장), 한 줄은 띄어쓰기 단위로 약 7자(두 줄 안), 시그니처를 가리키는 낱말 필수, 핵심 낱말 하나만 [대괄호], 물음표로 끝,
숙소·지역 이름·가격·마침표·느낌표·이모지·분위기 말 금지, 자막을 그대로 옮기지 않는다, 최근 제목을 다시 쓰지 않는다.
유형 ① 반전 질문(상식과 어긋남): 예 "한겨울에 [노천 스파]가?" ② 의외 사실: 예 "산속에 [스핑크스]가 있다?" — 입력의 유형으로.
JSON 만: {"titles":["...","...","...","...","..."]}"""

INFO_SYSTEM = """너는 이 숙소를 처음 보는 시청자다. 아래는 숙소 쇼츠 영상 화면에 뜨는 글자 전부다(훅 제목 + 컷 자막).
이 글자만 보고 알 수 있는 '이 숙소의 특별한 점'을 최대 3개, 각각 짧게 적는다. 글자에 없는 내용은 추측하지 않는다. 알 수 없으면 빈 목록.
JSON 만: {"special":["..."]}"""


def phrase_errs(ph: list, shots: list[dict], sig: dict, h: dict, req: dict, facts: list[str]) -> list[str]:
    errs = []
    if len(ph) != len(shots):
        return [f"phrases {len(ph)}개 — 컷 수 {len(shots)}개와 같게"]
    toks = so.name_tokens(h["name"], req, h)
    corpus = " ".join(facts)
    prev = []
    for i, (t, s) in enumerate(zip(ph, shots), 1):
        t = design.one_line(t)
        L = len(t)
        if not (3 <= L <= 15):
            errs.append(f"자막 {i} '{t}' {L}자 — 4~14자")
        elif not design.fits(t, "subtitle")[0]:
            errs.append(f"자막 {i} '{t}' 이 자막 한 줄에 안 들어감 — 줄인다")
        mood = MOOD_RX.search(t)
        if mood:
            errs.append(f"자막 {i} '{t}' 분위기 말 '{mood.group(0)}' — 사실 낱말로")
        if not _overlap(_tokens(t), _tokens(_body(s["fact"]))):
            errs.append(f"자막 {i} '{t}' 에 근거 사실 낱말이 없음 — 이 컷 정보: '{s['point']}' (사실: {_body(s['fact'])[:30]})")
        flat = re.sub(r"\s", "", t)
        if any(SequenceMatcher(None, flat, q).ratio() >= 0.8 for q in prev):
            errs.append(f"자막 {i} '{t}' 이 앞 컷과 같은 말 — 컷마다 다른 정보")
        prev.append(flat)
        if PAST_RX.search(t) or FIRST_RX.search(t):
            errs.append(f"자막 {i} '{t}' 1인칭·체험·과거형 금지")
        if so.ENDING_RX.search(t):
            errs.append(f"자막 {i} '~니다' — '~해요'체로")
        if any(k in t for k in toks):
            errs.append(f"자막 {i} 숙소 이름 금지")
        if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", t):
            errs.append(f"자막 {i} 가격 숫자 금지")
        for d in DIGIT_RX.findall(t):
            if d not in corpus:
                errs.append(f"자막 {i} 숫자 '{d}' 는 사실 목록에 없음"); break
        for b in list(ms.BANNED) + list(mt.WORDING_BAN):
            if b in t:
                errs.append(f"자막 {i} 금지 표현 '{b}'"); break
        if so.cold_month(req) and so.SUMMER_TALK_RX.search(t):
            errs.append(f"자막 {i} 겨울 편에 여름 해변 시설")
        allow = f"{s['description']} {s['fact']} {sig['fact']}"
        bad = [x for x in photos.facility_terms(t) if not photos.term_ok(x, allow)]
        if bad:
            errs.append(f"자막 {i} 시설 이름 '{'/'.join(bad)}' 는 이 컷 사진·근거 사실에서 확인 안 됨")
        if i == 1 and ADJ_RX.search(_body(sig["fact"])) and not ADJ_RX.search(t):
            errs.append(f"자막 1 '{t}' — 시그니처가 숙소 밖 시설이라 '바로 옆' 같은 위치를 넣는다(숙소 안 시설처럼 보이면 안 된다)")
    return errs


def caption_errs(cap: dict, h: dict, req: dict, sig: dict, facts: list[str]) -> list[str]:
    errs = []
    hook, save = str(cap.get("hook") or ""), str(cap.get("save") or "")
    pts = [str(x or "") for x in (cap.get("points") or [])] if isinstance(cap.get("points"), list) else []
    if not hook.strip():
        errs.append("caption.hook(첫 줄) 없음")
    if not [t for t in pts if t.strip()]:
        errs.append("caption.points(차별성·유인 1~3줄) 없음")
    if not save.strip():
        errs.append("caption.save 없음")
    ftoks = set()
    for f in facts:
        ftoks |= _tokens(_body(f))
    if hook.strip() and not _overlap(_tokens(hook), _tokens(sig["name"]) | _tokens(_body(sig["fact"]))):
        errs.append(f"caption.hook '{hook[:24]}' 에 시그니처가 없음 — 첫 줄은 시그니처가 무엇이고 왜 의외인지")
    for t in pts:
        if t.strip() and not _overlap(_tokens(t), ftoks):
            errs.append(f"caption.points '{t[:24]}' 에 사실 낱말이 없음 — 사실 그대로")
    allow = " ".join(facts) + " " + sig["fact"]
    for t in [hook, *pts, save]:
        if not t.strip():
            continue
        mood = MOOD_RX.search(t)
        if mood:
            errs.append(f"caption '{t[:20]}' 분위기 말 '{mood.group(0)}' — 사실로")
        if PAST_RX.search(t) or FIRST_RX.search(t):
            errs.append(f"caption '{t[:20]}' 1인칭·체험·과거형")
        if re.search(r"\d[\d,]*\s*(원|만원|만 원|%)", t):
            errs.append(f"caption '{t[:20]}' 가격 숫자")
        bad = [x for x in photos.facility_terms(t) if not photos.term_ok(x, allow)]
        if bad:
            errs.append(f"caption 시설 이름 '{'/'.join(bad)}' 는 사실에 없음")
        for b in ms.BANNED:
            if b in t:
                errs.append(f"caption 금지 표현 '{b}'"); break
    return errs


def grounded_checklist(items: list, facts: list[str], h: dict) -> list[str]:
    """체크 항목은 사실 번호에 묶는다. 옮긴 글이 원문과 낱말이 절반도 안 겹치거나 원문에 없는 숫자가 있으면 원문 그대로 쓴다."""
    out = []
    for it in items or []:
        fi = _int(it.get("fact")) if isinstance(it, dict) else None
        if fi is None or not (1 <= fi <= len(facts)):
            continue
        src = facts[fi - 1]
        txt = design.one_line(str(it.get("text") or ""))[:40]
        ta, tb = _tokens(txt), _tokens(src)
        if not txt or not ta or _overlap(ta, tb) / len(ta) < 0.5 or any(d not in src for d in DIGIT_RX.findall(txt)) or PAST_RX.search(txt):
            txt = _body(src)[:40]
        if txt not in out:
            out.append(txt)
    band = make_folder.price_band(h["name"])
    if band:
        out.append(f"1박 {band}")
    if h.get("honest"):
        out.append(f"후기 속 아쉬움: {h['honest']}")
    return out[:6]


def sig_title_errs(title: str, ph: list, shots: list[dict], sig: dict, h: dict, req: dict) -> list[str]:
    """기존 훅 제목 규칙(make_solo.hook_title_errs) + 시그니처 낱말 필수(신박함을 묻는다) + 분위기 말 금지."""
    cut = {"i": 1, "shot": {"description": f"{shots[0]['description']} {sig['fact']}"}}
    errs = so.hook_title_errs(title, " ".join(ph), h, req, cut)
    t = design.plain(design.one_line(title)) if title else ""
    if t and not _overlap(_tokens(t), _tokens(sig["name"]) | _tokens(sig["what"]) | _tokens(_body(sig["fact"]))):
        errs.append(f"hook_title '{title}' 에 시그니처 낱말이 없음 — 시그니처의 신박함을 묻는다")
    if t and MOOD_RX.search(t):
        errs.append("hook_title 분위기 말 금지")
    return errs


def ensure_sig_title(models: dict, title: str, ph: list, shots: list[dict], sig: dict, h: dict, req: dict, ttype: str, report: dict) -> str:
    """훅 제목만 틀리면 제목 후보만 다시 받는다(텍스트 1~2번 · 몇 원). 그래도 안 되면 제목 없이(미리보기 문서에 표시)."""
    errs = sig_title_errs(title, ph, shots, sig, h, req)
    if not errs:
        return title
    log("훅 제목 다시 쓰기:", errs[:2])
    content = (f"유형: {ttype} — {so.TITLE_TYPES[ttype]}\n시그니처: {sig['name']} — {sig['what']}\n왜 의외: {sig['why']}\n"
               f"자막(그대로 옮기지 말 것): {' / '.join(ph)}\n테마: {req.get('theme')} · 시기: {req.get('month')}\n"
               f"최근 제목(다시 쓰지 말 것): {' / '.join(so.recent_titles()) or '없음'}")
    for _ in range(2):
        try:
            r = _ask(models, SIG_TITLE_SYSTEM, content + ("\n\n직전 후보의 문제: " + " / ".join(errs[:4]) if errs else ""), 0.8)
        except RuntimeError as e:
            log(f"훅 제목 호출 실패: {str(e)[:80]}"); continue
        for t in r.get("titles") or []:
            t = design.one_line(str(t))
            try:
                e2 = sig_title_errs(t, ph, shots, sig, h, req)
            except Exception as e:  # noqa: BLE001                               # 후보 하나가 이상해도 실행을 멈추지 않는다
                e2 = [f"hook_title 검사 오류 {str(e)[:40]}"]
            if not e2:
                log(f"훅 제목: {t}")
                return t
            errs = e2
    report["hook_title_missing"] = errs[:3]
    log("훅 제목 후보가 모두 규칙에 걸림 → 제목 없이(아래 자막만). 미리보기에서 확인")
    return ""


def info_test(models: dict, ph: list, title: str, shots: list[dict]) -> dict:
    """정보 전달 시험(약 1원): 화면 글자(훅 제목 + 자막)만 보고 '특별한 점'을 말하게 해, 컷마다 전할 사실과 몇 개가 맞는지 센다.
    run-47 처럼 분위기 글자뿐이면 특별한 점을 말할 수 없다 → 미달."""
    screen = (f"훅 제목: {design.plain(title)}\n" if title else "") + "\n".join(f"자막 {j}: {p}" for j, p in enumerate(ph, 1))
    try:
        r = _ask(models, INFO_SYSTEM, screen, 0.0)
    except RuntimeError as e:
        return {"ok": True, "special": [], "matched": 0, "need": 0, "note": f"시험 호출 실패 — 건너뜀: {str(e)[:60]}"}
    items = [design.one_line(str(x)) for x in (r.get("special") or []) if str(x).strip()][:3]
    srcs = [_tokens(_body(s["fact"])) | _tokens(s["point"]) for s in shots]
    hit = {j for it in items for j, st in enumerate(srcs) if _overlap(_tokens(it), st)}
    need = min(2, len(shots))
    return {"ok": len(hit) >= need, "special": items, "matched": len(hit), "need": need}


def fallback_phrase(s: dict) -> str:
    """자막 대체(규칙에 3번 걸린 줄만 · v3): 그 컷 정보(사실 문장 또는 사진에 보이는 것)를 띄어쓰기 단위로 14자 안, 자막 한 줄에 들어가게."""
    t = _cut(re.sub(r"[.!?。]+$", "", str(s.get("point") or _body(s.get("fact")) or "")), 14)
    while t and not design.fits(t, "subtitle")[0]:
        t = _cut(t, len(t) - 1)
    return t


def default_tags(req: dict) -> list[str]:
    tags = ["#" + re.sub(r"[^가-힣A-Za-z0-9]", "", str(x)) for x in (req.get("theme"), req.get("region"))]
    return [t for t in tags if len(t) > 1] + ["#숙소추천", "#국내여행", "#호캉스"]


def text_fallback(models: dict, js: dict, ph: list, errs: list, shots: list[dict], sig: dict, h: dict, req: dict, facts: list[str], ttype: str,
                  report: dict) -> tuple[dict, list, str, dict]:
    """문구가 규칙을 3번 못 지켰을 때 — **걸린 자막 줄만** 그 컷 정보 문장으로 바꾸고, 캡션이 걸렸으면 사실 문장으로 만든다. 멈추지 않는다(v3).
    바꾼 줄·남은 문제는 report.text_fallback 과 미리보기 문서 '자동 대체'에 남긴다."""
    report["text_fallback"] = [str(e)[:120] for e in errs[:6]]
    log(f"문구가 규칙을 3번 못 지킴 → 걸린 줄만 사실 문장으로 바꿔 계속: {errs[:3]}")
    ph = [design.one_line(str(x)) for x in ph] if len(ph) == len(shots) else [""] * len(shots)
    bad = {int(m.group(1)) for e in errs for m in [re.match(r"자막 (\d+) ", str(e))] if m}
    if any(str(e).startswith("phrases ") for e in errs) or not any(ph):
        bad = set(range(1, len(shots) + 1))
    for j, s in enumerate(shots, 1):
        if j in bad or not ph[j - 1].strip():
            ph[j - 1] = fallback_phrase(s)
    left = phrase_errs(ph, shots, sig, h, req, facts)
    if left:
        report["text_fallback_left"] = left[:6]
        log(f"대체 자막에도 남은 문제(그대로 진행 · 미리보기에서 확인): {left[:3]}")
    cap = js.get("caption") if isinstance(js.get("caption"), dict) else {}
    if caption_errs(cap, h, req, sig, facts):
        pts = ([s["point"] for s in shots[1:] if s.get("fact_i")][:3] or [p["text"] for p in sig.get("points", [])[1:4] if p.get("fact_i")]
               or [_cut(_body(sig["fact"]), 40)])
        cap = {"hook": _cut(_body(sig["fact"]), 80), "points": pts, "save": "갈 계획이 있다면 저장해두고 다시 꺼내 보세요."}
    js = {**js, "caption": cap}
    if not js.get("checklist"):
        js["checklist"] = [{"fact": s["fact_i"], "text": ""} for s in shots if s.get("fact_i")]
    title = ensure_sig_title(models, design.one_line(str(js.get("hook_title") or "")), ph, shots, sig, h, req, ttype, report)
    return js, ph, title, info_test(models, ph, title, shots)


def write_text(models: dict, shots: list[dict], sig: dict, h: dict, req: dict, report: dict) -> dict:
    facts = facts_list(h)
    ttype = so.next_title_type()
    extra = sig["points"][len(shots):]
    content = (f"시그니처: {sig['name']} — {sig['what']}\n왜 의외: {sig['why']}\n다른 후보와 다른 점: {sig.get('vs_peers') or '-'}\n"
               f"시기: {req.get('month')} · 테마: {req.get('theme')}\n훅 제목 유형: {ttype} — {so.TITLE_TYPES[ttype]}\n"
               f"최근 제목(다시 쓰지 말 것): {' / '.join(so.recent_titles()) or '없음'}\n"
               f"숙소 이름(제목·캡션용, 자막·훅 제목에는 금지): {h['name']}\n\n컷(순서대로 · 화면 · 전할 정보):\n"
               + "\n".join(f"컷 {s['i']} [{s['role']}] 화면: {s['description']}\n   전할 정보: {s['point']} (근거 사실: {_body(s['fact'])})" for s in shots)
               + ("\n\n영상에 못 넣은 정보(캡션 points 에 쓸 수 있음):\n" + "\n".join(f"- [{p['role']}] {p['text']} (근거: {_body(p['fact'])})" for p in extra) if extra else "")
               + "\n\n사실(번호 — 체크리스트용):\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)))
    fb, js, errs, info, ph, title = "", {}, [], None, [], ""
    for attempt in range(3):
        try:
            js = _ask(models, TEXT_SYSTEM, content + fb, 0.5)
        except RuntimeError as e:
            errs = errs + [f"호출 실패: {str(e)[:100]}"]                                # 지난 답(ph)의 문제는 남긴다 — 대체할 때 걸린 줄을 알아야 한다
            continue
        ph = [design.one_line(str(x)) for x in (js.get("phrases") or [])]
        cap = js.get("caption") if isinstance(js.get("caption"), dict) else {}
        errs = phrase_errs(ph, shots, sig, h, req, facts) + caption_errs(cap, h, req, sig, facts)
        if errs:
            log(f"문구 검사 실패({attempt + 1}): {errs[:4]}")
            fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs[:10])
            continue
        title = ensure_sig_title(models, design.one_line(str(js.get("hook_title") or "")), ph, shots, sig, h, req, ttype, report)
        info = info_test(models, ph, title, shots)
        if not info["ok"] and attempt < 2:                                         # 두 번까지는 다시 쓰고, 마지막은 경고로 남긴다(미리보기 문서·관리실)
            errs = [f"정보 전달 시험 미달 — 화면 글자만 보고 읽힌 특별한 점: {', '.join(info['special']) or '없음'} "
                    f"(전할 사실과 맞음 {info['matched']}/{info['need']}). 자막마다 근거 사실의 구체적인 낱말(시설·형태·위치·방식)을 분명히"]
            log(f"정보 전달 시험 미달({attempt + 1}): {info}")
            fb = "\n\n지난 답의 문제(고쳐서 다시):\n- " + "\n- ".join(errs)
            continue
        break
    else:
        report["text_errs"] = errs
        js, ph, title, info = text_fallback(models, js if isinstance(js, dict) else {}, ph, errs, shots, sig, h, req, facts, ttype, report)
    report["info_test"] = info
    cap = js["caption"]
    name_title = str(js.get("title") or sig["name"])
    if h["name"] not in name_title:
        name_title = f"{h['name']} {name_title}".strip()
    text = {"phrases": ph, "hook_title": title, "hook_title_type": ttype,
            "caption": {"hook": design.one_line(str(cap.get("hook") or "")), "points": [design.one_line(str(x)) for x in cap.get("points") or [] if str(x).strip()][:3],
                        "save": design.one_line(str(cap.get("save") or ""))},
            "checklist": grounded_checklist(js.get("checklist"), facts, h), "title": name_title[:40],
            "hashtags": ([t if str(t).startswith("#") else f"#{t}" for t in (js.get("hashtags") or []) if str(t).strip()] or default_tags(req))[:5], "info_test": info}
    log(f"훅 제목: {text['hook_title']} · 자막: {' / '.join(ph)} · 정보 전달 {info['matched']}/{info['need']}")
    return text


# ── 6. 렌더 ─────────────────────────────────────────────────────────────────────────────
def photo_clip(image: Path, sec: float, out: Path, pattern: str, M: float = MOTION_SIG) -> Path:
    """make_solo.photo_clip 과 같은 가속·감속 무빙, 폭만 짧은 컷에 맞게(기본 12%)."""
    F = max(2, int(round(sec * ms.FPS)))
    t = f"(on/{F})"
    eo = f"(1-pow(1-{t},2))"
    io = f"({t}*{t}*(3-2*{t}))"
    z = {"push": f"1.0+{M}*{eo}", "pull": f"1.0+{M}*(1-{eo})", "pan": f"1.0+{M}*0.8+{M}*0.2*{io}",
         "tilt": f"1.0+{M}*0.8+{M}*0.2*{io}", "diag": f"1.0+{M}*{eo}"}[pattern]
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    x = {"push": cx, "pull": cx, "pan": f"(iw-iw/zoom)*{io}", "tilt": cx, "diag": f"(iw-iw/zoom)*(0.5-0.4*{eo})"}[pattern]
    y = {"push": cy, "pull": cy, "pan": cy, "tilt": f"(ih-ih/zoom)*(1-{io})", "diag": f"(ih-ih/zoom)*(0.5+0.4*{eo})"}[pattern]
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(ms.FPS), "-i", str(image),
            "-vf", f"scale=2160:3840:flags=lanczos,zoompan=z='{z}':x='{x}':y='{y}':d={F}:s=1080x1920:fps={ms.FPS},setsar=1",
            "-frames:v", str(F), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)])
    return out


def veo_clips(shots: list[dict], report: dict, theme: str) -> dict:
    """컷마다 그 실제 사진(9:16 크롭)을 **Veo 4초 AI 영상**으로 — 9컷 형식과 같은 지시문(사진별 카메라·자연 움직임 + 시설·구조 그대로 · photos.prompt_for).
    미리보기에서 만든 클립(find_reuse 가 가져온 veo_<i>.mp4)은 다시 만들지 않는다(0원). 안전 필터는 씨앗을 바꿔 한 번 더,
    한도·그 밖 실패는 그 컷만 사진 무빙(영상은 끝까지 만든다). 한도는 veo.py 가 돈 쓰기 전에 본다(한 번 3,000원 · 한 달 50,000원)."""
    clips, rows, stopped = {}, [], None
    new = [s for s in shots if not (SIG / f"veo_{s['i']}.mp4").exists()]
    log(f"AI 영상(Veo) {len(shots)}컷 — 새로 {len(new)}컷 · 예상 약 {veo.estimate_krw(len(new), VEO_SEC):,.0f}원 · 이번 달 누적 {veo.month_total():,.0f}원")
    for s in shots:
        i, out = s["i"], SIG / f"veo_{s['i']}.mp4"
        row = {"i": i, "k": s["k"], "ok": False, "krw": 0}
        if out.exists() and out.stat().st_size > 0:                                 # 미리보기 클립 재사용(0원)
            clips[i] = out
            row.update({"ok": True, "reused": True})
            rows.append(row)
            continue
        if stopped:
            row["error"] = f"한도: {stopped}"
            rows.append(row)
            continue
        small = SIG / f"veo_in_{i}.png"
        Image.open(SIG / s["img"]).convert("RGB").resize((720, 1280), Image.LANCZOS).save(small, "PNG")
        cat = s.get("category") if s.get("category") in photos.CATS else "special"
        prompt = photos.prompt_for({"veo_prompt": s.get("veo_prompt") or "", "category": cat})
        seed = veo.seed_for(theme, "sig", s["k"])
        before = veo.spent_this_run()
        for attempt in range(2):
            try:
                veo.make_clip(prompt, small, VEO_SEC, out, seed + attempt)
                row["ok"] = True
                clips[i] = out
                break
            except veo.RaiFiltered as e:
                row["error"] = f"안전 필터: {str(e)[:120]}"
                log(f"컷 {i} 안전 필터 → 씨앗 바꿔 다시" if attempt == 0 else f"컷 {i} 다시 해도 안전 필터 → 사진 무빙")
            except veo.CapReached as e:
                row["error"] = f"한도: {e}"
                stopped = str(e)
                break
            except veo.VeoError as e:
                row["error"] = str(e)[:160]
                break
        row["krw"] = round(veo.spent_this_run() - before)                           # 실패한 시도에 나간 값까지 이 컷 몫으로
        if not row["ok"]:
            log(f"컷 {i} AI 영상 실패 → 사진 무빙: {row.get('error')}")
        rows.append(row)
    report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clip_sec": VEO_SEC, "clips": rows, "stopped": stopped,
                     "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}
    return clips


def compare_sheet(shots: list[dict], text: dict, out: Path) -> Path:
    """컷별 스토리보드 — 사진 | 역할 · 자막 · 근거 사실. 운영자 검수용(공식 사진이 들어 있어 커밋·Release 금지, 텔레그램·아티팩트로만).
    (파일 이름은 워크플로가 보내는 compare_sheet.jpg 그대로 — v1 의 '원본 | 변주' 대신 v2 는 사진과 자막·근거를 나란히)"""
    tw, th, pad, tx = 300, 533, 16, 680
    im = Image.new("RGB", (tw + pad * 3 + tx, len(shots) * (th + pad) + pad), (18, 20, 26))
    d = ImageDraw.Draw(im)
    f_role, f_sub, f_small = design.font(26), design.font(40), design.font(24, bold=False)
    for r, s in enumerate(shots):
        y = pad + r * (th + pad)
        try:
            im.paste(Image.open(SIG / s["img"]).convert("RGB").resize((tw, th), Image.LANCZOS), (pad, y))
        except Exception:  # noqa: BLE001
            d.rectangle((pad, y, pad + tw, y + th), fill=(40, 40, 48))
        x = pad * 2 + tw
        d.text((x, y + 8), f"컷 {s['i']} · {s.get('role') or ''}" + (f" · {s['motion']}" if s.get("motion") else ""), font=f_role, fill=(94, 234, 212))
        yy = y + 52
        if r == 0 and text.get("hook_title"):
            d.text((x, yy), f"훅 제목  {design.plain(text['hook_title'])}", font=f_role, fill=(255, 205, 120))
            yy += 46
        d.text((x, yy), text["phrases"][r] if r < len(text["phrases"]) else "", font=f_sub, fill=(255, 255, 255))
        yy += 70
        body = "근거: " + _body(s.get("fact") or "")
        for ln in [body[i:i + 24] for i in range(0, len(body), 24)][:5]:
            d.text((x, yy), ln, font=f_small, fill=(190, 190, 200)); yy += 34
        desc = "사진: " + str(s.get("description") or "")
        for ln in [desc[i:i + 24] for i in range(0, len(desc), 24)][:3]:
            d.text((x, yy + 10), ln, font=f_small, fill=(140, 140, 150)); yy += 34
    im.save(out, "JPEG", quality=86)
    return out


def preview_md(req: dict, sig: dict, shots: list[dict], text: dict, h: dict, pos: int, folder: str, report: dict, preview: bool) -> str:
    chk = " · ".join(f"사진 {c['k']} {'주인공' if c.get('ok') else '탈락'}({c.get('share')})" for c in sig.get("checks") or [])
    md = [f"# 시그니처 {'미리보기' if preview else '제작'} — {h['name']} · {req.get('region')} · {req.get('theme')} · {req.get('month')}",
          f"형식: {'한 장면' if _fmt(req) == 'single' else '몽타주'} · 음악만(나레이션 없음) · 컷 {len(shots)}개(서로 다른 사진) · 프로필 {pos}번 ({folder}) · 영상에서는 숙소 이름 비공개", "",
          "## 시그니처", "", f"- **{sig['name']}** — {sig['what']}", f"- 근거(사실 {sig.get('fact_i')}): {_body(sig['fact'])}",
          f"- 다른 후보와 다른 점: {sig.get('vs_peers') or '-'} (비교한 후보 {sig.get('peers', 0)}곳)",
          f"- 의외성 {sig.get('surprise')} · 왜: {sig.get('why')}", f"- 사진 확인(시그니처가 주인공인가 · 화면 비율): {chk or '-'}", "",
          "## 컷 (자막 하나 = 사실 하나 · 컷마다 실제 사진 → AI 영상)", "", "| 컷 | 역할 | 자막 | 근거 사실 | 사진 | 영상 |", "|---|---|---|---|---|---|"]
    for r, s in enumerate(shots):
        vr = next((x for x in (report.get("veo") or {}).get("clips", []) if x.get("i") == s["i"]), {})
        how = ("AI 영상" + (" (미리보기 재사용)" if vr.get("reused") else "")) if vr.get("ok") else f"사진 무빙 ({str(vr.get('error') or '-')[:40]})"
        fact_txt = _body(s.get("fact") or "")[:40] + (" (사실 목록에 없음 — 사진에 보이는 것)" if s.get("photo_text") else "")
        md.append(f"| {s['i']} | {s.get('role') or '-'} | {text['phrases'][r]} | {fact_txt} | {s['description'][:36]} [{mt.SRC_KO.get(s.get('source'), '?')}] | {how} |")
    info = text.get("info_test") or {}
    md += ["", "## 정보 전달 시험", "",
           f"- 화면 글자만 보고 읽힌 특별한 점: {' / '.join(info.get('special') or []) or '없음'}",
           f"- 전할 사실과 맞음 {info.get('matched', 0)}/{info.get('need', 0)} → {'통과' if info.get('ok') else '**미달 — 확인 필요**'}" + (f" ({info['note']})" if info.get("note") else "")]
    extra = sig.get("points", [])[len(shots):]
    if extra:
        md += ["", "## 영상에 못 넣은 정보(사진 부족)", "", *[f"- [{p['role']}] {p['text']}" for p in extra]]
    c = text["caption"]
    md += ["", "## 훅 제목", "", (f"**{text['hook_title']}** ({text['hook_title_type']})" if text.get("hook_title") else f"(제목 없음 — 규칙에 맞는 후보가 없었다: {report.get('hook_title_missing')})"),
           "", "## 캡션", "", c.get("hook", ""), *(c.get("points") or []), "", *[f"· {x}" for x in text["checklist"]], "", c.get("save", ""),
           "", f"제목: {text['title']} · 해시태그: {' '.join(text['hashtags'])}", "",
           "## 비용", "", f"- AI 영상(Veo) {sum(1 for x in (report.get('veo') or {}).get('clips', []) if x.get('ok'))}/{len(shots)}컷 · 이번 실행 약 "
           f"{round(veo.spent_this_run() - report.get('images', {}).get('image_krw', 0)):,}원(재사용 클립 0원) · 글·비전은 텔레그램 알림의 추정치"]
    if sig.get("fallback") or report.get("text_fallback"):
        md += ["", "## 자동 대체(멈추지 않으려고 코드가 정한 것 — 확인 필요)", ""]
        if sig.get("fallback"):
            md.append(f"- 시그니처: 모델이 3번 모두 규칙에 맞는 답을 못 내 코드가 정함 — 사실 {sig.get('fact_i')}(사진이 가장 많이 이어진 것)")
        for e in report.get("text_fallback") or []:
            md.append(f"- 자막·캡션: {e}")
    return "\n".join(md) + "\n"


def render(shots: list[dict], text: dict, h: dict, req: dict, report: dict, folder: str, pos: int) -> tuple[Path, float, list]:
    """컷마다 AI 영상(Veo · 실패한 컷만 사진 무빙) + 자막 + 끝 카드 + 배경음악. 미리보기·제작 같은 영상(제작은 미리보기 클립 재사용)."""
    theme = str(req.get("theme") or "")
    style = str(req.get("caption_style") or design.DEFAULT_STYLE)
    frame = SIG / "ov_frame.png"
    design.frame_png(frame, ms.DISCLOSURE)
    clips = veo_clips(shots, report, theme)
    segs, timeline = [], []
    n = len(shots)
    for j, s in enumerate(shots):
        i = s["i"]
        L = DUR["hook"] if j == 0 else (DUR["last"] if j == n - 1 else DUR["mid"])
        overlays = [{"path": frame, "a": 0, "b": 99, "anim": False}]
        if j == 0 and text.get("hook_title"):
            ttl = SIG / "ov_title.png"
            design.hook_title_png(ttl, text["hook_title"])
            overlays.append({"path": ttl, "a": 0.0, "b": 99, "anim": False})          # 0초부터(첫 화면 = 썸네일 · Veo 첫 프레임 = 실제 사진)
        cap = SIG / f"ov_cap_{i:02d}.png"
        design.subtitle_png(cap, text["phrases"][j])
        overlays.append({"path": cap, "a": 0.0 if j == 0 else 0.08, "b": 99, "anim": j > 0, "fade": 0.12, "slide": 8})
        if i in clips:
            src, kind = clips[i], "AI 영상"
        else:
            pattern = PATTERNS[j % len(PATTERNS)]
            src = photo_clip(SIG / s["img"], L, SIG / f"pan_{i}.mp4", pattern)
            kind = f"사진 무빙·{pattern}"
        s["motion"] = "AI 영상" if i in clips else "사진 무빙"
        segs.append(so.cut_segment(100 + i, src, L, None, overlays, 1.0))
        timeline.append({"i": i, "kind": kind, "sec": round(L, 2), "role": s.get("role"), "variant": s["variant"], "people": s["people"], "phrase": text["phrases"][j],
                         "title": text["hook_title"] if j == 0 else None, "fallback": s.get("fallback")})
    card = design.end_card(SIG / "end_card.jpg", SIG / shots[0]["img"], folder, pos, style, ms.DISCLOSURE)
    segs.append(so.cut_segment(199, card, DUR["card"], None, [], image=True, fade_in=0.3))
    timeline.append({"i": "끝", "kind": "카드", "sec": DUR["card"]})
    (SIG / "concat.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in segs), encoding="utf-8")
    nob = SIG / "video_nomusic.mp4"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(SIG / "concat.txt"), "-c", "copy", "-movflags", "+faststart", str(nob)])
    total = ms.probe_duration(nob)
    video = ms.BUILD / "video.mp4"
    bgm_req = req.get("bgm", True)
    bgm_path = so.BGM if bgm_req is True else (mt.ROOT / "assets" / "music" / f"{bgm_req}.mp3" if isinstance(bgm_req, str) else None)
    if bgm_path and bgm_path.exists():
        so.mix_bgm(nob, bgm_path, video, total, level=MUSIC_LEVEL)
        report["bgm"] = bgm_path.name
    else:
        shutil.copy(nob, video)
        report["bgm"] = None
    return video, total, timeline


# ── 7. 계획 저장·재사용 ─────────────────────────────────────────────────────────────────
H_KEYS = ("name", "city", "room_names", "verified_facilities", "theme_hits", "blog_30d", "blog_total", "min_price", "honest", "photo_counts",
          "official_facts", "signature", "hook", "affiliate_url", "official_site", "rooms", "notice_facts", "closed_facilities", "panels", "notices_read")


def save_plan(req: dict, h: dict, pos0: int, sig: dict, shots: list[dict], text: dict) -> Path:
    keep = ("i", "k", "role", "point", "fact", "fact_i", "photo_text", "variant", "people", "pose", "place", "source", "src_url", "category", "view", "description",
            "veo_prompt", "motion", "src_img", "img", "verify", "fallback")
    plan = {"version": 3, "stay": h["name"], "format": str(req.get("format") or "montage"), "month": req.get("month"), "theme": req.get("theme"), "region": req.get("region"),
            "pos0": pos0, "h": {k: h.get(k) for k in H_KEYS}, "signature": sig, "shots": [{k: s.get(k) for k in keep} for s in shots], "text": text}
    out = SIG / "plan.json"
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return out


def find_reuse(req: dict) -> dict | None:
    """미리보기 실행의 아티팩트(build/reuse/<이름>/…/sig/plan.json)에서 같은 숙소·형식의 계획을 찾아 이미지·AI 클립(veo_<i>.mp4)과 함께 build/sig 로 가져온다.
    클립이 있는 컷은 다시 만들지 않는다(0원) — 미리보기에서 사진 무빙으로 내려간 컷만 제작 때 Veo 를 다시 시도한다."""
    if not req.get("reuse_runs") or not REUSE_DIR.exists():
        return None
    want = str(req.get("stay") or "").strip()
    fmt = str(req.get("format") or "montage")
    for f in sorted(REUSE_DIR.glob("*/**/sig/plan.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            plan = json.loads(f.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if plan.get("version") != 3 or (want and plan.get("stay") != want) or plan.get("format", "montage") != fmt:
            continue                                                                  # v1(빛·날씨 변주)·v2(사진 무빙) 계획은 쓰지 않는다
        need = {s["img"] for s in plan["shots"]} | {s["src_img"] for s in plan["shots"]}
        if not all((f.parent / n).exists() for n in need):
            log(f"재사용 계획 {f} — 이미지 파일이 빠짐 → 건너뜀"); continue
        SIG.mkdir(parents=True, exist_ok=True)
        for n in need:
            shutil.copy(f.parent / n, SIG / n)
        got = []
        for s in plan["shots"]:
            v = f.parent / f"veo_{s['i']}.mp4"
            if v.exists() and v.stat().st_size > 0:
                shutil.copy(v, SIG / v.name)
                got.append(s["i"])
        log(f"미리보기 계획 재사용(이미지 0원 · AI 클립 {len(got)}/{len(plan['shots'])}컷 0원): {f.relative_to(REUSE_DIR)}")
        return plan
    return None


# ── 진입점 ──────────────────────────────────────────────────────────────────────────────
def produce_sig(req: dict, models: dict, report: dict) -> tuple[Path, float, dict]:
    preview = str(req.get("stage") or "") == "preview"
    if SIG.exists():
        shutil.rmtree(SIG)
    SIG.mkdir(parents=True, exist_ok=True)
    report["stage"] = "preview" if preview else "produce"
    report["format"] = str(req.get("format") or "montage")
    plan = None if preview else find_reuse(req)
    if plan:
        h, pos0, sig, text = plan["h"], plan.get("pos0") or 0, plan["signature"], plan["text"]
        shots = plan["shots"]
        report["reused_plan"] = True
        report["hotels"] = [{k: h.get(k) for k in H_KEYS if k in h}]
    else:
        h, pos0 = so.assets(req, models, report)
        sig = choose_signature(models, h, req, report)
        shots = plan_cuts(sig, h, req, report)
        make_images(models, shots, report)                                         # 원본 사진 9:16 크롭만(편집 컷이 없어 0원)
        text = write_text(models, shots, sig, h, req, report)
        unblock(h["name"])                                                          # 전에 '사진 부족'으로 잠긴 숙소라도 이번에 만들어졌으면 푼다
    report["signature"] = {k: sig.get(k) for k in ("name", "what", "fact", "vs_peers", "peers", "points", "photos", "confirmed", "surprise", "why", "alternatives",
                                                   "checks", "fallback")}
    folder = mt.folder_name(req)
    try:
        pos = make_folder.place_hotel(req, h, pos0, None)                          # 대표 이미지는 바꾸지 않는다(변주는 공식 사진 파생물 — 페이지에 안 올림)
    except Exception as e:  # noqa: BLE001
        log(f"폴더 데이터 갱신 실패 ({str(e)[:80]}) — 순위표 위치로 대체")
        pos = pos0 or 1
    video, total, timeline = render(shots, text, h, req, report, folder, pos)          # 컷마다 AI 영상(재사용 클립은 0원)
    save_plan(req, h, pos0, sig, shots, text)                                       # 렌더 뒤에 — 컷별 영상 결과(motion)까지 남겨 제작이 클립을 재사용
    compare_sheet(shots, text, ms.PREVIEW / "compare_sheet.jpg")
    (ms.PREVIEW / "preview.md").write_text(preview_md(req, sig, shots, text, h, pos, folder, report, preview), encoding="utf-8")
    if not preview:
        so.save_hook_title(h["name"], text)                                         # 다음 편은 다른 유형(번갈아) — 제작 때만 기록
    report["hook_title"] = {"title": text["hook_title"], "type": text["hook_title_type"]}
    report["script"] = {"hook_title": text["hook_title"], "title": text["title"], "caption": text["caption"], "checklist": text["checklist"],
                        "cuts": [{"i": s["i"], "narration": text["phrases"][j], "caption": s.get("role") or VARIANT_KO[s["variant"]]} for j, s in enumerate(shots)]}
    report["screen_qa"] = []                                                        # (v1 변주 검수 자리) v2·v3 = 사진 확인(signature.checks) + 정보 전달 시험(info_test)
    report["info_test"] = text.get("info_test")
    report["timeline"] = timeline
    c = text["caption"]
    pc = h.get("photo_counts") or {}
    edited = any(s["variant"] != "original" or s["people"] != "none" for s in shots)
    ai_cuts = sum(1 for r in (report.get("veo") or {}).get("clips", []) if r.get("ok"))
    caption = (ms.DISCLOSURE + "\n\n" + str(c.get("hook") or "").strip()                       # 첫 줄 = 시그니처의 신박함(공감·감성 줄 없음)
               + ("\n" + "\n".join(c.get("points") or []) if c.get("points") else "")
               + ("\n\n" + "\n".join(f"· {x}" for x in text["checklist"]) if text["checklist"] else "")
               + "\n\n" + str(c.get("save") or "저장해두고 다시 꺼내 보세요.") + "\n같이 갈 사람에게도 보내 주세요."
               + f"\n\n{h['name']}" + (f" · {h['city']}" if h.get("city") else "")
               + f"\n객실 타입·예약 링크는 프로필 링크 → {pos}번 ({folder})"
               + ("\n사진: 숙소 공식 홈페이지" if pc.get("official") else "")
               + ("\n일부 장면(시간·날씨·뒷모습 인물)은 AI로 연출했어요. 실제 모습과 다를 수 있어요." if edited else "")
               + ("\n영상 속 움직임(물결·빛·카메라 이동)은 실제 사진을 바탕으로 AI로 만들었어요. 실제 모습과 다를 수 있어요." if ai_cuts else "")
               + "\n\n" + " ".join(text["hashtags"]))
    v = report.get("veo") or {}
    img_krw = int((report.get("images") or {}).get("image_krw") or 0)              # 장부상 한 번 실행 돈(spent_this_run)에는 이미지 편집도 들어 있다 → 나눠 적는다
    meta = {"mode": "signature", "label": f"시그니처 {'AI 미리보기' if preview else '제작'}(AI 영상 {ai_cuts}/{len(shots)}컷)", "stage": report["stage"], "stay": h["name"],
            "signature": sig["name"], "title": text["title"], "caption": caption, "folder": folder, "folder_pos": pos, "bgm": report.get("bgm"),
            "pinned_comment": f"{h['name']} — 객실 타입·링크는 프로필 링크 → {pos}번 ({folder}) · 쿠팡 파트너스 링크 포함",
            "affiliate_urls": {h["name"]: h.get("affiliate_url")}, "lines": text["phrases"], "cuts": timeline, "ai_edited": edited,
            "image_krw": img_krw, "info_ok": bool((text.get("info_test") or {}).get("ok")),
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": sum(1 for r in v.get("clips", []) if r.get("ok")), "clips_total": len(v.get("clips", [])),
                    "spent_krw": max(0, round(veo.spent_this_run()) - img_krw), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
