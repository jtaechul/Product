// 사운드 (기획서 18번). HTML5 Audio 기반. BGM/효과음 on·off는 localStorage에 저장.
const LS = "spotlight_audio";
let bgm = null, curSrc = null, curVol = 0.5;

function load() { try { return Object.assign({ bgm: true, sfx: true }, JSON.parse(localStorage.getItem(LS) || "{}")); } catch (e) { return { bgm: true, sfx: true }; } }
function persist() { try { localStorage.setItem(LS, JSON.stringify(st)); } catch (e) {} }
const st = load();

export function isBgmOn() { return st.bgm; }
export function isSfxOn() { return st.sfx; }

// BGM 재생(곡 전환 포함). 끈 상태면 곡만 기억하고 재생은 보류.
export function playBgm(src, vol = 0.5) {
  curSrc = src; curVol = vol;
  if (!st.bgm) return;
  try {
    if (!bgm || bgm.__src !== src) {
      if (bgm) bgm.pause();
      bgm = new Audio(src); bgm.__src = src; bgm.loop = true;
    }
    bgm.volume = vol;
    const p = bgm.play(); if (p && p.catch) p.catch(() => {});
  } catch (e) {}
}

export function stopBgm() { try { if (bgm) { bgm.pause(); bgm.currentTime = 0; } } catch (e) {} curSrc = null; }

export function setBgmOn(on) {
  st.bgm = on; persist();
  if (on) { if (curSrc) playBgm(curSrc, curVol); }
  else { try { if (bgm) bgm.pause(); } catch (e) {} }
}
export function setSfxOn(on) { st.sfx = on; persist(); }

// 자동재생 차단 환경: 첫 사용자 제스처에서 재생. 이미 상호작용했다면 즉시 재생.
export function armBgm(src, vol = 0.5) {
  const go = () => { playBgm(src, vol); window.removeEventListener("pointerdown", go); window.removeEventListener("keydown", go); };
  window.addEventListener("pointerdown", go);
  window.addEventListener("keydown", go);
  playBgm(src, vol);
}

// 효과음 (끈 상태면 무시)
export function playSfx(src, vol = 0.6) {
  if (!st.sfx) return;
  try { const a = new Audio(src); a.volume = vol; const p = a.play(); if (p && p.catch) p.catch(() => {}); } catch (e) {}
}
