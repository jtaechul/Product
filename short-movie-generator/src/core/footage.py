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
    # ※ umbellula sp.(MBARI 클립)는 정지 소스(motion 1.4 < 3.0)로 하드룰 #11 위반 → 시드 제거.
    #   (CI에서 auto 제작이 이 종에서 반복 실패하던 실제 사고. 움직이는 실사 확보 시 재편입.)
    # 3차 확충(2026-07, deep_sea 7종 소진 → 신규 종): NOAA Okeanos "Windows to the Deep 2018" Dive 11.
    #   붉고 가시 돋친 킹크랩(리소드과)이 해저를 걷고 거미불가사리를 잡아먹는 PD·16:9 실사(육안 검수 통과).
    #   앞 7초=NOAA 타이틀카드 / 뒤 15초=URL 오버레이·크레딧 카드 → trim으로 물리 제거(본편 ~91초만 사용).
    "lithodidae": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/d/d9/King_crab_eating_a_brittle_star.webm",
        "license": "public-domain", "credit": "NOAA Ocean Exploration", "trim": (7, 15),
        "source": "https://commons.wikimedia.org/wiki/File:King_crab_eating_a_brittle_star.webm",
    },
    # 범위 확장(심해→전 해양) + 다중 소스(GBIF/Commons 전세계) 첫 편입분.
    "sepioteuthis sepioidea": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/c/ce/Caribbean_Reef_Squid_Encounter.webm",
        "license": "cc-by", "credit": "Atsme · CC BY",
        "source": "https://commons.wikimedia.org/wiki/File:Caribbean_Reef_Squid_Encounter.webm",
    },
    # 신규 카테고리 시드 — 해양 미세조류(marine_algae) / 난파선(shipwreck).
    "bacillariophyta": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/3/39/Diatom_movement_DSC_1511.webm",
        "license": "cc-by", "credit": "Michael Clarke Stuff · CC BY",
        "source": "https://commons.wikimedia.org/wiki/File:Diatom_movement_DSC_1511.webm",
    },
    "wreck aries": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/1/15/Wreck_Aries_-_Dive_in_18m_cargo_ship.webm",
        "license": "cc-by", "credit": "Vitor Alves · CC BY", "trim": (10, 8),
        "source": "https://commons.wikimedia.org/wiki/File:Wreck_Aries_-_Dive_in_18m_cargo_ship.webm",
    },
    # 침몰선(shipwreck) 실사 영상 확충 — 매번 같은 배(아리에스)만 나오던 문제 해결(모두 실존·CC BY·동적영상 검증).
    # 아마추어 다이빙 영상은 인트로 타이틀카드(로고·문구)·아웃트로 크레딧이 박혀 있다.
    # trim=(앞초, 뒤초)로 그 구간을 소스에서 물리적으로 잘라 본편(깨끗한 다이브 영상)만 쓴다.
    # (예: U-1277 인트로에 'SUBMANIA Escola de Mergulho' 로고 → 앞 32초 트림.)
    "wreck u-1277": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/4/4b/Dive_in_U1277_a_wreck_dive_in_a_WWll_German_Submarine.webm",
        "license": "cc-by", "credit": "Victor Marafona · CC BY", "trim": (32, 8),
        "source": "https://commons.wikimedia.org/wiki/File:Dive_in_U1277_a_wreck_dive_in_a_WWll_German_Submarine.webm",
    },
    "wreck madeirense": {
        "url": "https://upload.wikimedia.org/wikipedia/commons/b/b7/Best_Wreck_dive_in_Portugal_-_Madeirense_Porto_Santo.webm",
        "license": "cc-by", "credit": "Victor Marafona · CC BY", "trim": (16, 8),
        "source": "https://commons.wikimedia.org/wiki/File:Best_Wreck_dive_in_Portugal_-_Madeirense_Porto_Santo.webm",
    },
}
# ※ SS Wisconsin(4:3·960×720)은 세로/가로 규격에 안 맞아 레터박스가 생겨 제외(아래 종횡비 게이트로도 자동 차단).


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


def _probe_dim(path: str) -> tuple[int, int] | None:
    """ffprobe로 (width, height) 조회. 실패 시 None."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
            capture_output=True, text=True, timeout=30).stdout.strip()
        w, h = out.split("x")[:2]
        return (int(w), int(h))
    except Exception:  # noqa: BLE001
        return None


def _probe_dur(path: str) -> float | None:
    """ffprobe로 길이(초) 조회. 실패 시 None."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path], capture_output=True, text=True, timeout=30).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
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
    # ★캐시 파일명은 종별로 분리(교차 오염 방지): 공용 'footage.webm' 하나만 쓰면, 게이트에
    #   걸려 폐기된 앞 종의 파일이 남아 다음 후보가 그걸 '캐시'로 재사용 → 전 후보 연쇄 실패.
    slug = re.sub(r"[^a-z0-9]+", "_", key or (common_name_en or "").lower()).strip("_") or "src"
    out = dest / f"footage_{slug}{ext}"
    # 캐시 재사용(재실행·레이트리밋 대비): 이미 유효 파일이 있으면 재다운로드 생략
    if out.exists() and out.stat().st_size > 100_000:
        log.info("[footage] 캐시 사용: %s", out)
    elif not _download(cand["url"], out):
        return None
    log.info("[footage] 확보: %s (%s, %s)", out, cand["license"], cand["credit"])

    def _reject(reason: str):
        """게이트 탈락 소스는 파일까지 지운다 — 다음 시도가 캐시로 오인 재사용하지 않게."""
        log.warning("[footage] %s → 폐기: %s / %s", reason, scientific_name, common_name_en)
        for p in (out, dest / f"footage_{slug}_trim{ext}"):
            try:
                Path(p).unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
        return None

    # ★종횡비 게이트(레터박스 방지): 9:16/16:9 규격에 안 맞는 소스(예: 4:3)는 검은 여백이
    #   생기므로 배제한다. 16:9(1.778) 기준 허용 [1.55, 1.95] 밖이면 소스 미확보로 처리.
    dim = _probe_dim(str(out))
    if dim:
        ar = dim[0] / dim[1] if dim[1] else 0
        if not (1.55 <= ar <= 1.95):
            return _reject(f"종횡비 부적합({dim[0]}x{dim[1]}, AR={ar:.2f})")
    # ★인트로/아웃트로 트림(번인 타이틀카드·크레딧 제거): trim=(앞초,뒤초)가 지정된 소스는
    #   본편만 남겨 로고·문구·인트로 레터박스를 원천 차단한다(아마추어 다이빙 영상 대응).
    trim = cand.get("trim")
    if trim:
        head, tail = float(trim[0]), float(trim[1])
        dur = _probe_dur(str(out))
        if dur and dur - head - tail > 8:   # 트림 후 최소 8초는 남아야 함
            trimmed = dest / f"footage_{slug}_trim{ext}"
            import subprocess
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{head:.2f}",
                                "-to", f"{dur - tail:.2f}", "-i", str(out),
                                "-c", "copy", str(trimmed)])
            if r.returncode == 0 and trimmed.exists() and trimmed.stat().st_size > 100_000:
                log.info("[footage] 인트로/아웃트로 트림: 앞 %.0fs·뒤 %.0fs 제거 → 본편만 사용", head, tail)
                out = trimmed
    # ★정지-이미지 소스 차단(핵심 규칙 · 절대 위반 금지): 움직임이 없는 '사진→영상 포장물'은
    # 영상으로 만들지 않는다. 정지로 판정되면 소스 미확보(None)로 처리 → 릴스는 중단, 롱폼은 스킵.
    try:
        from src.core import watermark_qc as _wq
        if _wq.is_static_source(str(out)):
            return _reject("정지 소스(영상 아님)")
    except Exception as e:  # noqa: BLE001  (검사 실패 시 통과 — 검사 오류로 제작 자체를 막지 않음)
        log.warning("[footage] 정지 검사 생략(오류): %s", e)
    # NOAA 소스는 좌상단 워터마크 영역 정보를 함께 반환(하류에서 회피/제거)
    logo = _NOAA_LOGO_BOX if "noaa" in (cand.get("credit", "") or "").lower() else None
    return {"path": str(out), "license": cand["license"],
            "credit": cand["credit"], "source": cand.get("source", ""),
            "logo_box": logo}
