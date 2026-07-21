// 보령 가을愛 스탬프 투어 — 앱 로직(화면 전환/흐름)
import { EVENT, SPOTS, getSpot } from './spots.js';
import { getCurrentPosition, checkWithin } from './geo.js';
import * as api from './api.js';

const root = document.getElementById('viewRoot');
const progressPill = document.getElementById('progressPill');
const progressCount = document.getElementById('progressCount');

let map = null;
let markers = {};
// 테스트 모드: 실제로 현장에 갈 수 없는 개발 환경에서 흐름을 확인하기 위한 옵션.
// 켜면 위치 확인 시 해당 지점 좌표로 시뮬레이션합니다. (배포 전 반드시 기본 OFF)
let testMode = false;

// ---------- 진입 ----------
function init() {
  const state = api.getLocalState();
  if (state && state.entryNo) {
    renderComplete(state);
  } else if (state && state.name) {
    renderMap();
  } else {
    renderIntro();
  }
}

// ---------- 공용 ----------
function setProgress() {
  const state = api.getLocalState();
  const n = state ? Object.keys(state.stamps || {}).length : 0;
  progressCount.textContent = n;
  progressPill.hidden = !(state && state.name);
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function toast(msg, kind = 'info') {
  const t = document.createElement('div');
  t.className = `toast toast--${kind}`;
  t.textContent = msg;
  document.body.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => {
    t.classList.remove('show');
    setTimeout(() => t.remove(), 300);
  }, 2600);
}

// 동의 상세 문안(자동 표시)
const DOC_PRIVACY = `
  <p><b>수집 항목</b> 이름, 휴대폰번호, 이메일, 방문 인증 사진</p>
  <p><b>수집·이용 목적</b> 스탬프 투어 응모 접수·본인확인·선착순 확인, 지역사랑상품권 지급 안내</p>
  <p><b>보유·이용 기간</b> 행사 종료 및 상품권 지급 완료 시까지(이후 지체 없이 파기)</p>
  <p><b>동의 거부 권리</b> 동의를 거부할 수 있으나, 거부 시 이벤트 참여가 제한됩니다.</p>`;
const DOC_TERMS = `
  <p>· 1인 1회 응모(중복 응모는 무효 처리될 수 있습니다).</p>
  <p>· 위치정보 조작 등 부정한 방법으로 인증한 경우 응모가 취소됩니다.</p>
  <p>· 상품권은 선착순으로 지급되며, 소진 시 마감됩니다.</p>
  <p>· 상품권 지급 시 본인확인이 필요할 수 있습니다.</p>`;
const DOC_PHOTO = `
  <p><b>수집 항목</b> 각 관광지 방문 인증 사진</p>
  <p><b>이용 목적</b> 방문 사실 확인 및 이벤트 운영. 완주 시 운영자(관리자) 이메일로 접수됩니다.</p>
  <p><b>보유 기간</b> 행사 종료 및 확인 완료 후 파기. 홍보 등 다른 목적으로 사용하지 않습니다.</p>`;
const CONSENT_DOCS = {
  privacy: { title: '개인정보 수집·이용 동의', html: DOC_PRIVACY },
  terms: { title: '이벤트 유의사항 동의', html: DOC_TERMS },
  photo: { title: '사진 수집·이용 동의', html: DOC_PHOTO },
};

function isEmail(e) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(e).trim()); }

// 사진을 축소해 dataURL 로 변환(용량 절감)
function downscaleImage(file, maxSize = 1024, quality = 0.7) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      let { width, height } = img;
      const m = Math.max(width, height);
      if (m > maxSize) { const r = maxSize / m; width = Math.round(width * r); height = Math.round(height * r); }
      const c = document.createElement('canvas');
      c.width = width; c.height = height;
      c.getContext('2d').drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', quality));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('이미지를 읽지 못했습니다.')); };
    img.src = url;
  });
}

// ---------- 화면 1: 인트로 + 이메일 인증 + 자동 동의 ----------
function renderIntro() {
  destroyMap();
  setProgress();
  let emailVerified = false;

  const consentBlock = (id, title, html) => `
    <div class="consent-block">
      <label class="check">
        <input type="checkbox" name="agree_${id}" checked />
        <span class="check-box"></span>
        <span class="check-text"><strong>${title}</strong></span>
      </label>
      <div class="consent-detail">${html}</div>
    </div>`;

  root.innerHTML = `
    <section class="view intro">
      <div class="hero">
        <div class="hero-badge">가을 한정</div>
        <h1 class="hero-title">${esc(EVENT.title)}</h1>
        <p class="hero-sub">${esc(EVENT.subtitle)}</p>
        <ul class="hero-steps">
          <li><span class="stepn">1</span> 3개 관광지를 방문하고</li>
          <li><span class="stepn">2</span> '방문 인증'과 '사진 인증'을 하면</li>
          <li><span class="stepn">3</span> 3곳 완주 시 자동 응모 → 선착순 상품권</li>
        </ul>
        <p class="hero-meta">${esc(EVENT.periodText)}</p>
      </div>

      <form id="consentForm" class="card form" novalidate>
        <h2 class="card-title">참여자 정보</h2>

        <label class="field">
          <span class="field-label">이름</span>
          <input class="input" name="name" type="text" autocomplete="name" placeholder="홍길동" required maxlength="20" />
        </label>

        <label class="field">
          <span class="field-label">휴대폰 번호</span>
          <input class="input" name="phone" type="tel" inputmode="numeric" autocomplete="tel" placeholder="010-1234-5678" required />
          <span class="field-hint">휴대폰 1개당 이메일 1개만 인증할 수 있어요.</span>
        </label>

        <div class="field">
          <span class="field-label">이메일 (인증 필요)</span>
          <div class="email-row">
            <input class="input" name="email" type="email" inputmode="email" autocomplete="email" placeholder="you@example.com" required />
            <button type="button" class="btn btn--outline btn--sm" id="otpSend">인증번호 받기</button>
          </div>
          <div id="otpArea" hidden>
            <div class="otp-row">
              <input class="input" id="otpInput" inputmode="numeric" maxlength="6" placeholder="인증번호 6자리" />
              <button type="button" class="btn btn--outline btn--sm" id="otpVerify">확인</button>
            </div>
            <div id="otpMsg" class="otp-msg"></div>
          </div>
          <div id="emailBadge" class="verified-badge" hidden>이메일 인증 완료</div>
        </div>

        <div class="consent">
          <div class="consent-head">약관 동의<span class="consent-auto">상세 내역 자동 표시 · 기본 동의</span></div>
          ${consentBlock('privacy', '[필수] 개인정보 수집·이용 동의', DOC_PRIVACY)}
          ${consentBlock('terms', '[필수] 이벤트 유의사항 동의', DOC_TERMS)}
          ${consentBlock('photo', '[필수] 사진 수집·이용 동의', DOC_PHOTO)}
        </div>

        <button type="submit" class="btn btn--primary btn--lg" id="startBtn" disabled>동의하고 시작하기</button>
        <button type="button" class="btn btn--ghost" id="toLookup">이미 참여했어요 — 응모 조회</button>
      </form>

      <p class="privacy-note">
        수집 항목: 이름, 휴대폰번호, 이메일, 방문 인증 사진 · 목적: 스탬프 투어 응모 및 상품권 지급 안내 ·
        보유기간: 행사 종료 후 지급 완료 시까지(이후 파기). 수집 정보는 운영자 이메일(${esc(api.ADMIN_EMAIL)})로 접수됩니다.
      </p>
    </section>
  `;

  const form = root.querySelector('#consentForm');
  const emailInput = form.querySelector('[name=email]');
  const phoneInput = form.querySelector('[name=phone]');
  const otpSend = root.querySelector('#otpSend');
  const otpArea = root.querySelector('#otpArea');
  const otpInput = root.querySelector('#otpInput');
  const otpVerify = root.querySelector('#otpVerify');
  const otpMsg = root.querySelector('#otpMsg');
  const emailBadge = root.querySelector('#emailBadge');
  const startBtn = root.querySelector('#startBtn');
  const consents = [...form.querySelectorAll('[name^=agree_]')];

  const allConsented = () => consents.every((c) => c.checked);
  const updateStart = () => { startBtn.disabled = !(emailVerified && allConsented()); };
  consents.forEach((c) => c.addEventListener('change', updateStart));

  const resetVerified = () => {
    if (!emailVerified && otpArea.hidden) return;
    emailVerified = false;
    emailBadge.hidden = true;
    otpArea.hidden = true;
    otpMsg.textContent = '';
    emailInput.disabled = false;
    updateStart();
  };
  emailInput.addEventListener('input', resetVerified);
  phoneInput.addEventListener('input', resetVerified);

  otpSend.addEventListener('click', async () => {
    const phone = phoneInput.value.trim();
    const email = emailInput.value.trim();
    if (!isValidPhone(phone)) return toast('휴대폰 번호를 먼저 정확히 입력해 주세요.', 'warn');
    if (!isEmail(email)) return toast('이메일을 정확히 입력해 주세요.', 'warn');
    otpSend.disabled = true; otpSend.textContent = '발송 중...';
    const res = await api.sendEmailOtp({ phone, email });
    otpSend.disabled = false; otpSend.textContent = '인증번호 재발송';
    if (!res.ok) {
      const map = {
        PHONE_TAKEN: `이 휴대폰 번호는 이미 다른 이메일(${res.boundEmail || ''})로 인증되었습니다.`,
        EMAIL_TAKEN: '이 이메일은 이미 다른 휴대폰 번호로 인증되었습니다.',
        BAD_PHONE: '휴대폰 번호를 확인해 주세요.',
        BAD_EMAIL: '이메일을 확인해 주세요.',
      };
      return toast(map[res.error] || '인증번호 발송에 실패했습니다.', 'err');
    }
    otpArea.hidden = false;
    otpInput.focus();
    // 데모: 실제 이메일 발송 대신 화면에 인증번호를 표시(실제 배포 시 제거)
    otpMsg.className = 'otp-msg demo';
    otpMsg.innerHTML = `데모용 인증번호: <b>${res.devCode}</b> <span class="otp-sub">(실제 서비스에선 이메일로 발송됩니다)</span>`;
  });

  otpVerify.addEventListener('click', async () => {
    const email = emailInput.value.trim();
    const code = otpInput.value.trim();
    if (code.length < 6) return toast('인증번호 6자리를 입력해 주세요.', 'warn');
    const res = await api.verifyEmailOtp({ email, code });
    if (!res.ok) {
      const map = {
        MISMATCH: `인증번호가 일치하지 않습니다. (남은 시도 ${res.left ?? ''}회)`,
        EXPIRED: '인증번호가 만료되었습니다. 다시 받아 주세요.',
        TOO_MANY: '시도 횟수를 초과했습니다. 다시 받아 주세요.',
        NO_OTP: '먼저 인증번호를 받아 주세요.',
      };
      otpMsg.className = 'otp-msg err';
      otpMsg.textContent = map[res.error] || '인증에 실패했습니다.';
      return;
    }
    emailVerified = true;
    otpArea.hidden = true;
    emailBadge.hidden = false;
    emailInput.disabled = true;
    otpSend.disabled = true;
    updateStart();
    toast('이메일 인증이 완료되었어요.', 'ok');
  });

  root.querySelector('#toLookup').addEventListener('click', renderLookup);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = form.name.value.trim();
    const phone = phoneInput.value.trim();
    const email = emailInput.value.trim();
    if (name.length < 1) return toast('이름을 입력해 주세요.', 'warn');
    if (!isValidPhone(phone)) return toast('휴대폰 번호를 정확히 입력해 주세요.', 'warn');
    if (!emailVerified) return toast('이메일 인증을 먼저 완료해 주세요.', 'warn');
    if (!allConsented()) return toast('필수 항목에 동의해 주세요.', 'warn');

    const res = await api.register({
      name, phone, email,
      agreements: { privacy: true, terms: true, photo: true },
    });
    if (!res.ok) return toast('등록에 실패했습니다. 이메일 인증을 다시 확인해 주세요.', 'err');
    toast('참여가 시작되었어요. 첫 스탬프를 모으러 가볼까요?', 'ok');
    renderMap();
  });
}

function isValidPhone(p) {
  const digits = p.replace(/[^0-9]/g, '');
  return /^01[0-9]{8,9}$/.test(digits);
}

// ---------- 화면 2: 지도 + 스탬프 목록 ----------
function renderMap() {
  setProgress();
  const state = api.getLocalState();
  const stamped = new Set(Object.keys(state?.stamps || {}));
  const photoed = new Set(Object.keys(state?.photos || {}));

  root.innerHTML = `
    <section class="view mapview">
      <div id="map" class="map"></div>

      <div class="sheet">
        <div class="sheet-head">
          <h2 class="card-title">스탬프 (${stamped.size}/${EVENT.requiredCount})</h2>
          <span class="sheet-hint">반경 200m 방문 인증 + 사진 첨부</span>
        </div>
        <ul class="spot-list">
          ${SPOTS.map((s) => spotRow(s, stamped.has(s.id), photoed.has(s.id))).join('')}
        </ul>
        ${stamped.size >= EVENT.requiredCount
          ? `<button class="btn btn--primary btn--lg" id="toFinalize">응모 완료하기</button>`
          : ''}
      </div>

      <button class="test-toggle ${testMode ? 'on' : ''}" id="testToggle"
              title="개발/테스트용: 현장에 없어도 인증 흐름을 시연합니다">
        테스트 모드 ${testMode ? 'ON' : 'OFF'}
      </button>
    </section>
  `;

  // 지도는 부가 요소 — 실패해도 인증 흐름은 계속 동작해야 하므로 리스너보다 먼저/독립 처리
  try { initMap(stamped); } catch (e) { showMapFallback(); }

  root.querySelectorAll('[data-spot]').forEach((btn) =>
    btn.addEventListener('click', () => openSpotSheet(btn.dataset.spot))
  );

  const fin = root.querySelector('#toFinalize');
  if (fin) fin.addEventListener('click', doFinalize);

  root.querySelector('#testToggle').addEventListener('click', () => {
    testMode = !testMode;
    renderMap();
    toast(testMode ? '테스트 모드 ON (배포 전 꺼주세요)' : '테스트 모드 OFF', testMode ? 'warn' : 'info');
  });
}

function spotRow(s, done, hasPhoto) {
  return `
    <li class="spot-row ${done ? 'done' : ''}">
      <div class="spot-stamp" aria-hidden="true">${done ? '<span class="stamp-check"></span>' : ''}</div>
      <div class="spot-body">
        <div class="spot-name">${esc(s.name)}</div>
        <div class="spot-tags">
          <span class="tag ${done ? 'tag--on' : ''}">방문 ${done ? '완료' : '대기'}</span>
          <span class="tag ${hasPhoto ? 'tag--on' : ''}">사진 ${hasPhoto ? '첨부' : '미첨부'}</span>
        </div>
      </div>
      <button class="btn btn--sm ${done ? 'btn--done' : 'btn--outline'}" data-spot="${s.id}">
        ${done ? '열기' : '인증하기'}
      </button>
    </li>
  `;
}

function showMapFallback() {
  const el = document.getElementById('map');
  if (el) {
    el.innerHTML = `<div class="map-fallback">지도를 불러오지 못했습니다. 아래 목록에서 방문 인증을 진행하세요.</div>`;
  }
}

function initMap(stamped) {
  if (!window.L) { showMapFallback(); return; }
  destroyMap();
  const center = [
    SPOTS.reduce((a, s) => a + s.lat, 0) / SPOTS.length,
    SPOTS.reduce((a, s) => a + s.lng, 0) / SPOTS.length,
  ];
  map = L.map('map', { zoomControl: true, attributionControl: true }).setView(center, 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap',
  }).addTo(map);

  const group = [];
  SPOTS.forEach((s) => {
    const done = stamped.has(s.id);
    const m = L.circleMarker([s.lat, s.lng], {
      radius: 10,
      color: done ? '#2f9e44' : '#b5451f',
      fillColor: done ? '#69db7c' : '#ff922b',
      fillOpacity: 0.9,
      weight: 3,
    }).addTo(map);
    m.bindPopup(`<b>${esc(s.name)}</b><br>${done ? '인증 완료' : '반경 200m 안에서 인증'}`);
    L.circle([s.lat, s.lng], { radius: s.radiusM, color: '#b5451f', weight: 1, opacity: 0.35, fillOpacity: 0.05 }).addTo(map);
    m.on('click', () => openSpotSheet(s.id));
    markers[s.id] = m;
    group.push([s.lat, s.lng]);
  });
  if (group.length) map.fitBounds(group, { padding: [50, 50] });
  setTimeout(() => map && map.invalidateSize(), 100);
}

function destroyMap() {
  if (map) { map.remove(); map = null; markers = {}; }
}

// ---------- 스탬프 인증 시트 ----------
function openSpotSheet(spotId) {
  const s = getSpot(spotId);
  if (!s) return;
  const state = api.getLocalState();
  const done = !!state?.stamps?.[spotId];
  const photo = state?.photos?.[spotId];

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <button class="modal-close" aria-label="닫기">&times;</button>
      <h3 class="modal-title">${esc(s.name)}</h3>
      <p class="modal-desc">${esc(s.desc)}</p>

      <div class="verify-section">
        <div class="vs-title">1. 방문 인증 (위치)</div>
        ${done
          ? `<div class="verify-result ok">방문 인증 완료</div>`
          : `<div class="verify-box">
               <p class="verify-guide">이 관광지 반경 <b>${s.radiusM}m</b> 안에서 눌러 주세요.</p>
               <div class="verify-status" id="verifyStatus" hidden></div>
               <button class="btn btn--primary btn--lg" id="verifyBtn">방문 인증하기</button>
             </div>`}
      </div>

      <div class="verify-section">
        <div class="vs-title">2. 사진 인증 (첨부)</div>
        <p class="verify-guide">방문한 모습을 사진으로 첨부하면 완주 시 함께 접수됩니다.</p>
        <input type="file" accept="image/*" capture="environment" id="photoInput" hidden />
        <div id="photoPreview">${photo
          ? `<img class="photo-thumb" src="${photo.dataUrl}" alt="첨부한 사진" /><div class="photo-name">첨부됨: ${esc(photo.name)}</div>`
          : ''}</div>
        <button class="btn btn--outline" id="photoBtn">${photo ? '사진 다시 첨부' : '사진 인증하기 (첨부)'}</button>
        <div class="verify-status" id="photoStatus" hidden></div>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector('.modal-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  const vbtn = overlay.querySelector('#verifyBtn');
  if (vbtn) vbtn.addEventListener('click', () => verifyAt(s, overlay));

  // 사진 첨부
  const photoInput = overlay.querySelector('#photoInput');
  const photoBtn = overlay.querySelector('#photoBtn');
  const photoStatus = overlay.querySelector('#photoStatus');
  const photoPreview = overlay.querySelector('#photoPreview');
  photoBtn.addEventListener('click', () => photoInput.click());
  photoInput.addEventListener('change', async () => {
    const file = photoInput.files && photoInput.files[0];
    if (!file) return;
    photoStatus.hidden = false;
    photoStatus.className = 'verify-status';
    photoStatus.textContent = '사진 처리 중...';
    try {
      const dataUrl = await downscaleImage(file);
      const res = await api.savePhoto(s.id, { name: file.name, dataUrl });
      if (!res.ok) throw new Error(res.error === 'STORAGE_FULL' ? '저장 공간이 부족합니다. 더 작은 사진을 사용해 주세요.' : '사진 저장 실패');
      photoPreview.innerHTML = `<img class="photo-thumb" src="${dataUrl}" alt="첨부한 사진" /><div class="photo-name">첨부됨: ${esc(file.name)}</div>`;
      photoBtn.textContent = '사진 다시 첨부';
      photoStatus.className = 'verify-status ok';
      photoStatus.textContent = '사진이 첨부되었습니다.';
      toast(`${s.name} 사진 첨부 완료`, 'ok');
    } catch (err) {
      photoStatus.className = 'verify-status err';
      photoStatus.textContent = err.message || '사진 처리에 실패했습니다.';
    }
  });
}

async function verifyAt(spot, overlay) {
  const btn = overlay.querySelector('#verifyBtn');
  const statusEl = overlay.querySelector('#verifyStatus');
  btn.disabled = true;
  btn.textContent = '위치 확인 중...';
  statusEl.hidden = false;
  statusEl.className = 'verify-status';
  statusEl.textContent = '현재 위치를 확인하고 있어요.';

  try {
    let pos;
    if (testMode) {
      // 테스트 모드: 지점 근처(약 50m 이내)로 시뮬레이션
      pos = { lat: spot.lat + 0.0003, lng: spot.lng + 0.0002, accuracy: 20 };
    } else {
      pos = await getCurrentPosition();
    }
    const { inside, distance } = checkWithin(spot, pos);
    if (!inside) {
      statusEl.className = 'verify-status warn';
      statusEl.innerHTML = `아직 도착하지 않았어요. 현재 약 <b>${distance}m</b> 떨어져 있습니다. (반경 ${spot.radiusM}m 안에서 인증)`;
      btn.disabled = false;
      btn.textContent = '다시 인증하기';
      return;
    }
    await api.recordStamp(spot.id, { distance });
    statusEl.className = 'verify-status ok';
    statusEl.textContent = `방문 인증 완료! (${distance}m)`;
    btn.textContent = '인증 완료';
    btn.disabled = true;
    setProgress();
    toast(`${spot.name} 방문 인증 완료!`, 'ok');

    // 사진 첨부 기회를 위해 자동 응모하지 않고, 지도로 돌아가 '응모 완료하기' 버튼을 노출
    setTimeout(() => { overlay.remove(); renderMap(); }, 900);
  } catch (err) {
    statusEl.className = 'verify-status err';
    statusEl.textContent = err?.message || '위치 확인에 실패했습니다.';
    btn.disabled = false;
    btn.textContent = '다시 인증하기';
  }
}

// ---------- 응모 확정 ----------
async function doFinalize() {
  const res = await api.finalizeEntry();
  if (!res.ok) {
    toast('응모 처리에 실패했습니다. 다시 시도해 주세요.', 'err');
    return;
  }
  renderComplete(api.getLocalState());
}

// ---------- 화면 3: 완료 ----------
function renderComplete(state) {
  destroyMap();
  setProgress();
  const closed = state.firstComeClosed;
  root.innerHTML = `
    <section class="view complete">
      <div class="complete-card">
        <div class="complete-mark" aria-hidden="true"></div>
        <h1 class="complete-title">응모가 완료되었어요!</h1>
        <p class="complete-sub">세 곳의 스탬프를 모두 모았습니다. 참여해 주셔서 감사합니다.</p>

        <div class="entry-box">
          <div class="entry-label">응모번호</div>
          <div class="entry-no">${esc(state.entryNo)}</div>
          <div class="entry-rank">선착순 ${state.rank}번째 응모</div>
        </div>

        <div class="notice ${closed ? 'notice--warn' : 'notice--ok'}">
          ${closed
            ? '선착순 인원이 마감되어 대기 순번으로 접수되었습니다. 잔여 발생 시 순번대로 안내드립니다.'
            : '선착순 대상에 포함되었습니다. 상품권은 안내 절차에 따라 지급됩니다.'}
        </div>

        <div class="notice notice--ok" style="margin-top:10px">
          응모 정보와 첨부 사진 ${Object.keys(state.photos || {}).length}장이
          운영자 이메일(${esc(state.adminEmail || api.ADMIN_EMAIL)})로 접수됩니다.
        </div>

        <p class="complete-hint">이 화면은 언제든 <b>응모 조회</b>에서 다시 확인할 수 있어요.</p>
        <button class="btn btn--outline btn--lg" id="againLookup">응모 내역 조회</button>
      </div>
      <button class="btn btn--ghost btn--sm reset-btn" id="resetBtn">처음부터(테스트 초기화)</button>
    </section>
  `;
  root.querySelector('#againLookup').addEventListener('click', renderLookup);
  root.querySelector('#resetBtn').addEventListener('click', () => {
    if (confirm('로컬 저장 데이터를 지우고 처음부터 시작할까요? (테스트용)')) {
      api.resetLocal();
      renderIntro();
    }
  });
}

// ---------- 화면 4: 응모 조회 ----------
function renderLookup() {
  destroyMap();
  progressPill.hidden = true;
  root.innerHTML = `
    <section class="view lookup">
      <div class="card">
        <h2 class="card-title">응모 내역 조회</h2>
        <p class="card-sub">참여 시 입력한 이름과 휴대폰 번호로 진행 상황을 확인합니다.</p>
        <form id="lookupForm" novalidate>
          <label class="field">
            <span class="field-label">이름</span>
            <input class="input" name="name" type="text" placeholder="홍길동" required />
          </label>
          <label class="field">
            <span class="field-label">휴대폰 번호</span>
            <input class="input" name="phone" type="tel" inputmode="numeric" placeholder="010-1234-5678" required />
          </label>
          <button type="submit" class="btn btn--primary btn--lg">조회하기</button>
          <button type="button" class="btn btn--ghost" id="backHome">뒤로</button>
        </form>
        <div id="lookupResult"></div>
      </div>
    </section>
  `;
  root.querySelector('#backHome').addEventListener('click', init);
  const form = root.querySelector('#lookupForm');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const res = await api.lookupEntry({ name: form.name.value, phone: form.phone.value });
    const box = root.querySelector('#lookupResult');
    if (!res.ok) {
      box.innerHTML = `<div class="notice notice--warn">일치하는 응모 내역이 없습니다. 이름과 번호를 확인해 주세요.</div>`;
      return;
    }
    const done = res.stamps.length;
    box.innerHTML = `
      <div class="lookup-card">
        <div class="lookup-row"><span>진행</span><b>${done}/${res.total} 인증</b></div>
        ${res.entryNo
          ? `<div class="lookup-row"><span>응모번호</span><b>${esc(res.entryNo)}</b></div>
             <div class="lookup-row"><span>선착순</span><b>${res.rank}번째${res.firstComeClosed ? ' (대기)' : ''}</b></div>`
          : `<div class="notice notice--ok">아직 응모 전이에요. 남은 스탬프를 모으면 자동 응모됩니다.</div>`}
      </div>
    `;
  });
}

// ---------- 문서 뷰(동의서/유의사항 요약) ----------
function openDoc(kind) {
  const docs = {
    privacy: {
      title: '개인정보 수집·이용 동의',
      html: `
        <p><b>1. 수집 항목</b><br>이름, 휴대폰 번호, 스탬프 인증·응모 기록</p>
        <p><b>2. 수집·이용 목적</b><br>스탬프 투어 응모 접수, 선착순 확인, 지역사랑상품권 지급 안내</p>
        <p><b>3. 보유·이용 기간</b><br>행사 종료 및 상품권 지급 완료 시까지. 이후 지체 없이 파기합니다.</p>
        <p><b>4. 동의 거부 권리</b><br>동의를 거부할 수 있으나, 이 경우 이벤트 참여가 제한됩니다.</p>
        <p><b>5. 처리 위탁</b><br>행사 운영·상품권 지급을 위해 대행업체에 위탁될 수 있으며, 수탁자·위탁내용은 처리방침에 고지합니다.</p>
        <p class="doc-mini">※ 개인정보는 서버에 암호화되어 저장되며, 원문을 이메일 등으로 외부에 전송하지 않습니다.</p>
      `,
    },
    terms: {
      title: '이벤트 유의사항',
      html: `
        <p>· 1인 1회 응모(중복 응모는 무효 처리될 수 있습니다).</p>
        <p>· 위치정보 조작 등 부정한 방법으로 인증한 경우 응모가 취소됩니다.</p>
        <p>· 상품권은 선착순으로 지급되며, 소진 시 마감됩니다.</p>
        <p>· 상품권 지급 시 본인확인이 필요할 수 있습니다.</p>
        <p>· 상세 기간·경품 규모 등은 공식 안내를 따릅니다.</p>
      `,
    },
  };
  const d = docs[kind];
  if (!d) return;
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <button class="modal-close" aria-label="닫기">&times;</button>
      <h3 class="modal-title">${d.title}</h3>
      <div class="doc-body">${d.html}</div>
      <button class="btn btn--primary btn--lg" id="docOk">확인</button>
    </div>
  `;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector('.modal-close').addEventListener('click', close);
  overlay.querySelector('#docOk').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
}

// 모든 선언 초기화 후 마지막에 진입
init();
