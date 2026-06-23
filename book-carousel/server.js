require('dotenv').config();
const express = require('express');
const path = require('path');
const Anthropic = require('@anthropic-ai/sdk');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.json({ limit: '1mb' }));
app.use(express.static(__dirname));

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

function extractJson(text) {
  const match = text.match(/\{[\s\S]*\}/);
  if (!match) throw new Error('응답에서 JSON을 찾을 수 없습니다.');
  return JSON.parse(match[0]);
}

// 5페이지 캐럿셀 텍스트 생성
app.post('/api/generate', async (req, res) => {
  const { title, author, year, coreMessage, targetAudience, category } = req.body;

  if (!title || !author || !coreMessage) {
    return res.status(400).json({ error: '제목, 저자, 핵심 메시지는 필수입니다.' });
  }

  try {
    const message = await anthropic.messages.create({
      model: 'claude-opus-4-8',
      max_tokens: 2048,
      system: '당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다. 공포감·호기심·위기감을 자극해 저장·공유율을 높이는 콘텐츠를 씁니다. 반드시 JSON만 응답합니다.',
      messages: [{
        role: 'user',
        content: `다음 책으로 5페이지 인스타그램 캐럿셀을 작성하세요.

책: ${title} / 저자: ${author}${year ? ` (${year})` : ''}
핵심 메시지: ${coreMessage}
${targetAudience ? `대상: ${targetAudience}` : ''}
카테고리: ${category || '자기계발'}

페이지 가이드:
1페이지(훅): 공포·위기감·호기심 강한 후크. "당신이 ○○를 모른다면..." 형태로 독자가 "나 얘기다"라고 느껴야 함. headline(1~2줄 강렬한 문구) + subtext(보조 1줄)
2페이지(문제): 구체적 수치·사례로 문제 상황 제시. "왜 이런 일이?" 의문 유발. headline + body(3~4줄)
3페이지(심각성): 역사적 배경·통계. "대부분은 모른다" 충격 사실. headline + body(3~4줄)
4페이지(실마리): 책의 해결 방향 암시(완전한 답 X, 궁금증 최고조 유지). headline + body(3~4줄)
5페이지(CTA): 자연스럽고 우회적인 행동 유도. cta(2~3줄) + linkText("이 책 자세히 보기" 형태)

JSON 형식으로만 응답:
{"page1":{"headline":"...","subtext":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
      }]
    });

    const pages = extractJson(message.content[0].text);
    res.json({ success: true, pages });

  } catch (err) {
    console.error('[generate]', err.message);
    res.status(500).json({ error: err.message || '생성 중 오류가 발생했습니다.' });
  }
});

// 콘텐츠 품질 검증
app.post('/api/validate', async (req, res) => {
  const { pages, bookInfo } = req.body;

  try {
    const message = await anthropic.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 1024,
      system: '당신은 소셜미디어 콘텐츠 전문 편집장입니다. 인스타그램 캐럿셀 품질을 엄격히 평가합니다. 반드시 JSON만 응답합니다.',
      messages: [{
        role: 'user',
        content: `책 "${bookInfo.title}" (${bookInfo.author}) 캐럿셀을 평가하세요.

내용:
${JSON.stringify(pages, null, 2)}

평가기준(100점 만점):
- consistency(일관성 · 페이지간 논리 연결): 0~20
- curiosity(호기심 유발 · 계속 넘기고 싶은 정도): 0~25
- clarity(텍스트 명확성 · 가독성): 0~20
- cta(CTA 자연스러움 · 노골적 광고 아닌 정도): 0~20
- overall(전반적 완성도 · 바로 게시 가능한 수준): 0~15

JSON 형식으로만 응답:
{"totalScore":85,"scores":{"consistency":18,"curiosity":22,"clarity":17,"cta":16,"overall":12},"feedback":"전반적 평가 의견 2~3문장","improvements":["개선점1","개선점2","개선점3"],"approved":true}
approved는 totalScore가 70 이상이면 true, 미만이면 false.`
      }]
    });

    const result = extractJson(message.content[0].text);
    res.json({ success: true, ...result });

  } catch (err) {
    console.error('[validate]', err.message);
    res.status(500).json({ error: err.message || '검증 중 오류가 발생했습니다.' });
  }
});

// 피드백 반영 재생성
app.post('/api/regenerate', async (req, res) => {
  const { bookInfo, previousPages, feedback, improvements } = req.body;

  try {
    const message = await anthropic.messages.create({
      model: 'claude-opus-4-8',
      max_tokens: 2048,
      system: '당신은 인스타그램 책 리뷰 카드뉴스 전문 카피라이터입니다. 편집장 피드백을 반영해 더 나은 버전을 씁니다. 반드시 JSON만 응답합니다.',
      messages: [{
        role: 'user',
        content: `책 "${bookInfo.title}" (${bookInfo.author}) 캐럿셀을 피드백 반영해 개선하세요.

이전 버전:
${JSON.stringify(previousPages, null, 2)}

편집장 피드백: ${feedback}
개선 요청: ${improvements.join(' / ')}

같은 JSON 형식으로 개선된 버전 작성:
{"page1":{"headline":"...","subtext":"..."},"page2":{"headline":"...","body":"..."},"page3":{"headline":"...","body":"..."},"page4":{"headline":"...","body":"..."},"page5":{"cta":"...","linkText":"..."}}`
      }]
    });

    const pages = extractJson(message.content[0].text);
    res.json({ success: true, pages });

  } catch (err) {
    console.error('[regenerate]', err.message);
    res.status(500).json({ error: err.message || '재생성 중 오류가 발생했습니다.' });
  }
});

// 카카오톡 발송 (Phase 4 준비 중)
app.post('/api/send-kakao', async (req, res) => {
  res.json({
    success: false,
    stub: true,
    message: '카카오톡 연동은 Phase 4에서 구현됩니다. 현재는 텍스트를 복사해 사용해주세요.'
  });
});

app.listen(PORT, () => {
  console.log(`\n북 캐럿셀 생성기 실행 중: http://localhost:${PORT}\n`);
  if (!process.env.ANTHROPIC_API_KEY) {
    console.warn('주의: ANTHROPIC_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.\n');
  }
});
