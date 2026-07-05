"""deep_sea 프롬프트 템플릿 엔진 — 종 데이터로부터 3컷 프롬프트를 자동 조립.

구조: [스타일 블록(고정)] + [종 형태 블록(데이터)] + [컷 블록(행동+카메라)]
- 새 종 추가 = data.SPECIES 에 appearance/cut_behaviors 만 채우면 프롬프트 자동 생성.
- 심해(무광층) 규칙: 태양광·수면 표현 금지 → 조명은 ROV 라이트만.
  ※ 금지어("sunlight" 등)는 게이트가 검출하므로, 템플릿 문구 자체에 금지어를 쓰지 않고
    "far below the reach of any natural light" 처럼 부정 없이 서술한다.
- 실사 ROV 룩: 과도한 선명함·시네마틱 이펙트 배제(저화질 카메라 질감 명시).
"""
from __future__ import annotations

# 스타일 블록 (deep_sea_realism v2 — 실측 피드백 반영: 무태양광·저화질 ROV 실사)
_STYLE_BLOCK = (
    "Authentic footage from a scientific deep-sea ROV (remotely operated vehicle) at about "
    "{depth_hint} meters depth, in total darkness far below the reach of any natural light. "
    "The scene is lit ONLY by the vehicle's own floodlights: a hard, narrow beam with sharp "
    "falloff into pure black; everything outside the beam stays black. "
    "Murky blue-green water, dense drifting marine snow, suspended sediment particles crossing "
    "the light beam. Gentle mechanical camera drift and faint vibration of an underwater vehicle. "
    "Practical low-grade scientific camera look: soft focus, visible video noise, mild compression "
    "artifacts, muted desaturated colors, limited dynamic range, slight motion blur. "
    "NOT sharp, NOT cinematic, no dramatic lighting effects, no lens flares, no light shafts from "
    "above, no on-screen text, no HUD, no watermark."
)

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
    anatomy = _ANATOMY_BLOCK.format(
        appearance=species_entry["appearance"],
        anatomy_lock=species_entry["anatomy_lock"],
        forbidden_features=species_entry["forbidden_features"],
    )
    cut = _CUT_BLOCKS[cut_type].format(behavior=behaviors[cut_type])

    parts = [style, anatomy, cut, _FORMAT_BLOCK]

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
