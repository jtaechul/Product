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
  const [userId, expS, sig] = String(token || '').split('.');
  const exp = Number(expS);
  if (!userId || !sig || !Number.isFinite(exp) || exp * 1000 < Date.now()) return null;
  const user = await db.prepare('SELECT * FROM users WHERE id = ?1').bind(userId).first();
  if (!user) return null;
  const want = await hmacHex(user.pin_hash, `${userId}.${exp}`);
  return sig === want ? user : null;
}

// Hono 미들웨어 — c.get('user')에 사용자 행을 싣는다
export const requireAuth = async (c, next) => {
  const m = /^Bearer\s+(.+)$/.exec(c.req.header('Authorization') || '');
  const user = m ? await verifyToken(c.env.DB, m[1]) : null;
  if (!user) return c.json({ error: '로그인이 필요합니다' }, 401);
  c.set('user', user);
  await next();
};
