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
    if (auth) {
      try { reviewN = (await api('/api/me', { headers: authHeaders() })).review_due; } catch { /* 무시 */ }
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
          <span class="row-t">다시 볼 문제 ${reviewN}개</span>
          <span class="row-s">${reviewN ? '오늘 복습하면 잊지 않아요' : '틀린 문제가 모이면 여기서 복습해요'}</span>
        </span>
        <svg class="row-arrow" viewBox="0 0 16 16"><path d="M6 3.5 10.5 8 6 12.5"/></svg>
      </button>`;

    view.querySelector('[data-login]')?.addEventListener('click', showLogin);
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

// ---------- 오답 ----------
async function showReview() {
  setTab('review');
  tabbarVisible(true);
  if (auth) {
    view.innerHTML = '<p class="loading">복습할 문제를 찾는 중...</p>';
    try {
      const r = await api('/api/review', { headers: authHeaders() });
      if (!r.count) {
        view.innerHTML = `<div class="greet"><div><h1 class="greet-title">다시 풀 문제</h1></div></div>
          <div class="card"><p class="empty">오늘 복습할 문제가 없어요.<br>틀린 문제는 1일 → 3일 → 7일 → 14일 뒤에 다시 나와요.</p></div>`;
        return;
      }
      const list = r.questions.map((q) => `
        <div class="row">
          <span class="row-ico">${q.part}</span>
          <span class="row-body">
            <span class="row-t">${esc(q.stem || PART_INFO[q.part].name)}</span>
            <span class="row-s">${PART_INFO[q.part].name} · ${q.srs_box}번째 복습</span>
          </span>
        </div>`).join('');
      view.innerHTML = `
        <div class="greet"><div>
          <p class="greet-date">틀린 문제는 다시 만나야 내 것이 돼요</p>
          <h1 class="greet-title">오늘 복습할 문제 ${r.count}개</h1>
        </div></div>
        <button class="btn-hero" style="background:var(--primary);color:#fff" data-review-start>복습 시작</button>
        <div class="card"><div class="rowlist">${list}</div></div>`;
      view.querySelectorAll('.row-ico').forEach((el) => {
        el.style.cssText += 'font-size:.74rem;font-weight:700;background:var(--primary-soft);color:var(--primary)';
      });
      view.querySelector('[data-review-start]').addEventListener('click', () =>
        startSession(r.questions, r.passages, '오답 복습'));
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
function showRecord() {
  setTab('record');
  tabbarVisible(true);
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
    trackToday: !!opts.trackToday,
    idx: opts.trackToday ? Math.min(store.setIdx, questions.length - 1) : 0,
  });
  tabbarVisible(false);
  renderQuestion();
}

function endSession() {
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
  const shownAt = Date.now();  // time_ms 측정 기준 (찍기 판정에 쓰인다)
  const q = session.questions[session.idx];
  const passage = q.passage_id ? session.passages[q.passage_id] : null;
  const info = PART_INFO[q.part];
  const total = session.questions.length;

  const chips = [
    `<span class="chip">${q.part} ${info.name}</span>`,
    `<span class="chip">난이도 ${q.difficulty_label}</span>`,
    q.accent ? `<span class="chip">${ACCENT_KO[q.accent] || q.accent}</span>` : '',
    q.status === 'draft' ? '<span class="chip warn">초안</span>' : '',
  ].join('');

  // 듣기 자료: 음원이 있으면 플레이어, 없으면 스크립트 열람(검수용)
  let media = '';
  const audioUrl = q.audio_url || passage?.audio_url;
  const script = q.script || (q.section === 'LC' ? passage?.content : null);
  if (audioUrl) {
    media = `<div class="audio-box"><audio controls preload="none" src="${esc(audioUrl)}"></audio></div>`;
  } else if (script) {
    media = `<p class="notice">음원 준비 중 — 지금은 스크립트로 확인해요.</p>
      <button class="script-toggle" data-toggle>스크립트 보기</button>
      <div class="passage" data-script hidden>${esc(script)}</div>`;
  }
  // L1: image_url에 보기 4컷 경로 배열(JSON)이 실려 오면 그림 보기로 렌더한다
  let choiceImages = null;
  if (q.part === 'L1' && q.image_url?.startsWith('[')) {
    try { choiceImages = JSON.parse(q.image_url); } catch { choiceImages = null; }
  }
  if (q.part === 'L1' && !choiceImages) {
    media = '<p class="notice">그림 준비 중인 문항이에요. 스크립트로 확인해요.</p>' + media;
  }

  const readingPassage = (q.section === 'RC' && passage)
    ? `<div class="passage">${esc(passage.content)}</div>` : '';

  view.innerHTML = `
    <div class="player-head">
      <button class="btn-ghost" data-back>나가기</button>
      <div class="progress-track"><div class="progress-fill" style="width:${(session.idx / total) * 100}%"></div></div>
      <span class="progress-num">${session.idx + 1}/${total}</span>
    </div>
    <div class="qcard">
      <div class="qbadges">${chips}</div>
      ${readingPassage}${media}
      ${q.stem ? `<p class="stem">${esc(q.stem)}</p>` : ''}
      ${choiceImages ? `
      <div class="choices img-grid">
        ${choiceImages.map((src, i) => `
          <button class="choice choice-img" data-idx="${i}" aria-label="보기 ${LETTERS[i]}">
            <img src="${esc(src)}" alt="" loading="lazy" />
            <span class="letter">${LETTERS[i]}</span>
          </button>`).join('')}
      </div>` : `
      <div class="choices">
        ${q.choices.map((c, i) => `
          <button class="choice" data-idx="${i}">
            <span class="letter">${LETTERS[i]}</span><span>${esc(c)}</span>
          </button>`).join('')}
      </div>`}
      <div data-result></div>
      <div class="nav-row"><button class="btn-primary" data-next disabled>${
        session.idx + 1 >= total ? '끝내기' : '다음 문제'}</button></div>
    </div>`;

  view.querySelector('[data-back]').addEventListener('click', () => { tabbarVisible(true); setTab('home'); showHome(); });
  view.querySelector('[data-toggle]')?.addEventListener('click', (e) => {
    const box = view.querySelector('[data-script]');
    box.hidden = !box.hidden;
    e.target.textContent = box.hidden ? '스크립트 보기' : '스크립트 접기';
  });

  const nextBtn = view.querySelector('[data-next]');
  nextBtn.addEventListener('click', () => {
    if (session.idx + 1 >= total) return endSession();
    session.idx += 1;
    if (session.trackToday) { store.setIdx = session.idx; save(); }
    renderQuestion();
    window.scrollTo({ top: 0, behavior: 'instant' });
  });

  const buttons = [...view.querySelectorAll('.choice')];
  buttons.forEach((btn) => btn.addEventListener('click', async () => {
    buttons.forEach((b) => (b.disabled = true));
    try {
      const payload = JSON.stringify({
        question_id: q.id, chosen_idx: Number(btn.dataset.idx), time_ms: Date.now() - shownAt,
      });
      let r = null;
      if (auth) {
        // 로그인 상태면 서버에 기록(실력 갱신·오답 SRS 포함). 토큰 만료 시 게스트로 강등.
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
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
      });
      buttons.forEach((b, i) => {
        if (i === r.answer_idx) b.classList.add('correct');
        else if (b === btn && !r.correct) b.classList.add('wrong');
        else b.classList.add('dim');
      });
      view.querySelector('[data-result]').innerHTML = `
        <div class="result ${r.correct ? 'ok' : 'bad'}">
          <p class="verdict">${r.correct ? '정답이에요!' : '아쉬워요, 다시 볼까요?'}</p>
          <p>${esc(r.explanation_ko)}</p>
        </div>`;
      if (r.correct) session.correct += 1;
      recordAnswer(q, passage, r.correct);
      if (session.trackToday) { store.setIdx = session.idx + 1; save(); }
      nextBtn.disabled = false;
      nextBtn.focus();
    } catch (e) {
      buttons.forEach((b) => (b.disabled = false));
      view.querySelector('[data-result]').innerHTML =
        `<div class="result bad"><p>${esc(e.message)}</p></div>`;
    }
  }));
}

showHome();
