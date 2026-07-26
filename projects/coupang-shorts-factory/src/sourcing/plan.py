"""소싱 ③b: 방향 3안 게이트 + 대본·제목·설명·해시태그 생성.

소싱 저장물(product/{hash}.json + promo/{hash}.json) → build_product_info → product dict →
  1) prepare_directions : 차별점 3안 추출(⭐ 절대 게이트) → data/mechanism/{hash}.json
  2) generate_plan      : 방향이 '확정'된 경우에만 대본 생성 → data/sources/plan/{hash}.json

기존 파이프라인(pipeline.py plan 모드)의 규약을 그대로 재사용한다:
  mechanism.prepare(extract, gate) → (확정 텍스트|None, need_choice) → product["차별점_작동방식"] 주입 →
  generate_script(product, settings)(내부에서 sanitize 완료). 4안(직접 의견) 가격 예외(_price_ok)도 동일.

mechanism 파일은 옛 파이프라인과 같은 data/mechanism/{hash}.json을 쓴다(포맷·관리자 방향선택 UI 재사용).
소싱 해시는 틱톡 검색어 기반이라 CSV row_hash와 충돌하지 않는다. 대본은 옛 data/plans/ 대신
data/sources/plan/ 에 저장해 옛 produce/cron이 소싱 대본을 건드리지 않게 격리한다.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.sourcing.models import PROJECT_ROOT
from src.sourcing.product_info import build_product_info


def _plan_path(project_root: Path, product_hash: str) -> Path:
    return Path(project_root) / "data" / "sources" / "plan" / f"{product_hash}.json"


def load_plan(product_hash: str, project_root: Path | None = None) -> dict | None:
    p = _plan_path(project_root or PROJECT_ROOT, product_hash)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[plan] 대본 파일 파싱 실패({e})")
        return None


def _product(product_hash: str, project_root: Path) -> dict:
    """소싱 저장물 → generate_script/mechanism용 product dict(+ _row_hash)."""
    product = build_product_info(product_hash, base_dir=Path(project_root) / "data" / "sources")
    product["_row_hash"] = product_hash   # mechanism/generate가 해시로 참조
    return product


def prepare_directions(product_hash: str, settings: dict,
                       project_root: Path | None = None) -> dict:
    """차별점 3안 추출(⭐ 절대 게이트) → data/mechanism/{hash}.json 저장.

    반환 {status, ...}:
      - "confirmed" : 운영자가 이미 방향을 확정함(text 포함) → 바로 대본 생성 가능
      - "ready"     : 3안을 뽑아 저장함(options) → 관리자에서 하나 고르거나 4안 입력 대기
      - "stub"      : 자료 부족·키 없음·추출 실패(note) → 4안(직접 의견) 확정 또는 자료 보강 후 재시도
    대본은 절대 만들지 않는다(생성은 generate_plan의 몫). LLM은 3안 추출에만 쓴다."""
    from src.product import mechanism
    root = project_root or PROJECT_ROOT
    product = _product(product_hash, root)
    mech_txt, need_choice = mechanism.prepare(product, settings, root, extract=True, gate=True)
    if not need_choice:
        return {"status": "confirmed", "text": mech_txt or ""}
    data = mechanism.load(root, product_hash) or {}
    if data.get("options"):
        return {"status": "ready", "options": data["options"]}
    return {"status": "stub", "note": data.get("note") or "차별점 3안을 만들지 못했습니다"}


def generate_plan(product_hash: str, settings: dict, project_root: Path | None = None,
                  *, generate=None) -> dict:
    """⭐ 절대 게이트 통과(방향 확정) 시에만 대본 생성 → data/sources/plan/{hash}.json.

    미확정이면 {"status":"need_choice"}로 즉시 중단(토큰 0). generate는 테스트 주입용
    (기본 generate_script — 내부에서 sanitize 완료). 4안 가격 예외(_price_ok)도 반영."""
    from src.product import mechanism
    root = project_root or PROJECT_ROOT
    product = _product(product_hash, root)

    mech_txt, need_choice = mechanism.prepare(product, settings, root, extract=True, gate=True)
    if need_choice:
        return {"status": "need_choice"}   # 방향 미확정 — 대본 생성 안 함(게이트)
    if mechanism.price_allowed(mechanism.load(root, product_hash)):
        product["_price_ok"] = True        # 4안에서 운영자가 가격 언급 → 가격 표현 허용
    if mech_txt:
        product["차별점_작동방식"] = mech_txt   # generate_script 상품 JSON에 노출

    if generate is None:
        from src.script.generate import generate_script
        generate = generate_script
    script = generate(product, settings)   # generate_script가 내부에서 sanitize_script 수행

    p = _plan_path(root, product_hash)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(script, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"status": "ok", "title": script.get("title", ""),
            "lines": len(script.get("lines") or []), "path": str(p)}


def _load_settings(root: Path) -> dict:
    import yaml
    return yaml.safe_load((Path(root) / "config" / "settings.yaml").read_text(encoding="utf-8")) or {}


def _main(argv=None) -> int:
    """워크플로 CLI. mode=directions(3안 추출·게이트) | script(방향 확정 시 대본 생성).
    결과 JSON을 'PLAN_RESULT:' 접두로 출력(잡 로그·관리자 폴링이 읽음). 항상 커밋은 워크플로가."""
    import argparse
    ap = argparse.ArgumentParser(description="소싱 ③b 방향 3안·대본 생성")
    ap.add_argument("--hash", required=True, help="상품 해시(product/{hash}.json)")
    ap.add_argument("--mode", choices=["directions", "script"], required=True)
    args = ap.parse_args(argv)
    settings = _load_settings(PROJECT_ROOT)
    if args.mode == "directions":
        res = prepare_directions(args.hash, settings)
    else:
        res = generate_plan(args.hash, settings)
    print("PLAN_RESULT:", json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_main(sys.argv[1:]))
