"""deep_sea 시드 데이터 — 종 정보 + 프롬프트 재료 (형태·행동) + 정확성 플래그.

컷 프롬프트는 하드코딩하지 않는다 → prompts.py 템플릿이 이 데이터로 자동 조립.
새 종 추가 시 채울 것: 기본 정보 + accuracy_flags + appearance/anatomy_lock/
forbidden_features/cut_behaviors (+ situation_id).
정보 소스(FishBase/WoRMS/NOAA 등)에서 재작성한 사실 데이터. API 자동 조회는 Phase 2+.
"""

SPECIES = {
    "dumbo octopus": {
        # --- 기본 정보 (info/caption 용) ---
        "scientific_name": "Grimpoteuthis spp.",
        "common_name_ko": "덤보문어",
        "common_name_en": "Dumbo octopus",
        "depth_range_m": "1000-4000",
        "distribution": "전 세계 심해",
        "habitat": "심해 저층(비생물 퇴적층)",
        "diet": ["갑각류", "다모류", "요각류"],
        "fun_facts": [
            "귀처럼 보이는 지느러미를 펄럭여 헤엄친다",
            "수심 4,000m 이상에서도 발견되는 가장 깊은 곳의 문어",
            "먹이를 통째로 삼킨다",
        ],
        "sources": ["NOAA", "WoRMS", "MBARI(정보만)"],
        # --- 정확성 플래그 (정확성 게이트 기준) ---
        "accuracy_flags": {
            "bioluminescent": False,  # Grimpoteuthis 속은 발광 미확인 → 발광 컷 금지
            "swallows_prey_whole": True,
            "max_depth_m": 4000,
            "has_ear_like_fins": True,
        },
        # --- 프롬프트 재료 (prompts.py 템플릿이 사용) ---
        "situation_id": "discovery_swim",
        "appearance": (
            "a dumbo octopus (Grimpoteuthis), a small deep-sea octopus with a soft rounded "
            "gelatinous body and two large paddle-like fins on top of its head that look like "
            "an elephant's ears"
        ),
        "anatomy_lock": (
            "exactly two ear-like fins on top of the mantle and eight short arms joined by a "
            "wide umbrella-like web; keep the fin count (2), arm count (8) and the web shape "
            "unchanged; the body stays soft, rounded and semi-gelatinous"
        ),
        "forbidden_features": (
            "long muscular tentacles, curling sucker-covered arms of a shallow-water octopus, "
            "a common-octopus body, extra limbs, or any change to the two ear-like fins"
        ),
        "cut_behaviors": {
            "discovery": "hovering in the water and slowly flapping its two ear-like fins",
            "behavior": (
                "swimming by gently flapping its two large ear-like fins like wings while its "
                "webbed arms trail and spread beneath it"
            ),
            "detail": (
                "hovering almost motionless, its webbed arms and soft body seen up close while "
                "the two ear-like fins make small slow adjustments"
            ),
        },
    },
}


def resolve_key(query: str) -> str | None:
    """입력 질의를 시드 키로 정규화.

    정확 일치(키/일반명 KR·EN/학명) 우선. 부분 일치는 오매칭 방지를 위해
    '질의가 종 이름의 한 단어와 정확히 일치'하는 경우만 허용(양방향 substring 금지).
    """
    q = query.strip().lower()
    if not q:
        return None
    if q in SPECIES:
        return q
    for key, sp in SPECIES.items():
        aliases = {sp["common_name_en"].lower(), sp["common_name_ko"], sp["scientific_name"].lower()}
        if q in aliases:
            return key

    # 부분 일치: 질의가 종 이름의 '단어' 하나와 정확히 일치할 때만 (예: "dumbo" → dumbo octopus).
    # 유일하게 매칭될 때만 채택(모호하면 None).
    matches = set()
    for key, sp in SPECIES.items():
        words = set(key.split()) | set(sp["common_name_en"].lower().split()) | {sp["common_name_ko"]}
        if q in words and len(q) >= 3:
            matches.add(key)
    return matches.pop() if len(matches) == 1 else None
