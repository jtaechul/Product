"""collection_base — 데이터 주도형 reels 카테고리 베이스(심해 외 카테고리 공용).

새 카테고리(해양 미세조류·난파선 등)는 SUBJECTS(대상 정보) + COPY(일본어 훅/본문/캡션 시드)만
채우면 이 베이스가 reels 파이프라인 계약을 그대로 이행한다. 코어(footage/hook_intro/reframe)는
카테고리 불변이라 재사용하고, 실사 영상은 core footage._SEED에 대상 키(scientific_name)로 등록한다.

★미게시 대상 재사용(큐): auto 선택은 **아직 영상이 제작되지 않은 대상(catalog 미기록)을 우선**
고른다. 그래서 확보(시드)만 되고 아직 제작·게시되지 않은 대상이 유실되지 않고 다음 차례에
반드시 쓰인다. 모든 대상이 한 번씩 제작된 뒤에야 회차(episode)로 순환한다.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from src.core.contracts import CaptionData, PipelineError, RawAsset, Situation, SpeciesInfo
from src.registry import CategoryModule

log = logging.getLogger(__name__)


def parse_depth(depth_range_m: str) -> tuple[int, int]:
    """'1-150' → (1, 150). 단일값이면 절반~값, 없으면 기본."""
    nums = [int(x) for x in re.findall(r"\d+", depth_range_m or "")]
    if not nums:
        return (0, 100)
    if len(nums) == 1:
        return (max(0, nums[0] // 2), nums[0])
    return (min(nums), max(nums))


class CollectionCategory(CategoryModule):
    """SUBJECTS + COPY 만으로 reels를 굴리는 범용 카테고리 베이스."""

    category_id = ""
    style_profile = "marine_collection"
    series_title = ""
    bgm_filename = "beneath_the_frozen_shelf.mp3"
    corner_label = "OCEAN · ARCHIVE"        # 오프닝 코너 라벨(카테고리별)
    scale_label = "生息水深"                 # 우측 스케일 제목
    show_scale = True                        # 수심 스케일 표시 여부
    SUBJECTS: dict = {}
    COPY: dict = {}
    _dir = Path(__file__).resolve().parent   # 하위 클래스가 __file__로 override

    # ── 원장 경로(카테고리별 분리) ──
    def _catalog_path(self) -> Path:
        return self._dir / f"{self.category_id}_catalog.json"

    def _load_catalog(self) -> list[dict]:
        p = self._catalog_path()
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                return d if isinstance(d, list) else []
            except Exception:  # noqa: BLE001
                return []
        return []

    # ── 입력/정보 ──
    def parse_input(self, query: str) -> str:
        q = (query or "").strip().lower()
        if q in self.SUBJECTS:
            return q
        for key, sp in self.SUBJECTS.items():
            aliases = {sp["common_name_en"].lower(), sp["common_name_ko"],
                       sp["scientific_name"].lower()}
            if q in aliases:
                return key
        raise PipelineError("input", f"미등록 대상: {query!r} (자동은 'auto')")

    def get_info(self, subject_query: str) -> SpeciesInfo:
        sp = self.SUBJECTS[subject_query]
        return SpeciesInfo(
            scientific_name=sp["scientific_name"], common_name_ko=sp["common_name_ko"],
            common_name_en=sp["common_name_en"], depth_range_m=sp["depth_range_m"],
            distribution=sp["distribution"], habitat=sp["habitat"],
            diet=sp.get("diet", []), fun_facts=sp.get("fun_facts", []),
            sources=sp.get("sources", []),
        )

    # ── auto 선택: 실사 영상 보유 + '미제작 우선'(큐 재사용) ──
    def pick_footage_species(self) -> str:
        from src.core import footage
        seeded = {k.lower() for k in footage.seeded_keys()}
        pool = [k for k, sp in self.SUBJECTS.items()
                if sp["scientific_name"].strip().lower() in seeded]
        if not pool:
            raise PipelineError("input", f"[{self.category_id}] 실사 영상 보유 대상 없음(시드 필요)")
        made = {str(it.get("scientific_name", "")).strip().lower() for it in self._load_catalog()}
        unmade = [k for k in pool if self.SUBJECTS[k]["scientific_name"].strip().lower() not in made]
        if unmade:                       # 아직 제작 안 된 대상 우선(확보만 되고 미게시된 것 유실 방지)
            return unmade[0]
        try:                             # 전부 제작됨 → 회차로 순환
            ep = self.next_episode()
        except Exception:  # noqa: BLE001
            ep = 0
        return pool[ep % len(pool)]

    # ── 훅/본문/캡션 ──
    def hook_intro_spec(self, info: SpeciesInfo):
        from src.core.hook_intro import SpeciesSpec
        key = self._key_for(info)
        c = self.COPY.get(key)
        if not c:
            return None
        dmin, dmax = parse_depth(info.depth_range_m)
        sci = (info.scientific_name or "").strip()
        sci = sci[0].upper() + sci[1:] if sci else sci
        spec = SpeciesSpec(
            jp_name=c["jp_name"], sci_name=sci, depth_min=dmin, depth_max=dmax,
            hook_line1=c["hook_line1"], hook_line2=c["hook_line2"],
            hook_pop_words=list(c["pop_words"]), feature_line=c["feature_line"],
            feature_glow_word=c.get("feature_glow_word", c["pop_words"][0]),
            corner_label=self.corner_label, scale_label=self.scale_label,
            show_scale=self.show_scale,
        )
        hook_text = c["hook_line1"] + c["hook_line2"]
        bgm = Path(__file__).resolve().parents[2] / "assets" / "audio" / "bgm" / self.bgm_filename
        return (spec, hook_text, str(bgm) if bgm.exists() else None)

    def reels_body_script(self, info: SpeciesInfo):
        c = self.COPY.get(self._key_for(info))
        return list(c["body"]) if c and c.get("body") else None

    def build_reels_caption(self, info: SpeciesInfo, spec) -> CaptionData:
        from src.core import rich_caption
        c = self.COPY.get(self._key_for(info), {})
        credit = (info.sources or ["Wikimedia Commons"])[0]
        rc = rich_caption.generate(
            info, spec.jp_name, spec.sci_name, spec.feature_line,
            spec.hook_line1, spec.hook_line2, hook_ko=c.get("hook_ko", ""),
            feature_ko=c.get("feature_ko", ""), credit=credit,
            default_tags=list(c.get("tags", ["#海", f"#{spec.jp_name}", "#生き物"])),
            default_tags_ko=list(c["tags_ko"]) if c.get("tags_ko") else None)
        return CaptionData(
            hook_text=spec.hook_line1 + spec.hook_line2,
            overlay_facts=[info.habitat or ""], caption_body=rc["jp"],
            hashtags=rc["tags"], reveal_name=f"{spec.jp_name} / {spec.sci_name}",
            reveal_fact=spec.feature_line, caption_ko=rc["ko"], hook_ko=c.get("hook_ko", ""),
            hashtags_ko=rc["tags_ko"],
        )

    def _key_for(self, info: SpeciesInfo) -> str:
        sci = (info.scientific_name or "").strip().lower()
        for k, sp in self.SUBJECTS.items():
            if sp["scientific_name"].strip().lower() == sci:
                return k
        return ""

    # ── 도감 회차(카테고리별 원장) ──
    def next_episode(self) -> int:
        items = self._load_catalog()
        return (max((int(it.get("no", 0)) for it in items), default=0) + 1) if items else 1

    def log_catalog(self, episode: int, info: SpeciesInfo) -> None:
        items = self._load_catalog()
        if any(int(it.get("no", 0)) == int(episode) for it in items):
            return
        items.append({"no": int(episode), "common_name_ko": info.common_name_ko,
                      "common_name_en": info.common_name_en,
                      "scientific_name": info.scientific_name, "date": date.today().isoformat()})
        items.sort(key=lambda it: int(it.get("no", 0)))
        self._catalog_path().write_text(json.dumps(items, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

    # ── CategoryModule ABC 미사용 경로(narrated/hud) 최소 구현 ──
    def source_assets(self, info, raw_dir):  # reels는 footage 모듈이 담당
        return []

    def get_situation(self, info) -> Situation:
        raise NotImplementedError(f"{self.category_id}는 reels 전용")

    def validate_cuts(self, situation) -> list[str]:
        return []

    def build_caption(self, info) -> CaptionData:
        raise NotImplementedError(f"{self.category_id}는 reels 전용")

    def ambient_audio_spec(self) -> dict:
        return {"profile": "ocean_ambient"}
