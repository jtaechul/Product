const CORS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
};

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
// 7초 타임아웃 — probe 과다로 Worker 30s 한도 초과 방지
async function probeModel(apiKey, model) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 7000);
  try {
    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
      body: JSON.stringify({ model, max_tokens: 1, messages: [{ role: 'user', content: 'hi' }] }),
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    return res.status;
  } catch {
    clearTimeout(timer);
    return 0; // 타임아웃·네트워크 오류 → 사용 불가로 처리
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

  const main = await firstUsable(mainOrder);
  const light = (await firstUsable(lightOrder)) || main;

  if (!main) {
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

async function callClaude(apiKey, { model, system, user, max_tokens = 2048 }) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
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
  if (!res.ok) {
    const errBody = await res.json().catch(() => ({}));
    const detail = errBody?.error?.message || JSON.stringify(errBody);
    throw new Error(`[${res.status}] ${detail}`);
  }
  return (await res.json()).content[0].text;
}

function extractJson(text) {
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('JSON 파싱 실패');
  return JSON.parse(match[0]);
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
    // 이미지 전송 실패시 텍스트로 폴백
    console.error(`이미지 전송 실패(폴백): ${err.description || res.status}`);
    return sendTelegramMessage(botToken, chatId, caption || photoUrl);
  }
  return res.json();
}

async function handleSendTelegram(env, body) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error('TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.');
  }

  const { pages, bookInfo, caption, hashtags, commentKeyword, dmKeyword, images } = body;
  const kw = commentKeyword || dmKeyword || '';

  const captionBlock = caption
    ? `\n\n[캡션]\n${caption}\n${(hashtags || []).join(' ')}${kw ? `\n\n댓글 키워드: '${kw}'` : ''}`
    : '';

  // 1) 요약 텍스트 메시지
  const summaryMsg = `[북 캐럿셀 미리보기]\n책: ${bookInfo.title}\n저자: ${bookInfo.author}\n카테고리: ${bookInfo.category || ''}${captionBlock}`;
  await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, summaryMsg);
  await new Promise(r => setTimeout(r, 300));

  // 2) 페이지별 이미지+텍스트 전송 (이미지가 있으면 sendPhoto, 없으면 텍스트)
  const pageDefs = [
    { key: 'page1', label: '1/5 훅', text: pages.page1?.headline || '' },
    { key: 'page2', label: '2/5 문제', text: `${pages.page2?.headline || ''}\n\n${pages.page2?.body || ''}` },
    { key: 'page3', label: '3/5 심각성', text: `${pages.page3?.headline || ''}\n\n${pages.page3?.body || ''}` },
    { key: 'page4', label: '4/5 실마리', text: `${pages.page4?.headline || ''}\n\n${pages.page4?.body || ''}` },
    { key: 'page5', label: '5/5 반문·결말', text: `${pages.page5?.cta || ''}\n\n${pages.page5?.linkText || ''}` },
  ];

  let sent = 1;
  for (const { key, label, text } of pageDefs) {
    const imgUrl = images?.[key];
    const msgText = `[${label}]\n${text.trim()}`;
    if (imgUrl) {
      await sendTelegramPhoto(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, imgUrl, msgText);
    } else {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, msgText);
    }
    sent++;
    await new Promise(r => setTimeout(r, 300));
  }

  // KV에 게시물 상태 저장 (텔레그램 승인 콜백용, 24시간 TTL)
  if (env.PENDING_POSTS) {
    await env.PENDING_POSTS.put('latest', JSON.stringify({
      pages, bookInfo, caption, hashtags, commentKeyword: kw, images,
      createdAt: new Date().toISOString(),
    }), { expirationTtl: 86400 });
  }

  // 인스타그램 게시 승인 인라인 버튼 발송
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text: `[인스타그램 게시 승인]\n\n책: ${bookInfo.title}\n저자: ${bookInfo.author}\n\n위 캐럿셀을 인스타그램에 게시할까요?`,
      reply_markup: {
        inline_keyboard: [
          [{ text: '게시하기', callback_data: 'approve' }, { text: '취소', callback_data: 'cancel' }],
          [{ text: '수정 필요 (웹에서)', callback_data: 'modify' }],
        ],
      },
    }),
  }).catch(() => {});

  return { success: true, message: `텔레그램으로 ${sent}개 메시지를 보냈습니다. 텔레그램에서 [게시하기] 버튼을 눌러 인스타그램에 게시해주세요.` };
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
    user: `오늘 날짜: ${today}
주제: "${topic}"${excludeClause}

이 주제와 관련해 지금 이 시점에 주목받을 만한 실제 책 4권을 추천하세요.
최근 1~2년 내 출간된 신간이거나, 최신 사회 이슈(AI·경제위기·부동산·건강·인간관계·기후·취업 등)와 직접 연결되는 인사이트 있는 책을 우선 선정하세요.
동일 저자 책은 중복 추천하지 마세요.

각 책에 대해:
- title: 책 제목 (실제 출판된 책)
- author: 저자명
- year: 출판연도 (숫자)
- category: 카테고리
- coreMessage: 이 책의 핵심 메시지 (1~2문장)
- targetAudience: 주요 대상 독자층 (1문장)
- reason: 지금 이 책을 읽어야 하는 이유 (1문장, 최신 트렌드/이슈 연결)

JSON 형식:
{"books":[{"title":"...","author":"...","year":2024,"category":"...","coreMessage":"...","targetAudience":"...","reason":"..."}]}`,
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
    user: `책: "${title}"${author ? ` / 저자: ${author}` : ''}

이 책의 정보를 분석하세요.

JSON: {"author":"저자명","year":출판연도(숫자),"category":"카테고리","coreMessage":"이 책의 핵심 메시지 1~2문장","targetAudience":"주요 대상 독자층 1문장"}`,
  });

  return { success: true, ...extractJson(text) };
}

async function handleGenerate(env, body) {
  const { title, author, year, coreMessage, targetAudience, category } = body;
  if (!title || !author || !coreMessage) throw new Error('제목, 저자, 핵심 메시지는 필수입니다.');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'main'),
    system: `당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다.
핵심 규칙(절대 위반 금지):
1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.
2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.
3. 공포감·호기심·위기감으로 저장·공유율을 높인다.
반드시 JSON만 응답한다.`,
    user: `다음 책 정보로 5페이지 인스타그램 캐럿셀을 작성하세요.

카테고리: ${category || '자기계발'}
핵심 메시지: ${coreMessage}
${targetAudience ? `대상: ${targetAudience}` : ''}

페이지 가이드 (길이 규칙 엄수):
1페이지(훅 — 헤드라인만): 카드 전체를 단 하나의 강렬한 문장으로 채운다.
  - headline: 40자 이내 완전한 문장('주어+상황+구체적 결과' 구조 필수).
    좋은 예: "지금 이 순간에도 당신의 뇌는 몸보다 먼저 죽어가고 있다"
             "한국인 3명 중 1명은 이미 부채 함정에 빠졌다는 사실을 아는가"
    나쁜 예(절대 금지): "뇌가 먼저 죽어간다" / "돈이 사라진다" (단어 조각)
  - subtext 없음 — JSON에 포함하지 않는다.
2페이지(문제): 구체적 수치·현실 사례로 독자가 공감할 문제 상황을 서술한다.
  - headline: 18자 이내
  - body: 3~4줄, 한 줄 45자 이내. 구체적 수치(%, 명, 연도)를 최소 1개 포함.
3페이지(심각성): "대부분은 이 사실을 모른다" 접근으로 충격 사실·연구 결과를 제시한다.
  - headline: 18자 이내
  - body: 3~4줄, 한 줄 45자 이내. 출처 가능 수준의 실제 통계·연구 인용 1건 이상.
4페이지(실마리): 완전한 해결책은 절대 주지 말고 '해결 방향의 단서'만 암시해 DM 욕구를 자극한다.
  - headline: 18자 이내
  - body: 3~4줄, 한 줄 45자 이내. 마지막 줄은 '그렇다면 어떻게?' 암시로 끝낸다.
5페이지(반문·열린 결말): 구매 유도·책 이름 없이 독자 스스로 생각하게 만드는 반문.
  - cta: 열린 질문 2줄 이내
  - linkText: 여운 있는 한 줄

JSON:
{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });

  return { success: true, pages: extractJson(text) };
}

async function handleValidate(env, body) {
  const { pages, bookInfo } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 1024,
    system: '당신은 소셜미디어 콘텐츠 전문 편집장 겸 저작권 검토자입니다. 반드시 JSON만 응답합니다.',
    user: `책 "${bookInfo.title}" (저자: ${bookInfo.author}) 캐럿셀을 아래 5가지 기준으로 평가하세요.

캐럿셀 내용:
${JSON.stringify(pages, null, 2)}

평가 기준 (100점 만점):
1. accuracy(책 내용 부합도): 캐럿셀 내용이 해당 책의 실제 메시지와 일치하는가? 0~20
2. factual(사실 정확성): 수치·통계·사례에 명백한 오류나 과장이 없는가? 0~20
3. copyright(저작권 안전성): 책의 핵심 내용을 그대로 옮기지 않고 요약·재해석했는가? 저자명·책 제목이 본문에 노출되지 않는가? 0~20
4. engagement(소비자 자극): 공포감·호기심·위기감이 충분해 저장·DM·구매 욕구를 자극하는가? 0~25
5. quality(문장 품질): 오타·비문·어색한 표현이 없고 간결한가? 0~15

JSON: {"totalScore":85,"scores":{"accuracy":17,"factual":16,"copyright":18,"engagement":22,"quality":12},"feedback":"전체 평가 2~3문장","improvements":["구체적 개선점1","개선점2","개선점3"],"approved":true}
approved는 totalScore>=70이면 true.`
  });
  return { success: true, ...extractJson(text) };
}

// page5가 누락되는 원인: max_tokens 부족 시 Claude가 JSON에서 page5를 생략해도
// extractJson이 유효한 JSON을 파싱, applyImagesToCards가 조용히 건너뜀.
// 대책: max_tokens 1200으로 상향 + 누락 페이지를 폴백 프롬프트로 보완.
const FALLBACK_IMAGE_PROMPTS = {
  page1: 'dramatic spotlight on dark empty stage, single beam of light, stage curtains, cinematic atmosphere, no text',
  page2: 'crowded city streets at night, monochrome, overwhelming pressure, symbolic, cinematic, no text',
  page3: 'broken hourglass on dark table, red warning light, unsettling discovery, cinematic atmosphere, no text',
  page4: 'single candle flame in complete darkness, small hope emerging, warm glow, cinematic, no text',
  page5: 'vast open landscape at twilight, single silhouette walking toward horizon, contemplative, mysterious, open-ended, no text',
};

async function handleGenerateImages(env, body) {
  const { pages, bookInfo } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 1200,
    system: '당신은 AI 이미지 프롬프트 전문가입니다. 인스타그램 카드뉴스용 드라마틱한 일러스트 프롬프트를 영어로 작성합니다. 반드시 JSON만 응답합니다.',
    user: `책 카테고리: ${bookInfo.category || '자기계발'}

각 페이지 핵심 메시지:
1페이지(훅): ${pages.page1?.headline || ''}
2페이지(문제): ${pages.page2?.headline || ''}
3페이지(심각성): ${pages.page3?.headline || ''}
4페이지(실마리): ${pages.page4?.headline || ''}
5페이지(반문·결말): ${pages.page5?.cta || ''}

위 내용에 맞는 드라마틱한 일러스트 프롬프트를 정확히 5개 작성하세요.
page1~page5 키를 반드시 모두 포함해야 합니다.

규칙:
- 책·책 표지 이미지 절대 금지
- 어둡고 긴장감 있는 분위기 (dark, dramatic, cinematic)
- 인물보다 상황·상징·분위기 중심 (symbolic, abstract)
- 5페이지는 여운·열린 결말 분위기 (contemplative, mysterious, open-ended)
- 텍스트·글자 없음 (no text)
- Instagram 1:1 정사각형 최적화
- 영어, 40단어 이내

JSON (page1~page5 모두 필수): {"page1":"prompt","page2":"prompt","page3":"prompt","page4":"prompt","page5":"prompt"}`,
  });

  const prompts = extractJson(text);

  // 5페이지 모두 존재하는지 확인 — 누락 시 폴백 프롬프트로 보완
  for (let i = 1; i <= 5; i++) {
    const key = `page${i}`;
    if (!prompts[key] || typeof prompts[key] !== 'string' || prompts[key].trim() === '') {
      prompts[key] = FALLBACK_IMAGE_PROMPTS[key];
    }
  }

  const suffix = ', dark cinematic dramatic atmosphere, no text, no books, high quality, 8k';
  const base = 'https://image.pollinations.ai/prompt/';

  // 페이지마다 다른 seed → 동일 요청 충돌·캐시 문제로 인한 로딩 실패 감소
  const images = {};
  for (const [page, prompt] of Object.entries(prompts)) {
    const seed = Math.floor(Math.random() * 900000) + 100000;
    images[page] = `${base}${encodeURIComponent(prompt + suffix)}?width=1080&height=1080&nologo=true&seed=${seed}`;
  }

  return { success: true, images, prompts };
}

async function handleGenerateCaption(env, body) {
  const { pages, bookInfo, dmKeyword } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  // 댓글 키워드: 2자 이하, 특수기호 없는 순수 한글/영문
  let kw = (dmKeyword || bookInfo.category || '독서').replace(/[^가-힣a-zA-Z0-9]/g, '').slice(0, 2) || '책';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 512,
    system: '당신은 인스타그램 마케터입니다. 댓글 유도 중심의 짧고 강렬한 캡션을 작성합니다. 책 제목을 절대 노출하지 않고, 노골적 판매 표현을 피합니다. 반드시 JSON만 응답합니다.',
    user: `책 카테고리: ${bookInfo.category || '자기계발'}
핵심 메시지: ${bookInfo.coreMessage || ''}
캐럿셀 첫 줄 훅: ${pages.page1?.headline || ''}
댓글 키워드: "${kw}" (방문자가 댓글에 이 키워드를 남기면 DM으로 책 정보와 구매링크를 자동 발송하는 시스템)

인스타그램 캡션을 작성하세요.

규칙:
- 첫 줄: 호기심/위기감 자극 단문 또는 질문 (책 제목 절대 노출 금지)
- 2~3줄: 캐럿셀 핵심만 초간결 요약 (반복 금지, 노골적 판매 금지)
- 마지막 줄: "댓글에 '${kw}'를 남겨주세요" 형태의 자연스러운 유도 문구
- 해시태그: 정확히 3개 (카테고리 관련)
- 전체 5줄 이내, 짧고 강렬하게

JSON: {"caption":"첫줄\\n둘째줄\\n셋째줄\\n댓글유도줄","hashtags":["#tag1","#tag2","#tag3"],"commentKeyword":"${kw}"}`,
  });

  const result = extractJson(text);
  // 구형 dmKeyword 필드도 호환성 유지
  result.dmKeyword = result.commentKeyword || kw;
  return { success: true, ...result };
}

async function handleRegenerate(env, body) {
  const { bookInfo, previousPages, feedback, improvements } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'main'),
    system: `당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다.
핵심 규칙(절대 위반 금지):
1. 책 제목·저자명·구매 링크를 캐럿셀 본문 어디에도 절대 쓰지 않는다.
2. 각 페이지 텍스트는 최소한의 단어로 임팩트를 낸다 — 장황한 설명 금지.
3. 5페이지는 반문·열린 결말 구조 — 구매 유도나 직접 행동 지시 없이 독자에게 질문을 던진다.
반드시 JSON만 응답한다.`,
    user: `캐럿셀을 피드백에 맞게 개선하세요.
카테고리: ${bookInfo.category || '자기계발'}
핵심 메시지: ${bookInfo.coreMessage || ''}

이전 버전:
${JSON.stringify(previousPages, null, 2)}

피드백: ${feedback}
개선 요청: ${improvements.join(' / ')}

텍스트 길이 기준:
- 1페이지 headline: 40자 이내 완전한 문장(주어+상황+결과). 단어 조각 절대 금지. subtext 없음.
- 2~4페이지 headline: 18자 이내, body: 3~4줄(줄당 45자 이내). 구체적 수치·사례 포함.
- JSON 형식: {"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},...}

JSON:
{"page1":{"headline":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });
  return { success: true, pages: extractJson(text) };
}

// ===== Phase 5 준비: DM 자동 회신 내용 생성 =====
async function handleGenerateDmReply(env, body) {
  const { pages, bookInfo, affiliateLink } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 512,
    system: '당신은 인스타그램 DM 자동 회신 작성 전문가입니다. 댓글 키워드를 남긴 팔로워에게 보낼 DM을 씁니다. 따뜻하고 개인적인 톤, 노골적 판매 금지. 반드시 JSON만 응답합니다.',
    user: `책 제목: ${bookInfo.title}
저자: ${bookInfo.author}
카테고리: ${bookInfo.category || '자기계발'}
핵심 메시지: ${bookInfo.coreMessage || ''}

5페이지에서 독자에게 던진 반문: ${pages.page5?.cta || ''}
5페이지 마무리 문구: ${pages.page5?.linkText || ''}

어필리에이트 링크: ${affiliateLink || '(미입력)'}

댓글에 키워드를 남긴 팔로워에게 보낼 DM을 작성하세요.

구성:
1. 친근한 인사 (1줄)
2. 책 제목과 저자 자연스럽게 소개 (1줄)
3. 이 책이 답하는 핵심 질문·고민 (독자 공감 유도, 2줄 이내)
4. 5페이지 반문에 대한 제한적 힌트 (완전한 답은 절대 주지 말 것, 2줄 이내)
5. 어필리에이트 링크 안내 (자연스럽게, 없으면 "곧 공유드릴게요" 처리)
6. 따뜻한 마무리 (1줄)

JSON: {"dmText":"전체 DM 텍스트(줄바꿈은 \\n)"}`,
  });

  const result = extractJson(text);

  // KV에 DM 회신 저장 (키워드 기반, 7일 TTL) — Phase 5 댓글 자동 감지용
  if (env.PENDING_POSTS && body.commentKeyword) {
    const kw2 = String(body.commentKeyword).replace(/[^가-힣a-zA-Z0-9]/g, '').slice(0, 2);
    if (kw2) await env.PENDING_POSTS.put(`dm_reply_${kw2}`, result.dmText || '', { expirationTtl: 604800 });
  }

  return { success: true, ...result };
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

  // 텔레그램에 콜백 즉시 응답 (5초 내 필수)
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/answerCallbackQuery`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ callback_query_id: callbackId, text: '처리 중...' }),
  }).catch(() => {});

  const chatId = env.TELEGRAM_CHAT_ID;

  if (cbData === 'approve') {
    if (!env.PENDING_POSTS) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, 'KV 스토어가 설정되지 않았습니다. 관리자에게 문의해주세요.');
      return { ok: true };
    }
    const stateJson = await env.PENDING_POSTS.get('latest');
    if (!stateJson) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, '게시할 콘텐츠가 없습니다 (만료됐거나 취소됨). 웹에서 다시 생성해주세요.');
      return { ok: true };
    }
    const ps = JSON.parse(stateJson);
    try {
      const result = await handlePostInstagram(env, { images: ps.images, caption: ps.caption, hashtags: ps.hashtags });
      await env.PENDING_POSTS.delete('latest');
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
        `인스타그램 게시 완료!\n미디어 ID: ${result.mediaId}\n\n책: ${ps.bookInfo?.title || ''}`);
    } catch (err) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
        `인스타그램 게시 실패: ${err.message}\n\n웹에서 직접 게시해주세요: https://book-carousel.jtaechul.workers.dev/`);
    }
  } else if (cbData === 'cancel') {
    if (env.PENDING_POSTS) await env.PENDING_POSTS.delete('latest');
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId, '게시가 취소됐습니다.');
  } else if (cbData === 'modify') {
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chatId,
      '웹에서 수정 후 다시 발송해주세요:\nhttps://book-carousel.jtaechul.workers.dev/');
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

// ===== 메인 라우터 =====
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    if (url.pathname.startsWith('/api/')) {
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
        else if (url.pathname === '/api/suggest') result = await handleSuggest(env, body);
        else if (url.pathname === '/api/analyze') result = await handleAnalyze(env, body);
        else if (url.pathname === '/api/generate') result = await handleGenerate(env, body);
        else if (url.pathname === '/api/generate-images') result = await handleGenerateImages(env, body);
        else if (url.pathname === '/api/generate-caption') result = await handleGenerateCaption(env, body);
        else if (url.pathname === '/api/validate') result = await handleValidate(env, body);
        else if (url.pathname === '/api/regenerate') result = await handleRegenerate(env, body);
        else if (url.pathname === '/api/send-telegram') result = await handleSendTelegram(env, body);
        else if (url.pathname === '/api/generate-dm-reply') result = await handleGenerateDmReply(env, body);
        else if (url.pathname === '/api/post-instagram') result = await handlePostInstagram(env, body);
        else if (url.pathname === '/api/telegram-webhook') result = await handleTelegramWebhook(env, body);
        else if (url.pathname === '/api/setup-webhook') result = await handleSetupWebhook(env);
        else return json({ error: '없는 경로입니다.' }, 404);

        return json(result);
      } catch (err) {
        return json({ error: err.message }, 500);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
