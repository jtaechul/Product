const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const SELF_URL = 'https://insight-vault.pages.dev';
const WORKER_URL = 'https://book-carousel.jtaechul.workers.dev';

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS },
  });
}

// ===== Claude API =====
// 모델 ID를 하드코딩하지 않는다. 키마다 접근 가능한 모델이 달라(403/404 발생).
// /v1/models 는 "목록에 보이는 것"만 알려줄 뿐 실제 호출 권한과 다르므로,
// 후보 모델에 1토큰 테스트 호출을 실제로 던져 200이 나오는 것만 골라 쓴다.
let _modelCache = null;

// /v1/models 조회 실패 시(네트워크·레이트리밋) 폴백으로 쓸 알려진 모델 목록
const FALLBACK_MODEL_IDS = [
  'claude-sonnet-4-6', 'claude-opus-4-8', 'claude-haiku-4-5-20251001',
  'claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-4-5',
  'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022',
];

async function listModelIds(apiKey) {
  const res = await fetch('https://api.anthropic.com/v1/models?limit=100', {
    headers: { 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.data || []).map(m => m.id);
}

// 모델을 실제로 호출해 사용 가능 여부 확인 (200이면 사용 가능)
// 10초 타임아웃 + 일시적 과부하(429/529/5xx) 1회 재시도
async function probeModel(apiKey, model, attempt = 0) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 6000);
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({ model, max_tokens: 1, messages: [{ role: 'user', content: 'hi' }] }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    // 일시적 과부하/레이트리밋이면 1회 재시도 (probe 한 번 실패로 앱 전체가 멈추지 않게)
    if ((res.status === 429 || res.status === 529 || res.status >= 500) && attempt < 1) {
      await new Promise(r => setTimeout(r, 1500));
      return probeModel(apiKey, model, attempt + 1);
    }
    return res.status;
  } catch {
    clearTimeout(timer);
    return 0; // 타임아웃·네트워크 오류
  }
}

// 후보를 우선순위대로 늘어놓되, 실제 목록에 있는 모델만 남긴다
function orderCandidates(ids, patterns) {
  const out = [];
  for (const p of patterns) {
    for (const id of ids) {
      if (id.includes(p) && !out.includes(id)) out.push(id);
    }
  }
  return out;
}

const HARDCODED_FALLBACK_MAIN = 'claude-sonnet-4-6';
const HARDCODED_FALLBACK_LIGHT = 'claude-haiku-4-5-20251001';
const MODEL_CACHE_KV_KEY = 'model_cache_v2';
const MODEL_CACHE_TTL = 86400; // 24h

async function resolveModels(apiKey, env) {
  if (_modelCache) return _modelCache;

  // KV 캐시 우선 확인 — 콜드스타트마다 프로빙 반복을 방지
  if (env?.PENDING_POSTS) {
    try {
      const cached = await env.PENDING_POSTS.get(MODEL_CACHE_KV_KEY, 'json');
      if (cached?.main) {
        _modelCache = { main: cached.main, light: cached.light || cached.main, source: 'kv-cache' };
        return _modelCache;
      }
    } catch {}
  }

  let ids = await listModelIds(apiKey);
  // /v1/models 실패(네트워크·레이트리밋) → 알려진 후보로 폴백
  if (ids.length === 0) ids = FALLBACK_MODEL_IDS;

  const probed = {};

  const mainOrder = orderCandidates(ids, ['sonnet-4', 'sonnet', 'opus-4', 'opus', 'haiku']);
  const lightOrder = orderCandidates(ids, ['haiku-4', 'haiku', 'sonnet-4', 'sonnet']);

  // 최대 3개만 순차 탐색 — probe 과다로 30s Worker 한도 초과 방지
  const firstUsable = async (order) => {
    for (const m of order.slice(0, 3)) {
      if (probed[m] === undefined) probed[m] = await probeModel(apiKey, m);
      if (probed[m] === 200) return m;
    }
    return null;
  };

  let main = await firstUsable(mainOrder);
  let light = (await firstUsable(lightOrder)) || main;

  // 모든 probe가 실패하면 폴백을 쓰되, 실제 /v1/models 목록의 첫 후보를 우선한다
  // (레거시 하드코딩 ID는 키에 따라 404가 나므로 마지막 수단).
  // ⚠️ 검증되지 않은 폴백은 KV에 캐시하지 않는다 → 일시적 탐색 실패가 24시간
  // 동안 잘못된 모델로 고정되는 "캐시 포이즈닝"을 막는다(잦은 404의 근본 원인).
  if (!main) {
    main = mainOrder[0] || HARDCODED_FALLBACK_MAIN;
    light = lightOrder[0] || main;
    _modelCache = { main, light, source: 'unverified-fallback', available: ids, probed };
    return _modelCache;
  }

  _modelCache = { main, light, source: 'probed', available: ids, probed };
  // 성공한 모델 ID를 KV에 저장 — 다음 콜드스타트에서 재프로빙 없이 즉시 사용
  if (env?.PENDING_POSTS) {
    try { await env.PENDING_POSTS.put(MODEL_CACHE_KV_KEY, JSON.stringify({ main, light }), { expirationTtl: MODEL_CACHE_TTL }); } catch {}
  }
  return _modelCache;
}

// 모델 캐시 무효화 — 잘못된 모델이 캐시됐을 때 비워서 다음 해석에서 재탐색하게 한다.
async function clearModelCache(env) {
  _modelCache = null;
  if (env?.PENDING_POSTS) {
    try { await env.PENDING_POSTS.delete(MODEL_CACHE_KV_KEY); } catch {}
  }
}

// tier에 맞는 후보 모델을 우선순위대로 반환(중복 제거). /v1/models 실패 시 하드코딩 폴백.
// 자가복구(healModelByRealCall)가 이 목록에 "실제 요청"을 순서대로 던져 200을 찾는다.
async function orderedCandidateModels(apiKey, tier) {
  let ids = await listModelIds(apiKey);
  if (!ids.length) ids = FALLBACK_MODEL_IDS.slice();
  const order = tier === 'light'
    ? orderCandidates(ids, ['haiku-4', 'haiku', 'sonnet-4', 'sonnet', 'opus'])
    : orderCandidates(ids, ['sonnet-4', 'sonnet', 'opus-4', 'opus', 'haiku']);
  // 알려진 폴백 ID도 뒤에 덧붙여 최후의 수단 확보(목록 조회가 비었을 때 대비)
  for (const f of FALLBACK_MODEL_IDS) if (!order.includes(f)) order.push(f);
  return order;
}

// 동작이 확인된 모델을 메모리·KV에 캐시. 다른 tier 슬롯이 비었거나 방금 실패한
// 모델과 같으면 함께 갱신한다(양쪽 tier가 같은 나쁜 모델로 물려 있던 문제 방지).
async function cacheWorkingModel(env, tier, model, badModel) {
  const prev = _modelCache || {};
  let main = tier === 'main' ? model : prev.main;
  let light = tier === 'light' ? model : prev.light;
  if (!main || main === badModel) main = tier === 'main' ? model : (main || model);
  if (!light || light === badModel) light = tier === 'light' ? model : (light || model);
  _modelCache = { main, light, source: 'healed' };
  if (env?.PENDING_POSTS) {
    try { await env.PENDING_POSTS.put(MODEL_CACHE_KV_KEY, JSON.stringify({ main, light }), { expirationTtl: MODEL_CACHE_TTL }); } catch {}
  }
}

// 403/404 자가복구(결정적) — 후보 모델에 "실제 요청"을 순서대로 보내 200이 나오는
// 첫 모델의 응답을 반환하고 그 모델을 캐시한다. probe(1토큰 'hi')와 실제 호출의 권한
// 괴리를 없애고, 후보를 전부 소진할 때까지 시도해 "한 번 재시도 후 포기" 문제를 제거한다.
async function healModelByRealCall(apiKey, opts, badModel) {
  const { system, user, max_tokens = 2048, env, tier = 'main' } = opts;
  await clearModelCache(env);
  const candidates = (await orderedCandidateModels(apiKey, tier)).filter(m => m !== badModel);
  let forbidden403 = 0; // 서로 다른 모델이 연속 403이면 모델 문제가 아니라 "지역 라우팅 차단"
  for (const model of candidates) {
    let res;
    try {
      res = await fetch('https://api.anthropic.com/v1/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
        body: JSON.stringify({ model, max_tokens, system, messages: [{ role: 'user', content: user }] }),
      });
    } catch { continue; } // 네트워크 오류 → 다음 후보
    if (res.ok) {
      await cacheWorkingModel(env, tier, model, badModel);
      try { return (await res.json()).content[0].text; } catch { return null; }
    }
    if (res.status === 403) {
      forbidden403++;
      // 서로 다른 모델 3개가 전부 403("Request not allowed") = 키/모델 문제가 아니라
      // Cloudflare가 요청을 Anthropic 차단 지역(홍콩 등)으로 내보낸 것 → 조기 중단.
      // 이 오류는 "일시적"이므로 상위에서 재시도하게 REGION_BLOCKED로 태깅해 던진다.
      if (forbidden403 >= 3) throw new Error('REGION_BLOCKED');
    }
    // 과부하(429/5xx)면 잠깐 쉬고 다음 후보로.
    if (res.status === 429 || res.status === 529 || res.status >= 500) {
      await new Promise(r => setTimeout(r, 800));
    }
  }
  if (forbidden403 >= 2) throw new Error('REGION_BLOCKED'); // 후보 대부분 403 → 같은 결론
  return null; // 모든 후보가 404 등 → 진짜 키/권한 문제
}

// 핸들러에서 쓸 모델 ID 반환 (없으면 원인을 알려주는 에러)
async function getModel(apiKey, tier, env) {
  const m = await resolveModels(apiKey, env);
  if (!m.main) {
    throw new Error(
      'API 키로 호출 가능한 Claude 모델이 없습니다. ' +
      '목록엔 보이지만 실제 호출이 거부됩니다(권한·크레딧·워크스페이스 모델 제한 가능). ' +
      'Anthropic 콘솔에서 이 키의 모델 접근 권한과 결제 상태를 확인하세요. ' +
      `(확인된 모델: ${(m.available || []).join(', ') || '없음'})`
    );
  }
  return tier === 'light' ? m.light : m.main;
}

// ===== 일일 API 예산 가드 (크레딧 보호) =====
// Claude 호출 횟수를 KST 날짜별로 KV에 기록해, 폭주(무한 재시도·과다 테스트·봇 남용)로
// 크레딧이 하루에 소진되는 것을 막는다. 카운트는 "논리적 호출" 기준(재시도·자가복구는
// 같은 호출로 간주해 중복 카운트하지 않음).
//   SOFT_CAP 초과: optional(부가) 호출만 생략 — 릴스 훅·적합성 게이트·텍스트 압축 등
//                  폴백이 있는 호출이라 결과물은 계속 나온다.
//   HARD_CAP 초과: 모든 호출 차단(BUDGET_EXCEEDED). 다음 날 자동 해제.
// 하루 정상 사용량: 일일 자동 1편 ≈ 7~9회 + 수동 제작 2~3편 ≈ 20~30회 → 여유 있게 설정.
const DAILY_SOFT_CAP = 60;
const DAILY_HARD_CAP = 120;
function _kstDay() { return new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10); }
async function bumpApiUsage(env) {
  if (!env?.PENDING_POSTS) return 0;
  const key = `api_usage_${_kstDay()}`;
  let n = 0;
  try { n = parseInt(await env.PENDING_POSTS.get(key) || '0', 10) || 0; } catch {}
  n += 1;
  try { await env.PENDING_POSTS.put(key, String(n), { expirationTtl: 2 * 24 * 3600 }); } catch {}
  return n;
}
async function getApiUsage(env) {
  if (!env?.PENDING_POSTS) return 0;
  try { return parseInt(await env.PENDING_POSTS.get(`api_usage_${_kstDay()}`) || '0', 10) || 0; } catch { return 0; }
}

// 일시적 오류(429 요청과다 · 529 과부하 · 5xx · 네트워크)는 재시도로 흡수한다.
// 파이프라인이 Claude를 연속 6회 호출하므로, 단발 실패 한 번에 단계 전체가
// 무너지지 않도록 지수 백오프 재시도를 둔다 (이게 3·4단계 간헐 실패의 근본 원인이었음).
// 403은 영구 오류("Request not allowed") — 재시도해도 같은 결과. 즉시 실패 처리.
const RETRYABLE_STATUS = new Set([408, 409, 429, 500, 502, 503, 504, 529]);

async function callClaude(apiKey, opts, attempt = 0) {
  const MAX_RETRIES = 3;
  const BACKOFF_MS = [1000, 3000, 7000];
  const { system, user, max_tokens = 2048, env, tier = 'main' } = opts;

  // ⭐ 일일 예산 가드 — 논리적 호출당 1회만 카운트(재시도 attempt>0 · 자가복구 _healed 제외)
  if (attempt === 0 && !opts._healed && env) {
    const used = await bumpApiUsage(env);
    if (used > DAILY_HARD_CAP) {
      throw new Error(`BUDGET_EXCEEDED: 오늘 Claude API 일일 예산(${DAILY_HARD_CAP}회)을 초과했습니다 — 크레딧 보호를 위해 차단하며, 내일(KST) 자동 해제됩니다.`);
    }
    if (opts.optional && used > DAILY_SOFT_CAP) {
      // 부가 호출(폴백 있음)은 소프트캡부터 생략 — 호출한 쪽 try/catch가 폴백 처리
      throw new Error('BUDGET_SKIP: 일일 예산 절약 모드 — 부가 호출 생략');
    }
  }

  // 모델은 직접 주어지면 그걸, 아니면 tier로 해석한다(자가복구를 위해 env·tier 보관).
  const model = opts.model || await getModel(apiKey, tier, env);

  let res;
  try {
    res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model,
        max_tokens,
        system,
        messages: [{ role: 'user', content: user }],
      }),
    });
  } catch (netErr) {
    // 네트워크 오류 → 재시도
    if (attempt < MAX_RETRIES) {
      await new Promise(r => setTimeout(r, BACKOFF_MS[attempt]));
      return callClaude(apiKey, opts, attempt + 1);
    }
    throw new Error(`Claude 호출 네트워크 오류: ${netErr.message}`);
  }

  if (!res.ok) {
    // 404(모델 없음)·403(접근 불가/"Request not allowed") → 선택/캐시된 모델이 이 키로
    // 거부됨. 후보 모델에 "실제 요청"을 순서대로 던져 200 나오는 첫 모델로 결정적 자가복구.
    // (probe와 실제 호출의 권한 괴리를 없애고, 후보를 전부 소진할 때까지 시도)
    if ((res.status === 404 || res.status === 403) && env && !opts._healed) {
      let healed;
      try {
        healed = await healModelByRealCall(apiKey, { ...opts, _healed: true }, model);
      } catch (he) {
        if (/REGION_BLOCKED/.test(he.message)) {
          // 모델·키 문제가 아니라, Cloudflare가 이 요청을 Anthropic이 차단하는 지역
          // (홍콩 등)으로 내보낸 것. 일시적 — 크론/프론트가 자동 재시도한다.
          throw new Error('[403] REGION_BLOCKED: 일시적인 해외 경유지 차단으로 Claude 호출이 거부되었습니다. 잠시 후 자동으로 다시 시도됩니다 — API 키·크레딧 문제가 아닙니다.');
        }
        throw he;
      }
      if (healed !== null && healed !== undefined) return healed;
      // 모든 후보가 404 등으로 실패 → 키/권한/결제 문제. 명확히 안내.
      const eb = await res.json().catch(() => ({}));
      const dt = eb?.error?.message || 'Request not allowed';
      throw new Error(`[${res.status}] ${dt} — 이 API 키로 호출 가능한 Claude 모델을 찾지 못했습니다. Anthropic 콘솔에서 키의 모델 접근 권한·결제(크레딧) 상태를 확인하세요.`);
    }
    if (RETRYABLE_STATUS.has(res.status) && attempt < MAX_RETRIES) {
      // 서버가 Retry-After를 주면 우선 존중, 없으면 지수 백오프
      const ra = parseInt(res.headers.get('retry-after') || '', 10);
      const wait = Number.isFinite(ra) ? Math.min(ra * 1000, 10000) : BACKOFF_MS[attempt];
      await new Promise(r => setTimeout(r, wait));
      return callClaude(apiKey, opts, attempt + 1);
    }
    const errBody = await res.json().catch(() => ({}));
    const detail = errBody?.error?.message || JSON.stringify(errBody);
    throw new Error(`[${res.status}] ${detail}`);
  }
  return (await res.json()).content[0].text;
}

// ===== 책 실존 검증 =====
// AI가 지어낸 가짜 책으로 캐럿셀을 만드는 것을 막는다.
// 여러 소스로 확인: 네이버 책 API(키 있을 때·정확) → 알라딘(포지티브 신호) → AI 검증(명백한 가짜만).
// ⚠️ "확실한 가짜"만 차단하고, 판단이 애매하면 막지 않는다(진짜 책을 막는 거짓 음성 방지).
function coupangSearchUrl(title) {
  return `https://www.coupang.com/np/search?q=${encodeURIComponent(title || '')}`;
}

// 네이버 책 검색 API (정확·Worker에서도 동작) — 키가 있을 때만. total>0 이면 실존.
async function naverBookCheck(env, query) {
  if (!env?.NAVER_CLIENT_ID || !env?.NAVER_CLIENT_SECRET) return null;
  try {
    const res = await fetch(`https://openapi.naver.com/v1/search/book.json?query=${encodeURIComponent(query)}&display=3`, {
      headers: { 'X-Naver-Client-Id': env.NAVER_CLIENT_ID, 'X-Naver-Client-Secret': env.NAVER_CLIENT_SECRET },
    });
    if (!res.ok) return null;
    const d = await res.json();
    return (d.total || 0) > 0;
  } catch { return null; }
}

// 네이버 책 검색 — 상세 정보(제목·저자·출판사·소개)를 돌려준다. 교차검증·교정용.
function _clean(s) {
  return String(s || '').replace(/<\/?b>/gi, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').trim();
}
// 공백·문장부호만 제거하고 글자(한글 포함)·숫자는 보존한다.
// (주의: \W 는 한글을 비단어로 보고 지워버리므로 쓰면 안 됨 → 유니코드 letter/number만 남김)
function _normTitle(s) { return String(s || '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ''); }

// ⭐ 성인·에로 콘텐츠 필터 (검열 체계) — 성인만화·성인소설·에로/19금 등이 리뷰로 제작되지 않게 차단.
// 고정밀 마커만 사용해 건강한 연애·성심리 도서의 오탐(false positive)을 최소화한다.
const ADULT_PATTERNS = [
  /19\s*금/, /19\s*\+/, /미성년자\s*관람\s*불가/, /청소년\s*이용\s*불가/, /성인\s*인증/,
  /성인\s*(만화|웹툰|소설|물|용|콘텐츠)/, /에로(틱|티카|물|소설|스)?/, /야설/, /야한\s*소설/,
  /음란/, /포르노/, /하드코어/, /관능\s*소설/, /19세\s*이상/, /성인향/, /\bBL\b.*(성인|19)/,
  /\berotic(a|as)?\b/i, /\bhentai\b/i, /\bporn/i, /\bnsfw\b/i, /\bsmut\b/i, /\bxxx\b/i,
  /explicit\s+sexual/i, /adult\s+(manhwa|manga|comic|webtoon|novel|fiction|content)/i,
];
function containsAdultContent(...parts) {
  const t = parts.filter(Boolean).join(' ');
  return ADULT_PATTERNS.some(re => re.test(t));
}

async function naverBookLookup(env, query) {
  if (!env?.NAVER_CLIENT_ID || !env?.NAVER_CLIENT_SECRET) return null; // 키 없으면 판단 불가
  try {
    const res = await fetch(`https://openapi.naver.com/v1/search/book.json?query=${encodeURIComponent(query)}&display=10`, {
      headers: { 'X-Naver-Client-Id': env.NAVER_CLIENT_ID, 'X-Naver-Client-Secret': env.NAVER_CLIENT_SECRET },
    });
    if (!res.ok) return null;
    const d = await res.json();
    const items = (d.items || []).map(it => ({
      title: _clean(it.title),
      author: _clean(it.author).replace(/\^/g, ', ').replace(/\|/g, ', '),
      publisher: _clean(it.publisher),
      pubdate: it.pubdate || '',
      description: _clean(it.description),
      image: it.image || '',          // 책 표지 이미지 URL
    }));
    return { found: items.length > 0, items, total: d.total || 0 };
  } catch { return null; }
}

// ⭐ 교차검증: 제목으로 네이버에서 실제 책을 찾아 "진짜 제목·저자"로 교정한다.
// status: 'found'(교정정보 포함) / 'notfound'(실존 안 함 → 차단) / 'unknown'(키없음·조회실패 → 보류)
async function crossVerifyBook(env, title, author) {
  const t = (title || '').trim();
  if (!t) return { status: 'notfound' };

  // ⚠️ 제목만으로 조회한다. (제목+저자를 합쳐 조회하면 저자가 틀릴 때 0건이 나와
  //    진짜 책도 못 찾으므로.) 제목으로 찾은 뒤 네이버의 진짜 저자로 교정한다.
  const look = await naverBookLookup(env, t);
  if (look === null) return { status: 'unknown' };       // 네이버 키 없음/조회 실패
  if (!look.found || !look.items.length) return { status: 'notfound' };

  const nt = _normTitle(t);
  // 제목이 일치하는 항목들 (엉뚱한 책 매칭 방지)
  const titleMatches = look.items.filter(it => {
    const ni = _normTitle(it.title);
    return ni && nt && (ni.includes(nt) || nt.includes(ni));
  });
  if (!titleMatches.length) return { status: 'notfound' };  // 그 제목의 책이 실존하지 않음

  // 같은 제목이 여러 권이면 저자가 비슷한 것을 우선, 없으면 첫 항목
  const na = _normTitle(author);
  const best = (na && titleMatches.find(it => {
    const ia = _normTitle(it.author);
    return ia && (ia.includes(na) || na.includes(ia));
  })) || titleMatches[0];

  return {
    status: 'found',
    title: best.title,
    author: best.author,         // ← 네이버의 진짜 저자로 교정
    publisher: best.publisher,
    description: best.description,
    cover: best.image || '',     // ← 책 표지 이미지
  };
}

// 알라딘 검색 — 결과가 충분하면 실존 확정(포지티브 신호만). Worker IP가 차단돼 셸을
// 반환하면 카운트가 낮을 수 있으므로 "부족=가짜"로 단정하지 않는다(거짓 음성 방지).
async function aladinPositiveCheck(query) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 7000);
  try {
    const res = await fetch(`https://www.aladin.co.kr/search/wsearchresult.aspx?SearchWord=${encodeURIComponent(query)}`, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9',
      },
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return { count: 0, ok: false };
    const html = await res.text();
    return { count: (html.match(/wproduct\.aspx/g) || []).length, ok: true };
  } catch { clearTimeout(timer); return { count: 0, ok: false }; }
}

// AI 스켑틱 검증 (키 불필요·Worker OK) — 명백한 가짜만 걸러낸다.
async function aiBookCheck(env, title, author) {
  try {
    const txt = await callLightModel(env, {
       max_tokens: 150,
      system: '당신은 도서 사실 검증가입니다. 명백히 가짜인 책만 걸러냅니다. 진짜 책을 가짜로 판정하지 않도록 보수적으로 판단합니다. 반드시 JSON만 응답합니다.',
      user: `다음 책 제목이 "명백히 지어낸 가짜"인지 판정하세요.\n제목: ${title}\n저자: ${author || '(미상)'}\n\n판정 규칙(진짜 책을 막지 않는 것이 최우선):\n- 제목이 무의미한 문자열이거나(임의 숫자·자모 뒤섞임 등) 정상적인 책 제목으로 보이지 않으면: real=false, confidence="high"\n- 실제로 존재할 법한 정상적인 제목이면, 당신이 그 책을 몰라도: real=true (확신 없으면 confidence="low")\nJSON: {"real": true/false, "confidence": "high"/"low"}`,
    });
    const j = extractJson(txt);
    if (j.real === true) return true;
    if (j.real === false && j.confidence === 'high') return false;
    return null; // 모르겠음 → 보류(차단 안 함)
  } catch { return null; }
}

// 책 실존 종합 검증.
// confirmed: true(실존) / false(확실한 가짜 → 차단) / null(판단 불가 → 차단 안 함)
async function verifyBookReal(env, title, author) {
  const t = (title || '').trim();
  if (!t) return { confirmed: false, source: 'none', coupangSearchUrl: coupangSearchUrl(t) };
  const query = author ? `${t} ${author}` : t;

  const naver = await naverBookCheck(env, query);
  if (naver === true) return { confirmed: true, source: 'naver', coupangSearchUrl: coupangSearchUrl(t) };
  if (naver === false) return { confirmed: false, source: 'naver', coupangSearchUrl: coupangSearchUrl(t) };

  const al = await aladinPositiveCheck(query);
  if (al.ok && al.count >= 8) return { confirmed: true, source: 'aladin', productCount: al.count, coupangSearchUrl: coupangSearchUrl(t) };

  const ai = await aiBookCheck(env, t, author);
  return { confirmed: ai, source: 'ai', coupangSearchUrl: coupangSearchUrl(t) };
}

function extractJson(text) {
  if (!text) throw new Error('JSON 파싱 실패: 빈 응답');
  // ```json ... ``` 코드펜스 제거 후 첫 { ~ 마지막 } 구간 파싱
  const cleaned = text.replace(/```(?:json)?/gi, '').trim();
  const start = cleaned.indexOf('{');
  const end = cleaned.lastIndexOf('}');
  if (start === -1 || end === -1 || end <= start) throw new Error('JSON 파싱 실패');
  const body = cleaned.slice(start, end + 1);
  try {
    return JSON.parse(body);
  } catch (e) {
    // 응답이 잘렸거나(max_tokens 초과) 사소한 문법 오류 → 복구 시도.
    // ① 흔한 결함 정리: 트레일링 콤마 제거 ② 그래도 실패하면 "마지막 완결 요소까지"만 파싱.
    const repaired = repairTruncatedJson(body);
    if (repaired) { try { return JSON.parse(repaired); } catch {} }
    throw e; // 복구 실패 → 원래 오류(상위에서 재시도/폴백 처리)
  }
}
// 잘린/사소하게 깨진 JSON을 최대한 살린다. 특히 books:[...] 같은 배열이 중간에 끊겼을 때,
// 마지막으로 완결된 요소까지만 남기고 열린 괄호를 닫아 유효 JSON으로 만든다.
function repairTruncatedJson(s) {
  let t = s.replace(/,\s*([}\]])/g, '$1'); // 트레일링 콤마 제거
  try { JSON.parse(t); return t; } catch {}
  // 문자열/이스케이프를 인지하며 스캔. 값(객체·배열)이 닫힐 때마다 그 지점과
  // "그때의 열린 괄호 스택"을 스냅샷으로 기록 → 가장 마지막 스냅샷이 최대 복구 지점.
  let inStr = false, esc = false;
  const stack = [];            // 아직 안 닫힌 여는 괄호에 대응하는 닫는 문자들
  let cutAt = -1, cutStack = null;
  for (let i = 0; i < t.length; i++) {
    const c = t[i];
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
      continue;
    }
    if (c === '"') { inStr = true; continue; }
    if (c === '{' || c === '[') stack.push(c === '{' ? '}' : ']');
    else if (c === '}' || c === ']') {
      stack.pop();
      if (stack.length) { cutAt = i; cutStack = stack.slice(); } // 아직 바깥이 남음 = 요소 하나 완결
      else return t.slice(0, i + 1); // 전체가 완결된 지점 → 그대로 반환
    }
  }
  if (cutAt === -1 || !cutStack) return null; // 살릴 완결 요소가 없음
  let cut = t.slice(0, cutAt + 1).replace(/,\s*$/, '');
  for (let i = cutStack.length - 1; i >= 0; i--) cut += cutStack[i]; // 열린 괄호 역순으로 닫기
  return cut;
}

// ===== Telegram =====
async function sendTelegramMessage(botToken, chatId, text) {
  const res = await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`텔레그램 발송 실패: ${err.description || res.status}`);
  }
  return res.json();
}

async function sendTelegramPhoto(botToken, chatId, photoUrl, caption) {
  const res = await fetch(`https://api.telegram.org/bot${botToken}/sendPhoto`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, photo: photoUrl, caption: caption || '' }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error(`이미지 전송 실패(폴백): ${err.description || res.status}`);
    return sendTelegramMessage(botToken, chatId, caption || photoUrl);
  }
  return res.json();
}

// 브라우저에서 Canvas로 합성한 이미지(base64 data URL)를 파일로 전송
async function sendTelegramPhotoFile(botToken, chatId, base64DataUrl, caption) {
  const match = base64DataUrl.match(/^data:([^;]+);base64,(.+)$/s);
  if (!match) return null;
  const mimeType = match[1];
  const binary = Uint8Array.from(atob(match[2]), c => c.charCodeAt(0));
  const form = new FormData();
  form.append('chat_id', String(chatId));
  if (caption) form.append('caption', caption);
  form.append('photo', new Blob([binary], { type: mimeType }), 'carousel.jpg');
  const res = await fetch(`https://api.telegram.org/bot${botToken}/sendPhoto`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    console.error(`파일 전송 실패: ${err.description || res.status}`);
    return null;
  }
  return res.json();
}

// 추가 수신자(앱에서 등록한 텔레그램 채팅 ID들). 터미널·대시보드 없이 앱에서 추가/삭제.
async function getExtraTelegramChatIds(env) {
  try { return (await env?.PENDING_POSTS?.get('telegram_extra_chat_ids', 'json')) || []; } catch { return []; }
}
// 기본 수신자(TELEGRAM_CHAT_ID 시크릿) + 추가 수신자 목록을 합쳐 중복 제거.
async function getAllTelegramChatIds(env) {
  const ids = [];
  if (env.TELEGRAM_CHAT_ID) ids.push(String(env.TELEGRAM_CHAT_ID));
  const extra = await getExtraTelegramChatIds(env);
  for (const id of extra) { const s = String(id).trim(); if (s) ids.push(s); }
  return [...new Set(ids)];
}

async function handleSendTelegramImage(env, body) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error('TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.');
  }
  const { imageDataUrl, caption } = body;
  if (!imageDataUrl) throw new Error('imageDataUrl이 필요합니다.');
  const chatIds = await getAllTelegramChatIds(env);
  let okCount = 0;
  for (const chatId of chatIds) {
    const result = await sendTelegramPhotoFile(env.TELEGRAM_BOT_TOKEN, chatId, imageDataUrl, caption || '');
    if (result) okCount++;
  }
  if (!okCount) throw new Error('텔레그램 이미지 전송 실패');
  return { success: true };
}

// 텔레그램에는 "제작 완료 알림 + 확인하러 가기 링크"만 보낸다.
// (이미지·세부 문구는 보내지 않음. 인스타그램 게시 결정은 캐럿셀 제작 페이지에서 함.)
// 등록된 모든 수신자(기본 1명 + 앱에서 추가한 수신자)에게 동일하게 발송한다.
async function handleSendTelegram(env, body) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error('TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.');
  }

  const { bookInfo, pipelineId } = body;
  // pipelineId가 있으면 해당 결과 페이지로 바로 연결되는 링크를 만든다.
  const link = pipelineId
    ? `${WORKER_URL}/?pipeline=${encodeURIComponent(pipelineId)}`
    : `${WORKER_URL}/`;

  const title = bookInfo?.title ? `"${bookInfo.title}"` : '';
  const msg = `[북 캐럿셀 제작 완료]\n\n${title} 캐럿셀(카드뉴스 5장 + 캡션)이 완성됐습니다.\n아래 "확인하러 가기"를 눌러 결과를 보고, 인스타그램 게시 여부를 결정해주세요.\n\n${link}`;

  const chatIds = await getAllTelegramChatIds(env);
  let okCount = 0;
  let lastErr = null;
  for (const chatId of chatIds) {
    try {
      const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          chat_id: chatId,
          text: msg,
          reply_markup: {
            inline_keyboard: [[{ text: '확인하러 가기', url: link }]],
          },
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        lastErr = err.description || String(res.status);
      } else {
        okCount++;
      }
    } catch (e) {
      lastErr = e.message;
    }
  }
  if (!okCount) throw new Error(`텔레그램 발송 실패: ${lastErr || '알 수 없는 오류'}`);

  return { success: true, message: `텔레그램으로 제작 완료 알림과 확인 링크를 보냈습니다. (수신자 ${okCount}/${chatIds.length}명)` };
}

// ===== Claude 핸들러 =====

// 카테고리/이슈 기반 책 추천
// 이미 캐럿셀로 만든 책 제목을 기록(반복 제작 방지). 제작 함수(handleGenerate)에서 매번 호출.
async function recordUsedBook(env, title) {
  if (!env.PENDING_POSTS || !title) return;
  let arr = [];
  try { arr = (await env.PENDING_POSTS.get('used_books', 'json')) || []; } catch {}
  const norm = _normTitle(title);
  if (arr.some(t => _normTitle(t) === norm)) return;   // 이미 기록됨
  arr.push(title);
  await env.PENDING_POSTS.put('used_books', JSON.stringify(arr.slice(-80)), { expirationTtl: 120 * 24 * 3600 });
}
// 제외할 책 제목 = 전달된 목록 + used_books(제작 이력) + book_catalog(도서관 등록). 정규화 중복 제거.
async function getUsedExcludes(env, extra = []) {
  const set = [...extra];
  try { const u = (await env.PENDING_POSTS.get('used_books', 'json')) || []; set.push(...u); } catch {}
  try { const c = (await env.PENDING_POSTS.get('book_catalog', 'json')) || []; set.push(...c.map(b => b && b.title).filter(Boolean)); } catch {}
  const seen = new Set(); const out = [];
  for (const t of set) { const n = _normTitle(t); if (n && !seen.has(n)) { seen.add(n); out.push(t); } }
  return out;
}

async function handleSuggest(env, body) {
  const { category, issue, excludeTitles = [] } = body;
  const topic = issue || category || '연애·관계 심리';

  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  // 프론트가 보낸 제외 목록 + 서버의 제작 이력(used_books)·도서관 등록본을 모두 합쳐 제외.
  const exclude = await getUsedExcludes(env, excludeTitles);
  const excludeClause = exclude.length
    ? `\n제외 도서(이미 만든 책 — 절대 추천 금지, 반드시 새로운 책으로): ${exclude.slice(-40).join(', ')}`
    : '';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main', max_tokens: 2600, // 6권×8필드 한글 JSON — 잘림(파싱 오류) 방지 위해 넉넉히
    system: '당신은 연애·관계 심리 전문 도서 큐레이터입니다. 30대 독자가 자신의 연애 패턴·이별·짝사랑·애착 유형을 이해하도록 돕는 실제 출판된 책을 추천합니다. 사랑·관계·심리·자기이해를 다루는 에세이, 심리학, 관계 안내서를 중심으로 큐레이션합니다. [금지] 성인용 만화·성인 소설·에로/19금·관능 소설 등 성인용(19세 이상) 콘텐츠는 절대 추천하지 마세요. 건전한 일반 도서만 추천합니다. 반드시 JSON만 응답합니다.',
    user: `오늘 날짜: ${today}\n주제: "${topic}"${excludeClause}\n\n이 주제와 관련해 30대 독자에게 깊이 공감받을 실제 책 6권을 추천하세요.\n\n[필수 — 실존 도서만] 당신이 실제로 한국에 출간된 것을 확신하는 책만 추천하세요. 제목·저자를 지어내지 마세요. 확신이 없으면 그 책은 빼고 확실한 책으로 채우세요. 너무 유명하지 않아도 되지만 반드시 실재해야 합니다(가짜 책 추천 시 시스템에서 자동 탈락됨).\n\n[선정 기준]\n- [적합성 — 매우 중요] 책의 "실제 핵심 주제"가 "${topic}"을 직접 다뤄야 한다. 사랑·인생 일반론(철학서·고전)을 큰 범주가 겹친다는 이유로 끼워 맞추지 말 것.\n- 연애·관계·사랑·애착·이별·자기이해를 다루는 책 (심리학/에세이/관계 안내서)\n- 독자가 "이건 내 얘기다"라고 느낄 수 있는 책 (예: 애착유형, 회피형·불안형 연애, 반복되는 연애 패턴, 자존감과 사랑, 건강한 경계, 이별 회복, 짝사랑·썸·설렘의 심리)\n- 한국 독자가 쉽게 구할 수 있는 국내 출간서 우선\n- 동일 저자 책은 중복 추천 금지\n\n각 책에 대해:\n- title: 책 제목 (실제 출판된 책, 정확한 제목)\n- author: 저자명 (정확히)\n- year: 출판연도 (숫자)\n- category: 세부 카테고리 (예: 애착심리 / 연애에세이 / 이별과회복 / 자존감과사랑 / 짝사랑과설렘 / 관계심리)\n- coreMessage: 이 책의 핵심 메시지 (1~2문장)\n- targetAudience: 주요 대상 독자층 (1문장)\n- reason: 30대가 지금 이 책을 읽어야 하는 이유 (1문장)\n- lesson: 이 책이 주는 핵심 교훈 한 문장 (주제 "${topic}"와 연결된, 마음에 남는 짧은 통찰)\n\nJSON 형식:\n{"books":[{"title":"...","author":"...","year":2024,"category":"...","coreMessage":"...","targetAudience":"...","reason":"...","lesson":"..."}]}`,
  });

  const parsed = extractJson(text);
  const books = Array.isArray(parsed.books) ? parsed.books : [];

  // [핵심 규칙] 교차검증 — 네이버에서 진짜 책을 찾아 실존 확인 + 저자 자동 교정.
  // 실존 안 함(notfound)은 제외, 저자가 틀리면 진짜 저자로 교정. 키 없음/조회실패(unknown)는
  // 알라딘 포지티브 신호로 보완하고 그래도 모르면 통과(거짓 음성 방지). 최종 차단은 제작 게이트.
  const checked = await Promise.all(books.map(async (b) => {
    const cv = await crossVerifyBook(env, b.title, b.author).catch(() => ({ status: 'unknown' }));
    if (cv.status === 'found') {
      return { ...b, author: cv.author || b.author, title: cv.title || b.title, description: cv.description || '', verified: true, _drop: false, coupangSearchUrl: coupangSearchUrl(cv.title || b.title) };
    }
    if (cv.status === 'notfound') {
      return { ...b, verified: false, _drop: true, coupangSearchUrl: coupangSearchUrl(b.title) };
    }
    // unknown → 알라딘 포지티브만 확인
    const al = await aladinPositiveCheck(b.author ? `${b.title} ${b.author}` : b.title).catch(() => ({ ok: false, count: 0 }));
    return { ...b, verified: al.ok && al.count >= 8, _drop: false, coupangSearchUrl: coupangSearchUrl(b.title) };
  }));
  let usable = checked.filter(b => !b._drop);                 // 실존 안 하는 책 제외
  // ⭐ 성인·에로 도서 강제 제외 (AI가 실수로 넣어도 서버에서 차단)
  usable = usable.filter(b => !containsAdultContent(b.title, b.author, b.category, b.coreMessage, b.description));
  // [강제 제외] AI가 제외 지시를 무시하고 이미 만든 책을 또 넣어도 서버에서 걸러낸다.
  const exNorm = new Set(exclude.map(_normTitle));
  const fresh = usable.filter(b => !exNorm.has(_normTitle(b.title)));
  if (fresh.length) usable = fresh;   // 전부 제외되면(신간 부족) 최소 원본 유지
  usable.sort((a, b) => (b.verified ? 1 : 0) - (a.verified ? 1 : 0));  // 실존 확인 책 우선

  // ⭐ 레인 적합성 게이트 — 네이버 "실제 책 소개"를 기준으로 주제를 직접 다루는 책만 남긴다.
  // (실제 발생 사례: 일반 사랑 철학서 『사랑의 기술』이 '짝사랑과설렘' 레인에 끼워 맞춰져
  //  책 내용과 무관한 카드뉴스가 제작됨 → 이 게이트가 차단)
  if (usable.length > 1) {
    try {
      const items = usable.map((b, i) => `${i + 1}. ${b.title} (${b.author}) — ${(b.description || b.coreMessage || '').slice(0, 220)}`).join('\n');
      const ftText = await callLightModel(env, {
         max_tokens: 200, optional: true, // 예산 절약 모드에서 생략 가능(폴백: 전체 유지)
        system: '당신은 도서 큐레이션 검수자입니다. 반드시 JSON만 응답합니다.',
        user: `주제: "${topic}"\n\n아래 책들이 이 주제를 "실제로 직접" 다루는지, 각 책의 소개문을 기준으로 판정하세요. 사랑·인생 일반론이라 큰 범주만 겹치고 이 주제를 직접 다루지 않으면 false.\n\n${items}\n\nJSON: {"fits":[true,false,...]} (순서대로 정확히 ${usable.length}개)`,
      });
      const f = extractJson(ftText);
      if (Array.isArray(f.fits) && f.fits.length === usable.length) {
        const fitted = usable.filter((_, i) => f.fits[i] === true);
        if (fitted.length) usable = fitted;   // 전부 탈락이면 원본 유지(빈 결과 방지)
      }
    } catch {} // 게이트 실패는 치명적이지 않음 — 원본 유지
  }

  usable = usable.slice(0, 4).map(({ _drop, ...rest }) => rest);

  return { success: true, books: usable };
}

// 책 제목만으로 핵심메시지·독자층 자동 분석
async function handleAnalyze(env, body) {
  const { title, author } = body;
  if (!title) throw new Error('책 제목이 필요합니다.');

  // 교차검증: 네이버에서 진짜 저자·정보를 먼저 확보(있으면 분석 프롬프트에도 사실로 제공)
  const cv = await crossVerifyBook(env, title, author);
  const realAuthor = cv.status === 'found' ? cv.author : author;

  const text = await callLightModel(env, {
    
    max_tokens: 512,
    system: '당신은 도서 분석 전문가입니다. 책 제목과 저자를 보고 핵심 메시지와 대상 독자층을 분석합니다. 반드시 JSON만 응답합니다.',
    user: `책: "${cv.status === 'found' ? cv.title : title}"${realAuthor ? ` / 저자: ${realAuthor}` : ''}${cv.status === 'found' && cv.description ? `\n참고(실제 책 소개): ${cv.description}` : ''}\n\n이 책의 정보를 분석하세요.\n\nJSON: {"author":"저자명","year":출판연도(숫자),"category":"카테고리","coreMessage":"이 책의 핵심 메시지 1~2문장","targetAudience":"주요 대상 독자층 1문장"}`,
  });

  const result = extractJson(text);
  // 네이버로 확인된 진짜 저자/제목이 있으면 그것으로 최종 확정(AI 추정보다 우선)
  if (cv.status === 'found') {
    if (cv.author) result.author = cv.author;
    result.verifiedTitle = cv.title;
    result.verified = true;
  } else if (cv.status === 'notfound') {
    result.notFound = true;
  }
  return { success: true, ...result };
}

// ===== 한국어 문장 교정 (어색·틀린 표현 자동 차단) =====
// 규칙 기반(무료·즉시) + AI 교정(새 눈으로 재점검) 이중 그물. 생성 직후 실행해
// "한 겹 가벼워집니다"(→"한결"), 되/돼 혼동 같은 어색·오류 표현을 걸러낸다.

// 고정밀 규칙 교정 — 맥락과 무관하게 거의 항상 틀린 조합만 좁게 잡는다(오탐 방지).
function fixCommonKoreanErrors(s) {
  if (typeof s !== 'string' || !s) return s;
  let t = s;
  // "한 겹/한겹 + 가벼(워/운/게)…" = 단위 오용 → "한결"(부사: 한층 더)
  t = t.replace(/한\s*겹(\s*)(가벼|가볍)/g, '한결$1$2');
  // "몇 일" → "며칠"(표준어)
  t = t.replace(/몇\s*일(?![가-힣])/g, '며칠');
  // "왠지" 외 "웬지" → "왠지"
  t = t.replace(/웬지/g, '왠지');
  return t;
}
// 페이지 객체의 모든 문자열 필드에 규칙 교정 적용
function applyRuleFixesToPages(pages) {
  const out = JSON.parse(JSON.stringify(pages || {}));
  for (const k of Object.keys(out)) {
    const p = out[k];
    if (p && typeof p === 'object') {
      for (const f of ['headline', 'body', 'cta', 'linkText']) {
        if (typeof p[f] === 'string') p[f] = fixCommonKoreanErrors(p[f]);
      }
    }
  }
  return out;
}
// 교정 결과를 원본에 안전 병합 — 존재하는 문자열 필드만, 비어있지 않을 때만 덮어씀
// (AI가 구조를 흐트러뜨려도 페이지·필드가 사라지지 않게)
function mergeProofread(orig, fixed) {
  const out = JSON.parse(JSON.stringify(orig || {}));
  for (const k of Object.keys(out)) {
    const o = out[k], f = fixed && fixed[k];
    if (o && typeof o === 'object' && f && typeof f === 'object') {
      for (const fld of ['headline', 'body', 'cta', 'linkText']) {
        if (typeof o[fld] === 'string' && typeof f[fld] === 'string' && f[fld].trim()) o[fld] = f[fld].trim();
      }
    }
  }
  return out;
}
// 생성 직후 교정 오케스트레이터: ① 규칙 교정 → ② AI 교정(옵션, 예산 절약 모드에선 생략)
// → 다시 규칙 교정. 실패해도 반드시 유효한 pages를 반환(생성 흐름 절대 안 깨짐).
async function proofreadPages(env, pages, logCtx) {
  let out = applyRuleFixesToPages(pages);
  try {
    const text = await callLightModel(env, {
       max_tokens: 900, optional: true, // 예산 소프트캡 초과 시 규칙 교정만
      system: '당신은 한국어 교정 전문 에디터입니다. 의미·톤·길이는 그대로 두고, 어색하거나 틀린 표현만 자연스럽게 고칩니다. 반드시 JSON만 응답합니다.',
      user: `아래 인스타그램 카드뉴스 문구에서 "어색하거나 틀린 한국어"만 골라 고치세요. 의미·따뜻한 톤·길이는 유지합니다.\n\n[특히 이런 오류를 반드시 잡으세요]\n- 단위/수량 표현 오용: "마음의 짐이 한 겹 가벼워진다"(X)→"한결 가벼워진다"(O). '겹'은 층을 세는 말이라 '가벼워지다'와 안 맞음.\n- 발음이 비슷해 잘못 쓰는 말: 한 겹/한결, 되/돼, -로서/-로써, -든지/-던지, 왠지/웬, 며칠/몇 일, 안/않.\n- 어색한 연어(서로 안 어울리는 단어 조합), 조사·어미 오류, 비문, 오타.\n- 존댓말·문어체 일관성(반말이 섞이면 존댓말로).\n[하지 말 것] 멀쩡한 문장을 취향으로 바꾸지 말 것. 틀리거나 확연히 어색한 것만 최소 수정.\n\n원문(JSON):\n${JSON.stringify(pages)}\n\n같은 구조의 JSON으로 고친 최종본만 반환하세요(고칠 게 없으면 원문 그대로). changes에는 고친 것을 "원래 → 수정" 형태로 넣으세요.\nJSON: {"pages":{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"cta":"...","linkText":"..."}},"changes":["..."]}`,
    });
    const r = extractJson(text);
    if (r && r.pages && r.pages.page1 && r.pages.page4) {
      out = mergeProofread(out, r.pages);
      if (logCtx?.env && logCtx?.pipelineId && Array.isArray(r.changes) && r.changes.length) {
        await logStep(logCtx.env, logCtx.pipelineId, { step: logCtx.step || 1, phase: 'proofread', note: r.changes.slice(0, 5).join(' · ').slice(0, 120) });
      }
    }
  } catch { /* AI 교정 실패·예산 초과 → 규칙 교정본 유지 */ }
  return applyRuleFixesToPages(out); // AI 결과에도 규칙 교정 재적용(이중 안전)
}

async function handleGenerate(env, body) {
  const { title, author, year, coreMessage, targetAudience, category } = body;
  if (!title || !author || !coreMessage) throw new Error('제목, 저자, 핵심 메시지는 필수입니다.');

  // ⭐ 성인 필터(1차) — 제목·저자·카테고리·핵심메시지에서 성인/에로 신호가 보이면 즉시 차단.
  // skipVerify로도 우회 불가(성인물은 어떤 경우에도 제작 금지).
  if (containsAdultContent(title, author, category, coreMessage)) {
    throw new Error('ADULT_BLOCKED: 성인·에로(19금·성인만화/소설 등) 도서는 리뷰를 만들 수 없습니다.');
  }

  // [핵심 규칙] 교차검증 게이트 — ① 실존 확인 ② 제목+저자 일치 확인·교정.
  // 네이버에서 진짜 저자를 가져와 틀린 저자를 자동 교정한다. 가짜는 차단.
  // skipVerify=true(사용자가 직접 확인)면 건너뛴다.
  let correctedBook = null;
  let bookCover = '';
  let bookDesc = String(body.description || ''); // 프론트/파이프라인이 이미 확보한 소개문
  if (!body.skipVerify) {
    const cv = await crossVerifyBook(env, title, author);
    if (cv.status === 'notfound') {
      throw new Error(`BOOK_NOT_FOUND: "${title}"은(는) 실제 출간된 책으로 확인되지 않습니다. 제목·저자를 확인하거나, 실제 책이 맞다면 직접 확인 후 진행하세요.`);
    }
    // ⭐ 성인 필터(2차) — 네이버 실제 책 소개글로 재확인(제목만으론 안 걸리는 에로 소설 차단).
    if (containsAdultContent(cv.title, cv.description)) {
      throw new Error('ADULT_BLOCKED: 성인·에로(19금·성인만화/소설 등) 도서는 리뷰를 만들 수 없습니다.');
    }
    if (cv.status === 'found') {
      bookCover = cv.cover || '';
      if (cv.description) bookDesc = cv.description; // ⭐ 실제 책 소개(출판사) — 생성 근거로 사용
      // 저자가 틀렸으면 네이버의 진짜 저자로 교정해서 알려준다(프론트가 반영)
      if (cv.author && cv.author !== author) {
        correctedBook = { title: cv.title || title, author: cv.author, publisher: cv.publisher || '' };
      }
    } else if (cv.status === 'unknown') {
      // 네이버 키 없음/실패 → 기존 게이트로 명백한 가짜만 차단(거짓 음성 방지)
      const v = await verifyBookReal(env, title, author);
      if (v.confirmed === false) {
        throw new Error(`BOOK_NOT_FOUND: "${title}"은(는) 실제 출간된 책으로 확인되지 않습니다. 제목·저자를 확인하거나, 실제 책이 맞다면 직접 확인 후 진행하세요.`);
      }
    }
  }

  const lt = laneTone(category); // 3레인 톤 — 카테고리(설렘/이별/자존감)에 맞는 감정 결

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main', max_tokens: 1200,
    system: `당신은 연애·관계 심리 책을 소개하는 인스타그램 카드뉴스 전문 카피라이터입니다.\n타겟 독자: ${lt.audience}.\n핵심 규칙(절대 위반 금지):\n1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.\n2. 각 페이지 텍스트는 최소한의 단어로 마음을 건드린다 — 장황한 설명 금지.\n3. 공포·위기·충격이 아니라 '깊은 공감과 위로'로 저장·공유를 유도한다. 독자가 "이건 내 얘기다"라고 느껴 저장하게 만든다.\n4. 통계·수치·연구 인용보다 감정과 경험의 언어를 쓴다. 따뜻하고 문학적인 톤.\n5. 모든 콘텐츠에 반말을 절대 사용하지 않는다 — 문어체·존댓말(~습니다/~합니다/~네요/~까요)만 허용.\n반드시 JSON만 응답한다.`,
    user: `다음 책 정보로 4페이지 인스타그램 캐럿셀을 작성하세요.\n\n카테고리: ${category || '연애·관계 심리'}\n핵심 메시지: ${coreMessage}\n${targetAudience ? `대상: ${targetAudience}` : ''}\n${bookDesc ? `실제 책 소개(출판사 제공 — 이 책의 진짜 내용): ${bookDesc.slice(0, 600)}\n` : ''}\n[근거 규칙 — 절대 위반 금지] ${bookDesc ? '위 "실제 책 소개"가 이 책의 진짜 내용입니다. 2~4페이지의 통찰·위로·솔루션은 반드시 이 소개의 주제·관점과 일치해야 하며, 소개에 없는 개념·주장을 책의 것처럼 지어내지 마세요. 소개의 주제가 카테고리 톤과 거리가 있으면, 톤을 책의 실제 주제 쪽으로 맞추세요(책이 우선).' : '이 책의 실제 내용을 확신할 수 없으므로, 특정 개념·주장을 책의 것처럼 단정하지 말고 핵심 메시지 범위 안의 보편적 위로에 머무르세요.'}\n\n[전체 톤 — 카테고리에 맞춰 조절] 대상: ${lt.audience}.\n톤: ${lt.tone}.\n흐름: ${lt.flow}.\n\n[연결성 — 매우 중요·최우선] 4페이지는 뚝뚝 끊긴 독립 카드가 아니라, 한 사람이 이어서 들려주는 "한 편의 편지"처럼 매끄럽게 이어져야 합니다.\n- 먼저 1→4페이지를 관통하는 하나의 감정 실(한 장면·한 마음)을 정하고, 각 페이지가 그 실을 이어받아 나아가게 쓰세요(장면 → 패턴과 마음의 이유 → 바라보는 법 → 오늘의 책).\n- 각 페이지는 바로 앞 페이지가 남긴 감정·표현을 자연스럽게 받아서 풀되, 억지 접속사("그래서/하지만"으로 시작)로 잇지 말고 같은 표현 반복도 금지. 감정의 결만 하나로 이으세요.\n- 1페이지 훅의 장면·감정이 2·3페이지에서 같은 사람의 이야기로 살아 있어야 하고, 4페이지는 그 여정을 감싸 안으며 책으로 건네야 합니다(갑자기 딴 이야기로 튀지 말 것).\n\n[겸용 — 중요] 이 문구는 1:1 카드뉴스와 9:16 릴스(세로 영상)에 함께 쓰입니다. 릴스에는 각 body의 "첫 1~2문장만" 발췌되므로, 1·2·3페이지의 첫 문장들만 이어 읽어도 하나의 이야기로 연결되어야 합니다.\n\n페이지 가이드 (길이 규칙 엄수):\n1페이지(공감 훅 — 헤드라인만): 카드 전체를 단 하나의 마음을 건드리는 문장으로 채운다.\n  - headline: 40자 이내 완전한 문장. 독자가 연애에서 겪었을 구체적 순간·감정을 정확히 포착한다.\n    규칙: "당신이 이 사실을 모른다면" 패턴 절대 금지. "대부분의 사람들이" 금지. 공포·경고 톤 금지. 주어 없는 단어 조각 금지.\n    접근법: 독자가 혼자 느꼈던 감정을 들킨 듯한 문장.\n    좋은 예(이번 카테고리 톤): ${lt.hookExample}\n             "좋아할수록 더 차갑게 굴게 되는 사람이 있습니다"\n    나쁜 예(절대 금지): "당신의 연애는 실패하고 있다" / "이대로면 평생 혼자입니다" (공포·단정 톤)\n  - subtext 없음 — JSON에 포함하지 않는다.\n2페이지(패턴과 마음의 이유): 반복해온 연애 패턴을 부드럽게 짚고, 그 심리적 뿌리(애착·상처·두려움)까지 한 페이지에서 따뜻하게 풀어낸다. 비난 금지.\n  - headline: 18자 이내\n  - body: 4~5줄, 한 줄 40자 이내. [문장 배치 규칙 — 필수] 첫 1~2문장에 이 페이지의 핵심을 완결되게 담는다(릴스에는 이 첫 문장들만 단독 노출됨). 이후 문장은 부연·확장. 앞 문장들은 "맞아, 나 그래" 하는 구체적 장면, 뒤는 "당신이 이상한 게 아니라 이런 마음이 있었던 것" 같은 이유의 통찰. 수치·학술 인용 금지.\n3페이지(위로의 실마리): 완전한 해답 대신 '이렇게 바라보면 달라진다'는 방향을 부드럽게 암시한다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 40자 이내. [문장 배치 규칙 — 필수] 첫 1~2문장에 핵심 위로를 완결되게 담는다(릴스 단독 노출). 이후는 부연. 마지막 줄은 희망적 여운으로 끝낸다. 단정적 해결책 금지.\n4페이지(책 공개 — 마무리): 독자에게 오늘의 책을 건넨다. (제목·저자·표지는 시스템이 자동으로 함께 보여주므로 본문 텍스트에 제목·저자를 직접 쓰지 말 것.)\n  - cta: 3페이지의 위로를 잇는 따뜻한 마무리 + 핵심 솔루션 한 문장(${lt.theme}에서 오늘 가져갈 마음의 방향). A/B·질문·"댓글" 언급 금지. 독자 가슴에 남는 한 문장.\n  - linkText: 그 마음에 책을 자연스럽게 건네는 한 줄 (예: "이 마음에 오래 곁이 되어줄 책을 소개합니다"). 제목은 쓰지 말 것(시스템이 표지·제목·저자를 함께 노출). "프로필 링크" 언급은 불필요.\n\nJSON:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"cta":"...","linkText":"..."}}`
  });

  let pages = extractJson(text);
  // ⭐ 한국어 교정 패스 — 어색·틀린 표현("한 겹"→"한결" 등) 자동 차단(규칙+AI 이중).
  pages = await proofreadPages(env, pages);
  // 실제로 제작된 책 제목을 기록 → 다음 추천에서 자동 제외(반복 제작 방지). 모든 제작 경로가 여기를 지남.
  await recordUsedBook(env, correctedBook?.title || title).catch(() => {});
  // bookDescription: 검증 단계가 실제 책 소개 기준으로 부합도를 채점할 수 있게 반환
  return { success: true, pages, correctedBook, bookCover, bookDescription: bookDesc };
}

async function handleValidate(env, body) {
  const { pages, bookInfo } = body;
  // ⭐ 실제 책 소개(출판사)가 있으면 그것을 부합도 채점의 근거로 사용 — AI 기억에만
  // 의존한 추측 채점(할루시네이션 미탐지)을 막는다.
  const bookDesc = String(bookInfo.description || '').slice(0, 600);
  const text = await callLightModel(env, {
    
    max_tokens: 1024,
    system: '당신은 소셜미디어 콘텐츠 전문 편집장 겸 저작권 검토자입니다. 반드시 JSON만 응답합니다.',
    user: `책 "${bookInfo.title}" (저자: ${bookInfo.author}) 캐럿셀을 아래 5가지 기준으로 평가하세요.\n${bookDesc ? `\n실제 책 소개(출판사 제공 — 부합도 채점의 근거):\n${bookDesc}\n` : ''}\n캐럿셀 내용:\n${JSON.stringify(pages, null, 2)}\n\n평가 기준 (100점 만점):\n1. accuracy(책 내용 부합도): ${bookDesc ? '캐럿셀의 통찰·솔루션이 위 "실제 책 소개"의 주제·메시지와 일치하는가? 소개와 무관한 주제를 책의 것처럼 말하면 크게 감점.' : '캐럿셀 내용이 해당 책의 실제 메시지와 일치하는가? (소개 미제공 — 확신 없으면 보수적으로 감점)'} 0~20\n2. factual(사실 정확성): 수치·통계·사례에 명백한 오류나 과장이 없는가? 0~20\n3. copyright(저작권 안전성): 책의 핵심 내용을 그대로 옮기지 않고 요약·재해석했는가? 저자명·책 제목이 본문에 노출되지 않는가? 0~20\n4. engagement(공감·참여 유도): 30대 독자가 "이건 내 얘기다"라고 느껴 저장·공유하고 싶어지는 깊은 공감과 위로가 있는가? 따뜻한 톤이 유지되는가(공포·단정·비난 톤이면 감점)? 0~25\n5. quality(문장 품질): 오타·비문·어색한 표현이 없고 간결한가? 또한 2·3페이지 body의 "첫 1~2문장"만 이어 읽어도(릴스 발췌) 흐름이 연결되는가? 0~15\n\nJSON: {"totalScore":85,"scores":{"accuracy":17,"factual":16,"copyright":18,"engagement":22,"quality":12},"feedback":"전체 평가 2~3문장","improvements":["구체적 개선점1","개선점2","개선점3"],"approved":true}\napproved는 totalScore>=70이면 true.`
  });
  return { success: true, ...extractJson(text) };
}

// ⭐ 3레인 톤 시스템 — 계정 정체성("행간 — 연애 책방")은 하나로 고정하고,
// 감정 구간(레인)에 따라 톤만 바꾼다. 카테고리를 늘리는 대신 연애의 감정 단계를 넓혀
// 팔로워 이탈(니치 졸업·무거운 톤 피로)을 막는다.
// light=설렘·썸·짝사랑(가벼움) / core=이별·재회·회복(수익 핵심) / self=자존감·나를 사랑하기(깊은 위로)
function laneOf(cat) {
  const c = String(cat || '');
  if (/설렘|짝사랑|썸|시작|고백|두근/.test(c)) return 'light';
  if (/자존|자기|나를/.test(c)) return 'self';
  return 'core';
}
const LANE_TONES = {
  light: {
    audience: '짝사랑·썸·연애 초반의 설렘을 지나는 30대',
    theme: '짝사랑과 설렘',
    tone: '풋풋하고 설레는 공감 — 무겁지 않게, 읽으며 슬며시 미소 짓게 하는 가벼운 톤. 위로보다 "맞아, 딱 이 기분!" 하는 반가움을 준다',
    flow: '설렘의 순간 공감 → 짝사랑·썸에서 반복되는 패턴 → 그 마음의 심리적 이유 → 용기와 설렘의 실마리 → 오늘의 책 소개',
    hookExample: '"답장이 오기 전까지는 아무 일도 손에 잡히지 않았습니다"',
    hashtagExample: '#짝사랑 #설렘 #책추천',
  },
  core: {
    audience: '이별·재회·회복을 지나는 30대',
    theme: '이별과 회복',
    tone: '깊은 공감과 위로 — 독자가 "이건 내 얘기다"라고 느껴 저장하게 만드는 따뜻한 톤',
    flow: '공감 → 패턴 발견 → 마음의 이유 → 위로의 실마리 → 오늘의 책 소개',
    hookExample: '"헤어지자는 말보다, 잡지 않을까 봐 더 무서웠습니다"',
    hashtagExample: '#이별 #연애심리 #책추천',
  },
  self: {
    audience: '연애 속에서 자신을 잃어버린 적 있는, 나를 먼저 사랑하고 싶은 30대',
    theme: '자존감과 나를 사랑하기',
    tone: '따뜻하고 단단한 위로 — 자책이 아니라 자기 존중과 회복으로 이끄는 톤',
    flow: '자신을 잃었던 순간 공감 → 반복 패턴 → 마음의 이유 → 나를 아끼는 방향 → 오늘의 책 소개',
    hookExample: '"그 사람에게 맞추느라, 내가 뭘 좋아했는지 잊어버렸습니다"',
    hashtagExample: '#자존감 #연애심리 #책추천',
  },
};
function laneTone(cat) { return LANE_TONES[laneOf(cat)]; }

// 인물 정체성만 고정(같은 화풍·같은 여성). 얼굴 방향은 여기서 말하지 않는다 —
// 자세(POSE)와 얼굴 묘사가 충돌하면(예: 뒷모습+얼굴 설명) AI가 머리를 180° 비틀어버리므로,
// 얼굴 관련 지시는 자세 그룹(얼굴 보임/안 보임)에 맞춰 아래에서 따로 붙인다.
const CHARACTER_ANCHOR = 'a cute anime girl character, a young woman with long wavy brown hair, adorable appealing anime character design; keep her identity recognizable while varying her pose, clothing and setting; keep her hands simple and relaxed, tucked in sleeves or pockets or out of frame — no detailed fingers and no fingers touching paper or pages';
// 화풍: 완전한 일본 애니메이션 일러스트(게임 캐릭터 일러스트 급). 반실사가 옆모습 눈을 어색하게
// 만들던 문제 → 풀 애니 스타일은 눈을 단순·또렷한 형태로 그려 훨씬 안정적.
const STYLE_ANCHOR = 'high-quality Japanese anime style illustration, 2D anime key visual, clean bold anime line art, flat vivid cel shading, glossy detailed anime hair, soft anime lighting with gentle bloom, like a modern anime game character illustration, fully stylized anime — absolutely not photorealistic, not semi-realistic, not 3d render, Instagram square 1:1';
// 해부학 안전장치 — 머리·목이 몸과 같은 방향, 비틀림·뭉개짐 금지 (모든 인물 컷 공통).
const ANATOMY_TAIL = ', anatomically correct natural pose, her head and neck aligned naturally with her body direction, never twisted or turned backwards, no distorted or melted face, no deformed anatomy, no extra limbs';
// 주제(카테고리)별 분위기·색감 — 이별/자존감/설렘이 서로 다른 느낌이 나도록.
function categoryMood(cat) {
  const c = String(cat || '');
  if (/설렘|짝사랑|썸|시작|고백|두근/.test(c)) return 'sweet fluttering hopeful mood, bright blush pink, peach and soft coral palette, airy spring daylight, light-hearted and dreamy, gentle sparkle';
  if (/자존|자기|나를/.test(c)) return 'warm uplifting mood, soft gold, cream and peach palette, bright gentle morning light, calm quiet confidence, cozy and hopeful';
  if (/이별|재회|회복|헤어|그리움/.test(c)) return 'melancholic tender yet gently healing mood, muted cool palette of dusty blue, soft grey and pale lavender with a touch of warm cream, quiet dusk or soft rainy atmosphere';
  if (/애착|관계|소통|경계|거리/.test(c)) return 'calm reassuring mood, soft sage, cream and dusty rose palette, gentle warm light, quiet and tender';
  return 'warm tender mood, soft pastel palette of cream, dusty rose and sage, cozy lyrical atmosphere';
}
// 인물 컷 자세 변주 — "얼굴 안 보임(뒷모습)"과 "얼굴 보임(앞/옆)" 두 그룹으로 분리.
// 뒷모습에 얼굴 묘사를 섞으면 AI가 고개를 뒤로 꺾어버리므로, 그룹마다 꼬리말을 다르게 붙인다.
const POSES_BACK = [   // 얼굴이 전혀 안 보이는 구도 — 얼굴 묘사 절대 금지
  'seen from behind gazing out a window, hands at her sides',
  'full back view, arms loosely at her sides',
  'seen from behind, head resting gently against a window',
  'walking away into the soft distance, back to the viewer',
  'a distant small figure against a bright window, seen from behind',
];
const POSES_FACE = [   // 얼굴이 보이는 구도 — 풀 애니 눈(크고 또렷한 애니 눈 또는 감은 눈). 극단적 옆모습은 제외.
  'front view with eyes gently closed and a soft peaceful smile, hands relaxed at her sides',
  'front view with big gentle anime eyes and a warm soft smile',
  'three-quarter front view looking slightly aside with calm anime eyes',
  'three-quarter front view with a wistful expression, eyes soft',
  'head tilted back with eyes closed, feeling the breeze, hands in her pockets',
  'front-facing with a gentle closed-eye smile, hands tucked into her sweater sleeves',
  'looking up with eyes closed toward soft light',
  'sitting curled up, chin near her knees, eyes closed, hands hidden',
  'lying down on her side, eyes closed, relaxed',
];
// 그룹별 꼬리말: 뒷모습=얼굴 없음 명시 / 얼굴 컷=또렷한 애니 눈 명시. 둘 다 해부학 가드 포함.
const BACK_TAIL = ', her face is not visible at all, only the back of her head with flowing hair, she looks in the same direction her body faces' ;
const PERSON_FACE_TAIL = ', a beautiful clean anime face with large expressive well-drawn anime eyes (or softly closed eyes), cute natural anime expression, crisp symmetrical features, no distorted eyes, no melted or malformed face; hands kept simple and relaxed, hidden in sleeves or pockets or out of frame, no close-up fingers, no tangled hands';
const SETTING_VARIATIONS = [
  'by a rain-streaked window', 'in a quiet cafe corner', 'in a cozy dim bedroom', 'on a city street at dusk',
  'on a bus by the window', 'in a sunlit kitchen', 'on a park bench in autumn', 'in a softly lit living room',
];
// 인물 없는 배경 장면용 앵커 — 같은 화풍·색감은 유지하되 사람은 넣지 않는다.
const SCENE_ANCHOR = 'absolutely no people, no person, no human, no figure, no silhouette, no hands, no body parts anywhere in the image — an empty atmospheric symbolic scene only (cozy interior, window, quiet place or meaningful objects)';

// 페이지별 폴백 프롬프트 — Claude 생성 실패 시 사용. (인물은 1페이지에만, 2~5는 무인)
const FALLBACK_IMAGE_PROMPTS = {
  page1: 'a woman seen from behind sitting alone by a large window at dusk, soft city lights bokeh outside, quiet wistful mood, empty space around her',
  page2: 'an empty cafe table by a window with a single cup and a phone left face-down, soft afternoon light, tender lonely atmosphere',
  page3: 'a window as gentle morning light streams in over a sheer curtain, hopeful warm glow, a quiet turning moment',
};

// 페이지별 감정 역할 — 1페이지의 감정만 레인(설렘/이별/자존감)에 따라 달라진다.
// 인물은 1페이지(표지)에만 등장. 2~5페이지는 무인 장면.
const LANE_PAGE1_EMOTION = {
  light: '좋아하는 마음을 들킨 듯한 설렘·두근거림',
  core: '이별 후의 쓸쓸함·그리움',
  self: '나를 가만히 돌아보는 조용한 마음',
};
function pageVisualDirections(lane) {
  return {
    page1: `혼자 있는 그녀 — 들킨 듯한 첫 감정(${LANE_PAGE1_EMOTION[lane] || LANE_PAGE1_EMOTION.core}). 뒷모습/옆모습, 여백 넉넉히(스크롤을 멈추는 표지 컷·인물 고정).`,
    page2: '반복된 패턴과 마음의 뿌리를 들여다보는 순간 — 무인(사물·공간)으로 감정 상징.',
    page3: '빛이 드는 전환·희망의 실마리 — 무인, 따뜻한 아침빛.',
  };
}

async function handleGenerateImages(env, body) {
  const { pages, bookInfo } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 페이지 전체 내용 구성 (헤드라인 + 본문) — 텍스트 해석을 위해 더 길게 전달
  const pageContents = {
    page1: [pages.page1?.headline, pages.page1?.body].filter(Boolean).join(' / '),
    page2: [pages.page2?.headline, pages.page2?.body].filter(Boolean).join(' / '),
    page3: [pages.page3?.headline, pages.page3?.body].filter(Boolean).join(' / '),
  };

  const PV = pageVisualDirections(laneOf(bookInfo.category)); // 레인별 1페이지 감정 반영

  const text = await callLightModel(env, {
    
    max_tokens: 1000,
    system: '당신은 한국 웹툰풍 감성 일러스트 아트 디렉터입니다. 연애·관계(설렘·이별·자존감) 주제의 책 카드뉴스 배경으로 쓸 Flux 이미지 영어 프롬프트를 작성합니다.\n\n[인물 배치 — 매우 중요·절대 규칙] 사람(30대 한국 여성)은 오직 1페이지(표지)에만 등장합니다.\n· 1페이지: 그녀(스크롤을 멈추는 표지 컷).\n· 2·3페이지: 사람을 절대 넣지 마세요. 사람 얼굴·인물·실루엣·손 모두 금지. 오직 사물·공간·풍경으로 감정을 상징하는 "무인(no people)" 장면만 묘사합니다.\n\n[손·손가락 규칙] 무료 AI는 손·손가락을 자주 뭉갭니다. 1페이지 인물도 손은 소매·주머니에 넣거나 프레임 밖으로 두고, 손가락 클로즈업은 피하세요.\n\n[스타일 고정 — 3장 공통] "귀엽고 퀄리티 높은 애니풍" 일러스트: 깔끔한 라인, 부드러운 플랫 셀 셰이딩, 포근한 빛. 실사·반실사·3D 렌더 절대 금지. 색감·분위기는 시스템이 주제에 맞게 자동으로 덧붙이므로 너는 장면·감정에 집중. 3장이 한 시리즈로 묶이게. (4페이지는 시스템이 1페이지 이미지를 흐려 책 표지와 합성하므로 생성하지 않음)\n\n[2~3페이지 무인 장면 발상] 창가·카페 한켠·침대맡·책상·골목·버스 안, 휴대폰·편지·머그·담요·우산·책, 빈 의자, 비 오는 유리창, 저물녘→새벽빛 등 사물·공간으로 감정을 상징. 2장의 장소·구도가 서로 뚜렷이 다르게.\n\n[규칙]\n1. 구도·조명 구체적으로 (wide shot, soft window light, golden morning light)\n2. 2~3페이지는 반드시 사람 없음(no people, no person, no figure)\n3. 텍스트·글자·숫자 없음 (no text, no letters, no words)\n4. 하단 30%는 부드럽고 단순하게 (텍스트 오버레이 공간)\n5. 각 프롬프트 영어 25~55단어. 인물 외형·화풍은 시스템이 자동으로 덧붙이므로, 너는 "그 장의 장면·사물·감정·장소"에 집중.\n반드시 JSON만 응답한다.',
    user: `책 제목: ${bookInfo.title || ''}\n카테고리: ${bookInfo.category || '이별·재회·회복'}\n책 핵심 주제: ${bookInfo.coreMessage || ''}\n\n1페이지만 인물(그녀). 2·3페이지는 사람 없는 무인 분위기 배경으로만 묘사하세요. (4페이지는 시스템이 합성 — 생성 불필요)\n\n1페이지 ${PV.page1}\n  문장: ${pageContents.page1}\n2페이지 ${PV.page2}\n  문장: ${pageContents.page2}\n3페이지 ${PV.page3}\n  문장: ${pageContents.page3}\n\n[필수] 3장의 장소·구도가 서로 겹치지 않게. 인물은 1페이지에만, 2·3페이지는 사람 없음. 텍스트·글자 없음.\n\nJSON: {"page1":"...","page2":"...","page3":"..."}`,
  });

  const parsed = extractJson(text);

  // ⭐ 인물은 오직 1페이지(표지)에만. 2~5페이지는 무인 장면(인체 할루시네이션 원천 차단).
  const PERSON_PAGES = new Set(['page1']);

  // 3페이지 프롬프트만 추려 검증 — 누락 시 페이지별 폴백으로 보완 (4페이지는 합성)
  const prompts = {};
  for (let i = 1; i <= 3; i++) {
    const key = `page${i}`;
    const v = parsed[key];
    prompts[key] = (v && typeof v === 'string' && v.trim()) ? v.trim() : FALLBACK_IMAGE_PROMPTS[key];
  }

  // 페이지별로 앵커를 다르게 붙인다: 1페이지=캐릭터 앵커, 2~5페이지=무인 장면 앵커.
  // 화풍·색감 앵커(STYLE_ANCHOR)는 5장 공통 → 인물/배경이 한 시리즈로 묶인다.
  const base = 'https://image.pollinations.ai/prompt/';
  const tail = ', no text, no letters, no words, high quality';
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const mood = categoryMood(bookInfo.category);   // 주제별 분위기·색감(이별·자존감·설렘 등)
  const images = {};
  const fullPrompts = {};   // 앵커까지 합친 최종 프롬프트 — page1을 Gemini로 보낼 때 사용
  for (const [page, prompt] of Object.entries(prompts)) {
    const seed = Math.floor(Math.random() * 900000) + 100000;
    let anchor, faceTail = '';
    if (PERSON_PAGES.has(page)) {
      // 자세를 "얼굴 안 보임(뒷모습)" 또는 "얼굴 보임(앞·옆)" 그룹에서 뽑고,
      // 그 그룹에 맞는 꼬리말만 붙인다(뒷모습+얼굴묘사 충돌 → 고개 꺾임 방지).
      const useBack = Math.random() < 0.5;
      const pose = useBack ? pick(POSES_BACK) : pick(POSES_FACE);
      anchor = `${CHARACTER_ANCHOR}, ${pose}, ${pick(SETTING_VARIATIONS)}`;
      faceTail = (useBack ? BACK_TAIL : PERSON_FACE_TAIL) + ANATOMY_TAIL;
    } else {
      anchor = SCENE_ANCHOR;
    }
    const full = `${prompt}, ${anchor}, ${STYLE_ANCHOR}, ${mood}${faceTail}${tail}`;
    fullPrompts[page] = full;
    images[page] = `${base}${encodeURIComponent(full)}?width=1080&height=1080&nologo=true&seed=${seed}&model=flux&enhance=true`;
  }

  return { success: true, images, prompts, fullPrompts };
}

// ===== Gemini 이미지(표지 전용) =====
// 손·눈 등 인체 하자가 가장 적은 모델로 "1페이지 표지"만 생성한다(비용 절감: 나머지는 무료).
// 키(GEMINI_API_KEY) 없거나 실패하면 null → 호출부가 무료 Pollinations로 폴백한다.
const GEMINI_IMAGE_MODEL = 'gemini-2.5-flash-image'; // 일명 Nano Banana(텍스트→이미지, inlineData 반환)
// 표지는 특히 인체 하자가 도드라지므로, 실패하기 쉬운 요소(손가락·정면 눈 클로즈업)를
// 강하게 배제하는 지시를 덧붙인다(모델을 바꿔도 이 구도 회피가 하자율을 크게 낮춘다).
const GEMINI_SAFE_ANATOMY =
  ' Composition rules (critical): do NOT show hands or fingers at all — keep hands hidden in sleeves or pockets or fully out of frame. ' +
  'Avoid any close-up of the face; show her from behind, or in three-quarter view, or with eyes gently closed, or as a small distant figure. ' +
  'Flat 2D Japanese anime illustration, clean cel shading, soft anime eyes — not photorealistic, not 3D. ' +
  'Anatomy must be natural and correct: head and neck aligned with the body, no twisted neck, no extra or missing limbs, no malformed hands, no distorted eyes.';

// Gemini 키 해석: Cloudflare 시크릿(env.GEMINI_API_KEY) 우선, 없으면 앱에서 저장한
// KV 값(gemini_api_key)을 쓴다 → 사용자가 터미널·대시보드 없이 앱 화면에서 키를 넣게.
async function getGeminiKey(env) {
  if (env?.GEMINI_API_KEY) return env.GEMINI_API_KEY;
  try { return (await env?.PENDING_POSTS?.get('gemini_api_key')) || null; } catch { return null; }
}

// ===== Gemini 텍스트(보조 호출용) =====
// 정책: 핵심 생성(책 추천·캐럿셀 생성·재생성)은 감성 한국어 품질을 위해 Claude 유지,
// 보조 호출(검증·캡션·교정·적합성 게이트·텍스트 압축·분석·이미지 프롬프트)은
// 훨씬 저렴한 Gemini Flash-Lite로 처리한다. 실패·키 없음 시 Claude light로 자동 폴백.
const GEMINI_TEXT_MODEL = 'gemini-flash-lite-latest';
async function callGeminiText(apiKey, opts) {
  const { system, user, max_tokens = 1024 } = opts;
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TEXT_MODEL}:generateContent?key=${apiKey}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const res = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        systemInstruction: system ? { parts: [{ text: system }] } : undefined,
        contents: [{ role: 'user', parts: [{ text: user }] }],
        generationConfig: { maxOutputTokens: max_tokens, temperature: 0.7 },
      }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`[gemini ${res.status}]`);
    const d = await res.json();
    const t = (d?.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('');
    if (!t.trim()) throw new Error('gemini 빈 응답');
    return t;
  } catch (e) { clearTimeout(timer); throw e; }
}
// 보조 텍스트 호출 라우터 — Gemini(저렴) 우선, 실패 시 Claude light 폴백(안정성 유지).
async function callLightModel(env, opts) {
  const gk = await getGeminiKey(env);
  if (gk) {
    try { return await callGeminiText(gk, opts); } catch { /* Claude 폴백 */ }
  }
  return callClaude(env.ANTHROPIC_API_KEY, { ...opts, env, tier: 'light' });
}

async function generateGeminiImageBytes(apiKey, prompt) {
  if (!apiKey) return null;
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_IMAGE_MODEL}:generateContent?key=${apiKey}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 45000);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: `${prompt}${GEMINI_SAFE_ANATOMY} Square 1:1 image, no text or letters anywhere.` }] }],
        generationConfig: { responseModalities: ['IMAGE'] },
      }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    if (!res.ok) return null;
    const data = await res.json();
    const parts = data?.candidates?.[0]?.content?.parts || [];
    const img = parts.find(p => p.inlineData?.data);
    if (!img) return null;
    // base64 → 바이너리(Uint8Array)
    const b64 = img.inlineData.data;
    const bin = atob(b64);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return { bytes, mime: img.inlineData.mimeType || 'image/png' };
  } catch {
    clearTimeout(timer);
    return null;
  }
}

// 유료 이미지(표지) 일일 사용량 — 구글 청구 폭주 방지. Claude 예산과 별개 카운터.
const DAILY_IMAGE_CAP = 40; // 하루 유료 표지 40장(자동 1편+수동 몇 편이면 충분)
async function bumpImageUsage(env) {
  if (!env?.PENDING_POSTS) return 0;
  const key = `img_usage_${_kstDay()}`;
  let n = 0;
  try { n = parseInt(await env.PENDING_POSTS.get(key) || '0', 10) || 0; } catch {}
  n += 1;
  try { await env.PENDING_POSTS.put(key, String(n), { expirationTtl: 2 * 24 * 3600 }); } catch {}
  return n;
}
async function getImageUsage(env) {
  if (!env?.PENDING_POSTS) return 0;
  try { return parseInt(await env.PENDING_POSTS.get(`img_usage_${_kstDay()}`) || '0', 10) || 0; } catch { return 0; }
}

// (제거됨) 릴스 별도 문구 생성 — 문구 통일 정책: 릴스는 캐럿셀 4페이지 문구를 그대로 사용(프론트에서 배치만 다르게 렌더).

async function handleGenerateCaption(env, body) {
  const { pages, bookInfo, dmKeyword, bookNumber } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 댓글 키워드 힌트: 특수기호만 제거하고 원형 그대로 Claude에 전달.
  // Claude가 자연스러운 완결 단어(2~3자)를 직접 선택한다 — 강제 절단 금지.
  const kwHint = (dmKeyword || bookInfo.category || '독서').replace(/[^가-힣a-zA-Z0-9]/g, '') || '독서';
  const lt = laneTone(bookInfo.category); // 3레인 톤(설렘/이별/자존감)

  const text = await callLightModel(env, {
    
    max_tokens: 512,
    system: `당신은 ${lt.theme}를 다루는 연애 책을 소개하는 인스타그램 콘텐츠 크리에이터입니다. ${lt.audience} 독자가 자기 마음을 들킨 듯 공감해 "저장"하고 "친구에게 공유"하고 싶어지는 캡션을 씁니다. 톤: ${lt.tone}. 팔로워 성장이 목적이므로 저장·공유를 유도합니다. 노골적 판매·공포·단정·비난 금지. 반말 절대 금지 — 문어체·존댓말(~습니다/~네요/~까요)만. 반드시 JSON만 응답합니다.`,
    user: `책 카테고리: ${bookInfo.category || '이별과회복'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n캐럿셀 첫 줄 훅: ${pages.page1?.headline || ''}\n\n인스타그램 캡션을 작성하세요. (이 게시물의 목적: 저장·공유로 팔로워 늘리기. 댓글·DM·A/B 유도 없음.)\n\n[캡션 구조 — 순서 엄수]\n1줄: 독자가 ${lt.theme}에서 혼자 느꼈을 감정을 포착한 공감형 한 문장 (책 제목은 시스템이 따로 붙이므로 본문엔 쓰지 말 것. "당신이 모른다면"·"대부분의 사람들이" 금지. 공포·단정 금지)\n2~3줄: 캐럿셀 핵심 위로/통찰 초간결 요약 (반복 금지)\n끝에서 둘째 줄: 저장 유도 ("마음이 복잡한 날 다시 꺼내보고 싶다면 저장해두세요" 형태)\n마지막 줄: 공유 유도 ("같은 마음을 지나는 사람에게 조용히 건네주세요" 형태)\n\n[추가 규칙]\n- 해시태그: 정확히 3개 (카테고리에 맞게. 예: ${lt.hashtagExample})\n- 전체 6줄 이내, 짧고 따뜻하게\n- 댓글·DM·A/B·"프로필 링크" 언급 금지 (저장·공유만)\n\nJSON: {"caption":"1줄\\n2줄\\n3줄\\n저장유도줄\\n공유유도줄","hashtags":["#이별","#연애심리","#책추천"]}`,
  });

  const result = extractJson(text);
  if (result.caption) result.caption = fixCommonKoreanErrors(result.caption); // 규칙 교정(무료)
  result.dmKeyword = (bookInfo.category || '책').replace(/[^가-힣a-zA-Z0-9]/g, '').slice(0, 4) || '책';
  // 캡션 끝에 오늘의 책 공개(제목·저자) + 계정 핸들 + 프로필 링크 유도.
  // (프로필 바이오의 도서관 링크에 구매 링크가 있으므로 책을 만나고 싶은 사람을 그쪽으로 유도)
  const HANDLE = '@love.between_lines';
  const profileLine = `${HANDLE} 프로필 링크에서 오늘의 책을 만나보세요`;
  if (bookInfo.title) {
    const by = bookInfo.author ? ` · ${bookInfo.author}` : '';
    result.caption = (result.caption || '') + `\n\n오늘의 책 · 「${bookInfo.title}」${by}\n${profileLine}`;
  } else {
    result.caption = (result.caption || '') + `\n\n${profileLine}`;
  }
  return { success: true, ...result };
}

async function handleRegenerate(env, body) {
  const { bookInfo, previousPages, feedback, improvements } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main',
    system: `당신은 연애·관계 심리 책을 소개하는 인스타그램 카드뉴스 전문 카피라이터입니다.\n핵심 규칙(절대 위반 금지):\n1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.\n2. 각 페이지 텍스트는 최소한의 단어로 마음을 건드린다 — 장황한 설명 금지.\n3. 공포·단정·비난이 아니라 깊은 공감과 위로. 통계·수치·연구 인용 금지, 감정과 경험의 언어만.\n4. 마지막(4)페이지는 질문·A/B·"댓글" 언급 없이 따뜻한 마무리 한 문장으로 감싼다.\n5. 반말 절대 금지 — 문어체·존댓말(~습니다/~네요/~까요)만.\n반드시 JSON만 응답한다.`,
    user: `캐럿셀을 피드백에 맞게 개선하세요.\n카테고리: ${bookInfo.category || '연애·관계 심리'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n${bookInfo.description ? `실제 책 소개(출판사 — 통찰·솔루션은 이 소개의 주제와 일치해야 하며, 소개에 없는 개념을 책의 것처럼 지어내지 말 것): ${String(bookInfo.description).slice(0, 600)}\n` : ''}\n이전 버전:\n${JSON.stringify(previousPages, null, 2)}\n\n피드백: ${feedback}\n개선 요청: ${improvements.join(' / ')}\n\n[연결성 — 최우선] 개선본도 4페이지가 "한 편의 편지"처럼 매끄럽게 이어져야 합니다. 1페이지 훅에서 꺼낸 하나의 장면·감정이 2·3페이지에서 같은 사람의 이야기로 계속 살아 있고(장면 → 패턴과 마음의 이유 → 바라보는 법), 4페이지가 그 여정을 감싸 안으며 책으로 건네야 합니다. 각 페이지는 앞 페이지가 남긴 감정을 이어받으세요(단, 억지 접속사로 잇지 말고 같은 표현 반복 금지). 갑자기 딴 이야기로 튀지 말 것.\n\n텍스트 길이 기준:\n- 1페이지 headline: 40자 이내 완전한 문장. 단어 조각 절대 금지. subtext 없음.\n- 2~3페이지 headline: 18자 이내, body: 3~5줄(줄당 40자 이내). 감정·장면 위주(수치·사례 금지).\n- 4페이지 cta: 3페이지를 잇는 따뜻한 마무리 한 문장 / linkText: 책을 건네는 다리 한 줄.\n\nJSON:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"cta":"...","linkText":"..."}}`
  });
  const pages = await proofreadPages(env, extractJson(text)); // 재생성본도 교정
  return { success: true, pages };
}

// 캔버스 넘침 감지 후 텍스트 단축
async function handleAdjustText(env, body) {
  const { pages, bookInfo, issues } = body;
  if (!pages || !issues?.length) return { success: true, pages };

  const issueDesc = issues.map(i =>
    `${i.page} ${i.type}: ${i.currentLines}줄(최대 ${i.maxLines}줄) — "${i.text}"`
  ).join('\n');

  let text;
  try {
    text = await callLightModel(env, {
      
      max_tokens: 1024,
      optional: true, // 예산 절약 모드에서 생략(폴백: 원본 텍스트 유지)
      system: '당신은 인스타그램 카드뉴스 카피라이터입니다. 주어진 텍스트를 지정된 줄 수 이내로 압축합니다. 반말 절대 금지 — 문어체·존댓말만 허용. 반드시 JSON만 응답합니다.',
    user: `다음 캐럿셀 텍스트가 이미지 레이아웃에서 넘칩니다. 각 항목을 지정된 최대 줄 수 이내로 압축하세요.\n의미·임팩트는 유지하되 더 간결하게 다듬어주세요.\n\n현재 캐럿셀:\n${JSON.stringify(pages, null, 2)}\n\n넘치는 항목:\n${issueDesc}\n\n압축 규칙:\n- headline: 최대 3줄 (40자 이내, 강렬하게)\n- body: 최대 5줄 (줄당 45자 이내)\n- 책 제목·저자명 절대 노출 금지\n\n전체 pages JSON을 반환하세요:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"cta":"...","linkText":"..."}}`,
    });
  } catch {
    return { success: true, pages }; // 예산 절약 생략·호출 실패 시 원본 유지
  }

  try {
    return { success: true, pages: extractJson(text) };
  } catch {
    return { success: true, pages }; // 파싱 실패 시 원본 유지
  }
}

// ===== Phase 5 준비: DM 자동 회신 내용 생성 =====
async function handleGenerateDmReply(env, body) {
  // ⭐ DM 기능 폐기(저장·공유 전략). Claude를 호출하지 않는다(데이터 낭비 방지).
  return { success: true, disabled: true, dmText: '' };
}
async function logStep(env, pipelineId, entry) {
  if (!env.PENDING_POSTS || !pipelineId) return;
  const key = `plog_${pipelineId}`;
  let log = [];
  try { log = (await env.PENDING_POSTS.get(key, 'json')) || []; } catch {}
  log.push({ ts: new Date().toISOString(), ...entry });
  if (log.length > 200) log = log.slice(-200);
  try { await env.PENDING_POSTS.put(key, JSON.stringify(log), { expirationTtl: PLOG_TTL }); } catch {}
}

async function runStep(env, pipelineId, step) {
  // 항상 KV에서 최신 상태를 읽어 이전 단계 결과를 활용
  const state = (await env.PENDING_POSTS?.get(`pipeline_${pipelineId}`, 'json').catch(() => null)) || {};
  const { affiliateLinks = [], commentKeyword = '', bookNumber = '', models: savedModels } = state;
  let bookInfo = state.bookInfo; // autoSelect 모드에서는 1단계에서 채워진다

  // 단계별 Worker 인스턴스가 새로 뜨므로 _modelCache가 리셋됨 — KV에 저장된 값으로 복원
  if (savedModels?.main && !_modelCache) {
    _modelCache = { main: savedModels.main, light: savedModels.light };
  }

  const t0 = Date.now();
  const setActive = (label) => savePipelineStatus(env, pipelineId, { step, stepStatus: 'active', runningStep: step, label });

  if (step === 1) {
    // ⭐ 책 자동 선정(autoSelect) — 브라우저가 아니라 크론 문맥에서 책을 고른다.
    // 지역 라우팅 차단(REGION_BLOCKED) 등 일시 오류가 나도 크론 재시도가 다른
    // 경유지에서 다시 시도하므로 결정적으로 완수된다. 선정 즉시 KV에 저장되어
    // 이후 재시도에서는 이 블록을 건너뛴다(중복 선정 방지).
    if (!bookInfo?.title && state.autoSelect) {
      const as = state.autoSelect;
      if (as.title) {
        // 제목 직접 입력 모드 — 서버(크론)가 분석까지 수행(브라우저 Claude 호출 제거)
        await setActive(`책 정보 분석 중... (${as.title})`);
        const an = await handleAnalyze(env, { title: as.title, author: as.author || '' });
        if (an.notFound) throw new Error(`BOOK_NOT_FOUND: "${as.title}"은(는) 실제 출간된 책으로 확인되지 않습니다. 제목·저자를 확인해주세요.`);
        bookInfo = {
          title: an.verifiedTitle || as.title,
          author: an.author || as.author || '',
          year: an.year || '',
          category: as.category || an.category || '',
          coreMessage: an.coreMessage || '',
          targetAudience: an.targetAudience || '',
        };
      } else {
        await setActive('AI가 책을 자동 선정 중...');
        const sd = await handleSuggest(env, { category: as.category, issue: as.issue || '', excludeTitles: as.excludeTitles || [] });
        const chosen = (sd.books || [])[0];
        if (!chosen) throw new Error('책 추천을 받지 못했습니다 — 잠시 후 다시 시도해주세요.');
        bookInfo = {
          title: chosen.title, author: chosen.author || '', year: chosen.year || '',
          category: as.category || chosen.category || '', // 레인 고정 — 톤 일관성
          coreMessage: chosen.coreMessage || chosen.reason || '',
          targetAudience: chosen.targetAudience || '',
          description: chosen.description || '', // 실제 책 소개 — 생성·검증 근거
        };
      }
      await savePipelineStatus(env, pipelineId, { bookInfo, label: `책 선정: ${bookInfo.title}` });
      await logStep(env, pipelineId, { step, phase: 'book-selected', note: `${bookInfo.title} / ${bookInfo.author}` });
      if (state.isAutoDaily && bookInfo.title) {
        // 일일 자동: 사용 책 기록(최근 30권) — 다음 날 중복 추천 방지
        // (bookInfo.title 사용 — chosen은 else 블록 지역변수라 여기선 접근 불가)
        try {
          const usedStr = await env.PENDING_POSTS.get('daily_used_books');
          const used = usedStr ? JSON.parse(usedStr) : [];
          await env.PENDING_POSTS.put('daily_used_books', JSON.stringify([...used, bookInfo.title].slice(-30)), { expirationTtl: 31 * 24 * 3600 });
        } catch {}
      }
    }
    if (!bookInfo?.title) throw new Error('책 정보가 없습니다.');
    await setActive('Claude AI가 4페이지 카드뉴스를 작성 중...');
    await logStep(env, pipelineId, { step, phase: 'start', model: _modelCache?.main });
    // 1단계(생성) 실패는 치명적 → throw하여 advancePipeline이 error로 마감
    const genData = await handleGenerate(env, bookInfo);
    const pages = genData.pages;
    const patch = { step: 1, stepStatus: 'done', label: '4페이지 카드뉴스 생성 완료', pages };
    if (genData.bookCover) patch.bookCover = genData.bookCover;   // 마지막 장 표지
    if (genData.bookDescription) patch.bookDescription = genData.bookDescription; // 검증 근거(실제 책 소개)
    // 교차검증으로 저자가 교정됐으면 bookInfo에 반영(이후 단계·도서관·DM에 진짜 저자 사용)
    if (genData.correctedBook) {
      const fixed = { ...bookInfo, title: genData.correctedBook.title || bookInfo.title, author: genData.correctedBook.author || bookInfo.author };
      patch.bookInfo = fixed;
    }
    // 모델 ID를 KV에 저장 → 이후 단계에서 재프로빙 없이 재활용
    if (_modelCache?.main) patch.models = { main: _modelCache.main, light: _modelCache.light };
    await savePipelineStatus(env, pipelineId, patch);
    await logStep(env, pipelineId, { step, phase: 'done', model: _modelCache?.main, durationMs: Date.now() - t0 });

  } else if (step === 2) {
    const { pages } = state;
    await setActive('AI 자동 품질 평가 중...');
    await logStep(env, pipelineId, { step, phase: 'start' });
    // 실제 책 소개를 검증·재생성에 근거로 전달 — 부합도를 추측이 아닌 사실로 채점
    const gBook = { ...bookInfo, description: state.bookDescription || '' };
    let updatedPages = pages;
    let validation = null;
    try {
      for (let attempt = 1; attempt <= 2; attempt++) {
        validation = await handleValidate(env, { pages: updatedPages, bookInfo: gBook });
        if (validation.approved) break;
        // ⭐ 크레딧 절약: 재생성(main 모델 2회분)은 품질이 명백히 낮을 때(60점 미만)만.
        // 60~69점은 미세 개선 여지라 재생성 비용 대비 이득이 적다 → 그대로 통과시켜 발송.
        if ((validation.totalScore || 0) >= 60) break;
        if (attempt < 2) {
          const rd = await handleRegenerate(env, { bookInfo: gBook, previousPages: updatedPages, feedback: validation.feedback, improvements: validation.improvements || [] });
          updatedPages = rd.pages;
        }
      }
    } catch (e) {
      await logStep(env, pipelineId, { step, phase: 'warn', error: '검증 실패(계속 진행): ' + e.message });
    }
    await savePipelineStatus(env, pipelineId, { step: 2, stepStatus: 'done', label: `${validation?.totalScore || 0}/100점`, pages: updatedPages, validation });
    await logStep(env, pipelineId, { step, phase: 'done', durationMs: Date.now() - t0, note: `score ${validation?.totalScore || 0}` });

  } else if (step === 3) {
    // ⭐ 3단계는 "이어하기(재개) 가능" 설계 — 한 번에 다 받으려다 2분을 넘기면 크론이
    // 멈춤으로 오판해 중복 실행(표지 중복 과금·429 폭풍)하던 문제의 근본 해결.
    // 진행 상황(imgProg)을 저장하고 stepStatus='partial'로 두면, 다음 advancePipeline이
    // 스테일 대기 없이 같은 단계를 이어서 실행한다. 표지·프롬프트 생성은 정확히 1회.
    const { pages } = state;
    const pageKeys = ['page1', 'page2', 'page3'];  // 4페이지는 프론트가 1페이지 흐림배경+책표지로 합성
    const MAX_TRIES = 3;   // 페이지당 총 시도(틱에 걸쳐) — 초과 시 원본 URL 폴백

    // (1회만) 이미지 프롬프트·URL 생성 → 상태에 고정 (재진입 시 Claude 재호출 방지)
    let urlMap = state.imgUrls || null;
    let fullPrompts = state.imgFullPrompts || null;
    if (!urlMap) {
      await setActive('AI 이미지 프롬프트 생성 중...');
      await logStep(env, pipelineId, { step, phase: 'start' });
      try {
        const imgData = await handleGenerateImages(env, { pages, bookInfo });
        urlMap = imgData.images || {};
        fullPrompts = imgData.fullPrompts || {};
      } catch (e) {
        await logStep(env, pipelineId, { step, phase: 'warn', error: '이미지 프롬프트 생성 실패(계속 진행): ' + e.message });
        urlMap = {}; fullPrompts = {};
      }
      await savePipelineStatus(env, pipelineId, { step: 3, stepStatus: 'partial', runningStep: 3, imgUrls: urlMap, imgFullPrompts: fullPrompts, label: '이미지 준비 완료 — 내려받기 시작' });
    }

    const prog = state.imgProg || { done: {}, tries: {}, coverTried: false };

    // Gemini 표지 — 정확히 1회만 시도(coverTried 플래그로 중복 과금 차단)
    if (!prog.coverTried && !prog.done.page1) {
      prog.coverTried = true;
      const geminiKey = await getGeminiKey(env);
      if (geminiKey && fullPrompts?.page1 && (await getImageUsage(env)) < DAILY_IMAGE_CAP) {
        await setActive('표지 이미지 생성 중 (Gemini)...');
        const g = await generateGeminiImageBytes(geminiKey, fullPrompts.page1);
        if (g?.bytes?.length) {
          await env.PENDING_POSTS.put(`img_${pipelineId}_page1`, g.bytes, { expirationTtl: 24 * 3600 });
          await bumpImageUsage(env);
          prog.done.page1 = true;
          await logStep(env, pipelineId, { step, phase: 'cover', note: `Gemini 표지 생성 (${g.bytes.length} bytes)` });
        } else {
          await logStep(env, pipelineId, { step, phase: 'warn', error: 'Gemini 표지 실패 → 무료 폴백' });
        }
      }
      await savePipelineStatus(env, pipelineId, { step: 3, stepStatus: 'partial', runningStep: 3, imgProg: prog, label: '본문 이미지 내려받는 중...' });
    }

    // 남은 페이지를 시간 예산 내에서 순차 다운로드. 페이지당 이번 틱 1회 시도만 —
    // 긴 백오프 대기 대신 "다음 크론 틱"이 자연스러운 간격(무료 티어 429 회피)이 된다.
    const TICK_DEADLINE = Date.now() + 40 * 1000;
    for (const page of pageKeys) {
      if (prog.done[page]) continue;
      if ((prog.tries[page] || 0) >= MAX_TRIES) continue;
      if (!urlMap[page]) { prog.tries[page] = MAX_TRIES; continue; }
      if (Date.now() > TICK_DEADLINE) break;
      prog.tries[page] = (prog.tries[page] || 0) + 1;
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 70000);
        const res = await fetch(urlMap[page], { signal: ctrl.signal });
        clearTimeout(timer);
        if (res.ok) {
          const buf = await res.arrayBuffer();
          await env.PENDING_POSTS.put(`img_${pipelineId}_${page}`, buf, { expirationTtl: 24 * 3600 });
          prog.done[page] = true;
        } else if (res.status !== 429 && res.status < 500) {
          prog.tries[page] = MAX_TRIES; // 영구 오류 — 재시도 무의미
          await logStep(env, pipelineId, { step, phase: 'warn', error: `${page} HTTP ${res.status} → 원본 URL 폴백` });
        }
        // 429/5xx는 tries만 늘리고 다음 틱에 재시도
      } catch (e) { /* 타임아웃·네트워크 → 다음 틱 재시도 */ }
      // 진행 저장(updatedAt 갱신 → 스테일 오판 방지) + 무료 티어 간격
      const doneCount = pageKeys.filter(p => prog.done[p]).length;
      await savePipelineStatus(env, pipelineId, { step: 3, stepStatus: 'partial', runningStep: 3, imgProg: prog, label: `본문 이미지 내려받는 중 (${doneCount}/${pageKeys.length})...` });
      await new Promise(r => setTimeout(r, 2000));
    }

    // 완료 판정: 전 페이지가 성공했거나 시도 소진 → 마감. 아니면 다음 틱이 이어서.
    const finished = pageKeys.every(p => prog.done[p] || (prog.tries[p] || 0) >= MAX_TRIES);
    if (!finished) return; // stepStatus='partial' 유지 — 다음 advancePipeline이 재진입

    const images = {};
    for (const p of pageKeys) {
      images[p] = prog.done[p] ? `/api/image?id=${pipelineId}&page=${p}` : (urlMap[p] || null);
      if (!prog.done[p] && urlMap[p]) await logStep(env, pipelineId, { step, phase: 'warn', error: `${p} 내려받기 실패 → 원본 URL 폴백(브라우저가 직접 로드)` });
    }
    images.page4 = images.page1; // 4페이지(책 공개) 배경 = 1페이지 이미지(프론트가 흐림 처리)
    await savePipelineStatus(env, pipelineId, { step: 3, stepStatus: 'done', label: '이미지 저장 완료', images });
    await logStep(env, pipelineId, { step, phase: 'done', durationMs: Date.now() - t0 });

  } else if (step === 4) {
    const { pages } = state;
    await setActive('인스타그램 캡션 작성 중...');
    await logStep(env, pipelineId, { step, phase: 'start' });
    let caption = '', hashtags = [], dmKeyword = '';
    try {
      const capData = await handleGenerateCaption(env, { pages, bookInfo, dmKeyword: commentKeyword, bookNumber });
      caption = capData.caption || '';
      hashtags = capData.hashtags || [];
      dmKeyword = capData.commentKeyword || capData.dmKeyword || '';
    } catch (e) {
      await logStep(env, pipelineId, { step, phase: 'warn', error: '캡션 생성 실패(계속 진행): ' + e.message });
    }
    // 릴스 문구는 별도 생성하지 않는다(문구 통일 정책) — 캐럿셀 4페이지 문구를 프론트가 그대로 배치.
    await savePipelineStatus(env, pipelineId, { step: 4, stepStatus: 'done', label: '캡션 + 해시태그 생성 완료', caption, hashtags, dmKeyword });
    await logStep(env, pipelineId, { step, phase: 'done', durationMs: Date.now() - t0 });

  } else if (step === 5) {
    // 새 전략(저장·공유 중심)에서는 DM 자동 회신을 만들지 않는다. 단계는 건너뛰며 통과.
    await savePipelineStatus(env, pipelineId, { step: 5, stepStatus: 'done', label: 'DM 단계 생략(새 전략: 저장·공유 중심)' });
    await logStep(env, pipelineId, { step, phase: 'skip', note: 'DM 미사용' });

  } else if (step === 6) {
    const { telegramSentAt } = state;
    // 중복 발송 방지: 이미 발송했으면 건너뜀 (크론 재실행 시 텔레그램 중복 방지)
    if (telegramSentAt) {
      await savePipelineStatus(env, pipelineId, { step: 6, stepStatus: 'done', label: '텔레그램 발송 완료(중복 방지)' });
      await logStep(env, pipelineId, { step, phase: 'skip', note: '이미 발송됨' });
    } else {
      await setActive('텔레그램으로 제작 완료 알림 발송 중...');
      await logStep(env, pipelineId, { step, phase: 'start' });
      let telegramError = null;
      try {
        // 텔레그램에는 완료 알림 + 확인 링크만 발송 (이미지·문구는 보내지 않음)
        await handleSendTelegram(env, { bookInfo, pipelineId });
      } catch (e) {
        telegramError = e.message;
      }
      await savePipelineStatus(env, pipelineId, {
        step: 6,
        stepStatus: telegramError ? 'error' : 'done',
        telegramSentAt: telegramError ? null : Date.now(),
        label: telegramError ? `텔레그램 발송 실패: ${telegramError}` : '텔레그램으로 완료 알림 + 확인 링크 발송 완료',
      });
      await logStep(env, pipelineId, { step, phase: telegramError ? 'error' : 'done', error: telegramError, durationMs: Date.now() - t0 });
    }

  } else if (step === 7) {
    const step6Error = state.step === 6 && state.stepStatus === 'error';
    // 도서관 등록은 "완전 자동(매일 크론)"일 때만 자동으로 한다.
    // 사람이 직접 만드는 경우엔 제작 페이지의 "도서관 등록" 메뉴에서 직접 올린다
    // (실제로 게시할 책만 등록 → 초안이 도서관을 어지럽히지 않게).
    if (state.isAutoDaily) {
      await addBookToCatalog(env, {
        bookInfo,
        bookNumber,
        pipelineId,
        coupangLink: state.affiliateLinks?.[0] || null,
        cover: state.bookCover || bookInfo?.cover || '',
      });
    }
    await savePipelineStatus(env, pipelineId, {
      step: 7,
      stepStatus: 'done',
      status: 'complete',
      label: step6Error ? '완료 (텔레그램 알림 실패 — 이 페이지에서 바로 게시 가능)' : '완료! 텔레그램 알림을 보냈습니다. 이 페이지에서 게시 여부를 결정하세요.',
      completedAt: Date.now(),
    });
    await logStep(env, pipelineId, { step, phase: 'complete' });
  }
}

// 파이프라인을 한 단계 전진시킨다 (시작 직후 킥 + 크론 양쪽에서 호출).
// 진행중 단계가 살아있으면 손대지 않고, 멈춘(stale) 단계만 재실행 → 중복 없이 자가복구.
async function advancePipeline(env, pipelineId) {
  const state = await env.PENDING_POSTS?.get(`pipeline_${pipelineId}`, 'json').catch(() => null);
  if (!state || state.status !== 'running') return;

  const step = state.step || 0;
  const stepStatus = state.stepStatus || 'done';
  const age = Date.now() - (state.updatedAt || 0);

  let nextStep;
  if (stepStatus === 'partial') {
    // 이어하기 가능 단계(3단계 이미지) — 스테일 대기 없이 같은 단계를 바로 재진입.
    // 진행 상황이 상태에 저장돼 있어 중복 작업·중복 과금 없음(멱등).
    nextStep = step;
  } else if (stepStatus === 'active') {
    if (age < STEP_STALE_MS) return;             // 아직 진행중 — 건드리지 않음
    nextStep = state.runningStep || step || 1;   // 멈춘 단계를 재실행
    await logStep(env, pipelineId, { step: nextStep, phase: 'recover', note: `${Math.round(age / 1000)}s 멈춤 → 재실행` });
  } else if (stepStatus === 'error') {
    // 일시적 오류(403·429·5xx·네트워크)는 크론이 같은 단계를 자동 재시도 → 자가복구.
    // 영구 오류이거나 재시도 한도 초과면 status를 error로 마감(이후 크론이 더는 집지 않음).
    const retries = state.errorRetries || 0;
    if (retries >= MAX_ERROR_RETRIES || !isTransientPipelineError(state.error)) {
      if (state.status !== 'error') {
        await savePipelineStatus(env, pipelineId, { status: 'error', label: `단계 ${step} 실패(자동 복구 불가): ${state.error || ''}` });
      }
      return;
    }
    if (age < ERROR_RETRY_MS) return;              // 재시도 최소 간격 확보
    nextStep = step;                                // 실패한 단계를 다시 실행
    await logStep(env, pipelineId, { step: nextStep, phase: 'recover', note: `일시 오류 재시도 ${retries + 1}/${MAX_ERROR_RETRIES}` });
  } else {
    nextStep = step + 1;                           // 이전 단계 done → 다음 단계
  }

  if (nextStep > 7) {
    await savePipelineStatus(env, pipelineId, { status: 'complete', stepStatus: 'done' });
    return;
  }

  try {
    await runStep(env, pipelineId, nextStep);
  } catch (e) {
    const retries = (state.errorRetries || 0) + 1;
    if (isTransientPipelineError(e.message) && retries <= MAX_ERROR_RETRIES) {
      // 일시적 오류 → running 유지 + 카운터 증가. 크론 다음 틱이 같은 단계를 재시도한다.
      await savePipelineStatus(env, pipelineId, {
        status: 'running', step: nextStep, stepStatus: 'error', errorRetries: retries,
        label: `단계 ${nextStep} 일시 오류 — 자동 재시도 중 (${retries}/${MAX_ERROR_RETRIES})`,
        error: e.message,
      });
      await logStep(env, pipelineId, { step: nextStep, phase: 'retry', error: e.message, note: `${retries}/${MAX_ERROR_RETRIES}` });
    } else {
      // 영구 오류이거나 한도 초과 → 파이프라인 마감
      await savePipelineStatus(env, pipelineId, { status: 'error', step: nextStep, stepStatus: 'error', label: `단계 ${nextStep} 실패: ${e.message}`, error: e.message });
      await logStep(env, pipelineId, { step: nextStep, phase: 'error', error: e.message });
    }
  }
}

// 매일 오전 8시(KST) 크론에서 호출 — 요일별 카테고리로 책을 자동 선정해 파이프라인을 시작
async function runDailyAuto(env) {
  if (!env.ANTHROPIC_API_KEY || !env.PENDING_POSTS) return;

  // KST 기준 오늘 날짜 계산 (UTC+9)
  const kstNow = new Date(Date.now() + 9 * 60 * 60 * 1000);
  const todayStr = kstNow.toISOString().slice(0, 10); // YYYY-MM-DD

  // 오늘 이미 자동 실행됐으면 스킵 (크론 중복 방지)
  const todayKey = `daily_auto_${todayStr}`;
  const alreadyRan = await env.PENDING_POSTS.get(todayKey).catch(() => null);
  if (alreadyRan) return;

  // ⭐ 3레인 톤 교차 편성 — 정체성(연애 책방)은 하나, 감정 구간만 넓힌다.
  // 설렘(가벼움·이탈 방지) 3일 / 이별·회복(수익 핵심) 2일 / 자존감(깊은 위로) 2일.
  // 인접한 요일에 같은 레인이 오지 않게 배치(주 경계 포함: 토 자존감 → 일 설렘).
  const LANES = ['짝사랑과설렘', '이별과회복', '자존감과사랑'];
  const DAILY_CATEGORIES = ['짝사랑과설렘', '이별과회복', '자존감과사랑', '짝사랑과설렘', '이별과회복', '짝사랑과설렘', '자존감과사랑'];
  let category = DAILY_CATEGORIES[kstNow.getDay()];

  // ⭐ 직전 주제 중복 방지 — 마지막 자동 생성과 같은 카테고리면 다음 레인으로 회피.
  // (크론 누락·수동 실행 등으로 편성이 어긋나도 이틀 연속 같은 주제가 나오지 않게 하는 안전장치)
  const lastCategory = await env.PENDING_POSTS.get('last_daily_category').catch(() => null);
  if (lastCategory && lastCategory === category) {
    category = LANES[(LANES.indexOf(category) + 1) % LANES.length];
  }

  // 최근 30일 내 사용한 책 목록 (중복 추천 방지)
  const usedStr = await env.PENDING_POSTS.get('daily_used_books').catch(() => null);
  const usedBooks = usedStr ? JSON.parse(usedStr) : [];

  // ⭐ 책 선정은 여기서 하지 않는다 — 이 크론은 하루 1회뿐이라, 여기서 Claude를
  // 직접 부르다 일시 오류(지역 차단·과부하)가 나면 그날 포스트가 통째로 사라진다.
  // 대신 autoSelect 파이프라인만 만들어 두면, 1분 크론 상태머신이 책 선정부터
  // 재시도(최대 5회)와 함께 결정적으로 완수한다.
  const pipelineId = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  await savePipelineStatus(env, pipelineId, {
    status: 'running',
    step: 0,
    stepStatus: 'done',
    bookInfo: null,
    autoSelect: { category, excludeTitles: usedBooks.slice(-20) },
    affiliateLinks: [],
    commentKeyword: category,
    startedAt: Date.now(),
    label: `[자동] 파이프라인 시작 — 책 자동 선정 대기 (${category})`,
    isAutoDaily: true,
  });
  await logStep(env, pipelineId, { step: 0, phase: 'start', note: `[자동] 카테고리: ${category} (책은 1단계에서 자동 선정)` });

  // 오늘 실행 기록 저장 (25시간 TTL — 다음 날 자동 실행 전까지 중복 방지)
  await env.PENDING_POSTS.put(todayKey, pipelineId, { expirationTtl: 25 * 3600 });

  // 오늘 사용한 카테고리 기록 — 내일 같은 주제가 연속으로 나오지 않게 (3일 보관)
  await env.PENDING_POSTS.put('last_daily_category', category, { expirationTtl: 3 * 24 * 3600 }).catch(() => {});
}

// 크론(매 1분)에서 호출 — 진행중 파이프라인을 찾아 각각 한 단계씩 전진.
// KV list()를 쓰지 않고 active_pipelines 인덱스(get 1회)만 읽는다 → 무료 list 한도 절약.
async function runScheduled(env) {
  if (!env.PENDING_POSTS) return;
  let ids = [];
  try { ids = (await env.PENDING_POSTS.get('active_pipelines', 'json')) || []; } catch {}
  if (!ids.length) return;

  // 크론(예산 넉넉)은 한 틱에서 파이프라인을 "여러 단계 연속" 전진시킨다.
  // advancePipeline은 runStep을 await로 끝까지 실행하므로, 루프를 돌면 생성→검증→
  // 이미지→캡션→… 이 한 인보케이션 안에서 이어진다 → 단계마다 1분씩 기다리는
  // 지연 누적(최대 7분)을 없앤다. 각 파이프라인 시작 전 예산(시간)만 확인.
  const DEADLINE = Date.now() + 55 * 1000; // 한 틱 최대 ~55초 작업(크론 벽시계 여유 내)
  const stale = [];
  let touched = 0;
  for (const id of ids) {
    if (Date.now() > DEADLINE || touched >= 8) break;
    const state = await env.PENDING_POSTS.get(`pipeline_${id}`, 'json').catch(() => null);
    if (!state) { stale.push(id); continue; }                 // 만료·삭제 → 인덱스 정리
    if (state.status !== 'running') { stale.push(id); continue; } // 완료·오류 → 인덱스 정리
    touched++;
    // 이 파이프라인을 예산이 허용하는 한 연속 전진(진전이 없으면 다음으로)
    let prevStep = -1, prevStatus = '', prevUpdated = 0;
    for (let k = 0; k < 12; k++) {
      if (Date.now() > DEADLINE) break;
      await advancePipeline(env, id);
      const st = await env.PENDING_POSTS.get(`pipeline_${id}`, 'json').catch(() => null);
      if (!st || st.status !== 'running') break;              // 완료·오류·소멸 → 종료
      // 진전 판정: 단계/상태뿐 아니라 updatedAt도 본다 — partial(이미지 이어받기)은
      // 단계가 같아도 진행 저장 때마다 updatedAt이 갱신되므로 계속 이어서 돌 수 있다.
      const upd = st.updatedAt || 0;
      if (st.step === prevStep && st.stepStatus === prevStatus && upd === prevUpdated) break;
      prevStep = st.step; prevStatus = st.stepStatus; prevUpdated = upd;
    }
  }
  // 끝난(또는 사라진) 파이프라인을 인덱스에서 한 번에 제거
  if (stale.length) {
    const next = ids.filter(x => !stale.includes(x));
    await env.PENDING_POSTS.put('active_pipelines', JSON.stringify(next));
  }
}

async function handlePipelineStepEndpoint(env, ctx, body) {
  // 수동 넛지 엔드포인트(옵션) — self-fetch 사슬은 더 이상 쓰지 않음. 크론이 주 구동자.
  const { pipelineId } = body;
  if (!pipelineId || !env.PENDING_POSTS) return { ok: true };
  ctx.waitUntil(advancePipeline(env, pipelineId).catch(() => {}));
  return { ok: true };
}

async function handlePipelineLog(env, url) {
  const pipelineId = url.searchParams.get('id');
  if (!pipelineId) return { error: 'pipelineId가 필요합니다.' };
  if (!env.PENDING_POSTS) return { error: 'KV 스토어 미설정' };
  const log = await env.PENDING_POSTS.get(`plog_${pipelineId}`, 'json').catch(() => null);
  return { pipelineId, log: log || [] };
}

async function handlePipelineStart(env, ctx, body) {
  const { bookInfo, affiliateLinks, commentKeyword, autoSelect } = body;
  // bookInfo가 없으면 autoSelect(카테고리)로 서버(크론)가 책을 자동 선정한다 —
  // 브라우저 쪽 Claude 호출이 지역 차단(403)될 때의 결정적 우회 경로.
  if (!bookInfo?.title && !autoSelect?.category && !autoSelect?.title) throw new Error('책 정보(bookInfo.title) 또는 자동 선정 정보(autoSelect.category/title)가 필요합니다.');
  if (!env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY가 설정되지 않았습니다.');
  if (!env.PENDING_POSTS) throw new Error('KV 스토어가 필요합니다.');

  const pipelineId = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const bookNumber = await reserveBookNumber(env);

  // 초기 상태: step 0 / done → 다음 전진 시 1단계 실행
  await savePipelineStatus(env, pipelineId, {
    status: 'running',
    step: 0,
    stepStatus: 'done',
    bookInfo: bookInfo?.title ? bookInfo : null,
    autoSelect: bookInfo?.title ? undefined : autoSelect,
    affiliateLinks: affiliateLinks || [],
    commentKeyword: commentKeyword || '',
    bookNumber,
    startedAt: Date.now(),
    label: bookInfo?.title
      ? `파이프라인 시작 — 도서 #${bookNumber} | 곧 자동 진행됩니다`
      : `파이프라인 시작 — 도서 #${bookNumber} | 책 자동 선정 대기 (${autoSelect.category})`,
  });
  await logStep(env, pipelineId, { step: 0, phase: 'start', note: bookInfo?.title ? `책: ${bookInfo.title}` : `autoSelect: ${autoSelect.category}` });

  // 즉시 1단계 킥 (self-fetch 없이 같은 인보케이션 waitUntil에서 직접 실행).
  // ⚠️ bookInfo가 있을 때(제작 단계=생성만, ~15초)만 킥한다. autoSelect(책 선정+생성,
  // ~40초 이상)를 킥하면 fetch waitUntil 예산(~30초)을 넘겨 도중에 죽는데, 그러면
  // ① 이미 호출한 suggest 크레딧이 낭비되고 ② 크론이 suggest를 재호출해 이중과금되며
  // ③ 죽은 'active' 상태가 STEP_STALE_MS만큼 방치된다. 그래서 autoSelect는 예산이 넉넉한
  // 크론이 한 번에 완주하게 맡긴다(크론은 첫 픽업까지 최대 ~1분).
  if (bookInfo?.title) ctx.waitUntil(advancePipeline(env, pipelineId).catch(() => {}));

  return { success: true, pipelineId, bookNumber };
}

// ===== 서버사이드 파이프라인 (구형 — 30초 한도로 대형 파이프라인 제한됨) =====
// 진행중 파이프라인 id 목록을 단일 키에 보관 → 크론이 KV list() 대신 get() 한 번으로 찾는다.
// (KV list 무료 한도 1000회/일 초과 방지: 매분 크론의 list 1440회/일이 원인이었음)
async function indexActivePipeline(env, id, active) {
  if (!env.PENDING_POSTS) return;
  let arr = [];
  try { arr = (await env.PENDING_POSTS.get('active_pipelines', 'json')) || []; } catch {}
  const has = arr.includes(id);
  if (active && !has) {
    arr.push(id);
    await env.PENDING_POSTS.put('active_pipelines', JSON.stringify(arr.slice(-100)));
  } else if (!active && has) {
    await env.PENDING_POSTS.put('active_pipelines', JSON.stringify(arr.filter(x => x !== id)));
  }
}

async function savePipelineStatus(env, pipelineId, patch) {
  if (!env.PENDING_POSTS || !pipelineId) return;
  const key = `pipeline_${pipelineId}`;
  let existing = {};
  try { existing = await env.PENDING_POSTS.get(key, 'json') || {}; } catch {}
  const updated = { ...existing, ...patch, updatedAt: Date.now() };
  // 완료된 파이프라인은 텔레그램 "확인하러 가기" 링크가 나중에 눌려도 결과를
  // 불러올 수 있도록 1일간 보관. 진행중은 1시간(자가복구·타임아웃 판정용).
  const ttl = (updated.status === 'complete') ? 24 * 3600 : 3600;
  await env.PENDING_POSTS.put(key, JSON.stringify(updated), { expirationTtl: ttl });
  // 진행중이면 인덱스에 등록, 완료/오류면 제거 (크론이 list 없이 찾도록)
  if (updated.status === 'running') await indexActivePipeline(env, pipelineId, true);
  else if (updated.status === 'complete' || updated.status === 'error') await indexActivePipeline(env, pipelineId, false);
}

async function executePipeline(env, pipelineId, bookInfo, affiliateLinks, commentKeyword) {
  try {
    // Step 1: 캐럿셀 생성
    await savePipelineStatus(env, pipelineId, { step: 1, stepStatus: 'active', label: 'Claude AI가 5페이지 카드뉴스를 작성 중...' });
    let pages;
    try {
      const genData = await handleGenerate(env, bookInfo);
      pages = genData.pages;
    } catch (e) {
      return await savePipelineStatus(env, pipelineId, { status: 'error', error: `캐럿셀 생성 실패: ${e.message}` });
    }
    await savePipelineStatus(env, pipelineId, { step: 1, stepStatus: 'done', label: '4페이지 카드뉴스 생성 완료', pages });

    // Step 2: 품질 검증 (최대 2회)
    await savePipelineStatus(env, pipelineId, { step: 2, stepStatus: 'active', label: 'AI 자동 품질 평가 중...' });
    let validation = null;
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        validation = await handleValidate(env, { pages, bookInfo });
        if (validation.approved) break;
        if (attempt < 2) {
          const rd = await handleRegenerate(env, { bookInfo, previousPages: pages, feedback: validation.feedback, improvements: validation.improvements || [] });
          pages = rd.pages;
        }
      } catch { break; }
    }
    await savePipelineStatus(env, pipelineId, { step: 2, stepStatus: 'done', label: `${validation?.totalScore || 0}/100점`, pages, validation });

    // Step 3: 이미지 생성
    await savePipelineStatus(env, pipelineId, { step: 3, stepStatus: 'active', label: 'Pollinations AI로 이미지 생성 중...' });
    let images = null;
    try {
      const imgData = await handleGenerateImages(env, { pages, bookInfo });
      images = imgData.images;
    } catch {}
    await savePipelineStatus(env, pipelineId, { step: 3, stepStatus: 'done', label: '이미지 URL 생성 완료', images });

    // Pollinations 사전 렌더링 대기
    await new Promise(r => setTimeout(r, 8000));

    // Step 4: 캡션 생성
    await savePipelineStatus(env, pipelineId, { step: 4, stepStatus: 'active', label: '인스타그램 캡션 작성 중...' });
    let caption = '', hashtags = [], dmKeyword = '';
    try {
      const capData = await handleGenerateCaption(env, { pages, bookInfo, dmKeyword: commentKeyword });
      caption = capData.caption || ''; hashtags = capData.hashtags || []; dmKeyword = capData.commentKeyword || capData.dmKeyword || '';
    } catch {}
    await savePipelineStatus(env, pipelineId, { step: 4, stepStatus: 'done', label: '캡션 + 해시태그 생성 완료', caption, hashtags, dmKeyword });

    // Step 5: DM 미사용(저장·공유 전략) — 아무 생성도 하지 않고 통과(Claude 호출 0)
    await savePipelineStatus(env, pipelineId, { step: 5, stepStatus: 'done', label: 'DM 단계 생략(미사용)' });

    // Step 6: 텔레그램 발송 (완료 알림 + 확인 링크만)
    await savePipelineStatus(env, pipelineId, { step: 6, stepStatus: 'active', label: '텔레그램으로 제작 완료 알림 발송 중...' });
    let telegramError = null;
    try {
      await handleSendTelegram(env, { bookInfo, pipelineId });
    } catch (e) { telegramError = e.message; }
    await savePipelineStatus(env, pipelineId, {
      step: 6, stepStatus: telegramError ? 'error' : 'done',
      label: telegramError ? `텔레그램 발송 실패: ${telegramError}` : '텔레그램으로 완료 알림 + 확인 링크 발송 완료',
    });

    // 완료
    await savePipelineStatus(env, pipelineId, {
      step: 7, stepStatus: 'done', status: 'complete',
      label: telegramError ? '완료 (텔레그램 알림 실패 — 이 페이지에서 바로 게시 가능)' : '완료! 텔레그램 알림을 보냈습니다. 이 페이지에서 게시 여부를 결정하세요.',
      completedAt: Date.now(),
    });
  } catch (err) {
    await savePipelineStatus(env, pipelineId, { status: 'error', error: err.message });
  }
}

async function handleRunPipeline(env, body, ctx) {
  const { bookInfo, affiliateLinks, commentKeyword } = body;
  if (!bookInfo?.title) throw new Error('책 정보(bookInfo.title)가 필요합니다.');
  if (!env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY가 설정되지 않았습니다.');

  // KV 없으면 폴백 모드: 서버 백그라운드 실행하되 폴링 없이 진행
  if (!env.PENDING_POSTS) {
    const pipelinePromise = executePipeline(env, null, bookInfo, affiliateLinks || [], commentKeyword || '');
    if (ctx?.waitUntil) ctx.waitUntil(pipelinePromise);
    else pipelinePromise.catch(() => {});
    return { success: true, pipelineId: null, mode: 'direct' };
  }

  const pipelineId = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  await savePipelineStatus(env, pipelineId, { step: 0, stepStatus: 'active', status: 'started', bookInfo, startedAt: Date.now(), label: '파이프라인 시작 중...' });
  const pipelinePromise = executePipeline(env, pipelineId, bookInfo, affiliateLinks || [], commentKeyword || '');
  if (ctx?.waitUntil) ctx.waitUntil(pipelinePromise);
  else pipelinePromise.catch(() => {});
  return { success: true, pipelineId, mode: 'kv' };
}

async function handlePipelineStatus(env, url) {
  const pipelineId = url.searchParams.get('id');
  if (!pipelineId) return { status: 'error', error: 'pipelineId가 필요합니다.' };
  if (!env.PENDING_POSTS) return { status: 'error', error: 'KV 스토어 미설정' };
  const data = await env.PENDING_POSTS.get(`pipeline_${pipelineId}`, 'json').catch(() => null);
  if (!data) return { status: 'not_found' };
  return { ...data, pipelineId };
}

// ===== Phase 4: 인스타그램 캐럿셀 게시 =====
async function handlePostInstagram(env, body) {
  if (!env.INSTAGRAM_ACCESS_TOKEN || !env.INSTAGRAM_USER_ID) {
    throw new Error('INSTAGRAM_ACCESS_TOKEN 또는 INSTAGRAM_USER_ID 시크릿을 Cloudflare Workers에 설정해주세요.');
  }

  const { images, caption, hashtags } = body;
  if (!images || !caption) throw new Error('이미지(images)와 캡션(caption)이 필요합니다.');

  const TOKEN = env.INSTAGRAM_ACCESS_TOKEN;
  const IG_ID = env.INSTAGRAM_USER_ID;
  const BASE = `https://graph.instagram.com/v21.0/${IG_ID}`;
  const captionFull = caption + (hashtags?.length ? '\n\n' + hashtags.join(' ') : '');

  // Step 1: 페이지별 미디어 컨테이너 생성 (is_carousel_item=true)
  const containerIds = [];
  for (const page of ['page1', 'page2', 'page3', 'page4']) {
    const imgUrl = images[page];
    if (!imgUrl) continue;
    const res = await fetch(`${BASE}/media`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_url: imgUrl, is_carousel_item: true, access_token: TOKEN }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(`이미지 컨테이너 생성 실패 (${page}): ${err.error?.message || res.status}`);
    }
    containerIds.push((await res.json()).id);
    await new Promise(r => setTimeout(r, 500));
  }

  if (containerIds.length < 2) throw new Error('캐럿셀은 최소 2장의 이미지가 필요합니다.');

  // Step 2: 캐럿셀 컨테이너 생성
  const carRes = await fetch(`${BASE}/media`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ media_type: 'CAROUSEL', children: containerIds.join(','), caption: captionFull, access_token: TOKEN }),
  });
  if (!carRes.ok) {
    const err = await carRes.json().catch(() => ({}));
    throw new Error(`캐럿셀 컨테이너 생성 실패: ${err.error?.message || carRes.status}`);
  }
  const carouselId = (await carRes.json()).id;

  // Step 3: 게시 (생성 후 잠시 대기)
  await new Promise(r => setTimeout(r, 2000));
  const pubRes = await fetch(`${BASE}/media_publish`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ creation_id: carouselId, access_token: TOKEN }),
  });
  if (!pubRes.ok) {
    const err = await pubRes.json().catch(() => ({}));
    throw new Error(`인스타그램 게시 실패: ${err.error?.message || pubRes.status}`);
  }
  const pubData = await pubRes.json();
  return { success: true, mediaId: pubData.id, message: '인스타그램에 캐럿셀이 게시됐습니다!' };
}

// ===== Phase 4: 텔레그램 Webhook (인라인 버튼 콜백 처리) =====
async function handleTelegramWebhook(env, body) {
  const { callback_query } = body;
  if (!callback_query) return { ok: true };

  const callbackId = callback_query.id;
  const cbData = callback_query.data;
  // chat id: 콜백 메시지에서 먼저, 없으면 env 폴백
  const chatId = callback_query.message?.chat?.id || env.TELEGRAM_CHAT_ID;

  const answerCallback = (text, showAlert = false) =>
    fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ callback_query_id: callbackId, text, show_alert: showAlert }),
    }).catch(() => {});

  if (cbData === 'approve') {
    await answerCallback('처리 중...');
    if (!env.PENDING_POSTS) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, 'KV 스토어가 설정되지 않았습니다.').catch(() => {});
      return { ok: true };
    }
    const stateJson = await env.PENDING_POSTS.get('latest').catch(() => null);
    if (!stateJson) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, '게시할 콘텐츠가 없습니다 (만료됐거나 취소됨). 웹에서 다시 생성해주세요.').catch(() => {});
      return { ok: true };
    }
    const ps = JSON.parse(stateJson);
    try {
      const result = await handlePostInstagram(env, { images: ps.images, caption: ps.caption, hashtags: ps.hashtags });
      await env.PENDING_POSTS.delete('latest').catch(() => {});
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
        `인스타그램 게시 완료!\n미디어 ID: ${result.mediaId}\n\n책: ${ps.bookInfo?.title || ''}`).catch(() => {});
    } catch (err) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
        `인스타그램 게시 실패: ${err.message}\n\n웹에서 직접 게시해주세요: https://book-carousel.jtaechul.workers.dev/`).catch(() => {});
    }
  } else if (cbData === 'cancel') {
    await answerCallback('취소됐습니다.');
    if (env.PENDING_POSTS) await env.PENDING_POSTS.delete('latest').catch(() => {});
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, '게시가 취소됐습니다.').catch(() => {});
  } else if (cbData === 'modify') {
    await answerCallback('웹에서 수정해주세요', true);
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
      '웹에서 수정 후 다시 발송해주세요:\nhttps://book-carousel.jtaechul.workers.dev/').catch(() => {});
  } else {
    await answerCallback('');
  }

  return { ok: true };
}

// ===== 텔레그램 Webhook URL 등록 (최초 1회 실행) =====
async function handleSetupWebhook(env) {
  if (!env.TELEGRAM_BOT_TOKEN) throw new Error('TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.');
  const webhookUrl = 'https://book-carousel.jtaechul.workers.dev/api/telegram-webhook';
  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: webhookUrl }),
  });
  const data = await res.json();
  return { success: true, webhookUrl, ...data };
}

// ===== Phase 5: 인스타그램 댓글 DM 자동 회신 Webhook =====
async function handleInstagramWebhook(env, request) {
  const url = new URL(request.url);

  // GET: Meta webhook 도메인 검증
  if (request.method === 'GET') {
    const mode = url.searchParams.get('hub.mode');
    const token = url.searchParams.get('hub.verify_token');
    const challenge = url.searchParams.get('hub.challenge');
    const VERIFY = env.INSTAGRAM_VERIFY_TOKEN || 'book_carousel_verify';
    if (mode === 'subscribe' && token === VERIFY) return new Response(challenge, { status: 200 });
    return new Response('Forbidden', { status: 403 });
  }

  // POST: 댓글 이벤트 → 키워드 감지 → DM 자동 회신
  const body = await request.json().catch(() => ({}));
  for (const entry of body.entry || []) {
    for (const change of entry.changes || []) {
      if (change.field === 'comments') {
        const text = (change.value?.text || '').trim();
        const senderId = change.value?.from?.id;
        if (!senderId || !env.PENDING_POSTS || !env.INSTAGRAM_ACCESS_TOKEN) continue;

        const { keys } = await env.PENDING_POSTS.list({ prefix: 'dm_reply_' });
        for (const { name } of keys) {
          const kw = name.replace('dm_reply_', '');
          if (text.includes(kw)) {
            const dmText = await env.PENDING_POSTS.get(name);
            if (dmText) {
              await fetch('https://graph.instagram.com/v21.0/me/messages', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  recipient: { id: senderId },
                  message: { text: dmText },
                  access_token: env.INSTAGRAM_ACCESS_TOKEN,
                }),
              }).catch(() => {});
            }
            break;
          }
        }
      }
    }
  }
  return new Response('EVENT_RECEIVED', { status: 200 });
}

// KV에 저장된 이미지 바이너리를 반환 (step 3에서 저장, 24h 유효)
async function handleImageServe(env, url) {
  const id = url.searchParams.get('id');
  const page = url.searchParams.get('page');
  if (!id || !page) return new Response('Bad Request', { status: 400, headers: CORS });
  const buf = await env.PENDING_POSTS.get(`img_${id}_${page}`, 'arrayBuffer').catch(() => null);
  if (!buf) return new Response('Image not found', { status: 404, headers: CORS });
  // 포맷 자동 감지: Gemini 표지는 PNG, Pollinations 본문은 JPEG일 수 있음(매직바이트로 판별)
  const b = new Uint8Array(buf.slice(0, 4));
  const isPng = b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47;
  const mime = isPng ? 'image/png' : 'image/jpeg';
  return new Response(buf, {
    headers: { 'Content-Type': mime, 'Cache-Control': 'public, max-age=86400', ...CORS },
  });
}

// ===== 도서 카탈로그 =====

async function reserveBookNumber(env) {
  if (!env.PENDING_POSTS) return '001';
  const current = parseInt((await env.PENDING_POSTS.get('book_counter').catch(() => '0')) || '0', 10);
  const next = current + 1;
  await env.PENDING_POSTS.put('book_counter', String(next));
  return String(next).padStart(3, '0');
}

async function addBookToCatalog(env, { bookInfo, bookNumber, pipelineId, coupangLink = null, cover = '' }) {
  if (!env.PENDING_POSTS || !bookNumber) return;
  const catalog = (await env.PENDING_POSTS.get('book_catalog', 'json').catch(() => null)) || [];
  const coverUrl = cover || bookInfo?.cover || '';
  const entry = {
    number: bookNumber,
    title: bookInfo?.title || '',
    author: bookInfo?.author || '',
    category: bookInfo?.category || '기타',
    coreMessage: bookInfo?.coreMessage || '',
    cover: coverUrl,             // ← 책 표지(네이버) — 도서관에서 표지로 노출
    date: new Date().toISOString().slice(0, 10),
    pipelineId,
    coupangLink,
  };
  // 같은 번호가 이미 있으면 내용·링크를 갱신(업서트), 없으면 새로 추가.
  // → "도서관 등록" 메뉴에서 소개·링크를 고쳐 다시 등록하면 덮어쓰기 된다.
  const idx = catalog.findIndex(b => b.number === bookNumber);
  if (idx >= 0) {
    // 새 표지가 없으면 기존 표지 보존(소개·링크만 수정하는 경우 표지 유지)
    const merged = { ...catalog[idx], ...entry, date: catalog[idx].date };
    if (!coverUrl && catalog[idx].cover) merged.cover = catalog[idx].cover;
    catalog[idx] = merged;
  } else {
    catalog.unshift(entry);
  }
  await env.PENDING_POSTS.put('book_catalog', JSON.stringify(catalog));
}

async function handleAddBookToCatalog(env, body) {
  const { bookInfo, coupangLink, affiliateLinks, affiliateLink } = body;
  if (!bookInfo?.title) throw new Error('bookInfo.title이 필요합니다.');

  const link = coupangLink
    || (Array.isArray(affiliateLinks) && affiliateLinks.find(l => l && l.trim()))
    || affiliateLink
    || null;

  // 이미 예약된 번호(body.bookNumber)가 있으면 그대로 사용 → 캡션·도서관 번호 일치.
  // 없을 때만 새 번호를 매긴다.
  const bookNumber = body.bookNumber || await reserveBookNumber(env);
  await addBookToCatalog(env, { bookInfo, bookNumber, pipelineId: null, coupangLink: link, cover: body.cover || bookInfo?.cover || '' });
  return { success: true, bookNumber };
}

// 번호를 3자리(001)로 정규화 ("1", "001", "No.1" 모두 인식)
function normNum(v) {
  return String(parseInt(String(v || '').replace(/[^0-9]/g, ''), 10) || 0).padStart(3, '0');
}

// 한 게시물의 모든 내용을 번호로 묶어 저장 — 관리자 보관함의 원본.
// 텍스트(캡션·5장·DM·링크·소개)는 영구, 이미지는 며칠 뒤 자동 삭제(게시물엔 이미 올라가 있으므로).
async function handleSavePost(env, body) {
  const { bookInfo, pages, caption, hashtags, dmText, coupangLink, affiliateLinks, images, cover } = body;
  if (!bookInfo?.title) throw new Error('bookInfo.title이 필요합니다.');
  if (!env.PENDING_POSTS) throw new Error('저장소가 없습니다.');

  const link = coupangLink
    || (Array.isArray(affiliateLinks) && affiliateLinks.find(l => l && l.trim()))
    || null;
  const bookNumber = body.bookNumber || await reserveBookNumber(env);
  const num = normNum(bookNumber);
  if (num === '000') throw new Error('번호가 올바르지 않습니다.');

  const existing = await env.PENDING_POSTS.get(`post_${num}`, 'json').catch(() => null);
  const pipelineId = body.pipelineId || existing?.pipelineId || null;
  const record = {
    number: num,
    bookInfo,
    pages: pages || existing?.pages || null,
    caption: caption != null ? caption : (existing?.caption || ''),
    hashtags: hashtags || existing?.hashtags || [],
    dmText: dmText != null ? dmText : (existing?.dmText || ''),
    coupangLink: link != null ? link : (existing?.coupangLink || null),
    pipelineId,
    date: existing?.date || new Date().toISOString().slice(0, 10),
    updatedAt: new Date().toISOString().slice(0, 10),
  };
  await env.PENDING_POSTS.put(`post_${num}`, JSON.stringify(record));

  // 이미지: 3일 TTL (임시 보관)
  if (images && typeof images === 'object' && Object.keys(images).length) {
    await env.PENDING_POSTS.put(`post_img_${num}`, JSON.stringify(images), { expirationTtl: 259200 });
  }

  // 도서관 카드 + DM 영구본 동기화
  await addBookToCatalog(env, { bookInfo, bookNumber: num, pipelineId, coupangLink: record.coupangLink, cover: cover || bookInfo?.cover || '' });
  if (record.dmText) {
    await env.PENDING_POSTS.put(`dm_book_${num}`, JSON.stringify({
      number: num, title: bookInfo.title || '', dmText: record.dmText, date: record.date,
    }));
  }
  return { success: true, bookNumber: num };
}

// 도서관에서 책 삭제 + 번호 취소. 카탈로그·게시물·이미지·DM·중복이력에서 모두 제거하고,
// 삭제한 게 "가장 큰 번호"면 book_counter를 회수해 다음 책이 그 번호를 재사용하게 한다.
async function handleDeleteBook(env, body) {
  if (!env.PENDING_POSTS) throw new Error('저장소가 없습니다.');
  const num = normNum(body.number);
  if (num === '000') throw new Error('번호가 올바르지 않습니다.');

  // 삭제 대상 제목 확보(중복이력에서 빼기 위해)
  const catalog = (await env.PENDING_POSTS.get('book_catalog', 'json').catch(() => null)) || [];
  const target = catalog.find(b => b.number === num);
  const title = target?.title || '';

  // 1) 카탈로그에서 제거
  const nextCatalog = catalog.filter(b => b.number !== num);
  await env.PENDING_POSTS.put('book_catalog', JSON.stringify(nextCatalog));

  // 2) 게시물·이미지·DM 기록 삭제
  await env.PENDING_POSTS.delete(`post_${num}`).catch(() => {});
  await env.PENDING_POSTS.delete(`post_img_${num}`).catch(() => {});
  await env.PENDING_POSTS.delete(`dm_book_${num}`).catch(() => {});

  // 3) 중복 제작 이력(used_books)에서 제목 제거 → 다시 추천 가능
  if (title) {
    try {
      const used = (await env.PENDING_POSTS.get('used_books', 'json')) || [];
      const nt = _normTitle(title);
      const nextUsed = used.filter(t => _normTitle(t) !== nt);
      if (nextUsed.length !== used.length) await env.PENDING_POSTS.put('used_books', JSON.stringify(nextUsed));
    } catch {}
  }

  // 4) 번호 회수: 남은 책들의 최대 번호로 counter 재설정(빈 카탈로그면 0).
  //    → 마지막 번호를 지우면 그 번호가 다음 책에 재사용됨. 중간 번호 삭제는 빈칸만 남김(딥링크 보호).
  let counterReclaimed = false;
  try {
    const maxRemain = nextCatalog.reduce((m, b) => Math.max(m, parseInt(b.number, 10) || 0), 0);
    const curCounter = parseInt((await env.PENDING_POSTS.get('book_counter').catch(() => '0')) || '0', 10);
    if (maxRemain < curCounter) {
      await env.PENDING_POSTS.put('book_counter', String(maxRemain));
      counterReclaimed = true;
    }
  } catch {}

  return { success: true, deleted: num, counterReclaimed };
}

// 번호로 한 게시물의 모든 내용을 불러온다 (보관함 상세).
async function handleGetPost(env, body) {
  const num = normNum(body.number);
  if (num === '000') return { success: false, error: '번호가 올바르지 않습니다.' };

  const post = await env.PENDING_POSTS.get(`post_${num}`, 'json').catch(() => null);
  const dmRec = await env.PENDING_POSTS.get(`dm_book_${num}`, 'json').catch(() => null);
  const images = await env.PENDING_POSTS.get(`post_img_${num}`, 'json').catch(() => null);
  const catalog = (await env.PENDING_POSTS.get('book_catalog', 'json').catch(() => null)) || [];
  const cat = catalog.find(b => b.number === num);

  if (!post && !cat && !dmRec) return { success: false, error: `No.${num} 기록을 찾을 수 없습니다.` };

  const bi = post?.bookInfo || (cat ? { title: cat.title, author: cat.author, category: cat.category, coreMessage: cat.coreMessage } : {});

  // 번들에 빠진 부분(캡션·5장·이미지·DM)은 파이프라인 기록에서 보완 → 도서관에 있는 책은
  // 가능한 모든 내용이 관리자 페이지에 보이게 한다.
  let pages = post?.pages || null;
  let caption = post?.caption || '';
  let hashtags = post?.hashtags || [];
  let dmText = post?.dmText || dmRec?.dmText || '';
  let imgs = images || null;
  const pid = post?.pipelineId || cat?.pipelineId;
  if (pid && (!pages || !caption || !imgs)) {
    const ps = await env.PENDING_POSTS.get(`pipeline_${pid}`, 'json').catch(() => null);
    if (ps) {
      if (!pages) pages = ps.pages || null;
      if (!caption) caption = ps.caption || '';
      if (!hashtags.length) hashtags = ps.hashtags || [];
      if (!imgs) imgs = ps.images || null;
      if (!dmText) dmText = ps.dmText || '';
    }
  }

  return {
    success: true,
    number: num,
    title: bi.title || cat?.title || dmRec?.title || '',
    bookInfo: bi,
    pages,
    caption,
    hashtags,
    dmText,
    coupangLink: post?.coupangLink || cat?.coupangLink || null,
    coreMessage: bi.coreMessage || cat?.coreMessage || '',
    images: imgs || null,
    date: post?.date || cat?.date || '',
  };
}

// ── 초안(draft) 저장/조회/삭제 ──
// 만들었지만 아직 등록/게시 안 한 캐럿셀을 번호 없이 임시 보관(7일). 이미지가 사라지지 않게,
// 그리고 마음에 드는 것만 골라 도서관에 정식 등록(번호 부여)하도록.
const DRAFT_TTL = 604800; // 7일
function pruneDraftIndex(index) {
  const cutoff = Date.now() - DRAFT_TTL * 1000;
  return (index || []).filter(d => d && d.createdAt && d.createdAt > cutoff);
}
async function handleSaveDraft(env, body) {
  if (!env.PENDING_POSTS) throw new Error('저장소가 없습니다.');
  const { bookInfo, pages, caption, hashtags, images, cover } = body;
  if (!bookInfo?.title && !pages) throw new Error('저장할 초안 내용이 없습니다.');
  const id = body.draftId || ('d' + Date.now() + Math.random().toString(36).slice(2, 6));
  const createdAt = Date.now();
  const draft = {
    id, bookInfo: bookInfo || {}, pages: pages || null,
    caption: caption || '', hashtags: hashtags || [],
    images: images || null, cover: cover || bookInfo?.cover || '',
    createdAt, date: new Date().toISOString().slice(0, 10),
  };
  await env.PENDING_POSTS.put(`draft_${id}`, JSON.stringify(draft), { expirationTtl: DRAFT_TTL });
  // 인덱스 갱신(요약만)
  let index = (await env.PENDING_POSTS.get('draft_index', 'json').catch(() => null)) || [];
  index = pruneDraftIndex(index).filter(d => d.id !== id);
  index.unshift({
    id, title: bookInfo?.title || '(제목 미정)', author: bookInfo?.author || '',
    category: bookInfo?.category || '', cover: draft.cover,
    hasImages: !!(images && Object.keys(images).length), createdAt, date: draft.date,
  });
  await env.PENDING_POSTS.put('draft_index', JSON.stringify(index));
  return { success: true, draftId: id };
}
async function handleListDrafts(env) {
  if (!env.PENDING_POSTS) return { success: true, drafts: [] };
  let index = (await env.PENDING_POSTS.get('draft_index', 'json').catch(() => null)) || [];
  const pruned = pruneDraftIndex(index);
  if (pruned.length !== index.length) await env.PENDING_POSTS.put('draft_index', JSON.stringify(pruned));
  return { success: true, drafts: pruned };
}
async function handleGetDraft(env, body) {
  const id = body.draftId;
  if (!id) return { success: false, error: '초안 id가 필요합니다.' };
  const draft = await env.PENDING_POSTS.get(`draft_${id}`, 'json').catch(() => null);
  if (!draft) return { success: false, error: '초안을 찾을 수 없습니다(보관 기간 만료일 수 있음).' };
  return { success: true, draft };
}
async function handleDeleteDraft(env, body) {
  const id = body.draftId;
  if (!id) return { success: false, error: '초안 id가 필요합니다.' };
  await env.PENDING_POSTS.delete(`draft_${id}`);
  let index = (await env.PENDING_POSTS.get('draft_index', 'json').catch(() => null)) || [];
  index = pruneDraftIndex(index).filter(d => d.id !== id);
  await env.PENDING_POSTS.put('draft_index', JSON.stringify(index));
  return { success: true };
}

function generateBooksHTML(catalog) {
  const CAT_COLORS = {
    '애착': '#C2708F', '연애': '#D08A6E', '에세이': '#D08A6E',
    '이별': '#9B6A8F', '회복': '#9B6A8F',
    '자존감': '#C18A4B', '사랑': '#C2708F',
    '관계': '#A2708F', '심리': '#8E6AA8',
    '짝사랑': '#D98AA0', '설렘': '#D98AA0',
  };
  const catColor = c => { for (const [k, v] of Object.entries(CAT_COLORS)) if (c?.includes(k)) return v; return '#A98C7A'; };

  const allCats = ['전체', ...new Set(catalog.map(b => b.category).filter(Boolean))];
  const tabsHTML = allCats.map((c, i) =>
    `<button class="tab${i === 0 ? ' active' : ''}" data-filter="${c}">${c}</button>`
  ).join('');

  const cardsHTML = catalog.length === 0
    ? `<div class="empty"><p>곧 첫 번째 책이 등록됩니다.</p></div>`
    : catalog.map((b, i) => {
        const color = catColor(b.category);
        const btn = b.coupangLink
          ? `<a href="${b.coupangLink}" target="_blank" rel="noopener" class="cta">책 만나보기 →</a>`
          : `<span class="cta-soon">링크 준비 중</span>`;
        return `
  <article class="card" data-category="${b.category || '기타'}">
    <div class="card-top">
      ${i === 0 ? '<span class="badge-new">NEW</span>' : '<span></span>'}
      <span class="book-num">No.${b.number}</span>
    </div>
    <div style="display:flex;gap:16px;align-items:flex-start;margin-bottom:14px;">
      ${b.cover ? `<img src="/api/cover?url=${encodeURIComponent(b.cover)}" alt="표지" loading="lazy" onerror="this.style.display='none'" style="width:88px;height:126px;flex-shrink:0;border-radius:8px;object-fit:cover;box-shadow:0 3px 12px rgba(0,0,0,.2);background:#EDE6DD;">` : ''}
      <div style="min-width:0;flex:1;">
        <span class="cat-pill" style="background:${color}18;color:${color}">${b.category || '기타'}</span>
        <h2 class="book-title">${b.title}</h2>
        <p class="book-author" style="margin-bottom:0;">${b.author}</p>
      </div>
    </div>
    ${b.coreMessage ? `<blockquote class="book-msg">${b.coreMessage}</blockquote>` : ''}
    <div class="card-foot">
      <span class="book-date">${b.date}</span>
      ${btn}
    </div>
  </article>`;
      }).join('');

  return `<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>오늘의 연애 책방 | 행간</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@600;700&family=Noto+Sans+KR:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#FBF5F0;--card:#fff;--dark:#4A2F38;
  --gold:#C2708F;--text:#3A2A2E;--sub:#8A7479;
  --border:#EFE3DC;--radius:16px;
}
body{background:var(--bg);color:var(--text);font-family:'Noto Sans KR',sans-serif;min-height:100vh;padding-bottom:80px}

/* header */
.hd{background:var(--dark);color:#fff;padding:44px 20px 0;text-align:center}
.hd-eyebrow{font-size:10px;letter-spacing:4px;color:var(--gold);font-weight:600;text-transform:uppercase;margin-bottom:12px}
.hd-title{font-family:'Noto Serif KR',serif;font-size:28px;font-weight:700;line-height:1.25;margin-bottom:10px}
.hd-sub{font-size:12.5px;color:#9CA3AF;line-height:1.7;margin-bottom:28px}

/* tabs */
.tabs-wrap{background:var(--dark);padding:0 16px 18px;position:sticky;top:0;z-index:20}
.tabs{display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;-ms-overflow-style:none}
.tabs::-webkit-scrollbar{display:none}
.tab{background:#2A2A2A;color:#9CA3AF;border:none;padding:8px 18px;border-radius:20px;font-size:13px;font-family:'Noto Sans KR',sans-serif;cursor:pointer;white-space:nowrap;transition:all .2s;font-weight:500}
.tab.active,.tab:hover{background:var(--gold);color:var(--dark);font-weight:600}

/* catalog */
.catalog{max-width:520px;margin:0 auto;padding:24px 16px 0;display:flex;flex-direction:column;gap:16px}

/* card */
.card{background:var(--card);border-radius:var(--radius);padding:24px;box-shadow:0 2px 16px rgba(0,0,0,.06);position:relative;overflow:hidden;transition:box-shadow .25s,transform .25s}
.card:hover{box-shadow:0 8px 32px rgba(0,0,0,.11);transform:translateY(-2px)}
.card::after{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:linear-gradient(90deg,var(--gold),transparent)}
.card.hidden{display:none}

.card-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.badge-new{background:#EF4444;color:#fff;font-size:9px;font-weight:700;padding:3px 9px;border-radius:4px;letter-spacing:1.5px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}
.book-num{font-family:'Noto Serif KR',serif;font-size:32px;font-weight:700;color:#F0EBE2;line-height:1;user-select:none}

.cat-pill{display:inline-block;font-size:11px;font-weight:600;padding:4px 12px;border-radius:20px;margin-bottom:14px}
.book-title{font-family:'Noto Serif KR',serif;font-size:20px;font-weight:700;line-height:1.4;margin-bottom:6px}
.book-author{font-size:13px;color:var(--sub);margin-bottom:14px}
.book-msg{font-size:13.5px;line-height:1.75;color:#374151;background:#F9F5EF;border-left:3px solid var(--gold);border-radius:0 8px 8px 0;padding:12px 14px;margin-bottom:18px}
.card-foot{display:flex;justify-content:space-between;align-items:center;gap:12px}
.book-date{font-size:11.5px;color:#9CA3AF}
.cta{background:var(--dark);color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:600;transition:all .2s;white-space:nowrap}
.cta:hover{background:var(--gold);color:var(--dark)}
.cta-soon{font-size:12px;color:#9CA3AF;font-style:italic}

/* empty */
.empty{text-align:center;padding:60px 20px;color:var(--sub);font-size:15px}

/* footer */
.foot{max-width:520px;margin:40px auto 0;padding:0 16px;text-align:center;border-top:1px solid var(--border);padding-top:24px}
.foot p{font-size:11px;color:#9CA3AF;line-height:1.8}
.foot a{color:var(--gold);text-decoration:none}
.foot .insta{font-size:13px;font-weight:600;color:var(--dark);margin-bottom:8px}
</style>
</head>
<body>
<header class="hd">
  <p class="hd-eyebrow">Love Between the Lines</p>
  <h1 class="hd-title">행간<br>연애 책방</h1>
  <p class="hd-sub">오늘 마음에 닿은 그 책을 여기서 만나요.<br>게시물의 도서 번호(No.000)로 바로 찾을 수 있습니다.</p>
</header>
<div class="tabs-wrap"><div class="tabs" role="tablist">${tabsHTML}</div></div>
<main class="catalog" id="catalog">${cardsHTML}</main>
<footer class="foot">
  <p class="insta"><a href="https://www.instagram.com/love.between.lines" target="_blank">@love.between.lines</a></p>
  <p>이 페이지의 도서 구매 링크는 쿠팡 파트너스 활동의 일환으로,<br>이에 따른 일정액의 수수료를 제공받습니다.</p>
</footer>
<script>
const tabs=document.querySelectorAll('.tab');
const cards=document.querySelectorAll('.card');
tabs.forEach(t=>t.addEventListener('click',()=>{
  tabs.forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  const f=t.dataset.filter;
  cards.forEach(c=>c.classList.toggle('hidden',f!=='전체'&&c.dataset.category!==f));
}));
// URL #번호로 해당 책 카드 자동 스크롤 (숫자만 비교)
(function(){
  var t=(location.hash.replace('#','')||'').replace(/\\D/g,'');
  if(!t)return;
  cards.forEach(function(c){
    var n=(c.querySelector('.book-num')?.textContent||'').replace(/\\D/g,'');
    if(n===t){setTimeout(function(){c.scrollIntoView({behavior:'smooth',block:'center'});},300);c.style.outline='2px solid var(--gold)';c.style.outlineOffset='3px';}
  });
})();
</script>
</body>
</html>`;
}

async function handleBooksPage(env) {
  const catalog = (await env.PENDING_POSTS?.get('book_catalog', 'json').catch(() => null)) || [];
  return new Response(generateBooksHTML(catalog), {
    headers: { 'Content-Type': 'text/html;charset=UTF-8' },
  });
}

// ===== 메인 라우터 =====
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    if (url.pathname.startsWith('/api/')) {
      // GET 전용 바이너리 응답 경로 — body 파싱 전에 먼저 처리
      if (url.pathname === '/api/image') {
        return await handleImageServe(env, url);
      }

      // 책 표지 프록시 — 네이버 이미지를 우리 도메인으로 받아 캔버스 CORS 오염 없이 그릴 수 있게
      if (url.pathname === '/api/cover') {
        const src = url.searchParams.get('url') || '';
        if (!/^https:\/\/[\w.-]*pstatic\.net\//.test(src) && !/^https:\/\/[\w.-]*(naver|nstatic)\.[\w.]+\//.test(src)) {
          return new Response('bad url', { status: 400, headers: CORS });
        }
        try {
          const r = await fetch(src);
          if (!r.ok) return new Response('not found', { status: 404, headers: CORS });
          const buf = await r.arrayBuffer();
          return new Response(buf, {
            headers: {
              'Content-Type': r.headers.get('content-type') || 'image/jpeg',
              'Access-Control-Allow-Origin': '*',
              'Cache-Control': 'public, max-age=604800',
            },
          });
        } catch {
          return new Response('error', { status: 502, headers: CORS });
        }
      }

      // instagram-webhook은 GET/POST 모두 처리 + raw request 필요 → body 파싱 전에 분기
      if (url.pathname === '/api/instagram-webhook') {
        return await handleInstagramWebhook(env, request);
      }

      try {
        const body = request.method === 'POST' ? await request.json() : {};
        let result;

        // 진단용: 키 상태 + /v1/models 원시 응답 + 모델 선택 결과 확인
        if (url.pathname === '/api/models') {
          _modelCache = null; // 진단 시 캐시 무시하고 새로 조회
          const key = env.ANTHROPIC_API_KEY;

          // 1) 키 존재 여부 (값은 노출하지 않고 앞 6자만 마스킹)
          const keyInfo = {
            present: !!key,
            length: key ? key.length : 0,
            prefix: key ? key.slice(0, 6) + '...' : null,
          };

          // 2) /v1/models 원시 응답 그대로 확인
          let rawStatus = null, rawBody = null;
          try {
            const r = await fetch('https://api.anthropic.com/v1/models?limit=100', {
              headers: { 'x-api-key': key || '', 'anthropic-version': '2023-06-01' },
            });
            rawStatus = r.status;
            rawBody = await r.text();
            if (rawBody && rawBody.length > 800) rawBody = rawBody.slice(0, 800) + '…';
          } catch (e) {
            rawBody = 'fetch 실패: ' + e.message;
          }

          // 3) 모델 자동 선택 시도
          const resolved = await resolveModels(key, env);

          result = { keyInfo, modelsEndpoint: { status: rawStatus, body: rawBody }, resolved };
        }
        else if (url.pathname === '/api/debug-env') result = {
          hasApiKey: !!env.ANTHROPIC_API_KEY,
          hasTelegramToken: !!env.TELEGRAM_BOT_TOKEN,
          hasTelegramChatId: !!env.TELEGRAM_CHAT_ID,
          hasPendingPosts: !!env.PENDING_POSTS,
          pendingPostsType: env.PENDING_POSTS ? typeof env.PENDING_POSTS : 'undefined',
          hasInstagramToken: !!env.INSTAGRAM_ACCESS_TOKEN,
        }
        else if (url.pathname === '/api/suggest') result = await handleSuggest(env, body);
        else if (url.pathname === '/api/analyze') result = await handleAnalyze(env, body);
        else if (url.pathname === '/api/generate') result = await handleGenerate(env, body);
        else if (url.pathname === '/api/generate-images') result = await handleGenerateImages(env, body);
        else if (url.pathname === '/api/generate-caption') result = await handleGenerateCaption(env, body);
        else if (url.pathname === '/api/validate') result = await handleValidate(env, body);
        else if (url.pathname === '/api/regenerate') result = await handleRegenerate(env, body);
        else if (url.pathname === '/api/telegram-bot-info') {
          // 봇 사용자명 확인용(사용자에게 "이 봇에게 먼저 메시지 보내세요" 링크를 안내하기 위함). 토큰 자체는 노출 안 함.
          if (!env.TELEGRAM_BOT_TOKEN) { result = { success: false, error: '봇 토큰이 설정되지 않았습니다.' }; }
          else {
            const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getMe`);
            const d = await r.json().catch(() => ({}));
            result = d.ok ? { success: true, username: d.result.username } : { success: false, error: d.description || '조회 실패' };
          }
        }
        else if (url.pathname === '/api/telegram-chat-info') {
          // 진단용: 등록하려는 채팅 ID가 실제로 어떤 대상(개인/봇/그룹)인지 확인 (토큰 노출 안 함).
          const chatId = url.searchParams.get('chatId') || body.chatId;
          if (!env.TELEGRAM_BOT_TOKEN) { result = { success: false, error: '봇 토큰이 설정되지 않았습니다.' }; }
          else if (!chatId) { result = { success: false, error: 'chatId가 필요합니다.' }; }
          else {
            const r = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getChat?chat_id=${encodeURIComponent(chatId)}`);
            const d = await r.json().catch(() => ({}));
            result = d.ok
              ? { success: true, type: d.result.type, isBot: !!d.result.is_bot, firstName: d.result.first_name || null, username: d.result.username || null }
              : { success: false, error: d.description || '조회 실패' };
          }
        }
        else if (url.pathname === '/api/send-telegram') result = await handleSendTelegram(env, body);
        else if (url.pathname === '/api/send-telegram-image') result = await handleSendTelegramImage(env, body);
        else if (url.pathname === '/api/generate-dm-reply') result = await handleGenerateDmReply(env, body);
        else if (url.pathname === '/api/post-instagram') result = await handlePostInstagram(env, body);
        else if (url.pathname === '/api/telegram-webhook') result = await handleTelegramWebhook(env, body);
        else if (url.pathname === '/api/setup-webhook') result = await handleSetupWebhook(env);
        else if (url.pathname === '/api/adjust-text') result = await handleAdjustText(env, body);
        else if (url.pathname === '/api/pipeline-start') result = await handlePipelineStart(env, ctx, body);
        else if (url.pathname === '/api/pipeline-step') result = await handlePipelineStepEndpoint(env, ctx, body);
        else if (url.pathname === '/api/run-pipeline') result = await handleRunPipeline(env, body, ctx);
        else if (url.pathname === '/api/pipeline-status') result = await handlePipelineStatus(env, url);
        else if (url.pathname === '/api/pipeline-log') result = await handlePipelineLog(env, url);
        else if (url.pathname === '/api/add-book-to-catalog') result = await handleAddBookToCatalog(env, body);
        else if (url.pathname === '/api/save-post') result = await handleSavePost(env, body);
        else if (url.pathname === '/api/get-post') result = await handleGetPost(env, body);
        else if (url.pathname === '/api/delete-book') result = await handleDeleteBook(env, body);
        else if (url.pathname === '/api/save-draft') result = await handleSaveDraft(env, body);
        else if (url.pathname === '/api/list-drafts') result = await handleListDrafts(env);
        else if (url.pathname === '/api/get-draft') result = await handleGetDraft(env, body);
        else if (url.pathname === '/api/delete-draft') result = await handleDeleteDraft(env, body);
        else if (url.pathname === '/api/reserve-book-number') {
          const bookNumber = await reserveBookNumber(env);
          result = { success: true, bookNumber };
        }
        else if (url.pathname === '/api/usage') {
          // 오늘(KST) Claude API 사용량 — 크레딧 소진 감시용
          const used = await getApiUsage(env);
          const imgUsed = await getImageUsage(env);
          result = { success: true, day: _kstDay(), used, softCap: DAILY_SOFT_CAP, hardCap: DAILY_HARD_CAP, savingMode: used > DAILY_SOFT_CAP, blocked: used > DAILY_HARD_CAP,
            geminiCover: !!(await getGeminiKey(env)), imageUsed: imgUsed, imageCap: DAILY_IMAGE_CAP };
        }
        else if (url.pathname === '/api/gemini-key') {
          // 앱에서 Gemini 키 저장/상태확인 (터미널·대시보드 없이). 값은 절대 반환하지 않는다.
          if (request.method === 'POST') {
            const key = String(body.key || '').trim();
            if (!key) { result = { success: false, error: '키가 비어 있습니다.' }; }
            else if (!/^AIza[0-9A-Za-z_\-]{20,}$/.test(key)) { result = { success: false, error: '키 형식이 올바르지 않습니다. AIza로 시작하는 Google AI Studio 키를 넣어주세요.' }; }
            else if (env.GEMINI_API_KEY) { result = { success: false, error: '이미 Cloudflare 시크릿으로 설정돼 있어 앱 저장이 필요 없습니다.' }; }
            else {
              // 저장 전에 실제로 이미지 1장 생성해 키 유효성 검증(1x1 테스트는 불가하므로 짧은 프롬프트)
              const test = await generateGeminiImageBytes(key, 'a small simple flat pastel illustration of a closed book on a table, no text');
              if (!test?.bytes?.length) { result = { success: false, error: '이 키로 이미지 생성에 실패했습니다. 키가 맞는지, Google AI Studio에서 이미지(Gemini) 사용이 켜져 있는지 확인해주세요.' }; }
              else { await env.PENDING_POSTS.put('gemini_api_key', key); result = { success: true, message: '표지 AI 키가 저장되었습니다. 다음 제작부터 표지가 Gemini로 생성됩니다.' }; }
            }
          } else {
            const has = !!(await getGeminiKey(env));
            result = { success: true, configured: has, source: env.GEMINI_API_KEY ? 'secret' : (has ? 'app' : 'none') };
          }
        }
        else if (url.pathname === '/api/telegram-recipients') {
          // 앱에서 텔레그램 추가 수신자(채팅 ID) 등록/삭제/조회 (터미널·대시보드 없이).
          if (request.method === 'POST') {
            const action = String(body.action || 'add');
            const chatId = String(body.chatId || '').trim();
            if (!/^-?\d+$/.test(chatId)) { result = { success: false, error: '채팅 ID는 숫자만 입력하세요 (예: 8231379366).' }; }
            else {
              let extra = await getExtraTelegramChatIds(env);
              if (action === 'remove') {
                extra = extra.filter(id => String(id) !== chatId);
                await env.PENDING_POSTS.put('telegram_extra_chat_ids', JSON.stringify(extra));
                result = { success: true, message: '삭제되었습니다.', extra };
              } else {
                if (String(env.TELEGRAM_CHAT_ID || '') === chatId || extra.some(id => String(id) === chatId)) {
                  result = { success: false, error: '이미 등록된 채팅 ID입니다.' };
                } else {
                  extra.push(chatId);
                  await env.PENDING_POSTS.put('telegram_extra_chat_ids', JSON.stringify(extra));
                  // 등록 즉시 실제로 알림을 보내 유효한 채팅 ID인지 검증(봇과 대화를 먼저 시작해야 전송 가능).
                  let verified = false, verifyErr = '';
                  try {
                    const vres = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
                      method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ chat_id: chatId, text: '[행간 — 연애 책방] 이 채팅으로 북 캐럿셀 제작 완료 알림을 받도록 등록되었습니다.' }),
                    });
                    verified = vres.ok;
                    if (!vres.ok) { const e = await vres.json().catch(() => ({})); verifyErr = e.description || String(vres.status); }
                  } catch (e) { verifyErr = e.message; }
                  if (!verified) {
                    extra = extra.filter(id => id !== chatId);
                    await env.PENDING_POSTS.put('telegram_extra_chat_ids', JSON.stringify(extra));
                    result = { success: false, error: `등록은 했지만 테스트 발송에 실패해 취소했습니다: ${verifyErr}. 먼저 텔레그램에서 해당 봇에게 아무 메시지나 보낸 뒤 다시 시도해주세요.` };
                  } else {
                    result = { success: true, message: '등록되었고 테스트 알림도 발송했습니다. 텔레그램을 확인해보세요.', extra };
                  }
                }
              }
            }
          } else {
            result = { success: true, primary: !!env.TELEGRAM_CHAT_ID, extra: await getExtraTelegramChatIds(env) };
          }
        }
        else if (url.pathname === '/api/reset-model-cache') {
          await clearModelCache(env);
          const m = await resolveModels(env.ANTHROPIC_API_KEY, env);
          result = { success: true, model: m.main, light: m.light, source: m.source };
        }
        else if (url.pathname === '/api/verify-book') {
          const cv = await crossVerifyBook(env, body.title, body.author);
          result = {
            success: true,
            exists: cv.status === 'found' ? true : (cv.status === 'notfound' ? false : null),
            realTitle: cv.title || null,
            realAuthor: cv.author || null,        // 네이버로 확인된 진짜 저자
            publisher: cv.publisher || null,
            status: cv.status,
            coupangSearchUrl: coupangSearchUrl(body.title),
          };
        }
        else if (url.pathname === '/api/get-dm') {
          const num = String(parseInt(String(body.number || '').replace(/[^0-9]/g, ''), 10) || 0).padStart(3, '0');
          const data = (num !== '000' && env.PENDING_POSTS)
            ? await env.PENDING_POSTS.get(`dm_book_${num}`, 'json').catch(() => null)
            : null;
          result = data
            ? { success: true, ...data }
            : { success: false, error: `No.${num} 게시물의 DM을 찾을 수 없습니다. (해당 책의 DM이 생성된 적 있는지 확인하세요)` };
        }
        else if (url.pathname === '/api/reset-catalog') {
          await env.PENDING_POSTS.put('book_catalog', JSON.stringify([]));
          await env.PENDING_POSTS.put('book_counter', '0');
          // 보관함 관련 키(post_/dm_book_/post_img_)도 함께 삭제
          let deleted = 0;
          for (const prefix of ['post_', 'dm_book_', 'post_img_']) {
            let cursor;
            do {
              const lst = await env.PENDING_POSTS.list({ prefix, cursor });
              for (const k of lst.keys) { await env.PENDING_POSTS.delete(k.name); deleted++; }
              cursor = lst.list_complete ? null : lst.cursor;
            } while (cursor);
          }
          result = { success: true, message: `도서관이 초기화되었습니다. (보관함 ${deleted}건 삭제)` };
        }
        else if (url.pathname === '/api/book-catalog') {
          const catalog = (await env.PENDING_POSTS?.get('book_catalog', 'json').catch(() => null)) || [];
          return new Response(JSON.stringify(catalog), { headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' } });
        }
        else return json({ error: '없는 경로입니다.' }, 404);

        return json(result);
      } catch (err) {
        return json({ error: err.message }, 500);
      }
    }

    // 도서 카탈로그 페이지 (GET /books)
    if (request.method === 'GET' && url.pathname === '/books') {
      return handleBooksPage(env);
    }

    return env.ASSETS.fetch(request);
  },

  // Cron Trigger — 두 가지 스케줄로 분기한다.
  //   "0 23 * * *" : 매일 오전 8시(KST=UTC+9) — 일일 자동 캐럿셀 생성
  //   "* * * * *"  : 매 1분 — 진행중 파이프라인을 한 단계씩 전진
  async scheduled(event, env, ctx) {
    if (event.cron === '0 23 * * *') {
      ctx.waitUntil(runDailyAuto(env));
    } else {
      ctx.waitUntil(runScheduled(env));
    }
  },
};
