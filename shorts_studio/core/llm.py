"""llm — 동화 대본 + 타깃 영상 AI 툴에 맞춘 영문 프롬프트 생성 (OpenAI)."""
from __future__ import annotations

import json
from dataclasses import dataclass

MODELS = ["gpt-4o", "gpt-4o-mini", "gpt-4.1"]

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

_USER = """주제: {topic}
컷(씬) 수: {n_scenes}
타깃 영상 생성 툴: {tool}

아래 JSON 스키마로만 답하세요.

{{
  "title": "쇼츠 제목 (한국어, 18자 이내, 호기심을 자극)",
  "scenes": [
    {{
      "narration": "그 씬의 한국어 나레이션 대본",
      "visual": "그 씬 화면을 한국어로 한 줄 요약(사용자 확인용)",
      "prompt": "영상 생성 AI에 넣을 영문 프롬프트",
      "negative": "네거티브 프롬프트(영문). 필요 없으면 빈 문자열"
    }}
  ],
  "hashtags": ["#해시태그", "#3개", "#한국어"]
}}

[나레이션 규칙]
- 정확히 {n_scenes}개의 씬. 전체를 이어 읽으면 하나의 완결된 이야기.
- 각 씬 나레이션은 한국어 2~3문장, 45~70자. 전체 합계 35~55초 분량.
- 따뜻하고 해학적인 구어체 존댓말("~했답니다", "~하지 뭐예요"). 옛이야기 들려주듯.
- 1번 씬 첫 문장은 훅: 궁금증을 만들고 끝까지 보게 만들 것.
- 마지막 씬은 잔잔한 교훈이나 여운으로 마무리. 설교조 금지.
- 숫자·영어·특수문자 금지(음성으로 읽히므로). 한글과 기본 문장부호만.

[영문 프롬프트 규칙]
- 툴 문법: {tool_guide}
- 모든 프롬프트에 다음 스타일 키워드를 자연스럽게 녹여 넣을 것: {style}
- 각 씬은 5~8초 분량의 단일 연속 샷. 컷 전환·여러 장면 금지.
- 화면에 글자·자막·워터마크가 나오지 않게 할 것(텍스트 요소 요청 금지).
- 씬 간 등장인물의 생김새·의상·나이를 동일하게 유지하도록 매 프롬프트에 인물 묘사를 반복할 것.
- "negative"는 {negative_note}
"""


@dataclass
class Scene:
    narration: str
    visual: str
    prompt: str
    negative: str = ""


@dataclass
class Storyboard:
    title: str
    scenes: list[Scene]
    hashtags: list[str]


def generate_storyboard(api_key: str, topic: str, n_scenes: int, tool: str,
                        model: str = "gpt-4o") -> Storyboard:
    from openai import OpenAI

    cfg = TOOLS[tool]
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        temperature=0.85,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _USER.format(
                topic=topic, n_scenes=n_scenes, tool=tool,
                tool_guide=cfg["guide"], style=STYLE_KEYWORDS,
                negative_note=("이 툴이 네거티브 프롬프트를 지원하므로 반드시 채울 것"
                               if cfg["negative"] else "빈 문자열로 둘 것"),
            )},
        ],
    )
    data = json.loads(resp.choices[0].message.content)

    scenes = []
    for s in (data.get("scenes") or [])[:n_scenes]:
        prompt = " ".join(str(s.get("prompt", "")).split()) + cfg["suffix"]
        scenes.append(Scene(
            narration=" ".join(str(s.get("narration", "")).split()),
            visual=str(s.get("visual", "")).strip(),
            prompt=prompt.strip(),
            negative=" ".join(str(s.get("negative", "")).split()),
        ))
    if not scenes:
        raise RuntimeError("대본 생성 결과가 비었습니다. 주제를 조금 더 구체적으로 적어 보세요.")

    return Storyboard(
        title=str(data.get("title") or topic).strip(),
        scenes=scenes,
        hashtags=[str(h) for h in (data.get("hashtags") or [])][:5],
    )
