"""피사체 학습(Gemini 비전) — 소싱한 사진이 '그 종(생물)인지' 대분류로 검증하고,
피사체(눈·몸통) 위치를 찾아 켄번즈 크롭을 정확히 맞춘다.

운영자 요청(명령2): "gemini API가 있으니 해당 종의 이미지를 분석·학습한 뒤 제작에 들어가라."
저작권: 학습(분석)은 어떤 이미지로도 문제없다 — 다만 최종 출력에 쓰는 소스는 라이선스 게이트를
통과한 것만(footage 쪽에서 이미 강제). 이 모듈은 '판별/좌표'만 돌려주고 이미지를 출력에 넣지 않는다.

★핵심 안전규칙(CLAUDE.md Step2 사고 재발방지): 저해상 프레임에서 '종 단위' 시각 식별은 불가능하다.
따라서 `verify_species`는 **대분류 불일치(자동차·사람·미술품·전혀 다른 육상동물)** 만 하드 리젝트하고,
'그 종이 맞는지'는 판단하지 않는다(진짜 생물 사진을 날리지 않게). 확신 없으면 통과(None/True).

키(GEMINI_API_KEY) 없으면 모든 함수가 안전하게 폴백값(None)을 돌려준다 → 호출부는 기존 휴리스틱 사용."""
from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("shorts")

_MODEL = "gemini-2.5-flash"


def _client():
    if not os.environ.get("GEMINI_API_KEY"):
        return None
    try:
        from google import genai
        return genai.Client()
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        log.info("[vision] genai 클라이언트 생성 실패: %s", e)
        return None


def _ask(image_path: str, prompt: str) -> str | None:
    cl = _client()
    if cl is None:
        return None
    try:
        from google.genai import types
        part = types.Part.from_bytes(data=open(image_path, "rb").read(), mime_type="image/jpeg")
        resp = cl.models.generate_content(model=_MODEL, contents=[part, prompt])
        return (resp.text or "").strip() or None
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as e:  # noqa: BLE001
        log.info("[vision] 비전 호출 실패(%s): %s", image_path, e)
        return None


def _json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def available() -> bool:
    """키가 있어 비전 학습이 가능한지(호출부가 로그·분기용으로 참조)."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def verify_species(image_path: str, scientific_name: str = "", common_name_en: str = "") -> bool | None:
    """이 사진이 '해양 생물(그 종의 대분류)'인지 검증. **대분류 불일치만** False로 하드 리젝트.

    반환: True(생물 맞음/판단됨) · False(자동차·사람·미술품·전혀 다른 육상생물 등 명백한 오소싱) ·
          None(키 없음/불확실 → 호출부는 통과시킴).
    ★종 단위 식별은 하지 않는다(저해상 시각 식별 불가 · 진짜 생물 사진 보존)."""
    name = (common_name_en or scientific_name or "").strip()
    hint = f' The intended subject is roughly "{name}".' if name else ""
    prompt = (
        "You are screening a stock photo for a marine-wildlife video. Look at the image."
        f"{hint} Answer STRICT JSON only: "
        '{"is_marine_organism": true|false, "gross_category": "<fish|invertebrate|marine_mammal|'
        'car|person|artwork|land_animal|plant|other>", "confident": true|false}. '
        "Set is_marine_organism=false ONLY for an obvious non-marine subject "
        "(a car, a person's portrait, a painting/illustration, a land animal, a logo). "
        "Do NOT judge the exact species. If it is any real underwater/sea creature or specimen, "
        "set is_marine_organism=true. If unsure, set confident=false."
    )
    d = _json(_ask(image_path, prompt) or "")
    if not d:
        return None
    if d.get("is_marine_organism") is False and d.get("confident") is True:
        cat = str(d.get("gross_category") or "").lower()
        if cat in {"car", "person", "artwork", "land_animal", "plant", "other"}:
            log.info("[vision] 오소싱 배제: %s (%s)", image_path, cat)
            return False
    return True


def locate_focus(image_path: str) -> tuple[float, float] | None:
    """피사체의 초점(눈 우선, 없으면 몸통 중심)을 정규화 좌표(0~1)로. 켄번즈 크롭 중심에 쓴다.

    반환: (fx, fy) 또는 None(키 없음/불확실 → 호출부는 휴리스틱 `_eye_focus`/`_subject_focus` 사용)."""
    prompt = (
        "Locate the main subject (the animal) in this photo. Answer STRICT JSON only: "
        '{"eye": [x, y] or null, "body_center": [x, y], "confident": true|false} '
        "with all coordinates normalized 0..1 (x=left→right, y=top→bottom). "
        '"eye" is the subject\'s nearest visible eye if clearly identifiable, else null. '
        '"body_center" is the centroid of the animal\'s body. If no clear single animal, confident=false.'
    )
    d = _json(_ask(image_path, prompt) or "")
    if not d or d.get("confident") is not True:
        return None
    pt = d.get("eye") or d.get("body_center")
    try:
        fx, fy = float(pt[0]), float(pt[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
        return None
    return (fx, fy)
