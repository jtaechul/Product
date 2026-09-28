"""v2 자막 글꼴 재발 방지(운영자 확정 2026-09-28 · 실사고).

사고: 자막 글꼴이 가변 글꼴(NotoSansJP-VF)이라 libass가 이름으로 찾지 못했다. 작업 PC는 시스템 일본어 글꼴로
우연히 대체돼 멀쩡해 보였고, 일본어 글꼴이 없는 GitHub 서버에서 조립하자 자막이 전부 네모(□)로 나왔다.
이 테스트는 **서버와 같은 조건(시스템에 일본어 글꼴 없음)** 을 fontconfig로 만들어 그 자리에서 검사한다.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "v2" / "tools"))
import karaoke  # noqa: E402

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")


def _fc_env(tmp_path: Path, latin: bool) -> dict:
    """시스템 일본어 글꼴이 없는 서버 흉내: latin=True면 기본 라틴 글꼴만, False면 글꼴 0개."""
    dirs = ""
    if latin:
        d = next((p for p in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation")
                  if Path(p).is_dir()), "")
        dirs = f"<dir>{d}</dir>" if d else ""
    conf = tmp_path / "fonts.conf"
    conf.write_text(f'<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig>{dirs}'
                    f'<cachedir>{tmp_path}/fc-cache</cachedir></fontconfig>', encoding="utf-8")
    return {**os.environ, "FONTCONFIG_FILE": str(conf)}


@pytest.mark.parametrize("latin", [True, False])
def test_subtitles_render_without_system_japanese_font(tmp_path, latin):
    r = karaoke.verify_font(env=_fc_env(tmp_path, latin))
    assert r["ok"] and r["ink_px"] > 800 and r["diff_vs_fallback_px"] > 400


def test_same_look_everywhere(tmp_path):
    """작업 PC와 서버가 **같은 글꼴**로 그린다(예전엔 PC만 시스템 글꼴로 대체돼 달랐다)."""
    here = karaoke.verify_font()
    server = karaoke.verify_font(env=_fc_env(tmp_path, True))
    assert here["ink_px"] == server["ink_px"]


def test_self_check_blocks_the_old_variable_font(tmp_path, monkeypatch):
    """옛 방식(가변 글꼴 폴더)으로 되돌리면 자가 검사가 반드시 막는다."""
    monkeypatch.setattr(karaoke, "FONTS_DIR", ROOT / "vendor" / "fonts")
    monkeypatch.setattr(karaoke, "FONT_FILE", ROOT / "vendor" / "fonts" / "NotoSansJP-VF.ttf")
    with pytest.raises(karaoke.SubtitleFontError):
        karaoke.verify_font(env=_fc_env(tmp_path, True))


def test_subtitle_font_dir_has_only_the_static_bold():
    """전용 폴더에 같은 이름의 가변본이 끼면 그게 먼저 잡혀 재발할 수 있다."""
    files = sorted(p.name for p in karaoke.FONTS_DIR.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".woff2"))
    assert files == ["NotoSansJP-Bold.ttf"]


def test_assemble_stops_before_making_video_when_font_fails(tmp_path, monkeypatch):
    import json
    import admin
    pilots = tmp_path / "pilots"
    dst = pilots / "bathynomus_giganteus"
    dst.mkdir(parents=True)
    real = ROOT / "v2" / "pilots" / "bathynomus_giganteus"
    shutil.copy(real / "status.json", dst / "status.json")
    monkeypatch.setattr(admin, "V2", tmp_path)
    monkeypatch.setattr(admin, "PILOTS", pilots)

    def broken(*a, **k):
        raise karaoke.SubtitleFontError("네모")
    monkeypatch.setattr(karaoke, "verify_font", broken)
    built = []
    import assemble as A
    monkeypatch.setattr(A, "main", lambda *a, **k: built.append(1))
    with pytest.raises(SystemExit):
        admin.assemble("bathynomus_giganteus")
    st = json.loads((dst / "status.json").read_text(encoding="utf-8"))
    assert built == []                                          # 영상은 만들지 않았다
    assert st["checks"]["subtitle_font"]["ok"] is False
    assert "자막 글꼴" in st["stages"]["video"]["notes"][-1]["text"]
