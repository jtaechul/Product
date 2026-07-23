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


# 큰 몸꼴(대분류) 그룹 — 이 수준의 불일치만 잡는다(종 단위 식별 아님 · 저해상서도 신뢰 가능).
_BODY_GROUPS = ("fish", "shark_or_ray", "crustacean", "cephalopod", "gastropod_or_nudibranch",
                "jellyfish_or_ctenophore", "sea_star_or_urchin", "worm", "sea_anemone_or_coral",
                "marine_mammal", "sea_turtle", "other")


def verify_taxon_match(image_path: str, scientific_name: str = "", common_name_en: str = "") -> bool | None:
    """★큰 몸꼴(대분류) 일치 검증(운영자 확정 · 실사고: '이프노푸스(다리로 선 심해어)'로 소싱한 NOAA 클립이
    실제로는 **대왕등각류(갑각류)** 였다 → 오프닝 사진(물고기)과 본문 영상(갑각류)이 다른 종). 저해상에서
    **종 식별은 불가**하지만 '물고기 vs 갑각류 vs 해파리' 같은 **큰 몸꼴 차이는 확실히** 구분된다.
    이 함수는 그 **명백한 몸꼴 불일치만** False로 잡는다(종·과 단위는 판단 안 함 → 진짜 영상 보존).

    반환: True(일치 또는 불확실 → 통과) · False(명백히 다른 큰 몸꼴 · 오종) · None(키 없음)."""
    name = (common_name_en or scientific_name or "").strip()
    if not name:
        return None
    prompt = (
        "You are a marine biologist checking whether a video frame shows the CORRECT kind of animal. "
        f"The clip is supposed to show \"{scientific_name}\" (\"{common_name_en}\"). "
        "Judge ONLY the broad body plan / major group, NOT the exact species. Answer STRICT JSON only: "
        '{"expected_group": "<one of: ' + "|".join(_BODY_GROUPS) + '>", '
        '"dominant_group": "<same set, the main animal actually visible>", '
        '"clear_mismatch": true|false, "confident": true|false}. '
        "Set clear_mismatch=true ONLY when the dominant visible animal is UNMISTAKABLY a different major "
        "group than expected (e.g. expected a fish but it is a crustacean/isopod; expected a crab but it "
        "is a jellyfish). If the frame is empty/dark/unclear, or the animal could plausibly be the "
        "expected group, set clear_mismatch=false and confident=false. Never judge fine species."
    )
    d = _json(_ask(image_path, prompt) or "")
    if not d or "clear_mismatch" not in d:
        return None
    if d.get("clear_mismatch") is True and d.get("confident") is True:
        log.info("[vision] 큰 몸꼴 불일치(오종) 배제: %s (기대 %s / 실제 %s)",
                 image_path, d.get("expected_group"), d.get("dominant_group"))
        return False
    return True


def is_single_subject(image_path: str, species_hint: str = "") -> bool | None:
    """★오프닝훅·엔드카드용 히어로 이미지 게이트(운영자 확정 · 절대 위반 금지): 이미지에 **한 종·한 개체가
    또렷하게 크게** 나와야 한다. 여러 종·여러 개체가 나온 도판(taxonomic plate)·비교표·다중패널 그림은
    거부(실사고: 물고기 E/F/G/H 표본이 나란한 도판이 엔드카드에 삽입됨).

    반환: True(단일 개체 · 히어로 적격) · False(도판/다중 개체/비교표 → 거부) · None(키 없음/불확실).
    ★None이면 호출부는 '확정 아님'으로 보고 그 사진을 쓰지 않는다(안전 폴백=실제 영상 프레임)."""
    hint = f' The subject should be "{species_hint}".' if species_hint else ""
    prompt = (
        "You are choosing a HERO image for a video title card. It must show ONE single animal "
        f"specimen, clearly and prominently.{hint} Answer STRICT JSON only: "
        '{"single_clear_subject": true|false, "reason": "<multi_panel_plate|multiple_specimens|'
        'comparison_figure|tiny_or_unclear|single_ok>"}. '
        "Set single_clear_subject=false if the image is a scientific figure/plate with multiple "
        "specimens or panels (e.g. labeled A/B/C or E/F/G/H), a comparison chart, a collage, or shows "
        "several animals. Set true ONLY for one clear individual animal filling much of the frame."
    )
    d = _json(_ask(image_path, prompt) or "")
    if not d or "single_clear_subject" not in d:
        return None
    ok = bool(d.get("single_clear_subject"))
    if not ok:
        log.info("[vision] 히어로 거부(다중/도판): %s (%s)", image_path, d.get("reason"))
    return ok


def is_live_wild_subject(image_path: str, species_hint: str = "") -> bool | None:
    """★살아있는 야생 개체(물속)인지 게이트(운영자 확정 · 실사고 #046 민태과: 해변 모래 위 죽은 물고기 +
    사람 발이 나온 사진이 본문·오프닝에 삽입됨). 저비용 Gemini로 '문맥'만 판별한다 — **죽었거나·물 밖·육상/
    해변/갑판·사람이 손질/파지·접시·시장·표본** 사진을 거부(살아있는 바다/수족관 개체는 통과).

    ★종ID가 아니라 '문맥(살아있음·물속)' 판별이라 저해상서도 확실(모래 위 물고기+발 vs 어두운 물속 개체).
    반환: True(살아있는 물속 개체) · False(죽음/물 밖/사람손질/육상/식품/표본 · 확신할 때만) · None(키 없음/불확실).
    """
    hint = f' The intended animal is roughly "{species_hint}".' if species_hint else ""
    prompt = (
        "You are screening a stock photo for a WILDLIFE video that must show a LIVING sea animal in water."
        f"{hint} Answer STRICT JSON only: "
        '{"living_in_water": true|false, "context": "<underwater|aquarium|out_of_water_on_land|'
        'held_by_human|on_deck_or_boat|on_plate_or_food|dead_or_specimen|unclear>", "confident": true|false}. '
        "Set living_in_water=false if the animal is clearly DEAD, OUT OF WATER, lying on sand/ground/beach/"
        "deck/table, being held or handled by a person, on a plate, at a market/fishmonger, or a preserved "
        "specimen. Set true only for a live animal in the sea or an aquarium. Do NOT judge the exact species. "
        "If you cannot tell, set confident=false."
    )
    d = _json(_ask(image_path, prompt) or "")
    if not d or "living_in_water" not in d:
        return None
    if d.get("living_in_water") is False and d.get("confident") is True:
        log.info("[vision] 비(非)살아있음/물밖 배제: %s (%s)", image_path, d.get("context"))
        return False
    return True


def screen_photo(image_path: str, scientific_name: str = "", common_name_en: str = "",
                 need_single: bool = False) -> dict | None:
    """★비용 절감(운영자 확정): 사진 스크리닝을 **한 번의 Gemini 호출**로 합친다(예전엔 verify_species +
    is_live_wild_subject + is_single_subject를 따로 불러 사진당 2~3회 → 1회). 종ID는 안 한다(문맥·대분류만).

    반환 dict 또는 None(키 없음/파싱 실패 → 호출부는 통과=진짜 사진 보존).
      {"reject": bool(명백한 배제만), "reason": str, "single_ok": bool|None(need_single일 때만)}
    배제 기준(확신 있을 때만): ① 대분류 비생물(자동차·사람·미술품·육상동물) ② 죽음/물밖/해변·갑판/사람손질/
    접시/표본. need_single이면 ③ 도판·다중개체·비교표는 confident 무관 배제(히어로 부적격)."""
    name = (common_name_en or scientific_name or "").strip()
    hint = f' The intended subject is roughly "{name}".' if name else ""
    single_field = ' "single_clear_subject": true|false,' if need_single else ""
    single_rule = ("" if not need_single else
                   " single_clear_subject=false if it is a scientific plate with multiple specimens/panels, a "
                   "comparison figure, a collage, or several animals; true only for one clear individual.")
    prompt = (
        "You are screening a stock photo for a LIVING marine-wildlife video."
        f"{hint} Answer STRICT JSON only: "
        '{"is_marine_organism": true|false, "living_in_water": true|false,' + single_field +
        ' "confident": true|false}. '
        "is_marine_organism=false ONLY for an obvious non-marine subject (car, person portrait, painting, "
        "land animal, logo). living_in_water=false if the animal is clearly dead, out of water, on sand/beach/"
        "deck/table, handled by a person, on a plate, at a market, or a preserved specimen; true for a live "
        "animal in the sea or an aquarium." + single_rule +
        " Do NOT judge the exact species. If unsure about a field, set confident=false."
    )
    d = _json(_ask(image_path, prompt) or "")
    if not d:
        return None
    conf = d.get("confident") is True
    reject, reason = False, "ok"
    if conf and d.get("is_marine_organism") is False:
        reject, reason = True, "non_marine"
    elif conf and d.get("living_in_water") is False:
        reject, reason = True, "dead_or_out_of_water"
    elif need_single and d.get("single_clear_subject") is False:
        reject, reason = True, "multi_or_plate"          # 도판·다중은 현행 is_single_subject처럼 confident 무관 배제
    if reject:
        log.info("[vision] 스크리닝 배제: %s (%s)", image_path, reason)
    return {"reject": reject, "reason": reason,
            "single_ok": (d.get("single_clear_subject") is True) if need_single else None}


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
