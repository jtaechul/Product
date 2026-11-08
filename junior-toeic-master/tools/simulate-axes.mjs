#!/usr/bin/env node
// 실력 지도 5축이 "며칠 만에 켜지는가"를 실제 엔진으로 잰다.
//
// 부모 화면에 "속뜻 알기"가 몇 주가 지나도 계속 '재는 중'으로만 남는 일이 있었다.
// 코드가 틀린 게 아니라 그 축에 붙은 문항이 너무 적어서, 아이가 3문항(측정 최소치)을
// 만나기까지 하염없이 걸린 것이다. 감으로 "좀 늘리자"고 하면 또 모자랄 수 있으니
// composeDailySet + recordAnswer 를 진짜로 돌려 축별로 며칠에 켜지는지 숫자로 본다.
//
// 사용: node tools/simulate-axes.mjs [일수] [세트크기] [학생수]
//   예) node tools/simulate-axes.mjs 21 12 30
//
// 읽는 법
//   - "켜진 날" = 그 축이 처음으로 3문항을 채워 점수가 나온 날 (중앙값 / 최악)
//   - 30일까지 못 켜지는 축이 있으면 그 축의 문항을 늘려야 한다.

import { DatabaseSync } from 'node:sqlite';
import { readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { composeDailySet, recordAnswer, SKILL_AXES } from '../worker/engine.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const DAYS = Number(process.argv[2] || 21);
const SET_SIZE = Number(process.argv[3] || 12);
const STUDENTS = Number(process.argv[4] || 30);
const MIN = 3;                      // engine.mjs 의 AXIS_MIN_ATTEMPTS 와 같은 값

const d1Dir = join(ROOT, '.wrangler/state/v3/d1/miniflare-D1DatabaseObject');
const file = readdirSync(d1Dir).find((f) => f.endsWith('.sqlite') && f !== 'metadata.sqlite');
if (!file) { console.error('로컬 D1이 없습니다 — wrangler d1 migrations apply --local 을 먼저 하세요'); process.exit(1); }
const sqlite = new DatabaseSync(join(d1Dir, file));

const db = {
  prepare(sql) {
    // D1은 ?1 ?2 처럼 번호를 쓰고 sqlite는 순서대로 ? 를 쓴다. 번호는 같은 것이
    // 여러 번 나올 수 있어서(ON CONFLICT 절에서 흔하다) 그냥 ? 로 바꾸면 값이 밀린다.
    // 나온 순서대로 값을 다시 늘어놓아 자리표와 짝을 맞춘다.
    const order = [...sql.matchAll(/\?(\d+)/g)].map((m) => Number(m[1]) - 1);
    const text = sql.replace(/\?(\d+)/g, '?');
    let args = [];
    const api = {
      bind(...a) { args = order.length ? order.map((i) => a[i]) : a; return api; },
      all() { return { results: sqlite.prepare(text).all(...args) }; },
      first() { return sqlite.prepare(text).get(...args) ?? null; },
      run() { return sqlite.prepare(text).run(...args); },
    };
    return api;
  },
  batch(stmts) { for (const s of stmts) s.run(); return []; },
};

// 태그 → 축
const axisOf = {};
for (const ax of SKILL_AXES) for (const t of ax.tags) axisOf[t] = ax.key;
const tagsBy = {};
for (const { question_id, tag_id } of sqlite.prepare('SELECT question_id, tag_id FROM question_tags').all())
  (tagsBy[question_id] ||= []).push(tag_id);

// 축별로 문항이 몇 개나 있는지 먼저 본다 — 켜지는 속도의 근본 원인이다
const bankByAxis = {};
for (const ids of Object.values({ x: 0 })) void ids;
for (const [qid, tags] of Object.entries(tagsBy))
  for (const k of new Set(tags.map((t) => axisOf[t]).filter(Boolean)))
    (bankByAxis[k] ||= new Set()).add(qid);
const bankN = sqlite.prepare("SELECT COUNT(*) n FROM questions WHERE status='active'").get().n;

console.log(`문항 ${bankN}개 / 하루 ${SET_SIZE}문항 / 학생 ${STUDENTS}명 / ${DAYS}일\n`);
console.log('축별 문항 수');
for (const ax of SKILL_AXES) {
  const n = bankByAxis[ax.key]?.size ?? 0;
  console.log(`  ${ax.name.padEnd(7)} ${String(n).padStart(3)}개  (${(n / bankN * 100).toFixed(1)}%)`
    + `  하루 세트에 기대 ${(n / bankN * SET_SIZE).toFixed(1)}문항`);
}

const base = new Date();
const dayStr = (i) => {
  const d = new Date(base);
  d.setUTCDate(d.getUTCDate() - (DAYS - 1) + i);
  return d.toISOString().slice(0, 10);
};
const SKILL = 1200;

sqlite.prepare(`INSERT OR REPLACE INTO classes (id, academy_id, name, grade, set_size, created_at)
                VALUES ('AXSIM-CLASS', 'ACAD-DEMO', '축시뮬반', '초5', ?, '2026-01-01T00:00:00Z')`).run(SET_SIZE);

const litOn = Object.fromEntries(SKILL_AXES.map((a) => [a.key, []]));   // 축 → 학생별 켜진 날
const totalOn = Object.fromEntries(SKILL_AXES.map((a) => [a.key, []])); // 축 → 학생별 총 만난 문항

for (let s = 0; s < STUDENTS; s++) {
  const uid = `AXSIM-${s}`;
  for (const t of ['answers', 'daily_sets', 'review_queue', 'user_tag_skills',
                   'user_skill_daily', 'user_daily_stats', 'user_stats', 'sessions'])
    sqlite.prepare(`DELETE FROM ${t} WHERE user_id = ?`).run(uid);
  sqlite.prepare(`INSERT OR REPLACE INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at)
                  VALUES (?, 'student', ?, 'x', '축시뮬', 'ACAD-DEMO', 'AXSIM-CLASS', '2026-01-01T00:00:00Z')`)
    .run(uid, `AXSIM${s}`);
  const user = { id: uid, class_id: 'AXSIM-CLASS', display_name: '축시뮬' };

  const attempts = Object.fromEntries(SKILL_AXES.map((a) => [a.key, 0]));
  const lit = {};

  for (let day = 0; day < DAYS; day++) {
    const today = dayStr(day);
    const sessionId = `AXS-${uid}-${today}`;
    sqlite.prepare(`INSERT OR REPLACE INTO sessions (id, user_id, type, question_ids, started_at)
                    VALUES (?, ?, 'daily', '[]', ?)`).run(sessionId, uid, `${today}T09:00:00.000Z`);
    const { ids } = await composeDailySet(db, user, today);
    for (const id of ids) {
      const q = sqlite.prepare('SELECT id, rating, answer_idx FROM questions WHERE id = ?').get(id);
      const p = 1 / (1 + 10 ** ((q.rating - SKILL) / 400));
      // 학생마다 다른 순서로 맞고 틀리게 — 한 사람만 보면 운에 속는다
      const correct = Math.abs(Math.sin((day + 1) * 7919 + s * 104729 + id.charCodeAt(12) * 31)) < p;
      const chosenIdx = correct ? q.answer_idx : (q.answer_idx + 1) % 4;
      await recordAnswer(db, { user, question: q, chosenIdx, timeMs: 9000, sessionId });
      // 찍기(2초 미만)는 반영 안 되지만 여기선 9초로 고정이라 전부 반영된다
      for (const k of new Set((tagsBy[id] || []).map((t) => axisOf[t]).filter(Boolean))) attempts[k]++;
    }
    for (const ax of SKILL_AXES)
      if (lit[ax.key] === undefined && attempts[ax.key] >= MIN) lit[ax.key] = day + 1;
  }
  for (const ax of SKILL_AXES) { litOn[ax.key].push(lit[ax.key] ?? null); totalOn[ax.key].push(attempts[ax.key]); }
  for (const t of ['answers', 'daily_sets', 'review_queue', 'user_tag_skills',
                   'user_skill_daily', 'user_daily_stats', 'user_stats', 'sessions'])
    sqlite.prepare(`DELETE FROM ${t} WHERE user_id = ?`).run(uid);
  sqlite.prepare('DELETE FROM users WHERE id = ?').run(uid);
}

const med = (a) => { const x = a.slice().sort((p, q) => p - q); return x[Math.floor(x.length / 2)]; };
console.log(`\n축이 켜지는 날 (3문항을 채워 점수가 나오기까지)`);
let fail = 0;
for (const ax of SKILL_AXES) {
  const v = litOn[ax.key];
  const ok = v.filter((x) => x != null);
  const never = v.length - ok.length;
  if (never) fail++;
  const line = ok.length
    ? `중앙값 ${String(med(ok)).padStart(2)}일  최악 ${String(Math.max(...ok)).padStart(2)}일`
    : '한 명도 못 켬';
  console.log(`  ${ax.name.padEnd(7)} ${line}` + (never ? `  ⚠ ${DAYS}일 안에 못 켠 학생 ${never}/${STUDENTS}명` : ''));
}
// 켜지고 끝이 아니라 계속 쌓여야 점수가 움직인다 — "켜졌는데 그대로다"를 잡는 눈금
console.log(`\n${DAYS}일 동안 축마다 만난 문항 수 (중앙값)`);
for (const ax of SKILL_AXES)
  console.log(`  ${ax.name.padEnd(7)} ${String(med(totalOn[ax.key])).padStart(3)}문항`
    + `  = 하루 ${(med(totalOn[ax.key]) / DAYS).toFixed(1)}문항`);
console.log(fail ? `\n⚠ ${DAYS}일이 지나도 '재는 중'에 머무는 축이 있습니다 — 그 축의 문항을 늘리세요.`
  : `\n모든 축이 ${DAYS}일 안에 켜집니다.`);
