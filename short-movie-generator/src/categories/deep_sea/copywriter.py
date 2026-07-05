"""deep_sea 카피라이터 — 역할 분리 텍스트 생성 + 훅 채점 루프.

역할별 텍스트:
  1) 훅(컷1 상단): 호기심 격차. 종명 스포일 절대 금지. 12~22자.
  2) 컷 비트(컷별 하단 1줄): 컷1 미스터리 → 컷2 행동 → 컷3 리빌(종명+킬러팩트).
  3) 캡션+해시태그: 저장·공유 유도.

원칙(해자 보호):
- LLM은 검증된 팩트(data.SPECIES)의 '재표현'만 한다. 새 사실 생성 금지.
- 훅 후보 N개 생성 → 채점(호기심/위기감/길이/스포일) → 최고 1개 선택.
- LLM 없거나 실패 시 결정적 템플릿 폴백(파이프라인은 절대 멈추지 않음).
- 스포일 검사는 코드로도 강제(LLM 판단에만 의존하지 않음).
"""
from __future__ import annotations

import logging
import re

from src.core import llm
from src.core.contracts import CaptionData, SpeciesInfo

log = logging.getLogger(__name__)

N_HOOK_CANDIDATES = 5


# ---------- 스포일 가드 (코드 강제) ----------

def _spoiler_terms(info: SpeciesInfo) -> list[str]:
    """훅·컷1/2에 등장하면 안 되는 종명 계열 단어."""
    terms = [info.common_name_ko, info.common_name_en.lower()]
    # 학명 속명 (예: Grimpoteuthis)
    genus = info.scientific_name.split()[0].strip()
    if genus:
        terms.append(genus.lower())
    # 한국어 종명의 구성어 (예: 덤보문어 → 덤보) — 일반어(문어)는 허용
    ko = info.common_name_ko
    if len(ko) >= 4:
        terms.append(ko[: len(ko) // 2])
    return [t for t in terms if t]


def has_spoiler(text: str, info: SpeciesInfo) -> bool:
    low = text.lower()
    return any(t.lower() in low for t in _spoiler_terms(info))


# ---------- 훅: 후보 생성 → 채점 → 선택 ----------

def _depth_str(info: SpeciesInfo) -> str:
    """최대 수심을 '4,000' 형태로. 숫자 파싱 실패 시 원문 그대로."""
    raw = info.depth_range_m.split("-")[-1]
    digits = re.sub(r"[^\d]", "", raw)
    return f"{int(digits):,}" if digits else raw


def _fallback_hooks(info: SpeciesInfo) -> list[str]:
    """결정적 템플릿 훅 (LLM 불가 시에도 품질 하한 보장).

    전략: 현실 기반 극도로 드라마틱한 심해 미스터리. 자극적·도파민형 호기심 훅.
    (종명 스포일 금지 — 리빌은 마지막)
    """
    d = _depth_str(info)
    return [
        f"수심 {d}m, 탐사정 카메라에 '이것'이 잡혔습니다",
        f"인류가 가본 적 없는 수심 {d}m… 어둠 속에서 뭔가 다가온다",
        "심해 탐사정이 포착한 정체불명의 생명체",
        f"수심 {d}m에서 센서가 미친 듯이 울린 이유",
    ]


def _generate_hook_candidates(info: SpeciesInfo) -> list[str]:
    facts = " / ".join(info.fun_facts[:3])
    prompt = (
        "너는 조회수 떡상하는 심해 미스터리 쇼츠의 훅 카피라이터다. 컨셉은 '현실 기반의 "
        "극도로 드라마틱한 심해 미스터리'(무인 탐사정 ROV가 심해에서 정체불명 생물을 포착). "
        f"첫 1초 훅 문장 후보를 한국어로 정확히 {N_HOOK_CANDIDATES}개 만들어라. 한 줄에 하나씩, "
        "번호·따옴표 없이.\n"
        "[규칙]\n"
        "- 12~26자. 자극적·도파민형: 궁금증 폭발, 긴장·미지의 공포, '이것/정체불명/포착' 같은 표현 활용\n"
        "- 스크롤을 멈추게 하는 강한 첫 문장. 밋밋한 다큐 톤 금지\n"
        "- 종 이름을 절대 쓰지 마라 (정체는 마지막에 리빌한다 = 궁금해서 끝까지 보게)\n"
        "- 생물의 '실제 특징'은 과장해도 되지만, 없는 사실(가짜 위험·포식)을 지어내진 마라\n"
        f"[실제 특징(참고)] 수심 {info.depth_range_m}m / {facts}\n"
    )
    raw = llm.generate_text(prompt)
    if not raw:
        return []
    lines = [re.sub(r"^[\d\.\-\)\s]+", "", l).strip().strip('"') for l in raw.splitlines()]
    return [l for l in lines if 6 <= len(l) <= 30][:N_HOOK_CANDIDATES]


def _judge_hooks(candidates: list[str], info: SpeciesInfo) -> str | None:
    """LLM 채점 → 최고 1개. 실패 시 None."""
    if not candidates:
        return None
    listing = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
    prompt = (
        "다음은 심해 미스터리 쇼츠의 첫 1초 훅 후보다. 기준: 스크롤 정지력/자극성(40) + "
        "궁금증 폭발·정체 은폐(30) + 긴장/미지의 공포(20) + 자연스러운 한국어(10). "
        "종 이름이 들어간 후보는 0점(리빌 스포일). 가장 도파민 터지는 후보의 번호 '하나만' 출력하라.\n"
        f"{listing}\n번호:"
    )
    raw = llm.generate_text(prompt, max_tokens=10)
    if not raw:
        return None
    m = re.search(r"\d+", raw)
    if not m:
        return None
    idx = int(m.group()) - 1
    return candidates[idx] if 0 <= idx < len(candidates) else None


def best_hook(info: SpeciesInfo) -> str:
    """훅 생성·채점 루프. 스포일은 코드로 최종 차단."""
    candidates = [c for c in _generate_hook_candidates(info) if not has_spoiler(c, info)]
    pick = _judge_hooks(candidates, info)
    if pick and not has_spoiler(pick, info):
        return pick
    for c in candidates:  # 채점 실패 시 첫 유효 후보
        return c
    for f in _fallback_hooks(info):  # LLM 전면 불가 → 템플릿
        if not has_spoiler(f, info):
            return f
    return _fallback_hooks(info)[0]


# ---------- 컷 비트 + 리빌 ----------

def cut_beats(info: SpeciesInfo) -> list[str]:
    """컷별 하단 1줄 (결정적 — 검증 팩트 재배치만, LLM 불필요).

    컷1 미스터리 → 컷2 행동(팩트) → 컷3 리빌(종명+킬러팩트).
    """
    behavior_fact = info.fun_facts[0] if info.fun_facts else info.habitat
    killer_fact = info.fun_facts[1] if len(info.fun_facts) > 1 else behavior_fact
    return [
        f"수심 {_depth_str(info)}m · 미확인 생명체 접근 중",   # 컷1(HUD 미사용): 종명 없음
        f"움직임 분석 중… {behavior_fact}",                    # 컷2: ANALYZING 라인 (종명 없음)
        f"{info.common_name_ko} ({info.common_name_en}) · {killer_fact}",  # 컷3: 리빌
    ]


def build(info: SpeciesInfo) -> CaptionData:
    """CaptionData 완성 (훅 루프 + 비트 + 캡션 + 해시태그)."""
    hook = best_hook(info)
    beats = cut_beats(info)
    killer_fact = info.fun_facts[1] if len(info.fun_facts) > 1 else (
        info.fun_facts[0] if info.fun_facts else info.habitat)

    body = (
        f"{hook}\n\n"
        f"정체는 바로 {info.common_name_ko}({info.common_name_en}). "
        f"수심 {info.depth_range_m}m {info.habitat}에서만 사는 진짜 심해 생물입니다. "
        f"{info.fun_facts[0] if info.fun_facts else ''}.\n\n"
        f"이런 심해 미스터리를 매일 만나려면 팔로우 필수. 소름 돋았다면 저장해두세요."
    )
    return CaptionData(
        hook_text=hook,
        overlay_facts=[f"수심 {info.depth_range_m}m",
                       info.fun_facts[0] if info.fun_facts else info.habitat],
        caption_body=body,
        hashtags=[f"#{info.common_name_ko}", "#심해생물", "#DeepSea"],
        cut_beats=beats,
        reveal_name=f"{info.common_name_ko} ({info.common_name_en})",
        reveal_fact=killer_fact,
    )
