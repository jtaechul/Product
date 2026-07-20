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
