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


# ★공개영상 소스 확대(운영자 요청 · NOAA 등 커먼스 밖 PD 영상): Internet Archive(archive.org)는
#   공개 JSON API + 직다운로드 URL을 제공해 자동화 가능하다(NOAA 포털은 API가 없어 자동화 불가 →
#   운영자 수동). 수익화 채널이라 저작권을 엄격히: ①유튜브·플리커 미러(출처 불명확)는 제외
#   ②명시적 PD/CC 라이선스 또는 확인된 미국 정부 업로더만 채택 ③거대 다이브 통짜 파일은 용량 상한.
_IA_GOV_RE = re.compile(r"\b(noaa|usgs|usfws|nasa|bureau of ocean|smithsonian|mbari)\b", re.I)
_IA_SKIP_PREFIX = ("youtube-", "flickr-")          # 미러(출처 불명확) 배제
_IA_MAX_BYTES = 220_000_000                        # ~220MB 상한(다이브 통짜 GB 파일 회피)


def _operator_footage(key: str, common_name_en: str = "") -> dict | None:
    """★운영자 수동 드롭 영상(최우선 소스 · 운영자 요청): NOAA 포털·유튜브 등 API로 자동화 못 하는
    풍부한 PD 영상을 운영자가 직접 받아 `assets/footage/<학명slug>.<mp4|webm|mov|mkv|m4v>`로 넣으면
    그 종 제작에 이 클립을 최우선으로 쓴다(자동 소싱보다 우선). 커먼스에 영상이 없는 종을 손으로 채우는
    확실한 길. 라이선스: 운영자가 PD/상업허용만 넣는다(NOAA=public-domain 크레딧). 없으면 None(자동 소싱)."""
    base = Path(__file__).resolve().parents[2] / "assets" / "footage"
    slug = re.sub(r"[^a-z0-9]+", "_", (key or common_name_en or "").lower()).strip("_")
    if not slug:
        return None
    for stem in (slug, (common_name_en or "").lower().replace(" ", "_")):
        for ext in (".mp4", ".webm", ".mov", ".mkv", ".m4v"):
            p = base / f"{stem}{ext}"
            if p.exists() and p.stat().st_size > 100_000:
                # 크레딧: 같은 이름의 .credit.txt 사이드카가 있으면 그것, 없으면 일반 PD 표기(오귀속 방지).
                sc = p.with_suffix(".credit.txt")
                credit = sc.read_text(encoding="utf-8").strip()[:120] if sc.exists() else "Public Domain"
                log.info("[footage] 운영자 드롭 영상 사용: %s (%s)", p, credit)
                return {"url": str(p), "license": "public-domain",
                        "credit": credit, "source": "operator: assets/footage"}
    return None


# ★NOAA Ocean Exploration 자동 소싱(운영자 목표 · 숨은 API 발굴): NCEI 비디오 포털은 공개 문서엔
#   API가 없다고 돼 있지만, 프론트엔드(callapi.js)를 뜯어보니 **ESRI Geoportal OpenSearch JSON API**를
#   호출한다. 이걸 직접 두들기면 종명으로 검색→그 종이 관측된 다이브를 특정→다이브 하이라이트 MP4
#   (퍼블릭도메인·직다운로드)를 얻는다. 실측: 'anglerfish' 115건, EX1708 DIVE21 → 640×360 h264 MP4.
_OER_OPENSEARCH = "https://www.ncei.noaa.gov/metadata/granule/geoportal/opensearch"
_OER_VIDEO_BASE = "https://www.ncei.noaa.gov/data/oceans/oer/video"


def _oer_compressed_listing(exp: str) -> tuple[str, list[str]]:
    """탐사(EX####)의 압축 하이라이트 폴더를 나열 → (base_url, [파일명]). 없으면 (base, [])."""
    base = f"{_OER_VIDEO_BASE}/{exp}/Video/Compressed/"
    try:
        import requests
        html = requests.get(base, headers={"User-Agent": _UA}, timeout=30).text
        return base, re.findall(r'href="([^"]+_Low\.mp4)"', html)
    except Exception:  # noqa: BLE001
        return base, []


def _noaa_oer_videos(query: str, n: int = 3) -> list[dict]:
    """★NOAA OER 자동 영상 소싱: 종명으로 OpenSearch→그 종 관측 다이브의 하이라이트 MP4(PD 직다운로드).
    반환 [{url, license:'public-domain', credit:'NOAA Ocean Exploration', source}]. 오류·미매치는 []."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        import requests
        d = requests.get(_OER_OPENSEARCH, headers={"User-Agent": _UA}, timeout=40,
                         params={"q": f"({q})", "start": 1, "max": n * 8,
                                 "orderBy": "title", "f": "pjson"}).json()
        results = d.get("results") or []
    except Exception as e:  # noqa: BLE001
        log.info("[footage] NOAA OER 검색 실패(%s): %s", q, e)
        return []
    listings: dict[str, tuple[str, list[str]]] = {}
    out: list[dict] = []
    seen: set = set()
    for r in results:
        src = r.get("_source", {}) or {}
        ident = src.get("apiso_Identifier_s") or ""
        m = re.match(r"(EX\d+)_DIVE(\d+)", ident)
        if not m:
            continue
        exp, dive = m.group(1), int(m.group(2))
        if exp not in listings:
            listings[exp] = _oer_compressed_listing(exp)
        base, files = listings[exp]
        if not files:
            continue
        pat = re.compile(rf"DIVE0*{dive}(?![0-9])", re.I)   # '_'가 word char라 \b 대신 (?!\d)
        match = [f for f in files if pat.search(f)]
        if not match:
            continue                                        # 그 다이브 하이라이트가 없으면 스킵(관련성 우선)
        url = base + match[0]
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "license": "public-domain", "credit": "NOAA Ocean Exploration",
                    "source": f"NOAA OER {exp} DIVE{dive:02d} ({_OER_OPENSEARCH})"})
        if len(out) >= n:
            break
    return out


def _archive_org_videos(query: str, n: int = 4) -> list[dict]:
    """Internet Archive에서 종 관련 **PD/CC 실사 영상**을 찾아 직다운로드 URL로 반환.
    저작권 안전(수익화): 유튜브·플리커 미러 제외 + (명시 PD/CC 라이선스 또는 미국 정부 업로더)만.
    반환: [{url, license, credit, source}] (없으면 []). 오류·오프라인은 무해([])."""
    q = (query or "").strip()
    if not q:
        return []
    out: list[dict] = []
    try:
        import requests
        sr = requests.get("https://archive.org/advancedsearch.php",
                          headers={"User-Agent": _UA}, timeout=25,
                          params=[("q", f'({q}) AND mediatype:movies'), ("rows", str(n * 4)),
                                  ("output", "json"), ("fl[]", "identifier"),
                                  ("fl[]", "licenseurl"), ("fl[]", "uploader"),
                                  ("fl[]", "collection"), ("fl[]", "title")]).json()
        docs = (sr.get("response") or {}).get("docs") or []
    except Exception as e:  # noqa: BLE001
        log.info("[footage] Internet Archive 검색 실패(%s): %s", q, e)
        return out
    for d in docs:
        ident = (d.get("identifier") or "").strip()
        if not ident or ident.lower().startswith(_IA_SKIP_PREFIX):
            continue
        # 저작권 판정: 명시 라이선스(_norm_license 통과) 우선, 없으면 정부 업로더/컬렉션만 PD로 인정.
        lic = _norm_license(d.get("licenseurl") or "")
        blob = f"{d.get('uploader', '')} {d.get('collection', '')} {ident}"
        if not lic:
            if _IA_GOV_RE.search(blob):
                lic = "public-domain"
            else:
                continue                                   # 근거 없는 라이선스는 채택 안 함(안전)
        try:                                               # 아이템 파일 목록 → 용량 상한 내 최대 영상
            md = requests.get(f"https://archive.org/metadata/{ident}",
                              headers={"User-Agent": _UA}, timeout=25).json()
        except Exception:  # noqa: BLE001
            continue
        vids = [f for f in (md.get("files") or [])
                if str(f.get("name", "")).lower().endswith(_VIDEO_EXT)
                and 300_000 < int(f.get("size") or 0) <= _IA_MAX_BYTES]
        if not vids:
            continue
        best = max(vids, key=lambda f: int(f.get("size") or 0))
        cred = "NOAA Ocean Exploration" if _IA_GOV_RE.search(blob) else (d.get("title") or ident)[:80]
        out.append({"url": f"https://archive.org/download/{ident}/{best['name']}",
                    "license": lic, "credit": f"{cred} · Internet Archive",
                    "source": f"https://archive.org/details/{ident}"})
        if len(out) >= n:
            break
    return out


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
    # ★로컬 파일(운영자 수동 드롭 등)은 복사로 처리(HTTP 아님).
    src = url[7:] if url.startswith("file://") else url
    if src and not src.lower().startswith(("http://", "https://")) and Path(src).exists():
        try:
            import shutil
            shutil.copyfile(src, dest)
            return dest.exists() and dest.stat().st_size > 10_000
        except Exception as e:  # noqa: BLE001
            log.warning("[footage] 로컬 파일 복사 실패 %s: %s", src, e)
            return False
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


def _commons_photo_candidates(query: str, n: int = 8, min_w: int = 1100, min_h: int = 800) -> list[dict]:
    """Commons 고해상 실사 사진 후보 여러 장(통과 라이선스) → [{url,license,credit,source}].
    ★히어로(오프닝훅·엔드카드)용: 여러 후보를 받아 상위(단일 피사체) 게이트로 고를 수 있게 한다."""
    out: list[dict] = []
    if not (query or "").strip():
        return out
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
            "titles": "|".join(titles[:30]),
            "iiprop": "url|size|extmetadata", "iiextmetadatafilter": "LicenseShortName|Artist",
        }).json()
        for page in info.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            if _NONSUBJECT_CAT_RE.search(title):      # 파일명 단계 오소싱(자동차·인물·도판어) 배제
                continue
            ii = (page.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = _norm_license(meta.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            w, h = ii.get("width", 0), ii.get("height", 0)
            if lic and url and any(url.lower().endswith(e) for e in _IMAGE_EXT) and w >= min_w and h >= min_h:
                artist = re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", "")).strip()
                cr = artist or "Wikimedia Commons"
                cr += " · CC BY-SA" if lic == "cc-by-sa" else (" · CC BY" if lic == "cc-by" else "")
                out.append({"url": url, "license": lic, "credit": cr, "source": title})
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 히어로 후보 검색 실패(%s): %s", query, e)
    return out[:n]


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
            "action": "query", "format": "json", "prop": "imageinfo|categories",
            "titles": "|".join(titles[:40]), "cllimit": "50",
            "iiprop": "url|size|extmetadata", "iiextmetadatafilter": "LicenseShortName|Artist",
        }).json()
        for page in info.get("query", {}).get("pages", {}).values():
            ii = (page.get("imageinfo") or [{}])[0]
            meta = ii.get("extmetadata", {})
            lic = _norm_license(meta.get("LicenseShortName", {}).get("value", ""))
            url = ii.get("url", "")
            w, h = ii.get("width", 0), ii.get("height", 0)
            # ★엉뚱한 피사체 배제(핵심 · 동음이의어 사고: Chimaera=물고기 속명이자 TVR 자동차):
            #   파일의 Commons 카테고리로 자동차·인물·미술품 등 비(非)생물을 거른다(실측 근거:
            #   차=Automobiles/Red roadsters, 물고기=Fish of…/학명). 카테고리는 같은 배치 호출로 받아 무비용.
            cats = " ".join(c.get("title", "") for c in page.get("categories", []) or [])
            if _NONSUBJECT_CAT_RE.search(cats) or _NONSUBJECT_CAT_RE.search(page.get("title", "")):
                log.info("[footage] 비생물 피사체 배제: %s", page.get("title", ""))
                continue
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


# ★비(非)생물 피사체 배제(동음이의어 오삽입 방지): 자동차·탈것·인물·미술품·건물 등. Commons 카테고리·
#   파일명에 이 단서가 있으면 그 사진을 쓰지 않는다(실사고: Chimaera 물고기에 TVR Chimaera 자동차 삽입).
_NONSUBJECT_CAT_RE = re.compile(
    r"automobile|roadster|\bcars?\b|\bvehicle|motorcycle|aircraft|airplane|\btrain\b|locomotive|"
    r"\bboat\b|firearm|\bweapon|\brifle|pistol|architecture|building|cathedral|castle|"
    r"sculptur|\bstatue|paintings?|\bdrawings?\b|engraving|lithograph|comics?|coins?|"
    r"\bstamps?\b|\bflags?\b|\blogos?\b|mytholog|\bactor|actress|politician|footballer|"
    r"\bTVR\b|Ferrari|Porsche|\bplayers?\b", re.I)


def _inaturalist_photos(scientific_name: str, n: int = 8) -> list[dict]:
    """★추가 소싱처(iNaturalist): 종명 → CC 라이선스 research-grade 관측 사진 [{url,license,credit,source}].
    Commons에 부족한 해양생물 실사를 넓게 보충한다(특히 얕은·연안·수족관 종). 심해종은 시민관측이
    드물어 적게 나오지만(무해), 일반 해양생물에선 크게 확대된다. CC0/CC-BY/CC-BY-SA만 채택(저작자 표기)."""
    sci = (scientific_name or "").strip()
    if not sci:
        return []
    _LIC = {"cc0": "cc0", "cc-by": "cc-by", "cc-by-sa": "cc-by-sa"}
    out: list[dict] = []
    seen: set = set()
    try:
        import requests
        d = requests.get("https://api.inaturalist.org/v1/observations",
                         headers={"User-Agent": _UA}, timeout=25, params={
                             "taxon_name": sci, "photo_license": "cc0,cc-by,cc-by-sa",
                             "quality_grade": "research", "photos": "true",
                             "per_page": str(max(10, n * 2)), "order_by": "votes"}).json()
    except Exception as e:  # noqa: BLE001
        log.info("[footage] iNaturalist 조회 실패(%s): %s", sci, e)
        return out
    for o in d.get("results", []):
        for ph in (o.get("photos") or []):
            lic = _LIC.get((ph.get("license_code") or "").lower())
            url = (ph.get("url") or "").replace("/square.", "/large.").replace("square", "large")
            if not (lic and url) or url in seen:
                continue
            seen.add(url)
            attr = re.sub(r"\s+", " ", (ph.get("attribution") or "").strip())[:120] or "iNaturalist"
            cr = attr if "inaturalist" in attr.lower() else f"{attr} · iNaturalist"
            out.append({"url": url, "license": lic, "credit": cr, "source": "iNaturalist"})
            break   # 관측당 대표 1장
        if len(out) >= n:
            break
    return out


def fetch_cutaway_photos(scientific_name: str, common_name_en: str, dest_dir: str,
                         n: int = 2, exclude_sources: tuple = ()) -> list[dict]:
    """본문 컷어웨이용 같은 대상 고해상 사진 최대 n장 확보 → [{path, credit, license}].
    같은 대상만(오정보 방지). exclude_sources(히어로 등)와 겹치는 파일은 제외. 없으면 [].
    ★다양성(운영자 요청): 짧은 영상이 반복될 때 컷어웨이를 여럿 넣으므로, n이 크면 커먼스뿐 아니라
    iNaturalist·Openverse까지 합쳐 '같은 대상'의 서로 다른 사진을 넉넉히 모은다(중복 URL 제거)."""
    ex = {s for s in exclude_sources if s}
    got = list(_commons_photos(scientific_name, n + len(ex) + 2) or _commons_photos(common_name_en, n + 2))
    if len(got) < n + len(ex):        # 부족하면 소스 확대(관측·집계 CC 사진)
        try:
            got += _inaturalist_photos(scientific_name, n) + _openverse_photos(scientific_name, n)
        except Exception:  # noqa: BLE001
            pass
        _seen: set = set()            # URL 중복 제거(소스 간 겹침)
        got = [g for g in got if g.get("url") and not (g["url"] in _seen or _seen.add(g["url"]))]
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
                          key: str = "", max_cover: float = 0.45) -> str:
    """본문(9:16, 자막 번인 전)에 같은 대상 고해상 사진 컷어웨이를 짧게 오버레이(디졸브).
    ★오디오·자막은 이후 단계에서 그대로 얹히므로 타이밍·자막 연속성이 보존된다(길이 불변).
    ★다양성(운영자 요청): 소스 영상이 짧아 반복될 때, **사진이 충분하면 컷어웨이 수를 늘려** 같은
    영상만 반복되는 피로를 깬다. 단, 컷어웨이 총합이 본문의 `max_cover`(기본 45%)를 넘지 않아 실제
    피사체 영상이 여전히 주가 되게 한다. 실패/사진없음 시 원본 body_v 그대로 반환(발행 불정지)."""
    import subprocess
    photos = [p for p in (photos or []) if p.get("path") and Path(p["path"]).exists()]
    if not photos or body_dur < 12:
        return body_v
    D = 2.0                                   # 컷어웨이 노출(디졸브 0.3 + 홀드 + 디졸브 0.3)
    # ★컷 수 = min(확보 사진 수, 커버상한으로 허용되는 수, 하드상한 6). 영상이 짧아 많이 반복될수록
    #   더 많은 사진을 넣지만, 총 커버가 본문의 45%를 넘지 않게(영상이 주·사진이 양념).
    n_by_cover = max(1, int(body_dur * max_cover / D))
    n = max(1, min(len(photos), n_by_cover, 6))
    # 창 위치: 본문 중반 70%(0.13~0.85)에 균등 배치(맨 앞/뒤 리빌 구간 회피 · 겹침 없게).
    if n == 1:
        fracs = [0.45]
    else:
        lo, hi = 0.13, 0.85
        fracs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
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

    ★단일 피사체 강제(운영자 확정 · 절대 위반 금지 · 실사고: 여러 종 도판이 엔드카드에 삽입):
    후보 여러 장을 받아 순서대로 ① 실사 사진성(`_looks_photographic`) ② **단일 개체 게이트**
    (`vision_subject.is_single_subject` — Gemini. 여러 종·도판·비교표·다중패널은 거부)를 통과한
    **첫 사진만** 히어로로 쓴다. 하나도 통과 못 하면 None → 상위는 **실제 영상 프레임**(진짜 단일
    피사체)으로 폴백(발행 불정지). ★비전 키가 없으면 '단일 확정 불가'로 보고 사진을 쓰지 않는다
    (도판 위험 회피 우선 · 영상 프레임 폴백이 안전)."""
    cands = _commons_photo_candidates(scientific_name, 8) or _commons_photo_candidates(common_name_en, 8)
    if not cands:
        return None
    try:
        from src.core import vision_subject
        vision_on = vision_subject.available()
    except Exception:  # noqa: BLE001
        vision_subject, vision_on = None, False
    dest = Path(dest_dir)
    key = (scientific_name or common_name_en or "hero").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_") or "hero"
    hint = scientific_name or common_name_en or ""
    for i, got in enumerate(cands):
        iext = next((e for e in _IMAGE_EXT if got["url"].lower().endswith(e)), ".jpg")
        out = dest / f"hero_{slug}_{i}{iext}"
        if not (out.exists() and out.stat().st_size > 50_000) and not _download(got["url"], out):
            continue
        if not _looks_photographic(str(out)):        # 삽화·흰배경 도판 배제
            continue
        # ★단일 개체 게이트: 비전 사용 가능하면 통과분만, 비전 없으면 사진 사용 안 함(도판 위험 회피).
        if vision_on:
            verdict = None
            try:
                verdict = vision_subject.is_single_subject(str(out), hint)
            except Exception:  # noqa: BLE001
                verdict = None
            if verdict is not True:                  # False(도판·다중) 또는 None(불확실) → 스킵
                continue
        else:
            # 비전 키 없음: 안전을 위해 히어로 사진을 쓰지 않는다(영상 프레임 폴백이 단일 피사체 보장).
            return None
        return {"path": str(out), "credit": got["credit"], "license": got["license"],
                "source": got.get("source", "")}
    return None


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


def _subject_crop(image_path: str, W: int, H: int) -> str | None:
    """★사진에서 피사체를 '학습'해 출력 종횡비(W:H)에 맞춘 크롭을 피사체 무게중심에 고정.
    켄번즈(중앙 줌) 전에 피사체를 프레임 중앙으로 옮겨, 세로(9:16) 프레임에서 넓은 사진의 좌우가
    잘려 피사체가 화면 밖으로 나가던 문제를 없앤다. 실패/미검출 시 None(원본 그대로 사용)."""
    try:
        from PIL import Image
        from src.core import reframe
        im = Image.open(image_path).convert("RGB")
        iw, ih = im.size
        if iw < 8 or ih < 8:
            return None
        # ★피사체 학습 3단(운영자 명령2 · 정확도 순): ① Gemini 비전(눈/몸통 정밀 좌표, 키 있으면)
        #   ② 휴리스틱 눈 검출 ③ 색무관 3단서 몸통 중심. 비전은 키 없으면 None → ②③ 폴백.
        focus = None
        try:
            from src.core import vision_subject
            focus = vision_subject.locate_focus(image_path)
        except Exception:  # noqa: BLE001
            focus = None
        if focus:
            cx, cy = focus
        else:
            eye = reframe._eye_focus(image_path)               # 눈 우선(사용자 규칙)
            if eye:
                cx, cy = eye
            else:
                cx, cy, _ = reframe._subject_focus(image_path)  # 색무관 3단서 검출(미검출 시 0.5,0.5)
        tar = W / H
        if iw / ih > tar:                                      # 이미지가 더 넓음 → 좌우(x) 크롭
            ch = ih; cw = max(8, int(round(ih * tar))); axis = "x"
        else:                                                  # 이미지가 더 높음 → 상하(y) 크롭
            cw = iw; ch = max(8, int(round(iw / tar))); axis = "y"
        if cw >= iw and ch >= ih:                              # 이미 목표 종횡비면 크롭 불필요
            return None
        # ★크롭되는 축에서 피사체가 '명백히' 치우쳤을 때만 이동(중앙 근처면 중앙크롭에 맡겨
        #   검출 노이즈로 이미 잘 잡힌 컷을 흔들지 않는다). 이동은 살짝 댐핑(0.85)해 과보정 방지.
        f = cx if axis == "x" else cy
        if abs(f - 0.5) < 0.12:
            return None
        cc = 0.5 + (f - 0.5) * 0.85
        if axis == "x":
            x0 = max(0, min(int(round(cc * iw - cw / 2)), iw - cw)); y0 = (ih - ch) // 2
        else:
            y0 = max(0, min(int(round(cc * ih - ch / 2)), ih - ch)); x0 = (iw - cw) // 2
        out = f"{Path(image_path).with_suffix('')}_subj_{W}x{H}.jpg"
        im.crop((x0, y0, x0 + cw, y0 + ch)).save(out, quality=92)
        return out
    except Exception as e:  # noqa: BLE001
        log.info("[footage] 피사체 크롭 생략(오류): %s", e)
        return None


def _kenburns_clip(image_path: str, out_path: str, seconds: int = 14, motion: str = "in",
                   W: int = 1280, H: int = 720) -> bool:
    """정지 사진 → 켄번즈 영상(W×H). ★난파선·미세조류 등 '정적 피사체' 사진의 무한 엔진.
    모션이 있어 정지-소스 게이트를 통과한다. motion=in/out/pan_r/pan_l로 줌 방향을 다양화해
    같은 소재가 반복돼도 매번 똑같은 느낌이 안 나게 한다(사진은 영상보다 훨씬 많아 공급이 사실상 무한).
    W,H로 16:9(본문 소스) 또는 9:16(본문 컷어웨이)을 선택한다.
    ★피사체 중심 프리크롭: 켄번즈 전에 피사체를 프레임 중앙에 고정(화면밖 이탈 방지)."""
    import subprocess
    src = _subject_crop(image_path, W, H) or image_path       # 피사체 학습·중앙 고정
    fr = int(seconds) * 30
    vf = _kenburns_vf(motion if motion in _KENBURNS_MOTIONS else "in", fr, W, H)
    try:
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", src,
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


def _normalize_doc_clip(src_v: str, out_v: str) -> bool:
    """사전 렌더 클립(지도 컷 등)을 다큐 켄번즈 컷과 동일 규격(720×1280·30fps·SAR1·무음)으로 재인코딩.
    concat 재인코딩 전 규격을 맞춰 컷 전환이 매끄럽게 이어지게 한다."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", src_v,
             "-vf", "scale=720:1280,setsar=1,fps=30,format=yuv420p",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-an", out_v],
            timeout=180)
        return r.returncode == 0 and Path(out_v).exists() and Path(out_v).stat().st_size > 50_000
    except Exception as e:  # noqa: BLE001
        log.warning("[footage] 다큐 영상 정규화 실패: %s", e); return False


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
    items = [im for im in (images or []) if im.get("url") or im.get("video")]
    if not items:
        return None
    overlays = overlays or {}
    # ── Phase 1: 각 항목 준비(이미지 다운로드 / 사전 렌더 영상 항목 확인) ────────────────
    #   ★video 항목: 미리 렌더된 9:16 클립(침몰 위치 지도 컷 등)을 시퀀스에 그대로 끼운다.
    prepared: list[dict] = []
    for i, im in enumerate(items):
        v = im.get("video")
        if v:
            if Path(v).exists() and Path(v).stat().st_size > 10_000:
                prepared.append({"kind": "vid", "src": v, "im": im, "dur": _probe_dur(v) or 3.0})
            else:
                log.info("[footage] 다큐 영상 항목 누락: %s", v)
            continue
        local = im.get("image_path")             # 사진 다큐: 이미 내려받아 검증한 로컬 파일 재사용
        if local and Path(local).exists() and Path(local).stat().st_size > 50_000:
            prepared.append({"kind": "img", "src": local, "im": im}); continue
        iext = next((e for e in _IMAGE_EXT if im["url"].lower().endswith(e)), ".jpg")
        img = dest / f"wdoc_{i}{iext}"
        if not (img.exists() and img.stat().st_size > 50_000) and not _download(im["url"], img):
            log.info("[footage] 다큐 이미지 다운로드 실패: %s", im["url"]); continue
        prepared.append({"kind": "img", "src": str(img), "im": im})
    if not prepared:
        return None
    # ── Phase 2: 이미지 컷 길이 배분 ─────────────────────────────────────────────────
    #   ★합을 target에 근접시켜 뒤쪽(잔해) 컷이 트림으로 잘려나가지 않게 한다(운영자 확정 · 재발방지).
    #   예전엔 per=max(3,ceil(target/n))으로 총합이 target보다 과하게 넘쳐(예: 40s vs 31s),
    #   파이프라인이 body_dur로 트림할 때 마지막 잔해 컷들이 통째로 잘렸다(수중 컷이 적게 보인 원인).
    #   → 컷당 최소 2초를 보장하되 뒤 컷에 +1초를 배분해 총합을 target 바로 위로 맞춘다.
    vids_dur = sum(p["dur"] for p in prepared if p["kind"] == "vid")
    m = sum(1 for p in prepared if p["kind"] == "img")
    base = extra = 0
    if m:
        img_target = max(2.0 * m, float(target_dur) - vids_dur)   # 컷당 최소 2초
        base = max(2, int(img_target // m))
        extra = min(m, max(0, int(math.ceil(img_target - base * m))))
    # ── Phase 3: 클립 생성(순서 유지) ───────────────────────────────────────────────
    clips: list[str] = []
    used: list[dict] = []
    img_idx = 0
    t_cursor = 0.0            # 시퀀스 내 누적 시각(지도 컷 SFX 타이밍용)
    map_start = None          # 지도(map) 컷 시작 시각 — 파이프라인이 이 시각에 스캔/락온 SFX를 믹스
    for p in prepared:
        im = p["im"]
        if p["kind"] == "vid":
            clip = dest / f"wdoc_vid_{len(clips)}.mp4"
            if _normalize_doc_clip(p["src"], str(clip)):     # 켄번즈 컷과 규격 통일(720×1280·30fps·무음)
                if im.get("beat") == "map" and map_start is None:
                    map_start = round(t_cursor, 2)
                clips.append(str(clip)); used.append(im)
                t_cursor += float(p.get("dur") or 0.0)
            continue
        per = base + (1 if img_idx >= m - extra else 0)       # 뒤(사고·잔해) 컷에 +1초
        img_idx += 1
        clip = dest / f"wdoc_clip_{len(clips)}.mp4"
        motion = _KENBURNS_MOTIONS[len(clips) % len(_KENBURNS_MOTIONS)]   # 컷마다 무브 교대(단조 방지)
        if not _kenburns_clip(p["src"], str(clip), seconds=per, motion=motion, W=720, H=1280):
            continue
        # 비트 카드 오버레이(선택): 제원 카드 등을 그 컷 위에 얹는다(디졸브)
        ov = overlays.get(im.get("beat", ""))
        if ov and Path(ov).exists():
            card_clip = dest / f"wdoc_card_{len(clips)}.mp4"
            if _overlay_card(str(clip), ov, str(card_clip), per):
                clip = card_clip
                overlays.pop(im.get("beat", ""), None)   # 카드는 한 번만
        clips.append(str(clip)); used.append(im)
        t_cursor += float(per)
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
            "beats": [im.get("beat", "") for im in used], "credits": creds,
            "map_start": map_start}   # 지도 컷 시작 시각(없으면 None) — 파이프라인 SFX 믹스용


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


def _fetch_video_footage(scientific_name: str, common_name_en: str, dest_dir: str) -> dict | None:
    """종 실사 **영상** 확보 → {path, license, credit, source} 또는 None(영상 확보 실패).
    ★사진 소스(media_kind=photo, 난파선 무한 엔진)는 켄번즈로 영상화해 반환한다.
    (실사 사진 다큐 폴백은 상위 래퍼 `fetch_footage`가 담당 — 영상 우선·없으면 이미지.)
    """
    dest = Path(dest_dir)
    key = (scientific_name or "").strip().lower()
    cand = _operator_footage(key, common_name_en)   # ★운영자 수동 드롭 최우선(있으면 그 클립 사용)
    if not cand:
        cand = _SEED.get(key)
    if not cand:
        cand = _commons_search(scientific_name) or _commons_search(common_name_en)
    if not cand and not key.startswith("wreck "):
        # ★커먼스에 없으면 자동 확장(운영자 목표): ①NOAA OER(숨은 geoportal API·종명 검색·PD 하이라이트)
        #   ②Internet Archive(안전필터). 아래 공통 다운로드·종횡비·정지·워터마크 게이트를 그대로 통과해야 채택.
        ext = (_noaa_oer_videos(scientific_name) or _noaa_oer_videos(common_name_en)
               or _archive_org_videos(scientific_name) or _archive_org_videos(common_name_en))
        if ext:
            cand = ext[0]
            log.info("[footage] 확장 소스 후보 채택: %s (%s)", cand["source"], cand["license"])
    if not cand:
        log.info("[footage] 실사 영상 미확보: %s / %s", scientific_name, common_name_en)
        return None
    if cand.get("media_kind") == "wreck_doc":   # ★유명 난파선 다큐(여러 이미지 시간순 시퀀스)
        return _wreck_doc_footage(cand, scientific_name)
    if cand.get("media_kind") == "photo":   # ★사진 후보 → 영상화
        # ★운영자 확정(절대 위반 금지): 생물은 **한 장짜리 켄번즈 영상 제작 금지**(단조로움).
        #   반드시 실사 4장 이상을 시간순 다큐 시퀀스로 만든다(_PHOTODOC_MIN=4). 4장을 못 채우면
        #   여기서 None을 돌려 소싱 목록에서 자동 제외되게 한다(단일 이미지 폴백 폐기).
        #   난파선은 아래 전용 사진 경로(_wreck_photo_footage)가 처리하므로 여기서 걸리지 않는다.
        if not (scientific_name or "").strip().lower().startswith("wreck "):
            doc = species_photo_doc(scientific_name, common_name_en, dest_dir)
            if doc:
                return doc
            log.info("[footage] 생물 실사 4장 미확보 → 단일 이미지 폴백 폐기, 스킵: %s / %s",
                     scientific_name, common_name_en)
            return None
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


# ── 실사 사진 다큐(영상 미확보 생물 → 여러 실사 이미지 켄번즈 시퀀스) ────────────────────
_PHOTODOC_MIN = 4          # 실사 최소 장수(운영자 확정: '1장 영상' 절대 금지 → 실사 4장↑만 제작·소싱)
_PHOTODOC_MAX = 7          # 시퀀스 최대 컷 수(다양한 컷)
_PHOTODOC_MIN_STRUCT = 12.0   # 이미지 최소 구조변별(macro std) — 밋밋한(빈) 표본 컷 배제
#   실측: 좋은 실사 14.8~85, 빈 표본 매크로 1.2~3.1 → 12가 안전한 경계. 좋은 사진이 4장 미만인
#   종(빈약한 소스)은 자동으로 제작 대상에서 빠진다(나쁜 영상 방지).
# 실사 필터: 삽화·도판·표본·오래된(–1949) 그림을 배제(살아있는 생물 다큐엔 실사만).
_NONPHOTO_RE = re.compile(
    r"illustration|drawing|\bplate\b|lithograph|vintage|poster|engraving|sketch|"
    r"painting|diagram|woodcut|etching|\bholotype\b|\bdried\b|dissect|\bjar\b|"
    r"\b(1[5-8]\d\d|19[0-4]\d)\b", re.I)


def _is_realistic_photo(p: dict) -> bool:
    """1차(메타데이터) 실사 필터: 파일명·크레딧에 삽화/도판/오래된-그림 단서가 없으면 True."""
    return not _NONPHOTO_RE.search(f"{p.get('credit', '')} {p.get('url', '')}")


def _looks_photographic(path: str) -> bool:
    """2차(시각) 실사 필터: 실제 픽셀로 '사진 vs 삽화·도판'을 가른다. 파일명에 단서가 없는
    흑백/세피아 도판(예: Carl Chun 1903 판)이 종이 흰 배경 위에 그려진 것을 배제한다.
    실측 근거: 실사(수중·표본)는 흰 배경이 거의 없음(0~19%). 도판은 흰 배경 70%+.
    검사 실패 시 True(막지 않음 — 검사 오류로 제작 차단하지 않음)."""
    try:
        from PIL import Image, ImageStat
        im = Image.open(path).convert("RGB").resize((96, 96))
    except Exception:  # noqa: BLE001
        return True
    hsv = im.convert("HSV")
    mean_s = ImageStat.Stat(hsv.getchannel("S")).mean[0]         # 평균 채도
    hist = hsv.getchannel("V").histogram()                      # 명도 히스토그램(256)
    white = sum(hist[236:]) / max(1, sum(hist))                 # 밝은(종이) 배경 비율
    if white > 0.55:                       # 넓은 흰/종이 배경 = 도판·삽화·고립 스캔
        return False
    if mean_s < 12 and white > 0.25:       # 흑백 라인드로잉
        return False
    return True


def _openverse_photos(query: str, n: int = 8) -> list[dict]:
    """★추가 소싱처(Openverse · 키 불필요): Flickr·스미소니언·박물관 등 여러 기관의 CC 이미지를
    한곳에서 집계. 종명으로 검색해 CC0/BY/BY-SA 고해상만 채택 → [{url,license,credit,source}].
    Commons·iNaturalist로 부족한 실사 풀을 넓힌다(저작자·라이선스 표기 유지)."""
    q = (query or "").strip()
    if not q:
        return []
    _LIC = {"cc0": "cc0", "pdm": "public-domain", "by": "cc-by", "by-sa": "cc-by-sa"}
    out: list[dict] = []
    try:
        import requests
        d = requests.get("https://api.openverse.org/v1/images/", headers={"User-Agent": _UA},
                         timeout=25, params={"q": q, "license": "cc0,pdm,by,by-sa",
                                             "page_size": str(max(10, n * 2)), "mature": "false"}).json()
    except Exception as e:  # noqa: BLE001
        log.info("[footage] Openverse 조회 실패(%s): %s", q, e)
        return out
    for r in d.get("results", []):
        lic = _LIC.get((r.get("license") or "").lower())
        url = r.get("url") or ""
        w, h = r.get("width") or 0, r.get("height") or 0
        if not (lic and url) or not any(url.lower().endswith(e) for e in _IMAGE_EXT):
            continue
        if w and h and (max(w, h) < 800 or min(w, h) < 480):   # 썸네일 배제(치수 미상은 통과 후 판단)
            continue                                            #   9:16 켄번즈(720×1280)엔 장변 800px면 충분
        cr = (r.get("creator") or "").strip()
        src = (r.get("source") or "openverse").strip()
        credit = " · ".join([x for x in (cr, src, {"cc-by": "CC BY", "cc-by-sa": "CC BY-SA"}.get(lic, "")) if x])
        out.append({"url": url, "license": lic, "credit": credit or "Openverse", "source": f"openverse:{src}"})
        if len(out) >= n:
            break
    return out


def _korea_public_photos(scientific_name: str, common_name_en: str, n: int = 6) -> list[dict]:
    """★한국 공공누리(KOGL) 소싱: 국립생물자원관 '국가생물종지식정보시스템' 등 공공 이미지.
    data.go.kr 서비스키(`DATA_GO_KR_KEY`)가 있으면 조회, 없으면 [](운영자 미설정 시 조용히 건너뜀).
    공공누리 제1유형은 상업 이용 허용(출처 표기) → 라이선스 게이트 통과(kogl-type1).
    ★국내 해양·수산 공공기관 자료를 적극 활용(운영자 요청)."""
    import os
    key = os.environ.get("DATA_GO_KR_KEY")
    if not key:
        return []
    out: list[dict] = []
    try:
        import requests
        # 국립생물자원관 생물종 검색(학명 우선) → 대표 이미지 URL. 데이터셋별 스키마가 달라
        # 운영자가 엔드포인트를 확정해 연결한다(아래는 표준형: serviceKey + 학명 파라미터).
        d = requests.get("https://apis.data.go.kr/1480523/NIBRSpeciesInfoService/searchSpecies",
                         timeout=25, headers={"User-Agent": _UA},
                         params={"serviceKey": key, "st": "1", "sw": scientific_name,
                                 "numOfRows": str(n), "_type": "json"}).json()
        items = (((d.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
        if isinstance(items, dict):
            items = [items]
        for it in items:
            url = it.get("imgUrl") or it.get("img_url") or ""
            if url and any(url.lower().endswith(e) for e in _IMAGE_EXT):
                out.append({"url": url, "license": "kogl-type1",
                            "credit": f"{it.get('reg_agncy', '국립생물자원관')} · 공공누리 제1유형",
                            "source": "data.go.kr:NIBR"})
            if len(out) >= n:
                break
    except Exception as e:  # noqa: BLE001
        log.info("[footage] 공공누리(data.go.kr) 조회 실패(%s): %s", scientific_name, e)
    return out


def species_photo_doc(scientific_name: str, common_name_en: str, dest_dir: str) -> dict | None:
    """★영상 미확보 생물 → 실사 사진 여러 장을 확보(라이선스+실사 필터). 4장 이상이면 사진 다큐로
    제작 가능. 실제 시퀀스 합성은 파이프라인이 본문 길이를 안 뒤 build_wreck_documentary로 수행한다
    (난파선 다큐와 동일 엔진). 부족하면 None(→ 제작 안 함 · 날조 없음).

    반환: {photo_doc:True, photos:[{url,beat,license,credit}], hero_url, license, credit, source, path:None}.
    """
    # ★소싱처 다변화(운영자 확정): 여러 CC 소스를 합쳐 실사 풀을 넓힌다 — 한 종에 이미지가 많아야
    #   '1장 우려먹기'가 아니라 다양한 컷의 다큐가 된다.
    #   ① Wikimedia Commons ② iNaturalist(관측) ③ Openverse(Flickr·스미소니언 등 집계·키불필요)
    #   ④ 한국 공공누리(data.go.kr 키 있으면) — 국내 해양·수산 공공자료.
    got = (_commons_photos(scientific_name, 12) or [])
    got += _inaturalist_photos(scientific_name, 10)
    got += _openverse_photos(scientific_name, 10)
    got += _korea_public_photos(scientific_name, common_name_en, 6)
    if len({p["url"] for p in got if p.get("url")}) < _PHOTODOC_MIN * 2:
        got += _commons_photos(common_name_en, 8) or []
        got += _openverse_photos(common_name_en, 6) or []
    _seen: set = set()                                        # URL 중복 제거(소스 간 겹침 정리)
    got = [p for p in got if p.get("url") and not (p["url"] in _seen or _seen.add(p["url"]))]
    cand = [p for p in got if _is_realistic_photo(p)]          # 1차: 메타데이터 필터
    if len(cand) < _PHOTODOC_MIN:
        log.info("[footage] 실사 후보 부족(1차 %d<%d) → 사진 다큐 스킵: %s",
                 len(cand), _PHOTODOC_MIN, scientific_name or common_name_en)
        return None
    # 2차: 실제 내려받아 '사진 vs 삽화·도판' 시각 판별(흰 배경 도판 배제). 통과분만 채택.
    chk = Path(dest_dir) / "photocheck"; chk.mkdir(parents=True, exist_ok=True)
    good: list[dict] = []
    for i, p in enumerate(cand):
        iext = next((e for e in _IMAGE_EXT if p["url"].lower().endswith(e)), ".jpg")
        fp = chk / f"chk_{i}{iext}"
        if not (fp.exists() and fp.stat().st_size > 50_000) and not _download(p["url"], fp):
            continue
        if not _looks_photographic(str(fp)):
            continue
        try:                                   # 밋밋한(빈) 표본 매크로 컷 배제(구조변별)
            from PIL import Image as _Im
            if _frame_macro_std(_Im.open(fp)) < _PHOTODOC_MIN_STRUCT:
                continue
        except Exception:  # noqa: BLE001
            pass
        # ★피사체 학습·검증(운영자 명령2 · 키 있을 때만): 동음이의어 오소싱(예 Chimaera=물고기이자
        #   TVR 자동차)을 대분류로 걸러낸다. 종ID는 안 함(진짜 생물 보존) — False(명백한 비생물)만 배제.
        try:
            from src.core import vision_subject
            if vision_subject.verify_species(str(fp), scientific_name, common_name_en) is False:
                continue
        except Exception:  # noqa: BLE001
            pass
        good.append({**p, "image_path": str(fp)})
        if len(good) >= _PHOTODOC_MAX:
            break
    if len(good) < _PHOTODOC_MIN:
        log.info("[footage] 실사 사진 부족(2차 %d<%d) → 사진 다큐 스킵: %s",
                 len(good), _PHOTODOC_MIN, scientific_name or common_name_en)
        return None
    seq = [{"url": g["url"], "image_path": g["image_path"], "beat": f"p{i}",
            "license": g["license"], "credit": g.get("credit", "")} for i, g in enumerate(good)]
    log.info("[footage] 실사 사진 다큐 후보 확보: %s (실사 %d장)", scientific_name, len(seq))
    return {"photo_doc": True, "photos": seq, "hero_url": good[0].get("image_path") or good[0]["url"],
            "path": None, "logo_box": None, "license": _rep_license([g["license"] for g in good]),
            "credit": " · ".join(sorted({g.get("credit", "") for g in good if g.get("credit")}))[:300],
            "source": "Wikimedia Commons"}


def fetch_footage(scientific_name: str, common_name_en: str, dest_dir: str) -> dict | None:
    """종 실사 소스 확보 → {path|photo_doc, license, credit, source} 또는 None.

    ★영상 우선·없으면 이미지(운영자 확정): 실사 영상을 먼저 시도하고, 영상이 없거나 게이트에 탈락하면
    같은 종의 **실사 사진 여러 장을 켄번즈 시퀀스**로 만들 수 있는지(사진 다큐) 확인해 폴백한다.
    이미지가 Commons에 훨씬 많아(영상 0개인 심해종 다수) 제작 가능 풀이 크게 늘어난다.
    실패 시 상위(파이프라인)는 '실사 미확보'로 판단해 중단/스킵한다(날조 방지).
    """
    v = _fetch_video_footage(scientific_name, common_name_en, dest_dir)
    if v:
        return v
    # 난파선은 사진 다큐(그 배 전용) 경로가 이미 _fetch_video_footage 안에 있으므로 여기선 생물만.
    if (scientific_name or "").strip().lower().startswith("wreck "):
        return None
    doc = species_photo_doc(scientific_name, common_name_en, dest_dir)
    if doc:
        log.info("[footage] 영상 미확보 → 실사 사진 다큐로 폴백: %s", scientific_name)
    return doc
