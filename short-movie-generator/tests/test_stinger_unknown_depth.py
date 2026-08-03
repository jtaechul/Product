"""★수심을 몰라도 스팅어를 버리지 않는다 — 위치는 보여주고 수심만 '?'(운영자 확정).

운영자 지시: "수심을 모르면 **위치를 표현해주고**, 수심은 내려오다가 **물음표**를 띄우면 되잖아.
  수심 정보가 없다고 해서 그냥 다 안 만드는 게 아니고. 수심 내려가는 애니메이션이 나오다가
  물음표를 표현해 주면 되잖아."

예전 동작: `depth is None`이면 `build_stinger`가 **None을 반환해 지도(위치)까지 통째로 생략**했다
  → 보여줄 수 있는 정보(서식해역)까지 버렸다.
지금: 위치(지도·해역 락온)는 그대로, 수심 판독값만 `?` + `記録なし`.
  ★연출용 기준 깊이(2000m)는 **화면에 수치로 나오지 않는다** — 눈금의 숫자도 함께 숨겨
    "2,000 m"가 새어나와 없는 수심을 주장하는 일이 없게 한다(날조 금지).
"""
import shutil

import pytest

from src.core import reels_stinger as RS
from src.core.longform import motion


class _Info:
    def __init__(self, depth):
        self.depth_range_m = depth
        self.scientific_name = "Testus profundus"
        self.common_name_en = "test creature"
        self.common_name_ko = "테스트"
        self.habitat = ""
        self.distribution = ""
        self.fun_facts = []


def test_spec_has_unknown_depth_flag():
    assert "depth_unknown" in motion.MotionSpec.__dataclass_fields__
    assert motion.MotionSpec().depth_unknown is False, "기본은 '수심 있음'이어야 합니다"


def test_stinger_no_longer_bails_out_without_depth():
    """★핵심 계약: 수심이 없다고 스팅어를 생략하면 안 된다(소스 계약으로 고정)."""
    from pathlib import Path
    s = (Path(__file__).resolve().parents[1] / "src" / "core"
         / "reels_stinger.py").read_text(encoding="utf-8")
    i = s.index("depth = _depth_max(")
    seg = s[i:i + 700]
    assert "return None" not in seg, "수심이 없다고 스팅어를 통째로 생략하고 있습니다"
    assert "depth_unknown" in seg, "수심 미상 표시를 넘기지 않습니다"
    assert "depth_unknown=depth_unknown" in s, "렌더러에 미상 여부가 전달되지 않습니다"


@pytest.mark.parametrize("depth", ["", None, "미상", "unknown"])
def test_unknown_depth_is_detected(depth):
    assert RS._depth_max(depth or "") is None


def test_known_depth_still_parsed():
    assert RS._depth_max("200-2000") == 2000


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg 없음")
def test_unknown_depth_frames_show_question_mark_not_a_number(tmp_path):
    """★실제 렌더 검증: 마지막 프레임에 '?'가 보이고, 눈금 숫자는 사라져야 한다.

    (숫자 노출 여부는 픽셀로 직접 확인 — 오른쪽 눈금 영역의 밝은 글자 픽셀 수를 센다.)"""
    from PIL import Image

    def render(unknown):
        out = tmp_path / ("unk" if unknown else "known")
        out.mkdir(parents=True, exist_ok=True)
        spec = motion.MotionSpec(target_depth_m=2000, region_label_jp="北大西洋",
                                 region_label_en="N. ATLANTIC",
                                 zones=[(100, "有光層"), (600, "薄明層")],
                                 depth_unknown=unknown)
        cfg = motion.MotionConfig(W=720, H=1280, FPS=24, t_map=0.9, t_flash=0.15,
                                  t_desc=1.0, t_hold=0.25, map_box=(70, 300, 650, 820))
        motion.render_locate_descent(str(out), spec, cfg)
        return Image.open(sorted(out.glob("m_*.png"))[-1]).convert("RGB")

    def ruler_text_px(im):
        """오른쪽 눈금 라벨 영역(축 왼쪽)에서 글자 픽셀 수.

        눈금 숫자는 흐린 회색(DIM)이라 밝기 임계는 낮게 잡는다 — 실측: 숫자 있음 191px / 없음 0px."""
        crop = im.crop((430, 60, 575, 1220))
        return sum(1 for q in crop.getdata() if sum(q) > 200)

    unk, known = render(True), render(False)
    assert ruler_text_px(known) > 0, "정상 상태에선 눈금 숫자가 보여야 합니다(대조군)"
    assert ruler_text_px(unk) == 0, "수심 미상인데 눈금에 숫자가 노출됩니다(없는 수심 주장)"
    # 판독값 영역(왼쪽)에 '?'가 그려져 밝은 픽셀이 존재해야 한다
    q = unk.crop((60, 300, 220, 420))
    assert sum(1 for p in q.getdata() if sum(p) > 260) > 200, "'?' 판독값이 보이지 않습니다"
