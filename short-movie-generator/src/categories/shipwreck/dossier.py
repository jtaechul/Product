"""shipwreck 다큐멘터리 모드 — '유명 난파선'의 사실 자료(dossier) 수집.

무명 다이빙 클립(사진 1장 우려먹기)과 달리, 위키백과 문서·제원 + 위키미디어 커먼스의
여러 장(취항 전·사고·잔해)이 존재하는 '유명 난파선'만 다룬다. 이 모듈은:
  1) 유명 난파선 후보 목록(FAMOUS_WRECKS)
  2) 위키백과 인포박스에서 제원(선종·톤수·전장·건조·침몰연도·침몰사유·소유·위치) 추출
  3) 위키미디어 커먼스에서 사용가능 라이선스 이미지 여러 장을 수집하고
     파일명·설명으로 '취항 전(afloat)·사고(sinking)·잔해(wreck)·초상(portrait)' 비트로 분류
  → build_dossier(name)가 이 셋을 묶은 구조화 자료를 반환(부족하면 None).

★날조 금지: 제원·사실은 위키백과 실제 값만. 값이 없으면 생략(지어내지 않음).
★라이선스: 통과 라이선스(PD/CC0/CC-BY/CC-BY-SA) 이미지만 채택(하드룰 #1).
"""
from __future__ import annotations

import json
import logging
import re
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

_UA = {"User-Agent": "abyss-shorts/1.0 (marine documentary; contact via github)"}
_WIKI = "https://en.wikipedia.org/w/api.php"
_COMMONS = "https://commons.wikimedia.org/w/api.php"

# ── 유명 난파선 후보(문서·제원·사진이 풍부한 배만 · 라이브 검증으로 재확인) ──────────────
# 카테고리 라벨은 전부 '침몰선'. 이름은 위키백과 문서 제목과 일치(정확 조회를 위해).
FAMOUS_WRECKS: list[str] = [
    "RMS Titanic", "RMS Lusitania", "HMHS Britannic", "RMS Empress of Ireland",
    "SS Andrea Doria", "SS Thistlegorm", "SS Edmund Fitzgerald", "MS Estonia",
    "German battleship Bismarck", "Japanese battleship Yamato", "USS Arizona (BB-39)",
    "USS Indianapolis (CA-35)", "German cruiser Admiral Graf Spee", "SS President Coolidge",
    "MV Doña Paz", "RMS Republic", "SS Central America", "HMS Hood", "SS Nomadic",
    "SS Great Britain", "MS Zenobia", "SS Yongala", "Vasa (ship)", "Mary Rose",
    "USS Oriskany (CV-34)", "SS Politician", "Costa Concordia", "MV Wilhelm Gustloff",
    "RMS Carpathia", "HMS Royal Oak (08)", "SS Mont-Blanc", "SS Norway",
    "USS Yorktown (CV-5)", "Kronan (ship)", "SS City of Adelaide (1864)",
]

# ── 라이선스 정규화(NC 선차단 — 하드룰 #1) ──────────────────────────────────
_LIC_BLOCK = ("cc-by-nc", "cc by-nc", "by-nc", "noncommercial", "cc-by-nd", "cc by-nd")
_LIC_OK = ("public domain", "cc0", "cc-zero", "cc by", "cc-by", "cc by-sa", "cc-by-sa",
           "attribution", "pd-", "no restrictions")


def _norm_license(short: str) -> str | None:
    """커먼스 LicenseShortName → 통과 라이선스 태그 또는 None(차단)."""
    s = (short or "").strip().lower()
    if not s:
        return None
    if any(b in s for b in _LIC_BLOCK):     # NC/ND 선차단
        return None
    if "cc0" in s or "cc-zero" in s or s.startswith("cc zero"):
        return "cc0"
    if "public domain" in s or s.startswith("pd") or "no restrictions" in s:
        return "public-domain"
    if "by-sa" in s or "by sa" in s:
        return "cc-by-sa"
    if "cc by" in s or "cc-by" in s or "attribution" in s:
        return "cc-by"
    return None


def _get(url: str, timeout: int = 25) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ── 인포박스 값 정리(템플릿·위키링크·ref 제거) ────────────────────────────────
def _expand_templates(v: str) -> str:
    """자주 쓰는 제원 템플릿을 사람이 읽을 문자열로 전개."""
    # {{cvt|415.1|ft}} / {{convert|70|m}} → "415.1 ft"
    def _cvt(m):
        parts = [p.strip() for p in m.group(1).split("|") if p.strip()]
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1]}"
        return parts[0] if parts else ""
    v = re.sub(r"\{\{\s*(?:cvt|convert)\s*\|([^{}]*)\}\}", _cvt, v, flags=re.I)
    # {{GRT|4898}} / {{NRT|2750}} / {{DWT|...}} / {{GT|...}}
    def _ton(m):
        unit = m.group(1).upper(); num = m.group(2).split("|")[0].strip()
        return f"{num} {unit}"
    v = re.sub(r"\{\{\s*(GRT|NRT|DWT|GT|BRT)\s*\|([^{}]*)\}\}", _ton, v, flags=re.I)
    return v


def _clean_field(v: str) -> str:
    v = _expand_templates(v)
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<ref[^>]*/>", "", v)
    v = re.sub(r"\{\{[^{}]*\}\}", " ", v)                       # 남은 템플릿 제거
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", v)     # [[a|b]] → b
    v = re.sub(r"'{2,}", "", v)                                 # 볼드/이탤릭
    v = re.sub(r"<[^>]+>", "", v)                               # HTML
    v = re.sub(r"\*+", " ", v)                                  # 리스트 불릿
    v = v.replace("&nbsp;", " ")
    # 플래그·이미지 템플릿 잔재 정리: 'border|20px', '18px', 앞쪽 'word|' 파편
    v = re.sub(r"\b\d+\s*px\b", " ", v)
    v = re.sub(r"\bborder\b", " ", v)
    v = re.sub(r"^\s*[a-z]{1,10}\|", " ", v)                    # 선두 'flag|' 류 파편
    return re.sub(r"\s+", " ", v).strip(" .,|")


def _valid_spec(c: str) -> bool:
    """'=' 포함(빈 필드가 다음 파라미터를 잘못 삼킨 경우)·과길이 값은 버린다(오파싱 방지)."""
    if not c or "=" in c:
        return False
    if len(c) > 90 or c.lower() in ("", "none", "n/a", "unknown"):
        return False
    return True


# 인포박스에서 뽑을 필드(위키 키 → dossier 키)
_SPEC_FIELDS = {
    "type": "type", "tonnage": "tonnage", "length": "length", "beam": "beam",
    "builder": "builder", "launched": "launched", "completed": "completed",
    "owner": "owner", "operator": "operator", "fate": "fate", "cargo": "cargo",
    "namesake": "namesake", "in service": "in_service", "maiden voyage": "maiden_voyage",
}


def _wiki_specs(name: str) -> dict:
    """위키백과 인포박스 → 제원 dict + 요약문. 실패 시 {}."""
    out: dict = {}
    try:
        q = (f"{_WIKI}?action=parse&page={urllib.parse.quote(name)}"
             "&prop=wikitext&format=json&redirects=1")
        w = _get(q)["parse"]["wikitext"]["*"]
    except Exception as e:  # noqa: BLE001
        log.info("[dossier] 위키텍스트 실패 %s: %s", name, e)
        return out
    for wk, dk in _SPEC_FIELDS.items():
        m = re.search(r"\|\s*" + re.escape(wk) + r"\s*=\s*([^\n]+)", w, flags=re.I)
        if m:
            c = _clean_field(m.group(1))
            if _valid_spec(c):
                out[dk] = c
    # 침몰 연도(fate/launched 등에서 4자리 연도 추출)
    yr = None
    for src in (out.get("fate", ""), out.get("in_service", "")):
        ym = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", src)
        if ym:
            yr = ym.group(1); break
    if yr:
        out["sunk_year"] = yr
    return out


def _wiki_summary(name: str) -> str:
    try:
        s = _get("https://en.wikipedia.org/api/rest_v1/page/summary/"
                 + urllib.parse.quote(name.replace(" ", "_")))
        return (s.get("extract") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


# ── 커먼스 이미지 수집 + 비트 분류 ───────────────────────────────────────────
_BEAT_AFLOAT = re.compile(
    r"afloat|in service|leaving|arriv|at sea|underway|maiden|launch|before|"
    r"passing|steaming|at dock|in port|harbou?r|moored|sailing|voyage|prior to", re.I)
_BEAT_SINKING = re.compile(
    r"sink|sunk|torpedo|explos|burning|fire|disaster|collision|struck|"
    r"attack|going down|abandon|last photo|newspaper|headline|cartoon", re.I)
_BEAT_WRECK = re.compile(
    r"wreck|pecio|relitto|\bdive|diving|underwater|seabed|debris|hull on|"
    r"remains|artifact|bow of|stern of|salvage|rov |sonar|scan|expedition", re.I)
_BEAT_PORTRAIT = re.compile(
    r"portrait|painting|drawing|illustration|poster|model|plan|diagram|"
    r"blueprint|profile|builder'?s|lithograph|postcard|advert", re.I)
# 화면에 부적합한 사진(사람 얼굴 위주·기념비·지도만 등)은 후순위/배제
_BEAT_BAD = re.compile(
    r"memorial|grave|cemetery|plaque|monument|survivor|passenger list|crew list|"
    r"captain|officer portrait|stamp|coin|medal|menu|ticket|signature", re.I)


def _classify_beat(title: str, caption: str) -> str:
    t = f"{title} {caption}"
    if _BEAT_BAD.search(t):
        return "skip"
    if _BEAT_WRECK.search(t):
        return "wreck"
    if _BEAT_SINKING.search(t):
        return "sinking"
    if _BEAT_PORTRAIT.search(t):
        return "portrait"
    if _BEAT_AFLOAT.search(t):
        return "afloat"
    return "afloat"   # 기본은 '취항 모습'으로(배 전경 사진이 대부분)


def _commons_images(name: str, limit: int = 40) -> list[dict]:
    """커먼스 파일 검색 → 사용가능 라이선스 이미지 [{url,title,caption,credit,license,beat}]."""
    q = (f"{_COMMONS}?action=query&generator=search"
         f"&gsrsearch={urllib.parse.quote(name)}&gsrnamespace=6&gsrlimit={limit}"
         "&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=1600&format=json")
    try:
        pages = _get(q).get("query", {}).get("pages", {})
    except Exception as e:  # noqa: BLE001
        log.info("[dossier] 커먼스 검색 실패 %s: %s", name, e)
        return []
    rows: list[dict] = []
    seen: set[str] = set()
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        title = (p.get("title") or "")[5:]                 # 'File:' 제거
        if not re.search(r"\.(jpe?g|png)$", title, re.I):
            continue
        em = ii.get("extmetadata", {}) or {}
        lic = _norm_license((em.get("LicenseShortName", {}) or {}).get("value", ""))
        if not lic:
            continue
        url = ii.get("thumburl") or ii.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        caption = _clean_field((em.get("ImageDescription", {}) or {}).get("value", ""))[:120]
        author = _clean_field((em.get("Artist", {}) or {}).get("value", ""))[:60] or "Wikimedia Commons"
        rows.append({
            "url": url, "title": title, "caption": caption,
            "credit": f"{author} · {lic.upper()}", "license": lic,
            "source": f"File:{title}", "beat": _classify_beat(title, caption),
        })
    return rows


_BEAT_ORDER = ("afloat", "portrait", "sinking", "wreck")


def build_dossier(name: str, min_images: int = 4) -> dict | None:
    """유명 난파선 자료 묶음. 이미지가 min_images 미만이거나 제원이 전무하면 None(빈약 → 문서 미제작)."""
    imgs = _commons_images(name)
    imgs = [im for im in imgs if im["beat"] != "skip"]
    if len(imgs) < min_images:
        log.info("[dossier] %s 이미지 부족(%d) → 스킵", name, len(imgs))
        return None
    specs = _wiki_specs(name)
    summary = _wiki_summary(name)
    if not specs and not summary:
        log.info("[dossier] %s 제원·요약 전무 → 스킵", name)
        return None
    # 비트별 이미지 그룹(각 비트 대표 몇 장)
    beats: dict[str, list[dict]] = {b: [] for b in _BEAT_ORDER}
    for im in imgs:
        beats.setdefault(im["beat"], []).append(im)
    # 잔해 사진이 하나도 없으면(주제 피사체 부재) 후순위지만 제작은 가능 — afloat로 흡수
    return {
        "name": name,
        "display": re.sub(r"\s*\([^)]*\)\s*$", "", name).strip(),   # 괄호 각주 제거
        "specs": specs,
        "summary": summary,
        "images": imgs,
        "beats": {b: beats.get(b, []) for b in _BEAT_ORDER},
        "credits": sorted({im["credit"] for im in imgs}),
        "sources": [f"Wikipedia: {name}", "Wikimedia Commons"],
    }


def ordered_beat_images(dossier: dict, max_per_beat: int = 2) -> list[dict]:
    """다큐 시퀀스용: afloat→portrait→sinking→wreck 순서로 대표 이미지를 골라 평탄화.
    각 비트 최대 max_per_beat장. 비어 있는 비트는 건너뛴다(날조 없이 있는 것만)."""
    out: list[dict] = []
    for b in _BEAT_ORDER:
        for im in (dossier.get("beats", {}).get(b) or [])[:max_per_beat]:
            out.append({**im, "beat": b})
    # 아무 비트도 안 잡히면 전체에서 앞쪽 몇 장
    if not out:
        out = dossier.get("images", [])[:4]
    return out
