#!/usr/bin/env node
// 2주 시뮬레이션 — "지금 문항 수로 며칠이나 버티는가"를 실제 엔진으로 확인한다.
//
// 문항을 늘릴지 말지는 감이 아니라 이 숫자로 정한다. 로컬 D1(sqlite)을 그대로 열고
// worker/engine.mjs 의 composeDailySet 을 진짜로 호출하면서 하루씩 앞으로 감는다.
// 학생은 자기 실력대로 맞히고 틀린다고 가정한다(레이팅 차이 → 정답 확률).
//
// 사용: node tools/simulate-fortnight.mjs [일수] [세트크기] [로그인ID]
//   로그인ID를 주면 그 학생 계정에 기록한다(실력 지도 화면을 실제 데이터로 확인할 때).
//   예) node tools/simulate-fortnight.mjs 14 12
//       node tools/simulate-fortnight.mjs 14 20     ← 초5~중3 반
//
// 확인하는 것
//   1) 매일 세트를 정원만큼 채우는가 (못 채우면 문항 부족)
//   2) 14일 무반복 규칙이 실제로 지켜지는가
//   3) 파트별로 골고루 나오는가 (한 파트만 먼저 바닥나는지)

import { DatabaseSync } from 'node:sqlite';
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { composeDailySet } from '../worker/engine.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DAYS = Number(process.argv[2] || 14);
const SET_SIZE = Number(process.argv[3] || 12);
const LOGIN_ID = process.argv[4] || null;   // 없으면 가상의 시뮬 학생

const d1Dir = join(ROOT, '.wrangler/state/v3/d1/miniflare-D1DatabaseObject');
const file = readdirSync(d1Dir).find((f) => f.endsWith('.sqlite') && f !== 'metadata.sqlite');
if (!file) { console.error('로컬 D1 파일이 없습니다 — wrangler d1 migrations apply --local 을 먼저 하세요'); process.exit(1); }
const sqlite = new DatabaseSync(join(d1Dir, file));

// D1 인터페이스(prepare/bind/all/first/run/batch)를 sqlite 위에 얇게 흉내 낸다.
// ?1 ?2 형태를 sqlite가 이해하는 ? 로 바꿔 순서대로 바인딩한다.
const toPositional = (sql) => sql.replace(/\?(\d+)/g, '?');
const db = {
  prepare(sql) {
    const text = toPositional(sql);
    let args = [];
    const api = {
      bind(...a) { args = a; return api; },
      all() { return { results: sqlite.prepare(text).all(...args) }; },
      first() { return sqlite.prepare(text).get(...args) ?? null; },
      run() { return sqlite.prepare(text).run(...args); },
    };
    return api;
  },
  batch(stmts) { for (const s of stmts) s.run(); return []; },
};

// ── 가상의 학생 한 명 ──
let USER = { id: 'SIM-USER', class_id: 'SIM-CLASS', display_name: '시뮬' };
sqlite.exec(`DELETE FROM answers WHERE user_id = 'SIM-USER';
             DELETE FROM daily_sets WHERE user_id = 'SIM-USER';
             DELETE FROM review_queue WHERE user_id = 'SIM-USER';
             DELETE FROM user_tag_skills WHERE user_id = 'SIM-USER';
             DELETE FROM user_skill_daily WHERE user_id = 'SIM-USER';
             DELETE FROM sessions WHERE user_id = 'SIM-USER';`);
sqlite.prepare(`INSERT OR REPLACE INTO classes (id, academy_id, name, grade, set_size, created_at)
                VALUES ('SIM-CLASS', 'ACAD-DEMO', '시뮬반', '초5', ?, '2026-01-01T00:00:00Z')`).run(SET_SIZE);
sqlite.exec(`INSERT OR REPLACE INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at)
             VALUES ('SIM-USER', 'student', 'SIM-0', 'x', '시뮬학생', 'ACAD-DEMO', 'SIM-CLASS', '2026-01-01T00:00:00Z')`);
if (LOGIN_ID) {
  const row = sqlite.prepare('SELECT id, class_id FROM users WHERE login_id = ?').get(LOGIN_ID.toUpperCase());
  if (!row) { console.error(`로그인ID ${LOGIN_ID} 계정이 없습니다`); process.exit(1); }
  USER = { ...row, display_name: LOGIN_ID };
  console.log(`${LOGIN_ID} 계정에 기록합니다 (기존 기록은 지웁니다)`);
  // sessions 를 참조하는 표(daily_sets·assignment_targets·answers)를 먼저 지운다 —
  // 순서를 바꾸면 FOREIGN KEY constraint failed 로 멈춘다
  for (const t of ['answers', 'daily_sets', 'assignment_targets', 'review_queue',
                   'user_tag_skills', 'user_skill_daily', 'user_daily_stats', 'user_stats', 'sessions'])
    sqlite.prepare(`DELETE FROM ${t} WHERE user_id = ?`).run(row.id);
}

const SKILL = 1200;                 // 학생 실력(진단 평균과 같은 눈금)
// 마지막 날이 '오늘'이 되도록 뒤에서부터 센다 — 14일 무반복 창 안에 전부 들어와야
// 실제와 같은 조건이 된다 (미래 날짜로 돌리면 영원히 무반복이 되어 결과가 거짓이 된다)
const base = new Date();
const dayStr = (i) => {
  const d = new Date(base);
  d.setUTCDate(d.getUTCDate() - (DAYS - 1) + i);
  return d.toISOString().slice(0, 10);
};

const sid = (date) => `S-${USER.id}-${date}`;

const PARTS = ['L1', 'L2', 'L3', 'L4', 'R1', 'R2', 'R3'];
const seenOn = new Map();           // question_id → 마지막으로 푼 날(인덱스)
let short = 0, repeat = 0;
const partTotals = Object.fromEntries(PARTS.map((p) => [p, 0]));

console.log(`문항 ${sqlite.prepare("SELECT COUNT(*) n FROM questions WHERE status='active'").get().n}개 / 하루 ${SET_SIZE}문항 / ${DAYS}일 시뮬레이션\n`);

for (let day = 0; day < DAYS; day++) {
  const today = dayStr(day);
  // 복습으로 다시 나오는 문항은 재출제가 아니라 설계된 동작 — 미리 구분해 둔다
  const dueIds = new Set(sqlite.prepare(
    `SELECT question_id FROM review_queue WHERE user_id = ? AND graduated_at IS NULL AND due_at <= ?`
  ).all(USER.id, today).map((r) => r.question_id));

  sqlite.prepare(`INSERT OR REPLACE INTO sessions (id, user_id, type, question_ids, started_at)
                  VALUES (?, ?, 'daily', '[]', ?)`).run(sid(today), USER.id, `${today}T09:00:00.000Z`);
  const { ids } = await composeDailySet(db, USER, today);
  const parts = Object.fromEntries(PARTS.map((p) => [p, 0]));
  let dup = 0;

  for (const id of ids) {
    const row = sqlite.prepare('SELECT part, rating, answer_idx FROM questions WHERE id = ?').get(id);
    parts[row.part]++; partTotals[row.part]++;
    const last = seenOn.get(id);
    if (last !== undefined && day - last < 14 && !dueIds.has(id)) dup++;
    seenOn.set(id, day);

    // 맞고 틀림을 실력 차로 흉내 낸다 (문항 레이팅이 높을수록 어려움)
    const p = 1 / (1 + 10 ** ((row.rating - SKILL) / 400));
    const correct = Math.abs(Math.sin((day + 1) * 7919 + id.length * 31 + id.charCodeAt(12))) < p;
    const chosen = correct ? row.answer_idx : (row.answer_idx + 1) % 4;
    // 푸는 시간도 흉내 낸다 — 익숙해질수록 조금씩 빨라지고, 문항마다 들쭉날쭉하다.
    // 고정값(9초)으로 넣으면 '빠르기' 화면이 늘 "지난주와 같음"이 되어 검증이 안 된다.
    const jitter = Math.abs(Math.sin((day + 3) * 104729 + id.length * 17)) * 5000 - 2500;
    const timeMs = Math.max(2200, Math.round(12000 - day * 260 + jitter));
    sqlite.prepare(`INSERT INTO answers (id, session_id, user_id, question_id, chosen_idx, is_correct, time_ms, answered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(`${USER.id}-${today}-${id}`, sid(today), USER.id, id, chosen, correct ? 1 : 0, timeMs, `${today}T09:00:00.000Z`);
    // 틀리면 복습 큐에 (SRS 1일 뒤) — 실제 recordAnswer와 같은 효과만 흉내
    if (!correct) {
      const next = dayStr(day + 1);
      sqlite.prepare(`INSERT INTO review_queue (id, user_id, question_id, box, due_at, created_at)
                      VALUES (?, ?, ?, 1, ?, ?)
                      ON CONFLICT(user_id, question_id) DO UPDATE SET box = 1, due_at = excluded.due_at`)
        .run(`RQ-${USER.id}-${id}`, USER.id, id, next, `${today}T09:00:00.000Z`);
    } else if (dueIds.has(id)) {
      sqlite.prepare(`UPDATE review_queue SET box = box + 1, due_at = ?
                       WHERE user_id = ? AND question_id = ?`)
        .run(dayStr(day + [1, 3, 7, 14][Math.min(3, 1)]), USER.id, id);
    }
  }

  if (ids.length < SET_SIZE) short++;
  repeat += dup;
  const bar = PARTS.map((p) => `${p}:${parts[p]}`).join(' ');
  console.log(`${day + 1}일차  ${String(ids.length).padStart(2)}/${SET_SIZE}문항  ${bar}` +
    (ids.length < SET_SIZE ? '  ← 정원 미달' : '') + (dup ? `  ← 14일 내 재출제 ${dup}` : ''));
}

console.log(`\n파트별 누적: ${PARTS.map((p) => `${p} ${partTotals[p]}`).join(' / ')}`);
console.log(`서로 다른 문항 ${seenOn.size}개 사용`);
console.log(short ? `⚠ 정원 미달 ${short}일 — 문항이 모자랍니다` : '정원 미달 없음');
console.log(repeat ? `⚠ 14일 내 재출제 ${repeat}건` : '14일 내 재출제 없음');
