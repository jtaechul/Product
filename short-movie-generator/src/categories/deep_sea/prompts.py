"""deep_sea 프롬프트 템플릿 엔진 — 종 데이터로부터 3컷 프롬프트를 자동 조립.

구조: [스타일 블록(고정)] + [종 형태 블록(데이터)] + [컷 블록(행동+카메라)]
- 새 종 추가 = data.SPECIES 에 appearance/cut_behaviors 만 채우면 프롬프트 자동 생성.
- 심해(무광층) 규칙: 태양광·수면 표현 금지 → 조명은 ROV 라이트만.
  ※ 금지어("sunlight" 등)는 게이트가 검출하므로, 템플릿 문구 자체에 금지어를 쓰지 않고
    "far below the reach of any natural light" 처럼 부정 없이 서술한다.
- 실사 ROV 룩: 과도한 선명함·시네마틱 이펙트 배제(저화질 카메라 질감 명시).
"""
from __future__ import annotations

# 스타일 블록 (deep_sea_realism v5 — 저노출·무핀조명·무태양광·무기포·풀프레임 ROV 실사)
_STYLE_BLOCK = (
    "Authentic footage from a scientific deep-sea ROV (remotely operated vehicle) at about "
    "{depth_hint} meters depth, in total darkness far below the reach of any natural light. "
    # 조명 규칙(핵심): 광원은 카메라 옆 램프, 정면 소구역만 밝고 나머지는 거의 검정.
    # 빛기둥/원뿔/광선/램프 자체는 절대 보이지 않음. 위쪽 광원 없음.
    "The only illumination comes from lamps on the vehicle right beside the camera, pointing "
    "forward the same way the camera looks. They light just a small patch directly in front of "
    "the camera; the lamps themselves and any visible cone, column, shaft or ray of light are "
    "never shown. Nothing lights the scene from above and nothing overhead is lit. Beyond the "
    "small lit patch the picture falls off fast into near-total blackness, and the corners and "
    "edges of the frame are black. "
    # 밝기(하드): 심해에 맞게 매우 어둡게, 저노출.
    "The shot is deliberately underexposed and very dark — a dim, only partly-lit subject against "
    "overwhelming darkness; NOT a bright, evenly lit or daylight-like scene. "
    "Gentle mechanical camera drift and faint vibration of an unmanned robotic vehicle. "
    "Practical low-grade scientific camera look: soft focus, visible video noise, mild compression "
    "artifacts, muted desaturated colors, limited dynamic range, slight motion blur. "
    # 물리 정확성(기포) — 종합 해법:
    #  (a) 명사(bubble/air/gas) 미사용 → 핑크코끼리 역효과 회피(리포트 존중)
    #  (b) 기포의 정의적 특징인 '상승 운동'을 방향으로 명시 통제 → 명시적 방지(요청 충족)
    #  (c) 대체 모션 원천을 확정 → 모델이 역동성을 기포로 채울 이유 제거
    "The water is utterly still and motionless, a heavy, dense, high-pressure column that hangs "
    "silent and undisturbed; its surface is impossibly far above and completely out of view. "
    "The only things that move at all are the animal's own slow, graceful motion, the gentle "
    "drift of the slowly pushing camera, and the marine snow — and the marine snow only ever "
    "sinks slowly DOWNWARD under gravity. In this sealed, purely liquid environment nothing ever "
    "rises, streams, jets or floats upward toward the top of the frame; there are no upward trails "
    "or plumes of any kind; every suspended speck moves only downward or hangs perfectly still. "
    "Everything else in the water is completely calm and static. "
    # 세로 풀프레임(레터박스 금지)
    "The image fills the entire vertical 9:16 frame edge to edge: no black bars, no letterbox, "
    "no widescreen crop, no cinematic aspect ratio. "
    "NOT sharp, NOT cinematic, no dramatic lighting effects, no lens flares, no light shafts from "
    "above, no on-screen text, no HUD, no watermark."
)

# ROV 존재감 블록 — 조명은 카메라와 동축(그림자·후방산란 방향 일치), 기체 힌트는 가장자리만.
# 스케일 레이저는 제거(실측상 Veo가 허공에 잘못 그림 → 할루시네이션 유발).
_ROV_BLOCK = (
    "Because the lamps sit right next to the camera, the subject is lit head-on from the camera's "
    "position and its shadows fall away from the camera into the dark. "
    "Out-of-focus particles drifting close to the lens catch the light and bloom into soft pale "
    "specks (backscatter), giving the honest look of real underwater vehicle footage. "
    "At the very edge of the frame a hint of the vehicle itself is barely visible — a dark blurred "
    "corner of its metal frame or a folded manipulator arm resting at the bottom edge, out of "
    "focus; it never reaches toward the animal and never enters the center of the frame."
)

# 서식대별 환경 블록 — habitat_zone 데이터가 배경을 결정.
# 주의(기포 트리거): '해저 근접·실트 교란' 묘사는 모델이 스러스터 흙먼지→기포로 연상시키므로
# benthic도 '먼 배경'으로만 둔다(생물은 열린 물에서 호버링, 바닥은 저 아래 부드럽게).
_ENV_BLOCKS = {
    # 해저(저서): 생물은 열린 어둠에 호버링, 해저는 저 멀리 부드럽고 흐릿한 배경으로만
    "benthic": (
        "Setting: the animal hovers in open, still, pitch-black water. Far below it and well out "
        "of focus, a faint dark seafloor is only dimly suggested in the distance — soft, calm and "
        "undisturbed, never close and never kicked up. The water immediately around the animal is "
        "open and clear of any nearby bottom. A light scatter of marine snow hangs almost "
        "motionless and settles gently downward."
    ),
    # 원양(수층): 흑수 배경, 부유물은 옅게
    "pelagic": (
        "Setting: open black midwater far above the seafloor — no bottom, no walls, nothing but "
        "endless still dark water in every direction. A light scatter of marine snow hangs almost "
        "motionless and settles gently downward through the lit area."
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
        "Discovery shot: the animal is faintly lit against surrounding darkness, {behavior}. "
        "Throughout the shot the dim light stays perfectly steady, constant and unchanging. The "
        "animal comes into fuller view only because the slowly drifting camera pushes gently "
        "closer through the calm water. Suspenseful, quiet documentary mood."
    ),
    "behavior": (
        "Behavior shot: the camera tracks laterally alongside the animal as it {behavior}. "
        "The vehicle's light keeps it dimly visible against pure black water, the surroundings "
        "lost in darkness. Immersive observational mood."
    ),
    "detail": (
        "Detail shot: the camera very slowly closes in and holds a near-macro view while the "
        "animal {behavior}. Fine skin texture and body details become visible where the vehicle's "
        "light directly falls on it, the rest fading to black. Intimate, mysterious mood."
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
        parts.insert(2, "The animal itself emits no light of its own; it is visible only where the vehicle's light directly falls on it.")

    return " ".join(parts)


def build_cuts(species_entry: dict) -> list[dict]:
    """표준 3컷 (discovery → behavior → detail) 프롬프트 일괄 생성."""
    return [
        {"cut_type": ct, "prompt": build_cut_prompt(species_entry, ct)}
        for ct in ("discovery", "behavior", "detail")
    ]
