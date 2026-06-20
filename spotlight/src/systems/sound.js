// 사운드 (기획서 18번). HTML5 Audio 기반. BGM/효과음 on·off는 localStorage에 저장.
const LS = "spotlight_audio";
let bgm = null, curSrc = null, curVol = 0.5;
let pendingGesture = false; // 자동재생 차단으로 재생 보류 중 → 다음 사용자 제스처에 재생

function load() { try { return Object.assign({ bgm: true, sfx: true }, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) { return { bgm: true, sfx: true }; } }
function persist() { try { localStorage.setItem(LS, JSON.stringify(st)); } catch (e) {} }
const st = load();

export function isBgmOn() { return st.bgm; }
export function isSfxOn() { return st.sfx; }

// 자동재생이 차단되면 첫 사용자 제스처(터치·클릭·키)에서 현재 곡을 다시 재생.
function armGestureRetry() {
  if (pendingGesture) return;
  pendingGesture = true;
  const go = () => {
    pendingGesture = false;
    window.removeEventListener("pointerdown", go, true);
    window.removeEventListener("touchstart", go, true);
    window.removeEventListener("keydown", go, true);
    if (st.bgm && curSrc) playBgm(curSrc, curVol);
  };
  window.addEventListener("pointerdown", go, true);
  window.addEventListener("touchstart", go, true);
  window.addEventListener("keydown", go, true);
}

// BGM 재생(곡 전환 포함). 끈 상태면 곡만 기억하고 재생은 보류.
// 자동재생이 막히면(브라우저 정책) 다음 사용자 제스처에서 자동으로 재시도한다.
export function playBgm(src, vol = 0.5) {
  curSrc = src; curVol = vol;
  if (!st.bgm) return;
  try {
    if (!bgm || bgm.__src !== src) {
      if (bgm) bgm.pause();
      bgm = new Audio(src); bgm.__src = src; bgm.loop = true;
    }
    bgm.volume = vol;
    const p = bgm.play();
    if (p && p.catch) p.catch(() => armGestureRetry()); // 차단되면 제스처 대기
  } catch (e) { armGestureRetry(); }
}

export function stopBgm() { try { if (bgm) { bgm.pause(); bgm.currentTime = 0; } } catch (e) {} curSrc = null; }

export function setBgmOn(on) {
  st.bgm = on; persist();
  if (on) { if (curSrc) playBgm(curSrc, curVol); }
  else { try { if (bgm) bgm.pause(); } catch (e) {} }
}
export function setSfxOn(on) { st.sfx = on; persist(); }

// 자동재생 차단 환경: 즉시 재생을 시도하고, 막히면 첫 제스처에서 재생(playBgm 내부 처리).
export function armBgm(src, vol = 0.5) { playBgm(src, vol); }

// 효과음 (끈 상태면 무시) — 파일(mp3) 기반. 합성 효과음은 아래 sfx() 사용.
export function playSfx(src, vol = 0.6) {
  if (!st.sfx) return;
  try { const a = new Audio(src); a.volume = vol; const p = a.play(); if (p && p.catch) p.catch(() => {}); } catch (e) {}
}

// ───────── Web Audio 합성 효과음 (별도 파일 불필요) ─────────
// 짧은 UI음·피드백음·박수/팡파레까지 코드로 생성한다. 사용자 제스처에서 호출되므로 컨텍스트가 깨어난다.
let actx = null;
function ac() {
  try {
    if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
    if (actx.state === "suspended") actx.resume().catch(() => {});
  } catch (e) { return null; }
  return actx;
}

// 단일 톤 (주파수·길이·음색·게인 + 짧은 어택/릴리즈 엔벨로프)
function tone(ctx, t0, freq, dur, { type = "triangle", gain = 0.16, glideTo = null } = {}) {
  const o = ctx.createOscillator(), g = ctx.createGain();
  o.type = type; o.frequency.setValueAtTime(freq, t0);
  if (glideTo) o.frequency.exponentialRampToValueAtTime(glideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g).connect(ctx.destination);
  o.start(t0); o.stop(t0 + dur + 0.02);
}

// 음 여러 개를 차례로 (아르페지오) — 팡파레·확인음 등
function seq(ctx, t0, notes, step, opt) { notes.forEach((f, i) => tone(ctx, t0 + i * step, f, opt.dur || step * 1.6, opt)); }

// 필터링한 화이트노이즈 버스트 (박수·환호 질감)
function applause(ctx, t0, dur = 1.2, gain = 0.22) {
  const len = Math.floor(ctx.sampleRate * dur);
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len); // 점점 잦아듦
  const src = ctx.createBufferSource(); src.buffer = buf;
  const bp = ctx.createBiquadFilter(); bp.type = "bandpass"; bp.frequency.value = 1800; bp.Q.value = 0.7;
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.linearRampToValueAtTime(gain, t0 + 0.06);
  // 박수 특유의 잘게 떨리는 진폭
  for (let tt = 0.1; tt < dur; tt += 0.045) g.gain.linearRampToValueAtTime(gain * (0.45 + Math.random() * 0.55), t0 + tt);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(bp).connect(g).connect(ctx.destination);
  src.start(t0); src.stop(t0 + dur + 0.02);
}

const N = { C5: 523, D5: 587, E5: 659, G5: 784, A5: 880, C6: 1047, E6: 1319, G6: 1568, G4: 392, Eb4: 311, C4: 262, A4: 440 };

// 효과음 이름 → 합성 레시피
const RECIPES = {
  tap:    (c, t) => tone(c, t, 720, 0.05, { type: "triangle", gain: 0.10 }),
  select: (c, t) => seq(c, t, [N.E5, N.A5], 0.06, { type: "triangle", gain: 0.12, dur: 0.09 }),
  cancel: (c, t) => tone(c, t, 520, 0.10, { type: "sine", gain: 0.10, glideTo: 300 }),
  next:   (c, t) => seq(c, t, [N.C5, N.G5], 0.07, { type: "triangle", gain: 0.14, dur: 0.12 }),
  page:   (c, t) => tone(c, t, 1100, 0.035, { type: "sine", gain: 0.06 }),
  save:   (c, t) => seq(c, t, [N.G5, N.C6], 0.07, { type: "sine", gain: 0.12, dur: 0.11 }),
  good:   (c, t) => seq(c, t, [N.E5, N.G5], 0.09, { type: "triangle", gain: 0.16, dur: 0.18 }),
  best:   (c, t) => { seq(c, t, [N.C5, N.E5, N.G5, N.C6], 0.085, { type: "square", gain: 0.13, dur: 0.22 }); applause(c, t + 0.18, 1.0, 0.16); },
  bad:    (c, t) => seq(c, t, [N.G4, N.Eb4, N.C4], 0.13, { type: "sine", gain: 0.13, dur: 0.30 }),
  bonus:  (c, t) => seq(c, t, [N.C6, N.E6, N.G6], 0.06, { type: "sine", gain: 0.12, dur: 0.20 }),
  award:  (c, t) => { seq(c, t, [N.G4, N.C5, N.E5, N.G5], 0.11, { type: "square", gain: 0.13, dur: 0.28 }); applause(c, t + 0.3, 1.4, 0.22); },
  warn:   (c, t) => { tone(c, t, N.A4, 0.12, { type: "sine", gain: 0.10 }); tone(c, t + 0.16, N.A4, 0.12, { type: "sine", gain: 0.10 }); },
};

// 합성 효과음 재생 (이름). 효과음이 꺼져 있으면 무시.
export function sfx(name) {
  if (!st.sfx) return;
  const ctx = ac(); if (!ctx) return;
  const r = RECIPES[name]; if (!r) return;
  try { r(ctx, ctx.currentTime + 0.001); } catch (e) {}
}
