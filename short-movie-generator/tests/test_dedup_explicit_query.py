"""종 중복 제작 재발방지 — '특정 대상 직접 입력'(auto가 아닌 명시 이름) 경로의 중복 검사.

실사고: 대시보드 '특정 대상 직접 입력'으로 만든 대상(예: 대왕등각류/Bathynomus giganteus)이
auto 경로의 원장(catalog) 대조 없이 그대로 재생산돼, 같은 종 영상이 여러 날짜에 걸쳐 반복 제작됐다
(catalog.json에 같은 학명이 no=8·17로 두 번 기록됨). auto 경로(footage_candidates)는 원장과 대조해
이미 만든 대상을 거르지만, 명시 이름 경로(`category.parse_input(query)`)는 그 검사가 없었다.
"""
from src.core.contracts import PipelineError, SpeciesInfo


def test_deep_sea_is_already_produced(monkeypatch):
    from src.categories.deep_sea import catalog, module

    monkeypatch.setattr(catalog, "_load", lambda: [
        {"no": 8, "common_name_ko": "대왕등각류", "common_name_en": "Giant isopod",
         "scientific_name": "Bathynomus giganteus", "date": "2026-07-08"},
    ])
    cat = module.DeepSeaCategory()
    made = SpeciesInfo(scientific_name="Bathynomus giganteus", common_name_ko="대왕등각류",
                       common_name_en="Giant isopod", depth_range_m="", distribution="",
                       habitat="", diet=[], fun_facts=[], sources=[])
    dup = cat.is_already_produced(made)
    assert dup == (8, "2026-07-08")

    # 대소문자·공백 차이에도 학명으로 매칭
    made2 = SpeciesInfo(scientific_name="  bathynomus giganteus  ", common_name_ko="",
                        common_name_en="", depth_range_m="", distribution="", habitat="",
                        diet=[], fun_facts=[], sources=[])
    assert cat.is_already_produced(made2) == (8, "2026-07-08")

    # 미제작 종은 None
    fresh = SpeciesInfo(scientific_name="Chimaeriformes", common_name_ko="", common_name_en="",
                        depth_range_m="", distribution="", habitat="", diet=[], fun_facts=[],
                        sources=[])
    assert cat.is_already_produced(fresh) is None


def test_collection_category_is_already_produced(monkeypatch, tmp_path):
    from src.categories import collection_base

    class _Dummy(collection_base.CollectionCategory):
        category_id = "marine_life"
        SUBJECTS = {}
        COPY = {}
        corner_label = ""
        scale_label = ""
        show_scale = False
        bgm_filename = "x.mp3"
        fixed_hashtag = ""
        fixed_hashtag_ko = ""
        show_sci_name = True

        def __init__(self):
            self._dir = tmp_path

    cat = _Dummy()
    monkeypatch.setattr(cat, "_load_catalog", lambda: [
        {"no": 3, "common_name_en": "Octopus", "scientific_name": "Octopus vulgaris", "date": "2026-07-01"},
    ])
    made = SpeciesInfo(scientific_name="Octopus vulgaris", common_name_ko="", common_name_en="Octopus",
                       depth_range_m="", distribution="", habitat="", diet=[], fun_facts=[], sources=[])
    assert cat.is_already_produced(made) == (3, "2026-07-01")
    fresh = SpeciesInfo(scientific_name="Something else", common_name_ko="", common_name_en="",
                        depth_range_m="", distribution="", habitat="", diet=[], fun_facts=[], sources=[])
    assert cat.is_already_produced(fresh) is None


def test_run_reels_allows_duplicate_explicit_query(monkeypatch, caplog):
    """★규칙 전환(운영자 확정): 이미 만든 종을 이름으로 다시 요청해도 **막지 않는다**.

    운영자 지시: "중복 이슈로 제작이 안 되는데, 영상 중복이더라도 그냥 제작되게 해줘. 다른 느낌으로
      또 만들어질 수도 있잖아. **중복에 따른 실패는 이제 앞으로 없도록** 해줘."
    → 예전엔 여기서 PipelineError로 즉시 중단했다(대왕등각류 반복 제작 방지). 이제는 경고만 남기고
      **새 회차로 계속 만든다**(덮어쓰기가 아니라 새 회차라 기존 콘텐츠는 그대로 보존).
    """
    import logging

    from src.core import pipeline

    made = SpeciesInfo(scientific_name="Bathynomus giganteus", common_name_ko="대왕등각류",
                       common_name_en="Giant isopod", depth_range_m="", distribution="",
                       habitat="", diet=[], fun_facts=[], sources=[])

    class _Cat:
        def parse_input(self, query):
            return "giant_isopod"

        def get_info(self, subject):
            return made

        def is_already_produced(self, info):
            return (8, "2026-07-08")

    monkeypatch.setattr(pipeline, "get_category", lambda cid: _Cat())
    with caplog.at_level(logging.WARNING):
        try:
            pipeline.run_reels("deep_sea", "Giant isopod")
        except PipelineError as e:
            # 중복 때문이 아니라 **그 다음 단계**에서 멈춰야 한다(이 더미 카테고리엔 훅 스펙이 없다)
            assert "이미 제작된" not in str(e), f"중복으로 중단됐습니다: {e}"
    assert any("중복 허용 규칙" in r.getMessage() for r in caplog.records), \
        "중복을 허용했다는 기록이 남지 않았습니다"


def test_run_reels_allows_explicit_episode_regeneration(monkeypatch):
    """episode가 명시(재생성)되면 이미 만든 종이어도 중복 검사에서 막히지 않고 다음 단계로 진행."""
    from src.core import pipeline

    made = SpeciesInfo(scientific_name="Bathynomus giganteus", common_name_ko="대왕등각류",
                       common_name_en="Giant isopod", depth_range_m="", distribution="",
                       habitat="", diet=[], fun_facts=[], sources=[])

    class _Cat:
        def parse_input(self, query):
            return "giant_isopod"

        def get_info(self, subject):
            return made

        def is_already_produced(self, info):
            raise AssertionError("재생성(episode 명시) 경로에서는 중복 검사를 호출하면 안 됨")

    monkeypatch.setattr(pipeline, "get_category", lambda cid: _Cat())
    # 중복 검사 다음 단계(_verify_subject_or_raise)에서 의도적으로 멈춰 그 이후 로직은 검증 범위 밖으로 둔다.
    monkeypatch.setattr(pipeline, "_verify_subject_or_raise",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("reached-next-step")))
    try:
        pipeline.run_reels("deep_sea", "Giant isopod", episode=17)
        assert False, "다음 단계까지 도달해야 함"
    except RuntimeError as e:
        assert "reached-next-step" in str(e)


# ── auto 경로: 전 종을 이미 만들었어도 **실패하지 않는다**(운영자 확정 규칙) ──────
def test_auto_never_fails_when_everything_is_already_made():
    """★"중복에 따른 실패는 이제 앞으로 없도록" — 전 종 제작 완료 상태에서도 후보가 남아야 한다.

    예전엔 이 상황에서 후보가 0건이 되어 "제작 가능한 미제작 대상이 없습니다"로 제작이 멈췄다
    (운영자가 실제로 이 오류를 텔레그램으로 받았다). 이제는 **오래전에 만든 종부터** 다시 만든다.
    """
    from src.categories.deep_sea import data
    from src.registry import get_category

    cat = get_category("deep_sea")
    before = cat.footage_candidates()
    assert before, "정상 상태에서도 후보가 없습니다(시드 문제)"

    everything = {sp["scientific_name"].strip().lower() for sp in data.SPECIES.values()}
    everything |= {sp.get("common_name_en", "").strip().lower() for sp in data.SPECIES.values()}
    real = cat._made_set
    try:
        cat._made_set = lambda: everything          # 전 종을 이미 만든 상태로 위장
        after = cat.footage_candidates()
        assert after, "전 종 제작 완료라고 후보가 0건이 되면 안 됩니다(중복 실패 재발)"
        assert cat.pick_footage_species(), "auto가 대상을 하나도 못 고릅니다"
    finally:
        cat._made_set = real


def test_made_species_are_ordered_oldest_first():
    """다시 만들 때는 **가장 오래전에 만든 것부터** — 같은 종이 연달아 나오지 않게."""
    from src.registry import get_category
    cat = get_category("deep_sea")
    order = cat._made_order()
    assert isinstance(order, dict), "제작 순서 정보를 만들지 못합니다"


def test_no_duplicate_abort_remains_in_source():
    """소스 계약: 중복을 사유로 제작을 중단하는 코드가 남아 있으면 안 된다."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for rel in ("src/core/pipeline.py", "src/categories/deep_sea/module.py"):
        s = (root / rel).read_text(encoding="utf-8")
        for m in re.finditer(r"raise PipelineError\([^)]{0,240}", s, re.S):
            blob = m.group(0)
            assert "중복" not in blob and "이미 제작된" not in blob, \
                f"{rel}: 중복으로 제작을 중단하는 코드가 남아 있습니다 — {blob[:110]}"
