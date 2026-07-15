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
