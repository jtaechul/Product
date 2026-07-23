"""★컷어웨이 다양화(운영자 요청: 짧은 영상 무한반복보다 여러 이미지 소스가 다채롭다).
반복이 심할수록 컷어웨이를 늘리되, 총 커버가 본문 45%를 넘지 않고 길이는 보존된다."""
import subprocess, tempfile, os, random
from PIL import Image
from src.core import footage


def _mkbody(d, dur):
    p = os.path.join(d, "body.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"nullsrc=s=720x1280:d={dur}", "-vf", "geq=random(1)*255:128:128",
                    "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", p], timeout=120)
    return p


def _photos(d, n):
    rnd = random.Random(3); out = []
    for i in range(n):
        p = os.path.join(d, f"ph{i}.jpg")
        im = Image.new("RGB", (900, 1200))
        im.putdata([(rnd.randint(80, 220), rnd.randint(60, 160), rnd.randint(40, 120)) for _ in range(900 * 1200)])
        im.save(p); out.append({"path": p, "credit": f"c{i}", "license": "cc0"})
    return out


def _dur(f):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", f], capture_output=True, text=True)
    return float((r.stdout or "0").strip() or 0)


def test_cutaways_inserted_and_length_preserved(tmp_path):
    d = str(tmp_path)
    body = _mkbody(d, 26)
    out = os.path.join(d, "out.mp4")
    res = footage.insert_photo_cutaways(body, _photos(d, 6), out, 26.0, key="t")
    assert res == out                                   # 여러 사진 → 삽입됨
    assert abs(_dur(out) - _dur(body)) < 0.3            # 길이 보존(자막·오디오 정합)


def test_too_short_body_skips(tmp_path):
    d = str(tmp_path)
    body = _mkbody(d, 8)
    out = os.path.join(d, "o2.mp4")
    # 본문 12초 미만 → 컷어웨이 삽입 안 함(원본 반환)
    assert footage.insert_photo_cutaways(body, _photos(d, 4), out, 8.0, key="t") == body


def test_nonliving_food_photo_rejected(tmp_path):
    """★#046 재발방지: 식품·건어물·표본 상태 사진은 컷어웨이로 쓰지 않는다(살아있는 개체만).
    ① 메타데이터(건어물·식품·시장·표본 등) ② 시각(흰 종이/스튜디오 배경)."""
    import random
    from PIL import Image, ImageDraw
    # 메타데이터: 식품·건어물·표본은 배제, 살아있는 개체는 통과
    assert footage._NONLIVING_RE.search("Dried Macrourus at fish market")
    assert footage._NONLIVING_RE.search("干物 標本")
    assert not footage._NONLIVING_RE.search("live grenadier swimming underwater NOAA")

    # 시각: 흰 종이 위 건어물(밝은 배경 55%↑) 배제 vs 어두운 물속 개체 통과
    food = tmp_path / "food.jpg"
    im = Image.new("RGB", (600, 900), (243, 242, 240)); d = ImageDraw.Draw(im)
    rnd = random.Random(3)
    for _ in range(900):
        x, y = rnd.randint(0, 599), rnd.randint(0, 899); v = rnd.randint(205, 236)
        d.line([(x, y), (x + rnd.randint(-6, 6), y + rnd.randint(-6, 6))], fill=(v, v, v - 3))
    d.polygon([(300, 150), (370, 165), (380, 700), (300, 760), (235, 700), (250, 165)], fill=(118, 68, 30))
    im.save(food)
    live = tmp_path / "live.jpg"
    b = Image.new("RGB", (600, 900), (14, 20, 30)); ImageDraw.Draw(b).ellipse([200, 380, 420, 520], fill=(72, 76, 82))
    b.save(live)
    assert footage._cutaway_image_ok(str(food)) is False        # 종이 배경 식품 → 배제
    assert footage._cutaway_image_ok(str(live)) is True         # 수중 개체 → 통과
    assert footage._cutaway_image_ok(str(live), credit="Dried specimen") is False   # 크레딧 단서로도 배제
