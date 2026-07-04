"""deep_sea 시드 데이터 — 종 정보 + 상황/컷 뱅크 (spec 6장 스키마).

정보 소스(FishBase/WoRMS/NOAA 등)에서 재작성한 사실 데이터. API 자동 조회는 Phase 2+.
accuracy_flags = 정확성 게이트 기준 (컷 프롬프트가 이를 위배하면 제작 차단).
"""

# 종 시드 (키: 소문자 일반명/학명 별칭)
SPECIES = {
    "dumbo octopus": {
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
        # Grimpoteuthis 속은 발광이 확인되지 않음 → 발광 컷 금지
        "accuracy_flags": {
            "bioluminescent": False,
            "swallows_prey_whole": True,
            "max_depth_m": 4000,
            "has_ear_like_fins": True,
        },
    },
}

# 상황 뱅크: 종별 실제 행동을 3컷으로. 새 종은 여기에 항목만 추가.
SITUATIONS = {
    "dumbo octopus": {
        "situation_id": "discovery_swim",
        "cuts": [
            {
                "cut_type": "discovery",
                "prompt": (
                    "POV footage from a deep-sea ROV exploring the pitch-black abyss. A hard "
                    "floodlight beam sweeps through turbid blue-green water thick with marine snow, "
                    "and a dumbo octopus with large ear-like fins slowly emerges from darkness into "
                    "the light. Subtle underwater-vehicle camera drift, slowly approaching. Murky "
                    "low-light look with faint video noise. Keep the octopus's exact shape, "
                    "proportions, and number of fins and arms unchanged. Vertical 9:16."
                ),
            },
            {
                "cut_type": "behavior",
                "prompt": (
                    "Deep-sea ROV footage tracking a dumbo octopus propelling itself through dark "
                    "water by flapping its large ear-like fins like wings, webbed arms trailing "
                    "beneath. Hard floodlight against total blackness; marine snow streaks past. "
                    "Subtle vehicle vibration. Murky low-light camera look. Keep the octopus's exact "
                    "shape and number of fins and arms unchanged. Vertical 9:16."
                ),
            },
            {
                "cut_type": "detail",
                "prompt": (
                    "Deep-sea ROV camera slowly closing in on a dumbo octopus near the seafloor, its "
                    "webbed arms and fine texture revealed under the floodlight in murky blue-green "
                    "water. Faint suspended particles drift through the beam. Subtle camera shake. "
                    "Keep the octopus's exact shape and number of arms unchanged. Vertical 9:16."
                ),
            },
        ],
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
