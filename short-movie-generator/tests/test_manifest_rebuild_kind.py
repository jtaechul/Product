"""manifest 재생성이 레코드 종류(kind)를 보존하는지 — 실사고 회귀 테스트.

실사고(nv-29999730295): rebuild_manifest가 longform만 특별 취급하고 나머지를 전부 else로
떨어뜨려 narrate 레코드가 kind="reels" · 이름 "종"으로 재생성됐다. 그 결과
① 라이브러리 '쇼츠' 목록과 실행 현황에 유령 항목이 뜨고
② /c/<id> 상세는 3자리 쇼츠 레코드를 못 찾아 "아직 제작이 완료되지 않았거나…"만 표시됐다.
"""
import json

from src.core import content_store as cs


def _write(base, name, rec):
    (base / "content").mkdir(parents=True, exist_ok=True)
    (base / "content" / name).write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def test_rebuild_preserves_narrate_kind(tmp_path):
    _write(tmp_path, "nv-123.json", {
        "id": "nv-123", "kind": "narrate", "mode": "longform",
        "created_at": "2026-07-23T11:38:59+00:00",
        "yt_title": "夜の海", "yt_title_ko": "밤바다",
        "media": {"video_url": "https://example.invalid/a.mp4"},
    })
    cs.rebuild_manifest(str(tmp_path))
    man = json.loads((tmp_path / "content" / "manifest.json").read_text(encoding="utf-8"))
    e = next(x for x in man if x["id"] == "nv-123")
    assert e["kind"] == "narrate"          # ★ 예전엔 "reels"로 뒤집혔다
    assert e["yt_title"] == "夜の海"
    assert e["mode"] == "longform"
    assert e["has_video"] is True
    assert "common_name_ko" not in e       # 쇼츠 형태로 오염되지 않는다


def test_rebuild_keeps_longform_and_reels_shapes(tmp_path):
    _write(tmp_path, "lf-1.json", {
        "id": "lf-1", "kind": "longform", "n": 6, "total_s": 400.0,
        "created_at": "2026-07-10T00:00:00+00:00",
        "yt_title": "TOP6", "yt_title_ko": "톱6", "media": {"video_url": "u"},
    })
    _write(tmp_path, "001.json", {
        "id": "001", "kind": "reels", "created_at": "2026-07-08T00:00:00+00:00",
        "species": {"common_name_ko": "대왕등각류", "common_name_en": "Giant isopod",
                    "scientific_name": "Bathynomus giganteus"},
    })
    cs.rebuild_manifest(str(tmp_path))
    man = {x["id"]: x for x in
           json.loads((tmp_path / "content" / "manifest.json").read_text(encoding="utf-8"))}
    assert man["lf-1"]["kind"] == "longform" and man["lf-1"]["n"] == 6
    assert man["001"]["kind"] == "reels"
    assert man["001"]["common_name_ko"] == "대왕등각류"


def test_narrate_record_never_lands_in_shorts_list(tmp_path):
    """대시보드 쇼츠 목록 필터(kind!=longform && kind!=narrate)와 동일한 조건으로 확인."""
    _write(tmp_path, "nv-9.json", {"id": "nv-9", "kind": "narrate", "mode": "shorts",
                                   "created_at": "2026-07-23T00:00:00+00:00", "media": {}})
    cs.rebuild_manifest(str(tmp_path))
    man = json.loads((tmp_path / "content" / "manifest.json").read_text(encoding="utf-8"))
    shorts = [x for x in man if x.get("kind") not in ("longform", "narrate")]
    assert shorts == []
