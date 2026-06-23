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

function redirect(url) {
  return Response.redirect(url, 302);
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

// ===== KakaoTalk OAuth =====
async function getKakaoToken(env) {
  const stored = await env.TOKENS.get('kakao_tokens', { type: 'json' });
  if (!stored) return null;

  // 액세스 토큰이 만료됐으면 리프레시
  if (Date.now() > stored.expires_at) {
    const refreshed = await refreshKakaoToken(env, stored.refresh_token);
    return refreshed;
  }
  return stored;
}

async function refreshKakaoToken(env, refreshToken) {
  const res = await fetch('https://kauth.kakao.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'refresh_token',
      client_id: env.KAKAO_APP_KEY,
      refresh_token: refreshToken,
    }),
  });
  if (!res.ok) throw new Error('카카오 토큰 갱신 실패');
  const data = await res.json();
  const tokens = {
    access_token: data.access_token,
    refresh_token: data.refresh_token || refreshToken,
    expires_at: Date.now() + (data.expires_in - 60) * 1000,
  };
  await env.TOKENS.put('kakao_tokens', JSON.stringify(tokens));
  return tokens;
}

async function sendKakaoMessage(accessToken, text) {
  const template = {
    object_type: 'text',
    text: text.substring(0, 200),
    link: { web_url: 'https://kakao.com', mobile_web_url: 'https://kakao.com' },
  };
  const res = await fetch('https://kapi.kakao.com/v2/api/talk/memo/default/send', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: `template_object=${encodeURIComponent(JSON.stringify(template))}`,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(`카카오 발송 실패: ${err.msg || res.status}`);
  }
  return res.json();
}

// ===== 카카오 OAuth 핸들러 =====
async function handleKakaoAuthStart(env, requestUrl) {
  const workerUrl = `${requestUrl.protocol}//${requestUrl.host}`;
  const redirectUri = `${workerUrl}/auth/kakao/callback`;
  const authUrl = new URL('https://kauth.kakao.com/oauth/authorize');
  authUrl.searchParams.set('client_id', env.KAKAO_APP_KEY);
  authUrl.searchParams.set('redirect_uri', redirectUri);
  authUrl.searchParams.set('response_type', 'code');
  authUrl.searchParams.set('scope', 'talk_message');
  return redirect(authUrl.toString());
}

async function handleKakaoAuthCallback(env, requestUrl) {
  const code = requestUrl.searchParams.get('code');
  if (!code) {
    return new Response('인증 코드 없음', { status: 400 });
  }

  const workerUrl = `${requestUrl.protocol}//${requestUrl.host}`;
  const redirectUri = `${workerUrl}/auth/kakao/callback`;

  const res = await fetch('https://kauth.kakao.com/oauth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: env.KAKAO_APP_KEY,
      redirect_uri: redirectUri,
      code,
    }),
  });

  if (!res.ok) {
    return new Response('토큰 발급 실패', { status: 500 });
  }

  const data = await res.json();
  const tokens = {
    access_token: data.access_token,
    refresh_token: data.refresh_token,
    expires_at: Date.now() + (data.expires_in - 60) * 1000,
  };
  await env.TOKENS.put('kakao_tokens', JSON.stringify(tokens));

  // 연동 완료 후 메인 페이지로 이동
  return new Response(`
    <html><head><meta charset="UTF-8">
    <script>
      window.opener && window.opener.postMessage('kakao_auth_done', '*');
      setTimeout(() => window.close(), 1000);
    </script></head>
    <body style="font-family:sans-serif;text-align:center;padding:40px">
      <h2>카카오톡 연동 완료!</h2>
      <p>이 창은 자동으로 닫힙니다.</p>
    </body></html>
  `, { headers: { 'Content-Type': 'text/html;charset=UTF-8' } });
}

// ===== Claude 핸들러 =====
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

// ===== 카카오톡 발송 =====
async function handleSendKakao(env, body, requestUrl) {
  const tokenData = await getKakaoToken(env);
  if (!tokenData) {
    return { success: false, needAuth: true, message: '카카오톡 연동이 필요합니다.' };
  }

  const { pages, bookInfo } = body;
  const workerUrl = `${requestUrl.protocol}//${requestUrl.host}`;
  const PAGE_LABELS = ['훅', '문제', '심각성', '실마리', 'CTA'];

  const messages = [
    `[북 캐럿셀 미리보기]\n책: ${bookInfo.title}\n저자: ${bookInfo.author}\n카테고리: ${bookInfo.category || ''}\n\n5장 캐럿셀이 생성됐습니다.`,
    `[1/5 ${PAGE_LABELS[0]}]\n${pages.page1.headline}\n\n${pages.page1.subtext || ''}`,
    `[2/5 ${PAGE_LABELS[1]}]\n${pages.page2.headline}\n\n${pages.page2.body || ''}`,
    `[3/5 ${PAGE_LABELS[2]}]\n${pages.page3.headline}\n\n${pages.page3.body || ''}`,
    `[4/5 ${PAGE_LABELS[3]}]\n${pages.page4.headline}\n\n${pages.page4.body || ''}`,
    `[5/5 ${PAGE_LABELS[4]}]\n${pages.page5.cta}\n\n${pages.page5.linkText || ''}`,
    `승인/거절하려면 아래 링크로 이동:\n${workerUrl}`,
  ];

  for (const msg of messages) {
    await sendKakaoMessage(tokenData.access_token, msg);
    await new Promise(r => setTimeout(r, 300)); // 과도한 요청 방지
  }

  return { success: true, message: `카카오톡으로 ${messages.length}개 메시지를 보냈습니다.` };
}

// ===== 카카오 연동 상태 확인 =====
async function handleKakaoStatus(env) {
  const tokenData = await env.TOKENS.get('kakao_tokens', { type: 'json' });
  return { connected: !!tokenData };
}

// ===== 메인 라우터 =====
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: CORS });
    }

    // 카카오 OAuth 라우트
    if (url.pathname === '/auth/kakao') {
      return handleKakaoAuthStart(env, url);
    }
    if (url.pathname === '/auth/kakao/callback') {
      return handleKakaoAuthCallback(env, url);
    }

    // API 라우트
    if (url.pathname.startsWith('/api/')) {
      try {
        if (url.pathname === '/api/kakao-status' && request.method === 'GET') {
          return json(await handleKakaoStatus(env));
        }

        const body = request.method === 'POST' ? await request.json() : {};
        let result;

        if (url.pathname === '/api/generate') result = await handleGenerate(env, body);
        else if (url.pathname === '/api/validate') result = await handleValidate(env, body);
        else if (url.pathname === '/api/regenerate') result = await handleRegenerate(env, body);
        else if (url.pathname === '/api/send-kakao') result = await handleSendKakao(env, body, url);
        else return json({ error: '없는 경로입니다.' }, 404);

        return json(result);
      } catch (err) {
        return json({ error: err.message }, 500);
      }
    }

    return env.ASSETS.fetch(request);
  },
};
