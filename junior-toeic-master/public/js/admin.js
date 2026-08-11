// 점프리시 관리자 화면
// 하는 일 두 가지 — (1) 학원·반·학생 계정 발급 (2) 아이들이 보낸 신고 확인.
// 지금까지는 계정을 늘리려면 손으로 SQL을 만들어 Cloudflare 콘솔에 붙여넣어야 했다.
//
// PIN 원칙: 서버가 만들고, 응답에 딱 한 번 실려 온다. 서버에는 해시만 남으므로
// 이 화면을 닫으면 아무도(만든 사람도) 다시 볼 수 없다 → 화면에서 바로 복사하게 만든다.

const view = document.getElementById('view');
const whoEl = document.getElementById('who');
const AUTH_KEY = 'jumplish.admin.v1';

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

// 로그인이 풀리면(토큰 만료·PIN 변경) 조용히 로그인 화면으로 돌려보낸다
const guard = (e) => {
  if (/로그인이 필요|권한이 없습니다/.test(e.message)) { saveAuth(null); start(); return true; }
  return false;
};

// 로그인 화면과 '처음 시작하기' 화면 중 맞는 쪽을 고른다
function start() {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  api('/api/setup/needed')
    .then((r) => (r.needed ? showSetup() : showLogin()))
    .catch(showLogin);
}

// ── 처음 시작하기 ──
// 관리자 계정이 하나도 없을 때만 나오는 화면. 하나 만들어지면 다시는 안 나온다.
// (계정을 만드는 화면에 들어가려면 계정이 있어야 하는 닭과 달걀을 여기서 푼다)
function showSetup() {
  whoEl.textContent = '';
  view.innerHTML = `
    <div class="card login">
      <div class="card-head"><span class="card-title">처음 시작하기</span></div>
      <p class="card-note">관리자 계정이 아직 없습니다. 지금 만들어주세요.</p>
      <div class="warn-box" style="margin:12px 0">이 화면은 <b>지금 딱 한 번만</b> 열립니다.
        계정을 만들면 다시는 나오지 않으니, 다른 사람이 먼저 만들지 않도록 지금 정해주세요.</div>
      <label class="field"><span>아이디 (영문·숫자)</span>
        <input data-id value="ADMIN" maxlength="32" autocapitalize="characters" /></label>
      <label class="field" style="margin-top:10px"><span>비밀번호 (8자 이상)</span>
        <input data-pw type="password" autocomplete="new-password" placeholder="8자 이상, 뻔하지 않게" /></label>
      <label class="field" style="margin-top:10px"><span>비밀번호 다시</span>
        <input data-pw2 type="password" autocomplete="new-password" /></label>
      <p class="card-note" style="margin-top:8px">비밀번호는 서버에 암호로만 저장되어,
        잃어버리면 아무도 다시 볼 수 없습니다. 비밀번호 관리 앱에 꼭 저장해두세요.</p>
      <button class="btn" data-go>관리자 계정 만들기</button>
      <p class="msg" data-msg></p>
    </div>`;
  const msg = view.querySelector('[data-msg]');
  const go = async (e) => {
    const login_id = view.querySelector('[data-id]').value.trim();
    const secret = view.querySelector('[data-pw]').value;
    const again = view.querySelector('[data-pw2]').value;
    msg.className = 'msg bad';
    if (secret.length < 8) { msg.textContent = '비밀번호를 8자 이상으로 정해주세요'; return; }
    if (secret !== again) { msg.textContent = '두 비밀번호가 다릅니다'; return; }
    e.target.disabled = true;
    try {
      const r = await api('/api/setup/admin', { method: 'POST', body: JSON.stringify({ login_id, secret }) });
      saveAuth(r);           // 만들자마자 로그인 상태로 들어간다
      showMain();
    } catch (err) { msg.textContent = err.message; e.target.disabled = false; }
  };
  view.querySelector('[data-go]').addEventListener('click', go);
  view.querySelectorAll('input').forEach((i) =>
    i.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') go({ target: view.querySelector('[data-go]') }); }));
}

// ── 로그인 ──
function showLogin() {
  whoEl.textContent = '';
  view.innerHTML = `
    <div class="card login">
      <div class="card-head"><span class="card-title">관리자 로그인</span></div>
      <label class="field"><span>로그인ID</span>
        <input data-id autocapitalize="characters" autocomplete="username" placeholder="ADMIN" /></label>
      <label class="field" style="margin-top:10px"><span>비밀번호</span>
        <input data-pw type="password" autocomplete="current-password" placeholder="긴 비밀번호" /></label>
      <button class="btn" data-go>로그인</button>
      <p class="msg" data-msg></p>
    </div>`;
  const msg = view.querySelector('[data-msg]');
  const go = async () => {
    const login_id = view.querySelector('[data-id]').value.trim();
    const pin = view.querySelector('[data-pw]').value;
    if (!login_id || !pin) { msg.className = 'msg bad'; msg.textContent = '아이디와 비밀번호를 넣어주세요'; return; }
    try {
      const r = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ login_id, pin }) });
      if (r.user.role !== 'super') { msg.className = 'msg bad'; msg.textContent = '관리자 계정이 아닙니다'; return; }
      saveAuth(r);
      showMain();
    } catch (e) { msg.className = 'msg bad'; msg.textContent = e.message; }
  };
  view.querySelector('[data-go]').addEventListener('click', go);
  view.querySelectorAll('input').forEach((i) =>
    i.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); }));
}

// ── 메인 (탭) ──
let tab = 'org';
let pendingN = 0;

async function showMain() {
  whoEl.innerHTML = `${esc(auth.user.login_id)} · <button class="btn ghost small" data-out>로그아웃</button>`;
  whoEl.querySelector('[data-out]').addEventListener('click', () => { saveAuth(null); start(); });
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  try {
    const o = await api('/api/admin/overview');
    pendingN = o.feedback_pending;
    render(o);
  } catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

function tabsHtml() {
  return `<div class="tabs">
    <button data-tab="org" ${tab === 'org' ? 'aria-current="page"' : ''}>학원 · 학생</button>
    <button data-tab="fb" ${tab === 'fb' ? 'aria-current="page"' : ''}>신고${
      pendingN ? `<span class="badge">${pendingN}</span>` : ''}</button>
  </div>`;
}
function bindTabs() {
  view.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => {
    tab = b.dataset.tab;
    tab === 'org' ? showMain() : showFeedback();
  }));
}

// ── 학원 목록 ──
function render(o) {
  const list = o.academies.length ? o.academies.map((a) => `
    <button class="row" data-academy="${esc(a.id)}" data-name="${esc(a.name)}">
      <span class="row-main">
        <span class="row-t">${esc(a.name)} <span class="chip">${esc(a.join_code)}</span></span>
        <span class="row-s">반 ${a.classes}개 · 학생 ${a.students}명 · 푼 문항 ${a.answers.toLocaleString()}개</span>
      </span>
      <span class="row-num">열기</span>
    </button>`).join('') : `<p class="empty">아직 학원이 없어요. 아래에서 만들어주세요.</p>`;

  view.innerHTML = `${tabsHtml()}
    <div class="card">
      <div class="card-head"><span class="card-title">학원</span>
        <span class="card-note">학원을 눌러 반과 학생을 관리합니다</span></div>
      <div class="rows">${list}</div>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">새 학원 만들기</span></div>
      <div class="form">
        <label class="field"><span>학원 이름</span><input data-a-name maxlength="40" placeholder="한빛영어학원" /></label>
        <label class="field"><span>가입코드 (학생 아이디 앞자리)</span>
          <input data-a-code maxlength="12" placeholder="HANB" autocapitalize="characters" /></label>
        <button class="btn" data-a-go>만들기</button>
      </div>
      <p class="card-note" style="margin-top:8px">가입코드가 HANB면 학생 아이디는 HANB-1, HANB-2… 가 됩니다. 나중에 바꿀 수 없어요.</p>
      <p class="msg" data-a-msg></p>
    </div>`;
  bindTabs();

  view.querySelectorAll('[data-academy]').forEach((b) =>
    b.addEventListener('click', () => showAcademy(b.dataset.academy, b.dataset.name)));

  const msg = view.querySelector('[data-a-msg]');
  view.querySelector('[data-a-go]').addEventListener('click', async (e) => {
    const name = view.querySelector('[data-a-name]').value.trim();
    const join_code = view.querySelector('[data-a-code]').value.trim().toUpperCase();
    e.target.disabled = true;
    try {
      await api('/api/admin/academy', { method: 'POST', body: JSON.stringify({ name, join_code }) });
      showMain();
    } catch (err) {
      if (!guard(err)) { msg.className = 'msg bad'; msg.textContent = err.message; }
      e.target.disabled = false;
    }
  });
}

// ── 한 학원: 반 목록 ──
async function showAcademy(academyId, academyName) {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  try {
    const { classes } = await api(`/api/admin/classes?academy_id=${encodeURIComponent(academyId)}`);
    const list = classes.length ? classes.map((k) => `
      <button class="row" data-class="${esc(k.id)}" data-name="${esc(k.name)}">
        <span class="row-main">
          <span class="row-t">${esc(k.name)}${k.grade ? ` <span class="chip">${esc(k.grade)}</span>` : ''}</span>
          <span class="row-s">학생 ${k.students}명 · 하루 ${k.set_size}문항</span>
        </span>
        <span class="row-num">열기</span>
      </button>`).join('') : `<p class="empty">아직 반이 없어요.</p>`;

    view.innerHTML = `${tabsHtml()}
      <button class="btn ghost small" data-back style="margin-bottom:12px">← 학원 목록</button>
      <div class="card">
        <div class="card-head"><span class="card-title">${esc(academyName)} · 반</span></div>
        <div class="rows">${list}</div>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">새 반 만들기</span></div>
        <div class="form">
          <label class="field"><span>반 이름</span><input data-c-name maxlength="30" placeholder="초5 A반" /></label>
          <label class="field"><span>학년</span>
            <select data-c-grade>
              ${['초3', '초4', '초5', '초6', '중1', '중2', '중3'].map((g) =>
                `<option${g === '초5' ? ' selected' : ''}>${g}</option>`).join('')}
            </select></label>
          <label class="field"><span>하루 문항 수</span>
            <select data-c-size>
              <option value="12">12문항 (초3~4 권장)</option>
              <option value="20" selected>20문항 (초5~중3 권장)</option>
            </select></label>
          <button class="btn" data-c-go>만들기</button>
        </div>
        <p class="msg" data-c-msg></p>
      </div>`;
    bindTabs();
    view.querySelector('[data-back]').addEventListener('click', showMain);
    view.querySelectorAll('[data-class]').forEach((b) =>
      b.addEventListener('click', () => showClass(b.dataset.class, b.dataset.name, academyId, academyName)));

    const msg = view.querySelector('[data-c-msg]');
    view.querySelector('[data-c-go]').addEventListener('click', async (e) => {
      e.target.disabled = true;
      try {
        await api('/api/admin/class', {
          method: 'POST',
          body: JSON.stringify({
            academy_id: academyId,
            name: view.querySelector('[data-c-name]').value.trim(),
            grade: view.querySelector('[data-c-grade]').value,
            set_size: Number(view.querySelector('[data-c-size]').value),
          }),
        });
        showAcademy(academyId, academyName);
      } catch (err) {
        if (!guard(err)) { msg.className = 'msg bad'; msg.textContent = err.message; }
        e.target.disabled = false;
      }
    });
  } catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

// ── 한 반: 학생 목록 + 발급 ──
async function showClass(classId, className, academyId, academyName) {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  try {
    const { students } = await api(`/api/admin/students?class_id=${encodeURIComponent(classId)}`);
    const list = students.length ? students.map((s) => `
      <div class="row">
        <span class="row-main">
          <span class="row-t">${esc(s.display_name)} <span class="chip">${esc(s.login_id)}</span></span>
          <span class="row-s">푼 문항 ${s.answers}개${s.last_day ? ` · 마지막 학습 ${esc(s.last_day)}` : ' · 아직 시작 안 함'}</span>
        </span>
        <button class="btn ghost small" data-repin="${esc(s.id)}" data-who="${esc(s.display_name)}">PIN 재발급</button>
      </div>`).join('') : `<p class="empty">아직 학생이 없어요.</p>`;

    view.innerHTML = `${tabsHtml()}
      <button class="btn ghost small" data-back style="margin-bottom:12px">← ${esc(academyName)} 반 목록</button>
      <div class="card">
        <div class="card-head"><span class="card-title">${esc(className)} · 학생 ${students.length}명</span>
          <span class="card-note">PIN은 서버에 암호로만 남아 다시 볼 수 없어요</span></div>
        <div class="rows">${list}</div>
      </div>
      <div class="card">
        <div class="card-head"><span class="card-title">학생 추가</span></div>
        <label class="field" style="width:100%">
          <span>이름을 한 줄에 한 명씩 (한 번에 50명까지)</span>
          <textarea data-s-names rows="5" placeholder="김하늘&#10;이준서&#10;박서연"></textarea>
        </label>
        <div style="margin-top:10px"><button class="btn" data-s-go>계정 만들기</button></div>
        <p class="msg" data-s-msg></p>
      </div>`;
    bindTabs();
    view.querySelector('[data-back]').addEventListener('click', () => showAcademy(academyId, academyName));

    // (학부모용 PIN 버튼은 없앴다 — 학부모는 이메일로 직접 가입해 아이 계정을 스스로 만든다.)

    view.querySelectorAll('[data-repin]').forEach((b) => b.addEventListener('click', async () => {
      if (!confirm(`${b.dataset.who} 학생의 PIN을 새로 만듭니다.\n지금 쓰던 PIN은 바로 못 쓰게 되고, 로그인도 풀립니다.\n계속할까요?`)) return;
      b.disabled = true;
      try {
        const r = await api(`/api/admin/student/${encodeURIComponent(b.dataset.repin)}/pin`, { method: 'POST' });
        showPins([{ login_id: r.login_id, display_name: b.dataset.who, pin: r.pin }]);
      } catch (e) { if (!guard(e)) alert(e.message); }
      b.disabled = false;
    }));

    const msg = view.querySelector('[data-s-msg]');
    view.querySelector('[data-s-go]').addEventListener('click', async (e) => {
      const names = view.querySelector('[data-s-names]').value.split('\n').map((s) => s.trim()).filter(Boolean);
      if (!names.length) { msg.className = 'msg bad'; msg.textContent = '이름을 한 명 이상 적어주세요'; return; }
      e.target.disabled = true;
      try {
        const r = await api('/api/admin/students', {
          method: 'POST', body: JSON.stringify({ class_id: classId, names }),
        });
        showPins(r.students, () => showClass(classId, className, academyId, academyName));
      } catch (err) {
        if (!guard(err)) { msg.className = 'msg bad'; msg.textContent = err.message; }
      }
      e.target.disabled = false;
    });
  } catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

// ── 발급 결과 — PIN이 보이는 유일한 순간 ──
function showPins(students, onClose, opts = {}) {
  const text = students.map((s) => `${s.display_name}\t${s.login_id}\t${s.pin}`).join('\n');
  const back = document.createElement('div');
  back.className = 'back';
  back.innerHTML = `
    <div class="modal" role="dialog" aria-label="발급된 계정">
      <h2>${opts.title ?? `계정 ${students.length}개를 만들었어요`}</h2>
      <p class="card-note">${opts.note ?? '아래 아이디와 PIN으로 학생이 로그인합니다.'}</p>
      <div class="warn-box">이 창을 닫으면 PIN을 다시 볼 수 없습니다.
        서버에는 암호로만 저장돼요. 지금 복사하거나 인쇄해서 나눠주세요.</div>
      <table class="pins">
        <thead><tr><th>이름</th><th>아이디</th><th>PIN</th></tr></thead>
        <tbody>${students.map((s) => `<tr>
          <td>${esc(s.display_name)}</td><td>${esc(s.login_id)}</td>
          <td class="pin">${esc(s.pin)}</td></tr>`).join('')}</tbody>
      </table>
      <div class="modal-actions">
        <button class="btn ghost" data-copy>전체 복사</button>
        <button class="btn ghost" data-print>인쇄</button>
        <button class="btn" data-close>복사했어요, 닫기</button>
      </div>
    </div>`;
  document.body.appendChild(back);

  const copyBtn = back.querySelector('[data-copy]');
  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = '복사됨';
    } catch {
      // 클립보드가 막힌 브라우저 — 직접 긁어 복사할 수 있게 전부 선택해 준다
      const r = document.createRange();
      r.selectNode(back.querySelector('table.pins'));
      getSelection().removeAllRanges();
      getSelection().addRange(r);
      copyBtn.textContent = '표를 직접 복사하세요';
    }
  });
  back.querySelector('[data-print]').addEventListener('click', () => window.print());
  back.querySelector('[data-close]').addEventListener('click', () => { back.remove(); onClose?.(); });
}

// ── 신고 ──
let showHandled = false;
async function showFeedback() {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  try {
    const { feedback } = await api(`/api/admin/feedback${showHandled ? '?all=1' : ''}`);
    pendingN = feedback.filter((f) => !f.handled_at).length;
    const KIND = {
      audio: '소리가 안 들려요', image: '사진이 안 맞아요', hard: '무슨 말인지 모르겠어요',
      answer: '답이 이상해요', etc: '그 밖에',
    };
    const PART = {
      L1: '사진 고르기', L2: '질의응답', L3: '짧은 대화', L4: '짧은 담화',
      R1: '문장 완성', R2: '지문 완성', R3: '독해',
    };
    const list = feedback.length ? feedback.map((f) => {
      // 듣기 문항은 화면에 지문이 없어서 stem이 비어 있다 — 파트 이름으로 대신 가리킨다
      const what = f.stem || (f.part ? `${PART[f.part] ?? f.part} 문항` : '화면 전체');
      return `<div class="row">
        <span class="chip k-${esc(f.kind)}">${esc(KIND[f.kind] ?? f.kind)}</span>
        <span class="row-main">
          <span class="row-t">${esc(what)}</span>
          <span class="row-s">${f.part ? esc(f.part) + ' · ' : ''}${esc(f.login_id || '로그인 안 함')} · ${esc(String(f.created_at).slice(0, 16).replace('T', ' '))}${
            f.note ? ` · “${esc(f.note)}”` : ''}</span>
        </span>
        ${f.handled_at
          ? `<span class="chip done">확인함</span>`
          : `<button class="btn ghost small" data-done="${esc(f.id)}">확인함</button>`}
      </div>`;
    }).join('') : `<p class="empty">${showHandled ? '신고가 없어요.' : '확인할 신고가 없어요.'}</p>`;

    view.innerHTML = `${tabsHtml()}
      <div class="card">
        <div class="card-head"><span class="card-title">아이들이 보낸 신고</span>
          <button class="btn ghost small" data-toggle>${showHandled ? '안 본 것만 보기' : '확인한 것도 보기'}</button></div>
        <div class="rows">${list}</div>
      </div>`;
    bindTabs();
    view.querySelector('[data-toggle]').addEventListener('click', () => { showHandled = !showHandled; showFeedback(); });
    view.querySelectorAll('[data-done]').forEach((b) => b.addEventListener('click', async () => {
      b.disabled = true;
      try {
        await api(`/api/admin/feedback/${encodeURIComponent(b.dataset.done)}/handled`,
          { method: 'POST', body: JSON.stringify({ done: true }) });
        showFeedback();
      } catch (e) { if (!guard(e)) { alert(e.message); b.disabled = false; } }
    }));
  } catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

// 이미 로그인돼 있으면 바로 메인. 아니면 관리자가 아예 없는지 먼저 물어보고,
// 없으면 '처음 시작하기', 있으면 평범한 로그인 화면.
auth ? showMain() : start();
