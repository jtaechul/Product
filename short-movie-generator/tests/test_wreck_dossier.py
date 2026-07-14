"""shipwreck 다큐멘터리 — dossier 순수 함수(네트워크 불필요) 회귀 테스트."""
from src.categories.shipwreck import dossier as D


def test_expand_cvt_and_tonnage_templates():
    assert D._expand_templates("{{cvt|415.1|ft}}") == "415.1 ft"
    assert D._expand_templates("{{convert|70|m}}") == "70 m"
    assert "4898 GRT" in D._expand_templates("{{GRT|4898}}, {{NRT|2750}}")


def test_clean_field_strips_wikilinks_and_flag_junk():
    assert D._clean_field("[[J.L. Thompson and Sons]], [[Sunderland]]") == "J.L. Thompson and Sons, Sunderland"
    # 플래그 템플릿 파편 'border|20px' 제거
    assert D._clean_field("border|20px Cunard Line").endswith("Cunard Line")


def test_valid_spec_rejects_miscaptured_values():
    # 빈 필드가 다음 파라미터를 삼킨 경우(값에 '=' 포함) → 버린다
    assert not D._valid_spec("christened = Mary, Lady Inverclyde")
    assert not D._valid_spec("owner= Albyn Line")
    assert D._valid_spec("Cargo ship")
    assert not D._valid_spec("x" * 120)   # 과길이


def test_norm_license_blocks_nc_allows_open():
    assert D._norm_license("CC BY-NC 4.0") is None          # 비상업 차단
    assert D._norm_license("CC BY-ND 2.0") is None
    assert D._norm_license("Public domain") == "public-domain"
    assert D._norm_license("CC0") == "cc0"
    assert D._norm_license("CC BY-SA 4.0") == "cc-by-sa"
    assert D._norm_license("CC BY 2.0") == "cc-by"
    assert D._norm_license("") is None


def test_classify_beat_orders_story():
    assert D._classify_beat("Pecio SS Thistlegorm underwater", "") == "wreck"
    assert D._classify_beat("Lusitania Sunk By a Submarine newspaper", "") == "sinking"
    assert D._classify_beat("Andrea Doria on slip before launch", "") == "afloat"
    assert D._classify_beat("Builder's model of the ship", "") == "portrait"
    # 기념비·승객명단 등 화면 부적합 → skip
    assert D._classify_beat("Lusitania memorial plaque", "") == "skip"


def test_jp_type_and_spec_helpers():
    assert D._jp_type("Cargo ship") == "貨物船"
    assert D._jp_type("Ocean liner") == "大型客船"
    assert D._jp_type("WWII German U-boat") == "潜水艦"
    assert D._jp_type("") == ""
    assert D._year("9 April 1940") == "1940"
    assert D._tonnage_short("4898 GRT, 2750 NRT") == "4898 GRT"


def test_spec_card_lines_only_known_fields():
    dossier = {"specs": {"type": "Cargo ship", "tonnage": "4898 GRT", "launched": "9 April 1940",
                         "sunk_year": "1941"}, "display": "SS Thistlegorm"}
    rows = dict(D.spec_card_lines(dossier))
    assert rows["船種"] == "貨物船"
    assert rows["進水"] == "1940年"
    assert rows["沈没"] == "1941年"
    # 값이 없는 필드는 카드에 넣지 않는다(날조 없음)
    assert "全長" not in rows


def test_fallback_body_is_keigo_and_ship_specific():
    dossier = {"specs": {"type": "Cargo ship", "tonnage": "4898 GRT", "launched": "1940",
                         "sunk_year": "1941"}, "display": "SS Thistlegorm"}
    body = D._fallback_body_jp(dossier)
    joined = "".join(body)
    assert "SS Thistlegorm" in joined
    assert "貨物船" in joined and "1941年" in joined
    # 敬体(하드룰 #8): 반말 종결('だ。'/'する。') 금지
    assert "だ。" not in joined
    assert len(body) >= 10


def test_ordered_beat_images_follows_story_order():
    dossier = {
        "images": [],
        "beats": {
            "afloat": [{"url": "a", "title": "afloat", "beat": "afloat", "license": "cc-by"}],
            "portrait": [{"url": "p", "title": "portrait", "beat": "portrait", "license": "cc-by"}],
            "sinking": [{"url": "s", "title": "sinking", "beat": "sinking", "license": "cc-by"}],
            "wreck": [{"url": "w", "title": "wreck", "beat": "wreck", "license": "cc-by"}],
        },
    }
    seq = D.ordered_beat_images(dossier, max_per_beat=1)
    assert [s["beat"] for s in seq] == ["afloat", "portrait", "sinking", "wreck"]
