// 백엔드 호출 래퍼.
// 프로토타입(P1)은 localStorage 기반 MOCK 으로 동작합니다.
// ⚠️ 프로토타입에서는 실제 개인정보를 서버로 전송/저장하지 않습니다(브라우저 로컬에만 보관).
//    실제 암호화 저장·이메일 발송·선착순·조회는 P2에서 Cloudflare Workers 로 교체합니다.
//    교체 시 MODE 를 'worker' 로 바꾸고 workerFetch 구현부를 연결하면 됩니다.

import { EVENT } from './spots.js';

const MODE = 'mock'; // 'mock' | 'worker'
const KEY = 'bst_v1';         // 참가자 개인 상태(로컬)
const SEQ_KEY = 'bst_seq_v1'; // 선착순 순번(로컬 mock 전용)
const OTP_KEY = 'bst_otp_v1'; // 진행 중인 이메일 OTP(로컬 mock)
const BIND_KEY = 'bst_bind_v1'; // 휴대폰↔이메일 1:1 바인딩(로컬 mock)

// 응모 시 저장되는 개인정보를 받을 관리자(대행업체) 수신 이메일 — 임시값
export const ADMIN_EMAIL = 'jtaechul@gmail.com';

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; }
  catch { return null; }
}
function save(state) { localStorage.setItem(KEY, JSON.stringify(state)); }

// ---- 공개 API ----

export function getLocalState() { return load(); }

// 이메일 인증번호(OTP) 발송 — 프로토타입은 실제 발송 대신 devCode 반환.
// 규칙: 휴대폰 1개당 이메일 1개(1:1). 이미 다른 이메일/휴대폰에 묶였으면 차단.
export async function sendEmailOtp({ phone, email }) {
  if (MODE === 'worker') return workerFetch('/api/otp/send', { phone, email });
  phone = normalizePhone(phone);
  email = String(email).trim().toLowerCase();
  if (!isValidPhone(phone)) return { ok: false, error: 'BAD_PHONE' };
  if (!isEmail(email)) return { ok: false, error: 'BAD_EMAIL' };

  const bind = loadBind();
  if (bind.byPhone[phone] && bind.byPhone[phone] !== email)
    return { ok: false, error: 'PHONE_TAKEN', boundEmail: maskEmail(bind.byPhone[phone]) };
  if (bind.byEmail[email] && bind.byEmail[email] !== phone)
    return { ok: false, error: 'EMAIL_TAKEN' };

  const code = String(Math.floor(100000 + Math.random() * 900000));
  const otp = { phone, email, code, exp: Date.now() + 5 * 60 * 1000, tries: 0 };
  localStorage.setItem(OTP_KEY, JSON.stringify(otp));
  // 실제 발송 지점(P2): 서버가 email 로 code 발송.
  return { ok: true, devCode: code }; // devCode 는 프로토타입 데모용(실제 배포 시 제거)
}

export async function verifyEmailOtp({ email, code }) {
  if (MODE === 'worker') return workerFetch('/api/otp/verify', { email, code });
  email = String(email).trim().toLowerCase();
  let otp;
  try { otp = JSON.parse(localStorage.getItem(OTP_KEY)); } catch { otp = null; }
  if (!otp || otp.email !== email) return { ok: false, error: 'NO_OTP' };
  if (Date.now() > otp.exp) { localStorage.removeItem(OTP_KEY); return { ok: false, error: 'EXPIRED' }; }
  if (otp.tries >= 5) return { ok: false, error: 'TOO_MANY' };
  if (String(code).trim() !== otp.code) {
    otp.tries++; localStorage.setItem(OTP_KEY, JSON.stringify(otp));
    return { ok: false, error: 'MISMATCH', left: 5 - otp.tries };
  }
  // 성공 → 휴대폰↔이메일 1:1 바인딩 기록
  const bind = loadBind();
  bind.byPhone[otp.phone] = otp.email;
  bind.byEmail[otp.email] = otp.phone;
  saveBind(bind);
  localStorage.removeItem(OTP_KEY);
  localStorage.setItem('bst_verified', JSON.stringify({ phone: otp.phone, email: otp.email }));
  return { ok: true };
}

// 개인정보 동의 + 등록 (프로토타입: 로컬 저장만). 이메일 인증 완료가 전제.
export async function register({ name, phone, email, agreements }) {
  if (MODE === 'worker') return workerFetch('/api/register', { name, phone, email, agreements });
  phone = normalizePhone(phone);
  email = String(email).trim().toLowerCase();
  let verified;
  try { verified = JSON.parse(localStorage.getItem('bst_verified')); } catch { verified = null; }
  if (!verified || verified.phone !== phone || verified.email !== email)
    return { ok: false, error: 'EMAIL_NOT_VERIFIED' };

  const now = new Date().toISOString();
  const state = {
    name: name.trim(),
    phone, email, emailVerified: true,
    agreements: agreements || { privacy: true, terms: true, photo: true },
    agreedAt: now,
    stamps: {},   // { spotId: { at, distance } }
    photos: {},   // { spotId: { name, dataUrl, at } }
    entryNo: null, rank: null, firstComeClosed: false, finalizedAt: null,
    adminEmail: ADMIN_EMAIL,
  };
  save(state);
  return { ok: true };
}

// 방문 인증 기록 (프로토타입: 로컬)
export async function recordStamp(spotId, { distance }) {
  if (MODE === 'worker') return workerFetch('/api/stamp', { spotId, distance });
  const state = load();
  if (!state) return { ok: false, error: 'NO_PARTICIPANT' };
  if (!state.stamps[spotId]) {
    state.stamps[spotId] = { at: new Date().toISOString(), distance };
    save(state);
  }
  return { ok: true, stamps: Object.keys(state.stamps) };
}

// 사진 첨부 저장 (프로토타입: 축소된 dataUrl 을 로컬 보관. 실제로는 서버 업로드)
export async function savePhoto(spotId, { name, dataUrl }) {
  const state = load();
  if (!state) return { ok: false, error: 'NO_PARTICIPANT' };
  state.photos[spotId] = { name, dataUrl, at: new Date().toISOString() };
  try { save(state); } catch (e) { return { ok: false, error: 'STORAGE_FULL' }; }
  return { ok: true, count: Object.keys(state.photos).length };
}

export function getPhotos() {
  const state = load();
  return state ? state.photos || {} : {};
}

// 3/3 완주 시 응모 확정 → 선착순 순번 부여 + (예정) 관리자 이메일로 개인정보·사진 전송
export async function finalizeEntry() {
  if (MODE === 'worker') return workerFetch('/api/finalize', {});
  const state = load();
  if (!state) return { ok: false, error: 'NO_PARTICIPANT' };
  if (Object.keys(state.stamps).length < EVENT.requiredCount) return { ok: false, error: 'NOT_COMPLETE' };
  if (state.entryNo) return { ok: true, entryNo: state.entryNo, rank: state.rank, firstComeClosed: state.firstComeClosed, photoCount: Object.keys(state.photos).length };

  const rank = nextSeq();
  state.rank = rank;
  state.entryNo = makeEntryNo(rank);
  state.firstComeClosed = rank > EVENT.firstComeLimit;
  state.finalizedAt = new Date().toISOString();
  save(state);

  // 실제 전송 지점(P2): 서버가 ADMIN_EMAIL 로 {이름,연락처,이메일,응모번호,사진들} 발송.
  // 프로토타입은 콘솔 기록만.
  try {
    console.log('[MOCK] 관리자 이메일 전송 예정 →', ADMIN_EMAIL, {
      name: state.name, phone: state.phone, email: state.email,
      entryNo: state.entryNo, photos: Object.keys(state.photos),
    });
  } catch {}

  return { ok: true, entryNo: state.entryNo, rank, firstComeClosed: state.firstComeClosed, photoCount: Object.keys(state.photos).length };
}

// 재접속 조회: 이름 + 연락처 일치 확인
export async function lookupEntry({ name, phone }) {
  if (MODE === 'worker') return workerFetch('/api/lookup', { name, phone });
  const state = load();
  if (!state) return { ok: false, error: 'NOT_FOUND' };
  const match = state.name === name.trim() && state.phone === normalizePhone(phone);
  if (!match) return { ok: false, error: 'NOT_FOUND' };
  return {
    ok: true,
    stamps: Object.keys(state.stamps),
    total: EVENT.requiredCount,
    entryNo: state.entryNo, rank: state.rank, firstComeClosed: state.firstComeClosed,
    email: maskEmail(state.email),
  };
}

// (프로토타입 시연용) 로컬 데이터 초기화
export function resetLocal() {
  [KEY, OTP_KEY, 'bst_verified'].forEach((k) => localStorage.removeItem(k));
  // 바인딩(BIND_KEY)·선착순(SEQ_KEY)은 유지(중복/순번 시연). 완전 초기화는 아래 주석 해제.
  // localStorage.removeItem(BIND_KEY); localStorage.removeItem(SEQ_KEY);
}

// ---- 내부 유틸 ----
function normalizePhone(p) { return String(p).replace(/[^0-9]/g, ''); }
function isValidPhone(p) { return /^01[0-9]{8,9}$/.test(normalizePhone(p)); }
function isEmail(e) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(e).trim()); }
function maskEmail(e) {
  if (!e || !e.includes('@')) return e || '';
  const [id, dom] = e.split('@');
  const head = id.slice(0, Math.min(2, id.length));
  return `${head}${'*'.repeat(Math.max(1, id.length - 2))}@${dom}`;
}
function loadBind() {
  try { return JSON.parse(localStorage.getItem(BIND_KEY)) || { byPhone: {}, byEmail: {} }; }
  catch { return { byPhone: {}, byEmail: {} }; }
}
function saveBind(b) { localStorage.setItem(BIND_KEY, JSON.stringify(b)); }
function nextSeq() {
  const cur = parseInt(localStorage.getItem(SEQ_KEY) || '0', 10) + 1;
  localStorage.setItem(SEQ_KEY, String(cur));
  return cur;
}
function makeEntryNo(rank) {
  const year = new Date().getFullYear();
  return `BST-${year}-${String(rank).padStart(6, '0')}`;
}
async function workerFetch(path, body) {
  // P2 연동 지점.
  throw new Error('worker 모드는 아직 연결되지 않았습니다(P2).');
}
