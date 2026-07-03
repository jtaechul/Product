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

// 일시적 오류(429 요청과다 · 529 과부하 · 5xx · 네트워크)는 재시도로 흡수한다.
// 파이프라인이 Claude를 연속 6회 호출하므로, 단발 실패 한 번에 단계 전체가
// 무너지지 않도록 지수 백오프 재시도를 둔다 (이게 3·4단계 간헐 실패의 근본 원인이었음).
// 403은 영구 오류("Request not allowed") — 재시도해도 같은 결과. 즉시 실패 처리.
const RETRYABLE_STATUS = new Set([408, 409, 429, 500, 502, 503, 504, 529]);

async function callClaude(apiKey, opts, attempt = 0) {
  const MAX_RETRIES = 3;
  const BACKOFF_MS = [1000, 3000, 7000];
  const { system, user, max_tokens = 2048, env, tier = 'main' } = opts;
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
    const txt = await callClaude(env.ANTHROPIC_API_KEY, {
      env, tier: 'light', max_tokens: 150,
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
  return JSON.parse(cleaned.slice(start, end + 1));
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

async function handleSendTelegramImage(env, body) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error('TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.');
  }
  const { imageDataUrl, caption } = body;
  if (!imageDataUrl) throw new Error('imageDataUrl이 필요합니다.');
  const result = await sendTelegramPhotoFile(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, imageDataUrl, caption || '');
  if (!result) throw new Error('텔레그램 이미지 전송 실패');
  return { success: true };
}

// 텔레그램에는 "제작 완료 알림 + 확인하러 가기 링크"만 보낸다.
// (이미지·세부 문구는 보내지 않음. 인스타그램 게시 결정은 캐럿셀 제작 페이지에서 함.)
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

  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text: msg,
      reply_markup: {
        inline_keyboard: [[{ text: '확인하러 가기', url: link }]],
      },
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`텔레그램 발송 실패: ${err.description || res.status}`);
  }

  return { success: true, message: '텔레그램으로 제작 완료 알림과 확인 링크를 보냈습니다.' };
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
    env, tier: 'main',
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
      const ftText = await callClaude(env.ANTHROPIC_API_KEY, {
        env, tier: 'light', max_tokens: 200,
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

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
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
    user: `다음 책 정보로 5페이지 인스타그램 캐럿셀을 작성하세요.\n\n카테고리: ${category || '연애·관계 심리'}\n핵심 메시지: ${coreMessage}\n${targetAudience ? `대상: ${targetAudience}` : ''}\n${bookDesc ? `실제 책 소개(출판사 제공 — 이 책의 진짜 내용): ${bookDesc.slice(0, 600)}\n` : ''}\n[근거 규칙 — 절대 위반 금지] ${bookDesc ? '위 "실제 책 소개"가 이 책의 진짜 내용입니다. 3~5페이지의 통찰·위로·솔루션은 반드시 이 소개의 주제·관점과 일치해야 하며, 소개에 없는 개념·주장을 책의 것처럼 지어내지 마세요. 소개의 주제가 카테고리 톤과 거리가 있으면, 톤을 책의 실제 주제 쪽으로 맞추세요(책이 우선).' : '이 책의 실제 내용을 확신할 수 없으므로, 특정 개념·주장을 책의 것처럼 단정하지 말고 핵심 메시지 범위 안의 보편적 위로에 머무르세요.'}\n\n[전체 톤 — 카테고리에 맞춰 조절] 대상: ${lt.audience}.\n톤: ${lt.tone}.\n흐름: ${lt.flow}.\n\n페이지 가이드 (길이 규칙 엄수):\n1페이지(공감 훅 — 헤드라인만): 카드 전체를 단 하나의 마음을 건드리는 문장으로 채운다.\n  - headline: 40자 이내 완전한 문장. 독자가 연애에서 겪었을 구체적 순간·감정을 정확히 포착한다.\n    규칙: "당신이 이 사실을 모른다면" 패턴 절대 금지. "대부분의 사람들이" 금지. 공포·경고 톤 금지. 주어 없는 단어 조각 금지.\n    접근법: 독자가 혼자 느꼈던 감정을 들킨 듯한 문장.\n    좋은 예(이번 카테고리 톤): ${lt.hookExample}\n             "좋아할수록 더 차갑게 굴게 되는 사람이 있습니다"\n    나쁜 예(절대 금지): "당신의 연애는 실패하고 있다" / "이대로면 평생 혼자입니다" (공포·단정 톤)\n  - subtext 없음 — JSON에 포함하지 않는다.\n2페이지(패턴 발견): 독자가 반복해온 연애 패턴을 부드럽게 이름 붙여 보여준다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 40자 이내. 독자가 "맞아, 나 그래"라고 느낄 구체적 행동·상황 묘사. 수치 금지, 감정과 장면 위주.\n3페이지(마음의 이유): 그 패턴의 심리적 뿌리를 따뜻하게 설명한다(애착, 상처, 두려움 등). 비난하지 않는다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 40자 이내. "당신이 이상한 게 아니라, 이런 마음이 있었던 것입니다" 같은 위로의 통찰. 심리학 개념을 쉽게 풀어 쓰되 학술 인용 금지.\n4페이지(위로의 실마리): 완전한 해답 대신 '이렇게 바라보면 달라진다'는 방향을 부드럽게 암시한다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 40자 이내. 마지막 줄은 희망적 여운으로 끝낸다. 단정적 해결책 금지.\n5페이지(책 공개 — 마무리): 독자에게 오늘의 책을 건넨다. (제목·저자·표지는 시스템이 자동으로 함께 보여주므로 본문 텍스트에 제목·저자를 직접 쓰지 말 것.)\n  - cta: 4페이지의 위로를 잇는 따뜻한 마무리 + 핵심 솔루션 한 문장(${lt.theme}에서 오늘 가져갈 마음의 방향). A/B·질문·"댓글" 언급 금지. 독자 가슴에 남는 한 문장.\n  - linkText: 그 마음에 책을 자연스럽게 건네는 한 줄 (예: "이 마음에 오래 곁이 되어줄 책을 소개합니다"). 제목은 쓰지 말 것(시스템이 표지·제목·저자를 함께 노출). "프로필 링크" 언급은 불필요.\n\nJSON:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });

  const pages = extractJson(text);
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
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
    max_tokens: 1024,
    system: '당신은 소셜미디어 콘텐츠 전문 편집장 겸 저작권 검토자입니다. 반드시 JSON만 응답합니다.',
    user: `책 "${bookInfo.title}" (저자: ${bookInfo.author}) 캐럿셀을 아래 5가지 기준으로 평가하세요.\n${bookDesc ? `\n실제 책 소개(출판사 제공 — 부합도 채점의 근거):\n${bookDesc}\n` : ''}\n캐럿셀 내용:\n${JSON.stringify(pages, null, 2)}\n\n평가 기준 (100점 만점):\n1. accuracy(책 내용 부합도): ${bookDesc ? '캐럿셀의 통찰·솔루션이 위 "실제 책 소개"의 주제·메시지와 일치하는가? 소개와 무관한 주제를 책의 것처럼 말하면 크게 감점.' : '캐럿셀 내용이 해당 책의 실제 메시지와 일치하는가? (소개 미제공 — 확신 없으면 보수적으로 감점)'} 0~20\n2. factual(사실 정확성): 수치·통계·사례에 명백한 오류나 과장이 없는가? 0~20\n3. copyright(저작권 안전성): 책의 핵심 내용을 그대로 옮기지 않고 요약·재해석했는가? 저자명·책 제목이 본문에 노출되지 않는가? 0~20\n4. engagement(공감·참여 유도): 30대 독자가 "이건 내 얘기다"라고 느껴 저장·공유하고 싶어지는 깊은 공감과 위로가 있는가? 따뜻한 톤이 유지되는가(공포·단정·비난 톤이면 감점)? 0~25\n5. quality(문장 품질): 오타·비문·어색한 표현이 없고 간결한가? 0~15\n\nJSON: {"totalScore":85,"scores":{"accuracy":17,"factual":16,"copyright":18,"engagement":22,"quality":12},"feedback":"전체 평가 2~3문장","improvements":["구체적 개선점1","개선점2","개선점3"],"approved":true}\napproved는 totalScore>=70이면 true.`
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
const SCENE_ANCHOR = 'no people in frame, an atmospheric symbolic scene only (cozy interior, window, quiet place or meaningful objects)';

// 페이지별 폴백 프롬프트 — Claude 생성 실패 시 사용. (인물 배치는 personPage로 동적 결정)
const FALLBACK_IMAGE_PROMPTS = {
  page1: 'a woman seen from behind sitting alone by a large window at dusk, soft city lights bokeh outside, quiet wistful mood, empty space around her',
  page2: 'an empty cafe table by a window with a single cup and a phone left face-down, soft afternoon light, tender lonely atmosphere',
  page3: 'a cozy dim bedroom corner with a crumpled blanket and a warm glowing bedside lamp, introspective quiet mood, soft shadows',
  page4: 'a window as gentle morning light streams in over a sheer curtain, hopeful warm glow, a quiet turning moment',
  page5: 'an open book resting on a sunlit windowsill with sheer curtains gently glowing, calm hopeful morning light',
};

// 페이지별 감정 역할 — 1페이지의 감정만 레인(설렘/이별/자존감)에 따라 달라진다.
// 인물 배치는 1장 고정 + 2~4 중 1장(personPage)으로 동적 결정.
const LANE_PAGE1_EMOTION = {
  light: '좋아하는 마음을 들킨 듯한 설렘·두근거림',
  core: '이별 후의 쓸쓸함·그리움',
  self: '나를 가만히 돌아보는 조용한 마음',
};
function pageVisualDirections(lane) {
  return {
    page1: `혼자 있는 그녀 — 들킨 듯한 첫 감정(${LANE_PAGE1_EMOTION[lane] || LANE_PAGE1_EMOTION.core}). 뒷모습/옆모습, 여백 넉넉히(스크롤을 멈추는 표지 컷·인물 고정).`,
    page2: '반복된 패턴/마음이 머무는 한 순간 — 장소·사물 또는 그녀.',
    page3: '마음의 뿌리를 들여다보는 조용한 순간 — 장소·사물 또는 그녀.',
    page4: '빛이 드는 전환·희망의 실마리 — 장소·사물 또는 그녀(따뜻한 아침빛).',
    page5: '평온한 마무리 — 책/창가 등 고요한 장면(하단은 책 공개 패널이 덮음, 인물 없음 권장).',
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
    page4: [pages.page4?.headline, pages.page4?.body].filter(Boolean).join(' / '),
    page5: [pages.page5?.cta, pages.page5?.body].filter(Boolean).join(' / '),
  };

  const PV = pageVisualDirections(laneOf(bookInfo.category)); // 레인별 1페이지 감정 반영

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
    max_tokens: 1000,
    system: '당신은 한국 웹툰풍 감성 일러스트 아트 디렉터입니다. 연애·관계(설렘·이별·자존감) 주제의 책 카드뉴스 배경으로 쓸 Flux 이미지 영어 프롬프트를 작성합니다.\n\n[인물 배치 — 매우 중요] 사람(같은 30대 한국 여성)은 정확히 2장에만 등장합니다.\n· 1페이지: 무조건 그녀(스크롤을 멈추는 표지 컷).\n· 2~4페이지 중 단 한 곳: 각 페이지의 "문장"을 읽고, 인물이 있을 때 감정이 가장 살아나는 페이지 한 곳을 골라 그녀를 넣으세요(예: 구체적 행동·장면이 그려지는 문장). 나머지 페이지(2~4 중 둘)와 5페이지는 사람 없는 분위기 장면.\n· 어느 페이지를 골랐는지 personPage로 반드시 알려주세요(page2/page3/page4 중 하나).\n\n[얼굴·해부학 규칙 — 매우 중요] 매번 자세·시점·표정·장소를 확 다르게 하세요(복붙 구도 금지). 단, 한 컷 안에서 몸의 방향과 얼굴 방향이 반드시 일치해야 합니다: 뒷모습이면 얼굴을 아예 묘사하지 말고(뒤통수만), "어깨 너머로 뒤돌아보기" 같은 목이 꺾이는 구도는 절대 금지. 얼굴이 보이는 컷은 앞모습 또는 3/4 정면으로 하고(극단적 옆모습은 눈이 어색해지므로 피함), 크고 또렷한 애니 눈 또는 감은 눈으로 그리세요. 완전한 애니 스타일이므로 눈 뜬 앞모습·미소도 환영합니다.\n\n[손·손가락 규칙] 무료 AI는 손·손가락(특히 종이·책장을 만지는 손)을 자주 뭉갭니다. 그러니 손은 소매·주머니에 넣거나 프레임 밖으로 두고, 손가락을 클로즈업하거나 종이·책장을 세밀하게 만지는 구도는 피하세요. 인물이 책을 든다면 덮인 책을 느슨히 안거나 무릎·탁자 위에 두고 손가락은 드러내지 마세요.\n\n[스타일 고정 — 5장 공통] "귀엽고 퀄리티 높은 애니풍" 일러스트: 둥글고 사랑스러운 이목구비, 깔끔한 라인, 부드러운 플랫 셀 셰이딩, 포근한 빛. 실사·반실사·3D 렌더 절대 금지(섬찟함 방지). 색감·분위기는 시스템이 주제에 맞게 자동으로 덧붙이므로 너는 색 지정 대신 장면·감정에 집중. 인물 컷과 배경 컷이 한 시리즈로 묶이게.\n\n[배경 장면 발상] 창가·카페·침대·책상·골목·버스 안, 휴대폰·편지·머그·담요·우산·책, 빈 의자, 비 오는 유리창, 저물녘→새벽빛 등으로 감정을 상징. 5장의 장소·구도가 서로 뚜렷이 다르게.\n\n[규칙]\n1. 구도·조명 구체적으로 (back view, side profile, wide shot, soft window light, golden morning light)\n2. 인물 컷은 정면 얼굴 클로즈업 금지 / 배경 컷은 사람 없음(no people)\n3. 텍스트·글자·숫자 없음 (no text, no letters, no words)\n4. 하단 30%는 부드럽고 단순하게 (텍스트 오버레이 공간)\n5. 각 프롬프트 영어 25~55단어. 인물 외형·화풍·사람유무는 시스템이 자동으로 덧붙이므로, 너는 "그 장의 장면·자세/사물·감정·장소"에 집중해 묘사.\n반드시 JSON만 응답한다.',
    user: `책 제목: ${bookInfo.title || ''}\n카테고리: ${bookInfo.category || '이별·재회·회복'}\n책 핵심 주제: ${bookInfo.coreMessage || ''}\n\n1페이지는 무조건 그녀(인물). 2~4페이지 문장을 읽고 인물이 가장 어울리는 한 곳을 골라 그녀를 넣고(personPage로 표기), 나머지와 5페이지는 사람 없는 분위기 배경으로 묘사하세요.\n\n1페이지 ${PV.page1}\n  문장: ${pageContents.page1}\n2페이지 ${PV.page2}\n  문장: ${pageContents.page2}\n3페이지 ${PV.page3}\n  문장: ${pageContents.page3}\n4페이지 ${PV.page4}\n  문장: ${pageContents.page4}\n5페이지 ${PV.page5}\n  문장: ${pageContents.page5}\n\n[필수] 5장의 장소·구도가 서로 겹치지 않게. 인물은 1페이지 + (2~4 중 personPage) 두 곳만, 나머지는 사람 없음. 텍스트·글자 없음.\n\nJSON: {"page1":"...","page2":"...","page3":"...","page4":"...","page5":"...","personPage":"page3"}`,
  });

  const parsed = extractJson(text);

  // 인물 2번째 페이지: Claude가 고른 personPage(2~4) 사용, 유효하지 않으면 page4로 폴백.
  let personPage = parsed.personPage;
  if (!['page2', 'page3', 'page4'].includes(personPage)) personPage = 'page4';
  const PERSON_PAGES = new Set(['page1', personPage]);

  // 5페이지 프롬프트만 추려 검증 — 누락 시 페이지별 폴백으로 보완
  const prompts = {};
  for (let i = 1; i <= 5; i++) {
    const key = `page${i}`;
    const v = parsed[key];
    prompts[key] = (v && typeof v === 'string' && v.trim()) ? v.trim() : FALLBACK_IMAGE_PROMPTS[key];
  }

  // 페이지별로 앵커를 다르게 붙인다: 인물 페이지(1 + personPage)=캐릭터 앵커, 나머지=장면 앵커.
  // 화풍·색감 앵커(STYLE_ANCHOR)는 5장 공통 → 인물/배경이 한 시리즈로 묶인다.
  const base = 'https://image.pollinations.ai/prompt/';
  const tail = ', no text, no letters, no words, high quality';
  const pick = arr => arr[Math.floor(Math.random() * arr.length)];
  const mood = categoryMood(bookInfo.category);   // 주제별 분위기·색감(이별·자존감·설렘 등)
  const images = {};
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
    images[page] = `${base}${encodeURIComponent(full)}?width=1080&height=1080&nologo=true&seed=${seed}&model=flux&enhance=true`;
  }

  return { success: true, images, prompts };
}

// 릴스 1페이지 전용 "스크롤을 멈추는 강한 훅" 생성 (캐럿셀 1페이지의 잔잔한 공감문과 별개).
async function handleReelHook(env, body) {
  const { pages, bookInfo } = body;
  const summary = [pages?.page1?.headline, pages?.page2?.headline, pages?.page4?.headline].filter(Boolean).join(' / ');
  const fallback = pages?.page1?.headline || '';
  const lt = laneTone(bookInfo?.category); // 3레인 톤(설렘/이별/자존감)
  try {
    const text = await callClaude(env.ANTHROPIC_API_KEY, {
      env, tier: 'light', max_tokens: 400,
      system: `당신은 인스타그램 릴스 훅 카피라이터입니다. 타깃은 ${lt.audience} 여성. 스크롤을 1초 만에 멈추게 하는 강한 첫 문장(훅)을 만듭니다.\n규칙:\n① 유형은 "콕 집어내는 감정"(예: ${lt.hookExample}) 또는 "궁금증 격차" 또는 "금기/질문". 감정의 결은 카테고리에 맞게: ${lt.tone}.\n② 한 줄, 18~28자. 너무 길지 않게.\n③ 따뜻하되 강렬하게. 공포·단정·비난·자극적 과장 금지.\n④ 책 제목·저자 노출 금지. 이모지 금지.\n반드시 JSON만 응답.`,
      user: `책 핵심: ${bookInfo?.coreMessage || ''}\n캐럿셀 요지: ${summary}\n\n스크롤을 멈추게 하는 릴스 훅 후보 3개를 만들고, 그중 가장 강한 하나를 고르세요.\nJSON: {"candidates":["...","...","..."],"best":"가장 강한 한 줄"}`,
    });
    const r = extractJson(text);
    const best = (r.best || (Array.isArray(r.candidates) && r.candidates[0]) || fallback || '').toString().trim();
    return { success: true, hook: best || fallback, candidates: Array.isArray(r.candidates) ? r.candidates : [] };
  } catch (e) {
    return { success: true, hook: fallback, candidates: [] };
  }
}

// 릴스 대본(4장) — 한 편의 흐름으로 "연결되게" 생성하고, 자체 검증(연결성·가독성)까지 한 번에.
// 캐럿셀의 조각을 잘라 붙이던 방식(어색함)을 대체한다. 5번째 장(책 공개)은 시스템이 표지로 처리.
async function handleGenerateReel(env, body) {
  const { pages, bookInfo } = body;
  const arc = [pages?.page1?.headline, pages?.page2?.headline, pages?.page3?.headline, pages?.page4?.headline, pages?.page5?.cta]
    .filter(Boolean).join(' / ');
  // 폴백: 캐럿셀 헤드라인 그대로
  const fb = {
    s1: pages?.page1?.headline || '', s2: pages?.page2?.headline || '',
    s3: pages?.page3?.headline || '', s4: pages?.page4?.headline || '',
  };
  const lt = laneTone(bookInfo?.category); // 3레인 톤(설렘/이별/자존감)
  try {
    const text = await callClaude(env.ANTHROPIC_API_KEY, {
      env, tier: 'light', max_tokens: 700,
      system: `당신은 인스타 릴스 대본 카피라이터입니다. 타깃은 ${lt.audience} 여성. 감정의 결: ${lt.tone}.\n[목표] 4개의 슬라이드 문구가 "한 편의 이야기처럼 자연스럽게 이어지게" 씁니다(뚝뚝 끊긴 조각 금지).\n[구성·흐름]\n· s1(훅): 스크롤을 멈추는 강한 첫 문장(콕 집는 감정/궁금증). 18~28자.\n· s2: s1에서 자연스럽게 이어받아 그 감정·패턴을 구체적 장면으로. \n· s3: 그 마음의 이유를 따뜻하게 짚음(비난 금지).\n· s4: 희망으로 전환하는 마무리(단정적 해결책 금지, 여운).\n[문체·규칙] 존댓말·문어체, 따뜻하되 강렬. 각 슬라이드 한 화면에서 4~5초에 읽히게 45자 이내(한두 문장). 책 제목·저자 노출 금지, 이모지 금지, 공포·단정 금지. 앞 문장과 접속·지시어로 연결되게(예: "그런데", "사실은", "그래서").\n[검증] 초안을 쓴 뒤, 4장이 매끄럽게 이어지는지·각 장이 4~5초에 읽히는지 스스로 점검하고 어색하면 고쳐서 최종본만 냅니다.\n반드시 JSON만 응답.`,
      user: `책 핵심 주제: ${bookInfo?.coreMessage || ''}\n카테고리: ${bookInfo?.category || '이별·재회·회복'}\n캐럿셀 흐름(참고): ${arc}\n\n위 흐름을 살리되, 4개 슬라이드가 자연스럽게 이어지는 릴스 대본을 쓰고 스스로 검증·보완해 최종본을 내세요.\nJSON: {"reel":{"s1":"...","s2":"...","s3":"...","s4":"..."},"validation":{"connected":true,"readable":true,"score":0~100,"note":"연결성·가독성 한줄평"}}`,
    });
    const r = extractJson(text);
    const reel = r.reel || {};
    const out = {
      s1: (reel.s1 || fb.s1).toString().trim(),
      s2: (reel.s2 || fb.s2).toString().trim(),
      s3: (reel.s3 || fb.s3).toString().trim(),
      s4: (reel.s4 || fb.s4).toString().trim(),
    };
    const validation = r.validation || { connected: true, readable: true, score: null, note: '' };
    return { success: true, reel: out, validation };
  } catch (e) {
    return { success: true, reel: fb, validation: { connected: true, readable: true, score: null, note: '자동 생성 실패 — 캐럿셀 문구로 대체' } };
  }
}

async function handleGenerateCaption(env, body) {
  const { pages, bookInfo, dmKeyword, bookNumber } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 댓글 키워드 힌트: 특수기호만 제거하고 원형 그대로 Claude에 전달.
  // Claude가 자연스러운 완결 단어(2~3자)를 직접 선택한다 — 강제 절단 금지.
  const kwHint = (dmKeyword || bookInfo.category || '독서').replace(/[^가-힣a-zA-Z0-9]/g, '') || '독서';
  const lt = laneTone(bookInfo.category); // 3레인 톤(설렘/이별/자존감)

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
    max_tokens: 512,
    system: `당신은 ${lt.theme}를 다루는 연애 책을 소개하는 인스타그램 콘텐츠 크리에이터입니다. ${lt.audience} 독자가 자기 마음을 들킨 듯 공감해 "저장"하고 "친구에게 공유"하고 싶어지는 캡션을 씁니다. 톤: ${lt.tone}. 팔로워 성장이 목적이므로 저장·공유를 유도합니다. 노골적 판매·공포·단정·비난 금지. 반말 절대 금지 — 문어체·존댓말(~습니다/~네요/~까요)만. 반드시 JSON만 응답합니다.`,
    user: `책 카테고리: ${bookInfo.category || '이별과회복'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n캐럿셀 첫 줄 훅: ${pages.page1?.headline || ''}\n\n인스타그램 캡션을 작성하세요. (이 게시물의 목적: 저장·공유로 팔로워 늘리기. 댓글·DM·A/B 유도 없음.)\n\n[캡션 구조 — 순서 엄수]\n1줄: 독자가 ${lt.theme}에서 혼자 느꼈을 감정을 포착한 공감형 한 문장 (책 제목은 시스템이 따로 붙이므로 본문엔 쓰지 말 것. "당신이 모른다면"·"대부분의 사람들이" 금지. 공포·단정 금지)\n2~3줄: 캐럿셀 핵심 위로/통찰 초간결 요약 (반복 금지)\n끝에서 둘째 줄: 저장 유도 ("마음이 복잡한 날 다시 꺼내보고 싶다면 저장해두세요" 형태)\n마지막 줄: 공유 유도 ("같은 마음을 지나는 사람에게 조용히 건네주세요" 형태)\n\n[추가 규칙]\n- 해시태그: 정확히 3개 (카테고리에 맞게. 예: ${lt.hashtagExample})\n- 전체 6줄 이내, 짧고 따뜻하게\n- 댓글·DM·A/B·"프로필 링크" 언급 금지 (저장·공유만)\n\nJSON: {"caption":"1줄\\n2줄\\n3줄\\n저장유도줄\\n공유유도줄","hashtags":["#이별","#연애심리","#책추천"]}`,
  });

  const result = extractJson(text);
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
    system: `당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다.\n핵심 규칙(절대 위반 금지):\n1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.\n2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.\n3. 5페이지는 반문·열린 결말 구조 — 구매 유도나 직접 행동 지시 없이 독자에게 질문을 던진다.\n4. 모든 콘텐츠에 반말을 절대 사용하지 않는다 — 문어체·존댓말(~습니다/~합니다/~세요)만 허용.\n반드시 JSON만 응답한다.`,
    user: `캐럿셀을 피드백에 맞게 개선하세요.\n카테고리: ${bookInfo.category || '연애·관계 심리'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n${bookInfo.description ? `실제 책 소개(출판사 — 통찰·솔루션은 이 소개의 주제와 일치해야 하며, 소개에 없는 개념을 책의 것처럼 지어내지 말 것): ${String(bookInfo.description).slice(0, 600)}\n` : ''}\n이전 버전:\n${JSON.stringify(previousPages, null, 2)}\n\n피드백: ${feedback}\n개선 요청: ${improvements.join(' / ')}\n\n텍스트 길이 기준:\n- 1페이지 headline: 40자 이내 완전한 문장(주어+상황+결과). 단어 조각 절대 금지. subtext 없음.\n- 2~4페이지 headline: 18자 이내, body: 3~4줄(줄당 45자 이내). 구체적 수치·사례 포함.\n- JSON 형식: {"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},...}\n\nJSON:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });
  return { success: true, pages: extractJson(text) };
}

// 캔버스 넘침 감지 후 텍스트 단축
async function handleAdjustText(env, body) {
  const { pages, bookInfo, issues } = body;
  if (!pages || !issues?.length) return { success: true, pages };

  const issueDesc = issues.map(i =>
    `${i.page} ${i.type}: ${i.currentLines}줄(최대 ${i.maxLines}줄) — "${i.text}"`
  ).join('\n');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
    max_tokens: 1024,
    system: '당신은 인스타그램 카드뉴스 카피라이터입니다. 주어진 텍스트를 지정된 줄 수 이내로 압축합니다. 반말 절대 금지 — 문어체·존댓말만 허용. 반드시 JSON만 응답합니다.',
    user: `다음 캐럿셀 텍스트가 이미지 레이아웃에서 넘칩니다. 각 항목을 지정된 최대 줄 수 이내로 압축하세요.\n의미·임팩트는 유지하되 더 간결하게 다듬어주세요.\n\n현재 캐럿셀:\n${JSON.stringify(pages, null, 2)}\n\n넘치는 항목:\n${issueDesc}\n\n압축 규칙:\n- headline: 최대 3줄 (40자 이내, 강렬하게)\n- body: 최대 5줄 (줄당 45자 이내)\n- 책 제목·저자명 절대 노출 금지\n\n전체 pages JSON을 반환하세요:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`,
  });

  try {
    return { success: true, pages: extractJson(text) };
  } catch {
    return { success: true, pages }; // 파싱 실패 시 원본 유지
  }
}

// ===== Phase 5 준비: DM 자동 회신 내용 생성 =====
async function handleGenerateDmReply(env, body) {
  const { pages, bookInfo, affiliateLink, affiliateLinks, bookNumber } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 여러 링크 지원: affiliateLinks 배열 우선, 없으면 단일 affiliateLink 폴백
  const links = Array.isArray(affiliateLinks) && affiliateLinks.length
    ? affiliateLinks.filter(l => l && l.trim())
    : (affiliateLink ? [affiliateLink] : []);
  const linksText = links.length
    ? links.map((l, i) => `${i + 1}. ${l}`).join('\n')
    : '';

  // 책 페이지 딥링크: 도서 번호가 있으면 해당 책 카드로 바로 스크롤되는 앵커(#번호)를 건다.
  const bookLink = bookNumber ? `${SELF_URL}/books.html#${bookNumber}` : `${SELF_URL}/books.html`;
  const linkGuide = bookNumber
    ? `${bookLink} (이 링크를 누르면 오늘의 책(No.${bookNumber}) 페이지가 바로 열립니다)`
    : `${bookLink}`;

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main',
    max_tokens: 1600,
    system: '당신은 연애·관계 심리 전문 상담가이자 인스타그램 DM 회신 작성자입니다. 게시물 마지막 장 A/B 투표에 댓글을 남긴 팔로워에게 보낼 DM을 "하나의 메시지"로 작성합니다. 이 한 통의 DM 안에 A를 선택한 경우와 B를 선택한 경우의 내용을 모두 담아, 받은 사람이 자기 쪽을 읽으면 되게 합니다. 각 경우마다 그 성향을 따뜻하게 진단하고 책 내용에 근거한 구체적 솔루션을 함께 제시합니다. 단정·비난·공포 금지, 위로와 통찰의 톤. 노골적 판매 금지. 반말 절대 금지 — 존댓말만. 반드시 JSON만 응답합니다.',
    user: `책 제목: ${bookInfo.title}\n저자: ${bookInfo.author || ''}\n카테고리: ${bookInfo.category || '연애·관계 심리'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n\n게시물 마지막 장의 A/B 투표 질문(이 선택지의 A·B 의미를 정확히 반영하세요):\n${pages.page5?.cta || ''}\n\n[작업] A·B 댓글 응답자 모두에게 보낼 "하나의 DM"을 작성하세요. A용/B용을 따로 만들지 말고, 한 통의 메시지 안에 두 경우를 모두 담으세요.\n\nDM 구성 순서:\n1. 따뜻한 인사 한 문장\n2. "A를 선택하셨다면" 섹션 — A 성향의 심리 진단(왜 그런 마음이 드는지, 애착·두려움·습관 등 뿌리)과 오늘부터 해볼 수 있는 책 기반 솔루션. 진단+솔루션 합쳐 최소 3문장 이상.\n3. "B를 선택하셨다면" 섹션 — B 성향의 심리 진단과 책 기반 솔루션. 진단+솔루션 합쳐 최소 3문장 이상. (A와 분명히 다른 내용)\n4. 책 안내: 더 깊은 이야기는 오늘의 책 "${bookInfo.title}"에 담겨 있다는 뉘앙스 한 문장.\n5. 도서 링크 안내: 아래 링크를 DM 본문에 그대로 포함(필수, 누락 금지):\n${linkGuide}\n${linksText ? `6. 구매 링크 안내 — 아래 링크도 그대로 포함(누락 금지):\n${linksText}\n` : ''}${linksText ? '7' : '6'}. 따뜻한 마무리 한 문장\n\n[톤 주의] A/B 어느 쪽이든 "당신이 틀렸다"는 뉘앙스 금지. 두 성향 모두 이해받아 마땅하다는 전제로 씁니다. A/B 섹션은 줄바꿈으로 또렷이 구분하세요.\n\nJSON: {"dmText":"A·B 두 경우를 모두 담은 하나의 DM 전체(줄바꿈은 \\n)"}`,
  });

  const parsed = extractJson(text);
  const dmText = parsed.dmText || parsed.dmTextA || '';

  // (구) 파이프라인ID 기반 임시 저장 — Phase 5 자동 감지용 (7일)
  if (env.PENDING_POSTS && body.pipelineId) {
    const pid = String(body.pipelineId).replace(/[^a-zA-Z0-9]/g, '');
    if (pid) {
      await env.PENDING_POSTS.put(`dm_reply_${pid}`, dmText, { expirationTtl: 604800 });
    }
  }

  // 도서 번호 기반 영구 저장 — 몇 달 뒤 댓글이 달려도 번호로 DM을 꺼낼 수 있게(유효기간 없음)
  if (env.PENDING_POSTS && bookNumber) {
    const num = String(parseInt(String(bookNumber).replace(/[^0-9]/g, ''), 10) || 0).padStart(3, '0');
    if (num !== '000') {
      await env.PENDING_POSTS.put(`dm_book_${num}`, JSON.stringify({
        number: num,
        title: bookInfo.title || '',
        dmText,
        date: new Date().toISOString().slice(0, 10),
      }));
    }
  }

  return { success: true, dmText, dmTextA: dmText, dmTextB: dmText };
}

// ===== 체인 파이프라인 (탭 닫아도 서버에서 계속 진행) =====
// 각 단계마다 독립 Worker 인보케이션 → 단계별 새 30초 예산

// ===== 크론 구동 파이프라인 상태머신 =====
// self-fetch 사슬을 제거하고, 1분마다 도는 Cron Trigger가 "진행중" 파이프라인을
// 한 단계씩 전진시킨다. 한 단계가 누락/중단돼도 다음 크론 틱이 자동 재개 → 자가복구.
// (Cloudflare Workers는 긴 작업을 보장하지 않으므로, 복구 가능한 외부 스케줄러가 필요)

const PIPELINE_TTL = 3600;        // 파이프라인 상태 보존(초)
const PLOG_TTL = 604800;          // 작업 로그 보존(초, 7일) — 사후 오류 분석용
const STEP_STALE_MS = 5 * 60 * 1000;  // 5분 후 멈춘 단계 재실행 (Claude API 느릴 때 오조기 재시도 방지)
const ERROR_RETRY_MS = 15 * 1000;     // 일시적 오류 후 재시도 최소 간격 (크론 다음 틱에 재시도)
const MAX_ERROR_RETRIES = 5;          // 일시적 오류 자동 재시도 한도 (초과 시 영구 실패로 마감)

// 오류 메시지에서 상태코드를 추출해 "일시적(재시도 가치 있음)" 오류인지 판정한다.
// callClaude는 실패를 "[403] ..." 형태로 코드를 앞에 붙여 던진다.
// - 코드가 RETRYABLE_STATUS(429·5xx·529 등)면 일시적 → 크론이 자동 재시도
// - 403은 영구 오류("Request not allowed") → 재시도 없이 즉시 영구 실패
// - 코드가 없으면(네트워크·타임아웃·모델 해석 실패 등) 일시적으로 간주
function isTransientPipelineError(msg) {
  // 가짜 책(실존 미확인)·성인 차단은 재시도해도 동일 → 영구 오류로 즉시 마감
  if (/BOOK_NOT_FOUND|ADULT_BLOCKED/.test(msg || '')) return false;
  // 지역 라우팅 차단(REGION_BLOCKED)은 일시적 — 다음 크론 틱은 다른 경유지에서
  // 실행될 수 있으므로 반드시 재시도한다(코드가 [403]이어도 영구 처리 금지).
  if (/REGION_BLOCKED/.test(msg || '')) return true;
  const m = /^\[(\d+)\]/.exec(msg || '');
  if (!m) return true;
  return RETRYABLE_STATUS.has(parseInt(m[1], 10));
}

// 작업 로그 기록 — 별도 KV 키(plog_<id>). 파이프라인 상태가 만료돼도 7일간 남아 사후 분석 가능.
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
      await setActive('AI가 책을 자동 선정 중...');
      const as = state.autoSelect;
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
      await savePipelineStatus(env, pipelineId, { bookInfo, label: `책 선정: ${bookInfo.title}` });
      await logStep(env, pipelineId, { step, phase: 'book-selected', note: `${bookInfo.title} / ${bookInfo.author}` });
      if (state.isAutoDaily) {
        // 일일 자동: 사용 책 기록(최근 30권) — 다음 날 중복 추천 방지
        try {
          const usedStr = await env.PENDING_POSTS.get('daily_used_books');
          const used = usedStr ? JSON.parse(usedStr) : [];
          await env.PENDING_POSTS.put('daily_used_books', JSON.stringify([...used, chosen.title].slice(-30)), { expirationTtl: 31 * 24 * 3600 });
        } catch {}
      }
    }
    if (!bookInfo?.title) throw new Error('책 정보가 없습니다.');
    await setActive('Claude AI가 5페이지 카드뉴스를 작성 중...');
    await logStep(env, pipelineId, { step, phase: 'start', model: _modelCache?.main });
    // 1단계(생성) 실패는 치명적 → throw하여 advancePipeline이 error로 마감
    const genData = await handleGenerate(env, bookInfo);
    const pages = genData.pages;
    const patch = { step: 1, stepStatus: 'done', label: '5페이지 카드뉴스 생성 완료', pages };
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
    const { pages } = state;
    await setActive('AI 이미지 프롬프트 생성 중...');
    await logStep(env, pipelineId, { step, phase: 'start' });
    let images = null;
    try {
      const imgData = await handleGenerateImages(env, { pages, bookInfo });
      const urlMap = imgData.images; // { page1: 'https://image.pollinations.ai/...', ... }

      // 5장을 동시에 다운로드해 KV에 바이너리로 저장 (90초/장 타임아웃)
      await setActive('Pollinations.ai 이미지 다운로드 중 (1~2분 소요)...');
      const pageKeys = ['page1', 'page2', 'page3', 'page4', 'page5'];
      const downloadResults = await Promise.allSettled(
        pageKeys.map(async page => {
          const url = urlMap[page];
          if (!url) throw new Error('URL 없음');
          const ctrl = new AbortController();
          const timer = setTimeout(() => ctrl.abort(), 90000);
          try {
            const res = await fetch(url, { signal: ctrl.signal });
            clearTimeout(timer);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const buf = await res.arrayBuffer();
            await env.PENDING_POSTS.put(`img_${pipelineId}_${page}`, buf, { expirationTtl: 24 * 3600 });
            return { page, size: buf.byteLength };
          } catch (e) {
            clearTimeout(timer);
            throw e;
          }
        })
      );

      // 성공한 페이지는 /api/image 경로, 실패 시 원본 Pollinations URL 폴백
      images = {};
      for (let i = 0; i < pageKeys.length; i++) {
        const page = pageKeys[i];
        if (downloadResults[i].status === 'fulfilled') {
          images[page] = `/api/image?id=${pipelineId}&page=${page}`;
        } else {
          images[page] = urlMap[page];
          await logStep(env, pipelineId, { step, phase: 'warn', error: `${page} 다운로드 실패: ${downloadResults[i].reason?.message}` });
        }
      }
    } catch (e) {
      await logStep(env, pipelineId, { step, phase: 'warn', error: '이미지 생성 실패(계속 진행): ' + e.message });
    }
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
  if (stepStatus === 'active') {
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

  let checked = 0, advanced = 0;
  const stale = [];
  for (const id of ids) {
    if (checked >= 30 || advanced >= 5) break;   // 한 틱당 작업량 상한
    checked++;
    const state = await env.PENDING_POSTS.get(`pipeline_${id}`, 'json').catch(() => null);
    if (!state) { stale.push(id); continue; }                 // 만료·삭제 → 인덱스 정리
    if (state.status !== 'running') { stale.push(id); continue; } // 완료·오류 → 인덱스 정리
    await advancePipeline(env, id);
    advanced++;
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
  if (!bookInfo?.title && !autoSelect?.category) throw new Error('책 정보(bookInfo.title) 또는 자동 선정 카테고리(autoSelect.category)가 필요합니다.');
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
  // 이 킥이 실패하거나 중간에 죽어도 크론이 자동으로 이어받는다 → 화면 상태 무관.
  // 단, autoSelect(책 선정+생성)는 브라우저 요청 수명(약 30초)을 확실히 넘겨 킥이
  // 도중에 죽고 5분 스테일 대기까지 유발 → 킥을 생략하고 다음 크론 틱(≤60초)이
  // 크론의 넉넉한 실행 예산으로 바로 처리하게 한다(실측: 킥 사망 시 5~6분 지연).
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
    await savePipelineStatus(env, pipelineId, { step: 1, stepStatus: 'done', label: '5페이지 카드뉴스 생성 완료', pages });

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

    // Step 5: DM 회신 생성
    await savePipelineStatus(env, pipelineId, { step: 5, stepStatus: 'active', label: 'DM 자동 회신 내용 작성 중...' });
    try {
      await handleGenerateDmReply(env, { pages, bookInfo, affiliateLinks, commentKeyword: dmKeyword });
    } catch {}
    await savePipelineStatus(env, pipelineId, { step: 5, stepStatus: 'done', label: 'DM 자동 회신 생성 완료' });

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
  for (const page of ['page1', 'page2', 'page3', 'page4', 'page5']) {
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
  return new Response(buf, {
    headers: { 'Content-Type': 'image/jpeg', 'Cache-Control': 'public, max-age=86400', ...CORS },
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
        else if (url.pathname === '/api/reel-hook') result = await handleReelHook(env, body);
        else if (url.pathname === '/api/generate-reel') result = await handleGenerateReel(env, body);
        else if (url.pathname === '/api/generate-caption') result = await handleGenerateCaption(env, body);
        else if (url.pathname === '/api/validate') result = await handleValidate(env, body);
        else if (url.pathname === '/api/regenerate') result = await handleRegenerate(env, body);
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
