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
■ yt_title (YouTube Shorts 用タイトル・アルゴリズム/マーケティング最適化):
- 日本語 **20〜38字**(モバイルで切れない長さ)。文末に「 #Shorts」を付ける。
- **好奇心ギャップ**が核: 一番意外な事実を「答えを言わずに」チラ見せする(全部言わない)。
  例の型: 「〜する◯◯の正体」「なぜ◯◯は〜のか」「【衝撃】〜だった」「99%が知らない〜」。
- 検索性のため**種名({jp})を必ず含める**。冒頭寄りにフック語(【衝撃】【謎】など)か疑問形。
- 誇張・捏造は禁止(上の「確かな事実」の範囲内でだけ驚きを作る)。絵文字は使わない。
■ ko_title: yt_title の自然な韓国語版(同じ型・同じ長さ感、日本語を残さない、末尾 #Shorts)。

JSON例: {{"jp_caption":"...","ko_caption":"...","hashtags":["#..","#..","#.."],"ko_hashtags":["#..","#..","#.."],"yt_title":"... #Shorts","ko_title":"... #Shorts"}}
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


def _fallback_titles(info: SpeciesInfo, jp_name: str, hook_jp: str, hook_ko: str) -> tuple[str, str]:
    """LLM 실패 시 유튜브 제목(일/한) — 마케팅 원칙을 담은 결정론 템플릿.

    원칙: 호기심 갭(훅을 던지고 답을 감춤) + 종명 포함(검색성) + 강조 괄호【】 + #Shorts.
    종마다 같은 틀만 반복되지 않게 학명 해시로 템플릿을 로테이션한다(사실 날조 없음)."""
    ko_name = info.common_name_ko or jp_name
    hj = (hook_jp or "").strip().rstrip("。.!！?？")
    hk = (hook_ko or "").strip().rstrip(".!?")
    jp_tpl = [
        f"【衝撃】{hj}——{jp_name}の正体 #Shorts",
        f"なぜ{jp_name}は「{hj}」のか #Shorts",
        f"{hj}…{jp_name}、知られざる素顔 #Shorts",
        f"【深海の謎】{jp_name}が{hj}理由 #Shorts",
    ]
    ko_tpl = [
        f"【충격】{hk}——{ko_name}의 정체 #Shorts",
        f"{ko_name}는 왜? {hk} #Shorts",
        f"{hk}…{ko_name}, 알려지지 않은 얼굴 #Shorts",
        f"【깊은 바다의 수수께끼】{ko_name}——{hk} #Shorts",
    ]
    i = sum(ord(c) for c in (info.scientific_name or jp_name)) % len(jp_tpl)
    # 훅이 비면 종명 중심의 안전 제목
    if not hj:
        return (f"【深海の神秘】{jp_name}の知られざる生態 #Shorts",
                f"【깊은 바다의 신비】{ko_name}의 알려지지 않은 생태 #Shorts")
    return jp_tpl[i], ko_tpl[i]


def _valid_title(t: str, jp_name: str) -> bool:
    """LLM 제목 채택 기준: 비어있지 않고, 너무 짧거나 길지 않고(12~60자), 종명 포함."""
    t = (t or "").strip()
    return bool(t) and 12 <= len(t) <= 60 and (jp_name in t if jp_name else True)


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
    tj, tk = _fallback_titles(info, jp_name, f"{hook_line1}{hook_line2}", hook_ko)
    return {"jp": jp, "ko": ko, "tags": default_tags, "tags_ko": tags_ko,
            "yt_title": tj, "yt_title_ko": tk}


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
    """예시 수준 분량인지 — 글자수 기준(≥260자). 줄바꿈 유무는 보지 않는다
    (LLM이 한 문단으로 줄 때가 있어 줄 수로 판정하면 좋은 캡션을 놓친다 → _format_lines가 줄바꿈 정리)."""
    return bool(jp) and len(jp) >= 260


def _format_lines(jp: str) -> str:
    """가독성: 한 문단으로 온 캡션을 문장(。!?) 단위로 줄바꿈해 예시처럼 읽기 좋게 만든다.
    이미 줄바꿈이 충분하면(≥6) 그대로 둔다. 마지막 '映像:' 크레딧 줄은 분리 유지."""
    jp = (jp or "").strip()
    if jp.count("\n") >= 6:
        return jp
    cred = ""
    m = re.search(r"(映像[:：].*)$", jp)
    if m:
        cred = m.group(1).strip()
        jp = jp[:m.start()].strip()
    # 문장 끝(。!?) 뒤에서 줄바꿈. 기존 줄바꿈은 문단 구분으로 유지.
    parts = []
    for para in jp.split("\n"):
        para = para.strip()
        if not para:
            continue
        sents = re.findall(r"[^。!?！？]*[。!?！？]|[^。!?！？]+$", para)
        parts.extend(s.strip() for s in sents if s.strip())
    body = "\n".join(parts)
    return body + ("\n\n" + cred if cred else "")


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
        jp = _format_lines(jp)   # 한 문단이면 문장 단위 줄바꿈으로 가독성 정리
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
        # 유튜브 제목: LLM 제목이 기준(길이·종명 포함) 통과 시 채택, 아니면 마케팅 폴백
        tj = str(d.get("yt_title", "")).strip()
        tk = str(d.get("ko_title", "")).strip()
        if not _valid_title(tj, jp_name):
            tj, fk = _fallback_titles(info, jp_name, f"{hook_line1}{hook_line2}", hook_ko)
            tk = tk if tk else fk
        if not tk or re.search(r"[ぁ-んァ-ヶ]", tk):   # 한국어판에 일본어 잔류 → 폴백
            tk = _fallback_titles(info, jp_name, f"{hook_line1}{hook_line2}", hook_ko)[1]
        if not tj.rstrip().endswith("#Shorts"):
            tj = tj.rstrip() + " #Shorts"
        if not tk.rstrip().endswith("#Shorts"):
            tk = tk.rstrip() + " #Shorts"
        return {"jp": jp, "ko": ko, "tags": tags, "tags_ko": ko_tags,
                "yt_title": tj, "yt_title_ko": tk}

    log.warning("[rich_caption] LLM 리치 캡션 실패 → 사실 기반 폴백 사용")
    return _fallback(info, jp_name, sci_name, feature_line, hook_line1, hook_line2,
                     hook_ko, feature_ko, credit, default_tags, default_tags_ko)
