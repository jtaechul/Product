// ===== HoleDash · 메인 (상태 머신 + 게임 로직 + 화면 연결) =====
import { Renderer } from './render.js';
import { PoseTracker, dist, visible } from './pose.js';
import { Sfx } from './audio.js';
import { buildWallMask } from './walls.js';
import { drawBodyMask, computeCollisionRate, bodyThicknessFromShoulder } from './collision.js';
import {
  LM, MASK_W, MASK_H, STAGE_WALLS, PRACTICE_WALL, poseHint,
  gradeFromRate, comboMultiplier, START_LIFE, BASE_APPROACH_SEC, INTER_WALL_SEC,
  RANK_TITLES, CONSOLATION_TITLE,
} from './config.js';

const $ = (id) => document.getElementById(id);

// ---- 전역 ----
const canvas = $('game');
const video = $('cam');
const renderer = new Renderer(canvas, video);
const pose = new PoseTracker(video);
const sfx = new Sfx();

// 충돌 마스크용 오프스크린
const bodyMaskCanvas = Object.assign(document.createElement('canvas'), { width: MASK_W, height: MASK_H });
const bodyMaskCtx = bodyMaskCanvas.getContext('2d', { willReadFrequently: true });
const wallMaskCanvas = Object.assign(document.createElement('canvas'), { width: MASK_W, height: MASK_H });

// 디버그: ?synth → 웹캠/모델 없이 합성 포즈로 게임 흐름·렌더 확인(카메라 없는 미리보기)
const SYNTH = new URLSearchParams(location.search).has('synth');

let state = 'TITLE';
let players = [];        // {name, score, perfects, walls}
let current = null;      // 현재 플레이어
let landmarks = null;
let lastTime = performance.now() / 1000;

// 게임 진행 상태
const g = {
  wallIndex: 0,
  wallStart: 0,
  approachSec: 4,
  phase: 'idle',        // countdown | approach | gap | done
  phaseStart: 0,
  practice: false,
  lastGrade: null,
};

// ---- 화면 전환 ----
const SCREENS = ['title', 'how', 'register', 'calib', 'result', 'final', 'error', 'loading'];
function showScreen(name) {
  for (const s of SCREENS) $('screen-' + s).classList.toggle('hidden', s !== name);
  $('overlay').style.pointerEvents = name ? 'auto' : 'none';
}
function hideAllScreens() { for (const s of SCREENS) $('screen-' + s).classList.add('hidden'); }
function setHud(on) { $('hud').classList.toggle('hidden', !on); }

// ---- 캘리브레이션 데이터(흐름 게이트 + 신체 표시) ----
const calib = { phase: 0, samples: [], tStart: 0, shoulder: 0, height: 0 };

// ====== 버튼 이벤트 ======
$('btnStart').onclick = () => { sfx.resume(); gotoRegister(); };
$('btnHow').onclick = () => { showScreen('how'); state = 'HOW'; };
$('btnHowBack').onclick = () => { showScreen('title'); state = 'TITLE'; };
$('btnRegister').onclick = () => {
  const name = ($('playerName').value || '').trim() || `도전자 ${players.length + 1}`;
  current = { name, score: 0, perfects: 0, walls: 0 };
  startCalibration();
};
$('btnCalibStart').onclick = () => beginCalibMeasure();
$('btnNextPlayer').onclick = () => { players.push(current); gotoRegister(); };
$('btnRetry').onclick = () => { startCalibration(); };
$('btnRestartAll').onclick = () => { players = []; showScreen('title'); state = 'TITLE'; setHud(false); };
$('btnErrorRetry').onclick = () => location.reload();

function gotoRegister() {
  $('playerName').value = '';
  showScreen('register');
  state = 'REGISTER';
  setHud(false);
}

// ====== 부팅: 모델 + 카메라 ======
// 합성 포즈(차렷 자세, 약간의 흔들림). 정규화 좌표(0~1).
function synthPose(t) {
  const lm = [];
  for (let i = 0; i < 33; i++) lm.push({ x: 0.5, y: 0.5, z: 0, visibility: 1 });
  const sway = Math.sin(t * 1.5) * 0.01;
  const cx = 0.5 + sway;
  const set = (i, x, y) => { lm[i] = { x, y, z: 0, visibility: 1 }; };
  // 팔을 천천히 내렸다↔벌렸다(T자) 반복 → 캘리브레이션·다양한 벽 입력 테스트
  const a = (Math.sin(t * 0.8) + 1) / 2; // 0=down, 1=T
  const wx = 0.12 + a * 0.30, wy = 0.57 - a * 0.27;
  const ex = 0.11 + a * 0.13, ey = 0.44 - a * 0.135;
  set(LM.NOSE, cx, 0.18);
  set(LM.L_SHOULDER, cx - 0.085, 0.30);
  set(LM.R_SHOULDER, cx + 0.085, 0.30);
  set(LM.L_ELBOW, cx - ex, ey);
  set(LM.R_ELBOW, cx + ex, ey);
  set(LM.L_WRIST, cx - wx, wy);
  set(LM.R_WRIST, cx + wx, wy);
  set(LM.L_HIP, cx - 0.05, 0.56);
  set(LM.R_HIP, cx + 0.05, 0.56);
  set(LM.L_KNEE, cx - 0.055, 0.74);
  set(LM.R_KNEE, cx + 0.055, 0.74);
  set(LM.L_ANKLE, cx - 0.06, 0.92);
  set(LM.R_ANKLE, cx + 0.06, 0.92);
  return lm;
}

async function boot() {
  if (SYNTH) { showScreen('title'); state = 'TITLE'; return; }
  showScreen('loading');
  try {
    $('loadingMsg').textContent = '카메라를 켜는 중…';
    await pose.startCamera();
    $('loadingMsg').textContent = '자세 인식 모델을 불러오는 중…';
    await pose.init();
    showScreen('title');
    state = 'TITLE';
  } catch (e) {
    console.error(e);
    let msg = '알 수 없는 오류가 발생했어요.';
    if (e && /Permission|NotAllowed/i.test(e.name + e.message)) msg = '카메라 권한이 거부됐어요. 브라우저 주소창의 카메라 아이콘에서 허용해 주세요.';
    else if (e && /NotFound/i.test(e.name)) msg = '카메라를 찾지 못했어요. 웹캠이 연결돼 있는지 확인해 주세요.';
    else if (e && /import|fetch|network/i.test(e.message || '')) msg = '인식 모델을 불러오지 못했어요(인터넷 연결 확인).';
    $('errorMsg').textContent = msg;
    showScreen('error');
    state = 'ERROR';
  }
}

// ====== 캘리브레이션 ======
function startCalibration() {
  calib.phase = 0; calib.samples = []; calib.shoulder = 0; calib.height = 0;
  $('ck-stand').textContent = '⬜ 차렷 자세 (키·어깨너비)';
  $('ck-stand').classList.remove('done');
  $('ck-tpose').textContent = '⬜ 양팔 벌리기 (윙스팬)';
  $('ck-tpose').classList.remove('done');
  $('calibTitle').textContent = `${current.name} · 신체 등록`;
  $('calibInstruction').textContent = '화면 가이드 안에 전신이 들어오게 서고, [측정 시작]을 누르세요';
  $('btnCalibStart').classList.remove('hidden');
  showScreen('calib');
  state = 'CALIB';
  setHud(false);
}

function beginCalibMeasure() {
  $('btnCalibStart').classList.add('hidden');
  calib.phase = 1; calib.samples = []; calib.tStart = performance.now() / 1000;
  $('calibInstruction').textContent = '차렷! 가만히 서주세요 (측정 중…)';
  hideAllScreens();           // 캔버스 가이드만 보이게
  $('overlay').style.pointerEvents = 'none';
  state = 'CALIB_RUN';
}

function updateCalib(t) {
  // 가이드 + 스캔라인은 loop의 draw에서 처리
  if (!landmarks) return;
  const ls = landmarks[LM.L_SHOULDER], rs = landmarks[LM.R_SHOULDER];
  const lw = landmarks[LM.L_WRIST], rw = landmarks[LM.R_WRIST];
  const nose = landmarks[LM.NOSE], la = landmarks[LM.L_ANKLE], ra = landmarks[LM.R_ANKLE];
  const elapsed = t - calib.tStart;

  if (calib.phase === 1) { // 차렷: 어깨너비/키
    if (ls && rs && visible(landmarks, LM.L_SHOULDER) && visible(landmarks, LM.R_SHOULDER)) {
      const sw = dist(ls, rs);
      let h = 0;
      if (nose && (la || ra)) {
        const ankleY = Math.max(la ? la.y : 0, ra ? ra.y : 0);
        h = Math.abs(ankleY - nose.y);
      }
      calib.samples.push({ sw, h });
    }
    if (elapsed > 2.4 && calib.samples.length > 8) {
      const swAvg = avg(calib.samples.map((s) => s.sw));
      const hAvg = avg(calib.samples.map((s) => s.h));
      calib.shoulder = swAvg; calib.height = hAvg;
      $('ck-stand').textContent = '✅ 차렷 자세 측정 완료';
      $('ck-stand').classList.add('done');
      // 2단계
      calib.phase = 2; calib.samples = []; calib.tStart = t;
    }
  } else if (calib.phase === 2) { // T자: 윙스팬
    if (lw && rw && visible(landmarks, LM.L_WRIST) && visible(landmarks, LM.R_WRIST)) {
      const span = dist(lw, rw);
      // 팔을 충분히 벌렸을 때만 유효 샘플
      if (span > calib.shoulder * 1.8) calib.samples.push(span);
    }
    if (elapsed > 2.4 && calib.samples.length > 6) {
      calib.wingspan = avg(calib.samples);
      $('ck-tpose').textContent = '✅ 양팔 벌리기 측정 완료';
      $('ck-tpose').classList.add('done');
      calib.phase = 3; calib.tStart = t;
    }
  } else if (calib.phase === 3) {
    if (elapsed > 1.0) startPractice();
  }
}

function avg(arr) { return arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0; }

// ====== 연습 + 본게임 ======
function startPractice() {
  g.practice = true;
  g.wallIndex = 0;
  current.life = START_LIFE;
  current.score = 0; current.perfects = 0; current.walls = 0;
  current.combo = 0;
  setHud(true);
  updateHud();
  beginCountdown('연습! 점수 미반영');
  state = 'PLAY';
}

function startMainGame() {
  g.practice = false;
  g.wallIndex = 0;
  current.score = 0; current.combo = 0; current.walls = 0; current.perfects = 0;
  current.life = START_LIFE;
  updateHud();
  beginCountdown('시작!');
}

function beginCountdown(label) {
  g.phase = 'countdown';
  g.phaseStart = performance.now() / 1000;
  g.countdownLabel = label;
}

function beginWall() {
  const wall = currentWall();
  g.phase = 'approach';
  g.wallStart = performance.now() / 1000;
  g.approachSec = BASE_APPROACH_SEC / wall.approachSpeed;
  g.judged = false;
  $('hudRound').textContent = g.practice ? '연습' : `ROUND ${wall.level}`;
  $('hudWall').textContent = g.practice ? '' : `벽 ${g.wallIndex + 1} / ${STAGE_WALLS.length}`;
}

function currentWall() {
  return g.practice ? PRACTICE_WALL : STAGE_WALLS[g.wallIndex];
}

// 판정: 마스크 좌표계로 충돌률 계산
function judge() {
  const wall = currentWall();
  let rate = 1.0;
  if (landmarks) {
    const geom = maskGeom();
    if (geom) {
      const t = (performance.now() / 1000) - g.wallStart;
      let extraRot = 0, extraDX = 0;
      if (wall.variant === 'rotate') extraRot = 0; // 판정 시점엔 거의 정렬
      if (wall.variant === 'moving') extraDX = Math.sin((performance.now() / 1000) * 2.2) * geom.S * 1.2 * 0.7;
      buildWallMask(wallMaskCanvas, wall, { ...geom, extraRot, extraDX });
      const wallMask = readMask(wallMaskCanvas);
      const thick = bodyThicknessFromShoulder(shoulderNorm());
      drawBodyMask(bodyMaskCtx, landmarks, thick);
      rate = computeCollisionRate(bodyMaskCtx, wallMask);
    }
  }
  const grade = gradeFromRate(rate);
  g.lastGrade = grade;
  applyGrade(grade, wall);
}

function readMask(maskCanvas) {
  const ctx = maskCanvas.getContext('2d', { willReadFrequently: true });
  const img = ctx.getImageData(0, 0, MASK_W, MASK_H).data;
  const mask = new Uint8Array(MASK_W * MASK_H);
  for (let i = 0, j = 3; i < mask.length; i++, j += 4) mask[i] = img[j] > 40 ? 1 : 0;
  return mask;
}

// 어깨너비(정규화)
function shoulderNorm() {
  const a = landmarks[LM.L_SHOULDER], b = landmarks[LM.R_SHOULDER];
  if (!a || !b) return 0.18;
  return Math.max(0.06, dist(a, b));
}

// 마스크 좌표계 geom(미러)
function maskGeom() {
  const ls = landmarks[LM.L_SHOULDER], rs = landmarks[LM.R_SHOULDER];
  const lh = landmarks[LM.L_HIP], rh = landmarks[LM.R_HIP];
  if (!ls || !rs) return null;
  const sx = (nx) => (1 - nx) * MASK_W;
  const sy = (ny) => ny * MASK_H;
  let cx, cy;
  if (lh && rh) {
    cx = (sx(ls.x) + sx(rs.x) + sx(lh.x) + sx(rh.x)) / 4;
    cy = (sy(ls.y) + sy(rs.y) + sy(lh.y) + sy(rh.y)) / 4;
  } else {
    cx = (sx(ls.x) + sx(rs.x)) / 2;
    cy = (sy(ls.y) + sy(rs.y)) / 2 + MASK_H * 0.15;
  }
  const S = shoulderNorm() * MASK_W;
  return { cx, cy, S, VH: S * 1.7 };
}

function applyGrade(grade, wall) {
  const scoring = !g.practice;
  if (scoring) current.walls++;
  // 연출
  const screenGeom = landmarks ? renderer.screenGeom(landmarks) : { cx: renderer.W / 2, cy: renderer.H / 2 };
  renderer.tintSkeleton(grade.color, 0.7);
  if (grade.grade === 'CRASH') {
    renderer.setFlash('#ff3030');
    sfx.grade('CRASH');
    shakeScreen();
    if (scoring) { current.life = Math.max(0, current.life - 1); current.combo = 0; }
  } else {
    renderer.burst(screenGeom.cx, screenGeom.cy, grade.color, grade.grade === 'PERFECT' ? 40 : 22);
    if (grade.grade === 'PERFECT') renderer.setFlash(grade.color);
    if (scoring) {
      if (grade.grade === 'PERFECT') current.perfects++;
      // 콤보(GREAT 이상)
      if (grade.grade === 'PERFECT' || grade.grade === 'GREAT') current.combo++;
      else current.combo = 0;
      const mult = comboMultiplier(current.combo);
      const speedBonus = Math.round(grade.score * 0.1 * (wall.approachSpeed - 1));
      current.score += Math.round(grade.score * mult) + Math.max(0, speedBonus);
    }
    sfx.grade(grade.grade, current.combo);
  }
  showGradeText(grade);
  updateHud();
}

function showGradeText(grade) {
  const el = $('grade');
  let txt = grade.label;
  if ((grade.grade === 'PERFECT' || grade.grade === 'GREAT') && current.combo >= 2) {
    txt += ` ×${comboMultiplier(current.combo)}`;
  }
  el.textContent = txt;
  el.style.color = grade.color;
  el.classList.remove('hidden');
  // 애니메이션 재시작
  el.style.animation = 'none'; el.offsetHeight; el.style.animation = '';
  clearTimeout(showGradeText._t);
  showGradeText._t = setTimeout(() => el.classList.add('hidden'), 900);
}

function shakeScreen() {
  const app = $('app');
  app.classList.remove('shake'); app.offsetHeight; app.classList.add('shake');
  setTimeout(() => app.classList.remove('shake'), 420);
}

function updateHud() {
  $('hudScore').textContent = current.score;
  $('hudCombo').textContent = current.combo >= 2 ? `🔥 ${current.combo} COMBO` : '';
  $('hudLife').textContent = g.practice ? '연습' : '❤️'.repeat(current.life) + '🖤'.repeat(Math.max(0, START_LIFE - current.life));
}

// 벽 완료 후 다음으로
function advanceWall() {
  if (g.practice) {
    // 연습 1벽 후 본게임
    g.practice = false;
    startMainGame();
    return;
  }
  if (current.life <= 0) { finishPlayer(); return; }
  g.wallIndex++;
  if (g.wallIndex >= STAGE_WALLS.length) { finishPlayer(true); return; }
  beginWall();
}

function finishPlayer(cleared = false) {
  state = 'RESULT';
  setHud(false);
  $('resultName').textContent = cleared ? `🎉 ${current.name} 완주!` : `${current.name} 종료`;
  $('resultScore').textContent = current.score;
  $('resultStats').innerHTML =
    `통과한 벽 <b>${current.walls}</b>개 · PERFECT <b>${current.perfects}</b>회<br>` +
    (cleared ? '모든 벽을 완주했어요! 🏁' : `라이프 소진 (벽 ${current.walls})`);
  if (cleared) sfx.fanfare();
  showScreen('result');
}

// 최종 순위 화면
function showFinal() {
  state = 'FINAL';
  const sorted = [...players].sort((a, b) => b.score - a.score);
  const list = $('rankingList');
  list.innerHTML = '';
  sorted.forEach((p, i) => {
    const li = document.createElement('li');
    if (i < 3) li.classList.add('rank-' + (i + 1));
    const title = i < 3 ? RANK_TITLES[i] : CONSOLATION_TITLE;
    li.innerHTML = `<span>${i + 1}. ${p.name} <span class="rank-title">${title}</span></span><span>${p.score}</span>`;
    list.appendChild(li);
  });
  showScreen('final');
}

// 결과 화면의 "다음 도전자" → 등록 / "시상식" 분기:
// 등록 화면에서 도전자가 없을 때 시상식으로 갈 수 있게 버튼 추가 동작
$('btnRegister').insertAdjacentHTML('afterend', '<button class="btn btn-ghost" id="btnFinish">그만하고 시상식 🏆</button>');
$('btnFinish').onclick = () => {
  if (current && state === 'REGISTER') { /* 등록 안 한 현재 입력은 버림 */ }
  if (players.length === 0) { alert('아직 완료한 도전자가 없어요!'); return; }
  showFinal();
};

// ====== 메인 루프 ======
function loop() {
  const nowMs = performance.now();
  const t = nowMs / 1000;
  const dt = Math.min(0.05, t - lastTime);
  lastTime = t;

  landmarks = SYNTH ? synthPose(t) : pose.detect(nowMs);

  renderer.drawCamera();

  if (state === 'CALIB_RUN') {
    const scanY = ((t * 0.6) % 1);
    renderer.drawCalibGuide(scanY);
    renderer.drawSkeleton(landmarks);
    updateCalib(t);
  } else if (state === 'PLAY') {
    renderer.drawSkeleton(landmarks);
    updatePlay(t);
  } else if (state === 'TITLE' || state === 'REGISTER' || state === 'CALIB') {
    renderer.drawSkeleton(landmarks);
  }

  renderer.updateEffects(dt);
  renderer.drawEffects();

  requestAnimationFrame(loop);
}

function updatePlay(t) {
  const wall = currentWall();
  if (g.phase === 'countdown') {
    const el = t - g.phaseStart;
    const n = Math.ceil(3 - el);
    if (el >= 3) { beginWall(); return; }
    renderer.drawBigText(n > 0 ? String(n) : 'GO', g.countdownLabel);
    if (n !== g.lastCount) { g.lastCount = n; if (n > 0) sfx.beep(); else sfx.go(); }
  } else if (g.phase === 'approach') {
    const el = t - g.wallStart;
    const progress = Math.min(1, el / g.approachSec);
    const geom = landmarks ? renderer.screenGeom(landmarks) : { cx: renderer.W / 2, cy: renderer.H / 2, S: 80, VH: 136 };
    renderer.drawWall(wall, geom, progress, t);
    renderer.drawPoseHint(poseHint(wall));
    if (progress >= 1 && !g.judged) {
      g.judged = true;
      judge();
      g.phase = 'gap';
      g.phaseStart = t;
    }
  } else if (g.phase === 'gap') {
    // 통과/충돌 후 잠깐 — 벽이 빠져나간 연출은 생략(이펙트만)
    if (t - g.phaseStart >= INTER_WALL_SEC) advanceWall();
  }
}

// 시작
window.addEventListener('click', () => sfx.resume(), { once: true });
boot();
loop();
