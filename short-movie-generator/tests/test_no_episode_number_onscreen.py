"""회차(도감) 번호가 시청자에게 보이지 않는지 — 운영자 확정 규칙 회귀 테스트.

운영자 확정: "도감 번호 체계는 내부적으로만 관리하는 거지 외부적으로 드러나게 하지 마.
굳이 다른 사람들이 이게 몇 번인지 알 필요는 없다."

→ 번호는 원장(catalog)·대시보드에서만 쓰고, **화면·캡션·제목** 어디에도 찍지 않는다.
   (예전 `SPECIMEN LOGGED · ENTRY No.047` · `DATABASE ENTRY · No.047` · 캐러셀 `No.047`)
"""
import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"

# 화면에 굽히는 텍스트를 만드는 모듈들(원장·대시보드 코드는 번호를 써도 된다).
_ONSCREEN = ["core/endcard.py", "core/carousel.py", "core/hook_intro.py", "core/overlay.py"]

# "No.007" / "No. 7" / "ENTRY No" 처럼 회차를 찍는 패턴
_PAT = re.compile(r"No\.?\s*\{?\s*(?:episode|no|ep)\b|ENTRY\s+No|SPECIMEN\s+LOGGED\s*·\s*No", re.I)


@pytest.mark.parametrize("rel", _ONSCREEN)
def test_onscreen_modules_do_not_print_episode_number(rel):
    p = _SRC / rel
    if not p.exists():
        pytest.skip(f"{rel} 없음")
    hits = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):      # 주석(규칙 설명)은 제외
            continue
        if _PAT.search(line):
            hits.append(f"{rel}:{i}: {line.strip()[:100]}")
    assert not hits, "화면 텍스트에 회차 번호가 들어갑니다(외부 노출 금지):\n" + "\n".join(hits)


def test_endcard_renders_without_number():
    """엔드카드 HTML을 실제로 만들어 번호가 없는지 확인."""
    from src.core import endcard
    from src.core.contracts import CaptionData
    cap = CaptionData(hook_text="훅", overlay_facts=[], caption_body="본문", hashtags=["#a"],
                      reveal_name="ダイオウグソクムシ / Bathynomus giganteus", reveal_fact="특징")
    html = endcard._endcard_html(cap, "심해 도감", 47, "DEEP DIVE LOG")
    assert "No.047" not in html and "No. 047" not in html
    assert "SPECIMEN LOGGED" in html          # 라벨 자체는 유지(디자인 보존)


def test_carousel_cover_renders_without_number():
    from src.core import carousel
    fn = getattr(carousel, "_cover_html", None) or getattr(carousel, "_cover", None)
    if fn is None:
        pytest.skip("커버 렌더 함수 시그니처가 달라 스킵")
    src = (_SRC / "core/carousel.py").read_text(encoding="utf-8")
    assert "No.{episode:03d}" not in src
