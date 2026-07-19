"""심해(deep_sea) 카테고리 적합성 검증 — 결정론(LLM 비의존, 네트워크 불필요).

정어리(Sardinops sagax)·갑오징어(Sepia officinalis)·참문어(Octopus vulgaris) 같은
'표층·연안 종'이 「심해 도감」에 잘못 편입돼 가짜 수심('水深 200〜2,000 m')이 자막으로
붙는 사고를 막는다. (실제 사고: IMG_3667 = #026 정어리, 水深 200〜2,000 m — 허위)

━━ 검증 규칙(모두 실제 문헌 텍스트 근거만 사용, 지어내지 않음) ━━
  1) 명백한 표층·연안 분류군(정어리·청어·멸치·고등어·참치·연안 두족류·갯민숭 등)은 하드 배제.
  2) 심해 '양성 증거'가 있어야 채택:
       (a) 문헌에 서식 최대수심 ≥ 200 m 수치가 있거나,
       (b) 심해대 키워드(deep-sea/abyssal/bathyal/mesopelagic/hydrothermal vent/深海 …)가 있음.
  3) 근거가 전혀 없으면 배제한다(수심을 지어내지 않는다 — 날조 금지 원칙).

반환: DeepSeaVerdict(ok, depth_range_m, reason)
      - depth_range_m 은 '문헌에서 실제로 추출된 값'만(예: '200-2300'), 없으면 '' (표기 안 함).

'200 m'는 표준 해양학에서 유광층(epipelagic) 아래 중층수(mesopelagic)가 시작되는 경계다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 유광층 경계 — 이 이상을 서식 수심으로 갖는 종을 '심해'로 인정.
DEEP_SEA_MIN_M = 200

# ── 표층·연안 종 하드 배제(정체성어) ──
# 어(魚) 표층 회유종과 연안 얕은 종의 '속·과·통용명'을 특정어로 배제한다.
# 주의: 심해어 오배제 방지를 위해 광범위한 서식지 단어가 아니라 '분류군 정체성'만 매칭.
_SHALLOW = re.compile(
    # 정어리·청어·전어·정어리류(Clupeidae/Alosidae) — 표층 회유
    r"sardinops|\bsardina\b|clupe[a-z]*|alosa\b|alosidae|dorosoma|sprattus|\bsprat\b|"
    r"\bherring\b|\bherrings\b|\bsardine\b|\bsardines\b|\bpilchard\b|\bshad\b|"
    r"マイワシ|\bイワシ|ニシン|"
    # 멸치(Engraulidae)
    r"engraulis|engraulidae|\banchovy\b|\banchovies\b|カタクチイワシ|"
    # 고등어·참치·가다랑어 등 표층 스콤브리드(Scombridae)
    r"scomber\b|scombridae|\bmackerel\b|\btuna\b|thunnus|katsuwonus|\bbonito\b|"
    r"サバ\b|マグロ|カツオ|"
    # 연안 얕은 두족류(표층~연안 100 m 내외)
    r"sepia officinalis|octopus vulgaris|"
    # 갯민숭·군소 등 조간대·연안 복족류
    r"\baplysia\b|sea hare|アメフラシ",
    re.I,
)

# ── 심해대 양성 키워드 ──
_DEEP_KW = re.compile(
    r"deep[- ]?sea|deep[- ]?water|abyssal|abyssopelagic|abyss\b|bathyal|bathypelagic|"
    r"mesopelagic|hadal|hadopelagic|midnight zone|twilight zone|aphotic|"
    r"hydrotherm|cold seep|\bseep\b|benthopelagic|"
    r"深海|深層|深海性|深海魚|漸深層|中深層|熱水噴出",
    re.I,
)

_DEPTH_UNIT = r"(?:m\b|meters?\b|metres?\b|メートル|미터|메터)"
# 단일 수심('4000 m') — 각 수치에 단위가 붙는 경우.
_DEPTH_NUM = re.compile(r"(\d{2,5})\s*" + _DEPTH_UNIT, re.I)
# 범위 수심('200 to 2,000 m' · '200–2000 m') — 앞 수치는 뒤 단위를 공유한다.
_DEPTH_RANGE = re.compile(
    r"(\d{2,5})\s*(?:to|and|[-–—〜~]|から)\s*(\d{2,5})\s*" + _DEPTH_UNIT, re.I)


@dataclass
class DeepSeaVerdict:
    ok: bool
    depth_range_m: str      # 문헌에서 실제 추출된 값만('' = 근거 없음 → 표기 안 함)
    reason: str


def extract_depth(text: str) -> str:
    """텍스트에서 서식 수심(미터) 수치를 뽑아 'lo-hi'(또는 단일값)로 반환. 없으면 ''.
    콤마(2,000)·단위표기 다양성을 흡수한다."""
    if not text:
        return ""
    flat = text.replace(",", "").replace("，", "")
    nums = []
    for m in _DEPTH_RANGE.finditer(flat):   # 범위('200 to 2000 m')는 양끝 모두 채집
        for g in (m.group(1), m.group(2)):
            n = int(g)
            if 1 <= n <= 11000:
                nums.append(n)
    for m in _DEPTH_NUM.finditer(flat):     # 단일 수치
        n = int(m.group(1))
        if 1 <= n <= 11000:      # 마리아나 해구(≈11,000 m) 상한
            nums.append(n)
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    return f"{lo}-{hi}" if lo != hi else str(hi)


def _max_depth(depth_range_m: str) -> int:
    nums = [int(x) for x in re.findall(r"\d+", depth_range_m or "")]
    return max(nums) if nums else 0


def verdict(sci: str, common_en: str, corpus: str) -> DeepSeaVerdict:
    """심해 적합성 판정(순수 함수 · 결정론). corpus = 위키 본문 + 사실 + 설명 등 합친 텍스트.

    sci/common_en 은 정체성 하드배제(표층 종)에 쓰고, corpus 는 수심·심해 키워드 근거에 쓴다.
    """
    ident = f"{sci or ''} {common_en or ''}"
    blob = f"{ident} {corpus or ''}"

    # 1) 표층·연안 분류군 하드 배제(정어리 등)
    hit = _SHALLOW.search(ident) or _SHALLOW.search(blob)
    if hit:
        return DeepSeaVerdict(False, "", f"표층·연안 분류군({hit.group(0)}) — 심해 부적합")

    # 2) 심해 양성 증거: (a) 수심 ≥ 200 m 또는 (b) 심해대 키워드
    depth = extract_depth(blob)
    dmax = _max_depth(depth)
    if dmax >= DEEP_SEA_MIN_M:
        return DeepSeaVerdict(True, depth, f"서식 최대수심 {dmax} m ≥ {DEEP_SEA_MIN_M} m")
    kw = _DEEP_KW.search(blob)
    if kw:
        # 심해대 키워드로 확인 — 수심 수치는 있으면 표기, 없으면 '' (지어내지 않음)
        return DeepSeaVerdict(True, depth, f"심해대 근거 키워드({kw.group(0)})")

    # 3) 근거 없음 → 배제(수심 날조 방지)
    return DeepSeaVerdict(False, "", "심해 근거(수심 ≥200 m·심해대 키워드) 없음")


# ── 서식해역(대양 basin) 판정 — 침몰선 지도 표기(北大西洋 등)와 동일 표기 체계 ──
#   생물의 서식해역을 지도에 '北大西洋/北太平洋/…'로 표기하되, **문헌(literature) 근거가 있을 때만**
#   표기한다(운영자 확정). 정확한 좌표·숫자는 노출하지 않고(하드룰 '임의 좌표 금지' 준수) 일반화된
#   대양 basin 중심으로만 락온한다. 근거가 없거나 불일치면 None(→ 일반 라벨 '生息海域'로 폴백·날조 금지).
@dataclass
class HabitatRegion:
    label_jp: str
    label_en: str
    lat: float | None       # basin 중심 위도(일반화 · worldwide면 None)
    lon: float | None       # basin 중심 경도(일반화 · worldwide면 None)
    reason: str


# basin: (jp, en, 중심위도, 중심경도) — 일반화된 대양 중심(정밀 종 좌표 아님).
_BASINS: dict[str, tuple[str, str, float | None, float | None]] = {
    "n_atlantic":    ("北大西洋", "N. ATLANTIC", 40.0, -40.0),
    "s_atlantic":    ("南大西洋", "S. ATLANTIC", -25.0, -15.0),
    "n_pacific":     ("北太平洋", "N. PACIFIC", 40.0, -175.0),
    "s_pacific":     ("南太平洋", "S. PACIFIC", -25.0, -140.0),
    "indian":        ("インド洋", "INDIAN OCEAN", -20.0, 75.0),
    "mediterranean": ("地中海", "MEDITERRANEAN", 38.0, 15.0),
    "southern":      ("南極海", "SOUTHERN OCEAN", -62.0, 0.0),
    "arctic":        ("北極海", "ARCTIC OCEAN", 82.0, 0.0),
    "atlantic":      ("大西洋", "ATLANTIC", 5.0, -30.0),      # 남·북 미상
    "pacific":       ("太平洋", "PACIFIC", 0.0, -160.0),      # 남·북 미상
    "worldwide":     ("全世界の海", "WORLDWIDE", None, None),  # 범존(cosmopolitan)
}
# 매칭 순서(구체적인 것부터) — 한/영/일 키워드. 구체 basin이 잡히면 일반 basin·worldwide보다 우선.
_REGION_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("n_atlantic",    re.compile(r"북대서양|north\s*atlantic|北大西洋", re.I)),
    ("s_atlantic",    re.compile(r"남대서양|south\s*atlantic|南大西洋", re.I)),
    ("n_pacific",     re.compile(r"북태평양|north\s*pacific|北太平洋|北東太平洋|北西太平洋", re.I)),
    ("s_pacific",     re.compile(r"남태평양|south\s*pacific|南太平洋", re.I)),
    ("mediterranean", re.compile(r"지중해|mediterranean|地中海", re.I)),
    ("indian",        re.compile(r"인도양|indian\s*ocean|インド洋", re.I)),
    ("southern",      re.compile(r"남극해|남극\s*해|남극권|southern\s*ocean|antarctic|南極海|南大洋", re.I)),
    ("arctic",        re.compile(r"북극해|북극\s*해|arctic\s*ocean|\barctic\b|北極海", re.I)),
    ("atlantic",      re.compile(r"대서양|atlantic|大西洋", re.I)),
    ("pacific",       re.compile(r"태평양|pacific|太平洋", re.I)),
    ("worldwide",     re.compile(r"전\s*세계|전세계|cosmopolitan|world[- ]?wide|all\s+ocean|"
                                 r"global\s+distribution|全世界|世界中|汎存|широ", re.I)),
]
_SPECIFIC = {"n_atlantic", "s_atlantic", "n_pacific", "s_pacific",
             "indian", "mediterranean", "southern", "arctic"}   # basin이 특정된 것
_GENERIC = {"atlantic", "pacific"}                              # 남·북 미상(구체보단 약함)


def _match_basins(text: str) -> list[str]:
    """텍스트에서 매칭된 basin 키를 순서(구체적→일반) 그대로 반환(중복 제거)."""
    out: list[str] = []
    for key, pat in _REGION_PATTERNS:
        if pat.search(text or "") and key not in out:
            out.append(key)
    return out


def habitat_region(distribution: str, corpus: str) -> HabitatRegion | None:
    """★서식해역을 침몰선 지도와 같은 대양 표기(北大西洋 등)로 판정 + **문헌 일치 검증**.

    distribution = 우리 데이터(국문 분포, 예: '북태평양 심해') — 화면 표기 후보.
    corpus       = 문헌(위키 서식/분포 본문 + 사실) — 진위 근거.
    규칙(운영자 확정): 화면에 쓸 대양 라벨은 **문헌 근거가 있을 때만** 노출한다.
      · distribution·corpus가 같은 구체 basin을 가리키면 → 검증됨(그 basin).
      · distribution엔 없고 corpus(문헌)만 구체 basin을 가지면 → 문헌을 신뢰(그 basin).
      · distribution은 basin을 주장하나 문헌이 이를 뒷받침 안 하면(다른 basin·근거 없음) → None
        (날조 방지 · 일반 라벨 '生息海域'로 폴백).
      · 양쪽이 worldwide(범존)만 가리키면 → 全世界の海(특정 락온 없음).
    반환: HabitatRegion(라벨·basin중심·사유) 또는 None(문헌 미확인 → 일반 라벨)."""
    disp = _match_basins(distribution)
    corp = _match_basins(corpus)
    disp_spec = [k for k in disp if k in _SPECIFIC]
    corp_spec = [k for k in corp if k in _SPECIFIC]

    def mk(key: str, reason: str) -> HabitatRegion:
        jp, en, la, lo = _BASINS[key]
        return HabitatRegion(jp, en, la, lo, reason)

    # ① distribution·corpus가 공유하는 구체 basin(가장 강한 검증)
    both = [k for k in disp_spec if k in corp_spec]
    if both:
        return mk(both[0], f"문헌·데이터 일치({_BASINS[both[0]][1]})")
    # ② 문헌(corpus)이 구체 basin을 가짐 → 문헌 신뢰(데이터가 비었거나 달라도 문헌 우선)
    if corp_spec:
        return mk(corp_spec[0], f"문헌 근거({_BASINS[corp_spec[0]][1]})")
    # ③ 데이터·문헌 어느 쪽이든 일반 basin(남·북 미상)이 문헌에 있으면 그것
    corp_gen = [k for k in corp if k in _GENERIC]
    if corp_gen:
        return mk(corp_gen[0], f"문헌 근거({_BASINS[corp_gen[0]][1]}·남북 미상)")
    # ④ 범존(worldwide)이 문헌 또는 데이터에 명시 → 全世界の海(특정 락온 없음)
    if "worldwide" in corp or "worldwide" in disp:
        return mk("worldwide", "범존(cosmopolitan) — 문헌/데이터 명시")
    # ⑤ 문헌이 서식해역을 뒷받침하지 않음 → None(일반 라벨 폴백 · 날조 금지)
    return None
