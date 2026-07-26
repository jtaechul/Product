"""운영자가 직접 소싱한 영상이 '침몰선'일 때 — 침몰선 형태로 제작(운영자 확정) 회귀 테스트.

운영자 확정: "내가 직접 검색해 소싱한 영상의 경우, 침몰선인 경우에는 침몰선 형태로 제작해도 돼."
설계 확정(선택지):
  · 화면 = **내 영상**  · 대본·캡션 = **그 배 자료(dossier)**
  · 배 이름을 못 찾거나 자료가 부족하면 → **일반 나레이션형으로** 폴백(제작 실패 아님)

네트워크는 전부 모킹한다. ★모킹 주의: `from src.categories.shipwreck import dossier`는 **모듈 객체**를
잡으므로 함수 자체를 monkeypatch.setattr 로 바꾼다(sys.modules 치환은 실행 순서에 의존해 깨진다).
"""
import pytest

from src.categories.shipwreck import dossier as dsr
from src.core import discovery, footage

_DOSS = {"name": "Andrea Doria", "display": "Andrea Doria",
         "specs": {"type": "ocean liner", "tonnage": "29,100 GRT", "fate": "collision, 1956"},
         "summary": "イタリアの客船。1956年に衝突事故で沈没しました。",
         "images": [], "beats": {}, "credits": [], "sources": ["Wikipedia: Andrea Doria"],
         "sink_lat": None, "sink_lon": None, "sink_region_jp": None, "sink_region_en": None}


def _no_commons(monkeypatch):
    """커먼스 파일이 아닌 URL을 쓰므로 구조화데이터 조회는 일어나지 않아야 한다(안전망)."""
    monkeypatch.setattr(discovery, "_commons_file_meta", lambda url: ("", "", "", ""))


# ── 정체성 확보 ───────────────────────────────────────────────────────────────
def test_resolves_wreck_from_title(monkeypatch):
    """제목의 배 이름 + 그 배 자료가 잡히면 침몰선 레코드를 돌려준다."""
    _no_commons(monkeypatch)
    monkeypatch.setattr(dsr, "build_dossier", lambda name, min_images=4: _DOSS)
    rec = discovery.resolve_wreck_from_video("https://example.invalid/x.mp4",
                                             "Diving the wreck of Andrea Doria")
    assert rec and rec["kind"] == "wreck"
    assert rec["key"].startswith("wreck ")
    # ★화면은 운영자 영상 그대로 — 자동 다큐(이미지 시퀀스)로 바꾸지 않는다.
    assert rec["footage"]["url"] == "https://example.invalid/x.mp4"
    assert rec["footage"]["media_kind"] == "operator_wreck"
    assert rec["subject"]["habitat"] == "침몰선"
    assert rec["copy"]["body"], "일본어 카피(훅·본문)가 있어야 hook_intro_spec이 성립한다"


def test_dossier_needs_no_images(monkeypatch):
    """★화면은 내 영상이므로 이미지 장수를 요구하지 않는다(min_images=0으로 조회)."""
    seen = {}
    _no_commons(monkeypatch)

    def _bd(name, min_images=4):
        seen["min"] = min_images
        return _DOSS
    monkeypatch.setattr(dsr, "build_dossier", _bd)
    assert discovery.resolve_wreck_from_video("https://x.invalid/a.mp4", "SS Andrea Doria wreck")
    assert seen["min"] == 0


def test_no_ship_name_falls_back(monkeypatch):
    """배 이름이 없으면 None → 호출부가 일반 나레이션형으로 넘긴다(운영자 확정 폴백)."""
    _no_commons(monkeypatch)
    monkeypatch.setattr(dsr, "build_dossier", lambda name, min_images=4: _DOSS)
    assert discovery.resolve_wreck_from_video("https://x.invalid/a.mp4", "amazing dive 2024") is None


def test_no_dossier_falls_back(monkeypatch):
    """이름은 있어도 **그 배 자료가 없으면** 제작하지 않는다(역사·제원 날조 금지)."""
    _no_commons(monkeypatch)
    monkeypatch.setattr(dsr, "build_dossier", lambda name, min_images=4: None)
    assert discovery.resolve_wreck_from_video("https://x.invalid/a.mp4",
                                              "wreck of Andrea Doria") is None


def test_never_fabricates_specs(monkeypatch):
    """자료에 없는 값은 subject에 채우지 않는다(수심·해역은 문헌·제목에서만)."""
    _no_commons(monkeypatch)
    monkeypatch.setattr(dsr, "build_dossier", lambda name, min_images=4: _DOSS)
    rec = discovery.resolve_wreck_from_video("https://x.invalid/a.mp4", "wreck of Andrea Doria")
    assert rec["subject"]["depth_range_m"] == ""       # 제목에 수심이 없으면 빈 값
    assert rec["subject"]["distribution"] == ""        # 좌표 없으면 해역도 비움


# ── 영상 캐시가 '어떤 형태로 만들 영상인지'를 잃지 않아야 한다 ─────────────────
def test_video_cache_keeps_media_kind(tmp_path, monkeypatch):
    """캐시가 media_kind/wiki_title을 떨어뜨리면 다음 실행이 침몰선인 걸 잊는다(회귀 방지)."""
    monkeypatch.setattr(footage, "_VIDEO_CACHE_PATH", tmp_path / "cache.json")
    monkeypatch.setattr(footage, "_VIDEO_CACHE", None, raising=False)
    footage._video_cache_put("wreck andrea doria", {
        "url": "https://x.invalid/a.mp4", "license": "cc-by", "credit": "Someone",
        "source": "File:A.webm", "media_kind": "operator_wreck", "wiki_title": "Andrea Doria"})
    ref = footage._video_cache_get("wreck andrea doria")
    assert ref["media_kind"] == "operator_wreck"
    assert ref["wiki_title"] == "Andrea Doria"


# ── 파이프라인 배선: 대본·캡션·CTA가 침몰선 쪽으로 갈라지는지 ────────────────
def test_pipeline_branches_on_wreck_dossier():
    """소스 코드 수준 회귀: fv['wreck_dossier']가 대본·캡션 분기를 타야 한다.
    (실제 렌더는 E2E에서 확인 — 여기서는 분기 자체가 지워지지 않았는지 지킨다)"""
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "core" / "pipeline.py"
    txt = src.read_text(encoding="utf-8")
    assert 'elif fv.get("wreck_dossier")' in txt, "대본 분기 누락"
    assert 'fv.get("doc") or fv.get("wreck_dossier")' in txt, "캡션 분기 누락"
    assert "_is_wreck_ep" in txt, "CTA·스팅어 공통 플래그 누락"
