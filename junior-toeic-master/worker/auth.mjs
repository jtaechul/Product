// 점프리시 인증 — 학원 발급 로그인ID(가입코드-순번) + 6자리 PIN (PRD 5절·ERD users)
// 설계 메모
// - PIN 해시: s1$<salt>$<sha256(salt:pin)>  (Workers 무료 플랜 CPU 한도 때문에 PBKDF2 대신
//   SHA-256. PIN은 저엔트로피라 어떤 빠른 해시든 오프라인 공격엔 약하다 — 방어선은
//   로그인 시도 제한(M4에서 학원 단위로 추가)과 계정 잠금이다.)
// - 토큰: <userId>.<만료초>.<HMAC-SHA256(key=pin_hash, msg=userId.만료초)>
//   서버 비밀키가 따로 필요 없다(사용자 행을 어차피 읽는다). PIN을 바꾸면
//   그 학생의 기존 토큰이 전부 무효화된다 — 의도된 동작.

const enc = new TextEncoder();

export async function sha256Hex(s) {
  const d = await crypto.subtle.digest('SHA-256', enc.encode(s));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function hashPin(pin, salt = crypto.randomUUID().slice(0, 8)) {
  return `s1$${salt}$${await sha256Hex(`${salt}:${pin}`)}`;
}

export async function verifyPin(pin, stored) {
  const [v, salt, hex] = String(stored || '').split('$');
  if (v !== 's1' || !salt || !hex) return false;
  return (await sha256Hex(`${salt}:${pin}`)) === hex;
}

// ── 학부모 비밀번호 해시 (아이 PIN과 다른 방식을 쓴다) ──
// 아이 PIN은 6자리라 어떤 해시를 써도 오프라인 공격엔 약하고, 대신 로그인 시도 제한으로 막는다.
// 학부모 비밀번호는 다르다 — 사람들은 비밀번호를 다른 사이트와 돌려쓰기 때문에,
// DB가 유출되면 우리 서비스 밖에서도 피해가 난다. 그래서 여기만 PBKDF2로 느리게 만든다.
// 느려도 되는 이유: 토큰이 30일짜리라 학부모가 이 계산을 겪는 건 한 달에 한 번뿐이다.
const KDF_ITER = 100_000;

export async function hashSecret(secret, salt = crypto.randomUUID().replace(/-/g, '').slice(0, 16)) {
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: enc.encode(salt), iterations: KDF_ITER, hash: 'SHA-256' }, key, 256);
  const hex = [...new Uint8Array(bits)].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `p2$${KDF_ITER}$${salt}$${hex}`;
}

export async function verifySecret(secret, stored) {
  const [v, iterS, salt, hex] = String(stored || '').split('$');
  if (v !== 'p2' || !salt || !hex) return false;
  const iter = Number(iterS);
  if (!Number.isFinite(iter) || iter < 1000 || iter > 1_000_000) return false;
  const key = await crypto.subtle.importKey('raw', enc.encode(secret), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'PBKDF2', salt: enc.encode(salt), iterations: iter, hash: 'SHA-256' }, key, 256);
  const got = [...new Uint8Array(bits)].map((b) => b.toString(16).padStart(2, '0')).join('');
  // 길이가 다르면 바로 실패. 같으면 글자를 전부 훑어 비교한다(빨리 끝나는 데서 새는 정보를 막는다)
  if (got.length !== hex.length) return false;
  let diff = 0;
  for (let i = 0; i < got.length; i++) diff |= got.charCodeAt(i) ^ hex.charCodeAt(i);
  return diff === 0;
}

async function hmacHex(key, msg) {
  const k = await crypto.subtle.importKey('raw', enc.encode(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = await crypto.subtle.sign('HMAC', k, enc.encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

const TOKEN_TTL_S = 30 * 24 * 3600; // 30일

export async function makeToken(user) {
  const exp = Math.floor(Date.now() / 1000) + TOKEN_TTL_S;
  const msg = `${user.id}.${exp}`;
  return `${msg}.${await hmacHex(user.pin_hash, msg)}`;
}

// 성공 시 users 행 반환, 실패 시 null
export async function verifyToken(db, token) {
  const parts = String(token || '').split('.');
  // 학부모 토큰(p.으로 시작)은 여기서 절대 통과시키지 않는다 — 부모가 아이 대신
  // 문제를 풀거나 이름을 바꾸면 안 된다. 부모 토큰은 verifyParentToken 만 받는다.
  if (parts.length !== 3) return null;
  const [userId, expS, sig] = parts;
  const exp = Number(expS);
  if (!userId || !sig || !Number.isFinite(exp) || exp * 1000 < Date.now()) return null;
  const user = await db.prepare('SELECT * FROM users WHERE id = ?1').bind(userId).first();
  if (!user) return null;
  const want = await hmacHex(user.pin_hash, `${userId}.${exp}`);
  return sig === want ? user : null;
}

// ── 학부모 토큰 ──
//   pa.<학부모id>.<만료초>.<HMAC(key=password_hash)>
// 학생 토큰은 조각이 3개뿐이라(이건 4개) 서로 섞일 수 없다.
// 서명 열쇠가 비밀번호 해시라, 비밀번호를 바꾸면 학부모 토큰만 무효가 되고
// 아이 로그인은 그대로다.
//
// 학원이 발급하던 'p.<자녀id>' 토큰은 없앴다 — 학원 영업을 하지 않기로 하면서
// 그 화면 자체가 사라졌고, 들어갈 문이 없는 열쇠를 남겨둘 이유가 없다.
const PA = 'pa';

export async function makeAccountToken(parent) {
  const exp = Math.floor(Date.now() / 1000) + TOKEN_TTL_S;
  const msg = `${PA}.${parent.id}.${exp}`;
  return `${msg}.${await hmacHex(parent.password_hash, msg)}`;
}

// 성공 시 parents 행, 실패 시 null
export async function verifyParentToken(db, token) {
  const parts = String(token || '').split('.');
  if (parts.length !== 4 || parts[0] !== PA) return null;
  const [, parentId, expS, sig] = parts;
  const exp = Number(expS);
  if (!parentId || !sig || !Number.isFinite(exp) || exp * 1000 < Date.now()) return null;
  const parent = await db.prepare('SELECT * FROM parents WHERE id = ?1').bind(parentId).first();
  if (!parent) return null;
  const want = await hmacHex(parent.password_hash, `${PA}.${parentId}.${exp}`);
  return sig === want ? parent : null;
}

// 학부모 전용 미들웨어 — c.get('child')에 '지금 보고 있는 자녀' 행을 싣는다.
//
// 어느 아이를 볼지는 요청이 정하지만, **그 아이가 이 학부모의 아이인지는 서버가 확인한다.**
// 남의 아이 id를 넣어도 parent_id 가 안 맞으면 조회 자체가 비어서 돌아온다.
export const requireParent = async (c, next) => {
  const m = /^Bearer\s+(.+)$/.exec(c.req.header('Authorization') || '');
  const parent = m ? await verifyParentToken(c.env.DB, m[1]) : null;
  if (!parent) return c.json({ error: '로그인이 필요합니다' }, 401);

  const wanted = c.req.query('child_id');
  const child = await (wanted
    ? c.env.DB.prepare(`SELECT * FROM users WHERE id = ?1 AND parent_id = ?2 AND role = 'student'`)
        .bind(wanted, parent.id)
    : c.env.DB.prepare(
        `SELECT * FROM users WHERE parent_id = ?1 AND role = 'student' ORDER BY created_at LIMIT 1`)
        .bind(parent.id)
  ).first();
  // 두 경우를 나눠 안내한다. 어느 쪽이든 남의 아이가 있는지 없는지는 알려주지 않는다 —
  // 없는 id를 넣었을 때와 남의 아이 id를 넣었을 때의 답이 똑같다.
  if (!child) {
    return wanted
      ? c.json({ error: '아이를 찾을 수 없습니다' }, 404)
      : c.json({ error: '아이를 먼저 등록해주세요', need_child: true }, 404);
  }
  c.set('child', child);
  c.set('parent', parent);
  await next();
};

// 자녀 등록·PIN 재발급처럼 '아이가 아직 없어도' 되는 화면용.
// requireParent 는 아이가 없으면 404를 내므로 가입 직후 화면에서는 쓸 수 없다.
export const requireParentAccount = async (c, next) => {
  const m = /^Bearer\s+(.+)$/.exec(c.req.header('Authorization') || '');
  const parent = m ? await verifyParentToken(c.env.DB, m[1]) : null;
  if (!parent) return c.json({ error: '학부모 계정으로 로그인해주세요' }, 401);
  c.set('parent', parent);
  await next();
};

// ── 로그인 시도 제한 ──
// PIN이 저엔트로피라(6자리 = 100만 가지) 막지 않으면 스크립트로 다 넣어볼 수 있다.
// 실패가 쌓일수록 잠금이 길어지고, 한 번 성공하면 0으로 돌아간다.
// 잠금을 짧게 시작하는 이유: 남의 아이디를 일부러 잠가 괴롭히는 것도 막아야 한다.
const LOCK_STEPS = [
  { fails: 20, minutes: 30 },
  { fails: 10, minutes: 5 },
  { fails: 5, minutes: 1 },
];
const lockMinutes = (fails) => LOCK_STEPS.find((s) => fails >= s.fails)?.minutes ?? 0;

// 지금 잠겨 있으면 남은 초, 아니면 0
export async function loginLockedFor(db, loginId) {
  const row = await db.prepare('SELECT locked_until FROM login_attempts WHERE login_id = ?1')
    .bind(loginId).first();
  if (!row?.locked_until) return 0;
  const left = Math.ceil((Date.parse(row.locked_until) - Date.now()) / 1000);
  return left > 0 ? left : 0;
}

export async function noteLoginFail(db, loginId) {
  const row = await db.prepare('SELECT fails FROM login_attempts WHERE login_id = ?1')
    .bind(loginId).first();
  const fails = (row?.fails ?? 0) + 1;
  const mins = lockMinutes(fails);
  const until = mins ? new Date(Date.now() + mins * 60_000).toISOString() : null;
  await db.prepare(
    `INSERT INTO login_attempts (login_id, fails, last_fail_at, locked_until) VALUES (?1, ?2, ?3, ?4)
     ON CONFLICT(login_id) DO UPDATE SET fails = ?2, last_fail_at = ?3, locked_until = ?4`
  ).bind(loginId, fails, new Date().toISOString(), until).run();
  return { fails, lockedSeconds: mins * 60 };
}

export const clearLoginFails = (db, loginId) =>
  db.prepare('DELETE FROM login_attempts WHERE login_id = ?1').bind(loginId).run();

// ── 비밀번호 형식 ──
// 학생은 6자리 숫자 PIN 그대로(아이들이 외워야 한다). 관리자·강사는 계정을 발급할 수 있는
// 권한이라 6자리로는 부족하다 — 8자 이상을 쓴다.
//
// 8자면 짧지 않나: 남이 찍어서 맞히는(온라인) 공격은 위 로그인 잠금이 막는다.
// 남는 위험은 DB가 통째로 유출됐을 때 오프라인으로 돌려보는 경우인데, 8자짜리
// 뻔한 비밀번호는 그때 금방 깨진다. 그래서 길이만 보지 않고 뻔한 것들을 걸러낸다.
export const STAFF_ROLES = ['teacher', 'academy_admin', 'super'];
export const SECRET_MIN = 8;
export const isStudentPin = (s) => /^\d{6}$/.test(String(s ?? ''));

// 자주 쓰이는 비밀번호와 그 변형(대소문자·뒤에 붙는 숫자)을 막는다.
const WEAK = [
  'password', 'passw0rd', 'admin', 'administrator', 'jumplish', 'jumprish',
  'qwerty', 'qwertyui', 'asdfasdf', 'iloveyou', 'welcome', 'letmein',
  'abcd', 'abcdefg', 'test', 'secret', 'master', 'login', 'academy', 'english',
];
// 로그인할 때 쓰는 형식 검사 — 길이만 본다.
// 뻔한 비밀번호 검사(아래 weakSecretReason)를 여기 섞으면 안 된다. 규칙을 나중에 강화했을 때
// 이미 그 비밀번호로 만들어진 계정이 로그인조차 못 하게 된다.
export const isStaffSecret = (s) =>
  typeof s === 'string' && s.length >= SECRET_MIN && s.length <= 200;

// 새로 정할 때만 쓰는 검사 — 문제가 있으면 그 이유를, 없으면 null
export function weakSecretReason(secret, loginId = '') {
  const s = String(secret ?? '');
  if (s.length < SECRET_MIN) return `비밀번호는 ${SECRET_MIN}자 이상이어야 합니다`;
  if (s.length > 200) return '비밀번호가 너무 깁니다';
  if (/\s/.test(s)) return '비밀번호에 공백은 쓸 수 없어요';
  const low = s.toLowerCase();
  // 숫자만 / 같은 글자 반복 / 연속된 순서 (12345678, aaaaaaaa, abcdefgh)
  if (/^\d+$/.test(s)) return '숫자만으로는 안 돼요. 글자를 섞어주세요';
  if (/^(.)\1+$/.test(s)) return '같은 글자만 반복하면 안 돼요';
  if ('abcdefghijklmnopqrstuvwxyz'.includes(low) || '01234567890'.includes(low)) {
    return '순서대로 이어지는 글자는 쉽게 뚫려요';
  }
  // 뻔한 단어 + 뒤에 붙인 숫자(admin123, password1!) 도 같이 걸러낸다
  const core = low.replace(/[^a-z]/g, '');
  if (WEAK.some((w) => core === w || (core.startsWith(w) && core.length - w.length <= 2))) {
    return '너무 흔한 비밀번호예요. 다른 말로 정해주세요';
  }
  // 아이디를 그대로 비밀번호에 넣은 경우를 막는다.
  // 단, 아이디에서 뽑은 글자가 너무 짧으면 검사 자체가 무의미하다 —
  // 이메일이 a@b.com 이면 '아이디'가 'a' 한 글자라, a가 들어간 멀쩡한 비밀번호가 전부 막힌다.
  const idCore = String(loginId).toLowerCase().replace(/[^a-z]/g, '');
  if (idCore.length >= 4 && core.includes(idCore) && core.length <= 12) {
    return '아이디와 너무 비슷해요';
  }
  return null;   // 문제 없음
}

// Hono 미들웨어 — c.get('user')에 사용자 행을 싣는다
export const requireAuth = async (c, next) => {
  const m = /^Bearer\s+(.+)$/.exec(c.req.header('Authorization') || '');
  const user = m ? await verifyToken(c.env.DB, m[1]) : null;
  if (!user) return c.json({ error: '로그인이 필요합니다' }, 401);
  c.set('user', user);
  await next();
};

// 역할 제한 — requireAuth 뒤에 붙여 쓴다. 권한이 없으면 404가 아니라 403으로 분명히 막는다.
export const requireRole = (...roles) => async (c, next) => {
  const u = c.get('user');
  if (!u || !roles.includes(u.role)) return c.json({ error: '권한이 없습니다' }, 403);
  await next();
};
