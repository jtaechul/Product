"""소싱 plan(③b) 오케스트레이션 단위 테스트 — LLM 없이(키 제거 + generate 주입).

검증 핵심: ⭐ 절대 게이트 — 방향 미확정이면 대본을 만들지 않는다(need_choice), 확정이면 확정
텍스트를 product["차별점_작동방식"]로 주입해 generate_script를 부른다. 3안 추출(LLM)은 CI에서 실증.
python tests/test_sourcing_plan.py
"""
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.sourcing import plan   # noqa: E402

_fails = []
_KEYS = ("SHORTS_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "SHORTS_GEMINI_API_KEY")


def check(cond, label):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}")
    if not cond:
        _fails.append(label)


@contextmanager
def no_keys():
    """대본 키를 확실히 제거 — 게이트가 '키 없음'으로 결정론적으로 스텁하도록."""
    saved = {k: os.environ.pop(k, None) for k in _KEYS}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def _seed_product(root: Path, hsh: str):
    base = root / "data" / "sources"
    (base / "product").mkdir(parents=True, exist_ok=True)
    (base / "promo").mkdir(parents=True, exist_ok=True)
    cand = {"title": "gadget", "title_ko": "접이식 무선 선풍기",
            "coupang_keywords": ["휴대용 선풍기"], "naver": {"coupang_title": "휴대용 미니 선풍기"}}
    (base / "product" / f"{hsh}.json").write_text(json.dumps(
        {"keyword": "선풍기", "hash": hsh, "product": cand,
         "coupang": {"affiliate_url": "https://link.coupang.com/a/AAA"}}), encoding="utf-8")
    (base / "promo" / f"{hsh}.json").write_text(json.dumps(
        {"product_hash": hsh, "keyword": "휴대용 미니 선풍기", "count": 1,
         "videos": [{"title_ko": "목에 걸면 시원", "title": "neck fan demo"}]}), encoding="utf-8")


def _seed_mechanism(root: Path, hsh: str, chosen=0):
    p = root / "data" / "mechanism" / f"{hsh}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "options": [{"title": "냉감 원리", "mechanism": "반도체 냉각판으로 목을 직접 식힌다"},
                    {"title": "지속", "mechanism": "대용량 배터리로 6시간"},
                    {"title": "구조", "mechanism": "날개 없는 구조로 머리카락 안 낌"}],
        "chosen": chosen, "custom": "", "confirmed": True}), encoding="utf-8")


def test_gate_blocks_without_direction():
    print("[T1] ⭐ 게이트 — 방향 미확정이면 대본 생성 안 함")
    with no_keys(), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_product(root, "h1")
        called = {"n": 0}

        def fake_gen(product, settings):
            called["n"] += 1
            return {"title": "X", "lines": []}

        res = plan.generate_plan("h1", {"script": {"provider": "claude"}}, project_root=root, generate=fake_gen)
        check(res["status"] == "need_choice", f"need_choice 반환 ({res['status']})")
        check(called["n"] == 0, "generate_script 미호출(토큰 0)")
        check(not plan._plan_path(root, "h1").exists(), "대본 파일 미생성")


def test_prepare_stub_without_key():
    print("[T2] prepare_directions — 키 없음 → 스텁(4안 필요)")
    with no_keys(), tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_product(root, "h2")
        res = plan.prepare_directions("h2", {"script": {"provider": "claude"}}, project_root=root)
        check(res["status"] == "stub", f"stub 반환 ({res['status']})")
        check("note" in res and res["note"], "사유(note) 포함")
        # 스텁 파일이 저장됐는지(관리자 ② 메뉴가 사유+4안을 띄우려면 필요)
        mech = root / "data" / "mechanism" / "h2.json"
        check(mech.exists(), "스텁 mechanism 파일 저장")


def test_prepare_confirmed():
    print("[T3] prepare_directions — 이미 확정 → confirmed(text)")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_product(root, "h3")
        _seed_mechanism(root, "h3", chosen=0)
        res = plan.prepare_directions("h3", {"script": {"provider": "claude"}}, project_root=root)
        check(res["status"] == "confirmed", f"confirmed 반환 ({res['status']})")
        check("반도체 냉각판" in res.get("text", ""), "1안 확정 텍스트 반환")


def test_generate_with_direction():
    print("[T4] 확정 방향 → 대본 생성(주입 확인·저장·로드)")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _seed_product(root, "h4")
        _seed_mechanism(root, "h4", chosen=1)   # 2안(지속) 선택
        seen = {}

        def fake_gen(product, settings):
            seen["mech"] = product.get("차별점_작동방식")
            seen["row_hash"] = product.get("_row_hash")
            seen["name"] = product.get("name")
            return {"title": "이 선풍기 6시간 갔다", "headline": "충전 한 번의 반전",
                    "description": "설명", "hashtags": ["#선풍기", "#여름", "#꿀템"],
                    "lines": [{"text": "덥다", "subs": ["덥다"], "stage": 1, "is_hook": True}]}

        res = plan.generate_plan("h4", {"script": {"provider": "claude"}}, project_root=root, generate=fake_gen)
        check(res["status"] == "ok", f"ok 반환 ({res['status']})")
        check("6시간" in (seen.get("mech") or ""), "2안 확정 텍스트가 차별점_작동방식로 주입됨")
        check(seen.get("row_hash") == "h4", "_row_hash 주입됨")
        check(seen.get("name") == "휴대용 미니 선풍기", "쿠팡 등록명이 product.name")
        loaded = plan.load_plan("h4", project_root=root)
        check(loaded and loaded.get("title") == "이 선풍기 6시간 갔다", "대본 저장·로드 왕복")
        check(res["lines"] == 1, "라인 수 리포트")


if __name__ == "__main__":
    for fn in [test_gate_blocks_without_direction, test_prepare_stub_without_key,
               test_prepare_confirmed, test_generate_with_direction]:
        fn()
    print()
    if _fails:
        print(f"실패 {len(_fails)}건: {_fails}")
        raise SystemExit(1)
    print("결과: 소싱 plan 게이트·주입·저장 정상 (3안 추출 LLM은 CI 실증).")
