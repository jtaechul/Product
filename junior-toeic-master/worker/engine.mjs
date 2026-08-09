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
  return { correct };
}
