"""E2E 파이프라인 테스트 (panzoom) + 실패 경로(안전 중단) 검증.

느린 테스트(FFmpeg 3컷 인코딩)라 -m e2e 로 분리 실행 가능.
"""
import json

import pytest

from src.core.contracts import PipelineError


pytestmark = pytest.mark.e2e


def test_full_pipeline_panzoom(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from src.core import pipeline

    result = pipeline.run("deep_sea", "dumbo octopus", "panzoom", base_dir=str(tmp_path))

    # 수용 기준 (spec 11-1) 자동 검증
    assert result.qc_passed, result.qc_report
    assert (tmp_path / "output").exists()

    with open(result.sidecar_meta, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["license_ok"] is True
    assert meta["license"] in {"public-domain", "cc0", "cc-by", "kogl-type1"}
    assert meta["caption"]["hook_text"]
    assert len(meta["caption"]["hashtags"]) == 3
    assert meta["qc"]["audio_present_not_silent"]["passed"] is True
    assert meta["qc"]["resolution_9_16"]["detail"] == "720x1280"


def test_veo_without_key_becomes_pipeline_error(tmp_path, monkeypatch):
    """키 없이 Veo 선택 시 시각화 실패가 PipelineError로 통일돼 깔끔히 중단 (날것 트레이스 금지)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from src.core import pipeline

    with pytest.raises(PipelineError) as ei:
        pipeline.run("deep_sea", "dumbo octopus", "veo_img2video", base_dir=str(tmp_path))
    assert ei.value.stage == "visualization"


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
