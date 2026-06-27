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
  DODGE_TRAVEL_SEC, DODGE_HIT_UNITS, DODGE_SCORE, DODGE_FROM_WALL, DODGE_CHANCE, DODGE_GAP_SEC,
} from './config.js';

const $ = (id) => document.getElementById(id);

// ---- 전역 ----
const canvas = $('game');
const video = $('cam');
const renderer = new Renderer(canvas, video);
const pose = new PoseTracker(video);
const sfx = new Sfx();
// 스테이지별 배경음악(0=스테이지1, 1=스테이지2, 2=스테이지3)
const bgmTracks = [$('bgm'), $('bgm2'), $('bgm3')];
bgmTracks.forEach((a) => { a.volume = 0.5; });
let curStage = -1;
let muted = false;

// wallIndex → 스테이지(21벽을 3등분: 0~6 / 7~13 / 14~20)
function stageOf(wallIndex) { return Math.min(2, Math.floor(wallIndex / 7)); }

function bgmStopAll() { bgmTracks.forEach((a) => a.pause()); }
function bgmPlayStage(s) {
  if (muted) return;
  bgmTracks.forEach((a, i) => { if (i !== s) a.pause(); });
  if (s !== curStage) { try { bgmTracks[s].currentTime = 0; } catch (e) {} }
  curStage = s;
  try { bgmTracks[s].play().catch(() => {}); } catch (e) {}
}

// 충돌 마스크용 오프스크린
const bodyMaskCanvas = Object.assign(document.createElement('canvas'), { width: MASK_W, height: MASK_H });
const bodyMaskCtx = bodyMaskCanvas.getContext('2d', { willReadFrequently: true });
const wallMaskCanvas = Object.assign(document.createElement('canvas'), { width: MASK_W, height: MASK_H });

// 디버그: ?synth → 웹캠/모델 없이 합성 포즈로 게임 흐름·렌더 확인(카메라 없는 미리보기)
const SYNTH = new URLSearchParams(location.search).has('synth');

let state = 'TITLE';
let players = [];        // {name, score, perfects, walls}
let groundY = 0.90;      // 바닥선(정규화 y) — 캘리브레이션에서 발 높이로 보정
let headY = 0.18;        // 머리선(정규화 y) — 캘리브레이션에서 코 높이로 보정
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

// ---- 캘리브레이션 상태 ----
const calib = { progress: 0, done: false, tStart: 0, status: '' };

// ====== 버튼 이벤트 ======
$('btnStart').onclick = () => { sfx.resume(); tryLockLandscape(); gotoRegister(); };

// 가로 고정 시도(지원 기기에서만). 실패하면 회전 안내(#rotateGate)가 대신 처리.
async function tryLockLandscape() {
  try {
    const el = document.documentElement;
    if (el.requestFullscreen) await el.requestFullscreen();
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    if (screen.orientation && screen.orientation.lock) await screen.orientation.lock('landscape');
  } catch (e) { /* 미지원(예: iOS) → 회전 안내로 유도 */ }
}
$('btnHow').onclick = () => { showScreen('how'); state = 'HOW'; };
$('btnHowBack').onclick = () => { showScreen('title'); state = 'TITLE'; };
$('btnRegister').onclick = () => {
  const name = ($('playerName').value || '').trim() || `도전자 ${players.length + 1}`;
  current = { name, score: 0, perfects: 0, walls: 0 };
  startCalibration();
};
$('btnCalibStart').onclick = () => beginCalibScan();
$('btnCalibSkip').onclick = () => finishCalibration();
$('btnNextPlayer').onclick = () => { players.push(current); gotoRegister(); };
$('btnRetry').onclick = () => { startCalibration(); };
$('btnRestartAll').onclick = () => { players = []; showScreen('title'); state = 'TITLE'; setHud(false); };
$('btnErrorRetry').onclick = () => location.reload();
$('btnMute').onclick = () => {
  muted = !muted;
  sfx.enabled = !muted;
  sfx.resume();
  if (muted) bgmStopAll();
  else if (state === 'PLAY') bgmPlayStage(Math.max(0, curStage));
  $('btnMute').textContent = muted ? '🔇' : '🔊';
};

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

// ====== 캘리브레이션 (전신 감지되면 자동 통과 · 절대 멈추지 않음) ======
function startCalibration() {
  $('calibTitle').textContent = `${current.name} · 자세 준비`;
  $('btnCalibSkip').classList.add('hidden');
  showScreen('calib');
  state = 'CALIB';
  setHud(false);
}

function beginCalibScan() {
  calib.progress = 0; calib.done = false; calib.tStart = performance.now() / 1000;
  calib.feet = []; calib.heads = []; calib.prev = null;
  calib.status = 'T자로 팔 벌리고 가만히 서주세요';
  hideAllScreens();
  $('overlay').style.pointerEvents = 'none';
  $('btnCalibSkip').classList.add('hidden');
  state = 'CALIB_RUN';
}

function vget(i) { return (landmarks && landmarks[i]) ? (landmarks[i].visibility ?? 1) : 0; }

// 양 발목 평균 y(정규화). 둘 다 안 보이면 null
function ankleY() {
  const la = vget(LM.L_ANKLE) >= 0.3, ra = vget(LM.R_ANKLE) >= 0.3;
  if (la && ra) return (landmarks[LM.L_ANKLE].y + landmarks[LM.R_ANKLE].y) / 2;
  if (la) return landmarks[LM.L_ANKLE].y;
  if (ra) return landmarks[LM.R_ANKLE].y;
  return null;
}

function isFullBodyVisible() {
  if (!landmarks) return false;
  const head = vget(LM.NOSE) >= 0.3;
  const sh = vget(LM.L_SHOULDER) >= 0.3 && vget(LM.R_SHOULDER) >= 0.3;
  const hip = vget(LM.L_HIP) >= 0.3 && vget(LM.R_HIP) >= 0.3;
  const ay = ankleY();
  const feet = ay !== null && ay < 0.985;
  return head && sh && hip && feet;
}

// 직전 프레임 대비 주요 관절 평균 이동량(정규화) → 움직임 측정. 작을수록 정지.
function bodyMotion() {
  if (!landmarks || !calib.prev) return 1;
  const idx = [LM.NOSE, LM.L_SHOULDER, LM.R_SHOULDER, LM.L_HIP, LM.R_HIP, LM.L_WRIST, LM.R_WRIST, LM.L_ANKLE, LM.R_ANKLE];
  let s = 0, n = 0;
  for (const i of idx) {
    const a = landmarks[i], b = calib.prev[i];
    if (a && b) { s += Math.hypot(a.x - b.x, a.y - b.y); n++; }
  }
  return n ? s / n : 1;
}

function calibReason() {
  if (!landmarks) return '사람이 안 보여요 — 카메라 앞에 서주세요';
  if (vget(LM.NOSE) < 0.3 || vget(LM.L_SHOULDER) < 0.3 || vget(LM.R_SHOULDER) < 0.3) return '머리와 어깨가 화면에 보이게';
  if (vget(LM.L_HIP) < 0.3 || vget(LM.R_HIP) < 0.3) return '허리까지 화면에 들어오게';
  const ay = ankleY();
  if (ay === null) return '👣 발끝까지 보이게 — 뒤로 한 걸음!';
  if (ay >= 0.985) return '👣 발이 화면 아래에 잘려요 — 살짝 뒤로!';
  return '발끝까지 보이게 서주세요';
}

function updateCalibScan(t, dt) {
  const vis = isFullBodyVisible();
  const motion = bodyMotion();
  const stable = vis && (SYNTH || motion < 0.016); // 충분히 멈춰 있어야 측정(합성모드는 면제)
  if (stable) {
    calib.progress = Math.min(1, calib.progress + dt / 2.0); // ~2초 가만히 → 완료
    calib.status = '좋아요! 그대로 멈춰요…';
    const ay = ankleY();
    if (ay !== null) calib.feet.push(ay);
    if (vget(LM.NOSE) >= 0.3) calib.heads.push(landmarks[LM.NOSE].y);
  } else if (vis) {
    calib.progress = Math.max(0, calib.progress - dt / 0.6); // 움직이면 빠르게 감소
    calib.status = '✋ 움직이지 말고 가만히! (정확히 측정 중)';
  } else {
    calib.progress = Math.max(0, calib.progress - dt / 0.7);
    calib.status = calibReason();
  }
  // 움직임 측정용 스냅샷
  if (landmarks) calib.prev = landmarks.map((p) => ({ x: p.x, y: p.y }));
  // 5초 지나도 안 끝나면 수동 시작 버튼 노출(절대 막히지 않게)
  if (t - calib.tStart > 5) $('btnCalibSkip').classList.remove('hidden');
  if (calib.progress >= 1 && !calib.done) {
    calib.done = true;
    // 측정한 발/머리 높이의 중앙값으로 확정(움직임 적은 마지막 구간 위주)
    const med = (arr, fb) => { if (!arr || !arr.length) return fb; const s = [...arr].sort((a, b) => a - b); return s[s.length >> 1]; };
    groundY = Math.min(0.985, Math.max(0.6, med(calib.feet, groundY)));
    headY = Math.min(groundY - 0.25, Math.max(0.02, med(calib.heads, headY)));
    sfx.go();
    finishCalibration();
  }
}

function finishCalibration() {
  $('btnCalibSkip').classList.add('hidden');
  startPractice();
}

// ====== 연습 + 본게임 ======
function startPractice() {
  curStage = -1; bgmPlayStage(0);
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
  current.dodgeCombo = 0;
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
  // 스테이지별 배경음악 전환(연습은 스테이지1 유지)
  if (!g.practice) bgmPlayStage(stageOf(g.wallIndex));
  // 댄스 벽이면 가운데 라운드 표시를 비우고(날아오는 제목이 대신), 아니면 ROUND 표시
  $('hudRound').textContent = g.practice ? '연습' : (wall.title ? '🎵 댄스' : `ROUND ${wall.level}`);
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

// 마스크 좌표계의 구멍(화면 wallGeom과 동일 비율 — 측정된 몸 길이 + 여유에 맞춤).
function maskGeom() {
  const H = MASK_H, pad = 0.06;
  const footY = Math.min(0.99, groundY + pad);
  const topMin = 0.03;
  const bodyFitS = Math.max(8, ((groundY - headY) + 2 * pad) * H / 4.3);
  const maxS = (footY - topMin) * H / 4.8;
  const S = Math.min(bodyFitS, maxS);
  const cy = footY * H - 2.2 * S;
  return { cx: MASK_W / 2, cy, S, VH: S * 1.7 };
}

function applyGrade(grade, wall) {
  const scoring = !g.practice;
  if (scoring) current.walls++;
  // 연출 — 고정 구멍 위치에서 이펙트
  const screenGeom = renderer.wallGeom(groundY, headY);
  renderer.tintSkeleton(grade.color, 0.7);
  if (grade.grade === 'CRASH') {
    renderer.setFlash('#ff3030');
    renderer.explode(screenGeom.cx, screenGeom.cy, { emojis: ['💥', '😵', '💫', '🌀', '🤡'] });
    sfx.crash();
    shakeScreen(true);
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

// 일반 배너(등급 외 — 장애물 결과 등)
function bannerText(text, color) {
  const el = $('grade');
  el.textContent = text;
  el.style.color = color;
  el.classList.remove('hidden');
  el.style.animation = 'none'; el.offsetHeight; el.style.animation = '';
  clearTimeout(showGradeText._t);
  showGradeText._t = setTimeout(() => el.classList.add('hidden'), 900);
}

function shakeScreen(big = false) {
  const app = $('app');
  const cls = big ? 'shake-big' : 'shake';
  app.classList.remove('shake', 'shake-big'); app.offsetHeight; app.classList.add(cls);
  setTimeout(() => app.classList.remove(cls), big ? 520 : 420);
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
  bgmStopAll(); curStage = -1;
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
  if (SYNTH) window.__hd = { state, phase: g.phase, life: current && current.life, score: current && current.score };

  renderer.drawCamera();

  if (state === 'CALIB_RUN') {
    renderer.drawSkeleton(landmarks);
    renderer.drawCalibUI(calib.progress, calib.status, t, groundY, headY);
    updateCalibScan(t, dt);
  } else if (state === 'PLAY') {
    // 인식 후 게임 중에는 뼈대를 그리지 않음(깔끔) — 카메라 영상으로 직접 맞춤
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
    const geom = renderer.wallGeom(groundY, headY);
    renderer.drawWall(wall, geom, progress, t);
    if (wall.title) renderer.drawSongTitle(wall.title, wall.artist, el);
    renderer.drawPoseHint(poseHint(wall));
    // 양옆 빈 공간: 이번 동작/콤보 + 다음 포즈 미리보기
    const nextWall = (!g.practice && g.wallIndex + 1 < STAGE_WALLS.length) ? STAGE_WALLS[g.wallIndex + 1] : null;
    renderer.drawSidePanels({
      moveText: poseHint(wall),
      combo: current.combo || 0,
      next: nextWall ? { wall: nextWall, label: poseHint(nextWall) } : null,
    });
    if (progress >= 1 && !g.judged) {
      g.judged = true;
      judge();
      g.phase = 'gap';
      g.phaseStart = t;
    }
  } else if (g.phase === 'gap') {
    // 통과/충돌 후 잠깐 — 벽 사이에 가끔 장애물 피하기 이벤트
    if (t - g.phaseStart >= INTER_WALL_SEC) {
      if (shouldDodge()) startDodge(t);
      else advanceWall();
    }
  } else if (g.phase === 'dodge') {
    updateDodge(t);
  }
}

// ====== 장애물 피하기 ======
function shouldDodge() {
  return !g.practice && current.life > 0 && g.wallIndex >= DODGE_FROM_WALL && Math.random() < DODGE_CHANCE;
}

function startDodge(t) {
  // 후반일수록 더 많은 공이 연달아 날아오는 '웨이브'
  let count = 1;
  if (g.wallIndex >= 4 && Math.random() < 0.6) count = 2;
  if (g.wallIndex >= 8 && Math.random() < 0.5) count = 3;
  const dirs = [-1, 0, 1];
  const list = [];
  for (let i = 0; i < count; i++) {
    list.push({ start: undefined, resolved: false, dir: dirs[Math.floor(Math.random() * 3)] });
  }
  g.dodge = { list, index: 0, doneAt: 0 };
  g.phase = 'dodge';
}

function updateDodge(t) {
  const d = g.dodge;
  if (d.index >= d.list.length) {
    if (t - d.doneAt >= 0.45) advanceWall();
    return;
  }
  const ob = d.list[d.index];
  if (ob.start === undefined) {
    // 장애물 등장 순간의 내 위치를 표적으로 잠금 → 옆으로 비켜야 함
    const geom = landmarks ? renderer.playerCenter(landmarks) : { cx: renderer.W / 2, cy: renderer.H * 0.45, S: 80 };
    ob.tx = geom.cx; ob.ty = geom.cy; ob.S = Math.max(46, geom.S);
    // 진입 방향(좌/위/우)
    const off = renderer.W * 0.45 * ob.dir;
    ob.sx = Math.max(renderer.W * 0.05, Math.min(renderer.W * 0.95, ob.tx + off));
    ob.start = t;
    sfx.whoosh();
  }
  if (ob.resolved) {
    if (t - ob.resolvedAt >= DODGE_GAP_SEC) {
      d.index++;
      if (d.index >= d.list.length) d.doneAt = t;
    }
    return;
  }
  const p = Math.min(1, (t - ob.start) / DODGE_TRAVEL_SEC);
  renderer.drawObstacle(ob, p, t);
  const hint = ob.dir < 0 ? '⬅️ 오른쪽으로 피해!' : ob.dir > 0 ? '오른쪽에서 와요 — 왼쪽으로! ➡️' : '⚠️ 옆으로 피해!';
  renderer.drawPoseHint(hint);
  if (p >= 1) { ob.resolved = true; ob.resolvedAt = t; judgeDodge(ob); }
}

function judgeDodge(ob) {
  let hit = false;
  if (landmarks) {
    const geom = renderer.playerCenter(landmarks);
    const dxUnits = Math.abs(geom.cx - ob.tx) / ob.S;
    hit = dxUnits < DODGE_HIT_UNITS;
  }
  if (hit) {
    current.life = Math.max(0, current.life - 1);
    current.combo = 0;
    current.dodgeCombo = 0;
    renderer.setFlash('#ff3030');
    renderer.explode(ob.tx, ob.ty, { emojis: ['💥', '😵', '🌟', '😖', '🪐'], ring: '#ff8a3d' });
    sfx.bonk();
    shakeScreen(true);
    bannerText('맞았다! 💥', '#ff5c5c');
  } else {
    current.dodgeCombo = (current.dodgeCombo || 0) + 1;
    const pts = DODGE_SCORE + (current.dodgeCombo - 1) * 15; // 연속 회피 보너스
    current.score += pts;
    renderer.burst(ob.tx, ob.ty, '#ffd23f', 26);
    sfx.ding(current.dodgeCombo - 1);
    const cstr = current.dodgeCombo >= 2 ? ` x${current.dodgeCombo}` : '';
    bannerText(`피했다!${cstr} +${pts}`, '#57e389');
  }
  updateHud();
}

// 시작
window.addEventListener('click', () => sfx.resume(), { once: true });
boot();
loop();
