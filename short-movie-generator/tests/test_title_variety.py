"""★제목·문구에서 '회사원 소재'를 쓰지 않는다(운영자 확정 · 식상함 지적).

운영자 지적: "제발 제목에 **유급휴가 문구** 좀 그만 사용해. 식상하다 정말. 창의력을 좀 발휘하자."

원인: 제목 프롬프트의 **예시**에 「有給ゼロで卵を守る深海の母」가 박혀 있어 LLM이 그 표현을 계속 베꼈다.
  실제 발행분 — "유급휴가 없이 수압300m 견디는 물고기", "유급휴가 없는 수심3520m 펠토스피라…"
조치:
  ① 그 예시를 제거하고, 회차마다 **다른 발상 각도**(_TITLE_LENSES 12종)를 지정해 발상을 흩는다.
  ② 제목 채택 단계에서 회사원 소재를 **반려**한다(LLM이 어겨도 발행되지 않게).
  ③ 훅·롱폼 대본·캡션 프롬프트의 "일상어(노동·제도·생활)" 유도도 넓은 영역으로 바꾼다
     — 제목만 고치면 캡션·나레이션에서 다시 나온다.
"""
import re
from pathlib import Path

import pytest

from src.core import rich_caption as RC

ROOT = Path(__file__).resolve().parents[1]
PROMPT_FILES = ("src/core/rich_caption.py",
                "src/categories/deep_sea/hook.py",
                "src/categories/deep_sea/longform_script.py")


@pytest.mark.parametrize("bad", [
    "유급휴가 없이 수압300m 견디는 물고기",
    "유급휴가 없는 수심3520m 펠토스피라",
    "有給ゼロで卵を守る深海の母",
    "残業続きの深海の掃除屋",
    "上司のいない海で生きる魚",
])
def test_stale_office_titles_are_rejected(bad):
    """★실제로 발행됐던 문구가 다시는 채택되지 않아야 한다."""
    assert not RC._valid_title(bad, ""), f"식상 표현인데 제목으로 채택됩니다: {bad}"


@pytest.mark.parametrize("good", [
    "수심3520m 어둠 속 8년을 기다린 알",
    "水圧800気圧、骨のない体で沈む",
    "光のない海で、目を捨てた魚",
])
def test_normal_titles_still_pass(good):
    """게이트가 과하면 멀쩡한 제목까지 막힌다 — 정상 제목은 통과해야 한다."""
    assert RC._valid_title(good, ""), f"정상 제목이 반려됩니다: {good}"


def test_lenses_rotate_across_species():
    """★같은 각도만 반복하면 제목이 또 비슷해진다 — 종에 따라 각도가 흩어져야 한다."""
    assert len(RC._TITLE_LENSES) >= 8, "발상 각도가 너무 적습니다"
    names = ["Ophidiidae", "Liparidae", "Grimpoteuthis", "Rajidae", "Porifera",
             "Ctenophora", "Asteroidea", "Teuthida", "Aphyonidae", "Selachimorpha"]
    picked = {RC._pick_lens(n) for n in names}
    assert len(picked) >= 4, f"각도가 쏠려 있습니다: {picked}"
    # 결정론: 같은 종은 항상 같은 각도(회차마다 제목이 요동치지 않게)
    assert RC._pick_lens("Ophidiidae") == RC._pick_lens("Ophidiidae")


def test_prompt_no_longer_teaches_the_office_joke():
    """★프롬프트에 회사원 예시가 남아 있으면 LLM이 또 베낀다(사고의 직접 원인)."""
    for rel in PROMPT_FILES:
        s = (ROOT / rel).read_text(encoding="utf-8")
        # 검사 대상은 **LLM에게 보이는 프롬프트 본문**뿐이다. 다음은 제외한다:
        #   · 금지 지시문 자체(금지어 목록이라 당연히 그 단어를 담는다)
        #   · 파이썬 주석(사고 경위를 남긴 기록 — LLM은 보지 않는다)
        #   · 반려용 정규식 정의(_STALE_TITLE)
        body = "\n".join(ln for ln in s.splitlines()
                         if "使用禁止" not in ln
                         and "_STALE_TITLE" not in ln
                         and not ln.lstrip().startswith("#"))
        for bad in ("有給ゼロ", "労働基準法", "(労働・制度・生活)"):
            assert bad not in body, f"{rel}: 회사원 소재 예시/유도가 남아 있습니다 — {bad}"


def test_prompt_asks_for_a_different_angle_each_time():
    s = (ROOT / "src" / "core" / "rich_caption.py").read_text(encoding="utf-8")
    assert "{lens}" in s and "_pick_lens(" in s, "회차별 발상 각도가 프롬프트에 주입되지 않습니다"
    assert re.search(r"lens=_pick_lens\(", s), "프롬프트 포맷에 각도가 전달되지 않습니다"
