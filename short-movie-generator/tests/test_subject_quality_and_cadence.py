"""★발행 빈도 축소 + 편당 품질 상향(운영자 확정 · @abyss_0cean 개선 실험).

【편당 품질】 실측 실패 사례: #058 `starfish / Asteroidea`(불가사리 **강** 전체),
#059 `shark / Selachimorpha`(상어 **상목** · 553종). 대상이 이렇게 넓으면
  · 수심·분포를 쓸 수 없어 화면이 비고
  · 사실 문장이 위키백과 총론 복붙이 되어 편마다 개성이 사라진다.
→ 제작 **전에** 걸러야 한다. 단, 막아서 제작이 교착되면 안 되므로(기존 원칙)
  auto는 '건너뛰기', 지정 제작은 '차단 + 우회 옵션'으로 나눈다.

【발행 빈도】 하루 1편 이상 발행하는 동안 주간 평균 조회가 1,560 → 715로 반토막 났다.
자동 발행은 원래 없으므로 **강제로 막지 않고**, 최근 7일 발행 수를 화면에 보여 판단을 돕는다.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import subject_quality as SQ

ROOT = Path(__file__).resolve().parents[1]


# ── 편당 품질: 대상 범위 게이트 ──────────────────────────────
def test_real_failures_are_blocked():
    """★실제로 나갔던 '너무 넓은 편'이 다시 통과하면 안 된다."""
    for sci, en in (("Selachimorpha", "shark"), ("Asteroidea", "starfish"),
                    ("Crinoidea", "Crinoidea"), ("Ctenophora", "Ctenophora"),
                    ("Pycnogonida", "Pycnogonida"), ("Chimaeriformes", "Chimaeriformes")):
        got = SQ.assess(sci, en)
        assert not got["ok"], f"{sci}가 통과했습니다(너무 넓은 분류군)"
        assert got["reason"], "왜 막혔는지 설명이 없으면 운영자가 조치할 수 없습니다"


def test_good_subjects_still_pass():
    """★게이트가 멀쩡한 대상까지 막으면 제작이 말라붙는다 — 종·속·과는 통과해야 한다."""
    for sci, en in (("Bathynomus giganteus", "giant isopod"),   # 종
                    ("Bathynomus", "giant isopod"),             # 속
                    ("Aphyonidae", "aphyonid"),                 # 과
                    ("Liparidae", "snailfish"),
                    ("Macrouridae", "grenadier"),
                    ("Peltospira smaragdina", "vent snail")):
        assert SQ.assess(sci, en)["ok"], f"{sci}가 막혔습니다(정상 대상)"


def test_whole_inventory_is_screened_without_wiping_it_out():
    """실측: 지금 인벤토리에 게이트를 걸어도 **제작 가능한 대상이 충분히 남아야** 한다."""
    ok = bad = 0
    for c in ("deep_sea", "marine_life", "marine_algae"):
        p = ROOT / "src" / "categories" / c / "discovered.json"
        if not p.exists():
            continue
        for r in json.loads(p.read_text(encoding="utf-8")):
            sp = r.get("species") or {}
            if SQ.assess(sp.get("scientific_name", ""), sp.get("common_name_en", ""))["ok"]:
                ok += 1
            else:
                bad += 1
    assert ok >= 20, f"게이트를 걸면 남는 대상이 너무 적습니다: {ok}종"
    assert bad >= 1, "너무 넓은 대상이 하나도 안 걸립니다 — 게이트가 사실상 꺼져 있습니다"


def test_pipeline_skips_broad_in_auto_and_blocks_on_explicit():
    """배선 계약: auto=건너뛰기(교착 금지) / 지정=차단(+allow_broad 우회)."""
    t = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert "subject_quality" in t, "파이프라인이 품질 게이트를 부르지 않습니다"
    assert "편당 품질 게이트" in t
    assert "allow_broad" in t, "우회 수단이 없으면 운영자가 예외를 만들 수 없습니다"
    assert "subject_quality" in t.split("_broad_skipped")[0], "auto 경로에 게이트가 없습니다"
    r = (ROOT / "src" / "run_pipeline.py").read_text(encoding="utf-8")
    assert "--allow-broad" in r, "CLI에 우회 옵션이 없습니다"
    wf = (ROOT.parent / ".github" / "workflows" / "generate-short.yml").read_text(encoding="utf-8")
    assert "allow_broad" in wf, "워크플로에서 우회 옵션을 넘길 수 없습니다"


def test_broad_subject_raises_in_explicit_mode(monkeypatch):
    """★문자열 확인이 아니라 실제로 막히는지 — 넓은 대상을 지정하면 PipelineError."""
    from src.core import pipeline as P
    from src.core.contracts import PipelineError, SpeciesInfo

    info = SpeciesInfo(scientific_name="Selachimorpha", common_name_ko="상어",
                       common_name_en="shark", depth_range_m="", distribution="",
                       habitat="", diet=[], fun_facts=["a"], sources=["b"])

    class _Cat:
        def parse_input(self, q):
            return "selachimorpha"

        def get_info(self, k):
            return info

    monkeypatch.setattr(P, "get_category", lambda cid: _Cat())
    with pytest.raises(PipelineError) as e:
        P.run_reels("deep_sea", "Selachimorpha", base_dir=str(ROOT))
    assert "품질" in str(e.value) or "subject_quality" in str(e.value), str(e.value)


def test_allow_broad_lets_it_through(monkeypatch):
    """우회를 켜면 품질 게이트에서는 안 막혀야 한다(그 다음 단계에서 막히는 건 별개)."""
    from src.core import pipeline as P
    from src.core.contracts import PipelineError, SpeciesInfo

    info = SpeciesInfo(scientific_name="Selachimorpha", common_name_ko="상어",
                       common_name_en="shark", depth_range_m="", distribution="",
                       habitat="", diet=[], fun_facts=["a"], sources=["b"])

    class _Cat:
        def parse_input(self, q):
            return "selachimorpha"

        def get_info(self, k):
            return info

    monkeypatch.setattr(P, "get_category", lambda cid: _Cat())
    with pytest.raises(PipelineError) as e:
        P.run_reels("deep_sea", "Selachimorpha", base_dir=str(ROOT),
                    manual={"allow_broad": "true"})
    assert "품질" not in str(e.value), f"우회를 켰는데 품질 게이트가 막았습니다: {e.value}"


def test_auto_skips_broad_and_picks_the_narrow_one(monkeypatch, caplog):
    """★auto는 막지 않고 **건너뛴다** — 넓은 후보가 앞에 있어도 좁은 대상으로 제작이 이어져야 한다.
    (막아버리면 '제작이 또 실패한다'는 기존 사고가 재발한다.)"""
    from src.core import footage as F
    from src.core import pipeline as P
    from src.core.contracts import PipelineError, SpeciesInfo

    infos = {
        "selachimorpha": SpeciesInfo(scientific_name="Selachimorpha", common_name_ko="상어",
                                     common_name_en="shark", depth_range_m="", distribution="",
                                     habitat="", diet=[], fun_facts=["a"], sources=["b"]),
        "bathynomus": SpeciesInfo(scientific_name="Bathynomus giganteus", common_name_ko="대왕구족충",
                                  common_name_en="giant isopod", depth_range_m="600-2000",
                                  distribution="", habitat="", diet=[], fun_facts=["a"],
                                  sources=["b"]),
    }

    class _Cat:
        def footage_candidates(self):
            return ["selachimorpha", "bathynomus"]      # 넓은 후보가 **앞**에 온다

        def pick_footage_species(self):
            return "bathynomus"

        def get_info(self, k):
            return infos[k]

    monkeypatch.setattr(P, "get_category", lambda cid: _Cat())
    monkeypatch.setattr(F, "fetch_footage",
                        lambda *a, **k: {"path": "x.mp4", "license": "public-domain",
                                         "credit": "NOAA"})
    with caplog.at_level("INFO"):
        with pytest.raises(PipelineError):      # 스텁 카테고리라 이후 단계에서 중단됨(정상)
            P.run_reels("deep_sea", "auto", base_dir=str(ROOT))
    text = caplog.text
    assert "품질 게이트" in text and "selachimorpha" in text, "넓은 후보를 건너뛰지 않았습니다"
    assert "대상 선택: bathynomus" in text, "좁은 대상으로 넘어가지 않았습니다"


# ── 발행 빈도 ────────────────────────────────────────────
def test_cadence_card_counts_only_recent_published():
    """최근 7일 · 실제 업로드된 것만 세야 '발행 빈도'가 의미를 가진다."""
    if not shutil.which("node"):
        pytest.skip("node 없음")
    r = subprocess.run(["node", str(ROOT / "worker" / "cadence_check.mjs")],
                       capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-600:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["target"] == 3, f"주간 목표가 바뀌었습니다: {got['target']}"
    assert got["counted"] == 3, f"8일 전·미업로드까지 세고 있습니다: {got['counted']}"
    assert got["over"] is True and got["underOver"] is False
    assert got["cardShowsCount"], "화면에 발행 수가 안 보입니다"
    assert got["cardWarnsWhenOver"] and got["cardEncouragesWhenUnder"]
