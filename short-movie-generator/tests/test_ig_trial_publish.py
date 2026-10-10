"""인스타 시험 릴스 API 요청 모양(운영자 선택 2026-10-09 · 후킹 A·B 겨루기) — 실제 인스타에 보내지 않고 요청만 검사.

- 시험 릴스 = 컨테이너 요청에 trial_params {"graduation_strategy": "MANUAL"} (Meta 2025-12 · 앱에서 직접 '모두에게 공유')
- 버전은 v24.0 고정(새 매개변수를 모르는 옛 버전이 조용히 무시하면 일반 릴스로 올라가는 사고)
- 지표: 한꺼번에 실패하면 지표마다 따로 물어 받을 수 있는 것만 · 오류 문구에 토큰이 남지 않게
"""
import json

from src.core import ig_publish as IG


class _R:
    def __init__(self, ok=True, status=200, data=None, text=""):
        self.ok, self.status_code, self._d, self.text = ok, status, data or {}, text or json.dumps(data or {})

    def json(self):
        return self._d


def test_trial_container_sends_trial_params_on_v24(monkeypatch):
    sent = {}

    def post(url, data=None, timeout=None):
        sent.update(url=url, data=data)
        return _R(data={"id": "C1"})
    monkeypatch.setattr(IG.requests, "post", post)
    assert IG.create_container(IG._FB_BASE, "IG1", "https://x/v.mp4", "cap", "TOK", trial="MANUAL") == "C1"
    assert json.loads(sent["data"]["trial_params"]) == {"graduation_strategy": "MANUAL"} and sent["data"]["media_type"] == "REELS"
    assert "/v24.0/" in sent["url"] and "/v24.0" in IG._IG_BASE
    IG.create_container(IG._FB_BASE, "IG1", "https://x/v.mp4", "cap", "TOK")              # 일반 릴스(예전 발행)엔 붙이지 않는다
    assert "trial_params" not in sent["data"]


def test_publish_trial_reel_flow(monkeypatch):
    calls = []
    monkeypatch.setattr(IG, "resolve_ig_user_id", lambda tok: (IG._IG_BASE, "IG1", "deep.sea"))
    monkeypatch.setattr(IG, "create_container", lambda base, ig, url, cap, tok, trial=None: calls.append(("create", trial)) or "C1")
    monkeypatch.setattr(IG, "wait_container", lambda base, cid, tok, max_wait=300, interval=8: calls.append(("wait", max_wait)))
    monkeypatch.setattr(IG, "publish_container", lambda base, ig, cid, tok: calls.append(("publish", cid)) or "M1")
    monkeypatch.setattr(IG, "media_info", lambda base, mid, tok: {"permalink": "https://www.instagram.com/reel/M1/"})
    r = IG.publish_trial_reel("TOK", "https://x/v.mp4", "cap")
    assert r == {"media_id": "M1", "permalink": "https://www.instagram.com/reel/M1/", "username": "deep.sea", "base": IG._IG_BASE}
    assert calls[0] == ("create", "MANUAL") and calls[-1] == ("publish", "C1")


def test_media_insights_falls_back_per_metric_and_hides_token(monkeypatch):
    monkeypatch.setattr(IG, "resolve_ig_user_id", lambda tok: (IG._IG_BASE, "IG1", "deep.sea"))

    def get(url, params=None, timeout=None):
        ms = params["metric"].split(",")
        if len(ms) > 1:
            return _R(ok=False, status=400, text='{"error":"bad metric reels_skip_rate"}')
        if ms[0] == "reels_skip_rate":
            return _R(ok=False, status=400, text=f'{{"error":"not available","access_token":"{params["access_token"]}"}}')
        val = {"views": 812, "reach": 640, "ig_reels_avg_watch_time": 4300}[ms[0]]
        return _R(data={"data": [{"name": ms[0], "values": [{"value": val}]}]})
    monkeypatch.setattr(IG.requests, "get", get)
    r = IG.media_insights("SECRETTOK", "M1")
    assert r["metrics"] == {"views": 812, "reach": 640, "ig_reels_avg_watch_time": 4300}
    assert "reels_skip_rate" in r["errors"] and "SECRETTOK" not in json.dumps(r)
    assert IG._metric_value({"total_value": {"value": 47.5}}) == 47.5                   # 새 지표는 total_value 로 올 수 있다


def test_trial_reel_refuses_other_account(monkeypatch):
    """실사고 2026-10-10: 키가 개인 계정 것이라 시험 릴스가 그 계정에 올라감 → 올릴 계정이 다르면 컨테이너도 만들지 않는다."""
    import pytest
    made = []
    monkeypatch.setattr(IG, "resolve_ig_user_id", lambda tok: (IG._IG_BASE, "IG9", "lord.shiba.ybd"))
    monkeypatch.setattr(IG, "create_container", lambda *a, **k: made.append(a) or "C9")
    with pytest.raises(IG.IGPublishError):
        IG.publish_trial_reel("TOK", "https://x/v.mp4", "cap", expect="abyss_0cean")
    assert not made
