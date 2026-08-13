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

// 상단바 — 브랜드는 가운데, 왼쪽에 돌아가는 길.
// 화면이 여러 장인데 돌아갈 버튼이 없으면 사용자는 브라우저 뒤로가기를 누르고,
// 이 화면은 한 페이지짜리라 그러면 로그인 화면까지 튕겨 나간다.
const head = (back) => `<div class="p-top">
  ${back ? '<button class="p-back" data-back>← 뒤로</button>' : '<span class="p-back-sp"></span>'}
  ${BRAND}
  <span class="p-back-sp"></span>
</div>`;

// 지금 누구로 로그인했는지 — 이메일까지 보여준다.
// 가족이 이메일 하나를 같이 쓰므로, 부모가 "내 계정이 맞나"를 확인할 곳이 필요하다.
const accountCard = (parent, extra = '') => `
  <div class="card p-acct">
    <div class="p-acct-b">
      <span class="p-acct-n">${esc(parent.display_name)}님</span>
      <span class="p-acct-e">${esc(parent.email)}</span>
    </div>
    <div class="p-acct-btns">
      ${extra}
      <button class="btn-ghost small" data-out>로그아웃</button>
    </div>
  </div>`;

// ── 들어오는 문 ──
// 학부모가 직접 가입하는 길 하나뿐이다. 학원을 거쳐 들어오는 화면은 두지 않는다
// (학원 영업을 하지 않기로 했다 — 학부모가 고객이다).
const err = (el, m) => { el.innerHTML = `<div class="result bad"><p>${esc(m)}</p></div>`; };

function showLogin(notice = '') {
  view.innerHTML = `
    <div class="card p-login">
      ${BRAND}
      <div><h1 class="greet-title" style="font-size:1.15rem">우리 아이 학습 보기</h1>
        <p class="card-note" style="margin-top:4px">가입하신 <b>이메일</b>과 <b>비밀번호</b>를 넣어주세요.</p></div>
      ${notice ? `<div class="result ok" style="margin-top:10px"><p>${esc(notice)}</p></div>` : ''}
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
        <p class="card-note" style="margin-top:4px">이메일 하나로 온 가족이 씁니다. 비밀번호만
          보호자용·아이용을 따로 정해 주세요. <b>하루 1세트는 계속 무료</b>입니다.</p></div>

      <label class="field" style="margin-top:12px"><span>보호자 이메일</span>
        <input data-email type="email" autocapitalize="off" autocomplete="username"
          inputmode="email" placeholder="parent@example.com" /></label>
      <label class="field" style="margin-top:10px"><span>비밀번호 (8자 이상)</span>
        <input data-pw type="password" autocomplete="new-password" placeholder="••••••••" /></label>
      <label class="field" style="margin-top:10px"><span>보호자 이름</span>
        <input data-name maxlength="12" autocomplete="name" placeholder="예: 김보호" /></label>
      <label class="field" style="margin-top:10px"><span>아이 이름</span>
        <input data-child maxlength="12" placeholder="예: 김하늘" /></label>
      <label class="field" style="margin-top:10px"><span>아이가 쓸 비밀번호 (4자 이상)</span>
        <input data-childpw autocomplete="off" placeholder="아이가 외우기 쉬운 것으로" /></label>
      <p class="card-note" style="margin-top:6px">아이는 <b>같은 이메일</b>에 <b>이 비밀번호</b>로 앱에 들어갑니다.
        보호자 비밀번호는 아이에게 알려주지 않아도 됩니다.<br>
        <b>아이가 둘 이상이면</b> 가입한 바로 다음 화면에서 더 추가할 수 있어요 (최대 3명).</p>

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
      child_password: view.querySelector('[data-childpw]').value,
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
// 둘째·셋째는 여기서 추가한다. 가입 폼에 여러 명을 넣게 만들면 첫 화면이 길어져
// 아이 하나인 대다수가 손해를 본다 — 가입 직후 이 화면으로 바로 오므로 흐름이 끊기지 않는다.
const MAX_KIDS = 3;

function showChildren() {
  view.innerHTML = '<p class="loading">불러오는 중...</p>';
  api('/api/parent/children').then((d) => {
    const full = d.children.length >= MAX_KIDS;
    const rows = d.children.map((ch) => `
      <div class="p-kid">
        <span class="p-kid-b"><span class="p-kid-n">${esc(ch.display_name)}</span></span>
        <button class="p-link" data-pw="${esc(ch.id)}" data-who="${esc(ch.display_name)}">비밀번호 바꾸기</button>
      </div>`).join('');
    view.innerHTML = `
      ${head(d.children.length > 0)}
      <div class="greet"><div>
        <p class="greet-date">보호자 설정</p>
        <h1 class="greet-title">우리 아이</h1>
      </div></div>
      <div class="card">
        <div class="card-head"><span class="card-title">등록한 아이</span></div>
        ${rows || '<p class="empty">아직 등록한 아이가 없어요.</p>'}
        <p class="p-warn" style="margin-top:12px">아이는 <b>같은 이메일</b>에 <b>자기 비밀번호</b>로
          앱에 들어갑니다. 보호자 비밀번호는 알려주지 않으셔도 돼요.</p>
      </div>
      ${full ? `
      <div class="card">
        <div class="card-head"><span class="card-title">아이 추가</span></div>
        <p class="empty">아이는 ${MAX_KIDS}명까지 등록할 수 있어요.</p>
        <div data-msg></div>
      </div>` : `
      <div class="card">
        <div class="card-head"><span class="card-title">${d.children.length ? '아이 더 추가' : '아이 추가'}</span>
          <span class="card-note">${d.children.length}/${MAX_KIDS}명</span></div>
        <label class="field"><span>아이 이름</span>
          <input data-new maxlength="12" placeholder="예: 김바다" /></label>
        <label class="field" style="margin-top:10px"><span>아이가 쓸 비밀번호 (4자 이상)</span>
          <input data-newpw autocomplete="off" placeholder="아이가 외우기 쉬운 것으로" /></label>
        <button class="btn-primary" data-add style="margin-top:10px">아이 추가</button>
        <div data-msg></div>
      </div>`}
      ${accountCard(d.parent,
        d.children.length ? '<button class="btn-ghost small" data-home>학습 기록 보기</button>' : '')}`;

    const msg = view.querySelector('[data-msg]');
    view.querySelector('[data-add]')?.addEventListener('click', async () => {
      const name = view.querySelector('[data-new]').value.trim();
      const password = view.querySelector('[data-newpw]').value;
      if (!name) return err(msg, '아이 이름을 넣어주세요.');
      if (password.trim().length < 4) return err(msg, '아이 비밀번호를 4자 이상으로 정해주세요.');
      try {
        await api('/api/parent/children', { method: 'POST', body: JSON.stringify({ name, password }) });
        showChildren();
      } catch (e) { err(msg, e.message); }
    });
    view.querySelectorAll('[data-pw]').forEach((b) => b.addEventListener('click', async () => {
      const password = prompt(`${b.dataset.who}(이)가 쓸 새 비밀번호를 정해주세요 (4자 이상)`);
      if (password === null) return;                    // 취소
      if (password.trim().length < 4) return err(msg, '아이 비밀번호를 4자 이상으로 정해주세요.');
      try {
        await api(`/api/parent/children/${b.dataset.pw}/password`,
          { method: 'POST', body: JSON.stringify({ password }) });
        msg.innerHTML = `<div class="result ok"><p>${esc(b.dataset.who)} 비밀번호를 바꿨어요.</p></div>`;
      } catch (e) { err(msg, e.message); }
    }));
    view.querySelector('[data-home]')?.addEventListener('click', () => showHome());
    view.querySelector('[data-back]')?.addEventListener('click', () => showHome());
    view.querySelector('[data-out]').addEventListener('click', () => { saveAuth(null); showLogin(); });
  }).catch((e) => {
    if (/로그인/.test(e.message)) { saveAuth(null); showLogin(); return; }
    view.innerHTML = `<div class="card"><p class="empty">${esc(e.message)}</p></div>`;
  });
}


// ── 한 줄 판정 ──
// 부모가 이 문장 하나만 읽고 나가도 손해가 없게 쓴다. 점수가 아니라 '요즘 어떤가'다.
const DAY = 86400000;
const dnum = (s) => Date.parse(`${s}T00:00:00Z`);

function verdict(d) {
  if (!d.answered) {
    return { eyebrow: '아직 시작 전', line: '아직 문제를 풀지 않았어요',
      sub: '앱에 처음 들어가면 실력을 재는 짧은 테스트부터 합니다.' };
  }

  // ⚠ 오늘 문제를 푼 아이에게 "한동안 쉬고 있어요"라고 말한 화면이 실제로 나갔다.
  // 아래 어떤 가지보다 '오늘 했나'를 먼저 본다. 오늘 앉은 아이에게는
  // 무슨 일이 있어도 쉬고 있다고 하지 않는다.
  if (d.today_n > 0) {
    if (d.streak >= 5) {
      return { eyebrow: '요즘', line: `${d.streak}일 이어서 하고 있어요`,
        sub: '오늘 몫도 이미 끝냈어요. 칭찬해주세요.' };
    }
    if (d.streak >= 2) {
      return { eyebrow: '오늘', line: `오늘까지 ${d.streak}일 이어서 했어요`,
        sub: '내일 한 번만 더 하면 습관이 됩니다.' };
    }
    return { eyebrow: '오늘', line: '오늘 학습을 마쳤어요',
      sub: `오늘 ${d.today_n}문제를 풀었어요. 내일도 하면 이어집니다.` };
  }

  // 여기부터는 오늘 몫이 남은 아이다.
  // '최근 2주'는 달력 기준 14일 안에 든 날만 센다. recent_days는 '공부한 날'만 담겨 오므로
  // 그냥 길이를 세면 한 달 전 기록까지 2주 안에 있는 것처럼 부풀려진다.
  const from = dnum(d.today) - 13 * DAY;
  const active = d.recent_days.filter((r) => r.n > 0 && dnum(r.d) >= from);
  const week = active.length;
  const last = active[active.length - 1];              // 마지막으로 공부한 날(오래된 날부터 정렬돼 옴)
  const gap = last ? Math.round((dnum(d.today) - dnum(last.d)) / DAY) : null;

  if (gap === 1) {
    return { eyebrow: '오늘', line: '오늘 몫만 남았어요',
      sub: d.streak >= 2 ? `어제까지 ${d.streak}일 이어서 했어요. 오늘 하면 이어집니다.`
        : '어제는 했어요. 오늘 10분이면 이어집니다.' };
  }
  if (week >= 7) {
    return { eyebrow: '요즘', line: '꾸준히 하고 있어요',
      sub: `최근 2주 중 ${week}일 학습했어요. 오늘 몫은 아직이에요.` };
  }
  if (week >= 3) {
    return { eyebrow: '요즘', line: '가끔 하고 있어요',
      sub: `최근 2주 중 ${week}일 학습했어요. 며칠 이어지면 훨씬 빨리 늘어요.` };
  }
  if (gap != null && gap <= 4) {
    return { eyebrow: '요즘', line: `${gap}일째 쉬고 있어요`,
      sub: '하루 10분이면 충분해요. 오늘 같이 앉아주세요.' };
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
    ${head(false)}
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

    ${d.parent
      ? accountCard(d.parent, '<button class="btn-ghost small" data-kids>아이 관리</button>')
      : '<p class="p-out"><button data-out>로그아웃</button></p>'}`;

  view.querySelectorAll('[data-kid]').forEach((b) =>
    b.addEventListener('click', () => showHome(b.dataset.kid)));
  view.querySelector('[data-kids]')?.addEventListener('click', showChildren);
  view.querySelector('[data-out]').addEventListener('click', () => {
    saveAuth(null);
    currentChildId = null;
    showLogin();
  });
}

// ── 비밀번호 재설정 (관리자가 만들어 준 링크로 들어온다) ──
// 토큰은 주소의 # 뒤에 실려 있어 서버 기록에도 남지 않는다. 새 비밀번호는
// 여기서 학부모가 직접 정한다 — 링크를 만들어 준 관리자도 알 수 없다.
function showReset(token) {
  view.innerHTML = `
    <div class="card p-login">
      ${BRAND}
      <div><h1 class="greet-title" style="font-size:1.15rem">새 비밀번호 정하기</h1>
        <p class="card-note" style="margin-top:4px">이 링크는 한 번만 쓸 수 있어요.
          새 비밀번호는 지금 정하는 분만 알게 됩니다.</p></div>
      <label class="field" style="margin-top:12px"><span>새 비밀번호 (8자 이상)</span>
        <input data-pw type="password" autocomplete="new-password" placeholder="8자 이상, 뻔하지 않게" /></label>
      <label class="field" style="margin-top:10px"><span>새 비밀번호 다시</span>
        <input data-pw2 type="password" autocomplete="new-password" /></label>
      <button class="btn-primary" data-go style="margin-top:12px">비밀번호 바꾸기</button>
      <div data-msg style="margin-top:10px"></div>
      <p class="card-note" style="margin-top:10px">아이 비밀번호는 그대로예요 —
        바뀌는 건 보호자 비밀번호뿐입니다.</p>
    </div>`;
  const msg = view.querySelector('[data-msg]');
  const go = async () => {
    const pw = view.querySelector('[data-pw]').value;
    const again = view.querySelector('[data-pw2]').value;
    if (pw.length < 8) return err(msg, '비밀번호를 8자 이상으로 정해주세요.');
    if (pw !== again) return err(msg, '두 비밀번호가 달라요. 같은 것을 두 번 넣어주세요.');
    try {
      await api('/api/parent/reset-password', {
        method: 'POST', body: JSON.stringify({ token, password: pw }) });
      history.replaceState(null, '', location.pathname);   // 주소에서 토큰을 지운다
      saveAuth(null);
      showLogin('비밀번호를 바꿨어요. 새 비밀번호로 로그인해주세요.');
    } catch (e) { err(msg, e.message); }
  };
  view.querySelector('[data-go]').addEventListener('click', go);
  view.querySelectorAll('input').forEach((i) =>
    i.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); }));
}

const resetToken = /^#reset=(.+)$/.exec(location.hash)?.[1];
if (resetToken) showReset(resetToken);
else auth ? showHome() : showLogin();
