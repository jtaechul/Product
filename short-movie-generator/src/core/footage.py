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

# 대표종 시드 — Commons/NOAA 검증된 PD 영상 직링크(학명 소문자 키)
_SEED = {
    "enypniastes eximia": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/a7/Ex1402-dive06_red_animal.webm",
        "license": "public-domain", "credit": "NOAA Ocean Exploration",
        "source": "https://commons.wikimedia.org/wiki/File:Ex1402-dive06_red_animal.webm",
    },
}


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
    return {"path": str(out), "license": cand["license"],
            "credit": cand["credit"], "source": cand.get("source", "")}
