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
        "hook_ko": "머리도, 눈도, 뼈도 없다.",
        "feature_ko": "헤엄치고·빛나고·비치는, 심해의 해삼",
    },
    "opisthoteuthis californiana": {
        "jp_name": "メンダコ",
        "hook_line1": "ぺたんこの、体に、",
        "hook_line2": "耳のひれ。",
        "pop_words": ["ぺたんこの、", "体に、", "耳のひれ。"],
        "feature_line": "ひらひら舞う、深海のメンダコ",
        "feature_glow_word": "舞う",
        "hook_ko": "납작한 몸에, 귀 같은 지느러미.",
        "feature_ko": "하늘하늘 헤엄치는, 심해의 넓적문어",
    },
    "graneledone boreopacifica": {
        "jp_name": "シンカイダコ",
        "hook_line1": "四年半、ただ、",
        "hook_line2": "待ちつづけた。",
        "pop_words": ["四年半、", "ただ、", "待ちつづけた。"],
        "feature_line": "卵を守る、深海のタコ",
        "feature_glow_word": "守る",
        "hook_ko": "4년 반을, 그저, 기다렸습니다.",
        "feature_ko": "알을 지키는, 심해의 문어",
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
- hook_ko: hook_line1+hook_line2 の自然な**韓国語訳**(運営者の参考用)
- feature_ko: feature_line の自然な**韓国語訳**

JSON例: {{"jp_name":"...","hook_line1":"...","hook_line2":"...","pop_words":["...","...","..."],"feature_line":"...","feature_glow_word":"...","hook_ko":"...","feature_ko":"..."}}
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
    d.setdefault("hook_ko", "")
    d.setdefault("feature_ko", "")
    return d


# 대표종 본문 나레이션(일본어) 시드
_BODY_SEED = {
    "enypniastes eximia": [
        "深海の闇を、", "ただよう赤い影。", "その正体は、", "ユメナマコ。",
        "ナマコの仲間です。", "普通のナマコは、", "海底を這う。", "だが、これは泳ぐ。",
        "ひれのような膜で、", "闇を舞う。", "透きとおる体。", "飲みこんだ泥が、",
        "そのまま透けて見える。", "敵に襲われると、", "光る皮をぬぎ捨て、", "身代わりにする。",
        "深海では、", "もっとも奇妙な姿が、", "もっとも巧みに、", "生きのびる。",
    ],
    "opisthoteuthis californiana": [
        "深海の底に、", "ぺたりと張りつく影。", "その正体は、", "メンダコ。",
        "タコの仲間です。", "ふだんは、", "体をぺったんこに広げ、", "海底で休む。",
        "動くときは、", "頭の耳びれを、", "ぱたぱたと羽ばたく。", "腕のあいだには、",
        "傘のような膜。", "ふわりと広げて、", "水を舞う。", "やわらかなゼリーの体で、",
        "深い海の圧にも、", "そっと耐える。",
    ],
    "graneledone boreopacifica": [
        "冷たい岩に、", "じっとたたずむ影。", "その正体は、", "深海にすむタコ。",
        "母ダコは、", "岩に卵を産みつける。", "そして、", "そのそばを離れない。",
        "四年半もの長い間、", "ほとんど食べずに、", "卵を守りつづける。",
        "知られるかぎり、", "最も長い子育て。", "やがて卵がかえるころ、",
        "母は静かに、", "その一生を終える。",
    ],
}

_BODY_PROMPT = """あなたは深海生物のショート動画ナレーション作家です。次の生物について、\
**日本語**で30〜40秒・16〜22個の短い節に分けたナレーションを作ります。JSON配列のみ出力(説明禁止)。

生物: 英名={en} / 学名={sci} / 生息水深={depth}m / 生息域={hab}
特徴: {facts}

要件:
- 各要素は読点や句点で終わる**短い節**(6〜12文字)。全体で神秘的→驚き→事実→余韻。
- **実際の形態・行動のみ**。無い発光・捕食・危険・数値の捏造禁止。
- 序盤で正体(和名)を明かし、中盤で驚きの特徴、終盤で余韻。
出力例: ["深海の闇に、","揺らめく影。","その正体は、", ...]
"""


def build_body_jp(info: SpeciesInfo) -> list[str] | None:
    """본문 일본어 나레이션 절 리스트. 시드 → LLM → None."""
    key = (info.scientific_name or "").strip().lower()
    if key in _BODY_SEED:
        return list(_BODY_SEED[key])
    facts = " / ".join((info.fun_facts or [])[:4]) or "-"
    prompt = _BODY_PROMPT.format(en=info.common_name_en, sci=info.scientific_name,
                                 depth=info.depth_range_m, hab=info.habitat, facts=facts)
    try:
        out = llm.generate_text(prompt, max_tokens=600)
    except Exception as e:  # noqa: BLE001
        log.warning("[deep_sea.hook] 본문 LLM 실패: %s", e)
        out = None
    if not out:
        return None
    m = re.search(r"\[.*\]", out, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    chunks = [str(x).strip() for x in arr if str(x).strip()]
    return chunks if len(chunks) >= 8 else None


_CAPTION_PROMPT = """日本のインスタ向け、深海生物ショート動画の**キャプション**を作ります。\
JSONのみ出力(説明・コードブロック禁止)。

生物: 和名={jp} / 学名={sci} / 生息水深={depth}m / 特徴={facts}

要件:
- jp_caption: 日本語。1行目=共感・驚きのフック(種名は出さない)。2〜3行=核心の事実を簡潔に。\
終盤に「保存」を促す1行と「シェア」を促す1行。最後の行は「映像: NOAA Ocean Exploration・Public Domain」。
- ko_caption: jp_caption の**完全な韓国語訳**(運営者の参考用)。日本語の文をそのまま残さず、\
**すべての行を自然な韓国語に**訳すこと。
- hashtags: 日本語ハッシュタグ**ちょうど3個**(例: ["#深海","#生き物","#ユメナマコ"])
- ko_hashtags: hashtags それぞれの**韓国語訳**3個(例: ["#심해","#생물","#유메나마코"])

JSON例: {{"jp_caption":"...","ko_caption":"...","hashtags":["#深海","#...","#..."],"ko_hashtags":["#심해","#...","#..."]}}
"""


def _ko_tags_fallback(tags: list[str], jp_name: str, ko_name: str) -> list[str]:
    """일본어 해시태그의 한국어 참고 번역(간이 사전 + 국명 치환)."""
    table = {"#深海": "#심해", "#生き物": "#생물", "#海": "#바다", "#タコ": "#문어",
             "#ナマコ": "#해삼", "#イカ": "#오징어", "#魚": "#물고기", f"#{jp_name}": f"#{ko_name}"}
    return [table.get(t, f"#{ko_name}" if jp_name and jp_name in t else t) for t in tags]


def build_reels_caption(info: SpeciesInfo, jp_name: str, sci_name: str,
                        feature_line: str, hook_line1: str, hook_line2: str,
                        hook_ko: str = "", feature_ko: str = "") -> dict:
    """reels 캡션 — 일본어(발행)와 한국어(참고 번역)를 **분리**해 반환.

    반환: {jp, ko, tags, tags_ko}. ko는 jp의 완전 번역이어야 한다(일본어 원문 잔류 금지 —
    과거 폴백이 훅·특징 문장을 일본어 그대로 한국어 블록에 끼워 넣던 실제 결함의 재발 방지).
    LLM 우선, 실패 시 시드 한국어 번역(hook_ko/feature_ko) 기반 완전 한국어 폴백.
    """
    facts = " / ".join((info.fun_facts or [])[:4]) or "-"
    prompt = _CAPTION_PROMPT.format(jp=jp_name, sci=sci_name, depth=info.depth_range_m, facts=facts)
    try:
        out = llm.generate_text(prompt, max_tokens=700)
    except Exception as e:  # noqa: BLE001
        log.warning("[deep_sea.hook] 캡션 LLM 실패: %s", e)
        out = None
    parsed = None
    if out:
        m = re.search(r"\{.*\}", out, re.S)
        if m:
            try:
                d = json.loads(m.group(0))
                if d.get("jp_caption") and d.get("ko_caption"):
                    tags = [t for t in (d.get("hashtags") or []) if str(t).strip()][:3]
                    if len(tags) < 3:
                        tags = (tags + ["#深海", f"#{jp_name}", "#生き物"])[:3]
                    ko_tags = [t for t in (d.get("ko_hashtags") or []) if str(t).strip()][:3]
                    if len(ko_tags) < 3:
                        ko_tags = _ko_tags_fallback(tags, jp_name, info.common_name_ko)
                    parsed = {"jp": d["jp_caption"].strip(), "ko": d["ko_caption"].strip(),
                              "tags": tags, "tags_ko": ko_tags}
            except Exception:  # noqa: BLE001
                parsed = None
    if not parsed:  # 폴백 템플릿 — 한국어 블록은 '완전 한국어'(일본어 원문 잔류 금지)
        hk = hook_ko or f"{info.common_name_ko}의 놀라운 비밀."
        fk = feature_ko or f"심해에 사는 {info.common_name_ko}"
        jp = (f"{hook_line1}{hook_line2}\n\n"
              f"{feature_line}。\n深海にすむ{jp_name}です。\n\n"
              f"心に残ったら保存を。\n同じ深海が気になる人へシェアを。\n\n"
              f"映像: NOAA Ocean Exploration・Public Domain")
        ko = (f"{hk}\n\n"
              f"{fk}.\n심해에 사는 {info.common_name_ko}입니다.\n\n"
              f"마음에 남았다면 저장해 두세요.\n같은 심해가 궁금한 사람에게 공유해 주세요.\n\n"
              f"영상: NOAA Ocean Exploration · 퍼블릭 도메인")
        tags = ["#深海", f"#{jp_name}", "#生き物"]
        parsed = {"jp": jp, "ko": ko, "tags": tags,
                  "tags_ko": ["#심해", f"#{info.common_name_ko}", "#생물"]}
    return parsed


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
