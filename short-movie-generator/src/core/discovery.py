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
# 발굴 검색어(해양생물 전반 — 심해 우선, 이어서 일반 해양). 브랜드(深海) 유지 위해 심해류 먼저.
_TERMS = [
    "deep sea creature", "deep sea fish", "abyssal", "hydrothermal vent",
    "anglerfish", "siphonophore", "sea cucumber", "brittle star", "sea spider",
    "octopus underwater", "squid underwater", "cuttlefish", "nudibranch", "sea slug",
    "jellyfish", "comb jelly", "reef fish", "moray eel", "seahorse", "crab underwater",
    "shrimp underwater", "starfish", "sea anemone", "marine worm",
]
# 수심 파싱(설명·위키 발췌에서 'N m'/'N-메터' 근사) — 없으면 빈 값.
_DEPTH = re.compile(r"(\d{2,5})\s*(?:m|메터|メートル|meters?|metres?)\b", re.I)
# 해양생물 확인(날조 방지와 별개 — '채널 주제 적합성'). 위키 발췌·설명에 아래 해양 단서가 있어야 채택.
_MARINE = re.compile(
    r"海|深海|魚類|甲殻|軟体動物|棘皮動物|刺胞動物|海綿|珊瑚|サンゴ|クラゲ|水母|タコ|イカ|"
    r"頭足|貝|エビ|カニ|ウニ|ヒトデ|ナマコ|イソギンチャク|プランクトン|"
    r"marine|\bsea\b|ocean|deep[- ]sea|abyssal|hydrotherm|\bfish\b|coral|crustacean|"
    r"mollus[ck]|cephalopod|echinoderm|cnidaria|jellyfish|aquatic|reef|benthic|"
    r"shrimp|crab|lobster|anemone|sponge|plankton|\bsquid\b|octopus", re.I)
# 채널 부적합(조류·곤충·육상식물·육상동물) 배제 — 해양 단서가 있어도 이게 있으면 스킵.
_EXCLUDE = re.compile(r"鳥類|鳥\b|海鳥|昆虫|植物|樹木|\bbird\b|seabird|\binsect\b|\bplant\b|reptile|amphibian", re.I)
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


def _search_titles(exclude_titles: set[str], per_term: int = 12) -> list[str]:
    titles: list[str] = []
    seen = set(t.lower() for t in exclude_titles)
    for term in _TERMS:
        d = _get(_COMMONS, action="query", list="search",
                 srsearch=f"{term} filetype:video", srnamespace="6", srlimit=str(per_term))
        for h in d.get("query", {}).get("search", []):
            t = h.get("title", "")
            if (t.lower().endswith(_VIDEO_EXT) and t.lower() not in seen
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
             validate=None) -> list[dict]:
    """새 해양생물 영상 후보를 발굴해 '제작 가능한 종 레코드' 리스트를 반환(최대 want개).

    validate(url) -> bool : 실사 다운로드+게이트(정지·카드) 검증 콜백(있으면 통과분만 채택).
    반환 각 항목 = {key, footage:{...}, species:{...}}  (footage._SEED / data.SPECIES 호환).
    """
    excl_sci = {s.strip().lower() for s in exclude_scinames if s}
    titles = _search_titles(exclude_titles)
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
            ar = (w / h) if h else 0
            if not (lic and url and url.lower().endswith(_VIDEO_EXT) and 1.55 <= ar <= 1.95):
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
            # 채널 주제 적합성: 해양생물 단서 필수 + 조류·곤충·육상 배제(바닷새 오채택 방지)
            blob = " ".join(facts) + " " + desc
            if _EXCLUDE.search(blob) or not _MARINE.search(blob):
                log.info("[discovery] 해양생물 아님으로 스킵: %s", sci)
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
            out.append({
                "key": sci.lower(),
                "footage": {"url": url, "license": lic, "credit": credit,
                            "source": title},
                "species": {
                    "scientific_name": sci, "common_name_ko": ko, "common_name_en": en,
                    "depth_range_m": depth, "distribution": "", "habitat": "",
                    "diet": [], "fun_facts": facts,
                    "sources": [fact_src, f"Wikimedia Commons ({title})"],
                },
            })
            log.info("[discovery] 채택: %s (ko=%s ja=%s, %s)", sci, ko, ident.get("ja"), lic)
    return out


def validate_source_url(url: str, tmp_dir: str) -> bool:
    """발굴 후보 URL을 실제로 내려받아 품질 게이트(종횡비·정지영상)를 통과하는지 검증.
    통과분만 discovered.json에 넣어, 제작 때 정지/레터박스로 실패하는 일을 예방한다."""
    from src.core import footage
    ext = next((e for e in _VIDEO_EXT if url.lower().endswith(e)), ".webm")
    dest = Path(tmp_dir) / f"_probe{ext}"
    try:
        if not footage._download(url, dest):
            return False
        dim = footage._probe_dim(str(dest))
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
