"""thumbnail — 롱폼(랭킹형) 유튜브 썸네일(16:9, 1280x720) 자동 생성.

기획서 규칙 준수: OS 이모지 금지(스파클·프레임은 CSS/SVG 벡터), 학명 이탤릭, 날조 금지
(피사체는 실제 소싱 프레임만 사용). 구성: 어두운 심해 배경 + 부유물 파티클 + 광선 + 림글로우
→ **우측에 피사체(좌측 텍스트와 겹치지 않게 우측 반쪽에 배치, 안쪽 가장자리는 배경으로 페이드)**
→ 좌측 대형 흰색 일본어 타이틀(글로우) + 골드 언더라인 + 검은 태그 → 중앙하단 골드 숫자 배지
→ **깔끔한 인셋 프레임 선 + 코너 브래킷**. HTML/CSS를 Playwright로 1280x720 PNG 렌더.
"""
from __future__ import annotations

import base64
import logging
import random
from pathlib import Path

log = logging.getLogger(__name__)

W, H = 1280, 720


def _data_uri(img_path: str) -> str:
    """이미지 파일 → base64 data URI (file:// 상대경로 미해결 회피, 자기완결 HTML)."""
    p = Path(img_path)
    ext = p.suffix.lower().lstrip(".") or "jpg"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return f"data:image/{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _snow(n: int = 46, seed: int = 42) -> str:
    """부유물(마린 스노우) 파티클 — 단일 엘리먼트의 box-shadow 목록(결정적 seed)."""
    rng = random.Random(seed)
    dots = []
    for _ in range(n):
        x = rng.randint(0, W); y = rng.randint(0, H)
        a = round(rng.uniform(0.05, 0.28), 2)
        dots.append(f"{x}px {y}px 0 {rng.choice([0, 0, 1])}px rgba(210,238,240,{a})")
    return ",".join(dots)


def build_html(title_lines: list[str], tag: str, count: int, unit: str,
               creature_img: str) -> str:
    """썸네일 HTML. title_lines=제목 줄들, tag=배지 문구(예: 実在します),
    count/unit=골드 숫자 배지(예: 6/選), creature_img=피사체 프레임 경로."""
    img = _data_uri(creature_img)
    title_html = "<br>".join(title_lines)
    snow = _snow()
    sparkle = (
        "<svg viewBox='0 0 100 100' width='42' height='42'>"
        "<path d='M50 3 L57 43 L97 50 L57 57 L50 97 L43 57 L3 50 L43 43 Z' "
        "fill='#eaf6f7' opacity='0.9'/></svg>"
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px;overflow:hidden;
    font-family:'Noto Sans CJK JP','Noto Sans CJK KR','Noto Sans JP',sans-serif}}
  .stage{{position:relative;width:{W}px;height:{H}px;
    background:radial-gradient(130% 110% at 74% 6%, #16454b 0%, #0d2a30 30%, #061217 66%, #02080a 100%)}}
  /* 피사체 뒤 시안 림글로우 */
  .glow{{position:absolute;right:2%;top:8%;width:62%;height:86%;border-radius:50%;
    background:radial-gradient(closest-side, rgba(60,190,200,.30), rgba(40,150,165,.10) 55%, transparent 72%);
    filter:blur(12px);mix-blend-mode:screen;pointer-events:none}}
  /* ★피사체 — 화면 우측에만 배치(좌측 텍스트와 안 겹침) + 안쪽(좌) 가장자리 배경 페이드.
     object-position으로 종(벨)을 우측 가시영역에 정확히 앉힌다(벨이 화면 밖으로 밀리지 않게). */
  .subj{{position:absolute;top:0;right:0;width:62%;height:100%;overflow:hidden;
    -webkit-mask-image:linear-gradient(90deg,transparent 0%,#000 33%);
            mask-image:linear-gradient(90deg,transparent 0%,#000 33%)}}
  .subj img{{position:absolute;inset:0;width:100%;height:100%;
    object-fit:cover;object-position:40% center;filter:saturate(1.08) contrast(1.06)}}
  .snow{{position:absolute;left:0;top:0;width:1px;height:1px;border-radius:50%;
    box-shadow:{snow};pointer-events:none}}
  .ray{{position:absolute;top:-14%;left:56%;width:26%;height:135%;transform:rotate(15deg);
    background:linear-gradient(180deg,rgba(226,248,249,.5),rgba(226,248,249,.09) 52%,transparent 76%);
    filter:blur(9px);mix-blend-mode:screen;pointer-events:none}}
  .vig{{position:absolute;inset:0;box-shadow:inset 0 0 240px 70px rgba(0,0,0,.6);pointer-events:none}}
  /* 좌측 텍스트 */
  .txt{{position:absolute;left:62px;top:92px;width:660px;z-index:3}}
  .title{{color:#fff;font-weight:900;font-size:99px;line-height:1.05;letter-spacing:.5px;
    text-shadow:0 0 28px rgba(150,232,238,.55),0 3px 10px rgba(0,0,0,.85),0 1px 2px rgba(0,0,0,.95)}}
  .uline{{width:190px;height:5px;margin-top:20px;border-radius:3px;
    background:linear-gradient(90deg,#ffe9a3,#e0a92e 60%,transparent);
    box-shadow:0 0 14px rgba(230,175,60,.6)}}
  .tag{{display:inline-block;margin-top:20px;background:#f5f4f1;color:#0a0f11;
    font-weight:800;font-size:33px;letter-spacing:2px;padding:8px 20px 10px;border-radius:5px;
    box-shadow:0 4px 16px rgba(0,0,0,.55)}}
  /* 골드 숫자 배지 */
  .badge{{position:absolute;left:110px;top:452px;display:flex;align-items:baseline;z-index:3;
    filter:drop-shadow(0 4px 20px rgba(230,180,50,.5)) drop-shadow(0 2px 3px rgba(0,0,0,.85))}}
  .num{{font-weight:900;font-size:236px;line-height:.9;
    background:linear-gradient(180deg,#fff7d4 4%,#f6d878 34%,#e0a52e 62%,#b9791a 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent;
    -webkit-text-stroke:2px rgba(120,74,10,.35)}}
  .unit{{font-weight:900;font-size:104px;margin-left:10px;
    background:linear-gradient(180deg,#fff7d4 4%,#f0c65e 46%,#c98b22 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent}}
  /* 깔끔한 인셋 프레임 + 코너 브래킷 */
  .frame{{position:absolute;inset:20px;border:2px solid rgba(224,244,246,.42);border-radius:9px;
    box-shadow:inset 0 0 0 1px rgba(0,0,0,.28), inset 0 0 40px rgba(0,0,0,.35);
    pointer-events:none;z-index:4}}
  .cnr{{position:absolute;width:34px;height:34px;border:3px solid #ffe6a6;z-index:5;
    filter:drop-shadow(0 0 6px rgba(230,180,60,.55))}}
  .tl{{left:14px;top:14px;border-right:0;border-bottom:0;border-radius:8px 0 0 0}}
  .tr{{right:14px;top:14px;border-left:0;border-bottom:0;border-radius:0 8px 0 0}}
  .bl{{left:14px;bottom:14px;border-right:0;border-top:0;border-radius:0 0 0 8px}}
  .br{{right:14px;bottom:14px;border-left:0;border-top:0;border-radius:0 0 8px 0}}
  .spark{{position:absolute;right:150px;bottom:104px;z-index:3;
    filter:drop-shadow(0 0 9px rgba(200,240,240,.8))}}
</style></head><body>
  <div class='stage'>
    <div class='glow'></div>
    <div class='subj'><img src='{img}'></div>
    <div class='snow'></div>
    <div class='ray'></div>
    <div class='vig'></div>
    <div class='txt'>
      <div class='title'>{title_html}</div>
      <div class='uline'></div>
      <div class='tag'>{tag}</div>
    </div>
    <div class='badge'><span class='num'>{count}</span><span class='unit'>{unit}</span></div>
    <div class='spark'>{sparkle}</div>
    <div class='frame'></div>
    <div class='cnr tl'></div><div class='cnr tr'></div>
    <div class='cnr bl'></div><div class='cnr br'></div>
  </div>
</body></html>"""


def pick_hero_frame(footage_path: str, out_jpg: str) -> str:
    """대표 피사체 프레임 1장 추출 — subject_score(피사체 잘 보임) 최고 프레임.
    붉은 피사체 신호가 없으면(비적색 생물) 클립 중앙 프레임으로 폴백. 썸네일용."""
    import shutil
    import subprocess
    from src.core import reframe
    work = Path(out_jpg).parent / "_hero"
    work.mkdir(parents=True, exist_ok=True)
    for f in work.glob("h_*.jpg"):
        f.unlink(missing_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", footage_path,
                    "-vf", "fps=1,scale=1280:720", "-q:v", "2", str(work / "h_%03d.jpg")],
                   check=True)
    frames = sorted(work.glob("h_*.jpg"))
    if not frames:
        raise RuntimeError(f"hero 프레임 추출 실패: {footage_path}")
    best = max(frames, key=lambda f: reframe.subject_score(str(f)))
    if reframe.subject_score(str(best)) <= 0:      # 적색 신호 없음 → 중앙 프레임
        best = frames[len(frames) // 2]
    shutil.copy(str(best), out_jpg)
    return out_jpg


def render_thumbnail(out_png: str, work_dir: str, title_lines: list[str], tag: str,
                     count: int, creature_img: str, unit: str = "選") -> str:
    """썸네일 1장 렌더(1280x720 PNG) → out_png 경로 반환. 실패 시 예외."""
    from src.core import htmlhud
    html = build_html(title_lines, tag, count, unit, creature_img)
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    htmlhud.render_static(html, out_png, work_dir, name="thumbnail", width=W, height=H)
    log.info("[thumbnail] 생성: %s (%dx%d)", out_png, W, H)
    return out_png
