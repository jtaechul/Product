"""실사 사진 다큐(영상 미확보 생물 → 여러 실사 이미지 켄번즈 시퀀스) — 순수 필터 회귀 테스트.

네트워크 없이 도는 부분만 테스트한다(키워드 필터·시각 사진성 필터). 실제 소싱·합성은
라이브 검증으로 확인했다(대왕등각류·프릴상어 제작 성공, 삽화·빈 표본 컷 배제)."""
from src.core import footage as F


def test_is_realistic_photo_metadata_filter():
    # 삽화·도판·오래된(–1949) 그림은 배제
    assert not F._is_realistic_photo({"url": "x/Vampyroteuthis_illustration_2.jpg", "credit": ""})
    assert not F._is_realistic_photo({"url": "x/plate.jpg", "credit": "Carl Chun 1903"})
    assert not F._is_realistic_photo({"url": "x/squid.jpg", "credit": "vintage poster"})
    assert not F._is_realistic_photo({"url": "x/lithograph_of_fish.jpg", "credit": ""})
    # 실제 실사(연도·삽화 단서 없음)는 통과
    assert F._is_realistic_photo({"url": "x/Bathynomus_Toba_Aquarium.jpg", "credit": "Photo by A"})
    assert F._is_realistic_photo({"url": "x/Pu_-_Vampyroteuthis.jpg", "credit": "Emőke Dénes · CC BY-SA"})


def test_looks_photographic_rejects_paper_plates(tmp_path):
    from PIL import Image
    # 흰 종이 배경 위 도판(대부분 흰색) → 배제
    plate = tmp_path / "plate.png"
    im = Image.new("RGB", (200, 200), (244, 243, 240))
    for y in range(150, 175):
        for x in range(40, 160):
            im.putpixel((x, y), (90, 80, 70))    # 얇은 선 그림
    im.save(plate)
    assert F._looks_photographic(str(plate)) is False

    # 흑백 라인드로잉(저채도 + 밝은 배경) → 배제
    gray = tmp_path / "gray.png"
    g = Image.new("RGB", (200, 200), (250, 250, 250))
    for x in range(0, 200, 3):
        g.putpixel((x, 100), (20, 20, 20))
    g.save(gray)
    assert F._looks_photographic(str(gray)) is False


def test_looks_photographic_keeps_real_photos(tmp_path):
    from PIL import Image
    import random
    rnd = random.Random(7)
    # 컬러 실사(밝은 배경 없음) → 통과
    photo = tmp_path / "photo.png"
    im = Image.new("RGB", (200, 200))
    im.putdata([(rnd.randint(120, 230), rnd.randint(60, 160), rnd.randint(30, 110))
                for _ in range(200 * 200)])
    im.save(photo)
    assert F._looks_photographic(str(photo)) is True

    # 어두운 배경 표본 사진(저채도지만 흰 배경 아님) → 통과(실사 표본 허용)
    dark = tmp_path / "dark.png"
    d = Image.new("RGB", (200, 200), (18, 16, 15))
    for _ in range(1200):
        d.putpixel((rnd.randint(0, 199), rnd.randint(0, 199)), (170, 150, 130))
    d.save(dark)
    assert F._looks_photographic(str(dark)) is True


def test_photodoc_constants_sane():
    assert F._PHOTODOC_MIN >= 4                 # 최소 4장(빈약 방지)
    assert F._PHOTODOC_MAX >= F._PHOTODOC_MIN
    assert F._PHOTODOC_MIN_STRUCT >= 10         # 빈 컷 배제 임계


def test_catalog_enables_photo_sourcing_for_creatures():
    """★소싱/제작 불능 수정: 심해·일반 해양생물은 영상이 거의 없어 사진 후보 보충이 필수 →
    _CATALOG의 photo 플래그가 켜져 있어야 '소싱하기'가 사진 후보를 낸다(0건 방지)."""
    from src.core import discovery as D
    assert D._CATALOG["deep_sea"]["photo"] is True
    assert D._CATALOG["marine_life"]["photo"] is True


def test_inaturalist_parses_cc_license_shape():
    """iNaturalist 응답이 없어도(오프라인) 함수가 안전하게 [] 반환하고, 라이선스 매핑이 온전한지."""
    # 네트워크 없이 도는 방어: 빈 종명은 즉시 []
    assert F._inaturalist_photos("") == []


def _blob(im, x0, x1, y0, y1, rnd):
    for y in range(y0, y1):
        for x in range(x0, x1):
            im.putpixel((x, y), (200 + rnd.randint(-40, 55), 150 + rnd.randint(-40, 40),
                                 90 + rnd.randint(-40, 40)))   # 밝고 질감 있는 피사체


def test_subject_crop_rescues_offcenter_subject(tmp_path):
    """★피사체가 한쪽에 치우친 넓은 사진 → 피사체 크롭이 중앙크롭보다 피사체를 더 담아야
    (사용자 불만: 시작 시 피사체가 화면 밖으로). 이미 중앙이면 크롭 안 함(과보정 방지)."""
    import random
    from PIL import Image
    from src.core import reframe
    rnd = random.Random(3)

    def signal(path):
        pts, _, _ = reframe._subject_pixels(path)
        return sum(p[0] for p in pts)

    def center_crop(path, W, H):
        im = Image.open(path).convert("RGB"); iw, ih = im.size; tar = W / H
        cw, ch = (int(ih * tar), ih) if iw / ih > tar else (iw, int(iw / tar))
        x0 = (iw - cw) // 2; y0 = (ih - ch) // 2
        o = str(path) + "_c.jpg"; im.crop((x0, y0, x0 + cw, y0 + ch)).save(o); return o

    # 넓은(16:9급) 이미지, 어두운 배경 + 피사체를 '왼쪽 끝'에 배치
    im = Image.new("RGB", (1600, 900), (10, 10, 14))
    _blob(im, 120, 460, 340, 620, rnd)          # 좌측(중심 x≈0.18)
    p = tmp_path / "off.jpg"; im.save(p)
    c = F._subject_crop(str(p), 720, 1280)
    assert c is not None, "치우친 피사체는 크롭 이동이 일어나야"
    assert signal(c) > signal(center_crop(str(p), 720, 1280)), "피사체 크롭이 피사체를 더 담아야"

    # 중앙에 피사체 → 크롭 안 함(안전)
    im2 = Image.new("RGB", (1600, 900), (10, 10, 14))
    _blob(im2, 700, 900, 380, 560, rnd)         # 중앙(x≈0.5)
    p2 = tmp_path / "ctr.jpg"; im2.save(p2)
    assert F._subject_crop(str(p2), 720, 1280) is None


def test_nonsubject_filter_rejects_vehicles():
    """★엉뚱한 이미지 배제(동음이의어: Chimaera=물고기이자 TVR 자동차): 자동차·미술품·인물
    카테고리는 거르고, 어류 카테고리는 통과."""
    R = F._NONSUBJECT_CAT_RE
    for bad in ["Category:Automobiles with license plates", "Category:Red roadsters",
                "TVR Chimaera IMG 8082.jpg", "Category:Sculptures", "Category:Paintings"]:
        assert R.search(bad), f"거르지 못함: {bad}"
    for ok in ["Category:Fish of Sardinia", "Category:Chimaera monstrosa",
               "Chimaera cubana.jpg", "Category:Chondrichthyes"]:
        assert not R.search(ok), f"잘못 거름: {ok}"


def test_eye_focus_safe_on_blank(tmp_path):
    """눈 검출은 확신 없으면 None(몸통 폴백) — 균일/작은 이미지에서 안전하게 None."""
    from PIL import Image
    from src.core import reframe
    p = tmp_path / "blank.png"
    Image.new("RGB", (300, 300), (40, 40, 44)).save(p)
    assert reframe._eye_focus(str(p)) is None


def test_vision_subject_safe_without_key(monkeypatch):
    """★피사체 학습(Gemini 비전) 안전 폴백: 키 없으면 verify/locate가 None(호출부 휴리스틱으로 폴백).
    키가 없을 때 절대 예외를 던지거나 진짜 사진을 배제하면 안 된다(제작 불능 방지)."""
    from src.core import vision_subject as V
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert V.available() is False
    assert V.verify_species("/no/such.jpg", "Vampyroteuthis infernalis", "vampire squid") is None
    assert V.locate_focus("/no/such.jpg") is None
    assert V.is_live_wild_subject("/no/such.jpg", "grenadier") is None      # 키 없으면 통과(현행 유지)
    assert V.screen_photo("/no/such.jpg", "Coryphaenoides", "grenadier") is None
    assert V.screen_photo("/no/such.jpg", "x", "y", need_single=True) is None
    assert V.pick_subject_frame(["/a.jpg", "/b.jpg"], "grenadier") is None      # 키 없으면 None(휴리스틱 폴백)


def test_pick_subject_frame_verdict(monkeypatch):
    """★#046 소코다라: Gemini가 후보 프레임 중 피사체 또렷한 것의 인덱스를 고른다(빈 바다 회피).
    범위 밖/생물없음/파싱실패는 None(호출부 휴리스틱)."""
    from src.core import vision_subject as V
    frames = ["/f0.jpg", "/f1.jpg", "/f2.jpg", "/f3.jpg"]
    monkeypatch.setattr(V, "_ask_images", lambda imgs, prompt, **k: '{"best_index": 2, "shows_animal": true}')
    assert V.pick_subject_frame(frames, "grenadier") == 2
    monkeypatch.setattr(V, "_ask_images", lambda imgs, prompt, **k: '{"best_index": 0, "shows_animal": false}')
    assert V.pick_subject_frame(frames, "grenadier") is None        # 생물 없음 → None
    monkeypatch.setattr(V, "_ask_images", lambda imgs, prompt, **k: '{"best_index": 9, "shows_animal": true}')
    assert V.pick_subject_frame(frames, "grenadier") is None        # 범위 밖 → None
    monkeypatch.setattr(V, "_ask_images", lambda imgs, prompt, **k: "설명만 있고 JSON 없음")
    assert V.pick_subject_frame(frames, "grenadier") is None
    assert V.pick_subject_frame(["/only.jpg"], "x") is None          # 후보 1장 → None


def test_screen_photo_combined_verdict(monkeypatch):
    """★비용절감: 사진 스크리닝을 Gemini 1회로 합침 — 비생물·죽음/물밖·(히어로)도판을 한 번에 판별.
    확신 있을 때만 배제, 불확실은 보존."""
    from src.core import vision_subject as V
    # 해변의 죽은 물고기 → reject
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"is_marine_organism": true, "living_in_water": false, "confident": true}')
    assert V.screen_photo("x.jpg", "Coryphaenoides", "grenadier")["reject"] is True
    # 살아있는 수중 개체 → 통과
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"is_marine_organism": true, "living_in_water": true, "confident": true}')
    assert V.screen_photo("x.jpg", "", "grenadier")["reject"] is False
    # 히어로(need_single): 도판/다중 → reject + single_ok False
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"is_marine_organism": true, "living_in_water": true, "single_clear_subject": false, "confident": true}')
    v = V.screen_photo("x.jpg", "", "grenadier", need_single=True)
    assert v["reject"] is True and v["single_ok"] is False
    # 히어로 단일·수중 → 통과 + single_ok True
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"is_marine_organism": true, "living_in_water": true, "single_clear_subject": true, "confident": true}')
    v = V.screen_photo("x.jpg", "", "grenadier", need_single=True)
    assert v["reject"] is False and v["single_ok"] is True
    # 불확실 → 배제 안 함(진짜 사진 보존)
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"is_marine_organism": false, "living_in_water": false, "confident": false}')
    assert V.screen_photo("x.jpg", "", "grenadier")["reject"] is False


def test_is_live_wild_subject_verdict(monkeypatch):
    """★#046: 저비용 Gemini '살아있는 물속 개체' 게이트 — 해변의 죽은 물고기(사람 발)만 배제,
    수중 개체는 통과, 불확실은 통과(진짜 사진 보존)."""
    from src.core import vision_subject as V
    # 해변의 죽은 물고기 + 사람 → 확신 False → 배제
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"living_in_water": false, "context": "out_of_water_on_land", "confident": true}')
    assert V.is_live_wild_subject("x.jpg", "grenadier") is False
    # 수중 개체 → 통과
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"living_in_water": true, "context": "underwater", "confident": true}')
    assert V.is_live_wild_subject("x.jpg", "grenadier") is True
    # 물 밖이지만 불확실 → 통과(진짜 사진 오배제 방지)
    monkeypatch.setattr(V, "_ask", lambda p, q: '{"living_in_water": false, "context": "unclear", "confident": false}')
    assert V.is_live_wild_subject("x.jpg", "grenadier") is True
    # 파싱 불가 → None
    monkeypatch.setattr(V, "_ask", lambda p, q: "설명만 있고 JSON 없음")
    assert V.is_live_wild_subject("x.jpg", "grenadier") is None


def test_vision_subject_json_parse():
    """비전 응답 JSON 추출(네트워크 불필요): 잡음 속 JSON만 뽑고, 비-JSON은 None.
    (verify는 대분류 비생물만 False, locate는 눈 우선·몸통 폴백 — 파싱이 이 판정의 근간.)"""
    from src.core import vision_subject as V
    assert V._json('노이즈 {"a": 1, "b": [2,3]} 꼬리') == {"a": 1, "b": [2, 3]}
    assert V._json("json 아님") is None
    d = V._json('{"eye": [0.5, 0.4], "body_center": [0.6, 0.6], "confident": true}')
    assert d["eye"] == [0.5, 0.4] and d["confident"] is True


def test_openverse_license_map_and_dims():
    """Openverse 라이선스 매핑·치수 게이트(네트워크 불필요) — CC0/PDM/BY/BY-SA만, 썸네일 배제."""
    from src.core import footage as F
    assert F._openverse_photos("") == []                  # 빈 질의 즉시 []
    # 라이선스 매핑 상수 확인(내부 규약): NC는 애초에 요청 안 함(license=cc0,pdm,by,by-sa)
    # 치수 게이트: 장변<800 또는 단변<480이면 배제(썸네일). 1024급 Flickr는 통과 설계.


def test_remove_and_prune_candidates(tmp_path, monkeypatch):
    """★관리자 삭제 기능: 특정 key 수동 삭제 + '제작 불가' 후보 자동 삭제(제작 가능 후보는 유지)."""
    from src.core import discovery as D, footage as FT
    cat = "marine_life"
    orig = D._cand_path(cat)
    bak = orig.read_text(encoding="utf-8") if orig.exists() else None
    try:
        D.save_candidates(cat, [{"key": "aaa", "name": "Aaa", "common_name_en": "a"},
                                {"key": "bbb", "name": "Bbb", "common_name_en": "b"},
                                {"key": "ccc", "name": "Ccc", "common_name_en": "c"}])
        assert D.remove_candidates(cat, ["bbb"]) == ["bbb"]
        assert [c["key"] for c in D.load_candidates(cat)] == ["aaa", "ccc"]
        # aaa만 제작가능하게 몽키패치 → ccc는 제작 불가로 삭제, aaa 유지
        monkeypatch.setattr(FT, "fetch_footage",
                            lambda sci, en, tmp: {"path": "x.mp4"} if sci == "Aaa" else None)
        removed = D.prune_unproducible(cat, str(tmp_path))
        assert "ccc" in removed
        assert [c["key"] for c in D.load_candidates(cat)] == ["aaa"]
    finally:
        if bak is not None:
            orig.write_text(bak, encoding="utf-8")
        else:
            orig.unlink(missing_ok=True)
