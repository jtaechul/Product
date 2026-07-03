// 플랫폼 어댑터 (토스 앱인토스 대응).
// - 토스앱(WebView) 안: vendor/apps-in-toss.min.mjs(공식 SDK 번들)로 네이티브 저장소·게임로그인·
//   리더보드·행동로그·Safe Area를 사용한다. (앱인토스 게임 필수 SDK 5종)
// - 일반 브라우저(GitHub Pages): localStorage 폴백. SDK는 아예 로드하지 않는다.
//
// 저장소 동기화 전략: 토스 Storage API는 비동기(Promise)지만 게임 코드는 동기 호출을 기대한다.
// → 부팅 시 initPlatform()이 필요한 키를 전부 메모리 캐시로 읽어오고(hydrate),
//   이후 읽기는 캐시에서 동기 반환, 쓰기는 캐시 갱신 + 비동기 반영(fire-and-forget).

// 게임이 쓰는 저장 키 전체 (여기에 등록해야 토스 저장소에서 미리 읽어온다)
const KEYS = ["spotlight_save", "spotlight_audio", "spotlight_ending_dex"];

// 토스 앱 WebView 감지: 앱인토스 브리지는 ReactNativeWebView로 통신한다.
export const isInToss = typeof window !== "undefined" && !!window.ReactNativeWebView;

let sdk = null;                 // 토스 SDK 모듈 (토스 안에서만 로드됨)
const cache = new Map();        // 저장소 메모리 캐시
let nativeInsets = { top: 0, bottom: 0 }; // 토스가 알려준 안전영역(노치·홈바)

// ms 안에 끝나지 않으면 포기하는 가드 — 브리지가 멈춰도 부팅(10초 규정)을 막지 않게
function withTimeout(promise, ms) {
  return Promise.race([promise, new Promise((res) => setTimeout(() => res(undefined), ms))]);
}

// 부팅 시 1회 호출. 실패해도 게임은 켜져야 하므로 절대 throw하지 않는다.
export async function initPlatform() {
  if (!isInToss) {
    for (const k of KEYS) {
      try { const v = localStorage.getItem(k); if (v != null) cache.set(k, v); } catch (e) {}
    }
    return;
  }
  try {
    sdk = await import("../../vendor/apps-in-toss.min.mjs");
    // 저장 키 hydrate + 안전영역 조회 (개별 실패 허용)
    await withTimeout(Promise.all([
      ...KEYS.map(async (k) => {
        try { const v = await sdk.Storage.getItem(k); if (v != null) cache.set(k, v); } catch (e) {}
      }),
      (async () => {
        try {
          const ins = await sdk.getSafeAreaInsets();
          if (ins) nativeInsets = { top: ins.top || 0, bottom: ins.bottom || 0 };
        } catch (e) {}
      })(),
    ]), 4000);
  } catch (e) {
    console.warn("[platform] 토스 SDK 초기화 실패(웹 폴백으로 진행):", e);
    sdk = null;
    for (const k of KEYS) {
      try { const v = localStorage.getItem(k); if (v != null) cache.set(k, v); } catch (e2) {}
    }
  }
}

// ── 저장소 (동기 파사드) ─────────────────────────────────────────────
export function storageGet(key) {
  return cache.has(key) ? cache.get(key) : null;
}
export function storageSet(key, value) {
  cache.set(key, value);
  if (sdk) sdk.Storage.setItem(key, value).catch(() => {});
  else { try { localStorage.setItem(key, value); } catch (e) {} }
}
export function storageRemove(key) {
  cache.delete(key);
  if (sdk) sdk.Storage.removeItem(key).catch(() => {});
  else { try { localStorage.removeItem(key); } catch (e) {} }
}

// ── 게임 로그인 (유저 식별자) ────────────────────────────────────────
// 토스: getAnonymousKey(신규) → getUserKeyForGame(구) 순으로 시도. 웹: 로컬 익명 id.
export async function getUserKey() {
  if (sdk) {
    try {
      const fn = sdk.getAnonymousKey || sdk.getUserKeyForGame;
      const r = await withTimeout(fn(), 4000);
      if (r && r.type === "HASH" && r.hash) return r.hash;
    } catch (e) {}
    return null; // 토스 안인데 실패 → 식별 불가로 처리
  }
  try {
    let id = localStorage.getItem("spotlight_local_uid");
    if (!id) { id = "local-" + Math.random().toString(36).slice(2, 10); localStorage.setItem("spotlight_local_uid", id); }
    return id;
  } catch (e) { return "local"; }
}

// ── 리더보드 (토스게임센터) ──────────────────────────────────────────
// score: 숫자(높을수록 상위). 토스 밖에서는 조용히 무시된다.
export async function submitScore(score) {
  if (!sdk) return null;
  try {
    const r = await sdk.submitGameCenterLeaderBoardScore({ score: String(score) });
    return r || null;
  } catch (e) { return null; }
}
export async function openLeaderboard() {
  if (!sdk) return;
  try { await sdk.openGameCenterLeaderboard(); } catch (e) {}
}

// ── 행동 로그 (앱인토스 Analytics) ──────────────────────────────────
// 값은 문자열/숫자/불리언만 허용된다(Primitive).
export function logEvent(name, params = {}) {
  if (!sdk) return;
  try { sdk.Analytics.click && sdk.Analytics.click({ log_name: name, ...params }); } catch (e) {}
}
export function logScreen(name) {
  if (!sdk) return;
  try { sdk.Analytics.screen && sdk.Analytics.screen({ log_name: name }); } catch (e) {}
}

// ── Safe Area ───────────────────────────────────────────────────────
// 토스 SDK가 알려준 인셋. SceneManager가 env(safe-area-inset)와 합쳐(max) 쓴다.
export function getNativeInsets() { return nativeInsets; }
