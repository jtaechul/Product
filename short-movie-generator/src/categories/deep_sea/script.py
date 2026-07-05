"""script — 나레이션 야생 다큐 대본 생성 (narrated_wildlife 전환).

전략(What On Earth TV 벤치마킹): 단일 생물 감정 서사. 30~45초, 현재형 단문 5~6개.
구조 고정: [호기심 훅] → [시그니처 실제 행동] → [검증된 팩트 2~3개] → [감정적 마무리].
각 문장에 낭독 톤 태그([gravelly][slow][whispered][reverent] 등)를 붙여 TTS가 문장별로 변조.

정확성 하드룰: 없는 행동·수치 날조 금지. 종 실제 데이터(info)만 사용.
LLM = Gemini(우선, 같은 생태계) → Claude 폴백(llm 체인) → 결정적 템플릿 폴백(키 없어도 동작).
"""
from __future__ import annotations

import logging
import re

from src.core import llm
from src.core.contracts import SpeciesInfo

log = logging.getLogger(__name__)

# 허용 톤 태그 (TTS가 문장별 스타일로 매핑). 미지 태그는 'slow'로 정규화.
TONES = ("gravelly", "slow", "whispered", "reverent", "tense", "hushed", "awe")
_DEFAULT_TONE = "slow"

_PROMPT = (
    "너는 수백만 조회수를 만드는 심해 야생 다큐 채널의 대본 작가다. [{species}]로 "
    "약 25초 세로 쇼츠 나레이션을 한국어로 쓴다. 목표는 '정보 나열'이 아니라 '끝까지 보게 만드는 이야기'다.\n"
    "★가장 중요: 절대 사실을 나열하지 마라. 하나의 미스터리/긴장을 걸고 그것을 풀어주는 서사여야 한다.\n"
    "[서사 구조 — 정확히 5문장, 현재형 단문, 각 28자 이내]\n"
    "1) 훅: 종명을 말하지 말고, 의외의 진실이나 질문으로 '호기심 갭'을 연다. (예: '이 바다엔 규칙이 없다')\n"
    "2) 위기/긴장: 이 생물이 처한 가혹한 조건(짓누르는 수압·영원한 어둠·먹이 없음)을 감각적으로 세운다.\n"
    "3) 반전: '그런데' 그 생물은 어떻게 살아남는가 — 시그니처 적응/행동을 '답'으로 공개한다.\n"
    "4) 심화: 그 사실이 얼마나 놀라운지 한 번 더 조인다(검증된 실제 팩트 1개).\n"
    "5) 감정 페이오프: 생존·경이의 의미로 여운을 남긴다.\n"
    "[규칙]\n"
    "- 아래 '검증된 사실'만 사용. 없는 행동·수치·위험·포식·발광 날조 절대 금지.\n"
    "- 감각 동사·짧고 강한 리듬. 2번과 3번 사이에 반드시 '반전'의 긴장이 있어야 한다.\n"
    "- 각 문장 앞 낭독 톤 태그: [gravelly][slow][whispered][reverent][awe][tense] 중.\n"
    "[종 정보]\n"
    "이름: {ko} ({en}) / 학명: {sci}\n"
    "수심: {depth}m / 서식: {habitat} / 분포: {dist}\n"
    "시그니처 행동: {behavior}\n"
    "검증된 사실: {facts}\n"
    "[출력 형식] 각 줄: '번호. [톤] 문장' (설명·머리말 없이 문장만)\n"
)


def _norm_tone(t: str) -> str:
    t = (t or "").strip().lower()
    return t if t in TONES else _DEFAULT_TONE


def _parse(raw: str) -> list[dict]:
    """LLM 출력 → [{text, tone}]. '1. [gravelly] 문장' / '[slow] 문장' 등 관대하게 파싱."""
    lines = []
    for ln in (raw or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        ln = re.sub(r"^\s*\d+[.)]\s*", "", ln)          # 앞 번호 제거
        m = re.match(r"^\[([a-zA-Z]+)\]\s*(.+)$", ln)     # [톤] 문장
        if m:
            text = m.group(2).strip()
            if text:
                lines.append({"text": text, "tone": _norm_tone(m.group(1))})
        elif ln and not ln.startswith("["):
            lines.append({"text": ln, "tone": _DEFAULT_TONE})
    return lines


def _valid(lines: list[dict]) -> bool:
    return 4 <= len(lines) <= 8 and all(l.get("text") for l in lines)


def _trim_to_five(lines: list[dict]) -> list[dict]:
    """길이 초과 시 5문장으로 압축(훅+본문+감정마무리 보존) — 영상 길이·비용 정합."""
    if len(lines) <= 5:
        return lines
    return [lines[0]] + lines[1:len(lines) - 1][:3] + [lines[-1]]


def _fallback(info: SpeciesInfo, behavior: str) -> list[dict]:
    """LLM 불가 시에도 '미스터리→위기→반전→여운' 서사 구조를 갖춘 결정적 대본(실제 사실만)."""
    f = list(info.fun_facts or [])
    depth = (info.depth_range_m or "").split("-")[-1] or "수천"
    sig = behavior or (f[0] if f else f"{info.common_name_ko}가 천천히 헤엄친다")
    twist = f[1] if len(f) > 1 else (f[0] if f else info.habitat or "")
    return [
        {"text": "이 아래엔, 살아남는 방식이 다르다.", "tone": "gravelly"},        # 훅(호기심 갭)
        {"text": f"수심 {depth}m, 빛도 온기도 없다.", "tone": "tense"},            # 위기/긴장
        {"text": f"그런데 이 생물은 버틴다 — {sig}.", "tone": "slow"},             # 반전
        {"text": f"{twist}.", "tone": "hushed"},                                # 심화(실제 사실)
        {"text": "가장 깊은 어둠이, 가장 질긴 생명을 키운다.", "tone": "reverent"},   # 감정 페이오프
    ]


def build_script(info: SpeciesInfo, behavior: str = "") -> list[dict]:
    """[{text, tone}] 나레이션 대본을 반환(5~6문장). LLM 우선, 실패 시 결정적 폴백."""
    facts = " / ".join((info.fun_facts or [])[:5]) or (info.habitat or "")
    prompt = _PROMPT.format(
        species=info.common_name_ko or info.common_name_en,
        ko=info.common_name_ko, en=info.common_name_en, sci=info.scientific_name,
        depth=info.depth_range_m, habitat=info.habitat, dist=info.distribution,
        behavior=behavior or "-", facts=facts,
    )
    raw = llm.generate_text(prompt, max_tokens=800)
    if raw:
        lines = _parse(raw)
        if _valid(lines):
            lines = _trim_to_five(lines)   # 5문장 상한(영상 24초·Veo 3컷 정합)
            log.info("[script] LLM 대본 %d문장", len(lines))
            return lines
        log.info("[script] LLM 출력 형식 불량 → 폴백")
    return _fallback(info, behavior)
