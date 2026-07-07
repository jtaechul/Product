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
        # 실제 사실만 (NOAA/WoRMS 재작성). [0]=행동 비트, [1]=킬러팩트로 쓰임.
        "fun_facts": [
            "귀처럼 보이는 지느러미를 펄럭여 헤엄친다",
            "수심 4,000m 이상에서도 발견되는 가장 깊은 곳의 문어",
            "먹이를 통째로 삼킨다",
            "빛이 없는 심해에 살아 먹물주머니가 퇴화해 아예 없다",
            "몸이 반투명한 젤리질이라 엄청난 수압에도 부드럽게 버틴다",
            "평균 몸길이 20~30cm의 아담한 크기",
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
        # HUD 콜아웃(부위 지시 라벨) — 컷2 분석 비트에서 지시선으로 잠깐 등장. 슬롯은 코어가 좌표화.
        "hud_callouts": [
            {"slot": "left-mid", "title": "FIN ×2", "sub": "EAR-LIKE · PADDLE"},
            {"slot": "right-mid", "title": "OCULAR", "sub": "LOW-LIGHT EYE"},
            {"slot": "right-low", "title": "ARMS ×8", "sub": "WEBBED · TRAILING"},
        ],
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
    "enypniastes eximia": {
        "scientific_name": "Enypniastes eximia",
        "common_name_ko": "머리없는닭괴물",
        "common_name_en": "Headless chicken monster",
        "depth_range_m": "500-6000",
        "distribution": "전 세계 심해",
        "habitat": "심해 저층~중층(유영성 해삼)",
        "diet": ["해저 퇴적물 속 유기물"],
        "fun_facts": [
            "머리·눈·뼈가 없는 심해 해삼이다",
            "지느러미 같은 막으로 헤엄쳐 이동한다",
            "몸이 투명해 삼킨 퇴적물이 그대로 비친다",
            "위협을 받으면 빛나는 피부를 벗어 미끼로 던진다",
            "대부분의 해삼과 달리 해저를 기지 않고 유영한다",
        ],
        "sources": ["NOAA Ocean Exploration", "WoRMS"],
        "accuracy_flags": {
            "bioluminescent": True,        # 위협 시 발광 피부 탈락(실제)
            "swims": True,
            "max_depth_m": 6000,
            "transparent_body": True,
        },
        "situation_id": "discovery_swim",
        "habitat_zone": "benthic",
        "appearance": (
            "an Enypniastes eximia (headless chicken monster), a translucent reddish "
            "swimming deep-sea sea cucumber with a webbed veil-like fin and no head, eyes or bones"
        ),
        "anatomy_lock": (
            "a single soft translucent sea cucumber body with a veil-like anterior web; "
            "no head, no eyes, no bones; keep the gelatinous swimming form unchanged"
        ),
        "forbidden_features": (
            "any fish head, eyes, skeleton, legs, or hard shell; not an octopus or jellyfish"
        ),
        "hud_callouts": [
            {"slot": "left-mid", "title": "VEIL", "sub": "WEBBED FIN"},
            {"slot": "right-mid", "title": "TRANSLUCENT", "sub": "GUT VISIBLE"},
        ],
        "cut_behaviors": {
            "discovery": "drifts in the open darkness, its translucent body faintly lit",
            "behavior": "swims by undulating its veil-like webbed fin through the water",
            "detail": "hovers near the seafloor, sediment visible through its transparent body",
        },
    },
    "opisthoteuthis californiana": {
        "scientific_name": "Opisthoteuthis californiana",
        "common_name_ko": "넓적문어",
        "common_name_en": "Flapjack octopus",
        "depth_range_m": "200-1500",
        "distribution": "북태평양 심해",
        "habitat": "심해 저층 바로 위",
        "diet": ["요각류", "단각류"],
        "fun_facts": [
            "몸을 팬케이크처럼 납작하게 편다",
            "팔 사이 우산 같은 막으로 부드럽게 유영한다",
            "머리 위 귀 같은 지느러미로 방향을 잡는다",
            "젤리질 몸이라 높은 수압에도 부드럽게 버틴다",
        ],
        "sources": ["NOAA Ocean Exploration", "MBARI"],
        "accuracy_flags": {"bioluminescent": False, "swims": True, "max_depth_m": 1500},
        "situation_id": "discovery_swim", "habitat_zone": "benthic",
        "appearance": ("an Opisthoteuthis (flapjack octopus), a small flattened gelatinous "
                       "deep-sea octopus with a webbed umbrella between short arms and two small fins"),
        "anatomy_lock": ("a single soft flattened octopus body with webbing between eight short arms "
                         "and two small ear-like fins; keep the pancake-like flattened form"),
        "forbidden_features": ("long muscular tentacles, hard shell, fish head, or extra limbs"),
        "hud_callouts": [{"slot": "left-mid", "title": "FINS ×2", "sub": "EAR-LIKE"},
                         {"slot": "right-mid", "title": "WEB", "sub": "UMBRELLA"}],
        "cut_behaviors": {
            "discovery": "rests flattened on the seafloor in the darkness",
            "behavior": "spreads its webbed arms like an umbrella and drifts upward",
            "detail": "flaps its two small fins, its soft body catching the light",
        },
    },
    "graneledone boreopacifica": {
        "scientific_name": "Graneledone boreopacifica",
        "common_name_ko": "북태평양심해문어",
        "common_name_en": "Deep-sea octopus",
        "depth_range_m": "1000-2600",
        "distribution": "북동태평양 심해",
        "habitat": "심해 저층 암반",
        "diet": ["갑각류", "작은 무척추동물"],
        "fun_facts": [
            "알려진 가장 긴 알 품기 기록을 가졌다(약 4년 반)",
            "그동안 거의 먹지 않고 알 곁을 지킨다",
            "차갑고 깊은 저층 암반에 붙어 산다",
            "몸에 작은 돌기가 돋아 있다",
        ],
        "sources": ["NOAA Ocean Exploration", "MBARI"],
        "accuracy_flags": {"bioluminescent": False, "swims": True, "max_depth_m": 2600},
        "situation_id": "discovery_swim", "habitat_zone": "benthic",
        "appearance": ("a Graneledone boreopacifica, a purplish deep-sea octopus with a rounded "
                       "warty mantle and eight arms, resting on rock in the cold deep"),
        "anatomy_lock": ("a single deep-sea octopus body with eight arms and a rounded bumpy mantle; "
                         "keep the octopus form unchanged"),
        "forbidden_features": ("ear-like fins, fish head, hard shell, or extra limbs"),
        "hud_callouts": [{"slot": "left-mid", "title": "ARMS ×8", "sub": "SUCKERED"},
                         {"slot": "right-mid", "title": "MANTLE", "sub": "WARTY"}],
        "cut_behaviors": {
            "discovery": "clings to dark rock in the cold deep",
            "behavior": "slowly crawls across the rock with its eight arms",
            "detail": "turns, its rounded warty mantle catching the ROV light",
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
