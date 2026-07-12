"""데이터 계약 (docs/spec.md 9장) — 모듈 간 주고받는 데이터 구조를 코드로 고정.

원칙(CLAUDE.md): 코어는 카테고리 내부를 모른다. 카테고리 모듈은 이 계약만 채우면 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# 통과 라이선스 (spec 12장) — 코어 하드 룰.
# ★CC-BY-SA 오픈(운영자 확정): 소스 풀 확대를 위해 CC-BY-SA도 허용한다(저작자·라이선스 표기 필수).
#   상업적 이용 가능·표시 조건이므로 크레딧을 반드시 캡션에 넣는다. NC(비상업)는 여전히 차단.
ALLOWED_LICENSES = frozenset({"public-domain", "cc0", "cc-by", "cc-by-sa", "kogl-type1"})
BLOCKED_LICENSES = frozenset({"cc-by-nc", "cc-by-nc-sa", "unknown"})


class PipelineError(RuntimeError):
    """단계 실패 시 명확 로그 + 안전 중단용 (부분 산출물 미발행)."""

    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


@dataclass
class SpeciesInfo:
    """info → sourcing/caption 계약."""
    scientific_name: str
    common_name_ko: str
    common_name_en: str
    depth_range_m: str
    distribution: str
    habitat: str
    diet: list[str] = field(default_factory=list)
    fun_facts: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class RawAsset:
    """sourcing → license_gate 계약."""
    asset_path: str
    source: str                 # 예: "NOAA"
    license: str | None         # 예: "public-domain" (불명이면 None/"unknown")
    credit_string: str
    source_url: str
    caption_text: str = ""      # NOAA 캡션 (copyright 표기 검사용)


@dataclass
class ApprovedAsset:
    """license_gate → visualization 계약 (통과분만)."""
    asset_path: str             # assets/approved/ 이하
    license_ok: bool
    credit_string: str
    source: str = ""
    license: str = ""


@dataclass
class CutSpec:
    """situation_bank → visualization 계약 (spec 6장 cuts[])."""
    cut_type: str               # discovery | behavior | detail
    prompt: str


@dataclass
class Situation:
    """상황 뱅크 스키마 (spec 6장)."""
    species: str
    scientific_name: str
    accuracy_flags: dict
    situation_id: str
    cuts: list[CutSpec] = field(default_factory=list)


@dataclass
class ClipResult:
    """visualization → assembler 계약."""
    clip_path: str
    cut_type: str
    duration_s: float


@dataclass
class CaptionData:
    """caption → overlay 계약.

    리빌 정책: 종명·킬러팩트는 컷1~2에서 숨기고 컷3에서 공개(엔드카드에서 재확인).
    - hook_text: 컷1 상단 훅 (종명 스포일 금지)
    - cut_beats: 컷별 하단 한 줄 [컷1 미스터리, 컷2 행동, 컷3 리빌]
    - reveal_name/reveal_fact: 컷3·엔드카드 공개용 종명·킬러팩트
    """
    hook_text: str
    overlay_facts: list[str]
    caption_body: str
    hashtags: list[str] = field(default_factory=list)
    cut_beats: list[str] = field(default_factory=list)
    reveal_name: str = ""
    reveal_fact: str = ""
    # 한국어 참고 번역(운영자용) — 일본어(발행문)와 '분리 저장'해 대시보드가 좌(일)/우(한)
    # 2단으로 나란히 보여준다(합본 1필드는 동시 열람 불가라 폐기).
    caption_ko: str = ""
    hook_ko: str = ""
    hashtags_ko: list[str] = field(default_factory=list)
    # 유튜브 쇼츠 게시용 제목(알고리즘/마케팅 최적화 — 호기심 갭 + 종명 + #Shorts).
    # 시스템(LLM/폴백)이 캡션과 함께 생성해 레코드에 저장 → 대시보드 제목 프레임에 표시.
    yt_title: str = ""
    yt_title_ko: str = ""
    # 근접 경보(선택): 실제 행동(개체가 카메라/ROV를 인지·근접)에 한해 컷2 후반 긴장 연출을
    # 붉은 글씨 + 쿵쿵/경보음으로 강화. 날조된 공격이 아니라 '근접·인지'만 표현(정확성 하드룰).
    alert: bool = False
    alert_text: str = ""


@dataclass
class OutputResult:
    """output 계약."""
    video_path: str
    sidecar_meta: str
    qc_passed: bool = False
    qc_report: dict = field(default_factory=dict)
