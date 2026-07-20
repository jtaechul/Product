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
