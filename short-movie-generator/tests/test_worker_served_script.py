"""대시보드가 **실제로 서빙하는** 인라인 스크립트의 문법 검사(치명 사고 재발방지).

실사고: worker/index.mjs 는 `node --check` 를 통과했는데, 관리자 페이지가 "불러오는 중…"에서
멈추고 아무 반응이 없었다. 원인은 HTML이 **템플릿 리터럴**이라는 점을 놓친 것:

    소스에 `\\/`  → 템플릿 리터럴이 이스케이프를 소비 → 브라우저엔 `/`   (정규식 붕괴)
    소스에 `\\n`  → 마찬가지로 실제 줄바꿈이 됨                 (문자열 붕괴)

즉 **파일 문법은 멀쩡한데 서빙되는 스크립트만 깨진다.** `node --check worker/index.mjs` 로는
절대 잡히지 않으므로, 워커를 실제로 실행해 HTML을 받아 그 안의 <script>를 검사한다.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_WORKER = _ROOT / "worker" / "index.mjs"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _served_html() -> str:
    """워커를 실행해 홈 화면 HTML을 그대로 받아온다(배포본과 동일한 문자열)."""
    js = (
        'const mod = await import(process.argv[1]);\n'
        'const res = await mod.default.fetch(new Request("https://x/"), {}, {});\n'
        'process.stdout.write(await res.text());\n'
    )
    r = subprocess.run(["node", "--input-type=module", "-e", js, str(_WORKER)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"워커 실행 실패: {r.stderr[-500:]}"
    return r.stdout


def _inline_script(html: str) -> str:
    m = re.search(r"<script>([\s\S]*)</script>", html)
    assert m, "인라인 <script> 를 찾지 못했습니다"
    return m.group(1)


def test_served_inline_script_parses(tmp_path):
    """★핵심: 브라우저가 받는 스크립트가 문법적으로 유효해야 한다."""
    js = _inline_script(_served_html())
    f = tmp_path / "served.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (
        "서빙되는 스크립트에 문법 오류가 있습니다(대시보드가 통째로 멈춥니다).\n"
        "HTML이 템플릿 리터럴이라 정규식/문자열의 역슬래시는 소스에 **두 번** 써야 합니다.\n"
        + r.stderr[-800:])


def test_no_broken_regex_from_escaping():
    """이스케이프 사고의 지문: 정규식이 `//...//` 로 뭉개졌는지 직접 확인."""
    js = _inline_script(_served_html())
    assert "//transcoded//" not in js
    # 슬래시 이스케이프가 살아 있어야 한다(트랜스코드 URL 판별용 정규식)
    assert r"/\/transcoded\//" in js


def test_dialog_strings_have_no_raw_newline():
    """confirm/alert 문자열 안에 **실제 줄바꿈**이 들어가면 문자열이 끊긴다."""
    js = _inline_script(_served_html())
    for m in re.finditer(r'\b(?:confirm|alert)\(', js):
        seg = js[m.start():m.start() + 400]
        first_line = seg.split("\n", 1)[0]
        # 여는 괄호 줄에서 따옴표 개수가 홀수면 문자열이 줄바꿈으로 끊긴 것
        assert first_line.count('"') % 2 == 0, f"끊긴 문자열: {first_line[:120]}"
