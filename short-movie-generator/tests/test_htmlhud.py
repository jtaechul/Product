"""htmlhud(애니메이션 HUD 엔진)·endcard HTML·HUD SFX 검증.

브라우저(Chromium) 렌더 경로를 실제로 태워 검증한다. 브라우저가 없으면 skip
(파이프라인은 이 경우 PIL HUD로 폴백하므로 발행 자체는 안전).
"""
import subprocess

import pytest

from src.core import audio, endcard, htmlhud
from src.core.contracts import CaptionData, SpeciesInfo

_HAS_BROWSER = htmlhud._chromium_path() is not None
browser_only = pytest.mark.skipif(not _HAS_BROWSER, reason="Chromium 없음 → PIL 폴백")


def _info():
    return SpeciesInfo(
        scientific_name="Grimpoteuthis sp.", common_name_ko="덤보문어",
        common_name_en="Dumbo Octopus", depth_range_m="3000-4000",
        distribution="전 세계 심해", habitat="심해 저층",
        fun_facts=["귀처럼 생긴 지느러미로 헤엄친다", "수심 4,000m 이하에 산다"],
    )


def _caption():
    return CaptionData(
        hook_text="수심 4,000m, '이것'이 잡혔습니다", overlay_facts=[], caption_body="",
        hashtags=["#a", "#b", "#c"], cut_beats=["미확인 접근", "귀처럼 헤엄친다", "리빌"],
        reveal_name="덤보문어 (Dumbo Octopus)", reveal_fact="귀처럼 헤엄치는 심해 문어",
    )


def _dims(path: str) -> str:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True,
    ).stdout.strip()
    return out


@browser_only
def test_config_splits_reveal_name():
    cfg = htmlhud._config(_caption(), _info(), "DEEP DIVE LOG", [8.0, 8.0, 8.0])
    assert cfg["revealName"] == "덤보문어"
    assert cfg["revealEn"] == "Dumbo Octopus"
    assert cfg["depthMax"] == 4000
    assert cfg["total"] == 24.0 and cfg["revealStart"] == 16.0


def test_schematic_html_has_specimen_panel_and_italic_sci():
    """스키매틱 테마: 생태 데이터 패널·학명 이탤릭·리치 상태카드 마크업 존재(브라우저 불필요)."""
    cfg = htmlhud._config(_caption(), _info(), "DEEP DIVE LOG", [8.0, 8.0, 8.0])
    html = htmlhud._schematic_html(cfg)
    assert 'id="specimen"' in html and "SPECIMEN DATA" in html     # 생태 데이터 패널
    assert '"spDepth"' in html and '"spDiet"' in html              # 생태 필드 주입
    assert "font-style:italic" in html                            # 학명 이탤릭
    assert 'class="schip"' in html and 'class="sbar"' in html     # 리치 상태카드
    assert "viewBox" in html                                       # 월드맵 svg
    assert "#FFC24D" in html                                       # ANALYZING 서술 앰버


def test_proximity_alert_config_and_sfx():
    """근접 경보(alert) 캡션 → cfg.alert/alertAt + sfx_timeline['alert'] 동기, 없으면 미발생."""
    cap = _caption()
    cap.alert = True
    cap.alert_text = "개체가 이쪽으로 접근 중"
    cfg = htmlhud._config(cap, _info(), "DEEP DIVE LOG", [8.0, 8.0, 8.0])
    assert cfg["alert"] is True
    assert 8.0 < cfg["alertAt"] < 16.0            # 컷2 후반, 리빌 이전
    assert cfg["alertText"] == "개체가 이쪽으로 접근 중"
    tl = htmlhud.sfx_timeline(cap, _info(), [8.0, 8.0, 8.0])
    assert tl["alert"] == round(cfg["alertAt"], 3)
    # 경보 없는 캡션이면 sfx에 alert 키 없음(차분한 종)
    assert "alert" not in htmlhud.sfx_timeline(_caption(), _info(), [8.0, 8.0, 8.0])


@browser_only
def test_apply_hud_renders_overlay(tmp_path):
    """작은 영상에 애니메이션 HUD 합성 → 720x1280 mp4 (브라우저 렌더 경로)."""
    base = tmp_path / "base.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=navy:s=720x1280:d=2:r=25", "-pix_fmt", "yuv420p", str(base)],
        check=True,
    )
    out = htmlhud.apply_hud(str(base), _caption(), _info(), "DEEP DIVE LOG",
                            [1.0, 1.0], str(tmp_path))
    assert _dims(out) == "720x1280"
    # HUD 프레임 시퀀스가 실제 생성됐는지
    assert list((tmp_path / "hud_frames").glob("seq_*.png"))


@browser_only
def test_endcard_html_path_renders_png(tmp_path):
    png = endcard._render_png(_caption(), "DEEP DIVE LOG", 7, "DEEP DIVE LOG", str(tmp_path))
    assert png.endswith(".png")
    from PIL import Image
    assert Image.open(png).size == (720, 1280)


def test_endcard_pil_fallback_when_no_browser(tmp_path, monkeypatch):
    """브라우저 실패를 강제해도 PIL 폴백으로 엔드카드 PNG가 나온다 (파이프라인 불정지)."""
    def boom(*a, **k):
        raise htmlhud.HudRenderError("forced")
    monkeypatch.setattr(htmlhud, "render_static", boom)
    png = endcard._render_png(_caption(), "DEEP DIVE LOG", 3, "DEEP DIVE LOG", str(tmp_path))
    from PIL import Image
    assert Image.open(png).size == (720, 1280)


def test_hud_sfx_reveal_louder_than_scan(tmp_path):
    """HUD SFX: 리빌 순간(차임+스팅)이 스캔 구간보다 확실히 크다."""
    base = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=black:s=320x568:d=20:r=25", "-pix_fmt", "yuv420p", str(base)],
        check=True,
    )
    out = audio.add_ambient(
        str(base), str(tmp_path), 20.0,
        {"reveal_accent": True, "hud_sfx": True}, reveal_at_s=16.0,
    )

    def mean_db(t, d):
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-ss", str(t), "-t", str(d), "-i", out,
             "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True,
        ).stderr
        for line in r.splitlines():
            if "mean_volume:" in line:
                return float(line.split("mean_volume:")[1].split("dB")[0])
        return -999.0

    assert mean_db(15.8, 1.0) > mean_db(9.0, 1.0) + 3  # 리빌이 최소 3dB 크다
