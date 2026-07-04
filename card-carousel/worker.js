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
  const msg = `[카드뉴스 제작 완료]\n\n${title} 카드뉴스(5장 + 캡션)가 완성됐습니다.\n아래 "확인하러 가기"를 눌러 결과를 보고, 게시 여부를 결정해주세요.\n\n${link}`;

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

// 페이지 JSON 스키마 (생성·재생성·번역 공용)
const PAGES_JSON_SHAPE = '{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}';

// 언어별 문체·분량 규칙 — 생성/재생성/캡션/릴스/번역이 공유
const LANG_STYLE = {
  ko: { name: '한국어', style: '존댓말·문어체(~습니다/~합니다/~네요). 반말 절대 금지', hl1: 40, hl: 18, line: 40, ex5: '"다시 꺼내보고 싶다면 저장해두세요"', tagEx: '#아침루틴' },
  en: { name: '영어(English)', style: '원어민이 쓴 듯한 자연스러운 SNS 톤', hl1: 70, hl: 30, line: 60, ex5: '"Save this for the mornings you need it"', tagEx: '#morningroutine' },
  ja: { name: '일본어(日本語)', style: '정중체(です・ます). 기계번역투 금지', hl1: 40, hl: 18, line: 40, ex5: '"また読み返したくなったら保存してください"', tagEx: '#朝活' },
};
function langOf(v) { return ['ko', 'en', 'ja'].includes(v) ? v : 'ko'; }

async function handleGenerate(env, body) {
  // v1.2: 선택한 언어 "하나"로만 생성 — 다른 언어는 탭 전환 시 /api/translate(싼 모델)로 지연 번역.
  // (3개 언어 동시 생성 대비: 안 쓰는 언어의 비싼 main 모델 토큰 낭비 제거)
  const topic = String(body.topic || body.title || '').trim();
  const coreMessage = String(body.coreMessage || '').trim();
  if (!topic && !coreMessage) throw new Error('주제(topic) 또는 핵심 메시지(coreMessage)가 필요합니다.');
  const lang = langOf(body.lang);
  const L = LANG_STYLE[lang];

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main', max_tokens: 1400,
    system: `당신은 인스타그램 카드뉴스(캐러셀) 전문 카피라이터입니다.\n핵심 규칙(절대 위반 금지):\n1. 모든 텍스트를 ${L.name}로 작성한다. 문체: ${L.style}.\n2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.\n3. 과장·공포 조장 금지. 확실하지 않은 통계·수치·연구를 지어내지 않는다.\n4. 독자가 "저장해두고 싶다", "친구에게 보내주고 싶다"고 느낄 공감과 실용성을 담는다. 이모지 금지.\n반드시 JSON만 응답한다.`,
    user: `다음 주제로 5페이지 인스타그램 카드뉴스를 ${L.name}로 작성하세요.\n\n주제: ${topic || coreMessage}\n${topic && coreMessage ? `핵심 메시지: ${coreMessage}\n` : ''}${body.targetAudience ? `대상 독자: ${body.targetAudience}\n` : ''}\n페이지 가이드 (길이 규칙 엄수):\n1페이지(후킹 — 헤드라인만): 스크롤을 멈추게 하는 단 하나의 문장으로 카드 전체를 채운다.\n  - headline: ${L.hl1}자 이내 완전한 문장. 독자가 "내 얘기다"라고 느낄 구체적 순간·감정, 또는 궁금증.\n    규칙: 공포·경고 톤 금지. "대부분의 사람들이" 같은 상투 패턴 금지. 주어 없는 단어 조각 금지.\n2페이지(공감·문제): 독자가 겪는 상황을 구체적 장면으로.\n  - headline: ${L.hl}자 이내 / body: 3~4줄, 한 줄 ${L.line}자 이내.\n3페이지(이유·원리): 왜 그런지 쉽게 풀어 설명.\n  - headline: ${L.hl}자 이내 / body: 3~4줄, 한 줄 ${L.line}자 이내.\n4페이지(방법·실마리): 오늘부터 해볼 수 있는 구체적 방향. 마지막 줄은 여운 있게.\n  - headline: ${L.hl}자 이내 / body: 3~4줄, 한 줄 ${L.line}자 이내.\n5페이지(마무리 CTA):\n  - cta: 전체를 한 문장으로 정리하는 마무리 — 독자 가슴에 남는 한 문장.\n  - linkText: 저장·팔로우를 자연스럽게 유도하는 한 줄 (예: ${L.ex5}).\n\nJSON:\n${PAGES_JSON_SHAPE}`
  });

  const pages = extractJson(text);
  if (!pages.page1) throw new Error('생성 결과 형식 오류');
  return { success: true, pages, lang };
}

// v1.2: 지연 번역 — 이미 생성된 콘텐츠(카드 5장 + 있으면 캡션·릴스)를 싼 모델(light)로
// 목표 언어에 현지화한다. 새 창작이 아니라 번역이므로 main 모델이 필요 없다(비용 절감 핵심).
async function handleTranslate(env, body) {
  const target = langOf(body.targetLang);
  const { pages, caption, hashtags, reelCaption, reelHashtags, reel } = body;
  if (!pages?.page1) throw new Error('번역할 pages가 필요합니다.');
  const L = LANG_STYLE[target];
  const input = { pages };
  if (caption) { input.caption = caption; input.hashtags = hashtags || []; }
  if (reelCaption) { input.reelCaption = reelCaption; input.reelHashtags = reelHashtags || []; }
  if (reel?.s1) input.reel = reel;

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light', max_tokens: 2400,
    system: `당신은 한/영/일 SNS 콘텐츠 현지화(localization) 전문가입니다.\n규칙:\n1. 모든 텍스트를 ${L.name}로 옮긴다. 문체: ${L.style}.\n2. 직역 금지 — 그 언어 사용자가 실제로 쓰는 자연스러운 관용 표현으로.\n3. 해시태그는 번역이 아니라 그 언어권 인스타그램에서 실제 쓰이는 태그로 교체 (예: ${L.tagEx}). 개수 유지.\n4. 분량 규칙: 1페이지 headline ${L.hl1}자, 2~4페이지 headline ${L.hl}자·줄당 ${L.line}자 이내. 이모지 금지.\n5. 입력 JSON과 완전히 같은 구조로만 응답한다(키 추가·삭제 금지).`,
    user: `다음 카드뉴스 콘텐츠를 ${L.name}로 현지화하세요.\n\n${JSON.stringify(input, null, 2)}`
  });

  const out = extractJson(text);
  if (!out.pages?.page1) throw new Error('번역 결과 형식 오류');
  return { success: true, targetLang: target, ...out };
}

async function handleValidate(env, body) {
  const { pages } = body;
  const bookInfo = body.bookInfo || {}; // 프론트가 주제 정보를 담아 보내는 컨테이너(topic/title/coreMessage)
  const topic = String(bookInfo.topic || bookInfo.title || bookInfo.coreMessage || '카드뉴스').trim();
  const L = LANG_STYLE[langOf(body.lang)];
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
    max_tokens: 1024,
    system: '당신은 소셜미디어 콘텐츠 전문 편집장 겸 콘텐츠 안전성 검토자입니다. 반드시 JSON만 응답합니다.',
    user: `주제 "${topic}" ${L.name} 카드뉴스(캐러셀)를 아래 5가지 기준으로 평가하세요.\n\n캐럿셀 내용:\n${JSON.stringify(pages, null, 2)}\n\n평가 기준 (100점 만점):\n1. accuracy(주제 부합도): 모든 페이지가 주제를 벗어나지 않고 하나의 흐름으로 일관되게 전개되는가? 0~20\n2. factual(사실 정확성): 수치·통계·사례에 명백한 오류나 과장, 지어낸 근거가 없는가? 0~20\n3. copyright(안전성): 표절·저작권 침해 소지, 혐오·차별 표현, 의료·법률·투자에 대한 위험한 단정이 없는가? 0~20\n4. engagement(공감·참여 유도): 독자가 "저장해두고 싶다", "공유하고 싶다"고 느낄 공감과 실용성이 있는가? (공포·단정·비난 톤이면 감점) 0~25\n5. quality(문장 품질): 오타·비문·어색한 표현이 없고 간결한가? 문체(${L.style})가 유지되는가? 0~15\n\nJSON: {"totalScore":85,"scores":{"accuracy":17,"factual":16,"copyright":18,"engagement":22,"quality":12},"feedback":"전체 평가 2~3문장","improvements":["구체적 개선점1","개선점2","개선점3"],"approved":true}\napproved는 totalScore>=70이면 true.`
  });
  return { success: true, ...extractJson(text) };
}

// 릴스 1페이지 전용 "스크롤을 멈추는 강한 훅" 생성 (캐럿셀 1페이지의 잔잔한 문구와 별개).
async function handleReelHook(env, body) {
  const { pages, bookInfo } = body; // bookInfo = 주제 정보 컨테이너(topic/title/coreMessage)
  const topic = String(bookInfo?.topic || bookInfo?.title || bookInfo?.coreMessage || '').trim();
  const summary = [pages?.page1?.headline, pages?.page2?.headline, pages?.page4?.headline].filter(Boolean).join(' / ');
  const fallback = pages?.page1?.headline || '';
  try {
    const text = await callClaude(env.ANTHROPIC_API_KEY, {
      env, tier: 'light', max_tokens: 400, optional: true, // 예산 절약 모드에서 생략(폴백: 캐럿셀 1페이지 문구)
      system: `당신은 인스타그램 릴스 훅 카피라이터입니다. 스크롤을 1초 만에 멈추게 하는 강한 첫 문장(훅)을 만듭니다.\n규칙:\n① 유형은 "콕 집어내는 공감" 또는 "궁금증 격차" 또는 "의외의 사실/질문".\n② 한 줄, 18~28자. 너무 길지 않게.\n③ 강렬하되 공포·단정·비난·자극적 과장 금지.\n④ 이모지 금지. 존댓말·문어체.\n반드시 JSON만 응답.`,
      user: `주제: ${topic}\n캐럿셀 요지: ${summary}\n\n스크롤을 멈추게 하는 릴스 훅 후보 3개를 만들고, 그중 가장 강한 하나를 고르세요.\nJSON: {"candidates":["...","...","..."],"best":"가장 강한 한 줄"}`,
    });
    const r = extractJson(text);
    const best = (r.best || (Array.isArray(r.candidates) && r.candidates[0]) || fallback || '').toString().trim();
    return { success: true, hook: best || fallback, candidates: Array.isArray(r.candidates) ? r.candidates : [] };
  } catch (e) {
    return { success: true, hook: fallback, candidates: [] };
  }
}

// 릴스 대본(4장) — 한 편의 흐름으로 "연결되게" 생성하고, 자체 검증(연결성·가독성)까지 한 번에.
// 캐럿셀의 조각을 잘라 붙이던 방식(어색함)을 대체한다. 5번째 장(마무리 CTA)은 프론트 캔버스가 처리.
// v1.2: 현재 언어 하나로만 생성 — 다른 언어는 탭 전환 시 /api/translate가 함께 번역.
async function handleGenerateReel(env, body) {
  const { pages, bookInfo } = body;
  const lang = langOf(body.lang);
  const L = LANG_STYLE[lang];
  const arc = [pages?.page1?.headline, pages?.page2?.headline, pages?.page3?.headline, pages?.page4?.headline, pages?.page5?.cta]
    .filter(Boolean).join(' / ');
  // 폴백: 캐럿셀 헤드라인 그대로
  const fb = {
    s1: pages?.page1?.headline || '', s2: pages?.page2?.headline || '',
    s3: pages?.page3?.headline || '', s4: pages?.page4?.headline || '',
  };
  const topic = String(bookInfo?.topic || bookInfo?.title || bookInfo?.coreMessage || '').trim();
  try {
    const text = await callClaude(env.ANTHROPIC_API_KEY, {
      env, tier: 'light', max_tokens: 700, optional: true, // 예산 절약 모드에서 생략(폴백: 캐럿셀 헤드라인)
      system: `당신은 인스타 릴스 대본 카피라이터입니다. 모든 문구를 ${L.name}로 씁니다. 문체: ${L.style}.\n[목표] 4개의 슬라이드 문구가 "한 편의 이야기처럼 자연스럽게 이어지게" 씁니다(뚝뚝 끊긴 조각 금지).\n[구성·흐름]\n· s1(훅): 스크롤을 멈추는 강한 첫 문장(콕 집는 공감/궁금증).\n· s2: s1에서 자연스럽게 이어받아 상황·문제를 구체적 장면으로.\n· s3: 그 이유나 원리를 쉽게 짚음(비난 금지).\n· s4: 실마리를 건네는 마무리(단정적 해결책 금지, 여운).\n[규칙] 각 슬라이드 한 화면에서 4~5초에 읽히게 ${L.line + 5}자 이내(한두 문장). 이모지 금지, 공포·단정 금지. 앞 문장과 접속·지시어로 연결되게.\n[검증] 초안을 쓴 뒤 4장이 매끄럽게 이어지는지 스스로 점검하고 최종본만 냅니다.\n반드시 JSON만 응답.`,
      user: `주제: ${topic}\n캐럿셀 흐름(참고): ${arc}\n\n위 흐름을 살리되, 4개 슬라이드가 자연스럽게 이어지는 릴스 대본을 쓰고 스스로 검증·보완해 최종본을 내세요.\nJSON: {"reel":{"s1":"...","s2":"...","s3":"...","s4":"..."},"validation":{"connected":true,"readable":true,"score":0~100,"note":"연결성·가독성 한줄평"}}`,
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
    return { success: true, reel: out, validation, lang };
  } catch (e) {
    return { success: true, reel: fb, validation: { connected: true, readable: true, score: null, note: '자동 생성 실패 — 캐럿셀 문구로 대체' }, lang };
  }
}

async function handleGenerateCaption(env, body) {
  const { pages } = body;
  const bookInfo = body.bookInfo || {}; // 주제 정보 컨테이너(topic/title/coreMessage)
  if (!pages) throw new Error('캐럿셀 데이터가 필요합니다.');

  const topic = String(bookInfo.topic || bookInfo.title || bookInfo.coreMessage || '').trim();
  const lang = langOf(body.lang);
  const L = LANG_STYLE[lang];

  // v1.2: 현재 언어 하나로만 생성 — 다른 언어 캡션은 탭 전환 시 /api/translate가 함께 번역
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'light',
    max_tokens: 600,
    system: `당신은 인스타그램 콘텐츠 크리에이터입니다. 독자가 공감해 "저장"하고 "친구에게 공유"하고 싶어지는 캡션을 ${L.name}로 씁니다. 문체: ${L.style}. 노골적 판매·공포·단정·비난 금지. 이모지 금지. 반드시 JSON만 응답합니다.`,
    user: `주제: ${topic}\n캐럿셀 첫 줄 훅: ${pages.page1?.headline || ''}\n\n인스타그램 캡션을 ${L.name}로 작성하세요. (목적: 저장·공유로 팔로워 늘리기.)\n\n[게시물 캡션(caption) 구조 — 순서 엄수]\n1줄: 독자의 마음을 붙잡는 공감형 한 문장 (공포·단정 금지)\n2~3줄: 캐럿셀 핵심 초간결 요약 (반복 금지)\n끝에서 둘째 줄: 저장 유도 한 문장\n마지막 줄: 공유 또는 팔로우 유도 한 문장\n\n[릴스 캡션(reelCaption)] 짧은 후킹형 1~2줄. 게시물 캡션의 요약 금지 — 릴스만의 강한 한 마디.\n\n[추가 규칙]\n- hashtags: 게시물용 정확히 3개 — 그 언어권 인스타에서 실제로 쓰이는 태그로 (예: ${L.tagEx})\n- reelHashtags: 릴스용 핵심 태그 정확히 2개\n- 게시물 캡션 전체 6줄 이내, 짧고 간결하게\n\nJSON:\n{"caption":"...","hashtags":["#","#","#"],"reelCaption":"...","reelHashtags":["#","#"]}`,
  });

  const parsed = extractJson(text);
  return {
    success: true, lang,
    caption: parsed.caption || '', hashtags: parsed.hashtags || [],
    reelCaption: parsed.reelCaption || '', reelHashtags: parsed.reelHashtags || [],
  };
}

async function handleRegenerate(env, body) {
  const { previousPages, feedback, improvements = [] } = body;
  const bookInfo = body.bookInfo || {}; // 주제 정보 컨테이너(topic/title/coreMessage)
  const topic = String(bookInfo.topic || bookInfo.title || bookInfo.coreMessage || '').trim();
  const lang = langOf(body.lang);
  const L = LANG_STYLE[lang];
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    env, tier: 'main', max_tokens: 1400,
    system: `당신은 인스타그램 카드뉴스(캐러셀) 전문 카피라이터입니다.\n핵심 규칙(절대 위반 금지):\n1. 모든 텍스트를 ${L.name}로 작성한다. 문체: ${L.style}.\n2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.\n3. 과장·공포 조장 금지. 확실하지 않은 통계·수치를 지어내지 않는다. 이모지 금지.\n반드시 JSON만 응답한다.`,
    user: `카드뉴스를 피드백에 맞게 개선하세요.\n주제: ${topic}\n${bookInfo.coreMessage && bookInfo.coreMessage !== topic ? `핵심 메시지: ${bookInfo.coreMessage}\n` : ''}\n이전 버전:\n${JSON.stringify(previousPages, null, 2)}\n\n피드백: ${feedback}\n개선 요청: ${improvements.join(' / ')}\n\n텍스트 길이 기준:\n- 1페이지 headline: ${L.hl1}자 이내 완전한 문장. 단어 조각 절대 금지. subtext 없음.\n- 2~4페이지 headline: ${L.hl}자 이내, body: 3~4줄(줄당 ${L.line}자 이내).\n- 5페이지: cta(마무리 한 문장) + linkText(저장·팔로우 유도 한 줄)\n\nJSON:\n${PAGES_JSON_SHAPE}`
  });
  return { success: true, pages: extractJson(text), lang };
}

// 캔버스 넘침 감지 후 텍스트 단축
async function handleAdjustText(env, body) {
  const { pages, issues } = body;
  if (!pages || !issues?.length) return { success: true, pages };

  const issueDesc = issues.map(i =>
    `${i.page} ${i.type}: ${i.currentLines}줄(최대 ${i.maxLines}줄) — "${i.text}"`
  ).join('\n');

  let text;
  try {
    text = await callClaude(env.ANTHROPIC_API_KEY, {
      env, tier: 'light',
      max_tokens: 1024,
      optional: true, // 예산 절약 모드에서 생략(폴백: 원본 텍스트 유지)
      system: '당신은 인스타그램 카드뉴스 카피라이터입니다. 주어진 텍스트를 지정된 줄 수 이내로 압축합니다. 반말 절대 금지 — 문어체·존댓말만 허용. 반드시 JSON만 응답합니다.',
    user: `다음 캐럿셀 텍스트가 이미지 레이아웃에서 넘칩니다. 각 항목을 지정된 최대 줄 수 이내로 압축하세요.\n의미·임팩트는 유지하되 더 간결하게 다듬어주세요.\n\n현재 캐럿셀:\n${JSON.stringify(pages, null, 2)}\n\n넘치는 항목:\n${issueDesc}\n\n압축 규칙:\n- headline: 최대 3줄 (40자 이내, 강렬하게)\n- body: 최대 5줄 (줄당 45자 이내)\n\n전체 pages JSON을 반환하세요:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`,
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
        { text: '이 이미지의 원본 출처를 추적하려 합니다. 구글 검색을 적극 활용해 아래를 조사하고, 마지막에 반드시 JSON 하나로 정리해 답하세요.\n\n조사 항목:\n1. 이미지에 무엇이 있는가 — 작품명(드라마·영화·애니·게임 등)·인물·장소·워터마크·로고·서명·화면 속 텍스트 같은 출처 단서 포함\n2. 이 이미지의 원본 출처로 추정되는 곳 (원작품/작가/공식 플랫폼)\n3. 저작권·라이선스 위험도 판정:\n   - high: 상업 콘텐츠(방송·영화·웹툰·유료 스톡 등)로 보여 무단 재가공 위험이 큼\n   - medium: 출처가 불명확하거나 이용 조건 확인 필요\n   - low: 퍼블릭 도메인·CC0·자유 이용 가능성이 높음\n   - unknown: 판단 불가\n\nJSON 형식(이 형식만, 다른 텍스트로 끝내지 말 것):\n{"summary":"이미지 설명 한두 문장","clues":["출처 단서1","단서2"],"originGuess":"추정 원본 출처 설명 한두 문장","originCandidates":[{"name":"출처명","url":"https://..."}],"licenseRisk":"high|medium|low|unknown","licenseNote":"위험도 판단 이유 한두 문장"}' },
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
async function handleFetchOriginImages(env, body) {
  const urls = (Array.isArray(body.urls) ? body.urls : [])
    .filter(u => /^https?:\/\//i.test(String(u))).slice(0, 3);
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
      if (ct.startsWith('image/')) { found.push({ pageUrl, imageUrl: pageUrl }); return; } // 링크가 이미지 자체
      if (!ct.includes('html')) return;
      const html = (await res.text()).slice(0, 500000);
      const cands = new Set();
      for (const re of [
        /<meta[^>]+property=["']og:image(?::secure_url)?["'][^>]*content=["']([^"']+)["']/gi,
        /<meta[^>]+content=["']([^"']+)["'][^>]*property=["']og:image(?::secure_url)?["']/gi,
        /<meta[^>]+name=["']twitter:image(?::src)?["'][^>]*content=["']([^"']+)["']/gi,
      ]) {
        let m;
        while ((m = re.exec(html)) && cands.size < 3) cands.add(m[1]);
      }
      for (const u of cands) {
        try { found.push({ pageUrl, imageUrl: new URL(u, pageUrl).href }); } catch {}
      }
    } catch {} // 페이지 하나 실패해도 나머지 계속
  }));

  // 중복 제거 + 최대 6개
  const seen = new Set(); const images = [];
  for (const r of found) {
    if (!seen.has(r.imageUrl)) { seen.add(r.imageUrl); images.push(r); if (images.length >= 6) break; }
  }
  return { success: true, images };
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
          const r = await fetch(src, { redirect: 'follow', headers: { 'User-Agent': 'Mozilla/5.0 (compatible; card-carousel/1.0)' } });
          const ct = r.headers.get('content-type') || '';
          if (!r.ok || !ct.startsWith('image/')) return new Response('not image', { status: 415, headers: CORS });
          const buf = await r.arrayBuffer();
          if (buf.byteLength > 15 * 1024 * 1024) return new Response('too large', { status: 413, headers: CORS });
          return new Response(buf, {
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
        else if (url.pathname === '/api/reel-hook') result = await handleReelHook(env, body);
        else if (url.pathname === '/api/generate-reel') result = await handleGenerateReel(env, body);
        else if (url.pathname === '/api/generate-caption') result = await handleGenerateCaption(env, body);
        else if (url.pathname === '/api/validate') result = await handleValidate(env, body);
        else if (url.pathname === '/api/regenerate') result = await handleRegenerate(env, body);
        else if (url.pathname === '/api/send-telegram') result = await handleSendTelegram(env, body);
        else if (url.pathname === '/api/send-telegram-image') result = await handleSendTelegramImage(env, body);
        else if (url.pathname === '/api/post-instagram') result = await handlePostInstagram(env, body);
        else if (url.pathname === '/api/telegram-webhook') result = await handleTelegramWebhook(env, body);
        else if (url.pathname === '/api/setup-webhook') result = await handleSetupWebhook(env);
        else if (url.pathname === '/api/adjust-text') result = await handleAdjustText(env, body);
        else if (url.pathname === '/api/trace-origin') result = await handleTraceOrigin(env, body);
        else if (url.pathname === '/api/suggest-topic') result = await handleSuggestTopic(env, body);
        else if (url.pathname === '/api/translate') result = await handleTranslate(env, body);
        else if (url.pathname === '/api/fetch-origin-images') result = await handleFetchOriginImages(env, body);
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

    return env.ASSETS.fetch(request);
  },
};
