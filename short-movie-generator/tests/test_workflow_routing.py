"""워크플로 라우팅 구조 검증 — 실사고 run #167 재발방지.

실사고: '찾은 영상으로 제작'에서 종·학명이 안 잡혀 나레이션형으로 **전환은 성공**했는데,
쇼츠 워크플로가 그대로 계속 달려 릴리스·레코드 스텝이 빈 결과로 터졌다
(`FileNotFoundError: ''`) → 운영자에겐 "제작 실패" 알림만 갔다. 실제 영상은 만들어지고 있었는데.

원인: 판별을 generate 잡 **안**의 스텝으로 넣고 파이프라인 스텝에만 `if` 를 걸었다.
      뒤따르는 15개 스텝에는 조건이 없어 전부 실행됐다(스텝마다 조건 다는 방식은 빠뜨리기 쉽다).
대책: 판별을 **별도 잡(route)** 으로 분리하고 generate 잡 전체를 `needs` + `if` 로 가둔다.

이 테스트는 그 구조가 유지되는지(=누가 되돌리지 않는지) 검사한다.
"""
import collections
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_WF = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "generate-short.yml"


class _NoDupLoader(yaml.SafeLoader):
    pass


def _no_dup(loader, node, deep=False):
    keys = [loader.construct_object(k, deep=deep) for k, _ in node.value]
    dup = [k for k, c in collections.Counter(keys).items() if c > 1]
    assert not dup, f"YAML 중복 키(앞의 값이 조용히 무시됨): {dup}"
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


_NoDupLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)


@pytest.fixture(scope="module")
def wf():
    if not _WF.exists():
        pytest.skip("워크플로 파일 없음")
    return yaml.load(_WF.read_text(encoding="utf-8"), Loader=_NoDupLoader)


def test_yaml_has_no_duplicate_keys(wf):
    """중복 키는 앞의 값이 조용히 사라진다(실제로 env 블록을 두 번 써 시크릿이 날아간 적 있음)."""
    assert wf["jobs"]


def test_route_job_exists_and_outputs_mode(wf):
    route = wf["jobs"].get("route")
    assert route, "판별 잡(route)이 없습니다 — 라우팅이 다시 스텝 안으로 들어갔는지 확인"
    assert "mode" in (route.get("outputs") or {}), "route 잡이 mode 출력을 내보내야 합니다"


def test_generate_job_is_gated_by_route(wf):
    """★핵심: 제작 잡 **전체**가 판별 결과로 가려져야 한다(스텝 단위 조건은 빠뜨리기 쉽다)."""
    gen = wf["jobs"]["generate"]
    needs = gen.get("needs")
    needs = [needs] if isinstance(needs, str) else (needs or [])
    assert "route" in needs, "generate 잡이 route 잡에 의존해야 합니다"
    cond = str(gen.get("if") or "")
    assert "needs.route.outputs.mode" in cond, f"generate 잡에 판별 조건이 없습니다: {cond!r}"
    assert "reels" in cond


def test_generate_steps_have_no_leftover_inline_gate(wf):
    """옛 방식(스텝 안 판별) 잔재가 남아 있으면 이중 게이트로 혼란해진다."""
    for st in wf["jobs"]["generate"]["steps"]:
        blob = str(st.get("if", "")) + str(st.get("name", ""))
        assert "idcheck" not in blob, f"옛 스텝 판별 잔재: {st.get('name')}"


def test_run_pipeline_step_unconditional(wf):
    """제작 잡에 들어왔다는 건 이미 '쇼츠로 간다'가 확정된 것 → 파이프라인은 무조건 돈다.
    (여기에 조건이 남아 있으면 또 '스킵됐는데 뒷단은 실행'되는 사고가 난다)"""
    steps = wf["jobs"]["generate"]["steps"]
    run_step = next((s for s in steps if s.get("name") == "Run pipeline"), None)
    assert run_step, "'Run pipeline' 스텝을 찾지 못했습니다"
    assert not run_step.get("if"), f"파이프라인 스텝에 조건이 남아 있습니다: {run_step.get('if')}"


def test_dispatch_needs_actions_write(wf):
    """다른 워크플로를 디스패치하려면 actions: write 권한이 필요하다."""
    perms = wf.get("permissions") or {}
    assert perms.get("actions") == "write", f"actions 권한 누락: {perms}"


def test_route_notifies_operator_it_is_not_a_failure(wf):
    """전환은 '실패'가 아니라는 걸 운영자에게 알려야 한다(예전엔 실패 알림만 가서 오해했다)."""
    blob = "\n".join(str(s.get("run", "")) for s in wf["jobs"]["route"]["steps"])
    assert "narrate-video.yml" in blob, "나레이션형 워크플로 디스패치가 없습니다"
    assert "실패 아님" in blob, "전환 알림에 '실패 아님' 안내가 없습니다"
