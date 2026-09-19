#!/usr/bin/env node
// 테스터 계정 발급 — 지인 자녀 실사용 검증(M3 완료 기준)용.
//
// 학원이 아직 없으므로 '테스터 학원 / 테스터반' 하나를 만들고 그 안에 계정을 발급한다.
// 반 정원은 12문항으로 고정한다 — 지금 문항 수(120개)로 2주를 버티는 유일한 설정이다.
// (근거: tools/simulate-fortnight.mjs — 20문항 반은 14일 중 6일이 정원 미달)
//
// 사용: node tools/make-testers.mjs [인원수] [가입코드]
//   예) node tools/make-testers.mjs 8 JT
//   산출: tools/out/testers.sql  (원격 적용: npx wrangler d1 execute jumplish-db --remote --file tools/out/testers.sql)
//        tools/out/testers.md    (아이·부모에게 나눠 줄 아이디/PIN 표)
//
// ⚠ PIN은 이 실행에서만 평문으로 보인다(DB에는 해시만 들어간다). testers.md 는
//   저장소에 커밋하지 않는다(tools/out/ 은 .gitignore 대상).

import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { webcrypto } from 'node:crypto';
import { hashPin } from '../worker/auth.mjs';

if (!globalThis.crypto) globalThis.crypto = webcrypto;   // 워커용 코드를 그대로 재사용

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tools', 'out');
const N = Math.max(1, Math.min(50, Number(process.argv[2] || 8)));
const CODE = (process.argv[3] || 'JT').toUpperCase().replace(/[^A-Z0-9]/g, '');
const SET_SIZE = 12;

const q = (s) => (s === null || s === undefined ? 'NULL' : `'${String(s).replace(/'/g, "''")}'`);
const now = new Date().toISOString();

// 6자리 PIN — 생일·1234 같은 추측하기 쉬운 값은 피한다
const WEAK = new Set(['000000', '111111', '123456', '654321', '121212', '112233']);
const pin6 = () => {
  for (;;) {
    const n = webcrypto.getRandomValues(new Uint32Array(1))[0] % 1000000;
    const s = String(n).padStart(6, '0');
    if (!WEAK.has(s) && !/^(\d)\1{5}$/.test(s)) return s;
  }
};

const ACADEMY = `ACAD-${CODE}`;
const CLASS = `CLASS-${CODE}`;
const sql = [
  '-- 테스터 계정 (지인 자녀 실사용 검증용). 반 정원 12문항 고정.',
  `INSERT OR IGNORE INTO academies (id, name, join_code, created_at) VALUES (${q(ACADEMY)}, '테스터', ${q(CODE)}, ${q(now)});`,
  `INSERT OR IGNORE INTO classes (id, academy_id, name, grade, set_size, created_at)` +
    ` VALUES (${q(CLASS)}, ${q(ACADEMY)}, '테스터반', '초5', ${SET_SIZE}, ${q(now)});`,
];
const rows = [];

for (let i = 1; i <= N; i++) {
  const loginId = `${CODE}-${i}`;
  const pin = pin6();
  const hash = await hashPin(pin);
  const id = `U-${CODE}-${String(i).padStart(2, '0')}`;
  sql.push(
    `INSERT INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at)` +
    ` VALUES (${q(id)}, 'student', ${q(loginId)}, ${q(hash)}, ${q(`테스터${i}`)}, ${q(ACADEMY)}, ${q(CLASS)}, ${q(now)})` +
    ` ON CONFLICT(login_id) DO UPDATE SET pin_hash=excluded.pin_hash, class_id=excluded.class_id;`
  );
  rows.push({ loginId, pin });
}

mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, 'testers.sql'), sql.join('\n') + '\n');

const md = [
  '# 점프리시 테스터 계정',
  '',
  `발급 ${N}개 · 반 정원 하루 ${SET_SIZE}문항 · 발급일 ${now.slice(0, 10)}`,
  '',
  '| 번호 | 아이디 | 비밀번호(6자리) | 사용할 아이 |',
  '|---|---|---|---|',
  ...rows.map((r, i) => `| ${i + 1} | \`${r.loginId}\` | \`${r.pin}\` | |`),
  '',
  '- 아이디는 대소문자를 가리지 않습니다.',
  '- 비밀번호는 이 표에만 있습니다. 잃어버리면 다시 발급해야 합니다.',
  '- 아이 한 명에 계정 하나씩 주세요(기록이 섞이면 추천이 엉킵니다).',
].join('\n');
writeFileSync(join(OUT, 'testers.md'), md + '\n');

console.log(`테스터 ${N}개 발급 — tools/out/testers.sql, tools/out/testers.md`);
console.log('원격 적용: npx wrangler d1 execute jumplish-db --remote --file tools/out/testers.sql');
console.table(rows);
