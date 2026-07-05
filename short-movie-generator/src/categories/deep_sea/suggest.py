"""deep_sea 종 자동 추천 + 중복 방지 (카테고리만 고르면 AI가 실존 종을 골라 전체 데이터 생성).

흐름: 생물학적 카테고리(저서/부유/유영) → Claude가 '아직 안 쓴' 실존 심해 종 1개를
data.SPECIES 스키마(정보 + 형태/해부 잠금/컷 행동 + 정확성 플래그 + HUD 콜아웃)로 반환 →
검증(필수필드·금지어·중복) → data.SPECIES에 런타임 등록 → 파이프라인이 그대로 제작.

중복 방지: used_species.json(원장)에 학명·영문명을 누적. 시드(data.SPECIES)도 제외 대상.
원장은 CI가 커밋해 매일 자동 실행 간 중복을 막는다.
LLM 불가 시: 아직 안 쓴 시드 종으로 폴백(최후엔 dumbo octopus).
"""
from __future__ import annotations

import json
import logging
import re

from src.categories.deep_sea import data
from src.core import llm

log = logging.getLogger(__name__)

from pathlib import Path  # noqa: E402

LEDGER = Path(__file__).resolve().parent / "used_species.json"

# 생물학적 카테고리 (사용자 선택 단위). zone은 배경(benthic 해저 / pelagic 원양) 결정.
BIOCATEGORIES = {
    "benthos": {"ko": "저서생물", "zone": "benthic",
                "desc": "a real DEEP-SEA BENTHIC animal that lives on or just above the sea floor "
                        "(e.g., sea cucumbers, sea pigs, tripod fish, deep-sea crabs, brittle stars)"},
    "plankton": {"ko": "부유생물", "zone": "pelagic",
                 "desc": "a real DEEP-SEA PLANKTONIC drifter carried by currents "
                         "(e.g., siphonophores, comb jellies/ctenophores, larvaceans, gelatinous zooplankton)"},
    "nekton": {"ko": "유영생물", "zone": "pelagic",
               "desc": "a real DEEP-SEA NEKTONIC animal that actively swims "
                       "(e.g., anglerfish, vampire squid, gulper eel, viperfish, lanternfish)"},
}
_ROTATION = ["nekton", "benthos", "plankton"]
_SLOTS = {"left-mid", "right-mid", "right-low", "left-low", "top"}

_BANNED_RE = re.compile(
    r"\b(diver|divers|human|humans|treasure|shipwreck|monster|giant|colossal|"
    r"attack\w*|hunt\w*|prey|preying|predat\w*|devour\w*|maul\w*)\b", re.IGNORECASE)
_GLOW_RE = re.compile(
    r"\b(biolumin\w*|glow\w*|luminescen\w*|luminous|photophore\w*|phosphoresc\w*|"
    r"light[- ]producing|light organ\w*)\b", re.IGNORECASE)

_REQUIRED = ("scientific_name", "common_name_ko", "common_name_en", "depth_range_m",
             "distribution", "habitat", "appearance", "anatomy_lock", "forbidden_features",
             "cut_behaviors", "accuracy_flags")


# ---------- 원장(중복 방지) ----------

def _load_used() -> list[dict]:
    if LEDGER.exists():
        try:
            return json.loads(LEDGER.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return []
    return []


def used_names() -> set[str]:
    names: set[str] = set()
    for it in _load_used():
        names.add(str(it.get("scientific_name", "")).lower())
        names.add(str(it.get("common_name_en", "")).lower())
    for sp in data.SPECIES.values():  # 시드도 중복 방지 대상
        names.add(sp["scientific_name"].lower())
        names.add(sp["common_name_en"].lower())
    return {n for n in names if n}


def mark_used(sp: dict) -> None:
    items = _load_used()
    items.append({"scientific_name": sp["scientific_name"], "common_name_en": sp["common_name_en"],
                  "common_name_ko": sp["common_name_ko"], "biocat": sp.get("_biocat", "")})
    LEDGER.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def used_count() -> int:
    return len(_load_used())


def _pick_category(explicit: str) -> str:
    if explicit in BIOCATEGORIES:
        return explicit
    return _ROTATION[used_count() % len(_ROTATION)]  # 결정적 로테이션


# ---------- LLM 종 추천 ----------

_EXAMPLE = json.dumps({
    "scientific_name": "Grimpoteuthis spp.", "common_name_ko": "덤보문어",
    "common_name_en": "Dumbo octopus", "depth_range_m": "1000-4000",
    "distribution": "전 세계 심해", "habitat": "심해 저층(비생물 퇴적층)",
    "diet": ["갑각류", "다모류"], "fun_facts": ["귀처럼 보이는 지느러미를 펄럭여 헤엄친다",
    "수심 4,000m 이상에서도 발견되는 가장 깊은 곳의 문어", "먹물주머니가 퇴화해 없다"],
    "accuracy_flags": {"bioluminescent": False},
    "appearance": "a dumbo octopus, a small soft rounded gelatinous octopus with two large "
                  "ear-like paddle fins on top of its head",
    "anatomy_lock": "exactly two ear-like fins and eight short arms with thin webbing; keep fin "
                    "count (2) and arm count (8) unchanged",
    "forbidden_features": "long muscular tentacles, curling sucker-covered arms, extra limbs",
    "cut_behaviors": {"discovery": "hovers in the open darkness, slowly flapping its two ear-like fins",
    "behavior": "swims by gently flapping its two ear-like fins like wings while its webbed arms trail beneath it",
    "detail": "slowly turns to face the camera, its large dark eyes catching the light, then gently drifts backward into the darkness"},
    "hud_callouts": [{"slot": "left-mid", "title": "FIN ×2", "sub": "EAR-LIKE · PADDLE"},
                     {"slot": "right-mid", "title": "OCULAR", "sub": "LOW-LIGHT EYE"},
                     {"slot": "right-low", "title": "ARMS ×8", "sub": "WEBBED · TRAILING"}],
}, ensure_ascii=False)


def _suggest_via_llm(biocat: str, exclude: list[str]) -> dict | None:
    meta = BIOCATEGORIES[biocat]
    ex = ", ".join(sorted(exclude)[:60]) or "(없음)"
    prompt = (
        "너는 심해 생물 도감 채널의 리서처다. 아래 조건의 '실존하는' 심해 생물 1종을 골라 "
        "JSON 하나만 출력하라(코드펜스·설명 금지).\n"
        f"[조건] {meta['desc']}. 반드시 실제로 존재하는 종. 아래 제외 목록과 겹치지 마라.\n"
        f"[제외(이미 사용)] {ex}\n"
        "[출력 스키마 — 예시와 '완전히 동일한 키'로]\n"
        f"{_EXAMPLE}\n"
        "[작성 규칙]\n"
        "- common_name_ko: 한국어 통용명, common_name_en: 영문 통용명, scientific_name: 학명(속명 대문자).\n"
        "- fun_facts: 실제 사실 3~5개(수치·의외성 위주). depth_range_m: 'min-max' 숫자.\n"
        "- appearance/anatomy_lock/forbidden_features/cut_behaviors: 모두 영어. 실제 형태·행동만.\n"
        "- cut_behaviors는 discovery/behavior/detail 3개. detail은 '카메라를 알아채고 반응 후 이탈'.\n"
        "- ★중요: appearance/anatomy_lock/forbidden_features/cut_behaviors 영어 서술에는 먹이·사냥·"
        "포식(prey/hunt/hunting/predator/attack/devour) 단어를 '절대' 쓰지 마라. 포식성 어종이라도 "
        "오직 '형태·헤엄·표류·회전·카메라 반응'만 묘사한다. (예: 유인 돌기가 있어도 "
        "\"lures prey\"가 아니라 \"a glowing lure drifts in front of it\"처럼 형태·빛만.)\n"
        "- 사람·난파선·보물·괴물·과장 크기 금지.\n"
        "- 발광하는 종이면 accuracy_flags.bioluminescent=true (그때만 glow/lure 등 빛 표현 허용).\n"
        "- hud_callouts: 2~4개, slot은 left-mid/right-mid/right-low/left-low/top 중에서, "
        "title은 짧은 영문(부위+수량), sub는 짧은 영문 설명.\n"
    )
    raw = llm.generate_text(prompt, max_tokens=2600)
    if not raw:
        return None
    raw = raw.strip()
    m = re.search(r"\{.*\}", raw, re.S)  # 코드펜스/잡텍스트 제거
    if not m:
        return None
    try:
        sp = json.loads(m.group())
    except Exception:  # noqa: BLE001
        return None
    sp["_biocat"] = biocat
    sp["habitat_zone"] = meta["zone"]
    return sp if _valid(sp, exclude) else None


def _valid(sp: dict, exclude: list[str]) -> bool:
    if not all(k in sp and sp[k] for k in _REQUIRED):
        return False
    if sp["common_name_en"].lower() in exclude or sp["scientific_name"].lower() in exclude:
        return False
    cb = sp.get("cut_behaviors", {})
    if not all(cb.get(k) for k in ("discovery", "behavior", "detail")):
        return False
    blob = " ".join([sp["appearance"], sp["anatomy_lock"], sp["forbidden_features"],
                     cb["discovery"], cb["behavior"], cb["detail"]])
    if _BANNED_RE.search(blob):
        return False
    if not sp.get("accuracy_flags", {}).get("bioluminescent") and _GLOW_RE.search(blob):
        return False
    return True


def _register(sp: dict) -> str:
    key = sp["common_name_en"].strip().lower()
    sp.setdefault("diet", [])
    sp.setdefault("fun_facts", [])
    sp.setdefault("sources", ["NOAA", "WoRMS"])
    sp.setdefault("situation_id", "auto_" + re.sub(r"[^a-z0-9]+", "_", key).strip("_"))
    # HUD 콜아웃 슬롯 정리
    slots = ["left-mid", "right-mid", "right-low"]
    cos = sp.get("hud_callouts") or []
    fixed = []
    for i, co in enumerate(cos[:4]):
        slot = co.get("slot") if co.get("slot") in _SLOTS else slots[i % len(slots)]
        fixed.append({"slot": slot, "title": str(co.get("title", ""))[:16],
                      "sub": str(co.get("sub", ""))[:24]})
    sp["hud_callouts"] = fixed
    # 근접 경보: 유영성(nekton) 활동종만 컷2 후반 붉은 경보(실제 근접·인지 연출, 날조 공격 아님).
    # 표류성(plankton)·저서(benthos)는 차분하게(경보 없음) → 종별 톤 다양화.
    if sp.get("_biocat") == "nekton":
        sp["hud_alert"] = True
        sp.setdefault("alert_text", "개체가 이쪽으로 빠르게 접근 중")
    else:
        sp.setdefault("hud_alert", False)
    data.SPECIES[key] = sp
    return key


def pick(explicit_category: str = "") -> str:
    """카테고리 → 실존 종 1개를 골라 등록하고 종 key 반환 (중복 방지 + 원장 기록)."""
    biocat = _pick_category(explicit_category)
    exclude = list(used_names())
    for attempt in range(4):
        sp = _suggest_via_llm(biocat, exclude)
        if sp:
            key = _register(sp)
            mark_used(sp)
            log.info("[suggest] %s → %s (%s)", biocat, sp["common_name_ko"], sp["scientific_name"])
            return key
        log.info("[suggest] 재시도 %d (카테고리=%s)", attempt + 1, biocat)
    # 폴백: 아직 안 쓴 시드 종 → 최후엔 dumbo octopus
    used = used_names()
    for key, sp in data.SPECIES.items():
        if sp["common_name_en"].lower() not in used:
            log.warning("[suggest] LLM 불가 → 시드 폴백: %s", key)
            return key
    log.warning("[suggest] 전부 소진/LLM 불가 → dumbo octopus 폴백")
    return "dumbo octopus"


if __name__ == "__main__":  # CLI: 카테고리 → 선택 종 영문명 출력 (진단용)
    import sys
    logging.basicConfig(level=logging.INFO)
    cat = sys.argv[1] if len(sys.argv) > 1 else ""
    print(data.SPECIES[pick(cat)]["common_name_en"])
