"""차별점·작동 방식 3안 추출 (2026-07-17 사용자 확정 — "뭘 파는지 모르겠다" 개선의 연료).

흐름: 기획(plan) 시점에 상품 자료(PDF·캡처에서 enrich가 뽑은 notes/specs)를 텍스트 LLM으로 분석해
"이 제품이 다른 제품과 다르게 해소한 지점 + 무슨 기능·구조로 + 어떻게 작동하는지"를 **서로 다른
각도 3안**으로 도출 → data/mechanism/{row_hash}.json 저장(워크플로가 커밋) → 관리자 기획 탭에서
운영자가 ①3안 중 선택 ②다시 추출 ③직접 의견(custom) 입력 → 대본 ④정체 공개의 뼈대로 사용.

파일 포맷: {"options": [{"title": "...", "mechanism": "..."} x3], "chosen": null|0|1|2, "custom": ""}
- chosen=null 이면 1안(options[0])을 기본 사용. custom이 있으면 custom이 최우선.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.script.generate import (
    _anthropic_generate, _gemini_generate, gemini_key, have_script_key, script_provider)

_SYSTEM = "너는 제품 분석가다. 요청한 JSON만 반환한다. 마크다운·설명·백틱 금지."

_PROMPT = """아래 상품 자료를 분석해, 이 제품이 **같은 종류의 다른 제품들과 다르게** 해소한 지점을
서로 다른 각도로 3안 도출하라. 각 안은 대본 작가가 그대로 쓸 '제품 설명의 뼈대'다.

각 안에 반드시 담을 것(한 안 = 2~3문장, 한국어 구어체 아님·건조한 정리체):
1) 차별 페인포인트: 기존 제품·기존 방식이 못 풀던 게 뭔가
2) 해소 기능·구조: 이 제품은 그걸 풀려고 무슨 기능/구조/부품을 넣었나
3) 작동 방식: 그 기능이 실제로 어떻게 작동해서 문제가 사라지나 (숫자 스펙이 있으면 포함)

규칙: 브랜드명·모델명·가격 금지(종류 일반명사로만). 자료에 없는 기능을 지어내지 마라 —
자료가 빈약해 확신이 없으면 그 안의 title 앞에 "추정: "을 붙여라.
3안은 서로 다른 각도(예: 핵심 메커니즘 / 지속·용량 / 구조·사용성)여야 한다.

출력(JSON만): {"options": [{"title": "8자 내 라벨", "mechanism": "..."}, {...}, {...}]}

상품 자료:
"""


def _path(project_root: Path, row_hash: str) -> Path:
    return Path(project_root) / "data" / "mechanism" / f"{row_hash}.json"


def load(project_root: Path, row_hash: str) -> dict | None:
    p = _path(project_root, row_hash)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[mech] 파일 파싱 실패({e}) — 재추출 대상으로 취급")
        return None


def chosen_text(data: dict | None) -> str | None:
    """운영자 확정 텍스트: custom > options[chosen] > options[0](기본 1안). 없으면 None."""
    if not data:
        return None
    custom = str(data.get("custom") or "").strip()
    if custom:
        return custom
    opts = [o for o in (data.get("options") or []) if str((o or {}).get("mechanism", "")).strip()]
    if not opts:
        return None
    ch = data.get("chosen")
    i = ch if isinstance(ch, int) and 0 <= ch < len(opts) else 0
    o = opts[i]
    return f"{o.get('title', '').strip()}: {o['mechanism'].strip()}".lstrip(": ").strip()


def _extract(product: dict, settings: dict) -> list:
    cfg = settings.get("script", {})
    provider = script_provider(settings)
    model = (cfg.get("gemini_model", "gemini-2.5-flash") if provider == "gemini"
             else cfg.get("model", "claude-sonnet-4-6"))
    material = {
        "상품명": product.get("name", ""),
        "특징": product.get("specs") or [],
        "카테고리": product.get("category", ""),
        "상세자료(notes)": str(product.get("notes") or "")[:3500],
    }
    prompt = _PROMPT + json.dumps(material, ensure_ascii=False, indent=1)
    text = (_gemini_generate(model, _SYSTEM, prompt, 1200) if provider == "gemini" and gemini_key()
            else _anthropic_generate(model, _SYSTEM, prompt, 1200))
    m = re.search(r"\{.*\}", text, re.S)
    data = json.loads(m.group(0)) if m else {}
    opts = []
    for o in (data.get("options") or [])[:3]:
        t, mech = str((o or {}).get("title", "")).strip()[:24], str((o or {}).get("mechanism", "")).strip()
        if mech:
            opts.append({"title": t or "차별점", "mechanism": mech[:400]})
    if not opts:
        raise ValueError(f"차별점 추출 응답에 options 없음: {text[:120]}")
    return opts


def is_confirmed(data: dict | None) -> bool:
    """운영자가 방향을 확정했는가 — confirmed 플래그, 직접 의견(custom), 번호 선택(chosen) 중 하나면 확정."""
    if not data:
        return False
    return (data.get("confirmed") is True
            or bool(str(data.get("custom") or "").strip())
            or isinstance(data.get("chosen"), int))


def prepare(product: dict, settings: dict, project_root: Path,
            extract: bool, gate: bool = False) -> tuple:
    """대본 생성 직전 호출. 반환 (확정 텍스트|None, need_choice).

    ⭐ 선택 게이트(2026-07-17 사용자 확정): gate=True(기획 모드)면 **운영자가 3안 중 방향을 확정하기
    전에는 대본을 만들지 않는다** — 3안만 추출·저장하고 need_choice=True를 돌려 파이프라인이 멈추게 한다.
    확정(custom/chosen/confirmed) 후 재실행되면 그 텍스트를 반환. 자료 없음·키 없음·추출 실패면
    게이트 없이 (None, False)로 기존 흐름 계속(운영자가 막히지 않게)."""
    data = load(project_root, product.get("_row_hash", ""))
    if data is None:
        if not extract or not have_script_key(settings) or not (product.get("notes") or product.get("specs")):
            if extract:
                print("[mech] 상세 자료(notes/specs) 또는 키 없음 — 차별점 추출 생략(게이트 없이 진행)")
            return None, False
        try:
            data = {"options": _extract(product, settings), "chosen": None, "custom": "", "confirmed": False}
            p = _path(project_root, product["_row_hash"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[mech] 차별점·작동방식 3안 추출 완료 → data/mechanism/{product['_row_hash']}.json "
                  f"({' / '.join(o['title'] for o in data['options'])})")
        except Exception as e:
            print(f"[mech] 차별점 추출 실패({type(e).__name__}: {e}) — 게이트 없이 기존 흐름으로 계속")
            return None, False
    if gate and not is_confirmed(data):
        return None, True                     # 운영자 선택 대기 — 대본 생성 전 중단
    txt = chosen_text(data)
    if txt:
        which = "직접 의견" if (data or {}).get("custom") else f"{((data or {}).get('chosen') or 0) + 1}안"
        print(f"[mech] 대본 뼈대 사용: {which} — {txt[:60]}...")
    return txt, False
