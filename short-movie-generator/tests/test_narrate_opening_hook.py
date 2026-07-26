"""나레이션형 쇼츠 — 오프닝 훅·자막 속도·원본 미리보기 회귀 테스트(운영자 확정 2차 수정).

실사고(첨부 영상 nv-30200041879):
  · 영상 0.2초부터 곧바로 본문 → **오프닝 훅이 없다**. 썸네일에만 훅 문구가 있었다.
    원인: "오프닝 훅 영상 카드 폐지"를 롱폼 기준으로 정하고 쇼츠에도 적용했다.
    운영자 확정: **숏폼은 오프닝 훅을 없애면 안 된다** + 방식은 도감형과 같은 애니메이션 훅.
  · 나레이션 12.4초에 자막 9개(1.4초마다 교체) → 원인 ①TTS +14% ②한 줄 7~14자.
    운영자 확정: 속도·글자수·문장수 **셋 다** 조정(도감형은 그대로 둔다).
  · 소싱 원본이 WebM(VP8)이라 아이폰에서 재생 불가 → 구간을 눈으로 정할 수 없었다.
    운영자 확정: 제작 때 **480p mp4**를 함께 만들어 올린다.
"""
import re
from pathlib import Path

import pytest

from src.core import content_store, narrate_attached as na


# ── 훅 문장 → 오프닝 애니메이션 어절 ─────────────────────────────────────────
@pytest.mark.parametrize("hook", [
    "深海に眠る、時を超えた記憶",
    "この光景を、ご存知ですか",
    "海の底に沈んだ巨大な船",
])
def test_hook_lines_split(hook):
    l1, l2, pops = na._hook_lines(hook)
    assert pops, "팝인 어절이 비면 오프닝이 만들어지지 않는다"
    assert 2 <= len(pops) <= 3
    # 어절을 이으면 원문 그대로여야 한다(글자 유실·중복 금지)
    assert "".join(pops) == re.sub(r"\s+", "", hook)
    assert l1 == pops[0] and l2 == "".join(pops[1:])


def test_hook_lines_empty_is_safe():
    assert na._hook_lines("") == ("", "", [])
    assert na._hook_lines("   ") == ("", "", [])


def test_hook_lines_short_hook_stays_one_piece():
    """아주 짧은 훅은 억지로 쪼개지 않는다(한 어절도 유효)."""
    _, _, pops = na._hook_lines("深海の記憶")
    assert pops == ["深海の記憶"]


def test_opening_hook_skipped_without_text():
    """훅 문구가 없으면 원본 본문을 그대로 돌려준다(발행 불정지)."""
    assert na._apply_opening_hook("body.mp4", "", Path("/tmp")) == "body.mp4"


# ── 자막 속도(운영자 확정: 나레이션형만) ─────────────────────────────────────
def test_shorts_tts_rate_is_not_fast():
    """+14%(빠름)로 되돌리면 자막이 다시 1.4초마다 넘어간다."""
    pct = int(na._SHORTS_TTS_RATE.replace("%", ""))
    assert pct <= 0, f"쇼츠 나레이션 속도가 빠릅니다: {na._SHORTS_TTS_RATE}"


def test_reels_tts_rate_unchanged():
    """★도감형(생물 쇼츠)은 운영자 확정에 따라 기존 속도를 유지한다(같이 건드리지 않는다)."""
    import inspect

    from src.core import narration_sync
    assert inspect.signature(narration_sync.synthesize).parameters["rate"].default == "+14%"


def test_shorts_script_prompt_asks_fewer_longer_lines(monkeypatch):
    """대본 프롬프트가 '5~7문장 × 12~20자'를 요구해야 자막이 3~4초 머문다."""
    seen = {}

    def _gen(prompt, max_tokens=0):
        seen["p"] = prompt
        return "海の底に、しずかな時間が流れます。\n深い場所へ、進んでいきます。\nそこに、影が見えます。"
    from src.core import llm
    monkeypatch.setattr(llm, "generate_text", _gen)
    na._jp_script("", "메모", "shorts")
    assert "5〜7" in seen["p"], "문장 수 지시가 줄지 않았습니다"
    assert "12〜20文字" in seen["p"], "한 줄 글자수 지시가 늘지 않았습니다"


def test_shorts_script_cap(monkeypatch):
    """LLM이 길게 뱉어도 쇼츠는 7문장으로 자른다."""
    from src.core import llm
    monkeypatch.setattr(llm, "generate_text",
                        lambda p, max_tokens=0: "\n".join(f"{i}行目の字幕です。" for i in range(20)))
    assert len(na._jp_script("", "메모", "shorts")) == 7


# ── 원본 미리보기 mp4(아이폰 재생용) ─────────────────────────────────────────
def test_preview_mp4_from_webm(tmp_path):
    """★핵심: WebM(VP8) 원본을 아이폰이 재생할 수 있는 H.264 mp4로 바꾼다.
    (소싱 캐시 17건 중 14건이 webm이라, 이게 없으면 구간 지정 자체가 불가능하다)"""
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg 없음")
    srcf = tmp_path / "src.webm"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "testsrc2=size=640x360:rate=15:duration=4",
                    "-c:v", "libvpx", "-b:v", "300k", str(srcf)], check=True, timeout=300)
    from src.core import source_preview
    out = source_preview.make_preview_mp4(str(srcf), str(tmp_path / "prev.mp4"))
    assert out and Path(out).exists()
    codec = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name", "-of", "csv=p=0", out],
                           capture_output=True, text=True).stdout.strip()
    assert codec == "h264", f"아이폰에서 재생 안 되는 코덱: {codec}"
    # ★타임라인 보존: 미리보기에서 읽은 초가 곧 컷 지정에 쓰는 초다(자르면 안 된다)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", out], capture_output=True, text=True).stdout.strip()
    assert abs(float(dur) - 4.0) < 0.5, f"원본과 길이가 다릅니다: {dur}"


def test_preview_missing_source_is_safe(tmp_path):
    from src.core import source_preview
    assert source_preview.make_preview_mp4(str(tmp_path / "none.webm"), str(tmp_path / "o.mp4")) == ""


def test_record_keeps_source_mp4_url(tmp_path):
    """레코드에 미리보기 URL이 남아야 대시보드가 그걸 재생한다."""
    (tmp_path / "content").mkdir()
    content_store.write_narrate_record(
        str(tmp_path), "nv-1", {"title_jp": "T", "hook_jp": "H"}, mode="shorts",
        video_url="https://x/v.mp4", source_url="https://x/s.webm",
        source_mp4_url="https://x/s_source.mp4")
    rec = content_store.load_record(str(tmp_path), "nv-1")
    assert rec["media"]["source_mp4_url"] == "https://x/s_source.mp4"


def test_record_without_preview_has_no_empty_key(tmp_path):
    """URL이 없으면 키 자체를 넣지 않는다(대시보드가 빈 문자열을 재생 시도하지 않게)."""
    (tmp_path / "content").mkdir()
    content_store.write_narrate_record(str(tmp_path), "nv-2", {"title_jp": "T"}, mode="shorts")
    rec = content_store.load_record(str(tmp_path), "nv-2")
    assert "source_mp4_url" not in rec["media"]
