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
        # 서식대가 배경을 결정 (benthic=해저 퇴적층 / pelagic=원양 흑수).
        # 덤보문어는 심해 저층 바로 위에서 호버링하는 저서성 → benthic.
        "habitat_zone": "benthic",
        "appearance": (
            "a dumbo octopus (Grimpoteuthis), a small deep-sea octopus with a soft rounded "
            "gelatinous body and two large paddle-like fins on top of its head that look like "
            "an elephant's ears"
        ),
        "anatomy_lock": (
            "exactly two ear-like fins on top of the mantle and eight short arms with thin skin "
            "webbing between the arms close to the body; keep the fin count (2) and arm count (8) "
            "unchanged; the body stays a single soft, rounded, semi-gelatinous octopus"
        ),
        # 주의: 우산/해파리 등 트리거 명사를 부정문에라도 넣지 않는다(핑크코끼리). 우산 아티팩트의
        # 실제 원인이던 긍정 문구 'umbrella-like web'는 anatomy_lock에서 이미 제거함.
        "forbidden_features": (
            "long muscular tentacles, curling sucker-covered arms of a shallow-water octopus, "
            "a common-octopus body, extra limbs, or any change to the two ear-like fins"
        ),
        # 스토리 아크(실제 행동만): 컷1 어둠 속 등장(미인지) → 컷2 유영(아직 미인지) →
        # 컷3 카메라를 뒤늦게 알아채고 눈맞춤 후 조용히 이탈(=이 종의 진짜 반응, 공격 아님).
        # 3인칭 현재형(as it ___ / while it ___ 에 문법적으로 호응)
        "cut_behaviors": {
            "discovery": "hovers in the open darkness, slowly flapping its two ear-like fins",
            "behavior": (
                "swims by gently flapping its two large ear-like fins like wings while its "
                "webbed arms trail and spread beneath it"
            ),
            # 컷3 = 반응 비트: 카메라를 알아채고 마주본 뒤 부드럽게 물러남 (실제 회피 행동)
            "detail": (
                "slowly turns to face the camera, its large dark eyes catching the light, then "
                "gently flaps its two ear-like fins and drifts backward into the darkness"
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
