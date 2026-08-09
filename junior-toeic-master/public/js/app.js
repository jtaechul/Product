// 점프리시 — 학생 화면 (모바일 세로)
// 첫 화면은 "무엇을 풀지 고르는 곳"이 아니라 "오늘 뭘 해야 하는지 알려주는 곳"이다.
// 파트를 직접 고르는 화면은 하단 '파트별' 탭으로 내렸다.
//
// 정답은 이 앱 어디에도 없다: 보기를 누르면 POST /api/check 가 채점·해설을 반환한다.
// M1은 로그인 전이라 학습 기록을 이 기기(localStorage)에 보관한다.
// M2에서 계정이 붙으면 서버의 user_skills·SRS 큐로 옮긴다.

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
const blank = { parts: {}, wrong: [], days: [], set: null, setDate: null, setIdx: 0 };
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
// 실제 사운드 파일(/sfx/*.mp3 — Freesound CC0, sfx-batch.mjs로 다운로드)이 있으면
// 그걸 쓰고, 아직 없거나 재생이 막히면 합성음으로 대체한다.
const SFX_VOL = { select: 0.25, correct: 0.4, wrong: 0.3, done: 0.45 };
const sfxPlayers = {};
function playSfx(name, fallback) {
  let a = sfxPlayers[name];
  if (a === null) return fallback();          // 파일 없음이 확인된 상태
  if (!a) {
    a = sfxPlayers[name] = new Audio(`/sfx/${name}.mp3`);
    a.preload = 'auto';
    a.volume = SFX_VOL[name] ?? 0.35;
  }
  a.currentTime = 0;
  a.play().catch(() => { sfxPlayers[name] = null; fallback(); });
}
const sfx = {
  select: () => playSfx('select', () => sfxTone([[880, 0, 0.05]], 'sine', 0.035)),
  correct: () => playSfx('correct', () => sfxTone([[659.25, 0, 0.12], [987.77, 0.09, 0.22]])),
  wrong: () => playSfx('wrong', () => sfxTone([[196, 0, 0.2]], 'square', 0.04)),
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

// ---------- 탭 ----------
let currentTab = 'home';
function setTab(name) {
  currentTab = name;
  tabbar.querySelectorAll('.tab').forEach((b) => {
    if (b.dataset.tab === name) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
}
tabbar.addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  setTab(btn.dataset.tab);
  ({ home: showHome, review: showReview, record: showRecord, parts: showParts }[btn.dataset.tab])();
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

const levelOf = (acc) =>
  acc === null ? 'lv-none' : acc >= 80 ? 'lv-high' : acc >= 60 ? 'lv-mid' : 'lv-low';

// 듣기 4칸 · 읽기 3칸을 같은 폭에 나눠 두 줄의 오른쪽 끝을 맞추고,
// 그 옆에 두 줄 높이를 다 쓰는 전체 평균 칸을 세운다.
function skillMap() {
  const weakest = ranked()[0]?.part;
  const cell = (p) => {
    const acc = accuracy(p);
    const weak = acc !== null && p === weakest ? ' is-weak' : '';
    return `<div class="skill ${levelOf(acc)}${weak}">
      <span class="code">${p}</span><span class="val">${acc === null ? '–' : acc}</span></div>`;
  };
  const answered = totalAnswered();
  const avg = answered ? Math.round((totalCorrect() / answered) * 100) : null;
  return `<div class="skillmap">
    <div class="skill-rows">
      <div class="skill-row lc">${['L1', 'L2', 'L3', 'L4'].map(cell).join('')}</div>
      <div class="skill-row rc">${['R1', 'R2', 'R3'].map(cell).join('')}</div>
    </div>
    <div class="skill-avg ${levelOf(avg)}">
      <span class="code">전체 평균</span>
      <span class="val">${avg === null ? '–' : avg}</span>
    </div>
  </div>`;
}

async function showHome() {
  setTab('home');
  tabbarVisible(true);
  view.innerHTML = '<p class="loading">오늘의 학습을 준비하고 있어요...</p>';
  try {
    const set = await ensureTodaySet();
    // 다시 볼 문제 수: 로그인은 서버 SRS 큐(오늘 도래분), 게스트는 이 기기 기록
    let reviewN = store.wrong.length;
    let me = null;
    if (auth) {
      try { me = await api('/api/me', { headers: authHeaders() }); reviewN = me.review_due; } catch { /* 무시 */ }
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
      <button class="card row" data-diag>
        <span class="row-ico" style="background:var(--primary-soft);color:var(--primary)">
          <svg viewBox="0 0 16 16"><path d="M2 13.5h12M4.5 13.5V7M8 13.5V3.5M11.5 13.5V9.5"/></svg>
        </span>
        <span class="row-body">
          <span class="row-t">첫 실력 진단 받기</span>
          <span class="row-s">약 10~15분 · 끝나면 매일 학습이 내 실력에 딱 맞춰져요</span>
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
              읽기 ${set.questions.filter((q) => q.section === 'RC').length}</p>
            <p class="sub">약 10분</p>
          </div>
        </div>
        <button class="btn-hero" data-start>${
          left === 0 ? '다시 풀어보기' : doneN > 0 ? '이어서 풀기' : '시작하기'}</button>
      </div>

      <div class="card">
        <div class="card-head">
          <span class="card-title">내 실력 지도</span>
          <span class="card-note">${answered ? `${answered}문항 기준` : '아직 기록 없음'}</span>
        </div>
        ${skillMap()}
      </div>

      ${focusCard}

      <button class="card row" data-tab-go="review">
        <span class="row-ico"><svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.4"/><path d="M8 4.5v4M8 11.2v.1"/></svg></span>
        <span class="row-body">
          <span class="row-t">오늘의 리매치 ${reviewN}판</span>
          <span class="row-s">${reviewN ? '틀렸던 문제에게 설욕할 시간이에요' : '틀린 문제가 생기면 여기서 다시 만나요'}</span>
        </span>
        <svg class="row-arrow" viewBox="0 0 16 16"><path d="M6 3.5 10.5 8 6 12.5"/></svg>
      </button>`;

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
async function showReview() {
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
        <div class="greet"><div>
          <p class="greet-date">4연승하면 그 문제는 영원히 봉인됩니다</p>
          <h1 class="greet-title">오늘의 리매치 ${r.count}판</h1>
        </div></div>
        <button class="btn-hero" style="background:var(--primary);color:#fff" data-review-start>리매치 시작</button>
        <div class="card"><div class="rowlist">${list}</div></div>`;
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
    view.innerHTML = `<div class="greet"><div><h1 class="greet-title">다시 풀 문제</h1></div></div>
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
  let sealed = null;
  if (auth) { try { sealed = (await api('/api/me', { headers: authHeaders() })).sealed; } catch { /* 무시 */ } }
  const answered = totalAnswered();
  const acc = answered ? Math.round((totalCorrect() / answered) * 100) : 0;
  view.innerHTML = `
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
      <div class="greet"><div>
        <p class="greet-date">골라서 더 풀고 싶을 때</p>
        <h1 class="greet-title">연습장</h1>
      </div></div>
      <p class="section-label">듣기 (Listening)</p>
      <div class="part-grid">${['L1', 'L2', 'L3', 'L4'].map(card).join('')}</div>
      <p class="section-label">읽기 (Reading)</p>
      <div class="part-grid">${['R1', 'R2', 'R3'].map(card).join('')}</div>`;
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
    media = `<div class="audio-box"><audio controls preload="auto" src="${esc(audioUrl)}"></audio>
      <p class="notice">음원은 자동으로 1번 나와요. 더 듣고 싶으면 재생 버튼을 누르세요.</p></div>`;
  } else if (script) {
    media = `<p class="notice">음원 준비 중 — 지금은 스크립트로 확인해요.</p>
      <button class="script-toggle" data-toggle>스크립트 보기</button>
      <div class="passage" data-script hidden>${esc(script)}</div>`;
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
        ${q.part === 'L1' && !choiceImages ? '<p class="notice">그림 준비 중인 문항이에요.</p>' : ''}
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
  const au = view.querySelector('audio');
  if (au) au.play().catch(() => { /* 수동 재생 안내는 이미 표시됨 */ });

  view.querySelector('[data-back]').addEventListener('click', () => { tabbarVisible(true); setTab('home'); showHome(); });
  view.querySelector('[data-toggle]')?.addEventListener('click', (e) => {
    const box = view.querySelector('[data-script]');
    box.hidden = !box.hidden;
    e.target.textContent = box.hidden ? '스크립트 보기' : '스크립트 접기';
  });

  const nextBtn = view.querySelector('[data-next]');
  const advanceGroup = () => {
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
        block.querySelector('[data-result]').innerHTML = `
          <div class="result ${r.correct ? 'ok' : 'bad'}">
            <p class="verdict">${r.graduated ? '4연승! 이 문제를 봉인 앨범에 박제했어요' : r.correct ? '정답이에요!' : '아쉬워요, 다시 볼까요?'}</p>
            <p>${esc(r.explanation_ko)}</p>
          </div>`;
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
