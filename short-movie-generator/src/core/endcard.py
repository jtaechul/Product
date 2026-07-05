"""endcard — 시리즈 엔드카드 (도감 등록 컨셉 · 재방문·팔로우 유도).

전략: 'DEEP DIVE LOG' 데이터베이스에 표본을 등록하는 계기판 카드.
HUD 언어(네온 프레임·Orbitron·Pretendard) 그대로 이어받아 본편과 톤을 통일한다.
어둡게 끝나므로 콜드오픈(어둠 시작)과 루프 재생이 자연스럽게 이어진다.

렌더: HTML(htmlhud 폰트/프레임) → PNG(우선). 브라우저 불가 시 PIL 폴백(파이프라인 불정지).
"""
from __future__ import annotations

import html as _html
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from src.core import htmlhud
from src.core.contracts import CaptionData, PipelineError
from src.core.overlay import _font, _text_with_stroke, _wrap
from src.core.visualization.base import CLIP_FPS, CLIP_H, CLIP_W

ENDCARD_DURATION_S = 2.0


def _split_name(name: str) -> tuple[str, str]:
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", name or "")
    return (m.group(1).strip(), m.group(2).strip()) if m else ((name or "").strip(), "")


# ─────────────────────────────── HTML 렌더 (우선) ───────────────────────────────

def _endcard_html(caption: CaptionData, series_title: str, episode: int,
                  watermark: str) -> str:
    name_ko, name_en = _split_name(caption.reveal_name)
    fact = _html.escape(caption.reveal_fact or "")
    e = lambda s: _html.escape(s or "")  # noqa: E731
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{htmlhud.fonts_face_css()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:720px;height:1280px;overflow:hidden}}
.card{{position:relative;width:720px;height:1280px;
  background:radial-gradient(120% 90% at 50% 30%,#08202e 0%,#04101a 55%,#02080e 100%);
  font-family:'Rajdhani';overflow:hidden}}
.scan{{position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(120,220,240,.03) 0 1px,transparent 1px 3px)}}
.frame{{position:absolute;inset:22px;border:1px solid rgba(80,220,240,.22);border-radius:6px}}
.brk{{position:absolute;width:46px;height:46px;border:2px solid rgba(90,225,245,.9)}}
.tl{{top:18px;left:18px;border-right:0;border-bottom:0}}.tr{{top:18px;right:18px;border-left:0;border-bottom:0}}
.bl{{bottom:18px;left:18px;border-right:0;border-top:0}}.br{{bottom:18px;right:18px;border-left:0;border-top:0}}
.hdr{{position:absolute;top:150px;left:0;right:0;text-align:center;
  font-family:'Orbitron';font-weight:900;font-size:24px;letter-spacing:7px;color:#39E0F0;
  text-shadow:0 0 14px rgba(57,224,240,.6)}}
.series{{position:absolute;top:198px;left:0;right:0;text-align:center;
  font-family:'Rajdhani';font-weight:700;font-size:19px;letter-spacing:5px;color:#7FD8DC;text-transform:uppercase}}
.entry{{position:absolute;top:250px;left:0;right:0;text-align:center;
  font-family:'STM';font-size:16px;letter-spacing:2px;color:#5B7A86}}
.hr{{position:absolute;top:430px;left:120px;right:120px;height:1px;
  background:linear-gradient(90deg,transparent,rgba(80,220,240,.7),transparent)}}
.tag{{position:absolute;top:452px;left:0;right:0;text-align:center;
  font-family:'Orbitron';font-weight:900;font-size:16px;letter-spacing:5px;color:#FF8A3D}}
.name{{position:absolute;top:496px;left:40px;right:40px;text-align:center;
  font-family:'Pretendard';font-weight:900;font-size:66px;color:#FFD98A;line-height:1.05;
  text-shadow:0 0 20px rgba(255,200,120,.4);word-break:keep-all}}
.en{{position:absolute;top:600px;left:0;right:0;text-align:center;
  font-family:'Orbitron';font-weight:900;font-size:26px;letter-spacing:1px;color:#FFE9B8}}
.fact{{position:absolute;top:672px;left:70px;right:70px;text-align:center;
  font-family:'PretendardM';font-size:23px;color:#CFEAF3;line-height:1.4;word-break:keep-all;text-wrap:pretty}}
.stat{{position:absolute;top:800px;left:120px;right:120px;text-align:center;
  font-family:'STM';font-size:17px;letter-spacing:2px;color:#4E97A8;
  padding-top:20px;border-top:1px solid rgba(80,220,240,.16)}}
.next{{position:absolute;bottom:250px;left:0;right:0;text-align:center;
  font-family:'Orbitron';font-weight:900;font-size:16px;letter-spacing:4px;color:#FF8A3D}}
.cta{{position:absolute;bottom:196px;left:0;right:0;text-align:center;
  font-family:'Pretendard';font-weight:900;font-size:34px;color:#fff;
  text-shadow:0 0 18px rgba(80,200,240,.4)}}
.wm{{position:absolute;bottom:44px;right:34px;font-family:'Orbitron';font-weight:900;
  font-size:16px;letter-spacing:3px;color:rgba(220,235,240,.72)}}
.pin{{position:absolute;bottom:44px;left:34px;font-family:'STM';font-size:15px;
  letter-spacing:1px;color:#5B7A86}}
</style></head><body>
<div class="card">
  <div class="scan"></div><div class="frame"></div>
  <div class="brk tl"></div><div class="brk tr"></div><div class="brk bl"></div><div class="brk br"></div>
  <div class="hdr">◉ DATABASE ENTRY</div>
  <div class="series">{e(series_title)}</div>
  <div class="entry">SPECIMEN LOGGED · ENTRY No.{episode:03d}</div>
  <div class="hr"></div>
  <div class="tag">▶ SPECIES IDENTIFIED</div>
  <div class="name">{e(name_ko)}</div>
  <div class="en">{e(name_en)}</div>
  <div class="fact">{fact}</div>
  <div class="stat">ARCHIVED TO DEEP DIVE LOG · CLEARANCE: PUBLIC · REC COMPLETE</div>
  <div class="next">▶ NEXT DIVE</div>
  <div class="cta">팔로우하고 다음 심해 생물 만나기</div>
  <div class="pin">34.21°N 127.88°E · DEPTH LOG</div>
  <div class="wm">{e(watermark)}</div>
</div></body></html>"""


# ─────────────────────────────── PIL 폴백 ───────────────────────────────

def _render_png_pil(caption: CaptionData, series_title: str, episode: int,
                    watermark: str, out_path: str) -> str:
    img = Image.new("RGB", (CLIP_W, CLIP_H), (3, 8, 16))
    d = ImageDraw.Draw(img)
    for y in range(CLIP_H // 2, CLIP_H):
        t = (y - CLIP_H // 2) / (CLIP_H // 2)
        d.line([(0, y), (CLIP_W, y)], fill=(3 + int(4 * t), 8 + int(10 * t), 16 + int(14 * t)))
    cx = CLIP_W // 2
    _text_with_stroke(d, (cx, 250), series_title, _font(40), fill=(120, 210, 225), anchor="ma")
    _text_with_stroke(d, (cx, 310), f"SPECIMEN LOGGED · No.{episode:03d}", _font(26),
                      fill=(150, 180, 195), anchor="ma")
    name_ko, name_en = _split_name(caption.reveal_name)
    y = 520
    for line in _wrap(d, name_ko, _font(58), CLIP_W - 120):
        _text_with_stroke(d, (cx, y), line, _font(58), fill=(255, 230, 160), anchor="ma")
        y += 72
    if name_en:
        _text_with_stroke(d, (cx, y + 4), name_en, _font(34), fill=(255, 233, 184), anchor="ma")
        y += 60
    y += 20
    for line in _wrap(d, caption.reveal_fact or "", _font(36), CLIP_W - 150):
        _text_with_stroke(d, (cx, y), line, _font(36), fill=(207, 234, 243), anchor="ma")
        y += 50
    _text_with_stroke(d, (cx, CLIP_H - 260), "팔로우하고 다음 심해 생물 만나기", _font(36),
                      fill=(255, 255, 255), anchor="ma")
    _text_with_stroke(d, (CLIP_W - 40, 36), watermark, _font(24),
                      fill=(255, 255, 255, 210), anchor="ra")
    img.save(out_path)
    return out_path


def _render_png(caption: CaptionData, series_title: str, episode: int,
                watermark: str, work_dir: str) -> str:
    out = str(Path(work_dir) / "endcard.png")
    try:
        html = _endcard_html(caption, series_title, episode, watermark)
        return htmlhud.render_static(html, out, work_dir, name="endcard")
    except htmlhud.HudRenderError:
        return _render_png_pil(caption, series_title, episode, watermark, out)


def build_endcard_video(caption: CaptionData, series_title: str, episode: int,
                        watermark: str, work_dir: str) -> str:
    """엔드카드 PNG → 페이드인 무음 비디오 (규격 동일: 720x1280@25)."""
    png = _render_png(caption, series_title, episode, watermark, work_dir)
    out = Path(work_dir) / "endcard.mp4"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-loop", "1", "-i", png,
         "-t", str(ENDCARD_DURATION_S), "-r", str(CLIP_FPS),
         "-vf", f"scale={CLIP_W}:{CLIP_H},setsar=1,fade=t=in:st=0:d=0.4",
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-an", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"엔드카드 생성 실패: {proc.stderr[-400:]}")
    return str(out)


def append_endcard(main_video: str, endcard_video: str, work_dir: str) -> str:
    """본편(오버레이 완료) 뒤에 엔드카드를 이어붙임 (video-only concat 재인코딩)."""
    out = Path(work_dir) / "with_endcard.mp4"
    fc = (f"[0:v]scale={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1[v0];"
          f"[1:v]scale={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1[v1];"
          f"[v0][v1]concat=n=2:v=1:a=0[outv]")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", main_video, "-i", endcard_video,
         "-filter_complex", fc, "-map", "[outv]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"엔드카드 결합 실패: {proc.stderr[-400:]}")
    return str(out)


# ─────────────────── 실제 NOAA 사진 카드 (신뢰 앵커 + 출처 크레딧) ───────────────────
# AI 영상은 '연출(재현)'이므로, 마지막에 진짜 NOAA 사진을 보여 신뢰를 확보한다.
# ('실제 포착 이미지' + SOURCE: NOAA · PUBLIC DOMAIN). 출처 크레딧 하드룰도 시각적으로 충족.
REALCARD_DURATION_S = 2.0


def _orbitron(size: int):
    from PIL import ImageFont
    p = htmlhud._FONTS_DIR / "Orbitron.ttf"
    return ImageFont.truetype(str(p), size) if p.exists() else _font(size)


def _real_card_overlay_png(credit_string: str, work_dir: str) -> str:
    """실제 사진 카드용 투명 오버레이(프레임+코너+라벨+크레딧). 사진 위에 합성."""
    img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    WHITE, CY = (234, 240, 244, 235), (67, 200, 218, 255)
    # 얇은 프레임 + 코너 틱
    d.rectangle([18, 18, CLIP_W - 18, CLIP_H - 18], outline=(234, 240, 244, 70), width=1)
    for (x, y, dx, dy, c) in [(30, 30, 1, 1, CY), (CLIP_W - 30, 30, -1, 1, WHITE),
                              (30, CLIP_H - 30, 1, -1, WHITE), (CLIP_W - 30, CLIP_H - 30, -1, -1, CY)]:
        d.line([(x, y), (x + dx * 26, y)], fill=c, width=2)
        d.line([(x, y), (x, y + dy * 26)], fill=c, width=2)
    # 상단 태그
    _text_with_stroke(d, (40, 44), "ARCHIVE / ACTUAL SPECIMEN", _orbitron(20), fill=CY)
    # 하단 라벨 바
    d.rectangle([0, CLIP_H - 190, CLIP_W, CLIP_H - 70], fill=(4, 9, 14, 175))
    d.line([(0, CLIP_H - 190), (CLIP_W, CLIP_H - 190)], fill=CY, width=2)
    _text_with_stroke(d, (CLIP_W // 2, CLIP_H - 176), "실제 포착 이미지", _font(46), anchor="ma")
    _text_with_stroke(d, (CLIP_W // 2, CLIP_H - 118), f"SOURCE: {credit_string}",
                      _orbitron(20), fill=(200, 214, 222, 235), anchor="ma")
    out = str(Path(work_dir) / "realcard_overlay.png")
    img.save(out)
    return out


def build_real_photo_card(asset_path: str, credit_string: str, work_dir: str) -> str:
    """승인 NOAA 사진 → 9:16 '꽉 채움'(cover, 검은 여백 없음) + 줌인 + 스캔라인/플래시 리빌
    + 라벨/크레딧 오버레이 → 카드 영상.
    """
    work = Path(work_dir)
    if not Path(asset_path).exists():
        raise PipelineError("endcard", f"실제 사진 없음: {asset_path}")
    overlay = _real_card_overlay_png(credit_string, work_dir)
    out = work / "realcard.mp4"
    fps = CLIP_FPS
    frames = int(REALCARD_DURATION_S * fps)
    dur = REALCARD_DURATION_S
    # cover(가득) → 2배 업스케일로 줌 여유 → zoompan 줌인 → 스캔라인 1회 하강 → 흰 플래시 리빌
    bg = (f"[0:v]scale={CLIP_W}:{CLIP_H}:force_original_aspect_ratio=increase,"
          f"crop={CLIP_W}:{CLIP_H},scale={CLIP_W*2}:{CLIP_H*2},"
          f"zoompan=z='min(1.0+0.0011*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={CLIP_W}x{CLIP_H}:fps={fps},setsar=1,"
          f"drawbox=x=0:y='ih*(t/0.7)':w=iw:h=4:color=0x9BE8F2@0.8:t=fill:enable='lt(t,0.7)',"
          f"fade=t=in:st=0:d=0.28:color=white[bg]")
    fc = (f"{bg};[bg][1:v]overlay=0:0:format=auto,"
          f"fade=t=out:st={dur-0.3:.2f}:d=0.3[v]")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", str(dur),
         "-i", asset_path, "-i", overlay,
         "-filter_complex", fc, "-map", "[v]", "-t", str(dur),
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-an", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"실제 사진 카드 생성 실패: {proc.stderr[-400:]}")
    return str(out)


# ─────────── 통합 마지막 페이지: 실제 NOAA 사진 + 도감 도시에(충격 리빌) ───────────
FINAL_PAGE_DURATION_S = 3.8


def _dossier_overlay_html(caption: CaptionData, series_title: str, episode: int,
                          watermark: str, credit_string: str, sci_name: str,
                          eco_line: str = "") -> str:
    name_ko, name_en = _split_name(caption.reveal_name)
    e = lambda s: _html.escape(s or "")  # noqa: E731
    eco_html = f'<div class="eco">{e(eco_line)}</div>' if eco_line else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{htmlhud.fonts_face_css()}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:720px;height:1280px;overflow:hidden;background:transparent}}
.d{{position:relative;width:720px;height:1280px;font-family:'Rajdhani';color:#EAF0F4}}
.topsc{{position:absolute;top:0;left:0;right:0;height:200px;background:linear-gradient(180deg,rgba(3,8,12,.72),transparent)}}
.botsc{{position:absolute;left:0;right:0;bottom:0;height:640px;background:linear-gradient(0deg,rgba(3,8,12,.92) 30%,rgba(3,8,12,.7) 62%,transparent)}}
.frame{{position:absolute;inset:18px;border:1px solid rgba(234,240,244,.24)}}
.brk{{position:absolute;width:30px;height:30px;border:1.5px solid #EAF0F4}}
.brk.c{{border-color:#43C8DA}}
.tl{{top:12px;left:12px;border-right:0;border-bottom:0}}.tr{{top:12px;right:12px;border-left:0;border-bottom:0}}
.bl{{bottom:12px;left:12px;border-right:0;border-top:0}}.br{{bottom:12px;right:12px;border-left:0;border-top:0}}
.hdr{{position:absolute;top:38px;left:40px;font-family:'Orbitron';font-weight:900;font-size:16px;letter-spacing:4px;color:#43C8DA}}
.real{{position:absolute;top:40px;right:40px;font-family:'STM';font-size:14px;letter-spacing:2px;color:#9BE8F2;text-align:right}}
.tag{{position:absolute;left:40px;bottom:404px;font-family:'Orbitron';font-weight:900;font-size:15px;letter-spacing:4px;color:#43C8DA}}
.name{{position:absolute;left:40px;right:40px;bottom:322px;font-family:'BHS';font-size:76px;line-height:1;color:#fff;word-break:keep-all;text-shadow:0 2px 12px rgba(0,0,0,.6)}}
.sci{{position:absolute;left:42px;right:40px;bottom:284px}}
.sci .en{{font-family:'Orbitron';font-weight:900;font-size:20px;letter-spacing:1px;color:#CBD6DE}}
.sci .la{{font-family:'PretendardM';font-style:italic;font-size:19px;color:#9FB0BA;margin-left:8px}}
.eco{{position:absolute;left:42px;right:44px;bottom:244px;font-family:'STM';font-size:16px;letter-spacing:.5px;color:#67C6D6;line-height:1.4;word-break:keep-all}}
.fact{{position:absolute;left:42px;right:44px;bottom:196px;font-family:'PretendardM';font-size:21px;color:#D6E0E7;line-height:1.32;word-break:keep-all;text-wrap:pretty}}
.cta{{position:absolute;left:40px;right:40px;bottom:120px;font-family:'Pretendard';font-weight:900;font-size:32px;color:#fff;text-shadow:0 0 16px rgba(80,200,240,.35)}}
.cta b{{color:#43C8DA}}
.src{{position:absolute;left:42px;bottom:44px;font-family:'STM';font-size:15px;letter-spacing:1px;color:#8FA0AA}}
.wm{{position:absolute;right:34px;bottom:44px;font-family:'Orbitron';font-weight:900;font-size:15px;letter-spacing:3px;color:rgba(234,240,244,.72)}}
</style></head><body>
<div class="d">
  <div class="topsc"></div><div class="botsc"></div>
  <div class="frame"></div><div class="brk tl c"></div><div class="brk tr"></div><div class="brk bl"></div><div class="brk br c"></div>
  <div class="hdr">◉ DATABASE ENTRY · No.{episode:03d}</div>
  <div class="real">ARCHIVE / ACTUAL SPECIMEN<br>{e(series_title)}</div>
  <div class="tag">▶ SPECIES IDENTIFIED</div>
  <div class="name">{e(name_ko)}</div>
  <div class="sci"><span class="en">{e(name_en).upper()}</span><span class="la">{e(sci_name)}</span></div>
  {eco_html}
  <div class="fact">{e(caption.reveal_fact)}</div>
  <div class="cta">팔로우하고 <b>다음 심해 생물</b> 만나기</div>
  <div class="src">SOURCE: {e(credit_string)}</div>
  <div class="wm">{e(watermark)}</div>
</div></body></html>"""


def _dossier_overlay_png(caption: CaptionData, series_title: str, episode: int,
                         watermark: str, credit_string: str, sci_name: str, work_dir: str,
                         eco_line: str = "") -> str:
    """도시에(정보) 투명 오버레이 PNG. HTML 우선, 브라우저 불가 시 PIL 폴백."""
    out = str(Path(work_dir) / "dossier_overlay.png")
    try:
        html = _dossier_overlay_html(caption, series_title, episode, watermark,
                                     credit_string, sci_name, eco_line)
        return htmlhud.render_static(html, out, work_dir, name="dossier", transparent=True)
    except htmlhud.HudRenderError:
        img = Image.new("RGBA", (CLIP_W, CLIP_H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([0, CLIP_H - 640, CLIP_W, CLIP_H], fill=(3, 8, 12, 210))
        name_ko, name_en = _split_name(caption.reveal_name)
        _text_with_stroke(d, (40, 40), f"DATABASE ENTRY · No.{episode:03d}", _orbitron(20), fill=(67, 200, 218, 255))
        y = CLIP_H - 360
        for line in _wrap(d, name_ko, _font(64), CLIP_W - 90):
            _text_with_stroke(d, (40, y), line, _font(64), fill=(255, 230, 160, 255)); y += 76
        _text_with_stroke(d, (42, y), name_en, _orbitron(22), fill=(203, 214, 222, 255)); y += 46
        if eco_line:
            _text_with_stroke(d, (42, y), eco_line, _orbitron(16), fill=(103, 198, 214, 255)); y += 44
        for line in _wrap(d, caption.reveal_fact or "", _font(34), CLIP_W - 100):
            _text_with_stroke(d, (42, y), line, _font(34), fill=(214, 224, 231, 255)); y += 46
        _text_with_stroke(d, (40, CLIP_H - 150), "팔로우하고 다음 심해 생물 만나기", _font(34), anchor="lm")
        _text_with_stroke(d, (42, CLIP_H - 60), f"SOURCE: {credit_string}", _orbitron(18), fill=(143, 160, 170, 255))
        _text_with_stroke(d, (CLIP_W - 34, CLIP_H - 60), watermark, _orbitron(18), fill=(234, 240, 244, 200), anchor="rm")
        img.save(out)
        return out


def _subject_center(asset_path: str) -> tuple[float, float]:
    """사진 속 생물의 중심을 (0~1, 0~1)로 반환. 비전 모델 사용, 실패 시 중앙(0.5,0.5)."""
    import os
    if not os.environ.get("GEMINI_API_KEY"):
        return (0.5, 0.5)
    try:
        from google import genai
        from google.genai import types
        client = genai.Client()
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=Path(asset_path).read_bytes(), mime_type="image/jpeg"),
                "이 사진에서 가장 두드러진 해양생물(피사체) 몸통의 중심점을 이미지 기준 "
                "정규화 좌표로 알려줘. x는 왼쪽0~오른쪽1, y는 위0~아래1. "
                "다른 말 없이 'x,y' 숫자만 (예: 0.42,0.55).",
            ],
        )
        m = re.search(r"([01](?:\.\d+)?)\s*,\s*([01](?:\.\d+)?)", getattr(resp, "text", "") or "")
        if m:
            cx, cy = float(m.group(1)), float(m.group(2))
            if 0 <= cx <= 1 and 0 <= cy <= 1:
                return (cx, cy)
    except Exception as e:  # noqa: BLE001
        log_ = __import__("logging").getLogger(__name__)
        log_.warning("피사체 중심 검출 실패 → 중앙 크롭: %s", e)
    return (0.5, 0.5)


def build_final_page(caption: CaptionData, series_title: str, episode: int, watermark: str,
                     asset_path: str, credit_string: str, sci_name: str, work_dir: str,
                     eco_line: str = "") -> str:
    """통합 마지막 페이지: 실제 NOAA 사진(꽉 채움·피사체 중앙 크롭)이 충격 리빌로 등장하고,
    그 위에 종 도감 도시에(종명·학명 이탤릭·생태특성·팩트·팔로우·출처)를 얹는다."""
    work = Path(work_dir)
    if not Path(asset_path).exists():
        raise PipelineError("endcard", f"실제 사진 없음: {asset_path}")
    overlay = _dossier_overlay_png(caption, series_title, episode, watermark,
                                   credit_string, sci_name, work_dir, eco_line)
    out = work / "final_page.mp4"
    fps, dur = CLIP_FPS, FINAL_PAGE_DURATION_S
    frames = int(dur * fps)
    # 피사체 중심 검출 → 그 지점을 중앙에 두고 9:16 cover 크롭 (생물이 화면 중앙에 오도록)
    cx, cy = _subject_center(asset_path)
    crop_x = f"clip(iw*{cx:.3f}-{CLIP_W//2},0,iw-{CLIP_W})"
    crop_y = f"clip(ih*{cy:.3f}-{CLIP_H//2},0,ih-{CLIP_H})"
    bg = (f"[0:v]scale={CLIP_W}:{CLIP_H}:force_original_aspect_ratio=increase,"
          f"crop={CLIP_W}:{CLIP_H}:x='{crop_x}':y='{crop_y}',"
          f"scale={CLIP_W*2}:{CLIP_H*2},"
          f"zoompan=z='max(1.03,1.18-0.15*on/8)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={CLIP_W}x{CLIP_H}:fps={fps},setsar=1,"
          f"eq=brightness=-0.06:saturation=1.06,"
          f"drawbox=x=0:y='ih*(t/0.6)':w=iw:h=4:color=0x9BE8F2@0.85:t=fill:enable='lt(t,0.6)',"
          f"fade=t=in:st=0:d=0.18:color=white[bg]")
    fc = f"{bg};[bg][1:v]overlay=0:0:format=auto,fade=t=out:st={dur-0.4:.2f}:d=0.4[v]"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-t", str(dur),
         "-i", asset_path, "-i", overlay, "-filter_complex", fc, "-map", "[v]", "-t", str(dur),
         "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-an", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"마지막 페이지 생성 실패: {proc.stderr[-400:]}")
    return str(out)


def concat_tail(videos: list[str], work_dir: str) -> str:
    """본편+실제사진카드+엔드카드 등 N개 클립을 재인코딩 concat (규격 통일)."""
    out = Path(work_dir) / "with_tail.mp4"
    parts = "".join(
        f"[{i}:v]scale={CLIP_W}:{CLIP_H},fps={CLIP_FPS},setsar=1[v{i}];"
        for i in range(len(videos))
    )
    joins = "".join(f"[v{i}]" for i in range(len(videos)))
    fc = f"{parts}{joins}concat=n={len(videos)}:v=1:a=0[outv]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for v in videos:
        cmd += ["-i", v]
    cmd += ["-filter_complex", fc, "-map", "[outv]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise PipelineError("endcard", f"tail concat 실패: {proc.stderr[-400:]}")
    return str(out)
