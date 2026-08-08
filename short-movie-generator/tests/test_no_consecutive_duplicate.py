"""★같은 종이 연달아 제작되면 안 된다(운영자 확정 · 실사고 #056·#057 아피오누스과).

운영자 지적: "쇼츠 생성 시작 눌렀더니 왜 또 같은 종이 한 번 더 생성되는 거야?"

원인 두 겹:
  ① **중복 판정 근거가 도감 원장(catalog.json) 하나뿐**이었다. 원장 기록(`log_catalog`)은 실패해도
     무시하고 넘어가고(발행 불정지), CI 커밋이 어긋나면 실제 발행분과 따로 논다.
     실측: #056은 콘텐츠 레코드엔 Aphyonidae인데 **원장엔 Ctenophora** → Aphyonidae가 '미제작'으로
     남아 다음 회차에 1순위로 다시 뽑혔다.
  ② 앞서 넣은 '중복 허용' 규칙의 재제작 정렬에서, **원장에 없는 종이 0으로 취급돼 맨 앞**으로 왔다
     → 방금 만들어 아직 기록되지 않은 종이 곧바로 재선택됐다.

조치:
  · `_made_set`/`_made_order`가 **원장 + 실제 발행 레코드(content/*.json)** 를 함께 본다(합집합).
  · 기록이 없으면 재제작 순서에서 **맨 뒤**로 보낸다(0 → 무한대).
  · **최근 `_RECENT_BLOCK` 회차에 만든 종은 재제작 후보에서 제외**한다
    (중복 허용은 풀 소진 시 안전망이지, 바로 다음 회차에 같은 종을 또 만들라는 뜻이 아니다).
"""
from src.categories.deep_sea import module as M
from src.registry import get_category


def _cat():
    return get_category("deep_sea")


def test_made_set_uses_published_records_too():
    """★핵심: 원장이 틀려도 **실제 발행 레코드**로 중복이 잡혀야 한다."""
    from src.core import content_store as CS
    made = _cat()._made_set()
    published = {r["scientific_name"].strip().lower() for r in CS.produced_species(".")}
    assert published, "발행 레코드를 하나도 못 읽었습니다"
    missing = sorted(published - made)
    assert not missing, f"발행했는데 '미제작'으로 판정되는 종이 있습니다: {missing[:5]}"


def test_recently_made_species_are_not_candidates():
    """★실사고 그 자체: 방금 만든 종이 다음 회차 후보에 있으면 안 된다."""
    cat = _cat()
    order = cat._made_order()
    assert order, "제작 순서 정보를 못 읽었습니다"
    newest = max(order.values())
    recent = {k for k, no in order.items() if no > newest - M._RECENT_BLOCK}
    cands = set(cat.footage_candidates())
    hit = sorted(recent & cands)
    assert not hit, f"최근에 만든 종이 다시 후보에 있습니다: {hit[:5]}"


def test_aphyonidae_is_not_picked_again():
    """실제로 연속 제작된 그 종이 후보에서 빠졌는지 직접 확인."""
    assert "aphyonidae" not in set(_cat().footage_candidates()), \
        "연속 중복이 났던 종이 여전히 후보에 있습니다"


def test_unrecorded_species_go_last_not_first():
    """★기록이 없는 종은 재제작 **후순위**여야 한다(예전엔 0이 되어 맨 앞으로 왔다)."""
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "src" / "categories" / "deep_sea"
         / "module.py").read_text(encoding="utf-8")
    i = s.index("def _last_no(")
    assert 'float("inf")' in s[i:i + 500], \
        "기록 없는 종이 맨 앞으로 오는 정렬입니다(방금 만든 종이 곧바로 재선택됩니다)"


def test_candidates_never_empty():
    """중복 허용 규칙은 유지 — 후보가 비어 제작이 실패하면 안 된다."""
    assert _cat().footage_candidates(), "후보가 비었습니다(중복 실패 재발)"


def test_every_published_species_is_in_the_dedup_set():
    """★중복을 실제로 막는 것은 `_made_set()`이다 — 발행한 종이 **하나라도** 빠지면 또 만들어진다.

    ⚠️예전 판정은 '발행 레코드가 **deep_sea 원장**에 이름으로 있는가'였는데, 회차 번호는
      **전 카테고리 공용**이라 marine_life 회차(#062 Crossota)가 deep_sea 원장에 없다고
      거짓 실패했다. 중복을 막는 진짜 계약은 원장이 아니라 **dedup 집합**이므로 그걸 본다
      (`_made_set`은 원장 + 실제 발행 레코드를 합집합으로 본다).
    """
    from src.core import content_store as CS
    from src.registry import get_category
    made = get_category("deep_sea")._made_set()
    missing = [(r["no"], r["scientific_name"]) for r in CS.produced_species(".")
               if str(r["scientific_name"]).strip().lower()
               and str(r["scientific_name"]).strip().lower() not in made]
    assert not missing, f"발행했는데 중복방지 집합에 없습니다(또 만들어집니다): {missing}"


def test_deep_sea_ledger_matches_its_own_records():
    """deep_sea 원장은 **deep_sea 회차**와 종이 일치해야 한다(번호별 대조).

    다른 카테고리(marine_life·shipwreck) 회차는 이 원장에 없는 게 정상이므로 제외한다.
    """
    import json
    from pathlib import Path

    from src.core import content_store as CS
    root = Path(__file__).resolve().parents[1]
    led = {int(x["no"]): x for x in
           json.loads((root / "src" / "categories" / "deep_sea"
                       / "catalog.json").read_text(encoding="utf-8"))}
    bad = []
    for r in CS.produced_species("."):
        no = int(r["no"])
        rec = json.loads((root / "content" / f"{no:03d}.json").read_text(encoding="utf-8"))
        if rec.get("category") != "deep_sea":
            continue
        l = led.get(no)
        if l and str(l["scientific_name"]).strip().lower() != str(r["scientific_name"]).strip().lower():
            bad.append((no, l["scientific_name"], r["scientific_name"]))
    assert not bad, f"원장과 발행 레코드가 어긋납니다(원장=, 발행=): {bad}"


def test_ledger_corrects_a_wrong_species_at_the_same_number(tmp_path, monkeypatch):
    """★근본 원인 수정: 같은 회차 번호에 **다른 종**이 이미 적혀 있으면 실제 제작분으로 고쳐 쓴다.

    예전에는 무조건 무시했다. 그래서 앞선 실행이 번호를 먼저 차지하면 실제로 만든 종이
    원장에 영영 안 들어가고(→ '미제작'으로 남아 **또 만들어짐**), 만들지도 않은 종이
    '제작됨'으로 잠겼다. 실측 어긋남 3건(#27·#56·#59)이 이 경로로 생겼다.
    """
    import json

    from src.categories.deep_sea import catalog as C
    p = tmp_path / "catalog.json"
    monkeypatch.setattr(C, "CATALOG", p)
    C.log_entry(7, "흡혈오징어", "Vampire squid", "Vampyroteuthis infernalis", "2026-08-01")
    # 같은 번호에 실제로는 다른 종이 제작됐다 → 정정되어야 한다
    C.log_entry(7, "상어", "shark", "Selachimorpha", "2026-08-06")
    rows = json.loads(p.read_text(encoding="utf-8"))
    assert len(rows) == 1, f"번호가 중복 append 됐습니다: {rows}"
    assert rows[0]["scientific_name"] == "Selachimorpha", \
        f"실제 제작분으로 정정되지 않았습니다: {rows[0]}"
    # 같은 종을 다시 기록해도 안전해야 한다(중복 호출)
    C.log_entry(7, "상어", "shark", "Selachimorpha", "2026-08-06")
    assert len(json.loads(p.read_text(encoding="utf-8"))) == 1
