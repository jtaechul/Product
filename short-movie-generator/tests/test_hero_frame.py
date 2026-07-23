"""오프닝 훅 배경 프레임 선택 회귀 테스트 (실사고: ソコダラ 등 빈 바다만 나옴).

핵심 결함:
- 릴스 `_score_best_frame` 폴백이 struct(매크로 표준편차)를 그대로 더해 '질감 많은 빈 모래 바닥'이
  어두운 물고기보다 높은 점수 → 빈 바다 선택.
- 나레이트 `_pick_hero_frame`은 Gemini를 아예 안 쓰고 밝기 stddev만 봐서 늘 빈 모래를 골랐다.

수정:
- 두 경로를 Gemini 우선 선택기(`_score_best_frame`)로 통일 + 촘촘한 샘플 + 움직임(fg) 주신호 폴백.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

from src.core import hook_intro_stage as his


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _make_sand_creature_video(out: str, work: Path, fps: int = 6, secs: int = 10) -> None:
    """대부분 '질감 많은 밝은 빈 모래'(정적) + 4~6초에만 '어두운 움직이는 피사체'가 나오는 합성 영상.
    어두운 피사체는 subject_score≈0(색·밝기 saliency 없음) → 오직 움직임(fg)으로만 구분되는 최악 케이스."""
    from PIL import Image, ImageDraw
    W, H = 320, 180
    sand = Image.new("L", (W, H))
    sp = sand.load()
    for y in range(H):                     # 결정론적 밝은 질감(높은 국소 분산) = 빈 모래
        for x in range(W):
            sp[x, y] = ((x * 7 + y * 13) % 96) + 130
    sand = sand.convert("RGB")
    fdir = work / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    nf = fps * secs
    for i in range(nf):
        im = sand.copy()
        t = i / fps
        if 4.0 <= t <= 6.0:                # 피사체 등장 구간(전체의 20%)
            d = ImageDraw.Draw(im)
            cx = int(W * (0.35 + 0.30 * (t - 4.0) / 2.0))   # 움직임(위치 변화)
            d.ellipse([cx - 26, H // 2 - 18, cx + 26, H // 2 + 18], fill=(44, 41, 50))  # 어두운 피사체
        im.save(fdir / f"fr_{i:03d}.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                    "-i", str(fdir / "fr_%03d.png"), "-pix_fmt", "yuv420p",
                    "-c:v", "libx264", "-crf", "18", out], check=True)


def _idx_to_time(idx: int, n: int, dur: float) -> float:
    return dur * (0.05 + 0.90 * idx / (n - 1))


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 없음")
def test_fallback_picks_moving_dark_subject_not_empty_sand(tmp_path, monkeypatch):
    """비전(Gemini) 미가동 폴백에서도, 어두운 움직이는 피사체 프레임을 골라야 한다(빈 모래 아님).
    (예전 struct 가중 폴백은 질감 많은 빈 모래를 골랐다 — 이 테스트가 그 재발을 막는다.)"""
    # Gemini 강제 미가동 → 폴백 경로 검증
    from src.core import vision_subject
    monkeypatch.setattr(vision_subject, "pick_subject_frame", lambda *a, **k: None)

    vid = str(tmp_path / "sand_creature.mp4")
    _make_sand_creature_video(vid, tmp_path / "gen")
    wd = tmp_path / "wd"; wd.mkdir()
    best, score = his._score_best_frame(vid, wd, n_samples=20)
    assert best and Path(best).exists(), "후보 프레임 선택 실패"
    idx = int(Path(best).stem.split("_")[1])
    t = _idx_to_time(idx, 20, 10.0)
    assert 3.3 <= t <= 6.7, f"빈 모래(피사체 없는 t={t:.2f}s) 선택 — 움직이는 피사체 구간(4~6s)이어야 함"


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg 없음")
def test_gemini_choice_is_used_when_available(tmp_path, monkeypatch):
    """Gemini가 특정 인덱스를 고르면 그 프레임을 그대로 써야 한다(비전 우선)."""
    from src.core import vision_subject
    monkeypatch.setattr(vision_subject, "pick_subject_frame", lambda paths, hint="": 9)
    vid = str(tmp_path / "v.mp4")
    _make_sand_creature_video(vid, tmp_path / "gen")
    wd = tmp_path / "wd"; wd.mkdir()
    best, score = his._score_best_frame(vid, wd, n_samples=20)
    assert score == 999.0 and Path(best).stem == "ecs_9", f"Gemini 선택(index 9) 미반영: {best}"


def test_narrate_hero_delegates_to_vision_picker(tmp_path, monkeypatch):
    """나레이트 _pick_hero_frame은 릴스와 동일한 Gemini 선택기(_score_best_frame)를 써야 한다
    (예전엔 stddev만 써서 빈 바다를 골랐다 — 이 구멍을 막았는지 검증)."""
    from src.core import narrate_attached as na
    # 실제 프레임 파일 하나를 '비전이 고른 최선 프레임'으로 반환하도록 대체
    chosen = tmp_path / "chosen.png"
    from PIL import Image
    im = Image.new("L", (640, 360)); px = im.load()          # 질감 있는 이미지(파일 크기 >1000B 보장)
    for y in range(360):
        for x in range(640):
            px[x, y] = ((x * 5 + y * 11) % 128) + 80
    im.convert("RGB").save(chosen)
    assert chosen.stat().st_size > 1000
    called = {}

    def _fake_score(video, wd, logo_box=None, hint="", n_samples=20):
        called["hint"] = hint
        called["n"] = n_samples
        return str(chosen), 999.0

    monkeypatch.setattr("src.core.hook_intro_stage._score_best_frame", _fake_score)
    monkeypatch.setattr(na, "_probe_dur", lambda v: 120.0)   # 길이만 양수면 됨(실제 grab은 대체됨)
    out = na._pick_hero_frame("dummy.mp4", tmp_path / "hero", 1080, subject_hint="Macrouridae")
    assert out == str(chosen), "나레이트가 비전 선택기 결과를 쓰지 않음(stddev 폴백으로 샘)"
    assert called.get("hint") == "Macrouridae"        # 종 힌트 전달 확인
    assert called.get("n", 0) >= 20                   # 촘촘한 샘플 요청 확인
