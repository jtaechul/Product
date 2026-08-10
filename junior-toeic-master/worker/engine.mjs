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
        // 무반복 기준선은 서버의 현재 시각이 아니라 넘겨받은 '오늘'(KST 날짜)에서 센다.
        // 그래야 이 함수가 입력만으로 결과가 정해져 시뮬레이션·테스트가 가능하다.
        .bind(user.id, new Date(Date.parse(`${today}T00:00:00+09:00`) - NO_REPEAT_DAYS * 86400_000).toISOString()).all(),
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

// ── 실력 지도 (레이더 5축 + 옆에 붙는 지표 2개) ──
// 축은 '능력' 기준으로 잡는다. 시험 파트(L1~R3)로 두면 "L2가 약해요"가 되는데
// 아이도 부모도 그 말을 못 알아듣는다.
// 어휘(V.*)는 축에서 뺐다 — 문항 78%에 붙어 있는 '주제 딱지'라 축으로 쓰면
// 전체 평균이 되어 영원히 안 움직인다. 어휘 약점은 오답 유형(W.meaning)이 잡는다.
export const SKILL_AXES = [
  { key: 'listen', name: '듣고 알기', tags: ['LS.photo', 'LS.qr', 'LS.gist', 'LS.accent'] },
  { key: 'read', name: '읽고 알기', tags: ['RS.gist', 'RS.context', 'RS.vocab'] },
  { key: 'find', name: '찾아내기', tags: ['LS.detail', 'RS.scan'] },
  { key: 'grammar', name: '문장 규칙', tags: ['G.tense', 'G.agreement', 'G.pos', 'G.prep', 'G.conj', 'G.pronoun', 'G.modal', 'G.compare', 'G.toinf', 'G.passive'] },
  // 속뜻(추론)은 하루 1문항 남짓이라 첫 주에는 '재는 중'으로 남는다. 그래도 축으로 둔다 —
  // 겉으로 드러난 말이 아니라 속뜻을 잡는 힘은 다른 축이 대신 말해주지 못한다.
  { key: 'infer', name: '속뜻 알기', tags: ['LS.infer', 'RS.infer'] },
];
const AXIS_MIN_ATTEMPTS = 3;   // 이보다 적으면 '아직 재는 중' — 3문항으로 실력이라 하면 거짓말이다

// 실수 유형 딱지 — 오답 보기마다 "왜 그걸 골랐는가"를 문항에 미리 붙여 뒀다(questions.miss_type).
// 축(레이더)이 '어디가 약한가'라면 이쪽은 '왜 틀리는가'다. 고칠 행동이 바로 나온다.
// 답안마다 따로 저장하지 않는다 — chosen_idx 와 문항의 딱지를 맞춰 나중에 언제든 다시 뽑는다.
// (그래서 딱지를 뒤늦게 손봐도 지난 기록까지 새 기준으로 다시 읽힌다)
export const MISS_KO = {
  'M.notsaid': '나오지 않은 내용을 골랐어요',
  'M.swap': '나온 정보를 엉뚱한 곳에 붙였어요',
  'M.number': '숫자를 다른 항목에서 가져왔어요',
  'M.opposite': '지문에 있는 낱말이지만 뜻이 반대예요',
  'A.wrongkind': '묻는 말과 다른 종류로 답했어요',
  'A.yesno': '골라 말해야 하는데 예·아니오로 답했어요',
  'A.echo': '들린 낱말에 낚였어요',
  'W.meaning': '낱말 뜻이 그 자리에 안 맞아요',
  'G.clue': '단서가 되는 낱말을 놓쳤어요',
  'G.pair': '짝이 되는 말이 빠졌어요',
  'G.form': '낱말 모양이 안 맞아요',
  'P.other': '다른 장면 사진이에요',
  'F.offtopic': '앞뒤와 이어지지 않아요',
};
const MISS_MIN = 3;            // 이만큼은 걸려야 '자주'라고 부를 수 있다

// 최근 오답에서 실수 유형 순위를 뽑는다. miss_type 은 {"보기번호": "코드"} 꼴의 JSON이라
// SQL로 풀지 않고 여기서 센다 (오답만 읽으므로 양이 적다).
export function rankMisses(rows, min = MISS_MIN) {
  const count = new Map();
  for (const r of rows) {
    let map;
    try { map = JSON.parse(r.miss_type); } catch { continue; }
    const code = map?.[String(r.chosen_idx)];
    if (!code || !MISS_KO[code]) continue;
    count.set(code, (count.get(code) ?? 0) + 1);
  }
  return [...count.entries()]
    .filter(([, n]) => n >= min)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([code, n]) => ({ code, name: MISS_KO[code], n }));
}

// '오늘'(KST 날짜 문자열)에서 며칠 앞뒤로 민 값.
//  ...ISO는 answered_at(타임스탬프)과 비교용, ...Date는 date 컬럼과 비교용
const kstMs = (date) => Date.parse(`${date}T00:00:00+09:00`);
const shiftISO = (date, days) => new Date(kstMs(date) + days * 86400_000).toISOString();
const shiftDate = (date, days) => kstDate(kstMs(date), days);

// 레이팅(900~1500)을 0~100으로. 점프 점수와 같은 눈금을 쓴다 — 화면에 100점짜리
// 점수가 둘인데 서로 다르면 아이가 어느 쪽을 믿어야 할지 모른다.
const toScore = (rating) => Math.max(0, Math.min(100, Math.round(((rating - 900) / 600) * 100)));

export async function computeSkillMap(db, user, today = kstDate()) {
  const [{ results: skills }, revive, speed, prev, { results: missRows }] = await Promise.all([
    db.prepare('SELECT tag_id, rating, attempts, correct FROM user_tag_skills WHERE user_id = ?1')
      .bind(user.id).all(),
    // 설욕률 — 전에 틀렸던 문제를 다시 만나 맞힌 비율. 정답률보다 정직하다
    // (새 문제를 쉬운 걸로만 받아도 정답률은 오르지만, 설욕률은 안 오른다)
    db.prepare(
      `SELECT COUNT(*) AS met, COALESCE(SUM(a.is_correct), 0) AS won
         FROM answers a
        WHERE a.user_id = ?1
          AND EXISTS (SELECT 1 FROM answers b
                       WHERE b.user_id = a.user_id AND b.question_id = a.question_id
                         AND b.is_correct = 0 AND b.answered_at < a.answered_at)`
    ).bind(user.id).first(),
    // 빠르기 — 맞힌 문제만, 찍기(2초 미만)는 뺀다. 최근 7일 vs 그 앞 7일
    db.prepare(
      `SELECT
         AVG(CASE WHEN answered_at >= ?2 THEN time_ms END) AS recent_ms,
         AVG(CASE WHEN answered_at <  ?2 AND answered_at >= ?3 THEN time_ms END) AS before_ms,
         COUNT(CASE WHEN answered_at >= ?2 THEN 1 END) AS recent_n
         FROM answers
        WHERE user_id = ?1 AND is_correct = 1 AND time_ms >= ?4`
    ).bind(user.id, shiftISO(today, -7), shiftISO(today, -14), GUESS_MS).first(),
    db.prepare('SELECT axes FROM user_skill_daily WHERE user_id = ?1 AND date <= ?2 ORDER BY date DESC LIMIT 1')
      .bind(user.id, shiftDate(today, -13)).first(),
    // 실수 유형 — 최근 30일 오답만. 예전 버릇까지 세면 이미 고친 것이 계속 1위로 남는다
    db.prepare(
      `SELECT a.chosen_idx, q.miss_type
         FROM answers a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ?1 AND a.is_correct = 0
          AND a.answered_at >= ?2 AND q.miss_type IS NOT NULL AND q.miss_type != ''`
    ).bind(user.id, shiftISO(today, -30)).all(),
  ]);

  const by = Object.fromEntries(skills.map((s) => [s.tag_id, s]));
  const past = (() => { try { return prev ? JSON.parse(prev.axes) : {}; } catch { return {}; } })();

  const axes = SKILL_AXES.map((ax) => {
    const rows = ax.tags.map((t) => by[t]).filter((s) => s && s.attempts > 0);
    const attempts = rows.reduce((n, s) => n + s.attempts, 0);
    if (attempts < AXIS_MIN_ATTEMPTS) {
      return { key: ax.key, name: ax.name, score: null, attempts, measuring: true, was: past[ax.key] ?? null };
    }
    // 많이 푼 태그가 더 크게 반영되도록 시도 횟수로 가중평균
    const rating = rows.reduce((sum, s) => sum + s.rating * s.attempts, 0) / attempts;
    return { key: ax.key, name: ax.name, score: toScore(rating), attempts, measuring: false, was: past[ax.key] ?? null };
  });

  const ready = axes.filter((a) => !a.measuring);
  const weakest = ready.length ? ready.reduce((m, a) => (a.score < m.score ? a : m)) : null;

  // 오늘 치 스냅샷 남기기 (없을 때만) — 2주 뒤에 '전보다 늘었나'를 그릴 재료
  if (ready.length) {
    const snap = Object.fromEntries(ready.map((a) => [a.key, a.score]));
    await db.prepare(
      `INSERT INTO user_skill_daily (user_id, date, axes) VALUES (?1, ?2, ?3)
       ON CONFLICT(user_id, date) DO UPDATE SET axes = excluded.axes`
    ).bind(user.id, today, JSON.stringify(snap)).run();
  }

  const round = (v) => (v == null ? null : Math.round(v));
  return {
    axes,
    weakest: weakest ? { key: weakest.key, name: weakest.name, score: weakest.score } : null,
    misses: rankMisses(missRows),
    revive: revive.met ? { met: revive.met, won: revive.won, rate: Math.round((revive.won / revive.met) * 100) } : null,
    speed: speed?.recent_n >= 5
      ? {
          seconds: Math.round(speed.recent_ms / 100) / 10,
          before_seconds: speed.before_ms ? Math.round(speed.before_ms / 100) / 10 : null,
          faster_by: speed.before_ms ? round((speed.before_ms - speed.recent_ms) / 100) / 10 : null,
        }
      : null,
  };
}
