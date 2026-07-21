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
