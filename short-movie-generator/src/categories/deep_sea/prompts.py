"""deep_sea 프롬프트 템플릿 엔진 — 종 데이터로부터 3컷 프롬프트를 자동 조립.

v9 재구성 (Gemini 분석 반영 — 간결·피사체 우선):
- 피사체(생물)를 맨 앞에 배치 → 모델 리소스가 형태·움직임에 먼저 집중.
- 유발어 제거: 'column'(기포 기둥 오역), 'vibration'(스크류 기포 연상), 'backscatter'(기포 번짐),
  'beam'(핀조명), 'cinematic'(레터박스), 그리고 상승운동 나열(핑크코끼리 과부하)까지 전면 배제.
- 물의 정적은 '상태'로 짧게 확정(부정어 나열 대신). 대체 모션은 생물·카메라·하강 마린스노우.
- 비협상 요소는 압축 유지: 데이터 수심, 저노출 어둠, 형태 잠금, 카메라옆 램프(핀조명 아님), 풀프레임.
- 검은 바/레터박스는 imageprep(9:16 사전합성) + assembler가 구조적으로 처리 → 프롬프트 부정 불필요.
"""
from __future__ import annotations

# 1) 피사체 (맨 앞) — 종 데이터의 appearance 사용
_SUBJECT_BLOCK = (
    "{appearance}, moving slowly and gracefully with calm, energy-saving deep-sea motion."
)

# 2) 형태 잠금 (피사체 바로 뒤, 압축)
_ANATOMY_BLOCK = "Keep its true anatomy exactly: {anatomy_lock}. Never {forbidden_features}."

# 3) 장면/조명/물 — 무인 ROV, 카메라 동축 정면광(설비 미노출), 저노출 어둠, 정적 물, 하강 마린스노우
# 주의: 'lamp/beam/flashlight/spotlight' 등 명사를 부르지 않는다(핑크코끼리 → 설비·빛기둥 유발).
# 대신 조명의 '방향(렌즈 뒤→정면 전진)'과 '화면엔 물+생물만' 긍정문으로 서술.
_SCENE_BLOCK = (
    "Filmed by an unmanned scientific ROV at about {depth_hint} meters deep in the pitch-black "
    "abyss. Everything is lit only from the camera's own viewpoint: the light comes from directly "
    "behind the lens and travels straight forward in the exact direction the camera looks, so the "
    "animal is lit from the front and its shadows fall away from the camera into the darkness "
    "behind it; the light travels horizontally forward and never comes from overhead. Nothing but "
    "the animal and empty darkness is visible in the frame. The surrounding abyss is a dense, "
    "absolutely motionless, completely dark void that fades instantly into total underexposed "
    "blackness at the edges. Everything stays perfectly calm and static, with no movement anywhere "
    "except the animal itself; the space around it is empty and clear. The light is dim, steady "
    "and unchanging."
)

# 4) 서식대 (짧게) — habitat_zone 데이터가 배경 결정
_ENV_BLOCKS = {
    "benthic": (
        "Far below the animal a faint dark seafloor is only dimly suggested in the distance, calm "
        "and undisturbed; the animal hovers in the open darkness well above it."
    ),
    "pelagic": (
        "The animal hovers in the open black abyss with no bottom or walls in view."
    ),
}

# 5) 스타일/규격 (압축, 긍정 위주)
_STYLE_BLOCK = (
    "Muted desaturated colors, soft focus, mild video noise, low-grade scientific camera look. "
    "Full-frame vertical 9:16, filling the frame edge to edge."
)

# 6) 컷별 모션 (맨 끝) — 종 데이터의 cut_behaviors 사용
# 스토리 아크: 컷1 어둠 속 형체 등장(카메라 미인지) → 컷2 가까이 추적(여전히 미인지, 긴장 상승)
# → 컷3 카메라를 뒤늦게 알아채고 마주본 뒤 조용히 이탈(반응 페이오프). 전부 실제 행동 범위.
_CUT_BLOCKS = {
    "discovery": (
        "At first only a faint shape resolves out of the black water; the camera drifts slowly "
        "toward it and it comes into fuller view as it {behavior}, unaware of the camera. "
        "Quiet, ominous, mysterious mood, slow building tension."
    ),
    "behavior": (
        "The camera glides closer and tracks smoothly alongside, still unnoticed, as it "
        "{behavior}. Tense, intimate, immersive mood as if secretly observing it."
    ),
    "detail": (
        "Then, up close, it {behavior}. Its form is seen clearly where the light falls while the "
        "rest fades to black — a charged, face-to-face payoff moment before it slips away. "
        "Intimate, dramatic mood."
    ),
}


def build_cut_prompt(species_entry: dict, cut_type: str) -> str:
    """종 데이터 + 컷 타입 → 완성 프롬프트 (피사체 우선·간결)."""
    flags = species_entry.get("accuracy_flags", {})
    depth = species_entry.get("depth_range_m", "1000-4000")
    behaviors = species_entry["cut_behaviors"]

    subject = _SUBJECT_BLOCK.format(appearance=species_entry["appearance"])
    anatomy = _ANATOMY_BLOCK.format(
        anatomy_lock=species_entry["anatomy_lock"],
        forbidden_features=species_entry["forbidden_features"],
    )
    scene = _SCENE_BLOCK.format(depth_hint=depth.replace("-", "–"))
    env = _ENV_BLOCKS[species_entry.get("habitat_zone", "pelagic")]
    cut = _CUT_BLOCKS[cut_type].format(behavior=behaviors[cut_type])

    parts = [subject, anatomy, scene, env, _STYLE_BLOCK, cut]

    # 발광 종이 아니면 짧게 명시 (게이트 오탐 방지: glow/luminous 단어 미사용)
    if not flags.get("bioluminescent"):
        parts.insert(2, "It produces no light of its own.")

    return " ".join(parts)


def build_cuts(species_entry: dict) -> list[dict]:
    """표준 3컷 (discovery → behavior → detail) 프롬프트 일괄 생성."""
    return [
        {"cut_type": ct, "prompt": build_cut_prompt(species_entry, ct)}
        for ct in ("discovery", "behavior", "detail")
    ]


# ── narrated_wildlife 전환: 동적 야생다큐 프롬프트(수심 인지) ──
# 스파이크 검증: (A) crisp cinematic 프롬프트는 화질·카메라 우수하나, 심해종은 반드시
# '수심 인지형(어둠 + 형태 잠금 + 부정 제약: 햇빛·수면·기포·산호초 금지)'이어야 서식지가 맞다.
import re as _re  # noqa: E402


def _max_depth(depth_range_m: str) -> int:
    d = _re.sub(r"[^\d]", "", (depth_range_m or "").split("-")[-1])
    return int(d) if d else 4000


def _is_deep(depth_range_m: str) -> bool:
    return _max_depth(depth_range_m) >= 200  # 유광층(~200m) 아래 = 어둠 강제


_WILD_DEEP_SCENE = (
    "in the pitch-black deep sea at about {depth} meters, lit only by a single expedition camera "
    "light with total darkness all around; no sunlight, no water surface, no rising air bubbles, "
    "no coral reef; faint marine snow drifting slowly in the light beam."
)
_WILD_SHALLOW_SCENE = (
    "in its natural ocean habitat with soft natural underwater light and gentle marine snow; "
    "no divers, no boats, no man-made objects."
)
_WILD_CAM = {
    "discovery": "Open on a brief held wide shot in the open water, then a smooth dynamic push-in that snaps focus onto the action.",
    "behavior": "The camera glides with it while a smooth dynamic push-in snaps focus onto the action at the key moment.",
    "detail": "A close macro hold on the signature action, then a slow drift back.",
}
_WILD_TAIL = (
    "Naturalistic wildlife-documentary look, crisp cinematic detail. Keep the animal's exact "
    "anatomy — {anatomy_lock}; do not distort, add, or fabricate features or behavior. Never "
    "{forbidden}. Energetic, awe-inspiring wildlife mood. Vertical 9:16, filling the frame."
)


def build_cut_prompt_wildlife(species_entry: dict, cut_type: str) -> str:
    """동적 야생다큐 프롬프트(수심 인지 + 형태 잠금). 정확성 하드룰 유지."""
    depth = species_entry.get("depth_range_m", "1000-4000")
    behavior = species_entry["cut_behaviors"][cut_type]
    subject = f"{species_entry['appearance']}, performing its signature behavior: {behavior}."
    scene = (_WILD_DEEP_SCENE.format(depth=_max_depth(depth)) if _is_deep(depth)
             else _WILD_SHALLOW_SCENE)
    tail = _WILD_TAIL.format(anatomy_lock=species_entry["anatomy_lock"],
                             forbidden=species_entry["forbidden_features"])
    parts = [subject, scene, _WILD_CAM[cut_type], tail]
    if not species_entry.get("accuracy_flags", {}).get("bioluminescent"):
        parts.insert(1, "It produces no light of its own.")
    return " ".join(parts)


def build_cuts_wildlife(species_entry: dict) -> list[dict]:
    """야생다큐 3컷(discovery → behavior → detail) 프롬프트."""
    return [
        {"cut_type": ct, "prompt": build_cut_prompt_wildlife(species_entry, ct)}
        for ct in ("discovery", "behavior", "detail")
    ]
