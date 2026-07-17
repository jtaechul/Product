"""footage — 실제 공용도메인(PD/CC0/CC-BY) 심해 '영상' 소싱.

새 제작 시스템의 핵심: AI 생성(Veo)·정지 켄번즈(panzoom)가 아니라 **실제 NOAA/Commons 심해 영상**을
받아 9:16로 재편집한다. 종별로 실사 영상을 확보한다.

우선순위: ① 대표종 시드 URL(검증됨) ② Wikimedia Commons 영상 검색(라이선스 게이트) ③ 실패 시 None.
라이선스: public-domain / cc0 / cc-by / kogl-type1만 통과(하드룰).
"""
from __future__ import annotations

import logging
import math
import re
from pathlib import Path

log = logging.getLogger(__name__)

_UA = ("DeepSeaShortsBot/1.0 (https://github.com/jtaechul/product; educational deep-sea shorts) "
       "requests/2")
# 통과 라이선스 부분일치 키(운영자 확정: CC-BY-SA 오픈). cc-by-sa는 'cc by'로도 잡히지만
# 명시 키를 둬서 _norm_license가 'cc-by-sa'로 정확히 분류하게 한다(크레딧 표기 구분).
_ALLOWED = ("public domain", "pd", "cc0", "cc-by", "cc by", "cc-by-sa", "cc by-sa", "publicdomain", "kogl")
_VIDEO_EXT = (".webm", ".ogv", ".ogg", ".mp4", ".mov")
_IMAGE_EXT = (".jpg", ".jpeg", ".png")

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


def _merge_discovered_seeds() -> None:
    """자동 발굴(discovery)로 확보된 종의 실사 시드를 _SEED에 병합한다(import 시 1회).
    이렇게 하면 손으로 시드를 추가하지 않아도 발굴된 종이 fetch_footage·auto 후보에 그대로 편입된다.
    discovery.load_discovered는 JSON만 읽어 import 순환이 없다."""
    try:
        from src.core import discovery
    except Exception:  # noqa: BLE001
        return
    for cid in ("deep_sea", "marine_life", "marine_algae", "shipwreck"):
        try:
            for it in discovery.load_discovered(cid):
                key = (it.get("key") or "").strip().lower()
                fp = it.get("footage") or {}
                # 유명 난파선 다큐(wreck_doc)는 단일 url이 없어도 된다(여러 이미지를 런타임에 수집).
                is_doc = fp.get("media_kind") == "wreck_doc"
                if key and (fp.get("url") or is_doc) and key not in _SEED:
                    _SEED[key] = {"url": fp.get("url", ""), "license": fp.get("license", "cc-by"),
                                  "credit": fp.get("credit", "Wikimedia Commons"),
                                  "source": fp.get("source", "")}
                    # ★사진 소스(난파선 무한 엔진): media_kind=photo면 fetch_footage가 켄번즈로 영상화한다.
                    #   media_kind=wreck_doc면 위키+커먼스 dossier로 여러 이미지 시간순 시퀀스를 만든다.
                    if fp.get("media_kind"):
                        _SEED[key]["media_kind"] = fp["media_kind"]
                    if fp.get("wiki_title"):
                        _SEED[key]["wiki_title"] = fp["wiki_title"]
                    if fp.get("image_url"):
                        _SEED[key]["image_url"] = fp["image_url"]
                    if fp.get("trim"):
                        _SEED[key]["trim"] = tuple(fp["trim"])
        except Exception:  # noqa: BLE001
            continue


_merge_discovered_seeds()


def seeded_keys() -> tuple:
    """검증된 실사 영상이 있는 종(학명 소문자) 목록 — auto 선택 풀."""
    return tuple(_SEED.keys())


def _norm_license(text: str) -> str | None:
    t = (text or "").strip().lower()
    # ★NC(비상업) 차단(하드룰): 'cc by'가 'cc by-nc'의 부분일치라 먼저 걸러 오통과를 막는다.
    if "nc" in t and ("by-nc" in t or "by nc" in t or "noncommercial" in t or "non-commercial" in t):
        return None
    if any(a in t for a in _ALLOWED):
        if "cc0" in t or "zero" in t:
            return "cc0"
        if "public" in t or t in ("pd",):
            return "public-domain"
        if "kogl" in t:
            return "kogl-type1"
        if "sa" in t and ("by-sa" in t or "by sa" in t):  # CC-BY-SA(오픈, 크레딧 필수)
            return "cc-by-sa"
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
    """실제 길이(초) = duration − start_time. 일부 NOAA/Commons webm은 타임스탬프가 0에서
    시작하지 않아 raw duration이 '끝 타임스탬프'(수 시간대)로 잡혀 구간 계산이 파괴된다
    (실측: graneledone 클립이 142219초로 오판). start_time을 빼 실제 재생 길이를 반환."""
    import subprocess
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=start_time,duration",
             "-of", "json", path], capture_output=True, text=True, timeout=30).stdout
        import json as _json
        fmt = _json.loads(out or "{}").get("format", {})
        dur = float(fmt.get("duration") or 0)
        start = float(fmt.get("start_time") or 0)
        return max(0.0, dur - max(0.0, start))
    except Exception:  # noqa: BLE001
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


def _card_flags(video: str, ss: float, span: float, fps: int, tmp: Path) -> list[bool]:
    """[ss, ss+span] 구간을 fps로 한 번에 추출해, 각 프레임이 '카드/검은 리드인'인지 리스트 반환.
    카드 = text_score(밝은 획-에지) 높음 + 평균 밝기 어두움, 또는 거의 순검정. 실사와 구분."""
    import subprocess
    from src.core import reframe
    from PIL import Image, ImageStat
    for f in tmp.glob("cf_*.jpg"):
        f.unlink(missing_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{ss:.2f}", "-t", f"{span:.2f}",
                        "-i", video, "-vf", f"fps={fps},scale=480:-1", str(tmp / "cf_%03d.jpg")],
                       check=True, timeout=60)
    except Exception:  # noqa: BLE001
        return []
    flags = []
    for f in sorted(tmp.glob("cf_*.jpg")):
        try:
            ts = reframe.text_score(str(f))
            br = ImageStat.Stat(Image.open(f).convert("L")).mean[0]
            flags.append((ts > 0.022 and br < 70) or br < 8)
        except Exception:  # noqa: BLE001
            flags.append(False)
    return flags


def _auto_trim_cards(path: str, dur: float, cap: float = 10.0) -> tuple[float, float]:
    """인트로/아웃트로 타이틀카드(어두운 배경+NOAA 로고·문구)를 **자동 탐지**해 잘라낼
    (앞초, 뒤초)를 반환. 수동 trim 값이 없는 클립(대다수 NOAA 영상)도 카드가 남지 않게 한다.

    ★재발방지(사용자 규칙): 롱폼 콜드오픈은 `-stream_loop`로 클립을 반복하는데, 인트로 카드가
    남아 있으면 루프마다 '검은 화면+반쯤 지워진 NOAA 문구'가 재노출됐다. 소스를 물리적으로
    카드 없는 본편으로 만들어 루프·컷 어디서도 카드가 못 나오게 한다.
    앞/뒤 각각 cap초까지 4fps로 스캔해 '첫 실사 프레임'(0.75초 연속)까지를 카드로 보고 자른다.
    """
    if not dur or dur <= 0:
        return (0.0, 0.0)
    fps = 4
    step = 1.0 / fps
    need = max(1, int(0.75 * fps))
    tmp = Path(path).parent / "_cardscan"
    tmp.mkdir(exist_ok=True)

    def edge(flags: list[bool]) -> float:
        clean = 0
        for i, is_card in enumerate(flags):
            if is_card:
                clean = 0
            else:
                clean += 1
                if clean >= need:
                    return max(0.0, (i - (clean - 1)) * step)
        return 0.0

    span = min(cap, max(0.0, dur))
    head = edge(_card_flags(path, 0.0, span, fps, tmp))
    tail = 0.0
    if dur > cap + 2:
        rflags = list(reversed(_card_flags(path, dur - span, span, fps, tmp)))
        tail = edge(rflags)
    for f in tmp.glob("cf_*.jpg"):
        f.unlink(missing_ok=True)
    if dur - head - tail < 8:            # 본편이 8초 미만 남는 과트림은 취소
        return (0.0, 0.0)
    return (round(head, 2), round(tail, 2))


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


def _commons_photo_search(query: str, min_w: int = 1200, min_h: int = 800) -> dict | None:
    """Commons에서 대상의 고해상 실사 사진 1장(통과 라이선스) → {url,license,credit,source} 또는 None.
    오프닝 훅·엔드카드 배경용 '히어로 이미지'(영상 프레임보다 훨씬 선명)."""
    try:
        import requests
        api = "https://commons.wikimedia.org/w/api.php"
        titles: list[str] = []
        for term in (query, f"{query} underwater"):
            if not (term or "").strip():
                continue
            s = requests.get(api, headers={"User-Agent": _UA}, timeout=30, params={
                "action": "query", "format": "json", "list": "search",
                "srsearch": f"{term} filetype:bitmap", "srnamespace": "6", "srlimit": "15",
            }).json()
            for h in s.get("query", {}).get("search", []):
                if any(h["title"].lower().endswith(e) for e in _IMAGE_EXT) and h["title"] not in titles:
                    titles.append(h["title"])
        if not titles:
            return None
        info = requests.get(api, headers={"User-Agent": _UA}, timeout=30, params={
            "action": "query", "format": "json", "prop": "imageinfo",
            "titles": "|".join(titles[:20]),
            "iiprop": "url|size|extmetadata", "iiextmetadatafilter": "LicenseShortName|Artist",
        }).json()
        for page in info.get("query", {}).get("pages", {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = _norm_license(meta.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            w, h = ii.get("width", 0), ii.get("height", 0)
            if lic and url and any(url.lower().endswith(e) for e in _IMAGE_EXT) and w >= min_w and h >= min_h:
                artist = re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
                cr = artist or "Wikimedia Commons"
                cr += " · CC BY-SA" if lic == "cc-by-sa" else (" · CC BY" if lic == "cc-by" else "")
                return {"url": url, "license": lic, "credit": cr, "source": page.get("title", "")}
        return None
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 히어로 사진 검색 실패(%s): %s", query, e)
        return None


def _commons_photos(query: str, n: int, min_w: int = 1200, min_h: int = 800) -> list[dict]:
    """대상의 고해상 사진 여러 장(통과 라이선스) → [{url,license,credit,source}]. 컷어웨이용."""
    out: list[dict] = []
    try:
        import requests
        api = "https://commons.wikimedia.org/w/api.php"
        titles: list[str] = []
        for term in (query, f"{query} underwater"):
            if not (term or "").strip():
                continue
            s = requests.get(api, headers={"User-Agent": _UA}, timeout=30, params={
                "action": "query", "format": "json", "list": "search",
                "srsearch": f"{term} filetype:bitmap", "srnamespace": "6", "srlimit": "20",
            }).json()
            for h in s.get("query", {}).get("search", []):
                if any(h["title"].lower().endswith(e) for e in _IMAGE_EXT) and h["title"] not in titles:
                    titles.append(h["title"])
        if not titles:
            return out
        info = requests.get(api, headers={"User-Agent": _UA}, timeout=30, params={
            "action": "query", "format": "json", "prop": "imageinfo",
            "titles": "|".join(titles[:40]),
            "iiprop": "url|size|extmetadata", "iiextmetadatafilter": "LicenseShortName|Artist",
        }).json()
        for page in info.get("query", {}).get("pages", {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = _norm_license(meta.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            w, h = ii.get("width", 0), ii.get("height", 0)
            if lic and url and any(url.lower().endswith(e) for e in _IMAGE_EXT) and w >= min_w and h >= min_h:
                artist = re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
                cr = artist or "Wikimedia Commons"
                cr += " · CC BY-SA" if lic == "cc-by-sa" else (" · CC BY" if lic == "cc-by" else "")
                out.append({"url": url, "license": lic, "credit": cr, "source": page.get("title", "")})
                if len(out) >= n:
                    break
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 컷어웨이 사진 검색 실패(%s): %s", query, e)
    return out


def fetch_cutaway_photos(scientific_name: str, common_name_en: str, dest_dir: str,
                         n: int = 2, exclude_sources: tuple = ()) -> list[dict]:
    """본문 컷어웨이용 같은 대상 고해상 사진 최대 n장 확보 → [{path, credit, license}].
    같은 대상만(오정보 방지). exclude_sources(히어로 등)와 겹치는 파일은 제외. 없으면 []."""
    ex = {s for s in exclude_sources if s}
    got = _commons_photos(scientific_name, n + len(ex) + 2) or _commons_photos(common_name_en, n + 2)
    dest = Path(dest_dir)
    key = (scientific_name or common_name_en or "cut").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_") or "cut"
    out: list[dict] = []
    for i, g in enumerate(got):
        if g.get("source") in ex or g["url"] in ex:
            continue
        iext = next((e for e in _IMAGE_EXT if g["url"].lower().endswith(e)), ".jpg")
        p = dest / f"cutaway_{slug}_{i}{iext}"
        if not (p.exists() and p.stat().st_size > 50_000) and not _download(g["url"], p):
            continue
        out.append({"path": str(p), "credit": g["credit"], "license": g["license"],
                    "source": g.get("source", "")})
        if len(out) >= n:
            break
    return out


def insert_photo_cutaways(body_v: str, photos: list[dict], out_v: str, body_dur: float,
                          key: str = "") -> str:
    """본문(9:16, 자막 번인 전)에 같은 대상 고해상 사진 컷어웨이 1~2컷을 짧게 오버레이(디졸브).
    ★오디오·자막은 이후 단계에서 그대로 얹히므로 타이밍·자막 연속성이 보존된다(길이 불변).
    소스가 짧아 반복될 때 반복 피로를 깬다. 실패/사진없음 시 원본 body_v 그대로 반환(발행 불정지)."""
    import subprocess
    photos = [p for p in (photos or []) if p.get("path") and Path(p["path"]).exists()]
    # 짧은 본문·사진 없음 → 삽입하지 않는다(긴 본문은 이미 다양 → 불필요, 남발 방지 최대 2컷).
    if not photos or body_dur < 12:
        return body_v
    n = min(2, len(photos), 1 if body_dur < 20 else 2)
    D = 1.8                                   # 컷어웨이 노출(디졸브 0.3 + 홀드 + 디졸브 0.3)
    # 창 위치: 본문 중반부에 균등 배치(맨 앞/뒤 리빌 구간은 피한다).
    fracs = [0.45] if n == 1 else [0.40, 0.68]
    starts = [round(body_dur * f, 2) for f in fracs[:n]]
    wd = Path(out_v).parent
    inputs = ["-i", body_v]
    fc = []
    labels_prev = "0:v"
    ok_clips = 0
    for i, (ph, T) in enumerate(zip(photos[:n], starts)):
        clip = wd / f"cut_{i}.mp4"
        motion = _kenburns_motion_for(f"{key}_cut{i}")
        if not _kenburns_clip(ph["path"], str(clip), seconds=2, motion=motion, W=720, H=1280):
            continue
        inputs += ["-i", str(clip)]
        ci = ok_clips + 1                      # ffmpeg 입력 인덱스(0=body)
        fc.append(
            f"[{ci}:v]format=yuva420p,fade=t=in:st=0:d=0.3:alpha=1,"
            f"fade=t=out:st={D-0.3}:d=0.3:alpha=1,setpts=PTS+{T}/TB[cv{i}];"
            f"[{labels_prev}][cv{i}]overlay=0:0:enable='between(t,{T},{T+D})'[bv{i}]")
        labels_prev = f"bv{i}"
        ok_clips += 1
    if ok_clips == 0:
        return body_v
    fc_str = ";".join(fc)
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc_str,
             "-map", f"[{labels_prev}]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19",
             "-an", out_v], timeout=300)
        if r.returncode == 0 and Path(out_v).exists() and Path(out_v).stat().st_size > 100_000:
            log.info("[footage] 본문 사진 컷어웨이 %d컷 삽입", ok_clips)
            return out_v
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 컷어웨이 삽입 실패 → 원본 유지: %s", e)
    return body_v


def fetch_hero_photo(scientific_name: str, common_name_en: str, dest_dir: str) -> dict | None:
    """오프닝 훅·엔드카드 배경용 고해상 실사 사진 확보 → {path, credit, license, source} 또는 None.
    학명 우선, 실패 시 영문명. 미확보면 None(상위는 기존 영상 프레임으로 폴백 — 발행 불정지)."""
    got = _commons_photo_search(scientific_name) or _commons_photo_search(common_name_en)
    if not got:
        return None
    dest = Path(dest_dir)
    key = (scientific_name or common_name_en or "hero").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_") or "hero"
    iext = next((e for e in _IMAGE_EXT if got["url"].lower().endswith(e)), ".jpg")
    out = dest / f"hero_{slug}{iext}"
    if not (out.exists() and out.stat().st_size > 50_000) and not _download(got["url"], out):
        return None
    return {"path": str(out), "credit": got["credit"], "license": got["license"],
            "source": got.get("source", "")}


_KENBURNS_MOTIONS = ("in", "out", "pan_r", "pan_l")


def _kenburns_motion_for(key: str) -> str:
    """대상 키로 켄번즈 카메라 무브를 결정론 선택(같은 영상 반복돼도 매번 똑같지 않게)."""
    import hashlib
    h = int(hashlib.md5((key or "kb").encode("utf-8")).hexdigest(), 16)
    return _KENBURNS_MOTIONS[h % len(_KENBURNS_MOTIONS)]


def _kenburns_vf(motion: str, fr: int, W: int = 1280, H: int = 720) -> str:
    """켄번즈 vf(줌 방향 다양화): in=푸시인, out=풀아웃, pan_r/pan_l=수평 트랙.
    출력 W×H로 커버 크롭(16:9 본문 소스 또는 9:16 컷어웨이 둘 다 지원)."""
    cover = f"scale={2 * W}:{2 * H}:force_original_aspect_ratio=increase,crop={2 * W}:{2 * H},"
    yc = "y='ih/2-(ih/zoom/2)'"
    if motion == "out":
        z = f"z='max(1.13-{0.13/max(fr,1):.6f}*on,1.0)'"
        xy = f"x='iw/2-(iw/zoom/2)':{yc}"
    elif motion == "pan_r":
        z, xy = "z='1.1'", f"x='(iw-iw/zoom)*on/{fr}':{yc}"
    elif motion == "pan_l":
        z, xy = "z='1.1'", f"x='(iw-iw/zoom)*(1-on/{fr})':{yc}"
    else:  # in (기본)
        z = f"z='min(zoom+{0.12/max(fr,1):.6f},1.12)'"
        xy = f"x='iw/2-(iw/zoom/2)':{yc}"
    return f"{cover}zoompan={z}:d={fr}:{xy}:s={W}x{H}:fps=30,format=yuv420p"


def _kenburns_clip(image_path: str, out_path: str, seconds: int = 14, motion: str = "in",
                   W: int = 1280, H: int = 720) -> bool:
    """정지 사진 → 켄번즈 영상(W×H). ★난파선·미세조류 등 '정적 피사체' 사진의 무한 엔진.
    모션이 있어 정지-소스 게이트를 통과한다. motion=in/out/pan_r/pan_l로 줌 방향을 다양화해
    같은 소재가 반복돼도 매번 똑같은 느낌이 안 나게 한다(사진은 영상보다 훨씬 많아 공급이 사실상 무한).
    W,H로 16:9(본문 소스) 또는 9:16(본문 컷어웨이)을 선택한다."""
    import subprocess
    fr = int(seconds) * 30
    vf = _kenburns_vf(motion if motion in _KENBURNS_MOTIONS else "in", fr, W, H)
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", image_path,
                            "-vf", vf, "-t", str(int(seconds)), "-c:v", "libx264", "-preset",
                            "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-an", out_path],
                           timeout=180)
        return (r.returncode == 0 and Path(out_path).exists()
                and Path(out_path).stat().st_size > 50_000)
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 켄번즈 합성 실패: %s", e)
        return False


def _fetch_photo_kenburns(cand: dict, dest: Path, key: str, common_name_en: str) -> dict | None:
    """사진 소스(media_kind=photo)를 내려받아 켄번즈로 16:9 영상화 → {path,license,credit,source}."""
    img_url = cand.get("image_url") or cand.get("url") or ""
    iext = next((e for e in _IMAGE_EXT if img_url.lower().endswith(e)), ".jpg")
    slug = re.sub(r"[^a-z0-9]+", "_", key or (common_name_en or "").lower()).strip("_") or "src"
    img = dest / f"photo_{slug}{iext}"
    if not (img.exists() and img.stat().st_size > 50_000) and not _download(img_url, img):
        log.info("[footage] 사진 다운로드 실패: %s", img_url)
        return None
    clip = dest / f"footage_{slug}_kb.mp4"
    if not _kenburns_clip(str(img), str(clip), motion=_kenburns_motion_for(key)):
        return None
    log.info("[footage] 사진→켄번즈 영상화 완료: %s (%s)", clip, cand.get("credit", ""))
    return {"path": str(clip), "license": cand["license"], "credit": cand["credit"],
            "source": cand.get("source", ""), "logo_box": None}


def _frame_macro_std(img) -> float:
    """프레임의 '대구조 밝기 분산' — 32×18로 강하게 줄여 마린스노(잡티)를 지우고 큰 덩어리만 남긴다.
    빈 물/균일 하강 컷은 낮고(≈0~11), 실제 피사체(생물·구조물)가 있으면 높다(실측 29~53)."""
    from PIL import ImageStat
    return ImageStat.Stat(img.convert("L").resize((32, 18))).stddev[0]


_MIN_VISIBILITY = 16.0   # p75 macro 기준(실측: 생물 최저 29.5 · 빈물 최고 11 → 16이 안전한 경계)


def subject_visibility(video: str, sample: int = 12) -> float:
    """영상에 '피사체(구조)'가 실제로 담겼는지 점수(대구조 밝기 분산 p75).
    ★목적: '아무것도 안 보이는 빈 물/준비 컷'을 배제(텐트 쉬림프 사고). 낮을수록 빈 화면.
    ※ 이 지표는 '구조 유무'만 본다 — '잠수사 vs 배' 같은 주제 일치는 Step2(CLIP 의미검증)가 판정."""
    import subprocess
    import tempfile
    from PIL import Image
    dur = _probe_dur(video) or 0.0
    if dur <= 0:
        return 0.0
    with tempfile.TemporaryDirectory(prefix="vis_") as td:
        ms: list[float] = []
        for i in range(sample):
            t = dur * (0.08 + 0.84 * i / max(1, sample - 1))
            f = Path(td) / f"v{i}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}",
                            "-i", video, "-frames:v", "1", str(f)], capture_output=True)
            if f.exists():
                try:
                    ms.append(_frame_macro_std(Image.open(f)))
                except Exception:  # noqa: BLE001
                    pass
        if len(ms) < 3:
            return 0.0
        ms.sort()
        return ms[int(len(ms) * 0.75)]   # p75(넉넉히 통과 — 일부 구간만 피사체여도 OK)


def footage_shows_subject(video: str, subject: str, sample: int = 6) -> bool | None:
    """★Step2 의미검증: 비전 LLM으로 영상에 '주제 피사체'가 실제로 나오는지 판정.
    True=충분히 나옴 / False=거의 안 나옴(잠수사·빈물·오종) / None=검증 불가(키 없음·실패 → 통과).
    프레임을 소량(작게) 샘플해 비용을 낮춘다. 키가 없으면 None → 상위는 게이트를 건너뛴다(발행 불정지)."""
    import subprocess
    import tempfile
    from src.core import llm
    dur = _probe_dur(video) or 0.0
    if dur <= 0:
        return None
    with tempfile.TemporaryDirectory(prefix="sv_") as td:
        frames: list[str] = []
        for i in range(sample):
            t = dur * (0.1 + 0.8 * i / max(1, sample - 1))
            f = Path(td) / f"s{i}.jpg"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video,
                            "-vf", "scale=384:-1", "-frames:v", "1", str(f)], capture_output=True)
            if f.exists():
                frames.append(str(f))
        if len(frames) < 3:
            return None
        scores = llm.score_frames_subject(frames, subject)
        if not scores:
            return None
        # 주제가 뚜렷한 프레임(≥0.7)이 최소 1/4 이상이면 '충분히 나옴'으로 본다(전 구간일 필요 없음).
        strong = sum(1 for s in scores if s >= 0.7)
        return strong >= max(1, len(scores) // 4)


def _wreck_photo_footage(scientific_name: str, common_name_en: str, dest: Path, key: str) -> dict | None:
    """난파선: 그 배의 실사 사진을 찾아 켄번즈 영상화 → footage dict. 없으면 None.
    ★잠수사 위주 영상보다 '배가 확실히 보이는 사진'을 우선한다(주제 피사체 보장).
    질의 변형을 여러 개 시도해 사진 적중률을 높인다(그래도 없으면 상위는 영상 경로로 폴백)."""
    name = re.sub(r"^wreck\s+", "", scientific_name or "", flags=re.I).strip()
    got = None
    for q in (scientific_name, f"{name} shipwreck", f"{name} wreck dive", name, common_name_en):
        if q and q.strip():
            got = _commons_photo_search(q)
            if got:
                break
    if not got:
        return None
    cand = {"url": got["url"], "image_url": got["url"], "media_kind": "photo",
            "license": got["license"], "credit": got["credit"], "source": got.get("source", "")}
    return _fetch_photo_kenburns(cand, dest, key, common_name_en)


def _rep_license(licenses: list[str]) -> str:
    """혼합 라이선스 → 대표값(가장 강한 표시의무). 전부 통과 라이선스 전제."""
    ls = [(x or "").lower() for x in licenses]
    if any("by-sa" in x for x in ls):
        return "cc-by-sa"
    if any(x == "cc-by" or "by" in x for x in ls if "sa" not in x):
        return "cc-by"
    if any("cc0" in x for x in ls):
        return "cc0"
    return "public-domain"


def build_wreck_documentary(images: list[dict], dest_dir: str, target_dur: float = 42.0,
                            key: str = "wreck", overlays: dict | None = None) -> dict | None:
    """★침몰선 다큐 시퀀스(반복 제거): 서로 다른 이미지를 '취항→(초상)→사고→잔해' 순서로
    각기 다른 켄번즈 컷(9:16)으로 이어붙인 하나의 영상. 한 장 우려먹기를 대체한다.

    images: dossier.ordered_beat_images() 결과([{url,beat,credit,license,...}] 순서 보존).
    overlays: {beat: png_path} — 해당 비트 컷 위에 얹을 화면 카드(제원 카드 등, 선택).
    반환 {path, sequenced:True, credit, license, source, beats} 또는 None(이미지 없음/합성 실패).
    """
    import subprocess
    dest = Path(dest_dir); dest.mkdir(parents=True, exist_ok=True)
    imgs = [im for im in (images or []) if im.get("url")]
    if not imgs:
        return None
    overlays = overlays or {}
    n = len(imgs)
    per = max(3, int(math.ceil(target_dur / n)))     # 컷당 초(정수) — 합 ≥ target_dur → 다운스트림 무반복
    clips: list[str] = []
    used: list[dict] = []
    for i, im in enumerate(imgs):
        iext = next((e for e in _IMAGE_EXT if im["url"].lower().endswith(e)), ".jpg")
        img = dest / f"wdoc_{i}{iext}"
        if not (img.exists() and img.stat().st_size > 50_000) and not _download(im["url"], img):
            log.info("[footage] 다큐 이미지 다운로드 실패: %s", im["url"]); continue
        clip = dest / f"wdoc_clip_{i}.mp4"
        motion = _KENBURNS_MOTIONS[i % len(_KENBURNS_MOTIONS)]   # 컷마다 무브 교대(단조 방지)
        if not _kenburns_clip(str(img), str(clip), seconds=per, motion=motion, W=720, H=1280):
            continue
        # 비트 카드 오버레이(선택): 제원 카드 등을 그 컷 위에 얹는다(디졸브)
        ov = overlays.get(im.get("beat", ""))
        if ov and Path(ov).exists():
            card_clip = dest / f"wdoc_card_{i}.mp4"
            if _overlay_card(str(clip), ov, str(card_clip), per):
                clip = card_clip
                overlays.pop(im.get("beat", ""), None)   # 카드는 한 번만
        clips.append(str(clip)); used.append(im)
    if not clips:
        return None
    # concat(하드컷 — 켄번즈 무브 연속성으로 컷 전환이 자연스럽다)
    # ★경로는 반드시 절대경로(재발방지 · 실사고): 예전엔 cwd=dest로 실행하면서 -i·-out에는
    #   '원래 cwd 기준 상대경로'(work/wdoc/…)를 넘겨, ffmpeg가 cwd(=work/wdoc) 밑에서 다시
    #   해석해 work/wdoc/work/wdoc/… 로 이중 중첩 → "No such file"로 난파선 다큐가 전부 실패했다.
    #   → list 엔트리·-i·출력 모두 절대경로로 고정하고 cwd 의존을 제거한다.
    lst = (dest / "wdoc_list.txt").resolve()
    lst.write_text("".join(f"file '{Path(c).resolve()}'\n" for c in clips), encoding="utf-8")
    out = (dest / "wreck_documentary.mp4").resolve()
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                            "-i", str(lst), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
                            "-an", str(out)], timeout=600)
        if not (r.returncode == 0 and out.exists() and out.stat().st_size > 100_000):
            return None
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 다큐 concat 실패: %s", e); return None
    creds = sorted({im.get("credit", "") for im in used if im.get("credit")})
    log.info("[footage] 침몰선 다큐 시퀀스 %d컷(%s) 합성 완료", len(clips),
             "→".join(im.get("beat", "?") for im in used))
    return {"path": str(out), "sequenced": True, "logo_box": None,
            "license": _rep_license([im.get("license", "") for im in used]),
            "credit": " · ".join(creds)[:300], "source": "Wikimedia Commons",
            "beats": [im.get("beat", "") for im in used], "credits": creds}


def _overlay_card(base_v: str, card_png: str, out_v: str, dur: int) -> bool:
    """base 9:16 영상 위에 카드 PNG(같은 720폭)를 디졸브로 얹는다(컷 중반 노출)."""
    import subprocess
    show = max(2.0, dur * 0.66)
    st = max(0.3, (dur - show) / 2)
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", base_v, "-loop", "1", "-i", card_png,
             "-filter_complex",
             (f"[1:v]format=yuva420p,fade=t=in:st=0:d=0.4:alpha=1,"
              f"fade=t=out:st={show-0.4:.2f}:d=0.4:alpha=1,setpts=PTS+{st:.2f}/TB[cd];"
              f"[0:v][cd]overlay=0:0:enable='between(t,{st:.2f},{st+show:.2f})'[v]"),
             "-map", "[v]", "-t", str(int(dur)), "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-crf", "20", "-an", out_v], timeout=300)
        return r.returncode == 0 and Path(out_v).exists() and Path(out_v).stat().st_size > 80_000
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 카드 오버레이 실패: %s", e); return False


def _wreck_doc_footage(cand: dict, scientific_name: str) -> dict | None:
    """유명 난파선 다큐: dossier(위키 제원+커먼스 멀티이미지)를 확보해 doc 딕트로 반환.
    실제 시퀀스 합성은 파이프라인이 본문 길이를 안 뒤에 build_wreck_documentary로 수행한다.
    자료가 빈약하면 None → 상위 auto 후보 순회가 다음 대상으로 넘어간다(날조 방지)."""
    try:
        from src.categories.shipwreck import dossier as _dsr
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] dossier 모듈 로드 실패: %s", e); return None
    title = (cand.get("wiki_title")
             or re.sub(r"^wreck\s+", "", scientific_name or "", flags=re.I).strip())
    doss = _dsr.build_dossier(title)
    if not doss:
        log.info("[footage] 난파선 다큐 자료 빈약 → 스킵: %s", title)
        return None
    afl = (doss.get("beats", {}).get("afloat") or doss.get("images", []))
    hero = afl[0].get("url") if afl else None
    return {"doc": True, "dossier": doss, "hero_url": hero, "path": None, "logo_box": None,
            "license": _rep_license([im.get("license", "") for im in doss.get("images", [])]),
            "credit": " · ".join(doss.get("credits", []))[:300], "source": "Wikimedia Commons"}


def fetch_footage(scientific_name: str, common_name_en: str, dest_dir: str) -> dict | None:
    """종 실사 영상 확보 → {path, license, credit, source} 또는 None(확보 실패).

    실패 시 상위(파이프라인)는 이 종을 '실사 영상 미확보'로 판단해 중단/스킵한다(날조 방지).
    ★사진 소스(media_kind=photo, 난파선 무한 엔진)는 켄번즈로 영상화해 반환한다.
    """
    dest = Path(dest_dir)
    key = (scientific_name or "").strip().lower()
    cand = _SEED.get(key)
    if not cand:
        cand = _commons_search(scientific_name) or _commons_search(common_name_en)
    if not cand:
        log.info("[footage] 실사 영상 미확보: %s / %s", scientific_name, common_name_en)
        return None
    if cand.get("media_kind") == "wreck_doc":   # ★유명 난파선 다큐(여러 이미지 시간순 시퀀스)
        return _wreck_doc_footage(cand, scientific_name)
    if cand.get("media_kind") == "photo":   # ★사진 → 켄번즈 영상화(난파선 무한 공급)
        return _fetch_photo_kenburns(cand, dest, key, common_name_en)
    # ★난파선은 아마추어 다이빙 영상을 소스로 절대 쓰지 않는다(운영자 확정 · 재발방지 · 절대 위반 금지).
    #   실사고(Batelo Cantanhede): 다이빙 영상은 ①인트로 타이틀카드(다이빙스쿨 로고)가 통짜로 박혀
    #   OCR로 못 지우고 ②배는 안 나오고 잠수사만 ③짧은 클립 반복 → 영상 품질을 근본적으로 무너뜨렸다.
    #   따라서 난파선 소스는 (1)유명 난파선 다큐(실제 배 사진 시퀀스) 또는 (2)그 배의 사진 켄번즈만
    #   허용한다. 둘 다 실패하면 raw 영상으로 폴백하지 않고 None → auto 후보 순회가 다음 대상으로.
    if key.startswith("wreck "):
        wp = _wreck_photo_footage(scientific_name, common_name_en, dest, key)
        if wp:
            log.info("[footage] 난파선 → 사진 켄번즈(주제 피사체 보장)")
            return wp
        # 이름으로 유명 난파선 다큐 자동 승격 시도(위키 제원+커먼스 멀티이미지). 빈약하면 None.
        doc = _wreck_doc_footage({"wiki_title": ""}, scientific_name)
        if doc:
            log.info("[footage] 난파선 → 다큐 자동 승격(그 배 실제 사진들)")
            return doc
        log.info("[footage] 난파선 사진·다큐 미확보 → 아마추어 영상 폴백 금지, 스킵: %s", scientific_name)
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
        for p in (out, dest / f"footage_{slug}_trim{ext}", dest / f"footage_{slug}_trim.mp4"):
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
    # ★인트로/아웃트로 트림(번인 타이틀카드·크레딧 제거): 수동 trim=(앞초,뒤초) + **자동 카드
    #   탐지**를 합쳐 본편만 남긴다. 대다수 NOAA 클립은 수동 trim이 없어도 인트로 카드가 있는데
    #   (예: 심해붉은해파리 Psychedelic Medusa 앞 ~6초), 롱폼 콜드오픈이 이를 `-stream_loop`로
    #   반복 노출하던 심각한 사고가 있었다 → 자동 탐지로 카드 없는 소스를 강제한다(재발방지).
    trim = cand.get("trim")
    dur = _probe_dur(str(out))
    auto_head, auto_tail = _auto_trim_cards(str(out), dur) if dur else (0.0, 0.0)
    m_head, m_tail = (float(trim[0]), float(trim[1])) if trim else (0.0, 0.0)
    head, tail = max(m_head, auto_head), max(m_tail, auto_tail)   # 둘 중 큰 값(카드 확실 제거)
    if head > 0 or tail > 0:
        if dur and dur - head - tail > 8:   # 트림 후 최소 8초는 남아야 함
            # ★프레임 정확 트림(재발방지 · 핵심): 예전엔 `-c copy`로 잘랐는데, 스트림 카피는
            #   **키프레임 단위로만** 잘려(-ss 7이 앞쪽 키프레임 0초로 당겨짐) 인트로 타이틀카드
            #   (NOAA 로고+문구)·아웃트로 크레딧이 그대로 남았다(실제 킹크랩 영상에 카드가 반복
            #   노출된 사고). → 재인코딩으로 **정확히 head~(dur-tail)** 구간만 남긴다(.mp4).
            trimmed = dest / f"footage_{slug}_trim.mp4"
            keep = dur - head - tail
            import subprocess
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{head:.2f}",
                                "-i", str(out), "-t", f"{keep:.2f}",
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                                "-pix_fmt", "yuv420p", "-an", str(trimmed)])
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
    # ★피사체 가시성 게이트(Step1 · 빈 물/준비 컷 배제): '아무것도 안 보이는' 클립은 버린다.
    #   → auto 후보 순회가 다음(피사체 있는) 클립으로 넘어간다(텐트 쉬림프 '빈 물' 사고 방지).
    try:
        vis = subject_visibility(str(out))
        if vis < _MIN_VISIBILITY:
            return _reject(f"피사체 미검출(빈 물/준비 컷 · 가시성 {vis:.0f}<{_MIN_VISIBILITY:.0f})")
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 가시성 검사 생략(오류): %s", e)
    # ★Step2 의미검증(비전 LLM) — ★난파선 전용(하드 리젝트)으로 한정한다(운영자 확정 · 존폐 사고 재발방지).
    #   실사고: 생물에 학명(예: 'Holothuria leucospilota')을 주면 비전 LLM이 '그 종'인지 시각으로
    #   식별하지 못해(384px 프레임에서 종 단위 판별 불가) 진짜 생물 영상까지 전부 폐기 → 소싱한
    #   심해·해양생물이 100% 제작 실패했다(sepia/octopus/holothuria/plankton 전부).
    #   → 생물은 Step1(가시성)만으로 게이트한다(빈 물/준비 컷은 Step1이 이미 배제). Step2 종ID 폐지.
    #   난파선은 '다이버 vs 배'를 구조로만 구분할 수 없어 Step2를 유지(단, 난파선은 이제 다큐/사진
    #   경로라 이 영상 게이트에 거의 도달하지 않음).
    if key.startswith("wreck "):
        try:
            subj = "the sunken shipwreck structure itself (not only divers, bubbles, or open water)"
            verdict = footage_shows_subject(str(out), subj)
            if verdict is False:
                return _reject("주제 피사체 미검출(비전 LLM · 난파선: 다이버/빈물)")
        except Exception as e:  # noqa: BLE001
            log.warning("[footage] 난파선 의미검증 생략(오류): %s", e)
    # NOAA 소스는 좌상단 워터마크 영역 정보를 함께 반환(하류에서 회피/제거)
    logo = _NOAA_LOGO_BOX if "noaa" in (cand.get("credit", "") or "").lower() else None
    return {"path": str(out), "license": cand["license"],
            "credit": cand["credit"], "source": cand.get("source", ""),
            "logo_box": logo}
