#!/usr/bin/env node
// AI 문항 초안 생성 (관리자 화면의 '문제 만들어줘' 주문을 받아 실행)
//
// 어디서 도는가: 깃허브 작업실(generate-questions.yml)에서만 돈다. 앱 서버(Workers)에는
// AI 열쇠를 두지 않는다 — 운영 중 외부 호출 0회 원칙 그대로다. 음원·사진 배치와 같은 자리.
//
// 무엇을 하는가: 초안을 받아 **저작 규칙집(worker/authoring.mjs)으로 걸러**, 통과한 것만
// content/questions/<파트>.json 에 status:"draft" 로 붙인다. 준비 중이므로 사람이 관리자
// 화면에서 보고 '출제 시작'을 눌러야 아이에게 나간다. 규칙에 걸린 초안은 버리고 이유를 찍는다.
//
// 사용: node tools/gen-questions.mjs --request requests/gen-....json   (관리자 화면이 넣은 주문서)
//   또는 node tools/gen-questions.mjs --part R3 --count 5 [--tag RS.infer]
//                                                          [--difficulty 3] [--note "..."]
// 열쇠는 둘 중 아무거나: ANTHROPIC_API_KEY(권장) 또는 GEMINI_API_KEY.
// 둘 다 있으면 Anthropic 을 쓴다. GEN_ENGINE=gemini 로 강제할 수 있다.

import Anthropic from '@anthropic-ai/sdk';
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PARTS, PART_LIST, PART_KO, PART_FORM, CHOICES_BY_PART, ACCENTS,
  EXPLANATION_MAX, WHY_NOT_MAX, KEY_EXPR_KO_MAX, HARD_TERMS,
  makeUlid, validateItem, MISS_KO,
} from '../worker/authoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');

const arg = (name, dflt = '') => {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
};
// 주문은 두 갈래로 들어온다.
//  (1) --request 주문서 파일 — 관리자 화면이 커밋한 것을 워크플로가 넘겨준다(정상 경로)
//  (2) 낱개 인자 — Actions 화면에서 손으로 돌릴 때
// 주문서 방식을 쓰는 이유: workflow_dispatch 는 워크플로 파일이 기본 브랜치에 있어야
// GitHub 이 인식하는데, 이 저장소의 배치들은 전부 작업 브랜치에서만 산다.
// 그래서 저장소가 이미 쓰고 있는 방식(주문서 푸시 → push 트리거)에 맞춘다.
const reqPath = arg('request');
let order = {};
if (reqPath) {
  try { order = JSON.parse(readFileSync(reqPath, 'utf8')); }
  catch (e) { console.error(`주문서를 읽지 못했습니다 (${reqPath}): ${e.message}`); process.exit(1); }
}
const pick = (name, dflt = '') => (order[name] ?? '') || arg(name, dflt);
const PART = pick('part');
const COUNT = Math.max(1, Math.min(20, Number(pick('count', '5')) || 5));
const TAG = pick('tag');
const DIFF = String(pick('difficulty') ?? '');
const NOTE = pick('note');

if (!PART_LIST.includes(PART)) {
  console.error(`--part 는 ${PART_LIST.join(', ')} 중 하나여야 합니다 (받은 값: ${PART || '없음'})`);
  process.exit(1);
}
// 엔진은 있는 열쇠로 알아서 고른다 — 운영자가 둘 중 아무거나 등록해 두면 돌아간다.
// Anthropic 을 먼저 보는 이유: 규칙이 까다로워(해설 100자·어려운 용어 금지·근거 원문 그대로)
// 통과율이 결과물의 양을 좌우하고, 지금까지 그쪽 통과율이 높았다.
// 음원 배치가 Gemini 무료 등급에서 느렸던 것은 요청이 수백 개였기 때문이고,
// 문항 생성은 주문당 요청 1번이라 분당 제한에 걸리지 않는다.
const ANTHROPIC_KEY = process.env.ANTHROPIC_API_KEY || '';
const GEMINI_KEY = process.env.GEMINI_API_KEY_JUMPLISH || process.env.GEMINI_API_KEY || '';
const ENGINE = process.env.GEN_ENGINE
  || (ANTHROPIC_KEY ? 'anthropic' : GEMINI_KEY ? 'gemini' : '');
if (!ENGINE) {
  console.error('AI 열쇠가 없습니다. Repository secrets 에 다음 중 하나를 등록해 주세요:');
  console.error('  ANTHROPIC_API_KEY  (권장 — 규칙 통과율이 높습니다)');
  console.error('  GEMINI_API_KEY     (이미 음원 제작에 쓰고 계시면 그대로 쓸 수 있습니다)');
  console.error('  ※ Environment secrets 에 넣으면 이 작업에서 보이지 않습니다.');
  process.exit(1);
}
if (ENGINE === 'anthropic' && !ANTHROPIC_KEY) { console.error('ANTHROPIC_API_KEY 가 없습니다'); process.exit(1); }
if (ENGINE === 'gemini' && !GEMINI_KEY) { console.error('GEMINI_API_KEY 가 없습니다'); process.exit(1); }

const tags = JSON.parse(readFileSync(join(CONTENT, 'tags.json'), 'utf8'));
const tagSection = Object.fromEntries(tags.map((t) => [t.code, t.section]));
const section = PARTS[PART];
const usable = tags.filter((t) => !t.code.startsWith('SEC.')
  && (t.section === 'ALL' || t.section === section));

const qFile = join(CONTENT, 'questions', `${PART}.json`);
const items = existsSync(qFile) ? JSON.parse(readFileSync(qFile, 'utf8')) : [];
// 이미 있는 문항 몇 개를 예시로 보여 준다 — 형식·말투·난이도를 글로 설명하는 것보다 정확하다.
const samples = items.slice(-3);

const form = PART_FORM[PART] === 'both' ? 'single' : PART_FORM[PART];
const isLC = section === 'LC';

const prompt = `당신은 초등 3학년~중학교 3학년 한국 학생을 위한 영어 문제(TOEIC Bridge 대비) 저작자입니다.
"${PART_KO[PART]}" 문항을 **${COUNT}개** 새로 만들어 주세요.

## 반드시 지킬 규칙
- 출력은 **JSON 배열 하나만**. 설명·인사말·코드펜스 없이 배열만 출력합니다.
- 각 원소는 아래 예시와 **완전히 같은 구조**입니다. tmp_id 는 넣지 마세요(시스템이 붙입니다).
- 보기(choices)는 정확히 ${CHOICES_BY_PART[PART]}개.
- 정답 위치를 고르게 섞으세요(한 자리에 몰리면 안 됩니다).
- explanation_ko(해설)는 ${EXPLANATION_MAX}자 이하, **아이 말로** 씁니다.
  다음 문법 용어는 절대 쓰지 마세요: ${HARD_TERMS.join(', ')}.
  예) "주어가 3인칭 단수라서" (X) → "My dog는 한 마리라서" (O)
- why_not: 오답 보기마다 ${WHY_NOT_MAX}자 이하 한 줄 이유. **정답 자리에는 넣지 않습니다.**
- miss_type: why_not 을 넣은 자리마다 하나씩. 다음 중에서만 고릅니다:
${Object.entries(MISS_KO).map(([k, v]) => `  ${k} = ${v}`).join('\n')}
- evidence: 정답의 근거가 되는 부분을 **원문에서 그대로 복사**합니다(철자·부호까지).
  ${isLC ? '들려줄 대본(script) 안에 있어야 합니다.' : '지문이나 문제 문장 안에 있어야 합니다.'}
- key_expr: 이 문제에서 챙겨 갈 표현 하나. ko 는 ${KEY_EXPR_KO_MAX}자 이하.
- **translation_ko (필수)**: 지문·문장의 한글 해석. 없으면 그 문항은 버려집니다.
  ${form === 'set' ? 'passage 안에 넣습니다(문항이 아니라 지문에 붙습니다).' : '문항 안에 넣습니다.'}
  · 빈칸 문제라면 **정답을 넣은 완성된 문장**을 해석합니다(빈칸을 그대로 두지 마세요).
  · 대화문은 화자 표시를 살립니다 — "W:" 는 "여:", "M:" 은 "남:", "N:" 은 "안내:".
  · 줄바꿈은 원문과 같은 자리에 둡니다.
  · 아이가 읽는 글이니 존댓말로 자연스럽게. 직역해서 어색한 문장은 뜻이 통하게 풀어 씁니다.
- tags: 아래 목록에서 1~3개만.
${usable.map((t) => `  ${t.code} = ${t.name_ko}`).join('\n')}
- difficulty_label: ${DIFF || '1~5 중 적절히 (쉬운 것 위주로 고르게)'}
${TAG ? `- **이번 주문은 "${TAG}" 개념 문항입니다.** 모든 문항의 tags 에 ${TAG} 를 넣으세요.` : ''}
${isLC ? `- 듣기이므로 발음(accent)은 ${ACCENTS.join('/')} 중 하나를 고르게 섞습니다.` : ''}
${form === 'set' ? '- 지문 묶음형입니다. passage 하나에 문항 2~3개를 답니다.' : ''}

## 소재 금지선 (가장 중요 — 하나라도 어기면 그 문항은 버려집니다)
아이가 푸는 문제입니다. **집집마다 생각이 다를 수 있는 소재는 아예 쓰지 마세요.**
낱말만 피하는 게 아니라 **이야기 자체를 다른 데서 가져오세요.**
- 정치·시사: 대통령·선거·정당·시위·파업·전쟁·군대·무기·남북관계·역사 갈등
- 종교: 기도·예배·특정 종교의 가르침이나 인물 (여행 중 들른 옛 절·성당이 배경인 정도는 괜찮습니다)
- 성·연애: 성적인 내용, 신체 묘사, 이성 교제
- 폭력·범죄: 때리기·괴롭힘·왕따·도둑질·죽음·자살
- 술·담배·도박·약물
- 차별·비하: 인종·국적·장애·외모·가난을 두고 편을 가르거나 놀리는 내용
- 실제 상표·회사 이름 (삼성·유튜브·스타벅스·나이키 등) — 일반 명사로 바꾸세요
- 그 밖에 **당신이 보기에 부모가 불편해할 만한 것은 전부** 쓰지 마세요.
  애매하면 쓰지 않는 쪽을 고릅니다 — 소재는 얼마든지 바꿀 수 있습니다.

## 안전하고 좋은 소재
학교 생활·급식·숙제·동아리 / 가족·형제·반려동물 / 친구와 놀기·생일 / 음식·요리 /
날씨·계절 / 여행·교통 / 운동·취미 / 도서관·병원·가게 같은 동네 장소

- 실제 기출을 베끼지 말고 100% 새로 씁니다.
${NOTE ? `\n## 추가 요청\n${NOTE}` : ''}

## 이 파일에 이미 있는 문항 (형식·말투를 그대로 따르세요)
${JSON.stringify(samples, null, 1)}`;

console.log(`주문: ${PART_KO[PART]} ${COUNT}문항${TAG ? ` · 개념 ${TAG}` : ''}${DIFF ? ` · 난이도 ${DIFF}` : ''}`);

// ── AI 호출 ──
// 어느 엔진이든 '초안 JSON 배열이 담긴 글'을 돌려주면 아래 검증이 똑같이 걸러 낸다.
// 그래서 엔진을 바꿔도 안전 규칙(민감 소재·해설 길이·근거)은 그대로 지켜진다.

async function askAnthropic() {
  // 출력이 길어(문항 여러 개 + 해설) 스트리밍으로 받아야 요청 시간 제한에 걸리지 않는다.
  // 초안 저작은 판단이 필요한 일이라 적응형 사고를 켠다.
  const client = new Anthropic({ apiKey: ANTHROPIC_KEY });
  try {
    const stream = client.messages.stream({
      model: process.env.GEN_MODEL || 'claude-opus-5',
      max_tokens: 64000,
      thinking: { type: 'adaptive' },
      messages: [{ role: 'user', content: prompt }],
    });
    const msg = await stream.finalMessage();
    if (msg.stop_reason === 'refusal') {
      console.error('AI가 이 주문을 거절했습니다. 주문 내용을 바꿔 다시 시도해 주세요.');
      process.exit(1);
    }
    return msg.content.filter((b) => b.type === 'text').map((b) => b.text).join('');
  } catch (e) {
    // 실패 종류를 나눠 알려 준다 — 열쇠 문제인지, 잠시 막힌 것인지에 따라 할 일이 다르다
    if (e instanceof Anthropic.AuthenticationError) console.error('ANTHROPIC_API_KEY 가 올바르지 않습니다');
    else if (e instanceof Anthropic.RateLimitError) console.error('요청이 몰렸습니다 — 잠시 뒤 다시 실행해 주세요');
    else if (e instanceof Anthropic.APIError) console.error(`AI 호출 실패 (${e.status}): ${e.message}`);
    else console.error(`AI 호출 실패: ${e.message}`);
    process.exit(1);
  }
}

async function askGemini() {
  // SDK 없이 REST 로 부른다 — 배치 도구라 의존성을 하나라도 덜 얹는 편이 낫고,
  // 음원 배치(tts-batch.mjs)도 같은 방식이라 저장소 안에서 하는 방법이 하나로 유지된다.
  const models = [process.env.GEN_MODEL || 'gemini-2.5-pro', 'gemini-2.5-flash'];
  let lastErr = '';
  for (const model of models) {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-goog-api-key': GEMINI_KEY },
      body: JSON.stringify({
        contents: [{ role: 'user', parts: [{ text: prompt }] }],
        // JSON 으로 달라고 못박으면 앞뒤에 말이 붙어 나오는 일이 줄어든다
        generationConfig: { responseMimeType: 'application/json', maxOutputTokens: 32000 },
      }),
    });
    if (res.ok) {
      const out = await res.json();
      const cand = out.candidates?.[0];
      if (cand?.finishReason === 'SAFETY' || cand?.finishReason === 'PROHIBITED_CONTENT') {
        console.error('AI가 이 주문을 거절했습니다. 주문 내용을 바꿔 다시 시도해 주세요.');
        process.exit(1);
      }
      const text = (cand?.content?.parts ?? []).map((p) => p.text ?? '').join('');
      if (text.trim()) { console.log(`엔진: gemini (${model})`); return text; }
      lastErr = `${model}: 빈 응답`;
      continue;
    }
    const body = (await res.text()).slice(0, 300);
    lastErr = `${model}: ${res.status} ${body}`;
    // 다음 후보로 넘어가는 건 '그 모델을 못 쓴다'고 할 때뿐이다.
    // 열쇠가 틀렸거나 한도를 넘은 경우는 모델을 바꿔도 똑같아서, 한 번 더 부르면
    // 시간만 쓰고 로그에는 엉뚱한 모델 이름이 남아 원인을 찾기 어려워진다.
    const modelProblem = /not found|not supported|is not available|unsupported|NOT_FOUND/i.test(body);
    if (!modelProblem) break;
  }
  console.error(`Gemini 호출 실패 — ${lastErr}`);
  if (/API_KEY|API key/i.test(lastErr)) console.error('GEMINI_API_KEY 가 올바른지 확인해 주세요.');
  process.exit(1);
}

if (ENGINE === 'anthropic') console.log('엔진: anthropic');
const text = ENGINE === 'anthropic' ? await askAnthropic() : await askGemini();

// 앞뒤에 말이 붙어 나와도 배열만 건져낸다
const start = text.indexOf('[');
const end = text.lastIndexOf(']');
if (start < 0 || end < 0) {
  console.error('AI 응답에서 JSON 배열을 찾지 못했습니다:\n' + text.slice(0, 600));
  process.exit(1);
}
let drafts;
try { drafts = JSON.parse(text.slice(start, end + 1)); }
catch (e) { console.error('AI 응답 JSON 을 읽지 못했습니다: ' + e.message); process.exit(1); }
if (!Array.isArray(drafts) || !drafts.length) { console.error('초안이 비었습니다'); process.exit(1); }

// ── 규칙집으로 거르기 ── 통과 못 한 초안은 버린다. 반쯤 맞는 문항을 사람이 고치는 것보다
// 다시 주문하는 편이 싸고, 무엇보다 잘못된 문항이 아이에게 갈 길을 아예 막는다.
const used = new Set(items.map((x) => x.tmp_id));
let seq = items.length + 1;
const nextTmp = () => {
  while (used.has(`${PART}-${String(seq).padStart(4, '0')}`)) seq += 1;
  const id = `${PART}-${String(seq).padStart(4, '0')}`;
  used.add(id);
  return id;
};

const accepted = [];
const rejected = [];
for (const d of drafts) {
  // 초안이 제 이름표·파트·상태를 지어 왔더라도 여기서 덮어쓴다.
  // 특히 status 는 언제나 draft — 사람이 확인하기 전에는 아이에게 나가지 않는다.
  const item = {
    type: d.type || form,
    ...d,
    tmp_id: nextTmp(),
    section, part: PART, status: 'draft',
  };
  const errs = validateItem(item, PART, tagSection);
  if (errs.length) rejected.push({ item, errs });
  else accepted.push(item);
}

console.log(`\n초안 ${drafts.length}개 → 통과 ${accepted.length}개 / 버림 ${rejected.length}개`);
for (const r of rejected) {
  const topic = r.errs.some((m) => m.includes('넣지 않는 소재'));
  console.log(`  버림 (${r.item.tmp_id})${topic ? ' ⚠ 소재 위반' : ''}:`);
  for (const m of r.errs) console.log(`    - ${m}`);
}
const topicN = rejected.filter((r) => r.errs.some((m) => m.includes('넣지 않는 소재'))).length;
if (topicN) {
  console.log(`\n⚠ 소재 금지선을 어긴 초안 ${topicN}개를 버렸습니다 — 프롬프트가 새면 여기서 걸립니다.`);
}
if (!accepted.length) {
  console.error('\n통과한 문항이 없어 아무것도 저장하지 않았습니다. 주문을 다시 넣어 주세요.');
  process.exit(1);
}

// ULID 매핑까지 같이 써 둔다 — 음원 배치가 러너에서 제 이름을 짓지 못하게(generate-tts.yml 검사)
const idmapPath = join(CONTENT, '.idmap.json');
const idmap = existsSync(idmapPath) ? JSON.parse(readFileSync(idmapPath, 'utf8')) : {};
const ulid = makeUlid();
for (const it of accepted) {
  const keys = it.type === 'set'
    ? [`p:${it.tmp_id}`, ...it.questions.map((_, i) => `q:${it.tmp_id}#${i + 1}`)]
    : [`q:${it.tmp_id}`];
  for (const k of keys) if (!idmap[k]) idmap[k] = ulid();
}

writeFileSync(qFile, `${JSON.stringify([...items, ...accepted], null, 2)}\n`);
writeFileSync(idmapPath, `${JSON.stringify(idmap, null, 2)}\n`);
console.log(`\n${PART}.json 에 ${accepted.length}개 추가 (준비 중 상태)`);
console.log(accepted.map((a) => `  ${a.tmp_id}`).join('\n'));
