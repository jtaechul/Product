// 점프리시 학부모 화면 — 읽기만 하는 화면. 자녀 딱 한 명만 보인다.
//
// 설계 원칙: 부모는 숫자를 읽으러 오지 않는다. "잘하고 있나? 내가 뭘 해주면 되나?"
// 이 두 가지에 답하는 게 전부다. 그래서 맨 위에 한 문장으로 답하고,
// 그 아래 근거(실력 지도·자주 걸리는 실수)를, 맨 아래에 오늘 할 일을 둔다.
//
// 아이 앱과 절대 섞이지 않는다: 로그인 열쇠도, 토큰도 다르다.
// 부모는 문제를 풀 수도, 아이 이름을 바꿀 수도 없다(읽기 API만 있다).

const view = document.getElementById('view');
const AUTH_KEY = 'jumplish.parent.v1';

let auth = null;
try { auth = JSON.parse(localStorage.getItem(AUTH_KEY) || 'null'); } catch { auth = null; }
const saveAuth = (a) => {
  auth = a;
  try { a ? localStorage.setItem(AUTH_KEY, JSON.stringify(a)) : localStorage.removeItem(AUTH_KEY); }
  catch { /* 무시 */ }
};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (m) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: {
      ...(opts.body ? { 'Content-Type': 'application/json' } : {}),
      ...(auth ? { Authorization: `Bearer ${auth.token}` } : {}),
      ...opts.headers,
    },
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `오류가 났어요 (${r.status})`);
  return data;
}

const BRAND = `<div class="p-brand">
  <span class="appbar-mark"><svg viewBox="0.5 4 23 17" aria-hidden="true">
    <path d="M1.5 20 L6 13.5 L10.5 20 Z" fill="#fff" opacity=".4"/>
    <path d="M7 20 L12 10 L17 20 Z" fill="#fff" opacity=".7"/>
    <path d="M13 20 L18 5.5 L23 20 Z" fill="#fff"/>
  </svg></span><span class="t">점프리시</span></div>`;

// ── 들어오는 문 ──
// 학부모가 직접 가입하는 길 하나뿐이다. 학원을 거쳐 들어오는 화면은 두지 않는다
// (학원 영업을 하지 않기로 했다 — 학부모가 고객이다).
const err = (el, m) => { el.innerHTML = `<div class="result bad"><p>${esc(m)}</p></div>`; };

function showLogin(prefill = '') {
  view.innerHTML = `
    <div class="card p-login">
      ${BRAND}
      <div><h1 class="greet-title" style="font-size:1.15rem">우리 아이 학습 보기</h1>
        <p class="card-note" style="margin-top:4px">가입하신 <b>이메일</b>과 <b>비밀번호</b>를 넣어주세요.</p></div>
      <label class="field" style="margin-top:12px"><span>이메일</span>
        <input data-email type="email" autocapitalize="off" autocomplete="username"
          inputmode="email" placeholder="parent@example.com" /></label>
      <label class="field" style="margin-top:10px"><span>비밀번호</span>
        <input data-pw type="password" autocomplete="current-password" placeholder="••••••••" /></label>
      <button class="btn-primary" data-go style="margin-top:12px">보기</button>
      <div data-msg></div>
      <p class="card-note" style="margin-top:10px">처음이신가요?
        <button class="p-link" data-signup>무료로 시작하기</button></p>
    </div>`;
  const msg = view.querySelector('[data-msg]');
  const go = async () => {
    const email = view.querySelector('[data-email]').value.trim();
    const password = view.querySelector('[data-pw]').value;
    if (!email || !password) return err(msg, '이메일과 비밀번호를 넣어주세요.');
    try {
      const r = await api('/api/parent/login-email', {
        method: 'POST', body: JSON.stringify({ email, password }) });
      saveAuth({ token: r.token, parent: r.parent, kind: 'account' });
      showHome();
    } catch (e) { err(msg, e.message); }
  };
  view.querySelector('[data-go]').addEventListener('click', go);
  view.querySelector('[data-signup]').addEventListener('click', showSignup);
  view.querySelectorAll('input').forEach((i) =>
    i.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); }));
}

// ── 가입 ──
// 아이 계정을 만드는 절차라 보호자 동의를 여기서 받는다. 동의 없이는 다음으로 못 간다.
// 아이에게는 이메일도 비밀번호도 만들게 하지 않는다 — 아이 몫은 아이디와 6자리 숫자뿐이다.
function showSignup() {
  view.innerHTML = `
    <div class="card p-login">
      ${BRAND}
      <div><h1 class="greet-title" style="font-size:1.15rem">무료로 시작하기</h1>
        <p class="card-note" style="margin-top:4px">보호자가 먼저 가입하고, 아이 계정을 만들어 주세요.
          <b>하루 1세트는 계속 무료</b>입니다.</p></div>

      <label class="field" style="margin-top:12px"><span>보호자 이메일</span>
        <input data-email type="email" autocapitalize="off" autocomplete="username"
          inputmode="email" placeholder="parent@example.com" /></label>
      <label class="field" style="margin-top:10px"><span>비밀번호 (8자 이상)</span>
        <input data-pw type="password" autocomplete="new-password" placeholder="••••••••" /></label>
      <label class="field" style="margin-top:10px"><span>보호자 이름</span>
        <input data-name maxlength="12" autocomplete="name" placeholder="예: 김보호" /></label>
      <label class="field" style="margin-top:10px"><span>아이 이름</span>
        <input data-child maxlength="12" placeholder="예: 김하늘" /></label>

      <label class="p-consent" style="margin-top:14px">
        <input type="checkbox" data-consent />
        <span>만 14세 미만 자녀의 계정을 <b>보호자인 제가</b> 만드는 것에 동의합니다.
          아이 계정에는 이메일·전화번호를 저장하지 않으며, 학습 기록만 남습니다.</span>
      </label>

      <button class="btn-primary" data-go style="margin-top:12px">가입하고 아이 계정 만들기</button>
      <div data-msg></div>
      <p class="card-note" style="margin-top:10px">이미 가입하셨나요?
        <button class="p-link" data-back>로그인</button></p>
    </div>`;
  const msg = view.querySelector('[data-msg]');
  const go = async () => {
    const body = {
      email: view.querySelector('[data-email]').value.trim(),
      password: view.querySelector('[data-pw]').value,
      name: view.querySelector('[data-name]').value.trim(),
      child_name: view.querySelector('[data-child]').value.trim(),
      consent: view.querySelector('[data-consent]').checked,
    };
    if (!body.consent) return err(msg, '보호자 동의에 체크해주세요.');
    try {
      const r = await api('/api/parent/signup', { method: 'POST', body: JSON.stringify(body) });
      saveAuth({ token: r.token, parent: r.parent, kind: 'account' });
      showChildren();
    } catch (e) { err(msg, e.message); }
  };
  view.querySelector('[data-go]').addEventListener('click', go);
  view.querySelector('[data-back]').addEventListener('click', () => showLogin());
}

// ── 아이 관리 ──
function showChildren() {
  view.innerHTML = '<p class="loading">불러오는 중...</p>';
  api('/api/parent/children').then((d) => {
    const rows = d.children.map((ch) => `
      <div class="p-kid">
        <span class="p-kid-b"><span class="p-kid-n">${esc(ch.display_name)}</span></span>
      </div>`).join('');
    view.innerHTML = `
      ${BRAND}
      <div class="greet"><div>
        <p class="greet-date">${esc(d.parent.display_name)}님</p>
        <h1 class="greet-title">우리 아이</h1>
      </div></div>
      <div class="card">
        <div class="card-head"><span class="card-title">등록한 아이</span></div>
        ${rows || '<p class="empty">아직 등록한 아이가 없어요.</p>'}
        <p class="p-warn" style="margin-top:12px">아이는 <b>지금 로그인하신 이메일과 비밀번호</b>로
          앱에 들어갑니다. 아이에게 따로 만들어 줄 아이디는 없어요.</p>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">아이 추가</span>
          <span class="card-note">최대 3명</span></div>
        <label class="field"><span>아이 이름</span>
          <input data-new maxlength="12" placeholder="예: 김바다" /></label>
        <button class="btn-primary" data-add style="margin-top:10px">아이 추가</button>
        <div data-msg></div>
      </div>
      ${d.children.length ? '<p class="p-out"><button data-home>학습 기록 보기</button></p>' : ''}
      <p class="p-out"><button data-out>로그아웃</button></p>`;

    const msg = view.querySelector('[data-msg]');
    view.querySelector('[data-add]').addEventListener('click', async () => {
      const name = view.querySelector('[data-new]').value.trim();
      if (!name) return err(msg, '아이 이름을 넣어주세요.');
      try {
        await api('/api/parent/children', { method: 'POST', body: JSON.stringify({ name }) });
        showChildren();
      } catch (e) { err(msg, e.message); }
    });
    view.querySelector('[data-home]')?.addEventListener('click', () => showHome());
    view.querySelector('[data-out]').addEventListener('click', () => { saveAuth(null); showLogin(); });
  }).catch((e) => {
    if (/로그인/.test(e.message)) { saveAuth(null); showLogin(); return; }
    view.innerHTML = `<div class="card"><p class="empty">${esc(e.message)}</p></div>`;
  });
}


// ── 한 줄 판정 ──
// 부모가 이 문장 하나만 읽고 나가도 손해가 없게 쓴다. 점수가 아니라 '요즘 어떤가'다.
function verdict(d) {
  const done = d.today_n > 0;
  const week = d.recent_days.filter((r) => r.n > 0).length;   // 최근 2주 중 학습한 날
  if (!d.answered) {
    return { eyebrow: '아직 시작 전', line: '아직 문제를 풀지 않았어요',
      sub: '앱에 처음 들어가면 실력을 재는 짧은 테스트부터 합니다.' };
  }
  if (d.streak >= 5) {
    return { eyebrow: '요즘', line: `${d.streak}일 이어서 하고 있어요`,
      sub: done ? '오늘 몫도 이미 끝냈습니다.' : '오늘 몫은 아직이에요.' };
  }
  if (week >= 7) {
    return { eyebrow: '요즘', line: '꾸준히 하고 있어요',
      sub: `최근 2주 중 ${week}일 학습했어요.` };
  }
  if (week >= 3) {
    return { eyebrow: '요즘', line: '가끔 하고 있어요',
      sub: `최근 2주 중 ${week}일 학습했어요. 며칠 이어지면 훨씬 빨리 늘어요.` };
  }
  return { eyebrow: '요즘', line: '한동안 쉬고 있어요',
    sub: `최근 2주 중 ${week}일 학습했어요. 하루 10분이면 충분합니다.` };
}

// 부모가 오늘 뭘 하면 되는지 — 데이터에서 나오는 것만 쓴다(빈말 금지)
function tips(d) {
  const out = [];
  if (!d.today_n) out.push(['오늘 10분만 같이 앉아주세요', '앱을 열어 "오늘의 학습"만 끝내면 됩니다.']);
  const m = d.misses?.[0];
  if (m) out.push([`"${m.name}"`, `요즘 ${m.n}번 이렇게 틀렸어요. 문제를 다시 읽어보게 해주세요.`]);
  const ready = (d.axes ?? []).filter((a) => a.score != null);
  if (ready.length) {
    const weak = ready.reduce((x, a) => (a.score < x.score ? a : x));
    out.push([`${weak.name}가 아직 약해요`, '앱이 이 부분을 매일 조금씩 더 넣어주고 있어요.']);
  }
  if (d.revive && d.revive.rate >= 60) {
    out.push(['틀린 문제를 다시 만나 이기고 있어요', `다시 만난 ${d.revive.met}판 중 ${d.revive.won}판을 맞혔어요. 칭찬해주세요.`]);
  }
  if (!out.length) out.push(['조금 더 풀면 보여드릴 게 많아져요', '며칠 쌓이면 약한 곳과 실수 유형이 나옵니다.']);
  return out.slice(0, 3);
}

const WEEKDAY = ['일', '월', '화', '수', '목', '금', '토'];

let currentChildId = null;   // 아이가 여럿일 때 지금 보고 있는 아이

async function showHome(childId = currentChildId) {
  view.innerHTML = '<p class="loading">불러오는 중...</p>';
  let d;
  try {
    d = await api('/api/parent/overview' + (childId ? `?child_id=${encodeURIComponent(childId)}` : ''));
  } catch (e) {
    if (/로그인이 필요/.test(e.message)) { saveAuth(null); showLogin(); return; }
    // 가입은 했는데 아이를 아직 안 만든 경우 — 막다른 화면 대신 아이 만드는 곳으로 보낸다
    if (/아이를 먼저/.test(e.message)) { showChildren(); return; }
    view.innerHTML = `<div class="card"><p class="empty">${esc(e.message)}</p></div>`;
    return;
  }
  currentChildId = d.child.id;
  const v = verdict(d);
  // 오늘이 며칠인지는 서버(한국 시간)를 따른다. 기기 시계로 계산하면 해외에서 보거나
  // 자정~오전 9시 사이에 볼 때 하루가 밀려, 오늘 한 것이 어제 칸에 칠해진다.
  const today = d.today;

  // 최근 2주 출석 — 날짜별 점. 부모는 이 줄에서 '꾸준한가'를 한눈에 읽는다
  const byDay = Object.fromEntries(d.recent_days.map((r) => [r.d, r.n]));
  const dots = Array.from({ length: 14 }, (_, i) => {
    const dt = new Date(`${today}T00:00:00Z`);
    dt.setUTCDate(dt.getUTCDate() - (13 - i));
    const key = dt.toISOString().slice(0, 10);
    const on = (byDay[key] ?? 0) > 0;
    return `<span class="dot-day${on ? ' on' : ''}${key === today ? ' is-today' : ''}"
      title="${key} ${byDay[key] ?? 0}문항">${WEEKDAY[dt.getUTCDay()]}</span>`;
  }).join('');

  const acc = d.answered ? Math.round((d.correct / d.answered) * 100) : 0;
  const ready = (d.axes ?? []).filter((a) => a.score != null);
  const bars = [...ready].sort((a, b) => a.score - b.score).map((a) => `
    <div class="sbar">
      <span class="sbl">${esc(a.name)}</span>
      <span class="sbt"><span class="sbf" style="width:${a.score}%"></span></span>
      <span class="sbn">${a.score}</span>
    </div>`).join('');

  // 아이가 둘 이상일 때만 고르는 줄을 보여준다. 한 명이면 화면이 그대로다.
  const tabs = (d.children?.length > 1) ? `<div class="p-kidtabs">${d.children.map((ch) => `
    <button class="p-kidtab${ch.id === d.child.id ? ' on' : ''}"
      data-kid="${esc(ch.id)}">${esc(ch.display_name)}</button>`).join('')}</div>` : '';

  view.innerHTML = `
    ${BRAND}
    ${tabs}
    <div class="greet"><div>
      <p class="greet-date">${esc(d.child.display_name)}${d.class ? ` · ${esc(d.class.name)}` : ''}</p>
      <h1 class="greet-title">우리 아이 학습</h1>
    </div></div>

    <div class="verdict">
      <p class="verdict-eyebrow">${esc(v.eyebrow)}</p>
      <p class="verdict-line">${esc(v.line)}</p>
      <p class="verdict-sub">${esc(v.sub)}</p>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">최근 2주</span>
        <span class="card-note">색이 칠해진 날 = 공부한 날</span></div>
      <div class="dots">${dots}</div>
      <div class="stat-row" style="margin-top:12px">
        <div class="stat"><span class="label">이어온 날</span><span class="value">${d.streak}일</span></div>
        <div class="stat"><span class="label">푼 문항</span><span class="value">${d.answered}</span></div>
        <div class="stat"><span class="label">정답률</span><span class="value">${d.answered ? acc + '%' : '–'}</span></div>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">이렇게 도와주세요</span></div>
      ${tips(d).map(([t, s], i) => `
        <div class="tip"><span class="tip-n">${i + 1}</span>
          <span class="tip-b"><span class="tip-t">${esc(t)}</span><span class="tip-s">${esc(s)}</span></span>
        </div>`).join('')}
    </div>

    ${ready.length ? `<div class="card">
      <div class="card-head"><span class="card-title">무엇이 늘고 있나</span>
        <span class="card-note">${ready.length}/${d.axes.length}칸 측정</span></div>
      ${bars}
      <p class="card-note" style="margin-top:10px">100점 만점의 시험 점수가 아니라,
        아이가 지금 어느 쪽에 강하고 약한지를 보여주는 눈금입니다.</p>
    </div>` : ''}

    ${d.misses?.length ? `<div class="card">
      <div class="card-head"><span class="card-title">요즘 자주 걸리는 실수</span></div>
      ${d.misses.map((m, i) => `
        <div class="miss${i ? ' sub' : ''}">
          <span class="miss-rank">${i + 1}</span>
          <span class="miss-name">${esc(m.name)}</span>
          <span class="miss-n">${m.n}번</span>
        </div>`).join('')}
    </div>` : ''}

    ${d.parent ? '<p class="p-out"><button data-kids>아이 관리 · PIN 재발급</button></p>' : ''}
    <p class="p-out"><button data-out>로그아웃</button></p>`;

  view.querySelectorAll('[data-kid]').forEach((b) =>
    b.addEventListener('click', () => showHome(b.dataset.kid)));
  view.querySelector('[data-kids]')?.addEventListener('click', showChildren);
  view.querySelector('[data-out]').addEventListener('click', () => {
    const id = auth?.child?.login_id ?? '';
    saveAuth(null);
    currentChildId = null;
    showLogin(id);
  });
}

auth ? showHome() : showLogin();
