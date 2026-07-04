const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const WORKER_URL = 'https://card-carousel.jtaechul.workers.dev';

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

// ===== 미국 중계기 공용 접근 (지역 라우팅 차단 대책) =====
// 한국발 요청이 홍콩 등 차단 경유지로 나가면 Anthropic이 403("Request not allowed"),
// Gemini가 400("User location is not supported")을 낸다. 둘 다 미국(wnam)에 고정된
// Durable Object(GeminiProxy — 범용 중계기로 확장)를 통해 미국 출구로 재시도한다.
let _relayEnv = null; // fetch 핸들러 진입 시 저장 — 함수 시그니처를 바꾸지 않고 중계기 접근

function relayViaUs(url, init = {}) {
  const stub = _relayEnv.GEMINI_DO.get(_relayEnv.GEMINI_DO.idFromName('us-gemini-proxy'), { locationHint: 'wnam' });
  return stub.fetch('https://gemini-proxy.internal/relay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      url,
      method: init.method || 'GET',
      headers: init.headers || {},
      rawBody: typeof init.body === 'string' ? init.body : null,
    }),
  });
}

// api.anthropic.com 공용 fetch — 403(지역 라우팅 차단)이면 미국 중계기로 즉시 재시도(결정적 우회)
async function anthropicFetch(url, init = {}) {
  const res = await fetch(url, init);
  if (res.status === 403 && _relayEnv?.GEMINI_DO) {
    const t = await res.clone().text().catch(() => '');
    if (/request not allowed/i.test(t)) return relayViaUs(url, init);
  }
  return res;
}

// /v1/models 조회 실패 시(네트워크·레이트리밋) 폴백으로 쓸 알려진 모델 목록
const FALLBACK_MODEL_IDS = [
  'claude-sonnet-4-6', 'claude-opus-4-8', 'claude-haiku-4-5-20251001',
  'claude-opus-4-5', 'claude-sonnet-4-5', 'claude-haiku-4-5',
  'claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022',
];

async function listModelIds(apiKey) {
  const res = await anthropicFetch('https://api.anthropic.com/v1/models?limit=100', {
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
    const res = await anthropicFetch('https://api.anthropic.com/v1/messages', {
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
      res = await anthropicFetch('https://api.anthropic.com/v1/messages', {
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
    res = await anthropicFetch('https://api.anthropic.com/v1/messages', {
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

// 텔레그램에는 "제작 완료 알림 + 확인하러 가기 링크"를 보낸다.
// 링크는 완성된 카드뉴스(훅 카드 이미지 + 캡션)를 그대로 보여주는 결과 페이지(/view?id=)로 연결된다.
async function handleSendTelegram(env, body) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error('TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.');
  }

  const { bookInfo, snapshot } = body;
  const title = bookInfo?.title ? `"${bookInfo.title}"` : '';

  // 완성 스냅샷(이미지·캡션·해시태그)을 KV에 저장하고, 그 결과 페이지 링크를 만든다.
  let link = `${WORKER_URL}/`;
  if (snapshot && Array.isArray(snapshot.images) && snapshot.images.length && env.PENDING_POSTS) {
    const id = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
    const record = {
      title: bookInfo?.title || snapshot.title || '',
      lang: snapshot.lang || 'ko',
      mode: snapshot.mode || 'post',
      caption: String(snapshot.caption || ''),
      hashtags: Array.isArray(snapshot.hashtags) ? snapshot.hashtags.slice(0, 8) : [],
      images: snapshot.images.slice(0, 12),   // JPEG dataURL 목록 (훅 카드 + 원본들)
      videoUrl: snapshot.videoUrl || '',       // 릴스: 원본 영상 URL(있으면)
      createdAt: new Date().toISOString(),
    };
    try {
      await env.PENDING_POSTS.put(`view:${id}`, JSON.stringify(record), { expirationTtl: 2 * 24 * 3600 });
      link = `${WORKER_URL}/view?id=${id}`;
    } catch { /* 저장 실패 시 기본 링크로 폴백 */ }
  }

  const msg = `[카드뉴스 제작 완료]\n\n${title} 카드뉴스(훅 카드 + 캡션)가 완성됐습니다.\n아래 "완성된 카드뉴스 보기"를 눌러 결과를 확인하세요.\n\n${link}`;

  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text: msg,
      reply_markup: {
        inline_keyboard: [[{ text: '완성된 카드뉴스 보기', url: link }]],
      },
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`텔레그램 발송 실패: ${err.description || res.status}`);
  }

  return { success: true, message: '텔레그램으로 제작 완료 알림과 결과 링크를 보냈습니다.', link };
}

// 완성된 카드뉴스 결과 페이지 — 텔레그램 링크(/view?id=)가 여는 읽기 전용 페이지.
// 저장해 둔 스냅샷(훅 카드 이미지 + 원본들 + 캡션 + 해시태그)을 그대로 보여준다.
function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function renderViewPage(rec) {
  const title = escapeHtml(rec.title || '카드뉴스');
  const caption = escapeHtml(rec.caption || '');
  const tags = (rec.hashtags || []).map(escapeHtml).join(' ');
  const captionFull = caption + (tags ? '\n\n' + tags : '');
  const imgs = (rec.images || []).map((src, i) =>
    `<div class="slide"><span class="idx">${i + 1}</span><img src="${escapeHtml(src)}" alt="카드 ${i + 1}"></div>`
  ).join('');
  const video = rec.videoUrl
    ? `<div class="slide"><span class="idx">영상</span><video controls muted playsinline preload="metadata" src="/api/img-proxy?url=${encodeURIComponent(rec.videoUrl)}"></video></div>`
    : '';
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>${title} — 완성된 카드뉴스</title>
<style>
  :root{--bg:#0f1115;--card:#181b22;--line:#262b36;--text:#e8eaed;--sub:#9aa3b2;--accent:#7c3aed;}
  *{box-sizing:border-box;margin:0;padding:0;}
  body{background:var(--bg);color:var(--text);font-family:'Noto Sans KR',system-ui,-apple-system,sans-serif;padding:16px;max-width:560px;margin:0 auto;line-height:1.6;}
  h1{font-size:17px;font-weight:800;margin-bottom:4px;}
  .meta{color:var(--sub);font-size:12px;margin-bottom:16px;}
  .slides{display:flex;flex-direction:column;gap:12px;}
  .slide{position:relative;border-radius:12px;overflow:hidden;background:#000;border:1px solid var(--line);}
  .slide img,.slide video{width:100%;display:block;}
  .idx{position:absolute;top:8px;left:8px;z-index:1;background:rgba(0,0,0,0.55);color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:20px;}
  .cap-box{margin-top:18px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;}
  .cap-box h2{font-size:13px;color:var(--sub);font-weight:700;margin-bottom:8px;}
  .cap-text{white-space:pre-wrap;font-size:14px;}
  .btn{display:block;width:100%;margin-top:12px;padding:12px;border:none;border-radius:10px;background:var(--accent);color:#fff;font-size:14px;font-weight:700;cursor:pointer;}
  .btn.sec{background:transparent;border:1px solid var(--line);color:var(--text);}
  .foot{color:var(--sub);font-size:11px;text-align:center;margin-top:20px;}
  .tip{color:var(--sub);font-size:12px;margin-top:6px;}
</style></head><body>
  <h1>${title}</h1>
  <div class="meta">완성된 카드뉴스 · ${escapeHtml(rec.mode === 'reel' ? '릴스' : '사진 카드뉴스')} · ${escapeHtml((rec.lang || 'ko').toUpperCase())}</div>
  <div class="slides">${imgs}${video}</div>
  <div class="cap-box">
    <h2>캡션 + 해시태그</h2>
    <div class="cap-text" id="cap">${captionFull}</div>
    <button class="btn" id="copyCap">캡션 복사</button>
    <div class="tip">이미지는 길게 눌러 저장하세요. 인스타그램에 이미지 업로드 후 캡션을 붙여넣으면 됩니다.</div>
  </div>
  <div class="foot">이 페이지는 제작 완료 시점의 결과를 담고 있으며 2일 후 만료됩니다.</div>
<script>
  document.getElementById('copyCap').addEventListener('click', async function(){
    try{ await navigator.clipboard.writeText(document.getElementById('cap').innerText); this.textContent='복사됨!'; setTimeout(()=>this.textContent='캡션 복사',1500);}catch(e){ this.textContent='복사 실패 — 길게 눌러 선택하세요'; }
  });
</script>
</body></html>`;
}

// ===== Claude 핸들러 =====

// 페이지 JSON 스키마 (생성·재생성·번역 공용)
// ===== v2.0 정보형 콘텐츠 엔진 =====
// 북캐러셀식 5장 텍스트(공감·교훈형)를 폐기하고, 참고 계정(macroooocosm·animezonein) 공식으로 전환:
//   1장 = 훅 헤드라인 카드(핵심 단어만 강조색) / 나머지 장 = 원본 미디어 그대로 / 정보는 캡션에.
// 흐름: 팩트 수집(Gemini 검색) → 훅+캡션 생성(Claude, 수집된 팩트만 사용) → 팩트 대조 검증.

// 언어별 문체 규칙 — 생성/재생성/검증/번역이 공유
const LANG_STYLE = {
  ko: { name: '한국어', style: '간결한 뉴스형 문어체(~습니다/~합니다). 반말 금지', tagEx: '#흥미로운사실' },
  en: { name: '영어(English)', style: '원어민이 쓴 듯한 자연스러운 정보 계정 톤', tagEx: '#didyouknow' },
  ja: { name: '일본어(日本語)', style: '정중체(です・ます). 기계번역투 금지', tagEx: '#雑学' },
};
function langOf(v) { return ['ko', 'en', 'ja'].includes(v) ? v : 'ko'; }

const CONTENT_JSON_SHAPE = '{"hook":{"headline":"...","accents":["강조단어1","강조단어2"]},"caption":"...","hashtags":["#","#","#","#"]}';

// STEP A: 팩트 수집 — Gemini 구글검색 그라운딩으로 주제의 "확인된 사실"을 먼저 모은다.
// 정보형 콘텐츠의 생명은 정확성 — Claude는 여기서 수집된 사실만 근거로 글을 쓴다(지어내기 차단).
async function handleCollectFacts(env, body) {
  if (!env.GEMINI_API_KEY) {
    throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다. Cloudflare Workers에 등록해주세요.');
  }
  const topic = String(body.topic || '').trim();
  if (!topic) throw new Error('주제(topic)가 필요합니다.');
  const core = String(body.coreMessage || '').trim();

  // 카드에 실제로 쓰는 이미지(들)를 함께 넣어 '이미지 속 그 대상'으로 팩트를 고정한다 (할루시네이션 방지의 핵심)
  const imgUrls = Array.isArray(body.imageDataUrls) ? body.imageDataUrls.slice(0, 2)
    : (body.imageDataUrl ? [body.imageDataUrl] : []);
  const imgParts = [];
  for (const u of imgUrls) {
    const m = String(u).match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
    if (m) imgParts.push({ inline_data: { mime_type: m[1], data: m[2] } });
  }
  const hasImage = imgParts.length > 0;

  const promptWithImage = `첨부한 이미지가 이 카드뉴스에 실제로 실릴 사진입니다. 먼저 구글 검색으로 이미지 속 대상을 정확히 식별한 뒤, "그 대상에 관한 확인된 사실만" 수집하세요.

⚠️ 할루시네이션 절대 금지:
- 이미지와 무관한 다른 인물·다른 사건·다른 종목의 이야기를 절대 섞지 마세요. (예: 이미지가 '피겨스케이팅 선수'인데 '육상 선수 우사인 볼트' 이야기를 넣으면 안 됨)
- 이미지 속 대상이 누구/무엇인지 확실치 않으면, 확실한 범위(종목·대회·장면 유형)로만 사실을 한정하고 subjectConfidence를 낮게 매기세요.
- 구글 검색으로 확인되지 않는 내용은 넣지 마세요. 수치·연도·이름은 검색 근거가 있을 때만.

- subject: 이미지가 무엇/누구를 보여주는지 한 문장으로 식별
- subjectConfidence: high | medium | low (이미지 대상 식별 확신도)
- facts: '이미지 속 그 대상'에 직접 관련된 확인된 사실 5~8개 (각 사실은 이미지 대상과 직접 관련될 것)
- summary: 배경 2~3문장

주제 힌트(참고용 — 이미지와 충돌하면 반드시 이미지를 우선): "${topic}"${core && core !== topic ? `\n참고 메시지: ${core}` : ''}

JSON만: {"subject":"...","subjectConfidence":"high|medium|low","facts":["사실1(수치 포함)","..."],"summary":"..."}`;

  const promptNoImage = `주제: "${topic}"${core && core !== topic ? `\n참고 메시지: ${core}` : ''}\n\n이 주제로 인스타그램 정보형 카드뉴스를 만들려 합니다. 구글 검색을 적극 활용해 "확인된 사실"만 수집하세요.\n\n- 흥미로운 사실 5~8개 (구체적 수치·연도·이름 포함), 검색으로 확인되지 않는 내용 금지\n- summary: 배경 2~3문장\n\nJSON만: {"subject":"${topic}","subjectConfidence":"medium","facts":["..."],"summary":"..."}`;

  const { data, text } = await callGemini(env, {
    contents: [{ parts: [...imgParts, { text: hasImage ? promptWithImage : promptNoImage }] }],
    tools: [{ google_search: {} }],
  });

  let parsed;
  try { parsed = extractJson(text); } catch { parsed = { facts: [], summary: text.trim().slice(0, 500) }; }
  const chunks = data.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
  const sources = chunks.map(c => c.web).filter(Boolean)
    .map(w => ({ title: w.title || '', url: w.uri || '' })).filter(s => s.url).slice(0, 6);
  const facts = (Array.isArray(parsed.facts) ? parsed.facts : []).map(f => String(f).trim()).filter(Boolean).slice(0, 8);
  if (!facts.length) throw new Error('이미지와 관련된, 검색으로 확인된 팩트를 찾지 못했습니다. 주제를 더 구체적으로 하거나 다른 이미지를 사용해보세요.');
  const subjectConfidence = ['high', 'medium', 'low'].includes(parsed.subjectConfidence) ? parsed.subjectConfidence : (hasImage ? 'medium' : 'medium');
  return { success: true, facts, summary: String(parsed.summary || '').trim(), sources, subject: String(parsed.subject || '').trim(), subjectConfidence, imageGrounded: hasImage };
}

// ===== 할루시네이션 게이트: 이미지 ↔ 생성 문구(헤드라인+캡션) 일치 검증 (Gemini 비전) =====
async function handleVerifyImageMatch(env, body) {
  if (!env.GEMINI_API_KEY) throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다.');
  const dataUrl = String(body.imageDataUrl || '');
  const m = dataUrl.match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
  if (!m) throw new Error('imageDataUrl이 필요합니다.');
  const headline = String(body.headline || '').trim();
  const caption = String(body.caption || '').trim();

  const { text } = await callGemini(env, {
    contents: [{
      parts: [
        { inline_data: { mime_type: m[1], data: m[2] } },
        { text: `이 이미지와 아래 카드뉴스 문구가 "같은 대상"에 관한 것인지 엄격히 판정하세요. 이미지에 보이는 인물·사건·종목과 문구가 말하는 인물·사건·종목이 다르면 관련 없음(false)입니다.\n\n[헤드라인] ${headline}\n[캡션] ${caption.slice(0, 800)}\n\n판정:\n- related: 이미지 속 대상과 문구의 대상이 동일/직접 관련이면 true, 다른 인물·다른 사건이면 false\n- imageSubject: 이미지가 실제로 보여주는 대상 한 문장\n- reason: 판정 이유 한 문장\n\nJSON만: {"related":true|false,"imageSubject":"...","reason":"..."}` },
      ],
    }],
  });
  let parsed;
  try { parsed = extractJson(text); } catch { parsed = { related: true, imageSubject: '', reason: '판정 실패(기본 통과)' }; }
  return { success: true, related: parsed.related !== false, imageSubject: String(parsed.imageSubject || '').trim(), reason: String(parsed.reason || '').trim() };
}

// STEP B: 훅 + 캡션 생성 — 수집된 팩트만 근거로. mode: 'post'(사진 카드뉴스) | 'reel'(동영상 릴스)
async function handleGenerate(env, body) {
  const topic = String(body.topic || body.title || '').trim();
  if (!topic) throw new Error('주제(topic)가 필요합니다.');
  const lang = langOf(body.lang);
  const L = LANG_STYLE[lang];
  const mode = body.mode === 'reel' ? 'reel' : 'post';
  const mediaCount = Math.max(1, Math.min(10, parseInt(body.mediaCount) || 1));
  const facts = (Array.isArray(body.facts) ? body.facts : []).slice(0, 8);
  const factsBlock = facts.length ? `\n[확인된 팩트 — 이것만 근거로 사용, 여기 없는 주장 금지]\n${facts.map((f, i) => `${i + 1}. ${f}`).join('\n')}\n${body.factsSummary ? `배경: ${body.factsSummary}\n` : ''}` : '';

  const captionGuide = mode === 'reel'
    ? `[캡션 — 릴스용]\n· 1~2줄 짧은 후킹 문장으로 시작 (스크롤 멈춘 시청자를 붙잡는)\n· 이어서 상세 설명 1~2문단 (팩트 근거, 흥미로운 수치·사실 중심)\n· 마지막 줄: 팔로우 유도 한 문장`
    : `[캡션 — 게시물용, 설명 문단형]\n· 첫 줄: 헤드라인을 평서문으로 풀어쓴 문장\n· 이어서 상세 설명 ${mediaCount >= 3 ? '2~3' : '1~2'}문단 (팩트 근거 — 슬라이드 ${mediaCount}장의 내용을 아우르게)\n· 마지막 줄: 저장 또는 팔로우 유도 한 문장`;

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main', max_tokens: 1200,
    system: `당신은 인스타그램 정보형 콘텐츠(흥미로운 사실·뉴스) 전문 카피라이터입니다. 참고 스타일: "SCIENTISTS HAVE DISCOVERED THE FIRST EVER ANIMAL THAT DOESN'T BREATHE!" 같은 강렬한 사실 기반 헤드라인.\n규칙(절대 위반 금지):\n1. 모든 텍스트를 ${L.name}로 작성. 문체: ${L.style}.\n2. 제공된 팩트에 없는 주장·수치를 지어내지 않는다.\n3. 교훈·위로·설교 금지 — 순수하게 "흥미로운 정보" 전달.\n4. 이모지 금지. 반드시 JSON만 응답.`,
    user: `주제: ${topic}\n${factsBlock}\n다음을 작성하세요:\n\n[hook — 1장에 새길 헤드라인]\n· headline: 스크롤을 멈추게 하는 사실 기반 한 문장 (${lang === 'en' ? '60자' : '35자'} 이내). "세계 최초", 놀라운 수치, 의외의 사실 등 호기심 격차 활용. 공포 조장·낚시성 과장 금지 — 팩트 안에서 가장 강한 것을 고를 것.\n· accents: headline 안에서 강조색을 입힐 핵심 단어(구) 1~2개 — headline에 실제로 포함된 표현만.\n\n${captionGuide}\n\n[hashtags] 주제에 맞는 태그 정확히 4개 (그 언어권에서 실제 쓰이는 것, 예: ${L.tagEx})\n\nJSON:\n${CONTENT_JSON_SHAPE}`,
  });

  const parsed = extractJson(text);
  if (!parsed.hook?.headline) throw new Error('생성 결과 형식 오류');
  return {
    success: true, lang, mode,
    hook: { headline: String(parsed.hook.headline).trim(), accents: (parsed.hook.accents || []).map(a => String(a).trim()).filter(Boolean).slice(0, 2) },
    caption: String(parsed.caption || '').trim(),
    hashtags: (parsed.hashtags || []).slice(0, 5),
  };
}

// 지연 번역 — 훅+캡션을 싼 모델(light)로 목표 언어에 현지화 (언어 탭 첫 클릭 시)
async function handleTranslate(env, body) {
  const target = langOf(body.targetLang);
  const { hook, caption, hashtags } = body;
  if (!hook?.headline) throw new Error('번역할 hook이 필요합니다.');
  const L = LANG_STYLE[target];

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light', max_tokens: 1200,
    system: `당신은 한/영/일 SNS 콘텐츠 현지화 전문가입니다.\n규칙:\n1. 모든 텍스트를 ${L.name}로 옮긴다. 문체: ${L.style}.\n2. 직역 금지 — 그 언어권 정보 계정이 실제 쓰는 자연스러운 표현으로.\n3. accents는 번역된 headline 안에 실제로 포함된 표현으로 다시 지정.\n4. 해시태그는 그 언어권에서 실제 쓰이는 태그로 교체(개수 유지). 이모지 금지.\n5. 입력과 같은 JSON 구조로만 응답.`,
    user: `다음 콘텐츠를 ${L.name}로 현지화하세요.\n\n${JSON.stringify({ hook, caption: caption || '', hashtags: hashtags || [] }, null, 2)}`,
  });

  const out = extractJson(text);
  if (!out.hook?.headline) throw new Error('번역 결과 형식 오류');
  return { success: true, targetLang: target, hook: out.hook, caption: out.caption || '', hashtags: out.hashtags || [] };
}

// STEP C: 검증 — 수집된 팩트와 대조해 "지어낸 정보"를 잡는다 (정보형의 핵심 품질 게이트)
async function handleValidate(env, body) {
  const { hook, caption, facts = [], topic = '' } = body;
  const L = LANG_STYLE[langOf(body.lang)];
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light', max_tokens: 1024,
    system: '당신은 정보형 SNS 콘텐츠 팩트체커 겸 편집장입니다. 반드시 JSON만 응답합니다.',
    user: `주제 "${topic}" ${L.name} 카드뉴스 콘텐츠를 평가하세요.\n\n[검증 근거 — 수집된 팩트]\n${facts.map((f, i) => `${i + 1}. ${f}`).join('\n') || '(없음)'}\n\n[콘텐츠]\n훅 헤드라인: ${hook?.headline || ''}\n캡션:\n${caption || ''}\n\n평가 기준 (100점 만점):\n1. accuracy(팩트 부합): 헤드라인·캡션의 모든 주장·수치가 위 팩트 목록에 근거하는가? 팩트에 없는 주장이 있으면 크게 감점. 0~25\n2. factual(과장 없음): 사실을 왜곡·과장하거나 낚시성으로 부풀리지 않았는가? 0~20\n3. copyright(안전성): 혐오·차별, 의료·법률·투자 단정, 저작권 문제 소지가 없는가? 0~15\n4. engagement(호기심·저장 유도): 훅이 스크롤을 멈추게 하고, 캡션이 끝까지 읽히며 저장하고 싶어지는가? 0~25\n5. quality(문장 품질): 오타·비문 없이 간결한가? 문체(${L.style}) 유지? 0~15\n\nJSON: {"totalScore":85,"scores":{"accuracy":22,"factual":17,"copyright":13,"engagement":21,"quality":12},"feedback":"전체 평가 2~3문장","improvements":["개선점1","개선점2"],"approved":true}\napproved는 totalScore>=70이면 true.`,
  });
  return { success: true, ...extractJson(text) };
}

// 피드백 반영 재생성 (같은 팩트 근거 유지)
async function handleRegenerate(env, body) {
  const { previousHook, previousCaption, feedback, improvements = [], facts = [], topic = '' } = body;
  const lang = langOf(body.lang);
  const L = LANG_STYLE[lang];
  const mode = body.mode === 'reel' ? 'reel' : 'post';
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main', max_tokens: 1200,
    system: `당신은 인스타그램 정보형 콘텐츠 전문 카피라이터입니다. 모든 텍스트를 ${L.name}로 작성(문체: ${L.style}). 제공된 팩트에 없는 주장 금지. 교훈·위로 금지, 순수 정보 전달. 이모지 금지. 반드시 JSON만 응답.`,
    user: `콘텐츠를 피드백에 맞게 개선하세요.\n주제: ${topic}\n\n[확인된 팩트 — 이것만 근거로]\n${facts.map((f, i) => `${i + 1}. ${f}`).join('\n') || '(없음)'}\n\n[이전 버전]\n훅: ${previousHook?.headline || ''}\n캡션:\n${previousCaption || ''}\n\n피드백: ${feedback}\n개선 요청: ${improvements.join(' / ')}\n\n(${mode === 'reel' ? '릴스용 — 캡션은 1~2줄 후킹 시작 + 상세 문단 + 팔로우 유도' : '게시물용 — 캡션은 설명 문단형 + 저장 유도'})\n\nJSON:\n${CONTENT_JSON_SHAPE}`,
  });
  const parsed = extractJson(text);
  if (!parsed.hook?.headline) throw new Error('재생성 결과 형식 오류');
  return {
    success: true, lang, mode,
    hook: { headline: String(parsed.hook.headline).trim(), accents: (parsed.hook.accents || []).map(a => String(a).trim()).filter(Boolean).slice(0, 2) },
    caption: String(parsed.caption || '').trim(),
    hashtags: (parsed.hashtags || []).slice(0, 5),
  };
}

// ===== Gemini 공통 호출 (지역 차단 방어 포함) =====
// "User location is not supported" [400] = 키·결제 문제가 아니라 Cloudflare 경유지(출구 IP)가
// Gemini 미지원 지역(홍콩 등)으로 판정된 것 — book-carousel의 Anthropic 403과 같은 부류의 문제.
// 방어(결정적): 직접 호출이 지역 차단되면 "미국(wnam)에 고정된 Durable Object"를 통해
// 재호출한다. DO는 생성된 지역에서 실행되므로 출구가 항상 미국 → 경유지 운에 의존하지 않음.
// 보조 방어: 워커 내부 재시도 + REGION_BLOCKED 태깅(프론트 자동 재시도) + Smart Placement.
async function callGemini(env, payload, attempt = 0, viaProxy = false) {
  const model = env.GEMINI_MODEL || 'gemini-2.5-flash';
  let res;
  if (viaProxy && env.GEMINI_DO) {
    // 미국 고정 중계기 경유 — idFromName은 같은 객체를 재사용, locationHint는 최초 생성 위치 지정
    const stub = env.GEMINI_DO.get(env.GEMINI_DO.idFromName('us-gemini-proxy'), { locationHint: 'wnam' });
    res = await stub.fetch('https://gemini-proxy.internal/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, payload }),
    });
  } else {
    res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-goog-api-key': env.GEMINI_API_KEY },
      body: JSON.stringify(payload),
    });
  }
  if (!res.ok) {
    const eb = await res.text().catch(() => '');
    const regionBlocked = res.status === 400 && /location is not supported/i.test(eb);
    if (regionBlocked && !viaProxy && env.GEMINI_DO) {
      return callGemini(env, payload, 0, true); // 결정적 우회: 미국 중계기로 전환
    }
    if (regionBlocked && attempt < 1) {
      await new Promise(r => setTimeout(r, 800));
      return callGemini(env, payload, attempt + 1, viaProxy);
    }
    if (regionBlocked) {
      throw new Error('REGION_BLOCKED: 일시적인 해외 경유지 차단 — 요청이 Gemini 미지원 지역(홍콩 등)을 경유했습니다. API 키·결제 문제가 아니며, 잠시 후 재시도해주세요.');
    }
    throw new Error(`Gemini 호출 실패 [${res.status}] ${eb.slice(0, 300)}`);
  }
  const data = await res.json();
  const text = (data.candidates?.[0]?.content?.parts || []).map(p => p.text || '').join('\n');
  return { data, text, model, viaProxy };
}

// 미국(wnam)에 고정 생성되는 API 중계기 — 이 객체 안에서의 fetch는 항상 미국에서 나간다.
// /generate: Gemini 전용 축약형 / /relay: 범용(Anthropic 등 허용 목록 대상만)
export class GeminiProxy {
  constructor(state, env) { this.env = env; }
  async fetch(request) {
    try {
      const path = new URL(request.url).pathname;

      if (path === '/relay') {
        const { url, method = 'GET', headers = {}, rawBody = null } = await request.json();
        // 허용된 백엔드로만 중계 (오픈 프록시화 방지)
        if (!/^https:\/\/(api\.anthropic\.com|generativelanguage\.googleapis\.com)\//.test(String(url))) {
          return new Response(JSON.stringify({ error: { message: '허용되지 않은 중계 대상' } }), { status: 400, headers: { 'Content-Type': 'application/json' } });
        }
        const res = await fetch(url, { method, headers, body: rawBody != null ? rawBody : undefined });
        return new Response(await res.text(), { status: res.status, headers: { 'Content-Type': res.headers.get('content-type') || 'application/json' } });
      }

      const { model, payload } = await request.json();
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': this.env.GEMINI_API_KEY },
        body: JSON.stringify(payload),
      });
      return new Response(await res.text(), { status: res.status, headers: { 'Content-Type': 'application/json' } });
    } catch (e) {
      return new Response(JSON.stringify({ error: { message: '중계기 오류: ' + e.message } }), { status: 500, headers: { 'Content-Type': 'application/json' } });
    }
  }
}

// ===== STEP 0: 원본 추적 (Gemini API — 이미지 인식 + 구글 검색 그라운딩) =====
// 업로드한 이미지가 어디서 온 것인지(작품·작가·플랫폼)와 저작권 위험도를 자동 조사한다.
// ⚠️ 방식의 한계: 구글 렌즈의 "픽셀 단위 완전 일치" 역검색이 아니라, Gemini가 이미지 내용을
// 인식한 뒤 구글 검색 그라운딩으로 출처를 "추정"한다. 정확한 최종 확인은 구글 렌즈 수동
// 검색으로 보완하고, 라이선스 판단 책임은 사용자에게 있다(기획서 1-2 설계 원칙 유지).
async function handleTraceOrigin(env, body) {
  if (!env.GEMINI_API_KEY) {
    throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다. Cloudflare Workers에 등록해주세요. (wrangler secret put GEMINI_API_KEY)');
  }
  const dataUrl = String(body.imageDataUrl || '');
  const m = dataUrl.match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
  if (!m) throw new Error('imageDataUrl(base64 데이터 URL 형식의 이미지)이 필요합니다.');
  const mime = m[1], b64 = m[2];

  const { data, text, model } = await callGemini(env, {
    contents: [{
      parts: [
        { inline_data: { mime_type: mime, data: b64 } },
        { text: '이 이미지의 원본 출처를 추적하려 합니다. 구글 검색을 적극 활용해 아래를 조사하고, 마지막에 반드시 JSON 하나로 정리해 답하세요.\n\n※ 목표: 이 이미지에 담긴 사건·인물·장면의 \'가공되지 않은 원본 사진\'이 있는 페이지를 찾는 것입니다. 특히 뉴스 기사·통신사·사진작가·공식 계정처럼 자막이나 편집이 없는 원본 사진이 실려 있을 만한 페이지의 URL을 originCandidates에 우선 담아주세요. (남이 자막을 박아 넣은 카드뉴스·짤 게시물보다, 글자 없는 원본이 있는 페이지를 앞에 두세요.)\n\n조사 항목:\n1. 이미지에 무엇이 있는가 — 작품명(드라마·영화·애니·게임 등)·인물·장소·사건·워터마크·로고·서명·화면 속 텍스트 같은 출처 단서 포함\n2. 이 이미지에 이미 삽입된 자막/캡션 글자가 있는가 (hasOverlayText: 사진 위에 겹쳐 넣은 큰 자막·제목·밈 문구가 있으면 true, 없으면 false)\n3. 이 사건·장면의 원본 사진이 있을 법한 출처 (뉴스·통신사·작가·공식 플랫폼)\n4. 저작권·라이선스 위험도 판정:\n   - high: 상업 콘텐츠(방송·영화·웹툰·유료 스톡 등)로 보여 무단 재가공 위험이 큼\n   - medium: 출처가 불명확하거나 이용 조건 확인 필요\n   - low: 퍼블릭 도메인·CC0·자유 이용 가능성이 높음\n   - unknown: 판단 불가\n\nJSON 형식(이 형식만, 다른 텍스트로 끝내지 말 것):\n{"summary":"이미지 설명 한두 문장","clues":["출처 단서1","단서2"],"hasOverlayText":true,"originGuess":"추정 원본 출처 설명 한두 문장","originCandidates":[{"name":"출처명","url":"https://..."}],"licenseRisk":"high|medium|low|unknown","licenseNote":"위험도 판단 이유 한두 문장"}' },
      ],
    }],
    tools: [{ google_search: {} }],
  });
  let analysis = null;
  try { analysis = extractJson(text); } catch { analysis = { summary: text.trim().slice(0, 1000) || '분석 결과를 읽지 못했습니다.' }; }

  // 그라운딩 메타데이터 — Gemini가 실제로 참고한 검색 결과 URL(추정 출처의 근거)
  const chunks = data.candidates?.[0]?.groundingMetadata?.groundingChunks || [];
  const sources = chunks
    .map(c => c.web).filter(Boolean)
    .map(w => ({ title: w.title || '', url: w.uri || '' }))
    .filter(s => s.url)
    .slice(0, 8);

  return { success: true, analysis, sources, model };
}

// ===== STEP 0 확장: 출처 페이지에서 원본 후보 이미지 추출 (기능 1-A) =====
// 원본 추적이 찾은 출처 페이지들을 열어 대표 이미지(og:image 등 — 보통 고화질 원본)를 뽑는다.
// 사용자가 후보를 클릭하면 업로드 이미지가 원본으로 교체된다(교체 여부는 사용자 선택).
// 명백한 잡동사니 이미지(아이콘·로고·아바타·스프라이트·추적픽셀·초소형)를 걸러낸다
const JUNK_IMG_RE = /(sprite|icon|logo|avatar|favicon|emoji|badge|button|pixel|spacer|blank|placeholder|1x1|loading|advert|banner_ad|doubleclick|analytics)/i;
function looksLikeRealImage(u) {
  if (!/^https?:\/\//i.test(u)) return false;
  if (/\.svg(\?|$)/i.test(u)) return false;                 // 벡터 아이콘 제외
  if (JUNK_IMG_RE.test(u)) return false;                    // 잡동사니 경로 제외
  if (/(^|[^0-9])(16|24|32|48|50|64|80)x\1?/i.test(u)) { /* noop */ } // (완화)
  if (/[_\-\/](16|24|32|48|50|64|75|100)x(16|24|32|48|50|64|75|100)([._\-]|$)/i.test(u)) return false; // 초소형 썸네일
  return /\.(jpe?g|png|webp)(\?|$)/i.test(u) || /\/(i|preview)\.redd\.it\//i.test(u) || /(fbcdn|cdninstagram|pbs\.twimg|images?\.|img\.|media\.|static\.)/i.test(u);
}

async function handleFetchOriginImages(env, body) {
  // '가공되지 않은 원본'을 더 다양하게 확보: 출처 8페이지 훑기 + og/twitter 메타 + 본문 <img> 태그까지 추출
  const urls = (Array.isArray(body.urls) ? body.urls : [])
    .filter(u => /^https?:\/\//i.test(String(u))).slice(0, 8);
  if (!urls.length) throw new Error('출처 페이지 URL(urls)이 필요합니다.');

  const found = [];
  await Promise.all(urls.map(async (pageUrl) => {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      const res = await fetch(pageUrl, {
        signal: ctrl.signal, redirect: 'follow',
        headers: { 'User-Agent': 'Mozilla/5.0 (compatible; card-carousel/1.0)' },
      });
      clearTimeout(timer);
      if (!res.ok) return;
      const ct = res.headers.get('content-type') || '';
      if (ct.startsWith('image/')) { found.push({ type: 'image', pageUrl, mediaUrl: pageUrl }); return; } // 링크가 이미지 자체
      if (!ct.includes('html')) return;
      const html = (await res.text()).slice(0, 800000);
      const imgs = new Set(), vids = new Set();
      // 1) 대표 이미지 메타 (보통 고화질 원본) — 앞쪽에 오게
      for (const re of [
        /<meta[^>]+property=["']og:image(?::secure_url)?["'][^>]*content=["']([^"']+)["']/gi,
        /<meta[^>]+content=["']([^"']+)["'][^>]*property=["']og:image(?::secure_url)?["']/gi,
        /<meta[^>]+name=["']twitter:image(?::src)?["'][^>]*content=["']([^"']+)["']/gi,
        /<link[^>]+rel=["']image_src["'][^>]*href=["']([^"']+)["']/gi,
      ]) {
        let m;
        while ((m = re.exec(html)) && imgs.size < 6) imgs.add(m[1]);
      }
      // 2) 본문 <img> 태그 — 관련 이미지를 더 다양하게 (src / data-src / srcset의 마지막=최대 후보)
      let im;
      const imgTagRe = /<img\b[^>]*>/gi;
      while ((im = imgTagRe.exec(html)) && imgs.size < 24) {
        const tag = im[0];
        const src = (tag.match(/\ssrc=["']([^"']+)["']/i) || [])[1]
          || (tag.match(/\sdata-src=["']([^"']+)["']/i) || [])[1];
        const srcset = (tag.match(/\ssrcset=["']([^"']+)["']/i) || [])[1];
        const fromSet = srcset ? srcset.split(',').pop().trim().split(/\s+/)[0] : '';
        for (const cand of [fromSet, src]) {
          if (cand && looksLikeRealImage(cand)) { imgs.add(cand); break; }
        }
      }
      // 3) 영상 후보(og:video 등) — 릴스 모드 소재
      for (const re of [
        /<meta[^>]+property=["']og:video(?::secure_url|:url)?["'][^>]*content=["']([^"']+)["']/gi,
        /<meta[^>]+content=["']([^"']+)["'][^>]*property=["']og:video(?::secure_url|:url)?["']/gi,
        /<meta[^>]+name=["']twitter:player:stream["'][^>]*content=["']([^"']+)["']/gi,
      ]) {
        let m;
        while ((m = re.exec(html)) && vids.size < 2) vids.add(m[1]);
      }
      for (const u of imgs) {
        try { const abs = new URL(u.replace(/&amp;/g, '&'), pageUrl).href; if (looksLikeRealImage(abs) || /^https?:\/\/[^ ]+og:image/.test(u)) found.push({ type: 'image', pageUrl, mediaUrl: abs }); } catch {}
      }
      for (const u of vids) { try { found.push({ type: 'video', pageUrl, mediaUrl: new URL(u.replace(/&amp;/g, '&'), pageUrl).href }); } catch {} }
    } catch {} // 페이지 하나 실패해도 나머지 계속
  }));

  // 중복 제거 + 최대 24개 (프론트에서 글자 없는 원본만 노출)
  const seen = new Set(); const media = [];
  for (const r of found) {
    if (!seen.has(r.mediaUrl)) { seen.add(r.mediaUrl); media.push(r); if (media.length >= 24) break; }
  }
  return { success: true, media };
}

// ===== A단계: Reddit 인기글 자동 추천 (공식 공개 JSON) =====
// 인기 서브레딧의 이미지 게시물을 가져와 카드뉴스 소재 후보로 제안한다.
// 선택하면 '검색용 시드'가 되어 기존 원본추적→글자없는 원본 선별 흐름을 그대로 탄다.
const REDDIT_CATS = {
  popular:   ['pics', 'interestingasfuck', 'Damnthatsinteresting'],
  facts:     ['todayilearned', 'Damnthatsinteresting', 'interestingasfuck'],
  space:     ['space', 'spaceporn', 'astrophotography'],
  nature:    ['NatureIsFuckingLit', 'EarthPorn', 'aww'],
  history:   ['HistoryPorn', 'history', 'OldSchoolCool'],
};
const REDDIT_UA = 'web:card-carousel:v2.5 (card carousel maker)';

// Reddit 앱 전용 OAuth 토큰 (client_credentials) — 키가 있을 때만. KV에 캐시.
async function redditToken(env) {
  if (!env.REDDIT_CLIENT_ID || !env.REDDIT_CLIENT_SECRET) return null;
  if (env.PENDING_POSTS) {
    const cached = await env.PENDING_POSTS.get('reddit_token').catch(() => null);
    if (cached) return cached;
  }
  const auth = btoa(`${env.REDDIT_CLIENT_ID}:${env.REDDIT_CLIENT_SECRET}`);
  const res = await fetch('https://www.reddit.com/api/v1/access_token', {
    method: 'POST',
    headers: { 'Authorization': `Basic ${auth}`, 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': REDDIT_UA },
    body: 'grant_type=client_credentials',
  }).catch(() => null);
  if (!res || !res.ok) return null;
  const j = await res.json().catch(() => null);
  const tok = j?.access_token;
  if (tok && env.PENDING_POSTS) {
    await env.PENDING_POSTS.put('reddit_token', tok, { expirationTtl: Math.max(300, (j.expires_in || 3600) - 120) }).catch(() => {});
  }
  return tok || null;
}

// Reddit children → 이미지 게시물 목록 (i.redd.it 직링 우선, preview 보조)
function parseRedditChildren(children) {
  const posts = [];
  for (const c of (children || [])) {
    const p = c?.data; if (!p) continue;
    if (p.over_18 || p.stickied) continue;
    const direct = p.url_overridden_by_dest || p.url || '';
    let img = '';
    if (/i\.redd\.it/i.test(direct) || /\.(jpe?g|png|webp)(\?|$)/i.test(direct)) img = direct; // 직링(핫링크 잘 됨) 우선
    if (!img && p.preview?.images?.[0]?.source?.url) img = String(p.preview.images[0].source.url).replace(/&amp;/g, '&');
    if (!img) continue;
    posts.push({
      title: String(p.title || '').slice(0, 200),
      subreddit: p.subreddit || '',
      ups: p.ups || 0,
      permalink: p.permalink ? 'https://www.reddit.com' + p.permalink : '',
      imageUrl: img,
    });
    if (posts.length >= 24) break;
  }
  return posts;
}

// 서버측 Reddit 인기글 — 브라우저 JSONP가 막혔을 때의 폴백.
// 데이터센터 IP는 www.reddit.com/.json 이 403나므로, 앱 키가 있으면 공식 OAuth(oauth.reddit.com)로 우회한다.
async function handleRedditTrending(env, body) {
  const cat = String(body.category || 'popular');
  const subs = REDDIT_CATS[cat] || REDDIT_CATS.popular;
  const multi = subs.join('+');

  const token = await redditToken(env);
  const base = token ? 'https://oauth.reddit.com' : 'https://www.reddit.com';
  const url = `${base}/r/${multi}/hot${token ? '' : '.json'}?limit=40&raw_json=1`;
  const headers = { 'User-Agent': REDDIT_UA, 'Accept': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 9000);
    res = await fetch(url, { signal: ctrl.signal, redirect: 'follow', headers });
    clearTimeout(timer);
  } catch (e) {
    throw new Error('Reddit 연결 실패: ' + e.message);
  }
  if (res.status === 403 || res.status === 429) {
    throw new Error(token
      ? `Reddit 응답 오류 [${res.status}] — 잠시 후 다시 시도해주세요.`
      : `REDDIT_BLOCKED: 서버에서 Reddit 접근이 차단됐습니다(${res.status}). 브라우저에서 직접 불러오기가 안 되면, Reddit 앱 키(REDDIT_CLIENT_ID/SECRET) 등록이 필요합니다.`);
  }
  if (!res.ok) throw new Error(`Reddit 응답 오류 [${res.status}] — 잠시 후 다시 시도해주세요.`);
  const data = await res.json().catch(() => null);
  return { success: true, category: cat, subs, posts: parseRedditChildren(data?.data?.children || []), via: token ? 'oauth' : 'public' };
}

// ===== A단계-2: 캡션 문단 ↔ 원본 이미지 자동 매칭 (Gemini 비전) =====
// 2장 이상일 때, 캡션 문단 흐름에 가장 잘 맞도록 2페이지 이후 원본들의 순서를 재배치한다.
async function handleMatchImages(env, body) {
  if (!env.GEMINI_API_KEY) throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다.');
  const paragraphs = (Array.isArray(body.paragraphs) ? body.paragraphs : []).map(s => String(s || '').trim()).filter(Boolean).slice(0, 12);
  const images = (Array.isArray(body.images) ? body.images : []).slice(0, 12);
  if (images.length < 2 || !paragraphs.length) return { success: true, order: images.map((_, i) => i) };

  const parts = [];
  images.forEach((u) => {
    const m = String(u).match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
    if (m) parts.push({ inline_data: { mime_type: m[1], data: m[2] } });
  });
  parts.push({ text: `카드뉴스 2페이지부터 각 문단에 어울리는 사진을 배치하려 합니다.\n\n[사진들] 위에 보낸 순서대로 0번, 1번, 2번 ... 입니다 (총 ${images.length}장).\n[문단들]\n${paragraphs.map((p, i) => `${i}) ${p}`).join('\n')}\n\n각 문단에 가장 잘 어울리는 사진의 번호를 정하되, 한 사진은 한 번만 쓰세요(가능하면). 사진 수와 같은 길이의 배열로, i번째 값이 '표시할 사진 번호'가 되도록 JSON 배열만 답하세요. 예: [2,0,1]` });

  const { text } = await callGemini(env, { contents: [{ parts }] });
  let order = [];
  try {
    const parsed = extractJson(text);
    if (Array.isArray(parsed)) order = parsed.map(n => parseInt(n, 10)).filter(n => Number.isInteger(n) && n >= 0 && n < images.length);
  } catch {}
  // 유효성: 중복/누락 보정 → 없으면 원래 순서
  const seen = new Set(); const clean = [];
  for (const i of order) { if (!seen.has(i)) { seen.add(i); clean.push(i); } }
  for (let i = 0; i < images.length; i++) if (!seen.has(i)) clean.push(i);
  return { success: true, order: clean.length === images.length ? clean : images.map((_, i) => i) };
}

// ===== STEP 0 확장: 후보 이미지의 '글자 삽입 여부' 판별 (기능 1-B, 핵심) =====
// 역검색으로 나온 후보 중엔 남이 이미 자막·캡션을 박아 넣은 '가공본'이 섞여 있다.
// 첫 장에만 우리 훅 문구를 얹으려면 배경은 반드시 '글자 없는 원본'이어야 하므로,
// Gemini 비전으로 후보들을 한 번에 분류해 가공본을 걸러낸다(브라우저는 이 결과로 원본만 노출).
async function handleFilterCleanImages(env, body) {
  if (!env.GEMINI_API_KEY) {
    throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다. Cloudflare Workers에 등록해주세요.');
  }
  const images = Array.isArray(body.images) ? body.images.slice(0, 24) : [];
  if (!images.length) throw new Error('분류할 이미지(images)가 필요합니다.');

  // 기준(업로드) 이미지 — 있으면 '같은 대상인지(related)'까지 판정해 무관한 후보를 걸러낸다
  const refMatch = String(body.refImage || '').match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
  const hasRef = !!refMatch;

  const parts = [];
  if (hasRef) parts.push({ inline_data: { mime_type: refMatch[1], data: refMatch[2] } });
  images.forEach((u) => {
    const m = String(u).match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
    if (m) parts.push({ inline_data: { mime_type: m[1], data: m[2] } });
  });

  const promptRef = `첫 번째 이미지는 '기준 이미지'(사용자가 올린, 원본을 찾으려는 대상)입니다. 이어지는 ${images.length}개 후보 이미지를 보낸 순서대로 각각 판정하세요.\n\n- related: 후보가 기준 이미지와 '같은 대상/같은 장소/같은 사건/같은 종류의 장면'을 보여주면 true. 전혀 다른 사물·인물·음식·차트·로고·다른 기사 사진이면 false. (예: 기준이 '사막의 원자로 시설 항공사진'인데 음식·인물·주식차트·커피 사진이면 반드시 false)\n- hasText: 사진 위에 삽입된 자막·캡션·큰 제목·워터마크·밈 문구가 있으면 true, 없으면 false. (간판·옷 로고처럼 현장에 원래 있던 글자는 false)\n\n반드시 후보 개수(${images.length}개)와 같은 길이의 JSON 배열로만: [{"related":true,"hasText":false,"note":"기준과 같은 시설 항공사진"}, ...]`;
  const promptNoRef = `위 이미지들을 보낸 순서대로 각각 판정하세요. '가공되지 않은 원본 사진'인지, '누군가 글자(자막·캡션·워터마크)를 박아 넣은 가공본'인지.\n- hasText=true: 삽입 자막/캡션/워터마크 있음\n- hasText=false: 삽입 글자 없는 깨끗한 원본\n\n${images.length}개 길이 JSON 배열만: [{"related":true,"hasText":false},...]`;

  parts.push({ text: hasRef ? promptRef : promptNoRef });

  const { text } = await callGemini(env, { contents: [{ parts }] });
  let arr = [];
  try {
    const parsed = extractJson(text);
    arr = Array.isArray(parsed) ? parsed : (Array.isArray(parsed.results) ? parsed.results : []);
  } catch { arr = []; }
  const results = images.map((_, i) => {
    const r = arr[i] || {};
    // 기준 이미지가 있으면 related 판정 사용(누락 시 무관으로 간주해 노이즈 차단), 없으면 모두 관련으로 취급
    const related = hasRef ? (r.related === true) : true;
    return { hasText: r.hasText === true, related, note: String(r.note || '').slice(0, 80) };
  });
  return { success: true, results, usedRef: hasRef };
}

// ===== STEP 1 모드 B: 주제 AI 자동 추출 (Gemini vision — 기획서 Phase 3) =====
// 업로드한 이미지(최대 3장)를 보고 카드뉴스 주제 1개 + 핵심 메시지 후보 3개를 제안한다.
// 사용자가 제안을 선택·수정한 뒤 생성 버튼을 누르는 흐름(자동 확정 아님).
async function handleSuggestTopic(env, body) {
  if (!env.GEMINI_API_KEY) {
    throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다. Cloudflare Workers에 등록해주세요. (wrangler secret put GEMINI_API_KEY)');
  }
  const urls = Array.isArray(body.imageDataUrls) ? body.imageDataUrls.slice(0, 3)
    : (body.imageDataUrl ? [body.imageDataUrl] : []);
  if (!urls.length) throw new Error('이미지(imageDataUrls)가 필요합니다.');

  const parts = [];
  for (const u of urls) {
    const m = String(u).match(/^data:(image\/[a-z0-9+.-]+);base64,([A-Za-z0-9+/=]+)$/i);
    if (!m) throw new Error('base64 데이터 URL 형식의 이미지가 필요합니다.');
    parts.push({ inline_data: { mime_type: m[1], data: m[2] } });
  }
  parts.push({ text: '이 이미지(들)로 인스타그램 카드뉴스(캐러셀)를 만들려 합니다. 이미지의 분위기·소재에 어울리는 카드뉴스 주제를 제안하세요.\n\n- topic: 카드뉴스 주제 1개 (한국어, 25자 이내 — 구체적이고 클릭하고 싶은 주제)\n- coreMessages: 그 주제로 전할 수 있는 핵심 메시지 후보 3개 (한국어, 각 1문장, 서로 다른 각도)\n\n규칙: 이미지와 동떨어진 주제 금지. 공포·자극 조장 금지. 이모지 금지.\nJSON만 응답: {"topic":"...","coreMessages":["...","...","..."]}' });

  const { text, model } = await callGemini(env, { contents: [{ parts }] });
  const parsed = extractJson(text);
  return {
    success: true,
    topic: String(parsed.topic || '').trim(),
    coreMessages: (Array.isArray(parsed.coreMessages) ? parsed.coreMessages : []).map(s => String(s).trim()).filter(Boolean).slice(0, 3),
    model,
  };
}

// ===== 인스타그램 캐럿셀 게시 (텔레그램 승인 후 게시 액션) =====
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
        `인스타그램 게시 완료!\n미디어 ID: ${result.mediaId}\n\n주제: ${ps.bookInfo?.title || ''}`).catch(() => {});
    } catch (err) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
        `인스타그램 게시 실패: ${err.message}\n\n웹에서 직접 게시해주세요: ${WORKER_URL}/`).catch(() => {});
    }
  } else if (cbData === 'cancel') {
    await answerCallback('취소됐습니다.');
    if (env.PENDING_POSTS) await env.PENDING_POSTS.delete('latest').catch(() => {});
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, '게시가 취소됐습니다.').catch(() => {});
  } else if (cbData === 'modify') {
    await answerCallback('웹에서 수정해주세요', true);
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
      `웹에서 수정 후 다시 발송해주세요:\n${WORKER_URL}/`).catch(() => {});
  } else {
    await answerCallback('');
  }

  return { ok: true };
}

// ===== 텔레그램 Webhook URL 등록 (최초 1회 실행) =====
async function handleSetupWebhook(env) {
  if (!env.TELEGRAM_BOT_TOKEN) throw new Error('TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.');
  const webhookUrl = `${WORKER_URL}/api/telegram-webhook`;
  const res = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: webhookUrl }),
  });
  const data = await res.json();
  return { success: true, webhookUrl, ...data };
}


// ===== 메인 라우터 =====
export default {
  async fetch(request, env, ctx) {
    _relayEnv = env; // 미국 중계기 접근용 — anthropicFetch가 지역 차단(403) 시 사용
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    if (url.pathname.startsWith('/api/')) {
      // 원본 후보 이미지 프록시 — 외부 이미지를 우리 도메인으로 받아 캔버스 CORS 오염 없이 사용
      if (url.pathname === '/api/img-proxy') {
        const src = url.searchParams.get('url') || '';
        if (!/^https?:\/\//i.test(src)) return new Response('bad url', { status: 400, headers: CORS });
        try {
          // Reddit 계열 이미지(preview.redd.it 등)는 Referer가 없으면 403 → reddit referer 부여
          const ph = { 'User-Agent': 'Mozilla/5.0 (compatible; card-carousel/1.0)' };
          if (/redd\.it|redditmedia\.com|reddit\.com/i.test(src)) ph['Referer'] = 'https://www.reddit.com/';
          const r = await fetch(src, { redirect: 'follow', headers: ph });
          const ct = r.headers.get('content-type') || '';
          // v2.0: 영상도 허용, 버퍼링 대신 스트리밍 전달(대용량 대응)
          if (!r.ok || !(ct.startsWith('image/') || ct.startsWith('video/'))) {
            return new Response('not media', { status: 415, headers: CORS });
          }
          return new Response(r.body, {
            headers: { 'Content-Type': ct, 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'public, max-age=86400' },
          });
        } catch {
          return new Response('fetch error', { status: 502, headers: CORS });
        }
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
            const r = await anthropicFetch('https://api.anthropic.com/v1/models?limit=100', {
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
        else if (url.pathname === '/api/generate') result = await handleGenerate(env, body);
        else if (url.pathname === '/api/validate') result = await handleValidate(env, body);
        else if (url.pathname === '/api/regenerate') result = await handleRegenerate(env, body);
        else if (url.pathname === '/api/send-telegram') result = await handleSendTelegram(env, body);
        else if (url.pathname === '/api/send-telegram-image') result = await handleSendTelegramImage(env, body);
        else if (url.pathname === '/api/post-instagram') result = await handlePostInstagram(env, body);
        else if (url.pathname === '/api/telegram-webhook') result = await handleTelegramWebhook(env, body);
        else if (url.pathname === '/api/setup-webhook') result = await handleSetupWebhook(env);
        else if (url.pathname === '/api/trace-origin') result = await handleTraceOrigin(env, body);
        else if (url.pathname === '/api/suggest-topic') result = await handleSuggestTopic(env, body);
        else if (url.pathname === '/api/translate') result = await handleTranslate(env, body);
        else if (url.pathname === '/api/collect-facts') result = await handleCollectFacts(env, body);
        else if (url.pathname === '/api/fetch-origin-images') result = await handleFetchOriginImages(env, body);
        else if (url.pathname === '/api/filter-clean') result = await handleFilterCleanImages(env, body);
        else if (url.pathname === '/api/reddit-trending') result = await handleRedditTrending(env, body);
        else if (url.pathname === '/api/match-images') result = await handleMatchImages(env, body);
        else if (url.pathname === '/api/verify-image-match') result = await handleVerifyImageMatch(env, body);
        else if (url.pathname === '/api/gemini-ping') {
          // 진단용: Gemini·Claude 연결 상태 + 미국 중계기 경유 여부 확인 (브라우저에서 열면 JSON 표시)
          if (!env.GEMINI_API_KEY) throw new Error('GEMINI_API_KEY 시크릿이 설정되지 않았습니다.');
          const r = await callGemini(env, { contents: [{ parts: [{ text: 'pong 이라는 한 단어로만 답하세요.' }] }] });
          let claudeOk = null;
          if (env.ANTHROPIC_API_KEY) {
            const st = await probeModel(env.ANTHROPIC_API_KEY, HARDCODED_FALLBACK_LIGHT);
            claudeOk = st === 200; // 403이었어도 anthropicFetch가 미국 중계기로 우회한 결과
          }
          result = { success: true, ok: /pong/i.test(r.text), claudeOk, reply: r.text.trim().slice(0, 40), viaUsProxy: !!r.viaProxy, model: r.model };
        }
        else if (url.pathname === '/api/usage') {
          // 오늘(KST) Claude API 사용량 — 크레딧 소진 감시용
          const used = await getApiUsage(env);
          result = { success: true, day: _kstDay(), used, softCap: DAILY_SOFT_CAP, hardCap: DAILY_HARD_CAP, savingMode: used > DAILY_SOFT_CAP, blocked: used > DAILY_HARD_CAP };
        }
        else if (url.pathname === '/api/reset-model-cache') {
          await clearModelCache(env);
          const m = await resolveModels(env.ANTHROPIC_API_KEY, env);
          result = { success: true, model: m.main, light: m.light, source: m.source };
        }
        else return json({ error: '없는 경로입니다.' }, 404);

        return json(result);
      } catch (err) {
        return json({ error: err.message }, 500);
      }
    }

    // 완성된 카드뉴스 결과 페이지 (텔레그램 링크가 여는 읽기 전용 페이지)
    if (request.method === 'GET' && url.pathname === '/view') {
      const id = url.searchParams.get('id') || '';
      const notFound = (m) => new Response(
        `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><body style="font-family:sans-serif;background:#0f1115;color:#e8eaed;padding:24px;text-align:center;"><h2>${m}</h2><p style="color:#9aa3b2">제작 페이지에서 다시 생성하고 발송해주세요.</p><p><a href="/" style="color:#7c3aed">제작 페이지로</a></p></body>`,
        { status: 404, headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS } });
      if (!/^[a-z0-9]{6,32}$/i.test(id) || !env.PENDING_POSTS) return notFound('결과를 찾을 수 없습니다');
      let rec = null;
      try { rec = await env.PENDING_POSTS.get(`view:${id}`, 'json'); } catch {}
      if (!rec) return notFound('결과가 만료되었거나 존재하지 않습니다');
      return new Response(renderViewPage(rec), { headers: { 'Content-Type': 'text/html; charset=utf-8', ...CORS } });
    }

    return env.ASSETS.fetch(request);
  },
};
