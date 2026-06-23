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

async function listModelIds(apiKey) {
  const res = await fetch('https://api.anthropic.com/v1/models?limit=100', {
    headers: { 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.data || []).map(m => m.id);
}

// 모델을 실제로 호출해 사용 가능 여부 확인 (200이면 사용 가능)
async function probeModel(apiKey, model) {
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' },
    body: JSON.stringify({ model, max_tokens: 1, messages: [{ role: 'user', content: 'hi' }] }),
  });
  return res.status;
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

  const ids = await listModelIds(apiKey);
  const probed = {}; // model -> status (디버깅용)

  // main: sonnet 우선(품질/비용 균형) → opus → 기타
  const mainOrder = orderCandidates(ids, ['sonnet-4', 'sonnet', 'opus-4', 'opus', 'haiku']);
  // light: haiku 우선 → sonnet
  const lightOrder = orderCandidates(ids, ['haiku-4', 'haiku', 'sonnet-4', 'sonnet']);

  const firstUsable = async (order) => {
    for (const m of order) {
      if (probed[m] === undefined) probed[m] = await probeModel(apiKey, m);
      if (probed[m] === 200) return m;
    }
    return null;
  };

  const main = await firstUsable(mainOrder);
  const light = (await firstUsable(lightOrder)) || main;

  // 호출 가능한 모델이 하나도 없으면 캐시하지 않고 진단 정보와 함께 실패 표시
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

async function handleSendTelegram(env, body) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error('TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 설정되지 않았습니다.');
  }

  const { pages, bookInfo, caption, hashtags, dmKeyword } = body;
  const PAGE_LABELS = ['훅', '문제', '심각성', '실마리', 'CTA'];

  const captionBlock = caption
    ? `\n\n[캡션]\n${caption}\n${(hashtags || []).join(' ')}${dmKeyword ? `\n\nDM 키워드: '${dmKeyword}'` : ''}`
    : '';

  const messages = [
    `[북 캐럿셀 미리보기]\n책: ${bookInfo.title}\n저자: ${bookInfo.author}\n카테고리: ${bookInfo.category || ''}${captionBlock}`,
    `[1/5 ${PAGE_LABELS[0]}]\n${pages.page1.headline}\n\n${pages.page1.subtext || ''}`,
    `[2/5 ${PAGE_LABELS[1]}]\n${pages.page2.headline}\n\n${pages.page2.body || ''}`,
    `[3/5 ${PAGE_LABELS[2]}]\n${pages.page3.headline}\n\n${pages.page3.body || ''}`,
    `[4/5 ${PAGE_LABELS[3]}]\n${pages.page4.headline}\n\n${pages.page4.body || ''}`,
    `[5/5 ${PAGE_LABELS[4]}]\n${pages.page5.cta}\n\n${pages.page5.linkText || ''}`,
  ];

  for (const msg of messages) {
    await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, msg);
    await new Promise(r => setTimeout(r, 200));
  }

  return { success: true, message: `텔레그램으로 ${messages.length}개 메시지를 보냈습니다.` };
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

페이지 가이드 (텍스트 길이 엄수):
1페이지(훅): FOMO·공포·위기감 후크. 추상적 단어 조각이 아닌 '주어+상황+구체적 결과'를 담은 완전한 문장으로 쓴다.
  - headline: 30자 이내 완전한 문장. 예시 스타일: "지금 이 순간에도 당신의 뇌는 몸보다 먼저 죽어가고 있다" / "한국인 3명 중 1명은 이미 부채 함정에 빠졌다는 사실을 아는가" — 막연한 단어 나열(예: '뇌가 먼저 죽어간다') 절대 금지.
  - subtext: 불안·호기심을 증폭하는 보조 문장 1줄 (25자 이내)
2페이지(문제): 구체적 수치·현실 사례로 문제 제시.
  - headline: 15자 이내
  - body: 2줄 이내, 한 줄 40자 이내
3페이지(심각성): 충격 사실·통계. "대부분은 모른다" 접근.
  - headline: 15자 이내
  - body: 2줄 이내, 한 줄 40자 이내
4페이지(실마리): 해결의 단서만 살짝 암시 — 완전한 답 절대 금지.
  - headline: 15자 이내
  - body: 2줄 이내, 한 줄 40자 이내
5페이지(반문·열린 결말): 구매 유도나 책 이름 없이, 독자 스스로 생각하게 만드는 반문.
  - cta: "당신은 어떻게 할 것인가?" 형태의 열린 질문 2줄 이내
  - linkText: "지금 당신의 선택이 미래를 바꾼다" 같은 여운 있는 한 줄

JSON:
{"page1":{"headline":"...","subtext":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
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

async function handleGenerateImages(env, body) {
  const { pages, bookInfo } = body;
  if (!pages || !bookInfo) throw new Error('캐럿셀 데이터가 필요합니다.');

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 600,
    system: '당신은 AI 이미지 프롬프트 전문가입니다. 인스타그램 카드뉴스용 드라마틱한 일러스트 프롬프트를 영어로 작성합니다. 반드시 JSON만 응답합니다.',
    user: `책 카테고리: ${bookInfo.category || '자기계발'}

각 페이지 핵심 메시지:
1페이지(훅): ${pages.page1?.headline || ''}
2페이지(문제): ${pages.page2?.headline || ''}
3페이지(심각성): ${pages.page3?.headline || ''}
4페이지(실마리): ${pages.page4?.headline || ''}

위 내용에 맞는 드라마틱한 일러스트 프롬프트 4개를 작성하세요.

규칙:
- 책·책 표지 이미지 절대 금지
- 어둡고 긴장감 있는 분위기 (dark, dramatic, cinematic)
- 인물보다 상황·상징·분위기 중심 (symbolic, abstract)
- 텍스트·글자 없음 (no text)
- Instagram 1:1 정사각형 최적화
- 영어, 40단어 이내

JSON: {"page1":"prompt","page2":"prompt","page3":"prompt","page4":"prompt"}`,
  });

  const prompts = extractJson(text);
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

  const kw = dmKeyword || bookInfo.category || '키워드';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: await getModel(env.ANTHROPIC_API_KEY, 'light'),
    max_tokens: 512,
    system: '당신은 인스타그램 마케터입니다. DM 유도 중심의 짧고 강렬한 캡션을 작성합니다. 책 제목을 절대 노출하지 않고, 노골적 판매 표현을 피합니다. 반드시 JSON만 응답합니다.',
    user: `책 카테고리: ${bookInfo.category || '자기계발'}
핵심 메시지: ${bookInfo.coreMessage || ''}
캐럿셀 첫 줄 훅: ${pages.page1?.headline || ''}
DM 키워드: "${kw}"

인스타그램 캡션을 작성하세요.

규칙:
- 첫 줄: 호기심/위기감 자극 단문 또는 질문 (책 제목 절대 노출 금지)
- 2~3줄: 캐럿셀 핵심만 초간결 요약 (반복 금지, 노골적 판매 금지)
- 마지막 줄: "DM으로 '${kw}'를 보내주세요" 형태의 자연스러운 유도 문구
- 해시태그: 정확히 3개 (카테고리 관련)
- 전체 5줄 이내, 짧고 강렬하게

JSON: {"caption":"첫줄\\n둘째줄\\n셋째줄\\nDM유도줄","hashtags":["#tag1","#tag2","#tag3"],"dmKeyword":"${kw}"}`,
  });

  return { success: true, ...extractJson(text) };
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
- 1페이지 headline: 30자 이내 완전한 문장 (주어+상황+구체적 결과). 추상적 단어 조각 금지. 예) "지금 이 순간에도 당신의 뇌는 몸보다 먼저 죽어가고 있다"
- 2~4페이지 headline: 15자 이내, body: 2줄 이내(줄당 40자 이내)
- subtext: 25자 이내

JSON:
{"page1":{"headline":"...","subtext":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });
  return { success: true, pages: extractJson(text) };
}

// ===== 메인 라우터 =====
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    if (url.pathname.startsWith('/api/')) {
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
        else return json({ error: '없는 경로입니다.' }, 404);

        return json(result);
      } catch (err) {
        return json({ error: err.message }, 500);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
