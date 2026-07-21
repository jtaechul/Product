// 백엔드 호출 래퍼.
// 프로토타입(P1)은 localStorage 기반 MOCK 으로 동작합니다.
// ⚠️ 프로토타입에서는 실제 개인정보를 서버로 전송/저장하지 않습니다(브라우저 로컬에만 보관).
//    실제 암호화 저장·선착순·조회는 P2에서 Cloudflare Workers 엔드포인트로 교체합니다.
//    교체 시 MODE 를 'worker' 로 바꾸고 workerFetch 구현부를 연결하면 됩니다.

import { EVENT } from './spots.js';

const MODE = 'mock'; // 'mock' | 'worker'
const KEY = 'bst_v1';           // 참가자 개인 상태(로컬)
const SEQ_KEY = 'bst_seq_v1';   // 선착순 순번(로컬 mock 전용)

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || null; }
  catch { return null; }
}
function save(state) {
  localStorage.setItem(KEY, JSON.stringify(state));
}

// ---- 공개 API ----

export function getLocalState() {
  return load();
}

// 개인정보 동의 + 등록 (프로토타입: 로컬 저장만)
export async function register({ name, phone }) {
  if (MODE === 'worker') return workerFetch('/api/register', { name, phone });
  const now = new Date().toISOString();
  const state = {
    name: name.trim(),
    phone: normalizePhone(phone),
    agreedAt: now,
    stamps: {},        // { spotId: { at, distance } }
    entryNo: null,
    rank: null,
    firstComeClosed: false,
    finalizedAt: null,
  };
  save(state);
  return { ok: true };
}

// 방문 인증 기록 (프로토타입: 로컬. 실제로는 서버가 좌표 재검증)
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

// 3/3 완주 시 응모 확정 → 선착순 순번 부여
export async function finalizeEntry() {
  if (MODE === 'worker') return workerFetch('/api/finalize', {});
  const state = load();
  if (!state) return { ok: false, error: 'NO_PARTICIPANT' };
  if (Object.keys(state.stamps).length < EVENT.requiredCount) {
    return { ok: false, error: 'NOT_COMPLETE' };
  }
  if (state.entryNo) {
    // 이미 응모됨(중복 방지)
    return { ok: true, entryNo: state.entryNo, rank: state.rank, firstComeClosed: state.firstComeClosed };
  }
  const rank = nextSeq();
  state.rank = rank;
  state.entryNo = makeEntryNo(rank);
  state.firstComeClosed = rank > EVENT.firstComeLimit;
  state.finalizedAt = new Date().toISOString();
  save(state);
  return { ok: true, entryNo: state.entryNo, rank, firstComeClosed: state.firstComeClosed };
}

// 재접속 조회: 이름 + 연락처 일치 확인 (프로토타입: 로컬 대조)
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
    entryNo: state.entryNo,
    rank: state.rank,
    firstComeClosed: state.firstComeClosed,
  };
}

// (프로토타입 시연용) 로컬 데이터 초기화
export function resetLocal() {
  localStorage.removeItem(KEY);
}

// ---- 내부 유틸 ----

function normalizePhone(p) {
  return String(p).replace(/[^0-9]/g, '');
}

function nextSeq() {
  const cur = parseInt(localStorage.getItem(SEQ_KEY) || '0', 10) + 1;
  localStorage.setItem(SEQ_KEY, String(cur));
  return cur;
}

function makeEntryNo(rank) {
  // 예: BST-2026-000123
  const year = new Date().getFullYear();
  return `BST-${year}-${String(rank).padStart(6, '0')}`;
}

async function workerFetch(path, body) {
  // P2 연동 지점. 예:
  // const res = await fetch(WORKER_BASE + path, {
  //   method: 'POST', headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify(body),
  // });
  // return res.json();
  throw new Error('worker 모드는 아직 연결되지 않았습니다(P2).');
}
