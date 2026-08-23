// 점프리시 관리자 화면
// 하는 일 두 가지 — (1) 가입한 가족이 얼마나 들어와 얼마나 쓰는지 보기
//                  (2) 아이들이 보낸 신고 확인.
//
// 이 화면은 **읽기 전용**이다. 계정 발급 버튼이 하나도 없는 게 설계다:
// 가입은 학부모가 /parent 에서 직접 하고(고객은 학부모다 — 2026-08-11 B2C 전환),
// 아이 비밀번호도 학부모가 학부모 화면에서 바꾼다. 관리자가 남의 가족 비밀번호를
// 만들거나 볼 수 있으면 그 권한 자체가 사고 경로가 된다.
//
// ⚠ 학원·반·학생 발급 화면은 지웠다(2026-08-12). 학원 영업을 접으면서 학생 앱의
// 아이디·PIN 로그인이 사라졌으므로, 여기서 발급한 PIN은 들어갈 문이 없는 열쇠였다.
// 테스터도 같은 가입 흐름을 쓴다 — 지인에게는 가입 주소를 보내면 된다(무료).

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

// 로그인이 풀리면(토큰 만료·비밀번호 변경) 조용히 로그인 화면으로 돌려보낸다
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
let tab = 'fam';
let pendingN = 0;

async function showMain() {
  whoEl.innerHTML = `${esc(auth.user.login_id)} · <button class="btn ghost small" data-out>로그아웃</button>`;
  whoEl.querySelector('[data-out]').addEventListener('click', () => { saveAuth(null); start(); });
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  try {
    const o = await api('/api/admin/overview');
    pendingN = o.feedback_pending;
    renderFamilies(o);
  } catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

function tabsHtml() {
  return `<div class="tabs">
    <button data-tab="fam" ${tab === 'fam' ? 'aria-current="page"' : ''}>가족</button>
    <button data-tab="fb" ${tab === 'fb' ? 'aria-current="page"' : ''}>신고${
      pendingN ? `<span class="badge">${pendingN}</span>` : ''}</button>
  </div>`;
}
function bindTabs() {
  view.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => {
    tab = b.dataset.tab;
    tab === 'fam' ? showMain() : showFeedback();
  }));
}

// ── 가족 현황 ──
// 한 가족 = 학부모 한 명(이메일)과 그 아이들. 여기서 보는 질문은 딱 두 가지다:
// "가입이 늘고 있나" 그리고 "가입한 아이가 실제로 매일 쓰고 있나"(리텐션 = 유료 전환의 바탕).
// 가족을 누르면 상세 화면 — 문의 대응·메모·정지·탈퇴·재설정 링크는 전부 거기서 한다.
function renderFamilies(o) {
  const kid = (k) => `
    <span class="row-s">· ${esc(k.display_name)} — ${
      k.answers
        ? `푼 문항 ${k.answers.toLocaleString()}개${k.last_day ? ` · 마지막 학습 ${
            k.last_day === o.today ? '오늘' : esc(k.last_day)}` : ''}`
        : '아직 시작 안 함'}</span>`;

  const list = o.families.length ? o.families.map((f) => `
    <button class="row" data-family="${esc(f.id)}">
      <span class="row-main">
        <span class="row-t">${esc(f.display_name)} <span class="chip">${esc(f.email)}</span>${
          f.status === 'suspended' ? ' <span class="chip k-answer">정지됨</span>' : ''}</span>
        <span class="row-s">가입 ${esc(String(f.joined).slice(0, 10))} · 아이 ${f.children.length}명</span>
        ${f.children.map(kid).join('')}
      </span>
      <span class="row-num">열기</span>
    </button>`).join('')
    : `<p class="empty">아직 가입한 가족이 없어요.<br/>
       지인 테스터에게는 학부모 가입 주소(<b>/parent</b>)를 보내주세요 — 무료입니다.</p>`;

  view.innerHTML = `${tabsHtml()}
    <div class="card">
      <div class="card-head"><span class="card-title">지금까지</span></div>
      <div class="rows">
        <div class="row"><span class="row-main">
          <span class="row-t">가족 ${o.stats.families}팀 · 아이 ${o.stats.children}명</span>
          <span class="row-s">오늘 학습한 아이 ${o.stats.active_today}명 · 지금까지 푼 문항 ${o.stats.answers.toLocaleString()}개</span>
        </span></div>
      </div>
    </div>
    <div class="card">
      <div class="card-head"><span class="card-title">가입한 가족</span>
        <span class="card-note">눌러서 관리 · 최근 가입 순</span></div>
      <div class="rows">${list}</div>
    </div>
    <p class="card-note" style="margin-top:10px">비밀번호는 서버에 암호로만 저장되어 관리자도
      볼 수 없어요. 비밀번호를 잊은 가족에게는 상세 화면에서 <b>재설정 링크</b>를 만들어 보내주세요 —
      새 비밀번호는 학부모가 직접 정합니다.</p>`;
  bindTabs();
  view.querySelectorAll('[data-family]').forEach((b) =>
    b.addEventListener('click', () => showFamily(b.dataset.family)));
}

// ── 가족 한 팀 상세 — 문의 전화를 받으며 여는 화면 ──
async function showFamily(id) {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  let d;
  try { d = await api(`/api/admin/family/${encodeURIComponent(id)}`); }
  catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; return; }
  const f = d.family;
  const suspended = f.status === 'suspended';

  // 아이마다 자기 카드 — 학습률(정답률·양), 학습 상황(최근 2주·이어온 날), 능력(실력 지도).
  // 형제가 있어도 섞이지 않게 아이 단위로 나눠 보여준다. 부모 화면과 같은 엔진 값이라
  // "부모 화면엔 이렇게 나오는데요" 문의에 같은 숫자로 답할 수 있다.
  const kidCard = (k) => {
    const acc = k.answers ? Math.round((k.correct ?? 0) / k.answers * 100) : 0;
    const bars = (k.axes ?? []).map((a) => a.score != null ? `
      <div class="sbar">
        <span class="sbl">${esc(a.name)}</span>
        <span class="sbt"><span class="sbf" style="width:${a.score}%"></span></span>
        <span class="sbn">${a.score}</span>
      </div>` : `
      <div class="sbar">
        <span class="sbl">${esc(a.name)}</span>
        <span class="sbt"></span>
        <span class="sbn dim">재는 중 ${a.attempts}/3</span>
      </div>`).join('');
    const extra = [];
    if (k.misses?.length) extra.push(`자주 하는 실수: ${k.misses.map((m) => `${esc(m.name)} ${m.n}번`).join(', ')}`);
    if (k.revive?.met >= 3) extra.push(`틀린 문제 설욕 ${k.revive.won}/${k.revive.met}판`);
    return `
    <div class="card">
      <div class="card-head"><span class="card-title">${esc(k.display_name)}</span>
        <span class="card-note">등록 ${esc(String(k.created_at).slice(0, 10))}</span></div>
      ${k.answers ? `
      <div class="kid-stats">
        <span><b>${k.answers.toLocaleString()}</b>문항</span>
        <span>정답률 <b>${acc}%</b></span>
        <span>최근 2주 <b>${k.week14}</b>일</span>
        <span>이어서 <b>${k.streak}</b>일</span>
        <span>마지막 학습 <b>${k.last_day === d.today ? '오늘' : esc(k.last_day ?? '—')}</b></span>
      </div>
      <div class="kid-axes">${bars}</div>
      ${extra.length ? `<p class="card-note" style="margin-top:8px">${extra.join(' · ')}</p>` : ''}`
      : `<p class="empty" style="padding:8px 0">아직 시작 안 했어요 — 앱에 처음 들어가면 진단부터 합니다.</p>`}
    </div>`;
  };
  const kids = d.children.length ? d.children.map(kidCard).join('')
    : `<div class="card"><p class="empty">등록된 아이가 없어요.</p></div>`;

  const notes = d.notes.length ? d.notes.map((n) => `
    <div class="row"><span class="row-main">
      <span class="row-t" style="font-weight:600">${esc(n.body)}</span>
      <span class="row-s">${esc(n.created_by)} · ${esc(String(n.created_at).slice(0, 16).replace('T', ' '))}</span>
    </span></div>`).join('') : `<p class="empty">아직 메모가 없어요.</p>`;

  const KIND = { audio: '소리가 안 들려요', image: '사진이 안 맞아요', hard: '무슨 말인지 모르겠어요',
    answer: '답이 이상해요', etc: '그 밖에' };
  const fb = d.feedback.length ? d.feedback.map((x) => `
    <div class="row">
      <span class="chip">${esc(KIND[x.kind] ?? x.kind)}</span>
      <span class="row-main">
        <span class="row-t">${esc(x.stem || (x.part ? `${x.part} 문항` : '화면 전체'))}</span>
        <span class="row-s">${esc(x.display_name)} · ${esc(String(x.created_at).slice(0, 16).replace('T', ' '))}${
          x.note ? ` · “${esc(x.note)}”` : ''}${x.handled_at ? ' · 확인함' : ''}</span>
      </span>
    </div>`).join('') : `<p class="empty">이 가족이 보낸 신고가 없어요.</p>`;

  view.innerHTML = `${tabsHtml()}
    <button class="btn ghost small" data-back style="margin-bottom:12px">← 가족 목록</button>
    <div class="card">
      <div class="card-head"><span class="card-title">${esc(f.display_name)}님 가족${
        suspended ? ' <span class="chip k-answer">정지됨</span>' : ''}</span></div>
      <p class="card-note">${esc(f.email)} · 가입 ${esc(String(f.created_at).slice(0, 10))} ·
        동의 ${esc(String(f.consent_at).slice(0, 10))}</p>
      <div class="modal-actions" style="margin-top:12px">
        <button class="btn ghost" data-reset>비밀번호 재설정 링크</button>
        <button class="btn ghost" data-suspend>${suspended ? '정지 해제' : '일시 정지'}</button>
      </div>
      <p class="msg" data-act-msg></p>
    </div>

    ${kids}

    <div class="card">
      <div class="card-head"><span class="card-title">운영 메모</span>
        <span class="card-note">문의·처리 이력을 남겨두세요</span></div>
      <label class="field" style="width:100%">
        <textarea data-note rows="2" maxlength="500" placeholder="예: 8/12 비밀번호 문의 → 재설정 링크 발송"></textarea>
      </label>
      <div style="margin-top:8px"><button class="btn" data-note-go>메모 남기기</button></div>
      <div class="rows" style="margin-top:10px">${notes}</div>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">이 가족이 보낸 신고</span></div>
      <div class="rows">${fb}</div>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">탈퇴 처리</span></div>
      <p class="card-note">학부모가 탈퇴(삭제)를 요청했을 때만 쓰세요. 아이 학습 기록·신고·메모까지
        <b>전부 지워지고 되돌릴 수 없습니다.</b> 개인정보 삭제 요청은 법적으로 지체 없이 처리해야 해요.</p>
      <div style="margin-top:10px"><button class="btn ghost small" data-del style="color:#dc2626">이 가족 탈퇴 처리…</button></div>
    </div>`;
  bindTabs();
  view.querySelector('[data-back]').addEventListener('click', showMain);
  const msg = view.querySelector('[data-act-msg]');

  // 재설정 링크 — 평문 토큰이 보이는 유일한 순간. 모달로 한 번 보여주고 끝.
  view.querySelector('[data-reset]').addEventListener('click', async (e) => {
    if (!confirm(`${f.display_name}님에게 줄 비밀번호 재설정 링크를 만듭니다.\n예전에 만든 링크가 있다면 못 쓰게 됩니다. 계속할까요?`)) return;
    e.target.disabled = true;
    try {
      const r = await api(`/api/admin/family/${encodeURIComponent(f.id)}/reset-link`, { method: 'POST' });
      showResetLink(f, r);
    } catch (err2) { if (!guard(err2)) { msg.className = 'msg bad'; msg.textContent = err2.message; } }
    e.target.disabled = false;
  });

  view.querySelector('[data-suspend]').addEventListener('click', async (e) => {
    const q = suspended
      ? '정지를 풀어줍니다. 가족이 다시 로그인할 수 있게 돼요. 계속할까요?'
      : '이 가족을 일시 정지합니다.\n학부모·아이 모두 바로 로그인이 막히고, 데이터는 그대로 남아요. 계속할까요?';
    if (!confirm(q)) return;
    e.target.disabled = true;
    try {
      await api(`/api/admin/family/${encodeURIComponent(f.id)}/suspend`,
        { method: 'POST', body: JSON.stringify({ suspend: !suspended }) });
      showFamily(f.id);
    } catch (err2) {
      if (!guard(err2)) { msg.className = 'msg bad'; msg.textContent = err2.message; e.target.disabled = false; }
    }
  });

  view.querySelector('[data-note-go]').addEventListener('click', async (e) => {
    const body = view.querySelector('[data-note]').value.trim();
    if (!body) return;
    e.target.disabled = true;
    try {
      await api(`/api/admin/family/${encodeURIComponent(f.id)}/note`,
        { method: 'POST', body: JSON.stringify({ body }) });
      showFamily(f.id);
    } catch (err2) {
      if (!guard(err2)) { msg.className = 'msg bad'; msg.textContent = err2.message; e.target.disabled = false; }
    }
  });

  view.querySelector('[data-del]').addEventListener('click', async () => {
    const typed = prompt(
      `정말 탈퇴 처리하려면 이 가족의 이메일을 그대로 입력하세요.\n\n${f.email}\n\n(아이 학습 기록까지 전부 삭제되며 되돌릴 수 없습니다)`);
    if (typed === null) return;
    try {
      await api(`/api/admin/family/${encodeURIComponent(f.id)}`,
        { method: 'DELETE', body: JSON.stringify({ email: typed.trim() }) });
      alert('탈퇴 처리가 끝났습니다. 이 가족의 모든 데이터를 지웠어요.');
      showMain();
    } catch (err2) { if (!guard(err2)) alert(err2.message); }
  });
}

// 재설정 링크 모달 — 닫으면 다시 볼 수 없다(서버엔 암호만 남는다)
function showResetLink(f, r) {
  const back = document.createElement('div');
  back.className = 'back';
  back.innerHTML = `
    <div class="modal" role="dialog" aria-label="비밀번호 재설정 링크">
      <h2>${esc(f.display_name)}님에게 보낼 링크</h2>
      <p class="card-note">학부모가 이 링크를 열어 <b>새 비밀번호를 직접 정합니다.</b>
        관리자는 새 비밀번호를 알 수 없어요.</p>
      <div class="warn-box">이 창을 닫으면 링크를 다시 볼 수 없습니다.
        지금 복사해서 학부모에게 직접(문자·카카오톡) 보내주세요. 24시간 뒤엔 못 씁니다.</div>
      <p style="word-break:break-all; font-size:.85rem; background:var(--line); border-radius:8px; padding:10px; margin-top:10px">${esc(r.url)}</p>
      <div class="modal-actions">
        <button class="btn ghost" data-copy>링크 복사</button>
        <button class="btn" data-close>복사했어요, 닫기</button>
      </div>
    </div>`;
  document.body.appendChild(back);
  const copyBtn = back.querySelector('[data-copy]');
  copyBtn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(r.url); copyBtn.textContent = '복사됨'; }
    catch { copyBtn.textContent = '길게 눌러 직접 복사하세요'; }
  });
  back.querySelector('[data-close]').addEventListener('click', () => { back.remove(); showFamily(f.id); });
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
          <span class="row-s">${f.part ? esc(f.part) + ' · ' : ''}${esc(f.display_name || f.login_id || '로그인 안 함')} · ${esc(String(f.created_at).slice(0, 16).replace('T', ' '))}${
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
