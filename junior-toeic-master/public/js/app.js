// 점프리시 M1 — 문항 열람·풀어보기 (모바일 세로 우선)
// 정답은 이 앱 어디에도 없다: 보기 선택 시 POST /api/check 가 채점·해설을 반환한다.

const view = document.getElementById('view');

const PART_INFO = {
  L1: { name: '사진 고르기', desc: '문장을 듣고 알맞은 그림 찾기' },
  L2: { name: '질의응답', desc: '질문을 듣고 알맞은 대답 고르기' },
  L3: { name: '짧은 대화', desc: '두 사람의 대화 듣기' },
  L4: { name: '짧은 담화', desc: '안내 방송·이야기 듣기' },
  R1: { name: '문장 완성', desc: '빈칸에 알맞은 말 고르기' },
  R2: { name: '지문 완성', desc: '글의 빈칸 3개 채우기' },
  R3: { name: '독해', desc: '글을 읽고 물음에 답하기' },
};
const ACCENT_KO = { US: '미국 발음', UK: '영국 발음', AU: '호주 발음' };
const LETTERS = ['A', 'B', 'C', 'D'];

const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

async function api(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `요청 실패 (${res.status})`);
  return data;
}

function renderError(msg) {
  view.innerHTML = `<div class="error-box"><strong>문제가 생겼어요.</strong><br>${esc(msg)}<br>
    <button class="btn-ghost" style="margin-top:10px" onclick="location.reload()">다시 시도</button></div>`;
}

// ---------- 홈: 파트 그리드 ----------
async function showHome() {
  view.innerHTML = '<p class="loading">불러오는 중...</p>';
  try {
    const { parts } = await api('/api/parts');
    const byCode = Object.fromEntries(parts.map((p) => [p.part, p]));
    const card = (code) => {
      const p = byCode[code];
      const info = PART_INFO[code];
      const count = p ? p.total : 0;
      const meta = p
        ? `${count}문항${p.total !== p.active ? ` · 준비 중 ${p.total - p.active}` : ''}`
        : '준비 중';
      return `<button class="part-card" data-part="${code}" ${count ? '' : 'disabled'}>
        <span class="part-code">${code}</span>
        <span class="part-name">${info.name}</span>
        <span class="part-meta">${info.desc} · ${meta}</span>
      </button>`;
    };
    view.innerHTML = `
      <div class="hero">
        <h1>매일 조금씩, 영어 실력이 점프!</h1>
        <p>M1 단계 미리보기: 만들어진 문항을 직접 풀어보며 검수할 수 있어요.</p>
      </div>
      <p class="section-label">듣기 (Listening)</p>
      <div class="part-grid">${['L1', 'L2', 'L3', 'L4'].map(card).join('')}</div>
      <p class="section-label">읽기 (Reading)</p>
      <div class="part-grid">${['R1', 'R2', 'R3'].map(card).join('')}</div>`;
    view.querySelectorAll('.part-card[data-part]').forEach((b) =>
      b.addEventListener('click', () => showPlayer(b.dataset.part)));
  } catch (e) { renderError(e.message); }
}

// ---------- 플레이어 ----------
const state = { part: null, questions: [], passages: {}, idx: 0 };

async function showPlayer(part) {
  view.innerHTML = '<p class="loading">문항을 가져오는 중...</p>';
  try {
    const data = await api(`/api/questions?part=${part}`);
    if (!data.questions.length) return renderError('이 파트에는 아직 문항이 없어요.');
    Object.assign(state, { part, questions: data.questions, passages: data.passages, idx: 0 });
    renderQuestion();
  } catch (e) { renderError(e.message); }
}

function renderQuestion() {
  const q = state.questions[state.idx];
  const passage = q.passage_id ? state.passages[q.passage_id] : null;
  const info = PART_INFO[q.part];

  const chips = [
    `<span class="chip">${q.part} ${info.name}</span>`,
    `<span class="chip">난이도 ${q.difficulty_label}</span>`,
    q.accent ? `<span class="chip">${ACCENT_KO[q.accent] || q.accent}</span>` : '',
    q.status === 'draft' ? `<span class="chip warn">초안</span>` : '',
  ].join('');

  // 듣기 자료 영역: 음원이 있으면 플레이어, 없으면 스크립트 열람(검수용)
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
  if (q.part === 'L1' && !q.image_url) {
    media = `<p class="notice">그림 준비 중인 초안 문항이에요. 아래 스크립트와 그림 설명으로 검수해요.</p>` + media;
  }

  // 읽기 지문
  const readingPassage = (q.section === 'RC' && passage)
    ? `<div class="passage">${esc(passage.content)}</div>` : '';

  view.innerHTML = `
    <div class="player-head">
      <button class="btn-ghost" data-home>목록으로</button>
      <span class="progress">${state.idx + 1} / ${state.questions.length}</span>
    </div>
    <div class="qcard">
      <div class="qbadges">${chips}</div>
      ${readingPassage}${media}
      ${q.stem ? `<p class="stem">${esc(q.stem)}</p>` : ''}
      <div class="choices">
        ${q.choices.map((c, i) => `
          <button class="choice" data-idx="${i}">
            <span class="letter">${LETTERS[i]}</span><span>${esc(c)}</span>
          </button>`).join('')}
      </div>
      <div data-result></div>
      <div class="nav-row">
        <button class="btn-primary" data-next disabled>다음 문제</button>
      </div>
    </div>`;

  view.querySelector('[data-home]').addEventListener('click', showHome);
  view.querySelector('[data-toggle]')?.addEventListener('click', (e) => {
    const box = view.querySelector('[data-script]');
    box.hidden = !box.hidden;
    e.target.textContent = box.hidden ? '스크립트 보기' : '스크립트 접기';
  });
  const nextBtn = view.querySelector('[data-next]');
  nextBtn.addEventListener('click', () => {
    if (state.idx + 1 >= state.questions.length) return showHome();
    state.idx += 1;
    renderQuestion();
  });
  if (state.idx + 1 >= state.questions.length) nextBtn.textContent = '목록으로 돌아가기';

  const buttons = [...view.querySelectorAll('.choice')];
  buttons.forEach((btn) => btn.addEventListener('click', async () => {
    buttons.forEach((b) => (b.disabled = true));
    try {
      const r = await api('/api/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: q.id, chosen_idx: Number(btn.dataset.idx) }),
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
