#!/usr/bin/env node
// 점프리시 콘텐츠 임포트 도구 (docs/content-pipeline.md 7절)
// content/*.json 검증 → tmp_id↔ULID 매핑(멱등) → tools/out/seed.sql 생성
// 사용: node tools/import.mjs [--check]   (--check: 검증만 하고 SQL 미생성)
// 주의: 재실행해도 같은 ULID를 재사용(멱등 upsert), rating·풀이 통계는 덮어쓰지 않는다.

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
// 검사 규칙·ULID는 관리자 저작 화면과 같은 자를 쓴다 (worker/authoring.mjs).
// 규칙을 두 벌 두면 화면은 통과시켰는데 여기서 막히는 문항이 생긴다.
import {
  PARTS, ACCENTS, RATING_BY_LABEL, CHOICES_BY_PART, HARD_TERMS,
  EXPLANATION_MAX, WHY_NOT_MAX, KEY_EXPR_KO_MAX,
  makeUlid, validateQuestionCore,
} from '../worker/authoring.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT_DIR = join(ROOT, 'tools', 'out');
const IDMAP_PATH = join(CONTENT, '.idmap.json');
const CHECK_ONLY = process.argv.includes('--check');



// 실수 유형 — 오답마다 "무슨 실수인지" 딱지 하나. 이유 문장은 읽을 수만 있고 셀 수 없어서,
// "이 아이가 이 실수를 몇 번 했나"에 답하려면 분류가 필요하다.
// 처방이 갈리는 지점으로 나눴다 (예: 낱말 뜻을 모르는 것과 문법 단서를 놓친 것은 다른 처방).

// ULID 생성기는 authoring.mjs 것을 쓴다 (관리자 저작 화면과 같은 형식)
const ulid = makeUlid();

// ---------- 유틸 ----------
const errors = [];
const warns = [];
const err = (m) => errors.push(m);
const warn = (m) => warns.push(m);
const q = (v) => (v === null || v === undefined) ? 'NULL' : `'${String(v).replace(/'/g, "''")}'`;
const readJson = (p) => JSON.parse(readFileSync(p, 'utf8'));

// ---------- 입력 로드 ----------
const tags = readJson(join(CONTENT, 'tags.json'));
const badges = readJson(join(CONTENT, 'badges.json'));
const tagSection = Object.fromEntries(tags.map((t) => [t.code, t.section]));

const qDir = join(CONTENT, 'questions');
const files = existsSync(qDir) ? readdirSync(qDir).filter((f) => f.endsWith('.json')).sort() : [];
if (files.length === 0) { console.error('content/questions/*.json 이 없습니다.'); process.exit(1); }

const idmap = existsSync(IDMAP_PATH) ? readJson(IDMAP_PATH) : {};
const takeId = (key) => (idmap[key] ||= ulid());

// 음원: 커밋된 public/audio 파일 존재 기준으로 채운다.
// (tts-batch의 manifest는 tools/out/ 소속이라 gitignore — 배포 러너엔 없다.
//  manifest에 의존하면 원격 seed의 audio_url이 전부 NULL이 되는 사고가 났다.)
const R2_BASE = (process.env.R2_PUBLIC_BASE || '').replace(/\/$/, '');
const audioUrlFor = (kind, id) => {
  const rel = `audio/${kind}/${id}.mp3`;
  if (!existsSync(join(ROOT, 'public', rel))) return null;
  return R2_BASE ? `${R2_BASE}/${rel}` : `/${rel}`;
};

// ⚠ 음원·사진 없는 문항은 절대 내보내지 않는다.
//
// 실제로 사고가 났다: 듣기 문항 36개를 새로 쓰고 음원(배치 TTS)을 만들기 전에 배포했더니,
// 소리가 나지 않는 듣기 문항이 아이들에게 그대로 출제됐다. 문항이 없는 것보다 나쁘다
// — 아이는 자기가 뭘 잘못한 줄 안다.
//
// 그래서 미디어가 없으면 status를 draft 로 내린다. 원고는 미리 써 두되, 음원·사진이
// 만들어져 public/ 에 들어온 다음에야 저절로 active 가 된다.
function gateOnMedia(ctx, part, status, audioUrl, imageUrls) {
  if (status !== 'active') return status;
  const isLC = PARTS[part] === 'LC';
  if (isLC && !audioUrl) {
    warn(`${ctx}: 음원이 아직 없어 draft로 내림 (tts-batch 실행 후 다시 import 하면 active)`);
    return 'draft';
  }
  if (part === 'L1' && !imageUrls) {
    warn(`${ctx}: 보기 사진 4컷이 아직 없어 draft로 내림 (img-batch 실행 후 다시 import)`);
    return 'draft';
  }
  return status;
}

// ── L1: 읽어 주는 문장이 정답 사진에 실제로 있는 것만 말하는지 ──
//
// 문장을 먼저 쓰고 그에 맞는 사진을 찾으면, 사진이 문장을 다 담지 못하는 일이 생긴다.
// 2026-08-12에 20문항 중 11개가 그랬다 — "두 아이가 모래성을 만든다"인데 사진엔 모래성만
// 있고, "남자아이가 오리에게 먹이를 준다"인데 사진 속은 여자아이였다.
//
// 사진의 태그는 대부분 사실을 말하고 있었다(그 사진 태그에 girl 이 있고 boy 는 없었다).
// 그래서 **문장이 말하는 사람과 사진 태그가 말하는 사람이 어긋나면 여기서 막는다.**
// 태그가 못 잡는 것(사람이 아예 안 찍혔는데 태그엔 children 이 있는 경우)은 사람이 봐야 한다.
const PERSON_WORDS = {
  boy: ['boy'], boys: ['boys', 'boy'],
  girl: ['girl'], girls: ['girls', 'girl'],
  man: ['man'], men: ['men', 'man'],
  woman: ['woman'], women: ['women', 'woman'],
  child: ['child', 'kid', 'boy', 'girl', 'toddler'],
  children: ['children', 'kids', 'boys', 'girls'],
};
function checkL1Sentence(ctx, script, tags) {
  if (!script || !tags) return;              // 사진을 아직 안 받았으면 검사할 게 없다
  const low = ` ${String(script).toLowerCase().replace(/[^a-z ]/g, ' ')} `;
  const tagLow = String(tags).toLowerCase();
  for (const [word, ok] of Object.entries(PERSON_WORDS)) {
    if (!low.includes(` ${word} `)) continue;
    if (ok.some((t) => tagLow.includes(t))) continue;
    warn(`${ctx}: 읽어 주는 문장은 "${word}"라고 하는데 정답 사진에는 그런 사람이 없습니다`
       + ` (사진 태그: ${tagLow.split(',').slice(0, 6).join(',')}…)`);
  }
  // 한 명이라고 했는데 사진 태그가 여럿을 가리키는 경우 (girls·children·kids)
  const singular = /\b(a|an)\s+(boy|girl|man|woman|child)\b/.test(low);
  if (singular && /\b(girls|boys|children|kids|sisters|brothers)\b/.test(tagLow)
      && !/\b(girl|boy|child|man|woman)\b/.test(tagLow.replace(/girls|boys|children|kids/g, ''))) {
    warn(`${ctx}: 문장은 한 명인데 사진에는 여러 명으로 보입니다 (태그에 girls·children 등)`);
  }
}

// L1 보기 4컷 (img-batch 산출: public/img/l1/{id}-{0..3}.jpg)
// 4컷이 모두 있을 때만 경로 배열(JSON)을 image_url에 싣는다 — 프런트가 그림 보기로 렌더.
// img-batch 가 남긴 사진 출처 기록 — 어떤 사진을 썼고 태그가 무엇인지 들어 있다
const l1PhotosPath = join(CONTENT, 'l1-photos.json');
const l1Photos = existsSync(l1PhotosPath) ? JSON.parse(readFileSync(l1PhotosPath, 'utf8')) : {};

const imageUrlsFor = (questionId) => {
  const paths = [0, 1, 2, 3].map((i) => `img/l1/${questionId}-${i}.jpg`);
  if (!paths.every((p) => existsSync(join(ROOT, 'public', p)))) return null;
  return JSON.stringify(paths.map((p) => `/${p}`));
};

// ---------- 검증 + 평탄화 ----------
const passages = [];  // {id, section, part, kind, content, image_url, audio_url, accent}
const questions = []; // {id, passage_id, section, part, stem, choices, answer_idx, ...}
const qTags = [];     // {question_id, tag_id}
const perPartAnswerPos = {};  // part -> [n0,n1,n2,n3]
const perPartDifficulty = {}; // part -> {label: n}
const seenTmp = new Set();

function checkQuestionCore(it, ctx, part, source = null) {
  // 규칙 검사는 관리자 저작 화면과 같은 자(worker/authoring.mjs)로 한다.
  // 여기서는 그 결과를 오류 목록에 옮기고, 파일 단위 통계만 따로 센다.
  for (const m of validateQuestionCore(it, ctx, part, source, tagSection)) errors.push(m);
  (perPartAnswerPos[part] ||= [0, 0, 0, 0])[it.answer_idx ?? 0]++;
  const d = (perPartDifficulty[part] ||= {});
  d[it.difficulty_label] = (d[it.difficulty_label] || 0) + 1;
}

function pushQuestion(part, tmpId, it, passageId, extra = {}) {
  const id = takeId(`q:${tmpId}`);
  questions.push({
    id, passage_id: passageId, section: PARTS[part], part,
    stem: it.stem ?? null, choices: JSON.stringify(it.choices),
    answer_idx: it.answer_idx, explanation_ko: it.explanation_ko,
    difficulty_label: it.difficulty_label,
    rating: RATING_BY_LABEL[it.difficulty_label],
    audio_url: extra.audio_url ?? null, image_url: extra.image_url ?? null,
    accent: extra.accent ?? null, script: extra.script ?? null,
    translation_ko: extra.translation_ko ?? it.translation_ko ?? null,
    evidence: it.evidence ?? null,
    why_not: it.why_not ? JSON.stringify(it.why_not) : null,
    miss_type: it.miss_type ? JSON.stringify(it.miss_type) : null,
    key_expr: it.key_expr ? JSON.stringify(it.key_expr) : null,
    status: extra.status ?? 'active',
  });
  for (const t of new Set(it.tags || [])) qTags.push({ question_id: id, tag_id: t });
}

for (const file of files) {
  const part = file.replace('.json', '');
  if (!PARTS[part]) { err(`${file}: 파일명은 파트 코드(L1~L4, R1~R3).json 이어야 합니다`); continue; }
  const items = readJson(join(qDir, file));
  if (!Array.isArray(items)) { err(`${file}: 최상위는 배열이어야 합니다`); continue; }

  for (const it of items) {
    const ctx = `${file}#${it.tmp_id || '?'}`;
    if (!it.tmp_id || seenTmp.has(it.tmp_id)) { err(`${ctx}: tmp_id 누락 또는 중복`); continue; }
    seenTmp.add(it.tmp_id);
    if (it.part !== part) err(`${ctx}: part(${it.part})가 파일(${part})과 다릅니다`);
    const status = it.status || 'active';
    if (!['draft', 'active', 'retired'].includes(status)) err(`${ctx}: status 오류`);

    if (it.type === 'single') {
      // 단독 문항의 "원문" = LC는 들려주는 문장, RC는 문제 문장 자체
      checkQuestionCore(it, ctx, part, it.tts_script || it.stem || null);
      if (part === 'L1' || part === 'L2') {
        if (typeof it.tts_script !== 'string' || !it.tts_script.trim()) err(`${ctx}: LC 단독 문항은 tts_script 필수`);
        if (!ACCENTS.includes(it.accent)) err(`${ctx}: LC 단독 문항은 accent(US/UK/AU) 필수`);
      }
      if (part === 'L1') {
        if (!Array.isArray(it.choice_image_prompts) || it.choice_image_prompts.length !== 4) {
          err(`${ctx}: L1은 choice_image_prompts 4개 필수`);
        }
        // 사진은 검색해서 가져온다 — 검색어와 함께 "반드시 있어야 할 말"을 못박아,
        // 엉뚱한 사진이 보기 자리에 들어가는 것을 배치 단계에서 막는다.
        const qs = it.choice_image_queries;
        if (!Array.isArray(qs) || qs.length !== 4) {
          err(`${ctx}: L1은 choice_image_queries 4개 필수 (사진 검색 조건)`);
        } else {
          qs.forEach((c, i) => {
            if (!c || typeof c.q !== 'string' || !c.q.trim()) err(`${ctx}: 보기${i} 검색어(q)가 없습니다`);
            if (!Array.isArray(c.need) || !c.need.length) err(`${ctx}: 보기${i} need는 1개 이상 필요합니다`);
            if (c.avoid !== undefined && !Array.isArray(c.avoid)) err(`${ctx}: 보기${i} avoid는 배열이어야 합니다`);
          });
        }
      }
      const qAudio = audioUrlFor('questions', takeId(`q:${it.tmp_id}`));
      const qImages = part === 'L1' ? imageUrlsFor(takeId(`q:${it.tmp_id}`)) : null;
      if (part === 'L1') {
        // 정답 컷의 태그와 읽어 주는 문장을 맞춰 본다
        const ansKey = `${takeId(`q:${it.tmp_id}`)}-${it.answer_idx}`;
        checkL1Sentence(ctx, it.tts_script, l1Photos[ansKey]?.tags);
      }
      pushQuestion(part, it.tmp_id, it, null, {
        accent: it.accent ?? null,
        status: gateOnMedia(ctx, part, status, qAudio, qImages),
        audio_url: qAudio,
        script: it.tts_script ?? null,
        image_url: qImages,
      });
    } else if (it.type === 'set') {
      const p = it.passage;
      if (!p || !['dialogue', 'talk', 'text', 'photo'].includes(p.kind)) { err(`${ctx}: passage.kind 오류`); continue; }
      const isLC = PARTS[part] === 'LC';
      const content = isLC ? p.script : p.content;
      if (typeof content !== 'string' || !content.trim()) err(`${ctx}: 지문(script/content) 필수`);
      if (isLC && !ACCENTS.includes(p.accent)) err(`${ctx}: LC 세트는 passage.accent 필수`);
      if (isLC && (!p.tts_voices || typeof p.tts_voices !== 'object')) err(`${ctx}: LC 세트는 tts_voices 필수`);
      if (!Array.isArray(it.questions) || it.questions.length < 1) { err(`${ctx}: questions 배열 필요`); continue; }

      const passageId = takeId(`p:${it.tmp_id}`);
      const pAudio = isLC ? audioUrlFor('passages', passageId) : null;
      passages.push({
        id: passageId, section: PARTS[part], part, kind: p.kind,
        content, image_url: p.image_url ?? null,
        audio_url: pAudio,
        accent: isLC ? p.accent : null,
        translation_ko: p.translation_ko ?? null,
      });
      const setStatus = gateOnMedia(ctx, part, status, pAudio, null);
      it.questions.forEach((sub, i) => {
        const subTmp = `${it.tmp_id}#${i + 1}`;
        const subCtx = `${ctx} 문항${i + 1}`;
        checkQuestionCore(sub, subCtx, part, content);
        pushQuestion(part, subTmp, sub, passageId, { status: setStatus, accent: isLC ? p.accent : null });
      });
    } else {
      err(`${ctx}: type은 single 또는 set`);
    }
  }
}

// 정답 위치 분포 경고 (파일 단위 40% 초과)
for (const [part, pos] of Object.entries(perPartAnswerPos)) {
  const total = pos.reduce((a, b) => a + b, 0);
  pos.forEach((n, i) => {
    if (total >= 8 && n / total > 0.4) warn(`${part}: 정답 위치 ${i}번이 ${Math.round(n / total * 100)}% (40% 초과 쏠림)`);
  });
}

// ---------- 리포트 ----------
console.log(`파일 ${files.length}개 / 문항 ${questions.length}개 / 지문 ${passages.length}개 / 태그 ${tags.length}개 / 뱃지 ${badges.length}개`);
console.log('파트별 문항·난이도 분포:');
for (const part of Object.keys(PARTS)) {
  if (!perPartDifficulty[part]) continue;
  const d = perPartDifficulty[part];
  const total = Object.values(d).reduce((a, b) => a + b, 0);
  console.log(`  ${part}: ${total}문항  난이도 ${[1, 2, 3, 4, 5].map((l) => `${l}:${d[l] || 0}`).join(' ')}`);
}
// ── 낱말 사전 (content/vocab.json → public/vocab.json) ──
// 아이가 정답 화면에서 모르는 낱말을 눌러 뜻을 보는 기능의 재료다.
// 운영 중 외부 사전 API를 부르지 않는다 — 뜻은 저작 단계에 다 적어 두고 정적 파일로 서빙한다.
// 여기서 '문항에 나오는데 뜻이 없는 낱말'을 잡는다. 이 검사가 없으면 새 문항을 넣을 때마다
// 아이가 눌러도 아무것도 안 뜨는 낱말이 조용히 늘어난다.
{
  const vocabPath = join(CONTENT, 'vocab.json');
  if (!existsSync(vocabPath)) {
    warn('content/vocab.json 이 없습니다 — 단어 뜻 보기가 동작하지 않습니다');
  } else {
    const vocab = JSON.parse(readFileSync(vocabPath, 'utf8'));
    const { words = {}, forms = {} } = vocab;
    const seen = new Set();
    const scan = (t) => {
      for (const raw of String(t ?? '').match(/[A-Za-z][A-Za-z'-]*/g) ?? []) {
        const w = raw.toLowerCase().replace(/^['-]+|['-]+$/g, '');
        if (w.length < 2 && w !== 'a' && w !== 'i') continue;
        if (w) seen.add(forms[w] ?? w);
      }
    };
    // 저작 파일을 그대로 다시 읽는다 — 위 루프의 items 는 파일마다 지역 변수라 여기서 못 본다
    for (const file of readdirSync(join(CONTENT, 'questions')).filter((f) => f.endsWith('.json'))) {
      for (const it of (readJson(join(CONTENT, 'questions', file)) ?? [])) {
        scan(it.tts_script);
        for (const qq of (it.questions ?? [it])) { scan(qq.stem); scan((qq.choices ?? []).join(' ')); }
      }
    }
    for (const p2 of passages) { scan(p2.tts_script); scan(p2.body); scan(p2.content); }
    const missing = [...seen].filter((w) => !(w in words)).sort();
    if (missing.length) {
      warn(`뜻이 없는 낱말 ${missing.length}개 — content/vocab.json 에 추가하세요: ${missing.slice(0, 15).join(', ')}${missing.length > 15 ? ' …' : ''}`);
    }
    if (!CHECK_ONLY) {
      writeFileSync(join(ROOT, 'public', 'vocab.json'), JSON.stringify(vocab));
      console.log(`낱말 사전: ${Object.keys(words).length}개 (어형 ${Object.keys(forms).length}개) → public/vocab.json`);
    }
  }
}

if (warns.length) { console.log('\n경고:'); warns.forEach((w) => console.log('  - ' + w)); }
if (errors.length) {
  console.error(`\n오류 ${errors.length}건 — 임포트 중단:`);
  errors.forEach((e) => console.error('  - ' + e));
  process.exit(1);
}
if (CHECK_ONLY) { console.log('\n검증 통과 (--check 모드, SQL 미생성)'); process.exit(0); }

// ---------- SQL 생성 (멱등 upsert) ----------
const now = new Date().toISOString();
const sql = [];
sql.push('-- 자동 생성: node tools/import.mjs (수정 금지 — content/*.json을 고치세요)');
sql.push('PRAGMA defer_foreign_keys = on;');

for (const t of tags) {
  sql.push(
    `INSERT INTO concept_tags (id, code, name_ko, section, part, exam_weight, parent_id) VALUES (` +
    [q(t.code), q(t.code), q(t.name_ko), q(t.section), q(t.part), t.exam_weight, 'NULL'].join(', ') + `) ` +
    `ON CONFLICT(id) DO UPDATE SET name_ko=excluded.name_ko, section=excluded.section, part=excluded.part, exam_weight=excluded.exam_weight;`
  );
}
for (const b of badges) {
  sql.push(
    `INSERT INTO badges (id, code, name_ko, description, icon) VALUES (` +
    [q(b.code), q(b.code), q(b.name_ko), q(b.description), q(b.icon)].join(', ') + `) ` +
    `ON CONFLICT(id) DO UPDATE SET name_ko=excluded.name_ko, description=excluded.description, icon=excluded.icon;`
  );
}
for (const p of passages) {
  sql.push(
    `INSERT INTO passages (id, section, part, kind, content, image_url, audio_url, accent, translation_ko, created_at) VALUES (` +
    [q(p.id), q(p.section), q(p.part), q(p.kind), q(p.content), q(p.image_url), q(p.audio_url), q(p.accent), q(p.translation_ko), q(now)].join(', ') + `) ` +
    `ON CONFLICT(id) DO UPDATE SET content=excluded.content, image_url=excluded.image_url, audio_url=excluded.audio_url, accent=excluded.accent, translation_ko=excluded.translation_ko;`
  );
}
for (const it of questions) {
  sql.push(
    `INSERT INTO questions (id, passage_id, section, part, stem, choices, answer_idx, explanation_ko, difficulty_label, rating, audio_url, image_url, accent, script, evidence, why_not, miss_type, key_expr, translation_ko, status, created_at) VALUES (` +
    [q(it.id), q(it.passage_id), q(it.section), q(it.part), q(it.stem), q(it.choices), it.answer_idx,
     q(it.explanation_ko), it.difficulty_label, it.rating, q(it.audio_url), q(it.image_url), q(it.accent), q(it.script), q(it.evidence),
     q(it.why_not), q(it.miss_type), q(it.key_expr), q(it.translation_ko), q(it.status), q(now)].join(', ') + `) ` +
    // rating·times_answered·times_correct·created_at은 운영 데이터 — 재임포트 시 보존
    `ON CONFLICT(id) DO UPDATE SET passage_id=excluded.passage_id, stem=excluded.stem, choices=excluded.choices, answer_idx=excluded.answer_idx, explanation_ko=excluded.explanation_ko, difficulty_label=excluded.difficulty_label, audio_url=excluded.audio_url, image_url=excluded.image_url, accent=excluded.accent, script=excluded.script, evidence=excluded.evidence, why_not=excluded.why_not, miss_type=excluded.miss_type, key_expr=excluded.key_expr, translation_ko=excluded.translation_ko, status=excluded.status;`
  );
}
const qIds = questions.map((x) => q(x.id)).join(', ');
sql.push(`DELETE FROM question_tags WHERE question_id IN (${qIds});`);
for (const qt of qTags) {
  sql.push(`INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (${q(qt.question_id)}, ${q(qt.tag_id)});`);
}

mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(join(OUT_DIR, 'seed.sql'), sql.join('\n') + '\n');
writeFileSync(IDMAP_PATH, JSON.stringify(idmap, null, 2) + '\n');
console.log(`\nseed.sql 생성 완료 (${sql.length} 문장) → tools/out/seed.sql`);
console.log('적용(로컬): npx wrangler d1 execute jumplish-db --local --file tools/out/seed.sql');
