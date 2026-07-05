"""content_store — 콘텐츠 영구 레코드 기록·병합·경량 편집 검증(관리자 페이지 기반)."""
import json

from src.core import content_store
from src.core.contracts import ApprovedAsset, CaptionData, SpeciesInfo


def _info():
    return SpeciesInfo(
        scientific_name="Chauliodus sloani", common_name_ko="바이퍼피시",
        common_name_en="Sloane's viperfish", depth_range_m="500-2500",
        distribution="대서양", habitat="심해 중층", diet=["소형 어류"],
        fun_facts=["큰 송곳니"], sources=["NOAA", "WoRMS"],
    )


def _cap(body="본문"):
    return CaptionData(hook_text="훅", overlay_facts=[], caption_body=body,
                       hashtags=["#바이퍼피시", "#심해생물", "#DeepSea"],
                       reveal_name="바이퍼피시 (Sloane's viperfish)", reveal_fact="송곳니")


def _asset():
    return ApprovedAsset(asset_path="/x/y.jpg", license_ok=True,
                         credit_string="Jane / Wikimedia Commons (cc-by)",
                         source="Wikimedia Commons", license="cc-by")


def test_write_record_shape(tmp_path):
    p = content_store.write_record(str(tmp_path), "007", info=_info(), caption=_cap(),
                                   asset=_asset(), visualizer="panzoom",
                                   video_file="/w/final_007.mp4", series_title="심해 도감")
    rec = json.loads(open(p, encoding="utf-8").read())
    assert rec["id"] == "007" and rec["status"] == "published"
    assert rec["species"]["common_name_en"] == "Sloane's viperfish"
    assert rec["reels"]["video_file"] == "final_007.mp4"
    assert rec["reels"]["hashtags"] == ["#바이퍼피시", "#심해생물", "#DeepSea"]
    assert rec["source"]["image_credit"] == "Jane / Wikimedia Commons (cc-by)"
    assert rec["source"]["info_sources"] == ["NOAA", "WoRMS"]
    assert rec["media"] == {} and rec["post"] is None  # CI/게시물 파트는 이후 채움


def test_caption_scope_merge_preserves_video_and_created(tmp_path):
    content_store.write_record(str(tmp_path), "007", info=_info(), caption=_cap("v1"),
                               asset=_asset(), visualizer="panzoom", video_file="/w/final_007.mp4")
    created = content_store.load_record(str(tmp_path), "007")["created_at"]
    # 캡션만 재생성 → 영상 참조·created_at 보존, 캡션만 갱신
    content_store.write_record(str(tmp_path), "007", info=_info(), caption=_cap("v2"),
                               asset=_asset(), visualizer="veo_text2video",
                               video_file="", scope="caption")
    rec = content_store.load_record(str(tmp_path), "007")
    assert rec["created_at"] == created
    assert rec["reels"]["video_file"] == "final_007.mp4"   # 보존
    assert rec["reels"]["caption"] == "v2"                 # 갱신


def test_update_caption_light_edit(tmp_path):
    content_store.write_record(str(tmp_path), "003", info=_info(), caption=_cap(),
                               asset=_asset(), visualizer="panzoom", video_file="/w/f.mp4")
    assert content_store.update_caption(str(tmp_path), "003", caption_body="수정본",
                                        hashtags=["#a", "#b"])
    rec = content_store.load_record(str(tmp_path), "003")
    assert rec["reels"]["caption"] == "수정본" and rec["reels"]["hashtags"] == ["#a", "#b"]
    assert content_store.update_caption(str(tmp_path), "999") is False  # 없는 id
