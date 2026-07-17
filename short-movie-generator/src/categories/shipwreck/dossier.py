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


def _dms_to_dec(parts: list[str]) -> float | None:
    """['41','43','57','N'] 또는 ['41.7325','N'] → 십진 도(度). 방향 S/W면 음수."""
    nums: list[float] = []
    hemi = None
    for p in parts:
        p = p.strip()
        if p.upper() in ("N", "S", "E", "W"):
            hemi = p.upper()
        else:
            try:
                nums.append(float(p))
            except ValueError:
                pass
    if not nums:
        return None
    dec = nums[0] + (nums[1] / 60 if len(nums) > 1 else 0) + (nums[2] / 3600 if len(nums) > 2 else 0)
    if hemi in ("S", "W"):
        dec = -dec
    return dec


def _parse_coord_tokens(toks: list[str]) -> tuple[float, float] | None:
    up = [t.upper() for t in toks]
    if any(t in ("N", "S", "E", "W") for t in up):
        try:
            i = next(k for k, t in enumerate(up) if t in ("N", "S"))
            j = next(k for k, t in enumerate(up) if t in ("E", "W") and k > i)
        except StopIteration:
            return None
        lat = _dms_to_dec(toks[0:i + 1]); lon = _dms_to_dec(toks[i + 1:j + 1])
    else:                                                  # 십진 쌍(예: 41.73|-49.95)
        nums: list[float] = []
        for t in toks:
            try:
                nums.append(float(t))
            except ValueError:
                pass
        if len(nums) < 2:
            return None
        lat, lon = nums[0], nums[1]
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return (round(lat, 4), round(lon, 4))


def _extract_coord(w: str) -> tuple[float, float] | None:
    """위키텍스트의 {{coord|…}}에서 침몰 좌표(십진 lat,lon) 추출. display=title 우선. 없으면 None.
    ★난파선은 침몰 위치가 문서화된 사실 → 지도 표기는 하드룰 '임의 좌표 금지' 대상이 아니다(근거 있음)."""
    cands = re.findall(r"\{\{\s*[Cc]oord\s*\|([^{}]*)\}\}", w or "")
    if not cands:
        return None

    def score(s: str) -> int:
        sl = s.lower()
        return 2 if "display=title" in sl or "title,inline" in sl or "inline,title" in sl else (
            1 if "title" in sl else 0)

    for c in sorted(cands, key=score, reverse=True):
        # 지시자(display=title, scale:…, type:…, region:… 등 '='·':' 포함)는 위치 무관하게 건너뛰고
        #   숫자·방향(N/S/E/W) 토큰만 취한다(에스토니아처럼 display=title가 숫자 앞에 오는 경우 대응).
        toks = [p.strip() for p in c.split("|")
                if "=" not in p and ":" not in p and p.strip()]
        ll = _parse_coord_tokens(toks)
        if ll:
            return ll
    return None


# 해역명 라벨(십진 좌표 → 대양·폐쇄해). 폐쇄해·특수수역을 먼저 판정(정확도), 미확신은 대양 basin.
def _ocean_label(lat: float, lon: float) -> tuple[str, str]:
    la, lo = lat, lon

    def box(a0, a1, o0, o1) -> bool:
        return a0 <= la <= a1 and o0 <= lo <= o1

    if box(41, 49, -93, -76): return ("五大湖", "GREAT LAKES")        # 담수호(에드먼드 피츠제럴드 등)
    if box(30, 46, -6, 37):   return ("地中海", "MEDITERRANEAN")      # 아드리아·에게·이오니아 포함
    if box(40, 48, 27, 42):   return ("黒海", "BLACK SEA")
    if box(53, 66, 9, 31):    return ("バルト海", "BALTIC SEA")
    if box(12, 30, 32, 44):   return ("紅海", "RED SEA")
    if box(9, 22, -89, -60):  return ("カリブ海", "CARIBBEAN SEA")
    if la > 66:  return ("北極海", "ARCTIC OCEAN")
    if la < -60: return ("南極海", "SOUTHERN OCEAN")
    if -100 <= lo <= 20:
        return ("北大西洋", "N. ATLANTIC") if la >= 0 else ("南大西洋", "S. ATLANTIC")
    if 20 < lo < 100:
        return ("インド洋", "INDIAN OCEAN")
    return ("北太平洋", "N. PACIFIC") if la >= 0 else ("南太平洋", "S. PACIFIC")


def _wiki_specs(name: str) -> dict:
    """위키백과 인포박스 → 제원 dict + 요약문 + 침몰 좌표(sink_lat/sink_lon). 실패 시 {}."""
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
    coord = _extract_coord(w)                              # 침몰 좌표(있으면)
    if coord:
        out["sink_lat"], out["sink_lon"] = coord
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


def _commons_images(name: str, limit: int = 40, query: str | None = None) -> list[dict]:
    """커먼스 파일 검색 → 사용가능 라이선스 이미지 [{url,title,caption,credit,license,beat}].
    query를 주면 그 문자열로 검색(수중 잔해 전용 검색 등). 없으면 name으로 검색."""
    q = (f"{_COMMONS}?action=query&generator=search"
         f"&gsrsearch={urllib.parse.quote(query or name)}&gsrnamespace=6&gsrlimit={limit}"
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
    # ★수중 잔해(촬영) 사진 우선 확보(운영자 확정 · 인명사고 콘텐츠의 핵심 자료):
    #   일반 이름 검색은 역사(취항) 사진 위주라 실제 수중 촬영이 상위에 안 잡힌다. 접두어(RMS/HMS 등)를
    #   뗀 '짧은 이름 + wreck/underwater'로 전용 검색해, 촬영된 수중 잔해가 있으면 반드시 수확한다.
    display = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    short = re.sub(r"^(SS|RMS|HMS|HMHS|MV|MS|USS|MT|SMS|USNS|RMHS)\s+", "", display).strip() or display
    seen = {im["url"] for im in imgs}
    for eq in (f"{short} underwater", f"{short} wreck"):
        try:
            for im in _commons_images(short, limit=30, query=eq):
                if im["url"] not in seen:
                    seen.add(im["url"]); imgs.append(im)
        except Exception as e:  # noqa: BLE001
            log.info("[dossier] 수중 잔해 검색 실패(%s): %s", eq, e)
    imgs = [im for im in imgs if im["beat"] != "skip"]
    if len(imgs) < min_images:
        log.info("[dossier] %s 이미지 부족(%d) → 스킵", name, len(imgs))
        return None
    specs = _wiki_specs(name)
    summary = _wiki_summary(name)
    if not specs and not summary:
        log.info("[dossier] %s 제원·요약 전무 → 스킵", name)
        return None
    # 침몰 좌표(있으면) → 해역명 라벨. 지도 컷(파이프라인)에서 사용. 없으면 지도 컷 생략(날조 안 함).
    sink_lat = specs.pop("sink_lat", None)
    sink_lon = specs.pop("sink_lon", None)
    region_jp = region_en = None
    if sink_lat is not None and sink_lon is not None:
        region_jp, region_en = _ocean_label(sink_lat, sink_lon)
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
        "sink_lat": sink_lat, "sink_lon": sink_lon,
        "sink_region_jp": region_jp, "sink_region_en": region_en,
        "images": imgs,
        "beats": {b: beats.get(b, []) for b in _BEAT_ORDER},
        "credits": sorted({im["credit"] for im in imgs}),
        "sources": [f"Wikipedia: {name}", "Wikimedia Commons"],
    }


# ── 제원 → 화면 카드 / 일본어 대본 ─────────────────────────────────────────
_JP_SHIP_TYPE = [
    (r"aircraft carrier|carrier", "空母"), (r"battleship", "戦艦"), (r"cruiser", "巡洋艦"),
    (r"destroyer", "駆逐艦"), (r"frigate", "フリゲート"), (r"submarine|u-?boat", "潜水艦"),
    (r"ocean liner|liner", "大型客船"), (r"passenger", "客船"), (r"ferry", "フェリー"),
    (r"tanker", "タンカー"), (r"cargo|freight", "貨物船"), (r"steamship|steamer", "蒸気船"),
    (r"yacht", "ヨット"), (r"warship", "軍艦"), (r"ship|vessel|boat", "船"),
]


def _jp_type(en_type: str) -> str:
    t = (en_type or "").lower()
    for pat, jp in _JP_SHIP_TYPE:
        if re.search(pat, t):
            return jp
    return ""


def _year(v: str) -> str:
    m = re.search(r"\b(1[5-9]\d\d|20\d\d)\b", v or "")
    return m.group(1) if m else ""


def _tonnage_short(v: str) -> str:
    m = re.search(r"([\d,]+)\s*(GRT|GT|NRT|DWT|BRT|tons?)", v or "", re.I)
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"
    m2 = re.search(r"([\d,]+)", v or "")
    return f"{m2.group(1)} t" if m2 else ""


def spec_card_lines(dossier: dict) -> list[tuple[str, str]]:
    """화면 제원 카드용 (일본어 라벨, 값) 목록 — 짧고 화면친화적인 항목만(값 없으면 생략)."""
    s = dossier.get("specs", {}) or {}
    rows: list[tuple[str, str]] = []
    jt = _jp_type(s.get("type", ""))
    if jt:
        rows.append(("船種", jt))
    ton = _tonnage_short(s.get("tonnage", ""))
    if ton:
        rows.append(("総トン数", ton))
    if s.get("length"):
        rows.append(("全長", s["length"]))
    ly = _year(s.get("launched", "") or s.get("completed", ""))
    if ly:
        rows.append(("進水", f"{ly}年"))
    sy = s.get("sunk_year") or _year(s.get("fate", ""))
    if sy:
        rows.append(("沈没", f"{sy}年"))
    return rows[:5]


def render_spec_card(dossier: dict, out_png: str, W: int = 720, H: int = 1280) -> str | None:
    """제원 카드 PNG(9:16 투명 배경, 하단 3분의 1 스키매틱 패널). 항목 없으면 None."""
    rows = spec_card_lines(dossier)
    if not rows:
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:  # noqa: BLE001
        return None
    fp_b = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
    fp_r = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

    def _f(path, sz):
        try:
            return ImageFont.truetype(path, sz, index=0)
        except Exception:  # noqa: BLE001
            return ImageFont.load_default()

    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    title = dossier.get("display", "")
    cyan = (120, 220, 255, 255)
    # 패널 위치(화면 46~74%). ★본문 자막(submv=h*0.16 → 세로 약 78~84%)과 겹치지 않도록
    #   위로 올린다(실사고: 자막이 제원 카드를 가림). 카드 하단 74% < 자막 상단 ≈78%.
    x0, y0, x1, y1 = 48, int(H * 0.46), W - 48, int(H * 0.74)
    d.rectangle([x0, y0, x1, y1], fill=(6, 16, 26, 205))
    d.rectangle([x0, y0, x1, y0 + 6], fill=cyan)                      # 상단 액센트 바
    fh = _f(fp_b, 34); fl = _f(fp_r, 30); fv = _f(fp_b, 34); ft = _f(fp_b, 24)
    d.text((x0 + 26, y0 + 22), "SHIP DATA", font=ft, fill=cyan)
    d.text((x0 + 26, y0 + 52), f"「{title}」", font=fh, fill=(255, 255, 255, 255))
    ry = y0 + 108
    for label, val in rows:
        d.text((x0 + 26, ry), label, font=fl, fill=(150, 200, 225, 255))
        d.text((x0 + 210, ry), str(val), font=fv, fill=(255, 255, 255, 255))
        ry += 46
    try:
        im.save(out_png)
        return out_png
    except Exception:  # noqa: BLE001
        return None


_WRECK_BODY_PROMPT = """あなたは沈没船ドキュメンタリーのショート動画ナレーション作家です。\
次の実在の沈没船について、**日本語**で28〜34秒・14〜18個の短い節に分けたナレーションを作ります\
(★合計180字以内)。JSON配列のみ出力(説明禁止)。

船名: {name}
判明している事実(この範囲だけを使う。無い情報は書かない): {facts}
概要: {summary}

■ 構成(この順に、時間軸で):
1) 就航(かつての姿): どんな船だったか(船種・年代)。
2) 事故/沈没: いつ・なぜ沈んだか(判明していれば)。
3) 諸元: トン数・全長など数字を一つ二つ、淡々と。
4) 今の姿: 海底に眠る船体、生き物のすみか。畏敬で締める。

■ トーン(厳守 · 最優先 · 絶対違反禁止): これは**実際に多くの人命が失われた事故**を扱う内容です。
ブラックユーモア・皮肉・笑い・軽口・オチ・言葉遊びは**一切禁止**(他カテゴリのハウス・トーンは適用しない)。
静かで敬意ある、**事実の伝達だけに徹する**ドキュメンタリー・ナレーションを書く。犠牲者を悼む姿勢を保つ。
■ **★敬体(です・ます)で書く。常体(だ・である)は禁止**。名詞・体言止めの短い節は可。
■ **事実の捏造は絶対禁止**: 上の事実に無い数値・原因・人的被害・宝物などを足さない(不明なら触れない)。
出力例: ["これは、ある貨物船の物語です。","かつて海を渡っていました。", ...]
"""


def wreck_body_jp(dossier: dict) -> list[str] | None:
    """그 배 전용 일본어 4비트 본문(敬体·하우스톤). LLM 우선, 실패 시 결정론 폴백."""
    s = dossier.get("specs", {}) or {}
    facts_bits = []
    if s.get("type"):
        facts_bits.append(f"船種={s['type']}")
    if s.get("tonnage"):
        facts_bits.append(f"トン数={s['tonnage']}")
    if s.get("length"):
        facts_bits.append(f"全長={s['length']}")
    if s.get("launched") or s.get("completed"):
        facts_bits.append(f"進水={s.get('launched') or s.get('completed')}")
    if s.get("builder"):
        facts_bits.append(f"建造={s['builder']}")
    if s.get("fate"):
        facts_bits.append(f"最期={s['fate']}")
    if s.get("owner"):
        facts_bits.append(f"船主={s['owner']}")
    facts = " / ".join(facts_bits) or "-"
    summary = (dossier.get("summary", "") or "")[:600]
    name = dossier.get("display", "")
    prompt = _WRECK_BODY_PROMPT.format(name=name, facts=facts, summary=summary)
    chunks = None
    try:
        from src.core import llm
        for _ in range(2):
            try:
                out = llm.generate_text(prompt, max_tokens=1400)
            except Exception as e:  # noqa: BLE001
                log.warning("[dossier] 본문 LLM 실패: %s", e); out = None
            chunks = _parse_body_chunks(out or "")
            if chunks:
                break
    except Exception as e:  # noqa: BLE001
        log.info("[dossier] LLM 미가용: %s", e)
    if not chunks:
        chunks = _fallback_body_jp(dossier)
    if not chunks:
        return None
    try:
        from src.core import naturalness
        return naturalness.polish_lines(chunks)
    except Exception:  # noqa: BLE001
        return chunks


def _parse_body_chunks(out: str) -> list[str] | None:
    """LLM 본문 → 절 리스트(JSON 배열 우선, 잘림 구제 파싱)."""
    if not out:
        return None
    m = re.search(r"\[.*\]", out, re.S)
    if m:
        try:
            arr = json.loads(m.group(0))
            chunks = [str(x).strip() for x in arr if str(x).strip()]
            if len(chunks) >= 8:
                return chunks
        except Exception:  # noqa: BLE001
            pass
    items = re.findall(r'"([^"\n]{1,40})"', out)
    chunks = [s.strip() for s in items if s.strip()]
    return chunks if len(chunks) >= 8 else None


def _fallback_body_jp(dossier: dict) -> list[str]:
    """LLM 미가용 시 결정론 일본어 본문(敬体). 판명된 사실만 사용(날조 없음)."""
    s = dossier.get("specs", {}) or {}
    name = dossier.get("display", "")
    jt = _jp_type(s.get("type", ""))
    ly = _year(s.get("launched", "") or s.get("completed", ""))
    sy = s.get("sunk_year") or _year(s.get("fate", ""))
    ton = _tonnage_short(s.get("tonnage", ""))
    out: list[str] = ["青い海の底に、", "静かに眠る、", "一隻の船。", f"「{name}」です。"]
    if jt and ly:
        out += [f"{ly}年に生まれた、", f"{jt}でした。"]
    elif jt:
        out += [f"かつては、{jt}として、", "海を渡っていました。"]
    if ton:
        out += [f"総トン数は、{ton}。"]
    if sy:
        out += [f"しかし、{sy}年。", "船は海の底へ、", "沈みました。"]
    else:
        out += ["やがて船は、", "海の底へ沈みました。"]
    # ★침몰선은 인명 사고 → 코믹·블랙유머 요소 완전 배제. 담담하고 존중하는 사실 서술만.
    out += ["今、その船体は、", "深い海の底に横たわり、", "静かに眠り続けています。"]
    return out


_WRECK_CAPTION_PROMPT = """あなたは沈没船ドキュメンタリーのSNS投稿キャプション作家です。\
次の実在の沈没船について、**日本語**の投稿キャプションを書きます。JSONのみ出力(説明禁止)。

船名: {name}
判明している事実(この範囲だけを使う。無い情報は書かない): {facts}
概要: {summary}

■ 内容(船の歴史・物語として · 時間軸で):
  ① どんな船で、いつ建造されたか ② いつ・なぜ沈んだか(判明していれば) ③ 今どの海域・水深何mに眠るか
  ④ 潜水調査・水中映像で記録される現在の姿。
■ ★これは生物の紹介では**ありません**。船の歴史・沈没の経緯・水深・海底に眠る姿に焦点を当てる。
  「〜に生息します」「主に〜で暮らします」など**生物の表現は絶対禁止**。
■ トーン: 静かで敬意ある、事実重視のドキュメンタリー。**ブラックユーモア・軽口・オチは一切禁止**
  (実際に人命が失われた事故)。**敬体(です・ます)**。
■ 事実の捏造は絶対禁止(人的被害の数・原因・宝物などを勝手に足さない。不明なら触れない)。
■ 分量: 日本語250〜380字。最後の1〜2行で「保存/また見返したくなる」誘導を1つ入れる。
出力JSON: {{"jp_caption":"…(改行\\nを含む本文)","ko_caption":"…(韓国語の全訳·敬語)",\
"hashtags":["#沈没船","#…","#…"],"ko_hashtags":["#침몰선","#…","#…"],\
"yt_title":"…(30字以内·刺激的でも可)","ko_title":"…(한국어 제목)"}}
"""


def _wreck_caption_tags(dossier: dict) -> tuple[list[str], list[str]]:
    """침몰선 전용 해시태그(생물 태그 배제). JP·KO 각 3개."""
    reg = dossier.get("sink_region_jp")
    jp = ["#沈没船", "#難破船", (f"#{reg}" if reg else "#海底")]
    ko = ["#침몰선", "#난파선", "#해저"]
    return jp, ko


def _depth_num(depth_m: str) -> str:
    nums = re.findall(r"\d[\d,]*", depth_m or "")
    return nums[-1] if nums else ""


def _fallback_wreck_caption(dossier: dict, depth_m: str = "") -> dict:
    """LLM 미가용 시 결정론 침몰선 캡션(敬体·역사 서술·생물 표현 없음·날조 없음)."""
    s = dossier.get("specs", {}) or {}
    name = dossier.get("display", "")
    jt = _jp_type(s.get("type", ""))
    ly = _year(s.get("launched", "") or s.get("completed", ""))
    sy = s.get("sunk_year") or _year(s.get("fate", ""))
    reg = dossier.get("sink_region_jp")
    dep = _depth_num(depth_m)
    L: list[str] = [f"「{name}」——"]
    if jt and ly:
        L.append(f"{ly}年に建造された、{jt}でした。")
    elif jt:
        L.append(f"かつて海を渡った、{jt}でした。")
    elif ly:
        L.append(f"{ly}年に、この船は生まれました。")
    if sy:
        L += [f"しかし{sy}年、その航海は終わりを迎えます。", "船は静かに、海の底へと沈んでいきました。"]
    else:
        L.append("やがて船は、深い海の底へと沈みました。")
    if reg and dep:
        L.append(f"今、その船体は{reg}の海底、水深{dep}mに横たわっています。")
    elif reg:
        L.append(f"今、その船体は{reg}の海底に、静かに眠っています。")
    elif dep:
        L.append(f"今、その船体は水深{dep}mの闇の中に眠っています。")
    else:
        L.append("今、その船体は深い海の底に、静かに横たわっています。")
    L.append("光の届かない海底で記録されたその姿は、潜水調査の映像として今も伝えられています。")
    # ★생물 표현 없이 역사·기록 관점의 상시 서술로 분량 확보(날조 없음)
    _EVER = ["時が止まったような船内に、当時の面影が残ります。",
             "沈黙の中に、かつての航海の記憶が刻まれています。",
             "海に沈んだ、もう一つの歴史がここにあります。"]
    body = "\n".join(L)
    i = 0
    while len(body.replace("\n", "")) < 230 and i < len(_EVER):
        body += "\n" + _EVER[i]; i += 1
    body += "\n\n海の底に眠る歴史を、また見返したくなったら保存してください。"
    # 한국어 참고 번역(결정론)
    ko_L = [f"'{name}'——"]
    if sy:
        ko_L.append(f"{sy}년, 이 배의 항해는 끝을 맞이했습니다.")
    ko_L.append("배는 조용히 바다 밑으로 가라앉았습니다.")
    if reg and dep:
        ko_L.append(f"지금 선체는 {reg}({dossier.get('sink_region_en','')})의 해저, 수심 {dep}m에 잠들어 있습니다.")
    elif dep:
        ko_L.append(f"지금 선체는 수심 {dep}m의 어둠 속에 잠들어 있습니다.")
    else:
        ko_L.append("지금 선체는 깊은 바다 밑에 조용히 누워 있습니다.")
    ko_L.append("빛이 닿지 않는 해저에서 촬영된 그 모습은 지금도 잠수 조사 영상으로 전해집니다.")
    ko_L.append("\n바다에 가라앉은 또 하나의 역사를, 다시 보고 싶다면 저장해 두세요.")
    jp_tags, ko_tags = _wreck_caption_tags(dossier)
    yt = f"【沈没船】{name}、最期の記録"
    yk = f"【침몰선】{name}, 최후의 기록"
    return {"jp": body, "ko": "\n".join(ko_L),
            "tags": jp_tags, "tags_ko": ko_tags,
            "yt_title": f"{yt} {jp_tags[0]} {jp_tags[1]}",
            "yt_title_ko": f"{yk} {ko_tags[0]} {ko_tags[1]}"}


def wreck_caption(dossier: dict, depth_m: str = "") -> dict:
    """★침몰선 전용 캡션(생물 관점 배제 · 역사/침몰 경위/수심/수중 잔해 중심 · 敬体).
    반환 {jp, ko, tags, tags_ko, yt_title, yt_title_ko}(rich_caption.generate와 동일 형태).
    LLM 우선(스토리), 실패 시 결정론 폴백. 사실은 dossier 실제 값만(날조 금지)."""
    s = dossier.get("specs", {}) or {}
    bits = []
    for k, lab in (("type", "船種"), ("tonnage", "トン数"), ("length", "全長"),
                   ("launched", "進水"), ("completed", "竣工"), ("builder", "建造"),
                   ("owner", "船主"), ("fate", "最期"), ("sunk_year", "沈没年")):
        if s.get(k):
            bits.append(f"{lab}={s[k]}")
    if dossier.get("sink_region_jp"):
        bits.append(f"沈没海域={dossier['sink_region_jp']}")
    if _depth_num(depth_m):
        bits.append(f"水深={_depth_num(depth_m)}m")
    facts = " / ".join(bits) or "-"
    summary = (dossier.get("summary", "") or "")[:600]
    prompt = _WRECK_CAPTION_PROMPT.format(name=dossier.get("display", ""), facts=facts, summary=summary)
    d = None
    try:
        from src.core import llm
        for _ in range(2):
            try:
                out = llm.generate_text(prompt, max_tokens=2200)
            except Exception as e:  # noqa: BLE001
                log.warning("[dossier] 캡션 LLM 실패: %s", e); out = None
            m = re.search(r"\{.*\}", out or "", re.S)
            if m:
                try:
                    cand = json.loads(m.group(0))
                except Exception:  # noqa: BLE001
                    cand = None
                if cand and len(str(cand.get("jp_caption", "")).replace("\n", "")) >= 180:
                    d = cand; break
    except Exception as e:  # noqa: BLE001
        log.info("[dossier] 캡션 LLM 미가용: %s", e)
    if not d:
        return _fallback_wreck_caption(dossier, depth_m)
    jp = str(d.get("jp_caption", "")).strip()
    ko = str(d.get("ko_caption", "")).strip()
    jp_tags, ko_tags = _wreck_caption_tags(dossier)
    # LLM 태그가 있으면 앞 3개 채택하되 침몰선 코어 태그를 보장
    lt = [t for t in (d.get("hashtags") or []) if str(t).strip()][:3]
    if lt:
        jp_tags = (["#沈没船"] + [t for t in lt if t != "#沈没船"])[:3]
    lk = [t for t in (d.get("ko_hashtags") or []) if str(t).strip()][:3]
    if lk:
        ko_tags = (["#침몰선"] + [t for t in lk if t != "#침몰선"])[:3]
    fb = _fallback_wreck_caption(dossier, depth_m)
    if not jp or re.search(r"生息|棲息|暮らし", jp):     # 생물 표현 유입 시 폴백(안전망)
        return fb
    try:
        from src.core import naturalness
        jp = naturalness.polish_text(jp)
    except Exception:  # noqa: BLE001
        pass
    if not ko or re.search(r"[ぁ-んァ-ヶ]", ko):
        ko = fb["ko"]
    yt = str(d.get("yt_title", "")).strip() or f"【沈没船】{dossier.get('display','')}、最期の記録"
    yk = str(d.get("ko_title", "")).strip() or f"【침몰선】{dossier.get('display','')}, 최후의 기록"
    return {"jp": jp, "ko": ko, "tags": jp_tags, "tags_ko": ko_tags,
            "yt_title": f"{yt} {jp_tags[0]} {jp_tags[1]}",
            "yt_title_ko": f"{yk} {ko_tags[0]} {ko_tags[1]}"}


def ordered_beat_images(dossier: dict, max_per_beat: int = 2) -> list[dict]:
    """다큐 시퀀스용: afloat→portrait→sinking→wreck **시간순**으로 대표 이미지를 골라 평탄화.
    ★수중 잔해(wreck)는 이 콘텐츠의 핵심 자료 → **있으면 반드시 포함하고 더 많이(우선) 담는다**
    (운영자 확정). 순서는 시간순(잔해는 마지막)을 유지하되, 잔해 컷은 다른 비트보다 넉넉히 넣는다."""
    beats = dossier.get("beats", {})
    out: list[dict] = []
    for b in _BEAT_ORDER:
        # 잔해(wreck)는 촬영본이 있으면 우선 → 상한을 +3 크게(운영자 확정: 뒷부분 수중 컷 한 컷 더).
        #   시퀀스 마지막이 실제 수중 잔해 컷으로 끝나도록 넉넉히 담는다(있는 만큼만, 없으면 안 지어냄).
        cap = (max_per_beat + 3) if b == "wreck" else max_per_beat
        for im in (beats.get(b) or [])[:cap]:
            out.append({**im, "beat": b})
    if not out:
        out = dossier.get("images", [])[:4]
    return out
