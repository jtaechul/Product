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


def test_wreck_body_has_no_black_humor():
    """★침몰선=인명 사고 → 코믹·블랙유머 완전 배제(팩트만). 폴백·프롬프트 모두 확인."""
    body = D._fallback_body_jp({"display": "テスト号",
                                "specs": {"type": "cargo ship", "tonnage": "5000", "sunk_year": "1912"}})
    joined = "".join(body)
    assert "港には戻れません" not in joined            # 예전 '블랙유머 1마디' 제거 확인
    # 프롬프트도 유머 금지·사실 전달 지시로 바뀌었는지
    assert "ブラックユーモア" in D._WRECK_BODY_PROMPT and "禁止" in D._WRECK_BODY_PROMPT
    assert "淡々としたブラックユーモアを1節" not in D._WRECK_BODY_PROMPT


def test_ordered_beats_prioritize_underwater_wreck():
    """수중 잔해(wreck) 촬영본이 있으면 반드시 포함하고 더 넉넉히(우선) 담는다.
    순서는 시간순 유지(잔해는 마지막)."""
    doss = {"beats": {
        "afloat": [{"url": f"http://x/a{i}.jpg", "beat": "afloat"} for i in range(6)],
        "portrait": [], "sinking": [{"url": "http://x/s.jpg", "beat": "sinking"}],
        "wreck": [{"url": f"http://x/w{i}.jpg", "beat": "wreck"} for i in range(5)],
    }, "images": []}
    seq = D.ordered_beat_images(doss, max_per_beat=2)
    beats = [s["beat"] for s in seq]
    assert beats.count("wreck") >= 3, "수중 잔해가 우선 포함(≥3컷)돼야"
    assert beats.count("wreck") > beats.count("afloat"), "잔해가 취항컷보다 많이(우선) 담겨야"
    # 시간순: 첫 컷은 afloat, 마지막 컷은 wreck
    assert beats[0] == "afloat" and beats[-1] == "wreck"


def test_ordered_beats_no_wreck_available_ok():
    """수중 잔해 촬영본이 없으면(없는 배) 지어내지 않고 있는 비트만 — wreck 0컷 정상."""
    doss = {"beats": {"afloat": [{"url": "http://x/a.jpg", "beat": "afloat"}],
                      "portrait": [], "sinking": [], "wreck": []}, "images": []}
    seq = D.ordered_beat_images(doss)
    assert all(s["beat"] != "wreck" for s in seq)   # 날조 없음
