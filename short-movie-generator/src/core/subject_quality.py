"""편당 품질 게이트 — **한 편 = 한 대상**이 되도록 '너무 넓은 분류군'을 제작 전에 막는다.

왜(실측 근거): 공개된 회차 중 #058은 대상이 `starfish / Asteroidea`(불가사리 **강** 전체),
#059는 `shark / Selachimorpha`(상어 **상목** 전체 · 553종)였다. 이런 편은
  · 수심·분포가 비고("어디에 사는지"를 쓸 수 없다 — 553종의 분포는 하나로 말할 수 없으므로)
  · 사실 문장이 위키백과 총론의 복붙("상어는 연골어강…")이 되어 **어느 편에도 없는 개성**이 사라진다
결과적으로 '심해 도감'이 아니라 '해양 백과사전 낭독'이 된다. 발행 편수를 줄이고 편당 품질을
올리기로 한 이상(운영자 확정), 이런 대상은 **만들기 전에** 걸러야 한다.

판정은 **네트워크 없이** 학명 형태로 한다(제작 직전에 외부 API가 죽어도 게이트가 살아 있어야 함):
  · 두 단어(이명법) = 종      → 통과   예) Bathynomus giganteus
  · `-idae`/`-inae`/`-ini`   = 과·아과·족 → 통과   예) Aphyonidae, Liparidae
  · `-oidea`/`-morpha`/`-phora`/`-formes`/`-acea`/`-zoa` = 상과·상목·문 등 → **차단**
  · 그 외 한 단어           = 속(genus)로 보고 통과   예) Bathynomus
  · 다만 영문 통칭이 'shark·starfish' 같은 **총칭어**면 속이라도 차단(대상이 특정되지 않음)

운영자가 그래도 만들겠다면 막지 않는다 — `allow_broad=True`(또는 워크플로 입력)로 통과시킨다.
"""
from __future__ import annotations

import re

# 과(family) 이하 = 대상이 충분히 좁다. 접미사만으로 판별 가능한 계급.
_OK_SUFFIX = ("idae", "inae", "ini")
# 과보다 위(상과·상목·목·강·문 등) — 한 편으로 묶기엔 너무 넓다.
_BROAD_SUFFIX = ("oidea", "morpha", "morphi", "formes", "phora", "poda", "acea",
                 "zoa", "cea", "ida", "ales")
# 위 접미사에 걸리지만 실제로는 좁은 분류군인 예외(오탐 방지). 필요할 때만 늘린다.
# (Sepiida는 갑오징어 '목'이라 예외가 아니다 — 예전 항목은 오류였다.)
_BROAD_EXCEPT: set[str] = set()

# ★접미사만으로는 못 잡는 **문·강·목** 이름을 이름 그대로 막는다(오탐 0 · 확실한 방법).
#   계기: #060이 `Porifera`(해면 **동물문 전체**)로 나갔다 — "fera"는 속 이름에도 쓰여
#   접미사 규칙에 넣기 위험하므로, 이런 건 목록으로 정확히 잡는다.
#   기준은 하나다 — **한 편으로 묶으면 수심·분포를 특정할 수 없는 넓이인가.**
_BROAD_NAMES = {
    # 문(phylum)
    "porifera", "cnidaria", "ctenophora", "echinodermata", "mollusca", "arthropoda",
    "annelida", "chordata", "nematoda", "bryozoa", "brachiopoda", "nemertea",
    "chaetognatha", "sipuncula", "hemichordata", "priapulida", "placozoa", "rotifera",
    "foraminifera", "radiolaria", "bacillariophyta", "platyhelminthes",
    # 강·아강(class·subclass)
    "anthozoa", "hydrozoa", "scyphozoa", "cubozoa", "octocorallia", "hexacorallia",
    "asteroidea", "ophiuroidea", "echinoidea", "holothuroidea", "crinoidea",
    "cephalopoda", "gastropoda", "bivalvia", "polychaeta", "malacostraca",
    "actinopterygii", "chondrichthyes", "osteichthyes", "elasmobranchii", "holocephali",
    "pycnogonida", "ascidiacea", "thaliacea", "crustacea", "tunicata",
    # 상목·목(superorder·order)
    "selachimorpha", "batoidea", "teleostei", "decapoda", "isopoda", "amphipoda",
    "copepoda", "euphausiacea", "actiniaria", "scleractinia", "alcyonacea",
    "pennatulacea", "zoantharia", "corallimorpharia", "teuthida", "octopoda",
    "sepiida", "myctophiformes", "chimaeriformes", "anguilliformes", "gadiformes",
}

# 영문 통칭 — 이 단어 하나로는 '어떤 생물'인지 특정되지 않는다(수심·분포를 쓸 수 없다).
# ★단, 통칭이 '허술한 이름'일 뿐 학명이 구체적인 경우(Bathynomus / "isopod")는 막지 않는다.
#   학명과 통칭이 **같은 말**일 때만(Octopus / "octopus") 대상이 특정 안 된 것으로 본다.
_GENERIC_COMMON = {
    "shark", "sharks", "fish", "fishes", "starfish", "sea star", "jellyfish",
    "crab", "crabs", "coral", "corals", "octopus", "squid", "eel", "eels",
    "worm", "worms", "shrimp", "prawn", "anemone", "sponge", "sponges",
    "snail", "snails", "urchin", "sea urchin", "ray", "rays", "whale", "dolphin",
    "sea cucumber", "crinoid", "comb jelly", "isopod", "amphipod", "copepod",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def rank_guess(scientific_name: str) -> str:
    """학명 형태 → 계급 추정. 반환: species/family/genus/broad/unknown."""
    sci = _norm(scientific_name)
    if not sci:
        return "unknown"
    if len(sci.split()) >= 2:
        return "species"
    low = sci.lower()
    if low in _BROAD_NAMES:      # ★이름으로 확정된 문·강·목이 먼저(접미사 규칙보다 정확)
        return "broad"
    if low in _BROAD_EXCEPT:
        return "genus"
    if low.endswith(_OK_SUFFIX):
        return "family"
    if low.endswith(_BROAD_SUFFIX):
        return "broad"
    return "genus"


def assess(scientific_name: str, common_name_en: str = "") -> dict:
    """대상이 한 편으로 묶을 만큼 좁은가. 반환 {"ok", "rank", "reason"}."""
    sci = _norm(scientific_name)
    rank = rank_guess(sci)
    if rank == "unknown":
        return {"ok": False, "rank": rank, "reason": "학명이 비어 있어 대상을 특정할 수 없습니다"}
    if rank == "broad":
        return {"ok": False, "rank": rank,
                "reason": f"'{sci}'는 과(family)보다 위 분류군입니다 — 한 편에 담기엔 너무 넓어 "
                          f"수심·분포를 특정할 수 없습니다(종 또는 과 단위로 좁히세요)"}
    common = _norm(common_name_en).lower()
    if common in _GENERIC_COMMON and rank != "species" and common == sci.lower():
        return {"ok": False, "rank": rank,
                "reason": f"'{sci}'는 영문 통칭 '{common}'과 같은 말이라 대상이 특정되지 "
                          f"않습니다 — 어떤 종/과인지 좁히세요"}
    return {"ok": True, "rank": rank, "reason": ""}


def is_specific_enough(scientific_name: str, common_name_en: str = "") -> bool:
    return bool(assess(scientific_name, common_name_en)["ok"])
