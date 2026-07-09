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

■ ハウス・トーン(厳守): **畏敬のドキュメンタリーを背骨に、たまに“淡々としたブラックユーモア”を一匙**。
真面目一辺倒で眠くさせない。**過酷/暗い事実を日常語(労働・制度・生活)に淡々と置き換える一文を1〜2箇所**だけ挟む
(例:「昼休みも、有給もありません。」)。はしゃがず、毒は薄く、最後は畏敬に戻す。事実は曲げない。
■ jp_caption の必須要件:
- **★敬体(です・ます)で書く。常体(だ・である/〜する/〜だ)は禁止**(語りかける丁寧な口調。疑問形・名詞止めは可)。
- 日本語。見本と同等の分量——**13〜18行・450〜700字**。短くしない。箇条書きの羅列は禁止。物語のように滑らかに。
- その物語の中に、**淡々としたブラックユーモアを1〜2文**だけ自然に混ぜる(浮かせない・全体の畏敬は保つ)。
- 構成: ①導入2〜3行(情景から入り種名は出さない) → ②「その名は{jp}(学名: {sci})。」で正式に一度 →
  ③生息地(水深{depth}m・分布{dist}・環境{hab})を情景として描く →
  ④「確かな事実」から2〜3個を選び、各事実を**3〜4行**かけて「なぜ・どんな姿・どんな暮らし」を理由や比喩とともに厚く描く →
  ⑤結び2行「心に残ったら保存を」「同じ海を想う誰かへシェアを」の主旨 → ⑥最終行「映像: {credit}」。
- 一文の長短にリズムをつけ、専門用語は噛み砕く。
■ ko_caption: jp_caption の完全な韓国語訳(日本語を一切残さない、自然で**同じ分量**の韓国語)。**存待말(〜습니다/〜입니다)で統一**、반말禁止。
■ hashtags: 日本語ちょうど3個。 ko_hashtags: その韓国語訳3個。
■ yt_title (YouTube Shorts 用タイトル。あなたは**CTRを極大化するプロのコピーライター**):
- 生物名と核となる特徴1〜2個を使い、視聴者が思わずクリックするタイトルを作る。
- **ハウス・トーン**: ただ煽るのではなく、**畏怖の核 + 淡々としたブラックユーモア/意外性**を効かせた“ひとひねり”。
  過酷な生態を日常語(労働・制度・生活)に落として意外性を出すと強い。例:「4年半、飲まず食わずの母」\
  「有給ゼロで卵を守る深海の母」「死骸専門、深海の掃除屋」。誇張はしても嘘はつかない。
- **全角30字以内**で簡潔に。**モバイルで切れないよう、最も刺激的な核キーワードを必ず文頭に置く**(先頭しか見えない)。
- **ハッシュタグ(#Shorts等)・絵文字・記号装飾は一切付けない**。**敬語(です・ます)は禁止**(タイトルは体言止め・言い切りで短く)。
- 検索性のため**種名({jp})を含める**(フックの後ろでよい)。
- **【衝撃】【驚愕】「99%が知らない」等の“中身のない”汎用接頭辞は禁止**(具体性のある刺激語・意外性で釣る)。
- **事実を曲げない**: 「怪物」「宇宙生物」等は直喩「〜のような」か疑問形で。無害な種に嘘の危険を捏造しない。
■ ko_title: yt_title の自然な韓国語版(同じ型・同じ長さ感、日本語を残さない、タグ無し)。

JSON例: {{"jp_caption":"...","ko_caption":"...","hashtags":["#..","#..","#.."],"ko_hashtags":["#..","#..","#.."],"yt_title":"...","ko_title":"..."}}
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

    원칙(제목 정책과 동일): 앞머리에 최강 훅(호기심 갭) + 종명 포함(검색성) +
    해시태그·범용 자극어(【衝撃】류) 금지. 훅 문장 자체가 이미 역설/의외성을 담고 있으므로
    훅을 앞세우고 종명으로 정체를 궁금하게 만든다. 종마다 템플릿 로테이션(같은 틀 반복 방지)."""
    ko_name = info.common_name_ko or jp_name
    hj = (hook_jp or "").strip().rstrip("。.!！?？")
    hk = (hook_ko or "").strip().rstrip(".!?")
    jp_tpl = [
        f"{hj}——{jp_name}の正体",
        f"なぜ{hj}のか。{jp_name}",
        f"{hj}…その名は{jp_name}",
        f"{hj}。{jp_name}の知られざる生態",
    ]
    ko_tpl = [
        f"{hk}——{ko_name}의 정체",
        f"{ko_name}는 왜? {hk}",
        f"{hk}…그 이름은 {ko_name}",
        f"{hk}. {ko_name}의 알려지지 않은 생태",
    ]
    i = sum(ord(c) for c in (info.scientific_name or jp_name)) % len(jp_tpl)
    # 훅이 비면 종명 중심의 안전 제목
    if not hj:
        return (f"深海でひっそり生きる、{jp_name}の素顔",
                f"깊은 바다에 숨어 사는, {ko_name}의 맨얼굴")
    return jp_tpl[i], ko_tpl[i]


_HYPE_PREFIX = re.compile(r"【(衝撃|驚愕|閲覧注意|충격|경악)】|99[%％]が知らない|99[%％]가 모르는")


def _clean_title(t: str) -> str:
    """제목 정책 강제: 해시태그(#Shorts 등)·범용 자극어 접두사 제거, 공백 정리.
    LLM이 정책을 어겨도 발행 제목은 항상 규격을 지키게 하는 최종 관문."""
    t = re.sub(r"#\S+", "", t or "")
    t = _HYPE_PREFIX.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip(" 　-—・|").strip()


def _valid_title(t: str, jp_name: str) -> bool:
    """LLM 제목 채택 기준: 정리 후 10~34자(모바일 30자 이내 목표+약간 여유) + 종명 포함(검색성)."""
    t = _clean_title(t)
    return bool(t) and 10 <= len(t) <= 34 and (jp_name in t if jp_name else True)


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
    """LLM 출력에서 JSON 추출 → dict(없으면 None).

    strict=False 필수: 모델이 캡션(13~18행)을 **실제 줄바꿈 포함** JSON 문자열로 줄 때가 있는데
    기본 json.loads는 제어문자를 거부해 좋은 캡션이 통째로 버려졌다(200 OK인데 폴백으로 빠진 실증).
    실패 시엔 원인 파악을 위해 출력 앞부분을 로그로 남긴다."""
    if not out:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        log.warning("[rich_caption] LLM 출력에 JSON 없음: %.120s", out)
        return None
    try:
        return json.loads(m.group(0), strict=False)
    except Exception as e:  # noqa: BLE001
        log.warning("[rich_caption] JSON 파싱 실패(%s): %.160s…", e, m.group(0))
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
            # 4000 토큰: JP 캡션(450~700자)+KO 완역+제목까지 담으면 2400으로는 잘려
            # JSON이 미완성(파싱 실패) → 폴백으로 빠지는 실증 사례가 있었다.
            out = llm.generate_text(prompt, max_tokens=4000)
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
        # 유튜브 제목: 정책 정리(_clean_title: 태그·자극어 제거) 후 기준 통과 시 채택, 아니면 폴백
        tj = _clean_title(str(d.get("yt_title", "")))
        tk = _clean_title(str(d.get("ko_title", "")))
        if not _valid_title(tj, jp_name):
            tj, fk = _fallback_titles(info, jp_name, f"{hook_line1}{hook_line2}", hook_ko)
            tk = tk if tk else fk
        if not tk or re.search(r"[ぁ-んァ-ヶ]", tk):   # 한국어판에 일본어 잔류 → 폴백
            tk = _fallback_titles(info, jp_name, f"{hook_line1}{hook_line2}", hook_ko)[1]
        return {"jp": jp, "ko": ko, "tags": tags, "tags_ko": ko_tags,
                "yt_title": tj, "yt_title_ko": tk}

    log.warning("[rich_caption] LLM 리치 캡션 실패 → 사실 기반 폴백 사용")
    return _fallback(info, jp_name, sci_name, feature_line, hook_line1, hook_line2,
                     hook_ko, feature_ko, credit, default_tags, default_tags_ko)
