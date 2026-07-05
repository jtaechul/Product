"""deep_sea 프롬프트 템플릿 엔진 — 종 데이터로부터 3컷 프롬프트를 자동 조립.

구조: [스타일 블록(고정)] + [종 형태 블록(데이터)] + [컷 블록(행동+카메라)]
- 새 종 추가 = data.SPECIES 에 appearance/cut_behaviors 만 채우면 프롬프트 자동 생성.
- 심해(무광층) 규칙: 태양광·수면 표현 금지 → 조명은 ROV 라이트만.
  ※ 금지어("sunlight" 등)는 게이트가 검출하므로, 템플릿 문구 자체에 금지어를 쓰지 않고
    "far below the reach of any natural light" 처럼 부정 없이 서술한다.
- 실사 ROV 룩: 과도한 선명함·시네마틱 이펙트 배제(저화질 카메라 질감 명시).
"""
from __future__ import annotations

# 스타일 블록 (deep_sea_realism v4 — 무태양광·무기포·풀프레임·저화질 ROV 실사)
_STYLE_BLOCK = (
    "Authentic footage from a scientific deep-sea ROV (remotely operated vehicle) at about "
    "{depth_hint} meters depth, in total darkness far below the reach of any natural light. "
    "The scene is lit ONLY by the vehicle's own floodlights: a hard, narrow beam with sharp "
    "falloff into pure black; everything outside the beam stays black. "
    "Gentle mechanical camera drift and faint vibration of an underwater vehicle. "
    "Practical low-grade scientific camera look: soft focus, visible video noise, mild compression "
    "artifacts, muted desaturated colors, limited dynamic range, slight motion blur. "
    # 물리 정확성(하드): 이 수심엔 사람/호흡장비가 닿을 수 없어 기포원이 없다 → 상승 기포 전면 금지.
    # (게이트 오탐 방지를 위해 'diver/human' 단어는 쓰지 않고 같은 뜻을 전달)
    "This depth is far beyond any level people or their breathing gear can reach, so there is no "
    "source of air at all: absolutely NO air bubbles of any kind, no rising bubbles, no bubble "
    "streams or columns, no breathing bubbles, no gas escaping anywhere in the scene. "
    # 세로 풀프레임(레터박스 금지)
    "The image fills the entire vertical 9:16 frame edge to edge: no black bars, no letterbox, "
    "no widescreen crop, no cinematic aspect ratio. "
    "NOT sharp, NOT cinematic, no dramatic lighting effects, no lens flares, no light shafts from "
    "above, no on-screen text, no HUD, no watermark."
)

# ROV 존재감 블록 — 조명은 카메라와 동축(그림자·후방산란 방향 일치), 기체 힌트는 가장자리만,
# 스케일 레이저는 '점 2개'만(빔·선 금지 → 할루시네이션 억제). 생물 접촉 금지.
_ROV_BLOCK = (
    "The floodlights are mounted right next to the camera on the same vehicle, so subjects are "
    "lit head-on from the camera's position and their shadows fall away from the camera. "
    "Out-of-focus particles drifting close to the lens catch the beam and bloom into soft pale "
    "specks (backscatter), giving the honest look of real underwater vehicle footage. "
    "At the very edge of the frame a hint of the vehicle itself is barely visible — a dark blurred "
    "corner of its metal frame or a folded manipulator arm resting at the bottom edge, out of "
    "focus; it never reaches toward the animal and never enters the center of the frame. "
    "Two tiny dim parallel red laser dots are projected onto the animal's body for scientific "
    "scale measurement — just two small dots, no visible beams, no lines."
)

# 서식대별 환경 블록 — habitat_zone 데이터가 배경·부유물 밀도를 결정
_ENV_BLOCKS = {
    # 해저(저서): 퇴적층이 하단에 보이고 부유물 짙음
    "benthic": (
        "Setting: just above the deep seafloor. A flat plain of pale fine silt and soft sediment "
        "fills the lower part of the frame and fades into darkness; the water column above stays "
        "pure black. The water is thick with suspended sediment and marine snow — dense pale "
        "particles hanging and slowly sinking everywhere in the beam (they never rise), heaviest "
        "near the bottom, and a faint haze of silt softens everything near the seafloor."
    ),
    # 원양(수층): 흑수 배경, 부유물은 옅게
    "pelagic": (
        "Setting: open black midwater far above the seafloor — no bottom, no walls, nothing but "
        "endless dark water in every direction. A light scatter of marine snow drifts and slowly "
        "sinks through the beam (the particles never rise)."
    ),
}

# 종 형태 블록 — 형태 왜곡 금지 (하드 룰)
_ANATOMY_BLOCK = (
    "The animal is {appearance}. "
    "Its true anatomy must be preserved exactly throughout: {anatomy_lock}. "
    "Never show {forbidden_features}. The creature stays its real size and moves only in ways "
    "this real species moves — slow, calm, energy-saving deep-sea motion."
)

# 컷 블록 — 카메라·연출 (스타일 스펙: slow push-in / lateral track / macro hold)
_CUT_BLOCKS = {
    "discovery": (
        "Discovery shot: at first the frame is almost entirely black water with marine snow. "
        "The floodlight beam slowly sweeps and the animal gradually emerges from the darkness "
        "into the edge of the light, {behavior}. The camera drifts slowly toward it. "
        "Suspenseful, quiet documentary mood."
    ),
    "behavior": (
        "Behavior shot: the camera tracks laterally alongside the animal as it {behavior}. "
        "The floodlight keeps it against pure black open water. Immersive observational mood."
    ),
    "detail": (
        "Detail shot: the camera very slowly closes in and holds a near-macro view while the "
        "animal {behavior}. Fine skin texture and body details become visible inside the beam. "
        "Intimate, mysterious mood."
    ),
}

_FORMAT_BLOCK = "Vertical 9:16 video."


def build_cut_prompt(species_entry: dict, cut_type: str) -> str:
    """종 데이터 + 컷 타입 → 완성 프롬프트."""
    flags = species_entry.get("accuracy_flags", {})
    depth = species_entry.get("depth_range_m", "1000-4000")
    behaviors = species_entry["cut_behaviors"]

    style = _STYLE_BLOCK.format(depth_hint=depth.replace("-", "–"))
    env = _ENV_BLOCKS[species_entry.get("habitat_zone", "pelagic")]
    anatomy = _ANATOMY_BLOCK.format(
        appearance=species_entry["appearance"],
        anatomy_lock=species_entry["anatomy_lock"],
        forbidden_features=species_entry["forbidden_features"],
    )
    cut = _CUT_BLOCKS[cut_type].format(behavior=behaviors[cut_type])

    parts = [style, env, _ROV_BLOCK, anatomy, cut, _FORMAT_BLOCK]

    # 발광 종이 아닌 경우: 스스로 빛나는 표현이 생기지 않도록 명시(금지어 없이 서술)
    if not flags.get("bioluminescent"):
        parts.insert(2, "The animal itself emits no light of its own; it is visible only where the vehicle's beam hits it.")

    return " ".join(parts)


def build_cuts(species_entry: dict) -> list[dict]:
    """표준 3컷 (discovery → behavior → detail) 프롬프트 일괄 생성."""
    return [
        {"cut_type": ct, "prompt": build_cut_prompt(species_entry, ct)}
        for ct in ("discovery", "behavior", "detail")
    ]
