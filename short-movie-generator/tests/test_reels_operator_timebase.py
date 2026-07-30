"""★도감형(reels)도 운영자가 고른 '초'를 그대로 지킨다(운영자 확정 · 절대 회귀 금지 · 실사고).

실사고(운영자 지적 · #050 바티노무스): "표지 지정한 거랑 영상 구획 지정한 게 지정한 대로 안 나오고
  이상한 데가 나오고, 구획도 선택하지 않은 것이 노출된다."

원인: 본문 재료를 만드는 단계(`pipeline.clean_source`)가 워터마크(크레딧 슬레이트) 회피를 위해
  원본을 **-ss(시작 이동) + -t(본문+10초만 남기기)** 로 다시 떴고, 그 뒤 리프레임·표지·엔드카드가
  모두 이 **잘린 파일**을 썼다. 운영자가 관리자 화면에서 고른 초는 **자르지 않은 원본** 기준이라
    ① 시작 이동만큼 전 구간이 통째로 밀리고
    ② 지정 초가 남긴 길이 밖이면 아예 사라져 자동 선택으로 대체됐다(= 고르지 않은 구획이 나온 이유).
  (앞서 `fetch_footage(skip_trim=)`로 한 번 막았지만 **여기서 두 번째로** 잘리고 있었다.)

실측 A/B(60초 소스 · 초당 색이 다른 영상으로 '몇 초를 보고 있는지'를 되짚음):
  예전 동작 → 5초가 원본 15.8초, 20초가 원본 30.8초, **45초는 아예 없음**(40초로 잘림)
  수정 후   → 5초=4.8초, 20초=20.0초, 45초=44.8초 (프레임 반올림 ±0.2초)
"""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _red_at(video: str, t: float, tmp: Path) -> float:
    """그 시각 화면의 빨강값 → '원본 몇 초의 장면인지'(빨강 = 초 × 4)."""
    from PIL import Image
    p = tmp / "probe.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video,
                    "-frames:v", "1", str(p)], check=True)
    return Image.open(p).convert("RGB").getpixel((640, 360))[0] / 4.0


@pytest.fixture(scope="module")
def marked_source(tmp_path_factory):
    """40초 소스 — 매 초 색이 달라 '지금 원본 몇 초를 보고 있는지'를 색으로 알 수 있다."""
    d = tmp_path_factory.mktemp("rl")
    src = d / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=1280x720:d=40:r=25",
                    "-vf", "geq=r='4*floor(T)':g='40':b='90'",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    return d, str(src)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_operator_edit_keeps_the_original_time_base(marked_source):
    """★핵심: 운영자 지정이 있으면 **자르지도 밀지도 않는다** — 고른 초가 그 초 그대로."""
    from src.core import pipeline as PL
    d, src = marked_source
    out = str(d / "clean_op.mp4")
    PL.clean_source(src, out, 8.0, op_edit=True)

    assert PL._probe_duration(out) > 35, "운영자 지정인데 원본이 잘렸습니다(지정 초가 사라집니다)"
    for t in (3.0, 12.0, 30.0):
        got = _red_at(out, t, d)
        assert abs(got - t) <= 0.5, f"{t}초를 골랐는데 원본 {got:.1f}초 장면이 나옵니다(시간축이 밀렸습니다)"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_without_operator_edit_the_old_trimming_still_applies(marked_source):
    """지정이 없을 때는 기존 동작(슬레이트 회피 + 길이 자르기)을 그대로 유지한다."""
    from src.core import pipeline as PL
    d, src = marked_source
    out = str(d / "clean_auto.mp4")
    PL.clean_source(src, out, 8.0, op_edit=False)
    assert PL._probe_duration(out) <= 19.0, "자동 경로는 본문+10초로 잘라 빠르게 처리해야 합니다"


def test_source_contract_no_seek_or_trim_when_operator_edited():
    """소스 계약: 운영자 지정 분기에 -ss(시작 이동)·-t(길이 자르기)가 들어가면 안 된다."""
    s = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    i = s.index("def clean_source(")
    body = s[i:s.index("\ndef _probe_wh(", i)]
    op = body[body.index("if op_edit:"):body.index("chain = WQ.delogo_chain(wm[\"boxes\"], 1280, 720)")]
    assert '"-ss"' not in op, "운영자 지정인데 시작을 옮기고 있습니다(전 구간이 밀립니다)"
    assert '"-t"' not in op, "운영자 지정인데 길이를 자르고 있습니다(지정 초가 사라집니다)"
    assert "scale=1280:720" not in op, "운영자 지정인데 강제로 16:9로 늘립니다(구획 비율이 어긋납니다)"


def test_pipeline_passes_operator_edit_flag():
    """배선 계약: cut_specs·cover가 있으면 그 사실이 clean_source까지 전달돼야 한다."""
    s = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert '_op_edit = bool(str(_man.get("cut_specs")' in s, "운영자 지정 판정이 없습니다"
    assert "clean_source(fv[\"path\"]" in s and "op_edit=_op_edit" in s, \
        "본문 재료 만들기에 운영자 지정 여부가 전달되지 않습니다"


def test_reels_record_keeps_applied_and_edit():
    """도감형도 '실제 반영 내역'과 '내 지정값'을 남긴다 — 화면에서 확인·복원할 근거."""
    pl = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    cs = (ROOT / "src" / "core" / "content_store.py").read_text(encoding="utf-8")
    assert "applied=_applied or None" in pl and "edit=_edit or None" in pl, \
        "도감형 제작이 반영 내역·지정값을 기록하지 않습니다"
    assert "applied: dict | None = None" in cs and 'rec["applied"] = applied' in cs, \
        "레코드 저장이 반영 내역을 받지 않습니다"
    assert 'rec["edit"] = edit' in cs, "레코드 저장이 운영자 지정값을 보존하지 않습니다"
    assert '"applied_cuts.json"' in pl or "applied_cuts.json" in pl, \
        "실제로 쓰인 컷 목록을 읽지 않습니다"
