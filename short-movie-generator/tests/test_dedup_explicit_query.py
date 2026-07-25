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


def test_run_reels_blocks_duplicate_explicit_query(monkeypatch):
    """episode 미지정(신규 제작) + 이미 만든 종을 이름으로 직접 요청 → PipelineError로 즉시 중단."""
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
    try:
        pipeline.run_reels("deep_sea", "Giant isopod")
        assert False, "중복 대상인데 예외가 발생하지 않음"
    except PipelineError as e:
        assert "이미 제작된" in str(e) and "#008" in str(e)


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
