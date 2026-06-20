// 사운드 (기획서 18번). HTML5 Audio 기반. 브라우저 자동재생 정책 때문에 첫 사용자 입력에서 재생 시작.
let bgm = null;
let curSrc = null;

export function playBgm(src, vol = 0.5) {
  try {
    if (!bgm || curSrc !== src) {
      if (bgm) { bgm.pause(); }
      bgm = new Audio(src); bgm.loop = true; bgm.volume = vol; curSrc = src;
    }
    const p = bgm.play();
    if (p && p.catch) p.catch(() => {});
  } catch (e) {}
}

export function stopBgm() {
  try { if (bgm) { bgm.pause(); bgm.currentTime = 0; } } catch (e) {}
}

// 자동재생 차단 환경: 첫 사용자 제스처(탭/키)에서 재생. 이미 상호작용했다면 즉시 재생.
export function armBgm(src, vol = 0.5) {
  const go = () => { playBgm(src, vol); window.removeEventListener("pointerdown", go); window.removeEventListener("keydown", go); };
  window.addEventListener("pointerdown", go);
  window.addEventListener("keydown", go);
  playBgm(src, vol);
}
