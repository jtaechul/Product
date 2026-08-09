#!/usr/bin/env node
// 점프리시 콘텐츠 임포트 도구 (docs/content-pipeline.md 7절)
// content/*.json 검증 → tmp_id↔ULID 매핑(멱등) → tools/out/seed.sql 생성
// 사용: node tools/import.mjs [--check]   (--check: 검증만 하고 SQL 미생성)
// 주의: 재실행해도 같은 ULID를 재사용(멱등 upsert), rating·풀이 통계는 덮어쓰지 않는다.

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const CONTENT = join(ROOT, 'content');
const OUT_DIR = join(ROOT, 'tools', 'out');
const IDMAP_PATH = join(CONTENT, '.idmap.json');
const CHECK_ONLY = process.argv.includes('--check');

const RATING_BY_LABEL = { 1: 900, 2: 1050, 3: 1200, 4: 1350, 5: 1500 };
const PARTS = { L1: 'LC', L2: 'LC', L3: 'LC', L4: 'LC', R1: 'RC', R2: 'RC', R3: 'RC' };
const ACCENTS = ['US', 'UK', 'AU'];
// 실제 TOEIC Bridge 규격 — Part 2(질의응답)는 보기 3개, 나머지는 4개
const CHOICES_BY_PART = { L1: 4, L2: 3, L3: 4, L4: 4, R1: 4, R2: 4, R3: 4 };

// 해설 읽기 쉬움 기준 (초3~중3 대상)
// 문법 용어는 아이가 모르는 말이다 — 용어 대신 실제 단어를 보여주고 풀어 쓴다.
// 예) "주어 My dog는 3인칭 단수라서" → "My dog는 한 마리라서"
const HARD_TERMS = [
  '3인칭', '인칭', '단수', '복수', '주어', '동사', '명사', '형용사', '부사', '전치사',
  '관사', '시제', '과거형', '현재형', '수식', '의문사', '조동사', '정오', '목적어',
  '비교급', '최상급', '현재진행', '현재완료', '능동', '수동태', '동사원형', '부정문',
];
const EXPLANATION_MAX = 100;   // 이보다 길면 아이가 끝까지 읽지 않는다
const WHY_NOT_MAX = 40;        // 오답 이유는 한 줄에 들어와야 한다
const KEY_EXPR_KO_MAX = 30;    // 표현 카드의 뜻도 한 줄

// ---------- ULID (크록포드 base32, 모노토닉) ----------
// 같은 실행 안에서 발급 순서 = 사전순이 되도록 시퀀스를 넣는다.
// 세트(지문) 내 문항이 저작 순서대로 정렬돼야 하므로(ORDER BY id) 필수.
const B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
let ulidSeq = 0;
function ulid(now = Date.now()) {
  let time = '';
  let t = now;
  for (let i = 0; i < 10; i++) { time = B32[t % 32] + time; t = Math.floor(t / 32); }
  let seqPart = '';
  let n = ulidSeq++;
  for (let i = 0; i < 6; i++) { seqPart = B32[n % 32] + seqPart; n = Math.floor(n / 32); }
  const rand = randomBytes(10);
  let out = '';
  for (let i = 0; i < 10; i++) out += B32[rand[i] % 32];
  return time + seqPart + out;
}

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
const tagCodes = new Set(tags.map((t) => t.code));
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

// L1 보기 4컷 (img-batch 산출: public/img/l1/{id}-{0..3}.jpg)
// 4컷이 모두 있을 때만 경로 배열(JSON)을 image_url에 싣는다 — 프런트가 그림 보기로 렌더.
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
  const section = PARTS[part];
  // 실제 TOEIC Bridge 규격: Part 2(질의응답)만 보기 3개(A~C), 나머지는 4개(A~D).
  // 파트별로 못박아 두어야 저작 중에 보기 수가 실전과 어긋나는 것을 막는다.
  const wantChoices = CHOICES_BY_PART[part];
  if (!Array.isArray(it.choices) || it.choices.length !== wantChoices ||
      !it.choices.every((c) => typeof c === 'string' && c.trim())) {
    err(`${ctx}: ${part}의 choices는 정확히 ${wantChoices}개의 문자열이어야 합니다 (실제 시험 규격)`);
  }
  if (!Number.isInteger(it.answer_idx) || it.answer_idx < 0 || it.answer_idx >= (it.choices?.length || 0)) {
    err(`${ctx}: answer_idx 범위 오류`);
  }
  if (typeof it.explanation_ko !== 'string' || it.explanation_ko.trim().length < 5) {
    err(`${ctx}: explanation_ko가 비어있거나 너무 짧습니다`);
  } else {
    const hard = HARD_TERMS.filter((w) => it.explanation_ko.includes(w));
    if (hard.length) {
      err(`${ctx}: 해설에 어려운 문법 용어 [${hard.join(', ')}] — 아이 말로 풀어 쓰세요`);
    }
    if (it.explanation_ko.length > EXPLANATION_MAX) {
      err(`${ctx}: 해설이 ${it.explanation_ko.length}자 (${EXPLANATION_MAX}자 이하로)`);
    }
  }
  // 근거(선택): 지문·스크립트·문장에서 정답의 실마리가 되는 부분을 "그대로" 적으면
  // 화면이 그 자리를 형광펜으로 칠해 준다. 글 설명보다 훨씬 빨리 이해된다.
  // 한 글자라도 다르면 칠할 자리를 못 찾으므로, 원문에 실제로 있는지 여기서 막는다.
  if (it.evidence !== undefined) {
    if (typeof it.evidence !== 'string' || !it.evidence.trim()) {
      err(`${ctx}: evidence는 원문에 그대로 있는 문장(부분)이어야 합니다`);
    } else if (!source) {
      err(`${ctx}: 근거를 칠할 원문(지문·스크립트·문제 문장)이 없어 evidence를 쓸 수 없습니다`);
    } else if (!source.includes(it.evidence)) {
      err(`${ctx}: evidence "${it.evidence}"를 원문에서 찾지 못했습니다 (철자·부호까지 그대로여야 함)`);
    }
  }
  // 오답 이유(선택): 아이가 고른 보기에만 한 줄로 뜬다. 정답 자리에는 쓸 수 없다.
  if (it.why_not !== undefined) {
    if (typeof it.why_not !== 'object' || it.why_not === null || Array.isArray(it.why_not)) {
      err(`${ctx}: why_not은 {"보기번호": "이유"} 형태여야 합니다`);
    } else {
      for (const [k, v] of Object.entries(it.why_not)) {
        const i = Number(k);
        if (!Number.isInteger(i) || i < 0 || i >= (it.choices?.length || 0)) {
          err(`${ctx}: why_not의 보기번호 "${k}"가 범위를 벗어났습니다`);
        } else if (i === it.answer_idx) {
          err(`${ctx}: why_not에 정답 자리(${k})를 넣을 수 없습니다`);
        }
        if (typeof v !== 'string' || !v.trim()) err(`${ctx}: why_not[${k}]가 비어 있습니다`);
        else {
          const hard = HARD_TERMS.filter((w) => v.includes(w));
          if (hard.length) err(`${ctx}: why_not[${k}]에 어려운 용어 [${hard.join(', ')}]`);
          if (v.length > WHY_NOT_MAX) err(`${ctx}: why_not[${k}]가 ${v.length}자 (${WHY_NOT_MAX}자 이하로)`);
        }
      }
    }
  }
  // 표현 카드(선택): 이 문제에서 챙겨 갈 표현 1개
  if (it.key_expr !== undefined) {
    const k = it.key_expr;
    if (typeof k !== 'object' || k === null || typeof k.en !== 'string' || !k.en.trim()
        || typeof k.ko !== 'string' || !k.ko.trim()) {
      err(`${ctx}: key_expr은 {"en": "영어 표현", "ko": "뜻"} 형태여야 합니다`);
    } else if (k.ko.length > KEY_EXPR_KO_MAX) {
      err(`${ctx}: key_expr.ko가 ${k.ko.length}자 (${KEY_EXPR_KO_MAX}자 이하로)`);
    }
  }
  if (!Number.isInteger(it.difficulty_label) || it.difficulty_label < 1 || it.difficulty_label > 5) {
    err(`${ctx}: difficulty_label은 1~5 정수`);
  }
  if (!Array.isArray(it.tags) || it.tags.length < 1 || it.tags.length > 3) {
    err(`${ctx}: tags는 1~3개`);
  } else {
    for (const t of it.tags) {
      if (!tagCodes.has(t)) err(`${ctx}: 미등록 태그 "${t}"`);
      else if (tagSection[t] !== 'ALL' && tagSection[t] !== section) {
        err(`${ctx}: 태그 "${t}"는 ${tagSection[t]} 전용 (${section} 문항에 사용 불가)`);
      }
    }
  }
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
    evidence: it.evidence ?? null,
    why_not: it.why_not ? JSON.stringify(it.why_not) : null,
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
      if (part === 'L1' && (!Array.isArray(it.choice_image_prompts) || it.choice_image_prompts.length !== 4)) {
        err(`${ctx}: L1은 choice_image_prompts 4개 필수`);
      }
      pushQuestion(part, it.tmp_id, it, null, {
        accent: it.accent ?? null, status, audio_url: audioUrlFor('questions', takeId(`q:${it.tmp_id}`)),
        script: it.tts_script ?? null,
        image_url: part === 'L1' ? imageUrlsFor(takeId(`q:${it.tmp_id}`)) : null,
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
      passages.push({
        id: passageId, section: PARTS[part], part, kind: p.kind,
        content, image_url: p.image_url ?? null,
        audio_url: isLC ? audioUrlFor('passages', passageId) : null,
        accent: isLC ? p.accent : null,
      });
      it.questions.forEach((sub, i) => {
        const subTmp = `${it.tmp_id}#${i + 1}`;
        const subCtx = `${ctx} 문항${i + 1}`;
        checkQuestionCore(sub, subCtx, part, content);
        pushQuestion(part, subTmp, sub, passageId, { status, accent: isLC ? p.accent : null });
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
    `INSERT INTO passages (id, section, part, kind, content, image_url, audio_url, accent, created_at) VALUES (` +
    [q(p.id), q(p.section), q(p.part), q(p.kind), q(p.content), q(p.image_url), q(p.audio_url), q(p.accent), q(now)].join(', ') + `) ` +
    `ON CONFLICT(id) DO UPDATE SET content=excluded.content, image_url=excluded.image_url, audio_url=excluded.audio_url, accent=excluded.accent;`
  );
}
for (const it of questions) {
  sql.push(
    `INSERT INTO questions (id, passage_id, section, part, stem, choices, answer_idx, explanation_ko, difficulty_label, rating, audio_url, image_url, accent, script, evidence, why_not, key_expr, status, created_at) VALUES (` +
    [q(it.id), q(it.passage_id), q(it.section), q(it.part), q(it.stem), q(it.choices), it.answer_idx,
     q(it.explanation_ko), it.difficulty_label, it.rating, q(it.audio_url), q(it.image_url), q(it.accent), q(it.script), q(it.evidence),
     q(it.why_not), q(it.key_expr), q(it.status), q(now)].join(', ') + `) ` +
    // rating·times_answered·times_correct·created_at은 운영 데이터 — 재임포트 시 보존
    `ON CONFLICT(id) DO UPDATE SET passage_id=excluded.passage_id, stem=excluded.stem, choices=excluded.choices, answer_idx=excluded.answer_idx, explanation_ko=excluded.explanation_ko, difficulty_label=excluded.difficulty_label, audio_url=excluded.audio_url, image_url=excluded.image_url, accent=excluded.accent, script=excluded.script, evidence=excluded.evidence, why_not=excluded.why_not, key_expr=excluded.key_expr, status=excluded.status;`
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
