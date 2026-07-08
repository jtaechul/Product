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

■ 品質の基準（この“長さ・濃さ・語り口”を必ず同等に再現する。※下は別の生き物の見本。内容は流用禁止・書き写し禁止）:
真っ青な海の中で、まるで空気が揺らぐように、透明な影がひとつ現れる。
次の瞬間、その姿は消えたかと思うと、模様だけが波打って残る——そんな不思議な生き物が、浅瀬には棲んでいる。
その名は◯◯(学名: ◯◯)。
◯◯の海の、水深にしてわずか数メートルから百数十メートルほどの浅い海域を住処にしている。
珊瑚の陰や海草の草原のような場所を選び、群れで漂うようにして暮らしているという。
（ここに「確かな事実」を2〜3個、情景・理由・比喩を添えて厚く描く。1つの事実を3〜4行かけて掘り下げる）
もしこの物語が心に触れたなら、どうか保存しておいてほしい。
そして、同じ海を想う誰かにも、そっとシェアしてあげてください。
映像: ◯◯

■ 対象データ(この範囲の事実のみ使用・**捏造厳禁**。無い行動・数値・発光・捕食は書かない):
- 和名: {jp}
- 学名: {sci}
- 生息水深: {depth} m
- 生息環境: {hab}
- 分布: {dist}
- 確かな事実:
{facts}

■ jp_caption の必須要件:
- 日本語。見本と同等の分量——**13〜18行・450〜700字**。短くしない。箇条書きの羅列は禁止。物語のように滑らかに。
- 構成: ①導入2〜3行(情景から入り種名は出さない) → ②「その名は{jp}(学名: {sci})。」で正式に一度 →
  ③生息地(水深{depth}m・分布{dist}・環境{hab})を情景として描く →
  ④「確かな事実」から2〜3個を選び、各事実を**3〜4行**かけて「なぜ・どんな姿・どんな暮らし」を理由や比喩とともに厚く描く →
  ⑤結び2行「心に残ったら保存を」「同じ海を想う誰かへシェアを」の主旨 → ⑥最終行「映像: {credit}」。
- 一文の長短にリズムをつけ、専門用語は噛み砕く。
■ ko_caption: jp_caption の完全な韓国語訳(日本語を一切残さない、自然で**同じ分量**の韓国語)。
■ hashtags: 日本語ちょうど3個。 ko_hashtags: その韓国語訳3個。

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


def _parse(out: str):
    """LLM 출력에서 JSON 추출 → dict(없으면 None)."""
    if not out:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def _is_rich(jp: str) -> bool:
    """예시 수준 분량인지 — 200자 이상 + 8줄 이상이면 리치로 인정."""
    return bool(jp) and len(jp) >= 200 and jp.count("\n") >= 8


def generate(info: SpeciesInfo, jp_name: str, sci_name: str, feature_line: str,
             hook_line1: str, hook_line2: str, hook_ko: str = "", feature_ko: str = "",
             credit: str = "", default_tags: list[str] | None = None,
             default_tags_ko: list[str] | None = None) -> dict:
    """리치 캡션 {jp, ko, tags, tags_ko}. LLM(예시 수준 분량 강제) 우선, 실패 시 리치 폴백.

    핵심: 분량이 예시(13~18행)에 못 미치면 1회 재시도. 일본어(발행본)만 충분하면 채택하고,
    한국어 번역에 문제가 있어도 일본어는 버리지 않는다(한국어만 폴백으로 보완).
    """
    credit = credit or ((info.sources or ["Wikimedia Commons"])[0])
    default_tags = default_tags or ["#海", f"#{jp_name}", "#生き物"]
    facts = "\n".join(f"- {f}" for f in (info.fun_facts or [])[:6]) or "- (追加事実なし)"
    prompt = _PROMPT.format(jp=jp_name, sci=_cap_sci(sci_name), depth=info.depth_range_m,
                            hab=info.habitat, dist=info.distribution, facts=facts, credit=credit)
    fb = None  # 폴백은 필요할 때만 계산

    d = None
    for attempt in range(2):   # 분량 미달이면 1회 재시도
        try:
            out = llm.generate_text(prompt, max_tokens=2400)
        except Exception as e:  # noqa: BLE001
            log.warning("[rich_caption] LLM 실패(%d): %s", attempt, e)
            out = None
        cand = _parse(out)
        if cand and _is_rich(str(cand.get("jp_caption", "")).strip()):
            d = cand
            break
        d = d or cand  # 리치는 아니어도 일단 보관(둘 다 실패하면 폴백)

    jp = str((d or {}).get("jp_caption", "")).strip()
    if _is_rich(jp):
        tags = [t for t in (d.get("hashtags") or []) if str(t).strip()][:3]
        if len(tags) < 3:
            tags = (tags + default_tags)[:3]
        ko = str(d.get("ko_caption", "")).strip()
        if not ko or re.search(r"[ぁ-んァ-ヶ]", ko):   # 한국어 잔류/부재 → 한국어만 폴백 보완
            fb = fb or _fallback(info, jp_name, sci_name, feature_line, hook_line1, hook_line2,
                                 hook_ko, feature_ko, credit, default_tags, default_tags_ko)
            ko = fb["ko"]
        ko_tags = [t for t in (d.get("ko_hashtags") or []) if str(t).strip()][:3]
        if len(ko_tags) < 3:
            ko_tags = _ko_tags(tags, jp_name, info.common_name_ko or jp_name)
        return {"jp": jp, "ko": ko, "tags": tags, "tags_ko": ko_tags}

    log.warning("[rich_caption] LLM 리치 캡션 실패 → 사실 기반 폴백 사용")
    return _fallback(info, jp_name, sci_name, feature_line, hook_line1, hook_line2,
                     hook_ko, feature_ko, credit, default_tags, default_tags_ko)
