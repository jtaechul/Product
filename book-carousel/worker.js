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
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.error?.message || `Claude API 오류 ${res.status}`);
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

  const { pages, bookInfo } = body;
  const PAGE_LABELS = ['훅', '문제', '심각성', '실마리', 'CTA'];

  const messages = [
    `[북 캐럿셀 미리보기]\n책: ${bookInfo.title}\n저자: ${bookInfo.author}\n카테고리: ${bookInfo.category || ''}\n\n5장 캐럿셀이 생성됐습니다.`,
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
  const { category, issue } = body;
  const topic = issue || category || '자기계발';

  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: 'claude-opus-4-8',
    system: '당신은 도서 큐레이터입니다. 현재 베스트셀러 트렌드와 사회적 이슈를 바탕으로 실제 존재하는 책을 추천합니다. 반드시 JSON만 응답합니다.',
    user: `주제: "${topic}"

이 주제와 관련해 현재 주목받는 실제 책 4권을 추천하세요.
베스트셀러이거나 최신 사회 이슈(경제 위기, AI, 부동산, 건강, 인간관계 등)에 인사이트를 주는 책 위주로 선정하세요.

각 책에 대해:
- title: 책 제목 (실제 출판된 책)
- author: 저자명
- year: 출판연도
- category: 카테고리
- coreMessage: 이 책의 핵심 메시지 (1~2문장)
- targetAudience: 주요 대상 독자층 (1문장)
- reason: 지금 이 책을 읽어야 하는 이유 (1문장, 사회 트렌드/이슈 연결)

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
    model: 'claude-sonnet-4-6',
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
    model: 'claude-opus-4-8',
    system: '당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다. 공포감·호기심·위기감을 자극해 저장·공유율을 높이는 콘텐츠를 씁니다. 반드시 JSON만 응답합니다.',
    user: `다음 책으로 5페이지 인스타그램 캐럿셀을 작성하세요.

책: ${title} / 저자: ${author}${year ? ` (${year})` : ''}
핵심 메시지: ${coreMessage}
${targetAudience ? `대상: ${targetAudience}` : ''}
카테고리: ${category || '자기계발'}

페이지 가이드:
1페이지(훅): 공포·위기감·호기심 강한 후크. "당신이 ○○를 모른다면..." 형태. headline(1~2줄) + subtext(보조 1줄)
2페이지(문제): 구체적 수치·사례로 문제 제시. headline + body(3~4줄)
3페이지(심각성): 통계·충격 사실. "대부분은 모른다" 접근. headline + body(3~4줄)
4페이지(실마리): 책의 해결 방향 암시(완전한 답 X). headline + body(3~4줄)
5페이지(CTA): 자연스러운 행동 유도. cta(2~3줄) + linkText

JSON 형식:
{"page1":{"headline":"...","subtext":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
  });

  return { success: true, pages: extractJson(text) };
}

async function handleValidate(env, body) {
  const { pages, bookInfo } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: 'claude-sonnet-4-6',
    max_tokens: 1024,
    system: '당신은 소셜미디어 콘텐츠 전문 편집장입니다. 반드시 JSON만 응답합니다.',
    user: `책 "${bookInfo.title}" (${bookInfo.author}) 캐럿셀을 평가하세요.

${JSON.stringify(pages, null, 2)}

평가기준(100점 만점):
- consistency(일관성): 0~20
- curiosity(호기심 유발): 0~25
- clarity(가독성): 0~20
- cta(CTA 자연스러움): 0~20
- overall(완성도): 0~15

JSON: {"totalScore":85,"scores":{"consistency":18,"curiosity":22,"clarity":17,"cta":16,"overall":12},"feedback":"평가 2~3문장","improvements":["개선1","개선2","개선3"],"approved":true}
approved는 totalScore>=70이면 true.`
  });
  return { success: true, ...extractJson(text) };
}

async function handleRegenerate(env, body) {
  const { bookInfo, previousPages, feedback, improvements } = body;
  const text = await callClaude(env.ANTHROPIC_API_KEY, {
    model: 'claude-opus-4-8',
    system: '당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다. 피드백 반영해 개선합니다. 반드시 JSON만 응답합니다.',
    user: `책 "${bookInfo.title}" (${bookInfo.author}) 캐럿셀을 개선하세요.

이전 버전:
${JSON.stringify(previousPages, null, 2)}

피드백: ${feedback}
개선 요청: ${improvements.join(' / ')}

JSON 형식:
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

        if (url.pathname === '/api/suggest') result = await handleSuggest(env, body);
        else if (url.pathname === '/api/analyze') result = await handleAnalyze(env, body);
        else if (url.pathname === '/api/generate') result = await handleGenerate(env, body);
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
