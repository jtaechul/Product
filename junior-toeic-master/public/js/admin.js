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
    <button data-tab="q" ${tab === 'q' ? 'aria-current="page"' : ''}>문항</button>
    <button data-tab="fb" ${tab === 'fb' ? 'aria-current="page"' : ''}>신고${
      pendingN ? `<span class="badge">${pendingN}</span>` : ''}</button>
  </div>`;
}
function bindTabs() {
  view.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => {
    tab = b.dataset.tab;
    if (tab === 'fam') showMain();
    else if (tab === 'q') showQuestions();
    else showFeedback();
  }));
}

// ── 가족 현황 ──
// 한 가족 = 학부모 한 명(이메일)과 그 아이들. 여기서 보는 질문은 딱 두 가지다:
// "가입이 늘고 있나" 그리고 "가입한 아이가 실제로 매일 쓰고 있나"(리텐션 = 유료 전환의 바탕).
// 가족을 누르면 상세 화면 — 문의 대응·메모·정지·탈퇴·재설정 링크는 전부 거기서 한다.
function renderFamilies(o) {
  // 아이 줄의 첫 정보는 '오늘'이다. 목록을 훑는 이유가 대개 "오늘 누가 했나"이고,
  // '마지막 학습 = 오늘'만으로는 한 문제만 열어본 아이와 한 세트를 끝낸 아이가 같아 보인다.
  const kid = (k) => {
    if (!k.answers) return `<span class="row-s">· ${esc(k.display_name)} — 아직 시작 안 함</span>`;
    const todayPart = k.today_n
      ? `<b class="hot">오늘 ${k.today_n}문항</b>`
      : `오늘 아직${k.last_day ? ` (마지막 ${esc(k.last_day)})` : ''}`;
    return `<span class="row-s">· ${esc(k.display_name)} — ${todayPart} · 누적 ${
      k.answers.toLocaleString()}개</span>`;
  };

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
          <span class="row-s">오늘 학습한 아이 <b>${o.stats.active_today}명</b> · 오늘 푼 문항 <b>${
            (o.stats.today_answers ?? 0).toLocaleString()}개</b> · 지금까지 ${o.stats.answers.toLocaleString()}개</span>
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
        <span class="${k.today_n ? 'hot' : 'dim'}">오늘 <b>${k.today_n ?? 0}</b>문항</span>
        <span>누적 <b>${k.answers.toLocaleString()}</b>문항</span>
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

// ── 문항 (2026-08-23) ──
// 하는 일 세 가지 — (1) 무엇이 부족한지 보기 (2) 직접 만들기 (3) AI에게 초안 시키기.
//
// 여기서 만든 문항은 저장소의 content/questions/*.json 에 커밋된다. DB에 바로 넣지 않는 이유는
// 원본을 하나로 두기 위해서다 — 음원·사진 배치와 배포가 모두 그 파일을 보고 돌기 때문에,
// 파일에 들어가야 듣기 문항에 소리가 붙고 다음 배포에 출제까지 이어진다.
//
// 새 문항은 언제나 '준비 중'으로 들어간다. 사람이 보고 '출제 시작'을 눌러야 아이에게 나간다.

let content = null;      // 현황판 자료 (파트·태그·축·신고)
let qFilter = { status: 'draft' };   // 목록에서 지금 보고 있는 조건

async function showQuestions() {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  try {
    content = await api('/api/admin/content');
    renderQuestions();
  } catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

// 축(실력 5칸)이 이 화면의 첫 번째 답이다. 총량이 넉넉해도 한 축이 얇으면
// 그 축의 실력이 안 재져서 아이 화면에 '재는 중'이 계속 남는다.
const AXIS_LOW = 40;     // 이보다 적으면 얇다고 본다 (5축 균형 기준)

function renderQuestions() {
  const c = content;
  // 막대는 '출제중'이고, 검수를 기다리는 몫은 옆에 따로 적는다.
  // 방금 만든 문항이 왜 숫자에 안 잡히는지 화면에서 바로 보여야 한다.
  const axes = c.axes.map((a) => {
    const low = a.n < AXIS_LOW;
    return `<div class="sbar">
      <span class="sbl">${esc(a.name)}</span>
      <span class="sbt"><span class="sbf${low ? ' low' : ''}" style="width:${
        Math.min(100, Math.round((a.n / 80) * 100))}%"></span></span>
      <span class="sbn">${a.n}${a.draft ? `<span class="sbd">+${a.draft}</span>` : ''}${low ? ' ⚠' : ''}</span>
    </div>`;
  }).join('');

  const parts = c.parts.map((p) => `<div class="row">
    <span class="row-main">
      <span class="row-t">${esc(c.parts_ko[p.part] ?? p.part)}</span>
      <span class="row-s">출제중 ${p.active}${p.draft ? ` · 준비중 ${p.draft}` : ''}${
        p.retired ? ` · 내림 ${p.retired}` : ''}</span>
    </span>
    <button class="btn ghost small" data-order="${esc(p.part)}">만들기</button>
  </div>`).join('');

  // 얇은 개념 6개 — 여기가 다음에 만들 것이다
  const thin = c.tags.filter((t) => !t.id.startsWith('SEC.')).slice(0, 6).map((t) => `
    <button class="chip thin" data-order-tag="${esc(t.id)}" data-order-sec="${esc(t.section)}"
      title="${esc(t.id)}">${esc(t.name_ko)} ${t.n}</button>`).join('');

  const reported = c.reported.length ? c.reported.map((r) => `<div class="row">
    <span class="chip k-answer">신고 ${r.n}</span>
    <span class="row-main">
      <span class="row-t">${esc(r.stem || `${c.parts_ko[r.part] ?? r.part} 문항`)}</span>
      <span class="row-s">${esc(r.part)} · ${esc(r.kinds || '')}</span>
    </span>
    <button class="btn ghost small" data-open="${esc(r.id)}">열기</button>
  </div>`).join('') : '<p class="empty">신고된 문항이 없어요.</p>';

  const silent = (c.media?.lc_no_audio ?? 0) + (c.media?.l1_no_image ?? 0);

  view.innerHTML = `${tabsHtml()}
    ${c.repo.ready ? '' : `<div class="warn-box">저장소 연결이 아직 안 됐어요.
      새 문항을 만들려면 <b>GITHUB_TOKEN</b> 을 등록해야 합니다 (아래 '도움말' 참고).</div>`}

    <!-- 이 화면에서 할 일은 사실상 이 버튼 하나다. 무엇을 만들지 고르는 일은
         서버가 대신한다(얇은 축 → 그 축의 얇은 태그 → 그 태그가 나오는 파트). -->
    <div class="card fill-card" data-fillbox>
      <p class="empty" style="padding:14px 0">부족한 곳을 확인하는 중...</p>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">지금 문제은행</span>
        <span class="card-note">전체 ${c.total} · 출제중 ${c.active}</span></div>
      ${axes}
      <p class="card-note">막대는 실력 5칸이 각각 <b>출제 중인</b> 문항 수예요.
        <b>⚠ 표시된 칸이 다음에 만들 곳</b>입니다 (${AXIS_LOW}문항 미만).
        ${c.axes.some((a) => a.draft) ? '<b class="hot">+숫자</b>는 만들어 두고 <b>확인을 기다리는</b> 몫이라 아직 아이에게 안 나갑니다 — 아래에서 출제 시작을 눌러주세요.' : ''}</p>
      ${silent ? `<p class="card-note">소리·사진이 아직 없어 출제 못 하는 문항 ${silent}개
        — 음원 만들기 작업이 돌면 저절로 풀립니다.</p>` : ''}
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">얇은 개념</span>
        <span class="card-note">위 버튼이 여기부터 채웁니다</span></div>
      <div class="chips">${thin}</div>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">종류별</span>
        <span class="card-note">종류를 콕 집어 주문하려면 '만들기'</span></div>
      <div class="rows">${parts}</div>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">아이들이 신고한 문항</span></div>
      <div class="rows">${reported}</div>
    </div>

    <div class="card">
      <div class="card-head"><span class="card-title">문항 찾아보기</span></div>
      <div class="qfilter">
        <select data-fstatus>
          <option value="draft"${qFilter.status === 'draft' ? ' selected' : ''}>준비 중</option>
          <option value="active"${qFilter.status === 'active' ? ' selected' : ''}>출제 중</option>
          <option value="retired"${qFilter.status === 'retired' ? ' selected' : ''}>내린 것</option>
          <option value=""${!qFilter.status ? ' selected' : ''}>전체</option>
        </select>
        <select data-fpart>
          <option value="">모든 종류</option>
          ${Object.entries(c.parts_ko).map(([k, v]) =>
            `<option value="${esc(k)}"${qFilter.part === k ? ' selected' : ''}>${esc(v)}</option>`).join('')}
        </select>
        <input data-fq placeholder="문장 검색" value="${esc(qFilter.q ?? '')}" />
        <button class="btn ghost small" data-find>찾기</button>
      </div>
      <div class="rows" data-qlist><p class="empty">찾기를 눌러주세요.</p></div>
    </div>

    <p class="card-note" style="text-align:center;margin-top:10px">
      AI가 놓친 문제를 손으로 만들고 싶다면 <button class="linklike" data-new>직접 쓰기</button></p>`;

  bindTabs();
  renderFillBox();
  view.querySelector('[data-new]').addEventListener('click', () => showNewQuestion());
  view.querySelectorAll('[data-order]').forEach((b) =>
    b.addEventListener('click', () => showOrder({ part: b.dataset.order })));
  view.querySelectorAll('[data-order-tag]').forEach((b) =>
    b.addEventListener('click', () => showOrder({
      tag: b.dataset.orderTag,
      part: b.dataset.orderSec === 'LC' ? 'L3' : 'R3',
    })));
  view.querySelectorAll('[data-open]').forEach((b) =>
    b.addEventListener('click', () => showQuestion(b.dataset.open)));
  view.querySelector('[data-find]').addEventListener('click', findQuestions);
  view.querySelector('[data-fq]').addEventListener('keydown', (e) => { if (e.key === 'Enter') findQuestions(); });
  findQuestions();
}

async function findQuestions() {
  qFilter = {
    status: view.querySelector('[data-fstatus]').value,
    part: view.querySelector('[data-fpart]').value,
    q: view.querySelector('[data-fq]').value.trim(),
  };
  const box = view.querySelector('[data-qlist]');
  box.innerHTML = '<p class="empty">찾는 중...</p>';
  const qs = new URLSearchParams(Object.entries(qFilter).filter(([, v]) => v));
  try {
    const { items } = await api(`/api/admin/questions?${qs}`);
    box.innerHTML = items.length ? items.map((it) => {
      const rate = it.times_answered ? Math.round((it.times_correct / it.times_answered) * 100) : null;
      return `<div class="row">
        <span class="chip s-${esc(it.status)}">${
          { draft: '준비중', active: '출제중', retired: '내림' }[it.status] ?? it.status}</span>
        <span class="row-main">
          <span class="row-t">${esc(it.stem || `${content.parts_ko[it.part] ?? it.part} 문항`)}</span>
          <span class="row-s">${esc(it.part)} · 난이도 ${it.difficulty_label}${
            rate != null ? ` · 정답률 ${rate}%` : ''}${it.reports ? ` · 신고 ${it.reports}` : ''}${
            content.parts_ko[it.part]?.startsWith('듣기') && !it.audio_url ? ' · 소리 없음' : ''}</span>
        </span>
        <button class="btn ghost small" data-open="${esc(it.id)}">열기</button>
      </div>`;
    }).join('') : '<p class="empty">해당하는 문항이 없어요.</p>';
    box.querySelectorAll('[data-open]').forEach((b) =>
      b.addEventListener('click', () => showQuestion(b.dataset.open)));
  } catch (e) { if (!guard(e)) box.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
}

// ── 버튼 하나로 부족한 문제 채우기 ──
// 이 화면에서 운영자가 할 일은 사실상 이것뿐이다. 무엇을 몇 개 만들지는 서버가 정한다
// (얇은 축 → 그 축의 얇은 태그 → 그 태그가 실제로 나오는 파트). 고를 것도, 적을 것도 없다.
// 버튼에 미리 숫자를 적어 두는 이유: 누르기 전에 무엇이 만들어지는지 보여야 안심하고 누른다.
async function renderFillBox() {
  const box = view.querySelector('[data-fillbox]');
  if (!box) return;
  let p;
  try { p = await api('/api/admin/fill-gaps'); }
  catch (e) { if (!guard(e)) box.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; return; }

  const draftLine = p.drafts
    ? `<div class="fill-draft">
         <span>확인을 기다리는 새 문제 <b>${p.drafts}개</b></span>
         <button class="btn ghost small" data-seedrafts>보러 가기</button>
         <button class="btn small" data-activate>전부 출제 시작</button>
       </div>` : '';

  box.innerHTML = `
    <div class="card-head"><span class="card-title">문제 늘리기</span></div>
    ${p.total ? `
      <p class="card-note">지금 <b>${esc(p.orders.map((o) => o.why).join(' · '))}</b>가 얇아요.
        아래 버튼을 누르면 앱이 알아서 그 자리를 채웁니다 — 고르실 것 없습니다.</p>
      <button class="btn big" data-fill${p.ready ? '' : ' disabled'}>${esc(p.label)}</button>
      ${p.ready ? '' : '<p class="card-note">저장소 연결(GITHUB_TOKEN)을 먼저 등록해주세요.</p>'}`
    : '<p class="card-note">지금은 모든 칸이 충분해요. 더 만들 곳이 없습니다.</p>'}
    ${draftLine}
    <div data-fillmsg></div>`;

  const msg = box.querySelector('[data-fillmsg]');
  box.querySelector('[data-fill]')?.addEventListener('click', async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    msg.innerHTML = '<p class="card-note">주문을 넣는 중...</p>';
    try {
      const r = await api('/api/admin/fill-gaps', { method: 'POST', body: '{}' });
      msg.innerHTML = `<p class="msg ok">${esc(r.next)}</p>`;
    } catch (err) {
      if (guard(err)) return;
      msg.innerHTML = `<p class="msg bad">${esc(err.message)}</p>`;
      b.disabled = false;
    }
  });
  box.querySelector('[data-seedrafts]')?.addEventListener('click', () => {
    qFilter = { status: 'draft' };
    view.querySelector('[data-fstatus]').value = 'draft';
    view.querySelector('[data-fpart]').value = '';
    view.querySelector('[data-fq]').value = '';
    findQuestions();
    view.querySelector('[data-qlist]').scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
  box.querySelector('[data-activate]')?.addEventListener('click', async (e) => {
    if (!confirm('확인을 기다리는 새 문제를 전부 출제할까요?\n소리·사진이 아직 없는 것은 자동으로 남겨둡니다.')) return;
    const b = e.currentTarget;
    b.disabled = true;
    msg.innerHTML = '<p class="card-note">출제하는 중...</p>';
    try {
      const r = await api('/api/admin/questions/activate-drafts', { method: 'POST', body: '{}' });
      msg.innerHTML = `<p class="msg ok">${esc(r.next)}${
        r.synced ? '' : '<br>(저장소 반영은 못 했어요 — 다음 배포 때 되돌아올 수 있습니다)'}</p>`;
      setTimeout(showQuestions, 1400);
    } catch (err) {
      if (guard(err)) return;
      msg.innerHTML = `<p class="msg bad">${esc(err.message)}</p>`;
      b.disabled = false;
    }
  });
}

// ── 문항 하나 — 아이가 보는 그대로 + 출제/내리기 ──
const LETTERS = ['A', 'B', 'C', 'D'];

async function showQuestion(id) {
  view.innerHTML = `<p class="empty">불러오는 중...</p>`;
  let d;
  try { d = await api(`/api/admin/questions/${encodeURIComponent(id)}`); }
  catch (e) { if (!guard(e)) view.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; return; }
  const q = d.question;
  const imgs = Array.isArray(q.image_url) ? q.image_url : null;

  const choices = imgs
    ? `<div class="qimgs">${imgs.map((src, i) => `<div class="qimg${i === q.answer_idx ? ' good' : ''}">
        <img src="${esc(src)}" alt="보기 ${LETTERS[i]}" loading="lazy" />
        <span class="qletter">${LETTERS[i]}</span>${i === q.answer_idx ? '<span class="chip good">정답</span>' : ''}
      </div>`).join('')}</div>`
    : q.choices.map((cc, i) => `<div class="qchoice${i === q.answer_idx ? ' good' : ''}">
        <span class="qletter">${LETTERS[i]}</span><span class="qtext">${esc(cc)}</span>
        ${i === q.answer_idx ? '<span class="chip good">정답</span>' : ''}
        ${q.why_not?.[i] ? `<span class="row-s">${esc(q.why_not[i])}</span>` : ''}
      </div>`).join('');

  const source = q.script || q.p_content || '';
  const silent = content?.parts_ko[q.part]?.startsWith('듣기') && !q.audio_url;

  view.innerHTML = `
    <button class="back" data-back>← 문항 목록</button>
    <div class="card">
      <div class="card-head">
        <span class="card-title">${esc(content?.parts_ko[q.part] ?? q.part)}</span>
        <span class="chip s-${esc(q.status)}">${
          { draft: '준비중', active: '출제중', retired: '내림' }[q.status] ?? q.status}</span>
      </div>
      ${source ? `<div class="qpassage"><span class="qcap">${
        q.script ? '들려주는 내용' : '지문'}</span>${esc(source)}</div>` : ''}
      ${q.audio_url ? `<audio controls src="${esc(q.audio_url)}" style="width:100%;margin-top:8px"></audio>` : ''}
      ${silent ? '<div class="warn-box">아직 소리가 없어요 — 음원이 만들어져야 출제할 수 있습니다.</div>' : ''}
      ${q.translation_ko ? `<div class="qpassage"><span class="qcap">한글 해석</span>${
        esc(q.translation_ko)}</div>` : `<p class="card-note" style="margin-top:8px">
        ⚠ 한글 해석이 없는 문항입니다 — 정답 화면에 해석이 안 나갑니다.</p>`}
      ${q.stem ? `<p class="qstem">${esc(q.stem)}</p>` : ''}
      ${choices}
      <div class="qline"><span class="qcap">정답 풀이</span><p>${esc(q.explanation_ko)}</p></div>
      ${q.evidence ? `<div class="qline"><span class="qcap">근거</span><p>${esc(q.evidence)}</p></div>` : ''}
      <p class="card-note">난이도 ${q.difficulty_label} · 태그 ${esc(q.tags.join(', '))} · 정답률 ${
        q.times_answered ? Math.round((q.times_correct / q.times_answered) * 100) + '%' : '아직 없음'}</p>
    </div>

    ${d.reports.length ? `<div class="card">
      <div class="card-head"><span class="card-title">이 문항에 온 신고 ${d.reports.length}건</span></div>
      <div class="rows">${d.reports.map((r) => `<div class="row">
        <span class="chip k-${esc(r.kind)}">${esc(r.kind)}</span>
        <span class="row-main"><span class="row-t">${esc(r.note || '(적은 말 없음)')}</span>
          <span class="row-s">${esc(String(r.created_at).slice(0, 16).replace('T', ' '))}</span></span>
      </div>`).join('')}</div>
    </div>` : ''}

    <div class="card">
      <div class="card-head"><span class="card-title">이 문항을</span></div>
      <div class="modal-actions">
        ${q.status !== 'active' ? `<button class="btn" data-st="active"${silent ? ' disabled' : ''}>출제 시작</button>` : ''}
        ${q.status !== 'retired' ? '<button class="btn ghost" data-st="retired">내리기</button>' : ''}
        ${q.status === 'retired' ? '<button class="btn ghost" data-st="draft">준비 중으로</button>' : ''}
      </div>
      <p class="card-note">‘내리기’는 곧바로 반영돼요 — 다음 세트부터 이 문항이 나오지 않습니다.</p>
      <div data-stmsg></div>
    </div>`;

  view.querySelector('[data-back]').addEventListener('click', showQuestions);
  const msg = view.querySelector('[data-stmsg]');
  view.querySelectorAll('[data-st]').forEach((b) => b.addEventListener('click', async () => {
    const to = b.dataset.st;
    if (to === 'retired' && !confirm('이 문항을 내릴까요? 다음 세트부터 아이에게 나오지 않습니다.')) return;
    b.disabled = true;
    try {
      const r = await api(`/api/admin/questions/${encodeURIComponent(id)}/status`,
        { method: 'POST', body: JSON.stringify({ status: to }) });
      msg.innerHTML = `<p class="msg ok">바꿨어요.${
        r.synced ? '' : ' (저장소에는 반영하지 못해 다음 배포 때 되돌아올 수 있어요)'}</p>`;
      setTimeout(() => showQuestion(id), 900);
    } catch (e) { if (!guard(e)) { msg.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; b.disabled = false; } }
  }));
}

// ── 직접 만들기 ──
// 저장을 눌러야 알려주는 대신, 타이핑을 멈추면 바로 검사해서 무엇이 걸리는지 보여준다.
// 규칙이 까다로운 편이라(해설 100자·어려운 용어 금지·근거는 원문 그대로) 미리 알려주지 않으면
// 다 쓰고 나서 되돌리는 일이 반복된다.
function showNewQuestion() {
  const c = content;
  // 기본은 R1(문장 완성) — 칸이 가장 적어 처음 쓰는 사람이 끝까지 채울 수 있다.
  const partOpts = Object.entries(c.parts_ko)
    .map(([k, v]) => `<option value="${esc(k)}"${k === 'R1' ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const missOpts = Object.entries(c.miss_types)
    .map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');

  view.innerHTML = `
    <button class="back" data-back>← 문항 목록</button>
    <div class="card">
      <div class="card-head"><span class="card-title">새 문제 만들기</span></div>
      <p class="card-note">만든 문제는 <b>준비 중</b>으로 저장돼요. 확인한 뒤 ‘출제 시작’을
        눌러야 아이에게 나갑니다.</p>

      <label class="field"><span>종류</span><select data-part>${partOpts}</select></label>

      <div data-lc hidden>
        <label class="field"><span>들려줄 내용 (영어 대본)</span>
          <textarea data-script rows="4" placeholder="W: Where is my book?&#10;M: It's on the desk."></textarea></label>
        <label class="field"><span>발음</span><select data-accent>
          ${c.accents.map((a) => `<option value="${a}">${
            { US: '미국', UK: '영국', AU: '호주' }[a]}</option>`).join('')}</select></label>
      </div>
      <div data-rcset hidden>
        <label class="field"><span>지문 (영어)</span>
          <textarea data-passage rows="5" placeholder="읽을 글을 넣어주세요"></textarea></label>
      </div>
      <div data-l1 hidden>
        <p class="card-note">사진 고르기는 보기 4컷을 <b>사진 검색</b>으로 가져와요.
          컷마다 <b>검색어</b>와 <b>사진에 꼭 있어야 할 말</b>을 적어주세요
          (엉뚱한 사진이 들어가는 걸 막아줍니다).</p>
        <div data-l1rows></div>
      </div>

      <label class="field"><span>문제 문장</span>
        <input data-stem placeholder="Where is the book?" /></label>

      <div data-choices class="qform-choices"></div>

      <label class="field"><span>정답 풀이 (한국어, 100자 이내·쉬운 말로)</span>
        <textarea data-exp rows="2" placeholder="책상 위에 있다고 했어요."></textarea></label>
      <label class="field"><span>근거 — 원문에서 그대로 복사 (선택)</span>
        <input data-ev placeholder="It's on the desk." /></label>

      <div class="qform-row">
        <label class="field"><span>난이도</span><select data-diff>
          ${[1, 2, 3, 4, 5].map((n) => `<option value="${n}"${n === 2 ? ' selected' : ''}>${n}</option>`).join('')}
        </select></label>
        <label class="field"><span>개념 태그 (1~3개)</span><select data-tags multiple size="5">
          ${c.tags.filter((t) => !t.id.startsWith('SEC.'))
            .map((t) => `<option value="${esc(t.id)}">${esc(t.name_ko)} (${t.n})</option>`).join('')}
        </select></label>
      </div>

      <label class="field"><span>오늘의 표현 (선택)</span>
        <div class="qform-row">
          <input data-kexp placeholder="on the desk" />
          <input data-kko placeholder="책상 위에" />
        </div></label>

      <div data-check class="qcheck"></div>
      <div class="modal-actions">
        <button class="btn" data-save>저장하기</button>
        <button class="btn ghost" data-back2>그만두기</button>
      </div>
      <div data-savemsg></div>
    </div>
    <template data-misstpl>${missOpts}</template>`;

  const $ = (s) => view.querySelector(s);
  const partSel = $('[data-part]');

  // 종류를 고르면 그에 맞는 칸만 보인다 — 듣기면 대본·발음, 지문형이면 지문.
  function syncForm() {
    const part = partSel.value;
    const form = c.part_form[part] === 'both' ? 'single' : c.part_form[part];
    const isLC = part.startsWith('L');
    $('[data-lc]').hidden = !isLC;
    $('[data-rcset]').hidden = !(form === 'set' && !isLC);
    $('[data-l1]').hidden = part !== 'L1';
    if (part === 'L1' && !$('[data-l1rows]').children.length) {
      $('[data-l1rows]').innerHTML = Array.from({ length: 4 }, (_, i) => `
        <div class="qform-row">
          <input data-iq="${i}" placeholder="보기 ${LETTERS[i]} 사진 검색어 (영어)" />
          <input data-in="${i}" placeholder="꼭 있어야 할 말 (쉼표로)" />
        </div>`).join('');
    }
    // 보기 칸은 종류마다 개수가 다르다 (질의응답만 3개)
    const n = c.choices_by_part[part] ?? 4;
    $('[data-choices]').innerHTML = Array.from({ length: n }, (_, i) => `
      <div class="qform-choice">
        <label class="qform-ans"><input type="radio" name="ans" value="${i}"${i === 0 ? ' checked' : ''} />
          <span>${LETTERS[i]}</span></label>
        <input data-c="${i}" placeholder="보기 ${LETTERS[i]}" />
        <input data-w="${i}" placeholder="이 보기를 고른 아이에게 (40자 이내)" />
        <select data-m="${i}"><option value="">실수 유형 고르기</option>${missOpts}</select>
      </div>`).join('');
    bindLive();
    check();
  }

  // 화면의 입력을 저장 형식(JSON)으로 모은다 — 검사와 저장이 같은 것을 본다.
  function collect() {
    const part = partSel.value;
    const form = c.part_form[part] === 'both' ? 'single' : c.part_form[part];
    const isLC = part.startsWith('L');
    const n = c.choices_by_part[part] ?? 4;
    const answer = Number(view.querySelector('input[name="ans"]:checked')?.value ?? 0);
    const choices = Array.from({ length: n }, (_, i) => $(`[data-c="${i}"]`)?.value.trim() ?? '');
    const why = {};
    const miss = {};
    for (let i = 0; i < n; i++) {
      if (i === answer) continue;
      const w = $(`[data-w="${i}"]`)?.value.trim();
      const m = $(`[data-m="${i}"]`)?.value;
      if (w) { why[i] = w; if (m) miss[i] = m; }
    }
    const tags = [...$('[data-tags]').selectedOptions].map((o) => o.value);
    const kEn = $('[data-kexp]').value.trim();
    const kKo = $('[data-kko]').value.trim();
    const core = {
      stem: $('[data-stem]').value.trim() || null,
      choices, answer_idx: answer,
      explanation_ko: $('[data-exp]').value.trim(),
      difficulty_label: Number($('[data-diff]').value),
      tags,
      ...(($('[data-ev]').value.trim()) ? { evidence: $('[data-ev]').value.trim() } : {}),
      ...(Object.keys(why).length ? { why_not: why, miss_type: miss } : {}),
      ...((kEn && kKo) ? { key_expr: { en: kEn, ko: kKo } } : {}),
    };
    if (form === 'set') {
      return {
        part,
        item: {
          type: 'set', part,
          passage: isLC
            ? { kind: 'dialogue', script: $('[data-script]').value.trim(), accent: $('[data-accent]').value,
                tts_voices: { W: 'female', M: 'male' } }
            : { kind: 'text', content: $('[data-passage]').value.trim() },
          questions: [core],
        },
      };
    }
    const l1 = part === 'L1' ? (() => {
      const qs = Array.from({ length: 4 }, (_, i) => ({
        q: $(`[data-iq="${i}"]`)?.value.trim() ?? '',
        need: ($(`[data-in="${i}"]`)?.value ?? '').split(',').map((w) => w.trim()).filter(Boolean),
      }));
      return {
        choice_image_queries: qs,
        // 사진 설명은 검색어를 그대로 쓴다 — 배치가 사진을 고를 때 참고만 하는 값이다
        choice_image_prompts: qs.map((x) => x.q),
      };
    })() : {};
    return {
      part,
      item: {
        type: 'single', part, ...core,
        ...(isLC ? { tts_script: $('[data-script]').value.trim(), accent: $('[data-accent]').value } : {}),
        ...l1,
      },
    };
  }

  // 타이핑이 멈추면 검사 — 매 글자마다 부르면 서버가 시달린다
  let timer = null;
  const check = () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const box = $('[data-check]');
      try {
        const r = await api('/api/admin/questions/validate',
          { method: 'POST', body: JSON.stringify(collect()) });
        box.innerHTML = r.ok
          ? '<p class="msg ok">지금 이대로 저장할 수 있어요.</p>'
          : `<p class="qcheck-t">아직 이런 게 걸려요</p><ul>${
            r.errors.map((m) => `<li>${esc(m.replace(/^[^:]*:\s*/, ''))}</li>`).join('')}</ul>`;
      } catch (e) { if (!guard(e)) box.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`; }
    }, 500);
  };
  function bindLive() {
    view.querySelectorAll('input, textarea, select').forEach((el) => {
      el.removeEventListener('input', check);
      el.addEventListener('input', check);
    });
  }

  partSel.addEventListener('change', syncForm);
  $('[data-back]').addEventListener('click', showQuestions);
  $('[data-back2]').addEventListener('click', showQuestions);
  $('[data-save]').addEventListener('click', async () => {
    const btn = $('[data-save]');
    const msg = $('[data-savemsg]');
    btn.disabled = true;
    msg.innerHTML = '<p class="card-note">저장하는 중...</p>';
    try {
      const r = await api('/api/admin/questions', { method: 'POST', body: JSON.stringify(collect()) });
      msg.innerHTML = `<p class="msg ok">${esc(r.next)}<br>이름표: ${esc(r.tmp_id)}</p>`;
    } catch (e) {
      if (guard(e)) return;
      msg.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`;
      btn.disabled = false;
    }
  });
  syncForm();
}

// ── AI에게 초안 시키기 ──
function showOrder(pre = {}) {
  const c = content;
  view.innerHTML = `
    <button class="back" data-back>← 문항 목록</button>
    <div class="card">
      <div class="card-head"><span class="card-title">AI에게 초안 맡기기</span></div>
      <p class="card-note">주문하면 초안을 만들어 <b>준비 중</b>으로 넣어줘요.
        규칙에 어긋난 초안은 자동으로 버려집니다. 확인은 사람이 합니다.</p>

      <label class="field"><span>종류</span><select data-part>
        ${Object.entries(c.parts_ko).map(([k, v]) =>
          `<option value="${esc(k)}"${pre.part === k ? ' selected' : ''}>${esc(v)}</option>`).join('')}
      </select></label>
      <label class="field"><span>몇 문항 (1~20)</span>
        <input data-count type="number" min="1" max="20" value="5" /></label>
      <label class="field"><span>개념 태그 (비우면 자동)</span><select data-tag>
        <option value="">자동</option>
        ${c.tags.filter((t) => !t.id.startsWith('SEC.')).map((t) =>
          `<option value="${esc(t.id)}"${pre.tag === t.id ? ' selected' : ''}>${esc(t.name_ko)} (${t.n})</option>`).join('')}
      </select></label>
      <label class="field"><span>난이도 (비우면 섞어서)</span><select data-diff>
        <option value="">섞어서</option>
        ${[1, 2, 3, 4, 5].map((n) => `<option value="${n}">${n}</option>`).join('')}
      </select></label>
      <label class="field"><span>추가 요청 (선택)</span>
        <input data-note placeholder="예: 학교 급식이나 체육대회 소재로" /></label>

      <div class="modal-actions">
        <button class="btn" data-go>주문하기</button>
        <button class="btn ghost" data-back2>그만두기</button>
      </div>
      <div data-msg></div>
    </div>`;
  const $ = (s) => view.querySelector(s);
  $('[data-back]').addEventListener('click', showQuestions);
  $('[data-back2]').addEventListener('click', showQuestions);
  $('[data-go]').addEventListener('click', async () => {
    const btn = $('[data-go]');
    const msg = $('[data-msg]');
    btn.disabled = true;
    msg.innerHTML = '<p class="card-note">주문을 넣는 중...</p>';
    try {
      const r = await api('/api/admin/generate-order', {
        method: 'POST',
        body: JSON.stringify({
          part: $('[data-part]').value,
          count: Number($('[data-count]').value),
          tag: $('[data-tag]').value,
          difficulty: $('[data-diff]').value,
          note: $('[data-note]').value.trim(),
        }),
      });
      msg.innerHTML = `<p class="msg ok">${esc(r.next)}</p>`;
    } catch (e) {
      if (guard(e)) return;
      msg.innerHTML = `<p class="msg bad">${esc(e.message)}</p>`;
      btn.disabled = false;
    }
  });
}

// 이미 로그인돼 있으면 바로 메인. 아니면 관리자가 아예 없는지 먼저 물어보고,
// 없으면 '처음 시작하기', 있으면 평범한 로그인 화면.
auth ? showMain() : start();
