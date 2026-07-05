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
    return {
        "d0": w[0][1] - w[0][0],
        "d1": w[1][1] - w[1][0],
        "total": w[2][1],
        "revealStart": w[2][0],
        "depthMax": _max_depth_num(info),
        "unit": "ROV · DEEP DIVE UNIT",
        "watermark": watermark,
        "lat": "34.21", "lon": "127.88",
        "hook": caption.hook_text or "",
        "beat2": beats[1],
        "revealName": name_ko.strip(),
        "revealEn": name_en.strip(),
        "revealFact": caption.reveal_fact or "",
    }


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
.scanwrap{position:absolute;bottom:262px;left:0;right:0;text-align:center}
.scanwrap .tag{font-family:'Orbitron';font-weight:900;font-size:30px;letter-spacing:6px;color:#39E0F0;text-shadow:0 0 14px rgba(57,224,240,.7)}
.scanwrap .sub{font-family:'Rajdhani';font-weight:700;font-size:18px;letter-spacing:2px;color:#FF8A3D;text-transform:uppercase;margin-top:8px;min-height:22px}
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
  $('temp').textContent = (2.1+Math.sin(t*3.1)*0.05).toFixed(1)+'°C';
  $('coord').textContent = C.lat+'°N  '+C.lon+'°E';
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
    const hdur=Math.max(0.6,C.hook.length*0.06);
    const fadeIn=clamp((t-0.2)/0.4,0,1);
    const fadeOut=clamp((d0-t)/0.7,0,1);   // 컷1 마지막 0.7s 페이드아웃 → 컷2 클린
    hw.style.opacity=Math.min(fadeIn,fadeOut);
    const tp=typed(C.hook,0.25,hdur,t);
    $('hook').innerHTML=tp+(done(C.hook,0.25,hdur,t)?'':caret(t));
  } else hw.style.opacity=0;

  // --- 스캔/분석 태그 (컷1·2), 리빌서 숨김 ---
  const sw=$('scanwrap');
  if(t<d0){sw.style.opacity=1;$('stag').textContent='SCANNING'+dots(t);
    $('ssub').style.opacity=(0.55+0.45*Math.abs(Math.sin(t*3)));$('ssub').textContent='UNKNOWN LIFEFORM DETECTED';}
  else if(!inReveal){sw.style.opacity=1;$('stag').textContent='ANALYZING'+dots(t);
    const tp=typed(C.beat2,d0+0.15,Math.max(0.8,C.beat2.length*0.05),t);
    $('ssub').style.opacity=1;$('ssub').innerHTML=tp+(done(C.beat2,d0+0.15,C.beat2.length*0.05,t)?'':caret(t));}
  else sw.style.opacity=0;

  // --- 리빌 패널 (컷3 슬라이드업 + 타이핑) ---
  const rv=$('reveal');
  if(inReveal){const p=clamp((t-rs)/0.5,0,1);rv.style.opacity=easeOut(p);
    rv.style.transform='translateY('+((1-easeOut(p))*44).toFixed(1)+'px)';
    $('rlab').style.opacity=(0.6+0.4*Math.abs(Math.sin(t*4)));
    const nDur=Math.max(0.5,C.revealName.length*0.08);
    const ntp=typed(C.revealName,rs+0.2,nDur,t);
    $('rname').innerHTML=ntp+(done(C.revealName,rs+0.2,nDur,t)?'':caret(t));
    $('ren').style.opacity=done(C.revealName,rs+0.2,nDur,t)?1:0;
    $('ren').textContent=C.revealEn;
    const fStart=rs+0.25+nDur;const fDur=Math.max(0.6,C.revealFact.length*0.045);
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


def render_frames(cfg: dict, work_dir: Path, fps: float = HUD_FPS) -> tuple[Path, int]:
    """render(t)를 fps로 샘플링해 투명 PNG 시퀀스를 만든다. (frames_dir, n_frames)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"playwright 미가용: {e}") from e

    html = _build_html(cfg, work_dir)
    frames_dir = work_dir / "hud_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    for old in frames_dir.glob("seq_*.png"):
        old.unlink()

    total = float(cfg["total"])
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
                  name: str = "static") -> str:
    """단일 정지 HTML을 불투명 PNG로 렌더 (엔드카드 등). 실패 시 HudRenderError."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"playwright 미가용: {e}") from e

    work = Path(work_dir)
    html_path = work / f"{name}.html"
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
            page.screenshot(path=out_png,
                            clip={"x": 0, "y": 0, "width": CLIP_W, "height": CLIP_H})
            browser.close()
    except Exception as e:  # noqa: BLE001
        raise HudRenderError(f"정지 렌더 실패: {e}") from e
    if not Path(out_png).exists():
        raise HudRenderError("정지 PNG 미생성")
    return out_png


def apply_hud(base_video: str, caption: CaptionData, info: SpeciesInfo, watermark: str,
              cut_durations: list[float], work_dir: str) -> str:
    """애니메이션 HTML HUD를 영상 위에 합성 (PIL hud와 동일 시그니처).

    실패 시 HudRenderError를 던진다 → pipeline이 PIL hud로 폴백.
    """
    work = Path(work_dir)
    cfg = _config(caption, info, watermark, cut_durations)
    frames_dir, _n = render_frames(cfg, work)
    total = float(cfg["total"])
    result = _overlay_sequence(base_video, frames_dir, total, work)
    log.info("HTML HUD 합성 완료: %s (%.1fs, %d프레임)", result, total, _n)
    return result
