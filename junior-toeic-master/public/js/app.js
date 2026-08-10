// 점프리시 — 학생 화면 (모바일 세로)
// 첫 화면은 "무엇을 풀지 고르는 곳"이 아니라 "오늘 뭘 해야 하는지 알려주는 곳"이다.
// 파트를 직접 고르는 화면은 하단 '파트별' 탭으로 내렸다.
//
// 정답은 이 앱 어디에도 없다: 보기를 누르면 POST /api/check 가 채점·해설을 반환한다.
// M1은 로그인 전이라 학습 기록을 이 기기(localStorage)에 보관한다.
// M2에서 계정이 붙으면 서버의 user_skills·SRS 큐로 옮긴다.

import { conceptOf } from './concepts.js';

const view = document.getElementById('view');
const tabbar = document.getElementById('tabbar');

const PART_INFO = {
  L1: { name: '사진 고르기', desc: '문장을 듣고 알맞은 그림 찾기' },
  L2: { name: '질의응답', desc: '질문을 듣고 알맞은 대답 고르기' },
  L3: { name: '짧은 대화', desc: '두 사람의 대화 듣기' },
  L4: { name: '짧은 담화', desc: '안내 방송·이야기 듣기' },
  R1: { name: '문장 완성', desc: '빈칸에 알맞은 말 고르기' },
  R2: { name: '지문 완성', desc: '글의 빈칸 3개 채우기' },
  R3: { name: '독해', desc: '글을 읽고 물음에 답하기' },
};
const PARTS = Object.keys(PART_INFO);
const ACCENT_KO = { US: '미국 발음', UK: '영국 발음', AU: '호주 발음' };
const LETTERS = ['A', 'B', 'C', 'D'];
const WEAK_MIN = 3;      // 이만큼은 풀어야 실력을 판단한다
const WRONG_MAX = 30;    // 오답 보관 상한

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const todayKey = () => new Date().toLocaleDateString('sv');  // YYYY-MM-DD (로컬 기준)

// ---------- 학습 기록 ----------
const KEY = 'jumplish.progress.v1';
const blank = { parts: {}, wrong: [], days: [], set: null, setDate: null, setIdx: 0, exprs: [] };
let store;
try { store = { ...blank, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; }
catch { store = { ...blank }; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(store)); } catch { /* 저장 실패는 무시 */ } };

function recordAnswer(q, passage, correct) {
  const p = (store.parts[q.part] ||= { answered: 0, correct: 0 });
  p.answered += 1;
  if (correct) p.correct += 1;

  store.wrong = store.wrong.filter((w) => w.q.id !== q.id);
  if (!correct) store.wrong.unshift({ q, passage: passage || null, at: Date.now() });
  store.wrong = store.wrong.slice(0, WRONG_MAX);

  const d = todayKey();
  if (!store.days.includes(d)) { store.days.push(d); store.days = store.days.slice(-400); }
  save();
}

// 표현 주머니 — 틀린 문제의 표현은 담아 두고, 그 표현을 다시 맞히면 뺀다.
// 아이가 "내가 아직 모르는 표현"만 모아 보게 하려는 것이다.
function rememberExpr(q, expr, correct) {
  const i = store.exprs.findIndex((e) => e.id === q.id);
  if (correct) { if (i >= 0) store.exprs.splice(i, 1); }
  else {
    const item = { id: q.id, part: q.part, en: expr.en, ko: expr.ko, at: Date.now() };
    if (i >= 0) store.exprs[i] = item; else store.exprs.unshift(item);
    store.exprs = store.exprs.slice(0, 60);
  }
  save();
}

function streakDays() {
  if (!store.days.length) return 0;
  const set = new Set(store.days);
  let n = 0;
  const cur = new Date();
  if (!set.has(todayKey())) cur.setDate(cur.getDate() - 1);  // 오늘 아직 안 했으면 어제부터 센다
  for (;;) {
    if (!set.has(cur.toLocaleDateString('sv'))) break;
    n += 1;
    cur.setDate(cur.getDate() - 1);
  }
  return n;
}

// 이번 주(월~일) 중 학습한 날. 숫자 배지 대신 요일을 직접 보여준다 —
// 며칠째인지보다 "이번 주에 어디가 비었는지"가 아이에게 더 와닿는다.
function weekMarks() {
  const dayNames = ['월', '화', '수', '목', '금', '토', '일'];
  const done = new Set(store.days);
  const now = new Date();
  const monday = new Date(now);
  monday.setDate(now.getDate() - ((now.getDay() + 6) % 7));  // 이번 주 월요일
  return dayNames.map((label, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    const key = d.toLocaleDateString('sv');
    return { label, done: done.has(key), today: key === todayKey(), future: key > todayKey() };
  });
}

const accuracy = (part) => {
  const p = store.parts[part];
  return p && p.answered >= WEAK_MIN ? Math.round((p.correct / p.answered) * 100) : null;
};
const ranked = () => PARTS.map((p) => ({ part: p, acc: accuracy(p) })).filter((x) => x.acc !== null)
  .sort((a, b) => a.acc - b.acc);
const totalAnswered = () => Object.values(store.parts).reduce((n, p) => n + p.answered, 0);
const totalCorrect = () => Object.values(store.parts).reduce((n, p) => n + p.correct, 0);

// ---------- 로그인 (M2: 학원 발급 ID + 6자리 PIN) ----------
const AUTH_KEY = 'jumplish.auth.v1';
let auth = null;
try { auth = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); } catch { auth = null; }
const saveAuth = (a) => { auth = a; try { a ? localStorage.setItem(AUTH_KEY, JSON.stringify(a)) : localStorage.removeItem(AUTH_KEY); } catch { /* 무시 */ } };

// ---------- 개인 설정 (캐릭터·소리) ----------
const PREF_KEY = 'jumplish.pref.v1';
let pref = { sound: true };
try { pref = { ...pref, ...JSON.parse(localStorage.getItem(PREF_KEY) || '{}') }; } catch { /* 기본값 */ }
const savePref = () => { try { localStorage.setItem(PREF_KEY, JSON.stringify(pref)); } catch { /* 무시 */ } };

// ---------- 효과음 (Web Audio 합성 — 파일·외부 요청 0, 운영비 0원 원칙 유지) ----------
let audioCtx = null;
function sfxTone(seq, type = 'triangle', vol = 0.09) {
  try {
    audioCtx ||= new (window.AudioContext || window.webkitAudioContext)();
    const t0 = audioCtx.currentTime;
    for (const [freq, at, dur] of seq) {
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.type = type;
      o.frequency.value = freq;
      g.gain.setValueAtTime(0, t0 + at);
      g.gain.linearRampToValueAtTime(vol, t0 + at + 0.015);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + at + dur);
      o.connect(g).connect(audioCtx.destination);
      o.start(t0 + at);
      o.stop(t0 + at + dur + 0.05);
    }
  } catch { /* 소리는 못 나도 학습엔 지장 없음 */ }
}
// 실제 사운드 파일(/sfx/*.mp3 — Freesound CC0)을 쓰되, HTML <audio>가 아니라
// Web Audio로 튼다. <audio>로 틀면 브라우저가 '음악 재생'으로 인식해 화면 위에
// 미디어 컨트롤이 뜨고, 폰에서는 듣던 음악까지 끊긴다. 효과음은 그러면 안 된다.
//
// 파일마다 녹음 음량이 제각각이라(오답음은 최대 5%밖에 안 돼 사실상 안 들렸다)
// 불러올 때 최대 음량을 재서 1.0으로 맞춘 뒤, 아래 비율을 곱한다.
const SFX_VOL = { select: 0.10, correct: 0.30, wrong: 0.20, done: 0.35 };
const sfxBuf = {};     // 이름 → { buf, gain } / null(파일 못 씀)
let actx = null;

function audio() {
  actx ||= new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state === 'suspended') actx.resume().catch(() => { /* 곧 다시 시도된다 */ });
  return actx;
}

async function loadSfx(name) {
  try {
    const res = await fetch(`/sfx/${name}.mp3`);
    if (!res.ok) throw new Error('없음');
    const buf = await audio().decodeAudioData(await res.arrayBuffer());
    // 최대 음량을 재서 정규화 배수를 구한다 (너무 작게 녹음된 파일 구제)
    let peak = 0;
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i += 8) { const v = Math.abs(d[i]); if (v > peak) peak = v; }
    sfxBuf[name] = { buf, gain: peak > 0.01 ? Math.min(12, 1 / peak) : 1 };
  } catch { sfxBuf[name] = null; }
}

// 첫 터치에 오디오를 깨우고 파일을 미리 받아 둔다.
// (모바일은 사용자가 화면을 건드리기 전에는 소리를 못 낸다)
let sfxReady = false;
const wakeSfx = () => {
  if (sfxReady) return;
  sfxReady = true;
  audio();
  for (const n of Object.keys(SFX_VOL)) loadSfx(n);
};
addEventListener('pointerdown', wakeSfx, { once: true, capture: true });
addEventListener('keydown', wakeSfx, { once: true, capture: true });

function playSfx(name, fallback) {
  if (!pref.sound) return;
  wakeSfx();
  const item = sfxBuf[name];
  if (!item) return fallback();          // 아직 안 받았거나 못 쓰는 파일 → 합성음
  const ctx = audio();
  const src = ctx.createBufferSource();
  const g = ctx.createGain();
  src.buffer = item.buf;
  g.gain.value = item.gain * (SFX_VOL[name] ?? 0.3);
  src.connect(g).connect(ctx.destination);
  src.start();
}
// ── 문항 음원 재생기 ──
// <audio>를 쓰면 화면 위에 음악 컨트롤이 뜨고(폰에서는 듣던 음악까지 끊긴다),
// 재생바를 잡아당겨 원하는 데로 건너뛸 수 있어 실전 듣기와 어긋난다.
// 그래서 Web Audio로 직접 틀고, 버튼은 '다시 듣기' 하나만 둔다.
const clipCache = {};                       // 주소 → 디코드된 소리 (한 번만 받는다)
const loadClip = (url) => (clipCache[url] ||= fetch(url)
  .then((r) => { if (!r.ok) throw new Error('음원 없음'); return r.arrayBuffer(); })
  .then((b) => audio().decodeAudioData(b)));

const player = { src: null, url: null, startedAt: 0, rate: 1, buf: null, raf: 0, onTick: null };

function stopClip() {
  if (player.src) { try { player.src.stop(); } catch { /* 이미 끝남 */ } player.src.onended = null; }
  player.src = null;
  cancelAnimationFrame(player.raf);
  player.raf = 0;
}

// rate 1 = 보통 속도, 0.75 = 천천히
async function playClip(url, rate = 1) {
  const ctx = audio();
  const buf = await loadClip(url);
  stopClip();
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.playbackRate.value = rate;
  src.connect(ctx.destination);
  src.start();
  Object.assign(player, { src, url, buf, rate, startedAt: ctx.currentTime });
  src.onended = () => { if (player.src === src) { stopClip(); player.onTick?.(1, false); } };
  const tick = () => {
    if (player.src !== src) return;
    const p = Math.min(1, ((ctx.currentTime - player.startedAt) * rate) / buf.duration);
    player.onTick?.(p, true);
    player.raf = requestAnimationFrame(tick);
  };
  tick();
}

// 파일을 못 쓸 때 대신 낼 합성음. 짧고 부드럽게 — 오답음은 특히 세지 않게.
const sfx = {
  select: () => playSfx('select', () => sfxTone([[880, 0, 0.05]], 'sine', 0.035)),
  correct: () => playSfx('correct', () => sfxTone([[659.25, 0, 0.12], [987.77, 0.09, 0.22]])),
  wrong: () => playSfx('wrong', () => sfxTone([[392, 0, 0.09], [294, 0.07, 0.16]], 'sine', 0.05)),
  done: () => playSfx('done', () => sfxTone([[523.25, 0, 0.12], [659.25, 0.1, 0.12], [783.99, 0.2, 0.12], [1046.5, 0.3, 0.3]])),
};

// ---------- 통신 ----------
async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}
const renderError = (msg) => {
  view.innerHTML = `<div class="error-box"><strong>문제가 생겼어요.</strong><br>${esc(msg)}<br>
    <button class="btn-ghost" style="margin-top:10px" onclick="location.reload()">다시 시도</button></div>`;
};

// ---------- 상단 앱바 + 설정 시트 ----------
// 다른 학습앱 관행: 좌측 브랜드, 우측 프로필 아바타 → 탭하면 설정 시트가 올라온다.
function appBar() {
  return `
    <div class="appbar">
      <div class="appbar-brand">
        <span class="appbar-mark"><svg viewBox="0.5 4 23 17" aria-hidden="true">
          <path d="M1.5 20 L6 13.5 L10.5 20 Z" fill="#fff" opacity=".4"/>
          <path d="M7 20 L12 10 L17 20 Z" fill="#fff" opacity=".7"/>
          <path d="M13 20 L18 5.5 L23 20 Z" fill="#fff"/>
        </svg></span>
        <span class="appbar-name">점프리시</span>
      </div>
      <button class="avatar-btn" data-profile aria-label="내 정보와 설정">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="9" r="3.6"/><path d="M4.5 20c1.3-3.6 4.1-5.4 7.5-5.4S18.2 16.4 19.5 20"/></svg>
      </button>
    </div>`;
}

function bindAppBar() {
  view.querySelector('[data-profile]')?.addEventListener('click', showSettings);
}

function showSettings() {
  const back = document.createElement('div');
  back.className = 'sheet-back';
  back.innerHTML = `
    <div class="sheet" role="dialog" aria-label="내 정보와 설정">
      <div class="sheet-grab"></div>
      <h2>${auth ? esc(auth.user.display_name) + ' 님' : '내 정보'}</h2>
      <p class="card-note">${auth
        ? `아이디 ${esc(auth.user.login_id)} · 기록이 서버에 저장돼요`
        : '로그인하지 않았어요 — 기록이 이 기기에만 남아요'}</p>

      ${auth ? `
      <p class="sheet-sect">이름</p>
      <div class="name-row">
        <input class="name-input" data-name maxlength="12" value="${esc(auth.user.display_name)}"
               aria-label="화면에 보일 이름" />
        <button class="btn-primary name-save" data-name-save>저장</button>
      </div>
      <p class="card-note" data-name-msg>화면에 보일 별명이에요. 12자까지 쓸 수 있어요.
        진짜 이름 대신 별명을 쓰는 걸 권해요.</p>` : ''}


      <p class="sheet-sect">소리</p>
      <div class="switch-row">
        <span>효과음 켜기</span>
        <button class="switch" data-sound role="switch" aria-checked="${pref.sound}" aria-label="효과음 켜기"></button>
      </div>

      <p class="sheet-sect">개인정보</p>
      <p class="card-note">점프리시는 이메일·전화번호를 받지 않아요. 학원에서 받은 아이디와
        비밀번호 6자리, 그리고 문제 푼 기록만 저장합니다.</p>

      <p class="sheet-sect">사진 출처</p>
      <p class="card-note">듣기 1번의 사진은
        <a href="https://pixabay.com" target="_blank" rel="noopener">Pixabay</a>에서 가져왔어요.</p>

      <div style="display:flex; gap:8px; margin-top:6px">
        <button class="btn-ghost" style="flex:1" data-close>닫기</button>
        <button class="btn-primary" style="flex:1" data-auth-toggle>${auth ? '로그아웃' : '로그인'}</button>
      </div>
    </div>`;
  document.body.appendChild(back);
  const close = () => back.remove();
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  back.querySelector('[data-close]').addEventListener('click', close);
  back.querySelector('[data-sound]').addEventListener('click', (e) => {
    pref.sound = !pref.sound; savePref();
    e.currentTarget.setAttribute('aria-checked', String(pref.sound));
    if (pref.sound) sfx.select();
  });
  const nameSave = back.querySelector('[data-name-save]');
  if (nameSave) {
    const input = back.querySelector('[data-name]');
    const msg = back.querySelector('[data-name-msg]');
    const submit = async () => {
      const value = input.value.trim();
      if (!value || value === auth.user.display_name) return;
      nameSave.disabled = true;
      try {
        const r = await api('/api/me/name', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({ display_name: value }),
        });
        saveAuth({ ...auth, user: { ...auth.user, display_name: r.display_name } });
        back.querySelector('h2').textContent = `${r.display_name} 님`;
        input.value = r.display_name;
        msg.textContent = '바뀌었어요.';
        rerenderTab();          // 뒤에 깔린 화면의 인사말까지 바로 바꾼다
        sfx.correct();
      } catch (e) {
        msg.textContent = e.message;      // 서버가 이유를 아이 말로 돌려준다
      } finally { nameSave.disabled = false; }
    };
    nameSave.addEventListener('click', submit);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
  }

  back.querySelector('[data-auth-toggle]').addEventListener('click', () => {
    close();
    if (auth) { saveAuth(null); store.set = null; store.setDate = null; save(); setTab('home'); showHome(); }
    else showLogin();
  });
}

// ---------- 탭 ----------
let currentTab = 'home';
function setTab(name) {
  currentTab = name;
  tabbar.querySelectorAll('.tab').forEach((b) => {
    if (b.dataset.tab === name) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
}
const TAB_VIEWS = { home: showHome, review: showReview, record: showRecord, parts: showParts };
// 설정에서 무언가 바꾸면(이름 등) 지금 보고 있는 화면을 다시 그린다.
// 안 그리면 저장은 됐는데 화면엔 옛 이름이 남아 "안 바뀐다"고 느끼게 된다.
const rerenderTab = () => TAB_VIEWS[currentTab]?.();
tabbar.addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  setTab(btn.dataset.tab);
  TAB_VIEWS[btn.dataset.tab]?.();
});
const tabbarVisible = (on) => {
  tabbar.style.display = on ? 'flex' : 'none';
  document.body.classList.toggle('no-tabbar', !on);
};

// ---------- 홈: 오늘의 맞춤 학습 ----------
const authHeaders = () => (auth ? { Authorization: `Bearer ${auth.token}` } : {});

async function ensureTodaySet() {
  const owner = auth?.user?.id || 'guest';
  if (store.set && store.setDate === todayKey() && store.setUser === owner) return store.set;
  let data;
  if (auth) {
    // 서버가 복습+약점+신규 슬롯으로 개인 세트를 만든다 (기기 바꿔도 같은 세트)
    try {
      data = await api('/api/today', { headers: authHeaders() });
    } catch (e) {
      if (/로그인/.test(e.message)) { saveAuth(null); } else throw e;
    }
  }
  if (!data) {
    const weak = ranked().slice(0, 2).map((x) => x.part);
    const strong = ranked().slice(-2).reverse().map((x) => x.part);
    const qs = new URLSearchParams();
    if (weak.length) qs.set('weak', weak.join(','));
    if (strong.length) qs.set('strong', strong.join(','));
    data = await api(`/api/today?${qs}`);
  }
  store.set = data;
  store.setDate = todayKey();
  store.setUser = owner;
  store.setIdx = 0;
  save();
  return data;
}

// 등반 지도 카드 — 고도는 서버 결정적 수식(학습일·실력 성장·봉인), 베이스캠프는 고수위
// 캐릭터를 등산로 곡선 위 진행률 지점에 올린다 (SVG 경로 좌표 → 화면 좌표)

const levelOf = (acc) =>
  acc === null ? 'lv-none' : acc >= 80 ? 'lv-high' : acc >= 60 ? 'lv-mid' : 'lv-low';

// ── 내 실력 지도 (오각형 레이더) ──
// 시험 파트(L1~R3) 대신 '능력' 5축으로 그린다 — "L2가 약해요"는 아이도 부모도 못 알아듣는다.
// 점선은 2주 전 내 모습, 흐린 축은 아직 표본이 모자라 값을 못 내는 축이다.
function radarSvg(axes) {
  const S = 250, cx = S / 2, cy = S / 2, R = S * 0.33, pad = S * 0.22;
  const at = (i, r) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / axes.length;
    return [cx + Math.cos(a) * R * r, cy + Math.sin(a) * R * r];
  };
  const poly = (vals) => vals.map((v, i) => at(i, v).join(',')).join(' ');
  const r0 = 0.06;                                   // 0점도 점이 보이도록 최소 반지름
  const now = axes.map((a) => (a.score ?? 0) / 100 + r0);
  const was = axes.map((a) => (a.was ?? 0) / 100 + r0);
  const hasWas = axes.some((a) => a.was != null);
  const rings = [1, 0.75, 0.5, 0.25]
    .map((r) => `<polygon class="rg" points="${poly(axes.map(() => r))}"/>`).join('');
  const spokes = axes.map((_, i) => `<line class="rg" x1="${cx}" y1="${cy}" x2="${at(i, 1)[0]}" y2="${at(i, 1)[1]}"/>`).join('');
  const dots = axes.map((a, i) => {
    const [x, y] = at(i, now[i]);
    return a.score == null
      ? `<circle class="rd-off" cx="${x}" cy="${y}" r="4"/>`
      : `<circle class="rd" cx="${x}" cy="${y}" r="5"/>`;
  }).join('');
  const labels = axes.map((a, i) => {
    const [x, y] = at(i, 1.26);
    const anchor = Math.abs(x - cx) < 4 ? 'middle' : (x > cx ? 'start' : 'end');
    return `<text class="rl${a.score == null ? ' off' : ''}" x="${x}" y="${y + 4}" text-anchor="${anchor}">${esc(a.name)}</text>` +
      (a.score == null ? '' : `<text class="rv" x="${x}" y="${y + 19}" text-anchor="${anchor}">${a.score}</text>`);
  }).join('');
  return `<svg class="radar" viewBox="${-pad} ${S * 0.04} ${S + pad * 2} ${S * 0.94}" role="img"
    aria-label="실력 지도">${rings}${spokes}
    ${hasWas ? `<polygon class="rp-was" points="${poly(was)}"/>` : ''}
    <polygon class="rp-now" points="${poly(now)}"/>${dots}${labels}</svg>`;
}

function skillCard(sm) {
  const axes = sm?.axes ?? [];
  const ready = axes.filter((a) => a.score != null);
  const bars = [...ready].sort((a, b) => a.score - b.score).map((a) => `
    <div class="sbar">
      <span class="sbl">${esc(a.name)}</span>
      <span class="sbt"><span class="sbf" style="width:${a.score}%"></span></span>
      <span class="sbn">${a.score}</span>
    </div>`).join('');
  const head = sm?.weakest
    ? `<p class="card-note">가장 약한 곳</p><p class="weak-name">${esc(sm.weakest.name)}</p>`
    : `<p class="card-note">아직 실력을 재는 중이에요 — 문제를 풀면 채워져요</p>`;
  return `<div class="card">
    <div class="card-head"><span class="card-title">내 실력 지도</span>
      <span class="card-note">${ready.length ? `${ready.length}/${axes.length}칸 측정` : '측정 전'}</span></div>
    ${radarSvg(axes.length ? axes : SKILL_AXIS_NAMES.map((name) => ({ name, score: null, was: null })))}
    ${head}${bars}
  </div>`;
}
const SKILL_AXIS_NAMES = ['듣고 알기', '읽고 알기', '찾아내기', '문장 규칙', '속뜻 알기'];

// 레이더에 섞지 않는 두 지표 — 성격이 다르다.
// 설욕률은 정답률보다 정직하다(쉬운 새 문제만 받아도 정답률은 오르지만 설욕률은 안 오른다).
function duoCards(sm) {
  if (!sm?.revive && !sm?.speed) return '';
  const revive = sm.revive
    ? `<div class="duo-c"><p class="card-note">설욕률</p><p class="duo-n">${sm.revive.rate}%</p>
         <p class="duo-s">다시 만나 ${sm.revive.won}판 승</p></div>`
    : `<div class="duo-c"><p class="card-note">설욕률</p><p class="duo-n">–</p>
         <p class="duo-s">틀린 문제를 다시 만나면 표시돼요</p></div>`;
  const speed = sm.speed
    ? `<div class="duo-c"><p class="card-note">푸는 속도</p><p class="duo-n">${sm.speed.seconds}초</p>
         <p class="duo-s">${sm.speed.faster_by > 0 ? `지난주보다 ${sm.speed.faster_by}초 빨라짐`
           : sm.speed.faster_by < 0 ? '지난주보다 조금 느려짐' : '한 문제 푸는 데 걸린 시간'}</p></div>`
    : `<div class="duo-c"><p class="card-note">푸는 속도</p><p class="duo-n">–</p>
         <p class="duo-s">조금 더 풀면 표시돼요</p></div>`;
  return `<div class="duo">${revive}${speed}</div>`;
}


async function showHome() {
  setTab('home');
  tabbarVisible(true);
  view.innerHTML = '<p class="loading">오늘의 학습을 준비하고 있어요...</p>';
  try {
    const set = await ensureTodaySet();
    // 다시 볼 문제 수: 로그인은 서버 SRS 큐(오늘 도래분), 게스트는 이 기기 기록
    let reviewN = store.wrong.length;
    let me = null, sm = null;
    if (auth) {
      try {
        me = await api('/api/me', { headers: authHeaders() });
        reviewN = me.review_due;
        // 다른 기기에서 이름을 바꿨을 수 있다 — 서버 값이 다르면 이 기기 것을 맞춘다
        if (me.user?.display_name && me.user.display_name !== auth.user.display_name) {
          saveAuth({ ...auth, user: { ...auth.user, display_name: me.user.display_name } });
        }
      } catch { /* 무시 */ }
      try { sm = await api('/api/skillmap', { headers: authHeaders() }); } catch { /* 무시 */ }
    }
    const total = set.questions.length;
    const doneN = Math.min(store.setIdx, total);
    const left = total - doneN;
    const C = 2 * Math.PI * 17;
    const weak = ranked()[0];
    const answered = totalAnswered();

    const focusCard = weak
      ? `<div class="card focus">
           <div class="focus-head"><span class="dot"></span>
             <span class="focus-title">가장 약한 곳 — ${weak.part} ${PART_INFO[weak.part].name}</span></div>
           <p class="focus-desc">${esc(PART_INFO[weak.part].desc)}에서 자주 틀리고 있어요.
             오늘 학습에 이 파트를 더 넣었습니다.</p>
           <button class="btn-focus" data-focus="${weak.part}">${weak.part} 집중해서 풀기</button>
         </div>`
      : `<div class="card focus">
           <div class="focus-head"><span class="dot" style="background:var(--primary)"></span>
             <span class="focus-title">아직 실력을 재는 중이에요</span></div>
           <p class="focus-desc">${WEAK_MIN}문제 이상 푼 파트부터 점수가 나타나요.
             오늘의 학습을 마치면 약한 곳을 콕 집어 알려드릴게요.</p>
         </div>`;

    const hello = auth?.user?.display_name
      ? `${auth.user.display_name} 님, ${left === 0 ? '오늘 학습을 다 마쳤어요' : '오늘도 점프해볼까요'}`
      : (left === 0 ? '오늘 학습을 다 마쳤어요' : '오늘도 한 번 점프해볼까요');
    view.innerHTML = `
      ${appBar()}
      <div class="greet">
        <div>
          <p class="greet-date">${new Date().toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'long' })}</p>
          <h1 class="greet-title">${esc(hello)}</h1>
        </div>
        ${auth ? '' : '<button class="btn-ghost" data-login>로그인</button>'}
      </div>

      <div class="week" role="group" aria-label="이번 주 학습한 날">
        <span class="week-label">이번 주</span>
        <div class="week-days">${weekMarks().map((d) => `
          <span class="wd${d.done ? ' is-done' : ''}${d.today ? ' is-today' : ''}${d.future ? ' is-future' : ''}"
                aria-label="${d.label}요일 ${d.done ? '학습함' : '학습 안 함'}">${d.label}</span>`).join('')}
        </div>
      </div>

      ${auth && me && !me.diagnosed ? `
      <button class="card row diag-card" data-diag>
        <span class="row-ico diag-ico">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M15.8 15.8 21 21"/><path d="M11 8.2v3.2l2.2 1.3"/></svg>
        </span>
        <span class="row-body">
          <span class="row-t">내 실력 알아보기</span>
          <span class="row-s">문제 몇 개만 풀면 나에게 딱 맞는 학습이 시작돼요 (10분)</span>
        </span>
        <svg class="row-arrow" viewBox="0 0 16 16"><path d="M6 3.5 10.5 8 6 12.5"/></svg>
      </button>` : ''}

      <div class="today">
        <p class="today-label">오늘의 학습</p>
        <div class="today-main">
          <svg class="ring" viewBox="0 0 42 42" aria-hidden="true">
            <circle cx="21" cy="21" r="17" fill="none" stroke="rgba(255,255,255,.28)" stroke-width="5"/>
            <circle cx="21" cy="21" r="17" fill="none" stroke="var(--accent)" stroke-width="5" stroke-linecap="round"
                    stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${(C * (1 - doneN / total)).toFixed(1)}"
                    transform="rotate(-90 21 21)"/>
            <text x="21" y="24" text-anchor="middle" font-size="10" fill="#fff">${doneN}/${total}</text>
          </svg>
          <div class="today-figs">
            <p class="n">${left === 0 ? '전부 완료' : `${left}문항 남음`}</p>
            <p class="sub">듣기 ${set.questions.filter((q) => q.section === 'LC').length} ·
              읽기 ${set.questions.filter((q) => q.section === 'RC').length} · 약 10분</p>
          </div>
        </div>
        <button class="btn-hero" data-start>${
          left === 0 ? '다시 풀어보기' : doneN > 0 ? '이어서 풀기' : '시작하기'}</button>
      </div>

      ${skillCard(sm)}
      ${duoCards(sm)}

      ${sm?.weakest ? '' : focusCard}

      <button class="card row" data-tab-go="review">
        <span class="row-ico"><svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.4"/><path d="M8 4.5v4M8 11.2v.1"/></svg></span>
        <span class="row-body">
          <span class="row-t">오늘의 리매치 ${reviewN}판</span>
          <span class="row-s">${reviewN ? '틀렸던 문제에게 설욕할 시간이에요' : '틀린 문제가 생기면 여기서 다시 만나요'}</span>
        </span>
        <svg class="row-arrow" viewBox="0 0 16 16"><path d="M6 3.5 10.5 8 6 12.5"/></svg>
      </button>`;

    bindAppBar();
    view.querySelector('[data-login]')?.addEventListener('click', showLogin);
    view.querySelector('[data-diag]')?.addEventListener('click', showDiagnostic);
    view.querySelector('[data-start]').addEventListener('click', () => {
      if (left === 0) { store.setIdx = 0; save(); }
      startSession(set.questions, set.passages, '오늘의 학습', { trackToday: true });
    });
    view.querySelector('[data-focus]')?.addEventListener('click', (e) => showPartPractice(e.target.dataset.focus));
    view.querySelector('[data-tab-go]').addEventListener('click', () => { setTab('review'); showReview(); });
  } catch (e) { renderError(e.message); }
}

// ---------- 로그인 화면 ----------
function showLogin() {
  tabbarVisible(false);
  view.innerHTML = `
    <div class="player-head"><button class="btn-ghost" data-back>돌아가기</button></div>
    <div class="qcard" style="gap:15px">
      <div>
        <h1 class="greet-title">학원 로그인</h1>
        <p class="card-note" style="margin-top:4px">선생님께 받은 아이디와 비밀번호 6자리를 넣어주세요.</p>
      </div>
      <label class="field"><span>아이디 (예: JUMP-1)</span>
        <input data-lid autocapitalize="characters" autocomplete="username" placeholder="가입코드-번호" /></label>
      <label class="field"><span>비밀번호 (숫자 6자리)</span>
        <input data-pin type="password" inputmode="numeric" maxlength="6" autocomplete="current-password" placeholder="●●●●●●" /></label>
      <div data-result></div>
      <button class="btn-primary" data-submit>로그인</button>
      <p class="card-note">아직 아이디가 없어도 괜찮아요 — 로그인 없이 풀면 이 기기에만 기록됩니다.</p>
    </div>`;
  view.querySelector('[data-back]').addEventListener('click', () => { setTab('home'); showHome(); });
  const submit = async () => {
    const login_id = view.querySelector('[data-lid]').value.trim();
    const pin = view.querySelector('[data-pin]').value.trim();
    const box = view.querySelector('[data-result]');
    if (!login_id || !/^\d{6}$/.test(pin)) {
      box.innerHTML = '<div class="result bad"><p>아이디와 숫자 6자리를 확인해주세요.</p></div>';
      return;
    }
    try {
      const r = await api('/api/auth/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ login_id, pin }),
      });
      saveAuth({ token: r.token, user: r.user });
      setTab('home'); showHome();
    } catch (e) {
      box.innerHTML = `<div class="result bad"><p>${esc(e.message)}</p></div>`;
    }
  };
  view.querySelector('[data-submit]').addEventListener('click', submit);
  view.querySelector('[data-pin]').addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
}

// ---------- 진단 테스트 ----------
async function showDiagnostic() {
  tabbarVisible(false);
  view.innerHTML = '<p class="loading">진단을 준비하고 있어요...</p>';
  try {
    const s1 = await api('/api/diagnostic/start', { method: 'POST', headers: authHeaders() });
    if (s1.done) { setTab('home'); return showHome(); }
    runDiagStage(s1);
  } catch (e) { renderError(e.message); }
}

function runDiagStage(stage) {
  startSession(stage.questions, stage.passages, '실력 진단');
  session.diag = { session_id: stage.session_id, stage: stage.stage, answers: [] };
  renderQuestion();  // 진단 상태(하단 버튼 숨김·자동 진행)를 반영해 다시 그림
}

async function endDiagStage() {
  const d = session.diag;
  session.diag = null;
  view.innerHTML = '<p class="loading">채점하고 있어요...</p>';
  const body = (o) => ({ method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify(o) });
  try {
    if (d.stage === 1) {
      const s2 = await api('/api/diagnostic/stage2', body({ session_id: d.session_id, answers: d.answers }));
      view.innerHTML = `
        <div class="done">
          <div class="done-mark"><svg viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5"/></svg></div>
          <p class="done-title">절반 왔어요!</p>
          <p class="done-sub">잘하고 있어요. 이제 ${s2.count}문제만 더 풀면 끝나요.</p>
        </div>
        <button class="btn-hero" style="background:var(--primary);color:#fff" data-go>이어서 풀기</button>`;
      view.querySelector('[data-go]').addEventListener('click', () => runDiagStage(s2));
    } else {
      const r = await api('/api/diagnostic/finish', body({ session_id: d.session_id, answers: d.answers }));
      showDiagResult(r);
    }
  } catch (e) { renderError(e.message); }
}

function showDiagResult(r) {
  sfx.done();
  tabbarVisible(true);
  store.set = null; store.setDate = null; save();  // 새 실력 기준으로 오늘 세트 재생성
  const rows = r.report.map((x) => `
    <div class="row">
      <span class="row-ico" style="background:var(--primary-soft);color:var(--primary)">${x.part}</span>
      <span class="row-body">
        <span class="row-t">${PART_INFO[x.part].name}</span>
        <span class="row-s">${x.count}문항 중 ${Math.round(x.acc * x.count / 100)}개 정답</span>
      </span>
      <span class="progress-num">${x.grade}등급</span>
    </div>`).join('');
  view.innerHTML = `
    <div class="done">
      <div class="done-mark"><svg viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5"/></svg></div>
      <p class="done-title">진단 완료!</p>
      <p class="done-sub">파트별 등급이에요 (1~5등급, 5가 최고).${r.group === 'junior' ? '<br>문항 수가 적어 참고용이에요.' : ''}</p>
    </div>
    <div class="card"><div class="rowlist">${rows}</div></div>
    <button class="btn-hero" style="background:var(--primary);color:#fff" data-go-home>내 맞춤 학습 시작하기</button>`;
  view.querySelector('[data-go-home]').addEventListener('click', () => { setTab('home'); showHome(); });
}

// ---------- 오답 ----------
// 틀린 문제에서 담아 둔 표현들 — 아직 내 것이 아닌 표현만 모여 있다.
function exprPocketHtml() {
  if (!store.exprs.length) return '';
  const list = store.exprs.map((e) => `
    <div class="row">
      <span class="row-ico">${e.part}</span>
      <span class="row-body">
        <span class="row-t">${esc(e.en)}</span>
        <span class="row-s">${esc(e.ko)}</span>
      </span>
    </div>`).join('');
  return `
    <p class="section-label">표현 주머니 ${store.exprs.length}개</p>
    <div class="card"><div class="rowlist">${list}</div>
      <p class="notice">그 문제를 다시 맞히면 주머니에서 빠져요.</p></div>`;
}

async function showReview() {
  await renderReview();
  const pocket = exprPocketHtml();
  if (pocket) {
    view.insertAdjacentHTML('beforeend', pocket);
    view.querySelectorAll('.row-ico').forEach((el) => {
      el.style.cssText += 'font-size:.74rem;font-weight:700;background:var(--primary-soft);color:var(--primary)';
    });
  }
}

async function renderReview() {
  setTab('review');
  tabbarVisible(true);
  if (auth) {
    view.innerHTML = '<p class="loading">복습할 문제를 찾는 중...</p>';
    try {
      const r = await api('/api/review', { headers: authHeaders() });
      if (!r.count) {
        view.innerHTML = `<div class="greet"><div><h1 class="greet-title">오늘의 리매치</h1></div></div>
          <div class="card"><p class="empty">오늘 만날 상대가 없어요.<br>틀린 문제는 1일 → 3일 → 7일 → 14일 뒤에 리매치로 돌아와요.<br>4연승하면 봉인 앨범에 박제됩니다.</p></div>`;
        return;
      }
      const list = r.questions.map((q) => `
        <div class="row">
          <span class="row-ico">${q.part}</span>
          <span class="row-body">
            <span class="row-t">${esc(q.stem || PART_INFO[q.part].name)}</span>
            <span class="row-s">${PART_INFO[q.part].name} · ${q.srs_box}연승째 도전 ${q.srs_box >= 4 ? '(이기면 봉인!)' : ''}</span>
          </span>
        </div>`).join('');
      view.innerHTML = `
        ${appBar()}
        <div class="greet"><div>
          <p class="greet-date">4연승하면 그 문제는 영원히 봉인됩니다</p>
          <h1 class="greet-title">오늘의 리매치 ${r.count}판</h1>
        </div></div>
        <button class="btn-hero" style="background:var(--primary);color:#fff" data-review-start>리매치 시작</button>
        <div class="card"><div class="rowlist">${list}</div></div>`;
      bindAppBar();
      view.querySelectorAll('.row-ico').forEach((el) => {
        el.style.cssText += 'font-size:.74rem;font-weight:700;background:var(--primary-soft);color:var(--primary)';
      });
      view.querySelector('[data-review-start]').addEventListener('click', () =>
        startSession(r.questions, r.passages, '리매치'));
      return;
    } catch (e) {
      if (/로그인/.test(e.message)) saveAuth(null);
      else return renderError(e.message);
    }
  }
  if (!store.wrong.length) {
    view.innerHTML = `${appBar()}<div class="greet"><div><h1 class="greet-title">다시 풀 문제</h1></div></div>
      <div class="card"><p class="empty">아직 틀린 문제가 없어요.<br>오늘의 학습을 풀면 여기에 모입니다.</p></div>`;
    return;
  }
  const list = store.wrong.map((w) => `
    <div class="row">
      <span class="row-ico">${w.q.part}</span>
      <span class="row-body">
        <span class="row-t">${esc(w.q.stem || PART_INFO[w.q.part].name)}</span>
        <span class="row-s">${PART_INFO[w.q.part].name} · ${new Date(w.at).toLocaleDateString('ko-KR')}</span>
      </span>
    </div>`).join('');
  view.innerHTML = `
    <div class="greet"><div>
      <p class="greet-date">틀린 문제는 다시 만나야 내 것이 돼요</p>
      <h1 class="greet-title">다시 볼 문제 ${store.wrong.length}개</h1>
    </div></div>
    <button class="btn-hero" style="background:var(--primary);color:#fff" data-review-start>전부 다시 풀기</button>
    <div class="card"><div class="rowlist">${list}</div></div>`;
  view.querySelectorAll('.row-ico').forEach((el) => {
    el.style.cssText += 'font-size:.74rem;font-weight:700;background:var(--primary-soft);color:var(--primary)';
  });
  view.querySelector('[data-review-start]').addEventListener('click', () => {
    const qs = store.wrong.map((w) => w.q);
    const ps = {};
    store.wrong.forEach((w) => { if (w.passage) ps[w.passage.id] = w.passage; });
    startSession(qs, ps, '오답 복습');
  });
}

// ---------- 기록 ----------
async function showRecord() {
  setTab('record');
  tabbarVisible(true);
  let sealed = null, rec = null;
  if (auth) {
    try { sealed = (await api('/api/me', { headers: authHeaders() })).sealed; } catch { /* 무시 */ }
    try { rec = await api('/api/records', { headers: authHeaders() }); } catch { /* 무시 */ }
  }
  const answered = totalAnswered();
  const acc = answered ? Math.round((totalCorrect() / answered) * 100) : 0;
  view.innerHTML = `
    ${appBar()}
    <div class="greet"><div>
      <p class="greet-date">지금까지 걸어온 자리</p>
      <h1 class="greet-title">내 발자국</h1>
    </div></div>
    <div class="stat-row">
      <div class="stat"><span class="label">이어온 날</span><span class="value">${streakDays()}일</span></div>
      <div class="stat"><span class="label">푼 문항</span><span class="value">${answered}</span></div>
      <div class="stat"><span class="label">정답률</span><span class="value">${answered ? acc + '%' : '–'}</span></div>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">파트별 숙달도</span>
        <span class="card-note">${WEAK_MIN}문항 이상 푼 파트만</span></div>
      ${skillMap()}
    </div>
    ${rec ? `
    <div class="card">
      <div class="card-head"><span class="card-title">내 최고 기록</span>
        <span class="card-note">어제의 나와 대결</span></div>
      <div class="rowlist">
        <div class="row">
          <span class="row-body">
            <span class="row-t">연속 정답 ${rec.best_run}개</span>
            <span class="row-s">${
              rec.current_run > 0 && rec.best_run >= 3 && rec.current_run >= rec.best_run - 2 && rec.current_run < rec.best_run
                ? `지금 ${rec.current_run}연속 — 최고 기록까지 ${rec.best_run - rec.current_run}개!`
                : rec.current_run > 0 && rec.current_run >= rec.best_run && rec.best_run > 0
                  ? `지금 ${rec.current_run}연속 — 신기록 진행 중!`
                  : `지금 ${rec.current_run}연속`}</span>
          </span>
        </div>
        <div class="row">
          <span class="row-body">
            <span class="row-t">하루 최다 풀이 ${rec.best_day ? rec.best_day.n : 0}문항</span>
            <span class="row-s">오늘은 ${rec.today_n}문항${
              rec.best_day && rec.today_n > 0 && rec.today_n >= rec.best_day.n - 3 && rec.today_n < rec.best_day.n
                ? ` — 기록 갱신까지 ${rec.best_day.n - rec.today_n}문항!` : ''}</span>
          </span>
        </div>
      </div>
    </div>` : ''}
    ${sealed !== null ? `
    <div class="card row">
      <span class="row-ico" style="background:var(--ok-soft);color:var(--ok)">
        <svg viewBox="0 0 16 16"><rect x="3" y="6.5" width="10" height="7" rx="1.6"/><path d="M5.5 6.5V5a2.5 2.5 0 0 1 5 0v1.5"/></svg>
      </span>
      <span class="row-body">
        <span class="row-t">봉인 앨범 ${sealed}문제</span>
        <span class="row-s">리매치 4연승으로 완전히 이겨낸 문제들</span>
      </span>
    </div>` : ''}
    <div class="card row">
      <span class="row-body">
        <span class="row-t">${auth ? esc(`${auth.user.display_name} (${auth.user.login_id})`) : '로그인하지 않았어요'}</span>
        <span class="row-s">${auth ? '풀이 기록이 서버에 저장되고 있어요' : '로그인하면 기록이 어느 기기에서나 이어져요'}</span>
      </span>
      <button class="btn-ghost" data-auth-btn>${auth ? '로그아웃' : '로그인'}</button>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">파트별 상세</span></div>
      <div class="rowlist">${PARTS.map((p) => {
        const s = store.parts[p];
        return `<div class="row">
          <span class="row-body">
            <span class="row-t">${p} ${PART_INFO[p].name}</span>
            <span class="row-s">${s ? `${s.correct} / ${s.answered} 문항` : '아직 풀지 않음'}</span>
          </span>
          <span class="progress-num">${accuracy(p) === null ? '–' : accuracy(p) + '%'}</span>
        </div>`;
      }).join('')}</div>
    </div>`;
  bindAppBar();
  view.querySelector('[data-auth-btn]').addEventListener('click', () => {
    if (auth) { saveAuth(null); showRecord(); }
    else showLogin();
  });
}

// ---------- 파트별 연습 (하부 메뉴) ----------
async function showParts() {
  setTab('parts');
  tabbarVisible(true);
  view.innerHTML = '<p class="loading">불러오는 중...</p>';
  try {
    const { parts } = await api('/api/parts');
    const byCode = Object.fromEntries(parts.map((p) => [p.part, p]));
    const card = (code) => {
      const p = byCode[code];
      const info = PART_INFO[code];
      const count = p ? p.total : 0;
      return `<button class="part-card" data-part="${code}" ${count ? '' : 'disabled'}>
        <span class="part-code">${code}</span>
        <span class="part-name">${info.name}</span>
        <span class="part-meta">${info.desc}</span>
        <span class="part-meta">${count ? `${count}문항` : '준비 중'}</span>
      </button>`;
    };
    view.innerHTML = `
      ${appBar()}
      <div class="greet"><div>
        <p class="greet-date">골라서 더 풀고 싶을 때</p>
        <h1 class="greet-title">연습장</h1>
      </div></div>
      <p class="section-label">듣기 (Listening)</p>
      <div class="part-grid">${['L1', 'L2', 'L3', 'L4'].map(card).join('')}</div>
      <p class="section-label">읽기 (Reading)</p>
      <div class="part-grid">${['R1', 'R2', 'R3'].map(card).join('')}</div>`;
    bindAppBar();
    view.querySelectorAll('.part-card[data-part]').forEach((b) =>
      b.addEventListener('click', () => showPartPractice(b.dataset.part)));
  } catch (e) { renderError(e.message); }
}

async function showPartPractice(part) {
  view.innerHTML = '<p class="loading">문항을 가져오는 중...</p>';
  try {
    const data = await api(`/api/questions?part=${part}`);
    if (!data.questions.length) return renderError('이 파트에는 아직 문항이 없어요.');
    startSession(data.questions, data.passages, `${part} ${PART_INFO[part].name}`);
  } catch (e) { renderError(e.message); }
}

// ---------- 문제 풀이 ----------
const session = { questions: [], passages: {}, idx: 0, title: '', trackToday: false, correct: 0 };

function startSession(questions, passages, title, opts = {}) {
  Object.assign(session, {
    questions, passages, title, correct: 0,
    trackToday: !!opts.trackToday, diag: null,
  });
  // 같은 지문(passage_id)을 잇달아 공유하는 문항을 한 화면(세트)으로 묶는다.
  // 실전처럼 음원·지문은 세트당 1번, 문제들은 그 아래 연속 배치.
  session.groups = [];
  let cur = null;
  questions.forEach((q, i) => {
    if (cur && q.passage_id && cur.pid === q.passage_id) cur.items.push(i);
    else { cur = { pid: q.passage_id || null, items: [i] }; session.groups.push(cur); }
  });
  const done = opts.trackToday ? Math.min(store.setIdx, questions.length) : 0;
  session.doneBase = done;   // 이 앞 번호까지는 지난 접속에서 이미 풂 (잠금 표시)
  session.gidx = session.groups.findIndex((g) => g.items[g.items.length - 1] >= done);
  if (session.gidx < 0) session.gidx = session.groups.length - 1;
  tabbarVisible(false);
  renderQuestion();
}

function endSession() {
  sfx.done();
  tabbarVisible(true);
  const n = session.questions.length;
  view.innerHTML = `
    <div class="done">
      <div class="done-mark"><svg viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5"/></svg></div>
      <p class="done-title">${session.title} 완료</p>
      <p class="done-sub">${n}문항 중 ${session.correct}문항 맞혔어요</p>
    </div>
    <button class="btn-hero" style="background:var(--primary);color:#fff" data-go-home>홈으로</button>`;
  view.querySelector('[data-go-home]').addEventListener('click', () => { setTab('home'); showHome(); });
}

// ── 막힌 자리 신고 ──
// 아이가 그 화면에서 바로 누르게 한다. 어른이 대신 옮겨 적으면 진짜 이유가 사라진다.
// 고르는 말은 아이가 실제로 느끼는 말로 적었다("어렵다"가 아니라 "무슨 말인지 모르겠어요").
const REPORT_KINDS = [
  ['audio', '소리가 안 들려요'],
  ['image', '사진이 문제랑 안 맞아요'],
  ['hard', '무슨 말인지 모르겠어요'],
  ['answer', '답이 이상해요'],
  ['etc', '그 밖에'],
];

function showReport(questionId, screen) {
  const back = document.createElement('div');
  back.className = 'sheet-back';
  back.innerHTML = `
    <div class="sheet" role="dialog" aria-label="이상한 점 알려주기">
      <div class="sheet-grab"></div>
      <h2>어떤 점이 불편했나요?</h2>
      <p class="card-note">알려주면 고칠게요. 답이 틀린 걸로 기록되지 않아요.</p>
      <div class="report-list">
        ${REPORT_KINDS.map(([k, label]) =>
          `<button class="report-pick" data-kind="${k}">${label}</button>`).join('')}
      </div>
      <textarea class="report-note" data-note rows="2" maxlength="300"
        placeholder="더 하고 싶은 말이 있으면 적어주세요 (안 적어도 돼요)"></textarea>
      <div style="display:flex; gap:8px; margin-top:6px">
        <button class="btn-ghost" style="flex:1" data-close>닫기</button>
        <button class="btn-primary" style="flex:1" data-send disabled>보내기</button>
      </div>
    </div>`;
  document.body.appendChild(back);
  const close = () => back.remove();
  let kind = null;
  const sendBtn = back.querySelector('[data-send]');
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  back.querySelector('[data-close]').addEventListener('click', close);
  back.querySelectorAll('[data-kind]').forEach((b) => b.addEventListener('click', () => {
    kind = b.dataset.kind;
    back.querySelectorAll('[data-kind]').forEach((x) => x.classList.toggle('on', x === b));
    sendBtn.disabled = false;
    sfx.select();
  }));
  sendBtn.addEventListener('click', async () => {
    if (!kind) return;
    sendBtn.disabled = true;
    try {
      await api('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({ question_id: questionId, kind, screen, note: back.querySelector('[data-note]').value }),
      });
      back.querySelector('.sheet').innerHTML =
        '<div class="sheet-grab"></div><h2>알려줘서 고마워요</h2>' +
        '<p class="card-note">덕분에 고칠 수 있어요. 계속 풀어볼까요?</p>' +
        '<button class="btn-primary" data-close2>계속하기</button>';
      back.querySelector('[data-close2]').addEventListener('click', close);
    } catch {
      sendBtn.disabled = false;
      sendBtn.textContent = '다시 보내기';
    }
  });
}

// 스크립트의 화자 표시(W:/M:/N:)는 음원 제작용 기호라 아이에게는 우리말로 바꿔 보여준다.
const SPEAKER_KO = { W: '여자', M: '남자', N: '안내' };
const readable = (s) => String(s ?? '').replace(/^([WMN]):/gm, (_, k) => `${SPEAKER_KO[k]}:`);

// 원문에서 근거 부분만 형광펜으로 칠한 HTML을 만든다 (나머지는 그대로 이스케이프).
function markEvidence(text, ev) {
  const i = text.indexOf(ev);
  if (i < 0) return esc(text);
  return esc(text.slice(0, i)) + `<mark class="ev">${esc(ev)}</mark>` + esc(text.slice(i + ev.length));
}

function renderQuestion() {
  const g = session.groups[session.gidx];
  const total = session.questions.length;
  const shownAt = Date.now();
  const lastGroup = session.gidx + 1 >= session.groups.length;
  const first = session.questions[g.items[0]];
  const passage = first.passage_id ? session.passages[first.passage_id] : null;
  const info = PART_INFO[first.part];
  const graded = new Set(g.items.filter((qi) => qi < session.doneBase && !session.diag));

  const chips = [
    `<span class="chip">${first.part} ${info.name}</span>`,
    first.accent ? `<span class="chip">${ACCENT_KO[first.accent] || first.accent}</span>` : '',
    first.status === 'draft' ? '<span class="chip warn">초안</span>' : '',
  ].join('');

  // ── 세트 공통 자료 (음원·지문은 세트당 1번) ──
  let media = '';
  const audioUrl = first.audio_url || passage?.audio_url;
  const script = first.script || (first.section === 'LC' ? passage?.content : null);
  if (audioUrl) {
    media = `<div class="audio-box" data-player>
        <button class="play-btn" data-play aria-label="다시 듣기">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13l11-6.5z"/></svg>
        </button>
        <div class="play-body">
          <div class="play-track"><div class="play-fill" data-fill></div></div>
          <p class="notice" data-play-note>소리가 한 번 나와요</p>
        </div>
        <button class="play-slow" data-slow>천천히</button>
      </div>`;
  } else if (script) {
    media = `<p class="notice">음원 준비 중 — 지금은 스크립트로 확인해요.</p>
      <button class="script-toggle" data-toggle>스크립트 보기</button>
      <div class="passage" data-script hidden>${esc(readable(script))}</div>`;
  }
  const readingPassage = (first.section === 'RC' && passage)
    ? `<div class="passage">${esc(passage.content)}</div>` : '';

  // ── 문제 블록들 (세트 아래 연속 배치) ──
  const blocks = g.items.map((qi, k) => {
    const q = session.questions[qi];
    let choiceImages = null;
    if (q.part === 'L1' && q.image_url?.startsWith('[')) {
      try { choiceImages = JSON.parse(q.image_url); } catch { choiceImages = null; }
    }
    const locked = graded.has(qi);
    const choicesHtml = choiceImages ? `
      <div class="choices img-grid">
        ${choiceImages.map((src, i) => `
          <button class="choice choice-img" data-idx="${i}" aria-label="보기 ${LETTERS[i]}" ${locked ? 'disabled' : ''}>
            <img src="${esc(src)}" alt="" loading="lazy" />
            <span class="letter">${LETTERS[i]}</span>
          </button>`).join('')}
      </div>` : `
      <div class="choices">
        ${q.choices.map((c, i) => `
          <button class="choice" data-idx="${i}" ${locked ? 'disabled' : ''}>
            <span class="letter">${LETTERS[i]}</span><span>${esc(c)}</span>
          </button>`).join('')}
      </div>`;
    return `
      <div class="qblock${locked ? ' locked' : ''}" data-block="${qi}">
        ${g.items.length > 1 ? `<p class="qnum">문제 ${k + 1}</p>` : ''}
        ${q.part === 'L1' && !choiceImages ? '<p class="notice">사진 준비 중인 문항이에요.</p>' : ''}
        ${q.stem ? `<p class="stem">${esc(q.stem)}</p>` : ''}
        ${choicesHtml}
        <div data-result>${locked ? '<p class="notice">지난 학습에서 이미 푼 문제예요.</p>' : ''}</div>
        ${locked || session.diag ? '' : ''}
        ${locked ? '' : `<button class="btn-primary btn-confirm" data-confirm disabled>선택 확정</button>`}
      </div>`;
  }).join('');

  view.innerHTML = `
    <div class="player-head">
      <button class="btn-ghost" data-back>나가기</button>
      <div class="progress-track"><div class="progress-fill" style="width:${(g.items[0] / total) * 100}%"></div></div>
      <span class="progress-num">${g.items[0] + 1}${g.items.length > 1 ? '–' + (g.items[g.items.length - 1] + 1) : ''}/${total}</span>
    </div>
    <div class="qcard">
      <div class="qbadges">${chips}</div>
      ${readingPassage}${media}
      ${blocks}
      ${session.diag ? '' : `<div class="nav-row"><button class="btn-primary" data-next disabled>${
        lastGroup ? '끝내기' : '다음'}</button></div>`}
    </div>`;

  // 음원 자동 재생 (세트당 1회 — 브라우저가 막으면 재생 버튼으로)
  const playerBox = view.querySelector('[data-player]');
  if (playerBox && audioUrl) {
    const fill = playerBox.querySelector('[data-fill]');
    const note = playerBox.querySelector('[data-play-note]');
    const btn = playerBox.querySelector('[data-play]');
    player.onTick = (p, playing) => {
      fill.style.width = `${(p * 100).toFixed(1)}%`;
      playerBox.classList.toggle('is-playing', playing);
      if (!playing) note.textContent = '다시 듣고 싶으면 ▶ 를 누르세요';
    };
    const go = (rate) => playClip(audioUrl, rate).catch(() => {
      note.textContent = '소리를 켜고 ▶ 를 눌러주세요';
    });
    btn.addEventListener('click', () => go(1));
    playerBox.querySelector('[data-slow]').addEventListener('click', () => go(0.75));
    go(1);
  }

  view.querySelector('[data-back]').addEventListener('click', () => {
    stopClip(); tabbarVisible(true); setTab('home'); showHome();
  });
  view.querySelector('[data-toggle]')?.addEventListener('click', (e) => {
    const box = view.querySelector('[data-script]');
    box.hidden = !box.hidden;
    e.target.textContent = box.hidden ? '스크립트 보기' : '스크립트 접기';
  });

  const nextBtn = view.querySelector('[data-next]');
  const advanceGroup = () => {
    stopClip();                 // 다음 문제로 넘어가면 앞 소리는 끊는다
    session.gidx += 1;
    renderQuestion();
    window.scrollTo({ top: 0, behavior: 'instant' });
  };
  const refreshNav = () => {
    const all = g.items.every((qi) => graded.has(qi));
    if (nextBtn) nextBtn.disabled = !all;
    if (session.diag && all) {
      setTimeout(() => {
        if (session.diag.answers.length >= total) return endDiagStage();
        advanceGroup();
      }, 250);
    }
  };
  nextBtn?.addEventListener('click', () => {
    if (nextBtn.disabled) return;
    if (lastGroup) return endSession();
    advanceGroup();
  });

  // ── 블록별 선택→확정 배선 ──
  g.items.forEach((qi) => {
    const q = session.questions[qi];
    const block = view.querySelector(`[data-block="${qi}"]`);
    if (!block || block.classList.contains('locked')) return;
    const buttons = [...block.querySelectorAll('.choice')];
    const confirmBtn = block.querySelector('[data-confirm]');
    let selected = null;
    let doneHere = false;

    buttons.forEach((btn) => btn.addEventListener('click', () => {
      if (doneHere) return;
      selected = Number(btn.dataset.idx);
      buttons.forEach((b) => b.classList.toggle('selected', b === btn));
      confirmBtn.disabled = false;
      sfx.select();
    }));

    confirmBtn.addEventListener('click', async () => {
      if (selected === null || doneHere) return;
      doneHere = true;
      confirmBtn.disabled = true;
      buttons.forEach((b) => (b.disabled = true));

      if (session.diag) {
        // 진단: 정오답을 보여주지 않고 기록만 (서버가 단계 끝에 일괄 채점)
        session.diag.answers.push({ question_id: q.id, chosen_idx: selected, time_ms: Date.now() - shownAt });
        block.classList.add('locked');
        confirmBtn.remove();
        graded.add(qi);
        refreshNav();
        block.nextElementSibling?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
        return;
      }

      try {
        const payload = JSON.stringify({ question_id: q.id, chosen_idx: selected, time_ms: Date.now() - shownAt });
        let r = null;
        if (auth) {
          try {
            r = await api('/api/answers', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${auth.token}` },
              body: payload,
            });
          } catch (e) {
            if (/로그인/.test(e.message)) saveAuth(null);
            else throw e;
          }
        }
        r = r || await api('/api/check', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload,
        });
        buttons.forEach((b, i) => {
          b.classList.remove('selected');
          if (i === r.answer_idx) b.classList.add('correct');
          else if (i === selected && !r.correct) b.classList.add('wrong');
          else b.classList.add('dim');
        });
        // ── 근거 보여주기: 글보다 먼저 "어디를 보고 푸는지"를 눈으로 짚어준다 ──
        // 원문이 이미 화면에 있으면 그 자리를 칠하고, 없으면(듣기 등) 원문째로 보여준다.
        let evHtml = '';
        if (r.evidence && r.evidence_text) {
          const spots = [...view.querySelectorAll('.passage'), ...block.querySelectorAll('.stem')];
          const spot = spots.find((el) => el.textContent.includes(r.evidence));
          if (spot) {
            spot.hidden = false;
            const toggle = view.querySelector('[data-toggle]');
            if (toggle) toggle.textContent = '스크립트 접기';
            spot.innerHTML = markEvidence(spot.textContent, r.evidence);  // 이전 표시는 지워짐
            // 짧은 근거는 한 번 더 짚어 주고, 긴 문장은 위에 칠한 곳만 가리킨다(중복 방지)
            evHtml = r.evidence.length <= 20
              ? `<p class="ev-hint"><mark class="ev">${esc(r.evidence)}</mark> — 여기가 힌트예요</p>`
              : '<p class="ev-hint">위에 노란색으로 칠한 곳이 힌트예요</p>';
          } else {
            evHtml = `<div class="ev-box"><p class="ev-cap">여기가 힌트예요</p>
              <p class="ev-text">${markEvidence(readable(r.evidence_text), r.evidence)}</p></div>`;
          }
        }
        const replay = audioUrl
          ? '<button class="ev-replay" data-replay>천천히 다시 듣기</button>' : '';
        // 내가 고른 보기만 콕 집어 "왜 아닌지" — 다른 오답까지 늘어놓으면 안 읽는다
        const whyHtml = r.why_not ? `
          <div class="why-not">
            <span class="why-letter">${LETTERS[selected]}</span>
            <span>${esc(r.why_not)}</span>
          </div>` : '';
        // 오늘 챙길 표현 카드 한 장
        const expr = r.key_expr;
        const exprHtml = expr ? `
          <div class="expr-card">
            <p class="expr-cap">이 문제에서 챙길 표현</p>
            <p class="expr-en">${esc(expr.en)}</p>
            <p class="expr-ko">${esc(expr.ko)}</p>
          </div>` : '';
        // 개념 그림 — 틀렸으면 펼쳐서, 맞았으면 접어서 (화면이 길어지지 않게)
        const con = conceptOf(r.concept);
        const conHtml = con ? `
          <details class="concept" ${r.correct ? '' : 'open'}>
            <summary>${esc(con.title)}</summary>
            <div class="concept-body">${con.svg}</div>
          </details>` : '';
        block.querySelector('[data-result]').innerHTML = `
          <div class="result ${r.correct ? 'ok' : 'bad'}">
            <p class="verdict">${r.graduated ? '4연승! 이 문제를 봉인 앨범에 박제했어요' : r.correct ? '정답이에요!' : '아쉬워요, 다시 볼까요?'}</p>
            ${whyHtml}${evHtml}${replay}
            <p>${esc(r.explanation_ko)}</p>
            ${conHtml}${exprHtml}
            <button class="report-link" data-report>이 문제, 이상해요</button>
          </div>`;
        block.querySelector('[data-report]').addEventListener('click', () =>
          showReport(q.id, `문제풀이:${q.part}`));
        if (expr) rememberExpr(q, expr, r.correct);
        block.querySelector('[data-replay]')?.addEventListener('click', () => {
          if (audioUrl) playClip(audioUrl, 0.75).catch(() => { /* 소리 꺼짐 */ });
        });
        (r.graduated ? sfx.done : r.correct ? sfx.correct : sfx.wrong)();
        if (r.correct) session.correct += 1;
        recordAnswer(q, passage, r.correct);
        if (session.trackToday) { store.setIdx = Math.min(total, store.setIdx + 1); save(); }
        confirmBtn.remove();
        graded.add(qi);
        refreshNav();
        if (!g.items.every((x) => graded.has(x))) {
          block.nextElementSibling?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
        }
      } catch (e) {
        doneHere = false;
        confirmBtn.disabled = false;
        buttons.forEach((b) => (b.disabled = false));
        block.querySelector('[data-result]').innerHTML =
          `<div class="result bad"><p>${esc(e.message)}</p></div>`;
      }
    });
  });
}

showHome();
