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
    "너는 [{species}]에 대한 약 25초 나레이션 야생 다큐 대본을 한국어로 쓴다.\n"
    "규칙:\n"
    "- **정확히 5문장**, 현재형 단문, 감각 동사 중심. **각 문장 28자 이내로 짧고 강하게**\n"
    "  (전체 낭독이 30초를 넘지 않게 — 이건 매우 중요).\n"
    "- 1번 문장 = 호기심 훅(의외의 진실).\n"
    "- 2~4번 = 시그니처 행동 + 검증된 실제 팩트 2~3개 (아래 사실만 사용, 지어내기 금지).\n"
    "- 5번 문장 = 생존·경이에 관한 감정적 마무리.\n"
    "- 각 문장 앞에 낭독 톤 태그를 대괄호로: [gravelly][slow][whispered][reverent][awe] 중.\n"
    "- 사실 정확성 필수. 없는 행동·수치·위험·포식 날조 금지.\n"
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
    """LLM 불가 시에도 서사 구조를 갖춘 결정적 대본(실제 사실만)."""
    f = list(info.fun_facts or [])
    depth = (info.depth_range_m or "").split("-")[-1] or "수천"
    hook = f"수심 {depth}m, 빛 한 점 없는 어둠 속. 무언가 움직인다."
    sig = behavior or (f[0] if f else f"{info.common_name_ko}가 천천히 헤엄친다")
    fact1 = f[1] if len(f) > 1 else (f[0] if f else info.habitat or "")
    fact2 = f[2] if len(f) > 2 else ""
    close = "이 깊고 검은 바다에서, 생명은 오늘도 조용히 버틴다."
    lines = [
        {"text": hook, "tone": "gravelly"},
        {"text": f"{sig}.", "tone": "slow"},
        {"text": f"{fact1}.", "tone": "hushed"},
    ]
    if fact2:
        lines.append({"text": f"{fact2}.", "tone": "whispered"})
    lines.append({"text": close, "tone": "reverent"})
    return lines


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
