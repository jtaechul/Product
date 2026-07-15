"""E2E 파이프라인 테스트 (panzoom) + 실패 경로(안전 중단) 검증.

느린 테스트(FFmpeg 3컷 인코딩)라 -m e2e 로 분리 실행 가능.
"""
import json

import pytest

from src.core.contracts import PipelineError


pytestmark = pytest.mark.e2e


def test_full_pipeline_panzoom(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from src.categories.deep_sea import catalog
    from src.core import pipeline
    # 도감 원장은 모듈 전역 경로 → 테스트가 저장소 파일을 오염시키지 않도록 tmp로 격리
    monkeypatch.setattr(catalog, "CATALOG", tmp_path / "catalog.json")

    result = pipeline.run("deep_sea", "dumbo octopus", "panzoom", base_dir=str(tmp_path))

    # 수용 기준 (spec 11-1) 자동 검증
    assert result.qc_passed, result.qc_report
    assert (tmp_path / "output").exists()

    with open(result.sidecar_meta, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["license_ok"] is True
    assert meta["license"] in {"public-domain", "cc0", "cc-by", "kogl-type1"}
    assert meta["caption"]["hook_text"]
    assert len(meta["caption"]["hashtags"]) >= 5  # 회귀 복구: 풍부한 해시태그 세트(3개 고정 폐기)
    assert meta["qc"]["audio_present_not_silent"]["passed"] is True
    assert meta["qc"]["resolution_9_16"]["detail"] == "720x1280"


def test_narrated_pipeline_panzoom(tmp_path, monkeypatch):
    """narrated_wildlife 파이프라인(panzoom·무키): 대본→합성→(나레이션 없음)→앰비언트→QC 통과."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from src.categories.deep_sea import catalog
    from src.core import pipeline
    monkeypatch.setattr(catalog, "CATALOG", tmp_path / "catalog.json")

    result = pipeline.run_narrated("deep_sea", "dumbo octopus", "panzoom", base_dir=str(tmp_path))
    assert result.qc_passed, result.qc_report
    with open(result.sidecar_meta, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["mode"] == "narrated_wildlife"
    assert 4 <= len(meta["script"]) <= 7           # 대본 문장 삽입
    assert meta["qc"]["audio_present_not_silent"]["passed"] is True
    assert meta["qc"]["resolution_9_16"]["detail"] == "720x1280"


@pytest.mark.parametrize("viz", ["veo_img2video", "veo_text2video"])
def test_veo_without_key_becomes_pipeline_error(tmp_path, monkeypatch, viz):
    """키 없이 Veo(img2video/text2video) 선택 시 시각화 실패가 PipelineError로 통일돼 깔끔히 중단."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from src.core import pipeline

    with pytest.raises(PipelineError) as ei:
        pipeline.run("deep_sea", "dumbo octopus", viz, base_dir=str(tmp_path))
    assert ei.value.stage == "visualization"


def test_qc_failure_blocks_publish(tmp_path, monkeypatch):
    """QC 실패(무음 등) 시 output/ 에 발행되지 않고 격리+중단 (하드 룰: 무음/부분 산출물 금지)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from src.core import audio, pipeline

    # 오디오 단계를 무음 통과로 오염 → QC의 audio_present_not_silent 실패 유도
    def silent(video_path, work_dir, duration_s, spec=None, **kwargs):
        import subprocess
        from pathlib import Path
        out = Path(work_dir) / "with_audio.mp4"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
             "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
             "-shortest", str(out)],
            check=True,
        )
        return str(out)

    monkeypatch.setattr(audio, "add_ambient", silent)
    with pytest.raises(PipelineError) as ei:
        pipeline.run("deep_sea", "dumbo octopus", "panzoom", base_dir=str(tmp_path))
    assert ei.value.stage == "output"
    # 발행물이 output/ 최상위에 없어야 함 (격리 폴더에만)
    published = list((tmp_path / "output").glob("*.mp4"))
    assert published == []


def test_pipeline_halts_when_all_assets_blocked(tmp_path, monkeypatch):
    """차단 라이선스만 소싱되면 시각화 이전에 안전 중단 (하드 룰)."""
    from src.categories.deep_sea.module import DeepSeaCategory
    from src.core import pipeline
    from src.core.contracts import RawAsset

    def only_blocked(self, info, raw_dir):
        from pathlib import Path
        p = Path(raw_dir) / "blocked.jpg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\xff\xd8fake")
        return [RawAsset(str(p), "X", "cc-by-nc", "c", "u")]

    monkeypatch.setattr(DeepSeaCategory, "source_assets", only_blocked)
    with pytest.raises(PipelineError) as ei:
        pipeline.run("deep_sea", "dumbo octopus", "panzoom", base_dir=str(tmp_path))
    assert ei.value.stage == "license_gate"
    # 차단 시 output 산출물이 없어야 함 (부분 산출물 미발행)
    outputs = list((tmp_path / "output").glob("*.mp4")) if (tmp_path / "output").exists() else []
    assert outputs == []
