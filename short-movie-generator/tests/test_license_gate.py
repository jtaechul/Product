"""라이선스 게이트 단위 테스트 (spec 12장 하드 룰)."""
import pytest

from src.core.contracts import RawAsset
from src.core import license_gate


def _asset(license_, caption="", src="NOAA"):
    return RawAsset(
        asset_path="x.jpg", source=src, license=license_,
        credit_string="c", source_url="u", caption_text=caption,
    )


@pytest.mark.parametrize("lic", ["public-domain", "cc0", "cc-by", "kogl-type1", "CC0", "Public-Domain"])
def test_allowed_licenses_pass(lic):
    ok, _ = license_gate.evaluate(_asset(lic))
    assert ok is True


@pytest.mark.parametrize("lic", ["cc-by-nc", "cc-by-sa", "cc-by-nc-sa", "unknown"])
def test_blocked_licenses_fail(lic):
    ok, _ = license_gate.evaluate(_asset(lic))
    assert ok is False


def test_null_license_blocked():
    assert license_gate.evaluate(_asset(None))[0] is False
    assert license_gate.evaluate(_asset(""))[0] is False


def test_noaa_copyright_caption_blocked():
    ok, reason = license_gate.evaluate(_asset("public-domain", caption="Photo Copyright J. Doe"))
    assert ok is False
    assert "copyright" in reason.lower()


def test_filter_only_passes_approved(tmp_path):
    good = tmp_path / "good.jpg"
    good.write_bytes(b"\xff\xd8fake")
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"\xff\xd8fake")
    assets = [
        RawAsset(str(good), "NOAA", "public-domain", "c", "u"),
        RawAsset(str(bad), "X", "cc-by-nc", "c", "u"),
    ]
    approved = license_gate.filter_assets(assets, str(tmp_path / "approved"))
    assert len(approved) == 1
    assert approved[0].license_ok is True
    assert "good" in approved[0].asset_path
