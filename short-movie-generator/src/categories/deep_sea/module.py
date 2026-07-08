"""deep_sea 카테고리 모듈 — CategoryModule 계약 구현.

소싱: NOAA 퍼블릭도메인 이미지 다운로드 시도 → 실패 시 합성 테스트 플레이스홀더(cc0).
정확성 게이트: accuracy_flags 위배 + 금지 픽션 요소(사람/난파선 등) 검사.
캡션: Gemini 훅(키 있으면) → 없으면 결정적 템플릿 폴백.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from src.categories.deep_sea import copywriter, data, prompts
from src.core.contracts import (
    CaptionData,
    CutSpec,
    PipelineError,
    RawAsset,
    Situation,
    SpeciesInfo,
)

log = logging.getLogger(__name__)

# 종 특정 실사 이미지 소싱: 학명/영문명으로 위키미디어 커먼스 → GBIF 미디어를 조회해
# '그 종의' 퍼블릭도메인/CC0/CC-BY 이미지를 가져온다. (이전엔 단일 하드코딩 URL이라
# 어떤 종이든 같은 덤보문어 사진이 들어가는 치명적 버그가 있었음 → 종별 조회로 해결.)
_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_GBIF_API = "https://api.gbif.org/v1/occurrence/search"
_UA = "DeepDiveLogBot/1.0 (deep-sea shorts; educational; +github.com/jtaechul/Product)"
_IMG_MIN_SIDE = 360  # 이보다 작은 이미지는 아이콘/썸네일로 간주해 제외

# 금지 픽션/윤리 요소 (spec 13장) — 어간 단위 정규식(어형 변화·우회 차단).
# 픽션(사람·난파선·보물·괴물·과장 크기) + 안 하는 포식(공격/사냥/포식 어간).
_BANNED_RE = re.compile(
    r"\b(diver|divers|human|humans|treasure|shipwreck|monster|giant|colossal|"
    r"attack\w*|hunt\w*|prey|preying|predat\w*|devour\w*|maul\w*)\b",
    re.IGNORECASE,
)
# 발광 표현 (bioluminescent=False 종에서 금지) — 동의어 포함. '발광'은 별도 검사.
_GLOW_RE = re.compile(
    r"\b(biolumin\w*|glow\w*|luminescen\w*|luminous|photophore\w*|phosphoresc\w*|"
    r"light[- ]producing|light organ\w*)\b",
    re.IGNORECASE,
)


def _meta(ext: dict, key: str) -> str:
    return str((ext.get(key) or {}).get("value", "")) if isinstance(ext.get(key), dict) else ""


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def _map_cc_license(raw: str) -> str | None:
    """커먼스/GBIF 라이선스 문자열 → 게이트 통과값(public-domain/cc0/cc-by). sa·nc·불명은 None(차단)."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    if "nc" in s or "noncommercial" in s or "non-commercial" in s:
        return None  # 비상업 차단
    if "sa" in s or "share" in s and "alike" in s or "sharealike" in s:
        return None  # 동일조건변경허락(SA) 차단
    if "cc0" in s or "zero" in s:
        return "cc0"
    if s.startswith("pd") or "publicdomain" in s or "public domain" in s or "public-domain" in s:
        return "public-domain"
    # 순수 CC-BY (버전 유무 무관): 'cc-by', 'cc by 4.0', '.../licenses/by/4.0/' 등
    if re.search(r"cc[ _-]?by(?![ _-]?(sa|nc))", s) or re.search(r"/licenses/by/", s):
        return "cc-by"
    return None


# 오래된 도판·삽화·박제 표본 등을 후순위로 미루기 위한 키워드 (실사 사진 우선)
_ILLUS_RE = re.compile(
    r"(plate|illustration|drawing|lithograph|engraving|sketch|painting|woodcut|"
    r"ichthyolog|historiae|naturelle|18\d\d|17\d\d|museum|specimen jar|preserved|"
    r"skeleton|fossil|stamp|logo|map|diagram|chart)", re.IGNORECASE)


def _photo_score(title: str, artist: str, mime: str, rank: int) -> float:
    """커먼스 후보를 '실사 사진'일 가능성으로 점수화 (높을수록 우선)."""
    blob = f"{title} {artist}".lower()
    score = 20.0 - min(rank, 19)          # 검색 랭크 반영(상위일수록 +)
    if "noaa" in blob or "mbari" in blob or "okeanos" in blob:
        score += 8                         # 심해 실사 출처 강한 선호
    if mime == "image/jpeg":
        score += 3                         # 사진은 대개 JPEG
    if _ILLUS_RE.search(blob):
        score -= 12                        # 삽화·도판·박제·지도 등 강한 후순위
    return score


def _download_image(url: str, dest: Path) -> bool:
    """URL 이미지를 받아 검증 후 JPEG로 정규화 저장. (다운스트림 ffmpeg·PIL·비전 호환 보장)"""
    import io

    import requests
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=30)
        if r.status_code != 200 or len(r.content) < 2000:
            return False
        from PIL import Image
        im = Image.open(io.BytesIO(r.content)).convert("RGB")
        if min(im.size) < _IMG_MIN_SIDE:  # 아이콘·썸네일 배제
            return False
        im.save(str(dest), "JPEG", quality=90)
        return True
    except Exception as e:  # noqa: BLE001
        log.info("[소싱] 이미지 다운로드/정규화 실패(%s): %s", url[:80], e)
        return False


class DeepSeaCategory:
    category_id = "deep_sea"
    style_profile = "deep_sea_realism"
    series_title = "심해 도감"  # 시리즈 브랜딩 (엔드카드·캡션 회차 표기)
    # 게시물(카드뉴스) 동시 제작 일시 중단 — 나레이션 야생다큐 전환 집중(재개: True).
    # 캐러셀 코드(carousel.py)·레코드 post 스키마·관리자 표시는 그대로 보존.
    generate_post = False

    # --- 입력/정보 ---
    def parse_input(self, query: str) -> str:
        q = (query or "").strip()
        # 자동 모드: 'auto' 또는 'auto:benthos|plankton|nekton' → AI가 실존 종 자동 추천(중복 방지)
        if q.lower() == "auto" or q.lower().startswith("auto:"):
            from src.categories.deep_sea import suggest
            cat = q.split(":", 1)[1].strip().lower() if ":" in q else ""
            return suggest.pick(cat)
        key = data.resolve_key(q)
        if key is None:
            raise PipelineError(
                "input", f"미등록 종: {query!r} (자동 추천은 'auto:benthos' 형식 사용)"
            )
        return key

    def get_info(self, subject_query: str) -> SpeciesInfo:
        sp = data.SPECIES[subject_query]
        return SpeciesInfo(
            scientific_name=sp["scientific_name"],
            common_name_ko=sp["common_name_ko"],
            common_name_en=sp["common_name_en"],
            depth_range_m=sp["depth_range_m"],
            distribution=sp["distribution"],
            habitat=sp["habitat"],
            diet=sp["diet"],
            fun_facts=sp["fun_facts"],
            sources=sp["sources"],
        )

    # --- 소싱 (종 특정 실사 이미지) ---
    def source_assets(self, info: SpeciesInfo, raw_dir: str) -> list[RawAsset]:
        raw = Path(raw_dir)
        raw.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "_", info.common_name_en.lower()).strip("_") or "specimen"
        dest = raw / f"{slug}.jpg"

        # 1) '그 종의' 실사 이미지: 위키미디어 커먼스 → GBIF (학명·영문명으로 조회, 라이선스 게이트)
        hit = self._fetch_species_photo(info, dest)
        if hit:
            log.info("[소싱] 종 특정 이미지 확보: %s (%s, %s)",
                     info.common_name_en, hit["source"], hit["license"])
            return [
                RawAsset(
                    asset_path=str(dest), source=hit["source"], license=hit["license"],
                    credit_string=hit["credit"], source_url=hit["url"], caption_text="",
                )
            ]

        # 2) 폴백: 합성 심해 플레이스홀더(자체 생성 → cc0). 실사 미확보 시에만.
        log.warning("[소싱] 종 특정 실사 미확보(%s) → 합성 플레이스홀더(cc0). 실사 교체 권장.",
                    info.common_name_en)
        self._synthetic_placeholder(dest, info.common_name_en)
        return [
            RawAsset(
                asset_path=str(dest),
                source="SYNTHETIC-TEST",
                license="cc0",
                credit_string="Illustration (self-generated, CC0) — 실사 교체 필요",
                source_url="local://synthetic",
                caption_text="",
            )
        ]

    def _fetch_species_photo(self, info: SpeciesInfo, dest: Path) -> dict | None:
        """학명·영문명으로 커먼스→GBIF를 조회해 통과 라이선스의 종 특정 이미지를 dest(JPEG)로 저장."""
        try:
            import requests  # noqa: F401
        except ImportError:
            return None
        sci = (info.scientific_name or "").strip()
        en = (info.common_name_en or "").strip()
        # 학명이 가장 정확 → 영문 통용명 순. 커먼스 우선(정제된 도감 이미지), GBIF 보조.
        for q in [s for s in (sci, en) if s]:
            hit = self._commons_photo(q, dest)
            if hit:
                return hit
        if sci:
            hit = self._gbif_photo(sci, dest)
            if hit:
                return hit
        return None

    def _commons_photo(self, query: str, dest: Path) -> dict | None:
        import requests
        params = {
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": query, "gsrnamespace": "6", "gsrlimit": "20",
            "prop": "imageinfo", "iiprop": "url|extmetadata|mime|size", "iiurlwidth": "1400",
        }
        try:
            r = requests.get(_COMMONS_API, params=params, headers={"User-Agent": _UA}, timeout=25)
            if r.status_code != 200:
                return None
            pages = list((r.json().get("query", {}).get("pages", {}) or {}).values())
        except Exception as e:  # noqa: BLE001
            log.info("[소싱] 커먼스 조회 예외(%s): %s", query, e)
            return None
        # 통과 라이선스 후보를 모아 '실사 사진' 우선으로 점수화(오래된 도판·삽화 후순위) → 최고점부터 시도
        cands = []
        for pg in pages:
            ii = (pg.get("imageinfo") or [{}])[0]
            if ii.get("mime", "") not in ("image/jpeg", "image/png"):
                continue
            ext = ii.get("extmetadata", {}) or {}
            lic = _map_cc_license(_meta(ext, "License") or _meta(ext, "LicenseShortName"))
            if not lic:
                continue
            url = ii.get("thumburl") or ii.get("url")
            if not url:
                continue
            artist = _strip_html(_meta(ext, "Artist"))
            cands.append({
                "url": url, "lic": lic, "artist": artist,
                "score": _photo_score(pg.get("title", ""), artist, ii.get("mime", ""),
                                      pg.get("index", 999)),
            })
        cands.sort(key=lambda c: c["score"], reverse=True)
        for c in cands:
            if not _download_image(c["url"], dest):
                continue
            who = (c["artist"] or "Wikimedia Commons")[:60]
            return {"source": "Wikimedia Commons", "license": c["lic"], "url": c["url"],
                    "credit": f"{who} / Wikimedia Commons ({c['lic']})"}
        return None

    def _gbif_photo(self, sci: str, dest: Path) -> dict | None:
        import requests
        try:
            r = requests.get(_GBIF_API, params={"scientificName": sci, "mediaType": "StillImage",
                             "limit": "20"}, headers={"User-Agent": _UA}, timeout=25)
            if r.status_code != 200:
                return None
            results = r.json().get("results", []) or []
        except Exception as e:  # noqa: BLE001
            log.info("[소싱] GBIF 조회 예외(%s): %s", sci, e)
            return None
        for occ in results:
            for m in occ.get("media", []) or []:
                if (m.get("type") or "StillImage") != "StillImage":
                    continue
                fmt = (m.get("format") or "").lower()
                if fmt and not any(x in fmt for x in ("jpeg", "jpg", "png")):
                    continue
                lic = _map_cc_license(m.get("license"))
                if not lic:
                    continue
                url = m.get("identifier")
                if not url or not _download_image(url, dest):
                    continue
                who = (_strip_html(m.get("rightsHolder") or m.get("publisher") or "") or "GBIF")[:60]
                return {"source": "GBIF", "license": lic, "url": url,
                        "credit": f"{who} / GBIF ({lic})"}
        return None

    def _synthetic_placeholder(self, dest: Path, label: str) -> None:
        from PIL import Image, ImageDraw, ImageFilter

        w, h = 900, 1400
        img = Image.new("RGB", (w, h), (4, 12, 26))
        d = ImageDraw.Draw(img)
        # 심해 그라디언트 + 스포트라이트 원
        for y in range(h):
            t = y / h
            d.line([(0, y), (w, y)], fill=(int(3 + 6 * t), int(12 + 18 * t), int(28 + 30 * t)))
        cx, cy = w // 2, int(h * 0.42)
        for r in range(320, 0, -6):
            a = int(70 * (1 - r / 320))
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(6 + a // 4, 26 + a // 3, 44 + a))
        # 문어 몸통(창백한 타원) + 귀 지느러미 두 개
        d.ellipse([cx - 120, cy - 90, cx + 120, cy + 110], fill=(150, 170, 185))
        d.ellipse([cx - 210, cy - 70, cx - 110, cy + 10], fill=(120, 145, 165))
        d.ellipse([cx + 110, cy - 70, cx + 210, cy + 10], fill=(120, 145, 165))
        # 팔(아래로 늘어진 웨브)
        for i in range(-3, 4):
            x = cx + i * 34
            d.line([(x, cy + 80), (x + i * 10, cy + 300)], fill=(110, 135, 155), width=16)
        img = img.filter(ImageFilter.GaussianBlur(2))
        # 종 라벨 표기 (플레이스홀더임을 명시 + 종별 식별). 폰트 없으면 생략.
        try:
            from PIL import ImageFont

            d2 = ImageDraw.Draw(img)
            font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 40)
            d2.text((cx, int(h * 0.80)), f"[TEST] {label}", font=font, fill=(220, 235, 245),
                    anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
        except Exception:  # noqa: BLE001
            pass
        img.save(dest, quality=88)

    # --- 상황/정확성 ---
    def get_situation(self, info: SpeciesInfo) -> Situation:
        key = data.resolve_key(info.common_name_en)
        sp = data.SPECIES[key]
        cuts = prompts.build_cuts(sp)  # 종 데이터 → 3컷 프롬프트 자동 조립 (템플릿)
        return Situation(
            species=key,
            scientific_name=info.scientific_name,
            accuracy_flags=sp["accuracy_flags"],
            situation_id=sp["situation_id"],
            cuts=[CutSpec(cut_type=c["cut_type"], prompt=c["prompt"]) for c in cuts],
        )

    def hud_callouts(self, info: SpeciesInfo) -> list[dict]:
        """HUD 부위 콜아웃 라벨(슬롯+제목+부제). 코어가 슬롯을 화면 좌표로 변환."""
        key = data.resolve_key(info.common_name_en)
        return data.SPECIES.get(key, {}).get("hud_callouts", [])

    # --- narrated_wildlife 전환: 동적 야생다큐 컷 + 나레이션 대본 ---
    def get_situation_wildlife(self, info: SpeciesInfo) -> Situation:
        """야생다큐(동적·수심인지) 3컷 상황. validate_cuts(정확성 게이트)는 공용 재사용."""
        key = data.resolve_key(info.common_name_en)
        sp = data.SPECIES[key]
        cuts = prompts.build_cuts_wildlife(sp)
        return Situation(
            species=key, scientific_name=info.scientific_name,
            accuracy_flags=sp["accuracy_flags"], situation_id=sp["situation_id"],
            cuts=[CutSpec(cut_type=c["cut_type"], prompt=c["prompt"]) for c in cuts],
        )

    def build_script(self, info: SpeciesInfo) -> list[dict]:
        """나레이션 대본 [{text,tone}] — 시그니처 행동 힌트로 첫 fun_fact 사용."""
        from src.categories.deep_sea import script
        behavior = info.fun_facts[0] if info.fun_facts else ""
        return script.build_script(info, behavior=behavior)

    def build_narrated_caption(self, info: SpeciesInfo) -> CaptionData:
        """narrated_wildlife 캡션(전환 §6 형식)."""
        return copywriter.build_narrated_caption(info)

    # --- 오프닝 훅 / 엔드카드 시스템 입력 (hook_intro) ---
    def hook_intro_spec(self, info: SpeciesInfo):
        """(SpeciesSpec, hook_text, bgm) 반환 → 코어가 오프닝/엔드카드/전환/사운드 자동 적용.
        일본어 훅 카피 생성 실패 시 None(시스템 휴면·발행 불정지)."""
        from src.categories.deep_sea import hook as hook_copy
        from src.core.hook_intro import SpeciesSpec
        h = hook_copy.build_hook(info)
        if not h:
            return None
        dmin, dmax = self._parse_depth(info.depth_range_m)
        sci = (info.scientific_name or "").strip()
        sci = sci[0].upper() + sci[1:] if sci else sci
        spec = SpeciesSpec(
            jp_name=h["jp_name"], sci_name=sci, depth_min=dmin, depth_max=dmax,
            hook_line1=h["hook_line1"], hook_line2=h["hook_line2"],
            hook_pop_words=list(h["pop_words"]), feature_line=h["feature_line"],
            feature_glow_word=h.get("feature_glow_word", h["pop_words"][0]),
        )
        hook_text = h["hook_line1"] + h["hook_line2"]
        bgm = self._pick_bgm(sci or h["jp_name"])
        return (spec, hook_text, bgm)

    def _pick_bgm(self, seed: str) -> str | None:
        """심해 전용 BGM 로테이션 — 영상이 많은 카테고리라 단조로움/이탈을 막으려 여러 곡을 돌린다.
        `assets/audio/bgm/deepsea_*.mp3`(+기존 beneath_the_frozen_shelf)를 후보로 모으고,
        종명 해시로 결정론 선택(같은 종은 항상 같은 곡 → 재생성 일관, 종마다 곡이 달라 다양성 확보).
        곡 파일을 추가하면 자동으로 로테이션에 합류(코드 수정 불필요)."""
        bgm_dir = Path(__file__).resolve().parents[3] / "assets" / "audio" / "bgm"
        cands = sorted(bgm_dir.glob("deepsea_*.mp3"))
        legacy = bgm_dir / "beneath_the_frozen_shelf.mp3"
        if legacy.exists():
            cands.append(legacy)
        cands = [p for p in cands if p.exists()]
        if not cands:
            return None
        # 안정 해시(md5)로 균등 분산 — sum(ord)은 곡이 특정 트랙에 쏠렸다.
        import hashlib
        h = int(hashlib.md5((seed or "deep").encode("utf-8")).hexdigest(), 16)
        return str(cands[h % len(cands)])

    def pick_footage_species(self) -> str:
        """auto 모드: 검증된 실사 영상이 있는 종만 선택.

        ★미제작 우선(큐 재사용): 아직 영상이 만들어지지 않은 종(catalog 미기록)을 먼저 고른다.
        그래서 확보(시드)만 되고 아직 제작·게시되지 않은 종이 유실되지 않고 반드시 다음 차례에
        쓰인다. 모든 종이 한 번씩 제작된 뒤에야 회차(episode)로 순환한다.
        """
        from src.categories.deep_sea import catalog
        from src.core import footage
        seeded = {k.lower() for k in footage.seeded_keys()}
        pool = [key for key, sp in data.SPECIES.items()
                if sp["scientific_name"].strip().lower() in seeded]
        if not pool:
            raise PipelineError("input", "실사 영상 보유 종이 없습니다(시드 필요)")
        made = set()
        try:
            for it in catalog._load():
                made.add(str(it.get("scientific_name", "")).strip().lower())
                made.add(str(it.get("common_name_en", "")).strip().lower())
        except Exception:  # noqa: BLE001
            made = set()
        unmade = [k for k in pool
                  if data.SPECIES[k]["scientific_name"].strip().lower() not in made]
        if unmade:
            return unmade[0]
        try:
            ep = self.next_episode()
        except Exception:  # noqa: BLE001
            ep = 0
        return pool[ep % len(pool)]

    def reels_body_script(self, info: SpeciesInfo) -> list[str] | None:
        """reels(실사+일본어) 본문 나레이션 절 리스트. 시드/LLM, 실패 시 None."""
        from src.categories.deep_sea import hook as hook_copy
        return hook_copy.build_body_jp(info)

    def build_reels_caption(self, info: SpeciesInfo, spec) -> CaptionData:
        """reels 캡션 — 일본어(발행문)와 한국어(참고 번역)를 **분리 저장**.
        caption_body=일본어만(발행 그대로), caption_ko/hook_ko/hashtags_ko=한국어 참고.
        (과거 JP+KO 합본 1필드는 대시보드에서 동시 열람 불가 → 분리 필드로 전환)"""
        from src.categories.deep_sea import hook as hook_copy
        from src.core import rich_caption
        h = hook_copy.build_hook(info) or {}
        # 리치 캡션(과학 사실 2~3개를 이야기로 엮음) — LLM 우선, 실패 시 사실 기반 리치 폴백
        c = rich_caption.generate(
            info, spec.jp_name, spec.sci_name, spec.feature_line,
            spec.hook_line1, spec.hook_line2, hook_ko=h.get("hook_ko", ""),
            feature_ko=h.get("feature_ko", ""), credit="NOAA Ocean Exploration・Public Domain",
            default_tags=["#深海", f"#{spec.jp_name}", "#生き物"])
        return CaptionData(
            hook_text=spec.hook_line1 + spec.hook_line2,
            overlay_facts=[f"水深 {info.depth_range_m} m"],
            caption_body=c["jp"], hashtags=c["tags"],
            reveal_name=f"{spec.jp_name} / {spec.sci_name}",
            reveal_fact=spec.feature_line,
            caption_ko=c["ko"], hook_ko=h.get("hook_ko", "") or "",
            hashtags_ko=list(c.get("tags_ko", [])),
            yt_title=c.get("yt_title", ""), yt_title_ko=c.get("yt_title_ko", ""))

    @staticmethod
    def _parse_depth(depth_range_m: str) -> tuple[int, int]:
        """'1000-4000' → (1000, 4000). 단일값이면 절반~값, 없으면 심해 기본."""
        nums = [int(x) for x in re.findall(r"\d+", depth_range_m or "")]
        if not nums:
            return (200, 2000)
        if len(nums) == 1:
            return (max(0, nums[0] // 2), nums[0])
        return (min(nums), max(nums))

    # --- 도감 회차 번호 (커밋되는 원장으로 안정적 누적 — CI 컨테이너 리셋 무관) ---
    def next_episode(self) -> int:
        """다음 도감 엔트리 번호(읽기 전용 예약). 실제 기록은 제작 성공 후 log_catalog에서."""
        from src.categories.deep_sea import catalog
        return catalog.peek_next()

    def log_catalog(self, episode: int, info: SpeciesInfo) -> None:
        """제작 성공분을 도감 원장에 기록(현황판·번호 누적 근거). 실패해도 파이프라인 불정지."""
        from datetime import date

        from src.categories.deep_sea import catalog
        try:
            catalog.log_entry(episode, info.common_name_ko, info.common_name_en,
                              info.scientific_name, date.today().isoformat())
        except Exception as e:  # noqa: BLE001
            log.warning("도감 원장 기록 실패(무시): %s", e)

    def validate_cuts(self, situation: Situation) -> list[str]:
        violations: list[str] = []
        glow_ok = bool(situation.accuracy_flags.get("bioluminescent"))
        for cut in situation.cuts:
            p = cut.prompt
            for m in set(_BANNED_RE.findall(p)):
                violations.append(f"{cut.cut_type}: 금지 요소 '{m}'")
            if not glow_ok:
                glow_hits = set(_GLOW_RE.findall(p))
                if "발광" in p:
                    glow_hits.add("발광")
                for m in glow_hits:
                    violations.append(
                        f"{cut.cut_type}: 발광 표현 '{m}' (accuracy_flags.bioluminescent=false)"
                    )
        return violations

    # --- 캡션 (copywriter: 훅 채점 루프 + 리빌 정책) ---
    def build_caption(self, info: SpeciesInfo) -> CaptionData:
        cap = copywriter.build(info)
        # 근접 경보(실제 근접·인지 상황 한정): 종 데이터의 hud_alert가 켜진 활동성 종만
        # 컷2 후반 붉은 경보 + 쿵쿵/경보음으로 긴장 강화(날조된 공격 아님).
        key = data.resolve_key(info.common_name_en)
        sp = data.SPECIES.get(key, {}) if key else {}
        if sp.get("hud_alert"):
            cap.alert = True
            cap.alert_text = sp.get("alert_text") or "개체가 이쪽으로 접근 중"
        return cap

    def attach_attribution(self, caption: CaptionData, info: SpeciesInfo,
                           image_credit: str) -> CaptionData:
        """저작권 표기: 캡션 말미에 이미지 출처(저작자·라이선스)+종 정보 출처 삽입."""
        return copywriter.append_attribution(caption, info, image_credit)

    # --- 오디오 ---
    def ambient_audio_spec(self) -> dict:
        return {"noise_color": "brown", "lowpass_hz": 300, "volume": 1.25, "fade_s": 1.5,
                "reveal_accent": True,  # 컷3(리빌) 시작에 서브베이스 스웰+스팅
                "hud_sfx": True,        # 스캔 소나 핑 + 타이핑 클릭 + 리빌 확정 차임
                # 배경음악: 앰비언스 밑에 낮게 레이어 (다크 시네마틱 앰비언트)
                "bgm_path": "assets/audio/bgm/beneath_the_frozen_shelf.mp3",
                "bgm_volume": 0.5}

    # --- 그레이딩 (deep_sea_realism ROV 질감 — 오버레이 전 적용, 텍스트는 선명 유지) ---
    def grade_filter(self) -> str | None:
        # Veo의 '예쁜 시네마틱'·과노출 편향 보정 (프롬프트가 무시돼도 어둠을 보장하는 하한선):
        # 탈채도 + 밝기 하향 + 감마로 미드톤 crush + 블랙 리프트 억제(어두운 곳 더 어둡게) +
        # 강한 비네트(가장자리·상단 잔여 광선 억제) + 노이즈/미세블러(저화질 실사 질감)
        return (
            "eq=saturation=0.75:contrast=1.06:brightness=-0.12:gamma=0.82,"
            "curves=all='0/0 0.5/0.4 1/0.95',"
            "gblur=sigma=0.5,"
            "noise=alls=8:allf=t,"
            "vignette=angle=PI/3.6:mode=forward"
        )
