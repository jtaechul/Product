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
TONES = ("gravelly", "slow", "whispered", "whispering", "reverent", "tense", "hushed", "awe",
         "mysterious", "somber", "awestruck", "thoughtful", "final")
_DEFAULT_TONE = "slow"

_PROMPT = (
    "너는 조회수 1.7억을 만든 심해 다큐 릴스 공식을 쓰는 대본 작가다. [{species}]로 "
    "약 25~30초 세로 쇼츠 나레이션을 한국어로 쓴다. 목표는 '정보'가 아니라 '끝까지 보게 만드는 충격'이다.\n"
    "★핵심 공식(절대 사실 나열 금지): '단 하나의 가장 충격적이면서 검증된 실제 사실'을 척추로 삼고,\n"
    " 그것을 '2단 리빌 + 재프레이밍'으로 공개한다.\n"
    "[구조 — 정확히 6문장, 현재형 단문, 각 30자 이내, 갈수록 고조]\n"
    "1) 훅: 종명 대신 '~에는 비밀이 있다/규칙이 없다'류로 호기심 갭을 연다.\n"
    "2) 1차 리빌(도입): 그 충격적 사실의 초입을 살짝 연다(긴장).\n"
    "3) 1차 리빌(공개): 충격 사실의 정체를 공개한다.\n"
    "4) 2차 리빌: 숨은 두 번째 층(공생·감각·생존기제 등 '또 다른 실제 사실')을 쌓는다.\n"
    "5) 재프레이밍: 낯설거나 섬뜩한 사실을 '경이'로 뒤집는다.\n"
    "6) 철학적 마무리: 보편적 여운 한 문장(예: '여기선 아무것도 보이는 그대로가 아니다').\n"
    "[규칙]\n"
    "- 아래 '검증된 사실'만 사용. 없는 행동·수치·관계·위험·포식·발광 날조 절대 금지.\n"
    "- 충격성은 '구조'로 만들고 사실은 진짜만. 문장이 뒤로 갈수록 강해지게.\n"
    "- 각 문장 앞 낭독 톤 태그: [mysterious][whispering][somber][awestruck][thoughtful][final] 중.\n"
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
    # 잘린(truncated) 마지막 문장 제거: 종결부호 없이 매우 짧으면 LLM 응답이 끊긴 것으로 보고 버림.
    if len(lines) > 4:
        last = lines[-1]["text"].rstrip()
        if len(last) < 8 and not re.search(r"[.!?…\"'」』.]$|다$|까$|라$", last):
            lines.pop()
    return lines


def _valid(lines: list[dict]) -> bool:
    return 4 <= len(lines) <= 8 and all(l.get("text") for l in lines)


def _trim(lines: list[dict], cap: int = 6) -> list[dict]:
    """길이 초과 시 cap문장으로 압축(훅+본문+철학적 마무리 보존) — 영상 길이·비용 정합."""
    if len(lines) <= cap:
        return lines
    return [lines[0]] + lines[1:len(lines) - 1][:cap - 2] + [lines[-1]]


def _fallback(info: SpeciesInfo, behavior: str) -> list[dict]:
    """LLM 불가 시에도 '충격사실→2단 리빌→재프레이밍→철학' 구조를 갖춘 결정적 대본(실제 사실만)."""
    f = list(info.fun_facts or [])
    depth = (info.depth_range_m or "").split("-")[-1] or "수천"
    shock = f[0] if f else (behavior or f"{info.common_name_ko}의 생존 방식")
    second = f[1] if len(f) > 1 else (info.habitat or "")
    return [
        {"text": f"수심 {depth}m, 이곳엔 비밀이 있다.", "tone": "mysterious"},        # 훅
        {"text": "빛도 온기도 없는 완전한 어둠.", "tone": "somber"},                 # 1차 리빌 도입
        {"text": f"그런데, {shock}.", "tone": "whispering"},                       # 1차 리빌 공개
        {"text": f"게다가 {second}." if second else "그리고 그 몸은 압력을 껴안는다.",
         "tone": "awestruck"},                                                    # 2차 리빌
        {"text": "가장 약해 보이는 것이, 이 어둠을 지배한다.", "tone": "thoughtful"},  # 재프레이밍
        {"text": "여기선, 아무것도 보이는 그대로가 아니다.", "tone": "final"},         # 철학적 마무리
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
    raw = llm.generate_text(prompt, max_tokens=1400)  # 6문장 + 여유(과거 800→마지막 문장 잘림)
    if raw:
        lines = _parse(raw)
        if _valid(lines):
            lines = _trim(lines, cap=6)   # 6문장 상한(2단 리빌 구조·가속 낭독 정합)
            log.info("[script] LLM 대본 %d문장", len(lines))
            return lines
        log.info("[script] LLM 출력 형식 불량 → 폴백")
    return _fallback(info, behavior)
