// 점프리시(Jumplish) API Worker — Hono
// 절대 규칙: 문항을 내려주는 어떤 응답에도 answer_idx·explanation_ko를 포함하지 않는다.
// 채점 엔드포인트만 정답에 접근한다. (docs/engine.md · PRD 6절)
import { Hono } from 'hono';
import { verifyPin, makeToken, requireAuth, verifyToken } from './auth.mjs';
import { recordAnswer, composeDailySet, computeClimb, kstDate, DIAG, diagBand, pickDiagQuestions } from './engine.mjs';

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
  const { results: tags } = await db.prepare(
    'SELECT tag_id FROM question_tags WHERE question_id = ?1'
  ).bind(q.id).all();
  const codes = tags.map((t) => t.tag_id);
  return {
    ...(await evidenceOf(db, q)),
    why_not: (why && chosenIdx !== q.answer_idx) ? (why[String(chosenIdx)] ?? null) : null,
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
  if (typeof login_id !== 'string' || !/^\d{6}$/.test(String(pin))) {
    return c.json({ error: '로그인ID와 6자리 PIN을 입력하세요' }, 400);
  }
  const user = await c.env.DB.prepare(
    'SELECT * FROM users WHERE login_id = ?1'
  ).bind(login_id.trim().toUpperCase()).first();
  // 계정 존재 여부를 구분해 알려주지 않는다 (계정 추측 방지)
  if (!user || !(await verifyPin(String(pin), user.pin_hash))) {
    return c.json({ error: '로그인ID 또는 PIN이 맞지 않아요' }, 401);
  }
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
  const [{ results: seq }, best, today] = await Promise.all([
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
  ]);
  // 최장 연속 정답 + 지금 이어지는 연속 (최근 답부터 뒤로)
  let bestRun = 0, run = 0;
  for (const r of seq) { run = r.is_correct ? run + 1 : 0; if (run > bestRun) bestRun = run; }
  let currentRun = 0;
  for (let i = seq.length - 1; i >= 0 && seq[i].is_correct; i--) currentRun++;
  return c.json({
    best_run: bestRun, current_run: currentRun,
    best_day: best ? { date: best.d, n: best.n } : null,
    today_n: today.n,
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
    'SELECT id, passage_id, stem, script, evidence, why_not, key_expr, answer_idx, explanation_ko, rating FROM questions WHERE id = ?1'
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
    'SELECT id, passage_id, stem, script, evidence, why_not, key_expr, answer_idx, explanation_ko FROM questions WHERE id = ?1'
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
