"""htmlhud — 애니메이션 SF ROV HUD 엔진 (HTML/CSS + Playwright 프레임 렌더 → FFmpeg 합성).

전략(CLAUDE.md): 현실 기반 극도로 드라마틱한 심해 미스터리. 실제 생물 위에
'우주선 조종 계기판(ROV)' HUD를 얹어 SCANNING → ANALYZING → SPECIES IDENTIFIED로 리빌한다.

왜 HTML인가:
- PIL 정적 합성은 폰트·글로우·글래스모피즘·타이핑 애니메이션 표현이 빈약하다.
- HTML/CSS + 상용가능 OFL 폰트(Orbitron·Share Tech Mono·Black Han Sans·Pretendard)로
  '세련된 우주선 인터페이스'를 만들고, 결정적 render(t) 함수로 매 프레임을 그려
  Playwright(headless Chromium)로 투명 PNG 시퀀스를 뽑은 뒤 FFmpeg로 영상 위에 올린다.

원칙:
- render(t)는 순수 결정적(같은 t → 같은 화면) → 재현 가능·프레임 시퀀스화 용이.
- 화면 중앙(생물)은 가리지 않는다. HUD는 프레임·코너·상하단으로.
- 브라우저 사용 불가/실패 시 상위(pipeline)가 PIL hud로 폴백 (파이프라인 불정지).
"""
from __future__ import annotations

import json
import logging
import math
import re
import subprocess
from pathlib import Path

from src.core.contracts import CaptionData, PipelineError, SpeciesInfo
from src.core.visualization.base import CLIP_H, CLIP_W

log = logging.getLogger(__name__)

HUD_FPS = 12.5  # 오버레이 프레임레이트 (출력 25fps의 1/2 — 부드럽되 렌더 비용 절반)

# 타이핑 타이밍 (초/글자). 시각(render(t))과 효과음(sfx_timeline)이 공유 → 항상 동기.
HOOK_CPS, BEAT_CPS, NAME_CPS, FACT_CPS = 0.085, 0.075, 0.11, 0.062
HOOK_START, BEAT_START_OFF = 0.25, 0.15   # 훅 시작(절대), 컷2 비트 시작(=d0+off)
NAME_START_OFF, FACT_GAP = 0.20, 0.25      # 리빌 이름 시작(=rs+off), 팩트=이름끝+gap
HOOK_MIN, BEAT_MIN, NAME_MIN, FACT_MIN = 1.0, 0.9, 0.7, 0.9
_CHROMIUM_CANDIDATES = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
]
_FONTS_DIR = Path(__file__).resolve().parents[2] / "vendor" / "fonts"


class HudRenderError(RuntimeError):
    """HTML HUD 렌더 실패 (상위에서 폴백 판단)."""


def _max_depth_num(info: SpeciesInfo) -> int:
    raw = info.depth_range_m.split("-")[-1]
    digits = re.sub(r"[^\d]", "", raw)
    return int(digits) if digits else 4000


def _clip_trait(s: str, limit: int = 28) -> str:
    """상단 코너 SPECIMEN 패널용 특징 요약 — 문장부호에서 잘라 한 줄로(길면 … 부여)."""
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    head = s[:limit]
    cut = max(head.rfind("."), head.rfind(","), head.rfind(" "))
    return (head[:cut] if cut >= limit - 10 else head).rstrip() + "…"


def _deep_sea_temp_c(depth_m: int) -> float:
    """수심(m) → 통상 심해 수온(°C) 역산.

    해양 수온 프로파일 근사: 표층은 따뜻하고 수온약층에서 급강하한 뒤 심해는 ~2°C로 수렴.
    지수 감쇠 모델 T(d) = 1.8 + 16.5·exp(-d/750), 하한 1.5°C.
    예) 1,000m≈6.2°C / 2,000m≈2.9°C / 4,000m≈1.9°C (실측 대표값과 근사).
    """
    t = 1.8 + 16.5 * math.exp(-depth_m / 750.0)
    return round(max(1.5, t), 1)


def _windows(cut_durations: list[float]) -> list[tuple[float, float]]:
    t0, out = 0.0, []
    for d in cut_durations:
        out.append((t0, t0 + d))
        t0 += d
    while len(out) < 3:
        out.append(out[-1] if out else (0.0, 0.0))
    return out[:3]


def _config(caption: CaptionData, info: SpeciesInfo, watermark: str,
            cut_durations: list[float]) -> dict:
    w = _windows(cut_durations)
    beats = (caption.cut_beats or ["", "", ""]) + ["", "", ""]
    # 리빌 이름을 KR / EN 분리 (예: "덤보문어 (Dumbo Octopus)")
    name = caption.reveal_name or f"{info.common_name_ko} ({info.common_name_en})"
    m = re.match(r"^(.*?)\s*\(([^)]+)\)\s*$", name)
    name_ko, name_en = (m.group(1), m.group(2)) if m else (name, info.common_name_en)
    name_ko, name_en = name_ko.strip(), name_en.strip()
    hook = caption.hook_text or ""
    beat2 = beats[1] or ""
    fact = caption.reveal_fact or ""
    d0 = w[0][1] - w[0][0]
    rs = w[2][0]
    # 타이핑 지속시간 (시각·효과음 공유) — 느리게, 최소값 보장
    hook_dur = max(HOOK_MIN, len(hook) * HOOK_CPS)
    beat2_dur = max(BEAT_MIN, len(beat2) * BEAT_CPS)
    name_dur = max(NAME_MIN, len(name_ko) * NAME_CPS)
    fact_dur = max(FACT_MIN, len(fact) * FACT_CPS)
    return {
        "d0": d0,
        "d1": w[1][1] - w[1][0],
        "total": w[2][1],
        "revealStart": rs,
        "depthMax": _max_depth_num(info),
        "tempC": _deep_sea_temp_c(_max_depth_num(info)),  # 수심 기반 역산 수온
        "unit": "ROV · DEEP DIVE UNIT",
        "watermark": watermark,
        "lat": "34.21", "lon": "127.88",
        "hook": hook,
        "beat2": beat2,
        "revealName": name_ko,
        "revealEn": name_en,
        "sciName": info.scientific_name or "",   # 학명 (이탤릭·속명 대문자로 표기)
        "revealFact": fact,
        "mapLon": 127.9, "mapLat": 34.2,          # 서식지/탐지 좌표(마커) — 추후 종별화
        "distribution": info.distribution or "",
        # 생태 데이터 패널(콜아웃 대체) — 생물 위치와 무관해 임의 종에도 항상 정확
        "spDepth": f"{info.depth_range_m} m" if info.depth_range_m else "—",
        "spHabitat": info.habitat or "—",
        "spDiet": " · ".join(info.diet[:3]) if info.diet else "—",
        # 상단 코너 패널이라 짧게 유지(길면 아래로 늘어나 피사체를 침범) — 전체 특징은 마지막 페이지에 노출
        "spTrait": _clip_trait(info.fun_facts[0]) if info.fun_facts else "—",
        # 타이핑 스케줄 (start 절대초, dur초)
        "hookStart": HOOK_START, "hookDur": hook_dur,
        "beat2Start": d0 + BEAT_START_OFF, "beat2Dur": beat2_dur,
        "nameStart": rs + NAME_START_OFF, "nameDur": name_dur,
        "factStart": rs + NAME_START_OFF + name_dur + FACT_GAP, "factDur": fact_dur,
        # 근접 경보(실제 근접·인지 상황 한정): 컷2 후반(리빌 1.5s 전)에 붉은 경보로 긴장 고조.
        "alert": bool(caption.alert),
        "alertText": (caption.alert_text or "개체가 이쪽으로 접근 중"),
        "alertAt": max(d0 + 0.3, rs - 1.5),
    }


def sfx_timeline(caption: CaptionData, info: SpeciesInfo, cut_durations: list[float]) -> dict:
    """효과음 동기용 타임라인 (타이핑 버스트·스캔 종료·리빌 시점).

    render(t)와 동일한 _config 값을 재사용 → 화면 타이핑과 타자 효과음이 정확히 일치.
    """
    c = _config(caption, info, "", cut_durations)
    typing = []
    for start, dur, text in (
        (c["hookStart"], c["hookDur"], c["hook"]),
        (c["beat2Start"], c["beat2Dur"], c["beat2"]),
        (c["nameStart"], c["nameDur"], c["revealName"]),
        (c["factStart"], c["factDur"], c["revealFact"]),
    ):
        if text:
            typing.append((round(float(start), 3), round(float(dur), 3)))
    tl = {"typing": typing, "scan_end": float(c["revealStart"]), "reveal_at": float(c["revealStart"])}
    if c.get("alert"):  # 근접 경보 시각 타이밍과 동기된 '쿵쿵'+경보음 트리거
        tl["alert"] = round(float(c["alertAt"]), 3)
    return tl


# ─────────────────────────────── HTML 템플릿 ───────────────────────────────
# 확정 디자인(vendor/fonts/hud.html) 기반 + 투명 배경 + 애니메이션 노드 + render(t).
_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:'Orbitron';src:url('%FONTS%/Orbitron.ttf');font-weight:900}
@font-face{font-family:'Rajdhani';src:url('%FONTS%/Rajdhani-Bold.ttf');font-weight:700}
@font-face{font-family:'STM';src:url('%FONTS%/ShareTechMono.ttf')}
@font-face{font-family:'BHS';src:url('%FONTS%/BlackHanSans.ttf')}
@font-face{font-family:'Pretendard';src:url('%FONTS%/Pretendard-Black.woff2');font-weight:900}
@font-face{font-family:'PretendardM';src:url('%FONTS%/Pretendard-Medium.woff2')}
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:720px;height:1280px;overflow:hidden;background:transparent}
.stage{position:relative;width:720px;height:1280px;overflow:hidden;font-family:'Rajdhani'}
.vig{position:absolute;inset:0;background:radial-gradient(120% 92% at 50% 44%,transparent 46%,rgba(0,10,16,.42) 82%,rgba(0,6,10,.82) 100%);pointer-events:none}
.scan{position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(120,220,240,.03) 0 1px,transparent 1px 3px);pointer-events:none}
.frame{position:absolute;inset:16px;border:1px solid rgba(80,220,240,.16);border-radius:4px}
.brk{position:absolute;width:44px;height:44px;border:2px solid rgba(90,225,245,.9)}
.tl{top:14px;left:14px;border-right:0;border-bottom:0}.tr{top:14px;right:14px;border-left:0;border-bottom:0}
.bl{bottom:14px;left:14px;border-right:0;border-top:0}.br{bottom:14px;right:14px;border-left:0;border-top:0}
.tick{position:absolute;top:12px;left:14px;width:14px;height:4px;background:#FF8A3D}
.unit{position:absolute;top:34px;left:40px;font-family:'Orbitron';font-weight:900;font-size:15px;letter-spacing:4px;color:#39E0F0;text-shadow:0 0 8px rgba(57,224,240,.6)}
.rec{position:absolute;top:62px;left:40px;font-family:'STM';font-size:19px;color:#EAF6F8;letter-spacing:1px}
.rec b{color:#FF5A5A}
.tel{position:absolute;top:26px;right:22px;width:238px;padding:12px 14px;background:rgba(6,18,26,.42);border:1px solid rgba(80,220,240,.35);border-radius:6px;backdrop-filter:blur(3px)}
.tel .lab{font-family:'Rajdhani';font-weight:700;font-size:12px;letter-spacing:3px;color:#5FE6F2;text-transform:uppercase}
.tel .val{font-family:'STM';font-size:23px;color:#EAF6F8;line-height:1.15}
.tel .val.big{color:#39E0F0;text-shadow:0 0 10px rgba(57,224,240,.5)}
.tel .sub{font-family:'STM';font-size:14px;color:#8FA6B0}
.bar{position:absolute;top:24px;left:50%;transform:translateX(-50%);display:flex;gap:4px}
.bar i{width:26px;height:4px;background:rgba(90,225,245,.3)}.bar i.on{background:#39E0F0;box-shadow:0 0 6px #39E0F0}
.reticle{position:absolute;left:50%;top:480px;width:360px;height:360px;transform:translate(-50%,-50%);opacity:0}
.reticle .c{position:absolute;width:40px;height:40px;border:3px solid #39E0F0}
.reticle .a{top:0;left:0;border-right:0;border-bottom:0}.reticle .b{top:0;right:0;border-left:0;border-bottom:0}
.reticle .d{bottom:0;left:0;border-right:0;border-top:0}.reticle .e{bottom:0;right:0;border-left:0;border-top:0}
.reticle .lk{position:absolute;top:-30px;left:50%;transform:translateX(-50%);font-family:'Orbitron';font-weight:900;font-size:15px;letter-spacing:3px;color:#39E0F0;white-space:nowrap}
.scanline{position:absolute;left:16px;right:16px;height:2px;background:linear-gradient(90deg,transparent,rgba(80,225,245,.85),transparent);box-shadow:0 0 12px rgba(80,225,245,.7);top:0;opacity:0}
.hookwrap{position:absolute;top:196px;left:0;right:0;text-align:center;padding:0 34px}
.hookwrap::before{content:'';position:absolute;inset:-24px 0;background:radial-gradient(80% 120% at 50% 50%,rgba(0,8,14,.55),transparent 72%);z-index:-1}
.hook{font-family:'BHS';font-size:60px;line-height:1.14;color:#fff;text-shadow:0 3px 0 rgba(0,0,0,.85),0 0 22px rgba(80,200,240,.35);letter-spacing:-1px}
.hook .car{color:#39E0F0;font-weight:400}
.scanwrap{position:absolute;bottom:300px;left:52px;right:52px;text-align:center;
  padding:14px 20px 18px;border-radius:14px;background:rgba(5,16,24,.46);
  border:1px solid rgba(80,220,240,.30);backdrop-filter:blur(3px)}
.scanwrap .tag{font-family:'Orbitron';font-weight:900;font-size:31px;letter-spacing:6px;color:#39E0F0;text-shadow:0 0 15px rgba(57,224,240,.75)}
.scanwrap .sub{font-family:'Pretendard';font-weight:900;font-size:30px;color:#F2F8FB;margin-top:12px;min-height:36px;line-height:1.22;
  text-shadow:0 2px 0 rgba(0,0,0,.82),0 0 16px rgba(80,200,240,.32)}
.radar{position:absolute;bottom:150px;left:36px;width:120px;height:120px}
.sonarlab{position:absolute;bottom:128px;left:36px;font-family:'Rajdhani';font-weight:700;font-size:13px;letter-spacing:2px;color:#7FD8DC}
.reveal{position:absolute;left:24px;right:24px;bottom:96px;padding:18px 20px;background:linear-gradient(180deg,rgba(8,22,32,.62),rgba(5,14,22,.72));border:1px solid rgba(80,220,240,.5);border-radius:10px;backdrop-filter:blur(5px);opacity:0;box-shadow:0 0 34px rgba(20,120,150,.25)}
.reveal .lab{font-family:'Orbitron';font-weight:900;font-size:16px;letter-spacing:3px;color:#FF8A3D}
.reveal .name{font-family:'Pretendard';font-weight:900;font-size:44px;color:#FFD98A;text-shadow:0 0 16px rgba(255,200,120,.4);margin-top:4px;line-height:1.05}
.reveal .en{font-family:'Orbitron';font-weight:900;font-size:22px;color:#FFE9B8;letter-spacing:1px;margin-top:2px}
.reveal .fact{font-family:'PretendardM';font-size:21px;color:#CFEAF3;margin-top:8px;line-height:1.3}
.wm{position:absolute;bottom:38px;right:30px;font-family:'Orbitron';font-weight:900;font-size:16px;letter-spacing:3px;color:rgba(220,235,240,.72)}
</style></head><body>
<div class="stage">
<div class="vig"></div><div class="scan"></div>
<div class="frame"></div><div class="brk tl"></div><div class="brk tr"></div><div class="brk bl"></div><div class="brk br"></div>
<div class="tick"></div>
<div class="scanline" id="scanline"></div>
<div class="reticle" id="reticle"><div class="lk" id="lk">SCANNING TARGET</div>
  <div class="c a"></div><div class="c b"></div><div class="c d"></div><div class="c e"></div></div>
<div class="bar" id="bar"><i></i><i></i><i></i><i></i></div>
<div class="unit"></div>
<div class="rec"><b>●</b> <span id="rec">REC 00:00:00</span></div>
<div class="tel">
  <div class="lab">DEPTH</div><div class="val big" id="depth">0 M</div>
  <div class="lab" style="margin-top:6px">TEMP</div><div class="val" id="temp">2.1°C</div>
  <div class="sub" id="coord"></div></div>
<svg class="radar" viewBox="0 0 120 120">
  <circle cx="60" cy="60" r="56" fill="none" stroke="rgba(80,220,240,.5)" stroke-width="1.5"/>
  <circle cx="60" cy="60" r="37" fill="none" stroke="rgba(80,220,240,.35)" stroke-width="1.5"/>
  <circle cx="60" cy="60" r="18" fill="none" stroke="rgba(80,220,240,.3)" stroke-width="1.5"/>
  <line id="sweep" x1="60" y1="60" x2="116" y2="60" stroke="#FF8A3D" stroke-width="2.5"/>
  <circle id="blip" cx="60" cy="60" r="3.5" fill="#FF8A3D" opacity="0"/>
  <circle cx="60" cy="60" r="3" fill="#FF8A3D"/></svg>
<div class="sonarlab">TACTICAL SONAR</div>
<div class="hookwrap" id="hookwrap"><div class="hook" id="hook"></div></div>
<div class="scanwrap" id="scanwrap"><div class="tag" id="stag"></div><div class="sub" id="ssub"></div></div>
<div class="reveal" id="reveal">
  <div class="lab" id="rlab">▶ SPECIES IDENTIFIED</div>
  <div class="name" id="rname"></div><div class="en" id="ren"></div>
  <div class="fact" id="rfact"></div></div>
<div class="wm"></div>
</div>
<script>
const C = /*CONFIG*/;
document.querySelector('.unit').textContent = C.unit;
document.querySelector('.wm').textContent = C.watermark;
const $=id=>document.getElementById(id);
function clamp(x,a,b){return Math.min(b,Math.max(a,x));}
function easeOut(x){return 1-Math.pow(1-x,3);}
function comma(n){return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g,',');}
function typed(str,ts,dur,t){const f=clamp((t-ts)/dur,0,1);return str.slice(0,Math.floor(str.length*f));}
function done(str,ts,dur,t){return (t-ts)>=dur;}
function caret(t){return (Math.floor(t*2)%2)?'<span class="car">▌</span>':'<span class="car" style="opacity:0">▌</span>';}
function dots(t){const n=1+Math.floor((t*1.6)%4);return ' '+'. '.repeat(n).trim();}
function tc(t){const s=Math.floor(t);const mm=String(Math.floor(s/60)).padStart(2,'0');const ss=String(s%60).padStart(2,'0');return `REC 00:${mm}:${ss}`;}

function render(t){
  const d0=C.d0, d1=C.d1, rs=C.revealStart, total=C.total;
  const inReveal = t>=rs;
  // --- 상시 텔레메트리 ---
  $('rec').textContent = tc(t);
  const dep = C.depthMax*easeOut(clamp(t/1.3,0,1));
  const jitter = t>1.3 ? Math.sin(t*7.0)*3 : 0;
  $('depth').textContent = comma(dep+jitter)+' M';
  $('temp').textContent = (C.tempC+Math.sin(t*3.1)*0.05).toFixed(1)+'°C';
  $('coord').textContent = 'LOCATING'+dots(t);
  // 진행바 (4분할)
  const frac=clamp(t/total,0,1);
  [...$('bar').children].forEach((el,i)=>el.className=((i+1)/4<=frac+1e-3)?'on':'');
  // 레이더 스윕 + 블립(리빌 임박 시 타깃 감지)
  const ang=(t*230)%360, rad=ang*Math.PI/180;
  $('sweep').setAttribute('x2',(60+56*Math.cos(rad)).toFixed(1));
  $('sweep').setAttribute('y2',(60+56*Math.sin(rad)).toFixed(1));
  if(t>d0){const ba=(t*230)%360;$('blip').setAttribute('opacity',(ba<40?0.9:0.15).toFixed(2));
    $('blip').setAttribute('cx',(60+30*Math.cos((-40)*Math.PI/180)).toFixed(1));
    $('blip').setAttribute('cy',(60+30*Math.sin((-40)*Math.PI/180)).toFixed(1));}
  // 스캔라인 (컷1~2)
  if(!inReveal){$('scanline').style.opacity=0.9;$('scanline').style.top=(((t%2.2)/2.2)*1248+16).toFixed(0)+'px';}
  else $('scanline').style.opacity=0;

  // --- 조준 레티클 ---
  const ret=$('reticle');
  if(t<d0){ret.style.opacity=clamp((t-0.4)/0.6,0,1)*0.35;ret.style.transform='translate(-50%,-50%) scale('+(1.15-0.15*easeOut(clamp((t-0.4)/0.8,0,1)))+')';
    ret.querySelectorAll('.c').forEach(c=>c.style.borderColor='#39E0F0');$('lk').style.opacity=0;}
  else if(!inReveal){ret.style.opacity=0.85;const pulse=1+Math.sin(t*6)*0.012;ret.style.transform='translate(-50%,-50%) scale('+pulse+')';
    ret.querySelectorAll('.c').forEach(c=>c.style.borderColor='#39E0F0');$('lk').style.opacity=1;$('lk').textContent='SCANNING TARGET';$('lk').style.color='#39E0F0';}
  else{const snap=1-easeOut(clamp((t-rs)/0.35,0,1))*0.06;ret.style.opacity=clamp(1-(t-rs-1.2)/0.6,0,1);ret.style.transform='translate(-50%,-50%) scale('+snap+')';
    ret.querySelectorAll('.c').forEach(c=>c.style.borderColor='#FF8A3D');$('lk').style.opacity=1;$('lk').textContent='● TARGET LOCKED';$('lk').style.color='#FF8A3D';}

  // --- 훅 (컷1: 타이핑 → 유지 → 컷1 끝 페이드아웃, 컷2·리빌서 숨김) ---
  const hw=$('hookwrap');
  if(t<d0){
    const fadeIn=clamp((t-0.2)/0.4,0,1);
    const fadeOut=clamp((d0-t)/0.7,0,1);   // 컷1 마지막 0.7s 페이드아웃 → 컷2 클린
    hw.style.opacity=Math.min(fadeIn,fadeOut);
    const tp=typed(C.hook,C.hookStart,C.hookDur,t);
    $('hook').innerHTML=tp+(done(C.hook,C.hookStart,C.hookDur,t)?'':caret(t));
  } else hw.style.opacity=0;

  // --- 스캔/분석 태그 (컷1·2), 리빌서 숨김 ---
  const sw=$('scanwrap');
  if(t<d0){sw.style.opacity=1;$('stag').textContent='SCANNING'+dots(t);
    $('ssub').style.opacity=(0.72+0.28*Math.abs(Math.sin(t*3)));$('ssub').textContent='미확인 생명체 감지';}
  else if(!inReveal){sw.style.opacity=1;$('stag').textContent='ANALYZING'+dots(t);
    const tp=typed(C.beat2,C.beat2Start,C.beat2Dur,t);
    $('ssub').style.opacity=1;$('ssub').innerHTML=tp+(done(C.beat2,C.beat2Start,C.beat2Dur,t)?'':caret(t));}
  else sw.style.opacity=0;

  // --- 리빌 패널 (컷3 슬라이드업 + 타이핑) ---
  const rv=$('reveal');
  if(inReveal){const p=clamp((t-rs)/0.5,0,1);rv.style.opacity=easeOut(p);
    rv.style.transform='translateY('+((1-easeOut(p))*44).toFixed(1)+'px)';
    $('rlab').style.opacity=(0.6+0.4*Math.abs(Math.sin(t*4)));
    const ntp=typed(C.revealName,C.nameStart,C.nameDur,t);
    $('rname').innerHTML=ntp+(done(C.revealName,C.nameStart,C.nameDur,t)?'':caret(t));
    $('ren').style.opacity=done(C.revealName,C.nameStart,C.nameDur,t)?1:0;
    $('ren').textContent=C.revealEn;
    const fStart=C.factStart,fDur=C.factDur;
    $('rfact').innerHTML=typed(C.revealFact,fStart,fDur,t)+((t>fStart&&!done(C.revealFact,fStart,fDur,t))?caret(t):'');
  } else {rv.style.opacity=0;}
}
window.render=render;
</script></body></html>"""


def _build_html(cfg: dict, work_dir: Path) -> Path:
    fonts_uri = _FONTS_DIR.resolve().as_uri()
    html = _TEMPLATE.replace("%FONTS%", fonts_uri).replace("/*CONFIG*/", json.dumps(cfg))
    path = work_dir / "hud_render.html"
    path.write_text(html, encoding="utf-8")
    return path


def _chromium_path() -> str | None:
    for p in _CHROMIUM_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def render_frames(html_path: Path, total: float, work_dir: Path,
                  fps: float = HUD_FPS) -> tuple[Path, int]:
    """render(t)를 fps로 샘플링해 투명 PNG 시퀀스를 만든다. (frames_dir, n_frames).

    html_path: window.render(t) 를 정의한 HTML (테마별로 상위에서 생성해 전달).
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"playwright 미가용: {e}") from e

    html = html_path.resolve()  # 상대경로는 file:// URI 불가 (CI base_dir='.' 폴백 원인)
    frames_dir = work_dir / "hud_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("seq_*.png"):
        old.unlink()

    n = max(1, math.ceil(total * fps) + 2)
    launch = {"args": ["--no-sandbox", "--disable-gpu", "--force-color-profile=srgb"]}
    exe = _chromium_path()
    if exe:
        launch["executable_path"] = exe

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch)
            page = browser.new_page(
                viewport={"width": CLIP_W, "height": CLIP_H}, device_scale_factor=1
            )
            page.goto(html.as_uri())
            page.wait_for_function("typeof window.render === 'function'")
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(250)  # 폰트 로드 안정화
            clip = {"x": 0, "y": 0, "width": CLIP_W, "height": CLIP_H}
            for i in range(n):
                t = i / fps
                page.evaluate("(t)=>window.render(t)", t)
                page.screenshot(path=str(frames_dir / f"seq_{i:05d}.png"),
                                omit_background=True, clip=clip)
            browser.close()
    except HudRenderError:
        raise
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"프레임 렌더 실패: {e}") from e

    if not any(frames_dir.glob("seq_*.png")):
        raise HudRenderError("생성된 프레임 없음")
    return frames_dir, n


def _overlay_sequence(base_video: str, frames_dir: Path, total: float,
                      work_dir: Path, fps: float = HUD_FPS) -> str:
    out = work_dir / "overlaid.mp4"
    seq = str(frames_dir / "seq_%05d.png")
    fc = ("[1:v]setpts=PTS-STARTPTS[hud];"
          "[0:v][hud]overlay=0:0:format=auto:eof_action=repeat[o]")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-i", base_video,
           "-framerate", str(fps), "-i", seq,
           "-filter_complex", fc, "-map", "[o]",
           "-t", f"{total:.3f}",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise HudRenderError(f"HUD 시퀀스 합성 실패: {proc.stderr[-500:]}")
    return str(out)


FONTS_URI = _FONTS_DIR.resolve().as_uri()


def fonts_face_css() -> str:
    """엔드카드 등 다른 HTML 렌더에서 재사용할 @font-face 블록 (절대 file:// 경로)."""
    u = FONTS_URI
    return (
        f"@font-face{{font-family:'Orbitron';src:url('{u}/Orbitron.ttf');font-weight:900}}"
        f"@font-face{{font-family:'Rajdhani';src:url('{u}/Rajdhani-Bold.ttf');font-weight:700}}"
        f"@font-face{{font-family:'STM';src:url('{u}/ShareTechMono.ttf')}}"
        f"@font-face{{font-family:'BHS';src:url('{u}/BlackHanSans.ttf')}}"
        f"@font-face{{font-family:'Pretendard';src:url('{u}/Pretendard-Black.woff2');font-weight:900}}"
        f"@font-face{{font-family:'PretendardM';src:url('{u}/Pretendard-Medium.woff2')}}"
    )


def render_static(full_html: str, out_png: str, work_dir: str,
                  name: str = "static", transparent: bool = False) -> str:
    """단일 정지 HTML을 PNG로 렌더 (transparent=True면 투명 배경 오버레이). 실패 시 HudRenderError."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"playwright 미가용: {e}") from e

    work = Path(work_dir)
    html_path = (work / f"{name}.html").resolve()  # 상대경로 → file:// URI 불가 방지
    html_path.write_text(full_html, encoding="utf-8")
    launch = {"args": ["--no-sandbox", "--disable-gpu", "--force-color-profile=srgb"]}
    exe = _chromium_path()
    if exe:
        launch["executable_path"] = exe
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch)
            page = browser.new_page(
                viewport={"width": CLIP_W, "height": CLIP_H}, device_scale_factor=1
            )
            page.goto(html_path.as_uri())
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(250)
            page.screenshot(path=out_png, omit_background=transparent,
                            clip={"x": 0, "y": 0, "width": CLIP_W, "height": CLIP_H})
            browser.close()
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"정지 렌더 실패: {e}") from e
    if not Path(out_png).exists():
        raise HudRenderError("정지 PNG 미생성")
    return out_png


# ═══════════════════ 스키매틱 테마 (흰/회색 도면 + 시안 소량) ═══════════════════
# 부위 콜아웃 슬롯 → 화면 좌표 (지시점x1,y1 / 꺾임x2,y2 / 라벨x lx / 정렬).
# 좌표는 '중앙 정렬된 피사체' 기준 근사 — 콜아웃은 컷2(분석 비트)에서만 잠깐 등장.
_SCHEM_SLOTS = {
    # 콜아웃은 상태카드(하단 ~y808↑) 위쪽에만 배치 → 겹침 방지.
    "left-mid": (175, 520, 120, 470, 40, "l"),
    "right-mid": (470, 600, 560, 555, 690, "r"),
    "right-low": (450, 700, 558, 672, 690, "r"),
    "left-low": (250, 690, 150, 662, 40, "l"),
    "top": (360, 300, 300, 250, 90, "l"),
}
_SCHEM_CONT = [(-100, 45, 34, 20), (-82, 56, 24, 13), (-85, 14, 7, 11), (-60, -20, 15, 24),
               (-44, 72, 10, 7), (14, 52, 17, 11), (20, 3, 20, 32), (46, 28, 12, 12),
               (96, 55, 44, 20), (78, 23, 10, 12), (108, 12, 14, 11), (120, -3, 17, 6),
               (134, -25, 17, 11), (140, 38, 4, 8)]


def _schem_is_land(lon: float, lat: float) -> bool:
    return any(((lon - cl) / rx) ** 2 + ((lat - cy) / ry) ** 2 <= 1.0
               for cl, cy, rx, ry in _SCHEM_CONT)


def _schem_map_svg(mk_lon: float, mk_lat: float) -> str:
    """단색 도트 월드맵 + '스캔' 표현. 좌표가 가상이므로 정점(핀) 대신 좌→우 스캔 스윕.

    스캔 밴드가 지나가는 열의 육지 도트를 밝게 처리해 '탐색 중' 느낌(정확한 위치 특정 회피).
    """
    dots = []
    for c in range(0, 61):
        lon = -180 + c * 6
        for r in range(0, 26):
            lat = 80 - r * 6
            x, y = lon + 180, 80 - lat
            if _schem_is_land(lon, lat):
                dots.append(f'<circle class="ld" data-x="{x}" cx="{x}" cy="{y}" r="1.7" '
                            f'fill="#EAF0F4" opacity="0.55"/>')
            else:
                dots.append(f'<circle cx="{x}" cy="{y}" r="0.7" fill="#94A2AC" opacity="0.12"/>')
    scan = (
        '<defs><linearGradient id="scg" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#43C8DA" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#43C8DA" stop-opacity="0.28"/></linearGradient></defs>'
        '<rect id="mapband" x="0" y="0" width="26" height="150" fill="url(#scg)"/>'
        '<line id="mapscan" x1="0" y1="0" x2="0" y2="150" stroke="#9BE8F2" stroke-width="1.4" opacity="0.9"/>'
    )
    return (f'<svg viewBox="0 0 360 150" preserveAspectRatio="xMidYMid meet" '
            f'style="width:100%;height:100%">{"".join(dots)}{scan}</svg>')


def _schem_callouts_html(callouts: list[dict]) -> str:
    parts = []
    for i, co in enumerate(callouts):
        slot = co.get("slot", "left-mid")
        x1, y1, x2, y2, lx, align = _SCHEM_SLOTS.get(slot, _SCHEM_SLOTS["left-mid"])
        title = _html_escape(co.get("title", ""))
        sub = _html_escape(co.get("sub", ""))
        w = abs(lx - x2)
        left = min(lx, x2)
        parts.append(
            f'<svg class="lead" viewBox="0 0 720 1280"><polyline id="lead{i}" '
            f'points="{x1},{y1} {x2},{y2} {lx},{y2}" fill="none" stroke="#EAF0F4" stroke-width="1.2"/>'
            f'<circle cx="{x1}" cy="{y1}" r="3.2" fill="none" stroke="#43C8DA" stroke-width="1.3"/></svg>'
            f'<div class="col {align}" id="col{i}" style="left:{left}px;top:{y2-30}px;width:{w}px">'
            f'<div class="ct">{title}</div><div class="cv">{sub}</div></div>'
        )
    return "".join(parts)


def _html_escape(s: str) -> str:
    import html as _h
    return _h.escape(s or "")


def _schem_ruler_html() -> str:
    s = ""
    for i in range(0, 9):
        y = 60 + i * 145
        col = "#43C8DA" if i == 4 else "rgba(234,240,244,.65)"
        s += f'<div class="rk" style="top:{y}px;background:{col}"></div>'
        s += f'<div class="rn" style="top:{y-9}px">{i}</div>'
    return s


_SCHEM_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"><style>
%FONTS%
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:720px;height:1280px;overflow:hidden;background:transparent}
.stage{position:relative;width:720px;height:1280px;overflow:hidden;font-family:'Rajdhani';color:#EAF0F4}
.vig{position:absolute;inset:0;background:radial-gradient(120% 92% at 50% 44%,transparent 48%,rgba(0,4,8,.5) 84%,rgba(0,3,6,.84) 100%)}
.grid{position:absolute;inset:0;opacity:.055;background:linear-gradient(#fff 1px,transparent 1px) 0 0/64px 64px,linear-gradient(90deg,#fff 1px,transparent 1px) 0 0/64px 64px}
.tgt{position:absolute;left:50%;top:470px;width:520px;height:520px;transform:translate(-50%,-50%);border-radius:50%;border:1px solid rgba(67,200,218,.13)}
.frame{position:absolute;inset:18px;border:1px solid rgba(234,240,244,.26)}
.brk{position:absolute;width:30px;height:30px;border:1.5px solid #EAF0F4}
.brk.c{border-color:#43C8DA}
.tl{top:12px;left:12px;border-right:0;border-bottom:0}.tr{top:12px;right:12px;border-left:0;border-bottom:0}
.bl{bottom:12px;left:12px;border-right:0;border-top:0}.br{bottom:12px;right:12px;border-left:0;border-top:0}
.unit{position:absolute;top:34px;left:40px;font-family:'Orbitron';font-weight:900;font-size:15px;letter-spacing:4px;color:#EAF0F4}
.rec{position:absolute;top:60px;left:40px;font-family:'STM';font-size:18px;color:#94A2AC;letter-spacing:1px}
.rec b{color:#43C8DA}
.tel{position:absolute;top:30px;right:40px;width:212px;text-align:right;border-top:1px solid rgba(234,240,244,.5);border-bottom:1px solid rgba(234,240,244,.5);padding:8px 0}
.tel .row{display:flex;justify-content:space-between;font-family:'STM';font-size:16px;line-height:1.5}
.tel .row .k{color:#5E6A73;letter-spacing:1px}.tel .row .v{color:#EAF0F4}
.tel .row .v.c{color:#43C8DA}
.rk{position:absolute;right:20px;width:12px;height:1px}
.rn{position:absolute;right:36px;font-family:'STM';font-size:12px;color:#5E6A73}
/* 생태 데이터 패널 (콜아웃 대체 — 부위 지시 대신 종 생태정보, 임의 종에도 정확)
   위치: 좌측 '상단' 코너(헤더 아래) — 중앙의 피사체를 가리지 않도록 상단으로 이동. */
.specimen{position:absolute;left:30px;top:92px;width:292px;padding:10px 13px 11px;
  background:rgba(6,14,20,.52);border:1px solid rgba(234,240,244,.26);border-left:2px solid #43C8DA;
  backdrop-filter:blur(3px);opacity:0}
.specimen .cbr{position:absolute;width:11px;height:11px;border:1.5px solid #43C8DA}
.specimen .a{top:-1px;left:-1px;border-right:0;border-bottom:0}.specimen .b{top:-1px;right:-1px;border-left:0;border-bottom:0}
.specimen .c{bottom:-1px;left:-1px;border-right:0;border-top:0}.specimen .d{bottom:-1px;right:-1px;border-left:0;border-top:0}
.sphead{font-family:'Orbitron';font-weight:900;font-size:13px;letter-spacing:3px;color:#43C8DA;margin-bottom:7px}
.sprow{display:flex;gap:10px;align-items:baseline;margin-top:5px}
.sprow .k{font-family:'Rajdhani';font-weight:700;font-size:11px;letter-spacing:2px;color:#7C8E98;
  text-transform:uppercase;width:62px;flex:none}
.sprow .v{font-family:'PretendardM';font-size:15px;color:#EAF0F4;line-height:1.25;word-break:keep-all}
.hookwrap{position:absolute;top:150px;left:40px;right:40px}
.hook{font-family:'BHS';font-size:52px;line-height:1.12;color:#fff;text-shadow:0 2px 10px rgba(0,0,0,.7);word-break:keep-all;text-wrap:pretty}
.hook .car{color:#43C8DA;font-weight:400}
.hrule{margin-top:14px;height:2px;background:linear-gradient(90deg,#43C8DA,rgba(234,240,244,.5) 40%,transparent)}
.mapwrap{position:absolute;left:36px;bottom:112px;width:270px}
.mlab{font-family:'STM';font-size:12px;letter-spacing:1px;color:#94A2AC;margin-bottom:6px}
.map{width:270px;height:118px;border:1px solid rgba(234,240,244,.22);padding:6px;background:rgba(8,12,16,.32)}
.dial{position:absolute;left:330px;bottom:150px;width:78px;height:78px}
.dlab{position:absolute;left:342px;bottom:132px;font-family:'Rajdhani';font-weight:700;font-size:11px;letter-spacing:2px;color:#94A2AC}
/* 리치 상태 카드 (item3) */
.status{position:absolute;bottom:322px;left:48px;right:48px;padding:14px 20px 16px;background:rgba(8,13,18,.5);border:1px solid rgba(234,240,244,.28);border-left:2px solid #43C8DA;backdrop-filter:blur(3px)}
.status .cbr{position:absolute;width:12px;height:12px;border:1.5px solid #43C8DA}
.status .tlc{top:-1px;left:-1px;border-right:0;border-bottom:0}.status .trc{top:-1px;right:-1px;border-left:0;border-bottom:0}
.status .blc{bottom:-1px;left:-1px;border-right:0;border-top:0}.status .brc{bottom:-1px;right:-1px;border-left:0;border-top:0}
.shead{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.schip{font-family:'STM';font-size:12px;letter-spacing:2px;color:#04121a;background:#43C8DA;padding:2px 8px}
.sbar{display:flex;gap:3px;flex:1}
.sbar i{flex:1;height:6px;background:rgba(234,240,244,.16)}
.sbar i.on{background:#43C8DA}
.spct{font-family:'STM';font-size:14px;color:#94A2AC;letter-spacing:1px}
.stag{font-family:'Orbitron';font-weight:900;font-size:27px;letter-spacing:5px;color:#EAF0F4;text-align:center}
/* 식별 서술(ANALYZING)은 앰버로 — 어두운 심해 위에서 '시스템 판독 중' 느낌을 강조하고 가독성↑.
   근접 경보 시에는 render(t)가 붉은색으로 전환. */
.ssub{font-family:'PretendardM';font-weight:500;font-size:25px;color:#FFC24D;margin-top:11px;text-align:center;min-height:32px;text-shadow:0 2px 6px rgba(0,0,0,.75);word-break:keep-all;text-wrap:pretty}
.reveal{position:absolute;left:34px;right:34px;bottom:118px;border:1px solid rgba(234,240,244,.5);border-left:3px solid #43C8DA;padding:18px 22px;background:rgba(8,12,16,.52);backdrop-filter:blur(4px)}
.reveal .rtag{font-family:'STM';font-size:15px;letter-spacing:3px;color:#43C8DA}
.reveal .rname{font-family:'BHS';font-size:56px;color:#fff;margin-top:6px;line-height:1;word-break:keep-all}
.reveal .rname .car{color:#43C8DA}
.reveal .rsci{margin-top:8px}
.reveal .rsci .en{font-family:'Orbitron';font-weight:900;font-size:17px;letter-spacing:1px;color:#94A2AC}
.reveal .rsci .sci{font-family:'PretendardM';font-style:italic;font-size:18px;color:#B8C4CC;margin-left:8px}
.reveal .rfact{font-family:'PretendardM';font-size:20px;color:#D6E0E7;margin-top:10px;word-break:keep-all;text-wrap:pretty}
.wm{position:absolute;bottom:38px;right:34px;font-family:'Orbitron';font-weight:900;font-size:15px;letter-spacing:3px;color:rgba(234,240,244,.68)}
</style></head><body>
<div class="stage">
<div class="vig"></div><div class="grid"></div><div class="tgt"></div>
<div class="frame"></div><div class="brk tl c"></div><div class="brk tr"></div><div class="brk bl"></div><div class="brk br c"></div>
%RULER%
<div class="unit">ROV · DEEP DIVE UNIT</div>
<div class="rec"><b>●</b> <span id="rec">REC 00:00:00</span></div>
<div class="tel"><div class="row"><span class="k">DEPTH</span><span class="v c" id="depth">0 M</span></div>
  <div class="row"><span class="k">TEMP</span><span class="v" id="temp">2.1°C</span></div>
  <div class="row"><span class="k">POS</span><span class="v" id="coord"></span></div></div>
<div class="hookwrap" id="hookwrap"><div class="hook" id="hook"></div><div class="hrule"></div></div>
<div class="specimen" id="specimen">
  <div class="sphead">◈ SPECIMEN DATA</div>
  <div class="sprow"><span class="k">DEPTH</span><span class="v" id="spDepth"></span></div>
  <div class="sprow"><span class="k">HABITAT</span><span class="v" id="spHab"></span></div>
  <div class="sprow"><span class="k">DIET</span><span class="v" id="spDiet"></span></div>
  <div class="sprow"><span class="k">TRAIT</span><span class="v" id="spTrait"></span></div>
  <div class="cbr a"></div><div class="cbr b"></div><div class="cbr c"></div><div class="cbr d"></div>
</div>
<div class="mapwrap" id="mapwrap"><div class="mlab" id="mlab"></div><div class="map">%MAP%</div></div>
<svg class="dial" id="dial" viewBox="0 0 92 92">
  <circle cx="46" cy="46" r="44" fill="none" stroke="#EAF0F4" stroke-width="1"/>
  <circle cx="46" cy="46" r="28" fill="none" stroke="rgba(148,162,172,.5)" stroke-width="1"/>
  <line id="dsweep" x1="46" y1="46" x2="90" y2="46" stroke="#43C8DA" stroke-width="1.4"/>
  <circle cx="46" cy="46" r="2.4" fill="#43C8DA"/></svg>
<div class="dlab" id="dlab">SONAR</div>
<div class="status" id="status">
  <div class="shead"><span class="schip">STATUS</span>
    <div class="sbar" id="sbar"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
    <span class="spct" id="spct">00%</span></div>
  <div class="stag" id="stag">SCANNING</div><div class="ssub" id="ssub"></div>
  <div class="cbr tlc"></div><div class="cbr trc"></div><div class="cbr blc"></div><div class="cbr brc"></div>
</div>
<div class="reveal" id="reveal">
  <div class="rtag">▸ SPECIES IDENTIFIED</div>
  <div class="rname" id="rname"></div>
  <div class="rsci"><span class="en" id="ren"></span><span class="sci" id="rsci"></span></div>
  <div class="rfact" id="rfact"></div></div>
<div class="wm"></div>
</div>
<script>
const C = /*CONFIG*/;
document.querySelector('.wm').textContent = C.watermark;
$id=id=>document.getElementById(id);
function clamp(x,a,b){return Math.min(b,Math.max(a,x));}
function easeOut(x){return 1-Math.pow(1-x,3);}
function comma(n){return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g,',');}
function typed(s,ts,d,t){return s.slice(0,Math.floor(s.length*clamp((t-ts)/d,0,1)));}
function done(s,ts,d,t){return (t-ts)>=d;}
function caret(t){return (Math.floor(t*2)%2)?'<span class="car">▌</span>':'<span class="car" style="opacity:0">▌</span>';}
function dots(t){return ' '+'. '.repeat(1+Math.floor((t*1.6)%4)).trim();}
function tc(t){const s=Math.floor(t);return 'REC 00:'+String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}

function render(t){
  const d0=C.d0,d1=C.d1,rs=C.revealStart,total=C.total,inRev=t>=rs,c2=d0+d1;
  $id('rec').textContent=tc(t);
  $id('depth').textContent=comma(C.depthMax*easeOut(clamp(t/1.3,0,1))+(t>1.3?Math.sin(t*7)*3:0))+' M';
  $id('temp').textContent=(C.tempC+Math.sin(t*3.1)*0.05).toFixed(1)+'°C';
  $id('coord').textContent='LOCATING'+dots(t);   // 임의 좌표 금지 → 좌표 확인중 표기
  // 소나 다이얼 스윕
  const ang=(t*150)%360,rad=ang*Math.PI/180;
  $id('dsweep').setAttribute('x2',(46+44*Math.cos(rad)).toFixed(1));
  $id('dsweep').setAttribute('y2',(46+44*Math.sin(rad)).toFixed(1));
  // 월드맵 마커 깜박임 (컷1·2 표시, 리빌서 페이드)
  const mw=$id('mapwrap'),dl=$id('dial'),dlab=$id('dlab');
  const mapOn=inRev?clamp(1-(t-rs)/0.4,0,1):1;
  mw.style.opacity=mapOn;dl.style.opacity=mapOn;dlab.style.opacity=mapOn;
  $id('mlab').textContent=(C.distribution?('DISTRIBUTION · '+C.distribution):'GLOBAL DISTRIBUTION')+' · SCANNING';
  // 스캔 스윕(좌→우 반복) — 가짜 좌표 정점 대신 '탐색 중' 표현
  const sx=((t*70)%396)-18;                  // -18~378 이동(맵 밖에서 진입/이탈)
  $id('mapscan').setAttribute('x1',sx.toFixed(1));$id('mapscan').setAttribute('x2',sx.toFixed(1));
  $id('mapband').setAttribute('x',(sx-26).toFixed(1));
  // 스캔 통과 열의 육지 도트 하이라이트
  document.querySelectorAll('#mapwrap .ld').forEach(el=>{
    const dx=parseFloat(el.getAttribute('data-x'));
    el.setAttribute('opacity', (Math.abs(dx-sx)<14 ? 0.98 : 0.5).toFixed(2));});
  // 훅 (컷1 타이핑→페이드아웃)
  const hw=$id('hookwrap');
  if(t<d0){hw.style.opacity=Math.min(clamp((t-0.2)/0.4,0,1),clamp((d0-t)/0.7,0,1));
    $id('hook').innerHTML=typed(C.hook,C.hookStart,C.hookDur,t)+(done(C.hook,C.hookStart,C.hookDur,t)?'':caret(t));}
  else hw.style.opacity=0;
  // 생태 데이터 패널 (컷2 분석 비트) — 행별로 타이핑 등장, 컷2 끝 페이드아웃
  const sp=$id('specimen');
  if(!inRev && t>=d0){
    sp.style.opacity=Math.min(clamp((t-d0-0.15)/0.35,0,1), clamp((c2-t)/0.5,0,1));
    const rows=[['spDepth',C.spDepth],['spHab',C.spHabitat],['spDiet',C.spDiet],['spTrait',C.spTrait]];
    rows.forEach((r,i)=>{const st=d0+0.35+i*0.45;
      $id(r[0]).innerHTML=typed(String(r[1]),st,Math.max(0.35,String(r[1]).length*0.03),t);});
  } else sp.style.opacity=0;
  // 리치 상태 카드
  const sc=$id('status');
  if(!inRev){sc.style.opacity=1;
    const p=clamp(t/c2,0,1);const on=Math.round(p*8);
    [...$id('sbar').children].forEach((el,i)=>el.className=i<on?'on':'');
    $id('spct').textContent=String(Math.round(p*100)).padStart(2,'0')+'%';
    const alerting = C.alert && t>=C.alertAt && t<rs;   // 근접 경보(실제 근접·인지 한정)
    if(alerting){
      const ph=Math.abs(Math.sin(t*11));
      $id('stag').textContent='▲ 근접 경보';$id('stag').style.color='#FF4D4D';
      sc.style.borderLeftColor='#FF4D4D';
      sc.style.transform='translateX('+(Math.sin(t*46)*2.2).toFixed(1)+'px)';  // '쿵쿵' 미세 흔들림
      $id('ssub').style.color='#FF6B6B';$id('ssub').style.opacity=(0.7+0.3*ph);
      $id('ssub').textContent=C.alertText;
    } else if(t<d0){$id('stag').textContent='SCANNING'+dots(t);$id('stag').style.color='#EAF0F4';
      sc.style.borderLeftColor='#43C8DA';sc.style.transform='none';
      $id('ssub').style.color='#FFC24D';
      $id('ssub').style.opacity=(0.72+0.28*Math.abs(Math.sin(t*3)));$id('ssub').textContent='미확인 생명체 감지';}
    else{$id('stag').textContent='ANALYZING SPECIMEN';$id('stag').style.color='#EAF0F4';
      sc.style.borderLeftColor='#43C8DA';sc.style.transform='none';
      $id('ssub').style.color='#FFC24D';$id('ssub').style.opacity=1;
      $id('ssub').innerHTML=typed(C.beat2,C.beat2Start,C.beat2Dur,t)+(done(C.beat2,C.beat2Start,C.beat2Dur,t)?'':caret(t));}
  } else sc.style.opacity=clamp(1-(t-rs)/0.3,0,1);
  // 리빌
  const rv=$id('reveal');
  if(inRev){const p=clamp((t-rs)/0.5,0,1);rv.style.opacity=easeOut(p);
    rv.style.transform='translateY('+((1-easeOut(p))*40).toFixed(1)+'px)';
    $id('rname').innerHTML=typed(C.revealName,C.nameStart,C.nameDur,t)+(done(C.revealName,C.nameStart,C.nameDur,t)?'':caret(t));
    const nd=done(C.revealName,C.nameStart,C.nameDur,t);
    $id('ren').style.opacity=nd?1:0;$id('ren').textContent=C.revealEn.toUpperCase();
    $id('rsci').style.opacity=nd?1:0;$id('rsci').textContent=C.sciName;
    $id('rfact').innerHTML=typed(C.revealFact,C.factStart,C.factDur,t)+((t>C.factStart&&!done(C.revealFact,C.factStart,C.factDur,t))?caret(t):'');
  } else rv.style.opacity=0;
}
window.render=render;
</script></body></html>"""


def _schematic_html(cfg: dict, callouts: list[dict] | None = None) -> str:
    # callouts 인자는 하위호환 위해 유지(미사용) — 부위 지시선 대신 생태 데이터 패널 사용.
    html = (_SCHEM_TEMPLATE
            .replace("%FONTS%", fonts_face_css())
            .replace("%RULER%", _schem_ruler_html())
            .replace("%MAP%", _schem_map_svg(cfg["mapLon"], cfg["mapLat"]))
            .replace("/*CONFIG*/", json.dumps(cfg)))
    return html


THEME_DEFAULT = "schematic"


def apply_hud(base_video: str, caption: CaptionData, info: SpeciesInfo, watermark: str,
              cut_durations: list[float], work_dir: str,
              theme: str = THEME_DEFAULT, callouts: list[dict] | None = None) -> str:
    """애니메이션 HTML HUD를 영상 위에 합성 (PIL hud와 동일 시그니처 + theme/callouts).

    theme: 'schematic'(흰/회색 도면 + 시안 소량, 기본) | 'neon'(청록 SF).
    callouts: 카테고리가 제공한 부위 라벨 [{slot,title,sub}] (schematic 전용, 없으면 생략).
    실패 시 HudRenderError를 던진다 → pipeline이 PIL hud로 폴백.
    """
    work = Path(work_dir)
    cfg = _config(caption, info, watermark, cut_durations)
    total = float(cfg["total"])
    if theme == "schematic":
        html_str = _schematic_html(cfg, callouts or [])
        html_path = work / "hud_render.html"
        html_path.write_text(html_str, encoding="utf-8")
    else:
        html_path = _build_html(cfg, work)
    frames_dir, _n = render_frames(html_path, total, work)
    result = _overlay_sequence(base_video, frames_dir, total, work)
    log.info("HTML HUD 합성 완료(%s): %s (%.1fs, %d프레임)", theme, result, total, _n)
    return result
