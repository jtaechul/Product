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

# NOAA Ocean Exploration 퍼블릭도메인 후보 (도달 실패 시 합성 폴백).
# NOAA 연방정부 저작물 = 퍼블릭도메인(17 U.S.C. §105). 크레딧: NOAA Ocean Exploration.
_NOAA_CANDIDATES = [
    "https://oceanexplorer.noaa.gov/wp-content/uploads/2020/10/20201106-hires-1024x576.jpg",
]

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


class DeepSeaCategory:
    category_id = "deep_sea"
    style_profile = "deep_sea_realism"
    series_title = "심해 도감"  # 시리즈 브랜딩 (엔드카드·캡션 회차 표기)

    # --- 입력/정보 ---
    def parse_input(self, query: str) -> str:
        key = data.resolve_key(query)
        if key is None:
            raise PipelineError(
                "input", f"미등록 종: {query!r} (등록: {list(data.SPECIES)})"
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

    # --- 소싱 ---
    def source_assets(self, info: SpeciesInfo, raw_dir: str) -> list[RawAsset]:
        raw = Path(raw_dir)
        raw.mkdir(parents=True, exist_ok=True)
        slug = info.common_name_en.lower().replace(" ", "_")
        dest = raw / f"{slug}.jpg"

        # 1) 실제 NOAA 퍼블릭도메인 이미지 시도
        downloaded = self._try_download(dest)
        if downloaded:
            return [
                RawAsset(
                    asset_path=str(dest),
                    source="NOAA",
                    license="public-domain",
                    credit_string="Image: NOAA Ocean Exploration (public domain)",
                    source_url=downloaded,
                    caption_text="NOAA Ocean Exploration, Exploring Puerto Rico's Seamounts",
                )
            ]

        # 2) 폴백: 합성 심해 플레이스홀더(자체 생성 → cc0). 파이프라인 검증용.
        log.warning("NOAA 다운로드 실패 → 합성 테스트 이미지 생성(cc0). 실제 발행 전 실사로 교체 필요.")
        self._synthetic_placeholder(dest, info.common_name_en)
        return [
            RawAsset(
                asset_path=str(dest),
                source="SYNTHETIC-TEST",
                license="cc0",
                credit_string="Test placeholder (self-generated, CC0) — 실사 교체 필요",
                source_url="local://synthetic",
                caption_text="",
            )
        ]

    def _try_download(self, dest: Path) -> str | None:
        try:
            import requests
        except ImportError:
            return None
        for url in _NOAA_CANDIDATES:
            try:
                r = requests.get(url, timeout=20)
                if r.status_code == 200 and r.content[:2] == b"\xff\xd8":  # JPEG magic
                    dest.write_bytes(r.content)
                    return url
                log.info("소싱 후보 실패(%s): HTTP %s", url, r.status_code)
            except Exception as e:  # noqa: BLE001
                log.info("소싱 후보 예외(%s): %s", url, e)
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
        return copywriter.build(info)

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
