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

    심리학 레버 내장:
    - 호기심 격차(Loewenstein): '이것/정체불명/무언가' = 열린 루프 → 끝까지 보게
    - 최상급·구체 수치: '가장 깊은', 수심 {d}m → 각인·신뢰
    - 2인칭 개인화·FOMO: '당신이 평생 못 볼'
    - 미지의 긴장(부정성 편향): 가짜 위험 날조 없이 '미지'로 불안 유발
    (종명 스포일 금지 — 리빌은 마지막)
    """
    d = _depth_str(info)
    return [
        f"수심 {d}m, 당신이 평생 못 볼 장면이 찍혔습니다",
        f"지구에서 가장 깊은 어둠, 수심 {d}m에서 이것과 마주쳤습니다",
        f"탐사정 센서가 미친 듯 울렸다… 수심 {d}m 아래 '무언가'",
        f"인류가 거의 못 본 수심 {d}m, 어둠 속에서 이것이 다가온다",
        f"수심 {d}m, 카메라에 잡힌 정체불명의 형체",
    ]


def _generate_hook_candidates(info: SpeciesInfo) -> list[str]:
    facts = " / ".join(info.fun_facts[:3])
    prompt = (
        "너는 조회수 떡상하는 심해 미스터리 쇼츠의 훅 카피라이터다. 컨셉은 '현실 기반의 "
        "극도로 드라마틱한 심해 미스터리'(무인 탐사정 ROV가 심해에서 정체불명 생물을 포착). "
        f"첫 1초 훅 문장 후보를 한국어로 정확히 {N_HOOK_CANDIDATES}개 만들어라. 한 줄에 하나씩, "
        "번호·따옴표 없이.\n"
        "[반드시 활용할 심리 레버 — 후보마다 다른 조합으로]\n"
        "- 호기심 격차: '이것/정체불명/무언가'로 정답을 감춰 열린 루프를 만든다(끝까지 보게)\n"
        "- 구체성·최상급: 정확한 수심 숫자, '가장 깊은/인류가 거의 못 본' 최상급으로 각인\n"
        "- 개인적 관련성(2인칭·FOMO): '당신이 평생 못 볼', '지금 놓치면' 처럼 시청자를 끌어들임\n"
        "- 미지의 긴장(부정성 편향): 불확실·긴박함으로 불안 자극 (단, 가짜 위험·포식은 날조 금지)\n"
        "- 패턴 인터럽트: 상식을 뒤집는 의외의 한마디\n"
        "[규칙]\n"
        "- 14~28자. 스크롤을 멈추게 하는 강한 첫 문장. 밋밋한 다큐 톤 절대 금지\n"
        "- 종 이름을 절대 쓰지 마라 (정체는 마지막에 리빌 = 궁금해서 끝까지 봄)\n"
        "- 생물의 '실제 특징'은 극적으로 표현하되, 없는 사실(가짜 위험·포식·크기)을 지어내지 마라\n"
        f"[실제 특징(참고)] 수심 {info.depth_range_m}m / {facts}\n"
    )
    raw = llm.generate_text(prompt)
    if not raw:
        return []
    lines = [re.sub(r"^[\d\.\-\)\s]+", "", l).strip().strip('"') for l in raw.splitlines()]
    return [l for l in lines if 8 <= len(l) <= 34][:N_HOOK_CANDIDATES]


def _judge_hooks(candidates: list[str], info: SpeciesInfo) -> str | None:
    """LLM 채점 → 최고 1개. 실패 시 None."""
    if not candidates:
        return None
    listing = "\n".join(f"{i+1}. {c}" for i, c in enumerate(candidates))
    prompt = (
        "다음은 심해 미스터리 쇼츠의 첫 1초 훅 후보다. 심리학 기준으로 채점하라: "
        "호기심 격차(열린 루프)·정체 은폐(30) + 스크롤 정지력/자극성(25) + "
        "구체성·최상급 각인(15) + 개인적 관련성·FOMO(15) + 미지의 긴장(10) + "
        "자연스러운 한국어(5). "
        "종 이름이 들어간 후보는 0점(리빌 스포일). 가장 끝까지 보게 만드는 후보의 번호 '하나만' 출력하라.\n"
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

    스토리 아크: 컷1 어둠 속 등장(미확인) → 컷2 아직 우리를 눈치 못 챈 채 유영(긴장·실제행동)
    → 컷3 리빌(종명+킬러팩트). 컷2 비트가 HUD 'ANALYZING' 하단에 타이핑된다.
    """
    behavior_fact = info.fun_facts[0] if info.fun_facts else info.habitat
    killer_fact = info.fun_facts[1] if len(info.fun_facts) > 1 else behavior_fact
    return [
        f"수심 {_depth_str(info)}m · 미확인 형체 접근",              # 컷1: 종명 없음
        f"아직 이쪽을 눈치채지 못한 채 — {behavior_fact}",           # 컷2: ANALYZING 하단(긴장+실제행동)
        f"{info.common_name_ko} ({info.common_name_en}) · {killer_fact}",  # 컷3: 리빌
    ]


# ---------- 캡션 본문: 관측 일지형 스토리텔링 (LLM 각색 + 결정적 폴백) ----------

def _storytelling_caption(info: SpeciesInfo, hook: str) -> str | None:
    """실제 정보(fun_facts)를 '재표현'해 몰입형 관측 일지 캡션 생성. 실패 시 None."""
    facts = "\n".join(f"- {f}" for f in info.fun_facts[:6])
    prompt = (
        "너는 심해 미스터리 쇼츠 채널 'DEEP DIVE LOG'의 카피라이터다. 무인 탐사정(ROV)이 "
        "심해에서 생물을 포착한 영상의 인스타그램 릴스 캡션을 한국어로 작성하라.\n"
        "[구조 — 그대로 따를 것]\n"
        f"1) 첫 줄: 이 훅을 그대로 또는 자연스럽게 변주: \"{hook}\"\n"
        "2) ROV 관측 일지처럼 몰입감 있는 미니 서사 2~3문장 (칠흑의 하강 → 센서 반응 → 조우). "
        "긴장감 있게, 현재형으로.\n"
        f"3) 정체 공개: {info.common_name_ko}({info.common_name_en}). 아래 [실제 정보]에서 "
        "2~3개를 골라 흥미롭게 각색해 풀어쓴다 (수치·의외성 위주).\n"
        "4) 마지막 1~2줄: 저장 유도(\"다시 보고 싶다면 저장\") + 팔로우 유도(\"팔로우하면 "
        "다음 심해 생물\") — 문구는 자연스럽게 변주.\n"
        "[규칙]\n"
        "- 300~500자. 존댓말. 이모지는 0~2개만. 해시태그 쓰지 마라(시스템이 붙임).\n"
        "- [실제 정보]에 없는 사실을 지어내지 마라 (연출·감정 표현은 자유).\n"
        f"[실제 정보] 종명 {info.common_name_ko}({info.common_name_en}) / 학명 "
        f"{info.scientific_name} / 수심 {info.depth_range_m}m / 서식 {info.habitat}\n{facts}\n"
    )
    raw = llm.generate_text(prompt, max_tokens=900)
    if not raw:
        return None
    text = raw.strip().strip('"')
    return text if 120 <= len(text) <= 700 else None


def _fallback_caption(info: SpeciesInfo, hook: str) -> str:
    """LLM 불가 시에도 서사 구조를 갖춘 결정적 캡션."""
    f = info.fun_facts
    fact1 = f[0] if f else info.habitat
    fact2 = f[3] if len(f) > 3 else (f[1] if len(f) > 1 else "")
    fact3 = f[4] if len(f) > 4 else ""
    d = _depth_str(info)
    lines = [
        hook,
        "",
        f"칠흑 같은 수심 {d}m. 탐사정의 라이트가 닿는 곳마다 어둠뿐이던 그때, "
        "센서에 무언가 잡혔습니다. 천천히 다가가자 — 이쪽을 전혀 눈치채지 못한 채 "
        "유유히 헤엄치는 작은 실루엣.",
        "",
        f"정체는 {info.common_name_ko}({info.common_name_en}), 학명 {info.scientific_name}. "
        f"{fact1}. " + (f"{fact2}. " if fact2 else "") + (f"{fact3}." if fact3 else ""),
        "",
        "다시 보고 싶은 장면이라면 저장해두세요. 팔로우하면 다음 심해 생물과 만납니다.",
    ]
    return "\n".join(lines)


def build(info: SpeciesInfo) -> CaptionData:
    """CaptionData 완성 (훅 루프 + 비트 + 스토리텔링 캡션 + 해시태그)."""
    hook = best_hook(info)
    beats = cut_beats(info)
    killer_fact = info.fun_facts[1] if len(info.fun_facts) > 1 else (
        info.fun_facts[0] if info.fun_facts else info.habitat)

    body = _storytelling_caption(info, hook) or _fallback_caption(info, hook)
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
