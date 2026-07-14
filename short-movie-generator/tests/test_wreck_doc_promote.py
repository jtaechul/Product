"""유명 난파선 다큐(wreck_doc) 후보 → 승격 → 시드 필드 전달(오프라인 · 파일 IO 모킹)."""
from src.core import discovery as DC


def test_promote_wreck_doc_carries_media_kind_and_wiki_title(monkeypatch):
    cand = {
        "kind": "wreck", "key": "wreck lusitania", "needs_confirm": True,
        "media_kind": "wreck_doc", "wiki_title": "RMS Lusitania", "url": "",
        "image_url": "http://x/hero.jpg", "license": "cc-by-sa", "credit": "Commons",
        "source": "Wikipedia: RMS Lusitania", "name": "Lusitania", "name_ja": "",
        "ship_type": "Ocean liner", "depth": "", "facts": ["선종: Ocean liner"],
        "fact_src": "Wikipedia: RMS Lusitania", "desc": "British ocean liner ...",
    }
    saved: dict = {}
    monkeypatch.setattr(DC, "load_candidates", lambda cid: [cand])
    monkeypatch.setattr(DC, "load_discovered", lambda cid: [])
    monkeypatch.setattr(DC, "save_discovered", lambda cid, items: saved.setdefault("disc", items))
    monkeypatch.setattr(DC, "save_candidates", lambda cid, items: saved.setdefault("cand", items))

    assert DC.promote_candidate("shipwreck", "wreck lusitania") is True
    entry = saved["disc"][0]
    assert entry["kind"] == "wreck"
    fp = entry["footage"]
    assert fp["media_kind"] == "wreck_doc"
    assert fp["wiki_title"] == "RMS Lusitania"
    # 침몰선 subject 정체성이 만들어진다(엔드카드·캡션용)
    assert entry["subject"]["scientific_name"] == "Wreck Lusitania"
    # 승격 후 candidates에서 제거
    assert saved["cand"] == []
