// 점프리시 규칙 기반 엔진 — Elo-lite 실력 갱신 + 라이트너 SRS (docs/engine.md)
// 운영 중 외부 API 0회: 전부 결정적 수식이다.

export const ELO_SCALE = 400;
export const DEFAULT_RATING = 1200;          // 진단 전 태그 초기 레이팅 (라벨3 상당)
export const GUESS_MS = 2000;                // 이 시간 미만 정답은 '찍기' — 레이팅·진급 없음
export const SRS_INTERVALS = [1, 3, 7, 14];  // 라이트너 박스 1~4 재출제 간격(일)

// 신규 학생일수록 크게 움직인다 (engine.md K_SCHEDULE)
export const kFor = (attempts) => (attempts < 20 ? 32 : attempts < 50 ? 24 : 16);

// KST 기준 날짜 문자열 (YYYY-MM-DD). SRS due는 날짜 단위다.
export const kstDate = (ms = Date.now(), plusDays = 0) =>
  new Date(ms + 9 * 3600_000 + plusDays * 86400_000).toISOString().slice(0, 10);

// ── 진단 테스트 (engine.md 4절) ──
// 2단계 적응형: 1단계 섹션 정답률로 2단계 난이도를 정한다. 진단 중 Elo 갱신 없음,
// 종료 시 파트별 정확도 → 대역 → 초기 레이팅으로 결정적 매핑(강사에게 설명 가능).
export const DIAG = {
  // 파트 배분 [1단계, 2단계]
  basic: { L1: [1, 1], L2: [2, 2], L3: [2, 2], L4: [2, 2], R1: [2, 2], R2: [1, 1], R3: [2, 2] },
  junior: { L1: [1, 1], L2: [1, 2], L3: [1, 1], L4: [1, 1], R1: [1, 2], R2: [1, 0], R3: [2, 1] },
  stage1Label: { basic: 3, junior: 2 },
  // 1단계 섹션 정답률 → 2단계 라벨
  stage2Label: (group, acc) => (group === 'basic'
    ? (acc >= 2 / 3 ? 4 : acc <= 1 / 3 ? 2 : 3)
    : (acc >= 2 / 3 ? 3 : acc <= 1 / 3 ? 1 : 2)),
  bands: [[85, 5, 1450], [70, 4, 1325], [55, 3, 1200], [40, 2, 1075], [0, 1, 950]],
};
export const diagBand = (accPct) => DIAG.bands.find(([min]) => accPct >= min);

// 파트·라벨 조건으로 무작위 선정. 후보 부족 시 라벨 무시 → 같은 섹션으로 완화(빈 배분 방지).
export async function pickDiagQuestions(db, part, label, n, excludeIds) {
  if (n < 1) return [];
  const out = [];
  const tryPick = async (where, binds) => {
    const excl = [...excludeIds, ...out];
    const marks = excl.map((_, i) => `?${i + binds.length + 1}`).join(',');
    const { results } = await db.prepare(
      `SELECT id FROM questions WHERE status = 'active' AND ${where}
       ${excl.length ? `AND id NOT IN (${marks})` : ''} ORDER BY RANDOM() LIMIT ${n - out.length}`
    ).bind(...binds, ...excl).all();
    out.push(...results.map((r) => r.id));
  };
  await tryPick('part = ?1 AND difficulty_label = ?2', [part, label]);
  if (out.length < n) await tryPick('part = ?1', [part]);
  if (out.length < n) await tryPick('section = ?1', [part.startsWith('L') ? 'LC' : 'RC']);
  return out;
}

// ── 오늘의 학습 세트 생성 (engine.md 5절) ──
// 복습(SRS due) + 약점(p 0.55~0.75) + 신규(경험 적은 태그) + 유지(강점 p≥0.8).
// 문제 은행이 120문항 규모라 후보 전체를 메모리에 놓고 JS로 조합한다.
const P_WEAK = [0.55, 0.75];
const NO_REPEAT_DAYS = 14;
const slotsFor = (size) => (size <= 12
  ? { review: 4, weak: 5, fresh: 2, keep: 1 }
  : { review: 6, weak: 8, fresh: 4, keep: 2 });

export async function composeDailySet(db, user, today) {
  const setSize = (await db.prepare(
    'SELECT set_size FROM classes WHERE id = ?1'
  ).bind(user.class_id).first())?.set_size ?? 12;
  const slots = slotsFor(setSize);

  const [{ results: bank }, { results: qtags }, { results: skills }, { results: due }, { results: recent }] =
    await Promise.all([
      db.prepare(`SELECT id, part, rating, passage_id FROM questions WHERE status = 'active'`).all(),
      db.prepare('SELECT question_id, tag_id FROM question_tags').all(),
      db.prepare('SELECT tag_id, rating, attempts FROM user_tag_skills WHERE user_id = ?1').bind(user.id).all(),
      db.prepare(`SELECT question_id FROM review_queue
                   WHERE user_id = ?1 AND graduated_at IS NULL AND due_at <= ?2
                   ORDER BY due_at LIMIT ?3`).bind(user.id, today, slots.review).all(),
      db.prepare(`SELECT DISTINCT question_id FROM answers
                   WHERE user_id = ?1 AND answered_at >= ?2`)
        .bind(user.id, new Date(Date.now() - NO_REPEAT_DAYS * 86400_000).toISOString()).all(),
    ]);

  const tagsBy = {};
  for (const { question_id, tag_id } of qtags) (tagsBy[question_id] ||= []).push(tag_id);
  const skillBy = Object.fromEntries(skills.map((s) => [s.tag_id, s]));
  const recentSet = new Set(recent.map((r) => r.question_id));
  const picked = [];
  const pickedSet = new Set();
  const take = (q) => { picked.push(q.id); pickedSet.add(q.id); };

  // 예상 정답률: 문항 태그 중 가장 약한 태그 레이팅 기준 (약한 고리가 지배)
  const pOf = (q) => {
    const rs = (tagsBy[q.id] || []).map((t) => skillBy[t]?.rating ?? DEFAULT_RATING);
    const r = rs.length ? Math.min(...rs) : DEFAULT_RATING;
    return 1 / (1 + 10 ** ((q.rating - r) / ELO_SCALE));
  };
  const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

  // 1) 복습 (14일 제외 규칙의 예외)
  const bankBy = Object.fromEntries(bank.map((q) => [q.id, q]));
  for (const { question_id } of due) if (bankBy[question_id]) take(bankBy[question_id]);

  // 2~4) 후보 풀: 최근 노출·기선택 제외
  const pool = bank.filter((q) => !pickedSet.has(q.id) && !recentSet.has(q.id));
  const withP = shuffle(pool.map((q) => ({ q, p: pOf(q) })));

  for (const { q } of withP.filter((x) => x.p >= P_WEAK[0] && x.p <= P_WEAK[1]).slice(0, slots.weak)) take(q);
  // 신규: 경험(시도) 0인 태그를 가진 문항 — 쉬운(p 높은) 것부터
  const fresh = withP
    .filter((x) => !pickedSet.has(x.q.id) && (tagsBy[x.q.id] || []).some((t) => (skillBy[t]?.attempts ?? 0) < 3))
    .sort((a, b) => b.p - a.p);
  for (const { q } of fresh.slice(0, slots.fresh)) take(q);
  for (const { q } of withP.filter((x) => !pickedSet.has(x.q.id) && x.p >= 0.8).slice(0, slots.keep)) take(q);
  // 부족분: 아무 후보로든 채운다 (빈 세트 금지)
  for (const { q } of withP) {
    if (picked.length >= setSize) break;
    if (!pickedSet.has(q.id)) take(q);
  }
  return { ids: picked, slots, setSize };
}

// ── 등반 지도 (M3-2, 게임화 '점프 원정대') ──
// 고도는 전부 결정적 수식 — 강사·학부모에게 그대로 설명 가능.
//   학습 계단  = 학습한 날 수 × 10        (꾸준함)
//   실력 계단  = max(0, (평균 레이팅 − 950) / 2)  (진단 하한 950 기준, 실력 성장분)
//   봉인 계단  = 봉인한 문제 × 5          (약점 극복)
// 베이스캠프 = 지금까지 도달한 최고 고도(user_stats.xp에 고수위 저장) —
// 레이팅이 내려가도 베이스캠프 아래로는 떨어지지 않는다(좌절 방지).
// 캠프는 100계단마다 하나(user_stats.level = 캠프 번호).
export async function computeClimb(db, user) {
  const [days, skill, sealed] = await Promise.all([
    db.prepare(`SELECT COUNT(DISTINCT date(answered_at, '+9 hours')) AS n FROM answers WHERE user_id = ?1`)
      .bind(user.id).first(),
    db.prepare('SELECT AVG(rating) AS r, COUNT(*) AS n FROM user_tag_skills WHERE user_id = ?1')
      .bind(user.id).first(),
    db.prepare('SELECT COUNT(*) AS n FROM review_queue WHERE user_id = ?1 AND graduated_at IS NOT NULL')
      .bind(user.id).first(),
  ]);
  const daySteps = days.n * 10;
  const skillSteps = skill.n ? Math.max(0, Math.round((skill.r - 950) / 2)) : 0;
  const sealSteps = sealed.n * 5;
  const altitude = daySteps + skillSteps + sealSteps;

  // 고수위(베이스캠프) 갱신 — 읽는 시점에 올려 둔다 (내려가는 일은 없음)
  const camp = Math.floor(altitude / 100) + 1;
  await db.prepare(
    `INSERT INTO user_stats (user_id, xp, level) VALUES (?1, ?2, ?3)
     ON CONFLICT(user_id) DO UPDATE SET xp = MAX(xp, ?2), level = MAX(level, ?3)`
  ).bind(user.id, altitude, camp).run();
  const row = await db.prepare('SELECT xp, level FROM user_stats WHERE user_id = ?1').bind(user.id).first();
  const basecamp = Math.max(row?.xp ?? 0, altitude);

  // 점프 점수(0~100): 자체 브랜드 점수. 평균 레이팅 900~1500을 0~100으로 환산한다.
  // TOEIC 공식 점수 예측이 아니므로 상표·과장광고 소지가 없고, 아이에게는 큰 숫자
  // 하나가 정답률 %보다 직관적이다. 진단 전(표본 0)에는 null.
  const jumpScore = skill.n
    ? Math.max(0, Math.min(100, Math.round(((skill.r - 900) / 600) * 100)))
    : null;

  return {
    altitude, basecamp, jump_score: jumpScore,
    camp: Math.floor(basecamp / 100) + 1,
    next_camp_at: (Math.floor(basecamp / 100) + 1) * 100,
    breakdown: { days: days.n, day_steps: daySteps, skill_steps: skillSteps, sealed: sealed.n, seal_steps: sealSteps },
  };
}

// 채점 결과 하나를 학습 기록에 반영한다.
// answers INSERT + user_tag_skills(Elo) UPSERT + review_queue(라이트너) UPSERT.
// D1 batch(단일 트랜잭션)로 묶어 부분 반영을 막는다.
export async function recordAnswer(db, { user, question, chosenIdx, timeMs, sessionId }) {
  const correct = chosenIdx === question.answer_idx;
  const guess = correct && timeMs > 0 && timeMs < GUESS_MS;
  const now = new Date().toISOString();
  const stmts = [];

  stmts.push(db.prepare(
    `INSERT INTO answers (id, session_id, user_id, question_id, chosen_idx, is_correct, time_ms, answered_at)
     VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8)`
  ).bind(crypto.randomUUID(), sessionId, user.id, question.id, chosenIdx, correct ? 1 : 0, timeMs | 0, now));

  stmts.push(db.prepare(
    'UPDATE questions SET times_answered = times_answered + 1, times_correct = times_correct + ?1 WHERE id = ?2'
  ).bind(correct ? 1 : 0, question.id));

  // ── Elo-lite: 문항의 태그별로 학생 레이팅 갱신 (찍기 정답은 반영 안 함) ──
  if (!guess) {
    const { results: tags } = await db.prepare(
      'SELECT tag_id FROM question_tags WHERE question_id = ?1'
    ).bind(question.id).all();
    for (const { tag_id } of tags) {
      const cur = await db.prepare(
        'SELECT rating, attempts, correct FROM user_tag_skills WHERE user_id = ?1 AND tag_id = ?2'
      ).bind(user.id, tag_id).first();
      const r = cur?.rating ?? DEFAULT_RATING;
      const attempts = cur?.attempts ?? 0;
      const expected = 1 / (1 + 10 ** ((question.rating - r) / ELO_SCALE));
      const next = r + kFor(attempts) * ((correct ? 1 : 0) - expected);
      stmts.push(db.prepare(
        `INSERT INTO user_tag_skills (user_id, tag_id, rating, attempts, correct, last_practiced_at)
         VALUES (?1, ?2, ?3, 1, ?4, ?5)
         ON CONFLICT(user_id, tag_id) DO UPDATE SET
           rating = ?3, attempts = attempts + 1, correct = correct + ?4, last_practiced_at = ?5`
      ).bind(user.id, tag_id, Math.round(next * 10) / 10, correct ? 1 : 0, now));
    }
  }

  // ── 라이트너 SRS (engine.md 6절) ──
  let graduated = false;
  if (!correct) {
    // 오답: box=1, 내일 재출제 (이미 있으면 box 1로 리셋·복귀)
    stmts.push(db.prepare(
      `INSERT INTO review_queue (id, user_id, question_id, box, due_at, created_at, graduated_at)
       VALUES (?1, ?2, ?3, 1, ?4, ?5, NULL)
       ON CONFLICT(user_id, question_id) DO UPDATE SET box = 1, due_at = ?4, graduated_at = NULL`
    ).bind(crypto.randomUUID(), user.id, question.id, kstDate(Date.now(), 1), now));
  } else if (!guess) {
    // 복습 항목의 정답: 박스 진급, 4박스 정답이면 졸업 (큐에 없던 문항은 변화 없음)
    const item = await db.prepare(
      'SELECT box FROM review_queue WHERE user_id = ?1 AND question_id = ?2 AND graduated_at IS NULL'
    ).bind(user.id, question.id).first();
    if (item) {
      if (item.box >= 4) {
        graduated = true;  // 4연승 졸업 = 봉인
        stmts.push(db.prepare(
          'UPDATE review_queue SET graduated_at = ?1 WHERE user_id = ?2 AND question_id = ?3'
        ).bind(now, user.id, question.id));
      } else {
        const nextBox = item.box + 1;
        stmts.push(db.prepare(
          'UPDATE review_queue SET box = ?1, due_at = ?2 WHERE user_id = ?3 AND question_id = ?4'
        ).bind(nextBox, kstDate(Date.now(), SRS_INTERVALS[nextBox - 1]), user.id, question.id));
      }
    }
  }

  await db.batch(stmts);
  return { correct, graduated };
}
