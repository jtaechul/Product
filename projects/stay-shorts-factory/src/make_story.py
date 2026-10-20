"""시그니처 이야기 쇼츠 — mode "signature" v4 (2026-10-15 운영자 "진행해" · 구조안 A '장점 하나, 여러 관점').

왜 다시 만들었나 — v3(stay-run-50 · 소노펠리체 · 약 930원) 운영자 평가 "세 컷만 하는 게 말이 되냐 · 시그니처 하나로 스토리를 연결해서
흥미를 점점 증폭시켜야지". 벤치마크 4편(운영자 업로드)을 컷·음성 단위로 뜯어 본 결과 4편 모두 **나레이션이 처음부터 끝까지 이어지는 이야기**
(음성 98~100% · 12~21컷 · 컷 1~2초 · 자막 = 나레이션 한 문장의 조각)였고, 우리 v3 는 나레이션 0% · 3컷 · 시설 이름표였다.
운영자 아이디어 "장점 하나를 다른 시각으로 계속 부각하고, 연결되는 관점에서도 계속 부각" = 벤치마크 ②(비 오는 날 노천탕)의 구조.

흐름
  1. 사진·사실 수집(make_solo.assets) → 장점(시그니처) 하나 고르기(make_sig.choose_signature — 못 고르면 코드가 정함 · 사진 2장 이상이면 멈추지 않음)
  2. 장점에 대한 사실 더 모으기 — 공식 홈페이지 글에서 그 장점에 관한 문장만(`deep_facts` · 글 호출 1번)
  3. 컷 재료 — 장점 사진마다 넓은 컷 + 비전이 고른 디테일 컷 1~2개(원본 픽셀만 잘라 확대 · 최대 1.5배) + 연결용 다른 사진(넓게)
  4. 대본 — 관점 7종을 한 문장씩: 훅(걱정·상식과 부딪히는 질문) → 정체(장점 이름) → 디테일·상황·사람·행동·연결·희소성 중 3개 이상 → 제안(첫 걱정을 푸는 한 줄).
     **관점 검사**: 훅 3초·정체 6초 안 / 훅 말고 모든 문장에 장점 낱말 / 근거(사실 번호·사진 설명) / 1인칭·과거형·분위기 말·숙소 이름·가격 금지 /
     같은 원본 사진 반복 상한 / 연결 사진은 연결 관점에서만 / 마지막 컷은 첫 장면 사진으로 돌아옴. 3번 못 지키면 걸린 문장만 사실 문장으로 고치거나 빼고 끝까지.
  5. 나레이션 한 번 합성 → 문장별 분할(make_solo.narrate · Kore · 1.28배속) + 가라오케 자막 + 훅 제목 + 배경음악(덕킹) + 끝 카드(프로필 번호)
  6. 미리보기 = AI 영상 없이(사진 무빙) 완성 영상 + 스토리보드 + 나레이션 — 글·비전·음성만(약 90원). 제작 = 미리보기 계획·음성 재사용 + 훅·정체·제안 3컷만 Veo(약 882원).

v5 '순간' 화면 문법 (2026-10-18 운영자 "원점에서 다시 검토" → 제안 채택) — 벤치마크(비 오는 날 노천탕 25.9만 · 촌캉스)는 컷마다 **사람(뒷모습·손)이나 날씨·빛이
움직이는 순간**인데 우리는 빈 방 사진 + 카메라 무빙이었다(#54 같은 사진 3번). 그래서:
  - 문장마다 actor(couple·back·hand·dog·env·none)·action_en 을 정하고, '순간' 문장(디테일·상황·사람·행동·연결)은 반드시 AI 컷(A 사람·강아지 / B 환경),
    '장소' 문장(정체·희소성·조건)만 겨냥 사진 무빙(C), 제안은 훅 AI 컷을 다시 써 첫 장면으로 돌아온다(R · 0원).
  - 예산 `ai_cuts`(기본 4 ≈ 1,176원): 훅 → 사람·강아지 컷 → 환경 컷 순으로 배정, 나머지는 C. 한 사진은 2컷까지.
  - 사람은 실사 뒷모습(얼굴 끝까지 없음)·강아지는 실사 소형견 — 피규어 폐기. 검수(약 1원): 사람 수·얼굴·강아지 수·새 사물·구조 변화·이상한 몸 → 탈락이면 그 컷만 C.
  - 화면 위 고지문 줄에 'AI 연출' 표시(실제 방문 영상으로 오인 방지) + 캡션 고지.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

import design
import make_folder
import make_mini as mm
import make_scenes as sc
import make_sig as sg
import make_solo as so
import make_stay as ms
import make_top3 as mt
import photos
import veo

STORY = ms.BUILD / "story"
REUSE_DIR = ms.BUILD / "reuse"
LENSES = ("훅", "정체", "디테일", "상황", "사람", "행동", "연결", "희소성", "조건", "제안")
MID_LENSES = ("디테일", "상황", "사람", "행동", "연결", "희소성", "조건")
MOMENT_LENSES = ("디테일", "상황", "사람", "행동", "연결")              # '순간' 문장 — 사람·강아지·환경이 실제로 움직이는 AI 컷(A/B)만 (v5)
PLACE_LENSES = ("정체", "희소성", "조건")                                # '장소' 문장 — 겨냥 사진 무빙(C) 허용
END_LENSES = ("제안", "약속")                                            # 마지막 문장 = 제안(2026-10-18 운영자 "되돌아옴이 아니고 제안") · '약속'은 옛 계획·대본의 별칭
AI_CUTS_DEFAULT = 6                                                  # 제작 때 AI 컷 수(v7 C안: 사람·강아지 씬 최대 6 ≈ 1,764원). request "ai_cuts"
ACTORS = ("couple", "back", "hand", "dog", "env")
ACTOR_KO = {"couple": "뒷모습 커플", "back": "뒷모습 한 사람", "hand": "손", "dog": "강아지", "env": "환경(빛·물·커튼)"}
DOG_RX = re.compile(r"반려견|강아지|펫\b|펫 |애견|댕댕|puppy|dog", re.I)
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
# 실사 강아지 컷(반려견 장점일 때만) — 사람은 손도 안 나온다. 새 물건(장난감·공·간식)·뛰기·짖기 금지
DOG_PROMPT = ("Camera: steady and locked-off, no camera movement. A small cream-white toy poodle — a real, living dog with soft curly fur, a small black nose "
              "and a coral-red collar, at true small-dog size for the furniture — enters from the lower edge of the frame and {action}. Natural, unhurried dog "
              "movement; it stays the same dog for the whole clip. No people appear, not even a hand. Keep every object, structure, surface and the view exactly "
              "as in the first frame; do not add any new objects, other animals or text.")
DOG_BAN_RX = re.compile(r"\b(person|people|man|woman|human|hand|hands|child|kid|baby|face|cat|two dogs|jump|jumps|run|runs|bark|barks|toy|ball|treat|food)\b", re.I)
# 환경 컷 — 사람·동물 없이 빛·커튼·물·김·비만. 시간·날씨 변주는 건물·가구·전망을 바꾸지 않는 범위에서(벤치마크의 노을·비)
ENV_STORY = ("Camera: steady, at most a very slow push-in, staying inside the photo the whole time. Only the existing light, air, fabric and water move: {action}. "
             "No people, no animals, no new objects, no text.")
ENV_BAN_RX = re.compile(r"\b(person|people|man|woman|human|hand|hands|child|dog|cat|animal|bird|birds|car|face|figure|silhouette|someone)\b", re.I)
ACTOR_BAN = {"hand": PERSON_BAN_RX, "back": PERSON_BAN_RX, "couple": mm.REAL_BAN_RX, "dog": DOG_BAN_RX, "env": ENV_BAN_RX}
DEFAULT_ACTION = {"hand": "reaches toward the main object in the scene and gently touches it",
                  "back": "walks in slowly, stops, and looks at the view ahead",
                  "couple": "walk in slowly side by side, stop, and look at the view ahead",
                  "dog": "walks in calmly, sniffs the floor and sits down, looking around",
                  "env": "soft daylight drifts across the room and the sheer curtain sways very slightly"}
EXPECT_KO = {"hand": "손·팔 하나만(얼굴·몸 없음)", "back": "뒷모습 한 사람(얼굴 없음)", "couple": "뒷모습 두 사람(얼굴 없음)", "dog": "작은 강아지 한 마리(사람 없음)",
             "env": "사람·동물 없이 빛·물·커튼만 움직임"}
VISUAL_CHECK_SYSTEM = """너는 AI 영상 검수자다. 이미지 3장: 첫 장면(원본 사진) · 중간 · 끝 장면. 기대: {expect}.
판단: people = 보이는 사람 수(가장 많은 장면 기준 · 손·팔만 보이면 "hand"), face_visible = 누구든 얼굴(눈·코·입)이 보이는 장면이 있는가, dogs = 강아지 수,
new_objects = 첫 장면에 없던 사물(사람·강아지 제외 · 손에 든 물건 포함), structure_changed = 벽·가구·물가·창·전망이 바뀌거나 사라졌나,
weird = 손가락 수·팔다리·몸 크기가 이상하거나 녹아내리듯 변하는가, looks_real = 사람·강아지가 실사처럼 자연스러운가(없으면 true).
JSON 만: {{"people":0,"face_visible":false,"dogs":0,"new_objects":[],"structure_changed":false,"weird":false,"looks_real":true,"why":"한 줄"}}"""
AI_NOTE = "일부 장면(사람·강아지·빛)은 AI 연출입니다"               # 화면 위 고지문 줄에 붙는다(실사 뒷모습 인물 — 실제 방문 영상으로 오인 방지)
LINE_LEN = (6, 30)                                                   # 문장 글자 수(공백 제외) — 1.28배속 약 6.6자/초
TOTAL_LEN = (80, 170)                                                # 전체 나레이션(공백 제외) — 약 12~26초 (v6: 장소 이동 문장 한 줄이 더 들어간다)
BEATS = (6, 9)
MIN_VIEWS = 3                                                        # 가운데 관점 종류 최소 개수(같은 말 반복이 아니라 '다른 시각')
ADV_PHOTOS = 4                                                       # 장점 사진 최대 장 수(디테일 비전 호출 상한)
LINK_PHOTOS = 8                                                      # 연결용 다른 사진 최대 장 수 (v6: 장소 다양성 우선으로 고른다)
# ── v6 '동선' 화면 문법 (2026-10-18 운영자 "숙소의 한 장소 화면만 계속 나온다 · 화면 전환이 더 많이 이루어져도 모자랄 판") ─────────────
# stay-run-55: 쓸 사진 5장 → 컷 재료 4개 → 7문장 중 4문장이 같은 방(사진 19) · 7컷 24초(벤치마크 12~13컷 17~21초). 규칙(코드 강제):
#  ① 문장마다 컷 1~2개(2.9초 넘는 문장은 서로 다른 사진 2개) ② 이어지는 컷에 같은 원본 사진 금지 ③ 사진 무빙은 사진당 2컷까지
#  ④ AI 컷은 4초 중 앞 2.0~2.6초만 쓰고 나머지는 다른 사진(뒷부분은 원본에서 멀어진다 · 비용 동일) ⑤ 장면 사진 6장·장소 4곳 미만이면 만들지 않는다(8장·5곳 미만은 경고)
AI_PART = (2.0, 2.6)                                                 # A/B 컷에서 AI 영상을 쓰는 길이(초) — 나머지는 둘째 컷(다른 사진) 무빙
TAIL_MIN = 0.9                                                       # 둘째 컷 최소 길이
INSERT_MAX = 1.3                                                     # 짧은 인서트(작은 패널 사진) 컷 최대 길이
C_PER_PHOTO = 2                                                      # 같은 원본 사진의 사진 무빙 컷 상한
SEC_PER_CHAR = 0.152                                                 # 1.28배속 실측 6.6자/초 — 문장 길이로 컷 수를 미리 정한다
WANT = {"photos": 8, "places": 5}                                    # 이 밑이면 미리보기 문서에 경고만 — 2026-10-18 운영자 "5컷 미만이어도 AI로 다른 영상을 생성하면 괜찮아, 제한 걸지 마" → 관문(중단·잠금) 없음
PLACE_RX = (("욕실", r"욕실|화장실|세면|샤워|변기|욕조"), ("사우나", r"사우나|찜질|발한"), ("온수탕·스파", r"온수탕|온탕|노천|스파|온천|자쿠지|히노키|족욕"),
            ("수영장", r"수영장|인피니티|돔|슬라이드|파도|유수풀|워터|풀\b|풀장|풀이"), ("바다", r"바다|해변|해안|오션|수평선|파도"),
            ("테라스", r"테라스|발코니|베란다|데크|루프탑|옥상"), ("정원·산책로", r"정원|산책|숲|잔디|소나무|해송"), ("라운지·카페", r"라운지|카페|바\b|레스토랑|식당|조식"),
            ("노래방", r"노래방"), ("편의점", r"편의점"), ("세탁실", r"세탁"), ("피트니스", r"피트니스|헬스|운동|러닝머신"), ("키즈", r"키즈|놀이방|볼풀"), ("도그 파크", r"도그 ?파크|애견 ?운동장|반려견 ?놀이터"))
ZOOM_MAX = 1.5                                                       # 디테일 컷 확대 상한(공식 사진 1024px → 1920 높이라 더 키우면 흐려진다)
SHOT_MIN = 0.9                                                       # 한 컷 최소 길이(초) — 한 문장에 컷 2~3개일 때
MIN_HOOK = 3.2
AIM_ZOOM = (0.22, 0.5)                                               # 대상 겨냥 무빙의 확대 폭(끝 화면 1.22~1.5배) — 2026-10-16 운영자 "카메라 무빙만? 이미지를 보고 크게 움직이든가"
MOTION = 0.24                                                        # 짧은 컷 사진 무빙 폭(9컷 형식 0.24 의 절반 남짓 — 1초 컷에서 흔들려 보이지 않게)
PATTERNS = ("push", "pan", "diag", "tilt", "pull")
PRICE_RX = re.compile(r"\d[\d,]*\s*(원|만원|만 원|%)")
FEATURE_MAX = 3                                                       # v10 특장점 라벨(2026-10-20 운영자 '2안 라벨만') — 영상당 1~3개(레퍼런스 또떠남 수락휴는 35초에 7개 = 시설 나열)
FEATURE_LEN = (4, 12)                                                 # 라벨 글자 수(공백 빼고) · 108px 두 줄까지(design.fits_lines('feature') · 띄어쓰기 자리에서만 나눔)
CARD_ANS = (6, 12)                                                    # v10.1 카드 답 줄 글자 수(공백 빼고) — 72px 한 줄
PAIN_LEN = (6, 14)                                                    # 걱정형 제목(페인포인트) 글자 수(공백 빼고) — 120px 두 줄까지
FEATURE_LENSES = ("정체", "디테일", "상황", "사람", "행동", "연결", "희소성", "조건")   # 훅·제안엔 라벨 없음
CARD_DEFAULT = True                                                   # 요약 카드 기본 켜짐 — 2026-10-20 운영자: '라벨만' 뒤 큰 글씨 재설계를 보고 '새 디자인으로 켠다' · request card:false 로 끔
CARD_SEC, CARD_SEC_SHORT = 3.0, 2.6                                  # v9 요약 카드(걱정 → 답 · 음악만) 길이 — 나레이션이 CARD_NARR_LIMIT 를 넘으면 짧게
CARD_NARR_LIMIT = 26.0
CARD_LINE = (6, 14)                                                   # 카드 글 한 줄(공백 제외 · 44px 한 줄 폭 680px)


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


def place_of(p: dict) -> str:
    """사진이 보여 주는 장소 이름(동선 규칙용). 객실은 욕실만 따로, 물놀이·특별 공간은 낱말로, 외관은 '외관'."""
    desc = f"{p.get('description') or ''} {p.get('src_alt') or ''}"
    cat = str(p.get("category") or "")
    if mt.is_exterior(p):
        return "외관"
    if cat == "room":
        return "욕실" if re.search(PLACE_RX[0][1], desc) else "객실"
    for name, rx in PLACE_RX:
        if re.search(rx, desc):
            return name
    return "물놀이" if cat == "water" else "특별 공간"


def material(h: dict, pool: dict, rejected: set, report: dict) -> dict:
    """재료 집계(0원): 일반 컷으로 쓸 수 있는 서로 다른 사진 수·장소 목록·인서트 패널 수. 관문(GATE)·경고(WANT)의 근거."""
    full = [k for k in pool if k not in rejected and photos.panel_grade(pool[k]) == "full"]
    inserts = [k for k in pool if k not in rejected and photos.panel_grade(pool[k]) == "insert"]
    places = sorted({place_of(pool[k]) for k in full})
    mat = {"photos": len(full), "places": places, "inserts": len(inserts), "panels": int(h.get("panels") or 0), "notices_read": int(h.get("notices_read") or 0),
           "notice_facts": len(h.get("notice_facts") or []), "closures": list(h.get("closure_notes") or []), "rejected": sorted(rejected)}
    report["material"] = mat
    log(f"재료: 장면 사진 {mat['photos']}장 · 장소 {len(places)}곳 {places} · 인서트 패널 {len(inserts)}장 · 안내문 사실 {mat['notice_facts']}개"
        + (f" · 제외 {mat['closures']}" if mat["closures"] else ""))
    return mat


def material_gate(mat: dict, h: dict, req: dict, report: dict) -> None:
    """장면 사진·장소가 권장(WANT) 밑이면 경고만 남긴다 — 멈추거나 잠그지 않는다(운영자 2026-10-18 "5컷 미만이어도 AI로 다른 영상을 생성하면 괜찮아, 제한 걸지 마").
    부족한 장면은 AI 컷(같은 사진 위의 다른 순간·동작)으로 채운다."""
    n, m = int(mat["photos"]), len(mat["places"])
    if n < WANT["photos"] or m < WANT["places"]:
        report["material_warning"] = f"장면 사진 {n}장 · 장소 {m}곳 — 권장 {WANT['photos']}장·{WANT['places']}곳 미만: 부족한 장면은 AI 컷으로 채운다(사진이 더 있는 숙소가 유리)"
        log("경고: " + report["material_warning"])


def diverse(cands: list[int], pool: dict, key, limit: int) -> list[int]:
    """장소가 서로 다른 사진을 먼저(장소마다 한 장씩 돌아가며), 같은 장소 안에서는 key 순. 인서트 패널은 뒤로."""
    groups: dict[str, list[int]] = {}
    for k in sorted(cands, key=lambda k: (photos.panel_grade(pool[k]) == "insert",) + tuple(key(k))):
        groups.setdefault(place_of(pool[k]), []).append(k)
    order = sorted(groups, key=lambda g: (photos.panel_grade(pool[groups[g][0]]) == "insert",) + tuple(key(groups[g][0])))
    out: list[int] = []
    while len(out) < limit and any(groups[g] for g in order):
        for g in order:
            if groups[g] and len(out) < limit:
                out.append(groups[g].pop(0))
    return out


def build_shots(models: dict, sig: dict, h: dict, report: dict) -> list[dict]:
    """컷 재료 목록. 장점 사진(주인공 확인 → 시그니처 낱말 사진) 최대 4장 × (넓게 + 디테일 1~2) + 연결용 다른 사진 최대 8장(넓게만 · 장소 다양성 우선)."""
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
    adv = [k for k in adv if photos.panel_grade(by_k[k]) == "full"][:ADV_PHOTOS]            # 작은 패널은 장점(AI 시작 장면) 사진이 될 수 없다
    # 주인공 확인 '아님' + 장점 사진과 같은 분류 = 닮아서 헷갈리는 사진(stay-run-53 키즈룸 ↔ 펫 객실).
    # stay-run-54: 분류를 안 보고 '아님'을 전부 뺐더니 바다 전망(다른 분류)까지 빠져 펫 객실 사진 2장으로 6문장 — 같은 사진 3번·'바다' 문장 밑에 하우스
    sig_cats = {by_k[k].get("category") for k in adv}
    rejected = {int(c["k"]) for c in checked if not (c.get("ok") or c.get("subject")) and by_k[int(c["k"])].get("category") in sig_cats}
    material(h, pool, rejected, report)
    cands = [k for k in pool if k not in adv and k not in rejected and not (mt.is_exterior(pool[k]) and k not in adv)]
    others = diverse(cands, pool, lambda k: (-sg._overlap(toks, sg._tokens(pool[k].get("description"))), -int(pool[k].get("quality") or 0), k), LINK_PHOTOS)
    STORY.mkdir(parents=True, exist_ok=True)
    shots, n = [], 0
    for k in adv:
        p = by_k[k]
        n += 1
        sid = f"S{n}"
        crop_shot(p["path"], STORY / f"shot_{sid}.png", float(p.get("focus_x", 0.5)), float(p.get("focus_y", 0.5)))
        shots.append({"id": sid, "k": k, "kind": "장점·넓게", "desc": p.get("description") or "", "img": f"shot_{sid}.png", "adv": True,
                      "category": p.get("category"), "veo_prompt": p.get("veo_prompt") or "", "source": p.get("source"), "place": place_of(p), "grade": "full"})
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
                          "zoom": round(1 / max(1 / ZOOM_MAX, min(1.0, frac)), 2), "place": place_of(p), "grade": "full"})
    for k in others:
        p = by_k[k]
        n += 1
        sid = f"S{n}"
        grade = photos.panel_grade(p)
        crop_shot(p["path"], STORY / f"shot_{sid}.png", float(p.get("focus_x", 0.5)), float(p.get("focus_y", 0.5)))
        shots.append({"id": sid, "k": k, "kind": "연결" + ("·짧은 인서트" if grade == "insert" else ""), "desc": p.get("description") or "", "img": f"shot_{sid}.png", "adv": False,
                      "category": p.get("category"), "veo_prompt": p.get("veo_prompt") or "", "source": p.get("source"), "place": place_of(p), "grade": grade})
    report["story_shots"] = [{k: s.get(k) for k in ("id", "k", "kind", "desc", "zoom", "place", "grade")} for s in shots]
    log(f"컷 재료 {len(shots)}개 — 장점 사진 {adv} · 연결 사진 {others} · 장소 {sorted({s['place'] for s in shots})}")
    return shots


# ── 3. 대본(관점별 한 문장) ─────────────────────────────────────────────────────────────
STORY_SYSTEM = """너는 숙소 쇼츠 작가다. 이 숙소의 **장점 하나**를 정해 두고, 나레이션 한 줄 한 줄이 그 장점을 **다른 관점으로 다시 부각**하는 20초 이야기를 쓴다.
(벤치마크: "여행 날 비 오면 다 망친 것 같잖아요. 근데 여긴 비가 와야 오히려 좋은 숙소예요. 방문만 열면 나만 쓰는 노천탕이 있어서 빗소리 들으며 산만 보면 돼요…"
 — 모든 문장이 노천탕이거나 노천탕에서 이어지는 행동, 마지막 문장이 첫 걱정을 푼다.)
관점(lens):
- 훅: 첫 문장. 시청자의 **상황**(날씨·계절·동반자 — 예 '여행 날 비 오면 망한 것 같잖아요', '강아지 두고 떠나는 여행, 늘 마음 쓰이죠?')이나 상식과 부딪히는 질문. 장점 이름은 아직 말하지 않아도 된다. 6~18자.
- 정체: 둘째 문장. 장점이 무엇인지 분명히(장점 이름 낱말 필수) — 훅의 걱정을 뒤집는다.
- 디테일: 가까이서 보이는 것(사진 디테일 컷과 맞게).
- 상황: 언제·어떤 날 가장 좋은지(사실·시기에 근거).
- 사람: 누구의 어떤 고민을 푸는지(아이와·둘이서 등 — 사실에 없는 서비스 지어내기 금지).
- 행동: 거기서 무엇을 하면 되는지(2인칭 · '~하면 돼요').
- 연결: **다른 장소로 이동**하는 문장(예 '방을 나서면 돔 수영장도 반려견과 같이 갈 수 있어요', '추우면 문 열고 방으로 들어오면 그만이에요') — 그 장소의 사진과 그 장소에 대한 사실 번호가 필수이고, 문장은 그 장점으로 돌아와야 한다. 이용 조건(제외·요금·목줄 등)이 사실에 있으면 과장하지 않는다.
- 희소성: 같은 테마 다른 숙소들이 내세우는 것과 비교한 차이(아래 '다른 후보' 목록에 근거 · 다른 숙소 이름은 말하지 않는다).
- 조건: 가기 전에 알아야 할 이용 조건·예약·포함 여부 한 줄(사실 번호 필수 · 솔직하게 · 벤치마크의 '대신 ~은 미리 예약' 같은 신뢰 장치).
- 제안: 마지막 문장. 훅의 걱정을 받아 시청자에게 **권하는** 한 줄(예 훅 '반려견 두고 떠나는 여행, 늘 마음 쓰이죠?' → 제안 '이번엔 반려견과 함께 떠나 보는 건 어떨까요?').
  바로 뒤에 끝 카드('예약 링크는 프로필 N번')가 붙으므로 그 답이 되게. 장점 낱말 포함, 저장 권유는 캡션에서.
규칙:
1) beats 6~9개: 첫째 훅, 둘째 정체, 마지막 제안, 가운데는 디테일·상황·사람·행동·연결·희소성·조건 중 **서로 다른 3개 이상**(디테일·상황·사람·행동·연결 = '순간' 문장이 3개 이상).
2) 훅 말고 **모든 문장에 장점 낱말**(장점 이름·설명·장점 사진에 보이는 사물)이 들어간다. 장점과 상관없는 시설 이야기 금지.
   단, 장점 이름을 매 문장 통째로 되풀이하지 않는다 — 장점의 **부분**(사진에 보이는 사물·사실 낱말: 계단·식기·탕·창…)으로 이어 간다.
3) 각 문장은 근거가 있어야 한다: fact = 아래 사실 번호, 사진에 보이는 것만 말하면 0. 사실·사진에 없는 내용·숫자 금지.
4) 말투: 2인칭 현재형 '~해요' 체. 금지: 1인칭·체험·과거형('다녀왔', '좋았', '-더라고요', '저는', '우리'), '~니다', 숙소 이름, 가격 숫자,
   '최고·유일·최저가·무조건', 분위기만 있는 말(노을빛·물들고·힐링·낭만·감성·설렘·아늑·포근·그림 같은·인생샷·완벽한·행복·추억).
5) 문장 길이: 공백 빼고 6~30자, 전체 합 80~170자(약 12~26초). 문장은 서로 이어지게(앞 문장을 받는 연결어 환영).
6) shots: 그 문장 동안 나올 컷 id(아래 목록). 훅·제안은 1개, 정체·가운데 문장은 **서로 다른 사진 2개**(첫 컷 = 문장의 대상, 둘째 컷 = 다른 장소·다른 사진 — 화면이 자주 바뀌어야 한다).
   **이어지는 컷에 같은 원본 사진 금지**(앞 문장의 마지막 컷과 다음 문장의 첫 컷도) · 같은 원본 사진은 영상 전체에서 2컷까지 · '짧은 인서트' 컷은 둘째 컷으로만.
   훅·정체·디테일의 첫 컷은 장점 사진. **제안은 훅과 다른 사진**(아직 덜 쓴 사진 — 장점 사진이 남아 있으면 그것, 없으면 연결 사진 · 화면은 제작 때 집·차 안의 '떠남' 인서트로 바뀐다). 장소가 다른 사진을 골고루 쓴다(목록의 '장소').
7) hook_title: 첫 화면 위쪽 큰 제목 — 장점의 신박함을 묻는 질문(장점 낱말 · 핵심 낱말 하나만 [대괄호] · 공백 빼고 6~14자 · 물음표 끝 · 숙소·지역 이름 금지 · 나레이션을 그대로 옮기지 않는다).
8) caption: hook(첫 줄 — 장점이 무엇이고 왜 의외인지, 사실 그대로) · points(장점의 다른 관점 1~3줄, 사실 그대로) · save(저장 권유 한 줄, 시기와 연결).
   checklist: 사실 번호와 짧은 체크 항목 2~4개. title: 유튜브 제목 12~28자(숙소 이름 포함). hashtags 5개.
9) **화면(actor · action_en)** — 문장마다 그 문장이 말하는 **순간이 화면에서 실제로 일어나게** 정한다. actor:
   "couple"(가운 입은 커플 뒷모습 — 바닥·공간이 넓게 보이는 사진) · "back"(한 사람 뒷모습) · "hand"(손·팔만, 사진에 이미 있는 사물에 동작) ·
   "dog"(실사 작은 강아지 — 아래 '강아지 등장'이 가능일 때만) · "env"(사람·동물 없이 빛·커튼·물·김·비만 움직임) · "none"(사진 그대로).
   규칙: 훅은 couple·dog·env 중 하나(가장 센 장면). 디테일·상황·사람·행동·연결 문장은 **none 금지**(문 열면·물 채우면·바다를 보면 — 그 동작이 보여야 한다).
   정체·희소성·조건·제안은 none. action_en = 영어 한 구절(8~160자) — 사진에 있는 사물·자리로만. 얼굴·돌아보기·카메라 보기·새 물건(컵·휴대폰·장난감)·뛰기·물에 뛰어들기 금지, 사람은 끝까지 뒷모습.
10) **흐름(시청자가 그 숙소에 들어가 하루를 보내는 순서)**: 훅(걱정) → 정체(답) → 들어서면 보이는 것 → 짐 풀고 하는 것 → 저녁·밤·아침 → 제안.
   문장 3부터는 앞 문장을 받는 말로 시작한다('들어서면·짐 풀면·그 옆엔·저녁엔·씻고 나면·그래서·이제' 등). 같은 연결어·같은 끝맺음을 이어 쓰지 않는다.
   각 문장은 **시청자가 얻는 것**(같이 잔다·짐이 준다·맡기지 않아도 된다·…)으로 끝낸다 — 시설 이름만 늘어놓지 않는다.
11) **반복 금지**: 같은 낱말 둘을 이은 말(예 '전용 계단', '반려견 객실')을 다른 문장에서 다시 쓰지 않는다. 한 낱말은 영상 전체에서 3문장까지.
   **제안은 정체를 되풀이하지 않는다** — 훅의 걱정 낱말을 받아 뒤집어 권한다(예 훅 '두고 떠나는 여행, 마음 쓰이죠?' → 제안 '이번엔 함께 떠나 보는 건 어떨까요?').
12) **card(요약 카드 · 조건 문장 뒤 3초 · 음악만 · 저장 유도)**: point = 훅의 걱정을 물음표 없는 **명사구**로(공백 빼고 6~14자 · 예 '반려견 두고 떠나는 여행'),
   answers = 이 숙소의 답 2~3줄(각 6~14자 명사구 · 서로 다른 내용 · 사실 번호 필수, 장점 사진에 보이는 것만 말하면 0 · 분위기 말·가격·숙소 이름·'~니다' 금지 · 첫 줄의 핵심 낱말 하나만 [대괄호]).
13) **feature(특장점 라벨 · 영상당 1~3개)**: 정체·디테일·상황·행동·연결·조건 중 1~3문장에 그 문장이 보여 주는 특장점을 공백 빼고 4~10자 명사구로(예 '펫 전용 객실', '전 객실 바다 전망'). 훅·제안은 "".
   같은 특장점이 이어지는 문장엔 같은 글을 그대로(화면 라벨이 이어진다). 그 문장의 사실·문장·장점 낱말에 근거 · 가격·분위기 말·숙소 이름·'~니다'·물음표·기호 금지 · 서로 다른 특장점은 3개까지.
JSON 만: {"beats":[{"lens":"훅","line":"...","shots":["S1"],"fact":0,"actor":"env","action_en":"...","feature":""}],"hook_title":"...",
 "caption":{"hook":"...","points":["..."],"save":"..."},"checklist":[{"fact":1,"text":"..."}],"title":"...","hashtags":["#..."],
 "card":{"point":"...","answers":[{"fact":1,"text":"..."},{"fact":0,"text":"..."}]}}"""


def _nospace(t: str) -> int:
    return len(re.sub(r"\s", "", str(t or "")))


FLOW_START = tuple(so.CONNECTORS) + ("문을", "짐", "도착", "씻", "말리", "자기 전", "잠들", "눈 뜨", "그다음", "그러다", "같이", "함께", "이번", "다음", "이제")   # '이번엔·다음엔' = 제안 문장의 연결어
END_RX = re.compile(r"(요|죠|다)$")


def _words(line: str) -> list[str]:
    """반복 검사용 낱말(순서 유지): sg._tokens 와 같은 조사 떼기, 끝맺음 낱말(…요·…죠)은 뺀다."""
    out = []
    for w in re.findall(r"[가-힣A-Za-z0-9]+", str(line or "")):
        w = re.sub(r"(은|는|이|가|을|를|과|와|의|에|에서|엔|으로|로|도|만|까지|부터|이에요|예요|이다|있는|하는)$", "", w)
        if len(w) >= 2 and not END_RX.search(w) and w not in sg.GENERIC_SIG:
            out.append(w)
    return out


def flow_story_errs(beats: list[dict]) -> list[str]:
    """2026-10-16 운영자 '대사 연결이 미흡하고 마지막 주어가 중간과 반복돼 어색': stay-run-53 대본은 '전용'이 4문장, 제안이 정체의 '전용 계단 … 반려견 객실'을 되풀이,
    문장 3~6 중 연결어로 시작한 문장 0개였다. 같은 말 두 낱말 반복(훅↔제안 되받기는 허용) · 한 낱말 4문장 이상 · 제안≈정체 · 연결어 부족 · 같은 끝맺음 3연속을 잡는다.
    오류는 '흐름:' 으로 시작 — 모델에게 고쳐 쓰라고 돌려주되, 3번 실패 뒤 repair(사실 문장으로 갈아 끼우기) 대상은 아니다(더 딱딱해진다)."""
    errs = []
    lines = [design.one_line(str(b.get("line") or "")) for b in beats]
    lenses = [str(b.get("lens") or "") for b in beats]
    words = [_words(x) for x in lines]
    grams = [{(a, b) for a, b in zip(w, w[1:])} for w in words]
    for j in range(1, len(lines)):
        for i in range(j):
            if lenses[i] == "훅" and lenses[j] in END_LENSES:
                continue                                                           # 첫 걱정을 되받아 권하는 것은 의도된 반복
            same = grams[i] & grams[j]
            if same:
                a, b = sorted(same)[0]
                errs.append(f"흐름: 문장 {j + 1} '{a} {b}' 가 문장 {i + 1} 의 말을 되풀이 — 새 정보나 다른 말로")
                break
    seen: dict[str, list[int]] = {}
    for k, w in enumerate(words, 1):
        for x in set(w):
            seen.setdefault(x, []).append(k)
    for x, ks in sorted(seen.items(), key=lambda kv: -len(kv[1])):
        if len(ks) > 3:
            errs.append(f"흐름: 문장 {ks[-1]} 낱말 '{x}' 이 {len(ks)}문장째 — 한 낱말은 3문장까지(장점의 다른 부분으로)")
            break
    if len(lines) >= 3 and "정체" in lenses and lenses[-1] in END_LENSES:
        a, b = re.sub(r"\s", "", lines[lenses.index("정체")]), re.sub(r"\s", "", lines[-1])
        if difflib.SequenceMatcher(None, a, b).ratio() >= 0.5:
            errs.append(f"흐름: 문장 {len(lines)} 제안이 정체를 되풀이 — 훅의 걱정을 받아 뒤집어 권한다('이번엔 ~해 보는 건 어떨까요?')")
    rest = lines[2:]
    linked = sum(1 for x in rest if any(x.startswith(w) or w in x[:8] for w in FLOW_START))
    if rest and linked < (len(rest) + 1) // 2:
        errs.append(f"흐름: 문장 3부터 앞 문장을 받는 말로 시작한 문장 {linked}/{len(rest)} — 절반 이상('들어서면·짐 풀면·저녁엔·그래서·이제' 등)")
    ends = [re.sub(r"[.!?~\s]+$", "", x)[-2:] for x in lines]
    for k in range(2, len(ends)):
        if ends[k] and ends[k] == ends[k - 1] == ends[k - 2]:
            errs.append(f"흐름: 문장 끝 '{ends[k]}' 3번 연속 — 끝맺음을 바꾼다")
            break
    return errs


def story_errs(js: dict, sig: dict, h: dict, req: dict, facts: list[str], shots: list[dict], peers: list[str], toks: set[str]) -> list[str]:
    """관점 검사. 오류 문구는 '문장 N ' 으로 시작하면 그 문장 탓(대체·삭제 대상), 아니면 전체 구조 탓."""
    errs = []
    beats = [b for b in (js.get("beats") or []) if isinstance(b, dict)]
    if not (BEATS[0] <= len(beats) <= BEATS[1]):
        return [f"beats {len(beats)}개 — {BEATS[0]}~{BEATS[1]}개"]
    by_id = {s["id"]: s for s in shots}
    lenses = [str(b.get("lens") or "").strip() for b in beats]
    if lenses[0] != "훅" or lenses[1] != "정체" or lenses[-1] not in END_LENSES:
        errs.append(f"관점 순서 {lenses} — 첫째 훅 · 둘째 정체 · 마지막 제안")
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
    limit = max(3, -(-n_used // n_photo))                                               # 대본 단계 상한(제안=되돌아옴은 안 셈). 사진 무빙만 2컷 제한은 화면 계획(plan_visuals)이 본다
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
        if lens in ("훅", *END_LENSES) and len(ids) != 1:
            errs.append(f"문장 {i} {lens} 컷은 1개")
        if len(ids) > 3:
            errs.append(f"문장 {i} 컷 {len(ids)}개 — 3개까지")
        if lens in ("훅", "정체", "디테일") and not by_id[ids[0]]["adv"]:                        # v8: 제안은 연결 사진도 된다(덜 쓴 사진 · 화면은 인서트)
            errs.append(f"문장 {i} {lens} 관점의 첫 컷에 연결 사진 — 장점 사진으로")
        for x in ids:                                                                       # v8: 제안도 센다(훅 되돌아옴 폐기 — 같은 사진 반복은 어디서든 반복)
            photo_count[by_id[x]["k"]] = photo_count.get(by_id[x]["k"], 0) + 1
        desc = " ".join(by_id[x]["desc"] for x in ids)
        fi = sg._int(b.get("fact"))
        fact = facts[fi - 1] if fi and 1 <= fi <= len(facts) else ""
        lt = sg._tokens(line)
        if lens not in ("훅", "조건") and not sg._overlap(lt, toks):                        # 조건(이용 조건 한 줄)은 사실 번호로 근거를 대면 된다
            errs.append(f"문장 {i} '{line}' 에 장점 낱말이 없음 — 모든 문장이 장점({sig['name']})을 다른 관점으로 말한다")
        if lens not in ("훅", *END_LENSES) and not sg._overlap(lt, sg._tokens(sg._body(fact)) | sg._tokens(desc)):
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
    return errs + flow_story_errs(beats)


def est_sec(j: int, line: str) -> float:
    """문장이 차지할 화면 시간(초) — 1.28배속 실측 6.6자/초. 컷을 몇 개 둘지 미리 정하는 데 쓴다(실제 길이는 음성으로)."""
    return max(MIN_HOOK if j == 0 else 0.0, _nospace(line) * SEC_PER_CHAR + 0.12)


def route_shots(beats: list[dict], shots: list[dict], report: dict | None = None) -> None:
    """v6 동선 규칙을 코드가 강제한다(0원): ① 첫 컷은 인서트 금지 · 훅/정체/디테일/제안 첫 컷은 장점 사진 ② 2.9초 넘는 문장(훅·제안 제외)은 서로 다른 사진 2컷
    ③ 이어지는 컷에 같은 원본 금지(앞 문장 마지막 컷 ↔ 다음 문장 첫 컷) ④ 같은 원본 사진은 2컷까지(v8: 제안도 센다 · 제안은 훅과 다른 사진). 인서트 컷(INS)은 그대로 둔다. 모델 답을 고칠 뿐 다시 묻지 않는다."""
    by_id = {s["id"]: s for s in shots}
    if not by_id or not beats:
        return
    full = [s for s in shots if s.get("grade", "full") != "insert"]
    if not full:
        return
    k_of = lambda sid: by_id[sid]["k"]                                                # noqa: E731
    n = len(beats)
    changes: list[str] = []

    def need_adv(b) -> bool:
        return b.get("lens") in ("훅", "정체", "디테일")                                   # v8: 제안은 장점 사진 선호일 뿐 필수 아님(pick 정렬이 장점 사진을 앞에 둔다)

    def pick(b, exclude_k: set, used: dict, prefer_place_not: str | None = None, allow_insert: bool = False, tail: bool = False) -> dict | None:
        lt = sg._tokens(b.get("line")) | sg._tokens(b.get("want"))
        cands = [s for s in shots if not s.get("insert") and (allow_insert or s.get("grade", "full") != "insert") and (s["adv"] or not need_adv(b))]
        cands = [s for s in cands if s["k"] not in exclude_k] or [s for s in cands if s["k"] not in {min(exclude_k) if exclude_k else -1}]
        if not cands:
            return None
        if tail:                                                                       # v8: 둘째 컷(꼬리)은 **아직 안 쓴 사진**이 먼저(원본은 영상에서 한 번만) · 장소 바꾸기 · 그다음 낱말 겹침
            return sorted(cands, key=lambda s: (used.get(s["k"], 0) >= C_PER_PHOTO, used.get(s["k"], 0), s.get("place") == prefer_place_not,
                                                -sg._overlap(lt, sg._tokens(s["desc"])), not s["adv"], s["id"]))[0]
        return sorted(cands, key=lambda s: (used.get(s["k"], 0) >= C_PER_PHOTO, s.get("place") == prefer_place_not,
                                            -sg._overlap(lt, sg._tokens(s["desc"])), used.get(s["k"], 0), not s["adv"], s["id"]))[0]

    # ① 첫 컷 규칙
    for j, b in enumerate(beats):
        ids = [x for x in (b.get("shots") or []) if x in by_id]
        if b.get("lens") in END_LENSES and j > 0:                                       # v8: 제안은 훅과 **다른** 장점 사진(되돌아옴 폐기 · 화면은 '떠남' 인서트가 덮는다)
            k0 = k_of(beats[0]["shots"][0]) if beats[0].get("shots") and beats[0]["shots"][0] in by_id else -1
            if not (ids and by_id[ids[0]].get("insert")) and (not ids or k_of(ids[0]) == k0):
                cnt: dict[int, int] = {}
                for bb in beats[:j]:
                    for x in bb.get("shots") or []:
                        if x in by_id:
                            cnt[k_of(x)] = cnt.get(k_of(x), 0) + 1
                prev_k = k_of(beats[j - 1]["shots"][-1]) if beats[j - 1].get("shots") and beats[j - 1]["shots"][-1] in by_id else -1
                best = pick(b, {k0, prev_k}, cnt)
                if best:
                    changes.append(f"문장 {j + 1} 제안 컷 {ids[:1]} → {best['id']}({best.get('place')} · 훅과 다른 사진)")
                    ids = [best["id"]]
            b["shots"] = ids[:1]
            continue
        if not ids or by_id[ids[0]].get("grade", "full") == "insert" or (need_adv(b) and not (by_id[ids[0]]["adv"] or by_id[ids[0]].get("insert"))):
            best = pick(b, set(), {})
            if best:
                changes.append(f"문장 {j + 1} 첫 컷 {ids[:1]} → {best['id']}({best.get('place')})")
                ids = [best["id"]] + [x for x in ids if x != best["id"]]
        b["shots"] = ids[:3]
    # ② 둘째 컷 — 2.9초 넘는 문장(훅·제안 제외)은 다른 사진으로
    used: dict[int, int] = {}
    for b in beats:
        for x in b["shots"]:
            used[k_of(x)] = used.get(k_of(x), 0) + 1
    for j, b in enumerate(beats):
        if b.get("lens") == "훅" or b.get("lens") in END_LENSES or len(b["shots"]) >= 2 or not b["shots"]:
            continue
        if est_sec(j, b.get("line")) < AI_PART[0] + TAIL_MIN:
            continue
        first = by_id[b["shots"][0]]
        nxt = k_of(beats[j + 1]["shots"][0]) if j + 1 < n and beats[j + 1].get("shots") else -1
        best = pick({**b, "lens": "연결"}, {first["k"], nxt}, used, prefer_place_not=first.get("place"), allow_insert=True, tail=True)
        if best and best["k"] != first["k"]:
            b["shots"].append(best["id"])
            used[best["k"]] = used.get(best["k"], 0) + 1
            changes.append(f"문장 {j + 1} 둘째 컷 +{best['id']}({best.get('place')})")
    # ③ 이어지는 컷에 같은 원본 금지
    for j in range(1, n):
        prev, cur = beats[j - 1], beats[j]
        if not prev.get("shots") or not cur.get("shots"):
            continue
        if k_of(cur["shots"][0]) != k_of(prev["shots"][-1]):
            continue
        if len(cur["shots"]) >= 2 and k_of(cur["shots"][1]) != k_of(prev["shots"][-1]) and by_id[cur["shots"][1]].get("grade", "full") != "insert" \
                and (by_id[cur["shots"][1]]["adv"] or not need_adv(cur)):
            cur["shots"].reverse(); changes.append(f"문장 {j + 1} 컷 순서 바꿈(앞 문장과 같은 사진)")
            continue
        if len(prev["shots"]) >= 2 and k_of(prev["shots"][0]) != k_of(cur["shots"][0]) and prev.get("lens") != "훅":
            prev["shots"].reverse(); changes.append(f"문장 {j} 컷 순서 바꿈(다음 문장과 같은 사진)")
            continue
        best = pick(cur, {k_of(prev["shots"][-1])} | ({k_of(cur["shots"][1])} if len(cur["shots"]) > 1 else set()), used)
        if best and best["k"] != k_of(prev["shots"][-1]):
            used[k_of(cur["shots"][0])] = max(0, used.get(k_of(cur["shots"][0]), 0) - 1)
            used[best["k"]] = used.get(best["k"], 0) + 1
            changes.append(f"문장 {j + 1} 첫 컷 {cur['shots'][0]} → {best['id']}(앞 문장과 같은 사진)")
            cur["shots"][0] = best["id"]
    # ④ 같은 원본 사진 2컷까지(제안 제외) — 넘치면 바꿀 수 있는 자리부터: 둘째 컷 → 사람·강아지 동작이 없는 문장의 첫 컷(훅 제외) 순.
    #    손·뒷모습·강아지 동작이 붙은 첫 컷은 그 사진의 사물에 맞춘 지시문이라 바꾸지 않는다.
    def occurrences(k: int) -> list[tuple[int, int]]:
        return [(j, m) for j, b in enumerate(beats) for m, x in enumerate(b["shots"]) if k_of(x) == k]

    def replaceable(j: int, m: int) -> int:                                            # 0 = 못 바꿈 · 1 = 둘째 컷 · 2 = 동작 없는 첫 컷
        b = beats[j]
        if m > 0:
            return 1
        if b.get("lens") == "훅" or str(b.get("actor") or "none").lower() in ("hand", "back", "couple", "dog"):
            return 0
        return 2
    for k in sorted({k_of(x) for b in beats for x in b["shots"] if k_of(x) >= 0}):
        guard = 0
        while len(occurrences(k)) > C_PER_PHOTO and guard < 6:
            guard += 1
            occ = sorted(((replaceable(j, m), -j, j, m) for j, m in occurrences(k)), key=lambda t: (t[0] == 0, -t[0], t[1]))   # 바꿀 수 있는 것 중 뒤 문장부터
            if not occ or occ[0][0] == 0:
                break
            _, _, j, m = occ[0]
            b = beats[j]
            x = b["shots"][m]
            nb = {k_of(y) for y in b["shots"] if y != x}
            if j + 1 < n and beats[j + 1].get("shots"):
                nb.add(k_of(beats[j + 1]["shots"][0]))
            if j > 0 and beats[j - 1].get("shots") and m == 0:
                nb.add(k_of(beats[j - 1]["shots"][-1]))
            cnt_now = {kk: len(occurrences(kk)) for kk in {k_of(y) for bb in beats for y in bb["shots"]}}
            best = pick(b if m == 0 else {**b, "lens": "연결"}, nb | {k}, cnt_now, prefer_place_not=by_id[b["shots"][0]].get("place") if m else None,
                        allow_insert=m > 0, tail=m > 0)
            if not best or best["k"] == k or cnt_now.get(best["k"], 0) >= C_PER_PHOTO:
                break
            b["shots"][m] = best["id"]
            changes.append(f"문장 {j + 1} 컷 {x} → {best['id']}(같은 사진 {C_PER_PHOTO}컷 초과)")
    if report is not None:
        report["route_changes"] = changes
    if changes:
        log(f"동선 배정 고침 {len(changes)}곳: " + " / ".join(changes[:6]))


def _line_idx(e: str) -> int | None:
    m = re.match(r"문장 (\d+) ", e)
    return int(m.group(1)) if m else None


def recheck_shots(text: dict, shots: list[dict], sig: dict, report: dict) -> None:
    """재사용 계획 다시 검사(돈 0) — build_shots 를 고치기 전에 만든 미리보기도 바로잡는다(stay-run-53: '도그 파크' 문장 밑에 키즈룸).
    주인공 확인을 못 통과한 사진의 컷은 목록에서 빼고(연결 컷으로도 안 씀), 그 컷을 쓰던 문장은 옆 문장과 다른 사진의 덜 쓴 컷으로 바꾼다
    (연결 관점은 남은 연결 컷 먼저, 나머지는 장점 컷)."""
    good = adv_ok(sig)
    failed = {int(c["k"]) for c in sig.get("checks") or [] if not (c.get("ok") or c.get("subject"))}
    sig_cats = {s.get("category") for s in shots if int(s["k"]) in good}
    bad = {s["id"] for s in shots if int(s["k"]) not in good and (s.get("adv") or (int(s["k"]) in failed and s.get("category") in sig_cats))}
    if not good or not bad:
        return
    by_id = {s["id"]: s for s in shots}
    adv = [s["id"] for s in shots if s.get("adv") and s["id"] not in bad]
    link = [s["id"] for s in shots if not s.get("adv") and s["id"] not in bad]
    if not adv:
        return
    beats = text.get("beats") or []
    use: dict[str, int] = {}
    for b in beats:
        for x in b.get("shots") or []:
            use[x] = use.get(x, 0) + 1
    changed = []
    for i, b in enumerate(beats):
        ids = list(b.get("shots") or [])
        if not any(x in bad for x in ids):
            continue
        # 옆 문장과 같은 원본 사진은 피한다(stay-run-53: 디테일·행동·희소성 세 문장이 같은 사진이 될 뻔함) → 덜 쓴 컷
        near = [x for j in (i - 1, i + 1) if 0 <= j < len(beats) for x in beats[j].get("shots") or [] if x in by_id]
        near_k = {by_id[x]["k"] for x in near}
        pool = (link + adv) if str(b.get("lens") or "") == "연결" else adv
        new = []
        for x in ids:
            if x in bad:
                cand = sorted((y for y in pool if y not in new and y not in ids and y not in bad),
                              key=lambda y: (by_id[y]["k"] in near_k, use.get(y, 0), pool.index(y)))
                if not cand:
                    continue
                y = cand[0]
                use[y] = use.get(y, 0) + 1
                changed.append({"beat": i + 1, "from": x, "to": y})
                x = y
            new.append(x)
        b["shots"] = new or [adv[0]]
    shots[:] = [s for s in shots if s["id"] not in bad]
    report["shot_recheck"] = {"not_signature": sorted(bad), "changed": changed}
    log(f"컷 다시 검사: 주인공 확인 안 된 사진의 컷 {sorted(bad)} 뺌 · 바꾼 문장 {changed}")


def fix_shots(js: dict, shots: list[dict]) -> None:
    """코드로 고칠 수 있는 것은 고친다(돈 0): ① 같은 컷을 두 번 쓰면 같은 사진의 안 쓴 컷(없으면 안 쓴 장점 컷)으로 바꾼다
    ② 제안 컷이 훅과 같은 사진이면 덜 쓴 다른 장점 사진으로(v8: 되돌아옴 폐기 — 운영자 2026-10-19 "똑같은 사진 반복이 눈에 거슬린다")."""
    beats = js.get("beats") or []
    if len(beats) < 2:
        return
    by_id = {s["id"]: s for s in shots}
    used = set()
    for b in beats:
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
    if not h_ids or str(last.get("lens") or "") not in END_LENSES:
        return
    k0 = by_id[h_ids[0]]["k"]
    l_ids = [x for x in last.get("shots") or [] if x in by_id]
    if l_ids and by_id[l_ids[0]]["k"] != k0:
        return
    cnt: dict[int, int] = {}
    for b in beats[:-1]:
        for x in b.get("shots") or []:
            if x in by_id:
                cnt[by_id[x]["k"]] = cnt.get(by_id[x]["k"], 0) + 1
    alt = sorted((s for s in shots if s["k"] != k0 and not s.get("insert") and s.get("grade", "full") != "insert"),
                 key=lambda s: (cnt.get(s["k"], 0), not s["adv"], s["id"] in used, s["id"]))        # 덜 쓴 사진 먼저(장점 사진 2장뿐이면 연결 사진) — 사진당 상한 충돌 방지
    if alt:
        last["shots"] = [alt[0]["id"]]


def repair(js: dict, errs: list[str], sig: dict, facts: list[str], report: dict) -> dict:
    """3번 다 관점 검사에 걸렸을 때 — 걸린 문장만 사실 문장으로 바꾸거나(훅·정체·제안) 뺀다(가운데, 6문장 아래로는 안 뺌). 멈추지 않는다."""
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
        elif lens in END_LENSES:
            b["line"] = f"이번엔 {sg._cut(sig['name'], 14)} 어떠세요?"
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


SCRIPTS = mt.ROOT / "data" / "story_scripts.json"                                   # 운영자가 승인한 숙소별 대본(관점·문장) — 있으면 모델은 컷·근거·제목·캡션만 고른다


def operator_script(stay: str) -> list[dict] | None:
    """2026-10-16 운영자 '대본을 소비자 관점으로 개선해' — 대화에서 다듬어 승인받은 문장을 그대로 쓰기 위한 입구(숙소 이름별)."""
    try:
        d = json.loads(SCRIPTS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    beats = [{"lens": str(b["lens"]), "line": design.one_line(str(b["line"])),
              **({"actor": str(b["actor"])} if b.get("actor") else {}), **({"action_en": str(b["action_en"])} if b.get("action_en") else {}),
              **({"want": str(b["want"])} if b.get("want") else {}), **({"fact_hint": str(b["fact_hint"])} if b.get("fact_hint") else {}),   # v6: 사진·근거 낱말 힌트
              **({"feature": str(b["feature"])} if b.get("feature") else {})}                                                            # v10: 특장점 라벨
             for b in ((d.get(stay) or {}).get("beats") or []) if isinstance(b, dict) and b.get("lens") and b.get("line")]
    return beats or None


def operator_caption(stay: str) -> dict | None:
    """운영자 승인 캡션(hook·points·save) — 사진이 없어 나레이션에서 뺀 이득(무료 펫 욕조 등)을 글로 전한다. 캡션 검사를 통과할 때만 쓴다."""
    try:
        c = (json.loads(SCRIPTS.read_text(encoding="utf-8")).get(stay) or {}).get("caption")
    except Exception:  # noqa: BLE001
        return None
    return c if isinstance(c, dict) and c.get("hook") else None


def operator_card(stay: str) -> dict | None:
    """운영자 승인 요약 카드(point · answers[text, fact_hint]) — 사실 번호는 실행마다 달라서 낱말 힌트(fact_hint)로 적고 코드가 번호를 찾는다."""
    try:
        c = (json.loads(SCRIPTS.read_text(encoding="utf-8")).get(stay) or {}).get("card")
    except Exception:  # noqa: BLE001
        return None
    return c if isinstance(c, dict) and c.get("point") and isinstance(c.get("answers"), list) else None


def operator_facts(stay: str, report: dict | None = None) -> list[str]:
    """운영자 확인 사실(`story_scripts.json` facts · 출처·날짜는 facts_note) — 공식 홈페이지 안내문 이미지를 운영자가 직접 읽어 적은 사실.
    수집기가 그 안내문을 못 읽은 실행(#59: 반려견 수영장 입장 규정 안내문이 콜라주 판정으로 빠짐)에서도 대본·캡션·카드의 근거가 되게 하는 안전망.
    사실 목록 맨 뒤에 '운영자 확인 안내문: ' 머리말로 붙고 미리보기 문서에 따로 표시된다."""
    try:
        d = json.loads(SCRIPTS.read_text(encoding="utf-8")).get(stay) or {}
    except Exception:  # noqa: BLE001
        return []
    out = [f"운영자 확인 안내문: {design.one_line(str(f))}" for f in (d.get("facts") or []) if isinstance(f, str) and f.strip()]
    if report is not None and out:
        report["operator_facts"] = {"facts": out, "note": design.one_line(str(d.get("facts_note") or ""))}
    return out


def card_errs(card, facts: list[str], toks: set[str], h: dict, req: dict, grounded: bool = True) -> list[str]:
    """요약 카드 검사(0원): point 6~14자 명사구(물음표·분위기 말·숙소 이름 금지) · 답 2~3줄 6~14자 · 한 줄 폭(design.fits) · 사실 번호 근거(0 이면 장점 사진 낱말)
    · 가격·1인칭·'~니다'·근거 없는 숫자·중복 금지 · [대괄호] 강조는 카드 전체에서 한 곳."""
    if not isinstance(card, dict):
        return ["card 없음"]
    errs = []
    point = design.one_line(str(card.get("point") or ""))
    ans = [a for a in (card.get("answers") or []) if isinstance(a, dict)]
    name_toks = [n for n in so.name_tokens(h["name"], req, h) if n]
    corpus = " ".join(facts)
    Lp = _nospace(design.plain(point))
    if not (CARD_LINE[0] <= Lp <= CARD_LINE[1]):
        errs.append(f"point '{point}' {Lp}자 — {CARD_LINE[0]}~{CARD_LINE[1]}자 명사구")
    elif not design.fits(point, "card_point")[0]:
        errs.append(f"point '{point}' 한 줄에 안 들어감")
    if "?" in point or "？" in point or so.ENDING_RX.search(point):
        errs.append("point 는 물음표 없는 명사구")
    if sg.MOOD_RX.search(point) or any(n in point for n in name_toks):
        errs.append("point 분위기 말·숙소 이름 금지")
    if not (2 <= len(ans) <= 3):
        errs.append(f"answers {len(ans)}개 — 2~3개")
    seen, brackets = set(), point.count("[")
    for i, a in enumerate(ans, 1):
        t = design.one_line(str(a.get("text") or ""))
        fi = sg._int(a.get("fact")) or 0
        Lt = _nospace(design.plain(t))
        if not (CARD_ANS[0] <= Lt <= CARD_ANS[1]):
            errs.append(f"답 {i} '{t}' {Lt}자 — {CARD_ANS[0]}~{CARD_ANS[1]}자"); continue
        if not design.fits(t, "card_line")[0]:
            errs.append(f"답 {i} '{t}' 한 줄에 안 들어감")
        if fi and not (1 <= fi <= len(facts)):
            errs.append(f"답 {i} 사실 번호 {fi} 없음")
        elif grounded:
            basis = (sg._tokens(sg._body(facts[fi - 1])) if fi else set()) | toks          # 인용 사실 낱말 또는 장점 사진·장점 이름 낱말('객실' 같은 일반 낱말은 비교에서 빠진다)
            if not sg._overlap(sg._tokens(design.plain(t)), basis):
                errs.append(f"답 {i} '{t}' 근거 낱말 없음(사실 {fi or '장점 사진'})")
        if sg.MOOD_RX.search(t):
            errs.append(f"답 {i} '{t}' 분위기 말")
        if PRICE_RX.search(t) or any(n in t for n in name_toks) or sg.PAST_RX.search(t) or sg.FIRST_RX.search(t):
            errs.append(f"답 {i} '{t}' 가격·숙소 이름·1인칭 금지")
        if any(d not in corpus and d != str(sg.month_num(req)) for d in sg.DIGIT_RX.findall(t)):
            errs.append(f"답 {i} '{t}' 숫자가 사실 목록에 없음")
        if so.ENDING_RX.search(t):
            errs.append(f"답 {i} '{t}' '~니다' 금지")
        key = design.plain(t).replace(" ", "")
        if key in seen:
            errs.append(f"답 {i} 중복")
        seen.add(key); brackets += t.count("[")
    if brackets > 1:
        errs.append("강조 [대괄호]는 카드 전체에서 한 곳만")
    if not errs and not design.card_fits(point, [design.one_line(str(a.get("text") or "")) for a in ans]):
        errs.append("카드가 화면 아래 안전영역을 넘음")
    return errs


def _reground_card(card: dict, facts: list[str], toks: set[str]) -> dict:
    """답 줄이 인용한 사실 번호와 낱말이 안 겹치면(모델이 번호를 잘못 적음) 낱말이 가장 많이 겹치는 사실로 번호를 바로잡는다(0원). 못 찾으면 그대로 두어 검사가 거른다."""
    out = []
    for a in card.get("answers") or []:
        if not isinstance(a, dict):
            continue
        t = design.plain(design.one_line(str(a.get("text") or "")))
        fi = sg._int(a.get("fact")) or 0
        if fi and (not (1 <= fi <= len(facts)) or not sg._overlap(sg._tokens(t), sg._tokens(sg._body(facts[fi - 1])))):
            fi2 = auto_fact(t, facts)
            fi = fi2 if fi2 else (0 if sg._overlap(sg._tokens(t), toks) else fi)
        out.append({**a, "fact": fi})
    return {**card, "answers": out}


def _norm_card(card: dict, facts: list[str], source: str) -> dict:
    ans = []
    for a in card.get("answers") or []:
        if isinstance(a, dict):
            fi = sg._int(a.get("fact")) or 0
            ans.append({"fact": fi if 1 <= fi <= len(facts) else 0, "text": design.one_line(str(a.get("text") or ""))})
    return {"point": design.one_line(str(card.get("point") or "")), "answers": ans[:3], "eyebrow": str(card.get("eyebrow") or design.CARD_EYEBROW), "source": source}


def feature_errs(t: str, b: dict, facts: list[str], toks: set[str], h: dict, req: dict) -> list[str]:
    """특장점 라벨 검사(0원): 공백 빼고 4~10자 · 한 줄 폭(장소 라벨 자리 72px) · 한글·영문·숫자·가운뎃점만 · 물음표·'~니다'·분위기 말·가격·숙소 이름 금지
    · 그 문장의 근거 사실·문장·장점 낱말과 겹쳐야 한다 · 사실·문장에 없는 숫자 금지."""
    errs = []
    t = design.one_line(str(t or ""))
    n = _nospace(t)
    if not (FEATURE_LEN[0] <= n <= FEATURE_LEN[1]):
        errs.append(f"글자 수 {n}(공백 빼고 {FEATURE_LEN[0]}~{FEATURE_LEN[1]})")
    elif not design.fits_lines(t, "feature"):
        errs.append("두 줄 폭 초과(띄어쓰기 자리에서 나눠 108px 두 줄)")
    if not re.fullmatch(r"[가-힣A-Za-z0-9·\s]+", t):
        errs.append("기호·이모지")
    if "?" in t or "？" in t or so.ENDING_RX.search(t):
        errs.append("물음표·'~니다'")
    m = sg.MOOD_RX.search(t)
    if m:
        errs.append(f"분위기 말 '{m.group(0)}'")
    if PRICE_RX.search(t):
        errs.append("가격")
    if any(x and x in t for x in so.name_tokens(h["name"], req, h)):
        errs.append("숙소 이름")
    basis = sg._tokens(sg._body(b.get("fact") or "")) | sg._tokens(b.get("line") or "") | set(toks)
    if not sg._overlap(sg._tokens(t), basis):
        errs.append("근거 낱말 없음(그 문장의 사실·문장·장점 낱말)")
    corpus = " ".join(facts) + " " + str(b.get("line") or "")
    for num in re.findall(r"\d+", t):
        if num not in corpus:
            errs.append(f"사실에 없는 숫자 {num}"); break
    return errs


def apply_features(beats: list[dict], facts: list[str], toks: set[str], sig: dict, h: dict, req: dict, report: dict, operator: bool = False) -> list[dict]:
    """v10 특장점 라벨(2026-10-20 운영자 '2안 라벨만'): 문장마다 적힌 feature 를 검사해 1~3개만 남긴다(훅·제안·규칙 밖 관점은 지움 · 같은 글이 이어지면 라벨 하나).
    하나도 없으면 정체 문장에 장점 이름(규칙에 맞을 때만). 라벨은 장소 라벨 자리(kicker)에 그 문장들 동안 떠 있다 — 레퍼런스(또떠남 수락휴)의 노란 라벨 역할."""
    n = len(beats)
    kept: list[str] = []
    tries = []
    for j, b in enumerate(beats):
        t = design.one_line(str(b.get("feature") or ""))
        b["feature"] = ""
        if not t:
            continue
        lens = str(b.get("lens") or "")
        if j == 0 or (j == n - 1 and lens in END_LENSES) or lens not in FEATURE_LENSES:
            tries.append({"beat": j + 1, "text": t, "errs": ["훅·제안·그 관점엔 라벨 없음"]}); continue
        errs = feature_errs(t, b, facts, toks, h, req)
        if errs:
            tries.append({"beat": j + 1, "text": t, "errs": errs[:3]}); continue
        if t not in kept and len(kept) >= FEATURE_MAX:
            tries.append({"beat": j + 1, "text": t, "errs": [f"{FEATURE_MAX}개 초과"]}); continue
        if t not in kept:
            kept.append(t)
        b["feature"] = t
    source = ("운영자" if operator else "모델") if kept else ""
    if not kept:                                                                       # 예비: 정체 문장에 장점 이름(규칙에 맞을 때만)
        j1 = next((j for j, b in enumerate(beats) if str(b.get("lens") or "") == "정체"), None)
        t = design.one_line(str(sig.get("name") or ""))
        if j1 is not None and t and not feature_errs(t, beats[j1], facts, toks, h, req):
            beats[j1]["feature"] = t; kept = [t]; source = "예비(장점 이름)"
    items = []
    for t in kept:
        js = [j + 1 for j, b in enumerate(beats) if b.get("feature") == t]
        fi = next((int(b.get("fact_i") or 0) for b in beats if b.get("feature") == t and b.get("fact_i")), 0)
        items.append({"text": t, "beats": js, "fact": fi})
    report["features"] = {"items": items, "source": source, "tries": tries[:8]}
    if tries:
        log("특장점 라벨 뺌: " + " / ".join(f"문장 {x['beat']} '{x['text']}' {x['errs'][0]}" for x in tries[:4]))
    return items


def pain_errs(t: str, h: dict, req: dict) -> list[str]:
    """걱정형 제목(페인포인트) 검사: 공백 빼고 6~14자 · 띄어쓰기 자리에서 120px 두 줄 · 물음표·느낌표·'~니다'·분위기 말·가격·숙소 이름 금지."""
    errs = []
    n = _nospace(design.plain(t))
    if not (PAIN_LEN[0] <= n <= PAIN_LEN[1]):
        errs.append(f"글자 수 {n}(공백 빼고 {PAIN_LEN[0]}~{PAIN_LEN[1]})")
    elif not design.fits_lines(design.plain(t), "hook_title"):
        errs.append("두 줄 폭 초과")
    if re.search(r"[?？!.。]", t) or so.ENDING_RX.search(t):
        errs.append("물음표·느낌표·마침표·'~니다'")
    m = sg.MOOD_RX.search(t)
    if m:
        errs.append(f"분위기 말 '{m.group(0)}'")
    if PRICE_RX.search(t):
        errs.append("가격")
    if any(x and x in t for x in so.name_tokens(h["name"], req, h)):
        errs.append("숙소 이름")
    return errs


def accent_word(t: str, toks: set[str]) -> str:
    """장점 낱말과 겹치는 첫 낱말 하나만 [대괄호](코랄) — 없으면 그대로."""
    words = t.split(" ")
    for i, w in enumerate(words):
        core = re.sub(r"(은|는|이|가|을|를|과|와|의|에|에서|으로|로|도|만|까지|부터)$", "", w)
        if len(core) >= 2 and any(core in x or x in core for x in toks):
            words[i] = f"[{core}]" + w[len(core):]
            return " ".join(words)
    return t


def pain_title(js: dict, op_card: dict | None, beats: list[dict], toks: set[str], h: dict, req: dict, report: dict) -> str:
    """v10.1 걱정형 제목(2026-10-20 운영자 "페인포인트 글씨 아주 크게"): 훅의 걱정을 큰 제목으로 — 운영자 카드 point → 모델 card.point → 훅 문장 첫 절.
    규칙에 맞는 첫 후보에 장점 낱말 하나만 [대괄호]. 전부 탈락이면 ""(호출부가 질문형 제목으로 되돌아간다)."""
    cands = []
    if op_card and op_card.get("point"):
        cands.append(("운영자", str(op_card["point"])))
    mc = js.get("card") if isinstance(js.get("card"), dict) else {}
    if mc.get("point"):
        cands.append(("모델", str(mc["point"])))
    hook = str(beats[0].get("line") or "") if beats else ""
    first = re.split(r"[,，?？!.]", hook)[0].strip()
    if first:
        cands.append(("훅 첫 절", first))
    tries = []
    for src, t in cands:
        t = design.one_line(design.plain(t)).strip(" ,")
        errs = pain_errs(t, h, req)
        if errs:
            tries.append({"source": src, "text": t, "errs": errs[:3]}); continue
        out = accent_word(t, toks)
        report["pain_title"] = {"source": src, "text": out, "tries": tries}
        return out
    report["pain_title"] = {"source": "", "text": "", "tries": tries}
    log("걱정형 제목 후보가 모두 규칙에 걸림 → 질문형 제목으로: " + " / ".join(f"{x['source']} '{x['text']}' {x['errs'][0]}" for x in tries[:3]))
    return ""


def make_card(model_card, op_card, facts: list[str], toks: set[str], sig: dict, h: dict, req: dict, beats: list[dict], checklist: list[str], report: dict) -> dict | None:
    """요약 카드 고르기(0원): 운영자 카드(fact_hint → 번호) → 모델 카드 → 예비(훅 첫 절 + 캡션 체크리스트 중 짧은 줄). 다 안 되면 카드 없이(기록)."""
    tries = []
    if op_card:
        op_card = {**op_card, "answers": [{"text": a.get("text"), "fact": sg._int(a.get("fact")) or auto_fact(str(a.get("text") or ""), facts, str(a.get("fact_hint") or ""))}
                                           for a in (op_card.get("answers") or []) if isinstance(a, dict)]}
    for src, cand in (("운영자", op_card), ("모델", model_card)):
        if not isinstance(cand, dict):
            continue
        cand = _reground_card(cand, facts, toks)
        errs = card_errs(cand, facts, toks, h, req)
        tries.append({"source": src, "errs": [str(e)[:100] for e in errs[:6]]})
        if not errs:
            report["card_check"] = tries
            return _norm_card(cand, facts, src)
    hook = str(beats[0].get("line") or "") if beats else ""
    point, eyebrow = re.split(r"[,，?？!！]", hook)[0].strip(), design.CARD_EYEBROW
    if not (CARD_LINE[0] <= _nospace(point) <= CARD_LINE[1]) or not design.fits(point, "card_point")[0] or so.ENDING_RX.search(point):
        point, eyebrow = sg._cut(sig["name"], CARD_LINE[1]), "핵심만 정리하면"
    ans: list[str] = []
    for t in checklist or []:
        t = design.one_line(str(t))
        if CARD_ANS[0] <= _nospace(t) <= CARD_ANS[1] and design.fits(t, "card_line")[0] and not sg.MOOD_RX.search(t) and not PRICE_RX.search(t) and t not in ans:
            ans.append(t)
    cand = {"point": point, "answers": [{"fact": 0, "text": t} for t in ans[:3]], "eyebrow": eyebrow}
    errs = card_errs(cand, facts, toks, h, req, grounded=False)                      # 체크리스트는 이미 사실 번호에 묶여 있다
    tries.append({"source": "예비", "errs": [str(e)[:100] for e in errs[:6]]})
    report["card_check"] = tries
    if errs:
        report["card"] = {"skipped": "; ".join(str(e)[:60] for e in errs[:3])}
        log(f"요약 카드 없음: {errs[:3]}")
        return None
    return _norm_card(cand, facts, "예비")


def auto_shots(beats: list[dict], shots: list[dict], only: set | None = None) -> None:
    """모델 답이 없을 때(또는 운영자가 want 로 사진을 지정한 문장만) 컷을 붙인다: 문장(+want) 낱말과 사진 설명이 많이 겹치는 컷, 옆 문장과 다른 사진, 제안 = 훅 컷.
    첫 컷은 인서트 패널 금지."""
    adv = [s for s in shots if s["adv"] and s.get("grade", "full") != "insert"] or [s for s in shots if s["adv"]] or shots
    used: dict[str, int] = {}
    for i, b in enumerate(beats):
        if only is not None and i not in only and i != len(beats) - 1:
            for x in b.get("shots") or []:
                used[x] = used.get(x, 0) + 1
            continue
        if b["lens"] in END_LENSES and beats[0].get("shots"):
            b["shots"] = list(beats[0]["shots"][:1]); continue
        pool = [s for s in shots if s.get("grade", "full") != "insert"] if b["lens"] in ("연결", "상황", "사람", "행동", "조건", "희소성") else adv
        prev_k = {s["k"] for s in shots if beats[i - 1].get("shots") and s["id"] in beats[i - 1]["shots"]} if i else set()
        lt = sg._tokens(b["line"]) | sg._tokens(b.get("want"))
        wt = sg._tokens(b.get("want"))
        best = sorted(pool, key=lambda s: (-sg._overlap(wt, sg._tokens(s["desc"])), s["k"] in prev_k, used.get(s["id"], 0),
                                           -sg._overlap(lt, sg._tokens(s["desc"])), not s["adv"]))[0]
        used[best["id"]] = used.get(best["id"], 0) + 1
        b["shots"] = [best["id"]]


def auto_fact(line: str, facts: list[str], hint: str = "") -> int:
    """문장(+근거 낱말 힌트) 낱말과 가장 많이 겹치는 사실 번호(1부터) — 없으면 0. 모델 답이 없을 때 운영자 문장의 근거를 코드가 붙인다(0원)."""
    lt, ht = sg._tokens(line), sg._tokens(hint)
    best, bi = 0, 0
    for i, f in enumerate(facts, 1):
        ft = sg._tokens(sg._body(f))
        n = sg._overlap(lt, ft) + 3 * sg._overlap(ht, ft)
        if n > best:
            best, bi = n, i
    return bi


def force_operator(js: dict, op: list[dict], shots: list[dict], facts: list[str] = ()) -> dict:
    """모델 답의 문장을 운영자 문장으로 덮는다(관점·문장·순서 고정). 컷·근거는 모델 답(문장 수가 같을 때) 또는 auto_shots·auto_fact."""
    got = [b for b in (js.get("beats") or []) if isinstance(b, dict)]
    beats = []
    for i, b in enumerate(op):
        g = got[i] if len(got) == len(op) else {}
        fi = (auto_fact(b["line"], list(facts), b["fact_hint"]) if b.get("fact_hint") else 0) or sg._int(g.get("fact")) \
            or (auto_fact(b["line"], list(facts)) if b["lens"] not in ("훅", *END_LENSES) else 0)                      # 운영자 근거 힌트 > 모델 > 낱말 겹침
        beats.append({"lens": b["lens"], "line": b["line"], "shots": [str(x) for x in (g.get("shots") or [])], "fact": fi,
                      "actor": b.get("actor") or g.get("actor") or "", "action_en": b.get("action_en") or g.get("action_en") or "",
                      "want": b.get("want") or "", "feature": b.get("feature") or g.get("feature") or ""})           # 운영자 화면 지시·라벨이 우선
    if not all(b["shots"] for b in beats) or any(x not in {s["id"] for s in shots} for b in beats for x in b["shots"]):
        auto_shots(beats, shots)
    elif any(b.get("want") for b in beats):
        auto_shots(beats, shots, only={i for i, b in enumerate(beats) if b.get("want")})                              # want 가 적힌 문장은 운영자가 고른 사진으로
    out = dict(js)
    out["beats"] = beats
    return out


def write_story(models: dict, sig: dict, h: dict, req: dict, facts: list[str], shots: list[dict], peers: list[str], toks: set[str], report: dict) -> dict:
    ttype = str(req.get("title_type") or "걱정형")                                     # v10.1 기본 = 걱정형(페인포인트 큰 제목) · '반전 질문'/'의외 사실'은 요청 title_type
    op = operator_script(h["name"])
    content = (f"장점: {sig['name']} — {sig.get('what') or ''}\n근거 사실: {sg._body(sig['fact'])}\n왜 의외: {sig.get('why') or '-'}\n"
               f"다른 후보와 다른 점: {sig.get('vs_peers') or '-'}\n시기: {req.get('month')} · 테마: {req.get('theme')} · 지역: {req.get('region')}\n"
               f"훅 제목 유형: {ttype} — {so.TITLE_TYPES[ttype]}\n최근 제목(다시 쓰지 말 것): {' / '.join(so.recent_titles()) or '없음'}\n"
               f"숙소 이름(제목·캡션용, 나레이션·훅 제목에는 금지): {h['name']}\n"
               f"강아지 등장(actor dog): {'가능 — 반려견 장점' if dog_ok(sig) else '불가'}\n\n"
               "장점 낱말(훅 말고 모든 문장에 하나 이상): " + ", ".join(sorted(toks)[:30]) + "\n\n"
               "같은 테마 다른 후보(희소성 관점 근거 · 이름은 말하지 않는다):\n" + ("\n".join(f"- {x}" for x in peers) or "- (없음)")
               + "\n\n사실(번호):\n" + "\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1))
               + "\n\n컷 목록(id · 종류 · 사진 번호 · 장소 · 보이는 것):\n" + "\n".join(f"{s['id']} · {s['kind']} · 사진 {s['k']} · 장소 {s.get('place') or '-'} · {s['desc']}" for s in shots))
    if op:
        content += ("\n\n운영자 확정 대본 — beats 의 lens·line 은 아래를 글자 그대로·같은 순서·같은 개수로 쓴다(바꾸지 않는다). "
                    "shots·fact·feature·hook_title·caption·checklist·title·hashtags 만 정한다(actor·action_en·feature 가 적힌 문장은 그것도 그대로):\n"
                    + "\n".join(f"{i}. [{b['lens']}] {b['line']}" + (f"  (actor {b['actor']}: {b.get('action_en') or ''})" if b.get("actor") else "")
                                + (f"  (feature: {b['feature']})" if b.get("feature") else "") for i, b in enumerate(op, 1)))
        report["operator_script"] = [b["line"] for b in op]
    fb, best, tries = "", None, []
    for attempt in range(3):
        try:
            js = sg._ask(models, STORY_SYSTEM, content + fb, 0.6)
        except RuntimeError as e:
            tries.append({"errs": [f"호출 실패: {str(e)[:80]}"]})
            continue
        if op:
            js = force_operator(js, op, shots, facts)
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
    if best is None and op:                                                            # 글 호출 실패여도 운영자 대본은 그대로(컷은 코드가)
        js = force_operator({}, op, shots, facts)
        fix_shots(js, shots)
        best = (js, story_errs(js, sig, h, req, facts, shots, peers, toks))
    if best is None:                                                                   # 글 호출이 세 번 모두 실패 — 장점 사실로 최소 이야기
        adv = [s for s in shots if s["adv"]] or shots
        js = {"beats": [{"lens": "훅", "line": f"{sg._cut(sig['name'], 16)}, 들어보셨어요?", "shots": [adv[0]["id"]], "fact": 0},
                        {"lens": "정체", "line": sg._cut(sg._body(sig['fact']), 28), "shots": [adv[min(1, len(adv) - 1)]["id"]], "fact": sig.get("fact_i") or 0}]
              + [{"lens": "디테일", "line": sg._cut(s["desc"], 28), "shots": [s["id"]], "fact": 0} for s in adv[2:6]]
              + [{"lens": "제안", "line": f"이번엔 {sg._cut(sig['name'], 14)} 어떠세요?", "shots": [adv[0]["id"]], "fact": 0}], "caption": {}}
        best = (js, ["글 호출 실패"])
    js, errs = best
    report["lens_check"] = {"ok": not errs, "errs": [str(e)[:120] for e in errs[:10]]}
    if errs and not op:                                                                # 운영자 대본의 문장은 고치지 않는다(검사 결과만 기록)
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
                      "actor": str(b.get("actor") or "").strip().lower(), "action_en": design.one_line(str(b.get("action_en") or "")),
                      "feature": design.one_line(str(b.get("feature") or "")),
                      **({"want": str(b.get("want"))} if b.get("want") else {})})
    route_shots(beats, shots, report)                                                  # v6 동선 규칙(코드 강제 · 0원)
    plan_visuals(beats, shots, report, ai_budget(req), dog_ok(sig))
    features = apply_features(beats, facts, toks, sig, h, req, report, bool(op and any(b.get("feature") for b in op)))   # v10 특장점 라벨(0원)
    scenes = storyboard_scenes(models, beats, shots, sig, req, report)                   # v7 씬 스토리보드(시트 이미지 · 돈)
    hook_sid = next((x for x in beats[0]["shots"] if not any(s.get("insert") for s in shots if s["id"] == x)), beats[0]["shots"][0])
    shots_desc = [{"description": next(s["desc"] for s in shots if s["id"] == hook_sid)}]
    title = pain_title(js, operator_card(h["name"]) if op else None, beats, toks, h, req, report) if ttype == "걱정형" else ""
    if not title:                                                                      # 걱정형 후보가 없으면 질문형(반전 질문)으로
        if ttype == "걱정형":
            ttype = "반전 질문"
        title = sg.ensure_sig_title(models, design.one_line(str(js.get("hook_title") or "")), [b["line"] for b in beats], shots_desc, sig, h, req, ttype, report)
    cap = js.get("caption") if isinstance(js.get("caption"), dict) else {}
    ocap = operator_caption(h["name"]) if op else None
    if ocap:
        oerrs = sg.caption_errs(ocap, h, req, sig, facts)
        report["operator_caption"] = {"ok": not oerrs, "errs": [str(e)[:100] for e in oerrs[:5]]}
        if not oerrs:
            cap = ocap
    if sg.caption_errs(cap, h, req, sig, facts):
        pts = [b["line"] for b in beats[2:5] if b["fact_i"]] or [sg._cut(sg._body(sig["fact"]), 40)]
        cap = {"hook": sg._cut(sg._body(sig["fact"]), 80), "points": pts, "save": "갈 계획이 있다면 저장해두고 다시 꺼내 보세요."}
    name_title = str(js.get("title") or sig["name"])
    if h["name"] not in name_title:
        name_title = f"{h['name']} {name_title}".strip()
    text = {"beats": beats, "hook_title": title, "hook_title_type": ttype, "scenes": scenes, "features": features,
            "caption": {"hook": design.one_line(str(cap.get("hook") or "")), "points": [design.one_line(str(x)) for x in cap.get("points") or [] if str(x).strip()][:3],
                        "save": design.one_line(str(cap.get("save") or ""))},
            "checklist": sg.grounded_checklist(js.get("checklist") or [{"fact": b["fact_i"]} for b in beats if b["fact_i"]], facts, h),
            "title": name_title[:40], "hashtags": ([t if str(t).startswith("#") else f"#{t}" for t in (js.get("hashtags") or []) if str(t).strip()] or sg.default_tags(req))[:5]}
    text["card"] = make_card(js.get("card"), operator_card(h["name"]) if op else None, facts, toks, sig, h, req, beats, text["checklist"], report)   # v9 요약 카드(0원)
    log("대본: " + " / ".join(f"[{b['lens']}] {b['line']}" for b in beats) + f" · 훅 제목 {title or '(없음)'}"
        + (f" · 요약 카드({text['card']['source']}) {text['card']['point']} / " + " / ".join(a['text'] for a in text['card']['answers']) if text.get("card") else " · 요약 카드 없음")
        + (" · 라벨 " + " / ".join(f["text"] for f in features) if features else " · 라벨 없음"))
    return text


def storyboard_scenes(models: dict, beats: list[dict], shots: list[dict] | dict, sig: dict, req: dict, report: dict) -> list[dict]:
    """v7: 컷마다 씬(사진 + 누가·동작 + 시간대) → 참조 사진별 2×2 시트(돈) → 패널 검수 → 컷 화면으로. request "storyboard": false 면 건너뜀(v6 사진 무빙)."""
    if req.get("storyboard", True) is False:
        report["storyboard"] = {"skipped": "request storyboard=false"}
        return []
    by_id = {s["id"]: s for s in (shots.values() if isinstance(shots, dict) else shots)}
    dog = dog_ok(sig)
    use_inserts = req.get("inserts", True) is not False and len(beats) >= 2
    scenes = sc.plan_scenes(beats, by_id, dog, report, end_scene=not use_inserts)        # 인서트를 쓰면 제안 컷은 인서트라 그 씬(패널·시트 값)은 만들지 않는다
    if scenes:
        sc.make_sheets(models, scenes, by_id, STORY, report)
    else:
        report["storyboard"] = {"sheets": [], "krw": 0, "scenes": []}
    # v8 C: 숙소와 무관한 감정 인서트(집 창가·현관·차창) 시트 1장 → 훅 첫 컷·제안 컷(훅 되돌아옴 대신). request "inserts": false 면 생략
    inserts = sc.plan_inserts(beats, dog) if use_inserts else []
    if inserts:
        sc.make_insert_sheet(models, inserts, STORY, report)
        added = sc.apply_inserts(beats, inserts, by_id, report, ai_budget(req))
        if added and isinstance(shots, list):                                          # 재료 목록(plan.json · report)에도 — 제작 재사용이 같은 인서트를 쓴다
            shots.extend(added)
            report.setdefault("story_shots", []).extend({k: s_.get(k) for k in ("id", "k", "kind", "desc", "zoom", "place", "grade")} for s_ in added)
    sc.apply_scenes(beats, scenes, by_id, report)
    visual_report(beats, by_id, report)
    sb = report.get("storyboard") or {}
    ins = report.get("inserts") or {}
    log(f"씬 스토리보드: 씬 {len([x for x in scenes if not x.get('spare')])}개 + 여분 {len([x for x in scenes if x.get('spare')])} · 시트 {len(sb.get('sheets') or [])}장 "
        f"· 통과 {sum(1 for x in scenes if x.get('ok'))}/{len(scenes)} · 약 {sb.get('krw', 0):,}원 · 인서트 {len(report.get('inserts_used') or [])}컷(약 {ins.get('krw', 0):,}원)")
    return [{k_: x.get(k_) for k_ in ("n", "j", "m", "sid", "k", "place", "who", "with_dog", "action_en", "time", "img", "ok", "why", "panel_px", "sheet", "spare", "angle", "minor")} for x in scenes]


# ── 4. 렌더 ─────────────────────────────────────────────────────────────────────────────
AIM_SYSTEM = """너는 쇼츠 카메라 감독이다. 세로 사진 한 장과 그 화면 동안 나올 나레이션 한 문장을 받는다.
문장이 말하는 대상(예: 계단·하우스·식기·침대·바다·탕)을 사진에서 찾아, 카메라가 **그 대상으로 크게 다가가 멈추게** 정한다.
- target: 대상의 중심 [x, y] (0~1, 왼쪽 위가 0,0). 문장 대상이 사진에 없으면 사진에서 가장 눈에 띄는 주인공 사물.
- zoom: 끝 화면 확대 정도 0.22~0.5 — 대상이 작으면 크게(0.45~0.5), 화면 절반 이상이면 작게(0.22~0.3).
- move: "in"(넓게 시작해 대상으로 다가감) 또는 "out"(대상에서 시작해 넓게 물러나 공간을 보여 줌 — 문장이 공간 전체·전망을 말할 때).
JSON 만: {"target":[0.5,0.6],"zoom":0.4,"move":"in","what":"계단"}"""


def aim_shots(models: dict, beats: list[dict], shots: dict, report: dict, skip: set | dict = ()) -> None:
    """문장마다 첫 컷 사진을 보고 카메라가 다가갈 대상을 정한다(비전 · 문장당 약 1원). 실패하면 그 문장은 기본 무빙. skip = AI 영상이 붙은 문장 번호(0부터)."""
    rows = []
    for j, b in enumerate(beats):
        sid = (b.get("shots") or [None])[0]
        if j in skip or not sid or sid not in shots or b.get("aim"):
            continue
        try:
            r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, AIM_SYSTEM, f"나레이션: {b['line']}", [sc.cut_img(b, 0, shots, STORY)]))
            x, y = [min(0.92, max(0.08, float(v))) for v in (r.get("target") or [0.5, 0.5])[:2]]
            z = min(AIM_ZOOM[1], max(AIM_ZOOM[0], float(r.get("zoom") or 0.35)))
            b["aim"] = {"x": round(x, 3), "y": round(y, 3), "zoom": round(z, 2), "move": "out" if r.get("move") == "out" else "in", "what": str(r.get("what") or "")[:20]}
        except Exception as e:  # noqa: BLE001
            b["aim"] = None
            log(f"문장 {j + 1} 카메라 대상 못 정함({str(e)[:60]}) — 기본 무빙")
        rows.append({"i": j + 1, "shot": sid, **(b.get("aim") or {})})
    report["camera_aim"] = rows


def aimed_clip(image: Path, sec: float, out: Path, aim: dict) -> Path:
    """대상 겨냥 무빙: 넓은 화면 ↔ 대상 중심 확대(1.22~1.5배)를 가속·감속으로. 화면 중심이 대상 쪽으로 같이 옮겨 간다(원본 픽셀만)."""
    F = max(2, int(round(sec * ms.FPS)))
    t = f"(on/{F})"
    e = f"(1-pow(1-{t},3))" if aim["move"] == "in" else f"(1-{t}*{t}*(3-2*{t}))"   # in: 빨리 다가가 천천히 멈춤 / out: 대상에서 부드럽게 물러남
    Z, tx, ty = aim["zoom"], aim["x"], aim["y"]
    z = f"1.0+{Z}*{e}"
    x = f"clip((0.5+({tx}-0.5)*{e})*iw-iw/zoom/2,0,iw-iw/zoom)"
    y = f"clip((0.5+({ty}-0.5)*{e})*ih-ih/zoom/2,0,ih-ih/zoom)"
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(ms.FPS), "-i", str(image),
            "-vf", f"scale=2160:3840:flags=lanczos,zoompan=z='{z}':x='{x}':y='{y}':d={F}:s=1080x1920:fps={ms.FPS},setsar=1",
            "-frames:v", str(F), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)])
    return out


def cut_secs(ids: list[str], shots: dict, L: float) -> list[float]:
    """문장 길이 L 을 컷들에 나눈다 — 짧은 인서트(작은 패널)는 INSERT_MAX 까지만, 나머지는 첫 컷이 넉넉히."""
    n = len(ids)
    if n == 1:
        return [L]
    ins = [shots.get(x, {}).get("grade") == "insert" for x in ids]
    secs = [0.0] * n
    rest = L
    for m in range(n):
        if ins[m]:
            secs[m] = max(SHOT_MIN, min(INSERT_MAX, L * 0.4)); rest -= secs[m]
    k = sum(1 for v in ins if not v) or n
    for m in range(n):
        if not ins[m]:
            secs[m] = max(SHOT_MIN, rest / k)
    return secs


def beat_clip(beat: dict, shots: dict, L: float, out: Path, j: int) -> tuple[Path, str]:
    """문장 하나의 화면 — 컷이 여러 개면 길이를 나눠 사진 무빙을 이어 붙인다(원본 픽셀만)."""
    ids = beat["shots"]
    parts, n = [], len(ids)
    secs = cut_secs(ids, shots, L)
    for m, sid in enumerate(ids):
        sec = secs[m]
        pat = PATTERNS[(j + m) % len(PATTERNS)]
        img = sc.cut_img(beat, m, shots, STORY)
        if m == 0 and beat.get("aim"):
            parts.append(aimed_clip(img, sec, STORY / f"pan_{j}_{m}.mp4", beat["aim"]))
        else:
            parts.append(sg.photo_clip(img, sec, STORY / f"pan_{j}_{m}.mp4", pat, MOTION))
    ks = beat.get("cut_kinds") or []
    sbk = (" · AI 스토리보드" if any(str(x).startswith("AI 스토리보드") for x in ks) else "") + (" · 인서트" if any(str(x).startswith("인서트") for x in ks) else "")
    if len(parts) == 1:
        a = beat.get("aim")
        return parts[0], (f"사진 무빙·{a['what'] or '대상'} {'다가감' if a['move'] == 'in' else '물러남'} {1 + a['zoom']:.2f}배" if a else f"사진 무빙·{PATTERNS[j % len(PATTERNS)]}") + sbk
    lst = STORY / f"beat_{j}.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")
    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    return out, f"사진 무빙 {n}컷" + sbk


def ai_budget(req: dict) -> int:
    """request "ai_cuts" — 없으면 기본 6, 0 이면 AI 컷 없음(사진 무빙만 · Veo 0원)."""
    v = req.get("ai_cuts")
    return AI_CUTS_DEFAULT if v is None or v == "" else max(0, int(v))


def card_segment(card: dict, photo: Path, L: float, disclosure: str, after: int, report: dict) -> tuple[Path, dict]:
    """v9 요약 카드 3초(음악만): 장점 사진 약한 블러·어둡기 배경(1.04배 느린 밀기) 위에 유리 칩 프레임 → 포인트 줄 → 답 줄들이 0.3초 간격으로 올라온다.
    자막·장소 라벨·어둡기 띠 없음(화면 글자 = 카드 + 고지문만)."""
    answers = [a["text"] for a in card["answers"]]
    eyebrow = card.get("eyebrow") or design.CARD_EYEBROW
    lay = design.card_layers(STORY, photo, card["point"], answers, eyebrow)
    clip = sg.photo_clip(lay["bg"], L, STORY / "card_bg.mp4", "push", 0.04)
    frame_nb = design.frame_png(STORY / "ov_frame_card.png", disclosure, band=False)
    overlays = [{"path": frame_nb, "a": 0, "b": 99, "anim": False}, {"path": lay["frame"], "a": 0.0, "b": 99, "anim": True, "fade": 0.22, "slide": 10}]
    t, step = 0.32, (0.30 if L >= 2.9 else 0.25)
    for p in lay["lines"]:
        overlays.append({"path": p, "a": round(t, 2), "b": 99, "anim": True, "fade": 0.16, "slide": 14}); t += step
    seg = so.cut_segment(150, clip, L, None, overlays)
    design.card_flat(STORY / "card_flat.jpg", photo, card["point"], answers, eyebrow)
    report["card"] = {"point": card["point"], "answers": card["answers"], "eyebrow": eyebrow, "source": card.get("source"), "sec": round(L, 2), "after": after}
    return seg, {"i": "요약", "lens": "요약 카드", "kind": f"요약 카드 · 걱정 → 답 {len(answers)}줄 · 음악만", "sec": round(L, 2), "narration": "",
                 "card": {"eyebrow": eyebrow, "point": card["point"], "answers": answers}}


def dog_ok(sig: dict) -> bool:
    """강아지 컷은 반려견이 장점일 때만(다른 숙소에 실사 강아지를 넣으면 '반려견 가능'으로 오해)."""
    return bool(DOG_RX.search(" ".join(str(sig.get(k) or "") for k in ("name", "what", "fact"))))


def valid_visual(b: dict, dog: bool) -> dict | None:
    """문장에 붙은 actor·action_en 이 규칙에 맞으면 {"actor","action_en"}, 아니면 None(코드가 기본값을 고른다)."""
    actor = str(b.get("actor") or "").strip().lower()
    act = design.one_line(str(b.get("action_en") or "")).rstrip(". ")
    if actor not in ACTORS or (actor == "dog" and not dog):
        return None
    if not act:
        act = DEFAULT_ACTION[actor]
    if not (8 <= len(act) <= 200) or not act.isascii() or ACTOR_BAN[actor].search(act):
        return None
    out = {"actor": actor, "action_en": act}
    if actor == "couple" and dog and DOG_RX.search(str(b.get("line") or "") + " " + act):   # 문장이나 동작에 강아지가 있으면 함께 걷는다
        out["with_dog"] = True
    return out


def plan_visuals(beats: list[dict], shots: list[dict] | dict, report: dict, budget: int = AI_CUTS_DEFAULT, dog: bool = False) -> None:
    """v5 화면 계획(0원): 문장마다 A(사람·강아지 AI) / B(환경 AI) / C(겨냥 사진 무빙) / R(훅 AI 컷 재사용 = 되돌아옴).
    훅·'순간' 문장은 AI, '장소' 문장은 C, 제안은 R. 예산(budget)은 훅 → 사람·강아지 → 환경 순. 모델이 actor 를 안 주거나 규칙 밖이면 코드가 기본값을 고른다."""
    n = len(beats)
    warns = []
    by_id0 = {s["id"]: s for s in (shots.values() if isinstance(shots, dict) else shots)}
    for j, b in enumerate(beats):
        lens = str(b.get("lens") or "")
        v = valid_visual(b, dog)
        first = by_id0.get((b.get("shots") or [None])[0]) or {}
        b.pop("hook_keep", None)
        if (j == n - 1 and lens in END_LENSES) or lens in PLACE_LENSES:
            v = None
        elif j == 0 and not first.get("insert") and DOG_RX.search(str(first.get("desc") or "")) and str(b.get("actor") or "").lower() in ("", "none"):
            v = None                                                                   # v6: 훅 사진에 실제 강아지가 이미 있으면 AI 로 건드리지 않는다(사진 무빙)
            b["hook_keep"] = "사진에 이미 강아지"
        elif v is None and (j == 0 or lens in MOMENT_LENSES):
            if dog and DOG_RX.search(str(b.get("line") or "")):
                actor = "dog"
            elif lens in ("행동", "디테일"):
                actor = "hand"
            else:
                actor = "env"
            v = {"actor": actor, "action_en": DEFAULT_ACTION[actor], "auto": True}
            if b.get("actor") and lens != "훅":
                warns.append(f"문장 {j + 1} 화면 지시 '{b.get('actor')}: {str(b.get('action_en') or '')[:40]}' 규칙 밖 → 코드가 {ACTOR_KO[actor]}")
        b["visual"] = v
    cands = [j for j, b in enumerate(beats) if b.get("visual")]
    order = sorted(cands, key=lambda j: (j != 0, beats[j]["visual"]["actor"] == "env", j))
    chosen = set(order[:max(0, int(budget))])
    for j, b in enumerate(beats):
        v = b.get("visual")
        if v and j in chosen:
            v["type"] = "B" if v["actor"] == "env" else "A"
        elif v:
            v["type"] = "C"; v["skipped"] = "AI 컷 예산 밖"
        else:
            b["visual"] = {"type": "C"}
    for b in beats:                                                                    # v6: A/B 문장의 둘째 컷은 AI 뒤에 붙는 다른 사진(꼬리)
        if b["visual"]["type"] in ("A", "B") and len(b.get("shots") or []) > 1:
            b["visual"]["tail"] = b["shots"][1]
    types = [b["visual"]["type"] for b in beats]
    for j in range(1, n - 1):
        if types[j] == "C" and types[j - 1] == "C":
            warns.append(f"문장 {j}·{j + 1} 사진 무빙이 연속(예산 {budget}컷)")
            break
    by_id = {s["id"]: s for s in (shots.values() if isinstance(shots, dict) else shots)}
    cnt: dict[int, int] = {}
    for b in beats:                                                                # 같은 사진의 **사진 무빙** 컷만 센다(AI 컷은 사람·강아지·빛으로 화면이 달라진다 · A/B 의 꼬리 컷은 센다)
        if b["visual"]["type"] == "R":
            continue
        for x in (b.get("shots") or [])[1 if b["visual"]["type"] in ("A", "B") else 0:]:
            if x in by_id and by_id[x]["k"] >= 0:
                cnt[by_id[x]["k"]] = cnt.get(by_id[x]["k"], 0) + 1
    over = {k: c for k, c in cnt.items() if c > 2}
    if over:
        warns.append(f"같은 사진의 사진 무빙 컷이 3개 이상 {over} — 사진 부족(#54 같은 그림 반복)")
    visual_report(beats, by_id, report, warns)


def visual_report(beats: list[dict], by_id: dict, report: dict, warns: list[str] | None = None) -> None:
    """화면 계획 보고(0원) — 인서트가 끼어든 뒤(storyboard_scenes)에도 다시 부른다."""
    report["visual_plan"] = [{"i": j + 1, "lens": b.get("lens"), "type": b["visual"]["type"], "actor": b["visual"].get("actor"),
                              "action_en": b["visual"].get("action_en"), "auto": bool(b["visual"].get("auto")), "shot": (b.get("shots") or [None])[0],
                              "shots": list(b.get("shots") or []), "tail": b["visual"].get("tail"), **({"keep": b["hook_keep"]} if b.get("hook_keep") else {}),
                              **({"insert": b["insert"]} if b.get("insert") else {})}
                             for j, b in enumerate(beats)]
    if warns is not None:
        report["visual_warnings"] = warns
    report["ai_cuts"] = sum(1 for b in beats if b["visual"]["type"] in ("A", "B"))
    report["cut_count"] = sum(len(b.get("shots") or []) for b in beats)
    report["places"] = sorted({by_id[x].get("place") or "-" for b in beats for x in (b.get("shots") or []) if x in by_id and not by_id[x].get("insert")})
    log("화면 계획: " + " ".join(f"{j + 1}{b['visual']['type']}" + (f"({ACTOR_KO[b['visual']['actor']]})" if b["visual"].get("actor") else "") + ("(인서트)" if b.get("insert") else "")
                               for j, b in enumerate(beats)) + (f" · 경고 {warns}" if warns else ""))


PERSON_PROMPT_IN = {                                                                 # v7: 스토리보드 패널에서 시작 — 손·사람이 첫 장면에 이미 있다
    "hand": ("Camera: steady and locked-off, no camera movement. The single adult hand and forearm already visible at the bottom edge of the first frame {action}, "
             "then rests naturally. Nothing else of the person ever appears. Realistic skin, same size as in the first frame. "
             "Keep every object, structure, surface and the view exactly as in the first frame; do not add any new objects, other people or text."),
    "back": ("Camera: steady, a very slow push-in. The one adult already in the first frame, seen strictly from behind (back of the head and shoulders, the face is never shown), "
             "stays where they are and {action}. They never turn around. Keep every object, structure, surface and the view exactly as in the first frame; "
             "do not add any new objects, other people or text."),
}
DOG_PROMPT_IN = ("Camera: steady and locked-off, no camera movement. The small cream-white toy poodle already in the first frame — a real, living dog with soft curly fur "
                 "and a coral-red collar, at true small-dog size for the furniture — {action}. Natural, unhurried dog movement; it stays the same dog for the whole clip. "
                 "No people appear, not even a hand. Keep every object, structure, surface and the view exactly as in the first frame; do not add any new objects, other animals or text.")


def visual_prompt(v: dict, shot: dict) -> str:
    actor, act = v["actor"], v["action_en"]
    in_frame = bool(v.get("in_frame"))                                               # 사람·강아지 패널이 통과해 그 패널에서 시작할 때만(apply_scenes) — 여분 패널·원본이면 '들어온다' 지시문
    if actor in PERSON_PROMPT:
        return (PERSON_PROMPT_IN if in_frame else PERSON_PROMPT)[actor].format(action=act)
    if actor == "couple":
        return mm.real_back_prompt(act, dog=bool(v.get("with_dog")), in_frame=in_frame)
    if actor == "dog":
        return (DOG_PROMPT_IN if in_frame else DOG_PROMPT).format(action=act)
    if v.get("auto"):                                                              # 기본 환경 컷 = 사진 분류가 준 카메라·자연 움직임(run-4·23·33 검증)
        cat = shot.get("category") if shot.get("category") in photos.CATS else "special"
        return photos.prompt_for({"veo_prompt": shot.get("veo_prompt") or "", "category": cat})
    return ENV_STORY.format(action=act) + photos.SUFFIX


def visual_check(models: dict, first: Path, clip: Path, j: int, v: dict) -> dict:
    """AI 컷 비전 검수(약 1원) — 첫 장면·2초·끝 장면. 판정은 코드가: 기대한 사람 수·얼굴 없음·강아지 수·새 사물·구조 변화·이상한 몸·실사 여부."""
    frames = []
    for k, t in enumerate((0.1, 2.0, 3.8)):
        f = STORY / f"pchk_{j}_{k}.jpg"
        ms.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(clip), "-frames:v", "1", "-vf", "scale=540:-2", str(f)])
        if f.exists():
            frames.append(f)
    if len(frames) < 2:
        return {"ok": False, "reason": "프레임을 못 뽑음"}
    actor = v["actor"]
    expect = EXPECT_KO[actor] + (" + 작은 강아지 한 마리" if v.get("with_dog") else "")
    try:
        r = ms._try_models("vision", models["text"], lambda m: sg._json_vision(m, VISUAL_CHECK_SYSTEM.format(expect=expect), f"기대: {expect}", frames))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"검수 호출 실패: {str(e)[:60]}"}
    probs = []
    ppl = r.get("people")
    pstr = str(ppl).strip().lower()
    want_dogs = 1 if (actor == "dog" or v.get("with_dog")) else 0
    if actor == "hand":
        ok_p = pstr in ("hand", "0", "1", "none")
    elif actor == "back":
        ok_p = pstr == "1"
    elif actor == "couple":
        ok_p = pstr == "2"
    else:
        ok_p = pstr in ("0", "none", "")
    if not ok_p:
        probs.append(f"사람 {ppl}")
    if r.get("face_visible"):
        probs.append("얼굴 보임")
    try:
        dogs = int(r.get("dogs") or 0)
    except (TypeError, ValueError):
        dogs = 0
    if dogs != want_dogs:
        probs.append(f"강아지 {dogs}마리(기대 {want_dogs})")
    if r.get("new_objects"):
        probs.append("새 사물: " + ", ".join(map(str, r["new_objects"]))[:60])
    if r.get("structure_changed"):
        probs.append("구조 변경")
    if r.get("weird"):
        probs.append("몸·손 모양 이상")
    if r.get("looks_real") is False and actor != "env":
        probs.append("실사처럼 안 보임")
    return {"ok": not probs, "reason": "; ".join(probs)[:160], "raw": {k: r.get(k) for k in ("people", "face_visible", "dogs", "new_objects", "structure_changed", "weird", "looks_real", "why")}}


def ai_beats(beats: list[dict], shots: dict, report: dict, theme: str, models: dict | None = None) -> dict:
    """제작 때만: 화면 계획의 A/B 문장을 Veo 4초로(R 은 훅 컷 재사용 0원). 검수 탈락·실패한 컷은 사진 무빙. 재사용 클립(veo_b<j>.mp4)은 0원."""
    clips, rows, stopped = {}, [], None
    for j, b in enumerate(beats):
        v = b.get("visual") or {}
        t = v.get("type")
        if t not in ("A", "B", "R"):
            continue
        s = shots[b["shots"][0]]
        out = STORY / f"veo_b{j}.mp4"
        row = {"i": j + 1, "lens": b["lens"], "shot": s["id"], "type": t, "actor": v.get("actor"), "ok": False, "krw": 0}
        if t == "R":
            if clips.get(0):
                clips[j] = clips[0]; row.update({"ok": True, "reused_hook": True})
            else:
                row["error"] = "훅 AI 컷이 없어 사진 무빙"
            rows.append(row); continue
        if out.exists() and out.stat().st_size > 0:
            clips[j] = out; row.update({"ok": True, "reused": True}); rows.append(row); continue
        if stopped:
            row["error"] = f"한도: {stopped}"; rows.append(row); continue
        small = STORY / f"veo_in_{j}.png"
        start = v.get("start_img") or s["img"]
        row["start"] = start                                                               # v7: 통과한 스토리보드 패널이면 그 장면(사람·강아지가 이미 있음)에서 시작
        Image.open(STORY / start).convert("RGB").resize((720, 1280), Image.LANCZOS).save(small, "PNG")
        try:
            prompt = visual_prompt(v, s)
        except RuntimeError as e:                                                 # 금지 낱말(커플 지시문) — 돈 쓰기 전에 그 컷만 사진 무빙
            row["error"] = f"지시문 거부: {str(e)[:100]}"; rows.append(row); continue
        (STORY / f"veo_prompt_{j}.txt").write_text(prompt, encoding="utf-8")
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
        if row["ok"] and t == "A":                                                # 사람·강아지 컷은 영상 뒤 비전 검수(약 1원) — 탈락이면 버린다(값은 이미 나감)
            chk = visual_check(models, small, out, j, v)
            row["check"] = chk
            if not chk.get("ok"):
                row["ok"] = False
                row["error"] = f"검수 탈락: {chk.get('reason')}"
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
    beats = text["beats"]
    clips = {} if preview else ai_beats(beats, shots, report, str(req.get("theme") or ""), models)
    if preview:
        report["veo"] = {"model": veo.MODEL, "fake": veo.FAKE, "clips": [], "spent_krw": 0, "month_total_krw": round(veo.month_total())}
    frame = STORY / "ov_frame.png"
    ai_any = any(r.get("ok") and r.get("type") in ("A", "B") for r in (report.get("veo") or {}).get("clips", []))
    disc_text = ms.DISCLOSURE + ("  ·  " + AI_NOTE if ai_any else "")
    design.frame_png(frame, disc_text)                                                 # 고지문 줄(GRID 고정 자리)에 'AI 연출' — 새 글자 유형을 만들지 않는다
    report["ai_note_on_screen"] = ai_any
    if models:
        aim_shots(models, beats, shots, report, skip=clips)
    segs, timeline = [], []
    n_beats = len(beats)
    hook_sid = next((x for b in beats for x in b["shots"] if x in shots and not shots[x].get("insert") and shots[x].get("adv")),
                    next((x for b in beats for x in b["shots"] if x in shots and not shots[x].get("insert")), beats[0]["shots"][0]))
    hook_img = STORY / shots[hook_sid]["img"]                                         # 끝 카드·요약 카드 배경 = 숙소 장점 사진(인서트는 집·차 안이라 제외)
    card = text.get("card") if req.get("card", CARD_DEFAULT) is True else None          # v9 요약 카드(v10.1 재설계 · 기본 켜짐 · request card:false 로 끔): 조건 문장 뒤 · 음악만
    card_after, card_sec = None, CARD_SEC
    if card and card.get("answers"):
        idx = [j for j, b in enumerate(beats) if str(b.get("lens") or "") == "조건"]
        card_after = idx[-1] if idx else max(0, n_beats - 2)
        narr_total = sum(float(narr.get(i) or narr.get(str(i)) or 2.0) for i in range(1, n_beats + 1))
        card_sec = CARD_SEC if narr_total <= CARD_NARR_LIMIT else CARD_SEC_SHORT
    for j, b in enumerate(beats):
        i = j + 1
        wav = B / f"narr_c{i}.wav"
        L = max(MIN_HOOK if j == 0 else 0.0, float(narr.get(i) or narr.get(str(i)) or 2.0) + 0.12, SHOT_MIN * len(b["shots"]))
        overlays = [{"path": frame, "a": 0, "b": 99, "anim": False}]
        if j == 0 and text.get("hook_title"):
            ttl = STORY / "ov_title.png"
            design.hook_title_png(ttl, text["hook_title"], "box" if text.get("hook_title_type") == "걱정형" else "shadow")   # v10.1 걱정형 = 줄마다 어두운 상자(레퍼런스 표지 방식)
            overlays.append({"path": ttl, "a": 0.0, "b": 99, "anim": False})
        feat = str(b.get("feature") or "")
        if feat:                                                                       # v10 특장점 라벨 — 장소 라벨 자리(왼쪽 72px 코랄) · 같은 라벨이 이어지는 문장에선 애니메이션 없이 그대로
            fo = STORY / f"ov_feat_{i:02d}.png"
            design.feature_png(fo, feat)
            first = not (j > 0 and str(beats[j - 1].get("feature") or "") == feat)
            overlays.append({"path": fo, "a": 0.0, "b": 99, "anim": True, "fade": 0.22, "slide": 10} if first else {"path": fo, "a": 0.0, "b": 99, "anim": False})
        chunks = so.karaoke_times(b["line"], wav, L)
        for k, (txt, ta, tb) in enumerate(chunks):
            capk = STORY / f"ov_cap_{i:02d}_{k}.png"
            design.subtitle_png(capk, txt)
            overlays.append({"path": capk, "a": ta, "b": tb, "anim": True, "fade": 0.05, "slide": 8})
        slow = 1.0
        v = b.get("visual") or {}
        ncut = len(b.get("shots") or [])
        if j in clips:
            src = clips[j]
            avail = ms.probe_duration(src)
            tail = v.get("tail") if v.get("type") in ("A", "B") else None
            if tail and tail in shots and L >= AI_PART[0] + TAIL_MIN and avail >= AI_PART[0]:
                # v6: AI 영상은 앞 2.0~2.6초만(뒷부분은 원본에서 멀어진다) + 나머지는 다른 사진의 무빙 컷 → 컷이 하나 더 늘고 비용은 같다
                ai = min(avail, max(AI_PART[0], min(AI_PART[1], L - TAIL_MIN)))
                if shots[tail].get("grade") == "insert" and L - ai > INSERT_MAX:
                    ai = min(avail, L - INSERT_MAX)
                tail_sec = max(TAIL_MIN, L - ai)
                head = STORY / f"ai_{j}.mp4"
                ms.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", f"{ai:.2f}", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                        "-pix_fmt", "yuv420p", "-r", str(ms.FPS), "-vf", "scale=1080:1920,setsar=1", str(head)])
                tail_clip = sg.photo_clip(sc.cut_img(b, 1, shots, STORY), tail_sec, STORY / f"pan_{j}_t.mp4", PATTERNS[(j + 1) % len(PATTERNS)], MOTION)
                lst = STORY / f"beat_{j}.txt"
                lst.write_text(f"file '{head.resolve()}'\nfile '{tail_clip.resolve()}'\n", encoding="utf-8")
                src = STORY / f"beat_{j}.mp4"
                ms.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(src)])
                kind = f"AI 영상·{ACTOR_KO.get(v.get('actor'), '')} {ai:.1f}초 + 사진 무빙({shots[tail].get('place') or ''})"
                ncut = 2
            elif v.get("type") == "R":
                start = min(1.0, max(0.0, avail - L))                                  # 훅 영상의 뒤쪽을 쓴다(첫 장면과 똑같은 그림 반복을 피함)
                if start > 0.05:
                    cut = STORY / f"ai_{j}.mp4"
                    ms.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.2f}", "-i", str(src), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                            "-pix_fmt", "yuv420p", "-r", str(ms.FPS), "-vf", "scale=1080:1920,setsar=1", str(cut)])
                    src, avail = cut, ms.probe_duration(cut)
                kind = "훅 컷 재사용(되돌아옴)"
                slow = min(1.25, L / avail) if L > avail else 1.0
                ncut = 1
            else:
                kind = f"AI 영상·{ACTOR_KO.get(v.get('actor'), '')}"
                slow = min(1.25, L / avail) if L > avail else 1.0
                ncut = 1
        else:
            src, kind = beat_clip(b, shots, L, STORY / f"beat_{j}.mp4", j)
            if preview and v.get("type") in ("A", "B", "R"):
                kind += " (제작 때 " + ("훅 컷 재사용" if v["type"] == "R" else "AI " + ACTOR_KO.get(v.get("actor"), "") + (f" {AI_PART[1]:.1f}초 + 사진 무빙" if v.get("tail") else "")) + ")"
        segs.append(so.cut_segment(100 + i, src, L, wav if wav.exists() else None, overlays, slow))
        timeline.append({"i": i, "lens": b["lens"], "kind": kind, "sec": round(L, 2), "shots": b["shots"], "cuts": ncut, "narration": b["line"],
                         "places": [shots[x].get("place") for x in b["shots"] if x in shots], "feature": feat or None,
                         "title": text["hook_title"] if j == 0 else None, "chunks": [[t, a, c] for t, a, c in chunks]})
        if card_after == j:
            seg, row = card_segment(card, hook_img, card_sec, disc_text, j + 1, report)
            segs.append(seg); timeline.append(row)
    card = design.end_card(STORY / "end_card.jpg", hook_img, folder, pos, style, ms.DISCLOSURE)
    Lc = max(3.6, float(narr.get("cta") or 2.5) + 0.7)
    cta_wav = B / "narr_cta.wav"
    segs.append(so.cut_segment(199, card, Lc, cta_wav if cta_wav.exists() else None, [], image=True, fade_in=0.3))
    timeline.append({"i": "끝", "lens": "끝 카드", "kind": "카드", "sec": round(Lc, 2), "narration": so.cta_text(folder, pos)})
    report["cut_count"] = sum(int(t.get("cuts") or 0) for t in timeline if t.get("cuts"))
    report["places"] = sorted({pl for t in timeline for pl in (t.get("places") or []) if pl and pl != "인서트"})
    log(f"컷 {report['cut_count']}개 · 장소 {len(report['places'])}곳 {report['places']}")
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
    cd = report.get("card") if (report.get("card") or {}).get("point") and (STORY / "card_flat.jpg").exists() else None
    im = Image.new("RGB", (pad * 2 + tw * 3 + 8 * 2 + pad + tx, pad + (len(beats) + (1 if cd else 0)) * rowh), (18, 20, 26))
    d = ImageDraw.Draw(im)
    f_lens, f_line, f_small = design.font(26), design.font(34), design.font(22, bold=False)
    veo_rows = {r["i"]: r for r in (report.get("veo") or {}).get("clips", [])}
    for r, b in enumerate(beats):
        y = pad + r * rowh
        for m, sid in enumerate(b["shots"][:3]):
            try:
                im.paste(Image.open(sc.cut_img(b, m, shots, STORY)).convert("RGB").resize((tw, th), Image.LANCZOS), (pad + m * (tw + 8), y))
                ck = (b.get("cut_kinds") or [""] * 3)[m] if m < len(b.get("cut_kinds") or []) else ""
                if ck:
                    d.rectangle((pad + m * (tw + 8), y + th - 24, pad + m * (tw + 8) + tw, y + th), fill=(0, 0, 0))
                    d.text((pad + m * (tw + 8) + 4, y + th - 22), ("AI " + ck.split(" ", 2)[-1] if ck.startswith("AI") else ck)[:16], font=design.font(18, bold=False),
                           fill=(94, 234, 212) if ck.startswith("AI") else (255, 170, 120))
                if m == 0 and b.get("feature"):                                        # v10 특장점 라벨(화면 왼쪽 장소 라벨 자리)
                    d.rectangle((pad, y, pad + tw, y + 24), fill=(0, 0, 0))
                    d.text((pad + 4, y + 2), f"라벨 {b['feature']}"[:16], font=design.font(18, bold=False), fill=(255, 138, 91))
            except Exception:  # noqa: BLE001
                d.rectangle((pad + m * (tw + 8), y, pad + m * (tw + 8) + tw, y + th), fill=(40, 40, 48))
        x = pad * 2 + tw * 3 + 16
        vr = veo_rows.get(r + 1)
        v = b.get("visual") or {}
        who = ACTOR_KO.get(v.get("actor"), "")
        if vr and vr.get("ok"):
            tag = " · 훅 컷 재사용" if v.get("type") == "R" else f" · AI {who}"
        elif v.get("type") in ("A", "B"):
            tag = f" · 제작 때 AI {who}" + ("(코드가 고름)" if v.get("auto") else "")
        elif v.get("type") == "R":
            tag = " · 제작 때 훅 컷 재사용"
        else:
            tag = " · 사진 무빙"
        pls = "·".join(dict.fromkeys(str(shots[x].get("place") or "") for x in b["shots"] if x in shots))
        d.text((x, y + 6), f"{r + 1} · {b['lens']}{tag} · {pls}"[:34], font=f_lens, fill=(94, 234, 212))
        yy = y + 46
        line = b["line"]
        for ln in [line[k:k + 17] for k in range(0, len(line), 17)][:3]:
            d.text((x, yy), ln, font=f_line, fill=(255, 255, 255)); yy += 44
        basis = "근거: " + (sg._body(b["fact"]) if b["fact"] else "사진에 보이는 것")
        for ln in [basis[k:k + 26] for k in range(0, len(basis), 26)][:2]:
            d.text((x, yy + 6), ln, font=f_small, fill=(190, 190, 200)); yy += 30
        cuts = " / ".join(f"{sid} {shots[sid]['kind']}" for sid in b["shots"])
        d.text((x, yy + 10), cuts[:40], font=f_small, fill=(140, 140, 150))
    if cd:                                                                              # v9 요약 카드 행(문장 사이 · 음악만)
        y = pad + len(beats) * rowh
        try:
            im.paste(Image.open(STORY / "card_flat.jpg").convert("RGB").resize((tw, th), Image.LANCZOS), (pad, y))
        except Exception:  # noqa: BLE001
            d.rectangle((pad, y, pad + tw, y + th), fill=(40, 40, 48))
        x = pad * 2 + tw * 3 + 16
        d.text((x, y + 6), f"요약 카드 · 문장 {cd.get('after')} 뒤 · {cd.get('sec')}초 · 음악만 · {cd.get('source')}"[:34], font=f_lens, fill=(94, 234, 212))
        yy = y + 46
        d.text((x, yy), f"{cd.get('eyebrow') or ''}: {cd['point']}"[:19], font=f_line, fill=(255, 255, 255)); yy += 44
        for a in cd.get("answers") or []:
            d.text((x, yy), f"- {a['text']}"[:19], font=f_line, fill=(255, 255, 255)); yy += 44
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
    mat = report.get("material") or {}
    if mat:
        md += ["## 재료 (v6 동선)", "",
               f"- 장면 사진 {mat.get('photos')}장 · 장소 {len(mat.get('places') or [])}곳 {', '.join(mat.get('places') or [])} · 짧은 인서트 패널 {mat.get('inserts', 0)}장"
               f" · 콜라주 패널 {mat.get('panels', 0)}장 · 안내문 {mat.get('notices_read', 0)}장 읽음(사실 {mat.get('notice_facts', 0)}개)",
               f"- 영상: 컷 {report.get('cut_count', 0)}개 · 장소 {len(report.get('places') or [])}곳 {', '.join(report.get('places') or [])}"]
        for c in mat.get("closures") or []:
            md.append(f"- 제외: {c}")
        if report.get("material_warning"):
            md.append(f"- **경고: {report['material_warning']}**")
        for c in (report.get("route_changes") or [])[:8]:
            md.append(f"- 동선 고침: {c}")
        md.append("")
    nf = list(h.get("notice_facts") or [])
    if nf:
        md += ["## 공식 안내문에서 읽은 사실", "", *[f"- {f}" for f in nf[:14]], ""]
    of = report.get("operator_facts") or {}
    if of.get("facts"):
        md += [f"## 운영자 확인 사실 (공식 홈페이지 안내문을 운영자가 읽어 적음 · {of.get('note') or '출처 메모 없음'})", "", *[f"- {sg._body(f)}" for f in of["facts"]], ""]
    sb = report.get("storyboard") or {}
    scn = [x for x in (text.get("scenes") or []) if x.get("j") is not None]
    if sb.get("sheets") is not None or scn:
        md += [f"## 씬 스토리보드 (v7 · 시트 {len(sb.get('sheets') or [])}장 · 약 {sb.get('krw', 0):,}원 · 통과 {sum(1 for x in scn if x.get('ok'))}/{len(scn)})", "",
               "| 문장 | 컷 | 장소 | 누가·동작 | 카메라 | 시간대 | 패널 | 결과 |", "|---|---|---|---|---|---|---|---|"]
        for x in scn:
            who = sc.WHO_KO.get(x.get("who"), "") + ("+강아지" if x.get("with_dog") else "")
            ang = "원본 각도" if x.get("angle") == sc.SAME_ANGLE else str(x.get("angle") or "")[:34]
            res = ("통과" + (f" (소품: {x['minor']})" if x.get("minor") else "")) if x.get("ok") \
                else ("원본 사진(꼬리 컷 · 시트 생략으로 돈 절약)" if "시트 생략" in str(x.get("why") or "") else "탈락 → 여분 패널·원본 (" + str(x.get("why") or "")[:40] + ")")
            md.append(f"| {x['j'] + 1} | {x['m'] + 1} | {x.get('place') or '-'} | {who}{(' · ' + str(x.get('action_en') or '')[:50]) if x.get('action_en') else ''} | {ang} | {sc.TIME_KO.get(x.get('time'), '')} "
                      f"| {x.get('panel_px') or 0}px | {res} |")
        for sh in sb.get("sheets") or []:
            if not sh.get("ok"):
                md.append(f"- 시트 {sh['n']} 실패: {sh.get('error')}")
        md += ["", "- 통과한 패널이 그 컷의 화면(스틸 무빙)이 되고, 제작 때 사람·강아지 씬은 그 패널에서 Veo 영상이 시작됩니다. 환경 씬은 원본과 다른 카메라 위치(v8).",
               "- 탈락한 패널은 같은 사진의 여분 패널로, 원본 사진은 영상 전체에서 한 번만 씁니다(이미 쓴 사진의 컷은 뺍니다)."]
        for d in (report.get("scene_drops") or [])[:6]:
            md.append(f"- 뺀 컷: {d}")
        md.append("")
    ins = report.get("inserts") or {}
    if ins.get("items"):
        used = set(report.get("inserts_used") or [])
        md += [f"## 감정 인서트 (v8 · 숙소 아님 · 시트 1장 약 {ins.get('krw', 0):,}원)", "", "| # | 쓰임 | 장면 | 결과 |", "|---|---|---|---|"]
        for x in ins["items"]:
            use = {"hook": "훅 첫 컷", "end": "제안 컷"}.get(x.get("role"), "예비") + (" · 사용" if f"INS{x.get('n')}" in used else "")
            md.append(f"| {x.get('n')} | {use} | {x.get('name')} — {str(x.get('what') or '')[:40]} | {'통과' if x.get('ok') else '탈락 (' + str(x.get('why') or '')[:30] + ')'} |")
        md += ["", "- 훅은 집·차 안의 '걱정' 장면에서 숙소로, 제안은 '떠남' 장면으로 끝납니다(훅 사진 되돌아옴 폐기).", ""]
    md += ["## 이야기 (관점별 한 문장)", "", "| # | 관점 | 문장 | 컷 | 장소 | 근거 |", "|---|---|---|---|---|---|"]
    for j, b in enumerate(text["beats"], 1):
        cuts = ", ".join(x + "(" + shots[x]["kind"] + ")" for x in b["shots"])
        pls = " → ".join(dict.fromkeys(str(shots[x].get("place") or "-") for x in b["shots"]))
        basis = sg._body(b["fact"])[:36] if b["fact"] else "사진에 보이는 것"
        md.append(f"| {j} | {b['lens']} | {b['line']} | {cuts} | {pls} | {basis} |")
    vp = report.get("visual_plan") or []
    if vp:
        md += ["", f"## 화면 계획 (제작 때 AI 컷 {report.get('ai_cuts', 0)}개 · 약 {294 * int(report.get('ai_cuts') or 0):,}원)", "",
               "| # | 관점 | 화면 | 동작 |", "|---|---|---|---|"]
        for r in vp:
            kind = {"A": "AI " + ACTOR_KO.get(r.get("actor"), ""), "B": "AI 환경", "C": "사진 무빙", "R": "훅 컷 재사용(되돌아옴)"}.get(r["type"], r["type"])
            if r.get("tail") and r["type"] in ("A", "B"):
                kind += f" {AI_PART[1]:.1f}초 + 사진 무빙"
            if r.get("keep"):
                kind += f" ({r['keep']})"
            if r.get("insert"):
                kind += f" (인서트 {r['insert']})"
            md.append(f"| {r['i']} | {r['lens']} | {kind}{' (코드가 고름)' if r.get('auto') else ''} | {r.get('action_en') or '-'} |")
        md += ["", "- 사람은 끝까지 뒷모습·강아지는 실사 소형견. 제작 뒤 비전 검수(사람 수·얼굴·강아지 수·새 사물·구조 변화)에 탈락하면 그 컷만 사진 무빙.",
               "- 화면 위 고지문 줄에 'AI 연출' 표시 + 캡션 고지."]
        for w in report.get("visual_warnings") or []:
            md.append(f"- 경고: {w}")
    cd = report.get("card") or {}
    if req.get("card", CARD_DEFAULT) is not True:
        md += ["", "## 요약 카드", "", "- 꺼짐(요청 card: false) — 기본은 켜짐(2026-10-20 운영자 '새 디자인으로 켠다')"]
    elif cd.get("point"):
        md += ["", f"## 요약 카드 (v9 · 문장 {cd.get('after')} 뒤 · {cd.get('sec')}초 · 음악만 · 저장 유도)", "",
               f"- {cd.get('eyebrow') or design.CARD_EYEBROW}: **{cd['point']}**", "- 여기서는:"]
        for a in cd.get("answers") or []:
            md.append(f"  - {a['text']}" + (f" (사실 {a['fact']})" if a.get("fact") else " (장점 사진에 보이는 것)"))
        md += [f"- 출처: {cd.get('source')} · 화면: 장점 사진 약한 블러 + 어둡기 + 유리 칩, 줄마다 0.3초 간격 등장, 카드 장면엔 자막·장소 라벨 없음"]
    elif cd.get("skipped"):
        md += ["", "## 요약 카드", "", f"- 없음(규칙에 맞는 줄이 없음): {cd['skipped']}"]
    ft = report.get("features") or {}
    if ft.get("items"):                                                                 # v10 특장점 라벨
        md += ["", f"## 특장점 라벨 (v10 · {len(ft['items'])}개 · {ft.get('source') or ''} · 장소 라벨 자리 72px 코랄 · 그 문장들 동안 유지)", ""]
        for f in ft["items"]:
            md.append(f"- **{f['text']}** — 문장 {'·'.join(str(x) for x in f['beats'])}" + (f" (사실 {f['fact']})" if f.get("fact") else " (장점 사진·문장 낱말)"))
    else:
        md += ["", "## 특장점 라벨", "", "- 없음(규칙에 맞는 라벨이 없음 — 모델 답·장점 이름 모두 탈락)"]
    for x in ft.get("tries") or []:
        md.append(f"- 뺌: 문장 {x['beat']} '{x['text']}' — {'; '.join(x['errs'])}")
    md += ["", "## 관점 검사", "", "- 결과: " + ("**통과**" if lc.get("ok") else "**미달 → 걸린 문장만 고치거나 뺌(아래 확인)**")]
    for e in (lc.get("after_fix") if not lc.get("ok") else []) or []:
        md.append(f"  - 고친 뒤 남은 것: {e}")
    for e in (report.get("story_fallback") or []):
        md.append(f"  - 처음 걸린 것: {e}")
    c = text["caption"]
    pt = report.get("pain_title") or {}
    md += ["", "## 훅 제목", "", (f"**{text['hook_title']}** ({text['hook_title_type']}" + (f" · {pt.get('source')} · 120px 어두운 상자" if text.get("hook_title_type") == "걱정형" else "") + ")" if text.get("hook_title") else "(제목 없음 — 규칙에 맞는 후보가 없었다)"),
           *[f"- 걱정형 후보 뺌: {x['source']} '{x['text']}' — {'; '.join(x['errs'])}" for x in (pt.get("tries") or [])],
           "", "## 캡션", "", c.get("hook", ""), *(c.get("points") or []), "", *[f"· {x}" for x in text["checklist"]], "", c.get("save", ""),
           "", f"제목: {text['title']} · 해시태그: {' '.join(text['hashtags'])}", "",
           "## 비용", "", (f"- 미리보기: 스토리보드 시트 약 {(report.get('storyboard') or {}).get('krw', 0):,}원 + 인서트 시트 약 {(report.get('inserts') or {}).get('krw', 0):,}원 · AI 영상 없음(사진 무빙) · 글·비전·음성 — 정식 제작 때 화면 계획대로 AI 컷 {report.get('ai_cuts', 0)}개(약 {294 * int(report.get('ai_cuts') or 0):,}원 + 검수)" if preview
                           else f"- AI 영상 {sum(1 for r in (report.get('veo') or {}).get('clips', []) if r.get('ok'))}/{len((report.get('veo') or {}).get('clips', []))}컷 · 이번 실행 약 {round(veo.spent_this_run()):,}원")]
    return "\n".join(md) + "\n"


# ── 6. 계획 저장·재사용 ─────────────────────────────────────────────────────────────────
NARR_FILES = ("narr_full.wav",)


def save_plan(req: dict, h: dict, pos0: int, pos: int, sig: dict, text: dict, shots: list[dict], narr: dict) -> Path:
    plan = {"version": 8, "stay": h["name"], "format": "story", "month": req.get("month"), "theme": req.get("theme"), "region": req.get("region"),
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
        if plan.get("version") not in (4, 5, 6, 7, 8) or (want and plan.get("stay") != want):
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
        report["features"] = {"items": [f for f in (text.get("features") or []) if isinstance(f, dict) and f.get("text")], "source": "미리보기 재사용", "tries": []}   # v10: 문서에도 라벨
        report["hotels"] = [{k: h.get(k) for k in sg.H_KEYS if k in h}]
        report["lens_check"] = {"ok": True, "note": "미리보기 대본 재사용"}
        recheck_shots(text, shot_list, sig, report)
        for s_ in shot_list:                                                            # v4·v5 계획엔 장소·등급이 없다
            s_.setdefault("grade", "full"); s_.setdefault("place", place_of({"description": s_.get("desc"), "category": s_.get("category")}))
        route_shots(text["beats"], shot_list, report)
        plan_visuals(text["beats"], shot_list, report, ai_budget(req), dog_ok(sig))   # 예산·규칙은 제작 때 값으로(0원)
        scenes_ok = [x for x in (text.get("scenes") or []) if x.get("ok") and x.get("img") and (STORY / x["img"]).exists()]
        if text.get("scenes"):                                                          # v7: 미리보기의 스토리보드 패널을 그대로(이미지 0원) — 파일이 없으면 원본
            for x in text["scenes"]:
                if x.get("img") and not (STORY / x["img"]).exists():
                    x["ok"] = False; x["why"] = "패널 파일 없음(아티팩트)"
            sc.apply_scenes(text["beats"], text["scenes"], {s_["id"]: s_ for s_ in shot_list}, report)
            report["storyboard"] = {"reused": True, "scenes": len(text["scenes"]), "panels_ok": len(scenes_ok), "krw": 0}
            report["inserts_used"] = [s_["id"] for b in text["beats"] for s_ in shot_list if s_.get("insert") and s_["id"] in (b.get("shots") or [])]
            visual_report(text["beats"], {s_["id"]: s_ for s_ in shot_list}, report)
    else:
        h, pos0 = so.assets(req, models, report)
        sig = sg.choose_signature(models, h, req, report)
        facts = sg.facts_list(h) + deep_facts(models, h, sig, report) + operator_facts(h["name"], report)   # 운영자 확인 사실은 맨 뒤(안전망)
        shot_list = build_shots(models, sig, h, report)
        material_gate(report.get("material") or {"photos": len({s_["k"] for s_ in shot_list}), "places": sorted({s_.get("place") for s_ in shot_list}), "inserts": 0}, h, req, report)
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
    ai = sum(1 for r in v.get("clips", []) if r.get("ok") and r.get("type") in ("A", "B"))
    lens_ok = bool((report.get("lens_check") or {}).get("ok"))
    caption = (ms.DISCLOSURE + "\n\n" + str(c.get("hook") or "").strip()
               + ("\n" + "\n".join(c.get("points") or []) if c.get("points") else "")
               + ("\n\n" + "\n".join(f"· {x}" for x in text["checklist"]) if text["checklist"] else "")
               + "\n\n" + str(c.get("save") or "저장해두고 다시 꺼내 보세요.") + "\n같이 갈 사람에게도 보내 주세요."
               + f"\n\n{h['name']}" + (f" · {h['city']}" if h.get("city") else "")
               + f"\n객실 타입·예약 링크는 프로필 링크 → {pos}번 ({folder})"
               + ("\n사진: 숙소 공식 홈페이지" if pc.get("official") else "")
               + ("\n일부 장면의 움직임(물결·빛·커튼·카메라 이동)은 실제 사진을 바탕으로 AI로 만들었어요. 실제 모습과 다를 수 있어요." if ai else "")
               + ("\n사람·강아지 장면은 AI로 만든 연출이에요(실제 사람·반려견 아님)." if any(r.get("ok") and r.get("type") == "A" for r in v.get("clips", [])) else "")
               + "\n\n" + " ".join(text["hashtags"]))
    sb = report.get("storyboard") or {}
    n_sheets = len(sb.get("sheets") or [])
    n_ins = len(report.get("inserts_used") or [])
    ins_krw = int((report.get("inserts") or {}).get("krw") or 0)
    meta = {"mode": "signature", "format": "story",
            "label": (f"시그니처 이야기 미리보기(스토리보드 시트 {n_sheets}장 · 인서트 {n_ins}컷 · AI 영상 없음)" if n_sheets or n_ins else "시그니처 이야기 미리보기(AI 영상 없음)") if preview
            else f"시그니처 이야기 제작(AI 영상 {ai}/{len(v.get('clips', []))}컷)", "storyboard_krw": int(sb.get("krw", 0) or 0) + ins_krw, "storyboard_sheets": n_sheets,
            "inserts": n_ins, "scene_drops": len(report.get("scene_drops") or []), "card": report.get("card"),
            "features": [f["text"] for f in (text.get("features") or []) if isinstance(f, dict) and f.get("text")],
            "cut_count": report.get("cut_count"), "places": report.get("places"), "material_warning": report.get("material_warning"),
            "stage": report["stage"], "stay": h["name"], "signature": sig["name"], "title": text["title"], "caption": caption, "folder": folder, "folder_pos": pos,
            "bgm": report.get("bgm"), "pinned_comment": f"{h['name']} — 객실 타입·링크는 프로필 링크 → {pos}번 ({folder}) · 쿠팡 파트너스 링크 포함",
            "affiliate_urls": {h["name"]: h.get("affiliate_url")}, "lines": [b["line"] for b in text["beats"]], "cuts": timeline, "lens_ok": lens_ok,
            "veo": {"model": veo.MODEL, "fake": veo.FAKE, "clips_ok": ai, "clips_total": len(v.get("clips", [])),
                    "spent_krw": round(veo.spent_this_run()), "month_total_krw": round(veo.month_total())}}
    return video, total, meta
