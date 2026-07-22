"""★공개영상 소스 확대(운영자 요청) — Internet Archive 저작권 안전필터 + 운영자 수동 드롭.
네트워크 없이 도는 부분만(필터 규칙·로컬 드롭·로컬 복사)."""
from pathlib import Path
from src.core import footage as F


def test_archive_org_empty_query_safe():
    assert F._archive_org_videos("") == []


def test_operator_footage_drop_and_credit(tmp_path, monkeypatch):
    """운영자가 assets/footage/<학명>.mp4를 넣으면 최우선 소스로 잡히고, .credit.txt로 저작자 표기."""
    base = tmp_path / "assets" / "footage"; base.mkdir(parents=True)
    # footage.py의 base 경로를 tmp로 우회(파일시스템만 검증)
    monkeypatch.setattr(F, "__file__", str(tmp_path / "src" / "core" / "footage.py"))
    (tmp_path / "src" / "core").mkdir(parents=True)
    clip = base / "melanocetus_johnsonii.mp4"
    clip.write_bytes(b"\x00" * 200_000)                 # 100KB 초과(존재 게이트)
    got = F._operator_footage("melanocetus johnsonii", "anglerfish")
    assert got and got["license"] == "public-domain" and got["source"].startswith("operator")
    assert got["credit"] == "Public Domain"             # 사이드카 없으면 일반 PD(오귀속 방지)
    (base / "melanocetus_johnsonii.credit.txt").write_text("NOAA Ocean Exploration", encoding="utf-8")
    assert F._operator_footage("melanocetus johnsonii", "x")["credit"] == "NOAA Ocean Exploration"
    # 없는 종은 None(자동 소싱으로)
    assert F._operator_footage("nonexistent species", "") is None


def test_download_copies_local_file(tmp_path):
    """로컬 경로(운영자 드롭)는 HTTP가 아니라 복사로 처리."""
    src = tmp_path / "s.mp4"; src.write_bytes(b"\x00" * 50_000)
    dest = tmp_path / "d.mp4"
    assert F._download(str(src), dest) is True and dest.exists()
    assert F._download("file://" + str(src), tmp_path / "d2.mp4") is True


class _StreamResp:
    """느린/거대 다운로드를 흉내내는 스트리밍 응답(컨텍스트 매니저)."""
    def __init__(self, chunks):
        self._chunks = chunks
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def raise_for_status(self): pass
    def iter_content(self, n):
        for c in self._chunks:
            yield c


def test_download_size_cap_aborts(tmp_path, monkeypatch):
    """★소싱 무한 행 방지: 다운로드가 크기 상한(_DL_MAX_BYTES)을 넘으면 포기(False)하고 부분 파일 제거."""
    import sys, types
    monkeypatch.setattr(F, "_DL_MAX_BYTES", 200_000, raising=False)   # 200KB로 낮춰 테스트
    big = b"\x00" * 100_000
    fake = types.SimpleNamespace(get=lambda *a, **k: _StreamResp([big, big, big]))  # 300KB > 200KB
    monkeypatch.setitem(sys.modules, "requests", fake)
    dest = tmp_path / "big.mp4"
    assert F._download("https://x/big.mp4", dest) is False
    assert not dest.exists()                                          # 부분 파일 삭제


def test_download_deadline_aborts(tmp_path, monkeypatch):
    """★느린(트리클) 서버: 총 벽시계 마감(_DL_MAX_SECS) 초과 시 재시도 없이 포기(False)."""
    import sys, types
    monkeypatch.setattr(F, "_DL_MAX_SECS", 0, raising=False)          # 즉시 마감 → 첫 청크에서 중단
    fake = types.SimpleNamespace(get=lambda *a, **k: _StreamResp([b"\x00" * 50_000]))
    monkeypatch.setitem(sys.modules, "requests", fake)
    dest = tmp_path / "slow.mp4"
    assert F._download("https://x/slow.mp4", dest) is False
    assert not dest.exists()


def test_noaa_oer_search_parses_and_matches_dive(monkeypatch):
    """★NOAA OER 자동 소싱(숨은 geoportal API): 종명 검색→그 종 다이브의 하이라이트 MP4 URL 구성.
    네트워크 없이(monkeypatch) 파싱·다이브 매칭·URL 조립을 검증. '_'가 word char라 \\b 대신 (?!\\d)."""
    class _Resp:
        def __init__(self, payload=None, text=""):
            self._p = payload; self.text = text
        def json(self): return self._p

    def fake_get(url, **kw):
        if "opensearch" in url:
            return _Resp(payload={"results": [
                {"_source": {"apiso_Identifier_s": "EX1711_DIVE14_20171217T010000Z_CPHD",
                             "apiso_Abstract_txt": "chimaera observed at 1500 m"}},
                {"_source": {"apiso_Identifier_s": "EX1708_DIVE01_x"}},   # 다이브 하이라이트 없음 → 스킵
            ]})
        # Compressed 디렉토리 리스팅
        if "EX1711" in url:
            return _Resp(text='<a href="EX1711_VID_20171217_DIVE14_CARTOON_CHIMAERA_Low.mp4">x</a>'
                              '<a href="EX1711_VID_x_DIVE02_OTHER_Low.mp4">y</a>')
        return _Resp(text="")
    import src.core.footage as FT
    monkeypatch.setattr(FT, "requests", __import__("types").SimpleNamespace(get=fake_get), raising=False)
    # requests는 함수 안에서 import되므로 sys.modules로 주입
    import sys, types
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=fake_get))
    got = FT._noaa_oer_videos("chimaera", 3)
    assert len(got) == 1                                   # DIVE14만 매칭(DIVE01은 하이라이트 없음)
    assert got[0]["license"] == "public-domain"
    assert got[0]["url"].endswith("EX1711_VID_20171217_DIVE14_CARTOON_CHIMAERA_Low.mp4")
    assert "DIVE14" in got[0]["source"]
    assert FT._noaa_oer_videos("") == []


def test_video_cache_roundtrip(monkeypatch, tmp_path):
    """★영상 URL 캐시(재발방지 044): 한 번 찾은 영상 URL을 저장→재사용(검색 우회로 분류=제작 일치)."""
    monkeypatch.setattr(F, "_VIDEO_CACHE_PATH", tmp_path / "_video_cache.json", raising=False)
    monkeypatch.setattr(F, "_VIDEO_CACHE", None, raising=False)
    assert F._video_cache_get("Ipnopidae") is None
    F._video_cache_put("Ipnopidae", {"url": "https://noaa/x_Low.mp4", "license": "public-domain",
                                     "credit": "NOAA", "source": "NOAA OER EX1 DIVE1", "trim": [2, 1]})
    got = F._video_cache_get("ipnopidae")            # 대소문자 무관
    assert got and got["url"].endswith("_Low.mp4") and got["trim"] == [2, 1]
    # 새 인스턴스에서도 파일로 영속(글로벌 리셋 후 재로드)
    monkeypatch.setattr(F, "_VIDEO_CACHE", None, raising=False)
    assert F._video_cache_get("Ipnopidae")["source"].startswith("NOAA OER")
    F._video_cache_pop("Ipnopidae")
    monkeypatch.setattr(F, "_VIDEO_CACHE", None, raising=False)
    assert F._video_cache_get("Ipnopidae") is None


def test_fetch_video_footage_never_returns_photo_doc(monkeypatch, tmp_path):
    """★재발방지(실사고 044 이프노푸스: '영상 확보'로 분류됐는데 이미지 슬라이드로 제작): 영상 전용
    함수는 생물에 대해 절대 photo_doc을 반환하지 않는다 — 사진 시드가 있고 영상 소스가 전무하면 None
    (예전엔 사진 시드가 photo_doc을 반환·영상 탐색을 가로채 '영상 확보'로 오분류)."""
    monkeypatch.setattr(F, "_SEED", {"testus fishus": {"url": "https://x/p.jpg", "media_kind": "photo",
                                                        "license": "cc-by", "credit": "X", "source": "photo"}}, raising=False)
    monkeypatch.setattr(F, "_operator_footage", lambda *a, **k: None)
    monkeypatch.setattr(F, "_commons_search", lambda *a, **k: None)
    monkeypatch.setattr(F, "_commons_category_videos", lambda *a, **k: None)
    monkeypatch.setattr(F, "_noaa_oer_videos", lambda *a, **k: [])
    monkeypatch.setattr(F, "_archive_org_videos", lambda *a, **k: [])
    called = {"photodoc": False}
    monkeypatch.setattr(F, "species_photo_doc", lambda *a, **k: called.__setitem__("photodoc", True) or {"photo_doc": True})
    r = F._fetch_video_footage("Testus fishus", "test fish", str(tmp_path))
    assert r is None                       # 영상 전용 함수는 None(photo_doc 반환 금지)
    assert called["photodoc"] is False     # 사진 다큐는 상위 래퍼가 담당 — 여기서 호출 안 함


def test_video_subject_gate_rejects_misidentified():
    """★키워드 오소싱 배제(실사고): 무관 영상은 거부, 진짜 피사체 영상은 통과."""
    ok = F._video_subject_ok
    # 오소싱(거부) — 파일명·카테고리 어디에도 피사체 토큰 없음
    assert ok("Earthworm moving.webm", ["Category:Lumbricus"], "Annelida", "") is False
    assert ok('"Cosmic Sea Slug" Hubble.webm', ["Category:Hubble images"], "Holothuroidea", "sea cucumber") is False
    assert ok("Aotearoa Pasifika Performance.webm", ["Category:Dance"], "Kiwa hirsuta", "yeti crab") is False
    assert ok("Alcohol - Drugslab.webm", ["Category:Harm reduction"], "Chiasmodon niger", "black swallower") is False
    # 진짜(통과) — 파일명 학명 / 공통명 토큰 / 카테고리 분류군
    assert ok("Bathynomus giganteus.webm", [], "Bathynomus", "") is True
    assert ok("Cage diving with a great white shark.webm", [], "Carcharodon carcharias", "great white shark") is True
    assert ok("Feeding Caribbean reef sharks.webm", ["Category:Carcharhinus perezi"], "Carcharhinus perezi", "") is True
    assert ok("Grey reef shark (Carcharhinus amblyrhynchos).webm", [], "Carcharhinus amblyrhynchos", "") is True


def test_token_hit_prefix_and_wholeword():
    assert F._token_hit(["cuttlefish"], "Red cuttle hunting") is True     # 접두 cuttle⊂cuttlefish
    assert F._token_hit(["annelida"], "Earthworm moving") is False        # worm은 earthworm의 전체어 아님
    assert F._token_hit(["shark", "white"], "great white shark") is True


def test_commons_category_videos_parses(monkeypatch):
    """분류군 카테고리 순회로 CC 영상 수확(피사체 정확)."""
    import sys, types
    class _R:
        def __init__(self, p): self._p = p
        def json(self): return self._p
    def fake_get(url, **kw):
        p = kw.get("params", {})
        if p.get("list") == "search":
            return _R({"query": {"search": [{"title": "Category:Bathynomus"}]}})
        if p.get("list") == "categorymembers":
            return _R({"query": {"categorymembers": [
                {"title": "File:Bathynomus giganteus swimming.webm"},
                {"title": "File:Some diagram.svg"}]}})
        if p.get("prop") == "imageinfo":
            return _R({"query": {"pages": {"1": {"title": "File:Bathynomus giganteus swimming.webm",
                "imageinfo": [{"url": "https://x/Bathynomus_giganteus_swimming.webm",
                    "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"},
                                    "Artist": {"value": "Diver"}}}]}}}})
        return _R({})
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=fake_get))
    got = F._commons_category_videos("Bathynomus", "")
    assert got and got["url"].endswith(".webm") and got["license"] == "cc-by-sa"
    assert F._commons_category_videos("") is None


def test_hero_single_subject_gate(monkeypatch):
    """★히어로(오프닝훅·엔드카드) 단일 개체 게이트(재발방지: 여러 종 도판이 엔드카드에 삽입).
    비전 키 없으면 fetch_hero_photo는 None(안전 폴백=영상 프레임). is_single_subject 폴백도 None."""
    from src.core import footage as F, vision_subject as V
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert V.is_single_subject("/no/such.jpg", "fish") is None
    # 후보가 있어도 비전 키 없으면 히어로 사진을 쓰지 않는다(영상 프레임 폴백)
    monkeypatch.setattr(F, "_commons_photo_candidates",
                        lambda q, n=8: [{"url": "http://x/a.jpg", "license": "cc0",
                                         "credit": "c", "source": "s"}])
    import tempfile
    assert F.fetch_hero_photo("Melanocetus johnsonii", "anglerfish", tempfile.mkdtemp()) is None


def test_is_single_subject_json_verdict():
    """비전 응답 파싱: 다중패널/도판이면 False, 단일이면 True."""
    from src.core import vision_subject as V
    assert V._json('{"single_clear_subject": false, "reason": "multi_panel_plate"}')["single_clear_subject"] is False
    assert V._json('{"single_clear_subject": true, "reason": "single_ok"}')["single_clear_subject"] is True


def test_commons_photo_candidates_empty_query():
    from src.core import footage as F
    assert F._commons_photo_candidates("") == []


def test_video_motion_bar_stricter_than_static(monkeypatch):
    """★'moving image' 배제(운영자 확정): 실사 영상은 정지문턱(3)보다 높은 _MIN_VIDEO_MOTION(8)으로
    거른다 — 느린 드리프트(움직임 6)는 사진 켄번즈로는 통과하되 실사 영상 소스로는 거부."""
    from src.core import watermark_qc as wq
    monkeypatch.setattr(wq, "motion_score", lambda *a, **k: 6.0)
    assert wq.is_static_source("x.mp4") is False                 # 기본 3.0 → 통과(켄번즈용)
    assert wq.is_static_source("x.mp4", threshold=F._MIN_VIDEO_MOTION) is True   # 8.0 → 영상 거부
    assert F._MIN_VIDEO_MOTION >= 8.0


def test_nonsubject_filter_blocks_military_homonym():
    """★동음이의어(grenadier=물고기이자 군 척탄병) 오삽입 차단: 군사·의장대 범주는 배제, 물고기는 통과."""
    r = F._NONSUBJECT_CAT_RE
    assert r.search("Grenadier Guards")
    assert r.search("Category:Carabinieri of Italy")
    assert r.search("Soldiers in ceremonial uniform")
    assert r.search("Military parade")
    assert not r.search("Grenadier (Macrouridae) par 400 m de fond")   # 물고기는 통과
    assert not r.search("Coryphaenoides rupestris")


def test_commons_photos_positive_sciname_filter(monkeypatch):
    """★학명 양성검증: 공통명 'grenadier'로 검색해도 학명(Macrouridae) 토큰이 없는 병사 사진은 배제,
    학명이 든 물고기 사진만 채택."""
    import sys, types
    class _R:
        def __init__(self, p): self._p = p
        def json(self): return self._p
    def fake_get(url, **kw):
        p = kw.get("params", {})
        if p.get("list") == "search":
            return _R({"query": {"search": [
                {"title": "File:Grenadier (Macrouridae) 400m.jpg"},
                {"title": "File:Grenadier Guard at palace.jpg"}]}})
        # imageinfo|categories
        return _R({"query": {"pages": {
            "1": {"title": "File:Grenadier (Macrouridae) 400m.jpg",
                  "categories": [{"title": "Category:Macrouridae"}],
                  "imageinfo": [{"url": "https://x/fish.jpg", "width": 1600, "height": 1200,
                                 "extmetadata": {"LicenseShortName": {"value": "CC BY-SA"}, "Artist": {"value": "Ifremer"}}}]},
            "2": {"title": "File:Grenadier Guard at palace.jpg",
                  "categories": [{"title": "Category:Grenadier Guards"}, {"title": "Category:Soldiers"}],
                  "imageinfo": [{"url": "https://x/guard.jpg", "width": 1600, "height": 1200,
                                 "extmetadata": {"LicenseShortName": {"value": "CC BY-SA"}, "Artist": {"value": "X"}}}]}}}})
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(get=fake_get))
    got = F._commons_photos("grenadier", 5, sci_name="Macrouridae")
    urls = [g["url"] for g in got]
    assert "https://x/fish.jpg" in urls           # 물고기 채택
    assert "https://x/guard.jpg" not in urls       # 병사 배제(학명 불일치 + 군사 범주)
