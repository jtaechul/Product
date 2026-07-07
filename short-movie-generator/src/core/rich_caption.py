"""rich_caption — 발행용 리치 캡션 생성(전 카테고리 공용).

목표: 캡션이 짧고 심심하지 않게, **검증된 과학적 사실 2~3개를 이야기처럼 엮은** 풍부한
일본어 캡션 + 한국어 완역을 만든다. LLM(Claude/Gemini) 우선, 실패 시 사실 기반 리치 템플릿.

원칙(하드룰): 사실만. 없는 행동·수치·발광·포식 날조 금지. CC-BY 등 크레딧 필수.
반환: {jp, ko, tags, tags_ko}. jp=발행 캡션(일본어), ko=참고 완역(한국어, 일본어 잔류 금지).
"""
from __future__ import annotations

import json
import logging
import re

from src.core import llm
from src.core.contracts import SpeciesInfo

log = logging.getLogger(__name__)

_PROMPT = """あなたは日本のSNS(インスタ/リール)向けの、海洋生物ショート動画の\
プロのキャプションライターです。次の情報から、**内容豊かで物語性のある**キャプションを作ります。\
JSONのみ出力(説明・コードブロック禁止)。

対象: 和名={jp} / 学名={sci} / 生息水深={depth}m / 生息域={hab} / 分布={dist}
確かな事実(この範囲の事実のみ使用・**捏造禁止**):
{facts}

要件:
- jp_caption: 日本語。**6〜9行**でしっかりした分量。構成:
  1行目=共感か驚きのフック(種名は出さない)。
  2〜5行=上の事実から**2〜3個**を選び、単なる列挙でなく**自然な物語の流れ**でつなぐ\
(擬人化しすぎず、事実に忠実に、しかし情感を込めて)。生息環境(水深・分布)も一言添える。
  終盤=「心に残ったら保存を」の主旨1行 +「同じ海が気になる人へシェアを」の主旨1行。
  最終行=「映像: {credit}」。
- ko_caption: jp_caption の**完全な韓国語訳**(日本語を一切残さない、自然な韓国語)。
- hashtags: 日本語ハッシュタグ**ちょうど3個**(例: ["#深海","#生き物","#{jp}"])。
- ko_hashtags: hashtags の韓国語訳3個。

JSON例: {{"jp_caption":"...","ko_caption":"...","hashtags":["#..","#..","#.."],"ko_hashtags":["#..","#..","#.."]}}
"""

_KO_TAG = {"#深海": "#심해", "#生き物": "#생물", "#海": "#바다", "#タコ": "#문어",
           "#イカ": "#오징어", "#クラゲ": "#해파리", "#サンゴ礁": "#산호초",
           "#プランクトン": "#플랑크톤", "#沈没船": "#난파선", "#海の生き物": "#해양생물"}


def _ko_tags(tags: list[str], jp_name: str, ko_name: str) -> list[str]:
    out = []
    for t in tags:
        if t in _KO_TAG:
            out.append(_KO_TAG[t])
        elif jp_name and jp_name in t:
            out.append(f"#{ko_name}")
        else:
            out.append(t)
    return out


def _fallback(info: SpeciesInfo, jp_name: str, feature_line: str, hook_line1: str,
              hook_line2: str, hook_ko: str, feature_ko: str, credit: str,
              default_tags: list[str], default_tags_ko: list[str] | None = None) -> dict:
    """LLM 실패 시 리치 템플릿. 한국어는 실제 fun_facts를 엮어 풍부하게(일본어 잔류 금지).
    일본어는 보유한 일본어 요소(훅·특징·수심)로 구성(사실 왜곡 없이)."""
    ko_name = info.common_name_ko or jp_name
    facts_ko = [f for f in (info.fun_facts or []) if f][:3]
    # 한국어 캡션 — fun_facts를 문장으로 엮음
    ko_story = "\n".join(f"· {f}." if not f.endswith(("다", ".", "요")) else f"· {f}"
                         for f in facts_ko)
    ko = (f"{hook_ko or (ko_name + '의 이야기.')}\n\n"
          f"{feature_ko or ('바다에 사는 ' + ko_name)}.\n"
          f"{ko_story}\n\n"
          f"수심 {info.depth_range_m}m · {info.distribution}\n\n"
          f"마음에 남았다면 저장해 두세요.\n같은 바다가 궁금한 사람에게 공유해 주세요.\n\n"
          f"영상: {credit}")
    # 일본어 캡션 — 보유 일본어 요소로만 구성(수심·특징). 분포는 한국어 데이터라 JP엔 넣지 않음(혼입 방지)
    jp = (f"{hook_line1}{hook_line2}\n\n"
          f"{feature_line}。\n"
          f"生息水深は {info.depth_range_m}メートル。\n"
          f"深い海の底に、たしかに生きている。\n\n"
          f"心に残ったら保存を。\n同じ海が気になる人へシェアを。\n\n"
          f"映像: {credit}")
    tags_ko = default_tags_ko if default_tags_ko else _ko_tags(default_tags, jp_name, ko_name)
    return {"jp": jp, "ko": ko, "tags": default_tags, "tags_ko": tags_ko}


def generate(info: SpeciesInfo, jp_name: str, sci_name: str, feature_line: str,
             hook_line1: str, hook_line2: str, hook_ko: str = "", feature_ko: str = "",
             credit: str = "", default_tags: list[str] | None = None,
             default_tags_ko: list[str] | None = None) -> dict:
    """리치 캡션 {jp, ko, tags, tags_ko}. LLM 우선, 실패 시 사실 기반 리치 폴백."""
    credit = credit or ((info.sources or ["Wikimedia Commons"])[0])
    default_tags = default_tags or ["#海", f"#{jp_name}", "#生き物"]
    facts = "\n".join(f"- {f}" for f in (info.fun_facts or [])[:6]) or "- (追加事実なし)"
    prompt = _PROMPT.format(jp=jp_name, sci=sci_name, depth=info.depth_range_m,
                            hab=info.habitat, dist=info.distribution, facts=facts, credit=credit)
    out = None
    try:
        out = llm.generate_text(prompt, max_tokens=1100)
    except Exception as e:  # noqa: BLE001
        log.warning("[rich_caption] LLM 실패: %s", e)
    if out:
        m = re.search(r"\{.*\}", out, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                jp, ko = d.get("jp_caption", "").strip(), d.get("ko_caption", "").strip()
                if jp and ko and not re.search(r"[ぁ-んァ-ヶ]", ko):   # KO에 일본어 잔류 금지
                    tags = [t for t in (d.get("hashtags") or []) if str(t).strip()][:3]
                    if len(tags) < 3:
                        tags = (tags + default_tags)[:3]
                    ko_tags = [t for t in (d.get("ko_hashtags") or []) if str(t).strip()][:3]
                    if len(ko_tags) < 3:
                        ko_tags = _ko_tags(tags, jp_name, info.common_name_ko or jp_name)
                    return {"jp": jp, "ko": ko, "tags": tags, "tags_ko": ko_tags}
            except Exception:  # noqa: BLE001
                pass
    return _fallback(info, jp_name, feature_line, hook_line1, hook_line2,
                     hook_ko, feature_ko, credit, default_tags, default_tags_ko)
