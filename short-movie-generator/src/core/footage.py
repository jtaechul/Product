"""footage — 실제 공용도메인(PD/CC0/CC-BY) 심해 '영상' 소싱.

새 제작 시스템의 핵심: AI 생성(Veo)·정지 켄번즈(panzoom)가 아니라 **실제 NOAA/Commons 심해 영상**을
받아 9:16로 재편집한다. 종별로 실사 영상을 확보한다.

우선순위: ① 대표종 시드 URL(검증됨) ② Wikimedia Commons 영상 검색(라이선스 게이트) ③ 실패 시 None.
라이선스: public-domain / cc0 / cc-by / kogl-type1만 통과(하드룰).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

_UA = ("DeepSeaShortsBot/1.0 (https://github.com/jtaechul/product; educational deep-sea shorts) "
       "requests/2")
_ALLOWED = ("public domain", "pd", "cc0", "cc-by", "cc by", "publicdomain", "kogl")
_VIDEO_EXT = (".webm", ".ogv", ".ogg", ".mp4", ".mov")

# NOAA Ocean Exploration 워터마크(좌상단 고정) 영역 — 원본 대비 비율(x, y, w, h).
# 실측: 1280x720 기준 로고 텍스트가 x≤261(0.20W)·y≤77(0.11H) → 여유 포함 0.28/0.15.
# 크롭이 이 영역과 겹치면 ① 프레임을 옆/아래로 밀어 회피(2안) ② 불가 시 delogo로 메움(3안).
_NOAA_LOGO_BOX = (0.0, 0.0, 0.28, 0.15)

# 대표종 시드 — Commons/NOAA 검증된 PD/CC0 영상 직링크(학명 소문자 키).
# 이 목록에 있는 종만 auto가 선택 → '실사 영상 없음' 실패를 원천 차단.
_SEED = {
    "enypniastes eximia": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/a7/Ex1402-dive06_red_animal.webm",
        "license": "cc0", "credit": "NOAA Ocean Exploration",
        "source": "https://commons.wikimedia.org/wiki/File:Ex1402-dive06_red_animal.webm",
    },
    "opisthoteuthis californiana": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/ad/Flapjack_octopus_seafloor.webm",
        "license": "public-domain", "credit": "NOAA Ocean Exploration",
        "source": "https://commons.wikimedia.org/wiki/File:Flapjack_octopus_seafloor.webm",
    },
    "graneledone boreopacifica": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/0/01/Graneledone_boreopacifica_seafloor.webm",
        "license": "public-domain", "credit": "NOAA Ocean Exploration",
        "source": "https://commons.wikimedia.org/wiki/File:Graneledone_boreopacifica_seafloor.webm",
    },
    # 2차 확충(2026-07, Commons 전수 sweep + 육안 검수 통과분).
    "bathynomus giganteus": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/b/b8/Bathynomus_giganteus.webm",
        "license": "public-domain", "credit": "NOAA",
        "source": "https://commons.wikimedia.org/wiki/File:Bathynomus_giganteus.webm",
    },
    "crossota sp.": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/9/9f/Okeanos_Explorer_PR_and_USVI_Dive_8-_Psychedelic_Medusa-NOAA-1280x720.webm",
        "license": "public-domain", "credit": "NOAA Ocean Exploration",
        "source": "https://commons.wikimedia.org/wiki/File:Okeanos_Explorer_PR_and_USVI_Dive_8-_Psychedelic_Medusa-NOAA-1280x720.webm",
    },
    "actinoscyphia aurelia": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/0/02/Venus_Flytrap_Anemone-_2017_American_Samoa.webm",
        "license": "public-domain", "credit": "NOAA Ocean Exploration",
        "source": "https://commons.wikimedia.org/wiki/File:Venus_Flytrap_Anemone-_2017_American_Samoa.webm",
    },
    "megalodicopia hians": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Predatory_tunicate_-_MBA.webm",
        "license": "cc-by", "credit": "Eric Polk (MBARI) · CC BY",
        "source": "https://commons.wikimedia.org/wiki/File:Predatory_tunicate_-_MBA.webm",
    },
    "umbellula sp.": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/7/7d/Umbellula_sp._-_MBA.webm",
        "license": "cc-by", "credit": "Eric Polk (MBARI) · CC BY",
        "source": "https://commons.wikimedia.org/wiki/File:Umbellula_sp._-_MBA.webm",
    },
    # 범위 확장(심해→전 해양) + 다중 소스(GBIF/Commons 전세계) 첫 편입분.
    "sepioteuthis sepioidea": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/c/ce/Caribbean_Reef_Squid_Encounter.webm",
        "license": "cc-by", "credit": "Atsme · CC BY",
        "source": "https://commons.wikimedia.org/wiki/File:Caribbean_Reef_Squid_Encounter.webm",
    },
}


def seeded_keys() -> tuple:
    """검증된 실사 영상이 있는 종(학명 소문자) 목록 — auto 선택 풀."""
    return tuple(_SEED.keys())


def _norm_license(text: str) -> str | None:
    t = (text or "").strip().lower()
    if any(a in t for a in _ALLOWED):
        if "cc0" in t or "zero" in t:
            return "cc0"
        if "public" in t or t in ("pd",):
            return "public-domain"
        if "kogl" in t:
            return "kogl-type1"
        return "cc-by"
    return None


def _download(url: str, dest: Path) -> bool:
    import time
    import requests
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):  # 429/네트워크 대비 백오프 재시도
        try:
            with requests.get(url, headers={"User-Agent": _UA}, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
            if dest.exists() and dest.stat().st_size > 10_000:
                return True
        except Exception as e:  # noqa: BLE001
            wait = 2 ** attempt
            log.warning("[footage] 다운로드 실패(%d/4) %s: %s → %ds 후 재시도", attempt + 1, url, e, wait)
            time.sleep(wait)
    return False


def _commons_search(query: str) -> dict | None:
    """Commons에서 종명 영상 검색 → 통과 라이선스 첫 결과의 원본 URL·크레딧 반환.
    재현율↑: 원문 종명과 '종명 deep sea' 두 변형으로 검색해 영상 파일 후보를 모은다."""
    try:
        import requests
        api = "https://commons.wikimedia.org/w/api.php"
        titles: list[str] = []
        for term in (query, f"{query} deep sea"):
            s = requests.get(api, headers={"User-Agent": _UA}, timeout=30, params={
                "action": "query", "format": "json", "list": "search",
                "srsearch": f'{term} filetype:video', "srnamespace": "6", "srlimit": "20",
            }).json()
            for h in s.get("query", {}).get("search", []):
                if any(h["title"].lower().endswith(e) for e in _VIDEO_EXT) and h["title"] not in titles:
                    titles.append(h["title"])
        if not titles:
            return None
        info = requests.get(api, headers={"User-Agent": _UA}, timeout=30, params={
            "action": "query", "format": "json", "prop": "imageinfo",
            "titles": "|".join(titles[:10]),
            "iiprop": "url|extmetadata", "iiextmetadatafilter": "LicenseShortName|Artist",
        }).json()
        for page in info.get("query", {}).get("pages", {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = _norm_license(meta.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            if lic and url and any(url.lower().endswith(e) for e in _VIDEO_EXT):
                artist = re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
                return {"url": url, "license": lic,
                        "credit": artist or "Wikimedia Commons",
                        "source": page.get("title", "")}
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] Commons 검색 실패(%s): %s", query, e)
        return None


def fetch_footage(scientific_name: str, common_name_en: str, dest_dir: str) -> dict | None:
    """종 실사 영상 확보 → {path, license, credit, source} 또는 None(확보 실패).

    실패 시 상위(파이프라인)는 이 종을 '실사 영상 미확보'로 판단해 중단/스킵한다(날조 방지).
    """
    dest = Path(dest_dir)
    key = (scientific_name or "").strip().lower()
    cand = _SEED.get(key)
    if not cand:
        cand = _commons_search(scientific_name) or _commons_search(common_name_en)
    if not cand:
        log.info("[footage] 실사 영상 미확보: %s / %s", scientific_name, common_name_en)
        return None
    ext = next((e for e in _VIDEO_EXT if cand["url"].lower().endswith(e)), ".webm")
    out = dest / f"footage{ext}"
    # 캐시 재사용(재실행·레이트리밋 대비): 이미 유효 파일이 있으면 재다운로드 생략
    if out.exists() and out.stat().st_size > 100_000:
        log.info("[footage] 캐시 사용: %s", out)
    elif not _download(cand["url"], out):
        return None
    log.info("[footage] 확보: %s (%s, %s)", out, cand["license"], cand["credit"])
    # NOAA 소스는 좌상단 워터마크 영역 정보를 함께 반환(하류에서 회피/제거)
    logo = _NOAA_LOGO_BOX if "noaa" in (cand.get("credit", "") or "").lower() else None
    return {"path": str(out), "license": cand["license"],
            "credit": cand["credit"], "source": cand.get("source", ""),
            "logo_box": logo}
