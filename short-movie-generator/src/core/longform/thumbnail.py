"""thumbnail — 롱폼(랭킹형) 유튜브 썸네일(16:9, 1280x720) 자동 생성.

기획서 규칙 준수: OS 이모지 금지(스파클은 인라인 SVG 벡터), 학명 이탤릭, 날조 금지
(피사체는 실제 소싱 프레임만 사용). 구성: 어두운 심해 배경 + 광선 → 우측 피사체(마스크로
배경에 자연스럽게 페이드) → 좌측 큰 흰색 일본어 타이틀(글로우) + 검은 태그 박스 →
중앙하단 골드 숫자 배지(예: 6選). HTML/CSS를 Playwright로 1280x720 PNG 렌더(기존 htmlhud 재사용).

파이프라인 연동: run_longform이 확정한 제목/편수/대표 피사체 프레임을 넣어 호출.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

log = logging.getLogger(__name__)

W, H = 1280, 720


def _data_uri(img_path: str) -> str:
    """이미지 파일 → base64 data URI (file:// 상대경로 미해결 문제 회피, 자기완결 HTML)."""
    p = Path(img_path)
    ext = p.suffix.lower().lstrip(".") or "jpg"
    mime = "jpeg" if ext in ("jpg", "jpeg") else ext
    return f"data:image/{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def build_html(title_lines: list[str], tag: str, count: int, unit: str,
               creature_img: str, accent: str = "#7fe3e0") -> str:
    """썸네일 HTML 문자열. title_lines=제목 줄들, tag=배지 문구(예: 実在します),
    count/unit=골드 숫자 배지(예: 6 / 選), creature_img=피사체 프레임 경로."""
    img = _data_uri(creature_img)
    title_html = "<br>".join(title_lines)
    sparkle = (
        "<svg class='spark' viewBox='0 0 100 100' width='46' height='46'>"
        "<path d='M50 2 L58 42 L98 50 L58 58 L50 98 L42 58 L2 50 L42 42 Z' "
        "fill='#dfeff0' opacity='0.85'/></svg>"
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  html,body{{width:{W}px;height:{H}px;overflow:hidden;
    font-family:'Noto Sans CJK JP','Noto Sans CJK KR','Noto Sans JP',sans-serif}}
  .stage{{position:relative;width:{W}px;height:{H}px;
    background:radial-gradient(120% 100% at 78% 8%, #123a40 0%, #0b2126 34%, #050d10 72%, #02080a 100%)}}
  /* 우측 피사체 — 커버 배치 후 좌측으로 페이드시켜 텍스트 공간 확보 */
  .subj{{position:absolute;inset:0;background:url('{img}') no-repeat right center/cover;
    -webkit-mask-image:linear-gradient(90deg,transparent 30%,#000 62%);
            mask-image:linear-gradient(90deg,transparent 30%,#000 62%)}}
  .subj::after{{content:'';position:absolute;inset:0;
    background:linear-gradient(90deg,#02080a 26%,rgba(3,10,13,.25) 52%,transparent 74%)}}
  /* 상단에서 비스듬히 내리는 광선 */
  .ray{{position:absolute;top:-14%;left:58%;width:30%;height:135%;transform:rotate(15deg);
    background:linear-gradient(180deg,rgba(226,248,249,.55),rgba(226,248,249,.10) 52%,transparent 76%);
    filter:blur(9px);mix-blend-mode:screen;pointer-events:none}}
  .vig{{position:absolute;inset:0;box-shadow:inset 0 0 220px 60px rgba(0,0,0,.55);pointer-events:none}}
  /* 좌측 텍스트 블록 */
  .txt{{position:absolute;left:58px;top:96px;width:720px}}
  .title{{color:#fff;font-weight:900;font-size:98px;line-height:1.06;letter-spacing:.5px;
    text-shadow:0 0 26px rgba(150,230,235,.55),0 3px 10px rgba(0,0,0,.8),0 1px 2px rgba(0,0,0,.9)}}
  .tag{{display:inline-block;margin-top:26px;background:#f4f4f2;color:#0a0f11;
    font-weight:800;font-size:34px;letter-spacing:2px;padding:8px 20px 10px;border-radius:4px;
    box-shadow:0 4px 16px rgba(0,0,0,.5)}}
  /* 골드 숫자 배지 */
  .badge{{position:absolute;left:250px;top:430px;display:flex;align-items:baseline;
    filter:drop-shadow(0 4px 18px rgba(230,180,50,.45)) drop-shadow(0 2px 3px rgba(0,0,0,.8))}}
  .num{{font-weight:900;font-size:250px;line-height:.9;
    background:linear-gradient(180deg,#fff6cf 6%,#f2cf6a 40%,#d99b2a 66%,#b8791b 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent}}
  .unit{{font-weight:900;font-size:110px;margin-left:8px;
    background:linear-gradient(180deg,#fff6cf 6%,#f2cf6a 44%,#c98b22 100%);
    -webkit-background-clip:text;background-clip:text;color:transparent}}
  .s1{{position:absolute;right:150px;bottom:110px;filter:drop-shadow(0 0 9px rgba(200,240,240,.75))}}
</style></head><body>
  <div class='stage'>
    <div class='subj'></div>
    <div class='ray'></div>
    <div class='vig'></div>
    <div class='txt'>
      <div class='title'>{title_html}</div>
      <div class='tag'>{tag}</div>
    </div>
    <div class='badge'><span class='num'>{count}</span><span class='unit'>{unit}</span></div>
    <div class='s1'>{sparkle}</div>
  </div>
</body></html>"""


def render_thumbnail(out_png: str, work_dir: str, title_lines: list[str], tag: str,
                     count: int, creature_img: str, unit: str = "選") -> str:
    """썸네일 1장 렌더(1280x720 PNG) → out_png 경로 반환. 실패 시 예외."""
    from src.core import htmlhud
    html = build_html(title_lines, tag, count, unit, creature_img)
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    htmlhud.render_static(html, out_png, work_dir, name="thumbnail", width=W, height=H)
    log.info("[thumbnail] 생성: %s (%dx%d)", out_png, W, H)
    return out_png
