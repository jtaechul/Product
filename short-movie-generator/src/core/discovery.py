"""discovery — 해양생물 실사 영상 '자동 발굴'(운영자 개입 없이 소스 확대·풀 보충).

문제(사용자 확정): 지금까지 제작 가능한 종은 footage._SEED에 손으로 넣은 소수뿐이라, 풀이
소진되면 매번 클로드에 들어와 시드를 추가해야 했고 아침 자동 제작이 계속 실패했다.

해결: 이 모듈이 **Wikimedia Commons 전체(NOAA 한정 아님 — MBARI·다이버·수족관 등 모든 기여자,
CC-BY-SA 포함)**를 넓게 검색해 새 해양생물 영상을 찾고, **날조 없이** 종의 정체성과 사실을
자동 확보해 제작 풀에 추가한다.

날조 방지(핵심): 종 정체성과 사실을 지어내지 않는다.
  ① 정체성: Commons 구조화데이터(P180 '묘사') → Wikidata 분류군, 또는 파일명·설명의 학명(이명법)
     → Wikidata 검색. **P31=분류군(Q16521)이고 P225(학명)를 가진 항목만** 채택(실존 종 확인).
  ② 사실: 해당 분류군의 Wikipedia(일→영) 도입부 발췌 = 출처 있는 실제 정보만 사용.
  → 정체성·사실 어느 하나라도 확보 못하면 그 후보는 스킵(추측 제작 안 함).

품질 게이트는 기존 footage 경로 재사용(라이선스·종횡비·정지영상·번인카드). 발굴 결과는
`discovered.json`(카테고리별, 커밋됨)에 저장돼 회차 간 유지되고, footage._SEED / data.SPECIES에
import 시 병합된다.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

log = logging.getLogger(__name__)

_UA = ("DeepSeaShortsBot/1.0 (https://github.com/jtaechul/product; educational marine shorts) "
       "requests/2")
_COMMONS = "https://commons.wikimedia.org/w/api.php"
_WD = "https://www.wikidata.org/w/api.php"
_VIDEO_EXT = (".webm", ".ogv", ".ogg", ".mp4", ".mov")
# 통과 라이선스(운영자 확정: CC-BY-SA도 오픈). 문자열 부분일치로 판정.
_ALLOWED = ("public domain", "cc0", "cc by", "cc-by", "cc by-sa", "cc-by-sa", "kogl")
_BINOMIAL = re.compile(r"\b([A-Z][a-z]{2,})\s+([a-z]{3,})\b")
# ── 카테고리별 발굴 검색어(핵심 수정) ──
# 문제: 예전엔 모든 생물 카테고리가 아래 하나의 심해 검색어를 공유해, 미세조류(marine_algae)를
#   검색조차 안 하고 심해동물만 반환했다(거미까지 샘). → 카테고리마다 고유 검색어를 둔다.
_TERMS_DEEP = [
    "deep sea creature", "deep sea fish", "abyssal", "hydrothermal vent",
    "anglerfish", "siphonophore", "vampire squid", "dumbo octopus", "brittle star",
    "sea spider", "deep sea cucumber", "chimaera", "viperfish", "hatchetfish",
    "deep sea jellyfish", "bioluminescent", "ctenophore deep",
]
_TERMS_MARINE = [
    # 상어·가오리(연골어류) — 인기 주제인데 예전엔 검색어에 아예 없었다
    "shark underwater", "reef shark", "nurse shark", "whale shark", "hammerhead shark",
    "leopard shark", "blacktip shark", "manta ray", "stingray", "eagle ray", "electric ray",
    # 두족류
    "octopus underwater", "octopus reef", "squid underwater", "reef squid", "cuttlefish",
    # 해파리·젤리류
    "jellyfish", "moon jelly", "comb jelly", "box jellyfish", "jellyfish swarm",
    # 뱀장어류(해양 어류)
    "moray eel", "garden eel", "ribbon eel",
    # 암초 어류 다양
    "reef fish", "clownfish", "pufferfish", "lionfish", "angelfish", "parrotfish",
    "grouper", "wrasse", "surgeonfish", "triggerfish", "scorpionfish", "frogfish",
    "seahorse", "pipefish", "batfish", "trumpetfish",
    # 갑각류
    "crab underwater", "shrimp underwater", "lobster underwater", "mantis shrimp", "hermit crab",
    # 극피·연체·기타
    "nudibranch", "sea slug", "starfish", "sea star", "sea urchin", "sea anemone",
    "flatworm marine", "sea cucumber reef", "sea snail underwater", "feather star",
]
_TERMS_ALGAE = [
    "diatom", "microalgae", "phytoplankton", "dinoflagellate", "plankton microscope",
    "marine algae", "Bacillariophyta", "Isochrysis", "Tetraselmis", "algae microscope",
    "diatom movement", "dinoflagellate swimming", "phytoplankton microscopy",
    "Chlorophyta", "cyanobacteria marine", "seaweed underwater", "kelp",
]
# 심해 브랜드 유지용 기본(레거시 replenish 호환). deep_sea 검색어와 동일.
_TERMS = _TERMS_DEEP
# 수심 파싱(설명·위키 발췌에서 'N m'/'N-메터' 근사) — 없으면 빈 값.
_DEPTH = re.compile(r"(\d{2,5})\s*(?:m|메터|メートル|meters?|metres?)\b", re.I)
# 해양생물 확인(날조 방지와 별개 — '채널 주제 적합성'). 위키 발췌·설명에 아래 해양 단서가 있어야 채택.
_MARINE = re.compile(
    r"海|深海|魚類|甲殻|軟体動物|棘皮動物|刺胞動物|海綿|珊瑚|サンゴ|クラゲ|水母|タコ|イカ|"
    r"頭足|貝|エビ|カニ|ウニ|ヒトデ|ナマコ|イソギンチャク|プランクトン|"
    r"marine|\bsea\b|ocean|deep[- ]sea|abyssal|hydrotherm|\bfish\b|coral|crustacean|"
    r"mollus[ck]|cephalopod|echinoderm|cnidaria|jellyfish|aquatic|reef|benthic|"
    r"shrimp|crab|lobster|anemone|sponge|plankton|\bsquid\b|octopus", re.I)
# 채널 부적합(조류·파충류·양서류·곤충·육상식물·육상동물) 배제 — 해양 단서가 있어도 이게 있으면 스킵.
# ★일본어 분류군어도 포함(영어 'reptile'만으론 '爬虫綱·ヤモリ·トカゲ' 같은 육상 파충류를 못 걸러
#   도마뱀붙이(Gekko japonicus)가 후보로 새던 사고 → 위키 발췌의 일본어 분류군어까지 배제).
_EXCLUDE = re.compile(
    r"鳥類|鳥\b|海鳥|昆虫|植物|樹木|爬虫|両生|トカゲ|ヤモリ|ヘビ|蛇|カエル|蛙|イモリ|サンショウウオ|"
    r"蜘蛛|クモ\b|サソリ|ダニ|"
    r"\bbird\b|seabird|\binsect\b|\bplant\b|reptile|amphibian|\bgecko\b|\blizard\b|\bsnake\b|"
    r"\bfrog\b|\btoad\b|\bnewt\b|salamander|arachnid|araneae|scorpion|\bmite\b|\btick\b|"
    r"widow spider|black widow|tarantula|wolf spider|jumping spider|huntsman|"
    r"\bbeetle\b|\bmoth\b|butterfly|\bwasp\b", re.I)
# ★주의: 육상 거미만 배제하고 '바다거미(sea spider·ウミグモ=Pycnogonida)'는 채널 대상이라 남긴다.
#   그래서 바로 위 목록은 'widow spider'·'arachnid' 등 육상 거미 특정어만 넣고, 범용 'spider'는 넣지 않는다.
# ── 미세조류(marine_algae) 전용 게이트 ──
# 조류(藻類) '양성 확인': 아래 단서가 학명·영문명·위키 발췌 어딘가에 있어야 채택(동물 오채택 방지).
_ALGAE = re.compile(
    r"藻|珪藻|藍藻|渦鞭毛|植物プランクトン|海藻|微細藻|プランクトン|"
    r"\balgae?\b|algal|diatom|phytoplankton|dinoflagellate|cyanobacteria|"
    r"Bacillariophy|Chlorophy|Rhodophy|Phaeophy|Haptophy|Cryptophy|Euglenophy|"
    r"microalga|seaweed|\bkelp\b|Chromista|protist", re.I)
# 미세조류 후보에서 배제할 '동물' 단서(해양동물이라도 미세조류 카테고리엔 부적합).
_ANIMAL = re.compile(
    r"魚類|魚\b|甲殻|軟体動物|棘皮動物|刺胞動物|海綿|タコ|イカ|頭足|貝\b|エビ|カニ|ウニ|ヒトデ|ナマコ|"
    r"クラゲ|イソギンチャク|"
    r"\bfish\b|\bcrab\b|shrimp|lobster|octopus|\bsquid\b|cuttlefish|mollus[ck]|cephalopod|"
    r"echinoderm|cnidaria|jellyfish|anemone|sponge|\bcoral\b|\burchin\b|\bslug\b|"
    r"\banimal\b|Animalia|vertebrate|mammal", re.I)
# 피사체가 깔끔하지 않은 '연구·사체·해부·표본·양식장' 클립 배제(파일명·설명 기준). 생물 자체가 주인공인
# 영상만 채택해 그로테스크/비주제 화면을 막는다(사체 분해 실험 영상 등 자동 오채택 방지).
_BADCLIP = re.compile(
    r"carcass|decomp|dissect|necrops|autops|corpse|dead\b|rotting|bait|"
    r"fishing|caught|catch|market|aquarium tank|glass tank|fillet|cooking|recipe|"
    r"死骸|解剖|標本|養殖|釣り|市場", re.I)


def _get(api: str, **params) -> dict:
    """API GET(JSON). 간헐적 비-JSON·레이트리밋 대비 재시도. 실패 시 빈 dict."""
    import requests
    params.setdefault("format", "json")
    for attempt in range(3):
        try:
            r = requests.get(api, headers={"User-Agent": _UA}, params=params, timeout=30)
            if r.status_code == 200 and r.text.lstrip()[:1] in ("{", "["):
                return r.json()
        except Exception as e:  # noqa: BLE001
            log.debug("[discovery] GET 실패(%d) %s: %s", attempt, api, e)
        time.sleep(1.0 + attempt)
    return {}


def _strip(html: str) -> str:
    return re.sub("<[^>]+>", "", html or "").strip()


# ── Wikidata 분류군 해석 ──
def _wd_entity(qid: str) -> dict | None:
    d = _get(_WD, action="wbgetentities", ids=qid, props="labels|claims|sitelinks",
             languages="ko|en|ja")
    return d.get("entities", {}).get(qid)


def _taxon_from_entity(qid: str, ent: dict) -> dict | None:
    """Wikidata 항목이 분류군(P31=Q16521)이고 학명(P225)이 있으면 정체성 dict 반환."""
    claims = ent.get("claims", {}) or {}
    is_taxon = any(
        c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q16521"
        for c in claims.get("P31", []))
    if not is_taxon or "P225" not in claims:
        return None
    try:
        sci = claims["P225"][0]["mainsnak"]["datavalue"]["value"]
    except Exception:  # noqa: BLE001
        return None
    labels = {k: v["value"] for k, v in ent.get("labels", {}).items()}
    sit = ent.get("sitelinks", {}) or {}
    ko = labels.get("ko") or (sit.get("kowiki", {}) or {}).get("title")
    return {"qid": qid, "sci": sci, "ko": ko, "ja": labels.get("ja"),
            "en": labels.get("en"), "sitelinks": sit}


def _resolve_qid(qid: str) -> dict | None:
    ent = _wd_entity(qid)
    return _taxon_from_entity(qid, ent) if ent else None


def _search_taxon_by_name(name: str) -> dict | None:
    """이름(학명 후보)으로 Wikidata 검색 → 첫 분류군 항목."""
    d = _get(_WD, action="wbsearchentities", search=name, language="en", type="item", limit="5")
    for hit in d.get("search", []):
        got = _resolve_qid(hit["id"])
        if got:
            return got
    return None


def _wiki_extract(sitelinks: dict, lang: str) -> str | None:
    key = f"{lang}wiki"
    node = sitelinks.get(key)
    if not node:
        return None
    d = _get(f"https://{lang}.wikipedia.org/w/api.php", action="query", prop="extracts",
             exintro="1", explaintext="1", redirects="1", titles=node["title"])
    for p in d.get("query", {}).get("pages", {}).values():
        return (p.get("extract") or "").strip() or None
    return None


def _facts_from_wiki(sitelinks: dict) -> tuple[list[str], str]:
    """분류군 Wikipedia(일→영) 도입부 → 문장 단위 사실 리스트 + 출처 표기.
    출처 있는 실제 문장만 쓴다(날조 방지). 사실이 없으면 ([], '')."""
    for lang in ("ja", "en"):
        text = _wiki_extract(sitelinks, lang)
        if text and len(text) > 40:
            sents = re.split(r"(?<=[。.!?])\s+", text)
            facts = [s.strip() for s in sents if len(s.strip()) > 10][:5]
            src = f"Wikipedia ({lang})"
            if facts:
                return facts, src
    return [], ""


def _depth_from_text(*texts: str) -> str:
    nums = []
    for t in texts:
        for m in _DEPTH.finditer(t or ""):
            n = int(m.group(1))
            if 1 <= n <= 11000:
                nums.append(n)
    if not nums:
        return ""
    lo, hi = min(nums), max(nums)
    return f"{lo}-{hi}" if lo != hi else str(hi)


# ── Commons 후보 수집 ──
def _norm_license(text: str) -> str | None:
    t = (text or "").strip().lower()
    # ★NC(비상업) 차단(하드룰): 'cc by'가 'cc by-nc'의 부분일치라 먼저 걸러야 오통과를 막는다.
    if "nc" in t and ("by-nc" in t or "by nc" in t or "noncommercial" in t or "non-commercial" in t):
        return None
    if not any(a in t for a in _ALLOWED):
        return None
    if "cc0" in t or "zero" in t:
        return "cc0"
    if "public" in t or t == "pd":
        return "public-domain"
    if "kogl" in t:
        return "kogl-type1"
    if "sa" in t and ("by-sa" in t or "by sa" in t):
        return "cc-by-sa"
    return "cc-by"


def _search_titles(exclude_titles: set[str], per_term: int = 12,
                   terms: list[str] | None = None, filetype: str = "video",
                   ext: tuple = _VIDEO_EXT) -> list[str]:
    titles: list[str] = []
    seen = set(t.lower() for t in exclude_titles)
    for term in (terms or _TERMS):
        d = _get(_COMMONS, action="query", list="search",
                 srsearch=f"{term} filetype:{filetype}", srnamespace="6", srlimit=str(per_term))
        for h in d.get("query", {}).get("search", []):
            t = h.get("title", "")
            if (t.lower().endswith(ext) and t.lower() not in seen
                    and t not in titles):
                titles.append(t)
    return titles


def _identity_for(pageid: str, title: str, desc: str) -> dict | None:
    """정체성 해석: ① 구조화데이터 P180 → Wikidata, ② 파일명·설명 학명 파싱 → Wikidata 검색."""
    # ① 구조화데이터(depicts)
    try:
        sd = _get(_COMMONS, action="wbgetentities", ids=f"M{pageid}")
        ent = sd.get("entities", {}).get(f"M{pageid}", {})
        statements = ent.get("statements", ent.get("claims", {})) or {}
        for st in statements.get("P180", []):
            dv = st.get("mainsnak", {}).get("datavalue", {}).get("value", {})
            qid = dv.get("id") if isinstance(dv, dict) else None
            if qid:
                got = _resolve_qid(qid)
                if got:
                    return got
    except Exception:  # noqa: BLE001
        pass
    # ② 파일명·설명 학명(이명법) 파싱 → Wikidata 검색
    base = re.sub(r"^File:", "", title)
    names, seen = [], set()
    for m in _BINOMIAL.finditer(base + " " + (desc or "")):
        nm = f"{m.group(1)} {m.group(2)}"
        if nm.lower() not in seen:
            seen.add(nm.lower())
            names.append(nm)
    for nm in names[:3]:
        got = _search_taxon_by_name(nm)
        if got:
            return got
    return None


def discover(exclude_scinames: set[str], exclude_titles: set[str], want: int = 3,
             validate=None, terms: list[str] | None = None,
             exclude_re: "re.Pattern | None" = None,
             require_re: "re.Pattern | None" = None, media: str = "video") -> list[dict]:
    """새 해양생물 소재 후보를 발굴해 '제작 가능한 종 레코드' 리스트를 반환(최대 want개).

    validate(url) -> bool : 실사 다운로드+게이트(정지·카드) 검증 콜백(있으면 통과분만 채택).
    terms       : 카테고리별 검색어(없으면 심해 기본 _TERMS).
    exclude_re  : 부적합 분류군 배제 정규식(없으면 육상동물 _EXCLUDE).
    require_re  : 양성 확인 정규식(있으면 학명·영문명·위키에 이 단서가 있어야 채택 — 미세조류용).
    media       : "video"=실사 영상. "photo"=고해상 사진(제작 시 켄번즈로 영상화 — 정적 피사체용).
    반환 각 항목 = {key, footage:{...}, species:{...}}  (footage._SEED / data.SPECIES 호환).
    """
    exclude_re = exclude_re or _EXCLUDE
    is_photo = media == "photo"
    ftype, fext = ("bitmap", _IMG_EXT) if is_photo else ("video", _VIDEO_EXT)
    excl_sci = {s.strip().lower() for s in exclude_scinames if s}
    titles = _search_titles(exclude_titles, terms=terms, filetype=ftype, ext=fext)
    log.info("[discovery] Commons 영상 후보 %d개 수집 → 정체성·사실·게이트 검증", len(titles))
    out: list[dict] = []
    for i in range(0, len(titles), 10):
        if len(out) >= want:
            break
        batch = titles[i:i + 10]
        info = _get(_COMMONS, action="query", prop="imageinfo", titles="|".join(batch),
                    iiprop="url|size|extmetadata",
                    iiextmetadatafilter="LicenseShortName|Artist|ImageDescription")
        for pid, page in info.get("query", {}).get("pages", {}).items():
            if len(out) >= want or int(pid) <= 0:
                continue
            ii = (page.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            lic = _norm_license(em.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            w, h = ii.get("width", 0), ii.get("height", 0)
            if not (lic and url and url.lower().endswith(fext)):
                continue
            if is_photo:                       # 사진: 켄번즈 확대 여유 위해 고해상만
                if not (w >= 1200 and h >= 800):
                    continue
            else:                              # 영상: 9:16/16:9 규격(레터박스 방지)
                ar = (w / h) if h else 0
                if not (1.55 <= ar <= 1.95):
                    continue
            title = page.get("title", "")
            desc = _strip(em.get("ImageDescription", {}).get("value", ""))
            if _BADCLIP.search(title + " " + desc):   # 연구·사체·해부·양식 클립 배제(피사체 부적합)
                continue
            ident = _identity_for(pid, title, desc)
            if not ident or not ident.get("sci"):
                continue
            sci = ident["sci"].strip()
            if sci.lower() in excl_sci or any(o["key"] == sci.lower() for o in out):
                continue
            facts, fact_src = _facts_from_wiki(ident["sitelinks"])
            if not facts:                       # 사실 없으면 스킵(날조 금지)
                log.info("[discovery] 사실 미확보로 스킵: %s", sci)
                continue
            # 채널 주제 적합성: 조류·파충류·양서류·곤충·육상식물 등 명백한 비해양만 배제한다.
            # ★'해양 단서 필수'는 폐지: _MARINE 키워드 화이트리스트가 불완전해 アメフラシ(바다토끼) 같은
            #   실제 해양생물을 오배제하던 문제가 있었다. 소싱 검색어 자체가 해양 중심이고 운영자 검토가
            #   있으므로, 재현율을 지키기 위해 _EXCLUDE(명백한 육상동물)로만 거른다.
            blob = " ".join(facts) + " " + desc
            if exclude_re.search(blob):
                log.info("[discovery] 부적합 분류군으로 스킵: %s", sci)
                continue
            # ★양성 확인(미세조류 등): 학명·영문명·위키 어디에도 요구 단서가 없으면 스킵(동물 오채택 방지).
            if require_re is not None and not require_re.search(
                    blob + " " + sci + " " + (ident.get("en") or "") + " " + (ident.get("ja") or "")):
                log.info("[discovery] 카테고리 양성단서 미확인으로 스킵: %s", sci)
                continue
            if validate and not validate(url):  # 실사 게이트(정지·카드 등)
                log.info("[discovery] 실사 게이트 탈락으로 스킵: %s", sci)
                continue
            artist = _strip(em.get("Artist", {}).get("value", ""))
            credit = artist or "Wikimedia Commons"
            if lic == "cc-by-sa":
                credit = f"{credit} · CC BY-SA"
            elif lic == "cc-by":
                credit = f"{credit} · CC BY"
            ko = ident.get("ko") or ident.get("en") or sci
            en = ident.get("en") or sci
            depth = _depth_from_text(desc, " ".join(facts))
            fp = {"url": url, "license": lic, "credit": credit, "source": title}
            if is_photo:   # 사진 → 제작 시 켄번즈로 영상화
                fp["media_kind"] = "photo"
                fp["image_url"] = url
            out.append({
                "key": sci.lower(),
                "footage": fp,
                "species": {
                    "scientific_name": sci, "common_name_ko": ko, "common_name_en": en,
                    "depth_range_m": depth, "distribution": "", "habitat": "",
                    "diet": [], "fun_facts": facts,
                    "sources": [fact_src, f"Wikimedia Commons ({title})"],
                },
            })
            log.info("[discovery] 채택: %s (ko=%s ja=%s, %s)", sci, ko, ident.get("ja"), lic)
    return out


# ── 침몰선(난파선) 소싱 — 학명이 없어 정체성 경로가 다르다(제목·설명·구조화데이터 → 운영자 확인) ──
_WRECK_TERMS = ["wreck dive", "shipwreck underwater", "wreck diving", "sunken ship",
                "ship wreck scuba", "underwater wreck", "wreck scuba", "shipwreck diving",
                "sunken wreck", "wreck of", "SS wreck", "submarine wreck dive",
                "sunken ship diver", "沈没船", "難破船", "épave plongée"]
# 배 이름 파싱: "wreck of X" / "SS X" 등. 오탐(Museum 등)은 _WRECK_BAD로 컷.
_WRECK_NAME = re.compile(
    r"(?:wreck of (?:the )?|wreck |난파선\s*|epave (?:du |de la |le )?|naufr[aá]gio (?:do |da )?)"
    r"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){0,2})"
    r"|\b((?:SS|HMS|USS|MV|RMS|MS|HMAS)\s+[A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){0,2})"
    r"|\b(U-?\d{2,4})")   # U-보트는 반드시 번호(U-1277) — 'U S Navy'가 'U S'로 잡히던 오탐 차단
# 느슨한 이름 추출용 잡음어(선박 명이 아닌 일반·지명·제목상투어). 이 단어들은 이름에서 걸러낸다.
_WRECK_NOISE = {
    "wreck", "wrecks", "diving", "dive", "dives", "diver", "divers", "underwater", "under", "water",
    "best", "sea", "black", "red", "ocean", "in", "of", "the", "a", "an", "and", "at", "on", "to",
    "with", "part", "video", "footage", "scuba", "cargo", "ship", "boat", "vessel", "sunken", "sunk",
    "portugal", "porto", "santo", "madeira", "spain", "italy", "greece", "atlantic", "france",
    "pacific", "mediterranean", "coast", "bay", "island", "reef", "deep", "meter", "meters",
    "metre", "metres", "day", "hd", "gopro", "final", "new", "old", "great", "big", "site",
    "first", "look", "world", "war", "wwii", "wwi", "navy", "eod", "ordnance", "removes",
    "north", "south", "east", "west", "off", "near", "from", "gulf", "lake", "river", "wreckage",
    "shipwreck", "shipwrecks", "ii", "iii", "nc", "ss", "uss", "hms", "hmas", "mv", "rms",
}
# 명백한 비-선명(제목 상투어 조합) — 느슨 추출 결과가 이거면 버린다(운영자 검토 부담 경감).
_WRECK_JUNK = {"first look", "u s", "world war", "wreck diving", "scuba diving", "mise"}


def _plausible_wreck_name(name: str) -> bool:
    """추출된 이름이 배 이름다운지 최소 검증(잡음 조합·너무 짧음 배제)."""
    n = (name or "").strip()
    if len(n.replace(" ", "")) < 3 or n.lower() in _WRECK_JUNK:
        return False
    toks = [t for t in n.split() if t]
    return any(len(t) >= 3 and t.lower() not in _WRECK_NOISE for t in toks)


def _wreck_name_from_title(title: str, desc: str = "") -> str:
    """제목에서 배 이름을 최선 추출(needs_confirm=True — 운영자가 최종 확인/수정).
    ① 'wreck of X'·'SS/HMS/U-… X' 강한 패턴 ② 없으면 제목의 '연속된 고유명사 구간'(잡음어 제외).
    실제 결함: 강한 접두사만 보다가 'Madeirense'·'Jacques Fraissinet' 같은 실제 제목을 전부 놓쳐
    침몰선 소싱이 0건이었다. 접두사 없이도 이름 후보를 뽑아 소싱이 되게 한다."""
    base = re.sub(r"^File:", "", title or "")
    base = re.sub(r"\.(webm|ogv|ogg|mp4|mov|jpg|jpeg|png)$", "", base, flags=re.I)
    m = _WRECK_NAME.search(base)
    if m:
        nm = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        if _plausible_wreck_name(nm):
            return nm
    # 느슨: 연속된 대문자 시작 토큰(잡음어 제외) 중 가장 긴 구간(최대 3어절)을 이름으로 본다.
    run: list[str] = []
    best: list[str] = []
    for w in re.findall(r"\S+", base):
        cw = re.sub(r"[^A-Za-z'’\-]", "", w)
        if cw and cw[0].isupper() and cw.lower() not in _WRECK_NOISE and len(cw) >= 3:
            run.append(cw)
            if len(run) > len(best):
                best = run[:]
        else:
            run = []
    nm = " ".join(best[:3]).strip()
    return nm if _plausible_wreck_name(nm) else ""


_WRECK_TYPE = re.compile(
    r"cargo ship|화물선|貨物船|passenger|여객선|submarine|잠수함|潜水艦|U-?boat|Uボート|"
    r"tanker|유조선|warship|군함|軍艦|destroyer|frigate|trawler|어선|ferry|bulk carrier", re.I)
_WRECK_BAD = re.compile(r"museum|박물관|\bmodel\b|모형|replica|game|simulator|minecraft", re.I)
_SHIP_QIDS = ("Q852190", "Q11446", "Q1229765", "Q17205621")  # shipwreck·ship·watercraft·상선 등
_IMG_EXT = (".jpg", ".jpeg", ".png")
# ★난파선 무한 소싱(운영자 확정) — 사진은 영상보다 수천 배 많다. Tier2용 사진 검색어.
_WRECK_PHOTO_TERMS = ["shipwreck underwater", "wreck dive underwater", "sunken ship underwater",
                      "shipwreck scuba diving", "underwater shipwreck", "wreck diving site",
                      "épave sous-marine", "pecio submarino", "沈船 水中"]
# Tier1 영상 확대용 카테고리(직접 영상 파일 보유). Tier3 명명 레지스트리는 by-ship-name 순회.
_WRECK_VIDEO_CATS = ["Wreck diving", "Shipwreck diving sites", "Underwater videos of shipwrecks"]
_WRECK_REGISTRY_CAT = "Shipwrecks by ship name"


def _wreck_identity(pid: str, title: str, desc: str) -> dict | None:
    """침몰선 정체성(약한 확신 — 운영자 확인 전제): 배 이름·선종·수심을 최선 추출.
    ① 구조화데이터 depicts→Wikidata 배/난파선 항목(있으면 위키 사실까지) ② 제목의 배 이름.
    확인 가능한 게 하나도 없으면 None(완전 불명은 후보에서 제외)."""
    name = name_ja = None
    facts: list[str] = []
    fact_src = ""
    # ① depicts → Wikidata 배/난파선
    try:
        sd = _get(_COMMONS, action="wbgetentities", ids=f"M{pid}")
        ent = sd.get("entities", {}).get(f"M{pid}", {})
        st = ent.get("statements", ent.get("claims", {})) or {}
        for s in st.get("P180", []):
            q = s.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
            if not q:
                continue
            e = _wd_entity(q)
            if not e:
                continue
            inst = [c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                    for c in (e.get("claims", {}) or {}).get("P31", [])]
            if any(x in _SHIP_QIDS for x in inst):
                labs = e.get("labels", {})
                name = (labs.get("en", {}) or {}).get("value") or (labs.get("ja", {}) or {}).get("value")
                name_ja = (labs.get("ja", {}) or {}).get("value")
                facts, fact_src = _facts_from_wiki(e.get("sitelinks", {}) or {})
                break
    except Exception:  # noqa: BLE001
        pass
    # ② 제목의 배 이름(강한 패턴 → 느슨한 고유명사 구간). needs_confirm=True라 운영자가 최종 확인.
    if not name:
        name = _wreck_name_from_title(title, desc) or None
    if not name:
        return None
    tm = _WRECK_TYPE.search(title + " " + (desc or ""))
    depth = _depth_from_text(title, desc, " ".join(facts))
    return {"name": name, "name_ja": name_ja, "facts": facts, "fact_src": fact_src,
            "ship_type": tm.group(0) if tm else "", "depth": depth}


def _catmembers(cat: str, cmtype: str, limit: int = 200) -> list[str]:
    """Commons 카테고리 멤버(file 또는 subcat) 제목 리스트."""
    d = _get(_COMMONS, action="query", list="categorymembers", cmtitle=f"Category:{cat}",
             cmtype=cmtype, cmlimit=str(limit))
    return [m.get("title", "") for m in d.get("query", {}).get("categorymembers", [])]


def _wreck_search_titles(terms: list[str], ext: tuple, filetype: str, per: int = 30) -> list[str]:
    """검색어들로 Commons에서 파일 제목 수집(영상/사진). ext=허용 확장자."""
    seen: dict[str, int] = {}
    for term in terms:
        d = _get(_COMMONS, action="query", list="search",
                 srsearch=f"{term} filetype:{filetype}", srnamespace="6", srlimit=str(per))
        for h in d.get("query", {}).get("search", []):
            t = h.get("title", "")
            if t.lower().endswith(ext):
                seen[t] = 1
    return list(seen)


def _cands_from_titles(titles: list[str], exclude: set[str], want: int,
                       media_kind: str, out_keys: set[str]) -> list[dict]:
    """파일 제목들 → 침몰선 후보(라이선스·(영상만)종횡비·이름·오탐 게이트). media_kind=video|photo."""
    out: list[dict] = []
    is_video = media_kind == "video"
    ext = _VIDEO_EXT if is_video else _IMG_EXT
    for i in range(0, len(titles), 20):
        if len(out) >= want:
            break
        info = _get(_COMMONS, action="query", prop="imageinfo", titles="|".join(titles[i:i + 20]),
                    iiprop="url|size|extmetadata",
                    iiextmetadatafilter="LicenseShortName|Artist|ImageDescription")
        for pid, page in info.get("query", {}).get("pages", {}).items():
            if len(out) >= want or int(pid) <= 0:
                continue
            ii = (page.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            lic = _norm_license(em.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            w, h = ii.get("width", 0), ii.get("height", 0)
            if not (lic and url and url.lower().endswith(ext)):
                continue
            if is_video:
                ar = (w / h) if h else 0
                if not (1.55 <= ar <= 1.95):
                    continue
            elif not (w >= 1200 and h >= 800):   # 사진은 켄번즈 확대 여유 위해 고해상만
                continue
            title = page.get("title", "")
            desc = _strip(em.get("ImageDescription", {}).get("value", ""))
            if _WRECK_BAD.search(title + " " + desc) or _BADCLIP.search(title + " " + desc):
                continue
            ident = _wreck_identity(pid, title, desc)
            if not ident:
                continue
            key = f"wreck {ident['name'].strip()}".lower()
            if key in exclude or key in out_keys or any(o["key"] == key for o in out):
                continue
            artist = _strip(em.get("Artist", {}).get("value", ""))
            credit = artist or "Wikimedia Commons"
            credit += " · CC BY-SA" if lic == "cc-by-sa" else (" · CC BY" if lic == "cc-by" else "")
            cand = {
                "kind": "wreck", "key": key, "needs_confirm": True, "media_kind": media_kind,
                "title": title, "url": url, "license": lic, "credit": credit, "source": title,
                "name": ident["name"], "name_ja": ident.get("name_ja") or "",
                "ship_type": ident.get("ship_type", ""), "depth": ident.get("depth", ""),
                "facts": ident.get("facts", []), "fact_src": ident.get("fact_src", ""),
                "desc": desc[:300],
            }
            if not is_video:
                cand["image_url"] = url
            out.append(cand)
            out_keys.add(key)
            log.info("[discovery] 침몰선 후보(%s): %s (%s)", media_kind, ident["name"], lic)
    return out


def _registry_candidates(exclude: set[str], want: int, out_keys: set[str]) -> list[dict]:
    """Tier3: 'Shipwrecks by ship name' 하위(배 이름별)를 순회 → 실존 명명 난파선.
    각 하위 카테고리 = 확인된 배 이름. 그 배의 파일(사진/영상)에서 첫 통과 소스를 후보로."""
    subs = _catmembers(_WRECK_REGISTRY_CAT, cmtype="subcat", limit=200)
    out: list[dict] = []
    for sub in subs:
        if len(out) >= want:
            break
        name = re.sub(r"^Category:", "", sub).strip()
        key = f"wreck {name}".lower()
        if not name or key in exclude or key in out_keys or any(o["key"] == key for o in out):
            continue
        files = _catmembers(sub, cmtype="file", limit=30)
        vids = [f for f in files if f.lower().endswith(_VIDEO_EXT)]
        imgs = [f for f in files if f.lower().endswith(_IMG_EXT)]
        # 그 배 자체의 파일이므로 이름 게이트는 이미 통과 — 영상 우선, 없으면 고해상 사진.
        for cand_list, mk in ((vids, "video"), (imgs, "photo")):
            if not cand_list:
                continue
            got = _cands_from_titles(cand_list[:8], exclude, 1, mk, set())
            if got:
                c = got[0]
                c["key"] = key            # 배 이름(레지스트리)을 정식 키로 고정
                c["name"] = name
                if not c.get("facts"):
                    c["facts"], c["fact_src"] = _wiki_intro_by_name(name)
                out.append(c)
                out_keys.add(key)
                log.info("[discovery] 침몰선 레지스트리 후보: %s (%s)", name, mk)
                break
    return out


def _wiki_intro_by_name(name: str) -> tuple[list[str], str]:
    """배 이름으로 Wikipedia(영) 도입부 사실 확보(있으면). 없으면 ([], '')."""
    for lang in ("en", "ja"):
        d = _get(f"https://{lang}.wikipedia.org/w/api.php", action="query", prop="extracts",
                 exintro="1", explaintext="1", redirects="1", titles=name)
        for p in d.get("query", {}).get("pages", {}).values():
            if int(p.get("pageid", 0) or 0) <= 0:
                continue
            text = (p.get("extract") or "").strip()
            if text and len(text) > 40:
                sents = re.split(r"(?<=[。.!?])\s+", text)
                facts = [s.strip() for s in sents if len(s.strip()) > 10][:5]
                if facts:
                    return facts, f"Wikipedia ({lang})"
    return [], ""


def _discover_wrecks(exclude_keys: set[str], want: int) -> list[dict]:
    """침몰선 무한 소싱(운영자 확정 3단):
    Tier1 영상(검색+카테고리) → Tier3 배이름 레지스트리(명명·사실) → Tier2 사진(켄번즈, 무한).
    영상·명명 우선(품질), 부족분은 사진으로 무한 보충. 모두 needs_confirm=True(운영자 확인)."""
    out_keys: set[str] = set()
    out: list[dict] = []
    # Tier1: 영상 검색 + 영상 보유 카테고리 순회
    vtitles = _wreck_search_titles(_WRECK_TERMS, _VIDEO_EXT, "video", per=40)
    for cat in _WRECK_VIDEO_CATS:
        vtitles += [t for t in _catmembers(cat, cmtype="file", limit=200)
                    if t.lower().endswith(_VIDEO_EXT)]
    out += _cands_from_titles(list(dict.fromkeys(vtitles)), exclude_keys, want, "video", out_keys)
    # Tier3: 배이름 레지스트리(명명 난파선 + 위키 사실)
    if len(out) < want:
        out += _registry_candidates(exclude_keys, want - len(out), out_keys)
    # Tier2: 사진 → 켄번즈(무한 공급)
    if len(out) < want:
        ptitles = _wreck_search_titles(_WRECK_PHOTO_TERMS, _IMG_EXT, "bitmap", per=40)
        out += _cands_from_titles(ptitles, exclude_keys, want - len(out), "photo", out_keys)
    return out[:want]


# ── 카테고리별 발굴 설정(핵심 수정) — 각 카테고리가 고유 검색어·게이트를 갖는다 ──
# terms=검색어, exclude=배제 분류군, require=양성 확인(없으면 None). shipwreck은 별도 경로.
_CATALOG = {
    "deep_sea":     {"terms": _TERMS_DEEP,   "exclude": _EXCLUDE, "require": None, "photo": False},
    "marine_life":  {"terms": _TERMS_MARINE, "exclude": _EXCLUDE, "require": None, "photo": False},
    # 미세조류: 동물 배제 + 조류 양성 확인(동물 카테고리의 'plant 배제'는 적용 안 함).
    # ★photo=True: 미세조류는 현미경 정지사진이 많고 대상도 거의 안 움직여 켄번즈가 잘 맞는다 →
    #   영상이 부족하면 사진 후보(media_kind=photo)로 보충(제작 시 fetch_footage가 켄번즈 영상화).
    "marine_algae": {"terms": _TERMS_ALGAE,  "exclude": _ANIMAL,  "require": _ALGAE, "photo": True},
}


def _rec_to_candidate(r: dict) -> dict:
    """discover() 레코드 → 후보 dict(사진이면 media_kind/image_url 승계)."""
    sp = r["species"]
    fp = r["footage"]
    c = {
        "kind": "creature", "key": r["key"], "needs_confirm": False,
        "title": fp["source"], "url": fp["url"],
        "license": fp["license"], "credit": fp["credit"], "source": fp["source"],
        "name": sp["scientific_name"], "name_ja": "",
        "common_name_ko": sp["common_name_ko"], "common_name_en": sp["common_name_en"],
        "depth": sp["depth_range_m"], "facts": sp["fun_facts"], "fact_src": (sp["sources"] or [""])[0],
        "species": sp,
    }
    if fp.get("media_kind") == "photo":
        c["media_kind"] = "photo"
        c["image_url"] = fp.get("image_url") or fp["url"]
    return c


def discover_candidates(category_id: str, want: int = 6, exclude_keys: set[str] | None = None) -> list[dict]:
    """관리자 '소싱하기'용 후보 목록(메타 수준 — 다운로드 안 함, 워크플로가 게이트·썸네일 담당).
    생물 카테고리=학명·사실 자동확보 후보, shipwreck=배 이름·선종 최선추출(needs_confirm).
    ★카테고리마다 고유 검색어·분류 게이트를 써서 '엉뚱한 종·중복'을 막는다.
    ★photo=True 카테고리(미세조류)는 영상 부족 시 고해상 사진으로 보충(켄번즈 영상화)."""
    exclude_keys = {k.strip().lower() for k in (exclude_keys or set())}
    if category_id == "shipwreck":
        return _discover_wrecks(exclude_keys, want)
    # 생물: 카테고리 설정으로 검색어·게이트 지정(미지정 카테고리는 심해 기본)
    cfg = _CATALOG.get(category_id, _CATALOG["deep_sea"])
    recs = discover(exclude_keys, set(), want=want, validate=None,
                    terms=cfg["terms"], exclude_re=cfg["exclude"], require_re=cfg["require"])
    cands = [_rec_to_candidate(r) for r in recs]
    # 사진 보충(미세조류 등): 영상이 want에 못 미치면 고해상 사진 후보로 채운다.
    if cfg.get("photo") and len(cands) < want:
        excl = exclude_keys | {c["key"] for c in cands}
        precs = discover(excl, set(), want=want - len(cands), validate=None,
                         terms=cfg["terms"], exclude_re=cfg["exclude"], require_re=cfg["require"],
                         media="photo")
        cands += [_rec_to_candidate(r) for r in precs]
    return cands


def make_thumbnail(url: str, out_jpg: str, tmp_dir: str) -> bool:
    """후보 영상 URL을 내려받아 '피사체가 잘 보이는 대표 프레임' 1장을 out_jpg로 저장(검토 미리보기용).
    실패 시 False. 다운로드본은 남겨 재사용 가능(정리는 호출측)."""
    import hashlib
    import subprocess
    from src.core import footage
    from src.core.longform import thumbnail as TH
    is_img = url.lower().endswith(_IMG_EXT)
    ext = (next((e for e in _IMG_EXT if url.lower().endswith(e)), ".jpg") if is_img
           else next((e for e in _VIDEO_EXT if url.lower().endswith(e)), ".webm"))
    # ★임시 파일명은 URL별 고유(해시)로 만든다. 고정 이름(_thumb_src)이면 여러 후보가 첫 후보의
    #   영상을 캐시로 재사용해 '모든 후보 썸네일이 동일'해지던 버그가 있었다(재발 방지).
    h = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
    src = Path(tmp_dir) / f"_thumb_{h}{ext}"
    min_sz = 20_000 if is_img else 100_000
    try:
        if not (src.exists() and src.stat().st_size > min_sz) and not footage._download(url, src):
            return False
        if is_img:   # ★사진 후보(난파선): 이미지를 그대로 미리보기 jpg로 변환(비디오 프레임 추출 아님)
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                                "-vf", "scale=640:-1", "-frames:v", "1", out_jpg], timeout=60)
            return r.returncode == 0 and Path(out_jpg).exists()
        TH.pick_hero_frame(str(src), out_jpg)
        return Path(out_jpg).exists()
    except Exception as e:  # noqa: BLE001
        log.warning("[discovery] 썸네일 생성 실패(%s): %s", url, e)
        return False


def validate_source_url(url: str, tmp_dir: str) -> bool:
    """발굴 후보 URL을 실제로 내려받아 품질 게이트를 통과하는지 검증.
    영상=종횡비·정지영상 게이트. ★사진(난파선 켄번즈 소스)=고해상 이미지인지만 확인
    (사진은 당연히 '정지'라 정지-게이트를 적용하면 안 된다 → 켄번즈로 영상화하므로 OK)."""
    from src.core import footage
    is_img = url.lower().endswith(_IMG_EXT)
    ext = (next((e for e in _IMG_EXT if url.lower().endswith(e)), ".jpg") if is_img
           else next((e for e in _VIDEO_EXT if url.lower().endswith(e)), ".webm"))
    dest = Path(tmp_dir) / f"_probe{ext}"
    try:
        if not footage._download(url, dest):
            return False
        dim = footage._probe_dim(str(dest))
        if is_img:   # 사진: 켄번즈 확대 여유 위해 고해상만 통과(정지 게이트 미적용)
            return bool(dim and dim[0] >= 1200 and dim[1] >= 800)
        if dim and dim[1] and not (1.55 <= dim[0] / dim[1] <= 1.95):
            return False
        from src.core import watermark_qc as wq
        if wq.is_static_source(str(dest)):
            return False
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("[discovery] 검증 오류(%s): %s", url, e)
        return False
    finally:
        try:
            dest.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass


# ── 영속화 + 로더(카테고리별 discovered.json) ──
_DISCOVERED_DIR = Path(__file__).resolve().parents[1] / "categories"


def _path(category_id: str) -> Path:
    return _DISCOVERED_DIR / category_id / "discovered.json"


def load_discovered(category_id: str) -> list[dict]:
    """discovered.json 로드(없으면 []). footage/data가 import 시 병합에 사용(무거운 import 없음)."""
    p = _path(category_id)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_discovered(category_id: str, items: list[dict]) -> None:
    p = _path(category_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 소싱 후보(검토 대기) 영속화 — 승인 전 목록. 승인 시 discovered.json(생물)/shipwreck 풀로 이동 ──
def _cand_path(category_id: str) -> Path:
    return _DISCOVERED_DIR / category_id / f"{category_id}_candidates.json"


def load_candidates(category_id: str) -> list[dict]:
    p = _cand_path(category_id)
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else []
    except Exception:  # noqa: BLE001
        return []


def save_candidates(category_id: str, items: list[dict]) -> None:
    p = _cand_path(category_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _all_known_keys() -> set[str]:
    """전 카테고리의 후보·승인·시드 키를 합친 집합(교차 카테고리 중복 방지용).
    ★같은 종이 여러 카테고리에 동시에 잡혀 '중복 미리보기'가 되던 문제를 막는다."""
    keys: set[str] = set()
    try:
        for d in _DISCOVERED_DIR.iterdir():
            if not d.is_dir():
                continue
            cid = d.name
            keys |= {c["key"] for c in load_candidates(cid)}
            keys |= {it["key"] for it in load_discovered(cid)}
    except Exception:  # noqa: BLE001
        pass
    try:
        from src.core import footage as _f
        keys |= {k.lower() for k in _f.seeded_keys()}
    except Exception:  # noqa: BLE001
        pass
    return keys


def source_to_candidates(category_id: str, want: int = 6, validate=None) -> list[dict]:
    """'소싱하기'가 호출: 새 후보를 발굴해 (선택) 실사 게이트로 거른 뒤 후보 파일에 저장.
    이미 후보/승인된 대상은 제외(전 카테고리 교차 중복까지). 반환 = 이번에 추가된 후보 목록."""
    existing = load_candidates(category_id)
    # ★전 카테고리 키를 제외 → 같은 종이 여러 카테고리에 중복 소싱되지 않게 한다.
    excl = _all_known_keys()
    excl |= {c["key"] for c in existing}
    found = discover_candidates(category_id, want=want, exclude_keys=excl)
    if validate:
        found = [c for c in found if validate(c["url"])]
    if not found:
        return []
    save_candidates(category_id, existing + found)
    return found


# 선종 영문/한국어 → 일본어(확인된 것만 표기). 없으면 일반어 '船'.
_SHIP_JA = {"cargo": "貨物船", "화물선": "貨物船", "submarine": "潜水艦", "잠수함": "潜水艦",
            "u-boat": "潜水艦", "uボート": "潜水艦", "tanker": "タンカー", "유조선": "タンカー",
            "passenger": "客船", "여객선": "客船", "ferry": "フェリー", "warship": "軍艦",
            "군함": "軍艦", "destroyer": "駆逐艦", "frigate": "フリゲート", "trawler": "漁船", "어선": "漁船"}


def _wreck_copy(name: str, name_ja: str, ship_type: str, depth: str) -> dict:
    """침몰선 승인 후보의 일본어 카피(敬体)를 결정론적으로 생성. ★날조 금지: 확인된 이름·선종·수심만
    쓰고, 미확인 역사(톤수·침몰연도·사연)는 절대 지어내지 않는다. 나머지는 일반적·정직한 표현."""
    jp_name = (name_ja or "").strip() or f"沈没船「{name}」"
    tja = ""
    tl = (ship_type or "").strip().lower()
    for k, v in _SHIP_JA.items():
        if k in tl:
            tja = v
            break
    subj = tja or "船"
    feat = f"海の命が集う、沈んだ{subj}"
    body = ["青い海の底に、", "静かに横たわる、", "大きな影。", "その正体は、", "沈没船です。"]
    if tja:
        body += [f"かつては、", f"海をゆく{tja}。"]
    if depth:
        body += ["水深、", f"{depth}メートル。"]
    body += ["長い時間をかけて、", "船体には、", "生き物が棲みつきました。", "魚が集まり、",
             "海藻がゆれる。", "沈んだ船は、", "新しい命の、", "すみかです。",
             "海に還った、", "静かな船です。"]
    return {"jp_name": jp_name, "hook_line1": "海の底に、", "hook_line2": "眠る船。",
            "pop_words": ["海の底に、", "眠る船。"], "feature_line": feat, "feature_glow_word": "命",
            "hook_ko": "바다 밑에, 잠든 배.", "feature_ko": f"바다 생명이 모이는, 가라앉은 배",
            "tags": ["#沈没船", "#難破船", "#海"], "tags_ko": ["#난파선", "#침몰선", "#바다"],
            "body": body}


def promote_candidate(category_id: str, key: str) -> bool:
    """검토 승인된 후보를 '제작 가능한 풀'로 승격(생물=discovered.json, 침몰선=shipwreck discovered.json).
    승격 후 candidates에서 제거. 이미 풀에 있으면 True(멱등). 없으면 False."""
    key = (key or "").strip().lower()
    cands = load_candidates(category_id)
    cand = next((c for c in cands if c["key"] == key), None)
    if cand is None:
        # 이미 승격됐으면 성공으로 간주
        return any(it["key"] == key for it in load_discovered(category_id))
    disc = load_discovered(category_id)
    if not any(it["key"] == key for it in disc):
        if cand["kind"] == "wreck":
            nm = cand.get("name") or key
            # ★사진 소스(무한 엔진)는 media_kind=photo + image_url을 실어 fetch_footage가 켄번즈로 영상화.
            fp = {"url": cand["url"], "license": cand["license"],
                  "credit": cand["credit"], "source": cand["source"]}
            if cand.get("media_kind") == "photo":
                fp["media_kind"] = "photo"
                fp["image_url"] = cand.get("image_url") or cand["url"]
            entry = {
                "key": key, "kind": "wreck",
                "footage": fp,
                "subject": {
                    "scientific_name": f"Wreck {nm}", "common_name_ko": f"{nm} 난파선",
                    "common_name_en": f"Wreck {nm}", "depth_range_m": cand.get("depth", ""),
                    "distribution": "", "habitat": "침몰선", "diet": [],
                    "fun_facts": cand.get("facts", []) or [f"바다에 가라앉은 배입니다"],
                    "sources": [cand.get("fact_src", ""), f"Wikimedia Commons ({cand['source']})"]},
                "copy": _wreck_copy(nm, cand.get("name_ja", ""), cand.get("ship_type", ""),
                                    cand.get("depth", "")),
            }
        else:
            cfp = {"url": cand["url"], "license": cand["license"],
                   "credit": cand["credit"], "source": cand["source"]}
            if cand.get("media_kind") == "photo":   # 사진 생물(미세조류 등) → 켄번즈 영상화
                cfp["media_kind"] = "photo"
                cfp["image_url"] = cand.get("image_url") or cand["url"]
            entry = {"key": key, "kind": "creature", "footage": cfp, "species": cand["species"]}
        save_discovered(category_id, disc + [entry])
    save_candidates(category_id, [c for c in cands if c["key"] != key])
    return True


def replenish(category_id: str, want: int = 2, validate=None) -> list[str]:
    """풀 보충: 이미 발굴/시드/제작된 종을 제외하고 새 종을 발굴해 discovered.json에 누적.
    반환: 새로 추가된 학명 키 리스트."""
    existing = load_discovered(category_id)
    excl_sci = {it["key"] for it in existing}
    excl_titles = {it["footage"].get("source", "") for it in existing}
    # 하드코딩 시드·제작 원장도 제외(중복 방지)
    try:
        from src.core import footage as _f
        excl_sci |= {k.lower() for k in _f.seeded_keys()}
    except Exception:  # noqa: BLE001
        pass
    new = discover(excl_sci, excl_titles, want=want, validate=validate)
    if not new:
        return []
    save_discovered(category_id, existing + new)
    return [it["key"] for it in new]
