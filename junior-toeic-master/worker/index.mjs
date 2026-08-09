// 점프리시(Jumplish) API Worker — Hono
// 절대 규칙: 문항을 내려주는 어떤 응답에도 answer_idx·explanation_ko를 포함하지 않는다.
// 채점 엔드포인트만 정답에 접근한다. (docs/engine.md · PRD 6절)
import { Hono } from 'hono';
import { verifyPin, makeToken, requireAuth } from './auth.mjs';
import { recordAnswer, kstDate } from './engine.mjs';

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
  return c.json({
    user: { id: u.id, login_id: u.login_id, display_name: u.display_name, role: u.role },
    answered: stats.answered, correct: stats.correct, review_due: due.n,
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
    'SELECT id, answer_idx, explanation_ko, rating FROM questions WHERE id = ?1'
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

  const { correct } = await recordAnswer(c.env.DB, {
    user: u, question: q, chosenIdx: chosen_idx, timeMs: time_ms | 0, sessionId: session.id,
  });
  return c.json({ correct, answer_idx: q.answer_idx, explanation_ko: q.explanation_ko });
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
    'SELECT id, answer_idx, explanation_ko FROM questions WHERE id = ?1'
  ).bind(question_id).first();
  if (!q) return c.json({ error: '문항을 찾을 수 없습니다' }, 404);

  const correct = chosen_idx === q.answer_idx;
  await c.env.DB.prepare(
    'UPDATE questions SET times_answered = times_answered + 1, times_correct = times_correct + ?1 WHERE id = ?2'
  ).bind(correct ? 1 : 0, q.id).run();

  return c.json({ correct, answer_idx: q.answer_idx, explanation_ko: q.explanation_ko });
});

app.notFound((c) => {
  if (new URL(c.req.url).pathname.startsWith('/api/')) {
    return c.json({ error: '없는 API 경로입니다' }, 404);
  }
  // 정적 자산은 [assets] 바인딩이 워커보다 먼저 서빙하므로 여기 오면 404가 맞다
  return c.text('Not Found', 404);
});

export default app;
