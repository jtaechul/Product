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
