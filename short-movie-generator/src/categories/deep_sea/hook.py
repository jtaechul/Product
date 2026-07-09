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
    "bathynomus giganteus": {
        "jp_name": "ダイオウグソクムシ",
        "hook_line1": "ダンゴムシが、",
        "hook_line2": "巨大化した。",
        "pop_words": ["ダンゴムシが、", "巨大化した。"],
        "feature_line": "海底を歩く、深海の大食漢",
        "feature_glow_word": "歩く",
        "hook_ko": "공벌레가, 거대해졌다.",
        "feature_ko": "해저를 걷는, 심해의 대식가",
    },
    "crossota sp.": {
        "jp_name": "シンカイクラゲ",
        "hook_line1": "赤は、",
        "hook_line2": "闇にまぎれる色。",
        "pop_words": ["赤は、", "闇にまぎれる色。"],
        "feature_line": "ゆらめく赤、深海をただようクラゲ",
        "feature_glow_word": "ゆらめく",
        "hook_ko": "붉은색은, 어둠에 숨는 색.",
        "feature_ko": "일렁이는 붉은빛, 심해를 떠도는 해파리",
    },
    "actinoscyphia aurelia": {
        "jp_name": "ハエトリギンチャク",
        "hook_line1": "食虫植物に、",
        "hook_line2": "にた深海の花。",
        "pop_words": ["食虫植物に、", "にた深海の花。"],
        "feature_line": "とじて食べる、深海のイソギンチャク",
        "feature_glow_word": "食べる",
        "hook_ko": "식충식물을, 닮은 심해의 꽃.",
        "feature_ko": "닫으며 먹는, 심해의 말미잘",
    },
    "megalodicopia hians": {
        "jp_name": "ニクショクホヤ",
        "hook_line1": "ホヤなのに、",
        "hook_line2": "獲物をとらえる。",
        "pop_words": ["ホヤなのに、", "獲物をとらえる。"],
        "feature_line": "口をとじて狩る、深海のホヤ",
        "feature_glow_word": "狩る",
        "hook_ko": "멍게인데, 먹이를 사냥한다.",
        "feature_ko": "입을 닫아 사냥하는, 심해의 멍게",
    },
    "umbellula sp.": {
        "jp_name": "シンカイウミエラ",
        "hook_line1": "一本の茎に、",
        "hook_line2": "花のような頭。",
        "pop_words": ["一本の茎に、", "花のような頭。"],
        "feature_line": "群れでくらす、深海のウミエラ",
        "feature_glow_word": "くらす",
        "hook_ko": "가느다란 줄기에, 꽃 같은 머리.",
        "feature_ko": "군체로 사는, 심해의 바다조름",
    },
}

_PROMPT = """あなたは**登録者1億人のYouTubeショート・アルゴリズムマーケター兼フッキングの達人**です。\
視聴者が3秒でスワイプを止める深海生物のオープニングフックを作ります。\
次の生物の情報から、JSONのみを出力してください(前後の説明・コードブロック禁止)。

生物: 英名={en} / 学名={sci} / 生息水深={depth}m / 生息域={hab}
特徴メモ: {facts}

【最優先=3秒フック】
- 生物名と、核となる特徴1〜2個だけを使い、視聴者の脳裏に一瞬で刺さる**没入型の一撃**を作る。
- ミステリー・恐怖・驚異を刺激する**挑発的トーン**。説明・ドキュメンタリー的な語りは徹底排除。
- 例の型:「絶対に会いたくない」「地球で最も奇妙な」「まるで宇宙生物のような」等で始め、\
  意外な特徴で落とす。答え(正体)は言い切らず、引きで残す。

要件:
- jp_name: この生物の日本語通称(カタカナ中心、なければ学名のカタカナ表記)
- hook_line1 / hook_line2: 2行のフック。**合計12〜15字**の、ごく短くスピード感のある単文。\
  各行は名詞・体言止め・読点で区切る(例:「頭も、目も、」「骨もない。」)。**種名は出さない**。
- pop_words: hook_line1+hook_line2を読点/句点で自然に区切った配列(3要素前後)
- feature_line: 「A・B・C、〜」形式の短い特徴文(例: 「泳ぐ・光る・透ける、深海のナマコ」)
- feature_glow_word: feature_line内で光・発光に関わる語(なければ最初の語)
- hook_ko: hook_line1+hook_line2 の自然な**韓国語訳**(運営者の参考用)
- feature_ko: feature_line の自然な**韓国語訳**

【フックは敬体を強制しない=インパクト最優先】
- フックは**マーケコピー**。です・ます(敬体)を強制しない。短い断片・体言止め・疑問形・言い切り、\
  どれでもよい(スピード感とリズムを優先。※本文ナレーション・字幕・キャプションは敬体厳守だが、フックは別)。
【厳守=信頼が資産・事実を曲げない】
- 挑発語は必ず**実在する特徴に紐づける**。無害な種に嘘の危険(「襲う」「猛毒」等)を捏造しない。
- 「宇宙生物」「怪物」等の断定は禁止。使うなら**直喩「〜のような」「まるで〜」**か**疑問形**にして事実を曲げない。

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
    # ★존댓말(敬体) 통일 — 문말 常体 금지. 体言止め·連用中止(、)는 정중함 유지 범위에서 허용.
    "enypniastes eximia": [
        "深海の闇を、", "ただよう赤い影。", "その正体は、", "ユメナマコ。",
        "ナマコの仲間です。", "普通のナマコは、", "海底を這います。", "でも、これは泳ぎます。",
        "ひれのような膜で、", "闇を舞います。", "透きとおる体。", "飲みこんだ泥が、",
        "そのまま透けて見えます。", "敵に襲われると、", "光る皮をぬぎ捨て、", "身代わりにします。",
        "深海では、", "もっとも奇妙な姿が、", "もっとも巧みに、", "生きのびます。",
    ],
    "opisthoteuthis californiana": [
        "深海の底に、", "ぺたりと張りつく影。", "その正体は、", "メンダコ。",
        "タコの仲間です。", "ふだんは、", "体をぺったんこに広げ、", "海底で休みます。",
        "動くときは、", "頭の耳びれを、", "ぱたぱたと羽ばたきます。", "腕のあいだには、",
        "傘のような膜。", "ふわりと広げて、", "水を舞います。", "やわらかなゼリーの体で、",
        "深い海の圧にも、", "そっと耐えます。",
    ],
    "graneledone boreopacifica": [
        "冷たい岩に、", "じっとたたずむ影。", "その正体は、", "深海にすむタコです。",
        "母ダコは、", "岩に卵を産みつけます。", "そして、", "そのそばを離れません。",
        "四年半もの長い間、", "ほとんど食べずに、", "卵を守りつづけるのです。",
        "知られるかぎり、", "最も長い子育てです。", "やがて卵がかえるころ、",
        "母は静かに、", "その一生を終えます。",
    ],
    "bathynomus giganteus": [
        "深海の底に、", "うずくまる影。", "その正体は、", "ダイオウグソクムシ。",
        "ダンゴムシの仲間です。", "体の長さは、", "三十センチをこえます。",
        "深海の掃除屋として、", "死んだ魚を食べます。", "えさの少ない、", "海の底。",
        "だから、", "ほとんど動かず、", "エネルギーを使いません。",
        "何ヶ月も、", "食べないことさえあります。", "深い海の、", "静かな大食漢です。",
    ],
    "crossota sp.": [
        "深海の中層を、", "ただよう赤い光。", "その正体は、", "深海性のクラゲ。",
        "鐘のような体から、", "細い触手を、", "放射状にのばします。",
        "赤い色は、", "深い海では、", "黒とおなじです。", "光の届かない闇に、", "すがたを消します。",
        "触手をひろげ、", "小さな獲物を、", "静かに待ちます。",
        "深海をただよう、", "赤い狩人です。",
    ],
    "actinoscyphia aurelia": [
        "流れのはやい、", "深海の崖に、", "咲く花のような影。", "その正体は、",
        "イソギンチャク。", "食虫植物の、", "ハエトリソウのように、",
        "触手のついた口を、", "ぱたりととじます。", "流れてきたエサを、",
        "つつみこみ、", "のがしません。", "海流にむきをあわせ、",
        "じっと待ちつづける、", "深海の花です。",
    ],
    "megalodicopia hians": [
        "深海の谷の、", "かべにはりつく影。", "その正体は、", "ホヤの仲間。",
        "ふつうのホヤは、", "水をこして、", "プランクトンを食べます。",
        "でも、これはちがいます。", "大きな口を、", "フードのようにひらき、",
        "エビのような獲物が、", "近づくと、", "一瞬でとじます。",
        "動かないのに、", "狩りをする、", "深海のホヤです。",
    ],
    "umbellula sp.": [
        "深海の砂地に、", "すっとのびる影。", "その正体は、", "ウミエラ。",
        "サンゴの仲間です。", "長い茎の先に、", "ポリプが集まり、", "花のように見えます。",
        "じつはこれ、", "一匹ではありません。", "小さな命が集まった、", "群体です。",
        "茎を砂にさし、", "海流にゆれながら、", "流れてくる養分を、", "とらえて食べます。",
        "深海にゆれる、", "生きた羽根かざりです。",
    ],
}

_BODY_PROMPT = """あなたは深海生物のショート動画ナレーション作家です。次の生物について、\
**日本語**で30〜40秒・16〜22個の短い節に分けたナレーションを作ります。JSON配列のみ出力(説明禁止)。

生物: 英名={en} / 学名={sci} / 生息水深={depth}m / 生息域={hab}
特徴: {facts}

■ ハウス・トーン(厳守): **「畏敬のドキュメンタリーを背骨に、たまに“淡々としたブラックユーモア”を一匙」**。
真面目一辺倒だと眠い。近年の動物ドキュメンタリーのように一度クスッとさせるが、笑いは**暗い/過酷な事実を
淡々と日常語(労働・制度・生活)に置き換える**ことで生む(はしゃがない・毒は薄く)。落ちは畏敬に戻す。

要件:
- **まず流れを設計してから書く**: 導入(情景・畏敬)→正体→確かな事実→畏敬の余韻。\
その中に**淡々としたブラックユーモアを1節だけ**混ぜる(例:「昼休みも、有給も、ありません。」)。
- **★敬体(です・ます)で書く。常体(だ・である/〜する/〜いる)は禁止**(語りかける丁寧な口調)。名詞・体言止めの短い節は可。
- 各節は読点/句点で終わる**短め**にし、字幕同期しやすく。
- **実際の形態・行動のみ**。無い発光・捕食・危険・数値の捏造禁止(笑いのために事実を曲げない)。
- 約8割は畏敬、ブラックユーモアは1節に留め、最後は畏敬で締める。
出力例: ["深海の底に、","じっと動かない母がいます。","その理由は、卵を守るため。","昼休みも、有給も、ありません。", ...]
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
- **★敬体で書く**: jp_caption は**です・ます体**、ko_caption は**〜습니다/〜입니다の存待말**で統一。\
常体(だ・である/〜다·〜한다)は禁止(疑問形・名詞止めの短いフックは可)。
- jp_caption: 日本語。1行目=共感・驚きのフック(種名は出さない)。2〜3行=核心の事実を簡潔に。\
終盤に「保存」を促す1行と「シェア」を促す1行。最後の行は「映像: NOAA Ocean Exploration・Public Domain」。
- ko_caption: jp_caption の**完全な韓国語訳**(運営者の参考用)。日本語の文をそのまま残さず、\
**すべての行を自然な韓国語(存待말)に**訳すこと。
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
