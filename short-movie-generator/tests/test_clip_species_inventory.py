"""★확보한 영상이 **제작 대상(종) 인벤토리**에 들어가 바로 제작 가능해야 한다(운영자 확정).

운영자 지적: "확보 영상을 별도 메뉴로 만들 게 아니라 **소싱된 목록(인벤토리)** 에 넣어야지.
  그리고 어떤 종인지 매칭해서 원할 때 바로 쇼츠로 만들 수 있게 해라 — 언제까지 수동으로 할래?"

그래서 28건의 클립을 **자동 식별**해 인벤토리(`discovered.json`)에 등록했다. 근거는 두 겹이며
**어느 하나라도 실패하면 등록하지 않는다**(사실 날조 금지):
  ① NOAA가 그 영상을 실은 **원본 페이지 본문**의 설명 문장에서 분류군을 뽑고
     (예: "This cusk eel in the family Ophidiidae was seen during Dive 09…")
  ② 그 이름을 **위키데이터 분류군**으로 검증 + **해양동물 게이트**(위키백과 본문에 해양·수생
     신호가 있고, "genus of wasps/plants" 같은 육상·식물 정의가 없을 것)를 통과해야 한다.

실측으로 걸러낸 오식별(그대로 뒀으면 가짜 도감이 됐다):
  · crab → **Crabronidae(말벌과)**   · anemone → **Anemone(식물 아네모네)**
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISC = ROOT / "src" / "categories" / "deep_sea" / "discovered.json"
CLIPS = ROOT / "src" / "data" / "noaa_clips.json"


def _rows():
    return json.loads(DISC.read_text(encoding="utf-8"))


def _noaa_backed():
    urls = {c["url"] for c in json.loads(CLIPS.read_text(encoding="utf-8"))["clips"]}
    return [r for r in _rows() if (r.get("footage") or {}).get("url") in urls]


def test_clips_became_producible_subjects():
    """★핵심: 확보한 영상이 '제작 가능한 대상'으로 인벤토리에 들어와 있어야 한다."""
    got = _noaa_backed()
    assert len(got) >= 10, f"인벤토리에 등록된 NOAA 클립 기반 종이 부족합니다: {len(got)}건"


def test_every_entry_has_license_and_credit():
    """저작권 표기가 비면 화면·메타가 허위가 된다(하드룰 #1)."""
    from src.core.contracts import ALLOWED_LICENSES
    for r in _noaa_backed():
        f = r["footage"]
        assert f["license"] in ALLOWED_LICENSES, f"{r['key']}: 허용되지 않는 라이선스 {f['license']}"
        assert f["license"] == "public-domain" and f["credit"].strip()


def test_no_misidentified_taxa_registered():
    """★실측 오식별이 다시 들어오면 안 된다 — 말벌과·식물은 심해 생물이 아니다."""
    keys = {str(r.get("key", "")).lower() for r in _rows()}
    for bad in ("crabronidae", "anemone"):
        assert bad not in keys, f"오식별 분류군이 인벤토리에 등록되어 있습니다: {bad}"


def test_species_fields_are_filled_from_verified_sources():
    """학명·이름이 비어 있으면 '지어낸 이름'과 구분이 안 된다 — 검증에서 온 값만 들어간다."""
    for r in _noaa_backed():
        sp = r["species"]
        assert sp["scientific_name"].strip(), f"{r['key']}: 학명이 비었습니다"
        assert sp["common_name_en"].strip() and sp["common_name_ko"].strip()


def test_no_duplicate_keys():
    keys = [str(r.get("key", "")).lower() for r in _rows()]
    assert len(keys) == len(set(keys)), "같은 종이 인벤토리에 중복 등록되어 있습니다"


def test_pipeline_can_pick_them_up():
    """★배선 계약: 소싱 시드로 실제로 잡혀야 '바로 제작'이 된다(등록만 하고 끝이면 의미 없다)."""
    from src.core import footage as F
    got = _noaa_backed()
    hit = [r for r in got if F._SEED.get(str(r["key"]).lower())]
    assert len(hit) >= 10, f"인벤토리에는 있는데 소싱 시드로 안 잡힙니다: {len(hit)}건"
    one = F._SEED[str(hit[0]["key"]).lower()]
    assert one["url"].startswith("https://oceanexplorer.noaa.gov/")
    assert one["license"] == "public-domain"


# ── 관리자 화면: 인벤토리에 '바로 제작 가능한 종'이 보여야 한다 ──────────
def test_inventory_screen_lists_ready_subjects():
    """★운영자 지적의 핵심: 확보한 것은 **별도 메뉴가 아니라 소싱 인벤토리**에 있어야 하고,
    거기서 바로 제작 버튼을 눌러 만들 수 있어야 한다."""
    import shutil
    import subprocess
    if not shutil.which("node"):
        import pytest as _p
        _p.skip("node 없음")
    r = subprocess.run(["node", str(ROOT / "worker" / "inventory_check.mjs")],
                       capture_output=True, text=True, timeout=180, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-600:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["cardsShown"] == got["readyInFile"], \
        f"제작 가능한 {got['readyInFile']}건 중 {got['cardsShown']}건만 인벤토리에 나옵니다"
    assert got["readyBadges"] == got["readyInFile"], "'확보 완료 · 바로 제작' 표시가 빠졌습니다"
    assert got["hasMakeButton"] == got["readyInFile"], "제작 버튼이 없으면 바로 만들 수 없습니다"
    assert got["tabCount"] == str(got["readyInFile"]), "탭의 건수가 실제와 다릅니다"


def test_inventory_reads_the_producible_list():
    """소스 계약: 인벤토리가 **제작이 실제로 쓰는 목록**(discovered.json)을 읽어야 한다."""
    w = (ROOT / "worker" / "index.mjs").read_text(encoding="utf-8")
    assert "/discovered.json" in w, "인벤토리가 제작 가능한 목록을 읽지 않습니다"
    assert "discovered\\.json" in w, "서버가 그 파일 읽기를 허용하지 않습니다"
    assert "_ready" in w, "'바로 제작 가능' 표시 구분이 없습니다"
