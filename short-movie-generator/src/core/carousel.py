"""carousel — 릴스와 함께 만드는 '게시물(인스타 캐러셀)' 5장 생성.

전략(사용자 확정): 도감형 인포그래픽 · 실사(NOAA)+HUD 인포그래픽 · 5장 · 4:5(1080x1350).
릴스가 도달(발견)이라면 캐러셀은 저장·신뢰·전문성. 릴스와 톤 통일(스키매틱 HUD 언어),
사실만(정확성 하드룰), 출처 표기(저작권 하드룰), 화면 조판 규칙(keep-all/pretty) 준수.

구성:
  [1] 표지  : NOAA 실사 배경(어둡게) + 훅 + 도감 넘버 + 스와이프
  [2] 정체·서식: 단색 월드맵 + 수심/수온/분포 + 종명(국문·영문·학명)
  [3] 형태 스펙: SPECIMEN DATA(수심·서식·먹이·특징) + 실사 썸네일
  [4] 놀라운 사실: fun_facts 2~3개 + 생태 한 줄
  [5] 출처·CTA : 이미지 출처 + 정보 출처 + 팔로우 유도 + 핸들

렌더: HTML → PNG(Playwright, htmlhud.render_static 재사용, 1080x1350). 브라우저 없으면 빈 리스트.
"""
from __future__ import annotations

import html as _html
import logging
from pathlib import Path

from src.core import htmlhud
from src.core.contracts import CaptionData, SpeciesInfo

log = logging.getLogger(__name__)

CW, CH = 1080, 1080  # 1:1 정사각 (카드뉴스 규격 — 무조건 1:1)
BRAND = "DEEP DIVE LOG"


def _e(s: str) -> str:
    return _html.escape(s or "")


def _img_data_uri(asset_path: str) -> str:
    """실사 이미지를 base64 data URI로 임베드(Playwright에서 file:// 서브리소스보다 확실히 로드)."""
    try:
        import base64
        p = Path(asset_path)
        if not p.exists():
            return ""
        b = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b}"
    except Exception:  # noqa: BLE001
        return ""


def _base_css() -> str:
    return (htmlhud.fonts_face_css() + """
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1080px;height:1080px;overflow:hidden}
.s{position:relative;width:1080px;height:1080px;font-family:'Rajdhani';color:#EAF0F4;
  background:radial-gradient(120% 90% at 50% 22%,#0b1a24 0%,#06111a 55%,#03080d 100%);overflow:hidden}
.grid{position:absolute;inset:0;opacity:.05;background:linear-gradient(#fff 1px,transparent 1px) 0 0/80px 80px,linear-gradient(90deg,#fff 1px,transparent 1px) 0 0/80px 80px}
.frame{position:absolute;inset:26px;border:1px solid rgba(234,240,244,.24)}
.brk{position:absolute;width:40px;height:40px;border:2px solid #EAF0F4}
.brk.c{border-color:#43C8DA}
.tl{top:18px;left:18px;border-right:0;border-bottom:0}.tr{top:18px;right:18px;border-left:0;border-bottom:0}
.bl{bottom:18px;left:18px;border-right:0;border-top:0}.br{bottom:18px;right:18px;border-left:0;border-top:0}
.top{position:absolute;top:46px;left:56px;right:56px;display:flex;justify-content:space-between;align-items:center}
.brand{font-family:'Orbitron';font-weight:900;font-size:20px;letter-spacing:5px;color:#43C8DA}
.no{font-family:'STM';font-size:18px;color:#94A2AC;letter-spacing:2px}
.wm{position:absolute;bottom:52px;right:56px;font-family:'Orbitron';font-weight:900;font-size:18px;letter-spacing:3px;color:rgba(234,240,244,.66)}
.pageno{position:absolute;bottom:52px;left:56px;font-family:'STM';font-size:17px;color:#5E6A73;letter-spacing:2px}
.kicker{font-family:'Orbitron';font-weight:900;font-size:20px;letter-spacing:5px;color:#43C8DA}
.hr{height:2px;background:linear-gradient(90deg,#43C8DA,rgba(234,240,244,.4) 45%,transparent);margin:14px 0 22px}
.kko{font-family:'BHS';word-break:keep-all;text-wrap:pretty}
.kmd{font-family:'PretendardM';word-break:keep-all;text-wrap:pretty}
""")


def _shell(inner: str, page: int, cover: bool = False) -> str:
    brand = "" if cover else (
        '<div class="top"><span class="brand">◉ ' + BRAND + '</span>'
        '<span class="no">DATABASE ENTRY</span></div>')
    return ("<!doctype html><html><head><meta charset='utf-8'><style>" + _base_css() +
            "</style></head><body><div class='s'>"
            "<div class='grid'></div><div class='frame'></div>"
            "<div class='brk tl c'></div><div class='brk tr'></div><div class='brk bl'></div><div class='brk br c'></div>"
            + brand + inner +
            "<div class='pageno'>" + f"{page:02d} / 05" + "</div>"
            "<div class='wm'>" + BRAND + "</div>"
            "</div></body></html>")


def _cover(info: SpeciesInfo, caption: CaptionData, asset_path: str, episode: int) -> str:
    hook = _e(caption.hook_text or f"수심 {info.depth_range_m}m에서 포착된 이것")
    uri = _img_data_uri(asset_path)
    # 실사 사진을 상단 '표본 패널'로(프레임+태그) → 어떤 사진이 와도 피사체가 확실히 보임.
    if uri:
        photo = (
            "<div style='position:absolute;left:44px;right:44px;top:110px;height:520px;"
            f"border:1px solid rgba(67,200,218,.5);background:linear-gradient(180deg,rgba(3,8,12,.05),rgba(3,8,12,.35)),"
            f"url(\"{uri}\") center/cover no-repeat'>"
            "<div style='position:absolute;top:16px;left:18px;font-family:Orbitron;font-weight:900;font-size:16px;letter-spacing:3px;color:#9BE8F2'>ARCHIVE / ACTUAL SPECIMEN</div>"
            "<div class='brk tl c' style='top:-1px;left:-1px'></div><div class='brk br c' style='bottom:-1px;right:-1px'></div>"
            "</div>")
    else:
        photo = ""
    inner = (
        "<div style='position:absolute;inset:0;background:radial-gradient(120% 90% at 50% 20%,#0b1a24,#03080d 70%)'></div>"
        "<div class='top' style='top:48px'><span class='brand'>◉ " + BRAND + "</span>"
        f"<span class='no'>No.{episode:03d}</span></div>"
        + photo +
        "<div style='position:absolute;left:60px;right:60px;bottom:74px'>"
        "<div class='kicker' style='color:#FFC24D;margin-bottom:14px'>▶ UNIDENTIFIED SPECIMEN</div>"
        f"<div class='kko' style='font-size:66px;line-height:1.1;color:#fff;text-shadow:0 3px 16px rgba(0,0,0,.7)'>{hook}</div>"
        "<div class='kmd' style='margin-top:18px;font-size:25px;color:#9BE8F2;letter-spacing:1px'>넘겨서 정체를 확인하세요 →</div>"
        "</div>")
    return _shell(inner, 1, cover=True)


def _habitat(info: SpeciesInfo) -> str:
    depth = htmlhud._max_depth_num(info)
    temp = htmlhud._deep_sea_temp_c(depth)
    mapsvg = htmlhud._schem_map_svg(0, 0).replace('id="mapscan"', 'style="display:none"').replace('id="mapband"', 'style="display:none"')
    dist = _e(info.distribution or "전 세계 심해")
    inner = (
        "<div style='position:absolute;left:60px;right:60px;top:140px'>"
        "<div class='kicker'>서식 · 분포</div><div class='hr'></div>"
        "<div style='width:100%;height:400px;border:1px solid rgba(234,240,244,.2);padding:16px;background:rgba(8,12,16,.3)'>"
        f"{mapsvg}</div>"
        "<div style='display:flex;gap:16px;margin-top:26px'>"
        f"<div style='flex:1;border-left:2px solid #43C8DA;padding:6px 16px'><div style='font-family:STM;font-size:18px;color:#7C8E98;letter-spacing:2px'>DEPTH</div><div style='font-family:STM;font-size:34px;color:#43C8DA'>{_e(info.depth_range_m)} m</div></div>"
        f"<div style='flex:1;border-left:2px solid rgba(234,240,244,.4);padding:6px 16px'><div style='font-family:STM;font-size:18px;color:#7C8E98;letter-spacing:2px'>TEMP</div><div style='font-family:STM;font-size:34px'>{temp}°C</div></div>"
        "</div>"
        f"<div class='kmd' style='margin-top:22px;font-size:26px;color:#C7D2DA'>분포: {dist}</div>"
        "</div>")
    return _shell(inner, 2)


def _form(info: SpeciesInfo, asset_path: str) -> str:
    diet = " · ".join(info.diet[:3]) if info.diet else "—"
    trait = _e(info.fun_facts[0]) if info.fun_facts else "—"
    uri = _img_data_uri(asset_path)
    thumb = (f"<div style='width:100%;height:300px;margin-bottom:22px;border:1px solid rgba(234,240,244,.2);"
             f"background:linear-gradient(180deg,rgba(3,8,12,.05),rgba(3,8,12,.45)),url(\"{uri}\") center/cover no-repeat'></div>") if uri else ""

    def row(k, v):
        return ("<div style='display:flex;gap:18px;align-items:baseline;margin-top:16px;border-bottom:1px solid rgba(234,240,244,.1);padding-bottom:14px'>"
                f"<div style='font-family:Rajdhani;font-weight:700;font-size:22px;letter-spacing:2px;color:#7C8E98;width:150px;flex:none'>{k}</div>"
                f"<div class='kmd' style='font-size:28px;color:#EAF0F4'>{v}</div></div>")
    inner = (
        "<div style='position:absolute;left:60px;right:60px;top:140px'>"
        "<div class='kicker'>표본 데이터</div><div class='hr'></div>"
        + thumb
        + row("수심 · DEPTH", _e(info.depth_range_m) + " m")
        + row("서식 · HABITAT", _e(info.habitat or "심해"))
        + row("먹이 · DIET", _e(diet))
        + row("특징 · TRAIT", trait)
        + "</div>")
    return _shell(inner, 3)


def _facts(info: SpeciesInfo, eco_line: str) -> str:
    facts = [f for f in (info.fun_facts or [])[1:4]] or (info.fun_facts or [])[:3]
    items = ""
    for i, f in enumerate(facts, 1):
        items += ("<div style='display:flex;gap:20px;margin-top:26px'>"
                  f"<div style='font-family:Orbitron;font-weight:900;font-size:40px;color:#43C8DA;line-height:1'>{i:02d}</div>"
                  f"<div class='kmd' style='font-size:31px;line-height:1.4;color:#EAF0F4'>{_e(f)}</div></div>")
    eco = (f"<div class='kmd' style='margin-top:40px;font-size:24px;color:#67C6D6;border-top:1px solid rgba(234,240,244,.15);padding-top:20px'>{_e(eco_line)}</div>"
           if eco_line else "")
    inner = (
        "<div style='position:absolute;left:60px;right:60px;top:140px'>"
        "<div class='kicker' style='color:#FFC24D'>놀라운 사실</div><div class='hr'></div>"
        + items + eco + "</div>")
    return _shell(inner, 4)


def _source(info: SpeciesInfo, caption: CaptionData, credit_string: str) -> str:
    name_ko = _e(info.common_name_ko)
    name_en = _e(info.common_name_en)
    sci = _e(info.scientific_name)
    src_info = " · ".join(s for s in (info.sources or []) if s) or "NOAA · WoRMS"
    inner = (
        "<div style='position:absolute;left:60px;right:60px;top:180px'>"
        "<div class='kicker'>▶ SPECIES IDENTIFIED</div><div class='hr'></div>"
        f"<div class='kko' style='font-size:78px;line-height:1.05;color:#fff'>{name_ko}</div>"
        f"<div style='margin-top:14px'><span style='font-family:Orbitron;font-weight:900;font-size:26px;color:#CBD6DE;letter-spacing:1px'>{name_en.upper()}</span>"
        f"<span style='font-family:PretendardM;font-style:italic;font-size:24px;color:#9FB0BA;margin-left:10px'>{sci}</span></div>"
        "<div style='margin-top:120px;border-top:1px solid rgba(234,240,244,.16);padding-top:26px'>"
        f"<div style='font-family:STM;font-size:22px;color:#8FA0AA;line-height:1.7'>이미지 출처: {_e(credit_string)}<br>정보 출처: {_e(src_info)}</div>"
        "</div>"
        "<div class='kmd' style='margin-top:56px;font-size:40px;font-weight:900;color:#fff'>팔로우하고 <span style='color:#43C8DA'>다음 심해 생물</span> 만나기</div>"
        "<div style='font-family:STM;font-size:24px;color:#9BE8F2;margin-top:14px;letter-spacing:2px'>@deep.dive.log</div>"
        "</div>")
    return _shell(inner, 5)


def build_carousel(info: SpeciesInfo, caption: CaptionData, credit_string: str,
                   asset_path: str, work_dir: str, episode: int,
                   eco_line: str = "") -> list[str]:
    """게시물 5장 PNG(1080x1350) 생성 → 파일 경로 리스트. 브라우저 불가 시 빈 리스트(발행 불정지)."""
    work = Path(work_dir)
    slides = [
        ("post_1_cover", _cover(info, caption, asset_path, episode)),
        ("post_2_habitat", _habitat(info)),
        ("post_3_form", _form(info, asset_path)),
        ("post_4_facts", _facts(info, eco_line)),
        ("post_5_source", _source(info, caption, credit_string)),
    ]
    out = []
    for name, html in slides:
        png = str(work / f"{name}.png")
        try:
            htmlhud.render_static(html, png, str(work), name=name, width=CW, height=CH)
            out.append(png)
        except htmlhud.HudRenderError as e:
            log.warning("[carousel] 슬라이드 렌더 실패(%s) → 게시물 생략: %s", name, e)
            return []
    log.info("[carousel] 게시물 %d장 생성", len(out))
    return out
