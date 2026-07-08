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
    # === 2차 확충 (Commons/NOAA 실사 영상 검증 통과분) ===
    "bathynomus giganteus": {
        "scientific_name": "Bathynomus giganteus",
        "common_name_ko": "대왕등각류",
        "common_name_en": "Giant isopod",
        "depth_range_m": "170-2140",
        "distribution": "서대서양·멕시코만 심해",
        "habitat": "심해 저층(진흙·모래 바닥)",
        "diet": ["죽은 물고기", "고래 사체", "해삼"],
        "fun_facts": [
            "육지의 쥐며느리·공벌레와 같은 등각류다",
            "몸길이가 30cm를 넘는 심해의 대형 청소부다",
            "먹이가 드문 바닥에서 죽은 동물을 먹는다",
            "에너지를 아끼려 거의 움직이지 않는다",
            "몇 달을 먹지 않고 버티기도 한다",
        ],
        "sources": ["NOAA", "WoRMS"],
        "accuracy_flags": {"bioluminescent": False, "swims": False, "max_depth_m": 2140},
        "situation_id": "discovery_swim", "habitat_zone": "benthic",
        "appearance": ("a Bathynomus giganteus (giant isopod), a large pale deep-sea isopod "
                       "with a segmented armored body and many legs, like a giant woodlouse"),
        "anatomy_lock": ("a single segmented isopod body with overlapping armored plates and "
                         "multiple legs; keep the woodlouse-like form; no fins, no tentacles"),
        "forbidden_features": ("fish head, tentacles, shell of a crab, or extra body sections"),
        "hud_callouts": [{"slot": "left-mid", "title": "SEGMENTS", "sub": "ARMORED"},
                         {"slot": "right-mid", "title": "SCAVENGER", "sub": "DEEP BENTHOS"}],
        "cut_behaviors": {
            "discovery": "rests on the pale muddy seafloor in the darkness",
            "behavior": "slowly walks across the sediment on many legs",
            "detail": "its segmented armored body catching the ROV light",
        },
    },
    "crossota sp.": {
        "scientific_name": "Crossota sp.",
        "common_name_ko": "심해붉은해파리",
        "common_name_en": "Deep-sea red medusa",
        "depth_range_m": "1000-4000",
        "distribution": "전 세계 심해 중층",
        "habitat": "심해 중층(유영성)",
        "diet": ["작은 동물플랑크톤"],
        "fun_facts": [
            "심해 중층을 떠다니는 트라키해파리다",
            "붉은 색은 빛이 없는 심해에서 검게 보여 몸을 숨긴다",
            "종 모양 몸에서 가는 촉수를 방사상으로 뻗는다",
            "촉수를 펼쳐 작은 먹이를 기다린다",
        ],
        "sources": ["NOAA Ocean Exploration"],
        "accuracy_flags": {"bioluminescent": False, "swims": True, "max_depth_m": 4000,
                           "transparent_body": False},
        "situation_id": "discovery_swim", "habitat_zone": "pelagic",
        "appearance": ("a Crossota deep-sea red trachymedusa, a small red bell-shaped jellyfish "
                       "with many fine tentacles radiating outward, drifting in dark open water"),
        "anatomy_lock": ("a single soft red medusa bell with radial canals and many thin "
                         "tentacles; keep the jellyfish form; no fish parts, no hard shell"),
        "forbidden_features": ("fish head, octopus arms, hard shell, or a stalk"),
        "hud_callouts": [{"slot": "left-mid", "title": "BELL", "sub": "RED PIGMENT"},
                         {"slot": "right-mid", "title": "TENTACLES", "sub": "RADIAL"}],
        "cut_behaviors": {
            "discovery": "drifts in the open darkness of the midwater",
            "behavior": "pulses its red bell, tentacles spread wide",
            "detail": "hovers, its fine tentacles trailing in the black water",
        },
    },
    "actinoscyphia aurelia": {
        "scientific_name": "Actinoscyphia aurelia",
        "common_name_ko": "파리지옥말미잘",
        "common_name_en": "Venus flytrap anemone",
        "depth_range_m": "1000-1600",
        "distribution": "멕시코만·대서양 심해",
        "habitat": "심해 저층 암반·산호(물살 있는 곳)",
        "diet": ["떠내려오는 유기물", "동물플랑크톤"],
        "fun_facts": [
            "식충식물 파리지옥처럼 입 원반을 닫아 먹이를 잡는다",
            "빠른 물살이 지나는 심해 절벽·산호에 붙어 산다",
            "물살 방향으로 몸을 돌려 먹이를 기다린다",
            "잡은 먹이를 감싸 놓치지 않는다",
        ],
        "sources": ["NOAA Ocean Exploration", "WoRMS"],
        "accuracy_flags": {"bioluminescent": False, "swims": False, "max_depth_m": 1600},
        "situation_id": "discovery_swim", "habitat_zone": "benthic",
        "appearance": ("an Actinoscyphia aurelia (Venus flytrap sea anemone), a pale pink deep-sea "
                       "anemone on a stalk whose crown of tentacles can fold shut like a Venus flytrap"),
        "anatomy_lock": ("a single anemone on a stalk with a crown of tentacles that folds closed; "
                         "keep the anemone form; no fish, no shell, no arms"),
        "forbidden_features": ("fish head, octopus arms, hard shell, or free swimming"),
        "hud_callouts": [{"slot": "left-mid", "title": "ORAL DISC", "sub": "FOLDS SHUT"},
                         {"slot": "right-mid", "title": "STALK", "sub": "ANCHORED"}],
        "cut_behaviors": {
            "discovery": "clings to a rocky ledge in the current",
            "behavior": "spreads its ring of tentacles into the flow",
            "detail": "folds its oral disc closed like a trap",
        },
    },
    "megalodicopia hians": {
        "scientific_name": "Megalodicopia hians",
        "common_name_ko": "육식멍게",
        "common_name_en": "Predatory tunicate",
        "depth_range_m": "200-1100",
        "distribution": "북태평양 심해(몬터레이 협곡 등)",
        "habitat": "심해 협곡 암벽",
        "diet": ["작은 갑각류", "동물플랑크톤"],
        "fun_facts": [
            "보통 멍게는 물을 걸러 먹지만 이 종은 먹이를 잡는다",
            "큰 두건 같은 입을 벌리고 있다가 순간적으로 닫는다",
            "심해 협곡의 암벽에 붙어 움직이지 않는다",
            "다가온 작은 동물을 두건으로 감싸 삼킨다",
        ],
        "sources": ["MBARI", "WoRMS"],
        "accuracy_flags": {"bioluminescent": False, "swims": False, "max_depth_m": 1100},
        "situation_id": "discovery_swim", "habitat_zone": "benthic",
        "appearance": ("a Megalodicopia hians (predatory tunicate), a translucent deep-sea sea squirt "
                       "on a stalk with a large gaping hood-like oral siphon that can snap shut"),
        "anatomy_lock": ("a single translucent tunicate on a stalk with one large hood-like opening; "
                         "keep the sea-squirt form; no fish, no arms, no shell"),
        "forbidden_features": ("fish head, octopus arms, hard shell, or free swimming"),
        "hud_callouts": [{"slot": "left-mid", "title": "HOOD", "sub": "TRAPS PREY"},
                         {"slot": "right-mid", "title": "STALK", "sub": "ON WALL"}],
        "cut_behaviors": {
            "discovery": "clings to the dark canyon wall",
            "behavior": "holds its hood-like mouth wide open",
            "detail": "snaps the hood shut around drifting prey",
        },
    },
    "umbellula sp.": {
        "scientific_name": "Umbellula sp.",
        "common_name_ko": "심해바다조름",
        "common_name_en": "Deep-sea sea pen",
        "depth_range_m": "100-6000",
        "distribution": "전 세계 심해 저층",
        "habitat": "심해 저층(진흙·모래에 고정)",
        "diet": ["떠내려오는 동물플랑크톤"],
        "fun_facts": [
            "산호의 친척인 자포동물 군체다",
            "긴 자루 끝에 폴립이 모여 꽃처럼 보인다",
            "한 개체가 아니라 작은 폴립 여럿이 모인 군체다",
            "자루를 바닥에 꽂고 물살에 흔들리며 먹이를 거른다",
        ],
        "sources": ["MBARI", "WoRMS"],
        "accuracy_flags": {"bioluminescent": False, "swims": False, "max_depth_m": 6000},
        "situation_id": "discovery_swim", "habitat_zone": "benthic",
        "appearance": ("an Umbellula deep-sea sea pen, a long slender stalk anchored in the seabed "
                       "with a cluster of polyps at the top like a flower on a stem"),
        "anatomy_lock": ("a single long stalk with a cluster of polyps at the tip; keep the sea-pen "
                         "form; no fish, no arms, no shell"),
        "forbidden_features": ("fish head, octopus arms, hard shell, or free swimming"),
        "hud_callouts": [{"slot": "left-mid", "title": "STALK", "sub": "IN SEDIMENT"},
                         {"slot": "right-mid", "title": "POLYPS", "sub": "COLONY"}],
        "cut_behaviors": {
            "discovery": "rises from the muddy seabed in the darkness",
            "behavior": "sways gently in the current on its long stalk",
            "detail": "its crown of polyps catching the ROV light",
        },
    },
    # (카리브암초오징어는 얕은 바다 종이라 marine_life 카테고리로 이동함)
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
