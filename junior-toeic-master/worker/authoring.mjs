// 문항 저작 규칙집 — **자를 한 벌만 둔다.**
//
// 예전에는 이 규칙이 tools/import.mjs 안에만 있었다. 관리자 화면에서도 문항을 만들게 되면서
// 규칙을 한 벌 더 쓰면, 관리자 화면은 통과시켰는데 배포 때 import 가 막는 문항이 생긴다
// (반대도 마찬가지 — 화면에서 막힌 문항이 파일로는 들어간다). 그래서 검사 규칙과 ULID 생성을
// 여기 한곳에 두고, 개발 도구(tools/import.mjs)와 관리자 API(worker/index.mjs)가 함께 쓴다.
//
// 이 파일은 파일 시스템을 만지지 않는다 — Cloudflare Workers 안에서도 그대로 돌아야 한다.
// 음원·사진이 실제로 있는지 보는 검사(gateOnMedia)는 파일을 봐야 하므로 import.mjs 몫이다.

import { MISS_KO } from './engine.mjs';

export const PARTS = { L1: 'LC', L2: 'LC', L3: 'LC', L4: 'LC', R1: 'RC', R2: 'RC', R3: 'RC' };
export const PART_LIST = Object.keys(PARTS);
export const ACCENTS = ['US', 'UK', 'AU'];
export const STATUSES = ['draft', 'active', 'retired'];
export const PASSAGE_KINDS = ['dialogue', 'talk', 'text', 'photo'];
export const RATING_BY_LABEL = { 1: 900, 2: 1050, 3: 1200, 4: 1350, 5: 1500 };

// 실제 TOEIC Bridge 규격 — Part 2(질의응답)는 보기 3개, 나머지는 4개
export const CHOICES_BY_PART = { L1: 4, L2: 3, L3: 4, L4: 4, R1: 4, R2: 4, R3: 4 };

// 파트를 사람 말로. 관리자 화면의 고르는 자리와 오류 문구에 같이 쓴다.
export const PART_KO = {
  L1: '듣기 · 사진 고르기', L2: '듣기 · 질의응답', L3: '듣기 · 짧은 대화', L4: '듣기 · 짧은 담화',
  R1: '읽기 · 문장 완성', R2: '읽기 · 지문 완성', R3: '읽기 · 독해',
};
// 파트별 형태 — single(단독 문항) / set(지문 묶음). R3는 둘 다 쓴다.
export const PART_FORM = { L1: 'single', L2: 'single', L3: 'set', L4: 'set', R1: 'single', R2: 'set', R3: 'both' };

// 해설 읽기 쉬움 기준 (초3~중3 대상)
// 문법 용어는 아이가 모르는 말이다 — 용어 대신 실제 단어를 보여주고 풀어 쓴다.
// 예) "주어 My dog는 3인칭 단수라서" → "My dog는 한 마리라서"
export const HARD_TERMS = [
  '3인칭', '인칭', '단수', '복수', '주어', '동사', '명사', '형용사', '부사', '전치사',
  '관사', '시제', '과거형', '현재형', '수식', '의문사', '조동사', '정오', '목적어',
  '비교급', '최상급', '현재진행', '현재완료', '능동', '수동태', '동사원형', '부정문',
];
export const EXPLANATION_MAX = 100;   // 이보다 길면 아이가 끝까지 읽지 않는다
export const WHY_NOT_MAX = 40;        // 오답 이유는 한 줄에 들어와야 한다
export const KEY_EXPR_KO_MAX = 30;    // 표현 카드의 뜻도 한 줄

// ---------- ULID (크록포드 base32, 모노토닉) ----------
// 같은 실행 안에서 발급 순서 = 사전순이 되도록 시퀀스를 넣는다.
// 세트(지문) 내 문항이 저작 순서대로 정렬돼야 하므로(ORDER BY id) 필수.
// 난수는 Web Crypto 로 뽑는다 — Node 22 와 Workers 양쪽에 다 있다.
const B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
export function makeUlid() {
  let seq = 0;
  return function ulid(now = Date.now()) {
    let time = '';
    let t = now;
    for (let i = 0; i < 10; i++) { time = B32[t % 32] + time; t = Math.floor(t / 32); }
    let seqPart = '';
    let n = seq++;
    for (let i = 0; i < 6; i++) { seqPart = B32[n % 32] + seqPart; n = Math.floor(n / 32); }
    const rand = crypto.getRandomValues(new Uint8Array(10));
    let out = '';
    for (let i = 0; i < 10; i++) out += B32[rand[i] % 32];
    return time + seqPart + out;
  };
}

// ---------- 문항 한 개 검사 ----------
// tagSection: { 태그코드: 'LC' | 'RC' | 'ALL' } — 등록된 태그 목록이자 쓸 수 있는 자리 표.
// source: 근거(evidence)를 칠할 원문. 없으면 evidence 를 쓸 수 없다.
// 반환: 사람이 읽는 한국어 오류 문장 배열 (비어 있으면 통과).
export function validateQuestionCore(it, ctx, part, source, tagSection) {
  const out = [];
  const err = (m) => out.push(`${ctx}: ${m}`);
  const section = PARTS[part];

  const wantChoices = CHOICES_BY_PART[part];
  if (!Array.isArray(it.choices) || it.choices.length !== wantChoices ||
      !it.choices.every((c) => typeof c === 'string' && c.trim())) {
    err(`${part}의 보기는 정확히 ${wantChoices}개여야 합니다 (실제 시험 규격)`);
  }
  if (!Number.isInteger(it.answer_idx) || it.answer_idx < 0 || it.answer_idx >= (it.choices?.length || 0)) {
    err('정답 자리(answer_idx)가 보기 범위를 벗어났습니다');
  }
  if (typeof it.explanation_ko !== 'string' || it.explanation_ko.trim().length < 5) {
    err('해설이 비어있거나 너무 짧습니다');
  } else {
    const hard = HARD_TERMS.filter((w) => it.explanation_ko.includes(w));
    if (hard.length) err(`해설에 아이가 모르는 문법 용어 [${hard.join(', ')}] — 쉬운 말로 풀어 쓰세요`);
    if (it.explanation_ko.length > EXPLANATION_MAX) {
      err(`해설이 ${it.explanation_ko.length}자입니다 (${EXPLANATION_MAX}자 이하로)`);
    }
  }
  // 근거(선택): 지문·스크립트·문장에서 정답의 실마리가 되는 부분을 "그대로" 적으면
  // 화면이 그 자리를 형광펜으로 칠해 준다. 한 글자라도 다르면 칠할 자리를 못 찾는다.
  if (it.evidence !== undefined && it.evidence !== null && it.evidence !== '') {
    if (typeof it.evidence !== 'string' || !it.evidence.trim()) {
      err('근거는 원문에 그대로 있는 문장(부분)이어야 합니다');
    } else if (!source) {
      err('근거를 칠할 원문(지문·들려줄 문장·문제 문장)이 없어 근거를 쓸 수 없습니다');
    } else if (!source.includes(it.evidence)) {
      err(`근거 "${it.evidence}"를 원문에서 찾지 못했습니다 (철자·부호까지 똑같아야 합니다)`);
    }
  }
  // 오답 이유(선택): 아이가 고른 보기에만 한 줄로 뜬다. 정답 자리에는 쓸 수 없다.
  if (it.why_not !== undefined && it.why_not !== null) {
    if (typeof it.why_not !== 'object' || Array.isArray(it.why_not)) {
      err('오답 이유는 {"보기번호": "이유"} 형태여야 합니다');
    } else {
      for (const [k, v] of Object.entries(it.why_not)) {
        const i = Number(k);
        if (!Number.isInteger(i) || i < 0 || i >= (it.choices?.length || 0)) {
          err(`오답 이유의 보기번호 "${k}"가 범위를 벗어났습니다`);
        } else if (i === it.answer_idx) {
          err(`정답 자리(${k})에는 오답 이유를 쓸 수 없습니다`);
        }
        if (typeof v !== 'string' || !v.trim()) err(`보기 ${k}의 오답 이유가 비어 있습니다`);
        else {
          const hard = HARD_TERMS.filter((w) => v.includes(w));
          if (hard.length) err(`보기 ${k} 오답 이유에 어려운 용어 [${hard.join(', ')}]`);
          if (v.length > WHY_NOT_MAX) err(`보기 ${k} 오답 이유가 ${v.length}자입니다 (${WHY_NOT_MAX}자 이하로)`);
        }
      }
    }
  }
  // 실수 유형: 오답 자리마다 딱지 하나. 딱지가 빠지면 그 오답만 통계에서 조용히 사라진다.
  if (it.miss_type !== undefined || it.why_not !== undefined) {
    const mt = it.miss_type;
    const hasWhy = it.why_not && typeof it.why_not === 'object' && !Array.isArray(it.why_not);
    if (hasWhy && (typeof mt !== 'object' || mt === null || Array.isArray(mt))) {
      err('오답 이유를 썼으면 실수 유형도 같은 자리마다 골라야 합니다');
    } else if (mt && typeof mt === 'object' && !Array.isArray(mt)) {
      for (const [k, v] of Object.entries(mt)) {
        if (!hasWhy || it.why_not[k] === undefined) err(`실수 유형 ${k}에 짝이 되는 오답 이유가 없습니다`);
        if (!MISS_KO[v]) err(`모르는 실수 유형 "${v}"`);
      }
      if (hasWhy) {
        for (const k of Object.keys(it.why_not)) {
          if (mt[k] === undefined) err(`보기 ${k}의 실수 유형이 비었습니다`);
        }
      }
    }
  }
  // 표현 카드(선택): 이 문제에서 챙겨 갈 표현 1개
  if (it.key_expr !== undefined && it.key_expr !== null) {
    const k = it.key_expr;
    if (typeof k !== 'object' || Array.isArray(k) || typeof k.en !== 'string' || !k.en.trim()
        || typeof k.ko !== 'string' || !k.ko.trim()) {
      err('표현 카드는 영어 표현과 뜻을 모두 채워야 합니다');
    } else if (k.ko.length > KEY_EXPR_KO_MAX) {
      err(`표현 카드의 뜻이 ${k.ko.length}자입니다 (${KEY_EXPR_KO_MAX}자 이하로)`);
    }
  }
  if (!Number.isInteger(it.difficulty_label) || it.difficulty_label < 1 || it.difficulty_label > 5) {
    err('난이도는 1~5 중 하나여야 합니다');
  }
  if (!Array.isArray(it.tags) || it.tags.length < 1 || it.tags.length > 3) {
    err('태그는 1~3개를 골라야 합니다');
  } else if (tagSection) {
    for (const t of it.tags) {
      if (!(t in tagSection)) err(`등록되지 않은 태그 "${t}"`);
      else if (tagSection[t] !== 'ALL' && tagSection[t] !== section) {
        err(`태그 "${t}"는 ${tagSection[t] === 'LC' ? '듣기' : '읽기'} 전용이라 이 문항에 쓸 수 없습니다`);
      }
    }
  }
  return out;
}

// ---------- 저작 단위(single·set) 한 덩어리 검사 ----------
// import.mjs 의 파일 순회와 관리자 저작 API 가 같은 규칙을 쓰게 하는 입구.
export function validateItem(it, part, tagSection) {
  const out = [];
  const ctx = it?.tmp_id || '새 문항';
  const err = (m) => out.push(`${ctx}: ${m}`);
  if (!PARTS[part]) { err(`모르는 파트 "${part}"`); return out; }
  if (it?.part && it.part !== part) err(`파트(${it.part})가 저장할 파일(${part})과 다릅니다`);
  const status = it?.status || 'active';
  if (!STATUSES.includes(status)) err('상태는 준비중(draft)·출제중(active)·내림(retired) 중 하나여야 합니다');

  if (it?.type === 'single') {
    // 단독 문항의 "원문" = LC는 들려주는 문장, RC는 문제 문장 자체
    out.push(...validateQuestionCore(it, ctx, part, it.tts_script || it.stem || null, tagSection));
    if (PARTS[part] === 'LC') {
      if (typeof it.tts_script !== 'string' || !it.tts_script.trim()) err('듣기 문항은 들려줄 문장(대본)이 필요합니다');
      if (!ACCENTS.includes(it.accent)) err('듣기 문항은 발음(미국·영국·호주)을 골라야 합니다');
    }
    if (part === 'L1') {
      const qs = it.choice_image_queries;
      if (!Array.isArray(qs) || qs.length !== 4) {
        err('사진 고르기는 보기 4컷의 사진 검색 조건이 필요합니다');
      } else {
        qs.forEach((c, i) => {
          if (!c || typeof c.q !== 'string' || !c.q.trim()) err(`보기${i} 사진 검색어가 없습니다`);
          if (!Array.isArray(c.need) || !c.need.length) err(`보기${i} 사진에 꼭 있어야 할 말(need)이 1개 이상 필요합니다`);
          if (c.avoid !== undefined && !Array.isArray(c.avoid)) err(`보기${i} 피할 말(avoid)은 목록이어야 합니다`);
        });
      }
      if (!Array.isArray(it.choice_image_prompts) || it.choice_image_prompts.length !== 4) {
        err('사진 고르기는 보기 4컷의 사진 설명이 필요합니다');
      }
    }
  } else if (it?.type === 'set') {
    const p = it.passage;
    const isLC = PARTS[part] === 'LC';
    if (!p || !PASSAGE_KINDS.includes(p.kind)) { err('지문 종류(kind)가 잘못됐습니다'); return out; }
    const content = isLC ? p.script : p.content;
    if (typeof content !== 'string' || !content.trim()) err(isLC ? '들려줄 대본이 필요합니다' : '지문이 필요합니다');
    if (isLC && !ACCENTS.includes(p.accent)) err('듣기 지문은 발음(미국·영국·호주)을 골라야 합니다');
    if (isLC && (!p.tts_voices || typeof p.tts_voices !== 'object')) err('듣기 지문은 성우 배정(tts_voices)이 필요합니다');
    if (!Array.isArray(it.questions) || it.questions.length < 1) { err('지문에 딸린 문항이 1개 이상 필요합니다'); return out; }
    it.questions.forEach((sub, i) => {
      out.push(...validateQuestionCore(sub, `${ctx} 문항${i + 1}`, part, content, tagSection));
    });
  } else {
    err('형태(type)는 단독 문항(single) 또는 지문 묶음(set)이어야 합니다');
  }
  return out;
}

export { MISS_KO };
