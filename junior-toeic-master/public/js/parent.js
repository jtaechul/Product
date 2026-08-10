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

// ── 로그인 ──
function showLogin(prefill = '') {
  view.innerHTML = `
    <div class="card p-login">
      ${BRAND}
      <div><h1 class="greet-title" style="font-size:1.15rem">우리 아이 학습 보기</h1>
        <p class="card-note" style="margin-top:4px">학원에서 받으신 <b>자녀 아이디</b>와
          <b>학부모용 6자리 PIN</b>을 넣어주세요.</p></div>
      <label class="field" style="margin-top:12px"><span>자녀 아이디</span>
        <input data-lid value="${esc(prefill)}" autocapitalize="characters"
          autocomplete="username" placeholder="예: JUMP-1" /></label>
      <label class="field" style="margin-top:10px"><span>학부모용 PIN (숫자 6자리)</span>
        <input data-pin type="password" inputmode="numeric" maxlength="6"
          autocomplete="current-password" placeholder="●●●●●●" /></label>
      <button class="btn-primary" data-go style="margin-top:12px">보기</button>
      <div data-msg></div>
      <p class="card-note" style="margin-top:6px">아이가 앱에 쓰는 PIN과는 다른 번호입니다.
        이 화면에서는 기록을 보기만 하고, 문제를 풀 수는 없어요.</p>
    </div>`;
  const msg = view.querySelector('[data-msg]');
  const go = async () => {
    const login_id = view.querySelector('[data-lid]').value.trim();
    const pin = view.querySelector('[data-pin]').value.trim();
    if (!login_id || !/^\d{6}$/.test(pin)) {
      msg.innerHTML = '<div class="result bad"><p>아이디와 숫자 6자리를 확인해주세요.</p></div>';
      return;
    }
    try {
      const r = await api('/api/parent/login', { method: 'POST', body: JSON.stringify({ login_id, pin }) });
      saveAuth(r);
      showHome();
    } catch (e) { msg.innerHTML = `<div class="result bad"><p>${esc(e.message)}</p></div>`; }
  };
  view.querySelector('[data-go]').addEventListener('click', go);
  view.querySelectorAll('input').forEach((i) =>
    i.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); }));
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

async function showHome() {
  view.innerHTML = '<p class="loading">불러오는 중...</p>';
  let d;
  try {
    d = await api('/api/parent/overview');
  } catch (e) {
    if (/로그인이 필요/.test(e.message)) { saveAuth(null); showLogin(); return; }
    view.innerHTML = `<div class="card"><p class="empty">${esc(e.message)}</p></div>`;
    return;
  }
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
    return `<span class="dot-day${on ? ' on' : ''}${key === today ? ' today' : ''}"
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

  view.innerHTML = `
    ${BRAND}
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

    <p class="p-out"><button data-out>다른 아이 보기 / 로그아웃</button></p>`;

  view.querySelector('[data-out]').addEventListener('click', () => {
    const id = auth?.child?.login_id ?? '';
    saveAuth(null);
    showLogin(id);
  });
}

auth ? showHome() : showLogin();
