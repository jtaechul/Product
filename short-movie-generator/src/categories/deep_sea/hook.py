"""deep_sea 오프닝 훅/엔드카드용 일본어 카피 생성.

hook_intro 시스템(오프닝 대형 타이틀·엔드카드)에 넣을 **일본어** 문구를 만든다.
- 국명(카타카나)·2줄 훅(종명 미노출·신비형)·팝 어절·특징문구.
- 우선순위: ① 큐레이션 시드(대표종) ② LLM(Claude/Gemini) ③ 실패 시 None(시스템 휴면·발행 불정지).

학명 표기 규칙(하드룰): 속명 첫 글자 대문자·이탤릭은 렌더 단계에서 강제(여기선 원문 유지).
"""
from __future__ import annotations

import json
import logging
import re

from src.core import llm
from src.core.contracts import SpeciesInfo

log = logging.getLogger(__name__)

# 대표종 큐레이션 시드(LLM 키 없어도 확정 품질 보장)
_SEED = {
    "enypniastes eximia": {
        "jp_name": "ユメナマコ",
        "hook_line1": "頭も、目も、",
        "hook_line2": "骨もない。",
        "pop_words": ["頭も、", "目も、", "骨もない。"],
        "feature_line": "泳ぐ・光る・透ける、深海のナマコ",
        "feature_glow_word": "光る",
    },
}

_PROMPT = """あなたは日本語のショート動画コピーライターです。深海生物の\
オープニングフック(タイトル)と特徴文を作ります。次の生物の情報から、\
JSONのみを出力してください(前後の説明・コードブロック禁止)。

生物: 英名={en} / 学名={sci} / 生息水深={depth}m / 生息域={hab}
特徴メモ: {facts}

要件:
- jp_name: この生物の日本語通称(カタカナ中心、なければ学名のカタカナ表記)
- hook_line1 / hook_line2: 2行の短いフック。神秘的・意外性。**種名は出さない**。合計12文字前後、\
各行は名詞や短文で読点で区切る(例: 「頭も、目も、」「骨もない。」)
- pop_words: hook_line1+hook_line2を読点/句点で自然に区切った配列(3要素前後)
- feature_line: 「A・B・C、〜」形式の短い特徴文(例: 「泳ぐ・光る・透ける、深海のナマコ」)
- feature_glow_word: feature_line内で光・発光に関わる語(なければ最初の語)

JSON例: {{"jp_name":"...","hook_line1":"...","hook_line2":"...","pop_words":["...","...","..."],"feature_line":"...","feature_glow_word":"..."}}
"""


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    need = {"jp_name", "hook_line1", "hook_line2", "pop_words", "feature_line"}
    if not need.issubset(d) or not isinstance(d.get("pop_words"), list) or len(d["pop_words"]) < 2:
        return None
    d.setdefault("feature_glow_word", d["pop_words"][0])
    return d


def build_hook(info: SpeciesInfo) -> dict | None:
    """일본어 훅 카피 dict 반환. 실패 시 None(시스템 휴면)."""
    key = (info.scientific_name or "").strip().lower()
    if key in _SEED:
        return _SEED[key]
    facts = " / ".join((info.fun_facts or [])[:3]) or "-"
    prompt = _PROMPT.format(en=info.common_name_en, sci=info.scientific_name,
                            depth=info.depth_range_m, hab=info.habitat, facts=facts)
    try:
        out = llm.generate_text(prompt, max_tokens=400)
    except Exception as e:  # noqa: BLE001
        log.warning("[deep_sea.hook] LLM 호출 실패: %s", e)
        out = None
    parsed = _parse_json(out or "")
    if not parsed:
        log.info("[deep_sea.hook] 훅 생성 불가(키 없음/파싱 실패) → 오프닝/엔드카드 생략")
    return parsed
