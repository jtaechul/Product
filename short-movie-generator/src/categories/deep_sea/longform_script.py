"""롱폼(랭킹형) 세그먼트용 상세 나레이션 · 스탬프 요약 · 해역 좌표 도출.

쇼츠(reels) 본문보다 **더 자세한** 종별 나레이션(8~14절, 敬体·보통속도)을 만든다.
테마(기이한/위험한/놀라운/미스터리한/무서운)에 맞춰 톤을 색칠하되, 사실 왜곡은 금지.
- LLM(Claude→Gemini) 우선, 실패 시 reels 시드 본문을 확장한 결정적 폴백.
- 스탬프(엔드 요약): stamp_line(한 줄 핵심) + stamp_big(짧은 임팩트 어구).
- 해역: distribution/habitat 키워드 → 지도 정규화 좌표(nx=lon/360, ny=(90-lat)/180) + 일본어 라벨.

★규칙: 나레이션·스탬프는 敬体(존댓말). 없는 행동·수치·위험·발광·포식 날조 금지(하드룰).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re

from src.categories.deep_sea import hook as hook_copy
from src.core import llm
from src.core.contracts import SpeciesInfo

log = logging.getLogger(__name__)

# 테마 키(한국어) → (일본어 형용, 타이틀어, 톤 힌트)
THEMES = {
    "기이한": ("奇妙な", "衝撃", "奇妙さ・不思議さ"),
    "위험한": ("危険な", "危険", "警戒・緊張感(ただし事実の範囲で)"),
    "놀라운": ("驚きの", "驚異", "驚き・感嘆"),
    "미스터리한": ("神秘の", "神秘", "謎めいた雰囲気"),
    "무서운": ("恐ろしい", "恐怖", "薄暗い畏怖(ただし事実の範囲で)"),
}
DEFAULT_THEME = "기이한"


def theme_words(theme_key: str) -> tuple[str, str, str]:
    return THEMES.get(theme_key, THEMES[DEFAULT_THEME])


# ─────────────── 해역 좌표(지도 정규화) ───────────────
# nx=lon/360, ny=(90-lat)/180 (Pacific-centered equirectangular, motion.py와 동일)
def _c(lon: float, lat: float) -> tuple[float, float]:
    return (round((lon % 360) / 360.0, 3), round((90.0 - lat) / 180.0, 3))


# 키워드(일/영/한) → (nx, ny, 일본어 라벨). 넓은 해역(포인트 아님) 기준 대표점.
_REGIONS = [
    (("北東太平洋", "northeast pacific", "북동태평양"), (*_c(-140, 40), "北東太平洋")),
    (("北西太平洋", "northwest pacific", "일본", "japan", "북서태평양"), (*_c(145, 35), "北西太平洋")),
    (("モントレー", "monterey", "california", "캘리포니아"), (*_c(-122, 36), "北東太平洋 モントレー湾")),
    (("メキシコ湾", "gulf of mexico", "멕시코만"), (*_c(-90, 25), "メキシコ湾")),
    (("北大西洋", "north atlantic", "북대서양"), (*_c(-30, 45), "北大西洋")),
    (("大西洋", "atlantic", "대서양"), (*_c(-25, 20), "大西洋")),
    (("地中海", "mediterranean", "지중해"), (*_c(18, 37), "地中海")),
    (("インド洋", "indian ocean", "인도양"), (*_c(80, -20), "インド洋")),
    (("南極", "南大洋", "southern ocean", "antarctic", "남극", "남대양"), (*_c(0, -62), "南極海")),
    (("太平洋", "pacific", "태평양"), (*_c(-160, 5), "太平洋")),
]
# 전 세계 분포 종을 지도에 흩뜨릴 대표 심해점(종 해시로 결정론 선택)
_WORLDWIDE = [
    (*_c(-140, 35), "太平洋の深海"),
    (*_c(-30, 30), "大西洋の深海"),
    (*_c(150, 20), "西太平洋の深海"),
    (*_c(70, -15), "インド洋の深海"),
    (*_c(-90, 20), "中央アメリカ沖の深海"),
]


def region_for(info: SpeciesInfo) -> tuple[float, float, str]:
    """(nx, ny, 라벨_jp). distribution/habitat 키워드 매칭 → 없으면 전세계 대표점(종 해시)."""
    hay = " ".join([info.distribution or "", info.habitat or "", info.scientific_name or ""]).lower()
    for keys, (nx, ny, label) in _REGIONS:
        if any(k.lower() in hay for k in keys):
            return (nx, ny, label)
    # 전 세계/미매칭 → 종 해시로 대표 심해점 분산
    h = int(hashlib.md5((info.scientific_name or "deep").encode("utf-8")).hexdigest(), 16)
    return _WORLDWIDE[h % len(_WORLDWIDE)]


# ─────────────── 상세 나레이션(LLM + 시드 확장 폴백) ───────────────
_PROMPT = """あなたは深海生物の長編ドキュメンタリー(YouTube 8分ランキング動画)のナレーション作家です。\
1種ぶんの語りを**日本語**で作ります。JSONのみ出力(説明・コードブロック禁止)。

テーマ: この動画は「{adj}深海生物」という切り口です(トーン: {tone})。
生物: 和名候補={jp} / 英名={en} / 学名={sci} / 生息水深={depth}m / 生息域={hab} / 分布={dist}
特徴(事実): {facts}

要件:
- narration: 10〜16個の短い節に分けた語り。導入(情景)→正体→驚きの生態を事実で2〜3点→\
テーマに沿った感情的な締め、という構成。**ぶつ切りでなく自然になめらかに**。
- **★敬体(です・ます)で統一。常体(だ・である/〜する/〜いる/〜終える)は禁止**。\
名詞・体言止めの短い節は可(丁寧さを保つ範囲で)。
- 各節は読点/句点で終わる短めの節にし、字幕同期しやすく。
- **実際の形態・行動のみ**。無い発光・捕食・危険・数値・サイズの捏造禁止。テーマで誇張しない。
- stamp_line: この生物の核心を1文で(敬体・20字前後、体言止め可)。
- stamp_big: 短く強い印象語(4〜8字、名詞句。例:「最長の子育て」「深海の掃除屋」)。

JSON例: {{"narration":["深海の底に、","じっと動かない影。", "..."],"stamp_line":"...","stamp_big":"..."}}
"""


def _seed_fallback(info: SpeciesInfo) -> dict:
    """LLM 불가 시: reels 시드 본문(일본어)을 그대로 사용. 한국어 fun_fact는 자막에 넣지 않는다.

    ★스탬프도 일본어 나레이션에서만 도출한다(한국어 fun_fact 주입 금지 — 敬体 위반 방지).
    시드가 없으면 최소 일본어 골격(사실 왜곡 없는 정보 뼈대)만 낸다.
    """
    base = hook_copy.build_body_jp(info)   # 시드(있으면, 일본어) 또는 None
    jp = _guess_jp(info)
    chunks: list[str] = list(base) if base else [
        "深海の闇に、", "ひそむ影。", f"その正体は、{jp}。",
        "その姿を、", "ゆっくりとご覧ください。",
    ]
    # 스탬프: 일본어 나레이션의 마지막(정리) 절을 핵심 한 줄로. 없으면 일반형.
    tail_jp = [c for c in chunks if _looks_jp(c)]
    stamp_line = _clip((tail_jp[-1].rstrip("、") if tail_jp else "深海に生きる、静かな存在です。"), 24)
    if not stamp_line.endswith(("。", "…")):
        stamp_line += "。"
    return {
        "narration": chunks[:16],
        "stamp_line": stamp_line,
        "stamp_big": _guess_big(info),
    }


def _looks_jp(s: str) -> bool:
    """가나/한자 포함 = 일본어로 간주(한국어 fun_fact 혼입 방지 판별)."""
    return any("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿" for ch in (s or ""))


def _guess_jp(info: SpeciesInfo) -> str:
    return (info.common_name_ko or info.common_name_en or info.scientific_name or "深海生物")


def _guess_big(info: SpeciesInfo) -> str:
    hab = info.habitat or ""
    if "掃除" in hab or "腐" in hab:
        return "深海の掃除屋"
    return "深海の主"


def _ko_to_plain(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _ensure_polite(s: str) -> str:
    """문말이 존댓말이 아니면 '。' 앞을 정리(폴백 안전판, 완벽 변환은 아님)."""
    s = s.strip()
    if not s:
        return s
    if not s.endswith(("です", "ます", "です。", "ます。", "。")):
        s = s.rstrip("。") + "です。"
    return s


def _ko_fact_to_jp_hint(fact: str) -> str:
    """한국어 fun_fact를 그대로 자막에 쓰지 않는다(敬体 일본어 필요). 폴백에선 생략(빈 문자열).
    → LLM이 정상 동작하는 CI에서 제대로 된 일본어 나레이션이 생성된다. 폴백은 시드 우선."""
    return ""


def _clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def build_segment_script(info: SpeciesInfo, theme_key: str = DEFAULT_THEME) -> dict:
    """롱폼 세그먼트 대본. 반환: {narration:[...], stamp_line, stamp_big}. LLM→시드 폴백(항상 dict)."""
    adj, _title, tone = theme_words(theme_key)
    jp = _guess_jp(info)
    facts = " / ".join((info.fun_facts or [])[:5]) or "-"
    prompt = _PROMPT.format(adj=adj, tone=tone, jp=jp, en=info.common_name_en,
                            sci=info.scientific_name, depth=info.depth_range_m,
                            hab=info.habitat, dist=info.distribution, facts=facts)
    out = None
    try:
        out = llm.generate_text(prompt, max_tokens=900)
    except Exception as e:  # noqa: BLE001
        log.warning("[longform_script] LLM 실패: %s", e)
    data = _parse(out)
    if data and len(data.get("narration", [])) >= 8:
        return data
    log.info("[longform_script] LLM 부족 → 시드 확장 폴백")
    return _seed_fallback(info)


def _parse(out: str | None) -> dict | None:
    if not out:
        return None
    m = re.search(r"\{.*\}", out, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None
    nar = [str(x).strip() for x in obj.get("narration", []) if str(x).strip()]
    if not nar:
        return None
    return {
        "narration": nar,
        "stamp_line": _clip(str(obj.get("stamp_line", "")).strip() or nar[-1], 26),
        "stamp_big": _clip(str(obj.get("stamp_big", "")).strip() or "深海の主", 10),
    }
