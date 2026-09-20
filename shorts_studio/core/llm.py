"""llm — 동화 대본 + 타깃 영상 AI 툴에 맞춘 영문 프롬프트 생성 (Gemini).

두 단계로 만든다.
  ① 줄거리 먼저 — 발단·전개·위기·결말과 등장인물을 통째로 설계한다.
  ② 그 줄거리를 씬으로 쪼갠다 — 각 씬이 앞 씬에서 무엇을 물려받아 다음으로 무엇을
     넘기는지 명시하게 해, 컷이 따로 노는 것을 막는다.
한 번에 시키면 모델이 앞뒤를 안 보고 씬을 하나씩 지어내어 이야기가 끊긴다.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .tts import estimate_seconds

MODELS = ["gemini-2.5-flash", "gemini-2.5-pro"]

# 기준 이미지를 만들 인물 수 상한. 늘릴수록 운영자가 만들어야 할 이미지가 늘어난다.
MAX_CHARACTERS = 3

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


# ---------------------------------------------------------------- ① 줄거리

_PLOT_USER = """주제: {topic}
이 이야기는 {n_scenes}개의 컷으로 만들 세로 쇼츠입니다. 먼저 **줄거리와 등장인물**만 설계하세요.

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
  "beats": [
    {{"stage": "발단|전개|위기|절정|결말", "summary": "그 대목에서 실제로 벌어지는 일 (한국어 1~2문장)"}}
  ]
}}

[줄거리 규칙 — beats]
- **인과로 이어질 것.** 각 대목은 앞 대목 때문에 벌어져야 한다. "그리고"가 아니라 "그래서".
- 발단에서 **인물이 무엇을 원하는지**, 위기에서 **그것을 가로막는 것이 무엇인지**를 분명히 한다.
- 결말은 앞에서 깔아 둔 것으로 풀어낸다. 갑자기 등장하는 해결사·우연 금지.
- 5개 대목 모두 채운다. 각 대목은 뒤에서 {n_scenes}개 컷으로 쪼개질 분량이다.

[등장인물 규칙 — characters]
- **최대 {max_chars}명.** 주인공 1명은 반드시 넣고, 이야기에 꼭 필요한 인물만 더한다.
  기준 이미지를 한 장씩 만들어야 하므로 많을수록 운영자 일이 늘어난다.
- 여기 없는 사람은 뒷모습·실루엣·멀리 있는 군중으로만 나온다. 얼굴이 보이는 인물은 여기 적는다.
- image_prompt: 정면 전신, 중립 표정, 평범하게 선 자세, 배경은 단순한 단색.
  나이·체형·머리 모양·한복 색과 무늬·신발까지 **구체적으로** 적는다.
  이 한 장이 모든 씬의 기준이 되므로 **외모는 오직 여기서만** 정한다.
  인물끼리 한눈에 구별되게 색과 실루엣을 다르게 준다.
  스타일 키워드를 포함할 것: {style}

[색감 고정 문장 규칙 — style_lock]
- 색·빛·질감을 못 박는 영문 **1문장**. 이 문장이 모든 씬 끝에 **글자 그대로** 붙는다.
- 반드시 담을 것: 색 팔레트(구체적인 색 3~4개), 광원의 성질, 시간대 느낌, 렌더링 질감.
- 예: "Consistent warm palette of ochre, deep indigo and pale jade under soft diffused
  late-afternoon light, gentle film grain, matte 3D storybook render."
- 장면마다 달라질 내용(장소·날씨·감정)은 여기 쓰지 않는다. 씬이 바뀌어도 **똑같아야** 한다.
"""


# ---------------------------------------------------------------- ② 씬 쪼개기

_SCENE_USER = """아래는 이미 확정된 줄거리입니다. 이것을 정확히 {n_scenes}개의 컷으로 쪼개세요.

제목: {title}
한 줄 줄거리: {logline}
등장인물: {cast_list}
대목:
{beats}

타깃 영상 생성 툴: {tool}

아래 JSON 스키마로만 답하세요.

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
  ],
  "hashtags": ["#해시태그", "#3개", "#한국어"]
}}

[이야기 연결 규칙 — 가장 중요]
- 정확히 {n_scenes}개. 위 대목을 순서대로 덮되, 분량이 많은 대목은 여러 컷으로 나눈다.
- ⭐ **컷마다 이야기가 한 칸씩 나아간다.** 같은 상황을 각도만 바꿔 두 번 보여 주지 않는다.
- ⭐ **앞 씬의 마지막 상태에서 이어 시작한다.** 인물의 위치·손에 든 것·시간대·감정이
  앞 씬 끝과 맞아야 한다. continuity 칸에 그 연결고리를 적고, 프롬프트도 거기 맞춘다.
- 장소가 바뀌면 나레이션에서 먼저 옮겨 준다("다음 날 아침, 마을 어귀에서는…").
  화면만 갑자기 다른 곳으로 뛰지 않는다.
- 마지막 씬은 앞에서 깔아 둔 것을 거둬들여 닫는다.

[나레이션 규칙]
- 전체를 이어 읽으면 하나의 완결된 이야기. 문장이 씬 경계에서 잘리지 않는다.
- ⭐ 각 씬 나레이션은 한국어 **1~2문장, 32~45자**. 이보다 길면 씬 하나가 10초를 넘는데,
  영상 생성 툴 대부분이 10초까지만 만들어 주어 쓸 수 없는 대본이 된다.
- 따뜻하고 해학적인 구어체 존댓말("~했답니다", "~하지 뭐예요"). 옛이야기 들려주듯.
- 1번 씬 첫 문장은 훅: 궁금증을 만들고 끝까지 보게 만들 것.
- 마지막 씬은 잔잔한 교훈이나 여운으로 마무리. 설교조 금지.
- 숫자·영어·특수문자 금지(음성으로 읽히므로). 한글과 기본 문장부호만.

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
    cast: list[str] = field(default_factory=list)


@dataclass
class Storyboard:
    title: str
    scenes: list[Scene]
    hashtags: list[str]
    characters: list[Character] = field(default_factory=list)
    style_lock: str = ""
    logline: str = ""


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


def generate_storyboard(api_key: str, topic: str, n_scenes: int, tool: str,
                        model: str = "gemini-2.5-flash") -> Storyboard:
    from google import genai

    cfg = TOOLS[tool]
    client = genai.Client(api_key=api_key)

    # ① 줄거리와 인물 먼저
    plot = _ask(client, model, _PLOT_USER.format(
        topic=topic, n_scenes=n_scenes, style=STYLE_KEYWORDS, max_chars=MAX_CHARACTERS,
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
    title = _one_line(plot.get("title")) or topic
    logline = _one_line(plot.get("logline"))
    beats = "\n".join(
        f"  - [{_one_line(b.get('stage'))}] {_one_line(b.get('summary'))}"
        for b in (plot.get("beats") or [])
    ) or "  - (대목 없음)"

    # ② 그 줄거리를 씬으로
    data = _ask(client, model, _SCENE_USER.format(
        n_scenes=n_scenes, title=title, logline=logline, beats=beats, tool=tool,
        cast_list=", ".join(f"{c.name}({c.role})" for c in characters),
        tool_guide=cfg["guide"],
        negative_note=("이 툴이 네거티브 프롬프트를 지원하므로 반드시 채울 것"
                       if cfg["negative"] else "빈 문자열로 둘 것"),
    ), temperature=0.85)

    known = {c.name for c in characters}
    scenes = []
    for s in (data.get("scenes") or [])[:n_scenes]:
        body = _one_line(s.get("prompt"))
        if style_lock and style_lock.lower() not in body.lower():
            body = f"{body} {style_lock}"
        body = f"{body} {SILENCE_LOCK}"          # 입 다무는 문장은 예외 없이 붙인다
        # 몇 초짜리로 만들어야 하는지 프롬프트에도 박아 둔다. 영상이 짧으면 마지막
        # 프레임이 얼어붙고, 길면 잘려 나간다.
        narration = _one_line(s.get("narration"))
        est = estimate_seconds(narration)
        body = f"{body} Single continuous shot of about {est:.0f} seconds."
        neg = _one_line(s.get("negative"))
        if cfg["negative"]:
            neg = f"{neg}, {SILENCE_NEGATIVE}".strip(" ,")
        scenes.append(Scene(
            narration=narration,
            visual=str(s.get("visual", "")).strip(),
            shot=_one_line(s.get("shot")),
            prompt=(body + cfg["suffix"]).strip(),
            negative=neg,
            est_seconds=est,
            voice_direction=_one_line(s.get("voice_direction")),
            continuity=_one_line(s.get("continuity")),
            cast=[n for n in (_one_line(c) for c in (s.get("cast") or [])) if n in known],
        ))
    if not scenes:
        raise RuntimeError("대본 생성 결과가 비었습니다. 주제를 조금 더 구체적으로 적어 보세요.")

    board = Storyboard(
        title=title,
        scenes=scenes,
        hashtags=[str(h) for h in (data.get("hashtags") or [])][:5],
        characters=characters,
        style_lock=style_lock,
        logline=logline,
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
