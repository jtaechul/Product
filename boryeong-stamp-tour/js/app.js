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
init();

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

// ---------- 화면 1: 인트로 + 동의 + 입력 ----------
function renderIntro() {
  destroyMap();
  setProgress();
  root.innerHTML = `
    <section class="view intro">
      <div class="hero">
        <div class="hero-badge">가을 한정</div>
        <h1 class="hero-title">${esc(EVENT.title)}</h1>
        <p class="hero-sub">${esc(EVENT.subtitle)}</p>
        <ul class="hero-steps">
          <li><span class="stepn">1</span> 3개 관광지를 방문하고</li>
          <li><span class="stepn">2</span> 현장에서 '방문 인증'을 누르면</li>
          <li><span class="stepn">3</span> 3곳 완주 시 자동 응모 → 선착순 상품권</li>
        </ul>
        <p class="hero-meta">${esc(EVENT.periodText)}</p>
      </div>

      <form id="consentForm" class="card form" novalidate>
        <h2 class="card-title">참여자 정보</h2>

        <label class="field">
          <span class="field-label">이름</span>
          <input class="input" name="name" type="text" inputmode="text"
                 autocomplete="name" placeholder="홍길동" required maxlength="20" />
        </label>

        <label class="field">
          <span class="field-label">휴대폰 번호</span>
          <input class="input" name="phone" type="tel" inputmode="numeric"
                 autocomplete="tel" placeholder="010-1234-5678" required />
          <span class="field-hint">응모 확인·상품권 안내에 사용됩니다.</span>
        </label>

        <div class="consent">
          <label class="check">
            <input type="checkbox" name="agreeAll" />
            <span class="check-box"></span>
            <span class="check-text"><strong>전체 동의</strong></span>
          </label>
          <div class="consent-items">
            <label class="check">
              <input type="checkbox" name="agreePrivacy" required />
              <span class="check-box"></span>
              <span class="check-text">[필수] 개인정보 수집·이용 동의
                <button type="button" class="linkbtn" data-doc="privacy">보기</button></span>
            </label>
            <label class="check">
              <input type="checkbox" name="agreeTerms" required />
              <span class="check-box"></span>
              <span class="check-text">[필수] 이벤트 유의사항 동의
                <button type="button" class="linkbtn" data-doc="terms">보기</button></span>
            </label>
          </div>
        </div>

        <button type="submit" class="btn btn--primary btn--lg">동의하고 시작하기</button>
        <button type="button" class="btn btn--ghost" id="toLookup">이미 참여했어요 — 응모 조회</button>
      </form>

      <p class="privacy-note">
        수집 항목: 이름, 휴대폰번호 · 목적: 스탬프 투어 응모 및 상품권 지급 안내 ·
        보유기간: 행사 종료 후 지급 완료 시까지(이후 파기). 자세한 내용은 개인정보 처리방침을 확인하세요.
      </p>
    </section>
  `;

  const form = root.querySelector('#consentForm');
  const agreeAll = form.querySelector('[name=agreeAll]');
  const subChecks = [...form.querySelectorAll('[name=agreePrivacy],[name=agreeTerms]')];

  agreeAll.addEventListener('change', () => {
    subChecks.forEach((c) => (c.checked = agreeAll.checked));
  });
  subChecks.forEach((c) =>
    c.addEventListener('change', () => {
      agreeAll.checked = subChecks.every((x) => x.checked);
    })
  );

  form.querySelectorAll('.linkbtn').forEach((b) =>
    b.addEventListener('click', () => openDoc(b.dataset.doc))
  );

  root.querySelector('#toLookup').addEventListener('click', renderLookup);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = form.name.value.trim();
    const phone = form.phone.value.trim();
    if (name.length < 1) return toast('이름을 입력해 주세요.', 'warn');
    if (!isValidPhone(phone)) return toast('휴대폰 번호를 정확히 입력해 주세요.', 'warn');
    if (!subChecks.every((c) => c.checked)) return toast('필수 항목에 동의해 주세요.', 'warn');

    await api.register({ name, phone });
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

  root.innerHTML = `
    <section class="view mapview">
      <div id="map" class="map"></div>

      <div class="sheet">
        <div class="sheet-head">
          <h2 class="card-title">스탬프 (${stamped.size}/${EVENT.requiredCount})</h2>
          <span class="sheet-hint">관광지 반경 200m 안에서 인증하세요</span>
        </div>
        <ul class="spot-list">
          ${SPOTS.map((s) => spotRow(s, stamped.has(s.id))).join('')}
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

function spotRow(s, done) {
  return `
    <li class="spot-row ${done ? 'done' : ''}">
      <div class="spot-stamp" aria-hidden="true">${done ? '<span class="stamp-check"></span>' : ''}</div>
      <div class="spot-body">
        <div class="spot-name">${esc(s.name)}</div>
        <div class="spot-desc">${esc(s.desc)}</div>
      </div>
      <button class="btn btn--sm ${done ? 'btn--done' : 'btn--outline'}" data-spot="${s.id}">
        ${done ? '인증됨' : '방문 인증'}
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

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <button class="modal-close" aria-label="닫기">&times;</button>
      <h3 class="modal-title">${esc(s.name)}</h3>
      <p class="modal-desc">${esc(s.desc)}</p>
      ${done
        ? `<div class="verify-result ok">이미 인증을 완료한 곳입니다.</div>`
        : `<div class="verify-box" id="verifyBox">
             <p class="verify-guide">이 관광지 반경 <b>${s.radiusM}m</b> 안에서 아래 버튼을 눌러 주세요.</p>
             <div class="verify-status" id="verifyStatus" hidden></div>
             <button class="btn btn--primary btn--lg" id="verifyBtn">방문 인증하기</button>
           </div>`}
    </div>
  `;
  document.body.appendChild(overlay);
  const close = () => overlay.remove();
  overlay.querySelector('.modal-close').addEventListener('click', close);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });

  if (!done) {
    overlay.querySelector('#verifyBtn').addEventListener('click', () => verifyAt(s, overlay));
  }
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
    statusEl.innerHTML = `인증 완료! (${distance}m) 🎉`.replace('🎉', '');
    btn.textContent = '인증 완료';
    setProgress();
    toast(`${spot.name} 인증 완료!`, 'ok');

    setTimeout(() => {
      overlay.remove();
      const state = api.getLocalState();
      if (Object.keys(state.stamps).length >= EVENT.requiredCount) {
        // 자동 응모 확정 흐름으로 이동
        doFinalize();
      } else {
        renderMap();
      }
    }, 900);
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
