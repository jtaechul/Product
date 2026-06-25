const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

const SELF_URL = 'https://book-carousel.jtaechul.workers.dev';

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
  const timer = setTimeout(() => ctrl.abort(), 10000);
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

async function resolveModels(apiKey) {
  if (_modelCache) return _modelCache;

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

  // probe가 200을 한 번도 못 받았더라도, 후보 모델 목록이 있으면 하드 실패하지 않고
  // 최상위 후보로 폴백한다. probe 실패는 대개 일시적 429/타임아웃이며, 진짜 권한·결제
  // 문제라면 실제 호출(callClaude, 재시도 포함)에서 정확한 상태코드로 surface된다.
  // → "사용 가능한 모델 없음"으로 앱 전체가 멈추는 일을 방지.
  if (!main) {
    main = mainOrder[0] || ids[0] || null;
    light = lightOrder[0] || main;
    if (main) {
      // 폴백 결과는 캐시하지 않음 → 다음 요청에서 정상 probe를 재시도
      return { main, light, source: 'fallback-unprobed', available: ids, probed };
    }
    return { main: null, light: null, source: 'none-usable', available: ids, probed };
  }

  _modelCache = { main, light, source: 'probed', available: ids, probed };
  return _modelCache;
}

// 핸들러에서 쓸 모델 ID 반환 (없으면 원인을 알려주는 에러)
async function getModel(apiKey, tier) {
  const m = await resolveModels(apiKey);
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
// 403은 보통 영구 오류지만, Anthropic이 간헐적으로 "Request not allowed" 403을
// 일시적으로 반환하는 사례가 관측됨(엣지 라우팅/리전). 제한된 재시도로 흡수한다.
const RETRYABLE_STATUS = new Set([403, 408, 409, 429, 500, 502, 503, 504, 529]);

async function callClaude(apiKey, { model, system, user, max_tokens = 2048 }, attempt = 0) {
  const MAX_RETRIES = 3;
  const BACKOFF_MS = [1000, 3000, 7000];
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
      return callClaude(apiKey, { model, system, user, max_tokens }, attempt + 1);
    }
    throw new Error(`Claude 호출 네트워크 오류: ${netErr.message}`);
  }

  if (!res.ok) {
    if (RETRYABLE_STATUS.has(res.status) && attempt < MAX_RETRIES) {
      // 서버가 Retry-After를 주면 우선 존중, 없으면 지수 백오프
      const ra = parseInt(res.headers.get('retry-after') || '', 10);
      const wait = Number.isFinite(ra) ? Math.min(ra * 1000, 10000) : BACKOFF_MS[attempt];
      await new Promise(r => setTimeout(r, wait));
      return callClaude(apiKey, { model, system, user, max_tokens }, attempt + 1);
    }
    const errBody = await res.json().catch(() => ({}));
    const detail = errBody?.error?.message || JSON.stringify(errBody);
    throw new Error(`[${res.status}] ${detail}`);
  }
  return (await res.json()).content[0].text;
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
    ? `${SELF_URL}/?pipeline=${encodeURIComponent(pipelineId)}`
    : `${SELF_URL}/`;

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
async function handleSuggest(env, body) {
  const { category, issue, excludeTitles = [] } = body;
  const topic = issue || category || '자기계발';

  const today = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
  const excludeClause = excludeTitles.length
    ? `\n제외 도서(이미 캐럿셀로 만든 책이므로 절대 추천 금지): ${excludeTitles.join(', ')}`
    : '';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'main'),
    system: '당신은 도서 큐레이터입니다. 최신 베스트셀러 트렌드와 사회적 이슈를 바탕으로 실제 존재하는 책을 추천합니다. 반드시 JSON만 응답합니다.',
    user: `오늘 날짜: ${today}\n주제: "${topic}"${excludeClause}\n\n이 주제와 관련해 지금 이 시점에 주목받을 만한 실제 책 4권을 추천하세요.\n최근 1~2년 내 출간된 신간이거나, 최신 사회 이슈(AI·경제위기·부동산·건강·인간관계·기후·취업 등)와 직접 연결되는 인사이트 있는 책을 우선 선정하세요.\n동일 저자 책은 중복 추천하지 마세요.\n\n각 책에 대해:\n- title: 책 제목 (실제 출판된 책)\n- author: 저자명\n- year: 출판연도 (숫자)\n- category: 카테고리\n- coreMessage: 이 책의 핵심 메시지 (1~2문장)\n- targetAudience: 주요 대상 독자층 (1문장)\n- reason: 지금 이 책을 읽어야 하는 이유 (1문장, 최신 트렌드/이슈 연결)\n\nJSON 형식:\n{"books":[{"title":"...","author":"...","year":2024,"category":"...","coreMessage":"...","targetAudience":"...","reason":"..."}]}`,
  });

  return { success: true, ...extractJson(text) };
}

// 책 제목만으로 핵심메시지·독자층 자동 분석
async function handleAnalyze(env, body) {
  const { title, author } = body;
  if (!title) throw new Error('책 제목이 필요합니다.');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 512,
    system: '당신은 도서 분석 전문가입니다. 책 제목과 저자를 보고 핵심 메시지와 대상 독자층을 분석합니다. 반드시 JSON만 응답합니다.',
    user: `책: "${title}"${author ? ` / 저자: ${author}` : ''}\n\n이 책의 정보를 분석하세요.\n\nJSON: {"author":"저자명","year":출판연도(숫자),"category":"카테고리","coreMessage":"이 책의 핵심 메시지 1~2문장","targetAudience":"주요 대상 독자층 1문장"}`,
  });

  return { success: true, ...extractJson(text) };
}

async function handleGenerate(env, body) {
  const { title, author, year, coreMessage, targetAudience, category } = body;
  if (!title || !author || !coreMessage) throw new Error('제목, 저자, 핵심 메시지는 필수입니다.');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'main'),
    system: `당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다.\n핵심 규칙(절대 위반 금지):\n1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.\n2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.\n3. 공포감·호기심·위기감으로 저장·공유율을 높인다.\n4. 모든 콘텐츠에 반말을 절대 사용하지 않는다 — 문어체·존댓말(~습니다/~합니다/~세요)만 허용.\n반드시 JSON만 응답한다.`,
    user: `다음 책 정보로 5페이지 인스타그램 캐럿셀을 작성하세요.\n\n카테고리: ${category || '자기계발'}\n핵심 메시지: ${coreMessage}\n${targetAudience ? `대상: ${targetAudience}` : ''}\n\n페이지 가이드 (길이 규칙 엄수):\n1페이지(훅 — 헤드라인만): 카드 전체를 단 하나의 강렬한 문장으로 채운다.\n  - headline: 40자 이내 완전한 문장. 독자가 이미 겪었을 구체적 상황을 묘사한다.\n    규칙: "당신이 이 사실을 모른다면" 패턴 절대 금지. "대부분의 사람들이" 금지. 주어 없는 단어 조각 금지.\n    접근법: 독자의 일상 경험을 정확히 포착한 문장. 통계보다 경험 공유형.\n    좋은 예: "매달 저축하는데 잔고는 왜 줄어드는 걸까요"\n             "열심히 일하는데 10년째 제자리라면 이유가 있습니다"\n             "아무리 다이어트해도 살이 빠지지 않는 데는 이유가 있습니다"\n    나쁜 예(절대 금지): "뇌가 먼저 죽어간다" / "당신의 뇌는 몸보다 먼저 죽어가고 있다" (공포 자극형)\n  - subtext 없음 — JSON에 포함하지 않는다.\n2페이지(문제): 구체적 수치·현실 사례로 독자가 공감할 문제 상황을 서술한다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 45자 이내. 구체적 수치(%, 명, 연도)를 최소 1개 포함.\n3페이지(심각성): "대부분은 이 사실을 모른다" 접근으로 충격 사실·연구 결과를 제시한다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 45자 이내. 출처 가능 수준의 실제 통계·연구 인용 1건 이상.\n4페이지(실마리): 완전한 해결책은 절대 주지 말고 '해결 방향의 단서'만 암시해 DM 욕구를 자극한다.\n  - headline: 18자 이내\n  - body: 3~4줄, 한 줄 45자 이내. 마지막 줄은 '그렇다면 어떻게?' 암시로 끝낸다.\n5페이지(참여형 질문): 독자가 자기 상황에 대해 답하고 싶어지는 A/B 선택 질문으로 참여를 유도한다.\n  - cta: 독자 자신의 경험/상태를 묻는 A/B 선택 형식 2~3줄.\n    예시 형식: "지금 당신은 어느 쪽인가요?\\nA. 알고는 있지만 아직 시작 못했다\\nB. 시작했지만 방향을 모르겠다"\n    핵심: 책이나 정보가 아니라 독자 자신의 상황을 묻는 질문이어야 한다.\n  - linkText: "더 알고 싶다면 댓글로 알려주세요" 형태의 자연스러운 참여 유도 한 줄 (키워드 강요 없이)\n\nJSON:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });

  return { success: true, pages: extractJson(text) };
}

async function handleValidate(env, body) {
  const { pages, bookInfo } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 1024,
    system: '당신은 소셜미디어 콘텐츠 전문 편집장 겸 저작권 검토자입니다. 반드시 JSON만 응답합니다.',
    user: `책 "${bookInfo.title}" (저자: ${bookInfo.author}) 캐럿셀을 아래 5가지 기준으로 평가하세요.\n\n캐럿셀 내용:\n${JSON.stringify(pages, null, 2)}\n\n평가 기준 (100점 만점):\n1. accuracy(책 내용 부합도): 캐럿셀 내용이 해당 책의 실제 메시지와 일치하는가? 0~20\n2. factual(사실 정확성): 수치·통계·사례에 명백한 오류나 과장이 없는가? 0~20\n3. copyright(저작권 안전성): 책의 핵심 내용을 그대로 옮기지 않고 요약·재해석했는가? 저자명·책 제목이 본문에 노출되지 않는가? 0~20\n4. engagement(소비자 자극): 공포감·호기심·위기감이 충분해 저장·DM·구매 욕구를 자극하는가? 0~25\n5. quality(문장 품질): 오타·비문·어색한 표현이 없고 간결한가? 0~15\n\nJSON: {"totalScore":85,"scores":{"accuracy":17,"factual":16,"copyright":18,"engagement":22,"quality":12},"feedback":"전체 평가 2~3문장","improvements":["구체적 개선점1","개선점2","개선점3"],"approved":true}\napproved는 totalScore>=70이면 true.`
  });
  return { success: true, ...extractJson(text) };
}

// 페이지별 폴백 프롬프트 — Claude가 생성 실패 시 사용
// 각 페이지의 감정 흐름(긴장→문제→충격→희망→여운)에 맞춘 비주얼 방향
const FALLBACK_IMAGE_PROMPTS = {
  page1: 'lone figure standing at edge of foggy cliff at dawn, dramatic cinematic atmosphere, tension and anticipation, dark moody tones with single ray of light, no text',
  page2: 'empty chair at cluttered desk late at night, single lamp light, papers scattered, documentary style photography, melancholic urban atmosphere, no text',
  page3: 'cracked dry earth under harsh sunlight, stark contrast, bold graphic composition, striking and impactful, warning visual, no text',
  page4: 'hands opening a book as golden sunrise light spills through, warm breakthrough feeling, hopeful and uplifting, soft natural light, no text',
  page5: 'solitary path through autumn forest, soft diffused light, contemplative open horizon, peaceful but unresolved, invitation to journey, no text',
};

// 페이지별 시각 방향 지침 — 사진 촬영 용어로 구체적으로 명시 (Flux 모델 최적화)
const PAGE_VISUAL_DIRECTIONS = {
  page1: 'editorial photography, lone silhouette on empty road at golden hour, long dramatic shadows, muted desaturated palette with single warm horizon glow, ultra-wide angle composition, strong negative space, bottom third dark and uncluttered for text overlay',
  page2: 'documentary photography, solitary person at rain-streaked cafe window at night, warm amber interior vs cold blue exterior, f/2.8 shallow depth of field, candid emotional weight, bottom half simple dark gradient for text',
  page3: 'bold conceptual photography, single stark object under harsh overhead spotlight against pure black background, strong geometric shadow on floor, graphic editorial style, extreme contrast, minimal composition, no clutter',
  page4: 'lifestyle photography, hands carefully opening a worn leather book near sunlit window, golden morning light, floating dust particles in light beam, warm hopeful intimate scale, dark lower third for text overlay',
  page5: 'fine art landscape photography, single bare tree on expansive open hillside at dusk, ultra-wide field of view, vast negative space dominates, contemplative and open-ended mood, soft gradient sky from orange to deep blue, serene and unresolved',
};

async function handleGenerateImages(env, body) {
  const { pages, bookInfo } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 페이지 전체 내용 구성 (헤드라인 + 본문 요약) — 내용 부합도 극대화
  const pageContents = {
    page1: [pages.page1?.headline, pages.page1?.body?.slice(0, 80)].filter(Boolean).join(' / '),
    page2: [pages.page2?.headline, pages.page2?.body?.slice(0, 80)].filter(Boolean).join(' / '),
    page3: [pages.page3?.headline, pages.page3?.body?.slice(0, 80)].filter(Boolean).join(' / '),
    page4: [pages.page4?.headline, pages.page4?.body?.slice(0, 80)].filter(Boolean).join(' / '),
    page5: [pages.page5?.cta, pages.page5?.body?.slice(0, 80)].filter(Boolean).join(' / '),
  };

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 1400,
    system: '당신은 광고 사진 아트 디렉터입니다. 각 페이지 감정에 맞는 Flux 이미지 생성 영어 프롬프트를 작성합니다.\n규칙:\n1. 카메라 렌즈·조명·구도를 구체적으로 명시한다 (예: f/2.8 shallow depth, golden hour backlight, rule of thirds)\n2. 사람 얼굴 클로즈업 금지 — 뒷모습·실루엣·손만 허용\n3. 텍스트·글자·숫자 없음 (no text, no letters)\n4. 이미지 하단 30%는 어둡거나 단순하게 — 텍스트 오버레이 공간\n5. 각 페이지마다 완전히 다른 시각 언어를 써야 한다 (중복 금지)\n6. 60단어 이내, Instagram 1:1 정사각형 기준\n반드시 JSON만 응답한다.',
    user: `책 카테고리: ${bookInfo.category || '자기계발'}\n책 핵심 주제: ${bookInfo.coreMessage || bookInfo.title || ''}\n\n아래 5페이지 카드뉴스 내용을 보고, 각 페이지의 내용과 감정에 정확히 부합하는 배경 이미지 프롬프트 5개를 작성하세요.\npage1~page5 키를 반드시 모두 포함해야 합니다.\n\n=== 각 페이지 내용 ===\n1페이지(훅 — 충격·공포·호기심): ${pageContents.page1}\n  시각 방향: ${PAGE_VISUAL_DIRECTIONS.page1}\n\n2페이지(문제 — 현실 직시): ${pageContents.page2}\n  시각 방향: ${PAGE_VISUAL_DIRECTIONS.page2}\n\n3페이지(심각성 — 경각심): ${pageContents.page3}\n  시각 방향: ${PAGE_VISUAL_DIRECTIONS.page3}\n\n4페이지(실마리 — 희망·전환): ${pageContents.page4}\n  시각 방향: ${PAGE_VISUAL_DIRECTIONS.page4}\n\n5페이지(CTA — 여운·초대): ${pageContents.page5}\n  시각 방향: ${PAGE_VISUAL_DIRECTIONS.page5}\n\n=== 공통 규칙 ===\n- 페이지별 내용과 감정을 구체적으로 반영할 것 (추상적 책 이미지 5개 금지)\n- 인물 얼굴 클로즈업 금지 (뒷모습·실루엣·손 등 허용)\n- 텍스트·글자·숫자 없음 (no text, no letters)\n- Instagram 1:1 정사각형 구도\n- 각 프롬프트는 영어, 60단어 이내\n- 하단 30%는 어둡거나 단순한 영역으로 구성 (텍스트 오버레이 공간 확보)\n\nJSON (page1~page5 모두 필수): {"page1":"prompt","page2":"prompt","page3":"prompt","page4":"prompt","page5":"prompt"}`,
  });

  const prompts = extractJson(text);

  // 5페이지 모두 존재하는지 확인 — 누락 시 페이지별 폴백으로 보완
  for (let i = 1; i <= 5; i++) {
    const key = `page${i}`;
    if (!prompts[key] || typeof prompts[key] !== 'string' || prompts[key].trim() === '') {
      prompts[key] = FALLBACK_IMAGE_PROMPTS[key];
    }
  }

  const suffix = ', no text, no letters, high quality, Instagram square format 1:1';
  const base = 'https://image.pollinations.ai/prompt/';

  // 페이지마다 다른 seed → 동일 요청 충돌·캐시 문제로 인한 로딩 실패 감소
  const images = {};
  for (const [page, prompt] of Object.entries(prompts)) {
    const seed = Math.floor(Math.random() * 900000) + 100000;
    images[page] = `${base}${encodeURIComponent(prompt + suffix)}?width=1080&height=1080&nologo=true&seed=${seed}&model=flux&enhance=true`;
  }

  return { success: true, images, prompts };
}

async function handleGenerateCaption(env, body) {
  const { pages, bookInfo, dmKeyword } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 댓글 키워드 힌트: 특수기호만 제거하고 원형 그대로 Claude에 전달.
  // Claude가 자연스러운 완결 단어(2~3자)를 직접 선택한다 — 강제 절단 금지.
  const kwHint = (dmKeyword || bookInfo.category || '독서').replace(/[^가-힣a-zA-Z0-9]/g, '') || '독서';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 512,
    system: '당신은 인스타그램 콘텐츠 크리에이터입니다. 독자가 자연스럽게 참여하고 싶어지는 캡션을 씁니다. 책 제목을 절대 노출하지 않고, 노골적 판매 표현을 피합니다. 반말 절대 금지 — 문어체·존댓말(~습니다/~합니다/~세요)만 허용. 반드시 JSON만 응답합니다.',
    user: `책 카테고리: ${bookInfo.category || '자기계발'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n캐럿셀 첫 줄 훅: ${pages.page1?.headline || ''}\n5페이지 CTA: ${pages.page5?.cta || ''}\n\n[댓글 키워드 선택 규칙]\n- 주제 힌트: "${kwHint}"\n- 이 주제에서 자연스럽고 완결된 단어를 댓글 키워드로 선택한다.\n- 키워드는 기본적으로 2자를 사용한다. 3자는 그 단어 자체가 원래부터 3자인 경우에만 허용한다.\n- 긴 단어를 억지로 잘라 만들지 않는다. (예: '경제투자'→'경제' 또는 '투자' 중 하나 선택. '경제투'처럼 어색하게 자르기 절대 금지)\n\n인스타그램 캡션을 작성하세요.\n\n[캡션 구조 — 순서 엄수]\n1줄: 독자의 일상 경험을 포착한 공감형 질문 (책 제목 절대 노출 금지. "당신이 모른다면" 패턴 금지. "대부분의 사람들이" 금지)\n2~3줄: 캐럿셀 핵심 인사이트 초간결 요약 (반복 금지, 노골적 판매 금지)\n끝에서 둘째 줄: 저장 유도 문구 ("나중에 꺼내보고 싶다면 저장해두세요" 또는 "도움이 됐다면 저장해두세요" 형태)\n마지막 줄: "더 자세한 내용이 궁금하다면 댓글에 '[선택한 키워드]'를 남겨주세요" 형태 — 강요 대신 선택 제공\n\n[추가 규칙]\n- 해시태그: 정확히 3개 (카테고리 관련)\n- 전체 6줄 이내, 짧고 강렬하게\n\nJSON: {"caption":"1줄\\n2줄\\n3줄\\n저장유도줄\\n댓글유도줄","hashtags":["#tag1","#tag2","#tag3"],"commentKeyword":"[2~3자 자연스러운 완결 키워드]"}`,
  });

  const result = extractJson(text);
  // 구형 dmKeyword 필드도 호환성 유지
  result.dmKeyword = result.commentKeyword || kwHint.slice(0, 2) || '책';
  return { success: true, ...result };
}

async function handleRegenerate(env, body) {
  const { bookInfo, previousPages, feedback, improvements } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'main'),
    system: `당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다.\n핵심 규칙(절대 위반 금지):\n1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.\n2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.\n3. 5페이지는 반문·열린 결말 구조 — 구매 유도나 직접 행동 지시 없이 독자에게 질문을 던진다.\n4. 모든 콘텐츠에 반말을 절대 사용하지 않는다 — 문어체·존댓말(~습니다/~합니다/~세요)만 허용.\n반드시 JSON만 응답한다.`,
    user: `캐럿셀을 피드백에 맞게 개선하세요.\n카테고리: ${bookInfo.category || '자기계발'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n\n이전 버전:\n${JSON.stringify(previousPages, null, 2)}\n\n피드백: ${feedback}\n개선 요청: ${improvements.join(' / ')}\n\n텍스트 길이 기준:\n- 1페이지 headline: 40자 이내 완전한 문장(주어+상황+결과). 단어 조각 절대 금지. subtext 없음.\n- 2~4페이지 headline: 18자 이내, body: 3~4줄(줄당 45자 이내). 구체적 수치·사례 포함.\n- JSON 형식: {"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},...}\n\nJSON:\n{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
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
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
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
  const { pages, bookInfo, affiliateLink, affiliateLinks } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 여러 링크 지원: affiliateLinks 배열 우선, 없으면 단일 affiliateLink 폴백
  const links = Array.isArray(affiliateLinks) && affiliateLinks.length
    ? affiliateLinks.filter(l => l && l.trim())
    : (affiliateLink ? [affiliateLink] : []);
  const linksText = links.length
    ? links.map((l, i) => `${i + 1}. ${l}`).join('\n')
    : '(미입력)';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 512,
    system: '당신은 인스타그램 DM 자동 회신 작성 전문가입니다. 댓글 키워드를 남긴 팔로워에게 보낼 DM을 씁니다. 따뜻하고 개인적인 톤, 노골적 판매 금지. 반말 절대 금지 — 존댓말(~습니다/~합니다/~세요)만 허용. 반드시 JSON만 응답합니다.',
    user: `책 제목: ${bookInfo.title}\n저자: ${bookInfo.author}\n카테고리: ${bookInfo.category || '자기계발'}\n핵심 메시지: ${bookInfo.coreMessage || ''}\n\n5페이지에서 독자에게 던진 반문: ${pages.page5?.cta || ''}\n5페이지 마무리 문구: ${pages.page5?.linkText || ''}\n\n어필리에이트 링크:\n${linksText}\n\n댓글에 키워드를 남긴 팔로워에게 보낼 DM을 작성하세요.\n\n구성:\n1. 친근한 인사 (1줄)\n2. 책 제목과 저자 자연스럽게 소개 (1줄)\n3. 이 책이 답하는 핵심 질문·고민 (독자 공감 유도, 2줄 이내)\n4. 5페이지 반문에 대한 제한적 힌트 (완전한 답은 절대 주지 말 것, 2줄 이내)\n5. 어필리에이트 링크 안내 (링크가 여러 개면 모두 자연스럽게 포함, 없으면 "곧 공유드릴게요" 처리)\n6. 따뜻한 마무리 (1줄)\n\nJSON: {"dmText":"전체 DM 텍스트(줄바꿈은 \\n)"}`,
  });

  const result = extractJson(text);

  // KV에 DM 회신 저장 (키워드 기반, 7일 TTL) — Phase 5 댓글 자동 감지용
  if (env.PENDING_POSTS && body.commentKeyword) {
    const kw2 = String(body.commentKeyword).replace(/[^가-힣a-zA-Z0-9]/g, '').slice(0, 3);
    if (kw2) await env.PENDING_POSTS.put(`dm_reply_${kw2}`, result.dmText || '', { expirationTtl: 604800 });
  }

  return { success: true, ...result };
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
  const { bookInfo, affiliateLinks = [], commentKeyword = '', models: savedModels } = state;

  // 단계별 Worker 인스턴스가 새로 뜨므로 _modelCache가 리셋됨 — KV에 저장된 값으로 복원
  if (savedModels?.main && !_modelCache) {
    _modelCache = { main: savedModels.main, light: savedModels.light };
  }

  const t0 = Date.now();
  const setActive = (label) => savePipelineStatus(env, pipelineId, { step, stepStatus: 'active', runningStep: step, label });

  if (step === 1) {
    await setActive('Claude AI가 5페이지 카드뉴스를 작성 중...');
    await logStep(env, pipelineId, { step, phase: 'start', model: _modelCache?.main });
    // 1단계(생성) 실패는 치명적 → throw하여 advancePipeline이 error로 마감
    const genData = await handleGenerate(env, bookInfo);
    const pages = genData.pages;
    const patch = { step: 1, stepStatus: 'done', label: '5페이지 카드뉴스 생성 완료', pages };
    // 모델 ID를 KV에 저장 → 이후 단계에서 재프로빙 없이 재활용
    if (_modelCache?.main) patch.models = { main: _modelCache.main, light: _modelCache.light };
    await savePipelineStatus(env, pipelineId, patch);
    await logStep(env, pipelineId, { step, phase: 'done', model: _modelCache?.main, durationMs: Date.now() - t0 });

  } else if (step === 2) {
    const { pages } = state;
    await setActive('AI 자동 품질 평가 중...');
    await logStep(env, pipelineId, { step, phase: 'start' });
    let updatedPages = pages;
    let validation = null;
    try {
      for (let attempt = 1; attempt <= 2; attempt++) {
        validation = await handleValidate(env, { pages: updatedPages, bookInfo });
        if (validation.approved) break;
        if (attempt < 2) {
          const rd = await handleRegenerate(env, { bookInfo, previousPages: updatedPages, feedback: validation.feedback, improvements: validation.improvements || [] });
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
      const capData = await handleGenerateCaption(env, { pages, bookInfo, dmKeyword: commentKeyword });
      caption = capData.caption || '';
      hashtags = capData.hashtags || [];
      dmKeyword = capData.commentKeyword || capData.dmKeyword || '';
    } catch (e) {
      await logStep(env, pipelineId, { step, phase: 'warn', error: '캡션 생성 실패(계속 진행): ' + e.message });
    }
    await savePipelineStatus(env, pipelineId, { step: 4, stepStatus: 'done', label: '캡션 + 해시태그 생성 완료', caption, hashtags, dmKeyword });
    await logStep(env, pipelineId, { step, phase: 'done', durationMs: Date.now() - t0 });

  } else if (step === 5) {
    const { pages, dmKeyword: savedKw } = state;
    const dmKeyword = savedKw || commentKeyword;
    await setActive('DM 자동 회신 내용 작성 중...');
    await logStep(env, pipelineId, { step, phase: 'start' });
    let dmText = '';
    try {
      const dmData = await handleGenerateDmReply(env, { pages, bookInfo, affiliateLinks, commentKeyword: dmKeyword });
      dmText = dmData?.dmText || '';
    } catch (e) {
      await logStep(env, pipelineId, { step, phase: 'warn', error: 'DM 회신 생성 실패(계속 진행): ' + e.message });
    }
    await savePipelineStatus(env, pipelineId, { step: 5, stepStatus: 'done', label: 'DM 자동 회신 생성 완료', dmText });
    await logStep(env, pipelineId, { step, phase: 'done', durationMs: Date.now() - t0 });

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
    return;                                        // 에러는 자동 재시도 안 함(무한루프 방지) — 로그로 분석
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
    await savePipelineStatus(env, pipelineId, { status: 'error', step: nextStep, stepStatus: 'error', label: `단계 ${nextStep} 실패: ${e.message}`, error: e.message });
    await logStep(env, pipelineId, { step: nextStep, phase: 'error', error: e.message });
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

  // 요일별 카테고리 순환 (일=0 ~ 토=6)
  const DAILY_CATEGORIES = ['경제', '심리', '건강', '자기계발', '인문', '사회', '과학'];
  const category = DAILY_CATEGORIES[kstNow.getDay()];

  // 최근 30일 내 사용한 책 목록 (중복 추천 방지)
  const usedStr = await env.PENDING_POSTS.get('daily_used_books').catch(() => null);
  const usedBooks = usedStr ? JSON.parse(usedStr) : [];

  // 1. AI 책 추천 — 이미 사용한 책은 제외
  const suggestData = await handleSuggest(env, { category, excludeTitles: usedBooks.slice(-20) });
  const books = suggestData.books || [];
  if (!books.length) return;

  // 추천 목록 중 첫 번째 책 선택
  const chosen = books[0];
  const bookInfo = {
    title: chosen.title,
    author: chosen.author || '',
    year: chosen.year || '',
    category: chosen.category || category,
    coreMessage: chosen.coreMessage || chosen.reason || '',
    targetAudience: chosen.targetAudience || '',
  };

  // 2. 파이프라인 시작 (수동 시작과 동일한 방식)
  const pipelineId = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  await savePipelineStatus(env, pipelineId, {
    status: 'running',
    step: 0,
    stepStatus: 'done',
    bookInfo,
    affiliateLinks: [],
    commentKeyword: category,
    startedAt: Date.now(),
    label: '[자동] 파이프라인 시작 — 곧 자동 진행됩니다',
    isAutoDaily: true,
  });
  await logStep(env, pipelineId, { step: 0, phase: 'start', note: `[자동] 책: ${bookInfo.title} / 카테고리: ${category}` });

  // 오늘 실행 기록 저장 (25시간 TTL — 다음 날 자동 실행 전까지 중복 방지)
  await env.PENDING_POSTS.put(todayKey, pipelineId, { expirationTtl: 25 * 3600 });

  // 사용 책 목록 업데이트 (최근 30권 보관, 31일 TTL)
  const newUsed = [...usedBooks, chosen.title].slice(-30);
  await env.PENDING_POSTS.put('daily_used_books', JSON.stringify(newUsed), { expirationTtl: 31 * 24 * 3600 });
}

// 크론(매 1분)에서 호출 — 진행중 파이프라인을 찾아 각각 한 단계씩 전진
async function runScheduled(env) {
  if (!env.PENDING_POSTS) return;
  let cursor;
  const ids = [];
  do {
    const list = await env.PENDING_POSTS.list({ prefix: 'pipeline_', cursor });
    for (const { name } of list.keys) ids.push(name.slice('pipeline_'.length));
    cursor = list.list_complete ? null : list.cursor;
  } while (cursor && ids.length < 200);

  let checked = 0, advanced = 0;
  for (const id of ids) {
    if (checked >= 30 || advanced >= 5) break;   // 한 틱당 작업량 상한
    checked++;
    const state = await env.PENDING_POSTS.get(`pipeline_${id}`, 'json').catch(() => null);
    if (!state || state.status !== 'running') continue;
    await advancePipeline(env, id);
    advanced++;
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
  const { bookInfo, affiliateLinks, commentKeyword } = body;
  if (!bookInfo?.title) throw new Error('책 정보(bookInfo.title)가 필요합니다.');
  if (!env.ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY가 설정되지 않았습니다.');
  if (!env.PENDING_POSTS) throw new Error('KV 스토어가 필요합니다.');

  const pipelineId = Date.now().toString(36) + Math.random().toString(36).slice(2, 7);

  // 초기 상태: step 0 / done → 다음 전진 시 1단계 실행
  await savePipelineStatus(env, pipelineId, {
    status: 'running',
    step: 0,
    stepStatus: 'done',
    bookInfo,
    affiliateLinks: affiliateLinks || [],
    commentKeyword: commentKeyword || '',
    startedAt: Date.now(),
    label: '파이프라인 시작 — 곧 자동 진행됩니다',
  });
  await logStep(env, pipelineId, { step: 0, phase: 'start', note: `책: ${bookInfo.title}` });

  // 즉시 1단계 킥 (self-fetch 없이 같은 인보케이션 waitUntil에서 직접 실행).
  // 이 킥이 실패하거나 중간에 죽어도 크론이 1분 내 자동으로 이어받는다 → 화면 상태 무관.
  ctx.waitUntil(advancePipeline(env, pipelineId).catch(() => {}));

  return { success: true, pipelineId };
}

// ===== 서버사이드 파이프라인 (구형 — 30초 한도로 대형 파이프라인 제한됨) =====
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
          const resolved = await resolveModels(key);

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
        else return json({ error: '없는 경로입니다.' }, 404);

        return json(result);
      } catch (err) {
        return json({ error: err.message }, 500);
      }
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
