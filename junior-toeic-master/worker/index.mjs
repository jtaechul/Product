// 점프리시(Jumplish) API Worker — Hono
// 절대 규칙: 문항을 내려주는 어떤 응답에도 answer_idx·explanation_ko를 포함하지 않는다.
// 채점 엔드포인트만 정답에 접근한다. (docs/engine.md · PRD 6절)
import { Hono } from 'hono';

const app = new Hono();

const PART_RE = /^(L[1-4]|R[1-3])$/;

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
