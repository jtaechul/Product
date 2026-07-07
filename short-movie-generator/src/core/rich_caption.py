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

_PROMPT = """あなたは日本の海洋生物系メディアの一流ライターです。以下のデータだけを使い、\
インスタ/リール用の【読み応えのある物語調キャプション】を書きます。JSONのみ出力(説明・コードブロック禁止)。

対象データ(この範囲の事実のみ使用・**捏造厳禁**。無い行動・数値・発光・捕食は書かない):
- 和名: {jp}
- 学名: {sci}
- 生息水深: {depth} m
- 生息環境: {hab}
- 分布: {dist}
- 確かな事実:
{facts}

【jp_caption の必須要件】
- 日本語。**10〜14行**の、しっかりした読み物。箇条書きの羅列は禁止。情感のある物語のように滑らかに。
- 構成:
  1) 導入(1〜2行): 想像をかき立てるフック(種名は出さない)。
  2) 本編(6〜9行): 次を**物語として織り込む**——
     ・和名と学名(学名は「(学名: {sci})」の形で正式表記で一度だけ入れる)。
     ・どれくらいの深さ({depth}m)の、どんな海({dist})の、どんな場所({hab})に暮らすのかを情景として描く。
     ・上の「確かな事実」から2〜3個を選び、ただ述べるのでなく\
「なぜそうなのか」「どんな姿・どんな暮らしか」を添えて、読者が思わず「へえ」と唸る知識として丁寧に描く。
  3) 結び(2行): 「心に残ったら保存を」の主旨 +「同じ海が気になる人へシェアを」の主旨。
  4) 最終行: 「映像: {credit}」。
- 一文の長短にリズムをつけ、単調な同型文の連続を避ける。専門用語は噛み砕いて説明する。
- ko_caption: jp_caption の**完全な韓国語訳**(日本語を一切残さない、自然で読みやすい韓国語。情報量は同じ)。
- hashtags: 日本語ハッシュタグ**ちょうど3個**(例: ["#深海","#生き物","#{jp}"])。
- ko_hashtags: hashtags の韓国語訳3個。

JSON例: {{"jp_caption":"...","ko_caption":"...","hashtags":["#..","#..","#.."],"ko_hashtags":["#..","#..","#.."]}}
"""


def _cap_sci(sci: str) -> str:
    """학명 표기: 속명 첫 글자 대문자·나머지 소문자 어절(예: 'Enypniastes eximia')."""
    s = (sci or "").strip()
    if not s:
        return s
    parts = s.split()
    parts[0] = parts[0][:1].upper() + parts[0][1:].lower()
    return " ".join(parts)

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


def _fallback(info: SpeciesInfo, jp_name: str, sci_name: str, feature_line: str,
              hook_line1: str, hook_line2: str, hook_ko: str, feature_ko: str, credit: str,
              default_tags: list[str], default_tags_ko: list[str] | None = None) -> dict:
    """LLM 실패 시 리치 템플릿. 학명·수심·분포·서식지·fun_facts를 서술식으로 엮어 풍부하게.
    한국어는 한국어 데이터로 완전 서술(일본어 잔류 금지). 일본어는 일본어 요소만(혼입 방지)."""
    ko_name = info.common_name_ko or jp_name
    sci = _cap_sci(sci_name)
    facts_ko = [f.strip().rstrip(".") for f in (info.fun_facts or []) if f][:3]
    # 한국어 캡션 — 서술식 읽을거리(학명·수심·분포·서식지·사실 엮음)
    ko_lines = [hook_ko or f"{ko_name}, 이름을 들어보셨나요?", ""]
    ko_lines.append(f"{ko_name}(학명: {sci}).")
    if info.depth_range_m and info.distribution:
        ko_lines.append(f"수심 {info.depth_range_m}m, {info.distribution}의 바다에 살아갑니다.")
    if info.habitat:
        ko_lines.append(f"주로 {info.habitat}에서 지냅니다.")
    for f in facts_ko:
        ko_lines.append(f"{f}.")
    if feature_ko:
        ko_lines.append(feature_ko + ".")
    ko_lines += ["", "마음이 복잡한 날, 다시 꺼내보고 싶다면 저장해 두세요.",
                 "같은 바다가 궁금한 사람에게 조용히 건네주세요.", "", f"영상: {credit}"]
    ko = "\n".join(ko_lines)
    # 일본어 캡션 — 일본어 요소 + 세계공통 학명·수심으로 서술(분포·서식지는 한국어라 제외)
    jp_lines = [f"{hook_line1}{hook_line2}", "",
                f"{jp_name}(学名: {sci})。",
                f"生息水深はおよそ {info.depth_range_m} メートル。",
                f"{feature_line}。",
                "深い海の底で、たしかに命をつないでいる一種です。", "",
                "心に残ったら保存を。", "同じ海が気になる人へシェアを。", "", f"映像: {credit}"]
    jp = "\n".join(jp_lines)
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
    prompt = _PROMPT.format(jp=jp_name, sci=_cap_sci(sci_name), depth=info.depth_range_m,
                            hab=info.habitat, dist=info.distribution, facts=facts, credit=credit)
    out = None
    try:
        out = llm.generate_text(prompt, max_tokens=1800)  # 10~14행 리치 캡션 여유
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
    return _fallback(info, jp_name, sci_name, feature_line, hook_line1, hook_line2,
                     hook_ko, feature_ko, credit, default_tags, default_tags_ko)
