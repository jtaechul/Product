"""★난파선은 해양생물 채널과 **다른 채널**에 올린다(운영자 확정 · 채널 정체성 분리).

배경(실측): 공개된 29편 중 8편이 난파선이었다. 같은 채널에 '심해 생물'과 '난파선 역사'가
섞이면 구독 이유가 흐려지고(주간 평균 조회 1,560 → 715, -54%), 추천 알고리즘도 시청자를
한 주제로 묶지 못한다. 그래서 **업로드 대상 채널을 카테고리로 가른다.**

핵심 계약 4가지:
  ① shipwreck → "wreck" 채널, 생물(deep_sea/marine_life/marine_algae) → "main" 채널
  ② 채널마다 **다른 환경변수**(YOUTUBE_* / YOUTUBE_WRECK_*)를 읽는다
  ③ 난파선 채널 시크릿이 없으면 **본 채널로 흘려보내지 않고 막는다**(분리가 무력화되면 의미 없음)
  ④ 난파선은 유튜브 카테고리도 생물(15)이 아니라 교육/역사(27)
"""
import os
from pathlib import Path

import pytest

from src.core import youtube_upload as YT

ROOT = Path(__file__).resolve().parents[1]
WF = ROOT.parent / ".github" / "workflows"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN",
              "YOUTUBE_WRECK_CLIENT_ID", "YOUTUBE_WRECK_CLIENT_SECRET",
              "YOUTUBE_WRECK_REFRESH_TOKEN"):
        monkeypatch.delenv(k, raising=False)


def test_wreck_category_routes_to_its_own_channel():
    """①난파선만 분리된다 — 생물 카테고리는 전부 본 채널."""
    assert YT.channel_for_category("shipwreck") == "wreck"
    for bio in ("deep_sea", "marine_life", "marine_algae", "", None):
        assert YT.channel_for_category(bio) == "main", f"{bio!r}가 난파선 채널로 샜습니다"


def test_channels_read_different_secrets(monkeypatch):
    """②두 채널이 같은 시크릿을 읽으면 '분리'가 아니라 이름만 다른 같은 채널이다."""
    assert YT._env_keys("main") != YT._env_keys("wreck")
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "a")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "b")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "c")
    assert YT.has_credentials("main") is True
    # 본 채널 키가 다 있어도 난파선 채널은 '없음'이어야 한다.
    assert YT.has_credentials("wreck") is False


def test_wreck_upload_blocked_when_its_channel_is_not_connected(monkeypatch, tmp_path):
    """③핵심: 난파선 채널이 없다고 본 채널로 올려버리면 분리한 의미가 사라진다 → 막아야 한다."""
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "a")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "b")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "c")
    v = tmp_path / "v.mp4"
    v.write_bytes(b"\0")
    with pytest.raises(RuntimeError) as e:
        YT.upload(str(v), "t", "d", channel="wreck")
    assert "wreck" in str(e.value), "어느 채널이 막혔는지 알 수 없는 오류 메시지입니다"


def test_wreck_uses_history_category_not_animals():
    """④난파선은 'Pets & Animals'가 아니다 — 채널 주제가 다르면 유튜브 카테고리도 달라야 한다."""
    assert YT.default_yt_category("main") == "15"
    assert YT.default_yt_category("wreck") == "27"


def test_upload_workflow_wires_the_split():
    """배선 계약: 워크플로가 카테고리로 채널을 고르고 난파선 시크릿을 실제로 넘겨야 한다."""
    for name in ("upload-short.yml", "upload-longform.yml"):
        t = (WF / name).read_text(encoding="utf-8")
        assert "channel_for_category" in t, f"{name}: 카테고리로 채널을 고르지 않습니다"
        assert "YOUTUBE_WRECK_REFRESH_TOKEN" in t, f"{name}: 난파선 채널 시크릿이 전달되지 않습니다"
        assert "channel=ch" in t, f"{name}: 고른 채널이 업로드에 전달되지 않습니다"


def test_token_health_warms_both_channels():
    """발행이 뜸한 채널일수록 '6개월 미사용 폐기'에 취약 → 두 채널 토큰을 모두 워밍해야 한다."""
    t = (WF / "youtube-token-health.yml").read_text(encoding="utf-8")
    assert "YOUTUBE_WRECK_REFRESH_TOKEN" in t, "난파선 채널 토큰이 점검 대상에서 빠졌습니다"
    assert "YOUTUBE_WRECK_" in t and "YOUTUBE_" in t


def test_dashboard_shows_target_channel():
    """운영자가 '어느 채널로 올라가는지' 모르고 누르면 섞이는 사고가 그대로 재발한다."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "올라갈 채널" in w, "업로드 버튼에 대상 채널 안내가 없습니다"
    assert "난파선 전용 채널" in w


def test_dashboard_renders_the_right_channel_per_record():
    """★문자열 존재만으로는 부족 — 실제로 렌더해서 난파선/생물이 **다르게** 표시되는지 본다."""
    import json
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("node 없음")
    r = subprocess.run(["node", str(ROOT / "worker" / "channel_split_check.mjs")],
                       capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-600:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["bioHasChannelLine"] and got["wreckHasChannelLine"], "대상 채널이 화면에 안 나옵니다"
    assert got["wreckChannel"] == "난파선 전용 채널", got["wreckChannel"]
    assert got["bioChannel"] != got["wreckChannel"], "생물과 난파선이 같은 채널로 표시됩니다"
    assert got["wreckHasWarning"] and not got["bioHasWarning"], "난파선 전용 안내가 잘못 붙었습니다"
