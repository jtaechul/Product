"""★구독 유도가 **실제 영상에 보여야** 한다(운영자 지시 "무조건 구독 늘려. 구걸도 해.").

@abyss_0cean 실측: 조회수 35,969 / 구독 24명 = **전환율 0.067%**(정상 쇼츠 0.5~2%의 1/10~1/30).
시청시간의 98.9%가 미구독자. 좋아요 0.44%.

☠️ 이 파일이 존재하는 진짜 이유(재발 방지):
  예전에는 구독 CTA를 `render_endcard()`(정지 PNG 함수)에 넣고 그 함수만 테스트했다.
  그런데 **릴스 파이프라인은 그 함수를 부르지 않는다** — 실제로 영상에 렌더되는 건
  `render_endcard_frames()`(→ `_styled_line`)다. 그래서 "엔드카드에 구독 유도를 넣었다"고
  보고했지만 **실제 영상에는 한 글자도 나오지 않았다**.
  → 이제 테스트는 **파이프라인이 실제로 부르는 함수**로 렌더해 픽셀로 확인한다.

구독 접점 3개(모두 화면에 보여야 한다):
  ① 엔드카드: 구독 이유 한 줄 + 'チャンネル登録' 알약 배지(맥동) · 홀드 3.2초
  ② 본문 자막: 마지막 CTA 절을 **다른 색·큰 글씨**로 강조
  ③ 본문 중간: 오른쪽 위 작은 구독 배지 1회(끝까지 안 보는 61%에게도 닿게)
"""
import shutil
import subprocess

import pytest

from src.core import hook_intro as HI


def _spec():
    return HI.SpeciesSpec(jp_name="クサウオ", sci_name="Liparidae",
                          feature_line="水圧に耐える、骨のない体",
                          depth_min=200, depth_max=3520,
                          hook_line1="a", hook_line2="b", hook_pop_words=["a"],
                          credit_line="映像: NOAA ・ Public Domain")


def test_config_has_subscribe_cta():
    cfg = HI.HookIntroConfig()
    assert cfg.end_cta_text.strip(), "구독 이유 문구가 비었습니다"
    assert "登録" in cfg.end_cta_sub, "구독 배지 문구가 없습니다"
    assert cfg.end_cta_size >= 36, "너무 작으면 모바일에서 안 보입니다"


def test_endcard_hold_is_long_enough_to_tap():
    """2초는 구독 버튼을 누를 시간이 안 된다 — 보고 손이 올라가는 데만 ~1초."""
    cfg = HI.HookIntroConfig()
    assert cfg.endcard_dur_s >= 3.0, f"엔드카드 홀드가 짧습니다: {cfg.endcard_dur_s}초"
    from src.core import pipeline as P
    assert P._ENDCARD_S == pytest.approx(cfg.endcard_dur_s), \
        "길이 예산 상수가 실제 엔드카드 길이와 다릅니다(총 길이 계산이 틀어집니다)"


def test_the_rendered_path_draws_the_cta():
    """★배선 계약: **파이프라인이 부르는 경로**(_styled_line)가 CTA를 그려야 한다.

    render_endcard()에만 넣고 끝내면 화면에는 안 나온다 — 실제로 그런 사고가 있었다.
    """
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "src" / "core"
         / "hook_intro.py").read_text(encoding="utf-8")
    i = s.index("def _styled_line(")
    body = s[i:s.index("\ndef ", i + 10)]
    assert "end_cta_text" in body, \
        "실제 렌더 경로(_styled_line)가 구독 문구를 그리지 않습니다"
    # 배지(알약)는 맥동시키려고 별도 레이어로 그린다
    assert "def _cta_pill_layer(" in s, "구독 배지 레이어가 없습니다"
    j = s.index("def render_endcard_frames(")
    frames_body = s[j:]
    assert "_cta_pill_layer" in frames_body, "프레임 렌더가 구독 배지를 합성하지 않습니다"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="렌더 환경 없음")
def test_cta_visible_and_inside_frame_in_real_frames(tmp_path):
    """★픽셀 검증(실제 렌더 경로): 배지가 보이고, 화면 밖으로 잘리지 않아야 한다.

    ⚠️엔드카드 프레임은 흔들림 여백 때문에 화면 전체가 Z≈1.105배 확대·중앙 크롭된다 →
      좌표를 그냥 두면 아래쪽이 잘린다(실제로 처음 넣었을 때 배지가 반쯤 잘렸다).
    """
    from PIL import Image
    cfg = HI.HookIntroConfig()
    bg = tmp_path / "bg.png"
    Image.new("RGB", (cfg.W, cfg.H), (12, 34, 54)).save(bg)
    frames, _ = HI.render_endcard_frames(str(bg), _spec(), str(tmp_path / "ec"), cfg)
    assert len(frames) == int(cfg.endcard_dur_s * cfg.FPS)
    im = Image.open(frames[len(frames) // 2]).convert("RGB")

    def badge_rows(y0, y1):
        """시안 배지(120,220,255)가 있는 행 수. 회색 크레딧을 세지 않도록 좁게 잡는다."""
        n = 0
        for y in range(y0, y1):
            row = [im.getpixel((x, y)) for x in range(cfg.W // 4, cfg.W * 3 // 4, 6)]
            if any(p[2] > 230 and p[1] > 195 and p[0] < 160 for p in row):
                n += 1
        return n

    assert badge_rows(1000, cfg.H - 30) > 20, "구독 배지가 보이지 않습니다"
    assert badge_rows(cfg.H - 8, cfg.H) == 0, "배지가 화면 아래로 잘렸습니다"
    # 등장 전(첫 프레임)에는 없어야 한다 — 쾅 등장 연출이 살아 있는지
    im0 = Image.open(frames[0]).convert("RGB")
    assert sum(1 for p in im0.crop((0, 1000, cfg.W, cfg.H)).getdata()
               if p[2] > 230 and p[1] > 195 and p[0] < 160) == 0, \
        "임팩트 전인데 배지가 이미 떠 있습니다"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="렌더 환경 없음")
def test_badge_pulses(tmp_path):
    """정지한 배지는 배경처럼 읽힌다 — 홀드 동안 크기가 실제로 변해야 한다."""
    from PIL import Image
    cfg = HI.HookIntroConfig()
    bg = tmp_path / "bg.png"
    Image.new("RGB", (cfg.W, cfg.H), (12, 34, 54)).save(bg)
    frames, _ = HI.render_endcard_frames(str(bg), _spec(), str(tmp_path / "ec"), cfg)

    def px(p):
        im = Image.open(p).convert("RGB")
        return sum(1 for q in im.crop((0, 1000, cfg.W, cfg.H)).getdata()
                   if q[2] > 230 and q[1] > 195 and q[0] < 160)

    sizes = [px(frames[i]) for i in range(len(frames) // 3, len(frames), 6)]
    assert sizes and max(sizes) > 0, "배지가 아예 없습니다"
    assert max(sizes) - min(sizes) > 500, f"배지가 맥동하지 않습니다: {sizes}"


# ── ② 자막 CTA 강조 · ③ 중간 배지 ─────────────────────────────
def _disp(n_body: int = 12):
    from src.core import pipeline as P
    chunks = P._prepend_open_loop([f"深海の底に、赤い影が漂います{i}。" for i in range(n_body)])
    chunks = P._append_cta(chunks)
    out, t = [], 0.0
    for c in chunks:
        out.append((c, t, t + 1.6))
        t += 1.6
    return out


def test_subtitle_cta_is_emphasised(tmp_path):
    """구독 절 자막이 본문과 똑같은 스타일이면 그냥 대사로 읽힌다."""
    from src.core import narration_sync as NS
    from pathlib import Path
    ass = Path(NS.build_synced_ass(_disp(), str(tmp_path / "t.ass"), hook_first=False))
    cta = [ln for ln in ass.read_text(encoding="utf-8").splitlines()
           if "Dialogue" in ln and "登録" in ln and "\\an9" not in ln]
    assert cta, "구독 유도 자막 줄이 없습니다"
    for ln in cta:
        assert "\\1c&H" in ln, f"구독 자막이 강조되지 않았습니다: {ln[:120]}"


def test_mid_video_subscribe_badge(tmp_path):
    """끝의 CTA만으로는 **끝까지 본 39%**에게만 닿는다 — 중간에 한 번 더 보여준다."""
    from src.core import narration_sync as NS
    from pathlib import Path
    disp = _disp()
    at = NS.pick_mid_badge_at(disp)
    assert at is not None and at > 0, "중간 배지 시각을 못 찾았습니다"
    assert at + 3.0 < float(disp[-1][2]) - 5.0, "끝 CTA와 너무 붙어 같은 말을 두 번 보게 됩니다"
    ass = Path(NS.build_synced_ass(disp, str(tmp_path / "t.ass"), hook_first=False))
    badge = [ln for ln in ass.read_text(encoding="utf-8").splitlines() if "\\an9" in ln]
    assert len(badge) == 1, f"중간 배지는 딱 한 번이어야 합니다: {len(badge)}회"
    assert "登録" in badge[0]


def test_mid_badge_skipped_when_body_is_short(tmp_path):
    """본문이 짧으면 배지와 끝 CTA가 겹친다 — 그럴 땐 아예 띄우지 않는다."""
    from src.core import narration_sync as NS
    short = [("短い本文です。", 0.0, 1.6), ("チャンネル登録で。", 1.6, 3.2)]
    assert NS.pick_mid_badge_at(short) is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="렌더 환경 없음")
def test_badge_and_cta_actually_burn_into_video(tmp_path):
    """★주장이 아니라 **구운 영상의 픽셀**로 확인 — 자막이 실제로 화면에 찍히는가."""
    from PIL import Image
    from src.core import narration_sync as NS
    disp = _disp()
    ass = NS.build_synced_ass(disp, str(tmp_path / "t.ass"), hook_first=False)
    src, out = tmp_path / "v.mp4", tmp_path / "subbed.mp4"
    dur = float(disp[-1][2]) + 1
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"color=c=0x0a2a40:s=720x1280:d={dur}:r=24",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"ass={ass}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(out)], check=True)
    BG = (10, 42, 64)

    def ink(t, box):
        p = str(tmp_path / f"f{t}.png")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(out),
                        "-frames:v", "1", p], check=True)
        im = Image.open(p).convert("RGB").crop(box)
        return sum(1 for q in im.getdata()
                   if abs(q[0] - BG[0]) + abs(q[1] - BG[1]) + abs(q[2] - BG[2]) > 90)

    at = NS.pick_mid_badge_at(disp)
    top = (0, 80, 720, 260)
    assert ink(at + 1.0, top) > 500, "중간 구독 배지가 화면에 안 찍혔습니다"
    assert ink(at + 6.0, top) == 0, "중간 배지가 계속 떠 있습니다(거슬림 · 1회여야 함)"
    assert ink(float(disp[-1][2]) - 0.8, (0, 900, 720, 1280)) > 500, \
        "끝 구독 자막이 화면에 안 찍혔습니다"


def test_narration_cta_still_exists_and_says_why():
    """음성 CTA 유지 + '무엇을 받는지'가 있어야 구독 이유가 된다."""
    from src.core import pipeline as P
    joined = "".join(P._CTA_BODY_JP)
    assert "登録" in joined, "나레이션 구독 유도가 사라졌습니다"
    assert "1話" in joined or "図鑑" in joined, "구독하면 무엇을 받는지가 없습니다"


def test_open_loop_creates_curiosity():
    """★호기심 갭: 끝까지 봐야 정체를 안다 → 완주율이 올라야 구독 화면에 닿는다."""
    from src.core import pipeline as P
    got = P._prepend_open_loop(["深海の底に、", "赤い影。"])
    assert got[0] == P._OPEN_LOOP_JP and "最後" in got[0]
    assert P._prepend_open_loop(got) == got, "두 번 붙습니다"
    # 실제로 마지막에 정체가 공개되므로 거짓 예고가 아니다(엔드카드에 종명·학명이 있다)
    cfg = HI.HookIntroConfig()
    assert cfg.end_title_size > 0
