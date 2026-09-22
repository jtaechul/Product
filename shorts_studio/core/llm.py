"""llm — 동화 대본 + 타깃 영상 AI 툴에 맞춘 영문 프롬프트 생성 (Gemini).

세 단계로 만든다.
  ① 줄거리 먼저 — 발단·전개·위기·절정·결말과 등장인물을 통째로 설계한다.
     컷 수에 따라 대목마다 몇 컷씩 줄지 미리 나눠, 컷이 늘면 이야기도 함께 두꺼워지게 한다.
  ② 컷 개요 — 컷마다 무슨 일이 벌어지는지 한 줄씩. 여기서 이야기가 한 칸씩 나아가는지 본다.
  ③ 컷 본문 — 그 개요를 여덟 개씩 묶어 나레이션·연기지시·영문 프롬프트를 쓴다.
  ④ 윤문 — 전체 나레이션을 **한 화면에 놓고** 말맛을 다듬는다. 묶음 경계에서 말이 끊기고,
     종결어미가 겹치고, 같은 인물 이름을 매 컷 되부르는 것은 전체를 봐야 잡힌다.
한 번에 다 시키면 모델이 앞뒤를 안 보고 컷을 지어내어 이야기가 끊기고,
컷이 많을수록 뒤쪽이 통째로 부실해진다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .tts import MARKERS, estimate_seconds, strip_markers

# Google 은 모델 아이디를 예고 없이 닫는다(gemini-2.5-flash 는 2026-09 에 막혀
# 대본 생성이 404 로 통째로 죽었다). 그래서 아이디를 하나로 못 박지 않고,
# **키로 실제 쓸 수 있는 목록을 받아** 아래 선호 순서대로 고른다(resolve_model).
MODELS = [
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-3-flash",
    "gemini-2.5-flash",
    "gemini-3.6-pro",
    "gemini-2.5-pro",
]

# 대본에 쓰면 안 되는 계열 — 이름만 보고 거른다.
_NOT_TEXT = ("tts", "embedding", "image", "vision", "aqa", "live", "native-audio")

_MODEL_PICK: dict[str, str] = {}


def available_models(client) -> list[str]:
    """이 키로 글을 만들 수 있는 모델 이름 목록."""
    out = []
    for m in client.models.list():
        name = str(getattr(m, "name", "") or "").split("/")[-1]
        acts = list(getattr(m, "supported_actions", None) or [])
        if not name or any(k in name for k in _NOT_TEXT):
            continue
        if acts and "generateContent" not in acts:
            continue
        out.append(name)
    return out


def resolve_model(client, want: str = "") -> str:
    """쓰겠다고 한 모델이 아직 살아 있으면 그대로, 막혔으면 살아 있는 것으로 바꾼다."""
    key = want or "*"
    if key in _MODEL_PICK:
        return _MODEL_PICK[key]
    try:
        names = available_models(client)
    except Exception as e:  # noqa: BLE001 — 목록 조회가 막혀도 생성은 시도해 본다
        print(f"::warning::모델 목록을 못 받았습니다({str(e)[:120]}). {want or MODELS[0]} 로 그냥 갑니다.")
        return want or MODELS[0]
    if not names:
        return want or MODELS[0]

    pick = ""
    for cand in ([want] if want else []) + MODELS:
        if cand and cand in names:
            pick = cand
            break
    if not pick:
        # 선호 목록이 전부 닫혔을 때 — 살아 있는 flash 계열 중 별칭(latest)을 먼저 본다.
        flash = [n for n in names if "flash" in n]
        pool = flash or names
        pick = next((n for n in pool if n.endswith("-latest")), pool[0])
    if want and pick != want:
        print(f"::warning::{want} 모델을 쓸 수 없어 {pick} 로 바꿉니다.")
    else:
        print(f"대본 모델: {pick}")
    _MODEL_PICK[key] = pick
    return pick

# 기준 이미지를 만들 인물 수 상한. 늘릴수록 운영자가 만들어야 할 이미지가 늘어난다.
MAX_CHARACTERS = 3

# 컷 수 상한. 컷 하나에 영상 클립 하나를 사람이 직접 만들어 올려야 하므로,
# 여기를 늘리면 코드가 아니라 운영자의 손이 그만큼 더 든다.
MAX_SCENES = 20

# 입을 움직이지 않게 하는 고정 문장. LLM이 매번 쓰기를 기대하지 않고 **무조건 붙인다**.
# 나레이터가 들려주는 이야기이므로 인물이 말하면 누가 말하는지 헷갈리고, 영상 AI가
# 지어낸 영어 입모양은 한국어 나레이션과도 어긋난다.
# 바라는 상태를 먼저 적는다 — 안전 검사기는 부정문을 못 읽고 낱말만 보기 때문이다.
SILENCE_LOCK = (
    "All characters keep their mouths completely closed and motionless for the entire shot, "
    "conveying everything through gesture, posture and eye expression alone. "
    "Silent pantomime performance with zero lip movement and no lip-sync."
)

# 네거티브 칸이 따로 있는 툴에는 여기까지 넣는다(프롬프트 본문이 아니라 전용 칸이라 안전).
SILENCE_NEGATIVE = "talking, speaking, mouth open, lip sync, moving lips, dialogue, subtitles, text"

STYLE_KEYWORDS = (
    "Korean traditional folklore style, 3D animated character, hanbok, "
    "warm storybook lighting, soft pastel color palette, cinematic depth of field"
)

# 툴마다 프롬프트를 읽는 방식이 다르다 — 문법·파라미터를 각각 맞춰 준다.
TOOLS: dict[str, dict] = {
    "Runway (Gen-3/Gen-4)": {
        "guide": (
            "One flowing English paragraph. Lead with the camera move, then subject, then "
            "environment and lighting. No bullet lists, no negative prompts, no parameter flags "
            "(Runway sets aspect ratio in the UI). 40-70 words."
        ),
        "suffix": "",
        "negative": False,
        "ui_note": "Runway는 프롬프트에 파라미터를 쓰지 않습니다. 업로드 화면에서 9:16을 직접 선택하세요.",
    },
    "Pika": {
        "guide": (
            "Compact comma-separated English phrases (not full sentences), visual nouns and "
            "adjectives first, camera move last. 25-45 words. Do not write the parameter flags "
            "yourself; they are appended automatically."
        ),
        "suffix": " -ar 9:16 -motion 2 -fps 24",
        "negative": False,
        "ui_note": "Pika는 프롬프트 뒤 파라미터로 비율을 지정합니다. -ar 9:16 이 자동으로 붙습니다.",
    },
    "Luma (Dream Machine)": {
        "guide": (
            "Natural conversational English, 1-2 sentences describing what happens over the "
            "5 seconds, with one explicit camera move. 30-50 words. No parameter flags."
        ),
        "suffix": " Vertical 9:16 framing.",
        "negative": False,
        "ui_note": "Luma는 UI에서 9:16을 선택하세요. 프롬프트에도 세로 프레이밍을 명시해 두었습니다.",
    },
    "Kling": {
        "guide": (
            "Structured English: [Subject] [Action] [Environment] [Camera] [Lighting], separated "
            "by commas. 30-55 words. Kling uses a separate negative prompt field, so also produce "
            "a short negative prompt."
        ),
        "suffix": "",
        "negative": True,
        "ui_note": "Kling은 비율을 UI에서 9:16으로 두고, 네거티브 프롬프트는 별도 칸에 붙여넣으세요.",
    },
    "Sora": {
        "guide": (
            "Write like a film shot direction in English: shot size, lens feel, subject action, "
            "blocking, light, mood. One rich paragraph, 50-80 words. No parameter flags."
        ),
        "suffix": " Shot vertically for a 9:16 frame.",
        "negative": False,
        "ui_note": "Sora는 해상도를 UI에서 세로(9:16)로 선택하세요.",
    },
    "Veo (Google)": {
        "guide": (
            "One English paragraph covering subject, action, camera, and lighting, plus a short "
            "ambient audio cue at the end (Veo generates sound). 45-75 words. No parameter flags."
        ),
        "suffix": " Vertical 9:16 aspect ratio.",
        "negative": False,
        "ui_note": "Veo는 소리도 함께 생성하므로 프롬프트 끝에 주변음 묘사를 넣었습니다.",
    },
}

_SYSTEM = """You are a senior writer-director for Korean short-form folklore animation,
in the warm, humorous, gently moralistic style of 전래동화 / 태담동화 YouTube Shorts.

You always return a single valid JSON object. No markdown, no commentary."""


# 이야기를 나누는 다섯 대목과, 컷을 몇 개씩 줄지 정하는 비중.
# 컷이 늘어나면 각 대목이 함께 두꺼워져야 이야기가 헐거워지지 않는다.
ACTS: list[tuple[str, float]] = [
    ("발단", 0.20),   # 인물과 그가 바라는 것
    ("전개", 0.30),   # 일이 굴러가며 커진다 — 컷이 늘면 여기가 제일 많이 늘어난다
    ("위기", 0.20),   # 가로막히는 것
    ("절정", 0.20),   # 부딪히고 결판난다
    ("결말", 0.10),   # 거둬들이고 여운
]

# 한 번에 본문을 쓰게 할 씬 수. 이보다 많이 시키면 뒤쪽이 대충 써지고 응답이 잘린다.
SCENES_PER_CALL = 8


def allocate_acts(n_scenes: int) -> list[int]:
    """대목마다 컷을 몇 개씩 줄지 나눈다. 각 대목 최소 1개, 합은 정확히 n_scenes."""
    k = len(ACTS)
    n = max(k, int(n_scenes))
    rest = n - k                       # 대목마다 1개씩 깔고 남은 것을 비중대로
    raw = [rest * w for _, w in ACTS]
    out = [int(x) for x in raw]
    left = rest - sum(out)
    for i in sorted(range(k), key=lambda i: raw[i] - out[i], reverse=True)[:left]:
        out[i] += 1
    return [1 + x for x in out]


# ---------------------------------------------------------------- ① 줄거리

_PLOT_USER = """주제: {topic}
이 이야기는 {n_scenes}개의 컷으로 만들 세로 쇼츠입니다({total_sec}초 안팎).
먼저 **줄거리와 등장인물**만 설계하세요.

아래 JSON 스키마로만 답하세요.

{{
  "title": "쇼츠 제목 (한국어, 18자 이내, 호기심을 자극)",
  "logline": "한 문장 줄거리 (한국어)",
  "characters": [
    {{
      "name": "이름 (한국어, 2~4자)",
      "role": "이야기에서 맡은 역할 (한국어 한 줄)",
      "image_prompt": "이 인물의 전신 참조 이미지 1장을 만들 영문 프롬프트"
    }}
  ],
  "style_lock": "모든 씬에 그대로 붙일 색감·조명 고정 문장 (영문 1문장)",
  "cover_prompt": "표지(썸네일) 이미지 1장을 만들 영문 프롬프트",
  "acts": [
    {{"stage": "발단", "summary": "그 대목에서 실제로 벌어지는 일 (한국어 2~3문장)"}},
    {{"stage": "전개", "summary": "..."}},
    {{"stage": "위기", "summary": "..."}},
    {{"stage": "절정", "summary": "..."}},
    {{"stage": "결말", "summary": "..."}}
  ]
}}

[줄거리 규칙 — acts]
- **다섯 대목을 모두, 반드시 이 순서로** 채웁니다: 발단 · 전개 · 위기 · 절정 · 결말.
- **인과로 이어질 것.** 각 대목은 앞 대목 때문에 벌어져야 한다. "그리고"가 아니라 "그래서".
- 발단에서 **인물이 무엇을 원하는지**, 위기에서 **그것을 가로막는 것이 무엇인지**를 분명히 한다.
- 절정은 원하던 것과 가로막는 것이 정면으로 부딪히는 한 장면이어야 한다. 얼버무리지 않는다.
- 결말은 앞에서 깔아 둔 것으로 풀어낸다. 갑자기 등장하는 해결사·우연 금지.
- 이 이야기는 컷 {n_scenes}개로 펼쳐집니다. 대목별로 이만큼 배정됩니다: {allocation}
  배정이 많은 대목은 **사건을 여러 단계로 쪼갤 수 있을 만큼** 두껍게 쓰세요.
  (예: 전개에 여섯 컷이면 "점점 커지는 일" 을 여섯 단계로 나눌 거리가 있어야 합니다.)

[등장인물 규칙 — characters]
- **최대 {max_chars}명.** 주인공 1명은 반드시 넣고, 이야기에 꼭 필요한 인물만 더한다.
  기준 이미지를 한 장씩 만들어야 하므로 많을수록 운영자 일이 늘어난다.
- 여기 없는 사람은 뒷모습·실루엣·멀리 있는 군중으로만 나온다. 얼굴이 보이는 인물은 여기 적는다.
- image_prompt: 정면 전신, 중립 표정, 평범하게 선 자세, 배경은 단순한 단색.
  나이·체형·머리 모양·한복 색과 무늬·신발까지 **구체적으로** 적는다.
  이 한 장이 모든 씬의 기준이 되므로 **외모는 오직 여기서만** 정한다.
  인물끼리 한눈에 구별되게 색과 실루엣을 다르게 준다.
  스타일 키워드를 포함할 것: {style}

[표지 프롬프트 규칙 — cover_prompt]
- 쇼츠 맨 앞에 1.8초 뜨는 **세로 9:16 표지 이미지 한 장**을 만들 영문 프롬프트.
- 이야기 전체를 한눈에 알리는 **가장 인상적인 한 장면**. 넘기려던 손가락을 멈추게 할 것.
- ⭐ **글자를 넣지 않는다.** "no text, no letters, no title, no watermark" 를 반드시 포함.
  제목은 시스템이 한글로 또렷하게 얹는다. 영상 AI가 쓰는 한글은 반드시 깨진다.
- ⭐ **화면 위쪽 삼분의 일은 하늘·안개·단색 벽처럼 단순하게 비워 둔다.** 그 위에 제목이 올라간다.
  인물과 핵심 사물은 가운데와 아래쪽에 둔다.
- ⭐ **화면 맨 위와 맨 아래 끝자락에는 중요한 것을 두지 않는다.** 검은 띠가 덮인다.
- 인물이 나온다면 위 등장인물 중 주인공. 외모는 적지 않는다(참조 이미지를 함께 넣는다).
- 색감은 style_lock 과 같은 결. 스타일 키워드를 포함할 것: {style}

[색감 고정 문장 규칙 — style_lock]
- 색·빛·질감을 못 박는 영문 **1문장**. 이 문장이 모든 씬 끝에 **글자 그대로** 붙는다.
- 반드시 담을 것: 색 팔레트(구체적인 색 3~4개), 광원의 성질, 시간대 느낌, 렌더링 질감.
- 예: "Consistent warm palette of ochre, deep indigo and pale jade under soft diffused
  late-afternoon light, gentle film grain, matte 3D storybook render."
- 장면마다 달라질 내용(장소·날씨·감정)은 여기 쓰지 않는다. 씬이 바뀌어도 **똑같아야** 한다.
"""


# ---------------------------------------------------------------- ② 컷 개요

_BEATS_USER = """아래는 확정된 줄거리입니다. 이것을 정확히 {n_scenes}개의 컷으로 나누되,
**지금은 각 컷에서 무슨 일이 벌어지는지 한 줄씩만** 적으세요. 대사나 프롬프트는 쓰지 마세요.

제목: {title}
한 줄 줄거리: {logline}
등장인물: {cast_list}

대목과 배정된 컷 수:
{acts}

아래 JSON 스키마로만 답하세요.

{{
  "beats": [
    {{
      "n": 1,
      "act": "발단",
      "summary": "그 컷에서 실제로 벌어지는 일 (한국어 한 문장)",
      "place": "장소 (한국어 몇 글자)",
      "cast": ["그 컷에 얼굴이 보이는 인물 이름"]
    }}
  ]
}}

[규칙]
- 정확히 {n_scenes}개. n은 1부터 {n_scenes}까지 빠짐없이.
- 대목별 배정 컷 수를 **정확히** 지킵니다. 순서도 발단 → 전개 → 위기 → 절정 → 결말 그대로.
- ⭐ **컷마다 이야기가 한 칸씩 나아갑니다.** 같은 상황을 각도만 바꿔 두 번 보여 주지 않습니다.
  앞 컷과 견주어 "무엇이 달라졌는가"를 한 마디로 댈 수 없으면 그 컷은 버리고 다시 쓰세요.
- ⭐ **앞 컷의 마지막 상태에서 이어 시작합니다.** 인물의 위치·손에 든 것·시간대가 이어져야 합니다.
- ⭐⭐ **단계를 건너뛰지 않습니다.** 다 쓴 뒤 이웃한 두 컷을 하나씩 짚으며 스스로 물어보세요:
  "앞 컷이 끝난 상태에서 이 컷이 **바로** 시작될 수 있는가? 사이에 빠진 일이 있는가?"
  빠진 일이 있으면 **그것도 컷으로 넣어** 개수를 맞추세요.
  (실패 예: '놀부가 못된 꾀를 마음먹었다' → 바로 '놀부의 박이 열렸다'. 제비 다리를
   부러뜨리고, 박씨를 받고, 심는 세 단계가 통째로 빠져 보는 사람이 "박씨를 어디서 났지?"
   하게 된다. 원인이 결과 바로 앞에 와야 한다.)
- 장소가 바뀌는 컷은 place 를 바꾸고, 그 전환이 자연스럽도록 앞뒤를 배치합니다.
- cast 는 위 등장인물 목록 안에서만 고릅니다. 한 컷에 세 명을 넘기지 않습니다.
"""


# ---------------------------------------------------------------- ③ 컷 본문

_SCENE_USER = """아래 줄거리와 컷 개요를 바탕으로, **{first}번부터 {last}번까지의 컷 본문**만 쓰세요.

제목: {title}
한 줄 줄거리: {logline}
등장인물: {cast_list}
타깃 영상 생성 툴: {tool}

전체 컷 개요(흐름 파악용, 이번에 쓸 것은 {first}~{last}번뿐):
{all_beats}

{prev_note}

아래 JSON 스키마로만 답하세요. scenes 는 정확히 {count}개, {first}번 컷부터 순서대로입니다.

{{
  "scenes": [
    {{
      "narration": "그 씬의 한국어 나레이션 대본",
      "voice_direction": "성우가 이 대목을 어떻게 읽어야 하는지 한국어 한 줄 연기 지시",
      "cast": ["그 씬 화면에 얼굴이 보이는 등장인물 이름"],
      "continuity": "앞 씬에서 무엇을 물려받아 다음 씬으로 무엇을 넘기는지 한국어 한 줄",
      "visual": "그 씬 화면을 한국어로 한 줄 요약(사용자 확인용)",
      "shot": "샷 크기 + 카메라 움직임 (영문, 예: medium shot, slow dolly-in)",
      "prompt": "영상 생성 AI에 넣을 영문 프롬프트",
      "negative": "네거티브 프롬프트(영문). 필요 없으면 빈 문자열"
    }}
  ]{hashtag_slot}
}}

[나레이션 규칙]
- 컷 개요에 적힌 그 컷의 일을 **그대로** 옮깁니다. 개요에 없는 사건을 새로 지어내지 않습니다.
- 전체를 이어 읽으면 하나의 완결된 이야기. 문장이 씬 경계에서 잘리지 않습니다.
- ⭐ 각 씬 나레이션은 한국어 **1~2문장, 32~45자**. 이보다 길면 씬 하나가 10초를 넘는데,
  영상 생성 툴 대부분이 10초까지만 만들어 주어 쓸 수 없는 대본이 된다.
- 따뜻하고 해학적인 구어체 존댓말("~했답니다", "~하지 뭐예요"). 옛이야기 들려주듯.
- ⭐ **한 문장에 사건 하나.** 두 문장이면 사건 둘까지. 한 문장에 사건을 셋 넣으면 숨이 찹니다.
  (나쁜 예: "박 속에서 음식과 비단 옷과 돈이 쏟아져 나와 모두 배불리 먹고 행복해졌지요."
   — 쏟아짐·먹음·행복해짐 셋이 한 문장에 들어갔습니다.)
- ⭐ **앞 씬과 같은 인물이면 이름을 다시 부르지 않습니다.** 한국어는 문맥이 이어지면 주어를
  생략합니다. 매 씬 이름을 부르면 낭독체가 딱딱해집니다.
  (나쁜 예: 4번 "흥부는~", 5번 "흥부네 가족은~" / 좋은 예: 4번 "흥부는~", 5번 "설레는 마음으로~")
  인물이 **바뀌는 씬에서만** 이름을 밝힙니다.
- ⭐ **종결어미를 연달아 겹치지 않습니다.** "~답니다 / ~었어요 / ~지 뭐예요 / ~더랍니다" 를
  번갈아 쓰되, **바로 앞 씬과 같은 어미는 쓰지 않습니다.** 마지막 씬은 "~답니다"로 닫습니다.
- ⭐ **씬 첫머리에 앞과 잇는 말**을 둡니다(그러자 / 그런데 / 며칠 뒤 / 그 말을 들은 /
  이윽고 / 하지만). 단 **같은 연결어를 두 번 쓰지 않습니다.**
- 숫자·영어 금지(음성으로 읽히므로). 한글과 기본 문장부호, 그리고 아래 연기 마커만.

[⭐ 연기 마커 — 나레이션 안에 직접 넣습니다]
- 감정이 바뀌는 자리에 아래 마커를 **대사 바로 앞에** 붙입니다. 성우가 그 지시대로 연기합니다.
  마커는 소리로 나가지 않고 자막에도 안 보입니다(시스템이 걷어냅니다).
- 쓸 수 있는 마커(이것만): {markers}
- 한 씬에 **1~2개**. 문장마다 붙이면 오히려 산만해집니다. 감정이 실제로 꺾이는 자리에만.
- 예: "[놀라며] 박을 타자 금은보화가 쏟아져 나왔지 뭐예요!"
- 예: "흥부는 제비를 품에 안았습니다. [속삭이며] 이제 괜찮단다."
- 마커를 뺀 글자 수가 위 32~45자 기준입니다.
{edge_note}

[연기 지시 규칙 — voice_direction]
- 성우에게 주는 지문. **감정 + 속도 + 힘**을 한 줄에 담는다. 그대로 TTS에 전달된다.
- 예: "들뜬 기대를 담아 조금 빠르게", "숨을 죽이고 낮게, 한 박자 느리게",
  "안타까움이 묻어나도록 살짝 떨리는 목소리로", "미소가 번지듯 부드럽고 느긋하게"
- 씬마다 달라야 한다. 전부 같은 톤이면 로봇처럼 들린다.
- 읽을 문장을 여기 옮겨 적지 않는다. 어떻게 읽을지만 쓴다.

[등장인물 규칙 — cast]
- 그 씬에 **얼굴이 보이는** 인물 이름만 적는다(위 등장인물 목록 안에서만).
- 목록에 없는 사람은 화면에 얼굴이 보이면 안 된다. 필요하면 뒷모습·실루엣·먼 군중으로.
- 한 씬에 세 명 넘게 넣지 않는다. 영상 AI가 인물을 뒤섞는다.

[씬 프롬프트 규칙 — scenes[].shot 과 scenes[].prompt]
- 툴 문법: {tool_guide}

- ⭐ **외모를 한 글자도 쓰지 않는다.** 운영자가 인물 기준 이미지를 영상 툴에 함께 넣는데,
  글로 또 적으면 두 지시가 싸워 컷마다 인물이 달라진다.
  · 쓰지 않을 것: 옷·한복·색·머리·얼굴·나이·키·체형을 가리키는 모든 낱말
  · 쓰지 않을 것: 옷을 만지는 동작(소매를 쥔다 등)
  · 인물은 이름으로만 부른다 (예: "Gildong walks along a mountain path")

- ⭐ **인물은 절대 말하지 않는다.** 나레이터가 들려주는 이야기라 인물이 입을 움직이면
  누가 말하는지 헷갈리고, 영상 AI가 지어낸 영어 입모양은 한국어 나레이션과도 어긋난다.
  · 대화·독백·외침·속삭임 같은 **발화 동작을 씬 내용으로 쓰지 않는다**
    (쓰지 않을 것: says, shouts, calls out, whispers, talks, argues, sings)
  · 감정은 몸짓·자세·눈빛·손으로만 드러낸다
  · 소리는 주변음만: "ambient wind and footsteps, soft traditional instrumental"
  · 입을 다물라는 문장은 시스템이 자동으로 붙이니 직접 적지 않아도 된다

- ⭐ **샷을 매번 다르게 한다.** shot 칸에 [샷 크기] + [카메라 움직임]을 적고 prompt 안에도 녹인다.
  · 샷 크기: wide establishing / medium / medium close-up / close-up / low-angle / high-angle /
    over-the-shoulder / extreme close-up on hands — **연속한 두 씬이 같은 크기면 안 된다.**
  · 카메라 움직임: slow dolly-in / dolly-out / pan left / crane up / handheld follow /
    rack focus / orbit — 씬마다 다른 것을 고른다. 정지 샷은 최대 1개까지만.
  · 각 씬 안에서 **무언가가 변한다**: 인물이 움직이거나, 빛이 바뀌거나, 카메라가 새 정보를
    드러낸다. 5~8초 동안 아무 일도 없는 고정 화면은 쓰지 않는다.

- 각 씬은 단일 연속 샷. 씬 안에서 컷 전환·여러 장소 금지.
- 장소·동작·카메라·빛만 적는다.
- 화면에 글자·자막·워터마크가 나오지 않게 할 것(텍스트 요소 요청 금지).
- "negative"는 {negative_note}
"""


# ---------------------------------------------------------------- ④ 윤문(다듬기)

_POLISH_USER = """아래는 한국 전래동화 쇼츠의 나레이션입니다. 컷마다 따로 쓰다 보니
**이어 읽으면 어색한 곳**이 있습니다. 내용은 그대로 두고 **말맛만** 다듬어 주세요.

제목: {title}
한 줄 줄거리: {logline}
등장인물: {cast_list}

현재 나레이션:
{numbered}

아래 JSON 스키마로만 답하세요. 개수는 정확히 {count}개, 순서 그대로입니다.

{{"narrations": ["1번 다듬은 문장", "2번 다듬은 문장", "..."]}}

[절대 바꾸지 말 것]
- **사건과 순서.** 없던 일을 넣거나 있던 일을 빼지 않습니다. 인물 이름도 그대로.
- 개수. {count}개를 {count}개로 돌려줍니다.

[다듬을 것 — 이어 읽었을 때 자연스럽게]
1. ⭐ **길이**: 연기 마커를 뺀 글자 수가 **32~45자**. 지금 넘치는 것은 줄입니다.
   줄일 때는 꾸밈말부터 덜어내고, 사건은 남깁니다.
2. ⭐ **한 문장에 사건 하나.** 셋이 들어간 문장은 둘로 나누거나 덜어냅니다.
3. ⭐ **주어 생략**: 앞 컷과 같은 인물이면 이름을 다시 부르지 않습니다. 인물이 바뀌는
   컷에서만 이름을 밝힙니다. 한국어는 문맥이 이어지면 주어를 생략합니다.
4. ⭐ **종결어미 리듬**: "~답니다 / ~었어요 / ~지 뭐예요 / ~더랍니다" 를 번갈아 쓰되
   **이웃한 두 컷이 같은 어미로 끝나지 않게** 합니다. 마지막 컷은 "~답니다"로 닫습니다.
5. ⭐ **연결어**: 컷 첫머리에 앞과 잇는 말을 둡니다(그러자 / 그런데 / 며칠 뒤 /
   그 말을 들은 / 이윽고 / 하지만). **같은 연결어를 두 번 쓰지 않습니다.**
6. ⭐ **1번은 훅**: "옛날 옛적에" 처럼 뻔하게 시작하지 않습니다. 사건 한가운데나
   의외의 장면에서 시작하거나, 답을 알고 싶게 만드는 한마디로 엽니다.
7. **연기 마커**({markers})는 감정이 꺾이는 컷에만 1~2개 남기고, 너무 많으면 덜어냅니다.
   마커는 대사 바로 앞에 붙입니다.
8. 숫자·영어 금지. 한글과 기본 문장부호, 마커만.
"""


@dataclass
class Character:
    name: str
    role: str = ""
    image_prompt: str = ""


@dataclass
class Scene:
    narration: str
    visual: str
    prompt: str
    shot: str = ""
    negative: str = ""
    est_seconds: float = 0.0
    voice_direction: str = ""
    continuity: str = ""
    act: str = ""
    cast: list[str] = field(default_factory=list)


@dataclass
class Storyboard:
    title: str
    scenes: list[Scene]
    hashtags: list[str]
    characters: list[Character] = field(default_factory=list)
    style_lock: str = ""
    logline: str = ""
    cover_prompt: str = ""


# 참조 이미지를 쓸 때 씬 프롬프트에 섞이면 안 되는 낱말.
# 이게 들어가면 이미지와 글이 싸워 컷마다 인물이 달라진다.
# (verdict-theater 의 wear_bait 규칙을 이식)
_LOOK_WORDS = re.compile(
    r"\b(hanbok|robe|dress|outfit|costume|clothes|clothing|sleeve|collar|"
    r"hair|haircut|hairstyle|beard|face|facial|eyes|skin|"
    r"young|old|teenage|boy|girl|man|woman|child|elderly|"
    r"tall|short|slim|thin|plump|wearing|wears|dressed|clad)\b",
    re.I,
)


# 발화 동작이 씬 내용에 들어가면 입 다물라는 지시와 싸운다.
_TALK_WORDS = re.compile(
    r"\b(say|says|said|speak|speaks|speaking|shout|shouts|shouting|yell|yells|"
    r"call out|calls out|whisper|whispers|talk|talks|talking|argue|argues|"
    r"sing|sings|singing|cry out|announce|announces|dialogue|conversation)\b",
    re.I,
)


def talk_words(prompt: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _TALK_WORDS.finditer(prompt)})


def strip_look_words(prompt: str) -> tuple[str, list[str]]:
    """외모 낱말이 남아 있으면 찾아서 돌려준다(지우지는 않는다 — 문장이 깨지므로)."""
    hits = sorted({m.group(0).lower() for m in _LOOK_WORDS.finditer(prompt)})
    return prompt, hits


def _ask(client, model: str, prompt: str, temperature: float) -> dict:
    from google.genai import types
    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    text = (resp.text or "").strip()
    if not text:
        raise RuntimeError("대본 생성 결과가 비었습니다. 주제를 조금 더 구체적으로 적어 보세요.")
    return json.loads(text)


def _one_line(v) -> str:
    return " ".join(str(v or "").split())


def _polish(client, model: str, title: str, logline: str, cast_list: str,
            narrations: list[str]) -> list[str]:
    """컷마다 따로 쓴 나레이션을 **한꺼번에 놓고** 다듬는다.

    컷을 여덟 개씩 나눠 쓰다 보면 묶음 경계에서 말맛이 끊기고, 종결어미가 겹치고,
    같은 인물 이름을 매 컷 되부른다. 전체를 한 화면에 놓고 봐야 잡힌다.
    사건을 건드리면 이야기가 망가지므로, **말맛만** 고치게 하고 결과를 검사한다.
    """
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(narrations, 1))
    try:
        data = _ask(client, model, _POLISH_USER.format(
            title=title, logline=logline, cast_list=cast_list,
            numbered=numbered, count=len(narrations),
            markers=" ".join(MARKERS),
        ), temperature=0.7)
        got = [_one_line(x) for x in (data.get("narrations") or [])]
    except Exception as e:  # noqa: BLE001
        print(f"::warning::나레이션 다듬기를 건너뜁니다({str(e)[:120]}).")
        return narrations

    if len(got) != len(narrations):
        print(f"::warning::다듬기 결과가 {len(got)}개로 와서 원본을 씁니다"
              f"(요청 {len(narrations)}개).")
        return narrations

    # 한 줄씩 검사 — 이상한 것만 원본으로 되돌린다(통째로 버리지 않는다).
    out = []
    for i, (old, new) in enumerate(zip(narrations, got), 1):
        plain = strip_markers(new)
        if not plain or len(plain) > 60 or len(plain) < 12:
            print(f"::warning::{i}번 다듬기 결과가 {len(plain)}자라 원본을 씁니다.")
            out.append(old)
        else:
            out.append(new)
    return out


def _check_flow(narrations: list[str], names: list[str]) -> None:
    """다듬은 뒤에도 남은 어색함을 알려 준다(고치지는 않는다)."""
    plains = [strip_markers(t) for t in narrations]
    for i, t in enumerate(plains, 1):
        if len(t) > 48:
            print(f"::warning::{i}번 나레이션이 {len(t)}자입니다(45자 권장). 씬이 길어집니다.")
    ends = [re.sub(r"[.!?…]+$", "", t)[-4:] for t in plains]
    for i in range(1, len(ends)):
        if ends[i] and ends[i] == ends[i - 1]:
            print(f"::warning::{i}번과 {i + 1}번 나레이션이 같은 말로 끝납니다('{ends[i]}').")
    for nm in names:
        c = sum(t.count(nm) for t in plains)
        if c > max(3, len(plains) // 2):
            print(f"::warning::'{nm}' 이 {c}번 반복됩니다. 주어를 더 생략하면 자연스럽습니다.")


def generate_storyboard(api_key: str, topic: str, n_scenes: int, tool: str,
                        model: str = "") -> Storyboard:
    """주제 → 스토리보드. 세 단계로 나눠 만든다.

    ① 줄거리와 인물(발단·전개·위기·절정·결말) → ② 컷마다 무슨 일이 벌어지는지 한 줄씩
    → ③ 그 개요를 {SCENES_PER_CALL}개씩 묶어 본문(나레이션·프롬프트) 작성.
    한 번에 다 시키면 모델이 앞뒤를 안 보고 컷을 지어내어 이야기가 끊기고,
    컷이 많을수록 뒤쪽이 통째로 부실해진다.
    """
    from google import genai

    cfg = TOOLS[tool]
    client = genai.Client(api_key=api_key)
    model = resolve_model(client, model)
    # 대목이 다섯이라 컷도 최소 다섯이어야 한 대목이 통째로 비지 않는다.
    n_scenes = max(len(ACTS), min(MAX_SCENES, int(n_scenes)))
    alloc = allocate_acts(n_scenes)

    # ① 줄거리와 인물
    print(f"[1/4] 줄거리 설계 — {n_scenes}컷, 대목별 배정 "
          f"{', '.join(f'{s}{c}' for (s, _), c in zip(ACTS, alloc))}")
    plot = _ask(client, model, _PLOT_USER.format(
        topic=topic, n_scenes=n_scenes, style=STYLE_KEYWORDS, max_chars=MAX_CHARACTERS,
        total_sec=int(n_scenes * 8),
        allocation=", ".join(f"{s} {c}컷" for (s, _), c in zip(ACTS, alloc)),
    ), temperature=0.9)

    characters = [
        Character(name=_one_line(c.get("name")),
                  role=_one_line(c.get("role")),
                  image_prompt=_one_line(c.get("image_prompt")))
        for c in (plot.get("characters") or [])
        if _one_line(c.get("name"))
    ][:MAX_CHARACTERS]
    if not characters:
        raise RuntimeError("등장인물을 만들지 못했습니다. 주제를 조금 더 구체적으로 적어 보세요.")

    # 색감 문장은 AI가 씬마다 새로 쓰게 두지 않고, 한 문장을 **그대로 복사**해 붙인다.
    # 매번 새로 쓰게 하면 표현이 조금씩 달라지고, 영상 AI는 그걸 다른 색으로 그린다.
    style_lock = _one_line(plot.get("style_lock"))
    cover_prompt = _one_line(plot.get("cover_prompt"))
    if cover_prompt and style_lock and style_lock.lower() not in cover_prompt.lower():
        cover_prompt = f"{cover_prompt} {style_lock}"
    if cover_prompt:
        # 글자 금지는 모델이 빠뜨리기 쉬워서 시스템이 못 박는다.
        cover_prompt = (f"{cover_prompt} Vertical 9:16 poster composition, "
                        "no text, no letters, no title, no watermark, no logo.")
    title = _one_line(plot.get("title")) or topic
    logline = _one_line(plot.get("logline"))
    cast_list = ", ".join(f"{c.name}({c.role})" for c in characters)

    by_stage = {_one_line(a.get("stage")): _one_line(a.get("summary"))
                for a in (plot.get("acts") or [])}
    acts_text = "\n".join(
        f"  [{stage}] {count}컷 — {by_stage.get(stage, '(비어 있음)')}"
        for (stage, _), count in zip(ACTS, alloc)
    )

    # ② 컷마다 무슨 일이 벌어지는지 한 줄씩
    print(f"[2/4] {n_scenes}컷 개요")
    beats_raw = (_ask(client, model, _BEATS_USER.format(
        n_scenes=n_scenes, title=title, logline=logline,
        cast_list=cast_list, acts=acts_text,
    ), temperature=0.85).get("beats") or [])[:n_scenes]
    if len(beats_raw) < n_scenes:
        raise RuntimeError(f"컷 개요를 {n_scenes}개 만들지 못했습니다"
                           f"(받은 개수: {len(beats_raw)}). 다시 시도해 보세요.")

    # 대목 이름은 우리가 정한 배정에서 가져온다(모델이 틀리게 적어도 흔들리지 않게).
    stage_of: list[str] = []
    for (stage, _), count in zip(ACTS, alloc):
        stage_of += [stage] * count
    beats = []
    for i, b in enumerate(beats_raw):
        beats.append({
            "n": i + 1,
            "act": stage_of[i] if i < len(stage_of) else "",
            "summary": _one_line(b.get("summary")),
            "place": _one_line(b.get("place")),
        })
    all_beats = "\n".join(
        f"  {b['n']}. [{b['act']}] ({b['place']}) {b['summary']}" for b in beats
    )

    # ③ 본문을 SCENES_PER_CALL 개씩 나눠 작성
    known = {c.name for c in characters}
    scenes: list[Scene] = []
    hashtags: list[str] = []
    batches = [(i, min(i + SCENES_PER_CALL, n_scenes))
               for i in range(0, n_scenes, SCENES_PER_CALL)]
    for bi, (lo, hi) in enumerate(batches):
        print(f"[3/4] 본문 {lo + 1}~{hi}번 컷 ({bi + 1}/{len(batches)})")
        prev_note = ""
        if scenes:
            prev = scenes[-1]
            prev_note = ("[바로 앞 컷에서 이어집니다]\n"
                         f"  {lo}번 나레이션: {prev.narration}\n"
                         f"  {lo}번 화면: {prev.visual}\n"
                         "  이 상태에서 자연스럽게 이어 시작하세요.")
        data = _ask(client, model, _SCENE_USER.format(
            first=lo + 1, last=hi, count=hi - lo,
            title=title, logline=logline, cast_list=cast_list, tool=tool,
            all_beats=all_beats, prev_note=prev_note,
            tool_guide=cfg["guide"],
            # 해시태그는 마지막 묶음에서 한 번만 받는다.
            hashtag_slot=(',\n  "hashtags": ["#해시태그", "#3개", "#한국어"]'
                          if bi == len(batches) - 1 else ""),
            edge_note=("- ⭐ 1번 씬은 **훅**입니다. \"옛날 옛적에\" 처럼 뻔하게 시작하지 마세요 —\n"
                       "  쇼츠에서 손가락이 그냥 지나갑니다. 사건 한가운데나 의외의 장면에서 시작하거나,\n"
                       "  듣는 사람이 답을 알고 싶게 만드는 한마디로 엽니다.\n"
                       "  (나쁜 예: \"옛날 옛적에 마음씨 착한 흥부가 살았답니다.\"\n"
                       "   좋은 예: \"부러진 제비 다리 하나가 한 집안의 운명을 바꿔 놓았지 뭐예요.\")"
                       if bi == 0 else "")
            + ("\n- 마지막 씬은 잔잔한 교훈이나 여운으로 마무리. 설교조 금지."
               if bi == len(batches) - 1 else ""),
            markers=" ".join(MARKERS),
            negative_note=("이 툴이 네거티브 프롬프트를 지원하므로 반드시 채울 것"
                           if cfg["negative"] else "빈 문자열로 둘 것"),
        ), temperature=0.85)
        if bi == len(batches) - 1:
            hashtags = [str(h) for h in (data.get("hashtags") or [])][:5]

        got = (data.get("scenes") or [])[:hi - lo]
        if not got:
            raise RuntimeError(f"{lo + 1}~{hi}번 컷 본문이 비었습니다. 다시 시도해 보세요.")
        for j, s in enumerate(got):
            body = _one_line(s.get("prompt"))
            if style_lock and style_lock.lower() not in body.lower():
                body = f"{body} {style_lock}"
            body = f"{body} {SILENCE_LOCK} __DUR__"   # 입 다무는 문장은 예외 없이 붙인다
            # 길이 문장(__DUR__)은 나중에 채운다 — 윤문 단계에서 나레이션 길이가 바뀐다.
            narration = _one_line(s.get("narration"))
            est = estimate_seconds(narration)
            neg = _one_line(s.get("negative"))
            if cfg["negative"]:
                neg = f"{neg}, {SILENCE_NEGATIVE}".strip(" ,")
            idx = lo + j
            scenes.append(Scene(
                narration=narration,
                visual=str(s.get("visual", "")).strip(),
                shot=_one_line(s.get("shot")),
                prompt=(body + cfg["suffix"]).strip(),
                negative=neg,
                est_seconds=est,
                voice_direction=_one_line(s.get("voice_direction")),
                continuity=_one_line(s.get("continuity")),
                act=beats[idx]["act"] if idx < len(beats) else "",
                cast=[n for n in (_one_line(c) for c in (s.get("cast") or []))
                      if n in known],
            ))

    # ④ 전체를 한꺼번에 놓고 말맛을 다듬는다. 컷마다 따로 쓰면 이어 읽을 때 어색하다.
    print(f"[4/4] 나레이션 다듬기 ({len(scenes)}컷 한꺼번에)")
    polished = _polish(client, model, title, logline, cast_list,
                       [sc.narration for sc in scenes])
    for sc, new_n in zip(scenes, polished):
        sc.narration = new_n
        sc.est_seconds = estimate_seconds(new_n)
        sc.prompt = sc.prompt.replace(
            "__DUR__", f"Single continuous shot of about {sc.est_seconds:.0f} seconds.")
    _check_flow([sc.narration for sc in scenes], [c.name for c in characters])

    if len(scenes) != n_scenes:
        print(f"::warning::컷을 {n_scenes}개 요청했는데 {len(scenes)}개가 만들어졌습니다.")
    if not scenes:
        raise RuntimeError("대본 생성 결과가 비었습니다. 주제를 조금 더 구체적으로 적어 보세요.")

    board = Storyboard(
        title=title,
        scenes=scenes,
        hashtags=hashtags,
        characters=characters,
        style_lock=style_lock,
        logline=logline,
        cover_prompt=cover_prompt,
    )

    # 기준 이미지가 있는데 한 번도 안 쓰이는 인물이 있으면 운영자가 헛일을 한다.
    used = {n for s in scenes for n in s.cast}
    for c in characters:
        if c.name not in used:
            print(f"::warning::등장인물 '{c.name}'이 어느 씬에도 배정되지 않았습니다. "
                  "기준 이미지를 만들 필요가 없을 수 있습니다.")

    for i, s in enumerate(board.scenes, 1):
        _, hits = strip_look_words(s.prompt)
        if hits:
            print(f"::warning::{i}번 씬 프롬프트에 외모 낱말이 남았습니다({', '.join(hits)}). "
                  "참조 이미지와 충돌해 인물이 달라질 수 있습니다.")
        talks = talk_words(s.prompt)
        if talks:
            print(f"::warning::{i}번 씬 프롬프트에 발화 동작이 있습니다({', '.join(talks)}). "
                  "인물이 입을 움직일 수 있습니다.")
        if s.est_seconds > 10:
            print(f"::warning::{i}번 씬이 약 {s.est_seconds:.0f}초입니다. 영상 툴 대부분이 "
                  "10초까지라 대본을 줄이는 편이 좋습니다.")
    return board
