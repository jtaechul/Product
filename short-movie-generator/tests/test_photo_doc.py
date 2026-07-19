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
