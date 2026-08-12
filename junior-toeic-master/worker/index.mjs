// 점프리시(Jumplish) API Worker — Hono
// 절대 규칙: 문항을 내려주는 어떤 응답에도 answer_idx·explanation_ko를 포함하지 않는다.
// 채점 엔드포인트만 정답에 접근한다. (docs/engine.md · PRD 6절)
import { Hono } from 'hono';
import {
  verifyPin, hashPin, makeToken, requireAuth, requireRole, verifyToken,
  loginLockedFor, noteLoginFail, clearLoginFails,
  isStudentPin, isStaffSecret, STAFF_ROLES, SECRET_MIN, weakSecretReason,
  requireParent, requireParentAccount,
  hashSecret, verifySecret, makeAccountToken,
} from './auth.mjs';
import { recordAnswer, composeDailySet, computeClimb, computeSkillMap, kstDate, DIAG, diagBand, pickDiagQuestions } from './engine.mjs';

// 진단 답안 일괄 채점·기록 (Elo·SRS 미반영 — engine.md 4절)
async function gradeDiagAnswers(db, user, sessionId, answers) {
  const now = new Date().toISOString();
  const stmts = [];
  const graded = [];
  for (const a of answers) {
    const q = await db.prepare('SELECT id, part, section, answer_idx FROM questions WHERE id = ?1')
      .bind(a.question_id).first();
    if (!q) continue;
    const correct = a.chosen_idx === q.answer_idx ? 1 : 0;
    graded.push({ part: q.part, section: q.section, correct });
    stmts.push(db.prepare(
      `INSERT INTO answers (id, session_id, user_id, question_id, chosen_idx, is_correct, time_ms, answered_at)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`
    ).bind(crypto.randomUUID(), sessionId, user.id, q.id, a.chosen_idx | 0, correct, a.time_ms | 0, now));
  }
  if (stmts.length) await db.batch(stmts);
  return graded;
}

// 채점 뒤에만 내려주는 "정답 근거" — 근거 부분(evidence)과 그것이 들어 있는 원문(text).
// 화면은 text 안에서 evidence 자리를 형광펜으로 칠한다. 글 해설보다 먼저 눈에 들어온다.
// 채점 전에는 절대 내려가지 않는다 (스크립트가 곧 답이 되는 LC 문항 보호).
async function evidenceOf(db, q) {
  if (!q.evidence) return { evidence: null, evidence_text: null };
  let text = q.script || q.stem || null;
  if (!text?.includes(q.evidence) && q.passage_id) {
    const p = await db.prepare('SELECT content FROM passages WHERE id = ?1').bind(q.passage_id).first();
    text = p?.content ?? text;
  }
  if (!text?.includes(q.evidence)) return { evidence: null, evidence_text: null };
  return { evidence: q.evidence, evidence_text: text };
}

const parseJson = (s) => { try { return s ? JSON.parse(s) : null; } catch { return null; } };

// 채점 결과에 붙는 "글이 아닌 해설" 묶음.
//  why_not  : 아이가 고른 보기 하나의 이유만 (다른 오답까지 주면 읽지 않는다)
//  key_expr : 이 문제에서 챙길 표현 카드
//  concept  : 개념 그림을 고르는 열쇠 — 문법 태그 우선, 없으면 듣기 전략 태그
async function feedbackOf(db, q, chosenIdx) {
  const why = parseJson(q.why_not);
  const miss = parseJson(q.miss_type);
  const { results: tags } = await db.prepare(
    'SELECT tag_id FROM question_tags WHERE question_id = ?1'
  ).bind(q.id).all();
  const codes = tags.map((t) => t.tag_id);
  return {
    ...(await evidenceOf(db, q)),
    why_not: (why && chosenIdx !== q.answer_idx) ? (why[String(chosenIdx)] ?? null) : null,
    miss_type: (miss && chosenIdx !== q.answer_idx) ? (miss[String(chosenIdx)] ?? null) : null,
    key_expr: parseJson(q.key_expr),
    concept: codes.find((t) => t.startsWith('G.')) || codes.find((t) => t === 'LS.qr') || null,
  };
}

const groupOf = async (db, user) => {
  const size = (await db.prepare('SELECT set_size FROM classes WHERE id = ?1').bind(user.class_id).first())?.set_size ?? 12;
  return size <= 12 ? 'junior' : 'basic';
};

// 문항 id 목록 → 학생용 필드(정답·해설·스크립트 미포함) + 지문. 시험 순서(파트 오름차순) 정렬.
async function hydrate(db, ids) {
  if (!ids.length) return { questions: [], passages: {} };
  const qm = ids.map((_, i) => `?${i + 1}`).join(',');
  const { results: rows } = await db.prepare(
    `SELECT id, passage_id, section, part, stem, choices, difficulty_label,
            audio_url, image_url, accent, status
       FROM questions WHERE id IN (${qm})`
  ).bind(...ids).all();
  rows.sort((a, b) => a.part.localeCompare(b.part) || a.id.localeCompare(b.id));
  const pids = [...new Set(rows.map((q) => q.passage_id).filter(Boolean))];
  const passages = {};
  if (pids.length) {
    const pm = pids.map((_, i) => `?${i + 1}`).join(',');
    const { results } = await db.prepare(
      `SELECT id, kind, content, image_url, audio_url, accent FROM passages WHERE id IN (${pm})`
    ).bind(...pids).all();
    for (const p of results) passages[p.id] = p;
  }
  return { questions: rows.map((q) => ({ ...q, choices: JSON.parse(q.choices) })), passages };
}

const app = new Hono();

const PART_RE = /^(L[1-4]|R[1-3])$/;

// ── 인증 (M2): 학원 발급 로그인ID + 6자리 PIN ──
app.post('/api/auth/login', async (c) => {
  const { login_id, pin } = await c.req.json().catch(() => ({}));
  // 학생은 6자리 숫자, 관리자·강사는 8자 이상 비밀번호. 둘 다 여기로 들어온다.
  // 로그인ID 길이도 여기서 막는다 — 실패는 아이디별로 기록하므로, 길이를 안 막으면
  // 아무 문자열이나 던져 login_attempts 표를 무한히 부풀릴 수 있다.
  if (typeof login_id !== 'string' || login_id.trim().length < 1 || login_id.trim().length > 32
      || !(isStudentPin(pin) || isStaffSecret(pin))) {
    return c.json({ error: '로그인ID와 비밀번호를 확인하세요' }, 400);
  }
  const id = login_id.trim().toUpperCase();

  // 잠겨 있으면 PIN을 보지도 않는다 — 맞는지 틀리는지조차 알려주면 안 된다
  const lockLeft = await loginLockedFor(c.env.DB, id);
  if (lockLeft > 0) {
    const m = Math.ceil(lockLeft / 60);
    return c.json({ error: `여러 번 틀려서 잠겼어요. ${m}분 뒤에 다시 해주세요` }, 429);
  }

  const user = await c.env.DB.prepare(
    'SELECT * FROM users WHERE login_id = ?1'
  ).bind(id).first();
  // 계정 존재 여부를 구분해 알려주지 않는다 (계정 추측 방지)
  // — 없는 계정도 실패로 기록한다. 안 그러면 "잠기는 아이디 = 있는 아이디"가 되어 버린다.
  if (!user || !(await verifyPin(String(pin), user.pin_hash))) {
    const { lockedSeconds } = await noteLoginFail(c.env.DB, id);
    return c.json({
      error: lockedSeconds
        ? `여러 번 틀려서 ${Math.ceil(lockedSeconds / 60)}분 동안 잠겼어요`
        : '로그인ID 또는 비밀번호가 맞지 않아요',
    }, lockedSeconds ? 429 : 401);
  }
  // 학생 계정에 긴 비밀번호로, 관리자 계정에 6자리로 들어오는 일은 없어야 한다
  if (STAFF_ROLES.includes(user.role) && !isStaffSecret(pin)) {
    await noteLoginFail(c.env.DB, id);
    return c.json({ error: '로그인ID 또는 비밀번호가 맞지 않아요' }, 401);
  }
  await clearLoginFails(c.env.DB, id);
  return c.json({
    token: await makeToken(user),
    user: { id: user.id, login_id: user.login_id, display_name: user.display_name, role: user.role },
  });
});

app.get('/api/me', requireAuth, async (c) => {
  const u = c.get('user');
  const stats = await c.env.DB.prepare(
    `SELECT COUNT(*) AS answered, COALESCE(SUM(is_correct), 0) AS correct
       FROM answers WHERE user_id = ?1`
  ).bind(u.id).first();
  const due = await c.env.DB.prepare(
    `SELECT COUNT(*) AS n FROM review_queue
      WHERE user_id = ?1 AND graduated_at IS NULL AND due_at <= ?2`
  ).bind(u.id, kstDate()).first();
  const climb = await computeClimb(c.env.DB, u);
  const diag = await c.env.DB.prepare(
    `SELECT summary FROM sessions WHERE user_id = ?1 AND type = 'diagnostic' AND finished_at IS NOT NULL LIMIT 1`
  ).bind(u.id).first();
  return c.json({
    user: { id: u.id, login_id: u.login_id, display_name: u.display_name, role: u.role },
    answered: stats.answered, correct: stats.correct, review_due: due.n, sealed: climb.breakdown.sealed,
    climb,
    diagnosed: !!diag, diag_report: diag ? JSON.parse(diag.summary) : null,
  });
});

// ── 진단 테스트 (2단계 적응형) ──
app.post('/api/diagnostic/start', requireAuth, async (c) => {
  const u = c.get('user');
  const done = await c.env.DB.prepare(
    `SELECT id FROM sessions WHERE user_id = ?1 AND type = 'diagnostic' AND finished_at IS NOT NULL LIMIT 1`
  ).bind(u.id).first();
  if (done) return c.json({ done: true });

  // 아직 안 끝났고 답도 하나 없는 옛 진단 세션은 지운다.
  // 아이가 진단을 시작만 하고 나가는 일이 반복되면 빈 세션이 계속 쌓인다.
  // (답이 하나라도 들어간 세션은 건드리지 않는다 — 기록이다)
  await c.env.DB.prepare(
    `DELETE FROM sessions
      WHERE user_id = ?1 AND type = 'diagnostic' AND finished_at IS NULL
        AND id NOT IN (SELECT DISTINCT session_id FROM answers WHERE user_id = ?1)`
  ).bind(u.id).run();

  const group = await groupOf(c.env.DB, u);
  const label = DIAG.stage1Label[group];
  const ids = [];
  for (const [part, [n1]] of Object.entries(DIAG[group])) {
    ids.push(...await pickDiagQuestions(c.env.DB, part, label, n1, ids));
  }
  const sessionId = crypto.randomUUID();
  await c.env.DB.prepare(
    `INSERT INTO sessions (id, user_id, type, question_ids, started_at) VALUES (?1, ?2, 'diagnostic', ?3, ?4)`
  ).bind(sessionId, u.id, JSON.stringify(ids), new Date().toISOString()).run();
  const { questions, passages } = await hydrate(c.env.DB, ids);
  return c.json({ session_id: sessionId, stage: 1, group, count: questions.length, questions, passages });
});

// 1단계 답안 제출 → 섹션 정답률로 2단계 난이도 결정, 2단계 문항 반환
app.post('/api/diagnostic/stage2', requireAuth, async (c) => {
  const u = c.get('user');
  const { session_id, answers } = await c.req.json().catch(() => ({}));
  const sess = await c.env.DB.prepare(
    `SELECT id, question_ids FROM sessions WHERE id = ?1 AND user_id = ?2 AND type = 'diagnostic' AND finished_at IS NULL`
  ).bind(String(session_id), u.id).first();
  if (!sess || !Array.isArray(answers)) return c.json({ error: '진단 세션이 없습니다' }, 400);
  const graded = await gradeDiagAnswers(c.env.DB, u, sess.id, answers);
  const accOf = (sec) => {
    const rows = graded.filter((g) => g.section === sec);
    return rows.length ? rows.reduce((n, g) => n + g.correct, 0) / rows.length : 0.5;
  };
  const group = await groupOf(c.env.DB, u);
  const labels = { LC: DIAG.stage2Label(group, accOf('LC')), RC: DIAG.stage2Label(group, accOf('RC')) };
  const prev = JSON.parse(sess.question_ids);
  const ids = [];
  for (const [part, [, n2]] of Object.entries(DIAG[group])) {
    const label = labels[part.startsWith('L') ? 'LC' : 'RC'];
    ids.push(...await pickDiagQuestions(c.env.DB, part, label, n2, [...prev, ...ids]));
  }
  await c.env.DB.prepare('UPDATE sessions SET question_ids = ?1 WHERE id = ?2')
    .bind(JSON.stringify([...prev, ...ids]), sess.id).run();
  const { questions, passages } = await hydrate(c.env.DB, ids);
  return c.json({ session_id: sess.id, stage: 2, count: questions.length, questions, passages });
});

// 2단계 답안 제출 → 파트별 대역 → 태그 초기 레이팅 기록, 결과 반환
app.post('/api/diagnostic/finish', requireAuth, async (c) => {
  const u = c.get('user');
  const { session_id, answers } = await c.req.json().catch(() => ({}));
  const sess = await c.env.DB.prepare(
    `SELECT id FROM sessions WHERE id = ?1 AND user_id = ?2 AND type = 'diagnostic' AND finished_at IS NULL`
  ).bind(String(session_id), u.id).first();
  if (!sess || !Array.isArray(answers)) return c.json({ error: '진단 세션이 없습니다' }, 400);
  await gradeDiagAnswers(c.env.DB, u, sess.id, answers);

  // 세션 전체(1+2단계) 답안으로 파트별 정확도 산출
  const { results: all } = await c.env.DB.prepare(
    `SELECT q.part, a.is_correct FROM answers a JOIN questions q ON q.id = a.question_id
      WHERE a.session_id = ?1`
  ).bind(sess.id).all();
  const byPart = {};
  for (const r of all) {
    const p = (byPart[r.part] ||= { n: 0, c: 0 });
    p.n += 1; p.c += r.is_correct;
  }
  const now = new Date().toISOString();
  const stmts = [];
  const report = [];
  for (const [part, { n, c: cor }] of Object.entries(byPart)) {
    const accPct = Math.round((cor / n) * 100);
    const [, grade, rating] = diagBand(accPct);
    report.push({ part, grade, acc: accPct, count: n });
    // 그 파트에서 실제 풀린 문항들의 태그를 초기화 대상으로 삼는다
    // (concept_tags.part는 어휘 등 공용 태그에서 NULL이라 직접 매핑이 샌다)
    const { results: tags } = await c.env.DB.prepare(
      `SELECT DISTINCT qt.tag_id AS id FROM answers a
         JOIN question_tags qt ON qt.question_id = a.question_id
         JOIN questions q ON q.id = a.question_id
        WHERE a.session_id = ?1 AND q.part = ?2`
    ).bind(sess.id, part).all();
    for (const { id: tagId } of tags) {
      stmts.push(c.env.DB.prepare(
        `INSERT INTO user_tag_skills (user_id, tag_id, rating, attempts, correct, last_practiced_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(user_id, tag_id) DO UPDATE SET rating = ?3, attempts = ?4, correct = ?5, last_practiced_at = ?6`
      ).bind(u.id, tagId, rating, n, cor, now));
    }
  }
  report.sort((a, b) => a.part.localeCompare(b.part));
  stmts.push(c.env.DB.prepare('UPDATE sessions SET finished_at = ?1, summary = ?2 WHERE id = ?3')
    .bind(now, JSON.stringify(report), sess.id));
  await c.env.DB.batch(stmts);
  return c.json({ report, group: await groupOf(c.env.DB, u) });
});

// 개인 최고 기록 (M3-3 '어제의 나와 대결') — 비교 대상은 남이 아니라 과거의 나
app.get('/api/records', requireAuth, async (c) => {
  const u = c.get('user');
  const [{ results: seq }, best, today, { results: parts }, { results: days }] = await Promise.all([
    c.env.DB.prepare(
      `SELECT is_correct FROM answers WHERE user_id = ?1 ORDER BY answered_at LIMIT 2000`
    ).bind(u.id).all(),
    c.env.DB.prepare(
      `SELECT date(answered_at, '+9 hours') AS d, COUNT(*) AS n FROM answers
        WHERE user_id = ?1 GROUP BY d ORDER BY n DESC, d LIMIT 1`
    ).bind(u.id).first(),
    c.env.DB.prepare(
      `SELECT COUNT(*) AS n FROM answers WHERE user_id = ?1 AND date(answered_at, '+9 hours') = ?2`
    ).bind(u.id, kstDate()).first(),
    // 파트별 기록 — 예전엔 이 기기(localStorage)에만 있었다. 학원 태블릿을 여러 명이
    // 돌려 쓰면 기록이 섞이고, 기기를 바꾸면 통째로 사라진다. 그래서 서버에서 센다.
    c.env.DB.prepare(
      `SELECT q.part, COUNT(*) AS answered, COALESCE(SUM(a.is_correct), 0) AS correct
         FROM answers a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ?1 GROUP BY q.part`
    ).bind(u.id).all(),
    // 공부한 날짜들 — '이어온 날'(연속)을 세려면 날짜 목록이 필요하다.
    // climb.breakdown.days 는 '총 며칠'이라 연속이 끊겨도 계속 늘어난다 — 다른 숫자다.
    c.env.DB.prepare(
      `SELECT DISTINCT date(answered_at, '+9 hours') AS d FROM answers
        WHERE user_id = ?1 ORDER BY d DESC LIMIT 400`
    ).bind(u.id).all(),
  ]);
  // 최장 연속 정답 + 지금 이어지는 연속 (최근 답부터 뒤로)
  let bestRun = 0, run = 0;
  for (const r of seq) { run = r.is_correct ? run + 1 : 0; if (run > bestRun) bestRun = run; }
  let currentRun = 0;
  for (let i = seq.length - 1; i >= 0 && seq[i].is_correct; i--) currentRun++;
  // 이어온 날(연속) — 오늘 아직 안 했으면 어제부터 센다. 오늘 안 풀었다고 어제까지의
  // 연속이 0이 되면 아침에 앱을 열자마자 기록이 사라진 것처럼 보인다.
  const dayset = new Set(days.map((r) => r.d));
  let streak = 0;
  const cur = new Date(`${kstDate()}T00:00:00Z`);
  if (!dayset.has(kstDate())) cur.setUTCDate(cur.getUTCDate() - 1);
  while (dayset.has(cur.toISOString().slice(0, 10))) { streak += 1; cur.setUTCDate(cur.getUTCDate() - 1); }

  return c.json({
    best_run: bestRun, current_run: currentRun,
    best_day: best ? { date: best.d, n: best.n } : null,
    today_n: today.n,
    streak,
    parts: Object.fromEntries(parts.map((p) => [p.part, { answered: p.answered, correct: p.correct }])),
  });
});

// 로그인 학생의 오답 복습 목록 — 오늘까지 도래한 SRS 큐 (오래된 순)
app.get('/api/review', requireAuth, async (c) => {
  const u = c.get('user');
  const { results } = await c.env.DB.prepare(
    `SELECT question_id, box, due_at FROM review_queue
      WHERE user_id = ?1 AND graduated_at IS NULL AND due_at <= ?2
      ORDER BY due_at LIMIT 50`
  ).bind(u.id, kstDate()).all();
  const { questions, passages } = await hydrate(c.env.DB, results.map((r) => r.question_id));
  const boxBy = Object.fromEntries(results.map((r) => [r.question_id, r.box]));
  return c.json({
    count: questions.length,
    questions: questions.map((q) => ({ ...q, srs_box: boxBy[q.id] })),
    passages,
  });
});

// 로그인 학생의 채점 — 기록·실력 갱신·SRS까지 서버가 처리한다 (M1 /api/check의 상위 호환)
app.post('/api/answers', requireAuth, async (c) => {
  const u = c.get('user');
  const body = await c.req.json().catch(() => ({}));
  const { question_id, chosen_idx, time_ms } = body;
  if (typeof question_id !== 'string' || !Number.isInteger(chosen_idx)) {
    return c.json({ error: 'question_id(문자열), chosen_idx(정수)가 필요합니다' }, 400);
  }
  const q = await c.env.DB.prepare(
    'SELECT id, passage_id, stem, script, evidence, why_not, miss_type, key_expr, answer_idx, explanation_ko, rating FROM questions WHERE id = ?1'
  ).bind(question_id).first();
  if (!q) return c.json({ error: '문항을 찾을 수 없습니다' }, 404);

  // 하루 한 세션(daily)에 묶는다 — question_ids 목록은 answers 테이블로 대신한다(M2-1 단순화)
  const today = kstDate();
  let session = await c.env.DB.prepare(
    `SELECT id FROM sessions WHERE user_id = ?1 AND type = 'daily' AND started_at LIKE ?2 || '%'`
  ).bind(u.id, today).first();
  if (!session) {
    session = { id: crypto.randomUUID() };
    await c.env.DB.prepare(
      `INSERT INTO sessions (id, user_id, type, question_ids, started_at) VALUES (?1, ?2, 'daily', '[]', ?3)`
    ).bind(session.id, u.id, new Date().toISOString()).run();
  }

  const { correct, graduated } = await recordAnswer(c.env.DB, {
    user: u, question: q, chosenIdx: chosen_idx, timeMs: time_ms | 0, sessionId: session.id,
  });
  return c.json({
    correct, graduated, answer_idx: q.answer_idx, explanation_ko: q.explanation_ko,
    ...(await feedbackOf(c.env.DB, q, chosen_idx)),
  });
});

// 실력 지도 — 레이더 5축 + 옆에 붙는 설욕률·빠르기.
// 화면이 어떻게 생기든 숫자는 여기서 나온다.
app.get('/api/skillmap', requireAuth, async (c) =>
  c.json(await computeSkillMap(c.env.DB, c.get('user'))));

// 화면에 뜰 이름 바꾸기.
// 개인정보 최소화 원칙상 이름은 '별명'이다 — 실명을 받으면 우리가 안 받겠다고 한 정보를
// 받는 셈이 된다. 그래서 실명처럼 보이는 걸 막지는 못해도, 화면에서 별명이라고 안내하고
// 길이·문자·나쁜 말만 서버에서 막는다. 로그인ID(학원 발급)는 바뀌지 않는다.
const NAME_MAX = 12;
const NAME_BLOCK = ['씨발', '시발', '병신', '좆', '지랄', 'ㅅㅂ', 'ㅄ', 'fuck', 'shit', 'bitch'];
app.post('/api/me/name', requireAuth, async (c) => {
  const u = c.get('user');
  const { display_name } = await c.req.json().catch(() => ({}));
  const name = typeof display_name === 'string' ? display_name.replace(/\s+/g, ' ').trim() : '';
  if (!name) return c.json({ error: '이름을 적어주세요' }, 400);
  if ([...name].length > NAME_MAX) return c.json({ error: `이름은 ${NAME_MAX}자까지예요` }, 400);
  if (/[\u0000-\u001f<>]/.test(name)) return c.json({ error: '쓸 수 없는 글자가 있어요' }, 400);
  const low = name.toLowerCase().replace(/\s/g, '');
  if (NAME_BLOCK.some((w) => low.includes(w))) return c.json({ error: '다른 이름으로 정해볼까요?' }, 400);

  await c.env.DB.prepare('UPDATE users SET display_name = ?1 WHERE id = ?2').bind(name, u.id).run();
  return c.json({ ok: true, display_name: name });
});

// 아이가 막힌 자리 신고 — 로그인 없이도 받는다(테스터가 로그인 전에 막힐 수도 있다).
// 답을 알려주지도, 아이를 탓하지도 않는다. 그냥 조용히 기록만 남긴다.
const FEEDBACK_KINDS = ['audio', 'image', 'hard', 'answer', 'etc'];
app.post('/api/feedback', async (c) => {
  const { question_id, kind, note, screen } = await c.req.json().catch(() => ({}));
  if (!FEEDBACK_KINDS.includes(kind)) return c.json({ error: '어떤 점이 불편한지 골라주세요' }, 400);
  const m = /^Bearer\s+(.+)$/.exec(c.req.header('Authorization') || '');
  const user = m ? await verifyToken(c.env.DB, m[1]) : null;
  // 문항 id는 실제로 있는 것만 남긴다 (오타·장난 입력이 외래키로 터지지 않게)
  const qid = typeof question_id === 'string'
    ? (await c.env.DB.prepare('SELECT id FROM questions WHERE id = ?1').bind(question_id).first())?.id ?? null
    : null;
  await c.env.DB.prepare(
    `INSERT INTO feedback (id, user_id, question_id, kind, note, screen, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7)`
  ).bind(crypto.randomUUID(), user?.id ?? null, qid, kind,
    typeof note === 'string' ? note.slice(0, 300) : null,
    typeof screen === 'string' ? screen.slice(0, 40) : null,
    new Date().toISOString()).run();
  return c.json({ ok: true });
});

// ══════════════════════════════════════════════════════════════════
//  관리자 API — 전부 super 전용. 학원·반·학생 계정 발급과 신고 확인.
//  지금까지는 계정을 늘리려면 손으로 SQL을 만들어 Cloudflare 콘솔에 붙여넣어야 했다.
// ══════════════════════════════════════════════════════════════════
const admin = [requireAuth, requireRole('super')];

// ── 첫 관리자 만들기 (딱 한 번만 열리는 문) ──
// 관리자 계정을 만드는 곳이 관리자 화면인데, 들어가려면 관리자 계정이 있어야 한다.
// 그 닭과 달걀을 푸는 문이다. 대신 아래 조건이 아니면 절대 열리지 않는다:
//   super 계정이 이 세상에 0개일 때만.
// 하나라도 생기는 순간 이 문은 영구히 닫히고, 그 뒤로는 관리자 화면에서만 계정을 만든다.
const superCount = async (db) =>
  (await db.prepare(`SELECT COUNT(*) AS n FROM users WHERE role = 'super'`).first()).n;

app.get('/api/setup/needed', async (c) => c.json({ needed: (await superCount(c.env.DB)) === 0 }));

// ══════════════════════════════════════════════════════════════════
//  학부모 API
//
//  들어오는 길이 두 개다.
//   1) 직접 가입 (B2C 주 경로) — 이메일 + 비밀번호. 학부모가 결제자이자 아이 계정의 주인.
//   2) 학원 발급 (유통 채널) — 자녀 아이디 + 학부모용 PIN. 기존 가정이 쓰던 방식 그대로.
//
//  어느 길로 들어오든 **읽기 전용**이다. 부모는 아이 대신 문제를 풀 수 없다.
// ══════════════════════════════════════════════════════════════════

// 아이에게 따로 아이디·비밀번호를 만들어 주지 않는다.
// **아이는 부모가 가입할 때 쓴 이메일·비밀번호 그대로 로그인한다.**
// 계정이 두 벌이면 부모가 여섯 자리 숫자를 아이에게 옮겨 적어 보내야 하고,
// 그 한 단계에서 가입을 포기한다. 가족이 하나의 열쇠를 쓰고, 아이가 여럿이면
// 로그인한 뒤 이름만 고른다.
//
// users.login_id 는 표에서 NOT NULL UNIQUE 라 값이 있어야 하므로 내부용으로만 만든다.
// 화면에 보여주지 않고, 문의가 들어왔을 때 사람을 특정하는 용도로만 쓴다.
const ID_ALPHA = 'ABCDEFGHJKLMNPQRTUVWXY2346789';
function makeChildLoginId() {
  const b = new Uint8Array(6);
  crypto.getRandomValues(b);
  return 'JP-' + [...b].map((n) => ID_ALPHA[n % ID_ALPHA.length]).join('');
}

// 동의서 버전. 문구가 바뀌면 올린다 — 누가 어느 버전에 동의했는지 남겨야
// 나중에 재동의를 받아야 하는지 판단할 수 있다.
const CONSENT_VER = '2026-08-11';
const MAX_CHILDREN = 3;

// 이메일은 형식만 가볍게 본다. 진짜 확인은 나중에 인증 메일로 한다.
const isEmail = (s) => typeof s === 'string' && s.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s);

// 아이 비밀번호 검사 — 부모 것보다 훨씬 느슨하다.
// 부모 비밀번호는 결제 정보를 지키는 열쇠라 8자 이상에 뻔한 것도 막지만,
// 아이 비밀번호가 지키는 건 자기 학습 기록뿐이다. 아홉 살이 매일 칠 수 있어야 하므로
// 네 글자 이상이면 통과시킨다. 어렵게 만들면 부모가 대신 외워주다가 결국 부모 것을 쓴다.
const CHILD_PW_MIN = 4;
function childPwReason(pw) {
  const s = String(pw ?? '');
  if (s.length < CHILD_PW_MIN) return `아이 비밀번호는 ${CHILD_PW_MIN}자 이상으로 해주세요`;
  if (s.length > 100) return '아이 비밀번호가 너무 깁니다';
  if (/\s/.test(s)) return '아이 비밀번호에 공백은 쓸 수 없어요';
  return null;
}

// 새 아이 계정 한 명을 만든다. 로그인ID가 겹치면 몇 번 다시 뽑는다.
async function createChild(db, { parentId, name, password, grade }) {
  for (let attempt = 0; attempt < 5; attempt++) {
    const loginId = makeChildLoginId();
    const dup = await db.prepare('SELECT 1 FROM users WHERE login_id = ?1').bind(loginId).first();
    if (dup) continue;
    const id = crypto.randomUUID();
    // 부모가 정해 준 아이 비밀번호가 여기 들어간다. 부모 것과 같은 이메일을 쓰되
    // 비밀번호만 다르므로, 아이는 부모 비밀번호를 알 필요가 없다(결제 화면도 못 연다).
    await db.prepare(
      `INSERT INTO users (id, role, login_id, pin_hash, display_name, created_at, parent_id)
       VALUES (?1, 'student', ?2, ?3, ?4, ?5, ?6)`
    ).bind(id, loginId, await hashPin(password), name, nowISO(), parentId).run();
    return { id, login_id: loginId, display_name: name, grade: grade ?? null };
  }
  return null;
}

// 이 가족의 아이 목록 (등록 순)
const childrenOf = async (db, parentId) => (await db.prepare(
  `SELECT id, display_name, created_at FROM users
    WHERE parent_id = ?1 AND role = 'student' ORDER BY created_at`
).bind(parentId).all()).results;

app.post('/api/parent/signup', async (c) => {
  const b = await c.req.json().catch(() => ({}));
  const email = String(b.email ?? '').trim().toLowerCase();
  const password = String(b.password ?? '');
  const name = clean(b.name, 12);
  const childName = clean(b.child_name, 12);
  const childPw = String(b.child_password ?? '');

  if (!isEmail(email)) return c.json({ error: '이메일 주소를 확인해주세요' }, 400);
  const weak = weakSecretReason(password, email.split('@')[0]);
  if (weak) return c.json({ error: weak }, 400);
  if (!name) return c.json({ error: '보호자 이름을 입력해주세요' }, 400);
  if (!childName) return c.json({ error: '아이 이름을 입력해주세요' }, 400);
  const childBad = childPwReason(childPw);
  if (childBad) return c.json({ error: childBad }, 400);
  // 아이 비밀번호를 부모 것과 똑같이 두면 아이가 결제 화면까지 열 수 있다 — 그럴 거면
  // 따로 정하는 의미가 없으므로 여기서 막는다.
  if (childPw === password) return c.json({ error: '아이 비밀번호는 보호자 것과 다르게 정해주세요' }, 400);
  // 만 14세 미만 아이의 계정을 만드는 절차라, 동의 없이는 한 걸음도 나갈 수 없다.
  if (b.consent !== true) return c.json({ error: '보호자 동의가 필요합니다' }, 400);

  const dup = await c.env.DB.prepare('SELECT 1 FROM parents WHERE email = ?1').bind(email).first();
  if (dup) return c.json({ error: '이미 가입된 이메일이에요. 로그인해주세요' }, 409);

  const parent = {
    id: crypto.randomUUID(),
    email,
    password_hash: await hashSecret(password),
    display_name: name,
  };
  const now = nowISO();
  await c.env.DB.prepare(
    `INSERT INTO parents (id, email, password_hash, display_name, consent_at, consent_ver, created_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?5)`
  ).bind(parent.id, email, parent.password_hash, name, now, CONSENT_VER).run();

  const child = await createChild(c.env.DB, {
    parentId: parent.id, name: childName, password: childPw, grade: b.grade });
  if (!child) return c.json({ error: '아이를 등록하지 못했어요. 다시 시도해주세요' }, 500);

  return c.json({
    token: await makeAccountToken(parent),
    parent: { email, display_name: name },
    child,
  });
});

app.post('/api/parent/login-email', async (c) => {
  const b = await c.req.json().catch(() => ({}));
  const email = String(b.email ?? '').trim().toLowerCase();
  const password = String(b.password ?? '');
  if (!isEmail(email) || !password) return c.json({ error: '이메일과 비밀번호를 확인해주세요' }, 400);

  // 잠금 열쇠는 이메일 기준. 아이 로그인·학원 발급 학부모 PIN과 서로 옮겨붙지 않게 접두어를 다르게 둔다.
  const key = `PE:${email}`;
  const lockLeft = await loginLockedFor(c.env.DB, key);
  if (lockLeft > 0) {
    return c.json({ error: `여러 번 틀려서 잠겼어요. ${Math.ceil(lockLeft / 60)}분 뒤에 다시 해주세요` }, 429);
  }

  const parent = await c.env.DB.prepare('SELECT * FROM parents WHERE email = ?1').bind(email).first();
  // 가입 안 된 이메일과 비밀번호가 틀린 경우를 똑같이 답한다(어느 이메일이 가입돼 있는지 흘리지 않는다)
  if (!parent || !(await verifySecret(password, parent.password_hash))) {
    const { lockedSeconds } = await noteLoginFail(c.env.DB, key);
    return c.json({
      error: lockedSeconds
        ? `여러 번 틀려서 ${Math.ceil(lockedSeconds / 60)}분 동안 잠겼어요`
        : '이메일 또는 비밀번호가 맞지 않아요',
    }, lockedSeconds ? 429 : 401);
  }
  await clearLoginFails(c.env.DB, key);
  return c.json({
    token: await makeAccountToken(parent),
    parent: { email: parent.email, display_name: parent.display_name },
  });
});

// ── 아이 앱 로그인 ──
// 이메일은 **부모 것 하나**를 온 가족이 같이 쓰고, **비밀번호만 사람마다 다르다.**
// 부모가 가입할 때 아이 비밀번호까지 직접 정해 주므로 옮겨 적어 보낼 것이 없고,
// 아이는 부모 비밀번호를 모른다(= 나중에 붙을 결제 화면을 열 수 없다).
//
// 비밀번호가 곧 '누구인지'라서 형제가 있어도 고르는 화면이 뜨지 않는다.
// 다만 부모가 두 아이에게 같은 비밀번호를 준 경우만 누구인지 물어본다.
app.post('/api/family/login', async (c) => {
  const b = await c.req.json().catch(() => ({}));
  const email = String(b.email ?? '').trim().toLowerCase();
  const password = String(b.password ?? '');
  if (!isEmail(email) || !password) return c.json({ error: '이메일과 비밀번호를 확인해주세요' }, 400);

  // 잠금은 아이 앱 전용으로 따로 센다. 부모 로그인과 같은 열쇠로 세면
  // 아이가 비밀번호를 여러 번 틀렸을 때 부모까지 못 들어간다.
  const key = `FC:${email}`;
  const lockLeft = await loginLockedFor(c.env.DB, key);
  if (lockLeft > 0) {
    return c.json({ error: `여러 번 틀려서 잠겼어요. ${Math.ceil(lockLeft / 60)}분 뒤에 다시 해주세요` }, 429);
  }

  const fail = async () => {
    const { lockedSeconds } = await noteLoginFail(c.env.DB, key);
    return c.json({
      error: lockedSeconds
        ? `여러 번 틀려서 ${Math.ceil(lockedSeconds / 60)}분 동안 잠겼어요`
        : '이메일 또는 비밀번호가 맞지 않아요',
    }, lockedSeconds ? 429 : 401);
  };

  const parent = await c.env.DB.prepare('SELECT id FROM parents WHERE email = ?1').bind(email).first();
  if (!parent) return fail();

  const { results: kids } = await c.env.DB.prepare(
    `SELECT * FROM users WHERE parent_id = ?1 AND role = 'student' ORDER BY created_at`
  ).bind(parent.id).all();

  // 비밀번호가 맞는 아이를 찾는다. 아이마다 다르게 정했다면 한 명만 걸린다.
  const matched = [];
  for (const k of kids) if (await verifyPin(password, k.pin_hash)) matched.push(k);
  if (!matched.length) return fail();
  await clearLoginFails(c.env.DB, key);

  const pickedId = clean(b.child_id, 40);
  const user = pickedId
    ? matched.find((k) => k.id === pickedId)
    : (matched.length === 1 ? matched[0] : null);
  if (!user) {
    return c.json({ choose: true, children: matched.map((k) => ({ id: k.id, display_name: k.display_name })) });
  }
  return c.json({
    token: await makeToken(user),
    user: { id: user.id, login_id: user.login_id, display_name: user.display_name, role: user.role },
  });
});

// 내 아이 목록. 아이가 없어도 200으로 빈 목록을 준다(가입 직후 화면이 여기서 시작한다).
app.get('/api/parent/children', requireParentAccount, async (c) => {
  const parent = c.get('parent');
  const children = await childrenOf(c.env.DB, parent.id);
  return c.json({ parent: { email: parent.email, display_name: parent.display_name }, children });
});

app.post('/api/parent/children', requireParentAccount, async (c) => {
  const parent = c.get('parent');
  const b = await c.req.json().catch(() => ({}));
  const name = clean(b.name, 12);
  const password = String(b.password ?? '');
  if (!name) return c.json({ error: '아이 이름을 입력해주세요' }, 400);
  const bad = childPwReason(password);
  if (bad) return c.json({ error: bad }, 400);

  const { n } = await c.env.DB.prepare(
    `SELECT COUNT(*) AS n FROM users WHERE parent_id = ?1 AND role = 'student'`
  ).bind(parent.id).first();
  if (n >= MAX_CHILDREN) return c.json({ error: `아이는 ${MAX_CHILDREN}명까지 등록할 수 있어요` }, 400);

  const child = await createChild(c.env.DB, { parentId: parent.id, name, password, grade: b.grade });
  if (!child) return c.json({ error: '아이를 등록하지 못했어요. 다시 시도해주세요' }, 500);
  return c.json({ child });
});

// 아이가 자기 비밀번호를 잊었을 때 부모가 새로 정해 준다.
app.post('/api/parent/children/:id/password', requireParentAccount, async (c) => {
  const parent = c.get('parent');
  const b = await c.req.json().catch(() => ({}));
  const password = String(b.password ?? '');
  const bad = childPwReason(password);
  if (bad) return c.json({ error: bad }, 400);
  if (await verifySecret(password, parent.password_hash)) {
    return c.json({ error: '아이 비밀번호는 보호자 것과 다르게 정해주세요' }, 400);
  }

  const child = await c.env.DB.prepare(
    `SELECT id, login_id, display_name FROM users WHERE id = ?1 AND parent_id = ?2 AND role = 'student'`
  ).bind(c.req.param('id'), parent.id).first();
  if (!child) return c.json({ error: '아이를 찾을 수 없습니다' }, 404);

  await c.env.DB.prepare('UPDATE users SET pin_hash = ?2 WHERE id = ?1')
    .bind(child.id, await hashPin(password)).run();
  // 비밀번호가 바뀌면 그 아이의 기존 토큰은 전부 무효가 된다(토큰 서명 열쇠가 pin_hash라서)
  await clearLoginFails(c.env.DB, `FC:${parent.email}`);
  return c.json({ child: { id: child.id, display_name: child.display_name } });
});

// 자녀 한 명의 요약. 부모는 이것만 본다 — 정답·해설·문항 원문은 내려주지 않는다.
app.get('/api/parent/overview', requireParent, async (c) => {
  const child = c.get('child');
  const today = kstDate();
  const [stats, { results: parts }, { results: days }, sm, klass] = await Promise.all([
    c.env.DB.prepare(
      `SELECT COUNT(*) AS answered, COALESCE(SUM(is_correct), 0) AS correct
         FROM answers WHERE user_id = ?1`
    ).bind(child.id).first(),
    c.env.DB.prepare(
      `SELECT q.part, COUNT(*) AS answered, COALESCE(SUM(a.is_correct), 0) AS correct
         FROM answers a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ?1 GROUP BY q.part`
    ).bind(child.id).all(),
    c.env.DB.prepare(
      `SELECT date(answered_at, '+9 hours') AS d, COUNT(*) AS n FROM answers
        WHERE user_id = ?1 GROUP BY d ORDER BY d DESC LIMIT 21`
    ).bind(child.id).all(),
    computeSkillMap(c.env.DB, child, today),
    c.env.DB.prepare('SELECT name, grade, set_size FROM classes WHERE id = ?1').bind(child.class_id).first(),
  ]);

  // 이어온 날(연속) — 오늘 아직 안 했으면 어제부터 센다
  const dayset = new Set(days.map((r) => r.d));
  let streak = 0;
  const cur = new Date(`${today}T00:00:00Z`);
  if (!dayset.has(today)) cur.setUTCDate(cur.getUTCDate() - 1);
  while (dayset.has(cur.toISOString().slice(0, 10))) { streak += 1; cur.setUTCDate(cur.getUTCDate() - 1); }

  // 직접 가입한 학부모는 아이가 여럿일 수 있다 — 화면에서 바꿔 볼 수 있게 목록을 함께 준다.
  // 학원 발급 토큰은 아이 하나에 묶여 있어 목록이 없다(null).
  const parent = c.get('parent');
  const siblings = parent
    ? (await c.env.DB.prepare(
        `SELECT id, display_name FROM users WHERE parent_id = ?1 AND role = 'student' ORDER BY created_at`
      ).bind(parent.id).all()).results
    : null;

  return c.json({
    child: { id: child.id, display_name: child.display_name, login_id: child.login_id },
    children: siblings,
    parent: parent ? { email: parent.email, display_name: parent.display_name } : null,
    class: klass ?? null,
    // 오늘 날짜를 서버가 알려준다 — 화면이 기기 시계로 따로 계산하면 한국이 아닌 곳에서
    // 보거나 자정~오전 9시 사이에 볼 때 하루가 어긋난다(서버는 한국 시간 기준).
    today,
    today_n: days.find((r) => r.d === today)?.n ?? 0,
    recent_days: days.slice(0, 14).reverse(),   // 최근 2주, 오래된 날부터
    streak,
    answered: stats.answered,
    correct: stats.correct,
    parts: Object.fromEntries(parts.map((p) => [p.part, { answered: p.answered, correct: p.correct }])),
    axes: sm.axes, misses: sm.misses, revive: sm.revive, speed: sm.speed,
  });
});

app.post('/api/setup/admin', async (c) => {
  if (await superCount(c.env.DB)) {
    return c.json({ error: '이미 관리자가 있습니다. 관리자 화면에서 로그인하세요.' }, 403);
  }
  const body = await c.req.json().catch(() => ({}));
  const loginId = clean(body.login_id, 32).toUpperCase();
  const secret = String(body.secret ?? '');
  if (!/^[A-Z0-9-]{2,32}$/.test(loginId)) {
    return c.json({ error: '아이디는 영문·숫자 2~32자입니다 (예: ADMIN)' }, 400);
  }
  // 새로 정하는 자리이므로 길이뿐 아니라 '뻔한 비밀번호'인지도 본다.
  // 8자는 짧아서, admin1234 같은 걸 쓰면 DB가 유출됐을 때 금방 깨진다.
  const weak = weakSecretReason(secret, loginId);
  if (weak) return c.json({ error: weak }, 400);
  const taken = await c.env.DB.prepare('SELECT 1 FROM users WHERE login_id = ?1').bind(loginId).first();
  if (taken) return c.json({ error: '이미 쓰고 있는 아이디입니다' }, 409);

  const id = crypto.randomUUID();
  // 여기서도 한 번 더 확인한다 — 두 사람이 동시에 눌렀을 때 둘 다 통과하면 안 된다.
  // D1은 트랜잭션 격리가 약해서, 조건부 INSERT 로 DB가 직접 막게 한다.
  const r = await c.env.DB.prepare(
    `INSERT INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at)
     SELECT ?1, 'super', ?2, ?3, '관리자', NULL, NULL, ?4
      WHERE NOT EXISTS (SELECT 1 FROM users WHERE role = 'super')`
  ).bind(id, loginId, await hashPin(secret), nowISO()).run();
  if (!r.meta?.changes) {
    return c.json({ error: '이미 관리자가 있습니다. 관리자 화면에서 로그인하세요.' }, 403);
  }
  const user = await c.env.DB.prepare('SELECT * FROM users WHERE id = ?1').bind(id).first();
  return c.json({
    token: await makeToken(user),
    user: { id: user.id, login_id: user.login_id, display_name: user.display_name, role: user.role },
  });
});
const nowISO = () => new Date().toISOString();
const clean = (s, max) => String(s ?? '').trim().slice(0, max);

// 한눈에 보는 현황 — 고객은 가족이다(2026-08-11 B2C 전환).
// 관리자 화면은 '읽기 전용'이다: 가족이 얼마나 들어와서 얼마나 쓰는지만 본다.
// 계정 발급·비밀번호 재설정은 관리자가 못 한다 — 가입은 학부모가 직접 하고,
// 아이 비밀번호는 학부모 화면에서 학부모가 바꾼다. 관리자가 남의 가족 비밀번호를
// 만들 수 있으면 그게 곧 사고 경로가 된다.
//
// ⚠ 학원 관리(학원·반·학생 발급·PIN 재발급) 엔드포인트는 지웠다(2026-08-12).
// 학원 영업을 접으면서 학생 앱에서 아이디·PIN 로그인 자체가 사라졌으므로,
// 관리자가 발급한 PIN은 들어갈 문이 없는 열쇠였다. academies·classes 표는
// 시뮬레이션·시드(tools/)용 내부 도구로만 남는다.
app.get('/api/admin/overview', ...admin, async (c) => {
  const [{ results: parents }, { results: kids }, pending] = await Promise.all([
    c.env.DB.prepare(
      `SELECT id, email, display_name, consent_at, created_at FROM parents ORDER BY created_at DESC LIMIT 500`
    ).all(),
    c.env.DB.prepare(
      `SELECT u.id, u.parent_id, u.display_name, u.created_at,
              (SELECT COUNT(*) FROM answers WHERE user_id = u.id) AS answers,
              (SELECT MAX(date(answered_at, '+9 hours')) FROM answers WHERE user_id = u.id) AS last_day
         FROM users u WHERE u.parent_id IS NOT NULL AND u.role = 'student'`
    ).all(),
    c.env.DB.prepare('SELECT COUNT(*) AS n FROM feedback WHERE handled_at IS NULL').first(),
  ]);
  const byParent = {};
  for (const k of kids) (byParent[k.parent_id] ||= []).push(k);
  const families = parents.map((p) => ({
    id: p.id, email: p.email, display_name: p.display_name,
    joined: p.created_at, children: byParent[p.id] ?? [],
  }));
  const today = kstDate();
  return c.json({
    families,
    stats: {
      families: parents.length,
      children: kids.length,
      answers: kids.reduce((n, k) => n + k.answers, 0),
      active_today: kids.filter((k) => k.last_day === today).length,
    },
    today,
    feedback_pending: pending.n,
  });
});

// 신고 목록 — 아이가 어느 문항에서 막혔는지. 기본은 아직 안 본 것만.
app.get('/api/admin/feedback', ...admin, async (c) => {
  const all = c.req.query('all') === '1';
  const { results } = await c.env.DB.prepare(
    `SELECT f.id, f.kind, f.note, f.screen, f.created_at, f.handled_at,
            f.question_id, q.part, q.stem, u.login_id, u.display_name
       FROM feedback f
       LEFT JOIN questions q ON q.id = f.question_id
       LEFT JOIN users u ON u.id = f.user_id
      ${all ? '' : 'WHERE f.handled_at IS NULL'}
      ORDER BY f.created_at DESC LIMIT 200`
  ).all();
  return c.json({ feedback: results });
});

app.post('/api/admin/feedback/:id/handled', ...admin, async (c) => {
  const done = (await c.req.json().catch(() => ({})))?.done !== false;
  const r = await c.env.DB.prepare('UPDATE feedback SET handled_at = ?2, handled_by = ?3 WHERE id = ?1')
    .bind(c.req.param('id'), done ? nowISO() : null, done ? c.get('user').id : null).run();
  if (!r.meta?.changes) return c.json({ error: '신고를 찾을 수 없습니다' }, 404);
  return c.json({ ok: true, handled: done });
});

app.get('/api/health', async (c) => {
  const counts = await c.env.DB.prepare(
    `SELECT
       (SELECT COUNT(*) FROM questions)                          AS questions,
       (SELECT COUNT(*) FROM questions WHERE status = 'active')  AS active_questions,
       (SELECT COUNT(*) FROM passages)                           AS passages,
       (SELECT COUNT(*) FROM concept_tags)                       AS tags,
       (SELECT COUNT(*) FROM badges)                             AS badges`
  ).first();
  return c.json({ ok: true, service: 'jumplish', phase: 'M1', counts });
});

app.get('/api/parts', async (c) => {
  const { results } = await c.env.DB.prepare(
    `SELECT part, section,
            COUNT(*)                                            AS total,
            SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END)  AS active,
            SUM(CASE WHEN audio_url IS NOT NULL THEN 1 ELSE 0 END) AS with_audio
       FROM questions
      GROUP BY part, section
      ORDER BY part`
  ).all();
  return c.json({ parts: results });
});

// 문항 열람 (M1: 검수·풀어보기용) — 정답·해설 미포함
app.get('/api/questions', async (c) => {
  const part = c.req.query('part') || '';
  if (!PART_RE.test(part)) {
    return c.json({ error: 'part 파라미터가 필요합니다 (L1~L4, R1~R3)' }, 400);
  }
  const limit = Math.min(parseInt(c.req.query('limit') || '60', 10) || 60, 100);

  const { results: rows } = await c.env.DB.prepare(
    // script는 M1 검수 화면의 "음원 준비 전 스크립트 열람"용 — M2 학생용 API에서는 제외한다
    `SELECT id, passage_id, section, part, stem, choices, difficulty_label,
            audio_url, image_url, accent, script, status
       FROM questions
      WHERE part = ?1 AND status IN ('active', 'draft')
      ORDER BY id
      LIMIT ?2`
  ).bind(part, limit).all();

  const passageIds = [...new Set(rows.map((q) => q.passage_id).filter(Boolean))];
  const passages = {};
  if (passageIds.length > 0) {
    const marks = passageIds.map((_, i) => `?${i + 1}`).join(',');
    const { results } = await c.env.DB.prepare(
      // content(지문/스크립트)는 독해 지문 표시 + 음원 준비 전 열람 대체용
      `SELECT id, kind, content, image_url, audio_url, accent
         FROM passages WHERE id IN (${marks})`
    ).bind(...passageIds).all();
    for (const p of results) passages[p.id] = p;
  }

  const questions = rows.map((q) => ({ ...q, choices: JSON.parse(q.choices) }));
  return c.json({ part, count: questions.length, questions, passages });
});

// 오늘의 맞춤 학습 세트 (M1: 로그인 전이라 약점은 클라이언트가 보관한 기록으로 계산해 넘긴다.
// M2에서 계정이 붙으면 서버의 user_skills·SRS 큐로 옮긴다 — docs/engine.md)
//   weak=L4,R3   약한 파트(가중치 +1)
//   exclude=id,id 최근에 맞힌 문항(다시 내보내지 않음)
const SET_COMPOSITION = { L1: 1, L2: 2, L3: 1, L4: 2, R1: 2, R2: 2, R3: 2 }; // 합 12 — 실제 시험 파트 비율 반영

app.get('/api/today', async (c) => {
  // 로그인 학생: 서버가 복습+약점+신규+유지 슬롯으로 세트를 만든다 (하루 1세트 고정 저장)
  const m = /^Bearer\s+(.+)$/.exec(c.req.header('Authorization') || '');
  const user = m ? await verifyToken(c.env.DB, m[1]) : null;
  if (user) {
    const today = kstDate();
    let set = await c.env.DB.prepare(
      'SELECT question_ids, slots FROM daily_sets WHERE user_id = ?1 AND date = ?2'
    ).bind(user.id, today).first();
    if (!set) {
      const made = await composeDailySet(c.env.DB, user, today);
      set = { question_ids: JSON.stringify(made.ids), slots: JSON.stringify(made.slots) };
      await c.env.DB.prepare(
        `INSERT INTO daily_sets (id, user_id, date, question_ids, slots, generated_at)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6)
         ON CONFLICT(user_id, date) DO NOTHING`
      ).bind(crypto.randomUUID(), user.id, today, set.question_ids, set.slots, new Date().toISOString()).run();
    }
    const ids = JSON.parse(set.question_ids);
    const { questions, passages } = await hydrate(c.env.DB, ids);
    return c.json({ count: questions.length, plan: JSON.parse(set.slots), personalized: true, questions, passages });
  }

  const weak = (c.req.query('weak') || '').split(',').filter((p) => PART_RE.test(p));
  const exclude = (c.req.query('exclude') || '').split(',').filter(Boolean).slice(0, 200);

  // 약한 파트는 한 문항 더, 대신 가장 쉬운 파트에서 한 문항 뺀다 (총량 유지)
  const plan = { ...SET_COMPOSITION };
  const strong = (c.req.query('strong') || '').split(',').filter((p) => PART_RE.test(p));
  weak.slice(0, 2).forEach((p, i) => {
    plan[p] += 1;
    const donor = strong[i];
    if (donor && plan[donor] > 1) plan[donor] -= 1;
  });

  const marks = exclude.map((_, i) => `?${i + 3}`).join(',');
  const draw = async (part, n, seen) => {
    if (n < 1) return [];
    const { results } = await c.env.DB.prepare(
      `SELECT id, passage_id, section, part, stem, choices, difficulty_label,
              audio_url, image_url, accent
         FROM questions
        WHERE part = ?1 AND status = 'active'
              ${exclude.length ? `AND id NOT IN (${marks})` : ''}
        ORDER BY RANDOM() LIMIT ?2`
    ).bind(part, n + seen.size, ...exclude).all();
    return results.filter((q) => !seen.has(q.id)).slice(0, n);
  };

  const picked = [];
  const seen = new Set();
  const target = Object.values(plan).reduce((a, b) => a + b, 0);
  for (const [part, n] of Object.entries(plan)) {
    const got = await draw(part, n, seen);
    got.forEach((q) => seen.add(q.id));
    picked.push(...got);
    plan[part] = got.length; // 실제로 담은 수 (L1처럼 초안뿐인 파트는 0이 된다)
  }
  // 문항이 없는 파트(그림 준비 중인 L1 등) 때문에 세트가 비면 다른 파트로 채운다
  for (const part of Object.keys(SET_COMPOSITION)) {
    if (picked.length >= target) break;
    const got = await draw(part, target - picked.length, seen);
    got.forEach((q) => seen.add(q.id));
    picked.push(...got);
    plan[part] += got.length;
  }
  // 실제 시험 순서(듣기 → 읽기, 파트 오름차순)로 정렬
  picked.sort((a, b) => a.part.localeCompare(b.part));

  const passageIds = [...new Set(picked.map((q) => q.passage_id).filter(Boolean))];
  const passages = {};
  if (passageIds.length > 0) {
    const marks = passageIds.map((_, i) => `?${i + 1}`).join(',');
    const { results } = await c.env.DB.prepare(
      `SELECT id, kind, content, image_url, audio_url, accent FROM passages WHERE id IN (${marks})`
    ).bind(...passageIds).all();
    for (const p of results) passages[p.id] = p;
  }

  return c.json({
    count: picked.length,
    plan,
    questions: picked.map((q) => ({ ...q, choices: JSON.parse(q.choices) })),
    passages,
  });
});

// 간이 채점 (M1 전용 — M2에서 세션 기반 POST /api/answers 로 대체 예정)
app.post('/api/check', async (c) => {
  const body = await c.req.json().catch(() => ({}));
  const { question_id, chosen_idx } = body;
  if (typeof question_id !== 'string' || !Number.isInteger(chosen_idx)) {
    return c.json({ error: 'question_id(문자열), chosen_idx(정수)가 필요합니다' }, 400);
  }
  const q = await c.env.DB.prepare(
    'SELECT id, passage_id, stem, script, evidence, why_not, miss_type, key_expr, answer_idx, explanation_ko FROM questions WHERE id = ?1'
  ).bind(question_id).first();
  if (!q) return c.json({ error: '문항을 찾을 수 없습니다' }, 404);

  const correct = chosen_idx === q.answer_idx;
  await c.env.DB.prepare(
    'UPDATE questions SET times_answered = times_answered + 1, times_correct = times_correct + ?1 WHERE id = ?2'
  ).bind(correct ? 1 : 0, q.id).run();

  return c.json({
    correct, answer_idx: q.answer_idx, explanation_ko: q.explanation_ko,
    ...(await feedbackOf(c.env.DB, q, chosen_idx)),
  });
});

app.notFound((c) => {
  if (new URL(c.req.url).pathname.startsWith('/api/')) {
    return c.json({ error: '없는 API 경로입니다' }, 404);
  }
  // 정적 자산은 [assets] 바인딩이 워커보다 먼저 서빙하므로 여기 오면 404가 맞다
  return c.text('Not Found', 404);
});

export default app;
