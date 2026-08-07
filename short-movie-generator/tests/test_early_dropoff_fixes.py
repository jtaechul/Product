"""★초반 이탈 대책(운영자 확정 · 유튜브 스튜디오 실측 기반).

실측(28일): 조회 3.6만 → **유효 조회 1.4만(39%)** = 10명 중 6명이 초반에 스와이프.
시청자층: 45세 이상 71%(65+ 만 27%) · 남성 89% · 일본 95% · 시청시간의 98.9%가 미구독자.
가장 많이 본 회차의 훅: 「正体はヤドカリ、深海の鎧武者キングクラブ」(= **정체 공개형**).

원인(코드 확인): 오프닝 4.6초가 **정지 사진 1장**이고 그 뒤 지도 스팅어가 2.3초 →
**첫 6.9초 동안 화면이 움직이지 않았다**. 쇼츠에서 6.9초는 이미 늦다.

대책 4가지를 이 파일이 지킨다:
  ① 오프닝 배경이 실제로 **움직인다** + 오프닝을 2.8초로 단축
  ② 스팅어를 본문 **중간**(문장 경계)으로 이동 — 말이 잘리지 않게
  ③ 훅은 정체 공개형 — 추상 비유형 훅은 채택하지 않는다
  ④ 45세 이상 대응 — 글자 하한 상향 · 컷 수 축소
"""
import subprocess
import tempfile
from pathlib import Path

import pytest
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]


def _px_diff(a: str, b: str) -> float:
    d = ImageChops.difference(Image.open(a).convert("L"), Image.open(b).convert("L"))
    return sum(i * c for i, c in enumerate(d.histogram())) / (720 * 1280)


def _moving_source(wd: Path) -> str:
    """좌→우로 움직이는 밝은 원(=피사체) 테스트 영상."""
    src = wd / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=0x08243a:s=1280x720:d=12:r=24",
         "-f", "lavfi", "-i", "color=c=0xd0e8ff:s=140x140:d=12:r=24",
         "-filter_complex",
         "[1:v]format=yuva420p[c];[0:v][c]overlay=x='60+120*t':y='260+60*sin(3*t)'",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    return str(src)


# ── ① 오프닝이 실제로 움직이는가 ──────────────────────────
def test_opening_background_actually_moves():
    """★핵심: '움직이게 했다'는 주장 대신 **화면이 실제로 변하는지** 픽셀로 잰다.

    비교 대상은 기존 방식(정지 사진 1장)이다. 텍스트 팝인 애니가 끝난 뒤 구간(뒤 40%)만
    비교하므로, 차이가 나면 그건 **배경이 움직였다**는 뜻이다.
    """
    from src.core import hook_intro as HI
    from src.core import hook_intro_stage as HS
    wd = Path(tempfile.mkdtemp())
    src = _moving_source(wd)
    cfg = HI.HookIntroConfig()
    spec = HI.SpeciesSpec(jp_name="テスト", sci_name="Testus testus", depth_min=200, depth_max=2000,
                          hook_line1="カニに見えて、", hook_line2="カニじゃない。",
                          hook_pop_words=["カニに見えて、", "カニじゃない。"],
                          feature_line="泳ぐ・光る・透ける、深海のナマコ")
    n = int(cfg.opening_seg_s * cfg.FPS)
    seq = HS.opening_bg_frames(src, 2.0, str(wd / "obg"), cfg.W, cfg.H, n=n + 2, fps=cfg.FPS)
    assert len(seq) >= n, f"오프닝 배경 프레임이 부족합니다: {len(seq)}/{n}"

    def tail_spread(paths):
        tail = paths[int(len(paths) * 0.6):]
        return _px_diff(tail[0], tail[-1])

    moving = tail_spread(HI.render_opening_frames(seq, {"a": 0.0, "b": 0.6}, spec,
                                                  str(wd / "of_mov"), cfg))
    still = tail_spread(HI.render_opening_frames(seq[0], {"a": 0.0, "b": 0.6}, spec,
                                                 str(wd / "of_still"), cfg))
    assert still < 1.0, f"정지 배경인데 화면이 변합니다(비교 기준이 깨짐): {still}"
    assert moving > still * 10, f"오프닝이 사실상 정지입니다(움직임 {moving} vs 정지 {still})"


def test_opening_is_shorter():
    """오프닝 4.6 → 2.8초. 길이 예산 상수도 같이 움직여야 총 길이 계산이 맞는다."""
    from src.core import hook_intro as HI
    from src.core import pipeline as P
    assert HI.HookIntroConfig().opening_seg_s == pytest.approx(2.8)
    assert P._OPENING_S == pytest.approx(2.8)
    assert P._FIXED_OVERHEAD_S == pytest.approx(2.8 + 2.3 + 2.0)


def test_still_fallback_still_works():
    """★배경을 못 뽑아도 제작이 멈추면 안 된다 — 정지 1장 경로가 그대로 살아 있어야 한다."""
    from src.core import hook_intro as HI
    from src.core import hook_intro_stage as HS
    wd = Path(tempfile.mkdtemp())
    assert HS.opening_bg_frames(str(wd / "없는파일.mp4"), 1.0, str(wd / "o"), 720, 1280,
                                n=10, fps=24) == [], "없는 소스인데 빈 리스트를 안 돌려줍니다"
    cfg = HI.HookIntroConfig()
    spec = HI.SpeciesSpec(jp_name="テスト", sci_name="Testus testus", depth_min=10, depth_max=90,
                          hook_line1="ひとつ、", hook_line2="骨もない。",
                          hook_pop_words=["ひとつ、", "骨もない。"], feature_line="a・b・c、海の生き物")
    src = _moving_source(wd)
    one = HS.opening_bg_frames(src, 1.0, str(wd / "one"), cfg.W, cfg.H, n=2, fps=cfg.FPS)[0]
    got = HI.render_opening_frames(one, {"a": 0.0}, spec, str(wd / "of"), cfg)
    assert len(got) == int(cfg.opening_seg_s * cfg.FPS)


# ── ② 스팅어를 본문 중간으로 ─────────────────────────────
def test_stinger_goes_into_the_middle_not_the_front():
    """★실제로 끼워 넣어 확인: 삽입 지점 전후는 본문, 그 사이는 스팅어여야 한다."""
    from src.core import reels_stinger as R
    wd = Path(tempfile.mkdtemp())
    body, st, out = wd / "body.mp4", wd / "st.mp4", wd / "out.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=20:r=24",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(body)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=green:s=720x1280:d=2.3:r=24",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "2.3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(st)], check=True)
    assert R.insert_into_body(str(st), str(body), str(out), at_s=6.5, stinger_dur=2.3,
                              work_dir=str(wd / "sfx"))

    def rgb_at(t):
        p = str(wd / f"f{t}.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(out),
                        "-frames:v", "1", p], check=True)
        return Image.open(p).convert("RGB").getpixel((360, 640))

    def dur(p):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
        return float(r.stdout.strip())

    assert dur(str(out)) == pytest.approx(22.3, abs=0.2), "삽입 후 길이가 안 맞습니다"
    assert rgb_at(5.0)[2] > 200, "삽입 전 구간이 본문이 아닙니다"
    assert rgb_at(7.5)[1] > 80 and rgb_at(7.5)[2] < 80, "삽입 지점이 스팅어가 아닙니다"
    assert rgb_at(12.0)[2] > 200, "삽입 후 구간이 본문으로 안 돌아왔습니다"


def test_insert_point_is_a_sentence_boundary():
    """★문장 한가운데를 끊으면 나레이션이 잘린다 — 경계에서만 자른다."""
    from src.core import reels_stinger as R
    disp = [("a", 0.0, 2.1), ("b", 2.1, 5.0), ("c", 5.0, 7.2), ("d", 7.2, 12.0)]
    at = R.pick_insert_point(disp)
    assert at in {row[2] for row in disp}, f"경계가 아닌 지점을 골랐습니다: {at}"
    assert at == pytest.approx(7.2), f"목표 6.5초에 가장 가까운 경계가 아닙니다: {at}"
    # 허용 구간 밖뿐이면 포기해야 한다(억지로 끼워 넣지 않는다)
    assert R.pick_insert_point([("a", 0.0, 1.2), ("b", 1.2, 2.4)]) is None


def test_pipeline_inserts_instead_of_prepending():
    """배선 계약: 파이프라인이 앞에 붙이지 말고 **중간에 끼워야** 한다."""
    t = (ROOT / "src" / "core" / "pipeline.py").read_text(encoding="utf-8")
    assert "insert_into_body" in t, "스팅어를 본문 중간에 끼우지 않습니다"
    assert "pick_insert_point" in t, "삽입 지점을 문장 경계에서 고르지 않습니다"
    assert "prepend_to_body" not in t, "아직도 스팅어를 맨 앞에 붙이고 있습니다"


# ── ③ 훅: 정체 공개형 ────────────────────────────────────
def test_abstract_metaphor_hooks_are_rejected():
    """★실측 실패 문구가 다시 통과하면 안 된다 — 정보량 0인 시적 비유는 초반에 스와이프된다."""
    from src.categories.deep_sea.hook import is_abstract_hook as A
    for bad in ("闇、潜む地獄。牙持つ、巨影。", "深海の、静かな影。", "底なしの、闇。"):
        assert A(bad), f"추상 비유형인데 통과했습니다: {bad}"


def test_concrete_reveal_hooks_pass():
    """정체 공개형·구체 사실형은 통과해야 한다(게이트가 전부 막으면 제작이 죽는다)."""
    from src.categories.deep_sea.hook import is_abstract_hook as A
    for good in ("カニに見えて、カニじゃない。", "正体は、ヤドカリ。", "四年半、ただ、卵を守る。",
                 "頭も、目も、骨もない。", "水深8000mの、住人。"):
        assert not A(good), f"정상 훅이 막혔습니다: {good}"


def test_llm_hook_output_is_screened():
    """LLM이 추상형을 내놓으면 채택하지 않는다(재생성 유도)."""
    from src.categories.deep_sea import hook as HK
    bad = ('{"jp_name":"テスト","hook_line1":"闇、潜む地獄。","hook_line2":"牙持つ、巨影。",'
           '"pop_words":["闇、潜む地獄。","牙持つ、巨影。"],"feature_line":"a・b・c、深海の魚"}')
    assert HK._parse_json(bad) is None, "추상형 훅이 그대로 채택됩니다"
    good = bad.replace("闇、潜む地獄。", "カニに見えて、").replace("牙持つ、巨影。", "カニじゃない。")
    assert HK._parse_json(good) is not None, "정상 훅까지 거절합니다"


def test_prompt_teaches_the_reveal_pattern():
    """프롬프트가 '정체 공개형'을 실제로 지시해야 한다(코드만 막고 지시가 없으면 계속 재시도만 난다)."""
    from src.categories.deep_sea import hook as HK
    assert "正体" in HK._PROMPT and "に見えて" in HK._PROMPT
    assert "39%" in HK._PROMPT, "왜 바꾸는지(실측 근거)가 프롬프트에 없습니다"


# ── ④ 45세 이상 시청자 대응 ──────────────────────────────
def test_hook_font_floor_raised_for_older_viewers():
    """시청자의 71%가 45세 이상 — 작은 글자는 읽히지 않는다."""
    from src.core import hook_intro as HI
    assert HI.HookIntroConfig().title_min_size >= 68


def test_cuts_reduced():
    """빠른 구도 전환은 이 연령대에서 이탈이 크다 — 기본 컷 수를 줄인다."""
    from src.core import reframe
    assert reframe._DEFAULT_MAX_CUTS == 3
    assert reframe._MIN_CUTS <= reframe._DEFAULT_MAX_CUTS
