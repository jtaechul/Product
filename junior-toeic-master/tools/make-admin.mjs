#!/usr/bin/env node
// 관리자(super) 계정 만들기 — 비밀번호는 절대 저장소에 남기지 않는다.
//
// 왜 따로 도구인가: 관리자 화면에서 학원·학생 계정을 만들 수 있게 되지만,
// 그 화면에 들어갈 첫 관리자 계정만은 손으로 만들어야 한다(닭과 달걀).
//
// ⚠️ 이 저장소는 공개다. 비밀번호가 커밋되면 그 순간 관리자 계정이 남의 것이 된다.
//    그래서 결과는 tools/out/ 에만 쓴다 (.gitignore 로 막혀 있음).
//
// 사용: node tools/make-admin.mjs [로그인ID]        (기본값 ADMIN)
//   → tools/out/admin.sql  : 운영 DB에 붙여넣을 SQL
//   → tools/out/admin.txt  : 로그인ID + 비밀번호 (한 번만 생성됨, 안전한 곳에 옮기고 지울 것)

import { writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { webcrypto, randomInt } from 'node:crypto';

globalThis.crypto ??= webcrypto;                  // auth.mjs 가 Workers 의 crypto 를 쓴다
const { hashPin, SECRET_MIN } = await import('../worker/auth.mjs');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'tools', 'out');
const LOGIN_ID = (process.argv[2] || 'ADMIN').trim().toUpperCase();

if (!/^[A-Z0-9-]{2,32}$/.test(LOGIN_ID)) {
  console.error('로그인ID는 영문 대문자·숫자·하이픈 2~32자만 됩니다');
  process.exit(1);
}

// 사람이 옮겨 적을 수 있으면서 충분히 긴 비밀번호.
// 헷갈리는 글자(0/O, 1/l/I)는 뺐다 — 잘못 적어 못 들어가는 일이 실제로 잦다.
const WORDS = 'abcdefghjkmnpqrstuvwxyz23456789';
const chunk = (n) => Array.from({ length: n }, () => WORDS[randomInt(WORDS.length)]).join('');
const secret = [chunk(5), chunk(5), chunk(5), chunk(5)].join('-');   // 23자
if (secret.length < SECRET_MIN) throw new Error('비밀번호가 너무 짧습니다');

const id = `U-${chunk(8)}`;
const sql = `-- 점프리시 관리자(super) 계정 — 이 파일은 저장소에 커밋되지 않습니다.
-- Cloudflare 콘솔 > D1 > jumplish-db > Console 에 붙여넣고 실행하세요.
INSERT INTO users (id, role, login_id, pin_hash, display_name, academy_id, class_id, created_at)
VALUES ('${id}', 'super', '${LOGIN_ID}', '${await hashPin(secret)}', '관리자', NULL, NULL, '${new Date().toISOString()}');
`;

if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });
writeFileSync(join(OUT, 'admin.sql'), sql);
writeFileSync(join(OUT, 'admin.txt'),
  `점프리시 관리자 계정\n\n로그인ID: ${LOGIN_ID}\n비밀번호: ${secret}\n\n` +
  `· 이 비밀번호는 서버에 해시로만 저장되어, 잃어버리면 다시 볼 수 없습니다.\n` +
  `· 비밀번호 관리 앱에 옮겨 적은 뒤 이 파일은 지우세요.\n` +
  `· 저장소에 커밋하지 마세요 (tools/out/ 은 .gitignore 로 막혀 있습니다).\n`);

console.log(`관리자 계정 준비 완료\n`);
console.log(`  로그인ID : ${LOGIN_ID}`);
console.log(`  비밀번호 : ${secret}\n`);
console.log(`  SQL      : tools/out/admin.sql   ← Cloudflare D1 콘솔에 붙여넣기`);
console.log(`  메모     : tools/out/admin.txt   ← 옮겨 적은 뒤 삭제\n`);
console.log(`⚠️  비밀번호는 여기 말고 어디에도 남지 않습니다. 지금 옮겨 적으세요.`);
